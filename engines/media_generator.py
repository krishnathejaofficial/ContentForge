"""
engines/media_generator.py — Multi-background fetcher with video clip support.

Features:
  - Downloads 4-6 images per category from Pexels + Pixabay
  - Downloads portrait video clips from Pexels Video API
  - Per-category BGM search with yt-dlp fallback
  - Smart LANCZOS center-crop to 1080×1920
"""
import io
import logging
import os
import random
import time
from pathlib import Path
from typing import List, Optional

import requests
from PIL import Image, ImageDraw, ImageFilter

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PEXELS_API_KEY, PIXABAY_API_KEY, OUTPUT_DIR, VIDEO_WIDTH, VIDEO_HEIGHT

logger = logging.getLogger(__name__)

# ── Category queries (2 queries per category for diversity) ───────────────────
CATEGORY_QUERIES = {
    "facts":        ["abstract colorful bokeh", "vibrant light particles"],
    "science":      ["science laboratory glowing", "molecular structure abstract"],
    "biology":      ["nature macro cells biology", "dna helix abstract"],
    "history":      ["ancient ruins architecture", "historical stone monument"],
    "technology":   ["technology neon circuit board", "futuristic digital city"],
    "space":        ["galaxy nebula stars cosmos", "space telescope deep field"],
    "psychology":   ["human mind brain abstract", "psychology silhouette thought"],
    "health":       ["wellness lifestyle minimal", "fitness green nature light"],
    "nature":       ["forest sunlight misty", "waterfall nature landscape"],
    "mathematics":  ["geometry abstract pattern", "fractal colorful mathematics"],
    "geography":    ["aerial city drone view", "earth landscape mountains"],
    "animals":      ["wildlife animal portrait", "nature macro insect"],
    "food":         ["gourmet food colorful", "restaurant aesthetic flat lay"],
    "sports":       ["athlete motion blur dynamic", "stadium lights sports"],
    "music":        ["music concert stage lights", "vinyl record studio"],
    "movies":       ["cinema dramatic lighting", "film strip dark aesthetic"],
    "books":        ["library books cozy", "reading vintage warm light"],
    "philosophy":   ["ancient columns philosophy", "contemplation silhouette mist"],
    "economics":    ["city financial district", "stock market abstract neon"],
    "politics":     ["government capitol building", "democratic flag architecture"],
    "environment":  ["green forest ecology", "ocean waves environment"],
    "architecture": ["modern architecture geometry", "building structure abstract"],
    "art":          ["art paint splash colorful", "gallery modern abstract"],
    "fashion":      ["fashion aesthetic minimal", "runway elegant light"],
    "travel":       ["travel adventure landscape", "city skyline destination"],
    "fitness":      ["gym workout fitness", "running athlete sunrise"],
    "nutrition":    ["healthy colorful vegetables", "organic food flat lay"],
    "language":     ["typography letters art", "book open light"],
    "mythology":    ["fantasy epic dramatic", "ancient temple mythology"],
    "inventions":   ["innovation laboratory light", "invention blueprint tech"],
}

BGM_QUERIES = {
    "space":        "space ambient no copyright music",
    "nature":       "nature ambient chill no copyright",
    "technology":   "electronic beats background no copyright",
    "psychology":   "calm piano ambient no copyright",
    "history":      "cinematic epic background no copyright",
    "art":          "aesthetic lofi background no copyright",
    "default":      "lofi chill background no copyright short",
}

GRADIENT_PALETTES = {
    "space":        [(5, 0, 20), (30, 0, 80), (80, 0, 120)],
    "nature":       [(10, 40, 10), (30, 100, 40), (60, 160, 60)],
    "technology":   [(0, 10, 30), (0, 40, 100), (0, 100, 160)],
    "health":       [(10, 60, 50), (30, 130, 90), (60, 180, 120)],
    "psychology":   [(30, 0, 60), (80, 20, 120), (120, 60, 160)],
    "history":      [(40, 25, 10), (90, 60, 30), (140, 100, 50)],
    "art":          [(60, 0, 60), (130, 30, 100), (180, 80, 140)],
    "default":      [(15, 10, 40), (50, 20, 90), (100, 50, 130)],
}


# ── Image helpers ──────────────────────────────────────────────────────────────

def _smart_crop(img: Image.Image) -> Image.Image:
    img = img.convert("RGB")
    w, h = img.size
    ratio = w / h
    target = VIDEO_WIDTH / VIDEO_HEIGHT
    if ratio > target:
        new_h, new_w = VIDEO_HEIGHT, int(VIDEO_HEIGHT * ratio)
    else:
        new_w, new_h = VIDEO_WIDTH, int(VIDEO_WIDTH / ratio)
    new_w, new_h = max(new_w, VIDEO_WIDTH), max(new_h, VIDEO_HEIGHT)
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - VIDEO_WIDTH) // 2
    top  = (new_h - VIDEO_HEIGHT) // 2
    return img.crop((left, top, left + VIDEO_WIDTH, top + VIDEO_HEIGHT))


def _gradient_fallback(category: str) -> Image.Image:
    palette = GRADIENT_PALETTES.get(category.lower(), GRADIENT_PALETTES["default"])
    c1, c2, c3 = palette
    img  = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT))
    draw = ImageDraw.Draw(img)
    half = VIDEO_HEIGHT // 2
    for y in range(half):
        t = y / half
        draw.line([(0, y), (VIDEO_WIDTH, y)], fill=tuple(int(c1[i] + (c2[i]-c1[i])*t) for i in range(3)))
    for y in range(half, VIDEO_HEIGHT):
        t = (y - half) / half
        draw.line([(0, y), (VIDEO_WIDTH, y)], fill=tuple(int(c2[i] + (c3[i]-c2[i])*t) for i in range(3)))
    return img.filter(ImageFilter.GaussianBlur(radius=4))


def _pexels_images(query: str, count: int = 5) -> List[bytes]:
    if not PEXELS_API_KEY:
        return []
    try:
        r = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "per_page": min(count * 2, 20), "orientation": "portrait"},
            timeout=12,
        )
        r.raise_for_status()
        photos = r.json().get("photos", [])
        random.shuffle(photos)
        result = []
        for photo in photos[:count]:
            src = photo["src"]
            url = src.get("large2x") or src.get("large") or src.get("original")
            try:
                ir = requests.get(url, timeout=20)
                ir.raise_for_status()
                result.append(ir.content)
            except Exception:
                pass
        return result
    except Exception as e:
        logger.warning(f"[Media] Pexels images failed: {e}")
        return []


def _pixabay_images(query: str, count: int = 3) -> List[bytes]:
    if not PIXABAY_API_KEY:
        return []
    try:
        r = requests.get(
            "https://pixabay.com/api/",
            params={
                "key": PIXABAY_API_KEY, "q": query,
                "image_type": "photo", "orientation": "vertical",
                "per_page": min(count * 2, 20), "safesearch": "true", "min_height": 1000,
            },
            timeout=12,
        )
        r.raise_for_status()
        hits = r.json().get("hits", [])
        random.shuffle(hits)
        result = []
        for hit in hits[:count]:
            try:
                ir = requests.get(hit["largeImageURL"], timeout=20)
                ir.raise_for_status()
                result.append(ir.content)
            except Exception:
                pass
        return result
    except Exception as e:
        logger.warning(f"[Media] Pixabay images failed: {e}")
        return []


def _pexels_video_url(query: str) -> Optional[str]:
    """Fetch a single portrait video download URL from Pexels Video API."""
    if not PEXELS_API_KEY:
        return None
    try:
        r = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "per_page": 10, "orientation": "portrait"},
            timeout=12,
        )
        r.raise_for_status()
        videos = r.json().get("videos", [])
        random.shuffle(videos)
        for video in videos[:5]:
            duration = video.get("duration", 999)
            if duration < 5 or duration > 30:
                continue
            # Pick best SD portrait file
            best = None
            for vf in video.get("video_files", []):
                if vf.get("quality") in ("sd", "hd") and vf.get("width", 0) <= 1080:
                    if best is None or vf.get("height", 0) > best.get("height", 0):
                        best = vf
            if best:
                return best["link"]
    except Exception as e:
        logger.warning(f"[Media] Pexels video failed: {e}")
    return None


class MediaGenerator:

    async def get_background(self, category: str) -> str:
        """Get a single background image (backward-compat)."""
        paths = await self.get_multiple_backgrounds(category, count=1)
        return paths[0] if paths else str(OUTPUT_DIR / "bg_fallback.jpg")

    async def get_multiple_backgrounds(self, category: str, count: int = 3) -> List[str]:
        """
        Download `count` background images in PARALLEL (asyncio.gather).
        Reduced default to 3 for speed. Falls back to gradient if APIs fail.
        """
        import asyncio
        queries = CATEGORY_QUERIES.get(category.lower(), ["abstract colorful background", "vibrant light bokeh"])
        # Collect all raw image bytes from both queries (mixed)
        all_raw: List[bytes] = []
        for query in queries:
            all_raw += _pexels_images(query, count=count)
            if len(all_raw) >= count:
                break
        if len(all_raw) < count:
            for query in queries:
                all_raw += _pixabay_images(query, count=count - len(all_raw))
                if len(all_raw) >= count:
                    break

        # Process + save images in parallel threads
        saved: List[str] = []
        lock  = asyncio.Lock()

        async def process_one(raw: bytes, idx: int):
            nonlocal saved
            try:
                img   = _smart_crop(Image.open(io.BytesIO(raw)))
                fname = str(OUTPUT_DIR / f"bg_{category}_{int(time.time()*1000)}_{idx}.jpg")
                await asyncio.to_thread(img.save, fname, "JPEG", quality=90)
                async with lock:
                    saved.append(fname)
                    logger.info(f"[Media] BG {len(saved)}: {Path(fname).name}")
            except Exception as e:
                logger.warning(f"[Media] Image {idx} failed: {e}")

        tasks = [process_one(raw, i) for i, raw in enumerate(all_raw[:count])]
        await asyncio.gather(*tasks)

        # Fill with gradients if not enough
        while len(saved) < max(1, count):
            img   = _gradient_fallback(category)
            fname = str(OUTPUT_DIR / f"bg_{category}_grad_{len(saved)}.jpg")
            img.save(fname, "JPEG", quality=90)
            saved.append(fname)
            logger.info(f"[Media] Gradient fallback added")

        logger.info(f"[Media] {len(saved)} backgrounds ready for '{category}'")
        return saved[:count]

    async def get_pexels_video_clip(self, category: str) -> Optional[str]:
        """Download a short portrait video clip from Pexels for the category."""
        queries = CATEGORY_QUERIES.get(category.lower(), ["abstract colorful"])
        for query in queries:
            url = _pexels_video_url(query)
            if url:
                try:
                    out_path = OUTPUT_DIR / f"vid_{category}_{int(time.time())}.mp4"
                    import asyncio
                    def dl():
                        r = requests.get(url, timeout=30, stream=True)
                        r.raise_for_status()
                        with open(out_path, "wb") as f:
                            for chunk in r.iter_content(chunk_size=1024*64):
                                f.write(chunk)
                    await asyncio.to_thread(dl)
                    if out_path.exists() and out_path.stat().st_size > 100_000:
                        logger.info(f"[Media] Video clip: {out_path.name}")
                        return str(out_path)
                except Exception as e:
                    logger.warning(f"[Media] Video download failed: {e}")
        return None

    async def get_free_bgm(self, category: str) -> Optional[str]:
        """Fetch free BGM via yt-dlp (cached per category). Falls back to procedural."""
        cache_path = OUTPUT_DIR / f"bgm_{category}.mp3"
        if cache_path.exists() and cache_path.stat().st_size > 100_000:
            logger.info(f"[Media] Using cached BGM: {cache_path.name}")
            return str(cache_path)

        logger.info(f"[Media] Fetching BGM for '{category}' via yt-dlp...")
        try:
            import yt_dlp
            search_q = BGM_QUERIES.get(category.lower(), BGM_QUERIES["default"])

            def download():
                opts = {
                    "format": "bestaudio/best",
                    "outtmpl": str(OUTPUT_DIR / f"bgm_{category}.%(ext)s"),
                    "postprocessors": [{"key": "FFmpegExtractAudio",
                                        "preferredcodec": "mp3", "preferredquality": "128"}],
                    "quiet": True, "no_warnings": True,
                    "max_downloads": 1, "default_search": "ytsearch5",
                    "match_filter": yt_dlp.utils.match_filter_func("duration <= 180"),
                    "socket_timeout": 15,
                }
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.extract_info(search_q, download=True)

            import asyncio
            await asyncio.to_thread(download)

            if cache_path.exists() and cache_path.stat().st_size > 50_000:
                logger.info(f"[Media] BGM downloaded: {cache_path.name}")
                return str(cache_path)
        except Exception as e:
            logger.warning(f"[Media] BGM yt-dlp failed: {e}")
        return None  # TTS engine will use procedural fallback
