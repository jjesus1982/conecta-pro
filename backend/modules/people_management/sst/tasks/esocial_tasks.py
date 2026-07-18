"""Tasks Celery — transmissão SST → eSocial + pull de recibos.

Fecha o ciclo SST↔eSocial (Missão B):
- transmit_cat_to_esocial (S-2210)          ← POST /sst/cat
- transmit_aso_to_esocial (S-2220)          ← PUT /sst/aso/{id}/resultado (status=realizado)
- transmit_afastamento_to_esocial (S-2230)  ← POST /sst/afastamentos e PUT retorno
  (o retorno RE-TRANSMITE o S-2230, que passa a incluir <fimAfastamento> —
   comportamento do gerador da Onda A quando status=encerrado)
- esocial_pull_recibos (beat 2h)            → consulta protocolos pendentes
  (esocial_status='transmitida' sem recibo) no WsConsultarLoteEventos, casa
  recibo → atualiza status (CAT: status='registrada_inss' + numero_recibo_esocial).

HONESTIDADE: protocolo/recibo SEMPRE reais (retornados pelo governo). Falha de
transmissão → esocial_status='erro' (retry exponencial 3x para falha de infra;
dado obrigatório faltante NÃO é retried — precisa de correção humana).
Fila: gov.esocial (fila existente do módulo gov). Ambiente: ESOCIAL_AMBIENTE
(default producaorestrita — a virada para produção é do orquestrador).
"""

import asyncio
import logging
from typing import Any
from uuid import uuid4

from celery import shared_task
from sqlalchemy import text

from core.database import async_session_factory, engine

logger = logging.getLogger(__name__)

# backoff exponencial: 1min, 2min, 4min (3 retries)
_RETRY_BASE_SECONDS = 60


def run_async(coro):
    """Executa coroutine em task Celery (padrão do módulo gov — sync_tasks).

    Dispõe o pool async NO MESMO loop antes de fechá-lo — senão as conexões
    asyncpg ficam órfãs e acumulam como idle no Postgres.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.run_until_complete(engine.dispose())
        finally:
            loop.close()


# Config por tipo: tabela de origem, coluna-chave, coluna de recibo
# S-2240 usa a tabela de rastreio própria (sst_s2240_transmissoes — Missão M2):
# o evento não tem coluna de recibo na origem (employees) e sem rastreio a
# Central de Transmissão não teria como impedir dupla transmissão.
_FONTES = {
    "S-2210": {"tabela": "gp_cats", "chave": "cat_id", "col_recibo": "numero_recibo_esocial"},
    "S-2220": {"tabela": "gp_asos", "chave": "aso_id", "col_recibo": "recibo_s2220"},
    "S-2230": {"tabela": "sst_afastamentos", "chave": "id::text", "col_recibo": "recibo_s2230"},
    "S-2240": {
        "tabela": "sst_s2240_transmissoes",
        "chave": "employee_id::text",
        "col_recibo": "recibo_s2240",
    },
}


async def _transmitir(tipo: str, ref_id: str) -> dict[str, Any]:
    """Chama o contrato da Onda A e persiste o protocolo REAL para o pull."""
    from modules.people_management.hr.services.esocial_service import transmitir_evento_sst

    fonte = _FONTES[tipo]
    async with async_session_factory() as db:
        if tipo == "S-2240":
            # garante a linha de rastreio (o transmitir_evento_sst não persiste
            # status para S-2240 — a origem employees não tem colunas eSocial)
            await db.execute(
                text(
                    "INSERT INTO sst_s2240_transmissoes (employee_id, esocial_status) "
                    "VALUES (CAST(:r AS uuid), 'enfileirada') "
                    "ON CONFLICT (employee_id) DO NOTHING"
                ),
                {"r": str(ref_id)},
            )
            await db.commit()
        try:
            resultado = await transmitir_evento_sst(db, tipo, ref_id)
        except ValueError as exc:
            # Dado obrigatório ausente / registro inexistente: falha de DADO —
            # não é retried; marca erro honesto para aparecer na tela.
            await db.execute(
                text(
                    f"UPDATE {fonte['tabela']} SET esocial_status = 'erro' "
                    f"WHERE {fonte['chave']} = :r"
                ),
                {"r": str(ref_id)},
            )
            await db.commit()
            logger.error("%s %s: dado obrigatório ausente — %s", tipo, ref_id, exc)
            return {"status": "erro_dado", "erros": [str(exc)], "protocolo": None, "recibo": None}
        except Exception:
            # Falha de INFRA (SSL/rede/timeout): transmitir_evento_sst já gravou
            # esocial_status='erro' quando aplicável; commit + propaga p/ retry.
            await db.commit()
            raise

        # Persiste o protocolo REAL; se re-transmissão (retorno de afastamento),
        # zera o recibo antigo para o pull casar o recibo NOVO deste lote.
        if resultado.get("protocolo"):
            sets = "esocial_protocolo = :p"
            params: dict[str, Any] = {"p": resultado["protocolo"], "r": str(ref_id)}
            if resultado.get("recibo"):
                sets += f", {fonte['col_recibo']} = :rec"
                params["rec"] = resultado["recibo"]
            else:
                sets += f", {fonte['col_recibo']} = NULL"
            await db.execute(
                text(f"UPDATE {fonte['tabela']} SET {sets} WHERE {fonte['chave']} = :r"), params
            )
            await db.commit()
        if tipo == "S-2240":
            # espelha o status honesto no rastreio (aceita|transmitida|rejeitada) —
            # para os demais tipos o próprio transmitir_evento_sst grava na origem
            await db.execute(
                text(
                    "UPDATE sst_s2240_transmissoes SET esocial_status = :st, "
                    "transmitida_em = CASE WHEN :st IN ('transmitida', 'aceita') "
                    "  THEN COALESCE(transmitida_em, now()) ELSE transmitida_em END, "
                    "atualizado_em = now() WHERE employee_id::text = :r"
                ),
                {"st": resultado.get("status") or "erro", "r": str(ref_id)},
            )
            await db.commit()
        return resultado


def _task_transmit(self, tipo: str, ref_id: str) -> dict[str, Any]:
    try:
        resultado = run_async(_transmitir(tipo, ref_id))
        logger.info("%s %s: %s", tipo, ref_id, resultado.get("status"))
        return resultado
    except Exception as exc:
        countdown = _RETRY_BASE_SECONDS * (2**self.request.retries)
        logger.warning(
            "%s %s: falha de infra (%s) — retry %d/3 em %ds",
            tipo, ref_id, exc, self.request.retries + 1, countdown,
        )
        raise self.retry(exc=exc, countdown=countdown, max_retries=3)


@shared_task(bind=True, name="sst.transmit_cat_to_esocial", queue="gov.esocial", max_retries=3)
def transmit_cat_to_esocial(self, cat_id: str):
    """Transmite CAT (S-2210) ao eSocial. Prazo legal: 1 dia útil após o acidente."""
    return _task_transmit(self, "S-2210", cat_id)


@shared_task(bind=True, name="sst.transmit_aso_to_esocial", queue="gov.esocial", max_retries=3)
def transmit_aso_to_esocial(self, aso_id: str):
    """Transmite ASO realizado (S-2220) ao eSocial."""
    return _task_transmit(self, "S-2220", aso_id)


@shared_task(bind=True, name="sst.transmit_afastamento_to_esocial", queue="gov.esocial", max_retries=3)
def transmit_afastamento_to_esocial(self, afastamento_id: str):
    """Transmite afastamento (S-2230) ao eSocial (início e, no retorno, o término)."""
    return _task_transmit(self, "S-2230", afastamento_id)


@shared_task(bind=True, name="sst.transmit_s2240_to_esocial", queue="gov.esocial", max_retries=3)
def transmit_s2240_to_esocial(self, employee_id: str):
    """Transmite S-2240 (Condições Ambientais) ao eSocial — ref = employees.id.

    Disparada SOMENTE pela Central de Transmissão (lote assistido, gate humano):
    a Central já barra ASG (gate MB) e itens já existentes no governo (espelho).
    Rastreio de protocolo/recibo: sst_s2240_transmissoes (pull 2h casa o recibo).
    """
    return _task_transmit(self, "S-2240", employee_id)


# ============================================================================
# PULL DE RECIBOS (beat esocial-pull-recibos, a cada 2h)
# ============================================================================


async def _consultar_protocolo(transmitter, tipo: str, cnpj: str, protocolo: str):
    """Consulta um protocolo no WsConsultarLoteEventos reusando o transmitter.

    O ESocialTransmitter guarda eventos em memória; para consultar um protocolo
    persistido no banco, registra-se um evento sintético com o protocolo REAL e
    usa-se o check_status público (mesmo SOAP de consulta do envio).
    """
    from modules.government_integrations.core.esocial_transmitter import (
        ESocialEvent,
        EventType,
        TransmissionStatus,
    )

    evento = ESocialEvent(
        id=uuid4(),
        event_type=EventType(tipo),
        status=TransmissionStatus.TRANSMITTED,
        employer_cnpj=cnpj,
        protocol=protocolo,
    )
    transmitter._events[evento.id] = evento  # noqa: SLF001 — registro p/ consulta
    return await transmitter.check_status(evento.id)


async def _pull_recibos() -> dict[str, Any]:
    import os

    from modules.government_integrations.core.esocial_transmitter import (
        ESocialTransmitter,
        TransmissionStatus,
        resolve_environment,
    )
    from modules.people_management.hr.services.esocial_service import _carregar_empregador

    resumo: dict[str, Any] = {"consultados": 0, "recibos_casados": 0, "rejeitados": 0, "pendentes": 0}

    async with async_session_factory() as db:
        empregador = await _carregar_empregador(db)
        cnpj = empregador["cnpj"]

        pendencias: list[dict[str, Any]] = []
        for tipo, fonte in _FONTES.items():
            rows = (
                await db.execute(
                    text(
                        f"SELECT {fonte['chave'].split('::')[0]} AS ref, esocial_protocolo "
                        f"FROM {fonte['tabela']} "
                        f"WHERE esocial_status = 'transmitida' "
                        f"AND esocial_protocolo IS NOT NULL "
                        f"AND {fonte['col_recibo']} IS NULL"
                    )
                )
            ).mappings().all()
            pendencias += [
                {"tipo": tipo, "ref": str(r["ref"]), "protocolo": r["esocial_protocolo"]} for r in rows
            ]

        if not pendencias:
            return resumo

        transmitter = ESocialTransmitter(
            environment=resolve_environment(),  # default SEGURO: producaorestrita
            certificate_path=os.environ.get(
                "CERTIFICATE_PATH", "/opt/conecta-pro/credentials/certificates/certificado.pfx"
            ),
            certificate_password=os.environ.get("CERTIFICATE_PASSWORD", ""),
        )
        await transmitter.load_certificate()

        for p in pendencias:
            fonte = _FONTES[p["tipo"]]
            resumo["consultados"] += 1
            try:
                evento = await _consultar_protocolo(transmitter, p["tipo"], cnpj, p["protocolo"])
            except Exception as exc:  # noqa: BLE001 — segue o lote; próximo beat reconsulta
                logger.warning("Pull %s %s: consulta falhou: %s", p["tipo"], p["ref"], exc)
                resumo["pendentes"] += 1
                continue

            if evento.receipt_number:
                sets = f"{fonte['col_recibo']} = :rec, esocial_status = 'aceita'"
                if p["tipo"] == "S-2210":
                    # CAT registrada no INSS: ciclo aberta→transmitida→registrada_inss
                    sets += ", status = 'registrada_inss'"
                await db.execute(
                    text(f"UPDATE {fonte['tabela']} SET {sets} WHERE {fonte['chave']} = :r"),
                    {"rec": evento.receipt_number, "r": p["ref"]},
                )
                await db.commit()
                resumo["recibos_casados"] += 1
                logger.info("Pull %s %s: recibo %s casado", p["tipo"], p["ref"], evento.receipt_number)
            elif evento.status == TransmissionStatus.REJECTED:
                await db.execute(
                    text(
                        f"UPDATE {fonte['tabela']} SET esocial_status = 'rejeitada' "
                        f"WHERE {fonte['chave']} = :r"
                    ),
                    {"r": p["ref"]},
                )
                await db.commit()
                resumo["rejeitados"] += 1
                logger.warning("Pull %s %s: REJEITADO pelo governo: %s", p["tipo"], p["ref"], evento.errors)
            else:
                resumo["pendentes"] += 1  # ainda em processamento no governo

    return resumo


@shared_task(bind=True, name="sst.esocial_pull_recibos", queue="gov.esocial", max_retries=1)
def esocial_pull_recibos(self):
    """Beat 2h: casa recibos REAIS dos protocolos SST pendentes (S-2210/S-2220/S-2230)."""
    try:
        resumo = run_async(_pull_recibos())
        logger.info("esocial_pull_recibos: %s", resumo)
        return resumo
    except Exception as exc:
        logger.error("esocial_pull_recibos: falha geral: %s", exc)
        return {"erro": str(exc)}
