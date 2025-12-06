"""Pydantic models for Vulnerability data and helpers to parse LLM output.

This module provides Pydantic models for vulnerability information and
a robust parser for converting LLM responses into typed Vuln objects.

Helper functions:
- _extract_json_from_text(text) -> str | None : returns a likely JSON substring
  from the given text (fenced code blocks, first balanced object, etc.).
- _repair_json_string(s) -> str : attempts to fix common LLM JSON formatting
  issues (remove comments, replace single quotes, remove trailing commas).
- parse_vuln_from_llm(text, *, raise_on_error=True) -> Vuln | None: top-level
  helper that extracts, repairs, loads JSON and validates into Vuln model.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from pydantic import BaseModel, ValidationError


class ImpactedSoftware(BaseModel):
    name: str
    before_version: str | None = None
    after_version: str | None = None


class Vuln(BaseModel):
    id: str
    description: str
    published: str
    v2score: float | None = None
    v31score: float | None = None

    additional_info: str | None = None

    impacts: list[ImpactedSoftware] | None = None


def _extract_json_from_text(text: str) -> Optional[str]:
    """Try to extract a JSON substring from a possibly noisy LLM output.

    The function attempts the following heuristics in order:
    1. Find a fenced code block indicating JSON (```json ... ``` or ``` ... ```)
    2. Find the first balanced JSON array starting with '[' or object starting with '{'
    3. If none found, return None
    """
    if not text:
        return None

    # 1) Fenced code block (prefer JSON-specifier but accept generic fences)
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()

    # 2) Balanced first JSON array or object (careful with nested brackets)
    # Prefer array '[' over object '{'
    array_start = text.find("[")
    object_start = text.find("{")
    
    if array_start == -1 and object_start == -1:
        return None
    
    # Choose the earlier one, prefer array if both at same position
    if array_start != -1 and (object_start == -1 or array_start <= object_start):
        start = array_start
        open_char, close_char = '[', ']'
    else:
        start = object_start
        open_char, close_char = '{', '}'

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _repair_json_string(s: str) -> str:
    """Attempt to repair common JSON issues LLMs produce.

    Fixes:
    - Remove single-line and block comments (// and /* */)
    - Convert single quoted keys/values to double quotes as a fallback
    - Remove trailing commas before } or ]
    - Strip surrounding markdown markers or backticks
    """
    if not s:
        return s

    # Remove Markdown fences if present
    s = re.sub(r"^\s*`+\s*", "", s)
    s = re.sub(r"`+\s*$", "", s)

    # Remove comments (// or /* */)
    s = re.sub(r"//.*?$", "", s, flags=re.MULTILINE)
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)

    # Remove trailing commas: `, }` -> `}` and `, ]` -> `]`
    s = re.sub(r",\s*([}\]])", r"\1", s)

    # If JSON decode still fails, LLMs commonly use single quotes; attempt a
    # conservative single->double quote replacement where appropriate. This
    # is a heuristic and may still fail for complex cases.
    single_quotes_likely = "'" in s and '"' not in s
    if single_quotes_likely:
        # Avoid replacing quotes inside nested JSON fragments; a simple
        # blanket replace is the pragmatic fallback here.
        s = s.replace("'", '"')

    return s


def parse_vuln_from_llm(text: str, *, raise_on_error: bool = True) -> Optional[Vuln]:
    """Parse an LLM response into a single Vuln object.

    This function is robust to common LLM output formats: pure JSON, JSON
    inside markdown code blocks, or verbose text that contains a JSON segment.
    It attempts to extract JSON, repair common issues, and finally validate the
    final payload against the Vuln Pydantic model.

    If `raise_on_error` is True, JSON parsing or validation errors are raised
    to help debugging; otherwise, None is returned on failure.
    
    Note: If you expect multiple vulnerabilities, use parse_vulns_from_llm instead.
    """
    vulns = parse_vulns_from_llm(text, raise_on_error=raise_on_error)
    if vulns:
        return vulns[0]
    return None


def parse_vulns_from_llm(text: str, *, raise_on_error: bool = True) -> Optional[list[Vuln]]:
    """Parse an LLM response into a list of Vuln objects.

    This function is robust to common LLM output formats: pure JSON array, JSON
    inside markdown code blocks, or verbose text that contains a JSON segment.
    It attempts to extract JSON, repair common issues, and finally validate the
    final payload against the Vuln Pydantic model.

    Supports both:
    - JSON array: [{...}, {...}]
    - Single JSON object: {...} (will be wrapped in a list)

    If `raise_on_error` is True, JSON parsing or validation errors are raised
    to help debugging; otherwise, None is returned on failure.
    """
    json_str = _extract_json_from_text(text)
    if not json_str:
        # Maybe the whole text is JSON, try to parse as-is
        json_str = text.strip()
    if not json_str:
        if raise_on_error:
            raise ValueError("No JSON found in LLM response")
        return None

    payload = None
    for attempt in range(2):
        try:
            payload = json.loads(json_str)
            break
        except json.JSONDecodeError:
            if attempt == 0:
                json_str = _repair_json_string(json_str)
                continue
            if raise_on_error:
                raise
            return None

    # Normalize to list
    if isinstance(payload, dict):
        payload = [payload]
    elif not isinstance(payload, list):
        if raise_on_error:
            raise ValueError(f"Expected JSON array or object, got {type(payload).__name__}")
        return None

    try:
        vulns = [Vuln.model_validate(item) for item in payload]
        return vulns
    except ValidationError:
        if raise_on_error:
            raise
        return None


__all__ = ["Vuln", "ImpactedSoftware", "parse_vuln_from_llm", "parse_vulns_from_llm"]