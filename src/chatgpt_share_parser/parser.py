"""Render a ChatGPT share page and extract compact conversation outputs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

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

WAIT_FOR_CONVERSATION_JS = r"""
() => {
  const loaderData =
    window.__reactRouterContext?.state?.loaderData ||
    window.__reactRouterDataRouter?.state?.loaderData ||
    {};
  const hasShareData = Object.values(loaderData).some((value) => {
    const data = value?.serverResponse?.data;
    return data?.linear_conversation || data?.mapping;
  });
  return hasShareData || document.querySelector('article');
}
"""


EXTRACT_SHARE_DATA_JS = r"""
() => {
  const loaderData =
    window.__reactRouterContext?.state?.loaderData ||
    window.__reactRouterDataRouter?.state?.loaderData ||
    {};
  for (const value of Object.values(loaderData)) {
    const data = value?.serverResponse?.data;
    if (data?.linear_conversation || data?.mapping) return data;
  }
  return null;
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
            page.wait_for_function(WAIT_FOR_CONVERSATION_JS, timeout=30_000)
            rendered = page.locator("body").inner_text(timeout=30_000)
            share_data = page.evaluate(EXTRACT_SHARE_DATA_JS)
            messages = extract_messages_from_share_data(share_data)
            if not messages:
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


def extract_messages_from_share_data(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Extract visible transcript turns from ChatGPT share loader data."""

    messages: list[dict[str, Any]] = []
    preambles: list[str] = []
    finished_markers: list[str] = []

    for node in iter_conversation_nodes(data):
        message = node.get("message") or {}
        metadata = message.get("metadata") or {}
        if metadata.get("is_visually_hidden_from_conversation"):
            continue

        author = message.get("author") or {}
        role = author.get("role")
        text = extract_message_text(message)

        if role == "user" and message.get("recipient") == "all" and text:
            messages.append({"role": "user", "content": text})
            preambles = []
            finished_markers = []
            continue

        if role == "tool" and metadata.get("finished_text"):
            finished_markers.append(str(metadata["finished_text"]).strip())
            continue

        if role != "assistant" or message.get("recipient") != "all":
            continue

        content = message.get("content") or {}
        if content.get("content_type") != "text" or not text:
            continue

        if metadata.get("is_thinking_preamble_message"):
            preambles.append(text)
            continue

        assistant_parts = [*preambles, *finished_markers, text]
        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "content": "\n\n".join(part for part in assistant_parts if part),
        }
        sources = extract_message_sources(metadata)
        if sources:
            assistant_message["sources"] = sources
        messages.append(assistant_message)
        preambles = []
        finished_markers = []

    return messages


def iter_conversation_nodes(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    linear_conversation = data.get("linear_conversation")
    if isinstance(linear_conversation, list):
        return [node for node in linear_conversation if isinstance(node, dict)]

    mapping = data.get("mapping")
    current_node = data.get("current_node")
    if not isinstance(mapping, dict) or not current_node:
        return []

    nodes: list[dict[str, Any]] = []
    node_id = current_node
    seen: set[str] = set()
    while isinstance(node_id, str) and node_id not in seen:
        seen.add(node_id)
        node = mapping.get(node_id)
        if not isinstance(node, dict):
            break
        nodes.append(node)
        node_id = node.get("parent")
    return list(reversed(nodes))


def extract_message_text(message: dict[str, Any]) -> str:
    content = message.get("content") or {}
    if "parts" in content:
        return "\n".join(str(part) for part in content.get("parts") or []).strip()
    if "text" in content:
        return str(content.get("text") or "").strip()
    return ""


def extract_message_sources(metadata: dict[str, Any]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for reference in metadata.get("content_references") or []:
        if not isinstance(reference, dict):
            continue
        marker = (reference.get("matched_text") or "").strip()
        source_items = [
            *(reference.get("items") or []),
            *(reference.get("fallback_items") or []),
            *(reference.get("sources") or []),
        ]
        for item in source_items:
            if not isinstance(item, dict):
                continue
            add_source(sources, seen, item, marker)
            for supporting in item.get("supporting_websites") or []:
                add_source(sources, seen, supporting, marker)

    return sources


def add_source(
    sources: list[dict[str, str]],
    seen: set[tuple[str, str, str, str]],
    item: Any,
    marker: str,
) -> None:
    if not isinstance(item, dict):
        return
    title = str(item.get("title") or item.get("attribution") or item.get("url") or "")
    url = str(item.get("url") or "")
    attribution = str(item.get("attribution") or "")
    if not title and not url:
        return

    key = (marker, title, url, attribution)
    if key in seen:
        return
    seen.add(key)

    source: dict[str, str] = {}
    if marker:
        source["marker"] = marker
    if title:
        source["title"] = title
    if url:
        source["url"] = url
    if attribution:
        source["attribution"] = attribution
    sources.append(source)


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
        sources = format_sources(message.get("sources", []))
        if sources:
            content = f"{content}\n\n{sources}"
        blocks.append(f"{header}\n\n{content}")

    return "\n\n".join(blocks).strip() + "\n"


def format_sources(sources: object) -> str:
    if not isinstance(sources, list) or not sources:
        return ""

    lines = ["### Sources", ""]
    for source in sources:
        if not isinstance(source, dict):
            continue
        marker = source.get("marker")
        title = source.get("title") or source.get("url") or "Source"
        url = source.get("url")
        attribution = source.get("attribution")
        marker_prefix = f"`{marker}`: " if marker else ""
        if url:
            line = f"- {marker_prefix}[{title}]({url})"
        else:
            line = f"- {marker_prefix}{title}"
        if attribution:
            line += f" — {attribution}"
        lines.append(line)
    return "\n".join(lines)


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
