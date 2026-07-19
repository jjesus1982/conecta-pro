"""
Service para NFS-e Padrao Nacional.

Preparacao para migracao do padrao ABRASF para o Padrao Nacional de NFS-e.
O Padrao Nacional esta sendo implementado gradualmente e substituira
os padroes municipais a partir de 2026.

Portal: https://www.gov.br/nfse
Documentacao: https://www.gov.br/nfse/pt-br/acesso-a-informacao/manuais
"""

import logging
import os
from datetime import datetime
from decimal import Decimal
from typing import Any

from modules.government_integrations.core import CertificateManager
from modules.government_integrations.core.nfse_nacional import (
    MAPEAMENTO_SERVICOS_VIGILANCIA,
    AmbienteNacional,
    DPSNacional,
    NFSeNacionalManager,
    PrestadorNacional,
    RegimeEspecial,
    ServicoNacional,
    TipoTributacao,
    TomadorNacional,
)

logger = logging.getLogger(__name__)


class NFSeNacionalService:
    """
    Service para operacoes de NFS-e com Padrao Nacional.

    IMPORTANTE: Este service esta em preparacao para a migracao.
    O Padrao Nacional ainda nao esta disponivel em Manaus.
    Use NFSeManausService para emissoes atuais.

    Funcionalidades (preparacao):
    - Emissao de DPS (Declaracao de Prestacao de Servicos)
    - Consulta de DPS/NFS-e
    - Cancelamento de NFS-e
    - Substituicao de NFS-e
    - Consulta de status de migracao
    - Comparacao entre padroes
    - Mapeamento de codigos de servico
    """

    def __init__(self, empresa_slug: str | None = None):
        """Inicializa o service.

        - `empresa_slug=None` (default): configuração via env vars — comportamento
          histórico (CNPJ1), inalterado para todos os chamadores atuais.
        - `empresa_slug='conecta_patrimonial'` (Multi-CNPJ E5): identidade fiscal,
          certificado e ambiente lidos da tabela `empresas` (fonte única) —
          nunca do env, nunca com fallback de outra empresa.
        """
        self._manager: NFSeNacionalManager | None = None
        self._cert_manager: CertificateManager | None = None
        self.empresa_slug = empresa_slug

        if empresa_slug:
            from modules.fiscal.services.nfse_multi_empresa_service import (
                EMPRESAS_CONFIG,
                refresh_empresas_config,
            )

            refresh_empresas_config()
            cfg = EMPRESAS_CONFIG.get(empresa_slug)
            if not cfg or not cfg.get("cnpj"):
                raise LookupError(
                    f"NFSe Nacional: empresa '{empresa_slug}' sem configuração/CNPJ ativo"
                )
            self.cnpj = cfg["cnpj"]
            self.ambiente = cfg.get("ambiente") or "homologacao"
            self.inscricao_municipal = cfg.get("inscricao_municipal") or ""
            self.codigo_municipio = cfg.get("codigo_municipio") or "1302603"
            self.razao_social = cfg.get("razao_social") or ""
            self.cert_path = cfg.get("certificado_path") or ""
            self.cert_password = cfg.get("certificado_senha") or ""
            self.optante_simples = (cfg.get("regime") or "").lower() == "simples_nacional"
        else:
            # Configuracoes do ambiente (legado, CNPJ1)
            self.cnpj = os.getenv("NFSE_NACIONAL_CNPJ", os.getenv("NFSE_MANAUS_CNPJ", "35710481000103"))
            self.ambiente = os.getenv("NFSE_NACIONAL_ENVIRONMENT", "homologacao")
            self.inscricao_municipal = os.getenv("NFSE_NACIONAL_IM", os.getenv("NFSE_MANAUS_IM", ""))
            self.codigo_municipio = os.getenv("NFSE_NACIONAL_COD_MUNICIPIO", "1302603")  # Manaus
            self.razao_social = os.getenv("NFSE_NACIONAL_RAZAO_SOCIAL", "Conecta Plus Servicos LTDA")
            self.cert_path = os.getenv("CERTIFICATE_PATH", "/opt/conecta-pro/credentials/certificates/certificado.pfx")
            self.cert_password = os.getenv("CERTIFICATE_PASSWORD", "")
            self.optante_simples = False  # CNPJ1/legado = Lucro Real (nunca assumir Simples)

        logger.info(
            f"NFSe Nacional Service inicializado - CNPJ: {self.cnpj}"
            + (f" (empresa={empresa_slug})" if empresa_slug else "")
        )

    def _get_manager(self) -> NFSeNacionalManager:
        """Obtem instancia do manager, inicializando se necessario."""
        if self._manager is None:
            # Inicializar certificado se disponivel
            if os.path.exists(self.cert_path) and self.cert_password:
                try:
                    self._cert_manager = CertificateManager(pfx_path=self.cert_path, password=self.cert_password)
                    self._cert_manager.load()
                    logger.info(f"Certificado carregado: {self._cert_manager.info.subject_cn}")
                except Exception as e:
                    logger.warning(f"Erro ao carregar certificado: {e}")
                    self._cert_manager = None
            else:
                logger.warning("Certificado nao configurado para NFS-e Nacional")
                self._cert_manager = None

            ambiente = AmbienteNacional.PRODUCAO if self.ambiente == "producao" else AmbienteNacional.HOMOLOGACAO

            self._manager = NFSeNacionalManager(
                ambiente=ambiente,
                cnpj=self.cnpj,
                certificado_path=self.cert_path if self._cert_manager else None,
                certificado_senha=self.cert_password if self._cert_manager else None,
            )

        return self._manager

    def emitir_dps(
        self,
        tomador_data: dict[str, Any],
        servico_data: dict[str, Any],
        prestador_data: dict[str, Any] | None = None,
        competencia: str | None = None,
        tipo_tributacao: str = "1",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Emite DPS (Declaracao de Prestacao de Servicos).

        NOTA: Esta em preparacao. Retorna payload preparado para migracao.

        Args:
            tomador_data: Dados do tomador do servico
            servico_data: Dados do servico
            prestador_data: Dados do prestador (opcional)
            competencia: Competencia no formato "YYYY-MM"
            tipo_tributacao: Tipo de tributacao

        Returns:
            Dict com resultado da emissao (preparacao)
        """
        manager = self._get_manager()

        # Criar prestador
        if prestador_data:
            prestador = PrestadorNacional(
                cnpj=prestador_data.get("cnpj", self.cnpj),
                inscricao_municipal=prestador_data.get("inscricao_municipal", self.inscricao_municipal),
                codigo_municipio=prestador_data.get("codigo_municipio", self.codigo_municipio),
                razao_social=prestador_data.get("razao_social", self.razao_social),
                nome_fantasia=prestador_data.get("nome_fantasia"),
                regime_especial=RegimeEspecial(prestador_data.get("regime_especial", "6")),
                optante_simples=prestador_data.get("optante_simples", self.optante_simples),
            )
        else:
            prestador = PrestadorNacional(
                cnpj=self.cnpj,
                inscricao_municipal=self.inscricao_municipal,
                codigo_municipio=self.codigo_municipio,
                razao_social=self.razao_social,
                optante_simples=self.optante_simples,
            )

        # Criar tomador
        tomador = TomadorNacional(
            cpf_cnpj=tomador_data.get("cpf_cnpj", ""),
            razao_social=tomador_data.get("razao_social", ""),
            endereco={
                "logradouro": tomador_data.get("logradouro", ""),
                "numero": tomador_data.get("numero", "S/N"),
                "complemento": tomador_data.get("complemento", ""),
                "bairro": tomador_data.get("bairro", ""),
                "codigo_municipio": tomador_data.get("codigo_municipio", "1302603"),
                "uf": tomador_data.get("uf", "AM"),
                "cep": tomador_data.get("cep", ""),
            },
            email=tomador_data.get("email"),
            telefone=tomador_data.get("telefone"),
            inscricao_municipal=tomador_data.get("inscricao_municipal"),
            tipo_documento="CNPJ" if len(tomador_data.get("cpf_cnpj", "")) == 14 else "CPF",
        )

        # Criar servico
        valor_servico = Decimal(str(servico_data.get("valor_servico", 0)))
        aliquota_iss = Decimal(str(servico_data.get("aliquota_iss", "0.05")))

        servico = ServicoNacional(
            codigo_tributacao_nacional=servico_data.get("codigo_tributacao_nacional", "1.1701.10.00"),
            descricao=servico_data.get("descricao", ""),
            valor_servico=valor_servico,
            valor_deducao=Decimal(str(servico_data.get("valor_deducao", 0))),
            valor_desconto_incondicionado=Decimal(str(servico_data.get("valor_desconto_incondicionado", 0))),
            valor_desconto_condicionado=Decimal(str(servico_data.get("valor_desconto_condicionado", 0))),
            codigo_cnae=servico_data.get("codigo_cnae"),
            aliquota_iss=aliquota_iss,
            iss_retido=servico_data.get("iss_retido", False),
        )

        # Competencia
        if competencia:
            comp_date = datetime.strptime(competencia, "%Y-%m")
        else:
            comp_date = datetime.now()

        # Gerar numero DPS
        numero_dps = f"{int(datetime.now().timestamp())}"

        # Criar DPS
        dps = DPSNacional(
            id_dps=f"DPS-{datetime.now().strftime('%Y')}-{numero_dps}",
            numero=numero_dps,
            prestador=prestador,
            tomador=tomador,
            servico=servico,
            data_competencia=comp_date,
            tipo_tributacao=TipoTributacao(tipo_tributacao),
        )

        # Calcular valores
        dps.calcular_valores()

        # Emitir via manager (retorna payload preparado)
        resultado = manager.emitir_dps(dps, dry_run=dry_run)

        # Adicionar informacoes extras
        resultado.update(
            {
                "id_dps": dps.id_dps,
                "numero_dps": dps.numero,
                "valor_servico": str(valor_servico),
                "valor_iss": str(dps.valor_iss) if dps.valor_iss else "0",
                "valor_liquido": str(dps.valor_liquido) if dps.valor_liquido else str(valor_servico),
                "tomador_cpf_cnpj": tomador.cpf_cnpj,
                "data_emissao": datetime.now().isoformat(),
            }
        )

        logger.info(
            f"DPS preparada: ID={dps.id_dps}, "
            f"Tomador={tomador.cpf_cnpj}, "
            f"Valor={valor_servico}, "
            f"Status={resultado['status']}"
        )

        return resultado

    def consultar_dps(self, id_dps: str) -> dict[str, Any]:
        """
        Consulta DPS pelo ID.

        NOTA: Em preparacao. Retorna informacoes simuladas.

        Args:
            id_dps: ID da DPS

        Returns:
            Dict com dados da DPS
        """
        logger.info(f"Consulta DPS: {id_dps}")

        return {
            "status": "preparacao",
            "id_dps": id_dps,
            "mensagem": "Consulta de DPS em preparacao. Padrao Nacional ainda nao disponivel.",
            "nota": "Use NFSeManausService para consultas no padrao atual (ABRASF).",
        }

    def consultar_nfse(self, numero_nfse: str) -> dict[str, Any]:
        """
        Consulta NFS-e pelo numero nacional.

        NOTA: Em preparacao. Retorna informacoes simuladas.

        Args:
            numero_nfse: Numero nacional da NFS-e

        Returns:
            Dict com dados da NFS-e
        """
        logger.info(f"Consulta NFS-e Nacional: {numero_nfse}")

        return {
            "status": "preparacao",
            "numero_nfse": numero_nfse,
            "mensagem": "Consulta de NFS-e Nacional em preparacao. Migracao prevista para 2026.",
            "nota": "Use NFSeManausService para consultas no padrao atual.",
        }

    def cancelar_nfse(
        self, numero_nfse: str, motivo_cancelamento: str = "1", justificativa: str | None = None
    ) -> dict[str, Any]:
        """
        Cancela uma NFS-e no Padrao Nacional.

        NOTA: Em preparacao. Retorna informacoes simuladas.

        Args:
            numero_nfse: Numero nacional da NFS-e a cancelar
            motivo_cancelamento: Codigo do motivo
            justificativa: Justificativa detalhada

        Returns:
            Dict com resultado do cancelamento
        """
        logger.info(f"Cancelamento NFS-e Nacional: {numero_nfse}")

        return {
            "status": "preparacao",
            "numero_nfse": numero_nfse,
            "motivo_cancelamento": motivo_cancelamento,
            "justificativa": justificativa,
            "mensagem": "Cancelamento em preparacao. Padrao Nacional ainda nao disponivel.",
            "nota": "Use NFSeManausService para cancelamentos no padrao atual.",
        }

    def substituir_nfse(
        self,
        numero_nfse_substituida: str,
        tomador_data: dict[str, Any],
        servico_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Substitui uma NFS-e no Padrao Nacional.

        NOTA: Em preparacao. Retorna informacoes simuladas.

        Args:
            numero_nfse_substituida: Numero da NFS-e a substituir
            tomador_data: Dados do tomador
            servico_data: Dados do servico

        Returns:
            Dict com resultado da substituicao
        """
        logger.info(f"Substituicao NFS-e Nacional: {numero_nfse_substituida}")

        return {
            "status": "preparacao",
            "numero_nfse_substituida": numero_nfse_substituida,
            "mensagem": "Substituicao em preparacao. Padrao Nacional ainda nao disponivel.",
            "nota": "Use NFSeManausService para substituicoes no padrao atual.",
        }

    def consultar_eventos(self, numero_nfse: str) -> dict[str, Any]:
        """
        Consulta eventos de uma NFS-e.

        NOTA: Em preparacao.

        Args:
            numero_nfse: Numero nacional da NFS-e

        Returns:
            Dict com eventos da NFS-e
        """
        logger.info(f"Consulta eventos NFS-e Nacional: {numero_nfse}")

        return {
            "status": "preparacao",
            "numero_nfse": numero_nfse,
            "eventos": [],
            "mensagem": "Consulta de eventos em preparacao.",
        }

    def consultar_status_migracao(self) -> dict[str, Any]:
        """
        Consulta status da migracao para o Padrao Nacional.

        Returns:
            Dict com informacoes sobre a migracao
        """
        manager = self._get_manager()
        return manager.consultar_status_migracao()

    def comparar_padroes(self) -> dict[str, Any]:
        """
        Compara caracteristicas entre padrao atual e Padrao Nacional.

        Returns:
            Dict com comparacao entre padroes
        """
        manager = self._get_manager()
        return manager.comparar_padroes()

    def obter_mapeamento_servicos(self) -> list[dict[str, Any]]:
        """
        Obtem mapeamento de codigos de servico ABRASF para NBS.

        Returns:
            Lista de mapeamentos de servicos
        """
        mapeamentos = []
        for codigo_abrasf, dados in MAPEAMENTO_SERVICOS_VIGILANCIA.items():
            mapeamentos.append(
                {
                    "codigo_abrasf": codigo_abrasf,
                    "codigo_nbs": dados["nbs"],
                    "descricao": dados["descricao"],
                }
            )
        return mapeamentos

    def validar_conexao(self) -> dict[str, Any]:
        """
        Valida conexao e status do Padrao Nacional.

        Returns:
            Dict com status da conexao
        """
        manager = self._get_manager()

        resultado = {
            "ambiente": self.ambiente,
            "cnpj": self.cnpj,
            "url_base": manager.url_base,
            "status_api": "preparacao",
            "certificado_configurado": self._cert_manager is not None,
            "migracao_disponivel": False,
            "mensagem": "Padrao Nacional em preparacao. Migracao prevista para 2026.",
        }

        # Validar certificado se configurado
        if self._cert_manager:
            try:
                valido, msg = self._cert_manager.validate()
                resultado["certificado_valido"] = valido
                resultado["certificado_mensagem"] = msg
                resultado["certificado_expira"] = self._cert_manager.info.valid_until.isoformat()
            except Exception as e:
                resultado["certificado_valido"] = False
                resultado["certificado_mensagem"] = str(e)

        return resultado

    def listar_codigos_servico_nacional(self) -> list[dict[str, Any]]:
        """
        Lista codigos de servico disponiveis no Padrao Nacional.

        Returns:
            Lista de codigos de servico NBS
        """
        codigos = [
            {
                "codigo_nbs": "1.1701.10.00",
                "codigo_lc116": "11.02",
                "descricao": "Servicos de vigilancia e seguranca privada",
                "aliquota_sugerida": "5%",
            },
            {
                "codigo_nbs": "1.1701.20.00",
                "codigo_lc116": "11.03",
                "descricao": "Servicos de escolta armada",
                "aliquota_sugerida": "5%",
            },
            {
                "codigo_nbs": "1.1702.10.00",
                "codigo_lc116": "11.04",
                "descricao": "Servicos de armazenamento e guarda de bens",
                "aliquota_sugerida": "5%",
            },
            {
                "codigo_nbs": "1.1701.30.00",
                "codigo_lc116": "11.05",
                "descricao": "Servicos de transporte de valores",
                "aliquota_sugerida": "5%",
            },
            {
                "codigo_nbs": "1.1901.10.00",
                "codigo_lc116": "17.01",
                "descricao": "Assessoria ou consultoria de qualquer natureza",
                "aliquota_sugerida": "5%",
            },
            {
                "codigo_nbs": "1.1901.20.00",
                "codigo_lc116": "17.02",
                "descricao": "Analise, exame, pesquisa e fornecimento de dados",
                "aliquota_sugerida": "5%",
            },
        ]
        return codigos


# Singleton para uso global
_nfse_nacional_service: NFSeNacionalService | None = None


def get_nfse_nacional_service() -> NFSeNacionalService:
    """Obtem instancia singleton do service."""
    global _nfse_nacional_service
    if _nfse_nacional_service is None:
        _nfse_nacional_service = NFSeNacionalService()
    return _nfse_nacional_service
