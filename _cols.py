"""Measure the real built document's columns, paragraph by paragraph."""
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
        if text.strip():
            lines.append((round(line["bbox"][1], 1), round(line["bbox"][0], 1), text))
lines.sort()

# Column census: how many lines start at each x, and what they are.
census: dict[float, list[str]] = {}
for y, x, t in lines:
    census.setdefault(x, []).append(t[:44])

print("LEFT-EDGE CENSUS for %s page %d" % (path.split("\\")[-1], page_no))
print("-" * 74)
for x in sorted(census):
    print("x=%-6.1f  %2d lines" % (x, len(census[x])))
    for sample in census[x][:3]:
        print("            %s" % sample)
print()
print("REFERENCE (sample columns):")
print("   72 heading number / footer     108 label, list number, body wrap")
print("  126 list wrap                   144 body first line / sub-heading text")
print("  216 inline-label content")
