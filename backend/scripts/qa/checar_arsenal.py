#!/usr/bin/env python3
"""O arsenal está dizendo a verdade sobre o sistema?

`docs/ARSENAL_SKILLS.md` afirma fatos: quantas skills existem, onde o código mora, que
comandos rodar, quantos oráculos há. Documento apodrece igual a oráculo — e com consequência
pior, porque quem segue instrução velha erra com confiança.

Já aconteceu: a `fecha-modulo` afirmava que não havia `ERP_PASS` no `.env` e mandava
reportar a lente TELA como "NÃO VERIFICADA". Havia. O próximo agente teria pulado o teste
por causa de uma frase desatualizada.

E há a deriva do espelho: o plugin vive em `~/.claude/` e a cópia versionada em
`skills/_plugin/`. Editar de um lado só é questão de tempo.

Roda sozinho (não precisa do banco):
    python3 backend/scripts/qa/checar_arsenal.py
"""
from __future__ import annotations

import filecmp
import json
import re
from pathlib import Path

REPO = Path("/opt/conecta-pro")
VIVO = Path("/root/.claude/skills/conecta-pro-skills")
ESPELHO = REPO / "skills/_plugin/conecta-pro-skills"
ARSENAL = REPO / "docs/ARSENAL_SKILLS.md"
ORQ = REPO / "backend/scripts/orq"


def _falhas() -> list[str]:
    out: list[str] = []

    if not ARSENAL.exists():
        return [f"{ARSENAL} não existe — o arsenal sumiu"]
    doc = ARSENAL.read_text(encoding="utf-8")

    # ── 1. skill citada no arsenal existe de verdade? ──────────────────────────
    plugin = json.loads((VIVO / ".claude-plugin/plugin.json").read_text())
    registradas = {Path(s).name for s in plugin["skills"]}
    em_disco = {p.name for p in (VIVO / "skills").iterdir() if (p / "SKILL.md").exists()}

    so_registrada = registradas - em_disco
    if so_registrada:
        out.append(f"plugin.json registra skill que NÃO existe em disco: {sorted(so_registrada)}")
    so_disco = em_disco - registradas
    if so_disco:
        out.append(f"skill em disco e FORA do plugin.json (não carrega): {sorted(so_disco)}")

    citadas = set(re.findall(r"conecta-pro-skills:([a-z0-9-]+)", doc)) | \
        set(re.findall(r"\*\*`?([a-z][a-z0-9-]+)`?\*\*\s*\|", doc))
    fantasmas = {c for c in citadas if c in em_disco or c in registradas}
    inexistentes = {c for c in re.findall(r"conecta-pro-skills:([a-z0-9-]+)", doc)
                    if c not in em_disco}
    if inexistentes:
        out.append(f"o arsenal manda invocar skill que não existe: {sorted(inexistentes)}")
    faltando_no_doc = em_disco - fantasmas - set(re.findall(r"`([a-z0-9-]+)`", doc))
    if faltando_no_doc:
        out.append(f"skill existe e o arsenal não cita: {sorted(faltando_no_doc)}")

    # ── 2. contagem que o arsenal afirma ───────────────────────────────────────
    m = re.search(r"Nossas \(`conecta-pro-skills`\) — (\d+)", doc)
    if m and int(m.group(1)) != len(em_disco):
        out.append(f"arsenal diz {m.group(1)} skills nossas; existem {len(em_disco)}")

    # ── 3. espelho versionado × cópia viva ─────────────────────────────────────
    if not ESPELHO.exists():
        out.append(f"espelho {ESPELHO} não existe — as skills voltaram a viver só em ~/.claude")
    else:
        divergiu = []
        for p in (VIVO / "skills").rglob("SKILL.md"):
            eq = ESPELHO / "skills" / p.relative_to(VIVO / "skills")
            if not eq.exists() or not filecmp.cmp(p, eq, shallow=False):
                divergiu.append(p.parent.name)
        if divergiu:
            out.append(f"espelho DIVERGE da cópia viva em: {sorted(divergiu)} "
                       f"— alguém editou de um lado só")

    # ── 4. caminhos e comandos que o arsenal manda usar ────────────────────────
    for caminho in sorted(set(re.findall(r"`((?:backend|scripts|docs|auditoria)/[\w./-]+)`", doc))):
        alvo = REPO / caminho
        if any(x in caminho for x in ("<", ">", "AAAA", "*")):
            continue
        if not alvo.exists():
            out.append(f"arsenal cita caminho que não existe: {caminho}")

    # ── 5. a varredura diária está mesmo agendada? ─────────────────────────────
    try:
        import subprocess
        cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        if "oraculos_diarios.sh" not in cron:
            out.append("varredura dos oráculos NÃO está no crontab — o arsenal promete vigia diária")
        else:
            linha = next(x for x in cron.splitlines() if "oraculos_diarios.sh" in x and not x.strip().startswith("#"))
            hora = " ".join(linha.split()[:5])
            if not re.search(r"varredura diária.*?(\d{2}):(\d{2})|(\d{2}):(\d{2}).*?varredura", doc, re.I):
                pass  # o doc não fixa horário; nada a conferir
            out.append(f"OK-INFO varredura agendada: {hora}")
    except Exception as exc:  # noqa: BLE001
        out.append(f"não consegui ler o crontab: {exc}")

    # ── 6. contagem de oráculos ────────────────────────────────────────────────
    n_orq = len([p for p in ORQ.glob("*.py") if not p.name.startswith("_")])
    for m in re.finditer(r"(\d+)\s+or[áa]culos", doc):
        if abs(int(m.group(1)) - n_orq) > 0 and int(m.group(1)) not in (0,):
            out.append(f"arsenal diz '{m.group(1)} oráculos'; existem {n_orq} em {ORQ.name}/")
            break

    return out


def main() -> int:
    falhas = [f for f in _falhas() if not f.startswith("OK-INFO")]
    infos = [f[8:] for f in _falhas() if f.startswith("OK-INFO")]
    for i in infos:
        print(f"  info: {i}")
    if not falhas:
        print("arsenal confere: skills registradas, espelho igual, caminhos existem, vigia agendada")
        return 0
    print(f"\n{len(falhas)} divergência(s) entre o arsenal e o sistema:\n")
    for f in falhas:
        print(f"  x {f}")
    print("\nCorrija o DOCUMENTO ou o sistema — mas não deixe os dois discordando: "
          "instrução velha faz o próximo errar com confiança.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
