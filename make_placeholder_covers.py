"""Generates simple placeholder A5 cover PDFs so the stamp/merge pipeline can
be tested end-to-end before the real InDesign/Illustrator covers exist.

Each placeholder is a plain background with a title and a text box marking
where the date stamp will land (matching config.json's date_stamp position).
Run once: `python make_placeholder_covers.py`. Safe to re-run any time --
it overwrites whichever four files config.json's "covers" section currently
points to (one cover + back-cover pair per pdf_type, "web" and "print").

**Real covers already exist for this project** (config.json's default
paths), so running this script as-is will overwrite them with placeholders
again -- only do that deliberately (e.g. point config.json elsewhere
first), not by habit.
"""

import json

from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

import cover_stamp  # noqa: F401 -- side effect: registers Inter with reportlab

A5_WIDTH, A5_HEIGHT = 420.0, 595.0  # points (148mm x 210mm)


def make_placeholder(path: str, title: str, subtitle: str, stamp_config: dict) -> None:
    c = canvas.Canvas(path, pagesize=(A5_WIDTH, A5_HEIGHT))

    # Plain background.
    c.setFillColor(HexColor("#f4f1ec"))
    c.rect(0, 0, A5_WIDTH, A5_HEIGHT, fill=True, stroke=False)

    # Title.
    c.setFillColor(HexColor("#1a1a1a"))
    c.setFont("Inter-Bold", 26)
    c.drawCentredString(A5_WIDTH / 2, A5_HEIGHT / 2 + 20, "IKYUM")

    c.setFont("Inter", 12)
    c.drawCentredString(A5_WIDTH / 2, A5_HEIGHT / 2 - 6, title)
    c.setFont("Inter", 9)
    c.drawCentredString(A5_WIDTH / 2, A5_HEIGHT / 2 - 22, subtitle)

    # Box marking where the date stamp will be drawn, so it's visible even
    # before real content is stamped there.
    box_w, box_h = 130, 16
    x, y = stamp_config["x"], stamp_config["y"]
    c.setStrokeColor(HexColor("#999999"))
    c.setDash(2, 2)
    c.rect(x - 4, y - 4, box_w, box_h, fill=False, stroke=True)
    c.setDash()
    c.setFont("Inter", 6)
    c.setFillColor(HexColor("#999999"))
    c.drawString(x - 4, y + box_h - 4, "date stamp position (placeholder)")

    c.save()


def main() -> None:
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    stamps = config["date_stamp"]

    for pdf_type, covers in config["covers"].items():
        if pdf_type.startswith("_"):
            continue  # config.json's "_comment" key
        make_placeholder(
            covers["cover_template"],
            title=f"Placeholder cover ({pdf_type})",
            subtitle="Replace with the real InDesign/Illustrator cover design",
            stamp_config=stamps["cover"],
        )
        make_placeholder(
            covers["back_cover_template"],
            title=f"Placeholder back cover ({pdf_type})",
            subtitle="Replace with the real InDesign/Illustrator back cover design",
            stamp_config=stamps["back_cover"],
        )
        print(f"Wrote {covers['cover_template']} and {covers['back_cover_template']}")


if __name__ == "__main__":
    main()
