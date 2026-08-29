from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from leukcut.bitmap_text import draw_text_filters, timecode_filters, wrap_action
from leukcut.manifest import APPROVED, Manifest, Shot, audio_duration


@dataclass(frozen=True)
class RenderResult:
    ok: bool
    message: str = ""
    command: tuple[str, ...] = ()


def _number(value: Decimal) -> str:
    return format(value, "f")


def srt_timestamp(value: Decimal) -> str:
    milliseconds = int((value * 1000).to_integral_value())
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def make_srt(manifest: Manifest) -> str:
    blocks: list[str] = []
    cue = 1
    for shot in manifest.shots:
        if shot.dialogue is None:
            continue
        blocks.append(
            f"{cue}\n{srt_timestamp(shot.t_in)} --> {srt_timestamp(shot.t_out)}\n{shot.dialogue}\n"
        )
        cue += 1
    return "\n".join(blocks)


def _base_clip_filter(manifest: Manifest, shot: Shot, index: int, slate: bool) -> list[str]:
    frames = int(shot.duration * manifest.fps)
    if slate:
        filters = [f"trim=end_frame={frames}", f"setpts=N/({manifest.fps}*TB)"]
        slate_lines = [shot.id, *wrap_action(shot.action)]
        line_height = 7 * 5 + 15
        slate_y = max(200, (manifest.height - len(slate_lines) * line_height) // 2)
        filters.extend(draw_text_filters(shot.id, 120, slate_y, 7, "white"))
        action_y = slate_y + 90
        for line_no, line in enumerate(slate_lines[1:]):
            filters.extend(draw_text_filters(line, 120, action_y + line_no * line_height, 5, "white"))
    else:
        filters = [
            f"scale={manifest.width}:{manifest.height}:force_original_aspect_ratio=increase:flags=lanczos",
            f"crop={manifest.width}:{manifest.height}",
        ]
        if manifest.kenburns_enabled and frames > 1:
            delta = _number(manifest.max_zoom - Decimal(1))
            maximum = _number(manifest.max_zoom)
            if index % 2 == 0:
                zoom = f"1+{delta}*on/{frames - 1}"
            else:
                zoom = f"{maximum}-{delta}*on/{frames - 1}"
            filters.append(
                f"zoompan=z='{zoom}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':"
                f"d={frames}:s={manifest.width}x{manifest.height}:fps={manifest.fps}"
            )
        else:
            filters.append(f"fps={manifest.fps}")
        filters.extend([f"trim=end_frame={frames}", f"setpts=N/({manifest.fps}*TB)"])
    filters.append("format=yuv420p")
    return filters


def _cut_graph(manifest: Manifest, labels: list[str]) -> tuple[list[str], str]:
    if len(labels) == 1:
        return [], labels[0]
    output = "cutv"
    return [f"{''.join(f'[{label}]' for label in labels)}concat=n={len(labels)}:v=1:a=0[{output}]"] , output


def _final_graph(manifest: Manifest, labels: list[str]) -> tuple[list[str], str]:
    fades = [shot.transition == "crossfade" for shot in manifest.shots[:-1]]
    if not any(fades):
        return _cut_graph(manifest, labels)
    fade_frames = 8
    half = fade_frames // 2
    graph: list[str] = []
    exclusive_labels: list[str] = []
    incoming_labels: list[str | None] = [None] * len(labels)
    outgoing_labels: list[str | None] = [None] * len(labels)
    for index, (shot, label) in enumerate(zip(manifest.shots, labels, strict=True)):
        frames = int(shot.duration * manifest.fps)
        incoming = index > 0 and fades[index - 1]
        outgoing = index < len(fades) and fades[index]
        uses = 1 + int(incoming) + int(outgoing)
        branches = [f"sp{index}_{branch}" for branch in range(uses)]
        if uses == 1:
            graph.append(f"[{label}]null[{branches[0]}]")
        else:
            graph.append(f"[{label}]split={uses}{''.join(f'[{branch}]' for branch in branches)}")
        cursor = 0
        start = half if incoming else 0
        end = frames - half if outgoing else frames
        exclusive = f"ex{index}"
        graph.append(
            f"[{branches[cursor]}]trim=start_frame={start}:end_frame={end},"
            f"setpts=N/({manifest.fps}*TB)[{exclusive}]"
        )
        exclusive_labels.append(exclusive)
        cursor += 1
        if incoming:
            incoming_label = f"in{index}"
            graph.append(
                f"[{branches[cursor]}]trim=start_frame=0:end_frame={fade_frames},"
                f"setpts=N/({manifest.fps}*TB)[{incoming_label}]"
            )
            incoming_labels[index] = incoming_label
            cursor += 1
        if outgoing:
            outgoing_label = f"out{index}"
            graph.append(
                f"[{branches[cursor]}]trim=start_frame={frames - fade_frames}:end_frame={frames},"
                f"setpts=N/({manifest.fps}*TB)[{outgoing_label}]"
            )
            outgoing_labels[index] = outgoing_label
    transition_labels: dict[int, str] = {}
    for index, enabled in enumerate(fades):
        if not enabled:
            continue
        output = f"xf{index}"
        duration = Decimal(fade_frames) / manifest.fps
        graph.append(
            f"[{outgoing_labels[index]}][{incoming_labels[index + 1]}]"
            f"xfade=transition=fade:duration={_number(duration)}:offset=0[{output}]"
        )
        transition_labels[index] = output
    components: list[str] = []
    for index, exclusive in enumerate(exclusive_labels):
        components.append(exclusive)
        if index in transition_labels:
            components.append(transition_labels[index])
    output = "finalv"
    graph.append(f"{''.join(f'[{label}]' for label in components)}concat=n={len(components)}:v=1:a=0[{output}]")
    return graph, output


def _write_temp_text(directory: Path, suffix: str, content: str) -> Path:
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, suffix=suffix, delete=False)
    try:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    finally:
        handle.close()
    return Path(handle.name)


def render(manifest: Manifest, output: Path, mode: str, allow_pending: bool = False) -> RenderResult:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return RenderResult(False, "ffmpeg is not installed or not on PATH")
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    srt_output = output.parent / f"{manifest.short_id}.srt"
    temporary_paths: list[Path] = []
    try:
        video_handle = tempfile.NamedTemporaryFile(dir=output.parent, suffix=".mp4", delete=False)
        video_handle.close()
        temp_video = Path(video_handle.name)
        temporary_paths.append(temp_video)
        temp_srt = _write_temp_text(output.parent, ".srt", make_srt(manifest))
        temporary_paths.append(temp_srt)

        command = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-y"]
        labels: list[str] = []
        graph: list[str] = []
        for index, shot in enumerate(manifest.shots):
            slate = allow_pending and shot.status not in APPROVED
            if slate:
                command.extend(
                    [
                        "-f",
                        "lavfi",
                        "-i",
                        f"color=c=0x1F2A5A:s={manifest.width}x{manifest.height}:r={manifest.fps}",
                    ]
                )
            else:
                command.extend(["-loop", "1", "-framerate", str(manifest.fps), "-i", str(shot.resolved_file)])
            label = f"shot{index}"
            filters = _base_clip_filter(manifest, shot, index, slate)
            if mode == "animatic":
                filters.extend(draw_text_filters(shot.id, 42, 42, 4, "white@0.7"))
            graph.append(f"[{index}:v]{','.join(filters)}[{label}]")
            labels.append(label)

        audio_index = len(manifest.shots)
        if (
            manifest.guide_track is not None
            and manifest.guide_track.is_file()
            and audio_duration(manifest.guide_track) is not None
        ):
            command.extend(["-i", str(manifest.guide_track)])
        else:
            command.extend(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"])
        srt_text = make_srt(manifest)
        subtitle_index: int | None = None
        if srt_text:
            subtitle_index = audio_index + 1
            command.extend(["-f", "srt", "-i", str(temp_srt)])

        assembly_graph, visual_label = (
            _cut_graph(manifest, labels) if mode == "animatic" else _final_graph(manifest, labels)
        )
        graph.extend(assembly_graph)
        final_filters: list[str] = []
        if mode == "animatic":
            final_filters.extend(timecode_filters(manifest.width, manifest.fps))
        final_filters.extend(
            [
                f"trim=end_frame={manifest.total_frames}",
                f"setpts=N/({manifest.fps}*TB)",
                "format=yuv420p",
            ]
        )
        graph.append(f"[{visual_label}]{','.join(final_filters)}[vout]")
        graph.append(
            f"[{audio_index}:a]aresample=48000,apad,atrim=end={_number(manifest.duration)},"
            "asetpts=N/SR/TB[aout]"
        )
        temp_graph = _write_temp_text(output.parent, ".ffgraph", ";\n".join(graph) + "\n")
        temporary_paths.append(temp_graph)

        command.extend(["-filter_complex_script", str(temp_graph), "-map", "[vout]", "-map", "[aout]"])
        if subtitle_index is not None:
            command.extend(["-map", f"{subtitle_index}:s:0"])
        command.extend(
            [
                "-map_metadata",
                "-1",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-r",
                str(manifest.fps),
                "-fps_mode",
                "cfr",
                "-frames:v",
                str(manifest.total_frames),
                "-x264-params",
                "threads=1:lookahead_threads=1:sliced_threads=0",
                "-threads",
                "1",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
            ]
        )
        if subtitle_index is not None:
            command.extend(["-c:s", "mov_text", "-metadata:s:s:0", "language=fra"])
        command.extend(
            [
                "-movflags",
                "+faststart",
                "-fflags",
                "+bitexact",
                "-flags:v",
                "+bitexact",
                "-flags:a",
                "+bitexact",
                str(temp_video),
            ]
        )
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            detail = result.stderr.strip().splitlines()
            message = detail[-1] if detail else f"ffmpeg exited {result.returncode}"
            return RenderResult(False, message, tuple(command))
        if not temp_video.is_file() or temp_video.stat().st_size == 0:
            return RenderResult(False, "ffmpeg did not create a non-empty video", tuple(command))
        os.replace(temp_srt, srt_output)
        temporary_paths.remove(temp_srt)
        os.replace(temp_video, output)
        temporary_paths.remove(temp_video)
        return RenderResult(True, command=tuple(command))
    except OSError as exc:
        return RenderResult(False, str(exc))
    finally:
        for path in temporary_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
