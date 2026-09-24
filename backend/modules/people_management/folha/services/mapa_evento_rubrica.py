"""O elo que faltava do «Evento como hub»: o mapa OCORRÊNCIA DO PONTO → RUBRICA DA FOLHA (DGX W5).

24/09/2026. A F1 trouxe a rubrica como DADO (os 40 atributos do evento da DGX em `rubricas_folha`)
e a F7 trouxe a configuração de ponto em CASCATA (`ponto_configuracoes`). O elo entre as duas
continuava em código: quando o ponto produz uma ocorrência (falta, HE 50%, adicional noturno, hora
noturna reduzida, intrajornada, DSR), quem decide em QUAL rubrica isso vira — e com que fórmula —
é `calculo_service.py`. Na DGX isso é uma linha de cadastro («Configurações de Ponto» → mapa
evento→rubrica + tipo de cálculo). Enquanto for código, mudar a CCT é mexer em Python.

**Paralelo cego.** `calculo_service.py` NÃO foi tocado — aqui só se LÊ. A semente reproduz
exatamente o que o motor faz hoje, cada linha com `origem_regra` apontando arquivo e linha; quem
prova que o cadastro diz a verdade é `scripts/orq/test_oraculo_w5_mapa_evento_rubrica.py`
(Σ|Δ| = R$ 0,00 nas 153 verbas de ponto de 08+09/2026). Ligar o motor a este cadastro é o passo
seguinte (o «F1-b» da F1), e este oráculo já é a trava dele.

Cascata, a MESMA da F7: **colaborador > escala > função > condomínio > empresa**. Linha inativa ou
fora da vigência é ignorada; dentro do mesmo escopo, a mais recente vence.

A `formula` é texto que se lê como se fala — «arred(salario_base ÷ 30) × dias» — e ao mesmo tempo
é avaliável (o oráculo recompõe o valor do holerite com ela). Nada em produção avalia fórmula:
o motor segue com a regra em Python e a tela só exibe o texto.

DDL idempotente em `_ensure(db)` (padrão da casa; `alembic/versions/` é zona proibida).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import text

#: De-para cargo do cadastro → cargo da CCT. Cópia FIEL de `calculo_service.CARGO_CCT_ALIAS`
#: (o oráculo precisa do piso efetivo por SQL próprio e não pode importar o motor em SQL).
#: Se o motor mudar o de-para, o oráculo acusa a diferença em (b) — é essa a graça.
CARGO_CCT_ALIAS = {
    "AGENTE DE PORTARIA": "PORTEIROS AGENTE DE PORTARIA GUARDETE",
    "AGENTE DE SERVICOS GERAIS": "SERVICOS GERAIS FAXINEIRO",
    "ARTIFICE": "ARTIFICE NAO ESPECIALIZADO",
    "LIDER DE PORTARIA": "LIDER DE PORTARIA",
    "JARDINEIROS": "JARDINEIROS",
    "JARDINEIRO": "JARDINEIROS",
}

#: Os eventos do ponto. `produzido` = o motor de folha REALMENTE emite uma verba para isso hoje
#: (levantado lendo `calculo_service.py` e conferido nos holerites de 08 e 09/2026). Os demais
#: existem na DGX e aqui não têm caminho nenhum — nem código, nem rubrica: por isso NÃO são
#: semeados (linha com rubrica inventada seria ficção). Ver §7 do relatório DGX_W5.
EVENTOS: dict[str, dict[str, Any]] = {
    "falta": {"rotulo": "Falta injustificada", "produzido": True},
    "dsr_sobre_falta": {"rotulo": "DSR perdido por falta", "produzido": True},
    "he50": {"rotulo": "Hora extra 50%", "produzido": True},
    "adicional_noturno": {"rotulo": "Adicional noturno", "produzido": True},
    "hora_noturna_reduzida": {"rotulo": "Hora noturna reduzida (52'30\")", "produzido": True},
    "intrajornada": {"rotulo": "Intrajornada não concedida (noturna)", "produzido": True},
    "intrajornada_diurna": {"rotulo": "Intrajornada não concedida (diurna)", "produzido": True},
    "dsr_sobre_he": {"rotulo": "DSR sobre verbas variáveis", "produzido": True},
    "falta_justificada": {"rotulo": "Falta justificada (abonada)", "produzido": False},
    "atraso": {"rotulo": "Atraso", "produzido": False},
    "he100": {"rotulo": "Hora extra 100%", "produzido": False},
    "feriado_trabalhado": {"rotulo": "Feriado trabalhado", "produzido": False},
    "sobreaviso": {"rotulo": "Sobreaviso", "produzido": False},
    "banco_horas_credito": {"rotulo": "Banco de horas — crédito", "produzido": False},
    "banco_horas_debito": {"rotulo": "Banco de horas — débito", "produzido": False},
}

#: do menos ao mais específico — o último que fala, vence (mesma ordem da F7)
ESCOPOS = ("empresa", "condominio", "funcao", "escala", "colaborador")
BASES = ("salario_base", "salario_minimo", "valor_hora", "piso_cct", "evento")

DDL = [
    """CREATE TABLE IF NOT EXISTS ponto_evento_rubrica (
  id serial PRIMARY KEY,
  evento varchar(40) NOT NULL,
  rubrica_codigo varchar(10) NOT NULL,
  escopo varchar(20) NOT NULL DEFAULT 'empresa'
      CHECK (escopo IN ('empresa','condominio','funcao','escala','colaborador')),
  escopo_id text NOT NULL DEFAULT '',
  formula text NOT NULL,
  base varchar(20) NOT NULL CHECK (base IN ('salario_base','salario_minimo','valor_hora','piso_cct','evento')),
  percentual numeric(10,4),
  ativo boolean NOT NULL DEFAULT true,
  vigencia_inicio date, vigencia_fim date,
  origem_regra text NOT NULL,
  criado_por varchar(120),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now())""",
    "CREATE INDEX IF NOT EXISTS ix_ponto_evento_rubrica ON ponto_evento_rubrica (evento, escopo, escopo_id) WHERE ativo",
]

#: A SEMENTE — exatamente o que `calculo_service.py` faz hoje, com a linha de onde saiu.
#: (evento, rubrica, fórmula, base, percentual, origem_regra)
#:
#: Variáveis da fórmula (o oráculo as monta do holerite + cadastro do empregado):
#:   horas/dias/plantoes = a QUANTIDADE que o motor gravou na `referencia` do holerite
#:   valor_hora = arred(salario_base ÷ divisor da escala)   ·   salario_base = base cheia (pós-piso)
#:   ronda = adicional_ronda_percentual ÷ 100   ·   valor_he = valor da HE 50% da mesma pessoa
#:   fator_dsr = 1/6 no 12x36, domingos÷dias úteis no comercial
SEMENTE: list[tuple[str, str, str, str, str | None, str]] = [
    (
        "falta",
        "1051",
        "arred(salario_base ÷ 30) × dias",
        "salario_base",
        "1.0000",
        "calculo_service.py L583-597 (_vd_falta = salario_base_full/30 × unjustified_absent_days de time_sheets); "
        "só desconta com cobertura de batidas ≥ COBERTURA_MINIMA_FALTAS — art. 6º Lei 605/49",
    ),
    (
        "dsr_sobre_falta",
        "1053",
        "arred(salario_base ÷ 30) × dias",
        "salario_base",
        "1.0000",
        "calculo_service.py L598-607 (dsr_lost_days de time_sheets × valor-dia) — art. 6º Lei 605/49",
    ),
    (
        "he50",
        "0040",
        "horas × valor_hora × 1,5",
        "valor_hora",
        "1.5000",
        "calculo_service.py L608-623 (horas_trab_reais − divisor da escala, × hora_normal × 1,5) — "
        "art. 59 §1º CLT / CCT SINDECOMPRESTS",
    ),
    (
        "adicional_noturno",
        "0020",
        "arred(horas × 60 ÷ 52,5) × valor_hora × 0,20",
        "valor_hora",
        "0.2000",
        "calculo_service.py L667-696 (7h de relógio por plantão agendado; redução 52'30\" → horas legais; 20%) — "
        "art. 73 CLT; decisão do Jordan 04/08/2026 (pagar pela ESCALA, não pelo ponto)",
    ),
    (
        "hora_noturna_reduzida",
        "0021",
        "horas × valor_hora × (1 + 0,20 + ronda) × 1,5",
        "valor_hora",
        "1.5000",
        "calculo_service.py L697-719 (hora fictícia da redução = 1h/plantão, paga como extra 50% sobre a base "
        "com adicionais habituais: noturno 20% + ronda) — fator medido em 96 observações da folha Portte jan-jun",
    ),
    (
        "intrajornada",
        "0031",
        "plantoes × valor_hora × (1 + 0,20 + ronda) × 1,5",
        "valor_hora",
        "1.5000",
        "calculo_service.py L720-746 (1h por plantão NOTURNO, só para employees.recebe_intrajornada) — "
        "art. 71 §4º CLT; bate 21/21 com a folha Portte em 6 meses",
    ),
    (
        "intrajornada_diurna",
        "0030",
        "plantoes × valor_hora × (1 + ronda) × 1,5",
        "valor_hora",
        "1.5000",
        "calculo_service.py L720-746 (1h por plantão DIURNO; sem o prêmio noturno — mede 1,5000 exato sem ronda) — "
        "art. 71 §4º CLT",
    ),
    (
        "dsr_sobre_he",
        "0090",
        "valor_he × fator_dsr",
        "evento",
        None,
        "calculo_service.py L748-775 (reflexo SÓ sobre hora extra: em 101 de 101 pessoas-mês com noturno e sem HE "
        "o DSR da Portte é zero; fator 1/6 no 12x36) — Súmulas 60/172 TST + CCT",
    ),
]

_ENSURED = False


async def _ensure(db) -> None:
    """DDL + semente, uma vez por processo. A semente só entra onde NÃO há linha daquele evento
    no escopo empresa — o que o dono editar nunca é sobrescrito."""
    global _ENSURED
    if _ENSURED:
        return
    for stmt in DDL:
        await db.execute(text(stmt))
    for evento, cod, formula, base, pct, origem in SEMENTE:
        await db.execute(
            text(
                "INSERT INTO ponto_evento_rubrica (evento, rubrica_codigo, escopo, escopo_id, formula, base, "
                "percentual, origem_regra, criado_por) "
                "SELECT CAST(:ev AS varchar), :cod, 'empresa', '', :f, :b, CAST(:p AS numeric), :o, 'dgx-w5' "
                " WHERE NOT EXISTS (SELECT 1 FROM ponto_evento_rubrica WHERE evento = CAST(:ev AS varchar) "
                "                     AND escopo = 'empresa')"
            ),
            {"ev": evento, "cod": cod, "f": formula, "b": base, "p": pct, "o": origem},
        )
    await db.commit()
    _ENSURED = True


_SQL_REGRAS = """
SELECT id, evento, rubrica_codigo, escopo, escopo_id, formula, base, percentual, vigencia_inicio, vigencia_fim,
       origem_regra
  FROM ponto_evento_rubrica
 WHERE ativo
   AND (vigencia_inicio IS NULL OR vigencia_inicio <= CAST(:ref AS date))
   AND (vigencia_fim IS NULL OR vigencia_fim >= CAST(:ref AS date))
 ORDER BY created_at, id
"""

#: Contexto da pessoa — reusa a mesma consulta da F7 (`config_ponto._SQL_CTX_EMPREGADO`) para a
#: cascata resolver o MESMO escopo nas duas frentes. Importado, não copiado.
from modules.people_management.ponto.config_ponto import _SQL_CTX_EMPREGADO  # noqa: E402


async def carregar_regras(db, ref: date | None = None) -> list[dict]:
    """Todas as linhas ativas e vigentes em `ref` (hoje por padrão). Uma leitura; `resolver` é puro."""
    await _ensure(db)
    ref = ref or datetime.now().date()
    return [dict(r) for r in (await db.execute(text(_SQL_REGRAS), {"ref": ref})).mappings().all()]


def _casa(regra: dict, ctx: dict[str, str | None]) -> bool:
    esc = regra["escopo"]
    if esc == "empresa":
        return True
    alvo = ctx.get(esc)
    if not alvo:
        return False
    a, b = str(regra["escopo_id"] or "").strip(), str(alvo).strip()
    return a == b or (esc in ("funcao", "escala") and a.casefold() == b.casefold())


def resolver(regras: list[dict], evento: str, **ctx: str | None) -> dict | None:
    """Pura. ctx: colaborador=, escala=, funcao=, condominio=. Devolve a linha mais específica
    que vale para este evento, ou None. Do menos ao mais específico; dentro do mesmo escopo, a
    mais recente vence (ordem de `created_at` da consulta)."""
    vencedora = None
    for esc in ESCOPOS:
        for r in regras:
            if r["evento"] == evento and r["escopo"] == esc and _casa(r, ctx):
                vencedora = r
    return vencedora


async def mapa_evento_rubrica(
    db,
    evento: str,
    employee_id: str | None = None,
    condominio_id: str | None = None,
    funcao: str | None = None,
    escala: str | None = None,
    ref: date | None = None,
) -> dict | None:
    """Em qual rubrica esta ocorrência do ponto vira verba, para esta pessoa, em `ref`.

    O que faltar no pedido é completado pelo cadastro do empregado (função, escala e condomínio).
    Devolve a linha do mapa (rubrica_codigo, formula, base, percentual, origem_regra, escopo) ou
    None quando não há regra — e None é resposta legítima: significa que este evento NÃO vira
    verba nenhuma hoje (os 7 eventos da DGX sem caminho aqui).
    """
    if employee_id:
        r = (await db.execute(text(_SQL_CTX_EMPREGADO), {"e": str(employee_id)})).mappings().first()
        if r:
            funcao = funcao or r["funcao"]
            escala = escala or r["escala"]
            condominio_id = condominio_id or r["condominio_id"]
    regras = await carregar_regras(db, ref)
    return resolver(
        regras,
        evento,
        colaborador=employee_id and str(employee_id),
        escala=escala,
        funcao=funcao,
        condominio=condominio_id and str(condominio_id),
    )
