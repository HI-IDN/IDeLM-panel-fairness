# Shared setup for all chapters: load the plotting functions and the pseudonymised panel data.
source("../code/panel_workload.R", chdir = TRUE)
panel <- read_panel("../data/tdf/panel.csv")
load_new_members("data/members.csv")
counts <- role_counts(panel)
members <- member_table(counts)
spread <- spread_table(members)
attendance <- attendance_table(panel)
n_meetings <- nlevels(panel$meeting)
