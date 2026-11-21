"""Rendering helpers for the Griductive Pygame GUI.

All rendering reads exclusively from ``PublicState`` and presentation-only view
state (animations, active selection, highlighted coords, hints, trace).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pygame

from models import (
    CharacterInfo,
    Clue,
    DeductionStep,
    HintResponse,
    PublicState,
    coord_to_rc,
    rc_to_coord,
)
from ui.animations import CardFlipAnimation
from ui.avatar_manager import AvatarManager
from ui.clue_formatter import format_clue_text, map_revealed_clues_to_coords
from ui.text import draw_text, draw_text_fitted, draw_wrapped
from ui.theme import (
    ACCENT,
    ACCENT_2,
    BG,
    BORDER,
    CARD_BACK,
    CRIMINAL,
    INNOCENT,
    MUTED,
    PANEL,
    PANEL_2,
    TEXT,
    WARNING,
    WHITE,
)


STATUS_COLORS = {
    "info": MUTED,
    "success": INNOCENT,
    "warning": WARNING,
    "error": CRIMINAL,
}

# Subtle translucent-style card tints (dark theme)
CARD_FRONT_CRIMINAL = (58, 30, 42)
CARD_FRONT_INNOCENT = (25, 52, 46)
HIGHLIGHT_FILL = (64, 57, 34)


@dataclass
class BoardViewState:
    """Mutable presentation-only state tracked by the GUI."""

    puzzle_id: str | None = None
    selected_coord: str | None = None
    selected_clue_id: str | None = None
    highlighted_coords: list[str] = field(default_factory=list)
    active_hint: HintResponse | None = None
    flip_animations: dict[str, CardFlipAnimation] = field(default_factory=dict)
    trace: list[DeductionStep] = field(default_factory=list)
    status_text: str = ""
    status_kind: str = "info"
    clue_scroll: int = 0
    trace_scroll: int = 0
    auto_solving: bool = False
    puzzle_picker_open: bool = False


@dataclass
class LayoutMetrics:
    """Computed rectangles for the current window size."""

    top_bar: pygame.Rect
    board_panel: pygame.Rect
    side_panel: pygame.Rect
    action_panel: pygame.Rect
    clues_panel: pygame.Rect
    trace_panel: pygame.Rect
    cell_rects: dict[str, pygame.Rect]
    col_header_centers: list[tuple[str, tuple[int, int]]]
    row_header_centers: list[tuple[str, tuple[int, int]]]


def compute_layout(surface_size: tuple[int, int], grid_size: int) -> LayoutMetrics:
    """Compute responsive rects for top bar, N×N board, and right side panel."""
    width, height = surface_size
    pad = 16
    top_h = 62
    top_bar = pygame.Rect(0, 0, width, top_h)

    side_w = max(360, min(440, int(width * 0.33)))
    content_top = top_h + 12
    content_h = max(300, height - content_top - pad)

    board_w = max(360, width - side_w - pad * 3)
    board_panel = pygame.Rect(pad, content_top, board_w, content_h)
    side_panel = pygame.Rect(board_panel.right + pad, content_top, side_w, content_h)

    action_h = 196
    remaining_h = max(200, side_panel.height - action_h - 20)
    clues_h = int(remaining_h * 0.54)
    trace_h = max(100, remaining_h - clues_h)

    action_panel = pygame.Rect(side_panel.left, side_panel.top, side_panel.width, action_h)
    clues_panel = pygame.Rect(side_panel.left, action_panel.bottom + 10, side_panel.width, clues_h)
    trace_panel = pygame.Rect(side_panel.left, clues_panel.bottom + 10, side_panel.width, trace_h)

    cell_rects: dict[str, pygame.Rect] = {}
    col_centers: list[tuple[str, tuple[int, int]]] = []
    row_centers: list[tuple[str, tuple[int, int]]] = []

    if grid_size > 0:
        axis_left = 30
        axis_top = 28
        inner_pad = 12
        gap = 12 if grid_size <= 3 else (10 if grid_size == 4 else 8)

        avail_w = max(120, board_panel.width - axis_left - inner_pad * 2)
        avail_h = max(120, board_panel.height - axis_top - inner_pad * 2)

        cell_w = max(60, (avail_w - gap * (grid_size - 1)) // grid_size)
        cell_h = max(60, (avail_h - gap * (grid_size - 1)) // grid_size)

        grid_w = cell_w * grid_size + gap * (grid_size - 1)
        grid_h = cell_h * grid_size + gap * (grid_size - 1)
        start_x = board_panel.left + axis_left + inner_pad + (avail_w - grid_w) // 2
        start_y = board_panel.top + axis_top + inner_pad + (avail_h - grid_h) // 2

        for c in range(grid_size):
            col_label = rc_to_coord(0, c, grid_size)[0]
            cx = start_x + c * (cell_w + gap) + cell_w // 2
            cy = start_y - 14
            col_centers.append((col_label, (cx, cy)))

        for r in range(grid_size):
            row_label = rc_to_coord(r, 0, grid_size)[1:]
            rx = start_x - 16
            ry = start_y + r * (cell_h + gap) + cell_h // 2
            row_centers.append((row_label, (rx, ry)))

        for r in range(grid_size):
            for c in range(grid_size):
                coord = rc_to_coord(r, c, grid_size)
                x = start_x + c * (cell_w + gap)
                y = start_y + r * (cell_h + gap)
                cell_rects[coord] = pygame.Rect(x, y, cell_w, cell_h)

    return LayoutMetrics(
        top_bar=top_bar,
        board_panel=board_panel,
        side_panel=side_panel,
        action_panel=action_panel,
        clues_panel=clues_panel,
        trace_panel=trace_panel,
        cell_rects=cell_rects,
        col_header_centers=col_centers,
        row_header_centers=row_centers,
    )


def draw_board(
    surface: pygame.Surface,
    layout: LayoutMetrics,
    public_state: PublicState,
    view: BoardViewState,
    avatars: AvatarManager | None,
) -> None:
    """Render the N×N board using only PublicState and presentation state."""
    pygame.draw.rect(surface, PANEL, layout.board_panel, border_radius=12)
    pygame.draw.rect(surface, BORDER, layout.board_panel, width=1, border_radius=12)

    for col_label, pos in layout.col_header_centers:
        draw_text(surface, col_label, pos, size=15, color=MUTED, bold=True, anchor="center")

    for row_label, pos in layout.row_header_centers:
        draw_text(surface, row_label, pos, size=15, color=MUTED, bold=True, anchor="center")

    chars_by_coord: dict[str, CharacterInfo] = {c.coord: c for c in public_state.characters}
    clues_by_coord = map_revealed_clues_to_coords(public_state)
    highlighted_set = set(view.highlighted_coords)
    hint_coord = view.active_hint.hint_coord if view.active_hint else None
    hint_clues = set(view.active_hint.relevant_clue_ids) if view.active_hint else set()

    for char in public_state.characters:
        coord = char.coord
        # Validate coord through models helper to keep canonical placement
        coord_to_rc(coord, public_state.size)
        base_rect = layout.cell_rects.get(coord)
        if base_rect is None:
            continue

        is_proved = coord in public_state.proved_verdicts
        verdict = public_state.proved_verdicts.get(coord)
        clue = clues_by_coord.get(coord)

        anim = view.flip_animations.get(coord)
        if anim is not None:
            draw_rect, show_front = anim.frame(base_rect)
        else:
            draw_rect = base_rect
            show_front = is_proved

        is_selected = view.selected_coord == coord
        is_clue_selected = clue is not None and view.selected_clue_id == clue.clue_id
        is_highlighted = coord in highlighted_set
        is_hint_target = hint_coord == coord
        is_hint_clue = clue is not None and clue.clue_id in hint_clues

        _draw_card(
            surface=surface,
            rect=draw_rect,
            full_rect=base_rect,
            char=char,
            grid_size=public_state.size,
            show_front=show_front,
            verdict=verdict,
            clue=clue,
            chars_by_coord=chars_by_coord,
            avatars=avatars,
            is_selected=is_selected,
            is_clue_selected=is_clue_selected,
            is_highlighted=is_highlighted,
            is_hint_target=is_hint_target,
            is_hint_clue=is_hint_clue,
        )


def _draw_card(
    *,
    surface: pygame.Surface,
    rect: pygame.Rect,
    full_rect: pygame.Rect,
    char: CharacterInfo,
    grid_size: int,
    show_front: bool,
    verdict: str | None,
    clue: Clue | None,
    chars_by_coord: dict[str, CharacterInfo],
    avatars: AvatarManager | None,
    is_selected: bool,
    is_clue_selected: bool,
    is_highlighted: bool,
    is_hint_target: bool,
    is_hint_clue: bool,
) -> None:
    if show_front and verdict == "CRIMINAL":
        fill = CARD_FRONT_CRIMINAL
    elif show_front and verdict == "INNOCENT":
        fill = CARD_FRONT_INNOCENT
    elif is_highlighted:
        fill = HIGHLIGHT_FILL
    else:
        fill = CARD_BACK

    border_color = BORDER
    border_width = 1
    if is_highlighted:
        border_color = WARNING
        border_width = 3
    if is_hint_clue or is_clue_selected:
        border_color = ACCENT_2
        border_width = 3
    if is_hint_target:
        border_color = ACCENT
        border_width = 3
    if is_selected:
        border_color = ACCENT
        border_width = 3

    pygame.draw.rect(surface, fill, rect, border_radius=10)
    pygame.draw.rect(surface, border_color, rect, width=border_width, border_radius=10)

    # While card is squeezed very thin mid-flip, skip inner content to avoid ugly clipping.
    if rect.width < max(36, int(full_rect.width * 0.42)):
        return

    compact = grid_size >= 5
    pad = 6 if compact else 9

    # Top header strip: coord badge + verdict/status pill
    coord_font = 12 if compact else 14
    draw_text(surface, char.coord, (rect.left + pad, rect.top + pad - 1), size=coord_font, color=MUTED, bold=True)

    if show_front and verdict is not None:
        badge_color = CRIMINAL if verdict == "CRIMINAL" else INNOCENT
        badge_label = "CRIM" if (compact and verdict == "CRIMINAL") else (
            "INNO" if (compact and verdict == "INNOCENT") else verdict
        )
        badge_font = 10 if compact else 11
        badge_rect = pygame.Rect(rect.right - (46 if compact else 72) - pad, rect.top + pad - 1, 46 if compact else 72, 18)
        pygame.draw.rect(surface, badge_color, badge_rect, border_radius=5)
        draw_text(surface, badge_label, badge_rect.center, size=badge_font, color=(12, 18, 26), bold=True, anchor="center")
    elif is_hint_target:
        badge_rect = pygame.Rect(rect.right - 46 - pad, rect.top + pad - 1, 46, 18)
        pygame.draw.rect(surface, ACCENT, badge_rect, border_radius=5)
        draw_text(surface, "HINT", badge_rect.center, size=10, color=(12, 18, 26), bold=True, anchor="center")
    elif is_highlighted:
        badge_rect = pygame.Rect(rect.right - 22 - pad, rect.top + pad - 1, 22, 18)
        pygame.draw.rect(surface, WARNING, badge_rect, border_radius=5)
        draw_text(surface, "*", badge_rect.center, size=13, color=(15, 18, 26), bold=True, anchor="center")

    if not show_front:
        _draw_face_down_body(surface, rect, char, avatars, compact, pad)
    else:
        _draw_face_up_body(surface, rect, char, clue, chars_by_coord, avatars, compact, pad)


def _draw_face_down_body(
    surface: pygame.Surface,
    rect: pygame.Rect,
    char: CharacterInfo,
    avatars: AvatarManager | None,
    compact: bool,
    pad: int,
) -> None:
    header_bottom = rect.top + (24 if compact else 28)
    name_h = 30 if compact else 38
    avatar_space_h = max(24, rect.bottom - header_bottom - name_h - pad)
    avatar_size = min(rect.width - pad * 2, avatar_space_h, 46 if compact else 78)

    avatar_bottom = header_bottom
    if avatars is not None and avatar_size >= 20:
        try:
            sprite = avatars.get(char.coord, (avatar_size, avatar_size))
            sprite_rect = sprite.get_rect(centerx=rect.centerx, top=header_bottom + 2)
            surface.blit(sprite, sprite_rect)
            avatar_bottom = sprite_rect.bottom
        except Exception:
            avatar_bottom = header_bottom + 4

    text_top = max(avatar_bottom + 2, rect.bottom - name_h - (2 if compact else 4))
    name_size = 12 if compact else 15
    occ_size = 10 if compact else 12
    draw_text_fitted(
        surface,
        char.name,
        (rect.centerx, text_top),
        rect.width - pad * 2,
        size=name_size,
        color=TEXT,
        bold=True,
        anchor="midtop",
    )
    draw_text_fitted(
        surface,
        char.occupation,
        (rect.centerx, text_top + (14 if compact else 18)),
        rect.width - pad * 2,
        size=occ_size,
        color=MUTED,
        bold=False,
        anchor="midtop",
    )


def _draw_face_up_body(
    surface: pygame.Surface,
    rect: pygame.Rect,
    char: CharacterInfo,
    clue: Clue | None,
    chars_by_coord: dict[str, CharacterInfo],
    avatars: AvatarManager | None,
    compact: bool,
    pad: int,
) -> None:
    row_top = rect.top + (23 if compact else 28)
    avatar_dim = 22 if compact else 32
    text_left = rect.left + pad

    if avatars is not None:
        try:
            sprite = avatars.get(char.coord, (avatar_dim, avatar_dim))
            surface.blit(sprite, (rect.left + pad, row_top))
            text_left = rect.left + pad + sprite.get_width() + 6
        except Exception:
            pass

    avail_name_w = max(30, rect.right - pad - text_left)
    draw_text_fitted(
        surface,
        char.name,
        (text_left, row_top),
        avail_name_w,
        size=11 if compact else 13,
        color=WHITE,
        bold=True,
    )
    draw_text_fitted(
        surface,
        char.occupation,
        (text_left, row_top + (12 if compact else 15)),
        avail_name_w,
        size=10 if compact else 11,
        color=MUTED,
    )

    clue_top = row_top + avatar_dim + (4 if compact else 6)
    clue_rect = pygame.Rect(
        rect.left + pad,
        clue_top,
        max(20, rect.width - pad * 2),
        max(14, rect.bottom - clue_top - pad),
    )
    pygame.draw.line(surface, BORDER, (rect.left + pad, clue_top - 3), (rect.right - pad, clue_top - 3), 1)

    if clue is not None:
        clue_text = format_clue_text(clue, chars_by_coord)
        draw_wrapped(
            surface,
            clue_text,
            clue_rect,
            size=10 if compact else 12,
            color=TEXT,
            bold=False,
            line_gap=2 if compact else 3,
        )


def draw_revealed_clues_panel(
    surface: pygame.Surface,
    panel_rect: pygame.Rect,
    public_state: PublicState,
    view: BoardViewState,
) -> list[tuple[pygame.Rect, Clue]]:
    """Draw scrollable revealed clues panel and return clickable ``(rect, Clue)`` rows."""
    pygame.draw.rect(surface, PANEL, panel_rect, border_radius=12)
    pygame.draw.rect(surface, BORDER, panel_rect, width=1, border_radius=12)

    title = f"Revealed Clues ({len(public_state.revealed_clues)})"
    draw_text(surface, title, (panel_rect.left + 12, panel_rect.top + 10), size=15, color=TEXT, bold=True)
    draw_text(
        surface,
        "Click clue to highlight",
        (panel_rect.right - 12, panel_rect.top + 12),
        size=11,
        color=MUTED,
        anchor="topright",
    )

    list_area = pygame.Rect(
        panel_rect.left + 10,
        panel_rect.top + 36,
        panel_rect.width - 20,
        max(20, panel_rect.height - 46),
    )

    if not public_state.revealed_clues:
        draw_text(surface, "No clues revealed yet.", (list_area.left + 4, list_area.top + 6), size=13, color=MUTED)
        return []

    chars_by_coord = {c.coord: c for c in public_state.characters}
    hint_clues = set(view.active_hint.relevant_clue_ids) if view.active_hint else set()
    clickable: list[tuple[pygame.Rect, Clue]] = []

    item_h = 46
    gap = 6
    total_h = len(public_state.revealed_clues) * (item_h + gap)
    max_scroll = max(0, total_h - list_area.height)
    view.clue_scroll = max(0, min(view.clue_scroll, max_scroll))

    prev_clip = surface.get_clip()
    surface.set_clip(list_area)

    y = list_area.top - view.clue_scroll
    for clue in public_state.revealed_clues:
        item_rect = pygame.Rect(list_area.left, y, list_area.width, item_h)
        if item_rect.bottom >= list_area.top and item_rect.top <= list_area.bottom:
            is_active = view.selected_clue_id == clue.clue_id
            is_hinted = clue.clue_id in hint_clues
            bg = (49, 60, 92) if is_active else ((41, 66, 67) if is_hinted else PANEL_2)
            border = WARNING if is_active else (ACCENT if is_hinted else BORDER)
            pygame.draw.rect(surface, bg, item_rect, border_radius=8)
            pygame.draw.rect(surface, border, item_rect, width=2 if (is_active or is_hinted) else 1, border_radius=8)

            header_tag = f"[{clue.clue_id}]"
            if is_hinted:
                header_tag += " HINT"
            draw_text(
                surface,
                header_tag,
                (item_rect.left + 8, item_rect.top + 4),
                size=11,
                color=ACCENT if is_hinted else WARNING if is_active else MUTED,
                bold=True,
            )
            clue_str = format_clue_text(clue, chars_by_coord)
            draw_text_fitted(
                surface,
                clue_str,
                (item_rect.left + 8, item_rect.top + 22),
                item_rect.width - 16,
                size=12,
                color=TEXT,
            )
            clipped_hit = item_rect.clip(list_area)
            if clipped_hit.height > 4:
                clickable.append((clipped_hit, clue))
        y += item_h + gap

    surface.set_clip(prev_clip)
    return clickable


def draw_trace_panel(
    surface: pygame.Surface,
    panel_rect: pygame.Rect,
    view: BoardViewState,
    agent_ready: bool,
) -> None:
    """Draw scrollable DeductionStep trace panel."""
    pygame.draw.rect(surface, PANEL, panel_rect, border_radius=12)
    pygame.draw.rect(surface, BORDER, panel_rect, width=1, border_radius=12)

    title = f"Deduction Trace ({len(view.trace)})"
    draw_text(surface, title, (panel_rect.left + 12, panel_rect.top + 10), size=15, color=TEXT, bold=True)

    list_area = pygame.Rect(
        panel_rect.left + 10,
        panel_rect.top + 36,
        panel_rect.width - 20,
        max(20, panel_rect.height - 46),
    )

    if not view.trace:
        msg = (
            "Run Auto Solve to record deduction steps."
            if agent_ready
            else "LogicAgent not ready (src/agent.py pending)."
        )
        draw_wrapped(surface, msg, list_area, size=12, color=MUTED, line_gap=4)
        return

    item_h = 46
    gap = 6
    total_h = len(view.trace) * (item_h + gap)
    max_scroll = max(0, total_h - list_area.height)
    view.trace_scroll = max(0, min(view.trace_scroll, max_scroll))

    prev_clip = surface.get_clip()
    surface.set_clip(list_area)

    y = list_area.top - view.trace_scroll
    for step in view.trace:
        item_rect = pygame.Rect(list_area.left, y, list_area.width, item_h)
        if item_rect.bottom >= list_area.top and item_rect.top <= list_area.bottom:
            pygame.draw.rect(surface, PANEL_2, item_rect, border_radius=8)
            pygame.draw.rect(surface, BORDER, item_rect, width=1, border_radius=8)

            v_color = CRIMINAL if step.verdict == "CRIMINAL" else INNOCENT
            line1 = f"#{step.step}  {step.target_coord} -> {step.verdict}"
            draw_text_fitted(
                surface,
                line1,
                (item_rect.left + 8, item_rect.top + 5),
                item_rect.width - 16,
                size=12,
                color=v_color,
                bold=True,
            )
            reveal_str = step.newly_revealed_clue_id or "-"
            line2 = f"Clues: {len(step.active_clue_ids)} | SAT calls: {step.sat_calls} | +{reveal_str}"
            draw_text_fitted(
                surface,
                line2,
                (item_rect.left + 8, item_rect.top + 24),
                item_rect.width - 16,
                size=11,
                color=MUTED,
            )
        y += item_h + gap

    surface.set_clip(prev_clip)


def draw_puzzle_picker_overlay(
    surface: pygame.Surface,
    puzzle_files: list[Path],
    current_puzzle_path: Path | None,
    error_message: str = "",
) -> tuple[list[tuple[pygame.Rect, Path]], pygame.Rect | None]:
    """Draw the Load Puzzle modal overlay and return clickable items and optional close rect."""
    width, height = surface.get_size()
    dim = pygame.Surface((width, height), pygame.SRCALPHA)
    dim.fill((9, 13, 22, 210))
    surface.blit(dim, (0, 0))

    modal_w = min(560, width - 60)
    modal_h = min(520, height - 80)
    modal = pygame.Rect((width - modal_w) // 2, (height - modal_h) // 2, modal_w, modal_h)

    pygame.draw.rect(surface, PANEL, modal, border_radius=14)
    pygame.draw.rect(surface, ACCENT, modal, width=2, border_radius=14)

    draw_text(surface, "Select Puzzle (src/puzzles/)", (modal.left + 20, modal.top + 18), size=20, color=TEXT, bold=True)
    draw_text(
        surface,
        "Puzzles are loaded strictly via GameEngine.",
        (modal.left + 20, modal.top + 46),
        size=13,
        color=MUTED,
    )

    close_rect: pygame.Rect | None = None
    if current_puzzle_path is not None:
        close_rect = pygame.Rect(modal.right - 88, modal.top + 18, 68, 32)
        pygame.draw.rect(surface, PANEL_2, close_rect, border_radius=8)
        pygame.draw.rect(surface, BORDER, close_rect, width=1, border_radius=8)
        draw_text(surface, "Close", close_rect.center, size=14, color=TEXT, bold=True, anchor="center")

    y = modal.top + 78
    if error_message:
        err_rect = pygame.Rect(modal.left + 20, y, modal.width - 40, 34)
        pygame.draw.rect(surface, (74, 30, 39), err_rect, border_radius=8)
        draw_text_fitted(surface, error_message, (err_rect.left + 10, err_rect.top + 8), err_rect.width - 20, size=13, color=CRIMINAL)
        y += 44

    clickable: list[tuple[pygame.Rect, Path]] = []
    if not puzzle_files:
        draw_text(
            surface,
            "No .json puzzle files found in src/puzzles/.",
            (modal.left + 20, y + 10),
            size=15,
            color=WARNING,
        )
        return clickable, close_rect

    row_h = 48
    gap = 10
    for path in puzzle_files:
        if y + row_h > modal.bottom - 18:
            break
        row_rect = pygame.Rect(modal.left + 20, y, modal.width - 40, row_h)
        is_current = current_puzzle_path is not None and path.resolve() == current_puzzle_path.resolve()
        pygame.draw.rect(surface, (42, 62, 82) if is_current else PANEL_2, row_rect, border_radius=10)
        pygame.draw.rect(surface, ACCENT if is_current else BORDER, row_rect, width=2 if is_current else 1, border_radius=10)

        draw_text_fitted(
            surface,
            path.stem,
            (row_rect.left + 14, row_rect.top + 8),
            row_rect.width - 110,
            size=16,
            color=WHITE,
            bold=True,
        )
        draw_text_fitted(
            surface,
            path.name,
            (row_rect.left + 14, row_rect.top + 28),
            row_rect.width - 110,
            size=12,
            color=MUTED,
        )
        tag = "LOADED" if is_current else "OPEN"
        draw_text(
            surface,
            tag,
            (row_rect.right - 16, row_rect.centery),
            size=13,
            color=ACCENT if is_current else TEXT,
            bold=True,
            anchor="midright",
        )
        clickable.append((row_rect, path))
        y += row_h + gap

    return clickable, close_rect
