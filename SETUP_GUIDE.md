# ContentForge — Complete Setup & Run Guide

> A step-by-step guide to get ContentForge running from zero, including every terminal command, where to get every API key, and what to install.

---

## 📋 What You Need Before Starting

| Requirement | Why | How to Get |
|---|---|---|
| Python 3.9+ | Runs the app | python.org/downloads |
| FFmpeg | Renders video | See Step 3 below |
| VS Code | Code editor | code.visualstudio.com |
| Git (optional) | Version control | git-scm.com |

---

## 🗂 Project Folder Overview

After setup your folder looks like this:

```
contentforge/
├── main.py                  ← FastAPI web server (entry point)
├── config.py                ← All settings & path constants
├── requirements.txt         ← Python package list
├── .env                     ← YOUR API keys (never commit this)
├── .env.example             ← Template showing which keys are needed
├── generate_fallbacks.py    ← Populates offline fact database
├── download_fonts.py        ← Downloads fonts from Google
│
├── engines/
│   ├── content_fetcher.py   ← Fetches facts from 30+ categories
│   ├── script_engine.py     ← AI script generator (Gemini / NVIDIA)
│   ├── media_generator.py   ← Downloads background images
│   ├── tts_engine.py        ← Text-to-speech + music mixing
│   ├── text_overlay.py      ← Places text on video with auto-contrast
│   └── composer.py          ← Assembles final MP4
│
├── utils/
│   ├── cache_manager.py     ← Caches API calls for 24 hours
│   ├── platform_formatter.py← Formats captions for Instagram/YouTube
│   ├── download_manager.py  ← Packages video + captions as ZIP
│   └── scheduler.py         ← Daily auto-generation script
│
├── assets/
│   ├── fonts/               ← .ttf font files (downloaded by script)
│   ├── bgm/                 ← Background music (you add uplifting.mp3)
│   └── fact_datasets.json   ← Offline fallback facts
│
├── templates/
│   └── index.html           ← Browser UI
│
└── output/                  ← Generated videos saved here
```

---

## 🚀 Step-by-Step Setup

### STEP 1 — Open the Project in VS Code

1. Open VS Code
2. Go to **File → Open Folder** and open the `contentforge` folder
3. Open the **integrated terminal**: press `` Ctrl+` `` (backtick) on Windows/Linux or `` Cmd+` `` on Mac

---

### STEP 2 — Check Python Version

Run this in your terminal:

```bash
python --version
```

You need **Python 3.9 or higher**. If you see `Python 3.9.x`, `3.10.x`, `3.11.x`, or `3.12.x` you're good.

If Python is not installed, download it from: https://www.python.org/downloads/
> On Windows: tick **"Add Python to PATH"** during install.

---

### STEP 3 — Install FFmpeg

FFmpeg is required by MoviePy to render video. This is the most important external dependency.

**Windows:**
```bash
# Option A — Using winget (Windows 10/11)
winget install ffmpeg

# Option B — Using Chocolatey (if you have it)
choco install ffmpeg

# Option C — Manual:
# 1. Go to https://www.gyan.dev/ffmpeg/builds/
# 2. Download ffmpeg-release-essentials.zip
# 3. Extract to C:\ffmpeg\
# 4. Add C:\ffmpeg\bin to your System PATH
#    (Search "Environment Variables" → Edit System Variables → PATH → New → C:\ffmpeg\bin)
```

**macOS:**
```bash
# Using Homebrew (recommended)
brew install ffmpeg

# If you don't have Homebrew, install it first:
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update && sudo apt install ffmpeg -y
```

**Verify FFmpeg is installed:**
```bash
ffmpeg -version
```
You should see version info. If you get "command not found", FFmpeg is not in your PATH.

---

### STEP 4 — Create a Virtual Environment

A virtual environment keeps this project's packages separate from your system Python.

```bash
# Create the virtual environment (run once)
python -m venv venv

# Activate it:
# Windows:
venv\Scripts\activate

# macOS / Linux:
source venv/bin/activate
```

> ✅ You'll know it's active when you see `(venv)` at the start of your terminal prompt.
> Every time you open a new terminal for this project, re-run the activate command.

---

### STEP 5 — Install Python Packages

```bash
pip install -r requirements.txt
```

This installs everything: FastAPI, MoviePy, Pillow, edge-tts, and more.
It may take 2–5 minutes. Wait for it to finish.

---

### STEP 6 — Download Fonts

```bash
python download_fonts.py
```

This downloads 3 Google Fonts (Inter Bold, Roboto, Bebas Neue) into `assets/fonts/`.

---

### STEP 7 — Generate Fallback Facts Database

```bash
python generate_fallbacks.py
```

This creates `assets/fact_datasets.json` with hundreds of pre-written facts so the app works even without API keys.

---

### STEP 8 — Set Up API Keys

Copy the example env file:

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Now open the `.env` file in VS Code and fill in your API keys.
Below is exactly where to get each key — all have free tiers.

---

## 🔑 API Keys — Where to Get Them

### 1. GEMINI_API_KEY (Most Important — Script Generation)
> **Free: 1,500 requests/day** — More than enough

1. Go to: https://aistudio.google.com/
2. Sign in with your Google account
3. Click **"Get API key"** → **"Create API key"**
4. Copy the key and paste into `.env`:
   ```
   GEMINI_API_KEY=AIzaSy...your_key_here
   ```

---

### 2. API_NINJAS_KEY (Facts, Animals, Exercises, Nutrition, History)
> **Free: 50,000 requests/month**

1. Go to: https://api-ninjas.com/
2. Click **"Get Free API Key"** → Sign up
3. After login, go to your **Profile** page
4. Your API key is shown there — copy it:
   ```
   API_NINJAS_KEY=your_key_here
   ```

---

### 3. NEWS_API_KEY (Technology, Health, Sports, Environment news)
> **Free: 100 requests/day** (developer plan)

1. Go to: https://newsapi.org/
2. Click **"Get API Key"** → Register
3. Your key is shown on the dashboard:
   ```
   NEWS_API_KEY=your_key_here
   ```

---

### 4. PEXELS_API_KEY (Background Images)
> **Free: 200 requests/hour, 20,000/month**

1. Go to: https://www.pexels.com/api/
2. Click **"Get Started"** → Create account
3. After login, go to: https://www.pexels.com/api/new/
4. Fill in the form → Your key appears immediately:
   ```
   PEXELS_API_KEY=your_key_here
   ```

---

### 5. PIXABAY_API_KEY (Backup Image Source)
> **Free: unlimited for registered users**

1. Go to: https://pixabay.com/api/docs/
2. Log in or create a free account
3. Your API key is shown on that page:
   ```
   PIXABAY_API_KEY=your_key_here
   ```

---

### 6. NVIDIA_API_KEY (Optional — Backup Script Generation)
> **Free: 1,000 credits** to start

1. Go to: https://build.nvidia.com/
2. Click **"Get API Key"** → Sign up
3. Copy your key:
   ```
   NVIDIA_API_KEY=your_key_here
   ```

---

### Which Keys Are Required?

| Key | Required? | Without It |
|---|---|---|
| GEMINI_API_KEY | ✅ Strongly recommended | App uses rule-based fallback scripts |
| PEXELS_API_KEY | ✅ Recommended | Uses gradient background |
| API_NINJAS_KEY | ✅ Recommended | Uses local fallback facts |
| NEWS_API_KEY | Optional | Some categories use defaults |
| PIXABAY_API_KEY | Optional | Pexels is the primary image source |
| NVIDIA_API_KEY | Optional | Gemini is the primary LLM |

> **Minimum to get started:** The app works with ZERO keys using fallbacks. Add Gemini + Pexels for best results.

---

### STEP 9 — Add Background Music (Optional)

1. Go to: https://pixabay.com/music/ (free, no attribution needed)
2. Search "uplifting" or "inspirational"
3. Download any track as MP3
4. Rename it `uplifting.mp3`
5. Place it in: `assets/bgm/uplifting.mp3`

The "Background Music" toggle in the UI will now work.

---

### STEP 10 — Run the App

```bash
python main.py
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
```

Open your browser and go to: **http://localhost:8000**

---

## 🎬 Using the App

1. **Choose a Category** — e.g. "Space", "Biology", "History"
2. **Choose a Voice** — e.g. `en-US-AriaNeural` (female) or `en-US-GuyNeural` (male)
3. **Choose Font Style** — Bold Impact, Clean Modern, or Elegant
4. **Toggle Background Music** — if you added `uplifting.mp3`
5. Click **Generate Reel**
6. Wait ~1-2 minutes (video rendering takes time)
7. Preview your video in the browser
8. Click **Download Package** to get a ZIP with:
   - The MP4 video
   - Caption text for Instagram/YouTube/TikTok
   - Full metadata JSON

---

## ⚙️ Common Issues & Fixes

### "ModuleNotFoundError: No module named 'edge_tts'"
```bash
pip install edge-tts
```

### "FileNotFoundError: ffmpeg" or MoviePy can't find FFmpeg
- Make sure FFmpeg is installed and in your PATH (Step 3)
- Restart your terminal after installing FFmpeg
- Test with: `ffmpeg -version`

### "ImageFont cannot open resource" (font errors)
```bash
python download_fonts.py
```

### The video generates but has no text overlay
- This usually means MoviePy's `TextClip` can't find `ImageMagick`
- Install ImageMagick: https://imagemagick.org/script/download.php
- On Windows, also check the `IMAGEMAGICK_BINARY` setting in MoviePy

### App starts but browser shows error on generate
- Check the terminal for error logs
- Most common: missing API key causes a module to crash
- The app always falls back gracefully — check `output/` folder for partial results

### "Port 8000 already in use"
```bash
# Change the port in .env:
PORT=8001
# Then run again:
python main.py
```

---

## 📅 Daily Auto-Generation (Optional)

To automatically generate one reel per day:

```bash
# Run manually anytime
python -m utils.scheduler

# Or set up a cron job (Linux/Mac):
# Edit crontab: crontab -e
# Add this line to run at 8am daily:
0 8 * * * cd /path/to/contentforge && venv/bin/python -m utils.scheduler
```

---

## 🌐 Deploying to Render (Free Cloud Hosting)

1. Push your project to GitHub (without `.env` — add it to `.gitignore`)
2. Go to: https://render.com → Create a **Web Service**
3. Connect your GitHub repo
4. Set **Build Command**: `pip install -r requirements.txt`
5. Set **Start Command**: `python main.py`
6. In Render dashboard → **Environment** → add all your API keys
7. Deploy — your app gets a public URL like `https://contentforge-xyz.onrender.com`

---

## 📦 Full Terminal Command Sequence (Quick Reference)

Copy-paste these in order for a fresh setup:

```bash
# 1. Enter the project folder
cd contentforge

# 2. Create virtual environment
python -m venv venv

# 3. Activate it (Windows)
venv\Scripts\activate
# OR activate (Mac/Linux)
source venv/bin/activate

# 4. Install packages
pip install -r requirements.txt

# 5. Download fonts
python download_fonts.py

# 6. Generate offline facts
python generate_fallbacks.py

# 7. Set up your .env file
copy .env.example .env     # Windows
# cp .env.example .env     # Mac/Linux
# Then open .env and add your API keys

# 8. Run the app
python main.py

# 9. Open browser
# http://localhost:8000
```

---

## 📁 Files You Should NEVER Edit (Unless You Know What You're Doing)

- `engines/composer.py` — video assembly logic
- `engines/text_overlay.py` — text rendering engine
- `utils/cache_manager.py` — caching system

## 📁 Files You Can Safely Customize

- `config.py` — change video resolution, default voice, categories
- `templates/index.html` — change the UI design
- `assets/fact_datasets.json` — add your own facts
- `generate_fallbacks.py` — add more fallback facts per category
