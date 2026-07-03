"""Shared timing utilities and result I/O for the graph-db benchmark."""
import json
import os
import statistics
import time
from typing import Callable


WARMUP_ITERS = 3
BENCH_ITERS  = 20


def bench(fn: Callable, warmup: int = WARMUP_ITERS, iters: int = BENCH_ITERS) -> dict:
    """Run fn warmup times (discarded), then iters times. Return latency stats in ms."""
    for _ in range(warmup):
        fn()
    times = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000.0)
    sorted_t = sorted(times)
    return {
        "min_ms":    round(min(times), 4),
        "median_ms": round(statistics.median(times), 4),
        "p95_ms":    round(sorted_t[int(0.95 * len(sorted_t))], 4),
        "max_ms":    round(max(times), 4),
        "iters":     iters,
    }


def bench_ingest(fn: Callable) -> dict:
    """Time a single cold-start ingest call."""
    t0 = time.perf_counter()
    fn()
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return {"ingest_ms": round(elapsed_ms, 2)}


def save_results(db_name: str, size_label: str, results: dict):
    os.makedirs("results", exist_ok=True)
    path = f"results/{db_name}_{size_label}.json"
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  → Saved {path}")


def load_all_results() -> dict:
    results = {}
    for fname in os.listdir("results"):
        if not fname.endswith(".json"):
            continue
        with open(f"results/{fname}") as f:
            data = json.load(f)
        key = fname[:-5]  # strip .json
        results[key] = data
    return results


def flag_anomaly(db: str, query: str, stats: dict, others: list[dict]) -> str | None:
    """Return a warning string if this result looks anomalous vs others."""
    if not others:
        return None
    other_medians = [o["median_ms"] for o in others if "median_ms" in o]
    if not other_medians:
        return None
    median = stats.get("median_ms", 0)
    if median == 0:
        return None
    ratio_hi = median / min(other_medians) if min(other_medians) > 0 else 0
    ratio_lo = max(other_medians) / median if median > 0 else 0
    if ratio_hi > 100:
        return f"ANOMALY: {db}/{query} is {ratio_hi:.0f}x SLOWER than others — investigate before reporting"
    if ratio_lo > 100:
        return f"ANOMALY: {db}/{query} is {ratio_lo:.0f}x FASTER than others — investigate before reporting"
    return None
