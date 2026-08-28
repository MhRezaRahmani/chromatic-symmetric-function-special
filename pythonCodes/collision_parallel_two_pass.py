# collision_parallel_two_pass.py
"""
Parallel tree-collision search with two-pass bucket optimization.

Pass 1:
    Count how many non-isomorphic trees occur in each bucket.

Pass 2:
    Compute the exact specialized polynomial only for trees whose bucket
    contains at least two trees.

Default bucket:
    (leaf count, exact minimum color sum)

The expensive polynomial computation is therefore skipped for singleton
buckets, while the polynomial itself is still computed exactly for every
tree that could participate in a collision.
"""

import gc
import json
import multiprocessing as mp
import sqlite3
import time
from collections import Counter
from pathlib import Path

import networkx as nx

from tree_collision_search_CORRECTED import (
    PackedPolynomialEngine,
    bucket_key,
    connect_db,
    exact_match,
    graph6_text,
    meta_get,
    meta_set,
    save_report,
)


# ============================================================
# DATABASE
# ============================================================

def optimize_database(db_path):
    """Open a shard database with speed-oriented SQLite settings."""
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")
    con.execute("PRAGMA cache_size=-100000")
    con.execute("PRAGMA temp_store=FILE")
    con.execute("PRAGMA mmap_size=0")
    return con


def init_shard_db(db_path):
    """Create shard tables if they do not already exist."""
    con = optimize_database(db_path)

    con.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS seen (
            bucket TEXT NOT NULL,
            digest BLOB NOT NULL,
            graph6 TEXT NOT NULL,
            tree_index INTEGER NOT NULL,
            PRIMARY KEY (bucket, digest)
        ) WITHOUT ROWID
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS collisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bucket TEXT NOT NULL,
            digest BLOB NOT NULL,
            graph6_a TEXT NOT NULL,
            graph6_b TEXT NOT NULL,
            tree_index_a INTEGER,
            tree_index_b INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    con.commit()
    con.close()


# ============================================================
# PASS 1: COUNT BUCKETS
# ============================================================

def count_buckets_shard(shard_id, n, shards, bucket_mode):
    """
    Count buckets for one shard.

    This pass does NOT compute the specialized polynomial.
    It only computes the bucket key, which for the default mode means
    leaf count + exact minimum color sum.
    """
    counts = Counter()

    for i, T in enumerate(nx.nonisomorphic_trees(n)):
        if i % shards != shard_id:
            continue

        counts[bucket_key(T, bucket_mode)] += 1

    return dict(counts)


def count_all_buckets(n, shards, workers, bucket_mode):
    """Parallel first pass: count all buckets and combine shard counters."""
    print("\n=== PASS 1/2: COUNTING BUCKETS ===", flush=True)
    print(
        f"n={n}, shards={shards}, workers={min(workers, shards)}, "
        f"bucket_mode={bucket_mode}",
        flush=True,
    )
    start = time.time()

    tasks = [
        (shard_id, n, shards, bucket_mode)
        for shard_id in range(shards)
    ]

    actual_workers = min(workers, shards)

    with mp.Pool(processes=actual_workers) as pool:
        partial_counts = pool.starmap(count_buckets_shard, tasks)

    counts = Counter()
    for part in partial_counts:
        counts.update(part)

    elapsed = time.time() - start
    singleton = sum(v == 1 for v in counts.values())
    nonsingleton = sum(v >= 2 for v in counts.values())
    total_trees = sum(counts.values())

    print(
        f"Pass 1 complete: {total_trees:,} trees, "
        f"{len(counts):,} buckets, "
        f"{singleton:,} singleton buckets, "
        f"{nonsingleton:,} non-singleton buckets.",
        flush=True,
    )
    print(f"Pass 1 time: {elapsed:.1f} seconds", flush=True)

    return dict(counts)


def load_or_count_buckets(n, shards, workers, bucket_mode, base_dir):
    """
    Reuse a completed bucket-count file if it matches this run.
    Otherwise perform Pass 1 and save the result.
    """
    counts_file = base_dir / "bucket_counts.json"

    if counts_file.exists():
        try:
            data = json.loads(counts_file.read_text(encoding="utf-8"))

            if (
                data.get("n") == n
                and data.get("bucket_mode") == bucket_mode
                and isinstance(data.get("counts"), dict)
            ):
                counts = {
                    str(k): int(v)
                    for k, v in data["counts"].items()
                }
                print(
                    f"Reusing bucket counts from {counts_file}",
                    flush=True,
                )
                return counts

            print(
                "Existing bucket_counts.json does not match this run; "
                "recomputing Pass 1.",
                flush=True,
            )

        except Exception:
            print(
                "Could not read existing bucket_counts.json; "
                "recomputing Pass 1.",
                flush=True,
            )

    counts = count_all_buckets(n, shards, workers, bucket_mode)

    payload = {
        "n": n,
        "bucket_mode": bucket_mode,
        "counts": counts,
    }

    counts_file.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(f"Saved bucket counts to {counts_file}", flush=True)
    return counts


# ============================================================
# PASS 2: POLYNOMIAL SEARCH
# ============================================================

def process_batch_trees(
    con,
    engine,
    trees,
    indices,
    bucket_mode,
    n,
    bucket_counts,
):
    """
    Process one batch.

    Crucially, the bucket is checked BEFORE engine.compute(T).
    Therefore singleton buckets never pay the cost of the polynomial DP.
    """
    for T, idx in zip(trees, indices):
        bkey = bucket_key(T, bucket_mode)

        # No collision can occur in a bucket containing only one tree.
        if bucket_counts.get(bkey, 0) < 2:
            continue

        packed = engine.compute(T)
        digest = engine.digest(packed)
        g6 = graph6_text(T)

        cur = con.execute(
            """
            INSERT OR IGNORE INTO seen(
                bucket,digest,graph6,tree_index
            )
            VALUES(?,?,?,?)
            """,
            (bkey, digest, g6, idx),
        )

        if cur.rowcount == 0:
            old = con.execute(
                """
                SELECT graph6, tree_index
                FROM seen
                WHERE bucket=? AND digest=?
                """,
                (bkey, digest),
            ).fetchone()

            if old is not None and old[0] != g6:
                # Hash match is only a candidate. Verify exact equality.
                ok, exact_poly = exact_match(engine, old[0], g6)

                if ok:
                    con.execute(
                        """
                        INSERT INTO collisions(
                            bucket,digest,graph6_a,graph6_b,
                            tree_index_a,tree_index_b
                        )
                        VALUES(?,?,?,?,?,?)
                        """,
                        (
                            bkey,
                            digest,
                            old[0],
                            g6,
                            old[1],
                            idx,
                        ),
                    )
                    con.commit()

                    print(
                        f"[shard] !!! COLLISION FOUND: "
                        f"indices {old[1]} and {idx}",
                        flush=True,
                    )

                    report_file = (
                        f"collision_{n}_{old[1]}_{idx}.json"
                    )

                    save_report(
                        report_file,
                        n,
                        bkey,
                        old[1],
                        idx,
                        old[0],
                        g6,
                        engine,
                        exact_poly,
                    )


def process_shard(
    shard_id,
    n,
    db_path,
    batch_size,
    shards,
    bucket_mode,
    bucket_counts,
):
    """Process one shard of the polynomial-search pass."""
    db_path = Path(db_path)
    pid = mp.current_process().pid
    prefix = f"[shard {shard_id} pid={pid}]"

    print(
        f"{prefix} starting n={n} db={db_path}",
        flush=True,
    )

    con = optimize_database(db_path)
    engine = PackedPolynomialEngine(n)

    # -1 means that no tree has yet been processed.
    last_processed = int(
        meta_get(con, "last_processed", "-1")
    )

    print(
        f"{prefix} resuming after index {last_processed}",
        flush=True,
    )

    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_bucket ON seen(bucket)"
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_digest ON seen(digest)"
    )

    batch_trees = []
    batch_indices = []

    for i, T in enumerate(nx.nonisomorphic_trees(n)):
        # True sharding: each tree belongs to exactly one shard.
        if i % shards != shard_id:
            continue

        # Resume only after the last committed index for this shard.
        if i <= last_processed:
            continue

        batch_trees.append(T)
        batch_indices.append(i)

        if len(batch_trees) >= batch_size:
            try:
                process_batch_trees(
                    con,
                    engine,
                    batch_trees,
                    batch_indices,
                    bucket_mode,
                    n,
                    bucket_counts,
                )
            except Exception as e:
                print(
                    f"{prefix} Error processing batch: {e}",
                    flush=True,
                )
                raise

            batch_trees = []
            batch_indices = []
            gc.collect()

            meta_set(con, "last_processed", i)
            con.commit()

            print(
                f"{prefix} processed through index {i:,}",
                flush=True,
            )

    # Process final partial batch.
    if batch_trees:
        process_batch_trees(
            con,
            engine,
            batch_trees,
            batch_indices,
            bucket_mode,
            n,
            bucket_counts,
        )

        meta_set(
            con,
            "last_processed",
            batch_indices[-1],
        )
        con.commit()

    con.close()
    print(f"{prefix} done.", flush=True)


# ============================================================
# MERGE
# ============================================================

def merge_shards(n, shards, base_dir):
    """
    Merge shard databases.

    Same-shard collisions were already recorded by the workers.
    Cross-shard hash matches are checked here.
    """
    print("\n=== MERGING SHARDS ===", flush=True)

    merged_db = base_dir / "merged.sqlite"
    con = connect_db(merged_db)
    engine = PackedPolynomialEngine(n)
    total_merged = 0

    for shard in range(shards):
        shard_path = base_dir / f"shard_{shard}.sqlite"

        if not shard_path.exists():
            print(
                f"[merge] shard {shard} not found, skipping.",
                flush=True,
            )
            continue

        src = sqlite3.connect(shard_path)
        src.row_factory = sqlite3.Row

        for row in src.execute("SELECT * FROM seen"):
            cur = con.execute(
                """
                INSERT OR IGNORE INTO seen(
                    bucket,digest,graph6,tree_index
                )
                VALUES(?,?,?,?)
                """,
                (
                    row["bucket"],
                    row["digest"],
                    row["graph6"],
                    row["tree_index"],
                ),
            )

            if cur.rowcount == 0:
                old = con.execute(
                    """
                    SELECT graph6, tree_index
                    FROM seen
                    WHERE bucket=? AND digest=?
                    """,
                    (row["bucket"], row["digest"]),
                ).fetchone()

                if old is not None and old[0] != row["graph6"]:
                    ok, _ = exact_match(
                        engine,
                        old[0],
                        row["graph6"],
                    )

                    if ok:
                        con.execute(
                            """
                            INSERT INTO collisions(
                                bucket,digest,graph6_a,graph6_b,
                                tree_index_a,tree_index_b
                            )
                            VALUES(?,?,?,?,?,?)
                            """,
                            (
                                row["bucket"],
                                row["digest"],
                                old[0],
                                row["graph6"],
                                old[1],
                                row["tree_index"],
                            ),
                        )

                        print(
                            "[merge] cross-shard collision: "
                            f"{old[0]} vs {row['graph6']}",
                            flush=True,
                        )

            total_merged += 1

            if total_merged % 10_000 == 0:
                con.commit()
                print(
                    f"[merge] {total_merged:,} records merged",
                    flush=True,
                )

        src.close()
        con.commit()

    print(
        f"\n[merge] complete — total records: "
        f"{total_merged:,}",
        flush=True,
    )

    con.close()


# ============================================================
# MAIN SEARCH
# ============================================================

def run_optimized(
    n=18,
    batch_size=1000,
    shards=4,
    workers=4,
    bucket_mode="leaves+minsum",
):
    print(
        f"Starting parallel two-pass search  "
        f"n={n}  shards={shards}  workers={workers}",
        flush=True,
    )

    base_dir = Path(f"optimized_n{n}")
    base_dir.mkdir(exist_ok=True)

    # --------------------------------------------------------
    # PASS 1: count buckets
    # --------------------------------------------------------
    bucket_counts = load_or_count_buckets(
        n,
        shards,
        workers,
        bucket_mode,
        base_dir,
    )

    # --------------------------------------------------------
    # Initialize shard databases
    # --------------------------------------------------------
    db_paths = []

    for shard in range(shards):
        db_path = base_dir / f"shard_{shard}.sqlite"
        init_shard_db(db_path)
        db_paths.append(str(db_path))

    # --------------------------------------------------------
    # PASS 2: exact polynomial search
    # --------------------------------------------------------
    print("\n=== PASS 2/2: EXACT POLYNOMIAL SEARCH ===", flush=True)

    tasks = [
        (
            shard_id,
            n,
            db_paths[shard_id],
            batch_size,
            shards,
            bucket_mode,
            bucket_counts,
        )
        for shard_id in range(shards)
    ]

    actual_workers = min(workers, shards)

    print(
        f"Spawning {actual_workers} worker(s) "
        f"for {shards} shard(s)...",
        flush=True,
    )

    with mp.Pool(processes=actual_workers) as pool:
        pool.starmap(process_shard, tasks)

    # --------------------------------------------------------
    # Merge
    # --------------------------------------------------------
    merge_shards(n, shards, base_dir)

    print("\nSEARCH COMPLETE.", flush=True)


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Parallel two-pass tree-collision search"
    )

    parser.add_argument(
        "--n",
        type=int,
        default=19,
        help="number of vertices",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="trees per database-processing batch",
    )

    parser.add_argument(
        "--shards",
        type=int,
        default=4,
        help="number of shards",
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=mp.cpu_count(),
        help="number of parallel worker processes",
    )

    parser.add_argument(
        "--bucket-mode",
        choices=[
            "leaves+minsum",
            "leaves",
            "known",
            "none",
        ],
        default="leaves+minsum",
        help="bucket mode",
    )

    args = parser.parse_args()

    # Required for Windows/macOS multiprocessing.
    mp.set_start_method("spawn", force=True)

    run_optimized(
        n=args.n,
        batch_size=args.batch_size,
        shards=args.shards,
        workers=args.workers,
        bucket_mode=args.bucket_mode,
    )
