"""
Service para DCTFWeb.

Camada de serviço para operações de DCTFWeb.
"""

import logging
import os
import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import psycopg2

from ..core.dctfweb import (
    DARF,
    CreditoVinculavel,
    DCTFWebDeclaracao,
    DCTFWebManager,
    DebitoContribuicao,
    TipoCredito,
    TipoDeclaracao,
)
from ..core.empresa_context import get_empresa_fiscal

logger = logging.getLogger(__name__)


class DCTFWebService:
    """Service para operações DCTFWeb."""

    def __init__(self):
        """Inicializa o service com a identificação REAL da empresa (tabela empresas)."""
        empresa = get_empresa_fiscal()
        self.cnpj = empresa.cnpj
        self.razao_social = empresa.razao_social
        self.ambiente = os.getenv("DCTFWEB_ENVIRONMENT", "producao")
        self._empresa_folha_periodos: dict[str, dict[str, Any]] = {}

        self.manager = DCTFWebManager(
            cnpj=self.cnpj,
            razao_social=self.razao_social,
            ambiente=self.ambiente,
        )

        logger.info(f"DCTFWeb Service inicializado - Ambiente: {self.ambiente}, CNPJ: {self.cnpj}")

    def criar_declaracao(
        self,
        periodo_apuracao: str,
        tipo: str = "1",
    ) -> dict[str, Any]:
        """
        Cria uma nova declaração DCTFWeb.

        Args:
            periodo_apuracao: Período (YYYY-MM)
            tipo: Tipo da declaração (1=Mensal, 2=Anual, 3=Diária, 4=Especial)

        Returns:
            Dict com dados da declaração criada
        """
        tipo_enum = TipoDeclaracao(tipo)

        declaracao = self.manager.criar_declaracao(
            periodo_apuracao=periodo_apuracao,
            tipo=tipo_enum,
        )

        logger.info(f"DCTFWeb criada: período {periodo_apuracao}, tipo {tipo}")

        return {
            "periodo_apuracao": declaracao.periodo_apuracao,
            "tipo": declaracao.tipo.value,
            "tipo_descricao": self._get_tipo_descricao(declaracao.tipo),
            "situacao": declaracao.situacao.value,
            "cnpj": declaracao.cnpj,
            "razao_social": declaracao.razao_social,
            "total_debitos": str(declaracao.total_debitos),
            "total_creditos": str(declaracao.total_creditos),
            "saldo_a_pagar": str(declaracao.saldo_a_pagar),
        }

    # -- Fonte real da folha (hr_payslips) para alimentar a DCTFWeb -----------

    @staticmethod
    def _db_url() -> str:
        return re.sub(r"\+asyncpg|\+psycopg2?", "", os.getenv("DATABASE_URL", ""))

    def carregar_folha_do_periodo(self, periodo_apuracao: str) -> dict[str, Any] | None:
        """
        Lê a folha REAL (hr_payslips) da competência e monta o dicionário de dados
        do eSocial esperado pelo manager (contribuição do segurado, patronal, RAT,
        terceiros). NUNCA fabrica: se a competência não tem holerite populado,
        retorna None (a tela deve exibir 'aguardando importação eSocial').

        Bases legais aplicadas sobre a base REAL de INSS da folha:
        - INSS descontado do segurado: soma real de inss_value dos holerites.
        - CP patronal (cód. 1138): 20% sobre a base de INSS da folha.
        - RAT/GILRAT (cód. 1171): 3% (grau de risco vigilância/portaria) — ajustável.
        - Terceiros/Sistema S (5,8%): distribuído nos códigos padrão.
        Se a base de INSS estiver zerada, retorna None (nada a declarar de verdade).
        """
        url = self._db_url()
        if not url:
            return None

        try:
            conn = psycopg2.connect(url)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            COUNT(*),
                            COALESCE(SUM(inss_value), 0),
                            COALESCE(SUM(inss_base), 0),
                            COALESCE(SUM(irrf_value), 0),
                            COALESCE(SUM(fgts_value), 0)
                        FROM hr_payslips
                        WHERE reference_period = %s
                          AND status <> 'cancelled'
                        """,
                        (periodo_apuracao,),
                    )
                    row = cur.fetchone()
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            logger.warning("DCTFWeb: falha ao ler hr_payslips de %s (%s)", periodo_apuracao, e)
            return None

        n, inss_seg, inss_base, irrf, fgts = row
        if not n or Decimal(str(inss_base)) <= 0:
            # Sem folha real populada nesta competência → nada a fabricar.
            return None

        inss_seg = Decimal(str(inss_seg))
        inss_base = Decimal(str(inss_base))
        fgts = Decimal(str(fgts))

        def _q(v: Decimal) -> float:
            return float(v.quantize(Decimal("0.01"), ROUND_HALF_UP))

        patronal = inss_base * Decimal("0.20")
        rat = inss_base * Decimal("0.03")
        terceiros_total = inss_base * Decimal("0.058")
        # distribuição usual do Sistema S para código de FPAS de vigilância/serviços
        terceiros = {
            "1184": _q(inss_base * Decimal("0.025")),  # Salário Educação 2,5%
            "1208": _q(inss_base * Decimal("0.015")),  # SEST 1,5%
            "1211": _q(inss_base * Decimal("0.010")),  # SENAT 1,0%
            "1187": _q(inss_base * Decimal("0.002")),  # INCRA 0,2%
            "1205": _q(inss_base * Decimal("0.001")),  # SENAR 0,1% (quando aplicável)
        }

        dados = {
            "contribuicao_segurado": _q(inss_seg),
            "contribuicao_patronal": _q(patronal),
            "rat": _q(rat),
            "terceiros": terceiros,
        }

        self._empresa_folha_periodos[periodo_apuracao] = {
            "fonte": "hr_payslips",
            "holerites": int(n),
            "inss_base": _q(inss_base),
            "inss_segurado": _q(inss_seg),
            "inss_patronal_20pct": _q(patronal),
            "rat_3pct": _q(rat),
            "terceiros_5_8pct": _q(terceiros_total),
            "fgts_informativo": _q(fgts),  # FGTS é guia própria (não DARF DCTFWeb)
        }
        logger.info(
            "DCTFWeb: folha real %s carregada de hr_payslips (%d holerites, base INSS %.2f)",
            periodo_apuracao,
            int(n),
            float(inss_base),
        )
        return dados

    def _dados_esocial_efetivos(
        self, periodo_apuracao: str, dados_esocial: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Usa os dados passados explicitamente; senão tenta a folha real."""
        if dados_esocial:
            return dados_esocial
        return self.carregar_folha_do_periodo(periodo_apuracao)

    def importar_esocial(
        self,
        periodo_apuracao: str,
        dados_esocial: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Cria declaração e importa dados do eSocial.

        Args:
            periodo_apuracao: Período (YYYY-MM)
            dados_esocial: Dados vindos do eSocial

        Returns:
            Dict com declaração atualizada
        """
        declaracao = self.manager.criar_declaracao(periodo_apuracao)
        declaracao = self.manager.importar_esocial(declaracao, dados_esocial)

        logger.info(
            f"Importado eSocial para DCTFWeb: {len(declaracao.debitos)} débitos, {len(declaracao.creditos)} créditos"
        )

        return self._declaracao_to_dict(declaracao)

    def importar_reinf(
        self,
        periodo_apuracao: str,
        dados_reinf: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Cria declaração e importa dados da EFD-Reinf.

        Args:
            periodo_apuracao: Período (YYYY-MM)
            dados_reinf: Dados vindos da EFD-Reinf

        Returns:
            Dict com declaração atualizada
        """
        declaracao = self.manager.criar_declaracao(periodo_apuracao)
        declaracao = self.manager.importar_reinf(declaracao, dados_reinf)

        logger.info(f"Importado EFD-Reinf para DCTFWeb: {len(declaracao.creditos)} créditos")

        return self._declaracao_to_dict(declaracao)

    def consolidar_declaracao(
        self,
        periodo_apuracao: str,
        dados_esocial: dict[str, Any] | None = None,
        dados_reinf: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Consolida declaração com dados do eSocial e EFD-Reinf.

        Args:
            periodo_apuracao: Período (YYYY-MM)
            dados_esocial: Dados do eSocial
            dados_reinf: Dados da EFD-Reinf

        Returns:
            Dict com declaração consolidada
        """
        declaracao = self.manager.criar_declaracao(periodo_apuracao)

        dados_esocial = self._dados_esocial_efetivos(periodo_apuracao, dados_esocial)
        if dados_esocial:
            declaracao = self.manager.importar_esocial(declaracao, dados_esocial)

        if dados_reinf:
            declaracao = self.manager.importar_reinf(declaracao, dados_reinf)

        logger.info(f"DCTFWeb consolidada: {len(declaracao.debitos)} débitos, {len(declaracao.creditos)} créditos")

        resultado = self._declaracao_to_dict(declaracao)
        resultado["veracidade"] = self._veracidade(periodo_apuracao, declaracao)
        return resultado

    def gerar_darfs(
        self,
        periodo_apuracao: str,
        dados_esocial: dict[str, Any] | None = None,
        dados_reinf: dict[str, Any] | None = None,
        data_vencimento: str | None = None,
    ) -> dict[str, Any]:
        """
        Gera DARFs para uma declaração.

        Args:
            periodo_apuracao: Período (YYYY-MM)
            dados_esocial: Dados do eSocial
            dados_reinf: Dados da EFD-Reinf
            data_vencimento: Data de vencimento (YYYY-MM-DD)

        Returns:
            Dict com DARFs gerados
        """
        declaracao = self.manager.criar_declaracao(periodo_apuracao)

        dados_esocial = self._dados_esocial_efetivos(periodo_apuracao, dados_esocial)
        if dados_esocial:
            declaracao = self.manager.importar_esocial(declaracao, dados_esocial)

        if dados_reinf:
            declaracao = self.manager.importar_reinf(declaracao, dados_reinf)

        dt_venc = None
        if data_vencimento:
            dt_venc = datetime.strptime(data_vencimento, "%Y-%m-%d").date()

        darfs = self.manager.gerar_darfs(declaracao, dt_venc)

        logger.info(f"Gerados {len(darfs)} DARFs para período {periodo_apuracao}")

        return {
            "periodo_apuracao": periodo_apuracao,
            "total_debitos": str(declaracao.total_debitos),
            "total_creditos": str(declaracao.total_creditos),
            "saldo_a_pagar": str(declaracao.saldo_a_pagar),
            "quantidade_darfs": len(darfs),
            "darfs": [self._darf_to_dict(d) for d in darfs],
            "veracidade": self._veracidade(periodo_apuracao, declaracao),
        }

    def transmitir(
        self,
        periodo_apuracao: str,
        dados_esocial: dict[str, Any] | None = None,
        dados_reinf: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Transmite declaração DCTFWeb.

        Args:
            periodo_apuracao: Período (YYYY-MM)
            dados_esocial: Dados do eSocial
            dados_reinf: Dados da EFD-Reinf

        Returns:
            Dict com resultado da transmissão
        """
        declaracao = self.manager.criar_declaracao(periodo_apuracao)

        dados_esocial = self._dados_esocial_efetivos(periodo_apuracao, dados_esocial)
        if dados_esocial:
            declaracao = self.manager.importar_esocial(declaracao, dados_esocial)

        if dados_reinf:
            declaracao = self.manager.importar_reinf(declaracao, dados_reinf)

        self.manager.gerar_darfs(declaracao)
        resultado = self.manager.transmitir(declaracao)
        resultado["veracidade"] = self._veracidade(periodo_apuracao, declaracao)

        logger.info(
            f"DCTFWeb {periodo_apuracao} apurada (saldo {resultado.get('saldo_a_pagar')}) "
            "— entrega via e-CAC pelo contador."
        )

        return resultado

    def consultar(self, periodo_apuracao: str) -> dict[str, Any]:
        """
        Consulta declaração por período.

        Consolida a folha REAL (hr_payslips) para mostrar o que já é apurável
        localmente. A consulta oficial (e-CAC) continua pendente de integração —
        rotulada honestamente, sem fingir apuração transmitida.

        Args:
            periodo_apuracao: Período (YYYY-MM)

        Returns:
            Dict com dados da declaração
        """
        base = self.manager.consultar(periodo_apuracao)
        dados_esocial = self.carregar_folha_do_periodo(periodo_apuracao)
        if dados_esocial:
            declaracao = self.manager.criar_declaracao(periodo_apuracao)
            declaracao = self.manager.importar_esocial(declaracao, dados_esocial)
            base["apuracao_local"] = {
                "total_debitos": str(declaracao.total_debitos),
                "saldo_a_pagar": str(declaracao.saldo_a_pagar),
                "debitos": [self._debito_to_dict(d) for d in declaracao.debitos],
            }
            base["veracidade"] = self._veracidade(periodo_apuracao, declaracao)
            base["mensagem"] = (
                "Apuração LOCAL a partir da folha real (hr_payslips). Consulta oficial "
                "via e-CAC ainda não integrada."
            )
        else:
            base["veracidade"] = self._veracidade(periodo_apuracao, None)
            base["mensagem"] = (
                "Sem folha (hr_payslips) populada nesta competência — aguardando importação "
                "eSocial. Consulta oficial via e-CAC ainda não integrada."
            )
        return base

    def _veracidade(self, periodo_apuracao: str, declaracao: DCTFWebDeclaracao | None) -> dict[str, Any]:
        """Bloco de honestidade: de onde vieram os números (ou por que estão vazios)."""
        folha = self._empresa_folha_periodos.get(periodo_apuracao)
        tem_debitos = bool(declaracao and declaracao.debitos)
        if folha and tem_debitos:
            status_v = "apurado_da_folha_real"
            obs = (
                "Débitos previdenciários apurados a partir da folha real (hr_payslips): "
                "INSS segurado da folha; patronal 20%, RAT/GILRAT 3% e Terceiros 5,8% sobre a "
                "base de INSS da competência. FGTS é guia própria (não entra em DARF DCTFWeb). "
                "Retenções de serviços (Reinf) e ajustes finais são do contador."
            )
        else:
            status_v = "aguardando_importacao_esocial"
            obs = (
                "Sem folha real (hr_payslips) desta competência — nada foi fabricado. "
                "Importe a folha/eSocial para apurar os débitos previdenciários reais."
            )
        return {
            "fonte": "hr_payslips" if folha else "sem_dados",
            "status": status_v,
            "folha": folha,
            "observacao": obs,
        }

    def listar_codigos_receita(self) -> dict[str, Any]:
        """
        Lista códigos de receita disponíveis.

        Returns:
            Dict com códigos de receita
        """
        return {"codigos": [{"codigo": k, "descricao": v} for k, v in self.manager.CODIGOS_RECEITA.items()]}

    def listar_tipos_declaracao(self) -> dict[str, Any]:
        """
        Lista tipos de declaração disponíveis.

        Returns:
            Dict com tipos de declaração
        """
        descricoes = {
            "1": "DCTFWeb Mensal",
            "2": "DCTFWeb 13º Salário (Anual)",
            "3": "DCTFWeb Diária (Espetáculos Desportivos)",
            "4": "DCTFWeb Especial",
        }

        return {"tipos": [{"codigo": t.value, "descricao": descricoes.get(t.value, t.name)} for t in TipoDeclaracao]}

    def listar_tipos_credito(self) -> dict[str, Any]:
        """
        Lista tipos de crédito vinculáveis.

        Returns:
            Dict com tipos de crédito
        """
        descricoes = {
            "1": "Salário-Família",
            "2": "Salário-Maternidade",
            "3": "Retenção Lei 9.711/98",
            "4": "Compensação",
            "5": "Suspensão",
            "6": "Parcelamento",
        }

        return {"tipos": [{"codigo": t.value, "descricao": descricoes.get(t.value, t.name)} for t in TipoCredito]}

    def validar_status(self) -> dict[str, Any]:
        """
        Valida status da configuração DCTFWeb.

        Returns:
            Dict com status
        """
        return {
            "ambiente": self.ambiente,
            "cnpj": self.cnpj,
            "razao_social": self.razao_social,
            "portal_ecac": "https://cav.receita.fazenda.gov.br/",
            "operacoes_disponiveis": [
                "Criar declaração",
                "Importar eSocial",
                "Importar EFD-Reinf",
                "Consolidar declaração",
                "Gerar DARFs",
                "Transmitir",
                "Consultar",
            ],
        }

    def _get_tipo_descricao(self, tipo: TipoDeclaracao) -> str:
        """Retorna descrição do tipo de declaração."""
        descricoes = {
            TipoDeclaracao.MENSAL: "DCTFWeb Mensal",
            TipoDeclaracao.ANUAL: "DCTFWeb 13º Salário",
            TipoDeclaracao.DIARIA: "DCTFWeb Diária",
            TipoDeclaracao.ESPECIAL: "DCTFWeb Especial",
        }
        return descricoes.get(tipo, tipo.name)

    def _declaracao_to_dict(self, declaracao: DCTFWebDeclaracao) -> dict[str, Any]:
        """Converte declaração para dict."""
        return {
            "numero_recibo": declaracao.numero_recibo,
            "tipo": declaracao.tipo.value,
            "tipo_descricao": self._get_tipo_descricao(declaracao.tipo),
            "situacao": declaracao.situacao.value,
            "periodo_apuracao": declaracao.periodo_apuracao,
            "data_transmissao": (declaracao.data_transmissao.isoformat() if declaracao.data_transmissao else None),
            "cnpj": declaracao.cnpj,
            "razao_social": declaracao.razao_social,
            "debitos": [self._debito_to_dict(d) for d in declaracao.debitos],
            "creditos": [self._credito_to_dict(c) for c in declaracao.creditos],
            "total_debitos": str(declaracao.total_debitos),
            "total_creditos": str(declaracao.total_creditos),
            "saldo_a_pagar": str(declaracao.saldo_a_pagar),
            "darfs": [self._darf_to_dict(d) for d in declaracao.darfs],
        }

    def _debito_to_dict(self, debito: DebitoContribuicao) -> dict[str, Any]:
        """Converte débito para dict."""
        return {
            "codigo_receita": debito.codigo_receita,
            "descricao": debito.descricao,
            "valor_principal": str(debito.valor_principal),
            "valor_acrescimos": str(debito.valor_acrescimos),
            "valor_total": str(debito.valor_total),
            "periodo_apuracao": debito.periodo_apuracao,
        }

    def _credito_to_dict(self, credito: CreditoVinculavel) -> dict[str, Any]:
        """Converte crédito para dict."""
        return {
            "tipo": credito.tipo.value,
            "descricao": credito.descricao,
            "valor": str(credito.valor),
            "periodo_apuracao": credito.periodo_apuracao,
            "numero_documento": credito.numero_documento,
        }

    def _darf_to_dict(self, darf: DARF) -> dict[str, Any]:
        """Converte DARF para dict."""
        return {
            "codigo_receita": darf.codigo_receita,
            "periodo_apuracao": darf.periodo_apuracao,
            "data_vencimento": darf.data_vencimento.isoformat(),
            "valor_principal": str(darf.valor_principal),
            "valor_multa": str(darf.valor_multa),
            "valor_juros": str(darf.valor_juros),
            "valor_total": str(darf.valor_total),
            "numero_referencia": darf.numero_referencia,
            "codigo_barras": darf.codigo_barras,
            "linha_digitavel": darf.linha_digitavel,
        }


# Singleton
_dctfweb_service: DCTFWebService | None = None


def get_dctfweb_service() -> DCTFWebService:
    """Retorna instância singleton do service."""
    global _dctfweb_service
    if _dctfweb_service is None:
        _dctfweb_service = DCTFWebService()
    return _dctfweb_service
