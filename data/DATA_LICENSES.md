# Data licenses and redistribution checklist

This file is **not legal advice**. It is an internal checklist so manuscript + repository claims stay aligned with upstream terms.

## Principles for this project

1. **Requirements JSONL** under `data/requirements/` are **curated derivatives** (normalized `{title, text}`). They must not reproduce large verbatim chunks of upstream copyrighted text without permission and attribution where required.
2. **Gold TTL, SHACL, CQs** are **author-created** artifacts for evaluation; license them explicitly (e.g. same as repo `LICENSE` or a `data/LICENSE` block) so redistribution is clear.
3. **Provenance honesty**: if health text is generic workflow language inspired by public documentation (not rows from MIMIC), say that in the paper—do not imply credentialed patient data were copied into the repo.

## Per-domain matrix (current design)

| Domain | Upstream anchor (provenance) | Redistribution / use notes | Action before journal submission |
|--------|------------------------------|----------------------------|-----------------------------------|
| ATM | Toronto CSC340 ATM PDF | License on the PDF is **not clearly stated** in-repo. | Confirm with host institution or **replace** corpus with fully original synthetic banking requirements under your chosen license. |
| Health | MIMIC-IV / MIMIC-IV-ED (PhysioNet) | **Credentialed access** applies to the databases, not necessarily to short derived NL—but PhysioNet **data use agreements** still matter for how you describe reuse. In-repo text contains **no patient identifiers**. | Align manuscript wording with **actual construction** (documentation-inspired abstraction vs chart-level derivation). Keep **no PHI** guarantee. |
| Retail | UCI Online Retail (ID 352), **CC BY 4.0** | Attribute UCI/dataset authors in paper + repo; respect **BY** (credit) and license compatibility for derivatives. | Add citation block + retain `registry.json` `source`/`license` fields; ensure gold/shapes license is stated. |

## Repository checklist (fill before submission)

- [ ] Every `primary_datasets[]` entry in `data/registry.json` has **source URL**, **license string**, **version or freeze date**, **construction_notes** matching the manuscript.
- [ ] Paper **Data Availability** / **Ethics** sections match: no claim of MIMIC row release if none exists; no ATM verbatim republication if not cleared.
- [ ] Third-party **CC BY** attribution text for Retail (and any other CC-licensed anchor) is in the paper appendix or footnote.
- [ ] If you ship a **“new”** corpus: bump `version` in `registry.json`, update `DATA_PROVENANCE.md` §4, and archive a checksum or tag in git.

## “New and legally clean” options (recommended directions)

1. **Fully synthetic requirements** (your team authors all NL + ontology): simplest chain—license the bundle as **CC0** or your repo license and cite no restrictive upstream.
2. **Only openly licensed anchors**: e.g. specifications under known **CC BY / Apache 2.0 / OGL** (verify each document); extract *short* requirements with attribution.
3. **Replace ATM anchor** if Toronto PDF terms stay unclear: use a banking-SRS substitute with explicit license or synthetic ATM network requirements.

## Where counts and paths are recorded

- Machine-readable: `data/registry.json`
- Human-readable steps: `data/DATA_PROVENANCE.md`
