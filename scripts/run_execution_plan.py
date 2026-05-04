#!/usr/bin/env python3
"""Execute Table-2 plan (steps 1-12) in journal order."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run execution plan Table 2 (steps 1-12).")
    parser.add_argument("--execute", action="store_true", help="Execute commands; otherwise dry-run.")
    parser.add_argument("--start-step", type=int, default=1, help="Start from this step (1-12).")
    parser.add_argument("--end-step", type=int, default=12, help="End at this step (1-12).")
    parser.add_argument(
        "--extra-domains-config",
        type=Path,
        default=PROJECT_ROOT / "configs/e5_cross_domain_manifest.json",
        help="Manifest JSON; step 9 runs entries in its 'extra_domains' list (same shape as 'domains').",
    )
    return parser.parse_args()


def _run(cmd: list[str], *, execute: bool, cwd: Path = PROJECT_ROOT) -> int:
    print(f"$ {' '.join(cmd)}")
    if not execute:
        return 0
    return subprocess.run(cmd, cwd=cwd, check=False).returncode


def _copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def step_1_freeze_configs(execute: bool) -> dict:
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    repro_root = PROJECT_ROOT / "runs/reproducibility" / f"freeze_{stamp}"
    print(f"[Step 1] Freeze configs/runs -> {repro_root}")
    if execute:
        repro_root.mkdir(parents=True, exist_ok=True)
        _copy_tree(PROJECT_ROOT / "configs", repro_root / "configs")
        _copy_tree(PROJECT_ROOT / "runs", repro_root / "runs_snapshot")
    return {"step": 1, "reproducibility_folder": str(repro_root)}


def step_2_baselines(execute: bool) -> dict:
    print("[Step 2] Re-run baseline family (Layer A)")
    rc = _run([sys.executable, "scripts/run_journal_layers.py", "--layer", "A", "--execute"] if execute else [sys.executable, "scripts/run_journal_layers.py", "--layer", "A"], execute=execute)
    return {"step": 2, "exit_code": rc}


def step_3_standardize_export(execute: bool) -> dict:
    print("[Step 3] Standardize metrics export")
    rc = _run([sys.executable, "scripts/build_journal_tables.py"], execute=execute)
    return {"step": 3, "exit_code": rc, "master_results": "runs/journal_tables/master_results.csv"}


def step_4_iteration_logging(execute: bool) -> dict:
    print("[Step 4] Ensure iteration logging via E-DIAG-1")
    cmd = [
        sys.executable,
        "scripts/run_e4_iterative.py",
        "--config",
        "configs/e4_iterative_repair_atm.json",
        "--stability-variant",
        "sa5",
        "--output-root",
        "runs/journal/E-DIAG-1",
    ]
    rc = _run(cmd, execute=execute)
    return {"step": 4, "exit_code": rc}


def step_5_stability_policy(execute: bool) -> dict:
    print("[Step 5] Implement/run stability-aware policy family")
    rc = _run([sys.executable, "scripts/run_journal_layers.py", "--layer", "B", "--execute"] if execute else [sys.executable, "scripts/run_journal_layers.py", "--layer", "B"], execute=execute)
    return {"step": 5, "exit_code": rc}


def step_6_novelty(execute: bool) -> dict:
    print("[Step 6] Run novelty experiments on ATM")
    rc = _run([sys.executable, "scripts/run_journal_layers.py", "--layer", "B", "--execute"] if execute else [sys.executable, "scripts/run_journal_layers.py", "--layer", "B"], execute=execute)
    return {"step": 6, "exit_code": rc}


def step_7_ablations(execute: bool) -> dict:
    print("[Step 7] Run ATM ablations")
    rc = _run([sys.executable, "scripts/run_journal_layers.py", "--layer", "C", "--execute"] if execute else [sys.executable, "scripts/run_journal_layers.py", "--layer", "C"], execute=execute)
    return {"step": 7, "exit_code": rc}


def step_8_healthcare(execute: bool) -> dict:
    print("[Step 8] Extend to healthcare")
    rc = _run([sys.executable, "scripts/run_e5_cross_domain.py", "--config", "configs/e5_cross_domain_manifest.json", "--llm-mode", "heuristic"], execute=execute)
    return {"step": 8, "exit_code": rc}


def step_9_extra_domains(execute: bool, extra_domains_config: Path) -> dict:
    print("[Step 9] Add one or two more domains (if provided via extra_domains in manifest)")
    if not extra_domains_config.exists():
        return {"step": 9, "skipped": True, "reason": f"Missing {extra_domains_config}"}
    payload = json.loads(extra_domains_config.read_text(encoding="utf-8"))
    extras = payload.get("extra_domains", [])
    if not extras:
        return {"step": 9, "skipped": True, "reason": "extra_domains is empty"}
    if not execute:
        return {"step": 9, "dry_run": True, "extra_domains": len(extras)}
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("e5_cross", PROJECT_ROOT / "scripts" / "run_e5_cross_domain.py")
    if spec is None or spec.loader is None:
        return {"step": 9, "error": "Could not load run_e5_cross_domain.py"}
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.run_domain_entries(extras, "heuristic")
    return {"step": 9, "runs": [{"name": d.get("name"), "mode": "inline_or_config"} for d in extras]}


def step_10_error_taxonomy(execute: bool) -> dict:
    print("[Step 10] Build error taxonomy logs")
    rc = _run([sys.executable, "scripts/run_journal_layers.py", "--layer", "D", "--execute"] if execute else [sys.executable, "scripts/run_journal_layers.py", "--layer", "D"], execute=execute)
    return {"step": 10, "exit_code": rc}


def step_11_multiseed(execute: bool) -> dict:
    print("[Step 11] Run multi-seed subset (3-5 seeds)")
    cmd = [sys.executable, "scripts/run_journal_layers.py", "--layer", "D", "--seed-list", "1,2,3,4,5", "--execute"] if execute else [sys.executable, "scripts/run_journal_layers.py", "--layer", "D", "--seed-list", "1,2,3,4,5"]
    rc = _run(cmd, execute=execute)
    return {"step": 11, "exit_code": rc}


def step_12_final_tables(execute: bool) -> dict:
    print("[Step 12] Build final plots/tables")
    rc_tables = _run([sys.executable, "scripts/build_journal_tables.py"], execute=execute)
    rc_plots = _run([sys.executable, "scripts/build_journal_plots.py"], execute=execute)
    return {"step": 12, "tables_exit_code": rc_tables, "plots_exit_code": rc_plots}


STEP_FUNCTIONS = {
    1: step_1_freeze_configs,
    2: step_2_baselines,
    3: step_3_standardize_export,
    4: step_4_iteration_logging,
    5: step_5_stability_policy,
    6: step_6_novelty,
    7: step_7_ablations,
    8: step_8_healthcare,
    9: step_9_extra_domains,
    10: step_10_error_taxonomy,
    11: step_11_multiseed,
    12: step_12_final_tables,
}


def main() -> None:
    args = parse_args()
    if args.start_step < 1 or args.end_step > 12 or args.start_step > args.end_step:
        raise SystemExit("Invalid step range. Use 1 <= start-step <= end-step <= 12")

    started = time.time()
    summary = []
    for step in range(args.start_step, args.end_step + 1):
        fn = STEP_FUNCTIONS[step]
        if step == 9:
            result = fn(args.execute, args.extra_domains_config)  # type: ignore[misc]
        else:
            result = fn(args.execute)  # type: ignore[misc]
        summary.append(result)

    output = {
        "executed": bool(args.execute),
        "start_step": args.start_step,
        "end_step": args.end_step,
        "elapsed_seconds": round(time.time() - started, 3),
        "summary": summary,
    }
    out_path = PROJECT_ROOT / "runs/execution_plan_status.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Wrote execution-plan status -> {out_path}")


if __name__ == "__main__":
    main()
