"""Regex patterns for deterministic governance constraint extraction."""

ROLE_PATTERNS = [
    r"\bonly\s+(?P<role>[a-z][a-z_-]*)\s+may\b",
    r"\brequires?\s+(?P<role>[a-z][a-z_-]*?)\s+approval\b",
]

SEPARATION_PATTERNS = [
    r"\bmust\s+be\s+separate\b",
    r"\bseparation\s+of\s+duties\b",
]

THRESHOLD_PATTERNS = [
    r"\btransfers?\s+(?P<source>above\s+\$?(?P<amount>\d[\d,]*(?:\.\d+)?)\s*(?P<suffix>m|million)?)\b\s+requires?\s+(?:[a-z][a-z_-]*\s+)?approval\b",
]
