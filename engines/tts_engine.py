"""
engines/tts_engine.py — Ultra-realistic voiceover with sentence-level sync + smart BGM.

Key features:
  - Uses edge-tts SentenceBoundary events for EXACT caption timing sync
  - Returns (audio_path, timed_captions) so composer knows EXACTLY when each phrase plays
  - Procedural lo-fi BGM fallback if yt-dlp fails (always works, no network needed)
  - Smart side-chain duck: voice always dominates BGM
  - Full text sanitization before TTS (no symbols read aloud)
"""
import asyncio
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Optional, List, Dict, Tuple

import edge_tts
from pydub import AudioSegment
from pydub.generators import Sine, Square, Sawtooth
from pydub.effects import normalize, compress_dynamic_range

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DEFAULT_VOICE, DEFAULT_BGM_VOLUME, DEFAULT_TARGET_LUFS, OUTPUT_DIR

logger = logging.getLogger(__name__)


# ── Text sanitizer ────────────────────────────────────────────────────────────

def clean_text_for_tts(text: str) -> str:
    """Strip everything TTS should NOT read aloud."""
    text = re.sub(r"<[^>]+>", " ", text)             # XML/HTML tags
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)  # **bold** → text
    text = re.sub(r"_{1,2}([^_]+)_{1,2}", r"\1", text)     # _italic_ → text
    text = re.sub(r"[`~#^@|\\{}]", " ", text)        # code/special chars
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)   # [link](url)
    text = re.sub(r"\[[^\]]*\]", "", text)            # [anything]
    text = re.sub(r"\{[^}]*\}", "", text)             # {anything}
    text = re.sub(r"https?://\S+", "", text)          # URLs
    text = re.sub(r"([.!?]){2,}", r"\1", text)        # ... → .
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ── Sentence-level timing from edge-tts stream ────────────────────────────────

async def _generate_with_sentence_timing(
    text: str,
    voice: str,
    rate: str = "-5%",
    volume: str = "+8%",
    pitch: str = "+1Hz",
) -> Tuple[bytes, List[Dict]]:
    """
    Stream edge-tts and capture SentenceBoundary events.
    Returns (mp3_bytes, sentence_timings)
    where sentence_timings = [{"text": str, "start_ms": float, "end_ms": float}, ...]
    """
    communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume, pitch=pitch)
    audio_chunks = []
    sentence_events = []

    async for event in communicate.stream():
        if event["type"] == "audio":
            audio_chunks.append(event["data"])
        elif event["type"] == "SentenceBoundary":
            # offset and duration are in 100-nanosecond units
            start_ms = event["offset"] / 10000.0
            dur_ms   = event["duration"] / 10000.0
            sentence_events.append({
                "text":     event.get("text", ""),
                "start_ms": start_ms,
                "end_ms":   start_ms + dur_ms,
            })

    return b"".join(audio_chunks), sentence_events


def _sentences_to_caption_lines(sentence_timings: List[Dict]) -> List[Dict]:
    """
    Convert sentence boundary events to caption line dicts:
    [{"text": str, "start": float, "end": float, "duration": float}, ...]
    """
    lines = []
    for s in sentence_timings:
        text = s["text"].strip()
        if not text:
            continue
        start = s["start_ms"] / 1000.0
        end   = s["end_ms"]   / 1000.0
        # If sentence is long, split into two chunks
        words = text.split()
        if len(words) > 10:
            mid    = len(words) // 2
            half_t = (start + end) / 2
            lines.append({"text": " ".join(words[:mid]), "start": round(start, 3), "end": round(half_t, 3), "duration": round(half_t - start, 3)})
            lines.append({"text": " ".join(words[mid:]), "start": round(half_t, 3), "end": round(end, 3), "duration": round(end - half_t, 3)})
        else:
            lines.append({"text": text, "start": round(start, 3), "end": round(end, 3), "duration": round(end - start, 3)})
    return lines


# ── Procedural lo-fi BGM ──────────────────────────────────────────────────────

def _generate_lofi_bgm(duration_ms: int) -> AudioSegment:
    """
    Generate a simple lo-fi chill beat using pydub generators.
    Always works — no internet or external files needed.
    Layers: bass note + soft hi-hat rhythm + subtle pad chord
    """
    bpm       = 75
    beat_ms   = int(60000 / bpm)    # one beat in ms (~800ms)
    bar_ms    = beat_ms * 4

    # Bass note A2 (110 Hz) — half-beat duration
    bass_note  = Sine(110).to_audio_segment(duration=beat_ms // 2) - 22
    bass_note2 = Sine(130).to_audio_segment(duration=beat_ms // 2) - 24

    # Soft hi-hat: white-ish noise via short Sawtooth at high freq
    hihat = Sawtooth(8000).to_audio_segment(duration=40) - 32
    hihat = hihat.fade_out(30)

    # Pad: stacked 3rd-based chord (C4=261, E4=329, G4=392)
    pad_c = Sine(261).to_audio_segment(duration=bar_ms) - 28
    pad_e = Sine(329).to_audio_segment(duration=bar_ms) - 29
    pad_g = Sine(392).to_audio_segment(duration=bar_ms) - 30
    pad   = pad_c.overlay(pad_e).overlay(pad_g)
    pad   = pad.fade_in(200).fade_out(200)

    # Build one bar
    bar = AudioSegment.silent(duration=bar_ms)
    # Beats 1 & 3: bass
    bar = bar.overlay(bass_note,  position=0)
    bar = bar.overlay(bass_note2, position=beat_ms * 2)
    # Hi-hats on all 4 beats
    for i in range(4):
        bar = bar.overlay(hihat, position=beat_ms * i)
    # Offbeat hi-hats (eighth notes)
    for i in range(4):
        bar = bar.overlay(hihat - 6, position=beat_ms * i + beat_ms // 2)
    # Add pad
    bar = bar.overlay(pad)

    # Loop to desired duration
    loops  = (duration_ms // bar_ms) + 2
    result = bar * loops
    result = result[:duration_ms]
    result = result.fade_in(2000).fade_out(3000)
    return normalize(result)


# ── BGM loading/fetching ──────────────────────────────────────────────────────

def _load_bgm(bgm_path: Optional[str], duration_ms: int) -> Optional[AudioSegment]:
    """Load BGM from path, or generate procedural fallback."""
    if bgm_path and Path(bgm_path).exists() and Path(bgm_path).stat().st_size > 50_000:
        try:
            return AudioSegment.from_file(bgm_path)
        except Exception as e:
            logger.warning(f"[TTS] Could not load BGM file: {e}")

    # Procedural fallback — always available
    logger.info("[TTS] Using procedural lo-fi BGM (no external file needed)")
    return _generate_lofi_bgm(duration_ms + 4000)


# ── Loudness ──────────────────────────────────────────────────────────────────

def _lufs_adjust(audio: AudioSegment, target: float = -14.0) -> AudioSegment:
    rms = audio.dBFS
    if rms == float("-inf"):
        return audio
    adjustment = max(-20.0, min(20.0, target - (rms - 3.0)))
    return audio + adjustment


# ── Duck and mix ──────────────────────────────────────────────────────────────

def _duck_and_mix(voice: AudioSegment, bgm: AudioSegment) -> AudioSegment:
    """Side-chain duck: BGM sits 15 dB under voice, hard-capped at -22 dBFS."""
    dur_ms = len(voice)

    # Loop BGM if needed
    if len(bgm) < dur_ms + 4000:
        repeats = (dur_ms + 4000) // max(len(bgm), 1) + 2
        bgm = bgm * repeats

    bgm = bgm[: dur_ms + 3000]
    bgm = normalize(bgm)
    bgm = bgm.fade_in(2000).fade_out(3000)

    target_db = voice.dBFS - 15
    gain      = target_db - bgm.dBFS
    bgm       = bgm + gain

    # Hard cap
    if bgm.dBFS > -22:
        bgm = bgm + (-22 - bgm.dBFS)

    bgm = bgm[:dur_ms]
    return voice.overlay(bgm)


# ── Main public API ───────────────────────────────────────────────────────────

async def generate_voiceover(
    text: str,
    voice: str = DEFAULT_VOICE,
    use_voice: bool = True,
    bgm_path: Optional[str] = None,
    bgm_volume: float = DEFAULT_BGM_VOLUME,
    target_lufs: float = DEFAULT_TARGET_LUFS,
    output_dir: Optional[str] = None,
) -> Tuple[str, List[Dict]]:
    """
    Generate voiceover + optional BGM mix.
    Returns (audio_path, timed_captions).
    timed_captions = [{"text": str, "start": float, "end": float, "duration": float}]
    """
    out_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    out_dir.mkdir(exist_ok=True)

    timed_captions = []

    if use_voice:
        clean = clean_text_for_tts(text)
        if not clean.strip():
            clean = "Here is an incredible fact you probably never knew about."

        logger.info(f"[TTS] Voice={voice} | {len(clean.split())} words")

        # Stream with sentence boundary events
        try:
            raw_bytes, sentence_timings = await _generate_with_sentence_timing(
                clean, voice, rate="-5%", volume="+8%", pitch="+1Hz"
            )
            timed_captions = _sentences_to_caption_lines(sentence_timings)
            logger.info(f"[TTS] Got {len(timed_captions)} caption segments from sentence boundaries")
        except Exception as e:
            logger.warning(f"[TTS] Edge-TTS failed ({e}), falling back to Google TTS (gTTS)...")
            from gtts import gTTS
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name
            
            # gTTS is a synchronous network call, wrap in to_thread if you like, but simple call is fine here
            import anyio
            def _run_gtts():
                tts = gTTS(text=clean, lang='en', slow=False)
                tts.save(tmp_path)
            await anyio.to_thread.run_sync(_run_gtts)
            
            with open(tmp_path, "rb") as f:
                raw_bytes = f.read()
            os.unlink(tmp_path)
            # Empty timed_captions since gTTS doesn't support timestamps, main.py will fallback to script lines
            timed_captions = []

        # Write raw mp3 bytes to temp file
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name

        voice_audio = AudioSegment.from_mp3(tmp_path)
        os.unlink(tmp_path)

        # Light compression
        try:
            voice_audio = compress_dynamic_range(
                voice_audio, threshold=-18.0, ratio=3.0, attack=5.0, release=50.0
            )
        except Exception:
            pass

    else:
        raise ValueError("use_voice must be True")

    # Normalise voice
    voice_audio = _lufs_adjust(voice_audio, target_lufs)
    total_ms    = len(voice_audio)
    logger.info(f"[TTS] Voice audio duration: {total_ms/1000:.1f}s")

    # Mix BGM
    if bgm_path is not None or True:  # Always add BGM (procedural fallback if no file)
        bgm = _load_bgm(bgm_path, total_ms)
        if bgm:
            try:
                final_audio = _duck_and_mix(voice_audio, bgm)
                final_audio = _lufs_adjust(final_audio, target_lufs)
                logger.info("[TTS] BGM mixed successfully")
            except Exception as e:
                logger.warning(f"[TTS] BGM mix failed ({e})")
                final_audio = voice_audio
        else:
            final_audio = voice_audio
    else:
        final_audio = voice_audio

    # Export
    out_path = str(out_dir / f"voice_{int(time.time())}.mp3")
    final_audio.export(out_path, format="mp3", bitrate="192k")
    logger.info(f"[TTS] Saved: {Path(out_path).name} ({len(final_audio)/1000:.1f}s)")

    return out_path, timed_captions


async def get_audio_duration(audio_path: str) -> float:
    return len(AudioSegment.from_file(audio_path)) / 1000.0
