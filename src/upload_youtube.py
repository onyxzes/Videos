"""Upload a Short to YouTube with the YouTube Data API v3.

Secrets (env): YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
Get the refresh token once on your computer with: python src/get_youtube_token.py

Note: Google locks uploads from *unverified* API projects to private until the
project passes Google's audit. Request the audit in Google Cloud Console.
"""
import os

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


def configured() -> bool:
    return all(os.environ.get(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))


def upload(video_path: str, script: dict, caption: str, privacy: str = "public") -> dict:
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    tags = script.get("hashtags", [])
    body = {
        "snippet": {
            "title": script["title"][:100],
            "description": caption,
            "tags": tags + ["shorts"],
            "categoryId": "22",  # People & Blogs
            "defaultLanguage": "es",
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": True},
    }
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return {"id": resp["id"], "url": f"https://youtube.com/shorts/{resp['id']}"}
