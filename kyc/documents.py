"""Render a synthetic identity document as an image.

Every card carries a SYNTHETIC SAMPLE watermark. The layout is generic and
does not imitate any real issuer's document.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 860, 540
NAVY, CYAN, INK, MUTED = (17, 86, 127), (41, 181, 232), (30, 41, 59), (100, 116, 139)


FONT_DIR = Path(__file__).resolve().parents[1] / "static"


def _font(size: int, bold: bool = False):
    """The app's bundled Inter font, so cards render the same locally, in Snowflake and in the browser."""
    try:
        return ImageFont.truetype(str(FONT_DIR / ("Inter-SemiBold.ttf" if bold else "Inter-Regular.ttf")), size)
    except OSError:
        return ImageFont.load_default(size=size)


def render(doc: dict, country_label: str) -> Image.Image:
    img = Image.new("RGB", (W, H), (244, 249, 252))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, W - 8, H - 8], radius=28, outline=(208, 232, 242), width=4, fill=(250, 253, 255))
    d.rounded_rectangle([8, 8, W - 8, 92], radius=28, fill=NAVY)
    d.rectangle([8, 60, W - 8, 92], fill=NAVY)
    title = doc["DOC_TYPE"].replace("_", " ")
    d.text((40, 26), f"{title}  ·  {country_label}", font=_font(32, bold=True), fill=(255, 255, 255))
    # Portrait placeholder
    d.rounded_rectangle([40, 125, 250, 395], radius=18, fill=(220, 236, 245))
    d.ellipse([100, 160, 190, 250], fill=(160, 200, 222))
    d.rounded_rectangle([75, 262, 215, 380], radius=50, fill=(160, 200, 222))
    fields = [
        ("SURNAME", doc["DOC_LAST_NAME"]),
        ("GIVEN NAMES", doc["DOC_FIRST_NAME"]),
        ("DATE OF BIRTH", str(doc["DOC_DATE_OF_BIRTH"])),
        ("DOCUMENT NO.", doc["DOC_NUMBER"]),
        ("DATE OF EXPIRY", str(doc["EXPIRY_DATE"])),
    ]
    y = 120
    for label, value in fields:
        d.text((290, y), label, font=_font(17), fill=MUTED)
        d.text((290, y + 20), str(value).upper(), font=_font(30, bold=True), fill=INK)
        y += 62
    # Machine-readable zone style footer (not a real MRZ format)
    d.rectangle([8, 430, W - 8, H - 8], fill=(232, 244, 248))
    zone = f"SYN<{doc['DOC_LAST_NAME'].upper()}<<{doc['DOC_FIRST_NAME'].upper()}<<<<{doc['DOC_NUMBER']}<<SAMPLE"
    d.text((40, 460), zone[:52], font=_font(24), fill=NAVY)
    # Watermark band, clear of the fields
    d.rounded_rectangle([600, 104, W - 24, 140], radius=10, fill=(253, 236, 231))
    d.text((614, 111), "SYNTHETIC SAMPLE", font=_font(20, bold=True), fill=(222, 53, 11))
    d.text((40, 404), "Not a real document", font=_font(17, bold=True), fill=(222, 53, 11))
    return img


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
