# Graph Database Benchmark Results

Databases compared: **DuckDB + DuckPGQ**, **LadybugDB**, **CozoDB**  
Methodology: 3 warmup runs + 20 timed runs per query. Latency in milliseconds.

## Query Latency — Small Dataset

_Median latency (ms). Lower is better._

| Query | DuckDB + DuckPGQ | LadybugDB | CozoDB |
|---|---|---|---|
| Point Lookup (by id) | 0.1 ms | 0.2 ms | 0.1 ms |
| 1-Hop Neighbor Expansion | 0.4 ms | 0.6 ms | 0.1 ms |
| 2-Hop Traversal | 0.8 ms | 1.8 ms | 0.1 ms |
| 3-Hop Traversal | 1.4 ms | 2.9 ms | 0.2 ms |
| Shortest Path | 58.1 ms | 5.1 ms | 29.9 ms |
| Filtered Traversal (temporal, 3-hop) | 0.9 ms | 6.3 ms | 16.8 ms |
| Pattern Match (A→B→C, B.category filter) | 1.6 ms | 4.0 ms | 11.9 ms |

### Small — P95 Latency Detail

| Query | DuckDB + DuckPGQ p95 | LadybugDB p95 | CozoDB p95 |
|---|---|---|---|
| Point Lookup (by id) | 0.2 ms | 0.3 ms | 0.1 ms |
| 1-Hop Neighbor Expansion | 0.7 ms | 0.7 ms | 0.1 ms |
| 2-Hop Traversal | 0.9 ms | 1.9 ms | 0.1 ms |
| 3-Hop Traversal | 1.5 ms | 3.0 ms | 0.2 ms |
| Shortest Path | 64.9 ms | 5.4 ms | 36.6 ms |
| Filtered Traversal (temporal, 3-hop) | 0.9 ms | 6.5 ms | 17.0 ms |
| Pattern Match (A→B→C, B.category filter) | 1.9 ms | 4.2 ms | 13.4 ms |

## Query Latency — Medium Dataset

_Median latency (ms). Lower is better._

| Query | DuckDB + DuckPGQ | LadybugDB | CozoDB |
|---|---|---|---|
| Point Lookup (by id) | 0.1 ms | 0.2 ms | 0.1 ms |
| 1-Hop Neighbor Expansion | 0.6 ms | 0.9 ms | 0.1 ms |
| 2-Hop Traversal | 1.3 ms | 4.8 ms | 0.1 ms |
| 3-Hop Traversal | 2.9 ms | 12.6 ms | 0.6 ms |
| Shortest Path | 1090.1 ms | 20.3 ms | 625.0 ms |
| Filtered Traversal (temporal, 3-hop) | 5.9 ms | 90.9 ms | 446.3 ms |
| Pattern Match (A→B→C, B.category filter) | 5.4 ms | 26.2 ms | 16.0 ms |

### Medium — P95 Latency Detail

| Query | DuckDB + DuckPGQ p95 | LadybugDB p95 | CozoDB p95 |
|---|---|---|---|
| Point Lookup (by id) | 0.1 ms | 0.3 ms | 0.1 ms |
| 1-Hop Neighbor Expansion | 0.8 ms | 1.1 ms | 0.1 ms |
| 2-Hop Traversal | 2.6 ms | 5.1 ms | 0.1 ms |
| 3-Hop Traversal | 3.5 ms | 13.2 ms | 0.6 ms |
| Shortest Path | 1154.0 ms | 22.4 ms | 638.0 ms |
| Filtered Traversal (temporal, 3-hop) | 7.5 ms | 95.7 ms | 459.0 ms |
| Pattern Match (A→B→C, B.category filter) | 5.8 ms | 27.2 ms | 16.6 ms |

## Query Latency — Large Dataset

_Median latency (ms). Lower is better._

| Query | DuckDB + DuckPGQ | LadybugDB | CozoDB |
|---|---|---|---|
| Point Lookup (by id) | 0.2 ms | 0.2 ms | 0.1 ms |
| 1-Hop Neighbor Expansion | 1.8 ms | 0.5 ms | 0.1 ms |
| 2-Hop Traversal | 3.0 ms | 2.6 ms | 0.2 ms |
| 3-Hop Traversal | 7.3 ms | 13.0 ms | 1.3 ms |
| Shortest Path | 11714.8 ms | 208.0 ms | 9146.3 ms |
| Filtered Traversal (temporal, 3-hop) | 24.6 ms | 228.3 ms | 4715.6 ms |
| Pattern Match (A→B→C, B.category filter) | 28.3 ms | 139.5 ms | 15.8 ms |

### Large — P95 Latency Detail

| Query | DuckDB + DuckPGQ p95 | LadybugDB p95 | CozoDB p95 |
|---|---|---|---|
| Point Lookup (by id) | 0.2 ms | 0.3 ms | 0.1 ms |
| 1-Hop Neighbor Expansion | 2.1 ms | 0.6 ms | 0.1 ms |
| 2-Hop Traversal | 3.7 ms | 6.6 ms | 0.6 ms |
| 3-Hop Traversal | 7.7 ms | 19.7 ms | 1.6 ms |
| Shortest Path | 12379.6 ms | 227.6 ms | 9425.2 ms |
| Filtered Traversal (temporal, 3-hop) | 25.7 ms | 241.6 ms | 4745.9 ms |
| Pattern Match (A→B→C, B.category filter) | 31.2 ms | 153.7 ms | 16.7 ms |

## Bulk Ingest / Load Time

_Cold-start ingest time (ms) for each dataset size._

| Size | DuckDB + DuckPGQ | LadybugDB | CozoDB |
|---|---|---|---|
| Small | 66.6 ms | 119.3 ms | 220.6 ms |
| Medium | 924.9 ms | 2402.0 ms | 4156.5 ms |
| Large | 6712.2 ms | 16747.9 ms | 42520.8 ms |

## Anomaly Flags

- **large/filtered_traversal**: CozoDB is 192× slower than DuckDB + DuckPGQ (4715.6 ms vs 24.6 ms).
  **Investigated — this is a structural difference, not a fairness bug.**
  CozoDB's edge relation is keyed on `{src, dst, edge_type}` with no secondary index on `ts`.
  Any timestamp range filter requires a full edge scan; with RocksDB this also incurs block I/O.
  DuckDB has an explicit `CREATE INDEX idx_edges_ts ON edges(ts)` and uses it in the CTE.
  **Implication**: if your workload involves frequent temporal filtering, CozoDB is the wrong choice at scale.

- **large/shortest_path**: LadybugDB is 56× faster than DuckDB (208 ms vs 11,715 ms) and 44× faster
  than CozoDB (208 ms vs 9,146 ms). **Investigated — this is a genuine algorithm difference.**
  LadybugDB's `[:Edge* SHORTEST]` uses a native bidirectional or early-terminating BFS that stops
  as soon as the target is reached. DuckDB's `ANY SHORTEST` and CozoDB's `ShortestPathBFS` complete
  the full BFS frontier at each depth level before declaring the result. On large graphs with avg
  degree 10 and diameter ~6, the difference compounds significantly.

## Errors / Unsupported Operations

_No errors or unsupported operations — all queries use each engine's idiomatic native syntax._

## Performance Notes

### CozoDB hop traversals scale with out-degree, not graph size
CozoDB's 2-hop / 3-hop times remain low across all sizes (0.1–1.3 ms on large) because edges are
indexed by `{src, dst, edge_type}` — each hop is an O(degree) B-tree range scan, not O(|E|).
The RocksDB block cache keeps hot index pages in memory after warmup, so on-disk storage adds
minimal overhead for these traversals. DuckDB and LadybugDB hop times grow with graph size because
their engines materialise more intermediate results.

### LadybugDB shortest path is genuinely fast via native `* SHORTEST`
The `[:Edge* SHORTEST]` syntax (documented in the LadybugDB Python tutorial) invokes a native
shortest-path algorithm that terminates as soon as the destination is first reached — O(V+E) in
the worst case but stops early in practice. This is a real algorithmic advantage, not a benchmark
artefact. DuckDB's `ANY SHORTEST` and CozoDB's `ShortestPathBFS` are slower because they appear
to complete full BFS frontiers rather than terminating on first hit.

Results confirmed correct against Python BFS ground truth: all three engines return the true
shortest path length (6 / 5 / 6 hops for small / medium / large).

### RocksDB vs in-memory (CozoDB)
All three databases use persistent on-disk storage. Switching CozoDB from in-memory to RocksDB
adds moderate overhead on scan-heavy queries (filtered traversal, pattern match) due to block I/O,
but point lookup and 1–2-hop traversal are unaffected (hot B-tree nodes stay in RocksDB's block cache).

## Recommendation (data-driven only)

Aggregate median latency across all 7 query types × small + medium datasets (14 pairs each):

1. **Winner** — **LadybugDB**: avg 12.6 ms/query
2. **2nd** — **CozoDB (RocksDB)**: avg 81.9 ms/query
3. **3rd** — **DuckDB + DuckPGQ**: avg 83.5 ms/query

LadybugDB's lead is almost entirely driven by shortest path (5 ms vs 1090 ms at medium). Strip
that query out and CozoDB leads on traversal, DuckDB leads on filtering and pattern match.

**By workload type:**

| Workload | Best choice |
|---|---|
| Shortest path | **LadybugDB** — native `* SHORTEST`, 20–56× faster than the others |
| Graph traversal (1–3 hop) | **CozoDB** — constant-time B-tree hops regardless of graph size |
| Temporal filtering on edges | **DuckDB** — secondary `ts` index; 6 ms vs 446 ms at medium |
| Pattern matching (subgraph) | **DuckDB** — vectorised SQL joins |
| Bulk ingest speed | **DuckDB** — direct Parquet read (6.7 s vs 16.7 s vs 42.5 s for large) |

**Bottom line**: LadybugDB wins if shortest path is in your hot path. CozoDB wins for hop
traversal workloads. DuckDB wins for temporal filtering, pattern matching, and ingest throughput —
and brings full SQL alongside the graph primitives.
