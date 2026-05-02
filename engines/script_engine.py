"""
engines/script_engine.py — LLM-powered script generator.
Tries Gemini → NVIDIA NIM → rule-based fallback.
"""
import re
import json
import logging
import asyncio
from typing import Dict, List, Any, Optional

import httpx

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import GEMINI_API_KEY, NVIDIA_API_KEY

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a viral short-form video scriptwriter for TikTok/Reels.
Given a raw fact, create an engaging 45-55 second script.

Return ONLY valid JSON — no explanation, no markdown fences:
{
  "narration": "Full narration spoken aloud. 100-120 words. Natural, conversational, engaging. Expand on the fact with context, a surprising angle, and a call-to-action at the end. NO symbols like * # @ or special chars. Plain sentences only.",
  "headline": "Punchy headline max 6 words ALL CAPS",
  "lines": [
    {"text": "Short display phrase max 9 words", "duration": 4.0},
    {"text": "Next phrase", "duration": 3.5}
  ],
  "youtube_title": "SEO YouTube title",
  "description": "2 sentence description",
  "hashtags": ["tag1", "tag2", "tag3", "tag4", "tag5"]
}

Strict rules:
- narration: 100-120 plain words, no special symbols, natural speech rhythm
- lines: 5-8 items matching the narration, each max 9 words, total ~50 seconds
- Expand the fact: add why it matters, a comparison, and end with a hook
- NO markdown, NO asterisks, NO hash symbols anywhere
- JSON only — nothing else"""


def _sanitize_narration(text: str) -> str:
    """Strip symbols that TTS reads aloud."""
    import re
    text = re.sub(r"<[^>]+>", " ", text)        # HTML/XML
    text = re.sub(r"[*_~`#@\\|{}\[\]^]", "", text)  # markdown/code symbols
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _rule_based_script(raw_text: str, category: str) -> Dict:
    """Fallback: build an expanded script without an LLM."""
    import re
    text = raw_text.strip().rstrip(".")
    sentences = re.split(r'(?<=[.!?])\s+', text)

    # Build 100-120 word narration by expanding short content
    base_words = text.split()
    narration_words = base_words[:100]

    # If source is short (<50 words), pad with contextual framing sentences
    if len(base_words) < 50:
        openers = [
            f"Here is a mind-blowing {category} fact that most people have never heard of.",
            "Scientists and researchers have been studying this for years.",
            "The implications of this discovery continue to surprise experts worldwide.",
            "Once you know this, you will never look at the world the same way again.",
            f"Follow for more incredible {category} facts every day.",
        ]
        combined = text + " " + " ".join(openers)
        narration_words = combined.split()[:110]

    narration = " ".join(narration_words)
    narration = _sanitize_narration(narration)

    # Build display lines (max 9 words each, 5-8 lines)
    lines = []
    for s in sentences[:8]:
        s = s.strip().strip(".,;:*#")
        if not s:
            continue
        words_s = s.split()
        if len(words_s) <= 9:
            lines.append({"text": s, "duration": max(3.0, len(words_s) * 0.40)})
        else:
            mid = len(words_s) // 2
            lines.append({"text": " ".join(words_s[:mid]), "duration": max(3.0, mid * 0.40)})
            lines.append({"text": " ".join(words_s[mid:]), "duration": max(3.0, (len(words_s)-mid) * 0.40)})

    if not lines:
        lines = [{"text": text[:60].strip(), "duration": 5.0}]
    lines = lines[:8]

    hl_words = narration.split()[:5]
    headline = " ".join(hl_words).upper()

    return {
        "narration": narration,
        "headline":  headline,
        "lines":     lines,
        "youtube_title": f"Mind-Blowing {category.title()} Fact You Never Knew",
        "description":   f"Discover this incredible {category} fact. {text[:120]}",
        "hashtags":  [category, "facts", "didyouknow", "viral", "learnontiktok"],
    }


async def _gemini_script(raw_text: str, category: str) -> Optional[Dict]:
    if not GEMINI_API_KEY:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": f"Category: {category}\nContent: {raw_text}\n\n{SYSTEM_PROMPT}"}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 600},
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        # Strip possible markdown fences
        text = re.sub(r"```json|```", "", text).strip()
        return json.loads(text)


async def _nvidia_script(raw_text: str, category: str) -> Optional[Dict]:
    if not NVIDIA_API_KEY:
        return None
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {NVIDIA_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "meta/llama-3.1-8b-instruct",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Category: {category}\nContent: {raw_text}"},
        ],
        "max_tokens": 600,
        "temperature": 0.7,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"]
        text = re.sub(r"```json|```", "", text).strip()
        return json.loads(text)


class ScriptEngine:

    async def generate(self, raw_text: str, category: str = "facts") -> Dict:
        """Generate structured script. Returns dict with narration, lines, metadata."""
        result = None
        # Try LLMs in order — NVIDIA first (user preference), Gemini as fallback
        for attempt_fn in [_nvidia_script, _gemini_script]:
            try:
                result = await attempt_fn(raw_text, category)
                if result and "narration" in result:
                    logger.info(f"[ScriptEngine] Script via {attempt_fn.__name__}")
                    break
            except Exception as e:
                logger.warning(f"[ScriptEngine] {attempt_fn.__name__} failed: {e}")

        if not result:
            logger.info("[ScriptEngine] Using rule-based fallback")
            result = _rule_based_script(raw_text, category)

        # Always sanitize
        if "narration" in result:
            result["narration"] = _sanitize_narration(result["narration"])
            # Enforce 120-word cap (keeps video under 55 seconds)
            words = result["narration"].split()
            if len(words) > 125:
                result["narration"] = " ".join(words[:125])
                logger.info("[ScriptEngine] Narration trimmed to 125 words")
            # Enforce minimum: expand if too short
            elif len(words) < 60:
                extra = f" This fascinating {category} fact is just one of many incredible things waiting to be discovered. Follow for more amazing content every day."
                result["narration"] = result["narration"].rstrip(".") + ". " + extra.strip()
                logger.info(f"[ScriptEngine] Narration expanded (was {len(words)} words)")

        # Sanitize caption lines
        for line in result.get("lines", []):
            if "text" in line:
                line["text"] = _sanitize_narration(line["text"])

        return result
