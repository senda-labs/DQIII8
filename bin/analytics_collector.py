import sqlite3
import os
import requests
from datetime import datetime
from pathlib import Path

JARVIS = Path("/root/jarvis")
DB = JARVIS / "database" / "jarvis_metrics.db"
ENV = JARVIS / ".env"


def load_env():
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def calculate_performance_score(metrics: dict) -> float:
    try:
        conn = sqlite3.connect(DB)
        avgs = conn.execute(
            "SELECT AVG(views_7d), AVG(retention_rate), AVG(ctr), AVG(rpm) FROM video_metrics WHERE views > 0"
        ).fetchone()
        conn.close()
        avg_views, avg_ret, avg_ctr, avg_rpm = avgs
        if not avg_views:
            return 0.0
        score = 0.0
        if avg_views > 0:
            score += min(40, (metrics.get("views_7d", 0) / avg_views) * 40)
        if avg_ret and avg_ret > 0:
            score += min(30, (metrics.get("retention_rate", 0) / avg_ret) * 30)
        if avg_ctr and avg_ctr > 0:
            score += min(20, (metrics.get("ctr", 0) / avg_ctr) * 20)
        if avg_rpm and avg_rpm > 0:
            score += min(10, (metrics.get("rpm", 0) / avg_rpm) * 10)
        return round(score, 2)
    except Exception:
        return 0.0


def collect_youtube(api_key: str, channel_ids: list) -> list:
    results = []
    base = "https://www.googleapis.com/youtube/v3"
    for channel_id in channel_ids:
        try:
            r = requests.get(
                f"{base}/search",
                params={
                    "key": api_key,
                    "channelId": channel_id,
                    "part": "id,snippet",
                    "type": "video",
                    "order": "date",
                    "maxResults": 50,
                },
                timeout=10,
            )
            if r.status_code != 200:
                print(f"[ANALYTICS] YouTube API error {r.status_code}")
                continue
            videos = r.json().get("items", [])
            video_ids = [v["id"]["videoId"] for v in videos]
            if not video_ids:
                continue
            stats_r = requests.get(
                f"{base}/videos",
                params={
                    "key": api_key,
                    "id": ",".join(video_ids),
                    "part": "statistics,contentDetails,snippet",
                },
                timeout=10,
            )
            for item in stats_r.json().get("items", []):
                stats = item.get("statistics", {})
                results.append(
                    {
                        "platform": "youtube",
                        "channel_id": channel_id,
                        "video_id": item["id"],
                        "video_title": item["snippet"]["title"],
                        "published_at": item["snippet"]["publishedAt"],
                        "views": int(stats.get("viewCount", 0)),
                        "likes": int(stats.get("likeCount", 0)),
                        "comments": int(stats.get("commentCount", 0)),
                    }
                )
        except Exception as e:
            print(f"[ANALYTICS] YouTube error {channel_id}: {e}")
    return results


def save_metrics(metrics_list: list) -> int:
    conn = sqlite3.connect(DB)
    saved = 0
    for m in metrics_list:
        m["performance_score"] = calculate_performance_score(m)
        m["collected_at"] = datetime.now().isoformat()
        existing = conn.execute(
            "SELECT id FROM video_metrics WHERE video_id=? AND platform=?",
            (m.get("video_id"), m.get("platform")),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE video_metrics SET views=?, likes=?, comments=?, performance_score=?, collected_at=? WHERE video_id=? AND platform=?",
                (
                    m.get("views", 0),
                    m.get("likes", 0),
                    m.get("comments", 0),
                    m.get("performance_score"),
                    m.get("collected_at"),
                    m.get("video_id"),
                    m.get("platform"),
                ),
            )
        else:
            conn.execute(
                "INSERT INTO video_metrics"
                " (platform, channel_id, video_id, video_title, published_at,"
                "  views, likes, comments, performance_score, collected_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    m.get("platform"),
                    m.get("channel_id"),
                    m.get("video_id"),
                    m.get("video_title"),
                    m.get("published_at"),
                    m.get("views", 0),
                    m.get("likes", 0),
                    m.get("comments", 0),
                    m.get("performance_score"),
                    m.get("collected_at"),
                ),
            )
        saved += 1
    conn.commit()
    conn.close()
    return saved


def main():
    load_env()
    print(f"[ANALYTICS] Iniciando — {datetime.now():%Y-%m-%d %H:%M}")
    total_saved = 0
    yt_key = os.environ.get("YOUTUBE_API_KEY", "")
    if yt_key:
        conn = sqlite3.connect(DB)
        channels = conn.execute(
            "SELECT channel_id FROM platform_config WHERE platform='youtube' AND enabled=1 AND channel_id IS NOT NULL"
        ).fetchall()
        conn.close()
        channel_ids = [c[0] for c in channels]
        if channel_ids:
            metrics = collect_youtube(yt_key, channel_ids)
            saved = save_metrics(metrics)
            total_saved += saved
            print(f"[ANALYTICS] YouTube: {saved} videos actualizados")
        else:
            print("[ANALYTICS] YouTube: sin channel_ids en BD")
    else:
        print("[ANALYTICS] YouTube: YOUTUBE_API_KEY no configurada — omitiendo")
    print(f"[ANALYTICS] Total: {total_saved} registros")


if __name__ == "__main__":
    main()
