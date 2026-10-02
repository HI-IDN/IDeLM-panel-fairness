# Review-panel meetings: who waits how long, and how schedules compare.
#
# Works on the pseudonymised panel.csv (agenda positions of held meetings) and on the output of
# models/panel_model.py (<prefix>_agenda.csv and <prefix>_members.csv). Sourced by the book in
# docs/; uses the helpers and theme from panel_workload.R.
library(tidyverse)

# Scenarios: result file prefix -> label, in the order they are compared.
scenarios <- c(current = "1. Tillaga starfsmanna, sanngjörn röð",
               free = "2a. Næsti fundur festur, restin bestuð",
               free_sum = "2b. Eins og 2a, án sanngirnisþreps",
               free_leximin = "2c. Eins og 2a, leximin",
               free_noworse = "2d. Eins og 2c, enginn verr settur en í 1",
               free_max4 = "3. Eins og 2a, mest 4 á fund",
               scratch = "4. Bestað frá byrjun")
scenario_colours <- setNames(c("#eb6834", "#2a78d6", "#8fb8ea", "#1f4f8f", "#e87ba4", "#1baf7a",
                               "#4a3aa7"), scenarios)

# Held meetings with a known agenda: per member, own proposals, slot of their last proposal (when
# they may leave) and how many proposals of others they sat through before that.
held_meetings <- function(panel) {
  held <- panel %>% filter(!is.na(position)) %>% mutate(position = as.integer(position))
  length <- held %>% count(meeting, name = "length")
  held %>%
    pivot_longer(all_of(names(role_labels)), names_to = "role", values_to = "member") %>%
    filter(!is.na(member)) %>%
    group_by(meeting, member) %>%
    summarise(own = n(), leave = max(position), .groups = "drop") %>%
    mutate(waiting = leave - own) %>%
    left_join(length, by = "meeting")
}

plot_held <- function(panel) {
  held <- held_meetings(panel)
  meetings <- sort(unique(as.character(held$meeting)))
  members <- sort(unique(held$member))
  # Running peel-off points: proposals of others sat through, summed over the held meetings so
  # far. Members who didn't attend a meeting keep their total from before.
  running <- expand_grid(meeting = meetings, member = members) %>%
    left_join(held %>% mutate(meeting = as.character(meeting)), by = c("meeting", "member")) %>%
    arrange(member, meeting) %>%
    group_by(member) %>%
    mutate(cumulative = cumsum(coalesce(waiting, 0L))) %>%
    group_by(meeting) %>%
    mutate(length = max(length, na.rm = TRUE)) %>%
    ungroup()
  # Each own proposal at its actual slot on the agenda.
  slots <- panel %>%
    filter(!is.na(position)) %>%
    mutate(position = as.integer(position), meeting = as.character(meeting)) %>%
    pivot_longer(all_of(names(role_labels)), values_to = "member") %>%
    filter(!is.na(member)) %>%
    select(meeting, member, position)
  # Sort members within each meeting by when they could leave; absent members at the bottom.
  # Factor levels run bottom to top: absent members first, then by leaving slot.
  key <- running %>% arrange(meeting, !is.na(leave), leave, cumulative) %>%
    mutate(row = paste(meeting, member, sep = "_"))
  running <- running %>% mutate(row = factor(paste(meeting, member, sep = "_"), levels = key$row))
  slots <- slots %>% mutate(row = factor(paste(meeting, member, sep = "_"), levels = levels(running$row)))
  present <- filter(running, !is.na(leave))
  max_cum <- max(running$cumulative)

  # One panel per meeting, each as wide as its meeting plus one slot for the running total, so the
  # x axes share one scale (e.g. 7/20 and 13/20 of the width for meetings of 6 and 12 proposals).
  panel_for <- function(mt) {
    keep <- function(d) filter(d, meeting == mt)
    n <- max(keep(running)$length)
    ggplot(keep(running), aes(y = row)) +
      geom_blank() +
      geom_segment(data = keep(present), aes(x = 0, xend = leave, yend = row), colour = "grey80",
                   linewidth = 2.5) +
      geom_tile(data = keep(slots), aes(x = position - 0.5, y = row), width = 0.9, height = 0.55,
                fill = role_colours[["Editor"]]) +
      geom_vline(xintercept = n, linetype = "dashed", colour = "black") +
      # Running total in the extra slot to the right of the end of the meeting.
      geom_tile(aes(x = n + 0.5, fill = cumulative), width = 0.9, height = 0.85) +
      geom_text(aes(x = n + 0.5, label = cumulative, colour = cumulative > max_cum / 2), size = 3) +
      scale_fill_viridis_c(option = "magma", direction = -1, begin = 0.2, end = 0.95,
                           limits = c(0, max_cum), name = "Uppsafnaðir biðpunktar") +
      scale_colour_manual(values = c(`TRUE` = "white", `FALSE` = "black"), guide = "none") +
      scale_y_discrete(labels = function(x) sub(".*_", "", x), drop = TRUE) +
      scale_x_continuous(breaks = seq(0, n, 2), limits = c(0, n + 1), expand = c(0, 0)) +
      labs(subtitle = mt, x = NULL, y = NULL) +
      theme_panel +
      theme(panel.grid.major.x = element_line(colour = "grey92"), legend.position = "none",
            plot.subtitle = element_text(hjust = 0.5))
  }
  panels <- lapply(meetings, panel_for)
  widths <- sapply(meetings, function(mt) max(running$length[running$meeting == mt]) + 1)

  legend <- cowplot::get_plot_component(
    panels[[1]] + theme(legend.position = "bottom", legend.key.width = unit(40, "pt"),
                        legend.title.position = "top"),
    "guide-box-bottom", return_all = TRUE)
  title <- cowplot::ggdraw() +
    cowplot::draw_label("Hvenær fagráðsmenn gátu farið af fundum sem eru búnir", x = 0.01, hjust = 0,
                        y = 0.82, size = 14) +
    cowplot::draw_label(paste0("Grá lína = tími á fundinum; blátt = eigin umsóknir; brotalína = fundarlok.
",
                               "Hægra megin: uppsafnaðir biðpunktar (umsóknir annarra sem setið var undir)"),
                        x = 0.01, hjust = 0, y = 0.35, size = 11)
  body <- cowplot::plot_grid(plotlist = panels, nrow = 1, rel_widths = widths, align = "h", axis = "tb")
  axis <- cowplot::ggdraw() + cowplot::draw_label("Dagskrárliður (umsóknir teknar fyrir)", size = 11)
  cowplot::plot_grid(title, body, axis, legend, ncol = 1, rel_heights = c(0.16, 1, 0.05, 0.12))
}

# The panel as scheduled by a model run: meetings (and agenda positions) from <prefix>_agenda.csv,
# so the data-chapter figures can be drawn for a model schedule too.
panel_from_agenda <- function(panel, agenda_file) {
  agenda <- read_csv(agenda_file, col_types = cols(.default = "c"))
  meetings <- unique(agenda$meeting)
  meetings <- meetings[order(as.integer(sub("M", "", meetings)))]
  panel %>%
    select(-meeting, -position) %>%
    left_join(agenda, by = "application") %>%
    mutate(meeting = factor(meeting, levels = meetings))
}

# Largest number of own proposals one member has in one meeting.
max_own_per_meeting <- function(panel) max(meeting_counts(panel)$n)

read_members <- function(prefix, scenario) {
  read_csv(paste0(prefix, "_members.csv"), show_col_types = FALSE) %>% mutate(scenario = scenario)
}

# Read every scenario that has results, as one data frame with a scenario column.
read_scenarios <- function(results) {
  available <- names(scenarios)[file.exists(file.path(results, paste0(names(scenarios), "_members.csv")))]
  bind_rows(lapply(available, function(s) read_members(file.path(results, s), scenarios[[s]]))) %>%
    mutate(scenario = factor(scenario, levels = scenarios))
}

# Times a conflicted member is present when that proposal is discussed, per scenario.
read_coi_present <- function(results) {
  available <- names(scenarios)[file.exists(file.path(results, paste0(names(scenarios), "_coi_present.csv")))]
  counts <- sapply(available, function(s)
    nrow(read_csv(file.path(results, paste0(s, "_coi_present.csv")), show_col_types = FALSE)))
  setNames(counts, scenarios[available])
}

# One value per member and scenario as a table of coloured cells: members in rows (sorted by the
# first scenario), scenarios in columns (by number), the value written in each cell.
plot_compare <- function(runs, value, title, fill_label, digits = 0) {
  runs <- droplevels(runs) %>% mutate(v = .data[[value]])
  order <- runs %>% filter(scenario == levels(scenario)[1]) %>% arrange(v) %>% pull(member)
  # A "Samtals" row at the bottom (the first level is drawn lowest) with each scenario's total.
  runs <- runs %>%
    mutate(member = factor(member, levels = c("Samtals", order)),
           number = factor(sub("[.].*", "", scenario), levels = sub("[.].*", "", levels(scenario))))
  totals <- runs %>% group_by(number) %>% summarise(v = sum(v), .groups = "drop") %>%
    mutate(member = factor("Samtals", levels = levels(runs$member)))
  # Distinct colour steps rather than a smooth gradient, so neighbouring values are easy to tell
  # apart, blue (low) to red (high): one colour per value for a few whole numbers (meetings), otherwise binned.
  few_values <- all(runs$v == round(runs$v)) && n_distinct(runs$v) <= 9
  if (few_values) {
    runs <- runs %>% mutate(fill = factor(v, levels = sort(unique(v))))
    fill_scale <- scale_fill_brewer(palette = "RdBu", direction = -1, name = fill_label, guide = guide_legend(reverse = TRUE))
  } else {
    runs <- runs %>% mutate(fill = v)
    fill_scale <- scale_fill_fermenter(palette = "RdBu", direction = -1, n.breaks = 7, name = fill_label)
  }
  ggplot(runs, aes(x = number, y = member, fill = fill)) +
    geom_tile(colour = "white", linewidth = 0.8) +
    geom_text(aes(label = format(round(v, digits), nsmall = digits, decimal.mark = ","),
                  colour = abs(v - (min(v) + max(v)) / 2) > 0.4 * (max(v) - min(v))), size = 3) +
    geom_tile(data = totals, aes(x = number, y = member), inherit.aes = FALSE,
              fill = "grey92", colour = "white", linewidth = 0.8) +
    geom_text(data = totals, aes(x = number, y = member, label = format(round(v, digits), nsmall = digits,
                                                                      decimal.mark = ",")),
              inherit.aes = FALSE, size = 3, fontface = "bold") +
    fill_scale +
    scale_colour_manual(values = c(`TRUE` = "white", `FALSE` = "black"), guide = "none") +
    scale_x_discrete(position = "top") +
    scale_y_discrete(limits = levels(runs$member)) +
    labs(title = title, x = "Sviðsmynd", y = NULL) +
    theme_panel +
    theme(panel.grid = element_blank(), legend.position = "right")
}

summary_table <- function(runs) {
  runs %>%
    group_by(Sviðsmynd = droplevels(scenario)) %>%
    summarise(`Mesta byrði` = max(burden),
              `Fundir samtals` = sum(meetings),
              `Fundir sem mætt er á (bil)` = sprintf("%d–%d", min(meetings), max(meetings)),
              `Biðpunktar samtals` = sum(waiting),
              `Fylgni funda og biðar` = cor(meetings, waiting, method = "spearman"),
              .groups = "drop")
}

# Solver time (minutes) and final gap (%) per scenario. The Gurobi logs stay local (they hold
# licence details); code/export_docs_data.py summarises them in solver.csv.
read_solver_info <- function(results) {
  solver_file <- file.path(results, "solver.csv")
  if (!file.exists(solver_file)) {
    return(tibble(scenario = factor(), minutes = numeric(), total_minutes = numeric(), limit_minutes = numeric(),
                  gap = numeric()))
  }
  solver <- read_csv(solver_file, show_col_types = FALSE) %>% filter(scenario %in% names(scenarios))
  # Older summaries have no time limit; take it from the run script instead.
  if (!"limit_minutes" %in% names(solver)) {
    limits <- script_time_limits()
    solver$limit_minutes <- if (length(limits)) unname(limits[solver$scenario]) else NA_real_
  }
  # Each run starts from the solution of another (--start), so its own time understates the work behind
  # it: add the time of every run in its chain.
  starts <- script_starts()
  own <- setNames(solver$minutes, solver$scenario)
  chain_minutes <- function(s) {
    total <- 0
    while (!is.na(s) && s %in% names(own)) {
      total <- total + own[[s]]
      s <- if (s %in% names(starts)) starts[[s]] else NA
    }
    total
  }
  solver$total_minutes <- sapply(solver$scenario, chain_minutes)
  # A run chosen by hand (see export_docs_data.py) carries the minutes of the runs it was started from.
  if ("prior_minutes" %in% names(solver)) {
    solver$total_minutes <- ifelse(is.na(solver$prior_minutes), solver$total_minutes,
                                   solver$minutes + solver$prior_minutes)
  }
  solver %>%
    transmute(scenario = factor(unlist(scenarios[scenario]), levels = unlist(scenarios)), minutes,
              total_minutes, limit_minutes = as.numeric(limit_minutes), gap)
}

# Lines of run_panel_scenarios.sh, with continued lines (ending in a backslash) joined.
script_lines <- function(script = run_script) {
  if (!file.exists(script)) return(character())
  strsplit(gsub("\\\\\n\\s*", " ", paste(readLines(script), collapse = "\n")), "\n")[[1]]
}

# The run each run of run_panel_scenarios.sh starts from: "run <name> ... --start "$R/<from>_agenda.csv"".
script_starts <- function(script = run_script) {
  lines <- script_lines(script)
  runs <- regmatches(lines, regexec('^\\s*(?:PANEL=\\S+ )?run (\\w+) .*--start "?\\$R/(\\w+)_agenda\\.csv', lines, perl = TRUE))
  runs <- Filter(length, runs)
  setNames(sapply(runs, `[`, 3), sapply(runs, `[`, 2))
}

# Time limit (minutes) of each run in run_panel_scenarios.sh: "run <name> ... --time-limit <seconds>".
run_script <- normalizePath("run_panel_scenarios.sh", mustWork = FALSE)  # this file is sourced from code/
script_time_limits <- function(script = run_script) {
  lines <- script_lines(script)
  runs <- regmatches(lines, regexec("^\\s*(?:PANEL=\\S+ )?run (\\w+) .*--time-limit (\\d+)", lines, perl = TRUE))
  runs <- Filter(length, runs)
  setNames(sapply(runs, function(m) as.numeric(m[3]) / 60), sapply(runs, `[`, 2))
}

# Step names of the stepwise objective, in the order they are solved.
step_labels <- c(rules = "Reglur", reference = "Viðmiðunarplan", meetings = "Fundir (þrep 1)",
                 worst = "Mesta byrði (þrep 2)", top1 = "leximin 1", top2 = "leximin 2", top3 = "leximin 3",
                 waiting = "Heildarbið (þrep 3)")

# The solver's progress for each step (code/export_docs_data.py: progress.csv): best solution found and
# best bound over time. Empty when the file is missing.
read_progress <- function(results) {
  progress_file <- file.path(results, "progress.csv")
  if (!file.exists(progress_file)) {
    return(tibble(scenario = factor(), step = integer(), level = factor(), seconds = numeric(),
                  incumbent = numeric(), bound = numeric(), gap = numeric()))
  }
  read_csv(progress_file, show_col_types = FALSE, na = c("", "-")) %>%
    filter(scenario %in% names(scenarios)) %>%
    mutate(scenario = factor(unlist(scenarios[scenario]), levels = unlist(scenarios)),
           level = factor(step_labels[level], levels = step_labels))
}

# Value of the best solution found and the best bound over time, one panel per step: the true optimum
# of a step lies in the shaded band between them, which is the gap.
plot_progress <- function(progress) {
  # Times are from the start of the run; show each step from its own start. The first two steps (rules and
  # reference plan) take seconds and show nothing of interest, so they are left out.
  step_end <- progress %>% group_by(step) %>% summarise(end = max(seconds), .groups = "drop") %>%
    mutate(start = lag(end, default = 0))
  progress <- progress %>% filter(!is.na(incumbent), !is.na(bound), !level %in% step_labels[c("rules", "reference")]) %>%
    left_join(step_end %>% select(step, start), by = "step") %>%
    mutate(minutes = (seconds - start) / 60) %>%
    group_by(level) %>% mutate(next_minutes = lead(minutes)) %>% ungroup()
  ggplot(progress, aes(x = minutes)) +
    # The gap as steps, like the lines: each value holds until the next progress line.
    geom_rect(data = filter(progress, !is.na(next_minutes)),
              aes(xmin = minutes, xmax = next_minutes, ymin = pmin(bound, incumbent),
                  ymax = pmax(bound, incumbent)), fill = "grey70", alpha = 0.4) +
    geom_step(aes(y = incumbent, colour = "Besta lausn sem fannst")) +
    geom_step(aes(y = bound, colour = "Neðra mark")) +
    facet_wrap(~level, scales = "free", ncol = 2) +
    scale_colour_manual(values = c("Besta lausn sem fannst" = "#b2182b", "Neðra mark" = "#2166ac"),
                        name = NULL) +
    labs(x = "Mínútur frá upphafi þreps", y = "Gildi markfalls í þrepinu") +
    theme_panel +
    theme(panel.grid.major.y = element_line(colour = "grey90"))
}

# Gurobi version used for the model runs, from solver.csv.
gurobi_version_of <- function(results) {
  solver_file <- file.path(results, "solver.csv")
  if (!file.exists(solver_file)) return("óþekkt")
  version <- na.omit(read_csv(solver_file, col_types = cols(.default = "c"))$version)
  if (length(version) == 0) "óþekkt" else version[1]
}

# The panel with editors and readers from a role model (models/role_model.py): same proposals and
# meetings, new roles.
panel_with_roles <- function(panel, roles_file) {
  roles <- read_csv(roles_file, col_types = cols(.default = "c")) %>%
    select(application, editor, reader1, reader2)
  panel %>%
    select(-editor, -reader1, -reader2) %>%
    left_join(roles, by = "application")
}

# Ranges over members of load, editor roles and pay, for several assignments (named list of panels).
assignment_summary <- function(panels) {
  bind_rows(lapply(names(panels), function(name) {
    counts <- role_counts(panels[[name]])
    pay <- pay_table(counts)
    table <- member_table(counts)
    reader <- counts %>% filter(role != "Editor") %>%
      pivot_wider(names_from = role, values_from = n, values_fill = 0)
    # Members who are editor on more than one proposal in the same meeting.
    bunched <- panels[[name]] %>% filter(!is.na(meeting), !is.na(editor)) %>%
      count(editor, meeting) %>% filter(n > 1) %>% nrow()
    span <- function(x, digits = 0) sprintf("%s–%s", format(round(min(x), digits), decimal.mark = ","),
                                            format(round(max(x), digits), decimal.mark = ","))
    tibble(Úthlutun = name,
           `Umsóknir á fagráðsmann` = span(table$Total),
           Ritstjórahlutverk = span(table$Editor),
           `Greiðsla (þús. kr.)` = span(pay$Pay / 1000),
           `Greiðsla á umsókn (þús. kr.)` = span(pay$per_proposal / 1000, 1),
           `1. lesari` = span(reader$`Reader 1`),
           `Mesti munur 1. og 2. lesara` = max(abs(reader$`Reader 1` - reader$`Reader 2`)),
           `Ritstjóri á fleiri en einni umsókn á sama fundi` = bunched)
  }))
}

# Exit flow: for each member and meeting, the slot after which they may leave (0 = not attending),
# linked across meetings and coloured by accumulated peel-off points (proposals of others sat through).
exit_flow <- function(schedule) {
  meetings <- levels(schedule$meeting)
  own <- schedule %>%
    filter(!is.na(meeting), !is.na(position)) %>%
    mutate(position = as.integer(position)) %>%
    pivot_longer(all_of(names(role_labels)), values_to = "member") %>%
    filter(!is.na(member)) %>%
    group_by(member, meeting) %>%
    summarise(own = n(), leave = max(position), .groups = "drop") %>%
    mutate(meeting = as.character(meeting))
  expand_grid(member = sort(unique(own$member)), meeting = meetings) %>%
    left_join(own, by = c("member", "meeting")) %>%
    mutate(leave = coalesce(leave, 0L), waiting = if_else(leave > 0, leave - own, 0L),
           meeting = factor(meeting, levels = meetings)) %>%
    arrange(member, meeting) %>%
    group_by(member) %>% mutate(cumulative = cumsum(waiting)) %>% ungroup()
}

plot_exit_flow <- function(schedule) {
  # Only meetings a member attends: the line goes straight to their next meeting.
  flow <- exit_flow(schedule) %>% filter(leave > 0)
  last <- flow %>% group_by(member) %>% slice_max(as.integer(meeting), n = 1) %>% ungroup()
  members <- sort(unique(flow$member))
  # One distinct colour per member: evenly spaced hues, alternating light and dark.
  colours <- setNames(grDevices::hcl(h = seq(15, 375, length.out = length(members) + 1)[seq_along(members)],
                                     c = 90, l = rep(c(45, 70), length.out = length(members))), members)
  ggplot(flow, aes(x = meeting, y = leave, group = member, colour = member)) +
    geom_line(linewidth = 0.7, alpha = 0.85) +
    geom_point(size = 2) +
    geom_text(data = last, aes(label = member), hjust = -0.25, size = 2.8, show.legend = FALSE) +
    scale_colour_manual(values = colours, guide = "none") +
    scale_y_continuous(breaks = seq(0, 15, 3), limits = c(1, NA)) +
    scale_x_discrete(expand = expansion(add = c(0.3, 0.9))) +
    labs(title = "Hvenær hver fagráðsmaður fer af hverjum fundi",
         subtitle = "Hæð = dagskrárliður þegar farið er; lína tengir þá fundi sem viðkomandi mætir á",
         x = NULL, y = "Dagskrárliður") +
    theme_panel +
    theme(panel.grid.major.y = element_line(colour = "grey92"))
}

# Exit groups per meeting: not attending, or leaving in the first, middle or last third of it.
exit_groups <- function(schedule) {
  flow <- exit_flow(schedule)
  lengths <- schedule %>% filter(!is.na(meeting), !is.na(position)) %>%
    group_by(meeting) %>% summarise(length = max(as.integer(position)), .groups = "drop") %>%
    mutate(meeting = as.character(meeting))
  flow %>%
    left_join(lengths, by = c("meeting" = "meeting")) %>%
    mutate(meeting = factor(meeting, levels = levels(flow$meeting)),
           group = case_when(leave == 0 ~ "Mætir ekki",
                             leave <= length / 3 ~ "Fer snemma",
                             leave <= 2 * length / 3 ~ "Miðja",
                             TRUE ~ "Fer seint"),
           group = factor(group, levels = c("Fer seint", "Miðja", "Fer snemma", "Mætir ekki")))
}

# Sankey (alluvial) view: members flow between exit groups from meeting to meeting, coloured by
# their total peel-off points over the round (low, middle or high third of members).
plot_exit_alluvial <- function(schedule) {
  groups <- exit_groups(schedule)
  total <- groups %>% group_by(member) %>% summarise(total = max(cumulative), .groups = "drop") %>%
    mutate(Biðpunktar = factor(c("Fæstir", "Miðlungs", "Flestir")[dplyr::ntile(total, 3)],
                               levels = c("Fæstir", "Miðlungs", "Flestir")))
  groups <- left_join(groups, total, by = "member")
  ggplot(groups, aes(x = meeting, stratum = group, alluvium = member, y = 1, fill = Biðpunktar)) +
    ggalluvial::geom_flow(stat = "alluvium", lode.guidance = "frontback", alpha = 0.7, colour = NA) +
    ggalluvial::geom_stratum(fill = "grey95", colour = "grey60", width = 0.35) +
    geom_text(stat = ggalluvial::StatStratum, aes(label = after_stat(stratum)), size = 2.4) +
    scale_fill_manual(values = c("Fæstir" = "#fbd08a", "Miðlungs" = "#e8615a", "Flestir" = "#4a1c6b"),
                      name = "Biðpunktar yfir lotuna") +
    labs(title = "Hvenær fagráðsmenn fara af fundum",
         subtitle = "Hópar á hverjum fundi eftir því hvenær farið er; flæði litað eftir biðpunktum yfir lotuna",
         x = NULL, y = "Fagráðsmenn") +
    theme_panel +
    theme(panel.grid = element_blank(), legend.position = "bottom")
}

# One distinct colour per member: evenly spaced hues, alternating light and dark.
member_colours <- function(members) {
  setNames(grDevices::hcl(h = seq(15, 375, length.out = length(members) + 1)[seq_along(members)],
                          c = 90, l = rep(c(45, 70), length.out = length(members))), members)
}

# Sankey (alluvial) view of the exit order: every member is one band through all meetings. In each
# meeting the members are stacked by the slot after which they leave (not attending at the bottom,
# last to leave at the top; R01, R02, ... within the same slot), so a band that rises leaves later
# than before and a band that falls leaves earlier.
plot_exit_sankey <- function(schedule) {
  flow <- exit_flow(schedule) %>%
    mutate(stratum = factor(leave, levels = rev(sort(unique(leave)))), order = as.integer(factor(member)))
  ggplot(flow, aes(x = meeting, stratum = stratum, alluvium = member, y = 1, order = order)) +
    ggalluvial::geom_alluvium(aes(fill = member), width = 1 / 3, alpha = 0.85, colour = "white",
                              linewidth = 0.2) +
    ggalluvial::geom_stratum(width = 1 / 3, fill = NA, colour = "grey40", linewidth = 0.3) +
    geom_text(stat = ggalluvial::StatStratum, size = 2.6,
              aes(label = if_else(after_stat(stratum) == "0", "–", as.character(after_stat(stratum))))) +
    scale_fill_manual(values = member_colours(sort(unique(flow$member))), name = NULL) +
    scale_y_continuous(breaks = NULL) +
    labs(title = "Hvenær hver fagráðsmaður fer af hverjum fundi",
         subtitle = "Tala = dagskrárliður þegar farið er (– = mætir ekki); ofar = fer seinna",
         x = NULL, y = "Fagráðsmenn, í þeirri röð sem þeir fara") +
    theme_panel +
    theme(panel.grid = element_blank(), legend.position = "right")
}

# Interactive version for the HTML book, drawn with plotly from the ggalluvial layout. Every band is
# coloured by the member's peel-off points so far (the same scale as the heatmap), so it darkens as
# the round goes on. Clicking a member's band at the first or last meeting, or their code at the left
# or right edge, keeps that member's path in colour and greys out the others; clicking again clears
# it. Hovering a band at a meeting shows the member, the slot after which they leave and their
# peel-off points so far (without changing which member is lit).
plot_exit_sankey_interactive <- function(schedule) {
  static <- plot_exit_sankey(schedule)
  flow <- exit_flow(schedule) %>% mutate(x = as.integer(meeting))
  lodes <- layer_data(static, 1) %>%
    transmute(member = as.character(alluvium), x, ymin, ymax) %>%
    left_join(flow, by = c("member", "x")) %>%
    mutate(text = if_else(leave > 0,
                          sprintf("%s<br>%s: fer eftir dagskrárlið %d<br>biðpunktar hingað til: %d",
                                  member, meeting, leave, cumulative),
                          sprintf("%s<br>%s: mætir ekki<br>biðpunktar hingað til: %d",
                                  member, meeting, cumulative))) %>%
    arrange(member, x)
  strata <- layer_data(static, 2) %>%
    transmute(x, ymin, ymax, absent = as.character(stratum) == "0",
              label = if_else(absent, "–", as.character(stratum)))
  members <- sort(unique(lodes$member))
  grey <- "rgba(150,150,150,0.25)"
  half <- 1 / 6  # half the width of a meeting column, as in the static figure
  # The heatmap's colour scale for peel-off points so far.
  top_value <- max(lodes$cumulative)
  scale_colours <- viridisLite::viridis(256, option = "magma", direction = -1, begin = 0.15, end = 0.9)
  colour_of <- function(value) scale_colours[pmin(256, 1 + floor(255 * value / max(top_value, 1)))]

  # One polygon per member and meeting: the box of that meeting, with the S-curve leading into it. Its
  # colour is the member's peel-off points after that meeting.
  segment <- function(lode, i) {
    flat <- function(y) tibble(x = c(lode$x[i] - half, lode$x[i] + half), y = y)
    side <- function(y) {
      if (i == 1) return(flat(y[1]))
      t <- seq(0, 1, length.out = 16)
      bind_rows(tibble(x = lode$x[i - 1] + half + (lode$x[i] - lode$x[i - 1] - 2 * half) * t,
                       y = y[i - 1] + (y[i] - y[i - 1]) * (3 * t^2 - 2 * t^3)),
                tibble(x = lode$x[i] + half, y = y[i]))
    }
    top <- side(lode$ymax)
    bottom <- side(lode$ymin)
    tibble(x = c(top$x, rev(bottom$x)), y = c(top$y, rev(bottom$y)))
  }
  n_meetings <- nlevels(flow$meeting)
  figure <- plotly::plot_ly()
  band_colours <- character()
  for (member in members) {  # traces member * n_meetings + 1 ...: the bands, one polygon per meeting
    lode <- lodes[lodes$member == member, ]
    for (i in seq_len(nrow(lode))) {
      polygon <- segment(lode, i)
      colour <- colour_of(lode$cumulative[i])
      band_colours <- c(band_colours, colour)
      figure <- plotly::add_trace(figure, type = "scatter", mode = "lines", fill = "toself",
                                  x = polygon$x, y = polygon$y, fillcolor = colour,
                                  line = list(color = "white", width = 0.6),
                                  hoverinfo = "skip", showlegend = FALSE)
    }
  }
  for (member in members) {  # the next traces: invisible points carrying the tooltips
    lode <- lodes[lodes$member == member, ]
    middle <- (lode$ymin + lode$ymax) / 2
    # In each meeting the full tooltip; halfway between two meetings just the member.
    figure <- plotly::add_trace(figure, type = "scatter", mode = "markers",
                                x = c(lode$x, head(lode$x, -1) + 0.5),
                                y = c(middle, (head(middle, -1) + tail(middle, -1)) / 2),
                                # Bigger at the outer meetings: those points are what one clicks to select a member.
                                marker = list(size = c(ifelse(lode$x %in% range(flow$x), 28, 16),
                                                       rep(16, nrow(lode) - 1)), opacity = 0),
                                text = c(lode$text, rep(member, nrow(lode) - 1)), hoverinfo = "text",
                                showlegend = FALSE)
  }
  # The colour bar: an invisible trace that carries the scale.
  figure <- plotly::add_trace(figure, type = "scatter", mode = "markers", x = c(1, 1), y = c(0, 0),
                              marker = list(size = 0.1, opacity = 0, color = c(0, top_value),
                                            colorscale = lapply(seq(0, 1, length.out = 8),
                                                                function(v) list(v, colour_of(v * top_value))),
                                            cmin = 0, cmax = top_value, showscale = TRUE,
                                            colorbar = list(title = list(text = "Biðpunktar<br>hingað til"),
                                                            len = 0.6, thickness = 14)),
                              hoverinfo = "skip", showlegend = FALSE)
  # Meeting columns: one box per leaving slot with its number; members who don't attend are faded.
  boxes <- lapply(seq_len(nrow(strata)), function(i) {
    list(type = "rect", x0 = strata$x[i] - half, x1 = strata$x[i] + half, y0 = strata$ymin[i],
         y1 = strata$ymax[i], line = list(color = "grey", width = 0.6),
         fillcolor = if (strata$absent[i]) "rgba(255,255,255,0.65)" else "rgba(255,255,255,0)")
  })
  note <- function(x, y, text, anchor = "center", clickable = FALSE) {
    # The slot numbers get a light backing so they stay readable on the dark bands.
    list(x = x, y = y, text = text, xanchor = anchor, showarrow = FALSE, font = list(size = 10, color = "#444"),
         captureevents = clickable, bgcolor = if (clickable) NULL else "rgba(255,255,255,0.75)", borderpad = 1)
  }
  ends <- lodes %>% filter(x %in% range(x)) %>% mutate(first = x == min(x))
  labels <- c(
    lapply(seq_len(nrow(strata)), function(i) note(strata$x[i], (strata$ymin[i] + strata$ymax[i]) / 2,
                                                   strata$label[i])),
    lapply(seq_len(nrow(ends)), function(i) note(ends$x[i] + if (ends$first[i]) -half - 0.04 else half + 0.04,
                                                 (ends$ymin[i] + ends$ymax[i]) / 2, ends$member[i],
                                                 if (ends$first[i]) "right" else "left", clickable = TRUE)))
  # For each annotation, the member it names (0-based index into members), or -1 for slot numbers.
  label_member <- c(rep(-1L, nrow(strata)), match(ends$member, members) - 1L)
  figure %>%
    plotly::layout(shapes = boxes, annotations = labels, hovermode = "closest",
                   xaxis = list(title = "", tickvals = seq_len(n_meetings), ticktext = levels(flow$meeting),
                                range = c(0.45, n_meetings + 0.55), showgrid = FALSE, zeroline = FALSE),
                   yaxis = list(title = "Fagráðsmenn, í þeirri röð sem þeir fara (ofar = seinna)",
                                showticklabels = FALSE, showgrid = FALSE, zeroline = FALSE)) %>%
    htmlwidgets::onRender(
      "function(el, x, data) {
         var bands = [], k, lit = -1;
         for (k = 0; k < data.n * data.meetings; k++) bands.push(k);
         function paint(m) {
           lit = m;
           Plotly.restyle(el, {fillcolor: bands.map(function(i) {
             return (m < 0 || Math.floor(i / data.meetings) === m) ? data.colours[i] : data.grey; })}, bands);
           var labels = {};
           data.member.forEach(function(r, j) {
             if (r < 0) return;
             labels['annotations[' + j + '].font.color'] = r === m ? '#000' : '#444';
             labels['annotations[' + j + '].font.size'] = r === m ? 12 : 10;
           });
           Plotly.relayout(el, labels);
         }
         // Clicking a member's band at the first or last meeting, or their code at either edge, keeps
         // their path in colour and greys out the others; clicking again, or a double click, clears
         // the selection. Hovering only shows tooltips, so it never changes focus.
         el.on('plotly_clickannotation', function(e) {
           var r = data.member[e.index];
           if (r >= 0) paint(r === lit ? -1 : r);
         });
         el.on('plotly_click', function(e) {
           var p = e.points && e.points[0], first = data.n * data.meetings;
           if (!p || p.curveNumber < first || p.curveNumber >= first + data.n) return;
           if (p.x !== 1 && p.x !== data.meetings) return;
           var r = p.curveNumber - first;
           paint(r === lit ? -1 : r);
         });
         el.on('plotly_doubleclick', function() { paint(-1); });
       }", data = list(colours = band_colours, grey = grey, member = label_member,
                       n = length(members), meetings = n_meetings))
}

# Heatmap view: members in rows, meetings in columns; the number is the slot after which they leave
# (blank = not attending) and the colour is their peel-off points so far.
plot_exit_heatmap <- function(schedule) {
  flow <- exit_flow(schedule)
  order <- flow %>% group_by(member) %>% summarise(total = max(cumulative), .groups = "drop") %>%
    arrange(total) %>% pull(member)
  flow <- flow %>% mutate(member = factor(member, levels = order))
  # Right of the meetings: peel-off points over the round, and per meeting attended.
  totals <- flow %>% group_by(member) %>%
    summarise(total = max(cumulative), per_meeting = total / sum(leave > 0), .groups = "drop")
  n <- nlevels(flow$meeting)
  ggplot(flow, aes(x = meeting, y = member)) +
    geom_tile(aes(fill = if_else(leave > 0, cumulative, NA_integer_)), colour = "white", linewidth = 0.6) +
    geom_text(aes(label = if_else(leave > 0, as.character(leave), ""),
                  colour = cumulative > max(cumulative) / 2), size = 2.8) +
    geom_text(data = totals, aes(x = n + 0.9, y = member, label = total),
              inherit.aes = FALSE, size = 3, fontface = "bold", colour = "grey20") +
    geom_text(data = totals, aes(x = n + 1.8, y = member, label = num_is(per_meeting)),
              inherit.aes = FALSE, size = 3, colour = "grey20") +
    annotate("text", x = c(n + 0.9, n + 1.8), y = length(order) + 0.9, label = c("Samtals", "Á fund"),
             size = 2.9, fontface = "bold", colour = "grey20") +
    scale_fill_viridis_c(option = "magma", direction = -1, begin = 0.15, end = 0.9, na.value = "grey95",
                         name = "Uppsafnaðir biðpunktar") +
    scale_colour_manual(values = c(`TRUE` = "white", `FALSE` = "black"), guide = "none") +
    scale_x_discrete(expand = expansion(add = c(0.6, 2.1))) +
    scale_y_discrete(expand = expansion(add = c(0.6, 1.4))) +
    labs(title = "Hvenær hver fagráðsmaður fer af hverjum fundi",
         subtitle = paste0("Tala = dagskrárliður þegar farið er (autt = mætir ekki); litur = biðpunktar hingað til.\n",
                           "Hægra megin: biðpunktar yfir lotuna, samtals og á hvern fund sem mætt er á"),
         x = NULL, y = NULL) +
    theme_panel +
    theme(panel.grid = element_blank(), legend.position = "bottom", legend.key.width = unit(40, "pt"),
          legend.title.position = "top")
}

# Interactive version for the HTML book: all lines grey; hovering a line highlights that member and
# shows a tooltip with their code, the meeting, the slot and their peel-off points so far.
plot_exit_flow_interactive <- function(schedule) {
  flow <- exit_flow(schedule) %>%
    filter(leave > 0) %>%
    mutate(text = sprintf("%s<br>%s: fer eftir dagskrárlið %d<br>biðpunktar hingað til: %d",
                          member, meeting, leave, cumulative))
  shared <- plotly::highlight_key(flow, ~member)
  plotly::plot_ly(shared, x = ~meeting, y = ~leave, split = ~member, type = "scatter",
                  mode = "lines+markers", text = ~text, hoverinfo = "text",
                  line = list(color = "rgba(150,150,150,0.45)", width = 1.5),
                  marker = list(color = "rgba(150,150,150,0.6)", size = 6), showlegend = FALSE) %>%
    plotly::layout(xaxis = list(title = ""), yaxis = list(title = "Dagskrárliður", rangemode = "tozero"),
                   hovermode = "closest") %>%
    plotly::highlight(on = "plotly_hover", off = "plotly_doubleclick", color = "#c2185b",
                      opacityDim = 0.35, selected = plotly::attrs_selected(line = list(width = 3)))
}
