# IKYUM Price List Generator

Local-only tool: upload the client's price-list `.xlsx`, get back a finished
A5 PDF (cover, price tables in CHF + EUR side by side, back cover). Runs
entirely on your machine — no hosting, no auth, nothing ever leaves
localhost.

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

WeasyPrint needs Pango/Cairo installed at the OS level (already present on
this machine via Homebrew). If setting up fresh on another Mac:

```bash
brew install pango cairo gdk-pixbuf libffi
```

## First-time setup: placeholder covers + sample data

The real cover PDFs (designed in InDesign/Illustrator, one pair per
`pdf_type` — see "Cover templates: one pair per PDF type" below) already
exist for this project. If you ever need to regenerate placeholders instead
(e.g. testing without the real designs), or a sample workbook:

```bash
./venv/bin/python make_placeholder_covers.py   # overwrites whatever config.json's "covers" currently points to
./venv/bin/python make_sample_data.py          # -> sample_data.xlsx
```

**Careful:** by default that first command overwrites the real cover files,
since that's what `config.json` points to today — only run it if you
actually mean to replace them with placeholders (e.g. after repointing
`config.json` elsewhere first).

## Run

```bash
./venv/bin/python app.py
```

Open **http://127.0.0.1:5000**, upload the workbook, pick a currency
(CHF + EUR, CHF only, or EUR only — CHF + EUR is the default), an exchange
rate buffer, a resale price multiplier (None by default — see "Resale
price" below), a PDF type (Web or Print — see "PDF type: web vs print"
below), and optionally a file name, click Generate, download the PDF.

The file name field controls only the *downloaded* file's name (what your
browser saves it as) — leave it blank for an automatic
`pricelist_<timestamp>_<id>.pdf` name. Whatever you type is sanitized
(invalid filesystem characters stripped, a single `.pdf` extension
enforced) rather than rejected, so accented names like "Liste d'été" come
through untouched. See `sanitize_pdf_filename` in `app.py`.

The live rate is always fetched and both covers always read "Rates from
[date]", even for a CHF-only export where no conversion actually happens —
that keeps the covers consistent no matter which currency option is
picked.

## Language

The upload page and result page have an EN / FR / DE toggle, top right.
Picking a language sets a cookie (1 year) so it's remembered next time you
open the app, and it also carries through the upload → generate flow via a
hidden form field, so the result page comes back in whatever language you
picked on the upload page even though that's a separate request.

Translation strings live in `i18n.py` as a plain dict per language — add a
new key there (and to every language's dict) and reference it in a
template with `{{ t('your_key') }}`.

**Scope note:** mostly this only covers the app's own UI chrome — but two
pieces of actual *PDF* content follow the same language choice too:

- the "Rates from [date]" text stamped onto the cover and back-cover pages
  — both its label and the date format itself (`date_stamp.py`, which owns
  its own EN/FR/DE strings rather than reusing `i18n.py`, since it needs
  per-language month names and date-ordering rules, not just a label)
- the one translated word/phrase in the per-page footer at the bottom of
  every price-table page (`i18n.py`'s `"pdf_footer_role"` — "Mandataire
  autorisé" / "Authorized Representative" / "Bevollmächtigter") — see
  "Page footer" below

Everything else in the PDF — category/item names, descriptions — comes
straight from the workbook and is never touched, and the fallback-rate
warning message (which embeds a raw exception string) still isn't
translated, since it can't be meaningfully translated anyway.

## Test the full pipeline headlessly

```bash
./venv/bin/python test_pipeline.py
```

Runs the whole flow against `sample_data.xlsx` and the placeholder covers,
and checks: page count/order (cover → TOC → price pages → back cover), that
EUR values match `ROUND(CHF * buffered_rate, 2)`, that the date stamp text
appears on both cover pages, that the table of contents lists every
category, that every TOC link's destination resolves to the actual correct
final page number, and — for `pdf_type="print"` — that the final page
count is a multiple of 4, that no page carries a clickable link
annotation, and that every page (bar the back cover — see its known
size-mismatch note above) is grown to the bleed+marks size.

## Exchange rate

The upload page's "Exchange rate" choice, right above the buffer, controls
where the CHF→EUR rate itself comes from:

- **Daily rate** (default) — fetched live at generation time, subject to
  the buffer below.
- **Custom rate** — a rate the client types in themselves (e.g. `0.97`; a
  comma decimal separator like `0,97` works too), used *exactly* as
  entered for every EUR price in that PDF. No buffer on top, regardless of
  the buffer checkbox's state — the whole point is letting the client
  directly control the final price with a number they chose, not adding a
  hidden markup they didn't ask for (see `fx_rate.get_current_rate`'s
  `custom_rate` parameter). The result page reflects this: "Rate source:
  Custom (entered manually)", with no separate mid-market-rate/buffer
  lines, since neither applies.

The daily rate is fetched live at generation time from the
**[Frankfurter API](https://frankfurter.dev)** — free, no API key, sourced
from ECB reference rates.

> **Note on XE:** XE.com's own rate API is a paid product with no free tier.
> Frankfurter is a free equivalent tracking the same mid-market rate family,
> **not** literally XE's feed. If a paid XE subscription is added later,
> swap the fetch logic in `fx_rate.py` (`fetch_live_rate`) — everything else
> (buffer, fallback, rounding) stays the same.

A configurable buffer (`config.json` → `fx.buffer_percent`, default `1.0`
i.e. +1%) is added on top of the fetched daily mid-market rate before it's
used, to cover fluctuation between generation and actual use. Whether it's
applied at all is a per-generation choice, not just a config value — there's
a checkbox on the upload page ("Apply +1% buffer on top of the live rate"),
checked by default. Unchecking it doesn't change `config.json`, it just
uses the raw mid-market rate for that one PDF; the result page reflects
whichever actually happened ("Buffer applied: +1.0%" or "None (disabled)").
This only ever affects the daily rate — it's simply ignored when a custom
rate is chosen, whatever the checkbox says.

If the live fetch fails for any reason (network down, API error), the app
falls back to `config.json` → `fx.fallback_rate` and shows a visible warning
banner in the UI with the reason. (This fallback only applies to the daily
rate too — a custom rate never touches the live fetch in the first place,
so there's nothing to fall back from.)

EUR prices are computed as `ROUND(CHF * buffered_rate, 2)` for every price
cell at generation time. This is the **only** source of truth for EUR
prices — any "Exchange Rate" sheet or formulas left over in a workbook from
an older version are ignored.

## Resale price

Every price in the workbook is the manufacturer's **wholesale** price.
The upload page has a "Resale price multiplier" dropdown, right below the
exchange rate buffer: **None** (disabled, default — the plain
wholesale-price table) or one of **×0.5 / ×0.6 / ×0.7 / ×0.8 / ×0.9 /
×1.1 / ×1.2 / ×1.3 / ×1.4 / ×1.5** (-50% through +50%) — one multiplier
for the whole document, applied uniformly (see `generate_pricelist.py`'s
`apply_resale_multiplier` / `RESALE_MULTIPLIERS`).

Picking one **replaces** every wholesale price shown with its resale price
— `ROUND(wholesale price * multiplier, 2)` — rather than showing both side
by side, so the table's shape (Options, then one price column per active
currency) never changes regardless of whether a multiplier is chosen.

Resale is computed from each currency's own (already-rounded) wholesale
value directly — CHF resale from CHF wholesale, EUR resale from EUR
wholesale — rather than converting through the other currency, so "resale
= wholesale × multiplier" holds exactly in whichever currency column
you're actually looking at.

The front cover also always gets a price-type mention, stamped
right-aligned on the same line as the "Rates from ..." date stamp,
mirroring its left margin (see `cover_stamp.py`'s `price_type_text`):
**"Sale prices"** ("Prix de vente" / "Verkaufspreise") when a multiplier
is chosen, or **"Wholesale prices"** ("Prix d'achat" / "Einkaufspreise")
when it isn't — see `i18n.py`'s `pdf_sale_prices_label` /
`pdf_wholesale_prices_label`. Either way it flags which kind of price the
table shows: the client's own sale price, or the manufacturer's plain
wholesale price. It's front-cover only: the back cover's own
bottom-right corner already carries the `www.ikyum.com` + QR code block,
which the mirrored right margin would otherwise land on top of. Applies
identically to both PDF types.

## Editable prices

The upload page has an "Editable prices" checkbox (off by default). When
checked, every price cell in the generated PDF — and *only* price cells,
never item names, descriptions, headers, or the table of contents — becomes
a real, fillable PDF form field, pre-filled with the generated value. A
client opening the PDF in Acrobat, Preview, or any other AcroForm-capable
viewer can click a price and retype it; everything else in the document
stays fixed, ordinary text, exactly as it would without the checkbox.

This works with any currency mode and with resale pricing: whichever value
is actually shown in a cell (wholesale or resale, CHF and/or EUR) is what
the field is pre-filled with.

**How it's built** (see `editable_fields.py` for the full mechanics):
WeasyPrint has no concept of "editable" text — it only draws flat, static
ink — so this is a second pass over the already-rendered price-table PDF.
`generate_pricelist.py`'s price cells, when `editable_prices=True`, are
each wrapped in a same-document link to a dummy anchor; WeasyPrint turns
that into a real PDF link annotation whose `/Rect` happens to be the exact
bounding box of that price, at zero cost to how the table looks (the link
is styled to be visually invisible — inherited color, no underline).
`editable_fields.py` reads those Rects back out, in the same order
`generate_pricelist.price_field_values()` produces each price's string, and
replaces each link with a borderless, transparent AcroForm text field
(`reportlab`) sized to the exact same spot, then discards the link. The
table of contents' own links are unaffected — see the module's docstring
for how its `writer.append()`-based approach avoids the same
named-destinations pitfall `cover_stamp.py` already calls out for its own
cover/back-cover assembly step.

One limitation worth knowing: CHF and EUR are independently editable
fields, not linked by a formula — retyping a CHF price doesn't recompute
the EUR price next to it (PDF form fields can run JavaScript in Acrobat,
but that's not portable to Preview or other viewers, so this deliberately
keeps every field a plain, independent value rather than something that
only half-works outside Acrobat).

## Config

Everything you'll want to tune lives in `config.json`:

| Key | Meaning |
|---|---|
| `fx.buffer_percent` | Buffer added on top of the live mid-market rate |
| `fx.fallback_rate` | Manual rate used if the live fetch fails |
| `covers.web` / `covers.print` | Each a `{cover_template, back_cover_template}` pair of paths — see "Cover templates: one pair per PDF type" above |
| `date_stamp.cover` / `date_stamp.back_cover` | x/y (points, from bottom-left), font, size, color for the date stamp on each cover |

Re-run `make_placeholder_covers.py` after changing `date_stamp` positions to
see the updated placeholder marker box.

## Font

Everything — the upload page, the price-table pages, and the "Rates from
..." / "Sale prices" / "Wholesale prices" cover stamps — uses **Inter**, self-hosted under
`static/fonts/` (SIL Open Font License 1.1, see `static/fonts/OFL.txt`).
The cover stamps specifically use **Inter-Bold at 10pt** (`config.json`'s
`date_stamp.cover.font` / `date_stamp.back_cover.font`), matching the
weight and size of the cover templates' own nearby text (e.g. the front
cover's "IKYUM® — Verres ophtalmiques sur mesure." tagline).
It's fetched once as static `.woff` files (regular/medium/semibold/bold)
and used two ways:

- the web UI and the WeasyPrint price-table pages load the `.woff` files
  directly via `@font-face`
- the reportlab-based date stamp (`cover_stamp.py`) needs actual `.ttf`
  files, so `.ttf` versions were generated once from the same `.woff` files
  with `fontTools` and are registered under `Inter` / `Inter-Medium` /
  `Inter-SemiBold` / `Inter-Bold` — the names `config.json`'s
  `date_stamp.*.font` can reference

Nothing here calls out to Google Fonts (or anywhere else) at runtime — the
font files are committed locally so generation still works with no internet
connection. To pick a different typeface later, replace the files under
`static/fonts/` (keeping the same filenames) or repoint the `src: url(...)`
paths in `static/style.css` and `generate_pricelist.py`'s `PAGE_TEMPLATE`,
and the `_INTER_WEIGHTS` mapping in `cover_stamp.py`.

## Branding (web UI)

The upload/result pages' background is `#006db0` (`--bg` in
`static/style.css`) and the top-left logo is `static/logo.png` — the "K"
mark, extracted directly from an early cover design (the now-superseded
`cover-template.pdf`, still in the project root but no longer referenced
by `config.json` — see "Cover templates: one pair per PDF type" above)
with its transparency mask intact, rather than recreated by hand, so it's
pixel-identical to the real covers. It's rendered at a fixed 140px width via the `.logo`
CSS rule. To swap in a higher-resolution version later, replace
`static/logo.png` (any resolution works — it's always displayed at 140px
wide) and keep the filename the same, or update the `<img>` src in
`templates/index.html` / `templates/result.html`.

The background is also a photo (`static/background.jpg`, 2200px wide,
optimized down from the 20MB/4352×3238 original you provided — that
original is kept untouched at `static/background-original.jpg` if you ever
need to re-export at a different size). It's layered under a blue gradient
in `style.css`'s `body` rule: opaque `--bg` blue for roughly the top third
of the viewport, fading to fully transparent by ~80% down, so the photo
only really shows through toward the bottom. To adjust where the fade
happens, tweak the percentages in that `linear-gradient(...)` — to swap the
photo entirely, replace `static/background.jpg` (any resolution works,
though something in the 1800–2400px-wide range keeps the page fast) and
keep the filename.

This only affects the *web UI's* background and logo — it has no effect on
the actual PDF cover pages, which are entirely your own
`cover-template.pdf` / `back-cover-template.pdf` designs.

## Page footer

Every price-table page — the table of contents and every category page,
i.e. every page of the PDF *except* the cover and back cover, which are
separate pages handled entirely by `cover_stamp.py` — carries a small
company-info line at the bottom: "RedNnmore Sàrl. | [role] | Rte d'Yverdon
30 CH-1028 Préverenges | info@redNmore.com", where `[role]` is the one
part that follows the client's language choice (see "Language" above).

This used to be an embedded SVG logo (a "CH | REP" badge plus this same
text, outlined to vector paths in Illustrator) but that rendered with
visibly deformed glyphs — most likely a font-hinting/outline issue baked
into the exported SVG itself — so it was replaced with plain text
(`generate_pricelist.py`'s `FOOTER_TEXT_TEMPLATE`), which is guaranteed
legible since it's real text set in the document's own embedded font
rather than someone else's vector export. It shares the bottom margin row
with the running page number via two separate `@page` margin boxes
(`@bottom-center` for the footer text, `@bottom-right` for the page
number) rather than any manual position stacking.

## Table of contents

The price-table PDF opens with a table of contents (right after the cover):
one entry per category, each clickable and jumping straight to that
category's page, with the correct page number next to it — both computed
by WeasyPrint at layout time via plain CSS, not hand-calculated:

- the jump itself is a same-document link (`<a href="#section-N">` to
  `id="section-N"` on that category's page)
- the page number next to each entry is CSS's `target-counter()`, which
  asks WeasyPrint "what page does that link's target land on"

The one thing that *does* need manual handling: this PDF is generated
standalone, before the cover gets prepended to it, so it doesn't
automatically know the cover pushes its own page 1 forward. `build_pricelist.py`
reads the real cover PDF's page count and passes it in so the TOC's page
numbers (and the per-page footer numbers) reflect the *final* assembled
PDF, not a restart from 1. See the comment above `@page :first` in
`generate_pricelist.py`'s `PAGE_TEMPLATE` for exactly how that offset is
applied.

**A merge subtlety worth knowing if you touch `cover_stamp.py`:** these
links live in the PDF's document-level "named destinations" tree, not on
individual pages — so `assemble_final_pdf` uses pypdf's `writer.append()`
(clones a whole document, catalog included) for the price-table pages
rather than adding them one at a time with `add_page()` in a loop, which
would silently drop that tree and leave every TOC link pointing nowhere.
The cover and back cover are still added with `add_page()` since they're
single already-stamped pages with no internal links of their own to carry
over.

**Back to top:** every price-table page (web mode only — see "PDF type"
below) also carries a small "↑ Index" pill-shaped button in the top-right
corner, back to the table of contents (`.back-to-top` in
`generate_pricelist.py`, targeting the TOC's own `id="toc"`) — a discreet
way back to the index from anywhere in a long catalog, without needing
the PDF viewer's own page navigation. Styled with a light background,
border and rounded corners (rather than plain text) so it reads clearly
as tappable, and sits a bit down from the physical top edge — both for
easier use on touchscreen PDF viewers (e.g. iPad).

## PDF type: web vs print

The upload page has a "PDF type" choice, right below the exchange rate
buffer:

- **Web** (default) — today's interactive PDF: trim size only, clickable
  table of contents.
- **Print** — the same content, laid out for an actual booklet print run:
  - every page (cover, price-table pages, back cover) grows by a 3mm bleed
    plus a 5mm crop-mark margin on every side — see `print_layout.py` for
    the exact geometry, shared by `generate_pricelist.py` (which draws its
    own marks natively in CSS for the price-table pages) and
    `print_marks.py` (which draws the equivalent marks by hand with pypdf
    + reportlab for the cover/back-cover pages, since those are opaque
    pre-rendered PDFs WeasyPrint never sees).
  - the table of contents entries become plain, non-clickable text —
    still showing the correct page number (still computed by CSS
    `target-counter()`, just off a `data-target` attribute instead of an
    `href`), but with no PDF link annotations, since a printed booklet has
    nothing to click.
  - the **final** page count (cover through back cover) is padded with
    blank marked filler pages, inserted right before the back cover, up to
    a multiple of 4 — required for saddle-stitch booklet printing, where
    each physical sheet folds down to 4 pages.

### Cover templates: one pair per PDF type

`config.json`'s `"covers"` has a separate cover/back-cover pair per
`pdf_type` — `cover-template-web.pdf` / `back-cover-template-web.pdf` for
Web, `cover-template-print.pdf` / `back-cover-template-print.pdf` for
Print. The print pair are real InDesign exports with their own bleed and
crop marks already built in (a `/TrimBox` — the true A5 cut size — smaller
than the page's `/MediaBox`, which extends further out to include that
margin); the web pair happen to be the same kind of file here, but don't
need to be.

`print_marks.py` tells the two cases apart per page via `has_own_bleed()`
(`/TrimBox` smaller than `/MediaBox`) rather than assuming anything about
a given file, so it does the right thing either way:

- **Print mode**: a cover with its own bleed/marks (`has_own_bleed` true)
  is used as-is, trusting the designer's own treatment; a plain trim-size
  one (no `/TrimBox` of its own, e.g. if a placeholder ever needs
  regenerating — see `make_placeholder_covers.py`) falls back to
  `add_bleed_and_marks`, which fabricates a blank bleed margin and draws
  our own crop marks (`print_layout.py`'s 3mm bleed + 5mm mark geometry).
- **Web mode**: `crop_to_trim` strips a real cover's bleed margin back off
  (a no-op for an already trim-size one), so every page of the interactive
  PDF — including the covers — ends up the same clean 148 x 210mm.

`cover_stamp.stamp_pdf_page` positions the date stamp relative to each
page's own `/TrimBox` (its bottom-left corner) rather than the raw
`/MediaBox`, so `config.json`'s `date_stamp.cover`/`back_cover` x/y stay
correct regardless of how much (if any) bleed margin surrounds the trim
area.

**Page-size note:** the print cover pair's own bleed margin (measured off
the actual files: ~7.4mm per side) doesn't exactly match this project's
own 8mm bleed+marks margin used for the generated price-table pages and
blank filler pages — so in print mode, the cover/back-cover end up
~1.2mm smaller overall than the rest of the booklet. That's the designer's
own real bleed choice, not a bug, and well within normal commercial
trimming tolerance; `test_pipeline.py` accounts for it by excluding the
cover pages from its "every page is the canonical size" check.

## How it fits together

- **`generate_pricelist.py`** — reads every sheet in the workbook
  (openpyxl), auto-detects category sections from bold formatting, and
  renders the styled A5 price-table pages (WeasyPrint) — a table of
  contents page, then one small block per item with its priced options
  listed underneath. This is the core price-table generator described in
  the original brief.
- **`fx_rate.py`** — live CHF→EUR fetch + buffer + fallback.
- **`date_stamp.py`** — hand-written ordinal date formatter ("Rates from
  July 14th 2026") — deliberately not delegated to a date library, since
  most don't handle English ordinal suffixes (1st/2nd/3rd/11th–13th/21st...)
  out of the box.
- **`cover_stamp.py`** — draws the date-stamp text onto a blank overlay page
  (reportlab) and merges it onto the cover template page, positioned
  relative to the page's own `/TrimBox` (`pypdf`
  `merge_transformed_page`) — standard watermark-style stamping. The
  template's own design is never touched, only drawn on top of. Also
  applies the right bleed/crop-mark treatment per `pdf_type` (via
  `print_marks.py` — see "Cover templates: one pair per PDF type" above)
  and, for `pdf_type="print"`, pads the final page count to a multiple
  of 4.
- **`print_layout.py`** — shared bleed/crop-mark/booklet-multiple constants
  for the "print PDF" export mode (see "PDF type: web vs print" above).
- **`print_marks.py`** — adds bleed margin + crop marks to a trim-size PDF
  page by hand (pypdf + reportlab), or crops a real print-ready page's
  bleed margin back off — used for the cover, back-cover, and blank
  filler pages, since those are opaque pre-rendered PDFs that
  `generate_pricelist.py`'s WeasyPrint/CSS approach never sees.
- **`editable_fields.py`** — turns each price cell into a fillable PDF form
  field when `editable_prices=True` (see "Editable prices" above);
  otherwise unused.
- **`build_pricelist.py`** — orchestrates the above into one final PDF:
  stamped cover → TOC + price-table pages (→ `editable_fields.py`, if
  requested) → stamped back cover (`pypdf` `PdfWriter`).
- **`app.py`** — the local Flask upload UI.
- **`i18n.py`** — EN/FR/DE translations for the web UI only (not PDF
  content — see the Language section above).
- **`make_placeholder_covers.py`** / **`make_sample_data.py`** — one-off
  generators for local testing artifacts, useful again if a cover ever
  needs a placeholder regenerated or a workbook fixture is needed (real
  covers and real client workbooks are otherwise already in use).
- **`test_pipeline.py`** — automated end-to-end check, including that every
  TOC link resolves to the correct final page.

## Workbook format expected

Every visible sheet in the workbook is read (not just one named "Price
List"), except any sheet whose name contains "exchange rate" (case
insensitive) — that's treated as a legacy manual-rate sheet left over from
an older version of the file and is never a source of truth for prices.

Real IKYUM price lists aren't a flat "one item, one price" list — most
items have several priced *options* on the same row (e.g. a lens priced
per coating: HC, CLARITY, CLARITY BLUE PRO, MIRROR, ...). So each item is
parsed as a name + description + a **list** of (option label, price) pairs,
not a single price. A plain single-price row just becomes an item with one
option in that list.

**Row detection — column A's bold formatting is the primary signal:**

- **Category header row**: column A's cell is bold *and* has its own
  option-column labels in the other columns (text, e.g. `["HC", "CLARITY",
  "MIRROR"]` in columns B/C/D) — those labels apply to numeric cells in the
  item rows below it, until the next such header row, e.g. a later item's
  numeric price in column C is labelled "CLARITY". A header that doesn't
  repeat a label leaves that column's items showing the generic fallback
  label "Price" (this is legitimate for a genuinely single-price section —
  see "Section descriptions and sub-headings" below for the more common
  reason it used to show up everywhere).
- **Item row**: column A has text, and either isn't bold or *is* bold but
  carries a numeric price of its own (some workbooks bold a row for
  emphasis even though it's simultaneously a real priced item — that still
  needs its price recorded, not discarded). For each other cell:
  - a **number** → a priced option (labelled per the header row above)
  - `x` / `n/a` / `-` / `--` → that option isn't offered, skipped
  - any other text → folded into the item's description (e.g. a diameter
    or index range)
- Category sections that end up with zero items (a footnote row with no
  prices, a title immediately followed by another header, ...) are dropped
  silently rather than rendered as an empty page.

If a sheet has **no bold formatting at all**, detection falls back to a
simpler rule: a row with a name but no numeric cell anywhere is treated as
a header. Bold is preferred whenever it's present, since it directly
reflects the source author's intent and isn't fooled by a non-header row
that happens to have no priced options (a footnote, for instance).

**Section descriptions and sub-headings:** a bold, no-numeric-cell row with
*no* option-column labels of its own can't be a category header (it has no
labels to apply), so it never starts a new section or resets the current
labels — instead:

- the **first** such row under a section title becomes that section's
  description, shown as a subtitle right under the title in the PDF (e.g.
  a bold "Unifocal sur mesure" line under a "SINGLE RX" title)
- any **further** one in the same section (this happens when two
  formerly-separate sections get merged into one, e.g. single-vision and
  progressive variants of the same lens family sharing a title) is shown
  as a small heading above whichever item comes next, rather than being
  silently dropped

**Known limitation:** if a genuine item row is bold, has zero numeric
cells (all options unavailable), *and* has no text of its own in the other
columns, it'll be misread as a section description/sub-heading rather than
an item, since positionally there's no way to tell those cases apart. Give
it at least one price, or don't bold it, to avoid that.

See `make_sample_data.py` for a simple worked example (14 categories, one
price per item).

**On the page**, each item is rendered as its own small block: the item
name and description as a heading, then one row per priced option showing
`Options | CHF | EUR` (the column header is translated per language and
always plural — see `i18n.py`'s `pdf_option_column_label`). That keeps the page narrow enough for A5 even when an
item has many options — the tradeoff is that a workbook with lots of
multi-option items produces a proportionally long PDF (a full lens catalog
with ~280 items across 20 sections currently comes out to ~65 price-table
pages, plus the two cover pages).

## Not in scope right now

- Email sending (an earlier version had this; deferred, not wired up here)
- Any hosting/server/auth beyond localhost
- Actual XE.com paid-tier data (see the note above)
