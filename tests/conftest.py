from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml
from PIL import Image, ImageDraw


REPO_ROOT = Path(__file__).parents[1]
PRODUCTION_FIXTURE = REPO_ROOT / "fixtures" / "SHORT_01.manifest.yaml"


@pytest.fixture
def production_data() -> dict:
    return copy.deepcopy(yaml.safe_load(PRODUCTION_FIXTURE.read_text(encoding="utf-8")))


@pytest.fixture
def short_folder(tmp_path: Path, production_data: dict) -> tuple[Path, Path, dict]:
    board = tmp_path / "01_STORYBOARD"
    board.mkdir()
    colors = [(31, 42, 90), (19, 26, 58), (224, 166, 78), (192, 91, 51), (110, 118, 69)]
    for index, shot in enumerate(production_data["shots"]):
        image = Image.new("RGB", (1080, 1920), colors[index % len(colors)])
        ImageDraw.Draw(image).text((60, 60), shot["id"], fill=(255, 255, 255))
        image.save(board / f"{shot['id']}_v01.png")
        shot["file"] = None
        shot["status"] = "approved"
    manifest_path = tmp_path / "SHORT_01.manifest.yaml"
    write_manifest(manifest_path, production_data)
    return tmp_path, manifest_path, production_data


def write_manifest(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

