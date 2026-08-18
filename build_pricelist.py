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
from fx_rate import RateResult, get_current_rate, load_config
from generate_pricelist import apply_exchange_rate, parse_workbook, render_price_table_pdf


@dataclass
class BuildResult:
    pdf_bytes: bytes
    rate: RateResult
    date_stamp_text: str
    section_count: int
    item_count: int
    currency_mode: str


def build(
    xlsx_path: str,
    config: dict | None = None,
    currency_mode: str = "both",
    apply_buffer: bool = True,
) -> BuildResult:
    """currency_mode selects which price column(s) appear in the price
    table: "chf", "eur", or "both" (default). The live rate is always
    fetched and the cover date stamp always reads "Rates from ..." even for
    a CHF-only export, so the covers stay consistent regardless of which
    columns are shown.

    apply_buffer turns config.json's fx.buffer_percent on (default) or off
    for this generation -- see fx_rate.get_current_rate.
    """
    if config is None:
        config = load_config()

    rate = get_current_rate(config, apply_buffer=apply_buffer)

    covers = config["covers"]
    stamps = config["date_stamp"]

    # The table of contents (rendered as part of the price-table PDF) needs
    # to know how many pages precede it in the final assembled PDF, purely
    # to get its page numbers right -- see render_price_table_pdf's docstring.
    cover_page_count = len(PdfReader(covers["cover_template"]).pages)

    sections = parse_workbook(xlsx_path)
    apply_exchange_rate(sections, rate.buffered_rate)
    price_table_pdf = render_price_table_pdf(sections, currency_mode, cover_page_count)

    date_stamp_text = format_rate_date_stamp(rate.fetched_at)
    final_pdf = assemble_final_pdf(
        cover_template_path=covers["cover_template"],
        back_cover_template_path=covers["back_cover_template"],
        price_table_pdf_bytes=price_table_pdf,
        date_stamp_text=date_stamp_text,
        cover_stamp_config=stamps["cover"],
        back_cover_stamp_config=stamps["back_cover"],
    )

    item_count = sum(len(section.items) for section in sections)
    return BuildResult(
        pdf_bytes=final_pdf,
        rate=rate,
        date_stamp_text=date_stamp_text,
        section_count=len(sections),
        item_count=item_count,
        currency_mode=currency_mode,
    )
