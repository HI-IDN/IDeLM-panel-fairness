# Fair scheduling of review-panel meetings

Optimisation models for scheduling the meetings of a grant review panel fairly.

A review panel discusses proposals one at a time. Each proposal has three panel members, one
*editor* and two *readers*, and a member may leave a meeting once all of their own proposals have
been discussed. Members whose proposals come last sit through the whole meeting, meeting after
meeting. A single meeting can't be fair to everyone, but the schedule over a whole review round
can be.

The models decide three things:

1. **Roles:** who is editor, reader 1 and reader 2 on each proposal, so that workload, editor roles
   and pay are balanced, and new members edit later and less.
2. **Meetings:** which meeting each proposal goes to.
3. **Order:** the order within each meeting, so that nobody waits much longer than others.

Fairness has two parts: how many meetings a member has to attend, and how long they wait at each
one (the proposals of others they sit through, *peel-off points*). A member who has to attend often
should be allowed to leave early. Meetings already held are fixed, conflicts of interest are
respected, and the next meeting's announced agenda can only be postponed, not added to.

The models are mixed-integer programs solved with Gurobi.

## Use case: the Icelandic Technology Development Fund

The use case is the review panel of the Icelandic Technology Development Fund
(Tækniþróunarsjóður, run by [Rannís](https://www.rannis.is)) for the 2026 round. The write-up is
an Icelandic Quarto book, published at <https://hi-idn.github.io/IDeLM-panel-fairness/>: a proof
of concept for a student summer project that could put the models into operation.

All panel data in this repository is pseudonymised (see *Data privacy*).

## Related work

This project is a companion to
[IDeLM-APAP](https://github.com/HI-IDN/IDeLM-APAP),
the *Anesthetist's Peel Assignment Problem*: sharing out fairly which anaesthetist goes home first
each day. Both are about the order in which a group is released from a shared workload.

## Repository layout

```
code/
  models/
    panel_model.py     meetings and order (Gurobi); settings in panel_model.yml
    role_model.py      editor / reader roles, or a full assignment from scratch
    check_agenda.py    checks an agenda against the rules
  scripts/                run_panel_scenarios.sh (all scenarios of the book), run_round.py (a round from a YAML file)
  run_experiments.py      parameter experiments (results in data/tdf/experiments/)
  export_docs_data.py     copies the results the book needs into docs/data/
  panel_palette.R         colours of all figures (Okabe-Ito and viridis)
  panel_workload.R        data figures and tables (ggplot2)
  panel_schedule.R        model figures and tables (ggplot2)
data/
  tdf/panel.csv        pseudonymised panel data, one row per proposal
docs/                  Quarto book (Icelandic), published to GitHub Pages
  data/                pseudonymised model results the book reads (from export_docs_data.py)
requirements.txt
```

## Getting started

Requires Python 3.10+, R with the tidyverse, Quarto and a [Gurobi](https://www.gurobi.com)
licence. Academic licences are free; the `gurobipy` pip package comes with a size-limited trial
licence that is too small for the full instance.

```bash
pip install -r requirements.txt
cd code
bash scripts/run_panel_scenarios.sh    # solve all scenarios (results in data/tdf/results/)
python export_docs_data.py     # pseudonymised copies for the book (docs/data/)
cd ../docs
quarto render                  # build the book (GitHub Actions does this on push to main)
```

## Data privacy

Real names, initials, application numbers and titles are never committed. Panel members and
proposals appear only as random codes (R01…, A001…), assigned in random order, and meetings as
M1…M9 in date order. Applicants, meeting names and dates are left out.
The code-to-name key, the raw extracts and all model results stay on the local machine.

## Roadmap

* Pairing members to proposals with their stated preferences, jointly with the schedule.
* Members' own preferences for how many proposals they take per meeting.
* An open-source solver (e.g. SCIP or HiGHS), so the tool can be used outside academia.

## License

GPL-3.0, see [LICENSE](LICENSE).
