"""GED — espelha o cliente novo em `ged_clients` quando ele vira ativo no CRM.

Ligado em 2026-08-07 (decisão Jordan). O evento `gedeon.cliente.espelhar` disparava 10x
sem ninguém reagir; ele carrega no payload a lista `modulos=[ged, operacional, financeiro,
fiscal, portal]` — a instrução de quem deveria espelhar. Só o GED foi implementado: é
documental, não cria posto, não move dinheiro, não fala com o governo.

O GAP QUE ISTO FECHA
  Medido em 2026-08-07: 21 clientes no CRM, 12 em `ged_clients`, **10 sem espelho**. Sem
  linha em `ged_clients` não há como pendurar kit documental no cliente.

O VÍNCULO CRM ↔ GED É POR NOME, e isso é frágil
  `ged_clients.id` e `clients.id` são UUIDs DIFERENTES para o mesmo cliente: 0 batem por id,
  11 de 12 batem por nome. Não há coluna de referência cruzada. Este handler segue a
  convenção existente (casa por nome normalizado) em vez de inventar outra — mas a
  fragilidade está registrada em auditoria/decisoes/eventos_investigacao_20260807.md:
  se o nome mudar de um lado, o espelho duplica.

IDEMPOTÊNCIA
  O evento já disparou 10x e pode repetir. O handler só INSERE quando não existe cliente com
  o mesmo nome normalizado. Nunca atualiza nem apaga — reprocessar é seguro.
"""

import logging
import re
import uuid

from sqlalchemy import text

from core.database import async_session_factory
from infrastructure.event_bus import ConectaEvent, EventTypes, event_bus

logger = logging.getLogger(__name__)

#: Tipos aceitos por ged_clients.type. 'condominio' é o default da coluna.
_TIPO_PADRAO = "condominio"


def _normalizar(nome: str) -> str:
    """Minúsculo, sem espaço duplicado nem borda — a chave de comparação por nome."""
    return re.sub(r"\s+", " ", (nome or "").strip()).lower()


async def on_cliente_espelhar(event: ConectaEvent) -> None:
    """Garante que o cliente exista em `ged_clients`. Idempotente por nome."""
    p = event.payload
    nome = (p.get("nome") or "").strip()
    if not nome:
        logger.info("GED espelhar: evento sem nome de cliente — ignorado")
        return

    alvo = _normalizar(nome)
    async with async_session_factory() as db:
        existe = (
            await db.execute(
                text(
                    "SELECT id FROM ged_clients "
                    "WHERE lower(regexp_replace(trim(name), '\\s+', ' ', 'g')) = :alvo LIMIT 1"
                ),
                {"alvo": alvo},
            )
        ).fetchone()
        if existe:
            logger.info("GED espelhar: '%s' já existe em ged_clients (%s)", nome, existe[0])
            return

        novo_id = str(uuid.uuid4())
        await db.execute(
            text(
                "INSERT INTO ged_clients (id, name, type, is_active, created_at, updated_at) "
                "VALUES (:id, :name, :tipo, true, now(), now())"
            ),
            {"id": novo_id, "name": nome, "tipo": _TIPO_PADRAO},
        )
        await db.commit()
        # O id do CRM vai no log porque nao ha coluna de referencia cruzada em ged_clients.
        # E o unico rastro do vinculo — ver a decisao pendente sobre formalizar essa FK.
        logger.info(
            "GED espelhar: cliente '%s' criado em ged_clients id=%s (crm cliente_id=%s)",
            nome,
            novo_id,
            p.get("cliente_id", "?"),
        )


def registrar_subscribers() -> None:
    """Registra o handler no ConectaEventBus. Chamado no lifespan do main_production."""
    event_bus.subscribe(EventTypes.GEDEON_CLIENTE_ESPELHAR, on_cliente_espelhar)
    logger.info("GED: subscriber de espelhamento de cliente registrado")
