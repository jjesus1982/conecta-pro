"""Mapa de férias por idade do período aquisitivo (frente 08, 12/09/2026).

Faixas da DGX: <12 (em aquisição) · 12–16 · 17–19 · 20–22 · >22 meses. A `>22` é o alarme de
dobra: o período concessivo acaba aos 24 meses e férias concedidas depois disso são pagas em
dobro (art. 137 CLT).

Fonte de férias GOZADAS é `hr_vacation_requests` APROVADA — `hr_vacation_periods.days_used` está
em 0 nas 67 linhas do staging mesmo com 5 férias aprovadas (period_id NULL): a tabela de períodos
foi semeada por calendário (2025-01-01 / 2026-01-19) e não é atualizada pelo fluxo de aprovação.
Dela sai só `days_entitled` (quando existe) e `limit_date`, devolvido como `limite_erp`.

Só leitura. Fuso: "hoje" é o de Manaus.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.integrations.connectors.whatsapp.identidade import SEM_VINCULO

EM_AQUISICAO = "< 12 meses (em aquisição)"
DOBRA = "> 22 meses (risco de dobra)"
AFASTADO_LONGO = "afastado > 6 meses (reinicia no retorno)"
NAO_CALCULADO = "não calculado"
#: Ordem da legenda. Soma de todas == ativos com vínculo (é o que o oráculo afirma).
FAIXAS = (EM_AQUISICAO, "12–16", "17–19", "20–22", DOBRA, AFASTADO_LONGO, NAO_CALCULADO)

#: Dias de férias por período aquisitivo com até 5 faltas (art. 130, I, CLT). Só vale quando o
#: ERP não tem linha em hr_vacation_periods para a pessoa — se tem, `days_entitled` manda.
DIAS_CLT_ART_130 = 30
#: Afastamento previdenciário acima disto reinicia o período (art. 133, IV e §2º).
MESES_AFASTAMENTO_LONGO = 6

#: `demitido` fica FORA de SEM_VINCULO de propósito lá (ele ainda conversa sobre rescisão);
#: aqui é vínculo encerrado, então soma-se. PJ e homologação não têm férias CLT.
SQL_PESSOAS = """
SELECT e.id::text, e.nome, coalesce(e.cargo,'—'), e.data_admissao, e.status
FROM employees e
WHERE e.status <> ALL(:sem) AND e.status <> 'demitido'
  AND coalesce(e.is_homologacao,false) = false
  AND coalesce(e.tipo_contrato,'') NOT ILIKE '%pj%'
ORDER BY e.nome
"""
SQL_AFASTAMENTOS = """
SELECT a.employee_id::text, coalesce(a.tipo,''), a.data_inicio, a.data_retorno, lower(coalesce(a.status,''))
FROM sst_afastamentos a WHERE a.data_inicio IS NOT NULL
"""
SQL_GOZADAS = """
SELECT r.employee_id::text, r.days_requested, r.start_date, r.end_date
FROM hr_vacation_requests r
WHERE upper(coalesce(r.status,'')) = 'APPROVED' AND r.start_date <= CAST(:hoje AS date)
"""
#: Linha mais antiga ainda não gozada por inteiro: é a que dá direito e limite do ERP.
SQL_PERIODOS = """
SELECT DISTINCT ON (p.employee_id) p.employee_id::text, p.days_entitled, p.limit_date
FROM hr_vacation_periods p WHERE coalesce(p.is_fully_used,false) = false
ORDER BY p.employee_id, p.start_date
"""


def hoje_manaus() -> date:
    return datetime.now(ZoneInfo("America/Manaus")).date()


def meses_entre(a: date, b: date) -> int:
    """Meses de calendário completos de `a` até `b` (negativo se b < a)."""
    d = relativedelta(b, a)
    return d.years * 12 + d.months


def faixa(idade_meses: int | None) -> str:
    """Faixa da DGX pela idade do período aquisitivo aberto. None = sem dado, faixa própria."""
    if idade_meses is None:
        return NAO_CALCULADO
    if idade_meses < 12:
        return EM_AQUISICAO
    if idade_meses <= 16:
        return "12–16"
    if idade_meses <= 19:
        return "17–19"
    if idade_meses <= 22:
        return "20–22"
    return DOBRA


def _previdenciario(tipo: str) -> bool:
    t = tipo.lower()
    return "doenca" in t or "doença" in t or "acidente" in t


def _longo(inicio: date, fim: date) -> bool:
    return fim > inicio + relativedelta(months=MESES_AFASTAMENTO_LONGO)


def ancora_periodo(admissao: date | None, afastamentos: list[tuple]) -> date | None:
    """Início da contagem do período aquisitivo.

    Art. 133, IV, CLT: não tem direito a férias quem, no período aquisitivo, recebeu benefício
    previdenciário por acidente ou doença por mais de 6 meses; §2º: o novo período começa quando
    o empregado volta ao serviço. Logo a âncora é a MAIOR data entre a admissão e o retorno de
    cada afastamento previdenciário (doença/acidente) que durou mais de 6 meses.

    `afastamentos` = [(tipo, data_inicio, data_retorno | None, status), ...]. Afastamento em
    curso (sem retorno) não move a âncora — ainda não há retorno. Sem admissão → None.
    Limite conhecido: soma afastamentos descontínuos NÃO é feita (a lei conta o total no período).
    """
    if admissao is None:
        return None
    retornos = [ret for tipo, ini, ret, _st in afastamentos
                if ret is not None and _previdenciario(tipo) and _longo(ini, ret)]
    return max([admissao, *retornos])


def afastado_longo_em_curso(afastamentos: list[tuple], hoje: date) -> bool:
    """Previdenciário, sem retorno, já passou de 6 meses: o período vai reiniciar no retorno."""
    return any(ret is None and st in ("ativo", "em_andamento") and _previdenciario(tipo) and _longo(ini, hoje)
               for tipo, ini, ret, st in afastamentos)


def _dias(days_requested, ini, fim) -> int:
    if days_requested is not None:
        return int(days_requested)
    if ini and fim:
        return (fim - ini).days + 1
    return 0


def situacao(admissao, afastamentos, gozados_dias: int, direito: int, hoje: date) -> dict:
    """Idade, faixa, saldo e limite de UMA pessoa. Puro — o oráculo e o demo() chamam direto.

    Férias gozadas consomem o período mais antigo primeiro: k períodos inteiros fechados =
    gozados // direito; o que sobra é o usado do período aberto.
    """
    ancora = ancora_periodo(admissao, afastamentos)
    if ancora is None:
        return {"ancora": None, "inicio_periodo": None, "idade_meses": None, "faixa": NAO_CALCULADO,
                "direito": direito, "usados": None, "restantes": None, "limite": None,
                "dias_para_limite": None, "risco_dobra": False, "vencida": False}
    k = gozados_dias // direito if direito else 0
    usados = gozados_dias - k * direito
    inicio = ancora + relativedelta(months=12 * k)
    if afastado_longo_em_curso(afastamentos, hoje):
        return {"ancora": ancora, "inicio_periodo": inicio, "idade_meses": None, "faixa": AFASTADO_LONGO,
                "direito": direito, "usados": usados, "restantes": direito - usados, "limite": None,
                "dias_para_limite": None, "risco_dobra": False, "vencida": False}
    idade = meses_entre(inicio, hoje)
    # aquisitivo 12 meses + concessivo 12 meses (art. 134): último dia para conceder
    limite = inicio + relativedelta(months=24) - timedelta(days=1)
    return {"ancora": ancora, "inicio_periodo": inicio, "idade_meses": idade, "faixa": faixa(idade),
            "direito": direito, "usados": usados, "restantes": direito - usados, "limite": limite,
            "dias_para_limite": (limite - hoje).days, "risco_dobra": idade > 22, "vencida": hoje > limite}


async def mapa(db: AsyncSession, hoje: date | None = None) -> list[dict]:
    """Uma linha por ativo com vínculo, ordenada do maior risco para o menor."""
    hoje = hoje if hoje is not None else hoje_manaus()
    pessoas = (await db.execute(text(SQL_PESSOAS), {"sem": list(SEM_VINCULO)})).fetchall()
    afast: dict[str, list[tuple]] = {}
    for eid, tipo, ini, ret, st in (await db.execute(text(SQL_AFASTAMENTOS))).fetchall():
        afast.setdefault(eid, []).append((tipo, ini, ret, st))
    gozados: dict[str, int] = {}
    for eid, dr, ini, fim in (await db.execute(text(SQL_GOZADAS), {"hoje": hoje})).fetchall():
        gozados[eid] = gozados.get(eid, 0) + _dias(dr, ini, fim)
    periodos = {eid: (ent, lim) for eid, ent, lim in (await db.execute(text(SQL_PERIODOS))).fetchall()}

    out = []
    for eid, nome, cargo, admissao, status in pessoas:
        ent, limite_erp = periodos.get(eid, (None, None))
        direito = int(ent) if ent is not None else DIAS_CLT_ART_130
        s = situacao(admissao, afast.get(eid, []), gozados.get(eid, 0), direito, hoje)
        out.append({"employee_id": eid, "nome": nome, "cargo": cargo, "status": status, "admissao": admissao,
                    "gozados_total": gozados.get(eid, 0), "limite_erp": limite_erp,
                    "tem_periodo_erp": ent is not None, **s})
    ordem = {DOBRA: 0, "20–22": 1, "17–19": 2, "12–16": 3, AFASTADO_LONGO: 4, NAO_CALCULADO: 5, EM_AQUISICAO: 6}
    out.sort(key=lambda r: (ordem[r["faixa"]], -(r["idade_meses"] if r["idade_meses"] is not None else -1), r["nome"]))
    return out


def demo() -> None:
    h = date(2026, 9, 12)
    assert faixa(None) == NAO_CALCULADO and faixa(0) == EM_AQUISICAO and faixa(11) == EM_AQUISICAO
    assert faixa(12) == "12–16" == faixa(16) and faixa(17) == "17–19" == faixa(19)
    assert faixa(20) == "20–22" == faixa(22) and faixa(23) == DOBRA
    adm = date(2023, 10, 6)
    longo = [("doenca", date(2025, 1, 10), date(2025, 8, 20), "encerrado")]
    curto = [("doenca", date(2025, 1, 10), date(2025, 3, 1), "encerrado")]
    assert ancora_periodo(adm, longo) == date(2025, 8, 20)
    assert ancora_periodo(adm, curto) == adm
    assert ancora_periodo(adm, [("suspensao_contratual", date(2025, 1, 1), date(2025, 9, 1), "encerrado")]) == adm
    assert ancora_periodo(None, longo) is None
    # sem afastamento: 35 meses de casa → dobra
    s = situacao(adm, [], 0, 30, h)
    assert s["faixa"] == DOBRA and s["vencida"] and s["idade_meses"] == 35
    # afastamento longo: período reinicia no retorno → 12 meses
    s = situacao(adm, longo, 0, 30, h)
    assert s["ancora"] == date(2025, 8, 20) and s["idade_meses"] == 12 and s["faixa"] == "12–16"
    # 30 dias gozados fecham o 1º período: aberto começa em 2024-10-06 → 23 meses → dobra iminente
    s = situacao(adm, [], 30, 30, h)
    assert s["inicio_periodo"] == date(2024, 10, 6) and s["idade_meses"] == 23 and s["faixa"] == DOBRA
    assert s["limite"] == date(2026, 10, 5) and s["dias_para_limite"] == 23 and not s["vencida"]
    # 20 dias gozados: mesmo período, 10 restantes
    s = situacao(date(2025, 2, 16), [], 20, 30, h)
    assert s["usados"] == 20 and s["restantes"] == 10 and s["faixa"] == "17–19"
    # afastado > 6 meses em curso: faixa própria, sem idade
    s = situacao(adm, [("doenca", date(2026, 3, 2), None, "ativo")], 0, 30, h)
    assert s["faixa"] == AFASTADO_LONGO and s["idade_meses"] is None
    # admitido hoje: idade 0 = em aquisição, não "não calculado"
    assert situacao(h, [], 0, 30, h)["faixa"] == EM_AQUISICAO
    assert situacao(None, [], 0, 30, h)["faixa"] == NAO_CALCULADO
    print("demo ok")


if __name__ == "__main__":
    demo()
