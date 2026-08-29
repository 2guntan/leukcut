# LEUKCUT — Shot-manifest assembly CLI · Handoff spec v1

**Waraba Studios · 2026-08-28 · Contract between the studio (Bou + AD) and the implementing agent (Codex).**
This document is the complete specification. Real production data ships with it: `SHORT_01.manifest.yaml` (18 shots). Build against it, not against invented examples.

## 1. Purpose

`leukcut` turns a validated shot manifest + a folder of approved still images + one guide audio track into a finished vertical video (animatic first, final cut later), deterministically and repeatably. It is the *assembly* stage of the studio pipeline. The creative stages (image generation, artistic review, status changes) happen elsewhere and are **out of scope**.

## 2. Non-goals (hard boundaries)

- **Never generates or modifies images.** No AI calls of any kind, no network access at runtime.
- **Never writes to the manifest.** `status` fields are set only by the studio's validation loop. `leukcut` reads, checks, assembles.
- **Never invents timing.** All durations come from the manifest timecodes.
- No GUI. CLI only.

## 3. Inputs & folder contract

Working directory = one short's folder (e.g. `SHORT_01_LA_LUNE/`):

```
SHORT_01_LA_LUNE/
  SHORT_01.manifest.yaml        # source of truth (schema waraba/shotmanifest/v1)
  01_STORYBOARD/                # stills, named SB1_C01_v01.jpeg (id + _vNN)
  02_AUDIO/GUIDE_TRACK_V1.wav   # single guide track (kora + silences), optional
  03_RENDERS/                   # leukcut outputs (created if missing)
```

Manifest schema essentials (see the YAML for the full shape):
- `short.format`: aspect `9:16`, resolution `[1080,1920]`, `fps`, `duration_s`.
- `shots[]`: `id`, `t_in`/`t_out` as `MM:SS.d`, `dialogue` (nullable, used for subtitles), `star_state` (`off|ignite|sparkle`), `status` (`pending|generated|approved|locked`), `file` (relative path, nullable), `version`.
- `defaults.kenburns`: `{enabled, max_zoom}`.
- `audio.guide_track` + `audio.markers` (informational in v1).

If `file` is null for a shot, resolve it by convention: highest `_vNN` matching `01_STORYBOARD/<id>_v*.{jpeg,jpg,png}`.

## 4. Commands

### `leukcut check [manifest]`
Validates and reports. Errors (exit 2): YAML/schema invalid; shot timecodes do not tile `0 → duration_s` exactly; duplicate ids; a shot with status `approved|locked` whose resolved file is missing or unreadable. Warnings (exit 1 with `--strict`, else 0): image aspect ratio deviating >2% from 9:16; resolution below 1080×1920; guide track missing or shorter than `duration_s`; any shot not yet `approved|locked`. Output: one line per finding, `ERROR|WARN <shot_id> <message>`, then a summary table of statuses.

### `leukcut status [manifest]`
Prints the shot table: id, t_in–t_out, duration, status, resolved file, version. No side effects.

### `leukcut animatic [manifest] -o 03_RENDERS/SHORT_01_ANIMATIC_vNN.mp4`
The v1 deliverable. **Gate: refuses (exit 3) unless every shot is `approved` or `locked`** — listing the blockers — unless `--allow-pending` is passed (then pending shots render as a slate: indigo #1F2A5A card with the shot id and action text in white).
- Each still is scaled/cropped (`cover`) to 1080×1920, shown for exactly `t_out - t_in`.
- Ken Burns when `defaults.kenburns.enabled`: slow center zoom from 1.0 to ≤ `max_zoom` over the shot (ffmpeg `zoompan`), alternating in/out per shot for rhythm.
- Hard cuts only in v1.
- Burn-ins (animatic mode only): shot id top-left, running timecode top-right, small, white at 70% opacity.
- Audio: `audio.guide_track` laid from 00:00, padded with silence or trimmed to `duration_s`. If absent, silent track.
- Subtitles: generate `SHORT_01.srt` from non-null `dialogue` fields (shot's full time range), written next to the output. Do not burn them in; mux as a soft subtitle stream if the container allows.
- Container: H.264 + AAC, `yuv420p`, faststart, 25 fps (from manifest), CRF ≈ 18.

### `leukcut final [manifest] -o ...`
Same as `animatic` without burn-ins, with 8-frame crossfades where `transition: crossfade` is set on a shot (v1 keeps cuts as default). Same gate, no `--allow-pending`.

## 5. Behavior requirements

- **Deterministic**: same inputs → byte-comparable outputs (fixed seeds/threads where ffmpeg allows; at minimum identical timing and structure).
- **Idempotent**: re-running overwrites the target output atomically (write temp, rename).
- **Total duration** of the render must equal `duration_s` ± 1 frame.
- Clear failures: never emit a video on exit ≠ 0.
- Runtime: Python ≥ 3.11, deps limited to `PyYAML` + system `ffmpeg` (document the minimum ffmpeg version). Single file or small package, `pipx`-installable.

## 6. Exit codes

`0` OK · `1` warnings under `--strict` · `2` manifest/file validation error · `3` gate refusal (unapproved shots) · `4` ffmpeg/runtime failure.

## 7. Acceptance test (must pass before handback)

1. Generate 18 placeholder stills (solid colors + shot id text, 1080×1920) named `SB1_C01_v01.png` … `SB1_C18_v01.png` via ffmpeg/PIL.
2. Set every status to `approved` in a **copy** of the manifest.
3. `leukcut check` → exit 0 (warnings allowed for missing audio).
4. `leukcut animatic` → MP4 of 60.0 s ± 1 frame, 1080×1920, 25 fps, plays in QuickTime/VLC, burn-ins visible, `SHORT_01.srt` contains 2 cues (C08, C17).
5. Corrupt one timecode → `check` exits 2 with a message naming the shot.
6. Set one shot back to `pending` → `animatic` exits 3 naming it; `--allow-pending` renders a slate for it.

## 8. Out of scope for v1 (planned v2 — do not build now)

Multi-track audio mixing at `audio.markers`; per-shot video clips (image-to-video) replacing stills via a `media: video` field; styled burned subtitles; OTIO export.
