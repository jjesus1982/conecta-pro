"""
Service para EFD-Reinf.

Camada de serviço para operações de EFD-Reinf.
"""

import logging
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ..core.certificate_manager import CertificateManager
from ..core.empresa_context import get_empresa_fiscal
from ..core.efd_reinf import (
    NATUREZAS_RENDIMENTO,
    ClassificacaoTributaria,
    EFDReinfManager,
    IndRetificacao,
    InfoContribuinte,
    PagamentoBeneficiarioPF,
    PagamentoBeneficiarioPJ,
    RetencaoServico,
    TipoAmbiente,
)

logger = logging.getLogger(__name__)


class EFDReinfService:
    """Service para operações EFD-Reinf."""

    def __init__(self):
        """Inicializa o service com a identificação REAL da empresa (tabela empresas)."""
        empresa = get_empresa_fiscal()
        self.cnpj = empresa.cnpj
        self.razao_social = empresa.razao_social
        self.ambiente_str = os.getenv("EFD_REINF_ENVIRONMENT", "producao_restrita")
        self.cert_path = os.getenv("CERTIFICATE_PATH", "")
        self.cert_password = os.getenv("CERTIFICATE_PASSWORD", "")

        self.ambiente = TipoAmbiente.PRODUCAO if self.ambiente_str == "producao" else TipoAmbiente.PRODUCAO_RESTRITA

        # Certificado é opcional
        self.cert_manager = None
        if self.cert_path and os.path.exists(self.cert_path):
            try:
                self.cert_manager = CertificateManager(pfx_path=self.cert_path, password=self.cert_password)
                logger.info("Certificado digital carregado para EFD-Reinf")
            except Exception as e:
                logger.warning(f"Certificado não carregado: {e}")

        self.manager = EFDReinfManager(
            certificate_manager=self.cert_manager,
            ambiente=self.ambiente,
            cnpj=self.cnpj,
        )

        logger.info(f"EFD-Reinf Service inicializado - Ambiente: {self.ambiente_str}, CNPJ: {self.cnpj}")

    def gerar_r1000(
        self,
        razao_social: str,
        classificacao_tributaria: str,
        inicio_validade: str,
        fim_validade: str | None = None,
        natureza_juridica: str | None = None,
        ind_coop: str = "0",
        ind_constr: str = "0",
        ind_desoneracao: str = "0",
        telefone: str | None = None,
        email: str | None = None,
        retificacao: bool = False,
    ) -> dict[str, Any]:
        """
        Gera evento R-1000 - Informações do Contribuinte.

        Args:
            razao_social: Razão social do contribuinte
            classificacao_tributaria: Código da classificação tributária
            inicio_validade: Início da validade (YYYY-MM)
            fim_validade: Fim da validade (YYYY-MM) - opcional
            natureza_juridica: Código da natureza jurídica
            ind_coop: Indicador de cooperativa (0=Não)
            ind_constr: Indicador de construtora (0=Não)
            ind_desoneracao: Indicador de desoneração (0=Não)
            telefone: Telefone de contato
            email: Email de contato
            retificacao: Se é retificação

        Returns:
            Dict com resultado da geração
        """
        try:
            # Mapeia classificação tributária
            class_trib = ClassificacaoTributaria(classificacao_tributaria)
        except ValueError:
            class_trib = ClassificacaoTributaria.EMPRESA_SIMPLES

        info = InfoContribuinte(
            cnpj=self.cnpj,
            razao_social=razao_social,
            classificacao_tributaria=class_trib,
            inicio_validade=inicio_validade,
            fim_validade=fim_validade,
            natureza_juridica=natureza_juridica,
            ind_coop=ind_coop,
            ind_constr=ind_constr,
            ind_desoneracao=ind_desoneracao,
            telefone=telefone,
            email=email,
        )

        ind_ret = IndRetificacao.RETIFICADOR if retificacao else IndRetificacao.ORIGINAL

        xml = self.manager.gerar_r1000(info, ind_ret)

        logger.info(f"Evento R-1000 gerado para CNPJ {self.cnpj}")

        return {
            "evento": "R-1000",
            "descricao": "Informações do Contribuinte",
            "xml": xml,
            "cnpj": self.cnpj,
            "inicio_validade": inicio_validade,
            "classificacao_tributaria": classificacao_tributaria,
            "ambiente": self.ambiente.value,
            "status": "gerado",
        }

    def gerar_r2010(
        self,
        periodo_apuracao: str,
        retencoes: list[dict[str, Any]],
        retificacao: bool = False,
    ) -> dict[str, Any]:
        """
        Gera evento R-2010 - Retenção Contribuição Previdenciária - Serviços Tomados.

        Args:
            periodo_apuracao: Período (YYYY-MM)
            retencoes: Lista de retenções com dados das NFs
            retificacao: Se é retificação

        Returns:
            Dict com resultado da geração
        """
        lista_retencoes = []
        valor_total_bruto = Decimal("0")
        valor_total_retencao = Decimal("0")

        for ret in retencoes:
            retencao = RetencaoServico(
                cnpj_prestador=ret["cnpj_prestador"],
                valor_bruto=Decimal(str(ret["valor_bruto"])),
                valor_base_retencao=Decimal(str(ret.get("valor_base_retencao") or ret["valor_bruto"])),
                valor_retencao=Decimal(str(ret["valor_retencao"])),
                valor_retencao_adicional=Decimal(str(ret.get("valor_retencao_adicional", "0"))),
                valor_nf_retido=Decimal(str(ret.get("valor_nf_retido", "0"))),
                serie_nf=ret.get("serie_nf", "1"),
                numero_nf=ret.get("numero_nf", ""),
                data_emissao_nf=(
                    datetime.strptime(ret["data_emissao_nf"], "%Y-%m-%d").date() if ret.get("data_emissao_nf") else None
                ),
                codigo_servico=ret.get("codigo_servico", "100000001"),
                ind_cprb=ret.get("ind_cprb", "0"),
            )
            lista_retencoes.append(retencao)
            valor_total_bruto += retencao.valor_bruto
            valor_total_retencao += retencao.valor_retencao

        ind_ret = IndRetificacao.RETIFICADOR if retificacao else IndRetificacao.ORIGINAL

        xml = self.manager.gerar_r2010(periodo_apuracao, lista_retencoes, ind_ret)

        logger.info(f"Evento R-2010 gerado: {len(lista_retencoes)} retenções, período {periodo_apuracao}")

        return {
            "evento": "R-2010",
            "descricao": "Retenção Contribuição Previdenciária - Serviços Tomados",
            "xml": xml,
            "cnpj": self.cnpj,
            "periodo_apuracao": periodo_apuracao,
            "quantidade_retencoes": len(lista_retencoes),
            "valor_total_bruto": str(valor_total_bruto),
            "valor_total_retencao": str(valor_total_retencao),
            "ambiente": self.ambiente.value,
            "status": "gerado",
        }

    def gerar_r4010(
        self,
        periodo_apuracao: str,
        pagamentos: list[dict[str, Any]],
        retificacao: bool = False,
    ) -> dict[str, Any]:
        """
        Gera evento R-4010 - Pagamentos a Beneficiário Pessoa Física.

        Args:
            periodo_apuracao: Período (YYYY-MM)
            pagamentos: Lista de pagamentos a PF
            retificacao: Se é retificação

        Returns:
            Dict com resultado da geração
        """
        lista_pagamentos = []
        valor_total_bruto = Decimal("0")
        valor_total_irrf = Decimal("0")

        for pag in pagamentos:
            pagamento = PagamentoBeneficiarioPF(
                cpf_beneficiario=pag["cpf_beneficiario"].replace(".", "").replace("-", ""),
                nome_beneficiario=pag["nome_beneficiario"],
                natureza_rendimento=pag["natureza_rendimento"],
                valor_bruto=Decimal(str(pag["valor_bruto"])),
                valor_irrf=Decimal(str(pag.get("valor_irrf", "0"))),
                valor_inss=Decimal(str(pag.get("valor_inss", "0"))),
                data_pagamento=(
                    datetime.strptime(pag["data_pagamento"], "%Y-%m-%d").date()
                    if pag.get("data_pagamento")
                    else date.today()
                ),
                descricao=pag.get("descricao"),
            )
            lista_pagamentos.append(pagamento)
            valor_total_bruto += pagamento.valor_bruto
            valor_total_irrf += pagamento.valor_irrf

        ind_ret = IndRetificacao.RETIFICADOR if retificacao else IndRetificacao.ORIGINAL

        xml = self.manager.gerar_r4010(periodo_apuracao, lista_pagamentos, ind_ret)

        logger.info(f"Evento R-4010 gerado: {len(lista_pagamentos)} pagamentos PF, período {periodo_apuracao}")

        return {
            "evento": "R-4010",
            "descricao": "Pagamentos/créditos a beneficiário pessoa física",
            "xml": xml,
            "cnpj": self.cnpj,
            "periodo_apuracao": periodo_apuracao,
            "quantidade_pagamentos": len(lista_pagamentos),
            "valor_total_bruto": str(valor_total_bruto),
            "valor_total_irrf": str(valor_total_irrf),
            "ambiente": self.ambiente.value,
            "status": "gerado",
        }

    def gerar_r4020(
        self,
        periodo_apuracao: str,
        pagamentos: list[dict[str, Any]],
        retificacao: bool = False,
    ) -> dict[str, Any]:
        """
        Gera evento R-4020 - Pagamentos a Beneficiário Pessoa Jurídica.

        Args:
            periodo_apuracao: Período (YYYY-MM)
            pagamentos: Lista de pagamentos a PJ
            retificacao: Se é retificação

        Returns:
            Dict com resultado da geração
        """
        lista_pagamentos = []
        valor_total_bruto = Decimal("0")
        valor_total_retencoes = Decimal("0")

        for pag in pagamentos:
            pagamento = PagamentoBeneficiarioPJ(
                cnpj_beneficiario=pag["cnpj_beneficiario"].replace(".", "").replace("/", "").replace("-", ""),
                razao_social=pag["razao_social"],
                natureza_rendimento=pag["natureza_rendimento"],
                valor_bruto=Decimal(str(pag["valor_bruto"])),
                valor_irrf=Decimal(str(pag.get("valor_irrf", "0"))),
                valor_csll=Decimal(str(pag.get("valor_csll", "0"))),
                valor_cofins=Decimal(str(pag.get("valor_cofins", "0"))),
                valor_pis=Decimal(str(pag.get("valor_pis", "0"))),
                data_pagamento=(
                    datetime.strptime(pag["data_pagamento"], "%Y-%m-%d").date()
                    if pag.get("data_pagamento")
                    else date.today()
                ),
                numero_nf=pag.get("numero_nf"),
            )
            lista_pagamentos.append(pagamento)
            valor_total_bruto += pagamento.valor_bruto
            valor_total_retencoes += (
                pagamento.valor_irrf + pagamento.valor_csll + pagamento.valor_cofins + pagamento.valor_pis
            )

        ind_ret = IndRetificacao.RETIFICADOR if retificacao else IndRetificacao.ORIGINAL

        xml = self.manager.gerar_r4020(periodo_apuracao, lista_pagamentos, ind_ret)

        logger.info(f"Evento R-4020 gerado: {len(lista_pagamentos)} pagamentos PJ, período {periodo_apuracao}")

        return {
            "evento": "R-4020",
            "descricao": "Pagamentos/créditos a beneficiário pessoa jurídica",
            "xml": xml,
            "cnpj": self.cnpj,
            "periodo_apuracao": periodo_apuracao,
            "quantidade_pagamentos": len(lista_pagamentos),
            "valor_total_bruto": str(valor_total_bruto),
            "valor_total_retencoes": str(valor_total_retencoes),
            "ambiente": self.ambiente.value,
            "status": "gerado",
        }

    def gerar_r2099(
        self,
        periodo_apuracao: str,
        retificacao: bool = False,
    ) -> dict[str, Any]:
        """
        Gera evento R-2099 - Fechamento dos Eventos Periódicos.

        Args:
            periodo_apuracao: Período (YYYY-MM)
            retificacao: Se é retificação

        Returns:
            Dict com resultado da geração
        """
        ind_ret = IndRetificacao.RETIFICADOR if retificacao else IndRetificacao.ORIGINAL

        xml = self.manager.gerar_r2099(periodo_apuracao, ind_ret)

        logger.info(f"Evento R-2099 gerado: fechamento período {periodo_apuracao}")

        return {
            "evento": "R-2099",
            "descricao": "Fechamento dos Eventos Periódicos",
            "xml": xml,
            "cnpj": self.cnpj,
            "periodo_apuracao": periodo_apuracao,
            "ambiente": self.ambiente.value,
            "status": "gerado",
        }

    def enviar_lote(self, eventos_xml: list[str]) -> dict[str, Any]:
        """
        Envia lote de eventos para a Receita Federal.

        Args:
            eventos_xml: Lista de XMLs de eventos

        Returns:
            Dict com resultado do envio
        """
        resultado = self.manager.enviar_lote(eventos_xml)

        logger.info(f"Lote EFD-Reinf enviado: {len(eventos_xml)} eventos")

        return {
            "xml_envio": resultado["xml_envio"],
            "quantidade_eventos": resultado["quantidade_eventos"],
            "ambiente": self.ambiente.value,
            "status": resultado["status"],
            "mensagem": "Lote preparado para envio" if self.cert_manager else "Modo simulado (sem certificado)",
        }

    def transmitir_r1000_real(self) -> dict[str, Any]:
        """
        Transmite R-1000 de verdade para a Receita Federal via SOAP + mTLS.

        Mesmo padrao do eSocial S-1000 que foi aceito com recibo
        1.2.0000000000305333794.
        """
        import re as re_mod

        import requests as http_requests

        # 1. Gerar XML do R-1000
        info = InfoContribuinte(
            cnpj=self.cnpj,
            razao_social=self.razao_social,
            classificacao_tributaria=ClassificacaoTributaria.EMPRESA_GERAL,
            inicio_validade="2026-01",
            ind_desoneracao="0",
            telefone="9293485518",
            email="jjesus@conectamais.pro",
        )
        xml_evento = self.manager.gerar_r1000(info)
        logger.info("R-1000 XML gerado: %d chars", len(xml_evento))

        # 2. Montar lote
        resultado_lote = self.manager.enviar_lote([xml_evento])
        xml_envio = resultado_lote["xml_envio"]

        # 3. Verificar certificado
        if not self.cert_manager:
            return {
                "sucesso": False,
                "erro": "Certificado nao configurado. Defina CERTIFICATE_PATH no .env",
                "xml_gerado": xml_evento[:500],
                "ambiente": self.ambiente.value,
            }

        # 4. Obter arquivos PEM
        try:
            cert_path, key_path = self.cert_manager.get_certificate_for_request()
        except Exception as e:
            return {"sucesso": False, "erro": f"Certificado: {e}", "xml_gerado": xml_evento[:300]}

        # 5. Montar envelope SOAP
        soap_envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <ReceberLoteEventos xmlns="http://sped.fazenda.gov.br/">
      <loteEventos>{xml_envio}</loteEventos>
    </ReceberLoteEventos>
  </soap:Body>
</soap:Envelope>"""

        # 6. Transmitir via mTLS
        url = self.manager.url
        logger.info("Transmitindo R-1000 para %s", url)

        try:
            response = http_requests.post(
                url,
                data=soap_envelope.encode("utf-8"),
                headers={
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": "http://sped.fazenda.gov.br/ReceberLoteEventos",
                },
                cert=(cert_path, key_path),
                timeout=60,
                verify=True,
            )

            logger.info("Resposta Reinf: HTTP %d (%d bytes)", response.status_code, len(response.content))

            # 7. Parsear resposta
            resp_text = response.text
            protocolo = None
            recibo = None
            erros = []

            m = re_mod.search(r"<nrProtEnvioLote>([^<]+)</nrProtEnvioLote>", resp_text)
            if m:
                protocolo = m.group(1)
            m = re_mod.search(r"<nrRec>([^<]+)</nrRec>", resp_text)
            if m:
                recibo = m.group(1)

            erros_raw = re_mod.findall(
                r"<codigo>([^<]+)</codigo>.*?<descricao>([^<]+)</descricao>", resp_text, re_mod.DOTALL
            )
            erros = [{"codigo": c, "descricao": d} for c, d in erros_raw]

            sucesso = bool(protocolo or recibo) or response.status_code == 200

            return {
                "sucesso": sucesso,
                "http_status": response.status_code,
                "protocolo": protocolo,
                "recibo": recibo,
                "erros": erros,
                "ambiente": self.ambiente.value,
                "url": url,
                "xml_gerado": xml_evento[:500],
                "resposta_resumo": resp_text[:800],
            }

        except http_requests.exceptions.SSLError as e:
            return {"sucesso": False, "erro": f"SSL/mTLS: {e}", "url": url}
        except http_requests.exceptions.ConnectionError as e:
            return {"sucesso": False, "erro": f"Conexao: {e}", "url": url}
        except Exception as e:
            return {"sucesso": False, "erro": str(e), "url": url}
        finally:
            # Limpar temporarios
            for p in [cert_path, key_path]:
                if p and os.path.exists(p):
                    try:
                        os.unlink(p)
                    except Exception:
                        pass

    def listar_naturezas_rendimento(self) -> dict[str, Any]:
        """
        Lista as naturezas de rendimento disponíveis.

        Returns:
            Dict com lista de naturezas
        """
        pf = {k: v for k, v in NATUREZAS_RENDIMENTO.items() if k.startswith("10")}
        pj = {k: v for k, v in NATUREZAS_RENDIMENTO.items() if k.startswith("15")}

        return {
            "pessoa_fisica": [{"codigo": k, "descricao": v} for k, v in pf.items()],
            "pessoa_juridica": [{"codigo": k, "descricao": v} for k, v in pj.items()],
        }

    def listar_classificacoes_tributarias(self) -> dict[str, Any]:
        """
        Lista as classificações tributárias disponíveis.

        Returns:
            Dict com lista de classificações
        """
        descricoes = {
            "01": "Empresa em geral",
            "02": "Optante pelo Simples Nacional",
            "03": "Microempreendedor Individual (MEI)",
            "04": "Produtor Rural Pessoa Jurídica",
            "06": "Agroindústria",
            "07": "Produtor Rural Pessoa Física",
            "08": "Consórcio",
            "09": "Entidade Imune ou Isenta",
            "10": "Missão Diplomática",
            "11": "Órgão Público",
        }

        return {
            "classificacoes": [
                {"codigo": ct.value, "descricao": descricoes.get(ct.value, ct.name)} for ct in ClassificacaoTributaria
            ]
        }

    def validar_status(self) -> dict[str, Any]:
        """
        Valida status da configuração EFD-Reinf.

        Returns:
            Dict com status da configuração
        """
        return {
            "ambiente": self.ambiente_str,
            "url": self.manager.url,
            "cnpj": self.cnpj,
            "certificado_configurado": self.cert_manager is not None,
            "certificado_valido": (self.cert_manager._loaded if self.cert_manager else False),
            "versao_layout": self.manager.VERSAO,
            "eventos_disponiveis": [
                "R-1000 - Informações do Contribuinte",
                "R-2010 - Retenção CP Serviços Tomados",
                "R-4010 - Pagamentos PF",
                "R-4020 - Pagamentos PJ",
                "R-2099 - Fechamento Periódico",
            ],
        }


# Singleton
_efd_reinf_service: EFDReinfService | None = None


def get_efd_reinf_service() -> EFDReinfService:
    """Retorna instância singleton do service."""
    global _efd_reinf_service
    if _efd_reinf_service is None:
        _efd_reinf_service = EFDReinfService()
    return _efd_reinf_service
