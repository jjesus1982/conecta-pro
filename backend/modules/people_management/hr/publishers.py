"""
Publishers do módulo DP (Departamento Pessoal) para o ConectaEventBus.

Publica eventos de admissão, demissão, férias, folha de pagamento e atestados.
"""

from __future__ import annotations

import logging
from typing import Any

from infrastructure.event_bus import ConectaEvent, EventTypes, event_bus

logger = logging.getLogger(__name__)


async def publish_funcionario_admitido(
    funcionario_id: str,
    funcionario_nome: str,
    cargo: str = "",
    data_admissao: str | None = None,
    cliente_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Publica evento quando um funcionário é admitido (processo de admissão concluído)."""
    try:
        await event_bus.publish(
            ConectaEvent(
                event_type=EventTypes.DP_FUNCIONARIO_ADMITIDO,
                payload={
                    "funcionario_id": funcionario_id,
                    "funcionario_nome": funcionario_nome,
                    "cargo": cargo,
                    "data_admissao": data_admissao,
                    **(extra or {}),
                },
                source_module="dp",
                funcionario_id=funcionario_id,
                cliente_id=cliente_id,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("publish_funcionario_admitido falhou: %s", exc)


async def publish_funcionario_demitido(
    funcionario_id: str,
    funcionario_nome: str,
    motivo: str = "",
    data_desligamento: str | None = None,
    cliente_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Publica evento quando um funcionário é desligado (rescisão concluída)."""
    try:
        await event_bus.publish(
            ConectaEvent(
                event_type=EventTypes.DP_FUNCIONARIO_DEMITIDO,
                payload={
                    "funcionario_id": funcionario_id,
                    "funcionario_nome": funcionario_nome,
                    "motivo": motivo,
                    "data_desligamento": data_desligamento,
                    **(extra or {}),
                },
                source_module="dp",
                funcionario_id=funcionario_id,
                cliente_id=cliente_id,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("publish_funcionario_demitido falhou: %s", exc)


async def publish_ferias_aprovadas(
    funcionario_id: str,
    funcionario_nome: str = "",
    inicio: str | None = None,
    fim: str | None = None,
    aprovado_por: str | None = None,
    cliente_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Publica evento quando férias são aprovadas para um funcionário."""
    try:
        await event_bus.publish(
            ConectaEvent(
                event_type=EventTypes.DP_FERIAS_APROVADAS,
                payload={
                    "funcionario_id": funcionario_id,
                    "funcionario_nome": funcionario_nome,
                    "inicio": inicio,
                    "fim": fim,
                    "aprovado_por": aprovado_por,
                    **(extra or {}),
                },
                source_module="dp",
                funcionario_id=funcionario_id,
                cliente_id=cliente_id,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("publish_ferias_aprovadas falhou: %s", exc)


async def publish_folha_fechada(
    competencia: str,
    total_funcionarios: int = 0,
    total_bruto: float = 0.0,
    extra: dict[str, Any] | None = None,
) -> None:
    """Publica evento quando a folha de pagamento mensal é fechada."""
    try:
        await event_bus.publish(
            ConectaEvent(
                event_type=EventTypes.DP_FOLHA_FECHADA,
                payload={
                    "competencia": competencia,
                    "total_funcionarios": total_funcionarios,
                    "total_bruto": total_bruto,
                    **(extra or {}),
                },
                source_module="dp",
                competencia=competencia,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("publish_folha_fechada falhou: %s", exc)


async def publish_beneficio_adicionado(
    funcionario_id: str,
    tipo_beneficio: str,
    benefit_id: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    """Publica evento quando um benefício é adicionado a um funcionário."""
    try:
        await event_bus.publish(
            ConectaEvent(
                event_type=EventTypes.DP_BENEFICIO_ADICIONADO,
                payload={
                    "funcionario_id": funcionario_id,
                    "tipo_beneficio": tipo_beneficio,
                    "benefit_id": benefit_id,
                    **(extra or {}),
                },
                source_module="dp",
                funcionario_id=funcionario_id,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("publish_beneficio_adicionado falhou: %s", exc)


async def publish_contrato_criado(
    funcionario_id: str,
    contract_id: str = "",
    tipo_contrato: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    """Publica evento quando um contrato de trabalho é criado."""
    try:
        await event_bus.publish(
            ConectaEvent(
                event_type=EventTypes.DP_CONTRATO_CRIADO,
                payload={
                    "funcionario_id": funcionario_id,
                    "contract_id": contract_id,
                    "tipo_contrato": tipo_contrato,
                    **(extra or {}),
                },
                source_module="dp",
                funcionario_id=funcionario_id,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("publish_contrato_criado falhou: %s", exc)


async def publish_holerite_gerado(
    funcionario_id: str,
    funcionario_nome: str = "",
    competencia: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    """Publica evento quando um holerite (contracheque) é gerado."""
    try:
        await event_bus.publish(
            ConectaEvent(
                event_type=EventTypes.DP_HOLERITE_GERADO,
                payload={
                    "funcionario_id": funcionario_id,
                    "funcionario_nome": funcionario_nome,
                    "competencia": competencia,
                    **(extra or {}),
                },
                source_module="dp",
                funcionario_id=funcionario_id,
                competencia=competencia,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("publish_holerite_gerado falhou: %s", exc)


async def publish_funcionario_atualizado(
    funcionario_id: str,
    funcionario_nome: str = "",
    campos_alterados: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Publica evento quando dados de um funcionário são atualizados."""
    try:
        await event_bus.publish(
            ConectaEvent(
                event_type=EventTypes.DP_FUNCIONARIO_TRANSFERIDO,
                payload={
                    "funcionario_id": funcionario_id,
                    "funcionario_nome": funcionario_nome,
                    "campos_alterados": campos_alterados or [],
                    **(extra or {}),
                },
                source_module="dp",
                funcionario_id=funcionario_id,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("publish_funcionario_atualizado falhou: %s", exc)


async def publish_ponto_registrado(
    employee_id: str,
    tipo: str = "clock_in",
    record_id: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    """DEPRECADO — publica `dp.ponto.registrado` a partir do caminho CLÁSSICO do HR.

    Decisão Jordan 2026-08-07: o canônico é `ponto.batida.registrada`
    (`ponto/publishers.py:publish_batida_registrada`), único que carrega punch_timestamp,
    cliente_id e geolocalização. Os dois gravam na MESMA tabela (`gp_clock_punches`) e
    anunciam o MESMO fato — é duplicação de subsistema, não de evento.

    Continua publicando para não quebrar os 4 pontos de chamada em `hr/controllers`; morre
    junto com o caminho clássico. **Não registre subscriber neste evento nem no canônico
    enquanto os dois coexistirem** — a mesma batida contaria duas vezes.
    """
    try:
        await event_bus.publish(
            ConectaEvent(
                event_type=EventTypes.DP_PONTO_REGISTRADO,
                payload={
                    "employee_id": employee_id,
                    "tipo": tipo,
                    "record_id": record_id,
                    **(extra or {}),
                },
                source_module="dp",
                funcionario_id=employee_id,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("publish_ponto_registrado falhou: %s", exc)


async def publish_esocial_gerado(
    cpf: str,
    matricula: str,
    evento_tipo: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Publica evento quando um XML eSocial é gerado."""
    try:
        await event_bus.publish(
            ConectaEvent(
                event_type=EventTypes.DP_ESOCIAL_GERADO,
                payload={
                    "cpf": cpf,
                    "matricula": matricula,
                    "evento_tipo": evento_tipo,
                    **(extra or {}),
                },
                source_module="dp",
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("publish_esocial_gerado falhou: %s", exc)


async def publish_atestado_registrado(
    funcionario_id: str,
    funcionario_nome: str = "",
    tipo: str = "medical_leave",
    dias: int = 0,
    cid: str | None = None,
    cliente_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Publica evento quando um atestado/afastamento é registrado."""
    try:
        await event_bus.publish(
            ConectaEvent(
                event_type=EventTypes.DP_ATESTADO_REGISTRADO,
                payload={
                    "funcionario_id": funcionario_id,
                    "funcionario_nome": funcionario_nome,
                    "tipo": tipo,
                    "dias": dias,
                    "cid": cid,
                    **(extra or {}),
                },
                source_module="dp",
                funcionario_id=funcionario_id,
                cliente_id=cliente_id,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("publish_atestado_registrado falhou: %s", exc)
