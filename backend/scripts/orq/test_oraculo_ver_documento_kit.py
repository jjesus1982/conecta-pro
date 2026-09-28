#!/usr/bin/env python3
"""Conferir documento de kit se faz NA TELA, e o chip não pode prometer o que não abre.

Pedido da Pyetra (28/09/2026): «na aba ver, preciso fazer a conferência sem precisar baixar
toda vez». Ela conferia baixando um ZIP de 43 arquivos para olhar um. Três coisas tinham de
ficar de pé ao mesmo tempo, e este oráculo afirma as três como REGRA — sem nome de pessoa,
sem id, sem data fixa; tudo é descoberto do banco e da resposta do próprio endpoint.

  (A) CHIP EXISTE — toda linha das telas `arquivos` e `kit-documentos` do módulo `documentos`
      traz um chip de documento. Até 28/09 não trazia nenhum: um comentário no builder dizia
      que «a rota serve ged_documents (tabela VAZIA)», olhando a rota do OUTRO módulo. A rota
      certa (`/people-management/ged/documents/{id}/download`) sempre serviu ged_kit_documents.

  (B) CHIP HONESTO — habilitado ⟺ o arquivo REALMENTE abre; desabilitado ⟹ tem motivo.
      A verdade de referência não é o chip, é o banco + o disco: `file_path` vazio, URL http
      (Drive: o fetch com Bearer morre no CORS do 307), `/inter/*`, ou caminho local que
      `os.path.isfile` não encontra ⟹ tem de estar cinza. Caminho local existente ⟹ tem de
      estar ligado. E a amostra dos ligados é CHAMADA de verdade: 200 ou o chip mentiu.

  (C) A ROTA ABRE, NÃO BAIXA — sem `?download` responde `Content-Disposition: inline` e grava
      `viewed` em `ged_kit_access_logs`; com `?download=1` (o único caso que o
      `frontend/src/lib/pdf.ts` manda) responde `attachment` e grava `downloaded`. Sem isso o
      log MENTE sobre quem só olhou, e a tela continua enchendo a pasta de Downloads.

⚠️ (A)/(B) leem a resposta do processo RODANDO, não o arquivo no disco: rodar isto com deploy
pendente mede o código antigo. Confira a camada antes de acreditar no verde.

Provado vermelho em 28/09/2026 contra o estado anterior (docsfn removido do builder +
`git show HEAD` do document_controller): (A) falhou em 500/500 linhas sem chip, (C) falhou em
`attachment` e em `downloaded` para acesso sem `?download`.

Receita:
  docker exec -e PYTHONPATH=/app conecta-pro-backend \
    python3 /app/scripts/orq/test_oraculo_ver_documento_kit.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import sys

sys.path.insert(0, "/app")
logging.disable(logging.CRITICAL)  # o import do app despeja o boot inteiro no stdout

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from core.auth.jwt import create_access_token  # noqa: E402
from core.database.session import async_session_factory  # noqa: E402

BASE = "http://127.0.0.1:8080"
TELAS = ("arquivos", "kit-documentos")  # as duas telas que listam ged_kit_documents
ROTA = "/api/v1/people-management/ged/documents/{}/download"
AMOSTRA = 15  # quantos chips habilitados são realmente chamados

falhas: list[str] = []


def _checa(cond: bool, msg: str) -> None:
    print(("  ok   " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


async def _usuario_com_ged(db) -> str:
    """Por PAPEL, nunca por e-mail: um ativo que alcance o GED. E-mail hardcoded já quebrou
    quatro oráculos aqui quando a pessoa saiu da empresa."""
    row = (
        await db.execute(
            text(
                "SELECT id FROM users WHERE is_active=true AND ('all'=ANY(permissions) "
                "OR 'module:ged'=ANY(permissions)) ORDER BY created_at LIMIT 1"
            )
        )
    ).first()
    assert row, "nenhum usuário ativo alcança o GED — oráculo não tem como se autenticar"
    return str(row[0])


def _verdade_do_disco(file_path: str | None) -> str:
    """O que DEVERIA acontecer com este documento, lido do dado + do disco (não do chip)."""
    from modules.people_management.ged.services.document_collector_service import GED_STORAGE_BASE

    fp = (file_path or "").strip()
    if not fp:
        return "cinza"
    if fp.startswith(("http://", "https://")) or fp.startswith("/inter/"):
        return "cinza"
    full = fp if os.path.isabs(fp) else os.path.join(GED_STORAGE_BASE, fp)
    return "abre" if os.path.isfile(full) else "cinza"


async def main() -> int:
    async with async_session_factory() as db:
        uid = await _usuario_com_ged(db)
        tok = create_access_token(subject=uid)
        cab = {"Authorization": f"Bearer {tok}"}

        async with httpx.AsyncClient(base_url=BASE, timeout=180.0) as cli:
            r = await cli.get("/api/v1/redesign/data/documentos", headers=cab)
            assert r.status_code == 200, f"módulo documentos não carregou: HTTP {r.status_code}"
            telas = r.json().get("screens") or {}

            # ── (A) toda linha tem chip ────────────────────────────────────────────────
            print("(A) chip de documento em TODA linha")
            ids_ligados: list[str] = []
            for nome in TELAS:
                tela = telas.get(nome) or {}
                linhas = tela.get("rows") or []
                _checa(bool(linhas), f"{nome}: tela existe e tem linhas ({len(linhas)})")
                sem = sum(1 for ln in linhas if not (ln.get("docs") or []))
                _checa(sem == 0, f"{nome}: {len(linhas) - sem}/{len(linhas)} linhas com chip")
                muda = 0  # chip cinza que não diz por quê: pior que chip nenhum
                for ln in linhas:
                    for c in ln.get("docs") or []:
                        did = (c.get("url") or "").rsplit("/download", 1)[0].rsplit("/", 1)[-1]
                        if c.get("disabled"):
                            muda += 0 if c.get("motivo") else 1
                        elif did:
                            ids_ligados.append(did)
                _checa(muda == 0, f"{nome}: nenhum chip cinza sem motivo (mudos: {muda})")

            # ── (B) habilitado ⟺ abre de verdade ─────────────────────────────────────
            print("(B) chip honesto: habilitado só quando o arquivo existe")
            # A verdade vem da FONTE (banco + disco) e é comparada com o chip, documento a
            # documento. Um chip ligado sobre arquivo inexistente é a mentira que isto caça.
            todos = {
                str(k): v
                for k, v in (
                    await db.execute(text("SELECT id, file_path FROM ged_kit_documents"))
                ).fetchall()
            }
            mentiu = [d for d in set(ids_ligados) if _verdade_do_disco(todos.get(d)) != "abre"]
            _checa(not mentiu, f"nenhum chip ligado sobre arquivo que não abre (mentiram: {len(mentiu)})")

            ligados = sorted(set(ids_ligados))
            _checa(bool(ligados), f"há chip ligado para chamar ({len(ligados)} documentos)")
            random.seed(0)
            ruins = []
            for did in random.sample(ligados, min(AMOSTRA, len(ligados))):
                resp = await cli.get(ROTA.format(did), headers=cab)
                if resp.status_code != 200:
                    ruins.append((did, resp.status_code))
            _checa(not ruins, f"amostra de {min(AMOSTRA, len(ligados))} chips ligados: todos 200 ({ruins})")

            # ── (C) inline × attachment, viewed × downloaded ─────────────────────────
            print("(C) a rota ABRE por padrão e só baixa quando pedem")
            # o alvo sai do BANCO, não dos chips: (C) mede a rota e tem de rodar mesmo quando a
            # tela está sem chip nenhum — foi assim que (A) e (C) apareceram vermelhas juntas
            alvo = next((d for d, fp in todos.items() if _verdade_do_disco(fp) == "abre"), None)
            assert alvo, "nenhum documento de kit com arquivo em disco — nada para abrir"
            kit = (
                await db.execute(text("SELECT kit_id FROM ged_kit_documents WHERE id=:i"), {"i": alvo})
            ).scalar()

            async def _acesso(query: str) -> tuple[str, str | None]:
                antes = (
                    await db.execute(
                        text("SELECT count(*) FROM ged_kit_access_logs WHERE kit_id=:k"), {"k": kit}
                    )
                ).scalar()
                resp = await cli.get(ROTA.format(alvo) + query, headers=cab)
                assert resp.status_code == 200, f"acesso '{query}' deu HTTP {resp.status_code}"
                # o log é gravado por OUTRA sessão de banco: só uma leitura nova enxerga
                await db.commit()
                depois = (
                    await db.execute(
                        text(
                            "SELECT action FROM ged_kit_access_logs WHERE kit_id=:k "
                            "ORDER BY created_at DESC LIMIT 1"
                        ),
                        {"k": kit},
                    )
                ).scalar()
                novo = (
                    await db.execute(
                        text("SELECT count(*) FROM ged_kit_access_logs WHERE kit_id=:k"), {"k": kit}
                    )
                ).scalar()
                assert novo == antes + 1, f"acesso '{query}' não gravou log ({antes}→{novo})"
                return resp.headers.get("content-disposition", ""), depois

            cd, acao = await _acesso("")
            _checa(cd.startswith("inline"), f"sem ?download → Content-Disposition inline (veio: {cd[:40]!r})")
            _checa(acao == "viewed", f"sem ?download → log grava 'viewed' (gravou: {acao!r})")

            cd, acao = await _acesso("?download=1")
            _checa(cd.startswith("attachment"), f"?download=1 → attachment (veio: {cd[:40]!r})")
            _checa(acao == "downloaded", f"?download=1 → log grava 'downloaded' (gravou: {acao!r})")

    print("\n" + (f"VERMELHO — {len(falhas)} falha(s)" if falhas else "VERDE"))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
