"""
GEDEON — Fatia 2: monta os comprovantes de pagamento de salário no workspace.

Fluxo (por condomínio/competência):
  1. Extrai os funcionários CLT da folha (PDF).
  2. Busca no Banco Inter (extrato/completo do mês de PAGAMENTO = competência+1) o
     PIX de salário de cada um (maior débito PIX > piso, casado por nome).
  3. GERA o comprovante (comprovante_generator) — produção interna do Conecta PRO.
  4. Arquiva no workspace: [AAAA-MM competência]/[Condomínio]/02 - Folha de Pagamento/.
  5. Âncora oficial: baixa o PDF do extrato do Inter (/extrato/exportar) do período.

Salário é pago em arrears (folha mês X → PIX ~dia 5 do mês X+1).
"""

from __future__ import annotations

import logging
import os
import re
import tempfile

from modules.gdrive.services.gdrive_service import gdrive_service
from modules.gedeon.services.comprovante_generator import gerar_comprovante_pdf
from modules.gedeon.services.kit_layout import (
    ROOT_WORKSPACE_ID,
    _arquivo_ja_existe,
    _garantir_pasta,
    mes_kit_de_competencia,
    pasta_kit_arquivo,
    primeiro_e_ultimo,
)

logger = logging.getLogger(__name__)

PISO_SALARIO = 400.0  # abaixo disso é VA/VT avulso (R$32-90), não salário


def _mes_pagamento(competencia: str) -> tuple[str, str]:
    """'05.2026' -> ('2026-06-01','2026-06-30') (mês seguinte = pagamento)."""
    mes, ano = competencia.split(".")
    m, a = int(mes), int(ano)
    m += 1
    if m > 12:
        m, a = 1, a + 1
    ultimo = [31, 29 if a % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return f"{a}-{m:02d}-01", f"{a}-{m:02d}-{ultimo:02d}"


def extrair_funcionarios_folha(pdf_bytes: bytes) -> list[tuple[str, bool]]:
    """Funcionários da folha como (nome, desligado). desligado=True se a 'Situação:'
    do funcionário é 'Demitido' (a folha traz o status logo após o CPF). Sinal preciso
    e localizado — quem foi demitido recebe pacote de rescisão, não comprovante de salário."""
    import fitz

    txt = "\n".join(p.get_text() for p in fitz.open(stream=pdf_bytes, filetype="pdf"))
    linhas = txt.split("\n")
    out: dict[str, bool] = {}
    for i, l in enumerate(linhas):
        m = re.match(r"^\d{1,3}\s+([A-ZÀ-Ú][A-ZÀ-Ú ]{8,50})$", l.strip())
        if m and any(re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}", linhas[j]) for j in range(i, min(i + 7, len(linhas)))):
            nome = m.group(1).strip()
            bloco = " ".join(linhas[i + 1 : i + 9])  # janela local (status fica logo após o CPF)
            desligado = "demitido" in bloco.lower() or "rescis" in bloco.lower()
            out[nome] = out.get(nome, False) or desligado
    return list(out.items())


async def _extrato_completo_todas_paginas(adapter, ini: str, fim: str) -> list[dict]:
    """Busca TODAS as páginas do extrato/completo (a API pagina 50/página, DESC)."""
    import asyncio

    todas: list[dict] = []
    pagina = 0
    while True:
        r = None
        for tentativa in range(4):
            try:
                r = await adapter._request(
                    "GET",
                    "/banking/v2/extrato/completo",
                    params={"dataInicio": ini, "dataFim": fim, "pagina": pagina, "tamanhoPagina": 100},
                )
                break
            except Exception as e:
                if "429" in str(e) and tentativa < 3:
                    await asyncio.sleep(2 * (tentativa + 1))  # backoff
                    continue
                raise
        txs = r.get("transacoes") or []
        todas.extend(txs)
        if not isinstance(r, dict) or r.get("ultimaPagina", True) or not txs:
            break
        pagina += 1
        await asyncio.sleep(0.4)  # gentil com o rate-limit do Inter
        if pagina > 50:  # trava de segurança
            break
    return todas


def _casar_salario(funcionario: str, transacoes: list[dict]) -> dict | None:
    """Maior PIX de débito > piso cujo favorecido casa o nome (primeiro+último)."""
    p, u = funcionario.split()[0].upper(), funcionario.split()[-1].upper()
    cands = []
    for t in transacoes:
        if t.get("tipoOperacao") != "D":
            continue
        try:
            v = float(t.get("valor", 0))
        except Exception:
            continue
        if v < PISO_SALARIO:
            continue
        alvo = (str(t.get("descricao", "")) + " " + str(t.get("detalhes", {}))).upper()
        if p in alvo and u in alvo:
            cands.append((v, t))
    if not cands:
        return None
    return max(cands, key=lambda x: x[0])[1]


async def buscar_extrato_pagamento(competencia: str, adapter) -> list[dict]:
    """Busca o extrato/completo do mês de pagamento UMA vez (reusar p/ vários condomínios)."""
    ini, fim = _mes_pagamento(competencia)
    await adapter.authenticate()
    return await _extrato_completo_todas_paginas(adapter, ini, fim)


async def montar_comprovantes(
    competencia: str,
    condominio: str,
    folha_pdf: bytes,
    adapter,
    emitido_em: str,
    dry_run: bool = False,
    txs: list[dict] | None = None,
) -> dict:
    """Monta os comprovantes de salário de um condomínio/competência no workspace.

    Passe `txs` (extrato já buscado) para evitar rate-limit ao rodar vários condomínios.
    """
    func_status = extrair_funcionarios_folha(folha_pdf)
    funcionarios = [n for n, resc in func_status if not resc]
    rescisoes = [n for n, resc in func_status if resc]
    if txs is None:
        txs = await buscar_extrato_pagamento(competencia, adapter)

    rel = {
        "competencia": competencia,
        "condominio": condominio,
        "funcionarios": len(funcionarios),
        "gerados": 0,
        "sem_pix": [],
        "rescisoes": rescisoes,
        "dry_run": dry_run,
        "detalhes": [],
    }

    # pasta do kit: [Condomínio]/[Mês]/[1. Folha e Pessoal] (todos os comprovantes de salário)
    if not dry_run:
        sub_folder = pasta_kit_arquivo(condominio, competencia, "Comprovante de Pagamento de Salário.pdf")

    for nome in funcionarios:
        t = _casar_salario(nome, txs)
        if not t:
            rel["sem_pix"].append(nome)
            continue
        det = t.get("detalhes", {}) or {}
        valor = t.get("valor")
        rel["detalhes"].append(f"{nome}: R${valor} em {t.get('dataTransacao')}")
        if dry_run:
            rel["gerados"] += 1
            continue
        pdf = gerar_comprovante_pdf(
            favorecido=det.get("nomeRecebedor") or nome,
            cpf=det.get("cpfCnpjRecebedor") or det.get("cpfCnpj"),
            valor=valor,
            data_pagamento=t.get("dataTransacao"),
            descricao=(t.get("titulo") or "PIX enviado").strip(),
            id_transacao=det.get("endToEndId") or t.get("idTransacao"),
            competencia=competencia,
            condominio=condominio,
            emitido_em=emitido_em,
        )
        fn = f"Comprovante de Pagamento de Salário_{primeiro_e_ultimo(det.get('nomeRecebedor') or nome)}.pdf"
        if _arquivo_ja_existe(sub_folder, fn):
            rel["gerados"] += 1
            continue
        path = os.path.join(tempfile.gettempdir(), fn)
        with open(path, "wb") as fh:
            fh.write(pdf)
        up = gdrive_service.fazer_upload_arquivo(path, sub_folder, fn)
        if up:
            rel["gerados"] += 1
    return rel


async def baixar_extrato_oficial(competencia: str, condominio: str, adapter) -> dict | None:
    """Âncora oficial: PDF do extrato do Inter do período de pagamento → workspace."""
    import base64

    ini, fim = _mes_pagamento(competencia)
    await adapter.authenticate()
    r = await adapter._request(
        "GET",
        "/banking/v2/extrato/exportar",
        params={"dataInicio": ini, "dataFim": fim},
    )
    b64 = r.get("pdf") if isinstance(r, dict) else None
    if not b64:
        return None
    # vai pra ÁREA DE AUDITORIA (ATLAS), não pro kit do cliente
    if not gdrive_service._service:
        gdrive_service.check_status()
    cache: dict = {}
    aud = _garantir_pasta(cache, "_AUDITORIA (ATLAS)", ROOT_WORKSPACE_ID)
    cond_folder = _garantir_pasta(cache, condominio, aud)
    sub_folder = _garantir_pasta(cache, mes_kit_de_competencia(competencia), cond_folder)
    fn = f"Extrato Oficial Inter (prova pagamentos) - {competencia}.pdf"
    if _arquivo_ja_existe(sub_folder, fn):
        return {"name": fn, "ja_existia": True}
    path = os.path.join(tempfile.gettempdir(), fn)
    with open(path, "wb") as fh:
        fh.write(base64.b64decode(b64))
    return gdrive_service.fazer_upload_arquivo(path, sub_folder, fn)
