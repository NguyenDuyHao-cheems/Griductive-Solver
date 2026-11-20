"""Shared data schemas and region-resolution utilities for Griductive Solver.

Single source of truth imported by GameEngine, Direct Semantic Evaluator,
CNF Encoder & Validator, DPLL SAT Solver, Deductive Logic Agent, and GUI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Status = Literal["CRIMINAL", "INNOCENT"]
EntailmentStatus = Literal["CRIMINAL", "INNOCENT", "UNKNOWN", "INCONSISTENT"]
VerdictReason = Literal["ENTAILED", "NOT_PROVABLE", "CONTRADICTED", "INCONSISTENT"]
SolverStatus = Literal["SAT", "UNSAT"]
UniquenessStatus = Literal["UNIQUE", "MULTIPLE", "UNSAT"]

RegionKind = Literal["ROW", "COL", "NEIGHBORS", "EXPLICIT"]
ClueType = Literal[
    # 6 required core templates
    "FACT",
    "SAME",
    "DIFFERENT",
    "EXACTLY",
    "AT_LEAST",
    "AT_MOST",
    # 2 team extensions
    "PARITY",
    "COMPARE_COUNT",
]
ParityKind = Literal["EVEN", "ODD"]
CompareOp = Literal["GT", "LT", "EQ"]


# ---------------------------------------------------------------------------
# Coordinate & Region helpers
# ---------------------------------------------------------------------------

def coord_to_rc(coord: str, size: int) -> tuple[int, int]:
    """Convert a cell coordinate like 'C2' to 0-indexed (row, col).

    Columns are letters A..E (left to right -> col 0..size-1).
    Rows are 1-indexed numbers 1..size (top to bottom -> row 0..size-1).
    """
    if not isinstance(coord, str) or len(coord) < 2:
        raise ValueError(f"Invalid coordinate format: {coord!r}")

    col_char = coord[0].upper()
    row_str = coord[1:]
    if not col_char.isalpha() or not row_str.isdigit():
        raise ValueError(f"Invalid coordinate format: {coord!r}")

    col = ord(col_char) - ord("A")
    row = int(row_str) - 1
    if not (0 <= row < size and 0 <= col < size):
        raise ValueError(f"Coordinate {coord!r} out of bounds for {size}x{size} grid.")
    return row, col


def rc_to_coord(row: int, col: int, size: int) -> str:
    """Convert 0-indexed (row, col) to a cell coordinate like 'C2'."""
    if not (0 <= row < size and 0 <= col < size):
        raise ValueError(f"Position ({row}, {col}) out of bounds for {size}x{size} grid.")
    return f"{chr(ord('A') + col)}{row + 1}"


def all_coords(size: int) -> list[str]:
    """Return all grid coordinates in deterministic row-major order."""
    return [rc_to_coord(r, c, size) for r in range(size) for c in range(size)]


# ---------------------------------------------------------------------------
# Core Data Schemas
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Region:
    """Structured clue region specification."""

    kind: RegionKind
    target: int | str | None = None
    cells: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Region:
        kind = data["kind"]
        target = data.get("target")
        raw_cells = data.get("cells") or ()
        return cls(kind=kind, target=target, cells=tuple(raw_cells))

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"kind": self.kind}
        if self.target is not None:
            result["target"] = self.target
        if self.cells:
            result["cells"] = list(self.cells)
        return result


def resolve_region(region: Region | dict[str, Any], size: int) -> list[str]:
    """Resolve a Region into a deterministic list of distinct cell coordinates.

    Shared by Validator/Encoder, Direct Semantic Evaluator, and GUI Highlight.

    Supported kinds:
    - ROW: target is 0-indexed row int (e.g. 0 -> row 1: ['A1', 'B1', ...]).
    - COL: target is column letter str (e.g. 'A' -> ['A1', 'A2', ...]).
    - NEIGHBORS: target is cell coord str (e.g. 'C2'); returns up to 8 adjacent
      cells (orthogonal + diagonal), excluding the target cell itself.
    - EXPLICIT: cells is a non-empty list of distinct valid coordinates.
    """
    if size <= 0:
        raise ValueError(f"Grid size must be positive, got {size}.")

    reg = region if isinstance(region, Region) else Region.from_dict(region)

    if reg.kind == "ROW":
        if not isinstance(reg.target, int) or isinstance(reg.target, bool):
            raise ValueError(f"ROW target must be a 0-indexed int, got {reg.target!r}.")
        if not (0 <= reg.target < size):
            raise ValueError(f"ROW target {reg.target} out of bounds for size {size}.")
        return [rc_to_coord(reg.target, c, size) for c in range(size)]

    if reg.kind == "COL":
        if not isinstance(reg.target, str) or len(reg.target) != 1 or not reg.target.isalpha():
            raise ValueError(f"COL target must be a single letter, got {reg.target!r}.")
        col = ord(reg.target.upper()) - ord("A")
        if not (0 <= col < size):
            raise ValueError(f"COL target {reg.target!r} out of bounds for size {size}.")
        return [rc_to_coord(r, col, size) for r in range(size)]

    if reg.kind == "NEIGHBORS":
        if not isinstance(reg.target, str):
            raise ValueError(f"NEIGHBORS target must be a coord str, got {reg.target!r}.")
        r0, c0 = coord_to_rc(reg.target, size)
        neighbors: list[str] = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r0 + dr, c0 + dc
                if 0 <= nr < size and 0 <= nc < size:
                    neighbors.append(rc_to_coord(nr, nc, size))
        return neighbors

    if reg.kind == "EXPLICIT":
        if not reg.cells:
            raise ValueError("EXPLICIT region must contain at least one cell.")
        seen: set[str] = set()
        resolved: list[str] = []
        for cell in reg.cells:
            r, c = coord_to_rc(cell, size)
            canonical = rc_to_coord(r, c, size)
            if canonical in seen:
                raise ValueError(f"Duplicate cell {canonical!r} in EXPLICIT region.")
            seen.add(canonical)
            resolved.append(canonical)
        return resolved

    raise ValueError(f"Unsupported region kind: {reg.kind!r}")


@dataclass(frozen=True)
class Clue:
    """Structured clue attached to a character card.

    Fields used per clue type:
    - FACT: target, status
    - SAME / DIFFERENT: a, b
    - EXACTLY / AT_LEAST / AT_MOST: region, k
    - PARITY: region, parity ('EVEN' | 'ODD')
    - COMPARE_COUNT: r1, op ('GT' | 'LT' | 'EQ'), r2
    """

    clue_id: str
    type: ClueType
    # FACT
    target: str | None = None
    status: Status | None = None
    # SAME / DIFFERENT
    a: str | None = None
    b: str | None = None
    # EXACTLY / AT_LEAST / AT_MOST / PARITY
    region: Region | None = None
    k: int | None = None
    parity: ParityKind | None = None
    # COMPARE_COUNT
    r1: Region | None = None
    op: CompareOp | None = None
    r2: Region | None = None
    # Optional natural-language rendering for GUI display
    text: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Clue:
        return cls(
            clue_id=data["clue_id"],
            type=data["type"],
            target=data.get("target"),
            status=data.get("status"),
            a=data.get("a"),
            b=data.get("b"),
            region=Region.from_dict(data["region"]) if data.get("region") else None,
            k=data.get("k"),
            parity=data.get("parity"),
            r1=Region.from_dict(data["r1"]) if data.get("r1") else None,
            op=data.get("op"),
            r2=Region.from_dict(data["r2"]) if data.get("r2") else None,
            text=data.get("text"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"clue_id": self.clue_id, "type": self.type}
        for key in ("target", "status", "a", "b", "k", "parity", "op", "text"):
            val = getattr(self, key)
            if val is not None:
                out[key] = val
        if self.region is not None:
            out["region"] = self.region.to_dict()
        if self.r1 is not None:
            out["r1"] = self.r1.to_dict()
        if self.r2 is not None:
            out["r2"] = self.r2.to_dict()
        return out


@dataclass(frozen=True)
class CharacterInfo:
    """Public character metadata visible on the board (never includes hidden state)."""

    coord: str
    name: str
    occupation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "coord": self.coord,
            "name": self.name,
            "occupation": self.occupation,
        }


@dataclass(frozen=True)
class PuzzleCell:
    """Full cell definition held exclusively by GameEngine."""

    coord: str
    row: int
    col: int
    name: str
    occupation: str
    hidden_status: Status
    clue: Clue

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PuzzleCell:
        return cls(
            coord=data["coord"],
            row=data["row"],
            col=data["col"],
            name=data["name"],
            occupation=data["occupation"],
            hidden_status=data["hidden_status"],
            clue=Clue.from_dict(data["clue"]),
        )

    def to_public_character(self) -> CharacterInfo:
        return CharacterInfo(
            coord=self.coord,
            name=self.name,
            occupation=self.occupation,
        )


@dataclass(frozen=True)
class Puzzle:
    """Full puzzle definition (loaded and owned only by GameEngine)."""

    puzzle_id: str
    size: int
    initial_revealed: tuple[str, ...]
    cells: tuple[PuzzleCell, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Puzzle:
        return cls(
            puzzle_id=data["puzzle_id"],
            size=data["size"],
            initial_revealed=tuple(data["initial_revealed"]),
            cells=tuple(PuzzleCell.from_dict(c) for c in data["cells"]),
        )

    def cell_map(self) -> dict[str, PuzzleCell]:
        return {cell.coord: cell for cell in self.cells}


@dataclass
class PublicState:
    """Public knowledge base state exposed by GameEngine to LogicAgent & GUI.

    MUST NEVER contain hidden_status or unrevealed clues.
    """

    size: int
    characters: list[CharacterInfo]
    proved_verdicts: dict[str, Status] = field(default_factory=dict)
    revealed_clues: list[Clue] = field(default_factory=list)
    unsolved_coords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "size": self.size,
            "characters": [c.to_dict() for c in self.characters],
            "proved_verdicts": dict(self.proved_verdicts),
            "revealed_clues": [c.to_dict() for c in self.revealed_clues],
            "unsolved_coords": list(self.unsolved_coords),
        }


# ---------------------------------------------------------------------------
# Encoder & DPLL Schemas
# ---------------------------------------------------------------------------

@dataclass
class CNFFormula:
    """CNF knowledge base produced by encoder.py for dpll.py."""

    num_primary_vars: int
    num_aux_vars: int
    var_map: dict[str, int]
    clauses: list[list[int]]

    @property
    def num_clauses(self) -> int:
        return len(self.clauses)

    @property
    def total_vars(self) -> int:
        return self.num_primary_vars + self.num_aux_vars


@dataclass
class SolverResult:
    """Output and performance metrics returned by dpll.py."""

    status: SolverStatus
    assignment: dict[int, bool] | None = None
    decisions: int = 0
    propagations: int = 0
    backtracks: int = 0
    runtime_ms: float = 0.0


# ---------------------------------------------------------------------------
# Logic Agent -> GameEngine / GUI Schemas
# ---------------------------------------------------------------------------

@dataclass
class VerdictResponse:
    """Result of submitting a verdict for a character."""

    accepted: bool
    reason: VerdictReason
    revealed_clue: Clue | None = None


@dataclass
class HintResponse:
    """Actionable hint derived purely from PublicState."""

    hint_coord: str | None = None
    verdict: Status | None = None
    relevant_clue_ids: list[str] = field(default_factory=list)


@dataclass
class DeductionStep:
    """Single step in the agent's no-guess deduction trace."""

    step: int
    active_clue_ids: list[str]
    sat_queries: list[str]
    sat_calls: int
    target_coord: str
    verdict: Status
    newly_revealed_clue_id: str | None = None