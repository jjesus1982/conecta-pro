"""
Tasks Celery do agente José Luís (WhatsApp).

whatsapp.followup_conversas — encontra conversas que ESFRIARAM (cliente sumiu
apos a ultima resposta) e envia ao Jordan, via Telegram, a lista com um rascunho
de retomada por conversa. NADA e enviado ao cliente automaticamente — o aval e
humano (Jordan/equipe decide e manda).
"""

import logging
import os

from celery_app import app

logger = logging.getLogger(__name__)

# Janela de "esfriou": cliente sem responder ha mais de 24h e menos de 7 dias.
FOLLOWUP_MIN_HORAS = 24
FOLLOWUP_MAX_DIAS = 7


def _run_async(coro):
    """Helper para rodar corrotinas async nas tasks Celery (engine propria)."""
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    database_url = os.getenv("DATABASE_URL", "").replace("postgresql://", "postgresql+asyncpg://")

    async def _inner():
        engine = create_async_engine(database_url, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with async_session() as session:
                return await coro(session)
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


def _telegram_send(text_msg: str) -> bool:
    """Entrega a lista ao Jordan via Telegram (credenciais do env). Best-effort."""
    token = os.getenv("MONITOR_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or ""
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.warning("followup_conversas: TELEGRAM ausente — lista NAO enviada (so log)")
        return False
    try:
        import requests  # noqa: PLC0415

        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text_msg[:4000], "parse_mode": "HTML"},
            timeout=15,
        )
        return r.status_code == 200
    except Exception as e:  # noqa: BLE001
        logger.error("followup_conversas: telegram falhou: %s", e)
        return False


async def _coletar_conversas_frias(session):
    """Conversas cuja ULTIMA mensagem e 'out' (respondida) e o cliente sumiu 24h-7d."""
    from sqlalchemy import text

    rows = (
        await session.execute(
            text(
                """
                WITH ultima AS (
                    SELECT DISTINCT ON (chatwoot_conversation_id)
                        chatwoot_conversation_id AS conv,
                        direction, content, created_at, phone_canonical, lead_id
                    FROM cwi_message_log
                    WHERE direction IN ('in','out') AND chatwoot_conversation_id IS NOT NULL
                    ORDER BY chatwoot_conversation_id, created_at DESC
                )
                SELECT u.conv, u.phone_canonical, u.created_at,
                       coalesce(l.name, 'Contato ' || coalesce(u.phone_canonical,'?')) AS nome,
                       coalesce(l.company, '')                                        AS empresa,
                       coalesce(l.status, '')                                         AS lead_status,
                       (SELECT i.content FROM cwi_message_log i
                         WHERE i.chatwoot_conversation_id = u.conv AND i.direction='in'
                           AND i.content IS NOT NULL AND i.content <> ''
                         ORDER BY i.created_at DESC LIMIT 1)                          AS ultimo_assunto
                FROM ultima u
                LEFT JOIN leads l ON l.id = (
                    SELECT m.lead_id FROM cwi_message_log m
                    WHERE m.chatwoot_conversation_id = u.conv AND m.lead_id IS NOT NULL
                    ORDER BY m.created_at DESC LIMIT 1
                )
                WHERE u.direction = 'out'
                  AND u.created_at < now() - interval '24 hours'
                  AND u.created_at > now() - interval '7 days'
                  AND coalesce(l.status,'') NOT IN ('converted','disqualified')
                ORDER BY u.created_at ASC
                LIMIT 15
                """
            )
        )
    ).fetchall()
    return rows


def _rascunho_followup(nome: str | None, dias: int, tema: str | None) -> str:
    """Rascunho de retomada CONTEXTUAL por tempo parado (multi-toque). Tom objetivo, sem puxa-saco."""
    primeiro = ""
    if nome and not nome.startswith("Contato"):
        primeiro = ", " + nome.split()[0]
    assunto = f" sobre {tema}" if tema and tema not in ("—", "") else ""
    if dias <= 2:
        # Toque 1 — lembrete leve, retomar de onde parou
        return (f"Oi{primeiro}! Aqui é o José Luís, da Conecta Mais. "
                f"Ficamos no meio da nossa conversa{assunto} — quer que eu siga te ajudando por aqui?")
    if dias <= 6:
        # Toque 2 — oferecer a visita gratuita (avanço)
        return (f"Oi{primeiro}, tudo bem? Aqui é o José Luís, da Conecta Mais. "
                f"Pra te ajudar a decidir{assunto}, posso encaminhar uma visita técnica gratuita e sem "
                f"compromisso da nossa equipe. Quer que eu agende?")
    # Toque 3+ — último toque, deixa a porta aberta sem insistir
    return (f"Oi{primeiro}! Aqui é o José Luís, da Conecta Mais. Vou deixar seu contato registrado "
            f"por aqui — quando quiser retomar{assunto}, é só me chamar que sigo à disposição. 👍")


@app.task(name="whatsapp.followup_conversas", bind=True, max_retries=1)
def followup_conversas(self):  # noqa: ARG001
    """Diario: lista conversas frias + rascunho CONTEXTUAL de retomada -> Telegram do Jordan."""
    try:
        rows = _run_async(_coletar_conversas_frias)
    except Exception as e:  # noqa: BLE001
        logger.error("followup_conversas: coleta falhou: %s", e)
        return {"ok": False}

    if not rows:
        _telegram_send("🤖 <b>José Luís — follow-up diário</b>\n\nNenhuma conversa esfriada nas últimas 24h–7d. 👌")
        return {"ok": True, "frias": 0}

    linhas = ["🤖 <b>José Luís — conversas que esfriaram</b> (aguardando SEU aval; nada foi enviado)\n"]
    for conv, phone, quando, nome, empresa, _status, assunto in rows:
        dias = max(1, (__import__("datetime").datetime.now(quando.tzinfo) - quando).days)
        quem = f"{nome}" + (f" ({empresa})" if empresa else "")
        tema = (assunto or "—").replace("\n", " ")[:90]
        toque = "1 (lembrete)" if dias <= 2 else ("2 (oferta de visita)" if dias <= 6 else "3 (último toque)")
        rascunho = _rascunho_followup(nome, dias, tema)
        linhas.append(
            f"• <b>{quem}</b> — conv #{conv}, parado há {dias}d · toque {toque}\n"
            f"  Último assunto: {tema}\n"
            f"  📋 Sugestão p/ retomar: <i>{rascunho}</i>\n"
        )
    linhas.append("\nPara retomar: responda na conversa do Chatwoot (a sugestão acima é só um rascunho).")
    _telegram_send("\n".join(linhas))
    logger.info("followup_conversas: %s conversas frias notificadas", len(rows))
    return {"ok": True, "frias": len(rows)}


# ======================= QUALITY MONITORING / LOOP DE APRENDIZADO =======================

_RUBRICA_AUDITORIA = (
    "Você audita a QUALIDADE do atendente José Luís (WhatsApp de uma empresa de portaria/"
    "segurança em Manaus). Na conversa, 'in:' = cliente e 'out:' = José Luís. Avalie SÓ as "
    "respostas do José Luís. Devolva APENAS um JSON válido (sem texto fora dele) com as chaves:\n"
    '{"nota": 0-10, "puxa_saco": true/false, "objetivo": true/false, "pediu_cnpj": true/false, '
    '"conduziu_visita": true/false, "vazou_preco": true/false, '
    '"problema": "frase curta do principal problema (ou vazio)", '
    '"destaque": "frase curta do que fez bem (ou vazio)"}\n'
    "Bom atendimento: OBJETIVO e curto, sem bajulação (não abrir com 'Perfeito!/Show!/Boa!/"
    "Maravilha!' a cada mensagem nem agradecer toda hora), pede o CNPJ cedo, conduz à visita, "
    "tom natural e humano, e NUNCA cita preço/valor. Penalize: verbosidade e re-resumo, "
    "puxa-saquismo, interrogatório/excesso de perguntas, e vazamento de preço (gravíssimo)."
)


def _nota(r: dict) -> float:
    """Nota do auditor coagida com segurança (LLM pode devolver não-numérico)."""
    try:
        return float(r.get("nota") or 0)
    except (TypeError, ValueError):
        return 0.0


def _flag(r: dict, key: str) -> bool:
    """Coage flag do auditor p/ bool (LLM pode devolver 'true'/'false'/'sim'/1)."""
    v = r.get(key)
    if isinstance(v, str):
        return v.strip().lower() in ("true", "sim", "yes", "1", "verdadeiro")
    return bool(v)


async def _auditar_conversas(session, horas: int = 24, limite: int = 15) -> list[dict]:
    """Coleta conversas recentes do agente e audita cada uma via LLM. Best-effort."""
    from sqlalchemy import text  # noqa: PLC0415

    rows = (
        await session.execute(
            text(
                "SELECT chatwoot_conversation_id AS conv, max(phone_canonical) AS phone, "
                "  string_agg(direction || ': ' || left(content, 350), E'\\n' ORDER BY created_at) AS transcript "
                "FROM cwi_message_log "
                "WHERE direction IN ('in','out') AND content IS NOT NULL AND content <> '' "
                "  AND created_at > now() - make_interval(hours => :h) "
                "GROUP BY chatwoot_conversation_id "
                "HAVING count(*) FILTER (WHERE direction='out') >= 2 "
                "ORDER BY max(created_at) DESC LIMIT :n"
            ),
            {"h": horas, "n": limite},
        )
    ).fetchall()
    if not rows:
        return []

    import json as _json  # noqa: PLC0415

    from openai import AsyncOpenAI  # noqa: PLC0415

    client = AsyncOpenAI(timeout=float(os.getenv("AGENT_OPENAI_TIMEOUT", "90")))
    model = os.getenv("AGENT_AUDIT_MODEL", "gpt-4o-mini")
    # kwargs compatíveis com a família do modelo (gpt-5/o-series não aceitam temperature
    # nem max_tokens — usam max_completion_tokens). Evita quebra silenciosa se trocar o modelo.
    if model.startswith(("gpt-5", "o1", "o3", "o4")):
        _akw = {"max_completion_tokens": 300}
    else:
        _akw = {"max_tokens": 300, "temperature": 0}
    out = []
    for conv, phone, transcript in rows:
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _RUBRICA_AUDITORIA},
                    {"role": "user", "content": f"CONVERSA (conv #{conv}):\n{transcript[:6000]}"},
                ],
                response_format={"type": "json_object"},
                **_akw,
            )
            data = _json.loads(resp.choices[0].message.content or "{}")
            data["conv"] = conv
            data["phone"] = phone
            out.append(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("auditor: falha conv=%s: %s", conv, exc)

    # LOOP DE APRENDIZADO: promove conversas EXCELENTES (nota>=8, sem vazar preço) a 'gold'
    # -> viram exemplos few-shot que o José Luís passa a espelhar. Idempotente.
    from sqlalchemy import text as _text  # noqa: PLC0415

    promovidas = 0
    for r in out:
        # Gold (rígido): nota alta, SEM vazar preço, E com avanço real (pediu CNPJ ou
        # conduziu à visita) — evita conversa "simpática mas vazia" virar exemplo.
        if _nota(r) >= 8 and not _flag(r, "vazou_preco") and (_flag(r, "conduziu_visita") or _flag(r, "pediu_cnpj")):
            try:
                res = await session.execute(
                    _text(
                        "INSERT INTO cwi_message_log (direction, phone_canonical, chatwoot_conversation_id, content, created_at) "
                        "SELECT 'gld', :ph, :conv, :nota, now() WHERE NOT EXISTS "
                        "(SELECT 1 FROM cwi_message_log g WHERE g.direction='gld' AND g.chatwoot_conversation_id=:conv)"
                    ),
                    {"ph": r.get("phone"), "conv": r["conv"], "nota": f"gold:{str(r.get('destaque') or '')[:200]}"},
                )
                promovidas += res.rowcount or 0
            except Exception as exc:  # noqa: BLE001
                logger.warning("auditor: falha ao promover gold conv=%s: %s", r.get("conv"), exc)
    if promovidas:
        await session.commit()
        logger.info("auditor: %s conversas promovidas a gold (few-shot)", promovidas)
    return out


@app.task(name="whatsapp.auditar_qualidade", bind=True, max_retries=1)
def auditar_qualidade(self):  # noqa: ARG001
    """Diario: audita a qualidade das conversas do José Luís e manda digest no Telegram."""
    try:
        results = _run_async(_auditar_conversas)
    except Exception as e:  # noqa: BLE001
        logger.error("auditar_qualidade: falha: %s", e)
        return {"ok": False}

    if not results:
        _telegram_send("🔎 <b>Auditoria José Luís</b>\n\nNenhuma conversa com atendimento nas últimas 24h.")
        return {"ok": True, "n": 0}

    n = len(results)
    notas = [_nota(r) for r in results]
    media = sum(notas) / n if n else 0
    pediu_cnpj = sum(1 for r in results if _flag(r, "pediu_cnpj"))
    conduziu = sum(1 for r in results if _flag(r, "conduziu_visita"))
    vazou = [r for r in results if _flag(r, "vazou_preco")]
    problemas = sorted((r for r in results if r.get("problema") or _flag(r, "puxa_saco") or _nota(r) < 7),
                       key=_nota)
    destaques = sorted((r for r in results if r.get("destaque") and _nota(r) >= 8),
                       key=lambda r: -_nota(r))

    L = [f"🔎 <b>Auditoria José Luís</b> (24h)",
         f"📊 {n} conversas · nota média <b>{media:.1f}/10</b>",
         f"📈 Pediu CNPJ: {pediu_cnpj}/{n} · Conduziu à visita: {conduziu}/{n} · Vazou preço: {len(vazou)}/{n}"]
    if vazou:
        L.append("\n🚨 <b>VAZAMENTO DE PREÇO</b> (grave): " + ", ".join(f"#{r['conv']}" for r in vazou))
    if problemas:
        L.append("\n⚠️ <b>Pra melhorar:</b>")
        for r in problemas[:5]:
            tag = "puxa-saco" if _flag(r, "puxa_saco") else (r.get("problema") or "abaixo do padrão")
            L.append(f"• #{r['conv']} (nota {_nota(r):.0f}): {str(tag)[:90]}")
    if destaques:
        L.append("\n✅ <b>Destaques:</b>")
        for r in destaques[:3]:
            L.append(f"• #{r['conv']} (nota {_nota(r):.0f}): {str(r.get('destaque'))[:90]}")
    gold_n = sum(1 for r in results if _nota(r) >= 8 and not _flag(r, "vazou_preco")
                 and (_flag(r, "conduziu_visita") or _flag(r, "pediu_cnpj")))
    if gold_n:
        L.append(f"\n🏆 {gold_n} conversa(s) viraram exemplo (gold) — o José Luís vai espelhar daqui pra frente.")
    _telegram_send("\n".join(L))
    logger.info("auditar_qualidade: %s conversas auditadas, media %.1f", n, media)
    return {"ok": True, "n": n, "media": round(media, 1)}


# ============================================================================
# whatsapp.notificar_status_os — ATUALIZAÇÕES PROATIVAS DE OS (Campo -> WhatsApp)
# Quando a equipe muda o status da OS no módulo Campo do Conecta PRO, o cliente
# recebe a atualização automaticamente no WhatsApp (reduz ansiedade — as 5 respostas).
# Lê ordens_servico (tabela do Campo) das OS abertas pelo José Luís (ticket_sistema=
# 'whatsapp'); compara status atual x last_notified_status (no extra_metadata) e avisa.
# ============================================================================

# StatusOS -> mensagem amigável ao cliente. Statuses internos (rascunho/aberta) não
# notificam (só avançam o marcador). {num} = número da OS; {quando} = data se houver.
_OS_STATUS_MSG = {
    "agendada": "✅ Boa notícia! Sua OS {num} foi agendada{quando}. Nossa equipe técnica vai até você. Qualquer coisa, é só me chamar.",
    "reagendada": "📅 Sua OS {num} foi reagendada{quando}. Te confirmo o novo horário por aqui.",
    "em_deslocamento": "🚗 Sua OS {num}: nosso técnico já está a caminho! Em breve chega aí.",
    "em_andamento": "🔧 Sua OS {num} está em atendimento agora — a equipe está trabalhando nisso.",
    "aguardando_peca": "⏳ Sua OS {num} está aguardando uma peça pra concluir o reparo. Assim que chegar, retomamos e te aviso.",
    "aguardando_cliente": "⏳ Sua OS {num} está aguardando um retorno seu pra seguir. Me avisa quando puder, por favor.",
    "pausada": "⏸️ Sua OS {num} foi pausada temporariamente. Te aviso assim que for retomada.",
    "concluida": "✅ Sua OS {num} foi concluída! Espero que esteja tudo certo agora. Qualquer coisa, conte comigo. 😊",
    "cancelada": "Sua OS {num} foi cancelada. Se precisar, é só me chamar por aqui que eu reabro.",
}


@app.task(name="whatsapp.notificar_status_os", bind=True, max_retries=1)
def notificar_status_os(self):  # noqa: ARG001
    """Varre as OS de origem WhatsApp e avisa o cliente quando o status mudou no Campo."""
    if os.getenv("AGENT_OS_UPDATES_ENABLED", "true").strip().lower() not in ("true", "1", "sim", "yes", "s"):
        return {"status": "disabled"}
    try:
        return _run_async(_notificar_status_os)
    except Exception as e:  # noqa: BLE001
        logger.error("notificar_status_os: %s", e)
        return {"status": "error", "error": str(e)}


async def _notificar_status_os(session):
    from sqlalchemy import text  # noqa: PLC0415

    from modules.integrations.connectors.whatsapp.agent_service import _post_public_reply  # noqa: PLC0415

    # ordens_servico grava o status como NOME do enum (MAIÚSCULO, ex.: 'AGENDADA'); o
    # marcador last_notified_status segue o mesmo formato. O mapa de mensagens é por
    # valor minúsculo, então normalizamos no lookup.
    rows = (
        await session.execute(
            text(
                "SELECT id, numero, status, data_agendada, "
                "extra_metadata->>'conversation_id' AS conv, "
                "coalesce(extra_metadata->>'last_notified_status','ABERTA') AS last "
                "FROM ordens_servico "
                "WHERE ticket_sistema='whatsapp' AND ticket_origem_id IS NOT NULL "
                "AND coalesce(is_active, true) = true "
                "AND status <> coalesce(extra_metadata->>'last_notified_status','ABERTA')"
            )
        )
    ).fetchall()

    async def _marcar(os_id, status):
        # avança o marcador e ZERA o contador de falhas
        await session.execute(
            text(
                "UPDATE ordens_servico SET extra_metadata = jsonb_set(jsonb_set("
                "coalesce(extra_metadata,'{}'::jsonb), '{last_notified_status}', to_jsonb(:s::text)), "
                "'{notify_fail_count}', '0'::jsonb) WHERE id = :id"
            ),
            {"s": status, "id": str(os_id)},
        )

    async def _inc_fail(os_id):
        row = (
            await session.execute(
                text(
                    "UPDATE ordens_servico SET extra_metadata = jsonb_set("
                    "coalesce(extra_metadata,'{}'::jsonb), '{notify_fail_count}', "
                    "to_jsonb(coalesce((extra_metadata->>'notify_fail_count')::int,0) + 1)) "
                    "WHERE id = :id RETURNING (extra_metadata->>'notify_fail_count')::int"
                ),
                {"id": str(os_id)},
            )
        ).first()
        return (row[0] if row and row[0] is not None else 1)

    # Após MAX_FAILS tentativas sem sucesso, desiste da transição (avança o marcador) —
    # evita reenvio infinito a cada 5min e mensagem indevida se a conversa for reaproveitada.
    MAX_FAILS = 6
    enviados = 0
    for r in rows:
        os_id, numero, status, data_ag, conv, _last = r
        msg_tpl = _OS_STATUS_MSG.get(str(status).lower())
        if not msg_tpl or not conv:
            # status interno (rascunho/aberta) ou sem conversa -> só avança o marcador
            await _marcar(os_id, status)
            continue
        try:
            quando = f" para {data_ag.strftime('%d/%m')}" if data_ag else ""
        except Exception:  # noqa: BLE001
            quando = ""
        msg = msg_tpl.format(num=numero, quando=quando)
        ok = await _post_public_reply(int(conv), msg)
        if ok:
            await _marcar(os_id, status)
            enviados += 1
            logger.info("notificar_status_os: OS %s -> %s avisado conv=%s", numero, status, conv)
        else:
            fails = await _inc_fail(os_id)
            if fails >= MAX_FAILS:
                await _marcar(os_id, status)  # desiste desta transição
                logger.warning("notificar_status_os: OS %s -> %s DESISTIU após %s falhas de envio", numero, status, fails)
    await session.commit()
    return {"status": "ok", "notificados": enviados, "candidatos": len(rows)}
