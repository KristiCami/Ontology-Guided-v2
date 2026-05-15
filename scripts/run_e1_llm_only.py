#!/usr/bin/env python3
"""Run the E1 LLM-only baseline (no SHACL/Reasoner, no repair loop)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

from rdflib import Graph, URIRef

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from og_nsd import OntologyDraftingPipeline, PipelineConfig  # noqa: E402
from og_nsd.metrics import compute_exact_metrics, compute_semantic_metrics  # noqa: E402
from og_nsd.queries import CompetencyQuestionRunner  # noqa: E402


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the E1 LLM-only experiment")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "configs/e1_llm_only_atm.json")
    parser.add_argument("--output-root", type=Path, default=None, help="Override output root.")
    parser.add_argument("--temperature", type=float, default=None, help="Override LLM temperature.")
    parser.add_argument("--seed", type=int, default=None, help="Seed tag for reproducibility metadata.")
    parser.add_argument(
        "--prompt-mode",
        choices=["raw", "ontology_aware"],
        default=None,
        help="Prompt mode override for baseline comparison runs.",
    )
    return parser.parse_args()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


_STANDARD_NAMESPACES = (
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "http://www.w3.org/2000/01/rdf-schema#",
    "http://www.w3.org/2002/07/owl#",
    "http://www.w3.org/2001/XMLSchema#",
)


def _normalize_base_ns(base_namespace: str | None) -> str:
    if not base_namespace:
        return ""
    base_ns = base_namespace.rstrip("#/")
    return f"{base_ns}#"


def _qname(graph: Graph, term) -> str:
    try:
        return graph.namespace_manager.normalizeUri(term)
    except Exception:
        return str(term)


def collect_drift_samples(graph: Graph, base_namespace: str | None, limit: int = 10) -> List[str]:
    base_ns = _normalize_base_ns(base_namespace)
    samples: List[str] = []
    for subj, pred, obj in graph:
        for term in (subj, pred, obj):
            if not isinstance(term, URIRef):
                continue
            iri = str(term)
            if (base_ns and iri.startswith(base_ns)) or iri.startswith(_STANDARD_NAMESPACES):
                continue
            qname = _qname(graph, term)
            if qname not in samples:
                samples.append(qname)
            if len(samples) >= limit:
                return samples
    return samples


def collect_redundant_axioms(graph: Graph, limit: int = 10) -> List[str]:
    occurrences = {}
    redundant_samples: List[str] = []
    for subj, pred, obj in graph:
        if isinstance(pred, URIRef) and str(pred).endswith("sourceRequirement"):
            occurrences.setdefault(str(obj), []).append(subj)
    for req_id, subjects in occurrences.items():
        if len(subjects) < 2:
            continue
        for subj in subjects:
            redundant_samples.append(f"{_qname(graph, subj)} repeats sourceRequirement {req_id}")
            if len(redundant_samples) >= limit:
                return redundant_samples
    return redundant_samples


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    output_root = PROJECT_ROOT / cfg.get("output_root", "runs/E1_llm_only")
    if args.output_root is not None:
        output_root = args.output_root
    ensure_dir(output_root)
    prompt_mode = args.prompt_mode or cfg.get("prompt_mode", "raw")
    use_ontology_context = cfg.get("use_ontology_context", False)
    if prompt_mode == "ontology_aware":
        use_ontology_context = True

    pipeline_config = PipelineConfig(
        requirements_path=PROJECT_ROOT / cfg["requirements_path"],
        shapes_path=None,
        base_ontology_path=None,
        competency_questions_path=PROJECT_ROOT / cfg.get("competency_questions")
        if cfg.get("competency_questions")
        else None,
        output_path=output_root / "pred.ttl",
        report_path=output_root / "run_report.json",
        llm_mode=cfg.get("llm_mode", "heuristic"),
        max_requirements=cfg.get("max_requirements", 20),
        reasoning_enabled=False,
        max_iterations=0,
        draft_only=True,
        use_ontology_context=use_ontology_context,
        grounding_ontology_path=PROJECT_ROOT / cfg["ontology_path"] if cfg.get("ontology_path") else None,
        base_namespace=cfg.get("base_namespace", "http://lod.csd.auth.gr/atm/atm.ttl#"),
        llm_temperature=args.temperature if args.temperature is not None else cfg.get("temperature", 0.1),
        llm_seed=args.seed,
    )

    pipeline = OntologyDraftingPipeline(pipeline_config)
    pipeline.run()
    run_report_path = pipeline_config.report_path or output_root / "run_report.json"

    pred_graph = Graph().parse(pipeline_config.output_path)
    gold_path = PROJECT_ROOT / cfg.get("ontology_path", "data/domains/atm/atm_gold.ttl")

    (output_root / "metrics_exact.json").write_text(
        json.dumps(compute_exact_metrics(pipeline_config.output_path, gold_path), indent=2),
        encoding="utf-8",
    )
    (output_root / "metrics_semantic.json").write_text(
        json.dumps(compute_semantic_metrics(pred_graph, Graph().parse(gold_path)), indent=2),
        encoding="utf-8",
    )

    if pipeline_config.competency_questions_path:
        cq_runner = CompetencyQuestionRunner(pipeline_config.competency_questions_path)
        cq_results = cq_runner.run(pred_graph)
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
        (output_root / "cq_results.json").write_text(json.dumps(cq_payload, indent=2), encoding="utf-8")

    run_report = json.loads(Path(run_report_path).read_text(encoding="utf-8")) if run_report_path else {}
    if pipeline.last_llm_response and pipeline.last_llm_response.token_usage:
        run_report["token_usage"] = pipeline.last_llm_response.token_usage
    run_report["drift_axioms_sample"] = collect_drift_samples(
        pred_graph, pipeline_config.base_namespace
    )
    run_report["redundant_axioms_sample"] = collect_redundant_axioms(pred_graph)
    run_report["experiment_metadata"] = {
        "seed": args.seed,
        "temperature": pipeline_config.llm_temperature,
        "prompt_mode": prompt_mode,
        "use_ontology_context": pipeline_config.use_ontology_context,
    }
    if run_report_path:
        Path(run_report_path).write_text(json.dumps(run_report, indent=2), encoding="utf-8")

    print("E1 run complete. Key outputs written under", output_root)


if __name__ == "__main__":
    main()
