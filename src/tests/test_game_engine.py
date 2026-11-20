"""Unit tests for GameEngine (Task 3 / Section 4.1)."""

import json
from pathlib import Path
import sys
import unittest

# Ensure src is on sys.path
SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from game_engine import GameEngine, LogicAgentProtocol
from models import EntailmentStatus, PublicState, Puzzle, Status


class MockLogicAgent:
    """Mock Logic Agent with controllable responses for testing GameEngine."""

    def __init__(self, canned_responses: dict[str, EntailmentStatus] | None = None) -> None:
        self.canned_responses: dict[str, EntailmentStatus] = canned_responses or {}
        self.call_history: list[tuple[PublicState, str]] = []

    def classify_cell(self, public_state: PublicState, coord: str) -> EntailmentStatus:
        self.call_history.append((public_state, coord))
        return self.canned_responses.get(coord, "UNKNOWN")


class TestGameEngine(unittest.TestCase):
    """Comprehensive tests for GameEngine."""

    def setUp(self) -> None:
        self.sample_path = SRC_DIR / "puzzles" / "sample_3x3.json"
        self.assertTrue(self.sample_path.is_file(), f"Sample puzzle missing: {self.sample_path}")

    def test_load_puzzle_and_initial_state(self) -> None:
        engine = GameEngine(self.sample_path)
        self.assertEqual(engine.puzzle_id, "sample_3x3")
        self.assertEqual(engine.size, 3)
        self.assertEqual(engine.total_cells, 9)
        self.assertEqual(engine.revealed_count, 2)
        self.assertEqual(engine.unsolved_count, 7)
        self.assertFalse(engine.is_solved())

        pub = engine.get_public_state()
        self.assertEqual(pub.size, 3)
        self.assertEqual(len(pub.characters), 9)
        self.assertEqual(set(pub.proved_verdicts.keys()), {"A1", "B2"})
        self.assertEqual(pub.proved_verdicts["A1"], "INNOCENT")
        self.assertEqual(pub.proved_verdicts["B2"], "INNOCENT")
        self.assertEqual(len(pub.revealed_clues), 2)
        self.assertEqual(len(pub.unsolved_coords), 7)
        self.assertNotIn("A1", pub.unsolved_coords)
        self.assertNotIn("B2", pub.unsolved_coords)

    def test_strict_information_hiding(self) -> None:
        engine = GameEngine(self.sample_path)
        pub = engine.get_public_state()

        # PublicState should have no hidden_status
        for char in pub.characters:
            self.assertFalse(hasattr(char, "hidden_status"))
            self.assertFalse(hasattr(char, "clue"))

        # Only revealed clues are in pub.revealed_clues
        revealed_ids = {c.clue_id for c in pub.revealed_clues}
        self.assertEqual(revealed_ids, {"clue_A1", "clue_B2"})

        # Unrevealed clues cannot be highlighted
        with self.assertRaises(ValueError):
            engine.get_clue_highlight_cells("clue_B1")

        # Mutating the returned PublicState does not mutate internal GameEngine state
        pub.unsolved_coords.clear()
        pub.proved_verdicts["HACK"] = "CRIMINAL"
        refreshed = engine.get_public_state()
        self.assertEqual(len(refreshed.unsolved_coords), 7)
        self.assertNotIn("HACK", refreshed.proved_verdicts)

    def test_restart(self) -> None:
        agent = MockLogicAgent({"A2": "CRIMINAL"})
        engine = GameEngine(self.sample_path, agent=agent)

        # Make an accepted move
        resp = engine.submit_verdict("A2", "CRIMINAL")
        self.assertTrue(resp.accepted)
        self.assertEqual(engine.revealed_count, 3)

        # Restart
        engine.restart()
        self.assertEqual(engine.revealed_count, 2)
        self.assertEqual(engine.unsolved_count, 7)
        pub = engine.get_public_state()
        self.assertNotIn("A2", pub.proved_verdicts)
        self.assertIn("A2", pub.unsolved_coords)

    def test_submit_verdict_entailed(self) -> None:
        agent = MockLogicAgent({"A2": "CRIMINAL"})
        engine = GameEngine(self.sample_path, agent=agent)

        resp = engine.submit_verdict("A2", "CRIMINAL")
        self.assertTrue(resp.accepted)
        self.assertEqual(resp.reason, "ENTAILED")
        self.assertIsNotNone(resp.revealed_clue)
        self.assertEqual(resp.revealed_clue.clue_id, "clue_A2")

        pub = engine.get_public_state()
        self.assertEqual(pub.proved_verdicts["A2"], "CRIMINAL")
        self.assertNotIn("A2", pub.unsolved_coords)
        self.assertIn("clue_A2", [c.clue_id for c in pub.revealed_clues])

    def test_submit_verdict_contradicted(self) -> None:
        agent = MockLogicAgent({"A2": "CRIMINAL"})
        engine = GameEngine(self.sample_path, agent=agent)

        # Player submits opposite verdict
        resp = engine.submit_verdict("A2", "INNOCENT")
        self.assertFalse(resp.accepted)
        self.assertEqual(resp.reason, "CONTRADICTED")
        self.assertIsNone(resp.revealed_clue)

        # State remains completely intact
        pub = engine.get_public_state()
        self.assertNotIn("A2", pub.proved_verdicts)
        self.assertIn("A2", pub.unsolved_coords)
        self.assertEqual(engine.revealed_count, 2)

    def test_submit_verdict_not_provable(self) -> None:
        agent = MockLogicAgent({"C1": "UNKNOWN"})
        engine = GameEngine(self.sample_path, agent=agent)

        # Player guesses INNOCENT for C1, which is unforced
        resp = engine.submit_verdict("C1", "INNOCENT")
        self.assertFalse(resp.accepted)
        self.assertEqual(resp.reason, "NOT_PROVABLE")
        self.assertIsNone(resp.revealed_clue)

        pub = engine.get_public_state()
        self.assertNotIn("C1", pub.proved_verdicts)
        self.assertIn("C1", pub.unsolved_coords)

    def test_submit_verdict_inconsistent(self) -> None:
        agent = MockLogicAgent({"B1": "INCONSISTENT"})
        engine = GameEngine(self.sample_path, agent=agent)

        resp = engine.submit_verdict("B1", "CRIMINAL")
        self.assertFalse(resp.accepted)
        self.assertEqual(resp.reason, "INCONSISTENT")
        self.assertIsNone(resp.revealed_clue)

    def test_submit_verdict_validation_and_errors(self) -> None:
        engine = GameEngine(self.sample_path)

        # No agent attached
        with self.assertRaises(RuntimeError):
            engine.submit_verdict("A2", "CRIMINAL")

        agent = MockLogicAgent()
        engine.set_agent(agent)

        # Invalid verdict
        with self.assertRaises(ValueError):
            engine.submit_verdict("A2", "UNKNOWN")  # type: ignore

        # Invalid coord
        with self.assertRaises(ValueError):
            engine.submit_verdict("Z9", "CRIMINAL")

        # Already solved cell
        with self.assertRaises(ValueError):
            engine.submit_verdict("A1", "INNOCENT")

    def test_load_sample_4x4(self) -> None:
        path_4x4 = SRC_DIR / "puzzles" / "sample_4x4.json"
        engine = GameEngine(path_4x4)
        self.assertEqual(engine.size, 4)
        self.assertEqual(engine.total_cells, 16)
        pub = engine.get_public_state()
        self.assertEqual(pub.size, 4)
        self.assertEqual(len(pub.characters), 16)
        self.assertEqual(len(pub.proved_verdicts), len(pub.revealed_clues))
        self.assertEqual(len(pub.unsolved_coords), 16 - len(pub.proved_verdicts))

    def test_clue_highlight_resolution(self) -> None:
        engine = GameEngine(self.sample_path)
        # clue_A1 is EXACTLY 1 criminal in ROW 0 (target=0 -> row 1: A1, B1, C1)
        highlighted = engine.get_clue_highlight_cells("clue_A1")
        self.assertEqual(highlighted, ["A1", "B1", "C1"])

        # clue_B2 is FACT target A2
        highlighted_b2 = engine.get_clue_highlight_cells("clue_B2")
        self.assertEqual(highlighted_b2, ["A2"])

    def test_full_solve_lifecycle(self) -> None:
        # Ground truth for sample_3x3:
        # A1: INNOCENT, B1: CRIMINAL, C1: INNOCENT
        # A2: CRIMINAL, B2: INNOCENT, C2: INNOCENT
        # A3: INNOCENT, B3: CRIMINAL, C3: CRIMINAL
        solution: dict[str, Status] = {
            "A1": "INNOCENT",
            "B1": "CRIMINAL",
            "C1": "INNOCENT",
            "A2": "CRIMINAL",
            "B2": "INNOCENT",
            "C2": "INNOCENT",
            "A3": "INNOCENT",
            "B3": "CRIMINAL",
            "C3": "CRIMINAL",
        }
        agent = MockLogicAgent(solution)  # type: ignore
        engine = GameEngine(self.sample_path, agent=agent)

        unsolved = list(engine.get_public_state().unsolved_coords)
        for coord in unsolved:
            resp = engine.submit_verdict(coord, solution[coord])
            self.assertTrue(resp.accepted)
            self.assertEqual(resp.reason, "ENTAILED")

        self.assertTrue(engine.is_solved())
        self.assertEqual(engine.unsolved_count, 0)
        self.assertEqual(engine.revealed_count, 9)


if __name__ == "__main__":
    unittest.main()
