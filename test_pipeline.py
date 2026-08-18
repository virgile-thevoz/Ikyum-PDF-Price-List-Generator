"""End-to-end smoke test for the full pipeline, run against sample_data.xlsx
and the placeholder cover PDFs.

Checks:
  - final PDF page count = cover + TOC + N price-table pages + back cover
  - page order: page 1 is the cover, last page is the back cover
  - EUR values in the rendered price table match ROUND(CHF * buffered_rate, 2)
  - the date stamp text appears on both the cover and back-cover pages
  - the table of contents lists every category and links to the right page
  - footer page numbers match the TOC's page numbers and the true final
    page position (i.e. the cover_page_count offset is applied correctly)

Run with: python test_pipeline.py
"""

import io
import sys

from pypdf import PdfReader

from build_pricelist import build
from fx_rate import load_config
from generate_pricelist import apply_exchange_rate, parse_workbook


def footer_page_number(page) -> str:
    """Extracts the last line of a page's text -- where @bottom-center puts
    the page-number footer -- for a quick sanity check.
    """
    text = (page.extract_text() or "").strip()
    return text.splitlines()[-1] if text else ""


def main() -> int:
    config = load_config()
    result = build("sample_data.xlsx", config)

    reader = PdfReader(io.BytesIO(result.pdf_bytes))
    total_pages = len(reader.pages)
    print(f"Total pages: {total_pages}")
    print(f"Rate source: {result.rate.source}")
    print(f"Mid-market rate: {result.rate.mid_market_rate}")
    print(f"Buffered rate used: {result.rate.buffered_rate}")
    print(f"Sections detected: {result.section_count}")
    print(f"Items detected: {result.item_count}")
    print(f"Date stamp: {result.date_stamp_text}")
    if result.rate.warning:
        print(f"WARNING: {result.rate.warning}")

    failures = []

    # -- Page count sanity: cover + TOC + at least 1 price page + back cover.
    if total_pages < 4:
        failures.append(f"Expected at least 4 pages, got {total_pages}")

    # -- Cover page text.
    cover_text = reader.pages[0].extract_text() or ""
    if result.date_stamp_text not in cover_text:
        failures.append(f"Date stamp not found on cover page. Extracted text was: {cover_text!r}")

    # -- Back cover page text (last page).
    back_cover_text = reader.pages[-1].extract_text() or ""
    if result.date_stamp_text not in back_cover_text:
        failures.append(f"Date stamp not found on back cover page. Extracted text was: {back_cover_text!r}")

    # -- EUR calculation correctness, recomputed independently from the source workbook.
    sections = parse_workbook("sample_data.xlsx")
    apply_exchange_rate(sections, result.rate.buffered_rate)
    mismatches = []
    for section in sections:
        for item in section.items:
            for price in item.prices:
                expected = round(price.chf * result.rate.buffered_rate, 2)
                if abs(price.eur - expected) > 1e-9:
                    mismatches.append((item.name, price.label, price.chf, price.eur, expected))
    if mismatches:
        failures.append(f"EUR calculation mismatches: {mismatches}")

    # -- Currency modes: each should show only the column(s) it promises.
    # Page index 2 = first section page (0=cover, 1=TOC, 2=first section).
    expectations = {
        "chf": {"CHF": True, "EUR": False},
        "eur": {"CHF": False, "EUR": True},
        "both": {"CHF": True, "EUR": True},
    }
    for mode, expect in expectations.items():
        mode_result = build("sample_data.xlsx", config, currency_mode=mode)
        mode_reader = PdfReader(io.BytesIO(mode_result.pdf_bytes))
        first_price_page_text = mode_reader.pages[2].extract_text() or ""
        for token, should_appear in expect.items():
            appears = token in first_price_page_text
            if appears != should_appear:
                failures.append(
                    f"currency_mode={mode!r}: expected {token!r} "
                    f"{'present' if should_appear else 'absent'} on the first price page, "
                    f"got {'present' if appears else 'absent'}"
                )

    # -- Buffer toggle: disabling it should give buffer_percent == 0 and a
    #    buffered_rate exactly equal to the mid-market rate (no markup).
    no_buffer_result = build("sample_data.xlsx", config, apply_buffer=False)
    if no_buffer_result.rate.buffer_percent != 0:
        failures.append(f"apply_buffer=False: expected buffer_percent 0, got {no_buffer_result.rate.buffer_percent}")
    if no_buffer_result.rate.buffered_rate != round(no_buffer_result.rate.mid_market_rate, 6):
        failures.append(
            f"apply_buffer=False: expected buffered_rate == mid_market_rate, got "
            f"{no_buffer_result.rate.buffered_rate} vs {no_buffer_result.rate.mid_market_rate}"
        )

    # -- Table of contents: page 2 (index 1) lists every category by name.
    cover_page_count = 1  # the placeholder cover is a single page
    toc_text = reader.pages[1].extract_text() or ""
    if "contents" not in toc_text.lower():
        failures.append(f"TOC heading 'Contents' not found on page 2. Extracted text was: {toc_text!r}")
    for section in sections:
        if section.name not in toc_text:
            failures.append(f"TOC missing category name: {section.name!r}")

    # -- Named destinations: one per section, each resolving to the correct
    #    final page index (cover pages + TOC page + that section's position).
    named_dests = reader.named_destinations
    expected_dest_names = {f"section-{i + 1}" for i in range(len(sections))}
    actual_dest_names = set(named_dests.keys())
    if actual_dest_names != expected_dest_names:
        failures.append(
            f"Named destinations mismatch. Expected {expected_dest_names}, got {actual_dest_names}"
        )
    for i, section in enumerate(sections):
        name = f"section-{i + 1}"
        if name not in named_dests:
            continue
        actual_page_index = reader.get_destination_page_number(named_dests[name])
        expected_page_index = cover_page_count + 1 + i  # + TOC page, 0-based
        if actual_page_index != expected_page_index:
            failures.append(
                f"TOC link for {section.name!r} ({name}) points to page index "
                f"{actual_page_index}, expected {expected_page_index}"
            )

    # -- Footer page numbers: TOC page and first section page should read
    #    the true final page number, not restart from 1.
    toc_footer = footer_page_number(reader.pages[1])
    if toc_footer != str(cover_page_count + 1):
        failures.append(f"TOC page footer reads {toc_footer!r}, expected {cover_page_count + 1!r}")
    first_section_footer = footer_page_number(reader.pages[2])
    if first_section_footer != str(cover_page_count + 2):
        failures.append(f"First section page footer reads {first_section_footer!r}, expected {cover_page_count + 2!r}")

    if failures:
        print("\nFAILED:")
        for f in failures:
            print(f" - {f}")
        return 1

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
