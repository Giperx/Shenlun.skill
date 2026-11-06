#!/usr/bin/env python3
"""Render Markdown to a black Songti PNG, optionally prefixed with an exam prompt.

Requires Pillow. Uses system fonts; no browser, account, or bundled font required.
"""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise SystemExit("缺少Pillow，请先执行：python3 -m pip install Pillow")


@dataclass(frozen=True)
class Face:
    path: str
    index: int = 0


def find_fonts(regular=None, bold=None, index=0, bold_index=0):
    if regular:
        return Face(str(regular), index), Face(str(bold), bold_index) if bold else None
    candidates = [
        ("/System/Library/Fonts/Supplemental/Songti.ttc", 6, 1),
        ("C:/Windows/Fonts/simsun.ttc", 0, None),
        ("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc", 2, None),
        ("/usr/share/fonts/truetype/arphic/uming.ttc", 0, None),
    ]
    for path, normal_index, heavy_index in candidates:
        if Path(path).is_file():
            normal = Face(path, normal_index)
            heavy = Face(str(bold), bold_index) if bold else (Face(path, heavy_index) if heavy_index is not None else None)
            return normal, heavy
    raise ValueError("未找到宋体/中文衬线字体。请用 --font 指定宋体文件，可另用 --bold-font 指定粗体。")


def inline(text, base_bold=False):
    """Keep visible text and bold runs. Link destinations are listed in the footer."""
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    spans = []
    for token in re.split(r"(\*\*.*?\*\*)", text):
        marked = token.startswith("**") and token.endswith("**") and len(token) >= 4
        spans.append((token[2:-2] if marked else token, base_bold or marked))
    return spans


def blocks(markdown):
    """A small, deterministic parser for the Markdown used in Shenlun answers."""
    lines = markdown.splitlines()
    result = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue
        if re.fullmatch(r"[-*_]{3,}", line):
            result.append(("rule", ""))
        elif line.startswith("```"):
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += i < len(lines)
            result.extend(("paragraph", x) for x in code)
        elif line.startswith("|"):
            table = [line]
            while i < len(lines) and lines[i].strip().startswith("|"):
                table.append(lines[i].strip())
                i += 1
            rows = []
            for row in table:
                cells = [cell.strip() for cell in row.strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", cell) for cell in cells):
                    rows.append(cells)
            result.append(("table", rows))
        elif line.startswith(">"):
            quote = [re.sub(r"^>\s?", "", line)]
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(re.sub(r"^>\s?", "", lines[i].strip()))
                i += 1
            result.append(("quote", " ".join(quote)))
        elif re.match(r"^#{1,6}\s", line):
            result.append(("heading", re.sub(r"^#{1,6}\s+", "", line)))
        elif re.fullmatch(r"\*\*[^*]+\*\*", line):
            result.append(("heading", line[2:-2]))
        elif re.match(r"^[-+*]\s+", line):
            result.append(("bullet", re.sub(r"^[-+*]\s+", "", line)))
        elif re.match(r"^\d+[.)]\s+", line):
            result.append(("paragraph", line))
        else:
            paragraph = [line]
            while i < len(lines) and lines[i].strip():
                following = lines[i].strip()
                if re.match(r"^(?:[>|#]|[-+*]\s|\d+[.)]\s|```)", following):
                    break
                if re.fullmatch(r"[-*_]{3,}", following) or re.fullmatch(r"\*\*[^*]+\*\*", following):
                    break
                paragraph.append(following)
                i += 1
            result.append(("paragraph", " ".join(paragraph)))
    return result


class Renderer:
    def __init__(self, width, size, regular, bold):
        self.width, self.size = width, size
        self.margin = round(width * .055)
        self.content_width = width - self.margin * 2
        if self.content_width < size * 8:
            raise ValueError("图像宽度不足，请增加 --width 或减小 --font-size。")
        self.regular, self.bold = regular, bold
        self.fonts = {}
        self.ops = []
        self.y = self.margin
        self.sections = []
        self.visible_characters = 0

    def font(self, size, bold=False):
        key = (size, bold)
        if key not in self.fonts:
            face = self.bold if bold and self.bold else self.regular
            self.fonts[key] = ImageFont.truetype(face.path, size, index=face.index)
        return self.fonts[key]

    def stroke(self, bold):
        return 1 if bold and self.bold is None else 0

    def advance(self, text, size, bold):
        return self.font(size, bold).getlength(text) + self.stroke(bold) * 2

    def wrap(self, spans, width, size):
        units = []
        # Keep ordinary Latin words and numbers together; split only oversized tokens.
        for text, bold in spans:
            for token in re.findall(r"[A-Za-z0-9_]+|[^A-Za-z0-9_]", text):
                pieces = list(token) if self.advance(token, size, bold) > width - size * 2 else [token]
                units.extend((piece, bold, self.advance(piece, size, bold)) for piece in pieces)
        start_punctuation = set("，。、；：？！）》】〉」』”’％%…—,.;:!?)]}")
        end_punctuation = set("（《【〈「『“‘([{")
        lines, line, used = [], [], 0
        for token, bold, advance in units:
            if token == "\n":
                lines.append(line)
                line, used = [], 0
                continue
            if line and used + advance > width:
                carry = []
                if token in start_punctuation:
                    carry.insert(0, line.pop())
                    while line and carry[0][0] in start_punctuation:
                        carry.insert(0, line.pop())
                while line and line[-1][0] in end_punctuation:
                    carry.insert(0, line.pop())
                if line:
                    lines.append(line)
                line = carry
                used = sum(unit[2] for unit in line)
            line.append((token, bold, advance))
            used += advance
        if line:
            lines.append(line)
        before = "".join(text for text, _ in spans).replace("\n", "")
        after = "".join(token for line in lines for token, _, _ in line)
        if before != after:
            raise ValueError("换行后正文不完整。")
        for line in lines:
            if sum(unit[2] for unit in line) > width + 1:
                raise ValueError("文字行超出可用宽度，请增加图像宽度。")
        self.visible_characters += len(before)
        return lines or [[]]

    def paint(self, lines, x, y, size):
        leading = round(size * 1.65)
        for line in lines:
            cursor = x
            for token, bold, advance in line:
                self.ops.append(("text", cursor, y, token, size, bold))
                cursor += advance
            y += leading
        return y

    def paragraph(self, text, size=None, bold=False, indent=0):
        size = size or self.size
        spans = inline(text, bold)
        plan = self.wrap(spans, self.content_width - indent, size)
        self.y = self.paint(plan, self.margin + indent, self.y, size) + round(size * .45)

    def rule(self):
        self.y += self.size * .35
        self.ops.append(("rule", self.margin, self.y, self.width - self.margin, self.y + 1))
        self.y += self.size * .85

    def table(self, rows):
        if not rows:
            return
        columns = max(map(len, rows))
        pad = max(8, self.size // 3)
        size = max(18, self.size - 5)
        minimum = size * 2 + pad * 2
        if columns * minimum > self.content_width:
            raise ValueError("表格列数过多，请增加 --width。")
        weights = [max(2, min(20, max((len(row[j]) if j < len(row) else 0) for row in rows))) for j in range(columns)]
        extra = self.content_width - minimum * columns
        widths = [minimum + extra * weight / sum(weights) for weight in weights]
        for row_index, row in enumerate(rows):
            row = row + [""] * (columns - len(row))
            plans = [self.wrap(inline(cell, row_index == 0), widths[j] - 2 * pad, size) for j, cell in enumerate(row)]
            height = max(map(len, plans)) * round(size * 1.65) + pad * 2
            x = self.margin
            for width, plan in zip(widths, plans):
                self.ops.append(("box", x, self.y, x + width, self.y + height, "#f4f4f4" if row_index == 0 else "white"))
                self.paint(plan, x + pad, self.y + pad, size)
                x += width
            self.y += height
        self.y += self.size * .6

    def markdown(self, text):
        for kind, value in blocks(text):
            if kind == "rule":
                self.rule()
            elif kind == "table":
                self.table(value)
            elif kind == "heading":
                self.y += self.size * .45
                self.paragraph(value, round(self.size * 1.15), bold=True)
            elif kind == "quote":
                pad = self.size * .6
                plan = self.wrap(inline(value), self.content_width - pad * 2, self.size)
                height = len(plan) * round(self.size * 1.65) + pad * 2
                self.ops.append(("box", self.margin, self.y, self.width - self.margin, self.y + height, "#f6f6f6"))
                self.paint(plan, self.margin + pad, self.y + pad, self.size)
                self.y += height + self.size * .6
            elif kind == "bullet":
                self.ops.append(("text", self.margin, self.y, "•", self.size, False))
                self.paragraph(value, indent=self.size)
            else:
                self.paragraph(value)

    def save(self, output):
        height = round(self.y + self.margin)
        if self.width * height > 100_000_000:
            raise ValueError("长图超过1亿像素，请分段导出或减小字体、宽度。")
        image = Image.new("RGB", (self.width, height), "white")
        draw = ImageDraw.Draw(image)
        for op in self.ops:
            if op[0] == "text":
                _, x, y, token, size, bold = op
                face = self.font(size, bold)
                baseline = y + max(self.font(size).getmetrics()[0], face.getmetrics()[0])
                stroke = self.stroke(bold)
                bbox = draw.textbbox((x, baseline), token, font=face, anchor="ls", stroke_width=stroke)
                if bbox[0] < 0 or bbox[2] > self.width or bbox[1] < 0 or bbox[3] > height:
                    raise ValueError(f"文字超出画布：{token!r}")
                draw.text((x, baseline), token, font=face, fill="black", anchor="ls", stroke_width=stroke)
            elif op[0] == "rule":
                draw.line(op[1:], fill="#b0b0b0", width=2)
            else:
                _, x1, y1, x2, y2, fill = op
                draw.rectangle((x1, y1, x2, y2), fill=fill, outline="#dedede", width=1)
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output, format="PNG", optimize=True)
        return image.size


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="完整回答的UTF-8 Markdown")
    parser.add_argument("output", type=Path, help="输出PNG")
    parser.add_argument("--prompt", type=Path, help="原考试题干及要求的UTF-8 Markdown")
    parser.add_argument("--title", default="申论学习长图")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--font-size", type=int, default=38)
    parser.add_argument("--font", type=Path)
    parser.add_argument("--bold-font", type=Path)
    parser.add_argument("--font-index", type=int, default=0)
    parser.add_argument("--bold-font-index", type=int, default=0)
    parser.add_argument("--manifest", type=Path, help="可选：输出字体、尺寸与正文计数JSON")
    args = parser.parse_args()
    try:
        if not 400 <= args.width <= 6000 or not 18 <= args.font_size <= 120:
            raise ValueError("宽度须在400–6000之间，字号须在18–120之间。")
        if args.input.resolve() == args.output.resolve() or (args.prompt and args.prompt.resolve() == args.output.resolve()):
            raise ValueError("输出不能覆盖输入正文或题干。")
        if args.manifest and args.manifest.resolve() in {p.resolve() for p in (args.input, args.output, args.prompt) if p}:
            raise ValueError("检查报告不能覆盖正文、题干或PNG。")
        answer = args.input.read_text(encoding="utf-8")
        prompt = args.prompt.read_text(encoding="utf-8") if args.prompt else None
        if not answer.strip() or (prompt is not None and not prompt.strip()):
            raise ValueError("正文或题干为空。")
        regular, bold = find_fonts(args.font, args.bold_font, args.font_index, args.bold_font_index)
        renderer = Renderer(args.width, args.font_size, regular, bold)
        renderer.paragraph(args.title, round(args.font_size * 1.4), bold=True)
        renderer.rule()
        if prompt:
            renderer.sections.append({"title": "原考试题目", "y": round(renderer.y)})
            renderer.paragraph("原考试题目", bold=True)
            renderer.markdown(prompt)
            renderer.rule()
        renderer.sections.append({"title": "完整回答", "y": round(renderer.y)})
        renderer.paragraph("完整回答", bold=True)
        renderer.markdown(answer)
        links = list(dict.fromkeys(re.findall(r"\[[^\]]+\]\(([^)]+)\)", (prompt or "") + "\n" + answer)))
        if links:
            renderer.rule()
            renderer.paragraph("原文链接", size=max(22, args.font_size - 8), bold=True)
            for link in links:
                renderer.paragraph(link, size=max(22, args.font_size - 10))
        dimensions = renderer.save(args.output)
        report = {"output": str(args.output), "dimensions": dimensions,
                  "font_regular": renderer.font(args.font_size).getname(),
                  "font_bold": renderer.font(args.font_size, True).getname(),
                  "synthetic_bold": bold is None, "text_color": "#000000",
                  "prompt_included": prompt is not None,
                  "visible_characters": renderer.visible_characters, "sections": renderer.sections}
        if args.manifest:
            args.manifest.parent.mkdir(parents=True, exist_ok=True)
            args.manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"导出失败：{exc}\n")


if __name__ == "__main__":
    main()
