"""guix-patched-commit on a small local repository standing in for Guix."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/guix-patched-commit"

PATCH = """diff --git a/guix/scripts/system.scm b/guix/scripts/system.scm
--- a/guix/scripts/system.scm
+++ b/guix/scripts/system.scm
@@ -1,2 +1,3 @@
 (define (reconfigure)
-  (check-forward-update))
+  (when validate
+    (check-forward-update)))
"""


def git(repo, *args, env=None):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env=env).stdout.strip()


class GuixPatchedCommit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        source = self.root / "source"
        (source / "guix/scripts").mkdir(parents=True)
        (source / "guix/scripts/system.scm").write_text("(define (reconfigure)\n  (check-forward-update))\n")
        git(self.root, "init", "--quiet", str(source))
        git(source, "add", ".")
        env = {**os.environ, "GIT_AUTHOR_NAME": "Upstream", "GIT_AUTHOR_EMAIL": "u@example.org",
               "GIT_COMMITTER_NAME": "Upstream", "GIT_COMMITTER_EMAIL": "u@example.org",
               "GIT_AUTHOR_DATE": "2026-09-04T09:33:22+03:00",
               "GIT_COMMITTER_DATE": "2026-09-04T09:33:22+03:00"}
        git(source, "commit", "--quiet", "-m", "upstream", env=env)
        self.pin = git(source, "rev-parse", "HEAD")
        self.source = source
        self.patch = self.root / "guix-skip-forward-check.patch"
        self.patch.write_text(PATCH)

    def clone(self, name):
        repo = self.root / name
        git(self.root, "init", "--quiet", "--bare", str(repo))
        git(repo, "fetch", "--quiet", str(self.source), self.pin)
        return repo

    def run_script(self, repo, patch=None, env=None):
        return subprocess.run([str(SCRIPT), str(repo), self.pin, str(patch or self.patch)],
                              capture_output=True, text=True, env=env)

    def test_patched_commit_is_g_plus_the_patch(self):
        repo = self.clone("a")
        result = self.run_script(repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        patched = result.stdout.strip()
        self.assertEqual(git(repo, "rev-parse", patched + "^"), self.pin)
        self.assertIn("(when validate", git(repo, "show", patched + ":guix/scripts/system.scm"))
        self.assertEqual(git(repo, "log", "-1", "--format=%cI", patched), "2026-09-04T09:33:22+03:00")

    def test_every_runner_makes_the_same_commit_whatever_its_git_configuration(self):
        first = self.run_script(self.clone("a")).stdout.strip()
        config = self.root / "gitconfig"
        config.write_text("[i18n]\n\tcommitEncoding = ISO-8859-1\n[user]\n\tname = Someone\n")
        env = {**os.environ, "GIT_CONFIG_GLOBAL": str(config), "TZ": "America/Los_Angeles"}
        second = self.run_script(self.clone("b"), env=env)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(second.stdout.strip(), first)

    def test_a_patch_that_does_not_apply_fails(self):
        bad = self.root / "bad.patch"
        bad.write_text(PATCH.replace("(check-forward-update))\n+", "(something-else))\n+"))
        result = self.run_script(self.clone("a"), patch=bad)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_a_missing_pin_fails(self):
        repo = self.root / "empty"
        git(self.root, "init", "--quiet", "--bare", str(repo))
        result = self.run_script(repo)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
