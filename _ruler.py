"""Overlay a ruler on a PDF page so positions can be compared visually.

Top margin carries inch ticks (long + labelled) and half/quarter ticks, plus
vertical locator lines down the page at each inch, so a reader can see at a
glance whether element A sits in the same place in two documents.

    python _ruler.py <input.pdf> <page-number-1-based> <output.png>
"""

from __future__ import annotations

import sys

import pymupdf

DPI = 110
# Left-frame ticks sit in the margin above the text; the body starts at 108pt
# (1.5in) on our pages and 108pt on the sample's body pages.
TICK_TOP = 4.0
TICK_LONG = 34.0
TICK_HALF = 24.0
TICK_QUARTER = 16.0
LABEL_Y = 44.0
GUIDE_TOP = 70.0
GREY = (0.72, 0.72, 0.72)
BLACK = (0.45, 0.45, 0.45)


def ruler(page, guide_to: float) -> None:
    height = page.rect.height
    # horizontal ticks every quarter inch along the top margin
    for quarter in range(0, 9):
        x = 72 + quarter * 18          # 18pt = 0.25in, starting at the margin
        if x > page.rect.width - 40:
            break
        if quarter % 4 == 0:
            length, colour = TICK_LONG, BLACK
        elif quarter % 2 == 0:
            length, colour = TICK_HALF, GREY
        else:
            length, colour = TICK_QUARTER, GREY
        page.draw_line(
            pymupdf.Point(x, TICK_TOP),
            pymupdf.Point(x, TICK_TOP + length),
            color=colour, width=0.7,
        )
        if quarter % 4 == 0:
            page.insert_text(
                pymupdf.Point(x + 2, LABEL_Y),
                "%d\"" % (quarter // 4),
                fontsize=7, fontname="helv", color=BLACK,
            )

    # vertical guides at each inch, faint, to read the y position of an element
    for inch in range(1, 11):
        y = 72 + (inch - 1) * 72
        if y > height - 60:
            break
        page.draw_line(
            pymupdf.Point(60, y), pymupdf.Point(72, y),
            color=GREY, width=0.7,
        )
        page.insert_text(
            pymupdf.Point(40, y + 3), "%d" % inch,
            fontsize=6.5, fontname="helv", color=GREY,
        )

    # a light vertical rule at the left margin and at each content column, so
    # x alignment is visible down the whole page
    for x, colour in ((72, GREY), (108, (0.85, 0.85, 0.85))):
        page.draw_line(
            pymupdf.Point(x, TICK_TOP), pymupdf.Point(x, guide_to),
            color=colour, width=0.6,
        )


def main() -> int:
    src, page_no, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    doc = pymupdf.open(src)
    page = doc[page_no - 1]
    guide_to = page.rect.height - 60
    ruler(page, guide_to)
    page.get_pixmap(dpi=DPI).save(out)
    print("wrote", out, "from page", page_no, "of", src)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
