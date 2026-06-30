"""Celery Tasks — CRM: follow-up de propostas.

FUNDAÇÃO 1: SELECIONA propostas vencidas para follow-up (cadência 2d/7d),
gera a lista e entrega ao Jordan via Telegram + log. NÃO contata o cliente.

⚠️  GATE LGPD — FOLLOWUP_AUTO_SEND = False:
    Com False, a rotina só GERA a lista e registra o follow-up como 'skipped'
    (a cadência AVANÇA, mas NADA é enviado ao cliente). Para LIGAR o disparo ao
    cliente (WhatsApp/e-mail) é necessário, NESTA ordem:
      1) revisão/aprovação LGPD do conteúdo e da base legal do contato;
      2) mudar FOLLOWUP_AUTO_SEND = True AQUI (constante no código, não no .env);
      3) rebuild da imagem do backend.

Semântica da cadência: ao listar uma proposta vencida, inserimos um registro em
proposal_followups (status='skipped' quando desligado). Como a próxima janela de
7 dias conta a partir desse registro, o MESMO lead NÃO reaparece na lista todo
dia — ele volta em +7 dias. Isso evita spam de lista e mantém a trilha (LGPD).
"""

import logging
import os

from celery_app import app

logger = logging.getLogger(__name__)

# === GATE LGPD — NÃO ligar sem revisão (ver docstring) ===
FOLLOWUP_AUTO_SEND = False

# Cadência
FOLLOWUP_FIRST_DAYS = 2  # 1º follow-up: 2 dias após sent_at
FOLLOWUP_NEXT_DAYS = 7  # seguintes: a cada 7 dias enquanto sem resposta


def _run_async(coro):
    """Helper para rodar corrotinas async nas tasks Celery (engine própria)."""
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgresql://", "postgresql+asyncpg://")

    async def _inner():
        engine = create_async_engine(DATABASE_URL, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with async_session() as session:
                return await coro(session)
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


def _telegram_send(text_msg: str) -> bool:
    """Entrega a lista ao Jordan via Telegram Bot API (credenciais do env). Best-effort."""
    token = os.getenv("MONITOR_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or ""
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.warning("followup: TELEGRAM token/chat ausente — lista NAO enviada (so log)")
        return False
    try:
        import requests  # noqa: PLC0415

        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text_msg, "parse_mode": "HTML"},
            timeout=15,
        )
        ok = r.status_code == 200 and r.json().get("ok")
        if not ok:
            logger.error("followup: Telegram falhou %s: %s", r.status_code, r.text[:200])
        return bool(ok)
    except Exception as e:  # noqa: BLE001
        logger.warning("followup: excecao no Telegram (best-effort): %s", e)
        return False


async def _enviar_followup_cliente(v: dict) -> tuple[str, str, str]:
    """BLOCO PRONTO — só roda com FOLLOWUP_AUTO_SEND=True. Retorna (channel, status, detail).

    NÃO é executado nesta fundação (gate LGPD). Mantido implementado p/ quando ligar.
    """
    from core.mailer import send_email  # noqa: PLC0415
    from modules.integrations.connectors.whatsapp.service import whatsapp_service  # noqa: PLC0415

    canais: list[str] = []
    msg_cli = (
        f"Olá! Sobre a proposta {v['number']} que enviamos, seguimos à disposição "
        f"para esclarecer dúvidas. Podemos avançar?"
    )
    try:
        if v.get("phone"):
            await whatsapp_service.send_custom(v["phone"], msg_cli)
            canais.append("whatsapp")
        if v.get("email"):
            await send_email(v["email"], f"Follow-up da proposta {v['number']}", f"<p>{msg_cli}</p>")
            canais.append("email")
        channel = "both" if len(canais) == 2 else (canais[0] if canais else "none")
        return channel, "sent", "enviado ao cliente"
    except Exception as e:  # noqa: BLE001
        return "none", "failed", str(e)[:200]


async def _followup_async(session):
    from datetime import datetime  # noqa: PLC0415

    from sqlalchemy import text  # noqa: PLC0415

    agora = datetime.utcnow()

    # 1) candidatas: enviadas e sem resposta
    rows = (
        await session.execute(
            text(
                "SELECT id, number, client_name, client_email, client_phone, total, sent_at "
                "FROM proposals WHERE status='sent' AND responded_at IS NULL AND sent_at IS NOT NULL"
            )
        )
    ).fetchall()

    vencidos: list[dict] = []
    for p in rows:
        pid, number, cname, cemail, cphone, total, sent_at = p
        # último follow-up já processado dessa proposta
        last = (
            await session.execute(
                text(
                    "SELECT sequence, COALESCE(sent_at, scheduled_for, created_at) AS quando "
                    "FROM proposal_followups WHERE proposal_id = :pid "
                    "ORDER BY sequence DESC LIMIT 1"
                ),
                {"pid": str(pid)},
            )
        ).first()

        if last is None:
            # nenhum follow-up ainda -> vence 2 dias após sent_at
            due = (agora - sent_at).total_seconds() >= FOLLOWUP_FIRST_DAYS * 86400
            next_seq = 1
        else:
            last_seq, quando = last
            due = (agora - quando).total_seconds() >= FOLLOWUP_NEXT_DAYS * 86400
            next_seq = last_seq + 1

        if not due:
            continue

        dias = int((agora - sent_at).total_seconds() // 86400)
        vencidos.append(
            {
                "id": str(pid),
                "number": number,
                "client_name": cname,
                "email": cemail,
                "phone": cphone,
                "total": float(total or 0),
                "dias": dias,
                "next_seq": next_seq,
            }
        )

    # 2) registra o follow-up (avança a cadência) + (se ligado) dispara ao cliente
    for v in vencidos:
        if FOLLOWUP_AUTO_SEND:
            # BLOCO PRONTO — NÃO executado nesta fundação (gate LGPD)
            channel, status_fu, detail = await _enviar_followup_cliente(v)
            await session.execute(
                text(
                    "INSERT INTO proposal_followups "
                    "(proposal_id, sequence, channel, status, scheduled_for, sent_at, detail) "
                    "VALUES (:pid, :seq, :ch, :st, :now, :now, :dt)"
                ),
                {"pid": v["id"], "seq": v["next_seq"], "ch": channel, "st": status_fu, "now": agora, "dt": detail},
            )
        else:
            await session.execute(
                text(
                    "INSERT INTO proposal_followups "
                    "(proposal_id, sequence, channel, status, scheduled_for, detail) "
                    "VALUES (:pid, :seq, 'none', 'skipped', :now, :dt)"
                ),
                {
                    "pid": v["id"],
                    "seq": v["next_seq"],
                    "now": agora,
                    "dt": "lista gerada, disparo desligado (gate LGPD)",
                },
            )
    await session.commit()

    # 3) monta e entrega a lista (Telegram + log)
    if vencidos:
        linhas = [
            f"• <b>{v['number']}</b> — {v['client_name']} — R$ {v['total']:.2f} "
            f"({v['dias']}d sem resposta, follow-up #{v['next_seq']})"
            for v in vencidos
        ]
        msg = (
            f"📋 <b>Follow-up de propostas</b> — {len(vencidos)} vencida(s)\n"
            f"(disparo ao cliente DESLIGADO — gate LGPD; lista para ação manual)\n\n" + "\n".join(linhas)
        )
    else:
        msg = "📋 Follow-up de propostas: nenhuma proposta vencida para follow-up hoje."

    entregue = _telegram_send(msg)
    logger.info("followup: vencidos=%s telegram=%s auto_send=%s", len(vencidos), entregue, FOLLOWUP_AUTO_SEND)
    return {"vencidos": len(vencidos), "telegram_ok": entregue, "auto_send": FOLLOWUP_AUTO_SEND}


@app.task(name="crm.followup_proposals", bind=True, max_retries=1)
def followup_proposals(self):
    """Rotina diária: gera lista de propostas vencidas p/ follow-up.

    NÃO contata o cliente (FOLLOWUP_AUTO_SEND=False / gate LGPD). Só seleciona,
    registra a cadência em proposal_followups e entrega a lista ao Jordan.
    """
    try:
        return _run_async(_followup_async)
    except Exception as e:  # noqa: BLE001
        logger.error("crm.followup_proposals falhou: %s", e)
        raise


@app.task(name="crm.process_sequences", bind=True, max_retries=1)
def process_sequences(self):
    """Processa os passos vencidos das sequências/cadências (envio e-mail/WhatsApp + avança o passo).
    Roda de hora em hora pelo Celery beat. Best-effort (nunca derruba o worker)."""
    from modules.crm.services.followups import within_business_hours
    from modules.crm.services.growth_services import process_due_enrollments

    # A cadência só TOCA o cliente em horário comercial (seg-sex 8-18h Manaus). Fora disso,
    # pula — o beat horário reprocessa na próxima janela. Respostas a inbound não passam por aqui.
    if not within_business_hours():
        return {"skip": "fora do horário comercial"}

    async def _inner(session):
        return await process_due_enrollments(session, limit=200)

    try:
        result = _run_async(_inner)
        logger.info("crm.process_sequences: %s", result)
        return result
    except Exception as e:  # noqa: BLE001
        logger.warning("crm.process_sequences falhou: %s", e)
        return {"error": str(e)}


# ============================================================================
# ORQUESTRAÇÃO José Luís ↔ Jordan (lembretes de pendência, resumo diário, agenda)
# ============================================================================
@app.task(name="crm.owner_pendentes", bind=True, max_retries=1)
def owner_pendentes(self):
    """Lembra o Jordan, 1x/dia, das propostas SEM resposta há >=N dias (default 3). Best-effort."""

    async def _inner(session):
        from modules.crm.services import orchestration as O

        # pendentes sem resposta — lê as PROPOSTAS reais (enviadas há >=3d sem resposta).
        # cadência "1x/dia" garantida pelo agendamento diário do beat.
        rows = await O.pendentes_sem_resposta(session)
        if not rows:
            return {"pendentes": 0}
        # temperatura por tempo sem resposta: <12 dias = pendente; >=12 (passou do D+10) = esfriando.
        mornos = [r for r in rows if (r["dias"] or 0) < 12]
        frios = [r for r in rows if (r["dias"] or 0) >= 12]
        partes = ["⏰ *Acompanhamento de propostas*"]
        if mornos:
            partes.append(
                "\n🟡 *Sem resposta ainda:*\n"
                + "\n".join(f"• {r['cliente_nome']} — {r['proposta'] or 'proposta'} ({r['dias']}d)" for r in mornos)
            )
        if frios:
            partes.append(
                "\n🔵 *Esfriando (passou do D+10):*\n"
                + "\n".join(f"• {r['cliente_nome']} — {r['proposta'] or 'proposta'} ({r['dias']}d)" for r in frios)
                + "\n\nDesses, quer que eu faça uma *última tentativa* ou prefere *encerrar*? Me diz quais."
            )
        if mornos and not frios:
            partes.append("\nQuer que eu dê um toque neles ou você assume algum?")
        await O.notify_owner("\n".join(partes))
        return {"pendentes": len(rows)}

    try:
        return _run_async(_inner)
    except Exception as e:  # noqa: BLE001
        logger.warning("crm.owner_pendentes falhou: %s", e)
        return {"error": str(e)}


@app.task(name="crm.owner_digest", bind=True, max_retries=1)
def owner_digest(self):
    """Resumo diário pro Jordan (fim do dia): respostas de hoje, pendentes, quem está com ele."""
    from sqlalchemy import text as _t

    async def _inner(session):
        from modules.crm.services import orchestration as O

        # conta sobre as PROPOSTAS reais do CRM + estado do acompanhamento
        d = (
            (
                await session.execute(
                    _t("""
            SELECT
              count(*) FILTER (WHERE p.status='draft') AS montadas,
              count(*) FILTER (WHERE p.status='sent') AS enviadas,
              count(*) FILTER (WHERE n.responsavel='jordan') AS com_jordan,
              count(*) FILTER (WHERE n.last_client_reply_at::date = (now() AT TIME ZONE 'America/Manaus')::date) AS responderam_hoje
            FROM proposals p LEFT JOIN crm_negociacao_state n ON n.proposal_id=p.id
            WHERE p.is_active=true AND p.status IN ('draft','sent')
        """),
                    {},
                )
            )
            .mappings()
            .first()
        )
        pendentes = len(await O.pendentes_sem_resposta(session))
        if not d or (d["montadas"] == 0 and d["enviadas"] == 0):
            return {"skip": "sem propostas abertas"}
        await O.notify_owner(
            f"🌙 *Resumo do dia*\n"
            f"• Propostas montadas (rascunho): {d['montadas']}\n"
            f"• Enviadas em acompanhamento: {d['enviadas']}\n"
            f"• Com você: {d['com_jordan']}\n"
            f"• Responderam hoje: {d['responderam_hoje']}\n"
            f"• Sem resposta (>= {O.REMINDER_AFTER_DAYS}d): {pendentes}\n\n"
            f"Bom descanso! Amanhã sigo em cima dos follow-ups. 💪"
        )
        return {"montadas": d["montadas"], "enviadas": d["enviadas"], "pendentes": pendentes}

    try:
        return _run_async(_inner)
    except Exception as e:  # noqa: BLE001
        logger.warning("crm.owner_digest falhou: %s", e)
        return {"error": str(e)}


@app.task(name="crm.owner_reminders_due", bind=True, max_retries=1)
def owner_reminders_due(self):
    """Dispara os lembretes agendados ('me lembra amanhã de X') que venceram."""
    from sqlalchemy import text as _t

    async def _inner(session):
        from modules.crm.services import orchestration as O

        rows = (
            (
                await session.execute(
                    _t(
                        "SELECT id, texto FROM crm_owner_reminder WHERE enviado=false AND quando <= now() "
                        "ORDER BY quando ASC LIMIT 20"
                    )
                )
            )
            .mappings()
            .all()
        )
        for r in rows:
            await O.notify_owner(f"🔔 *Lembrete:* {r['texto']}")
            await session.execute(_t("UPDATE crm_owner_reminder SET enviado=true WHERE id=:id"), {"id": r["id"]})
        await session.commit()
        return {"disparados": len(rows)}

    try:
        return _run_async(_inner)
    except Exception as e:  # noqa: BLE001
        logger.warning("crm.owner_reminders_due falhou: %s", e)
        return {"error": str(e)}


@app.task(name="crm.lembrete_reuniao", bind=True, max_retries=1)
def lembrete_reuniao(self):
    """Lembra o Jordan das reuniões confirmadas nas próximas ~24h (1x cada). Best-effort."""
    from sqlalchemy import text as _t

    async def _inner(session):
        from modules.crm.services import orchestration as O

        rows = (
            (
                await session.execute(
                    _t("""
            SELECT id, titulo, cliente_nome, to_char(quando AT TIME ZONE 'America/Manaus','DD/MM HH24:MI') AS quando,
                   COALESCE(local,'') AS local
            FROM crm_meetings
            WHERE status='confirmado' AND lembrete_enviado=false
              AND quando BETWEEN now() AND now() + interval '24 hours'
            ORDER BY quando ASC
        """)
                )
            )
            .mappings()
            .all()
        )
        for r in rows:
            loc = f" — {r['local']}" if r["local"] else ""
            cli = f" ({r['cliente_nome']})" if r["cliente_nome"] else ""
            await O.notify_owner(f"📅 *Lembrete de reunião*\n{r['titulo']}{cli}\n🕐 {r['quando']}{loc}")
            await session.execute(_t("UPDATE crm_meetings SET lembrete_enviado=true WHERE id=:id"), {"id": r["id"]})
        await session.commit()
        return {"lembrados": len(rows)}

    try:
        return _run_async(_inner)
    except Exception as e:  # noqa: BLE001
        logger.warning("crm.lembrete_reuniao falhou: %s", e)
        return {"error": str(e)}


@app.task(name="crm.score_leads", bind=True, max_retries=1)
def score_leads(self):
    """Recalcula o score dos leads ativos automaticamente (LeadScoringEngine). Best-effort."""
    from sqlalchemy import select

    async def _inner(session):
        from modules.crm.models.lead import Lead
        from modules.crm.services.lead_service import LeadScoringEngine

        eng = LeadScoringEngine()
        leads = (await session.execute(select(Lead).where(Lead.is_active.is_(True)).limit(500))).scalars().all()
        n = 0
        for ld in leads:
            try:
                score, prob = eng.calculate_score(ld)
                if ld.score != score or float(ld.probability or 0) != float(prob):
                    ld.score = score
                    ld.probability = prob
                    n += 1
            except Exception:  # noqa: BLE001
                continue
        await session.commit()
        return {"leads": len(leads), "atualizados": n}

    try:
        return _run_async(_inner)
    except Exception as e:  # noqa: BLE001
        logger.warning("crm.score_leads falhou: %s", e)
        return {"error": str(e)}


@app.task(name="crm.radar_frios", bind=True, max_retries=1)
def radar_frios(self):
    """Avisa o Jordan dos leads que esfriaram (sem auto-enviar ao cliente). 1x/dia. Best-effort."""

    async def _inner(session):
        from modules.crm.services import orchestration as O

        frios = await O.leads_frios(session)
        if not frios:
            return {"frios": 0}
        top = frios[:8]
        linhas = "\n".join(
            f"• {f['cliente_nome'] if 'cliente_nome' in f else f['name']} ({f['dias_parado']}d, origem {f['origem']})"
            for f in top
        )
        extra = f"\n…e mais {len(frios) - len(top)}." if len(frios) > len(top) else ""
        await O.notify_owner(
            f"🧊 *Leads esfriando* ({len(frios)})\n{linhas}{extra}\n\n"
            f"Quer que eu reative algum? Me diz 'reativa o [nome]' que eu mando um toque."
        )
        return {"frios": len(frios)}

    try:
        return _run_async(_inner)
    except Exception as e:  # noqa: BLE001
        logger.warning("crm.radar_frios falhou: %s", e)
        return {"error": str(e)}


@app.task(name="crm.heartbeat_ciclo", bind=True, max_retries=1)
def heartbeat_ciclo(self):
    """Checa a saúde do ciclo (WhatsApp/agente/webhook). Avisa o Jordan SÓ na transição ok→caiu
    e quando volta ao normal (sem spam horário). Best-effort."""

    async def _inner(session):
        from modules.crm.services import orchestration as O

        diag = await O.diagnostico_ciclo(session)
        agora_ok = bool(diag["saudavel"])
        last = await O.get_state(session, "heartbeat_status")
        novo = "ok" if agora_ok else "down"
        # Só ALERTA em transição REAL. Na 1ª execução (last=None) apenas registra — não manda
        # "normalizado" do nada. Avisa quando CAI (ok->down) e quando VOLTA (down->ok).
        alertou = False
        if last is not None and last != novo:
            if novo == "down":
                quebrados = [k for k, v in diag["itens"].items() if not v.get("ok")]
                await O.notify_owner(
                    f"🔴 *Alerta do ciclo* — algo caiu: {', '.join(quebrados)}.\n"
                    f"Os follow-ups e o atendimento do José Luís podem estar parados. Detalhe: "
                    f"{diag['itens']}"
                )
            else:
                await O.notify_owner("🟢 *Ciclo normalizado* — WhatsApp e agente de volta ao ar. ✅")
            alertou = True
        if last != novo:
            await O.set_state(session, "heartbeat_status", novo)
        return {"saudavel": agora_ok, "alertou": alertou}

    try:
        return _run_async(_inner)
    except Exception as e:  # noqa: BLE001
        logger.warning("crm.heartbeat_ciclo falhou: %s", e)
        return {"error": str(e)}


@app.task(name="crm.auto_acompanhar", bind=True, max_retries=1)
def auto_acompanhar(self):
    """Toda proposta ENVIADA (status='sent') sem estado de negociação ganha acompanhamento
    automático (entra no painel/pendentes do José Luís). Nada escapa do radar. Best-effort."""
    from sqlalchemy import text as _t

    async def _inner(session):
        from modules.crm.services import orchestration as O
        from modules.crm.services.phone import canonical_br

        rows = (
            (
                await session.execute(
                    _t("""
            SELECT p.id, p.client_name, p.client_phone, p.opportunity_id, p.sent_at, p.created_at
            FROM proposals p
            LEFT JOIN crm_negociacao_state n ON n.proposal_id = p.id
            WHERE p.is_active AND p.status='sent' AND n.id IS NULL
            LIMIT 200""")
                )
            )
            .mappings()
            .all()
        )
        n = 0
        for p in rows:
            await O.upsert_negociacao(
                session,
                proposal_id=str(p["id"]),
                deal_id=str(p["opportunity_id"]) if p["opportunity_id"] else None,
                phone_canonical=canonical_br(p["client_phone"]),
                cliente_nome=p["client_name"],
                proposta_enviada_em=(p["sent_at"] or p["created_at"]),
                responsavel="jose_luis",
            )
            n += 1
        return {"acompanhamentos_criados": n}

    try:
        return _run_async(_inner)
    except Exception as e:  # noqa: BLE001
        logger.warning("crm.auto_acompanhar falhou: %s", e)
        return {"error": str(e)}


@app.task(name="crm.enviar_followups_agendados", bind=True, max_retries=1)
def enviar_followups_agendados(self):
    """Envia os follow-ups que ficaram AGENDADOS (pedidos fora do horário). Só age em horário
    comercial (seg-sex 8-18h Manaus). Respeita opt-out. Best-effort."""
    from sqlalchemy import text as _t

    async def _inner(session):
        from modules.crm.services import followups as F

        if not F.within_business_hours():
            return {"skip": "fora do horário comercial"}
        rows = (
            (
                await session.execute(
                    _t("""
            SELECT id, phone_e164, phone_canonical, mensagem, proposal_id, deal_id
            FROM crm_followups WHERE status='agendado' AND canal='whatsapp' AND phone_e164 IS NOT NULL
            ORDER BY created_at ASC LIMIT 50""")
                )
            )
            .mappings()
            .all()
        )
        from modules.integrations.connectors.whatsapp.service import whatsapp_service

        enviados = 0
        for r in rows:
            if await F.is_opted_out(session, r["phone_canonical"] or ""):
                await session.execute(
                    _t("UPDATE crm_followups SET status='cancelado', detalhe='opt-out', updated_at=now() WHERE id=:id"),
                    {"id": r["id"]},
                )
                continue
            res = await whatsapp_service.send_custom(r["phone_e164"], r["mensagem"] or "")
            ok = res.get("status") == "sent"
            await session.execute(
                _t(
                    "UPDATE crm_followups SET status=:s, enviado_em=CASE WHEN :ok THEN now() ELSE enviado_em END, "
                    "chatwoot_conversation_id=:c, updated_at=now() WHERE id=:id"
                ),
                {"s": ("enviado" if ok else "erro"), "ok": ok, "c": res.get("conversation_id"), "id": r["id"]},
            )
            if ok:
                enviados += 1
        await session.commit()
        if enviados:
            from modules.crm.services import orchestration as O

            await O.notify_owner(f"📨 {enviados} follow-up(s) agendado(s) foram enviados agora (janela comercial).")
        return {"enviados": enviados, "candidatos": len(rows)}

    try:
        return _run_async(_inner)
    except Exception as e:  # noqa: BLE001
        logger.warning("crm.enviar_followups_agendados falhou: %s", e)
        return {"error": str(e)}
