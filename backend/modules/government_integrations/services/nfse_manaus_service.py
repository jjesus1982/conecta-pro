"""
Service para NFS-e Manaus.

Integração completa com WebService da Prefeitura de Manaus.
Provider: Abaco/GIF
Padrão: ABRASF 2.04
"""

import logging
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from modules.government_integrations.core import (
    CertificateManager,
    NaturezaOperacao,
    NFSeManaus,
    NFSeManausManager,
    Servico,
    Tomador,
)

logger = logging.getLogger(__name__)


class NFSeManausService:
    """
    Service para operações de NFS-e com Prefeitura de Manaus.

    Funcionalidades:
    - Emissão de NFS-e (via RPS)
    - Consulta de NFS-e
    - Cancelamento de NFS-e
    - Substituição de NFS-e
    """

    def __init__(self):
        """Inicializa o service com configurações do ambiente."""
        self._manager: NFSeManausManager | None = None
        self._cert_manager: CertificateManager | None = None

        # Configurações do ambiente
        self.cnpj = os.getenv("NFSE_MANAUS_CNPJ", "35710481000103")
        self.usuario = os.getenv("NFSE_MANAUS_USUARIO", self.cnpj)
        self.senha = os.getenv("NFSE_MANAUS_SENHA", "")
        self.ambiente = os.getenv("NFSE_MANAUS_ENVIRONMENT", "homologacao")
        self.inscricao_municipal = os.getenv("NFSE_MANAUS_IM", "")

        # Certificado digital
        self.cert_path = os.getenv("CERTIFICATE_PATH", "/opt/conecta-pro/credentials/certificates/certificado.pfx")
        self.cert_password = os.getenv("CERTIFICATE_PASSWORD", "")

    def _get_manager(self) -> NFSeManausManager:
        """Obtém instância do manager, inicializando se necessário."""
        if self._manager is None:
            # Inicializar certificado se disponível
            if os.path.exists(self.cert_path) and self.cert_password:
                self._cert_manager = CertificateManager(pfx_path=self.cert_path, password=self.cert_password)
                self._cert_manager.load()
                logger.info(f"Certificado carregado: {self._cert_manager.info.subject_cn}")
            else:
                logger.warning("Certificado não configurado, algumas operações podem falhar")
                self._cert_manager = None

            self._manager = NFSeManausManager(
                certificate_manager=self._cert_manager,
                ambiente=self.ambiente,
                inscricao_municipal=self.inscricao_municipal,
                cnpj=self.cnpj,
                usuario=self.usuario,
                senha=self.senha,
            )

        return self._manager

    def emitir_nfse(
        self,
        tomador_data: dict[str, Any],
        servico_data: dict[str, Any],
        competencia: str | None = None,
        natureza_operacao: str = "1",
        optante_simples: bool = True,
    ) -> dict[str, Any]:
        """
        Emite NFS-e através de RPS.

        Args:
            tomador_data: Dados do tomador do serviço:
                - cpf_cnpj: CPF ou CNPJ do tomador
                - razao_social: Nome/Razão social
                - endereco: Logradouro
                - numero: Número
                - bairro: Bairro
                - cidade: Cidade
                - uf: Estado (2 letras)
                - cep: CEP
                - email: Email (opcional)
                - telefone: Telefone (opcional)
            servico_data: Dados do serviço:
                - codigo_servico: Código LC 116 (ex: "11.02")
                - discriminacao: Descrição do serviço
                - valor_servicos: Valor total
                - aliquota_iss: Alíquota ISS (ex: 0.05 = 5%)
                - iss_retido: Se ISS é retido (bool)
            competencia: Competência no formato "YYYY-MM" (default: mês atual)
            natureza_operacao: Código da natureza (1=Tributação no município)
            optante_simples: Se é optante do Simples Nacional

        Returns:
            Dict com resultado da emissão:
                - numero_lote: Número do lote enviado
                - numero_rps: Número do RPS
                - xml_envio: XML enviado
                - status: Status da operação
                - protocolo: Protocolo de recebimento (se houver)
                - numero_nfse: Número da NFS-e (se autorizada)
                - codigo_verificacao: Código de verificação
        """
        manager = self._get_manager()

        # Criar objeto Tomador
        tomador = Tomador(
            cpf_cnpj=tomador_data.get("cpf_cnpj", ""),
            razao_social=tomador_data.get("razao_social", ""),
            endereco=tomador_data.get("endereco", ""),
            numero=tomador_data.get("numero", "S/N"),
            bairro=tomador_data.get("bairro", ""),
            cidade=tomador_data.get("cidade", "Manaus"),
            uf=tomador_data.get("uf", "AM"),
            cep=tomador_data.get("cep", ""),
            email=tomador_data.get("email"),
            telefone=tomador_data.get("telefone"),
            inscricao_municipal=tomador_data.get("inscricao_municipal"),
        )

        # Criar objeto Servico
        valor_servicos = Decimal(str(servico_data.get("valor_servicos", 0)))
        aliquota_iss = Decimal(str(servico_data.get("aliquota_iss", "0.05")))
        iss_retido = servico_data.get("iss_retido", False)

        # Calcular ISS
        valor_iss = valor_servicos * aliquota_iss

        servico = Servico(
            codigo_servico=servico_data.get("codigo_servico", "11.02"),
            discriminacao=servico_data.get("discriminacao", ""),
            valor_servicos=valor_servicos,
            valor_deducoes=Decimal(str(servico_data.get("valor_deducoes", 0))),
            valor_iss=valor_iss,
            aliquota_iss=aliquota_iss,
            iss_retido=iss_retido,
            codigo_cnae=servico_data.get("codigo_cnae"),
        )

        # Competência
        if competencia:
            comp_date = datetime.strptime(competencia, "%Y-%m").date()
        else:
            comp_date = date.today().replace(day=1)

        # Criar NFS-e
        nfse = NFSeManaus(
            prestador_cnpj=self.cnpj,
            prestador_inscricao_municipal=self.inscricao_municipal,
            tomador=tomador,
            servico=servico,
            data_emissao=datetime.now(),
            competencia=comp_date,
            natureza_operacao=NaturezaOperacao(natureza_operacao),
            optante_simples=optante_simples,
        )

        # Enviar lote
        resultado = manager.enviar_lote_rps([nfse])

        # Se ambiente de produção, enviar requisição SOAP
        if self.ambiente == "producao" and self._cert_manager:
            resposta = manager.enviar_requisicao("RecepcionarLoteRps", resultado["xml_envio"])

            resultado.update(
                {
                    "resposta_ws": resposta,
                    "status": "enviado" if resposta.get("sucesso") else "erro",
                    "protocolo": resposta.get("protocolo"),
                    "mensagem": resposta.get("erro") if not resposta.get("sucesso") else None,
                }
            )
        else:
            resultado["status"] = "simulado"
            resultado["mensagem"] = "Ambiente de homologação ou certificado não configurado"

        logger.info(
            f"NFS-e emitida: CNPJ={self.cnpj}, "
            f"Tomador={tomador.cpf_cnpj}, "
            f"Valor={valor_servicos}, "
            f"Status={resultado['status']}"
        )

        return resultado

    def consultar_nfse_por_rps(self, numero_rps: str, serie: str = "RPS", tipo: str = "1") -> dict[str, Any]:
        """
        Consulta NFS-e pelo número do RPS.

        Args:
            numero_rps: Número do RPS
            serie: Série do RPS (default: "RPS")
            tipo: Tipo do RPS (default: "1")

        Returns:
            Dict com dados da NFS-e ou erro
        """
        manager = self._get_manager()

        resultado = manager.consultar_nfse_por_rps(numero_rps, serie, tipo)

        # Enviar requisição se em produção
        if self.ambiente == "producao" and self._cert_manager:
            resposta = manager.enviar_requisicao("ConsultarNfsePorRps", resultado["xml_consulta"])
            resultado["resposta_ws"] = resposta
            resultado["status"] = "consultado" if resposta.get("sucesso") else "erro"
        else:
            resultado["status"] = "simulado"

        return resultado

    def consultar_nfse_por_numero(self, numero_nfse: str) -> dict[str, Any]:
        """
        Consulta NFS-e pelo número da nota.

        Args:
            numero_nfse: Número da NFS-e

        Returns:
            Dict com dados da NFS-e
        """
        manager = self._get_manager()

        resultado = manager.consultar_nfse_por_numero(numero_nfse)

        if self.ambiente == "producao" and self._cert_manager:
            resposta = manager.enviar_requisicao("ConsultarNfse", resultado["xml_consulta"])
            resultado["resposta_ws"] = resposta
            resultado["status"] = "consultado" if resposta.get("sucesso") else "erro"
        else:
            resultado["status"] = "simulado"

        return resultado

    def cancelar_nfse(
        self, numero_nfse: str, codigo_cancelamento: str = "1", motivo: str | None = None
    ) -> dict[str, Any]:
        """
        Cancela uma NFS-e.

        Args:
            numero_nfse: Número da NFS-e a cancelar
            codigo_cancelamento: Código do motivo:
                - "1": Erro na emissão
                - "2": Serviço não prestado
                - "3": Erro de preenchimento
                - "4": Duplicidade
            motivo: Descrição do motivo (opcional)

        Returns:
            Dict com resultado do cancelamento
        """
        manager = self._get_manager()

        resultado = manager.cancelar_nfse(numero_nfse, codigo_cancelamento)
        resultado["motivo"] = motivo

        if self.ambiente == "producao" and self._cert_manager:
            resposta = manager.enviar_requisicao("CancelarNfse", resultado["xml_cancelamento"])
            resultado["resposta_ws"] = resposta
            resultado["status"] = "cancelado" if resposta.get("sucesso") else "erro"
        else:
            resultado["status"] = "simulado"

        logger.info(f"Cancelamento NFS-e {numero_nfse}: {resultado['status']}")

        return resultado

    def substituir_nfse(
        self,
        numero_nfse_substituida: str,
        tomador_data: dict[str, Any],
        servico_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Substitui uma NFS-e por outra.

        Args:
            numero_nfse_substituida: Número da NFS-e a substituir
            tomador_data: Dados do tomador (mesmo formato de emitir_nfse)
            servico_data: Dados do serviço (mesmo formato de emitir_nfse)

        Returns:
            Dict com resultado da substituição
        """
        manager = self._get_manager()

        # Criar nova NFS-e
        tomador = Tomador(
            cpf_cnpj=tomador_data.get("cpf_cnpj", ""),
            razao_social=tomador_data.get("razao_social", ""),
            endereco=tomador_data.get("endereco", ""),
            numero=tomador_data.get("numero", "S/N"),
            bairro=tomador_data.get("bairro", ""),
            cidade=tomador_data.get("cidade", "Manaus"),
            uf=tomador_data.get("uf", "AM"),
            cep=tomador_data.get("cep", ""),
        )

        valor_servicos = Decimal(str(servico_data.get("valor_servicos", 0)))
        servico = Servico(
            codigo_servico=servico_data.get("codigo_servico", "11.02"),
            discriminacao=servico_data.get("discriminacao", ""),
            valor_servicos=valor_servicos,
        )

        nova_nfse = NFSeManaus(
            prestador_cnpj=self.cnpj,
            prestador_inscricao_municipal=self.inscricao_municipal,
            tomador=tomador,
            servico=servico,
        )

        resultado = manager.substituir_nfse(numero_nfse_substituida, nova_nfse)

        if self.ambiente == "producao" and self._cert_manager:
            resposta = manager.enviar_requisicao("SubstituirNfse", resultado["xml_substituicao"])
            resultado["resposta_ws"] = resposta
            resultado["status"] = "substituida" if resposta.get("sucesso") else "erro"
        else:
            resultado["status"] = "simulado"

        return resultado

    def consultar_situacao_lote(self, numero_lote: str) -> dict[str, Any]:
        """
        Consulta situação de um lote de RPS.

        Args:
            numero_lote: Número do lote

        Returns:
            Dict com situação do lote
        """
        manager = self._get_manager()

        # Montar XML de consulta
        from xml.etree import ElementTree as ET  # noqa: S405

        consulta = ET.Element("ConsultarSituacaoLoteRpsEnvio", xmlns=manager.NS_TIPOS)

        prestador = ET.SubElement(consulta, "Prestador")
        cpf_cnpj = ET.SubElement(prestador, "CpfCnpj")
        ET.SubElement(cpf_cnpj, "Cnpj").text = self.cnpj
        ET.SubElement(prestador, "InscricaoMunicipal").text = self.inscricao_municipal

        ET.SubElement(consulta, "Protocolo").text = numero_lote

        xml_str = ET.tostring(consulta, encoding="unicode")

        resultado = {
            "numero_lote": numero_lote,
            "xml_consulta": xml_str,
        }

        if self.ambiente == "producao" and self._cert_manager:
            resposta = manager.enviar_requisicao("ConsultarSituacaoLoteRps", xml_str)
            resultado["resposta_ws"] = resposta
            resultado["status"] = "consultado" if resposta.get("sucesso") else "erro"
        else:
            resultado["status"] = "simulado"

        return resultado

    def validar_conexao(self) -> dict[str, Any]:
        """
        Valida conexão com WebService da Prefeitura.

        Returns:
            Dict com status da conexão
        """
        import requests

        manager = self._get_manager()

        resultado = {
            "ambiente": self.ambiente,
            "cnpj": self.cnpj,
            "url_base": manager.url_base,
            "certificado_configurado": self._cert_manager is not None,
        }

        # Testar conexão HTTP
        try:
            response = requests.get(f"{manager.url_base}/arecepcionarloterps?wsdl", timeout=10)
            resultado["conexao_http"] = response.status_code == 200
            resultado["http_status"] = response.status_code
        except requests.RequestException as e:
            resultado["conexao_http"] = False
            resultado["erro_http"] = str(e)

        # Validar certificado se configurado
        if self._cert_manager:
            valido, msg = self._cert_manager.validate()
            resultado["certificado_valido"] = valido
            resultado["certificado_mensagem"] = msg
            resultado["certificado_expira"] = self._cert_manager.info.valid_until.isoformat()

        return resultado


# Singleton para uso global
_nfse_service: NFSeManausService | None = None


def get_nfse_manaus_service() -> NFSeManausService:
    """Obtém instância singleton do service."""
    global _nfse_service
    if _nfse_service is None:
        _nfse_service = NFSeManausService()
    return _nfse_service
