"""Agentes Financeiro e Fiscal & Contábil."""
import sys
sys.path.insert(0, '/opt/conecta-pro/agents/core')
from base_agent import BaseAgent


# ─── FINANCEIRO ─────────────────────────────────

COND = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'


class AgenteDashboardFinanceiro(BaseAgent):
    MODULO = "financeiro"
    SUBMODULO = "dashboard"
    ENDPOINTS = [
        f'/api/v1/financial/bi/dashboard?condominio_id={COND}',
    ]
    CONHECE_BUGS = [
        {
            'descricao': 'BI Dashboard Session→'
                         'AsyncSession (0/11 endpoints)',
            'corrigido': True,
            'auto_corrigivel': False
        }
    ]

    def auditar(self):
        return {
            'receita': self.db_query(
                "SELECT SUM(gross_value) "
                "FROM receivable_accounts "
                "WHERE status='paga';").strip(),
            'inadimplencia': self.db_query(
                "SELECT SUM(gross_value) "
                "FROM receivable_accounts "
                "WHERE status='pendente' "
                "AND due_date < CURRENT_DATE;"
            ).strip()
        }


class AgenteContratos(BaseAgent):
    MODULO = "financeiro"
    SUBMODULO = "contratos"
    ENDPOINTS = [
        '/api/v1/financial/contracts',
    ]
    CONHECE_BUGS = []


class AgenteContasPagar(BaseAgent):
    MODULO = "financeiro"
    SUBMODULO = "contas_pagar"
    ENDPOINTS = [
        f'/api/v1/financial/payables?condominio_id={COND}',
        f'/api/v1/financial/payables/stats?condominio_id={COND}',
        f'/api/v1/financial/payables/overdue?condominio_id={COND}',
    ]
    CONHECE_BUGS = [
        {
            'descricao': 'condominio_id sem '
                         'fallback JWT → 422',
            'corrigido': True,
            'auto_corrigivel': False
        },
        {
            'descricao': 'N+1 em bulk_payment',
            'corrigido': True,
            'auto_corrigivel': False
        }
    ]

    def auditar(self):
        return {
            'total': self.db_query(
                "SELECT COUNT(*), SUM(gross_value) "
                "FROM payable_accounts;").strip()
        }


class AgenteContasReceber(BaseAgent):
    MODULO = "financeiro"
    SUBMODULO = "contas_receber"
    ENDPOINTS = [
        f'/api/v1/financial/receivables?condominio_id={COND}',
        f'/api/v1/financial/receivables/stats?condominio_id={COND}',
        f'/api/v1/financial/receivables/installments/pending?condominio_id={COND}',
    ]
    CONHECE_BUGS = [
        {
            'descricao': 'grace_days coluna '
                         'inexistente no banco',
            'corrigido': True,
            'auto_corrigivel': False
        },
        {
            'descricao': '/installments/pending '
                         'capturado por /{id}',
            'corrigido': True,
            'auto_corrigivel': False
        }
    ]

    def auditar(self):
        return {
            'total': self.db_query(
                "SELECT COUNT(*), SUM(gross_value) "
                "FROM receivable_accounts;").strip()
        }


class AgenteFluxoCaixa(BaseAgent):
    MODULO = "financeiro"
    SUBMODULO = "fluxo_caixa"
    ENDPOINTS = [
        f'/api/v1/financial/cashflow/dashboard?condominio_id={COND}',
    ]
    CONHECE_BUGS = []


class AgenteConciliacaoBancaria(BaseAgent):
    MODULO = "financeiro"
    SUBMODULO = "conciliacao_bancaria"
    ENDPOINTS = [
        f'/api/v1/financial/bank-accounts?condominio_id={COND}',
    ]
    CONHECE_BUGS = [
        {
            'descricao': 'list_with_filters '
                         'ausente no BankTransaction',
            'corrigido': True,
            'auto_corrigivel': False
        }
    ]

    def auditar(self):
        return {
            'transacoes': self.db_query(
                "SELECT COUNT(*) "
                "FROM bank_transactions;").strip()
        }


class AgenteBoletos(BaseAgent):
    MODULO = "financeiro"
    SUBMODULO = "boletos_cobr"
    ENDPOINTS = [
        f'/api/v1/financial/billing-rules?condominio_id={COND}',
    ]
    CONHECE_BUGS = []


class AgenteFornecedores(BaseAgent):
    MODULO = "financeiro"
    SUBMODULO = "fornecedores"
    ENDPOINTS = [
        f'/api/v1/financial/suppliers?condominio_id={COND}',
    ]
    CONHECE_BUGS = []


class AgenteContabilidade(BaseAgent):
    MODULO = "financeiro"
    SUBMODULO = "contabilidade"
    ENDPOINTS = [
        # 08/09/2026: o ledger fin_* (accounts/cost-centers/periods) foi apagado — sonda o que existe
        '/api/v1/financial/accounting/dre',
        '/api/v1/financial/relatorios/balancete-real',
        '/api/v1/financial/relatorios/tributos?ano=2026',
    ]
    CONHECE_BUGS = [
        {
            'descricao': 'current_user["key"] '
                         '→ current_user.key '
                         '(72 ocorrências)',
            'corrigido': True,
            'auto_corrigivel': False
        }
    ]


class AgenteFaturamento(BaseAgent):
    MODULO = "financeiro"
    SUBMODULO = "faturamento"
    ENDPOINTS = [
        f'/api/v1/financial/billing-rules?condominio_id={COND}',
    ]
    CONHECE_BUGS = []


class AgentePrecificacao(BaseAgent):
    MODULO = "financeiro"
    SUBMODULO = "precificacao"
    ENDPOINTS = [
        '/api/v1/financial/contracts',
    ]
    CONHECE_BUGS = []


class AgenteRelatoriosFinanceiros(BaseAgent):
    MODULO = "financeiro"
    SUBMODULO = "relatorios_fin"
    ENDPOINTS = [
        f'/api/v1/financial/relatorios/dre?condominio_id={COND}&ano=2026',
    ]
    CONHECE_BUGS = []


# ─── FISCAL & CONTÁBIL ───────────────────────────

class AgenteNFe(BaseAgent):
    MODULO = "fiscal_contabil"
    SUBMODULO = "nfe"
    ENDPOINTS = [
        '/api/v1/government/sefaz-am/status',
        '/api/v1/government/nfse-nacional/status',
    ]
    CONHECE_BUGS = [
        {
            'descricao': 'SEFAZ nfe/list ausente '
                         '— apenas POST emitir/consultar',
            'corrigido': False,
            'auto_corrigivel': False
        }
    ]


class AgenteNFSe(BaseAgent):
    MODULO = "fiscal_contabil"
    SUBMODULO = "nfse"
    ENDPOINTS = [
        '/api/v1/government/nfse-manaus/consultar/rps/1',
        '/api/v1/government/simples-nacional/status',
    ]
    CONHECE_BUGS = [
        {
            'descricao': 'nfse/list e nfse-manaus/list '
                         'ausentes (rotas 404)',
            'corrigido': False,
            'auto_corrigivel': False
        }
    ]


class AgenteCertidoes(BaseAgent):
    MODULO = "fiscal_contabil"
    SUBMODULO = "certidoes"
    ENDPOINTS = [
        '/api/v1/government/certificates/',
        '/api/v1/government/ecac/status',
    ]
    CONHECE_BUGS = [
        {
            'descricao': 'ecac/certidoes ausente '
                         '— usar ecac/status',
            'corrigido': False,
            'auto_corrigivel': False
        }
    ]


class AgenteESocialFiscal(BaseAgent):
    MODULO = "fiscal_contabil"
    SUBMODULO = "esocial_fiscal"
    ENDPOINTS = [
        '/api/v1/government/esocial/eventos',
        '/api/v1/government/esocial/eventos-suportados',
    ]
    CONHECE_BUGS = [
        {
            'descricao': 'esocial/eventos '
                         'sem auth (dados fiscais)',
            'corrigido': True,
            'auto_corrigivel': False
        },
        {
            'descricao': 'get_db_sync ImportError',
            'corrigido': True,
            'auto_corrigivel': False
        }
    ]


class AgenteSPED(BaseAgent):
    MODULO = "fiscal_contabil"
    SUBMODULO = "sped"
    ENDPOINTS = [
        '/api/v1/government/sped-fiscal/status',
        '/api/v1/government/sped-contabil/status',
    ]
    CONHECE_BUGS = []


class AgenteDCTFWeb(BaseAgent):
    MODULO = "fiscal_contabil"
    SUBMODULO = "dctfweb"
    ENDPOINTS = [
        '/api/v1/government/dctfweb/status',
    ]
    CONHECE_BUGS = []


class AgenteEFDReinf(BaseAgent):
    MODULO = "fiscal_contabil"
    SUBMODULO = "efd_reinf"
    ENDPOINTS = [
        '/api/v1/government/efd-reinf/status',
        '/api/v1/government/efd-reinf/classificacoes-tributarias',
    ]
    CONHECE_BUGS = [
        {
            'descricao': 'reinf/status e reinf/r1000 '
                         'ausentes — prefixo correto: efd-reinf',
            'corrigido': False,
            'auto_corrigivel': False
        }
    ]
