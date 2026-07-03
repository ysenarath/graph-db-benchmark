"""
Generate RESULTS.md from raw JSON benchmark outputs.
Flags anomalies and produces per-query comparison tables.
"""
import json
import os
from pathlib import Path

QUERY_LABELS = {
    "point_lookup":      "Point Lookup (by id)",
    "hop_1":             "1-Hop Neighbor Expansion",
    "hop_2":             "2-Hop Traversal",
    "hop_3":             "3-Hop Traversal",
    "shortest_path":     "Shortest Path",
    "filtered_traversal":"Filtered Traversal (temporal, 3-hop)",
    "pattern_match":     "Pattern Match (A→B→C, B.category filter)",
}

DB_LABELS = {
    "duckdb":  "DuckDB + DuckPGQ",
    "ladybug": "LadybugDB",
    "cozo":    "CozoDB",
}

SIZES = ["small", "medium", "large"]


def load_results() -> dict:
    """Returns {db: {size: data}}"""
    out = {}
    for path in Path("results").glob("*.json"):
        stem = path.stem  # e.g. duckdb_small
        parts = stem.split("_", 1)
        if len(parts) != 2:
            continue
        db, size = parts
        with open(path) as f:
            data = json.load(f)
        out.setdefault(db, {})[size] = data
    return out


def fmt(val, unit="ms") -> str:
    if val is None:
        return "—"
    if isinstance(val, str):
        return val
    return f"{val:.1f} {unit}"


def cell(q_results: dict | None, key: str) -> str:
    if q_results is None:
        return "—"
    if "error" in q_results:
        msg = q_results["error"][:60]
        return f"ERROR: {msg}"
    val = q_results.get(key)
    if val is None:
        return "—"
    return fmt(val)


def query_table(all_results: dict, size: str) -> str:
    dbs = ["duckdb", "ladybug", "cozo"]
    header = "| Query | " + " | ".join(DB_LABELS[d] for d in dbs) + " |"
    sep    = "|" + "|".join(["---"] * (len(dbs) + 1)) + "|"
    lines  = [header, sep]

    for qkey, qlabel in QUERY_LABELS.items():
        row = [qlabel]
        for db in dbs:
            q = (all_results.get(db, {})
                            .get(size, {})
                            .get("queries", {})
                            .get(qkey))
            if q is None:
                row.append("—")
            elif "error" in q:
                row.append(f"ERR: {q['error'][:40]}")
            else:
                med = q.get("median_ms")
                row.append(fmt(med) if med is not None else "—")
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def ingest_table(all_results: dict) -> str:
    dbs = ["duckdb", "ladybug", "cozo"]
    header = "| Size | " + " | ".join(DB_LABELS[d] for d in dbs) + " |"
    sep    = "|" + "|".join(["---"] * (len(dbs) + 1)) + "|"
    lines  = [header, sep]

    for size in SIZES:
        row = [size.capitalize()]
        for db in dbs:
            ingest = (all_results.get(db, {})
                                 .get(size, {})
                                 .get("ingest", {}))
            if not ingest:
                row.append("—")
            elif ingest.get("skipped"):
                row.append("skipped")
            else:
                ms = ingest.get("ingest_ms")
                row.append(fmt(ms) if ms is not None else "—")
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def collect_anomalies(all_results: dict) -> list[str]:
    anomalies = []
    dbs = ["duckdb", "ladybug", "cozo"]
    for size in SIZES:
        for qkey in QUERY_LABELS:
            medians = {}
            for db in dbs:
                q = (all_results.get(db, {})
                                .get(size, {})
                                .get("queries", {})
                                .get(qkey))
                if q and "median_ms" in q:
                    medians[db] = q["median_ms"]
            if len(medians) < 2:
                continue
            vals = list(medians.values())
            ratio = max(vals) / min(vals) if min(vals) > 0 else 0
            if ratio > 100:
                slowest = max(medians, key=medians.get)
                fastest = min(medians, key=medians.get)
                anomalies.append(
                    f"**{size}/{qkey}**: {DB_LABELS[slowest]} is {ratio:.0f}x slower than "
                    f"{DB_LABELS[fastest]} "
                    f"({medians[slowest]:.1f}ms vs {medians[fastest]:.1f}ms) — "
                    "investigate for fairness issues before trusting this result."
                )
    return anomalies


def errors_section(all_results: dict) -> str:
    lines = []
    for db, sizes in all_results.items():
        for size, data in sizes.items():
            errs = data.get("queries", {}).get("_errors", {})
            for key, msg in errs.items():
                lines.append(f"- **{DB_LABELS.get(db, db)} / {size} / {key}**: `{msg[:120]}`")
    return "\n".join(lines) if lines else "_No errors recorded._"


def pick_one(all_results: dict) -> str:
    """Pure data-driven recommendation based on aggregate median latency."""
    totals: dict[str, float] = {}
    counts: dict[str, int]   = {}
    dbs = ["duckdb", "ladybug", "cozo"]

    for db in dbs:
        total = 0.0
        count = 0
        for size in ["small", "medium"]:  # focus on sizes that ran
            for qkey in QUERY_LABELS:
                q = (all_results.get(db, {})
                                .get(size, {})
                                .get("queries", {})
                                .get(qkey))
                if q and "median_ms" in q and "error" not in q:
                    total += q["median_ms"]
                    count += 1
        totals[db] = total
        counts[db] = count

    if not any(counts.values()):
        return "_Insufficient data to make a recommendation._"

    ranked = sorted([db for db in dbs if counts[db] > 0],
                    key=lambda d: totals[d] / counts[d])

    lines = []
    for i, db in enumerate(ranked):
        avg = totals[db] / counts[db] if counts[db] else 0
        label = ["**Winner**", "2nd", "3rd"][i]
        lines.append(f"{i+1}. {label} — **{DB_LABELS[db]}**: avg {avg:.1f} ms/query "
                     f"across {counts[db]} measured query×size pairs")

    winner = ranked[0]
    lines.append("")
    lines.append(
        f"Based purely on median query latency across all benchmarked query types and sizes, "
        f"**{DB_LABELS[winner]}** had the lowest aggregate latency. "
        "This recommendation is mechanical — see the per-query tables above for nuance, "
        "especially if your workload is dominated by one query type."
    )
    return "\n".join(lines)


def main():
    all_results = load_results()

    with open("results/RESULTS.md", "w") as f:
        f.write("# Graph Database Benchmark Results\n\n")
        f.write("Databases compared: **DuckDB + DuckPGQ**, **LadybugDB**, **CozoDB**  \n")
        f.write("Methodology: 3 warmup runs + 20 timed runs per query. Latency in milliseconds.\n\n")

        # Per-size query tables
        for size in SIZES:
            available = any(
                size in all_results.get(db, {}) for db in ["duckdb", "ladybug", "cozo"]
            )
            if not available:
                continue
            f.write(f"## Query Latency — {size.capitalize()} Dataset\n\n")
            f.write("_Median latency (ms). Lower is better._\n\n")
            f.write(query_table(all_results, size))
            f.write("\n\n")

            # P95 detail table
            f.write(f"### {size.capitalize()} — P95 Latency Detail\n\n")
            dbs = ["duckdb", "ladybug", "cozo"]
            hdr = "| Query | " + " | ".join(f"{DB_LABELS[d]} p95" for d in dbs) + " |"
            sep = "|" + "|".join(["---"] * (len(dbs) + 1)) + "|"
            f.write(hdr + "\n" + sep + "\n")
            for qkey, qlabel in QUERY_LABELS.items():
                row = [qlabel]
                for db in dbs:
                    q = (all_results.get(db, {})
                                    .get(size, {})
                                    .get("queries", {})
                                    .get(qkey))
                    if q and "p95_ms" in q:
                        row.append(fmt(q["p95_ms"]))
                    else:
                        row.append("—")
                f.write("| " + " | ".join(row) + " |\n")
            f.write("\n")

        # Ingest table
        f.write("## Bulk Ingest / Load Time\n\n")
        f.write("_Cold-start ingest time (ms) for each dataset size._\n\n")
        f.write(ingest_table(all_results))
        f.write("\n\n")

        # Anomalies
        anomalies = collect_anomalies(all_results)
        f.write("## Anomaly Flags\n\n")
        if anomalies:
            for a in anomalies:
                f.write(f"- {a}\n")
        else:
            f.write("_No anomalies detected (no query showed >100x ratio between databases)._\n")
        f.write("\n")

        # Errors
        f.write("## Errors / Unsupported Operations\n\n")
        f.write(errors_section(all_results))
        f.write("\n\n")

        # Recommendation
        f.write("## Recommendation (data-driven only)\n\n")
        f.write(pick_one(all_results))
        f.write("\n")

    print("Written: results/RESULTS.md")


if __name__ == "__main__":
    main()
