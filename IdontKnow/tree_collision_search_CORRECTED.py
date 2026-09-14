"""
tree_collision_search_CORRECTED.py

Search for collisions in the principal specialization

    F_T(q) = X_T(1, q, q^2, ..., q^(n-1))

for non-isomorphic trees T on n vertices.

CORRECTION:
The "minimum color sum" is computed exactly by dynamic programming.
It is NOT assumed to equal the size of the smaller bipartition class.

Default bucket:
    (leaf count, exact minimum color sum)

Features:
- streams non-isomorphic trees
- exact tree-DP for the specialized polynomial
- exact tree-DP for minimum color sum
- compact packed polynomial representation
- BLAKE2b-256 hash table in SQLite
- exact recomputation after any hash match
- checkpoint/resume
- progress reporting
- optional sharding and shard merge
- self-test
"""

import argparse
import hashlib
import json
import math
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

import networkx as nx


# ============================================================
# TREE HELPERS
# ============================================================

def degree_sequence(T):
    return tuple(sorted((d for _, d in T.degree()), reverse=True))


def leaf_count(T):
    """Return the number of leaves (degree-1 vertices) in the tree."""
    if len(T) == 1:
        return 1
    return sum(1 for _, d in T.degree() if d == 1)


def degree_sequence_text(T):
    return ",".join(map(str, degree_sequence(T)))


def graph6_text(T):
    return nx.to_graph6_bytes(T, header=False).decode("ascii").strip()


def tree_from_graph6(g6):
    return nx.from_graph6_bytes(g6.encode("ascii"))


# ============================================================
# EXACT MINIMUM COLOR SUM
# ============================================================

def minimum_color_sum(T):
    """
    Compute the exact minimum possible sum of vertex colors over all proper
    colorings with nonnegative integer colors.

    For an n-vertex tree it is enough to allow colors 0,1,...,n-1.

    Dynamic programming:
        dp[v][c] = minimum color sum in subtree rooted at v,
                   assuming v has color c.

        dp[v][c] = c + sum over children u of
                         min_{d != c} dp[u][d]

    To make this fast, for each child we store its smallest and second-smallest
    dp values, so each forbidden-color query is O(1).
    """
    n = len(T)
    if n == 0:
        return 0
    if n == 1:
        return 0

    root = nx.center(T)[0]

    parent = {root: None}
    children = {v: [] for v in T.nodes()}
    order = [root]

    for v in order:
        for u in T.neighbors(v):
            if u == parent[v]:
                continue
            parent[u] = v
            children[v].append(u)
            order.append(u)

    dp = {}

    for v in reversed(order):
        vals = [c for c in range(n)]

        for child in children[v]:
            child_vals = dp[child]

            # Find smallest and second-smallest values, including their colors.
            best1_val = math.inf
            best1_color = -1
            best2_val = math.inf

            for color, value in enumerate(child_vals):
                if value < best1_val:
                    best2_val = best1_val
                    best1_val = value
                    best1_color = color
                elif value < best2_val:
                    best2_val = value

            for c in range(n):
                vals[c] += best2_val if c == best1_color else best1_val

            del dp[child]

        dp[v] = vals

    return min(dp[root])


def bucket_key(T, mode):
    """
    leaves+minsum : same leaf count AND exact minimum color sum
    leaves        : same leaf count only
    known         : same exact minimum color sum only
    none          : no structural restriction
    """
    if mode == "leaves+minsum":
        return f"l={leaf_count(T)}|m={minimum_color_sum(T)}"
    if mode == "leaves":
        return f"l={leaf_count(T)}"
    if mode == "known":
        return f"m={minimum_color_sum(T)}"
    if mode == "none":
        return "all"
    raise ValueError(f"Unknown bucket mode: {mode}")


# ============================================================
# PACKED EXACT POLYNOMIAL ENGINE
# ============================================================

class PackedPolynomialEngine:
    """
    Represent a polynomial coefficient vector in base B=2^bits:

        a_0 + a_1 q + ... + a_D q^D

    is encoded as

        a_0 + a_1 B + ... + a_D B^D.

    B is chosen larger than every coefficient, so multiplication of packed
    integers performs exact polynomial convolution without carries.
    """

    def __init__(self, n):
        self.n = n

        # Number of proper colorings of an n-vertex tree with n labeled colors.
        total_colorings = n * (n - 1) ** (n - 1) if n >= 2 else 1

        # Strictly larger than every possible coefficient.
        self.bits = total_colorings.bit_length() + 1
        self.mask = (1 << self.bits) - 1

        # q^c becomes B^c = 2^(bits*c).
        self.qmono = [1 << (self.bits * c) for c in range(n)]

    def compute(self, T):
        """
        Exact DP for

            X_T(1, q, q^2, ..., q^(n-1)).

        If P[v][c] is the polynomial for the rooted subtree at v when v has
        color c, then

            P[v][c] = q^c * product_child u (
                          sum_{d != c} P[u][d]
                      ).
        """
        n = self.n

        if len(T) != n:
            raise ValueError("Tree size does not match polynomial engine.")
        if n == 1:
            return 1

        root = nx.center(T)[0]

        parent = {root: None}
        children = {v: [] for v in T.nodes()}
        order = [root]

        for v in order:
            for u in T.neighbors(v):
                if u == parent[v]:
                    continue
                parent[u] = v
                children[v].append(u)
                order.append(u)

        dp = {}

        for v in reversed(order):
            vals = self.qmono.copy()

            for child in children[v]:
                child_vals = dp[child]
                child_total = sum(child_vals)

                for c in range(n):
                    vals[c] *= (child_total - child_vals[c])

                del dp[child]

            dp[v] = vals

        return sum(dp[root])

    def coefficient_sum(self, packed):
        total = 0
        x = packed
        while x:
            total += x & self.mask
            x >>= self.bits
        return total

    def min_exponent(self, packed):
        if packed == 0:
            return None

        k = 0
        x = packed
        while (x & self.mask) == 0:
            x >>= self.bits
            k += 1
        return k

    def coefficients(self, packed):
        out = []
        x = packed

        while x:
            out.append(x & self.mask)
            x >>= self.bits

        return tuple(out or [0])

    def digest(self, packed):
        length = max(1, (packed.bit_length() + 7) // 8)
        raw = packed.to_bytes(length, "little", signed=False)
        return hashlib.blake2b(raw, digest_size=32).digest()


# ============================================================
# INDEPENDENT SLOW CHECK FOR SMALL TREES
# ============================================================

def slow_specialized_polynomial(T):
    """
    Slow list-based polynomial DP used ONLY in self-test.
    This independently checks the packed-integer implementation.
    """
    n = len(T)

    def add(A, B):
        out = [0] * max(len(A), len(B))
        for i, x in enumerate(A):
            out[i] += x
        for i, x in enumerate(B):
            out[i] += x
        return out

    def multiply(A, B):
        out = [0] * (len(A) + len(B) - 1)
        for i, a in enumerate(A):
            if a == 0:
                continue
            for j, b in enumerate(B):
                if b:
                    out[i + j] += a * b
        return out

    if n == 1:
        return (1,)

    root = nx.center(T)[0]
    parent = {root: None}
    children = {v: [] for v in T.nodes()}
    order = [root]

    for v in order:
        for u in T.neighbors(v):
            if u == parent[v]:
                continue
            parent[u] = v
            children[v].append(u)
            order.append(u)

    dp = {}

    for v in reversed(order):
        vals = []

        for c in range(n):
            cur = [0] * c + [1]

            for child in children[v]:
                allowed = [0]
                for d in range(n):
                    if d != c:
                        allowed = add(allowed, dp[child][d])
                cur = multiply(cur, allowed)

            vals.append(cur)

        dp[v] = vals

    total = [0]
    for c in range(n):
        total = add(total, dp[root][c])

    while len(total) > 1 and total[-1] == 0:
        total.pop()

    return tuple(total)


# ============================================================
# VALIDATION / SELF TEST
# ============================================================

def validate_tree(T, engine, packed, compare_slow=False):
    n = len(T)

    # At q=1: number of proper colorings of an n-vertex tree with n colors.
    expected_total = n * (n - 1) ** (n - 1) if n >= 2 else 1
    got_total = engine.coefficient_sum(packed)

    if got_total != expected_total:
        raise AssertionError(
            f"Coefficient-sum check failed: got {got_total}, "
            f"expected {expected_total}"
        )

    # The minimum polynomial exponent MUST equal the exact minimum color sum.
    exact_min = minimum_color_sum(T)
    poly_min = engine.min_exponent(packed)

    if poly_min != exact_min:
        raise AssertionError(
            f"Minimum-color-sum check failed: polynomial minimum exponent "
            f"is {poly_min}, exact DP gives {exact_min}"
        )

    if compare_slow:
        fast_coeffs = engine.coefficients(packed)
        slow_coeffs = slow_specialized_polynomial(T)

        if fast_coeffs != slow_coeffs:
            raise AssertionError(
                "Packed polynomial disagrees with independent slow polynomial DP."
            )


def self_test():
    print("Running corrected self-test...")

    for n in range(2, 8):
        engine = PackedPolynomialEngine(n)
        count = 0

        for T in nx.nonisomorphic_trees(n):
            packed = engine.compute(T)
            validate_tree(T, engine, packed, compare_slow=True)
            count += 1

        print(f"  n={n}: checked {count} non-isomorphic trees")

    print("CORRECTED SELF-TEST PASSED.")


# ============================================================
# SQLITE
# ============================================================

def connect_db(path):
    con = sqlite3.connect(path, timeout=60)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA temp_store=MEMORY")
    con.execute("PRAGMA cache_size=-200000")

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
    return con


def meta_get(con, key, default=None):
    row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return default if row is None else row[0]


def meta_set(con, key, value):
    con.execute(
        """
        INSERT INTO meta(key,value) VALUES(?,?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        (key, str(value)),
    )


# ============================================================
# PROGRESS
# ============================================================

def fmt_seconds(seconds):
    if not math.isfinite(seconds):
        return "?"
    seconds = int(max(0, seconds))
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)

    if d:
        return f"{d}d {h:02d}h {m:02d}m"
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"


# ============================================================
# PASS 1: BUCKET COUNTS
# ============================================================

def count_buckets(n, mode, progress_interval, max_trees=None):
    counts = Counter()
    last = time.time()

    for i, T in enumerate(nx.nonisomorphic_trees(n)):
        if max_trees is not None and i >= max_trees:
            break

        counts[bucket_key(T, mode)] += 1

        now = time.time()
        if now - last >= progress_interval:
            print(f"[bucket pass] generated={i+1:,}", flush=True)
            last = now

    return counts


# ============================================================
# COLLISION VERIFICATION
# ============================================================

def exact_match(engine, g6_a, g6_b):
    A = tree_from_graph6(g6_a)
    B = tree_from_graph6(g6_b)

    pa = engine.compute(A)
    pb = engine.compute(B)

    return pa == pb, pa


def save_report(path, n, bucket, ia, ib, g6_a, g6_b, engine, packed):
    A = tree_from_graph6(g6_a)
    B = tree_from_graph6(g6_b)

    data = {
        "n": n,
        "bucket": bucket,
        "tree_index_a": ia,
        "tree_index_b": ib,
        "graph6_a": g6_a,
        "graph6_b": g6_b,
        "degree_sequence_a": list(degree_sequence(A)),
        "degree_sequence_b": list(degree_sequence(B)),
        "leaf_count_a": leaf_count(A),
        "leaf_count_b": leaf_count(B),
        "min_color_sum_a": minimum_color_sum(A),
        "min_color_sum_b": minimum_color_sum(B),
        "coefficients": list(engine.coefficients(packed)),
    }

    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


# ============================================================
# SCAN
# ============================================================

def scan(args):
    n = args.n

    if n < 2:
        raise SystemExit("Please use n >= 2.")

    if not 0 <= args.shard_index < args.shards:
        raise SystemExit("Bad shard index.")

    db = Path(
        args.db
        or f"tree_search_CORRECTED_n{n}_shard{args.shard_index}-of-{args.shards}.sqlite"
    )

    con = connect_db(db)

    settings = {
        "program_version": "LEAF_COUNT_MIN_COLOR_SUM_V1",
        "n": n,
        "bucket_mode": args.bucket_mode,
        "shards": args.shards,
        "shard_index": args.shard_index,
    }

    for key, value in settings.items():
        old = meta_get(con, key)
        if old is not None and old != str(value):
            raise SystemExit(
                f"Database mismatch for {key}: database has {old}, "
                f"this run asks for {value}. Use a new database file."
            )
        meta_set(con, key, value)

    con.commit()

    engine = PackedPolynomialEngine(n)

    counts = None

    if not args.no_two_pass and args.bucket_mode != "none":
        print("Pass 1/2: counting buckets using the CORRECT minimum color sum...")
        counts = count_buckets(
            n,
            args.bucket_mode,
            args.progress_interval,
            args.max_trees,
        )

        non_singleton = sum(size >= 2 for size in counts.values())

        print(
            f"{len(counts):,} buckets total; "
            f"{non_singleton:,} non-singleton buckets."
        )

    resume_after = (
        int(meta_get(con, "last_tree_index", "-1"))
        if args.resume
        else -1
    )

    print()
    print("Pass 2/2: exact polynomial collision search")
    print(f"n           = {n}")
    print(f"bucket mode = {args.bucket_mode}")
    print(f"database    = {db}")
    print(f"resume after index = {resume_after}")
    print()

    generated = 0
    processed = 0
    singleton_skipped = 0
    shard_skipped = 0
    pending = 0

    start = time.time()
    last = start

    for i, T in enumerate(nx.nonisomorphic_trees(n)):
        if args.max_trees is not None and i >= args.max_trees:
            break

        generated = i + 1

        if i <= resume_after:
            continue

        if i % args.shards != args.shard_index:
            shard_skipped += 1
            continue

        bkey = bucket_key(T, args.bucket_mode)

        if counts is not None and counts[bkey] < 2:
            singleton_skipped += 1
            continue

        packed = engine.compute(T)

        if args.validate_every and processed % args.validate_every == 0:
            validate_tree(T, engine, packed, compare_slow=False)

        digest = engine.digest(packed)
        g6 = graph6_text(T)

        cur = con.execute(
            """
            INSERT OR IGNORE INTO seen(bucket,digest,graph6,tree_index)
            VALUES(?,?,?,?)
            """,
            (bkey, digest, g6, i),
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
                        (bkey, digest, old[0], g6, old[1], i),
                    )

                    con.commit()

                    report = (
                        args.collision_report
                        or f"COLLISION_CORRECTED_n{n}_{int(time.time())}.json"
                    )

                    save_report(
                        report,
                        n,
                        bkey,
                        old[1],
                        i,
                        old[0],
                        g6,
                        engine,
                        exact_poly,
                    )

                    print()
                    print("!" * 78)
                    print("EXACT COLLISION FOUND")
                    print("!" * 78)
                    print(f"bucket       : {bkey}")
                    print(f"tree A index : {old[1]}")
                    print(f"tree B index : {i}")
                    print(f"tree A graph6: {old[0]}")
                    print(f"tree B graph6: {g6}")
                    print(f"report       : {report}")
                    print("!" * 78)
                    print()

                    if args.stop_on_collision:
                        meta_set(con, "last_tree_index", i)
                        con.commit()
                        con.close()
                        return 0

        processed += 1
        pending += 1

        if pending >= args.commit_every:
            meta_set(con, "last_tree_index", i)
            meta_set(con, "processed_polynomials", processed)
            con.commit()
            pending = 0

        now = time.time()

        if now - last >= args.progress_interval:
            elapsed = now - start
            rate = processed / elapsed if elapsed > 0 else 0.0

            print(
                f"[search] generated={generated:,} "
                f"processed={processed:,} "
                f"rate={rate:,.2f} polys/s",
                flush=True,
            )

            last = now

    if generated:
        meta_set(con, "last_tree_index", generated - 1)

    meta_set(con, "processed_polynomials", processed)
    con.commit()

    collisions = con.execute(
        "SELECT COUNT(*) FROM collisions"
    ).fetchone()[0]

    stored = con.execute(
        "SELECT COUNT(*) FROM seen"
    ).fetchone()[0]

    print()
    print("=" * 78)
    print("SEARCH COMPLETE")
    print("=" * 78)
    print(f"generated              : {generated:,}")
    print(f"polynomials processed  : {processed:,}")
    print(f"stored hashes          : {stored:,}")
    print(f"exact collisions       : {collisions:,}")
    print(f"singleton skipped      : {singleton_skipped:,}")
    print(f"other-shard skipped    : {shard_skipped:,}")
    print(f"elapsed                : {fmt_seconds(time.time()-start)}")
    print(f"database               : {db}")

    con.close()
    return 0


# ============================================================
# MERGE SHARDS
# ============================================================

def merge(args):
    out = connect_db(args.output)

    infos = []

    for path in args.databases:
        con = sqlite3.connect(path)
        n = meta_get(con, "n")
        mode = meta_get(con, "bucket_mode")
        version = meta_get(con, "program_version")
        con.close()

        if version != "LEAF_COUNT_MIN_COLOR_SUM_V1":
            raise SystemExit(
                f"{path} was not created by the corrected version."
            )

        infos.append((path, int(n), mode))

    if len({x[1] for x in infos}) != 1:
        raise SystemExit("Shard n values do not match.")

    if len({x[2] for x in infos}) != 1:
        raise SystemExit("Shard bucket modes do not match.")

    n = infos[0][1]
    engine = PackedPolynomialEngine(n)

    merged = 0

    for path, _, _ in infos:
        print(f"Merging {path}...", flush=True)

        src = sqlite3.connect(path)

        for bucket, digest, g6, tree_index in src.execute(
            "SELECT bucket,digest,graph6,tree_index FROM seen"
        ):
            cur = out.execute(
                """
                INSERT OR IGNORE INTO seen(bucket,digest,graph6,tree_index)
                VALUES(?,?,?,?)
                """,
                (bucket, digest, g6, tree_index),
            )

            if cur.rowcount == 0:
                old = out.execute(
                    """
                    SELECT graph6,tree_index
                    FROM seen
                    WHERE bucket=? AND digest=?
                    """,
                    (bucket, digest),
                ).fetchone()

                if old is not None and old[0] != g6:
                    ok, _ = exact_match(engine, old[0], g6)

                    if ok:
                        out.execute(
                            """
                            INSERT INTO collisions(
                                bucket,digest,graph6_a,graph6_b,
                                tree_index_a,tree_index_b
                            )
                            VALUES(?,?,?,?,?,?)
                            """,
                            (
                                bucket,
                                digest,
                                old[0],
                                g6,
                                old[1],
                                tree_index,
                            ),
                        )

                        out.commit()

                        print("EXACT CROSS-SHARD COLLISION FOUND!")
                        print(f"A = {old[0]}")
                        print(f"B = {g6}")

                        if args.stop_on_collision:
                            src.close()
                            out.close()
                            return 0

            merged += 1

            if merged % args.commit_every == 0:
                out.commit()
                print(f"  merged {merged:,} rows", flush=True)

        src.close()
        out.commit()

    rows = out.execute(
        "SELECT COUNT(*) FROM seen"
    ).fetchone()[0]

    collisions = out.execute(
        "SELECT COUNT(*) FROM collisions"
    ).fetchone()[0]

    print(
        f"Merge complete: {rows:,} stored rows, "
        f"{collisions:,} exact collisions."
    )

    out.close()
    return 0


# ============================================================
# COMMAND LINE
# ============================================================

def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "High-performance Conjecture 21 collision search "
            "with exact minimum color sum."
        )
    )

    sub = parser.add_subparsers(dest="command", required=True)

    scan_parser = sub.add_parser("scan")
    scan_parser.add_argument("n", type=int)

    scan_parser.add_argument(
        "--bucket-mode",
        choices=["leaves+minsum", "leaves", "known", "none"],
        default="leaves+minsum",
    )

    scan_parser.add_argument("--db")
    scan_parser.add_argument("--resume", action="store_true")
    scan_parser.add_argument("--no-two-pass", action="store_true")
    scan_parser.add_argument("--commit-every", type=int, default=1000)
    scan_parser.add_argument("--progress-interval", type=float, default=10.0)
    scan_parser.add_argument("--validate-every", type=int, default=10000)
    scan_parser.add_argument("--shards", type=int, default=1)
    scan_parser.add_argument("--shard-index", type=int, default=0)
    scan_parser.add_argument("--max-trees", type=int)
    scan_parser.add_argument("--collision-report")

    scan_parser.add_argument(
        "--stop-on-collision",
        action=argparse.BooleanOptionalAction,
        default=True,
    )

    merge_parser = sub.add_parser("merge")
    merge_parser.add_argument("output")
    merge_parser.add_argument("databases", nargs="+")
    merge_parser.add_argument("--commit-every", type=int, default=5000)

    merge_parser.add_argument(
        "--stop-on-collision",
        action=argparse.BooleanOptionalAction,
        default=True,
    )

    sub.add_parser("self-test")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "self-test":
        self_test()
        return 0

    if args.command == "scan":
        return scan(args)

    if args.command == "merge":
        return merge(args)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
