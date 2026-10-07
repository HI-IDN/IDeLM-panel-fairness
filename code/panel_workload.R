# Review-panel workload: how many proposals each member has as editor and as reader.
#
# Reads the pseudonymised panel.csv. Sourced by docs/_setup.R; run directly from code/
# (Rscript panel_workload.R) to save the figures next to the data, which is gitignored.
#
# Roles: preparation is the same for everyone. In the meeting the editor speaks most (recaps the
# proposal), then reader 1, then reader 2. Afterwards the editor writes the feedback summary and
# both readers read it and confirm they agree. The export lists the two readers alphabetically,
# so who is reader 1 follows the alphabet. For the workload figures and tables the two readers are
# merged into one reader role.
library(tidyverse)

role_labels <- c(editor = "Editor", reader1 = "Reader 1", reader2 = "Reader 2")

# Figures are in Icelandic (the book is written for the fund); data keys stay in English.
is_labels <- c("Editor" = "Ritstjóri", "Reader" = "Lesari", "Reader 1" = "1. lesari",
               "Reader 2" = "2. lesari", "Total" = "Samtals", "Start fee" = "Grunngjald",
               "Unassigned" = "Óúthlutað")
tr <- function(x) unname(ifelse(x %in% names(is_labels), is_labels[x], x))
num_is <- function(x, digits = 1) format(round(x, digits), nsmall = digits, decimal.mark = ",")

# New panel members, from members.csv (member, new) next to panel.csv; empty without it.
new_members <- character()
load_new_members <- function(file) {
  if (file.exists(file)) {
    members <- read_csv(file, col_types = cols(.default = "c"))
    new_members <<- members$member[toupper(members$new) == "TRUE"]
  }
  invisible(new_members)
}
source("panel_palette.R")  # role_colours, pay_colours and the other figure colours

theme_panel <- theme_minimal(base_size = 11) +
  theme(panel.grid.major.y = element_blank(), panel.grid.minor = element_blank(),
        legend.position = "top", legend.justification = "left",
        plot.title.position = "plot", plot.background = element_rect(fill = "white", colour = NA))

read_panel <- function(file) {
  panel <- read_csv(file, col_types = cols(.default = "c"))
  # Meetings are M1, M2, ... in date order (panel.csv has no real dates).
  n <- max(as.integer(sub("M", "", na.omit(panel$meeting))))
  panel %>% mutate(meeting = factor(meeting, levels = paste0("M", seq_len(n))))
}

# One row per member and role (editor, reader 1, reader 2), including zero counts.
role_counts <- function(panel) {
  panel %>%
    pivot_longer(all_of(names(role_labels)), names_to = "role", values_to = "member") %>%
    filter(!is.na(member)) %>%
    mutate(role = factor(role_labels[role], levels = role_labels)) %>%
    count(member, role) %>%
    complete(member, role, fill = list(n = 0))
}

# Merge reader 1 and reader 2 into a single reader role.
merge_readers <- function(counts) {
  counts %>%
    mutate(role = fct_collapse(role, Reader = c("Reader 1", "Reader 2"))) %>%
    group_by(member, role) %>% summarise(n = sum(n), .groups = "drop")
}

# Per member: editor, reader and total load (reader 1 and 2 merged).
member_table <- function(counts) {
  merge_readers(counts) %>%
    pivot_wider(names_from = role, values_from = n) %>%
    mutate(Total = Editor + Reader) %>%
    arrange(desc(Total), member)
}

# Range and median of the per-member load, by role.
spread_table <- function(table) {
  table %>%
    pivot_longer(c(Editor, Reader, Total), names_to = "Role", values_to = "n") %>%
    group_by(Role) %>%
    summarise(Min = min(n), Median = median(n), Max = max(n), .groups = "drop")
}

plot_members <- function(counts) {
  load <- merge_readers(counts)
  totals <- load %>% group_by(member) %>%
    summarise(total = sum(n), editor_share = n[role == "Editor"] / total, .groups = "drop")
  load <- load %>% mutate(member = fct_reorder(member, n, .fun = sum))
  medians <- tibble(x = c(median(load$n[load$role == "Editor"]), median(totals$total)),
                    label = sprintf(c("miðgildi ritstjóra %g", "miðgildi samtals %g"), x))
  n_members <- nrow(totals)

  ggplot(load, aes(x = n, y = member, fill = fct_rev(role))) +
    geom_col(width = 0.7, colour = "white", linewidth = 0.4) +
    geom_vline(data = medians, aes(xintercept = x), linetype = "dashed", colour = "black",
               linewidth = 0.6) +
    geom_label(data = medians, aes(x = x, y = n_members + 0.9, label = label), inherit.aes = FALSE,
               size = 3.4, colour = "black", fill = "white", linewidth = 0) +
    geom_text(data = totals, aes(x = total, y = member,
                                 label = sprintf("%d (%.0f%%)", total, 100 * editor_share)),
              inherit.aes = FALSE, hjust = 0, nudge_x = 0.3, size = 3.2, colour = "grey30") +
    scale_fill_manual(values = role_colours, breaks = c("Editor", "Reader"), labels = tr, name = NULL) +
    scale_x_continuous(expand = expansion(mult = c(0, 0.14))) +
    scale_y_discrete(expand = expansion(add = c(0.6, 1.4))) +
    labs(title = "Umsóknir á hvern fagráðsmann, eftir hlutverki",
         subtitle = sprintf("%d fagráðsmenn, raðað eftir heildarfjölda. Merki: samtals (%% sem ritstjóri)",
                            n_members),
         x = "Umsóknir", y = NULL) +
    theme_panel
}

# Per member: editor, reader 1 and reader 2 roles (room in the discussion), sorted by total load.
plot_roles <- function(counts) {
  totals <- counts %>% group_by(member) %>% summarise(total = sum(n), .groups = "drop")
  counts <- counts %>% mutate(member = factor(member, levels = totals$member[order(totals$total)]))
  ggplot(counts, aes(x = n, y = member, fill = fct_rev(role))) +
    geom_col(width = 0.7, colour = "white", linewidth = 0.4) +
    scale_fill_manual(values = role_colours, breaks = c("Editor", "Reader 1", "Reader 2"), labels = tr,
                      name = NULL) +
    scale_x_continuous(expand = expansion(mult = c(0, 0.05))) +
    labs(title = "Hlutverk hvers fagráðsmanns",
         subtitle = "Ritstjóri talar fyrst, 1. lesari næstur og 2. lesari síðastur",
         x = "Umsóknir", y = NULL) +
    theme_panel
}

plot_spread <- function(counts, share = FALSE) {
  # Editor, reader (1 and 2 merged) and each member's total (any role). With share = TRUE, each
  # role as a share of the member's own proposals instead (the total is then always 100 %).
  counts <- merge_readers(counts)
  totals <- counts %>% group_by(member) %>% summarise(n = sum(n), .groups = "drop") %>%
    mutate(role = "Total")
  if (share) {
    counts <- counts %>% left_join(select(totals, member, total = n), by = "member") %>%
      mutate(n = 100 * n / total, role = factor(as.character(role), levels = c("Editor", "Reader")))
  } else {
    counts <- bind_rows(counts %>% mutate(role = as.character(role)), totals) %>%
      mutate(role = factor(role, levels = c("Editor", "Reader", "Total")))
  }
  spread <- counts %>% group_by(role) %>%
    summarise(min = min(n), max = max(n), median = median(n), .groups = "drop") %>%
    mutate(y = as.numeric(fct_rev(role)))
  label <- if (share) "bil %.0f–%.0f %%, miðgildi %.0f %%" else "bil %g–%g, miðgildi %g"

  ggplot(counts, aes(x = n, y = fct_rev(role), colour = role)) +
    geom_linerange(data = spread, aes(xmin = min, xmax = max, y = fct_rev(role)),
                   inherit.aes = FALSE, linewidth = 6, colour = "grey92") +
    geom_point(position = position_jitter(width = 0, height = 0.15, seed = 1), size = 2.6,
               alpha = 0.85) +
    geom_segment(data = spread, aes(x = median, xend = median, y = y - 0.3, yend = y + 0.3),
                 inherit.aes = FALSE, linewidth = 1.4, colour = "black") +
    geom_text(data = spread, aes(x = max, y = fct_rev(role),
                                 label = sprintf(label, min, max, median)),
              inherit.aes = FALSE, hjust = -0.1, size = 3.4, colour = "black") +
    scale_colour_manual(values = role_colours, guide = "none") +
    (if (share) scale_x_continuous(breaks = seq(0, 100, 20), labels = function(x) paste(x, "%"),
                                   expand = expansion(mult = c(0.02, 0.4)))
     else scale_x_continuous(breaks = seq(0, 30, 4), expand = expansion(mult = c(0.02, 0.4)))) +
    expand_limits(x = 0) +
    scale_y_discrete(labels = tr) +
    labs(title = if (share) "Hlutfall hlutverka af umsóknum hvers fagráðsmanns"
                 else "Dreifing umsókna á fagráðsmenn, eftir hlutverki",
         subtitle = "Hver punktur er einn fagráðsmaður; grátt band = bil, svart strik = miðgildi",
         x = if (share) "Hlutfall af eigin umsóknum" else "Umsóknir", y = NULL) +
    theme_panel
}

# Pay per round (ISK): a start fee per member, plus a fee per proposal by role.
pay_rates <- c(start = 38000, editor = 23000, reader = 15000)

pay_table <- function(counts, rates = pay_rates) {
  member_table(counts) %>%
    mutate(`Start fee` = rates[["start"]], Editor = Editor * rates[["editor"]],
           Reader = Reader * rates[["reader"]], Pay = `Start fee` + Editor + Reader,
           per_proposal = Pay / Total) %>%
    select(member, proposals = Total, `Start fee`, Editor, Reader, Pay, per_proposal) %>%
    arrange(desc(Pay))
}

plot_pay <- function(counts, rates = pay_rates, split_readers = TRUE) {
  pay <- pay_table(counts, rates)
  # Reader pay, optionally split into reader 1 and reader 2 (same rate) to show how the roles are
  # shared.
  readers <- counts %>%
    filter(role %in% c("Reader 1", "Reader 2")) %>%
    mutate(role = if (split_readers) as.character(role) else "Reader") %>%
    group_by(member, role) %>% summarise(n = sum(n), .groups = "drop") %>%
    transmute(member, part = role, isk = n * rates[["reader"]])
  colours <- pay_colours[c("Start fee", "Editor", if (split_readers) c("Reader 1", "Reader 2") else "Reader")]
  parts <- pay %>%
    select(member, `Start fee`, Editor) %>%
    pivot_longer(-member, names_to = "part", values_to = "isk") %>%
    bind_rows(readers) %>%
    mutate(part = factor(part, levels = rev(names(colours))),
           member = factor(member, levels = rev(pay$member)))
  median_pay <- median(pay$Pay)

  ggplot(parts, aes(x = isk / 1000, y = member, fill = part)) +
    geom_col(width = 0.7, colour = "white", linewidth = 0.4) +
    geom_vline(xintercept = median_pay / 1000, linetype = "dashed", colour = "black", linewidth = 0.6) +
    annotate("label", x = median_pay / 1000, y = nrow(pay) + 0.9,
             label = sprintf("miðgildi %s", format(median_pay / 1000, big.mark = ".", decimal.mark = ",")),
             size = 3.4, fill = "white", linewidth = 0) +
    geom_text(data = pay, aes(x = Pay / 1000, y = member,
                              label = sprintf("%s (%s)", format(Pay / 1000, big.mark = ".", decimal.mark = ","),
                                              num_is(per_proposal / 1000))),
              inherit.aes = FALSE, hjust = 0, nudge_x = 3, size = 3, colour = "grey30") +
    scale_fill_manual(values = colours, breaks = names(colours), labels = tr, name = NULL) +
    scale_x_continuous(expand = expansion(mult = c(0, 0.15)), labels = scales::comma) +
    scale_y_discrete(expand = expansion(add = c(0.6, 1.4))) +
    labs(title = "Laun hvers fagráðsmanns í þessari umsóknarlotu",
         subtitle = sprintf(paste("Grunngjald %s + %s á hvert ritstjórahlutverk + %s á hvert",
                                  "lesarahlutverk, í þús. kr.
Merki: samtals (á umsókn)"),
                            rates[["start"]] / 1000, rates[["editor"]] / 1000, rates[["reader"]] / 1000),
         x = "Þúsundir króna", y = NULL) +
    theme_panel
}

# Distribution of pay per proposal over the members (thousand ISK).
plot_pay_distribution <- function(counts, rates = pay_rates) {
  pay <- pay_table(counts, rates) %>% mutate(k = per_proposal / 1000)
  med <- median(pay$k)
  ggplot(pay, aes(x = k)) +
    geom_histogram(binwidth = 0.5, boundary = 0, fill = role_colours[["Editor"]], colour = "white") +
    geom_vline(xintercept = med, linetype = "dashed", colour = "black") +
    annotate("label", x = med, y = Inf, vjust = 1.2, label = sprintf("miðgildi %s", num_is(med)),
             size = 3.4, fill = "white", linewidth = 0) +
    scale_x_continuous(breaks = seq(15, 25, 1), labels = function(x) format(x, decimal.mark = ",")) +
    scale_y_continuous(breaks = seq(0, 10, 1), expand = expansion(mult = c(0, 0.15))) +
    labs(title = "Dreifing greiðslu á umsókn",
         subtitle = "Hver súla telur fagráðsmenn á hálfs þúsunds bili",
         x = "Greiðsla á umsókn (þús. kr.)", y = "Fagráðsmenn") +
    theme_panel +
    theme(panel.grid.major.y = element_line(colour = "grey92"))
}

# Per member and meeting: how many of their proposals are discussed there (zeros included).
# Proposals that have reviewers but no meeting yet are counted under an extra "Unassigned" level.
unassigned <- "Unassigned"
meeting_counts <- function(panel) {
  panel %>%
    pivot_longer(all_of(names(role_labels)), values_to = "member") %>%
    filter(!is.na(member)) %>%
    # Only add the Unassigned column when some proposals with reviewers have no meeting.
    mutate(meeting = if (anyNA(meeting)) fct_na_value_to_level(meeting, level = unassigned) else meeting) %>%
    count(member, meeting, .drop = FALSE) %>%
    complete(member, meeting, fill = list(n = 0))
}

# Per member: number of meetings they need to attend (meetings with at least one of their
# proposals), the proposals in those meetings, and proposals not yet assigned to a meeting.
attendance_table <- function(panel) {
  meeting_counts(panel) %>%
    group_by(member) %>%
    summarise(meetings = sum(n > 0 & meeting != unassigned),
              proposals = sum(n[meeting != unassigned]),
              unassigned = sum(n[meeting == unassigned]), .groups = "drop") %>%
    arrange(desc(meetings), desc(proposals))
}

plot_attendance <- function(panel) {
  # Most meetings at the top; ties broken by number of proposals.
  attendance <- attendance_table(panel) %>%
    arrange(meetings, proposals) %>%
    mutate(member = factor(member, levels = member))
  n_meetings <- nlevels(panel$meeting)
  median_meetings <- median(attendance$meetings)

  ggplot(attendance, aes(x = meetings, y = member)) +
    geom_col(width = 0.7, fill = role_colours[["Editor"]]) +
    geom_vline(xintercept = median_meetings, linetype = "dashed", colour = "black",
               linewidth = 0.6) +
    geom_label(aes(x = median_meetings, y = nrow(attendance) + 0.9,
                   label = sprintf("miðgildi %g", median_meetings)),
               data = tibble(), inherit.aes = FALSE, size = 3.4, fill = "white", linewidth = 0) +
    # Shorthand label: proposals in those meetings (proposals not yet assigned to a meeting).
    geom_text(aes(label = if_else(unassigned > 0, sprintf("%d (%d)", proposals, unassigned),
                                  as.character(proposals))),
              hjust = 0, nudge_x = 0.1, size = 3.2, colour = "grey30") +
    scale_x_continuous(breaks = 0:n_meetings, limits = c(0, n_meetings + 0.9),
                       expand = expansion(mult = c(0, 0.02))) +
    scale_y_discrete(expand = expansion(add = c(0.6, 1.4))) +
    labs(title = "Fundir sem hver fagráðsmaður þarf að mæta á",
         subtitle = sprintf(paste0("Fundir með a.m.k. einni umsókn viðkomandi, af %d.\n",
                                   "Merki: umsóknir á þeim fundum (umsóknir sem eru ekki komnar á fund)"),
                            n_meetings),
         x = "Fundir", y = NULL) +
    theme_panel
}

plot_meetings <- function(panel) {
  per_meeting <- meeting_counts(panel) %>%
    mutate(group = if_else(meeting == unassigned, unassigned, "Meeting"))

  # Order members by the centre of their workload over the round (mean meeting number weighted by
  # proposals): early-heavy members at the top, late-heavy at the bottom, so the rows form a
  # diagonal that shows who finishes early and who starts late.
  centre <- per_meeting %>%
    filter(meeting != unassigned) %>%
    group_by(member) %>%
    summarise(centre = weighted.mean(as.integer(meeting), n), total = sum(n), .groups = "drop") %>%
    arrange(desc(centre), total)
  per_meeting <- per_meeting %>% mutate(member = factor(member, levels = centre$member))

  # Counts are small integers, so each gets its own step (light = 1 ... dark blue = max) to make
  # differences easy to see; meetings without any of the member's proposals are light grey.
  levels_n <- seq_len(max(per_meeting$n))
  step_colours <- setNames(hi_sequential(length(levels_n)), levels_n)
  per_meeting <- per_meeting %>%
    mutate(step = factor(if_else(n == 0, "none", as.character(n)), levels = c("none", levels_n)))

  # Under each meeting label: how many members attend it (have at least one proposal there).
  attending <- per_meeting %>% group_by(meeting) %>% summarise(k = sum(n > 0), .groups = "drop")
  meeting_label <- function(x) {
    k <- attending$k[match(x, as.character(attending$meeting))]
    if_else(x == unassigned, tr(x), paste0(x, "\n", k))
  }

  ggplot(per_meeting, aes(x = meeting, y = member, fill = step)) +
    geom_tile(colour = "white", linewidth = 0.6) +
    geom_text(aes(label = if_else(n > 0, as.character(n), ""),
                  colour = n >= ceiling(max(n) / 2)), size = 3) +
    scale_colour_manual(values = c(`TRUE` = "white", `FALSE` = "black"), guide = "none") +
    scale_fill_manual(values = c(none = "grey95", step_colours), breaks = as.character(levels_n),
                      name = "Umsóknir") +
    scale_x_discrete(labels = meeting_label) +
    labs(title = "Umsóknir á hvern fagráðsmann og fund",
         subtitle = paste("Raðað eftir því hvenær umsóknir viðkomandi eru teknar fyrir (snemma efst);",
                          "grátt = engin.\nTala undir fundi = fjöldi fagráðsmanna sem mæta"),
         x = NULL, y = NULL) +
    # The unassigned column sits in its own panel so it doesn't read as another meeting.
    facet_grid(cols = vars(fct_relevel(group, "Meeting")), scales = "free_x", space = "free_x") +
    theme_panel +
    theme(panel.grid = element_blank(), legend.position = "right",
          strip.text = element_blank(), panel.spacing.x = unit(10, "pt"))
}

if (sys.nframe() == 0) {
  out_dir <- "../data/tdf/figures"
  dir.create(out_dir, showWarnings = FALSE)
  panel <- read_panel("../data/tdf/panel.csv")
  load_new_members("../data/tdf/members.csv")
  counts <- role_counts(panel)
  print(spread_table(member_table(counts)))
  ggsave(file.path(out_dir, "workload_by_member.png"), plot_members(counts), width = 7, height = 6,
         dpi = 150)
  ggsave(file.path(out_dir, "workload_spread_by_role.png"), plot_spread(counts), width = 7,
         height = 3.2, dpi = 150)
  ggsave(file.path(out_dir, "attendance_by_member.png"), plot_attendance(panel), width = 7,
         height = 6, dpi = 150)
  ggsave(file.path(out_dir, "pay_by_member.png"), plot_pay(counts), width = 7, height = 6, dpi = 150)
  ggsave(file.path(out_dir, "workload_by_meeting.png"), plot_meetings(panel), width = 7, height = 6,
         dpi = 150)
}
