from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml


TIMECODE_RE = re.compile(r"^(\d+):([0-5]\d)\.(\d+)$")
SHOT_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
APPROVED = {"approved", "locked"}
STATUSES = {"pending", "generated", "approved", "locked"}
STAR_STATES = {"off", "ignite", "sparkle"}
TRANSITIONS = {"cut", "crossfade"}
IMAGE_SUFFIXES = {".jpeg", ".jpg", ".png"}


@dataclass(frozen=True)
class Finding:
    level: str
    subject: str
    message: str

    def format(self) -> str:
        return f"{self.level} {self.subject} {self.message}"


@dataclass
class Shot:
    raw: dict[str, Any]
    id: str
    t_in: Decimal
    t_out: Decimal
    status: str
    file_value: str | None
    version: int
    dialogue: str | None
    action: str
    transition: str
    resolved_file: Path | None = None

    @property
    def duration(self) -> Decimal:
        return self.t_out - self.t_in


@dataclass
class Manifest:
    path: Path
    root: Path
    raw: dict[str, Any]
    short_id: str
    width: int
    height: int
    fps: int
    duration: Decimal
    shots: list[Shot]
    guide_track: Path | None
    kenburns_enabled: bool
    max_zoom: Decimal
    findings: list[Finding] = field(default_factory=list)

    @property
    def total_frames(self) -> int:
        return int(self.duration * self.fps)


def _error(findings: list[Finding], subject: str, message: str) -> None:
    findings.append(Finding("ERROR", subject, message))


def _warning(findings: list[Finding], subject: str, message: str) -> None:
    findings.append(Finding("WARN", subject, message))


def _decimal(value: Any, subject: str, name: str, findings: list[Finding]) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        _error(findings, subject, f"{name} must be numeric")
        return None
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        _error(findings, subject, f"{name} must be numeric")
        return None
    if not result.is_finite():
        _error(findings, subject, f"{name} must be finite")
        return None
    return result


def parse_timecode(value: Any, subject: str, name: str, findings: list[Finding]) -> Decimal | None:
    if not isinstance(value, str):
        _error(findings, subject, f"{name} must use MM:SS.d timecode syntax")
        return None
    match = TIMECODE_RE.fullmatch(value)
    if not match:
        _error(findings, subject, f"{name} '{value}' must use MM:SS.d timecode syntax")
        return None
    return Decimal(match.group(1)) * 60 + Decimal(match.group(2)) + Decimal(f"0.{match.group(3)}")


def discover_manifest(value: str | Path | None) -> Path:
    if value is not None:
        return Path(value).expanduser().resolve()
    matches = sorted(Path.cwd().glob("*.manifest.yaml"))
    if len(matches) != 1:
        raise ValueError(f"expected one *.manifest.yaml in {Path.cwd()}, found {len(matches)}")
    return matches[0].resolve()


def _required_mapping(parent: dict[str, Any], key: str, subject: str, findings: list[Finding]) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        _error(findings, subject, f"{key} must be a mapping")
        return {}
    return value


def _safe_relative_path(root: Path, value: Any, subject: str, name: str, findings: list[Finding]) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        _error(findings, subject, f"{name} must be a non-empty relative path or null")
        return None
    candidate = Path(value)
    if candidate.is_absolute():
        _error(findings, subject, f"{name} must be relative to the short folder")
        return None
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        _error(findings, subject, f"{name} escapes the short folder")
        return None
    return resolved


def resolve_shot_file(root: Path, shot: Shot) -> Path | None:
    if shot.file_value is not None:
        return (root / shot.file_value).resolve()
    board = root / "01_STORYBOARD"
    if not board.is_dir():
        return None
    pattern = re.compile(rf"^{re.escape(shot.id)}_v(\d+)(\.jpeg|\.jpg|\.png)$", re.IGNORECASE)
    candidates: list[tuple[int, str, Path]] = []
    for path in board.iterdir():
        if not path.is_file():
            continue
        match = pattern.fullmatch(path.name)
        if match:
            candidates.append((int(match.group(1)), path.name.casefold(), path.resolve()))
    return max(candidates)[2] if candidates else None


def load_manifest(path_value: str | Path | None) -> Manifest | None:
    findings: list[Finding] = []
    try:
        path = discover_manifest(path_value)
    except ValueError as exc:
        placeholder = Path(path_value).expanduser().resolve() if path_value else Path.cwd()
        return _invalid_manifest(placeholder, str(exc))
    if not path.is_file():
        return _invalid_manifest(path, "manifest does not exist or is not a regular file")
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        return _invalid_manifest(path, f"cannot read YAML: {exc}")
    if not isinstance(loaded, dict):
        return _invalid_manifest(path, "YAML root must be a mapping")

    root = path.parent.resolve()
    if loaded.get("schema") != "waraba/shotmanifest/v1":
        _error(findings, "MANIFEST", "schema must be waraba/shotmanifest/v1")
    short = _required_mapping(loaded, "short", "MANIFEST", findings)
    short_id = short.get("id")
    if not isinstance(short_id, str) or not SHOT_ID_RE.fullmatch(short_id):
        _error(findings, "MANIFEST", "short.id must contain only letters, digits, '_' or '-'")
        short_id = "UNKNOWN"
    fmt = _required_mapping(short, "format", "MANIFEST", findings)
    if fmt.get("aspect") != "9:16":
        _error(findings, "MANIFEST", "short.format.aspect must be 9:16")
    resolution = fmt.get("resolution")
    if (
        not isinstance(resolution, list)
        or len(resolution) != 2
        or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in resolution)
    ):
        _error(findings, "MANIFEST", "short.format.resolution must be [width, height] positive integers")
        width, height = 1080, 1920
    else:
        width, height = resolution
        if resolution != [1080, 1920]:
            _error(findings, "MANIFEST", "short.format.resolution must be [1080, 1920] in v1")
    fps_value = fmt.get("fps")
    if isinstance(fps_value, bool) or not isinstance(fps_value, int) or fps_value <= 0:
        _error(findings, "MANIFEST", "short.format.fps must be a positive integer")
        fps = 25
    else:
        fps = fps_value
    duration = _decimal(fmt.get("duration_s"), "MANIFEST", "short.format.duration_s", findings)
    if duration is None or duration <= 0:
        if duration is not None:
            _error(findings, "MANIFEST", "short.format.duration_s must be positive")
        duration = Decimal(0)
    if duration * fps != (duration * fps).to_integral_value():
        _error(findings, "MANIFEST", "duration_s must align to an exact video frame")

    defaults = _required_mapping(loaded, "defaults", "MANIFEST", findings)
    default_transition = defaults.get("transition", "cut")
    if default_transition not in TRANSITIONS:
        _error(findings, "MANIFEST", "defaults.transition must be cut or crossfade")
        default_transition = "cut"
    kenburns = _required_mapping(defaults, "kenburns", "MANIFEST", findings)
    enabled = kenburns.get("enabled")
    if not isinstance(enabled, bool):
        _error(findings, "MANIFEST", "defaults.kenburns.enabled must be boolean")
        enabled = False
    max_zoom = _decimal(kenburns.get("max_zoom"), "MANIFEST", "defaults.kenburns.max_zoom", findings)
    if max_zoom is None or max_zoom < 1:
        if max_zoom is not None:
            _error(findings, "MANIFEST", "defaults.kenburns.max_zoom must be >= 1.0")
        max_zoom = Decimal(1)

    shots_value = loaded.get("shots")
    if not isinstance(shots_value, list) or not shots_value:
        _error(findings, "MANIFEST", "shots must be a non-empty list")
        shots_value = []
    shots: list[Shot] = []
    for index, raw_shot in enumerate(shots_value):
        fallback = f"SHOT_{index + 1}"
        if not isinstance(raw_shot, dict):
            _error(findings, fallback, "shot must be a mapping")
            continue
        shot_id = raw_shot.get("id")
        if not isinstance(shot_id, str) or not SHOT_ID_RE.fullmatch(shot_id):
            _error(findings, fallback, "id must contain only letters, digits, '_' or '-'")
            shot_id = fallback
        t_in = parse_timecode(raw_shot.get("t_in"), shot_id, "t_in", findings)
        t_out = parse_timecode(raw_shot.get("t_out"), shot_id, "t_out", findings)
        status = raw_shot.get("status")
        if status not in STATUSES:
            _error(findings, shot_id, "status must be pending, generated, approved or locked")
            status = "pending"
        star_state = raw_shot.get("star_state")
        if star_state not in STAR_STATES:
            _error(findings, shot_id, "star_state must be off, ignite or sparkle")
        file_value = raw_shot.get("file")
        _safe_relative_path(root, file_value, shot_id, "file", findings)
        if file_value is not None and not isinstance(file_value, str):
            file_value = None
        version = raw_shot.get("version")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            _error(findings, shot_id, "version must be a positive integer")
            version = 1
        dialogue = raw_shot.get("dialogue")
        if dialogue is not None and not isinstance(dialogue, str):
            _error(findings, shot_id, "dialogue must be a string or null")
            dialogue = None
        action = raw_shot.get("action_fr")
        if not isinstance(action, str):
            _error(findings, shot_id, "action_fr must be a string")
            action = ""
        transition = raw_shot.get("transition", default_transition)
        if transition not in TRANSITIONS:
            _error(findings, shot_id, "transition must be cut or crossfade")
            transition = "cut"
        if t_in is None:
            t_in = Decimal(0)
        if t_out is None:
            t_out = t_in
        if t_out <= t_in:
            _error(findings, shot_id, "t_out must be after t_in")
        if (t_out - t_in) * fps != ((t_out - t_in) * fps).to_integral_value():
            _error(findings, shot_id, "duration must align to an exact video frame")
        shots.append(
            Shot(raw_shot, shot_id, t_in, t_out, status, file_value, version, dialogue, action, transition)
        )

    counts = Counter(shot.id for shot in shots)
    for shot_id in sorted(shot_id for shot_id, count in counts.items() if count > 1):
        _error(findings, shot_id, "duplicate shot id")
    expected = Decimal(0)
    for shot in shots:
        if shot.t_in != expected:
            _error(findings, shot.id, f"timeline does not tile: expected t_in {expected}, got {shot.t_in}")
        expected = shot.t_out
    if shots and expected != duration:
        _error(findings, shots[-1].id, f"timeline ends at {expected}, expected duration_s {duration}")

    audio = loaded.get("audio", {})
    if not isinstance(audio, dict):
        _error(findings, "MANIFEST", "audio must be a mapping")
        audio = {}
    guide = _safe_relative_path(root, audio.get("guide_track"), "AUDIO", "guide_track", findings)

    manifest = Manifest(
        path, root, loaded, short_id, width, height, fps, duration, shots, guide, enabled, max_zoom, findings
    )
    for shot in shots:
        shot.resolved_file = resolve_shot_file(root, shot)
    return manifest


def _invalid_manifest(path: Path, message: str) -> Manifest:
    return Manifest(
        path=path,
        root=path.parent,
        raw={},
        short_id="UNKNOWN",
        width=1080,
        height=1920,
        fps=25,
        duration=Decimal(0),
        shots=[],
        guide_track=None,
        kenburns_enabled=False,
        max_zoom=Decimal(1),
        findings=[Finding("ERROR", "MANIFEST", message)],
    )


def _probe(path: Path, selector: str, entries: str) -> dict[str, Any] | None:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return None
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        selector,
        "-show_entries",
        entries,
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def audio_duration(path: Path) -> Decimal | None:
    probe = _probe(path, "a:0", "format=duration")
    try:
        return Decimal(str(probe["format"]["duration"])) if probe else None
    except (KeyError, TypeError, InvalidOperation):
        return None


def collect_findings(manifest: Manifest) -> list[Finding]:
    findings = list(manifest.findings)
    for shot in manifest.shots:
        path = shot.resolved_file
        if shot.status not in APPROVED:
            _warning(findings, shot.id, f"status is {shot.status}; approval gate will block rendering")
        if shot.status not in APPROVED:
            continue
        if path is None or not path.is_file() or not os.access(path, os.R_OK):
            shown = shot.file_value or f"01_STORYBOARD/{shot.id}_v*.{{jpeg,jpg,png}}"
            _error(findings, shot.id, f"resolved file is missing or unreadable: {shown}")
            continue
        probe = _probe(path, "v:0", "stream=width,height")
        streams = probe.get("streams", []) if probe else []
        if not streams or not isinstance(streams[0].get("width"), int) or not isinstance(streams[0].get("height"), int):
            _error(findings, shot.id, f"resolved file is unreadable: {path.relative_to(manifest.root)}")
            continue
        width = streams[0]["width"]
        height = streams[0]["height"]
        aspect_error = abs((width / height) / (9 / 16) - 1)
        if aspect_error > 0.02:
            _warning(findings, shot.id, f"image aspect {width}:{height} deviates more than 2% from 9:16")
        if width < 1080 or height < 1920:
            _warning(findings, shot.id, f"image resolution {width}x{height} is below 1080x1920")

    guide = manifest.guide_track
    if guide is None or not guide.is_file() or not os.access(guide, os.R_OK):
        _warning(findings, "AUDIO", "guide track is missing; render will use silence")
    else:
        duration = audio_duration(guide)
        if duration is None:
            _warning(findings, "AUDIO", "guide track is unreadable; render will use silence")
        elif duration < manifest.duration:
            _warning(
                findings,
                "AUDIO",
                f"guide track is shorter than duration_s ({duration}s < {manifest.duration}s); silence will be padded",
            )
    return findings


def has_errors(findings: list[Finding]) -> bool:
    return any(finding.level == "ERROR" for finding in findings)


def status_counts(manifest: Manifest) -> Counter[str]:
    return Counter(shot.status for shot in manifest.shots)


def relative_display(path: Path | None, root: Path) -> str:
    if path is None:
        return "MISSING"
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
