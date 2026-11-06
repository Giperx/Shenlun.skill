"""Behavior checks for text layout and standalone source/tool distribution."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, ImageChops

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("shenlun_export_image", REPO / "skills/shared/scripts/export_image.py")
image_export = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = image_export
spec.loader.exec_module(image_export)


class ImageAndBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.regular, cls.bold = image_export.find_fonts()
        except ValueError as exc:
            raise unittest.SkipTest(str(exc))

    def test_wrapping_preserves_text_punctuation_and_numbers(self):
        renderer = image_export.Renderer(900, 38, self.regular, self.bold)
        spans = image_export.inline("**坚定信念**，在困难中前行。正文共306字，commit记录可追溯。")
        lines = renderer.wrap(spans, 280, 38)
        text = "".join(token for line in lines for token, _, _ in line)
        self.assertEqual(text, "坚定信念，在困难中前行。正文共306字，commit记录可追溯。")
        self.assertTrue(any(token == "306" for line in lines for token, _, _ in line))
        for line in lines[1:]:
            self.assertNotIn(line[0][0], "，。、；：？！）》】〉」』”’")
        for line in lines[:-1]:
            self.assertNotIn(line[-1][0], "（《【〈「『“‘")

    def test_wide_table_and_long_url_fit_canvas(self):
        renderer = image_export.Renderer(1200, 38, self.regular, self.bold)
        renderer.markdown("| 方法 | 材料 | 论证任务 |\n|---|---|---|\n| 否定之否定 | 博爱馆 | 保留有效能力，修正失当表达 |")
        renderer.paragraph("https://example.com/" + "a" * 180)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "table.png"
            renderer.save(output)
            with Image.open(output) as image:
                red, green, blue = image.split()
                self.assertIsNone(ImageChops.difference(red, green).getbbox())
                self.assertIsNone(ImageChops.difference(red, blue).getbbox())

    def test_missing_prompt_does_not_write_output(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            answer = folder / "answer.md"
            answer.write_text("完整正文", encoding="utf-8")
            output = folder / "answer.png"
            result = subprocess.run([sys.executable, str(REPO / "_tools/export_image.py"), str(answer), str(output),
                                     "--prompt", str(folder / "missing.md")], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())

    def test_standalone_install_contains_sources_and_working_exporter(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            destination = folder / "installed"
            subprocess.run([sys.executable, str(REPO / "_tools/install_skills.py"), "--dest", str(destination)],
                           check=True, capture_output=True)
            for number in (7, 8, 9):
                name = f"PDF-{number}.txt"
                original = REPO / "_sources/饮冰说申论/讲义提取" / name
                installed = destination / "shenlun-dawenti/references/yinbing-source-text" / name
                self.assertEqual(original.read_bytes(), installed.read_bytes())
            answer, prompt, output = folder / "answer.md", folder / "prompt.md", folder / "answer.png"
            answer.write_text("**坚定信念。**务实前行。", encoding="utf-8")
            prompt.write_text("原考试题目：理解两句话，写一篇文章。", encoding="utf-8")
            script = destination / "shared/scripts/export_image.py"
            result = subprocess.run([sys.executable, str(script), str(answer), str(output), "--prompt", str(prompt)],
                                    cwd=folder, check=True, capture_output=True, text=True)
            self.assertIn('"prompt_included": true', result.stdout)
            self.assertTrue(output.is_file())
            self.assertFalse((destination / "shenlun-dawenti").is_symlink())


if __name__ == "__main__":
    unittest.main()
