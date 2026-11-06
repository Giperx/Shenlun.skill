#!/usr/bin/env python3
"""Clean reference-book footer watermarks and rebuild page texts and skill volumes."""
import argparse
import json
from pathlib import Path
import re


PAGE_COUNT = 141
MARKER = re.compile(r"^===== TOPIC-2027 PAGE (\d+) =====\n", re.M)
# Match a whole footer with several independent signatures, including OCR errors.
# Do not match ordinary正文 containing 禁止、独家 or the original rights declaration.
FOOTER = re.compile(
    r"^\s*独[家罕].{0,12}二次传.{0,12}商用.{0,20}"
    r"如有问题.{0,40}三次上.{0,5}\s*$"
)
PAGE_BLOCK = re.compile(
    r'(<a id="pdf-(\d{3})"></a>\n\n## [^\n]+\n\n````text\n)'
    r'(.*?)(\n````)', re.S
)


def clean_page(text):
    return "\n".join(
        line for line in text.splitlines() if not FOOTER.fullmatch(line)
    ).strip()


def parse_pages(text):
    parts = MARKER.split(text)
    if parts[0].strip() or [int(p) for p in parts[1::2]] != list(range(1, PAGE_COUNT + 1)):
        raise ValueError("Expected exactly 141 ordered TOPIC-2027 page markers")
    return {int(parts[i]): clean_page(parts[i + 1]) for i in range(1, len(parts), 2)}


def sync(repo, check=False):
    raw = repo / "_sources/参考书"
    source = raw / "2027年高频考点话题-OCR.txt"
    original = source.read_text(encoding="utf-8")
    pages = parse_pages(original)
    outputs = {
        source: "".join(
            f"\n\n===== TOPIC-2027 PAGE {page} =====\n\n{body}\n"
            for page, body in pages.items()
        )
    }
    for page, body in pages.items():
        outputs[raw / f"ocr/{page:03}.txt"] = body + "\n"
    outputs[raw / "ocr-cleaned-counts.json"] = json.dumps(
        {
            "source": "TOPIC-2027",
            "page_count": PAGE_COUNT,
            "count_definition": "Unicode characters after footer removal, excluding leading/trailing whitespace",
            "pages": {str(page): len(body) for page, body in pages.items()},
        }, ensure_ascii=False, indent=2
    ) + "\n"

    bundle = repo / "skills/shenlun-dawenti/references/topic-library/source-text"
    seen = []

    def replace_block(match):
        page = int(match[2])
        if page not in pages:
            raise ValueError(f"Unexpected bundle page {page}")
        seen.append(page)
        return match[1] + pages[page] + match[4]

    for target in sorted(bundle.glob("*.md")):
        if target.name == "INDEX.md":
            continue
        outputs[target] = PAGE_BLOCK.sub(replace_block, target.read_text(encoding="utf-8"))
    if sorted(seen) != list(range(1, PAGE_COUNT + 1)):
        raise ValueError("Bundle must contain each page exactly once")

    pending = [
        (target, content.encode("utf-8")) for target, content in outputs.items()
        if not target.exists() or target.read_bytes() != content.encode("utf-8")
    ]
    if check and pending:
        raise ValueError(f"{len(pending)} files differ; run _tools/sync_topic_sources.py")
    for target, data in pending:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    removed = sum(bool(FOOTER.fullmatch(line)) for line in original.splitlines())
    print(f"Reference OCR {'verified' if check else 'synchronized'}: "
          f"141 pages, {len(pending)} files updated, {removed} merged footer lines removed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify without writing")
    args = parser.parse_args()
    try:
        sync(Path(__file__).resolve().parents[1], args.check)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Reference sync failed: {exc}\n")


if __name__ == "__main__":
    main()
