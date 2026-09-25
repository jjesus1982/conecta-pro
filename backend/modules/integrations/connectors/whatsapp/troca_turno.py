"""Tirar o Paiva do 05:30 — confirmação de assunção de posto em três tempos.

O pedido do Jordan (24/09/2026), nas palavras dele: *"todos os dias o Paiva acorda às 05:30
para ficar acompanhando as trocas de turno dos postos… a dor de cabeça é maior com agentes de
portaria com troca às 06:00 e 07:00. Talvez uma mensagem do José Luís no dia anterior pedindo a
confirmação… manda mensagem uma hora antes… e por fim postar no Gestão a cobertura dos postos
tanto pelas evidências de fotos quanto pelas batidas de ponto."*

⭐ O QUE FAZ ISSO VALER NÃO É O LEMBRETE. O Paiva já sabe acordar; o que ele não tem é TEMPO DE
REAÇÃO. Às 05:30 o furo já existe e não há mais quem cobrir. Na véspera às 18h, "quem não
confirmou" é uma lista curta e ainda há doze horas para resolver. A rotina move a descoberta do
problema, não o esforço.

Medido antes de escrever (amanhã): **3 pessoas assumem às 06:00 e 5 às 07:00**, e as 8 têm
telefone no cadastro. É uma população pequena o suficiente para caber numa mensagem e grande o
suficiente para arruinar a manhã de alguém.

## Os três tempos

1. **Véspera, 18h** — pergunta a cada um que assume de madrugada/manhã se está tudo certo.
2. **1h antes** — só para quem NÃO confirmou. Quem já disse "sim" não é incomodado de novo:
   lembrete que chega para todo mundo é lembrete que ninguém lê.
3. **Depois da troca** — cobertura no grupo Gestão, cruzando três fontes: a confirmação, a
   BATIDA (`gp_clock_punches`) e a FOTO no grupo do posto.

## Fronteiras que não se mexem

⚠️ **Nada disso altera escala.** A rotina LÊ `shifts` e escreve só na própria tabela de
confirmação. Quem não confirma não é substituído por mim: vira linha no relatório para o Paiva
ou o Jordan decidirem. Operacional é curado à mão, e isso não muda porque ficou conveniente.

⚠️ **"Não vou poder ir" não é recusa a ser arquivada** — é falta anunciada, e já existe caminho
para isso: `supervisao.registrar_pedido_de_escala` cria o rascunho COM a lista de quem pode
cobrir. Esta rotina só reconhece e encaminha; não reimplementa.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time, timedelta
from typing import Any

from core.logging import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

#: Manaus é UTC-4 e não tem horário de verão. O banco guarda UTC; a operação vive em Manaus, e
#: "as 06:00" da escala é hora de Manaus — confundir isso põe o lembrete 4h fora.
BRT = timedelta(hours=-4)

#: Turnos que doem: os que começam de madrugada/manhã cedo. O Jordan nomeou 06:00 e 07:00; abro
#: até 08:59 porque o mesmo raciocínio vale e o custo de incluir é uma mensagem.
#: ⚠️ 06:00–07:59 e não 05:00–08:59. Abri até as 9h "porque o custo de incluir é uma mensagem" e
#: a medição desmentiu: a janela larga pegava 17 turnos, contra 8 nas duas horas que o Jordan
#: nomeou. Dezessete mensagens por noite é a enxurrada que treina o time a ignorar o José Luís —
#: e ele pediu ajuda numa dor específica, não um lembrete geral. Alargar depois é trivial;
#: recuperar a atenção de quem já aprendeu a ignorar, não.
HORA_MIN, HORA_MAX = time(6, 0), time(7, 59)


def agora_manaus() -> datetime:
    from datetime import UTC  # noqa: PLC0415
    return datetime.now(UTC) + BRT


def hoje_manaus() -> date:
    return agora_manaus().date()


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "").lower()) if not unicodedata.combining(c))


#: "Sim" em WhatsApp de gente real. Determinístico de propósito: o que vira REGISTRO de que
#: alguém se comprometeu com um posto não pode depender de juízo do modelo.
#: ⚠️ O emoji vai FORA do grupo com `\b`: `\b` é fronteira de caractere de PALAVRA, e depois de
#: 👍 não existe fronteira nenhuma — o padrão nunca casava. Um "👍" é a confirmação mais comum
#: que existe em grupo de WhatsApp, e ela caía como "não respondeu".
_CONFIRMA = re.compile(
    r"^\s*((sim|ss+|isso|ok+|okay|blz|beleza|certo|confirmo|confirmado|positivo|"
    r"tudo (certo|ok|bem|tranquilo)|to indo|tou indo|estou indo|vou sim|ja estou|"
    r"ja vou|sem problema|de acordo|combinado|joia|jóia)\b|[👍✅🙏👌])")
#: "Não" explícito. NÃO tenta cobrir "não vou poder ir" — aquilo é falta anunciada e tem caminho
#: próprio (`supervisao.classificar_pedido`), com sugestão de substituto. Aqui só o "não" seco.
#: ⚠️ SÓ O "NÃO" SECO. Minha primeira versão tinha `nao vou`, e com isso "nao vou poder ir
#: amanha" virava um `recusado` arquivado em silêncio — contradizendo o que o docstring desta
#: classe promete. Falta anunciada tem caminho próprio
#: (`supervisao.classificar_pedido` → rascunho COM a lista de quem pode cobrir), e engolir aqui
#: destruía justamente a ajuda que o Paiva precisa. Régua que abraça demais rouba de outra.
_NEGA = re.compile(r"^\s*(nao|não|negativo)\s*[.!]?\s*$")


def ler_resposta(texto: str | None) -> str | None:
    """`confirmado` | `recusado` | None (não é resposta de confirmação).

    None é o caso mais comum e é o certo: a pessoa manda áudio, foto, "bom dia" ou uma pergunta.
    Interpretar isso como confirmação seria registrar compromisso que ninguém assumiu — e o
    relatório das 06:00 diria "confirmado" sobre um posto vazio.
    """
    t = _sem_acento(texto)
    if not t.strip():
        return None
    if _NEGA.match(t):
        return "recusado"
    if _CONFIRMA.match(t):
        return "confirmado"
    return None


async def _turnos_da_janela(db: AsyncSession, dia: date) -> list[dict]:
    """Turnos de `dia` que começam na janela dolorosa, com pessoa, posto e telefone."""
    rows = (await db.execute(text("""
        SELECT s.id::text, s.employee_id::text, s.post_id::text, s.shift_date, s.planned_start_time,
               e.nome, e.telefone, e.cargo, p.name AS posto
          FROM shifts s
          JOIN employees e ON e.id = s.employee_id
          LEFT JOIN posts p ON p.id = s.post_id
         WHERE s.shift_date = :d AND s.is_active AND NOT s.is_off_day
           AND s.planned_start_time BETWEEN :hmin AND :hmax
           AND e.status = 'ativo'
         ORDER BY s.planned_start_time, e.nome"""),
        {"d": dia, "hmin": HORA_MIN, "hmax": HORA_MAX})).mappings().all()
    return [dict(r) for r in rows]


async def pedir_confirmacoes(db: AsyncSession, *, dia: date | None = None, enviar: bool = True) -> dict:
    """Tempo 1 — véspera: pergunta a cada um se está tudo certo para assumir amanhã.

    `enviar=False` monta tudo e NÃO manda: é assim que eu testo sem escrever no WhatsApp de oito
    pessoas. O padrão é enviar porque em produção quem chama é o beat.
    """
    dia = dia or (hoje_manaus() + timedelta(days=1))
    turnos = await _turnos_da_janela(db, dia)
    if not turnos:
        return {"dia": str(dia), "turnos": 0, "enviados": 0}

    enviados, falhas, pulados = 0, [], 0
    for t in turnos:
        # Idempotência pela chave natural: o beat pode rodar duas vezes sem perguntar duas vezes.
        ja = (await db.execute(text(
            "SELECT pedido_em FROM troca_turno_confirmacoes WHERE shift_id = CAST(:s AS uuid)"),
            {"s": t["id"]})).first()
        if ja and ja[0]:
            pulados += 1
            continue

        hora = t["planned_start_time"].strftime("%Hh")
        posto = t["posto"] or "seu posto"
        primeiro = str(t["nome"] or "").split()[0].title()
        msg = (f"Oi {primeiro}, boa tarde! Amanhã você assume o {posto} às {hora}. "
               f"Está tudo certo? Só me responde *sim* que eu registro aqui. "
               f"Se tiver qualquer problema, me fala agora que ainda dá tempo de resolver.")

        await db.execute(text("""
            INSERT INTO troca_turno_confirmacoes
                   (shift_id, employee_id, post_id, data, hora_inicio, pedido_em, status)
            VALUES (CAST(:s AS uuid), CAST(:e AS uuid), CAST(:p AS uuid), :d, :h, now(), 'aguardando')
            ON CONFLICT (shift_id) DO UPDATE SET pedido_em = now()"""),
            {"s": t["id"], "e": t["employee_id"], "p": t["post_id"], "d": dia,
             "h": t["planned_start_time"]})

        if enviar:
            ok = await _mandar(t["telefone"], msg)
            if ok:
                enviados += 1
            else:
                # ⚠️ ENVIO FALHOU ≠ PESSOA OMISSA. Sem esta marca, o relatório das 08:30 diria
                # "não respondeu" sobre quem nunca recebeu a pergunta — culpando a pessoa pela
                # minha falha de entrega. `status` vira `nao_avisado` e o texto do relatório
                # separa as duas coisas.
                falhas.append(t["nome"])
                await db.execute(text(
                    "UPDATE troca_turno_confirmacoes SET status = 'nao_avisado' "
                    " WHERE shift_id = CAST(:s AS uuid)"), {"s": t["id"]})
        else:
            enviados += 1
    await db.commit()
    return {"dia": str(dia), "turnos": len(turnos), "enviados": enviados,
            "pulados_ja_perguntados": pulados, "falhas": falhas, "simulado": not enviar}


async def lembrar_uma_hora_antes(db: AsyncSession, *, enviar: bool = True) -> dict:
    """Tempo 2 — 1h antes: cobra SÓ quem não confirmou.

    ⚠️ "Só quem não confirmou" é a regra que faz o lembrete funcionar. Mandar para todos
    transformaria a mensagem em ruído diário, e quem confirmou ontem à noite receberia uma
    cobrança às 05:00 — o jeito mais rápido de o time aprender a ignorar o José Luís.
    """
    agora = agora_manaus()
    alvo_ini = (agora + timedelta(minutes=45)).time()
    alvo_fim = (agora + timedelta(minutes=75)).time()

    rows = (await db.execute(text("""
        SELECT c.id::text, c.hora_inicio, e.nome, e.telefone, p.name AS posto, c.status
          FROM troca_turno_confirmacoes c
          JOIN employees e ON e.id = c.employee_id
          LEFT JOIN posts p ON p.id = c.post_id
         WHERE c.data = :d AND c.status = 'aguardando' AND c.lembrete_em IS NULL
           AND c.hora_inicio BETWEEN :a AND :b"""),
        {"d": agora.date(), "a": alvo_ini, "b": alvo_fim})).mappings().all()

    enviados, falhas = 0, []
    for r in rows:
        primeiro = str(r["nome"] or "").split()[0].title()
        msg = (f"{primeiro}, bom dia! Você assume o {r['posto'] or 'posto'} às "
               f"{r['hora_inicio'].strftime('%Hh')} — daqui a uma hora. "
               f"Já está a caminho? Me responde só pra eu saber que está tudo certo.")
        if enviar:
            ok = await _mandar(r["telefone"], msg)
        else:
            ok = True
        if ok:
            enviados += 1
            await db.execute(text(
                "UPDATE troca_turno_confirmacoes SET lembrete_em = now() WHERE id = CAST(:i AS uuid)"),
                {"i": r["id"]})
        else:
            falhas.append(r["nome"])
    await db.commit()
    return {"janela": f"{alvo_ini:%H:%M}–{alvo_fim:%H:%M}", "sem_confirmacao": len(rows),
            "lembrados": enviados, "falhas": falhas, "simulado": not enviar}


async def registrar_resposta(db: AsyncSession, *, employee_id: str, texto: str) -> dict | None:
    """Casa a resposta da pessoa com o turno dela de hoje/amanhã. None se não havia pergunta.

    Devolve o que aconteceu para quem chama poder responder algo coerente — e não um "ok"
    genérico sobre um registro que talvez não exista.
    """
    veredito = ler_resposta(texto)
    if not veredito:
        return None
    r = (await db.execute(text("""
        SELECT c.id::text, c.data, c.hora_inicio, p.name AS posto
          FROM troca_turno_confirmacoes c LEFT JOIN posts p ON p.id = c.post_id
         WHERE c.employee_id = CAST(:e AS uuid) AND c.status = 'aguardando'
           AND c.data BETWEEN :h AND :h2
         ORDER BY c.data, c.hora_inicio LIMIT 1"""),
        {"e": str(employee_id), "h": hoje_manaus(), "h2": hoje_manaus() + timedelta(days=1)})).mappings().first()
    if not r:
        return None
    await db.execute(text(
        "UPDATE troca_turno_confirmacoes SET status = :s, resposta_texto = :t, respondido_em = now() "
        " WHERE id = CAST(:i AS uuid)"),
        {"s": veredito, "t": str(texto)[:500], "i": r["id"]})
    await db.commit()
    return {"status": veredito, "posto": r["posto"], "data": str(r["data"]),
            "hora": r["hora_inicio"].strftime("%Hh")}


async def _mandar(telefone: str | None, msg: str) -> bool:
    """True SÓ quando o serviço afirmou `status='sent'`. Ausência de erro não é entrega.

    🔴 Eu havia escrito `not (r.get("status") == "error")`, recusando apenas a falha NOMEADA.
    `_send_message` devolve QUATRO formas — `sent`, `error`, `exception`, `disabled` — e as duas
    últimas passavam como sucesso. Medido no disparo de 25/09 em `pix_confirma` (mesmo código):
    4 telefones fabricados ficaram "aguardando" sem nenhuma mensagem ter saído.

    Aqui o dano é maior que lá: `nao_avisado` existe justamente para o relatório das 08:30 não
    dizer ao Jordan que a pessoa foi OMISSA quando ela nunca recebeu a pergunta. Com a checagem
    frouxa, a falha de entrega virava omissão da pessoa — a acusação injusta que esta marca
    existe para impedir. Estado não previsto falha FECHADO.
    """
    if not telefone:
        return False
    try:
        from modules.integrations.connectors.whatsapp.service import whatsapp_service  # noqa: PLC0415

        r = await whatsapp_service.send_custom(str(telefone), msg)
        if isinstance(r, dict) and r.get("status") == "sent":
            return True
        logger.error("troca_turno: NÃO entregue para %s — resposta do serviço: %s",
                     telefone, (r if isinstance(r, dict) else type(r).__name__))
        return False
    except Exception as e:  # noqa: BLE001
        logger.error("troca_turno: envio falhou para %s (%s)", telefone, e)
        return False


async def fechar_cobertura(db: AsyncSession, *, dia: date | None = None) -> dict[str, Any]:
    """Tempo 3 — cruza CONFIRMAÇÃO × BATIDA × FOTO e devolve o que o Paiva precisa ver.

    ⭐ As três fontes existem por razões diferentes e nenhuma basta sozinha:
      · a CONFIRMAÇÃO diz o que a pessoa prometeu — e promessa não é presença;
      · a BATIDA prova que alguém registrou entrada — mas o relógio pode falhar, e a batida
        atrasada não distingue "chegou tarde" de "esqueceu de bater";
      · a FOTO no grupo do posto é a evidência que o condomínio vê, e é a que o Paiva usa hoje.

    O relatório destaca o CRUZAMENTO que dói: confirmou e não bateu. Esse é o furo silencioso —
    todo mundo achando que está coberto porque a pessoa disse que ia.
    """
    dia = dia or hoje_manaus()
    linhas = (await db.execute(text("""
        SELECT e.nome, c.hora_inicio, c.status, p.name AS posto, c.post_id::text,
               c.employee_id::text, c.respondido_em
          FROM troca_turno_confirmacoes c
          JOIN employees e ON e.id = c.employee_id
          LEFT JOIN posts p ON p.id = c.post_id
         WHERE c.data = :d ORDER BY c.hora_inicio, e.nome"""), {"d": dia})).mappings().all()
    if not linhas:
        return {"dia": str(dia), "turnos": 0}

    ok, confirmou_sem_bater, nao_respondeu, recusou = [], [], [], []
    for r in linhas:
        # Batida na janela do turno (±2h). `punch_timestamp` nesta tabela é hora de MANAUS, não
        # UTC — conferido no projeto; tratar como UTC jogaria a janela 4h fora.
        bateu = (await db.execute(text("""
            SELECT min(punch_timestamp) FROM gp_clock_punches
             WHERE employee_id = CAST(:e AS uuid)
               AND punch_timestamp BETWEEN (CAST(:d AS date) + CAST(:h AS time)) - interval '2 hours'
                                       AND (CAST(:d AS date) + CAST(:h AS time)) + interval '2 hours'"""),
            {"e": r["employee_id"], "d": dia, "h": r["hora_inicio"]})).scalar()
        # Foto no grupo daquele posto, na janela. `wa_grupo_mensagens.tipo` guarda 'image' quando
        # a mensagem é mídia (ver `absorver`).
        foto = (await db.execute(text("""
            SELECT count(*) FROM wa_grupo_mensagens m
             WHERE m.classificacao IN ('escala_do_dia','operacional','midia')
               AND m.criado_em BETWEEN (CAST(:d AS date) + CAST(:h AS time)) - interval '2 hours'
                                   AND (CAST(:d AS date) + CAST(:h AS time)) + interval '3 hours'"""),
            {"d": dia, "h": r["hora_inicio"]})).scalar() or 0

        item = {"quem": r["nome"], "posto": r["posto"] or "?",
                "hora": r["hora_inicio"].strftime("%Hh"),
                "bateu": bateu.strftime("%H:%M") if bateu else None,
                "evidencias_no_grupo": int(foto)}
        if r["status"] == "recusado":
            recusou.append(item)
        elif bateu:
            ok.append(item)
        elif r["status"] == "nao_avisado":
            item["por_que"] = "eu NÃO consegui avisar esta pessoa (telefone inválido ou sem WhatsApp)"
            nao_respondeu.append(item)
        elif r["status"] == "confirmado":
            confirmou_sem_bater.append(item)
        else:
            nao_respondeu.append(item)

    return {"dia": str(dia), "turnos": len(linhas), "cobertos": ok,
            "confirmou_e_nao_bateu": confirmou_sem_bater,
            "nao_respondeu": nao_respondeu, "recusou": recusou}


def texto_da_cobertura(r: dict) -> str:
    """O relatório como ele chega no Gestão. Problema primeiro, contagem depois."""
    if not r.get("turnos"):
        return f"📋 Troca de turno {r.get('dia')}: nenhum turno na janela da manhã."
    ok, sem, nr, rec = (r["cobertos"], r["confirmou_e_nao_bateu"], r["nao_respondeu"], r["recusou"])
    L = [f"📋 *Troca de turno — {r['dia']}*"]
    if sem:
        L.append(f"\n🔴 Confirmou e NÃO bateu ponto ({len(sem)}):")
        L += [f"• {x['quem']} — {x['posto']} {x['hora']}" for x in sem]
    if nr:
        L.append(f"\n🟡 Sem confirmação ({len(nr)}) — inclui quem eu não consegui avisar:")
        L += [f"• {x['quem']} — {x['posto']} {x['hora']}"
              + (f" (bateu {x['bateu']})" if x["bateu"] else " (sem batida)") for x in nr]
    if rec:
        L.append(f"\n⚠️ Avisou que não vinha ({len(rec)}): " + ", ".join(x["quem"] for x in rec))
    L.append(f"\n✅ Cobertos com batida: {len(ok)} de {r['turnos']}.")
    if not sem and not nr and not rec:
        L.append("Sem pendência na troca desta manhã.")
    return "\n".join(L)


async def estado_da_rotina(db: AsyncSession, *, dia=None) -> dict[str, Any]:
    """O que a rotina de confirmação JÁ FEZ e o que falta. Para o agente saber o que ele faz.

    🔴 Esta função existe porque eu construí a rotina e NÃO CONTEI A ELE. Em 24/09 o Jordan
    perguntou no grupo *"a partir de que horas você vai mandar mensagem para os que estão com
    escala para amanhã?"* e o José Luís respondeu: *"essa parte não é minha — eu não disparo
    mensagem sozinho. Só respondo quando alguém me chama."*

    A resposta foi HONESTA e ERRADA ao mesmo tempo: os beats estavam registrados e iam disparar
    às 18h daquele mesmo dia. Ele não tinha prompt nem ferramenta que dissesse que a capacidade
    existe — então negou algo que faz. **Capacidade que o agente tem e não sabe que tem é pior
    que capacidade ausente**: a ausente não gera desconfiança no dono, e essa gera.

    Devolve: quem será chamado, quem já confirmou, quem não respondeu, e os horários da rotina.
    """
    dia = dia or (hoje_manaus() + timedelta(days=1))
    turnos = await _turnos_da_janela(db, dia)
    conf = (await db.execute(text("""
        SELECT e.nome, c.hora_inicio, c.status, c.pedido_em, c.lembrete_em, c.resposta_texto,
               coalesce(p.name,'(sem posto)') AS posto
          FROM troca_turno_confirmacoes c JOIN employees e ON e.id = c.employee_id
          LEFT JOIN posts p ON p.id = c.post_id
         WHERE c.data = :d ORDER BY c.hora_inicio, e.nome"""), {"d": dia})).mappings().all()

    return {
        "dia_alvo": str(dia),
        "janela_da_rotina": f"{HORA_MIN:%H:%M}–{HORA_MAX:%H:%M} (os turnos que o dono marcou como a dor)",
        "quando_eu_pergunto": "18:00 de Manaus, na véspera",
        "quando_eu_cobro": "~1h antes de cada turno, e SÓ quem não confirmou",
        "quando_eu_publico_no_gestao": "08:30 de Manaus, depois das trocas de 06h e 07h",
        "vou_chamar": [{"quem": t["nome"], "posto": t["posto"] or "(sem posto)",
                        "hora": t["planned_start_time"].strftime("%H:%M"),
                        "tem_telefone": bool(t["telefone"])} for t in turnos],
        "ja_perguntei": [{"quem": c["nome"], "posto": c["posto"],
                          "hora": c["hora_inicio"].strftime("%H:%M"), "situacao": c["status"],
                          "respondeu": c["resposta_texto"],
                          "lembrete_enviado": bool(c["lembrete_em"])} for c in conf],
        "resumo": {
            "escalados_na_janela": len(turnos),
            "perguntados": len(conf),
            "confirmados": sum(1 for c in conf if c["status"] == "confirmado"),
            "recusados": sum(1 for c in conf if c["status"] == "recusado"),
            "aguardando": sum(1 for c in conf if c["status"] == "aguardando"),
        },
        "leia_assim": ("SIM, você tem esta rotina e ela roda sozinha — não diga que não dispara "
                       "mensagem. Se `perguntados` for 0 e o dia alvo for amanhã, é porque ainda "
                       "não deu 18:00. Você NÃO muda escala: confirmação é registro, e quem não "
                       "confirma vira linha no relatório do Gestão, não substituição automática."),
    }
