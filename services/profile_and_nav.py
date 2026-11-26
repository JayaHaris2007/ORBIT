"""Identity, user profile memory formatting, greeting, and UI navigation helpers."""

from __future__ import annotations

import re
from typing import Any


def _app():
    import app

    return app


_IDENTITY_QUESTION_PATTERNS = (
    re.compile(
        r"\bwho\s+(?:built|builed|builded|build|made|created|developed|"
        r"designed|coded|programmed)\s+(?:you|orbit|spidey|s\.p\.i\.d\.e\.y)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwho\s+(?:is|are)\s+your\s+(?:creator|developer|maker|builder|"
        r"author|owner|designer)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwho\s+(?:is|are)\s+behind\s+(?:you|orbit|spidey|s\.p\.i\.d\.e\.y)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:how|why)\s+(?:is|was|are|were)\s+(?:you|orbit|spidey|s\.p\.i\.d\.e\.y)\s+"
        r"(?:built|made|created|developed|designed)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:how|why)\s+(?:is|was|are|were)\s+(?:built|made|created)\s+"
        r"(?:you|orbit|spidey|s\.p\.i\.d\.e\.y)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:how|why)\s+(?:you|orbit|spidey|s\.p\.i\.d\.e\.y)\s+(?:are|were|is|was)\s+"
        r"(?:built|made|created)\b",
        re.IGNORECASE,
    ),
)

_BUILDER_NAME_PATTERN = re.compile(
    r"\b(?:built|builed|builded|made|created|developed|designed|coded|"
    r"programmed)\s+by\s+([A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){0,2})"
)

_BUILDER_LOOSE_PATTERN = re.compile(
    r"\b(?:built|builed|builded|made|created|developed|designed|coded|"
    r"programmed)\s+by\s+([^.;\n]{1,40})",
    re.IGNORECASE,
)

_ASSISTANT_REFERENCE_PATTERN = re.compile(
    r"\b(?:you|your|orbit|spidey|s\.p\.i\.d\.e\.y|assistant)\b", re.IGNORECASE
)


def _builder_names() -> list[str]:
    """Collect creator names from saved memories such as "built by Jaya Haris"."""
    names: list[str] = []
    for memory in _app().memory_store.list_memories():
        content = memory["content"]
        # Only memories that talk about the assistant describe its creator.
        if not _ASSISTANT_REFERENCE_PATTERN.search(content):
            continue
        match = _BUILDER_NAME_PATTERN.search(content) or _BUILDER_LOOSE_PATTERN.search(content)
        if not match:
            continue
        name = re.sub(r"\s+", " ", match.group(1)).strip(" .,!-")
        if name and name.lower() not in {existing.lower() for existing in names}:
            names.append(name)
    return names


def _identity_answer(prompt: str) -> str | None:
    """Answer creator questions straight from memory instead of the small model."""
    normalized = _app()._normalize_command(prompt)
    if not any(pattern.search(normalized) for pattern in _IDENTITY_QUESTION_PATTERNS):
        return None
    names = _builder_names()
    if not names:
        return None
    if len(names) == 1:
        return f"I was built by {names[0]}."
    return "I was built by " + ", ".join(names[:-1]) + f" and {names[-1]}."


# Notes about the assistant ("You was built by ...") skip the first person;
# notes the user saves about themselves usually start with I, my, or me.
_USER_FACT_PATTERN = re.compile(r"^(?:i|i'm|i’m|i've|my|me)\b", re.IGNORECASE)

_PROFILE_QUESTION_PATTERNS = (
    re.compile(
        r"\btell\s+(?:me\s+)?(?:something\s+|a bit\s+|more\s+)?about\s+me\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\btell\s+(?:me\s+)?(?:something\s+|a bit\s+|more\s+)?about\s+myself\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwhat\s+do\s+you\s+(?:know|remember|have)\s+(?:about|on)\s+me\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bdo\s+you\s+(?:know|remember)\s+me\b", re.IGNORECASE),
    re.compile(r"^(?:who|what)\s+am\s+i\s*$", re.IGNORECASE),
    re.compile(r"^describe\s+me\s*$", re.IGNORECASE),
    re.compile(r"\bsummar(?:y|ise|ize)\s+(?:me|myself)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:what(?:'s| is)|show(?:\s+me)?|tell\s+me)\s+my\s+"
        r"(?:profile|bio|details|background)\b",
        re.IGNORECASE,
    ),
    re.compile(r"^about\s+me\b", re.IGNORECASE),
)

_PROFILE_QUESTION_LEAD = re.compile(
    r"^(?:what|which|who|where|when|tell|show|list|do|does|can|could|how)\b",
    re.IGNORECASE,
)

# Words in the user's question that point at one part of their profile.
_PROFILE_TOPIC_WORDS = (
    ("The basics", ("name", "call me")),
    (
        "Education",
        (
            "education", "study", "studies", "studying", "college",
            "diploma", "degree", "school", "qualification", "background",
        ),
    ),
    (
        "Skills",
        ("skill", "skills", "stack", "technologies", "technology", "tech", "tools"),
    ),
    (
        "Currently building",
        ("working on", "developing", "building right now"),
    ),
    (
        "Projects",
        ("project", "projects", "built", "building", "portfolio", "work on"),
    ),
    ("Light House", ("startup", "business", "company", "light house")),
    ("Your setup", ("laptop", "computer", "pc", "hardware", "specs", "gpu", "ram")),
    (
        "How you like to work",
        ("goal", "goals", "ambition", "prefer", "preferences", "working style"),
    ),
)

# Keywords that decide which section of the summary a saved note belongs to.
_PROFILE_BUCKETS = (
    ("The basics", ("name", "developer", "enthusiast", "india", "entrepreneur")),
    (
        "Education",
        (
            "diploma", "degree", "college", "polytechnic", "b.e", "b.tech",
            "university", "school", "graduated",
        ),
    ),
    (
        "Skills",
        (
            "skill", "react", "javascript", "node", "python", "postgres",
            "firebase", "supabase", "tailwind", "rest api", "learning",
        ),
    ),
    (
        "Currently building",
        ("developing", "in progress", "currently working", "right now"),
    ),
    (
        "Projects",
        (
            "project", "spidey", "assistant", "application", "website", "build",
            "e-commerce", "client", "smart food",
        ),
    ),
    ("Light House", ("startup", "business", "company", "light house", "clients")),
    ("Your setup", ("laptop", "asus", "ryzen", "rtx", "gpu", "ram", "ssd", "hardware")),
    (
        "How you like to work",
        ("prefer", "enjoy", "goal", "long-term", "guidance", "interested", "ui design"),
    ),
)

_PROFILE_TOPIC_INTROS = {
    "The basics": "Here's what I have:",
    "Education": "Here's your background:",
    "Skills": "Here's your stack:",
    "Currently building": "Here's what you're building right now:",
    "Projects": "Here's what you've built:",
    "Light House": "Here's where Light House stands:",
    "Your setup": "Here's your setup:",
    "How you like to work": "Here's how you like to work:",
}

_SECOND_PERSON_REPLACEMENTS = (
    (re.compile(r"\bThe user's\b"), "Your"),
    (re.compile(r"\bthe user's\b"), "your"),
    (re.compile(r"\bThe user\b"), "You"),
    (re.compile(r"\bthe user\b"), "you"),
    (re.compile(r"\bMy\b"), "Your"),
    (re.compile(r"\bmy\b"), "your"),
    (re.compile(r"\bI[’']m\b"), "you're"),
    (re.compile(r"\bI am\b"), "you're"),
    (re.compile(r"\bI[’']ve\b"), "you've"),
    (re.compile(r"\bI[’']ll\b"), "you'll"),
    (re.compile(r"\bI[’']d\b"), "you'd"),
    (re.compile(r"\bI\b"), "you"),
    (re.compile(r"\bmyself\b"), "yourself"),
    (re.compile(r"\bmine\b"), "yours"),
    (re.compile(r"\bme\b"), "you"),
)

_NAME_IN_MEMORY_PATTERN = re.compile(
    r"\b(?:My name is|The user's name is|I'm|I am) "
    r"([A-Z][\w'-]*(?:\s+[A-Z][\w'-]*){0,2})"
)


def _describes_assistant(content: str) -> bool:
    """True for notes like "You was built by Jaya Haris", which describe S.P.I.D.E.Y."""
    return bool(
        _BUILDER_LOOSE_PATTERN.search(content)
        and _ASSISTANT_REFERENCE_PATTERN.search(content)
        and not _USER_FACT_PATTERN.match(content)
    )


def _user_fact_memories() -> list[dict[str, Any]]:
    """Everything saved about the user, minus the notes about the assistant."""
    facts = [
        memory
        for memory in _app().memory_store.list_memories()
        if not _describes_assistant(memory["content"].strip())
    ]
    facts.sort(key=lambda item: item["id"])
    return facts


_ASSISTANT_NAMES = {"spidey", "s.p.i.d.e.y", "s.p.i.d.e.y.", "jarvis", "orbit", "orbit007", "assistant"}


def _user_name(facts: list[dict[str, Any]]) -> str:
    for memory in facts:
        match = _NAME_IN_MEMORY_PATTERN.search(memory["content"])
        if match:
            candidate = match.group(1).strip(" .,!-")
            if candidate and candidate.lower() not in _ASSISTANT_NAMES:
                return candidate
    return ""


_THIRD_PERSON_VERBS = {
    "prefers": "prefer", "likes": "like", "loves": "love", "wants": "want",
    "needs": "need", "works": "work", "lives": "live", "studies": "study",
    "enjoys": "enjoy", "uses": "use", "has": "have", "does": "do",
    "goes": "go", "is": "are", "builds": "build", "makes": "make",
    "plans": "plan", "knows": "know", "plays": "play", "runs": "run",
    "keeps": "keep", "feels": "feel", "thinks": "think", "hopes": "hope",
}


def _second_person(text: str) -> str:
    """Rewrite a note the user saved about themselves so it addresses them."""
    result = text
    for pattern, replacement in _SECOND_PERSON_REPLACEMENTS:
        result = pattern.sub(replacement, result)
    # Notes written in the third person ("The user prefers ...") need their
    # verbs adjusted once "The user" becomes "you".
    result = re.sub(
        r"\b([Yy]ou) (\w+)\b",
        lambda match: (
            f"{match.group(1)} "
            f"{_THIRD_PERSON_VERBS.get(match.group(2).lower(), match.group(2))}"
        ),
        result,
    )
    # "I am developing" becomes "you're developing"; restore the capital.
    return re.sub(
        r"(^|[.!?]\s+)([a-z])",
        lambda match: match.group(1) + match.group(2).upper(),
        result,
    )


def _profile_label(content: str) -> str:
    """Pick the summary section a saved note belongs to."""
    lowered = content.lower()
    best_label = "Also worth knowing"
    best_score = 0
    for label, keywords in _PROFILE_BUCKETS:
        score = sum(1 for keyword in keywords if keyword in lowered)
        if score > best_score:
            best_label, best_score = label, score
    return best_label


def _profile_buckets(facts: list[dict[str, Any]]) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {}
    for memory in facts:
        label = _profile_label(memory["content"])
        buckets.setdefault(label, []).append(_second_person(memory["content"].strip()))
    return buckets


_NON_PROFILE_DOMAIN_GUARD = re.compile(
    r"\b(?:"
    r"tasks?|to[\s-]?dos?|habits?|streaks?|reminders?|remind|"
    r"roadmaps?|topics?|lessons?|modules?|learning|learn|"
    r"pending|remaining|left\s+to|next|unfinished|completed|done|"
    r"settings?|analytics?|stats?|telemetry|progress|briefing|"
    r"to\s+study|study\s+(?:plan|next|log|history|topics?)|studying\s+(?:right\s+now|now)"
    r")\b",
    re.IGNORECASE,
)


def _profile_topic(normalized: str) -> str | None:
    """Return the profile section a direct question like "what are my skills" asks about."""
    if not re.search(r"\b(?:my|i|me|mine)\b", normalized):
        return None
    if not _PROFILE_QUESTION_LEAD.match(normalized):
        return None
    # Never hijack actionable Tasks, Habits, Reminders, Learning, Analytics, or Settings queries.
    if _NON_PROFILE_DOMAIN_GUARD.search(normalized):
        return None
    for label, words in _PROFILE_TOPIC_WORDS:
        if any(re.search(rf"\b{re.escape(word)}\b", normalized) for word in words):
            return label
    return None


def _profile_overview(facts: list[dict[str, Any]]) -> str:
    buckets = _profile_buckets(facts)
    name = _user_name(facts)
    intro = (
        f"Here's what I've got on you, {name}:"
        if name
        else "Here's what I've got on you:"
    )
    lines: list[str] = []
    for label, _ in _PROFILE_BUCKETS:
        items = buckets.pop(label, [])
        if items:
            lines.append(f"- **{label}:** {' '.join(items)}")
    leftovers = [text for texts in buckets.values() for text in texts]
    if leftovers:
        lines.append(f"- **Also worth knowing:** {' '.join(leftovers)}")
    return (
        f"{intro}\n\n"
        + "\n".join(lines)
        + "\n\nAsk me to go deeper on any of it — your projects, your skills, "
        "or what you're working on right now."
    )


def _profile_topic_answer(label: str, facts: list[dict[str, Any]]) -> str:
    items = _profile_buckets(facts).get(label, [])
    if not items:
        return "I don't have anything saved on that yet."
    intro = _PROFILE_TOPIC_INTROS.get(label, "Here's what I have:")
    return f"{intro} {' '.join(items)}"


def _profile_answer(prompt: str) -> str | None:
    """Answer questions about the user from the notes they saved about themselves."""
    normalized = _app()._normalize_command(prompt).lower()
    if not normalized:
        return None
    overview = any(
        pattern.search(normalized) for pattern in _PROFILE_QUESTION_PATTERNS
    )
    topic = None if overview else _profile_topic(normalized)
    if not overview and topic is None:
        return None

    facts = _user_fact_memories()
    if not facts:
        return (
            "I don't have anything saved about you yet. Add a few details to "
            "your memory list — your name, what you work on, how you like to be "
            "helped — and I'll keep them in mind."
        )
    if topic is None:
        return _profile_overview(facts)
    name = _user_name(facts)
    if topic == "The basics" and name and re.search(r"\bname\b", normalized):
        return f"You're {name}."
    return _profile_topic_answer(topic, facts)


def _memories_for_prompt(prompt: str) -> list[dict[str, Any]]:
    """Semantic matches first, topped up with the most recent saved memories."""
    found = _app().memory_store.search_memories(prompt)
    if len(found) >= _app().MAX_RETRIEVED_MEMORIES:
        return found
    seen = {item["id"] for item in found}
    recent = [
        item for item in _app().memory_store.list_memories() if item["id"] not in seen
    ]
    return [*found, *recent[: _app().MAX_RETRIEVED_MEMORIES - len(found)]]


_GREETING_PATTERN = re.compile(
    r"(?:hi|hello|hey|yo|hiya|good\s+(?:morning|afternoon|evening)|morning|gm)"
    r"[\s!.,]*(?:orbit|spidey|s\.p\.i\.d\.e\.y|buddy|bro|dude|mate)?[\s!.,]*",
    re.IGNORECASE,
)

_ASSISTANT_INTRO_PATTERN = re.compile(
    r"(?:what(?:'s|s| is) your name|who are you|what are you|introduce yourself)",
    re.IGNORECASE,
)

_MORNING_PHRASE = re.compile(r"\b(?:good\s+morning|morning|gm)\b", re.IGNORECASE)
_last_morning_brief_date: str | None = None


def _morning_brief(normalized: str) -> str | None:
    """On 'good morning' / 'morning' / 'gm', return an inbox + day summary."""
    global _last_morning_brief_date
    from datetime import datetime

    if not _MORNING_PHRASE.search(normalized):
        return None
    today = datetime.now(_app().LOCAL_TIMEZONE).date().isoformat()

    parts: list[str] = []
    try:
        from services import gmail_reader

        if gmail_reader.is_configured():
            parts.append(gmail_reader.email_digest_text(max_results=6))
    except Exception:
        _app().LOGGER.debug("Morning email digest skipped", exc_info=True)

    try:
        open_tasks = _app().memory_store.list_tasks(include_completed=False)
        habits = _app().memory_store.list_habits()
        pending_habits = [h for h in habits if today not in (h.get("completed_dates") or [])]
        if open_tasks or pending_habits:
            parts.append(
                f"🗓️ Today: **{len(open_tasks)}** open task{'s' if len(open_tasks) != 1 else ''}"
                f" and **{len(pending_habits)}** habit{'s' if len(pending_habits) != 1 else ''} to check off."
            )
    except Exception:
        _app().LOGGER.debug("Morning task summary skipped", exc_info=True)

    if not parts:
        return None
    _last_morning_brief_date = today
    return "\n\n".join(parts)


def _greeting_answer(prompt: str) -> str | None:
    """Answer bare greetings instantly so a model load never delays hello."""
    normalized = _app()._normalize_command(prompt)
    if not _GREETING_PATTERN.fullmatch(normalized):
        return None
    name = _user_name(_user_fact_memories())
    first = name.split()[0] if name else ""
    brief = _morning_brief(normalized)
    if brief:
        hello = f"Good morning{', ' + first if first else ''}! ☀️"
        return f"{hello}\n\n{brief}"
    salutation = f"Hey {first}!" if first else "Hey!"
    return (
        f"{salutation} I'm ORBIT. Ask me about your tasks, habits, "
        "reminders, learning progress, emails, or anything you've saved."
    )


def _assistant_intro_answer(prompt: str) -> str | None:
    """Introduce ORBIT without asking the small model to guess its name."""
    normalized = _app()._normalize_command(prompt)
    if not _ASSISTANT_INTRO_PATTERN.fullmatch(normalized):
        return None
    return (
        "I'm ORBIT, your local assistant. I manage tasks, habits, and "
        "reminders, remember what you tell me, and answer questions — all on "
        "your own machine."
    )


_PAGE_BY_PROVIDER = {
    "local-habit-manager": "habits",
    "local-task-manager": "todos",
    "local-scheduler": "reminders",
    "local-learning": "learning",
    "local-memory": "reminders",
}

_PAGE_ROUTES = {
    "tasks": "/todos",
    "todos": "/todos",
    "habits": "/habits",
    "reminders": "/reminders",
    "memories": "/reminders",
    "notes": "/reminders",
    "dashboard": "/dashboard",
    "learning": "/learning",
    "analytics": "/analytics",
    "settings": "/settings",
}

def _route_for_page(page: str) -> str:
    return _PAGE_ROUTES.get(page, f"/{page}")

_PAGE_ALIASES = {
    "tasks": ("task", "tasks", "todo", "todos", "to-do", "to-dos", "to do", "to dos"),
    "habits": ("habit", "habits"),
    "reminders": ("reminder", "reminders", "reminders and memory", "recall"),
    "dashboard": ("dashboard", "home", "overview"),
    "chat": ("chat", "assistant"),
    "research": ("research", "web research"),
    "memories": ("memory", "memories", "notes"),
    "learning": ("learning", "learning tracker", "roadmap", "roadmaps", "study", "study plan"),
    "analytics": ("analytics", "stats", "telemetry", "progress"),
    "settings": ("settings", "setting", "preferences", "config", "configuration"),
}

_NAVIGATE_PATTERN = re.compile(
    r"^(?:(?:go|move|switch|navigate|jump|head)\s+(?:over\s+)?(?:to|into)"
    r"|goto|take\s+me\s+(?:to|into)|open|bring\s+up|show(?:\s+me)?)"
    r"\s+(?:the\s+|my\s+)?(?P<target>[a-z\- ]+?)"
    r"(?:\s+(?:page|section|tab|screen|view|area|popup|pop-up|panel))?$",
    re.IGNORECASE,
)


def _parse_navigation(prompt: str) -> str | None:
    """Return a page key for 'open learning' / 'go to tasks' style commands, else None."""
    normalized = _app()._normalize_command(prompt)
    match = _NAVIGATE_PATTERN.match(normalized)
    if not match:
        return None
    target = re.sub(r"\s+", " ", match.group("target").strip().lower())
    # Keep "show my tasks / habits / reminders / memories / notes / learning" routed to
    # their rich list handlers so the user gets actual data instead of just "Opening ...".
    if normalized.lower().startswith("show") and target in {
        "task", "tasks", "todo", "todos", "to-do", "to-dos", "to do", "to dos",
        "habit", "habits",
        "reminder", "reminders",
        "memory", "memories", "notes",
        "learning", "roadmap", "roadmaps", "learning tracker", "study plan",
    }:
        return None
    for page, words in _PAGE_ALIASES.items():
        if target in words:
            return page
    return None


def _page_for_provider(provider: str) -> str | None:
    if provider.startswith("local-navigate:"):
        return provider.split(":", 1)[1]
    return _PAGE_BY_PROVIDER.get(provider)


