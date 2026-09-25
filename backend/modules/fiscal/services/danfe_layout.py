"""DGX AB1 — O leiaute NORMATIVO do DANFE e do DANFSe (25/09/2026).

Por que este arquivo existe
---------------------------
O dono comparou a nota que o Conecta PRO desenha com a que ele emite hoje por um sistema de
terceiro (`nfemais.com.br`) e disse: «se sair tudo com a nossa cara talvez cause estranheza e
descredibilidade». A intuição está certa e a razão é mais forte do que ele supõe: **o leiaute do
DANFE não é escolha de design, é norma**. Ele está no Manual de Orientação do Contribuinte da
NF-e (MOC, Anexo «Manual de Especificações Técnicas do DANFE»), que fixa os blocos, a ordem dos
blocos, os rótulos e o conteúdo mínimo. Um DANFE «com a nossa cara» não é feio: é **não
conforme**. O mesmo vale para o DANFSe v2.0 do Padrão Nacional da NFS-e.

O que o DANFE anterior tinha (medido em 25/09/2026, nota nº 13 do sandbox, a réplica da NF-e
10.026 real) — extraído o texto do PDF e comparado campo a campo com o DANFE de verdade:

  · **sem canhoto** (recibo do destinatário) — bloco 1 do MOC, ausente;
  · **sem o bloco «DANFE / 0-ENTRADA 1-SAÍDA / Nº / SÉRIE / FOLHA»** — ausente;
  · **sem o endereço, o CEP, o telefone e a INSCRIÇÃO ESTADUAL do emitente** — só o CNPJ;
  · **sem a data/hora do protocolo** (só o número), sem o texto de consulta de autenticidade;
  · **sem FATURA/DUPLICATAS, sem TRANSPORTADOR/VOLUMES, sem CÁLCULO DO ISSQN,
    sem RESERVADO AO FISCO** — quatro blocos do MOC inexistentes;
  · **cálculo do imposto com os campos errados**: mostrava «V. PRODUTOS / V. DESCONTO /
    V. FRETE / V. ICMS / V. PIS / V. COFINS» e não os 13 campos que o MOC nomeia (BC do ICMS,
    ICMS ST, IPI, seguro, outras despesas…);
  · **tabela de produtos sem CST, BC ICMS, V. ICMS, V. IPI, %ICMS, %IPI** — 6 colunas
    obrigatórias faltando;
  · **truncava os itens** («… e mais N item(ns) — veja o XML»): o DANFE tem de listar TODOS os
    itens, paginando com FOLHA x/y;
  · **valores recontados em vez de lidos do XML**: o PDF dizia PIS R$ 41,54 e a nota autorizada
    pela SEFAZ diz `<vPIS>41.56</vPIS>`. Dois centavos, mas é o documento auxiliar discordando
    do documento fiscal — que é o defeito mais grave desta lista;
  · **rodapé de marketing** («0800 880 4414 · @conectamaisoficial») atravessando um documento
    fiscal. Era exatamente a «nossa cara» que o dono não quer.

A REGRA DE OURO DESTE ARQUIVO
-----------------------------
**O DANFE é a representação do XML autorizado, não um relatório do banco.** Sempre que a nota
tem `xml_autorizado`, TODO o conteúdo sai do XML — emitente, destinatário, itens, totais,
protocolo, informações complementares. O banco só é fonte enquanto a nota é rascunho. Assim o
documento impresso não tem como discordar do que foi ao fisco.

Formatos entregues, e por que não são três invenções
----------------------------------------------------
O MOC prevê o DANFE em **retrato** e em **paisagem** — mesmos blocos, mesma ordem, mesmos
rótulos; muda a orientação da folha e, com ela, quantos itens cabem por página. As duas saem
daqui do mesmo código (`danfe(..., orientacao=…)`), porque a geometria é relativa à folha.
O terceiro formato que existe na norma — o **DANFE Simplificado** — tem hipótese de uso
restrita (o Ajuste SINIEF 07/05 e o MOC o admitem em situações específicas, como venda fora do
estabelecimento), e **não** cabe na operação desta empresa (venda de material a condomínio, com
entrega). Oferecê-lo como «terceiro modelo» seria oferecer uma não conformidade com cara de
opção. O terceiro documento que o dono recebe para aprovar é o **DANFSe**, que é outro
documento, não outro leiaute do mesmo.

Código de barras: `Code128` do reportlab, alimentado com os 44 dígitos da chave, escolhe sozinho
o **subset C** (medido: 277 módulos + zonas mudas, contra 583 se fosse subset B) — que é o que o
MOC exige. O oráculo trava esse número.

O que este arquivo NÃO faz: não emite, não transmite, não assina, não calcula tributo. Desenha.
"""

from __future__ import annotations

import io
import logging
import os
import re
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm

_PRETO = colors.black
_CINZA = colors.HexColor("#555555")
_F = "Helvetica"
_FB = "Helvetica-Bold"

#: Namespace do leiaute 4.00 da NF-e. O `nfeProc` guardado traz o `protNFe` com prefixo e a
#: `NFe` sem — por isso toda busca aqui é por sufixo de tag.
_NS = "{http://www.portalfiscal.inf.br/nfe}"

MODALIDADE_FRETE = {
    "0": "0 - Remetente",
    "1": "1 - Destinatário",
    "2": "2 - Terceiros",
    "3": "3 - Próprio/Rem.",
    "4": "4 - Próprio/Dest.",
    "9": "9 - Sem frete",
}


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Formatação
# ─────────────────────────────────────────────────────────────────────────────────────────────
def digitos(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


def num(v, casas: int = 2) -> str:
    """Número no formato brasileiro. Vazio vira '0,00' — célula de valor em branco no DANFE
    é pior que zero: o leitor não sabe se é zero ou se o sistema não soube."""
    try:
        d = Decimal(str(v if v not in (None, "") else 0))
    except (InvalidOperation, ValueError):
        return "0," + "0" * casas
    return f"{d:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def doc_br(v) -> str:
    d = digitos(v)
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return d or ""


def cep_br(v) -> str:
    d = digitos(v)
    return f"{d[:5]}-{d[5:]}" if len(d) == 8 else (d or "")


def fone_br(v) -> str:
    d = digitos(v)
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return d or ""


def numero_nf(v) -> str:
    """Número da nota no formato do DANFE: 000.010.026."""
    d = digitos(v)
    if not d:
        return ""
    d = d.zfill(9)
    return f"{d[:3]}.{d[3:6]}.{d[6:]}"


def chave_formatada(chave: str) -> str:
    d = digitos(chave)
    return " ".join(d[i : i + 4] for i in range(0, len(d), 4)) if len(d) == 44 else d


def _dt_br(v, com_hora: bool = False) -> str:
    """ISO do XML ('2026-09-17T10:16:00-04:00') ou datetime do banco → DD/MM/AAAA."""
    if not v:
        return ""
    if not isinstance(v, str):
        return v.strftime("%d/%m/%Y %H:%M:%S" if com_hora else "%d/%m/%Y")
    s = str(v)
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}):(\d{2}))?", s)
    if not m:
        return s[:19]
    data = f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    if com_hora and m.group(4):
        return f"{data} {m.group(4)}:{m.group(5)}:{m.group(6)}"
    return data


def _hora(v) -> str:
    m = re.search(r"T(\d{2}:\d{2}:\d{2})", str(v or ""))
    return m.group(1) if m else ""


# ─────────────────────────────────────────────────────────────────────────────────────────────
# A folha: uma grade de caixas, em frações da largura útil — é isso que faz retrato e paisagem
# saírem do mesmo código.
# ─────────────────────────────────────────────────────────────────────────────────────────────
class _Folha:
    def __init__(self, c, pagesize, margem: float = 7 * mm):
        self.c = c
        self.w, self.h = pagesize
        self.x0 = margem
        self.x1 = self.w - margem
        self.y = self.h - margem

    @property
    def larg(self) -> float:
        return self.x1 - self.x0

    def faixa(self, titulo: str, altura: float = 4.0 * mm) -> None:
        """Barra de título de bloco (DESTINATÁRIO/REMETENTE, CÁLCULO DO IMPOSTO…)."""
        c = self.c
        c.setLineWidth(0.6)
        c.setStrokeColor(_PRETO)
        c.rect(self.x0, self.y - altura, self.larg, altura, fill=0, stroke=1)
        c.setFont(_FB, 6.2)
        c.setFillColor(_PRETO)
        c.drawCentredString((self.x0 + self.x1) / 2, self.y - altura + 1.2 * mm, titulo.upper())
        self.y -= altura

    def campos(
        self,
        defs: list[tuple],
        altura: float = 7.2 * mm,
        y: float | None = None,
        x0: float | None = None,
        larg: float | None = None,
    ) -> None:
        """Uma linha de células. `defs` = [(fração, rótulo, valor, alinhamento)].

        alinhamento: 'e' esquerda (padrão), 'd' direita, 'c' centro.
        A fração é da largura disponível — a soma deve dar 1.0.
        """
        c = self.c
        base_y = self.y if y is None else y
        x = self.x0 if x0 is None else x0
        disp = self.larg if larg is None else larg
        c.setLineWidth(0.5)
        c.setStrokeColor(_PRETO)
        for frac, rotulo, valor, *resto in defs:
            al = (resto[0] if resto else "e") or "e"
            cw = disp * frac
            c.rect(x, base_y - altura, cw, altura, fill=0, stroke=1)
            c.setFont(_F, 5.0)
            c.setFillColor(_CINZA)
            #: O RÓTULO também é encolhido. Sem isto, «COFINS - DÉBITO APURAÇÃO PRÓPRIA» invade
            #: a célula vizinha e o documento fica ilegível justamente onde há dinheiro.
            c.drawString(x + 1.0 * mm, base_y - 2.2 * mm, self._encolher(str(rotulo).upper(), cw - 2 * mm, _F, 5.0))
            c.setFont(_FB, 7.0)
            c.setFillColor(_PRETO)
            txt = "" if valor is None else str(valor)
            txt = self._encolher(txt, cw - 2 * mm, _FB, 7.0)
            if al == "d":
                c.drawRightString(x + cw - 1.0 * mm, base_y - altura + 1.6 * mm, txt)
            elif al == "c":
                c.drawCentredString(x + cw / 2, base_y - altura + 1.6 * mm, txt)
            else:
                c.drawString(x + 1.0 * mm, base_y - altura + 1.6 * mm, txt)
            x += cw
        if y is None:
            self.y -= altura

    def _encolher(self, txt: str, larg: float, fonte: str, tam: float) -> str:
        """Texto que não cabe é ENCURTADO com reticências, nunca deixado transbordar a célula —
        num documento fiscal, texto que invade a caixa vizinha é ilegível e parece erro."""
        if self.c.stringWidth(txt, fonte, tam) <= larg:
            return txt
        while txt and self.c.stringWidth(txt + "…", fonte, tam) > larg:
            txt = txt[:-1]
        return txt + "…"


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Leitura do XML autorizado — a fonte de verdade do DANFE
# ─────────────────────────────────────────────────────────────────────────────────────────────
def _t(no, tag: str, padrao: str = "") -> str:
    if no is None:
        return padrao
    achado = no.find(f"{_NS}{tag}")
    return (achado.text or padrao).strip() if achado is not None and achado.text else padrao


def dados_do_xml(xml: str) -> dict:  # noqa: PLR0915 — é uma leitura linear de um leiaute
    """Tudo o que o DANFE precisa, lido do `nfeProc`/`NFe` autorizado.

    Nunca levanta: XML ilegível devolve `{}` e quem chama cai no banco. `defusedxml` porque o
    conteúdo veio de uma resposta da SEFAZ guardada no banco — entrada externa.
    """
    from defusedxml.ElementTree import fromstring as _parse  # noqa: PLC0415

    try:
        raiz = _parse(xml)
    except Exception:  # noqa: BLE001
        return {}
    inf = next(raiz.iter(f"{_NS}infNFe"), None)
    if inf is None:
        return {}
    ide = inf.find(f"{_NS}ide")
    emit = inf.find(f"{_NS}emit")
    dest = inf.find(f"{_NS}dest")
    ender_emit = emit.find(f"{_NS}enderEmit") if emit is not None else None
    ender_dest = dest.find(f"{_NS}enderDest") if dest is not None else None
    total = next(raiz.iter(f"{_NS}ICMSTot"), None)
    issqn_tot = next(raiz.iter(f"{_NS}ISSQNtot"), None)
    transp = inf.find(f"{_NS}transp")
    transporta = transp.find(f"{_NS}transporta") if transp is not None else None
    veic = transp.find(f"{_NS}veicTransp") if transp is not None else None
    vol = transp.find(f"{_NS}vol") if transp is not None else None
    cobr = inf.find(f"{_NS}cobr")
    infad = inf.find(f"{_NS}infAdic")
    prot = next(raiz.iter(f"{_NS}infProt"), None)

    d: dict = {
        "chave": digitos(inf.get("Id", "")),
        "numero": _t(ide, "nNF"),
        "serie": _t(ide, "serie"),
        "modelo": _t(ide, "mod", "55"),
        "tp_nf": _t(ide, "tpNF", "1"),
        "natureza": _t(ide, "natOp"),
        "data_emissao": _dt_br(_t(ide, "dhEmi")),
        "data_saida": _dt_br(_t(ide, "dhSaiEnt")) or _dt_br(_t(ide, "dhEmi")),
        "hora_saida": _hora(_t(ide, "dhSaiEnt")) or _hora(_t(ide, "dhEmi")),
        "emit_nome": _t(emit, "xNome"),
        "emit_fantasia": _t(emit, "xFant"),
        "emit_cnpj": _t(emit, "CNPJ") or _t(emit, "CPF"),
        "emit_ie": _t(emit, "IE"),
        "emit_ie_st": _t(emit, "IEST"),
        "emit_im": _t(emit, "IM"),
        "emit_logradouro": _t(ender_emit, "xLgr"),
        "emit_numero": _t(ender_emit, "nro"),
        "emit_compl": _t(ender_emit, "xCpl"),
        "emit_bairro": _t(ender_emit, "xBairro"),
        "emit_municipio": _t(ender_emit, "xMun"),
        "emit_uf": _t(ender_emit, "UF"),
        "emit_cep": _t(ender_emit, "CEP"),
        "emit_fone": _t(ender_emit, "fone"),
        "dest_nome": _t(dest, "xNome"),
        "dest_doc": _t(dest, "CNPJ") or _t(dest, "CPF") or _t(dest, "idEstrangeiro"),
        "dest_ie": _t(dest, "IE"),
        "dest_logradouro": _t(ender_dest, "xLgr"),
        "dest_numero": _t(ender_dest, "nro"),
        "dest_bairro": _t(ender_dest, "xBairro"),
        "dest_municipio": _t(ender_dest, "xMun"),
        "dest_uf": _t(ender_dest, "UF"),
        "dest_cep": _t(ender_dest, "CEP"),
        "dest_fone": _t(ender_dest, "fone"),
        "mod_frete": _t(transp, "modFrete", "9"),
        "transp_nome": _t(transporta, "xNome"),
        "transp_doc": _t(transporta, "CNPJ") or _t(transporta, "CPF"),
        "transp_ie": _t(transporta, "IE"),
        "transp_ender": _t(transporta, "xEnder"),
        "transp_municipio": _t(transporta, "xMun"),
        "transp_uf": _t(transporta, "UF"),
        "transp_antt": _t(veic, "RNTC"),
        "transp_placa": _t(veic, "placa"),
        "transp_uf_placa": _t(veic, "UF"),
        "vol_q": _t(vol, "qVol"),
        "vol_esp": _t(vol, "esp"),
        "vol_marca": _t(vol, "marca"),
        "vol_num": _t(vol, "nVol"),
        "vol_peso_b": _t(vol, "pesoB"),
        "vol_peso_l": _t(vol, "pesoL"),
        "inf_cpl": _t(infad, "infCpl"),
        "inf_fisco": _t(infad, "infAdFisco"),
        "protocolo": _t(prot, "nProt"),
        "protocolo_dh": _dt_br(_t(prot, "dhRecbto"), com_hora=True),
        "c_stat": _t(prot, "cStat"),
        "tp_amb": _t(ide, "tpAmb", "2"),
    }
    for tag, chave in (
        ("vBC", "v_bc"),
        ("vICMS", "v_icms"),
        ("vBCST", "v_bcst"),
        ("vST", "v_st"),
        ("vProd", "v_prod"),
        ("vFrete", "v_frete"),
        ("vSeg", "v_seg"),
        ("vDesc", "v_desc"),
        ("vOutro", "v_outro"),
        ("vIPI", "v_ipi"),
        ("vPIS", "v_pis"),
        ("vCOFINS", "v_cofins"),
        ("vNF", "v_nf"),
        ("vTotTrib", "v_trib"),
    ):
        d[chave] = _t(total, tag, "0")
    for tag, chave in (("vServ", "iss_serv"), ("vBC", "iss_bc"), ("vISS", "iss_valor")):
        d[chave] = _t(issqn_tot, tag, "0")

    d["duplicatas"] = [
        (_t(dup, "nDup"), _dt_br(_t(dup, "dVenc")), _t(dup, "vDup", "0"))
        for dup in (cobr.iter(f"{_NS}dup") if cobr is not None else [])
    ]
    d["itens"] = [_item_do_xml(det) for det in raiz.iter(f"{_NS}det")]
    return d


def _item_do_xml(det) -> dict:
    prod = det.find(f"{_NS}prod")
    imp = det.find(f"{_NS}imposto")
    icms_g = imp.find(f"{_NS}ICMS") if imp is not None else None
    icms = next(iter(icms_g), None) if icms_g is not None else None
    ipi_g = imp.find(f"{_NS}IPI") if imp is not None else None
    ipi = next((x for x in (ipi_g or []) if x.tag.endswith("IPITrib")), None)
    cst = _t(icms, "CST") or _t(icms, "CSOSN")
    orig = _t(icms, "orig")
    return {
        "codigo": _t(prod, "cProd"),
        "descricao": _t(prod, "xProd"),
        "ncm": _t(prod, "NCM"),
        "cst": (orig + cst) if (orig and cst) else cst,
        "cfop": _t(prod, "CFOP"),
        "unidade": _t(prod, "uCom"),
        "quantidade": _t(prod, "qCom", "0"),
        "valor_unitario": _t(prod, "vUnCom", "0"),
        "valor_total": _t(prod, "vProd", "0"),
        "bc_icms": _t(icms, "vBC", "0"),
        "v_icms": _t(icms, "vICMS", "0"),
        "p_icms": _t(icms, "pICMS", "0"),
        "v_ipi": _t(ipi, "vIPI", "0"),
        "p_ipi": _t(ipi, "pIPI", "0"),
    }


def _do_banco(cab: dict, itens: list[dict]) -> dict:
    """Rascunho: a nota ainda não foi ao fisco, então a fonte é a linha de `nfes`.

    Só o que EXISTE na linha entra. Campo ausente fica vazio — o DANFE de um rascunho tem
    lacunas de verdade, e mostrá-las é mais honesto do que preenchê-las com zero.
    """
    fora = {
        "chave": digitos(cab.get("chave_acesso")),
        "numero": cab.get("numero"),
        "serie": cab.get("serie"),
        "modelo": "55",
        "tp_nf": "1",
        "natureza": cab.get("natureza_operacao") or "",
        "data_emissao": _dt_br(cab.get("data_emissao")),
        "data_saida": _dt_br(cab.get("data_emissao")),
        "hora_saida": "",
        "emit_nome": cab.get("emitente_razao_social") or "",
        "emit_cnpj": cab.get("emitente_cnpj") or "",
        "emit_ie": cab.get("emitente_ie") or "",
        "emit_uf": cab.get("emitente_uf") or "",
        "dest_nome": cab.get("destinatario_razao_social") or "",
        "dest_doc": cab.get("destinatario_cpf_cnpj") or "",
        "dest_ie": cab.get("destinatario_ie") or "",
        "dest_logradouro": cab.get("destinatario_logradouro") or "",
        "dest_numero": cab.get("destinatario_numero") or "",
        "dest_bairro": cab.get("destinatario_bairro") or "",
        "dest_municipio": cab.get("destinatario_municipio") or "",
        "dest_uf": cab.get("destinatario_uf") or "",
        "dest_cep": cab.get("destinatario_cep") or "",
        "mod_frete": str(cab.get("modalidade_frete") or "9"),
        "protocolo": cab.get("protocolo_autorizacao") or "",
        "protocolo_dh": "",
        "inf_cpl": cab.get("informacoes_complementares") or "",
        "inf_fisco": "",
        "duplicatas": [],
        "itens": [],
    }
    soma = Decimal(0)
    for it in itens:
        q = Decimal(str(it.get("quantidade") or 0))
        vu = Decimal(str(it.get("valor_unitario") or 0))
        vt = q * vu - Decimal(str(it.get("valor_desconto") or 0))
        soma += vt
        fora["itens"].append(
            {
                "codigo": it.get("codigo") or "",
                "descricao": it.get("descricao") or "",
                "ncm": digitos(it.get("ncm")),
                "cst": str(it.get("icms_cst") or ""),
                "cfop": digitos(it.get("cfop")),
                "unidade": it.get("unidade") or "UN",
                "quantidade": str(q),
                "valor_unitario": str(vu),
                "valor_total": str(vt),
                "bc_icms": "0",
                "v_icms": "0",
                "p_icms": str(it.get("icms_aliquota") or 0),
                "v_ipi": "0",
                "p_ipi": "0",
            }
        )
    frete = Decimal(str(cab.get("valor_frete") or 0))
    for k in (
        "v_bc",
        "v_icms",
        "v_bcst",
        "v_st",
        "v_seg",
        "v_desc",
        "v_outro",
        "v_ipi",
        "v_pis",
        "v_cofins",
        "v_trib",
        "iss_serv",
        "iss_bc",
        "iss_valor",
    ):
        fora[k] = "0"
    fora["v_prod"] = str(soma)
    fora["v_frete"] = str(frete)
    fora["v_nf"] = str(soma + frete)
    return fora


# ─────────────────────────────────────────────────────────────────────────────────────────────
# DANFE
# ─────────────────────────────────────────────────────────────────────────────────────────────
#: Quantos blocos fixos ficam acima da tabela de itens na página 1, em milímetros. Números
#: medidos com a régua do próprio reportlab, não chutados: se um bloco crescer, muda aqui.
#: URL de consulta pública da NF-e por chave. O QR é uma CONVENIÊNCIA, não exigência do MOC:
#: o DANFE modelo 55 identifica a nota pelo código de barras Code-128C da chave, e é ele que o
#: fisco confere. O QR que o dono viu no DANFSe pertence ao leiaute da NFS-e (v2.0), que é outro
#: documento. Acrescentar aqui não desloca nada e não substitui as barras — as duas coisas
#: convivem, e quem lê no celular chega na mesma consulta.
_QR_CONSULTA_NFE = "https://www.nfe.fazenda.gov.br/portal/consultaResumo.aspx?tipoConsulta=resumo&nfe={chave}"

_TEXTO_CONSULTA = (
    "Consulta de autenticidade no portal nacional da NF-e "
    "www.nfe.fazenda.gov.br/portal ou no site da Sefaz Autorizadora"
)

_COLS_ITENS = (
    # (fração da largura, rótulo, chave, alinhamento, casas decimais; -1 = enxuga zeros à direita)
    (0.085, "CÓDIGO", "codigo", "e", None),
    (0.255, "DESCRIÇÃO DO PRODUTO / SERVIÇO", "descricao", "e", None),
    (0.068, "NCM/SH", "ncm", "c", None),
    (0.035, "CST", "cst", "c", None),
    (0.042, "CFOP", "cfop", "c", None),
    (0.028, "UN", "unidade", "c", None),
    (0.055, "QUANT.", "quantidade", "d", -1),
    (0.065, "V. UNIT.", "valor_unitario", "d", -2),
    (0.068, "V. TOTAL", "valor_total", "d", 2),
    (0.068, "BC ICMS", "bc_icms", "d", 2),
    (0.062, "V. ICMS", "v_icms", "d", 2),
    (0.055, "V. IPI", "v_ipi", "d", 2),
    (0.057, "%ICMS", "p_icms", "d", 2),
    (0.057, "%IPI", "p_ipi", "d", 2),
)


def _num_item(v, casas: int) -> str:
    """Quantidade e valor unitário do DANFE. O MOC admite até 4 casas; o DANFE de referência
    imprime `1`, `2`, `9` — inteiro é inteiro. `casas = -1` enxuga zeros à direita (até 4),
    qualquer outro valor fixa as casas."""
    if casas >= 0:
        return num(v, casas)
    minimo = 0 if casas == -1 else 2  # -1 = quantidade (inteiro é inteiro); -2 = valor unitário
    txt = num(v, 4)
    inteiro, _, frac = txt.partition(",")
    frac = frac.rstrip("0")
    while len(frac) < minimo:
        frac += "0"
    return f"{inteiro},{frac}" if frac else inteiro


def danfe(
    cab: dict,
    itens: list[dict],
    orientacao: str = "retrato",
    sem_valor_fiscal: bool = True,
    logo: bool = True,
    marca: str = "inline",
) -> bytes:
    """DANFE no leiaute do MOC. `orientacao` = 'retrato' (padrão) ou 'paisagem'.

    `marca` diz COMO a logo aparece na caixa do emitente — não muda bloco nenhum do MOC,
    porque a marca vive dentro do campo de identificação do emitente e o que muda é só a
    arrumação dentro dele:

      · `"inline"`  — a logo à esquerda e o texto do emitente correndo ao lado (como estava)
      · `"celula"`  — a logo em CÉLULA PRÓPRIA, separada por um fio, e o emitente na coluna
        ao lado. É o tratamento do DANFSe v2.0, que o dono pediu em 25/09/2026: *«me agrada
        muito o modelo 03_danfse no canto superior esquerdo que tem nossa logo, eu gosto do
        formato da 01_danfe_retrato, cria um quarto modelo mesclando esses 2»*.

    Não é enfeite: com `inline`, o nome da empresa começa 29mm adentro de uma caixa de 40% da
    folha, e razão social longa é encolhida até virar ilegível. Com `celula`, a logo tem
    espaço próprio e o texto recupera a largura inteira da coluna.

    `cab`/`itens` são a linha de `nfes` e as de `nfe_itens` — mas se `cab['xml_autorizado']`
    existir, é ele que manda: o DANFE representa o documento fiscal, não o banco.

    Desenha DUAS vezes: a primeira num canvas descartado, só para CONTAR as páginas (o
    «FOLHA 1/3» precisa saber o total antes da primeira linha). Contar por estimativa de
    altura foi o que levou a versão anterior a truncar itens — aqui a conta é o próprio
    desenho, então não há como errar.
    """
    from reportlab.pdfgen import canvas as _canvas

    pagesize = landscape(A4) if str(orientacao).lower().startswith("pais") else A4
    d = dados_do_xml(str(cab.get("xml_autorizado") or "")) or _do_banco(cab, itens)
    if not d.get("itens") and itens:
        d["itens"] = _do_banco(cab, itens)["itens"]

    ensaio = _canvas.Canvas(io.BytesIO(), pagesize=pagesize)
    total = _desenhar(ensaio, pagesize, d, None, sem_valor_fiscal, logo, marca)

    buf = io.BytesIO()
    c = _canvas.Canvas(buf, pagesize=pagesize, pageCompression=0)
    c.setTitle(f"DANFE {numero_nf(d.get('numero'))} serie {d.get('serie') or ''}")
    c.setAuthor(d.get("emit_nome") or "")
    _desenhar(c, pagesize, d, total, sem_valor_fiscal, logo, marca)
    c.save()
    return buf.getvalue()


def _desenhar(
    c, pagesize, d: dict, total: int | None, sem_valor_fiscal: bool, logo: bool, marca: str = "inline"
) -> int:
    """Desenha o documento inteiro e devolve quantas páginas saíram."""
    fila = list(d.get("itens") or [])
    pagina = 0
    while True:
        pagina += 1
        f = _Folha(c, pagesize)
        primeira = pagina == 1
        if primeira:
            _canhoto(f, d)
        _cabecalho(f, d, folha=f"{pagina}/{total}" if total else f"{pagina}/…", logo=logo, marca=marca)
        if primeira:
            _emitente_dest(f, d)
            _duplicatas(f, d)
            _imposto(f, d)
            _transporte(f, d)
        #: O piso da tabela é o que sobra para ISSQN + dados adicionais. Numa página que não é
        #: a última, o rodapé não é desenhado — mas o piso continua o mesmo, senão a tabela de
        #: uma página do meio desceria até a margem e o documento ficaria com duas geometrias.
        piso = 7 * mm + _altura_rodape(d)
        fila = _tabela_itens(f, fila, piso)
        ultima = not fila
        if ultima:
            _issqn(f, d)
            _dados_adicionais(f, d)
        if sem_valor_fiscal:
            _tarja(c, pagesize, d)
        _assinatura(c, pagesize)
        c.showPage()
        if ultima:
            return pagina


#: Assinatura do sistema emissor, pedida pelo dono: «no canto inferior da nota informar que
#: essa nota foi emitida pelo Conecta PRO, o sistema de gestão inteligente da Conecta Mais».
#:
#: ⚠️ Ela é desenhada ABAIXO do quadro fiscal, no espaço da margem, e NUNCA dentro de
#: «INFORMAÇÕES COMPLEMENTARES». Aquele campo é o `infCpl` do XML — o que está impresso ali
#: tem de ser exatamente o que foi assinado e transmitido ao fisco. Escrever marketing nele
#: faria o DANFE DISCORDAR do documento fiscal, que é o defeito que esta frente acabou de
#: consertar (o PDF dizia PIS 41,54 e o XML 41,56). Identificação do software emissor no pé da
#: folha é prática comum e não é campo do MOC — por isso pode.
_ASSINATURA = "Documento emitido pelo Conecta PRO — sistema de gestão inteligente da Conecta Mais"


def _assinatura(c, pagesize) -> None:
    """Uma linha discreta no pé da folha, fora do quadro. Não desloca nem cobre campo algum."""
    w, _ = pagesize
    c.setFont(_F, 4.8)
    c.setFillColor(_CINZA)
    c.drawCentredString(w / 2, 3.4 * mm, _ASSINATURA)
    c.setFillColor(_PRETO)


def _altura_rodape(d: dict) -> float:
    """Altura reservada abaixo da tabela de itens: o ISSQN (quando a nota tem serviço) e o
    bloco de dados adicionais."""
    tem_iss = digitos(d.get("iss_serv")) not in ("", "0", "000")
    return (11.2 * mm if tem_iss else 0) + 26 * mm


def _canhoto(f: _Folha, d: dict) -> None:
    """Bloco 1 do MOC — recibo do destinatário. Sem ele o DANFE não é DANFE."""
    c = f.c
    alt = 13 * mm
    lrec = f.larg * 0.80
    c.setLineWidth(0.6)
    c.setStrokeColor(_PRETO)
    c.rect(f.x0, f.y - alt, lrec, alt, fill=0, stroke=1)
    c.setFont(_F, 5.6)
    c.setFillColor(_PRETO)
    c.drawString(
        f.x0 + 1.2 * mm,
        f.y - 3.0 * mm,
        f"RECEBEMOS DE {(d.get('emit_nome') or '').upper()} OS PRODUTOS CONSTANTES DA NOTA FISCAL",
    )
    c.drawString(
        f.x0 + 1.2 * mm,
        f.y - 5.6 * mm,
        "ELETRÔNICA INDICADA AO LADO, BEM COMO ATESTAMOS QUE OS MESMOS FORAM EXAMINADOS, SERVINDO O ACEITE",
    )
    c.drawString(f.x0 + 1.2 * mm, f.y - 8.2 * mm, "DA PRESENTE PARA TODOS OS EFEITOS LEGAIS.")
    f.campos(
        [(0.35, "Data de recebimento", "", "e"), (0.65, "Identificação e assinatura do recebedor", "", "e")],
        altura=4.6 * mm,
        y=f.y - alt + 4.6 * mm,
        x0=f.x0,
        larg=lrec,
    )
    c.rect(f.x0 + lrec, f.y - alt, f.larg - lrec, alt, fill=0, stroke=1)
    c.setFont(_FB, 9)
    c.drawCentredString(f.x0 + lrec + (f.larg - lrec) / 2, f.y - 4.4 * mm, "NF-e")
    c.setFont(_F, 6)
    c.drawCentredString(f.x0 + lrec + (f.larg - lrec) / 2, f.y - 8.0 * mm, f"Nº {numero_nf(d.get('numero'))}")
    c.drawCentredString(f.x0 + lrec + (f.larg - lrec) / 2, f.y - 11.0 * mm, f"SÉRIE {d.get('serie') or ''}")
    f.y -= alt
    c.setDash(2, 2)
    c.setLineWidth(0.4)
    c.line(f.x0, f.y - 2 * mm, f.x1, f.y - 2 * mm)
    c.setDash()
    f.y -= 4.5 * mm


def _qrcode(c, texto: str, x: float, y: float, lado: float) -> None:
    """QR quadrado de `lado`, no canto (x, y). Sem QR a chave por extenso ainda consulta."""
    try:
        from reportlab.graphics import renderPDF  # noqa: PLC0415
        from reportlab.graphics.barcode.qr import QrCodeWidget  # noqa: PLC0415
        from reportlab.graphics.shapes import Drawing  # noqa: PLC0415

        qr = QrCodeWidget(texto)
        x0, y0, x1, y1 = qr.getBounds()
        dw = Drawing(lado, lado, transform=[lado / (x1 - x0), 0, 0, lado / (y1 - y0), 0, 0])
        dw.add(qr)
        renderPDF.draw(dw, c, x, y)
    except Exception:  # noqa: BLE001
        pass


def _cabecalho(f: _Folha, d: dict, folha: str, logo: bool, marca: str = "inline") -> None:
    """Bloco 2 do MOC: emitente | DANFE (entrada/saída, nº, série, folha) | chave + barras."""
    c = f.c
    alt = 26 * mm
    c1 = f.larg * 0.40
    c2 = f.larg * 0.22
    c3 = f.larg - c1 - c2
    topo = f.y
    c.setLineWidth(0.6)
    c.setStrokeColor(_PRETO)
    c.rect(f.x0, topo - alt, c1, alt, fill=0, stroke=1)
    c.rect(f.x0 + c1, topo - alt, c2, alt, fill=0, stroke=1)
    c.rect(f.x0 + c1 + c2, topo - alt, c3, alt, fill=0, stroke=1)

    # ── emitente (o MOC admite o logotipo aqui — é o único lugar da marca no documento)
    x = f.x0 + 2 * mm
    y = topo - 5 * mm
    celula = str(marca).lower().startswith("cel")
    if logo:
        try:
            from modules.crm.services import pdf_branding as pb  # noqa: PLC0415

            # ⚠️ A MARCA CERTA OU MARCA NENHUMA — nunca a de reserva.
            #
            # `_desenha_logo_cheia` tenta três caminhos em cadeia e devolve `True` no primeiro
            # que abrir. Numa tela isso é gentileza; num DOCUMENTO FISCAL é armadilha: em
            # 25/09/2026 gerei um modelo de DANFE num contêiner sem `/app/uploads` montado, a
            # logo caiu para o arquivo de reserva, e saiu pequena e desbotada. O PDF dizia
            # «gerado», o código dizia `True`, e eu quase mandei ao dono um modelo visual com
            # a marca errada para aprovar. O que me salvou foi ABRIR o PDF.
            #
            # Aqui a cadeia é cortada: ou existe o arquivo canônico da marca, ou o DANFE sai
            # SEM logo — que é conforme, porque o MOC só ADMITE o logotipo, não o exige. Um
            # documento sem marca é sóbrio; um documento com a marca errada é constrangedor,
            # e o segundo não se distingue do primeiro sem alguém olhando.
            if not os.access(pb._LOGO_CHEIA, os.R_OK):
                logger.warning(
                    "[danfe] marca oficial ausente em %s — DANFE sai SEM logo, nunca com a de reserva",
                    pb._LOGO_CHEIA,
                )
                raise FileNotFoundError(pb._LOGO_CHEIA)

            if celula:
                # A marca ganha uma FAIXA própria no alto do campo do emitente, com fio
                # embaixo — e o nome da empresa passa a usar a LARGURA INTEIRA da célula.
                #
                # A primeira versão punha a logo numa COLUNA à esquerda, como no DANFSe. Ficou
                # pior, e a medição mostrou por quê: o campo do emitente no DANFE tem 40% da
                # folha (~74mm). Tirar 30mm para a logo deixa 44mm para a razão social, e
                # «CONECTAMAIS ELETRONICA LTDA» saiu truncada em «...ELETRONICA LT…». No
                # DANFSe a coluna cabe porque lá o prestador tem uma faixa de largura INTEIRA,
                # separada da do título — estrutura que o MOC não permite mexer aqui.
                #
                # Empilhando, os dois ganham: a logo fica maior que os 26×9mm do modo inline e
                # o nome recupera os 74mm. O fio é DENTRO do campo do emitente — não cria
                # bloco, não move nada do leiaute normativo.
                # As alturas aqui são o orçamento de 26mm da caixa, gasto até o fim: marca
                # 6,6 · fio · nome · 3 linhas de endereço a 3,0 · 2 de consulta a 2,4. A
                # primeira tentativa deixou a consulta em cima do CEP — em documento fiscal
                # texto sobreposto não é feio, é ilegível, e o CEP é campo obrigatório.
                # Marca CENTRADA e MAIOR, pedido do dono: «quero valorizar minha logo, minha
                # marca». 44mm de largura contra os 26mm do modo inline — 69% maior. O fio
                # embaixo separa a marca do texto sem criar bloco.
                larg_logo = 44 * mm
                if pb._desenha_logo_cheia(
                    c, f.x0 + (c1 - larg_logo) / 2, topo - 9.4 * mm, largura=larg_logo, altura=8.4 * mm
                ):
                    c.setLineWidth(0.4)
                    c.setStrokeColor(_CINZA)
                    c.line(f.x0 + 4 * mm, topo - 10.4 * mm, f.x0 + c1 - 4 * mm, topo - 10.4 * mm)
                    c.setStrokeColor(_PRETO)
                    y = topo - 13.0 * mm  # o texto do emitente começa abaixo do fio
            elif pb._desenha_logo_cheia(c, x, topo - 9.5 * mm, largura=26 * mm, altura=9 * mm):
                x += 29 * mm
        except Exception:  # noqa: BLE001 — sem logo o documento continua conforme
            pass
    c.setFillColor(_PRETO)
    # No modo célula tudo é centrado na caixa do emitente — marca, nome, endereço e a linha de
    # consulta. Foi o que o dono desenhou: «orna essas informações de forma bonita,
    # centralizada». `larg` é a largura útil, igual para todas as linhas, para o `_encolher`
    # não medir uma régua por linha.
    meio = f.x0 + c1 / 2
    larg = (c1 - 8 * mm) if celula else (f.x0 + c1 - x - 2 * mm)
    escrever = (lambda yy, txt, fonte, tam: c.drawCentredString(meio, yy, f._encolher(txt, larg, fonte, tam))) if celula \
        else (lambda yy, txt, fonte, tam: c.drawString(x, yy, f._encolher(txt, larg, fonte, tam)))
    c.setFont(_FB, 7.4)
    escrever(y, (d.get("emit_nome") or "").upper(), _FB, 7.4)
    c.setFont(_F, 6.2)
    ender = f"{d.get('emit_logradouro') or ''}, {d.get('emit_numero') or 'S/N'}".strip(", ")
    for k, txt in enumerate(
        (
            ender,
            f"{d.get('emit_bairro') or ''} - {d.get('emit_municipio') or ''}/{d.get('emit_uf') or ''}".strip(" -/"),
            f"CEP: {cep_br(d.get('emit_cep'))}   FONE: {fone_br(d.get('emit_fone'))}".strip(),
        )
    ):
        escrever(y - (k + 1) * (2.8 if celula else 3.0) * mm, txt, _F, 6.2)
    c.setFont(_F, 5.0)
    c.setFillColor(_CINZA)
    # com a marca empilhada, o emitente desce e o texto de consulta desce junto — em 2 linhas,
    # porque a terceira bateria na borda de baixo da caixa.
    _topo_consulta = topo - (23.6 if celula else 18.0) * mm
    for k, txt in enumerate(_quebrar(c, _TEXTO_CONSULTA, c1 - 6 * mm, _F, 4.6 if celula else 5.0)[: 2 if celula else 3]):
        if celula:
            c.setFont(_F, 4.6)
            c.drawCentredString(meio, _topo_consulta - k * 2.0 * mm, txt)
        else:
            c.drawString(f.x0 + 2 * mm, _topo_consulta - k * 2.6 * mm, txt)

    # ── DANFE
    xm = f.x0 + c1 + c2 / 2
    c.setFillColor(_PRETO)
    c.setFont(_FB, 13)
    c.drawCentredString(xm, topo - 5.6 * mm, "DANFE")
    c.setFont(_F, 5.2)
    for k, txt in enumerate(("DOCUMENTO AUXILIAR DA", "NOTA FISCAL ELETRÔNICA")):
        c.drawCentredString(xm, topo - 8.8 * mm - k * 2.6 * mm, txt)
    saida = str(d.get("tp_nf") or "1") == "1"
    c.setFont(_F, 5.2)
    c.drawCentredString(xm, topo - 15.4 * mm, "0 - ENTRADA")
    c.drawCentredString(xm, topo - 17.8 * mm, "1 - SAÍDA")
    c.setLineWidth(0.5)
    c.rect(f.x0 + c1 + c2 - 8 * mm, topo - 18.2 * mm, 4.6 * mm, 4.6 * mm, fill=0, stroke=1)
    c.setFont(_FB, 7)
    c.drawCentredString(f.x0 + c1 + c2 - 5.7 * mm, topo - 17.0 * mm, "1" if saida else "0")
    c.setFont(_FB, 7.4)
    c.drawCentredString(xm, topo - 21.2 * mm, f"Nº {numero_nf(d.get('numero'))}")
    c.setFont(_F, 6.4)
    c.drawCentredString(xm, topo - 24.2 * mm, f"SÉRIE {d.get('serie') or ''}     FOLHA {folha}")

    # ── chave de acesso + código de barras (Code-128C)
    chave = digitos(d.get("chave"))
    xc = f.x0 + c1 + c2
    # No modelo com marca em destaque, o QR de consulta divide a caixa com as barras: 18mm à
    # direita para o QR, o resto para o Code-128C. As barras NÃO encolhem abaixo do que se lê —
    # se não couberem as duas coisas, quem sai é o QR, porque ele é conveniência e a barra é o
    # que o fisco confere.
    # O QR divide a FAIXA DAS BARRAS com o Code-128C — e só ela. A chave por extenso continua
    # usando a largura inteira da caixa, embaixo dos dois.
    #
    # A primeira tentativa punha o QR de 17mm ocupando também a altura da chave: as barras
    # entraram por cima do QR e a chave saiu TRUNCADA («…5500 2000 0000 …»). Chave truncada em
    # DANFE não é problema estético — ela é o identificador com que o destinatário consulta a
    # nota e com que o fisco a acha. Nada pode empurrá-la.
    lado_qr = 14 * mm if (celula and len(chave) == 44) else 0.0
    larg_bc = c3 - lado_qr - (3 * mm if lado_qr else 0)
    if len(chave) == 44:
        try:
            from reportlab.graphics.barcode import code128  # noqa: PLC0415

            bw = min(0.33, (larg_bc - 6 * mm) / 397.0)
            if bw < 0.20:  # barra ilegível: o QR sai, porque a barra é o que o fisco confere
                lado_qr, larg_bc = 0.0, c3
                bw = min(0.33, (c3 - 10 * mm) / 397.0)
            bc = code128.Code128(chave, barHeight=11 * mm, barWidth=bw, humanReadable=False)
            bc.drawOn(c, xc + (larg_bc - bc.width) / 2, topo - 14 * mm)
        except Exception:  # noqa: BLE001 — sem barras a chave por extenso ainda identifica a nota
            pass
    if lado_qr:
        _qrcode(c, _QR_CONSULTA_NFE.format(chave=chave), xc + c3 - lado_qr - 1.5 * mm, topo - 14.6 * mm, lado_qr)
    c.setFont(_F, 5.0)
    c.setFillColor(_CINZA)
    c.drawString(xc + 1.5 * mm, topo - 2.6 * mm, "CHAVE DE ACESSO")
    c.setFont(_FB, 7.0)
    c.setFillColor(_PRETO)
    _tam_chave = 6.4 if lado_qr else 7.0
    c.setFont(_FB, _tam_chave)
    c.drawCentredString(
        xc + c3 / 2, topo - 17.6 * mm, f._encolher(chave_formatada(chave), c3 - 3 * mm, _FB, _tam_chave)
    )
    c.setFont(_F, 5.0)
    c.setFillColor(_CINZA)
    c.drawString(xc + 1.5 * mm, topo - 21.0 * mm, "PROTOCOLO DE AUTORIZAÇÃO DE USO")
    c.setFont(_FB, 7.0)
    c.setFillColor(_PRETO)
    prot = " - ".join(x for x in (d.get("protocolo"), d.get("protocolo_dh")) if x) or "—"
    c.drawString(xc + 1.5 * mm, topo - 24.4 * mm, f._encolher(prot, c3 - 3 * mm, _FB, 7.0))
    f.y = topo - alt

    f.campos([(1.0, "Natureza da operação", d.get("natureza") or "", "e")], altura=6.8 * mm)
    f.campos(
        [
            (0.34, "Inscrição estadual", d.get("emit_ie") or "", "e"),
            (0.33, "Inscrição estadual do subst. trib.", d.get("emit_ie_st") or "", "e"),
            (0.33, "CNPJ", doc_br(d.get("emit_cnpj")), "e"),
        ],
        altura=6.8 * mm,
    )


def _emitente_dest(f: _Folha, d: dict) -> None:
    f.faixa("Destinatário / Remetente")
    f.campos(
        [
            (0.58, "Nome / razão social", d.get("dest_nome") or "", "e"),
            (0.24, "CNPJ / CPF", doc_br(d.get("dest_doc")), "e"),
            (0.18, "Data da emissão", d.get("data_emissao") or "", "e"),
        ]
    )
    f.campos(
        [
            (0.44, "Endereço", f"{d.get('dest_logradouro') or ''}, {d.get('dest_numero') or 'S/N'}".strip(", "), "e"),
            (0.24, "Bairro / distrito", d.get("dest_bairro") or "", "e"),
            (0.14, "CEP", cep_br(d.get("dest_cep")), "e"),
            (0.18, "Data da saída / entrada", d.get("data_saida") or "", "e"),
        ]
    )
    f.campos(
        [
            (0.32, "Município", d.get("dest_municipio") or "", "e"),
            (0.20, "Fone / fax", fone_br(d.get("dest_fone")), "e"),
            (0.06, "UF", d.get("dest_uf") or "", "c"),
            (0.24, "Inscrição estadual", d.get("dest_ie") or "ISENTO", "e"),
            (0.18, "Hora da saída", d.get("hora_saida") or "", "e"),
        ]
    )


def _duplicatas(f: _Folha, d: dict) -> None:
    """Bloco FATURA/DUPLICATAS — só aparece quando a nota TEM duplicata.

    O DANFE de referência do dono (NF-e 10.026, emitida pelo nfemais) também o omite quando não
    há cobrança a prazo. Desenhar uma caixa vazia com o rótulo «FATURA» não acrescenta nada e
    rouba altura da tabela de itens, que é onde o documento precisa de espaço.
    """
    dups = d.get("duplicatas") or []
    if not dups:
        return
    f.faixa("Fatura / Duplicatas")
    for bloco in [dups[i : i + 4] for i in range(0, min(len(dups), 8), 4)]:
        defs = []
        for n, venc, valor in bloco:
            defs.append((0.25 / 1, f"Núm. {n}", f"{venc}   R$ {num(valor)}", "e"))
        while len(defs) < 4:
            defs.append((0.25, "", "", "e"))
        f.campos([(0.25, r, v, a) for _, r, v, a in defs], altura=6.4 * mm)


def _imposto(f: _Folha, d: dict) -> None:
    f.faixa("Cálculo do imposto")
    f.campos(
        [
            (0.17, "Base de cálculo do ICMS", num(d.get("v_bc")), "d"),
            (0.17, "Valor do ICMS", num(d.get("v_icms")), "d"),
            (0.17, "Base de cálculo do ICMS ST", num(d.get("v_bcst")), "d"),
            (0.17, "Valor do ICMS substituição", num(d.get("v_st")), "d"),
            (0.14, "Valor total do IPI", num(d.get("v_ipi")), "d"),
            (0.18, "Valor total dos produtos", num(d.get("v_prod")), "d"),
        ]
    )
    f.campos(
        [
            (0.14, "Valor do frete", num(d.get("v_frete")), "d"),
            (0.14, "Valor do seguro", num(d.get("v_seg")), "d"),
            (0.14, "Desconto", num(d.get("v_desc")), "d"),
            (0.16, "Outras despesas acessórias", num(d.get("v_outro")), "d"),
            (0.13, "Valor do PIS", num(d.get("v_pis")), "d"),
            (0.13, "Valor da COFINS", num(d.get("v_cofins")), "d"),
            (0.16, "Valor total da nota", num(d.get("v_nf")), "d"),
        ]
    )


def _transporte(f: _Folha, d: dict) -> None:
    f.faixa("Transportador / Volumes transportados")
    f.campos(
        [
            (0.36, "Razão social", d.get("transp_nome") or "", "e"),
            (0.16, "Frete por conta", MODALIDADE_FRETE.get(str(d.get("mod_frete") or "9"), ""), "e"),
            (0.13, "Código ANTT", d.get("transp_antt") or "", "e"),
            (0.13, "Placa do veículo", d.get("transp_placa") or "", "e"),
            (0.06, "UF", d.get("transp_uf_placa") or "", "c"),
            (0.16, "CNPJ / CPF", doc_br(d.get("transp_doc")), "e"),
        ]
    )
    f.campos(
        [
            (0.48, "Endereço", d.get("transp_ender") or "", "e"),
            (0.26, "Município", d.get("transp_municipio") or "", "e"),
            (0.06, "UF", d.get("transp_uf") or "", "c"),
            (0.20, "Inscrição estadual", d.get("transp_ie") or "", "e"),
        ]
    )
    f.campos(
        [
            (0.14, "Quantidade", d.get("vol_q") or "", "d"),
            (0.22, "Espécie", d.get("vol_esp") or "", "e"),
            (0.20, "Marca", d.get("vol_marca") or "", "e"),
            (0.16, "Numeração", d.get("vol_num") or "", "e"),
            (0.14, "Peso bruto", num(d.get("vol_peso_b"), 3), "d"),
            (0.14, "Peso líquido", num(d.get("vol_peso_l"), 3), "d"),
        ]
    )


def _tabela_itens(f: _Folha, linhas: list[dict], piso: float) -> list[dict]:
    """Desenha o que couber entre o topo atual e `piso`, e devolve o que sobrou.

    A descrição do produto QUEBRA em várias linhas em vez de ser cortada: o MOC manda imprimir
    a descrição do item, e «CABO LAN CAT5E 305M 100% CO…» não é a descrição do item.
    """
    c = f.c
    f.faixa("Dados dos produtos / serviços")
    topo = f.y
    cab_alt = 4.2 * mm
    alt_linha = 3.3 * mm
    larg_desc = f.larg * _COLS_ITENS[1][0] - 1.4 * mm

    y = topo - cab_alt - 2.4 * mm
    usados = 0
    for it in linhas:
        partes = _quebrar(c, it.get("descricao") or "", larg_desc, _F, 5.6) or [""]
        if y - (len(partes) - 1) * alt_linha < piso + 1.5 * mm:
            break
        it["_desc"] = partes
        y -= len(partes) * alt_linha
        usados += 1
    cabem = linhas[:usados] if usados else linhas[:1]
    if not usados and linhas:  # item gigante numa página curta: entra cortado, mas entra
        cabem[0]["_desc"] = _quebrar(c, cabem[0].get("descricao") or "", larg_desc, _F, 5.6)[:1]

    fundo = piso
    c.setLineWidth(0.6)
    c.setStrokeColor(_PRETO)
    c.rect(f.x0, fundo, f.larg, topo - fundo, fill=0, stroke=1)
    c.line(f.x0, topo - cab_alt, f.x1, topo - cab_alt)

    x = f.x0
    c.setFont(_FB, 4.8)
    c.setFillColor(_PRETO)
    for frac, rotulo, _k, _al, _cs in _COLS_ITENS:
        cw = f.larg * frac
        c.drawCentredString(x + cw / 2, topo - 2.9 * mm, rotulo)
        if x > f.x0:
            c.setLineWidth(0.4)
            c.line(x, fundo, x, topo)
            c.setLineWidth(0.6)
        x += cw

    y = topo - cab_alt - 2.4 * mm
    for it in cabem:
        partes = it.get("_desc") or [it.get("descricao") or ""]
        x = f.x0
        c.setFont(_F, 5.6)
        c.setFillColor(_PRETO)
        for frac, _rot, chave, al, casas in _COLS_ITENS:
            cw = f.larg * frac
            if chave == "descricao":
                for k, parte in enumerate(partes):
                    c.drawString(x + 0.7 * mm, y - k * alt_linha, parte)
                x += cw
                continue
            valor = it.get(chave) or ""
            txt = _num_item(valor, casas) if casas is not None else str(valor)
            txt = f._encolher(txt, cw - 1.4 * mm, _F, 5.6)
            if al == "d":
                c.drawRightString(x + cw - 0.7 * mm, y, txt)
            elif al == "c":
                c.drawCentredString(x + cw / 2, y, txt)
            else:
                c.drawString(x + 0.7 * mm, y, txt)
            x += cw
        y -= len(partes) * alt_linha
    f.y = fundo
    return linhas[len(cabem) :]


def _issqn(f: _Folha, d: dict) -> None:
    if digitos(d.get("iss_serv")) in ("", "0", "000"):
        return
    f.faixa("Cálculo do ISSQN")
    f.campos(
        [
            (0.25, "Inscrição municipal", d.get("emit_im") or "", "e"),
            (0.25, "Valor total dos serviços", num(d.get("iss_serv")), "d"),
            (0.25, "Base de cálculo do ISSQN", num(d.get("iss_bc")), "d"),
            (0.25, "Valor do ISSQN", num(d.get("iss_valor")), "d"),
        ]
    )


def _dados_adicionais(f: _Folha, d: dict) -> None:
    c = f.c
    f.faixa("Dados adicionais")
    alt = 22 * mm
    lc = f.larg * 0.68
    c.setLineWidth(0.6)
    c.rect(f.x0, f.y - alt, lc, alt, fill=0, stroke=1)
    c.rect(f.x0 + lc, f.y - alt, f.larg - lc, alt, fill=0, stroke=1)
    c.setFont(_F, 5.0)
    c.setFillColor(_CINZA)
    c.drawString(f.x0 + 1.2 * mm, f.y - 2.4 * mm, "INFORMAÇÕES COMPLEMENTARES")
    c.drawString(f.x0 + lc + 1.2 * mm, f.y - 2.4 * mm, "RESERVADO AO FISCO")
    c.setFont(_F, 5.4)
    c.setFillColor(_PRETO)
    for k, ln in enumerate(_quebrar(c, d.get("inf_cpl") or "", lc - 3 * mm, _F, 5.4)[:6]):
        c.drawString(f.x0 + 1.2 * mm, f.y - 5.4 * mm - k * 2.8 * mm, ln)
    for k, ln in enumerate(_quebrar(c, d.get("inf_fisco") or "", f.larg - lc - 3 * mm, _F, 5.4)[:6]):
        c.drawString(f.x0 + lc + 1.2 * mm, f.y - 5.4 * mm - k * 2.8 * mm, ln)
    f.y -= alt


def _tarja(c, pagesize, d: dict) -> None:
    w, h = pagesize
    c.saveState()
    c.setFillColor(colors.Color(0.85, 0.15, 0.15, alpha=0.20))
    c.translate(w / 2, h / 2)
    c.rotate(30)
    c.setFont(_FB, 40)
    c.drawCentredString(0, 0, "SEM VALOR FISCAL")
    c.setFont(_FB, 12)
    c.drawCentredString(
        0,
        -12 * mm,
        "AMBIENTE DE HOMOLOGAÇÃO" if str(d.get("tp_amb") or "2") == "2" else "NOTA NÃO AUTORIZADA",
    )
    c.restoreState()


def _quebrar(c, txt: str, larg: float, fonte: str, tam: float) -> list[str]:
    """Quebra por palavra respeitando a largura real da fonte."""
    fora: list[str] = []
    linha = ""
    for palavra in re.sub(r"\s+", " ", str(txt or "")).strip().split(" "):
        se = f"{linha} {palavra}".strip()
        if linha and c.stringWidth(se, fonte, tam) > larg:
            fora.append(linha)
            linha = palavra
        else:
            linha = se
    if linha:
        fora.append(linha)
    return fora
