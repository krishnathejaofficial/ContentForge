"""
config.py — Central configuration for ContentForge.
All environment variables and path constants live here.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Explicitly tell MoviePy where ImageMagick is installed to prevent [WinError 2]
os.environ["IMAGEMAGICK_BINARY"] = r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"

load_dotenv()

# ─── API Keys ─────────────────────────────────────────────────────────────────
NEWS_API_KEY        = os.getenv("NEWS_API_KEY", "")
API_NINJAS_KEY      = os.getenv("API_NINJAS_KEY", "")
PEXELS_API_KEY      = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY     = os.getenv("PIXABAY_API_KEY", "")
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY", "")
NVIDIA_API_KEY      = os.getenv("NVIDIA_API_KEY", "")

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / os.getenv("OUTPUT_DIR", "output")
ASSETS_DIR = BASE_DIR / os.getenv("ASSETS_DIR", "assets")
FONTS_DIR  = ASSETS_DIR / "fonts"
BGM_DIR    = ASSETS_DIR / "bgm"
FACT_JSON  = ASSETS_DIR / "fact_datasets.json"

# Ensure output directory exists
OUTPUT_DIR.mkdir(exist_ok=True)

# ─── Video Settings ───────────────────────────────────────────────────────────
VIDEO_WIDTH  = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS    = 24

# ─── TTS Settings ─────────────────────────────────────────────────────────────
DEFAULT_VOICE       = "en-US-ChristopherNeural"   # Most human-like
DEFAULT_BGM_VOLUME  = 0.12
DEFAULT_TARGET_LUFS = -14                         # Louder, social-media optimized

# ─── Available Voices ─────────────────────────────────────────────────────────
AVAILABLE_VOICES = [
    "en-US-ChristopherNeural",  # Extremely realistic, deep documentary voice
    "en-US-EricNeural",         # Upbeat, casual, conversational
    "en-US-SteffanNeural",      # Professional, clean
    "en-US-AriaNeural",         # Very natural, expressive female
    "en-US-JennyNeural",        # Classic, clear conversational female
    "en-US-GuyNeural",          # Energetic, newscaster style
    "en-GB-SoniaNeural",        # Natural British female
    "en-AU-NatashaNeural",      # Natural Australian female
    "en-IN-NeerjaNeural",       # Natural Indian English
]

# ─── Categories ───────────────────────────────────────────────────────────────
CATEGORIES = [
    "facts", "science", "biology", "history", "technology",
    "space", "psychology", "health", "nature", "mathematics",
    "geography", "animals", "food", "sports", "music",
    "movies", "books", "philosophy", "economics", "politics",
    "environment", "architecture", "art", "fashion", "travel",
    "fitness", "nutrition", "language", "mythology", "inventions",
]

# ─── Font Options ─────────────────────────────────────────────────────────────
AVAILABLE_FONTS = {
    "Bold Impact":    "BebasNeue-Regular.ttf",
    "Clean Modern":  "Inter-Bold.ttf",
    "Elegant":       "Roboto-Regular.ttf",
}
