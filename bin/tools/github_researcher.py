"""
github_researcher.py — Researches GitHub on a topic.
Searches repositories, evaluates applicability to the DQIII8 stack,
generates a report and sends it via Telegram.

Usage:
  python3 github_researcher.py "video generation python"
  python3 github_researcher.py "ffmpeg automation" --min-stars 100
  python3 github_researcher.py "tts elevenlabs" --max-repos 20
"""

import sys, os, json, sqlite3, time, re, argparse
from pathlib import Path
from datetime import datetime
import httpx

CONTENT_ROOT = os.environ.get("CONTENT_PROJECT_ROOT", "")
if CONTENT_ROOT:
    sys.path.insert(0, CONTENT_ROOT)

JARVIS = Path(os.environ.get("DQIII8_ROOT", "/root/jarvis"))
DB = str(JARVIS / "database" / "dqiii8.db")
OUT_DIR = JARVIS / "tasks" / "github_reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# DQIII8 stack for compatibility evaluation
JARVIS_STACK = {
    "languages": ["python", "bash"],
    "frameworks": ["fastapi", "asyncio", "ffmpeg", "moviepy"],
    "services": ["elevenlabs", "groq", "fal", "telegram"],
    "focus": [
        "video",
        "tts",
        "content",
        "automation",
        "youtube",
        "shorts",
        "tiktok",
        "subtitles",
        "script",
        "llm",
        "ai",
        "generation",
    ],
    "avoid": ["javascript", "typescript", "react", "node", "java", "c++", "rust", "unity"],
    "hardware": {
        "available": ["cpu", "vps", "linux"],
        "unavailable": ["gpu", "cuda", "vram", "nvidia", "tensorflow-gpu", "torch+cuda"],
    },
    "python_min": "3.9",
    "python_max": "3.12",
}

# Keywords indicating GPU requirement — severe penalty on CPU-only VPS
GPU_KEYWORDS = [
    "cuda",
    "gpu",
    "vram",
    "nvidia",
    "torch.cuda",
    "stable diffusion",
    "diffusers",
    "pytorch gpu",
    "accelerate",
    "tensorflow-gpu",
    "rife",
    "ncnn",
    "requires gpu",
    "gpu required",
    "graphics card",
    "video card",
]

# Keywords indicating locked Python version
PYTHON_EXCLUSIVE = [
    "python 3.10 only",
    "python 3.10 required",
    "not supported on 3.11",
    "requires python 3.10",
    "3.10 only",
    "python 3.9 only",
    "requires python 3.9",
]

# Keywords confirming CPU compatibility — boost
CPU_PHRASES = [
    "cpu only",
    "no gpu required",
    "pure python",
    "without gpu",
    "cpu-based",
    "no cuda",
    "cpu inference",
    "runs on cpu",
]


# ─── GitHub API client ────────────────────────────────────────────
class GitHubClient:
    BASE = "https://api.github.com"

    def __init__(self):
        from dotenv import load_dotenv

        content_env = Path(os.environ.get("CONTENT_PROJECT_ROOT", "")) / "config" / ".env"
        if content_env.parent.parent.exists():
            load_dotenv(str(content_env))
        load_dotenv(str(JARVIS / ".env"))
        self.token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or ""
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"
        else:
            print("⚠️  No GITHUB_TOKEN — rate limit: 60 req/h")
        self.scraper_key = os.getenv("SCRAPERAPI_KEY", "")
        self.scraper_available = bool(self.scraper_key)
        if self.scraper_available:
            print("  ✅ ScraperAPI available — deep scraping mode")
        else:
            print("  ℹ️  No ScraperAPI — using GitHub API (sufficient)")

    def search_repos(
        self, query: str, min_stars: int = 50, max_repos: int = 30, language: str = None
    ) -> list:
        """Searches repositories by query."""
        q = f"{query} stars:>{min_stars}"
        if language:
            q += f" language:{language}"

        params = {
            "q": q,
            "sort": "stars",
            "order": "desc",
            "per_page": min(max_repos, 30),
        }

        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{self.BASE}/search/repositories", headers=self.headers, params=params
            )
            if resp.status_code == 403:
                raise RuntimeError("GitHub rate limit reached. " "Add GITHUB_TOKEN to .env")
            resp.raise_for_status()
            data = resp.json()

        repos = data.get("items", [])
        print(f"  Found: {data.get('total_count',0)} | " f"Processing: {len(repos)}")
        return repos

    def get_readme(self, full_name: str) -> str:
        """Gets the README of a repo."""
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(
                    f"{self.BASE}/repos/{full_name}/readme",
                    headers={**self.headers, "Accept": "application/vnd.github.raw"},
                )
                if resp.status_code == 200:
                    # Truncate long README
                    text = resp.text[:3000]
                    # Clean markdown
                    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
                    text = re.sub(r"\[.*?\]\(.*?\)", "", text)
                    text = re.sub(r"#{1,6}\s", "", text)
                    return text.strip()[:1500]
        except Exception:
            pass
        return ""

    def get_topics(self, full_name: str) -> list:
        """Gets the topics of a repo."""
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(
                    f"{self.BASE}/repos/{full_name}/topics",
                    headers={**self.headers, "Accept": "application/vnd.github.mercy-preview+json"},
                )
                if resp.status_code == 200:
                    return resp.json().get("names", [])
        except Exception:
            pass
        return []

    def scrape_page_markdown(self, url: str) -> str:
        """
        Gets any GitHub page in LLM-ready markdown format.
        Uses ScraperAPI if available, GitHub API as fallback.
        """
        if not self.scraper_available:
            repo_path = url.replace("https://github.com/", "")
            return self.get_readme(repo_path)
        try:
            payload = {
                "api_key": self.scraper_key,
                "url": url,
                "output_format": "markdown",
                "country": "us",
            }
            with httpx.Client(timeout=30) as client:
                resp = client.get("https://api.scraperapi.com/", params=payload)
                resp.raise_for_status()
                content = resp.text
                if "## " in content:
                    content = content[content.index("## ") :]
                return content[:4000]
        except Exception as e:
            print(f"    ScraperAPI error: {e} → fallback GitHub API")
            repo_path = url.replace("https://github.com/", "")
            return self.get_readme(repo_path)

    def get_repo_code_structure(self, full_name: str) -> dict:
        """Gets the file structure of the repo to evaluate integration."""
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(
                    f"{self.BASE}/repos/{full_name}/git/trees/HEAD",
                    headers=self.headers,
                    params={"recursive": "1"},
                )
                if resp.status_code == 200:
                    tree = resp.json().get("tree", [])
                    py_files = [
                        f["path"] for f in tree if f["path"].endswith(".py") and f["type"] == "blob"
                    ]
                    return {
                        "py_files_count": len(py_files),
                        "has_tests": any("test" in f.lower() for f in py_files),
                        "has_docker": any(
                            f["path"] in ["Dockerfile", "docker-compose.yml"] for f in tree
                        ),
                        "has_requirements": any(
                            f["path"] in ["requirements.txt", "pyproject.toml", "setup.py"]
                            for f in tree
                        ),
                        "py_files_sample": py_files[:10],
                    }
        except Exception:
            pass
        return {}

    def get_repo_issues_summary(self, full_name: str) -> dict:
        """Gets open issues to evaluate project maturity."""
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(
                    f"{self.BASE}/repos/{full_name}/issues",
                    headers=self.headers,
                    params={"state": "open", "per_page": 5},
                )
                if resp.status_code == 200:
                    issues = resp.json()
                    return {
                        "open_issues_sample": len(issues),
                        "latest_issue_title": (issues[0]["title"][:80] if issues else "none"),
                    }
        except Exception:
            pass
        return {}


# ─── Applicability evaluator ──────────────────────────────────────
class ApplicabilityEvaluator:
    """
    Evaluates how applicable a repo is to the DQIII8 stack.
    Score 0-10 based on multiple factors.
    """

    def evaluate(self, repo: dict, readme: str, topics: list, code_structure: dict = None) -> dict:
        score = 0.0
        reasons = []
        stack_matches = []

        name = repo["full_name"].lower()
        desc = (repo.get("description") or "").lower()
        lang = (repo.get("language") or "").lower()
        readme_lower = readme.lower()
        all_text = f"{name} {desc} {readme_lower} {' '.join(topics)}"

        # ── Factor 1: Compatible language (0-3 pts) ──────────────
        if lang == "python":
            score += 3.0
            stack_matches.append("Python")
        elif lang in ["shell", "bash"]:
            score += 1.5
            stack_matches.append("Bash")
        elif lang in JARVIS_STACK["avoid"]:
            score -= 2.0
            reasons.append(f"Incompatible language: {lang}")

        # ── Factor 2: Match with project focus (0-3 pts) ─────────
        focus_hits = 0
        for term in JARVIS_STACK["focus"]:
            if term in all_text:
                focus_hits += 1
                if term not in stack_matches:
                    stack_matches.append(term)
        focus_score = min(3.0, focus_hits * 0.5)
        score += focus_score
        if focus_hits > 0:
            reasons.append(f"Topic relevance: {focus_hits} matches")

        # ── Factor 3: Match with stack frameworks (0-2 pts) ──────
        for fw in JARVIS_STACK["frameworks"]:
            if fw in all_text:
                score += 0.5
                stack_matches.append(fw)
                reasons.append(f"Uses {fw}")

        # ── Factor 4: Popularity / quality (0-1 pt) ──────────────
        stars = repo.get("stargazers_count", 0)
        if stars >= 1000:
            score += 1.0
            reasons.append(f"⭐ {stars} stars")
        elif stars >= 500:
            score += 0.7
        elif stars >= 100:
            score += 0.4

        # ── Factor 5: Recent activity (0-1 pt) ────────────────────
        updated = repo.get("updated_at", "")
        if updated:
            from datetime import datetime, timezone

            try:
                last = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                days_old = (now - last).days
                if days_old < 90:
                    score += 1.0
                    reasons.append(f"Updated {days_old}d ago")
                elif days_old < 365:
                    score += 0.5
                else:
                    reasons.append(f"Not updated in {days_old}d")
            except Exception:
                pass

        # ── Factor 6: Compatible license ─────────────────────────
        license_info = repo.get("license")
        if license_info:
            lic = license_info.get("spdx_id", "").upper()
            if lic in ["MIT", "APACHE-2.0", "BSD-2-CLAUSE", "BSD-3-CLAUSE", "ISC", "CC0-1.0"]:
                score += 0.5
                reasons.append(f"License: {lic}")
            elif lic == "GPL-3.0":
                reasons.append("⚠️ GPL — review restrictions")

        # ── Factor 7: code structure (0-1.5 pts) ─────────────────
        if code_structure:
            if code_structure.get("has_requirements"):
                score += 0.5
                reasons.append("✅ requirements.txt — direct pip install")
            if code_structure.get("has_tests"):
                score += 0.5
                reasons.append("✅ Tests included — more reliable code")
            if code_structure.get("has_docker"):
                score += 0.3
                reasons.append("✅ Dockerized — easy to isolate")
            py_count = code_structure.get("py_files_count", 0)
            if 5 <= py_count <= 30:
                score += 0.2
                reasons.append(f"📁 {py_count} .py files (ideal size)")
            elif py_count > 100:
                reasons.append(f"⚠️ {py_count} .py files (large project)")

        # ── Factor 8: repo size (0-0.3 pts) ──────────────────────
        if repo.get("size", 0) < 1000:
            score += 0.3
            reasons.append("🔧 Lightweight repo — easy to copy parts")

        # ── Factor 9: CPU-only confirmation (evaluate first) ─────
        cpu_confirmed = any(p in all_text for p in CPU_PHRASES)
        if cpu_confirmed:
            score += 1.5
            reasons.append("✅ CPU-only confirmed — compatible with VPS")

        # ── Factor 10: GPU requirement — severe penalty ───────────
        # cpu_confirmed short-circuits: "no gpu required" does not trigger GPU penalty
        gpu_blocked = (not cpu_confirmed) and any(kw in all_text for kw in GPU_KEYWORDS)
        if gpu_blocked:
            score -= 4.0
            reasons.append("🚫 Requires GPU/CUDA — incompatible with CPU-only VPS")

        # ── Factor 11: exclusive Python version ───────────────────
        python_locked = any(kw in all_text for kw in PYTHON_EXCLUSIVE)
        if python_locked:
            score -= 2.0
            reasons.append("⚠️ Exclusive Python version — incompatibility risk")

        # ── Classify integration effort ───────────────────────────
        score = round(min(10.0, max(0.0, score)), 2)
        if score >= 8.0:
            effort = "LOW — Drop-in integration"
        elif score >= 6.0:
            effort = "MEDIUM — Adapt to our stack"
        elif score >= 4.0:
            effort = "HIGH — Extract useful parts"
        else:
            effort = "SKIP — Not applicable"

        return {
            "score": score,
            "reasons": reasons,
            "stack_matches": list(set(stack_matches)),
            "effort": effort,
            "gpu_blocked": gpu_blocked,
            "python_locked": python_locked,
            "integration_type": _classify_integration(score, code_structure, gpu_blocked),
            "code_structure": code_structure or {},
        }


def _classify_integration(
    score: float, code_structure: dict = None, gpu_blocked: bool = False
) -> str:
    """Classifies how to integrate the repo into DQIII8."""
    if gpu_blocked:
        return "REFERENCE — GPU required, not viable on current VPS"
    if score >= 8.0:
        return "COPY — Direct integration possible"
    elif score >= 6.5:
        return "ADAPT — Adapt 1-2 key functions"
    elif score >= 5.0:
        return "EXTRACT — Extract only core logic"
    elif score >= 3.5:
        return "REFERENCE — Use as reference/inspiration"
    else:
        return "SKIP"


# ─── Multi-query search ───────────────────────────────────────────

QUERY_EXPANSIONS = {
    "video generation": [
        "video generation python",
        "ai video creator python",
        "automated video python ffmpeg",
        "video synthesis python",
    ],
    "subtitle": [
        "subtitle generator python whisper",
        "auto subtitles python",
        "caption generator python tts",
        "ass subtitle python",
    ],
    "tts": [
        "text to speech python",
        "tts automation python",
        "elevenlabs python wrapper",
        "voice synthesis python",
    ],
    "content automation": [
        "youtube automation python",
        "social media automation python",
        "shorts generator python",
        "tiktok bot python",
    ],
}


def multi_search(topic: str, min_stars: int = 50, max_repos: int = 40) -> list:
    """
    Searches with multiple related queries and deduplicates.
    Finds repos that a single query would miss.
    """
    client = GitHubClient()

    # Expand queries if topic matches any key
    queries = [topic]
    for key, expansions in QUERY_EXPANSIONS.items():
        if key in topic.lower():
            queries = expansions
            break

    per_query = max(5, max_repos // len(queries))
    all_repos: dict = {}

    for q in queries:
        print(f"  Query: '{q}'")
        try:
            repos = client.search_repos(q, min_stars=min_stars, max_repos=per_query)
            for r in repos:
                name = r["full_name"]
                if name not in all_repos:
                    all_repos[name] = r
            time.sleep(1)  # respect rate limit between queries
        except Exception as e:
            print(f"    Error in query '{q}': {e}")

    print(f"  Total unique after deduplication: {len(all_repos)}")
    return list(all_repos.values())


# ─── Reporter ────────────────────────────────────────────────────
def generate_report(topic: str, repos_data: list, session_id: int) -> str:
    """Generates .md report ready for Gemini or direct reading."""

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    report_path = OUT_DIR / f'github_{topic[:30].replace(" ","_")}_{timestamp}.md'

    # Sort by score
    sorted_repos = sorted(repos_data, key=lambda x: x["eval"]["score"], reverse=True)

    lines = [
        f"# GitHub Research — {topic}",
        f"**Date:** {timestamp}",
        f"**Repos analyzed:** {len(repos_data)}",
        f"**Stack DQIII8:** Python + FFmpeg + ElevenLabs + Fal.ai\n",
        "---\n",
        "## 🏆 TOP 5 — Most applicable\n",
    ]

    # Top 5
    for i, r in enumerate(sorted_repos[:5], 1):
        repo = r["repo"]
        ev = r["eval"]
        cs = ev.get("code_structure", {})
        lines += [
            f"### {i}. [{repo['full_name']}]({repo['html_url']})",
            f"**Score:** {ev['score']}/10 | **Effort:** {ev['effort']}",
            f"**Integration:** {ev.get('integration_type', '?')}",
            f"**Stars:** ⭐{repo.get('stargazers_count',0):,} | "
            f"**Lang:** {repo.get('language','?')} | "
            f"**Updated:** {repo.get('updated_at','?')[:10]}",
            f"**Description:** {repo.get('description','N/A')}",
            f"**Stack match:** {', '.join(ev['stack_matches'])}",
            f"**Why:** {' | '.join(ev['reasons'][:4])}",
        ]
        if cs:
            struct_parts = []
            if cs.get("has_requirements"):
                struct_parts.append("requirements.txt ✅")
            if cs.get("has_tests"):
                struct_parts.append("tests ✅")
            if cs.get("has_docker"):
                struct_parts.append("Docker ✅")
            py_n = cs.get("py_files_count", 0)
            if py_n:
                struct_parts.append(f"{py_n} .py files")
            if struct_parts:
                lines.append(f"**Structure:** {' | '.join(struct_parts)}")
        lines.append("")
        if r.get("readme_preview"):
            lines += [
                "**README preview:**",
                "```",
                f"{r['readme_preview'][:300]}",
                "```",
                "",
            ]

    # Full table
    lines += [
        "---\n",
        "## 📊 Full table\n",
        "| Repo | Score | Stars | Lang | Effort |",
        "|------|-------|-------|------|--------|",
    ]
    for r in sorted_repos:
        repo = r["repo"]
        ev = r["eval"]
        lines.append(
            f"| [{repo['name']}]({repo['html_url']}) | "
            f"{ev['score']} | "
            f"{repo.get('stargazers_count',0):,} | "
            f"{repo.get('language','?')} | "
            f"{ev['effort'].split(' — ')[0]} |"
        )

    # GPU-blocked section
    gpu_blocked_repos = [r for r in sorted_repos if r["eval"].get("gpu_blocked")]
    if gpu_blocked_repos:
        lines += ["\n---\n", "## ⛔ Blocked by hardware (GPU/CUDA required)\n"]
        lines.append("*Save for when the VPS has a GPU:*\n")
        lines += [
            "| Repo | Score adj. | Stars | Why blocked |",
            "|------|-----------|-------|-------------|",
        ]
        for r in gpu_blocked_repos:
            repo = r["repo"]
            ev = r["eval"]
            gpu_reason = next(
                (reason for reason in ev["reasons"] if "GPU" in reason or "CUDA" in reason),
                "GPU required",
            )
            lines.append(
                f"| [{repo['name']}]({repo['html_url']}) | "
                f"{ev['score']} | "
                f"⭐{repo.get('stargazers_count',0):,} | "
                f"{gpu_reason} |"
            )
        lines.append("")

    # Quick Wins section (exclude gpu-blocked repos)
    quick_wins = [
        r
        for r in sorted_repos
        if r["eval"]["score"] >= 7.0
        and not r["eval"].get("gpu_blocked")
        and r["eval"].get("integration_type", "").startswith(("COPY", "ADAPT"))
    ]
    if quick_wins:
        lines += ["\n---\n", "## ⚡ Quick Wins — Integrable this week\n"]
        for r in quick_wins[:3]:
            repo = r["repo"]
            ev = r["eval"]
            # Infer what DQIII8 problem this solves
            matches = ev.get("stack_matches", [])
            jarvis_gap = (
                "functionality related to " + ", ".join(matches[:3]) if matches else "pipeline"
            )
            lines += [
                f"### {repo['name']} ({ev['score']}/10)",
                f"**DQIII8 problem it solves:** {jarvis_gap}",
                f"**Integration type:** {ev.get('integration_type','?')}",
                f"**Install:** `pip install` from {repo['html_url']}",
                f"**Estimated time:** {'1-2h' if ev['score'] >= 8.0 else '2-4h'}",
                "",
            ]

    lines += [
        "\n---\n",
        "## 🔍 Question for Gemini\n",
        f"Current stack: Python + FFmpeg + ElevenLabs + Fal.ai + Telegram\n",
        f"Researched topic: **{topic}**\n",
        "Among the listed repositories, which one has the greatest potential "
        "for direct integration? Is there one that solves a problem "
        "we are currently patching with custom code?",
    ]

    report = "\n".join(lines)
    report_path.write_text(report, encoding="utf-8")
    return str(report_path)


# ─── Main ─────────────────────────────────────────────────────────
def research(
    topic: str,
    min_stars: int = 50,
    max_repos: int = 25,
    language: str = "python",
    send_telegram: bool = True,
) -> str:
    """
    Researches GitHub on a topic and generates a report.
    """
    print(f"\n{'='*55}")
    print(f"GITHUB RESEARCHER — {topic}")
    print(f"min_stars={min_stars} | max_repos={max_repos} | lang={language}")
    print("=" * 55)

    client = GitHubClient()
    evaluator = ApplicabilityEvaluator()
    conn = sqlite3.connect(DB)

    # Create session
    cur = conn.execute(
        """
        INSERT INTO github_search_sessions (topic, query_used)
        VALUES (?,?)
    """,
        (topic, f"{topic} language:{language} stars:>{min_stars}"),
    )
    session_id = cur.lastrowid
    conn.commit()

    # Search repos (multi-query if topic matches expansions)
    print(f"\n[1/4] Searching repos...")
    repos = multi_search(topic, min_stars=min_stars, max_repos=max_repos)
    # If multi_search doesn't expand (topic without match), filter by language if specified
    if language and language != "python":
        repos = [r for r in repos if (r.get("language") or "").lower() == language]

    # Analyze each repo
    print(f"\n[2/4] Analyzing {len(repos)} repos...")
    repos_data = []

    for i, repo in enumerate(repos, 1):
        name = repo["full_name"]
        print(f"  [{i:2}/{len(repos)}] {name}", end="", flush=True)

        # README + topics + code structure (with pause to not exceed rate limit)
        readme = client.get_readme(name)
        topics_list = client.get_topics(name)
        code_structure = client.get_repo_code_structure(name)
        time.sleep(0.4)  # respect rate limit

        # Evaluate
        ev = evaluator.evaluate(repo, readme, topics_list, code_structure=code_structure)
        print(f"→ {ev['score']}/10 {ev['effort'].split(' — ')[0]}")

        repos_data.append(
            {
                "repo": repo,
                "eval": ev,
                "readme_preview": readme[:400] if readme else "",
            }
        )

        # Save to DB
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO github_research
                (search_topic, repo_full_name, repo_url, description,
                 stars, forks, last_updated, language, license,
                 readme_summary, topics_tags,
                 applicability_score, applicability_reason,
                 stack_match, integration_effort, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending')
            """,
                (
                    topic,
                    name,
                    repo.get("html_url", ""),
                    (repo.get("description") or "")[:300],
                    repo.get("stargazers_count", 0),
                    repo.get("forks_count", 0),
                    repo.get("updated_at", "")[:10],
                    repo.get("language", ""),
                    (repo.get("license") or {}).get("spdx_id", ""),
                    readme[:500] if readme else "",
                    json.dumps(topics_list),
                    ev["score"],
                    " | ".join(ev["reasons"][:3]),
                    json.dumps(ev["stack_matches"]),
                    ev["effort"],
                ),
            )
            conn.commit()
        except Exception as e:
            print(f"    DB error: {e}")

    # Generate report
    print(f"\n[3/4] Generating report...")
    report_path = generate_report(topic, repos_data, session_id)
    print(f"  ✅ {report_path}")

    # Top repo
    sorted_data = sorted(repos_data, key=lambda x: x["eval"]["score"], reverse=True)
    top = sorted_data[0] if sorted_data else None

    # Update session
    conn.execute(
        """
        UPDATE github_search_sessions
        SET repos_found=?, repos_scored=?, top_repo=?,
            top_score=?, report_path=?
        WHERE id=?
    """,
        (
            len(repos),
            len(repos_data),
            top["repo"]["full_name"] if top else "",
            top["eval"]["score"] if top else 0,
            report_path,
            session_id,
        ),
    )
    conn.commit()
    conn.close()

    # Enviar a Telegram
    if send_telegram:
        print(f"\n[4/4] Enviando a Telegram...")
        _send_telegram_report(topic, sorted_data[:5], report_path)

    print(f"\n✅ Research completado")
    print(f"   Top repo: {top['repo']['full_name'] if top else 'N/A'}")
    print(f"   Score: {top['eval']['score'] if top else 0}/10")
    print(f"   Reporte: {report_path}")
    return report_path


def _send_telegram_report(topic, top_repos, report_path):
    """Sends summary via Telegram + .md report as a document."""
    try:
        import asyncio
        from dotenv import load_dotenv

        load_dotenv(str(JARVIS / ".env"))
        bot_token = os.getenv("DQIII8_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("JARVIS_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if not bot_token or not chat_id:
            print("  ⚠️  Telegram not configured")
            return

        async def send():
            async with httpx.AsyncClient(timeout=30) as client:
                # Summary message
                lines = [
                    f"🔍 <b>GitHub Research</b>: {topic}",
                    f"📊 Analyzed: {len(top_repos)} top repos\n",
                ]
                for i, r in enumerate(top_repos[:3], 1):
                    repo = r["repo"]
                    ev = r["eval"]
                    lines.append(
                        f"{i}. <b>{repo['name']}</b> "
                        f"({ev['score']}/10)\n"
                        f"   ⭐{repo.get('stargazers_count',0):,} | "
                        f"{ev['effort'].split(' — ')[0]}\n"
                        f"   {repo.get('description','')[:80]}"
                    )
                lines.append("\n📄 Full report attached for Gemini.")

                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    data={"chat_id": chat_id, "text": "\n".join(lines), "parse_mode": "HTML"},
                )

                # Send .md as document
                with open(report_path, "rb") as f:
                    await client.post(
                        f"https://api.telegram.org/bot{bot_token}/sendDocument",
                        data={
                            "chat_id": chat_id,
                            "caption": f"📊 GitHub Research: {topic}\nPaste into Gemini for analysis.",
                        },
                        files={"document": f},
                    )

        asyncio.run(send())
        print("  ✅ Sent to Telegram")

    except Exception as e:
        print(f"  Telegram error: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Research GitHub on a topic")
    parser.add_argument("topic", help='Topic to research (e.g. "video generation python")')
    parser.add_argument("--min-stars", type=int, default=50)
    parser.add_argument("--max-repos", type=int, default=25)
    parser.add_argument("--language", default="python")
    parser.add_argument("--no-telegram", action="store_true")
    args = parser.parse_args()

    research(
        topic=args.topic,
        min_stars=args.min_stars,
        max_repos=args.max_repos,
        language=args.language,
        send_telegram=not args.no_telegram,
    )
