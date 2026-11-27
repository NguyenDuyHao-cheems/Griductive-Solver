"""Random 3-SAT stress test for the DPLL solver (report Section 3.1, "Hạn chế").

Generates uniform random 3-SAT instances with a fixed seed and solves each one
with ``DPLLSolver``. Every clause picks 3 distinct variables uniformly at random
and negates each with probability 1/2 (the standard fixed-clause-length model).

Each instance runs in its own child process, killed after ``--hard-timeout``
seconds, so one very hard seed cannot block the whole run. One CSV row is
written per seed, including timeouts.

Usage (from the repository root)::

    python src/experiments/random_3sat.py --vars 150 --ratio 4.2 \
        --seeds 0 1 2 3 4 --hard-timeout 900 --output random_3sat_results.csv
"""

from __future__ import annotations

import argparse
import csv
import multiprocessing as mp
import platform
import random
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dpll import DPLLSolver, verify_assignment  # noqa: E402

FIELDS = [
    "seed", "num_vars", "num_clauses", "ratio", "status",
    "decisions", "propagations", "backtracks", "runtime_ms", "verified",
]


def generate(num_vars: int, num_clauses: int, seed: int) -> list[list[int]]:
    """Uniform random 3-SAT: 3 distinct variables per clause, random signs."""
    rng = random.Random(seed)
    clauses = []
    for _ in range(num_clauses):
        variables = rng.sample(range(1, num_vars + 1), 3)
        clauses.append([v if rng.random() < 0.5 else -v for v in variables])
    return clauses


def _worker(conn, num_vars: int, num_clauses: int, seed: int) -> None:
    clauses = generate(num_vars, num_clauses, seed)
    result = DPLLSolver(clauses, num_vars=num_vars).solve()
    verified = result.status == "UNSAT" or verify_assignment(clauses, result.assignment)
    conn.send({
        "status": result.status,
        "decisions": result.decisions,
        "propagations": result.propagations,
        "backtracks": result.backtracks,
        "runtime_ms": round(result.runtime_ms, 1),
        "verified": verified,
    })
    conn.close()


def run_seed(num_vars: int, num_clauses: int, seed: int, hard_timeout_s: float) -> dict:
    row = {"seed": seed, "num_vars": num_vars, "num_clauses": num_clauses,
           "ratio": round(num_clauses / num_vars, 3)}
    parent, child = mp.Pipe(duplex=False)
    proc = mp.get_context("spawn").Process(target=_worker, args=(child, num_vars, num_clauses, seed))
    proc.start()
    child.close()
    if parent.poll(hard_timeout_s):
        row.update(parent.recv())
    else:
        row.update(status="TIMEOUT", decisions="", propagations="", backtracks="",
                   runtime_ms=round(hard_timeout_s * 1000.0, 1), verified="")
    proc.kill()
    proc.join()
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vars", type=int, default=150)
    parser.add_argument("--ratio", type=float, default=4.2)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    parser.add_argument("--hard-timeout", type=float, default=900.0, help="seconds per seed")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "random_3sat_results.csv")
    args = parser.parse_args(argv)

    num_clauses = round(args.vars * args.ratio)
    print(f"Python {platform.python_version()} on {platform.platform()} / {platform.processor()}")
    print(f"{args.vars} vars, {num_clauses} clauses (ratio {args.ratio}), seeds {args.seeds}")
    rows = []
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for seed in args.seeds:
            row = run_seed(args.vars, num_clauses, seed, args.hard_timeout)
            writer.writerow(row)
            handle.flush()
            rows.append(row)
            print(f"seed={seed}: {row['status']} runtime_ms={row['runtime_ms']} "
                  f"decisions={row['decisions']} backtracks={row['backtracks']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
