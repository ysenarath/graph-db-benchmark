"""
CozoDB benchmark.
Uses Datalog (CozoScript) for all queries. Embedded via pycozo[embedded].
Temporal filtering is native to Datalog — no workarounds needed.
Backend: RocksDB (persistent on-disk), matching DuckDB and LadybugDB.
"""
import json
import os
import shutil

import pandas as pd
from pycozo.client import Client

from benchmark_utils import bench, bench_ingest, save_results

CHUNK_SIZE = 50_000  # rows per batch insert
DB_DIR = "dbs/cozo"


def _df_to_rows(df: pd.DataFrame) -> list[list]:
    return df.values.tolist()


def create_schema(client: Client):
    client.run("""
        :create nodes {
            id: Int
            =>
            category: String,
            value: Float,
            ts: Int
        }
    """)
    client.run("""
        :create edges {
            src: Int,
            dst: Int,
            edge_type: String
            =>
            ts: Int
        }
    """)


def ingest(size_label: str, client: Client):
    nodes_pq = f"data/nodes_{size_label}.parquet"
    edges_pq = f"data/edges_{size_label}.parquet"

    nodes_df = pd.read_parquet(nodes_pq)
    edges_df = pd.read_parquet(edges_pq)

    # Insert nodes in chunks
    for start in range(0, len(nodes_df), CHUNK_SIZE):
        chunk = nodes_df.iloc[start:start + CHUNK_SIZE]
        rows = chunk[["id", "category", "value", "ts"]].values.tolist()
        # CozoDB inline data via constant rules then put
        client.run("""
            ?[id, category, value, ts] <- $rows
            :put nodes { id => category, value, ts }
        """, {"rows": rows})

    # Insert edges in chunks
    for start in range(0, len(edges_df), CHUNK_SIZE):
        chunk = edges_df.iloc[start:start + CHUNK_SIZE]
        rows = chunk[["src", "dst", "edge_type", "ts"]].values.tolist()
        client.run("""
            ?[src, dst, edge_type, ts] <- $rows
            :put edges { src, dst, edge_type => ts }
        """, {"rows": rows})


def run_benchmarks(size_label: str, params: dict, client: Client) -> dict:
    p = params
    results = {}
    errors  = {}

    # 1. Point lookup — $nid in key position for index lookup; id is implicitly $nid
    nid = p["point_node"]
    def q_point():
        client.run("""
            ?[category, value, ts] := *nodes[$nid, category, value, ts]
        """, {"nid": nid})
    results["point_lookup"] = bench(q_point)

    # 2. 1-hop neighbor expansion — $src in key position for index lookup
    src = p["hop_src"]
    def q_1hop():
        client.run("""
            ?[dst] := *edges[$src, dst, _, _]
        """, {"src": src})
    results["hop_1"] = bench(q_1hop)

    # 3. 2-hop traversal
    def q_2hop():
        client.run("""
            ?[count(dst)] :=
                *edges[$src, mid, _, _],
                *edges[mid, dst, _, _]
        """, {"src": src})
    results["hop_2"] = bench(q_2hop)

    # 4. 3-hop traversal
    def q_3hop():
        client.run("""
            ?[count(dst)] :=
                *edges[$src, m1, _, _],
                *edges[m1, m2, _, _],
                *edges[m2, dst, _, _]
        """, {"src": src})
    try:
        results["hop_3"] = bench(q_3hop)
    except Exception as ex:
        errors["hop_3"] = str(ex)
        results["hop_3"] = {"error": str(ex)}

    # 5. Shortest path (BFS — unweighted)
    # ShortestPathBFS(edges[], start[], stop[]) → [from, to, path]
    # start/stop sub-rules use <- [[$var]] inline param syntax
    sp_src = p["sp_src"]
    sp_dst = p["sp_dst"]
    def q_sp():
        client.run("""
            edge_proj[src, dst] := *edges[src, dst, _, _]
            start_n[n] <- [[$sp_src]]
            stop_n[n]  <- [[$sp_dst]]
            ?[a, b, path] <~ ShortestPathBFS(edge_proj[], start_n[], stop_n[])
        """, {"sp_src": sp_src, "sp_dst": sp_dst})
    try:
        results["shortest_path"] = bench(q_sp)
    except Exception as ex:
        errors["shortest_path"] = str(ex)
        results["shortest_path"] = {"error": str(ex)}

    # 6. Filtered traversal (temporal) — 3 hops, edges within ts window
    # This is CozoDB's stated strength: seamless temporal predicates in Datalog
    fsrc  = p["filter_src"]
    ts_lo = p["ts_lo"]
    ts_hi = p["ts_hi"]
    def q_filtered():
        client.run("""
            temp_edge[src, dst] :=
                *edges[src, dst, _, ts],
                ts >= $ts_lo,
                ts <= $ts_hi

            ?[count(dst)] :=
                temp_edge[$fsrc, m1],
                temp_edge[m1, m2],
                temp_edge[m2, dst]
        """, {"fsrc": fsrc, "ts_lo": ts_lo, "ts_hi": ts_hi})
    results["filtered_traversal"] = bench(q_filtered)

    # 7. Pattern match: A->B->C where B.category = pattern_cat
    pcat = p["pattern_cat"]
    def q_pattern():
        client.run("""
            ?[a, b, c] :=
                *edges[a, b, _, _],
                *edges[b, c, _, _],
                *nodes[b, cat, _, _],
                cat = $pcat
            :limit 1000
        """, {"pcat": pcat})
    results["pattern_match"] = bench(q_pattern)

    if errors:
        results["_errors"] = errors
    return results


def run_size(size_label: str, params: dict):
    nodes_pq = f"data/nodes_{size_label}.parquet"
    if not os.path.exists(nodes_pq):
        print(f"  [SKIP] No data for {size_label} tier.")
        return

    print(f"\n[CozoDB] Size: {size_label}")

    db_path = f"{DB_DIR}/{size_label}"
    if os.path.exists(db_path):
        shutil.rmtree(db_path)
    os.makedirs(DB_DIR, exist_ok=True)

    client = Client("rocksdb", db_path)
    create_schema(client)

    print("  Ingesting data …", flush=True)
    ingest_result = bench_ingest(lambda: ingest(size_label, client))
    print(f"  Ingest time: {ingest_result['ingest_ms']:.0f} ms")

    print("  Running query benchmarks …", flush=True)
    query_results = run_benchmarks(size_label, params, client)

    client.close()

    output = {
        "db":      "cozodb",
        "size":    size_label,
        "ingest":  ingest_result,
        "queries": query_results,
    }
    save_results("cozo", size_label, output)
    return output


def main():
    with open("data/query_params.json") as f:
        all_params = json.load(f)

    for size_label in ["small", "medium", "large"]:
        params = all_params.get(size_label, {})
        if params.get("skipped"):
            print(f"[CozoDB] Skipping {size_label}: {params['reason']}")
            continue
        run_size(size_label, params)

    print("\n[CozoDB] Done.")


if __name__ == "__main__":
    main()
