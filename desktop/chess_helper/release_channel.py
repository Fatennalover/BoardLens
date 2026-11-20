"""Release source selected by the distributor at build time."""
from functools import lru_cache
import json
from pathlib import Path
import re

REPOSITORY_PATTERN = r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9][A-Za-z0-9_.-]*"


@lru_cache(maxsize=1)
def repository():
    config = Path(__file__).parent / "assets" / "engines" / "release-channel.json"
    try:
        channel = json.loads(config.read_text(encoding="utf-8")).get("repository")
    except (OSError, ValueError, AttributeError):
        return ""
    return channel if isinstance(channel, str) and re.fullmatch(REPOSITORY_PATTERN, channel) else ""


def releases():
    repo = repository()
    return f"https://github.com/{repo}/releases" if repo else ""
