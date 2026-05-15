#!/usr/bin/env python3
"""Unify run outputs from every experiment source into a single master results table.

Sources merged:
- ``runs/journal_execution_status.json`` (from ``scripts/run_journal_layers.py``)
- ``runs/must_pass_status.json``         (from ``scripts/run_must_pass.py``)
- ``runs/ablation_matrix/status.json``   (from ``scripts/run_ablation_matrix.py``)
- ``runs/E5_cross_domain/<domain>/``     (from ``scripts/run_e5_cross_domain.py``)

Outputs (under ``runs/`` by default):
- ``master_results.csv``     -- one row per experiment run with a common schema
- ``master_results.json``    -- same rows plus per-layer/source aggregates
- ``master_results_summary.md`` -- human-readable summary for the paper appendix

Missing status files are skipped silently so the script is safe to run on a
partially-populated workspace (e.g. only MUST-PASS executed so far).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_SEED_SUFFIX_PATTERN = re.compile(r"-S(\d+)$")

MASTER_SCHEMA = [
    "source",
    "layer",
    "exp_id",
    "phase_id",
    "base_id",
    "seed",
    "run_root",
    "exit_code",
    "runtime_seconds",
    "f1_semantic",
    "cq_pass_rate",
    "hard_violations_final",
    "soft_violations_final",
    "total_tokens",
    "cost_proxy",
    "stop_reason",
    "stability_variant",
    "feedback_variant",
    "ablation_profile",
    "error_codes_count",
]


@dataclass
class ResultRow:
    source: str
    layer: str | None
    exp_id: str
    phase_id: str | None = None
    base_id: str | None = None
    seed: str | None = None
    run_root: str | None = None
    exit_code: int | None = None
    runtime_seconds: float | None = None
    f1_semantic: float | None = None
    cq_pass_rate: float | None = None
    hard_violations_final: int | None = None
    soft_violations_final: int | None = None
    total_tokens: int | None = None
    cost_proxy: float | None = None
    stop_reason: str | None = None
    stability_variant: str | None = None
    feedback_variant: str | None = None
    ablation_profile: str | None = None
    error_codes_count: int | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {key: getattr(self, key) for key in MASTER_SCHEMA}


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _parse_seed_id(exp_id: str) -> tuple[str, str | None]:
    match = _SEED_SUFFIX_PATTERN.search(exp_id)
    if not match:
        return exp_id, None
    return exp_id[: match.start()], match.group(1)


def _output_root_from_cmd(cmd: list[str]) -> Path | None:
    """Return ``Path`` referenced by ``--output-root`` in a command, if any."""

    for idx, token in enumerate(cmd):
        if token == "--output-root" and idx + 1 < len(cmd):
            value = Path(cmd[idx + 1])
            if not value.is_absolute():
                value = PROJECT_ROOT / value
            return value
    return None


def _f1_from_run_root(run_root: Path) -> float | None:
    """Read ``metrics_semantic.json`` (E1) or ``final/metrics_semantic.json`` (E4)."""

    for candidate in (run_root / "final" / "metrics_semantic.json", run_root / "metrics_semantic.json"):
        payload = _read_json(candidate)
        if isinstance(payload, dict):
            value = payload.get("f1")
            if isinstance(value, (int, float)):
                return float(value)
    return None


def _cq_rate_from_run_root(run_root: Path) -> float | None:
    for candidate in (run_root / "final" / "cq_results.json", run_root / "cq_results.json"):
        payload = _read_json(candidate)
        if isinstance(payload, dict):
            value = payload.get("pass_rate")
            if isinstance(value, (int, float)):
                return float(value)
    return None


def _shacl_summary_from_run_root(run_root: Path) -> tuple[int | None, int | None]:
    payload = _read_json(run_root / "final" / "validation_summary.json")
    if not isinstance(payload, dict):
        payload = _read_json(run_root / "validation_summary.json")
    if not isinstance(payload, dict):
        return None, None
    violations = payload.get("violations")
    if not isinstance(violations, dict):
        return None, None
    hard = violations.get("hard")
    soft = violations.get("soft")
    hard_val = int(hard) if isinstance(hard, (int, float)) else None
    soft_val = int(soft) if isinstance(soft, (int, float)) else None
    return hard_val, soft_val


def _tokens_from_run_root(run_root: Path) -> int | None:
    payload = _read_json(run_root / "run_report.json")
    if not isinstance(payload, dict):
        return None
    usage = payload.get("token_usage")
    if not isinstance(usage, dict):
        return None
    total = usage.get("total_tokens")
    if isinstance(total, int):
        return total
    return None


def _experiment_metadata_from_run_root(run_root: Path) -> dict[str, Any]:
    payload = _read_json(run_root / "run_report.json")
    if not isinstance(payload, dict):
        return {}
    meta = payload.get("experiment_metadata")
    return meta if isinstance(meta, dict) else {}


def _stop_reason_from_run_root(run_root: Path) -> str | None:
    payload = _read_json(run_root / "run_report.json")
    if isinstance(payload, dict):
        stop = payload.get("stop_reason")
        if isinstance(stop, str):
            return stop
    repair_log = _read_json(run_root / "repair_log.json")
    if isinstance(repair_log, dict):
        stop = repair_log.get("stop_reason") or (repair_log.get("stop") or {}).get("reason")
        if isinstance(stop, str):
            return stop
    return None


def _error_codes_from_run_root(run_root: Path) -> int:
    payload = _read_json(run_root / "diagnostics_summary.json")
    if not isinstance(payload, dict):
        return 0
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return 0
    codes: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            for code in row.get("error_taxonomy") or []:
                codes.add(str(code))
    return len(codes)


def _enrich_from_run_root(row: ResultRow, run_root: Path) -> None:
    row.run_root = str(run_root)
    row.f1_semantic = _f1_from_run_root(run_root)
    row.cq_pass_rate = _cq_rate_from_run_root(run_root)
    hard, soft = _shacl_summary_from_run_root(run_root)
    row.hard_violations_final = hard
    row.soft_violations_final = soft
    row.total_tokens = _tokens_from_run_root(run_root)
    if isinstance(row.runtime_seconds, (int, float)) and isinstance(row.total_tokens, int):
        row.cost_proxy = (row.total_tokens / 1000.0) * float(row.runtime_seconds)
    row.stop_reason = _stop_reason_from_run_root(run_root)
    row.error_codes_count = _error_codes_from_run_root(run_root)
    meta = _experiment_metadata_from_run_root(run_root)
    if meta:
        row.stability_variant = meta.get("stability_variant")
        row.feedback_variant = meta.get("feedback_variant")
        row.ablation_profile = meta.get("ablation_profile")
        if row.seed is None and meta.get("seed") is not None:
            row.seed = str(meta["seed"])


def collect_journal_layers(status_path: Path) -> list[ResultRow]:
    status = _read_json(status_path)
    if not isinstance(status, list):
        return []
    rows: list[ResultRow] = []
    for item in status:
        if not isinstance(item, dict):
            continue
        exp_id = str(item.get("id", ""))
        base_id, seed = _parse_seed_id(exp_id)
        if seed is not None:
            run_root = PROJECT_ROOT / "runs/journal" / base_id / f"seed_{seed}"
        else:
            run_root = PROJECT_ROOT / "runs/journal" / exp_id
        row = ResultRow(
            source="journal_layers",
            layer=item.get("layer"),
            exp_id=exp_id,
            phase_id=item.get("phase_id", base_id if seed is not None else exp_id),
            base_id=base_id,
            seed=seed,
            exit_code=item.get("exit_code"),
            runtime_seconds=item.get("runtime_seconds"),
        )
        _enrich_from_run_root(row, run_root)
        rows.append(row)
    return rows


def collect_must_pass(status_path: Path, manifest_path: Path) -> list[ResultRow]:
    status = _read_json(status_path) or []
    manifest = _read_json(manifest_path) or []
    cmd_by_id: dict[str, list[str]] = {}
    for entry in manifest if isinstance(manifest, list) else []:
        if isinstance(entry, dict) and "id" in entry and "cmd" in entry:
            cmd_by_id[entry["id"]] = entry["cmd"]

    rows: list[ResultRow] = []
    for item in status if isinstance(status, list) else []:
        if not isinstance(item, dict):
            continue
        exp_id = str(item.get("id", ""))
        cmd = cmd_by_id.get(exp_id, [])
        run_root = _output_root_from_cmd(cmd)
        row = ResultRow(
            source="must_pass",
            layer="MUST",
            exp_id=exp_id,
            phase_id=item.get("must_id", exp_id),
            base_id=item.get("must_id"),
            exit_code=item.get("exit_code"),
            runtime_seconds=item.get("runtime_seconds"),
        )
        if run_root is not None:
            _enrich_from_run_root(row, run_root)
        rows.append(row)
    return rows


def collect_ablation_matrix(status_path: Path) -> list[ResultRow]:
    status = _read_json(status_path)
    if not isinstance(status, list):
        return []
    rows: list[ResultRow] = []
    for item in status:
        if not isinstance(item, dict):
            continue
        exp_id = str(item.get("id", ""))
        run_root_raw = item.get("run_root")
        run_root = Path(run_root_raw) if run_root_raw else None
        if run_root and not run_root.is_absolute():
            run_root = PROJECT_ROOT / run_root
        row = ResultRow(
            source="ablation_matrix",
            layer="C",
            exp_id=exp_id,
            phase_id=exp_id,
            base_id=exp_id,
            exit_code=item.get("exit_code"),
            runtime_seconds=item.get("runtime_seconds"),
        )
        if run_root is not None:
            _enrich_from_run_root(row, run_root)
        rows.append(row)
    return rows


def collect_cross_domain(cross_root: Path) -> list[ResultRow]:
    if not cross_root.exists():
        return []
    rows: list[ResultRow] = []
    for entry in sorted(cross_root.iterdir()):
        if not entry.is_dir():
            continue
        row = ResultRow(
            source="cross_domain",
            layer="A",
            exp_id=f"E-BASE-4-{entry.name}",
            phase_id="E-BASE-4",
            base_id=entry.name,
        )
        _enrich_from_run_root(row, entry)
        rows.append(row)
    return rows


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def _mean(values: Iterable[float]) -> float | None:
    pool = [float(v) for v in values if isinstance(v, (int, float))]
    if not pool:
        return None
    return sum(pool) / len(pool)


def _stdev(values: Iterable[float]) -> float | None:
    pool = [float(v) for v in values if isinstance(v, (int, float))]
    if len(pool) < 2:
        return 0.0 if pool else None
    return statistics.pstdev(pool)


def _build_summary(rows: list[ResultRow]) -> dict[str, Any]:
    by_layer: dict[str, list[ResultRow]] = defaultdict(list)
    by_source: dict[str, list[ResultRow]] = defaultdict(list)
    for row in rows:
        if row.layer:
            by_layer[row.layer].append(row)
        by_source[row.source].append(row)

    def _aggregate(group: Iterable[ResultRow]) -> dict[str, Any]:
        items = list(group)
        return {
            "count": len(items),
            "exit_code_zero_pct": (
                sum(1 for r in items if r.exit_code == 0) / len(items) if items else None
            ),
            "mean_f1": _mean(r.f1_semantic for r in items if r.f1_semantic is not None),
            "std_f1": _stdev(r.f1_semantic for r in items if r.f1_semantic is not None),
            "mean_cq_pass_rate": _mean(r.cq_pass_rate for r in items if r.cq_pass_rate is not None),
            "total_tokens": sum(r.total_tokens for r in items if isinstance(r.total_tokens, int)),
            "total_runtime_seconds": sum(
                r.runtime_seconds for r in items if isinstance(r.runtime_seconds, (int, float))
            ),
        }

    return {
        "by_layer": {layer: _aggregate(items) for layer, items in sorted(by_layer.items())},
        "by_source": {source: _aggregate(items) for source, items in sorted(by_source.items())},
        "total": _aggregate(rows),
    }


def _render_summary_markdown(summary: dict[str, Any], total_rows: int) -> str:
    lines = ["# Master Results Summary", ""]
    lines.append(f"- Total rows: **{total_rows}**")
    total = summary.get("total", {})
    if total.get("mean_f1") is not None:
        lines.append(f"- Overall mean F1 (semantic): **{total['mean_f1']:.4f}**")
    if total.get("total_tokens"):
        lines.append(f"- Total tokens (across runs): **{total['total_tokens']:,}**")
    if total.get("total_runtime_seconds"):
        lines.append(f"- Total runtime (s): **{total['total_runtime_seconds']:.1f}**")
    lines.append("")

    lines.append("## By layer")
    lines.append("")
    lines.append("| Layer | Count | Mean F1 | Std F1 | Mean CQ pass | Tokens | Runtime (s) |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for layer, agg in summary.get("by_layer", {}).items():
        lines.append(
            "| {layer} | {count} | {mf1} | {sf1} | {mcq} | {tokens} | {runtime} |".format(
                layer=layer,
                count=agg.get("count", 0),
                mf1=f"{agg['mean_f1']:.4f}" if agg.get("mean_f1") is not None else "-",
                sf1=f"{agg['std_f1']:.4f}" if agg.get("std_f1") is not None else "-",
                mcq=f"{agg['mean_cq_pass_rate']:.4f}" if agg.get("mean_cq_pass_rate") is not None else "-",
                tokens=f"{agg.get('total_tokens', 0):,}" if agg.get("total_tokens") else "-",
                runtime=f"{agg['total_runtime_seconds']:.1f}" if agg.get("total_runtime_seconds") else "-",
            )
        )
    lines.append("")

    lines.append("## By source")
    lines.append("")
    lines.append("| Source | Count | Mean F1 | Tokens | Runtime (s) |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for source, agg in summary.get("by_source", {}).items():
        lines.append(
            "| {source} | {count} | {mf1} | {tokens} | {runtime} |".format(
                source=source,
                count=agg.get("count", 0),
                mf1=f"{agg['mean_f1']:.4f}" if agg.get("mean_f1") is not None else "-",
                tokens=f"{agg.get('total_tokens', 0):,}" if agg.get("total_tokens") else "-",
                runtime=f"{agg['total_runtime_seconds']:.1f}" if agg.get("total_runtime_seconds") else "-",
            )
        )
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a unified master results CSV/JSON across all run sources.")
    parser.add_argument(
        "--journal-status",
        type=Path,
        default=PROJECT_ROOT / "runs/journal_execution_status.json",
        help="Status JSON produced by scripts/run_journal_layers.py.",
    )
    parser.add_argument(
        "--must-status",
        type=Path,
        default=PROJECT_ROOT / "runs/must_pass_status.json",
        help="Status JSON produced by scripts/run_must_pass.py.",
    )
    parser.add_argument(
        "--must-manifest",
        type=Path,
        default=PROJECT_ROOT / "runs/must_manifest.json",
        help="Manifest JSON written by scripts/run_must_pass.py for run_root resolution.",
    )
    parser.add_argument(
        "--ablation-status",
        type=Path,
        default=PROJECT_ROOT / "runs/ablation_matrix/status.json",
        help="Status JSON produced by scripts/run_ablation_matrix.py.",
    )
    parser.add_argument(
        "--cross-domain-root",
        type=Path,
        default=PROJECT_ROOT / "runs/E5_cross_domain",
        help="Root directory containing E5 cross-domain run outputs (one subdir per domain).",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=PROJECT_ROOT / "runs",
        help="Where master_results.csv / .json / _summary.md will be written.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows: list[ResultRow] = []
    rows.extend(collect_journal_layers(args.journal_status))
    rows.extend(collect_must_pass(args.must_status, args.must_manifest))
    rows.extend(collect_ablation_matrix(args.ablation_status))
    rows.extend(collect_cross_domain(args.cross_domain_root))

    row_dicts = [r.to_dict() for r in rows]
    summary = _build_summary(rows)

    args.outdir.mkdir(parents=True, exist_ok=True)
    _write_csv(args.outdir / "master_results.csv", row_dicts, MASTER_SCHEMA)
    (args.outdir / "master_results.json").write_text(
        json.dumps({"rows": row_dicts, "summary": summary}, indent=2), encoding="utf-8"
    )
    (args.outdir / "master_results_summary.md").write_text(
        _render_summary_markdown(summary, len(row_dicts)), encoding="utf-8"
    )
    print(f"Wrote {len(row_dicts)} master rows to {args.outdir / 'master_results.csv'}")


if __name__ == "__main__":
    main()
