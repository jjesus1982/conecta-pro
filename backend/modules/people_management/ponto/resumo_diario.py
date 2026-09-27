"""O dia de ponto fechado vai para quem decide — todo dia, sem acumular.

Jordan, 27/09/2026: *"ao final do dia sempre após todos terem batidos seus pontos, pyetra e
orlailson deve receber o resumo de quem bateu atraso, justificativas, hora de chegada, hora de
saida, saida pra almoço, volta de almoço, assim eles podem diariamente aprovar ou reprovar, não
deixando acumular"*.

## Por que 08:00 e não 20:00

⭐ **O último ponto do dia é batido no dia seguinte.** O noturno entra 18:00/19:00 e sai
06:00/07:00 da manhã seguinte — às 20:00 ele nem começou. Um resumo das 20:00 fecharia o diurno
e deixaria metade da operação de fora, justamente a metade em que a batida some mais.

Então o resumo sai às **08:00** e fala do `shift_date` de **ONTEM**: a essa hora todo turno
daquela data já terminou, inclusive o noturno que atravessou a madrugada. A Pyetra e o
Orlailson abrem o dia com a lista pronta, que é o que "não deixar acumular" significa na
prática.

⚠️ `shift_date` é a âncora, NUNCA a data da batida. Um turno 18:00→06:00 tem `shift_date` do
dia em que COMEÇOU, e a saída dele cai no dia seguinte no relógio — parear por data de batida
partiria o mesmo turno em dois dias e mostraria gente "sem entrada" e gente "sem saída" que na
verdade é a mesma pessoa.

## O que entra na lista

Só quem tem algo a DECIDIR ou algo FALTANDO. Quem bateu os quatro pontos no horário não gera
linha — vira contagem no rodapé. Uma lista em que 90% das linhas não pedem nada treina quem
lê a passar o olho, e aí a linha que importava passa junto.
"""

from __future__ import annotations

import logging
import os
from datetime import date as _date
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: A MESMA tolerância da parede e dos lembretes. Um número, um lugar — ver
#: `punch_service.registrar_batida` e `operacional.lembrete_ponto`.
TOLERANCIA_MIN = int(os.getenv("PONTO_TOLERANCIA_ANTES_MIN", "5"))

#: Quem aprova ponto. ⚠️ É REGRA, não lista de nomes: quem tem papel de aprovação E vínculo de
#: funcionário vivo E telefone no cadastro. Hoje isso devolve exatamente a Pyetra (`admin`) e o
#: Orlailson (`gerente_operacional`) — os dois que o Jordan nomeou. O Jordan também é `admin`,
#: mas não tem `employee_id` na conta, então não entra; a conta `mcp-service` idem.
#:
#: Aprovador novo com telefone passa a receber sozinho, sem ninguém editar código. Por isso o
#: envio LOGA os destinatários a cada rodada: expansão silenciosa de audiência é como dado de
#: DP vaza sem que ninguém perceba.
ROLES_APROVADOR = ("admin", "gerente_operacional")

#: Onde o resumo é publicado. O dono autorizou a voz do José Luís em DOIS grupos — Gestão e
#: Escritório — e escolheu este para o ponto: é onde a Pyetra e o Orlailson trabalham, e o
#: histórico mostra exatamente os dois como únicos autores.
GRUPO_DESTINO = "Escritório"

#: 🔴 NÃO FILTRA STATUS NEM TELEFONE AQUI, DE PROPÓSITO.
#:
#: Minha 1ª versão exigia `e.status = 'ativo'` e devolveu **NENHUM aprovador**: a Pyetra e o
#: Orlailson são `pj_ativo`. O resumo montava perfeito e não chegava a ninguém — verde que não
#: prova nada. O vocabulário real da coluna tem sete valores (`ativo`, `pj_ativo`,
#: `afastado_inss`, `inativo`, `demitido`, `suspenso`, `candidato`), e adivinhar um deles é
#: como se erra aqui.
#:
#: ⭐ E a correção NÃO é escrever o filtro certo: é não escrever um segundo filtro. Quem sabe
#: quem pode receber mensagem é `destinatario.resolver` — ele usa
#: `startswith(("ativo","pj_","afastado"))`, que aceita PJ e afastado e recusa demitido (e
#: `"inativo"` não casa com `"ativo"`, porque começa com "in"). Duas implementações da mesma
#: regra divergem na primeira mudança; foi assim que esta casa ficou com três pareadores de
#: batida. Aqui só se acha QUEM TEM O PAPEL; quem julga elegibilidade é a porta única, e cada
#: recusa dela aparece no log com nome e motivo em vez de sumir num WHERE.
_SQL_APROVADORES = """
SELECT e.id::text AS employee_id, e.nome, u.role
  FROM users u JOIN employees e ON e.id = u.employee_id
 WHERE u.is_active AND u.role = ANY(:roles)
 ORDER BY e.nome
"""

#: Os quatro marcos do dia de uma pessoa, com o previsto ao lado do realizado.
#:
#: ⚠️ `fim_previsto` soma um dia quando o fim é menor que o início: noturno cruza a meia-noite e
#: `TIME + 24 hours` **dá a volta** em vez de avançar o dia.
#:
#: ⚠️ A janela de batidas vai de 3h ANTES do início a 6h DEPOIS do fim. Os 3h são a mesma régua
#: de `supervisao.situacao_do_turno` e de `lembrete_ponto` — em 26/09 dois leitores da casa
#: usavam números diferentes para o mesmo fato e o sistema dizia as duas coisas no mesmo minuto.
_SQL_DIA = """
WITH t AS (
  SELECT sh.id AS shift_id, e.id AS employee_id, e.nome, p.name AS posto,
         sh.planned_start_time AS ini_prev,
         sh.planned_end_time   AS fim_prev,
         (sh.shift_date + sh.planned_start_time) AS ini_ts,
         (sh.shift_date + sh.planned_end_time
          + CASE WHEN sh.planned_end_time <= sh.planned_start_time
                 THEN INTERVAL '1 day' ELSE INTERVAL '0' END) AS fim_ts,
         coalesce(p.tem_intervalo_almoco, true) AS almoca,
         lower(coalesce(e.status,'')) AS status_emp
    FROM shifts sh
    JOIN posts p     ON p.id = sh.post_id
    JOIN employees e ON e.id = sh.employee_id
   WHERE sh.shift_date = CAST(CAST(:dia AS text) AS date)
     AND sh.is_active AND NOT sh.is_off_day
     AND lower(coalesce(sh.status,'')) IN ('scheduled','agendado','ativo')
     AND coalesce(e.is_homologacao, false) = false
     -- 🔴 NÃO filtra por `status = 'ativo'`. Medido em 7 dias: **2 DEMITIDOS e 1 AFASTADO do
     -- INSS têm turno ativo na escala**. Esconder esses três seria esconder justamente o que
     -- mais precisa de decisão — é o caso KEYSON, que em 26/09 foi publicado como escalado
     -- meses depois de sair. O resumo os mostra COM O RÓTULO, e quem decide decide.
)
SELECT t.*,
       (SELECT min(c.punch_timestamp) FROM gp_clock_punches c
         WHERE c.employee_id = t.employee_id AND c.punch_type = 'entrada'
           AND c.punch_timestamp BETWEEN t.ini_ts - interval '3 hours'
                                     AND t.fim_ts + interval '6 hours') AS entrada,
       (SELECT min(c.punch_timestamp) FROM gp_clock_punches c
         WHERE c.employee_id = t.employee_id AND c.punch_type = 'saida_almoco'
           AND c.punch_timestamp BETWEEN t.ini_ts AND t.fim_ts + interval '6 hours') AS alm_saida,
       (SELECT min(c.punch_timestamp) FROM gp_clock_punches c
         WHERE c.employee_id = t.employee_id AND c.punch_type = 'retorno_almoco'
           AND c.punch_timestamp BETWEEN t.ini_ts AND t.fim_ts + interval '6 hours') AS alm_volta,
       (SELECT max(c.punch_timestamp) FROM gp_clock_punches c
         WHERE c.employee_id = t.employee_id AND c.punch_type = 'saida'
           AND c.punch_timestamp BETWEEN t.ini_ts AND t.fim_ts + interval '6 hours') AS saida,
       (SELECT count(*) FROM gp_clock_punches c
         WHERE c.employee_id = t.employee_id AND c.device_type = 'contingencia'
           AND c.punch_timestamp BETWEEN t.ini_ts - interval '3 hours'
                                     AND t.fim_ts + interval '6 hours') AS n_contingencia,
       (SELECT string_agg(j.reason, E'\\n— ' ORDER BY j.created_at)
          FROM gp_justifications j JOIN gp_clock_punches c ON c.punch_id = j.punch_id
         WHERE c.employee_id = t.employee_id AND j.status = 'pendente'
           AND c.punch_timestamp BETWEEN t.ini_ts - interval '3 hours'
                                     AND t.fim_ts + interval '6 hours') AS justificativas
  FROM t
 ORDER BY t.ini_ts, t.nome
"""


#: Dias sem bater a partir dos quais a pessoa aparece na cauda. 10 dias cobre a folga do 12x36
#: (36h) com margem; férias e afastamento aparecem pelo rótulo do vínculo, não aqui.
DIAS_SUMIDO = 10

#: ⭐ 27/09/2026 — QUEM NÃO TEM TURNO NÃO GERA LINHA EM RESUMO NENHUM, E POR ISSO SOME.
#:
#: Descoberto ao corrigir a EIDY: o dono avisou que ela estava escalada no posto errado; ao tirar
#: os turnos errados ela ficou com ZERO turnos e desapareceu de todas as telas diárias — ausente
#: desde 11/09 e invisível. A correção abriu o buraco, e o buraco já existia para outras cinco.
#:
#: Medido no dia: **6 pessoas ativas** nessa situação, três delas citadas pelo próprio dono na
#: mesma conversa (Kelly Patricia, Eidy, Rilem). Duas NUNCA bateram ponto.
#:
#: ⚠️ `data_admissao` entra para não gritar com recém-contratado: quem foi admitido há 3 dias e
#: ainda não bateu não é um sumiço, é um acesso que ainda não fechou.
_SQL_SUMIDOS = f"""
SELECT e.nome, e.data_admissao,
       max(g.punch_timestamp)::date AS ultima,
       (SELECT count(*) FROM shifts s WHERE s.employee_id = e.id AND s.is_active
          AND s.shift_date >= (now() AT TIME ZONE 'America/Manaus')::date) AS turnos_futuros
  FROM employees e LEFT JOIN gp_clock_punches g ON g.employee_id = e.id
 WHERE lower(coalesce(e.status,'')) LIKE 'ativo%'
   AND coalesce(e.is_homologacao, false) = false
   AND (e.tipo_contrato IS NULL OR e.tipo_contrato <> 'pj')
 GROUP BY e.id, e.nome, e.data_admissao
HAVING (max(g.punch_timestamp) IS NULL
        AND (e.data_admissao IS NULL
             OR e.data_admissao < (now() AT TIME ZONE 'America/Manaus')::date - {DIAS_SUMIDO}))
    OR max(g.punch_timestamp) < (now() AT TIME ZONE 'America/Manaus')::date - {DIAS_SUMIDO}
 ORDER BY max(g.punch_timestamp) NULLS FIRST
"""

def _hhmm(ts) -> str:
    return ts.strftime("%H:%M") if ts else "—"


def _min(a, b) -> int | None:
    """Minutos de `a` menos `b`, ou None se faltar um dos dois."""
    if not a or not b:
        return None
    return int((a - b).total_seconds() // 60)


async def montar(db, dia) -> dict[str, Any]:
    """Monta o resumo do `shift_date` pedido. READ-ONLY: só lê e organiza."""
    linhas = (await db.execute(text(_SQL_DIA), {"dia": str(dia)})).mappings().all()
    problemas: list[dict] = []
    limpos = 0

    for r in linhas:
        atraso = _min(r["entrada"], r["ini_ts"])
        sobra = _min(r["saida"], r["fim_ts"])
        # 🔴 "SEM ALMOÇO" SÓ É FALHA ONDE O ALMOÇO EXISTE — e existe por DUAS condições, não uma.
        #
        # ⚠️ A primeira versão olhava só `posts.tem_intervalo_almoco` e acusou de "almoço
        # incompleto" gente de turno de QUATRO HORAS (07:00–11:00, 08:00–12:00): Antonio Carlos,
        # Vanderlice, Edilene, Kalel. Jornada de 4h não tem intervalo — CLT art. 71 só exige
        # acima de 6h. Eram 25 linhas de pendência em 30 turnos, e quase metade era invenção
        # minha. Lista que grita em tudo ensina a ignorar a lista.
        #
        # ⭐ A duração é do TURNO, não do posto. O posto diz se ali se almoça; o turno diz se
        # aquele dia era longo o bastante para haver almoço. As duas coisas juntas.
        _horas = (r["fim_ts"] - r["ini_ts"]).total_seconds() / 3600
        # ⚠️ E não existe "almoço incompleto" em quem NUNCA ENTROU: sem jornada não houve
        # intervalo a cumprir. Acusar isso empilha uma queixa falsa sobre uma verdadeira e faz
        # a linha grave parecer igual às outras.
        falta_almoco = (bool(r["almoca"]) and _horas > 6 and r["entrada"] is not None
                        and (not r["alm_saida"] or not r["alm_volta"]))
        motivos = []
        # ⚠️ Quando FALTAM AS DUAS pontas, os traços na linha de horários já dizem tudo e o
        # ícone ⬛ classifica: repetir "sem entrada; sem saída" em texto só gasta a tela.
        _mudo = r["entrada"] is None and r["saida"] is None
        if r["entrada"] is None:
            if not _mudo:
                motivos.append("*sem batida de entrada*")
        elif atraso is not None and atraso > TOLERANCIA_MIN:
            motivos.append(f"entrou *{atraso}min atrasada(o)*")
        if r["saida"] is None:
            if not _mudo:
                motivos.append("*sem batida de saída* (jornada aberta)")
        elif sobra is not None and sobra > TOLERANCIA_MIN:
            motivos.append(f"saiu *{sobra}min depois* (hora extra)")
        elif sobra is not None and sobra < -TOLERANCIA_MIN:
            motivos.append(f"saiu *{-sobra}min antes*")
        if falta_almoco:
            motivos.append("almoço incompleto")
        if r["n_contingencia"]:
            motivos.append(f"{r['n_contingencia']} batida(s) por contingência")
        # ⚠️ O rótulo do vínculo vem ANTES de qualquer horário: uma pessoa demitida escalada
        # não é um problema de ponto, é um problema de escala, e decidir o atraso dela seria
        # discutir o detalhe errado.
        _st = r["status_emp"]
        if _st and not _st.startswith("ativo"):
            motivos.insert(0, f"🔴 *vínculo: {_st.upper()}* — e mesmo assim está escalada(o)")

        # 🔴 27/09 — O QUE CONTA COMO PROBLEMA NÃO PODE DEPENDER DO TEXTO DE EXIBIÇÃO.
        #
        # Eu calei os motivos de quem não bateu NADA (os traços já diziam) e, como o teste de
        # "está limpo" olhava a lista de motivos, **as 6 pessoas sem nenhuma batida passaram a
        # contar como OK** — os limpos pularam de 7 para 13 e os seis casos mais graves do dia
        # sumiram da lista. Mudei a vitrine e o veredito mudou junto.
        #
        # ⭐ Agora o FATO é medido dos dados, e `motivos` é só como o fato aparece. É a mesma
        # família do erro mais caro desta casa: a lógica estava certa, a OBSERVAÇÃO é que
        # olhava a coisa errada.
        tem_problema = (
            r["entrada"] is None or r["saida"] is None
            or (atraso is not None and abs(atraso) > TOLERANCIA_MIN)
            or (sobra is not None and abs(sobra) > TOLERANCIA_MIN)
            or falta_almoco or bool(r["n_contingencia"])
            or bool(_st and not _st.startswith("ativo"))
            or bool(r["justificativas"])
        )
        if not tem_problema:
            limpos += 1
            continue
        # ⭐ GRAVIDADE ORDENA A LISTA. Quem não bateu NADA o turno inteiro não pode aparecer
        # embaixo de um atraso de 6 minutos — quem lê de cima para baixo decide primeiro o que
        # importa, e se parar no meio parou no lugar certo.
        if _st and not _st.startswith(("ativo", "pj_")):
            peso = -1           # demitido/inativo/suspenso escalado vem ANTES de tudo
        elif r["entrada"] is None and r["saida"] is None:
            peso = 0            # turno inteiro sem registro
        elif r["entrada"] is None or r["saida"] is None:
            peso = 1            # jornada aberta
        elif max(abs(atraso or 0), abs(sobra or 0)) > 30:
            peso = 2            # desvio grande de horário
        else:
            peso = 3            # desvio pequeno, contingência, almoço
        problemas.append({
            "peso": peso,
            "nome": r["nome"], "posto": r["posto"],
            "previsto": f"{str(r['ini_prev'])[:5]}–{str(r['fim_prev'])[:5]}",
            "entrada": _hhmm(r["entrada"]), "alm_saida": _hhmm(r["alm_saida"]),
            "alm_volta": _hhmm(r["alm_volta"]), "saida": _hhmm(r["saida"]),
            "motivos": motivos, "justificativas": r["justificativas"],
        })

    problemas.sort(key=lambda p: (p["peso"], p["nome"]))
    hoje = _date.today()
    sumidos = [
        {"nome": r["nome"],
         "ultima": r["ultima"].strftime("%d/%m") if r["ultima"] else None,
         "dias": (hoje - r["ultima"]).days if r["ultima"] else None,
         "turnos_futuros": int(r["turnos_futuros"] or 0)}
        for r in (await db.execute(text(_SQL_SUMIDOS))).mappings().all()
    ]
    return {"dia": str(dia), "turnos": len(linhas), "limpos": limpos, "problemas": problemas,
            "sumidos": sumidos}


#: Cada faixa vira uma SEÇÃO própria no relatório, com densidade diferente.
#:
#: ⭐ 27/09/2026 — Jordan: *"de uma forma bem estruturada, separada, organizada, não um amontoado
#: de informações"*. A 1ª versão listava todo mundo no mesmo formato de duas linhas: quem não
#: bateu NADA aparecia com `— · 🍽 —→— · —`, que é ruído puro, ao lado de quem tem desvio de
#: minutos, onde a linha de horários é justamente o que decide.
#:
#: Cada seção mostra só o que serve para DECIDIR aquele caso.
#: (ícone, título, mostra a linha dos 4 marcos?, uma linha só por pessoa?)
#:
#: ⚠️ O desvio PEQUENO é compacto de propósito: por definição são minutos, e três linhas para
#: cada um empurrava o caso grave para o fim de uma mensagem de 109 linhas. Quem lê decide de
#: cima para baixo; se parar no meio, tem de ter parado no lugar certo.
_FAIXAS: dict[int, tuple[str, str, bool, bool]] = {
    -1: ("🔴", "VÍNCULO NÃO ESTÁ ATIVO", False, False),
    0: ("⬛", "NENHUMA BATIDA NO TURNO", False, True),
    1: ("🟠", "JORNADA ABERTA", True, False),
    2: ("⏰", "FORA DO HORÁRIO", True, False),
    3: ("·", "DESVIO PEQUENO E CONTINGÊNCIA", False, True),
}


def _primeiro_e_ultimo(nome: str) -> str:
    """«MARIA DA SILVA SANTOS» → «Maria Santos». Quem lê conhece a equipe; nome inteiro em
    caixa alta estoura a linha do WhatsApp e empurra o horário para a linha seguinte."""
    ps = [x for x in str(nome or "").split() if len(x) > 2]
    return (f"{ps[0]} {ps[-1]}" if len(ps) > 1 else (ps[0] if ps else "?")).title()


def _posto_curto(posto: str) -> str:
    """Tira «Condomínio»/«Residencial» — todos são, e a palavra ocupa metade da linha."""
    t = str(posto or "")
    for p in ("Condomínio ", "Residencial ", "Condominio "):
        t = t.replace(p, "")
    return t


def _corta(txt: str, n: int) -> str:
    """Corta na PALAVRA, nunca no meio dela — e diz que cortou."""
    t = " ".join(str(txt or "").split())
    if len(t) <= n:
        return t
    return t[:t.rfind(" ", 0, n)] + "…"


def _marcos(p: dict) -> str:
    """A linha dos quatro pontos, só onde ela decide alguma coisa."""
    return f"{p['entrada']} → {p['saida']}   🍽 {p['alm_saida']}→{p['alm_volta']}"


def texto(dados: dict) -> str | None:
    """A mensagem. Devolve None quando o dia foi limpo — dia sem decisão não gera mensagem.

    ⭐ SILÊNCIO QUANDO NÃO HÁ O QUE DECIDIR é requisito, não economia. Um resumo que chega todo
    dia dizendo "nada a fazer" ensina a não abrir o resumo, e aí o dia que tinha sete decisões
    chega no mesmo envelope já ignorado.
    """
    if not dados["problemas"] and not dados.get("sumidos"):
        return None

    d = dados["dia"]
    out = [f"📋 *PONTO DE {d[8:10]}/{d[5:7]}*",
           "_Para aprovar ou reprovar — Pyetra e Orlailson_", ""]

    for peso, (icone, titulo, com_marcos, compacto) in _FAIXAS.items():
        gente = [p for p in dados["problemas"] if p["peso"] == peso]
        if not gente:
            continue
        out.append(f"*{icone} {titulo}* — {len(gente)}")
        for p in gente:
            curto = _primeiro_e_ultimo(p["nome"])
            if compacto:
                razao = f" · _{'; '.join(p['motivos'])}_" if p["motivos"] else ""
                out.append(f"  • *{curto}* — {_posto_curto(p['posto'])} {p['previsto']}{razao}")
                continue
            out.append(f"  • *{curto}* — {_posto_curto(p['posto'])} {p['previsto']}")
            if com_marcos:
                out.append(f"     {_marcos(p)}")
            if p["motivos"]:
                out.append(f"     _{'; '.join(p['motivos'])}_")
            if p["justificativas"]:
                out.append(f"     💬 _{_corta(p['justificativas'], 130)}_")
        out.append("")

    if dados.get("sumidos"):
        out.append(f"*👤 SEM BATER HÁ MAIS DE {DIAS_SUMIDO} DIAS* — {len(dados['sumidos'])}")
        out.append("  _não têm turno hoje, então não aparecem acima_")
        for x in dados["sumidos"]:
            quando = f"última em {x['ultima']} ({x['dias']}d)" if x["ultima"] else "*nunca bateu*"
            alerta = (f" · ⚠️ *{x['turnos_futuros']}* turno(s) futuro(s)"
                      if x["turnos_futuros"] else "")
            out.append(f"  • {x['nome']} — {quando}{alerta}")
        out.append("")

    if dados["limpos"]:
        out.append(f"✅ *{dados['limpos']}* bateram os quatro pontos no horário.")
    out.append("👉 *erp.conectamais.pro* → Aprovações")
    return "\n".join(out)


async def conferir_com_hermes(dados: dict) -> str | None:
    """⭐ SEGUNDA LEITURA, POR OUTRA FONTE. Devolve a linha de conferência, ou None.

    🔴 POR QUE EXISTE (27/09/2026). Jordan: *"preciso que ele mostre evidências de que fez,
    provas de que aquilo que foi pedido realmente foi feito e funcionou, se ele não conseguir
    ele informa"*.

    ⭐ O resumo é montado por consultas MINHAS ao banco. Ele pode estar certo e pode estar
    errado — e o dia inteiro mostrou as duas coisas: acusei 316 relatórios quando eram 74,
    contei 25 pendências quando eram 18, dei a Eidy como escalada num posto que não é dela.
    **Um número conferido por quem o produziu não é conferido.**
    O Hermes lê o MESMO dia por `ponto_dashboard`/`presenca_ao_vivo`, que são outro caminho
    até o mesmo fato, e diz se bate.

    ⚠️ Best-effort com resultado DITO: se ele não responder, a linha diz que não conferiu.
    Omitir a conferência faria o relatório parecer verificado quando não foi — que é a
    diferença exata entre «verde» e «verde que prova alguma coisa».
    """
    from modules.ai.conversation.services.hermes_client import (
        HermesIndisponivel,
        perguntar_hermes,
    )

    # ⚠️ CONFERE O QUE DÁ PARA CONFERIR HOJE, não o recorte de ontem.
    #
    # A 1ª versão pedia para validar as contagens do DIA anterior e o Hermes respondeu, com
    # razão: *"nenhuma tool do ERP devolve o recorte do dia 26/09 — `presenca_ao_vivo` é ao
    # vivo e só traz hoje; `ponto_dashboard` e `painel_espelho_ponto` entregam só o acumulado
    # do mês"*. Ele estava certo, e isso é um ACHADO: falta uma ferramenta de ponto por dia.
    #
    # ⭐ Mas um rodapé "não consegui" todo santo dia é ruído. A CAUDA é verificável agora e é
    # a parte mais sujeita a envelhecer: quem não bate há dez dias é fato cumulativo, e se
    # alguém voltou a bater hoje a minha lista está errada — que é exatamente o tipo de erro
    # que eu quero que outra fonte pegue.
    # ⚠️ TRÊS NOMES, NÃO OITO. Medido: conferir 6 pessoas uma a uma estourou 180s e o resumo
    # foi SEM conferência. Prova cara que não chega é prova que não existe — melhor conferir
    # três com folga do que oito e perder tudo.
    nomes = ", ".join(x["nome"] for x in (dados.get("sumidos") or [])[:3]) or "(ninguém)"
    pedido = (
        f"Eu afirmo que estas pessoas estão ATIVAS e NÃO batem ponto há mais de "
        f"{DIAS_SUMIDO} dias:\n{nomes}\n\n"
        "CONFIRA cada uma com as ferramentas do ERP (espelho de ponto, presença, ficha). "
        "Responda em UMA linha começando com:\n"
        "· CONFERE — se todas realmente estão sem bater\n"
        "· NAO CONFERE — se alguma bateu recentemente; diga QUEM e QUANDO\n"
        "· NAO CONSEGUI — se a ferramenta não responder; diga qual e por quê\n"
        "Cite sempre a ferramenta que usou."
    )
    try:
        txt, _ = await perguntar_hermes(
            messages=[{"role": "user", "content": pedido}],
            system_prompt=(
                "Você é o Hermes, do Conecta PRO. Você tem as ferramentas MCP do ERP. "
                "Sua função aqui é CONFERIR o que outro sistema produziu — não concordar. "
                "Se divergir, diga o que VOCÊ achou e de onde. NUNCA diga que conferiu sem "
                "ter chamado a ferramenta.\n\n"
                "⚠️ SEJA ECONÔMICO: prefira UMA consulta que traga todos de uma vez "
                "(ex.: listar_funcionarios, colaboradores_sem_escala) a uma por pessoa. "
                "Responda em uma linha só."),
            # prazo de rotina de fundo: às 08:00 ninguém está esperando na tela, e prova que
            # não chega a tempo é prova que não existe
            timeout=float(os.getenv("RESUMO_HERMES_TIMEOUT", "420")))
        linha = " ".join((txt or "").split())[:320]
        logger.info("resumo_diario: conferência do Hermes — %s", linha[:120])
        return linha or None
    except HermesIndisponivel as exc:
        logger.warning("resumo_diario: Hermes fora (%s) — resumo vai SEM conferência", exc)
        return f"NAO CONSEGUI conferir com o Hermes: {str(exc)[:90]}"
    except Exception as exc:  # noqa: BLE001
        logger.error("resumo_diario: conferência falhou (%s)", exc)
        return f"NAO CONSEGUI conferir com o Hermes: {str(exc)[:90]}"


async def enviar(db, dia) -> dict[str, Any]:
    """Publica o resumo no grupo ESCRITÓRIO, onde a Pyetra e o Orlailson já trabalham.

    🔴 27/09/2026 — MUDOU DE PRIVADO PARA GRUPO. Jordan: *"o resumo do ponto deve ser postado
    pelo José Luís no grupo escritório"*.

    ⭐ Por que faz sentido: o Escritório tem exatamente os dois que decidem, e nada mais.
    Medido: dois autores no histórico, Pyetra e Orlailson, zero gente de fora. No privado cada
    um via a sua cópia e não via a decisão do outro; no grupo os dois veem a mesma lista e
    quem tratar pode dizer ali mesmo.

    ⚠️ Publicação NÃO passa pela parede de "só fala quando chamado" — aquela governa CONVERSA.
    Relatório é o que o dono autorizou explicitamente: *"pode mandar relatório e tudo mais"*.
    """
    from modules.integrations.connectors.whatsapp import supervisao as _sup

    dados = await montar(db, dia)
    msg = texto(dados)
    if msg:
        # ⭐ A PROVA VAI NO RODAPÉ, seja ela boa ou ruim. Ver `conferir_com_hermes`.
        prova = await conferir_com_hermes(dados)
        if prova:
            icone = ("✅" if prova.upper().startswith("CONFERE")
                     else "⚠️" if prova.upper().startswith(("NAO CONFERE", "NÃO CONFERE"))
                     else "❔")
            msg += f"\n\n{icone} _Conferido pelo Hermes: {prova}_"
    if not msg:
        logger.info("resumo_diario %s: dia limpo (%s turnos) — ninguém recebe", dia,
                    dados["turnos"])
        return {**dados, "publicado": False, "silencio": True}

    destino = (await db.execute(text(
        "SELECT chatwoot_conversation_id FROM wa_grupos "
        " WHERE nome = :g AND modo = 'falar' AND chatwoot_conversation_id IS NOT NULL"),
        {"g": GRUPO_DESTINO})).scalar()
    if not destino:
        # ⚠️ FALHA DITA, NÃO SILENCIOSA. Sem destino o resumo sumiria e o silêncio pareceria
        # "dia limpo" — que é a pior confusão possível num relatório de exceções.
        logger.error("resumo_diario: grupo %r não existe ou não está em modo `falar` — "
                     "%s pendência(s) NÃO publicadas", GRUPO_DESTINO, len(dados["problemas"]))
        return {**dados, "publicado": False, "erro": f"sem grupo {GRUPO_DESTINO}"}

    publicado = bool(await _sup._publicar_no_grupo(int(destino), msg))
    logger.info("resumo_diario %s: %s pendência(s) → grupo %s (publicado=%s)",
                dia, len(dados["problemas"]), GRUPO_DESTINO, publicado)
    return {**dados, "publicado": publicado, "destino": GRUPO_DESTINO}
