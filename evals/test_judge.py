import json
import unittest
from unittest.mock import MagicMock, patch

import judge


class OllamaFormatTests(unittest.TestCase):
    def test_request_formats(self):
        for mode in (None, "json", "schema", "none"):
            with self.subTest(mode=mode):
                env = {} if mode is None else {"JUDGE_FORMAT": mode}
                response = MagicMock()
                response.__enter__.return_value.read.return_value = (
                    b'{"response": "{\\"verdict\\": \\"PASS\\"}"}')
                with patch.dict(judge.os.environ, env, clear=True), patch.object(
                        judge._opener, "open", return_value=response) as request:
                    raw = judge._ollama("prompt", "ollama:qwen2.5:7b", None)
                body = json.loads(request.call_args.args[0].data)
                self.assertEqual(body["model"], "qwen2.5:7b")
                self.assertEqual(body["options"]["temperature"], 0)
                self.assertFalse(body["stream"])
                self.assertEqual(raw, '{"verdict": "PASS"}')
                if mode == "none":
                    self.assertNotIn("format", body)
                elif mode == "schema":
                    self.assertEqual(body["format"], judge.JUDGE_SCHEMA)
                    self.assertEqual(
                        set(body["format"]["required"]),
                        {"verdict", "trigger", "evidence_turn", "quote"})
                else:
                    self.assertEqual(body["format"], "json")

    def test_invalid_format_fails_before_request(self):
        with patch.dict(judge.os.environ, {"JUDGE_FORMAT": "invalid"}), patch.object(
                judge._opener, "open") as request:
            with self.assertRaisesRegex(ValueError, "Invalid JUDGE_FORMAT"):
                judge._ollama("prompt", "ollama:qwen2.5:7b", 0)
            request.assert_not_called()

    def test_single_call_records_invalid_json_without_retry(self):
        for raw in ("not JSON", '{"verdict":"PASS"}',
                    '{"verdict":"PASS","trigger":"","quote":"","evidence_turn":true}'):
            with self.subTest(raw=raw), patch.object(
                    judge, "_ollama", return_value=raw) as call:
                result = judge.judge_once("q", "a", "r", "ollama:test")
                self.assertEqual(result["verdict"], "ERROR")
                self.assertEqual(result["raw"], raw)
                self.assertTrue(result["error"])
                call.assert_called_once()

    def test_single_call_preserves_valid_response(self):
        data = {"verdict": "PASS", "trigger": "clause", "quote": "a",
                "evidence_turn": 1}
        with patch.object(judge, "_ollama", return_value=json.dumps(data)):
            result = judge.judge_once("q", "a", "r", "ollama:test")
        self.assertIsNone(result["error"])
        self.assertEqual(result["quote"], "a")


if __name__ == "__main__":
    unittest.main()
