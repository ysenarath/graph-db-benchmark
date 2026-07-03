"""
DuckDB + DuckPGQ benchmark.
Uses SQL/PGQ syntax via the community extension.
"""
import json
import os
import sys
import time

import duckdb

from benchmark_utils import bench, bench_ingest, save_results

DB_DIR = "dbs/duckdb"


def setup_extension(conn):
    conn.execute("INSTALL duckpgq FROM community")
    conn.execute("LOAD duckpgq")


def ingest(size_label: str, conn: duckdb.DuckDBPyConnection):
    nodes_pq = f"data/nodes_{size_label}.parquet"
    edges_pq = f"data/edges_{size_label}.parquet"

    conn.execute("DROP TABLE IF EXISTS nodes CASCADE")
    conn.execute("DROP TABLE IF EXISTS edges CASCADE")
    conn.execute(f"""
        CREATE TABLE nodes AS SELECT * FROM read_parquet('{nodes_pq}')
    """)
    conn.execute(f"""
        CREATE TABLE edges AS SELECT * FROM read_parquet('{edges_pq}')
    """)

    # Indexes for fair comparison
    conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_id ON nodes(id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_ts ON edges(ts)")

    # Register property graph (table name = label, no explicit LABEL keyword in this version)
    conn.execute("DROP PROPERTY GRAPH IF EXISTS g")
    conn.execute("""
        CREATE PROPERTY GRAPH g
        VERTEX TABLES (nodes)
        EDGE TABLES (
            edges
                SOURCE KEY (src) REFERENCES nodes(id)
                DESTINATION KEY (dst) REFERENCES nodes(id)
        )
    """)


def run_benchmarks(size_label: str, params: dict, conn: duckdb.DuckDBPyConnection) -> dict:
    p = params
    results = {}
    errors  = {}

    # 1. Point lookup
    nid = p["point_node"]
    def q_point():
        conn.execute(f"SELECT * FROM nodes WHERE id = {nid}").fetchall()
    results["point_lookup"] = bench(q_point)

    # 2. 1-hop neighbor expansion
    src = p["hop_src"]
    def q_1hop():
        conn.execute(f"""
            FROM GRAPH_TABLE (g
                MATCH (a:nodes WHERE a.id = {src})-[e:edges]->(b:nodes)
                COLUMNS (b.id)
            )
        """).fetchall()
    results["hop_1"] = bench(q_1hop)

    # 3. 2-hop traversal
    def q_2hop():
        conn.execute(f"""
            FROM GRAPH_TABLE (g
                MATCH (a:nodes WHERE a.id = {src})-[e1:edges]->(b:nodes)-[e2:edges]->(c:nodes)
                COLUMNS (c.id)
            )
        """).fetchall()
    results["hop_2"] = bench(q_2hop)

    # 4. 3-hop traversal
    def q_3hop():
        conn.execute(f"""
            FROM GRAPH_TABLE (g
                MATCH (a:nodes WHERE a.id = {src})-[e1:edges]->(b:nodes)-[e2:edges]->(c:nodes)
                          -[e3:edges]->(d:nodes)
                COLUMNS (d.id)
            )
        """).fetchall()
    try:
        results["hop_3"] = bench(q_3hop)
    except Exception as ex:
        errors["hop_3"] = str(ex)
        results["hop_3"] = {"error": str(ex)}

    # 5. Shortest path
    sp_src = p["sp_src"]
    sp_dst = p["sp_dst"]
    def q_sp():
        r = conn.execute(f"""
            FROM GRAPH_TABLE (g
                MATCH p = ANY SHORTEST (a:nodes WHERE a.id = {sp_src})-[e:edges]->+(b:nodes WHERE b.id = {sp_dst})
                COLUMNS (path_length(p))
            )
        """).fetchall()
        return r
    try:
        results["shortest_path"] = bench(q_sp)
    except Exception as ex:
        errors["shortest_path"] = str(ex)
        results["shortest_path"] = {"error": str(ex)}

    # 6. Filtered traversal (temporal) — 3-hop following only edges within ts window
    fsrc = p["filter_src"]
    ts_lo = p["ts_lo"]
    ts_hi = p["ts_hi"]
    def q_filtered():
        conn.execute(f"""
            WITH filtered_edges AS (
                SELECT src, dst FROM edges
                WHERE ts >= {ts_lo} AND ts <= {ts_hi}
            ),
            hop1 AS (
                SELECT f.dst AS mid1
                FROM filtered_edges f
                WHERE f.src = {fsrc}
            ),
            hop2 AS (
                SELECT f.dst AS mid2
                FROM filtered_edges f
                JOIN hop1 h ON f.src = h.mid1
            ),
            hop3 AS (
                SELECT f.dst
                FROM filtered_edges f
                JOIN hop2 h ON f.src = h.mid2
            )
            SELECT COUNT(*) FROM hop3
        """).fetchall()
    results["filtered_traversal"] = bench(q_filtered)

    # 7. Pattern match: A->B->C where B.category = pattern_cat
    pcat = p["pattern_cat"]
    def q_pattern():
        conn.execute(f"""
            FROM GRAPH_TABLE (g
                MATCH (a:nodes)-[e1:edges]->(b:nodes WHERE b.category = '{pcat}')
                          -[e2:edges]->(c:nodes)
                COLUMNS (a.id, b.id, c.id)
            )
            LIMIT 1000
        """).fetchall()
    results["pattern_match"] = bench(q_pattern)

    if errors:
        results["_errors"] = errors
    return results


def run_size(size_label: str, params: dict):
    nodes_pq = f"data/nodes_{size_label}.parquet"
    if not os.path.exists(nodes_pq):
        print(f"  [SKIP] No data for {size_label} tier.")
        return

    os.makedirs(DB_DIR, exist_ok=True)
    db_path = f"{DB_DIR}/{size_label}.duckdb"
    if os.path.exists(db_path):
        os.remove(db_path)

    print(f"\n[DuckDB] Size: {size_label}")
    conn = duckdb.connect(db_path)
    setup_extension(conn)

    print("  Ingesting data …", flush=True)
    ingest_result = bench_ingest(lambda: ingest(size_label, conn))
    print(f"  Ingest time: {ingest_result['ingest_ms']:.0f} ms")

    print("  Running query benchmarks …", flush=True)
    query_results = run_benchmarks(size_label, params, conn)

    conn.close()

    output = {
        "db":            "duckdb_duckpgq",
        "size":          size_label,
        "ingest":        ingest_result,
        "queries":       query_results,
    }
    save_results("duckdb", size_label, output)
    return output


def main():
    with open("data/query_params.json") as f:
        all_params = json.load(f)

    for size_label in ["small", "medium", "large"]:
        params = all_params.get(size_label, {})
        if params.get("skipped"):
            print(f"[DuckDB] Skipping {size_label}: {params['reason']}")
            continue
        run_size(size_label, params)

    print("\n[DuckDB] Done.")


if __name__ == "__main__":
    main()
