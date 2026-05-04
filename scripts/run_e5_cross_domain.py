#!/usr/bin/env python3
"""Run the E5 cross-domain experiment across multiple domain blocks."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rdflib import Graph

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from og_nsd import OntologyDraftingPipeline, PipelineConfig  # noqa: E402
from og_nsd.metrics import compute_exact_metrics, compute_semantic_metrics  # noqa: E402
from og_nsd.shacl import summarize_shacl_report  # noqa: E402

_DOMAIN_META_KEYS = frozenset({"name", "output_root", "config"})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the E5 cross-domain experiment")
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "configs/e5_cross_domain_manifest.json",
        help="Path to JSON with a 'domains' list (inline blocks and/or config paths)",
    )
    parser.add_argument(
        "--llm-mode",
        dest="llm_mode",
        choices=["openai", "heuristic"],
        default=None,
        help="Override llm_mode for all listed domains (e.g., heuristic to avoid API quota issues)",
    )
    return parser.parse_args()


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def resolve_domain_entry(domain: dict) -> tuple[str, Path | None, dict]:
    """Return (name, output_root, cfg_dict). Each domain is either a path reference or an inline experiment block."""

    output_root = PROJECT_ROOT / domain["output_root"] if domain.get("output_root") else None
    cfg_rel = domain.get("config")
    if cfg_rel:
        cfg_path = PROJECT_ROOT / cfg_rel
        cfg = load_config(cfg_path)
        name = domain.get("name") or cfg_path.stem
        return name, output_root, cfg
    cfg = {k: v for k, v in domain.items() if k not in _DOMAIN_META_KEYS}
    name = domain.get("name") or "domain"
    return name, output_root, cfg


def run_domain(name: str, cfg: dict, output_root: Path | None, llm_mode_override: str | None) -> None:
    resolved_output_root = output_root or (PROJECT_ROOT / cfg.get("output_root", f"runs/E5_cross_domain/{name}"))
    ensure_dir(resolved_output_root)

    pipeline_config = PipelineConfig(
        requirements_path=PROJECT_ROOT / cfg["requirements_path"],
        shapes_path=PROJECT_ROOT / cfg["shapes_path"],
        base_ontology_path=None,
        competency_questions_path=PROJECT_ROOT / cfg.get("competency_questions")
        if cfg.get("competency_questions")
        else None,
        output_path=resolved_output_root / "pred.ttl",
        report_path=resolved_output_root / "run_report.json",
        llm_mode=llm_mode_override or cfg.get("llm_mode", "heuristic"),
        max_requirements=cfg.get("max_requirements", 20),
        reasoning_enabled=cfg.get("reasoning", True),
        max_iterations=cfg.get("iterations", 0),
        use_ontology_context=cfg.get("use_ontology_context", True),
        grounding_ontology_path=PROJECT_ROOT / cfg["ontology_path"] if cfg.get("ontology_path") else None,
        base_namespace=cfg.get("base_namespace", "http://lod.csd.auth.gr/atm/atm.ttl#"),
    )

    pipeline = OntologyDraftingPipeline(pipeline_config)
    pipeline.run()

    asserted_graph = pipeline.state_graph or Graph().parse(pipeline_config.output_path)
    data_graph = pipeline.reasoned_graph or asserted_graph

    if pipeline.last_shacl_report:
        (resolved_output_root / "validation_summary.json").write_text(
            json.dumps(summarize_shacl_report(pipeline.last_shacl_report), indent=2),
            encoding="utf-8",
        )

    gold_path = PROJECT_ROOT / cfg.get("ontology_path", "data/domains/atm/atm_gold.ttl")
    (resolved_output_root / "metrics_exact.json").write_text(
        json.dumps(compute_exact_metrics(pipeline_config.output_path, gold_path), indent=2),
        encoding="utf-8",
    )
    (resolved_output_root / "metrics_semantic.json").write_text(
        json.dumps(compute_semantic_metrics(data_graph, Graph().parse(gold_path)), indent=2),
        encoding="utf-8",
    )

    print(f"E5 run complete for {name}. Outputs written under {resolved_output_root}")


def run_domain_entries(domains: list[dict], llm_mode_override: str | None) -> None:
    """Run a list of domain entries (used for manifest ``domains`` or ``extra_domains``)."""

    for domain in domains:
        name, output_root, cfg = resolve_domain_entry(domain)
        run_domain(name, cfg, output_root, llm_mode_override)


def main() -> None:
    args = parse_args()
    payload = load_config(args.config)
    domains = payload.get("domains", [])
    if not domains:
        raise SystemExit("No 'domains' entries in configs/e5_cross_domain_manifest.json")

    run_domain_entries(domains, args.llm_mode)


if __name__ == "__main__":
    main()
