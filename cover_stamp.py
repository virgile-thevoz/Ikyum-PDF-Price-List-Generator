"""Stamps the "Rates from ..." date text (and a right-aligned "Sale
prices"/"Wholesale prices" mention on the same line -- front cover only,
see assemble_final_pdf) onto a cover PDF template.

Technique: draw the text onto a blank same-size overlay page with
reportlab, then merge that overlay onto the template's page with
pypdf's merge_page (standard watermark/stamp technique). The template's
own visual design (colors, images, layout) is untouched -- we only ever
draw text on top of it.
"""

import io
import os

from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

import print_marks
from print_layout import BOOKLET_PAGE_MULTIPLE

# Self-hosted Inter (SIL OFL 1.1, see static/fonts/OFL.txt), registered with
# reportlab under these names so config.json's date_stamp.font can select
# them. reportlab needs actual .ttf files -- static/fonts/*.woff (used by the
# web UI and the WeasyPrint price-table pages) were converted to .ttf once
# with fontTools; both are kept in sync as the same underlying typeface.
_FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "fonts")
_INTER_WEIGHTS = {
    "Inter": "Inter-Regular.ttf",
    "Inter-Medium": "Inter-Medium.ttf",
    "Inter-SemiBold": "Inter-SemiBold.ttf",
    "Inter-Bold": "Inter-Bold.ttf",
}
for _font_name, _filename in _INTER_WEIGHTS.items():
    pdfmetrics.registerFont(TTFont(_font_name, os.path.join(_FONTS_DIR, _filename)))


def _make_text_overlay(
    page_width_pt: float, page_height_pt: float, text: str, stamp_config: dict, secondary_text: str | None = None
) -> PdfReader:
    """Builds a single-page PDF, sized to match the template page, with
    `text` drawn at the configured position/font/size/color, and --  when
    given -- `secondary_text` drawn in the same font/size/color on the same
    line (stamp_config's y), right-aligned so its own right edge sits as far
    from the page's right edge as `text` sits from the left (mirroring the
    left margin as a right margin, for a symmetric look).
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(page_width_pt, page_height_pt))
    c.setFont(stamp_config["font"], stamp_config["font_size"])
    c.setFillColor(HexColor(stamp_config["color"]))
    c.drawString(stamp_config["x"], stamp_config["y"], text)
    if secondary_text:
        c.drawRightString(page_width_pt - stamp_config["x"], stamp_config["y"], secondary_text)
    c.save()
    buffer.seek(0)
    return PdfReader(buffer)


def stamp_pdf_page(template_path: str, text: str, stamp_config: dict, secondary_text: str | None = None):
    """Returns a pypdf page object: the template's first page with `text`
    (and, if given, `secondary_text` -- see _make_text_overlay) stamped
    onto it at the configured position.

    stamp_config's x/y are relative to the page's own /TrimBox -- its
    bottom-left corner, i.e. the true final cut size -- not the raw
    /MediaBox. For a plain trim-size template (no /TrimBox of its own,
    e.g. the original placeholder covers) those are the same box at the
    same (0, 0) origin, so this is a no-op change from just using the
    page directly. For a real print-ready export (from InDesign or
    similar) the /MediaBox usually extends beyond the trim to include
    bleed/crop-mark space, with /TrimBox inset somewhere inside it -- so
    the overlay is sized to the trim box and translated by its origin,
    landing the stamp inside the visible trim area instead of the
    (possibly much larger) full sheet.
    """
    template_reader = PdfReader(template_path)
    template_page = template_reader.pages[0]
    trim_box = template_page.trimbox
    trim_width = float(trim_box.width)
    trim_height = float(trim_box.height)

    overlay_reader = _make_text_overlay(trim_width, trim_height, text, stamp_config, secondary_text)
    template_page.merge_transformed_page(overlay_reader.pages[0], Transformation().translate(float(trim_box.left), float(trim_box.bottom)))
    return template_page


def _finish_cover_page(page, pdf_type: str):
    """Applies the bleed/marks treatment appropriate for `pdf_type` to an
    already-stamped cover or back-cover page (see print_marks.py's module
    docstring for the two situations this distinguishes):

    - "print": a real print-ready cover (print_marks.has_own_bleed(page))
      is used as-is, trusting the designer's own bleed and crop marks;
      a plain trim-size one (e.g. the original placeholder covers) gets
      print_marks.add_bleed_and_marks' fabricated treatment instead.
    - "web": always print_marks.crop_to_trim -- a no-op for an
      already-trim-size page, or strips a real cover's bleed margin back
      off so every page of the interactive PDF is the same clean trim
      size.
    """
    if pdf_type == "print":
        if print_marks.has_own_bleed(page):
            return page
        return print_marks.add_bleed_and_marks(page)
    return print_marks.crop_to_trim(page)


def assemble_final_pdf(
    cover_template_path: str,
    back_cover_template_path: str,
    price_table_pdf_bytes: bytes,
    date_stamp_text: str,
    cover_stamp_config: dict,
    back_cover_stamp_config: dict,
    pdf_type: str = "web",
    price_type_text: str | None = None,
) -> bytes:
    """Builds the final PDF: stamped cover + all price-table pages + stamped
    back cover, in that order.

    pdf_type "print" additionally: adds bleed + crop marks to the cover and
    back-cover pages, unless they already have their own (see
    _finish_cover_page/print_marks.py -- price_table_pdf_bytes is expected
    to already carry its own marks either way, via generate_pricelist.py's
    print-mode rendering), and pads the *final* page count up to a multiple
    of print_layout.BOOKLET_PAGE_MULTIPLE with blank marked filler pages,
    for saddle-stitch booklet printing. Fillers are inserted right before
    the back cover so it stays the physically last page of the printed
    booklet. pdf_type "web" crops the covers down to trim size instead, in
    case they came in with a real bleed margin of their own -- see
    _finish_cover_page.

    price_type_text, when given (build_pricelist.py always passes "Sale
    prices", in whichever language is active -- there's no separate
    "wholesale prices" wording; every generated PDF's cover reads "Sale
    prices" regardless of whether a resale multiplier was used), is
    stamped on the front cover only -- on the same line as
    date_stamp_text, right-aligned to mirror its left margin. Not stamped
    on the back cover: its own bottom-right corner is already occupied by
    the "www.ikyum.com" + QR code block, which the mirrored right margin
    lands on top of. Applies identically regardless of pdf_type: this is
    plain text stamped alongside the date, not affected by the
    bleed/crop-mark handling above.
    """
    writer = PdfWriter()

    cover_page = stamp_pdf_page(cover_template_path, date_stamp_text, cover_stamp_config, price_type_text)
    cover_page = _finish_cover_page(cover_page, pdf_type)
    writer.add_page(cover_page)

    # append(), not a page-by-page add_page() loop: the price-table PDF's
    # table of contents links to its own other pages via named destinations
    # (see generate_pricelist.py), which live in the *document catalog*, not
    # on individual pages. add_page() only copies pages one at a time and
    # silently drops that catalog-level structure, which would leave the
    # links pointing nowhere; append() clones the whole document including
    # its named-destinations tree, so the links keep working post-merge.
    price_table_reader = PdfReader(io.BytesIO(price_table_pdf_bytes))
    writer.append(price_table_reader)

    back_cover_page = stamp_pdf_page(back_cover_template_path, date_stamp_text, back_cover_stamp_config)
    back_cover_page = _finish_cover_page(back_cover_page, pdf_type)
    if pdf_type == "print":
        remainder = (len(writer.pages) + 1) % BOOKLET_PAGE_MULTIPLE  # +1 for the back cover about to be added
        for _ in range(BOOKLET_PAGE_MULTIPLE - remainder if remainder else 0):
            writer.add_page(print_marks.make_blank_marked_page())
    writer.add_page(back_cover_page)

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
