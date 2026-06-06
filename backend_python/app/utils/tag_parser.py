# -*- coding: utf-8 -*-
"""
#tag extraction utility -- auto-extract tags from video title and description.

Usage:
  >>> extract_tags("Great weather today #travel #food #travel")
  ['travel', 'food']   <- deduplicated, preserving appearance order

Rules:
  - Starts with #
  - Followed by letters, digits, underscores (Unicode mode includes Chinese etc.)
  - Terminates on space, punctuation, or end of string
  - Same tag only kept once (first occurrence)

Regex explanation:
  #  -> match literal # character
  (  -> start capture group
  \w -> match letter, digit, underscore (re.UNICODE mode includes Chinese, Japanese etc.)
  +  -> at least one character
  )  -> end capture group

Why findall instead of finditer?
  With a capture group, findall returns captured content directly, saving manual .group(1).
"""
import re

# Compile once, reuse many times -- more efficient than re.findall(pattern, text) each call.
_TAG_RE = re.compile(r"#([\w]+)", re.UNICODE)


def extract_tags(text: str) -> list[str]:
    """
    Extract #tag list from text.

    Args:
      text: arbitrary text (video title + description concatenated)

    Returns:
      Deduplicated tag name list in appearance order (without # prefix)

    Algorithm:
      regex findall -> iterate -> check if seen -> add unseen to result
    """
    matches = _TAG_RE.findall(text)
    seen: set[str] = set()
    tags: list[str] = []
    for tag in matches:
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags
