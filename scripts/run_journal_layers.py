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
    parser.add_argument(
        "--novelty-seed-list",
        type=str,
        default="1",
        help=(
            "Comma-separated seeds for novelty variance (E-NOV-1 main novelty). "
            "Use 1 seed to keep matrix lean; >=3 for mean/std reporting."
        ),
    )
    parser.add_argument(
        "--ablation-seed-list",
        type=str,
        default="1",
        help=(
            "Comma-separated seeds for ablation runs (E-ABL-1..6). "
            "Use 1 seed by default to limit cost."
        ),
    )
    return parser.parse_args()


def _python_cmd(*parts: str) -> list[str]:
    return [sys.executable, *parts]


def _seeds(raw: str) -> list[int]:
    items = [part.strip() for part in raw.split(",") if part.strip()]
    return [int(part) for part in items]


def _expand_seeds(
    *,
    base_id: str,
    layer: str,
    cmd_template: list[str],
    seeds: list[int],
    output_template: str,
    outputs: list[str] | None = None,
    notes: str | None = None,
) -> list[dict]:
    """Replicate a base experiment across seeds, emitting per-seed entries.

    Each replicated entry uses ID ``<base_id>-S<seed>`` (matching the
    convention already established for E-DIAG-4) so that
    ``scripts/build_journal_tables.py`` can group and summarise them.
    Single-seed lists collapse back to the original (non-replicated) entry to
    keep the matrix lean by default.
    """

    if len(seeds) <= 1:
        seed = seeds[0] if seeds else 1
        cmd = list(cmd_template) + ["--seed", str(seed), "--output-root", output_template.format(seed=seed)]
        entry: dict = {"id": base_id, "layer": layer, "cmd": cmd}
        if outputs:
            entry["outputs"] = outputs
        if notes:
            entry["notes"] = notes
        return [entry]

    entries: list[dict] = []
    for seed in seeds:
        cmd = list(cmd_template) + ["--seed", str(seed), "--output-root", output_template.format(seed=seed)]
        entry = {
            "id": f"{base_id}-S{seed}",
            "phase_id": base_id,
            "layer": layer,
            "cmd": cmd,
        }
        if outputs:
            entry["outputs"] = outputs
        if notes:
            entry["notes"] = notes
        entries.append(entry)
    return entries


def build_matrix(
    seed_values: list[int],
    novelty_seeds: list[int] | None = None,
    ablation_seeds: list[int] | None = None,
) -> list[dict]:
    novelty_seeds = novelty_seeds or [1]
    ablation_seeds = ablation_seeds or [1]
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
        # Layer B (E-NOV-1 seed-expanded entries appended after this static block)
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
        # Layer C (E-ABL-* seed-expanded entries appended after this static block)
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

    # Layer B — E-NOV-1 main novelty, optionally seed-replicated for mean/std
    matrix.extend(
        _expand_seeds(
            base_id="E-NOV-1",
            layer="B",
            cmd_template=_python_cmd(
                "scripts/run_e4_iterative.py",
                "--config",
                "configs/e4_iterative_repair_atm.json",
                "--stability-variant",
                "sa5",
                "--feedback-variant",
                "typed_priority",
            ),
            seeds=novelty_seeds,
            output_template="runs/journal/E-NOV-1/seed_{seed}"
            if len(novelty_seeds) > 1
            else "runs/journal/E-NOV-1",
            outputs=["diagnostics_summary.json", "final/metrics_semantic.json", "run_report.json"],
        )
    )

    # Layer C — ablations, optionally seed-replicated for robustness checks
    ablation_specs = [
        ("E-ABL-1", "no_shacl"),
        ("E-ABL-2", "no_reasoning"),
        ("E-ABL-3", "no_cq"),
        ("E-ABL-4", "no_ontology_context"),
        ("E-ABL-5", "no_exemplars"),
        ("E-ABL-6", "no_growth_control"),
    ]
    for base_id, profile in ablation_specs:
        matrix.extend(
            _expand_seeds(
                base_id=base_id,
                layer="C",
                cmd_template=_python_cmd(
                    "scripts/run_e4_iterative.py",
                    "--config",
                    "configs/e4_iterative_repair_atm.json",
                    "--ablation-profile",
                    profile,
                ),
                seeds=ablation_seeds,
                output_template=(
                    f"runs/journal/{base_id}/seed_{{seed}}"
                    if len(ablation_seeds) > 1
                    else f"runs/journal/{base_id}"
                ),
                outputs=["final/metrics_semantic.json", "repair_log.json", "run_report.json"],
            )
        )

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

    # Stable sort by (layer, phase_id, id) so the manifest reads A -> B -> C -> D
    # even after seed-expanded blocks are appended.
    matrix.sort(key=lambda entry: (entry["layer"], entry.get("phase_id", entry["id"]), entry["id"]))
    return matrix


def main() -> None:
    args = parse_args()
    manifest = build_matrix(
        _seeds(args.seed_list),
        novelty_seeds=_seeds(args.novelty_seed_list),
        ablation_seeds=_seeds(args.ablation_seed_list),
    )
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
