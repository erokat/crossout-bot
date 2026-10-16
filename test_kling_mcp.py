# -*- coding: utf-8 -*-
"""
test_kling_mcp.py - Unit tests for Kling AI Remote MCP client and video generation integration.
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

import kling_client


class TestKlingMCP(unittest.TestCase):
    def test_mcp_rpc_call_no_token(self):
        with patch.dict(os.environ, {}, clear=True):
            res = kling_client.mcp_rpc_call("tools/list")
            self.assertIn("error", res)
            self.assertEqual(res["error"]["code"], -32000)

    @patch("urllib.request.urlopen")
    def test_call_kling_tool_success(self, mock_urlopen):
        with patch.dict(os.environ, {"KLING_API_KEY": "fake_kling_token_123"}):
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({
                "jsonrpc": "2.0",
                "id": "kling-1",
                "result": {"status": "ok", "task_id": "task_abc_999"}
            }).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.__exit__.return_value = False
            mock_urlopen.return_value = mock_resp

            ok, result = kling_client.call_kling_tool("kling_generate_video", {"prompt": "robot fight"})
            self.assertTrue(ok)
            self.assertEqual(result.get("task_id"), "task_abc_999")

            self.assertTrue(mock_urlopen.called)
            req = mock_urlopen.call_args[0][0]
            self.assertEqual(req.headers.get("Authorization"), "Bearer fake_kling_token_123")
            body = json.loads(req.data.decode("utf-8"))
            self.assertEqual(body["method"], "tools/call")
            self.assertEqual(body["params"]["name"], "kling_generate_video")
            self.assertEqual(body["params"]["arguments"]["prompt"], "robot fight")

    @patch("kling_client.call_kling_tool")
    def test_submit_text_to_video(self, mock_call):
        mock_call.return_value = (True, {"task_id": "test_video_task_555"})

        ok, task_id = kling_client.submit_text_to_video("A cinematic crossout race in desert")
        self.assertTrue(ok)
        self.assertEqual(task_id, "test_video_task_555")

        mock_call.assert_called_once()
        args = mock_call.call_args[0][1]
        self.assertEqual(args["prompt"], "A cinematic crossout race in desert")
        self.assertEqual(args["model"], "kling-v1")

    @patch("kling_client.call_kling_tool")
    def test_get_task_status(self, mock_call):
        # Case 1: succeed with video url
        mock_call.return_value = (True, {
            "data": {
                "status": "succeed",
                "progress": 100,
                "videos": [{"url": "https://cdn.kling.ai/generated_video.mp4"}]
            }
        })

        ok, status_data = kling_client.get_task_status("test_task_777")
        self.assertTrue(ok)
        self.assertEqual(status_data["status"], "succeed")
        self.assertEqual(status_data["progress"], 100)
        self.assertEqual(status_data["video_url"], "https://cdn.kling.ai/generated_video.mp4")

    @patch("subprocess.run")
    def test_request_owner_permission_for_kling(self, mock_subproc):
        # Approved case
        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"req_id": "r1", "verdict": "APPROVED", "comment": "ok"})
        )
        approved = kling_client.request_owner_permission_for_kling("Сгенерировать видео", requester_name="Ярик")
        self.assertTrue(approved)

        # Rejected case
        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"req_id": "r2", "verdict": "REJECTED", "comment": "no"})
        )
        rejected = kling_client.request_owner_permission_for_kling("Сгенерировать видео", requester_name="Ярик")
        self.assertFalse(rejected)

    @patch("kling_client.request_owner_permission_for_kling")
    @patch("kling_client.check_kling_credits")
    @patch("kling_client.submit_text_to_video")
    @patch("kling_client.get_task_status")
    @patch("kling_client.download_kling_video")
    @patch("subprocess.run")
    def test_generate_kling_video_async_flow(
        self, mock_run, mock_dl, mock_status, mock_submit, mock_credits, mock_perm
    ):
        mock_perm.return_value = True
        mock_credits.return_value = (True, {"credits": 100})
        mock_submit.return_value = (True, "task_111")
        mock_status.return_value = (True, {"status": "succeed", "video_url": "https://kling.ai/v.mp4"})
        mock_dl.return_value = "/tmp/fake_kling.mp4"

        with patch("os.path.exists", return_value=True), patch("os.remove"):
            with patch("time.sleep"):
                # Run for owner (permission bypassed)
                t1 = kling_client.generate_kling_video_async(
                    prompt="Owner request",
                    is_owner=True
                )
                t1.join(timeout=2.0)
                self.assertFalse(mock_perm.called)

                # Run for Yarik (permission checked)
                t2 = kling_client.generate_kling_video_async(
                    prompt="Yarik request",
                    is_owner=False,
                    sender_name="Ярик"
                )
                t2.join(timeout=2.0)
                self.assertTrue(mock_perm.called)

    @patch("kling_client.check_kling_credits")
    @patch("kling_client.submit_text_to_video")
    @patch("subprocess.run")
    def test_generate_kling_video_async_zero_credits(self, mock_run, mock_submit, mock_credits):
        mock_credits.return_value = (True, {"credits": 0})
        with patch.dict(os.environ, {"KLING_API_KEY": "fake_key"}):
            t = kling_client.generate_kling_video_async(
                prompt="No credits test",
                is_owner=True
            )
            t.join(timeout=2.0)
            # Submit should NOT be called because credits are 0
            self.assertFalse(mock_submit.called)

    @patch("skills.kling_video_skill.generate_kling_video_async")
    def test_kling_video_skill_invokes_async(self, mock_gen_async):
        with patch.dict(os.environ, {"KLING_API_KEY": "fake_key"}):
            import skills.kling_video_skill as kvs
            res, media = kvs.handle_task("сгенерируй видео неоновый город", is_owner_sender=True)
            self.assertIn("🎬", res)
            self.assertIsNone(media)
            mock_gen_async.assert_called_once()
            self.assertIn("неоновый город", mock_gen_async.call_args[1]["prompt"])


if __name__ == "__main__":
    unittest.main()
