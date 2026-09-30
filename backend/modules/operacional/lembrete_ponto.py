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
# 🔴 26/09/2026 — "APP" ERA MENTIRA, E ELA ENSINOU O AGENTE A ERRAR.
# Jordan: *"não usamos app ainda, usamos o link do sistema do portal do funcionário no
# navegador"*. Estas duas frases saíam para TODO MUNDO, todos os dias, dizendo "app" — e o José
# Luís, sem nenhum fato melhor no contexto, improvisou a partir delas: mandou o Wisley, recém
# contratado, *instalar o Tangerino*, que está DESLIGADO desde 13/09. O rapaz ia baixar um app
# morto e continuar sem bater.
#
# ⚠️ A lição não é sobre o texto: é que **o agente aprende com o que a casa diz**. Uma frase
# errada repetida 1.500 vezes vira a verdade dele. Medido: 1.292 batidas `mobile` com
# `device_id CEL-…` (navegador do celular) e ZERO `tangerino` depois de 13/09.
# ⭐ 27/09/2026 — OS 5 MINUTOS SÃO **UM** NÚMERO, E GOVERNAM AS TRÊS COISAS.
#
# Jordan: *"coloca como regra geral também para todas as batidas de ponto o josé luis avisar
# com os mesmos 5m antes das batidas de ponto e 5m do que deveria ser as batidas de ponto,
# vamos usar esses mesmos 5m para avisar e para cobrar, assim vamos evitar batidas atrasada e
# evitar batidas antes da hora, e isso vale para todas as batidas"*.
#
# A mesma tolerância aparece em três lugares que antes eram independentes:
#
#   1. a PAREDE recusa a batida adiantada     (`punch_service`, `PONTO_TOLERANCIA_ANTES_MIN`)
#   2. a JUSTIFICATIVA é exigida além dela    (`punch_service`, mesmo env)
#   3. o AVISO sai 5 min antes e a COBRANÇA 5 min depois          (aqui)
#
# ⚠️ Por isso `TOLERANCIA_MIN` lê a MESMA variável de ambiente que a parede. Se alguém mudar
# para 10 e este módulo continuasse em 5, o sistema avisaria num minuto e recusaria em outro —
# é a família de defeito mais caro desta casa: **lógica certa, observação errada**. Um número,
# um lugar.
TOLERANCIA_MIN = int(os.getenv("PONTO_TOLERANCIA_ANTES_MIN", "5"))

# 🔴 26/09/2026 — "APP" ERA MENTIRA, E ELA ENSINOU O AGENTE A ERRAR.
# Jordan: *"não usamos app ainda, usamos o link do sistema do portal do funcionário no
# navegador"*. As frases antigas saíam para TODO MUNDO, todos os dias, dizendo "app" — e o José
# Luís, sem nenhum fato melhor no contexto, improvisou a partir delas: mandou o Wisley, recém
# contratado, *instalar o Tangerino*, que está DESLIGADO desde 13/09. O rapaz ia baixar um app
# morto e continuar sem bater.
#
# ⚠️ A lição não é sobre o texto: é que **o agente aprende com o que a casa diz**. Uma frase
# errada repetida 1.500 vezes vira a verdade dele. Medido: 1.292 batidas `mobile` com
# `device_id CEL-…` (navegador do celular) e ZERO `tangerino` depois de 13/09.
_PORTAL = "https://erp.conectamais.pro → Meu Espaço"

#: 🔴 A SAÍDA PARA O ALMOÇO NÃO ESTÁ AQUI, E ISSO É DADO FALTANDO — NÃO ESQUECIMENTO.
#: `shifts` guarda a DURAÇÃO do intervalo (`planned_break_minutes`) e **nenhuma hora prevista**
#: para ele. Sem hora prevista não existe "5 minutos antes": eu teria de inventar um horário, e
#: aí o aviso sairia na hora errada com cara de certo. A volta do almoço, ao contrário, TEM
#: referência real — a saída que a própria pessoa bateu, mais a duração. Enquanto o dono não
#: decidir se entra um `planned_break_start`, este marco fica de fora e dito em voz alta.
MARCO_SEM_HORARIO = "saida_almoco"

#: A referência de cada marco: o INSTANTE que devia ter sido batido.
#: ⚠️ `_REF_SAIDA` soma um dia quando o fim é menor que o início — noturno cruza a meia-noite e
#: `TIME + 24 hours` **dá a volta** em vez de avançar o dia.
#: ⭐ 29/09/2026 — A HORA CORRIGIDA À MÃO MANDA AQUI TAMBÉM.
#:
#: A CELIANE recebeu, em 28 e 29/09: «Seu turno no Condomínio Ideal Flores da Cidade começa em 5
#: minutos, às **08:00**» — disparado às 07:55. Ela entra às **09:00**, e o horário certo estava
#: gravado em `ponto_horario_vigencia` desde 24/09, pelo próprio dono, no grupo.
#:
#: O mesmo cadastro errado fazia `punch_service` RECUSAR a batida dela por 60 minutos de atraso
#: inexistente. Aquele lado foi consertado hoje; este NÃO, e é o pior dos dois: recusar ela
#: percebe e reclama — **o lembrete ensina a hora errada e ela acredita**.
#:
#: ⚠️ Medido: 43 arquivos usam `planned_start_time` e apenas 2 liam a vigência. Este é o terceiro,
#: escolhido porque é o que FALA com a pessoa. Os outros 40 estão no relatório, não consertados.
#:
#: Fica como subconsulta correlacionada de propósito: `_REF_*` é interpolado em várias consultas
#: e um JOIN exigiria mexer no FROM de cada uma — aqui a correção entra em todas de uma vez,
#: inclusive no `to_char({ref})` que escreve a hora NA MENSAGEM. Um conserto, dois efeitos.
def _hora_vigente(campo: str) -> str:
    """Horário efetivo do turno: o corrigido à mão se houver vigência na data, senão o cadastro."""
    return (
        f"coalesce((SELECT hv.{campo} FROM ponto_horario_vigencia hv "
        "           WHERE hv.employee_id = sh.employee_id "
        "             AND hv.vigencia_inicio <= sh.shift_date "
        "             AND (hv.vigencia_fim IS NULL OR hv.vigencia_fim >= sh.shift_date) "
        "           ORDER BY hv.vigencia_inicio DESC LIMIT 1), "
        f"         sh.planned_{'start' if campo == 'entrada' else 'end'}_time)"
    )


_HORA_ENTRADA = _hora_vigente("entrada")
_HORA_SAIDA = _hora_vigente("saida")

_REF_ENTRADA = f"(sh.shift_date + {_HORA_ENTRADA})"
_REF_SAIDA = (
    f"(sh.shift_date + {_HORA_SAIDA} + CASE WHEN {_HORA_SAIDA} <= "
    f"{_HORA_ENTRADA} THEN INTERVAL '1 day' ELSE INTERVAL '0' END)"
)
#: ⭐ A volta do almoço é o único marco cuja hora prevista sai de uma BATIDA, não da escala:
#: quem saiu 12:07 para 60 minutos deve voltar 13:07. Medido em 7 dias: **99 saídas para almoço
#: contra 88 voltas** — 11 almoços sem volta registrada, que é exatamente o que a cobrança pega.
_REF_RETORNO = (
    "((SELECT max(cp.punch_timestamp) FROM gp_clock_punches cp "
    "   WHERE cp.employee_id = e.id AND cp.punch_type = 'saida_almoco' "
    f"    AND cp.punch_timestamp >= {_REF_ENTRADA}) "
    " + (coalesce(sh.planned_break_minutes, 60) || ' minutes')::interval)"
)

#: Cada marco: o código base no log, a referência, como saber que já bateu, e os textos.
#:
#: ⚠️ `base` existe porque `ponto_lembrete_log.etapa` é **smallint** com PK `(shift_id, etapa)`.
#: O código gravado é `base + delta`, então (entrada, −5) e (saída, −5) nunca colidem no mesmo
#: turno. A entrada mantém `base=0` de propósito: o código 25 continua sendo o 25 de antes e o
#: histórico de dedup da conversa do José Luís não zera.
MARCOS: dict[str, dict] = {
    "entrada": {
        "base": 0,
        "ref": _REF_ENTRADA,
        # a janela de 3h/12h e "qualquer batida" são deliberadas: é a MESMA régua de
        # `supervisao.situacao_do_turno`. Ver o comentário longo no SQL abaixo.
        "ja_bateu": (
            "AND NOT EXISTS (SELECT 1 FROM gp_clock_punches cp "
            "  WHERE cp.employee_id = e.id "
            "    AND coalesce(cp.status,'') NOT IN ('facial_reprovado') "
            f"   AND cp.punch_timestamp BETWEEN ({_REF_ENTRADA} - interval '3 hours') "
            f"                              AND ({_REF_ENTRADA} + interval '12 hours'))"
        ),
        "textos": {
            -TOLERANCIA_MIN: (
                "Seu turno no {posto} começa em {tol} minutos, às {hora}. Bata o ponto pelo "
                "navegador do celular: " + _PORTAL + "\n\n⚠️ Bata *às {hora}*, não antes — "
                "antes do horário o sistema não aceita, e depois conta atraso."
            ),
            TOLERANCIA_MIN: (
                "Passou das {hora} e ainda não entrou sua batida de *entrada* no {posto}. "
                "Bata agora em " + _PORTAL + " — o sistema vai pedir o motivo do atraso, e "
                "ele vai direto para a supervisão aprovar."
            ),
            # ⭐ 11/09/2026 — A ÚLTIMA NÃO COBRA: PERGUNTA. Jordan: *"ele não puxa conversa. Só
            # responde. Quem não bateu às 07:10 recebe um lembrete automático genérico — ele
            # podia perguntar 'tá tudo bem?' e resolver ali"*. E resolveu: a pesquisa daquele
            # dia trouxe três defeitos reais que ninguém tinha reportado em semanas.
            #
            # Repetir um terceiro aviso não informa nada que a pessoa já não saiba — ela sabe
            # que não bateu. O que falta é alguém perguntar POR QUÊ. A resposta cai no José
            # Luís, que reconhece funcionário pelo telefone e resolve ali: ver o ponto,
            # registrar contingência, justificar, abrir pendência para o DP.
            25: (
                "Oi! Aqui é o José Luís — eu cuido do ponto junto com a Pyetra. Vi que seu "
                "turno das {hora} no {posto} começou e ainda não entrou batida sua aqui. Está "
                "tudo bem? Se o sistema não estiver deixando bater, me conta o que aparece na "
                "tela que eu resolvo agora."
            ),
        },
    },
    "retorno_almoco": {
        "base": 200,
        "ref": _REF_RETORNO,
        "ja_bateu": (
            "AND NOT EXISTS (SELECT 1 FROM gp_clock_punches cp "
            "  WHERE cp.employee_id = e.id AND cp.punch_type = 'retorno_almoco' "
            f"   AND cp.punch_timestamp >= {_REF_ENTRADA})"
        ),
        # 🔴 27/09/2026 — NÃO COBRE VOLTA DE ALMOÇO EM POSTO QUE NÃO ALMOÇA.
        #
        # Quatro postos (Green Hills, Prime Arena, Villa dei Fiori, Villa dos Pássaros) pagam
        # **intrajornada** justamente porque o agente não para: bate entrada e saída, nada mais.
        # Medido hoje: o EULER, do Prime Arena, tem como única batida do turno um
        # `saida_almoco` às 05:56 — que é a SAÍDA dele às 06:00 com o botão errado. O JAIR fez
        # o mesmo par às 15:13/15:14 de ontem, um minuto de diferença.
        #
        # ⚠️ Sem esta linha, o lembrete cobraria do Euler a volta de um almoço que o posto dele
        # não tem, usando a batida errada como prova de que ele saiu para almoçar. **Um dado
        # errado à montante vira mensagem confiante à jusante** — e a mensagem ensina a pessoa
        # a repetir o erro.
        # 🔴 30/09/2026, 01:21 — INTERVALO ZERO MANDAVA A PESSOA VOLTAR NO INSTANTE EM QUE SAIU.
        #
        # O DANIEL bateu `saida_almoco` às **01:16** e às 01:21 recebeu «Passou das **01:16** e
        # você não bateu a volta do almoço». A conta é `saída + intervalo`, e o turno dele de
        # 29/09 tem `planned_break_minutes = 0` — enquanto TODOS os outros turnos dele (01/10 em
        # diante) têm 60.
        #
        # ⭐ O `coalesce(..., 60)` do `_REF_RETORNO` defende contra NULL e **aceita o zero como
        # intervalo real**. Zero não é «intervalo de zero minuto»: é «não há intervalo».
        #
        # ⚠️ E não é caso isolado: medido na janela de ±30 dias, **383 turnos com intervalo 0,
        # em 34 pessoas** (contra 1.387 com 60). Oito dessas pessoas têm turnos com zero E batem
        # almoço na prática — a contradição está no cadastro, não nelas.
        #
        # A guarda de POSTO (`tem_intervalo_almoco`) não pega isto: o Ideal Flores TEM intervalo,
        # e o zero estava no TURNO. Duas fontes, duas guardas.
        "extra": ("AND coalesce(p.tem_intervalo_almoco, true) = true "
                  "AND coalesce(sh.planned_break_minutes, 60) > 0"),
        "textos": {
            -TOLERANCIA_MIN: (
                "Seu intervalo no {posto} termina às {hora}, em {tol} minutos. Bata a *volta "
                "do almoço* no horário em " + _PORTAL + "."
            ),
            TOLERANCIA_MIN: (
                "Passou das {hora} e você não bateu a *volta do almoço* no {posto}. Bata "
                "agora em " + _PORTAL + " — o sistema vai pedir o motivo."
            ),
        },
    },
    "saida": {
        "base": 400,
        "ref": _REF_SAIDA,
        "ja_bateu": (
            "AND NOT EXISTS (SELECT 1 FROM gp_clock_punches cp "
            "  WHERE cp.employee_id = e.id AND cp.punch_type = 'saida' "
            f"   AND cp.punch_timestamp BETWEEN ({_REF_SAIDA} - interval '3 hours') "
            f"                              AND ({_REF_SAIDA} + interval '6 hours'))"
        ),
        # ⚠️ Só cobra saída de quem ENTROU. Mandar "bata a saída" para quem nunca bateu a
        # entrada é ruído em cima de um problema que já é do vigia — e ainda ensina a pessoa a
        # bater saída sem entrada, que produz jornada aberta e não fecha nem à mão.
        "extra": (
            "AND EXISTS (SELECT 1 FROM gp_clock_punches cp "
            "  WHERE cp.employee_id = e.id AND cp.punch_type = 'entrada' "
            f"   AND cp.punch_timestamp BETWEEN ({_REF_ENTRADA} - interval '3 hours') "
            f"                              AND {_REF_SAIDA})"
        ),
        "textos": {
            -TOLERANCIA_MIN: (
                "Seu turno no {posto} termina às {hora}, em {tol} minutos. Bata a *saída* em "
                + _PORTAL + "\n\n⚠️ Bata *às {hora}* — depois do horário o sistema vai pedir "
                "o motivo, porque conta hora extra."
            ),
            TOLERANCIA_MIN: (
                "Passou das {hora} e ainda não entrou sua batida de *saída* no {posto}. Bata "
                "agora em " + _PORTAL + " — sem ela a jornada fica aberta e o DP tem de "
                "corrigir à mão."
            ),
        },
    },
}

#: União plana de TODOS os textos, pela chave que vai ao log. É o que o oráculo do "sem app"
#: varre — e agora ele cobre os 7 textos dos três marcos, não só os da entrada.
ETAPAS: dict[int, str] = {
    spec["base"] + delta: texto
    for spec in MARCOS.values()
    for delta, texto in spec["textos"].items()
}

# Dono, 07/09/2026 ("destrava tudo, deixa tudo funcionando"): o lembrete rodou meses em modo
# DRY — montava as mensagens certas (5 na janela das 17:45 de hoje) e não enviava, porque a
# variável nunca foi posta no ambiente. Ligado por padrão; PONTO_LEMBRETE_ENABLED=false desliga.
PONTO_LEMBRETE_ENABLED = os.getenv("PONTO_LEMBRETE_ENABLED", "true").lower() == "true"

# ponytail: teto por rodada protege o número Baileys de uma escala malformada
# (ex.: 300 turnos com o mesmo horário de início). O excedente vai para o log e
# para o retorno da task, nunca some em silêncio. Subir só depois de medir o
# volume real de um dia.
TETO_POR_RODADA = 30


def etapa_log(marco: str, delta_min: int) -> int:
    """Código gravado em `ponto_lembrete_log.etapa` = base do marco + o delta.

    ⚠️ A coluna é **smallint** com PK `(shift_id, etapa)`. Sem o `base`, o aviso de entrada e o
    aviso de saída do mesmo turno teriam o mesmo código −5 e o segundo seria engolido pelo
    `ON CONFLICT DO NOTHING` — a pessoa receberia o aviso da entrada e nunca o da saída.
    """
    return int(MARCOS[marco]["base"]) + int(delta_min)


#: Filtros que valem para os TRÊS marcos — em UM lugar de propósito.
#:
#: ⚠️ Eram uma consulta só; ao virar três, cada linha daqui passou a ser um lugar onde as
#: versões podem divergir. O `is_homologacao` é o exemplo que já custou caro nesta casa: ele
#: existe para o time de homologação nunca receber mensagem de verdade, e tem oráculo próprio
#: (`test_oraculo_homologacao_nao_recebe_mensagem`). Se eu tivesse copiado o WHERE três vezes,
#: bastaria esquecer uma para começar a mandar WhatsApp para dado de teste.
_FILTROS_COMUNS = """
  AND sh.is_active = TRUE
  AND sh.is_off_day = FALSE
  AND lower(coalesce(sh.status,\'\')) IN (\'scheduled\',\'agendado\',\'ativo\')
  AND coalesce(e.is_homologacao, false) = false
  AND e.status = \'ativo\'
  AND (e.tipo_contrato = \'clt\' OR e.tipo_contrato IS NULL)
  AND (e.tipo_contrato IS DISTINCT FROM \'pj\')
""" + SQL_NAO_AUSENTE_HOJE


def sql_do_marco(marco: str) -> str:
    """Pendentes deste marco, com `delta_min` medido contra o horário previsto DELE.

    🔴 A JANELA DE DATA É DE DOIS DIAS, E ISSO NÃO É FOLGA: é o noturno.
    Um turno 18:00→06:00 tem `shift_date` de ONTEM quando a saída chega, às 06:00 de hoje.
    Com `shift_date = hoje` o aviso de saída do noturno nunca sairia — e o noturno é metade da
    operação. O filtro de `delta_min` é que escolhe o turno certo: o marco de ontem dá delta de
    centenas de minutos e não casa com nenhuma etapa.

    ⚠️ Para a ENTRADA a janela de pareamento é de 3h antes a 12h depois, e conta QUALQUER
    batida. É deliberado: é a MESMA régua de `supervisao.situacao_do_turno`. Em 26/09 a ÉLEN
    bateu 17:57 para um turno de 19:00 e recebeu "você ainda não bateu" — porque este leitor
    usava 1 hora e o outro 3. O defeito não era o número: era existirem dois números para o
    mesmo fato.
    """
    m = MARCOS[marco]
    ref = m["ref"]
    return f"""
SELECT sh.id::text AS shift_id, e.id::text AS employee_id, e.nome,
       coalesce(nullif(e.celular,\'\'), nullif(e.telefone,\'\')) AS telefone,
       p.name AS posto,
       to_char({ref}, \'HH24:MI\') AS hora,
       (EXTRACT(EPOCH FROM (
          (now() AT TIME ZONE \'America/Manaus\') - ({ref})
       ))/60)::int AS delta_min
FROM shifts sh
JOIN posts p ON p.id = sh.post_id
JOIN employees e ON e.id = sh.employee_id
WHERE sh.shift_date BETWEEN ((now() AT TIME ZONE \'America/Manaus\')::date - 1)
                        AND ((now() AT TIME ZONE \'America/Manaus\')::date)
{_FILTROS_COMUNS}
  -- sem horário previsto não há o que avisar (a volta do almoço só existe depois da saída)
  AND ({ref}) IS NOT NULL
  {m["ja_bateu"]}
  {m.get("extra", "")}
  -- dedup: nunca repete a mesma etapa do mesmo turno
  AND NOT EXISTS (
    SELECT 1 FROM ponto_lembrete_log l
    WHERE l.shift_id = sh.id AND l.etapa = :etapa
  )
"""


#: Uma consulta por marco, montada na importação. Os oráculos varrem este dicionário — checar
#: só uma das três deixaria as outras duas sem régua.
SQLS: dict[str, str] = {marco: sql_do_marco(marco) for marco in MARCOS}


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
    """Uma rodada (1 minuto). No máximo 1 mensagem por turno, por marco, por etapa."""
    res = {
        "enviados": 0,
        "pulados_sem_telefone": 0,
        "pulados_telefone_invalido": 0,
        "pulados_optout": 0,
        "teto_rodada": 0,
        "falhas_envio": 0,
        "por_marco": {},
        "dry_run": not PONTO_LEMBRETE_ENABLED,
    }

    for marco, spec in MARCOS.items():
        for delta, modelo in spec["textos"].items():
            etapa = etapa_log(marco, delta)
            linhas = db.execute(text(SQLS[marco]), {"etapa": etapa}).mappings().all()
            for r in linhas:
                # ⚠️ O SQL dedupe por etapa, mas o MINUTO é conferido aqui: um beat atrasado não
                # pode disparar o aviso "começa em 5 minutos" vinte minutos depois.
                #
                # Aceito o minuto exato **ou o seguinte** porque o beat perder um tique é real
                # (celery reinicia, a fila engasga) e uma janela de 1 minuto transforma isso em
                # aviso que nunca sai. O dedup por (shift_id, etapa) garante que aceitar dois
                # minutos não vira duas mensagens.
                if int(r["delta_min"]) not in (delta, delta + 1):
                    continue

                bruto = (r["telefone"] or "").strip()
                if not bruto:
                    res["pulados_sem_telefone"] += 1
                    logger.warning("[Lembrete Ponto] %s sem telefone — turno %s",
                                   r["nome"], r["shift_id"])
                    continue

                tel = normalizar_telefone(bruto)
                if not tel:
                    res["pulados_telefone_invalido"] += 1
                    logger.warning(
                        "[Lembrete Ponto] %s com telefone INVÁLIDO no cadastro (%r) — não "
                        "enviado. Corrigir no cadastro; não dá para adivinhar o número.",
                        r["nome"], bruto,
                    )
                    continue

                if _optout(db, tel):
                    res["pulados_optout"] += 1
                    continue

                if res["enviados"] >= TETO_POR_RODADA:
                    res["teto_rodada"] += 1
                    logger.warning("[Lembrete Ponto] teto da rodada atingido — %s ficou de fora",
                                   r["nome"])
                    continue

                msg = modelo.format(posto=r["posto"], hora=r["hora"], tol=TOLERANCIA_MIN)
                if res["dry_run"]:
                    logger.info("[Lembrete Ponto][DRY] %s/%+d -> %s (%s): %s",
                                marco, delta, r["nome"], tel, msg)
                    continue

                ok = await _enviar(tel, msg)
                db.execute(
                    text(
                        "INSERT INTO ponto_lembrete_log (shift_id, etapa, employee_id, "
                        "telefone, ok) VALUES (:s, :e, :emp, :tel, :ok) ON CONFLICT DO NOTHING"
                    ),
                    {"s": r["shift_id"], "e": etapa, "emp": r["employee_id"],
                     "tel": tel, "ok": ok},
                )
                db.commit()
                if ok:
                    res["enviados"] += 1
                    res["por_marco"][marco] = res["por_marco"].get(marco, 0) + 1
                else:
                    res["falhas_envio"] += 1

    return res
