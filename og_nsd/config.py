"""Configuration helpers for the OG-NSD pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class PipelineConfig:
    """Runtime configuration for :class:`OntologyDraftingPipeline`."""

    requirements_path: Path
    shapes_path: Optional[Path]
    base_ontology_path: Optional[Path]
    competency_questions_path: Optional[Path]
    output_path: Path
    report_path: Optional[Path] = None
    llm_mode: str = "heuristic"
    base_namespace: str = "http://lod.csd.auth.gr/atm/atm.ttl#"
    max_iterations: int = 2
    max_requirements: Optional[int] = 20
    include_boilerplate_context: bool = True
    llm_temperature: float = 0.1
    prompt_template_path: Optional[Path] = None
    reasoning_enabled: bool = False
    save_intermediate: bool = True
    intermediate_dir: Path = field(default_factory=lambda: Path("build"))
    draft_only: bool = False
    use_ontology_context: bool = False
    grounding_ontology_path: Optional[Path] = None
    dev_split_path: Optional[Path] = None
    test_split_path: Optional[Path] = None
    llm_seed: Optional[int] = None

    def ensure_output_dirs(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        if self.report_path is not None:
            self.report_path.parent.mkdir(parents=True, exist_ok=True)
        if self.save_intermediate:
            self.intermediate_dir.mkdir(parents=True, exist_ok=True)
