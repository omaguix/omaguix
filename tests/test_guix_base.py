"""guix-base on small local repositories standing in for Guix and a fork."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/guix-base"
ENV = {**os.environ, "GIT_AUTHOR_NAME": "Upstream", "GIT_AUTHOR_EMAIL": "u@example.org",
       "GIT_COMMITTER_NAME": "Upstream", "GIT_COMMITTER_EMAIL": "u@example.org",
       "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env=ENV).stdout.strip()


class GuixBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        upstream = self.root / "upstream"
        git(self.root, "init", "--quiet", str(upstream))
        (upstream / "a.scm").write_text("old\n")
        git(upstream, "add", ".")
        git(upstream, "commit", "--quiet", "-m", "first")
        self.first = git(upstream, "rev-parse", "HEAD")
        (upstream / "a.scm").write_text("pin\n")
        git(upstream, "commit", "--quiet", "-am", "pin")
        self.pin = git(upstream, "rev-parse", "HEAD")
        self.upstream = upstream
        # The fork: the fix on top of the pin, and one on top of an older commit.
        fork = self.root / "fork"
        git(self.root, "clone", "--quiet", str(upstream), str(fork))
        (fork / "a.scm").write_text("pin\nfix\n")
        git(fork, "commit", "--quiet", "-am", "fix")
        self.fix = git(fork, "rev-parse", "HEAD")
        git(fork, "checkout", "--quiet", "-b", "old", self.first)
        (fork / "a.scm").write_text("old\nfix\n")
        git(fork, "commit", "--quiet", "-am", "fix on an older commit")
        self.old_fix = git(fork, "rev-parse", "HEAD")
        self.fork_url = (fork / ".git").as_uri()
        self.modules = self.root / "modules"
        (self.modules / "omaguix").mkdir(parents=True)
        (self.modules / "omaguix/guix-commit").write_text(self.pin + "\n")

    def repo(self, shallow):
        repo = self.root / ("shallow" if shallow else "full")
        git(self.root, "init", "--quiet", "--bare", str(repo))
        depth = ["--depth=1"] if shallow else []
        git(repo, "fetch", "--quiet", *depth, str(self.upstream), self.pin)
        return repo

    def fork(self, line):
        (self.modules / "omaguix/guix-fork").write_text(line + "\n")

    def run_script(self, repo):
        return subprocess.run([str(SCRIPT), str(repo), str(self.modules)],
                              capture_output=True, text=True)

    def test_without_a_fork_the_base_is_the_pin(self):
        result = self.run_script(self.repo(shallow=False))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), self.pin)

    def test_a_fork_commit_on_the_pin_is_the_base_in_full_and_shallow_repositories(self):
        self.fork(f"{self.fork_url} {self.fix}")
        for shallow in (False, True):
            with self.subTest(shallow=shallow):
                repo = self.repo(shallow)
                result = self.run_script(repo)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), self.fix)
                self.assertEqual(git(repo, "show", f"{self.fix}:a.scm"), "pin\nfix")
                self.assertEqual(git(repo, "rev-parse", "--is-shallow-repository"),
                                 "true" if shallow else "false")

    def test_a_fork_commit_not_on_the_pin_fails(self):
        self.fork(f"{self.fork_url} {self.old_fix}")
        result = self.run_script(self.repo(shallow=True))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("parents are not exactly", result.stderr)

    def test_a_fork_file_without_a_final_newline_is_read(self):
        (self.modules / "omaguix/guix-fork").write_text(f"{self.fork_url} {self.fix}")
        result = self.run_script(self.repo(shallow=False))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), self.fix)

    def test_a_malformed_fork_file_fails(self):
        for line in (self.fork_url, f"{self.fork_url} {self.fix} extra",
                     f"ssh://host/guix {self.fix}", f"{self.fork_url} {self.fix[:12]}",
                     f"{self.fork_url} {self.fix}\nsecond line"):
            with self.subTest(line=line):
                self.fork(line)
                result = self.run_script(self.repo(shallow=False))
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                shutil.rmtree(self.root / "full")


if __name__ == "__main__":
    unittest.main()
