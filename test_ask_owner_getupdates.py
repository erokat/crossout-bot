# -*- coding: utf-8 -*-
"""
test_ask_owner_getupdates.py - Unit tests for ask_owner.py SQLite-based confirmation resolution,
inline keyboard cleanup, and verification that getUpdates is NOT polled (preventing HTTP 409 Conflict).
"""

import os
import sys
import json
import io
import unittest
from unittest.mock import patch, MagicMock

import ask_owner


class TestAskOwnerGetUpdates(unittest.TestCase):
    def setUp(self):
        self.bot_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        self.owner_id = 5067025016

    def test_answer_callback(self):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            ask_owner.answer_callback(self.bot_token, "cb_123", "✅ Разрешено!")
            
            self.assertTrue(mock_urlopen.called)
            req = mock_urlopen.call_args[0][0]
            self.assertIn("answerCallbackQuery", req.full_url)
            body = json.loads(req.data.decode("utf-8"))
            self.assertEqual(body["callback_query_id"], "cb_123")
            self.assertEqual(body["text"], "✅ Разрешено!")

    def test_remove_inline_keyboard(self):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({"ok": True}).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            
            res = ask_owner.remove_inline_keyboard(self.bot_token, self.owner_id, 456)
            self.assertTrue(res)
            
            req = mock_urlopen.call_args[0][0]
            self.assertIn("editMessageReplyMarkup", req.full_url)
            body = json.loads(req.data.decode("utf-8"))
            self.assertEqual(body["chat_id"], self.owner_id)
            self.assertEqual(body["message_id"], 456)
            self.assertEqual(body["reply_markup"], {"inline_keyboard": []})

    @patch("ask_owner.load_config")
    @patch("ask_owner.init_db")
    @patch("ask_owner.create_confirmation")
    @patch("ask_owner.get_confirmation")
    @patch("urllib.request.urlopen")
    def test_main_sqlite_approval(
        self, mock_urlopen, mock_get_conf, mock_create_conf,
        mock_init_db, mock_load_config
    ):
        mock_load_config.return_value = {
            "bot_token": self.bot_token,
            "owner_id": self.owner_id,
            "render_url": "https://test.onrender.com"
        }
        # Simulate SQLite returning approved status
        mock_get_conf.return_value = {
            "status": "approved",
            "comment": "Approved via Web/DB"
        }

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True, "result": {"message_id": 999}}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with patch.object(sys, "argv", ["ask_owner.py", "Ярик просит удалить сообщение: привет"]):
            with patch("sys.stdout", new=io.StringIO()) as fake_out:
                ask_owner.main()
                output = fake_out.getvalue()
                self.assertIn("APPROVED", output)

        mock_create_conf.assert_called_once()
        # Ensure getUpdates is NEVER called, preventing HTTP 409 Conflict
        for call in mock_urlopen.call_args_list:
            req = call[0][0]
            url = req.full_url if hasattr(req, "full_url") else str(req)
            self.assertNotIn("getUpdates", url)

    @patch("ask_owner.load_config")
    @patch("ask_owner.init_db")
    @patch("ask_owner.create_confirmation")
    @patch("ask_owner.get_confirmation")
    @patch("urllib.request.urlopen")
    def test_main_sqlite_rejection(
        self, mock_urlopen, mock_get_conf, mock_create_conf,
        mock_init_db, mock_load_config
    ):
        mock_load_config.return_value = {
            "bot_token": self.bot_token,
            "owner_id": self.owner_id,
            "render_url": "https://test.onrender.com"
        }
        # Simulate SQLite returning rejected status
        mock_get_conf.return_value = {
            "status": "rejected",
            "comment": "Rejected via Web/DB"
        }

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True, "result": {"message_id": 888}}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with patch.object(sys, "argv", ["ask_owner.py", "Сгенерировать видео?"]):
            with patch("sys.stdout", new=io.StringIO()) as fake_out:
                ask_owner.main()
                output = fake_out.getvalue()
                self.assertIn("REJECTED", output)

        mock_create_conf.assert_called_once()
        # Ensure getUpdates is NEVER called, preventing HTTP 409 Conflict
        for call in mock_urlopen.call_args_list:
            req = call[0][0]
            url = req.full_url if hasattr(req, "full_url") else str(req)
            self.assertNotIn("getUpdates", url)


if __name__ == "__main__":
    unittest.main()
