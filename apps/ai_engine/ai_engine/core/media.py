"""Media conversion helpers: audio → FLAC, audio duration, image downscale, image data URLs.

Pure transforms over raw bytes, independent of any job. Audio is normalized to mono 16 kHz FLAC for
the gateway; images are re-encoded to a bounded-longest-edge JPEG before captioning (vision token
cost scales with pixels). Failures here surface as ``RuntimeError`` (audio) or a graceful fallback to
the original bytes (image), so a downscale can never break captioning.
"""
import base64
import subprocess
from io import BytesIO

try:  # Pillow is used to downscale photos before captioning; degrade gracefully if absent.
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover - exercised only in a Pillow-less environment
    Image = None
    ImageOps = None

# Longest-edge caps + JPEG quality for the worker-side downscale. A normal caption pass bounds the
# longest edge into the 1024–1536 band (detail:low); a product-label re-read keeps more pixels so
# small lot/brand text is legible (detail:high). GPT-class vision tokens scale with pixels.
CAPTION_MAX_EDGE = 1280
CAPTION_PRODUCT_LABEL_MAX_EDGE = 2048
CAPTION_JPEG_QUALITY = 80


def audio_to_flac_mono_16khz_base64(content: bytes) -> str:
    """Convert arbitrary audio bytes to mono 16 kHz FLAC and base64 encode them."""
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-sample_fmt",
        "s16",
        "-f",
        "flac",
        "pipe:1",
    ]
    try:
        result = subprocess.run(cmd, input=content, capture_output=True, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("Audio conversion to FLAC failed: ffmpeg is not installed or not available on PATH") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Audio conversion to FLAC failed: {stderr or exc}") from exc
    return base64.b64encode(result.stdout).decode("ascii")


def audio_duration_seconds(content: bytes) -> float | None:
    """Best-effort audio duration (seconds) via ffprobe, for per-minute transcription pricing."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nokey=1:noprint_wrappers=1", "pipe:0",
    ]
    try:
        result = subprocess.run(cmd, input=content, capture_output=True, check=True)
        value = result.stdout.decode("utf-8", errors="replace").strip()
        return float(value) if value else None
    except Exception:
        return None


def downscale_image_for_caption(
    content: bytes,
    media_type: str | None,
    *,
    max_edge: int = CAPTION_MAX_EDGE,
    quality: int = CAPTION_JPEG_QUALITY,
) -> tuple[bytes, str]:
    """Re-encode image bytes to a bounded-longest-edge JPEG before sending to the gateway.

    Honors EXIF orientation, flattens to RGB, bounds the longest edge to ``max_edge`` (keeping aspect),
    and JPEG-encodes at ``quality``. Returns ``(bytes, "image/jpeg")``. On any failure (Pillow absent,
    undecodable bytes, already small) it returns the original bytes + media type — captioning must
    never break because a downscale failed.
    """
    if Image is None or ImageOps is None:
        return content, media_type or "image/jpeg"
    try:
        with Image.open(BytesIO(content)) as image:
            image = ImageOps.exif_transpose(image)  # bake in rotation; drop EXIF
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            longest = max(image.size)
            if longest > max_edge:
                scale = max_edge / float(longest)
                image = image.resize(
                    (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                    Image.LANCZOS,
                )
            buffer = BytesIO()
            image.convert("RGB").save(buffer, format="JPEG", quality=quality, optimize=True)
            return buffer.getvalue(), "image/jpeg"
    except Exception:  # noqa: BLE001 - any decode/encode failure falls back to the raw upload
        return content, media_type or "image/jpeg"


def image_to_data_url(content: bytes, media_type: str | None) -> str:
    """Base64-encode image bytes into an OpenAI-compatible data URL."""
    mime = media_type if isinstance(media_type, str) and media_type.startswith("image/") else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"
