"""
Vector search benchmark: HNSW index build + kNN (k=10) + hybrid (kNN → 1-hop expansion).
Embedding: 128-dim float32 unit vectors, cosine metric.
All three databases run against the same data (nodes_vec_{size}.parquet + edges_{size}.parquet).
Results saved as results/vec_{db}_{size}.json.
"""
import json
import os
import shutil
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from benchmark_utils import bench, bench_ingest, save_results

EMBED_DIM = 128
K = 10
DB_DIR = "dbs/vec"
CHUNK = 50_000


# ─── Shared data loader ───────────────────────────────────────────────────────

def _load_embeddings_numpy(size_label: str) -> np.ndarray:
    """Return (N, EMBED_DIM) float32 numpy array from nodes_vec parquet."""
    tbl = pq.read_table(f"data/nodes_vec_{size_label}.parquet",
                        columns=["embedding"])
    emb_ca = tbl.column("embedding")
    if isinstance(emb_ca, pa.ChunkedArray):
        emb_ca = emb_ca.combine_chunks()
    # FixedSizeListArray.values → flat Float32Array
    flat = emb_ca.values.to_numpy(zero_copy_only=False)
    return flat.reshape(-1, EMBED_DIM).astype(np.float32)


# ─── DuckDB ──────────────────────────────────────────────────────────────────

def run_duckdb_vec(size_label: str, params: dict):
    nodes_pq = f"data/nodes_vec_{size_label}.parquet"
    edges_pq = f"data/edges_{size_label}.parquet"
    db_path   = f"{DB_DIR}/duckdb_{size_label}.duckdb"

    if os.path.exists(db_path):
        os.remove(db_path)
    os.makedirs(DB_DIR, exist_ok=True)

    import duckdb
    conn = duckdb.connect(db_path)
    conn.execute("INSTALL vss")
    conn.execute("LOAD vss")
    conn.execute("SET hnsw_enable_experimental_persistence = true")

    conn.execute(f"""
        CREATE TABLE nodes (
            id BIGINT PRIMARY KEY,
            category VARCHAR,
            value DOUBLE,
            ts BIGINT,
            embedding FLOAT[{EMBED_DIM}]
        )
    """)
    conn.execute("CREATE TABLE edges (src BIGINT, dst BIGINT, edge_type VARCHAR, ts BIGINT)")

    print("  [DuckDB] Ingesting …", flush=True)
    ingest_result = bench_ingest(lambda: (
        conn.execute(f"COPY nodes FROM '{nodes_pq}'"),
        conn.execute(f"COPY edges FROM '{edges_pq}'"),
    ))
    print(f"  [DuckDB] Ingest: {ingest_result['ingest_ms']:.0f} ms")

    print("  [DuckDB] Building HNSW index …", flush=True)
    t0 = time.perf_counter()
    conn.execute(f"CREATE INDEX emb_idx ON nodes USING HNSW (embedding) WITH (metric = 'cosine')")
    index_build_ms = (time.perf_counter() - t0) * 1000
    print(f"  [DuckDB] Index build: {index_build_ms:.0f} ms")

    # Pre-build SQL with the query vector as a literal (avoids per-call serialization overhead)
    q = params["query_vector"]
    q_lit = f"[{','.join(f'{x:.8f}' for x in q)}]::FLOAT[{EMBED_DIM}]"
    knn_sql = f"SELECT id FROM nodes ORDER BY array_cosine_distance(embedding, {q_lit}) LIMIT {K}"
    hybrid_sql = f"""
        WITH top_k AS (
            SELECT id FROM nodes ORDER BY array_cosine_distance(embedding, {q_lit}) LIMIT {K}
        )
        SELECT COUNT(DISTINCT e.dst) FROM edges e JOIN top_k ON e.src = top_k.id
    """

    def q_knn():
        conn.execute(knn_sql).fetchall()

    def q_hybrid():
        conn.execute(hybrid_sql).fetchone()

    print("  [DuckDB] Benchmarking queries …", flush=True)
    knn_result    = bench(q_knn)
    hybrid_result = bench(q_hybrid)

    conn.close()

    output = {
        "db":          "vec_duckdb",
        "size":        size_label,
        "ingest":      ingest_result,
        "index_build": {"build_ms": round(index_build_ms, 2)},
        "queries": {
            "vector_knn":       knn_result,
            "hybrid_vector_hop": hybrid_result,
        },
    }
    save_results("vec_duckdb", size_label, output)
    return output


# ─── LadybugDB ───────────────────────────────────────────────────────────────

def run_ladybug_vec(size_label: str, params: dict):
    nodes_pq = f"data/nodes_vec_{size_label}.parquet"
    edges_pq = f"data/edges_{size_label}.parquet"
    db_path   = f"{DB_DIR}/ladybug_{size_label}.lbug"

    if os.path.exists(db_path):
        if os.path.isdir(db_path):
            shutil.rmtree(db_path)
        else:
            os.remove(db_path)
    os.makedirs(DB_DIR, exist_ok=True)

    import ladybug as lb
    db   = lb.Database(db_path)
    conn = lb.Connection(db)

    conn.execute("INSTALL VECTOR; LOAD EXTENSION VECTOR")

    conn.execute(f"CREATE NODE TABLE Node("
                 f"id INT64 PRIMARY KEY, category STRING, value DOUBLE, ts INT64, "
                 f"embedding FLOAT[{EMBED_DIM}])")
    conn.execute("CREATE REL TABLE Edge(FROM Node TO Node, edge_type STRING, ts INT64)")

    print("  [LadybugDB] Ingesting …", flush=True)
    ingest_result = bench_ingest(lambda: (
        conn.execute(f"COPY Node FROM '{nodes_pq}'"),
        conn.execute(f"COPY Edge FROM '{edges_pq}'"),
    ))
    print(f"  [LadybugDB] Ingest: {ingest_result['ingest_ms']:.0f} ms")

    print("  [LadybugDB] Building HNSW index …", flush=True)
    t0 = time.perf_counter()
    conn.execute(f"""
        CALL CREATE_VECTOR_INDEX(
            'Node', 'emb_idx', 'embedding',
            metric := 'cosine',
            efc := 200,
            cache_embeddings := true
        )
    """)
    index_build_ms = (time.perf_counter() - t0) * 1000
    print(f"  [LadybugDB] Index build: {index_build_ms:.0f} ms")

    q = params["query_vector"]

    def q_knn():
        r = conn.execute(
            "CALL QUERY_VECTOR_INDEX('Node', 'emb_idx', $query_vector, 10) "
            "RETURN node.id, distance",
            {"query_vector": q},
        )
        while r.has_next():
            r.get_next()

    def q_hybrid():
        r = conn.execute(
            "CALL QUERY_VECTOR_INDEX('Node', 'emb_idx', $query_vector, 10) "
            "WITH node AS n, distance "
            "MATCH (n)-[:Edge]->(nb:Node) "
            "RETURN COUNT(DISTINCT nb.id)",
            {"query_vector": q},
        )
        while r.has_next():
            r.get_next()

    print("  [LadybugDB] Benchmarking queries …", flush=True)
    knn_result    = bench(q_knn)
    hybrid_result = bench(q_hybrid)

    del conn, db

    output = {
        "db":          "vec_ladybug",
        "size":        size_label,
        "ingest":      ingest_result,
        "index_build": {"build_ms": round(index_build_ms, 2)},
        "queries": {
            "vector_knn":       knn_result,
            "hybrid_vector_hop": hybrid_result,
        },
    }
    save_results("vec_ladybug", size_label, output)
    return output


# ─── CozoDB ──────────────────────────────────────────────────────────────────

def run_cozo_vec(size_label: str, params: dict):
    # CozoDB HNSW on RocksDB persists every graph connection individually, making
    # index build I/O-bound. Small (10K nodes) takes ~108s; medium/large would take
    # hours. Skip those tiers and report the finding in the results.
    if size_label in ("medium", "large"):
        print(f"  [CozoDB] Skipping {size_label}: HNSW index build on RocksDB is "
              f"I/O-bound (~108s for 10K nodes, O(N log N) → hours at this scale).")
        note = {
            "db": "vec_cozo", "size": size_label,
            "skipped": True,
            "reason": "CozoDB HNSW on RocksDB is I/O-bound: ~108s for 10K nodes; "
                      f"{size_label} would take hours.",
        }
        save_results("vec_cozo", size_label, note)
        return note

    nodes_pq = f"data/nodes_vec_{size_label}.parquet"
    edges_pq = f"data/edges_{size_label}.parquet"
    db_path   = f"{DB_DIR}/cozo_{size_label}"

    if os.path.exists(db_path):
        shutil.rmtree(db_path)
    os.makedirs(DB_DIR, exist_ok=True)

    from pycozo.client import Client
    client = Client("rocksdb", db_path)

    client.run(f"""
        :create nodes {{
            id: Int
            =>
            category: String,
            value: Float,
            ts: Int,
            embedding: <F32; {EMBED_DIM}>
        }}
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

    print("  [CozoDB] Ingesting …", flush=True)

    # Load parquet data (embeddings need Python-side conversion for CozoDB)
    import pandas as pd
    tbl     = pq.read_table(nodes_pq)
    ids     = tbl["id"].to_pylist()
    cats    = tbl["category"].to_pylist()
    vals    = tbl["value"].to_pylist()
    tss     = tbl["ts"].to_pylist()
    emb_ca  = tbl["embedding"].combine_chunks()
    emb_flat = emb_ca.values.to_numpy(zero_copy_only=False)
    embeddings = emb_flat.reshape(-1, EMBED_DIM)   # (N, 128) float32 view
    n = len(ids)

    edges_df = pd.read_parquet(edges_pq)

    def _ingest():
        for start in range(0, n, CHUNK):
            end  = min(start + CHUNK, n)
            rows = [
                [ids[i], cats[i], float(vals[i]), int(tss[i]), embeddings[i].tolist()]
                for i in range(start, end)
            ]
            client.run(
                "?[id, category, value, ts, embedding] <- $rows\n"
                ":put nodes { id => category, value, ts, embedding }",
                {"rows": rows},
            )
        for start in range(0, len(edges_df), CHUNK):
            chunk = edges_df.iloc[start:start + CHUNK]
            rows  = chunk[["src", "dst", "edge_type", "ts"]].values.tolist()
            client.run(
                "?[src, dst, edge_type, ts] <- $rows\n"
                ":put edges { src, dst, edge_type => ts }",
                {"rows": rows},
            )

    ingest_result = bench_ingest(_ingest)
    print(f"  [CozoDB] Ingest: {ingest_result['ingest_ms']:.0f} ms")

    print("  [CozoDB] Building HNSW index …", flush=True)
    t0 = time.perf_counter()
    # m=16, ef_construction=100 keeps build time manageable on RocksDB;
    # CozoDB HNSW persists every graph connection to RocksDB, so build is I/O bound.
    client.run(f"""
        ::hnsw create nodes:emb_idx {{
            fields: [embedding],
            dim: {EMBED_DIM},
            dtype: F32,
            m: 16,
            ef_construction: 100,
            distance: Cosine
        }}
    """)
    index_build_ms = (time.perf_counter() - t0) * 1000
    print(f"  [CozoDB] Index build: {index_build_ms:.0f} ms")

    q = params["query_vector"]  # Python list of 128 floats

    def q_knn():
        # vec($q) converts the Python list to a CozoDB vector type
        client.run(
            f"?[id, dist] := ~nodes:emb_idx{{ id | query: vec($q), k: {K}, ef: 50, bind_distance: dist }}",
            {"q": q},
        )

    def q_hybrid():
        client.run(
            f"knn[id] := ~nodes:emb_idx{{ id | query: vec($q), k: {K}, ef: 50 }}\n"
            "?[count(neighbor)] := knn[id], *edges[id, neighbor, _, _]",
            {"q": q},
        )

    print("  [CozoDB] Benchmarking queries …", flush=True)
    knn_result    = bench(q_knn)
    hybrid_result = bench(q_hybrid)

    client.close()

    output = {
        "db":          "vec_cozo",
        "size":        size_label,
        "ingest":      ingest_result,
        "index_build": {"build_ms": round(index_build_ms, 2)},
        "queries": {
            "vector_knn":       knn_result,
            "hybrid_vector_hop": hybrid_result,
        },
    }
    save_results("vec_cozo", size_label, output)
    return output


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    with open("data/query_params.json") as f:
        all_params = json.load(f)

    for size_label in ["small", "medium", "large"]:
        params = all_params.get(size_label, {})
        if params.get("skipped"):
            print(f"[Vector] Skipping {size_label}: {params['reason']}")
            continue
        if not os.path.exists(f"data/nodes_vec_{size_label}.parquet"):
            print(f"[Vector] Skipping {size_label}: nodes_vec_{size_label}.parquet missing — "
                  "run generate_data.py first.")
            continue
        if "query_vector" not in params:
            print(f"[Vector] Skipping {size_label}: query_vector missing from query_params.json — "
                  "run generate_data.py first.")
            continue

        print(f"\n{'='*55}\n[Vector] Size: {size_label}\n{'='*55}")
        run_duckdb_vec(size_label, params)
        run_ladybug_vec(size_label, params)
        run_cozo_vec(size_label, params)

    print("\n[Vector] Done.")


if __name__ == "__main__":
    main()
