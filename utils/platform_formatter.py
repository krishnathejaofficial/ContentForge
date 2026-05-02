"""
utils/platform_formatter.py — Format captions, hashtags, and metadata
for different social media platforms.
"""
from typing import Dict, List


PLATFORM_HASHTAG_LIMITS = {
    "instagram": 30,
    "tiktok": 20,
    "youtube": 10,
    "twitter": 5,
}

PLATFORM_CAPTION_LIMITS = {
    "instagram": 2200,
    "tiktok": 2200,
    "youtube": 5000,
    "twitter": 280,
}


def format_instagram(title: str, description: str, hashtags: List[str]) -> Dict:
    tags = hashtags[:PLATFORM_HASHTAG_LIMITS["instagram"]]
    caption = f"{title}\n\n{description}\n\n" + " ".join(f"#{t}" for t in tags)
    caption = caption[:PLATFORM_CAPTION_LIMITS["instagram"]]
    return {"caption": caption, "hashtags": tags}


def format_youtube(title: str, description: str, hashtags: List[str]) -> Dict:
    tags = hashtags[:PLATFORM_HASHTAG_LIMITS["youtube"]]
    desc = f"{description}\n\n" + " ".join(f"#{t}" for t in tags)
    return {
        "title": title[:100],
        "description": desc[:PLATFORM_CAPTION_LIMITS["youtube"]],
        "tags": tags,
    }


def format_tiktok(title: str, description: str, hashtags: List[str]) -> Dict:
    tags = hashtags[:PLATFORM_HASHTAG_LIMITS["tiktok"]]
    caption = f"{description} " + " ".join(f"#{t}" for t in tags)
    caption = caption[:PLATFORM_CAPTION_LIMITS["tiktok"]]
    return {"caption": caption, "hashtags": tags}


def format_all_platforms(title: str, description: str, hashtags: List[str]) -> Dict:
    return {
        "instagram": format_instagram(title, description, hashtags),
        "youtube":   format_youtube(title, description, hashtags),
        "tiktok":    format_tiktok(title, description, hashtags),
    }
