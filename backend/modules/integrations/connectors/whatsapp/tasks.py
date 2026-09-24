"""
Tasks Celery do agente José Luís (WhatsApp).

whatsapp.followup_conversas — encontra conversas que ESFRIARAM (cliente sumiu
apos a ultima resposta) e entrega no SINO a lista com um rascunho
de retomada por conversa. NADA e enviado ao cliente automaticamente — o aval e
humano (Jordan/equipe decide e manda).
"""

from core.llm_client import modelo_barato, novo_cliente
import contextlib
import logging
import os
import re
from datetime import UTC, date, datetime

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


async def _entregar_no_sino(
    session, *, title: str, body: str, correlation_id: str, severidade: str = "atencao"
) -> int:
    """Materializa o alerta no sino (communication_notifications) p/ os roles comerciais.

    Substitui o antigo envio por bot externo: canal banido na casa E degradava
    mal — sem token no worker, só logava warning e a lista NÃO chegava a ninguém,
    silêncio que parece funcionamento. Aqui o RBAC é resolvido server-side e a
    entrega é auditável. Devolve quantos destinatários receberam (0 = ninguém).
    """
    from modules.notifications.proativo.entrega import (  # noqa: PLC0415
        enviar_individual,
        resolver_usuarios_por_roles,
    )

    dest = await resolver_usuarios_por_roles(session, ("admin",))
    if not dest:
        logger.warning("%s: nenhum destinatario p/ os roles — alerta NAO entregue", correlation_id)
        return 0
    await enviar_individual(
        session,
        user_ids=dest,
        title=title[:200],
        body=body[:4000],
        familia="comercial",
        severidade=severidade,
        correlation_id=correlation_id,
        action_url="/redesign/crm",
    )
    await session.commit()
    return len(dest)


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
    """Diario: conversas frias + rascunho de retomada -> SINO (communication_notifications)."""
    try:
        rows = _run_async(_coletar_conversas_frias)
    except Exception as e:  # noqa: BLE001
        logger.error("followup_conversas: coleta falhou: %s", e)
        return {"ok": False}

    if not rows:
        # Silêncio honesto: nada esfriou -> ninguém é notificado. Mandar "nada hoje"
        # todos os dias é ruído que treina o time a ignorar o sino.
        return {"ok": True, "frias": 0}

    linhas = []
    for conv, phone, quando, nome, empresa, _status, assunto in rows:  # noqa: B007
        dias = max(1, (__import__("datetime").datetime.now(quando.tzinfo) - quando).days)
        quem = f"{nome}" + (f" ({empresa})" if empresa else "")
        tema = (assunto or "—").replace("\n", " ")[:90]
        toque = "1 (lembrete)" if dias <= 2 else ("2 (oferta de visita)" if dias <= 6 else "3 (último toque)")
        rascunho = _rascunho_followup(nome, dias, tema)
        linhas.append(
            f"• {quem} — conv #{conv}, parado há {dias}d · toque {toque}\n"
            f"  Último assunto: {tema}\n"
            f"  Sugestão p/ retomar: {rascunho}\n"
        )
    corpo = "\n".join(linhas) + "\nNada foi enviado ao cliente — a sugestão é rascunho."
    dest = _run_async(
        lambda s: _entregar_no_sino(
            s,
            title=f"{len(rows)} conversa(s) esfriaram — retomar?",
            body=corpo,
            correlation_id=f"followup_frio:{date.today().isoformat()}",
        )
    )
    logger.info("followup_conversas: %s conversas frias -> %s destinatarios", len(rows), dest)
    return {"ok": True, "frias": len(rows), "destinatarios": dest}


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

    client = novo_cliente(origem="whatsapp.task", timeout=float(os.getenv("AGENT_OPENAI_TIMEOUT", "90")))
    from core.llm_client import modelo_barato  # noqa: PLC0415

    # nome de modelo fixo quebra na troca de provedor: "gpt-4o-mini" devolve HTTP 400 na
    # DeepSeek, e esta é uma rotina de FUNDO — ninguém veria falhar
    model = os.getenv("AGENT_AUDIT_MODEL") or modelo_barato()
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
    """Diario: audita a qualidade das conversas do José Luís e entrega o digest no SINO."""
    try:
        results = _run_async(_auditar_conversas)
    except Exception as e:  # noqa: BLE001
        logger.error("auditar_qualidade: falha: %s", e)
        return {"ok": False}

    if not results:
        # Silêncio honesto, igual ao follow-up: sem atendimento não há o que auditar.
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
    corpo = re.sub(r"</?[a-z]+>", "", "\n".join(L))  # tags de markup antigas; o sino é texto puro
    dest = _run_async(
        lambda s: _entregar_no_sino(
            s,
            title=f"Auditoria José Luís — {n} conversa(s), média {media:.1f}",
            body=corpo,
            correlation_id=f"auditoria_jl:{date.today().isoformat()}",
            severidade="atencao" if media < 7 else "info",
        )
    )
    logger.info("auditar_qualidade: %s conversas, media %.1f -> %s destinatarios", n, media, dest)
    return {"ok": True, "n": n, "media": round(media, 1), "destinatarios": dest}


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
        try:
            conv_int = int(conv)
        except (ValueError, TypeError):
            # conversation_id corrompido -> não dá pra avisar; avança o marcador e segue
            # (nunca deixa um dado ruim abortar o lote inteiro / re-notificar os já enviados).
            await _marcar(os_id, status)
            continue
        msg = msg_tpl.format(num=numero, quando=quando)
        ok = await _post_public_reply(conv_int, msg)
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


# ═════════ P0 · A RESPOSTA DO AGENTE PRECISA SOBREVIVER AO DEPLOY ═════════
# 28/08/2026 — o Jordan mandou SEIS mensagens e um PDF às 16:14 e não recebeu NADA. Nem
# erro, nem "processando": silêncio. Medido em `cwi_message_log`: seis `in`, zero `out`,
# exatamente na janela em que o bake 4 recriava os workers. Repetiu às 16:35, no bake 5.
#
# ⭐ A CAUSA: o webhook agendava a resposta com `BackgroundTasks` do FastAPI —
# in-process, sem fila, sem retry — e devolvia 200 ao Chatwoot ANTES de a tarefa rodar.
# O deploy trocava o container, a tarefa morria sem log, e o Chatwoot nunca reenviava
# porque já tinha recebido 200. Fizemos 5 bakes nesse dia: cinco janelas de silêncio,
# assando consertos NO AGENTE enquanto ele tentava usar o agente.
#
# Aqui a resposta vira tarefa DURÁVEL: fica no Redis, sobrevive à troca de container e é
# reentregue se o worker morrer no meio (`acks_late`). Fila `webhooks` — MEDIDA antes de
# escolher: tem consumidor vivo no worker `integrations`, prioridade 8. Fila sem
# consumidor é o mesmo silêncio com outro nome, e já nos custou o `ged`.
@app.task(name="whatsapp.processar_incoming", bind=True, max_retries=2,
          acks_late=True, default_retry_delay=20)
def processar_incoming_task(self, conversation_id: int, phone_canonical: str | None = None):
    from modules.integrations.connectors.whatsapp import agent_service

    try:
        _run_async(lambda _s: agent_service.processar_incoming(conversation_id, phone_canonical))
        return {"ok": True, "conversation_id": conversation_id}
    except Exception as e:  # noqa: BLE001
        logger.error("processar_incoming conv=%s falhou: %s", conversation_id, e)
        # Retry de verdade: sem ele, "durável" seria só uma palavra diferente para o mesmo
        # silêncio. Estourou o retry -> a varredura abaixo é a última rede.
        raise self.retry(exc=e) from e


#: Janela da varredura. Abaixo de 3 min ainda pode ser resposta em curso (o laço leva ~5s,
#: mas o teto do caminho é 90s); acima de 90 min responder vira estranho — o Jordan já
#: seguiu a vida. Entre os dois, atraso é melhor que silêncio.
_VARRE_MIN, _VARRE_MAX = 3, 90


@app.task(name="whatsapp.varrer_sem_resposta", bind=True, max_retries=1)
def varrer_sem_resposta(self):  # noqa: ARG001
    """Suspenders: acha conversa cuja ÚLTIMA mensagem é do cliente e sem resposta, e reprocessa.

    Mesmo com fila durável a mensagem some se o worker morrer antes do ack — e some em
    silêncio, que é a parte cara. Esta varredura transforma "sumiu" em "atrasou".

    Reprocessa UMA vez por conversa, não uma por mensagem: `processar_incoming` já lê a
    conversa inteira, então seis mensagens seguidas viram uma resposta, não seis.
    """
    from sqlalchemy import text as _t

    async def _pendentes(session):
        r = await session.execute(_t("""
            SELECT m.chatwoot_conversation_id AS conv,
                   max(m.phone_canonical) AS fone,
                   count(*) AS n
            FROM cwi_message_log m
            WHERE m.direction = 'in'
              AND m.created_at BETWEEN now() - (:mx * interval '1 minute')
                                   AND now() - (:mn * interval '1 minute')
              AND NOT EXISTS (
                    SELECT 1 FROM cwi_message_log o
                    WHERE o.chatwoot_conversation_id = m.chatwoot_conversation_id
                      AND o.direction IN ('out', 'drf')
                      AND o.created_at > m.created_at)
              -- ⭐ 24/09/2026: GRUPO EM OBSERVAÇÃO NÃO É "SEM RESPOSTA", é silêncio por
              -- decisão do dono. Sem esta linha, toda mensagem de grupo virava candidata
              -- PERMANENTE desta varredura durante os 90 min da janela: um WARNING
              -- "conversa X SEM resposta" por rodada, para sempre, sobre algo que está
              -- certo. Alarme que soa sempre é alarme que ninguém lê.
              --
              -- ⚠️ A parede de verdade mora em `processar_incoming` (o ponto por onde esta
              -- varredura e o webhook passam). Esta linha não é a parede — é esta task
              -- parando de MENTIR no log e de gastar fila com trabalho que será recusado.
              -- ⚠️ EXCLUI GRUPO EM QUALQUER MODO, e não só em observação (24/09/2026,
              -- quando o Jordan liberou a conversa nos grupos). Num grupo, "mensagem sem
              -- resposta" é o NORMAL: o prompt diz "silêncio é resposta válida e é o padrão",
              -- porque conversa entre colegas, bom dia e piada não pedem resposta do agente.
              -- Com a condição antiga (`modo <> 'falar'`), virar o modo para `falar` faria esta
              -- varredura perseguir TODA mensagem de grupo e forçar uma resposta — desfazendo
              -- pelo suspensório exatamente o comportamento que o prompt pede.
              AND NOT EXISTS (
                    SELECT 1 FROM wa_grupos g
                    WHERE g.chatwoot_conversation_id = m.chatwoot_conversation_id)
            GROUP BY 1"""), {"mn": _VARRE_MIN, "mx": _VARRE_MAX})
        return [dict(x) for x in r.mappings().all()]

    try:
        pend = _run_async(_pendentes)
    except Exception as e:  # noqa: BLE001
        logger.error("varrer_sem_resposta: consulta falhou: %s", e)
        return {"ok": False}

    if not pend:
        return {"ok": True, "pendentes": 0}  # silêncio honesto: nada preso

    for p in pend:
        logger.warning("[jose-luis] conversa %s com %s mensagem(ns) SEM resposta — "
                       "reprocessando", p["conv"], p["n"])
        processar_incoming_task.apply_async(
            args=[int(p["conv"]), p.get("fone")], queue="webhooks", priority=9)
    return {"ok": True, "pendentes": len(pend),
            "conversas": [p["conv"] for p in pend]}


# ═════════ PASSO 2 · A MÍDIA SAI DO CAMINHO SÍNCRONO DO WEBHOOK ═════════
# 28/08/2026 — medido, não suposto: uma foto custa ~1,2s de visão, mas o ÚNICO vídeo que o
# Jordan mandou consumiu **93,8s e devolveu ZERO** (`whatsapp.stt`, tokens_saida=0). O teto
# do caminho é 90s: o vídeo já estourou uma vez, hoje. E a rotina diária dele a partir de
# agora é mandar as fotos e vídeos da visita — 30 fotos seriam ~36s no handler.
#
# Com a análise aqui, o webhook devolve 200 na hora e a mídia tem o tempo que precisar.
#
# ⚠️ E ISSO CRIA UMA JANELA CEGA que precisa de trava explícita: a mensagem entra no
# histórico ANTES de a foto estar descrita. Se o agente responder nessa janela, ele responde
# sem ter visto a foto — e vai dizer que viu, que é pior que demorar. Por isso o contador
# `jl:midia:conv:*`: enquanto houver anexo em análise, `processar_incoming` ADIA.
MARCA_ANALISE = "📎 [analisando anexo(s)…]"

#: Marcado por `controller._transcrever_audio_attachments` quando o provedor recusa por
#: saldo. Existe porque aquele bloco engole a exceção de propósito (anexo ruim não pode
#: derrubar o webhook) — e sem isto a causa "sem crédito" chegaria ao Jordan como
#: "arquivo ilegível", que o faria tentar de novo para sempre.
_ULTIMO_ERRO: dict[str, bool] = {"sem_credito": False}


def _ultimo_erro_sem_credito() -> bool:
    v = _ULTIMO_ERRO.get("sem_credito")
    _ULTIMO_ERRO["sem_credito"] = False
    return bool(v)


@app.task(name="whatsapp.analisar_midia", bind=True, max_retries=2,
          acks_late=True, default_retry_delay=15)
def analisar_midia(self, conv_id: int, msg_id, payload: dict, phone: str | None = None):
    """Analisa os anexos fora do webhook e COMPLETA a mensagem já gravada."""
    import asyncio as _a

    from sqlalchemy import text as _t

    from modules.integrations.connectors.whatsapp import controller as C

    chave = f"jl:midia:conv:{conv_id}"

    async def _trabalho(session):
        _sem_credito = False
        try:
            desc = await C._transcrever_audio_attachments(payload, conv_id)
        except Exception as e:  # noqa: BLE001
            logger.error("analisar_midia conv=%s falhou: %s", conv_id, e)
            desc = None
            _sem_credito = "credit" in str(e).lower() or "insufficient_quota" in str(e).lower()
        if desc is None and not _sem_credito:
            # A falha é engolida dentro do `_transcrever_...` (ele nunca derruba o webhook),
            # então o motivo só existe no log. Lemos de lá o que o `except` não viu.
            _sem_credito = bool(_ultimo_erro_sem_credito())
        # Sem descrição NÃO some a marca em silêncio: o agente precisa saber que veio anexo
        # e que não deu para ler — senão responde como se nada tivesse chegado.
        #
        # ⚠️ E A CAUSA IMPORTA (28/08/2026): "sem crédito na conta" e "arquivo ilegível" não
        # podem usar a mesma frase. A segunda faz o Jordan achar que a foto dele era ruim e
        # tentar de novo — quando o que falta é saldo na OpenAI, onde vive o Whisper.
        # Áudio e vídeo passam por lá; foto vai pela DeepSeek.
        if desc:
            texto = desc
        elif _sem_credito:
            texto = ("📎 [anexo recebido — NÃO consegui transcrever: a conta de "
                     "transcrição (OpenAI) está sem crédito. Não é o arquivo.]")
        else:
            texto = "📎 [anexo recebido — não consegui interpretar o conteúdo]"
        await session.execute(_t(
            "UPDATE cwi_message_log SET content = replace(content, :marca, :texto) "
            "WHERE chatwoot_message_id = :m"),
            {"marca": MARCA_ANALISE, "texto": texto[:20000], "m": msg_id})
        await session.commit()
        if desc:
            await C._midia_para_visita_aberta(conv_id, desc)
        return bool(desc)

    ok = _run_async(_trabalho)

    # Contador chega a zero -> a rajada inteira foi analisada -> AGORA o agente responde.
    restantes = 0
    try:
        from core.cache.redis import get_redis

        async def _dec(_s):
            r = await get_redis()
            n = await r.decr(chave)
            if n <= 0:
                await r.delete(chave)
            return max(int(n), 0)

        restantes = _run_async(_dec)
    except Exception as e:  # noqa: BLE001
        logger.error("analisar_midia: contador indisponível (%s) — liberando mesmo assim", e)

    if restantes <= 0:
        processar_incoming_task.apply_async(args=[conv_id, phone], queue="webhooks", priority=8)
    return {"ok": ok, "conversation_id": conv_id, "anexos_restantes": restantes}


# ─────────────────────────────────────────────────────────────────────────────────────────
# whatsapp.checar_saldo_llm — AVISO DE SALDO DO PROVEDOR DO LLM
#
# 31/08/2026: das 11:43 às 13:02 a conta ficou SEM CRÉDITO — 34 recusas `402 Insufficient
# Balance`. O Jordan descobriu levando "estou com um problema técnico" na cara, três vezes,
# durante uma hora; e o pedido dele das 12:04 só foi respondido às 13:04.
#
# Duas decisões que valem a pena registrar:
#  · **Nada de LLM aqui.** O alerta dispara exatamente quando o LLM está morto. Texto fixo,
#    entregue por `notify_owner`, que só usa a API do WhatsApp.
#  · **Saldo sozinho não decide nada; saldo com AUTONOMIA decide.** "US$ 4,20" não diz se é
#    para agir hoje; "US$ 4,20 · ~3 dias" diz.
# ─────────────────────────────────────────────────────────────────────────────────────────

_SALDO_ATENCAO = float(os.getenv("LLM_SALDO_ATENCAO_USD", "5"))
_SALDO_CRITICO = float(os.getenv("LLM_SALDO_CRITICO_USD", "2"))


async def _saldo_provedor() -> float | None:
    """Saldo em USD, ou None se o provedor não expõe esse endpoint.

    Só a DeepSeek publica `/user/balance`. Em qualquer outro provedor devolve None e a
    task se cala — melhor não avisar do que avisar número inventado.
    """
    import httpx  # noqa: PLC0415

    base = (os.getenv("LLM_BASE_URL") or "").rstrip("/")
    key = os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or ""
    if not (base and key and "deepseek" in base):
        return None
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{base}/user/balance", headers={"Authorization": f"Bearer {key}"})
        r.raise_for_status()
        infos = (r.json() or {}).get("balance_infos") or []
    return float(infos[0].get("total_balance", 0)) if infos else None


async def _gasto_medio_diario(session) -> float:
    """Média de gasto/dia, ignorando dias de custo ZERO.

    Dia zerado é dia em que o serviço estava FORA (foi o caso de 30/08), não dia barato.
    Incluí-lo puxaria a média para baixo e inflaria a autonomia estimada — erro na direção
    perigosa: diria "6 dias" quando restam 3.
    """
    from sqlalchemy import text as _t  # noqa: PLC0415

    return float((await session.execute(_t(
        "SELECT coalesce(avg(d),0) FROM (SELECT sum(custo_usd) d FROM llm_usage "
        "WHERE criado_em >= now() - interval '7 days' "
        "GROUP BY date_trunc('day', criado_em) HAVING sum(custo_usd) > 0) x"))).scalar() or 0)


@app.task(name="whatsapp.checar_saldo_llm", bind=True, max_retries=0)
def checar_saldo_llm(self):  # noqa: ARG001
    try:
        return _run_async(_checar_saldo_llm)
    except Exception as e:  # noqa: BLE001
        logger.error("checar_saldo_llm: %s", e)
        return {"erro": str(e)[:200]}


async def _checar_saldo_llm(session):
    from core.cache.redis import get_redis  # noqa: PLC0415
    from modules.crm.services.orchestration import notify_owner  # noqa: PLC0415

    saldo = await _saldo_provedor()
    if saldo is None:
        return {"pulado": "provedor não expõe saldo"}

    nivel = "critico" if saldo < _SALDO_CRITICO else ("atencao" if saldo < _SALDO_ATENCAO else "ok")
    if nivel == "ok":
        # some o silenciador quando o saldo volta: a próxima queda avisa na hora
        with contextlib.suppress(Exception):
            r = await get_redis()
            await r.delete("llm:saldo:avisado")
            await r.delete("llm:saldo:desde")
        return {"saldo": saldo, "nivel": "ok"}

    # ⚠️ Não repetir sem MUDANÇA de patamar. A frase de erro repetida 9× em 63 segundos
    # ensinou que aviso que se repete deixa de ser lido — e este precisa ser lido.
    redis = await get_redis()
    chave = "llm:saldo:avisado"
    if (await redis.get(chave)) == nivel:
        return {"saldo": saldo, "nivel": nivel, "silenciado": "mesmo patamar"}

    # Crítico lembra a cada 3h SÓ no primeiro dia. Depois disso a informação é a mesma e o
    # dono já a tem: de 03 a 07/09/2026 foram 29 avisos "US$ -0.02" — seis por dia, cinco
    # dias — e um aviso que se repete deixa de ser lido. Do segundo dia em diante, um por dia.
    chave_desde = "llm:saldo:desde"
    desde = await redis.get(chave_desde)
    if not desde:
        desde = datetime.now(UTC).isoformat()
        await redis.set(chave_desde, desde, ex=30 * 24 * 3600)
    desde_s = desde.decode() if isinstance(desde, bytes) else str(desde)
    try:
        horas_no_patamar = (datetime.now(UTC) - datetime.fromisoformat(desde_s)).total_seconds() / 3600
    except ValueError:
        horas_no_patamar = 0.0

    media = await _gasto_medio_diario(session)
    dias = f"~{saldo / media:.0f} dia(s)" if media > 0 else "autonomia desconhecida"
    icone = "🔴" if nivel == "critico" else "⚠️"
    if saldo <= 0:
        corpo = ("Zerou: o José Luís NÃO está respondendo aos clientes no WhatsApp (a mensagem deles "
                 "vira \"estou com um problema técnico\"). Volta assim que houver crédito no provedor.")
    else:
        corpo = (f"Consumo médio: US$ {media:.2f}/dia → resta {dias}.\n\n"
                 "Quando zerar, ele para de responder e a mensagem vira \"estou com um problema técnico\".")
    await notify_owner(f"{icone} *Saldo do José Luís: US$ {saldo:.2f}*\n\n{corpo}")
    # janela por patamar: crítico lembra em 3h no primeiro dia; depois, e no 'atenção', uma vez por dia
    repete_em = 3 * 3600 if (nivel == "critico" and horas_no_patamar < 24) else 24 * 3600
    await redis.set(chave, nivel, ex=repete_em)
    logger.warning("checar_saldo_llm: saldo US$ %.2f (%s) — dono avisado", saldo, nivel)
    return {"saldo": saldo, "nivel": nivel, "media_dia": media, "avisado": True}


# ─────────────────────────────────────────────────────────────────────────────────────────
# whatsapp.checar_canal_surdo — O CANAL ESTÁ VERDE E MUDO?
#
# 31/08/2026, 15:13 → 17:32: o WhatsApp parou de ENTREGAR mensagem de entrada. 2h19 sem que
# ninguém percebesse, e o Jordan descobriu porque o agente não respondeu. Todos os monitores
# verdes: container `healthy` há 7 semanas, `/status` HTTP 200 a cada 30s.
#
# ⚠️ A saída continuou funcionando — os avisos de diária saíram normalmente. Por isso é
# invisível: metade do canal morre e a outra metade prova que "está no ar".
#
# POR QUE NÃO MEDIR SILÊNCIO: medido, 21 dias, dias úteis 8-18h — intervalo médio de 10
# minutos, e só 2 passaram de 4h. Um alarme de silêncio precisaria de 4h para não gritar à
# toa, e a falha de hoje durou 2h19: teria disparado DEPOIS de o Jordan reclamar. Serve para
# relatório, não para alarme.
#
# O QUE MEDE, ENTÃO: o caminho que quebrou. Hoje, `/status` respondia 200 em milissegundos
# enquanto a rota que fala com o WhatsApp de verdade pendurava 25 segundos sem responder.
# Essa diferença é o sinal — e é a única coisa que distinguia "no ar" de "surdo".
# ─────────────────────────────────────────────────────────────────────────────────────────

_BAILEYS_URL = os.getenv("BAILEYS_URL", "http://baileys-api:3025")
_BAILEYS_FONE = os.getenv("BAILEYS_CONNECTION", "+558008804414")


async def _sonda_whatsapp(timeout: float = 12.0) -> tuple[bool, str]:
    """(vivo, motivo). Faz um round-trip REAL ao WhatsApp, não um health check local."""
    import httpx  # noqa: PLC0415

    from modules.crm.services.orchestration import OWNER_E164  # noqa: PLC0415

    jid = re.sub(r"\D", "", str(OWNER_E164 or "")) + "@s.whatsapp.net"
    chave = os.getenv("BAILEYS_API_KEY", "")
    url = f"{_BAILEYS_URL}/connections/{_BAILEYS_FONE}/profile-picture-url"
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(url, params={"jid": jid},
                            headers={"x-api-key": chave} if chave else None)
        # ⚠️ 401/403 NÃO é prova de nada: a requisição morre na autenticação, ANTES de
        # qualquer round-trip ao WhatsApp. Chamar isso de "vivo" seria a sonda mais
        # perigosa possível — verde permanente sobre canal morto. Sem chave, ela se
        # declara INDETERMINADA e diz o porquê, em vez de mentir.
        if r.status_code in (401, 403):
            return (None, f"HTTP {r.status_code} — sem BAILEYS_API_KEY, a sonda não "
                          "alcança o WhatsApp e não prova nada")
        # Demais respostas provam que o socket foi até o WhatsApp e voltou.
        return (True, f"HTTP {r.status_code}")
    except Exception as e:  # noqa: BLE001
        return (False, type(e).__name__)


@app.task(name="whatsapp.checar_canal_surdo", bind=True, max_retries=0)
def checar_canal_surdo(self):  # noqa: ARG001
    try:
        return _run_async(_checar_canal_surdo)
    except Exception as e:  # noqa: BLE001
        logger.error("checar_canal_surdo: %s", e)
        return {"erro": str(e)[:200]}


async def _checar_canal_surdo(session):
    from core.cache.redis import get_redis  # noqa: PLC0415
    from modules.crm.services.orchestration import notify_owner  # noqa: PLC0415

    vivo, motivo = await _sonda_whatsapp()
    if vivo is None:
        # Não conta como falha nem como sucesso. Um alarme que não pode medir tem de dizer
        # isso alto, não escolher um lado.
        logger.error("checar_canal_surdo: NÃO VERIFICADO — %s", motivo)
        return {"vivo": None, "motivo": motivo}
    redis = await get_redis()
    chave = "wa:canal:falhas"
    if vivo:
        with contextlib.suppress(Exception):
            await redis.delete(chave)
        return {"vivo": True, "motivo": motivo}

    # ⚠️ DUAS falhas seguidas antes de avisar. Uma sonda que expira pode ser lentidão do
    # WhatsApp; duas em sequência são o padrão de hoje. Alarme que grita por soluço deixa
    # de ser lido — foi a lição das 9 frases de erro em 63 segundos.
    n = await redis.incr(chave)
    await redis.expire(chave, 3600)
    if n < 2:
        logger.warning("checar_canal_surdo: sonda falhou (%s) — 1ª vez, aguardando confirmar", motivo)
        return {"vivo": False, "motivo": motivo, "falhas": n}

    if n == 2:
        await notify_owner(
            "🔇 *O WhatsApp pode estar surdo.*\n\n"
            "A conexão responde, mas a sonda que fala com o WhatsApp de verdade não "
            f"respondeu em duas tentativas seguidas ({motivo}).\n\n"
            "Foi o que aconteceu hoje das 15:13 às 17:32: mensagem SUA não chegava, e os "
            "avisos automáticos continuavam saindo normalmente — por isso ninguém viu.\n\n"
            "Se eu não estiver respondendo, é isso. Reiniciar o baileys resolve e não "
            "perde a sessão.")
    logger.error("checar_canal_surdo: canal SURDO (%s), %ª falha — dono avisado", motivo, n)
    return {"vivo": False, "motivo": motivo, "falhas": n, "avisado": n == 2}


# ═════════ TROCA DE TURNO — os três tempos (Jordan, 24/09/2026) ═════════
#
# ⚠️ As três tasks são finas de propósito: a lógica vive em `troca_turno.py`, testável sem
# Celery. Task que carrega regra é regra que só roda em produção.

@app.task(name="whatsapp.turno_pedir_confirmacao", bind=True, max_retries=1)
def turno_pedir_confirmacao(self):  # noqa: ARG001
    """Véspera 18h Manaus: pergunta a quem assume posto amanhã às 06h/07h se está tudo certo."""
    from modules.integrations.connectors.whatsapp import troca_turno as _tt

    try:
        r = _run_async(lambda s: _tt.pedir_confirmacoes(s))
        logger.info("[jose-luis] confirmação de turno pedida: %s", r)
        return r
    except Exception as e:  # noqa: BLE001
        logger.error("turno_pedir_confirmacao falhou: %s", e)
        return {"ok": False, "erro": str(e)[:200]}


@app.task(name="whatsapp.turno_lembrar", bind=True, max_retries=1)
def turno_lembrar(self):  # noqa: ARG001
    """A cada 15 min na janela da manhã: cobra SÓ quem não confirmou, ~1h antes de assumir."""
    from modules.integrations.connectors.whatsapp import troca_turno as _tt

    try:
        r = _run_async(lambda s: _tt.lembrar_uma_hora_antes(s))
        if r.get("lembrados"):
            logger.info("[jose-luis] lembrete de turno: %s", r)
        return r
    except Exception as e:  # noqa: BLE001
        logger.error("turno_lembrar falhou: %s", e)
        return {"ok": False, "erro": str(e)[:200]}


@app.task(name="whatsapp.turno_fechar_cobertura", bind=True, max_retries=1)
def turno_fechar_cobertura(self):  # noqa: ARG001
    """08:30 Manaus: publica no GESTÃO a cobertura da manhã (confirmação × batida × foto)."""
    from modules.integrations.connectors.whatsapp import supervisao as _sup
    from modules.integrations.connectors.whatsapp import troca_turno as _tt

    async def _fazer(s):
        from sqlalchemy import text as _t

        r = await _tt.fechar_cobertura(s)
        # ⚠️ SILÊNCIO QUANDO NÃO HÁ TURNO, mas NÃO quando está tudo certo. São casos
        # diferentes: "não havia troca hoje" não interessa a ninguém; "as 8 trocas foram
        # cobertas" é exatamente o que tira o Paiva do 05:30 — ele precisa saber que alguém
        # conferiu, senão volta a conferir sozinho.
        if not r.get("turnos"):
            return {"ok": True, "turnos": 0, "publicado": False}
        destino = (await s.execute(_t(
            "SELECT chatwoot_conversation_id FROM wa_grupos "
            " WHERE recebe_relatorio AND chatwoot_conversation_id IS NOT NULL LIMIT 1"))).scalar()
        if not destino:
            logger.warning("turno_fechar_cobertura: sem grupo de relatório — nada publicado")
            return {"ok": False, "motivo": "sem destino", **r}
        ok = await _sup._publicar_no_grupo(int(destino), _tt.texto_da_cobertura(r))
        return {"ok": bool(ok), "publicado": bool(ok), "turnos": r["turnos"],
                "confirmou_e_nao_bateu": len(r["confirmou_e_nao_bateu"]),
                "nao_respondeu": len(r["nao_respondeu"])}

    try:
        r = _run_async(_fazer)
        logger.info("[jose-luis] cobertura da troca publicada: %s", r)
        return r
    except Exception as e:  # noqa: BLE001
        logger.error("turno_fechar_cobertura falhou: %s", e)
        return {"ok": False, "erro": str(e)[:200]}


# ═════════ REDE DE SEGURANÇA PARA GRUPO (Jordan, 24/09/2026) ═════════
#
# 🔴 A DÍVIDA QUE EU ABRI E ESTA TASK PAGA. `varrer_sem_resposta` era a rede que recuperava
# mensagem perdida quando um worker morre — e eu a excluí dos grupos de propósito, porque em
# grupo "sem resposta" é o NORMAL (o prompt diz "silêncio é resposta válida e é o padrão") e ela
# forçaria resposta a toda piada e bom dia.
#
# A consequência apareceu no mesmo dia: o Jordan mandou duas mensagens no Gestão às 15:37 e
# 15:49, um bake recriou o worker da fila `webhooks` naquele minuto, as tarefas sumiram e o
# Chatwoot não reentrega — ele já recebeu 200. Duas mensagens para o nada.
#
# ⭐ A RÉGUA CERTA NÃO É "SEM RESPOSTA", É "FALARAM COM ELE E NÃO HOUVE RESPOSTA". A menção
# (`mention://contact/…/Conecta`) é o sinal inequívoco de que alguém esperava resposta — e é o
# que separa "ninguém falou com ele" de "alguém falou e a mensagem se perdeu".
#
# ⚠️ Só grupos em `falar`. Em grupo de condomínio (modo `observar`) ele não responde nem quando
# mencionado, e recuperar ali seria dar voz onde o dono não deu.

#: Nome do próprio número nas menções. `[@Conecta Mais](mention://contact/3/Conecta%20Mais)` —
#: o id do contato muda por instalação, o nome não. Configurável porque o dia em que mudar, o
#: sintoma seria a rede parar de funcionar em silêncio.
_MENCAO_A_MIM = os.getenv("JOSE_LUIS_NOME_MENCAO", "Conecta")


@app.task(name="whatsapp.varrer_grupos_mencao", bind=True, max_retries=1)
def varrer_grupos_mencao(self):  # noqa: ARG001
    """Recupera menção ao José Luís em grupo `falar` que ficou sem resposta. 3–60 min."""
    from sqlalchemy import text as _t

    async def _pendentes(s):
        r = await s.execute(_t("""
            SELECT m.grupo_jid, g.nome, g.chatwoot_conversation_id AS conv, count(*) AS n
              FROM wa_grupo_mensagens m
              JOIN wa_grupos g ON g.jid = m.grupo_jid
             WHERE g.modo = 'falar' AND g.chatwoot_conversation_id IS NOT NULL
               AND m.conteudo ILIKE '%mention://contact/%'
               AND m.conteudo ILIKE '%' || :eu || '%'
               AND m.criado_em BETWEEN now() - interval '60 minutes'
                                   AND now() - interval '3 minutes'
               -- resposta NOSSA depois dela? `wa_grupo_falas` guarda o que o agente publicou.
               AND NOT EXISTS (
                     SELECT 1 FROM wa_grupo_falas f
                      WHERE f.grupo_jid = m.grupo_jid AND f.quando > m.criado_em)
             GROUP BY 1, 2, 3"""), {"eu": _MENCAO_A_MIM})
        return [dict(x) for x in r.mappings().all()]

    try:
        pend = _run_async(_pendentes)
    except Exception as e:  # noqa: BLE001
        logger.error("varrer_grupos_mencao: consulta falhou: %s", e)
        return {"ok": False}

    if not pend:
        return {"ok": True, "pendentes": 0}  # silêncio honesto: nada preso

    for p in pend:
        logger.warning("[jose-luis] %s mencão(ões) no grupo %s SEM resposta — reprocessando "
                       "conv=%s", p["n"], p["nome"], p["conv"])
        processar_incoming_task.apply_async(
            args=[int(p["conv"]), None], queue="webhooks", priority=9)
    return {"ok": True, "pendentes": len(pend),
            "grupos": [p["nome"] for p in pend]}
