"""Adds bleed margin and crop marks to a trim-size PDF page, for the
"print PDF" export mode's cover and back-cover pages, plus blank filler
pages used to round the final page count up to a multiple of
`print_layout.BOOKLET_PAGE_MULTIPLE`.

`generate_pricelist.py` gets the same effect natively via CSS (see the
print-mode branch of its PAGE_TEMPLATE) because it controls that HTML
content directly. The covers are opaque, already-rendered PDF pages that
WeasyPrint never sees, so their bleed/marks have to be added by hand here
with pypdf and reportlab -- using the exact same `print_layout` constants,
so every page in the final print PDF ends up the same size regardless of
which of the two code paths produced it.

Two cover situations are handled, distinguished by has_own_bleed():

- **a plain trim-size cover** (no /TrimBox of its own, e.g. the original
  placeholder covers): add_bleed_and_marks() fabricates a bleed margin
  (left blank -- see its docstring) and draws our own crop marks.
- **a real print-ready export** (from InDesign or similar, /TrimBox
  smaller than /MediaBox -- e.g. the actual IKYUM cover designs): already
  has its own bleed and marks baked in by the designer, so it's used
  as-is in print mode, and crop_to_trim() strips that margin back off for
  web mode (where every page should be the same clean trim size).
"""

import io

from pypdf import PageObject, PdfReader, Transformation
from reportlab.pdfgen import canvas

from print_layout import BLEED_MM, MARK_LENGTH_MM, MARK_LINE_WIDTH_PT, MM_TO_PT, TRIM_HEIGHT_MM, TRIM_WIDTH_MM

MARK_MARGIN_PT = (BLEED_MM + MARK_LENGTH_MM) * MM_TO_PT
MARK_LENGTH_PT = MARK_LENGTH_MM * MM_TO_PT


def _draw_crop_marks(c: canvas.Canvas, page_width_pt: float, page_height_pt: float) -> None:
    """Draws the 8 crop-mark line segments (2 per corner) for a page whose
    trim box is inset by MARK_MARGIN_PT from every edge -- i.e. each mark
    starts exactly at the page edge and runs MARK_LENGTH_PT inward, leaving
    the bleed area (between the mark and the trim edge) untouched.
    """
    c.setLineWidth(MARK_LINE_WIDTH_PT)
    c.setStrokeColorRGB(0, 0, 0)

    left, right = MARK_MARGIN_PT, page_width_pt - MARK_MARGIN_PT
    bottom, top = MARK_MARGIN_PT, page_height_pt - MARK_MARGIN_PT
    length = MARK_LENGTH_PT

    segments = [
        # bottom-left corner
        (0, bottom, length, bottom), (left, 0, left, length),
        # bottom-right corner
        (page_width_pt - length, bottom, page_width_pt, bottom), (right, 0, right, length),
        # top-left corner
        (0, top, length, top), (left, page_height_pt - length, left, page_height_pt),
        # top-right corner
        (page_width_pt - length, top, page_width_pt, top), (right, page_height_pt - length, right, page_height_pt),
    ]
    for x1, y1, x2, y2 in segments:
        c.line(x1, y1, x2, y2)


def _marks_only_page(page_width_pt: float, page_height_pt: float):
    """A pypdf page containing nothing but the crop marks, sized exactly
    page_width_pt x page_height_pt -- used both as an overlay (merged onto
    a page carrying real content) and as a complete blank filler page.
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(page_width_pt, page_height_pt))
    _draw_crop_marks(c, page_width_pt, page_height_pt)
    c.save()
    buffer.seek(0)
    return PdfReader(buffer).pages[0]


def has_own_bleed(page: PageObject) -> bool:
    """True if `page` already ships with its own bleed/crop-mark margin --
    i.e. it's a real print-ready export (from InDesign or similar) whose
    /TrimBox is smaller than its /MediaBox, with the trim area inset
    somewhere inside the larger sheet. False for a plain trim-size page (no
    separate /TrimBox, so pypdf's `.trimbox` falls back to `.mediabox` and
    the two compare equal) -- e.g. the original placeholder covers, which
    still need add_bleed_and_marks' treatment. See that function and
    cover_stamp.assemble_final_pdf for how this decides whether to trust a
    cover's own bleed/marks or fabricate a plain one.
    """
    trim = page.trimbox
    media = page.mediabox
    return float(trim.width) < float(media.width) or float(trim.height) < float(media.height)


def crop_to_trim(page: PageObject) -> PageObject:
    """Crops `page` down to its own /TrimBox in place, discarding any
    surrounding bleed/crop-mark margin -- the "web PDF" counterpart to
    add_bleed_and_marks, so a cover exported with real bleed built in
    (has_own_bleed(page) is True) still ends up the same clean trim size as
    the rest of the interactive PDF. A no-op if the page has no bleed
    margin of its own (has_own_bleed(page) is False) -- it's already
    trim-size.

    Only the page's box metadata changes here (which region is "visible"),
    not its content stream's coordinate space -- so anything already
    stamped onto the page (see cover_stamp.stamp_pdf_page, which positions
    relative to /TrimBox for exactly this reason) stays correctly placed.
    """
    if has_own_bleed(page):
        page.mediabox = page.trimbox
        page.cropbox = page.trimbox
    return page


def add_bleed_and_marks(page: PageObject) -> PageObject:
    """Returns a new page: `page`'s own content centered on a larger canvas
    (page size + 2*MARK_MARGIN_PT on each dimension), with crop marks drawn
    at the true trim corners. `page`'s own design is untouched -- see
    print_layout.py's docstring for why the bleed area is left blank rather
    than fabricating extended artwork.

    Only meant for a plain trim-size page (has_own_bleed(page) is False) --
    callers should use `page` as-is when it already has its own bleed/marks
    baked in, rather than adding this as a redundant second layer on top;
    see has_own_bleed and cover_stamp.assemble_final_pdf.
    """
    trim_width_pt = float(page.mediabox.width)
    trim_height_pt = float(page.mediabox.height)
    new_width_pt = trim_width_pt + 2 * MARK_MARGIN_PT
    new_height_pt = trim_height_pt + 2 * MARK_MARGIN_PT

    new_page = PageObject.create_blank_page(width=new_width_pt, height=new_height_pt)
    new_page.merge_transformed_page(page, Transformation().translate(MARK_MARGIN_PT, MARK_MARGIN_PT))
    new_page.merge_page(_marks_only_page(new_width_pt, new_height_pt))
    return new_page


def make_blank_marked_page() -> PageObject:
    """A content-free filler page at the canonical A5 trim size (matching
    the cover and price-table pages), with crop marks only -- used to pad
    a print PDF's final page count up to a multiple of
    print_layout.BOOKLET_PAGE_MULTIPLE.
    """
    width_pt = TRIM_WIDTH_MM * MM_TO_PT + 2 * MARK_MARGIN_PT
    height_pt = TRIM_HEIGHT_MM * MM_TO_PT + 2 * MARK_MARGIN_PT
    blank = PageObject.create_blank_page(width=width_pt, height=height_pt)
    blank.merge_page(_marks_only_page(width_pt, height_pt))
    return blank
