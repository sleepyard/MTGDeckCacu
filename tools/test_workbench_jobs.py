"""Deterministic regression coverage for limited gates, jobs and cached art."""
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deck_core
import deck_image
import deck_model
import deck_workbench as wb
import workbench_jobs
from test_deck_workbench import FakeTable, ServerFixture, cp, pool_card


def wait_job(registry, key):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = registry.get(key)
        if job["status"] != "running":
            return job
        threading.Event().wait(.01)
    raise AssertionError("Job did not finish")


class LimitedAuditTests(unittest.TestCase):
    def test_copies_above_four_and_large_sideboard_are_pool_based(self):
        deck = deck_model.parse_text("Deck\n6 Test Card\n35 Plains\nSideboard\n20 Test Card\n")
        result = wb.build_limited_audit(deck, [{"name": "Test Card", "count": 26}])
        self.assertTrue(result["ok"])
        self.assertEqual(result["rotation"]["status"], "not_applicable")
        result = wb.build_limited_audit(deck, [{"name": "Test Card", "count": 25}])
        self.assertFalse(result["ok"])
        self.assertIn("26", result["pool"]["violations"][0])

    def test_missing_pool_unknown_and_missing_card_failure(self):
        deck = deck_model.parse_text("Deck\n1 Test Card\n39 Plains\n")
        self.assertIsNone(wb.build_limited_audit(deck, [])["ok"])
        result = wb.build_limited_audit(deck, [{"name": "Other Card", "count": 1}])
        self.assertFalse(result["ok"])

    def test_unresolved_pool_is_not_silently_rejected_or_passed(self):
        deck = deck_model.parse_text("Deck\n1 Test Card\n39 Plains\n")
        result = wb.build_limited_audit(deck, [], [{"name": "Test Card", "qty": 1}])
        self.assertIsNone(result["ok"])
        self.assertEqual(result["pool"]["unknown"], ["Test Card"])

    def test_limited_count_failure_even_with_unknown_pool(self):
        result = wb.build_limited_audit(deck_model.parse_text("39 Plains"), [])
        self.assertFalse(result["ok"])
        self.assertEqual(result["validate"]["status"], "fail")

    def test_pool_duplicate_names_merge_quantities(self):
        cards, unresolved = wb.hydrate_pool([(1, "Test Card"), (2, "Test Card")],
                                           lambda name: pool_card(name, "W", 2))
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["count"], 3)
        self.assertEqual(unresolved, [])

    def test_reimport_pool_invalidates_previous_pool_audit(self):
        state = wb.WorkbenchState()
        state.import_text("1 Test Card\n39 Plains")
        state.import_pool("1 Test Card", fetch_card=lambda name: pool_card(name, "W", 2))
        self.assertTrue(state.audit("", True, False)[0]["ok"])
        state.import_pool("1 Other Card", fetch_card=lambda name: pool_card(name, "W", 2))
        self.assertIsNone(state.slot("audit"))
        self.assertFalse(state.audit("", True, False)[0]["ok"])

    def test_mdfc_pool_matching_and_duplicate_rows_aggregate(self):
        result = wb.build_limited_audit(deck_model.parse_text("2 Front\n38 Plains"),
                                       [{"name": "Front // Back", "count": 1}, {"name": "Front", "count": 1}])
        self.assertTrue(result["ok"])

    def test_limited_http_never_calls_constructed_tools(self):
        state = wb.WorkbenchState()
        state.import_pool("26 Test Card", fetch_card=lambda name: pool_card(name, "W", 2))
        state.import_text("6 Test Card\n35 Plains\nSideboard\n20 Test Card")
        with mock.patch.object(wb, "_run_tool", side_effect=AssertionError("No CLI")), ServerFixture(state) as fx:
            status, result = fx.post_obj("/api/audit", {"limited": True})
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])

    def test_pioneer_does_not_gate_standard_rotation(self):
        with mock.patch.object(wb, "_run_tool", return_value=cp(0, "PASS")) as run, ServerFixture() as fx:
            fx.post_json("/api/builds/import", "60 Plains")
            status, result = fx.post_obj("/api/audit", {"format": "pioneer", "limited": False})
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        self.assertEqual(result["rotation"]["status"], "not_applicable")
        self.assertEqual(run.call_count, 1)

    def test_limited_edits_conserve_pool_and_allow_more_than_four(self):
        state = wb.WorkbenchState()
        state.import_pool("7 Test Card", fetch_card=lambda name: pool_card(name, "W", 2))
        state.import_text("4 Test Card\nSideboard\n3 Test Card")
        state.deck_move("Test Card", "sideboard", "main", 3, limited=True)
        self.assertEqual(state.snapshot()["counts"]["main"], 7)
        with self.assertRaises(wb.DeckEditError):
            state.deck_add("Test Card", "main", 1, limited=True)
        state.deck_add("Plains", "main", 40, limited=True)

    def test_edit_invalidates_audit_cache(self):
        state = wb.WorkbenchState()
        state.import_text("40 Plains")
        state.audit("", True, False)
        state.deck_remove("Plains", "main", 1)
        self.assertIsNone(state.slot("audit"))

    def test_rating_coverage_preserves_missing_and_metadata(self):
        pool = [pool_card("Rated", "W", 2), pool_card("Unrated", "W", 2)]
        table = FakeTable([dict(pool[0], grade="B"), dict(pool[1], grade="")])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "FRA.json"
            path.write_text(json.dumps({"source": "community+llm", "generated": "2026-09-13"}), encoding="utf-8")
            with mock.patch.object(wb.mtga_draft_tool, "card_table_path", return_value=path):
                summary = wb.summarize_ratings(pool, table, "FRA")
        self.assertEqual(summary["covered"], 1)
        self.assertEqual(summary["missing"], ["Unrated"])
        self.assertEqual(summary["source"], "community+llm")

    def test_41_land_check_uses_41_not_40(self):
        pool = [pool_card("White", "W", 2, count=30, cost="{1}{W}")]
        built = wb.LS.build_limited_deck(pool, table=FakeTable(pool), deck_size=41)
        self.assertEqual(built.land_check, deck_core.land_check(sum(built.lands.values()), 41))


class JobTests(unittest.TestCase):
    def test_progress_single_job_and_private_image(self):
        registry = workbench_jobs.JobRegistry()
        entered, release = threading.Event(), threading.Event()

        def worker(progress, key):
            progress("Checking cards", 1, 3)
            entered.set()
            release.wait(2)
            return {"download_url": "/api/jobs/" + key + "/image", "_image": b"PNG"}

        key = registry.start("image", "deck-one", worker)["job_id"]
        self.assertTrue(entered.wait(2))
        job = registry.get(key)
        self.assertEqual((job["message"], job["current"], job["total"]), ("Checking cards", 1, 3))
        self.assertEqual(registry.start("image", "deck-one", worker)["job_id"], key)
        with self.assertRaises(ValueError):
            registry.start("image", "different-deck", worker)
        release.set()
        self.assertNotIn("_image", wait_job(registry, key)["result"])
        self.assertEqual(registry.image(key), b"PNG")

    def test_job_failure_and_expiry(self):
        now = [100.0]
        registry = workbench_jobs.JobRegistry(ttl=10, clock=lambda: now[0])

        def fail(*args):
            raise OSError("No output")

        key = registry.start("audit", "a", fail)["job_id"]
        job = wait_job(registry, key)
        self.assertEqual(job["status"], "error")
        self.assertEqual(job["error"]["message"], "No output")
        now[0] += 11
        self.assertIsNone(registry.get(key))

    def test_background_audit_frozen_deck_and_stale_result(self):
        state = wb.WorkbenchState()
        state.import_text("60 Plains")
        entered, release = threading.Event(), threading.Event()

        def run(argv):
            self.assertIn("60 Plains", Path(argv[5]).read_text(encoding="utf-8"))
            entered.set()
            release.wait(2)
            return cp(0, "PASS")

        with mock.patch.object(wb, "_run_tool", side_effect=run):
            key = state.start_audit("pioneer", False, False)["job_id"]
            self.assertTrue(entered.wait(2))
            self.assertIn("CLI", state.jobs.get(key)["message"])
            state.deck_remove("Plains", "main", 1)
            release.set()
            result = wait_job(state.jobs, key)
        self.assertTrue(result["result"]["stale"])
        self.assertIsNone(state.slot("audit"))

    def test_image_http_download_and_failure_without_zero_image(self):
        state = wb.WorkbenchState()
        state.import_text("40 Plains")

        def render(argv):
            Path(argv[argv.index("--out") + 1]).write_bytes(b"\x89PNG\r\nfixture")
            return cp(0)

        with mock.patch.object(workbench_jobs, "card_image", return_value=Path("cached.png")), \
                mock.patch.object(wb, "_run_tool", side_effect=render), ServerFixture(state) as fx:
            status, started = fx.post_obj("/api/export-image", {"title": "Limited"})
            self.assertEqual(status, 202)
            job = wait_job(state.jobs, started["job_id"])
            self.assertEqual(job["status"], "done")
            status, image = fx.get(job["result"]["download_url"])
            self.assertEqual(status, 200)
            self.assertTrue(image.startswith(b"\x89PNG"))
        with mock.patch.object(workbench_jobs, "card_image", return_value=None), \
                mock.patch.object(wb, "_run_tool", return_value=cp(3, "", "Pillow unavailable")):
            job = wait_job(state.jobs, state.start_image()["job_id"])
        self.assertEqual(job["status"], "error")
        self.assertIsNone(state.jobs.image(job["job_id"]))

    def test_cached_art_skips_network_and_endpoint_rejects_outside_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mtgch_Test_Card.webp"
            path.write_bytes(b"cached-image")
            with mock.patch.object(deck_image, "CACHE_DIR", tmp), \
                    mock.patch.object(deck_image, "mtgch_card_info", side_effect=AssertionError("No HTTP")):
                self.assertEqual(workbench_jobs.card_image("Test Card"), path)
                with ServerFixture() as fx:
                    fx.post_json("/api/builds/import", "40 Test Card")
                    status, image = fx.get("/api/card-image?name=Test%20Card")
                    self.assertEqual((status, image), (200, b"cached-image"))
                    self.assertEqual(fx.get("/api/card-image?name=Outside")[0], 404)


if __name__ == "__main__":
    unittest.main()
