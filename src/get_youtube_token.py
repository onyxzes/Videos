"""Run ONCE on your own computer to get YT_REFRESH_TOKEN.

1. Google Cloud Console -> new project -> enable "YouTube Data API v3".
2. OAuth consent screen (External) -> add yourself as test user.
3. Credentials -> Create OAuth client ID -> "Desktop app" -> download JSON as client_secret.json.
4. pip install google-auth-oauthlib && python src/get_youtube_token.py client_secret.json
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

path = sys.argv[1] if len(sys.argv) > 1 else "client_secret.json"
flow = InstalledAppFlow.from_client_secrets_file(
    path, scopes=["https://www.googleapis.com/auth/youtube.upload"])
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
cfg = json.load(open(path))["installed"]
print("\nAdd these as GitHub repository secrets:\n")
print("YT_CLIENT_ID     =", cfg["client_id"])
print("YT_CLIENT_SECRET =", cfg["client_secret"])
print("YT_REFRESH_TOKEN =", creds.refresh_token)
