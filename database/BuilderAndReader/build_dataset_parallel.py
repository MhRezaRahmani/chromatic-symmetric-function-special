"""
build_public_dataset_parallel.py

Build a public dataset containing ONLY:

    graph6, polynomial

for every non-isomorphic tree on n vertices.

The exact polynomial is

    F_T(q) = X_T(1, q, q^2, ..., q^(n-1))

The polynomial is stored as a comma-separated coefficient vector:

    a0,a1,a2,...

meaning

    a0 + a1*q + a2*q^2 + ...

Parallel strategy:
    - each worker independently enumerates the same stream of
      non-isomorphic trees and keeps indices i % workers == worker_id;
    - each worker writes its own CSV and SQLite shard;
    - the parent merges the shards into one final SQLite database
      and one final CSV.

No search metadata, hashes, bucket information, tree indices, etc.
are stored in the public dataset.
"""

import argparse
import csv
import multiprocessing as mp
import os
import shutil
import time
from pathlib import Path

import networkx as nx

from tree_collision_search_CORRECTED import (
    PackedPolynomialEngine,
    graph6_text,
)


# ============================================================
# WORKER
# ============================================================

def worker_build(worker_id, n, workers, parts_dir, batch_flush):
    parts_dir = Path(parts_dir)
    csv_path = parts_dir / f"part_{worker_id:04d}.csv"

    if csv_path.exists():
        csv_path.unlink()

    engine = PackedPolynomialEngine(n)
    processed = 0
    started = time.time()

    with open(
        csv_path,
        "w",
        newline="",
        encoding="utf-8",
        buffering=1024 * 1024,
    ) as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["graph6", "polynomial"])

        for i, T in enumerate(nx.nonisomorphic_trees(n)):
            if i % workers != worker_id:
                continue

            packed = engine.compute(T)
            coefficients = engine.coefficients(packed)
            g6 = graph6_text(T)
            polynomial = ",".join(map(str, coefficients))

            writer.writerow([g6, polynomial])
            processed += 1

            if processed % batch_flush == 0:
                csv_file.flush()
                elapsed = time.time() - started
                rate = processed / elapsed if elapsed else 0.0
                print(
                    f"[worker {worker_id}] "
                    f"processed={processed:,} "
                    f"rate={rate:,.2f} trees/s",
                    flush=True,
                )

        csv_file.flush()

    elapsed = time.time() - started
    print(
        f"[worker {worker_id}] DONE: "
        f"{processed:,} trees in {elapsed:.1f}s",
        flush=True,
    )
    return worker_id, processed


# ============================================================
# FINAL CSV
# ============================================================

def merge_csv(parts_dir, workers, final_csv):
    print("\n=== MERGING CSV SHARDS ===", flush=True)

    total = 0

    with open(
        final_csv,
        "w",
        newline="",
        encoding="utf-8",
        buffering=1024 * 1024,
    ) as out_file:
        writer = csv.writer(out_file)
        writer.writerow(["graph6", "polynomial"])

        for worker_id in range(workers):
            csv_path = parts_dir / f"part_{worker_id:04d}.csv"

            if not csv_path.exists():
                raise RuntimeError(f"Missing worker CSV: {csv_path}")

            with open(
                csv_path,
                "r",
                newline="",
                encoding="utf-8",
            ) as in_file:
                reader = csv.reader(in_file)
                next(reader, None)

                for row in reader:
                    writer.writerow(row)
                    total += 1

            print(f"[merge] worker {worker_id}: done", flush=True)

    print(f"CSV merge complete: {total:,} records", flush=True)
    return total


# ============================================================
# MAIN
# ============================================================

def build_dataset(n, workers, output_dir, batch_flush, keep_parts):
    if n < 2:
        raise ValueError("n must be >= 2")

    workers = max(1, min(workers, os.cpu_count() or 1))

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    parts_dir = output_dir / "parts"
    if parts_dir.exists():
        shutil.rmtree(parts_dir)
    parts_dir.mkdir(parents=True)

    final_csv = output_dir / f"trees_n{n}.csv"
    if final_csv.exists():
        final_csv.unlink()

    print("=" * 70)
    print("PUBLIC TREE DATASET - CSV ONLY")
    print("=" * 70)
    print(f"n          = {n}")
    print(f"workers    = {workers}")
    print(f"output     = {output_dir}")
    print(f"CSV        = {final_csv}")
    print("=" * 70)
    print()

    started = time.time()
    ctx = mp.get_context("spawn")

    tasks = [
        (worker_id, n, workers, parts_dir, batch_flush)
        for worker_id in range(workers)
    ]

    with ctx.Pool(processes=workers) as pool:
        results = pool.starmap(worker_build, tasks)

    results.sort()
    total_workers = sum(count for _, count in results)

    print()
    print(f"Polynomial computation complete: {total_workers:,} trees")

    csv_count = merge_csv(parts_dir, workers, final_csv)

    if csv_count != total_workers:
        raise RuntimeError(
            f"Worker/CSV count mismatch: {total_workers} != {csv_count}"
        )

    if not keep_parts:
        shutil.rmtree(parts_dir)

    elapsed = time.time() - started

    print()
    print("=" * 70)
    print("DATASET COMPLETE")
    print("=" * 70)
    print(f"records    = {csv_count:,}")
    print(f"CSV        = {final_csv}")
    print(f"time       = {elapsed:.1f}s")
    print("=" * 70)



def main():
    parser = argparse.ArgumentParser(
        description="Build graph6 + polynomial dataset in parallel."
    )

    parser.add_argument(
        "--n",
        type=int,
        required=True,
        help="Number of vertices.",
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=min(8, os.cpu_count() or 1),
        help="Number of worker processes.",
    )

    parser.add_argument(
        "--output",
        type=str,
        default="public_dataset",
        help="Output directory.",
    )

    parser.add_argument(
        "--batch-flush",
        type=int,
        default=1000,
        help="Flush the CSV every N trees per worker.",
    )

    parser.add_argument(
        "--keep-parts",
        action="store_true",
        help="Keep per-worker CSV/SQLite files after merging.",
    )

    args = parser.parse_args()

    build_dataset(
        n=args.n,
        workers=args.workers,
        output_dir=args.output,
        batch_flush=args.batch_flush,
        keep_parts=args.keep_parts,
    )


if __name__ == "__main__":
    main()

#  type this in terminal: python build_dataset_parallel.py --n 19 --workers 8
# Warning! workers can be as much as cpu cores.