"""desktop-split against a fake store graph and fake narinfo servers: no Guix, no network."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FAKE_GUIX = '''
import os, sys
graph = {}
for line in open(os.environ["FAKE_GRAPH"]):
    item, *refs = line.split()
    graph[item] = refs
args = sys.argv[1:]
if args[:2] == ["gc", "-R"]:
    items = args[2:] or sys.stdin.read().split()
    seen, todo = set(), list(items)
    while todo:
        item = todo.pop()
        if item not in graph:
            sys.exit("guix gc: error: path `%s' is not valid" % item)
        if item not in seen:
            seen.add(item)
            todo.extend(graph[item])
    print("\\n".join(sorted(seen)))
elif args[:2] == ["gc", "--references"]:
    print("\\n".join(graph[args[2]]))
else:
    sys.exit("fake guix: unexpected %r" % args)
'''

FAKE_CURL = '''
import os, sys
url = sys.argv[-1]
host, name = url.split("/")[2], url.split("/")[-1]
codes = dict(line.split() for line in open(os.environ["FAKE_STATUS_" + host.split(".")[0].upper()]))
print(codes.get(name[:-len(".narinfo")], "404"), end="")
'''


def item(digit, name):
    return f"/gnu/store/{digit * 32}-{name}"


PACKAGE = item("1", "hello-2.12")
LIBC = item("2", "glibc-2.41")
PROFILE = item("3", "profile")
GUIX = item("4", "guix-a54c94c")
SYSTEM = item("5", "system")


class DesktopSplit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.bin = root / "bin"
        self.bin.mkdir()
        for name, source in (("guix", FAKE_GUIX), ("curl", FAKE_CURL)):
            (self.bin / name).write_text("#!" + sys.executable + "\n" + source)
            (self.bin / name).chmod(0o755)
        self.dir = root / "split"
        self.dir.mkdir()
        self.graph = {PACKAGE: [LIBC], LIBC: [], PROFILE: [GUIX], GUIX: [LIBC],
                      SYSTEM: [PACKAGE]}
        self.bordeaux = {LIBC}
        self.omaguix = set()
        (self.dir / "licenses.txt").write_text(f"{PACKAGE} hello GPL 3+\n{LIBC} glibc LGPL 2.1+\n")
        (self.dir / "closure.txt").write_text(f"{SYSTEM}\n{PACKAGE}\n{LIBC}\n")

    def split(self, *options):
        root = Path(self.tmp.name)
        (root / "graph").write_text("".join(f"{k} {' '.join(v)}\n" for k, v in self.graph.items()))
        for host, served in (("BORDEAUX", self.bordeaux), ("SUBSTITUTES", self.omaguix)):
            (root / host).write_text("".join(f"{Path(i).name[:32]} 200\n" for i in served))
        env = {**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
               "FAKE_GRAPH": str(root / "graph"), "FAKE_STATUS_BORDEAUX": str(root / "BORDEAUX"),
               "FAKE_STATUS_SUBSTITUTES": str(root / "SUBSTITUTES")}
        return subprocess.run([str(ROOT / "scripts/desktop-split"), *options, str(self.dir)],
                              env=env, capture_output=True, text=True)

    def lines(self, name):
        path = self.dir / name
        return path.read_text().split() if path.exists() else []

    def test_profile_and_its_closure_are_split_like_packages(self):
        result = self.split("--guix-profile", PROFILE, "--release-tag", "x86_64-desktop-tag")
        self.assertEqual(result.returncode, 0, result.stderr)
        closure = self.lines("package-closure.txt")
        self.assertEqual(sorted(closure), sorted([PACKAGE, LIBC, PROFILE, GUIX]))
        lists = [self.lines(n) for n in ("publish.txt", "vps-fetch.txt", "vps-has.txt")]
        self.assertEqual(sorted(sum(lists, [])), sorted(closure))
        self.assertEqual(len(set(sum(lists, []))), len(closure))
        self.assertEqual(sorted(lists[0]), sorted([PACKAGE, PROFILE, GUIX]))
        self.assertEqual(self.lines("release-tag.txt"), ["x86_64-desktop-tag"])

    def test_without_a_profile_the_closure_is_the_packages_only(self):
        result = self.split("--release-tag", "t")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(self.lines("package-closure.txt")), sorted([PACKAGE, LIBC]))

    def test_nothing_to_publish_leaves_the_tag_empty(self):
        self.bordeaux = {LIBC, GUIX}
        self.omaguix = {PACKAGE, PROFILE}
        result = self.split("--guix-profile", PROFILE, "--release-tag", "t")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.lines("publish.txt"), [])
        self.assertEqual((self.dir / "release-tag.txt").read_text(), "")

    def test_items_to_publish_need_a_tag(self):
        result = self.split("--guix-profile", PROFILE)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no --release-tag", result.stderr)

    def test_only_the_named_profile_is_exempt_from_the_per_machine_refusal(self):
        other = item("6", "profile")
        self.graph[PROFILE] = [GUIX, other]
        self.graph[other] = []
        result = self.split("--guix-profile", PROFILE, "--release-tag", "t")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"per-machine item to publish: {other}", result.stderr)
        self.assertNotIn(f"per-machine item to publish: {PROFILE}\n", result.stderr)

    def test_a_profile_that_is_no_store_item_is_refused(self):
        for bad in ("/tmp/profile", "/gnu/store/short-profile", PROFILE + "/bin/guix"):
            result = self.split("--guix-profile", bad, "--release-tag", "t")
            self.assertNotEqual(result.returncode, 0, bad)
            self.assertIn("is not a store item", result.stderr)

    def test_a_profile_missing_from_the_store_is_refused(self):
        result = self.split("--guix-profile", item("7", "profile"), "--release-tag", "t")
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
