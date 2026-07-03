"""
Synthetic property graph generator.
Fixed seed = 42. Outputs identical Parquet files for all three databases.
Also generates nodes_vec_{size}.parquet with 128-dim float32 unit-vector
embeddings for the vector search benchmark.
"""
import json
import os
import time

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

SEED = 42
EMBED_DIM = 128
CATEGORIES = ["person", "org", "location", "event", "product", "topic", "resource", "service"]
EDGE_TYPES  = ["knows", "works_at", "located_in", "part_of", "related_to"]

# Base timestamp: 2024-01-01 00:00:00 UTC in milliseconds
TS_BASE = 1704067200_000
TS_SPAN = 365 * 24 * 3600 * 1000  # 1 year in ms

SIZES = {
    "small":  {"nodes": 10_000,    "edges": 50_000},
    "medium": {"nodes": 100_000,   "edges": 1_000_000},
    "large":  {"nodes": 1_000_000, "edges": 10_000_000},
}


def generate_nodes(n: int, rng: np.random.Generator) -> pd.DataFrame:
    return pd.DataFrame({
        "id":       np.arange(n, dtype=np.int64),
        "category": rng.choice(CATEGORIES, size=n),
        "value":    rng.random(n).astype(np.float64),
        "ts":       (TS_BASE + rng.integers(0, TS_SPAN, size=n)).astype(np.int64),
    })


def generate_edges(n_nodes: int, n_edges: int, rng: np.random.Generator) -> pd.DataFrame:
    src = rng.integers(0, n_nodes, size=n_edges, dtype=np.int64)
    dst = rng.integers(0, n_nodes, size=n_edges, dtype=np.int64)
    # avoid self-loops
    mask = src == dst
    while mask.any():
        dst[mask] = rng.integers(0, n_nodes, size=mask.sum(), dtype=np.int64)
        mask = src == dst
    return pd.DataFrame({
        "src":       src,
        "dst":       dst,
        "edge_type": rng.choice(EDGE_TYPES, size=n_edges),
        "ts":        (TS_BASE + rng.integers(0, TS_SPAN, size=n_edges)).astype(np.int64),
    })


def query_params(size_label: str, n_nodes: int, rng: np.random.Generator) -> dict:
    """Fixed query parameters for a given size tier."""
    point_node   = int(rng.integers(0, n_nodes))
    hop_src      = int(rng.integers(0, n_nodes))
    sp_src       = int(rng.integers(0, n_nodes))
    sp_dst       = int(rng.integers(0, n_nodes))
    while sp_dst == sp_src:
        sp_dst = int(rng.integers(0, n_nodes))
    filter_src   = int(rng.integers(0, n_nodes))
    # temporal window: middle third of the year
    ts_lo = TS_BASE + TS_SPAN // 3
    ts_hi = TS_BASE + 2 * TS_SPAN // 3
    pattern_cat  = CATEGORIES[int(rng.integers(0, len(CATEGORIES)))]
    return {
        "size":        size_label,
        "point_node":  point_node,
        "hop_src":     hop_src,
        "sp_src":      sp_src,
        "sp_dst":      sp_dst,
        "filter_src":  filter_src,
        "ts_lo":       ts_lo,
        "ts_hi":       ts_hi,
        "pattern_cat": pattern_cat,
    }


def main():
    rng = np.random.default_rng(SEED)
    os.makedirs("data", exist_ok=True)

    all_params = {}
    skip_large = False

    for size_label, dims in SIZES.items():
        n_nodes = dims["nodes"]
        n_edges = dims["edges"]
        nodes_path = f"data/nodes_{size_label}.parquet"
        edges_path = f"data/edges_{size_label}.parquet"

        if size_label == "large":
            # Estimate RAM: ~80 bytes/node, ~96 bytes/edge
            est_gb = (n_nodes * 80 + n_edges * 96) / 1e9
            if est_gb > 6.0:
                print(f"[SKIP] Large tier: estimated {est_gb:.1f} GB RAM — exceeds 6 GB safety limit.")
                print("       Skipping large tier to avoid OOM. Adjust limit in generate_data.py if needed.")
                skip_large = True
                all_params["large"] = {"skipped": True, "reason": f"RAM estimate {est_gb:.1f} GB > 6 GB limit"}
                continue

        print(f"[{size_label}] Generating {n_nodes:,} nodes, {n_edges:,} edges …", flush=True)
        t0 = time.perf_counter()

        nodes = generate_nodes(n_nodes, rng)
        edges = generate_edges(n_nodes, n_edges, rng)

        nodes.to_parquet(nodes_path, index=False)
        edges.to_parquet(edges_path, index=False)

        # Query params drawn from main rng — same sequence as original benchmark
        params = query_params(size_label, n_nodes, rng)

        # Embeddings use a separate rng so they don't disturb the main rng sequence.
        # Seed is deterministic: SEED XOR n_nodes keeps each tier independent.
        print(f"         Generating {EMBED_DIM}-dim embeddings …", flush=True)
        emb_rng = np.random.default_rng(SEED ^ n_nodes)
        emb = emb_rng.standard_normal((n_nodes, EMBED_DIM)).astype(np.float32)
        emb /= np.linalg.norm(emb, axis=1, keepdims=True)
        # Write as FixedSizeList<float32, EMBED_DIM> — maps to FLOAT[128] in LadybugDB/DuckDB
        flat = pa.array(emb.flatten(), type=pa.float32())
        emb_col = pa.FixedSizeListArray.from_arrays(flat, EMBED_DIM)
        vec_tbl = pa.table({
            "id":        pa.array(nodes["id"].values, type=pa.int64()),
            "category":  pa.array(nodes["category"].values),
            "value":     pa.array(nodes["value"].values, type=pa.float64()),
            "ts":        pa.array(nodes["ts"].values, type=pa.int64()),
            "embedding": emb_col,
        })
        vec_path = f"data/nodes_vec_{size_label}.parquet"
        pq.write_table(vec_tbl, vec_path)

        # Query vector for vector benchmark (also from emb_rng)
        qvec = emb_rng.standard_normal(EMBED_DIM).astype(np.float32)
        qvec /= np.linalg.norm(qvec)
        params["query_vector"] = qvec.tolist()
        all_params[size_label] = params

        elapsed = time.perf_counter() - t0
        print(f"         Done in {elapsed:.2f}s → {nodes_path}, {edges_path}, {vec_path}")
        print(f"         Query params: {json.dumps({k: v for k, v in params.items() if k not in ('size', 'query_vector')})}")

    with open("data/query_params.json", "w") as f:
        json.dump(all_params, f, indent=2)
    print("\nSaved query_params.json")
    if skip_large:
        print("NOTE: Large tier was skipped (see above).")


if __name__ == "__main__":
    main()
