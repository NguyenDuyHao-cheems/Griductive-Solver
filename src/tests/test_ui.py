"""Unit and headless integration tests for Khoa's GUI modules (Section 4.1)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from game_engine import GameEngine
from models import (
    Clue,
    DeductionStep,
    EntailmentStatus,
    HintResponse,
    PublicState,
    Region,
    Status,
    all_coords,
    coord_to_rc,
)
from ui.agent_adapter import AgentAdapter
from ui.clue_formatter import (
    discover_puzzle_files,
    format_clue_text,
    get_clue_highlight_coords,
    map_revealed_clues_to_coords,
)

try:
    import pygame  # noqa: F401

    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False


class MockFullAgent:
    """Test-only mock agent supporting verdict classification, Hint, and step Auto Solve."""

    def __init__(
        self,
        verdicts: dict[str, EntailmentStatus] | None = None,
        hint: HintResponse | None = None,
        steps: list[DeductionStep | str | None] | None = None,
    ) -> None:
        self.verdicts = verdicts or {}
        self.hint = hint
        self.steps = list(steps or [])
        self._step_idx = 0

    def classify_cell(self, public_state: PublicState, coord: str) -> EntailmentStatus:
        return self.verdicts.get(coord, "UNKNOWN")

    def get_hint(self, public_state: PublicState) -> HintResponse:
        if self.hint is not None:
            return self.hint
        return HintResponse(hint_coord=None, verdict=None, relevant_clue_ids=[])

    def step(self, public_state: PublicState):
        if self._step_idx >= len(self.steps):
            return None
        item = self.steps[self._step_idx]
        self._step_idx += 1
        return item


def _write_temp_5x5_puzzle(directory: Path) -> Path:
    size = 5
    cells = []
    for coord in all_coords(size):
        row, col = coord_to_rc(coord, size)
        cells.append(
            {
                "coord": coord,
                "row": row,
                "col": col,
                "name": f"Person_{coord}",
                "occupation": "Tester",
                "hidden_status": "INNOCENT",
                "clue": {
                    "clue_id": f"clue_{coord}",
                    "type": "EXACTLY",
                    "region": {"kind": "ROW", "target": row},
                    "k": 0,
                    "text": f"No criminals in row {row + 1}.",
                },
            }
        )
    data = {
        "puzzle_id": "test_5x5",
        "size": 5,
        "initial_revealed": ["A1", "C3"],
        "cells": cells,
    }
    path = directory / "test_5x5.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestAgentAdapterAndFormatters(unittest.TestCase):
    def setUp(self) -> None:
        self.puzzles_dir = SRC_DIR / "puzzles"
        self.sample_3x3 = self.puzzles_dir / "sample_3x3.json"

    def test_default_discovery_handles_unimplemented_agent_safely(self) -> None:
        adapter = AgentAdapter(agent=None, auto_discover=False)
        # When agent is not available; adapter must report unavailable rather than fabricating
        self.assertFalse(adapter.can_verify_verdict)
        self.assertFalse(adapter.can_hint)
        self.assertFalse(adapter.can_auto_solve)
        self.assertFalse(adapter.is_ready)

        engine = GameEngine(self.sample_3x3)
        self.assertFalse(adapter.attach_to_engine(engine))
        res = adapter.run_auto_solve_step(engine)
        self.assertEqual(res.status, "UNAVAILABLE")

    def test_default_discovery_with_real_logic_agent(self) -> None:
        adapter = AgentAdapter(auto_discover=True)
        # src/agent.py is implemented; adapter must discover and connect real LogicAgent
        self.assertTrue(adapter.can_verify_verdict)
        self.assertTrue(adapter.can_hint)
        self.assertTrue(adapter.can_auto_solve)
        self.assertTrue(adapter.is_ready)

        engine = GameEngine(self.sample_3x3)
        self.assertTrue(adapter.attach_to_engine(engine))
        res = adapter.run_auto_solve_step(engine)
        self.assertEqual(res.status, "STEP")
        self.assertIsNotNone(res.step)

    def test_adapter_with_injected_mock_agent(self) -> None:
        step1 = DeductionStep(
            step=1,
            active_clue_ids=["clue_A1", "clue_B2"],
            sat_queries=["KB_0 ^ ~C_A2: UNSAT"],
            sat_calls=2,
            target_coord="A2",
            verdict="CRIMINAL",
            newly_revealed_clue_id=None,
        )
        mock = MockFullAgent(
            verdicts={"A2": "CRIMINAL"},
            hint=HintResponse(hint_coord="A2", verdict="CRIMINAL", relevant_clue_ids=["clue_B2"]),
            steps=[step1, None],
        )
        adapter = AgentAdapter(agent=mock)
        self.assertTrue(adapter.can_verify_verdict)
        self.assertTrue(adapter.can_hint)
        self.assertTrue(adapter.can_auto_solve)

        engine = GameEngine(self.sample_3x3)
        self.assertTrue(adapter.attach_to_engine(engine))

        hint = adapter.request_hint(engine.get_public_state())
        self.assertEqual(hint.hint_coord, "A2")
        self.assertEqual(hint.verdict, "CRIMINAL")
        self.assertEqual(hint.relevant_clue_ids, ["clue_B2"])

        res1 = adapter.run_auto_solve_step(engine)
        self.assertEqual(res1.status, "STEP")
        self.assertIsNotNone(res1.step)
        assert res1.step is not None
        self.assertEqual(res1.step.newly_revealed_clue_id, "clue_A2")
        self.assertEqual(engine.revealed_count, 3)

        res2 = adapter.run_auto_solve_step(engine)
        self.assertEqual(res2.status, "UNKNOWN")

    def test_clue_formatters_and_information_hiding(self) -> None:
        files = discover_puzzle_files(self.puzzles_dir)
        names = [p.name for p in files]
        self.assertIn("sample_3x3.json", names)
        self.assertIn("sample_4x4.json", names)

        engine = GameEngine(self.sample_3x3)
        pub = engine.get_public_state()
        mapped = map_revealed_clues_to_coords(pub)
        self.assertEqual(set(mapped.keys()), {"A1", "B2"})
        self.assertEqual(get_clue_highlight_coords(engine, mapped["A1"]), ["A1", "B1", "C1"])
        self.assertEqual(get_clue_highlight_coords(engine, mapped["B2"]), ["A2"])

        # Unrevealed clue must not be highlightable
        fake_unrevealed = Clue(clue_id="clue_B1", type="DIFFERENT", a="B1", b="C1")
        self.assertEqual(get_clue_highlight_coords(engine, fake_unrevealed), [])

        # Structured formatting fallback for all templates including extensions
        clues = [
            Clue(clue_id="c1", type="FACT", target="A1", status="CRIMINAL"),
            Clue(clue_id="c2", type="SAME", a="A1", b="B1"),
            Clue(clue_id="c3", type="DIFFERENT", a="A1", b="B1"),
            Clue(clue_id="c4", type="EXACTLY", region=Region("ROW", 0), k=1),
            Clue(clue_id="c5", type="AT_LEAST", region=Region("COL", "A"), k=1),
            Clue(clue_id="c6", type="AT_MOST", region=Region("NEIGHBORS", "B2"), k=2),
            Clue(clue_id="c7", type="PARITY", region=Region("EXPLICIT", cells=("A1", "B2")), parity="EVEN"),
            Clue(
                clue_id="c8",
                type="COMPARE_COUNT",
                r1=Region("ROW", 0),
                op="GT",
                r2=Region("COL", "A"),
            ),
        ]
        for clue in clues:
            rendered = format_clue_text(clue)
            self.assertTrue(len(rendered) > 5)


@unittest.skipUnless(HAS_PYGAME, "pygame is not installed in this environment")
class TestGriductiveAppHeadless(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        import pygame

        pygame.init()
        pygame.font.init()

    @classmethod
    def tearDownClass(cls) -> None:
        import pygame

        pygame.quit()

    def setUp(self) -> None:
        self.sample_3x3 = SRC_DIR / "puzzles" / "sample_3x3.json"
        self.sample_4x4 = SRC_DIR / "puzzles" / "sample_4x4.json"

    def test_startup_picker_and_disabled_buttons_without_agent(self) -> None:
        from ui.app import GriductiveApp

        app = GriductiveApp(auto_discover_agent=False)
        self.assertTrue(app.view.puzzle_picker_open)
        self.assertGreaterEqual(len(app.puzzle_files), 2)
        app.render()

        self.assertTrue(app.load_puzzle_file(self.sample_3x3))
        self.assertFalse(app.view.puzzle_picker_open)
        self.assertEqual(app.engine.puzzle_id, "sample_3x3")

        app.select_cell("A2")
        self.assertFalse(app._btn_criminal.enabled)
        self.assertFalse(app._btn_innocent.enabled)
        self.assertFalse(app._btn_hint.enabled)
        self.assertFalse(app._btn_auto.enabled)
        app.render()

    def test_startup_with_real_discovered_agent(self) -> None:
        from ui.app import GriductiveApp

        app = GriductiveApp(auto_discover_agent=True)
        self.assertTrue(app.load_puzzle_file(self.sample_3x3))
        app.select_cell("A2")
        self.assertTrue(app._btn_criminal.enabled)
        self.assertTrue(app._btn_innocent.enabled)
        self.assertTrue(app._btn_hint.enabled)
        self.assertTrue(app._btn_auto.enabled)
        app.render()

    def test_manual_verdicts_highlight_hint_restart_and_autosolve(self) -> None:
        from ui.app import AUTO_SOLVE_STEP_INTERVAL, GriductiveApp

        step1 = DeductionStep(
            step=1,
            active_clue_ids=["clue_A1", "clue_B2"],
            sat_queries=["KB_0 ^ ~C_A2: UNSAT"],
            sat_calls=2,
            target_coord="A2",
            verdict="CRIMINAL",
        )
        mock = MockFullAgent(
            verdicts={"A2": "CRIMINAL", "C1": "UNKNOWN", "B1": "INCONSISTENT"},
            hint=HintResponse(hint_coord="A2", verdict="CRIMINAL", relevant_clue_ids=["clue_B2"]),
            steps=[step1, "UNKNOWN"],
        )

        app = GriductiveApp(initial_puzzle=self.sample_3x3, agent=mock)
        self.assertTrue(app._btn_hint.enabled)
        self.assertTrue(app._btn_auto.enabled)

        # Rejected verdicts must NOT reveal clues or trigger card flip
        app.select_cell("C1")
        resp_np = app.submit_verdict("INNOCENT")
        self.assertIsNotNone(resp_np)
        assert resp_np is not None
        self.assertEqual(resp_np.reason, "NOT_PROVABLE")
        self.assertEqual(app.engine.revealed_count, 2)
        self.assertNotIn("C1", app.view.flip_animations)
        self.assertIn("NOT_PROVABLE", app.view.status_text)

        app.select_cell("A2")
        resp_con = app.submit_verdict("INNOCENT")
        assert resp_con is not None
        self.assertEqual(resp_con.reason, "CONTRADICTED")
        self.assertEqual(app.engine.revealed_count, 2)
        self.assertNotIn("A2", app.view.flip_animations)
        self.assertIn("CONTRADICTED", app.view.status_text)

        app.select_cell("B1")
        resp_inc = app.submit_verdict("CRIMINAL")
        assert resp_inc is not None
        self.assertEqual(resp_inc.reason, "INCONSISTENT")
        self.assertEqual(app.engine.revealed_count, 2)
        self.assertIn("INCONSISTENT", app.view.status_text)

        # Hint selects hint_coord and highlights relevant_clue_ids
        app.request_hint()
        self.assertEqual(app.view.selected_coord, "A2")
        self.assertEqual(app.view.highlighted_coords, ["A2"])

        # Entailed verdict triggers CardFlipAnimation and reveals clue
        resp_ok = app.submit_verdict("CRIMINAL")
        assert resp_ok is not None
        self.assertTrue(resp_ok.accepted)
        self.assertIn("A2", app.view.flip_animations)
        self.assertEqual(app.engine.revealed_count, 3)

        # Advance animation to completion and render
        app.update(0.2)
        app.render()
        app.update(0.2)
        self.assertNotIn("A2", app.view.flip_animations)

        # Restart resets board and clears view state
        app.restart_puzzle()
        self.assertEqual(app.engine.revealed_count, 2)
        self.assertEqual(app.view.trace, [])
        self.assertEqual(app.view.highlighted_coords, [])

        # Auto Solve steps once, waits for flip + timer, then stops on UNKNOWN
        app.toggle_auto_solve()
        self.assertTrue(app.view.auto_solving)
        self.assertEqual(len(app.view.trace), 1)
        self.assertEqual(app.engine.revealed_count, 3)
        self.assertIn("A2", app.view.flip_animations)

        app.update(AUTO_SOLVE_STEP_INTERVAL + 0.4)
        # First update finished animation; next update after interval triggers UNKNOWN stop
        app.update(AUTO_SOLVE_STEP_INTERVAL + 0.1)
        self.assertFalse(app.view.auto_solving)
        app.render()

    def test_supports_3x3_4x4_and_5x5_grids(self) -> None:
        from ui.app import GriductiveApp

        app = GriductiveApp(initial_puzzle=self.sample_4x4, auto_discover_agent=False)
        self.assertEqual(app.engine.size, 4)
        self.assertEqual(len(app.layout.cell_rects), 16)
        app.render()

        with tempfile.TemporaryDirectory() as tmp:
            path_5x5 = _write_temp_5x5_puzzle(Path(tmp))
            self.assertTrue(app.load_puzzle_file(path_5x5))
            self.assertEqual(app.engine.size, 5)
            self.assertEqual(len(app.layout.cell_rects), 25)
            app.render()


if __name__ == "__main__":
    unittest.main()
