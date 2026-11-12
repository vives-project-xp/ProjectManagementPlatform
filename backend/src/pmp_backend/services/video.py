"""Videos of a Weekly update (spec #110): checked at upload on type, length and
size only, then re-encoded with ffmpeg into an Instagram-friendly copy and a
small copy for the AI. ffmpeg comes with the imageio-ffmpeg package."""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg

from pmp_backend.errors import Refused

MAX_SECONDS = 90
# The containers phones record in; ffmpeg reports both MP4 and MOV as "mov,mp4,…".
_CONTAINER = re.compile(r"Input #0, [^,]*mov,mp4")
_DURATION = re.compile(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)")
_SIZE = re.compile(r"Stream #\S+.*Video: .*?(\d{2,5})x(\d{2,5})")
# A 90-second video takes a minute or two on the VM's 2 vCPUs.
ENCODE_TIMEOUT = 15 * 60

# The posted copy: H.264/AAC, the long side at most 1920 (1080p), playable
# while it downloads. The AI copy: 640 px, low quality, no sound.
_POSTED = [
    "-vf", "scale='if(gt(iw,ih),min(1920,iw),-2)':'if(gt(iw,ih),-2,min(1920,ih))'",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
]  # fmt: skip
_FOR_AI = [
    "-vf", "scale='if(gt(iw,ih),min(640,iw),-2)':'if(gt(iw,ih),-2,min(640,ih))'",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "32", "-pix_fmt", "yuv420p",
    "-an", "-movflags", "+faststart",
]  # fmt: skip


class VideoRefused(Refused):
    """The video didn't pass; the message says what to do instead."""


@dataclass(frozen=True)
class Probe:
    seconds: float
    width: int
    height: int


def _ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def probe(path: Path) -> Probe:
    """Its length and frame size, read from what `ffmpeg -i` reports."""
    result = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=60,
    )
    report = result.stderr
    duration = _DURATION.search(report)
    size = _SIZE.search(report)
    if not _CONTAINER.search(report) or duration is None or size is None:
        raise VideoRefused(
            "This file isn't a video we can read. Upload an MP4 or MOV video."
        )
    hours, minutes, seconds = duration.groups()
    return Probe(
        seconds=int(hours) * 3600 + int(minutes) * 60 + float(seconds),
        width=int(size.group(1)),
        height=int(size.group(2)),
    )


def check(path: Path) -> Probe:
    found = probe(path)
    if found.seconds > MAX_SECONDS + 0.5:
        raise VideoRefused(
            f"This video is {round(found.seconds)} seconds long; at most "
            f"{MAX_SECONDS} seconds are accepted. Trim it and try again."
        )
    return found


def _encode(source: Path, target: Path, options: list[str]) -> None:
    partial = target.with_name(f"{target.name}.partial.mp4")
    try:
        subprocess.run(
            [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(source)]
            + options
            + [str(partial)],
            check=True,
            capture_output=True,
            timeout=ENCODE_TIMEOUT,
        )
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)


def encode(source: Path, posted: Path, for_ai: Path) -> Probe:
    """Write both copies; the frame size of the posted one. Raises
    subprocess errors when ffmpeg fails."""
    _encode(source, posted, _POSTED)
    _encode(source, for_ai, _FOR_AI)
    return probe(posted)
