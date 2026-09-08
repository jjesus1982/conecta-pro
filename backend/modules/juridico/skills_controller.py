"""
Controller para skills jurídicas adaptadas — Conecta Mais
Serve os templates e prompts das skills 089, 090, 092, 095, 253, 305, 318
"""

import re
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/juridico", tags=["Jurídico"])

SKILLS_DIR = Path("/tmp/skills/juridico")  # nosec B108


def _parse_frontmatter(text: str) -> dict:
    """Extrai campos name e description do frontmatter YAML simples."""
    meta: dict = {}
    for line in text.splitlines():
        m = re.match(r"^(name|description):\s*(.+)$", line)
        if m:
            meta[m.group(1)] = m.group(2).strip()
    return meta


def parse_skill(filepath: Path) -> dict:
    """Extrai metadata e conteúdo de um arquivo .md de skill."""
    content = filepath.read_text(encoding="utf-8")
    # Extrair frontmatter YAML (---...---)
    fm_match = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
    if fm_match:
        meta = _parse_frontmatter(fm_match.group(1))
        body = fm_match.group(2)
    else:
        meta = {}
        body = content
    return {
        "id": filepath.stem,
        "name": meta.get("name", filepath.stem),
        "description": meta.get("description", ""),
        "content": body,
        "filename": filepath.name,
    }


