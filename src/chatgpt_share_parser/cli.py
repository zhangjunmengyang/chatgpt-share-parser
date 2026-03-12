"""Command-line entry point for chatgpt-share-parser."""

from __future__ import annotations

from chatgpt_share_parser.parser import (
    build_summary,
    format_transcript,
    parse_args,
    render_page,
    write_json,
    write_text,
)


def main() -> int:
    args = parse_args()
    rendered_text, messages = render_page(
        url=args.url,
        timeout_ms=args.timeout_ms,
        settle_ms=args.settle_ms,
        headful=args.headful,
    )

    transcript = format_transcript(messages)

    write_text(args.rendered_output, rendered_text)
    write_text(args.conversation_output, transcript)
    write_json(args.json_output, messages)

    should_print_transcript = args.stdout or not any(
        [args.rendered_output, args.conversation_output, args.json_output]
    )
    if should_print_transcript:
        print(transcript, end="")
    else:
        print(
            build_summary(
                rendered_text=rendered_text,
                messages=messages,
                rendered_output=args.rendered_output,
                conversation_output=args.conversation_output,
                json_output=args.json_output,
            )
        )
    return 0
