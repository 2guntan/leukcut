# leukcut

`leukcut` is Waraba Studios' deterministic shot-manifest assembly CLI. It
validates `waraba/shotmanifest/v1`, resolves approved stills, and creates a
vertical H.264/AAC animatic or final cut. It never changes manifests or images,
and it makes no network or AI calls.

The complete contract is [SPEC.md](SPEC.md). The test suite and acceptance
workflow use the real 18-shot [fixture](fixtures/SHORT_01.manifest.yaml).

## Install

Requirements:

- Python 3.11 or newer
- PyYAML (installed automatically)
- ffmpeg/ffprobe 5.1 or newer, built with `libx264`, the native AAC encoder,
  and the standard `zoompan`, `drawbox`, `concat`, `xfade`, and `apad` filters

Install into an isolated command environment:

```console
pipx install .
leukcut --version
```

For development:

```console
python -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest
```

## Commands

When `manifest` is omitted, exactly one `*.manifest.yaml` must exist in the
current directory.

```console
leukcut check [manifest]
leukcut check [manifest] --strict
leukcut status [manifest]
leukcut animatic [manifest] -o 03_RENDERS/SHORT_01_ANIMATIC_v01.mp4
leukcut animatic [manifest] -o 03_RENDERS/REVIEW.mp4 --allow-pending
leukcut final [manifest] -o 03_RENDERS/SHORT_01_FINAL_v01.mp4
```

`animatic` and `final` refuse unapproved shots. `--allow-pending` is animatic
only and replaces every unapproved shot with an indigo slate. A render writes
`<short.id>.srt` beside the video and muxes its cues as a soft subtitle stream.
Both outputs use temporary files and atomic renames.

Exit codes are `0` success, `1` warnings under `check --strict`, `2` validation
failure, `3` approval-gate refusal, and `4` ffmpeg/runtime failure.

## Acceptance fixture

The production fixture has explicit JPEG file paths (including v02/v03), but
the prescribed generator creates v01 PNG placeholders. The second command
below therefore creates a manifest copy with `file: null`, exercising the
contract's highest-`_vNN` convention without altering the source fixture.

```console
.venv/bin/python fixtures/make_placeholders.py
.venv/bin/python fixtures/prepare_acceptance.py
cd fixtures/SHORT_01_LA_LUNE
../../.venv/bin/leukcut check SHORT_01.manifest.yaml
../../.venv/bin/leukcut animatic SHORT_01.manifest.yaml \
  -o 03_RENDERS/SHORT_01_ANIMATIC_v01.mp4
```

The encoder fixes x264 to one thread, strips inherited metadata, uses exact
frame counts, and normalizes stream timing. Re-running with unchanged inputs
is idempotent and produces byte-identical output with the supported ffmpeg
build.
