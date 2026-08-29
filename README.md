# leukcut

Deterministic shot-manifest assembly CLI for Waraba Studios' shorts pipeline.
Reads a validated `*.manifest.yaml` (schema `waraba/shotmanifest/v1`), a folder
of approved stills and one guide audio track, and assembles the vertical video
(animatic first). It never generates images and never writes to the manifest.

- **Full specification (the contract): [SPEC.md](SPEC.md)** — build against it.
- **Real production data: `fixtures/SHORT_01.manifest.yaml`** — an 18-shot
  manifest with every shot `approved` (real timecodes, dialogue, star/tail
  canon fields). Develop and test against this file, not invented examples.
- Placeholder stills for the acceptance test: `python fixtures/make_placeholders.py`
  (creates `fixtures/SHORT_01_LA_LUNE/01_STORYBOARD/SB1_C01_v01.png` … `C18`).

Commands to implement: `leukcut check` · `leukcut status` · `leukcut animatic` · `leukcut final`.
Exit codes, gates, burn-ins, SRT generation and the acceptance test are all in SPEC.md.

Runtime: Python >= 3.11, PyYAML, system ffmpeg. No network at runtime.
