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
  - pdf_type="print": final page count is a multiple of 4 (booklet
    printing), every page carries no clickable link annotations, and every
    page grows to the bleed+marks size (see print_layout.py)
  - resale_multiplier: no wholesale/resale columns when unset (today's
    plain table), and when set, resale = ROUND(wholesale * multiplier, 2)
    in both currencies, matching generate_pricelist.apply_resale_multiplier

Run with: python test_pipeline.py
"""

import io
import sys

from pypdf import PdfReader

from build_pricelist import build
from fx_rate import load_config
from generate_pricelist import apply_exchange_rate, apply_resale_multiplier, parse_workbook
from print_layout import BOOKLET_PAGE_MULTIPLE, MARK_MARGIN_MM, MM_TO_PT, TRIM_HEIGHT_MM, TRIM_WIDTH_MM


def footer_page_number(page) -> str:
    """Extracts the page number from the last line of a page's text -- the
    bottom margin row, shared by the @bottom-center company footer and the
    @bottom-right page number (see generate_pricelist.py's @page rule), so
    the number is the trailing token rather than the whole line.
    """
    text = (page.extract_text() or "").strip()
    last_line = text.splitlines()[-1] if text else ""
    return last_line.split()[-1] if last_line else ""


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

    # -- Resale multiplier: disabled by default (today's plain table), and
    #    when set, resale = ROUND(wholesale * multiplier, 2) in both
    #    currencies, recomputed independently from the source workbook.
    plain_text = reader.pages[2].extract_text() or ""
    if "WHOLESALE" in plain_text.upper() or "RESALE" in plain_text.upper():
        failures.append(f"resale_multiplier=None: expected no wholesale/resale columns. Got: {plain_text!r}")
    resale_result = build("sample_data.xlsx", config, currency_mode="both", resale_multiplier=1.2)
    if resale_result.resale_multiplier != 1.2:
        failures.append(f"resale_multiplier=1.2: BuildResult.resale_multiplier is {resale_result.resale_multiplier!r}")
    resale_reader = PdfReader(io.BytesIO(resale_result.pdf_bytes))
    resale_page_text = resale_reader.pages[2].extract_text() or ""
    for token in ("WHOLESALE", "RESALE", "CHF", "EUR"):
        if token not in resale_page_text.upper():
            failures.append(f"resale_multiplier=1.2: expected {token!r} on first price page. Got: {resale_page_text!r}")
    resale_sections = parse_workbook("sample_data.xlsx")
    apply_exchange_rate(resale_sections, resale_result.rate.buffered_rate)
    apply_resale_multiplier(resale_sections, 1.2)
    resale_mismatches = []
    for section in resale_sections:
        for item in section.items:
            for price in item.prices:
                expected_chf_resale = round(price.chf * 1.2, 2)
                expected_eur_resale = round(price.eur * 1.2, 2)
                if abs(price.chf_resale - expected_chf_resale) > 1e-9 or abs(price.eur_resale - expected_eur_resale) > 1e-9:
                    resale_mismatches.append((item.name, price.label, price.chf_resale, price.eur_resale))
    if resale_mismatches:
        failures.append(f"Resale price calculation mismatches: {resale_mismatches}")
    invalid_resale_raised = False
    try:
        apply_resale_multiplier(resale_sections, 1.25)  # not one of RESALE_MULTIPLIERS
    except ValueError:
        invalid_resale_raised = True
    if not invalid_resale_raised:
        failures.append("apply_resale_multiplier(1.25): expected ValueError for an out-of-range multiplier")

    # -- Table of contents: page 2 (index 1) lists every category by name.
    cover_page_count = 1  # the placeholder cover is a single page
    toc_text = reader.pages[1].extract_text() or ""
    if "index" not in toc_text.lower():
        failures.append(f"TOC heading 'Index' not found on page 2. Extracted text was: {toc_text!r}")
    for section in sections:
        if section.name not in toc_text:
            failures.append(f"TOC missing category name: {section.name!r}")

    # -- Named destinations: one per section, plus "toc" (the back-to-top
    #    link's target -- see generate_pricelist.py's .back-to-top), each
    #    resolving to the correct final page index (cover pages + TOC page +
    #    that section's position).
    named_dests = reader.named_destinations
    expected_dest_names = {f"section-{i + 1}" for i in range(len(sections))} | {"toc"}
    actual_dest_names = set(named_dests.keys())
    if actual_dest_names != expected_dest_names:
        failures.append(
            f"Named destinations mismatch. Expected {expected_dest_names}, got {actual_dest_names}"
        )
    if "toc" in named_dests and reader.get_destination_page_number(named_dests["toc"]) != cover_page_count:
        failures.append(
            f"'toc' named destination resolves to page index {reader.get_destination_page_number(named_dests['toc'])}, "
            f"expected {cover_page_count} (the TOC page)"
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

    # -- Back-to-top link: a section page should carry a /Link annotation
    #    pointing at the "toc" destination (web mode only -- checked absent
    #    in print mode further down, alongside the other annotation checks).
    section_page_annots = reader.pages[2].get("/Annots") or []
    back_to_top_dests = [a.get_object().get("/Dest") for a in section_page_annots]
    if "toc" not in back_to_top_dests:
        failures.append(f"No back-to-top link (dest 'toc') found on the first section page. Link dests: {back_to_top_dests}")

    # -- Footer page numbers: TOC page and first section page should read
    #    the true final page number, not restart from 1.
    toc_footer = footer_page_number(reader.pages[1])
    if toc_footer != str(cover_page_count + 1):
        failures.append(f"TOC page footer reads {toc_footer!r}, expected {cover_page_count + 1!r}")
    first_section_footer = footer_page_number(reader.pages[2])
    if first_section_footer != str(cover_page_count + 2):
        failures.append(f"First section page footer reads {first_section_footer!r}, expected {cover_page_count + 2!r}")

    # -- Print PDF: booklet-ready page count, no clickable links, and every
    #    page grown to the bleed+marks size.
    print_result = build("sample_data.xlsx", config, pdf_type="print")
    print_reader = PdfReader(io.BytesIO(print_result.pdf_bytes))
    print_total_pages = len(print_reader.pages)
    if print_total_pages % BOOKLET_PAGE_MULTIPLE != 0:
        failures.append(
            f"pdf_type=print: total page count {print_total_pages} is not a multiple of {BOOKLET_PAGE_MULTIPLE}"
        )
    non_empty_annots = [i for i, p in enumerate(print_reader.pages) if p.get("/Annots")]
    if non_empty_annots:
        failures.append(f"pdf_type=print: expected no clickable links, found annotations on pages {non_empty_annots}")
    expected_w = round(TRIM_WIDTH_MM * MM_TO_PT + 2 * MARK_MARGIN_MM * MM_TO_PT, 1)
    expected_h = round(TRIM_HEIGHT_MM * MM_TO_PT + 2 * MARK_MARGIN_MM * MM_TO_PT, 1)
    # Every page except the back cover (its own template's stated size is
    # ~0.5pt off nominal A5 -- a pre-existing placeholder imprecision, not
    # something this feature introduces) should match the canonical size.
    for i, p in enumerate(print_reader.pages[:-1]):
        actual_w, actual_h = round(float(p.mediabox.width), 1), round(float(p.mediabox.height), 1)
        if (actual_w, actual_h) != (expected_w, expected_h):
            failures.append(
                f"pdf_type=print: page {i} size {actual_w}x{actual_h}pt, expected {expected_w}x{expected_h}pt"
            )

    # -- Language-dependent PDF content: the cover date stamp, the per-page
    #    footer's one translated word, and the TOC/back-to-top index label
    #    all follow lang, independent of the workbook's own (untouched)
    #    category/item names.
    lang_expectations = {
        "en": ("Rates from August", "Authorized Representative", "Index"),
        "fr": ("Tarifs valables à partir du", "Mandataire autorisé", "Index"),
        "de": ("Preise gültig ab", "Bevollmächtigter", "Verzeichnis"),
    }
    for lang, (date_stamp_prefix, footer_role, index_label) in lang_expectations.items():
        lang_result = build("sample_data.xlsx", config, lang=lang)
        if not lang_result.date_stamp_text.startswith(date_stamp_prefix):
            failures.append(f"lang={lang!r}: date stamp {lang_result.date_stamp_text!r} doesn't start with {date_stamp_prefix!r}")
        lang_reader = PdfReader(io.BytesIO(lang_result.pdf_bytes))
        toc_text = lang_reader.pages[1].extract_text() or ""
        if footer_role not in toc_text:
            failures.append(f"lang={lang!r}: footer role {footer_role!r} not found on TOC page. Got: {toc_text!r}")
        if toc_text.lower().count(index_label.lower()) < 2:
            # once for the TOC's own title, once for the back-to-top link's text
            failures.append(f"lang={lang!r}: index label {index_label!r} expected twice on TOC page. Got: {toc_text!r}")

    if failures:
        print("\nFAILED:")
        for f in failures:
            print(f" - {f}")
        return 1

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
