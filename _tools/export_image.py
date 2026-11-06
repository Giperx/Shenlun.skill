#!/usr/bin/env python3
"""Repository entry point for the image exporter shipped with the skills."""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parents[1] / "skills/shared/scripts/export_image.py"), run_name="__main__")
