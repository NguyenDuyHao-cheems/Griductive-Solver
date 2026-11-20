"""Deterministic propositional variables and structured clue validation."""

from __future__ import annotations

if __package__:
    from .models import Clue, PublicState, Region, all_coords, coord_to_rc, resolve_region
else:
    from models import Clue, PublicState, Region, all_coords, coord_to_rc, resolve_region


def build_var_map(state: PublicState) -> tuple[dict[str, int], dict[int, str]]:
    """Return coordinate-to-ID and ID-to-coordinate maps in row-major order.

    For a complete board, primary IDs are 1 through size**2. Auxiliary IDs
    start above that range.
    """
    _validate_grid_size(state.size)
    coords = all_coords(state.size)
    character_coords = [character.coord for character in state.characters]
    if len(character_coords) != len(coords) or set(character_coords) != set(coords):
        raise ValueError("PublicState.characters must contain one character per grid cell.")

    coord_by_var = dict(enumerate(coords, start=1))
    var_map = {coord: var_id for var_id, coord in coord_by_var.items()}
    return var_map, coord_by_var


def validate_clue(clue: Clue, size: int) -> bool:
    """Return True for a well-formed clue or raise ValueError with its ID."""
    try:
        _validate_grid_size(size)
        match clue.type:
            case "FACT":
                _validate_coord(clue.target, size, "target")
                if clue.status not in ("CRIMINAL", "INNOCENT"):
                    raise ValueError(f"status must be CRIMINAL or INNOCENT, got {clue.status!r}.")
            case "SAME" | "DIFFERENT":
                _validate_coord(clue.a, size, "a")
                _validate_coord(clue.b, size, "b")
            case "EXACTLY" | "AT_LEAST" | "AT_MOST":
                region_size = _region_size(clue.region, size, "region")
                k = clue.k
                if not isinstance(k, int) or isinstance(k, bool) or not 0 <= k <= region_size:
                    raise ValueError(f"k must be an integer from 0 to {region_size}, got {k!r}.")
            case "PARITY":
                _region_size(clue.region, size, "region")
                if clue.parity not in ("EVEN", "ODD"):
                    raise ValueError(f"parity must be EVEN or ODD, got {clue.parity!r}.")
            case "COMPARE_COUNT":
                _region_size(clue.r1, size, "r1")
                _region_size(clue.r2, size, "r2")
                if clue.op not in ("GT", "LT", "EQ"):
                    raise ValueError(f"op must be GT, LT, or EQ, got {clue.op!r}.")
            case _:
                raise ValueError(f"unsupported clue type {clue.type!r}.")
    except ValueError as error:
        raise ValueError(f"Clue {clue.clue_id!r}: {error}") from error
    return True


def _validate_grid_size(size: int) -> None:
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ValueError(f"Grid size must be a positive integer, got {size!r}.")


def _validate_coord(coord: str | None, size: int, field: str) -> None:
    if not isinstance(coord, str):
        raise ValueError(f"{field} must be a cell coordinate, got {coord!r}.")
    try:
        coord_to_rc(coord, size)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field}: {error}") from error


def _region_size(region: Region | None, size: int, field: str) -> int:
    if not isinstance(region, Region):
        raise ValueError(f"{field} must be a Region, got {region!r}.")
    try:
        coords = resolve_region(region, size)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field}: {error}") from error
    if not coords:
        raise ValueError(f"{field} must contain at least one cell.")
    return len(coords)
