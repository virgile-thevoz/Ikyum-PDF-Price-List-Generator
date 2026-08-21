"""Shared print-production constants for the "print PDF" export mode.

Both `generate_pricelist.py` (WeasyPrint/CSS, for the price-table pages)
and `print_marks.py` (pypdf/reportlab, for the cover/back-cover pages and
blank filler pages) size their bleed and crop marks off these same
numbers, so every page in a print PDF -- cover, price-table pages, blank
fillers, back cover -- ends up exactly the same final (trim + bleed +
marks) size, which real imposition/booklet-printing software expects.

## Geometry

Each page's trim box (the final cut size, A5: 148 x 210mm) sits centered
inside a larger sheet. Moving outward from the trim edge:

  1. the **bleed** area (BLEED_MM): reserved so any edge-to-edge artwork
     survives minor trimming misalignment. The current cover/back-cover
     templates are plain trim-size PDFs with no bleed artwork of their own
     (see README -- the real covers are still being designed in
     InDesign/Illustrator), so for now this area is left blank around the
     existing design rather than fabricating extended artwork. Once real
     print-ready covers exist, they can be dropped in with their own bleed
     already built in and `print_marks.add_bleed_and_marks` will still
     work correctly (it reads each page's actual size rather than
     assuming a fixed one).
  2. the **crop marks** (MARK_LENGTH_MM long), starting right where the
     bleed area ends (no extra gap) and running further outward -- the
     standard "marks start at the bleed edge" convention.

So the total margin added to each side of the trim box is
BLEED_MM + MARK_LENGTH_MM = MARK_MARGIN_MM.
"""

MM_TO_PT = 72 / 25.4  # PDF points per mm (72 pt/inch, 25.4mm/inch)

# A5 trim size, matching generate_pricelist.py's page design and the
# cover/back-cover templates.
TRIM_WIDTH_MM = 148.0
TRIM_HEIGHT_MM = 210.0

BLEED_MM = 3.0
MARK_LENGTH_MM = 5.0
MARK_MARGIN_MM = BLEED_MM + MARK_LENGTH_MM  # 8.0mm from trim edge to final page edge

MARK_LINE_WIDTH_PT = 0.25  # hairline, standard for crop marks

# Saddle-stitch booklet printing needs the *total* final page count (cover
# through back cover) to be a multiple of this, since each physical sheet
# folds down to this many pages.
BOOKLET_PAGE_MULTIPLE = 4
