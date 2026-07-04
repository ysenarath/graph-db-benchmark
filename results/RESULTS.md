# Graph Database Benchmark Results

Databases compared: **DuckDB + DuckPGQ**, **LadybugDB**, **CozoDB**  
Methodology: 3 warmup runs + 20 timed runs per query. Latency in milliseconds.

## Query Latency — Small Dataset

_Median latency (ms). Lower is better._

| Query | DuckDB + DuckPGQ | LadybugDB | CozoDB |
|---|---|---|---|
| Point Lookup (by id) | 0.1 ms | 0.2 ms | 0.1 ms |
| 1-Hop Neighbor Expansion | 0.4 ms | 0.6 ms | 0.1 ms |
| 2-Hop Traversal | 0.8 ms | 1.4 ms | 0.1 ms |
| 3-Hop Traversal | 1.4 ms | 1.4 ms | 0.2 ms |
| Shortest Path | 58.1 ms | 5.1 ms | 29.9 ms |
| Filtered Traversal (temporal, 3-hop) | 0.9 ms | 6.2 ms | 16.8 ms |
| Pattern Match (A→B→C, B.category filter) | 1.6 ms | 4.0 ms | 11.9 ms |

### Small — P95 Latency Detail

| Query | DuckDB + DuckPGQ p95 | LadybugDB p95 | CozoDB p95 |
|---|---|---|---|
| Point Lookup (by id) | 0.2 ms | 0.3 ms | 0.1 ms |
| 1-Hop Neighbor Expansion | 0.7 ms | 0.6 ms | 0.1 ms |
| 2-Hop Traversal | 0.9 ms | 1.5 ms | 0.1 ms |
| 3-Hop Traversal | 1.5 ms | 1.5 ms | 0.2 ms |
| Shortest Path | 64.9 ms | 5.3 ms | 36.6 ms |
| Filtered Traversal (temporal, 3-hop) | 0.9 ms | 6.5 ms | 17.0 ms |
| Pattern Match (A→B→C, B.category filter) | 1.9 ms | 4.1 ms | 13.4 ms |

## Query Latency — Medium Dataset

_Median latency (ms). Lower is better._

| Query | DuckDB + DuckPGQ | LadybugDB | CozoDB |
|---|---|---|---|
| Point Lookup (by id) | 0.1 ms | 0.2 ms | 0.1 ms |
| 1-Hop Neighbor Expansion | 0.6 ms | 0.9 ms | 0.1 ms |
| 2-Hop Traversal | 1.3 ms | 3.6 ms | 0.1 ms |
| 3-Hop Traversal | 2.9 ms | 4.8 ms | 0.6 ms |
| Shortest Path | 1090.1 ms | 19.9 ms | 625.0 ms |
| Filtered Traversal (temporal, 3-hop) | 5.9 ms | 88.4 ms | 446.3 ms |
| Pattern Match (A→B→C, B.category filter) | 5.4 ms | 27.3 ms | 16.0 ms |

### Medium — P95 Latency Detail

| Query | DuckDB + DuckPGQ p95 | LadybugDB p95 | CozoDB p95 |
|---|---|---|---|
| Point Lookup (by id) | 0.1 ms | 0.3 ms | 0.1 ms |
| 1-Hop Neighbor Expansion | 0.8 ms | 1.0 ms | 0.1 ms |
| 2-Hop Traversal | 2.6 ms | 3.9 ms | 0.1 ms |
| 3-Hop Traversal | 3.5 ms | 5.0 ms | 0.6 ms |
| Shortest Path | 1154.0 ms | 20.4 ms | 638.0 ms |
| Filtered Traversal (temporal, 3-hop) | 7.5 ms | 92.2 ms | 459.0 ms |
| Pattern Match (A→B→C, B.category filter) | 5.8 ms | 28.8 ms | 16.6 ms |

## Query Latency — Large Dataset

_Median latency (ms). Lower is better._

| Query | DuckDB + DuckPGQ | LadybugDB | CozoDB |
|---|---|---|---|
| Point Lookup (by id) | 0.2 ms | 0.2 ms | 0.1 ms |
| 1-Hop Neighbor Expansion | 1.8 ms | 0.6 ms | 0.1 ms |
| 2-Hop Traversal | 3.0 ms | 2.4 ms | 0.2 ms |
| 3-Hop Traversal | 7.3 ms | 6.5 ms | 1.3 ms |
| Shortest Path | 11714.8 ms | 205.1 ms | 9146.3 ms |
| Filtered Traversal (temporal, 3-hop) | 24.6 ms | 215.9 ms | 4715.6 ms |
| Pattern Match (A→B→C, B.category filter) | 28.3 ms | 147.9 ms | 15.8 ms |

### Large — P95 Latency Detail

| Query | DuckDB + DuckPGQ p95 | LadybugDB p95 | CozoDB p95 |
|---|---|---|---|
| Point Lookup (by id) | 0.2 ms | 0.3 ms | 0.1 ms |
| 1-Hop Neighbor Expansion | 2.1 ms | 0.7 ms | 0.1 ms |
| 2-Hop Traversal | 3.7 ms | 2.5 ms | 0.6 ms |
| 3-Hop Traversal | 7.7 ms | 13.8 ms | 1.6 ms |
| Shortest Path | 12379.6 ms | 224.5 ms | 9425.2 ms |
| Filtered Traversal (temporal, 3-hop) | 25.7 ms | 238.6 ms | 4745.9 ms |
| Pattern Match (A→B→C, B.category filter) | 31.2 ms | 152.2 ms | 16.7 ms |

## Bulk Ingest / Load Time

_Cold-start ingest time (ms) for each dataset size._

| Size | DuckDB + DuckPGQ | LadybugDB | CozoDB |
|---|---|---|---|
| Small | 66.6 ms | 126.0 ms | 220.6 ms |
| Medium | 924.9 ms | 2421.7 ms | 4156.5 ms |
| Large | 6712.2 ms | 17110.1 ms | 42520.8 ms |

## Anomaly Flags

- **large/filtered_traversal**: CozoDB is 192× slower than DuckDB + DuckPGQ (4715.6 ms vs 24.6 ms).
  **Investigated — structural difference, not a fairness bug.**
  CozoDB's edge relation is keyed on `{src, dst, edge_type}` with no secondary index on `ts`.
  Any timestamp range filter requires a full edge scan; with RocksDB this also incurs block I/O.
  DuckDB has an explicit `CREATE INDEX idx_edges_ts ON edges(ts)` and uses it in the CTE.
  **Implication**: if your workload involves frequent temporal filtering, CozoDB is the wrong choice at scale.

- **large/shortest_path**: LadybugDB is 57× faster than DuckDB (205 ms vs 11,715 ms) and 45× faster
  than CozoDB (205 ms vs 9,146 ms). **Investigated — genuine algorithm difference.**
  LadybugDB's `[:Edge* SHORTEST]` uses a native early-terminating BFS that stops as soon as the
  target is reached. DuckDB's `ANY SHORTEST` and CozoDB's `ShortestPathBFS` complete the full BFS
  frontier at each depth level before declaring the result.

## Errors / Unsupported Operations

_No errors or unsupported operations — all queries use each engine's idiomatic native syntax._

## Performance Notes

### LadybugDB traversal: variable-length path syntax is faster than chained MATCH

Using `[:Edge*N..N]` (variable-length exact-hop syntax) instead of chained MATCH triggers
LadybugDB's `RECURSIVE_EXTEND` operator instead of a nested hash join plan. The hash join plan
does a full `SCAN_NODE_TABLE` + full `SCAN_REL_TABLE` then hash-filters to the reachable set;
the recursive plan follows edges directly from the starting node. Confirmed via `PROFILE`.

| | 2-hop improvement | 3-hop improvement |
|---|---|---|
| Small | -24% | -50% |
| Medium | -25% | **-62%** |
| Large | -8% | -50% |

### CozoDB hop traversals scale with out-degree, not graph size

CozoDB's 2-hop / 3-hop times remain low across all sizes (0.1–1.3 ms on large) because edges are
indexed by `{src, dst, edge_type}` — each hop is an O(degree) B-tree range scan, not O(|E|).
RocksDB block cache keeps hot index pages in memory after warmup.

### LadybugDB shortest path is genuinely fast via native `* SHORTEST`

The `[:Edge* SHORTEST]` syntax invokes an early-terminating BFS that stops on first hit.
Results confirmed correct against Python BFS ground truth (6 / 5 / 6 hops for small / medium / large).

## Recommendation (data-driven only)

Aggregate median latency across all 7 query types × small + medium datasets (14 pairs each):

1. **Winner** — **LadybugDB**: avg 11.7 ms/query
2. **2nd** — **CozoDB (RocksDB)**: avg 81.9 ms/query
3. **3rd** — **DuckDB + DuckPGQ**: avg 83.5 ms/query

LadybugDB's lead is almost entirely driven by shortest path (5 ms vs 1090 ms at medium). Strip
that query out and CozoDB leads on traversal, DuckDB leads on filtering and pattern match.

**By workload type:**

| Workload | Best choice |
|---|---|
| Shortest path | **LadybugDB** — native `* SHORTEST`, 45–57× faster than the others at large scale |
| Graph traversal (1–3 hop) | **CozoDB** — constant-time B-tree hops; LadybugDB improved but still 5–50× slower |
| Temporal filtering on edges | **DuckDB** — secondary `ts` index; 6 ms vs 446 ms at medium |
| Pattern matching (subgraph) | **DuckDB** — vectorised SQL joins |
| Bulk ingest speed | **DuckDB** — direct Parquet read (6.7 s vs 17 s vs 42.5 s for large) |

## Vector Search Benchmark

Embedding: 128-dim float32 unit vectors, cosine metric.  
HNSW index built after data load. 3 warmup + 20 timed runs per query.

### HNSW Index Build Time

_Cold-start time to build the HNSW index after all data is loaded._

| Size | DuckDB + vss | LadybugDB | CozoDB |
|---|---|---|---|
| Small | 353.2 ms | 3053.2 ms | 108186.9 ms |
| Medium | 4506.8 ms | 33758.8 ms | — |
| Large | 78225.0 ms | 438820.4 ms | — |

### kNN Search (k=10, cosine)

_Median latency (ms). Lower is better._

| Size | DuckDB + vss | LadybugDB | CozoDB |
|---|---|---|---|
| Small | 0.8 ms | 3.5 ms | 3.6 ms |
| Medium | 1.1 ms | 6.4 ms | — |
| Large | 1.1 ms | 186.5 ms | — |

### Hybrid: kNN → 1-hop expansion

_Median latency (ms). Lower is better._

| Size | DuckDB + vss | LadybugDB | CozoDB |
|---|---|---|---|
| Small | 1.4 ms | 12.7 ms | 3.6 ms |
| Medium | 2.3 ms | 262.5 ms | — |
| Large | 4.5 ms | 1016.8 ms | — |

### Cold-start vs warm kNN

The timed benchmark numbers above reflect warm performance (3 warmup runs fill the buffer pool).
Cold-start (first call on a fresh connection, OS page cache already warm from the benchmark run)
is very different:

| Size | DuckDB cold | DuckDB warm | LadybugDB cold | LadybugDB warm |
|---|---|---|---|---|
| Small | 12 ms | **1.1 ms** | 53 ms | 3.5 ms |
| Medium | 78 ms | **1.3 ms** | 446 ms | 6.4 ms |
| Large | 208 ms* | **1.4 ms** | 1,707 ms | 186 ms |

\* DuckDB large cold with OS page cache already warm. Truly cold (fresh OS page cache): **766 ms**,
measured via `EXPLAIN` + fresh Python process after the benchmark.

**Why DuckDB cold is slow — and why the warm numbers need a caveat:**

`EXPLAIN` reveals that DuckDB's optimizer does not perform a direct rowid point-lookup for the
10 HNSW results. Instead it runs a `SEQ_SCAN` of the full 1M-node table alongside the
`HNSW_INDEX_SCAN` and resolves candidates with a `HASH_JOIN (SEMI)` on rowid. This means:

- Every kNN query reads the full nodes table (~512 MB at large scale) to resolve 10 results.
- Warm performance (1.1 ms) requires those 512 MB to be resident in DuckDB's buffer pool.
- Cold performance degrades to 208–766 ms at large until the buffer pool is warm.

**LadybugDB's HNSW is genuinely disk-based:**
LadybugDB only reads the nodes actually traversed during HNSW graph navigation — it does not scan
the full table. This is why its warm latency scales with graph size (3 ms → 186 ms) rather than
staying flat, but also why its memory footprint is much lower and cold-start at small/medium is
faster than DuckDB cold.

### Vector search summary

| Dimension | DuckDB + vss | LadybugDB |
|---|---|---|
| kNN warm | **1 ms flat** (all sizes) | 4–186 ms (scales with N) |
| kNN cold | 12–766 ms | 53–1,707 ms |
| HNSW index build | **78 s** (large) | 439 s (large) |
| Memory requirement | Full table in RAM for fast queries | Only traversed nodes |
| CozoDB | Index build impractical on RocksDB (108 s for 10K nodes) | — |

**Use DuckDB + vss** if your embedding data fits comfortably in RAM and you run sustained
query traffic (buffer pool stays warm). The 1 ms flat warm latency is genuinely fast.

**Use LadybugDB** if your graph is large relative to available RAM, workloads are bursty
(cold-start matters), or you want disk-native vector search without loading all data into memory.

**CozoDB vector support is not yet practical** for graph-scale datasets on persistent storage.
