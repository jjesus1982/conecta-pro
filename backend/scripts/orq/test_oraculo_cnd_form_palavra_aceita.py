#!/usr/bin/env python3
"""Toda palavra que os formulários de CND OFERECEM tem que ser palavra que o gedeon ACEITA.

Origem (28/09/2026): a Pyetra não conseguia registrar nenhuma CND emitida à mão — e a Caixa
bloqueia a VPS por IP, então subir o PDF à mão é o ÚNICO caminho. O formulário
«Certidões — subir PDF emitido manualmente» oferecia `document_type` = "federal" / "caixa",
mas `modules/gedeon/controllers/cnd_controller.py` valida
`if document_type not in PORTAL_OFICIAL` — e as chaves de PORTAL_OFICIAL são
"certidao_negativa_federal" / "certidao_negativa_fgts". Medido no endpoint real:
2 de 2 valores oferecidos davam HTTP 400 «document_type inválido p/ upload manual».
O formulário e o validador estavam certos cada um por si; ninguém tinha olhado os dois ao
mesmo tempo. Nenhum teste pegava porque cada lado, isolado, é coerente.

A REGRA que este oráculo afirma (não a fotografia de hoje):

  (A) Para CADA opção de `document_type` do form de upload, a MESMA função de validação que
      o endpoint usa tem que aceitar. O conjunto aceito é lido de `PORTAL_OFICIAL` em tempo
      de execução — se alguém renomear uma chave lá, este oráculo fica vermelho, que é
      exatamente o que se quer. Nenhum valor esperado está escrito aqui.
  (B) A mesma pergunta no form irmão «emitir pelo robô»: cada opção de `portais` tem que
      passar pelo filtro `[p for p in portais if p in DOCTYPE]` do endpoint /emitir — que
      devolve 400 «nenhum portal válido» se a lista esvaziar.
  (C) Certidão é POR CNPJ: o campo `cnpj` dos dois forms tem que oferecer TODAS as empresas
      da tabela `empresas` (o conjunto vem do banco, não de uma lista fixa), ser obrigatório
      e NÃO ter default. O bug irmão era esse: o CNPJ vinha fixo na Patrimonial enquanto a
      certidão vencida era a da Eletrônica — a tela não alcançava o único caso que importava.
  (D) A tela tem que carregar o link do portal oficial que o backend já monta, senão ela
      manda emitir à mão sem dizer onde.

Por que (A)+(B)+(C) juntos e não só (A): (A) sozinho fica verde num form que aceita o
doctype certo mas de uma empresa só — foi assim que o defeito passou. Cada asserção cobre
um lado do mesmo par forma/validador.

🔒 SÓ LEITURA: monta as telas e compara conjuntos. Não chama o endpoint, não escreve em
`ged_certidoes`, não sobe PDF. Provar isto escrevendo no banco de produção seria pagar com
dado real por uma pergunta que se responde com dois conjuntos.

    docker exec -e PYTHONPATH=/app conecta-pro-backend \
        python3 /app/scripts/orq/test_oraculo_cnd_form_palavra_aceita.py

Linha canônica: `TOTAL: <n> divergência(s) forma×validador`. Exit 1 quando há achado.
"""
from __future__ import annotations

import asyncio
import logging
import sys

sys.path.insert(0, "/app")
logging.disable(logging.CRITICAL)


async def main() -> int:
    from sqlalchemy import text

    from core.database.session import async_session_factory

    # O validador REAL do endpoint, importado de onde ele vive — não uma cópia da regra.
    from modules.gedeon.controllers.cnd_controller import DOCTYPE, PORTAL_OFICIAL
    from modules.operacional.controllers.redesign_builders.documentos import (
        _ligar_lote3_20260908,
    )

    achados: list[str] = []
    telas: dict = {}
    async with async_session_factory() as db:
        await _ligar_lote3_20260908(db, telas)
        cnpjs_banco = {
            r[0] for r in (await db.execute(text("SELECT cnpj FROM empresas"))).all() if r[0]
        }

    def campos(slug: str) -> dict | None:
        scr = telas.get(slug)
        if not scr:
            achados.append(f"{slug}: tela não foi construída (exception engolida no try do builder)")
            return None
        return {f.get("key"): f for f in scr.get("fields") or []}

    up = campos("cnd-upload")
    em = campos("cnd-emitir")

    # (A) document_type oferecido ⊆ document_type aceito (chaves de PORTAL_OFICIAL)
    if up is not None:
        opts = [o.get("value") for o in (up.get("document_type") or {}).get("options") or []]
        if not opts:
            achados.append("cnd-upload: campo document_type sem nenhuma opção")
        for v in opts:
            if v not in PORTAL_OFICIAL:  # a MESMA condição de cnd_controller.upload_cnd
                achados.append(
                    f"cnd-upload: oferece document_type={v!r}, que o validador do gedeon RECUSA "
                    f"com 400 (aceitos: {sorted(PORTAL_OFICIAL)})"
                )

    # (B) portais oferecidos passam pelo filtro do /emitir
    if em is not None:
        pos = [o.get("value") for o in (em.get("portais") or {}).get("options") or []]
        if not pos:
            achados.append("cnd-emitir: campo portais sem nenhuma opção")
        for v in pos:
            if v not in DOCTYPE:
                achados.append(
                    f"cnd-emitir: oferece portal={v!r}, descartado pelo filtro do /emitir "
                    f"(aceitos: {sorted(DOCTYPE)})"
                )

    # (C) certidão é por CNPJ: as duas telas oferecem TODAS as empresas, sem default
    def _norm(c: str) -> str:
        return "".join(ch for ch in str(c) if ch.isdigit())

    for slug, cps in (("cnd-upload", up), ("cnd-emitir", em)):
        if cps is None:
            continue
        f = cps.get("cnpj")
        if not f:
            achados.append(f"{slug}: não tem campo cnpj — certidão é por CNPJ")
            continue
        if f.get("type") != "select":
            achados.append(
                f"{slug}: campo cnpj é {f.get('type')!r} com valor {f.get('value')!r} — "
                f"tem que ser select das {len(cnpjs_banco)} empresa(s) do banco"
            )
            continue
        ofertados = {_norm(o.get("value")) for o in f.get("options") or []}
        faltando = {_norm(c) for c in cnpjs_banco} - ofertados
        if faltando:
            achados.append(f"{slug}: campo cnpj não oferece a(s) empresa(s) {sorted(faltando)}")
        if "value" in f:
            achados.append(
                f"{slug}: campo cnpj vem com default {f['value']!r} — dois CNPJs, default "
                "esconde um deles (foi assim que a CND da Eletrônica ficou fora de alcance)"
            )
        if not str(f.get("label", "")).endswith("*"):
            achados.append(f"{slug}: campo cnpj não está marcado como obrigatório")

    # (D) o link do portal oficial que o backend já monta chega na tela
    sub = (telas.get("cnd-upload") or {}).get("sub") or ""
    for k, v in PORTAL_OFICIAL.items():
        if v["url"] not in sub:
            achados.append(f"cnd-upload: a tela não mostra o portal oficial de {k} ({v['url']})")

    for a in achados:
        print(f"   ✗ {a}")
    if not achados:
        print(f"   ✓ cnd-upload: document_type oferecido ⊆ aceito pelo gedeon {sorted(PORTAL_OFICIAL)}")
        print(f"   ✓ cnd-emitir: portais oferecidos ⊆ aceitos pelo /emitir {sorted(DOCTYPE)}")
        print(f"   ✓ as duas telas oferecem as {len(cnpjs_banco)} empresa(s) do banco, sem default")
        print(f"   ✓ os {len(PORTAL_OFICIAL)} links de portal oficial chegam na tela")
    print(f"\nTOTAL: {len(achados)} divergência(s) forma×validador")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
