import re

def parse_habit_completion(prompt: str) -> str | None:
    norm = re.sub(r"\s+", " ", prompt.strip())

    # 1. Direct batch completion: all habits
    if re.fullmatch(
        r"(?:(?:i\s+)?(?:have\s+|'ve\s+)?(?:just\s+|already\s+)?(?:completed|complete|finished|finish|did|done|checked\s+off)|"
        r"mark|done\s+with)\s+(?:(?:the|my\s+all|all\s+my|all|my)\s+)*habits?"
        r"(?:\s+(?:as\s+)?(?:completed|complete|done|finished))?",
        norm,
        re.IGNORECASE,
    ) or re.fullmatch(
        r"(?:(?:all\s+)?(?:my\s+)?habits?|my\s+all\s+habits?)\s+(?:are\s+)?(?:completed|complete|done|finished)",
        norm,
        re.IGNORECASE,
    ):
        return "all habits"

    # 2. 'mark [my/the] habit <name> [as] completed/done'
    m = re.fullmatch(
        r"mark\s+(?:(?:the|my)\s+)?habit\s+(.+?)\s+(?:as\s+)?(?:completed|complete|done|finished)",
        norm,
        re.IGNORECASE,
    )
    if m:
        return re.sub(r"^(?:my|the)\s+", "", m.group(1).strip(), flags=re.IGNORECASE)

    # 3. 'mark [my/the] <name> habit [as] completed/done'
    m = re.fullmatch(
        r"mark\s+(?:(?:the|my)\s+)?(.+?)\s+habits?\s+(?:as\s+)?(?:completed|complete|done|finished)",
        norm,
        re.IGNORECASE,
    )
    if m:
        target = m.group(1).strip()
        if re.fullmatch(r"(?:my\s+all|all\s+my|all|my)?", target, re.IGNORECASE):
            return "all habits"
        return re.sub(r"^(?:my|the)\s+", "", target, flags=re.IGNORECASE)

    # 4. Conversational specific habit: 'i (have) completed [my] [habit] <name>'
    m = re.fullmatch(
        r"(?:i\s+)?(?:have\s+|'ve\s+)?(?:just\s+|already\s+)?(?:completed|complete|finished|finish|done|checked\s+off)\s+"
        r"(?:(?:the|my)\s+)?habit\s+(.+)",
        norm,
        re.IGNORECASE,
    )
    if m:
        return re.sub(r"^(?:my|the)\s+", "", m.group(1).strip(), flags=re.IGNORECASE)

    # 5. Conversational specific habit: 'i (have) completed [my] <name> habit'
    m = re.fullmatch(
        r"(?:i\s+)?(?:have\s+|'ve\s+)?(?:just\s+|already\s+)?(?:completed|complete|finished|finish|done|checked\s+off)\s+"
        r"(?:(?:the|my)\s+)?(.+?)\s+habits?",
        norm,
        re.IGNORECASE,
    )
    if m:
        target = m.group(1).strip()
        if re.fullmatch(r"(?:my\s+all|all\s+my|all|my)?", target, re.IGNORECASE):
            return "all habits"
        return re.sub(r"^(?:my|the)\s+", "", target, flags=re.IGNORECASE)

    # 6. Standard 'complete habit <name>'
    m = re.fullmatch(
        r"(?:complete|completed|finish|finished|done\s+with|mark\s+done|check\s+off)\s+"
        r"(?:(?:the|my)\s+)?habits?(?:\s+(.+))?",
        norm,
        re.IGNORECASE,
    )
    if m:
        target = m.group(1)
        if not target or target.strip().lower() in {"", "all", "all of them", "them", "both"}:
            return "all habits"
        return re.sub(r"^(?:my|the)\s+", "", target.strip(), flags=re.IGNORECASE)

    return None

test_cases = [
    ("mark habits completed", "all habits"),
    ("mark habits as completed", "all habits"),
    ("mark habits done", "all habits"),
    ("complete habits", "all habits"),
    ("completed habits", "all habits"),
    ("finish habits", "all habits"),
    ("habits completed", "all habits"),
    ("habits done", "all habits"),
    ("mark my habits completed", "all habits"),
    ("mark all habits completed", "all habits"),
    ("mark my all habits completed", "all habits"),
    ("i have just completed all my habits", "all habits"),
    ("mark habit Sleeping completed", "Sleeping"),
    ("complete habit Sleeping", "Sleeping"),
]

for p, expected in test_cases:
    actual = parse_habit_completion(p)
    assert actual == expected, f"Failed for {p!r}: expected {expected!r}, got {actual!r}"

print("All habit completion test cases passed!")
