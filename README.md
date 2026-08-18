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

The real cover PDFs (designed in InDesign/Illustrator) aren't built yet. For
local testing, generate simple placeholders and a sample workbook:

```bash
./venv/bin/python make_placeholder_covers.py   # -> cover-template.pdf, back-cover-template.pdf
./venv/bin/python make_sample_data.py          # -> sample_data.xlsx
```

Once the real `cover-template.pdf` / `back-cover-template.pdf` exist, drop
them in the project root (same filenames, or update `config.json`) and the
placeholders are no longer used.

## Run

```bash
./venv/bin/python app.py
```

Open **http://127.0.0.1:5000**, upload the workbook, pick a currency
(CHF + EUR, CHF only, or EUR only — CHF + EUR is the default), click
Generate, download the PDF.

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
template with `{{ t('your_key') }}`. **Scope note:** only the app's own UI
chrome is translated. The "Rates from [date]" text stamped onto the actual
PDF covers is not — it's produced by `date_stamp.py`'s hand-rolled English
ordinal formatter and stays in English regardless of the UI language,
since nothing in the brief called for translating PDF content, and the
fallback-rate warning message (which embeds a raw exception string) isn't
translated for the same reason it can't be meaningfully translated anyway.

## Test the full pipeline headlessly

```bash
./venv/bin/python test_pipeline.py
```

Runs the whole flow against `sample_data.xlsx` and the placeholder covers,
and checks: page count/order (cover → TOC → price pages → back cover), that
EUR values match `ROUND(CHF * buffered_rate, 2)`, that the date stamp text
appears on both cover pages, that the table of contents lists every
category, and that every TOC link's destination resolves to the actual
correct final page number.

## Exchange rate

The CHF→EUR rate is fetched live at generation time from the
**[Frankfurter API](https://frankfurter.dev)** — free, no API key, sourced
from ECB reference rates.

> **Note on XE:** XE.com's own rate API is a paid product with no free tier.
> Frankfurter is a free equivalent tracking the same mid-market rate family,
> **not** literally XE's feed. If a paid XE subscription is added later,
> swap the fetch logic in `fx_rate.py` (`fetch_live_rate`) — everything else
> (buffer, fallback, rounding) stays the same.

A configurable buffer (`config.json` → `fx.buffer_percent`, default `1.0`
i.e. +1%) is added on top of the fetched mid-market rate before it's used,
to cover fluctuation between generation and actual use. Whether it's
applied at all is a per-generation choice, not just a config value — there's
a checkbox on the upload page ("Apply +1% buffer on top of the live rate"),
checked by default. Unchecking it doesn't change `config.json`, it just
uses the raw mid-market rate for that one PDF; the result page reflects
whichever actually happened ("Buffer applied: +1.0%" or "None (disabled)").

If the live fetch fails for any reason (network down, API error), the app
falls back to `config.json` → `fx.fallback_rate` and shows a visible warning
banner in the UI with the reason.

EUR prices are computed as `ROUND(CHF * buffered_rate, 2)` for every price
cell at generation time. This is the **only** source of truth for EUR
prices — any "Exchange Rate" sheet or formulas left over in a workbook from
an older version are ignored.

## Config

Everything you'll want to tune lives in `config.json`:

| Key | Meaning |
|---|---|
| `fx.buffer_percent` | Buffer added on top of the live mid-market rate |
| `fx.fallback_rate` | Manual rate used if the live fetch fails |
| `covers.cover_template` / `covers.back_cover_template` | Paths to the cover PDFs |
| `date_stamp.cover` / `date_stamp.back_cover` | x/y (points, from bottom-left), font, size, color for the date stamp on each cover |

Re-run `make_placeholder_covers.py` after changing `date_stamp` positions to
see the updated placeholder marker box.

## Font

Everything — the upload page, the price-table pages, and the "Rates from
..." date stamp on both covers — uses **Inter**, self-hosted under
`static/fonts/` (SIL Open Font License 1.1, see `static/fonts/OFL.txt`).
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
mark, extracted directly from `cover-template.pdf` (with its transparency
mask intact) rather than recreated by hand, so it's pixel-identical to what
the real cover uses. It's rendered at a fixed 140px width via the `.logo`
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
  (reportlab) and merges it onto the cover template page (`pypdf`
  `merge_page`) — standard watermark-style stamping. The template's own
  design is never touched, only drawn on top of.
- **`build_pricelist.py`** — orchestrates the above into one final PDF:
  stamped cover → TOC + price-table pages → stamped back cover (`pypdf`
  `PdfWriter`).
- **`app.py`** — the local Flask upload UI.
- **`i18n.py`** — EN/FR/DE translations for the web UI only (not PDF
  content — see the Language section above).
- **`make_placeholder_covers.py`** / **`make_sample_data.py`** — one-off
  generators for local testing artifacts (not needed once real covers and
  real client workbooks are in use).
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

- **Category header row**: column A's cell is bold. Any other text-only
  cells on that row (columns B onward) become the option labels applied to
  numeric cells in the item rows below it — e.g. a header row of `["HC",
  "CLARITY", "MIRROR"]` in columns B/C/D means a later item's numeric price
  in column C is labelled "CLARITY". Labels reset at each new header row —
  a header that doesn't repeat a label leaves that column's items showing
  the generic fallback label "Price".
- **Item row**: column A has text and is *not* bold. For each other cell:
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

**Known limitation:** if a genuine item row is bold *and* has zero numeric
cells (all options unavailable), it will be misread as a new category
header, since positionally there's no way to tell those two cases apart.
Give it at least one price, or don't bold it, to avoid that.

See `make_sample_data.py` for a simple worked example (14 categories, one
price per item).

**On the page**, each item is rendered as its own small block: the item
name and description as a heading, then one row per priced option showing
`Option | CHF | EUR`. That keeps the page narrow enough for A5 even when an
item has many options — the tradeoff is that a workbook with lots of
multi-option items produces a proportionally long PDF (a full lens catalog
with ~280 items across 20 sections currently comes out to ~65 price-table
pages, plus the two cover pages).

## Not in scope right now

- Email sending (an earlier version had this; deferred, not wired up here)
- Any hosting/server/auth beyond localhost
- Actual XE.com paid-tier data (see the note above)
