from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from leukcut.manifest import load_manifest
from leukcut.render import make_srt, render


def test_srt_has_only_c08_and_c17_cues(short_folder) -> None:
    _, manifest_path, _ = short_folder
    text = make_srt(load_manifest(manifest_path))
    assert text.count(" --> ") == 2
    assert "00:00:22,000 --> 00:00:28,000" in text
    assert "LEUK : « L'eau du dessus" in text
    assert "00:00:55,000 --> 00:00:58,000" in text
    assert "LEUK : « Maa ngi nii ! »" in text


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="system ffmpeg required")
def test_full_render_is_sixty_seconds_plus_or_minus_one_frame(short_folder) -> None:
    root, manifest_path, _ = short_folder
    manifest = load_manifest(manifest_path)
    output = root / "SHORT_01_ANIMATIC_v01.mp4"
    result = render(manifest, output, "animatic")
    assert result.ok, result.message
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,width,height,avg_frame_rate,nb_frames:format=duration",
            "-of",
            "json",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(probe.stdout)
    video = next(stream for stream in data["streams"] if stream["codec_type"] == "video")
    duration = float(data["format"]["duration"])
    assert abs(duration - 60.0) <= 1 / 25
    assert (video["width"], video["height"]) == (1080, 1920)
    assert video["avg_frame_rate"] == "25/1"
    assert int(video["nb_frames"]) == 1500

