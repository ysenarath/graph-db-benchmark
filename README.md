# Graph Database Benchmark

A reproducible benchmark comparing three embedded graph databases — all in-process, no server required:

| Database | Query language | Storage |
|---|---|---|
| [DuckDB](https://duckdb.org) + [DuckPGQ](https://duckpgq.org) | SQL/PGQ (SQL:2023) | columnar |
| [LadybugDB](https://ladybugdb.com) | Cypher | columnar (Kùzu-derived) |
| [CozoDB](https://cozodb.org) | Datalog | B-tree |

## Results

Full tables with p95 detail are in [`results/RESULTS.md`](results/RESULTS.md). Highlights below (median latency, large dataset — 1M nodes / 10M edges):

| Query | DuckDB + DuckPGQ | LadybugDB | CozoDB |
|---|---|---|---|
| Point Lookup | 0.2 ms | 0.2 ms | **0.1 ms** |
| 1-Hop Neighbor | 1.8 ms | **0.6 ms** | **0.1 ms** |
| 2-Hop Traversal | 3.0 ms | 2.4 ms | **0.2 ms** |
| 3-Hop Traversal | 7.3 ms | 6.5 ms | **1.3 ms** |
| Shortest Path | 11,715 ms | **205 ms** | 9,146 ms |
| Temporal Filter (3-hop) | **25 ms** | 216 ms | 4,716 ms |
| Pattern Match (A→B→C) | **28 ms** | 148 ms | **16 ms** |
| **Bulk Ingest** | **6.7 s** | 17.1 s | 42.5 s |

### When to pick which

| Workload | Best |
|---|---|
| Graph traversal (hops, reachability) | **CozoDB** — constant time, scales with degree not graph size |
| Temporal filtering on edges | **DuckDB** — secondary index on `ts`, 25 ms vs 4.7 s at large scale |
| Shortest path | **LadybugDB** — 57× faster than DuckDB, 45× faster than CozoDB |
| Pattern matching | **DuckDB** — vectorized SQL joins |
| Bulk ingest | **DuckDB** — direct Parquet read |

CozoDB's hop traversal is constant-time because edges are B-tree indexed by `{src, dst, edge_type}` — each hop is an O(degree) range scan, not O(|E|). This means 3-hop on 10M edges takes the same time as on 50K edges.

CozoDB's temporal filter is 192× slower than DuckDB on the large dataset. This is structural: CozoDB has no secondary index on `ts`, so any timestamp range filter requires a full edge scan. Investigated and confirmed not a fairness bug — see [`results/RESULTS.md`](results/RESULTS.md).

## Reproduce

```bash
git clone https://github.com/ysenarath/graph-db-benchmark
cd graph-db-benchmark
uv sync
uv run python generate_data.py   # ~3s; creates data/ with Parquet files
uv run python run_all.py         # runs all three DBs; ~10–30 min for large tier
```

Or benchmark a single database:

```bash
uv run python benchmark_duckdb.py
uv run python benchmark_ladybug.py
uv run python benchmark_cozo.py
uv run python report.py           # regenerate results/RESULTS.md from JSON
```

Data files are not committed (the large Parquet is 171 MB). `generate_data.py` uses a fixed seed (`np.random.default_rng(42)`) so the dataset is identical on every run.

## Dataset

Synthetic property graph generated with seed 42:

| Tier | Nodes | Edges |
|---|---|---|
| Small | 10,000 | 50,000 |
| Medium | 100,000 | 1,000,000 |
| Large | 1,000,000 | 10,000,000 |

Node properties: `id`, `category` (8 values), `value` (float), `ts` (Unix ms, spread over 2024)  
Edge properties: `src`, `dst`, `edge_type` (5 values), `ts` (Unix ms)

## Methodology

- 3 warmup runs, 20 timed runs per query
- Statistics: min / median / p95 / max
- Ingest: single cold-start timing, separate from query loop
- Each database runs in isolation (no concurrency)
- Idiomatic indexing for each engine (B-tree on `id`, `src`, `dst`, `ts` for DuckDB; native indexes for LadybugDB; key-position binding for CozoDB)
- Where a query type has no direct equivalent, the closest idiomatic workaround is used and documented

## Versions

| Package | Version |
|---|---|
| Python | 3.13.13 |
| `duckdb` | 1.5.4 |
| DuckPGQ | community extension (auto-installed) |
| `ladybug` | 0.18.0 |
| `pycozo` + `cozo-embedded` | 0.7.6 |

See [`environment.md`](environment.md) for full system info and workaround notes.

## Implementation notes

- **LadybugDB shortest path** uses the native `[:Edge* SHORTEST]` syntax from the LadybugDB Python tutorial. This triggers an early-terminating BFS that stops on first hit — 57× faster than DuckDB's `ANY SHORTEST` at large scale. Results verified against Python BFS ground truth.
- **LadybugDB 2/3-hop traversal** uses `[:Edge*2..2]` / `[:Edge*3..3]` (variable-length exact-hop) instead of chained `MATCH`. Profiling via `PROFILE` showed the chained form triggers a full `SCAN_NODE_TABLE` + `SCAN_REL_TABLE` then hash-join; the `*N..N` form triggers `RECURSIVE_EXTEND`, which follows edges forward from the source. ~25% faster on 2-hop, ~50–62% faster on 3-hop.
- **DuckPGQ `LABEL` keyword** not supported in DuckDB 1.5.4 community extension. Table names used as labels.
- **CozoDB point/1-hop queries** use key-position parameter binding (`*relation[$param, ...]`) rather than predicate-style (`x = $param`) to get index lookup instead of full scan.
