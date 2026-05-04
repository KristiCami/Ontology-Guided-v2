# Data for the journal paper

The experimental narrative fits **three primary datasets**:

1. **Primary A — ATM** (`domains/atm/`, `requirements/atm_requirements.jsonl`, `queries/atm_cqs.rq`)  
   - Main benchmark: drafting, SHACL, reasoning, CQ, iterative repair, stability, error taxonomy.  
   - **Grounding** and **metrics reference** both use `atm_gold.ttl`.

2. **Primary B — Health** (`domains/health/`, `requirements/health_requirements.jsonl`, `queries/health_cqs.rq`)  
   - Cross-domain / transfer: same pipeline, different vocabulary and shapes.  
   - Fills the second main corpus slot for generalization claims.

3. **Primary C — Retail** (`domains/retail/`, `requirements/retail_requirements.jsonl`, `queries/retail_cqs.rq`)  
   - Third domain for journal-level multi-domain robustness claims.
   - Covers ordering, payment, inventory, shipment, and returns semantics.

Machine-readable summary: **`registry.json`** (paths + fields to fill: source, license, counts).  
Human-readable provenance + conversion steps: **`DATA_PROVENANCE.md`**.  
Legal/redistribution matrix for journal submission: **`DATA_LICENSES.md`**.

## Per–primary-dataset checklist (what must exist)

For each primary domain you report in the journal:

| Asset | Role |
|-------|------|
| Requirements (JSONL) | NL input; one line per requirement with stable ID |
| Gold / reference ontology (TTL) | Evaluation reference (precision/recall/F1, semantic metrics) |
| Grounding TBox (TTL) | Optional schema grounding asset (in this setup we reuse gold) |
| SHACL shapes (TTL) | Structural constraints + violation-driven repair |
| CQ suite (`.rq`) | SPARQL ASK competency questions |
| Short **DATA.md** or `registry.json` metadata | Provenance, license, version, construction methodology |

## Current layout (repo)

| Path | Contents |
|------|----------|
| `domains/atm/` | `atm_gold.ttl` |
| `domains/health/` | `health_gold.ttl` |
| `domains/retail/` | `retail_gold.ttl` |
| `shapes/` | `shapes_atm.ttl`, `shapes_health.ttl`, `shapes_retail.ttl` |
| `requirements/` | `atm_requirements.jsonl`, `health_requirements.jsonl`, `retail_requirements.jsonl` |
| `queries/` | `atm_cqs.rq`, `health_cqs.rq`, `retail_cqs.rq` |
| `db/` | Reserved for local DB / exports (optional) |

All paths in `configs/*.json` are relative to the **repository root**.

## Priority for a strong journal

1. **Freeze and document** all primary corpora (license, source, version, train/dev/test policy).  
2. **Align CQs and SHACL** with claims: every table row should trace to these files.  
3. **Keep provenance precise**: avoid references to assets that are not present under `data/`.
4. **Compliance gate before submission**: verify `DATA_LICENSES.md` checklist and keep "derived/normalized corpus" wording in the manuscript.
