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
               free_target = "4. Eins og 2, markgildi á fund",
               scratch = "5. Bestað frá byrjun")
scenario_colours <- setNames(c("#eb6834", "#2a78d6", "#1baf7a", "#e87ba4", "#4a3aa7"), scenarios)

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
