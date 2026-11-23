# Griductive Solver — Source

Source code, puzzles, tests, and GUI assets live in this directory.

For setup and project-wide instructions, see the [root README](../README.md).

## Module Layout

- `main.py`: Entry point for launching the Pygame desktop GUI.
- `models.py`: Shared data schemas (dataclasses) and `resolve_region()` coordinate resolver.
- `game_engine.py`: GameEngine, state lifecycle, and independent Direct Semantic Evaluator.
- `encoder.py`: Variable mapping, clue validation, and automatic CNF encoding.
- `dpll.py`: Pure-Python DPLL SAT solver with assumption handling and metrics collection.
- `agent.py`: Deductive Logic Agent (entailment classification, uniqueness check, deduction loop, hint).
- `ui/`: Pygame desktop GUI components, board view, animations, and AgentAdapter.
- `assets/`: Character avatar sprites and visual assets for the GUI.
- `puzzles/`: JSON puzzle benchmark files for 3×3, 4×4, and 5×5 grids.
- `experiments/`: Benchmark evaluation runner and `plot_results.py` chart generator.
- `tests/`: Automated unit and integration test suite (`pytest`).

## Launching the GUI

From the repository root:

```powershell
python src/main.py
```

Pass `--puzzle src/puzzles/sample_3x3.json` to open a sample puzzle directly on launch.

## Running the Benchmark

```powershell
python src/experiments/run_experiments.py
```

Writes `benchmark_results.csv` (six Section 4.5 metric groups, one row per puzzle, failures/timeouts kept) to the repository root. See `--help` for the soft/hard timeout and repeat options.

## Generating Benchmark Charts

Once `benchmark_results.csv` is produced:

```powershell
python src/experiments/plot_results.py --input benchmark_results.csv --output assets
```

## Running Tests

```powershell
pytest src/tests
```
