"""
ApuracaoLucroRealService — IRPJ/CSLL REAL sobre o lucro do razão (não presunção).

No Lucro Real, a base é o LUCRO CONTÁBIL apurado (receita − deduções − custos/despesas
dedutíveis), não a presunção de 32% da receita (isso é Lucro Presumido). Este serviço lê
o razão real `accounting_entries` (que já tem receita de NFS-e, deduções ISS, folha,
encargos e COGS do estoque), isolado por empresa_id, e calcula IRPJ 15% + adicional 10% e
CSLL 9% sobre o lucro real do período (trimestral, como manda o Lucro Real trimestral).

Honestidade: o LALUR (adições/exclusões específicas) é do contador — aqui a base é o
resultado do razão, declarado explicitamente. Prejuízo → IRPJ/CSLL zero (e prejuízo fiscal
compensável, informado). NUNCA fabrica: se não há lançamento, o lucro é o que o razão diz.
"""

from __future__ import annotations

import logging
import os
import re
from decimal import ROUND_HALF_UP, Decimal

import psycopg2

logger = logging.getLogger(__name__)

EMPRESA_PRINCIPAL_ID = "619a3df1-8bce-49ce-b77a-04f80a0e8491"

IRPJ = Decimal("0.15")
IRPJ_ADICIONAL = Decimal("0.10")
CSLL = Decimal("0.09")
LIMITE_ADICIONAL_MES = Decimal("20000")  # R$ 20k/mês → R$ 60k/trimestre


def _db_url() -> str:
    return re.sub(r"\+asyncpg|\+psycopg2?", "", os.getenv("DATABASE_URL", ""))


def _q(v: Decimal) -> float:
    return float(v.quantize(Decimal("0.01"), ROUND_HALF_UP))


TRIMESTRE_MESES = {
    1: ["01", "02", "03"],
    2: ["04", "05", "06"],
    3: ["07", "08", "09"],
    4: ["10", "11", "12"],
}


class ApuracaoLucroRealService:
    def apurar(self, ano: int, trimestre: int | None = None,
               empresa_id: str = EMPRESA_PRINCIPAL_ID) -> dict:
        """Apura IRPJ/CSLL de um trimestre (ou do ano se trimestre=None) sobre o lucro real."""
        if trimestre and trimestre in TRIMESTRE_MESES:
            meses = [f"{ano}-{m}" for m in TRIMESTRE_MESES[trimestre]]
            rotulo = f"{trimestre}º trimestre/{ano}"
        else:
            meses = [f"{ano}-{m:02d}" for m in range(1, 13)]
            rotulo = f"Ano {ano}"

        conn = psycopg2.connect(_db_url())
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        COALESCE(sum(CASE WHEN conta_credito LIKE '3.1.1%%' THEN valor ELSE 0 END),0),
                        COALESCE(sum(CASE WHEN conta_debito  LIKE '3.1.2%%' THEN valor ELSE 0 END),0),
                        COALESCE(sum(CASE WHEN conta_debito  LIKE '4.1.1%%' THEN valor ELSE 0 END),0),
                        COALESCE(sum(CASE WHEN conta_debito  LIKE '4.1.2%%' THEN valor ELSE 0 END),0),
                        COALESCE(sum(CASE WHEN conta_debito  LIKE '4.1.3%%' THEN valor ELSE 0 END),0),
                        COALESCE(sum(CASE WHEN conta_debito  LIKE '4%%' OR conta_debito LIKE '3.2%%'
                                          THEN valor ELSE 0 END),0),
                        count(*)
                    FROM accounting_entries
                    WHERE status='confirmado' AND empresa_id=%s::uuid
                      AND periodo_competencia = ANY(%s)
                    """,
                    (empresa_id, meses),
                )
                r = cur.fetchone()
        finally:
            conn.close()

        receita = Decimal(str(r[0]))
        deducoes = Decimal(str(r[1]))
        pessoal = Decimal(str(r[2]))
        encargos = Decimal(str(r[3]))
        cogs = Decimal(str(r[4]))
        despesas = Decimal(str(r[5]))
        n_lanc = r[6]

        receita_liquida = receita - deducoes
        lucro = receita_liquida - despesas  # lucro antes do IRPJ/CSLL (resultado do razão)

        n_meses = len(meses)
        limite = LIMITE_ADICIONAL_MES * n_meses

        if lucro > 0:
            irpj = lucro * IRPJ
            excedente = max(Decimal("0"), lucro - limite)
            irpj_adicional = excedente * IRPJ_ADICIONAL
            csll = lucro * CSLL
            prejuizo_fiscal = Decimal("0")
        else:
            irpj = irpj_adicional = csll = Decimal("0")
            prejuizo_fiscal = -lucro

        total = irpj + irpj_adicional + csll

        return {
            "periodo": rotulo,
            "ano": ano,
            "trimestre": trimestre,
            "meses": meses,
            "empresa_id": empresa_id,
            "base": {
                "receita_bruta": _q(receita),
                "deducoes_iss": _q(deducoes),
                "receita_liquida": _q(receita_liquida),
                "despesa_pessoal": _q(pessoal),
                "despesa_encargos": _q(encargos),
                "custo_materiais_cogs": _q(cogs),
                "despesas_dedutiveis_total": _q(despesas),
                "lucro_antes_ircsll": _q(lucro),
            },
            "apuracao": {
                "irpj_15": _q(irpj),
                "irpj_adicional_10": _q(irpj_adicional),
                "limite_adicional": _q(limite),
                "csll_9": _q(csll),
                "total_irpj_csll": _q(total),
                "carga_sobre_receita_pct": _q((total / receita * 100) if receita > 0 else Decimal("0")),
            },
            "prejuizo_fiscal_compensavel": _q(prejuizo_fiscal),
            "metodo": "lucro_real_razao",
            "base_lancamentos": n_lanc,
            "observacao": (
                "Base = lucro do razão (accounting_entries): receita SÓ de NFS-e; folha completa nos 3 "
                "meses (jan/fev reconstruídas por âncora da folha de março + confirmação via PIX real do "
                "Inter, salário CLT estável); salários pagos não duplicam a folha; fornecedores em "
                "Serviços de Terceiros. IRPJ 15% + adicional 10% sobre o que exceder R$20k/mês; CSLL 9%. "
                "Ressalvas: (1) faltam as NFS-e emitidas de março (bloqueadas na API da prefeitura) — "
                "quando entrarem, a receita e o lucro sobem; (2) adições/exclusões do LALUR são do "
                "contador; (3) PIS/COFINS apurados à parte."
            ),
        }
