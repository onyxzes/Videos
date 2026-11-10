"""Text-to-speech with word timings (for karaoke captions).

Priority:
  1. ElevenLabs (env ELEVENLABS_API_KEY): the viral narrator voice heard on
     countless Shorts/TikToks. Default voice "Adam"; change it in config.json.
  2. edge-tts (free Microsoft neural voices).
Returns a list of {"word", "start", "end"} in seconds, or None if no TTS works.
"""
from __future__ import annotations

import asyncio
import base64
import os
from pathlib import Path

import requests


def _elevenlabs(text: str, cfg: dict, out: Path):
    el = cfg.get("elevenlabs", {})
    voice_id = el.get("voice_id", "pNInz6obpgDQGcFmaJgB")
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps",
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Content-Type": "application/json"},
        json={"text": text, "model_id": el.get("model_id", "eleven_multilingual_v2"),
              "language_code": cfg.get("language", "es"),
              "voice_settings": {"stability": el.get("stability", 0.35),
                                 "similarity_boost": 0.8, "style": el.get("style", 0.45),
                                 "use_speaker_boost": True, "speed": el.get("speed", 1.08)}},
        timeout=120)
    if r.status_code == 400 and "language_code" in r.text:
        # some models don't accept language_code; retry without it
        return _elevenlabs_nolang(text, cfg, out, voice_id)
    r.raise_for_status()
    return _parse_el(r.json(), out)


def _elevenlabs_nolang(text, cfg, out, voice_id):
    el = cfg.get("elevenlabs", {})
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps",
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
        json={"text": text, "model_id": el.get("model_id", "eleven_multilingual_v2")}, timeout=120)
    r.raise_for_status()
    return _parse_el(r.json(), out)


def _parse_el(data: dict, out: Path):
    out.write_bytes(base64.b64decode(data["audio_base64"]))
    al = data.get("alignment") or data.get("normalized_alignment")
    words, cur, start, end = [], "", None, 0.0
    for ch, s, e in zip(al["characters"], al["character_start_times_seconds"],
                        al["character_end_times_seconds"]):
        if ch.isspace():
            if cur:
                words.append({"word": cur, "start": start, "end": end})
            cur, start = "", None
            continue
        if start is None:
            start = s
        cur += ch
        end = e
    if cur:
        words.append({"word": cur, "start": start, "end": end})
    return words


async def _edge(text: str, cfg: dict, out: Path):
    import edge_tts
    com = edge_tts.Communicate(text, cfg.get("tts_voice", "es-MX-JorgeNeural"),
                               rate=cfg.get("tts_rate", "+10%"), pitch=cfg.get("tts_pitch", "+0Hz"),
                               boundary="WordBoundary")
    words = []
    with open(out, "wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                s = chunk["offset"] / 1e7
                words.append({"word": chunk["text"], "start": s, "end": s + chunk["duration"] / 1e7})
    return words


def synthesize(text: str, cfg: dict, out: Path):
    if os.environ.get("ELEVENLABS_API_KEY"):
        try:
            return _elevenlabs(text, cfg, out)
        except Exception as e:
            print(f"  [voice] ElevenLabs failed ({e}); falling back to edge-tts")
    try:
        words = asyncio.run(asyncio.wait_for(_edge(text, cfg, out), timeout=90))
        if out.exists() and out.stat().st_size > 1000:
            return words
    except Exception as e:
        print(f"  [voice] edge-tts unavailable ({type(e).__name__})")
    return None


def estimate(text: str, start: float = 0.0, wps: float = 2.9):
    """Fallback timings when there is no TTS (silent preview)."""
    words, t = [], start
    for w in text.split():
        d = max(0.18, len(w) / (wps * 5.2))
        words.append({"word": w, "start": t, "end": t + d})
        t += d + 0.04
    return words
