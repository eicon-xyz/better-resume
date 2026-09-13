"""PDF building helpers for resume-parser tests (generated, nothing binary in the repo)."""

from __future__ import annotations

import contextlib
import io
from collections.abc import Sequence

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

Line = tuple[str, int, bool]  # text, font size, bold

_CJK_FONT = "STSong-Light"


def build_pdf(lines: Sequence[Line], *, page_top: int = 800) -> bytes:
    """Render lines top-down; bold=True uses a bold font (CJK uses a size bump instead)."""
    with contextlib.suppress(KeyError):  # already registered in this process
        pdfmetrics.registerFont(UnicodeCIDFont(_CJK_FONT))

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    y = page_top
    for text, size, bold in lines:
        is_cjk = any("\u4e00" <= char <= "\u9fff" for char in text)
        if is_cjk:
            pdf.setFont(_CJK_FONT, size + (1 if bold else 0))
        else:
            pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        pdf.drawString(50, y, text)
        y -= size + 8
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
