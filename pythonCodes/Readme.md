# Tree Collision Search

This project searches for **collisions among non-isomorphic trees** on \(n\) vertices.

A collision is a pair of non-isomorphic trees \(T_1\) and \(T_2\) such that they have the same specialized chromatic symmetric function:

\[
F_T(q) = X_T(1, q, q^2, \dots, q^{n-1}).
\]

The repository contains two implementations:

- `tree_collision_search_CORRECTED.py` — the main, feature-complete, and safer implementation.
- `collision_parallel.py` — a multiprocessing-oriented implementation that imports the computational engine from the corrected script.

---

## Features

- Enumerates non-isomorphic trees using `networkx.nonisomorphic_trees`.
- Computes the exact minimum color sum of a tree.
- Computes specialized chromatic symmetric polynomials using dynamic programming.
- Uses packed integer polynomial representations for efficient exact arithmetic.
- Stores processed trees and verified collisions in SQLite databases.
- Supports deterministic sharding across several independent processes.
- Supports checkpointing and resuming interrupted scans.
- Produces JSON reports for confirmed collisions.
- Provides a self-test mode for validating the polynomial engine.

---

## Requirements

- Python 3
- `networkx`

Install the external dependency with:
```bash
pip install networkx
