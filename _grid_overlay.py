"""Overlay a sample page and a draft page on one numbered grid.

Everything runs from the bundled interpreter: pages are rasterised with the
LibreOffice kit, then composited with Pillow.

Outputs:
  <prefix>_grid.png     the sample alone, on a numbered 0.5" grid
  <prefix>_overlay.png  sample (blue) + draft (red) superimposed on that grid

Any displacement shows as a blue or red ghost beside the other colour.

    python _grid_overlay.py <sample.pdf> <sample-page> <draft.pdf> <draft-page> <prefix>
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

NODE = (
    r"C:\Users\earla\AppData\Local\Programs\DeepSeek Harness\resources\runtime"
    r"\primary-runtime\dependencies\node\bin\node.exe"
)
KIT = (
    r"C:\Users\earla\AppData\Local\Programs\DeepSeek Harness\resources"
    r"\app.asar.unpacked\dsh\node_modules\@deepseek-ai\libreoffice-kit\lib\cli.js"
)

DPI = 110
PT = DPI / 72.0                 # pixels per PDF point at this DPI
HALF_IN = 36.0                  # half inch in points
GRID = (205, 205, 205)
GRID_STRONG = (140, 140, 140)
COLUMN = (60, 140, 230)
SAMPLE_INK = (20, 60, 190)
DRAFT_INK = (200, 30, 30)
COLUMNS = (72.0, 108.0, 144.0, 216.0)


def render(pdf: Path, page: int, out_dir: Path) -> Image.Image:
    """Rasterise one page of *pdf* to a PIL image via the LibreOffice kit."""
    result = subprocess.run(
        [NODE, KIT, "render", "--input", str(pdf),
         "--output-dir", str(out_dir), "--pages", str(page), "--dpi", str(DPI)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    manifest = json.loads(result.stdout.strip().splitlines()[-1])
    png = manifest["images"][0]["path"]
    return Image.open(png).convert("L")


def tinted(gray: Image.Image, tint: tuple[int, int, int]) -> tuple[Image.Image, Image.Image]:
    """Return (recoloured ink on white, ink mask)."""
    mask = gray.point(lambda v: 255 - v)          # white paper -> 0, ink -> high
    colour = Image.new("RGB", gray.size, tint)
    white = Image.new("RGB", gray.size, (255, 255, 255))
    return Image.composite(colour, white, mask), mask


def multiply(a: Image.Image, b: Image.Image) -> Image.Image:
    """Screen-style multiply of two ink-on-white layers."""
    from PIL import ImageChops

    return ImageChops.multiply(a, b)


def draw_grid(img: Image.Image) -> None:
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 11)
    except OSError:
        font = ImageFont.load_default()

    width, height = img.size
    half = 0
    y = 0.0
    while y * PT <= height:
        py = y * PT
        strong = (half % 2 == 0)
        draw.line([(0, py), (width, py)],
                  fill=GRID_STRONG if strong else GRID,
                  width=1 if strong else 1)
        if strong and half:
            draw.text((3, py - 13), str(half // 2), fill=GRID_STRONG, font=font)
        y += HALF_IN
        half += 1

    half = 0
    x = 0.0
    while x * PT <= width:
        px = x * PT
        strong = (half % 2 == 0)
        draw.line([(px, 0), (px, height)],
                  fill=GRID_STRONG if strong else GRID, width=1)
        if strong and half:
            draw.text((px + 2, 2), str(half // 2), fill=GRID_STRONG, font=font)
        x += HALF_IN
        half += 1

    for column in COLUMNS:
        px = column * PT
        if px < width - 2:
            draw.line([(px, 0), (px, height)], fill=COLUMN, width=1)


def main() -> int:
    sample_pdf, sample_pg, draft_pdf, draft_pg, prefix = (
        sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4]), sys.argv[5]
    )
    sample_pdf, draft_pdf = Path(sample_pdf), Path(draft_pdf)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        sample_gray = render(sample_pdf, sample_pg, tmp_path / "s")
        draft_gray = render(draft_pdf, draft_pg, tmp_path / "d")

    # sample alone on the grid
    grid_img = Image.new("RGB", sample_gray.size, (255, 255, 255))
    grid_img.paste(tinted(sample_gray, (0, 0, 0))[0])
    draw_grid(grid_img)
    grid_img.save(prefix + "_grid.png")
    print("wrote", prefix + "_grid.png")

    # sample + draft superimposed
    sample_layer, _ = tinted(sample_gray, SAMPLE_INK)
    draft_layer, _ = tinted(draft_gray, DRAFT_INK)
    combined = multiply(sample_layer, draft_layer)
    draw_grid(combined)
    combined.save(prefix + "_overlay.png")
    print("wrote", prefix + "_overlay.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
