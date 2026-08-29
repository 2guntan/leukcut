#!/usr/bin/env python3
"""Prepare the SPEC section 7 manifest copy beside generated placeholders.

The checked-in production manifest names explicit JPEG versions, while
make_placeholders.py creates v01 PNG files. The acceptance copy clears `file`
so the specified convention resolver selects those placeholders. The source
manifest is never changed.
"""

from pathlib import Path

import yaml


here = Path(__file__).parent
source = here / "SHORT_01.manifest.yaml"
target = here / "SHORT_01_LA_LUNE" / "SHORT_01.manifest.yaml"
manifest = yaml.safe_load(source.read_text(encoding="utf-8"))
for shot in manifest["shots"]:
    shot["status"] = "approved"
    shot["file"] = None
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
print(f"Acceptance manifest copy: {target}")

