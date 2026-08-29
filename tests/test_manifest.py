from __future__ import annotations

import shutil

from conftest import write_manifest
from leukcut.manifest import collect_findings, has_errors, load_manifest


def error_messages(path) -> list[str]:
    return [finding.format() for finding in collect_findings(load_manifest(path)) if finding.level == "ERROR"]


def test_production_timeline_tiles_exactly(short_folder) -> None:
    _, manifest_path, _ = short_folder
    assert not has_errors(collect_findings(load_manifest(manifest_path)))


def test_timeline_gap_names_the_shot(short_folder) -> None:
    _, manifest_path, data = short_folder
    data["shots"][1]["t_in"] = "00:03.1"
    write_manifest(manifest_path, data)
    errors = error_messages(manifest_path)
    assert any("SB1_C02 timeline does not tile" in error for error in errors)


def test_duplicate_ids_are_rejected(short_folder) -> None:
    _, manifest_path, data = short_folder
    data["shots"][1]["id"] = "SB1_C01"
    write_manifest(manifest_path, data)
    assert any("SB1_C01 duplicate shot id" in error for error in error_messages(manifest_path))


def test_missing_approved_file_is_rejected(short_folder) -> None:
    _, manifest_path, data = short_folder
    data["shots"][0]["file"] = "01_STORYBOARD/DOES_NOT_EXIST.png"
    write_manifest(manifest_path, data)
    assert any("SB1_C01 resolved file is missing or unreadable" in error for error in error_messages(manifest_path))


def test_null_file_resolves_highest_numeric_version(short_folder) -> None:
    root, manifest_path, _ = short_folder
    original = root / "01_STORYBOARD" / "SB1_C01_v01.png"
    shutil.copyfile(original, root / "01_STORYBOARD" / "SB1_C01_v02.jpg")
    shutil.copyfile(original, root / "01_STORYBOARD" / "SB1_C01_v10.jpeg")
    manifest = load_manifest(manifest_path)
    assert manifest.shots[0].resolved_file.name == "SB1_C01_v10.jpeg"

