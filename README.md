# chatgpt-share-parser

Render a `chatgpt.com/share/...` page in Chromium and extract a clean, speaker-labeled transcript plus structured JSON.

This tool avoids scraping ChatGPT's hydration payload. Instead, it renders the shared page with Playwright and parses visible `article` blocks, which makes the output more robust when the backend share APIs are challenge-protected and when KaTeX text gets duplicated by naive `innerText` extraction.

## Features

- Parses each `article` block as a single message turn
- Detects `user` and `assistant` turns from the page markers
- Converts KaTeX formulas into Markdown-friendly `$...$` and `$$...$$`
- Preserves fenced code blocks
- Collapses excess blank lines for readable transcripts
- Writes transcript Markdown, full rendered text, and JSON message arrays

## Installation

```bash
pip install .
python -m playwright install chromium
```

## Usage

Print a transcript directly to stdout:

```bash
chatgpt-share-parser 'https://chatgpt.com/share/...'
```

Write transcript and JSON outputs to files:

```bash
chatgpt-share-parser 'https://chatgpt.com/share/...' \
  --conversation-output ./out/transcript.md \
  --json-output ./out/messages.json \
  --rendered-output ./out/rendered.txt
```

The legacy script entry point is also kept:

```bash
python scripts/parse_share.py 'https://chatgpt.com/share/...'
```

## Output format

Transcript output is compact and speaker-labeled:

```markdown
## User 01

...

## Assistant 01

...
```

JSON output is a list of objects shaped like:

```json
[
  {
    "role": "user",
    "content": "..."
  },
  {
    "role": "assistant",
    "content": "..."
  }
]
```

## CLI options

- `--rendered-output`: write the fully rendered page text
- `--conversation-output`: write the compact Markdown transcript
- `--json-output`: write parsed messages as JSON
- `--timeout-ms`: navigation timeout in milliseconds
- `--settle-ms`: extra wait after DOM load to let the page finish rendering
- `--headful`: launch Chromium with a visible window for debugging
- `--stdout`: always print the transcript to stdout

## Development

Run the lightweight tests:

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

## License

MIT
