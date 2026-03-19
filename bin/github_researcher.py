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

CONTENT_ROOT = os.environ.get("CONTENT_PROJECT_ROOT", "")
if CONTENT_ROOT:
    sys.path.insert(0, CONTENT_ROOT)

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB = str(JARVIS / "database" / "jarvis_metrics.db")
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
    "hardware": {
        "available": ["cpu", "vps", "linux"],
        "unavailable": ["gpu", "cuda", "vram", "nvidia", "tensorflow-gpu", "torch+cuda"],
    },
    "python_min": "3.9",
    "python_max": "3.12",
}

# Keywords que indican requisito de GPU — penalización severa en VPS CPU-only
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

# Keywords que indican versión de Python bloqueada
PYTHON_EXCLUSIVE = [
    "python 3.10 only",
    "python 3.10 required",
    "not supported on 3.11",
    "requires python 3.10",
    "3.10 only",
    "python 3.9 only",
    "requires python 3.9",
]

# Keywords que confirman compatibilidad CPU — boost
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
            print("⚠️  Sin GITHUB_TOKEN — rate limit: 60 req/h")
        self.scraper_key = os.getenv("SCRAPERAPI_KEY", "")
        self.scraper_available = bool(self.scraper_key)
        if self.scraper_available:
            print("  ✅ ScraperAPI disponible — modo deep scraping")
        else:
            print("  ℹ️  Sin ScraperAPI — usando GitHub API (suficiente)")

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

    def scrape_page_markdown(self, url: str) -> str:
        """
        Obtiene cualquier página de GitHub en formato markdown LLM-ready.
        Usa ScraperAPI si está disponible, GitHub API como fallback.
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
        """Obtiene estructura de archivos del repo para evaluar integración."""
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
        """Obtiene issues abiertos para evaluar madurez del proyecto."""
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


# ─── Evaluador de aplicabilidad ───────────────────────────────────
class ApplicabilityEvaluator:
    """
    Evalúa qué tan aplicable es un repo al stack JARVIS.
    Score 0-10 basado en múltiples factores.
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

        # ── Factor 7: estructura del código (0-1.5 pts) ──────────
        if code_structure:
            if code_structure.get("has_requirements"):
                score += 0.5
                reasons.append("✅ requirements.txt — pip install directo")
            if code_structure.get("has_tests"):
                score += 0.5
                reasons.append("✅ Tests incluidos — código más fiable")
            if code_structure.get("has_docker"):
                score += 0.3
                reasons.append("✅ Dockerized — fácil de aislar")
            py_count = code_structure.get("py_files_count", 0)
            if 5 <= py_count <= 30:
                score += 0.2
                reasons.append(f"📁 {py_count} archivos .py (tamaño ideal)")
            elif py_count > 100:
                reasons.append(f"⚠️ {py_count} archivos .py (proyecto grande)")

        # ── Factor 8: tamaño del repo (0-0.3 pts) ────────────────
        if repo.get("size", 0) < 1000:
            score += 0.3
            reasons.append("🔧 Repo ligero — fácil de copiar partes")

        # ── Factor 9: confirmación CPU-only (evaluar primero) ────
        cpu_confirmed = any(p in all_text for p in CPU_PHRASES)
        if cpu_confirmed:
            score += 1.5
            reasons.append("✅ CPU-only confirmado — compatible con VPS")

        # ── Factor 10: requisito GPU — penalización severa ────────
        # cpu_confirmed short-circuits: "no gpu required" no activa GPU penalty
        gpu_blocked = (not cpu_confirmed) and any(kw in all_text for kw in GPU_KEYWORDS)
        if gpu_blocked:
            score -= 4.0
            reasons.append("🚫 Requiere GPU/CUDA — incompatible con VPS CPU-only")

        # ── Factor 11: versión Python exclusiva ───────────────────
        python_locked = any(kw in all_text for kw in PYTHON_EXCLUSIVE)
        if python_locked:
            score -= 2.0
            reasons.append("⚠️ Python version exclusiva — riesgo de incompatibilidad")

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
            "gpu_blocked": gpu_blocked,
            "python_locked": python_locked,
            "integration_type": _classify_integration(score, code_structure, gpu_blocked),
            "code_structure": code_structure or {},
        }


def _classify_integration(
    score: float, code_structure: dict = None, gpu_blocked: bool = False
) -> str:
    """Clasifica cómo integrar el repo en JARVIS."""
    if gpu_blocked:
        return "REFERENCE — GPU requerida, no viable en VPS actual"
    if score >= 8.0:
        return "COPY — Integración directa posible"
    elif score >= 6.5:
        return "ADAPT — Adaptar 1-2 funciones clave"
    elif score >= 5.0:
        return "EXTRACT — Extraer solo la lógica core"
    elif score >= 3.5:
        return "REFERENCE — Usar como referencia/inspiración"
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
    Busca con múltiples queries relacionadas y deduplica.
    Encuentra repos que una sola query perdería.
    """
    client = GitHubClient()

    # Expandir queries si el topic coincide con alguna clave
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
            time.sleep(1)  # respetar rate limit entre queries
        except Exception as e:
            print(f"    Error en query '{q}': {e}")

    print(f"  Total únicos tras deduplicar: {len(all_repos)}")
    return list(all_repos.values())


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
        cs = ev.get("code_structure", {})
        lines += [
            f"### {i}. [{repo['full_name']}]({repo['html_url']})",
            f"**Score:** {ev['score']}/10 | **Esfuerzo:** {ev['effort']}",
            f"**Integración:** {ev.get('integration_type', '?')}",
            f"**Stars:** ⭐{repo.get('stargazers_count',0):,} | "
            f"**Lang:** {repo.get('language','?')} | "
            f"**Updated:** {repo.get('updated_at','?')[:10]}",
            f"**Descripción:** {repo.get('description','N/A')}",
            f"**Stack match:** {', '.join(ev['stack_matches'])}",
            f"**Por qué:** {' | '.join(ev['reasons'][:4])}",
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
                lines.append(f"**Estructura:** {' | '.join(struct_parts)}")
        lines.append("")
        if r.get("readme_preview"):
            lines += [
                "**README preview:**",
                "```",
                f"{r['readme_preview'][:300]}",
                "```",
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

    # GPU-blocked section
    gpu_blocked_repos = [r for r in sorted_repos if r["eval"].get("gpu_blocked")]
    if gpu_blocked_repos:
        lines += ["\n---\n", "## ⛔ Bloqueados por hardware (GPU/CUDA requerido)\n"]
        lines.append("*Guardar para cuando el VPS tenga GPU:*\n")
        lines += [
            "| Repo | Score adj. | Stars | Por qué bloqueado |",
            "|------|-----------|-------|-------------------|",
        ]
        for r in gpu_blocked_repos:
            repo = r["repo"]
            ev = r["eval"]
            gpu_reason = next(
                (reason for reason in ev["reasons"] if "GPU" in reason or "CUDA" in reason),
                "GPU requerida",
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
        lines += ["\n---\n", "## ⚡ Quick Wins — Integrables esta semana\n"]
        for r in quick_wins[:3]:
            repo = r["repo"]
            ev = r["eval"]
            # Inferir qué problema JARVIS resuelve
            matches = ev.get("stack_matches", [])
            jarvis_gap = (
                "funcionalidad relacionada con " + ", ".join(matches[:3]) if matches else "pipeline"
            )
            lines += [
                f"### {repo['name']} ({ev['score']}/10)",
                f"**Problema JARVIS que resuelve:** {jarvis_gap}",
                f"**Tipo integración:** {ev.get('integration_type','?')}",
                f"**Install:** `pip install` desde {repo['html_url']}",
                f"**Tiempo estimado:** {'1-2h' if ev['score'] >= 8.0 else '2-4h'}",
                "",
            ]

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

    # Buscar repos (multi-query si el topic coincide con expansiones)
    print(f"\n[1/4] Buscando repos...")
    repos = multi_search(topic, min_stars=min_stars, max_repos=max_repos)
    # Si multi_search no expande (topic sin match), filtra por language si se especificó
    if language and language != "python":
        repos = [r for r in repos if (r.get("language") or "").lower() == language]

    # Analizar cada repo
    print(f"\n[2/4] Analizando {len(repos)} repos...")
    repos_data = []

    for i, repo in enumerate(repos, 1):
        name = repo["full_name"]
        print(f"  [{i:2}/{len(repos)}] {name}", end="", flush=True)

        # README + topics + code structure (con pausa para no exceder rate limit)
        readme = client.get_readme(name)
        topics_list = client.get_topics(name)
        code_structure = client.get_repo_code_structure(name)
        time.sleep(0.4)  # respetar rate limit

        # Evaluar
        ev = evaluator.evaluate(repo, readme, topics_list, code_structure=code_structure)
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
                    json.dumps(topics_list),
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

        load_dotenv(str(JARVIS / ".env"))
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
