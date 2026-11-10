"""Turn today's trends into new video scripts with Claude (env ANTHROPIC_API_KEY).

Writes content/queue/<id>.json files in the same format render.py expects.
Usage: python src/write_scripts.py [count]
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

import anthropic
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent


class Slide(BaseModel):
    text: str = Field(description="On-screen text, max ~12 words, no emojis")
    voiceover: str = Field(description="What the narrator says, 1-2 short sentences")


class VideoScript(BaseModel):
    slug: str = Field(description="short-kebab-case-id")
    label: str = Field(description="1-2 word tag shown on the first slide, uppercase")
    topic: str
    trend_reason: str = Field(description="Which trend this rides and why now")
    hook: str = Field(description="First-second hook, max ~10 words, creates curiosity")
    hook_voiceover: str
    slides: list[Slide] = Field(description="3-5 slides")
    cta: str
    cta_voiceover: str
    title: str = Field(description="YouTube title, max 80 chars")
    caption: str = Field(description="Caption for TikTok/Instagram, may include 1-2 emojis")
    hashtags: list[str] = Field(description="4-6 hashtags without #")


class Batch(BaseModel):
    scripts: list[VideoScript]


SYSTEM = """You write scripts for faceless vertical short videos (TikTok, Reels, YouTube Shorts)
in {language} for {audience}. Niche: {niche}.
Rules:
- Pick topics from the trend list that a general audience cares about and that suit a
  text-plus-voiceover format: explainers, surprising facts, practical tips, countdowns.
- Skip tragedies, deaths, crimes, politics, medical claims, and private individuals.
- Only state facts you are confident are true and stable; if unsure, write tips or
  questions instead of facts. Never invent numbers.
- Do not use song lyrics, copyrighted characters, or celebrity likeness as content.
- Total spoken length 20-40 seconds. Hook must work with sound off.
- Each script must be different from the already-published titles given."""


def main(count: int = 3):
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    trend_files = sorted((ROOT / "trends").glob("*.json"))
    trends = json.loads(trend_files[-1].read_text(encoding="utf-8")) if trend_files else []
    done = [json.loads(p.read_text(encoding="utf-8"))["title"]
            for d in ("queue", "published") for p in (ROOT / "content" / d).glob("*.json")]
    today = dt.date.today().isoformat()

    client = anthropic.Anthropic()
    resp = client.messages.parse(
        model="claude-opus-5-5",
        max_tokens=16000,
        output_config={"effort": "medium"},
        system=SYSTEM.format(**cfg),
        messages=[{"role": "user", "content":
                   f"Today is {today}. Write {count} new scripts.\n\n"
                   f"Trending now:\n{json.dumps(trends[:80], ensure_ascii=False)}\n\n"
                   f"Already made (don't repeat):\n{json.dumps(done[-60:], ensure_ascii=False)}"}],
        output_format=Batch,
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        print(f"  [writer] no scripts (stop_reason={resp.stop_reason})")
        return []

    written = []
    for s in resp.parsed_output.scripts:
        data = s.model_dump()
        slug = re.sub(r"[^a-z0-9-]", "", data.pop("slug").lower())[:40] or "video"
        data = {"id": f"{today}-{slug}", **data}
        path = ROOT / "content" / "queue" / f"{data['id']}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(path)
        print(f"  [writer] + {path.name}: {data['title']}")
    return written


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
