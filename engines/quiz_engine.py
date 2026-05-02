"""
engines/quiz_engine.py — LLM-powered quiz and puzzle generator.

Generates structured quiz questions (4 options) and brain puzzles for video rendering.
Uses NVIDIA NIM → Gemini → rule-based fallback.
"""
import json
import logging
import random
import re
from typing import Dict, List, Optional

import httpx

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import NVIDIA_API_KEY, GEMINI_API_KEY

logger = logging.getLogger(__name__)

# ── Quiz prompt ────────────────────────────────────────────────────────────────
QUIZ_PROMPT = """You are a viral quiz video creator for TikTok/Reels.
Create ONE engaging multiple-choice quiz question for the given category.

Return ONLY valid JSON — no markdown, no explanation:
{
  "question": "Interesting question? (max 15 words)",
  "options": {
    "A": "First option",
    "B": "Second option",
    "C": "Third option",
    "D": "Fourth option"
  },
  "answer": "B",
  "explanation": "Brief 1-sentence explanation why the answer is correct.",
  "hook": "Catchy 6-word hook line to open the video",
  "cta": "Comment your answer below!",
  "narration": "Full TTS script: hook, read question, read all 4 options, reveal answer hint. 60-80 words. Plain text only, no symbols."
}

Rules:
- question must be factual, fun, surprising — not obvious
- options must all be plausible (no trick null options)
- answer must be one of A/B/C/D
- narration: say 'Option A', 'Option B', etc. End with 'Drop your answer in the comments!'
- NO markdown, NO asterisks, NO special symbols"""

# ── Puzzle prompt ──────────────────────────────────────────────────────────────
PUZZLE_PROMPT = """You are a viral visual puzzle creator for TikTok/Reels.
Create ONE engaging emoji-based visual puzzle for the given category.

Return ONLY valid JSON — no markdown, no explanation:
{
  "type": "emoji_math", 
  "puzzle": "🍎 + 🍎 = 10\\n🍎 + 🍌 = 7\\n🍌 + 🍇 = ??", 
  "answer": "4",
  "hint": "Apples are 5",
  "hook": "99% of people fail this!",
  "cta": "Comment your answer below!",
  "difficulty": "hard",
  "narration": "Are you a genius? Solve this emoji math puzzle! Drop your answer in the comments!"
}

Puzzle Types (Choose ONE):
1. "emoji_math": 3 lines of equations using emojis.
2. "guess_word": 3-5 emojis that represent a movie, phrase, or word (e.g., 🦇 + 👨 = Batman).
3. "odd_one": A string of 15 identical emojis and 1 slightly different emoji (e.g. 15 🥵 and 1 🥶).

Rules:
- MUST use actual emojis in the "puzzle" field.
- If emoji_math, use \\n to separate the 3 lines.
- NO markdown, NO asterisks, NO special characters in narration."""

# ── Fallback quizzes & puzzles ────────────────────────────────────────────────
FALLBACK_QUIZZES = {
    "space":       {"question":"Which planet has the most moons in our solar system?",
                    "options":{"A":"Jupiter","B":"Saturn","C":"Uranus","D":"Neptune"},
                    "answer":"B","explanation":"Saturn has 146 confirmed moons, the most of any planet."},
    "history":     {"question":"Which ancient wonder still stands today?",
                    "options":{"A":"Hanging Gardens","B":"Colossus","C":"Great Pyramid","D":"Lighthouse"},
                    "answer":"C","explanation":"The Great Pyramid of Giza is the only ancient wonder that survives."},
    "science":     {"question":"What percentage of the human body is water?",
                    "options":{"A":"45%","B":"55%","C":"60%","D":"75%"},
                    "answer":"C","explanation":"The average adult human body is about 60% water by weight."},
    "technology":  {"question":"What year was the first iPhone released?",
                    "options":{"A":"2005","B":"2007","C":"2008","D":"2010"},
                    "answer":"B","explanation":"Apple released the first iPhone on June 29, 2007."},
    "nature":      {"question":"Which animal has the longest lifespan?",
                    "options":{"A":"Tortoise","B":"Bowhead Whale","C":"Greenland Shark","D":"Koi Fish"},
                    "answer":"C","explanation":"Greenland sharks can live over 400 years, the longest of any vertebrate."},
    "default":     {"question":"What is the most spoken language in the world?",
                    "options":{"A":"Spanish","B":"English","C":"Hindi","D":"Mandarin"},
                    "answer":"D","explanation":"Mandarin Chinese has the most native speakers of any language."},
}

FALLBACK_PUZZLES = [
    {"type":"emoji_math","puzzle":"🍔 + 🍔 = 10\n🍔 + 🍟 = 8\n🍟 + 🥤 = ??","answer":"6","hint":"Burger is 5","difficulty":"medium"},
    {"type":"guess_word","puzzle":"🕷️ + 👨 = ?","answer":"Spider-Man","hint":"A famous superhero","difficulty":"easy"},
    {"type":"emoji_math","puzzle":"👟 + 👟 = 20\n👟 + 👔 = 15\n👔 + 🧢 = ??","answer":"10","hint":"Shoe is 10","difficulty":"hard"},
    {"type":"odd_one","puzzle":"🍎🍎🍎🍎\n🍎🍏🍎🍎\n🍎🍎🍎🍎","answer":"The green apple","hint":"Look in the middle","difficulty":"easy"}
]


async def _llm_request(prompt: str, user_msg: str) -> Optional[Dict]:
    """Try NVIDIA NIM then Gemini for JSON generation."""
    # NVIDIA NIM
    if NVIDIA_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(
                    "https://integrate.api.nvidia.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"},
                    json={
                        "model": "meta/llama-3.1-8b-instruct",
                        "messages": [
                            {"role": "system", "content": prompt},
                            {"role": "user",   "content": user_msg},
                        ],
                        "max_tokens": 500, "temperature": 0.8,
                    }
                )
                r.raise_for_status()
                text = r.json()["choices"][0]["message"]["content"]
                text = re.sub(r"```json|```", "", text).strip()
                return json.loads(text)
        except Exception as e:
            logger.warning(f"[QuizEngine] NVIDIA failed: {e}")

    # Gemini fallback
    if GEMINI_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
                    json={"contents": [{"parts": [{"text": f"{prompt}\n\n{user_msg}"}]}],
                          "generationConfig": {"temperature": 0.8, "maxOutputTokens": 500}},
                )
                r.raise_for_status()
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                text = re.sub(r"```json|```", "", text).strip()
                return json.loads(text)
        except Exception as e:
            logger.warning(f"[QuizEngine] Gemini failed: {e}")

    return None


class QuizEngine:

    async def generate_quiz(self, category: str) -> Dict:
        """Generate a quiz question with 4 options for the given category."""
        result = await _llm_request(QUIZ_PROMPT, f"Category: {category}")
        if result and "question" in result and "options" in result:
            logger.info(f"[QuizEngine] Quiz generated via LLM")
            return self._validate_quiz(result, category)

        # Fallback
        logger.info("[QuizEngine] Using fallback quiz")
        fb = FALLBACK_QUIZZES.get(category.lower(), FALLBACK_QUIZZES["default"]).copy()
        fb.setdefault("hook", f"Can you answer this {category} question?")
        fb.setdefault("cta",  "Comment your answer below!")
        q  = fb["question"]
        opts = fb["options"]
        fb.setdefault("narration",
            f"Let's see how smart you are! {q} "
            f"Option A: {opts['A']}. Option B: {opts['B']}. "
            f"Option C: {opts['C']}. Option D: {opts['D']}. "
            f"Think carefully! Drop your answer in the comments!")
        return fb

    async def generate_puzzle(self, category: str) -> Dict:
        """Generate a brain puzzle or riddle."""
        result = await _llm_request(PUZZLE_PROMPT, f"Category: {category}. Create a puzzle related to this topic.")
        if result and "puzzle" in result and "answer" in result:
            logger.info(f"[QuizEngine] Puzzle generated via LLM")
            return self._validate_puzzle(result)

        # Fallback
        logger.info("[QuizEngine] Using fallback puzzle")
        fb = random.choice(FALLBACK_PUZZLES).copy()
        fb.setdefault("hook", "Only 5% of people can solve this!")
        fb.setdefault("cta",  "Comment your answer below!")
        fb.setdefault("narration",
            f"Only the sharpest minds can solve this! Here is the puzzle: {fb['puzzle']} "
            f"Here is a hint: {fb['hint']}. "
            f"Can you figure it out? Drop your answer in the comments!")
        return fb

    def _validate_quiz(self, data: Dict, category: str) -> Dict:
        data.setdefault("hook", f"Test your {category} knowledge!")
        data.setdefault("cta",  "Comment your answer below!")
        data.setdefault("explanation", "")
        opts = data.get("options", {})
        for k in ["A","B","C","D"]:
            opts.setdefault(k, f"Option {k}")
        if data.get("answer") not in ["A","B","C","D"]:
            data["answer"] = "A"
        if "narration" not in data:
            q = data["question"]
            data["narration"] = (
                f"{data['hook']} {q} "
                f"Option A: {opts['A']}. Option B: {opts['B']}. "
                f"Option C: {opts['C']}. Option D: {opts['D']}. "
                f"Drop your answer in the comments!")
        return data

    def _validate_puzzle(self, data: Dict) -> Dict:
        data.setdefault("hook",       "Can you solve this?")
        data.setdefault("cta",        "Comment your answer below!")
        data.setdefault("hint",       "Think carefully!")
        data.setdefault("difficulty", "medium")
        data.setdefault("type",       "riddle")
        if "narration" not in data:
            data["narration"] = (
                f"{data['hook']} Here is the puzzle: {data['puzzle']} "
                f"Hint: {data['hint']}. Drop your answer in the comments!")
        return data
