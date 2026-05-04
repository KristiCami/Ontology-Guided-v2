#!/usr/bin/env python3
"""Orchestrate journal experiment layers (A-D) with reproducible manifests."""

from __future__ import annotations

import argparse
import json
import time
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run journal layers A-D experiments")
    parser.add_argument("--execute", action="store_true", help="Execute commands (default: dry-run)")
    parser.add_argument(
        "--layer",
        choices=["all", "A", "B", "C", "D"],
        default="all",
        help="Run only a specific layer.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "runs/journal_master_manifest.json",
        help="Where to store generated experiment manifest.",
    )
    parser.add_argument(
        "--status",
        type=Path,
        default=PROJECT_ROOT / "runs/journal_execution_status.json",
        help="Where to store execution status with runtime/cost metadata.",
    )
    parser.add_argument(
        "--seed-list",
        type=str,
        default="1,2,3",
        help="Comma-separated seeds for seed variance diagnostics (E-DIAG-4).",
    )
    return parser.parse_args()


def _python_cmd(*parts: str) -> list[str]:
    return [sys.executable, *parts]


def _seeds(raw: str) -> list[int]:
    items = [part.strip() for part in raw.split(",") if part.strip()]
    return [int(part) for part in items]


def build_matrix(seed_values: list[int]) -> list[dict]:
    matrix = [
        # Layer A
        {
            "id": "E-BASE-1",
            "layer": "A",
            "cmd": _python_cmd(
                "scripts/run_e1_llm_only.py",
                "--config",
                "configs/e1_llm_only_atm.json",
                "--temperature",
                "0.1",
                "--seed",
                "1",
                "--prompt-mode",
                "raw",
                "--output-root",
                "runs/journal/E-BASE-1",
            ),
            "outputs": ["metrics_exact.json", "metrics_semantic.json", "run_report.json"],
        },
        {
            "id": "E-BASE-2",
            "layer": "A",
            "cmd": _python_cmd(
                "scripts/run_e1_llm_only.py",
                "--config",
                "configs/e1_llm_only_atm.json",
                "--temperature",
                "0.1",
                "--seed",
                "1",
                "--prompt-mode",
                "ontology_aware",
                "--output-root",
                "runs/journal/E-BASE-2",
            ),
            "outputs": ["metrics_exact.json", "metrics_semantic.json", "run_report.json"],
        },
        {
            "id": "E-BASE-3",
            "layer": "A",
            "cmd": _python_cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--output-root",
                "runs/journal/E-BASE-3",
            ),
            "outputs": ["repair_log.json", "final/metrics_semantic.json"],
        },
        {"id": "E-BASE-4", "layer": "A", "cmd": _python_cmd("scripts/run_e5_cross_domain.py", "--config", "configs/e5_cross_domain_manifest.json")},
        # Layer B
        {
            "id": "E-NOV-1",
            "layer": "B",
            "cmd": _python_cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--stability-variant",
                "sa5",
                "--feedback-variant",
                "typed_priority",
                "--output-root",
                "runs/journal/E-NOV-1",
            ),
            "outputs": ["diagnostics_summary.json", "final/metrics_semantic.json"],
        },
        {
            "id": "E-NOV-2",
            "layer": "B",
            "cmd": _python_cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--feedback-variant",
                "raw",
                "--output-root",
                "runs/journal/E-NOV-2",
            ),
            "outputs": ["diagnostics_summary.json", "final/metrics_semantic.json"],
        },
        {
            "id": "E-NOV-3",
            "layer": "B",
            "cmd": _python_cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--local-repair-only",
                "--output-root",
                "runs/journal/E-NOV-3",
            ),
            "outputs": ["diagnostics_summary.json", "final/metrics_semantic.json"],
        },
        {
            "id": "E-NOV-4",
            "layer": "B",
            "cmd": _python_cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--max-patches-per-iter",
                "12",
                "--max-growth-ratio",
                "1.5",
                "--max-new-triples-per-iter",
                "200",
                "--output-root",
                "runs/journal/E-NOV-4",
            ),
            "outputs": ["diagnostics_summary.json", "final/metrics_semantic.json"],
        },
        # Layer C
        {
            "id": "E-ABL-1",
            "layer": "C",
            "cmd": _python_cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--ablation-profile",
                "no_shacl",
                "--output-root",
                "runs/journal/E-ABL-1",
            ),
            "outputs": ["final/metrics_semantic.json", "repair_log.json"],
        },
        {
            "id": "E-ABL-2",
            "layer": "C",
            "cmd": _python_cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--ablation-profile",
                "no_reasoning",
                "--output-root",
                "runs/journal/E-ABL-2",
            ),
            "outputs": ["final/metrics_semantic.json", "repair_log.json"],
        },
        {
            "id": "E-ABL-3",
            "layer": "C",
            "cmd": _python_cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--ablation-profile",
                "no_cq",
                "--output-root",
                "runs/journal/E-ABL-3",
            ),
            "outputs": ["final/metrics_semantic.json", "repair_log.json"],
        },
        {
            "id": "E-ABL-4",
            "layer": "C",
            "cmd": _python_cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--ablation-profile",
                "no_ontology_context",
                "--output-root",
                "runs/journal/E-ABL-4",
            ),
            "outputs": ["final/metrics_semantic.json", "repair_log.json"],
        },
        {
            "id": "E-ABL-5",
            "layer": "C",
            "cmd": _python_cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--ablation-profile",
                "no_exemplars",
                "--output-root",
                "runs/journal/E-ABL-5",
            ),
            "outputs": ["final/metrics_semantic.json", "repair_log.json"],
        },
        {
            "id": "E-ABL-6",
            "layer": "C",
            "cmd": _python_cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--ablation-profile",
                "no_growth_control",
                "--output-root",
                "runs/journal/E-ABL-6",
            ),
            "outputs": ["final/metrics_semantic.json", "repair_log.json"],
        },
        # Layer D
        {
            "id": "E-DIAG-1",
            "layer": "D",
            "cmd": _python_cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--stability-variant",
                "sa5",
                "--output-root",
                "runs/journal/E-DIAG-1",
            ),
            "outputs": ["diagnostics_summary.json", "repair_log.json"],
        },
        {
            "id": "E-DIAG-2",
            "layer": "D",
            "cmd": _python_cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--stability-variant",
                "sa5",
                "--output-root",
                "runs/journal/E-DIAG-2",
            ),
            "outputs": ["diagnostics_summary.json"],
            "notes": "Uses diagnostics error_taxonomy fields for failure analysis table.",
        },
        {
            "id": "E-DIAG-3",
            "layer": "D",
            "cmd": _python_cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--stability-variant",
                "sa5",
                "--feedback-variant",
                "typed_priority",
                "--output-root",
                "runs/journal/E-DIAG-3",
            ),
            "outputs": ["final/metrics_semantic.json", "diagnostics_summary.json"],
            "notes": "Runtime and token/cost proxy captured in status report.",
        },
    ]
    for seed in seed_values:
        matrix.append(
            {
                "id": f"E-DIAG-4-S{seed}",
                "phase_id": "E-DIAG-4",
                "layer": "D",
                "cmd": _python_cmd(
                    "scripts/run_e1_llm_only.py",
                    "--config",
                    "configs/e1_llm_only_atm.json",
                    "--seed",
                    str(seed),
                    "--temperature",
                    "0.1",
                    "--prompt-mode",
                    "raw",
                    "--output-root",
                    f"runs/journal/E-DIAG-4/seed_{seed}",
                ),
                "outputs": ["metrics_semantic.json", "run_report.json"],
            }
        )
    return matrix


def main() -> None:
    args = parse_args()
    manifest = build_matrix(_seeds(args.seed_list))
    if args.layer != "all":
        manifest = [item for item in manifest if item["layer"] == args.layer]

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote manifest with {len(manifest)} experiments -> {args.manifest}")

    if not args.execute:
        for item in manifest:
            print(f"[DRY-RUN] {item['id']}: {' '.join(item['cmd'])}")
        return

    status_rows = []
    for item in manifest:
        print(f"[RUN] {item['id']}")
        started = time.perf_counter()
        proc = subprocess.run(item["cmd"], cwd=PROJECT_ROOT, check=False)
        elapsed = time.perf_counter() - started
        status_rows.append(
            {
                "id": item["id"],
                "phase_id": item.get("phase_id", item["id"]),
                "layer": item["layer"],
                "exit_code": proc.returncode,
                "runtime_seconds": round(elapsed, 3),
                "outputs": item.get("outputs", []),
            }
        )

    args.status.parent.mkdir(parents=True, exist_ok=True)
    args.status.write_text(json.dumps(status_rows, indent=2), encoding="utf-8")
    print(f"Wrote execution status -> {args.status}")


if __name__ == "__main__":
    main()
