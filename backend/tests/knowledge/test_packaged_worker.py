from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

import backend.knowledge.import_service as import_service
from backend.knowledge.worker_protocol import DoneEvent, WorkerRequest, parse_worker_line
from backend.tests.knowledge.fixtures.build_fixtures import build_supported_fixtures


def test_release_scripts_collect_and_verify_packaged_worker_dependencies() -> None:
    project_root = Path(__file__).resolve().parents[3]
    build_script = (project_root / "backend" / "build_api.ps1").read_text(encoding="utf-8")
    verify_script = (project_root / "backend" / "verify_api_package.ps1").read_text(encoding="utf-8")

    for package in (
        "backend.knowledge",
        "fitz",
        "docx",
        "pptx",
        "openpyxl",
        "defusedxml",
        "charset_normalizer",
        "numpy",
        "rapidocr_onnxruntime",
        "onnxruntime",
        "cv2",
    ):
        assert f"--collect-all {package}" in build_script
    assert "A3_PACKAGED_API_EXE" in verify_script
    assert "test_packaged_worker.py" in verify_script
    for runtime_dll in (
        "msvcp140.dll",
        "MSVCP140_1.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "concrt140.dll",
    ):
        assert runtime_dll in build_script
    assert "System32" in build_script


def test_frozen_worker_command_uses_the_packaged_executable_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(import_service.sys, "frozen", True, raising=False)
    monkeypatch.setattr(import_service.sys, "executable", r"C:\A3\api.exe")

    command = import_service.knowledge_worker_command(Path(r"C:\A3"))

    assert command == [r"C:\A3\api.exe", "--knowledge-worker"]
    assert "backend.knowledge.worker_main" not in " ".join(command)


def test_run_dispatches_the_worker_before_loading_the_web_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import uvicorn
    import backend.knowledge.worker_main as worker_main
    import backend.run as run

    worker_calls: list[str] = []
    web_calls: list[object] = []
    monkeypatch.setattr(sys, "argv", ["api.exe", "--knowledge-worker"])
    monkeypatch.setattr(worker_main, "main", lambda: worker_calls.append("worker") or 7)
    monkeypatch.setattr(uvicorn, "run", lambda app, **_kwargs: web_calls.append(app))
    monkeypatch.setitem(sys.modules, "backend.main", SimpleNamespace(app=object()))

    assert run.main() == 7
    assert worker_calls == ["worker"]
    assert web_calls == []


PACKAGED_EXECUTABLE = os.environ.get("A3_PACKAGED_API_EXE", "").strip()


@pytest.mark.skipif(
    not PACKAGED_EXECUTABLE,
    reason="set A3_PACKAGED_API_EXE during packaged release verification",
)
@pytest.mark.parametrize(
    "fixture_name",
    [
        "lesson.pdf",
        "lesson.docx",
        "lesson.pptx",
        "lesson.xlsx",
        "lesson.csv",
        "lesson.txt",
        "lesson.md",
    ],
)
def test_packaged_worker_parses_each_supported_format(
    tmp_path: Path,
    fixture_name: str,
) -> None:
    executable = Path(PACKAGED_EXECUTABLE).resolve(strict=True)
    fixtures = build_supported_fixtures(tmp_path / "fixtures")
    source = fixtures / fixture_name
    digest = sha256(source.read_bytes()).hexdigest()
    objects_root = tmp_path / "knowledge" / "objects"
    objects_root.mkdir(parents=True)
    shutil.copyfile(source, objects_root / digest)
    request = WorkerRequest(
        job_id=1,
        object_relpath=f"objects/{digest}",
        extension=source.suffix.lower(),
        limits={},
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"SYSTEMROOT", "TEMP", "TMP"}
    }
    environment.update(
        {
            "PYTHONUTF8": "1",
            "PYTHONNOUSERSITE": "1",
            "A3_KNOWLEDGE_OBJECT_ROOT": str(objects_root),
        }
    )

    completed = subprocess.run(
        [str(executable), "--knowledge-worker"],
        input=(request.model_dump_json() + "\n").encode("utf-8"),
        capture_output=True,
        check=False,
        env=environment,
        timeout=30,
    )

    events = [parse_worker_line(line) for line in completed.stdout.splitlines()]
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    assert events
    assert isinstance(events[-1], DoneEvent)
    assert str(source) not in completed.stdout.decode("utf-8", errors="replace")
