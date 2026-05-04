"""Failure taxonomy for iterative ontology repair (journal Table 7, codes F1–F10)."""

from __future__ import annotations

from og_nsd.ontology import SchemaContext

# Paper-ready labels (English); Greek descriptions live in the manuscript.
CANONICAL_FAILURE_TAGS: dict[str, str] = {
    "F1": "F1_vocabulary_drift",
    "F2": "F2_missing_declaration",
    "F3": "F3_malformed_restriction",
    "F4": "F4_domain_range_misuse",
    "F5": "F5_patch_duplication",
    "F6": "F6_cq_overfitting",
    "F7": "F7_graph_explosion",
    "F8": "F8_reasoning_instability",
    "F9": "F9_semantic_dilution",
    "F10": "F10_repair_stagnation",
}

FAILURE_TAXONOMY_META: dict[str, tuple[str, str]] = {
    "F1": (
        "Vocabulary drift",
        "New project-namespace terms not present in the grounding schema.",
    ),
    "F2": (
        "Missing declaration",
        "Class-level axioms referenced resources that lacked an explicit owl:Class declaration before reasoning.",
    ),
    "F3": (
        "Malformed restriction",
        "Invalid OWL restriction patterns removed or coerced before reasoning, or patch Turtle failed to parse.",
    ),
    "F4": (
        "Domain/range misuse",
        "SHACL reports datatype, class, or node-kind constraint violations on properties (typing / domain-range alignment).",
    ),
    "F5": (
        "Patch duplication",
        "Repair proposes the same patch content as the previous iteration (no semantic progress).",
    ),
    "F6": (
        "CQ overfitting",
        "Competency-question pass rate improves while hard SHACL violations increase.",
    ),
    "F7": (
        "Graph explosion",
        "Reasoned triple count jumps faster than the configured growth-ratio cap.",
    ),
    "F8": (
        "Reasoning instability",
        "Reasoner reports inconsistency, failure, or raised an exception.",
    ),
    "F9": (
        "Semantic dilution",
        "Graph grows without CQ gain and without reduction in hard violations (precision not keeping pace with size).",
    ),
    "F10": (
        "Repair stagnation",
        "No CQ improvement for at least the configured patience window.",
    ),
}


def taxonomy_meta_for_tag(tag: str) -> tuple[str, str, str]:
    """Return (code, title, description) for a stored tag like ``F6_cq_overfitting``."""

    key = _tag_to_code(tag)
    title, desc = FAILURE_TAXONOMY_META.get(key, ("Unknown", ""))
    return key, title, desc


def _tag_to_code(tag: str) -> str:
    for n in range(10, 0, -1):
        prefix = f"F{n}"
        if tag.startswith(prefix + "_") or tag == prefix:
            return prefix
    return tag.split("_", 1)[0] if "_" in tag else tag


def _expand_schema_term(term: str, prefixes: dict[str, str], base_ns: str) -> str | None:
    term = term.strip()
    if term.startswith("http://") or term.startswith("https://"):
        return term
    if ":" not in term:
        return None
    prefix, name = term.split(":", 1)
    uri_base = prefixes.get(prefix) or base_ns
    base = str(uri_base).rstrip("#/")
    return f"{base}#{name}"


def grounding_iris(schema: SchemaContext, base_ns: str) -> set[str]:
    """Full IRIs of classes and properties advertised in the grounding schema."""

    prefixes = schema.prefixes or {}
    out: set[str] = set()
    for cls in schema.classes:
        iri = _expand_schema_term(cls, prefixes, base_ns)
        if iri:
            out.add(iri)
    for name in list(schema.object_properties.keys()) + list(schema.datatype_properties.keys()):
        iri = _expand_schema_term(name, prefixes, base_ns)
        if iri:
            out.add(iri)
    return out


def compute_iteration_taxonomy(
    *,
    schema_context: SchemaContext | None,
    base_ns: str,
    new_classes: set[str],
    new_properties: set[str],
    growth_ratio: float,
    max_growth_ratio: float,
    reasoner_consistent: bool | None,
    reasoner_notes: str,
    no_gain_streak: int,
    no_gain_patience: int,
    patches_unchanged: bool,
    hard_violations: int,
    prev_hard_violations: int | None,
    cq_gain: float,
    new_triples: int,
    shacl_constraint_components: list[str],
    shacl_messages: list[str],
    shacl_violation_total: int = 0,
    patch_parse_error: bool = False,
) -> list[str]:
    """Return ordered unique failure tags for one repair iteration."""

    categories: list[str] = []
    notes = (reasoner_notes or "").lower()
    notes_lc = notes

    # F1 — terms in project namespace not in grounding vocabulary
    if schema_context and (new_classes or new_properties):
        allowed = grounding_iris(schema_context, base_ns)
        base = base_ns.rstrip("#/") + "#"
        for iri in new_classes | new_properties:
            if iri.startswith(base) and iri not in allowed:
                categories.append(CANONICAL_FAILURE_TAGS["F1"])
                break

    # F2 — auto-added class declarations for missing owl:Class
    if "missing owl:class" in notes_lc or (
        "declared" in notes_lc and "missing" in notes_lc and "owl:class" in notes_lc
    ):
        categories.append(CANONICAL_FAILURE_TAGS["F2"])

    # F3 — stripped restrictions / coerced literals (pre-reasoning sanitation)
    if (
        "invalid restriction" in notes_lc
        or ("removed" in notes_lc and "restriction" in notes_lc)
        or ("coerced" in notes_lc and "literal" in notes_lc)
        or patch_parse_error
    ):
        categories.append(CANONICAL_FAILURE_TAGS["F3"])

    # F4 — SHACL typing / domain-range style constraints
    comp_lc = " ".join(shacl_constraint_components).lower()
    msg_blob = " ".join(m or "" for m in shacl_messages).lower()
    if any(
        token in comp_lc
        for token in (
            "datatypeconstraintcomponent",
            "classconstraintcomponent",
            "nodekindconstraintcomponent",
            "inconstraintcomponent",
        )
    ) or any(
        token in msg_blob
        for token in ("datatype", "expected class", "node kind", "range", "domain", "sh:class")
    ):
        if shacl_violation_total > 0:
            categories.append(CANONICAL_FAILURE_TAGS["F4"])

    if patches_unchanged:
        categories.append(CANONICAL_FAILURE_TAGS["F5"])

    if (
        prev_hard_violations is not None
        and cq_gain > 1e-6
        and hard_violations > prev_hard_violations
    ):
        categories.append(CANONICAL_FAILURE_TAGS["F6"])

    if growth_ratio > max_growth_ratio:
        categories.append(CANONICAL_FAILURE_TAGS["F7"])

    if reasoner_consistent is False or any(
        token in notes_lc for token in ("failed", "exception", "nullpointer", "error", "pellet failed")
    ):
        categories.append(CANONICAL_FAILURE_TAGS["F8"])

    if (
        new_triples > 0
        and growth_ratio > 1.05
        and cq_gain <= 0
        and prev_hard_violations is not None
        and hard_violations >= prev_hard_violations
    ):
        categories.append(CANONICAL_FAILURE_TAGS["F9"])

    if no_gain_streak >= no_gain_patience:
        categories.append(CANONICAL_FAILURE_TAGS["F10"])

    # Preserve F-code order for stable diffs and paper tables
    order = {f"F{i}": i for i in range(1, 11)}
    seen: set[str] = set()
    ordered: list[str] = []
    for tag in sorted(set(categories), key=lambda t: (order.get(_tag_to_code(t), 99), t)):
        if tag not in seen:
            seen.add(tag)
            ordered.append(tag)
    return ordered
