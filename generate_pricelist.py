"""Core price-table PDF generator for IKYUM price lists.

Reads the client's price-list workbook (openpyxl), auto-detects the
product-category sections, computes EUR prices from a supplied CHF->EUR
rate, and renders styled A5 price-table pages (WeasyPrint) with CHF and EUR
shown side by side.

## Workbook shape this handles

Real IKYUM price lists aren't a flat "one item, one price" list -- most
items have several priced *options* on the same row (e.g. a lens with a
price per coating: HC, CLARITY, CLARITY BLUE PRO, MIRROR, ...). So each
parsed item carries a *list* of (option label, price) pairs rather than a
single price. A plain single-price row just ends up as an item with one
price entry.

Every visible sheet in the workbook is scanned (not just one named "Price
List"), except any sheet whose name contains "exchange rate" -- that's
assumed to be a legacy manual-rate sheet from an older version of the
workbook and is never a source of truth for prices (see fx_rate.py).

## Row detection

A row is a **category header** when column A's cell is bold. Any other
text-only cells on that same header row (columns B onward) become the
option labels used for numeric cells in the rows below it, until the next
header row -- e.g. a header row of ["HC", "CLARITY", "MIRROR"] in columns
B/C/D means a later item row's numeric price in column C is labelled
"CLARITY".

A row is an **item row** when column A has text and is not bold, and it
belongs to whichever header preceded it. For each other cell in that row:
  - a number is a priced option (labelled from the header row above, or
    generically "Price" if that column was never labelled)
  - "x" (or n/a, -, --) means that option isn't available and is skipped
  - any other text is a descriptive attribute (e.g. a diameter or index
    range) and gets folded into the item's description

If a sheet has no bold formatting at all, detection falls back to a
simpler rule: a row with a name but no numeric cell anywhere is treated as
a header. (Bold is tried first and preferred -- it directly reflects the
author's intent and isn't fooled by non-header rows that happen to have no
priced options, such as footnotes.)

A bold, no-numeric-cell row is only treated as a *new* header when it also
carries its own text option-labels in the other columns -- a bold row with
no other populated cells at all can't be defining a label set, so it's
never mistaken for a new section (see "Section descriptions and
sub-headings" below). And a bold row that *does* have numeric cells (some
real workbooks bold a row for emphasis even though it's simultaneously a
genuine priced item) is never treated as a header regardless of boldness --
it flows through as a normal item, using whichever labels are already in
scope, so its own prices aren't silently discarded.

Category sections that end up with zero items (e.g. a footnote row, or a
sheet title that's immediately followed by another header) are dropped
silently rather than rendered as an empty page.

## Section descriptions and sub-headings

Some sheets add one or two extra bold rows under a section's title that
carry a name in column A but no option-labels of their own in the other
columns. The first such row per section becomes that section's
`description` (a subtitle line shown right under the section title in the
PDF) -- it does not start a new section and does not reset the current
option labels, so items immediately below it keep showing their real
option names (HC, CLARITY, ...) instead of falling back to the generic
"Price" label.

Any *further* such row in the same section (this happens when two
formerly-separate sections get merged into one, e.g. "single vision" and
"progressive" variants of the same lens family sharing one title) is shown
as a small heading above whichever item comes next, rather than being
silently dropped -- see `pending_heading` in `_parse_sheet_rows`.

## Table of contents

This document's first page is a table of contents: one clickable entry per
category, each jumping straight to that category's page when clicked, with
the correct page number next to it. Both are computed by WeasyPrint itself
at layout time via plain CSS (`target-counter()` for the page numbers,
same-document `<a href="#section-N">` links for the jumps) -- nothing here
manually calculates page positions.

The one thing that does need manual handling: this document doesn't know
in isolation that a cover PDF will be prepended to it in the final
assembled PDF (see build_pricelist.py), so its own page counter would
otherwise start counting from 1 instead of the true final page number.
`cover_page_count` (passed in from the cover template's actual page count)
corrects for that via a single `@page :first { counter-reset: page ... }`
rule -- see the comment above that rule in PAGE_TEMPLATE for how it lines
up with cover_stamp.py's assembly step.

## PDF type: web vs print

Every generation picks one of two `pdf_type`s (see PDF_TYPES):

- **"web"** (default): today's interactive PDF -- trim size only, no
  bleed/marks, and a clickable table of contents (`<a href="#section-N">`
  entries, which WeasyPrint exports as real PDF link annotations).
- **"print"**: same content, laid out for a physical booklet print run --
  each page grows to trim size + 3mm bleed + crop marks on every side (see
  print_layout.py for the exact geometry, shared with print_marks.py which
  applies the equivalent treatment to the cover/back-cover pages), and the
  table of contents entries become plain non-clickable `<span>`s instead of
  `<a>`s -- same page numbers (still computed by `target-counter()`, just
  sourced from a `data-target` attribute instead of `href`), but no PDF
  link annotations, since a printed booklet has nothing to click.
  (Padding the *final* page count to a multiple of 4 for saddle-stitch
  booklet printing is handled one level up, in cover_stamp.py's
  assemble_final_pdf -- it's a whole-document concern, not something this
  module's own page count alone determines.)
"""

import os
from dataclasses import dataclass, field

import openpyxl
from jinja2 import Environment
from weasyprint import HTML

from print_layout import BLEED_MM, MARK_LENGTH_MM, MARK_MARGIN_MM, TRIM_HEIGHT_MM, TRIM_WIDTH_MM

# Project root, so the @font-face rules in PAGE_TEMPLATE (which reference
# "static/fonts/Inter-*.woff" as a relative path) resolve regardless of the
# process's current working directory.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

UNAVAILABLE_MARKERS = {"x", "n/a", "na", "-", "--"}


@dataclass
class PriceEntry:
    label: str
    chf: float
    eur: float = 0.0
    # Resale price = wholesale price (chf/eur above, straight from the
    # workbook) x a client-chosen multiplier (1.1-1.5) -- see
    # apply_resale_multiplier. Left at 0.0 and unused when no multiplier is
    # chosen (render_price_table_pdf's resale_multiplier=None, the default).
    chf_resale: float = 0.0
    eur_resale: float = 0.0


@dataclass
class Item:
    name: str
    description: str
    prices: list[PriceEntry] = field(default_factory=list)
    heading: str | None = None  # a sub-heading to show above this item, if any -- see _parse_sheet_rows


@dataclass
class Section:
    name: str
    items: list[Item] = field(default_factory=list)
    description: str = ""  # subtitle shown under the section title, if the workbook has one


def _is_bold(cell) -> bool:
    return bool(cell.font and cell.font.bold)


def _parse_sheet_rows(sheet, use_bold: bool) -> list[Section]:
    sections: list[Section] = []
    current: Section | None = None
    header_labels: dict[int, str] = {}
    pending_heading: str | None = None  # a sub-heading queued to attach to the next real item

    for row in sheet.iter_rows(min_row=1):
        name_obj = row[0]
        name_cell = name_obj.value
        if name_cell is None or (isinstance(name_cell, str) and not name_cell.strip()):
            continue  # blank separator row
        name_text = str(name_cell).strip()

        rest = [c.value for c in row[1:]]
        numeric_cols = [i for i, v in enumerate(rest) if isinstance(v, (int, float))]
        text_labels = {i: v.strip() for i, v in enumerate(rest) if isinstance(v, str) and v.strip()}

        # A numeric cell always disqualifies a row from being a header (see
        # the module docstring's "Row detection" section) -- checked first
        # so a bold-but-priced row (e.g. an emphasized "base variant" row)
        # still flows through as a normal item below instead of losing its
        # own prices.
        if use_bold:
            is_header = _is_bold(name_obj) and not numeric_cols
        else:
            is_header = not numeric_cols

        if is_header:
            if text_labels:
                # A genuine new section: it defines its own option-column
                # labels, same as every other real section does.
                current = Section(name=name_text)
                sections.append(current)
                header_labels = dict(text_labels)
                pending_heading = None
            elif current is not None:
                # No labels of its own, so this can't be starting a new
                # section -- it's auxiliary text for the CURRENT one (see
                # "Section descriptions and sub-headings" in the module
                # docstring): the first such row is the section's own
                # description, any further one is a heading for whichever
                # item comes next.
                if not current.description:
                    current.description = name_text
                else:
                    pending_heading = name_text
            continue

        if current is None:
            continue  # stray row before any header seen -- nothing to attach it to

        if not numeric_cols:
            continue  # named row with no priced option anywhere (e.g. a footnote) -- nothing to show

        attributes: list[str] = []
        prices: list[PriceEntry] = []
        for i, v in enumerate(rest):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                prices.append(PriceEntry(label=header_labels.get(i, "Price"), chf=float(v)))
            else:
                text = str(v).strip()
                if not text or text.lower() in UNAVAILABLE_MARKERS:
                    continue
                label = header_labels.get(i)
                attributes.append(f"{label}: {text}" if label else text)

        current.items.append(
            Item(name=name_text, description="; ".join(attributes), prices=prices, heading=pending_heading)
        )
        pending_heading = None

    return sections


def parse_sheet(sheet) -> list[Section]:
    """Parses one worksheet into sections, preferring bold-based header
    detection and falling back to the numeric-based heuristic if the sheet
    has no bold formatting at all (so nothing was detected).
    """
    sections = _parse_sheet_rows(sheet, use_bold=True)
    if not any(section.items for section in sections):
        sections = _parse_sheet_rows(sheet, use_bold=False)
    return sections


def parse_workbook(xlsx_path: str) -> list[Section]:
    """Reads every visible sheet (except legacy "Exchange Rate" sheets) and
    returns all detected category sections that have at least one item.
    """
    workbook = openpyxl.load_workbook(xlsx_path, data_only=True)
    sections: list[Section] = []
    for sheet in workbook.worksheets:
        if sheet.sheet_state != "visible":
            continue
        if "exchange rate" in sheet.title.strip().lower():
            continue
        sections.extend(parse_sheet(sheet))
    return [section for section in sections if section.items]


def apply_exchange_rate(sections: list[Section], buffered_rate: float) -> None:
    """Computes EUR = ROUND(CHF * rate, 2) for every priced option, in place."""
    for section in sections:
        for item in section.items:
            for price in item.prices:
                price.eur = round(price.chf * buffered_rate, 2)


RESALE_MULTIPLIERS = {0.5, 0.6, 0.7, 0.8, 0.9, 1.1, 1.2, 1.3, 1.4, 1.5}


def apply_resale_multiplier(sections: list[Section], multiplier: float | None) -> None:
    """Computes each priced option's resale price = ROUND(wholesale price *
    multiplier, 2), in both currencies, in place. Applied to each currency's
    own (already-rounded) wholesale value directly -- CHF_resale from CHF,
    EUR_resale from EUR -- rather than converting through the other
    currency, so "resale = wholesale x multiplier" holds exactly in
    whichever currency column the reader is actually looking at.

    A no-op when multiplier is None (the default -- no resale price chosen,
    matching today's plain wholesale-only table); render_price_table_pdf's
    own resale_multiplier controls whether the resulting values are shown
    at all, independent of whether this was ever called. When shown, the
    resale price *replaces* the wholesale price in the table rather than
    adding a second column next to it -- see render_price_table_pdf.
    """
    if multiplier is None:
        return
    if multiplier not in RESALE_MULTIPLIERS:
        raise ValueError(f"multiplier must be one of {RESALE_MULTIPLIERS} or None, got {multiplier!r}")
    for section in sections:
        for item in section.items:
            for price in item.prices:
                price.chf_resale = round(price.chf * multiplier, 2)
                price.eur_resale = round(price.eur * multiplier, 2)


PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  /* Self-hosted Inter (SIL OFL 1.1, see static/fonts/OFL.txt) -- resolved via
     the base_url passed to WeasyPrint's HTML(), not a network fetch, so this
     still renders with no internet connection. */
  @font-face {
    font-family: "Inter";
    font-style: normal;
    font-weight: 400;
    src: url("static/fonts/Inter-Regular.woff") format("woff");
  }
  @font-face {
    font-family: "Inter";
    font-style: normal;
    font-weight: 500;
    src: url("static/fonts/Inter-Medium.woff") format("woff");
  }
  @font-face {
    font-family: "Inter";
    font-style: normal;
    font-weight: 600;
    src: url("static/fonts/Inter-SemiBold.woff") format("woff");
  }
  @font-face {
    font-family: "Inter";
    font-style: normal;
    font-weight: 700;
    src: url("static/fonts/Inter-Bold.woff") format("woff");
  }
  @page {
    /* Web: trim size only (148mm x 210mm A5). Print: trim size plus the
       bleed + crop-mark margin on every side (see print_layout.py) -- the
       content margin below is padded out by that same amount so the
       actual table content sits at an identical position relative to the
       trim edge in both modes; only the surrounding sheet grows. */
    {% if pdf_type == 'print' %}
    size: {{ page_width_mm }}mm {{ page_height_mm }}mm;
    margin: {{ margin_top_mm }}mm {{ margin_right_mm }}mm {{ margin_bottom_mm }}mm {{ margin_left_mm }}mm;
    {% else %}
    size: {{ trim_width_mm }}mm {{ trim_height_mm }}mm;
    margin: {{ margin_top_mm }}mm {{ margin_right_mm }}mm {{ margin_bottom_mm }}mm {{ margin_left_mm }}mm;
    {% endif %}
    /* The company footer (address/legal line) and the running page number
       share this single margin row rather than stacking on separate lines:
       @bottom-left for the footer text, @bottom-right for the page number --
       CSS Paged Media's box-positioning keeps the two from colliding
       without any manual placement math. Same font-size for both, smaller
       than the rest of the document's small text, since neither is meant
       to draw attention. */
    @bottom-left {
      /* `| safe`: this is a CSS string, not HTML -- without it, Jinja's
         (correct, for HTML contexts) autoescaping would mangle the
         apostrophe in "d'Yverdon" into an HTML entity. footer_text is
         always a trusted, developer-composed string (see
         render_price_table_pdf), never user input, so bypassing
         autoescaping here is safe. */
      content: "{{ footer_text | safe }}";
      font-family: "Inter", "Helvetica Neue", Helvetica, Arial, sans-serif;
      font-size: 6pt;
      color: #999;
    }
    @bottom-right {
      content: counter(page);
      font-family: "Inter", "Helvetica Neue", Helvetica, Arial, sans-serif;
      font-size: 6pt;
      color: #999;
    }
  }
  /* The final PDF is cover(s) + this document + back cover, in that order,
     so this document's own page 1 (the table of contents) is actually final
     page {{ cover_page_count }} + 1. Resetting the "page" counter here --
     rather than leaving it to start at 1 -- keeps both the @bottom-right
     numbers above and the target-counter() page numbers in the table of
     contents below in sync with where pages actually land once assembled
     (see build_pricelist.py, which reads the real cover page count). */
  @page :first {
    counter-reset: page {{ cover_page_count + 1 }};
  }
  {% if pdf_type == 'print' %}
  /* Crop marks: fixed-position elements repeat at the same page-relative
     spot on every generated page (a WeasyPrint feature -- "fixed" behaves
     like "absolute", but repeats on every page instead of appearing once).
     Its containing block is the page *area* -- i.e. inside the @page
     margin above, not the physical sheet -- so each mark's top/right/
     bottom/left in _crop_mark_styles() is offset by a *negative* amount
     equal to that margin, which is what actually lets it reach out past
     the margin to the true sheet edge (confirmed empirically: WeasyPrint
     does not clip fixed content to the page area). Each mark starts
     exactly at the page edge and runs {{ mark_length_mm }}mm inward, leaving the
     {{ bleed_mm }}mm bleed area between it and the trim edge untouched -- see
     print_layout.py and print_marks.py (which draws the equivalent marks
     on the cover/back-cover pages) for the shared geometry. */
  .crop-mark {
    position: fixed;
    background: #000;
  }
  {% endif %}
  {% if pdf_type == 'web' %}
  /* Discreet per-page link back to the table of contents -- "fixed"
     repeats it on every page (same mechanism as the print mode's crop
     marks), sitting in the top margin above the section title so it never
     competes with the page's own content. Styled as a small pill button
     (background + border + rounded corners + padding), not plain text --
     both for a clearer tap affordance and a bigger touch target on
     touchscreens (e.g. iPad PDF viewers), and sits a bit further down
     from the physical top edge for the same reason -- easier to reach
     without fighting the viewer app's own top-edge chrome. Web mode
     only: print mode has no clickable links at all -- see the "PDF type"
     docstring section. */
  .back-to-top {
    position: fixed;
    top: -4mm;
    right: 0;
    display: inline-block;
    padding: 3pt 9pt;
    font-size: 7.5pt;
    color: #666;
    background: #f0f0f0;
    border: 0.5pt solid #ddd;
    border-radius: 9pt;
    text-decoration: none;
    letter-spacing: 0.2pt;
  }
  {% endif %}
  * { box-sizing: border-box; }
  body {
    font-family: "Inter", "Helvetica Neue", Helvetica, Arial, sans-serif;
    color: #1a1a1a;
    margin: 0;
  }
  .toc {
    page-break-after: always;
  }
  .toc-title {
    font-size: 12.6pt;
    font-weight: 700;
    letter-spacing: 0.4pt;
    text-transform: uppercase;
    border-bottom: 1.5pt solid #1a1a1a;
    padding-bottom: 5pt;
    margin: 0 0 10pt 0;
  }
  .toc-entry {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8pt;
    text-decoration: none;
    color: #1a1a1a;
    border-bottom: 0.5pt dotted #ccc;
    padding: 5pt 0;
    font-size: 8.55pt;
  }
  .toc-entry::after {
    color: #666;
    font-size: 7.65pt;
    flex: none;
  }
  /* Web mode's entries are <a href="#section-N">; print mode's are plain,
     non-clickable <span data-target="#section-N">s (see the body markup
     below) -- either way the page number is resolved the same way, via
     CSS target-counter(), just sourced from whichever attribute the
     element actually carries. */
  .toc-entry[href]::after {
    content: target-counter(attr(href), page);
  }
  .toc-entry[data-target]::after {
    content: target-counter(attr(data-target), page);
  }
  .section {
    page-break-before: always;
  }
  .section-title {
    font-size: 12.6pt;
    font-weight: 700;
    letter-spacing: 0.4pt;
    text-transform: uppercase;
    border-bottom: 1.5pt solid #1a1a1a;
    padding-bottom: 5pt;
    margin: 0 0 8pt 0;
  }
  .section-desc {
    color: #666;
    font-size: 8.55pt;
    margin: 0 0 10pt 0;
  }
  .item-block {
    page-break-inside: avoid;
    margin-bottom: 7pt;
  }
  .item-heading {
    font-size: 8.55pt;
    font-weight: 700;
    letter-spacing: 0.3pt;
    text-transform: uppercase;
    color: #444;
    margin: 0 0 5pt 0;
  }
  .item-name {
    font-size: 8.55pt;
    font-weight: 700;
    margin-bottom: 1pt;
  }
  .item-desc {
    color: #666;
    font-size: 6.75pt;
    margin-bottom: 2pt;
  }
  table.price-subtable {
    width: 100%;
    border-collapse: collapse;
    font-size: 7.2pt;
    margin-bottom: 2pt;
  }
  table.price-subtable th {
    text-align: left;
    font-size: 5.85pt;
    text-transform: uppercase;
    letter-spacing: 0.3pt;
    color: #999;
    padding: 1.5pt 4pt;
    border-bottom: 0.5pt solid #ccc;
  }
  table.price-subtable th.price-col,
  table.price-subtable td.price-col {
    text-align: right;
    white-space: nowrap;
    width: 22%;
  }
  table.price-subtable td {
    padding: 1.5pt 4pt;
  }
  table.price-subtable tbody tr:nth-child(even) {
    background: #f7f7f5;
  }
</style>
</head>
<body>
{% if pdf_type == 'print' %}
{% for mark in crop_marks %}
<div class="crop-mark" style="{% for prop, val in mark.items() %}{{ prop }}: {{ val }}; {% endfor %}"></div>
{% endfor %}
{% endif %}
{% if pdf_type == 'web' %}
<a class="back-to-top" href="#toc">&uarr; {{ index_label }}</a>
{% endif %}
<div class="toc" id="toc">
  <div class="toc-title">{{ index_label }}</div>
  {% for section in sections %}
  {% if pdf_type == 'print' %}
  <span class="toc-entry" data-target="#section-{{ loop.index }}">{{ section.name }}</span>
  {% else %}
  <a class="toc-entry" href="#section-{{ loop.index }}">{{ section.name }}</a>
  {% endif %}
  {% endfor %}
</div>
{% for section in sections %}
<div class="section" id="section-{{ loop.index }}">
  <div class="section-title">{{ section.name }}</div>
  {% if section.description %}<div class="section-desc">{{ section.description }}</div>{% endif %}
  {% for item in section.items %}
  <div class="item-block">
    {% if item.heading %}<div class="item-heading">{{ item.heading }}</div>{% endif %}
    <div class="item-name">{{ item.name }}</div>
    {% if item.description %}<div class="item-desc">{{ item.description }}</div>{% endif %}
    <table class="price-subtable">
      <thead>
        <tr>
          <th>{{ option_label }}</th>
          {% if show_chf %}<th class="price-col">CHF</th>{% endif %}
          {% if show_eur %}<th class="price-col">EUR</th>{% endif %}
        </tr>
      </thead>
      <tbody>
        {% for price in item.prices %}
        <tr>
          <td>{{ price.label }}</td>
          {# When a resale multiplier is chosen, its price *replaces* the
             wholesale price shown here rather than adding a second column
             next to it -- see apply_resale_multiplier. #}
          {% if show_chf %}<td class="price-col">{{ "%.2f"|format(price.chf_resale if show_resale else price.chf) }}</td>{% endif %}
          {% if show_eur %}<td class="price-col">{{ "%.2f"|format(price.eur_resale if show_resale else price.eur) }}</td>{% endif %}
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% endfor %}
</div>
{% endfor %}
</body>
</html>
"""


CURRENCY_MODES = {"chf", "eur", "both"}
PDF_TYPES = {"web", "print"}

# Content margins (from the trim edge), shared by both pdf_types -- print
# mode pads each of these out by MARK_MARGIN_MM (see the @page rule in
# PAGE_TEMPLATE) so the table content itself lands in the same place
# relative to the trim edge either way.
CONTENT_MARGIN_TOP_MM = 14.0
CONTENT_MARGIN_RIGHT_MM = 12.0
CONTENT_MARGIN_BOTTOM_MM = 18.0
CONTENT_MARGIN_LEFT_MM = 12.0

# The company footer line shown at the bottom of every page of this
# document -- i.e. every page except the cover and back cover, which are
# separate pages assembled by build_pricelist.py/cover_stamp.py and never
# touch this template. {role} is the one part that varies by language (see
# render_price_table_pdf's footer_role parameter and i18n.py's
# "pdf_footer_role" strings) -- the company name, address, and email are
# the same regardless of language.
#
# This used to be an embedded SVG logo (a "CH | REP" badge plus this same
# text, outlined to vector paths) but that rendered with visibly deformed
# glyphs -- most likely a font-hinting/outline issue in the exported SVG
# itself -- so it was dropped in favor of plain, guaranteed-legible text.
FOOTER_TEXT_TEMPLATE = "RedNnmore Sàrl. |  {role}  |  Rte d’Yverdon 30  CH-1028 Préverenges  |  info@redNmore.com"


def _crop_mark_styles(margin_top_mm: float, margin_right_mm: float, margin_bottom_mm: float, margin_left_mm: float) -> list[dict[str, str]]:
    """The inline CSS position for each of the 8 crop-mark line segments (2
    per corner x 4 corners) drawn in print mode, each a `position: fixed`
    div sized/placed with plain top/right/bottom/left/width/height.

    WeasyPrint's containing block for `position: fixed` is the page *area*
    (inside the @page margin), not the physical sheet -- so a mark meant to
    sit `trim_offset` mm from the true sheet edge needs a *negative* CSS
    offset of (trim_offset - that side's print-mode margin), which is
    confirmed to still render (WeasyPrint doesn't clip fixed content to the
    page area). A segment runs MARK_LENGTH_MM out from its page edge; see
    print_layout.py for why there's no separate gap value (the bleed area
    itself is the gap) and print_marks.py for the equivalent marks on the
    cover pages.
    """
    margins = {"top": margin_top_mm, "right": margin_right_mm, "bottom": margin_bottom_mm, "left": margin_left_mm}

    def offset(edge: str, trim_offset_mm: float) -> str:
        return f"{trim_offset_mm - margins[edge]}mm"

    length = f"{MARK_LENGTH_MM}mm"
    hairline = "0.25pt"
    styles = []
    for v_edge in ("top", "bottom"):
        for h_edge in ("left", "right"):
            # horizontal segment: runs along the trim edge's row
            styles.append({v_edge: offset(v_edge, MARK_MARGIN_MM), h_edge: offset(h_edge, 0), "width": length, "height": hairline})
            # vertical segment: runs along the trim edge's column
            styles.append({v_edge: offset(v_edge, 0), h_edge: offset(h_edge, MARK_MARGIN_MM), "width": hairline, "height": length})
    return styles


def render_price_table_pdf(
    sections: list[Section],
    currency_mode: str = "both",
    cover_page_count: int = 1,
    pdf_type: str = "web",
    footer_role: str = "Authorized Representative",
    index_label: str = "Index",
    option_label: str = "Options",
    resale_multiplier: float | None = None,
) -> bytes:
    """Renders a table of contents plus the category sections to a
    multi-page A5 PDF and returns the raw PDF bytes (no cover pages --
    those are stamped and merged separately, see build_pricelist.py).

    currency_mode selects which price column(s) are shown: "chf", "eur", or
    "both" (default).

    cover_page_count is the page count of the cover PDF that will precede
    this document in the final assembled PDF -- it's used purely to offset
    the page-number counter (@bottom-right footers, and the table of
    contents' page numbers) so they show the true final page number rather
    than restarting from 1. It has no effect on page order or content.

    pdf_type is "web" (default, today's interactive PDF) or "print" (bleed
    + crop marks, non-clickable table of contents) -- see the "PDF type"
    section of this module's docstring.

    footer_role, index_label, and option_label are already-translated
    (e.g. via i18n.py's translator) strings -- footer_role (e.g.
    "Mandataire autorisé", "Authorized Representative", "Bevollmächtigter")
    is slotted into FOOTER_TEXT_TEMPLATE for the footer shown at the bottom
    of every page; index_label (e.g. "Index", "Verzeichnis") is both the
    table of contents' own title and the word used in the "back to top"
    link (.back-to-top) on every other page; option_label (e.g. "Options",
    "Optionen") is the price sub-table's own column header, above each
    item's option names (HC, Clarity, Clarity Blue Pro, etc.) -- plural in
    every language, since an item can (and usually does) list more than
    one option. build_pricelist.py resolves all three via i18n.py before
    calling in, so this module itself stays uninvolved in language
    selection.

    resale_multiplier is None (default, today's plain wholesale-price
    table) or one of RESALE_MULTIPLIERS -- when set, every priced option's
    resale price (see apply_resale_multiplier, which must be called
    beforehand to actually populate PriceEntry.chf_resale/eur_resale)
    *replaces* its wholesale price in the table, rather than showing both;
    this parameter only controls which value is displayed, independent of
    whether apply_resale_multiplier was ever called.
    """
    if currency_mode not in CURRENCY_MODES:
        raise ValueError(f"currency_mode must be one of {CURRENCY_MODES}, got {currency_mode!r}")
    if pdf_type not in PDF_TYPES:
        raise ValueError(f"pdf_type must be one of {PDF_TYPES}, got {pdf_type!r}")
    if resale_multiplier is not None and resale_multiplier not in RESALE_MULTIPLIERS:
        raise ValueError(f"resale_multiplier must be one of {RESALE_MULTIPLIERS} or None, got {resale_multiplier!r}")

    is_print = pdf_type == "print"
    margin_top_mm = CONTENT_MARGIN_TOP_MM + (MARK_MARGIN_MM if is_print else 0)
    margin_right_mm = CONTENT_MARGIN_RIGHT_MM + (MARK_MARGIN_MM if is_print else 0)
    margin_bottom_mm = CONTENT_MARGIN_BOTTOM_MM + (MARK_MARGIN_MM if is_print else 0)
    margin_left_mm = CONTENT_MARGIN_LEFT_MM + (MARK_MARGIN_MM if is_print else 0)

    show_chf = currency_mode in ("chf", "both")
    show_eur = currency_mode in ("eur", "both")
    show_resale = resale_multiplier is not None

    env = Environment(autoescape=True)
    template = env.from_string(PAGE_TEMPLATE)
    html_content = template.render(
        sections=sections,
        show_chf=show_chf,
        show_eur=show_eur,
        cover_page_count=cover_page_count,
        pdf_type=pdf_type,
        trim_width_mm=TRIM_WIDTH_MM,
        trim_height_mm=TRIM_HEIGHT_MM,
        bleed_mm=BLEED_MM,
        mark_length_mm=MARK_LENGTH_MM,
        mark_margin_mm=MARK_MARGIN_MM,
        page_width_mm=TRIM_WIDTH_MM + 2 * MARK_MARGIN_MM,
        page_height_mm=TRIM_HEIGHT_MM + 2 * MARK_MARGIN_MM,
        margin_top_mm=margin_top_mm,
        margin_right_mm=margin_right_mm,
        margin_bottom_mm=margin_bottom_mm,
        margin_left_mm=margin_left_mm,
        crop_marks=_crop_mark_styles(margin_top_mm, margin_right_mm, margin_bottom_mm, margin_left_mm) if is_print else [],
        footer_text=FOOTER_TEXT_TEMPLATE.format(role=footer_role),
        index_label=index_label,
        option_label=option_label,
        show_resale=show_resale,
    )
    return HTML(string=html_content, base_url=PROJECT_ROOT).write_pdf()


def build_price_table_pdf(
    xlsx_path: str,
    buffered_rate: float,
    currency_mode: str = "both",
    cover_page_count: int = 1,
    pdf_type: str = "web",
    resale_multiplier: float | None = None,
) -> bytes:
    """Convenience entry point: parse workbook -> apply rate -> render PDF."""
    sections = parse_workbook(xlsx_path)
    apply_exchange_rate(sections, buffered_rate)
    apply_resale_multiplier(sections, resale_multiplier)
    return render_price_table_pdf(sections, currency_mode, cover_page_count, pdf_type, resale_multiplier=resale_multiplier)


if __name__ == "__main__":
    import sys

    xlsx_path = sys.argv[1] if len(sys.argv) > 1 else "sample_data.xlsx"
    rate = float(sys.argv[2]) if len(sys.argv) > 2 else 0.97
    pdf_type = sys.argv[3] if len(sys.argv) > 3 else "web"
    resale_multiplier = float(sys.argv[4]) if len(sys.argv) > 4 else None
    pdf_bytes = build_price_table_pdf(xlsx_path, rate, pdf_type=pdf_type, resale_multiplier=resale_multiplier)
    with open("price_table_only.pdf", "wb") as f:
        f.write(pdf_bytes)
    print(f"Wrote price_table_only.pdf ({len(pdf_bytes)} bytes) using rate {rate}, pdf_type={pdf_type}, resale_multiplier={resale_multiplier}")
