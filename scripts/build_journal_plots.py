#!/usr/bin/env python3
"""Generate final journal plots when matplotlib is available."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build journal plots from CSV tables.")
    parser.add_argument(
        "--tables-dir",
        type=Path,
        default=PROJECT_ROOT / "runs/journal_tables",
        help="Directory containing CSV tables.",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=PROJECT_ROOT / "runs/journal_plots",
        help="Directory for generated plots.",
    )
    return parser.parse_args()


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    args = parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    master = _read_csv(args.tables_dir / "master_results.csv")
    seed = _read_csv(args.tables_dir / "seed_variance_table.csv")
    error = _read_csv(args.tables_dir / "error_taxonomy_table.csv")

    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception:
        fallback = {
            "note": "matplotlib not available; plots skipped",
            "master_rows": len(master),
            "seed_rows": len(seed),
            "error_rows": len(error),
        }
        (args.outdir / "plot_fallback.json").write_text(json.dumps(fallback, indent=2), encoding="utf-8")
        print(f"No matplotlib. Wrote fallback metadata -> {args.outdir / 'plot_fallback.json'}")
        return

    # Plot 1: F1 by experiment ID
    ids = [row.get("id", "") for row in master]
    f1_vals = []
    for row in master:
        raw = row.get("f1_semantic")
        try:
            f1_vals.append(float(raw) if raw not in ("", None) else 0.0)
        except ValueError:
            f1_vals.append(0.0)
    plt.figure(figsize=(14, 5))
    plt.bar(ids, f1_vals)
    plt.xticks(rotation=75, ha="right")
    plt.ylabel("Semantic F1")
    plt.title("Master Results: F1 by Experiment")
    plt.tight_layout()
    plt.savefig(args.outdir / "f1_by_experiment.png", dpi=180)
    plt.close()

    # Plot 2: Seed variance line
    seeds = []
    seed_f1 = []
    for row in seed:
        try:
            seeds.append(int(row.get("seed", "0")))
            seed_f1.append(float(row.get("f1_semantic") or 0.0))
        except ValueError:
            continue
    if seeds:
        pairs = sorted(zip(seeds, seed_f1), key=lambda item: item[0])
        plt.figure(figsize=(7, 4))
        plt.plot([p[0] for p in pairs], [p[1] for p in pairs], marker="o")
        plt.xlabel("Seed")
        plt.ylabel("Semantic F1")
        plt.title("Seed Variance (E-DIAG-4)")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(args.outdir / "seed_variance_f1.png", dpi=180)
        plt.close()

    # Plot 3: Error taxonomy counts
    counts: dict[str, int] = {}
    for row in error:
        code = row.get("error_code", "")
        try:
            cnt = int(row.get("count", "0"))
        except ValueError:
            cnt = 0
        counts[code] = counts.get(code, 0) + cnt
    if counts:
        labels = sorted(counts.keys())
        values = [counts[label] for label in labels]
        plt.figure(figsize=(9, 4))
        plt.bar(labels, values)
        plt.ylabel("Count")
        plt.title("Error Taxonomy Frequency")
        plt.tight_layout()
        plt.savefig(args.outdir / "error_taxonomy_counts.png", dpi=180)
        plt.close()

    print(f"Wrote plots to {args.outdir}")


if __name__ == "__main__":
    main()
