"""Registra a TENTATIVA de bater ponto que FALHOU.

🔴 POR QUE ISTO EXISTE. Em 23/08/2026 o Jordan pediu uma auditoria severa do ponto: "a
Lívia dá divergência, o Ediwilson dá como se fosse ainda o primeiro acesso dele, pede pra
cadastrar de novo o rosto, enfim, muitos erros assim".

Eu não consegui responder. O banco tinha 1.943 batidas que DERAM CERTO e ZERO registro das
que falharam — quando o rosto não é reconhecido, ou a câmera não abre, ou a consulta ao
cadastro cai, nada é gravado e a tentativa some sem rastro. Consegui eliminar hipóteses
(descriptor válido, conta ativa, geofence ok, rosto cadastrado) mas não PROVAR a causa de
quatro pessoas que nunca bateram uma única vez.

Auditoria por eliminação é o que se faz quando falta evidência. Isto é a evidência.

Grava em `gp_audit_logs`, que já existe com a estrutura necessária (ator, IP, device,
geolocalização, extra_data em JSONB) — sem migration, que é zona proibida sem autorização.

⚠️ NUNCA DERRUBA A BATIDA. Se o log falhar, o funcionário não pode ser prejudicado: quem
está na guarita às 6h precisa registrar o ponto, não alimentar a auditoria. Toda falha aqui
é engolida de propósito — é o único `except` mudo que este arquivo aceita, e por essa razão.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: Motivos conhecidos. Texto livre também é aceito — o que não pode é a tentativa sumir.
MOTIVO_SEM_ROSTO = "sem_rosto_cadastrado"
MOTIVO_NAO_RECONHECIDO = "rosto_nao_reconhecido"
MOTIVO_CAMERA = "camera_nao_abriu"
MOTIVO_REFERENCIA_INDISPONIVEL = "cadastro_indisponivel"
MOTIVO_FORA_GEOFENCE = "fora_do_geofence"
MOTIVO_GPS = "gps_negado"
MOTIVO_DUPLICADA = "batida_duplicada"

# ⚠️ `gp_audit_logs` tem 11 colunas NOT NULL, incluindo actor_user_id, actor_user_name,
# actor_user_role e actor_user_module. Quem tenta bater e falha pode não ter user_id
# resolvido (a falha pode ser ANTES de identificar o usuário), então nenhum desses campos
# pode depender de dado que talvez não exista — daí os fallbacks abaixo. Sem eles o INSERT
# levanta NotNullViolation, o `except` engole, e a tentativa some: exatamente o buraco que
# este arquivo existe para tapar.
_SQL = text(
    "INSERT INTO gp_audit_logs (id, timestamp, action, entity, entity_id, description, "
    "  source_module, actor_user_id, actor_user_name, actor_user_role, actor_user_module, "
    "  context_ip, context_user_agent, context_device_type, context_geolocation, "
    "  related_funcionario_id, extra_data) "
    # 🔴 `now()` CRU GRAVAVA EM UTC — 4 HORAS ADIANTADO (medido em 29/09/2026).
    #
    # `gp_audit_logs.timestamp` é `timestamp WITHOUT time zone`, e a sessão do aplicativo roda
    # em UTC: `now()::timestamp` gravava 20:06 enquanto em Manaus eram 16:06. Medido no mesmo
    # dia, o resto da casa grava em MANAUS — `ponto.foto_vista` (943 linhas), `pesquisa_resposta`,
    # `kit.vinculos_removidos`, `ponto.batida_retipada`. Só esta ação estava fora.
    #
    # ⭐ O custo é exatamente o propósito desta tabela: a falha que a TELMA teve às 07:00 ficava
    # arquivada às 11:00. Quem investigasse «o que aconteceu às 7 da manhã» não acharia nada —
    # um registro de falha com hora errada é quase tão ruim quanto não ter registro.
    #
    # ⚠️ E ele me enganou na hora de ler: vi 17:00 num log e pensei «está no futuro».
    "VALUES (:id, (now() AT TIME ZONE 'America/Manaus'), 'ponto.tentativa_falhou', "
    "  'gp_clock_punches', :eid, :desc, "
    "  'people_management.ponto', :uid, :unome, 'funcionario', 'ponto', "
    "  :ip, :ua, :dev, CAST(:geo AS jsonb), :eid, CAST(:extra AS jsonb))"
)


async def registrar_falha_async(
    db,
    *,
    employee_id: str | None,
    motivo: str,
    detalhe: str | None = None,
    user_id: str | None = None,
    user_name: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    device: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Registra uma tentativa frustrada. Nunca levanta — a batida vem primeiro."""
    try:
        geo = (
            json.dumps({"latitude": latitude, "longitude": longitude})
            if latitude is not None and longitude is not None
            else None
        )
        payload = {"motivo": motivo, **(extra or {})}
        if detalhe:
            payload["detalhe"] = detalhe[:400]
        await db.execute(
            _SQL,
            {
                "id": str(uuid.uuid4()),
                "eid": str(employee_id) if employee_id else "desconhecido",
                "desc": f"{motivo}: {detalhe}"[:600] if detalhe else motivo,
                "uid": str(user_id) if user_id else "desconhecido",
                "unome": (user_name or "")[:120] or "desconhecido",
                "ip": (ip or "")[:60] or None,
                "ua": user_agent,
                "dev": (device or "")[:40] or None,
                "geo": geo,
                "extra": json.dumps(payload, ensure_ascii=False),
            },
        )
    except Exception as exc:  # noqa: BLE001 — ver docstring: log nunca derruba batida
        logger.warning("nao consegui registrar tentativa de ponto (%s): %s", motivo, exc)
