"""
engines/composer.py — Fast multi-background video assembly.

Speed optimizations:
  1. Background: pre-compute 10 keyframes per segment (BILINEAR), 
     per-frame = numpy interpolation only (~0.5ms vs 50ms PIL resize)
  2. Captions: pre-render pill RGBA once, per-frame = numpy shift/multiply only
  3. FFmpeg: ultrafast preset + 4 threads
  4. Vignette: pre-computed as float32 mask, baked with numpy matmul
"""
import logging
import random
import time
from pathlib import Path
from typing import List, Dict, Optional

import numpy as np
from PIL import Image, ImageDraw

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS, OUTPUT_DIR

import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS

logger = logging.getLogger(__name__)

W, H   = VIDEO_WIDTH, VIDEO_HEIGHT
XFADE  = 0.6   # crossfade seconds between backgrounds
N_KEYS = 3    # keyframes per background segment (lowered for 512MB RAM limit)

KB_MODES = [
    (+1, +1,  0), (+1, -1,  0), (+1,  0, +1),
    (-1, +1,  0), (-1,  0, -1),
]


# ── Pre-computation helpers ───────────────────────────────────────────────────

def _load_np(path: str) -> np.ndarray:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    r, tr = w/h, W/H
    if r > tr:
        nw, nh = int(h*r*H/h), H
    else:
        nw, nh = W, int(W/r)
    nw, nh = max(nw, W), max(nh, H)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    l, t = (nw-W)//2, (nh-H)//2
    return np.array(img.crop((l, t, l+W, t+H)))


def _precompute_segment(bg_arr: np.ndarray, kb_mode: tuple) -> List[np.ndarray]:
    """
    Pre-compute N_KEYS keyframes for one background segment.
    Uses BILINEAR (3× faster than LANCZOS). Only called once per segment.
    """
    zoom_dir, dx, dy = kb_mode
    frames = []
    for i in range(N_KEYS):
        p  = i / max(N_KEYS-1, 1)
        sc = (1.0 + 0.10*p) if zoom_dir > 0 else (1.10 - 0.10*p)
        nw, nh = max(int(W*sc), W), max(int(H*sc), H)
        img = Image.fromarray(bg_arr).resize((nw, nh), Image.Resampling.BILINEAR)
        arr = np.array(img)
        max_x, max_y = max(0, nw-W), max(0, nh-H)
        left = max(0, min((nw-W)//2 + int(dx*p*max_x*0.45), max_x))
        top  = max(0, min((nh-H)//2 + int(dy*p*max_y*0.45), max_y))
        frames.append(arr[top:top+H, left:left+W])
    return frames


def _interp(keyframes: List[np.ndarray], progress: float) -> np.ndarray:
    """Linear interpolation between keyframes — pure numpy, ~0.5ms."""
    n   = len(keyframes)
    idx = max(0.0, min(1.0, progress)) * (n-1)
    ia  = int(idx)
    ib  = min(ia+1, n-1)
    a   = idx - ia
    if ia == ib or a < 0.001:
        return keyframes[ia]
    return ((1-a)*keyframes[ia] + a*keyframes[ib]).astype(np.uint8)


def _make_vignette_mask() -> np.ndarray:
    """H×W float32 vignette mask (0=transparent, 1=full dark) pre-computed once."""
    ys = np.linspace(-1, 1, H)[:, None]
    xs = np.linspace(-1, 1, W)[None, :]
    dist = np.sqrt(xs**2 + ys**2) / np.sqrt(2)
    return (np.clip(dist - 0.3, 0, None) / 0.7).astype(np.float32) * 0.65


def _make_particle_seeds(n: int = 20) -> List[dict]:
    rng = random.Random(42)
    colors = [(255,255,255),(200,200,255),(255,220,180),(180,255,220)]
    return [{
        "x": rng.randint(0, W-8), "y_base": rng.randint(0, H),
        "speed": rng.uniform(18, 55), "size": rng.randint(2, 7),
        "alpha": rng.randint(20, 70), "color": rng.choice(colors),
        "wobble": rng.uniform(0.3, 1.5), "phase": rng.uniform(0, 6.28),
    } for _ in range(n)]


def _particles_numpy(t: float, seeds: List[dict]) -> np.ndarray:
    """Pure numpy particles — no PIL Draw, ~1ms per frame."""
    rgb = np.zeros((H, W, 3), np.float32)
    alp = np.zeros((H, W),    np.float32)
    for p in seeds:
        y = int((p["y_base"] - p["speed"]*t) % H)
        x = int(p["x"] + 10*np.sin(t*p["wobble"]+p["phase"])) % W
        s = p["size"]
        y1, y2 = max(0,y), min(H, y+s)
        x1, x2 = max(0,x), min(W, x+s)
        if y1<y2 and x1<x2:
            alp[y1:y2, x1:x2] = p["alpha"] / 255.0
            for c, v in enumerate(p["color"]):
                rgb[y1:y2, x1:x2, c] = v
    return rgb, alp


def _assign_line_timings(lines: List[Dict], total: float) -> List[Dict]:
    if lines and all("start" in l and "end" in l for l in lines):
        return lines
    n = len(lines)
    if not n:
        return []
    dur = total / n
    return [{**l, "start": round(i*dur,3), "end": round((i+1)*dur,3), "duration": round(dur,3)}
            for i, l in enumerate(lines)]


# ── Main composer ─────────────────────────────────────────────────────────────

def compose_reel(
    background_path,
    audio_path: str,
    script_lines: List[Dict],
    font_style: str = "Inter-Bold.ttf",
    output_path: Optional[str] = None,
    headline: Optional[str] = None,
) -> str:
    from moviepy.editor import AudioFileClip, VideoClip, CompositeVideoClip
    from engines.text_overlay import TextOverlay, AnimStyle, STYLE_CYCLE

    if not output_path:
        output_path = str(OUTPUT_DIR / f"reel_{int(time.time())}.mp4")
    Path(output_path).parent.mkdir(exist_ok=True)

    audio_clip     = AudioFileClip(audio_path)
    total_duration = audio_clip.duration
    logger.info(f"[Composer] {total_duration:.1f}s audio")

    # Load backgrounds
    bg_paths = background_path if isinstance(background_path, list) else [background_path]
    bg_arrays = []
    for p in bg_paths:
        try:
            bg_arrays.append(_load_np(p))
        except Exception as e:
            logger.warning(f"[Composer] Skip BG {p}: {e}")
    if not bg_arrays:
        raise ValueError("No backgrounds could be loaded")

    n_segs   = len(bg_arrays)
    seg_dur  = total_duration / n_segs
    kb_modes = (KB_MODES * ((n_segs // len(KB_MODES)) + 1))[:n_segs]
    random.shuffle(kb_modes)

    # ── Pre-compute keyframes upfront (once) ──────────────────────────────────
    logger.info(f"[Composer] Pre-computing {n_segs}×{N_KEYS} keyframes...")
    segment_keyframes = []
    for i, (arr, kb) in enumerate(zip(bg_arrays, kb_modes)):
        kf = _precompute_segment(arr, kb)
        segment_keyframes.append(kf)
        logger.info(f"[Composer] Segment {i+1}/{n_segs} keyframes ready")

    # Pre-compute static overlays
    vig_mask    = _make_vignette_mask()[:, :, None]  # H×W×1
    dark_layer  = np.zeros((H, W, 3), np.float32)    # pure black for vignette
    p_seeds     = _make_particle_seeds(20)
    sample_frame = bg_arrays[0].copy()

    # ── Background VideoClip (all numpy, no PIL per frame) ────────────────────
    def bg_make_frame(t: float) -> np.ndarray:
        import time
        time.sleep(0.001)  # Yield GIL to allow FastAPI to respond to polls
        seg_idx  = min(int(t / seg_dur), n_segs-1)
        local_t  = t - seg_idx * seg_dur
        progress = min(local_t / max(seg_dur, 1), 1.0)
        frame    = _interp(segment_keyframes[seg_idx], progress).astype(np.float32)

        # Crossfade to next segment
        blend_start = seg_dur - XFADE
        if local_t >= blend_start and seg_idx < n_segs-1:
            mix       = min(1.0, (local_t-blend_start)/XFADE)
            next_f    = segment_keyframes[seg_idx+1][0].astype(np.float32)
            frame     = frame*(1-mix) + next_f*mix

        # Vignette (numpy)
        frame = frame*(1-vig_mask) + dark_layer*vig_mask

        # Particles (numpy)
        p_rgb, p_a = _particles_numpy(t, p_seeds)
        p_a3 = p_a[:, :, None]
        frame = frame*(1-p_a3) + p_rgb*p_a3

        return np.clip(frame, 0, 255).astype(np.uint8)

    bg_clip = VideoClip(bg_make_frame, duration=total_duration).set_fps(VIDEO_FPS)

    # ── Caption clips ─────────────────────────────────────────────────────────
    engine     = TextOverlay()
    timed      = _assign_line_timings(script_lines, total_duration)
    all_clips  = [bg_clip]

    if headline and headline.strip():
        hl = headline.strip().strip('.,;:"\'*#')
        try:
            c = engine.make_caption_clip(sample_frame, hl, font_style, 2.5, "top", AnimStyle.SLIDE_UP)
            all_clips.append(c.set_start(0).set_end(2.5))
        except Exception as e:
            logger.warning(f"[Composer] Headline failed: {e}")

    for i, line in enumerate(timed):
        txt = str(line.get("text","")).strip().strip('.,;:"\'*#')
        if not txt:
            continue
        start = float(line["start"])
        end   = float(line["end"])
        dur   = max(0.4, end-start)
        style = STYLE_CYCLE[i % len(STYLE_CYCLE)]
        try:
            c = engine.make_caption_clip(sample_frame, txt, font_style, dur, "center", style)
            all_clips.append(c.set_start(start).set_end(end))
        except Exception as e:
            logger.warning(f"[Composer] Caption failed: {e}")

    logger.info(f"[Composer] {len(all_clips)-1} caption clips built")

    final = CompositeVideoClip(all_clips, size=(W,H))
    final = final.set_audio(audio_clip).set_duration(total_duration)

    logger.info(f"[Composer] Rendering → {output_path}")
    final.write_videofile(
        output_path,
        codec="libx264", audio_codec="aac",
        fps=VIDEO_FPS,
        preset="ultrafast",                      # fastest encoding
        ffmpeg_params=["-crf","25","-threads","2"],
        logger=None,
    )
    logger.info(f"[Composer] Done → {output_path}")
    return output_path
