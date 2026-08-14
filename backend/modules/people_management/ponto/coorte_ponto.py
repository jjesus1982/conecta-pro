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

SQL_PADRAO_BATIDAS = (
    "WITH dias AS ("
    "  SELECT p.employee_id, p.punch_timestamp::date AS dia, count(*) AS n "
    "  FROM gp_clock_punches p "
    "  WHERE p.punch_timestamp::date >= :desde AND " + CONECTA + " "
    "  GROUP BY 1,2), "
    "moda AS ("
    "  SELECT employee_id, n AS observado, count(*) AS vezes, "
    "         row_number() OVER (PARTITION BY employee_id "
    "                            ORDER BY count(*) DESC, n DESC) AS rk "
    "  FROM dias GROUP BY 1,2) "
    "SELECT e.id::text AS id, e.nome AS nome, m.observado AS observado, m.vezes AS vezes, "
    "       (SELECT count(*) FROM dias d WHERE d.employee_id = e.id) AS dias_medidos, "
    "       CASE WHEN lower(coalesce(e.escala_padrao,'')) LIKE '%44%' "
    "                 OR coalesce(po.tem_intervalo_almoco,false) THEN 4 ELSE 2 END AS esperado "
    "FROM employees e "
    "JOIN moda m ON m.employee_id = e.id AND m.rk = 1 "
    "LEFT JOIN posts po ON po.id = e.posto_atual_id "
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
