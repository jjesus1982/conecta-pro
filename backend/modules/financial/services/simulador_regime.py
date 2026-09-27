"""Simulador de regime tributário por empresa — Simples × Presumido × Real.

Existe porque a decisão do regime de 2027 tem prazo (31/01) e hoje é feita numa planilha
de terceiro que **usa a alíquota errada para esta casa**: a aba `REAL` da planilha do curso
aplica PIS 1,65% e COFINS 7,6% (não-cumulativos), quando vigilância e limpeza são 0,65% e
3,00% CUMULATIVOS por lei (Lei 10.833/2003, art. 10, XXIV). Quem decidir por aquela planilha
erra por 5,6 pontos e escolhe o regime errado.

## O que ele NÃO faz

Não decide. Devolve os três números com a abertura por tributo e diz de onde veio cada
alíquota. A escolha do regime é ato do dono com o contador.

E não chuta o RBT12: se não der para determiná-lo, **recusa**. Ver `RBT12NaoDeterminadoError`.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

# ─── Simples Nacional, Anexo IV (vigilância, limpeza, conservação) ────────────
#
# (teto do RBT12, alíquota nominal, parcela a deduzir) — LC 123/2006, Anexo IV.
#
# CONFERIDO POR DOIS CAMINHOS INDEPENDENTES em 26/09/2026: as duas guias reais da
# Patrimonial caem em faixas DIFERENTES (07/2026 na 2ª, 08/2026 na 3ª) e a fórmula
# `(RBT12 × nominal − deduzir) / RBT12` fecha nas duas.
#
# A 6ª FAIXA ESTÁ AUSENTE DE PROPÓSITO. As fontes consultadas dão parcela a deduzir de
# R$ 828.000, o que faria a alíquota efetiva CAIR de 16,89% para 10,00% ao cruzar
# R$ 3,6 milhões. Nenhuma tabela progressiva cai. Enquanto não for confirmada na fonte
# oficial, o simulador RECUSA RBT12 acima de R$ 3,6 mi em vez de devolver número — e isso
# importa: a Patrimonial está a 87% desse teto.
ANEXO_IV: list[tuple[float, float, float]] = [
    (180_000.00, 0.045, 0.00),
    (360_000.00, 0.090, 8_100.00),
    (720_000.00, 0.102, 12_420.00),
    (1_800_000.00, 0.140, 39_780.00),
    (3_600_000.00, 0.220, 183_780.00),
]

#: Lucro Presumido — base presumida de serviços em geral (IN RFB 1.700, Anexo).
BASE_PRESUMIDA_SERVICOS = 0.32
IRPJ = 0.15
IRPJ_ADICIONAL = 0.10
IRPJ_LIMITE_MENSAL = 20_000.00
CSLL = 0.09

#: PIS/COFINS CUMULATIVOS. Vigilância e limpeza permanecem no cumulativo mesmo no Lucro
#: Real — Lei 10.833/2003, art. 10, XXIV. «Lucro Real» não implica «não-cumulativo»: são
#: eixos independentes, e confundi-los é o erro da planilha de mercado.
PIS_CUMULATIVO = 0.0065
COFINS_CUMULATIVO = 0.0300


class FaixaNaoConfirmadaError(ValueError):
    """RBT12 na 6ª faixa do Anexo IV, cuja parcela a deduzir não foi confirmada."""


class RBT12NaoDeterminadoError(ValueError):
    """Sem receita para projetar o RBT12 — e chutá-lo escolhe a faixa, logo o imposto."""


def aliquota_efetiva_anexo_iv(rbt12: float) -> tuple[float, int]:
    """Alíquota efetiva e número da faixa. Levanta na 6ª, que não foi confirmada."""
    if rbt12 <= 0:
        raise RBT12NaoDeterminadoError("RBT12 zero ou negativo")
    for i, (teto, nominal, deduzir) in enumerate(ANEXO_IV, start=1):
        if rbt12 <= teto:
            return (rbt12 * nominal - deduzir) / rbt12, i
    raise FaixaNaoConfirmadaError(
        f"RBT12 de R$ {rbt12:,.2f} cai na 6ª faixa do Anexo IV, cuja parcela a deduzir "
        "não foi confirmada na fonte oficial (as fontes consultadas quebram a "
        "continuidade da curva). Confirme em sped.rfb.gov.br antes de usar."
    )


@dataclass
class Cenario:
    regime: str
    carga_total: float
    pct_receita: float
    abertura: dict[str, float] = field(default_factory=dict)
    nota: str = ""


def _conn():
    url = re.sub(r"\+asyncpg|\+psycopg2?", "", os.getenv("DATABASE_URL", ""))
    return psycopg2.connect(url)


def _dados(empresa_id: str, competencia: str) -> dict:
    """Receita, despesa operacional e folha da competência — do razão, não de estimativa."""
    with _conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
              coalesce(sum(a.valor) FILTER (
                  WHERE a.conta_credito LIKE '4.1%%' AND a.conta_credito NOT LIKE '4.3%%'), 0) receita,
              coalesce(sum(a.valor) FILTER (
                  WHERE c.account_type IN ('EXPENSE','COST')
                    AND a.conta_debito NOT LIKE '5.2.2%%'), 0) despesa_sem_tributo
              FROM accounting_entries a
         LEFT JOIN fin_accounting_accounts c ON c.code = a.conta_debito
             WHERE a.empresa_id = %s::uuid AND a.periodo_competencia = %s
               AND coalesce(a.tipo_lancamento,'') <> 'apuracao'
            """,
            (empresa_id, competencia),
        )
        r = dict(cur.fetchone() or {})
        cur.execute(
            "SELECT coalesce(sum(total_earnings),0) folha FROM hr_payslips "
            "WHERE empresa_id = %s::uuid AND to_char(competence_end,'YYYY-MM') = %s",
            (empresa_id, competencia),
        )
        r["folha"] = float((cur.fetchone() or {}).get("folha") or 0)
        cur.execute(
            "SELECT regime_tributario, anexo_simples FROM empresas WHERE id = %s::uuid",
            (empresa_id,),
        )
        e = cur.fetchone() or {}
        r["regime_cadastrado"] = e.get("regime_tributario")
        r["anexo_cadastrado"] = e.get("anexo_simples")
    return {
        k: (float(v) if isinstance(v, (int, float)) or hasattr(v, "real") and not isinstance(v, str) else v)
        for k, v in r.items()
    }


def simular(
    empresa_id: str,
    competencia: str,
    *,
    rbt12: float | None = None,
    aliquota_iss: float = 0.05,
    anexo: str = "IV",
) -> dict:
    """Os três regimes sobre a MESMA competência, com a abertura por tributo.

    `rbt12` ausente projeta o maduro: 12 × a receita da competência. É a pergunta que
    interessa para decidir 2027 — a Patrimonial está barata hoje só porque abriu em
    31/03/2026 e o RBT12 ainda está proporcionalizado.

    `aliquota_iss` 5% é a de Manaus para os itens 11.02, 07.10, 17.05 e 14.01
    (LC municipal 2.833/2021), conferida em 26/09/2026.
    """
    d = _dados(empresa_id, competencia)
    receita = float(d["receita"])
    if receita <= 0:
        raise RBT12NaoDeterminadoError(f"empresa {empresa_id} não tem receita em {competencia} — sem base para simular")
    folha = float(d["folha"])
    despesa = float(d["despesa_sem_tributo"])
    lucro = receita - despesa
    rbt = rbt12 if rbt12 is not None else receita * 12

    cenarios: dict[str, Cenario] = {}

    # ─── Simples Nacional ────────────────────────────────────────────────────
    efetiva, faixa = aliquota_efetiva_anexo_iv(rbt)
    das = receita * efetiva
    # No Anexo IV a CPP patronal e o RAT ficam FORA do DAS (LC 123, art. 18 §5º-C).
    cpp = folha * 0.23 if (anexo or "").upper().endswith("IV") else 0.0
    cenarios["simples"] = Cenario(
        regime=f"Simples Nacional Anexo {anexo}",
        carga_total=das + cpp,
        pct_receita=(das + cpp) / receita,
        abertura={"das": das, "cpp_patronal_fora_do_das": cpp},
        nota=(
            f"faixa {faixa}, alíquota efetiva {efetiva:.4%} sobre RBT12 de R$ {rbt:,.2f}. "
            + ("CPP 20% + RAT 3% por fora — Anexo IV." if cpp else "CPP dentro do DAS.")
        ),
    )

    # ─── Lucro Presumido ─────────────────────────────────────────────────────
    base = receita * BASE_PRESUMIDA_SERVICOS
    adic = max(0.0, base - IRPJ_LIMITE_MENSAL) * IRPJ_ADICIONAL
    pres = {
        "irpj": base * IRPJ,
        "irpj_adicional": adic,
        "csll": base * CSLL,
        "pis": receita * PIS_CUMULATIVO,
        "cofins": receita * COFINS_CUMULATIVO,
        "iss": receita * aliquota_iss,
        "cpp_patronal": folha * 0.288,  # 20% + RAT 3% + terceiros 5,8%
    }
    cenarios["lucro_presumido"] = Cenario(
        regime="Lucro Presumido",
        carga_total=sum(pres.values()),
        pct_receita=sum(pres.values()) / receita,
        abertura=pres,
        nota=f"base presumida {BASE_PRESUMIDA_SERVICOS:.0%} para serviços em geral",
    )

    # ─── Lucro Real ──────────────────────────────────────────────────────────
    lucro_positivo = max(0.0, lucro)
    real = {
        "irpj": lucro_positivo * IRPJ,
        "irpj_adicional": max(0.0, lucro_positivo - IRPJ_LIMITE_MENSAL) * IRPJ_ADICIONAL,
        "csll": lucro_positivo * CSLL,
        "pis": receita * PIS_CUMULATIVO,
        "cofins": receita * COFINS_CUMULATIVO,
        "iss": receita * aliquota_iss,
        "cpp_patronal": folha * 0.288,
    }
    cenarios["lucro_real"] = Cenario(
        regime="Lucro Real",
        carga_total=sum(real.values()),
        pct_receita=sum(real.values()) / receita,
        abertura=real,
        nota=(
            f"IRPJ/CSLL sobre o lucro REAL de R$ {lucro:,.2f} ({lucro / receita:.1%} da "
            "receita). PIS/COFINS CUMULATIVOS (0,65% e 3,00%) — vigilância e limpeza "
            "permanecem no cumulativo mesmo no Lucro Real, Lei 10.833 art. 10, XXIV."
        ),
    )

    melhor = min(cenarios.values(), key=lambda c: c.carga_total)
    return {
        "empresa_id": empresa_id,
        "competencia": competencia,
        "receita": receita,
        "folha": folha,
        "lucro_operacional": lucro,
        "rbt12_usado": rbt,
        "rbt12_projetado": rbt12 is None,
        "regime_cadastrado": d.get("regime_cadastrado"),
        "cenarios": {k: vars(v) for k, v in cenarios.items()},
        "menor_carga": melhor.regime,
        "economia_vs_cadastrado": None,
    }
