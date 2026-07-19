"""CollectionNegotiatorAgent — Analisa inadimplentes e gera estrategias de cobranca.

Skills injetadas (T3 Fase 2):
- gestao-inadimplencia (Skill 08) via SkillLoader
- 10 clientes reais Manaus com CNPJ das NFS-e março/2026
- Régua: D+1 WhatsApp → D+16 Carta → D+31 Negativação → D+61 Jurídico
- Chave PIX Conecta Mais embutida no system prompt
"""

from datetime import date

from sqlalchemy import and_, select

from modules.financial.agents.base_agent import BaseAgent
from modules.financial.agents.skill_loader import SkillLoader
from modules.financial.models.customer import Customer
from modules.financial.models.receivable_account import ReceivableAccount, ReceivableStatus

# Classificacao por faixa de atraso
_NIVEIS = [
    (1, 5, "lembrete", "alta", "WhatsApp/Email"),
    (6, 15, "contato_ativo", "alta", "Telefone/WhatsApp"),
    (16, 30, "notificacao_formal", "urgente", "Email formal/Carta"),
    (31, 60, "negativacao_iminente", "urgente", "Carta registrada/Email"),
    (61, 99999, "juridico", "urgente", "Advogado/Cartorio"),
]

_MENSAGENS = {
    "lembrete": (
        "Prezado(a) {nome}, verificamos que a fatura de R$ {valor:.2f} "
        "com vencimento em {vencimento} ainda nao foi quitada. "
        "Por favor, efetue o pagamento para evitar juros e multas."
    ),
    "contato_ativo": (
        "Prezado(a) {nome}, sua divida de R$ {valor:.2f} encontra-se "
        "{dias} dias em atraso. Entre em contato conosco para regularizar "
        "sua situacao e evitar restricoes no seu cadastro."
    ),
    "notificacao_formal": (
        "NOTIFICACAO FORMAL — {nome}: Informamos que o debito de R$ {valor:.2f} "
        "esta em atraso ha {dias} dias. Solicite sua segunda via e regularize "
        "ate o prazo estabelecido para evitar negativacao."
    ),
    "negativacao_iminente": (
        "AVISO DE NEGATIVACAO — {nome}: O valor de R$ {valor:.2f} em atraso "
        "ha {dias} dias sera encaminhado para protesto e negativacao nos "
        "orgaos de credito caso nao seja regularizado em 5 dias uteis."
    ),
    "juridico": (
        "COBRANCA JUDICIAL — {nome}: O debito de R$ {valor:.2f} com "
        "{dias} dias de atraso foi encaminhado ao setor juridico. "
        "Entre em contato imediatamente para evitar acao judicial."
    ),
}

# Taxa de recuperacao estimada por nivel (percentual)
_TAXA_RECUPERACAO = {
    "lembrete": 85.0,
    "contato_ativo": 65.0,
    "notificacao_formal": 45.0,
    "negativacao_iminente": 25.0,
    "juridico": 10.0,
}


def _classificar(dias: int) -> tuple[str, str, str]:
    """Retorna (nivel, prioridade, canal) para os dias de atraso."""
    for inicio, fim, nivel, prioridade, canal in _NIVEIS:
        if inicio <= dias <= fim:
            return nivel, prioridade, canal
    return "juridico", "urgente", "Advogado/Cartorio"


class CollectionNegotiatorAgent(BaseAgent):
    """Agente de negociacao e cobranca de inadimplentes."""

    name = "collection_negotiator"

    def _load_skills(self) -> str:
        """Carrega skill de gestão de inadimplência."""
        return SkillLoader.load("gestao-inadimplencia")

    def _get_enriched_system_prompt(self, base_prompt: str = "") -> str:
        """System prompt com régua de cobrança real Conecta Mais."""
        skill = self._load_skills()
        return (
            "Você é o CollectionNegotiatorAgent do GRUPO CONECTA MAIS.\n\n"
            "CONTEXTO DE COBRANÇA (Multi-CNPJ — a empresa CREDORA depende do contrato do condomínio):\n"
            "- Condomínios residenciais em Manaus/AM; síndicos eleitos ou profissionais\n"
            "- Contratos anuais com renovação automática\n"
            "- Tom: profissional e parceiro (nunca agressivo antes do D+30)\n"
            "- DADOS DE PAGAMENTO POR EMPRESA CREDORA (use o da empresa do contrato!):\n"
            "  · CONECTA MAIS ELETRÔNICA (contratos: Gelain, Parise Village, Green Hills):\n"
            "    PIX CNPJ 35.710.481/0001-03 | Banco Inter 077 | Conta 370990072-2\n"
            "  · CONECTA MAIS PATRIMONIAL (contratos: Ideal Flores, Laranjeiras, Mirante,\n"
            "    Prime Arena, Villa dos Pássaros, Villa Dei Fiori, Michelangelo):\n"
            "    PIX CNPJ 66.014.833/0001-10 | Banco Cora 403 | Ag 0001 Conta 7382527-7\n"
            "  · NUNCA envie dados de uma empresa para cobrança da outra.\n"
            "- Recebimentos da Patrimonial chegam LÍQUIDOS de INSS 11% retido na fonte "
            "(cessão de mão de obra) — ao conferir 'quanto falta', compare com o líquido.\n\n"
            f"SKILL DE COBRANÇA:\n{skill}\n\n"
            f"{base_prompt}\n\n"
            "Para cada cliente inadimplente retorne:\n"
            "- Valor vencido, dias atraso, prioridade (1-3)\n"
            "- Canal recomendado, script personalizado\n"
            "- Proposta de negociação se valor > R$10k"
        )

    async def analisar(self) -> dict:
        """Executa analise completa de inadimplentes."""
        return await self.execute()

    async def analyze_receivable(self, receivable_id: str) -> dict:
        """Analisa uma conta a receber especifica e retorna a acao de cobranca."""
        try:
            today = date.today()
            q = select(
                ReceivableAccount.id,
                ReceivableAccount.description,
                ReceivableAccount.net_value,
                ReceivableAccount.paid_value,
                ReceivableAccount.remaining_value,
                ReceivableAccount.due_date,
                ReceivableAccount.status,
                ReceivableAccount.customer_id,
                ReceivableAccount.customer_name.label("account_customer_name"),
                ReceivableAccount.collection_attempts,
            ).where(ReceivableAccount.id == receivable_id)
            row = (await self.session.execute(q)).first()
            if not row:
                return {"error": "Conta nao encontrada"}

            dias = (today - row.due_date).days if row.due_date < today else 0
            nivel, prioridade, canal = _classificar(dias)

            # Valor em atraso = saldo restante (desconta parciais).
            if row.remaining_value is not None:
                valor = float(row.remaining_value)
            else:
                valor = float((row.net_value or 0) - (row.paid_value or 0))

            # Nome do devedor: CRM, depois nome denormalizado na conta,
            # e por fim a descricao do servico.
            customer_name = row.account_customer_name or row.description or "Cliente"
            if row.customer_id:
                cq = select(Customer.name).where(Customer.id == row.customer_id)
                cname = (await self.session.execute(cq)).scalar_one_or_none()
                if cname:
                    customer_name = cname

            mensagem = _MENSAGENS[nivel].format(
                nome=customer_name,
                valor=valor,
                vencimento=row.due_date.strftime("%d/%m/%Y") if row.due_date else "-",
                dias=dias,
            )

            return {
                "id": str(row.id),
                "customer_name": customer_name,
                "valor": valor,
                "dias_atraso": dias,
                "nivel": nivel,
                "acao": nivel.replace("_", " ").title(),
                "mensagem": mensagem,
                "canal": canal,
                "prioridade": prioridade,
                "tentativas_anteriores": row.collection_attempts or 0,
                "taxa_recuperacao_estimada": _TAXA_RECUPERACAO.get(nivel, 10.0),
            }
        except Exception as exc:
            self.logger.warning(f"[{self.name}] Erro ao analisar receivable {receivable_id}: {exc}")
            return {"error": str(exc)}

    async def _execute(self, **kwargs) -> dict:
        today = date.today()

        # Busca todas as contas em atraso com dados do cliente
        q = (
            select(
                ReceivableAccount.id,
                ReceivableAccount.description,
                ReceivableAccount.net_value,
                ReceivableAccount.paid_value,
                ReceivableAccount.remaining_value,
                ReceivableAccount.due_date,
                ReceivableAccount.customer_id,
                ReceivableAccount.collection_attempts,
                ReceivableAccount.customer_name.label("account_customer_name"),
                Customer.name.label("crm_customer_name"),
            )
            .outerjoin(Customer, ReceivableAccount.customer_id == Customer.id)
            .where(
                and_(
                    ReceivableAccount.due_date < today,
                    ReceivableAccount.status.notin_(
                        [
                            ReceivableStatus.PAGA.value,
                            ReceivableStatus.CANCELADA.value,
                            ReceivableStatus.BAIXADA.value,
                        ]
                    ),
                )
            )
            .order_by(ReceivableAccount.due_date.asc())
        )
        rows = (await self.session.execute(q)).all()

        acoes: list[dict] = []
        total_em_atraso = 0.0
        taxa_ponderada = 0.0

        for row in rows:
            dias = (today - row.due_date).days
            # Valor em atraso = saldo restante (desconta o que ja foi pago em
            # contas parciais). remaining_value pode ser NULL nas contas totalmente
            # pendentes, entao cai para net_value - paid_value e por fim net_value.
            if row.remaining_value is not None:
                valor = float(row.remaining_value)
            else:
                valor = float((row.net_value or 0) - (row.paid_value or 0))
            total_em_atraso += valor

            nivel, prioridade, canal = _classificar(dias)
            # Nome do devedor: prioriza o cliente do CRM, depois o nome
            # denormalizado na propria conta (NFS-e sem vinculo ao CRM),
            # e so entao a descricao do servico como ultimo recurso.
            customer_name = (
                row.crm_customer_name
                or row.account_customer_name
                or row.description
                or "Cliente nao identificado"
            )

            mensagem = _MENSAGENS[nivel].format(
                nome=customer_name,
                valor=valor,
                vencimento=row.due_date.strftime("%d/%m/%Y"),
                dias=dias,
            )

            taxa = _TAXA_RECUPERACAO.get(nivel, 10.0)
            taxa_ponderada += taxa * valor

            acoes.append(
                {
                    "id": str(row.id),
                    "customer_name": customer_name,
                    "valor": round(valor, 2),
                    "dias_atraso": dias,
                    "nivel": nivel,
                    "acao": nivel.replace("_", " ").title(),
                    "mensagem": mensagem,
                    "canal": canal,
                    "prioridade": prioridade,
                    "tentativas_anteriores": row.collection_attempts or 0,
                }
            )

        # Ordena por prioridade: urgente primeiro, depois alta
        _ordem_prioridade = {"urgente": 0, "alta": 1, "media": 2, "baixa": 3}
        acoes.sort(key=lambda x: (_ordem_prioridade.get(x["prioridade"], 9), -x["valor"]))

        taxa_recuperacao_estimada = round(taxa_ponderada / total_em_atraso, 2) if total_em_atraso > 0 else 0.0

        return {
            "acoes": acoes,
            "total_em_atraso": round(total_em_atraso, 2),
            "qtd_inadimplentes": len(acoes),
            "taxa_recuperacao_estimada": taxa_recuperacao_estimada,
        }

    async def _fallback(self, **kwargs) -> dict:
        """Retorna estrutura vazia em caso de falha."""
        return {
            "acoes": [],
            "total_em_atraso": 0.0,
            "qtd_inadimplentes": 0,
            "taxa_recuperacao_estimada": 0.0,
        }
