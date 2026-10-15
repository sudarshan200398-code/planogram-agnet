"""Product pictures: a real file from the store folder's images/ if usable, else a generated SVG tile.

A real file is images/<sku>.jpg, then images/<sku>.png. It is fully decoded and shrunk to a PNG
tile; anything missing, empty, corrupt, too big or outside images/ falls back to the placeholder.
Both kinds are cached, real files by path, modified time and size so a replaced file shows up.
"""
from __future__ import annotations

import functools
import io
import logging
import re
import zlib
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from xml.sax.saxutils import escape

from PIL import Image
from pydantic import BaseModel

if TYPE_CHECKING:
    from .data_loader import Dataset
    from .schemas import Product
    from .settings import Settings

logger = logging.getLogger(__name__)

IMAGE_DIR = "images"
IMAGE_EXTENSIONS = (".jpg", ".png")  # checked in this order: .jpg wins
_WORD = re.compile(r"[^\W\d_]{2,}")


class ProductImage(BaseModel):
    """A picture for one product: PNG bytes from a real file, or SVG markup for a placeholder."""

    sku: str
    source: Literal["file", "placeholder"]
    data: str | bytes
    mime: Literal["image/png", "image/svg+xml"]


def category_colour(category: str, settings: Settings) -> str:
    """A palette colour chosen by a stable hash of the category, the same in every run."""
    palette = settings.image_palette
    return palette[zlib.crc32(category.casefold().encode("utf-8")) % len(palette)]


def initials(name: str, brand: str | None) -> str:
    """Up to two letters from the words after the brand; numbers and single letters are skipped."""
    rest = name
    if brand and name.casefold().startswith(brand.casefold()):
        rest = name[len(brand):]
    for text in (rest, brand or "", name):
        words = _WORD.findall(text)
        if words:
            return "".join(w[0] for w in words[:2]).upper()
    return "?"


def _wrap(name: str, per_line: int, max_lines: int = 2) -> list[str]:
    """Greedy word wrap; the last line ends with an ellipsis if the name does not fit."""
    lines: list[str] = []
    current = ""
    for word in name.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) <= per_line:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    lines = [line[:per_line] for line in lines] or [""]
    if len(lines) > max_lines or len(" ".join(lines)) < len(" ".join(name.split())):
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: per_line - 1].rstrip() + "…"
    return lines


@functools.lru_cache(maxsize=4096)
def _placeholder(name: str, colour: str, letters: str, tile: int) -> str:
    name_size = round(tile * 0.11)
    per_line = max(4, int(tile / (name_size * 0.56)))
    lines = _wrap(name, per_line)
    first_y = tile - name_size * 0.6 - (len(lines) - 1) * name_size * 1.15
    name_text = "".join(
        f'<text class="name" x="{tile / 2:g}" y="{first_y + i * name_size * 1.15:.1f}" '
        f'font-size="{name_size}" text-anchor="middle" fill="#ffffff">{escape(line)}</text>'
        for i, line in enumerate(lines)
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{tile}" height="{tile}" viewBox="0 0 {tile} {tile}" '
        f'font-family="Segoe UI, Helvetica, Arial, sans-serif" role="img">'
        f"<title>{escape(name)}</title>"
        f'<rect width="{tile}" height="{tile}" rx="{round(tile * 0.12)}" fill="{colour}"/>'
        f'<text x="{tile / 2:g}" y="{tile * 0.5:g}" font-size="{round(tile * 0.34)}" font-weight="700" '
        f'text-anchor="middle" fill="#ffffff">{escape(letters)}</text>'
        f"{name_text}</svg>"
    )


def placeholder_svg(name: str, category: str, brand: str | None, settings: Settings) -> str:
    """The generated tile: category colour, initials and the product name."""
    return _placeholder(name, category_colour(category, settings), initials(name, brand), settings.image_tile_px)


@functools.lru_cache(maxsize=1024)
def _thumbnail(path: str, mtime_ns: int, size: int, tile: int) -> bytes | None:
    """Decode a real picture fully and shrink it to a PNG tile; None if it cannot be used."""
    try:
        with Image.open(path) as img:
            img.load()
            pic = img.convert("RGBA" if "A" in img.getbands() else "RGB")
        pic.thumbnail((tile, tile))
        buf = io.BytesIO()
        pic.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Product image %s cannot be used, showing the placeholder: %s", path, exc)
        return None


def _real_file(sku: str, store_dir: str | Path, settings: Settings) -> bytes | None:
    images = (Path(store_dir) / IMAGE_DIR).resolve()
    for ext in IMAGE_EXTENSIONS:
        try:
            path = (images / f"{sku}{ext}").resolve()
            if path.parent != images or not path.is_file():
                continue
            stat = path.stat()
        except (OSError, ValueError):
            continue
        if not 0 < stat.st_size <= settings.image_max_bytes:
            continue
        data = _thumbnail(str(path), stat.st_mtime_ns, stat.st_size, settings.image_tile_px)
        if data is not None:
            return data
    return None


_PRODUCTS: dict[str, object] = {"source": None, "by_sku": {}}


def _product(sku: str, dataset: Dataset) -> Product | None:
    if _PRODUCTS["source"] is not dataset.products:
        _PRODUCTS["by_sku"] = {p.sku: p for p in dataset.products}
        _PRODUCTS["source"] = dataset.products
    return _PRODUCTS["by_sku"].get(sku)  # type: ignore[union-attr]


def product_image(sku: str, dataset: Dataset, store_dir: str | Path, settings: Settings) -> ProductImage:
    """The picture to show for a product. Never raises for a product or a bad file."""
    data = _real_file(sku, store_dir, settings)
    if data is not None:
        return ProductImage(sku=sku, source="file", data=data, mime="image/png")
    p = _product(sku, dataset)
    svg = placeholder_svg(p.name, p.category, p.brand, settings) if p else placeholder_svg(sku, sku, None, settings)
    return ProductImage(sku=sku, source="placeholder", data=svg, mime="image/svg+xml")
