"""LLM integration utilities."""
from __future__ import annotations

import abc
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Sequence

from .ontology import SchemaContext
from .requirements import Requirement

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None  # type: ignore


def slugify(label: str) -> str:
    label = re.sub(r"[^A-Za-z0-9]+", "_", label.strip())
    label = re.sub(r"_+", "_", label).strip("_")
    if not label:
        label = "Concept"
    if label[0].isdigit():
        label = f"C_{label}"
    return label


@dataclass
class LLMResponse:
    turtle: str
    reasoning_notes: str
    token_usage: Dict[str, int] | None = None
    exemplar_ids: List[str] | None = None


class LLMClient(abc.ABC):
    """Abstract base class for LLM-backed ontology drafting."""

    @abc.abstractmethod
    def generate_axioms(
        self,
        requirements: Sequence[Requirement],
        schema_context: SchemaContext | None = None,
        exemplars: Sequence[Requirement] | None = None,
    ) -> LLMResponse:
        raise NotImplementedError

    @abc.abstractmethod
    def generate_patch(self, prompts: Sequence[str], context_ttl: str) -> LLMResponse:
        """Produce ontology edits that attempt to resolve validation feedback.

        Parameters
        ----------
        prompts:
            A sequence of human-readable violation summaries produced by the
            SHACL validator and/or DL reasoner.
        context_ttl:
            A Turtle serialization of the current ontology graph so the model
            can ground its edits.
        """
        raise NotImplementedError

    def apply_patches(self, patches: Sequence[dict], context_ttl: str) -> LLMResponse:
        """Apply structured patches to the provided ontology graph.

        Implementations may delegate to :meth:`generate_patch` or construct a
        new prompt that includes the JSON patch plan. The default implementation
        raises ``NotImplementedError`` so callers must explicitly handle LLM
        capabilities.
        """
        raise NotImplementedError


class HeuristicLLM(LLMClient):
    """Rule-based fallback model for offline experimentation."""

    def __init__(self, base_namespace: str) -> None:
        self.base_ns = base_namespace.rstrip("#/") + "#"

    def generate_axioms(
        self,
        requirements: Sequence[Requirement],
        schema_context: SchemaContext | None = None,
        exemplars: Sequence[Requirement] | None = None,
    ) -> LLMResponse:
        triples: List[str] = [
            f"@prefix atm: <{self.base_ns}> .",
            "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
            "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        ]
        notes: List[str] = []
        for req in requirements:
            subject = self._extract_subject(req)
            obj = self._extract_object(req)
            prop = slugify(self._extract_predicate(req))
            triples.append(
                f"atm:{prop} a owl:ObjectProperty ; rdfs:domain atm:{subject} ; rdfs:range atm:{obj} ."
            )
            triples.append(f"atm:{subject} a owl:Class .")
            triples.append(f"atm:{obj} a owl:Class .")
            triples.append(
                f"atm:{subject}_{prop}_{obj} a owl:Axiom ; atm:sourceRequirement \"{req.identifier}\" ."
            )
            notes.append(f"Mapped '{req.text}' → atm:{subject} {prop} atm:{obj}")
        turtle = "\n".join(triples)
        exemplar_ids = [req.identifier for req in exemplars] if exemplars else None
        return LLMResponse(
            turtle=turtle,
            reasoning_notes="\n".join(notes),
            exemplar_ids=exemplar_ids,
        )

    def generate_patch(self, prompts: Sequence[str], context_ttl: str) -> LLMResponse:
        """Emit a simple, deterministic patch guided by violation summaries.

        The heuristic repair step is intentionally conservative: it adds
        annotations that make the problematic nodes/classes explicit and
        declares any referenced properties as OWL object properties. This keeps
        the graph syntactically valid while providing a concrete edit so the
        closed-loop controller can progress even without remote LLM access.
        """

        triples: List[str] = [
            f"@prefix atm: <{self.base_ns}> .",
            "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
            "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        ]
        notes: List[str] = []
        for idx, prompt in enumerate(prompts, start=1):
            focus = slugify(prompt.split()[0])
            triples.append(f"atm:{focus} a owl:Class .")
            triples.append(
                f"atm:{focus}_repair_{idx} a owl:Axiom ; rdfs:comment \"{prompt}\" ."
            )
            notes.append(f"Added repair note for: {prompt}")

        if len(triples) == 3:
            notes.append("No violations provided; emitted empty patch.")
        turtle = "\n".join(triples)
        return LLMResponse(turtle=turtle, reasoning_notes="\n".join(notes))

    def apply_patches(self, patches: Sequence[dict], context_ttl: str) -> LLMResponse:
        """Deterministically apply patch instructions to the ontology graph."""

        from rdflib import Graph, Literal, Namespace, URIRef
        from rdflib.namespace import OWL, RDF, RDFS, XSD

        graph = Graph()
        graph.parse(data=context_ttl, format="turtle")
        atm = Namespace(self.base_ns)
        graph.bind("atm", atm)
        notes: List[str] = []

        def _iri(value: str) -> URIRef:
            if value.startswith("http"):
                return URIRef(value)
            if ":" in value:
                prefix, local = value.split(":", 1)
                ns = dict(graph.namespace_manager.namespaces()).get(prefix)
                if ns:
                    return URIRef(ns + local)
            return URIRef(self.base_ns + value)

        for patch in patches:
            action = patch.get("action", "").lower()
            subject = patch.get("subject") or "UnknownSubject"
            predicate = patch.get("predicate") or "rdfs:comment"
            obj = patch.get("object") or "xsd:string"
            message = patch.get("message") or ""

            subj_iri = _iri(subject)
            pred_iri = _iri(predicate)

            if action in {"addsubclass", "subclass"}:
                obj_iri = _iri(obj)
                graph.add((subj_iri, RDFS.subClassOf, obj_iri))
                graph.add((subj_iri, RDF.type, OWL.Class))
                graph.add((obj_iri, RDF.type, OWL.Class))
                notes.append(f"{action}: {subject} rdfs:subClassOf {obj}")
                continue

            if action in {"addtriple", "assert"}:
                obj_node = _iri(obj) if ":" in obj or obj.startswith("http") else Literal(obj)
                graph.add((subj_iri, pred_iri, obj_node))
                notes.append(f"{action}: {subject} {predicate} {obj}")
                continue

            if obj.startswith("xsd:"):
                graph.add((pred_iri, RDFS.domain, subj_iri))
                graph.add((pred_iri, RDFS.range, _iri(obj)))
                graph.add((pred_iri, RDFS.label, Literal(message or "Patched property")))
                graph.add((pred_iri, RDF.type, OWL.DatatypeProperty))
                graph.add((subj_iri, RDF.type, OWL.Class))
            else:
                obj_iri = _iri(obj)
                graph.add((pred_iri, RDFS.domain, subj_iri))
                graph.add((pred_iri, RDFS.range, obj_iri))
                graph.add((pred_iri, RDF.type, OWL.ObjectProperty))
                graph.add((subj_iri, RDF.type, OWL.Class))
                graph.add((obj_iri, RDF.type, OWL.Class))

            notes.append(f"{action or 'patch'}: {subject} {predicate} {obj}")

        turtle = graph.serialize(format="turtle")
        return LLMResponse(turtle=turtle, reasoning_notes="\n".join(notes) or "Applied patches without notes")

    def _extract_subject(self, requirement: Requirement) -> str:
        if "customer" in requirement.text.lower():
            return "Customer"
        if "bank" in requirement.text.lower():
            return "Bank"
        return "ATM"

    def _extract_object(self, requirement: Requirement) -> str:
        if "transaction" in requirement.text.lower():
            return "Transaction"
        if "card" in requirement.text.lower():
            return "CashCard"
        if "account" in requirement.text.lower():
            return "Account"
        return "RequirementTarget"

    def _extract_predicate(self, requirement: Requirement) -> str:
        text = requirement.text.lower()
        if "log" in text:
            return "logs"
        if "verify" in text:
            return "verifies"
        if "dispense" in text:
            return "dispenses"
        if "maintain" in text:
            return "maintains"
        return "relatesTo"


class OpenAILLM(LLMClient):
    """Adapter for the OpenAI Chat Completions API."""

    def __init__(
        self,
        model: str = "gpt-5.2",
        temperature: float = 0.1,
        system_prompt: str | None = None,
        seed: int | None = None,
    ) -> None:
        if OpenAI is None:
            raise RuntimeError("openai package is not installed")
        self.model = model
        self.temperature = temperature
        self.system_prompt = system_prompt or self._default_system_prompt()
        self.seed = seed

    def _completion_kwargs(self) -> dict:
        kwargs: dict = {"model": self.model, "temperature": self.temperature}
        if self.seed is not None:
            kwargs["seed"] = int(self.seed)
        return kwargs

    def generate_axioms(
        self,
        requirements: Sequence[Requirement],
        schema_context: SchemaContext | None = None,
        exemplars: Sequence[Requirement] | None = None,
    ) -> LLMResponse:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": self._build_prompt(requirements, schema_context, exemplars),
            },
        ]
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            messages=messages,
            **self._completion_kwargs(),
        )
        content = response.choices[0].message.content.strip() if response.choices else ""
        token_usage = _extract_token_usage(response)
        return LLMResponse(
            turtle=content,
            reasoning_notes="Generated via OpenAI chat.completions",
            token_usage=token_usage,
            exemplar_ids=[req.identifier for req in exemplars] if exemplars else None,
        )

    def generate_patch(self, prompts: Sequence[str], context_ttl: str) -> LLMResponse:
        repair_prompt = self._build_repair_prompt(prompts, context_ttl)
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": repair_prompt},
        ]
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            messages=messages,
            **self._completion_kwargs(),
        )
        content = response.choices[0].message.content.strip() if response.choices else ""
        token_usage = _extract_token_usage(response)
        return LLMResponse(
            turtle=content,
            reasoning_notes="Patch generated via OpenAI chat.completions",
            token_usage=token_usage,
        )

    def apply_patches(self, patches: Sequence[dict], context_ttl: str) -> LLMResponse:
        patch_prompt = self._build_patch_application_prompt(patches, context_ttl)
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": patch_prompt},
        ]
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            messages=messages,
            **self._completion_kwargs(),
        )
        content = response.choices[0].message.content.strip() if response.choices else ""
        token_usage = _extract_token_usage(response)
        return LLMResponse(
            turtle=content,
            reasoning_notes="Applied patches via OpenAI chat.completions",
            token_usage=token_usage,
        )

    def _build_prompt(
        self,
        requirements: Sequence[Requirement],
        schema_context: SchemaContext | None,
        exemplars: Sequence[Requirement] | None = None,
    ) -> str:
        schema_section = self._format_schema_context(schema_context) if schema_context else ""
        exemplar_section = self._format_few_shot_examples(exemplars) if exemplars else ""

        spec_section = (
            "SECTION B — Drafting Specification\n"
            "- Use only the allowed classes and properties listed above.\n"
            "- Do not invent new class or property names unless a requirement introduces a clear new concept.\n"
            "- Respect domain/range constraints; align datatype properties to their declared datatypes.\n"
            "- Use the atm: namespace consistently; declare prefixes as needed.\n"
            "- Output only valid Turtle OWL axioms; do not include explanations.\n"
        )

        body = []
        for req in requirements:
            context = f"Title: {req.title}\nText: {req.text}"
            if req.boilerplate:
                context += f"\nBoilerplate:\n{req.boilerplate}"
            body.append(context)
        joined = "\n\n".join(body)

        requirements_section = f"SECTION C — Requirements Input\n{joined}"
        return "\n\n".join(
            filter(None, [schema_section, spec_section, exemplar_section, requirements_section])
        )

    def _format_schema_context(self, schema_context: SchemaContext) -> str:
        lines = ["SECTION A — Allowed Vocabulary (schema constraints)"]

        if schema_context.prefixes:
            lines.append("Prefixes:")
            for prefix, uri in schema_context.prefixes.items():
                lines.append(f"- {prefix}: <{uri}>")

        if schema_context.classes:
            lines.append("Valid classes:")
            for cls in schema_context.classes:
                lines.append(f"- {cls}")

        if schema_context.object_properties:
            lines.append("Valid object properties (domain → range):")
            for name, details in schema_context.object_properties.items():
                lines.append(f"- {name}: {details['domain']} → {details['range']}")

        if schema_context.datatype_properties:
            lines.append("Valid datatype properties (domain → datatype):")
            for name, details in schema_context.datatype_properties.items():
                lines.append(f"- {name}: {details['domain']} → {details['range']}")

        if schema_context.labels:
            lines.append("Labels / comments:")
            for term, label in schema_context.labels.items():
                lines.append(f"- {term}: {label}")

        return "\n".join(lines)

    def _format_few_shot_examples(self, exemplars: Sequence[Requirement]) -> str:
        if not exemplars:
            return ""

        blocks: List[str] = ["FEW-SHOT EXAMPLES (dev only):"]
        for exemplar in exemplars:
            blocks.append(f"[{exemplar.identifier}] {exemplar.text}")
            axioms_block = self._render_exemplar_axioms(exemplar)
            if axioms_block:
                blocks.append(axioms_block)
            blocks.append("---")
        return "\n".join(blocks).rstrip("-\n")

    def _render_exemplar_axioms(self, exemplar: Requirement) -> str:
        if exemplar.axioms is None:
            return ""

        sections: List[str] = []
        for key in ("prefixes", "tbox", "abox"):
            axioms = exemplar.axioms.get(key)
            if not axioms:
                continue
            if isinstance(axioms, dict):
                for prefix, uri in axioms.items():
                    sections.append(f"@prefix {prefix}: <{uri}> .")
            elif isinstance(axioms, list):
                sections.extend(axioms)
        return "\n".join(sections)

    def _default_system_prompt(self) -> str:
        return (
            "You are an ontology engineer who drafts OWL 2 DL axioms using Turtle syntax. "
            "Emit only syntactically valid Turtle with atm: prefix."
        )

    def _build_repair_prompt(self, prompts: Sequence[str], context_ttl: str) -> str:
        prompt_block = "\n".join(f"- {p}" for p in prompts) or "- No violations provided"
        return (
            "You are repairing an OWL ontology. Given the SHACL/Reasoner issues below, "
            "emit a compact Turtle patch that resolves them without deleting existing classes.\n\n"
            "Issues:\n"
            f"{prompt_block}\n\n"
            "Context (truncated Turtle):\n"
            f"{context_ttl[:4000]}\n"
            "Respond only with Turtle additions that address the issues."
        )

    def _build_patch_application_prompt(self, patches: Sequence[dict], context_ttl: str) -> str:
        import json

        patch_block = json.dumps(patches, indent=2, ensure_ascii=False)
        return (
            "You are repairing an OWL ontology using a deterministic patch plan.\n"
            "Apply only the patches provided; do not invent new resources, change namespaces, or delete existing triples.\n"
            "Preserve all prefixes and re-emit the entire ontology in Turtle syntax. Keep every triple that already\n"
            "exists unless a patch explicitly deletes it. Do not introduce new URIs or classes outside the provided\n"
            "namespaces. Maintain domains/ranges unless the patch changes them.\n\n"
            "Patch plan (JSON):\n"
            f"{patch_block}\n\n"
            "Current ontology (Turtle):\n"
            f"{context_ttl[:6000]}\n"
            "Return a full Turtle serialization that applies the patches and keeps all other triples intact."
        )


def _extract_token_usage(response) -> Dict[str, int] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None

    token_usage: Dict[str, int] = {}
    for field in ("prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens"):
        value = getattr(usage, field, None)
        if value is not None:
            token_usage[field] = int(value)

    # Some response objects expose a to_dict helper; merge to capture additional keys
    if hasattr(usage, "to_dict"):
        for key, value in usage.to_dict().items():  # type: ignore[call-arg]
            if isinstance(value, int):
                token_usage.setdefault(key, value)

    return token_usage or None
