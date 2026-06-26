import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "kb-lint-check.sh"


class KbLintCheckTests(unittest.TestCase):
    def to_bash_path(self, path: Path) -> str:
        text = str(path)
        if len(text) > 1 and text[1] == ":":
            return "/" + text[0].lower() + text[2:].replace("\\", "/")
        return text.replace("\\", "/")

    def run_lint(self, vault: Path) -> subprocess.CompletedProcess:
        bash = shutil.which("bash")
        if bash is None:
            self.fail("bash not found in PATH")
        return subprocess.run(
            [bash, self.to_bash_path(SCRIPT), self.to_bash_path(vault)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_clean_vault_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            wiki = vault / "wiki"
            wiki.mkdir(parents=True)
            (wiki / "index.md").write_text(
                "---\ntitle: Index\nsource: local\ncreated: 2026-01-01\ndomain: wiki\n---\n"
                "- [Topic](../../wiki/Topic.md)\n- [Related](../../wiki/Related.md)\n",
                encoding="utf-8",
            )
            (wiki / "Topic.md").write_text(
                "---\ntitle: Topic\nsource: local\ncreated: 2026-01-01\ndomain: wiki\n---\n"
                "# Topic\nSee [Related](../../wiki/Related.md).\n",
                encoding="utf-8",
            )
            (wiki / "Related.md").write_text(
                "---\ntitle: Related\nsource: local\ncreated: 2026-01-01\ndomain: wiki\n---\n"
                "# Related\nSee [Topic](../../wiki/Topic.md).\n",
                encoding="utf-8",
            )
            (wiki / "log.md").write_text("", encoding="utf-8")

            result = self.run_lint(vault)

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("[OK] no broken wiki/relative links detected", result.stdout)
            self.assertIn("[OK] no missing raw sources detected", result.stdout)
            self.assertNotIn("[ERR] broken links detected", result.stdout)
            self.assertNotIn("[ERR] missing raw sources detected", result.stdout)

    def test_frontmatter_check_reports_missing_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            wiki = vault / "wiki"
            wiki.mkdir(parents=True)
            (wiki / "index.md").write_text(
                "---\ntitle: Index\nsource: local\ncreated: 2026-01-01\ndomain: wiki\n---\n",
                encoding="utf-8",
            )
            (wiki / "Topic.md").write_text("# Topic\n", encoding="utf-8")
            (wiki / "log.md").write_text("", encoding="utf-8")

            result = self.run_lint(vault)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("frontmatter missing fields detected", result.stdout)

    def test_tag_duplicate_check_detects_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            wiki = vault / "wiki"
            wiki.mkdir(parents=True)
            (wiki / "index.md").write_text(
                "---\ntitle: Index\nsource: local\ncreated: 2026-01-01\ndomain: wiki\ntags: [ai]\n---\n",
                encoding="utf-8",
            )
            (wiki / "Topic.md").write_text(
                "---\ntitle: Topic\nsource: local\ncreated: 2026-01-01\ndomain: wiki\ntags: [ai]\n---\n"
                "# Topic\n",
                encoding="utf-8",
            )
            (wiki / "Related.md").write_text(
                "---\ntitle: Related\nsource: local\ncreated: 2026-01-01\ndomain: wiki\ntags: [ai]\n---\n"
                "# Related\n",
                encoding="utf-8",
            )
            (wiki / "log.md").write_text("", encoding="utf-8")

            result = self.run_lint(vault)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("excessive tag duplicates detected", result.stdout)

    def test_missing_vault_fails(self):
        result = self.run_lint(Path("/missing/vault"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Vault not found", result.stdout)

    def test_broken_link_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            wiki = vault / "wiki"
            wiki.mkdir(parents=True)
            (wiki / "index.md").write_text("- [Topic](wiki/Topic.md)\n", encoding="utf-8")
            (wiki / "Topic.md").write_text("# Topic\n[Bad](wiki/Missing.md)\n", encoding="utf-8")
            (wiki / "log.md").write_text("", encoding="utf-8")

            result = self.run_lint(vault)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("broken links detected", result.stdout)


if __name__ == "__main__":
    unittest.main()
