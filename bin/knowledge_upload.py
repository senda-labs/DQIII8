"""
Knowledge Upload v1
===================
Accepts PDF / MD / TXT / DOCX / ZIP files, auto-detects domain,
copies content to the correct agent knowledge directory, and re-indexes.

Usage:
    python3 bin/knowledge_upload.py path/to/file.pdf
    python3 bin/knowledge_upload.py path/to/file.md --agent finance-analyst
    python3 bin/knowledge_upload.py docs.zip --domain finance

    j --upload path/to/file.pdf
"""

from __future__ import annotations

import os
import shutil
import sys
import zipfile
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
sys.path.insert(0, str(JARVIS / "bin"))

from domain_classifier import classify_domain
from jal_common import load_env

SUPPORTED_EXTENSIONS = {".pdf", ".md", ".txt", ".docx", ".zip"}

# Maps domain name → agent that uses it
DOMAIN_AGENT_MAP: dict[str, str] = {
    "finance":          "finance-analyst",
    "economics":        "finance-analyst",
    "business":         "finance-analyst",
    "trading":          "finance-analyst",
    "technology":       "python-specialist",
    "computer_science": "python-specialist",
    "mathematics":      "python-specialist",
    "applied_sciences": "content-automator",
    "arts":             "creative-writer",
    "social_sciences":  "data-analyst",
}


def _extract_text_from_pdf(path: Path) -> str:
    """Extracts plain text from a PDF using pdfplumber if available."""
    try:
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
        return "\n\n".join(pages)
    except ImportError:
        return f"[PDF: {path.name} — install pdfplumber for text extraction]"
    except Exception as exc:
        return f"[PDF read error: {exc}]"


def _extract_text_from_docx(path: Path) -> str:
    """Extracts plain text from a DOCX file using python-docx if available."""
    try:
        import docx
        doc = docx.Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except ImportError:
        return f"[DOCX: {path.name} — install python-docx for text extraction]"
    except Exception as exc:
        return f"[DOCX read error: {exc}]"


def _get_text_for_classification(src: Path) -> str:
    """Returns enough text from the file for domain classification."""
    ext = src.suffix.lower()
    try:
        if ext in (".md", ".txt"):
            return src.read_text(encoding="utf-8", errors="replace")[:4000]
        if ext == ".pdf":
            return _extract_text_from_pdf(src)[:4000]
        if ext == ".docx":
            return _extract_text_from_docx(src)[:4000]
    except Exception:
        pass
    return src.stem.replace("_", " ").replace("-", " ")


def _detect_agent(src: Path, override_domain: str = "", override_agent: str = "") -> tuple[str, str, float]:
    """
    Returns (agent_name, domain, confidence).
    Uses override_agent > override_domain > auto-classification.
    """
    if override_agent:
        return override_agent, override_domain or "unknown", 1.0

    if override_domain:
        agent = DOMAIN_AGENT_MAP.get(override_domain, "python-specialist")
        return agent, override_domain, 1.0

    text = _get_text_for_classification(src)
    domain, confidence, method = classify_domain(text)
    agent = DOMAIN_AGENT_MAP.get(domain, "python-specialist")
    return agent, domain, confidence


def _copy_to_knowledge(src: Path, agent: str, subdir: str = "user_uploads") -> Path:
    """
    Copies file to .claude/agents/{agent}/knowledge/{subdir}/.
    Creates the directory if it doesn't exist.
    Returns the destination path.
    """
    dest_dir = JARVIS / ".claude" / "agents" / agent / "knowledge" / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copy2(str(src), str(dest))
    return dest


def _convert_to_md(src: Path, dest_dir: Path) -> Path:
    """
    Converts PDF/DOCX to a Markdown text file so the indexer can process it.
    Returns the path to the resulting .md file.
    """
    ext = src.suffix.lower()
    md_name = src.stem + ".md"
    md_path = dest_dir / md_name

    if ext == ".md" or ext == ".txt":
        shutil.copy2(str(src), str(md_path))
        return md_path

    if ext == ".pdf":
        text = _extract_text_from_pdf(src)
    elif ext == ".docx":
        text = _extract_text_from_docx(src)
    else:
        text = f"[Unsupported format: {ext}]"

    md_path.write_text(f"# {src.stem}\n\n{text}", encoding="utf-8")
    return md_path


def _reindex(agent: str) -> bool:
    """Runs knowledge_indexer.py for the given agent. Returns True on success."""
    import subprocess
    result = subprocess.run(
        [sys.executable, str(JARVIS / "bin" / "knowledge_indexer.py"), "--agent", agent],
        cwd=str(JARVIS),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[upload] Indexer error:\n{result.stderr[:500]}", file=sys.stderr)
        return False
    return True


def upload(
    file_path: str | Path,
    override_agent: str = "",
    override_domain: str = "",
    reindex: bool = True,
    verbose: bool = True,
) -> dict:
    """
    Main upload function.

    Args:
        file_path:       Path to file to upload
        override_agent:  Force a specific agent (skips auto-detection)
        override_domain: Force a specific domain (skips embedding classification)
        reindex:         Run knowledge_indexer after upload
        verbose:         Print progress

    Returns:
        {
          'success': bool,
          'agent': str,
          'domain': str,
          'confidence': float,
          'dest': str,
          'indexed': bool,
          'files_processed': int,
        }
    """
    src = Path(file_path).expanduser().resolve()

    if not src.exists():
        print(f"[upload] File not found: {src}", file=sys.stderr)
        return {"success": False, "agent": "", "domain": "", "confidence": 0.0,
                "dest": "", "indexed": False, "files_processed": 0}

    if src.suffix.lower() not in SUPPORTED_EXTENSIONS:
        print(f"[upload] Unsupported extension: {src.suffix} (supported: {SUPPORTED_EXTENSIONS})", file=sys.stderr)
        return {"success": False, "agent": "", "domain": "", "confidence": 0.0,
                "dest": str(src), "indexed": False, "files_processed": 0}

    # Handle ZIP: extract and upload each file individually
    if src.suffix.lower() == ".zip":
        return _upload_zip(src, override_agent, override_domain, reindex, verbose)

    agent, domain, confidence = _detect_agent(src, override_domain, override_agent)

    if verbose:
        print(f"[upload] {src.name} → agent={agent} domain={domain} conf={confidence:.2f}")

    # Copy original
    dest = _copy_to_knowledge(src, agent)

    # Convert to MD if needed (so indexer can process PDF/DOCX)
    if src.suffix.lower() in (".pdf", ".docx"):
        _convert_to_md(src, dest.parent)

    indexed = False
    if reindex:
        if verbose:
            print(f"[upload] Indexing {agent}...")
        indexed = _reindex(agent)
        if verbose:
            print(f"[upload] {'Indexed OK' if indexed else 'Index failed (non-critical)'}")

    if verbose:
        print(f"[upload] Done — {dest}")

    return {
        "success": True,
        "agent": agent,
        "domain": domain,
        "confidence": confidence,
        "dest": str(dest),
        "indexed": indexed,
        "files_processed": 1,
    }


def _upload_zip(
    src: Path,
    override_agent: str,
    override_domain: str,
    reindex: bool,
    verbose: bool,
) -> dict:
    """Extracts a ZIP and uploads each supported file."""
    import tempfile
    agents_touched: set[str] = set()
    processed = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(str(src)) as zf:
            zf.extractall(tmpdir)

        for extracted in Path(tmpdir).rglob("*"):
            if extracted.is_file() and extracted.suffix.lower() in SUPPORTED_EXTENSIONS - {".zip"}:
                result = upload(
                    extracted,
                    override_agent=override_agent,
                    override_domain=override_domain,
                    reindex=False,  # batch reindex after all files
                    verbose=verbose,
                )
                if result["success"]:
                    agents_touched.add(result["agent"])
                    processed += 1

    indexed = True
    if reindex:
        for agent in agents_touched:
            if verbose:
                print(f"[upload] Indexing {agent}...")
            indexed = _reindex(agent) and indexed

    return {
        "success": processed > 0,
        "agent": ", ".join(agents_touched),
        "domain": override_domain or "auto",
        "confidence": 1.0 if override_domain else 0.8,
        "dest": str(JARVIS / ".claude" / "agents"),
        "indexed": indexed,
        "files_processed": processed,
    }


def main():
    load_env()
    import argparse

    parser = argparse.ArgumentParser(description="DQIII8 Knowledge Upload")
    parser.add_argument("file", help="File to upload (PDF/MD/TXT/DOCX/ZIP)")
    parser.add_argument("--agent", "-a", default="", help="Force agent (skip auto-detection)")
    parser.add_argument("--domain", "-d", default="", help="Force domain")
    parser.add_argument("--no-reindex", action="store_true", help="Skip re-indexing")
    args = parser.parse_args()

    result = upload(
        args.file,
        override_agent=args.agent,
        override_domain=args.domain,
        reindex=not args.no_reindex,
        verbose=True,
    )

    if not result["success"]:
        sys.exit(1)

    print(f"\n[upload] Summary:")
    print(f"  agent:     {result['agent']}")
    print(f"  domain:    {result['domain']}")
    print(f"  files:     {result['files_processed']}")
    print(f"  indexed:   {result['indexed']}")
    print(f"  dest:      {result['dest']}")


if __name__ == "__main__":
    main()
