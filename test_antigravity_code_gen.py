# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import dynamic_agent
import keep_alive


class TestAntigravityCodeGen(unittest.TestCase):
    def tearDown(self):
        skill_file = os.path.join(BASE_DIR, "skills", "test_agy_skill.py")
        if os.path.exists(skill_file):
            try:
                os.remove(skill_file)
            except Exception:
                pass

    def test_generate_code_via_antigravity_invokes_cli_with_flash_medium(self):
        with patch("subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = "```python\nprint('hello from flash medium')\n```"
            mock_proc.stderr = ""
            mock_run.return_value = mock_proc

            res = dynamic_agent.generate_code_via_antigravity("Напиши код")
            self.assertIsNotNone(res)
            self.assertIn("hello from flash medium", res)

            mock_run.assert_called_once()
            cmd_called = mock_run.call_args[0][0]
            self.assertIn("--model", cmd_called)
            model_idx = cmd_called.index("--model")
            self.assertEqual(cmd_called[model_idx + 1], "gemini-3.8-flash-medium")
            self.assertIn("--dangerously-skip-permissions", cmd_called)
            self.assertIn("--disable-slash-commands", cmd_called)

            env_called = mock_run.call_args[1].get("env", {})
            self.assertEqual(env_called.get("GOMEMLIMIT"), "350MiB")
            self.assertEqual(env_called.get("GOGC"), "100")

    def test_keep_alive_run_antigravity_cli_uses_flash_medium(self):
        with patch("subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = "def foo(): return 42"
            mock_proc.stderr = ""
            mock_run.return_value = mock_proc

            res = keep_alive.run_antigravity_cli("Generate python code", timeout=90)
            self.assertEqual(res, "def foo(): return 42")

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            self.assertIn("--model", cmd)
            idx = cmd.index("--model")
            self.assertEqual(cmd[idx + 1], "gemini-3.8-flash-medium")

    def test_ask_ai_routes_code_directly_to_antigravity_cli(self):
        with patch("keep_alive.run_antigravity_cli") as mock_cli:
            mock_cli.return_value = "```python\nprint('code generated')\n```"

            code_prompt = "Напиши python скрипт для расчета факториала"
            result = keep_alive.ask_ai(code_prompt)

            self.assertEqual(result, "```python\nprint('code generated')\n```")
            mock_cli.assert_called_once()
            # Verify code prompt is passed directly without prepending the conversational Crossout/Yarik rule
            called_prompt = mock_cli.call_args[0][0]
            self.assertIn(code_prompt, called_prompt)
            self.assertNotIn("[СИСТЕМНОЕ ПРАВИЛО: Ты — верный, живой, остроумный бро", called_prompt)

    def test_execute_autonomous_task_uses_antigravity_code_gen(self):
        with patch("dynamic_agent.generate_code_via_antigravity") as mock_gen, \
             patch("dynamic_agent.run_script") as mock_run_script, \
             patch("db.save_dynamic_skill") as mock_db, \
             patch("github_sync.push_skill_to_github") as mock_gh:

            mock_gen.return_value = (
                "```python\n"
                "# SKILL_NAME: test_agy_skill\n"
                "# DESCRIPTION: Test agy skill\n"
                "# TRIGGERS: тест_аги\n"
                "print('Result from gemini-3.8-flash-medium')\n"
                "```"
            )
            mock_run_script.return_value = (0, "Result from gemini-3.8-flash-medium", "")

            reply, media = dynamic_agent.execute_autonomous_task(
                "создай модуль для тестирования agy генератора",
                sender_name="Миша",
                ask_ai_fn=None
            )

            mock_gen.assert_called()
            self.assertEqual(reply, "Result from gemini-3.8-flash-medium")

    def test_is_visual_art_request_classification(self):
        self.assertTrue(dynamic_agent.is_visual_art_request("сгенерируй фото там где на коробку наступил каблук"))
        self.assertTrue(dynamic_agent.is_visual_art_request("нарисуй персонажа слизнекота вотчера"))
        self.assertTrue(dynamic_agent.is_visual_art_request("сделай арт rain world с дымовыми сферами"))
        self.assertFalse(dynamic_agent.is_visual_art_request("сделай мем с птуром и вереском"))
        self.assertFalse(dynamic_agent.is_visual_art_request("напиши код парсера погоды"))

    def test_generate_image_via_antigravity_invokes_cli(self):
        with patch("subprocess.run") as mock_run, \
             patch("os.path.exists", return_value=True), \
             patch("os.path.isfile", return_value=True), \
             patch("os.path.getsize", return_value=50000):
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = "Created art: /tmp/fake_art_123.jpg"
            mock_proc.stderr = ""
            mock_run.return_value = mock_proc

            img_path = dynamic_agent.generate_image_via_antigravity("Rain World Watcher slugcat art")
            self.assertEqual(img_path, "/tmp/fake_art_123.jpg")
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            self.assertIn("--model", cmd)
            self.assertIn("gemini-3.8-flash-medium", cmd)
            self.assertIn("--dangerously-skip-permissions", cmd)
            prompt_called = cmd[cmd.index("-p") + 1]
            self.assertIn("image-generator", prompt_called)

    def test_research_visual_context_invokes_cli(self):
        with patch("subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = "[LOCATION_DETAILS]: Coral Caves\n[CHARACTER_DETAILS]: Watcher slugcat"
            mock_proc.stderr = ""
            mock_run.return_value = mock_proc

            research = dynamic_agent.research_visual_context("Rain World Watcher slugcat art")
            self.assertIn("[LOCATION_DETAILS]", research)
            self.assertIn("[CHARACTER_DETAILS]", research)
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            self.assertIn("search_web", cmd[cmd.index("-p") + 1])


if __name__ == "__main__":
    unittest.main()

