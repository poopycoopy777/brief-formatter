"""Group a rendered page's lines into paragraphs and report each column."""
import io
import sys

import pymupdf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

path, page_no = sys.argv[1], int(sys.argv[2])
doc = pymupdf.open(path)
page = doc[page_no - 1]

lines = []
for b in page.get_text("dict")["blocks"]:
    if b.get("type") != 0:
        continue
    for line in b["lines"]:
        text = "".join(s["text"] for s in line["spans"])
        if not text.strip():
            continue
        lines.append((round(line["bbox"][1], 1), round(line["bbox"][0], 1), text))

lines.sort()
if not lines:
    sys.exit(0)

# Modal pitch between consecutive line tops, then break where the gap is bigger.
gaps = sorted(
    round(b[0] - a[0], 1) for a, b in zip(lines, lines[1:]) if 0 < b[0] - a[0] < 60
)
pitch = gaps[len(gaps) // 2] if gaps else 36.0
paragraphs = [[lines[0]]]
for prev, cur in zip(lines, lines[1:]):
    if cur[0] - prev[0] > pitch * 1.35:
        paragraphs.append([cur])
    else:
        paragraphs[-1].append(cur)

print("modal pitch = %.1f" % pitch)
print("%-7s %-7s %s" % ("y", "x0", "text"))
print("-" * 76)
for para in paragraphs:
    y, x, t = para[0]
    print("%-7.1f %-7.1f %s" % (y, x, t[:50]))
    for y2, x2, t2 in para[1:]:
        print("%-7s %-7.1f %s" % ("", x2, "    " + t2[:46]))
    print()
