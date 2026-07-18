from pathlib import Path
import shutil
import subprocess


def test_quick_test_prefers_project_venv_python() -> None:
    project_root = Path(__file__).resolve().parents[2]
    script = project_root / "backend" / "quick_test.ps1"
    project_python = project_root / ".venv" / "Scripts" / "python.exe"
    competition_python = (
        project_root / "backend" / "competition" / "Scripts" / "python.exe"
    )
    source = script.read_text(encoding="utf-8-sig")

    assert source.index('$projectRoot ".venv\\Scripts\\python.exe"') < source.index(
        '$backendDir "competition\\Scripts\\python.exe"'
    )
    expected = next(
        (candidate.resolve() for candidate in (project_python, competition_python) if candidate.is_file()),
        None,
    )
    if expected is None:
        system_python = shutil.which("python")
        assert system_python is not None
        expected = Path(system_python).resolve()

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-PrintPython",
        ],
        cwd=project_root,
        capture_output=True,
        timeout=15,
        check=False,
    )

    stdout = result.stdout.decode("utf-8", errors="replace").strip()
    stderr = result.stderr.decode("utf-8", errors="replace").strip()
    assert result.returncode == 0, stderr or stdout
    assert Path(stdout).resolve() == expected
