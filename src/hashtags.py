"""Per-platform hashtag strategy.

Mix = trend tags (what people search today) + niche tags (who should see it)
+ broad discovery tags, trimmed to what each platform rewards:
  - TikTok: 3-5 tags; #parati/#fyp help classify the video as For You content.
  - Instagram: hard limit of 5 hashtags per Reel (since Dec 2025).
  - YouTube: the first 3 hashtags show above the title; #Shorts helps classify.
"""
import re

LIMITS = {"tiktok": 5, "instagram": 5, "youtube": 3}


def clean(tag: str) -> str:
    tag = tag.strip().lstrip("#").lower()
    tag = re.sub(r"[áàä]", "a", tag)
    tag = re.sub(r"[éèë]", "e", tag)
    tag = re.sub(r"[íìï]", "i", tag)
    tag = re.sub(r"[óòö]", "o", tag)
    tag = re.sub(r"[úùü]", "u", tag)
    return re.sub(r"[^a-z0-9ñ_]", "", tag)


def for_platform(script: dict, platform: str, cfg: dict) -> list[str]:
    broad = cfg.get("hashtags", {}).get("broad", {}).get(platform, [])
    tags = [clean(t) for t in script.get("hashtags", [])]
    limit = LIMITS[platform]
    n_broad = 1 if platform != "youtube" else 0
    picked = []
    for t in tags[: limit - n_broad] + [clean(b) for b in broad]:
        if t and t not in picked:
            picked.append(t)
    picked = picked[:limit]
    if platform == "youtube" and "shorts" not in picked:
        picked = picked[:2] + ["shorts"]
    return ["#" + t for t in picked]


def caption(script: dict, platform: str, cfg: dict) -> str:
    return f"{script['caption']}\n\n{' '.join(for_platform(script, platform, cfg))}"
