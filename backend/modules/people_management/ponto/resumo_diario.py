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
    return {"dia": str(dia), "turnos": len(linhas), "limpos": limpos, "problemas": problemas}


#: Rótulo de cada faixa de gravidade, na ordem em que a lista sai.
_FAIXAS = {
    -1: ("🔴", "escalada(o) sem vínculo ativo"),
    0: ("⬛", "turno inteiro sem nenhuma batida"),
    1: ("🟠", "jornada aberta (falta entrada ou saída)"),
    2: ("⏰", "desvio grande de horário"),
    3: ("·", "desvio pequeno, contingência ou almoço"),
}


def texto(dados: dict) -> str | None:
    """A mensagem. Devolve None quando o dia foi limpo — dia sem decisão não gera mensagem.

    ⭐ SILÊNCIO QUANDO NÃO HÁ O QUE DECIDIR é requisito, não economia. Um resumo que chega todo
    dia dizendo "nada a fazer" ensina a não abrir o resumo, e aí o dia que tinha sete decisões
    chega no mesmo envelope já ignorado.

    🔴 E O TAMANHO É PARTE DA CORREÇÃO. A 1ª versão gastava 5 linhas por pessoa: com 24
    pendências deu **6.404 caracteres e 130 linhas** — dentro do limite do WhatsApp e ilegível
    num celular. Resumo que não se lê é igual a resumo que não existe, e aí o efeito prático é
    o mesmo acúmulo que o Jordan pediu para acabar.
    """
    if not dados["problemas"]:
        return None

    d = dados["dia"]
    out = [f"📋 *Ponto de {d[8:10]}/{d[5:7]}* — {len(dados['problemas'])} para decidir, "
           f"{dados['limpos']} ok", ""]

    # CABEÇALHO: a forma do dia antes do detalhe. Quem lê decide onde gastar atenção sem ter
    # de percorrer a lista inteira para descobrir que havia dois casos graves no meio dela.
    for peso, (icone, rotulo) in _FAIXAS.items():
        n = sum(1 for p in dados["problemas"] if p["peso"] == peso)
        if n:
            out.append(f"{icone} *{n}* — {rotulo}")
    out.append("")

    for i, p in enumerate(dados["problemas"], 1):
        icone = _FAIXAS[p["peso"]][0]
        out.append(f"{icone} *{i}. {p['nome']}* · {p['posto']} {p['previsto']}")
        out.append(f"    {p['entrada']} · 🍽 {p['alm_saida']}→{p['alm_volta']} · {p['saida']}"
                   + ("  |  " + "; ".join(p["motivos"]) if p["motivos"] else ""))
        if p["justificativas"]:
            # ⚠️ Corta em 200 e DIZ que cortou. Justificativa inteira mora na Central; truncar
            # em silêncio faria a decisão sair com meia informação parecendo informação inteira.
            j = " ".join(p["justificativas"].split())
            out.append(f"    💬 _{j[:200]}_" + ("… *(texto completo na Central)*"
                                                if len(j) > 200 else ""))

    out += ["", "Aprovar ou reprovar: *erp.conectamais.pro → Aprovações*."]
    return "\n".join(out)


async def enviar(db, dia) -> dict[str, Any]:
    """Manda o resumo aos aprovadores. Telefone vem do CADASTRO, pela porta única.

    ⚠️ `destinatario.mandar` não aceita telefone por parâmetro — foi assim que o guia do Jair
    chegou ao Antonio Carlos em 26/09. Aqui se passa o `employee_id`, que é o identificador que
    não tem como ser ambíguo (há cinco ANTONIO nesta casa).
    """
    from modules.integrations.connectors.whatsapp.destinatario import mandar

    dados = await montar(db, dia)
    msg = texto(dados)
    if not msg:
        logger.info("resumo_diario %s: dia limpo (%s turnos) — ninguém recebe", dia,
                    dados["turnos"])
        return {**dados, "enviados": 0, "silencio": True}

    alvos = (await db.execute(text(_SQL_APROVADORES),
                              {"roles": list(ROLES_APROVADOR)})).mappings().all()
    # audiência NUNCA silenciosa: se a regra passar a alcançar gente nova, o log diz quem
    logger.info("resumo_diario %s: %s problema(s) → %s", dia, len(dados["problemas"]),
                ", ".join(a["nome"] for a in alvos) or "NINGUÉM")
    if not alvos:
        logger.error("resumo_diario: nenhum aprovador com telefone — o resumo não tem para onde "
                     "ir. Confira `users.role` e o celular no cadastro.")
        return {**dados, "enviados": 0, "erro": "sem aprovador com telefone"}

    enviados = 0
    for a in alvos:
        try:
            r = await mandar(db, quem=a["employee_id"], texto=msg,
                             motivo=f"resumo diário de ponto de {dia}")
            if r.get("ok"):
                enviados += 1
            else:
                logger.warning("resumo_diario: não entregou a %s — %s", a["nome"],
                               r.get("motivo"))
        except Exception as exc:  # noqa: BLE001 — um destinatário não derruba o outro
            logger.error("resumo_diario: falha ao enviar a %s — %s", a["nome"], exc)
    return {**dados, "enviados": enviados, "alvos": [a["nome"] for a in alvos]}
