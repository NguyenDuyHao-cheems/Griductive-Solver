"""Unit tests for Direct Semantic Evaluator (Task 4 / Section 4.2).

Verifies evaluate_clue and evaluate_puzzle against all 6 core templates
and 2 team extensions (PARITY, COMPARE_COUNT), plus ground truth validation
on sample_3x3.json and sample_4x4.json.
"""

from pathlib import Path
import sys
import unittest

SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from game_engine import GameEngine, evaluate_clue, evaluate_puzzle
from models import Clue, Region, Status


class TestSemanticEvaluator(unittest.TestCase):
    """Test suite for direct semantic evaluation without CNF or SAT solver."""

    def test_fact_evaluation(self) -> None:
        clue_crim = Clue(clue_id="c1", type="FACT", target="A1", status="CRIMINAL")
        clue_inno = Clue(clue_id="c2", type="FACT", target="B2", status="INNOCENT")

        # Matching assignments
        self.assertTrue(evaluate_clue(clue_crim, {"A1": "CRIMINAL"}))
        self.assertTrue(evaluate_clue(clue_inno, {"B2": "INNOCENT"}))

        # Mismatched assignments
        self.assertFalse(evaluate_clue(clue_crim, {"A1": "INNOCENT"}))
        self.assertFalse(evaluate_clue(clue_inno, {"B2": "CRIMINAL"}))

    def test_same_evaluation(self) -> None:
        clue = Clue(clue_id="c_same", type="SAME", a="A1", b="C3")

        # Both CRIMINAL -> True
        self.assertTrue(evaluate_clue(clue, {"A1": "CRIMINAL", "C3": "CRIMINAL"}))
        # Both INNOCENT -> True
        self.assertTrue(evaluate_clue(clue, {"A1": "INNOCENT", "C3": "INNOCENT"}))
        # Disagree -> False
        self.assertFalse(evaluate_clue(clue, {"A1": "CRIMINAL", "C3": "INNOCENT"}))
        self.assertFalse(evaluate_clue(clue, {"A1": "INNOCENT", "C3": "CRIMINAL"}))

    def test_different_evaluation(self) -> None:
        clue = Clue(clue_id="c_diff", type="DIFFERENT", a="A1", b="C3")

        # Disagree -> True
        self.assertTrue(evaluate_clue(clue, {"A1": "CRIMINAL", "C3": "INNOCENT"}))
        self.assertTrue(evaluate_clue(clue, {"A1": "INNOCENT", "C3": "CRIMINAL"}))
        # Both CRIMINAL -> False
        self.assertFalse(evaluate_clue(clue, {"A1": "CRIMINAL", "C3": "CRIMINAL"}))
        # Both INNOCENT -> False
        self.assertFalse(evaluate_clue(clue, {"A1": "INNOCENT", "C3": "INNOCENT"}))

    def test_counting_clues(self) -> None:
        # EXACTLY 2 in ROW 0 (A1, B1, C1 in 3x3)
        region_row0 = Region(kind="ROW", target=0)
        clue_exact = Clue(clue_id="c_exact", type="EXACTLY", region=region_row0, k=2)

        assign_2_crim: dict[str, Status] = {"A1": "CRIMINAL", "B1": "CRIMINAL", "C1": "INNOCENT"}
        assign_1_crim: dict[str, Status] = {"A1": "CRIMINAL", "B1": "INNOCENT", "C1": "INNOCENT"}
        assign_3_crim: dict[str, Status] = {"A1": "CRIMINAL", "B1": "CRIMINAL", "C1": "CRIMINAL"}
        assign_0_crim: dict[str, Status] = {"A1": "INNOCENT", "B1": "INNOCENT", "C1": "INNOCENT"}

        self.assertTrue(evaluate_clue(clue_exact, assign_2_crim, size=3))
        self.assertFalse(evaluate_clue(clue_exact, assign_1_crim, size=3))
        self.assertFalse(evaluate_clue(clue_exact, assign_3_crim, size=3))
        self.assertFalse(evaluate_clue(clue_exact, assign_0_crim, size=3))

        # AT_LEAST 2 in ROW 0
        clue_at_least = Clue(clue_id="c_at_least", type="AT_LEAST", region=region_row0, k=2)
        self.assertTrue(evaluate_clue(clue_at_least, assign_2_crim, size=3))
        self.assertTrue(evaluate_clue(clue_at_least, assign_3_crim, size=3))
        self.assertFalse(evaluate_clue(clue_at_least, assign_1_crim, size=3))
        self.assertFalse(evaluate_clue(clue_at_least, assign_0_crim, size=3))

        # AT_MOST 1 in ROW 0
        clue_at_most = Clue(clue_id="c_at_most", type="AT_MOST", region=region_row0, k=1)
        self.assertTrue(evaluate_clue(clue_at_most, assign_0_crim, size=3))
        self.assertTrue(evaluate_clue(clue_at_most, assign_1_crim, size=3))
        self.assertFalse(evaluate_clue(clue_at_most, assign_2_crim, size=3))
        self.assertFalse(evaluate_clue(clue_at_most, assign_3_crim, size=3))

    def test_region_types_neighbors_and_explicit(self) -> None:
        # NEIGHBORS of B2 in 3x3: all 8 other cells
        region_neigh = Region(kind="NEIGHBORS", target="B2")
        clue_neigh = Clue(clue_id="c_nb", type="EXACTLY", region=region_neigh, k=1)

        # 3x3 grid with only A1 being CRIMINAL
        all_cells = [f"{c}{r}" for r in range(1, 4) for c in ("A", "B", "C")]
        assign = {c: "INNOCENT" for c in all_cells}
        assign["A1"] = "CRIMINAL"

        self.assertTrue(evaluate_clue(clue_neigh, assign))

        # Add second criminal in neighbors -> False
        assign["C3"] = "CRIMINAL"
        self.assertFalse(evaluate_clue(clue_neigh, assign))

        # EXPLICIT region
        region_exp = Region(kind="EXPLICIT", cells=("A1", "B2", "C3"))
        clue_exp = Clue(clue_id="c_exp", type="AT_LEAST", region=region_exp, k=2)
        self.assertTrue(evaluate_clue(clue_exp, assign))

    def test_parity_extension(self) -> None:
        region_col = Region(kind="COL", target="B")
        clue_even = Clue(clue_id="p_even", type="PARITY", region=region_col, parity="EVEN")
        clue_odd = Clue(clue_id="p_odd", type="PARITY", region=region_col, parity="ODD")

        # 0 criminals in Col B (0 is EVEN)
        assign_0: dict[str, Status] = {"B1": "INNOCENT", "B2": "INNOCENT", "B3": "INNOCENT"}
        self.assertTrue(evaluate_clue(clue_even, assign_0, size=3))
        self.assertFalse(evaluate_clue(clue_odd, assign_0, size=3))

        # 1 criminal in Col B (1 is ODD)
        assign_1: dict[str, Status] = {"B1": "CRIMINAL", "B2": "INNOCENT", "B3": "INNOCENT"}
        self.assertFalse(evaluate_clue(clue_even, assign_1, size=3))
        self.assertTrue(evaluate_clue(clue_odd, assign_1, size=3))

        # 2 criminals in Col B (2 is EVEN)
        assign_2: dict[str, Status] = {"B1": "CRIMINAL", "B2": "CRIMINAL", "B3": "INNOCENT"}
        self.assertTrue(evaluate_clue(clue_even, assign_2, size=3))
        self.assertFalse(evaluate_clue(clue_odd, assign_2, size=3))

        # 3 criminals in Col B (3 is ODD)
        assign_3: dict[str, Status] = {"B1": "CRIMINAL", "B2": "CRIMINAL", "B3": "CRIMINAL"}
        self.assertFalse(evaluate_clue(clue_even, assign_3, size=3))
        self.assertTrue(evaluate_clue(clue_odd, assign_3, size=3))

    def test_compare_count_extension(self) -> None:
        r1 = Region(kind="ROW", target=0)  # A1, B1, C1
        r2 = Region(kind="ROW", target=1)  # A2, B2, C2

        clue_gt = Clue(clue_id="cmp_gt", type="COMPARE_COUNT", r1=r1, op="GT", r2=r2)
        clue_lt = Clue(clue_id="cmp_lt", type="COMPARE_COUNT", r1=r1, op="LT", r2=r2)
        clue_eq = Clue(clue_id="cmp_eq", type="COMPARE_COUNT", r1=r1, op="EQ", r2=r2)

        # r1 has 2 criminals, r2 has 1 criminal
        assign_r1_more: dict[str, Status] = {
            "A1": "CRIMINAL", "B1": "CRIMINAL", "C1": "INNOCENT",
            "A2": "CRIMINAL", "B2": "INNOCENT", "C2": "INNOCENT",
        }
        self.assertTrue(evaluate_clue(clue_gt, assign_r1_more, size=3))
        self.assertFalse(evaluate_clue(clue_lt, assign_r1_more, size=3))
        self.assertFalse(evaluate_clue(clue_eq, assign_r1_more, size=3))

        # r1 has 1 criminal, r2 has 2 criminals
        assign_r2_more: dict[str, Status] = {
            "A1": "CRIMINAL", "B1": "INNOCENT", "C1": "INNOCENT",
            "A2": "CRIMINAL", "B2": "CRIMINAL", "C2": "INNOCENT",
        }
        self.assertFalse(evaluate_clue(clue_gt, assign_r2_more, size=3))
        self.assertTrue(evaluate_clue(clue_lt, assign_r2_more, size=3))
        self.assertFalse(evaluate_clue(clue_eq, assign_r2_more, size=3))

        # r1 has 1 criminal, r2 has 1 criminal
        assign_equal: dict[str, Status] = {
            "A1": "CRIMINAL", "B1": "INNOCENT", "C1": "INNOCENT",
            "A2": "CRIMINAL", "B2": "INNOCENT", "C2": "INNOCENT",
        }
        self.assertFalse(evaluate_clue(clue_gt, assign_equal, size=3))
        self.assertFalse(evaluate_clue(clue_lt, assign_equal, size=3))
        self.assertTrue(evaluate_clue(clue_eq, assign_equal, size=3))

    def test_evaluate_puzzle_with_sample_puzzles(self) -> None:
        # 1. sample_3x3.json
        engine_3x3 = GameEngine(SRC_DIR / "puzzles" / "sample_3x3.json")
        solution_3x3 = engine_3x3.get_solution_for_testing()

        # Hidden ground truth satisfies 100% of clues
        self.assertTrue(evaluate_puzzle(engine_3x3._puzzle, solution_3x3))  # type: ignore

        # Flipping any single cell violates at least one clue
        for coord in solution_3x3:
            flipped = dict(solution_3x3)
            flipped[coord] = "INNOCENT" if solution_3x3[coord] == "CRIMINAL" else "CRIMINAL"
            self.assertFalse(
                evaluate_puzzle(engine_3x3._puzzle, flipped),  # type: ignore
                f"Flipping {coord} should violate at least one clue in 3x3 puzzle",
            )

        # 2. sample_4x4.json
        engine_4x4 = GameEngine(SRC_DIR / "puzzles" / "sample_4x4.json")
        solution_4x4 = engine_4x4.get_solution_for_testing()
        self.assertTrue(evaluate_puzzle(engine_4x4._puzzle, solution_4x4))  # type: ignore

        # Flipping a cell in 4x4
        flipped_4x4 = dict(solution_4x4)
        flipped_4x4["A1"] = "INNOCENT" if solution_4x4["A1"] == "CRIMINAL" else "CRIMINAL"
        self.assertFalse(evaluate_puzzle(engine_4x4._puzzle, flipped_4x4))  # type: ignore

    def test_error_handling(self) -> None:
        # Missing cell in assignment
        clue = Clue(clue_id="c_err", type="FACT", target="C3", status="CRIMINAL")
        with self.assertRaises(KeyError):
            evaluate_clue(clue, {"A1": "CRIMINAL"})

        # Missing required field
        malformed = Clue(clue_id="c_bad", type="FACT", target=None, status="CRIMINAL")
        with self.assertRaises(ValueError):
            evaluate_clue(malformed, {"A1": "CRIMINAL"})


if __name__ == "__main__":
    unittest.main()
