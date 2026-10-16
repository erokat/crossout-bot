# -*- coding: utf-8 -*-
"""
test_ask_owner_getupdates.py - Unit tests for ask_owner.py getUpdates polling,
inline callbacks, removing keyboards, and offset progression.
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
    @patch("ask_owner.resolve_confirmation")
    @patch("ask_owner.get_confirmation")
    @patch("ask_owner.get_kv")
    @patch("ask_owner.set_kv")
    @patch("urllib.request.urlopen")
    def test_main_inline_approval(
        self, mock_urlopen, mock_set_kv, mock_get_kv,
        mock_get_conf, mock_resolve_conf, mock_create_conf,
        mock_init_db, mock_load_config
    ):
        mock_load_config.return_value = {
            "bot_token": self.bot_token,
            "owner_id": self.owner_id,
            "render_url": "https://test.onrender.com"
        }
        mock_get_conf.return_value = None
        mock_get_kv.return_value = "100"

        def make_mock_resp(data_dict):
            m = MagicMock()
            m.read.return_value = json.dumps(data_dict).encode("utf-8")
            m.__enter__.return_value = m
            m.__exit__.return_value = False
            return m

        saved_req_id = []
        def side_create_conf(req_id, *args, **kwargs):
            saved_req_id.append(req_id)
        mock_create_conf.side_effect = side_create_conf

        def smart_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "sendMessage" in url:
                return make_mock_resp({"ok": True, "result": {"message_id": 999}})
            elif "getUpdates" in url and "offset=100" in url:
                rid = saved_req_id[0] if saved_req_id else "unknown"
                return make_mock_resp({
                    "ok": True,
                    "result": [{
                        "update_id": 105,
                        "callback_query": {
                            "id": "cq_abc",
                            "from": {"id": self.owner_id},
                            "data": f"approve_{rid}"
                        }
                    }]
                })
            else:
                return make_mock_resp({"ok": True})

        mock_urlopen.side_effect = smart_urlopen

        with patch.object(sys, "argv", ["ask_owner.py", "Ярик просит удалить сообщение: привет"]):
            with patch("sys.stdout", new=io.StringIO()) as fake_out:
                ask_owner.main()
                output = fake_out.getvalue()
                self.assertIn("APPROVED", output)

        mock_resolve_conf.assert_called_once()
        self.assertEqual(mock_resolve_conf.call_args[0][1], "approved")
        mock_set_kv.assert_called_with("control_bot_offset", "106")

    @patch("ask_owner.load_config")
    @patch("ask_owner.init_db")
    @patch("ask_owner.create_confirmation")
    @patch("ask_owner.resolve_confirmation")
    @patch("ask_owner.get_confirmation")
    @patch("ask_owner.get_kv")
    @patch("ask_owner.set_kv")
    @patch("urllib.request.urlopen")
    def test_main_text_rejection(
        self, mock_urlopen, mock_set_kv, mock_get_kv,
        mock_get_conf, mock_resolve_conf, mock_create_conf,
        mock_init_db, mock_load_config
    ):
        mock_load_config.return_value = {
            "bot_token": self.bot_token,
            "owner_id": self.owner_id,
            "render_url": "https://test.onrender.com"
        }
        mock_get_conf.return_value = None
        mock_get_kv.return_value = "200"

        def make_mock_resp(data_dict):
            m = MagicMock()
            m.read.return_value = json.dumps(data_dict).encode("utf-8")
            m.__enter__.return_value = m
            m.__exit__.return_value = False
            return m

        def smart_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "sendMessage" in url:
                return make_mock_resp({"ok": True, "result": {"message_id": 888}})
            elif "getUpdates" in url and "offset=200" in url:
                return make_mock_resp({
                    "ok": True,
                    "result": [{
                        "update_id": 209,
                        "message": {
                            "message_id": 1122,
                            "from": {"id": self.owner_id},
                            "text": "нет, не разрешаю"
                        }
                    }]
                })
            else:
                return make_mock_resp({"ok": True})

        mock_urlopen.side_effect = smart_urlopen

        with patch.object(sys, "argv", ["ask_owner.py", "Сгенерировать видео?"]):
            with patch("sys.stdout", new=io.StringIO()) as fake_out:
                ask_owner.main()
                output = fake_out.getvalue()
                self.assertIn("REJECTED", output)

        mock_resolve_conf.assert_called_once()
        self.assertEqual(mock_resolve_conf.call_args[0][1], "rejected")
        mock_set_kv.assert_called_with("control_bot_offset", "210")


if __name__ == "__main__":
    unittest.main()
