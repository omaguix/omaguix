"""Archive/install fixtures mock Guix; the optional integration uses real throwaway keys."""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("static_tree", str(ROOT / "scripts/static-tree"))
spec = importlib.util.spec_from_loader(loader.name, loader)
tree = importlib.util.module_from_spec(spec)
loader.exec_module(tree)


def fixture(directory, digit="0", size=4):
    directory.mkdir(exist_ok=True)
    (directory / "nix-cache-info").write_text("StoreDir: /gnu/store\nWantMassQuery: 0\nPriority: 100\n")
    item = "/gnu/store/" + digit * 32 + "-fixture"
    relative = "nar/gzip/" + Path(item).name
    payload = directory / relative
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_bytes(b"x" * size)  # Archive fixture, deliberately NOT a real NAR.
    (directory / (digit * 32 + ".narinfo")).write_text(
        f"StorePath: {item}\nNarHash: sha256:{'0' * 52}\nNarSize: {size}\nReferences: \n"
        f"Signature: 1;fixture;ZmFrZQ==\nURL: /{relative}\nCompression: gzip\nFileSize: {size}\n")
    return item


def fixture_guix(command, **kwargs):
    # Only a gateway mock. Neither crypto nor Guix's NAR decoder is emulated.
    env = kwargs["env"]
    rows = []
    for name in Path(env["STATIC_NARINFO_LIST"]).read_text().splitlines():
        fields = dict(line.split(": ", 1) for line in Path(name).read_text().splitlines())
        relative = fields["URL"].lstrip("/")
        if "STATIC_TREE" in env and not (Path(env["STATIC_TREE"]) / relative).is_file():
            raise subprocess.CalledProcessError(1, command)
        rows.append(f"{fields['StorePath']}\t{relative}\t{relative}\n")
    return subprocess.CompletedProcess(command, 0, "".join(rows), "")


class Fixtures(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.key = self.root / "fixture.pub"
        self.key.write_text("not a real key")
        patch = mock.patch.object(tree.subprocess, "run", side_effect=fixture_guix)
        self.gateway = patch.start()
        self.addCleanup(patch.stop)

    def release(self, number=1, digit="0", prefix="x86_64-desktop", reused=()):
        stage = self.root / f"tree-{prefix}-{number}"
        item = fixture(stage, digit)
        output = self.root / f"release-{prefix}-{number}"
        tree.pack(stage, output, {"version": 1, "tag": f"{prefix}-20261012-abcdef0-{number}",
                  "prefix": prefix, "created": f"2026-10-12T12:00:{number:02d}+00:00",
                  "guix_commit": tree.PIN, "workflow_commit": "a" * 40, "channel_commit": "b" * 40,
                  "system": "x86_64-linux" if prefix == "x86_64-desktop" else "aarch64-linux",
                  "roguix": [item, *reused]})
        return output, item

    def test_verification_is_delegated_once_with_one_tree_and_key(self):
        stage = self.root / "tree"
        item = fixture(stage)
        self.assertEqual(tree.verify(stage, self.key), {item})
        self.gateway.assert_called_once()
        env = self.gateway.call_args.kwargs["env"]
        self.assertEqual(env["STATIC_PUBLIC_KEY"], str(self.key))
        self.assertEqual(env["STATIC_TREE"], str(stage))
        self.assertIn("--commit=" + tree.PIN, self.gateway.call_args.args[0])
        source = (ROOT / "scripts/verify-substitutes.scm").read_text()
        for text in ("signature-case", "(public-keys->acl (list public-key))",
                     "decompressed-port", "open-hash-input-port", "narinfo-size"):
            self.assertIn(text, source)
        self.assertNotIn("valid-narinfo?", source)

    def test_unsigned_extra_files_are_rejected(self):
        stage = self.root / "tree"
        fixture(stage)
        (stage / "extra").write_text("not a substitute")
        with self.assertRaisesRegex(ValueError, "unsigned extra"):
            tree.verify(stage, self.key)

    def test_verifier_rejection_prevents_install(self):
        release, _ = self.release()
        self.gateway.side_effect = subprocess.CalledProcessError(1, "guix")
        target = self.root / "static"
        with self.assertRaises(subprocess.CalledProcessError):
            tree.install(release, target, self.key)
        self.assertFalse(list(target.glob("*.narinfo")))
        self.assertFalse(list((target / ".roguix").glob("*.json")))

    def test_tarball_batching_and_oversized_file_fail_closed(self):
        stage = self.root / "tree"
        for digit in ("0", "1", "2"):
            fixture(stage, digit, size=4000)
        output = self.root / "packed"
        tree.pack(stage, output, {"roguix": []}, limit=25000)
        assets = list(output.glob("tree-*.tar"))
        self.assertGreater(len(assets), 1)
        self.assertTrue(all(p.stat().st_size < 25000 and tarfile.is_tarfile(p) for p in assets))
        with self.assertRaisesRegex(ValueError, "single NAR"):
            tree.pack(stage, self.root / "too-small", {}, limit=16000)

    def test_checksum_tamper_rejected(self):
        release, _ = self.release()
        next(release.glob("tree-*.tar")).write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            tree.install(release, self.root / "static", self.key)

    def test_safe_extraction_rejects_paths_links_specials_and_duplicates(self):
        for name in ("../outside", "/absolute", "./nix-cache-info", "nar/../outside"):
            with self.assertRaises(ValueError):
                tree.safe(name)
        for index, kind in enumerate((tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.REGTYPE)):
            release, _ = self.release(index + 1)
            asset = next(release.glob("tree-*.tar"))
            with tarfile.open(asset, "w") as archive:
                info = tarfile.TarInfo("nix-cache-info")
                info.type, info.linkname = kind, "../../outside"
                archive.addfile(info)
                if kind == tarfile.REGTYPE:
                    archive.addfile(info)
            (release / "SHA256SUMS").write_text(
                f"{tree.sha(release / 'manifest.json')}  manifest.json\n{tree.sha(asset)}  {asset.name}\n")
            expected = FileExistsError if kind == tarfile.REGTYPE else ValueError
            with self.assertRaises(expected):
                tree.install(release, self.root / "static", self.key)
        self.assertFalse((self.root / "outside").exists())

    def test_nars_before_narinfos_and_no_deletion_by_default(self):
        first, old = self.release()
        second, new = self.release(2, "1", reused=[old])
        target = self.root / "static"
        tree.install(first, target, self.key)
        replaced, replace = [], os.replace
        def record(source, dest):
            replaced.append(Path(dest).relative_to(target).as_posix())
            return replace(source, dest)
        with mock.patch.object(tree.os, "replace", side_effect=record):
            tree.install(second, target, self.key)
        self.assertLess(replaced.index("nar/gzip/" + Path(new).name), replaced.index("1" * 32 + ".narinfo"))
        self.assertTrue((target / ("0" * 32 + ".narinfo")).exists())
        tree.prune(target, 1, self.key)
        self.assertTrue((target / "nar/gzip" / Path(old).name).exists())

    def test_retention_per_architecture_not_install_order(self):
        first, old = self.release(1)
        second, new = self.release(2, "1")
        arm, arm_item = self.release(3, "2", "aarch64-desktop")
        target = self.root / "static"
        for release in (second, arm, first):
            tree.install(release, target, self.key)
        tree.prune(target, 1, self.key)
        self.assertFalse((target / "nar/gzip" / Path(old).name).exists())
        for item in (new, arm_item):
            self.assertTrue((target / "nar/gzip" / Path(item).name).exists())

    def test_missing_backfill_blocks_pruning_without_deleting_old_items(self):
        first, old = self.release()
        missing = "/gnu/store/" + "2" * 32 + "-missing"
        second, _ = self.release(2, "1", reused=[missing])
        target = self.root / "static"
        for release in (first, second):
            tree.install(release, target, self.key)
        with self.assertRaises(FileNotFoundError):
            tree.prune(target, 1, self.key)
        self.assertTrue((target / "nar/gzip" / Path(old).name).exists())

    def backfill(self, digits, stamp="20261012T120000Z", extra=()):
        stage = self.root / ("bf-" + stamp + digits)
        items = [fixture(stage, d) for d in digits]
        output = self.root / ("backfill-" + stamp + digits)
        tag = "backfill-x86_64-" + stamp
        tree.pack(stage, output, {"version": 1, "tag": tag, "prefix": "backfill-x86_64",
                  "created": f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}T12:00:00+00:00",
                  "guix_commit": tree.PIN, "roguix": sorted(items)})
        return output, items

    def pack_backfill(self, mirror, lines, name="out"):
        listing = self.root / (name + ".txt")
        listing.write_text(lines)
        args = mock.Mock(tree=mirror, items=listing, arch="x86_64", output=self.root / name)
        tree.pack_backfill(args)
        return args.output

    def test_pack_backfill_packs_only_listed_and_fails_closed(self):
        mirror = self.root / "mirror"
        wanted = fixture(mirror, "0")
        fixture(mirror, "1")
        (mirror / "extra").write_text("ignored")
        output = self.pack_backfill(mirror, wanted + "\n")
        manifest = tree.read_manifest(output)
        self.assertEqual(manifest["roguix"], [wanted])
        self.assertRegex(manifest["tag"], r"backfill-x86_64-[0-9]{8}T[0-9]{6}Z")
        for key in ("system", "channel_commit", "workflow_commit"):
            self.assertNotIn(key, manifest)
        with tarfile.open(output / "tree-0000.tar") as archive:
            self.assertEqual(sorted(archive.getnames()),
                             sorted(["nix-cache-info", "0" * 32 + ".narinfo", "nar/gzip/" + Path(wanted).name]))
        missing = "/gnu/store/" + "2" * 32 + "-missing"
        with self.assertRaises(OSError):
            self.pack_backfill(mirror, missing + "\n", "m1")
        (mirror / "nar/gzip" / Path(wanted).name).unlink()
        with self.assertRaises(ValueError):
            self.pack_backfill(mirror, wanted + "\n", "m2")
        for bad in ("\n" + wanted + "\n", wanted + "\n" + wanted + "\n", "/etc/passwd\n"):
            with self.assertRaises(ValueError):
                self.pack_backfill(mirror, bad, "bad")

    def test_backfill_survives_prune_until_covered_and_does_not_count_toward_keep(self):
        target = self.root / "static"
        release, item = self.release(1, "0")
        first, (a,) = self.backfill("1", "20261012T120000Z")
        second, (b,) = self.backfill("2", "20261013T120000Z")
        for r in (release, first, second):
            tree.install(r, target, self.key)
        tree.prune(target, 1, self.key)
        for i in (item, a, b):
            self.assertTrue((target / "nar/gzip" / Path(i).name).exists())
        self.assertEqual(len(list((target / ".roguix").glob("backfill-*.json"))), 2)
        newer, _ = self.release(2, "3", reused=[a])
        tree.install(newer, target, self.key, keep=1)
        names = {p.name for p in (target / ".roguix").glob("*.json")}
        self.assertEqual(names, {"x86_64-desktop-20261012-abcdef0-2.json", "backfill-x86_64-20261013T120000Z.json"})
        self.assertTrue((target / "nar/gzip" / Path(a).name).exists())
        self.assertFalse((target / "nar/gzip" / Path(item).name).exists())

    def test_covered_backfill_record_is_removed(self):
        target = self.root / "static"
        first, (a,) = self.backfill("1")
        release, _ = self.release(1, "0", reused=[a])
        for r in (first, release):
            tree.install(r, target, self.key)
        tree.prune(target, 1, self.key)
        self.assertEqual([p.name for p in (target / ".roguix").glob("*.json")],
                         ["x86_64-desktop-20261012-abcdef0-1.json"])
        self.assertTrue((target / "nar/gzip" / Path(a).name).exists())

    def test_invalid_backfill_tag_rejected(self):
        for tag in ("backfill-riscv-20261012T120000Z", "backfill-x86_64-20261312T120000Z",
                    "backfill-x86_64-20261012", "backfill-x86_64-20261012T120000Z-1"):
            self.assertIsNone(tree.TAG.fullmatch(tag))
        release, _ = self.backfill("1")
        manifest = tree.json.loads((release / "manifest.json").read_text())
        manifest["tag"] = "backfill-x86_64-bogus"
        (release / "manifest.json").write_text(tree.json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "invalid manifest"):
            tree.read_manifest(release)

    def test_destination_symlink_rejected(self):
        release, _ = self.release()
        target = self.root / "static"
        target.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        (target / "nar").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "linked destination"):
            tree.install(release, target, self.key)
        self.assertFalse(list(outside.iterdir()))

    def test_listener_is_inherited_through_exec_without_rebinding(self):
        tools = self.root / "bin"
        tools.mkdir()
        fake = tools / "guix"
        fake.write_text("#!" + sys.executable + '''
import os, socket
from http.server import BaseHTTPRequestHandler, HTTPServer
assert int(os.environ["LISTEN_PID"]) == os.getpid()
assert os.environ["LISTEN_FDS"] == "1"
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ready")
    def log_message(self, *args): pass
server = HTTPServer(("127.0.0.1", 0), Handler, bind_and_activate=False)
server.socket.close()
server.socket = socket.socket(fileno=3)
server.serve_forever()
''')
        fake.chmod(0o755)
        command = [sys.executable, str(ROOT / "scripts/static-tree"), "serve", "--key", str(self.key),
                   "--secret", str(self.key), "--cache", str(self.root / "cache"), "--log", str(self.root / "log")]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   env={**os.environ, "PATH": str(tools) + os.pathsep + os.environ["PATH"]})
        try:
            port = process.stdout.readline().strip()  # Positive listener event, or EOF on failure.
            self.assertTrue(port.isdigit())
            import urllib.request
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open("http://127.0.0.1:" + port, timeout=10) as response:
                self.assertEqual(response.read(), b"ready")
        finally:
            process.terminate()
            process.communicate()

    def test_workflow_main_push_and_owner_dispatch_scope(self):
        source = (ROOT / ".github/workflows/build-desktop.yml").read_text()
        sign = source.split("  sign-substitutes:")[1]
        for text in ("github.ref == 'refs/heads/main'", "github.event_name == 'push'",
                     "github.event_name == 'workflow_dispatch'", "github.actor == github.repository_owner",
                     "environment: substitute-signing"):
            self.assertIn(text, sign)
        self.assertEqual(source.count("contents: write"), 1)
        self.assertEqual(source.count("secrets.SUBSTITUTE_SIGNING_KEY"), 1)
        import re
        self.assertTrue(all(re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", action)
                            for action in re.findall(r"uses: ([^\s#]+)", source)))


@unittest.skipUnless(shutil.which("guix"), "Guix absent: live signing, decompression and NAR hash checks not run")
class GuixIntegration(unittest.TestCase):
    def test_throwaway_key_bake_install_and_wrong_key(self):
        import gzip
        with tempfile.TemporaryDirectory(prefix="roguix-live-test-") as directory:
            temp = Path(directory).resolve()
            (temp / "payload.gz").write_bytes(gzip.compress(b"tiny compressed item", mtime=0))
            env = {**os.environ, "STATIC_TEST_DIR": str(temp)}
            subprocess.run(["guix", "time-machine", "--commit=" + tree.PIN, "--", "repl", "--",
                            str(ROOT / "tests/guix-fixture.scm")], env=env, check=True)
            items = (temp / "items.txt").read_text()
            split = temp / "split"
            split.mkdir()
            for name, data in {"publish.txt": items, "vps-has.txt": "", "guix-commit.txt": tree.PIN,
                               "channel-commit.txt": "b" * 40, "system.txt": "x86_64-linux"}.items():
                (split / name).write_text(data)
            env["SUBSTITUTE_SIGNING_KEY"] = (temp / "test.sec").read_text()
            release = temp / "release"
            subprocess.run([str(ROOT / "scripts/static-substitutes"), "bake", "--split", str(split),
                            "--output", str(release), "--key", str(temp / "test.pub"),
                            "--tag", "x86_64-desktop-20261012-abcdef0-1", "--workflow-commit", "a" * 40],
                           env=env, check=True)
            target = temp / "static"
            tree.install(release, target, temp / "test.pub")
            with self.assertRaises(subprocess.CalledProcessError):
                tree.verify(target, temp / "wrong.pub")
            nar = next((target / "nar").rglob("*-roguix-static-test"))
            raw = gzip.decompress(nar.read_bytes()).replace(b"tiny test item", b"evil test item")
            nar.write_bytes(gzip.compress(raw, mtime=0))
            # FileSize is unsigned transport metadata; preserve the valid
            # signature so this checks the signed uncompressed NarHash.
            import re
            info = target / (nar.name.split("-", 1)[0] + ".narinfo")
            info.write_text(re.sub(r"FileSize: [0-9]+", f"FileSize: {nar.stat().st_size}", info.read_text()))
            with self.assertRaises(subprocess.CalledProcessError):
                tree.verify(target, temp / "test.pub")


if __name__ == "__main__":
    unittest.main()
