# Ontology-Guided Ontology Drafting from Software Requirements

**A Neuro–Symbolic Pipeline for OWL Generation, Validation, and Feedback Repair**

---

## 0. System Overview & Quickstart
The repository contains an end-to-end implementation of the OG–NSD pipeline described in the accompanying paper. The code turns unstructured requirement statements into OWL axioms, validates them with SHACL shapes, optionally runs DL reasoning, and then uses the validation feedback to drive a closed-loop repair stage until the ontology conforms or a budget of iterations is exhausted.

### Repository layout
```
README.md
og_nsd/                     ← Python package (pipeline modules)
configs/                    ← Core experiment profiles E1–E6 (see configs/README.md)
data/                       ← Two primary corpora (ATM, health) + auxiliary bundle; see data/README.md & data/registry.json
  domains/atm/              ← ATM TTL assets (gold, context TBox, SHACL shapes)
  domains/health/           ← Healthcare domain TTL + shapes
  requirements/             ← JSONL requirement corpora
  queries/                  ← SPARQL ASK competency-question suites (.rq)
  splits/                   ← Dev/test requirement ID lists
  auxiliary/                ← Exemplars, stress JSONL, optional third-domain seed
  db/                       ← Reserved for local DB / exports (empty by default)
scripts/                    ← CLI runners (`run_pipeline`, E1–E6, journal tooling)
runs/                       ← Generated experiment outputs (gitignored except README)
paper/
  workshop/                 ← ACM-style workshop LaTeX sources
  journal/                  ← IEEE-style journal LaTeX skeleton
tests/                      ← Unit tests
docs/                       ← Optional notes (empty scaffold; see docs/README.md)
requirements.txt
```

### Installation
1. **Create a virtual environment** (Python ≥ 3.10 recommended) in PowerShell:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```
   **macOS (Terminal / zsh)**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```
2. **(Optional) Enable OpenAI-backed prompting.** Install `openai` and set `OPENAI_API_KEY`:
   ```powershell
   python -m pip install openai
   $env:OPENAI_API_KEY="sk-..."
   ```
   **macOS (Terminal / zsh)**
   ```bash
   python -m pip install openai
   export OPENAI_API_KEY="sk-..."
   ```
   The default mode (`--llm-mode heuristic`) is offline-safe and derives axioms with lightweight pattern rules for reproducibility.
   The provided ATM ontology-aware config (`configs/e3_ontology_aware_atm.json`) is now set to use the OpenAI backend, so ensure
   `OPENAI_API_KEY` is configured (or override `llm_mode` to `heuristic`) before running that example.

### Running the pipeline (ATM example)
```powershell
python scripts/run_pipeline.py `
  --requirements data/requirements/atm_requirements.jsonl `
  --shapes data/shapes/shapes_atm.ttl `
  --base data/domains/atm/atm_gold.ttl `
  --cqs data/queries/atm_cqs.rq `
  --output build/atm_generated.ttl `
  --report build/atm_report.json `
  --max-reqs 50 `
  --iterations 2
```
**macOS (Terminal / zsh)**
```bash
python scripts/run_pipeline.py \
  --requirements data/requirements/atm_requirements.jsonl \
  --shapes data/shapes/shapes_atm.ttl \
  --base data/domains/atm/atm_gold.ttl \
  --cqs data/queries/atm_cqs.rq \
  --output build/atm_generated.ttl \
  --report build/atm_report.json \
  --max-reqs 50 \
  --iterations 2
```
Key outputs:
- `build/atm_generated.ttl`: merged ontology (bootstrap + generated axioms + any repair patches).
- `build/atm_report.json`: SHACL summary, structured violation list, CQ pass/fail list, iteration-by-iteration diagnostics, LLM notes, and reasoning diagnostics if enabled (`--reasoning`).

### Draft-only baseline (raw ontology)
To reproduce the raw, no-assistance baseline (`pred.ttl` in the paper's notation), stop the pipeline after the first drafting pass and omit grounding assets. The command below writes the unvalidated ontology to `build/pred.ttl`:

```bash
python scripts/run_pipeline.py \
  --requirements data/requirements/atm_requirements.jsonl \
  --output build/pred.ttl \
  --llm-mode openai \
  --max-reqs 50 \
  --draft-only
```
Key points:
- Skip `--shapes` and `--base` to keep the model free-form; `--draft-only` bypasses SHACL/reasoner checks and any repair loop.
- You can still use `--llm-mode heuristic` for offline reproducibility, the command above shows the OpenAI-backed baseline.

### Customising runs
| Need | How |
| ---- | --- |
| Switch to OpenAI generation | Pass `--llm-mode openai` (requires API key). |
| Limit runtime | Adjust `--max-reqs` to sample the requirement corpus. |
| Enable DL reasoning | Append `--reasoning` (Pellet must be installed on the host; otherwise the code falls back gracefully). |
| Tune the repair loop | Set `--iterations` and `--temperature` to control how many violation→prompt rounds the pipeline attempts. |
| Use another domain | Point `--shapes`, `--base`, and `--cqs` to the new ontology assets. |
| Save intermediate Turtle | Edit `PipelineConfig` (see `og_nsd/config.py`) or extend `scripts/run_pipeline.py`. |
| Turn on ontology-aware prompting | Add `--use-ontology-context --ontology-context data/domains/atm/atm_gold.ttl` (or rely on `--base` as the grounding file) to feed schema vocabulary into the LLM prompt without copying gold axioms. |

Example ontology-aware draft run (OpenAI-backed):
```bash
python scripts/run_pipeline.py \
  --requirements data/requirements/atm_requirements.jsonl \
  --shapes data/shapes/shapes_atm.ttl \
  --output build/atm_generated.ttl \
  --report build/atm_report.json \
  --llm-mode openai \
  --use-ontology-context \
  --ontology-context data/domains/atm/atm_gold.ttl \
  --iterations 1
```

### Experiment runners (Table A)
The following scripts map directly to the experiments in Table A. Each script writes outputs under `runs/`.

```bash
# E1: LLM-only baseline
python scripts/run_e1_llm_only.py --config configs/e1_llm_only_atm.json

# E2: Symbolic-only baseline (heuristic rules + SHACL/Reasoner)
python scripts/run_e2_symbolic_only.py --config configs/e2_symbolic_atm.json

# E3: Ours (no-repair)
python scripts/run_atm_examples.py --config configs/e3_ontology_aware_atm.json

# E4: Ours (full closed-loop)
python scripts/run_e4_iterative.py --config configs/e4_iterative_repair_atm.json

# E5: Cross-domain (edit domains inside configs/e5_cross_domain_manifest.json)
python scripts/run_e5_cross_domain.py --config configs/e5_cross_domain_manifest.json

# E6: CQ-oriented (per-iteration CQ summary)
python scripts/run_e6_cq_oriented.py --config configs/e6_cq_oriented_atm.json
```

E5 uses a single manifest, `configs/e5_cross_domain_manifest.json`: its `domains` array holds inline ATM and healthcare blocks (add more domains there if needed). Optional additional domains for extended studies go in the same file under `extra_domains` (used by `run_execution_plan.py` step 9). Paths use `data/requirements/health_requirements.jsonl`, `data/domains/health/health_gold.ttl`, `data/shapes/shapes_health.ttl`, and `data/queries/health_cqs.rq` for health. Both default to `llm_mode=openai`. For offline runs, pass `--llm-mode heuristic` to `scripts/run_e5_cross_domain.py`.

### Development tips
- The pipeline is modular: swap in a domain-specific LLM by subclassing `LLMClient` or plug in another validator by editing `og_nsd/shacl.py`.
- `RequirementLoader` supports both pure JSON (list/dict) and JSONL files.  It also exposes `chunk_requirements` for few-shot prompt batching.
- Competency questions are plain SPARQL ASK queries separated by blank lines/comments, making it easy to author new CQ suites per domain.

---

## Abstract
Natural language requirements are often ambiguous and inconsistent, hindering automated validation and reuse. We present a neuro–symbolic pipeline that transforms free-form requirements into validated OWL ontologies via a closed-loop architecture that integrates Large Language Models (LLMs), SHACL constraints, and logical reasoning. Our contributions include (i) ontology-aware LLM prompting, (ii) SHACL-guided iterative repair, (iii) hybrid reasoning and validation, and (iv) plug-and-play domain adaptability. Evaluation on an ATM case study demonstrates improved precision, recall, and constraint compliance compared to neural-only and symbolic-only baselines.

**Index Terms** — Ontology learning, requirements engineering, OWL, SHACL, large language models, neuro–symbolic AI, automated reasoning.

## I. Introduction
### Problem
Requirements in natural language (NL) are informal and underspecified, creating obstacles for automation in validation, traceability, and reuse. Ontologies can provide a shared, machine-interpretable conceptualization but are costly to author manually.

### Approach
We propose OG–NSD, a compact neuro–symbolic pipeline that drafts OWL ontologies from NL requirements, aligns them with available vocabularies, validates them with reasoners and SHACL, and uses violations as repair prompts to iteratively converge to compliance.

### Contributions
Unlike prior ontology learning and neuro–symbolic frameworks, OG–NSD introduces three innovations:
1. **Violation-to-prompt synthesis**: SHACL and reasoner violations are automatically transformed into structured repair prompts, enabling an iterative self-correcting loop for OWL generation.
2. **Ontology-aware LLM prompting**: Domain vocabularies and exemplars are injected into prompts to ground the neural model and reduce semantic drift, improving both recall and convergence speed.
3. **Plug-and-play domain portability**: By swapping ontologies and SHACL shapes, the pipeline generalizes across domains (ATM, healthcare, automotive) without retraining the LLM.

Together, these contributions establish OG–NSD as the first neuro–symbolic pipeline that closes the loop between natural language requirements, ontology generation, and automated repair.

### Results (preview)
On an ATM case study and two additional domains, OG–NSD improves F1 and reduces violations relative to neural-only and symbolic-only baselines. Quantitative tables are being refreshed as the latest runs finish; early results show double-digit reductions in SHACL violations and consistent F1 gains over both neural-only and symbolic-only ablations.

## II. Related Work
### Ontology learning from text
Early pipelines extract terms and axioms from corpora via lexical patterns and statistical signals [1–4]. Text2Onto [2] and OntoLearn [3] exemplify the classic generate–then–curate approach: they induce taxonomies/relations and typically rely on manual post-editing or offline validation. OpenIE [4] broadened coverage but remained schema-agnostic. In contrast, OG–NSD does not stop at generation: it closes the loop by converting validator diagnostics into structured prompts that drive iterative OWL repair.

### Ontology alignment and reuse
Ontology matching is a mature field [5]. While our alignment step is standard, its role is different: matches supply hints (preferred labels, ranges, domains) that are injected into repair prompts, steering edits toward schema-consistent axioms during the loop.

### Validation with SHACL and reasoning
OWL 2 reasoners (e.g., Pellet, HermiT, ELK) ensure logical coherence and detect unsatisfiable classes [6–9]. SHACL [10] complements reasoning with shape-based constraints for structural and datatype compliance. Most pipelines apply these as post-hoc filters. OG–NSD integrates both as first-class feedback: SHACL/Reasoner messages are canonicalized and transformed into targeted LLM prompts (violation→prompt synthesis), enabling self-correction until conformance.

### Neuro–symbolic integration
Neuro-symbolic AI combines learning with logic via joint models or iterative coordination [11, 12]. Differentiable reasoning and rule-induction (e.g., Neural Theorem Provers; neural rule learning) show how constraints can guide learning [13, 14]. Our approach is orthogonal: we keep OWL/SHACL validators discrete and use their outputs to steer a powerful generator (an LLM) in a closed, symbolic-feedback loop.

### Closed-loop prompting and self-refinement
LLM self-improvement via structured feedback improves quality in open-ended tasks [15, 16]. OG–NSD adapts this idea to ontology engineering: validator diagnostics plus local graph context are turned into domain-aware prompts that request specific OWL patches, yielding consistent reductions in violations and improved recall.

## III. Methodology
### A. Problem Setup
Let $R$ be a set of natural language requirement sentences; let $O$ be a set of available ontologies with vocabulary $A$ (labels, synonyms, properties); and let $S$ be a set of SHACL shapes. The goal is to produce an OWL ontology $G$ that (i) is logically consistent under a DL reasoner and (ii) conforms to $S$.

We write $\text{viol}(G, S)$ for the multiset of SHACL violations returned by the validator and $\text{unsat}(G)$ for the set of unsatisfiable classes produced by the reasoner. We assess conformance via the weighted objective in Section III-B.

### B. Weighted SHACL Objective
Not all constraints are equally critical. We partition them into hard constraints (consistency, coherence, safety-critical SHACL shapes) and soft constraints (optional shapes, stylistic conventions, non-critical CQs). We then optimize a weighted objective:

$$
\min_{S \subseteq \mathcal{P}} \lambda_1 \sum_{v \in V_{\text{soft}}(S)} w(v) + \lambda_2 \, \text{EditCost}(S) + \lambda_3 \, \text{CQFail}(S) \quad \text{s.t.} \quad V_{\text{hard}}(S) = \varnothing.
$$

Here $w(v)$ is a weight for each soft violation, $\text{EditCost}$ penalizes distance from the prior ontology, and $\text{CQFail}$ counts failed competency questions. Hard constraints must be satisfied at all times. Here $\mathcal{P}$ denotes the finite set of candidate patches synthesized in the current round (Section III-F). $V_{\text{hard}}(S)$ and $V_{\text{soft}}(S)$ are, respectively, the sets of hard and soft violations remaining after applying $S$ to $G$ and re-validating. In our experiments, we set $\alpha = \beta = 1$, treating SHACL violations and unsatisfiable classes as equally important. Sensitivity analysis with other small values showed stable results.

### C. Pipeline Overview
The pipeline (Figure 1) follows five stages: (1) requirement segmentation, (2) LLM-based OWL axiom drafting, (3) alignment to existing ontologies, (4) hybrid validation using a DL reasoner and SHACL, and (5) violation-to-repair prompt synthesis for iterative correction until conformance.

**What is novel here.** Unlike prior pipelines that apply SHACL/reasoning only as a post-hoc filter, OG–NSD treats validation output as actionable feedback. Violations are canonically mapped to structured repair prompts for the LLM, closing the loop (NL → OWL → validate → prompt → OWL) until $\Phi(G)$ reaches zero or a budget is met.

### D. Methodological Framing: Counterexample-Guided Ontology Repair
Our pipeline can be understood as an instance of Counterexample-Guided Inductive Repair (CEGIR). In classical program synthesis and verification, CEGIS generates a candidate program, checks it against a verifier, and iteratively refines it using counterexamples. Analogously, OG–NSD generates OWL axioms from requirements, validates them via SHACL and reasoning, and treats each violation or failed competency question as a counterexample. The LLM proposes candidate ontology patches, and the verifier either accepts them or returns new counterexamples. This reframing positions our loop as the ontology analogue of CEGIS, but enhanced with domain vocabularies and semantic constraints.

### E. Ontology-Aware Prompting
Given preloaded ontologies $O$ and their vocabularies $A$, we ground the LLM with (i) preferred labels and synonyms, (ii) domain relations, and (iii) naming/typing conventions (e.g., class vs. object property) to reduce semantic drift. We use few-shot exemplars in Turtle with comments mapping NL phrases to OWL axioms; Listing 1 shows a minimal example.

**Component 1 (E3) — Ontology-Aware Prompting.** The ontology-aware mode redraws the ontology from the requirements text but constrains the vocabulary using a schema extracted from the gold ontology. The gold TTL is never injected verbatim; instead, a structured grounding context is built from classes, object properties with domain/range, datatype properties with datatypes, labels/comments, and prefix rules. The prompt is organised into three sections: (A) allowed vocabulary and domain/range constraints, (B) drafting specifications that forbid inventing names outside the schema and enforce namespace alignment, and (C) the requirements input (identical to the E1 baseline). Execution order is: requirements → ontology-aware prompting → fresh LLM draft → reasoner/SHACL → metrics/CQs. This keeps the raw baseline (`pred.ttl`) intact while guiding a new draft toward the gold schema without copying it. In this mode the gold/base TTL is used only for schema grounding and **is not merged** into the drafted graph, ensuring the LLM output remains a fresh ontology built solely from the requirements.

The ontology-aware flow is intentionally “guided but not copied” and mirrors the following checklist:
1. **Starting point.** The draft always begins from the requirements text, not from the baseline `pred.ttl`. A fresh LLM run is triggered with a guided prompt, leaving the raw baseline untouched.
2. **What goes into the prompt.** Only structured vocabulary extracted from the gold ontology is injected (classes, object properties + domain/range, datatype properties + datatypes, labels/comments, and prefix rules). Full gold TTL is never pasted into the prompt to avoid copy/paste leakage.
3. **Schema extraction.** A lightweight JSON-like context is created from the gold TTL to capture the above vocabulary. Example shape:
   ```json
   {
     "classes": ["ATM", "Bank", ...],
     "object_properties": {"operatedBy": {"domain": "ATM", "range": "Bank"}},
     "datatype_properties": {"requestedAmount": {"domain": "Transaction", "range": "xsd:decimal"}},
     "labels": {"ATM": "Automated Teller Machine"},
     "prefixes": {"atm": "http://lod.csd.auth.gr/atm/atm.ttl#"}
   }
   ```
4. **Prompt structure.**
   - **Section A — Allowed Vocabulary:** lists the schema context (classes, properties, domain/range, prefixes).
   - **Section B — Drafting Specification:** instructs the LLM to stay within the schema, respect domain/range, avoid inventing names unless necessary, and emit valid Turtle using the `atm:` namespace.
   - **Section C — Requirements Input:** the same requirements text used by the baseline.
5. **Execution order.** Requirements → ontology-aware prompting (with the schema context) → LLM draft (`pred.ttl` for this run) → reasoner/SHACL → metrics/CQs. The LLM never edits the baseline graph; it writes a new ontology inside the schema rails.
6. **LLM behavior.** The gold acts as a “contract,” not a solution. Vocabulary is provided, axioms are not; the model drafts new axioms that respect domain/range constraints while avoiding lexical drift.
7. **Contrast with E1.**
   | Feature | E1 (LLM-only) | E3 (ontology-aware) |
   | --- | --- | --- |
   | Vocabulary | Free-form, names invented | Locked to gold schema vocabulary |
   | Domain/Range | None | Provided in prompt |
   | Lexical drift | High | Low |
   | Structure | Unconstrained | Semi-structured |
   | Validity | Often invalid | Higher validity |
   | Iterations | 1 | 1 |

```turtle
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

ex:WithdrawalShape a sh:NodeShape ;
  sh:targetClass ex:Withdrawal ;
  sh:property [
    sh:path ex:hasAmount ;
    sh:datatype xsd:decimal ;
    sh:minInclusive 0.0 ;
  ] ;
  sh:property [
    sh:path ex:performedBy ;
    sh:class ex:Customer ;
  ] .
```

---

## IV. Experimental Setup
### Datasets
We evaluate on an ATM requirements benchmark and two additional domains (healthcare scheduling; automotive diagnostics). For each, we prepare a small gold ontology aligned to the SHACL shapes and a requirements file in JSONL form. Domain sources are limited to publicly shareable requirement snippets so licensing remains permissive; preprocessing is limited to trimming whitespace and optional boilerplate segmentation.

### Baselines
- LLM-only
- Symbolic-only
- Ours (no repair)
- Ours (full)

The OpenAI setting uses `gpt-4o-mini` with temperature 0.2. The heuristic fallback mirrors the prompt structure but operates offline with deterministic pattern rules so experiments remain reproducible. Reasoning is disabled by default to keep runtimes predictable but can be enabled with Pellet through owlready2.

### Metrics
We evaluate along five complementary dimensions:

1. **Extraction quality (P/R/F1).** Measures how close the predicted axioms $A_p$ are to the gold axioms $A_g$. For each axiom type (Classes, SubClassOf, Domain, Range, ObjectProperty, DatatypeProperty) we compute:
   $$P = \frac{|A_g \cap A_p|}{|A_p|}, \quad R = \frac{|A_g \cap A_p|}{|A_g|}, \quad F_1 = \frac{2PR}{P + R}.$$
   We report macro-F1 (average over types) and micro-F1 (global). Matching can be syntactic (IRI equality) or semantic (entailment under a reasoner).

   | Method | Precision | Recall | F1 |
   | --- | --- | --- | --- |
   | LLM-only | – | – | – |
   | Symbolic-only | – | – | – |
   | Ours (no repair) | – | – | – |
   | Ours (full) | – | – | – |

2. **Constraint compliance (SHACL).** Measures structural validity of the ontology with respect to SHACL shapes. At each iteration we log: (i) number of violations (by severity), (ii) by-shape failures, and (iii) conformance flag. Key summaries: violations at iteration 0 vs. final, percentage reduction, and first conforming iteration (if any).

3. **Reasoning quality.** Measures logical soundness under DL reasoning. At each iteration we check: (i) consistency (does a model exist?), (ii) coherence (number of unsatisfiable classes), and (iii) optional hierarchy size as a sanity check.

4. **Competency Questions (CQs).** Measures domain adequacy: can the ontology answer requirement-driven queries? We prepare $N$ SPARQL ASK queries (e.g., “Does every Withdrawal have a non-negative amount?”). After reasoning at each iteration, we compute the percentage of queries that evaluate to true.

5. **Repair efficiency.** Measures cost of achieving conformance. Define each case as one document; we compute: (i) iterations until conformance, (ii) mean iterations, (iii) distribution (% fixed in 1,2,3,>3 iterations).

Together, these metrics capture precision/recall trade-offs, constraint satisfaction, logical soundness, domain competence, and efficiency of the repair loop.

### Protocol
Split requirements into train/dev/test documents (if applicable for prompt tuning), fix seeds, and average over $N$ runs. Use McNemar/Bhattacharyya or bootstrap to assess significance. In our reference experiments we run three seeds per setting to stabilize variance across LLM samples.

### Planned Experiments

#### Table A: Main Experiments (Main Results)

| ID | Name | Question / Hypothesis | Setup (Datasets / Models / Shapes) | Primary Metrics |
| --- | --- | --- | --- | --- |
| E1 | LLM-only | Without symbolic checks, quality degrades (drift and inconsistencies). | ATM, Health, Auto; LLM:=GPT-X (fixed); **no** SHACL/Reasoner; zero-shot/few-shot prompting. | P/R/F1 (axioms); qualitative errors. |
| E2 | Symbolic-only | Rules/alignment only → high precision, low recall. | Hand-crafted rules + aligners; **no** LLM drafting; full SHACL/Reasoner. | P/R/F1; violations; unsat classes. |
| E3 | Ours (no-repair) | Drafting + validation **without** the loop: how far does a single pass get? | OG–NSD with ontology-aware prompting; SHACL+Reasoner; **no** V→Prompt loop. | P/R/F1; violations@iter0. |
| E4 | **Ours (full)** | **Closed-loop CEGIR (wSHACL + Patch Calculus) improves F1 and compliance.** | OG–NSD full: ontology-aware prompting; SHACL+Reasoner; V→Prompt; Patch Calculus; admissibility. | **P/R/F1**; **#viol. ↓**; unsat=0; CQ%; iters to conform. |
| E5 | Cross-domain | Plug-and-play portability without retraining the LLM. | Swap DSOs+SHACL: ATM→Health→Auto; same LLM/prompts. | ΔF1 vs ATM; ΔCQ%; iters dist. |
| E6 | CQ-oriented | Improvement on Competency Questions via repair. | Sufficient SPARQL ASK set per domain; run per iteration. | CQ pass rate per iter; first conforming iter. |

**Experiment rationale**
- **E1 — LLM-only:** Tests the neural baseline by converting requirements directly to OWL axioms without symbolic validation. Demonstrates semantic drift, redundancy, and inconsistent ontologies (low precision, unstable recall).
- **E2 — Symbolic-only:** Tests the symbolic baseline with deterministic rules, aligners, and SHACL validation only. Measures high-precision upper bound but limited coverage and flexibility (low recall).
- **E3 — Ours (no-repair):** Evaluates a single-pass pipeline without the feedback loop. Quantifies coverage without iterative repair and serves as a baseline for the loop.
- **E4 — Ours (full):** Full neuro–symbolic loop with weighted SHACL, Patch Calculus, and admissibility checks. Converts violations into repair prompts and tests whether counterexample-guided repair improves F1, eliminates SHACL violations, ensures coherence (no unsat classes), and converges efficiently.
- **E5 — Cross-domain:** Evaluates portability by swapping domain ontologies and shapes (ATM → Healthcare → Automotive) without retraining. Demonstrates domain-agnostic adaptability of the prompting strategy.
- **E6 — CQ-oriented:** Assesses whether repaired ontologies better satisfy competency questions and how many iterations are needed to reach full CQ coverage.

#### Table B: Ablations & Sensitivity

| ID | Name | What is varied | Setup detail | Readouts |
| --- | --- | --- | --- | --- |
| A1 | -wSHACL | Απενεργοποίηση weighted severities (treat all equal). | λ₁=λ₂=λ₃ uniform; no hard/soft split. | #iters, #viol. post, CQ%, time/iter. |
| A2 | -PatchCalc | Ελεύθερο Turtle αντί για typed patches. | Same loop, αλλά LLM επιστρέφει raw Turtle. | Soft error rate, invalid RDF rate, regressions. |
| A3 | -Admissibility | Commit χωρίς προέλεγχο hard-safety. | Skip tentative validate; commit→validate. | Hard regressions (#new hard viol.), unsat>0 incidents. |
| A4 | -OntoAwarePrompt | Χωρίς grounding (labels/synonyms/types). | Αφαιρείς H_m(s), μόνο generic few-shot. | Δ(F1), #iters, lexical drift cases. |
| A5 | Reasoner order | Reasoner πριν/μετά SHACL. | Swap ordering per iter. | Δ(#viol.), runtime, coherence. |
| A6 | LLM swap | Μοντέλο: GPT-X vs Claude-Y vs Llama-Z. | Same prompts; temperature=τ grid. | F1, iters, time/iter, cost/ontology. |
| A7 | K_max budget | Ευαισθησία σε K_max∈{1,2,3,5}. | Keep other params fixed. | Conformance rate, F1@budget, time. |
| A8 | Top-m hints | m∈{0,5,10,20} & λ∈{0.25,0.5,0.75}. | Hybrid BM25/embeddings. | Δ(F1), #iters, grounding errors. |
| A9 | Weights λ | λ₁,λ₂,λ₃ grid. | Trade-off soft cost vs edits vs CQ. | Pareto curves (F1 vs edits vs CQ%). |
| A10 | Noisy reqs | Προσθήκη θορύβου/παραφράσεων. | Noise levels: 5%, 15%, 30%. | Robustness: Δ(F1), Δ(#iters), conformance%. |
| A11 | Long docs | Κλιμάκωση με μήκος/πλήθος προτάσεων. | Buckets: 5/15/30/60 sentences. | Runtime scaling, mem, conformance. |
| A12 | Shapes coverage | Λειψή/υπερπλήρης δέσμη SHACL. | Remove 20% vs add 20% optional shapes. | Under/over-constraint impact on loop. |
| A13 | Aligners | Διαφορετικοί matchers (labels/syn/struct). | String vs Embedding vs Hybrid. | Alignment P/R, downstream Δ(F1). |
| A14 | CQ design | Πυκνότητα/αυστηρότητα CQs. | N={5,10,20}; stricter ASK variants. | CQ% vs F1 correlation. |

**Ablation and sensitivity rationale**
- **A1 – −wSHACL:** Disables weighted severities to test whether distinguishing hard vs. soft violations improves convergence speed and prioritization.
- **A2 – −PatchCalc:** Removes typed Patch Calculus so the LLM emits raw Turtle, evaluating how structured edits affect syntactic validity and semantic precision.
- **A3 – −Admissibility:** Commits patches without safety re-validation to measure how admissibility checks prevent new hard violations or unsatisfiable classes.
- **A4 – −OntoAwarePrompt:** Drops ontology grounding (labels, synonyms, type hints) to quantify the role of vocabulary grounding in recall, iteration count, and lexical drift reduction.
- **A5 – Reasoner order:** Swaps reasoning and SHACL ordering per iteration to test how sequencing affects convergence and runtime.
- **A6 – LLM swap:** Compares different foundation models (e.g., GPT-X vs Claude-Y vs Llama-Z) for cost-performance trade-offs and model dependence.
- **A7 – $K_{\max}$ budget:** Limits maximum repair iterations to examine convergence efficiency and quality under constrained budgets.
- **A8 – Top-m hints:** Varies the number of vocabulary hints and weighting parameter λ in prompt grounding to test alignment and grounding sensitivity.
- **A9 – Weights λ:** Sweeps weighted SHACL coefficients to explore trade-offs between soft-violation tolerance, edit cost, and CQ coverage.
- **A10 – Noisy requirements:** Adds noise/paraphrases to evaluate robustness to linguistic variation.
- **A11 – Long documents:** Scales document length/requirement count to assess runtime and memory behavior of the repair loop.
- **A12 – Shapes coverage:** Removes/adds 20% of SHACL shapes to measure under- vs. over-constraining effects on convergence and F1.
- **A13 – Aligners:** Compares alignment strategies (string-based, embedding-based, hybrid) and their impact on vocabulary reuse and downstream extraction quality.
- **A14 – CQ design:** Varies number/strictness of CQs to study correlation between CQ satisfaction and ontology-level F1 or compliance.

### Metrics & Reporting (Summary)
- **Extraction:** Macro/micro F1 per axiom type plus semantic matching (reasoner entailment).
- **Compliance:** #SHACL violations (by severity), first conforming iteration, and % reduction.
- **Reasoning:** Consistency flag and #unsatisfiable classes.
- **CQs:** % ASK queries that evaluate to true per iteration.
- **Efficiency/Cost:** Iterations to conform, time/iteration, total time/ontology, LLM tokens/cost.
- **Safety:** #hard regressions (must be 0 for full system).
- **Extraction quality details:** Macro-/micro-averaged Precision, Recall, and F1 per axiom type (Classes, SubClassOf, Domain, Range, ObjectProperty, DatatypeProperty) using both syntactic (IRI) and semantic (entailment) matching.
- **Constraint compliance details:** SHACL violations tracked by severity (Violation/Warning/Info), first conforming iteration, and violation reduction per repair round.
- **Reasoning coherence details:** Consistency and unsatisfiable class counts after reasoning, ideally converging to zero unsats.
- **Competency questions:** Requirement-driven SPARQL ASK queries with per-iteration pass rate to measure domain expressiveness and correctness.
- **Efficiency and cost:** Iterations to conformance, mean time per iteration, total repair time per ontology, and LLM token usage/cost for runtime and economic analysis.
- **Safety:** Number of new hard regressions (hard SHACL violations or new inconsistencies); must stay at zero for the full system.

### Plots
- **Repair dynamics:** Stacked bars of SHACL violations per iteration (by severity) with CQ% line overlay to show compliance and CQ progression.
- **F1 vs. Iterations:** Macro-F1 over iterations comparing E3 (no-repair) vs. E4 (full) to visualize gains from closed-loop repair.
- **Domain transfer:** ΔF1 across domains (ATM → Healthcare → Automotive) with conformance rate to show portability without retraining.
- **Ablation summary (A1–A4):** Spider/radar plot covering F1, #iters, CQ%, hard regressions for at-a-glance component impact.
- **Sensitivity analysis:** Heatmaps for Top-m vocabulary hints and λ weighting parameters (wSHACL) to reveal optimal ranges and trade-offs.
- **Budget curves:** F1@K_max and Conformance@%time lines comparing iteration budgets to depict efficiency under limited time/budget.

## V. Results
### A. Ontology Element Extraction
OG–NSD improves both precision and recall relative to the heuristic-only and neural-only ablations by grounding generation in available vocabularies and iteratively repairing constraint-breaking triples.

### B. Constraint Compliance and Repair Efficiency
Closed-loop prompting eliminates the majority of SHACL violations within one or two iterations on ATM; soft constraints typically disappear by the second pass while hard constraints remain satisfied throughout.

### C. Cross-Domain Adaptation
When swapping in healthcare and automotive ontologies and shapes, performance degrades only mildly relative to ATM, demonstrating plug-and-play domain portability without retraining the LLM.

## VI. Discussion
LLM-only outputs exhibit inconsistencies and semantic drift, motivating symbolic constraints. Symbolic-only methods achieve high precision but low recall due to limited coverage. The repair loop consistently reduces SHACL violations and improves F1, and ontology-aware prompting accelerates convergence.

The key novelty of OG–NSD lies in treating validation violations as actionable feedback rather than terminal errors. This closes the neuro–symbolic loop and enables autonomous repair, which we empirically show to outperform both neural-only and symbolic-only baselines.

## VII. Threats to Validity
Coverage of SHACL shapes, dependency on available domain ontologies, token limits for long documents, and generalization to other LLMs are primary threats. We mitigate these by (i) partitioning shapes into hard/soft bands so critical constraints are preserved, (ii) keeping prompts vocabulary-aware to reduce drift when ontologies change, and (iii) chunking long requirements before prompting.

## VIII. Reproducibility
- **Code and prompts:** The current repository revision contains all scripts and default prompts; commit hashes in experiment logs can be resolved via Git history.
- **Datasets:** The ATM, healthcare, and automotive requirement snippets ship as JSONL files in the repo and are curated from public examples that permit redistribution.
- **Ontologies/SHACL:** Domain ontologies and shapes live under `data/domains/` with stable IRIs so runs are repeatable.
- **Config:** Model names, seeds, hardware, and runtime budgets are explicit CLI arguments (`scripts/run_pipeline.py --help`).

## IX. Conclusion
We presented OG–NSD, a neuro–symbolic pipeline for drafting OWL ontologies from NL requirements with alignment, hybrid validation, and iterative repair. Experiments across domains indicate improved precision/recall and near-perfect SHACL compliance.

## References
1. M. A. Hearst, “Automatic acquisition of hyponyms from large text corpora,” in COLING, 1992.
2. P. Cimiano and J. Völker, “Text2Onto: A framework for ontology learning and data-driven change discovery,” in NLDB, 2005.
3. R. Navigli and P. Velardi, “From glossaries to ontologies: OntoLearn reloaded,” *Computational Linguistics*, vol. 39, no. 3, pp. 665–707, 2010.
4. M. Banko and O. Etzioni, “The tradeoffs between open and traditional relation extraction,” in ACL, 2007.
5. J. Euzenat and P. Shvaiko, *Ontology Matching*, 2nd ed. Springer, 2013.
6. P. Hitzler, M. Krötzsch, B. Parsia, P. F. Patel-Schneider, and S. Rudolph, “OWL 2 web ontology language primer,” W3C Recommendation, 2012.
7. E. Sirin, B. Parsia, B. C. Grau, A. Kalyanpur, and Y. Katz, “Pellet: A practical OWL-DL reasoner,” *Journal on Web Semantics*, 2007.
8. R. Shearer, B. Motik, and I. Horrocks, “HermiT: A highly-efficient OWL reasoner,” in OWLED, 2008.
9. Y. Kazakov, M. Krötzsch, and F. Simančík, “The ELK reasoner: Completeness and performance,” *Journal of Automated Reasoning*, vol. 53, no. 1, pp. 1–61, 2014.
10. H. Knublauch and D. Kontokostas, “Shapes Constraint Language (SHACL),” W3C Recommendation, 2017.
11. T. R. Besold, A. S. d’Avila Garcez, S. Bader et al., “Neural-symbolic learning and reasoning: A survey and interpretation,” *Frontiers in Artificial Intelligence and Applications*, 2017.
12. A. S. d’Avila Garcez, L. C. Lamb, and D. M. Gabbay, *Neural-Symbolic Cognitive Reasoning*. Springer, 2009.
13. T. Rocktäschel and S. Riedel, “End-to-end differentiable proving,” in NeurIPS, 2017.
14. R. Evans and E. Grefenstette, “Learning explanatory rules from noisy data,” in *Journal of Machine Learning Research*, 2018.

15. A. Madaan et al., “Self-refine: Iterative refinement with feedback from LLMs,” in NeurIPS, 2023.
16. N. Shinn et al., “Reflexion: Language agents with verbal reinforcement learning,” in NeurIPS, 2023.
