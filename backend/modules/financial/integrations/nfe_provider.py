"""
NFeProvider - Provedor de integração NF-e com SEFAZ via PyNFe.

Integração real com webservices SEFAZ usando biblioteca PyNFe 0.6.x.
Suporta emissão, cancelamento e consulta de NF-e em homologação/produção.
"""

import asyncio
import re
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from core.logging import logger


class NFeError(Exception):
    """Erro específico de operações NF-e."""

    def __init__(self, message: str, code: str | None = None, details: dict | None = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)


class NFeConfig(BaseModel):
    """Configuração para integração NF-e."""

    certificado_path: str = Field(..., description="Caminho para certificado A1 (.p12/.pfx)")
    certificado_senha: str = Field(..., description="Senha do certificado")
    ambiente: str = Field("2", description="1-Producao, 2-Homologacao")
    uf: str = Field("AM", description="Estado da empresa (Manaus-AM)")
    timeout_seconds: int = Field(30, description="Timeout para requisições SEFAZ")

    class Config:
        extra = "forbid"


# Dados do emitente (CONECTAMAIS ELETRONICA LTDA / Conecta PRO)
_EMITENTE = {
    "cnpj": "35710481000103",
    "razao_social": "CONECTAMAIS ELETRONICA LTDA",
    "nome_fantasia": "Conecta PRO Segurança",
    "ie": "",
    "im": "45177801",
    "cnae": "8011101",
    "regime_tributario": "3",  # 3=Lucro Real
    "logradouro": "Rua dos Andrades",
    "numero": "1000",
    "bairro": "Centro",
    "municipio": "Manaus",
    "cod_municipio": "1302603",
    "uf": "AM",
    "cep": "69010040",
    "pais": "1058",
}

# Mapa UF → código IBGE
_UF_COD = {
    "AM": "13",
    "SP": "35",
    "RJ": "33",
    "MG": "31",
    "RS": "43",
    "PR": "41",
    "SC": "42",
    "BA": "29",
    "GO": "52",
    "DF": "53",
    "CE": "23",
    "PE": "26",
    "MA": "21",
    "PA": "15",
    "MT": "51",
    "MS": "50",
}


def _parse_sefaz_xml(response_text: str) -> dict[str, str]:
    """Extrai campos da resposta SOAP da SEFAZ."""
    ns = "http://www.portalfiscal.inf.br/nfe"
    result: dict[str, str] = {}
    try:
        from lxml import etree

        match = re.search(r"<soap[^:]*:Body>(.*?)</soap[^:]*:Body>", response_text, re.DOTALL)
        if not match:
            return result
        root = etree.fromstring(match.group(1).strip().encode())  # noqa: S320
        for tag in ["cStat", "xMotivo", "chNFe", "nProt", "dhRecbto", "tpAmb", "verAplic", "cUF", "tMed"]:
            el = root.find(f".//{{{ns}}}{tag}")
            if el is not None and el.text:
                result[tag] = el.text.strip()
    except Exception as e:
        logger.warning(f"Erro ao parsear XML SEFAZ: {e}")
    return result


def _calcular_dv_chave(chave_sem_dv: str) -> str:
    """Calcula dígito verificador da chave NF-e (módulo 11)."""
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(int(d) * pesos[i % len(pesos)] for i, d in enumerate(reversed(chave_sem_dv)))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def _montar_nota_fiscal(
    nfe_data: dict[str, Any],
    numero: int,
    codigo_numerico: str,
    ambiente: str,
) -> tuple[Any, Any]:
    """
    Constrói Emitente e NotaFiscal completos para serialização.

    Returns:
        (nota_fiscal, emitente)
    """
    from pynfe.entidades.cliente import Cliente
    from pynfe.entidades.emitente import Emitente
    from pynfe.entidades.notafiscal import NotaFiscal

    # Emitente
    emit = Emitente()
    emit.cnpj = _EMITENTE["cnpj"]
    emit.razao_social = _EMITENTE["razao_social"]
    emit.nome_fantasia = _EMITENTE["nome_fantasia"]
    emit.inscricao_estadual = _EMITENTE["ie"]
    emit.inscricao_municipal = _EMITENTE["im"]
    emit.cnae_fiscal = _EMITENTE["cnae"]
    emit.codigo_de_regime_tributario = _EMITENTE["regime_tributario"]
    emit.endereco_logradouro = _EMITENTE["logradouro"]
    emit.endereco_numero = _EMITENTE["numero"]
    emit.endereco_bairro = _EMITENTE["bairro"]
    emit.endereco_municipio = _EMITENTE["municipio"]
    emit.endereco_cod_municipio = _EMITENTE["cod_municipio"]
    emit.endereco_uf = _EMITENTE["uf"]
    emit.endereco_cep = _EMITENTE["cep"]
    emit.endereco_pais = _EMITENTE["pais"]

    # Destinatário
    dest = nfe_data.get("destinatario", {})
    doc = re.sub(r"\D", "", dest.get("cnpj") or dest.get("cpf", "") or "")
    cli = Cliente()
    cli.tipo_documento = "PJ" if len(doc) == 14 else "PF"
    cli.numero_documento = doc or "00000000000"
    cli.razao_social = (dest.get("razao_social") or dest.get("nome") or "CONSUMIDOR")[:60]
    cli.email = dest.get("email", "")
    cli.indicador_ie = dest.get("indicador_ie", "9")
    cli.inscricao_estadual = dest.get("inscricao_estadual", "")
    cli.inscricao_suframa = dest.get("inscricao_suframa", "")
    end = dest.get("endereco", {})
    cli.endereco_logradouro = (end.get("logradouro") or "NAO INFORMADO")[:60]
    cli.endereco_numero = end.get("numero", "S/N")
    cli.endereco_bairro = (end.get("bairro") or "NAO INFORMADO")[:60]
    cli.endereco_municipio = (end.get("municipio") or "Manaus")[:60]
    cli.endereco_cod_municipio = end.get("cod_municipio", "1302603")
    cli.endereco_uf = end.get("uf", "AM")
    cli.endereco_cep = re.sub(r"\D", "", end.get("cep", "69000000"))
    cli.endereco_pais = "1058"

    # Nota Fiscal
    now = datetime.now()
    nf = NotaFiscal()
    nf.emitente = emit
    nf.destinatario_remetente = cli
    nf.modelo = "55"
    nf.serie = str(nfe_data.get("serie", "1")).zfill(3)
    nf.numero_nf = str(numero).zfill(9)
    nf.forma_emissao = "1"
    nf.processo_emissao = "0"
    nf.versao_processo_emissao = "1.00"
    nf.natureza_operacao = nfe_data.get("natureza_operacao", "PRESTACAO DE SERVICOS")[:60]
    nf.finalidade_emissao = nfe_data.get("finalidade", "1")
    nf.cliente_final = nfe_data.get("cliente_final", "1")
    nf.indicador_destino = nfe_data.get("indicador_destino", "1")
    nf.indicador_presencial = "9"
    nf.municipio = _EMITENTE["cod_municipio"]
    nf.uf = _EMITENTE["uf"]
    nf.data_emissao = now
    nf.data_saida_entrada = now
    nf.tipo_documento = nfe_data.get("tipo", "1")
    nf.transporte_modalidade_frete = "9"
    nf.codigo_numerico_aleatorio = codigo_numerico

    # Uf código
    uf_cod = _UF_COD.get(_EMITENTE["uf"], "13")
    aamm = now.strftime("%y%m")
    chave_sem_dv = f"{uf_cod}{aamm}{_EMITENTE['cnpj']}55{nf.serie}{nf.numero_nf}1{codigo_numerico}"
    dv = _calcular_dv_chave(chave_sem_dv)
    chave = chave_sem_dv + dv
    nf.dv_codigo_numerico_aleatorio = dv
    nf.identificador_unico = f"NFe{chave}"

    # Itens
    items = nfe_data.get("items") or []
    if not items:
        v_total = Decimal(str(nfe_data.get("valor_total", 1000.00)))
        items = [
            {
                "codigo": "001",
                "descricao": "SERVICOS DE PORTARIA E CONTROLE DE ACESSO PARA CONDOMINIOS",
                "ncm": "85311000",
                "cfop": "5933",
                "unidade": "MES",
                "quantidade": 1,
                "valor_unitario": float(v_total),
                "icms_situacao": "40",
                "pis_situacao": "07",
                "cofins_situacao": "07",
            }
        ]

    valor_produtos = Decimal("0.00")
    for i, item in enumerate(items, start=1):
        q = Decimal(str(item.get("quantidade", 1)))
        vu = Decimal(str(item.get("valor_unitario", 0)))
        vt = q * vu
        valor_produtos += vt
        nf.adicionar_produto_servico(
            codigo=str(item.get("codigo", i))[:60],
            descricao=str(item.get("descricao", "SERVICO"))[:120],
            ncm=re.sub(r"\D", "", str(item.get("ncm", "85311000"))),
            cfop=str(item.get("cfop", "5933")),
            unidade_comercial=str(item.get("unidade", "MES")),
            unidade_tributavel=str(item.get("unidade", "MES")),
            quantidade_comercial=q,
            quantidade_tributavel=q,
            valor_unitario_comercial=vu,
            valor_unitario_tributavel=vu,
            valor_total_bruto=vt,
            desconto=Decimal(str(item.get("desconto", 0))),
            compoe_valor_total=True,
            numero_item=i,
            icms_modalidade=str(item.get("icms_situacao", "40")),
            icms_origem="0",
            icms_valor=Decimal("0.00"),
            icms_valor_base_calculo=Decimal("0.00"),
            icms_aliquota=Decimal("0.00"),
            icms_motivo_desoneracao=None,
            pis_situacao_tributaria=str(item.get("pis_situacao", "07")),
            pis_valor_base_calculo=Decimal("0.00"),
            pis_aliquota_percentual=Decimal("0.00"),
            pis_valor=Decimal("0.00"),
            pis_tipo_calculo="P",
            cofins_situacao_tributaria=str(item.get("cofins_situacao", "07")),
            cofins_valor_base_calculo=Decimal("0.00"),
            cofins_aliquota_percentual=Decimal("0.00"),
            cofins_valor=Decimal("0.00"),
            cofins_tipo_calculo="P",
        )

    # Totais
    nf.totais_icms_total_produtos_e_servicos = valor_produtos
    nf.totais_icms_total_nota = valor_produtos
    nf.totais_icms_total_desconto = Decimal("0.00")
    nf.totais_icms_pis = Decimal("0.00")
    nf.totais_icms_cofins = Decimal("0.00")
    nf.totais_icms_total_frete = Decimal("0.00")
    nf.totais_icms_total_seguro = Decimal("0.00")
    nf.totais_icms_outras_despesas_acessorias = Decimal("0.00")

    # Pagamentos
    pagamentos = nfe_data.get("pagamentos") or [{"forma": "01", "valor": float(valor_produtos)}]
    for pag in pagamentos:
        nf.adicionar_pagamento(
            forma_pagamento=str(pag.get("forma", "01")),
            valor=Decimal(str(pag.get("valor", float(valor_produtos)))),
        )

    info_compl = nfe_data.get("informacoes_complementares", "")
    if not info_compl:
        info_compl = "NF-e emitida pelo sistema Conecta PRO ERP."
    nf.informacoes_complementares_interesse_contribuinte = info_compl[:5000]

    return nf, emit, chave


class NFeProvider:
    """
    Provedor de integração NF-e com SEFAZ via PyNFe 0.6.x.

    Conecta com webservices SEFAZ-AM para emissão, cancelamento e consulta
    de NF-e modelo 55 com assinatura digital certificado A1.
    """

    def __init__(self, config: NFeConfig):
        self.config = config
        self._uf_cod = _UF_COD.get(config.uf.upper(), "13")
        logger.info(
            f"NFeProvider inicializado - UF: {config.uf} "
            f"Ambiente: {'Produção' if config.ambiente == '1' else 'Homologação'}"
        )

    def _get_comunicacao(self) -> Any:
        """Cria instância ComunicacaoSefaz."""
        from pynfe.processamento.comunicacao import ComunicacaoSefaz

        return ComunicacaoSefaz(
            uf=self.config.uf,
            certificado=self.config.certificado_path,
            certificado_senha=self.config.certificado_senha,
            homologacao=(self.config.ambiente == "2"),
        )

    def _assinar_xml(self, xml_bytes: bytes) -> bytes:
        """Assina XML com certificado A1."""
        from pynfe.processamento.assinatura import AssinaturaA1

        assinatura = AssinaturaA1(
            certificado=self.config.certificado_path,
            senha=self.config.certificado_senha,
        )
        return assinatura.assinar(xml_bytes)

    async def emitir_nfe(self, nfe_data: dict[str, Any], nfe_id: UUID, numero: int) -> dict[str, Any]:
        """Emite NF-e na SEFAZ via PyNFe."""
        logger.info(f"Emitindo NF-e {numero} (ID: {nfe_id})")
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._emitir_sync, nfe_data, numero)
        except NFeError:
            raise
        except Exception as e:
            raise NFeError(
                f"Falha na emissão da NF-e: {str(e)}",
                code="EMISSION_ERROR",
                details={"nfe_id": str(nfe_id), "numero": numero},
            ) from e

    def _emitir_sync(self, nfe_data: dict[str, Any], numero: int) -> dict[str, Any]:
        import random

        from pynfe.entidades.fonte_dados import _fonte_dados
        from pynfe.processamento.serializacao import SerializacaoXML

        codigo_numerico = str(random.randint(10000000, 99999999))  # noqa: S311
        is_homolog = self.config.ambiente == "2"

        nota_fiscal, emitente, chave = _montar_nota_fiscal(nfe_data, numero, codigo_numerico, self.config.ambiente)

        # Serializa
        fonte = _fonte_dados
        fonte.limpar_dados()
        fonte.adicionar_objeto(emitente)
        fonte.adicionar_objeto(nota_fiscal)
        serializador = SerializacaoXML(fonte, homologacao=is_homolog)
        xml_bytes = serializador.exportar(retorna_string=False)

        # Assina
        xml_assinado = self._assinar_xml(xml_bytes)

        # Transmite
        comunicacao = self._get_comunicacao()
        resposta = comunicacao.autorizacao(modelo="nfe", nota_fiscal=xml_assinado, timeout=self.config.timeout_seconds)

        resp_text = resposta.text if hasattr(resposta, "text") else str(resposta)
        dados = _parse_sefaz_xml(resp_text)

        c_stat = dados.get("cStat", "")
        x_motivo = dados.get("xMotivo", "Sem resposta SEFAZ")

        if c_stat == "100":
            status = "autorizada"
        elif c_stat in ("110", "301", "302"):
            status = "denegada"
        elif c_stat and c_stat.startswith("2"):
            status = "rejeitada"
        else:
            status = "enviada"

        xml_str = xml_assinado.decode("utf-8") if isinstance(xml_assinado, bytes) else str(xml_assinado)

        logger.info(f"NF-e {numero}: [{c_stat}] {x_motivo}")
        return {
            "status": status,
            "chave_acesso": chave,
            "protocolo": dados.get("nProt", ""),
            "mensagem": f"[{c_stat}] {x_motivo}",
            "xml_autorizado": xml_str if status == "autorizada" else None,
            "pdf_danfe": None,
            "codigo_status": c_stat,
            "motivo": x_motivo,
            "data_autorizacao": dados.get("dhRecbto", datetime.now().isoformat()),
        }

    async def cancelar_nfe(self, chave_acesso: str, motivo: str, nfe_id: UUID) -> dict[str, Any]:
        """Cancela NF-e autorizada na SEFAZ."""
        logger.info(f"Cancelando NF-e {chave_acesso[:16]}...")
        if len(chave_acesso) != 44:
            raise NFeError("Chave de acesso deve ter 44 dígitos", code="INVALID_KEY")
        if len(motivo.strip()) < 15:
            raise NFeError("Motivo deve ter pelo menos 15 caracteres", code="INVALID_REASON")
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._cancelar_sync, chave_acesso, motivo)
        except NFeError:
            raise
        except Exception as e:
            raise NFeError(
                f"Falha no cancelamento: {str(e)}",
                code="CANCELLATION_ERROR",
                details={"chave_acesso": chave_acesso, "nfe_id": str(nfe_id)},
            ) from e

    def _cancelar_sync(self, chave_acesso: str, motivo: str) -> dict[str, Any]:
        from lxml import etree

        now = datetime.now()
        ns = "http://www.portalfiscal.inf.br/nfe"

        root = etree.Element(f"{{{ns}}}envEvento", versao="1.00")
        etree.SubElement(root, f"{{{ns}}}idLote").text = now.strftime("%Y%m%d%H%M%S")
        evento = etree.SubElement(root, f"{{{ns}}}evento", versao="1.00")
        inf = etree.SubElement(evento, f"{{{ns}}}infEvento")
        inf.set("Id", f"ID110111{chave_acesso}01")
        etree.SubElement(inf, f"{{{ns}}}cOrgao").text = self._uf_cod
        etree.SubElement(inf, f"{{{ns}}}tpAmb").text = self.config.ambiente
        etree.SubElement(inf, f"{{{ns}}}CNPJ").text = _EMITENTE["cnpj"]
        etree.SubElement(inf, f"{{{ns}}}chNFe").text = chave_acesso
        etree.SubElement(inf, f"{{{ns}}}dhEvento").text = now.strftime("%Y-%m-%dT%H:%M:%S-04:00")
        etree.SubElement(inf, f"{{{ns}}}tpEvento").text = "110111"
        etree.SubElement(inf, f"{{{ns}}}nSeqEvento").text = "1"
        etree.SubElement(inf, f"{{{ns}}}verEvento").text = "1.00"
        det = etree.SubElement(inf, f"{{{ns}}}detEvento", versao="1.00")
        etree.SubElement(det, f"{{{ns}}}descEvento").text = "Cancelamento"
        etree.SubElement(det, f"{{{ns}}}nProt").text = ""
        etree.SubElement(det, f"{{{ns}}}xJust").text = motivo[:255]

        xml_bytes = etree.tostring(root, xml_declaration=True, encoding="UTF-8")
        xml_assinado = self._assinar_xml(xml_bytes)

        comunicacao = self._get_comunicacao()
        resposta = comunicacao.evento(modelo="nfe", evento=xml_assinado)
        resp_text = resposta.text if hasattr(resposta, "text") else str(resposta)
        dados = _parse_sefaz_xml(resp_text)

        c_stat = dados.get("cStat", "")
        x_motivo = dados.get("xMotivo", "")
        logger.info(f"Cancelamento NF-e {chave_acesso[:16]}...: [{c_stat}] {x_motivo}")

        return {
            "status": "cancelada" if c_stat == "135" else "erro_cancelamento",
            "chave_acesso": chave_acesso,
            "protocolo": dados.get("nProt", ""),
            "mensagem": f"[{c_stat}] {x_motivo}",
            "data_cancelamento": now.isoformat(),
            "codigo_status": c_stat,
            "motivo_cancelamento": motivo,
        }

    async def consultar_status(self, chave_acesso: str) -> dict[str, Any]:
        """Consulta status atual da NF-e na SEFAZ."""
        if len(chave_acesso) != 44:
            raise NFeError("Chave de acesso deve ter 44 dígitos", code="INVALID_KEY")
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._consultar_sync, chave_acesso)
        except NFeError:
            raise
        except Exception as e:
            raise NFeError(f"Falha na consulta: {str(e)}", code="QUERY_ERROR") from e

    def _consultar_sync(self, chave_acesso: str) -> dict[str, Any]:
        comunicacao = self._get_comunicacao()
        resposta = comunicacao.consulta_nota(modelo="nfe", chave=chave_acesso)
        resp_text = resposta.text if hasattr(resposta, "text") else str(resposta)
        dados = _parse_sefaz_xml(resp_text)
        c_stat = dados.get("cStat", "")
        x_motivo = dados.get("xMotivo", "")
        status_map = {"100": "autorizada", "101": "cancelada", "110": "denegada"}
        return {
            "status": status_map.get(c_stat, "desconhecida"),
            "chave_acesso": chave_acesso,
            "protocolo": dados.get("nProt", ""),
            "data_autorizacao": dados.get("dhRecbto", ""),
            "codigo_status": c_stat,
            "descricao_status": x_motivo,
            "xml_disponivel": c_stat in ("100", "101"),
            "situacao": "CANCELADA" if c_stat == "101" else "NORMAL",
        }

    async def test_connection(self) -> dict[str, Any]:
        """Testa conexão com SEFAZ."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._status_sync)
        except Exception as e:
            raise NFeError(f"Falha na conexão com SEFAZ: {str(e)}", code="CONNECTION_ERROR") from e

    def _status_sync(self) -> dict[str, Any]:
        comunicacao = self._get_comunicacao()
        resposta = comunicacao.status_servico(modelo="nfe", timeout=self.config.timeout_seconds)
        resp_text = resposta.text if hasattr(resposta, "text") else str(resposta)
        dados = _parse_sefaz_xml(resp_text)
        c_stat = dados.get("cStat", "")
        x_motivo = dados.get("xMotivo", "Sem resposta")
        logger.info(f"Status SEFAZ {self.config.uf}: [{c_stat}] {x_motivo}")
        return {
            "conectado": True,
            "ambiente": "Homologação" if self.config.ambiente == "2" else "Produção",
            "uf": self.config.uf,
            "servico_ativo": c_stat == "107",
            "ultima_atualizacao": datetime.now().isoformat(),
            "versao_schema": dados.get("verAplic", "4.00"),
            "codigo_status": c_stat,
            "motivo": x_motivo,
            "tempo_medio_resposta": dados.get("tMed", "N/A"),
        }


def create_nfe_provider(
    certificado_path: str,
    certificado_senha: str,
    ambiente: str = "2",
    uf: str = "AM",
) -> NFeProvider:
    """Factory para criar instância do NFeProvider."""
    config = NFeConfig(
        certificado_path=certificado_path,
        certificado_senha=certificado_senha,
        ambiente=ambiente,
        uf=uf,
    )
    return NFeProvider(config)
