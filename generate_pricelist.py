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

Category sections that end up with zero items (e.g. a footnote row, or a
sheet title that's immediately followed by another header) are dropped
silently rather than rendered as an empty page.

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
"""

import os
from dataclasses import dataclass, field

import openpyxl
from jinja2 import Environment
from weasyprint import HTML

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


@dataclass
class Item:
    name: str
    description: str
    prices: list[PriceEntry] = field(default_factory=list)


@dataclass
class Section:
    name: str
    items: list[Item] = field(default_factory=list)


def _is_bold(cell) -> bool:
    return bool(cell.font and cell.font.bold)


def _parse_sheet_rows(sheet, use_bold: bool) -> list[Section]:
    sections: list[Section] = []
    current: Section | None = None
    header_labels: dict[int, str] = {}

    for row in sheet.iter_rows(min_row=1):
        name_obj = row[0]
        name_cell = name_obj.value
        if name_cell is None or (isinstance(name_cell, str) and not name_cell.strip()):
            continue  # blank separator row
        name_text = str(name_cell).strip()

        rest = [c.value for c in row[1:]]
        numeric_cols = [i for i, v in enumerate(rest) if isinstance(v, (int, float))]

        is_header = _is_bold(name_obj) if use_bold else not numeric_cols

        if is_header:
            current = Section(name=name_text)
            sections.append(current)
            header_labels = {
                i: v.strip() for i, v in enumerate(rest) if isinstance(v, str) and v.strip()
            }
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

        current.items.append(Item(name=name_text, description="; ".join(attributes), prices=prices))

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
    size: 148mm 210mm; /* A5 */
    margin: 14mm 12mm 16mm 12mm;
    @bottom-center {
      content: counter(page);
      font-family: "Inter", "Helvetica Neue", Helvetica, Arial, sans-serif;
      font-size: 8pt;
      color: #999;
    }
  }
  /* The final PDF is cover(s) + this document + back cover, in that order,
     so this document's own page 1 (the table of contents) is actually final
     page {{ cover_page_count }} + 1. Resetting the "page" counter here --
     rather than leaving it to start at 1 -- keeps both the @bottom-center
     numbers above and the target-counter() page numbers in the table of
     contents below in sync with where pages actually land once assembled
     (see build_pricelist.py, which reads the real cover page count). */
  @page :first {
    counter-reset: page {{ cover_page_count + 1 }};
  }
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
    font-size: 14pt;
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
    font-size: 9.5pt;
  }
  .toc-entry::after {
    content: target-counter(attr(href), page);
    color: #666;
    font-size: 8.5pt;
    flex: none;
  }
  .section {
    page-break-before: always;
  }
  .section-title {
    font-size: 14pt;
    font-weight: 700;
    letter-spacing: 0.4pt;
    text-transform: uppercase;
    border-bottom: 1.5pt solid #1a1a1a;
    padding-bottom: 5pt;
    margin: 0 0 8pt 0;
  }
  .item-block {
    page-break-inside: avoid;
    margin-bottom: 7pt;
  }
  .item-name {
    font-size: 9.5pt;
    font-weight: 700;
    margin-bottom: 1pt;
  }
  .item-desc {
    color: #666;
    font-size: 7.5pt;
    margin-bottom: 2pt;
  }
  table.price-subtable {
    width: 100%;
    border-collapse: collapse;
    font-size: 8pt;
    margin-bottom: 2pt;
  }
  table.price-subtable th {
    text-align: left;
    font-size: 6.5pt;
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
<div class="toc">
  <div class="toc-title">Contents</div>
  {% for section in sections %}
  <a class="toc-entry" href="#section-{{ loop.index }}">{{ section.name }}</a>
  {% endfor %}
</div>
{% for section in sections %}
<div class="section" id="section-{{ loop.index }}">
  <div class="section-title">{{ section.name }}</div>
  {% for item in section.items %}
  <div class="item-block">
    <div class="item-name">{{ item.name }}</div>
    {% if item.description %}<div class="item-desc">{{ item.description }}</div>{% endif %}
    <table class="price-subtable">
      <thead>
        <tr>
          <th>Option</th>
          {% if show_chf %}<th class="price-col">CHF</th>{% endif %}
          {% if show_eur %}<th class="price-col">EUR</th>{% endif %}
        </tr>
      </thead>
      <tbody>
        {% for price in item.prices %}
        <tr>
          <td>{{ price.label }}</td>
          {% if show_chf %}<td class="price-col">{{ "%.2f"|format(price.chf) }}</td>{% endif %}
          {% if show_eur %}<td class="price-col">{{ "%.2f"|format(price.eur) }}</td>{% endif %}
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


def render_price_table_pdf(sections: list[Section], currency_mode: str = "both", cover_page_count: int = 1) -> bytes:
    """Renders a table of contents plus the category sections to a
    multi-page A5 PDF and returns the raw PDF bytes (no cover pages --
    those are stamped and merged separately, see build_pricelist.py).

    currency_mode selects which price column(s) are shown: "chf", "eur", or
    "both" (default).

    cover_page_count is the page count of the cover PDF that will precede
    this document in the final assembled PDF -- it's used purely to offset
    the page-number counter (@bottom-center footers, and the table of
    contents' page numbers) so they show the true final page number rather
    than restarting from 1. It has no effect on page order or content.
    """
    if currency_mode not in CURRENCY_MODES:
        raise ValueError(f"currency_mode must be one of {CURRENCY_MODES}, got {currency_mode!r}")

    env = Environment(autoescape=True)
    template = env.from_string(PAGE_TEMPLATE)
    html_content = template.render(
        sections=sections,
        show_chf=currency_mode in ("chf", "both"),
        show_eur=currency_mode in ("eur", "both"),
        cover_page_count=cover_page_count,
    )
    return HTML(string=html_content, base_url=PROJECT_ROOT).write_pdf()


def build_price_table_pdf(
    xlsx_path: str, buffered_rate: float, currency_mode: str = "both", cover_page_count: int = 1
) -> bytes:
    """Convenience entry point: parse workbook -> apply rate -> render PDF."""
    sections = parse_workbook(xlsx_path)
    apply_exchange_rate(sections, buffered_rate)
    return render_price_table_pdf(sections, currency_mode, cover_page_count)


if __name__ == "__main__":
    import sys

    xlsx_path = sys.argv[1] if len(sys.argv) > 1 else "sample_data.xlsx"
    rate = float(sys.argv[2]) if len(sys.argv) > 2 else 0.97
    pdf_bytes = build_price_table_pdf(xlsx_path, rate)
    with open("price_table_only.pdf", "wb") as f:
        f.write(pdf_bytes)
    print(f"Wrote price_table_only.pdf ({len(pdf_bytes)} bytes) using rate {rate}")
