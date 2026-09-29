import json
import unittest

from copilot_bridge.protocol import extract_calls, format_result, iter_json_objects


class TestJsonScanner(unittest.TestCase):
    def test_finds_top_level_objects(self):
        text = 'davor {"a": 1} dazwischen {"b": {"c": 2}} danach'
        self.assertEqual(list(iter_json_objects(text)), ['{"a": 1}', '{"b": {"c": 2}}'])

    def test_braces_inside_strings_are_ignored(self):
        text = '{"a": "ein { ohne }"}'
        self.assertEqual(list(iter_json_objects(text)), [text])

    def test_escaped_quote_does_not_end_the_string(self):
        text = r'{"a": "er sagte \"hallo{\" und ging"}'
        self.assertEqual(list(iter_json_objects(text)), [text])

    def test_unbalanced_text_yields_nothing(self):
        self.assertEqual(list(iter_json_objects('{"a": 1')), [])


class TestExtractCalls(unittest.TestCase):
    def test_plain_text_payload(self):
        calls, errors = extract_calls('bitte: {"bridge":1,"tool":"sys.info","id":"x"}')
        self.assertEqual(errors, [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].tool, "sys.info")
        self.assertEqual(calls[0].id, "x")
        self.assertEqual(calls[0].args, {})

    def test_code_block_payload(self):
        code = [{"lang": "json", "text": '{"bridge":1,"tool":"fs.read","args":{"path":"a.txt"}}'}]
        calls, errors = extract_calls("siehe unten", code)
        self.assertEqual(errors, [])
        self.assertEqual(calls[0].tool, "fs.read")
        self.assertEqual(calls[0].args, {"path": "a.txt"})
        self.assertTrue(calls[0].id, "an id is generated when none is given")

    def test_marker_payload(self):
        text = 'Antwort <<<BRIDGE {"bridge":1,"tool":"bridge.ping"} BRIDGE>>> Ende'
        calls, _ = extract_calls(text)
        self.assertEqual([c.tool for c in calls], ["bridge.ping"])

    def test_batch_of_calls(self):
        payload = '{"bridge":1,"calls":[{"tool":"a.one"},{"tool":"b.two","args":{"x":1}}]}'
        calls, errors = extract_calls(payload)
        self.assertEqual(errors, [])
        self.assertEqual([c.tool for c in calls], ["a.one", "b.two"])
        self.assertEqual(calls[1].args, {"x": 1})

    def test_json_without_the_marker_is_ignored(self):
        calls, errors = extract_calls('{"tool":"shell.run","args":{"cmd":"dir"}}')
        self.assertEqual(calls, [])
        self.assertEqual(errors, [])

    def test_prose_about_tools_is_ignored(self):
        text = "Ich koennte fs.delete aufrufen, aber das mache ich lieber nicht."
        self.assertEqual(extract_calls(text)[0], [])

    def test_same_payload_in_text_and_code_is_deduplicated(self):
        payload = '{"bridge":1,"tool":"sys.info","id":"dup"}'
        calls, _ = extract_calls(f"hier: {payload}", [{"lang": "json", "text": payload}])
        self.assertEqual(len(calls), 1)

    def test_two_calls_differing_only_in_id_are_both_kept(self):
        text = (
            '{"bridge":1,"tool":"sys.info","id":"a"} und '
            '{"bridge":1,"tool":"sys.info","id":"b"}'
        )
        calls, _ = extract_calls(text)
        self.assertEqual([c.id for c in calls], ["a", "b"])
        self.assertNotEqual(calls[0].digest, calls[1].digest)

    def test_smart_quotes_are_repaired(self):
        text = '{\u201cbridge\u201d:1,\u201ctool\u201d:\u201csys.info\u201d}'
        calls, _ = extract_calls(text)
        self.assertEqual([c.tool for c in calls], ["sys.info"])

    def test_bad_tool_type_is_reported(self):
        calls, errors = extract_calls('{"bridge":1,"tool":42}')
        self.assertEqual(calls, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("non-empty string", errors[0])

    def test_bad_args_type_is_reported(self):
        calls, errors = extract_calls('{"bridge":1,"tool":"sys.info","args":"nope"}')
        self.assertEqual(calls, [])
        self.assertIn("must be an object", errors[0])

    def test_oversized_payload_is_refused(self):
        huge = '{"bridge":1,"tool":"x","args":{"blob":"' + "a" * 250_000 + '"}}'
        calls, errors = extract_calls(huge)
        self.assertEqual(calls, [])
        self.assertIn("exceeds", errors[0])

    def test_windows_path_backslashes_survive(self):
        code = [{"lang": "", "text": r'{"bridge":1,"tool":"fs.list","args":{"path":"C:\\Users\\Max"}}'}]
        calls, _ = extract_calls("", code)
        self.assertEqual(calls[0].args["path"], r"C:\Users\Max")


class TestFormatResult(unittest.TestCase):
    def test_success_envelope(self):
        parsed = json.loads(format_result("id1", True, {"a": 1}))
        self.assertEqual(parsed, {"bridge_result": 1, "id": "id1", "ok": True, "result": {"a": 1}})

    def test_error_envelope(self):
        parsed = json.loads(format_result("id1", False, "kaputt"))
        self.assertFalse(parsed["ok"])
        self.assertEqual(parsed["error"], "kaputt")

    def test_truncation_keeps_valid_json(self):
        text = format_result("id1", True, {"blob": "x" * 5000}, max_chars=500)
        parsed = json.loads(text)
        self.assertTrue(parsed["truncated"])
        self.assertLessEqual(len(text), 500)
        self.assertIn("truncated", parsed["result"])

    def test_result_envelope_is_not_mistaken_for_a_call(self):
        text = format_result("id1", True, {"path": "a.txt"})
        self.assertEqual(extract_calls(text)[0], [], "results must never re-trigger execution")


if __name__ == "__main__":
    unittest.main()
