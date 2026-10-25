import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

PRIVATE_KEY = re.compile(
    r"(?:^|[^a-z0-9])(?:password|passwd|pwd|token|secret|authorization|cookie|"
    r"api[_-]?key|session[_-]?id|csrf|nonce)(?:$|[^a-z0-9])"
)
ASSIGNMENT = re.compile(
    r"(?i)(\b(?:password|passwd|pwd|(?:access[_-]?|refresh[_-]?|id[_-]?)?token|"
    r"(?:client[_-]?)?secret|api[_-]?key|authorization|session[_-]?id)\b[\"']?\s*[:=]\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s&,;<>}]+)"
)
URL = re.compile(r"https?://[^\s<>\"']+")


def private_key(value):
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value).casefold()
    return bool(PRIVATE_KEY.search(normalized))


def redact_url(value):
    try:
        parts = urlsplit(value)
        netloc = (
            "redacted@" + parts.netloc.rsplit("@", 1)[1] if "@" in parts.netloc else parts.netloc
        )
        query = parse_qsl(parts.query, keep_blank_values=True)
        fragment = (
            parse_qsl(parts.fragment, keep_blank_values=True) if "=" in parts.fragment else []
        )
        safe_query = [(key, "[redacted]" if private_key(key) else item) for key, item in query]
        safe_fragment = [
            (key, "[redacted]" if private_key(key) else item) for key, item in fragment
        ]
        return urlunsplit(
            (
                parts.scheme,
                netloc,
                parts.path,
                urlencode(safe_query) if safe_query != query else parts.query,
                urlencode(safe_fragment) if safe_fragment != fragment else parts.fragment,
            )
        )
    except ValueError:
        return "[invalid URL]"


def redact_text(value):
    value = URL.sub(lambda match: redact_url(match.group()), str(value))
    value = re.sub(r"(?i)\b(Bearer|Basic)\s+[a-z0-9._~+/-]+=*", r"\1 [redacted]", value)
    return ASSIGNMENT.sub(lambda match: match.group(1) + "[redacted]", value)


def redact(value):
    if isinstance(value, dict):
        return {
            key: "[redacted]" if private_key(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return redact_text(value) if isinstance(value, str) else value
