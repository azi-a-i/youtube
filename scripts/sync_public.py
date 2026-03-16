"""Copy the checked-in frontend assets into Vercel's public directory."""

from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "web" / "static"
TARGET = ROOT / "public"


def main() -> int:
    TARGET.mkdir(parents=True, exist_ok=True)
    for name in ("styles.css", "app.js"):
        shutil.copy2(SOURCE / name, TARGET / name)
    stale_index = TARGET / "index.html"
    if stale_index.exists():
        stale_index.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
