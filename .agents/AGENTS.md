AGENTS.md — Griductive Solver

Guidelines for AI coding agents and contributors working on Griductive-Solver (CSC14003 — Introduction to Artificial Intelligence, Project 2, VNUHCM-US).

1. Project Overview

Goal: Build a no-guess Griductive puzzle game and deductive solver using propositional logic, automatic CNF encoding, and a custom DPLL SAT solver.

Tech Stack: Python 3.11+, GUI three.js, all code inside `src/`

Documentation: Full Vietnamese specification and team task breakdown live in docs/Project 2 - Griductive Solver (Bản Việt hóa).md.

2. Repository Structure
```
Griductive-Solver/
├── docs/
│   └── Project 2 - Griductive Solver (Bản Việt hóa).md
├── Source/
│   ├── main.py              # GUI entry point
│   ├── models.py            # Shared schemas & resolve_region()
│   ├── game_engine.py       # GameEngine & Direct Semantic Evaluator
│   ├── encoder.py           # Variable map, validator & CNF encoder
│   ├── dpll.py              # Pure-Python DPLL SAT solver & metrics
│   ├── agent.py             # Deductive Logic Agent (entailment, loop, hint, uniqueness)
│   ├── puzzles/             # 3x3, 4x4, 5x5 JSON puzzle files
│   ├── experiments/         # Benchmark runner & plotting scripts
│   ├── tests/               # Unit & integration tests
│   ├── requirements.txt     # Exported from uv before submission
│   └── README.md
├── .gitignore
├── LICENSE
└── README.md
```

3. Non-Negotiable Rules & Constraints

Pure-Python Algorithms Only (No External SAT Libraries in Runtime):

You MUST implement CNF encoding (encoder.py) and the DPLL SAT solver (dpll.py) from scratch in Python.

NEVER import pysat, z3, or any external SAT/CSP solver inside Source/ runtime modules. External solvers may only be used in Source/tests/ as reference oracles.

No Hardcoded CNF:

Never hardcode CNF clauses for specific puzzles. All active clues must be dynamically validated and encoded into CNF.

Strict Information Hiding (GameEngine vs. LogicAgent):

GameEngine owns the full puzzle, hidden_status, and unrevealed clues.

PublicState exposed to LogicAgent and the GUI MUST NEVER contain hidden_status or unrevealed clues.

Hint, Auto Solve, and verdict checking (ENTAILED, NOT_PROVABLE, CONTRADICTED, INCONSISTENT) must rely solely on LogicAgent reasoning over PublicState.

Independent Direct Semantic Evaluator:

evaluate_clue(clue, assignment) in game_engine.py must evaluate clues directly against a complete assignment without calling encoder.py.

Single Source of Truth (models.py):

All modules (game_engine.py, encoder.py, GUI highlight) must import shared schemas (Puzzle, Clue, PublicState, CNFFormula, SolverResult, VerdictResponse, HintResponse, DeductionStep) and resolve_region(region, size) from models.py.

Never duplicate coordinate or region resolution logic across files.

Determinism:

Primary Boolean variables C_i must be mapped deterministically and kept strictly separate from auxiliary variables.

DPLL variable selection and tie-breaking in the deduction loop (e.g., row-major order) must be deterministic.

4. Supported Clue Language

Regions: ROW, COL, NEIGHBORS (8-directional, excluding self), EXPLICIT (list of distinct cell coords).

6 Core Templates: FACT, SAME, DIFFERENT, EXACTLY, AT_LEAST, AT_MOST.

2 Team Extensions: PARITY (EVEN / ODD), COMPARE_COUNT (GT / LT / EQ).

5. Coding & Collaboration Conventions

Use Python 3.11+ type annotations (dataclass, Literal, list[str], dict[str, ...]).

When modifying any schema in models.py, immediately check and update all consumers (game_engine.py, encoder.py, dpll.py, agent.py, main.py, tests/).

Keep all tests passing (uv run pytest) before pushing to main or merging pull requests.

Do not commit .venv/, __pycache__/, or temporary CSV/plot artifacts unless explicitly needed for docs/ or Report.pdf.