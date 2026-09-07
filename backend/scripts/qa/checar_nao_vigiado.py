#!/usr/bin/env python3
"""MAPA DO NÃO-VIGIADO: cada tela do redesign × os oráculos e regras que a citam.

Era a lacuna que o ARSENAL_SKILLS.md §6 chamava de "a única que sobrou": cruzar a
superfície com os vigias e devolver o descoberto, ordenado por raio de dano. O Balanço
Patrimonial ficou meses exibindo PL de +R$ 2,02 milhões onde havia prejuízo de R$ 97 mil
porque não havia oráculo contábil — e nada apontava a ausência.

Dois sistemas de vigilância, contados JUNTOS (quem conta só um erra — regra da casa):
  · oráculos `scripts/orq/test_*.py` (varredura da meia-noite)
  · regras proativas `notifications/proativo/regras.py` (beat)

Superfície medida POR COMPORTAMENTO: chama `build(db)` de cada módulo do redesign e lê as
telas que ele devolve — não o que o arquivo declara. Tela é "vigiada" quando algum vigia
cita o slug dela (string literal) — critério fraco de propósito: prova ausência, não
presença. Vigiada aqui ≠ bem vigiada.

Raio de dano: 💰 dinheiro (pagar, pix, folha, boleto…) e 🏛️ governo (esocial, sped, nfse,
fgts…) saem primeiro.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/checar_nao_vigiado.py [--tudo]

Linha canônica (lida por `checar_regressao`): `TOTAL: <n> tela(s) sem vigia`.
Exit 1 quando há tela sem vigia (dívida: entra na base, acusa quando CRESCE).
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import sys

ORQ = pathlib.Path("/app/scripts/orq")
REGRAS = pathlib.Path("/app/modules/notifications/proativo/regras.py")
DINHEIRO = re.compile(r"pag|pix|folha|boleto|cobran|transfer|banc|caixa|recib|holerite|rescis", re.I)
GOVERNO = re.compile(r"esocial|sped|nfs|nfe|fgts|dctf|sefaz|certid|cnd|gov|simples|inss|irrf", re.I)


def _corpus() -> str:
    partes = [p.read_text(errors="replace") for p in ORQ.glob("test_*.py")]
    if REGRAS.exists():
        partes.append(REGRAS.read_text(errors="replace"))
    return "\n".join(partes)


async def main() -> int:
    sys.path.insert(0, "/app")
    import main_production  # noqa: F401,PLC0415 — primeiro, sempre
    from core.database import async_session_factory  # noqa: PLC0415
    from modules.operacional.controllers import redesign_data_controller as RD  # noqa: PLC0415

    corpus = _corpus()
    telas: list[tuple[str, str, str, str]] = []
    nao_verificados: list[str] = []
    async with async_session_factory() as db:
        for mod, build in sorted(RD.BUILDERS.items()):
            try:
                out = await asyncio.wait_for(build(db), timeout=180)
            except Exception as exc:  # noqa: BLE001 — builder quebrado é achado, não parada
                nao_verificados.append(f"{mod}: {type(exc).__name__}: {str(exc)[:60]}")
                continue
            if not isinstance(out, dict):
                nao_verificados.append(f"{mod}: build devolveu {type(out).__name__}")
                continue
            for slug, scr in out.items():
                if not isinstance(scr, dict):
                    continue
                if scr.get("type") == "redirect" or scr.get("groupRef"):
                    continue  # stub de agrupamento, não é superfície
                telas.append((mod, slug, str(scr.get("title") or "")[:50], str(scr.get("type") or "")))

    sem = []
    for mod, slug, titulo, tipo in telas:
        marcas = (f'"{slug}"', f"'{slug}'")
        vigiada = any(m in corpus for m in marcas) if len(slug) >= 4 else \
            any(f'"{mod}"' in corpus and m in corpus for m in marcas)
        if not vigiada:
            flag = ("💰" if DINHEIRO.search(slug + titulo) else "") + ("🏛️" if GOVERNO.search(slug + titulo) else "")
            sem.append((flag, mod, slug, titulo, tipo))
    sem.sort(key=lambda t: (t[0] == "", t[1], t[2]))

    print(f"{len(telas)} tela(s) em {len(RD.BUILDERS)} módulo(s) do redesign · "
          f"{len(telas) - len(sem)} com algum vigia · {len(sem)} sem nenhum\n")
    mostrar = sem if "--tudo" in sys.argv else sem[:60]
    for flag, mod, slug, titulo, tipo in mostrar:
        print(f"   {flag:<3} {mod}/{slug:<34} {tipo:<8} {titulo}")
    if len(sem) > len(mostrar):
        print(f"   (+{len(sem) - len(mostrar)} não listadas — use --tudo)")
    if nao_verificados:
        print("\nNÃO VERIFICADO (builder não respondeu — as telas dele não entraram na conta):")
        for n in nao_verificados:
            print(f"   ? {n}")
    print(f"\nTOTAL: {len(sem)} tela(s) sem vigia")
    return 1 if sem else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
