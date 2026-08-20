"""Extract technical audio metadata with FFprobe and FFmpeg."""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


COMMAND_TIMEOUT_SECONDS = 30
MEAN_VOLUME_PATTERN = re.compile(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", re.IGNORECASE)


class AudioMetadataError(ValueError):
    """Raised when tools are unavailable or a file cannot yield required metadata."""


@dataclass(frozen=True)
class AudioMetadata:
    duration_seconds: float
    sample_rate_hz: int
    bitrate_bps: int
    loudness_db: float


def _tool_path(command: str) -> str:
    path = shutil.which(command)
    if path is None:
        raise AudioMetadataError(
            f"Required audio tool '{command}' was not found. Install FFmpeg and ensure "
            f"'{command}' is available on PATH."
        )
    return path


def _run(command: list[str], tool_name: str) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AudioMetadataError(f"{tool_name} timed out while analyzing the audio.") from exc
    except OSError as exc:
        raise AudioMetadataError(f"Could not run {tool_name}: {exc}") from exc
    if result.returncode != 0:
        diagnostic = (result.stderr or result.stdout).strip().splitlines()
        detail = diagnostic[-1][:300] if diagnostic else "unknown decoding error"
        raise AudioMetadataError(f"{tool_name} could not read the audio: {detail}")
    return result


def _positive_float(value: object, label: str) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise AudioMetadataError(f"FFprobe did not report a valid {label}.") from exc
    if not math.isfinite(number) or number <= 0:
        raise AudioMetadataError(f"FFprobe did not report a valid {label}.")
    return number


def _positive_int(value: object, label: str) -> int:
    number = _positive_float(value, label)
    integer = int(number)
    if integer <= 0:
        raise AudioMetadataError(f"FFprobe did not report a valid {label}.")
    return integer


def extract_audio_metadata(file_path: Path) -> AudioMetadata:
    """Return required audio properties or raise a concise, user-safe error."""
    ffprobe = _tool_path("ffprobe")
    ffmpeg = _tool_path("ffmpeg")
    probe = _run(
        [
            ffprobe,
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_type,sample_rate,bit_rate,duration:format=duration,bit_rate",
            "-of", "json",
            str(file_path),
        ],
        "FFprobe",
    )
    try:
        payload = json.loads(probe.stdout)
        stream = payload["streams"][0]
        container = payload.get("format", {})
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise AudioMetadataError("The uploaded file does not contain a readable audio stream.") from exc

    if stream.get("codec_type") != "audio":
        raise AudioMetadataError("The uploaded file does not contain a readable audio stream.")
    duration = _positive_float(container.get("duration") or stream.get("duration"), "duration")
    sample_rate = _positive_int(stream.get("sample_rate"), "sample rate")
    bitrate = _positive_int(stream.get("bit_rate") or container.get("bit_rate"), "bitrate")

    volume = _run(
        [
            ffmpeg,
            "-nostdin", "-hide_banner", "-i", str(file_path),
            "-af", "volumedetect", "-f", "null", "-",
        ],
        "FFmpeg",
    )
    match = MEAN_VOLUME_PATTERN.search(volume.stderr)
    if match is None:
        raise AudioMetadataError("FFmpeg did not report a mean-volume loudness value.")
    loudness = float(match.group(1))
    if not math.isfinite(loudness):
        raise AudioMetadataError("FFmpeg did not report a valid loudness value.")

    return AudioMetadata(
        duration_seconds=duration,
        sample_rate_hz=sample_rate,
        bitrate_bps=bitrate,
        loudness_db=loudness,
    )
