# Experiment configs (core E1–E6)

Exactly **six** JSON files form the default experiment ladder; E5 bundles both ATM and healthcare in one manifest.

| File | Role |
|------|------|
| `e1_llm_only_atm.json` | E1 — LLM-only baseline (ATM) |
| `e2_symbolic_atm.json` | E2 — SHACL + reasoner symbolic baseline (ATM) |
| `e3_ontology_aware_atm.json` | E3 — ontology-aware drafting, no repair loop |
| `e4_iterative_repair_atm.json` | E4 — iterative SHACL/CQ repair (also default for stability, ablation, diagnostics runners) |
| `e5_cross_domain_manifest.json` | E5 — `domains`: inline ATM + health blocks; `extra_domains`: optional list (same shape) for extra cross-domain runs |
| `e6_cq_oriented_atm.json` | E6 — CQ-oriented / threshold-style runs (ATM) |

Each E5 domain entry may be **inline** (fields as in the sample) or, if you prefer split files, include `"config": "configs/…json"` plus `name` / `output_root` overrides.

Override defaults with `--config` on the matching script.
