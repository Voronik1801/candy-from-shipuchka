#!/usr/bin/env python3
"""Behaviour the detector must keep.

Most of these tests exist because the naive version got them wrong. A path
checker written in an evening reports every template, every repo-rooted path
and every SQL keyword as a broken link — and a noisy checker gets switched off.
Each case below is one of those false positives, pinned so it stays fixed.

    python3 -m unittest discover tests
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "sample"
sys.path.insert(0, str(ROOT))

import agent_drift  # noqa: E402


def run_fixture():
    out = subprocess.run(
        [sys.executable, str(ROOT / "agent_drift.py"), "--root", str(FIXTURE)],
        capture_output=True, text=True, check=True)
    return json.loads(out.stdout)["files"][0]


class DetectorBehaviour(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = run_fixture()
        cls.values = {f["kind"]: {x["value"] for x in cls.report["findings"]
                                  if x["kind"] == f["kind"]}
                      for f in cls.report["findings"]}

    def kind(self, name):
        return self.values.get(name, set())

    # ── true positives: the point of the tool ──

    def test_missing_file_is_broken(self):
        self.assertIn("docs/runbook-2024.md", self.kind("broken_path"))

    def test_missing_directory_is_broken(self):
        self.assertIn("config/deploy.yaml", self.kind("broken_path"))

    def test_live_directory_absent_from_docs_is_reported(self):
        self.assertIn("scripts/", self.kind("undocumented_dir"))

    # ── false positives that must never come back ──

    def test_template_with_live_matches_is_not_broken(self):
        """`notes/YYYY-MM-DD_slug.md` has real files behind it."""
        for kind in ("broken_path", "template_unused"):
            self.assertNotIn("notes/YYYY-MM-DD_slug.md", self.kind(kind))

    def test_repo_rooted_path_is_ambiguous_not_broken(self):
        """`sample/docs/architecture.md` resolves — just written oddly."""
        self.assertNotIn("sample/docs/architecture.md", self.kind("broken_path"))
        self.assertIn("sample/docs/architecture.md", self.kind("ambiguous_ref"))

    def test_sql_keywords_are_not_paths(self):
        for word in ("CREATE", "DROP/TRUNCATE", "ALTER TABLE"):
            self.assertNotIn(word, self.kind("broken_path"))

    def test_urls_are_not_paths(self):
        for url in ("github.com/example/sample", "https://example.com/handbook"):
            self.assertNotIn(url, self.kind("broken_path"))

    def test_hyphenated_words_are_not_paths(self):
        for word in ("fast-refresh", "manual-reload"):
            self.assertNotIn(word, self.kind("broken_path"))

    def test_shell_example_is_not_a_path(self):
        self.assertNotIn("python3 src/main.py --verbose", self.kind("broken_path"))

    def test_tree_entries_resolve_without_the_tree_root(self):
        """A stack-parsed tree yields `src/api/routes.py`, not `sample/src/...`."""
        self.assertNotIn("src/api/routes.py", self.kind("broken_path"))
        self.assertNotIn("src/main.py", self.kind("broken_path"))

    def test_vendored_and_empty_dirs_are_not_demanded(self):
        undoc = self.kind("undocumented_dir")
        self.assertNotIn("vendor/", undoc)
        self.assertNotIn("empty-dir/", undoc)

    # ── scoring ──

    def test_exactly_two_broken_paths(self):
        """Guards against a filter change quietly widening the net."""
        self.assertEqual(self.report["counts"]["broken"], 2,
                         f"unexpected: {self.kind('broken_path')}")

    def test_drift_is_a_number_in_range(self):
        self.assertGreater(self.report["drift"], 0)
        self.assertLessEqual(self.report["drift"], 100)


class UnitPieces(unittest.TestCase):
    def test_template_to_glob_expands_date_and_word_placeholders(self):
        self.assertEqual(agent_drift.template_to_glob("notes/YYYY-MM-DD_slug.md"),
                         "notes/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_*.md")

    def test_underscore_is_a_separator_not_a_word_char(self):
        """`_slug` must expand; that lookbehind bug made every date template dead."""
        self.assertIn("*", agent_drift.template_to_glob("a/YYYY_slug.md"))

    def test_tree_parser_drops_the_root_line(self):
        block = [(1, "sample/"), (2, "├── src/"), (3, "│   └── main.py")]
        got = [p for p, _, _ in agent_drift.parse_tree_block(block)]
        self.assertEqual(got, ["src", "src/main.py"])

    def test_frozen_project_cannot_be_stale(self):
        counts = {"verified": 10, "broken": 5, "ambiguous": 0,
                  "templates": 1, "template_unused": 0}
        drift, status = agent_drift.score(counts, [], 1, lag=200, churn=0)
        self.assertIn(status, ("fresh", "drifting"))

    def test_absolute_count_of_broken_paths_matters(self):
        """Six dead paths among fifty live ones is still bad."""
        big = {"verified": 50, "broken": 6, "ambiguous": 0,
               "templates": 1, "template_unused": 0}
        drift, _ = agent_drift.score(big, [], 1, lag=0, churn=5)
        self.assertGreater(drift, 30)


if __name__ == "__main__":
    unittest.main()
