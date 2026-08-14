"""Lembretes de ponto por WhatsApp — 3 por turno, param na batida.

O canal é Baileys (WhatsApp Web não-oficial) no número da empresa, o mesmo que o
comercial usa para proposta e follow-up. Por isso o teto de 3 mensagens por turno
e as janelas de 1 minuto são REQUISITO, não preferência: cadência de spam queima
o número e derruba junto o canal de cliente.

A escalada para líder do posto, supervisor e gerente operacional NÃO mora aqui —
quem faz é `operacional.check_late_employees`, pelo sino, a cada 5 minutos.

Plano: docs/superpowers/plans/2026-08-11-lembretes-ponto-whatsapp.md
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import text

from modules.people_management.ponto.coorte_ponto import SQL_NAO_AUSENTE_HOJE

logger = logging.getLogger(__name__)

# delta_min (minutos desde o início do turno; negativo = antes) -> modelo da mensagem
ETAPAS: dict[int, str] = {
    -15: "Seu turno no {posto} começa às {hora}. Bata o ponto pelo app do Conecta PRO.",
    0: "Seu turno no {posto} começou agora ({hora}). Bata o ponto pelo app.",
    10: "Você ainda não bateu o ponto do turno das {hora} no {posto}. Bata agora, por favor.",
}

PONTO_LEMBRETE_ENABLED = os.getenv("PONTO_LEMBRETE_ENABLED", "false").lower() == "true"

# ponytail: teto por rodada protege o número Baileys de uma escala malformada
# (ex.: 300 turnos com o mesmo horário de início). O excedente vai para o log e
# para o retorno da task, nunca some em silêncio. Subir só depois de medir o
# volume real de um dia.
TETO_POR_RODADA = 30


def etapa_para(delta_min: int) -> int | None:
    """Etapa exata deste minuto, ou None.

    Janela de 1 minuto por etapa: o beat roda a cada 60s e o dedup por
    (shift_id, etapa) impede repetição se o beat atrasar e rodar duas vezes.
    """
    return delta_min if delta_min in ETAPAS else None


SQL_PENDENTES = (
    """
SELECT sh.id::text AS shift_id, e.id::text AS employee_id, e.nome,
       coalesce(nullif(e.celular,''), nullif(e.telefone,'')) AS telefone,
       p.name AS posto,
       to_char(sh.planned_start_time, 'HH24:MI') AS hora,
       (EXTRACT(EPOCH FROM (
          (now() AT TIME ZONE 'America/Manaus')
          - ((now() AT TIME ZONE 'America/Manaus')::date + sh.planned_start_time)
       ))/60)::int AS delta_min
FROM shifts sh
JOIN posts p ON p.id = sh.post_id
JOIN employees e ON e.id = sh.employee_id
WHERE sh.shift_date = (now() AT TIME ZONE 'America/Manaus')::date
  AND sh.is_active = TRUE
  AND sh.is_off_day = FALSE
  AND lower(coalesce(sh.status,'')) IN ('scheduled','agendado','ativo')
  AND coalesce(e.is_homologacao, false) = false
  AND e.status = 'ativo'
  AND (e.tipo_contrato = 'clt' OR e.tipo_contrato IS NULL)
  AND (e.tipo_contrato IS DISTINCT FROM 'pj')
"""
    + SQL_NAO_AUSENTE_HOJE
    + """
  -- para na batida: qualquer batida válida na janela do turno cancela os lembretes
  AND NOT EXISTS (
    SELECT 1 FROM gp_clock_punches cp
    WHERE cp.employee_id = e.id
      AND coalesce(cp.status,'') NOT IN ('facial_reprovado')
      AND cp.punch_timestamp BETWEEN
            ((now() AT TIME ZONE 'America/Manaus')::date + sh.planned_start_time - interval '1 hour')
        AND ((now() AT TIME ZONE 'America/Manaus')::date + sh.planned_start_time + interval '12 hours')
  )
  -- dedup: nunca repete a mesma etapa do mesmo turno
  AND NOT EXISTS (
    SELECT 1 FROM ponto_lembrete_log l
    WHERE l.shift_id = sh.id AND l.etapa = :etapa
  )
"""
)


def _so_digitos(telefone: str) -> str:
    return "".join(c for c in telefone if c.isdigit())


def normalizar_telefone(bruto: str | None) -> str | None:
    """Devolve só os dígitos de um telefone BR válido, ou None se não der para confiar.

    O cadastro tem de tudo: '(92) 98463-5566', '92 98584-7540', '929848631485' (12
    dígitos), '982064669' (sem DDD) e '(99) 1361-770' (curto e com DDD de outro estado).
    Enviar para número inválido não é só desperdício: falha repetida é o gatilho clássico
    para o WhatsApp marcar o remetente como spam — e o remetente é o número da empresa,
    o mesmo do comercial.

    Aceita 10 dígitos (fixo com DDD) ou 11 (celular com DDD). NÃO completa DDD que falta,
    porque adivinhar DDD é mandar mensagem da empresa para um desconhecido.
    """
    if not bruto:
        return None
    dig = _so_digitos(bruto)
    if len(dig) not in (10, 11):
        return None
    if dig[:2] < "11" or dig[:2] > "99":  # DDD válido no Brasil
        return None
    if len(dig) == 11 and dig[2] != "9":  # celular com 11 dígitos começa com 9
        return None
    return dig


def _optout(db, telefone: str) -> bool:
    """Número que pediu para não receber mensagem. Consentimento é limite, não detalhe."""
    return bool(
        db.execute(
            text("SELECT 1 FROM crm_followup_optout WHERE phone_canonical = :p LIMIT 1"),
            {"p": _so_digitos(telefone)},
        )
        .mappings()
        .all()
    )


async def _enviar(telefone: str, mensagem: str) -> bool:
    from modules.integrations.connectors.whatsapp.service import send_text_message

    try:
        await send_text_message(telefone, mensagem)
        return True
    except Exception as exc:  # rede/Baileys fora do ar não pode derrubar a rodada
        logger.error("[Lembrete Ponto] falha ao enviar para %s: %s", telefone, exc)
        return False


async def rodar_lembretes(db) -> dict:
    """Uma rodada (1 minuto). No máximo 1 mensagem por turno por etapa."""
    res = {
        "enviados": 0,
        "pulados_sem_telefone": 0,
        "pulados_telefone_invalido": 0,
        "pulados_optout": 0,
        "teto_rodada": 0,
        "falhas_envio": 0,
        "dry_run": not PONTO_LEMBRETE_ENABLED,
    }

    for etapa, modelo in ETAPAS.items():
        linhas = db.execute(text(SQL_PENDENTES), {"etapa": etapa}).mappings().all()
        for r in linhas:
            # o SQL já filtra por etapa via dedup, mas o minuto é conferido aqui:
            # beat atrasado não pode disparar um lembrete fora da hora.
            if etapa_para(int(r["delta_min"])) != etapa:
                continue

            bruto = (r["telefone"] or "").strip()
            if not bruto:
                res["pulados_sem_telefone"] += 1
                logger.warning("[Lembrete Ponto] %s sem telefone — turno %s", r["nome"], r["shift_id"])
                continue

            tel = normalizar_telefone(bruto)
            if not tel:
                res["pulados_telefone_invalido"] += 1
                logger.warning(
                    "[Lembrete Ponto] %s com telefone INVÁLIDO no cadastro (%r) — não enviado. "
                    "Corrigir no cadastro; não dá para adivinhar o número.",
                    r["nome"],
                    bruto,
                )
                continue

            if _optout(db, tel):
                res["pulados_optout"] += 1
                continue

            if res["enviados"] >= TETO_POR_RODADA:
                res["teto_rodada"] += 1
                logger.warning("[Lembrete Ponto] teto da rodada atingido — %s ficou de fora", r["nome"])
                continue

            msg = modelo.format(posto=r["posto"], hora=r["hora"])
            if res["dry_run"]:
                logger.info("[Lembrete Ponto][DRY] -> %s (%s): %s", r["nome"], tel, msg)
                continue

            ok = await _enviar(tel, msg)
            db.execute(
                text(
                    "INSERT INTO ponto_lembrete_log (shift_id, etapa, employee_id, telefone, ok) "
                    "VALUES (:s, :e, :emp, :tel, :ok) ON CONFLICT DO NOTHING"
                ),
                {"s": r["shift_id"], "e": etapa, "emp": r["employee_id"], "tel": tel, "ok": ok},
            )
            db.commit()
            if ok:
                res["enviados"] += 1
            else:
                res["falhas_envio"] += 1

    return res
