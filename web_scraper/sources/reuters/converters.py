"""Content converters for Reuters articles."""

from ...converters.markdown import html_to_markdown


def article_to_markdown(html: str) -> str:
    """Convert Reuters article HTML to Markdown.

    Args:
        html: HTML content from article body.

    Returns:
        Markdown formatted string.
    """
    return html_to_markdown(
        html,
        strip_tags=["figure", "aside", "nav", "footer"],
        heading_style="ATX",
    )
