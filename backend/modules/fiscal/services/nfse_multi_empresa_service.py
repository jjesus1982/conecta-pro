"""
NFS-e Multi-Empresa Service
Seleciona automaticamente empresa emissora e aplica liminares no XML.

Fluxo:
1. Receber dados da NFS-e (tipo_servico, valor, cliente, etc.)
2. Identificar empresa emissora (Eletrônica ou Patrimonial)
3. Buscar liminares ativas da empresa
4. Aplicar liminares nos campos da NFS-e (PIS/COFINS=0, INSS=não retido)
5. Gerar XML conforme Sistema Nacional NFS-e
6. Transmitir via certificado A1 + Gov.br
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

# Mapeamento serviço → empresa (mesma lógica do ContractMigratorAgent)
SERVICOS_HUMANIZADOS = [
    "vigilancia",
    "portaria_presencial",
    "portaria_24h",
    "portaria_12x36",
    "limpeza",
    "jardinagem",
    "facilities",
    "recepcao",
    "zeladoria",
]
SERVICOS_ELETRONICOS = [
    "portaria_remota",
    "monitoramento",
    "cftv",
    "alarmes",
    "controle_acesso",
    "automacao",
    "seguranca_eletronica",
]

# Fallback estático usado APENAS se o banco não responder (dados mínimos e
# HONESTOS — liminares nunca são assumidas aqui; a fonte é a tabela liminares
# com status concedido). Fonte da verdade em runtime: tabela `empresas`.
EMPRESAS_CONFIG: dict[str, dict[str, Any]] = {
    "conecta_eletronica": {
        "cnpj": "35710481000103",
        "razao_social": "CONECTAMAIS ELETRONICA LTDA",
        "inscricao_municipal": "45177801",
        "suframa": "210140500",
        "codigo_municipio": "1302603",
        "regime": "lucro_real",
        "certificado_path": "/opt/conecta-pro/credentials/certificates/certificado.pfx",
        "certificado_senha": "Conecta123",
        "ambiente": "homologacao",
        "liminares": [],
    },
    "conecta_patrimonial": {
        "cnpj": "66014833000110",
        "razao_social": "CONECTAMAIS PATRIMONIAL LTDA",
        "inscricao_municipal": "721042001",
        "codigo_municipio": "1302603",
        "regime": "simples_nacional",
        "certificado_path": "/app/credentials/certificates/patrimonial.pfx",
        "ambiente": "homologacao",
        "liminares": [],  # NUNCA assumir liminar não concedida (notas reais têm INSS retido)
    },
}

_REFRESH_TTL_S = 60.0
_ultimo_refresh: list[float] = [0.0]


def refresh_empresas_config(force: bool = False) -> None:
    """Recarrega EMPRESAS_CONFIG da tabela `empresas` (+ liminares CONCEDIDAS).

    Mutação in-place (o dict é importado por referência pelo controller).
    Falha de banco => mantém o conteúdo atual (fallback honesto).
    """
    import os
    import re
    import time

    if not force and (time.monotonic() - _ultimo_refresh[0]) < _REFRESH_TTL_S:
        return
    url = re.sub(r"\+asyncpg|\+psycopg2?", "", os.getenv("DATABASE_URL", ""))
    if not url:
        return
    try:
        import psycopg2

        conn = psycopg2.connect(url)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT e.slug, e.cnpj, e.razao_social, e.inscricao_municipal,
                           e.inscricao_suframa, e.codigo_municipio_ibge,
                           e.regime_tributario, e.certificado_a1_path,
                           e.certificado_a1_senha, e.nfse_ambiente,
                           COALESCE(ARRAY_AGG(l.tipo) FILTER (
                               WHERE l.data_concessao IS NOT NULL
                                 AND LOWER(COALESCE(l.status::text,'')) NOT IN
                                     ('a_solicitar','indeferida','cassada','expirada','suspensa')
                           ), '{}') AS liminares_concedidas
                    FROM empresas e
                    LEFT JOIN liminares l ON l.empresa_id = e.id
                    WHERE e.status = 'ativa'
                    GROUP BY e.id
                    """
                )
                for row in cur.fetchall():
                    (slug, cnpj, razao, im, suframa, cod_mun, regime,
                     cert_path, cert_senha, ambiente, liminares) = row
                    cfg = EMPRESAS_CONFIG.setdefault(slug, {})
                    cfg.update(
                        {
                            "cnpj": re.sub(r"\D", "", cnpj or "") or None,
                            "razao_social": (razao or "").strip() or cfg.get("razao_social"),
                            "inscricao_municipal": re.sub(r"\D", "", im or "") or None,
                            "suframa": re.sub(r"\D", "", suframa or "") or None,
                            "codigo_municipio": (cod_mun or "1302603").strip(),
                            "regime": (str(regime) or "").replace("RegimeTributarioEnum.", "").lower()
                            or cfg.get("regime"),
                            "certificado_path": cert_path or cfg.get("certificado_path"),
                            "certificado_senha": cert_senha or cfg.get("certificado_senha"),
                            "ambiente": ambiente or cfg.get("ambiente", "homologacao"),
                            "liminares": sorted(set(liminares or [])),
                        }
                    )
        finally:
            conn.close()
        _ultimo_refresh[0] = time.monotonic()
    except Exception as e:  # noqa: BLE001
        logger.warning("EMPRESAS_CONFIG: falha ao recarregar do banco (%s); mantendo atual", e)


try:  # carga inicial no import (não derruba o app se o banco estiver fora)
    refresh_empresas_config(force=True)
except Exception:  # noqa: BLE001
    pass


@dataclass
class DadosNFSeMultiEmpresa:
    """Dados de entrada para emissão multi-empresa."""

    # Serviço
    tipo_servico: str
    descricao_servico: str
    valor_servico: float

    # Tomador (cliente)
    tomador_cnpj_cpf: str
    tomador_razao_social: str
    tomador_email: str | None = None
    tomador_municipio_codigo: str = "1302603"

    # Empresa emissora (auto-detectada se None)
    empresa_slug: str | None = None

    # Competência
    competencia_ano: int = 2026
    competencia_mes: int = 3

    # Forçar liminares mesmo antes de concedidas (para testes)
    forcar_liminares: list[str] = field(default_factory=list)


@dataclass
class ResultadoNFSeMultiEmpresa:
    """Resultado da preparação da NFS-e."""

    sucesso: bool
    empresa_emissora: str
    liminares_aplicadas: list[str]

    # Valores calculados
    valor_servico: float
    pis: float
    cofins: float
    iss: float
    inss_retido: bool
    valor_liquido: float

    # XML e protocolo
    xml_gerado: str | None = None
    numero_rps: str | None = None
    protocolo: str | None = None
    mensagem: str = ""
    ambiente: str = "homologacao"

    # Motivo seleção empresa
    motivo_empresa: str = ""


class NfseMultiEmpresaService:
    """
    Serviço para emissão de NFS-e com seleção automática de empresa
    e aplicação de liminares.
    """

    # Expor config para acesso externo (controllers)
    EMPRESAS_CONFIG = EMPRESAS_CONFIG

    def identificar_empresa(self, tipo_servico: str) -> str:
        """Identifica qual empresa deve emitir baseado no tipo de serviço."""
        ts = tipo_servico.lower()
        if any(s in ts for s in SERVICOS_HUMANIZADOS):
            return "conecta_patrimonial"
        if any(s in ts for s in SERVICOS_ELETRONICOS):
            return "conecta_eletronica"
        # Default: eletrônica (tem CNPJ ativo)
        return "conecta_eletronica"

    def calcular_tributos(
        self,
        valor_servico: float,
        empresa_slug: str,
        liminares_ativas: list[str],
    ) -> dict[str, Any]:
        """
        Calcula tributos da NFS-e conforme regime e liminares.

        Lucro Real (Eletrônica):
        - PIS: 0,65%, COFINS: 3%, ISS: 5%
        - INSS: 11% retido pelo tomador

        Simples Nacional (Patrimonial):
        - ISS: 5% (incluso no DAS, mas tomador retém)
        - Se liminar pis_cofins_zero: PIS=0, COFINS=0
        - Se liminar inss_nao_retido: INSS não retido
        """
        empresa = EMPRESAS_CONFIG.get(empresa_slug, EMPRESAS_CONFIG["conecta_eletronica"])
        regime = empresa["regime"]
        v = Decimal(str(valor_servico))

        if regime == "lucro_real":
            pis = float((v * Decimal("0.0065")).quantize(Decimal("0.01")))
            cofins = float((v * Decimal("0.03")).quantize(Decimal("0.01")))
            iss = float((v * Decimal("0.05")).quantize(Decimal("0.01")))
            inss_retido = True
            inss_valor = float((v * Decimal("0.11")).quantize(Decimal("0.01")))
        else:  # simples_nacional
            pis = 0.0
            cofins = 0.0
            iss = float((v * Decimal("0.05")).quantize(Decimal("0.01")))
            inss_retido = True
            inss_valor = float((v * Decimal("0.11")).quantize(Decimal("0.01")))

        liminares_aplicadas: list[str] = []

        if "pis_cofins_zero" in liminares_ativas:
            pis = 0.0
            cofins = 0.0
            liminares_aplicadas.append("pis_cofins_zero")

        if "inss_nao_retido" in liminares_ativas:
            inss_retido = False
            inss_valor = 0.0
            liminares_aplicadas.append("inss_nao_retido")

        total_retencoes = pis + cofins + iss + (inss_valor if inss_retido else 0)
        valor_liquido = float(v) - total_retencoes

        return {
            "pis": pis,
            "cofins": cofins,
            "iss": iss,
            "inss_retido": inss_retido,
            "inss_valor": inss_valor,
            "total_retencoes": total_retencoes,
            "valor_liquido": valor_liquido,
            "liminares_aplicadas": liminares_aplicadas,
        }

    def preparar_dados_nfse(self, dados: DadosNFSeMultiEmpresa) -> ResultadoNFSeMultiEmpresa:
        """
        Prepara todos os dados para emissão da NFS-e.
        Retorna resultado com tributos calculados e XML estruturado.
        """
        # 1. Identificar empresa
        empresa_slug = dados.empresa_slug or self.identificar_empresa(dados.tipo_servico)
        empresa_cfg = EMPRESAS_CONFIG.get(empresa_slug, EMPRESAS_CONFIG["conecta_eletronica"])

        # Motivo seleção
        motivo = f"Serviço '{dados.tipo_servico}' → {empresa_slug} ({empresa_cfg['regime']})"

        # 2. Liminares ativas (seed + forçadas para testes)
        liminares = list(set(empresa_cfg.get("liminares", []) + dados.forcar_liminares))

        # 3. Calcular tributos
        tributos = self.calcular_tributos(
            valor_servico=dados.valor_servico,
            empresa_slug=empresa_slug,
            liminares_ativas=liminares,
        )

        # 4. Verificar se empresa pode emitir (tem CNPJ)
        if empresa_cfg.get("cnpj") is None:
            return ResultadoNFSeMultiEmpresa(
                sucesso=False,
                empresa_emissora=empresa_slug,
                liminares_aplicadas=tributos["liminares_aplicadas"],
                valor_servico=dados.valor_servico,
                pis=tributos["pis"],
                cofins=tributos["cofins"],
                iss=tributos["iss"],
                inss_retido=tributos["inss_retido"],
                valor_liquido=tributos["valor_liquido"],
                mensagem=(
                    f"{empresa_slug} ainda nao tem CNPJ cadastrado (em abertura). "
                    f"Emitir pela Eletronica ate CNPJ ser obtido."
                ),
                motivo_empresa=motivo,
                ambiente=empresa_cfg.get("ambiente", "homologacao"),
            )

        # 5. Gerar XML (Sistema Nacional NFS-e)
        xml = self._gerar_xml_nfse(dados, empresa_cfg, tributos)

        return ResultadoNFSeMultiEmpresa(
            sucesso=True,
            empresa_emissora=empresa_slug,
            liminares_aplicadas=tributos["liminares_aplicadas"],
            valor_servico=dados.valor_servico,
            pis=tributos["pis"],
            cofins=tributos["cofins"],
            iss=tributos["iss"],
            inss_retido=tributos["inss_retido"],
            valor_liquido=tributos["valor_liquido"],
            xml_gerado=xml,
            mensagem="Dados preparados para transmissao ao Sistema Nacional NFS-e",
            motivo_empresa=motivo,
            ambiente=empresa_cfg.get("ambiente", "homologacao"),
        )

    def _gerar_xml_nfse(
        self,
        dados: DadosNFSeMultiEmpresa,
        empresa_cfg: dict,
        tributos: dict,
    ) -> str:
        """Gera XML da NFS-e no padrão ABRASF / Sistema Nacional."""
        inss_tag = ""
        if tributos["inss_retido"]:
            inss_tag = f"<ValorINSS>{tributos['inss_valor']:.2f}</ValorINSS>"

        # Liminares como comentário XML para rastreabilidade
        liminares_str = ", ".join(tributos["liminares_aplicadas"]) or "nenhuma"
        liminares_comment = f"<!-- Liminares aplicadas: {liminares_str} -->"

        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f"{liminares_comment}\n"
            '<GerarNfseEnvio xmlns="http://www.abrasf.org.br/nfse.xsd">\n'
            "  <Rps>\n"
            "    <InfDeclaracaoPrestacaoServico>\n"
            "      <Rps>\n"
            "        <IdentificacaoRps>\n"
            "          <Numero>1</Numero>\n"
            "          <Serie>1</Serie>\n"
            "          <Tipo>1</Tipo>\n"
            "        </IdentificacaoRps>\n"
            f"        <DataEmissao>{dados.competencia_ano}-{dados.competencia_mes:02d}-01</DataEmissao>\n"
            "        <Status>1</Status>\n"
            "      </Rps>\n"
            f"      <Competencia>{dados.competencia_ano}-{dados.competencia_mes:02d}-01</Competencia>\n"
            "      <Servico>\n"
            "        <Valores>\n"
            f"          <ValorServicos>{dados.valor_servico:.2f}</ValorServicos>\n"
            f"          <ValorPis>{tributos['pis']:.2f}</ValorPis>\n"
            f"          <ValorCofins>{tributos['cofins']:.2f}</ValorCofins>\n"
            f"          <ValorIss>{tributos['iss']:.2f}</ValorIss>\n"
            f"          {inss_tag}\n"
            f"          <ValorLiquidoNfse>{tributos['valor_liquido']:.2f}</ValorLiquidoNfse>\n"
            f"          <IssRetido>{'1' if tributos['inss_retido'] else '2'}</IssRetido>\n"
            "        </Valores>\n"
            "        <ItemListaServico>17.19</ItemListaServico>\n"
            f"        <Discriminacao>{dados.descricao_servico}</Discriminacao>\n"
            f"        <CodigoMunicipio>{empresa_cfg.get('codigo_municipio', '1302603')}</CodigoMunicipio>\n"
            "      </Servico>\n"
            "      <Prestador>\n"
            f"        <CpfCnpj><Cnpj>{empresa_cfg.get('cnpj', '')}</Cnpj></CpfCnpj>\n"
            f"        <InscricaoMunicipal>{empresa_cfg.get('inscricao_municipal', '')}</InscricaoMunicipal>\n"
            "      </Prestador>\n"
            "      <Tomador>\n"
            f"        <CpfCnpj><Cnpj>{dados.tomador_cnpj_cpf}</Cnpj></CpfCnpj>\n"
            f"        <RazaoSocial>{dados.tomador_razao_social}</RazaoSocial>\n"
            "      </Tomador>\n"
            "    </InfDeclaracaoPrestacaoServico>\n"
            "  </Rps>\n"
            "</GerarNfseEnvio>"
        )
