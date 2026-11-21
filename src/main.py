"""GUI entry point for Griductive Solver (Khoa — Section 4.1)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the Griductive Solver Pygame GUI.")
    parser.add_argument(
        "--puzzle",
        type=Path,
        default=None,
        help="Optional path to a puzzle JSON file to open immediately.",
    )
    parser.add_argument(
        "--puzzles-dir",
        type=Path,
        default=SRC_DIR / "puzzles",
        help="Directory containing puzzle JSON files (default: src/puzzles).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    try:
        import pygame  # noqa: F401
    except ImportError:
        print(
            "Error: pygame is not installed.\n"
            "Install dependencies inside your virtual environment with:\n"
            "    pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    from ui.app import GriductiveApp

    app = GriductiveApp(
        puzzles_dir=args.puzzles_dir,
        initial_puzzle=args.puzzle,
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
