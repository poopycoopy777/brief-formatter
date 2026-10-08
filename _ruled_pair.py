"""Stack a sample page and one of ours with identical rulers, side by side.

    python _ruled_pair.py <sample.pdf> <sample-page> <ours.pdf> <ours-page> <out.png>
"""
import io
import sys

import pymupdf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DPI = 100
GREY = (0.70, 0.70, 0.70)
RED = (0.85, 0.20, 0.20)
BLUE = (0.15, 0.30, 0.85)
GREEN = (0.15, 0.55, 0.15)
PURPLE = (0.55, 0.25, 0.70)

# Sample content columns, drawn on both pages so alignment is visible.
GUIDES = ((72, RED), (108, BLUE), (144, GREEN), (216, PURPLE))


def mark(page, label, colour) -> None:
    width, height = page.rect.width, page.rect.height
    page.draw_line(pymupdf.Point(0, 1), pymupdf.Point(width, 1),
                   color=colour, width=2)
    for quarter in range(0, 33):
        x = quarter * 18.0
        if x > width - 20:
            break
        if quarter % 4 == 0:
            length, col, tick_label = 30, colour, "%d" % (quarter // 4)
        elif quarter % 2 == 0:
            length, col, tick_label = 20, GREY, None
        else:
            length, col, tick_label = 12, GREY, None
        page.draw_line(pymupdf.Point(x, 2), pymupdf.Point(x, 2 + length),
                       color=col, width=0.7)
        if tick_label:
            page.insert_text(pymupdf.Point(x + 2, 44), tick_label,
                             fontsize=7, fontname="helv", color=colour)
    page.insert_text(pymupdf.Point(4, 58), label, fontsize=9,
                     fontname="hebo", color=colour)
    for inch in range(1, 12):
        y = inch * 72.0
        if y > height - 40:
            break
        page.draw_line(pymupdf.Point(0, y), pymupdf.Point(14, y),
                       color=GREY, width=0.6)
        page.insert_text(pymupdf.Point(16, y + 3), str(inch),
                         fontsize=6, fontname="helv", color=GREY)
    for x, col in GUIDES:
        if x < width - 10:
            page.draw_line(pymupdf.Point(x, 62), pymupdf.Point(x, height - 40),
                           color=col, width=0.55)


def main() -> int:
    sample_pdf, sample_pg, ours_pdf, ours_pg, out = (
        sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4]), sys.argv[5]
    )
    s = pymupdf.open(sample_pdf)
    o = pymupdf.open(ours_pdf)
    sp, op = s[sample_pg - 1], o[ours_pg - 1]
    mark(sp, "SAMPLE p%d" % sample_pg, RED)
    mark(op, "OURS p%d" % ours_pg, BLUE)

    pages = [sp.get_pixmap(dpi=DPI), op.get_pixmap(dpi=DPI)]
    gap = 20
    total_w = sum(p.width for p in pages) + gap
    total_h = max(p.height for p in pages)
    canvas = pymupdf.open()
    sheet = canvas.new_page(width=total_w, height=total_h)
    x = 0
    for pix in pages:
        sheet.insert_image(
            pymupdf.Rect(x, 0, x + pix.width, pix.height), pixmap=pix
        )
        x += pix.width + gap
    sheet.get_pixmap(dpi=DPI).save(out)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
