# Models for fair review-panel meetings

This folder holds the optimisation models behind the book in `docs/`, and the scripts that run
them. This README describes them on their own, so the code can be reviewed without the book.

## The problem

The review panel of the Icelandic Technology Development Fund (TÞS) meets about once a week during
a funding round. Each proposal is discussed once, by three panel members: an **editor** and two
**readers**. A member must attend every meeting where one of their proposals is on the agenda, and
may leave once the last of them has been discussed. Until then they sit through the proposals of
others: unpaid time, which this project calls **waiting**.

How proposals are spread over meetings, and the order within each meeting, decide how often each
member has to attend and how long they wait. The models make that fair. They are inspired by the
*Anesthetist's Peel Assignment Problem* (APAP,
[IDeLM-APAP](https://github.com/HI-IDN/IDeLM-APAP)), where a daily order decides which
anaesthetist goes home first. A meeting here plays the role of a day there, and a funding round
the role of a week.

Three decisions are involved:

1. **Who reviews which proposal**, and in which role (editor, reader 1 who speaks second, reader 2
   who speaks last).
2. **Which meeting** each proposal is discussed in.
3. **The order** within each meeting.

```mermaid
flowchart LR
  D["panel.csv<br/>(pseudonymised)"] --> S["panel_model.py<br/>2. meetings + 3. order"]
  S --> C["check_agenda.py<br/>rules hold?"]
  S --> R["role_model.py<br/>1. roles (after)"]
  R --> B["book (docs/)<br/>via export_docs_data.py"]
  C --> B
```

The reviewers of each proposal are taken as given (the staff's assignment). The schedule only
depends on *which three* members review a proposal, not on who of them is editor, so roles are
chosen afterwards. `role_model.py --mode assign` can also choose the reviewers themselves, for the
what-if of chapter 7 of the book.

## Data

`../data/tdf/panel.csv` is the only data in the repository. It is pseudonymised: members are codes
`R01`–`R21`, proposals `A001`–…, meetings `M1`–`M9` in date order, all assigned in random order.
One row per proposal:

| Column | Meaning |
|---|---|
| `application` | proposal code |
| `meeting` | meeting in the staff's current plan (empty: not yet placed) |
| `coi` | members with a conflict of interest, separated by `;` |
| `editor`, `reader1`, `reader2` | the three reviewers |
| `position` | slot on the agenda, for meetings that have already been held |
| `readers_alphabetical`, `readers_missing` | data-quality flags from the extraction |

`../data/tdf/members.csv` (`member`, `new`) marks new members. It stays local (gitignored), like
everything else in `data/tdf/` except `panel.csv`. Real names never enter the code or the data.

## The schedule model (`models/panel_model.py`)

A mixed-integer program, solved with Gurobi.

**Decision variables**

| Variable | Meaning |
|---|---|
| `x[p, m, k]` | proposal *p* is discussed in meeting *m* as number *k* |
| `a[r, m]` | member *r* attends meeting *m* |
| `leave[r, m]` | slot after which *r* may leave *m* (the slot of their last proposal; 0 if absent) |
| `z` | the largest burden of any member (for the fairness step) |

Variables exist only where they can be nonzero: a proposal of a held meeting has only its known
slot, a meeting has only as many slots as proposals that may go there, and `a`, `leave` exist only
for meetings a member can have a proposal in. Meetings a member cannot attend are left out of the
sets rather than forbidden by constraints.

**Measures**, per member over the round:

* *waiting* = slots sat through minus own proposals = proposals of others sat through;
* *meetings* = meetings attended;
* *burden* = α × meetings + waiting. α (in slots) says how much one meeting attended weighs against
  waiting; the chosen value is α = 2.

**Rules (constraints)**

| Rule | Hard or soft |
|---|---|
| Each proposal is discussed once; one proposal per slot; no gaps in an agenda | hard |
| Held meetings stay exactly as they were | hard |
| Nothing is added to the next, announced meeting (`--next-meeting M3`); its proposals may be postponed at a cost | hard / cost `postpone_penalty` |
| In the first meeting everyone attends with exactly one proposal (when it is still open) | hard |
| A member has at most `max_per_member` = 5 own proposals in a meeting not yet held | hard |
| … and preferably at most `soft_max_per_member` = 4 | cost `soft_max_weight` per extra proposal |
| Own proposals per meeting close to a target (3.5 experienced, 2.5 new) | cost `target_weight` |
| A member with a conflict of interest has left before that proposal comes up | cost `coi_penalty` each time not |
| Optional rotation (`--rotate-wait`): the members of the last proposal of a meeting leave early at the next meeting, or (`-1`) skip it | hard, experimental |

**Objective.** `--fairness` selects it. The recommended one is solved in steps, each holding what
the steps before reached (`lexburden`):

1. **Fewest meetings attended**, with the own proposals per meeting close to the targets and the
   costs above (conflicts, postponements, soft cap).
2. **The smallest largest burden**: minimise `z` with α × meetings + waiting ≤ `z` for every
   member. Members who attend often thus wait less, and nobody else waits more than necessary.
3. **The least total waiting**, with a tiny reward for new members waiting early in the round,
   when they sit longer to learn anyway.

The time limit is split 40 % for step 1 and the rest equally over the other steps. Other modes
are kept for comparison: `lexsum` (steps 1 and 3 only: the plan with least total waiting, to show
the price of fairness), `lexmax` (step 2 on waiting alone), `lex` and `lexboth` (APAP-style equity
bands on waiting per meeting), and the single-objective `proposal` (the book's original: least
burden per proposal for the worst-off member), `total`, `unpaid`, `bands` and `sum`.

**Solving.** Open meetings with the same candidate proposals are interchangeable, so symmetry is
broken by ordering them by their first proposal (off when meeting order matters, e.g. rotation).
A member with *j* own proposals in a meeting cannot leave before slot *j*, which strengthens the
bounds. `--start` warm-starts from an earlier agenda (reordered to respect the symmetry rule).
Even so, the gap is rarely closed within an hour for the scenarios that move proposals between
meetings: the solutions are the best found, not proven optimal. Splitting the problem in two
(meetings first, then the order within each meeting, like one APAP day) is the next step.

**Output** (`--out <prefix>`): `<prefix>_agenda.csv` (meeting, position, application),
`<prefix>_members.csv` (per member: proposals, meetings, slots, waiting, burden) and
`<prefix>_coi_present.csv`. The log prints the value and bound of each step.

## The role model (`models/role_model.py`)

Given an agenda, chooses for each proposal who of its three reviewers is editor and who is
reader 1 (`--mode roles`), or all three reviewers and the editor (`--mode assign`).

* **Pay** is a base fee plus 23 000 ISK per editor role and 15 000 ISK per reader role. In `roles`
  mode the spread of pay among experienced members is minimised, per proposal by default.
  Waiting is unpaid, and `--pay-per` can reward it with editor roles: per slot sat through
  (`presence`), per proposal plus waiting above the regression curve of waiting on meetings
  (`fit`), or, recommended, pay per proposal rising in proportion to how far a member's waiting
  per proposal is above the mean (`mean`: 50 % above the mean, 50 % more per proposal).
* **Limits**: nobody is editor on more than 2/3 of their proposals (`max_editor_share`); new
  members are not editor before the midpoint of their meetings and then on at most 15 %
  (`new_editor_share`); in `assign` mode at most two new members review a proposal.
* **Settled roles** are kept: held meetings always, and announced ones with `--keep-roles M3`.
* **Room in the discussion**: the editor takes 3 parts, reader 1 2 and reader 2 1; with a smaller
  weight, the spread of room per proposal over members is kept small.

Output: `<prefix>_panel.csv`, in the format of `panel.csv`, so it can be scheduled in turn.

## Checking (`models/check_agenda.py`)

Checks an agenda against the rules of its scenario, independently of the model: held meetings as
they were, closed meetings as planned, nothing added to the next meeting, per-member limits.
`run_panel_scenarios.sh` runs it after every schedule.

## Running

Requires Python 3.10+ with `requirements.txt` and a Gurobi licence (an academic licence is free;
the pip wheel's trial licence is too small). From `code/`:

```bash
bash run_panel_scenarios.sh            # all scenarios, results in ../data/tdf/results/
python export_docs_data.py             # pseudonymised copies the book reads (../docs/data/)
```

`run_panel_scenarios.sh` takes environment variables: `RESULTS` (results folder), `MODEL_OPTIONS`
(extra options for every schedule run) and `ONLY` (scenario names to run). The final runs of
1 October 2026 used

```bash
RESULTS=../data/tdf/results/final \
MODEL_OPTIONS="--fairness lexburden --alpha 2 --postpone-penalty 3" bash run_panel_scenarios.sh
```

| Scenario | What is free |
|---|---|
| `current` | the staff's meetings; only the order within each meeting |
| `free` | the next meeting (M3) is announced; later meetings are re-planned |
| `free_sum` | as `free`, without the fairness step (least total waiting, for comparison) |
| `free_max4` | as `free`, at most 4 own proposals per meeting |
| `scratch` | the whole round from the start, nothing fixed |
| `roles`, `roles_presence`, `roles_presence_free` | roles on the staff's meetings or on `free` |
| `assign`, `assign_schedule` | reviewers chosen from scratch, then meetings and order for them |

Each schedule starts from the solution of the one before (`--start`). Gurobi logs are written next
to the results and are never committed (they contain licence details).

## Settings (`models/panel_model.yml`)

Read by both models and shown as a table in the book; command-line options override them.

| Setting | Value | Meaning |
|---|---|---|
| `alpha` | 2 | cost of attending a meeting, in slots (chosen from an experiment with 0–4) |
| `max_per_meeting` | 15 | most proposals in a meeting |
| `max_per_member` / `soft_max_per_member` | 5 / 4 | hard limit and soft cap on own proposals in a meeting |
| `soft_max_weight` | 0.5 | cost per proposal above the soft cap |
| `coi_penalty` | 1 | cost each time a conflicted member is present |
| `postpone_penalty` | 0.5 (final runs: 3) | cost of postponing an announced proposal |
| `target_experienced` / `target_new` | 3.5 / 2.5 | target own proposals per meeting |
| `new_editor_share`, `max_editor_share`, `max_new_per_proposal` | 0.15, 2/3, 2 | role limits |
| `time_limit` | 600 s | default time limit |

`run_experiments.py` collects parameter experiments in a local SQLite file
(`../data/tdf/experiments/`).
