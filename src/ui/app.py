"""Main Pygame application controller for Griductive Solver (Khoa's GUI)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pygame

from game_engine import GameEngine
from models import Clue, PublicState, Status, VerdictResponse
from ui.agent_adapter import AgentAdapter
from ui.animations import CardFlipAnimation
from ui.avatar_manager import AvatarManager
from ui.board_view import (
    STATUS_COLORS,
    BoardViewState,
    LayoutMetrics,
    compute_layout,
    draw_board,
    draw_puzzle_picker_overlay,
    draw_revealed_clues_panel,
    draw_trace_panel,
)
from ui.button import Button
from ui.clue_formatter import (
    discover_puzzle_files,
    get_clue_highlight_coords,
    map_revealed_clues_to_coords,
)
from ui.text import draw_text, draw_text_fitted, draw_wrapped
from ui.theme import (
    ACCENT,
    BG,
    BORDER,
    CRIMINAL,
    FPS,
    INNOCENT,
    MUTED,
    PANEL,
    PANEL_2,
    SCREEN_SIZE,
    TEXT,
    TITLE,
    WARNING,
    WHITE,
)


DEFAULT_PUZZLES_DIR = Path(__file__).resolve().parents[1] / "puzzles"
AUTO_SOLVE_STEP_INTERVAL = 0.55


class GriductiveApp:
    """Interactive Pygame GUI for Griductive Solver.

    Strict boundaries:
    - Owns a single ``GameEngine`` instance and renders solely from ``PublicState``.
    - Isolates all ``LogicAgent`` calls behind ``AgentAdapter``.
    - Never reads ``hidden_status``, unrevealed clues, or puzzle JSON directly.
    """

    def __init__(
        self,
        *,
        puzzles_dir: Path | None = None,
        initial_puzzle: Path | str | None = None,
        agent: Any | None = None,
        auto_discover_agent: bool = True,
        screen_size: tuple[int, int] = SCREEN_SIZE,
        init_display: bool = True,
    ) -> None:
        self.puzzles_dir = Path(puzzles_dir) if puzzles_dir is not None else DEFAULT_PUZZLES_DIR
        self.engine = GameEngine()
        self.adapter = AgentAdapter(agent=agent, auto_discover=auto_discover_agent)
        self.adapter.attach_to_engine(self.engine)

        self.view = BoardViewState()
        self.puzzle_files: list[Path] = discover_puzzle_files(self.puzzles_dir)
        self.current_puzzle_path: Path | None = None
        self.picker_error: str = ""
        self.avatars: AvatarManager | None = None

        self._auto_solve_timer: float = 0.0
        self._running: bool = False
        self._screen_size: tuple[int, int] = screen_size
        self.surface: pygame.Surface | None = None
        self.clock: pygame.time.Clock | None = None

        # Cached interactive hit areas updated each render/layout pass
        self.layout: LayoutMetrics = compute_layout(self._screen_size, 0)
        self._top_buttons: list[Button] = []
        self._verdict_buttons: list[Button] = []
        self._clue_hitboxes: list[tuple[pygame.Rect, Clue]] = []
        self._picker_hitboxes: list[tuple[pygame.Rect, Path]] = []
        self._picker_close_rect: pygame.Rect | None = None

        if init_display:
            self._init_pygame(screen_size)

        if initial_puzzle is not None:
            self.load_puzzle_file(Path(initial_puzzle))
        else:
            # Show puzzle selector on startup (PLAN.md §1)
            self.view.puzzle_picker_open = True
            self._set_status(self._idle_status_message(), "info" if self.adapter.is_ready else "warning")

        self._rebuild_layout()

    def _init_pygame(self, screen_size: tuple[int, int]) -> None:
        if not pygame.get_init():
            pygame.init()
        if not pygame.font.get_init():
            pygame.font.init()
        self.surface = pygame.display.set_mode(screen_size, pygame.RESIZABLE)
        pygame.display.set_caption(TITLE)
        self.clock = pygame.time.Clock()
        self._screen_size = self.surface.get_size()

    def _idle_status_message(self) -> str:
        if not self.adapter.is_ready:
            return self.adapter.status_message
        return "Select an unsolved cell and choose CRIMINAL or INNOCENT, or click a clue to highlight."

    def _set_status(self, text: str, kind: str = "info") -> None:
        self.view.status_text = text
        self.view.status_kind = kind

    # ------------------------------------------------------------------
    # Puzzle lifecycle (strictly through GameEngine)
    # ------------------------------------------------------------------

    def refresh_puzzle_files(self) -> list[Path]:
        self.puzzle_files = discover_puzzle_files(self.puzzles_dir)
        return self.puzzle_files

    def load_puzzle_file(self, path: Path) -> bool:
        """Load a puzzle JSON path exclusively via ``GameEngine.load_puzzle()``."""
        try:
            self.engine.load_puzzle(path)
        except Exception as exc:
            self.picker_error = f"Failed to load {path.name}: {exc}"
            self._set_status(self.picker_error, "error")
            return False

        self.current_puzzle_path = path
        self.picker_error = ""
        self.view.puzzle_picker_open = False
        self._reset_view_state_from_engine()

        pub = self.engine.get_public_state()
        try:
            self.avatars = AvatarManager(self.engine.puzzle_id or path.stem, pub.characters)
        except Exception as exc:
            self.avatars = None
            self._set_status(f"Loaded {path.stem} (avatars unavailable: {exc})", "warning")
        else:
            if self.adapter.is_ready:
                self._set_status(
                    f"Loaded {self.engine.puzzle_id} ({pub.size}x{pub.size}). Select a face-down cell to deduce.",
                    "info",
                )
            else:
                self._set_status(
                    f"Loaded {self.engine.puzzle_id} ({pub.size}x{pub.size}). {self.adapter.status_message}",
                    "warning",
                )

        self._rebuild_layout()
        return True

    def restart_puzzle(self) -> None:
        """Reset current puzzle to initial_revealed via ``GameEngine.restart()``."""
        if self.engine.puzzle_id is None:
            return
        try:
            self.engine.restart()
        except Exception as exc:
            self._set_status(f"Restart failed: {exc}", "error")
            return

        self._reset_view_state_from_engine()
        msg = f"Restarted {self.engine.puzzle_id}."
        if not self.adapter.is_ready:
            msg = f"{msg} {self.adapter.status_message}"
        self._set_status(msg, "info" if self.adapter.is_ready else "warning")
        self._rebuild_layout()

    def _reset_view_state_from_engine(self) -> None:
        self.view.puzzle_id = self.engine.puzzle_id
        self.view.selected_coord = None
        self.view.selected_clue_id = None
        self.view.highlighted_coords.clear()
        self.view.active_hint = None
        self.view.flip_animations.clear()
        self.view.trace.clear()
        self.view.clue_scroll = 0
        self.view.trace_scroll = 0
        self.view.auto_solving = False
        self._auto_solve_timer = 0.0

    # ------------------------------------------------------------------
    # Gameplay actions
    # ------------------------------------------------------------------

    def select_cell(self, coord: str) -> None:
        if self.engine.puzzle_id is None:
            return
        pub = self.engine.get_public_state()
        self.view.selected_coord = coord

        if coord in pub.proved_verdicts:
            clues_by_coord = map_revealed_clues_to_coords(pub)
            clue = clues_by_coord.get(coord)
            if clue is not None:
                self.toggle_clue_highlight(clue)

        self._sync_button_states()

    def toggle_clue_highlight(self, clue: Clue) -> None:
        """Highlight referenced cells via GameEngine's public highlight API."""
        if self.engine.puzzle_id is None:
            return
        if self.view.selected_clue_id == clue.clue_id:
            self.view.selected_clue_id = None
            self.view.highlighted_coords = []
            return

        cells = get_clue_highlight_coords(self.engine, clue)
        self.view.selected_clue_id = clue.clue_id
        self.view.highlighted_coords = cells
        if cells:
            self._set_status(f"Highlighted {clue.clue_id}: {', '.join(cells)}", "info")
        else:
            self._set_status(f"Clue {clue.clue_id} has no highlightable cells.", "warning")

    def submit_verdict(self, verdict: Status) -> VerdictResponse | None:
        """Submit manual verdict for the currently selected unsolved cell."""
        if self.engine.puzzle_id is None:
            return None
        coord = self.view.selected_coord
        if coord is None:
            self._set_status("Select an unsolved cell first.", "warning")
            return None

        pub = self.engine.get_public_state()
        if coord not in pub.unsolved_coords:
            self._set_status(f"Cell {coord} is already proved.", "warning")
            return None

        if not self.adapter.can_verify_verdict:
            self._set_status(self.adapter.status_message, "warning")
            return None

        self.view.active_hint = None
        try:
            response = self.engine.submit_verdict(coord, verdict)
        except Exception as exc:
            self._set_status(f"Verdict error: {exc}", "error")
            return None

        if response.accepted:
            self.view.flip_animations[coord] = CardFlipAnimation()
            self.view.selected_coord = None
            if response.revealed_clue is not None:
                self.view.selected_clue_id = response.revealed_clue.clue_id
                self.view.highlighted_coords = get_clue_highlight_coords(self.engine, response.revealed_clue)
            if self.engine.is_solved():
                self._set_status("SOLVED! All characters deduced without guessing.", "success")
            else:
                clue_note = (
                    f" Revealed {response.revealed_clue.clue_id}."
                    if response.revealed_clue is not None
                    else ""
                )
                self._set_status(f"ENTAILED: {coord} is {verdict}.{clue_note}", "success")
        elif response.reason == "NOT_PROVABLE":
            self._set_status(
                f"NOT_PROVABLE: {coord} cannot be proven {verdict} from current clues (no guessing!).",
                "warning",
            )
        elif response.reason == "CONTRADICTED":
            self._set_status(
                f"CONTRADICTED: {coord} cannot be {verdict}; the opposite verdict is forced.",
                "error",
            )
        elif response.reason == "INCONSISTENT":
            self._set_status(
                "INCONSISTENT: The current public knowledge base is contradictory.",
                "error",
            )
        else:
            self._set_status(f"Rejected ({response.reason}).", "warning")

        self._sync_button_states()
        return response

    def request_hint(self) -> None:
        """Ask LogicAgent for a hint derived strictly from PublicState."""
        if self.engine.puzzle_id is None:
            return
        if self.engine.is_solved():
            self._set_status("Puzzle is already solved.", "success")
            return
        if not self.adapter.can_hint:
            self._set_status("Hint chua san sang: LogicAgent chua cai dat API get_hint().", "warning")
            return

        pub = self.engine.get_public_state()
        try:
            hint = self.adapter.request_hint(pub)
        except Exception as exc:
            self._set_status(f"Hint failed: {exc}", "error")
            return

        self.view.active_hint = hint
        if hint.hint_coord is None and not hint.relevant_clue_ids:
            self._set_status("Hint: no forced verdict available right now (UNKNOWN).", "warning")
            return

        if hint.hint_coord is not None and hint.hint_coord in pub.unsolved_coords:
            self.view.selected_coord = hint.hint_coord

        # Highlight union of relevant clues via GameEngine public highlight API
        highlighted: list[str] = []
        seen: set[str] = set()
        revealed_by_id = {c.clue_id: c for c in pub.revealed_clues}
        first_valid_clue_id: str | None = None
        for cid in hint.relevant_clue_ids:
            clue = revealed_by_id.get(cid)
            if clue is None:
                continue
            if first_valid_clue_id is None:
                first_valid_clue_id = cid
            for cell in get_clue_highlight_coords(self.engine, clue):
                if cell not in seen:
                    seen.add(cell)
                    highlighted.append(cell)

        self.view.selected_clue_id = first_valid_clue_id
        self.view.highlighted_coords = highlighted

        parts: list[str] = ["Hint:"]
        if hint.hint_coord:
            verdict_str = f" -> {hint.verdict}" if hint.verdict else ""
            parts.append(f"{hint.hint_coord}{verdict_str}")
        if hint.relevant_clue_ids:
            parts.append(f"(clues: {', '.join(hint.relevant_clue_ids)})")
        self._set_status(" ".join(parts), "success")
        self._sync_button_states()

    def toggle_auto_solve(self) -> None:
        if self.engine.puzzle_id is None:
            return
        if self.view.auto_solving:
            self.view.auto_solving = False
            self._set_status("Auto Solve stopped by user.", "info")
            self._sync_button_states()
            return

        if self.engine.is_solved():
            self._set_status("Puzzle is already solved.", "success")
            return
        if not self.adapter.can_auto_solve:
            self._set_status("Auto Solve chua san sang: LogicAgent chua cai dat API step.", "warning")
            return

        self.view.auto_solving = True
        self.view.active_hint = None
        self._auto_solve_timer = 0.0
        self._execute_auto_solve_step()
        self._sync_button_states()

    def _execute_auto_solve_step(self) -> None:
        result = self.adapter.run_auto_solve_step(self.engine)
        if result.status == "STEP" and result.step is not None:
            step = result.step
            self.view.trace.append(step)
            self.view.trace_scroll = max(0, len(self.view.trace) * 52)
            self.view.flip_animations[step.target_coord] = CardFlipAnimation()
            self.view.selected_coord = None
            if step.newly_revealed_clue_id:
                pub = self.engine.get_public_state()
                clue = next((c for c in pub.revealed_clues if c.clue_id == step.newly_revealed_clue_id), None)
                if clue is not None:
                    self.view.selected_clue_id = clue.clue_id
                    self.view.highlighted_coords = get_clue_highlight_coords(self.engine, clue)

            if self.engine.is_solved():
                self.view.auto_solving = False
                self._set_status(
                    f"Auto Solve finished! Solved in {len(self.view.trace)} step(s).",
                    "success",
                )
            else:
                self._set_status(
                    f"Auto Solve step #{step.step}: {step.target_coord} -> {step.verdict} (SAT calls: {step.sat_calls}).",
                    "success",
                )
            self._sync_button_states()
            return

        # Terminal states: SOLVED, UNKNOWN, INCONSISTENT, UNAVAILABLE, ERROR
        self.view.auto_solving = False
        kind = "success" if result.status == "SOLVED" else ("warning" if result.status in ("UNKNOWN", "UNAVAILABLE") else "error")
        self._set_status(result.message or f"Auto Solve stopped ({result.status}).", kind)
        self._sync_button_states()

    def open_puzzle_picker(self) -> None:
        self.view.auto_solving = False
        self.refresh_puzzle_files()
        self.picker_error = ""
        self.view.puzzle_picker_open = True
        self._sync_button_states()

    def close_puzzle_picker(self) -> None:
        if self.engine.puzzle_id is not None:
            self.view.puzzle_picker_open = False
            self._sync_button_states()

    # ------------------------------------------------------------------
    # Layout & Controls
    # ------------------------------------------------------------------

    def _rebuild_layout(self) -> None:
        grid_size = self.engine.size if self.engine.puzzle_id is not None else 0
        self.layout = compute_layout(self._screen_size, grid_size)

        # Top-bar control buttons (right-aligned)
        btn_h = 36
        btn_y = (self.layout.top_bar.height - btn_h) // 2
        right = self.layout.top_bar.right - 16
        gap = 8

        auto_w = 114
        hint_w = 82
        restart_w = 92
        load_w = 82

        auto_rect = pygame.Rect(right - auto_w, btn_y, auto_w, btn_h)
        hint_rect = pygame.Rect(auto_rect.left - gap - hint_w, btn_y, hint_w, btn_h)
        restart_rect = pygame.Rect(hint_rect.left - gap - restart_w, btn_y, restart_w, btn_h)
        load_rect = pygame.Rect(restart_rect.left - gap - load_w, btn_y, load_w, btn_h)

        self._btn_load = Button(load_rect, "Load", self.open_puzzle_picker)
        self._btn_restart = Button(restart_rect, "Restart", self.restart_puzzle)
        self._btn_hint = Button(hint_rect, "Hint", self.request_hint)
        self._btn_auto = Button(auto_rect, "Auto Solve", self.toggle_auto_solve, accent=True)
        self._top_buttons = [self._btn_load, self._btn_restart, self._btn_hint, self._btn_auto]

        # Verdict buttons inside Action Panel
        ap = self.layout.action_panel
        vb_y = ap.top + 82
        vb_h = 38
        vb_gap = 10
        vb_w = (ap.width - 24 - vb_gap) // 2
        crim_rect = pygame.Rect(ap.left + 12, vb_y, vb_w, vb_h)
        inno_rect = pygame.Rect(crim_rect.right + vb_gap, vb_y, vb_w, vb_h)

        self._btn_criminal = Button(
            crim_rect,
            "CRIMINAL",
            lambda: self.submit_verdict("CRIMINAL"),
            fill_color=(186, 58, 74),
            hover_color=CRIMINAL,
            text_color=WHITE,
        )
        self._btn_innocent = Button(
            inno_rect,
            "INNOCENT",
            lambda: self.submit_verdict("INNOCENT"),
            fill_color=(48, 148, 98),
            hover_color=INNOCENT,
            text_color=(10, 24, 18),
        )
        self._verdict_buttons = [self._btn_criminal, self._btn_innocent]
        self._sync_button_states()

    def _sync_button_states(self) -> None:
        has_puzzle = self.engine.puzzle_id is not None
        solved = self.engine.is_solved() if has_puzzle else False
        picker_open = self.view.puzzle_picker_open

        self._btn_load.enabled = True
        self._btn_restart.enabled = has_puzzle and not picker_open
        self._btn_hint.enabled = (
            has_puzzle and not solved and not picker_open and not self.view.auto_solving and self.adapter.can_hint
        )
        self._btn_auto.text = "Stop" if self.view.auto_solving else "Auto Solve"
        self._btn_auto.enabled = (
            has_puzzle
            and not picker_open
            and (self.view.auto_solving or (not solved and self.adapter.can_auto_solve))
        )

        can_submit = False
        if has_puzzle and not picker_open and not self.view.auto_solving and self.adapter.can_verify_verdict:
            if self.view.selected_coord is not None:
                pub = self.engine.get_public_state()
                can_submit = self.view.selected_coord in pub.unsolved_coords

        self._btn_criminal.enabled = can_submit
        self._btn_innocent.enabled = can_submit

    # ------------------------------------------------------------------
    # Frame update, event handling, rendering
    # ------------------------------------------------------------------

    def update(self, dt: float) -> None:
        """Advance card flip animations and Auto Solve step timer."""
        dt = max(0.0, float(dt))
        finished_coords = [
            coord
            for coord, anim in self.view.flip_animations.items()
            if anim.update(dt)
        ]
        for coord in finished_coords:
            del self.view.flip_animations[coord]

        if self.view.auto_solving:
            self._auto_solve_timer += dt
            if self._auto_solve_timer >= AUTO_SOLVE_STEP_INTERVAL and not self.view.flip_animations:
                self._auto_solve_timer = 0.0
                self._execute_auto_solve_step()

    def handle_event(self, event: pygame.event.Event) -> None:
        """Process a single Pygame event safely without crashing the loop."""
        try:
            if event.type == pygame.QUIT:
                self._running = False
                return

            if event.type == pygame.VIDEORESIZE:
                new_w = max(900, event.w)
                new_h = max(620, event.h)
                self._screen_size = (new_w, new_h)
                if self.surface is not None:
                    self.surface = pygame.display.set_mode(self._screen_size, pygame.RESIZABLE)
                self._rebuild_layout()
                return

            if event.type == pygame.KEYDOWN:
                self._handle_key(event.key)
                return

            if self.view.puzzle_picker_open:
                self._handle_picker_event(event)
                return

            for btn in self._top_buttons:
                if btn.handle_event(event):
                    return

            for btn in self._verdict_buttons:
                if btn.handle_event(event):
                    return

            if event.type == pygame.MOUSEWHEEL:
                mx, my = pygame.mouse.get_pos()
                if self.layout.clues_panel.collidepoint(mx, my):
                    self.view.clue_scroll = max(0, self.view.clue_scroll - event.y * 28)
                elif self.layout.trace_panel.collidepoint(mx, my):
                    self.view.trace_scroll = max(0, self.view.trace_scroll - event.y * 28)
                return

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = event.pos
                # Check revealed clues list clicks
                for rect, clue in self._clue_hitboxes:
                    if rect.collidepoint(pos):
                        self.toggle_clue_highlight(clue)
                        return

                # Check board cell clicks
                for coord, rect in self.layout.cell_rects.items():
                    if rect.collidepoint(pos):
                        self.select_cell(coord)
                        return
        except Exception as exc:
            self.view.auto_solving = False
            self._set_status(f"Unexpected UI error: {exc}", "error")

    def _handle_key(self, key: int) -> None:
        if key == pygame.K_ESCAPE:
            if self.view.puzzle_picker_open:
                self.close_puzzle_picker()
            else:
                self.view.selected_clue_id = None
                self.view.highlighted_coords = []
                self.view.active_hint = None
            return
        if self.view.puzzle_picker_open:
            return
        if key == pygame.K_l:
            self.open_puzzle_picker()
        elif key == pygame.K_r and self._btn_restart.enabled:
            self.restart_puzzle()
        elif key == pygame.K_h and self._btn_hint.enabled:
            self.request_hint()
        elif key == pygame.K_c and self._btn_criminal.enabled:
            self.submit_verdict("CRIMINAL")
        elif key == pygame.K_i and self._btn_innocent.enabled:
            self.submit_verdict("INNOCENT")

    def _handle_picker_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            if self._picker_close_rect is not None and self._picker_close_rect.collidepoint(pos):
                self.close_puzzle_picker()
                return
            for rect, path in self._picker_hitboxes:
                if rect.collidepoint(pos):
                    self.load_puzzle_file(path)
                    return

    def render(self, surface: pygame.Surface | None = None) -> None:
        target = surface if surface is not None else self.surface
        if target is None:
            return

        target.fill(BG)
        self._draw_top_bar(target)

        if self.engine.puzzle_id is not None:
            pub = self.engine.get_public_state()
            draw_board(target, self.layout, pub, self.view, self.avatars)
            self._draw_action_panel(target, pub)
            self._clue_hitboxes = draw_revealed_clues_panel(target, self.layout.clues_panel, pub, self.view)
            draw_trace_panel(target, self.layout.trace_panel, self.view, self.adapter.can_auto_solve)
        else:
            pygame.draw.rect(target, PANEL, self.layout.board_panel, border_radius=12)
            pygame.draw.rect(target, BORDER, self.layout.board_panel, width=1, border_radius=12)
            draw_text(
                target,
                "Choose a puzzle from src/puzzles/ to begin.",
                self.layout.board_panel.center,
                size=18,
                color=MUTED,
                anchor="center",
            )
            self._clue_hitboxes = []

        if self.view.puzzle_picker_open:
            self._picker_hitboxes, self._picker_close_rect = draw_puzzle_picker_overlay(
                target,
                self.puzzle_files,
                self.current_puzzle_path,
                error_message=self.picker_error,
            )
        else:
            self._picker_hitboxes = []
            self._picker_close_rect = None

    def _draw_top_bar(self, surface: pygame.Surface) -> None:
        bar = self.layout.top_bar
        pygame.draw.rect(surface, PANEL, bar)
        pygame.draw.line(surface, BORDER, (bar.left, bar.bottom - 1), (bar.right, bar.bottom - 1), 1)

        title_x = 18
        draw_text(surface, "Griductive Solver", (title_x, 12), size=20, color=WHITE, bold=True)

        if self.engine.puzzle_id is not None:
            subtitle = (
                f"Puzzle: {self.engine.puzzle_id} ({self.engine.size}x{self.engine.size})  |  "
                f"Proved: {self.engine.revealed_count}/{self.engine.total_cells}"
            )
        else:
            subtitle = "No puzzle loaded"
        draw_text(surface, subtitle, (title_x, 38), size=12, color=MUTED)

        # Agent status pill
        pill_text = "Agent: Ready" if self.adapter.is_ready else "Agent: Unavailable"
        pill_color = INNOCENT if self.adapter.is_ready else WARNING
        pill_rect = pygame.Rect(self._btn_load.rect.left - 156, (bar.height - 28) // 2, 144, 28)
        if pill_rect.left > 360:
            pygame.draw.rect(surface, PANEL_2, pill_rect, border_radius=14)
            pygame.draw.rect(surface, pill_color, pill_rect, width=1, border_radius=14)
            draw_text(surface, pill_text, pill_rect.center, size=12, color=pill_color, bold=True, anchor="center")

        for btn in self._top_buttons:
            btn.draw(surface)

    def _draw_action_panel(self, surface: pygame.Surface, public_state: PublicState) -> None:
        ap = self.layout.action_panel
        pygame.draw.rect(surface, PANEL, ap, border_radius=12)
        pygame.draw.rect(surface, BORDER, ap, width=1, border_radius=12)

        draw_text(surface, "Verdict & Status", (ap.left + 12, ap.top + 10), size=15, color=TEXT, bold=True)

        # Selected cell details
        sel_rect = pygame.Rect(ap.left + 12, ap.top + 34, ap.width - 24, 40)
        pygame.draw.rect(surface, PANEL_2, sel_rect, border_radius=8)
        pygame.draw.rect(surface, BORDER, sel_rect, width=1, border_radius=8)

        chars = {c.coord: c for c in public_state.characters}
        if self.view.selected_coord and self.view.selected_coord in chars:
            ch = chars[self.view.selected_coord]
            verdict = public_state.proved_verdicts.get(ch.coord)
            state_str = f"Proved: {verdict}" if verdict else "Face-down (unsolved)"
            state_col = (
                CRIMINAL if verdict == "CRIMINAL" else (INNOCENT if verdict == "INNOCENT" else ACCENT)
            )
            draw_text_fitted(
                surface,
                f"{ch.coord} — {ch.name} ({ch.occupation})",
                (sel_rect.left + 10, sel_rect.top + 4),
                sel_rect.width - 20,
                size=13,
                color=WHITE,
                bold=True,
            )
            draw_text_fitted(
                surface,
                state_str,
                (sel_rect.left + 10, sel_rect.top + 21),
                sel_rect.width - 20,
                size=11,
                color=state_col,
            )
        else:
            draw_text(
                surface,
                "Click a cell on the board to inspect or judge.",
                (sel_rect.left + 10, sel_rect.centery),
                size=12,
                color=MUTED,
                anchor="midleft",
            )

        for btn in self._verdict_buttons:
            btn.draw(surface)

        # Status feedback banner
        status_rect = pygame.Rect(ap.left + 12, ap.top + 128, ap.width - 24, ap.height - 138)
        status_color = STATUS_COLORS.get(self.view.status_kind, MUTED)
        pygame.draw.rect(surface, PANEL_2, status_rect, border_radius=8)
        pygame.draw.rect(surface, status_color, status_rect, width=1, border_radius=8)
        text_box = status_rect.inflate(-14, -10)
        draw_wrapped(
            surface,
            self.view.status_text or self._idle_status_message(),
            text_box,
            size=12,
            color=status_color if self.view.status_kind != "info" else TEXT,
            line_gap=3,
        )

    def run(self) -> None:
        """Run the main Pygame event/update/render loop."""
        if self.surface is None or self.clock is None:
            self._init_pygame(self._screen_size)
            self._rebuild_layout()

        assert self.surface is not None and self.clock is not None
        self._running = True
        while self._running:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                self.handle_event(event)
            self.update(dt)
            self.render(self.surface)
            pygame.display.flip()

        pygame.quit()
