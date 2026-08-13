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
