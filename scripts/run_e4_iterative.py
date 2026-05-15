"""Run the E4 iterative repair loop as described in the protocol."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from rdflib import Graph
from rdflib.namespace import OWL, RDF

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from og_nsd import OntologyAssembler, load_schema_context  # noqa: E402
from og_nsd.error_taxonomy import compute_iteration_taxonomy  # noqa: E402
from og_nsd.llm import HeuristicLLM, OpenAILLM  # noqa: E402
from og_nsd.reasoning import OwlreadyReasoner  # noqa: E402
from og_nsd.repair import (  # noqa: E402
    StopDecision,
    cq_results_to_patches,
    final_metrics,
    save_patch_plan,
    save_shacl_report,
    shacl_report_to_patches,
    should_stop,
)
from og_nsd.requirements import RequirementLoader, chunk_requirements  # noqa: E402
from og_nsd.shacl import ShaclValidator, summarize_shacl_report  # noqa: E402
from og_nsd.queries import CompetencyQuestionRunner  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the E4 iterative repair experiment")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "configs/e4_iterative_repair_atm.json")
    parser.add_argument("--cq-threshold", type=float, default=0.8)
    parser.add_argument(
        "--stop-policies",
        type=str,
        default=None,
        help=(
            "Comma-separated list of stop policies to sweep. "
            "Supported: default,hard_and_cq,ignore_no_hard,max_only. "
            "Defaults to config stop_policies (or stop_policy) when omitted."
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Override output root (defaults to config). When multiple stop policies are provided, each run is stored in a subfolder.",
    )
    parser.add_argument(
        "--kmax",
        type=int,
        default=None,  # kept for backwards compatibility; validated later.
        help="Deprecated; iterations are controlled via config. Do not set.",
    )
    parser.add_argument(
        "--min-patch-iterations",
        type=int,
        default=None,
        help="Require at least this many iterations that produced patches before stopping (unless max iterations hit).",
    )
    parser.add_argument(
        "--use-soft-violations",
        dest="use_soft_violations",
        action="store_true",
        help="Convert soft/warning SHACL results into patches when no hard violations are present.",
    )
    parser.add_argument(
        "--ignore-soft-violations",
        dest="use_soft_violations",
        action="store_false",
        help="Skip soft/warning SHACL results when generating patches.",
    )
    parser.add_argument(
        "--feedback-variant",
        choices=["raw", "typed", "typed_priority"],
        default=None,
        help="Feedback channel for repair prompts (raw text or typed patches).",
    )
    parser.add_argument(
        "--stability-variant",
        choices=["none", "sa1", "sa2", "sa3", "sa4", "sa5"],
        default=None,
        help="Stability-aware control variant for repair stopping/filtering.",
    )
    parser.add_argument(
        "--no-gain-patience",
        type=int,
        default=None,
        help="Stop after this many iterations without CQ gain (SA-1).",
    )
    parser.add_argument(
        "--max-growth-ratio",
        type=float,
        default=None,
        help="Stop or cap when graph growth ratio exceeds threshold (SA-2).",
    )
    parser.add_argument(
        "--max-patches-per-iter",
        type=int,
        default=None,
        help="Repair budget: max patches applied per iteration.",
    )
    parser.add_argument(
        "--max-new-triples-per-iter",
        type=int,
        default=None,
        help="Repair budget: stop if per-iteration triple delta exceeds limit.",
    )
    parser.add_argument(
        "--local-repair-only",
        dest="local_repair_only",
        action="store_true",
        help="Restrict patches to local/base namespace resources.",
    )
    parser.add_argument(
        "--allow-global-repair",
        dest="local_repair_only",
        action="store_false",
        help="Allow broad/global repair patches.",
    )
    parser.add_argument(
        "--ablation-profile",
        choices=[
            "none",
            "no_shacl",
            "no_reasoning",
            "no_cq",
            "no_ontology_context",
            "no_exemplars",
            "no_growth_control",
        ],
        default="none",
        help="Apply predefined ablation overrides.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed tag for reproducibility metadata; forwarded to OpenAI 'seed' when supported.",
    )
    parser.set_defaults(use_soft_violations=None)
    parser.set_defaults(local_repair_only=None)
    return parser.parse_args()


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def select_llm(cfg: dict, base_namespace: str, seed: int | None = None):
    mode = cfg.get("llm_mode", "heuristic")
    temperature = cfg.get("temperature", 0.2)
    if mode == "openai":
        try:
            return OpenAILLM(temperature=temperature, seed=seed)
        except RuntimeError:
            return HeuristicLLM(base_namespace)
    return HeuristicLLM(base_namespace)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _count_patch_types(patches):
    counts = {}
    for patch in patches:
        action = patch.action if hasattr(patch, "action") else patch.get("action")
        if action is None:
            continue
        counts[action] = counts.get(action, 0) + 1
    return counts


def _accumulate_token_usage(target: dict[str, int], src: dict[str, int] | None) -> None:
    """Sum integer fields of ``src`` into ``target`` in place.

    Mirrors the schema produced by ``og_nsd.llm._extract_token_usage`` so that
    ``run_report.json`` stays compatible with the E1 baseline reader in
    ``scripts/build_journal_tables.py``.
    """

    if not src:
        return
    for key, value in src.items():
        if isinstance(value, int):
            target[key] = target.get(key, 0) + value


def _normalize_stop_policies(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        items = raw.split(",")
    else:
        items = raw
    return [str(item).strip() for item in items if str(item).strip()]


def _apply_ablation_profile(cfg: dict[str, Any], profile: str) -> dict[str, Any]:
    updated = dict(cfg)
    if profile == "none":
        return updated
    if profile == "no_shacl":
        updated["validation"] = False
    elif profile == "no_reasoning":
        updated["reasoning"] = False
    elif profile == "no_cq":
        updated["competency_questions"] = None
    elif profile == "no_ontology_context":
        updated["use_ontology_context"] = False
        updated["prompt_mode"] = "baseline"
    elif profile == "no_exemplars":
        updated["use_exemplars"] = False
    elif profile == "no_growth_control":
        updated["stability_variant"] = "none"
    return updated


def _is_local_term(value: str, base_ns: str) -> bool:
    if value.startswith("http"):
        return value.startswith(base_ns.rstrip("#/"))
    return value.startswith("atm:")


def _filter_and_rank_patches(
    patches: list,
    *,
    feedback_variant: str,
    local_repair_only: bool,
    base_ns: str,
    max_patches_per_iter: int,
    hard_priority_only: bool,
) -> list:
    filtered = list(patches)
    if local_repair_only:
        filtered = [
            patch
            for patch in filtered
            if _is_local_term(getattr(patch, "subject", "") or "", base_ns)
            and _is_local_term(getattr(patch, "object", "") or "", base_ns)
        ]
    if hard_priority_only:
        filtered = [
            patch
            for patch in filtered
            if str(getattr(patch, "severity", "")).lower() in {"violation", "cq"}
        ]
    if feedback_variant == "typed_priority":
        def _priority(patch) -> tuple[int, str]:
            severity = str(getattr(patch, "severity", "")).lower()
            if severity == "violation":
                level = 0
            elif severity == "cq":
                level = 1
            else:
                level = 2
            return (level, getattr(patch, "predicate", ""))

        filtered = sorted(filtered, key=_priority)
    if max_patches_per_iter > 0:
        filtered = filtered[:max_patches_per_iter]
    return filtered


def _extract_vocab(graph: Graph) -> dict[str, set[str]]:
    classes: set[str] = set()
    properties: set[str] = set()
    for subject, _, obj in graph.triples((None, RDF.type, None)):
        if str(obj) == str(OWL.Class):
            classes.add(str(subject))
        elif str(obj) in {str(OWL.ObjectProperty), str(OWL.DatatypeProperty)}:
            properties.add(str(subject))
    return {"classes": classes, "properties": properties}


def _save_iteration_log(
    iter_dir: Path,
    iteration: int,
    shacl_summary: dict,
    cq_payload: dict,
    patches: list,
    patch_sources: list[str],
    patch_iteration_count: int,
    reasoning_result,
    triples_before_reasoning: int,
    stop_decision: StopDecision,
    diagnostics: dict[str, Any],
) -> dict:
    payload = {
        "iteration": iteration,
        "shacl": shacl_summary,
        "cq": {
            "pass_rate": cq_payload.get("pass_rate", 0.0),
            "failed": len([r for r in cq_payload.get("results", []) if not r.get("success", False)]),
            "failed_queries": [r.get("query") for r in cq_payload.get("results", []) if not r.get("success", False)],
            "results": cq_payload.get("results", []),
        },
        "patches": {
            "count": len(patches),
            "types": {k: v for k, v in _count_patch_types(patches).items() if v > 0},
            "sources": sorted(set(patch_sources)),
            "iterations_with_patches": patch_iteration_count,
        },
        "reasoning": {
            "enabled": reasoning_result.report.enabled,
            "consistent": reasoning_result.report.consistent,
            "unsat_classes": len(reasoning_result.report.unsatisfiable_classes),
            "notes": reasoning_result.report.notes,
            "backend": reasoning_result.report.backend,
            "triples_before_reasoning": triples_before_reasoning,
            "triples_after_reasoning": len(reasoning_result.expanded_graph),
        },
        "stop": {"decision": stop_decision.stop, "reason": stop_decision.reason},
        "stop_reason": stop_decision.reason,
        "diagnostics": diagnostics,
    }
    (iter_dir / "iteration_log.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    args = parse_args()
    cfg = _apply_ablation_profile(load_config(args.config), args.ablation_profile)
    base_ns = cfg.get("base_namespace", "http://lod.csd.auth.gr/atm/atm.ttl#")

    cli_stop_policies = _normalize_stop_policies(args.stop_policies)
    config_stop_policies = _normalize_stop_policies(cfg.get("stop_policies") or cfg.get("stop_policy"))
    stop_policies = cli_stop_policies or config_stop_policies or ["hard_and_cq"]

    output_root_base = PROJECT_ROOT / cfg.get("output_root", "runs/E4_full")
    if args.output_root:
        output_root_base = args.output_root
    ensure_dir(output_root_base)

    iterations_cfg = cfg.get("iterations")
    if iterations_cfg is None:
        raise ValueError("Config must define 'iterations' as the single source of truth for loop count.")
    if iterations_cfg <= 0:
        raise ValueError("Config field 'iterations' must be a positive integer.")
    if args.kmax is not None:
        raise ValueError("--kmax is deprecated; configure iterations exclusively via the config file.")

    min_patch_iterations = args.min_patch_iterations
    if min_patch_iterations is None:
        min_patch_iterations = cfg.get("min_patch_iterations", 2)
    if min_patch_iterations <= 0:
        raise ValueError("min_patch_iterations must be a positive integer.")

    use_soft_violations = cfg.get("use_soft_violations", True)
    if args.use_soft_violations is not None:
        use_soft_violations = args.use_soft_violations
    feedback_variant = args.feedback_variant or cfg.get("feedback_variant", "typed")
    stability_variant = args.stability_variant or cfg.get("stability_variant", "none")
    no_gain_patience = args.no_gain_patience or cfg.get("no_gain_patience", 2)
    max_growth_ratio = args.max_growth_ratio or cfg.get("max_growth_ratio", 1.8)
    max_patches_per_iter = args.max_patches_per_iter or cfg.get("max_patches_per_iter", 20)
    max_new_triples_per_iter = args.max_new_triples_per_iter or cfg.get("max_new_triples_per_iter", 400)
    local_repair_only = cfg.get("local_repair_only", False)
    if args.local_repair_only is not None:
        local_repair_only = args.local_repair_only
    if stability_variant in {"sa4", "sa5"}:
        local_repair_only = True

    prompt_mode = cfg.get("prompt_mode", "ontology_aware")
    valid_modes = {"ontology_aware", "baseline"}
    if prompt_mode not in valid_modes:
        raise ValueError(f"Unsupported prompt_mode '{prompt_mode}'. Choose from {sorted(valid_modes)}.")

    requirement_loader = RequirementLoader(PROJECT_ROOT / cfg["requirements_path"])
    requirements = requirement_loader.load(cfg.get("max_requirements", 20))
    use_exemplars = cfg.get("use_exemplars", True)
    exemplar_count = cfg.get("exemplar_count", 4)
    exemplar_pool = requirements[:exemplar_count] if use_exemplars else None

    ontology_context_path = None
    if cfg.get("use_ontology_context", True) and prompt_mode != "baseline":
        ontology_context_path = cfg.get("ontology_context_path") or cfg.get("ontology_path")
        if ontology_context_path is None:
            raise ValueError("use_ontology_context=true requires ontology_context_path or ontology_path in config.")

    gold_path = PROJECT_ROOT / (cfg.get("gold_path") or cfg["ontology_path"])
    if ontology_context_path:
        context_resolved = (PROJECT_ROOT / ontology_context_path).resolve()
        gold_resolved = gold_path.resolve()
        if context_resolved == gold_resolved:
            raise ValueError(
                "ontology_context_path must differ from gold_path to avoid schema leakage between grounding and gold."
            )

    schema_context = load_schema_context(PROJECT_ROOT / ontology_context_path, base_ns) if ontology_context_path else None

    assembler = OntologyAssembler(
        base_namespace=base_ns,
        default_prefixes=schema_context.prefixes if schema_context else None,
    )
    validator = ShaclValidator(PROJECT_ROOT / cfg["shapes_path"]) if cfg.get("validation", True) else None
    reasoner = OwlreadyReasoner(enabled=cfg.get("reasoning", True))
    cq_runner = None
    if cfg.get("competency_questions"):
        cq_runner = CompetencyQuestionRunner(PROJECT_ROOT / cfg["competency_questions"])

    llm = select_llm(cfg, base_ns, seed=args.seed)

    def run_single(policy: str, output_root: Path) -> None:
        state = assembler.bootstrap()
        iter_dir = output_root / "iter0"
        ensure_dir(iter_dir)

        total_token_usage: dict[str, int] = {}
        pending_iter_tokens: dict[str, int] = {}
        draft_token_usage: dict[str, int] = {}

        chunk_size = cfg.get("requirements_chunk_size", 5)
        for batch in chunk_requirements(requirements, size=chunk_size):
            response = llm.generate_axioms(batch, schema_context=schema_context, exemplars=exemplar_pool)
            _accumulate_token_usage(total_token_usage, response.token_usage)
            _accumulate_token_usage(pending_iter_tokens, response.token_usage)
            _accumulate_token_usage(draft_token_usage, response.token_usage)
            try:
                assembler.add_turtle(state, response.turtle)
            except ValueError as exc:
                (iter_dir / "llm_error.txt").write_text(
                    "Draft generation failed to parse LLM Turtle.\n"
                    f"Reason: {exc}\n\nRaw turtle:\n{response.turtle}",
                    encoding="utf-8",
                )
                (output_root / "run_report.json").write_text(
                    json.dumps(
                        {
                            "token_usage": total_token_usage or None,
                            "draft_token_usage": draft_token_usage or None,
                            "experiment_metadata": {
                                "seed": args.seed,
                                "stop_policy": policy,
                                "stability_variant": stability_variant,
                                "feedback_variant": feedback_variant,
                                "ablation_profile": args.ablation_profile,
                            },
                            "stop_reason": "draft_parse_error",
                            "iterations_executed": 0,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                repair_log: dict = {
                    "config": {
                        "path": str(args.config),
                        "iterations": iterations_cfg,
                        "min_patch_iterations": min_patch_iterations,
                        "requirements_chunk_size": cfg.get("requirements_chunk_size", 5),
                        "use_ontology_context": bool(ontology_context_path),
                        "ontology_context_path": str(ontology_context_path) if ontology_context_path else None,
                        "gold_path": str(gold_path),
                        "prompt_mode": prompt_mode,
                        "validation": cfg.get("validation", True),
                        "reasoning": cfg.get("reasoning", True),
                        "stop_policy": policy,
                        "use_soft_violations": use_soft_violations,
                        "feedback_variant": feedback_variant,
                        "stability_variant": stability_variant,
                        "ablation_profile": args.ablation_profile,
                    },
                    "iterations": {},
                    "stop": {"iteration": 0, "reason": "draft_parse_error", "error": str(exc)},
                }
                (output_root / "repair_log.json").write_text(json.dumps(repair_log, indent=2), encoding="utf-8")
                print(f"[{policy}] Aborted at draft due to Turtle parse error. See {iter_dir / 'llm_error.txt'}")
                return

        assembler.serialize(state, iter_dir / "pred.ttl")

        repair_log: dict = {
            "config": {
                "path": str(args.config),
                "iterations": iterations_cfg,
                "min_patch_iterations": min_patch_iterations,
                "requirements_chunk_size": cfg.get("requirements_chunk_size", 5),
                "use_ontology_context": bool(ontology_context_path),
                "ontology_context_path": str(ontology_context_path) if ontology_context_path else None,
                "gold_path": str(gold_path),
                "prompt_mode": prompt_mode,
                "validation": cfg.get("validation", True),
                "reasoning": cfg.get("reasoning", True),
                "stop_policy": policy,
                "use_soft_violations": use_soft_violations,
                "feedback_variant": feedback_variant,
                "stability_variant": stability_variant,
                "ablation_profile": args.ablation_profile,
            },
            "iterations": {},
        }
        previous_patches = None
        current_iter = 0
        cq_pass_rate = 0.0
        patch_iterations = 0
        previous_cq_pass_rate: float | None = None
        no_gain_streak = 0
        prev_reasoned_triples: int | None = None
        previous_asserted_triples: set[tuple[str, str, str]] | None = None
        previous_vocab = {"classes": set(), "properties": set()}
        diagnostics_rows: list[dict[str, Any]] = []
        prev_hard_violations: int | None = None

        while True:
            triples_before_reasoning = len(state.graph)
            reasoning_result = reasoner.run(state.graph)
            patch_sources: list[str] = []

            def _patch_key(patch) -> tuple[str | None, str | None, str | None]:
                if hasattr(patch, "subject"):
                    return (patch.subject, patch.predicate, patch.object)
                if isinstance(patch, dict):
                    return (patch.get("subject"), patch.get("predicate"), patch.get("object"))
                return (None, None, None)

            if cfg.get("validation", True):
                if validator is None:
                    raise RuntimeError("Validation enabled but SHACL validator is not configured.")
                shacl_report = validator.validate(reasoning_result.expanded_graph)
                summary = summarize_shacl_report(shacl_report)
                save_shacl_report(shacl_report, iter_dir / "shacl_report.ttl")
                patches = shacl_report_to_patches(
                    shacl_report, include_soft_if_no_hard=bool(use_soft_violations)
                )
                if patches:
                    patch_sources.append("shacl")
            else:
                shacl_report = None
                summary = {"total": 0, "violations": {"hard": 0, "soft": 0}}
                patches = []
                (iter_dir / "shacl_report.ttl").write_text("Validation disabled for this run.\n", encoding="utf-8")

            cq_results = cq_runner.run(reasoning_result.expanded_graph) if cq_runner else []
            cq_pass_rate = (sum(1 for res in cq_results if res.success) / len(cq_results)) if cq_results else 0.0
            cq_patches = cq_results_to_patches(cq_results) if cq_results else []
            if cq_patches:
                patch_sources.append("competency_questions")
            if patches:
                existing = {_patch_key(p) for p in patches}
                for patch in cq_patches:
                    key = _patch_key(patch)
                    if key not in existing:
                        patches.append(patch)
                        existing.add(key)
            else:
                patches = cq_patches

            hard_priority_only = stability_variant in {"sa3", "sa5"}
            patches = _filter_and_rank_patches(
                patches,
                feedback_variant=feedback_variant,
                local_repair_only=bool(local_repair_only),
                base_ns=base_ns,
                max_patches_per_iter=max_patches_per_iter,
                hard_priority_only=hard_priority_only,
            )

            save_patch_plan(patches, iter_dir / "patches.json")

            cq_payload = {
                "pass_rate": cq_pass_rate,
                "results": [
                    {"query": result.query, "success": result.success, "message": result.message}
                    for result in cq_results
                ],
            }
            (iter_dir / "cq_results.json").write_text(json.dumps(cq_payload, indent=2), encoding="utf-8")

            if patches:
                patch_iterations += 1

            if previous_cq_pass_rate is None:
                no_gain_streak = 0
            elif cq_pass_rate > previous_cq_pass_rate:
                no_gain_streak = 0
            else:
                no_gain_streak += 1
            cq_gain = 0.0 if previous_cq_pass_rate is None else (cq_pass_rate - previous_cq_pass_rate)
            previous_cq_pass_rate = cq_pass_rate

            reasoned_triples = len(reasoning_result.expanded_graph)
            current_asserted_triples = {(str(s), str(p), str(o)) for s, p, o in state.graph}
            if prev_reasoned_triples is None:
                growth_ratio = 1.0
                new_triples = 0
            else:
                growth_ratio = reasoned_triples / max(prev_reasoned_triples, 1)
                new_triples = reasoned_triples - prev_reasoned_triples
            prev_reasoned_triples = reasoned_triples
            if previous_asserted_triples is None:
                changed_triples = 0
            else:
                changed_triples = len(current_asserted_triples.symmetric_difference(previous_asserted_triples))
            previous_asserted_triples = current_asserted_triples

            vocab = _extract_vocab(state.graph)
            new_classes = vocab["classes"] - previous_vocab["classes"]
            new_properties = vocab["properties"] - previous_vocab["properties"]
            previous_vocab = vocab

            if not cfg.get("validation", True):
                stop_decision = StopDecision(True, "validation_disabled")
            else:
                stop_decision = should_stop(
                    iteration=current_iter,
                    max_iterations=iterations_cfg,
                    patches=patches,
                    previous_patches=previous_patches,
                    shacl_report=shacl_report,
                    cq_pass_rate=cq_pass_rate,
                    cq_threshold=args.cq_threshold,
                    stop_policy=policy,
                )

            if stability_variant in {"sa1", "sa5"} and no_gain_streak >= no_gain_patience:
                stop_decision = StopDecision(True, "stability_stop_no_cq_gain")
            if stability_variant in {"sa2", "sa5"} and growth_ratio > max_growth_ratio:
                stop_decision = StopDecision(True, "stability_stop_growth_ratio")
            if max_new_triples_per_iter > 0 and new_triples > max_new_triples_per_iter:
                stop_decision = StopDecision(True, "budget_stop_new_triples")

            if stop_decision.stop and stop_decision.reason != "max_iterations_reached":
                if patches and patch_iterations < min_patch_iterations:
                    stop_decision = StopDecision(False, "min_patch_iterations_not_met")

            constraint_components: list[str] = []
            shacl_messages: list[str] = []
            if shacl_report:
                constraint_components = sorted(
                    {
                        str(result.constraint_component)
                        for result in shacl_report.results
                        if result.constraint_component
                    }
                )
                shacl_messages = [
                    str(result.message)
                    for result in shacl_report.results
                    if result.message
                ]
            local_patch_count = sum(
                1
                for patch in patches
                if _is_local_term(getattr(patch, "subject", "") or "", base_ns)
                and _is_local_term(getattr(patch, "object", "") or "", base_ns)
            )
            patch_locality = (local_patch_count / len(patches)) if patches else 0.0
            diagnostics = {
                "cq": {
                    "passed": sum(1 for res in cq_results if res.success),
                    "total": len(cq_results),
                    "new_gains": max(cq_gain, 0.0),
                    "lost_gains": abs(min(cq_gain, 0.0)),
                    "no_gain_streak": no_gain_streak,
                },
                "shacl": {
                    "hard": summary["violations"]["hard"],
                    "soft": summary["violations"]["soft"],
                    "violation_types": constraint_components,
                },
                "reasoning": {
                    "success": reasoning_result.report.consistent is not False,
                    "consistent": reasoning_result.report.consistent,
                    "unsat": len(reasoning_result.report.unsatisfiable_classes),
                    "exceptions": bool(
                        any(
                            token in (reasoning_result.report.notes or "").lower()
                            for token in ("failed", "exception", "nullpointer", "error")
                        )
                    ),
                    "notes": reasoning_result.report.notes,
                },
                "graph": {
                    "asserted_triples": triples_before_reasoning,
                    "reasoned_triples": reasoned_triples,
                    "new_triples": new_triples,
                    "changed_triples": changed_triples,
                    "growth_ratio": growth_ratio,
                },
                "patch": {
                    "count": len(patches),
                    "changed_triples": changed_triples,
                    "locality_ratio": patch_locality,
                },
                "vocabulary": {
                    "new_classes_count": len(new_classes),
                    "new_properties_count": len(new_properties),
                    "new_classes_sample": sorted(list(new_classes))[:20],
                    "new_properties_sample": sorted(list(new_properties))[:20],
                },
                "stability": {
                    "explosion_flag": growth_ratio > max_growth_ratio,
                    "oscillation_flag": cq_gain < 0,
                },
                "efficiency": {
                    "iteration_tokens": dict(pending_iter_tokens),
                    "cumulative_tokens": dict(total_token_usage),
                },
            }
            pending_iter_tokens = {}
            diagnostics["error_taxonomy"] = compute_iteration_taxonomy(
                schema_context=schema_context,
                base_ns=base_ns,
                new_classes=set(new_classes),
                new_properties=set(new_properties),
                growth_ratio=growth_ratio,
                max_growth_ratio=max_growth_ratio,
                reasoner_consistent=reasoning_result.report.consistent,
                reasoner_notes=reasoning_result.report.notes or "",
                no_gain_streak=no_gain_streak,
                no_gain_patience=no_gain_patience,
                patches_unchanged=(stop_decision.reason == "patches_unchanged"),
                hard_violations=int(summary["violations"]["hard"]),
                prev_hard_violations=prev_hard_violations,
                cq_gain=cq_gain,
                new_triples=new_triples,
                shacl_constraint_components=constraint_components,
                shacl_messages=shacl_messages,
                shacl_violation_total=int(summary["violations"]["hard"] + summary["violations"]["soft"]),
                patch_parse_error=False,
            )
            prev_hard_violations = int(summary["violations"]["hard"])

            iteration_log = _save_iteration_log(
                iter_dir=iter_dir,
                iteration=current_iter,
                shacl_summary=summary,
                cq_payload=cq_payload,
                patches=patches,
                patch_sources=patch_sources,
                patch_iteration_count=patch_iterations,
                reasoning_result=reasoning_result,
                triples_before_reasoning=triples_before_reasoning,
                stop_decision=stop_decision,
                diagnostics=diagnostics,
            )
            repair_log["iterations"][f"iter{current_iter}"] = iteration_log
            diagnostics_rows.append(
                {
                    "iteration": current_iter,
                    "cq_pass_rate": cq_pass_rate,
                    "growth_ratio": growth_ratio,
                    "new_triples": new_triples,
                    "changed_triples": changed_triples,
                    "hard_violations": summary["violations"]["hard"],
                    "soft_violations": summary["violations"]["soft"],
                    "patch_count": len(patches),
                    "patch_locality_ratio": patch_locality,
                    "new_classes_count": len(new_classes),
                    "new_properties_count": len(new_properties),
                    "no_gain_streak": no_gain_streak,
                    "stop_reason": stop_decision.reason,
                    "error_taxonomy": diagnostics["error_taxonomy"],
                    "iteration_tokens": diagnostics["efficiency"]["iteration_tokens"],
                    "cumulative_tokens": diagnostics["efficiency"]["cumulative_tokens"],
                }
            )

            if stop_decision.stop:
                break

            previous_patches = patches
            next_iter = current_iter + 1
            next_dir = output_root / f"iter{next_iter}"
            ensure_dir(next_dir)

            context_ttl = state.graph.serialize(format="turtle")
            if feedback_variant == "raw":
                prompt_lines = [p.message or f"{p.subject} {p.predicate} {p.object}" for p in patches]
                patch_response = llm.generate_patch(prompt_lines, context_ttl)
            else:
                patch_response = llm.apply_patches([p.to_dict() for p in patches], context_ttl)
            _accumulate_token_usage(total_token_usage, patch_response.token_usage)
            _accumulate_token_usage(pending_iter_tokens, patch_response.token_usage)

            next_state = assembler.bootstrap()
            assembler.add_turtle(next_state, context_ttl)
            try:
                assembler.add_turtle(next_state, patch_response.turtle)
            except ValueError as exc:
                (next_dir / "llm_error.txt").write_text(
                    "Patch application failed to parse LLM Turtle.\n"
                    f"Reason: {exc}\n\nRaw turtle:\n{patch_response.turtle}",
                    encoding="utf-8",
                )
                fallback_notes = ["llm_patch_parse_error"]
                try:
                    fallback_llm = HeuristicLLM(base_ns)
                    fallback_response = fallback_llm.apply_patches([p.to_dict() for p in patches], context_ttl)
                    _accumulate_token_usage(total_token_usage, fallback_response.token_usage)
                    _accumulate_token_usage(pending_iter_tokens, fallback_response.token_usage)
                    assembler.add_turtle(next_state, fallback_response.turtle)
                    fallback_notes.append("fallback_heuristic_patch_applied")
                    (next_dir / "fallback_patch.ttl").write_text(fallback_response.turtle, encoding="utf-8")
                except Exception as fallback_exc:  # pragma: no cover - defensive guard
                    fallback_notes.append(f"fallback_failed: {fallback_exc}")
                    (next_dir / "patch_application_notes.txt").write_text(
                        "\n".join(fallback_notes), encoding="utf-8"
                    )
                    stop_decision = StopDecision(True, "patch_parse_error")
                    assembler.serialize(state, next_dir / "pred.ttl")
                    (next_dir / "shacl_report.ttl").write_text(
                        "Patch parse error; SHACL not executed.\n", encoding="utf-8"
                    )
                    save_patch_plan([], next_dir / "patches.json")
                    (next_dir / "cq_results.json").write_text(
                        json.dumps({"pass_rate": 0.0, "results": []}, indent=2), encoding="utf-8"
                    )
                    stub_reasoning = SimpleNamespace(
                        report=SimpleNamespace(
                            enabled=False,
                            consistent=False,
                            unsatisfiable_classes=[],
                            notes="patch_parse_error",
                            backend=None,
                        ),
                        expanded_graph=state.graph,
                    )
                    iteration_log = _save_iteration_log(
                        iter_dir=next_dir,
                        iteration=next_iter,
                        shacl_summary={"total": 0, "violations": {"hard": 0, "soft": 0}},
                        cq_payload={"pass_rate": 0.0, "results": []},
                        patches=[],
                        patch_sources=[],
                        patch_iteration_count=patch_iterations,
                        reasoning_result=stub_reasoning,
                        triples_before_reasoning=len(state.graph),
                        stop_decision=stop_decision,
                        diagnostics={
                            "graph": {"asserted_triples": len(state.graph), "reasoned_triples": len(state.graph)},
                            "efficiency": {
                                "iteration_tokens": dict(pending_iter_tokens),
                                "cumulative_tokens": dict(total_token_usage),
                            },
                            "error_taxonomy": compute_iteration_taxonomy(
                                schema_context=schema_context,
                                base_ns=base_ns,
                                new_classes=set(),
                                new_properties=set(),
                                growth_ratio=1.0,
                                max_growth_ratio=max_growth_ratio,
                                reasoner_consistent=False,
                                reasoner_notes="patch_parse_error",
                                no_gain_streak=0,
                                no_gain_patience=no_gain_patience,
                                patches_unchanged=False,
                                hard_violations=0,
                                prev_hard_violations=None,
                                cq_gain=0.0,
                                new_triples=0,
                                shacl_constraint_components=[],
                                shacl_messages=[],
                                shacl_violation_total=0,
                                patch_parse_error=True,
                            ),
                        },
                    )
                    repair_log["iterations"][f"iter{next_iter}"] = iteration_log
                    repair_log["stop"] = {
                        "iteration": next_iter,
                        "reason": stop_decision.reason,
                        "error": str(fallback_exc),
                    }
                    repair_log["stop_reason"] = stop_decision.reason
                    (output_root / "repair_log.json").write_text(json.dumps(repair_log, indent=2), encoding="utf-8")
                    (output_root / "run_report.json").write_text(
                        json.dumps(
                            {
                                "token_usage": total_token_usage or None,
                                "draft_token_usage": draft_token_usage or None,
                                "experiment_metadata": {
                                    "seed": args.seed,
                                    "stop_policy": policy,
                                    "stability_variant": stability_variant,
                                    "feedback_variant": feedback_variant,
                                    "ablation_profile": args.ablation_profile,
                                },
                                "stop_reason": stop_decision.reason,
                                "iterations_executed": next_iter,
                            },
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                    print(
                        f"[{policy}] Aborted at iter{next_iter} due to Turtle parse error. "
                        f"See {(next_dir / 'llm_error.txt')}"
                    )
                    return
                else:
                    (next_dir / "patch_application_notes.txt").write_text(
                        "\n".join(fallback_notes), encoding="utf-8"
                    )
            state = next_state
            assembler.serialize(state, next_dir / "pred.ttl")

            iter_dir = next_dir
            current_iter = next_iter

        repair_log["stop"] = {"iteration": current_iter, "reason": stop_decision.reason}
        repair_log["stop_reason"] = stop_decision.reason

        final_dir = output_root / "final"
        ensure_dir(final_dir)
        assembler.serialize(state, final_dir / "pred.ttl")

        gold_graph = Graph().parse(gold_path)
        metrics_payload = final_metrics(reasoning_result.expanded_graph, gold_graph)
        (final_dir / "metrics_exact.json").write_text(json.dumps(metrics_payload["exact"], indent=2), encoding="utf-8")
        (final_dir / "metrics_semantic.json").write_text(json.dumps(metrics_payload["semantic"], indent=2), encoding="utf-8")

        validation_summary_path = final_dir / "validation_summary.json"
        validation_summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        if cq_runner:
            cq_payload = {
                "pass_rate": cq_pass_rate,
                "results": [
                    {"query": result.query, "success": result.success, "message": result.message}
                    for result in cq_results
                ],
            }
            (final_dir / "cq_results.json").write_text(json.dumps(cq_payload, indent=2), encoding="utf-8")

        (output_root / "repair_log.json").write_text(json.dumps(repair_log, indent=2), encoding="utf-8")
        (output_root / "diagnostics_summary.json").write_text(
            json.dumps(
                {
                    "feedback_variant": feedback_variant,
                    "stability_variant": stability_variant,
                    "ablation_profile": args.ablation_profile,
                    "total_token_usage": total_token_usage,
                    "draft_token_usage": draft_token_usage,
                    "rows": diagnostics_rows,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        run_report = {
            "token_usage": total_token_usage or None,
            "draft_token_usage": draft_token_usage or None,
            "experiment_metadata": {
                "seed": args.seed,
                "temperature": cfg.get("temperature"),
                "stop_policy": policy,
                "stability_variant": stability_variant,
                "feedback_variant": feedback_variant,
                "ablation_profile": args.ablation_profile,
                "use_ontology_context": bool(ontology_context_path),
                "prompt_mode": prompt_mode,
                "max_iterations": iterations_cfg,
                "min_patch_iterations": min_patch_iterations,
                "no_gain_patience": no_gain_patience,
                "max_growth_ratio": max_growth_ratio,
                "max_patches_per_iter": max_patches_per_iter,
                "max_new_triples_per_iter": max_new_triples_per_iter,
                "local_repair_only": bool(local_repair_only),
            },
            "stop_reason": repair_log.get("stop_reason"),
            "iterations_executed": current_iter,
        }
        (output_root / "run_report.json").write_text(json.dumps(run_report, indent=2), encoding="utf-8")

        print(f"[{policy}] E4 run complete. Outputs written to {output_root}")

    for policy in stop_policies:
        policy_output_root = output_root_base
        if len(stop_policies) > 1:
            policy_output_root = output_root_base / policy
        ensure_dir(policy_output_root)
        run_single(policy, policy_output_root)


if __name__ == "__main__":
    main()
