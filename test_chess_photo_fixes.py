# -*- coding: utf-8 -*-
import unittest
import os
import shutil
from PIL import Image

from chess_engine import is_chess_request, parse_chess_request, process_chess_command, render_chess_board
from photo_editor import is_photo_editor_request, process_universal_photo_command

class TestChessPhotoFixes(unittest.TestCase):
    def test_chess_request_detection(self):
        # Without photo: should recognize chess context
        self.assertTrue(is_chess_request("Бот сгенерируй черной фигуре слон оружие птур из игры кроссаут", has_photo=False))
        self.assertTrue(is_chess_request("Бот поставь черного слона на H7", has_photo=False))
        self.assertTrue(is_chess_request("Бот чистая доска", has_photo=False))

        # With photo: photo editing commands must NOT be hijacked by chess engine
        self.assertFalse(is_chess_request("Бот прифотошопь к слону картинку птура", has_photo=True))
        self.assertFalse(is_chess_request("Бот наложи птур на картинку", has_photo=True))
        
        # With photo: clear board commands SHOULD be recognized by chess engine
        self.assertTrue(is_chess_request("Бот очисти доску и убери фигуры", has_photo=True))
        self.assertTrue(is_chess_request("убери фигуры", has_photo=True))

    def test_photo_editor_request_detection(self):
        # Replying to photo with editing instruction
        self.assertTrue(is_photo_editor_request("Бот прифотошопь к слону картинку птура", has_photo=True))
        self.assertTrue(is_photo_editor_request("прилепи птур", has_photo=True))
        self.assertTrue(is_photo_editor_request("добавь надпись мат", has_photo=True))

    def test_parse_chess_request_with_weapon(self):
        text = "Бот сгенерируй черной фигуре слон оружие птур из игры кроссаут"
        pieces, mode, highlights, arrow, attachments = parse_chess_request(text)
        
        self.assertEqual(mode, "weapon_sniper")
        self.assertIn("h7", pieces)
        self.assertEqual(pieces["h7"], "bB") # Black Bishop!
        self.assertIn("c2", pieces)
        self.assertEqual(pieces["c2"], "wQ") # White Queen!
        self.assertEqual(arrow, ("h7", "c2"))
        self.assertIsNotNone(attachments)
        self.assertEqual(attachments.get("h7"), "ptur")

    def test_process_chess_command_generation(self):
        text = "Бот сгенерируй черной фигуре слон оружие птур из игры кроссаут"
        img_path, caption = process_chess_command(text, sender_name="Ярик")
        self.assertTrue(os.path.exists(img_path))
        self.assertGreater(os.path.getsize(img_path), 5000)
        self.assertIn("слон", caption.lower())
        self.assertIn("птур", caption.lower())
        self.assertIn("h7", caption.lower())
        # Must NOT be an empty board caption!
        self.assertNotIn("чистую шахматную доску без фигур", caption)

    def test_photo_editor_chess_piece_overlay(self):
        # Create a test chessboard image
        test_img_path = "media/test_chess_target.png"
        img = Image.new("RGB", (1000, 1000), (200, 180, 150))
        img.save(test_img_path)

        edited_p, caption = process_universal_photo_command(test_img_path, "Бот прифотошопь к слону картинку птура")
        self.assertTrue(os.path.exists(edited_p))
        self.assertGreater(os.path.getsize(edited_p), 5000)
        self.assertIn("слону", caption.lower())
        self.assertIn("птур", caption.lower())

        if os.path.exists(test_img_path):
            os.remove(test_img_path)
        if os.path.exists(edited_p):
            os.remove(edited_p)

    def test_sniper_rifle_chess_placement(self):
        text = "Бот сгенерируй на шахматной доске на клетке B1 черного короля, на B3 белого короля, на C2 белого ферзя, на H7 черного слона и чтобы у одной фигуры была снайперка и чтобы там почти мат давала и выцеливала кого-то"
        pieces, mode, highlights, arrow, attachments = parse_chess_request(text)
        self.assertEqual(pieces.get("b1"), "bK")
        self.assertEqual(pieces.get("b3"), "wK")
        self.assertEqual(pieces.get("c2"), "wQ")
        self.assertEqual(pieces.get("h7"), "bB")
        self.assertEqual(arrow, ("h7", "c2"))
        self.assertIsNotNone(attachments)
        self.assertEqual(attachments.get("h7"), "sniper_rifle")

        img_path, caption = process_chess_command(text, sender_name="Миша")
        self.assertTrue(os.path.exists(img_path))
        self.assertIn("снайперск", caption.lower())
        self.assertIn("h7", caption.lower())
        self.assertIn("c2", caption.lower())

if __name__ == "__main__":
    unittest.main()
