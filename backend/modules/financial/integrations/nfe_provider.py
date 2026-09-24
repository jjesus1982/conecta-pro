"""NFeProvider — O emissor de NF-e modelo 55 (SEFAZ-AM) do Conecta PRO.

É o ÚNICO emissor da casa desde 24/09/2026 (DGX Z2). O concorrente
(`modules/fiscal_contabil/notas_fiscais/nfe/controller.py`, lxml à mão) foi
aposentado: tinha ZERO rotas, `tpAmb` chumbado em "1" (PRODUÇÃO) e numeração
por timestamp. A comparação medida está em `auditoria/frentes/DGX_Z2_emissor_nfe.md`.

Esta camada faz SÓ o diálogo com a SEFAZ: montar o leiaute, assinar com o A1 da
empresa certa, transmitir, ler o retorno. Numeração, persistência e guarda do XML
são de `modules/fiscal_contabil/notas_fiscais/nfe/emissor.py`.

A REGRA QUE NÃO SE QUEBRA
-------------------------
Nota em produção é documento fiscal irreversível. Toda transmissão passa por
`_exigir_ambiente()`: só sai com `tpAmb=1` se a env `NFE_PRODUCAO_LIBERADA`
estiver com o valor-senha exato (gate humano). E antes de cada POST o XML
serializado é RELIDO: se o `<tpAmb>` do XML não bater com o ambiente pedido,
nada é transmitido. Cinto e suspensório — o ambiente é medido no que vai no fio,
não no que o config diz.

Reforma tributária (NT 2025.002)
--------------------------------
A SEFAZ-AM rejeita 1115 "IBS/CBS nao informado" em HOMOLOGAÇÃO desde 01/07/2026.
PyNFe 0.6.5 é anterior à reforma e não serializa o grupo — `injetar_ibscbs()`
o acrescenta na árvore lxml ANTES da assinatura. Medido em 24/09/2026: sem ele,
rejeição 1115; com ele, cStat 100.
"""

import asyncio
import os
import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from core.logging import logger

NS_NFE = "http://www.portalfiscal.inf.br/nfe"

# Gate humano de produção. O valor é a frase inteira — env setada "1"/"true" NÃO abre.
_ENV_GATE_PRODUCAO = "NFE_PRODUCAO_LIBERADA"
_SENHA_GATE_PRODUCAO = "SIM_EU_SEI_O_QUE_ESTOU_FAZENDO"  # pragma: allowlist secret

# Textos que a SEFAZ exige em homologação (NT 2014.002). Sem eles: rejeição 610/9xx.
XPROD_HOMOLOGACAO = "NOTA FISCAL EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL"
XNOME_HOMOLOGACAO = "NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL"
CNPJ_DEST_HOMOLOGACAO = "99999999000191"

# Alíquotas da transição 2026 (LC 214/2025): IBS estadual 0,1%, municipal 0%, CBS 0,9%.
IBS_UF_2026 = "0.1000"
IBS_MUN_2026 = "0.0000"
CBS_2026 = "0.9000"


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


# Mapa UF → código IBGE (cUF da chave de acesso).
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


# ---------------------------------------------------------------------------
# A trava
# ---------------------------------------------------------------------------


def producao_liberada() -> bool:
    """True só quando o dono destravou produção na env, com a frase exata."""
    return os.getenv(_ENV_GATE_PRODUCAO, "") == _SENHA_GATE_PRODUCAO


def _exigir_ambiente(ambiente: str, operacao: str) -> None:
    """Toda ida à SEFAZ passa por aqui. Produção só com o gate humano aberto."""
    if ambiente == "2":
        return
    if ambiente != "1":
        raise NFeError(f"Ambiente NF-e inválido: {ambiente!r} (1=produção, 2=homologação)", code="AMBIENTE_INVALIDO")
    if not producao_liberada():
        raise NFeError(
            f"{operacao} em PRODUÇÃO bloqueada. Nota em produção é documento fiscal "
            f"irreversível (multa e obrigação acessória). Para liberar, defina a variável "
            f"de ambiente {_ENV_GATE_PRODUCAO} com o valor-senha combinado — decisão humana, "
            f"nunca automática.",
            code="PRODUCAO_TRAVADA",
        )


def _tp_amb_do_xml(xml: Any) -> list[str]:
    """Lê os <tpAmb> do que REALMENTE vai no fio (bytes ou árvore lxml)."""
    from lxml import etree

    if isinstance(xml, bytes | bytearray):
        bruto = bytes(xml)
    elif isinstance(xml, str):
        bruto = xml.encode("utf-8")
    else:
        bruto = etree.tostring(xml)
    return [m.decode() for m in re.findall(rb"<(?:\w+:)?tpAmb>(\d)</(?:\w+:)?tpAmb>", bruto)]


def _conferir_tp_amb(xml: Any, ambiente: str, operacao: str) -> None:
    """Cinto e suspensório: o ambiente é o que está no XML, não o que o config diz."""
    achados = set(_tp_amb_do_xml(xml))
    if not achados:
        raise NFeError(f"{operacao}: XML sem <tpAmb> — recuso transmitir às cegas.", code="TPAMB_AUSENTE")
    if achados != {ambiente}:
        raise NFeError(
            f"{operacao}: tpAmb do XML {sorted(achados)} difere do ambiente pedido ({ambiente}). Nada foi transmitido.",
            code="TPAMB_DIVERGENTE",
        )
    if achados == {"1"} and not producao_liberada():
        raise NFeError(f"{operacao}: XML em PRODUÇÃO sem o gate humano. Nada foi transmitido.", code="PRODUCAO_TRAVADA")


# ---------------------------------------------------------------------------
# Leiaute
# ---------------------------------------------------------------------------


def _parse_sefaz_xml(response_text: str) -> dict[str, str]:
    """Extrai campos da resposta da SEFAZ.

    Regex e não XPath de propósito: a SEFAZ-AM devolve o protNFe com prefixo
    (`<ns0:cStat>`) dentro de um nfeProc sem prefixo — medido em 24/09/2026, e foi
    o que fez o leitor anterior enxergar "" num retorno que era 100/Autorizado.
    O ÚLTIMO valor vence: numa resposta de lote, o do protNFe vem depois do 104.
    """
    result: dict[str, str] = {}
    if not response_text:
        return result
    for tag in ("cStat", "xMotivo", "chNFe", "nProt", "dhRecbto", "tpAmb", "verAplic", "cUF", "tMed", "nRec"):
        achados = re.findall(rf"<(?:\w+:)?{tag}>(.*?)</(?:\w+:)?{tag}>", response_text, re.DOTALL)
        if achados:
            result[tag] = achados[-1].strip()
            if len(achados) > 1:
                result[f"{tag}_todos"] = "|".join(a.strip() for a in achados)
    return result


def _calcular_dv_chave(chave_sem_dv: str) -> str:
    """Dígito verificador da chave NF-e (módulo 11, pesos 2..9 cíclicos da direita)."""
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(int(d) * pesos[i % len(pesos)] for i, d in enumerate(reversed(chave_sem_dv)))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def montar_chave(cnpj: str, uf: str, serie: int, numero: int, codigo_numerico: str, data: datetime) -> str:
    """Chave de acesso de 44 dígitos. Série e número ZERO-PADDED só aqui — nas tags
    <serie>/<nNF> o padding é rejeição 215 (medido)."""
    cnpj = re.sub(r"\D", "", cnpj).zfill(14)
    chave43 = (
        f"{_UF_COD.get(uf.upper(), '13')}{data:%y%m}{cnpj}55"
        f"{str(serie).zfill(3)}{str(numero).zfill(9)}1{codigo_numerico.zfill(8)}"
    )
    return chave43 + _calcular_dv_chave(chave43)


def _sub(pai, tag: str, texto: str | None = None):
    from lxml import etree

    el = etree.SubElement(pai, tag)
    if texto is not None:
        el.text = texto
    return el


def _q(valor: Decimal) -> str:
    return str(Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def injetar_ibscbs(raiz, p_ibs_uf: str = IBS_UF_2026, p_ibs_mun: str = IBS_MUN_2026, p_cbs: str = CBS_2026):
    """Acrescenta o grupo IBSCBS por item e o IBSCBSTot no total (NT 2025.002).

    A árvore que o PyNFe devolve ANTES da assinatura não tem namespace (o xmlns é
    atributo literal) — por isso as tags entram sem prefixo. Sem esta função a
    SEFAZ-AM rejeita 1115 desde 01/07/2026 em homologação.
    """
    tot_bc = tot_uf = tot_mun = tot_cbs = Decimal("0")
    for det in raiz.iter("det"):
        prod, imposto = det.find("prod"), det.find("imposto")
        if prod is None or imposto is None:
            continue
        vbc = Decimal(prod.findtext("vProd") or "0")
        v_uf = vbc * Decimal(p_ibs_uf) / 100
        v_mun = vbc * Decimal(p_ibs_mun) / 100
        v_cbs = vbc * Decimal(p_cbs) / 100
        g = _sub(imposto, "IBSCBS")
        _sub(g, "CST", "000")  # 000 = tributação integral
        _sub(g, "cClassTrib", "000001")
        gg = _sub(g, "gIBSCBS")
        _sub(gg, "vBC", _q(vbc))
        guf = _sub(gg, "gIBSUF")
        _sub(guf, "pIBSUF", p_ibs_uf)
        _sub(guf, "vIBSUF", _q(v_uf))
        gmu = _sub(gg, "gIBSMun")
        _sub(gmu, "pIBSMun", p_ibs_mun)
        _sub(gmu, "vIBSMun", _q(v_mun))
        _sub(gg, "vIBS", _q(v_uf + v_mun))
        gcb = _sub(gg, "gCBS")
        _sub(gcb, "pCBS", p_cbs)
        _sub(gcb, "vCBS", _q(v_cbs))
        tot_bc += vbc
        tot_uf += v_uf
        tot_mun += v_mun
        tot_cbs += v_cbs

    total = raiz.find(".//total")
    if total is None:
        raise NFeError("XML sem <total> — não dá para totalizar IBS/CBS.", code="XML_SEM_TOTAL")
    t = _sub(total, "IBSCBSTot")
    _sub(t, "vBCIBSCBS", _q(tot_bc))
    gi = _sub(t, "gIBS")
    guf = _sub(gi, "gIBSUF")
    _sub(guf, "vDif", "0.00")
    _sub(guf, "vDevTrib", "0.00")
    _sub(guf, "vIBSUF", _q(tot_uf))
    gmu = _sub(gi, "gIBSMun")
    _sub(gmu, "vDif", "0.00")
    _sub(gmu, "vDevTrib", "0.00")
    _sub(gmu, "vIBSMun", _q(tot_mun))
    _sub(gi, "vIBS", _q(tot_uf + tot_mun))
    _sub(gi, "vCredPres", "0.00")
    _sub(gi, "vCredPresCondSus", "0.00")
    gc = _sub(t, "gCBS")
    _sub(gc, "vDif", "0.00")
    _sub(gc, "vDevTrib", "0.00")
    _sub(gc, "vCBS", _q(tot_cbs))
    _sub(gc, "vCredPres", "0.00")
    _sub(gc, "vCredPresCondSus", "0.00")
    return raiz


_CAMPOS_EMITENTE = (
    ("cnpj", "CNPJ"),
    ("razao_social", "razão social"),
    ("inscricao_estadual", "inscrição estadual"),
    ("endereco_logradouro", "logradouro"),
    ("endereco_numero", "número"),
    ("endereco_bairro", "bairro"),
    ("endereco_cep", "CEP"),
    ("endereco_uf", "UF"),
    ("endereco_cod_municipio", "código IBGE do município"),
    ("endereco_municipio", "município"),
)


def conferir_emitente(emitente: dict[str, Any]) -> None:
    """Espelhar, não assumir: sem um campo legal do emitente, não se emite."""
    faltam = [rotulo for chave, rotulo in _CAMPOS_EMITENTE if not str(emitente.get(chave) or "").strip()]
    if faltam:
        raise NFeError(
            "Emitente incompleto na tabela `empresas` — falta: "
            + ", ".join(faltam)
            + ". Preencha o cadastro da empresa antes de emitir (nada é chutado aqui).",
            code="EMITENTE_INCOMPLETO",
            details={"faltam": faltam, "cnpj": emitente.get("cnpj")},
        )


def _montar_nota_fiscal(
    nfe_data: dict[str, Any],
    emitente: dict[str, Any],
    numero: int,
    codigo_numerico: str,
    ambiente: str,
) -> tuple[Any, Any, str]:
    """Constrói (NotaFiscal, Emitente, chave) do PyNFe a partir do cadastro real.

    Os nomes dos kwargs aqui NÃO são livres: `nf.cliente` (não
    `destinatario_remetente`), `tipo_documento="CNPJ"` (não "PJ"),
    `adicionar_pagamento(t_pag=, v_pag=)` (não forma_pagamento/valor), `serie`/
    `numero_nf` sem zfill, `ind_total`/`ean`/`cest`/`icms_credito`/
    `valor_tributos_aprox` obrigatórios. Cada um desses foi uma rejeição ou um
    AttributeError medido contra a SEFAZ-AM em 24/09/2026.
    """
    from pynfe.entidades.cliente import Cliente
    from pynfe.entidades.emitente import Emitente
    from pynfe.entidades.notafiscal import NotaFiscal

    conferir_emitente(emitente)
    homologacao = ambiente == "2"

    emit = Emitente()
    emit.cnpj = re.sub(r"\D", "", str(emitente["cnpj"]))
    emit.razao_social = str(emitente["razao_social"])[:60]
    emit.nome_fantasia = str(emitente.get("nome_fantasia") or emitente["razao_social"])[:60]
    emit.inscricao_estadual = re.sub(r"[^\dA-Z]", "", str(emitente["inscricao_estadual"]).upper())
    emit.inscricao_municipal = str(emitente.get("inscricao_municipal") or "")
    emit.inscricao_suframa = str(emitente.get("inscricao_suframa") or "")
    emit.codigo_de_regime_tributario = str(emitente.get("crt") or "3")
    emit.endereco_logradouro = str(emitente["endereco_logradouro"])[:60]
    emit.endereco_numero = str(emitente["endereco_numero"])[:60]
    emit.endereco_bairro = str(emitente["endereco_bairro"])[:60]
    emit.endereco_municipio = str(emitente["endereco_municipio"])[:60]
    emit.endereco_cod_municipio = str(emitente["endereco_cod_municipio"])
    emit.endereco_uf = str(emitente["endereco_uf"]).upper()
    emit.endereco_cep = re.sub(r"\D", "", str(emitente["endereco_cep"]))
    emit.endereco_pais = "1058"
    emit.endereco_telefone = re.sub(r"\D", "", str(emitente.get("telefone") or ""))

    dest = nfe_data.get("destinatario") or {}
    doc = re.sub(r"\D", "", str(dest.get("cnpj") or dest.get("cpf") or ""))
    end = dest.get("endereco") or {}
    cli = Cliente()
    if homologacao:
        # Regra da SEFAZ para homologação: destinatário de teste, nome padronizado.
        cli.tipo_documento = "CNPJ"
        cli.numero_documento = CNPJ_DEST_HOMOLOGACAO
        cli.razao_social = XNOME_HOMOLOGACAO
    else:
        cli.tipo_documento = "CNPJ" if len(doc) == 14 else "CPF"
        cli.numero_documento = doc
        cli.razao_social = str(dest.get("razao_social") or dest.get("nome") or "")[:60]
    cli.indicador_ie = int(dest.get("indicador_ie") or 9)
    cli.inscricao_estadual = str(dest.get("inscricao_estadual") or "")
    cli.inscricao_suframa = str(dest.get("inscricao_suframa") or "")
    cli.email = str(dest.get("email") or "")[:60]
    cli.endereco_logradouro = str(end.get("logradouro") or "NAO INFORMADO")[:60]
    cli.endereco_numero = str(end.get("numero") or "S/N")[:60]
    cli.endereco_bairro = str(end.get("bairro") or "NAO INFORMADO")[:60]
    cli.endereco_municipio = str(end.get("municipio") or "Manaus")[:60]
    cli.endereco_cod_municipio = str(end.get("cod_municipio") or "1302603")
    cli.endereco_uf = str(end.get("uf") or emit.endereco_uf).upper()
    cli.endereco_cep = re.sub(r"\D", "", str(end.get("cep") or "69000000"))
    cli.endereco_pais = "1058"

    agora = datetime.now()
    serie = int(nfe_data.get("serie") or 1)
    nf = NotaFiscal()
    nf.emitente = emit
    nf.cliente = cli
    nf.modelo = "55"
    nf.serie = str(serie)
    nf.numero_nf = str(numero)
    nf.forma_emissao = "1"
    nf.processo_emissao = "0"
    nf.versao_processo_emissao = "1.00"
    nf.natureza_operacao = str(nfe_data.get("natureza_operacao") or "VENDA DE MERCADORIA")[:60]
    nf.finalidade_emissao = str(nfe_data.get("finalidade") or "1")
    nf.cliente_final = str(nfe_data.get("cliente_final") or "1")
    nf.indicador_destino = "1" if cli.endereco_uf == emit.endereco_uf else "2"
    nf.indicador_presencial = "9"
    nf.municipio = emit.endereco_cod_municipio
    nf.uf = emit.endereco_uf
    nf.data_emissao = agora
    nf.data_saida_entrada = agora
    nf.tipo_documento = str(nfe_data.get("tipo") or "1")
    nf.transporte_modalidade_frete = "9"
    nf.codigo_numerico_aleatorio = codigo_numerico

    chave = montar_chave(emit.cnpj, emit.endereco_uf, serie, numero, codigo_numerico, agora)
    nf.dv_codigo_numerico_aleatorio = chave[-1]

    itens = nfe_data.get("items") or []
    if not itens:
        raise NFeError("NF-e sem itens — nada a emitir.", code="SEM_ITENS")

    valor_produtos = Decimal("0.00")
    tot_bc_icms = tot_icms = tot_pis = tot_cofins = Decimal("0.00")
    for i, item in enumerate(itens, start=1):
        q = Decimal(str(item.get("quantidade", 1)))
        vu = Decimal(str(item.get("valor_unitario", 0)))
        vt = (q * vu).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        valor_produtos += vt
        descricao = str(item.get("descricao") or "PRODUTO")[:120]
        if homologacao and i == 1:
            descricao = XPROD_HOMOLOGACAO
        # A tributação NÃO se decide aqui. Vem resolvida em cada item por
        # `modules/fiscal/services/tributacao_nfe.py` (DGX Z4), que é a única régua
        # da casa e carrega norma + origem de cada alíquota. O emissor só transcreve.
        cst = str(item.get("icms_cst") or "").strip()
        csosn = str(item.get("icms_csosn") or "").strip()
        if not cst and not csosn:
            raise NFeError(
                f"Item {i} sem CST/CSOSN de ICMS. A tributação vem de "
                "`modules.fiscal.services.tributacao_nfe` — o emissor não escolhe alíquota.",
                code="ITEM_SEM_TRIBUTACAO",
            )

        # `_cent()` da régua Z4 devolve float: "100.0" no XML é rejeição 215 (TDec_1302
        # exige 0, 0.dd ou n.dd). Tudo que é dinheiro entra aqui já quantizado em 2 casas.
        def _dec2(v) -> Decimal:
            return Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        aliq_icms = Decimal(str(item.get("icms_aliquota") or 0)).quantize(Decimal("0.0001"))
        bc_icms = _dec2(item.get("icms_base_calculo") if item.get("icms_base_calculo") is not None else vt)
        v_icms = _dec2(item.get("icms_valor"))
        v_deson = _dec2(item.get("icms_desonerado"))
        aliq_pis = Decimal(str(item.get("pis_aliquota") or 0)).quantize(Decimal("0.0001"))
        aliq_cofins = Decimal(str(item.get("cofins_aliquota") or 0)).quantize(Decimal("0.0001"))
        v_pis = (vt * aliq_pis / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        v_cofins = (vt * aliq_cofins / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        nf.adicionar_produto_servico(
            codigo=str(item.get("codigo") or i)[:60],
            descricao=descricao,
            ean="SEM GTIN",
            ean_tributavel="SEM GTIN",
            ncm=re.sub(r"\D", "", str(item.get("ncm") or "")),
            cest="",
            cfop=str(item.get("cfop") or ""),
            unidade_comercial=str(item.get("unidade") or "UN")[:6],
            unidade_tributavel=str(item.get("unidade") or "UN")[:6],
            quantidade_comercial=q,
            quantidade_tributavel=q,
            valor_unitario_comercial=vu,
            valor_unitario_tributavel=vu,
            valor_total_bruto=vt,
            desconto=Decimal(str(item.get("desconto", 0))),
            compoe_valor_total=1,
            ind_total=1,
            numero_item=i,
            valor_tributos_aprox=Decimal("0"),
            icms_modalidade=csosn or cst,
            icms_csosn=csosn,
            icms_credito=Decimal("0"),
            icms_origem=str(item.get("icms_origem") or "0"),
            icms_valor=v_icms,
            icms_valor_base_calculo=bc_icms,
            icms_aliquota=aliq_icms,
            icms_modalidade_determinacao_bc=0,
            icms_desonerado=v_deson,
            icms_motivo_desoneracao=int(item["icms_motivo_desoneracao"])
            if item.get("icms_motivo_desoneracao")
            else None,
            # No PyNFe é `pis_modalidade` que vira o <CST> e escolhe o grupo
            # (PISNT / PISAliq / PISOutr) — `pis_situacao_tributaria` é ignorado
            # pelo serializador. Deixar vazio gera <CST/> e rejeição 215 (medido).
            pis_modalidade=str(item.get("pis_cst") or "07"),
            pis_situacao_tributaria=str(item.get("pis_cst") or "07"),
            pis_valor_base_calculo=vt if aliq_pis else Decimal("0.00"),
            pis_aliquota_percentual=aliq_pis,
            pis_valor=v_pis,
            pis_tipo_calculo="P",
            cofins_modalidade=str(item.get("cofins_cst") or "07"),
            cofins_situacao_tributaria=str(item.get("cofins_cst") or "07"),
            cofins_valor_base_calculo=vt if aliq_cofins else Decimal("0.00"),
            cofins_aliquota_percentual=aliq_cofins,
            cofins_valor=v_cofins,
            cofins_tipo_calculo="P",
        )
        tot_bc_icms += bc_icms if v_icms else Decimal("0.00")
        tot_icms += v_icms
        tot_pis += v_pis
        tot_cofins += v_cofins

    nf.totais_icms_total_produtos_e_servicos = valor_produtos
    nf.totais_icms_base_calculo = tot_bc_icms
    nf.totais_icms_total = tot_icms
    nf.totais_icms_pis = tot_pis
    nf.totais_icms_cofins = tot_cofins
    nf.totais_icms_total_nota = valor_produtos
    for campo in ("total_desconto", "total_frete", "total_seguro", "outras_despesas_acessorias"):
        setattr(nf, f"totais_icms_{campo}", Decimal("0.00"))

    for pag in nfe_data.get("pagamentos") or [{"forma": "01", "valor": valor_produtos}]:
        nf.adicionar_pagamento(
            t_pag=str(pag.get("forma") or "01"),
            v_pag=Decimal(str(pag.get("valor") or valor_produtos)),
            ind_pag="0",
        )

    # infRespTec é obrigatório no leiaute 4.00 (sem ele: rejeição 972, medida).
    nf.adicionar_responsavel_tecnico(
        cnpj=emit.cnpj,
        contato=str(nfe_data.get("resp_tec_contato") or "Suporte Conecta PRO")[:60],
        email=str(nfe_data.get("resp_tec_email") or "financeiro@conectamais.pro")[:60],
        fone=emit.endereco_telefone or "0000000000",
    )

    info = str(nfe_data.get("informacoes_complementares") or "").strip()
    nf.informacoes_complementares_interesse_contribuinte = (info or "NF-e emitida pelo Conecta PRO ERP.")[:5000]

    return nf, emit, chave


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class NFeProvider:
    """Emissor NF-e modelo 55 via PyNFe 0.6.5 contra a SEFAZ-AM."""

    def __init__(self, config: NFeConfig):
        self.config = config
        self._uf_cod = _UF_COD.get(config.uf.upper(), "13")
        logger.info(
            f"NFeProvider — UF {config.uf} · ambiente {'PRODUÇÃO' if config.ambiente == '1' else 'homologação'}"
        )

    # -- infra -------------------------------------------------------------

    def _get_comunicacao(self) -> Any:
        from pynfe.processamento.comunicacao import ComunicacaoSefaz

        return ComunicacaoSefaz(
            uf=self.config.uf,
            certificado=self.config.certificado_path,
            certificado_senha=self.config.certificado_senha,
            homologacao=(self.config.ambiente == "2"),
        )

    def _assinar_xml(self, xml: Any) -> Any:
        from pynfe.processamento.assinatura import AssinaturaA1

        return AssinaturaA1(self.config.certificado_path, self.config.certificado_senha).assinar(xml)

    @staticmethod
    def _texto_resposta(resposta: Any) -> str:
        """PyNFe devolve `requests.Response`, tupla (codigo, resposta[, nfe]) ou lxml."""
        from lxml import etree

        if isinstance(resposta, tuple):
            for parte in resposta:
                texto = NFeProvider._texto_resposta(parte)
                if texto and "<" in texto:
                    return texto
            return str(resposta)
        texto = getattr(resposta, "text", None)
        if isinstance(texto, str):
            return texto
        if isinstance(resposta, etree._Element):
            return etree.tostring(resposta, encoding="unicode")
        if isinstance(resposta, bytes | bytearray):
            return bytes(resposta).decode("utf-8", "replace")
        return str(resposta)

    # -- emissão -----------------------------------------------------------

    async def emitir_nfe(
        self, nfe_data: dict[str, Any], nfe_id: UUID, numero: int, emitente: dict[str, Any]
    ) -> dict[str, Any]:
        """Emite NF-e na SEFAZ. `emitente` vem da tabela `empresas` — nunca chumbado."""
        _exigir_ambiente(self.config.ambiente, "Emissão de NF-e")
        try:
            return await asyncio.get_event_loop().run_in_executor(None, self._emitir_sync, nfe_data, numero, emitente)
        except NFeError:
            raise
        except Exception as e:
            raise NFeError(
                f"Falha na emissão da NF-e: {e}",
                code="EMISSION_ERROR",
                details={"nfe_id": str(nfe_id), "numero": numero},
            ) from e

    def _emitir_sync(self, nfe_data: dict[str, Any], numero: int, emitente: dict[str, Any]) -> dict[str, Any]:
        import secrets

        from lxml import etree
        from pynfe.entidades.fonte_dados import _fonte_dados
        from pynfe.processamento.serializacao import SerializacaoXML

        _exigir_ambiente(self.config.ambiente, "Emissão de NF-e")
        homologacao = self.config.ambiente == "2"
        codigo_numerico = str(10000000 + secrets.randbelow(90000000))

        nota, emit, chave = _montar_nota_fiscal(nfe_data, emitente, numero, codigo_numerico, self.config.ambiente)

        _fonte_dados.limpar_dados()
        _fonte_dados.adicionar_objeto(emit)
        _fonte_dados.adicionar_objeto(nota)
        arvore = SerializacaoXML(_fonte_dados, homologacao=homologacao).exportar(retorna_string=False)
        injetar_ibscbs(arvore)

        assinado = self._assinar_xml(arvore)
        _conferir_tp_amb(assinado, self.config.ambiente, "Emissão de NF-e")
        xml_assinado = assinado if isinstance(assinado, bytes) else etree.tostring(assinado)

        comunicacao = self._get_comunicacao()
        resposta = comunicacao.autorizacao(
            modelo="nfe",
            nota_fiscal=assinado,
            id_lote=int(datetime.now().timestamp()) % 100_000_000,
            ind_sinc=1,
            timeout=self.config.timeout_seconds,
        )
        texto = self._texto_resposta(resposta)
        dados = _parse_sefaz_xml(texto)

        c_stat = dados.get("cStat", "")
        x_motivo = dados.get("xMotivo", "Sem resposta SEFAZ")
        if c_stat == "100":
            status = "autorizada"
        elif c_stat in ("110", "301", "302"):
            status = "denegada"
        elif c_stat.startswith("2") or c_stat in ("204", "539"):
            status = "rejeitada"
        else:
            status = "enviada"

        logger.info(f"NF-e {numero}/{nota.serie} [{self.config.ambiente}]: [{c_stat}] {x_motivo}")
        return {
            "status": status,
            "chave_acesso": dados.get("chNFe") or chave,
            "protocolo": dados.get("nProt", ""),
            "mensagem": f"[{c_stat}] {x_motivo}",
            "xml_enviado": xml_assinado.decode("utf-8", "replace"),
            # nfeProc (NFe + protNFe) = o que a lei manda guardar por 5 anos.
            "xml_autorizado": texto if status == "autorizada" else None,
            "pdf_danfe": None,
            "codigo_status": c_stat,
            "motivo": x_motivo,
            "tp_amb": self.config.ambiente,
            "data_autorizacao": dados.get("dhRecbto") or datetime.now().isoformat(),
        }

    # -- cancelamento (evento 110111) --------------------------------------

    async def cancelar_nfe(
        self, chave_acesso: str, motivo: str, nfe_id: UUID, protocolo: str, cnpj_emitente: str
    ) -> dict[str, Any]:
        """Cancela NF-e autorizada. Prazo legal: 24h da autorização (SEFAZ recusa depois)."""
        _exigir_ambiente(self.config.ambiente, "Cancelamento de NF-e")
        if len(chave_acesso) != 44:
            raise NFeError("Chave de acesso deve ter 44 dígitos", code="INVALID_KEY")
        if len(motivo.strip()) < 15:
            raise NFeError("Motivo deve ter pelo menos 15 caracteres", code="INVALID_REASON")
        if not protocolo:
            raise NFeError("Cancelamento exige o protocolo de autorização (nProt).", code="SEM_PROTOCOLO")
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, self._cancelar_sync, chave_acesso, motivo, protocolo, cnpj_emitente
            )
        except NFeError:
            raise
        except Exception as e:
            raise NFeError(
                f"Falha no cancelamento: {e}",
                code="CANCELLATION_ERROR",
                details={"chave_acesso": chave_acesso, "nfe_id": str(nfe_id)},
            ) from e

    def _cancelar_sync(self, chave_acesso: str, motivo: str, protocolo: str, cnpj_emitente: str) -> dict[str, Any]:
        from lxml import etree

        _exigir_ambiente(self.config.ambiente, "Cancelamento de NF-e")
        agora = datetime.now().astimezone()
        cnpj = re.sub(r"\D", "", cnpj_emitente)

        # `ComunicacaoSefaz.evento()` monta o envEvento e o idLote sozinho — aqui vai
        # SÓ o <evento>. Mandar o envEvento inteiro devolve cStat 0 com xMotivo vazio
        # (medido em 24/09/2026: a SEFAZ recebe e não reconhece nada).
        evento = etree.Element("evento", versao="1.00", xmlns=NS_NFE)
        inf = etree.SubElement(evento, "infEvento")
        inf.set("Id", f"ID110111{chave_acesso}01")
        _sub(inf, "cOrgao", self._uf_cod)
        _sub(inf, "tpAmb", self.config.ambiente)
        _sub(inf, "CNPJ", cnpj)
        _sub(inf, "chNFe", chave_acesso)
        _sub(inf, "dhEvento", agora.strftime("%Y-%m-%dT%H:%M:%S%z")[:-2] + ":" + agora.strftime("%z")[-2:])
        _sub(inf, "tpEvento", "110111")
        _sub(inf, "nSeqEvento", "1")
        _sub(inf, "verEvento", "1.00")
        det = etree.SubElement(inf, "detEvento", versao="1.00")
        _sub(det, "descEvento", "Cancelamento")
        _sub(det, "nProt", protocolo)
        _sub(det, "xJust", motivo.strip()[:255])

        assinado = self._assinar_xml(evento)
        _conferir_tp_amb(assinado, self.config.ambiente, "Cancelamento de NF-e")

        resposta = self._get_comunicacao().evento(
            modelo="nfe", evento=assinado, id_lote=int(agora.timestamp()) % 100_000_000
        )
        texto = self._texto_resposta(resposta)
        dados = _parse_sefaz_xml(texto)
        c_stat = dados.get("cStat", "")
        x_motivo = dados.get("xMotivo", "")
        logger.info(f"Cancelamento {chave_acesso[:16]}…: [{c_stat}] {x_motivo}")
        return {
            # 135 = evento registrado; 155 = registrado fora de prazo (vale igual).
            "status": "cancelada" if c_stat in ("135", "155") else "erro_cancelamento",
            "chave_acesso": chave_acesso,
            "protocolo": dados.get("nProt", ""),
            "mensagem": f"[{c_stat}] {x_motivo}",
            "xml_evento": texto,
            "data_cancelamento": agora.isoformat(),
            "codigo_status": c_stat,
            "motivo_cancelamento": motivo,
        }

    # -- inutilização de faixa ---------------------------------------------

    async def inutilizar_faixa(
        self, cnpj_emitente: str, serie: int, numero_inicial: int, numero_final: int, justificativa: str
    ) -> dict[str, Any]:
        """Inutiliza uma faixa de numeração que nunca virou nota (buraco declarado)."""
        _exigir_ambiente(self.config.ambiente, "Inutilização de faixa")
        if numero_final < numero_inicial:
            raise NFeError("Faixa inválida: número final menor que o inicial.", code="FAIXA_INVALIDA")
        if len(justificativa.strip()) < 15:
            raise NFeError("Justificativa deve ter pelo menos 15 caracteres", code="INVALID_REASON")
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, self._inutilizar_sync, cnpj_emitente, serie, numero_inicial, numero_final, justificativa
            )
        except NFeError:
            raise
        except Exception as e:
            raise NFeError(f"Falha na inutilização: {e}", code="INUTILIZACAO_ERROR") from e

    def _inutilizar_sync(
        self, cnpj_emitente: str, serie: int, numero_inicial: int, numero_final: int, justificativa: str
    ) -> dict[str, Any]:
        _exigir_ambiente(self.config.ambiente, "Inutilização de faixa")
        cnpj = re.sub(r"\D", "", cnpj_emitente)
        resposta = self._get_comunicacao().inutilizacao(
            modelo="nfe",
            cnpj=cnpj,
            numero_inicial=numero_inicial,
            numero_final=numero_final,
            justificativa=justificativa.strip()[:255],
            ano=datetime.now().strftime("%y"),
            serie=str(serie),
        )
        texto = self._texto_resposta(resposta)
        dados = _parse_sefaz_xml(texto)
        c_stat = dados.get("cStat", "")
        x_motivo = dados.get("xMotivo", "")
        tp_amb_retorno = dados.get("tpAmb", "")
        if tp_amb_retorno and tp_amb_retorno != self.config.ambiente:
            raise NFeError(
                f"Inutilização respondida em tpAmb {tp_amb_retorno}, esperado {self.config.ambiente}.",
                code="TPAMB_DIVERGENTE",
            )
        logger.info(f"Inutilização {cnpj[:8]}… série {serie} {numero_inicial}-{numero_final}: [{c_stat}] {x_motivo}")
        return {
            # 102 = inutilização homologada.
            "status": "inutilizada" if c_stat == "102" else "erro_inutilizacao",
            "serie": serie,
            "numero_inicial": numero_inicial,
            "numero_final": numero_final,
            "protocolo": dados.get("nProt", ""),
            "mensagem": f"[{c_stat}] {x_motivo}",
            "xml_evento": texto,
            "codigo_status": c_stat,
            "justificativa": justificativa,
            "tp_amb": self.config.ambiente,
        }

    # -- consultas ---------------------------------------------------------

    async def consultar_status(self, chave_acesso: str) -> dict[str, Any]:
        """Consulta situação atual da NF-e na SEFAZ."""
        if len(chave_acesso) != 44:
            raise NFeError("Chave de acesso deve ter 44 dígitos", code="INVALID_KEY")
        try:
            return await asyncio.get_event_loop().run_in_executor(None, self._consultar_sync, chave_acesso)
        except NFeError:
            raise
        except Exception as e:
            raise NFeError(f"Falha na consulta: {e}", code="QUERY_ERROR") from e

    def _consultar_sync(self, chave_acesso: str) -> dict[str, Any]:
        resposta = self._get_comunicacao().consulta_nota(modelo="nfe", chave=chave_acesso)
        dados = _parse_sefaz_xml(self._texto_resposta(resposta))
        c_stat = dados.get("cStat", "")
        return {
            "status": {"100": "autorizada", "101": "cancelada", "110": "denegada"}.get(c_stat, "desconhecida"),
            "chave_acesso": chave_acesso,
            "protocolo": dados.get("nProt", ""),
            "data_autorizacao": dados.get("dhRecbto", ""),
            "codigo_status": c_stat,
            "descricao_status": dados.get("xMotivo", ""),
            "xml_disponivel": c_stat in ("100", "101"),
            "situacao": "CANCELADA" if c_stat == "101" else "NORMAL",
        }

    async def test_connection(self) -> dict[str, Any]:
        """Testa conexão com a SEFAZ (status do serviço)."""
        try:
            return await asyncio.get_event_loop().run_in_executor(None, self._status_sync)
        except Exception as e:
            raise NFeError(f"Falha na conexão com SEFAZ: {e}", code="CONNECTION_ERROR") from e

    def _status_sync(self) -> dict[str, Any]:
        resposta = self._get_comunicacao().status_servico(modelo="nfe", timeout=self.config.timeout_seconds)
        dados = _parse_sefaz_xml(self._texto_resposta(resposta))
        c_stat = dados.get("cStat", "")
        return {
            "conectado": True,
            "ambiente": "Homologação" if self.config.ambiente == "2" else "Produção",
            "uf": self.config.uf,
            "servico_ativo": c_stat == "107",
            "ultima_atualizacao": datetime.now().isoformat(),
            "versao_schema": dados.get("verAplic", "4.00"),
            "codigo_status": c_stat,
            "motivo": dados.get("xMotivo", "Sem resposta"),
            "tempo_medio_resposta": dados.get("tMed", "N/A"),
        }


def create_nfe_provider(
    certificado_path: str,
    certificado_senha: str,
    ambiente: str = "2",
    uf: str = "AM",
) -> NFeProvider:
    """Factory para criar instância do NFeProvider."""
    return NFeProvider(
        NFeConfig(
            certificado_path=certificado_path,
            certificado_senha=certificado_senha,
            ambiente=ambiente,
            uf=uf,
        )
    )
