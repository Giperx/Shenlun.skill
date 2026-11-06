#!/usr/bin/env python3
"""Install the three Shenlun skills and their shared resources without overwriting."""
import argparse
import os
from pathlib import Path
import shutil
import tempfile

NAMES = ("shenlun-router", "shenlun-xiaoti", "shenlun-dawenti", "shared")


def install(repo, destination, mode):
    sources = {name: repo / "skills" / name for name in NAMES}
    for name, source in sources.items():
        required = source / ("references" if name == "shared" else "SKILL.md")
        if not required.exists():
            raise ValueError(f"Incomplete package: {required}")
    # Standalone installs must retain original-text lookup and the image exporter.
    bundled_files = [
        "shenlun-dawenti/references/yinbing-source-text/INDEX.md",
        *(f"shenlun-dawenti/references/yinbing-source-text/PDF-{n}.txt" for n in (7, 8, 9)),
        "shared/scripts/export_image.py",
        "shared/references/image-export-rules.md",
    ]
    for relative in bundled_files:
        if not (repo / "skills" / relative).is_file():
            raise ValueError(f"Incomplete package: skills/{relative}")
    destination = destination.expanduser().resolve()
    pending = []
    # Check all names before making any changes, including shared resources.
    for name, source in sources.items():
        target = destination / name
        if target.is_symlink() and target.resolve() == source.resolve():
            print(f"Already linked: {target}")
            continue
        if os.path.lexists(target):
            raise FileExistsError(f"Destination exists; nothing overwritten: {target}")
        if destination == source or source in destination.parents:
            raise ValueError("Destination cannot be inside a source skill")
        pending.append(name)
    if not pending:
        return
    destination.mkdir(parents=True, exist_ok=True)
    created = []
    with tempfile.TemporaryDirectory(prefix=".shenlun-install-", dir=destination) as stage:
        stage = Path(stage)
        for name in pending:
            if mode == "link":
                (stage / name).symlink_to(sources[name].resolve(), target_is_directory=True)
            else:
                shutil.copytree(sources[name], stage / name,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
        try:
            for name in pending:
                target = destination / name
                if os.path.lexists(target):
                    raise FileExistsError(f"Destination changed during install: {target}")
                (stage / name).rename(target)
                created.append(target)
        except Exception:
            for target in reversed(created):
                if target.is_symlink():
                    target.unlink()
                else:
                    shutil.rmtree(target)
            raise
    for target in created:
        print(f"Installed ({mode}): {target}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path,
                        default=Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills",
                        help="Agent skills root (default: $CODEX_HOME/skills or ~/.codex/skills)")
    parser.add_argument("--mode", choices=("copy", "link"), default="copy",
                        help="copy for a standalone install; link to follow this checkout")
    args = parser.parse_args()
    try:
        install(Path(__file__).resolve().parents[1], args.dest, args.mode)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Install failed: {exc}\n")


if __name__ == "__main__":
    main()
