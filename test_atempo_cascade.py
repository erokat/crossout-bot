# -*- coding: utf-8 -*-
"""
test_atempo_cascade.py - Unit tests for ffmpeg atempo filter cascade
and ffprobe audio stream detection in video_editor.py.
"""

import os
import unittest
from unittest.mock import patch, MagicMock

import video_editor


class TestAtempoCascade(unittest.TestCase):
    def _eval_atempo_chain_product(self, chain_str):
        factors = []
        for part in chain_str.split(","):
            part = part.strip()
            self.assertTrue(part.startswith("atempo="))
            val = float(part.split("=")[1])
            self.assertGreaterEqual(val, 0.4999, f"Filter component {val} < 0.5")
            self.assertLessEqual(val, 2.0001, f"Filter component {val} > 2.0")
            factors.append(val)
        prod = 1.0
        for f in factors:
            prod *= f
        return prod

    def test_build_atempo_filter_normal(self):
        f = video_editor.build_atempo_filter(1.5)
        self.assertEqual(f, "atempo=1.5000")
        prod = self._eval_atempo_chain_product(f)
        self.assertAlmostEqual(prod, 1.5, places=3)

    def test_build_atempo_filter_slow_0_25(self):
        f = video_editor.build_atempo_filter(0.25)
        prod = self._eval_atempo_chain_product(f)
        self.assertAlmostEqual(prod, 0.25, places=3)
        self.assertIn("atempo=0.5", f)

    def test_build_atempo_filter_fast_3_0(self):
        f = video_editor.build_atempo_filter(3.0)
        prod = self._eval_atempo_chain_product(f)
        self.assertAlmostEqual(prod, 3.0, places=3)
        self.assertIn("atempo=2.0", f)

    def test_build_atempo_filter_extreme_speeds(self):
        # 4.0x speed
        f4 = video_editor.build_atempo_filter(4.0)
        self.assertAlmostEqual(self._eval_atempo_chain_product(f4), 4.0, places=3)

        # 0.125x (1/8th) speed
        f_eighth = video_editor.build_atempo_filter(0.125)
        self.assertAlmostEqual(self._eval_atempo_chain_product(f_eighth), 0.125, places=3)

    def test_build_atempo_filter_invalid_speed(self):
        f = video_editor.build_atempo_filter(0)
        self.assertEqual(f, "atempo=1.0")

        f_neg = video_editor.build_atempo_filter(-2.0)
        self.assertEqual(f_neg, "atempo=1.0")

    @patch("subprocess.run")
    def test_has_audio_stream(self, mock_run):
        # Audio stream present
        mock_run.return_value = MagicMock(returncode=0, stdout="audio\n")
        self.assertTrue(video_editor.has_audio_stream("test.mp4"))

        # Audio stream absent
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        self.assertFalse(video_editor.has_audio_stream("test.mp4"))

    @patch("video_editor.has_audio_stream")
    @patch("os.path.exists")
    @patch("os.path.getsize")
    @patch("subprocess.run")
    def test_change_video_speed_branches(self, mock_run, mock_getsize, mock_exists, mock_has_audio):
        mock_exists.return_value = True
        mock_getsize.return_value = 10000
        mock_run.return_value = MagicMock(returncode=0)

        # With audio stream: uses [0:a]atempo filter
        mock_has_audio.return_value = True
        res = video_editor.change_video_speed("input.mp4", speed=3.0)
        self.assertIsNotNone(res)
        called_cmd = mock_run.call_args[0][0]
        self.assertIn("-filter_complex", called_cmd)
        complex_idx = called_cmd.index("-filter_complex") + 1
        self.assertIn("atempo=2.0", called_cmd[complex_idx])

        # Without audio stream: uses -an
        mock_has_audio.return_value = False
        res = video_editor.change_video_speed("input.mp4", speed=0.25)
        self.assertIsNotNone(res)
        called_cmd = mock_run.call_args[0][0]
        self.assertIn("-an", called_cmd)


if __name__ == "__main__":
    unittest.main()
