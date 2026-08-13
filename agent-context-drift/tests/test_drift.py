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

import agent_drift
import claim_drift  # noqa: E402


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


class ClaimDrift(unittest.TestCase):
    """Claims rot without an address, so they need their own markup."""

    def _check(self, text, rel="CLAUDE.md", resolve=lambda v, b, r: "ok", **kw):
        owner = FIXTURE / rel
        return claim_drift.check(owner, text, FIXTURE, FIXTURE, resolve=resolve,
                                 owner_rel=rel, ignored=lambda a, b: False, **kw)

    def test_source_pointing_nowhere_is_a_finding(self):
        f, _ = self._check("Median reach 950 [source: gone/]",
                           resolve=lambda v, b, r: "broken")
        self.assertEqual([x["kind"] for x in f], ["broken_source"])

    def test_a_soft_verdict_does_not_excuse_a_missing_source(self):
        """The resolver softens unknown tree leaves to "descriptive"; a source
        must not inherit that mercy — it is an address, not a topic."""
        f, _ = self._check("Median 950 [source: tools/gone-away/]",
                           resolve=lambda v, b, r: "descriptive")
        self.assertEqual([x["kind"] for x in f], ["broken_source"])

    def test_a_live_source_silences_the_number(self):
        """A marked claim must not also be reported as unmarked."""
        f, c = self._check("Median reach 950 [source: tools/]")
        self.assertEqual(f, [])
        self.assertEqual(c["claims_unmarked"], 0)

    def test_russian_alias_is_accepted(self):
        _, c = self._check("Медиана 950 [источник: tools/]")
        self.assertEqual(c["sources"], 1)

    def test_bare_measurement_is_flagged_but_a_count_is_not(self):
        f, _ = self._check("Reach was 33 873 last month.")
        self.assertEqual([x["kind"] for x in f], ["unmarked_claim"])
        self.assertEqual(self._check("The deck has 8 slides.")[0], [])

    def test_drafts_and_T0_are_left_alone(self):
        """A draft is where you are allowed to be wrong out loud."""
        _, c = self._check("Stake level: T0\n\nReach was 33 873.")
        self.assertEqual(c["claims_unmarked"], 0)

    def test_code_fences_and_tables_are_not_claims(self):
        self.assertEqual(self._check("```\nreach = 33 873\n```")[0], [])
        self.assertEqual(self._check("| reach | 33 873 |")[0], [])

    def test_stake_level_example_in_prose_is_not_a_declaration(self):
        """The root file documents the syntax; that must not declare it T2."""
        body = "\n".join(["filler"] * 25 + ["Write `Stake level: T2` in the header."])
        self.assertIsNone(claim_drift._declared(body))
        self.assertEqual(claim_drift._declared("# Title\n> Stake level: T2\n"), "T2")

    def test_stale_unknown_needs_git_dates_and_stays_quiet_without_them(self):
        f, c = self._check("Goodhart was British statistics [?]")
        self.assertEqual(c["unknowns"], 1)
        self.assertEqual([x for x in f if x["kind"] == "stale_unknown"], [])

    def test_rate_is_a_share_so_detail_is_not_punished(self):
        few = claim_drift.rate({"claims_marked": 1, "claims_unmarked": 1})
        many = claim_drift.rate({"claims_marked": 50, "claims_unmarked": 50})
        self.assertEqual(few, many)


if __name__ == "__main__":
    unittest.main()
