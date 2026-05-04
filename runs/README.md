# Experiment outputs (`runs/`)

This directory holds **generated** artefacts from the experiment scripts (E1–E6, journal layers, ablations, etc.). It is intentionally **empty in a fresh clone**; runners recreate subfolders as needed.

Suggested layout (examples):

- `runs/E1_llm_only/`, `runs/E4_full/`, … — per-experiment roots from config `output_root`
- `runs/journal/` — journal protocol runs (`E-BASE-*`, `E-DIAG-*`, …)
- `runs/journal_tables/`, `runs/journal_plots/` — aggregated CSV/JSON/plots from `build_journal_*` scripts
- `runs/reproducibility/freeze_*` — snapshots from `run_execution_plan.py`
- `runs/must_*`, `runs/stability_core/`, `runs/ablation_matrix/` — MUST-pass and matrix tooling

Do not commit large run folders to Git unless you explicitly want frozen artefacts in version control.
