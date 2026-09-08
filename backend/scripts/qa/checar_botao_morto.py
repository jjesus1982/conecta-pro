#!/usr/bin/env python3
"""BOTÃO MORTO: endpoint que uma tela do redesign chama e o app não tem.

Estreia 07/09/2026: 4.310 referências em ~620 telas, 3 mortas — duas por `{ano}/{mes}` e
`{client_id}` literais na URL (o FormScreen manda os campos como query, nunca monta path
param) e uma rota que nunca existiu (`/analytics/executive/kpis/recalcular`). Os três
botões davam 404 desde que nasceram e ninguém viu: nada explode, o usuário só desiste.

Roda DENTRO do container (precisa de `main_production` para a tabela de rotas e dos
builders para as telas). Confere método também: rota que existe só com GET e a tela usa
POST é botão morto do mesmo jeito. Linha canônica: `TOTAL: N botão(ões) morto(s)`.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys

sys.path.insert(0, "/app" if os.path.isdir("/app") else os.path.join(os.path.dirname(__file__), "..", ".."))


def _rotas(app) -> list[tuple[re.Pattern, set[str]]]:
    out = []

    def walk(routes, prefix=""):
        for r in routes:
            p, ms = getattr(r, "path", None), getattr(r, "methods", None)
            if p and ms:
                rx = "^" + re.sub(r"\\\{[^}]+\\\}", r"[^/]+", re.escape(prefix + p)) + "$"
                out.append((re.compile(rx), set(ms)))
            sub = getattr(r, "routes", None)
            if sub:
                walk(sub, prefix + (p or ""))

    walk(app.routes)
    return out


def _endpoints(o, acc):
    if isinstance(o, dict):
        if isinstance(o.get("endpoint"), str):
            acc.append((o["endpoint"], (o.get("method") or "POST").upper()))
        for v in o.values():
            _endpoints(v, acc)
    elif isinstance(o, list):
        for v in o:
            _endpoints(v, acc)


async def main() -> int:
    import main_production  # noqa: F401,PLC0415 — primeiro, sempre
    from core.database import async_session_factory  # noqa: PLC0415
    from modules.operacional.controllers import redesign_data_controller as RD  # noqa: PLC0415

    rotas = _rotas(main_production.app)

    def vivo(ep: str, metodo: str) -> str:
        ep = ep.split("?")[0]
        bate = False
        for rx, ms in rotas:
            if rx.match(ep):
                bate = True
                if metodo in ms:
                    return "ok"
        return "metodo" if bate else "morto"

    mortos: list[str] = []
    total = 0
    async with async_session_factory() as db:
        for mod, build in sorted(RD.BUILDERS.items()):
            try:
                out = await build(db)
            except Exception as exc:  # noqa: BLE001 — módulo que não constrói é outro caçador
                print(f"  ! {mod}: não construiu ({str(exc)[:80]})")
                continue
            # Form cujo endpoint não está em `submit` (o FormScreen só lê scr.submit.endpoint):
            # a URL até existe, mas o botão não chama nada — foi assim com "Cobranças do mês" (07/09).
            for slug, scr in out.items():
                if isinstance(scr, dict) and scr.get("type") == "form" and not (
                        isinstance(scr.get("submit"), dict) and scr["submit"].get("endpoint")):
                    total += 1
                    mortos.append(f"{mod}/{slug}: form sem submit.endpoint (o botão não chama nada)")
            acc: list[tuple[str, str]] = []
            _endpoints(json.loads(json.dumps(out, default=str)), acc)
            for ep, me in sorted(set(acc)):
                if not ep.startswith("/api/"):
                    continue
                total += 1
                v = vivo(ep, me)
                if v != "ok":
                    mortos.append(f"{mod}: {me} {ep}" + ("  (rota existe, método não)" if v == "metodo" else "")
                                  + ("  ({…} literal — o front não monta path param)" if "{" in ep else ""))
    # Tela definida DEPOIS de montar_grupos(out) e listada como aba de grupo: a aba não nasce e a
    # tela só abre por URL direta — foi assim com 16 telas do Financeiro (07/09/2026, medido pelo
    # navegador). Checagem estática nos builders que têm um _*_grupos.py ao lado.
    import pathlib
    import re as _re
    _dir = pathlib.Path(RD.__file__).parent / "redesign_builders"
    for _g in sorted(_dir.glob("_*_grupos.py")):
        _tabs = set(_re.findall(r'\("([a-z0-9-]+)", "[^"]+"\)', _g.read_text(encoding="utf-8")))
        for _b in _dir.glob("*.py"):
            _src = _b.read_text(encoding="utf-8")
            if _b.name.startswith("_") or f"from modules.operacional.controllers.redesign_builders.{_g.stem} import" not in _src:
                continue
            _linhas = _src.split("\n")
            _calls = [i for i, l in enumerate(_linhas) if _re.match(r"\s+montar_grupos\(out\)", l)]
            if not _calls:
                continue
            for i, l in enumerate(_linhas[_calls[-1] + 1:], start=_calls[-1] + 2):
                _m = _re.match(r'\s*out\["([a-z0-9-]+)"\]\s*=', l)
                if _m and _m.group(1) in _tabs:
                    total += 1
                    mortos.append(f"{_b.name}:{i}: tela '{_m.group(1)}' definida DEPOIS de montar_grupos — a aba não nasce")
    for m in mortos:
        print("  ", m)
    print(f"{total} referência(s) a endpoint em {len(RD.BUILDERS)} módulo(s) do redesign")
    print(f"TOTAL: {len(mortos)} botão(ões) morto(s)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
