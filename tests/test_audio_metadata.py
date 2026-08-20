import json
import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

import pytest

from src.audio.metadata import AudioMetadataError, extract_audio_metadata


def write_wav(path: Path, duration: float = 0.25, sample_rate: int = 8000) -> None:
    frame_count = int(duration * sample_rate)
    frames = b"".join(
        struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / sample_rate)))
        for i in range(frame_count)
    )
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(frames)


def test_metadata_parses_probe_and_mean_volume(monkeypatch, tmp_path: Path) -> None:
    audio_path = tmp_path / "sample.wav"
    write_wav(audio_path)
    probe_payload = json.dumps(
        {
            "streams": [{"codec_type": "audio", "sample_rate": "8000", "bit_rate": "128000"}],
            "format": {"duration": "0.250000", "bit_rate": "129408"},
        }
    )
    results = iter(
        [
            subprocess.CompletedProcess([], 0, probe_payload, ""),
            subprocess.CompletedProcess([], 0, "", "[Parsed_volumedetect] mean_volume: -17.3 dB\n"),
        ]
    )
    monkeypatch.setattr("src.audio.metadata.shutil.which", lambda command: command)
    monkeypatch.setattr("src.audio.metadata.subprocess.run", lambda *args, **kwargs: next(results))

    metadata = extract_audio_metadata(audio_path)
    assert metadata.duration_seconds == 0.25
    assert metadata.sample_rate_hz == 8000
    assert metadata.bitrate_bps == 128000
    assert metadata.loudness_db == -17.3


def test_container_bitrate_is_deterministic_fallback(monkeypatch, tmp_path: Path) -> None:
    payload = json.dumps(
        {
            "streams": [{"codec_type": "audio", "sample_rate": "44100"}],
            "format": {"duration": "1.5", "bit_rate": "96000"},
        }
    )
    results = iter(
        [
            subprocess.CompletedProcess([], 0, payload, ""),
            subprocess.CompletedProcess([], 0, "", "mean_volume: -20.0 dB"),
        ]
    )
    monkeypatch.setattr("src.audio.metadata.shutil.which", lambda command: command)
    monkeypatch.setattr("src.audio.metadata.subprocess.run", lambda *args, **kwargs: next(results))
    metadata = extract_audio_metadata(tmp_path / "audio.m4a")
    assert metadata.bitrate_bps == 96000


def test_missing_tools_have_helpful_error(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("src.audio.metadata.shutil.which", lambda _command: None)
    with pytest.raises(AudioMetadataError, match="Install FFmpeg"):
        extract_audio_metadata(tmp_path / "audio.wav")


def test_invalid_audio_fails_cleanly(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("src.audio.metadata.shutil.which", lambda command: command)
    monkeypatch.setattr(
        "src.audio.metadata.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 1, "", "Invalid data found"),
    )
    with pytest.raises(AudioMetadataError, match="could not read the audio"):
        extract_audio_metadata(tmp_path / "fake.wav")


FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="FFmpeg/FFprobe are not installed")
def test_real_wav_metadata_extraction(tmp_path: Path) -> None:
    audio_path = tmp_path / "tone.wav"
    write_wav(audio_path, duration=0.5, sample_rate=16000)
    metadata = extract_audio_metadata(audio_path)
    assert metadata.duration_seconds == pytest.approx(0.5, abs=0.02)
    assert metadata.sample_rate_hz == 16000
    assert metadata.bitrate_bps > 0
    assert metadata.loudness_db < 0


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="FFmpeg/FFprobe are not installed")
def test_real_non_audio_file_is_rejected(tmp_path: Path) -> None:
    fake_audio = tmp_path / "fake.wav"
    fake_audio.write_text("not audio", encoding="utf-8")
    with pytest.raises(AudioMetadataError):
        extract_audio_metadata(fake_audio)
