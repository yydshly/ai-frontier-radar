import base64

from app.application.content_video.qr import build_qr_code_data_url


def test_qr_code_data_url_is_real_png():
    data_url = build_qr_code_data_url(
        "https://example.com/radar/share/2026-06-17"
    )
    prefix, encoded = data_url.split(",", 1)
    assert prefix == "data:image/png;base64"
    assert base64.b64decode(encoded).startswith(b"\x89PNG\r\n\x1a\n")
