"""DGX X5 — as decisões que só o dono pode tomar, com o número ao vivo (24/09/2026).

**Por que existe.** Em dois dias, 20 frentes produziram 51 decisões que só o Jordan pode tomar.
Elas estavam em `auditoria/RELATORIO_NOITE_2026-09-24.md` (§4, §12, §15, §19) e no §7 de cada
`auditoria/frentes/DGX_*.md` — markdown, com o número de quando foi medido. **Decisão em arquivo
morre**: quando ele abre o arquivo, o número já é de ontem, e não há onde registrar a resposta.

Aqui a decisão vira linha de banco com `numero_sql`: a consulta que mede a MESMA coisa HOJE. O
painel roda as consultas no render e mostra o valor com a hora da medição. Decisão sem número
(escolha pura — «veículo é patrimônio?») entra com `numero_sql` nulo e aparece como tal: **não
inventamos número para caber na coluna.**

**Três paredes para o `numero_sql` não escrever nada:**
1. varredura por palavra-chave (INSERT/UPDATE/DELETE/CREATE/DROP/ALTER/TRUNCATE/GRANT/REVOKE/
   COPY/MERGE) — recusa antes de chegar ao banco;
2. cada medição roda dentro de um SAVEPOINT que é SEMPRE desfeito, mesmo quando dá certo;
3. `statement_timeout` curto — consulta lenta não segura o painel do dono.

Um SQL que falha NÃO derruba o painel: a linha mostra «não medido» com o erro curto. É a
honestidade da casa — tela que mente é pior que tela vazia.

Nada aqui muda folha, preço, escala ou pagamento. É registro de decisão: texto, autor e data.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import text

logger = logging.getLogger(__name__)

AREAS = ("folha", "ponto", "operacional", "financeiro", "cadastro", "fiscal", "qa")
IMPACTOS = ("dinheiro", "risco", "cadastro", "operacao")
STATUS = ("aberta", "decidida", "descartada")

#: Palavras que uma consulta de MEDIÇÃO nunca precisa. `\b` de propósito: `created_at` e
#: `updated_at` continuam passando (a palavra segue com letra, não fecha a fronteira).
_PROIBIDO = re.compile(
    r"\b(insert|update|delete|create|drop|alter|truncate|grant|revoke|copy|merge|vacuum)\b",
    re.IGNORECASE,
)

TIMEOUT_MS = 4000


class DecisaoErro(Exception):  # noqa: N818 — «Erro» é o sufixo da casa (ver HEClassificacaoErro)
    def __init__(self, msg: str, status: int = 400) -> None:
        super().__init__(msg)
        self.status = status


# ───────────────────────────── DDL (idempotente, roda no 1º acesso) ─────────────────────────────
_DDL = (
    """
    CREATE TABLE IF NOT EXISTS dono_decisoes (
        id             serial PRIMARY KEY,
        codigo         varchar(20)  NOT NULL UNIQUE,
        titulo         varchar(200) NOT NULL,
        pergunta       text         NOT NULL,
        area           varchar(20)  NOT NULL,
        origem         varchar(120) NOT NULL,
        impacto        varchar(20)  NOT NULL,
        numero_sql     text,
        unidade        varchar(20),
        tela_para_agir varchar(200),
        status         varchar(20)  NOT NULL DEFAULT 'aberta',
        decisao        text,
        decidida_por   varchar(120),
        decidida_em    timestamptz,
        criada_em      timestamptz  NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_dono_decisoes_status ON dono_decisoes (status)",
)


# ───────────────────────────── as consultas que medem HOJE ─────────────────────────────
# Cada uma devolve UM escalar. Recontadas contra o sandbox em 24/09/2026 — o valor medido
# está no comentário ao lado e no relatório `auditoria/frentes/DGX_X5_painel_decisoes.md`.

SQL_FALTAS_FORA_INSS = """
SELECT ROUND(COALESCE(SUM(valor), 0)::numeric, 2) FROM folha_verba_espelho
 WHERE codigo IN ('1051', '1053')
   AND (ano, mes) = (SELECT ano, mes FROM folha_verba_espelho ORDER BY ano DESC, mes DESC LIMIT 1)
"""

SQL_ADICIONAL_FORA_CCT = """
SELECT count(*) FROM employees e LEFT JOIN cct_cargos c ON c.id = e.cct_cargo_id
 WHERE lower(coalesce(e.status, '')) = 'ativo' AND coalesce(e.is_homologacao, false) = false
   AND ( (coalesce(e.insalubridade_percentual, 0) > 0 AND coalesce(c.adicional_insalubridade_percentual, 0) = 0)
      OR (coalesce(e.periculosidade_percentual, 0) > 0 AND coalesce(c.adicional_periculosidade_percentual, 0) = 0) )
"""

SQL_SEM_CARGO_CCT = """
SELECT count(*) FROM employees
 WHERE lower(coalesce(status, '')) = 'ativo' AND coalesce(is_homologacao, false) = false
   AND cct_cargo_id IS NULL
"""

# Mesma régua do caçador `backend/scripts/qa/checar_escala_paridade.py` (LIMIAR 0,70 ·
# MIN_TURNOS 5 · MIN_BATIDAS 5 · 3 meses), recontada aqui por SQL própria.
SQL_ESCALA_PARIDADE = """
WITH turno AS (
  SELECT CAST(s.employee_id AS TEXT) AS eid, date_trunc('month', s.shift_date)::date AS comp,
         (s.shift_date + s.planned_start_time) - interval '1 hour' AS j0,
         (s.shift_date + CASE WHEN s.planned_end_time < s.planned_start_time
                              THEN interval '1 day' ELSE interval '0' END
          + s.planned_end_time) + interval '1 hour' AS j1
    FROM shifts s JOIN employees e ON CAST(e.id AS TEXT) = CAST(s.employee_id AS TEXT)
   WHERE s.shift_date >= date_trunc('month', CURRENT_DATE - interval '2 months')
     AND s.shift_date <  date_trunc('month', CURRENT_DATE + interval '1 month')
     AND lower(coalesce(s.status, '')) <> 'cancelled' AND NOT coalesce(s.is_off_day, false)
     AND s.planned_start_time > s.planned_end_time
     AND lower(coalesce(e.status, '')) NOT IN ('demitido', 'inativo')
     AND coalesce(e.is_homologacao, false) = false
), batida AS (
  SELECT CAST(p.employee_id AS TEXT) AS eid, date_trunc('month', p.punch_timestamp)::date AS comp,
         p.punch_timestamp AS ts
    FROM gp_clock_punches p
   WHERE p.punch_timestamp >= date_trunc('month', CURRENT_DATE - interval '2 months')
     AND p.punch_timestamp <  date_trunc('month', CURRENT_DATE + interval '1 month')
), turno_m AS (
  SELECT eid, comp, EXISTS (SELECT 1 FROM batida b WHERE b.eid = t.eid AND b.ts BETWEEN t.j0 AND t.j1) AS tem_batida
    FROM turno t
), batida_m AS (
  SELECT b.eid, b.comp,
         EXISTS (SELECT 1 FROM turno t WHERE t.eid = b.eid AND b.ts BETWEEN t.j0 AND t.j1) AS tem_turno
    FROM batida b
   WHERE EXISTS (SELECT 1 FROM turno t WHERE t.eid = b.eid AND t.comp = b.comp)
), agg AS (
  SELECT t.eid, t.comp, count(*) AS turnos, count(*) FILTER (WHERE NOT t.tem_batida) AS vazios,
         (SELECT count(*) FROM batida_m m WHERE m.eid = t.eid AND m.comp = t.comp) AS batidas,
         (SELECT count(*) FROM batida_m m WHERE m.eid = t.eid AND m.comp = t.comp AND NOT m.tem_turno) AS fora
    FROM turno_m t GROUP BY t.eid, t.comp
)
SELECT count(*) FROM agg
 WHERE turnos >= 5 AND batidas >= 5
   AND vazios::numeric / turnos  >= 0.70
   AND fora::numeric   / batidas >= 0.70
"""

SQL_HE_SEM_EXPLICACAO = """
SELECT count(*) FROM ponto_he_classificacao
 WHERE motivo = 'falta_de_efetivo' AND classificado_em IS NULL
   AND competencia = (SELECT max(competencia) FROM ponto_he_classificacao)
"""

SQL_POSTO_CONTRATO_FANTASMA = """
SELECT count(*) FROM posts p
 WHERE coalesce(p.is_active, true) AND p.contract_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM contracts c WHERE c.id = p.contract_id)
"""

SQL_POSTO_SEM_SALARIO = """
SELECT count(*) FROM posts
 WHERE coalesce(is_active, true) AND coalesce(salario_base, 0) = 0
"""

# Mesma união da tela CRM «Última visita por cliente» (_dgx_t3_operacional_comercial.py).
SQL_CLIENTE_SEM_VISITA = """
SELECT count(*) FROM clients c
 LEFT JOIN LATERAL (
   SELECT max(v.d) AS d FROM (
     SELECT cliente_id AS cid, data_visita::date AS d
       FROM crm_visit_reports WHERE cliente_id IS NOT NULL AND data_visita IS NOT NULL
     UNION ALL
     SELECT cliente_id,
            coalesce(((checkin_at AT TIME ZONE 'UTC') AT TIME ZONE 'America/Manaus')::date, data_visita)
       FROM visitas
      WHERE cliente_id IS NOT NULL AND coalesce(ativo, true)
        AND (status::text = 'realizada' OR checkin_at IS NOT NULL)
   ) v WHERE v.cid = c.id
 ) x ON true
 WHERE c.status::text = 'active' AND (x.d IS NULL OR x.d < current_date - 30)
"""

SQL_SEM_FOTO = """
SELECT count(*) FROM employees
 WHERE lower(coalesce(status, '')) NOT IN ('demitido', 'inativo')
   AND coalesce(is_homologacao, false) = false AND coalesce(foto_url, '') = ''
"""

SQL_SEM_CNH = """
SELECT count(*) FROM employees
 WHERE lower(coalesce(status, '')) NOT IN ('demitido', 'inativo')
   AND coalesce(is_homologacao, false) = false AND coalesce(cnh_numero, '') = ''
"""

# `employees.dependentes` (JSONB) é o que a FOLHA lê — ver `_dgx_f6_dp.py`.
SQL_DEPENDENTE_SEM_NASCIMENTO = """
SELECT count(*) FROM employees e, jsonb_array_elements(coalesce(e.dependentes, '[]'::jsonb)) d
 WHERE coalesce(d->>'data_nascimento', '') = ''
"""

# Faixa «> 22 meses» do mapa da frente 08: período aquisitivo ABERTO com mais de 22 meses.
SQL_FERIAS_22_MESES = """
SELECT count(DISTINCT p.employee_id) FROM employee_vacation_periods p
  JOIN employees e ON e.id = p.employee_id
 WHERE NOT coalesce(p.is_fully_used, false) AND coalesce(p.days_remaining, 0) > 0
   AND lower(coalesce(e.status, '')) NOT IN ('demitido', 'inativo')
   AND coalesce(e.is_homologacao, false) = false
   AND (date_part('year', age(current_date, p.start_date)) * 12
        + date_part('month', age(current_date, p.start_date))) > 22
"""

SQL_PENSAO_SEM_BENEFICIARIO = """
SELECT count(*) FROM employee_deductions d
 WHERE d.tipo = 'pensao_alimenticia' AND coalesce(d.ativo, true)
   AND NOT EXISTS (SELECT 1 FROM financial_beneficiarios b
                    WHERE b.employee_id = d.employee_id AND b.tipo = 'pensionista'
                      AND coalesce(b.ativo, true))
"""

SQL_NFE_SO_RESUMO = "SELECT count(*) FROM nfe_entradas WHERE coalesce(resumo, false) = true"

SQL_RUBRICA_NUNCA_EMITIDA = """
SELECT count(*) FROM rubricas_folha r
 WHERE coalesce(r.ativo, true)
   AND NOT EXISTS (SELECT 1 FROM folha_verba_espelho v WHERE v.codigo = r.codigo)
"""

SQL_LOGIN_DUPLICADO = """
SELECT count(*) FROM (SELECT employee_id FROM users
                       WHERE employee_id IS NOT NULL GROUP BY 1 HAVING count(*) > 1) x
"""

SQL_DEMISSAO_SEM_DATA = """
SELECT count(*) FROM employees
 WHERE lower(coalesce(status, '')) IN ('demitido', 'inativo')
   AND coalesce(is_homologacao, false) = false AND data_demissao IS NULL
"""

SQL_LEAD_SEM_CONTATO = """
SELECT count(*) FROM proativo_alert_state
 WHERE resolved_at IS NULL AND regra = 'lead_sem_contato'
"""


# ─────────────────────────────────── a semente ───────────────────────────────────
# (codigo, titulo, pergunta, area, origem, impacto, numero_sql, unidade, tela_para_agir)
# A PERGUNTA vem do §7 da frente que achou o problema — não foi inventada aqui.
SEMENTE: tuple[tuple, ...] = (
    # ─── as 14 obrigatórias (todas com número) ───
    (
        "D01",
        "Faltas fora da base do INSS",
        "O motor going-forward não tira as faltas (1051) nem o DSR sobre faltas (1053) da base do "
        "INSS — salário-de-contribuição é a remuneração efetivamente devida, então INSS do "
        "empregado e FGTS saem calculados A MAIOR. Em 09/2026 foram 19 pessoas com 1051 "
        "(R$ 2.575,28) + 12 com 1053 (R$ 2.018,58) = R$ 4.593,86 fora da base (FGTS 8% = "
        "R$ 367,51). Corrigir o motor e virar as flags `incide_inss` de 1051/1053, ou manter "
        "como está? O número abaixo é o R$ das faltas na última competência com espelho.",
        "folha",
        "DGX F1 §7.1",
        "dinheiro",
        SQL_FALTAS_FORA_INSS,
        "R$",
        "/redesign/departamento-pessoal?t=folha-rubricas",
    ),
    (
        "D02",
        "Adicionais pagos fora da CCT",
        "Quem tem laudo? A insalubridade de 10% é paga a pessoas de funções que a CCT não trata "
        "como cargo insalubre (Serviços Gerais 8 de 12, Artífice 2 de 2, Jardineiro 1 de 1) — "
        "precisa de LTCAT/laudo por posto: se houver, marcar o evento como obrigatório na função; "
        "se não houver, é pagamento sem base e parar é decisão de gente. E a ronda de 15% paga a "
        "15 agentes de portaria (CCT cl. 23ª paga a quem faz ronda no perímetro): confirmar posto "
        "a posto quem faz. O número abaixo conta insalubridade/periculosidade sem respaldo na "
        "função da CCT (ronda não entra: a CCT não tem coluna de ronda por cargo).",
        "folha",
        "DGX F2 §7.1 e §7.2",
        "dinheiro",
        SQL_ADICIONAL_FORA_CCT,
        "pessoas",
        "/redesign/departamento-pessoal?t=cct-funcoes",
    ),
    (
        "D03",
        "Ativos sem cargo da CCT",
        "Ativos sem função da CCT ficam FORA de toda conferência de piso e de evento — o sistema "
        "não sabe qual piso cobrar nem qual adicional é devido. Preencher `cct_cargo_id` no "
        "cadastro de cada um (na frente F2 eram ALAN VIEIRA, ALEXANDRE SOUZA, KELLY PATRICIA "
        "como AGENTE DE PORTARIA, NAILSON GARCIA como ARTÍFICE e THIAGO MAQUINE como JARDINEIRO)?",
        "cadastro",
        "DGX F2 §7.3",
        "cadastro",
        SQL_SEM_CARGO_CCT,
        "pessoas",
        "/redesign/departamento-pessoal?t=funcionarios",
    ),
    (
        "D04",
        "Escalas lançadas na paridade errada",
        "Há escala de 12x36 lançada no dia errado — a grade nos ímpares, a vida nos pares "
        "(RILEM, ADEILSON, MAIARA e mais um). Enquanto não for arrumada, o mapa de ponto chama o "
        "posto de descoberto todo dia e essas pessoas aparecem como «fora de escala». Quem "
        "corrige a grade é a operação: quem faz, e até quando?",
        "ponto",
        "DGX W1 §7.3 (caçador checar_escala_paridade)",
        "operacao",
        SQL_ESCALA_PARIDADE,
        "pessoas-mês",
        "/redesign/operacional?t=g-escalas",
    ),
    (
        "D05",
        "Hora extra sem explicação",
        "Cobertura de FALTA é repassável ao cliente? Hoje a sugestão diz que sim, mas manter o "
        "posto coberto quando um agente falta pode ser obrigação contratual nossa — nesse caso "
        "`cobertura_falta` deveria nascer custo nosso. E a HE repassável vira cobrança (item de "
        "NFS-e ou aditivo)? Quem confirma a classificação — hoje qualquer `module:dp`? O número "
        "abaixo é a HE da última competência que nasceu «falta de efetivo» (custo nosso) e "
        "ninguém confirmou.",
        "ponto",
        "DGX W3 §7.1",
        "dinheiro",
        SQL_HE_SEM_EXPLICACAO,
        "itens",
        "/redesign/departamento-pessoal?t=he-classificar",
    ),
    (
        "D06",
        "Postos apontando para contrato inexistente",
        "Postos da Conecta Village apontam para um contrato que não existe (`801b96b0…`, cliente "
        "CONECTAMAIS ELETRONICA/HOMOLOGAÇÃO). Por causa disso, 310 das 393 linhas de HE de 08/2026 "
        "ficam sem contrato. Ligar a um contrato real (qual?), ou deixar como está porque é "
        "homologação?",
        "operacional",
        "DGX T3 §7.2",
        "cadastro",
        SQL_POSTO_CONTRATO_FANTASMA,
        "itens",
        "/redesign/operacional?t=g-postos",
    ),
    (
        "D07",
        "Postos sem salário base",
        "Salário base por vaga: hoje nenhum posto tem. Sem ele, «Custo por contrato» mostra R$ 0. "
        "Preencher pela CCT (piso por função) em lote, ou vaga a vaga?",
        "operacional",
        "DGX T3 §7.3",
        "dinheiro",
        SQL_POSTO_SEM_SALARIO,
        "itens",
        "/redesign/operacional?t=g-postos",
    ),
    (
        "D08",
        "Clientes sem visita há mais de 30 dias",
        "Clientes ativos sem visita há mais de 30 dias (ou que nunca receberam nenhuma) — é a "
        "régua certa, 30 ou 60 dias? Hoje ninguém tem meta de visita.",
        "operacional",
        "DGX T3 §7.7",
        "operacao",
        SQL_CLIENTE_SEM_VISITA,
        "itens",
        "/redesign/crm?t=visitas-por-cliente",
    ),
    (
        "D09",
        "Pessoas sem foto",
        "Foto do funcionário: não há upload no sistema, e sem isso o crachá sai sempre com moldura "
        "vazia. Depois que o upload existir, foto passa a ser obrigatória na admissão? Se for "
        "regra, entra em «cadastro incompleto».",
        "cadastro",
        "DGX F6 §7.5 e DGX T1 §7.3",
        "cadastro",
        SQL_SEM_FOTO,
        "pessoas",
        "/redesign/departamento-pessoal?t=funcionarios",
    ),
    (
        "D10",
        "Pessoas sem CNH cadastrada",
        "Cadastrar a CNH dos supervisores (`cnh_numero` / `cnh_categoria` / `cnh_validade`): com "
        "isso a lista de motoristas passa a ser só quem pode dirigir, e a validade vencida pode "
        "bloquear a saída do veículo. Quem cadastra, e a validade vencida bloqueia mesmo?",
        "cadastro",
        "DGX F10 §7.2",
        "risco",
        SQL_SEM_CNH,
        "pessoas",
        "/redesign/departamento-pessoal?t=funcionarios",
    ),
    (
        "D11",
        "Dependentes sem data de nascimento",
        "Os dependentes que vieram do backfill Portte estão sem nome e sem data de nascimento — "
        "pagam cota de salário-família «sem prova». Cadastrar nome e nascimento de cada um (aba "
        "Dependentes → Remover + Novo), ou aceitar como está?",
        "folha",
        "DGX F6 §7.2",
        "dinheiro",
        SQL_DEPENDENTE_SEM_NASCIMENTO,
        "itens",
        "/redesign/departamento-pessoal?t=dependentes",
    ),
    (
        "D12",
        "Férias na faixa > 22 meses (risco de dobra)",
        "Para cada nome na faixa > 22 meses: confirmar no Sólides/na pasta se a pessoa tirou "
        "férias — se tirou, registrar a férias gozada no ERP; se não tirou, marcar férias antes da "
        "dobra. E `hr_vacation_periods` foi semeada por calendário, com `limit_date` errado: "
        "apagar e ressemear a partir da admissão, ou fazer a aprovação atualizar "
        "`days_used`/`period_id`? Há duas verdades sobre o limite até o dono decidir.",
        "folha",
        "FRENTE 08 §5 (mapa de férias)",
        "risco",
        SQL_FERIAS_22_MESES,
        "pessoas",
        "/redesign/departamento-pessoal?t=mapa-ferias",
    ),
    (
        "D13",
        "Pensão alimentícia sem beneficiário",
        "Desconto de pensão no DP sem pensionista cadastrado em `financial_beneficiarios` não dá "
        "para pagar: o dinheiro sai do colaborador e não tem para onde ir. Hoje são 0 descontos e "
        "0 pensionistas — quando entrar o primeiro, cadastrar o beneficiário passa a ser parte "
        "obrigatória do desconto, ou fica manual?",
        "financeiro",
        "DGX F11 §4.7 (tela pensionistas)",
        "risco",
        SQL_PENSAO_SEM_BENEFICIARIO,
        "pessoas",
        "/redesign/financeiro?t=pensionistas",
    ),
    (
        "D14",
        "NF-e que chegou só em resumo",
        "NF-e que chegaram só como resumo (≈ R$ 13,4 mil, abr–set/2026: Maraitt Locadora, OCSEG, "
        "L J Guerra, B A Elétrica…): manifestar ciência para baixar o XML e entrar no estoque? "
        "Hoje o sync só processa XML completo, então essas compras não existem no custo.",
        "fiscal",
        "DGX F9 §7.3",
        "dinheiro",
        SQL_NFE_SO_RESUMO,
        "itens",
        "/redesign/suprimentos?t=nf-entrada",
    ),
    # ─── outras mensuráveis (mesmas fontes, número recontado aqui) ───
    (
        "D15",
        "Rubricas ativas que o motor nunca emitiu",
        "Rubricas marcadas como ativas que nunca apareceram em holerite nenhum: inativar pela tela "
        "ou manter como «reserva»? Enquanto ativas, a API e o Hermes as listam como se existissem.",
        "folha",
        "DGX F1 §7.5",
        "cadastro",
        SQL_RUBRICA_NUNCA_EMITIDA,
        "itens",
        "/redesign/departamento-pessoal?t=folha-rubricas",
    ),
    (
        "D16",
        "Colaboradores com dois logins",
        "Colaboradores com dois logins em `users` para o mesmo `employee_id`: o painel agrupa por "
        "pessoa, mas o sino e os não-lidos do app são por usuário. Qual login vale — e o outro é "
        "desativado?",
        "cadastro",
        "DGX F8 §7.3",
        "operacao",
        SQL_LOGIN_DUPLICADO,
        "pessoas",
        "/redesign/configuracoes?t=usuarios",
    ),
    (
        "D17",
        "Demitidos sem data de demissão",
        "Inativos/demitidos sem data de demissão (e sem motivo): cadastrar a data de cada um, ou "
        "aceitar a série de turnover como está?",
        "cadastro",
        "DGX T1 §7.2",
        "cadastro",
        SQL_DEMISSAO_SEM_DATA,
        "pessoas",
        "/redesign/departamento-pessoal?t=funcionarios",
    ),
    (
        "D18",
        "Alertas «lead sem contato» afogando o painel",
        "Os alertas vivos de `lead_sem_contato` afogam o painel proativo: a régua é sensível "
        "demais, ou os leads são lixo e devem ser arquivados?",
        "operacional",
        "DGX T3 §7.6",
        "operacao",
        SQL_LEAD_SEM_CONTATO,
        "itens",
        "/redesign/operacional?t=painel-alertas",
    ),
    # ─── escolha pura: SEM número, e a tela diz isso ───
    (
        "D19",
        "Folga trabalhada: hora extra ou folga compensatória?",
        "Folga trabalhada vira HE ou folga compensatória? Decidir a rubrica e quem aprova — a "
        "folha não lê nada disto ainda.",
        "folha",
        "DGX F8 §7.1",
        "dinheiro",
        None,
        None,
        "/redesign/departamento-pessoal?t=he-classificar",
    ),
    (
        "D20",
        "Veículo é patrimônio?",
        "Veículo entra em `equipments` como patrimônio? Se sim, as manutenções e a frota viram uma "
        "coisa só — pendente desde a frente 10.",
        "operacional",
        "DGX F10 §7.3",
        "cadastro",
        None,
        None,
        "/redesign/equipamentos",
    ),
    (
        "D21",
        "Quais itens de vistoria bloqueiam a saída do veículo",
        "Quais itens de vistoria bloqueiam a saída de verdade (freio, pneu, farol)? Marcar demais "
        "vira porteira fechada; de menos, vistoria decorativa. Hoje os 5 itens não bloqueiam nada.",
        "operacional",
        "DGX V3 §7.5",
        "risco",
        None,
        None,
        "/redesign/equipamentos?t=frota-vistoria-itens",
    ),
    (
        "D22",
        "Cobrança automática por e-mail sem clique",
        "Ligar o envio de cobrança SEM clique (um beat diário lendo os mesmos parâmetros)? Hoje é "
        "por clique de propósito — comunicação com cliente real é gate humano.",
        "financeiro",
        "DGX T4 §7.1",
        "risco",
        None,
        None,
        "/redesign/financeiro?t=g-receber",
    ),
    (
        "D23",
        "A fatura substitui ou soma?",
        "A fatura substitui alguma coisa, ou soma? Ela vai ao cliente (junto do boleto? antes da "
        "nota?) ou fica como conferência interna?",
        "financeiro",
        "DGX W2 §7.1",
        "operacao",
        None,
        None,
        "/redesign/financeiro?t=faturas",
    ),
    (
        "D24",
        "Quem passa a faturar: a fatura ou gerar_recebiveis?",
        "Se a fatura vira o caminho oficial, `gerar_recebiveis` deve parar de criar título para "
        "contrato que já tem fatura na competência — hoje daria para duplicar o título.",
        "financeiro",
        "DGX W2 §7.2",
        "dinheiro",
        None,
        None,
        "/redesign/financeiro?t=faturas",
    ),
    (
        "D25",
        "Motivo de admissão na transferência: 10 ou 11?",
        "O contador transmitiu com 11 (sucessão); entre empresas do mesmo grupo sem sucessão "
        "societária a tabela 19 manda 10. Muda o `tpAdmissao` do S-2200. Pergunta para o contador, "
        "não para o sistema.",
        "fiscal",
        "DGX W4 §7.1",
        "risco",
        None,
        None,
        "/redesign/departamento-pessoal?t=esocial",
    ),
    (
        "D26",
        "Ligar NBS/CST/cClassTrib na emissão da NFS-e?",
        "Hoje o XML vai com `cNBS 120032900` e `cTribMun 100` fixos para toda nota. Trocar por "
        "cadastro muda o documento fiscal — precisa do contador e de emissão em homologação antes.",
        "fiscal",
        "DGX V5 §7.1",
        "risco",
        None,
        None,
        "/redesign/fiscal?t=nfse",
    ),
    (
        "D27",
        "Quem recebe o pânico quando não há alerta configurado?",
        "Hoje: ninguém — fica só a ocorrência e a tela. A alternativa é cair para "
        "`posts.supervisor_phone` / `emergency_phone`. Qual é a regra?",
        "operacional",
        "DGX U4 §7.1",
        "risco",
        None,
        None,
        "/redesign/operacional?t=ocorrencias",
    ),
    (
        "D28",
        "O CSV de apontamento deve LANÇAR na folha, ou só apontar?",
        "Hoje aponta (paralelo cego). Lançar é mudança no motor de cálculo, com oráculo de igualdade antes.",
        "folha",
        "DGX V4 §7.1",
        "dinheiro",
        None,
        None,
        "/redesign/departamento-pessoal?t=folha-apontamentos-importar",
    ),
)


async def ensure(db) -> None:
    """DDL + semente. Idempotente: roda no 1º acesso e em toda ação."""
    for ddl in _DDL:
        await db.execute(text(ddl))
    for codigo, titulo, pergunta, area, origem, impacto, sql, unidade, tela in SEMENTE:
        await db.execute(
            text(
                "INSERT INTO dono_decisoes "
                "(codigo, titulo, pergunta, area, origem, impacto, numero_sql, unidade, tela_para_agir) "
                "VALUES (:c, :t, :p, :a, :o, :i, :s, :u, :tl) ON CONFLICT (codigo) DO NOTHING"
            ),
            {
                "c": codigo,
                "t": titulo,
                "p": pergunta,
                "a": area,
                "o": origem,
                "i": impacto,
                "s": sql,
                "u": unidade,
                "tl": tela,
            },
        )
    await db.commit()


# ───────────────────────────────── medir ─────────────────────────────────
class _Desfaz(Exception):  # noqa: N818 — não é erro: é a sentinela que desfaz o savepoint
    """Sentinela: carrega o valor medido e força o SAVEPOINT a voltar atrás.

    O `async with db.begin_nested()` libera o savepoint quando o bloco termina bem e o desfaz
    quando sai por exceção. Sair SEMPRE por exceção é o que torna a medição só-leitura de fato,
    e não só de intenção.
    """


def proibido(sql: str) -> str | None:
    """Palavra de escrita encontrada no SQL, ou None. Público: o oráculo chama direto."""
    m = _PROIBIDO.search(sql or "")
    return m.group(1).upper() if m else None


async def medir(db, sql: str | None, timeout_ms: int = TIMEOUT_MS) -> tuple[object | None, str | None]:
    """Roda UM `numero_sql` e devolve `(valor, erro)`. Nunca levanta: erro vira texto curto."""
    if not (sql or "").strip():
        return (None, None)
    palavra = proibido(sql)
    if palavra:
        return (None, f"consulta recusada: contém {palavra}")
    try:
        async with db.begin_nested():
            await db.execute(text(f"SET LOCAL statement_timeout = {int(timeout_ms)}"))
            valor = (await db.execute(text(sql))).scalar()
            raise _Desfaz(valor)
    except _Desfaz as ok:
        return (ok.args[0], None)
    except Exception as exc:  # noqa: BLE001 — a linha mostra «não medido», o painel segue de pé
        logger.warning("x5: numero_sql falhou: %s", exc)
        return (None, f"{type(exc).__name__}: {str(exc).splitlines()[0][:120]}")


async def listar(db, medindo: bool = True) -> list[dict]:
    """Todas as decisões, com o número de HOJE quando há `numero_sql`."""
    rows = (
        await db.execute(
            text(
                "SELECT codigo, titulo, pergunta, area, origem, impacto, numero_sql, unidade, "
                "tela_para_agir, status, decisao, decidida_por, decidida_em, criada_em "
                "FROM dono_decisoes ORDER BY area, codigo"
            )
        )
    ).fetchall()
    saida: list[dict] = []
    for r in rows:
        d = {
            "codigo": r[0],
            "titulo": r[1],
            "pergunta": r[2],
            "area": r[3],
            "origem": r[4],
            "impacto": r[5],
            "numero_sql": r[6],
            "unidade": r[7],
            "tela_para_agir": r[8],
            "status": r[9],
            "decisao": r[10],
            "decidida_por": r[11],
            "decidida_em": r[12],
            "criada_em": r[13],
        }
        d["valor"], d["erro"] = (await medir(db, r[6])) if medindo else (None, None)
        saida.append(d)
    return saida


# ───────────────────────────────── decidir ─────────────────────────────────
async def decidir(db, codigo: str, decisao: str, quem: str, status: str = "decidida") -> dict:
    """Grava a decisão, o autor e a data. Tira a linha da lista de abertas."""
    codigo = (codigo or "").strip().upper()
    decisao = (decisao or "").strip()
    if status not in ("decidida", "descartada"):
        raise DecisaoErro("Status inválido: use «decidida» ou «descartada».")
    if not decisao:
        raise DecisaoErro("Escreva a decisão — é ela que fica registrada.")
    await ensure(db)
    row = (
        await db.execute(
            text(
                "UPDATE dono_decisoes SET status = :st, decisao = :d, decidida_por = :q, "
                "decidida_em = now() WHERE codigo = :c RETURNING codigo, titulo, status"
            ),
            {"st": status, "d": decisao[:4000], "q": (quem or "")[:120], "c": codigo},
        )
    ).first()
    if not row:
        await db.rollback()
        raise DecisaoErro(f"Decisão «{codigo}» não existe.", status=404)
    await db.commit()
    # O registro fica na linha E no log — quem decidiu o quê, quando, é rastro que não se perde
    # num UPDATE posterior.
    logger.info("x5 decisão %s por %s: [%s] %s", row[0], quem, row[2], decisao[:300])
    return {"codigo": row[0], "titulo": row[1], "status": row[2]}
