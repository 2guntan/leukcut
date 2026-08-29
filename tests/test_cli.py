from __future__ import annotations

from conftest import write_manifest
from leukcut.cli import EXIT_GATE, main


def test_animatic_gate_refuses_and_names_pending_shot(short_folder, capsys) -> None:
    root, manifest_path, data = short_folder
    data["shots"][7]["status"] = "pending"
    write_manifest(manifest_path, data)
    exit_code = main(["animatic", str(manifest_path), "-o", str(root / "blocked.mp4")])
    output = capsys.readouterr().out
    assert exit_code == EXIT_GATE
    assert "SB1_C08" in output
    assert not (root / "blocked.mp4").exists()

