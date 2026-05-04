# Data Provenance and Transformation Log

This file documents concrete upstream datasets and the reproducible transformation steps used to produce the normalized requirement corpora in this repository.

Important clarification: the requirement files in `data/requirements/` are **derived corpora**, not raw upstream datasets copied as-is. They are source-anchored, then normalized into a common `{title,text}` schema for reproducible cross-domain experiments.

## 1) Upstream sources used

### ATM domain (requirements corpus basis)

- Primary source document: <https://www.cs.toronto.edu/~sme/CSC340F/2005/assignments/inspections/atm.pdf>
- Source title (from PDF): "Requirements document for an automated teller machine network"
- Local file produced: `data/requirements/atm_requirements.jsonl`
- Notes: ATM requirements were extracted from the source PDF and normalized to canonical `{title,text}` records.

### Health domain (requirements corpus basis)

- Upstream anchors:
  - MIMIC-IV v2.2: <https://physionet.org/content/mimiciv/2.2/>
  - MIMIC-IV-ED v2.2: <https://physionet.org/content/mimic-iv-ed/2.2/>
- Access model: PhysioNet credentialed dataset access and associated data-use terms.
- Local file produced: `data/requirements/health_requirements.jsonl`
- Notes: Health requirements are a derived abstraction of real clinical workflow concepts (appointments/visits, labs, prescriptions, billing, vitals) and are maintained in the same canonical input format as ATM and Retail for fair cross-domain runs.

### Retail domain (real data anchor)

- UCI Online Retail dataset (ID 352): <https://archive.ics.uci.edu/dataset/352/online+retail>
- Declared UCI license: CC BY 4.0
- Local files produced:
  - `data/requirements/retail_requirements.jsonl`
  - `data/domains/retail/retail_gold.ttl`
  - `data/shapes/shapes_retail.ttl`
  - `data/queries/retail_cqs.rq`
- Notes: Requirement statements are a controlled semantic abstraction of real transactional concepts from the UCI schema.

## 2) Required evidence for journal reporting

For every reported domain (ATM, Health, Retail), fill the following before final submission:

- Source dataset URL / citation
- License
- Version or retrieval date
- Inclusion/exclusion criteria
- Preprocessing steps
- Final counts (requirements, classes/properties in gold, SHACL shapes, CQ count)

Use `data/registry.json` (`metadata_to_fill`) as the machine-readable version of the same information.
Use `data/DATA_LICENSES.md` as the legal/redistribution matrix for manuscript and repository checks.

## 3) Normalized requirement format

All requirement files under `data/requirements/` are stored as:

```json
[
  {"title": "Requirement 1", "text": "..."},
  {"title": "Requirement 2", "text": "..."}
]
```

This keeps input format identical across domains and avoids mixing annotations (boilerplate/placeholders/axioms) into prompt input.

## 4) Reproducible conversion procedure

Use:

`scripts/normalize_requirements_json.py`

Example:

`python scripts/normalize_requirements_json.py --input data/requirements/source.jsonl --output data/requirements/normalized.jsonl`

Conversion rules implemented by the script:

1. Parse JSON array/object or JSONL lines.
2. Keep only records that contain non-empty `text`.
3. Rewrite each record to `{title: "Requirement N", text: <original text>}`.
4. Write canonical pretty JSON array output.

### 4.1) ATM transformation steps (what was done)

1. Read source SRS from: <https://www.cs.toronto.edu/~sme/CSC340F/2005/assignments/inspections/atm.pdf>
2. Extract requirement statements from functional/performance requirement sections.
3. Clean OCR/layout artifacts (broken spacing, list markers, section noise).
4. Normalize each statement into `{title,text}` and re-index as `Requirement 1..30`.
5. Save final corpus as `data/requirements/atm_requirements.jsonl`.

### 4.2) Health transformation steps (what was done)

1. Start from clinical workflow concepts observed in MIMIC-IV / MIMIC-IV-ED documentation and schema (encounters, clinicians, lab orders/results, prescriptions, billing, vitals).
2. Convert those concepts into requirement-style natural-language statements suitable for ontology drafting tasks.
3. Keep only input-facing requirement text fields for pipeline use.
4. Normalize to canonical `{title,text}` and re-index as `Requirement 1..30`.
5. Save final corpus as `data/requirements/health_requirements.jsonl`.

### 4.3) Retail transformation steps (what was done)

1. Use UCI Online Retail (ID 352) as semantic anchor for entities/relations.
2. Derive requirement statements from transaction concepts (order, product, payment, inventory, shipment, return).
3. Normalize to canonical `{title,text}` and re-index as `Requirement 1..30`.
4. Save final corpus as `data/requirements/retail_requirements.jsonl`.

## 5) Current asset counts (for reproducibility table)

- Requirements:
  - ATM: 30
  - Health: 30
  - Retail: 30
- CQ count:
  - ATM: 21 ASK queries
  - Health: 8 ASK queries
  - Retail: 5 ASK queries
- SHACL node-shape count:
  - ATM: 6
  - Health: 8
  - Retail: 5

## 6) Current status note

All three domains now have full assets (requirements, gold ontology, SHACL shapes, CQs) and machine-readable provenance fields populated in `data/registry.json`.

## 7) Legal/compliance note

- These requirement corpora are derived and normalized artifacts.
- They should be described in papers as source-anchored derivatives, not raw upstream republications.
- Before journal submission, run the checklist in `data/DATA_LICENSES.md`.
