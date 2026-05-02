"""
main.py — ContentForge FastAPI web application.
Provides a browser-based UI to generate short-form video reels.
"""
import asyncio
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Optional

import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS

import uvicorn
from fastapi import FastAPI, Form, Request, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import sys
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    CATEGORIES, AVAILABLE_FONTS, AVAILABLE_VOICES,
    OUTPUT_DIR, DEFAULT_VOICE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("contentforge")

app = FastAPI(title="ContentForge", version="1.0.0")

# Mount static files
OUTPUT_DIR.mkdir(exist_ok=True)
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")

# Jinja2 templates
templates = Jinja2Templates(directory="templates")

# ─── In-memory job tracker ────────────────────────────────────────────────────
jobs: dict = {}  # job_id → {"status", "progress", "result", "error"}


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request":    request,
            "categories": CATEGORIES,
            "fonts":      AVAILABLE_FONTS,
            "voices":     AVAILABLE_VOICES,
        }
    )


@app.post("/generate")
async def generate_reel(
    background_tasks: BackgroundTasks,
    category:   str  = Form("facts"),
    voice:      str  = Form(DEFAULT_VOICE),
    font:       str  = Form("Inter-Bold.ttf"),
    use_bgm:    bool = Form(False),
    video_type: str  = Form("reel"),   # 'reel' | 'quiz' | 'puzzle'
):
    job_id = f"job_{int(time.time() * 1000)}"
    jobs[job_id] = {"status": "queued", "progress": "Starting...", "result": None, "error": None}
    if video_type in ("quiz", "puzzle"):
        background_tasks.add_task(_run_quiz_pipeline, job_id, category, voice, video_type)
    else:
        background_tasks.add_task(_run_pipeline, job_id, category, voice, font, use_bgm)
    return JSONResponse({"job_id": job_id})


@app.get("/status/{job_id}")
async def job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    return JSONResponse(job)


@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(
        str(file_path),
        media_type="video/mp4" if filename.endswith(".mp4") else "application/zip",
        filename=filename,
    )


@app.get("/download-package/{job_id}")
async def download_package(job_id: str):
    """Download the full ZIP package (video + captions + metadata)."""
    job = jobs.get(job_id)
    if not job or not job.get("result"):
        return JSONResponse({"error": "Job not complete"}, status_code=404)

    from utils.download_manager import create_download_package
    zip_path = create_download_package(job["result"]["video_path"], job["result"])
    return FileResponse(zip_path, media_type="application/zip", filename=Path(zip_path).name)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


# ─── Pipelines ────────────────────────────────────────────────────────────────

async def _run_quiz_pipeline(job_id: str, category: str, voice: str, video_type: str):
    """Pipeline for quiz and puzzle video generation."""
    def progress(msg: str):
        jobs[job_id]["progress"] = msg
        logger.info(f"[{job_id}] {msg}")

    try:
        jobs[job_id]["status"] = "running"

        # Step 1: Generate quiz / puzzle content
        from engines.quiz_engine import QuizEngine
        qe = QuizEngine()
        if video_type == "quiz":
            progress("🧠 Generating quiz question...")
            data = await qe.generate_quiz(category)
        else:
            progress("🧩 Generating brain puzzle...")
            data = await qe.generate_puzzle(category)

        # Step 2: Background images
        progress("🖼️ Downloading background...")
        from engines.media_generator import MediaGenerator
        media    = MediaGenerator()
        bg_paths = await media.get_multiple_backgrounds(category, count=2)

        # Step 3: Generate TTS narration
        progress("🎙️ Generating voiceover...")
        from engines.tts_engine import generate_voiceover, clean_text_for_tts
        narration   = clean_text_for_tts(data.get("narration", data.get("puzzle", "")))
        tts_result  = await generate_voiceover(narration, voice=voice, use_voice=True)
        audio_path  = tts_result[0] if isinstance(tts_result, tuple) else tts_result

        # Step 4: Compose quiz/puzzle video
        progress(f"🎬 Rendering {video_type} video...")
        from engines.quiz_composer import compose_quiz_video
        import anyio
        out_path = str(OUTPUT_DIR / f"{video_type}_{category}_{int(time.time())}.mp4")
        await anyio.to_thread.run_sync(
            compose_quiz_video, data, bg_paths, audio_path, out_path, video_type
        )

        result = {
            "video_path": out_path,
            "video_url":  f"/output/{Path(out_path).name}",
            "category":   category,
            "video_type": video_type,
            "data":       data,
            "hashtags":   [video_type, category, "quiz", "didyouknow", "viral"],
        }
        jobs[job_id].update({"status": "done", "result": result, "progress": "✅ Done!"})

    except Exception as e:
        logger.error(f"[{job_id}] Quiz pipeline failed", exc_info=True)
        jobs[job_id].update({"status": "error", "error": str(e), "progress": f"❌ {e}"})

async def _run_pipeline(
    job_id: str,
    category: str,
    voice: str,
    font: str,
    use_bgm: bool,
):
    def progress(msg: str):
        jobs[job_id]["progress"] = msg
        logger.info(f"[{job_id}] {msg}")

    try:
        jobs[job_id]["status"] = "running"

        # Step 1: Fetch content
        progress("📰 Fetching content...")
        from engines.content_fetcher import ContentFetcher
        fetcher = ContentFetcher()
        raw = fetcher.fetch_content(category)

        # Step 2: Generate script
        progress("✍️ Generating script with AI...")
        from engines.script_engine import ScriptEngine
        engine = ScriptEngine()
        script = await engine.generate(raw["text"], category)

        # Step 3: Download 3 diverse background images (parallel fetch)
        progress("🖼️ Downloading background images...")
        from engines.media_generator import MediaGenerator
        media    = MediaGenerator()
        bg_paths = await media.get_multiple_backgrounds(category, count=3)
        logger.info(f"[Pipeline] {len(bg_paths)} backgrounds ready")

        # Step 4: Fetch BGM (yt-dlp cached; tts_engine uses procedural fallback if None)
        bgm_path = None
        if use_bgm:
            progress("🎵 Fetching background music...")
            bgm_path = await media.get_free_bgm(category)
            progress("🎵 Music ready!" if bgm_path else "🎵 Using built-in procedural BGM")

        # Step 4b: Generate voiceover with sentence-sync captions
        progress("🎙️ Generating ultra-realistic voiceover...")
        from engines.tts_engine import generate_voiceover
        tts_result = await generate_voiceover(
            script["narration"],
            voice=voice,
            use_voice=True,
            bgm_path=bgm_path,
        )
        audio_path, timed_captions = tts_result if isinstance(tts_result, tuple) else (tts_result, [])
        caption_lines = timed_captions if timed_captions else script.get("lines", [])
        logger.info(f"[Pipeline] {len(caption_lines)} caption lines (synced={bool(timed_captions)})")

        # Step 5: Compose video with multi-background, particles, vignette, animations
        progress("🎬 Composing cinematic video (1-3 min)...")
        from engines.composer import compose_reel
        import anyio
        timestamp = int(time.time())
        out_path  = str(OUTPUT_DIR / f"reel_{category}_{timestamp}.mp4")

        await anyio.to_thread.run_sync(
            compose_reel,
            bg_paths,          # ← list of 5 backgrounds
            audio_path,
            caption_lines,
            font,
            out_path,
            script.get("headline")
        )

        # Step 6: Format for platforms
        progress("📲 Formatting for platforms...")
        from utils.platform_formatter import format_all_platforms
        platforms = format_all_platforms(
            script.get("youtube_title", ""),
            script.get("description", ""),
            script.get("hashtags", []),
        )

        # Done
        result = {
            "video_path": out_path,
            "video_url": f"/output/{Path(out_path).name}",
            "category": category,
            "source": raw.get("source", ""),
            "raw_text": raw["text"],
            "script": script,
            "platforms": platforms,
            "hashtags": script.get("hashtags", []),
        }
        jobs[job_id]["status"] = "done"
        jobs[job_id]["result"] = result
        jobs[job_id]["progress"] = "✅ Done!"

    except Exception as e:
        logger.error(f"[{job_id}] Pipeline failed", exc_info=True)
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
        jobs[job_id]["progress"] = f"❌ Error: {e}"


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
