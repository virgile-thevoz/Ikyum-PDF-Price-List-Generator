"""Stamps the "Rates from ..." date text onto a cover PDF template.

Technique: draw the text onto a blank same-size overlay page with
reportlab, then merge that overlay onto the template's page with
pypdf's merge_page (standard watermark/stamp technique). The template's
own visual design (colors, images, layout) is untouched -- we only ever
draw text on top of it.
"""

import io
import os

from pypdf import PdfReader, PdfWriter
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


def _make_text_overlay(page_width_pt: float, page_height_pt: float, text: str, stamp_config: dict) -> PdfReader:
    """Builds a single-page PDF, sized to match the template page, with the
    given text drawn at the configured position/font/size/color.
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(page_width_pt, page_height_pt))
    c.setFont(stamp_config["font"], stamp_config["font_size"])
    c.setFillColor(HexColor(stamp_config["color"]))
    c.drawString(stamp_config["x"], stamp_config["y"], text)
    c.save()
    buffer.seek(0)
    return PdfReader(buffer)


def stamp_pdf_page(template_path: str, text: str, stamp_config: dict):
    """Returns a pypdf page object: the template's first page with `text`
    stamped onto it at the configured position.
    """
    template_reader = PdfReader(template_path)
    template_page = template_reader.pages[0]
    page_width = float(template_page.mediabox.width)
    page_height = float(template_page.mediabox.height)

    overlay_reader = _make_text_overlay(page_width, page_height, text, stamp_config)
    template_page.merge_page(overlay_reader.pages[0])
    return template_page


def assemble_final_pdf(
    cover_template_path: str,
    back_cover_template_path: str,
    price_table_pdf_bytes: bytes,
    date_stamp_text: str,
    cover_stamp_config: dict,
    back_cover_stamp_config: dict,
    pdf_type: str = "web",
) -> bytes:
    """Builds the final PDF: stamped cover + all price-table pages + stamped
    back cover, in that order.

    pdf_type "print" additionally: adds bleed + crop marks to the cover and
    back-cover pages (print_marks.py -- price_table_pdf_bytes is expected to
    already carry its own, via generate_pricelist.py's print-mode
    rendering), and pads the *final* page count up to a multiple of
    print_layout.BOOKLET_PAGE_MULTIPLE with blank marked filler pages, for
    saddle-stitch booklet printing. Fillers are inserted right before the
    back cover so it stays the physically last page of the printed booklet.
    """
    writer = PdfWriter()

    cover_page = stamp_pdf_page(cover_template_path, date_stamp_text, cover_stamp_config)
    if pdf_type == "print":
        cover_page = print_marks.add_bleed_and_marks(cover_page)
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
    if pdf_type == "print":
        back_cover_page = print_marks.add_bleed_and_marks(back_cover_page)
        remainder = (len(writer.pages) + 1) % BOOKLET_PAGE_MULTIPLE  # +1 for the back cover about to be added
        for _ in range(BOOKLET_PAGE_MULTIPLE - remainder if remainder else 0):
            writer.add_page(print_marks.make_blank_marked_page())
    writer.add_page(back_cover_page)

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
