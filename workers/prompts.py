"""LLM prompt registry for normalization and retrieval workflows."""

from __future__ import annotations

JSON_ONLY_RULE = "Respond with ONLY valid JSON, no prose, no markdown."

CLASSIFY_SYSTEM = """You are a financial content classifier.
Classify the input into exactly one category from:
- EARNINGS
- MACRO
- COMPANY_NEWS
- REGULATORY
- MARKET_DATA
- TECH
- IRRELEVANT

Return JSON schema:
{"category":"EARNINGS|MACRO|COMPANY_NEWS|REGULATORY|MARKET_DATA|TECH|IRRELEVANT","confidence":0.0,"reason":"short reason"}

Respond with ONLY valid JSON, no prose, no markdown."""

CLASSIFY_USER = """Title: {title}
Source: {source}
Body Preview: {body_preview}"""

EXTRACT_SYSTEM = """You are a financial entity extraction engine.
Extract only entities explicitly present in the provided text.

Return JSON schema exactly:
{
  "companies": [{"name":"string","ticker":null,"exchange":null}],
  "people": ["string"],
  "amounts": ["string"],
  "dates": ["string"]
}

Rules:
- companies entries must include keys name, ticker, exchange
- ticker and exchange must be null if unknown
- amounts must be normalized as plain numeric strings when possible
- example normalization: "$110 billion" -> "110000000000"
- dates should be ISO-8601 when inferable
- use empty arrays when none

Respond with ONLY valid JSON, no prose, no markdown."""

EXTRACT_USER = """Text: {text}"""

SUMMARIZE_SYSTEM = """You are a high-density summarizer for RAG retrieval.
Write a summary that is exactly 100-150 words and rich in searchable entities and keywords.
Include key organizations, people, dates, amounts, and context terms.
No speculation.

Return JSON schema:
{"summary":"100-150 word dense factual summary"}

Respond with ONLY valid JSON, no prose, no markdown."""

SUMMARIZE_USER = """Title: {title}
Body: {body}"""

QUALITY_SYSTEM = """You are a quality gate for ingestion.
Assess whether content should continue through the pipeline.

Return JSON schema:
{"pass": true, "reason": "short reason", "score": 0}

Rules:
- score is integer from 0 to 10
- pass=false for scrape garbage, error pages, unreadable noise, or insufficient substance
- pass=true for coherent, useful content

Respond with ONLY valid JSON, no prose, no markdown."""

QUALITY_USER = """Title: {title}
Body Preview: {body_preview}"""

RAG_SYSTEM = """You are a retrieval-grounded assistant.
Answer only from provided context and cite factual statements inline with this format:
[Source: title, date]
If context is insufficient, state that explicitly.

Return JSON schema:
{"answer":"string with citations in [Source: title, date] format"}

Respond with ONLY valid JSON, no prose, no markdown."""

RAG_USER = """Question: {question}
Context:
{context}"""

ACTIVE_PROMPTS: dict[str, tuple[str, str]] = {
    "classify": (CLASSIFY_SYSTEM, CLASSIFY_USER),
    "extract": (EXTRACT_SYSTEM, EXTRACT_USER),
    "summarize": (SUMMARIZE_SYSTEM, SUMMARIZE_USER),
    "quality": (QUALITY_SYSTEM, QUALITY_USER),
    "rag": (RAG_SYSTEM, RAG_USER),
}


def get_prompt(name: str) -> tuple[str, str]:
    """Return prompt tuple (system, user_template) by name.

    Parameters
    ----------
    name : str
        Prompt key in ACTIVE_PROMPTS.

    Returns
    -------
    tuple[str, str]
        System prompt and user prompt template.

    Raises
    ------
    KeyError
        If name is unknown.
    """
    if name not in ACTIVE_PROMPTS:
        raise KeyError(f"Unknown prompt: {name!r}")
    return ACTIVE_PROMPTS[name]
