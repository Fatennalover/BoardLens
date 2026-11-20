"""Descriptions shared with the Android engine catalog."""
from functools import cache
import json
from pathlib import Path


@cache
def profiles():
    path = Path(__file__).parent / 'assets/engines/engine-profiles.json'
    return json.loads(path.read_text(encoding='utf-8'))


def profile(identity):
    return profiles()['maia3-5m' if identity == 'maia3' else identity]


def summary(identity):
    info = profile(identity)
    return f"{info['style']} · {info['strength']}"


def description(identity):
    info = profile(identity)
    return f"{summary(identity)}\n{info['rating']}\n\n{info['description']}"
