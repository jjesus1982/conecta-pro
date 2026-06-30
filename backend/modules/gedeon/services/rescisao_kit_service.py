"""GEDEON — Pacote de RESCISÃO no kit. Por demitido do mês (M = competência+1):
  1. Termo de Rescisão (TRCT)              — Onvio, categoria='rescisao' ("TRCT - Nome")
  2. Comprovante de Pagamento de Rescisão  — Inter, PIX pro demitido ANCORADO no valor do TRCT
  3. ASO Demissional                       — Onvio, categoria='aso'
  4. Carta de Pedido de Demissão           — Onvio
Arquiva na subpasta "1. Folha e Pessoal" do condomínio do demitido. Demitido que trabalhou o
mês fica no kit, com o pacote de rescisão como justificativa.

ÂNCORA NO TRCT (decisão Jordan): o valor líquido do TRCT define qual PIX do Inter é a verba
rescisória (evita confundir com salário final). Sem TRCT no Onvio → marca "pendente" (igual
ao VT/VR do Kalel); preenche sozinho quando o contador subir o termo e o Onvio sincronizar.
"""

from __future__ import annotations

import io
import re
import unicodedata

import fitz
from sqlalchemy import text

from modules.gdrive.services.gdrive_service import gdrive_service
from modules.gedeon.services.comprovante_generator import gerar_comprovante_pdf
from modules.gedeon.services.inter_kit_service import extrair_funcionarios_folha
from modules.gedeon.services.kit_layout import _arquivo_ja_existe, pasta_kit_arquivo
from modules.gedeon.services.onvio_kit_service import _garantir_binario


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper().strip()


def _valor_brl(s: str) -> float | None:
    try:
        return float(s.replace(".", "").replace(",", "."))
    except Exception:
        return None


def _mes_kit_ym(competencia: str) -> tuple[int, int]:
    m, a = int(competencia.split(".")[0]), int(competencia.split(".")[1])
    return (a, m + 1) if m < 12 else (a + 1, 1)


def demitidos_da_competencia(db, competencia: str) -> list[dict]:
    """Demitidos cuja rescisão é PROCESSADA no mês do kit (M = competência+1) — alinha com a
    referência (kit Junho ← demitidos de junho). Retorna [{nome, cpf, data_demissao}]."""
    a, m = _mes_kit_ym(competencia)
    ini = f"{a}-{m:02d}-01"
    a2, m2 = (a, m + 1) if m < 12 else (a + 1, 1)
    fim = f"{a2}-{m2:02d}-01"
    rows = db.execute(
        text(
            "SELECT nome, cpf, data_demissao FROM employees "
            "WHERE data_demissao >= :i AND data_demissao < :f ORDER BY data_demissao"
        ),
        {"i": ini, "f": fim},
    ).fetchall()
    return [{"nome": r[0], "cpf": r[1], "data_demissao": r[2]} for r in rows]


def _mapa_funcionario_condominio(db, competencia: str, condominios: list[str]) -> list[tuple[set, str]]:
    """[(set(tokens_nome), condomínio)] das folhas de cada kit (inclui demitidos)."""
    if not gdrive_service._service:
        gdrive_service.check_status()
    svc = gdrive_service._service
    from googleapiclient.http import MediaIoBaseDownload

    out: list[tuple[set, str]] = []
    for cond in condominios:
        folder = pasta_kit_arquivo(cond, competencia, "Folha de Pagamento.pdf")
        if not folder:
            continue
        it = (
            svc.files()
            .list(
                q=f"'{folder}' in parents and name='Folha de Pagamento.pdf' and trashed=false",
                fields="files(id)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
            .get("files", [])
        )
        if not it:
            continue
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, svc.files().get_media(fileId=it[0]["id"]))
        d = False
        while not d:
            _, d = dl.next_chunk()
        for nome, _r in extrair_funcionarios_folha(buf.getvalue()):
            toks = set(_norm(nome).split())
            if toks:
                out.append((toks, cond))
    return out


def _condominio_de(nome: str, mapa: list[tuple[set, str]]) -> str | None:
    tok = set(_norm(nome).split())
    if len(tok) < 2:
        return None
    # casa por subconjunto de tokens; só vale se levar a um único condomínio
    cands = {cond for ts, cond in mapa if tok <= ts or ts <= tok}
    return next(iter(cands)) if len(cands) == 1 else None


# Pacote de rescisão — busca AMPLA por NOME do arquivo (a categoria do Onvio vem errada:
# Carta de Demissão veio como guia_issqn, GFD FGTS RESCISÃO como fgts_guia, etc.). Cada item:
# (regex no nome, nome final no kit, é_ancora_valor). 1ª que casar classifica o doc.
RESCISAO_PADROES = [
    (r"\bTRCT\b|TERMO.*RESCIS|RESCIS.*CONTRATO", "Termo de Rescisão do Contrato de Trabalho_{n}.pdf", True),
    (r"RELAT[ÓO]?R?I?O?.*FGTS.*RESCIS", "Relatório GFD FGTS Rescisão_{n}.pdf", False),
    (r"GFD.*FGTS.*RESCIS|FGTS.*RESCIS", "GFD FGTS Rescisão_{n}.pdf", False),
    (r"CARTA.*DEMISS|PEDIDO.*DEMISS", "Carta de Pedido de Demissão_{n}.pdf", False),
    (r"AVISO.*PR[ÉE]VIO", "Aviso Prévio_{n}.pdf", False),
    (r"\bASO\b|DEMISSIONAL|PER[ÍI]CIA", "ASO Demissional_{n}.pdf", False),
    (r"SIMULA.*RESCIS", "Simulação de Rescisão_{n}.pdf", False),
    (r"HOMOLOG|QUITA[ÇC]|GRRF|GRFC|SEGURO.?DESEMP|CHAVE.*CONECTIV", "Rescisão - Outros_{n}.pdf", False),
]


def _docs_rescisao_onvio(db, nome: str) -> list[dict]:
    """Busca AMPLA: TODOS os docs do Onvio cujo nome casa o funcionário E qualquer variante de
    rescisão — ignorando a `categoria` (que o Onvio classifica errado)."""
    p = _norm(nome).split()
    if len(p) < 2:
        return []
    primeiro, ultimo = p[0], p[-1]
    # busca pelo PRIMEIRO nome (docs do Onvio às vezes têm só o 1º nome, ex.: "Carta - Railson");
    # o PADRÃO de rescisão é o filtro forte. Se o doc traz um sobrenome, tem que bater com o último.
    rows = db.execute(
        text(
            "SELECT nome_arquivo, caminho_local, onvio_folder_id, onvio_id "
            "FROM onvio_documents WHERE nome_arquivo ILIKE :l1"
        ),
        {"l1": f"%{primeiro}%"},
    ).fetchall()
    out = []
    for nm, caminho, folder_id, oid in rows:
        nmn = _norm(nm)
        # casa um padrão de rescisão?
        modelo = ancora = None
        for rx, mod, anc in RESCISAO_PADROES:
            if re.search(rx, nmn, re.I):
                modelo, ancora = mod, anc
                break
        if not modelo:
            continue
        # parte do nome no arquivo (depois de "_" ou "-"): se tiver >1 token e NÃO contiver o
        # último nome do funcionário, é outra pessoa (ex.: outro "Railson") → descarta
        m = re.split(r"[_\-]", nm)
        trecho_nome = _norm(m[-1])
        toks = [t for t in trecho_nome.split() if len(t) > 2]
        if len(toks) >= 2 and ultimo not in toks and primeiro not in toks:
            continue
        out.append(
            {
                "nome": nm,
                "caminho": caminho,
                "folder_id": folder_id,
                "onvio_id": oid,
                "modelo": modelo,
                "ancora": ancora,
            }
        )
    return out


def _valor_liquido_trct(pdf_bytes: bytes) -> float | None:
    try:
        txt = "\n".join(p.get_text() for p in fitz.open(stream=pdf_bytes, filetype="pdf"))
    except Exception:
        return None
    m = re.search(
        r"(?:VALOR L[ÍI]QUIDO|L[ÍI]QUIDO A RECEBER|TOTAL L[ÍI]QUIDO)\D{0,40}"
        r"(\d{1,3}(?:\.\d{3})*,\d{2})",
        txt,
        re.I,
    )
    return _valor_brl(m.group(1)) if m else None


def _pix_rescisao(txs: list[dict], nome: str, data_dem, valor_trct: float):
    """Acha o(s) PIX do Inter pro demitido que casa(m) o valor líquido do TRCT (âncora).
    Retorna (valor, data, id) do PIX único; senão None (parcial/ambíguo → não força)."""
    if not txs or not valor_trct:
        return None
    alvo = set(_norm(nome).split())
    cands = []
    for t in txs:
        if t.get("tipo_operacao") != "D":
            continue
        blob = _norm(f"{t.get('descricao', '')} {t.get('titulo', '')} {t.get('destinatario', '')}")
        if not (alvo and {p for p in alvo if len(p) > 3} & set(blob.split())):
            continue
        v = float(t.get("valor", 0) or 0)
        cands.append((v, t.get("data"), t.get("id")))
    # casa pelo valor do TRCT (tolerância R$1)
    for v, dt, tid in cands:
        if abs(v - valor_trct) <= 1.0:
            return {"valor": v, "data": dt, "id": tid}
    return None


# nomes finais no kit (convenção da referência Innovare)
NOME_TRCT = "Termo de Rescisão do Contrato de Trabalho_{n}.pdf"
NOME_ASO = "ASO Demissional_{n}.pdf"
NOME_CARTA = "Carta de Pedido de Demissão_{n}.pdf"
NOME_COMPROV = "Comprovante de Pagamento de Rescisão_{n}.pdf"


def arquivar_rescisao(
    competencia: str,
    condominios: list[str],
    db,
    onvio_client=None,
    txs: list[dict] | None = None,
    emitido_em: str | None = None,
    dry_run: bool = False,
) -> dict:
    rel = {"competencia": competencia, "demitidos": 0, "arquivados": 0, "pendentes": []}
    demitidos = demitidos_da_competencia(db, competencia)
    rel["demitidos"] = len(demitidos)
    if not demitidos:
        return rel
    mapa = _mapa_funcionario_condominio(db, competencia, condominios)

    for dem in demitidos:
        nome, cpf, data_dem = dem["nome"], dem.get("cpf"), dem["data_demissao"]
        primeiro = nome.split()[0].title() if nome else ""
        ult = nome.split()[-1].title() if len(nome.split()) > 1 else ""
        rotulo = f"{primeiro} {ult}".strip()
        cond = _condominio_de(nome, mapa)
        falta = []
        if not cond:
            rel["pendentes"].append({"funcionario": nome, "motivo": "condomínio não mapeado"})
            continue

        # 1+2) TODOS os docs de rescisão do Onvio (busca AMPLA por nome) — TRCT é âncora do valor
        valor_trct = None
        docs = _docs_rescisao_onvio(db, nome)
        achou_trct = False
        for d in docs:
            if d["ancora"]:
                achou_trct = True
            if dry_run:
                continue
            path = _garantir_binario(onvio_client, d["caminho"], d["folder_id"], d["onvio_id"])
            if not path:
                continue
            fn = d["modelo"].format(n=rotulo)
            folder = pasta_kit_arquivo(cond, competencia, fn)
            if folder and not _arquivo_ja_existe(folder, fn):
                if gdrive_service.fazer_upload_arquivo(path, folder, fn):
                    rel["arquivados"] += 1
            if d["ancora"]:
                try:
                    valor_trct = _valor_liquido_trct(open(path, "rb").read())
                except Exception:
                    pass
        if not achou_trct:
            falta.append("TRCT")

        # 3) Comprovante de verbas (Inter) ANCORADO no valor do TRCT
        if valor_trct and txs and not dry_run:
            pix = _pix_rescisao(txs, nome, data_dem, valor_trct)
            if pix:
                pdf = gerar_comprovante_pdf(
                    favorecido=nome,
                    cpf=cpf,
                    valor=pix["valor"],
                    data_pagamento=pix["data"],
                    descricao="Verbas rescisórias",
                    id_transacao=pix.get("id"),
                    competencia=competencia,
                    condominio=cond,
                    emitido_em=emitido_em,
                )
                fn = NOME_COMPROV.format(n=rotulo)
                folder = pasta_kit_arquivo(cond, competencia, fn)
                if folder and not _arquivo_ja_existe(folder, fn):
                    gdrive_service.fazer_upload_arquivo_bytes(pdf, folder, fn) if hasattr(
                        gdrive_service, "fazer_upload_arquivo_bytes"
                    ) else _upload_bytes(folder, fn, pdf)
                    rel["arquivados"] += 1
            else:
                falta.append("comprovante de verbas (PIX não casou o valor do TRCT)")
        elif not valor_trct:
            falta.append("comprovante de verbas (depende do TRCT)")

        if falta:
            rel["pendentes"].append({"funcionario": nome, "condominio": cond, "falta": falta})
    return rel


def _upload_bytes(folder_id: str, nome: str, pdf: bytes) -> bool:
    """Sobe bytes pro Drive (fallback se o gdrive_service não tiver helper de bytes)."""
    import os
    import tempfile

    fd, tmp = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(pdf)
        return gdrive_service.fazer_upload_arquivo(tmp, folder_id, nome)
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
