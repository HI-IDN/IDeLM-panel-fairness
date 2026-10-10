#!/usr/bin/env bash
# Renders the slides (glaerur.qmd) and copies them next to the book in _output/.
# The slides are not a book chapter, so `quarto render` of the book does not build them.
# Quarto runs it after every project render (`post-render` in _quarto.yml); it can also be run by hand.
set -euo pipefail
cd "$(dirname "$0")"
# Quarto sets these for the book render; the slides are rendered as a stand-alone file.
unset QUARTO_PROJECT_RENDER_ALL QUARTO_PROJECT_OUTPUT_FILES QUARTO_PROJECT_INPUT_FILES
# A failed slides build must not stop the book from being published.
if ! quarto render glaerur.qmd; then
  echo "WARNING: the slides could not be rendered; the book is unaffected." >&2
  exit 0
fi
mkdir -p _output
cp glaerur.html _output/
rm -rf _output/glaerur_files
cp -r glaerur_files _output/
# The pictures of the slides (img/) are not used by the book, so Quarto does not copy them.
mkdir -p _output/img
cp -r img/. _output/img/
