"""Render a vertical (1080x1920) retention-optimized short.

Layers, top to bottom:
  - progress bar (tells the viewer "it's short, stay")
  - section header that pops in on every new point
  - karaoke captions: 1-3 words at a time, current word highlighted
  - "satisfying" physics loop: a ball bouncing inside a glowing ring, growing on
    every bounce with a rising musical note; it nearly fills the ring by the end,
    which gives a second reason to keep watching
Audio: AI voice (voice.py) + synthesized bounce notes + whooshes + soft pad.
Everything is generated, so there is nothing copyrighted in the video.

Usage: python src/render.py content/queue/<id>.json out/<id>.mp4
"""
from __future__ import annotations

import colorsys
import json
import math
import random
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import voice  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FONT_BOLD = str(ROOT / "assets/fonts/Inter-Black.otf")
FONT_SEMI = str(ROOT / "assets/fonts/Inter-SemiBold.otf")
W, H, FPS, SR = 1080, 1920, 30, 44100
GAP = 0.22  # pause between sections (s)

# (top, bottom, accent/highlight)
PALETTES = [
    ((18, 16, 40), (70, 25, 120), (255, 214, 10)),
    ((4, 30, 48), (0, 105, 120), (0, 255, 200)),
    ((40, 6, 14), (150, 25, 45), (255, 214, 10)),
    ((10, 10, 12), (40, 40, 48), (0, 230, 118)),
    ((26, 14, 4), (150, 70, 10), (120, 220, 255)),
]
RING_C, RING_R = (540, 1290), 330


def run(cmd, **kw):
    res = subprocess.run(cmd, capture_output=True, **kw)
    if res.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed:\n{res.stderr[-2000:]!r}")
    return res.stdout


def probe_duration(path: Path) -> float:
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "default=nw=1:nk=1", str(path)], text=True).strip())


# ---------------- text helpers ----------------

_fonts: dict = {}


def font(path, size):
    key = (path, size)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(path, size)
    return _fonts[key]


def wrap(draw, text, fpath, size, max_w):
    f = font(fpath, size)
    lines, cur = [], ""
    for w in text.split():
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=f) <= max_w or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def text_block(text, fpath, max_w, max_lines, start, color=(255, 255, 255), stroke=7):
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    size = start
    while size > 40:
        lines = wrap(probe, text, fpath, size, max_w)
        if len(lines) <= max_lines and all(probe.textlength(l, font=font(fpath, size)) <= max_w for l in lines):
            break
        size -= 4
    f = font(fpath, size)
    lh = int(size * 1.15)
    img = Image.new("RGBA", (max_w + 2 * stroke + 20, lh * len(lines) + 2 * stroke + 10), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        x = (img.width - d.textlength(ln, font=f)) / 2
        d.text((x, stroke + i * lh), ln, font=f, fill=color, stroke_width=stroke, stroke_fill=(0, 0, 0))
    return img


# ---------------- layers ----------------

def background(palette) -> Image.Image:
    top, bottom, accent = palette
    base = Image.new("RGB", (W, H), top)
    mask = Image.linear_gradient("L").resize((W, H))
    img = Image.composite(Image.new("RGB", (W, H), bottom), base, mask).convert("RGBA")
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    cx, cy = RING_C
    gd.ellipse((cx - RING_R - 80, cy - RING_R - 80, cx + RING_R + 80, cy + RING_R + 80), fill=(*accent, 35))
    return Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(90)))


def header_img(text, label, accent):
    body = text_block(text, FONT_BOLD, 900, 3, 78)
    pad = 28
    lab_h = 0
    if label:
        lf = font(FONT_SEMI, 40)
        lw = int(ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(label, font=lf))
        lab_h = 70
    w, h = max(body.width, 900) + 2 * pad, body.height + 2 * pad + lab_h
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, lab_h // 2, w, h), radius=40, fill=(0, 0, 0, 120))
    if label:
        x = (w - lw) // 2
        d.rounded_rectangle((x - 26, 0, x + lw + 26, 62), radius=31, fill=(*accent, 255))
        d.text((x, 8), label, font=lf, fill=(10, 10, 10))
    img.alpha_composite(body, ((w - body.width) // 2, lab_h + pad - 6))
    return img


def caption_img(words, active, accent):
    f = font(FONT_BOLD, 104)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    space = probe.textlength(" ", font=f)
    widths = [probe.textlength(w, font=f) for w in words]
    total = sum(widths) + space * (len(words) - 1)
    scale = min(1.0, 960 / total) if total else 1
    if scale < 1:
        f = font(FONT_BOLD, int(104 * scale))
        space = probe.textlength(" ", font=f)
        widths = [probe.textlength(w, font=f) for w in words]
        total = sum(widths) + space * (len(words) - 1)
    img = Image.new("RGBA", (int(total) + 40, int(f.size * 1.4) + 30), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = 20
    for i, (w, wd) in enumerate(zip(words, widths)):
        col = accent if i == active else (255, 255, 255)
        d.text((x, 12), w, font=f, fill=col, stroke_width=9, stroke_fill=(0, 0, 0))
        x += wd + space
    return img


def chunk_words(words):
    """Group words into 1-3 word caption chunks, breaking at punctuation."""
    chunks, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        if len(cur) == 3 or w["word"][-1:] in ".,!?:;" or len(w["word"]) > 9:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


# ---------------- physics ----------------

class BallSim:
    def __init__(self, total_time, seed):
        rnd = random.Random(seed)
        self.p = np.array([rnd.uniform(-60, 60), -120.0])
        self.v = np.array([rnd.choice([-1, 1]) * rnd.uniform(250, 420), 0.0])
        self.r, self.r0, self.rmax = 26.0, 26.0, RING_R * 0.86
        self.T = total_time
        self.t = 0.0
        self.bounces: list[float] = []
        self.trail: list[tuple] = []
        self.flash = 0.0
        self.hue = rnd.random()

    def step(self, dt):
        g = np.array([0.0, 1500.0])
        for _ in range(4):
            h = dt / 4
            self.v += g * h
            self.p += self.v * h
            dist = np.linalg.norm(self.p)
            if dist + self.r >= RING_R:
                n = self.p / dist
                self.p = n * (RING_R - self.r - 0.5)
                self.v = self.v - 2 * np.dot(self.v, n) * n
                speed = np.linalg.norm(self.v)
                target = max(speed * 1.0, 760.0)  # keep it lively
                self.v = self.v / max(speed, 1e-6) * min(target, 1700.0)
                self.v += np.array([-n[1], n[0]]) * random.uniform(-60, 60)
                frac = min(1.0, (self.t + h) / self.T)
                self.r = max(self.r, self.r0 + (self.rmax - self.r0) * frac ** 1.3)
                self.bounces.append(self.t + h)
                self.flash = 1.0
            self.t += h
        self.trail.append((self.p.copy(), self.r))
        self.trail = self.trail[-10:]
        self.flash *= 0.82
        self.hue = (self.hue + 0.004) % 1

    def draw(self, frame: Image.Image):
        size = RING_R * 2 + 60
        layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        o = size / 2
        rc = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(self.hue, 0.6, 1.0))
        width = int(10 + 14 * self.flash)
        d.ellipse((o - RING_R - width / 2, o - RING_R - width / 2, o + RING_R + width / 2, o + RING_R + width / 2),
                  outline=(*rc, 255), width=width)
        n = len(self.trail)
        for i, (p, r) in enumerate(self.trail):
            a = int(25 + 110 * (i + 1) / n)
            hc = tuple(int(c * 255) for c in colorsys.hsv_to_rgb((self.hue + 0.5 - i * 0.01) % 1, 0.75, 1.0))
            d.ellipse((o + p[0] - r, o + p[1] - r, o + p[0] + r, o + p[1] + r), fill=(*hc, a))
        p, r = self.trail[-1]
        bc = tuple(int(c * 255) for c in colorsys.hsv_to_rgb((self.hue + 0.5) % 1, 0.8, 1.0))
        d.ellipse((o + p[0] - r, o + p[1] - r, o + p[0] + r, o + p[1] + r), fill=(*bc, 255),
                  outline=(255, 255, 255, 255), width=5)
        frame.alpha_composite(layer, (int(RING_C[0] - o), int(RING_C[1] - o)))


# ---------------- audio ----------------

def write_wav(path: Path, samples: np.ndarray):
    s = np.clip(samples, -1, 1)
    st = (np.stack([s, s], axis=1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(st.tobytes())


def sfx_track(total, bounces, transitions) -> np.ndarray:
    out = np.zeros(int((total + 1) * SR))
    scale = [0, 2, 4, 7, 9]  # major pentatonic
    for i, bt in enumerate(bounces):
        semis = scale[i % 5] + 12 * ((i // 5) % 3)
        f = 392.0 * 2 ** (semis / 12)
        n = int(0.45 * SR)
        t = np.arange(n) / SR
        tone = (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)) * np.exp(-t * 9) * 0.16
        s = int(bt * SR)
        out[s:s + n] += tone[: len(out) - s]
    rng = np.random.default_rng(1)
    for tt in transitions:
        n = int(0.35 * SR)
        t = np.arange(n) / SR
        noise = rng.standard_normal(n)
        # crude band sweep: smoothed noise with rising envelope
        k = np.ones(12) / 12
        sw = np.convolve(noise, k, mode="same") * np.sin(np.pi * t / t[-1]) ** 2 * 0.35
        s = max(0, int((tt - 0.12) * SR))
        out[s:s + n] += sw[: len(out) - s]
    return out


def pad_bed(seconds, path: Path):
    expr = ("0.10*sin(2*PI*220*t)+0.08*sin(2*PI*277.18*t)+0.07*sin(2*PI*329.63*t)"
            "+0.05*sin(2*PI*110*t)")
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"aevalsrc='{expr}':s={SR}:d={seconds:.2f}",
         "-af", f"tremolo=f=2:d=0.4,lowpass=f=1200,afade=t=in:d=1,"
                f"afade=t=out:st={max(0, seconds - 1.5):.2f}:d=1.5,volume=0.35",
         "-ac", "2", str(path)])


# ---------------- main ----------------

def render(script_path: Path, out_path: Path) -> Path:
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    script = json.loads(script_path.read_text(encoding="utf-8"))
    palette = PALETTES[sum(map(ord, script["id"])) % len(PALETTES)]
    accent = palette[2]

    sections = [{"text": script["hook"], "voiceover": script.get("hook_voiceover", script["hook"])}]
    sections += script["slides"]
    sections.append({"text": script["cta"], "voiceover": script.get("cta_voiceover", script["cta"])})

    tmp = Path(tempfile.mkdtemp(prefix="render_"))
    try:
        # 1) voice per section, with word timings on a global clock
        t, words, starts, vo_files, has_voice = 0.0, [], [], [], True
        for i, s in enumerate(sections):
            starts.append(t)
            mp3 = tmp / f"vo{i}.mp3"
            ws = voice.synthesize(s["voiceover"], cfg, mp3) if has_voice else None
            if ws:
                dur = probe_duration(mp3)
                vo_files.append((mp3, t))
            else:
                has_voice = False
                ws = voice.estimate(s["voiceover"])
                dur = ws[-1]["end"] + 0.1
            for w in ws:
                words.append({"word": w["word"].upper(), "start": w["start"] + t,
                              "end": w["end"] + t, "section": i})
            t += dur + GAP
        total = t + 0.5
        n_frames = int(total * FPS)

        # caption chunks with their display windows
        chunks = chunk_words(words)
        windows = []
        for ci, idx in enumerate(chunks):
            st = words[idx[0]]["start"]
            en = words[chunks[ci + 1][0]]["start"] if ci + 1 < len(chunks) else total
            windows.append((st, en))

        # 2) frames
        bg = background(palette)
        headers = [header_img(s["text"], script.get("label") if i == 0 else None, accent)
                   for i, s in enumerate(sections)]
        cap_cache: dict = {}
        sim = BallSim(total, script["id"])
        video_tmp = tmp / "video.mp4"
        ff = subprocess.Popen(
            ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
             "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
             "-pix_fmt", "yuv420p", str(video_tmp)], stdin=subprocess.PIPE)

        sec, ci = 0, 0
        for fi in range(n_frames):
            now = fi / FPS
            while sec + 1 < len(starts) and now >= starts[sec + 1] - 0.05:
                sec += 1
            while ci + 1 < len(windows) and now >= windows[ci + 1][0]:
                ci += 1

            frame = bg.copy()
            sim.step(1 / FPS)
            sim.draw(frame)

            # header with pop-in
            h = headers[sec]
            age = now - (starts[sec] - 0.05 if sec else 0)
            k = 1.0 if age > 0.12 or sec == 0 else 0.85 + 0.15 * age / 0.12
            hh = h if k == 1.0 else h.resize((int(h.width * k), int(h.height * k)))
            frame.alpha_composite(hh, ((W - hh.width) // 2, 150 + (h.height - hh.height) // 2))

            # karaoke caption
            if now >= windows[0][0] - 0.05:
                idx = chunks[ci]
                active = max([j for j, wi in enumerate(idx) if words[wi]["start"] <= now] or [0])
                key = (ci, active)
                if key not in cap_cache:
                    cap_cache = {k2: v for k2, v in cap_cache.items() if k2[0] >= ci - 1}
                    cap_cache[key] = caption_img([words[wi]["word"] for wi in idx], active, accent)
                c = cap_cache[key]
                age = now - windows[ci][0]
                k = 1.0 if age > 0.08 else 0.8 + 0.2 * max(0, age) / 0.08
                cc = c if k == 1.0 else c.resize((int(c.width * k), int(c.height * k)))
                cy = 150 + headers[sec].height + 40
                frame.alpha_composite(cc, ((W - cc.width) // 2, cy + (c.height - cc.height) // 2))

            # progress bar
            d = ImageDraw.Draw(frame)
            d.rectangle((0, 0, W, 14), fill=(0, 0, 0, 255))
            d.rectangle((0, 0, int(W * now / total), 14), fill=(*accent, 255))

            ff.stdin.write(frame.convert("RGB").tobytes())
        ff.stdin.close()
        if ff.wait() != 0:
            raise RuntimeError("ffmpeg video encode failed")

        # 3) audio mix
        sfx = tmp / "sfx.wav"
        write_wav(sfx, sfx_track(total, sim.bounces, starts[1:]))
        bed = tmp / "bed.wav"
        pad_bed(total, bed)
        inputs = ["-i", str(video_tmp), "-i", str(sfx), "-i", str(bed)]
        filt, mix = [], ["[s]", "[b]"]
        filt.append("[1:a]volume=0.9[s]")
        filt.append("[2:a]volume=0.6[b]")
        for j, (mp3, st) in enumerate(vo_files):
            inputs += ["-i", str(mp3)]
            ms = int(st * 1000)
            filt.append(f"[{3 + j}:a]adelay={ms}|{ms},volume=1.6[v{j}]")
            mix.append(f"[v{j}]")
        filt.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=longest:normalize=0,"
                    f"alimiter=limit=0.95,atrim=0:{total:.2f}[a]")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filt),
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(out_path)])
        print(f"  rendered {out_path} ({total:.1f}s, voice={'yes' if has_voice else 'no'}, "
              f"bounces={len(sim.bounces)})")
        return out_path
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    render(Path(sys.argv[1]), Path(sys.argv[2]))
