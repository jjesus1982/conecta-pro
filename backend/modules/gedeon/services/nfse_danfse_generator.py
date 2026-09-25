"""DANFSe — Documento Auxiliar da NFS-e, no leiaute v2.0 do Padrão Nacional (DGX AB1, 25/09/2026).

Por que este arquivo foi reescrito
----------------------------------
O que saía daqui antes era um resumo bonito com a marca da casa: PRESTADOR, TOMADOR, SERVIÇO,
DISCRIMINAÇÃO, VALORES (5 linhas) e a chave no rodapé. Comparado campo a campo com os **9
DANFSe que o próprio portal do fisco gerou** para esta empresa (agosto e setembro/2026, em
`uploads/_entrada/NFs/`), faltavam quatorze coisas, entre elas:

  · o **canhoto** («DATA CIENTIFICAÇÃO / IDENTIFICAÇÃO E ASSINATURA»);
  · o **QR Code** de verificação — medido no PDF do portal, ele aponta para
    `https://www.nfse.gov.br/ConsultaPublica?tpc=1&chave=<50 dígitos>`;
  · **número e série da DPS** e a data/hora dela (a NFS-e nasce de uma DPS; sem esses números
    a nota não se liga ao documento que a originou);
  · **ambiente gerador / tipo de ambiente / situação / finalidade**;
  · **endereço, IBGE, CEP, telefone e e-mail** do prestador e do tomador;
  · **código de tributação nacional e municipal, código da NBS e local da prestação**;
  · o bloco **TRIBUTAÇÃO MUNICIPAL (ISSQN)** com tipo de tributação, base, alíquota e retenção;
  · o bloco **TRIBUTAÇÃO FEDERAL** (IRRF, contribuição previdenciária, contribuições sociais);
  · o bloco **TRIBUTAÇÃO IBS/CBS** inteiro (CST, cClassTrib, base após exclusões, alíquotas e
    valores apurados) — que é o que a nota de 09/2026 já traz;
  · o total de **retenções** e o **valor líquido + IBS/CBS**.

A fonte do dado
---------------
O DANFSe é a representação da NFS-e assinada pelo fisco. Quando há XML, é dele que sai TUDO.
A tabela `nfse_emitidas_nacional` guarda 12 campos estruturados e **nenhum XML** — então o
DANFSe montado só com ela nasce com metade dos blocos vazios. Por isso `xml_nfse` passou a ser
uma coluna da tabela (DDL idempotente em `garantir_coluna_xml`) e a rota busca o XML no ADN
(`GET /nfse/{chave}`, leitura pura, mTLS) na primeira vez que alguém imprime a nota, guardando
depois. Campo que não existe sai como «-», que é exatamente o que o portal imprime.

`GET /nfse/DANFSe/{chave}` estava declarado no `ENDPOINTS` do manager nacional desde sempre e
**não é rota**: medido em 25/09/2026 contra a produção, devolve 404 `text/html` com a página do
IIS. O fisco não serve o PDF por API — serve o XML, e o PDF é desenhado aqui.
"""

from __future__ import annotations

import io
import re

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

from modules.crm.services import pdf_branding
from modules.fiscal.services.danfe_layout import (
    _CINZA,
    _F,
    _FB,
    _PRETO,
    _Folha,
    _quebrar,
    cep_br,
    digitos,
    doc_br,
    fone_br,
    num,
)

_NS = "{http://www.sped.fazenda.gov.br/nfse}"
_TRACO = "-"

#: URL do QR Code do DANFSe — MEDIDA, não suposta: o QR do PDF que o portal gerou para a
#: NFS-e 121 foi decodificado e é exatamente esta string.
QR_CONSULTA = "https://www.nfse.gov.br/ConsultaPublica?tpc=1&chave={chave}"

_SIMPLES = {"1": "Não optante", "2": "Optante - MEI", "3": "Optante - ME/EPP"}
_TRIB_ISSQN = {"1": "Operação Tributável", "2": "Exportação de Serviço", "3": "Não Incidência", "4": "Imunidade"}
_RET_ISSQN = {"1": "Não Retido", "2": "Retido pelo Tomador", "3": "Retido pelo Intermediário"}
_SITUACAO = {"100": "NFS-e Gerada", "101": "NFS-e Cancelada", "102": "NFS-e Substituída"}
_FINALIDADE = {"0": "NFS-e regular", "1": "NFS-e substituta", "2": "NFS-e emitida em contingência"}
#: Só o código 8 está MEDIDO (é o das notas desta empresa, lido do DANFSe do portal). O resto
#: da tabela de `tpRetPisCofins` não está no repositório — código sem descrição sai como código.
_RET_PISCOFINS = {"8": "8 - PIS/COFINS Não Retidos, CSLL Retido"}


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Leitura
# ─────────────────────────────────────────────────────────────────────────────────────────────
def _t(no, tag: str, padrao: str = "") -> str:
    if no is None:
        return padrao
    achado = no.find(f"{_NS}{tag}")
    return (achado.text or padrao).strip() if achado is not None and achado.text else padrao


def _acha(raiz, tag: str):
    return next(raiz.iter(f"{_NS}{tag}"), None)


def _data(v: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(v or ""))
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else (v or "")


def _data_hora(v: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})", str(v or ""))
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)} {m.group(4)}:{m.group(5)}:{m.group(6)}" if m else (v or "")


def _ctrib(v: str) -> str:
    """140101 → 14.01.01 (é como o portal imprime o código de tributação nacional)."""
    d = digitos(v)
    return f"{d[:2]}.{d[2:4]}.{d[4:]}" if len(d) == 6 else (d or "")


def _nbs(v: str) -> str:
    """120018900 → 1.2001.89.00."""
    d = digitos(v)
    return f"{d[0]}.{d[1:5]}.{d[5:7]}.{d[7:]}" if len(d) == 9 else (d or "")


def _ibge_cep(ibge: str, cep: str) -> str:
    i = digitos(ibge)
    fmt = f"{i[:2]}.{i[2:]}" if len(i) == 7 else i
    return " / ".join(x for x in (fmt, cep_br(cep)) if x) or _TRACO


def parse(xml: str) -> dict:  # noqa: PLR0915 — leitura linear de um leiaute
    """Todo o modelo do DANFSe v2.0 a partir da NFS-e assinada pelo fisco."""
    from defusedxml.ElementTree import fromstring as _parse  # noqa: PLC0415

    try:
        raiz = _parse(xml)
    except Exception:  # noqa: BLE001
        return {}
    inf = _acha(raiz, "infNFSe")
    if inf is None:
        return {}
    dps = _acha(raiz, "infDPS")
    emit = _acha(raiz, "emit")
    ender_emit = _acha(raiz, "enderNac") if emit is not None else None
    reg = _acha(raiz, "regTrib")
    toma = _acha(raiz, "toma")
    serv = _acha(raiz, "serv")
    cserv = _acha(raiz, "cServ")
    trib_mun = _acha(raiz, "tribMun")
    trib_fed = _acha(raiz, "tribFed")
    piscofins = _acha(raiz, "piscofins")
    ptrib = _acha(raiz, "pTotTrib")
    val_nfse = inf.find(f"{_NS}valores")
    ibs_raiz = inf.find(f"{_NS}IBSCBS")
    ibs_val = ibs_raiz.find(f"{_NS}valores") if ibs_raiz is not None else None
    tot_cibs = _acha(raiz, "totCIBS")
    ibs_dps = dps.find(f"{_NS}IBSCBS") if dps is not None else None
    gibscbs = _acha(raiz, "gIBSCBS")

    # o endereço do tomador vem em <end><endNac>… mas xLgr/nro/xBairro ficam fora do endNac
    end_toma = toma.find(f"{_NS}end") if toma is not None else None
    end_toma_nac = end_toma.find(f"{_NS}endNac") if end_toma is not None else None

    uf_ibs = ibs_val.find(f"{_NS}uf") if ibs_val is not None else None
    mun_ibs = ibs_val.find(f"{_NS}mun") if ibs_val is not None else None
    fed_ibs = ibs_val.find(f"{_NS}fed") if ibs_val is not None else None
    gibs = tot_cibs.find(f"{_NS}gIBS") if tot_cibs is not None else None
    gcbs = tot_cibs.find(f"{_NS}gCBS") if tot_cibs is not None else None

    ret_pc = _t(piscofins, "tpRetPisCofins")
    d = {
        "chave": digitos(inf.get("Id", "")),
        "numero": _t(inf, "nNFSe"),
        "municipio_emissao": _t(inf, "xLocEmi"),
        "amb_ger": _t(inf, "ambGer"),
        "tp_amb": _t(dps, "tpAmb"),
        "competencia": _data(_t(dps, "dCompet")),
        "emissao_dh": _data_hora(_t(inf, "dhProc")),
        "dps_numero": _t(dps, "nDPS"),
        "dps_serie": _t(dps, "serie"),
        "dps_emissao_dh": _data_hora(_t(dps, "dhEmi")),
        "situacao": _SITUACAO.get(_t(inf, "cStat"), _t(inf, "cStat")),
        "finalidade": _FINALIDADE.get(_t(ibs_dps, "finNFSe", "0"), "NFS-e regular"),
        "emitente_tipo": "Prestador",
        "prest_doc": doc_br(_t(emit, "CNPJ") or _t(emit, "CPF")),
        "prest_im": _t(emit, "IM").strip(),
        "prest_fone": fone_br(_t(emit, "fone")),
        "prest_nome": _t(emit, "xNome"),
        "prest_mun_uf": f"{_t(inf, 'xLocEmi')} / {_t(ender_emit, 'UF')}".strip(" /"),
        "prest_ibge_cep": _ibge_cep(_t(ender_emit, "cMun"), _t(ender_emit, "CEP")),
        "prest_end": ", ".join(
            x for x in (_t(ender_emit, "xLgr"), _t(ender_emit, "nro"), _t(ender_emit, "xBairro")) if x
        ),
        "prest_email": _t(emit, "email"),
        "prest_simples": _SIMPLES.get(_t(reg, "opSimpNac"), _TRACO),
        "prest_regime_sn": _t(reg, "regApTribSN") or _TRACO,
        "toma_doc": doc_br(_t(toma, "CNPJ") or _t(toma, "CPF")),
        "toma_im": _t(toma, "IM").strip() or _TRACO,
        "toma_fone": fone_br(_t(toma, "fone")) or _TRACO,
        "toma_nome": _t(toma, "xNome"),
        "toma_mun_uf": f"{_t(inf, 'xLocPrestacao')} / {_t(ender_emit, 'UF')}".strip(" /"),
        "toma_ibge_cep": _ibge_cep(_t(end_toma_nac, "cMun"), _t(end_toma_nac, "CEP")),
        "toma_end": ", ".join(x for x in (_t(end_toma, "xLgr"), _t(end_toma, "nro"), _t(end_toma, "xBairro")) if x),
        "toma_email": _t(toma, "email") or _TRACO,
        "serv_ctrib": f"{_ctrib(_t(cserv, 'cTribNac'))} / {_t(cserv, 'cTribMun') or _TRACO}",
        "serv_nbs": _nbs(_t(cserv, "cNBS")) or _TRACO,
        "serv_local": f"{_t(inf, 'xLocPrestacao')} / {_t(ender_emit, 'UF')}".strip(" /"),
        "serv_texto": _t(inf, "xTribNac"),
        "serv_desc": _t(cserv, "xDescServ"),
        "iss_tipo": _TRIB_ISSQN.get(_t(trib_mun, "tribISSQN"), _t(trib_mun, "tribISSQN") or _TRACO),
        "iss_mun": f"{_t(inf, 'xLocIncid')} / {_t(ender_emit, 'UF')}".strip(" /"),
        "iss_bc": _t(val_nfse, "vBC", "0"),
        "iss_aliq": _t(val_nfse, "pAliqAplic", "0"),
        "iss_ret": _RET_ISSQN.get(_t(trib_mun, "tpRetISSQN"), _TRACO),
        "iss_valor": _t(val_nfse, "vISSQN", "0"),
        "fed_irrf": _t(trib_fed, "vRetIRRF"),
        "fed_cp": _t(trib_fed, "vRetCP"),
        "fed_cs": _t(trib_fed, "vRetCSLL"),
        "fed_pis": _t(piscofins, "vPis"),
        "fed_cofins": _t(piscofins, "vCofins"),
        "fed_ret_desc": _RET_PISCOFINS.get(ret_pc, ret_pc or _TRACO),
        "ibs_cst": f"{_t(gibscbs, 'CST') or _TRACO} / {_t(gibscbs, 'cClassTrib') or _TRACO}",
        "ibs_ind_op": " / ".join(
            x
            for x in (
                _t(ibs_dps, "cIndOp"),
                _t(ibs_raiz, "cLocalidadeIncid"),
                _t(ibs_raiz, "xLocalidadeIncid"),
                _t(ender_emit, "UF"),
            )
            if x
        ),
        #: MEDIDO contra o DANFSe do portal (NFS-e 121): «Exclusões e Reduções da Base de Cálculo
        #: R$ 90,00» não é uma tag do XML — é `vServ - vBC(IBS)` (1.800,00 − 1.710,00). A tag
        #: `vCalcReeRepRes` vale 0,00 nessa mesma nota; imprimi-la seria mostrar 0 onde o fisco
        #: mostra 90.
        "ibs_exclusoes": _exclusoes(_t(_acha(raiz, "vServPrest"), "vServ", "0"), _t(ibs_val, "vBC")),
        "ibs_bc": _t(ibs_val, "vBC"),
        "ibs_aliq_uf": _t(uf_ibs, "pIBSUF"),
        "ibs_aliq_mun": _t(mun_ibs, "pIBSMun"),
        "ibs_ef_uf": _t(uf_ibs, "pAliqEfetUF"),
        "ibs_ef_mun": _t(mun_ibs, "pAliqEfetMun"),
        "ibs_val_uf": _t(gibs.find(f"{_NS}gIBSUFTot") if gibs is not None else None, "vIBSUF"),
        "ibs_val_mun": _t(gibs.find(f"{_NS}gIBSMunTot") if gibs is not None else None, "vIBSMun"),
        "ibs_total": _t(gibs, "vIBSTot"),
        "cbs_aliq": _t(fed_ibs, "pCBS"),
        "cbs_ef": _t(fed_ibs, "pAliqEfetCBS"),
        "cbs_valor": _t(gcbs, "vCBS"),
        "v_serv": _t(_acha(raiz, "vServPrest"), "vServ", "0"),
        "desc_incond": _t(_acha(raiz, "vDescIncond"), "vDescIncond"),
        "desc_cond": _t(_acha(raiz, "vDescCond"), "vDescCond"),
        "v_ret_total": _t(val_nfse, "vTotalRet", "0"),
        "v_liq": _t(val_nfse, "vLiq", "0"),
        "v_tot_nf_cibs": _t(tot_cibs, "vTotNF"),
        "inf_comp": _t(serv, "xInfComp") or _t(inf, "xInfComp"),
    }
    if ptrib is not None:
        d["inf_comp"] = ((d["inf_comp"] + "  ") if d["inf_comp"] else "") + (
            "Totais aproximados dos Tributos cfe. Lei nº 12.741/2012: "
            f"Federais: {num(_t(ptrib, 'pTotTribFed', '0'))} %; "
            f"Estaduais: {num(_t(ptrib, 'pTotTribEst', '0'))} %; "
            f"Municipais: {num(_t(ptrib, 'pTotTribMun', '0'))} %;"
        )
    return d


#: Todos os campos do leiaute v2.0. O modelo nasce COMPLETO e o que a origem não tem vira «-»:
#: um DANFSe com bloco faltando parece nota errada; com «-» parece nota sem aquele dado — que é
#: o que ele é, e é o que o portal imprime.
CAMPOS_V2 = (
    "chave",
    "numero",
    "municipio_emissao",
    "amb_ger",
    "tp_amb",
    "competencia",
    "emissao_dh",
    "dps_numero",
    "dps_serie",
    "dps_emissao_dh",
    "situacao",
    "finalidade",
    "emitente_tipo",
    "prest_doc",
    "prest_im",
    "prest_fone",
    "prest_nome",
    "prest_mun_uf",
    "prest_ibge_cep",
    "prest_end",
    "prest_email",
    "prest_simples",
    "prest_regime_sn",
    "toma_doc",
    "toma_im",
    "toma_fone",
    "toma_nome",
    "toma_mun_uf",
    "toma_ibge_cep",
    "toma_end",
    "toma_email",
    "serv_ctrib",
    "serv_nbs",
    "serv_local",
    "serv_texto",
    "serv_desc",
    "iss_tipo",
    "iss_mun",
    "iss_bc",
    "iss_aliq",
    "iss_ret",
    "iss_valor",
    "fed_irrf",
    "fed_cp",
    "fed_cs",
    "fed_pis",
    "fed_cofins",
    "fed_ret_desc",
    "ibs_cst",
    "ibs_ind_op",
    "ibs_exclusoes",
    "ibs_bc",
    "ibs_aliq_uf",
    "ibs_aliq_mun",
    "ibs_ef_uf",
    "ibs_ef_mun",
    "ibs_val_uf",
    "ibs_val_mun",
    "ibs_total",
    "cbs_aliq",
    "cbs_ef",
    "cbs_valor",
    "v_serv",
    "desc_incond",
    "desc_cond",
    "v_ret_total",
    "v_liq",
    "v_tot_nf_cibs",
    "inf_comp",
)


def _exclusoes(v_serv: str, v_bc_ibs: str) -> str:
    from decimal import Decimal  # noqa: PLC0415

    if not str(v_bc_ibs or "").strip():
        return ""
    try:
        return str(Decimal(str(v_serv or 0)) - Decimal(str(v_bc_ibs)))
    except Exception:  # noqa: BLE001
        return ""


def _vazio(base: dict) -> dict:
    """Modelo com todos os campos do v2.0; o que a origem não tem fica «-», como no portal."""
    return {k: base.get(k, "") for k in CAMPOS_V2}


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Entradas públicas (mesmas assinaturas de antes — kits, portais e a rota do fiscal usam estas)
# ─────────────────────────────────────────────────────────────────────────────────────────────
def gerar_danfse_pdf(xml: str) -> bytes:
    """DANFSe a partir do XML oficial — o caminho completo, com todos os blocos do v2.0."""
    return _render_danfse(_vazio(parse(xml)))


def gerar_danfse_de_emitida(row: dict) -> bytes:
    """DANFSe da NFS-e EMITIDA (`nfse_emitidas_nacional`).

    Se a linha já tem o XML guardado, é ele que manda — o resto da linha é ignorado, porque o
    XML é a nota que o fisco assinou. Sem XML, sai o que os 12 campos estruturados permitem e
    os blocos que dependem do XML saem «-». O DANFSe sem XML não é um DANFSe pela metade por
    descuido: é um DANFSe que declara o que não sabe.
    """
    if row.get("xml_nfse"):
        cheio = parse(str(row["xml_nfse"]))
        if cheio:
            return _render_danfse(_vazio(cheio))

    def dt(v) -> str:
        try:
            return v.strftime("%d/%m/%Y %H:%M:%S")
        except Exception:  # noqa: BLE001
            return str(v or "")

    comp = str(row.get("competencia") or "")
    if len(comp) == 7 and "-" in comp:
        ano, mes = comp.split("-")
        comp = f"{mes}/{ano}"
    serv = float(row.get("valor_servicos") or 0)
    liq = float(row.get("valor_liquido") or 0)
    return _render_danfse(
        _vazio(
            {
                "chave": str(row.get("chave_acesso") or ""),
                "numero": str(row.get("numero") or ""),
                "municipio_emissao": "Manaus",
                "competencia": comp,
                "emissao_dh": dt(row.get("data_emissao")),
                "situacao": "NFS-e Cancelada" if row.get("cancelada") else "NFS-e Gerada",
                "finalidade": "NFS-e regular",
                "emitente_tipo": "Prestador",
                "prest_doc": doc_br(row.get("emit_cnpj")),
                "prest_im": str(row.get("emit_im") or ""),
                "prest_nome": str(row.get("emit_nome") or ""),
                "toma_doc": doc_br(row.get("tomador_cnpj")),
                "toma_nome": str(row.get("tomador_nome") or ""),
                "serv_ctrib": _ctrib(row.get("codigo_servico")),
                "serv_desc": str(row.get("descricao") or ""),
                "iss_bc": serv,
                "iss_aliq": row.get("iss_aliquota") or 0,
                "iss_valor": row.get("iss_valor") or 0,
                "v_serv": serv,
                "v_ret_total": max(serv - liq, 0),
                "v_liq": liq,
            }
        )
    )


def gerar_danfse_de_nfse(row: dict) -> bytes:
    """DANFSe da tabela `nfses` (NFS-e de ENTRADA / histórico), quando não há XML guardado."""
    if row.get("xml_raw"):
        cheio = parse(str(row["xml_raw"]))
        if cheio:
            return _render_danfse(_vazio(cheio))

    def dt(v) -> str:
        try:
            return v.strftime("%d/%m/%Y")
        except Exception:  # noqa: BLE001
            return str(v or "")

    serv = float(row.get("valor_servicos") or 0)
    ded = float(row.get("valor_deducoes") or 0)
    iss = float(row.get("iss_valor") or 0)
    inss = float(row.get("inss_valor") or 0)
    return _render_danfse(
        _vazio(
            {
                "chave": str(row.get("codigo_verificacao") or ""),
                "numero": str(row.get("numero_nfse") or row.get("numero_rps") or ""),
                "municipio_emissao": str(row.get("tomador_municipio") or "Manaus"),
                "competencia": dt(row.get("data_competencia")),
                "emissao_dh": dt(row.get("data_emissao")),
                "situacao": "NFS-e Gerada",
                "emitente_tipo": "Prestador",
                "prest_doc": doc_br(row.get("prestador_cnpj")),
                "prest_im": str(row.get("prestador_inscricao_municipal") or ""),
                "prest_nome": str(row.get("prestador_razao_social") or ""),
                "toma_doc": doc_br(row.get("tomador_cpf_cnpj")),
                "toma_nome": str(row.get("tomador_razao_social") or ""),
                "serv_ctrib": _ctrib(row.get("codigo_servico")),
                "serv_desc": str(row.get("discriminacao") or row.get("descricao_servico") or ""),
                "iss_bc": serv - ded,
                "iss_valor": iss,
                "v_serv": serv,
                "v_ret_total": iss + inss,
                "v_liq": serv - iss - inss,
            }
        )
    )


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Desenho — leiaute DANFSe v2.0
# ─────────────────────────────────────────────────────────────────────────────────────────────
def _v(x) -> str:
    """Campo ausente vira «-», que é como o portal imprime o que não existe na nota."""
    s = "" if x is None else str(x).strip()
    return s or _TRACO


def _m(x) -> str:
    """Valor em reais; ausente vira «-» (e não «R$ 0,00», que seria inventar um zero)."""
    if x is None or str(x).strip() == "":
        return _TRACO
    return f"R$ {num(x)}"


def _p(x) -> str:
    if x is None or str(x).strip() == "":
        return _TRACO
    return f"{num(x)} %"


def _render_danfse(d: dict) -> bytes:  # noqa: PLR0915 — é um leiaute, é linear
    from reportlab.pdfgen import canvas as _canvas  # noqa: PLC0415

    buf = io.BytesIO()
    c = _canvas.Canvas(buf, pagesize=A4, pageCompression=0)
    c.setTitle(f"DANFSe {d.get('numero') or ''}")
    f = _Folha(c, A4, margem=8 * mm)

    _canhoto(f, d)
    _cabecalho(f, d)

    f.campos(
        [
            (0.17, "Número da NFS-e", _v(d["numero"]), "e"),
            (0.17, "Competência da NFS-e", _v(d["competencia"]), "e"),
            (0.24, "Data e hora da emissão da NFS-e", _v(d["emissao_dh"]), "e"),
            (0.13, "Número da DPS", _v(d["dps_numero"]), "e"),
            (0.11, "Série da DPS", _v(d["dps_serie"]), "e"),
            (0.18, "Data e hora da emissão da DPS", _v(d["dps_emissao_dh"]), "e"),
        ],
        altura=6.8 * mm,
    )
    f.campos(
        [
            (0.34, "Emitente da NFS-e", _v(d["emitente_tipo"]), "e"),
            (0.33, "Situação da NFS-e", _v(d["situacao"]), "e"),
            (0.33, "Finalidade", _v(d["finalidade"]), "e"),
        ],
        altura=6.8 * mm,
    )

    _parte(
        f,
        "Prestador / Fornecedor",
        d,
        "prest",
        extra=[
            ("Simples Nacional na data de competência", _v(d["prest_simples"])),
            ("Regime de apuração tributária pelo SN", _v(d["prest_regime_sn"])),
        ],
    )
    _parte(f, "Tomador / Adquirente", d, "toma")
    _linha_aviso(f, "DESTINATÁRIO DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e")
    _linha_aviso(f, "INTERMEDIÁRIO DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e")

    f.faixa("Serviço prestado")
    f.campos(
        [
            (0.34, "Código de tributação nacional / municipal", _v(d["serv_ctrib"]), "e"),
            (0.33, "Código da NBS", _v(d["serv_nbs"]), "e"),
            (0.33, "Local da prestação / sigla UF", _v(d["serv_local"]), "e"),
        ],
        altura=6.8 * mm,
    )
    _texto(f, "", d["serv_texto"], linhas=2)
    _texto(f, "Descrição do serviço", d["serv_desc"], linhas=3)

    f.faixa("Tributação municipal (ISSQN)")
    f.campos(
        [
            (0.22, "Tipo de tributação do ISSQN", _v(d["iss_tipo"]), "e"),
            (0.20, "Município / UF de incidência", _v(d["iss_mun"]), "e"),
            (0.15, "BC ISSQN", _m(d["iss_bc"]), "d"),
            (0.13, "Alíquota aplicada", _p(d["iss_aliq"]), "d"),
            (0.15, "Retenção do ISSQN", _v(d["iss_ret"]), "e"),
            (0.15, "ISSQN apurado", _m(d["iss_valor"]), "d"),
        ],
        altura=6.8 * mm,
    )

    f.faixa("Tributação federal (exceto CBS)")
    f.campos(
        [
            (0.14, "IRRF", _m(d["fed_irrf"]), "d"),
            (0.19, "Contrib. previdenciária retida", _m(d["fed_cp"]), "d"),
            (0.17, "Contribuições sociais retidas", _m(d["fed_cs"]), "d"),
            (0.15, "PIS - débito próprio", _m(d["fed_pis"]), "d"),
            (0.15, "COFINS - débito próprio", _m(d["fed_cofins"]), "d"),
            (0.20, "Descr. contrib. sociais retidas", _v(d["fed_ret_desc"]), "e"),
        ],
        altura=6.8 * mm,
    )

    if digitos(d.get("ibs_bc")) or digitos(d.get("cbs_valor")):
        f.faixa("Tributação IBS / CBS")
        f.campos(
            [
                (0.20, "CST / cClassTrib", _v(d["ibs_cst"]), "e"),
                (0.42, "Indic. operação / IBGE / município / UF", _v(d["ibs_ind_op"]), "e"),
                (0.19, "Exclusões e reduções da BC", _m(d["ibs_exclusoes"]), "d"),
                (0.19, "BC após exclusões e reduções", _m(d["ibs_bc"]), "d"),
            ],
            altura=6.8 * mm,
        )
        f.campos(
            [
                (0.16, "Alíquota IBS UF / mun", f"{_p(d['ibs_aliq_uf'])} / {_p(d['ibs_aliq_mun'])}", "e"),
                (0.14, "Alíq. efet. estadual IBS", _p(d["ibs_ef_uf"]), "d"),
                (0.14, "Val. apurado estadual IBS", _m(d["ibs_val_uf"]), "d"),
                (0.14, "Val. apurado munic. IBS", _m(d["ibs_val_mun"]), "d"),
                (0.14, "Val. total apurado IBS", _m(d["ibs_total"]), "d"),
                (0.14, "Alíq. efetiva CBS", _p(d["cbs_ef"]), "d"),
                (0.14, "Val. total apurado CBS", _m(d["cbs_valor"]), "d"),
            ],
            altura=6.8 * mm,
        )

    f.faixa("Valor total da NFS-e")
    f.campos(
        [
            (0.20, "Valor da operação / serviço", _m(d["v_serv"]), "d"),
            (0.16, "Desconto incondicionado", _m(d["desc_incond"]), "d"),
            (0.16, "Desconto condicionado", _m(d["desc_cond"]), "d"),
            (0.24, "Total das retenções (ISSQN / federais)", _m(d["v_ret_total"]), "d"),
            (0.24, "Valor líquido da NFS-e", _m(d["v_liq"]), "d"),
        ],
        altura=6.8 * mm,
    )
    f.campos(
        [
            (0.50, "Total do IBS / CBS", _m(_soma(d.get("ibs_total"), d.get("cbs_valor"))), "d"),
            (0.50, "Valor líquido da NFS-e + IBS / CBS", _m(d["v_tot_nf_cibs"] or d["v_liq"]), "d"),
        ],
        altura=6.8 * mm,
    )

    _texto(f, "Informações complementares", d["inf_comp"], linhas=4, titulo_faixa=True)
    c.showPage()
    c.save()
    return buf.getvalue()


def _soma(a, b) -> str:
    vals = [x for x in (a, b) if str(x or "").strip()]
    if not vals:
        return ""
    from decimal import Decimal  # noqa: PLC0415

    return str(sum(Decimal(str(x)) for x in vals))


def _canhoto(f: _Folha, d: dict) -> None:
    c = f.c
    alt = 11 * mm
    lesq = f.larg * 0.58
    f.campos(
        [(0.42, "Data cientificação", "", "e"), (0.58, "Identificação e assinatura", "", "e")],
        altura=alt,
        y=f.y,
        x0=f.x0,
        larg=lesq,
    )
    c.setLineWidth(0.6)
    c.setStrokeColor(_PRETO)
    c.rect(f.x0 + lesq, f.y - alt, f.larg - lesq, alt, fill=0, stroke=1)
    c.setFont(_F, 5.0)
    c.setFillColor(_CINZA)
    c.drawString(f.x0 + lesq + 1.2 * mm, f.y - 2.4 * mm, "Nº NFS-e / CHAVE NFS-e")
    c.setFont(_FB, 6.4)
    c.setFillColor(_PRETO)
    c.drawString(
        f.x0 + lesq + 1.2 * mm,
        f.y - 7.0 * mm,
        f._encolher(f"{_v(d['numero'])} / {_v(d['chave'])}", f.larg - lesq - 2.4 * mm, _FB, 6.4),
    )
    f.y -= alt
    c.setDash(2, 2)
    c.setLineWidth(0.4)
    c.line(f.x0, f.y - 2 * mm, f.x1, f.y - 2 * mm)
    c.setDash()
    f.y -= 4.5 * mm


def _cabecalho(f: _Folha, d: dict) -> None:
    c = f.c
    alt = 26 * mm
    lesq = f.larg * 0.46
    topo = f.y
    c.setLineWidth(0.6)
    c.setStrokeColor(_PRETO)
    c.rect(f.x0, topo - alt, lesq, alt, fill=0, stroke=1)
    c.rect(f.x0 + lesq, topo - alt, f.larg - lesq, alt, fill=0, stroke=1)

    x = f.x0 + 2 * mm
    if pdf_branding._desenha_logo_cheia(c, x, topo - 9.5 * mm, largura=26 * mm, altura=9 * mm):
        x += 29 * mm
    c.setFillColor(_PRETO)
    c.setFont(_FB, 12)
    c.drawString(x, topo - 6.4 * mm, "DANFSe v2.0")
    c.setFont(_F, 6.4)
    c.drawString(x, topo - 9.6 * mm, "Documento Auxiliar da NFS-e")
    c.setFont(_F, 6.4)
    c.drawString(f.x0 + 2 * mm, topo - 15.0 * mm, f"Município: {_v(d['municipio_emissao'])}")
    c.drawString(f.x0 + 2 * mm, topo - 18.4 * mm, f"Ambiente Gerador: {_v(d['amb_ger'])}")
    c.drawString(f.x0 + 2 * mm, topo - 21.8 * mm, f"Tipo de Ambiente: {_v(d['tp_amb'])}")

    xd = f.x0 + lesq
    largd = f.larg - lesq
    c.setFont(_F, 5.0)
    c.setFillColor(_CINZA)
    c.drawString(xd + 1.5 * mm, topo - 2.6 * mm, "CHAVE DE ACESSO DA NFS-e")
    c.setFont(_FB, 6.8)
    c.setFillColor(_PRETO)
    c.drawString(xd + 1.5 * mm, topo - 6.4 * mm, _v(d["chave"]))
    chave = digitos(d.get("chave"))
    if len(chave) == 50:
        _qrcode(c, QR_CONSULTA.format(chave=chave), xd + largd - 21 * mm, topo - 24 * mm, 19 * mm)
    c.setFont(_F, 5.4)
    c.setFillColor(_CINZA)
    for k, ln in enumerate(
        _quebrar(
            c,
            "A autenticidade desta NFS-e pode ser verificada pela leitura deste código QR ou "
            "pela consulta da chave de acesso no portal nacional da NFS-e.",
            largd - 25 * mm,
            _F,
            5.4,
        )[:4]
    ):
        c.drawString(xd + 1.5 * mm, topo - 10.6 * mm - k * 2.8 * mm, ln)
    f.y = topo - alt


def _qrcode(c, texto: str, x: float, y: float, lado: float) -> None:
    try:
        from reportlab.graphics import renderPDF  # noqa: PLC0415
        from reportlab.graphics.barcode.qr import QrCodeWidget  # noqa: PLC0415
        from reportlab.graphics.shapes import Drawing  # noqa: PLC0415

        qr = QrCodeWidget(texto)
        x0, y0, x1, y1 = qr.getBounds()
        dw = Drawing(lado, lado, transform=[lado / (x1 - x0), 0, 0, lado / (y1 - y0), 0, 0])
        dw.add(qr)
        renderPDF.draw(dw, c, x, y)
    except Exception:  # noqa: BLE001 — sem QR a chave por extenso ainda permite a consulta
        pass


def _parte(f: _Folha, titulo: str, d: dict, pref: str, extra: list | None = None) -> None:
    f.faixa(titulo)
    f.campos(
        [
            (0.34, "CNPJ / CPF / NIF", _v(d[f"{pref}_doc"]), "e"),
            (0.33, "Indicador municipal (inscrição)", _v(d[f"{pref}_im"]), "e"),
            (0.33, "Telefone", _v(d[f"{pref}_fone"]), "e"),
        ],
        altura=6.6 * mm,
    )
    f.campos(
        [
            (0.50, "Nome / nome empresarial", _v(d[f"{pref}_nome"]), "e"),
            (0.25, "Município / sigla UF", _v(d[f"{pref}_mun_uf"]), "e"),
            (0.25, "Código IBGE / CEP", _v(d[f"{pref}_ibge_cep"]), "e"),
        ],
        altura=6.6 * mm,
    )
    f.campos(
        [
            (0.62, "Endereço", _v(d[f"{pref}_end"]), "e"),
            (0.38, "E-mail", _v(d[f"{pref}_email"]), "e"),
        ],
        altura=6.6 * mm,
    )
    if extra:
        f.campos([(0.50, rot, val, "e") for rot, val in extra], altura=6.6 * mm)


def _linha_aviso(f: _Folha, texto: str) -> None:
    c = f.c
    alt = 4.4 * mm
    c.setLineWidth(0.5)
    c.setStrokeColor(_PRETO)
    c.rect(f.x0, f.y - alt, f.larg, alt, fill=0, stroke=1)
    c.setFont(_F, 5.6)
    c.setFillColor(_CINZA)
    c.drawCentredString((f.x0 + f.x1) / 2, f.y - 3.0 * mm, texto)
    f.y -= alt


def _texto(f: _Folha, rotulo: str, valor, linhas: int, titulo_faixa: bool = False) -> None:
    c = f.c
    if titulo_faixa:
        f.faixa(rotulo)
        rotulo = ""
    alt = (3.0 + linhas * 2.9) * mm
    c.setLineWidth(0.5)
    c.setStrokeColor(_PRETO)
    c.rect(f.x0, f.y - alt, f.larg, alt, fill=0, stroke=1)
    dy = 2.4 * mm
    if rotulo:
        c.setFont(_F, 5.0)
        c.setFillColor(_CINZA)
        c.drawString(f.x0 + 1.2 * mm, f.y - dy, rotulo.upper())
        dy += 2.8 * mm
    c.setFont(_F, 5.8)
    c.setFillColor(_PRETO)
    for k, ln in enumerate(_quebrar(c, str(valor or _TRACO), f.larg - 3 * mm, _F, 5.8)[:linhas]):
        c.drawString(f.x0 + 1.2 * mm, f.y - dy - k * 2.9 * mm, ln)
    f.y -= alt


# ─────────────────────────────────────────────────────────────────────────────────────────────
# A coluna que guarda o XML da nota emitida (DDL idempotente)
# ─────────────────────────────────────────────────────────────────────────────────────────────
async def garantir_coluna_xml(db) -> None:
    """`nfse_emitidas_nacional.xml_nfse` — a NFS-e assinada pelo fisco, guardada.

    Sem ela o DANFSe nasce com metade dos blocos «-», porque os 12 campos estruturados da
    tabela não contêm nem o endereço do tomador, nem a DPS, nem o IBS/CBS.
    """
    from sqlalchemy import text as _sql  # noqa: PLC0415

    await db.execute(_sql("ALTER TABLE nfse_emitidas_nacional ADD COLUMN IF NOT EXISTS xml_nfse TEXT"))
    await db.commit()
