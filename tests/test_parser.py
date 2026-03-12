from __future__ import annotations

import unittest

from chatgpt_share_parser.parser import format_transcript, normalize_message_content


class ParserFormattingTests(unittest.TestCase):
    def test_normalize_message_content_collapses_extra_blank_lines(self) -> None:
        text = "line 1\n\n\nline 2\n\n- a\n\n- b"
        self.assertEqual(normalize_message_content(text), "line 1\n\nline 2\n\n- a\n- b")

    def test_format_transcript_numbers_each_role_independently(self) -> None:
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
            {"role": "assistant", "content": "again"},
            {"role": "user", "content": "bye"},
        ]
        expected = (
            "## User 01\n\nhello\n\n"
            "## Assistant 01\n\nworld\n\n"
            "## Assistant 02\n\nagain\n\n"
            "## User 02\n\nbye\n"
        )
        self.assertEqual(format_transcript(messages), expected)


if __name__ == "__main__":
    unittest.main()
