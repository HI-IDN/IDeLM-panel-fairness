# Colour palette of all figures: the HÍ design standard (https://honnun.hi.is/), the same colours
# as docs/_extensions/tungufoss/haskoli-islands/theme/_tokens.scss. Sourced by panel_workload.R
# and panel_schedule.R, so a colour is changed here and nowhere else.

hi <- c(blue = "#10099F", dark_blue = "#0A0668", turquoise = "#2DD2C0", green = "#00FFBA",
        yellow = "#FAC55B", coral = "#FC8484", orange = "#FFA05F", engineering = "#EB7125",
        ink = "#262626", muted = "#5D6872", border = "#E8E8E8", surface = "#F5F5F5")

# Mix a colour with white: share = 0 is the colour itself, 1 is white.
hi_tint <- function(colour, share) {
  rgb <- grDevices::col2rgb(colour) / 255
  grDevices::rgb(t(1 - (1 - share) * (1 - rgb)))
}

# Roles: the editor is the HÍ blue, the readers the warm colours.
role_colours <- c("Editor" = hi[["blue"]], "Reader" = hi[["orange"]],
                  "Reader 1" = hi[["orange"]], "Reader 2" = hi[["turquoise"]], "Total" = hi[["muted"]])
pay_colours <- c("Start fee" = hi[["border"]], role_colours[c("Editor", "Reader", "Reader 1", "Reader 2")])

# One colour per scenario, in the order of `scenarios`.
scenario_palette <- unname(hi[c("muted", "blue", "turquoise", "dark_blue", "coral", "engineering", "yellow")])

# Low-to-high values (counts, peel-off points): from a light tint to the dark HÍ blue.
hi_sequential <- function(n) grDevices::colorRampPalette(c(hi_tint(hi[["blue"]], 0.8), hi[["blue"]],
                                                           hi[["dark_blue"]]))(n)
# Below / above the middle: HÍ blue to white to coral (blue = low, as in the former RdBu).
hi_diverging <- function(n) grDevices::colorRampPalette(c(hi[["blue"]], "#FFFFFF", hi[["coral"]]))(n)

# Few / medium / many (the Sankey groups).
tertile_colours <- c("Fæstir" = hi[["yellow"]], "Miðlungs" = hi[["coral"]], "Flestir" = hi[["blue"]])

# Lower bound and incumbent of the solver (the gap figure).
gap_colours <- c("Besta lausn sem fannst" = hi[["engineering"]], "Neðra mark" = hi[["blue"]])

# Highlight in the interactive figures.
hi_highlight <- hi[["engineering"]]

# One distinct colour per member: the HÍ colours in turn, then the same in a lighter shade.
member_colours <- function(members) {
  base <- unname(hi[c("blue", "turquoise", "orange", "coral", "yellow", "dark_blue", "green", "engineering")])
  pool <- c(base, sapply(base, function(x) hi_tint(x, 0.45)))
  setNames(rep_len(pool, length(members)), members)
}
