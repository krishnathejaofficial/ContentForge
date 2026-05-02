"""
engines/text_overlay.py — Fast caption overlay with pre-rendered pills.

Speed optimization: render_pill_rgba() is called ONCE per caption at init.
Per-frame operations are pure numpy (array slice + multiply) — ~0.1ms vs ~15ms PIL.

Animation styles:
  SLIDE_UP   — numpy row-shift upward
  POP        — pre-rendered at 5 scale steps, picked by progress
  SLIDE_LEFT — numpy column-shift from right
  FADE       — only alpha multiplication
"""
import logging
import textwrap
from enum import Enum
from pathlib import Path
from typing import List, Tuple, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import FONTS_DIR, VIDEO_WIDTH, VIDEO_HEIGHT

logger = logging.getLogger(__name__)

try:
    from moviepy.editor import VideoClip
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False

W, H     = VIDEO_WIDTH, VIDEO_HEIGHT
SAFE_X   = int(W * 0.08)
SAFE_Y   = int(H * 0.06)
MAX_TW   = W - 2 * SAFE_X
PAD_X, PAD_Y = 36, 22
PILL_R   = 22
LINE_GAP = 0.30
POP_STEPS = 6   # number of pre-rendered scale steps for POP animation


class AnimStyle(Enum):
    FADE       = "fade"
    SLIDE_UP   = "slide_up"
    POP        = "pop"
    SLIDE_LEFT = "slide_left"

STYLE_CYCLE = [AnimStyle.SLIDE_UP, AnimStyle.POP, AnimStyle.SLIDE_LEFT, AnimStyle.FADE]


class TextOverlay:
    def __init__(self, font_dir: Optional[str] = None):
        self.font_dir = Path(font_dir) if font_dir else FONTS_DIR

    def _load_font(self, name: str, size: int) -> ImageFont.FreeTypeFont:
        for p in [self.font_dir/name, self.font_dir/"Inter-Bold.ttf",
                  self.font_dir/"Roboto-Regular.ttf", self.font_dir/"BebasNeue-Regular.ttf"]:
            if p.exists():
                return ImageFont.truetype(str(p), size)
        for sf in ["arial.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]:
            try: return ImageFont.truetype(sf, size)
            except: pass
        return ImageFont.load_default()

    def _compute_layout(self, text: str, font_name: str, max_w: int, max_h: int):
        text = text.strip().strip(".,;:-")
        for size in range(66, 18, -2):
            font    = self._load_font(font_name, size)
            lines   = textwrap.wrap(text, width=28) or [text[:40]]
            dummy   = Image.new("RGB", (1,1))
            draw    = ImageDraw.Draw(dummy)
            dims    = [(bb:=draw.textbbox((0,0),ln,font=font), (bb[2]-bb[0], bb[3]-bb[1]))[1]
                       for ln in lines]
            gap     = int(size * LINE_GAP)
            tot_h   = sum(d[1] for d in dims) + gap*(len(lines)-1)
            if max(d[0] for d in dims) <= max_w and tot_h <= max_h:
                return lines, font, size, dims
        font  = self._load_font(font_name, 20)
        lines = [text[:30]]
        dummy = Image.new("RGB",(1,1)); draw = ImageDraw.Draw(dummy)
        bb    = draw.textbbox((0,0),lines[0],font=font)
        return lines, font, 20, [(bb[2]-bb[0], bb[3]-bb[1])]

    def render_pill_rgba(
        self, text: str, bg_sample: np.ndarray,
        font_name: str = "Inter-Bold.ttf",
        position: str  = "center",
        alpha: float   = 1.0,
    ) -> np.ndarray:
        """Returns H×W×4 RGBA. Called ONCE per caption — not per frame."""
        canvas = Image.new("RGBA", (W, H), (0,0,0,0))
        lines, font, size, dims = self._compute_layout(text, font_name, MAX_TW, int(H*0.28))
        gap     = int(size * LINE_GAP)
        block_w = max(d[0] for d in dims)
        block_h = sum(d[1] for d in dims) + gap*(len(lines)-1)
        pill_w  = min(block_w + PAD_X*2, W - 2*SAFE_X)
        pill_h  = block_h + PAD_Y*2
        pill_x  = max(SAFE_X, (W-pill_w)//2)
        if   position=="top":    pill_y = SAFE_Y + int(H*0.04)
        elif position=="bottom": pill_y = H - SAFE_Y - pill_h - int(H*0.03)
        else:                    pill_y = (H-pill_h)//2 + int(H*0.04)
        pill_y  = max(SAFE_Y, min(pill_y, H-SAFE_Y-pill_h))

        sy1,sy2 = max(0,pill_y), min(H, pill_y+pill_h)
        sx1,sx2 = max(0,pill_x), min(W, pill_x+pill_w)
        region  = bg_sample[sy1:sy2, sx1:sx2] if sy2>sy1 and sx2>sx1 else np.zeros((1,1,3))
        lum     = 0.299*region[:,:,0]+0.587*region[:,:,1]+0.114*region[:,:,2]
        bright  = float(np.mean(lum))
        tc      = "white" if bright < 140 else "black"
        fill    = (0,0,0,int(215*alpha)) if tc=="white" else (255,255,255,int(215*alpha))

        draw = ImageDraw.Draw(canvas)
        if pill_x<W and pill_x+pill_w>0 and pill_y<H and pill_y+pill_h>0:
            draw.rounded_rectangle([pill_x,pill_y,pill_x+pill_w,pill_y+pill_h],
                                   radius=PILL_R, fill=fill)
            sc = "black" if tc=="white" else "white"
            sw = max(1, size//38)
            yc = pill_y + PAD_Y
            for ln,(lw,lh) in zip(lines,dims):
                draw.text((pill_x+(pill_w-lw)//2, yc), ln, font=font,
                          fill=tc, stroke_width=sw, stroke_fill=sc)
                yc += lh + gap
        return np.array(canvas)

    def make_caption_clip(
        self, bg_sample: np.ndarray, text: str,
        font_name: str = "Inter-Bold.ttf", duration: float = 4.0,
        position: str = "center", style: "AnimStyle" = AnimStyle.FADE,
    ):
        """
        Pre-renders pill ONCE. Per-frame ops are pure numpy (~0.1ms each).
        """
        if not MOVIEPY_AVAILABLE:
            raise RuntimeError("MoviePy not available")

        fade = min(0.25, duration * 0.15)
        ANIM = min(0.4, duration * 0.20)  # animation-in window

        # ── Pre-render pill arrays (done ONCE) ────────────────────────────────
        rgba_full = self.render_pill_rgba(text, bg_sample, font_name, position, 1.0)
        rgb_full  = rgba_full[:,:,:3].astype(np.float32)   # H×W×3
        a_full    = rgba_full[:,:,3].astype(np.float32)/255.0  # H×W  (0..1)

        # For POP: pre-render at POP_STEPS scale levels (0.70 → 1.0)
        pop_frames_rgb = []
        pop_frames_a   = []
        if style == AnimStyle.POP:
            for si in range(POP_STEPS):
                sc = 0.70 + 0.30 * si/(POP_STEPS-1)
                nw, nh = max(1,int(W*sc)), max(1,int(H*sc))
                small  = Image.fromarray(rgba_full).resize((nw,nh), Image.Resampling.BILINEAR)
                out    = Image.new("RGBA",(W,H),(0,0,0,0))
                out.paste(small, ((W-nw)//2,(H-nh)//2))
                arr = np.array(out)
                pop_frames_rgb.append(arr[:,:,:3].astype(np.float32))
                pop_frames_a.append(arr[:,:,3].astype(np.float32)/255.0)

        def _master_alpha(t: float) -> float:
            if   t < fade:             return t/fade
            elif t > duration-fade:    return (duration-t)/max(fade,1e-6)
            return 1.0

        def _anim_progress(t: float) -> float:
            return min(1.0, t/max(ANIM,0.01))

        def make_frame(t: float) -> np.ndarray:
            p = _anim_progress(t)
            ease = 1-(1-p)**3  # cubic ease-out

            if style == AnimStyle.SLIDE_UP:
                y_off = int((1-ease)*180)
                if y_off > 0:
                    shifted = np.zeros_like(rgb_full)
                    shifted[y_off:] = rgb_full[:H-y_off]
                    return shifted.astype(np.uint8)
                return rgb_full.astype(np.uint8)

            elif style == AnimStyle.SLIDE_LEFT:
                x_off = int((1-ease)*420)
                if x_off > 0 and x_off < W:
                    shifted = np.zeros_like(rgb_full)
                    shifted[:, x_off:] = rgb_full[:, :W-x_off]
                    return shifted.astype(np.uint8)
                return rgb_full.astype(np.uint8)

            elif style == AnimStyle.POP:
                idx = min(int(p*(POP_STEPS-1)), POP_STEPS-1)
                return pop_frames_rgb[idx].astype(np.uint8)

            return rgb_full.astype(np.uint8)

        def make_mask(t: float) -> np.ndarray:
            ma   = max(0.0, min(1.0, _master_alpha(t)))
            p    = _anim_progress(t)
            ease = 1-(1-p)**3

            if style == AnimStyle.SLIDE_UP:
                y_off = int((1-ease)*180)
                if y_off > 0:
                    shifted = np.zeros_like(a_full)
                    shifted[y_off:] = a_full[:H-y_off]
                    return shifted * ma
                return a_full * ma

            elif style == AnimStyle.SLIDE_LEFT:
                x_off = int((1-ease)*420)
                if x_off > 0 and x_off < W:
                    shifted = np.zeros_like(a_full)
                    shifted[:, x_off:] = a_full[:, :W-x_off]
                    return shifted * ma
                return a_full * ma

            elif style == AnimStyle.POP:
                idx = min(int(p*(POP_STEPS-1)), POP_STEPS-1)
                return pop_frames_a[idx] * ma

            return a_full * ma

        clip = VideoClip(make_frame, duration=duration).set_fps(24)
        mask = VideoClip(make_mask, ismask=True, duration=duration).set_fps(24)
        return clip.set_mask(mask)

    # ── Compatibility wrappers ────────────────────────────────────────────────

    def add_caption_overlay(self, background_clip, text, font_name="Inter-Bold.ttf",
                            duration=4.0, position="center", style_index=0):
        sample = background_clip.get_frame(0)
        return self.make_caption_clip(sample, text, font_name, duration, position,
                                      STYLE_CYCLE[style_index % len(STYLE_CYCLE)])
