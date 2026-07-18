from pathlib import Path
import subprocess


def test_quick_test_prefers_project_venv_python():
    project_root = Path(__file__).resolve().parents[2]
    script = project_root / "backend" / "quick_test.ps1"
    expected = (project_root / ".venv" / "Scripts" / "python.exe").resolve()
    source = script.read_text(encoding="utf-8-sig")

    assert source.index('$projectRoot ".venv\\Scripts\\python.exe"') < source.index(
        '$backendDir "competition\\Scripts\\python.exe"'
    )
    if not expected.is_file():
        return

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
