"""The Quality check for photos of a Weekly update (spec #110, no AI): refuse
blurry, too dark, overexposed or too small photos with a reason the Student can
act on, and store the rest as a downscaled JPEG without metadata."""

import io
from dataclasses import dataclass

import pillow_heif
from PIL import Image, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

from pmp_backend.errors import Refused

pillow_heif.register_heif_opener()

FORMATS = {"JPEG", "PNG", "HEIF"}
MIN_SHORT_SIDE = 1080
STORED_LONG_SIDE = 2160
# Phone photos are 12-50 megapixels; more is refused before decoding.
Image.MAX_IMAGE_PIXELS = 60_000_000

# Thresholds tuned on 12 real photos (2026-11-12): sharp ones scored 45-660,
# visibly blurred copies 2-22. Brightness is the mean grey value (0-255).
MIN_SHARPNESS = 20.0
MIN_BRIGHTNESS = 35.0
MAX_BRIGHTNESS = 225.0
MAX_WHITE_SHARE = 0.35

_LAPLACIAN = ImageFilter.Kernel(
    (3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=128
)
_MEASURED_SIDE = 1024
_TILES = 4


class PhotoRefused(Refused):
    """The photo didn't pass; the message says what to do instead."""


@dataclass(frozen=True)
class Photo:
    """A photo that passed: the JPEG to store, its size and its quality score
    (higher is sharper; the AI gets the best ones)."""

    jpeg: bytes
    width: int
    height: int
    score: float


def _open(data: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(data))
        if image.format not in FORMATS:
            raise PhotoRefused("Only JPG, PNG and HEIC photos are accepted.")
        # Turned the right way up, as the phone showed it.
        return ImageOps.exif_transpose(image).convert("RGB")
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as error:
        raise PhotoRefused(
            "This file isn't a photo we can read. Upload a JPG, PNG or HEIC photo."
        ) from error


def sharpness(grey: Image.Image) -> float:
    """How sharp the sharpest part is: the variance of the Laplacian in the 3
    sharpest of 4x4 tiles, so a sharp subject before a blurred background passes."""
    edges = grey.filter(_LAPLACIAN)
    # Pillow leaves the outer pixels unfiltered.
    edges = edges.crop((2, 2, edges.width - 2, edges.height - 2))
    variances = []
    for column in range(_TILES):
        for row in range(_TILES):
            box = (
                column * edges.width // _TILES,
                row * edges.height // _TILES,
                (column + 1) * edges.width // _TILES,
                (row + 1) * edges.height // _TILES,
            )
            variances.append(ImageStat.Stat(edges.crop(box)).var[0])
    best = sorted(variances, reverse=True)[:3]
    return sum(best) / len(best)


def check_photo(data: bytes) -> Photo:
    image = _open(data)
    if min(image.size) < MIN_SHORT_SIDE:
        raise PhotoRefused(
            f"This photo is too small ({image.width}×{image.height}): its short side "
            f"needs at least {MIN_SHORT_SIDE} pixels. Upload the original from your "
            "phone, not a screenshot or a photo sent through a chat app."
        )
    grey = image.convert("L")
    grey.thumbnail((_MEASURED_SIDE, _MEASURED_SIDE))
    histogram = grey.histogram()
    brightness = ImageStat.Stat(grey).mean[0]
    white_share = sum(histogram[250:]) / sum(histogram)
    if brightness < MIN_BRIGHTNESS:
        raise PhotoRefused(
            "This photo is too dark: take it again in better light, or turn on "
            "the lights."
        )
    if brightness > MAX_BRIGHTNESS or white_share > MAX_WHITE_SHARE:
        raise PhotoRefused(
            "This photo is overexposed: don't point the camera at a lamp or a "
            "window, and try again."
        )
    score = sharpness(grey)
    if score < MIN_SHARPNESS:
        raise PhotoRefused(
            "This photo is blurry: hold the camera still, tap the subject to "
            "focus, and try again."
        )
    image.thumbnail((STORED_LONG_SIDE, STORED_LONG_SIDE))
    stored = io.BytesIO()
    # Saved without EXIF, so no location or camera data is kept.
    image.save(stored, "JPEG", quality=85, optimize=True)
    return Photo(
        jpeg=stored.getvalue(), width=image.width, height=image.height, score=score
    )
