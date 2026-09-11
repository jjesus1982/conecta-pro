#!/usr/bin/env python3
"""Dispara a pesquisa "você está conseguindo bater seu ponto?" — texto aprovado pelo Jordan.

⚠️ MANDA MENSAGEM REAL, para gente de verdade, em nome da empresa. Por isso:
  · `--enviar` é obrigatório; o padrão é ensaio.
  · **só quem tem número que EXISTE no WhatsApp** (conferido em `on-whatsapp`, um por um, na
    hora). Mandar para número inexistente registra sucesso e não chega a ninguém — seria
    fabricar uma pesquisa cujas respostas nunca viriam. Quem fica de fora sai NOMEADO: a
    ausência dele é informação, não silêncio.
  · lotes com pausa: o número do Baileys é o mesmo do comercial, e cadência de spam queima o
    canal inteiro. Mesma razão do `TETO_POR_RODADA` do lembrete de ponto.
  · idempotente por pessoa: quem já recebeu não recebe de novo (`ponto.pesquisa_enviada` no
    `gp_audit_logs`). Rodar duas vezes por engano não vira duas mensagens.

A resposta volta pelo José Luís, que desde 11/09 reconhece funcionário pelo telefone, se
apresenta como responsável pelo ponto junto com a Pyetra, e registra o que ouvir com a tool
`registrar_resposta_pesquisa_ponto`.

    python3 backend/scripts/disparar_pesquisa_ponto.py
    python3 backend/scripts/disparar_pesquisa_ponto.py --enviar
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import uuid

sys.path.insert(0, "/app")

PAUSA_ENTRE_MENSAGENS = 4.0   # segundos
TAMANHO_DO_LOTE = 12
PAUSA_ENTRE_LOTES = 45.0
ACAO_ENVIO = "ponto.pesquisa_enviada"


async def _alvos(db):
    from sqlalchemy import text

    from modules.integrations.connectors.whatsapp.identidade import SEM_VINCULO

    return (await db.execute(text(
        "SELECT e.id::text AS eid, e.nome, "
        "       coalesce(nullif(e.celular,''), e.telefone,'') AS fone "
        "  FROM employees e "
        " WHERE lower(coalesce(e.status,'ativo')) <> ALL(:sv) "
        "   AND coalesce(e.is_homologacao,false) = false "
        "   AND coalesce(nullif(e.celular,''), e.telefone,'') <> '' "
        "   AND NOT EXISTS (SELECT 1 FROM gp_audit_logs a "
        "                    WHERE a.action = :acao AND a.related_funcionario_id = e.id::text) "
        " ORDER BY e.nome"), {"sv": list(SEM_VINCULO), "acao": ACAO_ENVIO})).mappings().all()


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.integrations.connectors.whatsapp.service import whatsapp_service
    from modules.people_management.ponto.pesquisa_ponto import TEXTO

    enviar = "--enviar" in sys.argv
    async with async_session_factory() as db:
        pessoas = await _alvos(db)

    fila, sem_whatsapp, malformado = [], [], []
    for p in pessoas:
        d = re.sub(r"\D", "", p["fone"] or "")
        if len(d) != 11 or d[2] != "9":
            malformado.append((p["nome"], p["fone"]))
            continue
        jid = await whatsapp_service._resolve_jid("55" + d)
        (fila.append((p, d)) if jid else sem_whatsapp.append((p["nome"], p["fone"])))
        await asyncio.sleep(0.5)

    print(f"alvo: {len(fila)} funcionário(s) com número que EXISTE no WhatsApp")
    for nome, fone in malformado:
        print(f"  FORA (telefone malformado, não dá para mandar): {nome} — {fone}")
    for nome, fone in sem_whatsapp:
        print(f"  FORA (número não existe no WhatsApp): {nome} — {fone}")
    if not enviar:
        print(f"\nENSAIO: {len(fila)} mensagem(ns) seriam enviadas. Rode com --enviar.")
        print("\n--- texto ---\n" + TEXTO.format(primeiro="Fulano"))
        return 0

    enviados, falhas = 0, []
    for i, (p, d) in enumerate(fila):
        primeiro = (p["nome"] or "").split()[0].title()
        try:
            res = await whatsapp_service.send_custom(d, TEXTO.format(primeiro=primeiro))
            ok = str((res or {}).get("status", "")).lower() in ("sent", "ok", "success")
        except Exception as exc:  # noqa: BLE001 — uma falha não cala as outras
            ok, res = False, {"erro": str(exc)[:160]}
        if ok:
            enviados += 1
            async with async_session_factory() as db:
                await db.execute(text(
                    # ⚠️ `gp_audit_logs` tem 11 colunas NOT NULL (actor_user_id, _name, _role,
                    # _module entre elas) — o `tentativa_log` já tinha aprendido isso e eu
                    # repeti o erro escrevendo o INSERT do zero. Mesma convenção dele.
                    "INSERT INTO gp_audit_logs (id, timestamp, action, entity, entity_id, "
                    " description, source_module, actor_user_id, actor_user_name, "
                    " actor_user_role, actor_user_module, related_funcionario_id, extra_data) "
                    "VALUES (CAST(:i AS uuid), (now() AT TIME ZONE 'America/Manaus'), :a, 'ponto', "
                    " :e, 'pesquisa de ponto enviada', 'people_management.ponto', "
                    " 'jose-luis', 'José Luís (pesquisa de ponto)', 'sistema', 'ponto', "
                    " :e, CAST(:x AS jsonb))"),
                    {"i": str(uuid.uuid4()), "a": ACAO_ENVIO, "e": p["eid"], "n": p["nome"],
                     "x": json.dumps({"telefone": d}, ensure_ascii=False)})
                await db.commit()
            print(f"  enviado: {p['nome']}")
        else:
            falhas.append((p["nome"], str(res)[:120]))
            print(f"  FALHOU: {p['nome']} — {str(res)[:120]}")
        await asyncio.sleep(PAUSA_ENTRE_MENSAGENS)
        if (i + 1) % TAMANHO_DO_LOTE == 0 and i + 1 < len(fila):
            print(f"  … pausa de {PAUSA_ENTRE_LOTES:.0f}s (protege o número da empresa)")
            await asyncio.sleep(PAUSA_ENTRE_LOTES)

    print(f"\nTOTAL enviados: {enviados} · falhas: {len(falhas)} · "
          f"fora do alcance: {len(sem_whatsapp) + len(malformado)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
