"""
Image optimization and manipulation utility for DemoToSkill.
Ensures screenshots sent to Gemma 4 are downscaled to 1024px max width,
compressed as JPEG quality 70, and efficiently cached and hashed.
"""

import io
import hashlib
import base64
from pathlib import Path
from typing import Union
from PIL import Image

from app.config import (
    IMAGE_RESIZE_MAX_WIDTH,
    IMAGE_JPEG_QUALITY,
    SHOTS_DIR
)


def compute_image_hash(image_bytes: bytes) -> str:
    """Computes a SHA-256 hex digest for image bytes for caching and deduplication."""
    return hashlib.sha256(image_bytes).hexdigest()


def resize_and_compress_image(
    image_input: Union[bytes, str, Path, Image.Image],
    max_width: int = IMAGE_RESIZE_MAX_WIDTH,
    quality: int = IMAGE_JPEG_QUALITY
) -> bytes:
    """
    Downscales an image to max_width preserving aspect ratio and compresses to JPEG.
    Accepts raw bytes, filepath (str/Path), or a PIL Image instance.
    Returns JPEG bytes.
    """
    if isinstance(image_input, (str, Path)):
        img = Image.open(image_input)
    elif isinstance(image_input, bytes):
        img = Image.open(io.BytesIO(image_input))
    elif isinstance(image_input, Image.Image):
        img = image_input
    else:
        raise ValueError(f"Unsupported image input type: {type(image_input)}")

    if img.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    orig_w, orig_h = img.size
    if orig_w > max_width:
        new_w = max_width
        new_h = int((max_width / orig_w) * orig_h)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    output_buf = io.BytesIO()
    img.save(output_buf, format="JPEG", quality=quality, optimize=True)
    return output_buf.getvalue()


def encode_image_to_base64(image_bytes: bytes) -> str:
    """Encodes JPEG bytes to a base64 UTF-8 string."""
    return base64.b64encode(image_bytes).decode("utf-8")


def decode_image_from_base64(base64_str: str) -> bytes:
    """Decodes a base64 string (including data URI prefixes) into raw bytes."""
    if "," in base64_str:
        base64_str = base64_str.split(",", 1)[1]
    return base64.b64decode(base64_str)


def save_screenshot_bytes(
    image_bytes: bytes,
    filename: str,
    output_dir: Union[str, Path] = None
) -> Path:
    """
    Saves optimized screenshot bytes to disk and returns the resolved Path.
    Defaults to SHOTS_DIR from config.
    """
    target_dir = Path(output_dir) if output_dir else SHOTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / filename
    with open(file_path, "wb") as f:
        f.write(image_bytes)
    return file_path

