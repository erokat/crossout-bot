# -*- coding: utf-8 -*-
import unittest
import os
import shutil
from PIL import Image

from photo_editor import is_photo_editor_request, process_universal_photo_command
from dynamic_agent import is_visual_art_request

class TestPhotoEditorFixes(unittest.TestCase):
    def test_photo_editor_request_detection(self):
        # Replying to photo with editing instruction
        self.assertTrue(is_photo_editor_request("Бот прифотошопь к слону картинку птура", has_photo=True))
        self.assertTrue(is_photo_editor_request("прилепи птур", has_photo=True))
        self.assertTrue(is_photo_editor_request("добавь надпись мат", has_photo=True))
        self.assertFalse(is_photo_editor_request("Привет как дела", has_photo=False))

    def test_visual_art_request_detection(self):
        self.assertTrue(is_visual_art_request("Бот нарисуй слизнекота вотчера"))
        self.assertTrue(is_visual_art_request("Сгенерируй фото кота на окне"))
        self.assertTrue(is_visual_art_request("Создай арт по игре Rain World"))
        self.assertFalse(is_visual_art_request("Напиши код калькулятора"))
        self.assertFalse(is_visual_art_request("Бот сделай мем про птур"))

    def test_photo_editor_chess_piece_overlay(self):
        # Create a test target image
        test_img_path = "media/test_photo_target.png"
        img = Image.new("RGB", (1000, 1000), (200, 180, 150))
        img.save(test_img_path)

        edited_p, caption = process_universal_photo_command(test_img_path, "Бот прифотошопь картинку птура")
        self.assertTrue(os.path.exists(edited_p))
        self.assertGreater(os.path.getsize(edited_p), 5000)
        self.assertIn("птур", caption.lower())

        if os.path.exists(test_img_path):
            os.remove(test_img_path)
        if os.path.exists(edited_p):
            os.remove(edited_p)

if __name__ == "__main__":
    unittest.main()
