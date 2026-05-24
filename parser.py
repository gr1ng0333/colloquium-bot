from __future__ import annotations

import html
import re


BLOCK_FORMULA_RE = re.compile(r"\$\$([\s\S]*?)\$\$")
INLINE_FORMULA_RE = re.compile(r"\$([^\$]+?)\$")
GRAPH_BLOCK_RE = re.compile(r"\[ГРАФИК\][\s\S]*?\[/ГРАФИК\]", re.IGNORECASE)
GRAPH_MARKER_RE = re.compile(r"\[/?ГРАФИК\]", re.IGNORECASE)

IMAGE_PLACEHOLDER = (
    '<div class="image-placeholder">📊 К этому вопросу прилагается график '
    "(см. ниже)</div>"
)
IMAGE_PLACEHOLDER_TOKEN = "%%IMAGE_PLACEHOLDER%%"


def _protect_formulas(text: str) -> tuple[str, list[str], list[str]]:
    block_formulas: list[str] = []
    inline_formulas: list[str] = []

    def replace_block(match: re.Match) -> str:
        block_formulas.append(match.group(1))
        return f"%%BLOCK_FORMULA_{len(block_formulas) - 1}%%"

    def replace_inline(match: re.Match) -> str:
        inline_formulas.append(match.group(1))
        return f"%%INLINE_FORMULA_{len(inline_formulas) - 1}%%"

    text = BLOCK_FORMULA_RE.sub(replace_block, text)
    text = INLINE_FORMULA_RE.sub(replace_inline, text)
    return text, block_formulas, inline_formulas


def _remove_graph_markup(text: str, has_image: bool) -> str:
    placeholder_was_inserted = False

    def graph_replacement(_: re.Match) -> str:
        nonlocal placeholder_was_inserted
        if has_image and not placeholder_was_inserted:
            placeholder_was_inserted = True
            return f"\n\n{IMAGE_PLACEHOLDER_TOKEN}\n\n"
        return ""

    text = GRAPH_BLOCK_RE.sub(graph_replacement, text)
    text = GRAPH_MARKER_RE.sub(graph_replacement, text)
    return text


def _apply_strong(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)


def _heading_from_strong_line(line: str) -> str | None:
    match = re.fullmatch(r"<strong>(.*?)</strong>", line, re.DOTALL)
    if not match:
        return None

    content = match.group(1)
    if content.startswith("Вопрос"):
        return f"<h2>{content}</h2>"
    return f"<h3>{content}</h3>"


def _format_block(block: str) -> str:
    block = block.strip()
    if not block:
        return ""

    if block == IMAGE_PLACEHOLDER_TOKEN:
        return block

    if re.fullmatch(r"%%BLOCK_FORMULA_\d+%%", block):
        return block

    parts: list[str] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_lines:
            paragraph = "<br>".join(paragraph_lines)
            parts.append(f"<p>{paragraph}</p>")
            paragraph_lines.clear()

    for line in block.splitlines():
        line = line.strip()
        if not line:
            flush_paragraph()
            continue

        heading = _heading_from_strong_line(line)
        if heading:
            flush_paragraph()
            parts.append(heading)
            continue

        paragraph_lines.append(line)

    flush_paragraph()
    return "\n".join(parts)


def _restore_formulas(
    text: str,
    block_formulas: list[str],
    inline_formulas: list[str],
) -> str:
    for index, formula in enumerate(block_formulas):
        text = text.replace(
            f"%%BLOCK_FORMULA_{index}%%",
            f'<div class="katex-block">$${formula}$$</div>',
        )

    for index, formula in enumerate(inline_formulas):
        text = text.replace(
            f"%%INLINE_FORMULA_{index}%%",
            f'<span class="katex-inline">${formula}$</span>',
        )

    return text


def parse_raw_text(raw_text: str, has_image: bool = False) -> str:
    text, block_formulas, inline_formulas = _protect_formulas(raw_text)
    text = _remove_graph_markup(text, has_image)
    text = html.escape(text, quote=False)
    text = _apply_strong(text)
    text = re.sub(r"(%%BLOCK_FORMULA_\d+%%|%%IMAGE_PLACEHOLDER%%)", r"\n\n\1\n\n", text)

    blocks = re.split(r"\n\s*\n+", text)
    fragment = "\n".join(
        formatted for block in blocks if (formatted := _format_block(block))
    )
    fragment = fragment.replace(IMAGE_PLACEHOLDER_TOKEN, IMAGE_PLACEHOLDER)

    return _restore_formulas(fragment, block_formulas, inline_formulas)
