"""D6.2 — ConciliacaoService: concilia inter_transactions com folha de pagamento."""

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MATCH_FORTE_TOLERANCIA = Decimal("0.01")
MATCH_MEDIO_TOLERANCIA = Decimal("0.50")


class ConciliacaoService:
    """Concilia PIX/TED de débito em inter_transactions com pagamentos de salário.

    Critérios de match (§42.4: se ambíguo → em_conciliacao, não automatiza):
    1. CPF destinatário == employee.cpf E valor exato → FORTE
    2. CPF match E valor ±R$0.50 → MÉDIO
    3. Valor exato E descricao contém nome employee → FRACO
    4. Sem match → sem conciliação (não cria registro)
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def preparar_competencia(self, competencia: str) -> dict:
        """Cria registros inter_conciliacao_folha para todos os employees do mês.

        competencia: '2026-04'
        """
        mes, ano = int(competencia.split("-")[1]), int(competencia.split("-")[0])

        # Buscar payslips do mês
        rows = (
            (
                await self.db.execute(
                    text("""
                    SELECT e.id AS employee_id, e.nome, e.cpf,
                           p.net_salary AS valor_liquido
                    FROM employees e
                    JOIN hr_payslips p ON p.employee_id = e.id
                    WHERE p.reference_month = :mes AND p.reference_year = :ano
                      AND e.status = 'ativo'
                      AND p.net_salary > 0
                """),
                    {"mes": mes, "ano": ano},
                )
            )
            .mappings()
            .all()
        )

        criados = 0
        for r in rows:
            await self.db.execute(
                text("""
                    INSERT INTO inter_conciliacao_folha
                      (employee_id, competencia, valor_liquido, status)
                    VALUES (:eid, :comp, :valor, 'previsto')
                    ON CONFLICT DO NOTHING
                """),
                {"eid": str(r["employee_id"]), "comp": competencia, "valor": float(r["valor_liquido"])},
            )
            criados += 1

        await self.db.commit()
        logger.info("D6.2 preparar_competencia %s: %d registros criados", competencia, criados)
        return {"competencia": competencia, "criados": criados}

    async def conciliar_folha(self, competencia: str) -> dict[str, Any]:
        """Concilia transactions de débito do mês com folha.

        Para cada inter_transaction PIX/TED débito do mês, busca match em
        inter_conciliacao_folha. Atualiza status/data_paga/inter_transaction_id.
        """
        mes, ano = int(competencia.split("-")[1]), int(competencia.split("-")[0])

        # Pegar transactions débito do mês
        txs = (
            (
                await self.db.execute(
                    text("""
                    SELECT id, valor, descricao, data_lancamento,
                           detalhes_destinatario
                    FROM inter_transactions
                    WHERE tipo_operacao = 'D'
                      AND EXTRACT(MONTH FROM data_lancamento) = :mes
                      AND EXTRACT(YEAR FROM data_lancamento) = :ano
                      AND (tipo_transacao ILIKE '%PIX%' OR tipo_transacao ILIKE '%TED%'
                           OR tipo_transacao IS NULL)
                    ORDER BY data_lancamento
                """),
                    {"mes": mes, "ano": ano},
                )
            )
            .mappings()
            .all()
        )

        # Pegar todos employees com payslip do mês
        employees = (
            (
                await self.db.execute(
                    text("""
                    SELECT e.id, e.nome, e.cpf,
                           c.id AS conc_id, c.valor_liquido
                    FROM employees e
                    JOIN inter_conciliacao_folha c ON c.employee_id = e.id
                    WHERE c.competencia = :comp AND c.status = 'previsto'
                """),
                    {"comp": competencia},
                )
            )
            .mappings()
            .all()
        )

        matches_fortes = 0
        matches_medios = 0
        em_conciliacao = 0

        for tx in txs:
            tx_valor = Decimal(str(tx["valor"]))
            dest = tx.get("detalhes_destinatario") or {}
            dest_cpf = str(dest.get("cpf_cnpj") or dest.get("cpfCnpj") or dest.get("cpf") or "").replace(".", "").replace("-", "")  # a chave gravada pelo sync é cpf_cnpj (08/09/2026)

            matched_emp = None
            match_tipo = None

            for emp in employees:
                emp_cpf = (emp["cpf"] or "").replace(".", "").replace("-", "")
                emp_valor = Decimal(str(emp["valor_liquido"]))

                cpf_match = dest_cpf and emp_cpf and dest_cpf == emp_cpf
                valor_exato = abs(tx_valor - emp_valor) <= MATCH_FORTE_TOLERANCIA
                valor_proximo = abs(tx_valor - emp_valor) <= MATCH_MEDIO_TOLERANCIA
                nome_em_desc = emp["nome"] and emp["nome"].split()[0].lower() in (tx.get("descricao") or "").lower()

                if cpf_match and valor_exato:
                    matched_emp = emp
                    match_tipo = "forte"
                    break
                elif cpf_match and valor_proximo and matched_emp is None:
                    matched_emp = emp
                    match_tipo = "medio"
                elif valor_exato and nome_em_desc and matched_emp is None:
                    matched_emp = emp
                    match_tipo = "fraco"

            if matched_emp:
                # Verificar unicidade — se mais de 1 match, ambíguo
                outros = [
                    e
                    for e in employees
                    if e["conc_id"] != matched_emp["conc_id"]
                    and abs(Decimal(str(e["valor_liquido"])) - tx_valor) <= MATCH_MEDIO_TOLERANCIA
                ]
                status = "em_conciliacao" if outros else "pago"

                await self.db.execute(
                    text("""
                        UPDATE inter_conciliacao_folha
                        SET status = :status,
                            inter_transaction_id = :tx_id,
                            data_paga = :dp,
                            match_tipo = :mt,
                            updated_at = NOW()
                        WHERE id = :conc_id
                    """),
                    {
                        "status": status,
                        "tx_id": str(tx["id"]),
                        "dp": tx["data_lancamento"],
                        "mt": match_tipo,
                        "conc_id": str(matched_emp["conc_id"]),
                    },
                )
                if status == "pago":
                    if match_tipo == "forte":
                        matches_fortes += 1
                    else:
                        matches_medios += 1
                else:
                    em_conciliacao += 1

        await self.db.commit()
        logger.info(
            "D6.2 conciliar_folha %s: fortes=%d medios=%d em_conciliacao=%d",
            competencia,
            matches_fortes,
            matches_medios,
            em_conciliacao,
        )
        return {
            "competencia": competencia,
            "matches_fortes": matches_fortes,
            "matches_medios": matches_medios,
            "em_conciliacao": em_conciliacao,
            "total_txs_analisadas": len(txs),
        }

    async def listar_pagamentos(self, competencia: str) -> list[dict]:
        """Lista inter_conciliacao_folha para a competência."""
        rows = (
            (
                await self.db.execute(
                    text("""
                    SELECT c.id, c.competencia, c.status, c.match_tipo,
                           c.valor_liquido, c.data_prevista, c.data_paga,
                           e.nome, e.cpf
                    FROM inter_conciliacao_folha c
                    LEFT JOIN employees e ON e.id = c.employee_id
                    WHERE c.competencia = :comp
                    ORDER BY e.nome
                """),
                    {"comp": competencia},
                )
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]

    async def listar_divergencias(self) -> list[dict]:
        """Lista todos os registros em_conciliacao."""
        rows = (
            (
                await self.db.execute(
                    text("""
                    SELECT c.id, c.competencia, c.status, c.match_tipo,
                           c.valor_liquido, c.data_paga, c.observacoes,
                           e.nome, e.cpf,
                           t.valor AS tx_valor, t.descricao AS tx_descricao,
                           t.data_lancamento AS tx_data
                    FROM inter_conciliacao_folha c
                    LEFT JOIN employees e ON e.id = c.employee_id
                    LEFT JOIN inter_transactions t ON t.id = c.inter_transaction_id
                    WHERE c.status = 'em_conciliacao'
                    ORDER BY c.competencia DESC, e.nome
                """),
                )
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]
