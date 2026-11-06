#!/usr/bin/env python3
"""Copy the three versioned lecture texts into the standalone skill bundle."""
import argparse
from pathlib import Path
import re

SOURCES = {"PDF-7.txt": 33, "PDF-8.txt": 5, "PDF-9.txt": 37}


def sync(repo, check=False):
    raw = repo / "_sources/饮冰说申论/讲义提取"
    bundle = repo / "skills/shenlun-dawenti/references/yinbing-source-text"
    pending = []
    for name, pages in SOURCES.items():
        source = raw / name
        data = source.read_bytes()
        text = data.decode("utf-8")
        actual = [int(p) for p in re.findall(rf"^===== {name[:-4]} PAGE (\d+) =====$", text, re.M)]
        if actual != list(range(1, pages + 1)):
            raise ValueError(f"Page markers incomplete: {name}")
        target = bundle / name
        if not target.is_file() or target.read_bytes() != data:
            pending.append((target, data))
    if check and pending:
        raise ValueError("Lecture bundle differs; run _tools/sync_yinbing_sources.py")
    for target, data in pending:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    print(f"Lecture texts {'verified' if check else 'synchronized'}: {len(SOURCES)} files / 75 PDF pages")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        sync(Path(__file__).resolve().parents[1], args.check)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Source sync failed: {exc}\n")


if __name__ == "__main__":
    main()
