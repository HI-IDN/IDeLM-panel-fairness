# Colour palette of all figures. Standard R palettes that are colour-blind friendly, so the colours
# are the same everywhere and are changed here and nowhere else:
#  * categories (roles, scenarios, members): Okabe-Ito, `grDevices::palette.colors()` (R >= 4.0);
#  * low-to-high values: viridis "mako", a blue-green scale close to the colours of the HÍ design
#    standard (https://honnun.hi.is/). Sourced by panel_workload.R and panel_schedule.R.

okabe <- grDevices::palette.colors(palette = "Okabe-Ito")
names(okabe) <- c("black", "orange", "sky_blue", "green", "yellow", "blue", "vermillion", "purple", "grey")

# Roles: editor blue, readers orange and green.
role_colours <- c("Editor" = okabe[["blue"]], "Reader" = okabe[["orange"]],
                  "Reader 1" = okabe[["orange"]], "Reader 2" = okabe[["green"]], "Total" = okabe[["grey"]])
pay_colours <- c("Start fee" = "grey85", role_colours[c("Editor", "Reader", "Reader 1", "Reader 2")])

# One colour per scenario, in the order of `scenarios`.
scenario_palette <- unname(okabe[c("grey", "blue", "sky_blue", "green", "orange", "vermillion", "purple")])

# Low-to-high values (counts, peel-off points, differences between scenarios): light to dark.
hi_sequential <- function(n) viridisLite::viridis(n, option = "mako", direction = -1, begin = 0.2, end = 0.9)

# Few / medium / many (the Sankey groups): the same scale.
tertile_colours <- setNames(hi_sequential(3), c("Fæstir", "Miðlungs", "Flestir"))

# Lower bound and incumbent of the solver (the gap figure).
gap_colours <- c("Besta lausn sem fannst" = okabe[["vermillion"]], "Neðra mark" = okabe[["blue"]])

# Highlight in the interactive figures.
hi_highlight <- okabe[["vermillion"]]

# One colour per member. With this many members no palette is fully colour-blind safe, so the
# Okabe-Ito colours are used in turn, then the same in a lighter shade; the codes label the bands.
member_colours <- function(members) {
  base <- unname(okabe[-c(1, 9)])
  lighter <- grDevices::rgb(t(1 - 0.55 * (1 - grDevices::col2rgb(base) / 255)))
  setNames(rep_len(c(base, lighter), length(members)), members)
}
