# Griductive Solver — Source

Source code, puzzles, tests, and GUI assets live in this directory.

For setup and project-wide instructions, see the [root README](../README.md).

## Launching the GUI

From the repository root after installing dependencies:

```powershell
python src/main.py
```

Pass `--puzzle src/puzzles/sample_3x3.json` to open a sample directly. Verdict,
Hint, and Auto Solve controls are isolated in `src/ui/agent_adapter.py` and
remain disabled with a status notice until `src/agent.py` implements the
required LogicAgent APIs.

## Generating Benchmark Charts

Once `benchmark_results.csv` is available:

```powershell
python src/experiments/plot_results.py --input benchmark_results.csv --output assets
```

## Running Tests

```powershell
pytest src/tests
```
