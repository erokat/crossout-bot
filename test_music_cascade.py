# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import media_finder

class TestMusicCascade(unittest.TestCase):
    def test_generate_search_variations_with_author(self):
        query = "DELTARUNE - It's TV Time! от InstrumentManiac"
        clean_q = media_finder.clean_query(query, "music")
        vars = media_finder.generate_search_variations(clean_q)
        self.assertIn("DELTARUNE - It's TV Time! InstrumentManiac", vars)
        self.assertIn("DELTARUNE - It's TV Time!", vars)
        self.assertIn("InstrumentManiac DELTARUNE - It's TV Time!", vars)

    def test_generate_search_variations_with_dash(self):
        query = "Toby Fox - Megalovania"
        clean_q = media_finder.clean_query(query, "music")
        vars = media_finder.generate_search_variations(clean_q)
        self.assertIn("Toby Fox Megalovania", vars)

    @patch("media_finder.download_via_ytdlp")
    def test_find_and_download_music_soundcloud_tier1(self, mock_ytdlp):
        # Simulate SoundCloud succeeding on first variation
        mock_ytdlp.return_value = ("/fake/music/track.mp3", "Deltarune TV Time - Juno Songs")
        
        with patch("os.path.exists", return_value=False):
            track, title = media_finder.find_and_download_music("DELTARUNE - It's TV Time! от InstrumentManiac")
            self.assertEqual(track, "/fake/music/track.mp3")
            self.assertIn("Deltarune TV Time", title)
            mock_ytdlp.assert_called()
            # First call should be scsearch1
            first_call_prefix = mock_ytdlp.call_args_list[0][0][0]
            self.assertEqual(first_call_prefix, "scsearch1")

    @patch("media_finder.search_invidious_audio")
    @patch("media_finder.download_via_ytdlp")
    def test_find_and_download_music_invidious_tier2_fallback(self, mock_ytdlp, mock_invidious):
        # Simulate SoundCloud failing, Invidious succeeding
        mock_ytdlp.return_value = (None, "")
        mock_invidious.return_value = ("/fake/music/invidious.mp3", "Deltarune TV Time - Toby Fox")

        with patch("os.path.exists", return_value=False):
            track, title = media_finder.find_and_download_music("DELTARUNE - It's TV Time!")
            self.assertEqual(track, "/fake/music/invidious.mp3")
            self.assertEqual(title, "Deltarune TV Time - Toby Fox")
            mock_invidious.assert_called()

if __name__ == "__main__":
    unittest.main()
