#!/usr/bin/env python3
"""Run Stability-aware repair core variants SA-1..SA-5 (+baseline)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run stability-aware core variants.")
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "configs/e4_iterative_repair_atm.json",
        help="Base E4 config.",
    )
    parser.add_argument("--execute", action="store_true", help="Execute commands; otherwise dry-run.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "runs/stability_core",
        help="Output root for SA variant runs.",
    )
    parser.add_argument(
        "--status",
        type=Path,
        default=PROJECT_ROOT / "runs/stability_core/status.json",
        help="Status file path.",
    )
    return parser.parse_args()


def _cmd(*parts: str) -> list[str]:
    return [sys.executable, *parts]


def build_matrix(config: Path, output_root: Path) -> list[dict]:
    config_rel = str(config.relative_to(PROJECT_ROOT)) if config.is_absolute() else str(config)
    return [
        {
            "id": "SA-BASE",
            "description": "Current best non-stability baseline",
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                config_rel,
                "--stability-variant",
                "none",
                "--stop-policies",
                "max_only",
                "--feedback-variant",
                "typed",
                "--output-root",
                str(output_root / "SA-BASE"),
            ),
        },
        {
            "id": "SA-1",
            "description": "Stop if no CQ gain for k iterations",
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                config_rel,
                "--stability-variant",
                "sa1",
                "--no-gain-patience",
                "2",
                "--output-root",
                str(output_root / "SA-1"),
            ),
        },
        {
            "id": "SA-2",
            "description": "Stop if growth ratio exceeds threshold",
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                config_rel,
                "--stability-variant",
                "sa2",
                "--max-growth-ratio",
                "1.5",
                "--output-root",
                str(output_root / "SA-2"),
            ),
        },
        {
            "id": "SA-3",
            "description": "Repair only hard/high-priority feedback",
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                config_rel,
                "--stability-variant",
                "sa3",
                "--feedback-variant",
                "typed_priority",
                "--output-root",
                str(output_root / "SA-3"),
            ),
        },
        {
            "id": "SA-4",
            "description": "Local patch only",
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                config_rel,
                "--stability-variant",
                "sa4",
                "--local-repair-only",
                "--output-root",
                str(output_root / "SA-4"),
            ),
        },
        {
            "id": "SA-5",
            "description": "Hybrid stability-aware policy (main candidate)",
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                config_rel,
                "--stability-variant",
                "sa5",
                "--feedback-variant",
                "typed_priority",
                "--no-gain-patience",
                "2",
                "--max-growth-ratio",
                "1.5",
                "--max-patches-per-iter",
                "12",
                "--max-new-triples-per-iter",
                "200",
                "--output-root",
                str(output_root / "SA-5"),
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
                "description": row["description"],
                "exit_code": proc.returncode,
                "runtime_seconds": round(elapsed, 3),
                "run_root": str(args.output_root / row["id"]),
            }
        )
    args.status.parent.mkdir(parents=True, exist_ok=True)
    args.status.write_text(json.dumps(status_rows, indent=2), encoding="utf-8")
    print(f"Wrote stability-core status -> {args.status}")


if __name__ == "__main__":
    main()
