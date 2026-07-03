"""
Main benchmark orchestrator.
Run: uv run python run_all.py [--skip-large]
"""
import argparse
import json
import os
import platform
import subprocess
import sys
import time


def record_environment():
    import duckdb
    import ladybug as lb
    import pycozo

    py_ver = sys.version
    os_info = platform.platform()
    cpu_info = platform.processor()
    arch = platform.machine()

    # CPU core count
    try:
        import psutil
        cpu_count = psutil.cpu_count(logical=False)
        cpu_logical = psutil.cpu_count(logical=True)
        ram_gb = psutil.virtual_memory().total / 1e9
    except Exception:
        cpu_count = os.cpu_count()
        cpu_logical = os.cpu_count()
        ram_gb = 0

    content = f"""# Benchmark Environment

## System
- **OS**: {os_info}
- **CPU**: {cpu_info} ({arch})
- **Physical cores**: {cpu_count}
- **Logical cores**: {cpu_logical}
- **Total RAM**: {ram_gb:.1f} GB

## Python
- **Version**: {py_ver}

## Database Versions
- **DuckDB**: {duckdb.__version__}
- **DuckPGQ**: community extension (installed at runtime via `INSTALL duckpgq FROM community`)
- **LadybugDB** (`ladybug` package): {lb.__version__ if hasattr(lb, '__version__') else 'see pyproject.toml'}
- **CozoDB** (`pycozo`): {pycozo.__version__ if hasattr(pycozo, '__version__') else '0.7.6'}
- **cozo-embedded**: 0.7.6

## Notes
- CozoDB (pycozo 0.7.6) last released Dec 2023. Tested for Python 3.13 compatibility.
- LadybugDB is a Kùzu-derived fork (Kùzu was archived Sep 2025 after Apple acquisition).
  The `ladybug` PyPI package (v0.18+) is the graph database, not the environmental analysis tool.
- DuckPGQ is a community extension implementing SQL/PGQ (SQL:2023 standard) for DuckDB.
"""

    with open("environment.md", "w") as f:
        f.write(content)
    print("Written: environment.md")


def main():
    parser = argparse.ArgumentParser(description="Graph DB Benchmark Runner")
    parser.add_argument("--skip-large", action="store_true",
                        help="Skip the large dataset tier")
    parser.add_argument("--only", choices=["duckdb", "ladybug", "cozo"],
                        help="Run only one database")
    parser.add_argument("--sizes", nargs="+", choices=["small", "medium", "large"],
                        default=["small", "medium", "large"],
                        help="Which size tiers to run")
    args = parser.parse_args()

    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    print("=" * 60)
    print("Graph Database Benchmark")
    print("=" * 60)

    # Step 1: Record environment
    print("\n[1/5] Recording environment …")
    record_environment()

    # Step 2: Generate data
    print("\n[2/5] Generating dataset …")
    import generate_data
    generate_data.main()

    # Step 3: Run DuckDB benchmark
    dbs_to_run = ["duckdb", "ladybug", "cozo"]
    if args.only:
        dbs_to_run = [args.only]

    with open("data/query_params.json") as f:
        all_params = json.load(f)

    step = 3
    for db_name in dbs_to_run:
        print(f"\n[{step}/5] Running {db_name} benchmark …")
        step += 1
        t0 = time.perf_counter()
        try:
            if db_name == "duckdb":
                import benchmark_duckdb as bm
            elif db_name == "ladybug":
                import benchmark_ladybug as bm
            elif db_name == "cozo":
                import benchmark_cozo as bm
            bm.main()
        except Exception as ex:
            print(f"  ERROR running {db_name} benchmark: {ex}")
            import traceback
            traceback.print_exc()
        elapsed = time.perf_counter() - t0
        print(f"  Total time for {db_name}: {elapsed:.1f}s")

    # Step 4: Generate report
    print(f"\n[{step}/5] Generating RESULTS.md …")
    import report
    report.main()

    print("\n" + "=" * 60)
    print("Benchmark complete. See:")
    print("  environment.md    — system/version info")
    print("  data/             — Parquet datasets + query_params.json")
    print("  results/*.json    — raw timing data per DB per size")
    print("  results/RESULTS.md — summary tables and recommendation")
    print("=" * 60)


if __name__ == "__main__":
    main()
