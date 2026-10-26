"""Verify the chapter's arithmetic and consequential evaluation failures."""
import copy
import csv
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from evaluate_forecasts import HERE, evaluate, metrics


class ForecastEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        with (HERE / "forecasts.csv").open(newline="", encoding="utf-8") as stream:
            self.rows = list(csv.DictReader(stream))

    def write_rows(self, rows):
        path = self.work / "changed.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=self.rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        return path

    def compare(self, path=None):
        return evaluate(
            path or HERE / "forecasts.csv",
            HERE / "expected_population.csv",
            HERE / "policy.json",
        )

    def test_hand_calculated_metrics_and_segments(self):
        report = self.compare()
        self.assertEqual(report["baseline"]["mae"], 12.5)
        self.assertEqual(report["candidate"]["mae"], 5)
        self.assertAlmostEqual(report["candidate"]["wape_percent"], 100 * 40 / 850)
        self.assertEqual(report["candidate"]["bias_percent"], 0)
        self.assertEqual(report["mae_improvement_fraction"], 0.6)
        self.assertEqual(report["segments"]["North"]["candidate"]["mae"], 4)
        self.assertEqual(report["segments"]["South"]["candidate"]["mae"], 6)
        self.assertEqual(report["offline_gates"], "pass")
        self.assertEqual(report["production_approval"], "not_assessed")

    def test_late_features_rejected_without_new_report(self):
        self.rows[0]["features_available_at"] = "2026-01-05T04:31:00+07:00"
        path = self.write_rows(self.rows)
        output = self.work / "invalid_report.json"
        result = subprocess.run(
            [sys.executable, str(HERE / "evaluate_forecasts.py"),
             "--data", str(path), "--output", str(output)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("feature available after cutoff", result.stderr)
        self.assertFalse(output.exists())

    def test_duplicate_and_missing_keys_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate prediction"):
            self.compare(self.write_rows(self.rows + [copy.copy(self.rows[0])]))
        with self.assertRaisesRegex(ValueError, "missing expected"):
            self.compare(self.write_rows(self.rows[:-1]))

    def test_nonfinite_and_negative_units_rejected(self):
        for invalid in ("nan", "inf", "-1"):
            with self.subTest(invalid=invalid):
                changed = copy.deepcopy(self.rows)
                changed[0]["candidate_units"] = invalid
                with self.assertRaisesRegex(ValueError, "finite and nonnegative"):
                    self.compare(self.write_rows(changed))

    def test_timezone_and_forecast_boundary_rejected(self):
        changed = copy.deepcopy(self.rows)
        changed[0]["features_available_at"] = "2026-01-05T04:20:00"
        with self.assertRaisesRegex(ValueError, "time zone"):
            self.compare(self.write_rows(changed))
        changed = copy.deepcopy(self.rows)
        changed[0]["input_cutoff"] = "2026-01-06T00:00:00+07:00"
        with self.assertRaisesRegex(ValueError, "precede target day"):
            self.compare(self.write_rows(changed))

    def test_segment_regression_fails_despite_overall_improvement(self):
        changed = copy.deepcopy(self.rows)
        for row in changed:
            actual = float(row["actual_units"])
            row["candidate_units"] = str(actual + 11 if row["segment"] == "North" else actual)
        report = self.compare(self.write_rows(changed))
        self.assertGreater(report["mae_improvement_fraction"], 0.1)
        self.assertFalse(report["segments"]["North"]["no_mae_regression"])
        self.assertEqual(report["offline_gates"], "fail")

    def test_zero_demand_metrics_are_explicitly_undefined(self):
        result = metrics([{"actual_units": 0, "candidate_units": 5}], "candidate_units")
        self.assertEqual(result["mae"], 5)
        self.assertIsNone(result["wape_percent"])
        self.assertIsNone(result["bias_percent"])

    def test_existing_report_is_not_overwritten(self):
        output = self.work / "existing.json"
        output.write_text("existing evidence", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(HERE / "evaluate_forecasts.py"), "--output", str(output)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(output.read_text(encoding="utf-8"), "existing evidence")

    def test_changed_data_has_changed_hash(self):
        original = self.compare()
        changed = copy.deepcopy(self.rows)
        changed[0]["candidate_units"] = "97"
        updated = self.compare(self.write_rows(changed))
        self.assertNotEqual(original["sha256"]["data"], updated["sha256"]["data"])
        self.assertEqual(original["sha256"]["policy"], updated["sha256"]["policy"])


if __name__ == "__main__":
    unittest.main()
