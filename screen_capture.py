"""
E.V. — Screen Capture
Takes screenshots and describes them via Claude Vision.
"""

import base64
import io
from PIL import ImageGrab


def capture_screen() -> bytes:
    """Capture the entire screen, return PNG bytes."""
    img = ImageGrab.grab()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def describe_screen(anthropic_client, lang: str = "en") -> str:
    """Capture screen and describe it using Claude Vision."""
    png_bytes = capture_screen()
    b64 = base64.b64encode(png_bytes).decode("utf-8")
    prompt = (
        "Bu ekranda görünenleri Türkçe olarak kısaca anlat. En fazla 2-3 cümle. "
        "Açık olan en önemli programları ve içerikleri belirt."
        if lang == "tr" else
        "Briefly describe what's on this screen in English. At most 2-3 sentences. "
        "Mention the most important open programs and content."
    )

    response = await anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": b64,
                    },
                },
                {
                    "type": "text",
                    "text": prompt,
                },
            ],
        }],
    )
    return response.content[0].text
