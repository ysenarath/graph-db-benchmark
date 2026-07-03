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
the recursive plan follows edges directly from the starting node.

Profiled via `PROFILE MATCH (a:Node {id:…})-[:Edge]->(b:Node)-[:Edge]->(c:Node) …` —
confirmed `SCAN_NODE_TABLE` emits ~8K tuples for a graph with 10K nodes, vs 1 tuple for primary
key lookup in the recursive plan.

Improvement (median, 3 warmup + 20 timed runs):

| | 2-hop improvement | 3-hop improvement |
|---|---|---|
| Small (10K nodes) | -24% (1.8ms → 1.4ms) | -50% (2.9ms → 1.4ms) |
| Medium (100K nodes) | -25% (4.8ms → 3.6ms) | **-62%** (12.6ms → 4.8ms) |
| Large (1M nodes) | -8% (2.6ms → 2.4ms) | -50% (13.0ms → 6.5ms) |

All results verified correct against chained MATCH (same COUNT(DISTINCT) output).

### CozoDB hop traversals scale with out-degree, not graph size

CozoDB's 2-hop / 3-hop times remain low across all sizes (0.1–1.3 ms on large) because edges are
indexed by `{src, dst, edge_type}` — each hop is an O(degree) B-tree range scan, not O(|E|).
The RocksDB block cache keeps hot index pages in memory after warmup, so on-disk storage adds
minimal overhead for these traversals.

### LadybugDB shortest path is genuinely fast via native `* SHORTEST`

The `[:Edge* SHORTEST]` syntax invokes a native shortest-path algorithm that terminates as soon
as the destination is first reached. DuckDB's `ANY SHORTEST` and CozoDB's `ShortestPathBFS` appear
to complete full BFS frontiers rather than terminating on first hit.

Results confirmed correct against Python BFS ground truth: all three engines return the true
shortest path length (6 / 5 / 6 hops for small / medium / large).

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

**Bottom line**: LadybugDB wins if shortest path is in your hot path. CozoDB wins for hop
traversal workloads. DuckDB wins for temporal filtering, pattern matching, and ingest throughput —
and brings full SQL alongside the graph primitives.
