# Agent instructions

Fair scheduling of review-panel meetings: which meeting each proposal goes to, in what order, and
which member is editor or reader. The use case is the panel of the Icelandic Technology
Development Fund (Tækniþróunarsjóður, TÞS). See `README.md`. The sister project on leave-order
fairness for anaesthetists is
[IDeLM-APAP](https://github.com/HI-IDN/IDeLM-APAP).

## Tooling split

* **Preprocessing and models in Python.** This covers data extraction and pseudonymisation
  (`code/data/`) and the optimisation models (`code/models/`, Gurobi).
* **Postprocessing and figures in R with ggplot2** (`code/*.R`, tidyverse). Don't make
  figures with matplotlib.
* **Data is stored as CSV.** The only exception is the parameter experiments
  (`code/run_experiments.py`), which collect their runs in `data/tdf/experiments/experiments.sqlite`.
* **Write-up is a Quarto book** in `docs/`, in Icelandic (HÍ theme `haskoli-islands-html`,
  pinned v0.2.0). Chapters source `docs/_setup.R`, which loads `code/panel_workload.R`; model
  figures come from `code/panel_schedule.R`. Code chunks are hidden; the "Kóði" page under
  *Viðaukar* links to the GitHub repository and describes its layout in plain Icelandic.
  Render with `quarto render` or `quarto preview` from `docs/`. The book reads model results from
  `docs/data/` (committed), which `code/export_docs_data.py` fills from `data/tdf/results/` with
  whitelisted, code-only columns; Gurobi logs are never committed (licence details). GitHub
  Actions renders `docs/` and publishes it to Pages on every push to `main`.
* **Objectives** are written with `\underbrace` labels on each term, followed by a plain-language
  explanation of each term.
* **Schedule model:** `code/models/panel_model.py` (Gurobi), settings in
  `code/models/panel_model.yml`. Held meetings are fixed through the `position` column of
  `panel.csv`. All scenarios of the book: `code/run_panel_scenarios.sh`; each agenda is checked with
  `models/check_agenda.py`. Results go to `data/tdf/results/` (gitignored).
* **Role model:** `code/models/role_model.py` (editor / reader 1 / reader 2).
* Python dependencies go in `requirements.txt` at the repo root.
* Run scripts from `code/`; paths are relative to it (`../data/...`).

## Data privacy (non-negotiable)

* **Never commit real names, initials, application numbers, titles or applicants.** Panel data is
  committed only as pseudonymised codes (`data/tdf/panel.csv`).
* `data/tdf/*` is gitignored except `panel.csv`. The raw extract, the pseudonym key
  (`panel_key.csv`), the manual corrections (`corrections.csv`), the member list, the PDFs, the
  figures, the results and the experiments stay local.
* Don't print or log real names. Work with codes and show real values only when the user asks
  for a specific lookup.
* New codes are assigned in random order, never alphabetically or by submission order.
* The repository is public: check every commit for real values before pushing.

## Git

* Work on a branch and merge to `main` through a pull request.

## Data layout

* `data/tdf/`: panel data. A local, gitignored one-off script (`code/data/tdf_panel_extractor.py`)
  turned the PDF exports into `panel.csv` (columns: application, meeting (M1, M2, ... in date
  order), coi, editor, reader1, reader2, position, readers_alphabetical, readers_missing). Applicants,
  titles, meeting names and dates are not in it. Fix cells the export truncated in `corrections.csv`,
  and record the agenda order of held meetings in `agenda.csv` (both gitignored), not by editing
  outputs.
