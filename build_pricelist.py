"""Orchestrates a full price-list generation run:

  1. fetch (or fall back on) the current CHF->EUR rate
  2. parse the uploaded workbook and compute EUR prices
  3. render the price-table pages
  4. stamp the date onto the cover + back cover templates
  5. assemble cover + price pages + back cover into the final PDF

Used by both app.py (the web UI) and test_pipeline.py (the automated
end-to-end check).
"""

from dataclasses import dataclass

from pypdf import PdfReader

from cover_stamp import assemble_final_pdf
from date_stamp import format_rate_date_stamp
from editable_fields import make_price_table_editable
from fx_rate import RateResult, get_current_rate, load_config
from generate_pricelist import (
    PDF_TYPES,
    apply_exchange_rate,
    apply_resale_multiplier,
    parse_workbook,
    price_field_values,
    render_price_table_pdf,
)
from i18n import get_translator


@dataclass
class BuildResult:
    pdf_bytes: bytes
    rate: RateResult
    date_stamp_text: str
    section_count: int
    item_count: int
    currency_mode: str
    pdf_type: str
    resale_multiplier: float | None
    editable_prices: bool


def build(
    xlsx_path: str,
    config: dict | None = None,
    currency_mode: str = "both",
    apply_buffer: bool = True,
    pdf_type: str = "web",
    lang: str = "en",
    resale_multiplier: float | None = None,
    custom_rate: float | None = None,
    editable_prices: bool = False,
) -> BuildResult:
    """currency_mode selects which price column(s) appear in the price
    table: "chf", "eur", or "both" (default). The live rate is always
    fetched and the cover date stamp always reads "Rates from ..." even for
    a CHF-only export, so the covers stay consistent regardless of which
    columns are shown.

    apply_buffer turns config.json's fx.buffer_percent on (default) or off
    for this generation -- see fx_rate.get_current_rate.

    custom_rate is None (default -- use the daily live/fallback rate,
    subject to apply_buffer) or a positive CHF->EUR rate the client typed
    in themselves, used exactly as given with no buffer on top -- see
    fx_rate.get_current_rate.

    pdf_type is "web" (default, today's interactive PDF) or "print" (bleed +
    crop marks, non-clickable table of contents, final page count padded to
    a multiple of 4 for booklet printing) -- see generate_pricelist.py's
    "PDF type" docstring section for the full picture.

    lang (one of i18n.SUPPORTED_LANGS, default English) localizes the pieces
    of PDF *content* that vary by language: the cover/back-cover date stamp
    (date_stamp.py -- both its label and the date format itself), the one
    translated word/phrase in the per-page footer (generate_pricelist.py's
    footer_role, via i18n.py's "pdf_footer_role"), the table of contents'
    title / "back to top" link text (index_label, via "pdf_index_label"),
    and each item's price sub-table column header (option_label, via
    "pdf_option_column_label" -- e.g. "Options"/"Optionen", plural in every
    language). Everything else in the PDF stays in whatever language the
    workbook's own category/item names are written in -- this only covers
    the app's own added text.

    resale_multiplier is None (default -- every price in the workbook is
    shown as-is, today's plain wholesale-price table) or one of
    generate_pricelist.RESALE_MULTIPLIERS (0.5-0.9, 1.1-1.5): every priced
    option's resale price, computed as ROUND(wholesale price * multiplier,
    2), then *replaces* its wholesale price in the table -- see
    apply_resale_multiplier. Either way, the front cover also gets a
    mention flagging which kind of price the table shows, on the same line
    as the date stamp, right-aligned -- see cover_stamp.assemble_final_pdf's
    price_type_text -- exactly one of "Sale prices"/"Prix de vente"/
    "Verkaufspreise" (resale_multiplier set) or "Wholesale prices"/
    "Prix d'achat"/"Einkaufspreise" (resale_multiplier is None) always
    appears. Not shown on the back cover (see assemble_final_pdf).

    editable_prices is False (default -- today's plain, flat PDF, nothing in
    it editable) or True: every price cell (and only price cells -- never
    item names, descriptions, or any other text) becomes a fillable PDF
    form field the client can click into and retype, pre-filled with the
    generated value. See editable_fields.py for how -- in short, a second
    pass over the already-rendered price-table pages that replaces
    generate_pricelist.py's price-anchor links with real AcroForm text
    fields at the exact same position, before the cover/back-cover pages
    are stamped and everything is assembled together.
    """
    if pdf_type not in PDF_TYPES:
        raise ValueError(f"pdf_type must be one of {PDF_TYPES}, got {pdf_type!r}")
    if config is None:
        config = load_config()

    rate = get_current_rate(config, apply_buffer=apply_buffer, custom_rate=custom_rate)

    # A separate cover/back-cover pair per pdf_type -- see config.json's
    # "covers" and cover_stamp.py's _finish_cover_page for what actually
    # distinguishes them (a real print-ready cover carries its own bleed
    # and crop marks; the "web" pair doesn't need any).
    covers = config["covers"][pdf_type]
    stamps = config["date_stamp"]
    t = get_translator(lang)
    footer_role = t("pdf_footer_role")
    index_label = t("pdf_index_label")
    option_label = t("pdf_option_column_label")
    price_type_text = t("pdf_sale_prices_label") if resale_multiplier is not None else t("pdf_wholesale_prices_label")

    # The table of contents (rendered as part of the price-table PDF) needs
    # to know how many pages precede it in the final assembled PDF, purely
    # to get its page numbers right -- see render_price_table_pdf's docstring.
    cover_page_count = len(PdfReader(covers["cover_template"]).pages)

    sections = parse_workbook(xlsx_path)
    apply_exchange_rate(sections, rate.buffered_rate)
    apply_resale_multiplier(sections, resale_multiplier)
    price_table_pdf = render_price_table_pdf(
        sections, currency_mode, cover_page_count, pdf_type, footer_role, index_label, option_label, resale_multiplier,
        editable_prices=editable_prices,
    )
    if editable_prices:
        show_chf = currency_mode in ("chf", "both")
        show_eur = currency_mode in ("eur", "both")
        field_values = price_field_values(sections, show_chf, show_eur, resale_multiplier is not None)
        price_table_pdf = make_price_table_editable(price_table_pdf, field_values)

    date_stamp_text = format_rate_date_stamp(rate.fetched_at, lang)
    final_pdf = assemble_final_pdf(
        cover_template_path=covers["cover_template"],
        back_cover_template_path=covers["back_cover_template"],
        price_table_pdf_bytes=price_table_pdf,
        date_stamp_text=date_stamp_text,
        cover_stamp_config=stamps["cover"],
        back_cover_stamp_config=stamps["back_cover"],
        pdf_type=pdf_type,
        price_type_text=price_type_text,
    )

    item_count = sum(len(section.items) for section in sections)
    return BuildResult(
        pdf_bytes=final_pdf,
        rate=rate,
        date_stamp_text=date_stamp_text,
        section_count=len(sections),
        item_count=item_count,
        currency_mode=currency_mode,
        pdf_type=pdf_type,
        resale_multiplier=resale_multiplier,
        editable_prices=editable_prices,
    )
