# -*- coding: utf-8 -*-
"""
test_photo_ai_routing_and_cleanup.py - Tests for dynamic AI photo generation, photo editing,
and automatic script deletion after execution.
"""

import os
import sys
import unittest
import tempfile
from unittest.mock import patch, MagicMock

import dynamic_agent
import keep_alive


class TestPhotoAIRoutingAndCleanup(unittest.TestCase):
    def test_is_one_off_creative_task(self):
        # Photo generation queries
        self.assertTrue(dynamic_agent.is_one_off_creative_task("сгенерируй фото каблука на коробке"))
        self.assertTrue(dynamic_agent.is_one_off_creative_task("сгенерируй картинку туфли"))
        self.assertTrue(dynamic_agent.is_one_off_creative_task("нарисуй красивый закат"))
        self.assertTrue(dynamic_agent.is_one_off_creative_task("создай арт кота в киберпанке"))

        # Photo editing queries
        self.assertTrue(dynamic_agent.is_one_off_creative_task("обработай фото"))
        self.assertTrue(dynamic_agent.is_one_off_creative_task("добавь надпись верити на фото"))
        self.assertTrue(dynamic_agent.is_one_off_creative_task("размой задний фон"))
        self.assertTrue(dynamic_agent.is_one_off_creative_task("сделай фотомонтаж"))

        # Non-creative persistent skill request should NOT be one-off
        self.assertFalse(dynamic_agent.is_one_off_creative_task("добавь команду погоды для Тирасполя"))
        self.assertFalse(dynamic_agent.is_one_off_creative_task("создай модуль парсера курсов валют"))

    def test_execute_autonomous_task_deletes_one_off_script(self):
        # Mock ask_ai_fn to return a valid Python script that generates an image in media/
        mock_py_code = (
            "```python\n"
            "# SKILL_NAME: photo_heel_box\n"
            "# DESCRIPTION: Генерация каблука на коробке\n"
            "# TRIGGERS: каблук на коробке\n"
            "# REQUIREMENTS: pillow\n"
            "import os\n"
            "from PIL import Image\n"
            "out = os.path.join('media', 'test_heel_box_out.jpg')\n"
            "img = Image.new('RGB', (100, 100), color=(255, 0, 0))\n"
            "img.save(out)\n"
            "print(out)\n"
            "```"
        )
        def mock_ai(prompt, **kwargs):
            return mock_py_code

        expected_script_path = os.path.join(dynamic_agent.SKILLS_DIR, "photo_heel_box.py")
        if os.path.exists(expected_script_path):
            os.remove(expected_script_path)

        msg, media = dynamic_agent.execute_autonomous_task(
            task_text="сгенерируй фото каблука на коробке",
            sender_name="Миша",
            ask_ai_fn=mock_ai
        )

        self.assertIsNotNone(media)
        self.assertTrue(os.path.exists(media))
        # Ensure the script file was deleted after execution!
        self.assertFalse(os.path.exists(expected_script_path))

        # Cleanup test media
        if media and os.path.exists(media):
            try:
                os.remove(media)
            except Exception:
                pass

    @patch("keep_alive.safe_run_autonomous_task_async")
    @patch("keep_alive.subprocess.run")
    def test_owner_photo_edit_routed_to_ai(self, mock_subproc, mock_safe_run):
        mock_subproc.return_value = MagicMock(returncode=0, stdout="Sent msg 1001")
        msg_data = {
            "source": "owner",
            "text": "добавь надпись верити на фото",
            "photo": "/tmp/test_input_photo.jpg"
        }
        with patch("os.path.exists", return_value=True):
            keep_alive.handle_owner_message(msg_data)

        # safe_run_autonomous_task_async should be invoked for photo editing
        mock_safe_run.assert_called_once()
        args, kwargs = mock_safe_run.call_args
        self.assertEqual(kwargs.get("task_text"), "добавь надпись верити на фото")
        self.assertEqual(kwargs.get("photo_path"), "/tmp/test_input_photo.jpg")

    @patch("keep_alive.safe_run_autonomous_task_async")
    @patch("keep_alive.subprocess.run")
    def test_owner_visual_gen_routed_to_ai(self, mock_subproc, mock_safe_run):
        mock_subproc.return_value = MagicMock(returncode=0, stdout="Sent msg 1002")
        msg_data = {
            "source": "owner",
            "text": "сгенерируй фото каблука на коробке",
            "photo": None
        }
        keep_alive.handle_owner_message(msg_data)

        # safe_run_autonomous_task_async should be invoked for visual photo generation
        mock_safe_run.assert_called_once()
        args, kwargs = mock_safe_run.call_args
        self.assertEqual(kwargs.get("task_text"), "сгенерируй фото каблука на коробке")


if __name__ == "__main__":
    unittest.main()
