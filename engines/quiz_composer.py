"""
engines/quiz_composer.py — Beautiful quiz & puzzle video renderer.
Pure Pillow card design composited via MoviePy.
"""
import logging
import time
from pathlib import Path
from typing import Dict, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import VIDEO_WIDTH as W, VIDEO_HEIGHT as H, VIDEO_FPS, OUTPUT_DIR, FONTS_DIR

import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS

logger = logging.getLogger(__name__)

OPTION_COLORS = {
    "A": (59,  130, 246, 220),   # blue
    "B": (34,  197, 94,  220),   # green
    "C": (249, 115, 22,  220),   # orange
    "D": (168, 85,  247, 220),   # purple
}
CORRECT_COLOR  = (34, 197, 94, 240)
DARK_CARD      = (15, 15, 30, 210)
WHITE          = (255, 255, 255)
YELLOW         = (255, 215, 0)


def _load_font(size: int, bold: bool = True, emoji: bool = False) -> ImageFont.FreeTypeFont:
    if emoji:
        try: return ImageFont.truetype("seguiemj.ttf", size)
        except: pass
    names = ["Inter-Bold.ttf", "Roboto-Regular.ttf", "BebasNeue-Regular.ttf"] if bold \
            else ["Roboto-Regular.ttf", "Inter-Bold.ttf"]
    for n in names:
        p = FONTS_DIR / n
        if p.exists():
            return ImageFont.truetype(str(p), size)
    for sf in ["arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"]:
        try: return ImageFont.truetype(sf, size)
        except: pass
    return ImageFont.load_default()


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list:
    words = text.split()
    lines, cur = [], ""
    draw = ImageDraw.Draw(Image.new("RGB", (1,1)))
    for w in words:
        test = (cur + " " + w).strip()
        bb = draw.textbbox((0,0), test, font=font)
        if bb[2]-bb[0] <= max_w:
            cur = test
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines or [text[:40]]


def _blur_darken(bg_arr: np.ndarray, blur: int = 18, dark: float = 0.45) -> Image.Image:
    img = Image.fromarray(bg_arr).filter(ImageFilter.GaussianBlur(blur))
    overlay = Image.new("RGBA", img.size, (0, 0, 0, int(255*dark)))
    img = img.convert("RGBA")
    return Image.alpha_composite(img, overlay).convert("RGB")


def _rounded_rect(draw: ImageDraw.Draw, xy, radius: int, fill, border=None, border_width=3):
    x0,y0,x1,y1 = xy
    if x1<=x0 or y1<=y0: return
    draw.rounded_rectangle([x0,y0,x1,y1], radius=radius, fill=fill,
                           outline=border, width=border_width if border else 0)


# ── Quiz frame renderer ────────────────────────────────────────────────────────

def render_quiz_frame(
    bg_arr:  np.ndarray,
    quiz:    Dict,
    phase:   str,       # 'hook' | 'question' | 'options' | 'cta'
    alpha:   float = 1.0,
    reveal:  bool = False,
) -> np.ndarray:
    """
    Render a complete quiz frame onto bg_arr.
    phase controls which UI elements are visible.
    Returns H×W×3 uint8.
    """
    base = _blur_darken(bg_arr)
    canvas = base.convert("RGBA")
    draw   = ImageDraw.Draw(canvas)

    pad   = int(W * 0.06)
    card_w = W - 2*pad

    y_cursor = int(H * 0.06)

    # ── Hook badge ────────────────────────────────────────────────────────────
    hook_text = quiz.get("hook", "Test Your Knowledge!")
    f_hook = _load_font(42)
    lines_h = _wrap(hook_text, f_hook, card_w - 48)
    hh = sum(draw.textbbox((0,0), l, font=f_hook)[3] for l in lines_h) + 16*len(lines_h) + 24
    _rounded_rect(draw, (pad, y_cursor, pad+card_w, y_cursor+hh+16), 18,
                  fill=(255,200,0,210), border=None)
    yy = y_cursor + 12
    for ln in lines_h:
        bb = draw.textbbox((0,0), ln, font=f_hook)
        draw.text((pad + (card_w-(bb[2]-bb[0]))//2, yy), ln, font=f_hook, fill=(20,20,20))
        yy += bb[3]-bb[1] + 10
    y_cursor += hh + 28

    if phase == "hook":
        arr = np.array(canvas.convert("RGB")).astype(np.float32)
        return np.clip(arr, 0, 255).astype(np.uint8)

    # ── Question card ─────────────────────────────────────────────────────────
    question = quiz.get("question", "")
    f_q = _load_font(46)
    lines_q = _wrap(question, f_q, card_w - 64)
    lh  = draw.textbbox((0,0), "Ag", font=f_q)[3] + 14
    qh  = len(lines_q)*lh + 40
    _rounded_rect(draw, (pad, y_cursor, pad+card_w, y_cursor+qh), 20, fill=DARK_CARD,
                  border=(255,255,255,80), border_width=2)
    # Question label
    draw.text((pad+20, y_cursor+12), "❓ QUESTION", font=_load_font(28), fill=(180,180,255))
    yy = y_cursor + 46
    for ln in lines_q:
        bb = draw.textbbox((0,0), ln, font=f_q)
        draw.text((pad + (card_w-(bb[2]-bb[0]))//2, yy), ln, font=f_q, fill=WHITE)
        yy += lh
    y_cursor += qh + 24

    if phase == "question":
        arr = np.array(canvas.convert("RGB")).astype(np.float32)
        return np.clip(arr, 0, 255).astype(np.uint8)

    # ── Option cards ──────────────────────────────────────────────────────────
    options  = quiz.get("options", {})
    answer   = quiz.get("answer", "A")
    f_opt    = _load_font(42, bold=False)
    f_badge  = _load_font(38)
    opt_h    = 96
    gap      = 16

    for key in ["A","B","C","D"]:
        text  = options.get(key, key)
        color = CORRECT_COLOR if (reveal and key == answer) else OPTION_COLORS.get(key, (80,80,80,200))
        bord  = (255,255,255,180) if (reveal and key == answer) else None
        _rounded_rect(draw, (pad, y_cursor, pad+card_w, y_cursor+opt_h), 18,
                      fill=color, border=bord, border_width=3)
        
        # Badge (e.g. A, B, C, D)
        badge_r = 30
        bx, by  = pad+18, y_cursor + (opt_h-badge_r*2)//2
        draw.ellipse([bx, by, bx+badge_r*2, by+badge_r*2], fill=(255,255,255,220))
        # Center letter inside badge
        draw.text((bx + badge_r, by + badge_r - 2), key, font=f_badge, fill=(20,20,20), anchor="mm")
        
        # Option text (aligned right of badge)
        opt_lines = _wrap(text, f_opt, card_w - 120)
        oty = y_cursor + (opt_h - len(opt_lines)*50)//2
        for ol in opt_lines:
            draw.text((pad+96, oty), ol, font=f_opt, fill=WHITE)
            oty += 50

        if reveal and key == answer:
            draw.text((pad+card_w-52, y_cursor+(opt_h-36)//2), "✓", font=_load_font(40), fill=WHITE)

        y_cursor += opt_h + gap

    # ── CTA ───────────────────────────────────────────────────────────────────
    if phase in ("options","cta"):
        y_cursor += 10
        cta = quiz.get("cta", "Comment your answer! 👇")
        f_cta = _load_font(44)
        lines_cta = _wrap(cta, f_cta, card_w-32)
        ch = len(lines_cta)*58 + 24
        if y_cursor + ch < H - 40:
            _rounded_rect(draw, (pad, y_cursor, pad+card_w, y_cursor+ch), 18,
                          fill=(255,255,255,30), border=(255,255,255,100), border_width=2)
            yy = y_cursor + 14
            for ln in lines_cta:
                bb = draw.textbbox((0,0), ln, font=f_cta)
                draw.text((pad+(card_w-(bb[2]-bb[0]))//2, yy), ln, font=f_cta, fill=YELLOW)
                yy += 58

    arr = np.array(canvas.convert("RGB")).astype(np.float32)
    return np.clip(arr * alpha + np.zeros_like(arr) * (1-alpha), 0, 255).astype(np.uint8)


# ── Puzzle frame renderer ─────────────────────────────────────────────────────

def render_puzzle_frame(
    bg_arr: np.ndarray,
    puzzle: Dict,
    phase:  str,    # 'hook' | 'puzzle' | 'hint' | 'cta'
    alpha:  float = 1.0,
) -> np.ndarray:
    base   = _blur_darken(bg_arr, blur=22, dark=0.60)
    canvas = base.convert("RGBA")
    draw   = ImageDraw.Draw(canvas)
    pad    = int(W * 0.05)
    card_w = W - 2*pad
    y      = int(H * 0.07)

    # Hook (Warning Tape Style)
    hook = puzzle.get("hook","Can you solve this?")
    f_hk = _load_font(48)
    lh   = _wrap(hook, f_hk, card_w-48)
    hh   = sum(draw.textbbox((0,0),l,font=f_hk)[3] for l in lh)+20*len(lh)+32
    _rounded_rect(draw,(pad,y,pad+card_w,y+hh),18,fill=(239,68,68,230))
    yy = y+16
    for ln in lh:
        draw.text((W//2, yy), ln, font=f_hk, fill=WHITE, anchor="mt")
        yy += draw.textbbox((0,0),ln,font=f_hk)[3]-draw.textbbox((0,0),ln,font=f_hk)[1]+12
    y += hh+36

    if phase=="hook":
        return np.clip(np.array(canvas.convert("RGB")).astype(np.float32),0,255).astype(np.uint8)

    # Emoji Puzzle Graphics Card
    ptext = puzzle.get("puzzle","")
    f_p   = _load_font(85, emoji=True) # Massive font for emojis
    
    # Split puzzle by newlines (for math equations or grids)
    p_lines = ptext.split('\n')
    ph = len(p_lines)*120 + 70
    
    _rounded_rect(draw,(pad,y,pad+card_w,y+ph),26,fill=DARK_CARD,border=(150,150,255,180),border_width=4)
    draw.text((pad+24,y+16),"🧩 VISUAL PUZZLE",font=_load_font(34),fill=(180,180,255))
    
    yy = y+75
    for ln in p_lines:
        draw.text((W//2, yy), ln.strip(), font=f_p, fill=WHITE, anchor="mt")
        yy += 120
    y += ph+32

    diff = puzzle.get("difficulty","medium").upper()
    diff_color = {"EASY":(34,197,94,220),"MEDIUM":(249,115,22,220),"HARD":(239,68,68,220)}.get(diff,(100,100,100,220))
    _rounded_rect(draw,(pad,y,pad+220,y+56),14,fill=diff_color)
    draw.text((pad+20,y+10),f"⚡ {diff}",font=_load_font(34),fill=WHITE)
    y += 76

    if phase in ("hint","cta"):
        hint = puzzle.get("hint","Think carefully!")
        f_hn = _load_font(44)
        lhn  = _wrap(f"💡 Hint: {hint}", f_hn, card_w-48)
        hnh  = len(lhn)*56+32
        _rounded_rect(draw,(pad,y,pad+card_w,y+hnh),20,fill=(255,200,0,50),border=(255,200,0,200),border_width=3)
        yy = y+16
        for ln in lhn:
            draw.text((W//2, yy), ln, font=f_hn, fill=YELLOW, anchor="mt")
            yy += 56
        y += hnh+28

    if phase=="cta":
        cta = puzzle.get("cta","Comment your answer below!")
        f_ct = _load_font(48)
        lct  = _wrap(cta, f_ct, card_w-32)
        ch   = len(lct)*60+32
        if y+ch<H-40:
            _rounded_rect(draw,(pad,y,pad+card_w,y+ch),20,fill=(255,255,255,30),border=(255,255,255,120),border_width=3)
            yy = y+16
            for ln in lct:
                draw.text((W//2, yy), ln, font=f_ct, fill=YELLOW, anchor="mt")
                yy += 60

    return np.clip(np.array(canvas.convert("RGB")).astype(np.float32)*alpha,0,255).astype(np.uint8)


# ── Quiz video composer ───────────────────────────────────────────────────────

def compose_quiz_video(
    quiz:      Dict,
    bg_paths:  list,
    audio_path: str,
    output_path: Optional[str] = None,
    video_type: str = "quiz",   # 'quiz' or 'puzzle'
) -> str:
    from moviepy.editor import AudioFileClip, VideoClip

    if not output_path:
        output_path = str(OUTPUT_DIR / f"{video_type}_{int(time.time())}.mp4")
    Path(output_path).parent.mkdir(exist_ok=True)

    audio      = AudioFileClip(audio_path)
    total_dur  = audio.duration

    import random
    bg_arrays = []
    for p in bg_paths:
        try: bg_arrays.append(np.array(Image.open(p).convert("RGB").resize((W,H),Image.Resampling.LANCZOS)))
        except: pass
    if not bg_arrays:
        bg_arrays = [np.zeros((H,W,3),dtype=np.uint8)]

    bg = bg_arrays[0]

    # Timeline phases
    if video_type == "quiz":
        phases = [
            (0,           2.0,   "hook"),
            (2.0,         8.0,   "question"),
            (8.0,         total_dur-3.0, "options"),
            (total_dur-3.0, total_dur,   "cta"),
        ]
    else:
        phases = [
            (0,           2.5,   "hook"),
            (2.5,         total_dur-5.0, "puzzle"),
            (total_dur-5.0, total_dur-2.0, "hint"),
            (total_dur-2.0, total_dur,     "cta"),
        ]

    def get_phase(t):
        for s,e,ph in phases:
            if s <= t < e:
                fade = min(0.3, (e-s)*0.1)
                a = min(1.0, (t-s)/max(fade,0.01))
                a = min(a, min(1.0, (e-t)/max(fade,0.01)))
                return ph, max(0.3, a)
        return phases[-1][2], 1.0

    def make_frame(t):
        import time
        time.sleep(0.001)  # Yield GIL to allow FastAPI to respond to polls
        ph, alpha = get_phase(t)
        # Static background to prevent Memory Leaks / OOM on Render Free Tier
        bg_f = bg

        if video_type == "quiz":
            return render_quiz_frame(bg_f, quiz, ph, alpha)
        else:
            return render_puzzle_frame(bg_f, quiz, ph, alpha)

    clip = VideoClip(make_frame, duration=total_dur).set_fps(VIDEO_FPS)
    clip = clip.set_audio(audio).set_duration(total_dur)
    clip.write_videofile(
        output_path, codec="libx264", audio_codec="aac",
        fps=VIDEO_FPS, preset="ultrafast",
        ffmpeg_params=["-crf","28","-threads","1"], logger=None,
    )
    logger.info(f"[QuizComposer] Done → {output_path}")
    return output_path
