"""HTML to clean text extractor using BeautifulSoup4."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

# Tags to remove before text extraction
_STRIP_TAGS = {"script", "style", "nav", "footer", "header", "aside"}

# Max output length in characters
MAX_TEXT_LENGTH = 8000


def extract_text(html: str) -> str:
    """Strip HTML and return clean text.

    - Removes script, style, nav, footer, header, aside tags
    - Extracts visible text with spaces between elements
    - Collapses multiple whitespace/newlines into single spaces
    - Limits output to 8000 characters
    - Returns empty string for empty/None input
    """
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # Remove unwanted tags entirely
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()

    # Get text with space separator
    text = soup.get_text(separator=" ", strip=True)

    # Collapse multiple whitespace/newlines into single spaces
    text = re.sub(r"\s+", " ", text).strip()

    # Limit output length
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]

    return text
