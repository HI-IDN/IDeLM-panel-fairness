"""
Lower bounds on the burdens of a scenario, one member at a time.

For each member r, the schedule model of the scenario (the same options as models.panel_model) is
solved with only r's unpaid burden (alpha per meeting attended plus waiting) as the objective. The
bound Gurobi proves, LB[r], holds for r in every plan the rules allow. So in any plan the largest
burden is at least max LB[r], and the sum of the k largest burdens at least the sum of the k largest
LB[r]. These are often far stronger than the bound of the leximin steps, where Gurobi has to bound
the largest burden of all members at once.

Run from code/, with the options of the scenario, e.g. for scenario 2:
    python lower_bounds.py ../data/tdf/panel.csv --next-meeting M3 --fairness leximin \
        --time-limit 180 --out ../data/tdf/results/bounds/free
--time-limit is per member. Writes <out>_bounds.csv (member, bound, best, gap).
"""
import csv
import os
import sys

from gurobipy import GRB

from models import panel_model


def solve_bounds(self):
    rows = []
    time_limit = self.m.Params.TimeLimit
    self.m.Params.MIPFocus = 3  # the bound is what counts here
    for r in self.data.members:
        self.m.setObjective(self.unpaid(r, carry=False), GRB.MINIMIZE)
        self.m.Params.TimeLimit = time_limit
        self.m.optimize()
        best = self.m.ObjVal if self.m.SolCount else float('nan')
        rows.append({'member': r, 'bound': round(self.m.ObjBound, 3), 'best': round(best, 3),
                     'gap': round(self.m.MIPGap, 3) if self.m.SolCount else ''})
        print(f"bound {r}: {self.m.ObjBound:.2f} (best plan for {r} alone {best:.2f})")
    out = OUT + '_bounds.csv'
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    with open(out, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['member', 'bound', 'best', 'gap'])
        writer.writeheader()
        writer.writerows(rows)
    bounds = sorted((row['bound'] for row in rows), reverse=True)
    print('lower bounds on the k largest burdens: '
          + ', '.join(f'top{k} {sum(bounds[:k]):.2f}' for k in (1, 2, 3)))
    sys.exit(0)


OUT = sys.argv[sys.argv.index('--out') + 1]
panel_model.PanelScheduleModel.solve = solve_bounds

if __name__ == '__main__':
    panel_model.main()
