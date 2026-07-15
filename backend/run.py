from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _configure_desktop_data_dir() -> None:
    if not getattr(sys, "frozen", False) or os.environ.get("A3_DATA_DIR"):
        return
    root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "A3LearningAgent"
    root.mkdir(parents=True, exist_ok=True)
    os.environ["A3_DATA_DIR"] = str(root)
    template = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "backend" / ".env.example"
    target = root / ".env"
    if template.exists() and not target.exists():
        shutil.copyfile(template, target)


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--knowledge-worker":
        from backend.knowledge.worker_main import main as worker_main

        return worker_main()
    _configure_desktop_data_dir()
    import uvicorn
    from backend.main import app

    host = os.environ.get("A3_HOST", "127.0.0.1")
    port = int(os.environ.get("A3_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level=os.environ.get("A3_LOG_LEVEL", "info"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
