# Benchmark Environment

## System
- **OS**: macOS 26.5.1 (Sonoma), arm64 (Apple Silicon)
- **CPU**: Apple ARM (arm64) — 12 physical / 12 logical cores
- **Compiler**: Clang 22.1.3
- **Total RAM**: 68.7 GB

## Python
- **Version**: 3.13.13 (main, Jun 2 2026) [Clang 22.1.3]

## Database Versions & Installation
| Database | Package | Version | Install | Storage backend |
|---|---|---|---|---|
| DuckDB | `duckdb` | 1.5.4 | `uv add duckdb` | file (`.duckdb`) |
| DuckPGQ | community extension | auto (via SQL) | `INSTALL duckpgq FROM community; LOAD duckpgq` | — |
| LadybugDB | `ladybug` | 0.18.0 | `uv add ladybug` | directory (`.lbug`) |
| CozoDB | `pycozo[embedded]` + `cozo-embedded` | 0.7.6 | `uv add "pycozo[embedded]"` | RocksDB (directory) |

## Package Disambiguation Notes
- **`ladybug` PyPI package** (v0.18+) is the LadybugDB graph database — a Kùzu-derived fork
  maintained after Kùzu was archived in Sep 2025 following Apple acquisition.
  _Do not confuse with the unrelated `ladybug-tools` environmental analysis package._
- **`pycozo` v0.7.6** was last released Dec 2023. Tested successfully on Python 3.13.
  The `cozo-embedded` Rust backend (v0.7.6) was compiled for this platform.

## Data Generation
- Seed: `np.random.default_rng(42)` — fully reproducible
- Small: 10,000 nodes / 50,000 edges
- Medium: 100,000 nodes / 1,000,000 edges
- Large: 1,000,000 nodes / 10,000,000 edges

Node schema: `id (int64), category (str, 8 values), value (float64), ts (int64 ms epoch)`
Edge schema: `src (int64), dst (int64), edge_type (str, 5 values), ts (int64 ms epoch)`
Timestamp range: 2024-01-01 to 2024-12-31 UTC (uniform distribution)

## Benchmark Parameters
- Warmup runs: 3 (discarded)
- Timed runs: 20
- Statistics reported: min / median / p95 / max latency in ms
- Ingest: single cold-start timing (not looped)
- All databases run sequentially (no concurrency)

## Known Limitations / Design Notes
1. **DuckPGQ LABEL syntax**: `CREATE PROPERTY GRAPH … LABEL <name>` not supported in
   DuckDB 1.5.4 / DuckPGQ community extension. Table names used as labels instead.
   Affects graph creation only; query behaviour is identical.
2. **LadybugDB shortest path**: uses native `[:Edge* SHORTEST]` syntax per the LadybugDB
   Python tutorial. Results verified correct against Python BFS ground truth (6/5/6 hops).
3. **CozoDB temporal filter**: no secondary index on `ts`. Filter requires a full edge scan
   inside the `temp_edge` rule; accounts for CozoDB being slower on filtered_traversal.
4. **CozoDB point_lookup / 1-hop**: uses key-position parameter binding (`*nodes[$nid, ...]`)
   rather than predicate-style (`id = $nid`) to get B-tree index lookup instead of full scan.
