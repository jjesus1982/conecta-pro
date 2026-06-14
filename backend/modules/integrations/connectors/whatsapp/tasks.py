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

    client = AsyncOpenAI()
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
        if _nota(r) >= 8 and not r.get("vazou_preco") and (r.get("conduziu_visita") or r.get("pediu_cnpj")):
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
    pediu_cnpj = sum(1 for r in results if r.get("pediu_cnpj"))
    conduziu = sum(1 for r in results if r.get("conduziu_visita"))
    vazou = [r for r in results if r.get("vazou_preco")]
    problemas = sorted((r for r in results if r.get("problema") or r.get("puxa_saco") or _nota(r) < 7),
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
            tag = "puxa-saco" if r.get("puxa_saco") else (r.get("problema") or "abaixo do padrão")
            L.append(f"• #{r['conv']} (nota {_nota(r):.0f}): {str(tag)[:90]}")
    if destaques:
        L.append("\n✅ <b>Destaques:</b>")
        for r in destaques[:3]:
            L.append(f"• #{r['conv']} (nota {_nota(r):.0f}): {str(r.get('destaque'))[:90]}")
    gold_n = sum(1 for r in results if _nota(r) >= 8 and not r.get("vazou_preco")
                 and (r.get("conduziu_visita") or r.get("pediu_cnpj")))
    if gold_n:
        L.append(f"\n🏆 {gold_n} conversa(s) viraram exemplo (gold) — o José Luís vai espelhar daqui pra frente.")
    _telegram_send("\n".join(L))
    logger.info("auditar_qualidade: %s conversas auditadas, media %.1f", n, media)
    return {"ok": True, "n": n, "media": round(media, 1)}
