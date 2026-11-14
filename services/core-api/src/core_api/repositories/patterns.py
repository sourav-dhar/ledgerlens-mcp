"""SQL pattern helpers shared by repositories."""


def contains(term: str) -> str:
    """An ILIKE pattern matching ``term`` anywhere, with its own wildcards made literal."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
