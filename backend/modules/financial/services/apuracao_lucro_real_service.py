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
    def apurar(self, ano: int, trimestre: int | None = None, empresa_id: str = EMPRESA_PRINCIPAL_ID) -> dict:
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
                # Plano de 13/08/2026 (plano_contas_caixa.saldo): receita 4.x, ISS 5.2.2.01,
                # salários 5.1.1.01, encargos 5.1.1.02, materiais 5.1.1.06, dedutíveis = 5.x − ISS.
                # Até 07/09/2026 lia '3.1.1' como receita — o capital social de R$ 500 mil.
                from modules.financial.services.plano_contas_caixa import FILTRO_RAZAO, saldo

                cur.execute(
                    f"""
                    SELECT
                        -{saldo("4", "%%")},
                        {saldo("5.2.2.01", "%%")},
                        {saldo("5.1.1.01", "%%")},
                        {saldo("5.1.1.02", "%%")},
                        {saldo("5.1.1.06", "%%")},
                        {saldo("5", "%%")} - {saldo("5.2.2.01", "%%")},
                        count(*)
                    FROM accounting_entries
                    WHERE {FILTRO_RAZAO} AND empresa_id=%s::uuid
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
            # Renomeado em 27/09/2026. Chamava-se `prejuizo_fiscal_compensavel` e as DUAS
            # palavras estavam erradas: não é FISCAL (sem a Parte A do LALUR, prejuízo fiscal
            # e prejuízo contábil são coisas diferentes por definição) e não é COMPENSÁVEL
            # (nada aqui aplica a trava de 30% do art. 15 da Lei 9.065/95 nem consulta estoque
            # nenhum — isto é a foto do período, não o saldo). Quem compensa é
            # `lalur_service.apurar_lucro_real`. Nenhuma linha do front lia a chave antiga;
            # o único leitor vivo era o card do redesign, alterado no mesmo commit.
            "prejuizo_contabil_do_periodo": _q(prejuizo_fiscal),
            "metodo": "lucro_real_razao",
            "base_lancamentos": n_lanc,
            "observacao": (
                "Base = lucro do razão (accounting_entries): receita SÓ de NFS-e; folha completa nos 3 "
                "meses (jan/fev reconstruídas por âncora da folha de março + confirmação via PIX real do "
                "Inter, salário CLT estável); salários pagos não duplicam a folha; fornecedores em "
                "Serviços de Terceiros. IRPJ 15% + adicional 10% sobre o que exceder R$20k/mês; CSLL 9%. "
                "Ressalvas: (1) faltam as NFS-e emitidas de março (bloqueadas na API da prefeitura) — "
                "quando entrarem, a receita e o lucro sobem; (2) adições/exclusões do LALUR são do "
                "contador e vivem em `lalur_service` — enquanto a Parte A não for decidida, este "
                "número é o lucro do RAZÃO, não a base tributável; (3) PIS/COFINS apurados à parte."
            ),
        }
