"""Check conservative footer removal and reproducible reference-book distribution."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("topic_sync", REPO / "_tools/sync_topic_sources.py")
topic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(topic)


class TopicSourcesTests(unittest.TestCase):
    def test_only_standalone_footer_is_removed(self):
        body = (
            "该素材已经申请版权保护, 书学姐独家整理且未与其他机构合作，\n"
            "市场独一无二，小伙伴们只可自己学习使用， 不可进行二次传阅售卖\n"
            "治理塑料污染。深化全面禁止“洋垃圾”入境工作。"
        )
        for footer in (
            "独家整理，禁止二次传闵，茜止商用，盗者必究。如有问题，欢迎小红书交流: 书学姐〈三次上涯)",
            "独罕整理，禁止二次传闵，禁止商用，盗者必完.如有问题，欢迎小红书交流， 书学姐 《三次上涯)",
            "独家整理，禁止二次传阅，禁止商用，次者必究。如有问题，欢迎小红闻交流， 书学姐 (三次上兰)",
        ):
            self.assertEqual(topic.clean_page(footer + "\n\n" + body), body)

    def test_incomplete_or_repeated_page_markers_are_rejected(self):
        for text in (
            "===== TOPIC-2027 PAGE 1 =====\n正文",
            "".join(f"===== TOPIC-2027 PAGE {min(p, 140)} =====\n正文\n" for p in range(1, 142)),
        ):
            with self.assertRaises(ValueError):
                topic.parse_pages(text)

    def test_rebuild_and_read_only_check(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            raw = repo / "_sources/参考书"
            raw.mkdir(parents=True)
            source = raw / "2027年高频考点话题-OCR.txt"
            source.write_text("".join(
                f"===== TOPIC-2027 PAGE {p} =====\n第{p}页正文\n" for p in range(1, 142)
            ), encoding="utf-8")
            bundle = repo / "skills/shenlun-dawenti/references/topic-library/source-text"
            bundle.mkdir(parents=True)
            volume = bundle / "volume.md"
            volume.write_text("# 保留来源头\n\n" + "\n".join(
                f'<a id="pdf-{p:03}"></a>\n\n## PDF物理第{p}页\n\n````text\n旧文本\n````\n'
                for p in range(1, 142)
            ), encoding="utf-8")
            before = volume.read_bytes()
            with self.assertRaises(ValueError):
                topic.sync(repo, check=True)
            self.assertEqual(volume.read_bytes(), before)
            self.assertFalse((raw / "ocr").exists())
            topic.sync(repo)
            topic.sync(repo, check=True)
            self.assertTrue(volume.read_text(encoding="utf-8").startswith("# 保留来源头\n"))
            for p in range(1, 142):
                self.assertEqual((raw / f"ocr/{p:03}.txt").read_text(encoding="utf-8"), f"第{p}页正文\n")


if __name__ == "__main__":
    unittest.main()
