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
import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from modules.government_integrations.core import CertificateManager
from modules.government_integrations.core.nfse_nacional import (
    CTRIBNAC_PADRAO,
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


class CertificadoDeOutraEmpresaError(RuntimeError):
    """O certificado carregado não pertence ao CNPJ que vai emitir a nota.

    Emitir assinado pela empresa errada é pior do que não emitir: a nota nasce
    com o CNPJ de um prestador e a assinatura de outro. Aqui a emissão PARA.
    """


class NFSeNacionalService:
    """
    Service para operações de NFS-e com o Padrão Nacional.

    **Manaus ADERIU** — o texto anterior aqui dizia «em preparação, o Padrão Nacional ainda
    não está disponível em Manaus» e isso é falso desde pelo menos 01/2026: esta casa tem
    115 NFS-e reais no Padrão Nacional, com chave começando em `1302603` (IBGE de Manaus),
    e a frente Z7 emitiu em homologação pelos DOIS CNPJs em 24/09/2026.

    O que é REAL aqui:
    - emissão de DPS (`emitir_dps`) — provada contra a produção restrita, `cStat 100`;
    - consulta de NFS-e por chave e por chave de DPS (`consultar_nfse`, `consultar_por_dps`)
      — é o que a conciliação da frente AA4 usa para achar nota que o ERP não tem.

    O que é RECUSA declarada (e não simulação):
    - cancelamento, substituição e consulta de eventos por chave. Ver `_NAO_IMPLEMENTADO`.
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
                raise LookupError(f"NFSe Nacional: empresa '{empresa_slug}' sem configuração/CNPJ ativo")
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

    def _exigir_certificado_da_empresa(self) -> None:
        """O CNPJ do certificado tem que ser o CNPJ que assina a nota.

        Sem esta trava, `empresa_slug` trocava o CNPJ do XML mas o certificado
        continuava sendo o do singleton — nota da Patrimonial assinada pela
        Eletrônica. O fisco recusa, e se não recusasse seria pior.
        """
        import re as _re

        do_cert = _re.sub(r"\D", "", (self._cert_manager.info.subject_cpf_cnpj or ""))
        da_empresa = _re.sub(r"\D", "", self.cnpj or "")
        if do_cert and da_empresa and do_cert != da_empresa:
            raise CertificadoDeOutraEmpresaError(
                f"o certificado em {self.cert_path} é do CNPJ {do_cert} "
                f"({self._cert_manager.info.subject_cn}), mas a emissão é do CNPJ {da_empresa}"
                + (f" (empresa '{self.empresa_slug}')" if self.empresa_slug else "")
                + " — nota assinada pela empresa errada não sai daqui"
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
                    self._exigir_certificado_da_empresa()
                except CertificadoDeOutraEmpresaError:
                    raise
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
        numero: str | None = None,
        serie: str | None = None,
    ) -> dict[str, Any]:
        """
        Emite DPS (Declaração de Prestação de Serviços). **Transmite de verdade.**

        O aviso «em preparação, retorna payload preparado para migração» que estava aqui
        ficou obsoleto: este caminho autorizou NFS-e reais em 24/09/2026. Produção continua
        travada em `nfse_nacional` (duas camadas + frase-senha) — ver frente Z7.

        Args:
            tomador_data: Dados do tomador do servico
            servico_data: Dados do servico
            prestador_data: Dados do prestador (opcional)
            competencia: Competencia no formato "YYYY-MM"
            tipo_tributacao: Tipo de tributacao

        Returns:
            Dict com o que o fisco devolveu (chave de acesso, cStat, nNFSe, nDFSe, XML)
        """
        manager = self._get_manager()

        # Criar prestador
        if prestador_data:
            # A segunda porta para o mesmo erro: o slug escolhe o certificado, mas
            # `prestador.cnpj` escrevia por cima do CNPJ no XML. Quem quer emitir por
            # outro CNPJ troca de EMPRESA, não de campo.
            pedido = re.sub(r"\D", "", str(prestador_data.get("cnpj") or ""))
            meu = re.sub(r"\D", "", self.cnpj or "")
            if pedido and meu and pedido != meu:
                raise CertificadoDeOutraEmpresaError(
                    f"prestador.cnpj={pedido} não é o CNPJ desta emissão ({meu})"
                    + (f", empresa '{self.empresa_slug}'" if self.empresa_slug else "")
                    + " — escolha a empresa em `empresa`, não reescreva o CNPJ do prestador"
                )
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
            codigo_tributacao_nacional=servico_data.get("codigo_tributacao_nacional") or CTRIBNAC_PADRAO,
            descricao=servico_data.get("descricao", ""),
            valor_servico=valor_servico,
            valor_deducao=Decimal(str(servico_data.get("valor_deducao", 0))),
            valor_desconto_incondicionado=Decimal(str(servico_data.get("valor_desconto_incondicionado", 0))),
            valor_desconto_condicionado=Decimal(str(servico_data.get("valor_desconto_condicionado", 0))),
            codigo_cnae=servico_data.get("codigo_cnae"),
            codigo_nbs=servico_data.get("codigo_nbs"),
            aliquota_iss=aliquota_iss,
            iss_retido=servico_data.get("iss_retido", False),
        )

        # Competencia
        if competencia:
            comp_date = datetime.strptime(competencia, "%Y-%m")
        else:
            comp_date = datetime.now()

        # Número da DPS. Quem chama pelo emissor da Z7 passa o número reservado no
        # contador atômico (`nfse_emissao.proximo_numero`). Sem número dado, cai no
        # timestamp histórico — que é buraco garantido na numeração e por isso fica
        # anotado aqui em vez de escondido.
        numero_dps = str(numero).strip() if numero else f"{int(datetime.now().timestamp())}"

        # Criar DPS
        dps = DPSNacional(
            id_dps=f"DPS-{datetime.now().strftime('%Y')}-{numero_dps}",
            numero=numero_dps,
            # Série de QUEM emite. Sem isto a DPS saía sempre com 900 (chumbada no montador),
            # e sandbox, produção e o portal da contabilidade colidiam no fisco com E0014.
            serie=str(serie) if serie else "900",
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

    def consultar_por_dps(self, serie: str, numero: int | str) -> dict[str, Any]:
        """Pergunta ao fisco qual NFS-e saiu de (CNPJ + série + número de DPS).

        Substituiu um stub que devolvia um estado inventado e uma mensagem dizendo que o
        Padrão Nacional não estava disponível, **sem bater em URL nenhuma** — texto simulado
        num caminho de dinheiro. Manaus aderiu, e esta casa tem 115 notas reais lá dentro.
        """
        return self._get_manager().consultar_por_dps(serie, numero)

    def consultar_nfse(self, chave_acesso: str) -> dict[str, Any]:
        """`GET /nfse/{chave}` de verdade. Também substituiu um stub que não fazia requisição."""
        return self._get_manager().consultar_nfse(chave_acesso)

    #: Cancelamento e substituição de NFS-e existem no Padrão Nacional (evento
    #: `POST /nfse/{chave}/eventos`) e NÃO estão implementados aqui. O que havia no lugar
    #: eram três stubs devolvendo um estado inventado e a mensagem de que o Padrão Nacional
    #: não estava disponível — texto simulado num caminho de documento fiscal, e falso desde
    #: que Manaus aderiu: esta casa tem 115 notas reais no Padrão Nacional.
    #: Cancelar sem nunca ter exercido o caminho é pior que não cancelar. A recusa abaixo
    #: diz a verdade e aponta onde fazer.
    _NAO_IMPLEMENTADO = {
        "status": "nao_implementado",
        "implementado": False,
        "mensagem": (
            "Este sistema NÃO cancela nem substitui NFS-e do Padrão Nacional — o evento "
            "`POST /nfse/{chave}/eventos` nunca foi exercido aqui e nada que não foi exercido "
            "contra o fisco entra num caminho de documento fiscal. Faça pelo portal do fisco. "
            "Atenção ao prazo de cancelamento."
        ),
    }

    def cancelar_nfse(
        self, numero_nfse: str, motivo_cancelamento: str = "1", justificativa: str | None = None
    ) -> dict[str, Any]:
        """Recusa honesta. Ver `_NAO_IMPLEMENTADO`."""
        logger.info(f"Cancelamento de NFS-e pedido e RECUSADO (não implementado): {numero_nfse}")
        return {**self._NAO_IMPLEMENTADO, "operacao": "cancelar_nfse", "numero_nfse": numero_nfse}

    def substituir_nfse(
        self,
        numero_nfse_substituida: str,
        tomador_data: dict[str, Any],
        servico_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Recusa honesta. Ver `_NAO_IMPLEMENTADO`."""
        logger.info(f"Substituição de NFS-e pedida e RECUSADA (não implementada): {numero_nfse_substituida}")
        return {
            **self._NAO_IMPLEMENTADO,
            "operacao": "substituir_nfse",
            "numero_nfse_substituida": numero_nfse_substituida,
        }

    def consultar_eventos(self, numero_nfse: str) -> dict[str, Any]:
        """Recusa honesta: a consulta de eventos por chave não foi exercida contra o fisco.

        Quem hoje traz evento de cancelamento é a varredura do ADN por NSU
        (`gedeon/services/nfse_nacional_adn.distribuir`), que lê `e105101`/`e105102` — e
        essa SIM é real e está em produção.
        """
        logger.info(f"Consulta de eventos de NFS-e pedida e RECUSADA (não implementada): {numero_nfse}")
        return {
            **self._NAO_IMPLEMENTADO,
            "operacao": "consultar_eventos",
            "numero_nfse": numero_nfse,
            "onde_ha_evento_de_verdade": "modules/gedeon/services/nfse_nacional_adn.distribuir (ADN, por NSU)",
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
        Valida conexão e status do Padrão Nacional.

        Devolvia `status_api = "preparacao"` e «Migração prevista para 2026» — texto que a
        tela podia mostrar e que é falso: Manaus já está no Padrão Nacional e este sistema
        emite por ele. O que esta função sabe de verdade é se há certificado e se ele vale.

        Returns:
            Dict com o host do ambiente, o certificado e a validade dele
        """
        manager = self._get_manager()

        resultado = {
            "ambiente": self.ambiente,
            "cnpj": self.cnpj,
            "url_base": manager.url_base,
            "status_api": "ativo",
            "certificado_configurado": self._cert_manager is not None,
            "migracao_disponivel": True,
            "mensagem": (
                "Manaus está no Padrão Nacional: há 115 NFS-e reais desta casa lá, e a emissão por "
                "este caminho foi autorizada em homologação (produção restrita) em 24/09/2026."
            ),
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


# Um service POR EMPRESA. Era um singleton só, sem slug: qualquer emissão saía com o
# CNPJ e o certificado da Eletrônica, e a Patrimonial — que é quem faz vigilância,
# portaria e limpeza — não tinha como emitir nota nenhuma pelo ERP.
_services_por_empresa: dict[str | None, NFSeNacionalService] = {}

#: Apelidos aceitos na API para não obrigar ninguém a decorar o slug.
_APELIDOS: dict[str, str] = {
    "eletronica": "conecta_eletronica",
    "conectamais_eletronica": "conecta_eletronica",
    "35710481000103": "conecta_eletronica",
    "patrimonial": "conecta_patrimonial",
    "conectamais_patrimonial": "conecta_patrimonial",
    "66014833000110": "conecta_patrimonial",
}


def resolver_empresa_slug(valor: str | None) -> str | None:
    """Slug canônico a partir de slug, apelido ou CNPJ (com ou sem pontuação)."""
    if not valor:
        return None
    bruto = str(valor).strip().lower()
    return _APELIDOS.get(bruto) or _APELIDOS.get(re.sub(r"\D", "", bruto)) or bruto


def get_nfse_nacional_service(empresa: str | None = None) -> NFSeNacionalService:
    """Service da empresa pedida. `None` = comportamento histórico (CNPJ1, via env)."""
    slug = resolver_empresa_slug(empresa)
    if slug not in _services_por_empresa:
        _services_por_empresa[slug] = NFSeNacionalService(empresa_slug=slug)
    return _services_por_empresa[slug]
