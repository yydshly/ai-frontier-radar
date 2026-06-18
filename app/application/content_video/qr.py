"""QR-code helpers for share-video closing scenes."""
from __future__ import annotations

import base64
import io


def build_qr_code_data_url(url: str) -> str:
    """Return a PNG data URL for ``url`` using the project's segno dependency."""
    if not url or not url.strip():
        raise ValueError("A non-empty URL is required to build a QR code.")

    import segno

    buffer = io.BytesIO()
    segno.make(url.strip(), error="m").save(
        buffer,
        kind="png",
        scale=8,
        border=2,
        dark="#07111f",
        light="#ffffff",
    )
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
