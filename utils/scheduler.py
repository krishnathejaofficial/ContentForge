"""
utils/scheduler.py — Simple daily content scheduler.
Can be triggered by a cron job or Render Cron Service.
"""
import random
import asyncio
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class DailyScheduler:
    """
    Picks a random category and kicks off the full pipeline.
    Designed to be called by a cron job: python -m utils.scheduler
    """

    def __init__(self):
        from config import CATEGORIES
        self.categories = CATEGORIES

    async def run_daily(self, category: Optional[str] = None):
        """Run the full pipeline for one category."""
        from engines.content_fetcher import ContentFetcher
        from engines.script_engine import ScriptEngine
        from engines.media_generator import MediaGenerator
        from engines.tts_engine import generate_voiceover
        from engines.composer import compose_reel
        from config import DEFAULT_VOICE, BGM_DIR, OUTPUT_DIR

        chosen = category or random.choice(self.categories)
        logger.info(f"[Scheduler] Starting daily generation — category: {chosen}")

        try:
            # 1. Fetch content
            fetcher = ContentFetcher()
            raw = fetcher.fetch_content(chosen)

            # 2. Generate script
            engine = ScriptEngine()
            script = await engine.generate(raw["text"], chosen)

            # 3. Get background image
            media = MediaGenerator()
            bg_path = await media.get_background(chosen)

            # 4. Generate voiceover
            bgm = str(BGM_DIR / "uplifting.mp3") if (BGM_DIR / "uplifting.mp3").exists() else None
            audio_path = await generate_voiceover(
                script["narration"],
                voice=DEFAULT_VOICE,
                bgm_path=bgm,
            )

            # 5. Compose video
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = str(OUTPUT_DIR / f"reel_{chosen}_{timestamp}.mp4")
            compose_reel(bg_path, audio_path, script["lines"], output_path=out_path)

            logger.info(f"[Scheduler] Done! Output: {out_path}")
            return out_path

        except Exception as e:
            logger.error(f"[Scheduler] Pipeline failed: {e}", exc_info=True)
            raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scheduler = DailyScheduler()
    asyncio.run(scheduler.run_daily())
