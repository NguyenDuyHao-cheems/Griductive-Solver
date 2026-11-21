"""Presentation helpers for clues, regions, and puzzle discovery.

Strictly operates on PublicState, Clue, and GameEngine's public API.
Never inspects hidden_status, PuzzleCell, or raw puzzle JSON contents.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from game_engine import GameEngine
from models import CharacterInfo, Clue, PublicState, Region, resolve_region


def discover_puzzle_files(puzzles_dir: Path) -> list[Path]:
    """Return sorted JSON puzzle paths inside ``puzzles_dir`` without reading them."""
    if not puzzles_dir.is_dir():
        return []
    return sorted(
        (p for p in puzzles_dir.glob("*.json") if p.is_file()),
        key=lambda p: p.name.lower(),
    )


def map_revealed_clues_to_coords(public_state: PublicState) -> dict[str, Clue]:
    """Map each revealed coordinate in ``public_state`` to its revealed Clue.

    Uses PublicState alone: GameEngine appends to ``proved_verdicts`` and
    ``revealed_clues`` in lockstep order.
    """
    proved_coords = list(public_state.proved_verdicts.keys())
    clues = list(public_state.revealed_clues)
    mapping: dict[str, Clue] = {}

    if len(proved_coords) == len(clues):
        for coord, clue in zip(proved_coords, clues):
            mapping[coord] = clue
        return mapping

    # Fallback: match by canonical clue_id convention "clue_<COORD>" if lengths differ.
    valid_coords = set(proved_coords)
    for clue in clues:
        suffix = clue.clue_id.removeprefix("clue_")
        if suffix in valid_coords and suffix not in mapping:
            mapping[suffix] = clue
    return mapping


def get_clue_highlight_coords(engine: GameEngine, clue: Clue) -> list[str]:
    """Return highlighted cell coordinates for a revealed clue.

    Prefers ``GameEngine.get_clue_highlight_cells(clue_id)``, which enforces
    information hiding and delegates to ``models.resolve_region()``.
    """
    try:
        return engine.get_clue_highlight_cells(clue.clue_id)
    except ValueError:
        return []


def resolve_clue_regions_fallback(clue: Clue, size: int) -> list[str]:
    """Fallback region resolution using ``models.resolve_region()`` directly."""
    cells: list[str] = []
    if clue.type == "FACT" and clue.target:
        cells.append(clue.target)
    elif clue.type in ("SAME", "DIFFERENT"):
        if clue.a:
            cells.append(clue.a)
        if clue.b:
            cells.append(clue.b)
    elif clue.type in ("EXACTLY", "AT_LEAST", "AT_MOST", "PARITY") and clue.region is not None:
        cells.extend(resolve_region(clue.region, size))
    elif clue.type == "COMPARE_COUNT":
        if clue.r1 is not None:
            cells.extend(resolve_region(clue.r1, size))
        if clue.r2 is not None:
            cells.extend(resolve_region(clue.r2, size))

    seen: set[str] = set()
    unique: list[str] = []
    for coord in cells:
        if coord not in seen:
            seen.add(coord)
            unique.append(coord)
    return unique


def format_region_label(region: Region) -> str:
    """Format a structured Region into a compact human-readable label."""
    if region.kind == "ROW":
        row_num = int(region.target) + 1 if region.target is not None else "?"
        return f"row {row_num}"
    if region.kind == "COL":
        return f"col {region.target}"
    if region.kind == "NEIGHBORS":
        return f"neighbors of {region.target}"
    if region.kind == "EXPLICIT":
        return ", ".join(region.cells)
    return str(region.kind)


def format_clue_text(
    clue: Clue,
    characters: Mapping[str, CharacterInfo] | None = None,
) -> str:
    """Return display text for a revealed Clue, falling back to structured formatting."""
    if clue.text:
        return clue.text

    def label(coord: str | None) -> str:
        if not coord:
            return "?"
        if characters and coord in characters:
            return f"{characters[coord].name} ({coord})"
        return coord

    ctype = clue.type
    if ctype == "FACT":
        status_word = "a criminal" if clue.status == "CRIMINAL" else "innocent"
        return f"{label(clue.target)} is {status_word}."
    if ctype == "SAME":
        return f"{label(clue.a)} and {label(clue.b)} have the same status."
    if ctype == "DIFFERENT":
        return f"{label(clue.a)} and {label(clue.b)} have different statuses."
    if ctype == "EXACTLY" and clue.region is not None:
        return f"Exactly {clue.k} criminal(s) in {format_region_label(clue.region)}."
    if ctype == "AT_LEAST" and clue.region is not None:
        return f"At least {clue.k} criminal(s) in {format_region_label(clue.region)}."
    if ctype == "AT_MOST" and clue.region is not None:
        return f"At most {clue.k} criminal(s) in {format_region_label(clue.region)}."
    if ctype == "PARITY" and clue.region is not None:
        parity_word = "even" if clue.parity == "EVEN" else "odd"
        return f"Number of criminals in {format_region_label(clue.region)} is {parity_word}."
    if ctype == "COMPARE_COUNT" and clue.r1 is not None and clue.r2 is not None:
        op_map = {"GT": "more criminals than", "LT": "fewer criminals than", "EQ": "as many criminals as"}
        op_text = op_map.get(clue.op or "", str(clue.op))
        return f"{format_region_label(clue.r1)} has {op_text} {format_region_label(clue.r2)}."
    return f"{clue.clue_id}: {clue.type}"
