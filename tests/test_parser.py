from __future__ import annotations

import unittest

from chatgpt_share_parser import parser
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

    def test_extract_messages_from_current_share_data_merges_visible_assistant_turn(self) -> None:
        data = {
            "linear_conversation": [
                {
                    "message": {
                        "author": {"role": "system"},
                        "content": {"content_type": "text", "parts": ["hidden"]},
                        "metadata": {"is_visually_hidden_from_conversation": True},
                        "recipient": "all",
                    }
                },
                {
                    "message": {
                        "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": ["用户问题"]},
                        "metadata": {},
                        "recipient": "all",
                    }
                },
                {
                    "message": {
                        "author": {"role": "tool", "name": "a8km123"},
                        "content": {"content_type": "text", "parts": [""]},
                        "metadata": {"finished_text": "已思考 1m"},
                        "recipient": "all",
                    }
                },
                {
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {
                            "content_type": "text",
                            "parts": ["我先确认页面结构。"],
                        },
                        "metadata": {"is_thinking_preamble_message": True},
                        "recipient": "all",
                    }
                },
                {
                    "message": {
                        "author": {"role": "tool", "name": "web.run"},
                        "content": {
                            "content_type": "text",
                            "parts": ["The output of this plugin was redacted."],
                        },
                        "metadata": {"is_redacted": True},
                        "recipient": "all",
                    }
                },
                {
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {
                            "content_type": "text",
                            "parts": ["最终回答。citeturn1search0"],
                        },
                        "metadata": {
                            "content_references": [
                                {
                                    "matched_text": "citeturn1search0",
                                    "type": "grouped_webpages",
                                    "items": [
                                        {
                                            "title": "Example Source",
                                            "url": "https://example.com/source?utm_source=chatgpt.com",
                                            "attribution": "Example",
                                        }
                                    ],
                                }
                            ]
                        },
                        "recipient": "all",
                    }
                },
            ]
        }

        extract_messages_from_share_data = getattr(
            parser, "extract_messages_from_share_data", None
        )
        self.assertIsNotNone(extract_messages_from_share_data)
        messages = extract_messages_from_share_data(data)

        self.assertEqual(
            messages,
            [
                {"role": "user", "content": "用户问题"},
                {
                    "role": "assistant",
                    "content": "我先确认页面结构。\n\n已思考 1m\n\n最终回答。citeturn1search0",
                    "sources": [
                        {
                            "marker": "citeturn1search0",
                            "title": "Example Source",
                            "url": "https://example.com/source?utm_source=chatgpt.com",
                            "attribution": "Example",
                        }
                    ],
                },
            ],
        )

    def test_format_transcript_appends_sources_when_available(self) -> None:
        messages = [
            {
                "role": "assistant",
                "content": "回答。citeturn1search0",
                "sources": [
                    {
                        "marker": "citeturn1search0",
                        "title": "Example Source",
                        "url": "https://example.com/source?utm_source=chatgpt.com",
                        "attribution": "Example",
                    }
                ],
            }
        ]

        expected = (
            "## Assistant 01\n\n"
            "回答。citeturn1search0\n\n"
            "### Sources\n\n"
            "- `citeturn1search0`: [Example Source](https://example.com/source?utm_source=chatgpt.com) — Example\n"
        )
        self.assertEqual(format_transcript(messages), expected)


if __name__ == "__main__":
    unittest.main()
