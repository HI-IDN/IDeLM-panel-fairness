# Review-panel meetings: who waits how long, and how schedules compare.
#
# Works on the pseudonymised panel.csv (agenda positions of held meetings) and on the output of
# models/panel_model.py (<prefix>_agenda.csv and <prefix>_members.csv). Sourced by the book in
# docs/; uses the helpers and theme from panel_workload.R.
library(tidyverse)

# Scenarios: result file prefix -> label, in the order they are compared.
scenarios <- c(current = "1. Tillaga starfsmanna, sanngjörn röð",
               free = "2. Næsti fundur festur, restin bestuð",
               free_max4 = "3. Eins og 2, mest 4 á fund",
               scratch = "4. Bestað frá byrjun")
scenario_colours <- setNames(c("#eb6834", "#2a78d6", "#1baf7a", "#4a3aa7"), scenarios)
# Agenda slots where a member has a conflict of interest: red if they have to step out, pink if
# they are not in the meeting then (already left, or not attending).
conflict_colour <- "#d7263d"
conflict_away_colour <- "#f4a9b8"

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

# Conflicts of interest in held meetings: one row per conflicted member and proposal, and whether
# the member was still in the meeting (own proposals left) when it was taken, so had to step out.
held_conflicts <- function(panel) {
  panel %>%
    filter(!is.na(position), !is.na(coi)) %>%
    mutate(position = as.integer(position)) %>%
    separate_rows(coi, sep = ";") %>%
    select(meeting, member = coi, position) %>%
    left_join(held_meetings(panel) %>% select(meeting, member, leave), by = c("meeting", "member")) %>%
    mutate(in_meeting = !is.na(leave) & leave >= position)
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
  # Slots where a member has a conflict: they step out, or are not in the meeting then.
  conflicts <- held_conflicts(panel) %>%
    mutate(meeting = as.character(meeting),
           colour = if_else(in_meeting, conflict_colour, conflict_away_colour)) %>%
    inner_join(select(running, meeting, member, row), by = c("meeting", "member"))
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
      geom_tile(data = keep(conflicts), aes(x = position - 0.5, y = row), width = 0.9, height = 0.55,
                fill = keep(conflicts)$colour) +
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
                        y = 0.86, size = 14) +
    cowplot::draw_label(paste0("Grá lína = tími á fundinum; blátt = eigin umsóknir; brotalína = fundarlok.\n",
                               "Rautt = vanhæfur og víkur af fundi; bleikt = vanhæfur en farinn eða ekki mættur.\n",
                               "Hægra megin: uppsafnaðir biðpunktar (umsóknir annarra sem setið var undir)"),
                        x = 0.01, hjust = 0, y = 0.33, size = 11)
  body <- cowplot::plot_grid(plotlist = panels, nrow = 1, rel_widths = widths, align = "h", axis = "tb")
  axis <- cowplot::ggdraw() + cowplot::draw_label("Dagskrárliður (umsóknir teknar fyrir)", size = 11)
  cowplot::plot_grid(title, body, axis, legend, ncol = 1, rel_heights = c(0.2, 1, 0.05, 0.12))
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
  runs <- runs %>%
    mutate(member = factor(member, levels = order),
           number = factor(sub("[.].*", "", scenario), levels = sub("[.].*", "", levels(scenario))))
  ggplot(runs, aes(x = number, y = member, fill = v)) +
    geom_tile(colour = "white", linewidth = 0.8) +
    geom_text(aes(label = format(round(v, digits), nsmall = digits, decimal.mark = ","),
                  colour = v > (min(v) + max(v)) / 2), size = 3) +
    scale_fill_viridis_c(option = "mako", direction = -1, begin = 0.15, end = 0.85, name = fill_label) +
    scale_colour_manual(values = c(`TRUE` = "white", `FALSE` = "black"), guide = "none") +
    scale_x_discrete(position = "top") +
    labs(title = title, x = "Sviðsmynd", y = NULL) +
    theme_panel +
    theme(panel.grid = element_blank(), legend.position = "right")
}

summary_table <- function(runs) {
  runs %>%
    group_by(Sviðsmynd = droplevels(scenario)) %>%
    summarise(`Versta byrði á umsókn` = max(burden_per_proposal),
              `Fundir sem mætt er á (bil)` = sprintf("%d–%d", min(meetings), max(meetings)),
              `Biðpunktar samtals` = sum(waiting),
              `Biðpunktar á umsókn, mest` = max(waiting_per_proposal), .groups = "drop")
}

# Solver time (minutes) and final gap (%) per scenario. The Gurobi logs stay local (they hold
# licence details); code/export_docs_data.py summarises them in solver.csv.
read_solver_info <- function(results) {
  solver_file <- file.path(results, "solver.csv")
  if (!file.exists(solver_file)) return(tibble(scenario = factor(), minutes = numeric(), gap = numeric()))
  read_csv(solver_file, show_col_types = FALSE) %>%
    filter(scenario %in% names(scenarios)) %>%
    transmute(scenario = factor(unlist(scenarios[scenario]), levels = unlist(scenarios)), minutes, gap)
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
           `Lesari 1` = span(reader$`Reader 1`),
           `Mesti munur lesara 1 og 2` = max(abs(reader$`Reader 1` - reader$`Reader 2`)),
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

# One distinct colour per member: evenly spaced hues, alternating light and dark.
member_colours <- function(members) {
  setNames(grDevices::hcl(h = seq(15, 375, length.out = length(members) + 1)[seq_along(members)],
                          c = 90, l = rep(c(45, 70), length.out = length(members))), members)
}

plot_exit_flow <- function(schedule) {
  # Only meetings a member attends: the line goes straight to their next meeting.
  flow <- exit_flow(schedule) %>% filter(leave > 0)
  last <- flow %>% group_by(member) %>% slice_max(as.integer(meeting), n = 1) %>% ungroup()
  colours <- member_colours(sort(unique(flow$member)))
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

# Interactive version for the HTML book, drawn with plotly from the ggalluvial layout: all bands
# grey; clicking a member's code at the left or right edge lights their band up in their own
# colour, and hovering a band at a meeting shows the member, the slot after which they leave and
# their peel-off points so far (without changing which member is lit).
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
  colours <- member_colours(members)
  grey <- "rgba(150,150,150,0.4)"
  half <- 1 / 6  # half the width of a meeting column, as in the static figure

  # Outline of one band: flat through each meeting column, an S-curve between two columns.
  edge <- function(x, y) {
    t <- seq(0, 1, length.out = 16)
    bind_rows(lapply(seq_along(x), function(i) {
      flat <- tibble(x = c(x[i] - half, x[i] + half), y = y[i])
      if (i == length(x)) return(flat)
      bind_rows(flat, tibble(x = x[i] + half + (x[i + 1] - x[i] - 2 * half) * t,
                             y = y[i] + (y[i + 1] - y[i]) * (3 * t^2 - 2 * t^3)))
    }))
  }
  figure <- plotly::plot_ly()
  for (member in members) {  # traces 1..n: the bands
    lode <- lodes[lodes$member == member, ]
    top <- edge(lode$x, lode$ymax)
    bottom <- edge(lode$x, lode$ymin)
    figure <- plotly::add_trace(figure, type = "scatter", mode = "lines", fill = "toself",
                                x = c(top$x, rev(bottom$x)), y = c(top$y, rev(bottom$y)),
                                fillcolor = grey, line = list(color = "white", width = 0.6),
                                hoveron = "fills", hoverinfo = "none", showlegend = FALSE)
  }
  for (member in members) {  # traces n+1..2n: invisible points carrying the tooltips
    lode <- lodes[lodes$member == member, ]
    middle <- (lode$ymin + lode$ymax) / 2
    # In each meeting the full tooltip; halfway between two meetings just the member.
    figure <- plotly::add_trace(figure, type = "scatter", mode = "markers",
                                x = c(lode$x, head(lode$x, -1) + 0.5),
                                y = c(middle, (head(middle, -1) + tail(middle, -1)) / 2),
                                marker = list(size = 16, opacity = 0),
                                text = c(lode$text, rep(member, nrow(lode) - 1)), hoverinfo = "text",
                                showlegend = FALSE)
  }
  # Meeting columns: one box per leaving slot with its number; members who don't attend are faded.
  boxes <- lapply(seq_len(nrow(strata)), function(i) {
    list(type = "rect", x0 = strata$x[i] - half, x1 = strata$x[i] + half, y0 = strata$ymin[i],
         y1 = strata$ymax[i], line = list(color = "grey", width = 0.6),
         fillcolor = if (strata$absent[i]) "rgba(255,255,255,0.65)" else "rgba(255,255,255,0)")
  })
  note <- function(x, y, text, anchor = "center", clickable = FALSE) {
    list(x = x, y = y, text = text, xanchor = anchor, showarrow = FALSE, font = list(size = 10, color = "#444"),
         captureevents = clickable)
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
  n_meetings <- nlevels(flow$meeting)
  figure %>%
    plotly::layout(shapes = boxes, annotations = labels, hovermode = "closest",
                   xaxis = list(title = "", tickvals = seq_len(n_meetings), ticktext = levels(flow$meeting),
                                range = c(0.45, n_meetings + 0.55), showgrid = FALSE, zeroline = FALSE),
                   yaxis = list(title = "Fagráðsmenn, í þeirri röð sem þeir fara (ofar = seinna)",
                                showticklabels = FALSE, showgrid = FALSE, zeroline = FALSE)) %>%
    htmlwidgets::onRender(
      "function(el, x, data) {
         var bands = data.colours.map(function(c, i) { return i; }), lit = -1;
         function paint(k) {
           lit = k;
           Plotly.restyle(el, {fillcolor: bands.map(function(i) { return i === k ? data.colours[i] : data.grey; })}, bands);
           var labels = {};
           data.member.forEach(function(r, j) {
             if (r < 0) return;
             labels['annotations[' + j + '].font.color'] = r === k ? data.colours[r] : '#444';
             labels['annotations[' + j + '].font.size'] = r === k ? 12 : 10;
           });
           Plotly.relayout(el, labels);
         }
         // Clicking a member's code at either edge selects them; clicking it again, or a double
         // click, clears the selection. Hovering only shows tooltips, so it never changes focus.
         el.on('plotly_clickannotation', function(e) {
           var r = data.member[e.index];
           if (r >= 0) paint(r === lit ? -1 : r);
         });
         el.on('plotly_doubleclick', function() { paint(-1); });
       }", data = list(colours = unname(colours), grey = grey, member = label_member))
}

# The APAP equity measure for a schedule: waiting per meeting attended should be close to a common
# target c. Each member scores 1 + 0.5 + 0.2 for being within 1, 0.5 and 0.2 of c. The target is
# the value of c with the highest total score (tried: every member's value, shifted by each band).
equity_bands <- function(per_meeting, bands = c(1, 0.5, 0.2)) {
  score <- function(c) sum(sapply(bands, function(eps) eps * sum(abs(per_meeting - c) <= eps + 1e-9)))
  candidates <- unique(c(per_meeting, outer(per_meeting, c(-bands, bands), "+")))
  scores <- sapply(candidates, score)
  tibble(target = median(candidates[scores == max(scores)]), equity = max(scores),
         equity_max = sum(bands) * length(per_meeting))
}

# Objective terms per schedule, as facets (like the weekly objective terms of APAP), in the order of
# the steps: meetings attended (step 1), the largest unpaid burden alpha * meetings + waiting
# (step 2), total waiting (step 3); and, for comparison, the longest waiting of any member and the
# equity of the bands. `runs` has one row per member and a scenario column (read_members).
plot_objective_terms <- function(runs, alpha = 2) {
  terms <- runs %>%
    group_by(scenario) %>%
    # burden first: summarise() replaces meetings by its sum for the terms after it. The runs have
    # an alpha column of their own (the value they were solved with), hence .env$alpha.
    summarise(burden = max(.env$alpha * meetings + waiting), meetings = sum(meetings),
              total = sum(waiting), worst = max(waiting), equity_bands(waiting_per_meeting),
              .groups = "drop") %>%
    select(scenario, meetings, burden, total, worst, equity) %>%
    pivot_longer(-scenario, names_to = "term") %>%
    mutate(term = factor(term, c("meetings", "burden", "total", "worst", "equity"),
                         c("1. Mætingar samtals", paste0("2. Mesta ólaunuð byrði (", alpha, " × fundir + bið)"),
                           "3. Biðpunktar samtals", "Mesta bið eins fagráðsmanns", "Jöfnuður bið á fund (bönd)")))
  ggplot(terms, aes(x = value, y = fct_rev(scenario))) +
    geom_col(fill = role_colours[["Editor"]], width = 0.6) +
    geom_text(aes(label = format(round(value, 1), decimal.mark = ",", drop0trailing = TRUE)), hjust = -0.2,
              size = 3) +
    facet_wrap(~term, scales = "free_x", ncol = 3) +
    scale_x_continuous(expand = expansion(mult = c(0, 0.25))) +
    labs(title = "Liðir markfallsins eftir því hvað er bestað",
         subtitle = paste0("Þrepin 1–3 eru bestuð í þessari röð; jöfnuður: 1 + 0,5 + 0,2 fyrir hvern sem er innan ",
                           "1, 0,5 og 0,2 frá markgildi biðar á fund (mest ",
                           format(1.7 * n_distinct(runs$member), decimal.mark = ","), ")"),
         x = NULL, y = NULL) +
    theme_panel
}

# Trade-off between meetings attended and waiting: one point per member, and a curve of fair
# trade-offs. Members more than `band` above the curve are unlucky, more than `band` below lucky;
# the unlucky ones are those a reward (e.g. editor roles) should go to. Curves:
#   linear: alpha * meetings + waiting = median, so one meeting fewer allows alpha more waiting;
#   convex: a * meetings^2 + waiting = median, each extra meeting weighing more than the one
#           before (a = alpha / (2 * mean meetings), the same slope as linear at the mean);
#   fit:    the least-squares parabola through the members (how the plan does share, not a norm);
#   line:   the least-squares straight line through the members;
#   flat:   a level line at the mean, so everyone should wait the same whatever their meetings;
#   pareto: a parabola through the lower envelope, the least waiting reached at each number of
#           meetings (the best trade-offs reached). The strict Pareto front, members no one beats
#           on both, is degenerate here: few meetings and little waiting go together.
tradeoff_curve <- function(meetings, waiting, curve, alpha) {
  if (curve == "linear") {
    target <- median(alpha * meetings + waiting)
    return(function(m) target - alpha * m)
  }
  if (curve == "convex") {
    a <- alpha / (2 * mean(meetings))
    target <- median(a * meetings^2 + waiting)
    return(function(m) target - a * m^2)
  }
  if (curve == "flat") {
    level <- mean(waiting)
    return(function(m) rep(level, length(m)))
  }
  if (curve == "pareto") {
    lowest <- tapply(waiting, meetings, min)
    meetings <- as.numeric(names(lowest))
    waiting <- as.numeric(lowest)
  }
  degree <- min(if (curve == "line") 1 else 2, length(unique(meetings)) - 1)
  fit <- lm(waiting ~ poly(meetings, degree, raw = TRUE))
  function(m) unname(predict(fit, newdata = data.frame(meetings = m)))
}

# With per_proposal = TRUE the y axis is waiting per own proposal (the curves are drawn on that
# scale), and the size of each point is the member's total presence: slots sat through, own
# proposals and waiting.
plot_tradeoff <- function(runs, alpha = 2, band = 5, curves = c("linear", "convex", "fit", "pareto"),
                          per_proposal = FALSE) {
  if (per_proposal) runs <- runs %>% mutate(waiting = waiting / proposals)
  names_is <- c(linear = "Bein lína", convex = "Kúptur kostnaður", fit = "Aðhvarf", line = "Aðhvarfslína", flat = "Meðaltal",
                pareto = "Neðri umgjörð")
  span <- range(runs$meetings) + c(-0.5, 0.5)
  grid <- seq(span[1], span[2], length.out = 60)
  pieces <- lapply(curves, function(curve) {
    lapply(split(runs, runs$scenario, drop = TRUE), function(d) {
      f <- tradeoff_curve(d$meetings, d$waiting, curve, alpha)
      list(points = d %>% mutate(curve = names_is[[curve]], gap = waiting - f(meetings)),
           line = tibble(scenario = d$scenario[1], curve = names_is[[curve]], meetings = grid, mid = f(grid)))
    })
  })
  pieces <- unlist(pieces, recursive = FALSE)
  points <- bind_rows(lapply(pieces, `[[`, "points")) %>%
    mutate(status = factor(case_when(gap > band ~ "Óheppnir (yfir)", gap < -band ~ "Heppnir (undir)",
                                     TRUE ~ "Innan marka"),
                           c("Óheppnir (yfir)", "Innan marka", "Heppnir (undir)")),
           curve = factor(curve, names_is[curves]))
  lines <- bind_rows(lapply(pieces, `[[`, "line")) %>% mutate(curve = factor(curve, names_is[curves]))
  ggplot(points, aes(meetings, waiting)) +
    geom_ribbon(data = lines, aes(x = meetings, ymin = mid - band, ymax = mid + band), inherit.aes = FALSE,
                fill = "grey90") +
    geom_line(data = lines, aes(x = meetings, y = mid), inherit.aes = FALSE, colour = "grey50",
              linetype = "dashed") +
    geom_point(aes(colour = status, size = leave_slots), alpha = 0.8) +
    geom_text(aes(label = member, colour = status), size = 2.2, vjust = -0.9, show.legend = FALSE) +
    facet_grid(rows = vars(curve), cols = vars(scenario)) +
    scale_colour_manual(values = c("Óheppnir (yfir)" = "#d7263d", "Innan marka" = "grey40",
                                   "Heppnir (undir)" = "#2a78d6"), name = NULL, drop = FALSE) +
    scale_x_continuous(breaks = seq(ceiling(span[1]), floor(span[2]), 1)) +
    scale_size_area(max_size = 5, name = "Heildarviðvera (dagskrárliðir)") +
    coord_cartesian(xlim = span) +
    labs(title = "Fundir og bið hjá hverjum fagráðsmanni",
         subtitle = paste0("Brotalína: sanngjörn skipti funda og biðar (α = ", alpha,
                           "); grátt band: ±", format(band, decimal.mark = ","),
                           if (per_proposal) " biðpunktar á umsókn" else " biðpunktar"),
         x = "Fundir sem mætt er á",
         y = if (per_proposal) "Biðpunktar á eigin umsókn" else "Biðpunktar yfir lotuna") +
    theme_panel +
    theme(panel.grid.major.y = element_line(colour = "grey92"), legend.position = "top")
}
