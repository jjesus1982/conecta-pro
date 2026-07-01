"""
GEDEON — GED Orchestrator — Gestor Eletrônico de
Documentos com Inteligência Operacional e Neural.

Orquestrador invisível da Gestão de Pessoas.
Escuta o ConectaEventBus e age em background.
Nunca interrompe o usuário — exceto quando precisa
de uma decisão que só um humano pode tomar.

Arquitetura:
  ConectaEventBus → GEDEON → GedeonContext (Redis)
                           → Notificações (quando necessário)
"""

import logging
from datetime import datetime
from typing import Optional

from infrastructure.event_bus import (
    ConectaEvent,
    EventTypes,
    event_bus,
)
from modules.gedeon.agents.argos import argos  # noqa: F401
from modules.gedeon.agents.atlas import atlas  # noqa: F401
from modules.gedeon.agents.hermes import hermes  # noqa: F401
from modules.gedeon.agents.kronos import kronos  # noqa: F401
from modules.gedeon.agents.themis import themis  # noqa: F401
from modules.gedeon.context.gedeon_context import gedeon_context

logger = logging.getLogger(__name__)


class Gedeon:
    """
    O Orquestrador. Singleton. Invisível.
    Registra subscribers para todos os eventos relevantes
    e coordena os sub-agentes em background.
    """

    _instance: Optional["Gedeon"] = None

    @classmethod
    def get_instance(cls) -> "Gedeon":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def registrar_subscribers(self) -> None:
        """
        Registrar todos os handlers no ConectaEventBus.
        Chamado uma vez no startup da aplicação.
        """
        # ── DP ────────────────────────────────────────
        event_bus.subscribe(EventTypes.DP_FUNCIONARIO_ADMITIDO, self._on_funcionario_admitido)
        event_bus.subscribe(EventTypes.DP_FUNCIONARIO_DEMITIDO, self._on_funcionario_demitido)
        event_bus.subscribe(EventTypes.DP_ATESTADO_REGISTRADO, self._on_atestado_registrado)
        event_bus.subscribe(EventTypes.DP_FERIAS_APROVADAS, self._on_ferias_aprovadas)
        event_bus.subscribe(EventTypes.DP_FOLHA_FECHADA, self._on_folha_fechada)
        event_bus.subscribe(EventTypes.DP_HOLERITE_GERADO, self._on_holerite_gerado)

        # ── OPERACIONAL ───────────────────────────────
        event_bus.subscribe(EventTypes.OPS_OCORRENCIA_REGISTRADA, self._on_ocorrencia_registrada)
        event_bus.subscribe(EventTypes.OPS_ESCALA_PUBLICADA, self._on_escala_publicada)
        event_bus.subscribe(EventTypes.OPS_CAT_REGISTRADA, self._on_cat_registrada)

        # ── FISCAL ────────────────────────────────────
        event_bus.subscribe(EventTypes.FISCAL_CERTIDAO_VENCIDA, self._on_certidao_vencida)
        event_bus.subscribe(EventTypes.FISCAL_CERTIDAO_RENOVADA, self._on_certidao_renovada)
        event_bus.subscribe(EventTypes.FISCAL_NFS_EMITIDA, self._on_nfs_emitida)

        # ── FINANCEIRO ────────────────────────────────
        event_bus.subscribe(EventTypes.FIN_NOTA_EMITIDA, self._on_nota_emitida)
        event_bus.subscribe(EventTypes.FIN_CONTRATO_INADIMPLENTE, self._on_contrato_inadimplente)

        # ── SAÚDE ─────────────────────────────────────
        event_bus.subscribe(EventTypes.SAUDE_ASO_EMITIDO, self._on_aso_emitido)
        event_bus.subscribe(EventTypes.SAUDE_ASO_VENCENDO, self._on_aso_vencendo)
        event_bus.subscribe(EventTypes.SAUDE_EPI_ENTREGUE, self._on_epi_entregue)
        event_bus.subscribe(EventTypes.SAUDE_TREINAMENTO_CONCLUIDO, self._on_treinamento_concluido)

        # ── PONTO ─────────────────────────────────────
        event_bus.subscribe(EventTypes.PONTO_ESPELHO_FECHADO, self._on_espelho_fechado)
        event_bus.subscribe(EventTypes.PONTO_FALTA_CONFIRMADA, self._on_falta_confirmada)

        # ── CRM ───────────────────────────────────────
        event_bus.subscribe("crm.cliente.ativo", self._on_cliente_ativo)
        event_bus.subscribe("crm.contrato.assinado", self._on_contrato_assinado)

        # ── SOPHIA v2.0 — indexação automática cross-módulo ───────────────────
        try:
            from modules.gedeon.subscribers.sophia_subscriber import registrar_subscriber

            registrar_subscriber(event_bus)
            logger.info("SOPHIA v2.0: subscriber registrado no Event Bus")
        except Exception as _sophia_err:
            logger.warning("SOPHIA v2.0: subscriber não registrado: %s", _sophia_err)

        logger.info("GEDEON: subscribers registrados — operando em modo invisível")

    # ── HANDLERS DP ───────────────────────────────────

    async def _on_funcionario_admitido(self, event: ConectaEvent) -> None:
        """
        Admissão → preparar kit de integração no GED.
        Notificar Saúde para agendar ASO admissional.
        """
        p = event.payload
        competencia = datetime.utcnow().strftime("%Y-%m")
        cliente_id = event.cliente_id

        logger.info("GEDEON: admissão detectada — %s", p.get("funcionario_nome") or p.get("name", ""))

        if cliente_id:
            await gedeon_context.append_evento(
                cliente_id,
                competencia,
                "movimentacao_pessoal",
                {
                    "event_id": event.event_id,
                    "tipo": "admissao",
                    "funcionario": p.get("funcionario_nome") or p.get("name", ""),
                    "cargo": p.get("cargo", ""),
                    "data": p.get("data_admissao", ""),
                    "requer_doc": True,
                    "docs_necessarios": [
                        "Contrato de trabalho",
                        "Exame admissional (ASO)",
                        "Ficha de EPI",
                        "Declarações legais",
                    ],
                },
            )

        # Publicar evento de kit necessário
        await event_bus.publish(
            ConectaEvent(
                event_type=EventTypes.GED_KIT_INICIADO,
                payload={
                    "motivo": "admissao",
                    "funcionario": p.get("funcionario_nome") or p.get("name", ""),
                    "cargo": p.get("cargo", ""),
                },
                source_module="gedeon",
                cliente_id=cliente_id,
                funcionario_id=event.funcionario_id,
                competencia=competencia,
            )
        )

    async def _on_funcionario_demitido(self, event: ConectaEvent) -> None:
        p = event.payload
        competencia = datetime.utcnow().strftime("%Y-%m")
        if event.cliente_id:
            await gedeon_context.append_evento(
                event.cliente_id,
                competencia,
                "movimentacao_pessoal",
                {
                    "event_id": event.event_id,
                    "tipo": "demissao",
                    "funcionario": p.get("funcionario_nome") or p.get("name", ""),
                    "tipo_demissao": p.get("motivo") or p.get("tipo", ""),
                    "data": p.get("data_desligamento", ""),
                    "requer_doc": True,
                    "docs_necessarios": [
                        "TRCT",
                        "Homologação",
                        "Seguro-desemprego",
                        "Exame demissional",
                    ],
                },
            )
        logger.info("GEDEON: demissão processada — %s", p.get("funcionario_nome") or p.get("name", ""))

    async def _on_atestado_registrado(self, event: ConectaEvent) -> None:
        p = event.payload
        competencia = datetime.utcnow().strftime("%Y-%m")
        if event.cliente_id:
            await gedeon_context.append_evento(
                event.cliente_id,
                competencia,
                "movimentacao_pessoal",
                {
                    "event_id": event.event_id,
                    "tipo": "atestado",
                    "funcionario": p.get("nome", ""),
                    "data_inicio": p.get("data_inicio", ""),
                    "data_fim": p.get("data_fim", ""),
                    "dias": p.get("dias", 0),
                    "requer_doc": True,
                    "doc_pendente": "Digitalizar atestado",
                },
            )

    async def _on_ferias_aprovadas(self, event: ConectaEvent) -> None:
        p = event.payload
        _ini = p.get("inicio") or p.get("start_date", "")
        competencia = _ini[:7] if _ini else datetime.utcnow().strftime("%Y-%m")
        if event.cliente_id:
            await gedeon_context.append_evento(
                event.cliente_id,
                competencia,
                "movimentacao_pessoal",
                {
                    "event_id": event.event_id,
                    "tipo": "ferias",
                    "funcionario": p.get("funcionario_nome") or p.get("nome", ""),
                    "inicio": p.get("inicio") or p.get("start_date", ""),
                    "fim": p.get("fim") or p.get("end_date", ""),
                    "requer_doc": True,
                },
            )

    async def _on_folha_fechada(self, event: ConectaEvent) -> None:
        p = event.payload
        competencia = p.get("competencia", "")
        if event.cliente_id and competencia:
            ctx = await gedeon_context.get(event.cliente_id, competencia)
            docs = ctx.get("documentos_gerados", {})
            docs["folha"] = True
            docs["total_funcionarios"] = p.get("total_funcionarios", 0)
            await gedeon_context.update(event.cliente_id, competencia, "documentos_gerados", docs)
        logger.info("GEDEON: folha fechada competência=%s", competencia)

    async def _on_holerite_gerado(self, event: ConectaEvent) -> None:
        p = event.payload
        competencia = p.get("competencia", "")
        if event.cliente_id and competencia:
            ctx = await gedeon_context.get(event.cliente_id, competencia)
            docs = ctx.get("documentos_gerados", {})
            docs["holerites"] = docs.get("holerites", 0) + 1
            await gedeon_context.update(event.cliente_id, competencia, "documentos_gerados", docs)

    # ── HANDLERS OPERACIONAL ──────────────────────────

    async def _on_ocorrencia_registrada(self, event: ConectaEvent) -> None:
        p = event.payload
        competencia = p.get("data", "")[:7] if p.get("data") else datetime.utcnow().strftime("%Y-%m")
        if event.cliente_id:
            await gedeon_context.append_evento(
                event.cliente_id,
                competencia,
                "ocorrencias",
                {
                    "event_id": event.event_id,
                    "tipo": p.get("tipo", ""),
                    "descricao": p.get("descricao", ""),
                    "tem_bo": p.get("tem_bo", False),
                    "data": p.get("data", ""),
                    "requer_doc": p.get("tem_bo", False),
                },
            )

    async def _on_escala_publicada(self, event: ConectaEvent) -> None:
        competencia = event.competencia or datetime.utcnow().strftime("%Y-%m")
        if event.cliente_id:
            await gedeon_context.update(event.cliente_id, competencia, "escala_publicada", True)
        logger.info("GEDEON: escala processada cliente=%s", event.cliente_id)

    async def _on_cat_registrada(self, event: ConectaEvent) -> None:
        p = event.payload
        competencia = p.get("data", "")[:7] if p.get("data") else datetime.utcnow().strftime("%Y-%m")
        if event.cliente_id:
            await gedeon_context.append_evento(
                event.cliente_id,
                competencia,
                "ocorrencias",
                {
                    "event_id": event.event_id,
                    "tipo": "CAT",
                    "numero_cat": p.get("numero_cat", ""),
                    "funcionario": p.get("funcionario_nome", ""),
                    "afastamento": p.get("afastamento", False),
                    "requer_doc": True,
                    "doc_pendente": "CAT + exame médico",
                },
            )

    # ── HANDLERS FISCAL ───────────────────────────────

    async def _on_certidao_vencida(self, event: ConectaEvent) -> None:
        p = event.payload
        competencia = datetime.utcnow().strftime("%Y-%m")
        # Atualizar todos os clientes com contexto ativo
        client_ids = await gedeon_context.get_keys_for_competencia(competencia)
        for cliente_id in client_ids:
            ctx = await gedeon_context.get(cliente_id, competencia)
            cert = ctx.get("certidoes", {"ok": 0, "alerta": 0, "critico": 0})
            cert["critico"] = cert.get("critico", 0) + 1
            await gedeon_context.update(cliente_id, competencia, "certidoes", cert)
        logger.warning("GEDEON: certidão vencida — %s", p.get("nome", ""))

    async def _on_certidao_renovada(self, event: ConectaEvent) -> None:
        p = event.payload
        competencia = datetime.utcnow().strftime("%Y-%m")
        client_ids = await gedeon_context.get_keys_for_competencia(competencia)
        for cliente_id in client_ids:
            ctx = await gedeon_context.get(cliente_id, competencia)
            cert = ctx.get("certidoes", {"ok": 0, "alerta": 0, "critico": 0})
            if cert.get("critico", 0) > 0:
                cert["critico"] -= 1
            cert["ok"] = cert.get("ok", 0) + 1
            await gedeon_context.update(cliente_id, competencia, "certidoes", cert)
        logger.info("GEDEON: certidão renovada — %s", p.get("nome", ""))

    async def _on_nfs_emitida(self, event: ConectaEvent) -> None:
        p = event.payload
        competencia = event.competencia or p.get("competencia", "")
        if event.cliente_id and competencia:
            ctx = await gedeon_context.get(event.cliente_id, competencia)
            docs = ctx.get("documentos_gerados", {})
            docs["nfs_e"] = {
                "numero": p.get("numero_nota", ""),
                "valor": p.get("valor", 0),
                "url": p.get("arquivo_url", ""),
            }
            await gedeon_context.update(event.cliente_id, competencia, "documentos_gerados", docs)

    # ── HANDLERS FINANCEIRO ───────────────────────────

    async def _on_nota_emitida(self, event: ConectaEvent) -> None:
        await self._on_nfs_emitida(event)

    async def _on_contrato_inadimplente(self, event: ConectaEvent) -> None:
        p = event.payload
        competencia = datetime.utcnow().strftime("%Y-%m")
        if event.cliente_id:
            await gedeon_context.append_evento(
                event.cliente_id,
                competencia,
                "pendencias",
                {
                    "event_id": event.event_id,
                    "tipo": "inadimplencia",
                    "valor": p.get("valor", 0),
                    "dias": p.get("dias_atraso", 0),
                    "mensagem": (f"Cliente inadimplente ({p.get('dias_atraso', 0)} dias) — montar kit mesmo assim?"),
                    "requer_decisao": True,
                },
            )
        logger.warning("GEDEON: inadimplência — %s", p.get("nome_cliente", ""))

    # ── HANDLERS SAÚDE ────────────────────────────────

    async def _on_aso_emitido(self, event: ConectaEvent) -> None:
        p = event.payload
        competencia = datetime.utcnow().strftime("%Y-%m")
        if event.cliente_id:
            ctx = await gedeon_context.get(event.cliente_id, competencia)
            docs = ctx.get("documentos_gerados", {})
            asos = docs.get("asos", [])
            asos.append(
                {
                    "funcionario": p.get("funcionario_nome", ""),
                    "tipo": p.get("tipo_aso", ""),
                    "resultado": p.get("resultado", ""),
                    "validade": p.get("data_validade", ""),
                }
            )
            docs["asos"] = asos
            await gedeon_context.update(event.cliente_id, competencia, "documentos_gerados", docs)

    async def _on_aso_vencendo(self, event: ConectaEvent) -> None:
        p = event.payload
        competencia = datetime.utcnow().strftime("%Y-%m")
        if event.cliente_id:
            await gedeon_context.append_evento(
                event.cliente_id,
                competencia,
                "pendencias",
                {
                    "event_id": event.event_id,
                    "tipo": "aso_vencendo",
                    "funcionario": p.get("funcionario_nome", ""),
                    "dias": p.get("dias_restantes", 0),
                    "mensagem": (f"ASO de {p.get('funcionario_nome', '')} vence em {p.get('dias_restantes', 0)} dias"),
                    "requer_decisao": False,
                },
            )

    async def _on_epi_entregue(self, event: ConectaEvent) -> None:
        p = event.payload
        competencia = datetime.utcnow().strftime("%Y-%m")
        if event.cliente_id:
            ctx = await gedeon_context.get(event.cliente_id, competencia)
            docs = ctx.get("documentos_gerados", {})
            epis = docs.get("epis", [])
            epis.append(
                {
                    "funcionario": p.get("funcionario_nome", ""),
                    "tipo": p.get("tipo_epi", ""),
                }
            )
            docs["epis"] = epis
            await gedeon_context.update(event.cliente_id, competencia, "documentos_gerados", docs)

    async def _on_treinamento_concluido(self, event: ConectaEvent) -> None:
        p = event.payload
        competencia = p.get("data", "")[:7] if p.get("data") else datetime.utcnow().strftime("%Y-%m")
        if event.cliente_id:
            ctx = await gedeon_context.get(event.cliente_id, competencia)
            docs = ctx.get("documentos_gerados", {})
            treinamentos = docs.get("treinamentos", [])
            treinamentos.append(
                {
                    "funcionario": p.get("funcionario_nome", ""),
                    "nr": p.get("nr", ""),
                    "certificado": p.get("certificado_url", ""),
                }
            )
            docs["treinamentos"] = treinamentos
            await gedeon_context.update(event.cliente_id, competencia, "documentos_gerados", docs)

    # ── HANDLERS PONTO ────────────────────────────────

    async def _on_espelho_fechado(self, event: ConectaEvent) -> None:
        p = event.payload
        competencia = p.get("competencia", "")
        if event.cliente_id and competencia:
            ctx = await gedeon_context.get(event.cliente_id, competencia)
            docs = ctx.get("documentos_gerados", {})
            espelhos = docs.get("espelhos_ponto", [])
            espelhos.append(
                {
                    "funcionario": p.get("funcionario_nome", ""),
                    "horas_extras": p.get("horas_extras", 0),
                    "faltas": p.get("faltas", 0),
                }
            )
            docs["espelhos_ponto"] = espelhos
            await gedeon_context.update(event.cliente_id, competencia, "documentos_gerados", docs)

    async def _on_falta_confirmada(self, event: ConectaEvent) -> None:
        p = event.payload
        competencia = p.get("data", "")[:7] if p.get("data") else datetime.utcnow().strftime("%Y-%m")
        if event.cliente_id and not p.get("justificada"):
            await gedeon_context.append_evento(
                event.cliente_id,
                competencia,
                "movimentacao_pessoal",
                {
                    "event_id": event.event_id,
                    "tipo": "falta_injustificada",
                    "funcionario": p.get("funcionario_nome", ""),
                    "data": p.get("data", ""),
                },
            )

    # ── HANDLERS CRM ──────────────────────────────────

    async def _on_cliente_ativo(self, event: ConectaEvent) -> None:
        """
        Novo cliente ativado no CRM →
        inicializar contexto GEDEON.
        """
        p = event.payload
        cliente_id = event.cliente_id or p.get("cliente_id", "")
        nome = p.get("nome", "")
        tipo = p.get("tipo_contrato", "maos_de_obra")

        logger.info("GEDEON: novo cliente → espelhando módulos: %s [%s]", nome, tipo)

        competencia = datetime.utcnow().strftime("%Y-%m")
        await gedeon_context.update(cliente_id, competencia, "tipo_kit", tipo)

        await event_bus.publish(
            ConectaEvent(
                event_type="gedeon.cliente.espelhar",
                payload={
                    "cliente_id": cliente_id,
                    "nome": nome,
                    "tipo_contrato": tipo,
                    "servicos": p.get("servicos", []),
                    "modulos": ["ged", "operacional", "financeiro", "fiscal", "portal"],
                },
                source_module="gedeon",
                cliente_id=cliente_id,
            )
        )

    async def _on_contrato_assinado(self, event: ConectaEvent) -> None:
        p = event.payload
        cliente_id = event.cliente_id
        tipo_kit = p.get("tipo_kit", "maos_de_obra")

        if cliente_id:
            competencia = datetime.utcnow().strftime("%Y-%m")
            await gedeon_context.update(cliente_id, competencia, "tipo_kit", tipo_kit)
            logger.info("GEDEON: tipo kit configurado — %s → %s", cliente_id, tipo_kit)


# Singleton global
gedeon = Gedeon.get_instance()
