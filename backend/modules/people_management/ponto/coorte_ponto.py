"""Quem entra na coorte do PONTO — regra única, usada pelo painel e pelo lembrete.

Existia duplicada: o painel tinha o filtro dele e o lembrete tinha o dele. Toda vez
que a regra muda em um só, os dois passam a contar coisas diferentes e ninguém percebe.

Ausência é calculada por DATA, nunca por marcação manual: quem volta de férias volta
para a coorte sozinho, sem alguém lembrar de destravar. Vale igual para férias que
ainda serão lançadas — no dia em que o RH lançar, a pessoa sai daqui no minuto seguinte.
"""

from __future__ import annotations

# Alias `e` = tabela employees. O painel troca "e." por "e2." num dos SQLs dele, e
# a única ocorrência aqui é `e.id` — que é justamente o que deve ser trocado.
SQL_NAO_AUSENTE_HOJE = """
  -- férias aprovadas cobrindo hoje. Sempre o "hoje" de Manaus: a sessão do Postgres
  -- roda em UTC e o dia dela vira às 20h daqui, o que jogaria a data um dia à frente.
  AND NOT EXISTS (
    SELECT 1 FROM hr_vacation_requests v
    WHERE v.employee_id = e.id
      AND upper(coalesce(v.status,'')) = 'APPROVED'
      AND (now() AT TIME ZONE 'America/Manaus')::date BETWEEN v.start_date AND v.end_date
  )
  -- afastamento em curso: sem data de retorno registrada = ainda afastado
  AND NOT EXISTS (
    SELECT 1 FROM sst_afastamentos a
    WHERE a.employee_id = e.id
      AND lower(coalesce(a.status,'')) IN ('em_andamento','ativo')
      AND a.data_retorno IS NULL
  )
  -- Desligamento: só sai quem está na RETA FINAL. Aviso prévio trabalhado é gente
  -- trabalhando normalmente — quem tem semanas pela frente continua na coorte e adere
  -- ao ponto novo como todo mundo (caso do Adailson, último dia 04/09).
  -- Na última semana não vale mais onboardar (caso do Keyson, sexta é o último dia):
  -- ele termina batendo pelo Sólides. Sem data registrada, NÃO exclui — some dado
  -- não pode tirar ninguém da conta em silêncio.
  AND NOT EXISTS (
    SELECT 1 FROM termination_processes t
    WHERE t.employee_id = e.id
      AND lower(coalesce(t.status,'')) NOT IN ('cancelled','cancelado')
      AND t.last_working_day IS NOT NULL
      AND t.last_working_day <= (now() AT TIME ZONE 'America/Manaus')::date + DIAS_RETA_FINAL
  )
"""

# Quantos dias antes do último dia a pessoa deixa de ser cobrada pela adesão ao ponto
# novo. 7 = a última semana. É decisão de operação, não técnica: subir ou descer aqui
# muda só quem aparece como pendente no painel.
DIAS_RETA_FINAL = 7
SQL_NAO_AUSENTE_HOJE = SQL_NAO_AUSENTE_HOJE.replace("DIAS_RETA_FINAL", f"INTERVAL '{DIAS_RETA_FINAL} days'")


# ─────────────────────── padrão aprendido de batidas ───────────────────────
#
# Quantas batidas cada pessoa FAZ, medido do fato — não quantas o cadastro do posto diz
# que ela deveria fazer. Mora aqui, junto da coorte, porque três superfícies precisam da
# MESMA resposta: o painel público (`/painel-ponto`), o monitor do DP
# (`/human-resources/ativacao-ponto/monitor`) e quem for auditar depois. Três cópias da
# mesma regra viram três verdades — foi assim que a tela de férias passou meses mostrando
# 15 onde havia 19.
#
# Por que existe: em 13/08/2026 os NOVE postos estavam com `tem_intervalo_almoco = false`,
# o app fechava o dia na 2ª batida e 36 pessoas de 12x36 não conseguiam registrar a volta
# do almoço. O número esperado estava chumbado no cadastro e ninguém o confrontava com a
# realidade. Isto é esse confronto, rodando sozinho.

#: ⚠️ A JANELA COMEÇA AQUI, e a data não é detalhe. Todo o histórico anterior foi produzido
#: COM a trava ligada: as pessoas bateram 2 porque o app impedia a 3ª, não porque a jornada
#: delas tem 2. Aprender daquele período seria aprender o defeito e devolvê-lo como regra.
#: Mover esta data para trás contamina o aprendizado.
APRENDIZADO_DESDE = "2026-08-14"

#: Dias com batida necessários para a moda dizer alguma coisa. Com 1 ou 2 dias, um
#: esquecimento vira "mudança de jornada".
DIAS_PARA_CONCLUIR = 3

#: Só device do ponto próprio — `tangerino` é o sistema antigo e `web` é lançamento do DP.
CONECTA = "coalesce(device_type,'') NOT IN ('tangerino','web')"

#: Corte entre um turno e o seguinte. Menos que isto é intervalo dentro do mesmo turno;
#: mais, é turno novo. 14h cobre o 12x36 (12h de jornada) sem colar dois turnos seguidos.
HORAS_ENTRE_TURNOS = 14

SQL_PADRAO_BATIDAS = (
    # ⚠️ AGRUPA POR TURNO, NÃO POR DIA. A primeira versão contava
    # `punch_timestamp::date` e quebrava para o 12x36 NOTURNO, que é metade da equipe:
    # EDWARD entra 17:50 de um dia e sai 05:50 do outro, então cada dia-calendário tem UMA
    # batida. O painel diria "observado=1, esperado=2, DIVERGE" para quem está batendo
    # certo — o alerta nasceria mentindo. A legenda da planilha do Jordan já avisava:
    # "média não vale para turno que vira a meia-noite".
    "WITH b AS ("
    "  SELECT p.employee_id, p.punch_timestamp, "
    "         CASE WHEN lag(p.punch_timestamp) OVER ("
    "                     PARTITION BY p.employee_id ORDER BY p.punch_timestamp) "
    "                   > p.punch_timestamp - make_interval(hours => :horas_turno) "
    "              THEN 0 ELSE 1 END AS novo_turno "
    "  FROM gp_clock_punches p "
    "  WHERE p.punch_timestamp::date >= :desde AND " + CONECTA + "), "
    "g AS ("
    "  SELECT employee_id, punch_timestamp, "
    "         sum(novo_turno) OVER (PARTITION BY employee_id ORDER BY punch_timestamp) AS turno "
    "  FROM b), "
    "dias AS (SELECT employee_id, turno AS dia, count(*) AS n FROM g GROUP BY 1,2), "
    "moda AS ("
    "  SELECT employee_id, n AS observado, count(*) AS vezes, "
    "         row_number() OVER (PARTITION BY employee_id "
    "                            ORDER BY count(*) DESC, n DESC) AS rk "
    "  FROM dias GROUP BY 1,2) "
    "SELECT e.id::text AS id, e.nome AS nome, m.observado AS observado, m.vezes AS vezes, "
    "       (SELECT count(*) FROM dias d WHERE d.employee_id = e.id) AS dias_medidos, "
    # MESMA regra do app (`_proxima_batida_info`): quem recebe o adicional de intrajornada
    # não faz a pausa e bate 2; quem não recebe almoça uma hora e bate 4. Se o painel usar
    # um critério e o app outro, o alerta acusa divergência que não existe.
    "       CASE WHEN coalesce(e.recebe_intrajornada,false) THEN 2 ELSE 4 END AS esperado "
    "FROM employees e "
    "JOIN moda m ON m.employee_id = e.id AND m.rk = 1 "
    "WHERE {coorte} ORDER BY e.nome"
)


def montar_aprendizado(linhas) -> dict:
    """Transforma as linhas de `SQL_PADRAO_BATIDAS` no bloco que as telas mostram.

    `diverge` só é afirmado com maturidade (>= DIAS_PARA_CONCLUIR dias). Divergir não é
    erro de ninguém: é pergunta — ou o posto está cadastrado errado, ou a jornada mudou.
    """
    pessoas = []
    for r in linhas:
        maduro = int(r["dias_medidos"]) >= DIAS_PARA_CONCLUIR
        diverge = maduro and int(r["observado"]) != int(r["esperado"])
        pessoas.append({
            "nome": r["nome"],
            "esperado": int(r["esperado"]),
            "observado": int(r["observado"]),
            "dias_medidos": int(r["dias_medidos"]),
            "confirmacoes": int(r["vezes"]),
            "maduro": maduro,
            "diverge": diverge,
            "sugestao": (
                f"bate {r['observado']}× e o cadastro prevê {r['esperado']}× — "
                f"confira o intervalo do posto ou a escala"
            ) if diverge else None,
        })
    divergentes = [p for p in pessoas if p["diverge"]]
    if divergentes:
        alertas = [f"{p['nome']}: {p['sugestao']}" for p in divergentes]
    elif any(p["maduro"] for p in pessoas):
        alertas = ["nenhuma divergência entre o cadastro e o que as pessoas batem"]
    else:
        alertas = [f"aprendendo desde {APRENDIZADO_DESDE} — "
                   f"ainda sem {DIAS_PARA_CONCLUIR} dias para comparar"]
    return {
        "desde": APRENDIZADO_DESDE,
        "por_que_essa_data": (
            "o histórico anterior foi produzido com a trava da 2ª batida ligada — "
            "aprender dali seria aprender o defeito"
        ),
        "medidos": len(pessoas),
        "divergentes": len(divergentes),
        "pessoas": pessoas,
        "alertas": alertas,
    }


# ─────────────────────── jornada por posto (horário de entrada) ───────────────────────
#
# ATÉ 14/08/2026 O HORÁRIO DE ENTRADA NÃO EXISTIA NO SISTEMA. Vivia numa planilha e na
# cabeça de quem opera. Por isso o painel só sabia dizer "bateu / não bateu", nunca "está
# atrasado" — e quando 42 pessoas apareceram sem bater às 07:24 eu não tinha como separar
# quem estava atrasado de quem ainda nem tinha hora de entrar. Chutei "diurno = 06:00" e
# errei em quatro dos sete que apontei.
#
# POR QUE AQUI E NÃO EM TABELA. `work_schedules` existe e tem os campos certos, mas exige
# **30 colunas NOT NULL sem default** (banco de horas, multiplicadores de HE, geolocalização,
# biometria) — preencher tudo isso com valor que ninguém me deu seria fabricar. Horário de
# posto muda raramente e é decisão de operação, não de runtime: mora no código, revisado por
# quem lê o diff. Se um dia virar cadastro editável, `work_schedules` é o destino natural.
#
# FONTE: Jordan, posto a posto, em 14/08 — e confere com o histórico do SÓLIDES
# (01–10/08, 962 batidas, antes da virada para o Conecta PRO).

#: Minutos de atraso tolerados antes de o painel cobrar. Decisão do Jordan: "ninguém vai
#: bater o ponto às 06:00, vai bater sempre atrasado". Cobrar o minuto exato faria o alerta
#: tocar todo dia para todo mundo. 15 cobre o atraso pequeno e o adiantamento de Villa dos
#: Pássaros, que chega ~10 min ANTES.
TOLERANCIA_ENTRADA_MIN = 15

#: ⚠️ A tolerância vale para OS DOIS LADOS, e o lado de cá tem consequência em dinheiro:
#: "se bater antes, não pode contar como extra" (Jordan, 14/08). Villa dos Pássaros chega
#: ~10 min antes por hábito; contar isso como hora extra criaria adicional que ninguém
#: trabalhou. Quem calcula HE deve descartar o antecipado dentro da tolerância.

_PADRAO_06 = {"diurno": "06:00", "noturno": "18:00", "asg": "08:00"}
_PADRAO_07 = {"diurno": "07:00", "noturno": "19:00", "asg": None}

#: posto → turno → horário de entrada. `asg` vale para serviços gerais, artífice e
#: jardineiro (44h); `diurno`/`noturno` para agente e líder de portaria (12x36).
JORNADA_POR_POSTO = {
    # Ideal Flores: NINGUÉM recebe intrajornada — os 13 batem 4 vezes (os de 44h, 2 no
    # sábado). Diurno 06:00–18:00, noturno 18:00–06:00. Confirmado pelo Jordan em 14/08.
    "Condomínio Ideal Flores da Cidade": _PADRAO_06,
    "Condomínio Villa dos Pássaros": _PADRAO_06,
    "Condomínio Prime Arena": _PADRAO_06,
    "Condomínio Villa Dei Fiori": _PADRAO_06,
    # Laranjeiras: só portaria, sem ASG. Diurno 07:00–19:00, noturno 19:00–07:00,
    # ninguém recebe intrajornada (4 batidas). Confirmado pelo Jordan em 14/08 e batendo
    # com o Sólides (diurno 06:59–07:03, noturno 18:56–19:00, todos com 4 batidas/turno).
    "Residencial Laranjeiras Village": _PADRAO_07,
    "Condomínio Mirante das Flores": {**_PADRAO_07, "asg": "07:00"},
    "Condomínio Michelangelo": {"diurno": None, "noturno": None, "asg": "08:00"},
}

#: Jornada INDIVIDUAL, quando a pessoa não segue o padrão do posto. Ditada pelo Jordan,
#: posto a posto, em 14/08 — e conferida contra o que o Sólides mediu (01–10/08).
#:
#: Formato: nome → {"ent", "sai", "sabado", "domingo"}. `sabado`/`domingo` em `None`
#: significam "não trabalha nesse dia"; ausentes significam "segue a regra do cargo".
#:
#: MIRANTE DAS FLORES é o posto com mais variação, e não é bagunça — é revezamento:
#:   CHAGAS e ALEXANDRE   07:00–19:00   (medido 06:46 e 07:00)
#:   EDIWILSON e GAMA     10:00–22:00   (medido 09:55 e 10:00)
#:   AILTON e EDUARDO     19:00–07:00   (medido 18:59 e 19:00)  — noturno
#:   VANDERLICE e TELMA   07:00–16:00   (medido 07:01 e 07:02)  — ASG
#:   PAULO                09:00–18:00   (medido 09:00)          — ASG
#:
#: ⚠️ PAULO DA SILVA LAMEGO é ADVENTISTA: não trabalha sábado e cumpre o meio período no
#: DOMINGO, 08:00–12:00. Sem isto o painel o cobraria todo sábado e o daria como ausente
#: todo domingo — duas vezes errado, e sobre religião.
JORNADA_INDIVIDUAL = {
    "MAURICIO ALVES CHAGAS": {"ent": "07:00", "sai": "19:00"},
    "ALEXANDRE SOUZA DA SILVA": {"ent": "07:00", "sai": "19:00"},
    "EDIWILSON CORREA MARQUES": {"ent": "10:00", "sai": "22:00"},
    "ANTONIO CARLOS CASTRO GAMA": {"ent": "10:00", "sai": "22:00"},
    "AILTON CÉSAR VASCONCELOS": {"ent": "19:00", "sai": "07:00"},
    "EDUARDO OLIVEIRA DE SOUZA": {"ent": "19:00", "sai": "07:00"},
    "VANDERLICE SANTOS DA SILVA": {"ent": "07:00", "sai": "16:00"},
    "TELMA MARIA LAGES MEIRA": {"ent": "07:00", "sai": "16:00"},
    "PAULO DA SILVA LAMEGO": {"ent": "09:00", "sai": "18:00",
                              "sabado": None, "domingo": ("08:00", "12:00")},
}

#: Sábado do 44h: 08:00–12:00, meio período, 2 batidas.
SABADO_44H_ENTRADA = "08:00"

# ─── revezamento de fim de semana (Michelangelo) ───────────────────────────────
#
# Os 2 artífices do Michelangelo se revezam: um trabalha no SÁBADO, o outro no DOMINGO,
# 08:00–12:00, e na semana seguinte TROCAM. Não é escala fixa — é alternância semanal, e
# nenhuma regra por cargo ou por posto dá conta disso.
#
# O histórico do Sólides mostra o revezamento, mas com ruído (um terceiro artífice que saiu
# da empresa, batidas soltas de 1 marcação, um turno 13:00–17:00). Por isso a âncora é
# declarada, não inferida: digo QUEM trabalha no sábado de UMA semana conhecida, e o resto
# se alterna sozinho a partir dali.
REVEZAMENTO_FDS = {
    "Condomínio Michelangelo": {
        # semana ISO de referência e quem estava no SÁBADO dela; o outro fica no domingo
        "semana_ref": 33,          # semana de 10–16/08/2026
        "sabado": "ANTONIO CARLOS VIEIRA",
        "domingo": "KALEL SILVA DE JESUS",
        "entrada": "08:00",
    },
}


#: Quem participa de algum revezamento de fim de semana. Derivado do dicionário acima para
#: não virar uma segunda lista que alguém esquece de atualizar.
_NOMES_REVEZAM = {c[d] for c in REVEZAMENTO_FDS.values() for d in ("sabado", "domingo")}


def _reveza_fds(posto: str, nome: str, dow: int, iso_week: int) -> str | None | bool:
    """Quem trabalha neste fim de semana no posto que se reveza.

    Devolve o horário se a pessoa trabalha, None se não trabalha, e False quando o posto
    não tem revezamento (para o chamador seguir a regra normal — `None` já significa
    "não trabalha" e os dois não podem se confundir).
    """
    cfg = REVEZAMENTO_FDS.get(_posto_canonico(posto) or "")
    if not cfg or dow not in (0, 6):
        return False
    # semanas de diferença em relação à referência: par mantém, ímpar troca
    trocou = (iso_week - cfg["semana_ref"]) % 2 == 1
    no_sabado = cfg["domingo"] if trocou else cfg["sabado"]
    no_domingo = cfg["sabado"] if trocou else cfg["domingo"]
    escalado = no_sabado if dow == 6 else no_domingo
    return cfg["entrada"] if (nome or "").upper().strip() == escalado else None

# ─── folga do 12x36: quem trabalhou ontem NÃO está atrasado hoje ───────────────
#
# 🔴 DEFEITO QUE ISTO CORRIGE, medido em 14/08/2026 às 09:26 no painel de produção: dos 15
# "atrasados", ONZE estavam de FOLGA. O alerta que o Jordan pediu para monitorar a batida
# estava cobrando gente que não tinha que estar lá — e um alerta que grita todo dia com quem
# está de folga é um alerta que ninguém lê na semana seguinte.
#
# O sistema não tem a escala do 12x36: sabe a HORA de cada um, não o DIA. A tabela `shifts`
# existe e parecia a resposta, mas medi antes de usar e ela não serve para isto: em 7 dias
# houve **77 dias-pessoa de gente que bateu ponto sem ter turno lançado** (30% do total).
# Tratar "sem turno" como folga silenciaria atraso de verdade em quase um terço dos casos.
#
# O que serve é a própria batida, medida DIREITO. A primeira medição que fiz dizia que a
# alternância não existia — 190 casos de "bateu ontem e hoje" contra 130 de "bateu ontem e
# folgou hoje" — e estava errada pelo mesmo motivo de sempre: o NOTURNO bate em dois dias de
# calendário (entra 18:00 de um dia, sai 06:00 do outro). Medindo por INÍCIO DE TURNO, com o
# mesmo corte de 14h do aprendizado, a alternância aparece limpa:
#
#     dias entre inícios de turno (12x36, 21 dias):  2 dias → 246   4 → 16   1 → 7   3 → 4
#
# 246 de 278 (88,5%) em exatamente 2 dias. A regra: **turno começou ontem → folga hoje**.
#
# ponytail: heurística, não escala. Erra nos 7 casos de 1 dia (troca de plantão) e deixa de
# cobrar quem trocou de turno com o colega. Trocar por `shifts` no dia em que o operacional
# lançar turno para todo mundo — a consulta de aceite está no comentário acima: se
# `bateu_sem_escala` zerar, a escala virou fonte melhor que esta conta.
#
# Usa TODOS os devices de propósito, inclusive `tangerino`: até 11/08 as pessoas batiam no
# Sólides, e ignorar aquilo faria todo mundo parecer "sem turno recente" na primeira semana.
SQL_ULTIMO_TURNO = """
  LEFT JOIN (
    SELECT employee_id, max(d) AS ultimo_turno FROM (
      SELECT employee_id, punch_timestamp::date AS d,
             punch_timestamp - lag(punch_timestamp)
               OVER (PARTITION BY employee_id ORDER BY punch_timestamp) AS gap
      FROM gp_clock_punches
      WHERE punch_timestamp >= (now() AT TIME ZONE 'America/Manaus')::date - 30
        AND punch_timestamp < (now() AT TIME ZONE 'America/Manaus')::date
    ) x WHERE gap IS NULL OR gap > interval 'HORAS_ENTRE_TURNOS hours'
    GROUP BY employee_id
  ) ult ON ult.employee_id = e.id
"""
SQL_ULTIMO_TURNO = SQL_ULTIMO_TURNO.replace("HORAS_ENTRE_TURNOS", str(HORAS_ENTRE_TURNOS))


def folga_hoje(escala: str, dias_desde_turno: int | None) -> bool:
    """O 12x36 que começou turno ONTEM está de folga hoje — não é atraso.

    Só vale para 12x36: o 44h trabalha de segunda a sábado e um dia não prevê o outro.
    Sem batida recente (`None`) NÃO é folga — some dado não pode tirar ninguém da conta.
    """
    return "12x36" in (escala or "").lower() and dias_desde_turno == 1


# ─── quadro em transição ───────────────────────────────────────────────────────
#
# O quadro CERTO de um posto não está no banco: o banco tem quem já foi cadastrado. Quando
# alguém sai antes do substituto entrar, o posto fica com menos gente do que deveria e nada
# no sistema diz que aquilo é um buraco — parece só um posto pequeno.
#
# Registrado aqui porque é aqui que se olha antes de mexer em ponto de um posto. NADA CONSOME
# ISTO AINDA: é registro, não regra. Quem for ligar um alerta de quadro incompleto no painel
# tem o dado pronto; quem só quiser saber por que o Prime está com 2 AGP lê e entende.
#
# PRIME ARENA — declarado pelo Jordan em 14/08/2026. O correto são 4 AGP; hoje o sistema
# conhece 3, e dos 3 um sai hoje:
#
#   SAI   KEYSON DA SILVA PINTO    aviso prévio encerrado — `termination_processes` diz
#                                  last_working_day 14/08, voluntary. A coorte já o exclui
#                                  sozinha (reta final de 7 dias), então ele não vira
#                                  "ausente" no painel. Nada a fazer.
#   SAI   RILEM FERREIRA DE SOUZA  realocado para o Ideal Flores — o cadastro JÁ reflete
#                                  (posto_atual_nome = IDEAL FLORES). Nada a fazer.
#   ENTRA ALAN VIEIRA              no lugar do Keyson
#   ENTRA DALTON PACHECO           no lugar do Rilem
#
# Os dois que entram ainda NÃO EXISTEM no `employees`: serão contratados até 20/08 e começam
# a bater ponto de 20/08 em diante. Até lá o Prime opera com 2 AGP, e isso é cobertura, não
# defeito de sistema.
#
# ⚠️ ARYELTON BRAGA FIGUEIRA NÃO ENTRA NA CONTA DOS 4. Contrato de trabalho SUSPENSO, com
# processo trabalhista em curso (Jordan, 14/08). O `sst_afastamentos` tem a suspensão aberta
# desde 02/02/2026 sem data de retorno, e é por isso que a coorte o exclui — o registro está
# CERTO. Mas veja o aviso abaixo: existem batidas em nome dele mesmo assim.
QUADRO_EM_TRANSICAO = {
    "Condomínio Prime Arena": {
        "cargo": "AGENTE DE PORTARIA",
        "previsto": 4,
        "saem": ["KEYSON DA SILVA PINTO", "RILEM FERREIRA DE SOUZA"],
        "entram": ["ALAN VIEIRA", "DALTON PACHECO"],
        "contratar_ate": "2026-08-20",
        "batem_ponto_desde": "2026-08-20",
        # Prime é _PADRAO_06 e TODO AGP daqui recebe intrajornada → 2 batidas.
        # Os ASG (Graciene e Malaquias) não recebem → 4. Nada disso muda com a troca.
        "recebe_intrajornada": True,
    },
}

# ⚠️ BATIDA DE QUEM NÃO ESTÁ TRABALHANDO — achado de 14/08/2026, ainda EM ABERTO.
#
# O import do Sólides/Tangerino grava batidas para gente que não trabalhou. Medido:
#
#   CINTIA BEZERRA    afastada (acidente de trajeto) desde 21/05   80 batidas, a última HOJE
#   ARYELTON BRAGA    contrato suspenso desde 02/02                68 batidas, a última 13/08
#   FRANCISCO RAMON   de férias                                    28 batidas em agosto
#
# O que denuncia é o RELÓGIO: essas batidas caem no minuto e no segundo exatos (18:00:00,
# 06:00:00), todo dia, sem exceção. Gente de verdade bate torto — 06:46, 07:01, 09:55, 18:59.
# São 779 de 1253 batidas tangerino em agosto no minuto cheio (62%), e as 7 pessoas com 100%
# de batidas redondas incluem exatamente os três acima. Isso não é ponto: é a ESCALA sendo
# gravada como se fosse marcação.
#
# Por que ainda não quebrou nada nosso: `CONECTA` (linha ~78) já exclui `tangerino` e `web`
# do aprendizado, então o padrão de batidas aprende só do ponto próprio. E a parametrização
# de horários veio da palavra do Jordan, posto a posto — o Sólides serviu de conferência, e
# os números que usei eram justamente os tortos.
#
# Por que importa mesmo assim, e não é achado de estética: o Aryelton tem PROCESSO
# TRABALHISTA em curso. Uma tabela de ponto da própria empresa dizendo que ele bateu ponto
# durante a suspensão é prova contra a empresa, produzida por um importador. Isso é do dono
# do import do Sólides resolver — está fora do escopo do ponto — mas fica escrito aqui
# porque foi aqui que apareceu.

_CARGOS_44H = ("SERVIÇOS GERAIS", "SERVICOS GERAIS", "ARTÍFICE", "ARTIFICE", "JARDINEIRO")

#: ⚠️ O MESMO POSTO TEM DOIS NOMES no banco, e isto custou uma rodada: `posts.name` diz
#: "Condomínio Ideal Flores da Cidade" e `employees.posto_atual_nome` diz "IDEAL FLORES".
#: O painel passa o segundo, o dicionário acima usa o primeiro, e 29 pessoas saíram como
#: "sem horário". A busca casa por PALAVRA-CHAVE, sem acento e sem caixa, para aceitar as
#: duas grafias — e qualquer terceira que apareça.
_APELIDOS = {
    "IDEAL": "Condomínio Ideal Flores da Cidade",
    "PASSARO": "Condomínio Villa dos Pássaros",
    "PRIME": "Condomínio Prime Arena",
    "DEI FIOR": "Condomínio Villa Dei Fiori",
    "LARANJEIRA": "Residencial Laranjeiras Village",
    "MIRANTE": "Condomínio Mirante das Flores",
    "MICHEL": "Condomínio Michelangelo",
}


def _posto_canonico(posto: str) -> str | None:
    """Nome do posto como o dicionário de jornadas conhece, aceitando apelidos."""
    import unicodedata

    if not posto:
        return None
    chave = unicodedata.normalize("NFKD", posto).encode("ascii", "ignore").decode().upper()
    for pedaco, oficial in _APELIDOS.items():
        if pedaco in chave:
            return oficial
    return None


def horario_entrada(
    nome: str, posto: str, cargo: str, turno: str, dow: int = 1, iso_week: int = 0
) -> str | None:
    """Hora de entrada da pessoa NAQUELE dia da semana, ou None quando ela não trabalha.

    `dow` segue o Postgres: 0 = domingo … 6 = sábado.

    None é resposta legítima e é a mais importante: significa "não trabalha hoje" ou "não
    sei", e quem chama NÃO PODE concluir atraso a partir disso. Foi assumir horário onde eu
    não tinha um que me fez apontar quatro pessoas erradas em 14/08.
    """
    chave = (nome or "").upper().strip()
    ind = JORNADA_INDIVIDUAL.get(chave)
    é_44h = any(k in (cargo or "").upper() for k in _CARGOS_44H)

    # posto que se reveza no fim de semana responde antes de qualquer regra geral
    rev = _reveza_fds(posto, nome, dow, iso_week)
    if rev is not False:
        return rev

    if ind is not None:
        if dow == 6:                       # sábado
            if "sabado" in ind:
                sab = ind["sabado"]
                return sab[0] if sab else None
            return SABADO_44H_ENTRADA if é_44h else ind["ent"]
        if dow == 0:                       # domingo
            dom = ind.get("domingo")
            return dom[0] if dom else None
        return ind["ent"]

    if dow == 0:                           # domingo: só quem tem escala própria trabalha
        return None
    grupo = "asg" if é_44h else ("noturno" if (turno or "").lower().startswith("n") else "diurno")
    do_posto = (JORNADA_POR_POSTO.get(_posto_canonico(posto)) or {}).get(grupo)
    if do_posto is None:
        # O posto não tem esse grupo (Laranjeiras não tem ASG) ou não está parametrizado.
        # Devolver o sábado padrão aqui inventaria horário para quem o posto não conhece —
        # e seg-sex já responderia None. Incoerência assim vira alerta falso no sábado.
        return None
    if é_44h and dow == 6:
        return SABADO_44H_ENTRADA
    return do_posto


def dia_de_meio_periodo(nome: str, cargo: str, dow: int) -> bool:
    """Hoje é o meio período dessa pessoa? (2 batidas, sem pausa)

    Quem é 44h — ASG, artífice, jardineiro — trabalha meio período um dia por semana:
    08:00–12:00, duas batidas. A regra vale em TODOS os condomínios.

    O dia é o SÁBADO, exceto para quem tem escala própria em `JORNADA_INDIVIDUAL`. PAULO DA
    SILVA LAMEGO é adventista: folga sábado e cumpre o meio período no DOMINGO. Uma condição
    `dow == 6` solta no controller o deixaria com 4 batidas no domingo e o app cobraria duas
    que não existem.
    """
    if not any(k in (cargo or "").upper() for k in _CARGOS_44H):
        return False
    ind = JORNADA_INDIVIDUAL.get((nome or "").upper().strip())
    if ind:
        if ind.get("domingo") and dow == 0:
            return True
        if "sabado" in ind:                    # sábado declarado (ou None = não trabalha)
            return dow == 6 and ind["sabado"] is not None
    # Quem se reveza no fim de semana faz meio período no dia que lhe cabe — inclusive quando
    # esse dia é DOMINGO. Sem isto o KALEL sairia com 4 batidas no domingo dele: o `dow == 6`
    # abaixo só enxerga sábado, e o revezamento do Michelangelo é justamente o caso em que o
    # meio período cai fora dele. Basta o NOME: `horario_entrada` já devolve None no dia em
    # que a pessoa folga, então ninguém pergunta as batidas dela naquele dia.
    if (nome or "").upper().strip() in _NOMES_REVEZAM and dow in (0, 6):
        return True
    return dow == 6
