# LaTeX sources

- **`workshop/`** — ACM `sigconf` draft (`main.tex`, `sections/`, `references.bib`).
- **`journal/`** — IEEEtran-style long version skeleton (`main.tex`, `sections/`).

Build outputs (`*.aux`, `*.log`, `out/`) should not be committed. Example with `latexmk` from either subfolder:

```bash
cd paper/workshop
latexmk -pdf -interaction=nonstopmode -outdir=build main.tex
```

On Windows, use the same command from PowerShell if `latexmk` is on `PATH`.
