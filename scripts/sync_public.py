"""Copy the checked-in frontend assets into Vercel's public directory."""

from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "web" / "static"
TARGET = ROOT / "public"


def main() -> int:
    TARGET.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "styles.css", "app.js"):
        shutil.copy2(SOURCE / name, TARGET / name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
