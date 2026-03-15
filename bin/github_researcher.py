"""
github_researcher.py — Investiga GitHub sobre un tema.
Busca repositorios, evalúa aplicabilidad al stack JARVIS,
genera reporte y lo envía por Telegram.

Uso:
  python3 github_researcher.py "video generation python"
  python3 github_researcher.py "ffmpeg automation" --min-stars 100
  python3 github_researcher.py "tts elevenlabs" --max-repos 20
"""

import sys, os, json, sqlite3, time, re, argparse
from pathlib import Path
from datetime import datetime
import httpx

sys.path.insert(0, "/root/content-automation-faceless")

DB = "/root/jarvis/database/jarvis_metrics.db"
JARVIS = Path("/root/jarvis")
OUT_DIR = JARVIS / "tasks" / "github_reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Stack de JARVIS para evaluar compatibilidad
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
}


# ─── GitHub API client ────────────────────────────────────────────
class GitHubClient:
    BASE = "https://api.github.com"

    def __init__(self):
        from dotenv import load_dotenv

        load_dotenv("/root/content-automation-faceless/config/.env")
        load_dotenv("/root/jarvis/.env")
        self.token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or ""
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"
        else:
            print("⚠️  Sin GITHUB_TOKEN — rate limit: 60 req/h")

    def search_repos(
        self, query: str, min_stars: int = 50, max_repos: int = 30, language: str = None
    ) -> list:
        """Busca repositorios por query."""
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
                raise RuntimeError("GitHub rate limit alcanzado. " "Añadir GITHUB_TOKEN al .env")
            resp.raise_for_status()
            data = resp.json()

        repos = data.get("items", [])
        print(f"  Encontrados: {data.get('total_count',0)} | " f"Procesando: {len(repos)}")
        return repos

    def get_readme(self, full_name: str) -> str:
        """Obtiene el README de un repo."""
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(
                    f"{self.BASE}/repos/{full_name}/readme",
                    headers={**self.headers, "Accept": "application/vnd.github.raw"},
                )
                if resp.status_code == 200:
                    # Truncar README largo
                    text = resp.text[:3000]
                    # Limpiar markdown
                    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
                    text = re.sub(r"\[.*?\]\(.*?\)", "", text)
                    text = re.sub(r"#{1,6}\s", "", text)
                    return text.strip()[:1500]
        except Exception:
            pass
        return ""

    def get_topics(self, full_name: str) -> list:
        """Obtiene los topics de un repo."""
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


# ─── Evaluador de aplicabilidad ───────────────────────────────────
class ApplicabilityEvaluator:
    """
    Evalúa qué tan aplicable es un repo al stack JARVIS.
    Score 0-10 basado en múltiples factores.
    """

    def evaluate(self, repo: dict, readme: str, topics: list) -> dict:
        score = 0.0
        reasons = []
        stack_matches = []

        name = repo["full_name"].lower()
        desc = (repo.get("description") or "").lower()
        lang = (repo.get("language") or "").lower()
        readme_lower = readme.lower()
        all_text = f"{name} {desc} {readme_lower} {' '.join(topics)}"

        # ── Factor 1: Lenguaje compatible (0-3 pts) ──────────────
        if lang == "python":
            score += 3.0
            stack_matches.append("Python")
        elif lang in ["shell", "bash"]:
            score += 1.5
            stack_matches.append("Bash")
        elif lang in JARVIS_STACK["avoid"]:
            score -= 2.0
            reasons.append(f"Lenguaje no compatible: {lang}")

        # ── Factor 2: Match con focus del proyecto (0-3 pts) ─────
        focus_hits = 0
        for term in JARVIS_STACK["focus"]:
            if term in all_text:
                focus_hits += 1
                if term not in stack_matches:
                    stack_matches.append(term)
        focus_score = min(3.0, focus_hits * 0.5)
        score += focus_score
        if focus_hits > 0:
            reasons.append(f"Relevancia temática: {focus_hits} matches")

        # ── Factor 3: Match con frameworks del stack (0-2 pts) ───
        for fw in JARVIS_STACK["frameworks"]:
            if fw in all_text:
                score += 0.5
                stack_matches.append(fw)
                reasons.append(f"Usa {fw}")

        # ── Factor 4: Popularidad / calidad (0-1 pt) ─────────────
        stars = repo.get("stargazers_count", 0)
        if stars >= 1000:
            score += 1.0
            reasons.append(f"⭐ {stars} stars")
        elif stars >= 500:
            score += 0.7
        elif stars >= 100:
            score += 0.4

        # ── Factor 5: Actividad reciente (0-1 pt) ─────────────────
        updated = repo.get("updated_at", "")
        if updated:
            from datetime import datetime, timezone

            try:
                last = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                days_old = (now - last).days
                if days_old < 90:
                    score += 1.0
                    reasons.append(f"Actualizado hace {days_old}d")
                elif days_old < 365:
                    score += 0.5
                else:
                    reasons.append(f"Sin actualizar en {days_old}d")
            except Exception:
                pass

        # ── Factor 6: Licencia compatible ────────────────────────
        license_info = repo.get("license")
        if license_info:
            lic = license_info.get("spdx_id", "").upper()
            if lic in ["MIT", "APACHE-2.0", "BSD-2-CLAUSE", "BSD-3-CLAUSE", "ISC", "CC0-1.0"]:
                score += 0.5
                reasons.append(f"Licencia: {lic}")
            elif lic == "GPL-3.0":
                reasons.append("⚠️ GPL — revisar restricciones")

        # ── Clasificar esfuerzo de integración ───────────────────
        score = round(min(10.0, max(0.0, score)), 2)
        if score >= 8.0:
            effort = "LOW — Drop-in integration"
        elif score >= 6.0:
            effort = "MEDIUM — Adaptar a nuestro stack"
        elif score >= 4.0:
            effort = "HIGH — Extraer partes útiles"
        else:
            effort = "SKIP — No aplicable"

        return {
            "score": score,
            "reasons": reasons,
            "stack_matches": list(set(stack_matches)),
            "effort": effort,
        }


# ─── Reporter ────────────────────────────────────────────────────
def generate_report(topic: str, repos_data: list, session_id: int) -> str:
    """Genera reporte .md listo para Gemini o lectura directa."""

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    report_path = OUT_DIR / f'github_{topic[:30].replace(" ","_")}_{timestamp}.md'

    # Ordenar por score
    sorted_repos = sorted(repos_data, key=lambda x: x["eval"]["score"], reverse=True)

    lines = [
        f"# GitHub Research — {topic}",
        f"**Fecha:** {timestamp}",
        f"**Repos analizados:** {len(repos_data)}",
        f"**Stack JARVIS:** Python + FFmpeg + ElevenLabs + Fal.ai\n",
        "---\n",
        "## 🏆 TOP 5 — Más aplicables\n",
    ]

    # Top 5
    for i, r in enumerate(sorted_repos[:5], 1):
        repo = r["repo"]
        ev = r["eval"]
        lines += [
            f"### {i}. [{repo['full_name']}]({repo['html_url']})",
            f"**Score:** {ev['score']}/10 | " f"**Esfuerzo:** {ev['effort']}",
            f"**Stars:** ⭐{repo.get('stargazers_count',0):,} | "
            f"**Lang:** {repo.get('language','?')} | "
            f"**Updated:** {repo.get('updated_at','?')[:10]}",
            f"**Descripción:** {repo.get('description','N/A')}",
            f"**Stack match:** {', '.join(ev['stack_matches'])}",
            f"**Por qué:** {' | '.join(ev['reasons'][:3])}",
            "",
        ]
        if r.get("readme_preview"):
            lines += [
                f"**README preview:**",
                f"```",
                f"{r['readme_preview'][:300]}",
                f"```",
                "",
            ]

    # Tabla completa
    lines += [
        "---\n",
        "## 📊 Tabla completa\n",
        "| Repo | Score | Stars | Lang | Esfuerzo |",
        "|------|-------|-------|------|----------|",
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

    lines += [
        "\n---\n",
        "## 🔍 Pregunta para Gemini\n",
        f"Stack actual: Python + FFmpeg + ElevenLabs + Fal.ai + Telegram\n",
        f"Topic investigado: **{topic}**\n",
        "De los repositorios listados, ¿cuál tiene mayor potencial "
        "de integración directa? ¿Hay alguno que resuelva un problema "
        "que actualmente estemos parcheando con código propio?",
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
    Investiga GitHub sobre un tema y genera reporte.
    """
    print(f"\n{'='*55}")
    print(f"GITHUB RESEARCHER — {topic}")
    print(f"min_stars={min_stars} | max_repos={max_repos} | lang={language}")
    print("=" * 55)

    client = GitHubClient()
    evaluator = ApplicabilityEvaluator()
    conn = sqlite3.connect(DB)

    # Crear sesión
    cur = conn.execute(
        """
        INSERT INTO github_search_sessions (topic, query_used)
        VALUES (?,?)
    """,
        (topic, f"{topic} language:{language} stars:>{min_stars}"),
    )
    session_id = cur.lastrowid
    conn.commit()

    # Buscar repos
    print(f"\n[1/4] Buscando repos...")
    repos = client.search_repos(topic, min_stars=min_stars, max_repos=max_repos, language=language)

    # Analizar cada repo
    print(f"\n[2/4] Analizando {len(repos)} repos...")
    repos_data = []

    for i, repo in enumerate(repos, 1):
        name = repo["full_name"]
        print(f"  [{i:2}/{len(repos)}] {name}", end=" ", flush=True)

        # README (con pausa para no exceder rate limit)
        readme = client.get_readme(name)
        topics = client.get_topics(name)
        time.sleep(0.3)  # respetar rate limit

        # Evaluar
        ev = evaluator.evaluate(repo, readme, topics)
        print(f"→ {ev['score']}/10 {ev['effort'].split(' — ')[0]}")

        repos_data.append(
            {
                "repo": repo,
                "eval": ev,
                "readme_preview": readme[:400] if readme else "",
            }
        )

        # Guardar en BD
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
                    json.dumps(topics),
                    ev["score"],
                    " | ".join(ev["reasons"][:3]),
                    json.dumps(ev["stack_matches"]),
                    ev["effort"],
                ),
            )
            conn.commit()
        except Exception as e:
            print(f"    BD error: {e}")

    # Generar reporte
    print(f"\n[3/4] Generando reporte...")
    report_path = generate_report(topic, repos_data, session_id)
    print(f"  ✅ {report_path}")

    # Top repo
    sorted_data = sorted(repos_data, key=lambda x: x["eval"]["score"], reverse=True)
    top = sorted_data[0] if sorted_data else None

    # Actualizar sesión
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
    """Envía resumen por Telegram + reporte .md como documento."""
    try:
        import asyncio
        from dotenv import load_dotenv

        load_dotenv("/root/jarvis/.env")
        bot_token = os.getenv("JARVIS_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if not bot_token or not chat_id:
            print("  ⚠️  Telegram no configurado")
            return

        async def send():
            async with httpx.AsyncClient(timeout=30) as client:
                # Mensaje resumen
                lines = [
                    f"🔍 <b>GitHub Research</b>: {topic}",
                    f"📊 Analizados: {len(top_repos)} repos top\n",
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
                lines.append("\n📄 Reporte completo adjunto para Gemini.")

                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    data={"chat_id": chat_id, "text": "\n".join(lines), "parse_mode": "HTML"},
                )

                # Enviar .md como documento
                with open(report_path, "rb") as f:
                    await client.post(
                        f"https://api.telegram.org/bot{bot_token}/sendDocument",
                        data={
                            "chat_id": chat_id,
                            "caption": f"📊 GitHub Research: {topic}\nPega en Gemini para análisis.",
                        },
                        files={"document": f},
                    )

        asyncio.run(send())
        print("  ✅ Enviado a Telegram")

    except Exception as e:
        print(f"  Telegram error: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Investiga GitHub sobre un tema")
    parser.add_argument("topic", help='Tema a investigar (ej: "video generation python")')
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
