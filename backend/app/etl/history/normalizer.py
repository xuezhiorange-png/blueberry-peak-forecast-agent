import re
import unicodedata

from backend.app.etl.history.schemas import AliasConfig

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value)).strip()
    text = _WHITESPACE_RE.sub(" ", text)
    return text or None


def normalize_factory(value: object | None, aliases: AliasConfig) -> tuple[str | None, str | None]:
    normalized = normalize_text(value)
    if normalized is None:
        return None, None
    return normalized, aliases.aliases.get(normalized, normalized)


def normalize_variety(value: object | None, aliases: AliasConfig) -> tuple[str | None, str | None]:
    normalized = normalize_text(value)
    if normalized is None:
        return None, None
    for prefix in aliases.remove_prefixes:
        prefix_normalized = normalize_text(prefix)
        if prefix_normalized and normalized.startswith(prefix_normalized):
            normalized = normalized.removeprefix(prefix_normalized).strip()
    return normalized or None, aliases.aliases.get(normalized, normalized)
