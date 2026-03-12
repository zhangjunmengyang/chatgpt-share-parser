"""Render a ChatGPT share page and extract compact conversation outputs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PREAMBLE = "This is a copy of a conversation between ChatGPT & Anonymous."
ROLE_LABELS = {
    "user": "User",
    "assistant": "Assistant",
}


EXTRACT_MESSAGES_JS = r"""
() => {
  const paragraphTags = new Set(['P', 'DIV', 'SECTION', 'ARTICLE', 'BLOCKQUOTE', 'TABLE', 'TR', 'TD', 'TH']);
  const headingTags = new Set(['H1', 'H2', 'H3', 'H4']);

  function clean(text) {
    return text
      .replace(/\u200b/g, '')
      .replace(/[ \t]+\n/g, '\n')
      .replace(/[ \t]{2,}/g, ' ')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  function extract(node) {
    if (!node) return '';

    if (node.nodeType === Node.TEXT_NODE) {
      return node.textContent || '';
    }

    if (node.nodeType !== Node.ELEMENT_NODE) {
      return '';
    }

    const el = node;
    const tag = el.tagName;

    if (tag === 'H5' || tag === 'H6') return '';
    if (tag === 'BR') return '\n';
    if (el.getAttribute('aria-hidden') === 'true') return '';

    if (el.matches('.katex-display')) {
      const ann = el.querySelector('annotation');
      return ann ? `\n$$${ann.textContent || ''}$$\n` : '';
    }

    if (el.matches('.katex')) {
      const ann = el.querySelector('annotation');
      return ann ? `$${ann.textContent || ''}$` : '';
    }

    if (el.matches('.katex-html, .katex-mathml')) return '';
    if (tag === 'ANNOTATION') return '';

    if (tag === 'PRE') {
      const inner = clean(el.innerText || '');
      return inner ? '\n```\\n' + inner + '\\n```\\n' : '';
    }

    if (tag === 'CODE') {
      return clean(el.innerText || '');
    }

    if (tag === 'LI') {
      let text = '';
      for (const child of el.childNodes) text += extract(child);
      text = clean(text);
      return text ? `- ${text}\n` : '';
    }

    if (tag === 'UL' || tag === 'OL') {
      let text = '';
      for (const child of el.childNodes) text += extract(child);
      return '\n' + clean(text) + '\n';
    }

    let text = '';
    for (const child of el.childNodes) {
      text += extract(child);
    }

    text = clean(text);
    if (!text) return '';

    if (headingTags.has(tag)) {
      return `\n### ${text}\n`;
    }

    if (paragraphTags.has(tag)) {
      return `\n${text}\n`;
    }

    return text;
  }

  const articles = Array.from(document.querySelectorAll('article'));
  return articles.map((article) => {
    const marker = article.querySelector('h5, h6')?.textContent?.trim() || '';
    const role =
      marker === 'You said:' ? 'user' :
      marker === 'ChatGPT said:' ? 'assistant' :
      'unknown';

    return {
      role,
      content: clean(extract(article)),
    };
  }).filter(item => item.role !== 'unknown' && item.content);
}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a ChatGPT share page and extract compact conversation outputs."
    )
    parser.add_argument("url", help="chatgpt.com/share/... URL")
    parser.add_argument(
        "--rendered-output",
        type=Path,
        help="Write the full rendered page text here.",
    )
    parser.add_argument(
        "--conversation-output",
        type=Path,
        help="Write a compact speaker-labeled transcript here.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Write parsed role/content messages as JSON here.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=120_000,
        help="Navigation timeout in milliseconds.",
    )
    parser.add_argument(
        "--settle-ms",
        type=int,
        default=8_000,
        help="Extra wait after DOM load so the share page can finish rendering.",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Launch Chromium with a visible window for debugging.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Always print the transcript to stdout.",
    )
    return parser.parse_args()


def render_page(
    url: str,
    timeout_ms: int,
    settle_ms: int,
    headful: bool,
) -> tuple[str, list[dict[str, str]]]:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headful)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 2000})
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(settle_ms)
            page.get_by_text(PREAMBLE).wait_for(timeout=30_000)
            rendered = page.locator("body").inner_text(timeout=30_000)
            messages = page.evaluate(EXTRACT_MESSAGES_JS)
            return rendered, messages
        except PlaywrightTimeoutError as exc:
            raise RuntimeError(
                "Timed out while rendering the share page. "
                "If Chromium is missing, run `python -m playwright install chromium`."
            ) from exc
        finally:
            browser.close()


def write_text(path: Path | None, content: str) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path | None, payload: object) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_message_content(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(?m)(^- .+)\n\n(?=- )", r"\1\n", text)
    text = re.sub(r"(?m)(^\d+[.)] .+)\n\n(?=\d+[.)] )", r"\1\n", text)
    return text.strip()


def format_transcript(messages: list[dict[str, str]]) -> str:
    counters = {"user": 0, "assistant": 0}
    blocks: list[str] = []

    for message in messages:
        role = message["role"]
        counters[role] += 1
        label = ROLE_LABELS.get(role, role.title())
        header = f"## {label} {counters[role]:02d}"
        content = normalize_message_content(message["content"])
        blocks.append(f"{header}\n\n{content}")

    return "\n\n".join(blocks).strip() + "\n"


def build_summary(
    rendered_text: str,
    messages: list[dict[str, str]],
    rendered_output: Path | None,
    conversation_output: Path | None,
    json_output: Path | None,
) -> str:
    return json.dumps(
        {
            "rendered_chars": len(rendered_text),
            "messages": len(messages),
            "rendered_output": str(rendered_output) if rendered_output else None,
            "conversation_output": str(conversation_output) if conversation_output else None,
            "json_output": str(json_output) if json_output else None,
        },
        ensure_ascii=False,
        indent=2,
    )
