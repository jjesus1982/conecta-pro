"""
Conecta PRO — ConectaEventBus: barramento unificado de eventos.

Substitui: GPEventBus (gp:* PubSub) + MessageBus (in-memory asyncio)
Transporte: Redis Streams — persistência + replay + consumer groups
Namespace: conecta:{dominio}:{acao}

Compatibilidade retroativa:
  - GPEventBus.emit()  → event_bus.emit()  (mesmo assinatura)
  - GPEventBus.subscribe() → event_bus.subscribe() (wildcards mantidos)
"""

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Any

import redis.asyncio as aioredis
from fastapi import WebSocket

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prioridade — mantém compatibilidade com GPEventBus (IntEnum CRITICO=1)
# ---------------------------------------------------------------------------
class EventPriority(IntEnum):
    CRITICO = 1
    ALTO = 2
    NORMAL = 3
    BAIXO = 4

    # Aliases em inglês (usado pelo MessageBus legado)
    CRITICAL = 1
    HIGH = 2
    LOW = 4


# ---------------------------------------------------------------------------
# Actor / Context — mantidos do GPEventBus para compatibilidade
# ---------------------------------------------------------------------------
@dataclass
class EventActor:
    user_id: str = ""
    user_name: str = ""
    user_role: str = ""
    user_module: str = ""


@dataclass
class EventContext:
    ip_address: str = ""
    user_agent: str = ""
    device_type: str = "web"
    session_id: str = ""
    geolocation: dict[str, float] | None = None


# ---------------------------------------------------------------------------
# ConectaEvent — estrutura unificada
# ---------------------------------------------------------------------------
@dataclass
class ConectaEvent:
    """Evento padrão do Conecta PRO (unifica Event + Message)."""

    event_type: str
    payload: dict[str, Any]
    source_module: str
    priority: EventPriority = EventPriority.NORMAL
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    correlation_id: str | None = None
    affected_modules: list[str] = field(default_factory=list)
    actor: EventActor | None = None
    context: EventContext | None = None
    # Campos extras de domínio (opcionais)
    funcionario_id: str | None = None
    cliente_id: str | None = None
    competencia: str | None = None  # "2026-03"

    def to_stream_dict(self) -> dict[str, str]:
        """Serializa para Redis Streams (valores devem ser string)."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "payload": json.dumps(self.payload, default=str),
            "source_module": self.source_module,
            "priority": str(int(self.priority)),
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id or "",
            "affected_modules": json.dumps(self.affected_modules),
            "actor": json.dumps(asdict(self.actor)) if self.actor else "{}",
            "context": json.dumps(asdict(self.context)) if self.context else "{}",
            "funcionario_id": self.funcionario_id or "",
            "cliente_id": self.cliente_id or "",
            "competencia": self.competencia or "",
        }

    def to_dict(self) -> dict[str, Any]:
        """Compatibilidade com código que chama event.to_dict()."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "payload": self.payload,
            "source_module": self.source_module,
            "priority": int(self.priority),
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
            "affected_modules": self.affected_modules,
            "actor": asdict(self.actor) if self.actor else None,
            "context": asdict(self.context) if self.context else None,
            "funcionario_id": self.funcionario_id,
            "cliente_id": self.cliente_id,
            "competencia": self.competencia,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_stream_dict(cls, data: dict[str, str]) -> "ConectaEvent":
        actor_data = json.loads(data.get("actor", "{}"))
        actor = EventActor(**actor_data) if actor_data else None
        ctx_data = json.loads(data.get("context", "{}"))
        context = EventContext(**ctx_data) if ctx_data else None
        ev = cls(
            event_type=data.get("event_type", ""),
            payload=json.loads(data.get("payload", "{}")),
            source_module=data.get("source_module", ""),
            priority=EventPriority(int(data.get("priority", 3))),
            event_id=data.get("event_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", datetime.utcnow().isoformat()),
            correlation_id=data.get("correlation_id") or None,
            affected_modules=json.loads(data.get("affected_modules", "[]")),
            actor=actor,
            context=context,
            funcionario_id=data.get("funcionario_id") or None,
            cliente_id=data.get("cliente_id") or None,
            competencia=data.get("competencia") or None,
        )
        return ev

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConectaEvent":
        """Compatibilidade com código legado que usa Event.from_dict()."""
        actor = None
        if data.get("actor"):
            actor = EventActor(**data["actor"])
        context = None
        if data.get("context"):
            context = EventContext(**data["context"])
        return cls(
            event_type=data.get("event_type", ""),
            payload=data.get("payload", {}),
            source_module=data.get("source_module", ""),
            priority=EventPriority(data.get("priority", 3)),
            event_id=data.get("event_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", datetime.utcnow().isoformat()),
            correlation_id=data.get("correlation_id"),
            affected_modules=data.get("affected_modules", []),
            actor=actor,
            context=context,
        )

    @classmethod
    def from_json(cls, json_str: str) -> "ConectaEvent":
        return cls.from_dict(json.loads(json_str))


# Alias de compatibilidade com código que importa "Event"
Event = ConectaEvent


# ---------------------------------------------------------------------------
# Catálogo de tipos de eventos
# ---------------------------------------------------------------------------
class EventTypes:
    """Fonte única de verdade para todos os event_type do sistema."""

    # ── GP (retrocompatibilidade com GPEventTypes gp.*) ──────────────────
    GP_DOCUMENTO_CRIADO = "gp.documento.criado"
    GP_DOCUMENTO_ASSINADO = "gp.documento.assinado"
    GP_DOCUMENTO_ARQUIVADO = "gp.documento.arquivado"
    GP_PONTO_BATIDO = "gp.ponto.batido"
    GP_PONTO_FALTA = "gp.ponto.falta"
    GP_PONTO_HORA_EXTRA = "gp.ponto.hora_extra"
    GP_PONTO_MES_FECHADO = "gp.ponto.mes_fechado"
    GP_FOLHA_CALCULADA = "gp.folha.calculada"
    GP_FOLHA_FECHADA = "gp.folha.fechada"
    GP_FUNCIONARIO_ADMITIDO = "gp.funcionario.admitido"
    GP_FUNCIONARIO_DEMITIDO = "gp.funcionario.demitido"
    GP_FUNCIONARIO_TRANSFERIDO = "gp.funcionario.transferido"
    GP_ESCALA_PUBLICADA = "gp.escala.publicada"
    GP_ADVERTENCIA_APLICADA = "gp.disciplinar.advertencia"
    GP_FERIAS_APROVADAS = "gp.ferias.aprovadas"
    GP_ASO_EMITIDO = "gp.aso.emitido"
    GP_ASO_VENCENDO = "gp.aso.vencendo"
    GP_EPI_ENTREGUE = "gp.epi.entregue"
    GP_TREINAMENTO_CONCLUIDO = "gp.treinamento.concluido"

    # ── DP ───────────────────────────────────────────────────────────────
    DP_FUNCIONARIO_ADMITIDO = "dp.funcionario.admitido"
    DP_FUNCIONARIO_DEMITIDO = "dp.funcionario.demitido"
    DP_FUNCIONARIO_TRANSFERIDO = "dp.funcionario.transferido"
    DP_ATESTADO_REGISTRADO = "dp.atestado.registrado"
    DP_FERIAS_APROVADAS = "dp.ferias.aprovadas"
    DP_FERIAS_INICIADAS = "dp.ferias.iniciadas"
    DP_FOLHA_FECHADA = "dp.folha.fechada"
    DP_HOLERITE_GERADO = "dp.holerite.gerado"
    DP_AFASTAMENTO_INSS = "dp.afastamento.inss"
    DP_BENEFICIO_ADICIONADO = "dp.beneficio.adicionado"
    DP_CONTRATO_CRIADO = "dp.contrato.criado"
    DP_CARGO_ALTERADO = "dp.funcionario.cargo_alterado"
    DP_SALARIO_RECALCULADO = "dp.folha.salario_recalculado"

    # ── CCT (fonte única de cargos/pisos/adicionais) ──────────────────────
    CCT_CARGO_ATUALIZADO = "cct.cargo.atualizado"
    CCT_CONVENCAO_VIGENTE = "cct.convencao.vigente"
    CCT_REAJUSTE_APLICADO = "cct.reajuste.aplicado"

    # ── OPERACIONAL ───────────────────────────────────────────────────────
    OPS_OCORRENCIA_REGISTRADA = "operacional.ocorrencia.registrada"
    OPS_CAT_REGISTRADA = "operacional.cat.registrada"
    OPS_ESCALA_PUBLICADA = "operacional.escala.publicada"
    OPS_TURNO_DESCOBERTO = "operacional.turno.descoberto"
    OPS_SUBSTITUICAO_REALIZADA = "operacional.substituicao.realizada"
    OPS_BANCO_HORAS_CRIADO = "operacional.banco_horas.criado"
    OPS_MEDIDA_DISCIPLINAR_CRIADA = "operacional.medida_disciplinar.criada"
    OPS_ALOCACAO_CRIADA = "operacional.alocacao.criada"
    OPS_TURNO_INICIADO = "operacional.turno.iniciado"
    OPS_TURNO_ENCERRADO = "operacional.turno.encerrado"
    OPS_FERIAS_APROVADAS_OP = "operacional.ferias.aprovadas"
    OPS_DIARISTA_CRIADA = "operacional.diarista.criada"
    OPS_DIARISTA_CHECKIN = "operacional.diarista.checkin"
    OPS_DIARISTA_CHECKOUT = "operacional.diarista.checkout"
    OPS_DIARISTA_PAGAMENTO = "operacional.diarista.pagamento_processado"
    OPS_COMUNICADO_PUBLICADO = "operacional.comunicado.publicado"

    # ── DP (complemento) ──────────────────────────────────────────────────
    DP_PONTO_REGISTRADO = "dp.ponto.registrado"
    DP_ESOCIAL_GERADO = "dp.esocial.gerado"

    # ── RH ────────────────────────────────────────────────────────────────
    RH_PLANO_CARREIRA_CRIADO = "rh.plano_carreira.criado"
    RH_MILESTONE_CONCLUIDO = "rh.milestone.concluido"
    RH_AVALIACAO_CRIADA = "rh.avaliacao_desempenho.criada"
    RH_AVALIACAO_CONCLUIDA = "rh.avaliacao_desempenho.concluida"
    RH_ONBOARDING_ITEM_CONCLUIDO = "rh.onboarding.item_concluido"
    RH_AVALIACAO_360_CRIADA = "rh.avaliacao_360.criada"
    RH_AVALIACAO_360_INICIADA = "rh.avaliacao_360.iniciada"

    # ── PONTO ─────────────────────────────────────────────────────────────
    PONTO_BATIDA_REGISTRADA = "ponto.batida.registrada"
    PONTO_ESPELHO_FECHADO = "ponto.espelho.fechado"
    PONTO_FALTA_CONFIRMADA = "ponto.falta.confirmada"
    PONTO_HORA_EXTRA_APROVADA = "ponto.hora_extra.aprovada"

    # ── SAÚDE OCUPACIONAL ─────────────────────────────────────────────────
    SAUDE_ASO_EMITIDO = "saude.aso.emitido"
    SAUDE_ASO_VENCENDO = "saude.aso.vencendo"
    SAUDE_EPI_ENTREGUE = "saude.epi.entregue"
    SAUDE_TREINAMENTO_CONCLUIDO = "saude.treinamento.concluido"
    SAUDE_PPRA_ATUALIZADO = "saude.ppra.atualizado"
    SAUDE_PCMSO_ATUALIZADO = "saude.pcmso.atualizado"
    SAUDE_CAT_REGISTRADA = "saude.cat.registrada"
    SAUDE_AFASTAMENTO_INICIADO = "saude.afastamento.iniciado"

    # ── GED ───────────────────────────────────────────────────────────────
    GED_DOCUMENTO_CRIADO = "ged.documento.criado"
    GED_DOCUMENTO_ATUALIZADO = "ged.documento.atualizado"
    GED_KIT_INICIADO = "ged.kit.iniciado"
    GED_KIT_MONTADO = "ged.kit.montado"
    GED_KIT_ENVIADO = "ged.kit.enviado"
    GED_KIT_CONFIRMADO = "ged.kit.confirmado"
    GED_KIT_DOCUMENTO_VINCULADO = "ged.kit.documento_vinculado"  # HERMES — §94
    GED_CERTIDAO_VENCIDA = "ged.certidao.vencida"
    GED_CERTIDAO_VENCENDO = "ged.certidao.vencendo"
    GED_CERTIDAO_RENOVADA = "ged.certidao.renovada"
    GED_ASSINATURA_PENDENTE = "ged.assinatura.pendente"
    GED_ASSINATURA_CONCLUIDA = "ged.assinatura.concluida"

    # ── FISCAL ────────────────────────────────────────────────────────────
    FISCAL_CERTIDAO_VENCIDA = "fiscal.certidao.vencida"
    FISCAL_CERTIDAO_RENOVADA = "fiscal.certidao.renovada"
    FISCAL_NFS_EMITIDA = "fiscal.nfs.emitida"
    FISCAL_CND_CONSULTADA = "fiscal.cnd.consultada"

    # ── FINANCEIRO ────────────────────────────────────────────────────────
    FIN_CONTRATO_INADIMPLENTE = "financeiro.contrato.inadimplente"
    FIN_NOTA_EMITIDA = "financeiro.nota.emitida"
    FIN_CONTRATO_RENOVADO = "financeiro.contrato.renovado"
    FIN_PAGAMENTO_RECEBIDO = "financeiro.pagamento.recebido"
    FIN_PAGAMENTO_REALIZADO = "financeiro.pagamento.realizado"
    FIN_INADIMPLENCIA_DETECTADA = "financeiro.inadimplencia.detectada"

    # ── GOV ───────────────────────────────────────────────────────────────
    GOV_ESOCIAL_TRANSMITIDO = "gov.esocial.transmitido"
    GOV_FGTS_RECOLHIDO = "gov.fgts.recolhido"
    GOV_SEFAZ_AUTORIZADO = "gov.sefaz.autorizado"

    # ── PORTAL ────────────────────────────────────────────────────────────
    PORTAL_DOCUMENTO_SOLICITADO = "portal.documento.solicitado"
    PORTAL_FERIAS_SOLICITADAS = "portal.ferias.solicitadas"

    # ── CRM ───────────────────────────────────────────────────────────────
    CRM_LEAD_CONVERTIDO = "crm.lead.convertido"
    CRM_CONTRATO_ASSINADO = "crm.contrato.assinado"
    CRM_CLIENTE_ATIVO = "crm.cliente.ativo"
    CRM_CLIENTE_INATIVADO = "crm.cliente.inativado"
    CRM_PROPOSTA_APROVADA = "crm.proposta.aprovada"


# ---------------------------------------------------------------------------
# ConectaEventBus — barramento unificado
# ---------------------------------------------------------------------------
class ConectaEventBus:
    """
    Barramento unificado do Conecta PRO.

    Transporte: Redis Streams (xadd/xreadgroup) para persistência e replay.
    Retrocompatível com GPEventBus:
      - .emit()      → mesma assinatura
      - .subscribe() → wildcards mantidos
      - .publish()   → mesmo comportamento
      - WebSocket    → broadcast mantido

    Streams por domínio:
      conecta:stream:gp, dp, operacional, ponto, saude,
      ged, fiscal, financeiro, gov, portal, sistema
    """

    STREAMS: dict[str, str] = {
        "gp": "conecta:stream:gp",
        "dp": "conecta:stream:dp",
        "ged": "conecta:stream:ged",
        "operacional": "conecta:stream:operacional",
        "fiscal": "conecta:stream:fiscal",
        "ponto": "conecta:stream:ponto",
        "saude": "conecta:stream:saude",
        "financeiro": "conecta:stream:financeiro",
        "rh": "conecta:stream:rh",
        "portal": "conecta:stream:portal",
        "gov": "conecta:stream:gov",
        "sistema": "conecta:stream:sistema",
    }
    DEFAULT_STREAM = "conecta:stream:sistema"
    PROCESSED_EVENTS_KEY = "conecta:processed_events"
    PROCESSED_EVENTS_TTL = 3600 * 24  # 24h — deduplicação

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None
        self._handlers: dict[str, list[Callable]] = {}
        self._websockets: set[WebSocket] = set()
        self._running = False
        self._consumer_task: asyncio.Task | None = None

    # ── Conexão ─────────────────────────────────────────────────────────

    async def connect(self, redis_url: str | None = None) -> None:
        """Conectar ao Redis. Chamado no lifespan do FastAPI."""
        if self._redis is not None:
            return
        from core.config import settings as _settings

        url = redis_url or getattr(_settings, "redis_url", "redis://localhost:6379/1")
        self._redis = await aioredis.from_url(url, encoding="utf-8", decode_responses=True)
        logger.info("ConectaEventBus conectado: %s", url)

    async def disconnect(self) -> None:
        self._running = False
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
        if self._redis:
            await self._redis.aclose()
            self._redis = None
        logger.info("ConectaEventBus desconectado")

    # ── Publicar ────────────────────────────────────────────────────────

    def _stream_for(self, event_type: str) -> str:
        dominio = event_type.split(".")[0] if "." in event_type else "sistema"
        return self.STREAMS.get(dominio, self.DEFAULT_STREAM)

    async def publish(self, event: ConectaEvent) -> bool:
        """Publica evento no Redis Stream correspondente."""
        if self._redis is None:
            # Sem conexão, cada publish floodava o log com um WARNING. Avisa UMA vez
            # (warning) e depois rebaixa p/ debug — não polui o log com 1 linha por evento.
            if not getattr(self, "_warned_desconectado", False):
                logger.warning("EventBus não conectado — eventos serão descartados (avisado 1x)")
                self._warned_desconectado = True
            else:
                logger.debug("EventBus não conectado — descartando: %s", event.event_type)
            return False
        try:
            stream = self._stream_for(event.event_type)
            await self._redis.xadd(stream, event.to_stream_dict(), maxlen=10000)
            await self._broadcast_websocket(event)
            logger.debug("Evento: %s → %s [%s]", event.event_type, stream, event.event_id[:8])
            return True
        except Exception as e:
            logger.error("Erro ao publicar evento %s: %s", event.event_type, e)
            return False

    # ── Emit (alias GPEventBus) ─────────────────────────────────────────

    async def emit(
        self,
        event_type: str,
        payload: dict[str, Any],
        source_module: str,
        priority: EventPriority = EventPriority.NORMAL,
        actor: EventActor | None = None,
        context: EventContext | None = None,
        affected_modules: list[str] | None = None,
        funcionario_id: str | None = None,
        cliente_id: str | None = None,
        competencia: str | None = None,
    ) -> ConectaEvent:
        """Cria e publica um evento (retrocompatível com GPEventBus.emit)."""
        event = ConectaEvent(
            event_type=event_type,
            payload=payload,
            source_module=source_module,
            priority=priority,
            actor=actor,
            context=context,
            affected_modules=affected_modules or [],
            funcionario_id=funcionario_id,
            cliente_id=cliente_id,
            competencia=competencia,
        )
        await self.publish(event)
        return event

    # ── Subscribe ────────────────────────────────────────────────────────

    def subscribe(self, event_type: str, handler: Callable) -> None:
        """
        Registra handler para tipo de evento.
        Wildcards: "gp.*"  →  qualquer gp.x.y
                   "dp.funcionario.*"  →  dp.funcionario.x
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.debug("Handler registrado: %s", event_type)

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def _matches(self, tipo: str, pattern: str) -> bool:
        if pattern == tipo or pattern == "*":
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return tipo == prefix or tipo.startswith(prefix + ".")
        if pattern.endswith(".**"):
            prefix = pattern[:-3]
            return tipo.startswith(prefix)
        return False

    async def _dispatch(self, event: ConectaEvent) -> None:
        for pattern, handlers in self._handlers.items():
            if self._matches(event.event_type, pattern):
                for handler in handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(event)
                        else:
                            handler(event)
                    except Exception as e:
                        logger.error(
                            "Erro handler %s para %s: %s", getattr(handler, "__name__", "?"), event.event_type, e
                        )

    # ── Consumer loop (Redis Streams) ────────────────────────────────────

    async def start_consuming(
        self,
        group_name: str = "conecta-pro",
        consumer_name: str = "main-worker",
    ) -> None:
        """Inicia consumer de todos os streams em background."""
        if self._redis is None:
            logger.error("Redis não conectado — consumer não iniciado")
            return

        for stream in self.STREAMS.values():
            try:
                await self._redis.xgroup_create(stream, group_name, id="$", mkstream=True)
            except Exception:
                pass  # grupo já existe

        self._running = True
        logger.info("ConectaEventBus consumindo %d streams", len(self.STREAMS))

        while self._running:
            try:
                results = await self._redis.xreadgroup(
                    groupname=group_name,
                    consumername=consumer_name,
                    streams=dict.fromkeys(self.STREAMS.values(), ">"),
                    count=50,
                    block=1000,
                )
                for stream, messages in results or []:
                    for msg_id, data in messages:
                        try:
                            event = ConectaEvent.from_stream_dict(data)
                            if await self._is_duplicate(event.event_id):
                                await self._redis.xack(stream, group_name, msg_id)
                                continue
                            await self._mark_processed(event.event_id)
                            await self._dispatch(event)
                            await self._redis.xack(stream, group_name, msg_id)
                        except Exception as e:
                            logger.error("Erro msg %s: %s", msg_id, e)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Erro consumer loop: %s", e)
                await asyncio.sleep(1)

    # ── Deduplicação ─────────────────────────────────────────────────────

    async def _is_duplicate(self, event_id: str) -> bool:
        if not self._redis:
            return False
        return bool(await self._redis.sismember(self.PROCESSED_EVENTS_KEY, event_id))

    async def _mark_processed(self, event_id: str) -> None:
        if not self._redis:
            return
        await self._redis.sadd(self.PROCESSED_EVENTS_KEY, event_id)
        await self._redis.expire(self.PROCESSED_EVENTS_KEY, self.PROCESSED_EVENTS_TTL)

    # ── WebSocket (mantém API do GPEventBus) ─────────────────────────────

    async def register_websocket(self, ws: WebSocket) -> None:
        self._websockets.add(ws)

    async def unregister_websocket(self, ws: WebSocket) -> None:
        self._websockets.discard(ws)

    async def _broadcast_websocket(self, event: ConectaEvent) -> None:
        if not self._websockets:
            return
        msg = event.to_json()
        dead: set[WebSocket] = set()
        for ws in self._websockets:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._websockets.discard(ws)

    # ── Stats (retrocompatível com GPEventBus.get_stats) ─────────────────

    def get_stats(self) -> dict[str, Any]:
        return {
            "websockets_connected": len(self._websockets),
            "handlers_registered": sum(len(h) for h in self._handlers.values()),
            "event_types_subscribed": list(self._handlers.keys()),
            "running": self._running,
            "streams": list(self.STREAMS.keys()),
        }

    def get_health(self) -> dict[str, Any]:
        return {
            "status": "healthy" if self._running else "idle",
            "running": self._running,
            "redis_connected": self._redis is not None,
            "timestamp": datetime.utcnow().isoformat(),
        }


# ---------------------------------------------------------------------------
# Singleton global
# ---------------------------------------------------------------------------
_event_bus: ConectaEventBus | None = None


def get_event_bus() -> ConectaEventBus:
    """Retorna singleton do ConectaEventBus (retrocompatível com GPEventBus)."""
    global _event_bus
    if _event_bus is None:
        _event_bus = ConectaEventBus()
    return _event_bus


# Instância pronta para importar diretamente
event_bus = get_event_bus()
