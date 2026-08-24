# Tree Collision Search

A computational framework for searching for collisions between non-isomorphic trees under the principal specialization of the chromatic symmetric function.

The project computes

[
F_T(q) = X_T(1,q,q^2,\ldots,q^{n-1}),
]

for non-isomorphic trees (T) on (n) vertices, and searches for distinct trees having the same specialized polynomial.

The implementation provides both an **exact single-process search** and an **optimized parallel search using multiprocessing and sharding**.

---

## Project Structure

```text
.
├── tree_collision_search_CORRECTED.py
├── collision_parallel.py
└── README.md
```

### `tree_collision_search_CORRECTED.py`

The main exact implementation.

It provides:

* Enumeration of non-isomorphic trees
* Exact computation of the specialized polynomial
* Exact computation of the minimum color sum
* Structural bucketing
* Compact packed-integer polynomial representation
* BLAKE2b-256 hashing
* SQLite-based collision storage
* Exact verification after hash matches
* Checkpoint/resume support
* Optional sharding
* Shard merging
* Progress reporting
* Independent self-tests

### `collision_parallel.py`

A multiprocessing-based implementation designed for larger searches.

It:

* Splits the tree indices into independent shards
* Runs multiple shards concurrently
* Gives each shard its own SQLite database
* Processes trees in batches
* Uses optimized SQLite settings
* Supports resuming partially completed shards
* Merges all shard databases after processing
* Performs exact verification of cross-shard collisions

---

# 1. Mathematical Background

Let (T) be a tree with (n) vertices.

The chromatic symmetric function of (T) is

[
X_T = \sum_{\kappa} x_{\kappa(v_1)}x_{\kappa(v_2)}\cdots x_{\kappa(v_n)},
]

where the sum is over all proper colorings (\kappa) of the vertices of (T).

A coloring is **proper** if adjacent vertices receive different colors.

This project studies the principal specialization

[
F_T(q)
======

X_T(1,q,q^2,\ldots,q^{n-1}).
]

Therefore, every vertex colored with color (c) contributes

[
q^c.
]

Consequently, a proper coloring contributes

[
q^{\sum_{v\in V(T)} c(v)}.
]

Hence,

[
F_T(q)
======

\sum_{\kappa\text{ proper}}
q^{\sum_{v\in V(T)}c(v)}.
]

The goal is to determine whether two **non-isomorphic trees** (T_1) and (T_2) can satisfy

[
F_{T_1}(q)=F_{T_2}(q).
]

Such a pair is called a **collision** in this search.

---

# 2. Exact Polynomial Computation

The polynomial is computed using dynamic programming on the tree.

The tree is rooted at its center.

For a vertex (v), let

[
P[v][c]
]

denote the polynomial contributed by the subtree rooted at (v), assuming that (v) has color (c).

Then

[
P[v][c]
=======

q^c
\prod_{u\text{ child of }v}
\left(
\sum_{d\ne c}P[u][d]
\right).
]

The final polynomial is

[
F_T(q)
======

\sum_c P[r][c],
]

where (r) is the chosen root.

The implementation uses colors

[
0,1,\ldots,n-1.
]

For a tree on (n) vertices, this is sufficient for the computation.

---

# 3. Packed Polynomial Representation

Directly storing every polynomial as a Python list of coefficients can become expensive.

The implementation therefore uses a packed-integer representation.

Suppose

[
P(q)=a_0+a_1q+\cdots+a_Dq^D.
]

Choose a base

[
B=2^{b}
]

large enough that every coefficient is smaller than (B).

The polynomial is represented by

[
a_0+a_1B+a_2B^2+\cdots+a_DB^D.
]

Since the base is larger than every coefficient, polynomial multiplication can be performed using integer multiplication without coefficient carries.

This allows the implementation to use Python's highly optimized arbitrary-precision integer arithmetic.

The class responsible for this representation is:

```python
PackedPolynomialEngine
```

It provides methods for:

* Computing the exact polynomial
* Extracting coefficients
* Computing the coefficient sum
* Finding the minimum exponent
* Computing a BLAKE2b-256 digest

---

# 4. Minimum Color Sum

An important correction in this implementation is the computation of the minimum possible exponent of (F_T(q)).

For a proper coloring (c), define

[
S(c)=\sum_{v\in V(T)}c(v).
]

The minimum color sum is

[
m(T)=\min_c S(c),
]

where the minimum is taken over all proper colorings.

The code computes this quantity **exactly** using a separate tree dynamic program.

For a vertex (v),

[
dp[v][c]
]

is the minimum color sum of the subtree rooted at (v), assuming (v) receives color (c).

The recurrence is

[
dp[v][c]
========

c+
\sum_{u\text{ child of }v}
\min_{d\ne c}dp[u][d].
]

To make the forbidden-color query efficient, the implementation stores the smallest and second-smallest values of each child's DP array.

Therefore, for a child (u),

[
\min_{d\ne c}dp[u][d]
]

can be obtained in (O(1)) time.

The minimum color sum is then

[
m(T)=\min_c dp[r][c].
]

### Important

The implementation does **not** assume that the minimum color sum is equal to the size of a bipartition class.

It is computed independently and exactly.

---

# 5. Bucketization

Before comparing polynomials, trees can optionally be divided into buckets.

A collision can only occur between trees satisfying the same selected bucket condition.

The following modes are available:

| Mode            | Bucket condition                                 |
| --------------- | ------------------------------------------------ |
| `leaves+minsum` | Same leaf count and same exact minimum color sum |
| `leaves`        | Same leaf count                                  |
| `known`         | Same exact minimum color sum                     |
| `none`          | No structural filtering                          |

The default is:

```text
leaves+minsum
```

For example, a bucket may look like:

```text
l=7|m=15
```

where:

* `l=7` means the tree has 7 leaves
* `m=15` means its exact minimum color sum is 15

This filtering can significantly reduce the number of polynomial comparisons.

---

# 6. Two-Pass Search

The corrected implementation optionally uses two passes.

## Pass 1 — Bucket Counting

All non-isomorphic trees are generated and their bucket sizes are counted.

Buckets containing only one tree cannot contain a collision.

Therefore, singleton buckets can be skipped during the expensive polynomial computation.

Example:

```text
Pass 1/2: counting buckets using the CORRECT minimum color sum...
```

The program reports:

```text
123,456 buckets total;
7,890 non-singleton buckets.
```

## Pass 2 — Polynomial Search

Only trees that can potentially participate in a collision are processed.

For each tree:

1. Compute its bucket.
2. Compute its exact specialized polynomial.
3. Compute its BLAKE2b-256 digest.
4. Search for a previously stored polynomial with the same bucket and digest.
5. If a candidate exists, recompute both polynomials exactly.
6. Record the collision if the polynomials are genuinely equal.

---

# 7. Hashing and Exact Verification

The polynomial itself can be very large.

Therefore, the implementation stores a compact cryptographic digest:

```text
BLAKE2b-256
```

The database key is

```text
(bucket, digest)
```

However, a hash match is **never** considered sufficient evidence of a collision.

After a hash match, the program reconstructs both trees and computes their polynomials again:

```python
ok, exact_poly = exact_match(engine, old[0], g6)
```

Only if

```python
pa == pb
```

is the pair recorded as an exact collision.

Thus the workflow is:

```text
Polynomial
    │
    ▼
BLAKE2b-256
    │
    ▼
Hash match?
    │
    ├── No ──> Continue
    │
    └── Yes
          │
          ▼
    Exact polynomial recomputation
          │
          ▼
    Equal?
      │       │
     No      Yes
      │       │
      ▼       ▼
   Ignore   Collision
```

---

# 8. Tree Identification

Trees are stored using the `graph6` representation provided by NetworkX.

For example:

```python
g6 = graph6_text(T)
```

The graph6 string provides a compact representation of the tree and allows it to be reconstructed later:

```python
tree_from_graph6(g6)
```

The database therefore does not need to store the complete NetworkX graph object.

---

# 9. SQLite Database

The search uses SQLite to maintain persistent state.

The database contains three main tables.

## `meta`

Stores configuration and checkpoint information.

Examples:

```text
program_version
n
bucket_mode
shards
shard_index
last_tree_index
processed_polynomials
```

## `seen`

Stores previously encountered polynomial hashes.

Conceptually:

```text
bucket
digest
graph6
tree_index
```

The primary key is:

```text
(bucket, digest)
```

## `collisions`

Stores confirmed exact collisions.

It includes:

```text
bucket
digest
graph6_a
graph6_b
tree_index_a
tree_index_b
created_at
```

---

# 10. Checkpoint and Resume

The search can resume from a previous checkpoint.

For example:

```bash
python tree_collision_search_CORRECTED.py scan 22 --resume
```

The program reads the last processed tree index from SQLite and continues from there.

This is useful for searches that may run for many hours or days.

---

# 11. Running the Corrected Single-Process Search

Install the required dependency:

```bash
pip install networkx
```

Then run:

```bash
python tree_collision_search_CORRECTED.py scan 19
```

The default configuration is:

```text
bucket mode = leaves+minsum
shards      = 1
shard index = 0
```

A typical command with explicit options is:

```bash
python tree_collision_search_CORRECTED.py scan 19 \
    --bucket-mode leaves+minsum \
    --progress-interval 10 \
    --commit-every 1000 \
    --validate-every 10000
```

On Windows, the same command can be written as:

```powershell
python tree_collision_search_CORRECTED.py scan 19 --bucket-mode leaves+minsum --progress-interval 10 --commit-every 1000 --validate-every 10000
```

---

# 12. Available Scan Options

The `scan` command supports:

```text
--bucket-mode
--db
--resume
--no-two-pass
--commit-every
--progress-interval
--validate-every
--shards
--shard-index
--max-trees
--collision-report
--stop-on-collision
```

### Bucket mode

```bash
--bucket-mode leaves+minsum
```

Available modes:

```text
leaves+minsum
leaves
known
none
```

### Resume

```bash
--resume
```

Continue from the checkpoint stored in the database.

### Disable two-pass search

```bash
--no-two-pass
```

This skips the initial bucket-counting pass.

### Commit frequency

```bash
--commit-every 1000
```

Controls how frequently progress is committed to SQLite.

A larger value can reduce database overhead but means that more progress may need to be repeated after an unexpected interruption.

### Progress interval

```bash
--progress-interval 10
```

Print progress approximately every 10 seconds.

### Validation

```bash
--validate-every 10000
```

Periodically performs consistency checks on computed polynomials.

### Limit the number of trees

Useful for testing:

```bash
--max-trees 1000
```

This does **not** perform a complete search; it limits the enumeration to the specified number of trees.

---

# 13. Self-Test

Before performing a large computation, the implementation can be tested with:

```bash
python tree_collision_search_CORRECTED.py self-test
```

The self-test checks all non-isomorphic trees for

```text
n = 2, 3, 4, 5, 6, 7
```

For each tree it verifies:

1. The total coefficient sum.
2. The minimum exponent.
3. The packed polynomial against an independent slow implementation.

The expected final message is:

```text
CORRECTED SELF-TEST PASSED.
```

This provides an important sanity check before starting a large search.

---

# 14. Parallel Search

For larger values of (n), `collision_parallel.py` provides a multiprocessing implementation.

The main idea is to divide the enumeration into independent shards.

For (S) shards, a tree with index (i) belongs to shard

[
i\bmod S.
]

Therefore:

```text
shard 0: 0, S, 2S, 3S, ...
shard 1: 1, S+1, 2S+1, ...
...
shard S-1: S-1, 2S-1, ...
```

Each shard has its own SQLite database.

For example:

```text
optimized_n22/
├── shard_0.sqlite
├── shard_1.sqlite
├── shard_2.sqlite
├── ...
├── shard_7.sqlite
└── merged.sqlite
```

This prevents multiple worker processes from writing to the same SQLite database during the main computation.

---

# 15. Multiprocessing Architecture

Suppose:

```text
shards  = 8
workers = 4
```

The program creates 8 shards but runs at most 4 worker processes simultaneously.

Conceptually:

```text
                    Tree Enumeration
                           │
             ┌─────────────┼─────────────┐
             │             │             │
          Shard 0       Shard 1       Shard 2 ...
             │             │             │
             ▼             ▼             ▼
          SQLite         SQLite        SQLite
             │             │             │
             └─────────────┼─────────────┘
                           ▼
                    Merge Shards
                           │
                           ▼
                    merged.sqlite
```

The number of simultaneously running workers is:

```python
min(workers, shards)
```

---

# 16. Running the Parallel Search

For example:

```bash
python collision_parallel.py --n 22 --shards 8 --workers 4
```

A more explicit configuration:

```bash
python collision_parallel.py \
    --n 22 \
    --batch-size 1000 \
    --shards 8 \
    --workers 4 \
    --bucket-mode leaves+minsum
```

On Windows PowerShell:

```powershell
python collision_parallel.py --n 22 --batch-size 1000 --shards 8 --workers 4 --bucket-mode leaves+minsum
```

---

# 17. Parallel Search Parameters

## `--n`

Number of vertices in each tree.

Example:

```bash
--n 22
```

## `--batch-size`

Number of trees processed before the worker writes a checkpoint.

Example:

```bash
--batch-size 1000
```

Larger batches can reduce overhead but may increase memory usage.

## `--shards`

Number of independent partitions.

Example:

```bash
--shards 8
```

## `--workers`

Number of simultaneously running Python processes.

Example:

```bash
--workers 4
```

A reasonable starting point is usually the number of available CPU cores, but the optimal value depends on CPU, RAM, and storage performance.

## `--bucket-mode`

Available values:

```text
leaves+minsum
leaves
known
none
```

The default is:

```text
leaves+minsum
```

---

# 18. Batch Processing

The parallel implementation does not necessarily process every tree individually with a database commit.

Instead, trees are accumulated into batches:

```text
Tree
Tree
Tree
...
Tree
    │
    ▼
Batch
    │
    ▼
Polynomial computation
    │
    ▼
SQLite update
    │
    ▼
Checkpoint
```

The batch size is controlled by:

```bash
--batch-size
```

For example:

```bash
--batch-size 5000
```

---

# 19. Resuming Parallel Shards

Each shard maintains its own checkpoint:

```text
last_processed
```

Therefore, if a worker stops unexpectedly, its shard can continue from the stored index rather than starting from the beginning.

This is particularly useful for long-running computations.

---

# 20. Merging Shards

After all workers finish, the program automatically merges the shard databases.

For example:

```text
shard_0.sqlite
shard_1.sqlite
...
shard_7.sqlite
```

are merged into:

```text
merged.sqlite
```

During the merge, the program checks for duplicate `(bucket, digest)` pairs.

If the same digest appears in two different shards, the candidate trees are recomputed exactly.

Therefore, collisions that occur between trees belonging to different shards are also detected.

---

# 21. Cross-Shard Collision Detection

A collision can occur between:

```text
Tree A → shard 2
Tree B → shard 7
```

Neither shard necessarily knows about the other tree while processing independently.

The merge step solves this problem.

Conceptually:

```text
Shard 2
   │
   │ Tree A
   ▼
 merged.sqlite
                    ┐
                    │ same bucket + digest
                    │
Shard 7             │
   │                │
   │ Tree B         │
   ▼                ▼
 merged.sqlite → exact verification
                    │
                    ▼
              Exact collision
```

Thus, sharding does not remove cross-shard collision detection.

---

# 22. Collision Reports

When an exact collision is found, a JSON report is generated.

A report contains information such as:

```json
{
  "n": 22,
  "bucket": "l=7|m=15",
  "tree_index_a": 12345,
  "tree_index_b": 67890,
  "graph6_a": "...",
  "graph6_b": "...",
  "degree_sequence_a": [4, 3, 2, 2, 1, 1],
  "degree_sequence_b": [4, 3, 2, 2, 1, 1],
  "leaf_count_a": 3,
  "leaf_count_b": 3,
  "min_color_sum_a": 15,
  "min_color_sum_b": 15,
  "coefficients": [...]
}
```

This makes the result independently inspectable.

---

# 23. Collision Definition

The program reports a collision only when all of the following hold:

1. The two objects are different graph6 representations.
2. They occur as distinct non-isomorphic trees in the enumeration.
3. They belong to the same selected bucket.
4. Their BLAKE2b-256 hashes match.
5. Their complete packed polynomial representations are exactly equal.

The final condition is decisive:

[
F_{T_1}(q)=F_{T_2}(q).
]

A hash match alone is never treated as proof of a collision.

---

# 24. Useful Output Information

During execution, the program reports information such as:

```text
generated
processed
rate
stored hashes
exact collisions
singleton skipped
other-shard skipped
elapsed time
```

For example:

```text
[search] generated=100,000 processed=42,000 rate=125.30 polys/s
```

The `processed` count refers to trees for which the polynomial was actually computed.

The `generated` count refers to the number of trees reached in the enumeration.

---

# 25. Performance Considerations

The computational cost grows rapidly with (n) because the number of non-isomorphic trees increases quickly.

For this reason, the implementation combines several optimizations:

### 1. Non-isomorphic enumeration

NetworkX generates each unlabeled tree only once.

### 2. Structural buckets

Trees that cannot belong to the same bucket are not compared.

### 3. Exact minimum-color-sum DP

The minimum color sum is computed efficiently using tree DP.

### 4. Packed polynomials

Large coefficient vectors are represented as Python integers.

### 5. Hashing

Instead of comparing large polynomial objects repeatedly, BLAKE2b-256 is used as a compact candidate key.

### 6. Exact verification

Hash matches are verified by recomputing the actual polynomial.

### 7. SQLite persistence

Search progress survives process termination.

### 8. Sharding

Different parts of the tree enumeration can be processed independently.

### 9. Multiprocessing

Several shards can be processed simultaneously on multiple CPU cores.

---

# 26. Recommended Workflow

For a large search, the following workflow is recommended.

### Step 1 — Run the self-test

```bash
python tree_collision_search_CORRECTED.py self-test
```

Make sure it ends with:

```text
CORRECTED SELF-TEST PASSED.
```

### Step 2 — Run a small test

For example:

```bash
python tree_collision_search_CORRECTED.py scan 10 --max-trees 1000
```

### Step 3 — Run the full single-process implementation

```bash
python tree_collision_search_CORRECTED.py scan 19
```

### Step 4 — For larger searches, use multiprocessing

```bash
python collision_parallel.py \
    --n 22 \
    --shards 8 \
    --workers 4 \
    --batch-size 1000
```

### Step 5 — Preserve the generated databases

The SQLite databases contain the persistent search state and collision information.

---

# 27. Reproducibility

For reproducible experiments, record at least:

```text
n
bucket mode
number of shards
number of workers
batch size
program version
Python version
NetworkX version
operating system
```

The corrected implementation stores important configuration parameters in the SQLite `meta` table.

A database cannot be reused with incompatible search settings without creating a new database.

---

# 28. Dependencies

The project requires:

* Python 3.9+
* NetworkX
* SQLite (included with standard Python installations)

Install NetworkX with:

```bash
pip install networkx
```

No external database server is required.

---

# 29. Important Implementation Note

The two implementations use slightly different SQLite configurations.

The corrected single-process implementation prioritizes safer persistent operation:

```text
WAL
synchronous=NORMAL
```

The parallel implementation uses more aggressive settings for temporary shard databases:

```text
journal_mode=OFF
synchronous=OFF
```

The latter can provide better performance, but it provides weaker durability guarantees if a process or machine fails during a database write.

The shard databases are therefore best regarded as intermediate computation artifacts that can be regenerated if necessary.

---

# 30. Summary

This project performs an exact computational search for collisions of the principal specialization

[
F_T(q)=X_T(1,q,q^2,\ldots,q^{n-1})
]

over non-isomorphic trees.

The main implementation combines:

```text
Non-isomorphic tree enumeration
            ↓
Exact minimum-color-sum DP
            ↓
Structural bucketization
            ↓
Exact polynomial tree-DP
            ↓
Packed integer representation
            ↓
BLAKE2b-256 hashing
            ↓
SQLite persistence
            ↓
Exact collision verification
```

For large searches, the computation can additionally be parallelized:

```text
                All non-isomorphic trees
                         │
                         ▼
                 Modular sharding
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
       Shard 0        Shard 1        Shard 2 ...
          │              │              │
       Worker          Worker         Worker
          │              │              │
          └──────────────┼──────────────┘
                         ▼
                  Merge databases
                         │
                         ▼
              Cross-shard verification
                         │
                         ▼
                Exact collisions
```

The key design principle is that **hashes and structural buckets are used only to accelerate the search; the final collision decision is always made by exact polynomial equality.**
