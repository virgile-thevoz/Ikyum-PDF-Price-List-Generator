"""Turns the price values in an already-rendered price-table PDF into real,
fillable PDF form fields (AcroForm text fields) -- so a client can click a
price and retype it, while every other piece of text (item names,
descriptions, headers, the table of contents) stays plain, non-editable PDF
content, untouched.

## Why this can't just be "generate the PDF differently"

WeasyPrint (and PDF content streams in general) only know how to draw flat,
non-interactive ink -- there's no notion of "this text is editable" at that
level. Getting a genuinely fillable field requires attaching a proper
AcroForm /Widget annotation, positioned in PDF points, to the page -- a
structure WeasyPrint has no way to produce from HTML/CSS. So this module
does it as a second pass over the PDF WeasyPrint already produced.

## How a price's exact position is found

generate_pricelist.py's price_cell macro, when called with
editable_prices=True, wraps every rendered price in a same-document link
(`<a class="price-anchor" href="#price-anchor-target">`) that's styled to
be visually invisible (inherited color, no underline). WeasyPrint turns
that into a real PDF link annotation -- and a link annotation's /Rect is
the exact bounding box of the text it wraps. That gives pixel-exact
positions for free, without any text-scanning/OCR-style guessing: every
link annotation on a page whose /Dest is PRICE_ANCHOR_DEST is a price, in
the same left-to-right, top-to-bottom order the template rendered them in.

Those Rects are zipped against generate_pricelist.price_field_values(),
which walks the same sections/items/prices structure in the same order to
produce the exact string each price should default to -- so the field's
starting value always matches what the anchor at that Rect actually shows,
without re-reading text back out of the PDF.

## Building the actual fields

For each price's Rect, a one-field AcroForm overlay page is built with
reportlab (same "draw on a same-size overlay page" idea cover_stamp.py
uses for the date stamp) -- transparent, borderless by default, so the
table looks identical to the non-editable version until someone clicks a
price. reportlab's own PDF has no relation to the real document's pages,
so pypdf.merge_page (content-stream-only) can't be used to attach it the
way cover_stamp.py attaches the date stamp: an AcroForm field lives in
/Annots, which merge_page never touches. Instead, this borrows the
opposite direction -- the *content* is merged onto the field's own overlay
page (which keeps its own /Annots intact), and that combined page replaces
the original in the writer.

## Keeping the table of contents' links alive

The document's TOC links (see generate_pricelist.py) live in the PDF's
document-level named-destinations tree, not on individual pages -- exactly
the same subtlety cover_stamp.py's assemble_final_pdf already calls out
for its own writer.append() usage. This module preserves it the same way:
the whole document is cloned in with writer.append() first (which clones
the catalog, named-destinations tree included), and only *after* that are
the per-page field annotations spliced into the already-cloned pages --
never rebuilt page-by-page from scratch, which would silently drop that
tree and break every TOC link.
"""

import io

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, BooleanObject, DictionaryObject, NameObject, NumberObject
from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas

# Must match the id="..." target generate_pricelist.py's PAGE_TEMPLATE gives
# every price-anchor link -- the /Dest a price's link annotation carries.
PRICE_ANCHOR_DEST = "price-anchor-target"

FIELD_FONT = "Helvetica"  # a base-14 font, so no font file needs embedding
FIELD_FONT_SIZE = 7.2  # matches table.price-subtable's own font-size
FIELD_TEXT_COLOR = Color(0.102, 0.102, 0.102)  # #1a1a1a, same as the surrounding table text
# reportlab's textfield() treats a color argument of None as "use my own
# default" (a pale-blue fill + dark-grey border), not "draw nothing" --
# passing fully-transparent Color objects instead is what actually makes a
# field's fill/border invisible, so the table looks identical to the
# non-editable version until a price is clicked.
FIELD_TRANSPARENT = Color(0, 0, 0, alpha=0)
# A couple of points of breathing room around each price's tight text
# bounding box, so the field is comfortably clickable/editable without
# visually overlapping neighbouring cells.
FIELD_PADDING_X_PT = 2.0
FIELD_PADDING_Y_PT = 1.5


def _make_field_overlay(mediabox, rects_and_names: list[tuple[tuple[float, float, float, float], str, str]]) -> "PdfReader":
    """One overlay page, same size as `mediabox`, carrying one fillable text
    field per (rect, field_name, value) -- transparent and borderless, so it
    adds no visible mark of its own; the field itself is what makes that
    area clickable/editable once merged onto the real page.
    """
    width = float(mediabox.width)
    height = float(mediabox.height)
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width, height))
    form = c.acroForm
    for (x0, y0, x1, y1), name, value in rects_and_names:
        form.textfield(
            name=name,
            value=value,
            x=x0 - FIELD_PADDING_X_PT,
            y=y0 - FIELD_PADDING_Y_PT,
            width=(x1 - x0) + 2 * FIELD_PADDING_X_PT,
            height=(y1 - y0) + 2 * FIELD_PADDING_Y_PT,
            fontName=FIELD_FONT,
            fontSize=FIELD_FONT_SIZE,
            borderStyle="solid",
            borderWidth=0,
            borderColor=FIELD_TRANSPARENT,
            fillColor=FIELD_TRANSPARENT,
            textColor=FIELD_TEXT_COLOR,
        )
    c.showPage()
    c.save()
    buffer.seek(0)
    reader = PdfReader(buffer)
    # Right-align each field's typed value, matching .price-col's own
    # text-align: right -- reportlab's textfield() has no alignment
    # parameter, so this patches the field dict's /Q (quadding) directly
    # before it gets cloned into the real document.
    for annot in reader.pages[0].get("/Annots") or []:
        annot.get_object()[NameObject("/Q")] = NumberObject(2)
    return reader


def make_price_table_editable(price_table_pdf_bytes: bytes, field_values: list[str]) -> bytes:
    """Returns a copy of `price_table_pdf_bytes` where every price-anchor
    link (see generate_pricelist.py's editable_prices) has been replaced
    with a fillable AcroForm text field occupying the exact same spot, and
    is otherwise identical -- item names, descriptions, headers, and the
    table of contents (links included) are untouched.

    field_values must be generate_pricelist.price_field_values()'s output
    for the same sections/show_chf/show_eur/show_resale this PDF was
    rendered with -- its Nth entry becomes the Nth price-anchor field's
    starting value, in document order (top-to-bottom within a page,
    page order across pages). A length mismatch against the number of
    price-anchor links actually found means the PDF wasn't rendered with
    editable_prices=True against this same data, and raises ValueError
    rather than silently mismatching prices to fields.
    """
    reader = PdfReader(io.BytesIO(price_table_pdf_bytes))

    # writer.append(), not a page-by-page add_page() loop -- see this
    # module's docstring ("Keeping the table of contents' links alive").
    writer = PdfWriter()
    writer.append(reader)

    field_refs = []
    dr = None  # AcroForm /DR (default resources, e.g. the Helvetica font
    # dict field appearances reference) -- grabbed from the first overlay
    # built below and reused for the whole document's own /AcroForm.
    value_index = 0
    field_counter = 0
    # pypdf's IndirectObject.clone() caches its per-source-object translation
    # keyed by id(source_reader) (a raw memory address, via a dict on the
    # writer). A one-page-per-price overlay_reader built inside the loop
    # below is otherwise unreferenced once the loop moves on, so Python is
    # free to garbage-collect it and reuse its memory address for the *next*
    # overlay_reader -- and when that happens, pypdf's cache mistakes the
    # new reader for the old one and silently reuses (rather than clones) an
    # earlier page's field objects, quietly dropping the current page's own
    # fields. Keeping every overlay_reader alive here (it's cheap -- one
    # small in-memory PDF per page) for the rest of this call keeps every
    # id() distinct and sidesteps that collision entirely.
    _keep_alive: list = []

    for page in writer.pages:
        all_annots = page.get("/Annots")
        if not all_annots:
            continue
        price_annots = [a for a in all_annots if a.get_object().get("/Dest") == PRICE_ANCHOR_DEST]
        if not price_annots:
            continue

        rects_and_names = []
        for annot in price_annots:
            if value_index >= len(field_values):
                raise ValueError(
                    f"found more price-anchor links than field_values entries ({len(field_values)}) -- "
                    "field_values must come from price_field_values() for this exact PDF"
                )
            rect = tuple(float(v) for v in annot.get_object()["/Rect"])
            field_counter += 1
            rects_and_names.append((rect, f"price_{field_counter}", field_values[value_index]))
            value_index += 1

        overlay_reader = _make_field_overlay(page.mediabox, rects_and_names)
        _keep_alive.append(overlay_reader)
        if dr is None:
            dr = overlay_reader.trailer["/Root"]["/AcroForm"]["/DR"].clone(writer)

        # Drop the price-anchor links themselves -- they've done their job
        # (giving us exact Rects) and would otherwise sit underneath the
        # new fields as dead "jump to nowhere useful" hotspots. Any other
        # annotation on the page (e.g. the web-mode "back to top" link)
        # is kept as-is.
        kept_annots = [a for a in all_annots if a.get_object().get("/Dest") != PRICE_ANCHOR_DEST]
        if kept_annots:
            page[NameObject("/Annots")] = ArrayObject(kept_annots)
        else:
            del page[NameObject("/Annots")]

        # Clone each field annotation from the throwaway overlay document
        # into the real writer, and append it to this (already-cloned-in)
        # page's own /Annots -- see the docstring's "Building the actual
        # fields" for why the reverse (merging the page's content onto the
        # overlay page) isn't used here: we want to keep using *this*
        # page object, which writer.append() already wired into the
        # document's real page tree/named-destinations structure.
        annots_array = page.get("/Annots")
        if annots_array is None:
            page[NameObject("/Annots")] = ArrayObject()
            annots_array = page["/Annots"]
        for overlay_annot in overlay_reader.pages[0].get("/Annots") or []:
            cloned_ref = overlay_annot.clone(writer)
            annots_array.append(cloned_ref)
            field_refs.append(cloned_ref)

    if value_index != len(field_values):
        raise ValueError(
            f"found {value_index} price-anchor links but field_values has {len(field_values)} entries -- "
            "field_values must come from price_field_values() for this exact PDF"
        )

    if field_refs:
        acroform = DictionaryObject()
        acroform[NameObject("/Fields")] = ArrayObject(field_refs)
        # False: every field already carries its own /AP appearance stream
        # (reportlab builds one for each textfield()), so viewers don't
        # need to regenerate appearances themselves -- and some (Preview.app
        # in particular) render fields blank if asked to and don't.
        acroform[NameObject("/NeedAppearances")] = BooleanObject(False)
        if dr is not None:
            acroform[NameObject("/DR")] = dr
        writer._root_object[NameObject("/AcroForm")] = writer._add_object(acroform)

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
