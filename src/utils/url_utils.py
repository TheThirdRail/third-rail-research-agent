"""URL utility functions shared across tools and services."""

from urllib.parse import urlparse


def extract_domain(url_or_domain: str) -> str:
    """Extract a normalised domain from a URL or bare domain string.

    Handles full URLs, bare domains, ``www.`` prefixes, and invalid input.

    Returns:
        Lower-cased domain with leading ``www.`` stripped, or the cleaned
        input string if parsing fails.
    """
    if not url_or_domain:
        return ""

    text = url_or_domain.strip()

    # If it looks like a URL, parse it
    if "://" in text or text.startswith("//"):
        try:
            host = urlparse(text).netloc
            if host:
                return host.lower().removeprefix("www.")
        except ValueError:
            return text.lower().removeprefix("www.")

    # Bare domain or fallback — strip scheme-less www. prefix
    return text.lower().removeprefix("www.")
