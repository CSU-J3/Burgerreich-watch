"""Shared text helpers for Burgerreich collectors.

Normalization and the rule-based obs_type classifier, used by every collector so
there is one copy. Project-local — these operate on Burgerreich's
config.OBS_TYPE_KEYWORDS and are not reusable-core, so they stay here, not in
watchcore.
"""
from __future__ import annotations

import re

from . import config

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", text or "")).strip()


def classify(text: str) -> str:
    """Rule-based obs_type. Domain-first (naval/air/ground), then posture, else
    other. Matches the schema spec's worked example (a carrier *transit* is
    "naval", not "posture")."""
    low = text.lower()
    for obs_type, keywords in config.OBS_TYPE_KEYWORDS.items():
        if any(kw in low for kw in keywords):
            return obs_type
    return "other"
