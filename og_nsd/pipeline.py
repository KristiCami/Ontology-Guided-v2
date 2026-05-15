"""High-level orchestration for the OG-NSD pipeline."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from .config import PipelineConfig
from .llm import HeuristicLLM, LLMClient, LLMResponse, OpenAILLM
from .ontology import OntologyAssembler, load_schema_context
from .queries import CompetencyQuestionRunner
from .reasoning import OwlreadyReasoner
from .reporting import build_report, save_report
from .requirements import RequirementLoader, chunk_requirements, load_split_ids
from .shacl import ShaclValidator


class OntologyDraftingPipeline:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.config.ensure_output_dirs()
        self.schema_context = self._load_schema_context(config)
        default_prefixes = self.schema_context.prefixes if self.schema_context else None
        base_path = None if config.use_ontology_context else config.base_ontology_path
        self.assembler = OntologyAssembler(
            base_path, base_namespace=config.base_namespace, default_prefixes=default_prefixes
        )
        self.validator = ShaclValidator(config.shapes_path) if config.shapes_path else None
        self.reasoner = OwlreadyReasoner(enabled=config.reasoning_enabled)
        self.cq_runner: Optional[CompetencyQuestionRunner] = None
        if config.competency_questions_path:
            self.cq_runner = CompetencyQuestionRunner(config.competency_questions_path)
        self.llm = self._select_llm(config)
        self.last_llm_response: Optional[LLMResponse] = None
        self.last_shacl_report = None
        self.last_reasoner_report = None
        self.last_cq_results = None
        self.state_graph = None
        self.reasoned_graph = None

    def _select_llm(self, config: PipelineConfig) -> LLMClient:
        if config.llm_mode == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                try:
                    return OpenAILLM(temperature=config.llm_temperature, seed=config.llm_seed)
                except RuntimeError:
                    logging.warning(
                        "openai package missing; falling back to heuristic LLM for offline execution"
                    )
                    return HeuristicLLM(base_namespace=config.base_namespace)
            logging.warning(
                "OPENAI_API_KEY not set; falling back to heuristic LLM for offline execution"
            )
            return HeuristicLLM(base_namespace=config.base_namespace)
        return HeuristicLLM(base_namespace=config.base_namespace)

    def run(self) -> dict:
        dev_ids = load_split_ids(self.config.dev_split_path)
        test_ids = load_split_ids(self.config.test_split_path)
        loader = RequirementLoader(self.config.requirements_path, dev_ids=dev_ids, test_ids=test_ids)
        requirements = loader.load(self.config.max_requirements)
        exemplar_pool = (
            [req for req in requirements if req.split == "dev"][:6] if dev_ids else None
        )
        state = self.assembler.bootstrap()
        llm_response: Optional[LLMResponse] = None
        for batch in chunk_requirements(requirements, size=5):
            llm_response = self.llm.generate_axioms(
                batch, schema_context=self.schema_context, exemplars=exemplar_pool
            )
            self.assembler.add_turtle(state, llm_response.turtle)
        if llm_response is None:
            raise RuntimeError("LLM returned no axioms")
        self.last_llm_response = llm_response

        if self.config.draft_only:
            report = {
                "mode": "draft_only",
                "triples": len(state.graph),
                "llm_notes": llm_response.reasoning_notes,
                "token_usage": llm_response.token_usage,
            }
            self.assembler.serialize(state, self.config.output_path)
            if self.config.report_path:
                save_report(report, self.config.report_path)
            return report

        iteration_reports = []
        patch_notes: list[str] = []
        if self.validator is None:
            raise RuntimeError("SHACL validator not configured; provide --shapes or use --draft-only.")
        for iteration in range(self.config.max_iterations + 1):
            reasoner_result = self.reasoner.run(state.graph)
            reasoner_report = reasoner_result.report
            shacl_input_graph = reasoner_result.expanded_graph
            shacl_report = self.validator.validate(shacl_input_graph)
            cq_results = self.cq_runner.run(shacl_input_graph) if self.cq_runner else None
            iteration_reports.append(
                {
                    "iteration": iteration,
                    "conforms": shacl_report.conforms,
                    "shacl": shacl_report,
                    "reasoner": reasoner_report,
                    "cq_results": cq_results,
                }
            )

            if shacl_report.conforms or iteration == self.config.max_iterations:
                break

            prompts = self._synthesize_repair_prompts(shacl_report)
            context_ttl = state.graph.serialize(format="turtle")
            patch_response = self.llm.generate_patch(prompts, context_ttl)
            patch_notes.append(patch_response.reasoning_notes)
            if patch_response.turtle.strip():
                self.assembler.add_turtle(state, patch_response.turtle)

        report = build_report(
            llm_response=llm_response,
            shacl_report=iteration_reports[-1]["shacl"],
            cq_results=iteration_reports[-1]["cq_results"],
            reasoner_report=iteration_reports[-1]["reasoner"],
            iterations=iteration_reports,
            patch_notes=patch_notes,
            unmatched_split_ids=sorted(loader.unmatched_split_ids),
        )
        self.assembler.serialize(state, self.config.output_path)
        self.state_graph = state.graph
        self.reasoned_graph = shacl_input_graph if "shacl_input_graph" in locals() else None
        self.last_shacl_report = iteration_reports[-1]["shacl"]
        self.last_reasoner_report = iteration_reports[-1]["reasoner"]
        self.last_cq_results = iteration_reports[-1]["cq_results"]
        self.last_llm_response = llm_response
        if self.config.report_path:
            save_report(report, self.config.report_path)
        return report

    def _synthesize_repair_prompts(self, shacl_report) -> list[str]:
        prompts: list[str] = []
        for result in shacl_report.results:
            parts = []
            if result.message:
                parts.append(result.message)
            if result.path:
                parts.append(f"path={result.path}")
            if result.focus_node:
                parts.append(f"focus={result.focus_node}")
            prompts.append(" | ".join(parts))
        if not prompts and shacl_report.text_report:
            prompts.append(shacl_report.text_report.splitlines()[0])
        return prompts

    def _load_schema_context(self, config: PipelineConfig):
        if not config.use_ontology_context:
            return None

        grounding_path = config.grounding_ontology_path or config.base_ontology_path
        if grounding_path is None:
            raise ValueError(
                "Ontology-aware prompting requested but no grounding ontology was provided. "
                "Pass --ontology-context or --base to supply a TTL for schema extraction."
            )
        return load_schema_context(grounding_path, config.base_namespace)
