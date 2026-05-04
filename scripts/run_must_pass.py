#!/usr/bin/env python3
"""Run MUST-PASS subset (M1-M8) for journal skeleton."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run MUST-PASS experiment subset (M1-M8).")
    parser.add_argument("--execute", action="store_true", help="Execute commands; default is dry-run.")
    parser.add_argument(
        "--status",
        type=Path,
        default=PROJECT_ROOT / "runs/must_pass_status.json",
        help="Output JSON status file.",
    )
    return parser.parse_args()


def _cmd(*parts: str) -> list[str]:
    return [sys.executable, *parts]


def build_must_matrix() -> list[dict]:
    return [
        # M1 Raw drafting baseline low/high temperature
        {
            "id": "M1-low-temp",
            "must_id": "M1",
            "name": "Raw drafting baseline low temp",
            "cmd": _cmd(
                "scripts/run_e1_llm_only.py",
                "--config",
                "configs/e1_llm_only_atm.json",
                "--prompt-mode",
                "raw",
                "--temperature",
                "0.1",
                "--seed",
                "1",
                "--output-root",
                "runs/must/M1/low_temp",
            ),
            "outputs": ["metrics_semantic.json", "run_report.json"],
        },
        {
            "id": "M1-high-temp",
            "must_id": "M1",
            "name": "Raw drafting baseline high temp",
            "cmd": _cmd(
                "scripts/run_e1_llm_only.py",
                "--config",
                "configs/e1_llm_only_atm.json",
                "--prompt-mode",
                "raw",
                "--temperature",
                "0.8",
                "--seed",
                "1",
                "--output-root",
                "runs/must/M1/high_temp",
            ),
            "outputs": ["metrics_semantic.json", "run_report.json"],
        },
        # M2 Ontology-aware vs no ontology-aware
        {
            "id": "M2-no-context",
            "must_id": "M2",
            "name": "Raw baseline without ontology context",
            "cmd": _cmd(
                "scripts/run_e1_llm_only.py",
                "--config",
                "configs/e1_llm_only_atm.json",
                "--prompt-mode",
                "raw",
                "--temperature",
                "0.1",
                "--seed",
                "2",
                "--output-root",
                "runs/must/M2/no_context",
            ),
            "outputs": ["metrics_semantic.json", "run_report.json"],
        },
        {
            "id": "M2-with-context",
            "must_id": "M2",
            "name": "Drafting with ontology grounding context",
            "cmd": _cmd(
                "scripts/run_e1_llm_only.py",
                "--config",
                "configs/e1_llm_only_atm.json",
                "--prompt-mode",
                "ontology_aware",
                "--temperature",
                "0.1",
                "--seed",
                "2",
                "--output-root",
                "runs/must/M2/with_context",
            ),
            "outputs": ["metrics_semantic.json", "run_report.json"],
        },
        # M3 Current repair policy comparison
        {
            "id": "M3-policy-comparison",
            "must_id": "M3",
            "name": "Repair policy sweep",
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--stop-policies",
                "default,max_only,hard_and_cq,ignore_no_hard",
                "--output-root",
                "runs/must/M3/policies",
            ),
            "outputs": ["repair_log.json", "final/metrics_semantic.json"],
        },
        # M4 Stability-aware vs current best
        {
            "id": "M4-current-best",
            "must_id": "M4",
            "name": "Current best policy reference",
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--stop-policies",
                "max_only",
                "--output-root",
                "runs/must/M4/current_best",
            ),
            "outputs": ["final/metrics_semantic.json", "diagnostics_summary.json"],
        },
        {
            "id": "M4-stability-aware",
            "must_id": "M4",
            "name": "Stability-aware policy candidate",
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--stability-variant",
                "sa5",
                "--feedback-variant",
                "typed_priority",
                "--output-root",
                "runs/must/M4/stability_aware",
            ),
            "outputs": ["final/metrics_semantic.json", "diagnostics_summary.json"],
        },
        # M5 Ablations: no SHACL / no reasoning / no CQ
        {
            "id": "M5-no-shacl",
            "must_id": "M5",
            "name": "Ablation without SHACL",
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--ablation-profile",
                "no_shacl",
                "--output-root",
                "runs/must/M5/no_shacl",
            ),
            "outputs": ["final/metrics_semantic.json", "repair_log.json"],
        },
        {
            "id": "M5-no-reasoning",
            "must_id": "M5",
            "name": "Ablation without reasoning",
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--ablation-profile",
                "no_reasoning",
                "--output-root",
                "runs/must/M5/no_reasoning",
            ),
            "outputs": ["final/metrics_semantic.json", "repair_log.json"],
        },
        {
            "id": "M5-no-cq",
            "must_id": "M5",
            "name": "Ablation without CQ feedback",
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--ablation-profile",
                "no_cq",
                "--output-root",
                "runs/must/M5/no_cq",
            ),
            "outputs": ["final/metrics_semantic.json", "repair_log.json"],
        },
        # M6 Iteration dynamics logging
        {
            "id": "M6-iteration-dynamics",
            "must_id": "M6",
            "name": "Detailed iteration dynamics logging",
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--stability-variant",
                "sa5",
                "--output-root",
                "runs/must/M6/iteration_dynamics",
            ),
            "outputs": ["repair_log.json", "diagnostics_summary.json"],
        },
        # M7 Error taxonomy analysis
        {
            "id": "M7-error-taxonomy",
            "must_id": "M7",
            "name": "Failure taxonomy extraction run",
            "cmd": _cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--stability-variant",
                "sa5",
                "--feedback-variant",
                "typed_priority",
                "--output-root",
                "runs/must/M7/error_taxonomy",
            ),
            "outputs": ["diagnostics_summary.json"],
        },
        # M8 Cross-domain comparison
        {
            "id": "M8-cross-domain",
            "must_id": "M8",
            "name": "ATM vs healthcare transfer comparison",
            "cmd": _cmd(
                "scripts/run_e5_cross_domain.py",
                "--config",
                "configs/e5_cross_domain_manifest.json",
                "--llm-mode",
                "heuristic",
            ),
            "outputs": ["runs/E5_cross_domain/atm/metrics_semantic.json", "runs/E5_cross_domain/health/metrics_semantic.json"],
        },
    ]


def main() -> None:
    args = parse_args()
    matrix = build_must_matrix()
    args.status.parent.mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "runs/must").mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "runs/must_manifest.json").write_text(json.dumps(matrix, indent=2), encoding="utf-8")

    if not args.execute:
        for item in matrix:
            print(f"[DRY-RUN] {item['id']}: {' '.join(item['cmd'])}")
        return

    rows = []
    for item in matrix:
        print(f"[RUN] {item['id']}")
        started = time.perf_counter()
        proc = subprocess.run(item["cmd"], cwd=PROJECT_ROOT, check=False)
        elapsed = time.perf_counter() - started
        rows.append(
            {
                "id": item["id"],
                "must_id": item["must_id"],
                "name": item["name"],
                "exit_code": proc.returncode,
                "runtime_seconds": round(elapsed, 3),
                "outputs": item.get("outputs", []),
            }
        )
    args.status.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Wrote MUST status -> {args.status}")


if __name__ == "__main__":
    main()
