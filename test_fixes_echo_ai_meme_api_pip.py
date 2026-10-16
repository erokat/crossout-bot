# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import tempfile
import urllib.error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from db import clean_requirement_name, parse_skill_metadata_from_code, restore_dynamic_skills, set_kv
from send import send_via_bot_api
from ask_owner import send_bot_message
from keep_alive import handle_yarik_message, get_bot_sent_ids
from meme_generator import generate_dynamic_meme_via_ai, generate_crossout_meme, render_dynamic_pillow_meme


class TestEchoLoopPrevention(unittest.TestCase):
    @patch("keep_alive.spawn_meme_creator_subagent")
    @patch("keep_alive.ask_ai")
    @patch("keep_alive.subprocess.run")
    def test_handle_yarik_message_ignores_bot_sent_ids(self, mock_subproc, mock_ask, mock_spawn):
        with patch("keep_alive.get_bot_sent_ids", return_value={77702}):
            msg = {
                "id": 77702,
                "sender_id": 6271387044,
                "text": "!бот сделай мем",
                "out": False
            }
            handle_yarik_message(msg)
            mock_spawn.assert_not_called()
            mock_ask.assert_not_called()
            mock_subproc.assert_not_called()

    @patch("keep_alive.spawn_meme_creator_subagent")
    @patch("keep_alive.ask_ai")
    @patch("keep_alive.subprocess.run")
    def test_handle_yarik_message_ignores_bot_sent_outgoing(self, mock_subproc, mock_ask, mock_spawn):
        with patch("keep_alive.get_bot_sent_ids", return_value={77701}):
            msg = {
                "id": 77701,
                "sender_id": 5067025016,
                "text": "Ярик, лови мем!",
                "out": True
            }
            handle_yarik_message(msg)
            mock_spawn.assert_not_called()
            mock_ask.assert_not_called()
            mock_subproc.assert_not_called()

    @patch("keep_alive.spawn_meme_creator_subagent")
    @patch("keep_alive.ask_ai")
    @patch("keep_alive.subprocess.run")
    def test_handle_yarik_message_processes_owner_outgoing_command(self, mock_subproc, mock_ask, mock_spawn):
        with patch("keep_alive.get_bot_sent_ids", return_value=set()):
            msg = {
                "id": 77704,
                "sender_id": 5067025016,
                "text": "!бот сделай 2 мема",
                "out": True
            }
            handle_yarik_message(msg)
            self.assertEqual(mock_spawn.call_count, 2)
            mock_subproc.assert_not_called()


class TestPipInvalidRequirementsFix(unittest.TestCase):
    def test_clean_requirement_name_filters_stdlib(self):
        self.assertIsNone(clean_requirement_name("os"))
        self.assertIsNone(clean_requirement_name("import os"))
        self.assertIsNone(clean_requirement_name("from sys import argv"))
        self.assertIsNone(clean_requirement_name("sys"))
        self.assertIsNone(clean_requirement_name("math"))
        self.assertIsNone(clean_requirement_name("re"))
        self.assertIsNone(clean_requirement_name("time"))
        self.assertIsNone(clean_requirement_name("json"))
        self.assertIsNone(clean_requirement_name("random"))
        self.assertIsNone(clean_requirement_name("subprocess"))
        self.assertIsNone(clean_requirement_name("internal_module config"))

    def test_clean_requirement_name_allows_valid_external_packages(self):
        self.assertEqual(clean_requirement_name("requests"), "requests")
        self.assertEqual(clean_requirement_name("beautifulsoup4>=4.9.0"), "beautifulsoup4>=4.9.0")
        self.assertEqual(clean_requirement_name("pillow"), "pillow")
        self.assertEqual(clean_requirement_name("numpy"), "numpy")

    def test_parse_skill_metadata_from_code_strips_invalid_requirements(self):
        code = (
            '# SKILL_NAME: test_calc\n'
            '# DESCRIPTION: Calculator\n'
            '# TRIGGERS: calc\n'
            '# REQUIREMENTS: import os, sys, requests, math, pillow\n'
            'print("calc")\n'
        )
        s_name, s_desc, s_trig, s_req = parse_skill_metadata_from_code(code)
        self.assertEqual(s_name, "test_calc")
        self.assertIn("requests", s_req)
        self.assertIn("pillow", s_req)
        self.assertNotIn("import os", s_req)
        self.assertNotIn("os", s_req)
        self.assertNotIn("sys", s_req)
        self.assertNotIn("math", s_req)


class TestBotApiErrorHandling(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_caption_truncated_to_1024(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ok": true, "result": {"message_id": 111}}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        # Create a temp test photo
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tf.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
            tf_path = tf.name

        try:
            long_text = "A" * 2000
            res = send_via_bot_api("dummy_token", 123456, text=long_text, file_path=tf_path)
            self.assertIsNotNone(res)
            self.assertTrue(res.get("ok"))
            call_req = mock_urlopen.call_args[0][0]
            body_bytes = call_req.data
            # Verify body does not contain 2000 'A's
            self.assertNotIn(b"A" * 1500, body_bytes)
            self.assertIn(b"...", body_bytes)
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    @patch("urllib.request.urlopen")
    def test_retry_without_reply_to_on_http_400(self, mock_urlopen):
        # First call raises HTTPError 400 (e.g. replied message not found)
        # Second call succeeds
        err_fp = MagicMock()
        err_fp.read.return_value = b'{"ok": false, "description": "Bad Request: replied message not found"}'
        http_err = urllib.error.HTTPError("https://api.telegram.org", 400, "Bad Request", {}, err_fp)

        success_resp = MagicMock()
        success_resp.read.return_value = b'{"ok": true, "result": {"message_id": 222}}'
        success_resp.__enter__.return_value = success_resp

        mock_urlopen.side_effect = [http_err, success_resp]

        res = send_via_bot_api("dummy_token", 123456, text="Hello", reply_to=99999)
        self.assertIsNotNone(res)
        self.assertTrue(res.get("ok"))
        self.assertEqual(mock_urlopen.call_count, 2)


class TestDynamicMemeCreationViaAI(unittest.TestCase):
    @patch("dynamic_agent.generate_code_via_antigravity")
    def test_generate_dynamic_meme_via_ai_executes_generated_code(self, mock_agy):
        # Mock AI code generator to return a working Pillow script
        mock_script = (
            "```python\n"
            "import os, sys\n"
            "from PIL import Image\n"
            "media_dir = os.path.abspath('media')\n"
            "os.makedirs(media_dir, exist_ok=True)\n"
            "out_path = os.path.join(media_dir, 'test_unit_dynamic_ai_meme.png')\n"
            "img = Image.new('RGB', (800, 800), (25, 30, 45))\n"
            "img.save(out_path)\n"
            "print(out_path)\n"
            "```"
        )
        mock_agy.return_value = mock_script

        out_path = generate_dynamic_meme_via_ai("Бот, сгенерируй кринжанутый мем из кроссаута")
        self.assertIsNotNone(out_path)
        self.assertTrue(os.path.exists(out_path))
        self.assertGreater(os.path.getsize(out_path), 500)
        mock_agy.assert_called_once()
        prompt_called = mock_agy.call_args[0][0]
        self.assertIn("Crossout", prompt_called)

        # Cleanup
        if os.path.exists(out_path):
            os.remove(out_path)

    def test_render_dynamic_pillow_meme_fallback_creates_valid_image(self):
        out_path = render_dynamic_pillow_meme("тест юмора про программирование", is_crossout=False)
        self.assertIsNotNone(out_path)
        self.assertTrue(os.path.exists(out_path))
        self.assertGreater(os.path.getsize(out_path), 1000)

    def test_sanitize_meme_code_russian_replaces_english_cliches(self):
        from meme_generator import sanitize_meme_code_russian
        code = (
            'draw.text((10, 10), "Me: mom can we have pizza at home?", font=f)\n'
            'draw.text((10, 50), "Mom: no, we have pizza at home", font=f)\n'
            'draw.text((10, 90), "Nobody: absolutely no one:", font=f)\n'
        )
        cleaned = sanitize_meme_code_russian(code)
        self.assertNotIn("Me:", cleaned)
        self.assertNotIn("Mom:", cleaned)
        self.assertNotIn("Nobody:", cleaned)
        self.assertIn("Я:", cleaned)
        self.assertIn("Мама:", cleaned)
        self.assertIn("Никто:", cleaned)

    @patch("dynamic_agent.generate_code_via_antigravity")
    def test_generate_dynamic_meme_via_ai_prompt_enforces_100_percent_russian(self, mock_agy):
        mock_agy.return_value = (
            "```python\n"
            "import os, sys\n"
            "from PIL import Image\n"
            "media_dir = os.path.abspath('media')\n"
            "out_path = os.path.join(media_dir, 'test_ru_ai_meme.png')\n"
            "img = Image.new('RGB', (800, 800), (25, 30, 45))\n"
            "img.save(out_path)\n"
            "print(out_path)\n"
            "```"
        )
        out = generate_dynamic_meme_via_ai("мем про кота")
        self.assertIsNotNone(out)
        prompt_called = mock_agy.call_args[0][0]
        self.assertIn("СТРОЖАЙШЕ 100% РУССКИЙ ЯЗЫК", prompt_called)
        self.assertIn("КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать что-либо на английском языке", prompt_called)
        if os.path.exists(out):
            os.remove(out)

    def test_ensure_russian_text_in_meme_engine(self):
        from meme_engine import ensure_russian_text
        text = "Me: please buy game. Mom: no, we have games at home"
        res = ensure_russian_text(text)
        self.assertNotIn("Me:", res)
        self.assertNotIn("Mom:", res)
        self.assertIn("Я:", res)
        self.assertIn("Мама:", res)


if __name__ == "__main__":
    unittest.main()

