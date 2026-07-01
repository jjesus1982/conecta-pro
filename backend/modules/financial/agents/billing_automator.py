"""BillingAutomatorAgent — Automação do ciclo de faturamento."""

from datetime import date, timedelta

from sqlalchemy import and_, func, select

from modules.financial.agents.base_agent import BaseAgent
from modules.financial.models.receivable_account import ReceivableAccount, ReceivableStatus


class BillingAutomatorAgent(BaseAgent):
    """
    Agente de automação do ciclo de faturamento.
    Identifica contratos para faturar, calcula medições e automatiza emissão.
    """

    name = "billing_automator"

    async def _execute(self, **kwargs) -> dict:
        return await self.gerar_resumo_faturamento(date.today())

    async def _fallback(self, **kwargs) -> dict:
        today = date.today()
        return {
            "mes": today.strftime("%Y-%m"),
            "total_faturado": 0.0,
            "total_pendente": 0.0,
            "total_vencido": 0.0,
            "total_pago": 0.0,
            "qtd_faturas": 0,
            "qtd_clientes": 0,
            "ticket_medio": 0.0,
        }

    # ------------------------------------------------------------------
    # 1. Listar contratos pendentes de faturamento para um mês
    # ------------------------------------------------------------------

    async def listar_contratos_para_faturar(self, mes: date) -> list[dict]:
        """
        Retorna lista de clientes com contas a receber pendentes no mês indicado.
        """
        try:
            primeiro_dia = mes.replace(day=1)
            if mes.month == 12:
                ultimo_dia = mes.replace(day=31)
            else:
                ultimo_dia = mes.replace(month=mes.month + 1, day=1) - timedelta(days=1)

            q = (
                select(
                    ReceivableAccount.customer_id,
                    func.count(ReceivableAccount.id).label("qtd_titulos"),
                    func.sum(ReceivableAccount.net_value).label("valor_total"),
                    func.min(ReceivableAccount.due_date).label("vencimento_min"),
                    func.max(ReceivableAccount.due_date).label("vencimento_max"),
                    func.max(ReceivableAccount.status).label("status_exemplo"),
                )
                .where(
                    and_(
                        ReceivableAccount.due_date >= primeiro_dia,
                        ReceivableAccount.due_date <= ultimo_dia,
                        ReceivableAccount.status.notin_(
                            [
                                ReceivableStatus.PAGA.value,
                                ReceivableStatus.CANCELADA.value,
                            ]
                        ),
                        ReceivableAccount.ativo.is_(True),
                    )
                )
                .group_by(ReceivableAccount.customer_id)
                .order_by(func.sum(ReceivableAccount.net_value).desc())
            )

            rows = (await self.session.execute(q)).all()

            result = []
            for row in rows:
                venc_min = row.vencimento_min
                venc_max = row.vencimento_max
                venc_medio_delta = (
                    (venc_max - venc_min).days // 2 if venc_min and venc_max and venc_min != venc_max else 0
                )
                venc_medio = (venc_min + timedelta(days=venc_medio_delta)).isoformat() if venc_min else None

                result.append(
                    {
                        "customer_id": str(row.customer_id) if row.customer_id else None,
                        "customer_name": f"Cliente {str(row.customer_id)[:8]}" if row.customer_id else "Sem cliente",
                        "valor_total": round(float(row.valor_total or 0), 2),
                        "qtd_titulos": row.qtd_titulos or 0,
                        "vencimento_medio": venc_medio,
                        "status": row.status_exemplo or ReceivableStatus.PENDENTE.value,
                    }
                )

            return result

        except Exception as exc:
            self.logger.warning("[billing_automator] listar_contratos_para_faturar: %s", exc)
            return []

    # ------------------------------------------------------------------
    # 2. Calcular medição de um contrato por tipo de serviço
    # ------------------------------------------------------------------

    def calcular_medicao(
        self,
        contrato_descricao: str,
        tipo: str,
        periodo_dias: int,
    ) -> dict:
        """
        Calcula medição mensal estimada por tipo de serviço de portaria/serviços para condomínios.
        Retorna detalhamento de custos e valor total.
        """
        tipo_norm = tipo.lower().strip()
        periodo = max(1, periodo_dias)

        # Tabela de parâmetros padrão por tipo (valores de referência SP)
        params = {
            "portaria": {
                "custo_diario_posto": 350.0,
                "he_percentual": 0.08,
                "noturno_percentual": 0.12,
                "label": "Portaria / Serviços para Condomínios",
            },
            "limpeza": {
                "custo_diario_posto": 180.0,
                "he_percentual": 0.05,
                "noturno_percentual": 0.0,
                "label": "Limpeza e Conservação",
            },
            "jardinagem": {
                "custo_diario_posto": 120.0,
                "he_percentual": 0.02,
                "noturno_percentual": 0.0,
                "label": "Jardinagem",
            },
            "seguranca_eletronica": {
                "custo_diario_posto": 95.0,
                "he_percentual": 0.0,
                "noturno_percentual": 0.10,
                "label": "Segurança Eletrônica / Monitoramento",
            },
            "portaria_remota": {
                "custo_diario_posto": 75.0,
                "he_percentual": 0.0,
                "noturno_percentual": 0.08,
                "label": "Portaria Remota",
            },
        }

        params = params.get(tipo_norm, params["portaria"])
        valor_base = round(params["custo_diario_posto"] * periodo, 2)
        adicional_he = round(valor_base * params["he_percentual"], 2)
        adicional_noturno = round(valor_base * params["noturno_percentual"], 2)
        deducoes = 0.0
        valor_total = round(valor_base + adicional_he + adicional_noturno - deducoes, 2)

        return {
            "tipo": tipo_norm,
            "tipo_label": params["label"],
            "contrato_descricao": contrato_descricao,
            "periodo_dias": periodo,
            "valor_base": valor_base,
            "adicional_he": adicional_he,
            "adicional_noturno": adicional_noturno,
            "deducoes": deducoes,
            "valor_total": valor_total,
            "detalhamento": {
                "custo_diario": params["custo_diario_posto"],
                "he_percentual": round(params["he_percentual"] * 100, 1),
                "noturno_percentual": round(params["noturno_percentual"] * 100, 1),
            },
        }

    # ------------------------------------------------------------------
    # 3. Resumo de faturamento do mês
    # ------------------------------------------------------------------

    async def gerar_resumo_faturamento(self, mes: date) -> dict:
        """Retorna resumo de faturamento para o mês."""
        try:
            primeiro_dia = mes.replace(day=1)
            if mes.month == 12:
                ultimo_dia = mes.replace(day=31)
            else:
                ultimo_dia = mes.replace(month=mes.month + 1, day=1) - timedelta(days=1)

            today = date.today()

            # Total faturado (todas as contas do mês exceto canceladas)
            base_q = select(
                func.coalesce(func.sum(ReceivableAccount.net_value), 0).label("total"),
                func.coalesce(func.count(ReceivableAccount.id), 0).label("qtd"),
                func.coalesce(func.count(ReceivableAccount.id), 0).label("qtd_clientes"),
            ).where(
                and_(
                    ReceivableAccount.due_date >= primeiro_dia,
                    ReceivableAccount.due_date <= ultimo_dia,
                    ReceivableAccount.status != ReceivableStatus.CANCELADA.value,
                    ReceivableAccount.ativo.is_(True),
                )
            )
            base_row = (await self.session.execute(base_q)).one()
            total_faturado = float(base_row.total or 0)
            qtd_faturas = int(base_row.qtd or 0)
            qtd_clientes = int(base_row.qtd_clientes or 0)

            # Pago
            pago_q = select(func.coalesce(func.sum(ReceivableAccount.paid_value), 0)).where(
                and_(
                    ReceivableAccount.due_date >= primeiro_dia,
                    ReceivableAccount.due_date <= ultimo_dia,
                    ReceivableAccount.status == ReceivableStatus.PAGA.value,
                    ReceivableAccount.ativo.is_(True),
                )
            )
            total_pago = float((await self.session.execute(pago_q)).scalar_one() or 0)

            # Vencido (vencimento anterior a hoje, não pago)
            vencido_q = select(func.coalesce(func.sum(ReceivableAccount.net_value), 0)).where(
                and_(
                    ReceivableAccount.due_date >= primeiro_dia,
                    ReceivableAccount.due_date <= min(ultimo_dia, today - timedelta(days=7)),
                    ReceivableAccount.status.notin_(
                        [
                            ReceivableStatus.PAGA.value,
                            ReceivableStatus.CANCELADA.value,
                        ]
                    ),
                    ReceivableAccount.ativo.is_(True),
                )
            )
            total_vencido = float((await self.session.execute(vencido_q)).scalar_one() or 0)

            total_pendente = max(0.0, total_faturado - total_pago - total_vencido)
            ticket_medio = round(total_faturado / qtd_faturas, 2) if qtd_faturas > 0 else 0.0

            return {
                "mes": mes.strftime("%Y-%m"),
                "total_faturado": round(total_faturado, 2),
                "total_pendente": round(total_pendente, 2),
                "total_vencido": round(total_vencido, 2),
                "total_pago": round(total_pago, 2),
                "qtd_faturas": qtd_faturas,
                "qtd_clientes": qtd_clientes,
                "ticket_medio": ticket_medio,
            }

        except Exception as exc:
            self.logger.warning("[billing_automator] gerar_resumo_faturamento: %s", exc)
            return {
                "mes": mes.strftime("%Y-%m"),
                "total_faturado": 0.0,
                "total_pendente": 0.0,
                "total_vencido": 0.0,
                "total_pago": 0.0,
                "qtd_faturas": 0,
                "qtd_clientes": 0,
                "ticket_medio": 0.0,
            }

    # ------------------------------------------------------------------
    # 4. Preview de faturamento automático
    # ------------------------------------------------------------------

    async def executar_faturamento_preview(self, mes: date) -> dict:
        """
        Preview do que seria faturado automaticamente no mês indicado.
        Identifica contas pendentes de criação com base em recorrências.
        """
        try:
            contratos = await self.listar_contratos_para_faturar(mes)
            valor_estimado = sum(c["valor_total"] for c in contratos)
            observacoes = []

            if not contratos:
                observacoes.append("Nenhum contrato identificado para faturamento automático neste mês.")
            else:
                observacoes.append(f"{len(contratos)} clientes com faturas pendentes identificadas.")
                vencidos = [c for c in contratos if c["status"] == ReceivableStatus.VENCIDA.value]
                if vencidos:
                    observacoes.append(
                        f"{len(vencidos)} contrato(s) com títulos já vencidos — ação de cobrança recomendada."
                    )

            return {
                "contratos_a_faturar": contratos,
                "valor_estimado": round(valor_estimado, 2),
                "qtd_contratos": len(contratos),
                "observacoes": observacoes,
            }

        except Exception as exc:
            self.logger.warning("[billing_automator] executar_faturamento_preview: %s", exc)
            return {
                "contratos_a_faturar": [],
                "valor_estimado": 0.0,
                "qtd_contratos": 0,
                "observacoes": ["Erro ao gerar preview de faturamento."],
            }
