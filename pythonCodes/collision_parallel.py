# optimized_search_parallel.py
"""
نسخه موازی با multiprocessing — هر shard در یک پروسه مستقل اجرا می‌شود.
"""

import sqlite3
import time
import gc
import multiprocessing as mp
from pathlib import Path
import networkx as nx
from tree_collision_search_CORRECTED import (
    PackedPolynomialEngine,
    minimum_color_sum,
    degree_sequence_text,
    graph6_text,
    connect_db,
    meta_set,
    meta_get,
    exact_match,
    save_report,
    bucket_key,
    validate_tree,
)


# ──────────────────────────────────────────────
# دیتابیس
# ──────────────────────────────────────────────

def optimize_database(db_path):
    """اتصال به دیتابیس با تنظیمات بهینه‌شده."""
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")
    con.execute("PRAGMA cache_size=-100000")
    con.execute("PRAGMA temp_store=FILE")
    con.execute("PRAGMA mmap_size=0")
    return con


def init_shard_db(db_path):
    """ساخت جداول shard اگر وجود نداشته باشند."""
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


# ──────────────────────────────────────────────
# پردازش یک دسته از درختان
# ──────────────────────────────────────────────

def process_batch_trees(con, engine, trees, indices, bucket_mode, n):
    """پردازش یک دسته از درختان و ثبت برخوردها."""
    for T, idx in zip(trees, indices):
        bkey = bucket_key(T, bucket_mode)
        packed = engine.compute(T)
        digest = engine.digest(packed)
        g6 = graph6_text(T)

        cur = con.execute(
            "INSERT OR IGNORE INTO seen(bucket,digest,graph6,tree_index) VALUES(?,?,?,?)",
            (bkey, digest, g6, idx),
        )

        if cur.rowcount == 0:
            old = con.execute(
                "SELECT graph6, tree_index FROM seen WHERE bucket=? AND digest=?",
                (bkey, digest),
            ).fetchone()

            if old is not None and old[0] != g6:
                ok, exact_poly = exact_match(engine, old[0], g6)
                if ok:
                    con.execute(
                        """INSERT INTO collisions(
                               bucket, digest, graph6_a, graph6_b,
                               tree_index_a, tree_index_b)
                           VALUES(?,?,?,?,?,?)""",
                        (bkey, digest, old[0], g6, old[1], idx),
                    )
                    con.commit()

                    print(
                        f"[shard] !!! COLLISION FOUND: indices {old[1]} and {idx}",
                        flush=True,
                    )

                    report_file = f"collision_{n}_{old[1]}_{idx}.json"
                    save_report(
                        report_file, n, bkey, old[1], idx, old[0], g6, engine, exact_poly
                    )


# ──────────────────────────────────────────────
# پردازش یک shard — تابع worker
# ──────────────────────────────────────────────

def process_shard(
    shard_id: int,
    n: int,
    db_path: str,
    batch_size: int,
    shards: int,
    bucket_mode: str = "leaves+minsum",
):
    """
    پردازش کامل یک shard.
    این تابع در یک پروسه مستقل فراخوانی می‌شود.
    """
    db_path = Path(db_path)
    pid = mp.current_process().pid
    prefix = f"[shard {shard_id} pid={pid}]"

    print(f"{prefix} starting  n={n}  db={db_path}", flush=True)

    con = optimize_database(db_path)
    engine = PackedPolynomialEngine(n)

    # بازیابی آخرین ایندکس پردازش‌شده
    last_processed = int(meta_get(con, "last_processed", "0"))
    print(f"{prefix} resuming from index {last_processed}", flush=True)

    # ایندکس‌های سرعت‌بخش
    con.execute("CREATE INDEX IF NOT EXISTS idx_bucket ON seen(bucket)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_digest ON seen(digest)")

    batch_trees: list = []
    batch_indices: list = []
    current_batch_size = batch_size

    for i, T in enumerate(nx.nonisomorphic_trees(n)):
        if i % shards != shard_id:
            continue
        if i <= last_processed:
            continue

        batch_trees.append(T)
        batch_indices.append(i)

        if len(batch_trees) >= current_batch_size:
            try:
                process_batch_trees(con, engine, batch_trees, batch_indices, bucket_mode, n)
            except Exception as e:
                print(f"{prefix} Error processing batch: {e}", flush=True)
                raise

            batch_trees = []
            batch_indices = []
            gc.collect()

            meta_set(con, "last_processed", i)
            con.commit()
            print(f"{prefix} processed up to index {i:,}", flush=True)

    # باقیمانده
    if batch_trees:
        process_batch_trees(con, engine, batch_trees, batch_indices, bucket_mode, n)
        meta_set(con, "last_processed", batch_indices[-1])
        con.commit()

    con.close()
    print(f"{prefix} done.", flush=True)


# ──────────────────────────────────────────────
# ادغام شاردها
# ──────────────────────────────────────────────

def merge_shards(n: int, shards: int, base_dir: Path):
    """ادغام همه دیتابیس‌های shard در یک فایل واحد."""
    merged_db = base_dir / "merged.sqlite"
    con = connect_db(merged_db)
    engine = PackedPolynomialEngine(n)
    total_merged = 0

    for shard in range(shards):
        shard_path = base_dir / f"shard_{shard}.sqlite"
        if not shard_path.exists():
            print(f"[merge] shard {shard} not found, skipping.", flush=True)
            continue

        src = sqlite3.connect(shard_path)
        src.row_factory = sqlite3.Row

        for row in src.execute("SELECT * FROM seen"):
            cur = con.execute(
                "INSERT OR IGNORE INTO seen(bucket,digest,graph6,tree_index) VALUES(?,?,?,?)",
                (row["bucket"], row["digest"], row["graph6"], row["tree_index"]),
            )

            if cur.rowcount == 0:
                old = con.execute(
                    "SELECT graph6, tree_index FROM seen WHERE bucket=? AND digest=?",
                    (row["bucket"], row["digest"]),
                ).fetchone()

                if old is not None and old[0] != row["graph6"]:
                    ok, _ = exact_match(engine, old[0], row["graph6"])
                    if ok:
                        con.execute(
                            """INSERT INTO collisions(
                                   bucket, digest, graph6_a, graph6_b,
                                   tree_index_a, tree_index_b)
                               VALUES(?,?,?,?,?,?)""",
                            (
                                row["bucket"], row["digest"],
                                old[0], row["graph6"],
                                old[1], row["tree_index"],
                            ),
                        )
                        print(
                            f"[merge] cross-shard collision: {old[0]} vs {row['graph6']}",
                            flush=True,
                        )

            total_merged += 1
            if total_merged % 10_000 == 0:
                con.commit()
                print(f"[merge] {total_merged:,} records merged", flush=True)

        src.close()
        con.commit()

    print(f"\n[merge] complete — total records: {total_merged:,}", flush=True)
    con.close()


# ──────────────────────────────────────────────
# اجرای اصلی
# ──────────────────────────────────────────────

def run_optimized(
    n: int = 5,
    batch_size: int = 1000,
    shards: int = 4,
    workers: int = 4,
    bucket_mode: str = "leaves+minsum",
):
    """
    اجرای موازی جستجو.

    Parameters
    ----------
    n          : تعداد رأس‌های درخت
    batch_size : اندازه هر دسته
    shards     : تعداد shardها (= تعداد دیتابیس‌های مجزا)
    workers    : تعداد پروسه‌های موازی
    bucket_mode: حالت bucket‌بندی
    """
    print(f"Starting parallel search  n={n}  shards={shards}  workers={workers}")

    base_dir = Path(f"optimized_n{n}")
    base_dir.mkdir(exist_ok=True)

    # ایجاد همه دیتابیس‌ها پیش از fork
    db_paths = []
    for shard in range(shards):
        db_path = base_dir / f"shard_{shard}.sqlite"
        init_shard_db(db_path)
        db_paths.append(str(db_path))

    # آرگومان‌های worker
    tasks = [
        (shard_id, n, db_paths[shard_id], batch_size,shards, bucket_mode)
        for shard_id in range(shards)
    ]

    # اجرای موازی
    actual_workers = min(workers, shards)
    print(f"Spawning {actual_workers} worker(s) for {shards} shard(s)…\n", flush=True)

    with mp.Pool(processes=actual_workers) as pool:
        pool.starmap(process_shard, tasks)

    # ادغام نتایج
    print("\n=== Merging shards ===", flush=True)
    merge_shards(n, shards, base_dir)


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    # مقدار پیش‌فرض
    DEFAULT_N = 20

    parser = argparse.ArgumentParser(
        description="Parallel tree-collision search (multiprocessing)"
    )
    parser.add_argument("--n",           type=int, default=DEFAULT_N,          help="تعداد رأس")
    parser.add_argument("--batch-size",  type=int, default=1000,               help="اندازه دسته")
    parser.add_argument("--shards",      type=int, default=4,                  help="تعداد shardها")
    parser.add_argument("--workers",     type=int, default=mp.cpu_count(),     help="تعداد پروسه‌های موازی")
    parser.add_argument(
        "--bucket-mode",
        choices=["leaves+minsum", "leaves", "known", "none"],
        default="leaves+minsum",
        help="حالت bucket‌بندی",
    )
    args = parser.parse_args()

    # spawn برای سازگاری با macOS/Windows
    mp.set_start_method("spawn", force=True)

    run_optimized(
        n=args.n,
        batch_size=args.batch_size,
        shards=args.shards,
        workers=args.workers,
        bucket_mode=args.bucket_mode,
    )