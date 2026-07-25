"""Fase 5.2a.3 — Camada de Garantia: AUDITORIA append-only de ações de agente.

REUSA a tabela `audit_logs` (Sprint 33, `modules/audit/models/audit_log.py`) —
NÃO cria tabela nova. Faz INSERT direto via SQL (não passa por
`AuditService.create_audit_log`) por dois motivos:

1. As colunas `action`/`category` no BANCO são `VARCHAR` livre (confirmado na
   migration `sprint33_create_audit_tables.py`) — só o model Python as amarra
   a `StrEnum`s fixos (`AuditAction`/`AuditCategory`) que NÃO têm um valor
   "agent_response"/"agent". Ir pelo `AuditService` exigiria ou reaproveitar um
   valor de enum que não descreve bem o evento (ex. `API_CALL`/`INTEGRATION`),
   ou alterar o enum compartilhado — fora do escopo desta task.
2. Mantém este pacote (`garantia/`) standalone e sem import-time dependency no
   módulo `audit` inteiro (schemas/repository/models) — só `sqlalchemy`.

Append-only: só INSERT, nunca UPDATE/DELETE em produção (a limpeza feita nos
testes é exclusivamente da linha marcada "TESTE 5.2a3").
"""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def registrar_acao_agente(
    db: AsyncSession,
    *,
    origem: str,
    pergunta: str,
    resposta: str,
    modelo: str,
    tier: str,
    provider: str,
    tokens: int | None = None,
    latencia_ms: int | None = None,
    groundedness_ok: bool | None = None,
    trace_id: str | None = None,
) -> str:
    """Grava 1 linha append-only em `audit_logs` para uma resposta de agente
    (Hermes/consultor). Retorna o `event_id` gerado.

    `pergunta`/`resposta` são truncadas (2000/4000 chars) — o objetivo é
    auditoria/trilha, não um espelho 1:1 da conversa completa.
    """
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    event_id = f"EVT-AGT-{ts}-{secrets.token_hex(4).upper()}"
    details = {
        "origem": origem,
        "pergunta": (pergunta or "")[:2000],
        "resposta": (resposta or "")[:4000],
        "modelo": modelo,
        "tier": tier,
        "provider": provider,
        "tokens": tokens,
        "latencia_ms": latencia_ms,
        "groundedness_ok": groundedness_ok,
        "trace_id": trace_id,
    }

    await db.execute(
        text(
            """
            INSERT INTO audit_logs (
                id, event_id, action, category, severity, result, description,
                details, entity_type, is_sensitive, is_pii, requires_review,
                archived, created_at
            ) VALUES (
                :id, :event_id, 'agent_response', 'agent', 'info', 'success',
                :description, CAST(:details AS jsonb), 'agent_action',
                false, false, false, false, :created_at
            )
            """
        ),
        {
            "id": str(uuid4()),
            "event_id": event_id,
            "description": f"Agente ({origem or 'hermes'}) respondeu via {provider}/{modelo}",
            "details": json.dumps(details, ensure_ascii=False, default=str),
            "created_at": datetime.utcnow(),
        },
    )
    await db.commit()
    logger.info(
        "agent_audit: registrado %s (origem=%s modelo=%s tier=%s groundedness_ok=%s)",
        event_id, origem, modelo, tier, groundedness_ok,
    )
    return event_id


async def registrar_proposta_acao(
    db: AsyncSession,
    *,
    origem: str,
    tool: str,
    args: dict,
    dominio: str,
    gate: str,
    entity_type: str,
    entity_id: str,
    aprovadores: list[str],
    proposto_por: str,
    trace_id: str | None = None,
) -> str:
    """Append-only em `audit_logs`: 1 linha por PROPOSTA de ação (propor→aprovar).
    Registra tool/args/entity/gate/aprovadores + quem propôs (3 papéis). NUNCA
    representa execução — só a criação do PENDENTE.

    ATOMICIDADE: NÃO faz commit. Só emite o INSERT do audit na transação corrente;
    quem commita é a primitiva `propor` (único commit no fim, após inserir+audit+
    sino). Assim, se qualquer passo falhar, pendente+audit+notificação revertem
    juntos (rollback) — nada fica durável sem entrega. Único caller: `acoes.base`."""
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    event_id = f"EVT-PROP-{ts}-{secrets.token_hex(4).upper()}"
    details = {
        "origem": origem, "tool": tool, "args": args, "dominio": dominio,
        "gate": gate, "entity_type": entity_type, "entity_id": entity_id,
        "aprovadores": aprovadores, "proposto_por": proposto_por,
        "trace_id": trace_id, "fase": "5.4", "acao": "propor",
    }
    await db.execute(
        text(
            """
            INSERT INTO audit_logs (
                id, event_id, action, category, severity, result, description,
                details, entity_type, is_sensitive, is_pii, requires_review,
                archived, created_at
            ) VALUES (
                :id, :event_id, 'agent_action', 'agent', 'info', 'success',
                :description, CAST(:details AS jsonb), :entity_type,
                false, false, true, false, :created_at
            )
            """
        ),
        {
            "id": str(uuid4()),
            "event_id": event_id,
            "description": f"Agente propôs {tool} ({dominio}, gate {gate}) — PENDENTE de aprovação",
            "details": json.dumps(details, ensure_ascii=False, default=str),
            "entity_type": entity_type,
            "created_at": datetime.utcnow(),
        },
    )
    # SEM commit: a primitiva `propor` commita tudo de uma vez no fim (atomicidade).
    logger.info("agent_audit: proposta %s tool=%s dominio=%s gate=%s entity=%s",
                event_id, tool, dominio, gate, entity_id)
    return event_id


# ─────────────────────────────────────────────────────────────────────────────
# TESTE (padrão 5.1: sem pytest, `python agent_audit.py`, asyncio + asserts).
# Precisa de uma DATABASE_URL real (staging, NUNCA produção :8080 in-process).
# Grava 1 linha marcada "TESTE 5.2a3" e a REMOVE no final.
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import asyncio
    import os

    from sqlalchemy.ext.asyncio import create_async_engine

    async def main() -> None:
        db_url = os.environ["DATABASE_URL_TESTE"]  # obrigatório, sem default silencioso
        engine = create_async_engine(db_url)
        Session = __import__(
            "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
        ).async_sessionmaker(engine, expire_on_commit=False)

        async with Session() as db:
            antes = (
                await db.execute(text("SELECT count(*) FROM audit_logs"))
            ).scalar_one()

            event_id = await registrar_acao_agente(
                db,
                origem="executivo",
                pergunta="TESTE 5.2a3 — qual o saldo hoje?",
                resposta="TESTE 5.2a3 — o saldo é R$ 9.125,56.",
                modelo="gpt-5",
                tier="pesada",
                provider="hermes",
                tokens=321,
                latencia_ms=1234,
                groundedness_ok=True,
                trace_id="trace-teste-5.2a3",
            )
            assert event_id.startswith("EVT-AGT-"), f"event_id inesperado: {event_id}"

            depois = (
                await db.execute(text("SELECT count(*) FROM audit_logs"))
            ).scalar_one()
            assert depois == antes + 1, f"esperado +1 linha, veio antes={antes} depois={depois}"

            row = (
                await db.execute(
                    text(
                        "SELECT action, category, details FROM audit_logs WHERE event_id = :e"
                    ),
                    {"e": event_id},
                )
            ).mappings().first()
            assert row is not None, "linha não encontrada após INSERT"
            assert row["action"] == "agent_response", row
            assert row["category"] == "agent", row
            d = row["details"]
            d = json.loads(d) if isinstance(d, str) else d
            assert d["origem"] == "executivo", d
            assert d["modelo"] == "gpt-5", d
            assert d["tier"] == "pesada", d
            assert d["provider"] == "hermes", d
            assert d["tokens"] == 321, d
            assert d["latencia_ms"] == 1234, d
            assert d["groundedness_ok"] is True, d
            print("TESTE 1 (linha gravada com os campos certos) PASS:", event_id)

            # limpeza — só remove a própria linha marcada "TESTE 5.2a3"
            await db.execute(
                text("DELETE FROM audit_logs WHERE event_id = :e"), {"e": event_id}
            )
            await db.commit()
            restante = (
                await db.execute(
                    text("SELECT count(*) FROM audit_logs WHERE event_id = :e"), {"e": event_id}
                )
            ).scalar_one()
            assert restante == 0, "linha de teste não foi removida"
            print("TESTE 2 (limpeza da linha de teste) PASS")

        await engine.dispose()
        print("\nTODOS OS TESTES DE agent_audit.py PASSARAM")

    asyncio.run(main())
