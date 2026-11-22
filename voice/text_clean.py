"""Text cleaner and speech summarizer for natural, concise TTS output."""

from __future__ import annotations

import re

# Match <think>...</think> reasoning blocks
_THINK_BLOCK = re.compile(r"(?is)<think>.*?</think>")

# Match markdown code blocks and inline code
_CODE_BLOCK = re.compile(r"(?s)```.*?```")
_INLINE_CODE = re.compile(r"`([^`]+)`")

# Match URLs
_URL_PATTERN = re.compile(r"https?://\S+|www\.\S+")

# Match markdown images and links
_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^)]*\)")

# Match markdown table borders and divider lines (e.g. |---|---|)
_TABLE_DIVIDER = re.compile(r"(?m)^\s*\|?[\s\-:|]+\|?\s*$")
_TABLE_ROW_BORDER = re.compile(r"(?m)^\s*\|\s*|\s*\|\s*$")

# Markdown decoration
_HEADING = re.compile(r"(?m)^\s*#{1,6}\s+")
_BLOCKQUOTE = re.compile(r"(?m)^\s*>\s*")
_BULLETS = re.compile(r"(?m)^\s*[-*+•]\s+")
_ORDERED_LIST = re.compile(r"(?m)^\s*\d+[.)]\s+")
_EMPHASIS = re.compile(r"(\*\*|__|\*|_)")
_STRIKETHROUGH = re.compile(r"~~")

# Emojis and miscellaneous symbols
_EMOJI_PATTERN = re.compile(
    r"[\U00010000-\U0010ffff"  # Astral planes (surrogate-pair emojis)
    r"\u2600-\u27bf"          # Misc symbols & dingbats
    r"\u2300-\u23ff"          # Misc technical
    r"\u2b50-\u2b55"
    r"\ufe0e\ufe0f"           # Variation selectors
    r"\u200d"                 # Zero-width joiner
    r"]+",
    flags=re.UNICODE,
)

# Currency and common symbols
_DOLLAR_AMOUNT = re.compile(r"\$(\d+(?:\.\d+)?)")
_RUPEE_AMOUNT = re.compile(r"₹\s*(\d+(?:[.,]\d+)?)\s*([kKlL]|cr|crore|lakh)?(\+)?", re.IGNORECASE)
_PERCENT_AMOUNT = re.compile(r"(\d+(?:\.\d+)?)\s*%")

# Section headers in structured replies
_SECTION_HEADER = re.compile(
    r"^(?:#{1,6}\s*)?(?P<label>[A-Za-z][A-Za-z0-9\s/&-]{0,30}):\s*$"
)
_PAST_SECTION_LABELS = {"past", "completed", "archived", "previous", "ended", "closed", "done"}

# Dash-separated detail lines (e.g. "Title — Date (Mode) — Details" or "Title - Details")
_DASH_DETAIL_SPLIT = re.compile(r"\s+(?:—|–|--|-)\s+")
_FRACTION_PATTERN = re.compile(r"\b(\d+)\s*/\s*(\d+)\b")
_FILE_EXT_PATTERN = re.compile(r"\b([A-Za-z0-9_]+)\.(cpp|hpp|py|js|jsx|ts|tsx|java|json|md|sql|html|css)\b")
_CPP_PATTERN = re.compile(r"\bC\+\+(?![A-Za-z0-9])")
_CSHARP_PATTERN = re.compile(r"\bC#(?![A-Za-z0-9])")


def _replace_rupee(match: re.Match[str]) -> str:
    amount = match.group(1).replace(",", "")
    unit = (match.group(2) or "").lower()
    plus = " plus" if match.group(3) else ""
    unit_map = {
        "k": " thousand",
        "l": " lakh",
        "lakh": " lakh",
        "cr": " crore",
        "crore": " crore",
    }
    spoken_unit = unit_map.get(unit, "")
    return f"{amount}{spoken_unit}{plus} rupees"


def clean_text_for_speech(text: str) -> str:
    """Transform markdown and technical text into clean, pronounceable English sentences."""
    if not text:
        return ""

    # 1. Drop reasoning blocks
    text = _THINK_BLOCK.sub(" ", text)

    # 2. Strip code blocks completely, preserve inline code content
    text = _CODE_BLOCK.sub(" ", text)
    text = _INLINE_CODE.sub(r"\1", text)

    # 3. Strip URLs, images, retain link anchor text
    text = _URL_PATTERN.sub(" ", text)
    text = _IMAGE_PATTERN.sub(" ", text)
    text = _LINK_PATTERN.sub(r"\1", text)

    # 4. Remove tables and table dividers
    text = _TABLE_DIVIDER.sub(" ", text)
    text = _TABLE_ROW_BORDER.sub(" ", text)
    text = text.replace("|", ", ")

    # 5. Remove markdown structure
    text = _HEADING.sub("", text)
    text = _BLOCKQUOTE.sub("", text)
    text = _BULLETS.sub("", text)
    text = _ORDERED_LIST.sub("", text)
    text = _EMPHASIS.sub("", text)
    text = _STRIKETHROUGH.sub("", text)

    # 6. Currency, technical terms, and spoken math/symbols
    text = _CPP_PATTERN.sub("C plus plus", text)
    text = _CSHARP_PATTERN.sub("C sharp", text)
    text = _FILE_EXT_PATTERN.sub(
        lambda m: f"{m.group(1).replace('_', ' ')} dot {m.group(2)}",
        text,
    )
    text = _FRACTION_PATTERN.sub(r"\1 out of \2", text)
    text = _RUPEE_AMOUNT.sub(_replace_rupee, text)
    text = _DOLLAR_AMOUNT.sub(r"\1 dollars", text)
    text = _PERCENT_AMOUNT.sub(r"\1 percent", text)
    text = text.replace("%", " percent")
    text = text.replace("&", " and ")
    text = text.replace("×", " and ")
    text = text.replace("@", " at ")
    text = text.replace("°C", " degrees Celsius")
    text = text.replace("°F", " degrees Fahrenheit")
    text = text.replace("°", " degrees")
    text = text.replace("=", " equals ")
    text = re.sub(r"\s+[—–-]\s+", ", ", text)
    text = re.sub(r"(?<=[A-Za-z0-9])_(?=[A-Za-z0-9])", " ", text)

    # 7. Strip emojis and odd unicode symbols
    text = _EMOJI_PATTERN.sub("", text)

    # 8. Collapse whitespace and repeated punctuation
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*", "\n", text)
    text = re.sub(r"\n+", ".\n", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"([,.!?;:]){2,}", r"\1", text)

    return text.strip()


def _extract_item_headline(line: str) -> str:
    """Extract just the main title/subject from a list or dash-detailed line."""
    cleaned = _BULLETS.sub("", line.strip())
    cleaned = _ORDERED_LIST.sub("", cleaned)
    cleaned = _EMPHASIS.sub("", cleaned)
    cleaned = _LINK_PATTERN.sub(r"\1", cleaned).strip()
    # Split on em-dash / en-dash / spaced hyphen metadata
    parts = _DASH_DETAIL_SPLIT.split(cleaned)
    head = parts[0].strip()
    # If `Title: long description`, keep the title when short and capitalized
    if ":" in head:
        left, right = head.split(":", 1)
        if 2 <= len(left.strip()) <= 50 and right.strip():
            head = left.strip()
    # Remove trailing parenthetical metadata like "(Online)" or "(high priority)"
    head = re.sub(r"\s*\([^)]{1,40}\)\s*$", "", head).strip()
    return head.rstrip(".,;:-—– ")


def _join_natural(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def summarize_for_speech(text: str, max_items: int = 4, max_prose_chars: int = 260) -> str:
    """Condense chat responses so TTS speaks only the main highlights naturally.

    - Short conversational replies are spoken as-is.
    - Structured lists or dash-detailed blocks (e.g., hackathons, tasks, search
      results) speak the intro, the top item names only (skipping secondary
      dates/prizes/parentheticals and 'Past'/'Completed' sections when active
      items exist), and any closing question.
    - Long multi-paragraph or code-heavy replies speak the first 1-2 summary
      sentences plus any closing question.
    """
    if not text or not text.strip():
        return ""

    without_think = _THINK_BLOCK.sub(" ", text).strip()
    has_code_block = bool(_CODE_BLOCK.search(without_think))
    without_code = _CODE_BLOCK.sub(" ", without_think).strip()

    raw_lines = [ln.strip() for ln in without_code.splitlines() if ln.strip()]
    if not raw_lines:
        return clean_text_for_speech(text)

    # Check if this is a multi-section analytical/overview summary (e.g., Tasks + Habits + Learning + Focus Areas)
    named_sections: list[tuple[str, list[str]]] = []
    section_intro: list[str] = []
    closing_question = ""
    active_sec_name: str | None = None
    active_sec_lines: list[str] = []

    _INLINE_SECTION = re.compile(
        r"^(?:#{1,6}\s*)?(?P<label>(?:Tasks?|Habits?|Learning(?:\s+Progress|\s+Roadmap)?|Focus(?:\s+Areas?)?|Gamification|Reminders?|Summary|Overview|Recommendations?)(?:\s*\([^)]*\))?):\s*(?P<rest>.*)$",
        re.IGNORECASE,
    )

    for ln in raw_lines:
        plain_ln = _EMPHASIS.sub("", ln).strip()
        if not plain_ln:
            continue
        m_inline = _INLINE_SECTION.match(plain_ln)
        if m_inline:
            if active_sec_name is not None:
                named_sections.append((active_sec_name, active_sec_lines))
            active_sec_name = m_inline.group("label").strip()
            rest = m_inline.group("rest").strip()
            active_sec_lines = [rest] if rest else []
            continue
        if plain_ln.endswith("?") and len(plain_ln) <= 130 and active_sec_name is not None:
            closing_question = plain_ln
            continue
        if active_sec_name is None:
            section_intro.append(plain_ln)
        else:
            active_sec_lines.append(plain_ln)

    if active_sec_name is not None:
        named_sections.append((active_sec_name, active_sec_lines))

    # Case 0: Multi-section analytics / overview briefing — speak concise natural highlights
    if len(named_sections) >= 2:
        focus_sections = [
            (lbl, lines)
            for lbl, lines in named_sections
            if any(k in lbl.lower() for k in ("focus", "recommend", "improve", "summary"))
        ]
        spoken_parts: list[str] = []
        if section_intro:
            lead = section_intro[0].rstrip(":. ")
            if len(lead) <= 80:
                spoken_parts.append(f"{lead}.")

        # Prioritize focus/recommendations if present, plus key status from habits/learning/tasks
        selected = []
        for lbl, lines in named_sections:
            low = lbl.lower()
            if "gamification" in low:
                continue
            if focus_sections and any(k in low for k in ("focus", "recommend")):
                items = [_extract_item_headline(x) for x in lines if x.strip()]
                items = [x for x in items if x][:3]
                if items:
                    selected.append(f"Your main focus areas are {_join_natural(items)}.")
                continue
            # Keep first concise takeaway sentence for status sections
            if lines and len(selected) < 3:
                first_line = _BULLETS.sub("", _ORDERED_LIST.sub("", lines[0])).strip()
                first_sent = re.split(r"(?<=[.!?])\s+", first_line)[0].rstrip(".")
                if first_sent and len(first_sent) <= 115:
                    if low.startswith(("task", "learning")):
                        selected.append(f"{first_sent}.")
                    elif low.startswith("habit"):
                        # Summarize missed/pending habit if mentioned in lines
                        missed = next(
                            (l for l in lines if re.search(r"\b(not done|missed|pending|uncompleted)\b", l, re.I)),
                            None,
                        )
                        if missed:
                            habit_name = _extract_item_headline(missed)
                            selected.append(f"For habits, {habit_name} is still pending today.")
                        else:
                            selected.append(f"For habits, {first_sent}.")

        if selected:
            spoken_parts.extend(selected[:3])
            if closing_question:
                spoken_parts.append(closing_question)
            return clean_text_for_speech(" ".join(spoken_parts))

    # Check if this is a structured list or dash-detailed response
    intro_lines: list[str] = []
    outro_lines: list[str] = []
    primary_items: list[str] = []
    past_items: list[str] = []
    current_section = "primary"
    seen_list_or_section = False

    for ln in raw_lines:
        sec_match = _SECTION_HEADER.match(_EMPHASIS.sub("", ln))
        if sec_match:
            seen_list_or_section = True
            label = sec_match.group("label").strip().lower()
            if any(word in label for word in _PAST_SECTION_LABELS):
                current_section = "past"
            else:
                current_section = "primary"
            continue

        is_bullet = bool(_BULLETS.match(ln) or _ORDERED_LIST.match(ln))
        is_dash_item = len(_DASH_DETAIL_SPLIT.split(ln)) >= 2
        if is_bullet or is_dash_item:
            seen_list_or_section = True
            headline = _extract_item_headline(ln)
            if headline:
                if current_section == "past":
                    past_items.append(headline)
                else:
                    primary_items.append(headline)
            continue

        if not seen_list_or_section:
            intro_lines.append(ln)
        else:
            outro_lines.append(ln)

    chosen_items = primary_items if primary_items else past_items

    # Case 1: Structured list / dash-detailed items (2+ items, or 1+ item with sections/dash details)
    if len(chosen_items) >= 2 or (len(chosen_items) == 1 and (past_items or len(raw_lines) >= 3)):
        spoken_parts: list[str] = []
        if intro_lines:
            intro = intro_lines[0].rstrip(":. ")
            display_items = chosen_items[:max_items]
            extra_count = len(chosen_items) - len(display_items)
            joined = _join_natural(display_items)
            if extra_count > 0:
                joined = f"{joined}, and {extra_count} more"
            spoken_parts.append(f"{intro}: {joined}.")
        else:
            display_items = chosen_items[:max_items]
            extra_count = len(chosen_items) - len(display_items)
            joined = _join_natural(display_items)
            if extra_count > 0:
                joined = f"{joined}, and {extra_count} more"
            spoken_parts.append(f"The main ones are {joined}.")

        # Keep closing question or short call-to-action if present
        if outro_lines:
            last_outro = outro_lines[-1]
            if "?" in last_outro or len(last_outro) <= 90:
                spoken_parts.append(last_outro)

        return clean_text_for_speech(" ".join(spoken_parts))

    # Case 2: Long prose or code-heavy explanation
    cleaned_full = clean_text_for_speech(without_code)
    if len(cleaned_full) <= max_prose_chars and not has_code_block:
        return cleaned_full

    # Split into sentences and keep the first 1-2 main sentences + any trailing question
    sentence_chunks = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+", cleaned_full)
        if s.strip()
    ]
    if not sentence_chunks:
        return cleaned_full

    summary_sentences = sentence_chunks[:2]
    if len(" ".join(summary_sentences)) > max_prose_chars:
        summary_sentences = sentence_chunks[:1]

    if has_code_block:
        summary_sentences.append("I've put the code and details in the chat.")
    elif len(sentence_chunks) > len(summary_sentences):
        last_sent = sentence_chunks[-1]
        if last_sent.endswith("?") and last_sent not in summary_sentences and len(last_sent) <= 100:
            summary_sentences.append(last_sent)

    return " ".join(summary_sentences).strip()
