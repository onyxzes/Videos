"""Send a video to TikTok with the Content Posting API.

Secrets (env): TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REFRESH_TOKEN
Modes (config.json -> platforms.tiktok.mode):
  "inbox"  -> video lands in your TikTok inbox/drafts; you add the trending
              sound and tap Post in the app (scope video.upload). Recommended:
              trending sounds can't be attached through the API.
  "direct" -> publishes directly (scope video.publish). Until TikTok audits
              your app, privacy_level must be SELF_ONLY (only you can see it).
"""
import os
import time

import requests

API = "https://open.tiktokapis.com/v2"
CHUNK = 10 * 1024 * 1024


def configured() -> bool:
    return all(os.environ.get(k) for k in
               ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN"))


def _access_token() -> str:
    r = requests.post(f"{API}/oauth/token/", data={
        "client_key": os.environ["TIKTOK_CLIENT_KEY"],
        "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
        "grant_type": "refresh_token",
        "refresh_token": os.environ["TIKTOK_REFRESH_TOKEN"]}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "access_token" not in data:
        raise RuntimeError(f"TikTok token refresh failed: {data}")
    return data["access_token"]


def upload(video_path: str, caption: str, mode: str = "inbox", privacy_level: str = "SELF_ONLY") -> dict:
    token = _access_token()
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
    size = os.path.getsize(video_path)
    chunk = size if size <= CHUNK else CHUNK
    count = max(1, size // chunk) if size > CHUNK else 1
    source = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk, "total_chunk_count": count}

    if mode == "direct":
        body = {"post_info": {"title": caption[:2200], "privacy_level": privacy_level,
                              "disable_comment": False, "disable_duet": False,
                              "disable_stitch": False, "is_aigc": True},
                "source_info": source}
        url = f"{API}/post/publish/video/init/"
    else:
        body = {"source_info": source}
        url = f"{API}/post/publish/inbox/video/init/"

    r = requests.post(url, headers=h, json=body, timeout=60)
    r.raise_for_status()
    data = r.json()["data"]
    publish_id, upload_url = data["publish_id"], data["upload_url"]

    with open(video_path, "rb") as f:
        for i in range(count):
            start = i * chunk
            end = size - 1 if i == count - 1 else start + chunk - 1
            f.seek(start)
            part = f.read(end - start + 1)
            requests.put(upload_url, data=part, timeout=600, headers={
                "Content-Type": "video/mp4", "Content-Length": str(len(part)),
                "Content-Range": f"bytes {start}-{end}/{size}"}).raise_for_status()

    status = None
    for _ in range(30):
        s = requests.post(f"{API}/post/publish/status/fetch/", headers=h,
                          json={"publish_id": publish_id}, timeout=30).json()
        status = s.get("data", {}).get("status")
        if status in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
            break
        if status == "FAILED":
            raise RuntimeError(f"TikTok failed: {s}")
        time.sleep(10)
    return {"id": publish_id, "status": status, "mode": mode}
