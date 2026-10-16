# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock
import io
import json

from skills.web_search_skill import clean_query, search_wikipedia, search_duckduckgo, web_search
from dynamic_agent import calculate_skill_match_score, is_autonomous_task, execute_autonomous_task

class TestWebSearchSkill(unittest.TestCase):
    def test_clean_query(self):
        self.assertEqual(clean_query("!бот найди в интернете последние новости"), "последние новости")
        self.assertEqual(clean_query("погугли квантовый компьютер"), "квантовый компьютер")
        self.assertEqual(clean_query("что известно о Марсе"), "Марсе")
        self.assertEqual(clean_query("«SpaceX» в интернете"), "SpaceX")

    @patch("urllib.request.urlopen")
    def test_search_wikipedia_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "title": "Квантовый компьютер",
            "extract": "Квантовый компьютер — вычислительное устройство на основе квантовой механики.",
            "content_urls": {"desktop": {"page": "https://ru.wikipedia.org/wiki/Квантовый_компьютер"}}
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = search_wikipedia("Квантовый компьютер")
        self.assertIsNotNone(res)
        self.assertEqual(res["title"], "Квантовый компьютер")
        self.assertIn("квантовой механики", res["extract"])

    @patch("urllib.request.urlopen")
    def test_search_duckduckgo_success(self, mock_urlopen):
        sample_html = """
        <table>
        <tr>
            <td valign="top">
                <a rel="nofollow" href="https://example.com/test" class="result-link">Тестовая статья о науке</a>
            </td>
        </tr>
        <tr>
            <td class='result-snippet'>Это краткое описание статьи о передовых открытиях науки.</td>
        </tr>
        </table>
        """
        mock_resp = MagicMock()
        mock_resp.read.return_value = sample_html.encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        results = search_duckduckgo("наука")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Тестовая статья о науке")
        self.assertEqual(results[0]["url"], "https://example.com/test")
        self.assertIn("краткое описание", results[0]["snippet"])

    @patch("skills.web_search_skill.search_wikipedia")
    @patch("skills.web_search_skill.search_duckduckgo")
    def test_web_search_formatting(self, mock_ddg, mock_wiki):
        mock_wiki.return_value = {
            "title": "Теория струн",
            "extract": "Направление физики, изучающее одномерные протяжённые объекты.",
            "url": "https://ru.wikipedia.org/wiki/Теория_струн"
        }
        mock_ddg.return_value = [
            {"title": "Что такое теория струн", "url": "https://example.com/string", "snippet": "Подробный разбор концепции для начинающих."}
        ]

        text = web_search("что такое теория струн")
        self.assertIn("Теория струн", text)
        self.assertIn("https://example.com/string", text)
        self.assertIn("Направление физики", text)

    def test_skill_triggers_and_autonomous_classification(self):
        triggers = ["найди в интернете", "поиск в интернете", "погугли", "найди в сети", "что известно о", "в интернете"]
        score_search = calculate_skill_match_score("погугли последние открытия", "web_search_skill", triggers)
        self.assertGreaterEqual(score_search, 6)

        query = "Бот, создай себе скилл, чтобы ты мог правильно искать информацию в интернете"
        self.assertTrue(is_autonomous_task(query))

        res, media = execute_autonomous_task(query, sender_name="Миша")
        self.assertIn("web_search_skill.py", res)
        self.assertIn("уже успешно создан и зарегистрирован", res)
        self.assertIn("📌", res)
        self.assertNotIn("_{desc}_", res)
        self.assertIsNone(media)

    def test_prepare_telethon_text(self):
        from send import prepare_telethon_text
        from telethon.extensions import markdown

        raw_text = "⚡ **Навык создан и активен:** `web_search_skill.py`\n_Умный поиск информации, новостей, фактов и ответов на вопросы в интернете_"
        prepared = prepare_telethon_text(raw_text)
        self.assertIn("__Умный поиск информации", prepared)

        parsed_msg, entities = markdown.parse(prepared)
        self.assertNotIn("_Умный поиск", parsed_msg)
        self.assertNotIn("интернете_", parsed_msg)
        self.assertTrue(any(e.__class__.__name__ == "MessageEntityItalic" for e in entities))

    def test_image_search_not_hijacking_info(self):
        from media_finder import extract_image_search_and_caption
        is_img, query, cap = extract_image_search_and_caption("бот найди в интернете информацию о горбатых калоедах(о Ярике)")
        self.assertFalse(is_img)

        is_img2, query2, cap2 = extract_image_search_and_caption("бот найди в интернете фото горбатых калоедов")
        self.assertTrue(is_img2)
        self.assertIn("горбатых калоедов", query2)

if __name__ == "__main__":
    unittest.main()
