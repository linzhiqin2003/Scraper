"""HTML to Markdown conversion utilities."""

from typing import Optional

from bs4 import BeautifulSoup
from markdownify import markdownify as md


def html_to_markdown(
    html: str,
    strip_tags: Optional[list] = None,
    heading_style: str = "ATX",
) -> str:
    """Convert HTML content to Markdown.

    Args:
        html: HTML content string.
        strip_tags: List of tag names to remove before conversion.
        heading_style: Heading style ('ATX' for #, 'SETEXT' for underlines).

    Returns:
        Markdown formatted string.
    """
    if not html:
        return ""

    # Parse HTML
    soup = BeautifulSoup(html, "html.parser")

    # Remove unwanted tags
    if strip_tags:
        for tag in strip_tags:
            for element in soup.find_all(tag):
                element.decompose()

    # Remove script and style tags by default
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()

    # Convert to markdown
    markdown = md(
        str(soup),
        heading_style=heading_style,
        strip=["script", "style"],
    )

    # Clean up extra whitespace
    lines = markdown.split("\n")
    cleaned_lines = []
    prev_empty = False

    for line in lines:
        line = line.rstrip()
        is_empty = not line

        # Skip consecutive empty lines
        if is_empty and prev_empty:
            continue

        cleaned_lines.append(line)
        prev_empty = is_empty

    return "\n".join(cleaned_lines).strip()


def extract_text(html: str) -> str:
    """Extract plain text from HTML.

    Args:
        html: HTML content string.

    Returns:
        Plain text without HTML tags.
    """
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # Remove script and style tags
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()

    return soup.get_text(separator=" ", strip=True)
