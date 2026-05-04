#!/usr/bin/env python3
"""Run dedicated ablation matrix A1-A7."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ablation matrix A1-A7.")
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "configs/e4_iterative_repair_atm.json",
        help="Base config for ablation runs.",
    )
    parser.add_argument("--execute", action="store_true", help="Execute commands; default is dry-run.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "runs/ablation_matrix",
        help="Output root for ablation runs.",
    )
    parser.add_argument(
        "--status",
        type=Path,
        default=PROJECT_ROOT / "runs/ablation_matrix/status.json",
        help="Status output file.",
    )
    return parser.parse_args()


def _cmd(*parts: str) -> list[str]:
    return [sys.executable, *parts]


def build_matrix(config: Path, output_root: Path) -> list[dict]:
    config_rel = str(config.relative_to(PROJECT_ROOT)) if config.is_absolute() else str(config)
    return [
        {
            "id": "A0",
            "name": "Reference (full method)",
            "question": "Baseline for ablation deltas",
            "output_dir": str(output_root / "A0_reference"),
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                config_rel,
                "--stability-variant",
                "sa5",
                "--feedback-variant",
                "typed_priority",
                "--local-repair-only",
                "--output-root",
                str(output_root / "A0_reference"),
            ),
        },
        {
            "id": "A1",
            "name": "No SHACL",
            "question": "Χρειάζεται structural validation ή όχι;",
            "output_dir": str(output_root / "A1_no_shacl"),
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                config_rel,
                "--ablation-profile",
                "no_shacl",
                "--output-root",
                str(output_root / "A1_no_shacl"),
            ),
        },
        {
            "id": "A2",
            "name": "No reasoning",
            "question": "Ο reasoner βοηθά μόνο ως checker ή και ως stabilizer;",
            "output_dir": str(output_root / "A2_no_reasoning"),
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                config_rel,
                "--ablation-profile",
                "no_reasoning",
                "--output-root",
                str(output_root / "A2_no_reasoning"),
            ),
        },
        {
            "id": "A3",
            "name": "No CQ feedback",
            "question": "Τα CQs βοηθούν ουσιαστικά ή δημιουργούν overfitting pressure;",
            "output_dir": str(output_root / "A3_no_cq"),
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                config_rel,
                "--ablation-profile",
                "no_cq",
                "--output-root",
                str(output_root / "A3_no_cq"),
            ),
        },
        {
            "id": "A4",
            "name": "No ontology context",
            "question": "Πόσο σημαντικό είναι το grounding;",
            "output_dir": str(output_root / "A4_no_context"),
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                config_rel,
                "--ablation-profile",
                "no_ontology_context",
                "--output-root",
                str(output_root / "A4_no_context"),
            ),
        },
        {
            "id": "A5",
            "name": "No exemplars",
            "question": "Προσφέρουν κάτι τα exemplars πέρα από vocabulary hints;",
            "output_dir": str(output_root / "A5_no_exemplars"),
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                config_rel,
                "--ablation-profile",
                "no_exemplars",
                "--output-root",
                str(output_root / "A5_no_exemplars"),
            ),
        },
        {
            "id": "A6",
            "name": "No growth control",
            "question": "Το stability control όντως αποτρέπει degeneration;",
            "output_dir": str(output_root / "A6_no_growth_control"),
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                config_rel,
                "--ablation-profile",
                "no_growth_control",
                "--output-root",
                str(output_root / "A6_no_growth_control"),
            ),
        },
        {
            "id": "A7",
            "name": "Global rewrite instead of local repair",
            "question": "Είναι καλύτερο local patching ή broad rewriting;",
            "output_dir": str(output_root / "A7_global_rewrite"),
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                config_rel,
                "--stability-variant",
                "sa5",
                "--allow-global-repair",
                "--feedback-variant",
                "raw",
                "--output-root",
                str(output_root / "A7_global_rewrite"),
            ),
        },
    ]


def main() -> None:
    args = parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    matrix = build_matrix(args.config, args.output_root)
    (args.output_root / "manifest.json").write_text(json.dumps(matrix, indent=2), encoding="utf-8")

    if not args.execute:
        for row in matrix:
            print(f"[DRY-RUN] {row['id']}: {' '.join(row['cmd'])}")
        return

    status_rows = []
    for row in matrix:
        print(f"[RUN] {row['id']}")
        started = time.perf_counter()
        proc = subprocess.run(row["cmd"], cwd=PROJECT_ROOT, check=False)
        elapsed = time.perf_counter() - started
        status_rows.append(
            {
                "id": row["id"],
                "name": row["name"],
                "question": row["question"],
                "exit_code": proc.returncode,
                "runtime_seconds": round(elapsed, 3),
                "run_root": row["output_dir"],
            }
        )
    args.status.parent.mkdir(parents=True, exist_ok=True)
    args.status.write_text(json.dumps(status_rows, indent=2), encoding="utf-8")
    print(f"Wrote ablation status -> {args.status}")


if __name__ == "__main__":
    main()
