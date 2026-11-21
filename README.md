# Griductive Solver

Project 2 for CSC14003: a no-guess deduction game on an N×N grid. The shared
data contracts are in `src/models.py`; `src/game_engine.py` owns the puzzle
and exposes only public game state to the interface and logic agent.

## Khoa's Work: GUI and Experiment Presentation

Khoa is responsible for the playable GUI, clue highlighting, Load/Restart/Hint/
Auto Solve controls, deduction trace display, experiment charts and analysis,
and the demonstration video. The GUI renders only `PublicState` and uses
`GameEngine.get_clue_highlight_cells()` / `models.resolve_region()` for clue
regions. It never inspects hidden statuses, unrevealed clues, or raw puzzle JSON.

### Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Launching the GUI

```powershell
python src/main.py
```

Optional: open a specific puzzle directly on launch (or pass `--puzzles-dir <dir>`):

```powershell
python src/main.py --puzzle src/puzzles/sample_3x3.json
```

**Current integration status:**

- **Working now:** Puzzle picker (`src/puzzles/`), loading and restarting via `GameEngine`, 3×3–5×5 responsive board rendering with avatars (`src/assets/sprites/avatars/`), face-down/face-up cards, `CardFlipAnimation`, and clue region highlighting.
- **Pending `src/agent.py`:** Verdict submission (`CRIMINAL`/`INNOCENT`), `Hint`, `Auto Solve`, and `DeductionStep` trace are wired through `src/ui/agent_adapter.py` (passing `PublicState` only) and stay disabled with a clear status notice until `LogicAgent` is implemented in `src/agent.py`.

### Generating Benchmark Charts and Tables

Once `benchmark_results.csv` is produced by the benchmark runner:

```powershell
python src/experiments/plot_results.py --input benchmark_results.csv --output assets
```

This generates `assets/benchmark_summary.md` and four PNG charts (`chart_1_cnf_size.png` through `chart_4_size_scaling.png`) covering all six required metric groups while retaining and clearly marking `TIMEOUT`, `FAILED`, `UNKNOWN`, and `MISSING_STATUS` rows. Missing numeric values are shown as `-` in tables and left blank (`NaN`) in charts, not drawn as zero.

### Running Tests

```powershell
pytest src/tests
```

Khoa's scope, progress, and design decisions are tracked in `docs/KHOA.md`.
