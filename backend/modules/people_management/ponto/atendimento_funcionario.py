"""O que o funcionário pergunta sobre o PRÓPRIO ponto, e o que dá para resolver na hora (11/09/2026).

Decisão do Jordan, 11/09/2026, sobre o José Luís no WhatsApp: **"que ele resolva sozinho"**.
Resolver sozinho aqui tem um limite legal que não é opinião: ponto é registro de FATO e batida
lançada por terceiro sem trilha é o que vira palavra contra palavra numa reclamatória. Então o
"sozinho" acontece pelos dois caminhos que a casa JÁ criou para isso, e nenhum deles inventa hora:

  * **batida de contingência** (`self_service.batida-contingencia`, 56 usos em 30 dias): quem não
    conseguiu bater pelo rosto registra PENDENTE e o DP valida. Ninguém perde o ponto.
  * **justificativa** (`gp_justifications`, status `pendente`): atraso/falta com o motivo dito por
    ele, que o DP revisa na tela de sempre e a folha lê (`payroll_service._absences`).

O que muda com este módulo é só QUEM alcança esses caminhos: até hoje eles existiam atrás do login
do portal. Quem manda mensagem às 3 da manhã da guarita, sem conseguir abrir o app, não tem login —
tem WhatsApp. Medido nas 2.074 mensagens do José Luís: 64 dos 98 números são de funcionários.

Identidade NUNCA vem por argumento: o `employee_id` sai do telefone (`whatsapp/identidade.py`),
como em toda a casa. Sem isso, uma frase ("sou o Rene") moveria ponto de outra pessoa.
"""
from __future__ import annotations

import datetime as _dt
import logging
import uuid as _uuid
from zoneinfo import ZoneInfo as _ZoneInfo

from sqlalchemy import text as sql

logger = logging.getLogger(__name__)

#: Duas batidas iguais em minutos é dedo duplo, não dois fatos. Mesmo teto do app.
MINUTOS_ANTI_DUPLICATA = 10

CATEGORIAS = ("transito", "saude", "familiar", "transporte_publico", "acidente", "outro")
TIPOS = ("atraso", "falta")

_SQL_TURNO_HOJE = """
SELECT to_char(sh.planned_start_time,'HH24:MI') AS inicio,
       to_char(sh.planned_end_time,'HH24:MI')   AS fim,
       p.name AS posto, sh.is_off_day, sh.id::text AS shift_id
  FROM shifts sh JOIN posts p ON p.id = sh.post_id
 WHERE sh.employee_id = CAST(:e AS uuid)
   AND sh.shift_date = (now() AT TIME ZONE 'America/Manaus')::date
   AND sh.is_active = TRUE
 ORDER BY sh.planned_start_time LIMIT 1
"""

#: A janela é o TURNO (14h), não o dia do calendário — na virada da meia-noite o noturno
#: perderia as próprias batidas. Mesmo corte de `_proxima_batida_info` e do espelho.
_SQL_BATIDAS_JANELA = """
SELECT to_char(punch_timestamp,'DD/MM HH24:MI') AS quando, punch_type, status, device_type
  FROM gp_clock_punches
 WHERE employee_id = CAST(:e AS uuid)
   AND punch_timestamp > (now() AT TIME ZONE 'America/Manaus') - interval '14 hours'
 ORDER BY punch_timestamp
"""


async def situacao_hoje(db, employee_id: str) -> dict:
    """O que o SISTEMA enxerga do ponto dele agora — turno, batidas da janela, o que falta.

    É a resposta para a pergunta mais frequente ("bateu ou não bateu?"), e é a que desarma o
    lembrete: quem recebeu "você ainda não bateu" e bateu no Tangerino precisa ver o que o
    nosso banco tem, não ouvir de novo que bata.
    """
    from modules.people_management.employee_portal.controllers.self_service_controller import (  # noqa: PLC0415
        _proxima_batida_info,
    )

    turno = (await db.execute(sql(_SQL_TURNO_HOJE), {"e": employee_id})).mappings().first()
    batidas = (await db.execute(sql(_SQL_BATIDAS_JANELA), {"e": employee_id})).mappings().all()
    try:
        prox = await _proxima_batida_info(db, employee_id)
    except Exception as exc:  # noqa: BLE001 — a leitura não pode cair por causa da projeção
        logger.warning("situacao_hoje: próxima batida indisponível (%s)", exc)
        prox = {"tipo": "", "concluido": False}
    pend = (await db.execute(sql(
        "SELECT justification_type, reason, status, to_char(created_at,'DD/MM') AS dia "
        "  FROM gp_justifications WHERE employee_id = :e AND status = 'pendente' "
        " ORDER BY created_at DESC LIMIT 5"), {"e": str(employee_id)})).mappings().all()
    return {
        "turno_hoje": (f"{turno['inicio']}–{turno['fim']} no {turno['posto']}" if turno and not turno["is_off_day"]
                       else ("FOLGA hoje" if turno else "sem turno na escala de hoje")),
        "batidas_do_turno": [f"{b['quando']} {b['punch_type']}"
                             + (f" ({b['status']})" if b["status"] not in ("approved", "normal") else "")
                             + (" [veio do Tangerino]" if b["device_type"] == "tangerino" else "")
                             for b in batidas],
        "proxima_batida": ("jornada do turno concluída" if prox.get("concluido") else prox.get("tipo") or "—"),
        "justificativas_pendentes": [f"{j['dia']} {j['justification_type']}: {j['reason']}" for j in pend],
    }


def _hora_informada(quando: str | None) -> _dt.datetime | None:
    """Converte "08:38" na hora REAL daquele instante em Manaus, ou None se não der para confiar.

    🔴 27/09/2026 — POR QUE ISTO NASCEU. O JONILSON ficou 15 horas com a jornada aberta porque
    saiu às 08:38 esperando a rendição e não conseguiu bater. O José Luís tinha duas tools e
    nenhuma servia: `registrar_batida_contingencia` carimbava AGORA (09:20, quase uma hora
    depois do fato) e `abrir_pendencia_dp` só pede a um humano. Ele escolheu a pendência — o
    que era razoável — e então disse ao Jonilson *"Registrado: saída de hoje às 08:38"*.
    **Fez uma coisa e contou outra**, e o rapaz foi dormir achando que a jornada tinha fechado.

    ⭐ A capacidade que faltava não era esperteza do modelo: era poder gravar a batida na HORA
    QUE A PESSOA INFORMOU. Élen, Anilson, Matheus, Erika e Jonilson precisaram disso no mesmo
    dia.

    ⚠️ E hora vinda de um modelo precisa de parede, senão vira fabricação:

      · NUNCA no futuro — eu mesmo deixei uma batida de teste às 19:40 num banco às 07:01
      · NUNCA mais de 18h atrás — além disso é outro turno, não esta jornada
      · se a hora dita já passou hoje, é hoje; se ainda não chegou, é de ONTEM (noturno que
        atravessa a meia-noite — `TIME + 24h` daria a volta em vez de avançar o dia)
    """
    import re as _re  # noqa: PLC0415

    if not quando:
        return None
    m = _re.search(r"(\d{1,2})\s*[:hH]\s*(\d{2})", str(quando))
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None
    agora = _dt.datetime.now(_ZoneInfo("America/Manaus")).replace(tzinfo=None)
    alvo = agora.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if alvo > agora:                      # ainda não chegou hoje ⇒ foi ontem
        alvo -= _dt.timedelta(days=1)
    if (agora - alvo) > _dt.timedelta(hours=18):
        return None                        # longe demais para ser esta jornada
    return alvo


async def registrar_contingencia(db, employee_id: str, motivo: str,
                                 quando: str | None = None) -> dict:
    """A batida que o app não conseguiu registrar, gravada PENDENTE para o DP validar.

    Mesma gravação do endpoint `/self-service/batida-contingencia` — o que muda é a porta de
    entrada (WhatsApp em vez do portal). O tipo sai da SEQUÊNCIA da pessoa, nunca do que ela
    diz: quem decide se falta "entrada" ou "retorno do almoço" é `_proxima_batida_info`, que
    conhece intrajornada, meio período de sábado e a virada do turno noturno.

    `quando` = hora que a PESSOA informou ("08:38"). Sem ela, carimba agora — o que só está
    certo quando a pessoa está no posto neste momento. Ver `_hora_informada`.
    """
    from modules.people_management.employee_portal.controllers.self_service_controller import (  # noqa: PLC0415
        _proxima_batida_info,
    )

    # ⚠️ A anti-duplicata olha em torno da hora DO FATO, não de agora: com hora informada,
    # medir a partir de `now()` procuraria vizinhança no lugar errado e deixaria duplicar.
    hora_fato = _hora_informada(quando)
    recente = (await db.execute(sql(
        "SELECT to_char(punch_timestamp,'HH24:MI') FROM gp_clock_punches "
        " WHERE employee_id = CAST(:e AS uuid) "
        "   AND abs(EXTRACT(EPOCH FROM (punch_timestamp - "
        "       coalesce(CAST(CAST(:ts AS text) AS timestamp), (now() AT TIME ZONE 'America/Manaus')))))"
        "       <= :m * 60 "
        " ORDER BY punch_timestamp DESC LIMIT 1"),
        {"e": employee_id, "m": MINUTOS_ANTI_DUPLICATA,
         "ts": hora_fato.isoformat(sep=" ") if hora_fato else None})).scalar()
    if recente:
        return {"ok": True, "ja_registrado": True, "hora": recente,
                "msg": f"Já existe uma batida sua às {recente}. Não registrei outra para não duplicar."}

    prox = await _proxima_batida_info(db, employee_id)
    tipo = "extra" if prox.get("concluido") else (prox.get("tipo") or "entrada")
    pid = str(_uuid.uuid4())
    await db.execute(sql(
        "INSERT INTO gp_clock_punches (punch_id, employee_id, punch_type, punch_timestamp, "
        " server_timestamp, status, device_type, created_at, updated_at) "
        "VALUES (:pid, CAST(:e AS uuid), :t, "
        " coalesce(CAST(CAST(:ts AS text) AS timestamp), (now() AT TIME ZONE 'America/Manaus')), "
        " (now() AT TIME ZONE 'America/Manaus'), 'pending_contingencia', 'contingencia', now(), now())"),
        {"pid": pid, "e": employee_id, "t": tipo,
         "ts": hora_fato.isoformat(sep=" ") if hora_fato else None})
    # O motivo dito por ele é a trilha do DP: sem isso a batida pendente chega sem história.
    await db.execute(sql(
        "INSERT INTO gp_justifications (justification_id, punch_id, employee_id, justification_type, "
        " reason, category, status, source, created_at) "
        "VALUES (:jid, :pid, :e, 'atraso', :r, 'outro', 'pendente', 'whatsapp', now())"),
        {"jid": str(_uuid.uuid4()), "pid": pid, "e": str(employee_id),
         "r": (f"Batida por contingência via WhatsApp: {motivo}"
               + (f" [HORA INFORMADA PELA PRÓPRIA PESSOA: {hora_fato.strftime('%d/%m %H:%M')} — "
                  f"não é a hora em que o agente registrou]" if hora_fato else ""))[:2000]})
    await db.commit()
    logger.info("contingência via WhatsApp: employee=%s tipo=%s punch=%s", employee_id, tipo, pid)
    _hh = hora_fato.strftime("%H:%M") if hora_fato else None
    return {"ok": True, "punch_id": pid, "tipo": tipo, "hora": _hh,
            "hora_informada_aceita": bool(hora_fato),
            # ⚠️ Quando a pessoa DIZ uma hora e a parede recusa (futuro, >18h), o texto avisa em
            # vez de fingir: senão o agente repetiria a hora dita e a batida estaria noutra.
            "msg": (f"Registrei sua {tipo} das *{_hh}*, com a hora que você me informou. "
                    f"Fica pendente de validação do DP e você não perde o ponto."
                    if hora_fato else
                    f"Registrei sua {tipo} *agora*, pendente de validação do DP. Você não "
                    f"perdeu o ponto.")}


async def registrar_justificativa(db, employee_id: str, tipo: str, motivo: str,
                                  categoria: str = "outro", anexo: str | None = None) -> dict:
    """Atraso ou falta com o motivo dito pelo funcionário — nasce PENDENTE, o DP revisa.

    A folha lê esta tabela (`payroll_service._absences`), então o que entra aqui chega ao
    fechamento do mês. Por isso `status='pendente'` não é rascunho esquecido: é o gate humano.
    """
    tipo = tipo if tipo in TIPOS else "atraso"
    categoria = categoria if categoria in CATEGORIAS else "outro"
    if not (motivo or "").strip():
        return {"ok": False, "msg": "sem motivo não dá para justificar — pergunte o que aconteceu"}

    # ⭐ 27/09/2026 — A RESPOSTA DELE PREENCHE A PERGUNTA QUE NÓS FIZEMOS.
    #
    # Nesta mesma manhã a batida fora do horário passou a nascer com uma justificativa PENDENTE
    # E VAZIA, e o José Luís a pedir o motivo no WhatsApp. O ALEXANDRE respondeu *"Troca de
    # horário"* e **nada capturou a resposta**: esta função só sabia INSERIR, então ou o agente
    # não fazia nada (foi o que aconteceu) ou criaria uma segunda justificativa órfã, sem
    # `punch_id`, enquanto a presa à batida seguia vazia.
    #
    # ⭐ Um ciclo que pergunta e não guarda a resposta é pior que não perguntar: gasta a
    # paciência da pessoa e entrega à supervisão uma decisão sem informação nenhuma.
    #
    # ⚠️ Só preenche o que está VAZIO — nunca sobrescreve palavras que alguém já deu — e só
    # dentro de 24h, para uma pendência velha não engolir uma justificativa nova de outro dia.
    aberta = (await db.execute(sql(
        "SELECT justification_id FROM gp_justifications "
        " WHERE employee_id = :e AND status = 'pendente' "
        "   AND coalesce(reason,'') = '' AND punch_id IS NOT NULL "
        "   AND created_at > now() - interval '24 hours' "
        " ORDER BY created_at DESC LIMIT 1"), {"e": str(employee_id)})).scalar()
    if aberta:
        await db.execute(sql(
            "UPDATE gp_justifications SET reason = :r, category = :c, updated_at = now() "
            " WHERE justification_id = :j"),
            {"r": motivo.strip()[:2000], "c": categoria, "j": aberta})
        # o rascunho da Central dizia «ainda não informou o motivo» — deixar essa frase no ar
        # faria a supervisão adiar uma decisão que já pode ser tomada
        await db.execute(sql(
            # ⚠️ `agent_drafts` NÃO tem coluna de atualização — conferido no schema, depois de
            # eu supor `updated_at` e a transação estourar. Três vezes hoje eu chutei coluna.
            "UPDATE agent_drafts SET resumo = resumo || :add "
            " WHERE tipo = 'justificar_ponto' AND status = 'rascunho' "
            "   AND payload->>'justification_id' = :j"),
            {"j": aberta, "add": f"\n\n✅ MOTIVO INFORMADO POR ELE NO WHATSAPP:\n« "
                                 f"{motivo.strip()[:600]} »"})
        await db.commit()
        logger.info("justificativa %s PREENCHIDA com a resposta de %s", aberta, employee_id)
        return {"ok": True, "justification_id": aberta, "preencheu_pendente": True,
                "msg": ("Anotei o motivo com as suas palavras e juntei à batida. Agora a "
                        "supervisão decide — você não precisa fazer mais nada.")}

    jid = str(_uuid.uuid4())
    await db.execute(sql(
        "INSERT INTO gp_justifications (justification_id, employee_id, justification_type, reason, "
        " category, status, source, attachments, created_at) "
        "VALUES (:jid, :e, :t, :r, :c, 'pendente', 'whatsapp', CAST(:a AS jsonb), now())"),
        {"jid": jid, "e": str(employee_id), "t": tipo, "r": motivo.strip()[:2000], "c": categoria,
         "a": f'["{anexo}"]' if anexo else "[]"})
    await db.commit()
    logger.info("justificativa via WhatsApp: employee=%s tipo=%s", employee_id, tipo)
    return {"ok": True, "justification_id": jid,
            "msg": f"Registrei sua justificativa de {tipo}. O DP vai analisar e você fica sabendo."}
