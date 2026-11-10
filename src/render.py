"""Render a vertical (1080x1920) short video from a script JSON.

Format: faceless "text + voiceover" slides with a slow zoom, progress bar,
synthesized royalty-free background pad, and Spanish TTS (edge-tts) when the
network allows it. Works on TikTok, Reels and YouTube Shorts.

Usage: python src/render.py content/queue/<id>.json out/<id>.mp4
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT_BOLD = ROOT / "assets/fonts/Inter-Black.otf"
FONT_SEMI = ROOT / "assets/fonts/Inter-SemiBold.otf"
W, H, FPS = 1080, 1920, 30

PALETTES = [
    ((20, 20, 40), (90, 30, 140), (255, 214, 10)),     # night purple / yellow
    ((5, 40, 60), (0, 140, 150), (255, 255, 255)),     # teal
    ((60, 10, 20), (200, 40, 60), (255, 230, 200)),    # red (holiday)
    ((15, 15, 15), (60, 60, 60), (0, 230, 118)),       # dark / neon green
    ((30, 20, 5), (210, 120, 20), (255, 255, 255)),    # amber
]


def load_config() -> dict:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def run(cmd: list[str]) -> str:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed:\n{res.stderr[-2000:]}")
    return res.stdout


def duration(path: Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(path)])
    return float(out.strip())


# ---------- visuals ----------

def gradient(top, bottom) -> Image.Image:
    base = Image.new("RGB", (W, H), top)
    overlay = Image.new("RGB", (W, H), bottom)
    mask = Image.linear_gradient("L").resize((W, H))
    return Image.composite(overlay, base, mask)


def fit_text(draw, text, font_path, max_w, max_h, start=120, min_size=48):
    size = start
    while size >= min_size:
        font = ImageFont.truetype(str(font_path), size)
        chars = max(8, int(max_w / (size * 0.55)))
        lines = []
        for para in text.split("\n"):
            lines += textwrap.wrap(para, width=chars) or [""]
        spacing = int(size * 0.25)
        boxes = [draw.textbbox((0, 0), ln, font=font) for ln in lines]
        tw = max(b[2] - b[0] for b in boxes)
        th = sum(b[3] - b[1] for b in boxes) + spacing * (len(lines) - 1)
        if tw <= max_w and th <= max_h:
            return font, lines, spacing
        size -= 6
    return font, lines, spacing


def slide_image(text: str, palette, index: int, total: int, label: str | None) -> Image.Image:
    top, bottom, accent = palette
    img = gradient(top, bottom)
    # soft decorative blobs
    blob = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(blob)
    bd.ellipse((-200, 1300, 600, 2100), fill=(*accent, 40))
    bd.ellipse((600, -200, 1400, 600), fill=(*accent, 30))
    img = Image.alpha_composite(img.convert("RGBA"), blob.filter(ImageFilter.GaussianBlur(80)))
    d = ImageDraw.Draw(img)

    if label:
        f = ImageFont.truetype(str(FONT_SEMI), 44)
        bb = d.textbbox((0, 0), label, font=f)
        pad = 24
        x = (W - (bb[2] - bb[0])) // 2
        d.rounded_rectangle((x - pad, 260 - pad // 2, x + bb[2] - bb[0] + pad, 260 + bb[3] - bb[1] + pad),
                            radius=30, fill=(*accent, 255))
        d.text((x, 260), label, font=f, fill=top)

    # keep text inside the platform "safe zone" (UI overlays bottom/right)
    max_w, max_h = W - 200, 900
    font, lines, spacing = fit_text(d, text, FONT_BOLD, max_w, max_h)
    boxes = [d.textbbox((0, 0), ln, font=font) for ln in lines]
    total_h = sum(b[3] - b[1] for b in boxes) + spacing * (len(lines) - 1)
    y = 420 + (max_h - total_h) // 2
    for ln, b in zip(lines, boxes):
        x = (W - (b[2] - b[0])) // 2
        d.text((x, y), ln, font=font, fill=(255, 255, 255),
               stroke_width=6, stroke_fill=(0, 0, 0))
        y += (b[3] - b[1]) + spacing

    # progress dots
    r, gap = 12, 40
    sx = (W - (total - 1) * gap) // 2
    for i in range(total):
        c = accent if i <= index else (255, 255, 255)
        a = 255 if i <= index else 90
        d.ellipse((sx + i * gap - r, 1500 - r, sx + i * gap + r, 1500 + r), fill=(*c, a))
    return img.convert("RGB")


# ---------- audio ----------

async def _tts(text: str, voice: str, rate: str, out: Path):
    import edge_tts  # imported lazily so rendering works without it
    await edge_tts.Communicate(text, voice, rate=rate).save(str(out))


def tts(text: str, voice: str, rate: str, out: Path) -> bool:
    try:
        asyncio.run(asyncio.wait_for(_tts(text, voice, rate, out), timeout=60))
        return out.exists() and out.stat().st_size > 1000
    except Exception as e:  # network blocked, voice missing, etc.
        print(f"  [tts] unavailable ({type(e).__name__}): continuing without voice")
        return False


def music_bed(seconds: float, out: Path):
    """Royalty-free ambient pad (synthesized chord with gentle pulse)."""
    expr = ("0.10*sin(2*PI*220*t)+0.08*sin(2*PI*277.18*t)+0.07*sin(2*PI*329.63*t)"
            "+0.05*sin(2*PI*110*t)")
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", f"aevalsrc='{expr}':s=44100:d={seconds:.2f}",
         "-af", "tremolo=f=2:d=0.4,lowpass=f=1200,"
                f"afade=t=in:d=1,afade=t=out:st={max(0, seconds - 1.5):.2f}:d=1.5,volume=0.6",
         "-ac", "2", str(out)])


# ---------- main ----------

def render(script_path: Path, out_path: Path) -> Path:
    cfg = load_config()
    script = json.loads(script_path.read_text(encoding="utf-8"))
    voice = cfg.get("tts_voice", "es-MX-JorgeNeural")
    rate = cfg.get("tts_rate", "+8%")
    palette = PALETTES[sum(map(ord, script["id"])) % len(PALETTES)]

    slides = [{"text": script["hook"], "voiceover": script.get("hook_voiceover", script["hook"])}]
    slides += script["slides"]
    slides.append({"text": script["cta"], "voiceover": script.get("cta_voiceover", script["cta"])})

    tmp = Path(tempfile.mkdtemp(prefix="render_"))
    try:
        segments, voice_parts, have_voice = [], [], True
        for i, s in enumerate(slides):
            label = script.get("label") if i == 0 else None
            png = tmp / f"s{i}.png"
            slide_image(s["text"], palette, i, len(slides), label).save(png)

            vo = tmp / f"v{i}.mp3"
            if have_voice and tts(s["voiceover"], voice, rate, vo):
                dur = duration(vo) + 0.35
                voice_parts.append((vo, dur))
            else:
                have_voice = False
                words = len(s["voiceover"].split())
                dur = max(2.2, min(6.0, words / 2.8))
                voice_parts.append((None, dur))

            frames = int(dur * FPS)
            seg = tmp / f"s{i}.mp4"
            run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", str(png),
                 "-vf", f"scale=1296:2304,zoompan=z='min(zoom+0.0007,1.08)':d={frames}"
                        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},format=yuv420p",
                 "-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                 str(seg)])
            segments.append(seg)

        concat = tmp / "list.txt"
        concat.write_text("".join(f"file '{p}'\n" for p in segments))
        video = tmp / "video.mp4"
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat),
             "-c", "copy", str(video)])
        total = duration(video)

        bed = tmp / "bed.wav"
        music_bed(total, bed)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        if have_voice and all(v for v, _ in voice_parts):
            # pad each voice clip to its slide length, then concat
            padded = []
            for i, (v, dur) in enumerate(voice_parts):
                p = tmp / f"vp{i}.wav"
                run(["ffmpeg", "-y", "-v", "error", "-i", str(v), "-af", f"apad=whole_dur={dur:.3f}",
                     "-ar", "44100", "-ac", "2", str(p)])
                padded.append(p)
            (tmp / "alist.txt").write_text("".join(f"file '{p}'\n" for p in padded))
            vo_all = tmp / "vo.wav"
            run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                 "-i", str(tmp / "alist.txt"), str(vo_all)])
            run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(vo_all), "-i", str(bed),
                 "-filter_complex", "[2:a]volume=0.35[b];[1:a][b]amix=inputs=2:duration=first:normalize=0[a]",
                 "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                 "-shortest", "-movflags", "+faststart", str(out_path)])
        else:
            run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(bed),
                 "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                 "-shortest", "-movflags", "+faststart", str(out_path)])
        print(f"  rendered {out_path} ({total:.1f}s, voice={'yes' if have_voice else 'no'})")
        return out_path
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    render(Path(sys.argv[1]), Path(sys.argv[2]))
