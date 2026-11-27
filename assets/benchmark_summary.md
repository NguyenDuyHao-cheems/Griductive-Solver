# Benchmark Summary (6 Metric Groups)

- Total puzzles: **8** (Solved: **8**, Timeout: **0**, Failed/Other: **0**)
- Note: Average metrics by grid size are computed over **SOLVED** puzzles only; timeout and failure cases are retained in full below and never counted as successes.
- Missing or unavailable numeric measurements are shown as `-` in tables and left blank in charts; they are not treated as zero.

## 1. Per-Puzzle Results (All Cases Retained)

| Puzzle | Size | Status | Primary Vars | Aux Vars | Clauses | SAT Calls | Decisions | Propagations | Backtracks | Steps | Waves | Runtime (ms) |
| :--- | :---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| puzzle_3x3_01 | 3x3 | SOLVED | 9 | 36 | 149 | 20 | 10 | 403 | 0 | 7 | 3 | 3.63 |
| puzzle_3x3_02 | 3x3 | SOLVED | 9 | 30 | 130 | 28 | 18 | 494 | 0 | 7 | 3 | 3.24 |
| sample_3x3 | 3x3 | SOLVED | 9 | 17 | 77 | 38 | 12 | 503 | 0 | 7 | 6 | 2.17 |
| puzzle_4x4_01 | 4x4 | SOLVED | 16 | 60 | 262 | 62 | 26 | 1732 | 0 | 14 | 2 | 10.44 |
| puzzle_4x4_02 | 4x4 | SOLVED | 16 | 40 | 185 | 94 | 79 | 2284 | 0 | 14 | 5 | 10.80 |
| sample_4x4 | 4x4 | SOLVED | 16 | 54 | 220 | 88 | 89 | 2932 | 0 | 14 | 6 | 10.27 |
| puzzle_5x5_01 | 5x5 | SOLVED | 25 | 186 | 731 | 84 | 253 | 6014 | 3 | 22 | 4 | 44.97 |
| puzzle_5x5_02 | 5x5 | SOLVED | 25 | 209 | 807 | 76 | 147 | 7067 | 1 | 22 | 4 | 52.73 |

## 2. Aggregated Summary by Grid Size (Success Averages + Non-Success Counts)

| Size | Total | Solved | Timeout | Failed | Avg Primary | Avg Aux | Avg Clauses | Avg SAT Calls | Avg Decisions | Avg Propagations | Avg Backtracks | Avg Steps | Avg Waves | Avg Runtime (ms) |
| :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3x3 | 3 | 3 | 0 | 0 | 9 | 27.7 | 118.7 | 28.7 | 13.3 | 466.7 | 0 | 7 | 4 | 3.01 |
| 4x4 | 3 | 3 | 0 | 0 | 16 | 51.3 | 222.3 | 81.3 | 64.7 | 2316 | 0 | 14 | 4.3 | 10.50 |
| 5x5 | 2 | 2 | 0 | 0 | 25 | 197.5 | 769 | 80 | 200 | 6540.5 | 2 | 22 | 4 | 48.85 |
