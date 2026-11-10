"""Publish a Reel via the Instagram Graph API (resumable upload, no public URL needed).

Secrets (env): IG_USER_ID, IG_ACCESS_TOKEN
Requires an Instagram Professional (Business/Creator) account linked to a
Facebook Page, and a Meta app with instagram_content_publish permission.
Use a long-lived token (60 days) and refresh it before it expires.
"""
import os
import time

import requests

GRAPH = "https://graph.facebook.com/v21.0"


def configured() -> bool:
    return bool(os.environ.get("IG_USER_ID") and os.environ.get("IG_ACCESS_TOKEN"))


def upload(video_path: str, script: dict, share_to_feed: bool = True) -> dict:
    uid, token = os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"]
    caption = script["caption"] + "\n\n" + " ".join(f"#{t}" for t in script.get("hashtags", []))

    r = requests.post(f"{GRAPH}/{uid}/media", data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption,
        "share_to_feed": str(share_to_feed).lower(), "access_token": token}, timeout=60)
    r.raise_for_status()
    container = r.json()["id"]

    size = os.path.getsize(video_path)
    with open(video_path, "rb") as f:
        r = requests.post(f"https://rupload.facebook.com/ig-api-upload/v21.0/{container}",
                          headers={"Authorization": f"OAuth {token}", "offset": "0",
                                   "file_size": str(size)}, data=f, timeout=600)
    r.raise_for_status()

    for _ in range(60):  # wait up to ~10 min for processing
        s = requests.get(f"{GRAPH}/{container}", params={
            "fields": "status_code,status", "access_token": token}, timeout=30).json()
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram processing error: {s}")
        time.sleep(10)
    else:
        raise TimeoutError("Instagram processing timed out")

    r = requests.post(f"{GRAPH}/{uid}/media_publish",
                      data={"creation_id": container, "access_token": token}, timeout=60)
    r.raise_for_status()
    media_id = r.json()["id"]
    link = requests.get(f"{GRAPH}/{media_id}", params={"fields": "permalink", "access_token": token},
                        timeout=30).json().get("permalink")
    return {"id": media_id, "url": link}
