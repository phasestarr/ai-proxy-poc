from app.config.chat import GENERATED_CHAT_HISTORY_TITLE_MAX_CHARS


def build_title_from_prompt(prompt: str) -> str:
    candidate = " ".join(prompt.strip().split())
    if not candidate:
        return "New chat"
    return candidate[:GENERATED_CHAT_HISTORY_TITLE_MAX_CHARS]


def normalize_history_title(title: str | None) -> str | None:
    if title is None:
        return None
    candidate = " ".join(title.strip().split())
    return candidate or None
