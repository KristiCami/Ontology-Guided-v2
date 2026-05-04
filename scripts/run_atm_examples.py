#!/usr/bin/env python3
"""Preset runner for the ATM ontology-aware (E3) experiment."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from og_nsd import OntologyDraftingPipeline, PipelineConfig  # noqa: E402
from og_nsd.metrics import (  # noqa: E402
    compute_exact_metrics_from_graphs,
    compute_semantic_metrics,
)
from og_nsd.queries import CompetencyQuestionRunner  # noqa: E402
from og_nsd.shacl import ShaclValidator, summarize_shacl_report  # noqa: E402
from rdflib import Graph  # noqa: E402


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ATM ontology-aware example (E3)")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "configs/e3_ontology_aware_atm.json")
    return parser.parse_args()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    output_root = PROJECT_ROOT / cfg.get("output_root", "runs/E3_no_repair")
    iter_dir = output_root / "iter0"
    ensure_dir(iter_dir)

    ontology_context = cfg.get("ontology_context_path") or cfg.get("ontology_path")
    grounding_path = PROJECT_ROOT / ontology_context if ontology_context else None

    pipeline_config = PipelineConfig(
        requirements_path=PROJECT_ROOT / cfg["requirements_path"],
        shapes_path=PROJECT_ROOT / cfg["shapes_path"],
        base_ontology_path=None,
        competency_questions_path=PROJECT_ROOT / cfg.get("competency_questions")
        if cfg.get("competency_questions")
        else None,
        output_path=iter_dir / "pred.ttl",
        report_path=output_root / "run_report.json",
        llm_mode=cfg.get("llm_mode", "heuristic"),
        max_requirements=cfg.get("max_requirements", 50),
        reasoning_enabled=cfg.get("reasoning", False),
        max_iterations=cfg.get("iterations", 15),
        use_ontology_context=cfg.get("use_ontology_context", False),
        grounding_ontology_path=grounding_path,
        dev_split_path=PROJECT_ROOT / cfg.get("dev_split") if cfg.get("dev_split") else None,
        test_split_path=PROJECT_ROOT / cfg.get("test_split") if cfg.get("test_split") else None,
    )

    pipeline = OntologyDraftingPipeline(pipeline_config)
    pipeline.run()

    asserted_graph = pipeline.state_graph or Graph().parse(pipeline_config.output_path)
    reasoning_result = pipeline.reasoner.run(asserted_graph)
    data_graph = reasoning_result.expanded_graph

    validator = ShaclValidator(pipeline_config.shapes_path) if pipeline_config.shapes_path else None
    if validator:
        shacl_report = validator.validate(data_graph)
        validation_report_path = output_root / "validation_report.ttl"
        if shacl_report.report_graph_ttl:
            validation_report_path.write_text(shacl_report.report_graph_ttl, encoding="utf-8")
        summary_path = output_root / "validation_summary.json"
        summary_path.write_text(json.dumps(summarize_shacl_report(shacl_report), indent=2), encoding="utf-8")

    gold_path = PROJECT_ROOT / cfg.get("gold_path", "data/domains/atm/atm_gold.ttl")
    gold_graph = Graph().parse(gold_path)
    exact_metrics_path = output_root / "metrics_exact.json"
    semantic_metrics_path = output_root / "metrics_semantic.json"
    exact_metrics_path.write_text(
        json.dumps(compute_exact_metrics_from_graphs(data_graph, gold_graph), indent=2),
        encoding="utf-8",
    )
    semantic_metrics_path.write_text(
        json.dumps(
            compute_semantic_metrics(data_graph, gold_graph),
            indent=2,
        ),
        encoding="utf-8",
    )

    reasoning_payload = {
        "unsat_classes": reasoning_result.report.unsatisfiable_classes,
        "total_unsat": len(reasoning_result.report.unsatisfiable_classes),
        "notes": reasoning_result.report.notes,
    }
    (output_root / "reasoning_report.json").write_text(
        json.dumps(reasoning_payload, indent=2), encoding="utf-8"
    )

    if pipeline_config.competency_questions_path:
        cq_runner = CompetencyQuestionRunner(pipeline_config.competency_questions_path)
        cq_results = cq_runner.run(data_graph)
        passed = sum(1 for result in cq_results if result.success)
        total = len(cq_results)
        cq_payload = {
            "pass_rate": (passed / total) if total else 0.0,
            "passed": passed,
            "total": total,
            "results": [
                {"query": result.query, "success": result.success, "message": result.message}
                for result in cq_results
            ],
        }
        (output_root / "cq_results_iter0.json").write_text(
            json.dumps(cq_payload, indent=2), encoding="utf-8"
        )

    print("E3 run complete. Key outputs written under", output_root)


if __name__ == "__main__":
    main()
