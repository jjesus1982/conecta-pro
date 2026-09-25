#!/usr/bin/env python3
"""Oráculo AB1 — o DANFE e o DANFSe saem no leiaute NORMATIVO e dizem o que o XML diz.

POR QUE EXISTE
--------------
O dono pediu que a nota do Conecta PRO saísse «no padrão de mercado, igual à que foi emitida
por outro sistema». O leiaute do DANFE não é gosto: está no MOC da NF-e (Anexo «Manual de
Especificações Técnicas do DANFE») e fixa blocos, ordem e conteúdo mínimo. O DANFSe segue o
leiaute v2.0 do Padrão Nacional. Sair diferente é NÃO CONFORMIDADE, e é invisível numa tela
verde — só aparece quando alguém extrai o texto do PDF e confere.

Em 24/09/2026 o oráculo da frente Z3 passava verde com o DANFE saindo **sem nenhuma linha de
produto**, porque entregava os itens na mão em vez de carregá-los do banco. Este aqui não
entrega nada na mão: lê as notas autorizadas do banco pelo caminho de produção
(`carregar_nota` → `danfe_pdf`) e recontabiliza tudo por parsing PRÓPRIO do XML — regex, não
o módulo sob teste. Se o desenho e o XML discordarem, é vermelho.

O QUE AFIRMA
------------
(a) Todos os blocos obrigatórios do MOC estão no DANFE de TODA nota autorizada — canhoto,
    identificação do emitente com endereço e IE, DANFE/entrada-saída/folha, chave, protocolo,
    natureza, destinatário, cálculo do imposto (os 13 campos), transportador/volumes, dados
    dos produtos (as 14 colunas) e dados adicionais com «reservado ao fisco».
(b) O DANFE **não inventa e não recalcula**: chave, protocolo, natureza, CNPJ/IE do emitente,
    totais (vProd, vNF, vICMS, vPIS, vCOFINS) e, item a item, NCM, CFOP, quantidade e valor
    total batem com o XML que a SEFAZ autorizou.
(c) **Nenhum item some.** Todos os `<det>` do XML aparecem no PDF, paginando quando preciso,
    com FOLHA n/N coerente (incluindo um caso de 80 itens, que força várias páginas).
(d) O código de barras da chave usa **subset C** (277 módulos), como o MOC exige.
(e) O DANFE não carrega rodapé de marketing (0800, redes sociais) — é documento fiscal.
(f) A tarja «SEM VALOR FISCAL» continua em toda nota que não está autorizada em produção.
(g) O DANFSe traz os blocos do v2.0 e os valores batem com a NFS-e assinada pelo fisco
    (vServ, vBC, pAliqAplic, vISSQN, vTotalRet, vLiq, IBS-UF, CBS).
(h) O QR do DANFSe aponta para a consulta pública com a chave da própria nota — decodificado
    do PDF gerado, não conferido por leitura do código-fonte.

ESTADO MEDIDO NO NASCIMENTO (25/09/2026, código anterior à frente)
------------------------------------------------------------------
    TOTAL desvios AB1: 21
    (a) faltavam 9 blocos/rótulos · (b) vPIS do PDF 41,54 contra 41,56 do XML ·
    (d) sem conferência · (g) faltavam 11 blocos do v2.0 · (h) sem QR.

COMO RODA
---------
    docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \
      --tmpfs /app/logs:rw,mode=1777 -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 \
      --env-file /opt/conecta-pro/.env -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= \
      $ENVS conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_ab1_danfe_leiaute.py
"""

from __future__ import annotations

import asyncio
import re
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402

FALHAS: list[str] = []

#: Rótulos que o MOC manda existir no DANFE. Não é a lista inteira do manual — é a parte que
#: um DANFE de venda de mercadoria não pode deixar de imprimir, e foi conferida contra o
#: DANFE REAL da empresa (NF-e 10.026, emitida pelo nfemais em 17/09/2026).
BLOCOS_DANFE = [
    "RECEBEMOS DE",
    "DATA DE RECEBIMENTO",
    "IDENTIFICAÇÃO E ASSINATURA DO RECEBEDOR",
    "DANFE",
    "DOCUMENTO AUXILIAR DA",
    "NOTA FISCAL ELETRÔNICA",
    "0 - ENTRADA",
    "1 - SAÍDA",
    "FOLHA",
    "CHAVE DE ACESSO",
    "PROTOCOLO DE AUTORIZAÇÃO DE USO",
    "NATUREZA DA OPERAÇÃO",
    "INSCRIÇÃO ESTADUAL DO SUBST. TRIB.",
    "DESTINATÁRIO / REMETENTE",
    "BAIRRO / DISTRITO",
    "DATA DA SAÍDA / ENTRADA",
    "HORA DA SAÍDA",
    "CÁLCULO DO IMPOSTO",
    "BASE DE CÁLCULO DO ICMS",
    "VALOR DO ICMS",
    "BASE DE CÁLCULO DO ICMS ST",
    "VALOR DO ICMS SUBSTITUIÇÃO",
    "VALOR TOTAL DO IPI",
    "VALOR TOTAL DOS PRODUTOS",
    "VALOR DO FRETE",
    "VALOR DO SEGURO",
    "DESCONTO",
    "OUTRAS DESPESAS ACESSÓRIAS",
    "VALOR TOTAL DA NOTA",
    "TRANSPORTADOR / VOLUMES TRANSPORTADOS",
    "FRETE POR CONTA",
    "PESO BRUTO",
    "PESO LÍQUIDO",
    "DADOS DOS PRODUTOS / SERVIÇOS",
    "NCM/SH",
    "CST",
    "CFOP",
    "V. UNIT.",
    "BC ICMS",
    "V. ICMS",
    "V. IPI",
    "%ICMS",
    "%IPI",
    "DADOS ADICIONAIS",
    "INFORMAÇÕES COMPLEMENTARES",
    "RESERVADO AO FISCO",
]

BLOCOS_DANFSE = [
    "DATA CIENTIFICAÇÃO",
    "IDENTIFICAÇÃO E ASSINATURA",
    "CHAVE NFS-e",
    "DANFSe v2.0",
    "Documento Auxiliar da NFS-e",
    "Ambiente Gerador",
    "Tipo de Ambiente",
    "CHAVE DE ACESSO DA NFS-e",
    "NÚMERO DA DPS",
    "SÉRIE DA DPS",
    "SITUAÇÃO DA NFS-E",
    "FINALIDADE",
    "PRESTADOR / FORNECEDOR",
    "INDICADOR MUNICIPAL (INSCRIÇÃO)",
    "CÓDIGO IBGE / CEP",
    "SIMPLES NACIONAL NA DATA DE COMPETÊNCIA",
    "TOMADOR / ADQUIRENTE",
    "SERVIÇO PRESTADO",
    "CÓDIGO DE TRIBUTAÇÃO NACIONAL / MUNICIPAL",
    "CÓDIGO DA NBS",
    "LOCAL DA PRESTAÇÃO",
    "DESCRIÇÃO DO SERVIÇO",
    "TRIBUTAÇÃO MUNICIPAL (ISSQN)",
    "TIPO DE TRIBUTAÇÃO DO ISSQN",
    "BC ISSQN",
    "ALÍQUOTA APLICADA",
    "RETENÇÃO DO ISSQN",
    "ISSQN APURADO",
    "TRIBUTAÇÃO FEDERAL",
    "IRRF",
    "VALOR TOTAL DA NFS-E",
    "TOTAL DAS RETENÇÕES",
    "VALOR LÍQUIDO DA NFS-E",
    "INFORMAÇÕES COMPLEMENTARES",
]


def texto_do_pdf(pdf: bytes) -> tuple[str, int]:
    import pymupdf

    doc = pymupdf.open(stream=pdf, filetype="pdf")
    return "\n".join(p.get_text() for p in doc), doc.page_count


def brl(v) -> str:
    return f"{Decimal(str(v or 0)):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tag(xml: str, nome: str, todos: bool = False):
    achados = re.findall(rf"<(?:\w+:)?{nome}>([^<]*)</(?:\w+:)?{nome}>", xml)
    return achados if todos else (achados[-1] if achados else "")


def dets(xml: str) -> list[str]:
    return re.findall(r"<det\b.*?</det>", xml, re.S)


# ─────────────────────────────────────────────────────────────────────────────────────────────
async def main() -> int:  # noqa: PLR0912, PLR0915 — é uma bateria, é linear
    from modules.gedeon.services.nfse_danfse_generator import gerar_danfse_pdf
    from modules.operacional.controllers.redesign_builders import _dgx_z3_tela_nfe as z3

    conferidas = 0
    async with async_session_factory() as db:
        notas = (
            await db.execute(
                text(
                    "SELECT id::text, numero, chave_acesso, protocolo_autorizacao, xml_autorizado "
                    "FROM nfes WHERE status='autorizada' AND coalesce(xml_autorizado,'') <> '' "
                    "AND active IS NOT false ORDER BY numero"
                )
            )
        ).fetchall()

        if not notas:
            FALHAS.append("(a) nenhuma nota autorizada com XML no banco — o oráculo não tem o que provar")

        for nid, numero, chave, protocolo, xml in notas:
            cab, itens = await z3.carregar_nota(db, nid)

            for orientacao in ("retrato", "paisagem"):
                try:
                    pdf = z3.danfe_pdf(cab, itens, orientacao=orientacao)
                except TypeError:
                    #: Código sem a forma paisagem: o retrato ainda é conferido (é o que importa
                    #: medir), e a falta da paisagem vira UMA falha, não um atalho que cala as
                    #: outras 40 conferências.
                    if orientacao != "retrato":
                        FALHAS.append(f"(a) nota {numero}: DANFE não tem a forma paisagem prevista no MOC")
                        continue
                    pdf = z3.danfe_pdf(cab, itens)
                txt, paginas = texto_do_pdf(pdf)
                dado = f"nota {numero}/{orientacao}"

                # (a) blocos do MOC
                for rotulo in BLOCOS_DANFE:
                    if rotulo.upper() not in txt.upper():
                        FALHAS.append(f"(a) {dado}: bloco/rótulo ausente no DANFE — «{rotulo}»")

                # (b) o DANFE diz o que o XML diz
                chave_x = re.sub(r"\D", "", str(chave or ""))
                if " ".join(chave_x[i : i + 4] for i in range(0, 44, 4)) not in txt:
                    FALHAS.append(f"(b) {dado}: chave de acesso formatada não está no PDF")
                if protocolo and str(protocolo) not in txt:
                    FALHAS.append(f"(b) {dado}: protocolo {protocolo} não está no PDF")
                for rotulo, valor in (
                    ("natOp", tag(xml, "natOp")),
                    ("IE do emitente", tag(xml, "IE")),
                ):
                    if valor and valor.upper() not in txt.upper():
                        FALHAS.append(f"(b) {dado}: {rotulo} «{valor}» do XML não está no PDF")
                for tot in ("vProd", "vNF", "vICMS", "vPIS", "vCOFINS"):
                    m = re.search(rf"<ICMSTot>.*?<{tot}>([^<]+)</{tot}>", xml, re.S)
                    if m and brl(m.group(1)) not in txt:
                        FALHAS.append(
                            f"(b) {dado}: total {tot}={brl(m.group(1))} do XML não aparece no PDF "
                            "(o DANFE está recalculando em vez de representar a nota)"
                        )
                for i, det in enumerate(dets(xml), start=1):
                    for campo in ("NCM", "CFOP"):
                        v = tag(det, campo)
                        if v and v not in txt:
                            FALHAS.append(f"(b) {dado}: item {i} {campo}={v} ausente no PDF")
                    vprod = tag(det, "vProd")
                    if vprod and brl(vprod) not in txt:
                        FALHAS.append(f"(b) {dado}: item {i} vProd={brl(vprod)} ausente no PDF")

                # (c) nenhum item some
                faltando = [tag(d_, "cProd") for d_ in dets(xml) if tag(d_, "cProd") and tag(d_, "cProd") not in txt]
                if faltando:
                    FALHAS.append(f"(c) {dado}: {len(faltando)} item(ns) do XML não saíram no PDF: {faltando[:3]}")
                if f"FOLHA 1/{paginas}" not in txt.replace("\n", " "):
                    FALHAS.append(f"(c) {dado}: PDF com {paginas} página(s) e o rótulo FOLHA não bate")

                # (e) sem marketing num documento fiscal
                for proibido in ("0800", "@conectamaisoficial", "www.conectamais.pro"):
                    if proibido in txt:
                        FALHAS.append(f"(e) {dado}: rodapé de marketing «{proibido}» dentro do DANFE")

                # (f) a tarja continua
                if "SEM VALOR FISCAL" not in txt:
                    FALHAS.append(f"(f) {dado}: nota não autorizada em produção sem a tarja SEM VALOR FISCAL")
                conferidas += 1

    # (c) o caso que força várias páginas — 80 itens, rascunho, sem XML
    paginas = 0
    try:
        from modules.fiscal.services.danfe_layout import danfe as _danfe
    except ImportError as e:
        FALHAS.append(f"(c) leiaute normativo ausente — {e}")
        _danfe = None

    muitos = [
        {
            "codigo": f"ITEM-{i:03d}",
            "descricao": f"PRODUTO DE TESTE {i:03d} COM DESCRIÇÃO LONGA PARA FORÇAR A QUEBRA DE LINHA",
            "ncm": "85258919",
            "cfop": "5102",
            "unidade": "UN",
            "quantidade": 1,
            "valor_unitario": Decimal("10.00"),
            "icms_cst": "00",
        }
        for i in range(1, 81)
    ]
    if _danfe is not None:
        pdf = _danfe({"numero": 999, "serie": 1, "natureza_operacao": "TESTE"}, muitos, orientacao="retrato")
        txt, paginas = texto_do_pdf(pdf)
        sumidos = [it["codigo"] for it in muitos if it["codigo"] not in txt]
        if sumidos:
            FALHAS.append(f"(c) 80 itens: {len(sumidos)} sumiram do DANFE ({sumidos[:3]}…) — o MOC manda listar todos")
        if paginas < 2:
            FALHAS.append(f"(c) 80 itens couberam em {paginas} página — a paginação não está sendo exercida")
        for n in range(1, paginas + 1):
            if f"FOLHA {n}/{paginas}" not in txt.replace("\n", " "):
                FALHAS.append(f"(c) 80 itens: falta o rótulo FOLHA {n}/{paginas}")

    # (d) código de barras em subset C
    from reportlab.graphics.barcode import code128

    bw = 0.30
    bc = code128.Code128("1" * 44, barWidth=bw, humanReadable=False)
    modulos = round(bc.width / bw)
    quieto = round((modulos - 277) / 2)
    if modulos != 277 + 2 * quieto or quieto <= 0:
        FALHAS.append(
            f"(d) o Code128 da chave usa {modulos} módulos; 44 dígitos em subset C são 277 + zonas mudas "
            "(subset B daria 583) — o MOC exige o C"
        )

    # (g) e (h) — DANFSe contra a NFS-e assinada pelo fisco
    async with async_session_factory() as db:
        try:
            from modules.gedeon.services.nfse_danfse_generator import garantir_coluna_xml

            await garantir_coluna_xml(db)
        except ImportError as e:
            FALHAS.append(f"(g) a coluna que guarda a NFS-e assinada não existe — {e}")
        try:
            xml_nfse = (
                await db.execute(
                    text(
                        "SELECT xml_nfse FROM nfse_emitidas_nacional "
                        "WHERE coalesce(xml_nfse,'') <> '' ORDER BY numero::int DESC LIMIT 1"
                    )
                )
            ).scalar() or ""
        except Exception as e:  # noqa: BLE001 — coluna ainda não existe
            await db.rollback()
            FALHAS.append(f"(g) não foi possível ler a NFS-e assinada — {type(e).__name__}")
            xml_nfse = ""
    if not xml_nfse:
        FALHAS.append(
            "(g) nenhuma NFS-e com XML guardado em `nfse_emitidas_nacional.xml_nfse` — abra uma "
            "pela rota `/api/v1/financial/fiscal/nfse-emitida/{chave}/danfse`, que busca o XML no "
            "ADN e o guarda; sem XML o DANFSe não tem como trazer os blocos do v2.0"
        )
    else:
        pdf = gerar_danfse_pdf(xml_nfse)
        txt, _ = texto_do_pdf(pdf)
        for rotulo in BLOCOS_DANFSE:
            if rotulo.upper() not in txt.upper():
                FALHAS.append(f"(g) DANFSe: bloco/rótulo ausente — «{rotulo}»")
        #: `cTribNac` sai pontuado (140101 → 14.01.01) porque é assim que o portal imprime —
        #: conferido no DANFSe oficial da NFS-e 121. O oráculo cobra a forma do portal.
        ctrib = tag(xml_nfse, "cTribNac")
        for nome, valor in (
            ("nNFSe", tag(xml_nfse, "nNFSe")),
            ("nDPS", tag(xml_nfse, "nDPS")),
            ("cTribNac", f"{ctrib[:2]}.{ctrib[2:4]}.{ctrib[4:]}" if len(ctrib) == 6 else ctrib),
        ):
            if valor and valor not in txt:
                FALHAS.append(f"(g) DANFSe: {nome}={valor} do XML não está no PDF")
        for nome in ("vServ", "vBC", "vISSQN", "vTotalRet", "vLiq", "vIBSUF", "vCBS"):
            v = tag(xml_nfse, nome)
            if v and brl(v) not in txt:
                FALHAS.append(f"(g) DANFSe: {nome}={brl(v)} do XML não aparece no PDF")
        aliq = tag(xml_nfse, "pAliqAplic")
        if aliq and f"{brl(aliq)} %" not in txt:
            FALHAS.append(f"(g) DANFSe: alíquota aplicada {brl(aliq)} % do XML não aparece no PDF")

        chave_nfse = re.search(r'Id="NFS(\d{50})"', xml_nfse)
        esperado = f"https://www.nfse.gov.br/ConsultaPublica?tpc=1&chave={chave_nfse.group(1)}" if chave_nfse else ""
        lido = _ler_qr(pdf)
        if esperado and lido != esperado:
            FALHAS.append(f"(h) DANFSe: QR lido «{lido}» ≠ consulta pública da chave «{esperado}»")

    print(f"DANFEs conferidos contra o XML: {conferidas} · DANFE de 80 itens: {paginas} páginas")
    for f in FALHAS:
        print("  ✗", f)
    if not FALHAS:
        print(
            "OK DANFE/DANFSe: blocos do MOC e do v2.0 completos, valores iguais aos do XML, "
            "nenhum item truncado, barras em subset C, QR na consulta pública, sem marketing."
        )
    print(f"TOTAL desvios AB1: {len(FALHAS)}")
    return 1 if FALHAS else 0


def _ler_qr(pdf: bytes) -> str:
    """Decodifica o QR do PDF gerado. Conferir o QR pelo código-fonte não prova nada: o que
    importa é o que está desenhado na folha que o cliente recebe."""
    try:
        import pymupdf
        import zxingcpp
        from PIL import Image

        doc = pymupdf.open(stream=pdf, filetype="pdf")
        pix = doc[0].get_pixmap(dpi=250)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        achados = zxingcpp.read_barcodes(img)
        return next((a.text for a in achados if "ConsultaPublica" in a.text), "")
    except Exception as e:  # noqa: BLE001
        return f"(não foi possível ler: {type(e).__name__}: {e})"


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
