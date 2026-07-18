"""
NF-e Produto — Controller
Emissão de Nota Fiscal Eletrônica (modelo 55) via SEFAZ-AM.

Endpoints:
  POST /fiscal/nfe/emitir           — emite NF-e, persiste em nfes + nfe_itens
  GET  /fiscal/nfe/listar           — lista NF-es do DB
  GET  /fiscal/nfe/{nfe_id}/status  — consulta status individual
  GET  /fiscal/nfe/sefaz-status     — status do serviço SEFAZ-AM

Certificado: /app/credentials/certificates/certificado.pfx (A1, valido ate 2027)
Emitente: CONECTAMAIS ELETRONICA LTDA — CNPJ 35710481000103 — IE 45177801 — CRT 1 — Manaus-AM
SEFAZ-AM (producao): nfe.sefaz.am.gov.br
"""

import logging
import secrets
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from lxml import etree
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nfe", tags=["NF-e Produto"])

# ---------------------------------------------------------------------------
# Constantes do emitente (CONECTAMAIS ELETRONICA LTDA)
# ---------------------------------------------------------------------------
EMITENTE_CNPJ = "35710481000103"
EMITENTE_RAZAO_SOCIAL = "CONECTAMAIS ELETRONICA LTDA"
EMITENTE_IE = "45177801"
EMITENTE_CRT = "3"  # Lucro Real / Regime Normal → CRT 3
EMITENTE_UF = "AM"
EMITENTE_COD_MUN = "1302603"  # Manaus
EMITENTE_MUNICIPIO = "Manaus"
EMITENTE_LOGRADOURO = "Avenida Constantino Nery"
EMITENTE_NUMERO = "3343"
EMITENTE_BAIRRO = "Chapada"
EMITENTE_CEP = "69050001"
EMITENTE_FONE = "9232212100"

NFE_NAMESPACE = "http://www.portalfiscal.inf.br/nfe"
NFE_VERSAO = "4.00"
NFE_MODELO = "55"
NFE_SERIE_PADRAO = 1
COD_UF_AM = "13"
COD_MUN_MANAUS = "1302603"

CERT_PATH = "/app/credentials/certificates/certificado.pfx"
import os

CERT_PASSWORD = os.getenv("CERTIFICATE_PASSWORD", "")  # senha só via env

# ---------------------------------------------------------------------------
# Schemas de entrada
# ---------------------------------------------------------------------------


class DestinatarioSchema(BaseModel):
    cpf_cnpj: str = Field(..., description="CPF ou CNPJ do destinatário (só números)")
    razao_social: str = Field(..., max_length=60)
    ie: str | None = Field(default=None, description="Inscrição Estadual ou ISENTO")
    email: str | None = None
    uf: str = Field(..., min_length=2, max_length=2, description="UF ex: AM")
    logradouro: str = Field(..., max_length=60)
    numero: str = Field(..., max_length=10)
    bairro: str = Field(..., max_length=60)
    municipio: str = Field(..., max_length=60)
    cod_municipio: str = Field(..., description="Código IBGE do município")
    cep: str = Field(..., description="CEP só dígitos")
    telefone: str | None = None
    ind_ie_dest: str = Field(default="9", description="1=contribuinte ICMS 2=isento 9=não contribuinte")


class ProdutoItemSchema(BaseModel):
    codigo: str = Field(..., max_length=60, description="Código interno do produto/serviço")
    descricao: str = Field(..., max_length=120)
    ncm: str = Field(..., description="NCM 8 dígitos")
    cfop: str = Field(..., description="CFOP 4 dígitos ex: 5933")
    unidade: str = Field(..., max_length=6, description="UN, HR, M2 etc")
    quantidade: Decimal = Field(..., gt=0)
    valor_unitario: Decimal = Field(..., gt=0)
    valor_desconto: Decimal = Field(default=Decimal("0"))
    # Tributação simplificada (Lucro Real — serviços segurança / ZFM)
    icms_cst: str = Field(default="40", description="CST ICMS ex: 40=Isento")
    icms_origem: str = Field(default="0", description="0=Nacional")
    pis_cst: str = Field(default="07", description="07=Operação isenta")
    cofins_cst: str = Field(default="07")
    produto_id: str | None = Field(default=None, description="UUID do produto no ERP")


class PagamentoSchema(BaseModel):
    forma: str = Field(default="15", description="01=Dinheiro 15=Boleto 99=Outros")
    valor: Decimal = Field(..., gt=0)


class NFEEmitirRequest(BaseModel):
    natureza_operacao: str = Field(default="PRESTACAO DE SERVICOS", max_length=60)
    finalidade: str = Field(default="1", description="1=Normal 2=Complementar 3=Ajuste 4=Devolução")
    destinatario: DestinatarioSchema
    produtos: list[ProdutoItemSchema] = Field(..., min_length=1, max_length=990)
    pagamento: PagamentoSchema
    modalidade_frete: str = Field(default="9", description="9=Sem frete")
    informacoes_complementares: str | None = Field(default=None, max_length=2000)
    is_zfm: bool = Field(default=True, description="True=Zona Franca de Manaus")
    suframa_destinatario: str | None = Field(default=None, description="Inscrição SUFRAMA 9 dígitos")
    serie: int = Field(default=NFE_SERIE_PADRAO)
    # empresa_id referencia no ERP (mapeia para condominio_id no DB)
    empresa_id: str | None = Field(default=None, description="UUID da empresa emitente no ERP")


# ---------------------------------------------------------------------------
# Helpers: chave de acesso e XML
# ---------------------------------------------------------------------------


def _calcular_dv_modulo11(chave43: str) -> int:
    """Calcula o dígito verificador (módulo 11) para chave NF-e."""
    pesos = list(range(2, 10)) * 6  # pesos 2-9 ciclicos
    soma = sum(int(d) * p for d, p in zip(reversed(chave43), pesos, strict=False))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def _gerar_chave(
    cnpj: str,
    serie: int,
    numero: int,
    cod_uf: str = COD_UF_AM,
    mod: str = NFE_MODELO,
    tp_emis: str = "1",
) -> tuple[str, str]:
    """
    Gera chave de acesso NF-e (44 dígitos) e cNF (8 dígitos).
    Retorna (chave44, cNF8).
    """
    now = datetime.now()
    aa = now.strftime("%y")
    mm = now.strftime("%m")
    c_nf = str(10000000 + secrets.randbelow(90000000))  # 8 dígitos (não criptográfico, mas aceito)
    chave43 = f"{cod_uf:0>2}{aa}{mm}{cnpj:0>14}{mod:0>2}{serie:0>3}{numero:0>9}{tp_emis}{c_nf:0>8}"
    dv = _calcular_dv_modulo11(chave43)
    return chave43 + str(dv), c_nf


def _prox_numero(serie: int) -> int:
    """Número sequencial simples baseado em timestamp + random para evitar colisões."""
    import time

    ts = int(time.time()) % 1_000_000_000
    return (ts % 999_999_999) + 1


def _gerar_xml_nfe(
    chave: str,
    c_nf: str,
    numero: int,
    serie: int,
    request: NFEEmitirRequest,
) -> etree._Element:
    """
    Gera elemento lxml com NF-e layout 4.0 (antes da assinatura).
    """
    ns = NFE_NAMESPACE
    now = datetime.now(tz=UTC).astimezone()
    dh_emis = now.strftime("%Y-%m-%dT%H:%M:%S") + now.strftime("%z")[:3] + ":" + now.strftime("%z")[3:]
    dh_saida = dh_emis  # saída na mesma hora para serviços

    dest = request.destinatario

    # UF destino (1=interna, 2=interestadual, 3=exterior)
    id_dest = "1" if dest.uf == EMITENTE_UF else "2"
    ind_final = "1"  # consumidor final (serviços de segurança)
    ind_pres = "1"  # presencial (padrão)

    # ----------------------------------------------------------------
    # Raiz NFe
    # ----------------------------------------------------------------
    nfe = etree.Element("NFe", xmlns=ns)
    inf = etree.SubElement(nfe, "infNFe")
    inf.set("Id", f"NFe{chave}")
    inf.set("versao", NFE_VERSAO)

    # ---- ide --------------------------------------------------------
    ide = etree.SubElement(inf, "ide")
    etree.SubElement(ide, "cUF").text = COD_UF_AM
    etree.SubElement(ide, "cNF").text = c_nf
    etree.SubElement(ide, "natOp").text = request.natureza_operacao[:60]
    etree.SubElement(ide, "mod").text = NFE_MODELO
    etree.SubElement(ide, "serie").text = str(serie)
    etree.SubElement(ide, "nNF").text = str(numero)
    etree.SubElement(ide, "dhEmi").text = dh_emis
    etree.SubElement(ide, "dhSaiEnt").text = dh_saida
    etree.SubElement(ide, "tpNF").text = "1"  # 1=saída
    etree.SubElement(ide, "idDest").text = id_dest
    etree.SubElement(ide, "cMunFG").text = COD_MUN_MANAUS
    etree.SubElement(ide, "tpImp").text = "1"  # 1=DANFE retrato
    etree.SubElement(ide, "tpEmis").text = "1"  # 1=normal
    etree.SubElement(ide, "cDV").text = chave[-1]
    etree.SubElement(ide, "tpAmb").text = "1"  # 1=produção
    etree.SubElement(ide, "finNFe").text = request.finalidade
    etree.SubElement(ide, "indFinal").text = ind_final
    etree.SubElement(ide, "indPres").text = ind_pres
    etree.SubElement(ide, "procEmi").text = "3"  # 3=app próprio
    etree.SubElement(ide, "verProc").text = "2.0.0"

    # ---- emit -------------------------------------------------------
    emit = etree.SubElement(inf, "emit")
    etree.SubElement(emit, "CNPJ").text = EMITENTE_CNPJ
    etree.SubElement(emit, "xNome").text = EMITENTE_RAZAO_SOCIAL
    end_emit = etree.SubElement(emit, "enderEmit")
    etree.SubElement(end_emit, "xLgr").text = EMITENTE_LOGRADOURO
    etree.SubElement(end_emit, "nro").text = EMITENTE_NUMERO
    etree.SubElement(end_emit, "xBairro").text = EMITENTE_BAIRRO
    etree.SubElement(end_emit, "cMun").text = EMITENTE_COD_MUN
    etree.SubElement(end_emit, "xMun").text = EMITENTE_MUNICIPIO
    etree.SubElement(end_emit, "UF").text = EMITENTE_UF
    etree.SubElement(end_emit, "CEP").text = EMITENTE_CEP
    etree.SubElement(end_emit, "cPais").text = "1058"
    etree.SubElement(end_emit, "xPais").text = "Brasil"
    etree.SubElement(end_emit, "fone").text = EMITENTE_FONE
    etree.SubElement(emit, "IE").text = EMITENTE_IE
    etree.SubElement(emit, "CRT").text = EMITENTE_CRT

    # ---- dest -------------------------------------------------------
    dest_el = etree.SubElement(inf, "dest")
    cpf_cnpj = "".join(c for c in dest.cpf_cnpj if c.isdigit())
    if len(cpf_cnpj) == 14:
        etree.SubElement(dest_el, "CNPJ").text = cpf_cnpj
    else:
        etree.SubElement(dest_el, "CPF").text = cpf_cnpj
    etree.SubElement(dest_el, "xNome").text = dest.razao_social[:60]
    end_dest = etree.SubElement(dest_el, "enderDest")
    etree.SubElement(end_dest, "xLgr").text = dest.logradouro[:60]
    etree.SubElement(end_dest, "nro").text = dest.numero[:10]
    etree.SubElement(end_dest, "xBairro").text = dest.bairro[:60]
    etree.SubElement(end_dest, "cMun").text = dest.cod_municipio
    etree.SubElement(end_dest, "xMun").text = dest.municipio[:60]
    etree.SubElement(end_dest, "UF").text = dest.uf
    etree.SubElement(end_dest, "CEP").text = "".join(c for c in dest.cep if c.isdigit())
    etree.SubElement(end_dest, "cPais").text = "1058"
    etree.SubElement(end_dest, "xPais").text = "Brasil"
    if dest.telefone:
        etree.SubElement(end_dest, "fone").text = "".join(c for c in dest.telefone if c.isdigit())[:14]
    etree.SubElement(dest_el, "indIEDest").text = dest.ind_ie_dest
    if dest.ie and dest.ie.upper() not in ("ISENTO", ""):
        etree.SubElement(dest_el, "IE").text = dest.ie
    elif dest.ind_ie_dest == "2":
        etree.SubElement(dest_el, "IE").text = "ISENTO"
    if dest.email:
        etree.SubElement(dest_el, "email").text = dest.email[:60]

    # ---- det[] ------------------------------------------------------
    val_total_prod = Decimal("0")
    val_total_icms = Decimal("0")
    val_total_pis = Decimal("0")
    val_total_cofins = Decimal("0")
    val_total_desc = Decimal("0")

    for idx, item in enumerate(request.produtos, start=1):
        det = etree.SubElement(inf, "det")
        det.set("nItem", str(idx))

        prod = etree.SubElement(det, "prod")
        etree.SubElement(prod, "cProd").text = item.codigo[:60]
        etree.SubElement(prod, "cEAN").text = "SEM GTIN"
        etree.SubElement(prod, "xProd").text = item.descricao[:120]
        etree.SubElement(prod, "NCM").text = "".join(c for c in item.ncm if c.isdigit())[:8]
        etree.SubElement(prod, "CFOP").text = item.cfop[:4]
        etree.SubElement(prod, "uCom").text = item.unidade[:6]
        etree.SubElement(prod, "qCom").text = f"{item.quantidade:.4f}"
        etree.SubElement(prod, "vUnCom").text = f"{item.valor_unitario:.4f}"
        val_bruto = (item.quantidade * item.valor_unitario).quantize(Decimal("0.01"))
        val_liq = (val_bruto - item.valor_desconto).quantize(Decimal("0.01"))
        etree.SubElement(prod, "vProd").text = f"{val_bruto:.2f}"
        etree.SubElement(prod, "cEANTrib").text = "SEM GTIN"
        etree.SubElement(prod, "uTrib").text = item.unidade[:6]
        etree.SubElement(prod, "qTrib").text = f"{item.quantidade:.4f}"
        etree.SubElement(prod, "vUnTrib").text = f"{item.valor_unitario:.4f}"
        if item.valor_desconto > 0:
            etree.SubElement(prod, "vDesc").text = f"{item.valor_desconto:.2f}"
        etree.SubElement(prod, "indTot").text = "1"

        val_total_prod += val_bruto
        val_total_desc += item.valor_desconto

        imposto = etree.SubElement(det, "imposto")

        # ICMS (CST 40 = Isento para serviços ZFM / Lucro Real)
        icms_el = etree.SubElement(imposto, "ICMS")
        icms_cst_el = etree.SubElement(icms_el, f"ICMS{item.icms_cst}")
        etree.SubElement(icms_cst_el, "orig").text = item.icms_origem
        etree.SubElement(icms_cst_el, "CST").text = item.icms_cst

        # PIS
        pis_el = etree.SubElement(imposto, "PIS")
        pis_cst_code = item.pis_cst
        pis_tag = f"PIS{'NT' if pis_cst_code in ('07', '08', '09') else 'Aliq'}"
        pis_inner = etree.SubElement(pis_el, pis_tag)
        etree.SubElement(pis_inner, "CST").text = pis_cst_code
        if pis_tag == "PISAliq":
            etree.SubElement(pis_inner, "vBC").text = f"{val_liq:.2f}"
            etree.SubElement(pis_inner, "pPIS").text = "0.00"
            etree.SubElement(pis_inner, "vPIS").text = "0.00"

        # COFINS
        cof_el = etree.SubElement(imposto, "COFINS")
        cof_cst_code = item.cofins_cst
        cof_tag = f"COFINS{'NT' if cof_cst_code in ('07', '08', '09') else 'Aliq'}"
        cof_inner = etree.SubElement(cof_el, cof_tag)
        etree.SubElement(cof_inner, "CST").text = cof_cst_code
        if cof_tag == "COFINSAliq":
            etree.SubElement(cof_inner, "vBC").text = f"{val_liq:.2f}"
            etree.SubElement(cof_inner, "pCOFINS").text = "0.00"
            etree.SubElement(cof_inner, "vCOFINS").text = "0.00"

    # ---- total ------------------------------------------------------
    val_nf = (val_total_prod - val_total_desc).quantize(Decimal("0.01"))
    total = etree.SubElement(inf, "total")
    ice = etree.SubElement(total, "ICMSTot")
    etree.SubElement(ice, "vBC").text = "0.00"
    etree.SubElement(ice, "vICMS").text = f"{val_total_icms:.2f}"
    etree.SubElement(ice, "vICMSDeson").text = "0.00"
    etree.SubElement(ice, "vFCP").text = "0.00"
    etree.SubElement(ice, "vBCST").text = "0.00"
    etree.SubElement(ice, "vST").text = "0.00"
    etree.SubElement(ice, "vFCPST").text = "0.00"
    etree.SubElement(ice, "vFCPSTRet").text = "0.00"
    etree.SubElement(ice, "vProd").text = f"{val_total_prod:.2f}"
    etree.SubElement(ice, "vFrete").text = "0.00"
    etree.SubElement(ice, "vSeg").text = "0.00"
    etree.SubElement(ice, "vDesc").text = f"{val_total_desc:.2f}"
    etree.SubElement(ice, "vII").text = "0.00"
    etree.SubElement(ice, "vIPI").text = "0.00"
    etree.SubElement(ice, "vIPIDevol").text = "0.00"
    etree.SubElement(ice, "vPIS").text = f"{val_total_pis:.2f}"
    etree.SubElement(ice, "vCOFINS").text = f"{val_total_cofins:.2f}"
    etree.SubElement(ice, "vOutro").text = "0.00"
    etree.SubElement(ice, "vNF").text = f"{val_nf:.2f}"

    # ---- transp -----------------------------------------------------
    transp = etree.SubElement(inf, "transp")
    etree.SubElement(transp, "modFrete").text = request.modalidade_frete

    # ---- pag --------------------------------------------------------
    pag_el = etree.SubElement(inf, "pag")
    det_pag = etree.SubElement(pag_el, "detPag")
    etree.SubElement(det_pag, "tPag").text = request.pagamento.forma
    etree.SubElement(det_pag, "vPag").text = f"{request.pagamento.valor:.2f}"

    # ---- infAdic ----------------------------------------------------
    if request.informacoes_complementares or request.is_zfm:
        inf_adic = etree.SubElement(inf, "infAdic")
        obs_parts = []
        if request.is_zfm:
            obs_parts.append("PRODUTO/SERVICO COMERCIALIZADO NA ZONA FRANCA DE MANAUS. SUFRAMA: 210140500")
        if request.suframa_destinatario:
            obs_parts.append(f"SUFRAMA DESTINATARIO: {request.suframa_destinatario}")
        if request.informacoes_complementares:
            obs_parts.append(request.informacoes_complementares)
        obs_text = " | ".join(obs_parts)[:5000]
        etree.SubElement(inf_adic, "infCpl").text = obs_text

    # ---- infRespTec (obrigatório NF-e 4.0) -------------------------
    resp_tec = etree.SubElement(inf, "infRespTec")
    etree.SubElement(resp_tec, "CNPJ").text = EMITENTE_CNPJ  # CNPJ do desenvolvedor
    etree.SubElement(resp_tec, "xContato").text = "Jordan Santos de Jesus"
    etree.SubElement(resp_tec, "email").text = "financeiro@conectamais.pro"
    etree.SubElement(resp_tec, "fone").text = EMITENTE_FONE

    return nfe


def _assinar_nfe(nfe_element: etree._Element) -> etree._Element:
    """Assina NF-e com certificado A1 usando PyNFe."""
    from pynfe.processamento.assinatura import AssinaturaA1

    assinatura = AssinaturaA1(CERT_PATH, CERT_PASSWORD)
    return assinatura.assinar(nfe_element)


def _submeter_sefaz(nfe_signed: etree._Element, id_lote: int = 1) -> dict[str, Any]:
    """Envia NF-e assinada ao SEFAZ-AM. Retorna dict com resultado."""
    from pynfe.processamento.comunicacao import ComunicacaoSefaz

    sefaz = ComunicacaoSefaz(
        uf="AM",
        certificado=CERT_PATH,
        certificado_senha=CERT_PASSWORD,
        homologacao=False,  # produção
    )
    resultado = sefaz.autorizacao(
        modelo="nfe",
        nota_fiscal=nfe_signed,
        id_lote=id_lote,
        ind_sinc=1,  # síncrono
    )

    # resultado é (codigo, xml_ou_response[, nfe])
    codigo = resultado[0] if isinstance(resultado, tuple) else 1
    payload = resultado[1] if isinstance(resultado, tuple) else resultado
    NFE_NS = "http://www.portalfiscal.inf.br/nfe"

    if codigo == 0:
        # Sucesso: payload é etree._Element (nfeProc com NFe+protNFe)
        protocolo = None
        c_stat = None
        x_motivo = None
        dh_recbto = None
        try:
            prot_el = payload.find(f".//{{{NFE_NS}}}protNFe/{{{NFE_NS}}}infProt")
            if prot_el is not None:
                protocolo = prot_el.findtext(f"{{{NFE_NS}}}nProt")
                c_stat = prot_el.findtext(f"{{{NFE_NS}}}cStat")
                x_motivo = prot_el.findtext(f"{{{NFE_NS}}}xMotivo")
                dh_recbto = prot_el.findtext(f"{{{NFE_NS}}}dhRecbto")
        except Exception:
            pass
        return {
            "autorizada": True,
            "protocolo": protocolo,
            "c_stat": c_stat,
            "x_motivo": x_motivo,
            "dh_autorizacao": dh_recbto,
            "xml_autorizado": etree.tostring(payload, encoding="unicode"),
        }
    else:
        # Erro/Rejeição: payload pode ser requests.Response ou elemento lxml
        c_stat_err = ""
        x_motivo_err = ""
        protocolo_err = None
        dh_err = None
        try:
            if hasattr(payload, "content"):
                # Parsear o SOAP de resposta para encontrar infProt
                el = etree.fromstring(payload.content)  # noqa: S320
                # Tentar infProt primeiro (rejeição individual da NF-e)
                inf_prot = el.find(f".//{{{NFE_NS}}}infProt")
                if inf_prot is not None:
                    c_stat_err = inf_prot.findtext(f"{{{NFE_NS}}}cStat") or ""
                    x_motivo_err = inf_prot.findtext(f"{{{NFE_NS}}}xMotivo") or ""
                    protocolo_err = inf_prot.findtext(f"{{{NFE_NS}}}nProt")
                    dh_err = inf_prot.findtext(f"{{{NFE_NS}}}dhRecbto")
                else:
                    # fallback: cStat do retEnviNFe
                    c_stat_err = el.findtext(f".//{{{NFE_NS}}}cStat") or ""
                    x_motivo_err = el.findtext(f".//{{{NFE_NS}}}xMotivo") or ""
            else:
                x_motivo_err = etree.tostring(payload, encoding="unicode")[:500]
        except Exception as exc:
            x_motivo_err = str(exc)
        return {
            "autorizada": False,
            "protocolo": protocolo_err,
            "c_stat": c_stat_err,
            "x_motivo": x_motivo_err,
            "dh_autorizacao": dh_err,
            "xml_autorizado": None,
        }


def _text(el: etree._Element, tag: str, ns: dict) -> str | None:
    found = el.find(tag, ns)
    return found.text if found is not None else None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/sefaz-status", summary="Status do serviço SEFAZ-AM")
async def sefaz_status(_: CurrentActiveUser) -> dict[str, Any]:
    """Consulta status do WebService SEFAZ-AM (modelo 55)."""
    try:
        from pynfe.processamento.comunicacao import ComunicacaoSefaz

        sefaz = ComunicacaoSefaz(
            uf="AM",
            certificado=CERT_PATH,
            certificado_senha=CERT_PASSWORD,
            homologacao=False,
        )
        resp = sefaz.status_servico(modelo="nfe")
        el = etree.fromstring(resp.content)  # noqa: S320
        c_stat = el.find(".//{http://www.portalfiscal.inf.br/nfe}cStat")
        x_motivo = el.find(".//{http://www.portalfiscal.inf.br/nfe}xMotivo")
        dh = el.find(".//{http://www.portalfiscal.inf.br/nfe}dhRecbto")
        return {
            "sefaz_am": {
                "disponivel": resp.status_code == 200,
                "c_stat": c_stat.text if c_stat is not None else None,
                "x_motivo": x_motivo.text if x_motivo is not None else None,
                "dh_recbto": dh.text if dh is not None else None,
                "ambiente": "producao",
            },
            "certificado": {
                "path": CERT_PATH,
                "valido_ate": "2027-01-13",
                "emitente": EMITENTE_CNPJ,
            },
        }
    except Exception as exc:
        logger.error("Erro ao consultar status SEFAZ-AM: %s", exc)
        raise HTTPException(status_code=503, detail=f"SEFAZ-AM indisponível: {exc}")


@router.post(
    "/emitir",
    status_code=status.HTTP_201_CREATED,
    summary="Emite NF-e produto via SEFAZ-AM",
)
async def emitir_nfe(
    request: NFEEmitirRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Emite NF-e modelo 55 via SEFAZ-AM (produção).

    1. Gera chave de acesso e XML NF-e layout 4.00
    2. Assina com certificado A1 da CONECTAMAIS ELETRONICA LTDA
    3. Submete ao SEFAZ-AM em modo síncrono
    4. Persiste resultado em nfes + nfe_itens
    """
    # --- gerar numero sequencial ---
    r_num = await db.execute(
        text("SELECT COALESCE(MAX(numero), 0) + 1 FROM nfes WHERE serie = :s"),
        {"s": request.serie},
    )
    numero = r_num.scalar() or 1

    # --- gerar chave e XML ---
    chave, c_nf = _gerar_chave(
        cnpj=EMITENTE_CNPJ,
        serie=request.serie,
        numero=numero,
    )

    try:
        nfe_xml = _gerar_xml_nfe(chave, c_nf, numero, request.serie, request)
    except Exception as exc:
        logger.error("Erro gerando XML NF-e: %s", exc)
        raise HTTPException(status_code=422, detail=f"Erro gerando XML NF-e: {exc}")

    # --- assinar ---
    try:
        nfe_signed = _assinar_nfe(nfe_xml)
        xml_assinado = etree.tostring(nfe_signed, encoding="unicode")
    except Exception as exc:
        logger.error("Erro assinando NF-e: %s", exc)
        raise HTTPException(status_code=500, detail=f"Erro na assinatura digital: {exc}")

    # --- submeter SEFAZ ---
    nfe_id = str(uuid.uuid4())
    empresa_id = request.empresa_id or "00000000-0000-0000-0000-000000000001"
    status_nfe = "processando"
    resultado_sefaz: dict[str, Any] = {}

    try:
        resultado_sefaz = _submeter_sefaz(nfe_signed, id_lote=numero)
        status_nfe = "autorizada" if resultado_sefaz["autorizada"] else "rejeitada"
    except Exception as exc:
        logger.error("Erro comunicando com SEFAZ-AM: %s", exc)
        status_nfe = "erro_comunicacao"
        resultado_sefaz = {"x_motivo": str(exc), "autorizada": False}

    # --- calcular totais para persistir ---
    val_total_prod = sum((p.quantidade * p.valor_unitario).quantize(Decimal("0.01")) for p in request.produtos)
    val_total_desc = sum(p.valor_desconto for p in request.produtos)
    val_nf = (val_total_prod - val_total_desc).quantize(Decimal("0.01"))

    dest = request.destinatario
    cpf_cnpj_dest = "".join(c for c in dest.cpf_cnpj if c.isdigit())

    # --- persistir nfes ---
    protocolo = resultado_sefaz.get("protocolo")
    dh_aut = None
    if resultado_sefaz.get("dh_autorizacao"):
        try:
            dh_raw = datetime.fromisoformat(resultado_sefaz["dh_autorizacao"])
            # DB column is 'timestamp without time zone' — strip tz info
            dh_aut = dh_raw.replace(tzinfo=None)
        except Exception:
            dh_aut = None

    await db.execute(
        text("""
            INSERT INTO nfes (
                id, condominio_id, tipo, finalidade, status, serie, numero, chave_acesso,
                natureza_operacao, data_emissao,
                emitente_cnpj, emitente_razao_social, emitente_ie, emitente_uf, emitente_crt,
                destinatario_cpf_cnpj, destinatario_razao_social, destinatario_ie, destinatario_email,
                destinatario_uf, destinatario_logradouro, destinatario_numero,
                destinatario_bairro, destinatario_municipio, destinatario_cep, destinatario_telefone,
                modalidade_frete, forma_pagamento, meio_pagamento, valor_pagamento,
                valor_total_produtos, valor_total_icms, valor_total_ipi,
                valor_total_pis, valor_total_cofins, valor_total_frete,
                valor_total_seguro, valor_total_desconto, valor_total_outros, valor_total_nota,
                informacoes_complementares, is_zfm, suframa_destinatario,
                protocolo_autorizacao, data_autorizacao, motivo_rejeicao,
                xml_enviado, xml_autorizado, created_at, updated_at, active
            ) VALUES (
                CAST(:id AS uuid), CAST(:condo_id AS uuid), :tipo, :finalidade, :status,
                :serie, :numero, :chave_acesso,
                :nat_op, NOW(),
                :emit_cnpj, :emit_xnome, :emit_ie, :emit_uf, :emit_crt,
                :dest_cpf_cnpj, :dest_xnome, :dest_ie, :dest_email,
                :dest_uf, :dest_lgr, :dest_nro,
                :dest_bairro, :dest_mun, :dest_cep, :dest_fone,
                :mod_frete, :forma_pag, :meio_pag, :val_pag,
                :val_prod, 0, 0,
                0, 0, 0,
                0, :val_desc, 0, :val_nf,
                :inf_cpl, :is_zfm, :suframa,
                :protocolo, :dh_aut, :motivo_rej,
                :xml_env, :xml_aut, NOW(), NOW(), true
            )
        """),
        {
            "id": nfe_id,
            "condo_id": empresa_id,
            "tipo": "saida",
            "finalidade": request.finalidade,
            "status": status_nfe,
            "serie": request.serie,
            "numero": numero,
            "chave_acesso": chave,
            "nat_op": request.natureza_operacao[:60],
            "emit_cnpj": EMITENTE_CNPJ,
            "emit_xnome": EMITENTE_RAZAO_SOCIAL,
            "emit_ie": EMITENTE_IE,
            "emit_uf": EMITENTE_UF,
            "emit_crt": EMITENTE_CRT,
            "dest_cpf_cnpj": cpf_cnpj_dest,
            "dest_xnome": dest.razao_social[:60],
            "dest_ie": dest.ie or "",
            "dest_email": dest.email,
            "dest_uf": dest.uf,
            "dest_lgr": dest.logradouro[:60],
            "dest_nro": dest.numero[:10],
            "dest_bairro": dest.bairro[:60],
            "dest_mun": dest.municipio[:60],
            "dest_cep": "".join(c for c in dest.cep if c.isdigit()),
            "dest_fone": dest.telefone,
            "mod_frete": request.modalidade_frete,
            "forma_pag": request.pagamento.forma,
            "meio_pag": request.pagamento.forma,
            "val_pag": float(request.pagamento.valor),
            "val_prod": float(val_total_prod),
            "val_desc": float(val_total_desc),
            "val_nf": float(val_nf),
            "inf_cpl": request.informacoes_complementares,
            "is_zfm": request.is_zfm,
            "suframa": request.suframa_destinatario,
            "protocolo": protocolo,
            "dh_aut": dh_aut,
            "motivo_rej": resultado_sefaz.get("x_motivo") if not resultado_sefaz.get("autorizada") else None,
            "xml_env": xml_assinado,
            "xml_aut": resultado_sefaz.get("xml_autorizado"),
        },
    )

    # --- persistir nfe_itens ---
    for idx, item in enumerate(request.produtos, start=1):
        val_bruto = (item.quantidade * item.valor_unitario).quantize(Decimal("0.01"))
        await db.execute(
            text("""
                INSERT INTO nfe_itens (
                    id, nfe_id, numero_item, produto_id,
                    codigo_produto, descricao, ncm, cfop, unidade,
                    quantidade, valor_unitario, valor_total, valor_desconto,
                    valor_frete, valor_seguro, valor_outros,
                    icms_origem, icms_cst, icms_base_calculo, icms_aliquota, icms_valor,
                    pis_cst, pis_base_calculo, pis_aliquota, pis_valor,
                    cofins_cst, cofins_base_calculo, cofins_aliquota, cofins_valor,
                    created_at
                ) VALUES (
                    gen_random_uuid(), CAST(:nfe_id AS uuid), :n_item, CAST(:prod_id AS uuid),
                    :codigo, :descricao, :ncm, :cfop, :unidade,
                    :qtd, :v_unit, :v_total, :v_desc,
                    0, 0, 0,
                    :icms_orig, :icms_cst, 0, 0, 0,
                    :pis_cst, 0, 0, 0,
                    :cofins_cst, 0, 0, 0,
                    NOW()
                )
            """),
            {
                "nfe_id": nfe_id,
                "n_item": idx,
                "prod_id": item.produto_id,
                "codigo": item.codigo[:60],
                "descricao": item.descricao[:120],
                "ncm": "".join(c for c in item.ncm if c.isdigit())[:8],
                "cfop": item.cfop[:4],
                "unidade": item.unidade[:6],
                "qtd": float(item.quantidade),
                "v_unit": float(item.valor_unitario),
                "v_total": float(val_bruto),
                "v_desc": float(item.valor_desconto),
                "icms_orig": item.icms_origem,
                "icms_cst": item.icms_cst,
                "pis_cst": item.pis_cst,
                "cofins_cst": item.cofins_cst,
            },
        )

    await db.commit()

    return {
        "nfe_id": nfe_id,
        "chave_acesso": chave,
        "numero": numero,
        "serie": request.serie,
        "status": status_nfe,
        "protocolo": protocolo,
        "c_stat": resultado_sefaz.get("c_stat"),
        "x_motivo": resultado_sefaz.get("x_motivo"),
        "dh_autorizacao": resultado_sefaz.get("dh_autorizacao"),
        "valor_total": float(val_nf),
        "xml_assinado_gerado": True,
        "sefaz_am": "producao",
    }


@router.get("/listar", summary="Lista NF-es emitidas")
async def listar_nfes(
    _: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    limite: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    status_filtro: str | None = Query(default=None, alias="status"),
) -> dict[str, Any]:
    """Lista NF-es do banco de dados, mais recentes primeiro."""
    where = "WHERE active = true"
    params: dict[str, Any] = {"limite": limite, "offset": offset}
    if status_filtro:
        where += " AND status = :status_filtro"
        params["status_filtro"] = status_filtro

    r_total = await db.execute(text(f"SELECT COUNT(*) FROM nfes {where}"), params)
    total = r_total.scalar() or 0

    r_nfes = await db.execute(
        text(f"""
            SELECT id, chave_acesso, numero, serie, status, natureza_operacao,
                   destinatario_razao_social, destinatario_cpf_cnpj,
                   valor_total_nota, protocolo_autorizacao, data_emissao, data_autorizacao
            FROM nfes
            {where}
            ORDER BY data_emissao DESC
            LIMIT :limite OFFSET :offset
        """),
        params,
    )

    rows = r_nfes.fetchall()
    nfes = [
        {
            "id": str(r[0]),
            "chave_acesso": r[1],
            "numero": r[2],
            "serie": r[3],
            "status": r[4],
            "natureza_operacao": r[5],
            "destinatario": r[6],
            "destinatario_cpf_cnpj": r[7],
            "valor_total": float(r[8]) if r[8] else 0.0,
            "protocolo": r[9],
            "data_emissao": r[10].isoformat() if r[10] else None,
            "data_autorizacao": r[11].isoformat() if r[11] else None,
        }
        for r in rows
    ]

    return {"total": total, "limite": limite, "offset": offset, "nfes": nfes}


@router.get("/{nfe_id}/status", summary="Status de uma NF-e")
async def status_nfe(
    nfe_id: str,
    _: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retorna status detalhado de uma NF-e pelo ID interno."""
    r = await db.execute(
        text("""
            SELECT id, chave_acesso, numero, serie, status, natureza_operacao,
                   destinatario_razao_social, valor_total_nota, protocolo_autorizacao,
                   motivo_rejeicao, data_emissao, data_autorizacao, xml_autorizado
            FROM nfes WHERE id = CAST(:nfe_id AS uuid) AND active = true
        """),
        {"nfe_id": nfe_id},
    )
    row = r.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="NF-e não encontrada")

    # Itens
    r_itens = await db.execute(
        text("""
            SELECT numero_item, codigo_produto, descricao, quantidade, valor_unitario, valor_total
            FROM nfe_itens WHERE nfe_id = CAST(:nfe_id AS uuid) ORDER BY numero_item
        """),
        {"nfe_id": nfe_id},
    )
    itens = [
        {
            "item": r2[0],
            "codigo": r2[1],
            "descricao": r2[2],
            "quantidade": float(r2[3]) if r2[3] else 0,
            "valor_unitario": float(r2[4]) if r2[4] else 0,
            "valor_total": float(r2[5]) if r2[5] else 0,
        }
        for r2 in r_itens.fetchall()
    ]

    return {
        "id": str(row[0]),
        "chave_acesso": row[1],
        "numero": row[2],
        "serie": row[3],
        "status": row[4],
        "natureza_operacao": row[5],
        "destinatario": row[6],
        "valor_total": float(row[7]) if row[7] else 0.0,
        "protocolo": row[8],
        "motivo_rejeicao": row[9],
        "data_emissao": row[10].isoformat() if row[10] else None,
        "data_autorizacao": row[11].isoformat() if row[11] else None,
        "tem_xml_autorizado": bool(row[12]),
        "itens": itens,
    }
