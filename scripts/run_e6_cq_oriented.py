#!/usr/bin/env python3
"""Run the E6 CQ-oriented experiment and summarize CQ pass rates per iteration."""
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


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the E6 CQ-oriented experiment")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "configs/e6_cq_oriented_atm.json")
    return parser.parse_args()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _cq_pass_rate(results: list[dict] | None) -> float:
    if not results:
        return 0.0
    passed = sum(1 for result in results if result.get("success"))
    return passed / len(results)


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    output_root = PROJECT_ROOT / cfg.get("output_root", "runs/E6_cq_oriented")
    ensure_dir(output_root)

    pipeline_config = PipelineConfig(
        requirements_path=PROJECT_ROOT / cfg["requirements_path"],
        shapes_path=PROJECT_ROOT / cfg["shapes_path"],
        base_ontology_path=None,
        competency_questions_path=PROJECT_ROOT / cfg.get("competency_questions")
        if cfg.get("competency_questions")
        else None,
        output_path=output_root / "pred.ttl",
        report_path=output_root / "run_report.json",
        llm_mode=cfg.get("llm_mode", "heuristic"),
        max_requirements=cfg.get("max_requirements", 20),
        reasoning_enabled=cfg.get("reasoning", True),
        max_iterations=cfg.get("iterations", 3),
        use_ontology_context=cfg.get("use_ontology_context", True),
        grounding_ontology_path=PROJECT_ROOT / cfg["ontology_path"] if cfg.get("ontology_path") else None,
        base_namespace=cfg.get("base_namespace", "http://lod.csd.auth.gr/atm/atm.ttl#"),
    )

    pipeline = OntologyDraftingPipeline(pipeline_config)
    report = pipeline.run()

    asserted_graph = pipeline.state_graph or Graph().parse(pipeline_config.output_path)
    data_graph = pipeline.reasoned_graph or asserted_graph

    if pipeline.last_shacl_report:
        (output_root / "validation_summary.json").write_text(
            json.dumps(summarize_shacl_report(pipeline.last_shacl_report), indent=2),
            encoding="utf-8",
        )

    gold_path = PROJECT_ROOT / cfg.get("ontology_path", "data/domains/atm/atm_gold.ttl")
    (output_root / "metrics_exact.json").write_text(
        json.dumps(compute_exact_metrics(pipeline_config.output_path, gold_path), indent=2),
        encoding="utf-8",
    )
    (output_root / "metrics_semantic.json").write_text(
        json.dumps(compute_semantic_metrics(data_graph, Graph().parse(gold_path)), indent=2),
        encoding="utf-8",
    )

    if report.get("iterations"):
        cq_summary = []
        for item in report["iterations"]:
            cq_summary.append(
                {
                    "iteration": item["iteration"],
                    "conforms": item["conforms"],
                    "cq_pass_rate": _cq_pass_rate(item.get("cq_results")),
                }
            )
        (output_root / "cq_summary.json").write_text(
            json.dumps(cq_summary, indent=2),
            encoding="utf-8",
        )

    print("E6 run complete. Key outputs written under", output_root)


if __name__ == "__main__":
    main()
