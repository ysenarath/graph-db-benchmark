"""
LadybugDB benchmark.
LadybugDB is a Kuzu-derived fork with Cypher queries and columnar storage.
Python package: ladybug (v0.18+)
"""
import json
import os
import shutil

import ladybug as lb
import pandas as pd

from benchmark_utils import bench, bench_ingest, save_results

DB_DIR = "dbs/ladybug"


def ingest(size_label: str, db: lb.Database, conn: lb.Connection):
    nodes_pq = f"data/nodes_{size_label}.parquet"
    edges_pq = f"data/edges_{size_label}.parquet"

    # Schema
    conn.execute("CREATE NODE TABLE IF NOT EXISTS Node("
                 "id INT64 PRIMARY KEY, "
                 "category STRING, "
                 "value DOUBLE, "
                 "ts INT64)")

    conn.execute("CREATE REL TABLE IF NOT EXISTS Edge("
                 "FROM Node TO Node, "
                 "edge_type STRING, "
                 "ts INT64)")

    # Bulk load from Parquet — extension auto-detected from filename
    # Edge Parquet columns: src (from-key), dst (to-key), edge_type, ts (positional)
    conn.execute(f"COPY Node FROM '{nodes_pq}'")
    conn.execute(f"COPY Edge FROM '{edges_pq}'")


def run_benchmarks(size_label: str, params: dict, conn: lb.Connection) -> dict:
    p = params
    results = {}
    errors  = {}

    # 1. Point lookup
    nid = p["point_node"]
    def q_point():
        r = conn.execute(f"MATCH (n:Node {{id: {nid}}}) RETURN n.id, n.category, n.value, n.ts")
        while r.has_next():
            r.get_next()
    results["point_lookup"] = bench(q_point)

    # 2. 1-hop neighbor expansion
    src = p["hop_src"]
    def q_1hop():
        r = conn.execute(f"MATCH (a:Node {{id: {src}}})-[:Edge]->(b:Node) RETURN b.id")
        while r.has_next():
            r.get_next()
    results["hop_1"] = bench(q_1hop)

    # 3. 2-hop traversal
    def q_2hop():
        r = conn.execute(f"""
            MATCH (a:Node {{id: {src}}})-[:Edge]->(b:Node)-[:Edge]->(c:Node)
            RETURN COUNT(DISTINCT c.id)
        """)
        while r.has_next():
            r.get_next()
    results["hop_2"] = bench(q_2hop)

    # 4. 3-hop traversal
    def q_3hop():
        r = conn.execute(f"""
            MATCH (a:Node {{id: {src}}})-[:Edge]->(b:Node)-[:Edge]->(c:Node)-[:Edge]->(d:Node)
            RETURN COUNT(DISTINCT d.id)
        """)
        while r.has_next():
            r.get_next()
    try:
        results["hop_3"] = bench(q_3hop)
    except Exception as ex:
        errors["hop_3"] = str(ex)
        results["hop_3"] = {"error": str(ex)}

    # 5. Shortest path — native syntax: [:Edge* SHORTEST]
    sp_src = p["sp_src"]
    sp_dst = p["sp_dst"]
    def q_sp():
        r = conn.execute(f"""
            MATCH p = (a:Node {{id: {sp_src}}})-[:Edge* SHORTEST]->(b:Node {{id: {sp_dst}}})
            RETURN length(p)
        """)
        while r.has_next():
            r.get_next()
    try:
        results["shortest_path"] = bench(q_sp)
    except Exception as ex:
        errors["shortest_path"] = str(ex)
        results["shortest_path"] = {"error": str(ex)}

    # 6. Filtered traversal (temporal) — 3-hop following edges in ts window
    fsrc   = p["filter_src"]
    ts_lo  = p["ts_lo"]
    ts_hi  = p["ts_hi"]
    def q_filtered():
        r = conn.execute(f"""
            MATCH (a:Node {{id: {fsrc}}})-[e1:Edge]->(b:Node)-[e2:Edge]->(c:Node)-[e3:Edge]->(d:Node)
            WHERE e1.ts >= {ts_lo} AND e1.ts <= {ts_hi}
              AND e2.ts >= {ts_lo} AND e2.ts <= {ts_hi}
              AND e3.ts >= {ts_lo} AND e3.ts <= {ts_hi}
            RETURN COUNT(DISTINCT d.id)
        """)
        while r.has_next():
            r.get_next()
    results["filtered_traversal"] = bench(q_filtered)

    # 7. Pattern match: A->B->C where B.category = pattern_cat
    pcat = p["pattern_cat"]
    def q_pattern():
        r = conn.execute(f"""
            MATCH (a:Node)-[:Edge]->(b:Node)-[:Edge]->(c:Node)
            WHERE b.category = '{pcat}'
            RETURN a.id, b.id, c.id
            LIMIT 1000
        """)
        while r.has_next():
            r.get_next()
    results["pattern_match"] = bench(q_pattern)

    if errors:
        results["_errors"] = errors
    return results


def run_size(size_label: str, params: dict):
    nodes_pq = f"data/nodes_{size_label}.parquet"
    if not os.path.exists(nodes_pq):
        print(f"  [SKIP] No data for {size_label} tier.")
        return

    db_path = f"{DB_DIR}/{size_label}.lbug"
    if os.path.exists(db_path):
        if os.path.isdir(db_path):
            shutil.rmtree(db_path)
        else:
            os.remove(db_path)
    os.makedirs(DB_DIR, exist_ok=True)

    print(f"\n[LadybugDB] Size: {size_label}")

    # LadybugDB uses a directory-based storage
    db   = lb.Database(db_path)
    conn = lb.Connection(db)

    print("  Ingesting data …", flush=True)
    ingest_result = bench_ingest(lambda: ingest(size_label, db, conn))
    print(f"  Ingest time: {ingest_result['ingest_ms']:.0f} ms")

    print("  Running query benchmarks …", flush=True)
    query_results = run_benchmarks(size_label, params, conn)

    del conn
    del db

    output = {
        "db":      "ladybugdb",
        "size":    size_label,
        "ingest":  ingest_result,
        "queries": query_results,
    }
    save_results("ladybug", size_label, output)
    return output


def main():
    with open("data/query_params.json") as f:
        all_params = json.load(f)

    for size_label in ["small", "medium", "large"]:
        params = all_params.get(size_label, {})
        if params.get("skipped"):
            print(f"[LadybugDB] Skipping {size_label}: {params['reason']}")
            continue
        run_size(size_label, params)

    print("\n[LadybugDB] Done.")


if __name__ == "__main__":
    main()
