"""Nightly job: refresh trends, top up the script queue, render the next
video(s) and publish to every platform that has credentials configured.

Usage: python src/run_nightly.py [--dry-run]
  --dry-run  render only, don't upload or move files
"""
import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render  # noqa: E402
import trends  # noqa: E402
import upload_instagram  # noqa: E402
import upload_tiktok  # noqa: E402
import upload_youtube  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
QUEUE, PUBLISHED, OUT = ROOT / "content/queue", ROOT / "content/published", ROOT / "out"


def main(dry_run: bool = False):
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    plats = cfg["platforms"]

    trends.collect()
    if len(list(QUEUE.glob("*.json"))) < cfg.get("min_queue", 4) and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import write_scripts
            write_scripts.main(3)
        except Exception:
            traceback.print_exc()

    queue = sorted(QUEUE.glob("*.json"),
                   key=lambda p: (json.loads(p.read_text(encoding="utf-8")).get("priority", 50), p.name))
    if not queue:
        print("Queue empty: nothing to publish. Add scripts or set ANTHROPIC_API_KEY.")
        return

    for script_path in queue[: cfg.get("videos_per_run", 1)]:
        script = json.loads(script_path.read_text(encoding="utf-8"))
        print(f"== {script['id']}: {script['title']}")
        video = OUT / f"{script['id']}.mp4"
        render.render(script_path, video)
        if dry_run:
            continue

        results = script.setdefault("results", {})
        jobs = [
            ("youtube", upload_youtube, lambda: upload_youtube.upload(
                str(video), script, plats["youtube"].get("privacy", "public"))),
            ("instagram", upload_instagram, lambda: upload_instagram.upload(
                str(video), script, plats["instagram"].get("share_to_feed", True))),
            ("tiktok", upload_tiktok, lambda: upload_tiktok.upload(
                str(video), script, plats["tiktok"].get("mode", "inbox"),
                plats["tiktok"].get("privacy_level", "SELF_ONLY"))),
        ]
        for name, mod, job in jobs:
            if not plats.get(name, {}).get("enabled") or name in results:
                continue
            if not mod.configured():
                print(f"  [{name}] skipped: credentials not set")
                continue
            try:
                results[name] = job()
                print(f"  [{name}] ok: {results[name]}")
            except Exception as e:
                traceback.print_exc()
                results.setdefault("errors", {})[name] = str(e)[:500]

        ok = [k for k in results if k != "errors"]
        if ok:
            PUBLISHED.mkdir(parents=True, exist_ok=True)
            (PUBLISHED / script_path.name).write_text(
                json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
            script_path.unlink()
        else:
            script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
            print("  nothing published; script stays in the queue")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
