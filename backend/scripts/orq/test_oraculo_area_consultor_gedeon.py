#!/usr/bin/env python3
"""Oráculo — o form do Consultor GEDEON só oferece área que o validador aceita, e manda pelo
canal que o validador LÊ.

28/09/2026. Dois defeitos da mesma família («o formulário oferece uma palavra que o endpoint
recusa»), os dois medidos contra o contêiner antes do conserto:

  (1) `documentos.py` oferecia `area` como TEXTO LIVRE com placeholder «Ex.: folha, documentos,
      kit» (tela `gedeon-perguntar`) e «Ex.: folha, documentos» (tela `gedeon-perguntar-arquivo`).
      `AREAS_VALIDAS` é {montagem, checklist, intercorrencias, folha}: de três valores sugeridos,
      DOIS eram recusados. Medido: `{"area":"documentos"}` → HTTP 422 «Área inválida 'documentos'.
      Válidas: checklist, folha, intercorrencias, montagem»; `{"area":"kit"}` → o mesmo 422.

  (2) a tela com anexo mandava `area`/`pergunta` na QUERY STRING (`submit.query`), mas a rota
      declara os dois como `Form(...)` — que lê SÓ o corpo multipart. Resultado medido: HTTP **200**
      com a pergunta da usuária DESCARTADA em silêncio (a linha gravada em `gedeon_consultas` veio
      `area='checklist'` e `pergunta='Analise este documento no contexto do fechamento do kit.'`).
      Um 422 barulhento tinha sido melhor; este devolvia resposta plausível sobre outra pergunta.

O que este arquivo afirma é REGRA, não fotografia — nenhum valor de área, nome de tela ou
placeholder está fixado aqui. As duas afirmações derivam da FONTE:

  (a) **as opções saem do validador.** Para toda tela de `documentos.py` cujo endpoint bate em
      `/gedeon/consultor/perguntar*`, o campo `area` tem de ser `select` e o CONJUNTO de
      `options[].value` tem de ser IGUAL a `consultor_service.AREAS_VALIDAS` — importado, não
      copiado. Área nova no backend deixa isto vermelho até alguém abrir o form; área removida,
      idem. E o `value` default tem de ser um dos válidos (select que abre num valor recusado é o
      mesmo defeito com outra cara).

  (b) **o campo vai pelo canal que a rota lê.** Para toda tela de `documentos.py` com
      `submit.multipart`, se a assinatura REAL da função da rota declara algum parâmetro como
      `Form(...)`, então o form NÃO pode pôr `submit.query` — senão o valor sai pela URL e a rota
      cai no default sem reclamar. A assinatura é lida por introspecção do app montado (é ela a
      fonte, não a minha lembrança dela).

Não fixa: nenhuma área, nenhum id de tela, nenhuma data, nenhuma pessoa. Se o Consultor GEDEON
ganhar uma terceira tela com anexo, ela entra na conta sozinha.

Uso:  docker exec conecta-pro-backend python scripts/orq/test_oraculo_area_consultor_gedeon.py
"""

from __future__ import annotations

import asyncio
import inspect
import sys

sys.path.insert(0, "/app")


def _endpoints_com_form() -> dict[str, set[str]]:
    """{caminho da rota: nomes dos parâmetros declarados como Form(...)}, lido do app montado."""
    from fastapi.params import Form

    from main_production import app

    fora: dict[str, set[str]] = {}
    for r in app.routes:
        fn = getattr(r, "endpoint", None)
        caminho = getattr(r, "path", None)
        if fn is None or caminho is None:
            continue
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            continue
        formais = {n for n, p in sig.parameters.items() if isinstance(p.default, Form)}
        if formais:
            fora[caminho] = formais
    return fora


def _telas_form(out: dict) -> list[tuple[str, dict]]:
    """Achata a saída do builder em (id da tela, dict da tela) para as que são form com submit."""
    achadas: list[tuple[str, dict]] = []
    for tid, tela in out.items():
        if isinstance(tela, dict) and tela.get("type") == "form" and isinstance(tela.get("submit"), dict):
            achadas.append((str(tid), tela))
    return achadas


async def main() -> int:
    from core.database import async_session_factory
    from modules.gedeon.services.consultor_service import AREAS_VALIDAS
    from modules.operacional.controllers.redesign_builders import documentos

    validas = {str(a).strip().lower() for a in AREAS_VALIDAS}
    falhas: list[str] = []

    async with async_session_factory() as db:
        out = await documentos.build(db)

    telas = _telas_form(out)
    if not telas:
        print("   ✗ o builder de documentos não devolveu NENHUM form — oráculo cego")
        return 1

    # ── (a) as opções de `area` saem do validador ────────────────────────────────────────
    conferidas_a = 0
    for tid, tela in telas:
        ep = str(tela["submit"].get("endpoint") or "")
        if "/gedeon/consultor/perguntar" not in ep:
            continue
        campo = next((f for f in (tela.get("fields") or []) if isinstance(f, dict) and f.get("key") == "area"), None)
        if campo is None:
            falhas.append(f"{tid} → {ep}: manda para o validador de área e NÃO tem campo `area`")
            continue
        conferidas_a += 1
        if campo.get("type") != "select":
            falhas.append(
                f"{tid} → {ep}: campo `area` é `{campo.get('type')}` (texto livre) e o backend só "
                f"aceita {sorted(validas)} — placeholder «{campo.get('ph') or ''}»"
            )
            continue
        ofertadas = {str(o.get("value")).strip().lower() for o in (campo.get("options") or [])}
        if ofertadas != validas:
            so_no_form = sorted(ofertadas - validas)
            so_no_backend = sorted(validas - ofertadas)
            falhas.append(
                f"{tid} → {ep}: opções de `area` divergem de AREAS_VALIDAS — "
                f"oferecidas e RECUSADAS: {so_no_form or '—'} · válidas e NÃO oferecidas: "
                f"{so_no_backend or '—'}"
            )
        default = str(campo.get("value") or "").strip().lower()
        if default and default not in validas:
            falhas.append(f"{tid} → {ep}: select abre no valor `{default}`, que o backend recusa")

    if not conferidas_a:
        falhas.append(
            "nenhuma tela de documentos.py aponta para /gedeon/consultor/perguntar* — "
            "a tela sumiu ou o endpoint mudou; oráculo cego de propósito não fica verde"
        )

    # ── (b) multipart + Form(...) na rota ⇒ proibido `submit.query` ──────────────────────
    form_por_rota = _endpoints_com_form()
    conferidas_b = 0
    for tid, tela in telas:
        sub = tela["submit"]
        if not sub.get("multipart"):
            continue
        ep = str(sub.get("endpoint") or "")
        formais = next((v for k, v in form_por_rota.items() if ep.endswith(k)), None)
        if formais is None:
            continue  # rota não usa Form(...): `query` ali é legítimo
        conferidas_b += 1
        if not sub.get("query"):
            continue
        chaves = {str(f.get("key")) for f in (tela.get("fields") or []) if isinstance(f, dict)}
        perdidos = sorted(chaves & formais)
        falhas.append(
            f"{tid} → {ep}: multipart COM `query`, mas a rota declara {sorted(formais)} como "
            f"Form(...) — {perdidos or 'os campos'} sairiam pela URL e a rota cairia no default, "
            f"devolvendo 200 com o valor da usuária descartado"
        )

    for f in falhas:
        print(f"   ✗ {f}")
    if not falhas:
        print(f"   ✓ (a) {conferidas_a} form(s) de área: opções == AREAS_VALIDAS {sorted(validas)}")
        print(f"   ✓ (b) {conferidas_b} form(s) multipart sobre rota com Form(...): nenhum com `query`")
    print(f"\nTOTAL: {len(falhas)} divergência(s) form × validador")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
