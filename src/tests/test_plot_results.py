"""Unit tests for Khoa's benchmark plotting & summary script (Section 4.5)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from experiments.plot_results import (
    build_markdown_summary,
    generate_report_artifacts,
    load_benchmark_csv,
    main as plot_main,
    summarize_by_size,
)

HAS_MATPLOTLIB = importlib.util.find_spec("matplotlib") is not None


SAMPLE_CSV = """\
puzzle_id,size,status,num_primary_vars,num_aux_vars,num_clauses,sat_calls,decisions,propagations,backtracks,deduction_steps,reveal_waves,runtime_ms,notes
grid_3x3_01,3,SOLVED,9,18,54,18,4,42,1,7,4,3.5,
grid_3x3_02,3,SOLVED,9,20,60,20,6,50,2,7,3,4.5,
grid_4x4_01,4,SOLVED,16,45,140,42,18,190,5,14,6,18.2,
grid_4x4_02,4,UNKNOWN,16,40,128,36,15,150,4,6,3,12.0,Ambiguous state reached
grid_5x5_01,5,TIMEOUT,25,110,410,120,250,1800,90,9,4,10000.0,Exceeded 10s limit
"""


class TestPlotResults(unittest.TestCase):
    def test_load_and_summarize_preserves_failures_and_timeouts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "benchmark_results.csv"
            csv_path.write_text(SAMPLE_CSV, encoding="utf-8")

            rows = load_benchmark_csv(csv_path)
            self.assertEqual(len(rows), 5)
            self.assertEqual([r.outcome_bucket for r in rows], ["SOLVED", "SOLVED", "SOLVED", "FAILED", "TIMEOUT"])

            summary = summarize_by_size(rows)
            by_size = {item["size"]: item for item in summary}

            # 3x3: 2 solved, avg runtime = (3.5 + 4.5)/2 = 4.0
            self.assertEqual(by_size[3]["solved"], 2)
            self.assertEqual(by_size[3]["timeout"], 0)
            self.assertEqual(by_size[3]["failed"], 0)
            self.assertAlmostEqual(by_size[3]["avg_runtime_ms"], 4.0)

            # 4x4: 1 solved, 1 failed; average must exclude the UNKNOWN/FAILED row (18.2, not 15.1)
            self.assertEqual(by_size[4]["total"], 2)
            self.assertEqual(by_size[4]["solved"], 1)
            self.assertEqual(by_size[4]["failed"], 1)
            self.assertAlmostEqual(by_size[4]["avg_runtime_ms"], 18.2)

            # 5x5: 0 solved, 1 timeout; success mean must be None (never counted as success)
            self.assertEqual(by_size[5]["total"], 1)
            self.assertEqual(by_size[5]["solved"], 0)
            self.assertEqual(by_size[5]["timeout"], 1)
            self.assertIsNone(by_size[5]["avg_runtime_ms"])

            md = build_markdown_summary(rows)
            self.assertIn("grid_5x5_01", md)
            self.assertIn("TIMEOUT", md)
            self.assertIn("UNKNOWN", md)
            self.assertIn("Failure & Timeout Cases", md)

    @unittest.skipUnless(HAS_MATPLOTLIB, "matplotlib is not installed in this environment")
    def test_generate_charts_and_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            csv_path = tmp_dir / "benchmark_results.csv"
            out_dir = tmp_dir / "assets"
            csv_path.write_text(SAMPLE_CSV, encoding="utf-8")

            summary_path, chart_paths = generate_report_artifacts(csv_path, out_dir)
            self.assertTrue(summary_path.is_file())
            self.assertEqual(len(chart_paths), 4)
            for chart in chart_paths:
                self.assertTrue(chart.is_file())
                self.assertGreater(chart.stat().st_size, 1000)

            rc = plot_main(["--input", str(csv_path), "--output", str(out_dir)])
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
