"""Relatório de PAGAMENTO da folha, no timbrado padrão-ouro da Conecta Mais.

Origem: 22/09/2026. Depois de pagar os 49 do adiantamento, o Jordan abriu a tela e disse:
«o relatório do que foi pago está fora do padrão ouro do Conecta PRO». Estava: eu tinha
entregue uma TABELA NA TELA e chamado de relatório. Relatório da empresa é documento —
sai com logo real, cor oficial, rodapé com CNPJ e 0800.

Reusa `pdf_branding` (a mesma marca do holerite, do contrato e da proposta) e segue a
forma de `folha_pdf`: paisagem, resumo em cards, tabela e nota de rodapé.

O que este papel tem e a tela não tinha:
  · o CNPJ CERTO no timbrado — a folha CLT é da PATRIMONIAL, e o default do branding é a
    Eletrônica. Sair com o CNPJ errado num relatório de pagamento é o tipo de erro que só
    aparece quando o contador devolve;
  · o COMPROVANTE do banco (e2e) por linha — sem ele o relatório só repete o que nós
    mesmos escrevemos, e o que se confere é o que o BANCO fez;
  · a hora de cada pagamento, que é o que casa com o extrato.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules.crm.services.pdf_branding import (
    AZUL_ESCURO,
    EMPRESA,
    EMPRESA_PATRIMONIAL,
    FONTE,
    FONTE_B,
    FUNDO_CLARO,
    TEXTO,
    brl,
    header_footer,
    secao,
    styles,
)

_ROTULO_PARCELA = {1: "Adiantamento (40%)", 2: "Saldo (60%)"}


def _empresa_do_cnpj(cnpj: str | None) -> dict | None:
    d = "".join(ch for ch in str(cnpj or "") if ch.isdigit())
    if not d:
        return None
    for cand in (EMPRESA_PATRIMONIAL, EMPRESA):
        if d == "".join(ch for ch in cand["cnpj"] if ch.isdigit()):
            return cand
    return None


def montar_relatorio_pagamento(dados: dict[str, Any]) -> bytes:
    """BYTES do PDF. `dados`: {competencia 'MM/AAAA', parcela, empresa_cnpj, itens[...]}.

    Cada item: {nome, cpf, chave, valor, quando, comprovante, banco}.
    """
    st = styles()
    comp = str(dados.get("competencia") or "—")
    parcela = int(dados.get("parcela") or 1)
    rotulo = _ROTULO_PARCELA.get(parcela, f"Parcela {parcela}")
    itens: list[dict] = list(dados.get("itens") or [])
    emp = _empresa_do_cnpj(dados.get("empresa_cnpj"))

    pagina = landscape(A4)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=pagina,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=40 * mm,
        bottomMargin=20 * mm,
        title=f"Relatorio de Pagamento {comp} - {rotulo}",
    )
    story: list = []

    story.append(
        Paragraph(
            f"<b>Competência:</b> {comp} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Parcela:</b> {rotulo} "
            f"&nbsp;&nbsp;|&nbsp;&nbsp; <b>Pagamentos:</b> {len(itens)}",
            st["small"],
        )
    )
    story.append(Paragraph(f"Emitido em {datetime.now().strftime('%d/%m/%Y %H:%M')}", st["small"]))
    story.append(Spacer(1, 5 * mm))

    total = round(sum(float(i.get("valor") or 0) for i in itens), 2)
    com_comprov = sum(1 for i in itens if str(i.get("comprovante") or "").strip() not in ("", "—"))
    quando = [i.get("quando") for i in itens if i.get("quando")]
    janela = "—"
    if quando:
        ini, fim = min(quando), max(quando)
        janela = (
            ini.strftime("%d/%m/%Y %H:%M")
            if ini == fim
            else f"{ini.strftime('%d/%m/%Y %H:%M')} → {fim.strftime('%H:%M')}"
        )

    story += secao("Resumo do pagamento", st)
    resumo_rows = [
        ["Pessoas pagas", str(len(itens)), "Total pago", brl(total)],
        ["Com comprovante do banco", f"{com_comprov} de {len(itens)}", "Quando saiu", janela],
    ]
    tbl_resumo = Table(resumo_rows, colWidths=[62 * mm, 68 * mm, 62 * mm, 77 * mm])
    tbl_resumo.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), FONTE),
                ("FONTNAME", (0, 0), (0, -1), FONTE_B),
                ("FONTNAME", (2, 0), (2, -1), FONTE_B),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TEXTCOLOR", (0, 0), (-1, -1), TEXTO),
                ("BACKGROUND", (0, 0), (-1, -1), FUNDO_CLARO),
                ("GRID", (0, 0), (-1, -1), 0.4, AZUL_ESCURO),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(tbl_resumo)
    story.append(Spacer(1, 6 * mm))

    story += secao("Pagamentos", st)
    linhas = [["#", "Colaborador", "CPF", "Chave PIX", "Banco de destino", "Valor", "Quando saiu", "Comprovante"]]
    for n, i in enumerate(itens, start=1):
        q = i.get("quando")
        linhas.append(
            [
                str(n),
                str(i.get("nome") or "—")[:34],
                str(i.get("cpf") or "—"),
                str(i.get("chave") or "—")[:28],
                str(i.get("banco") or "—")[:24],
                brl(float(i.get("valor") or 0)),
                q.strftime("%d/%m/%Y %H:%M") if q else "—",
                str(i.get("comprovante") or "—")[:30],
            ]
        )
    linhas.append(["", "TOTAL", "", "", "", brl(total), "", ""])

    tbl = Table(linhas, colWidths=[8 * mm, 50 * mm, 26 * mm, 44 * mm, 38 * mm, 24 * mm, 28 * mm, 51 * mm], repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), FONTE_B),
                ("FONTNAME", (0, 1), (-1, -1), FONTE),
                ("FONTNAME", (0, -1), (-1, -1), FONTE_B),
                ("FONTSIZE", (0, 0), (-1, -1), 7.2),
                ("BACKGROUND", (0, 0), (-1, 0), AZUL_ESCURO),
                ("TEXTCOLOR", (0, 0), (-1, 0), FUNDO_CLARO),
                ("TEXTCOLOR", (0, 1), (-1, -1), TEXTO),
                ("GRID", (0, 0), (-1, -1), 0.3, AZUL_ESCURO),
                ("ALIGN", (5, 1), (5, -1), "RIGHT"),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [None, FUNDO_CLARO]),
                ("BACKGROUND", (0, -1), (-1, -1), FUNDO_CLARO),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ]
        )
    )
    story.append(tbl)

    # Honestidade sobre o que ainda não dá para afirmar: a coluna do banco vem do EXTRATO
    # conciliado, e a conciliação roda no dia seguinte. Sem esta nota, «—» seria lido como
    # «não identificamos o banco» em vez de «o extrato ainda não chegou».
    sem_banco = sum(1 for i in itens if str(i.get("banco") or "—").strip() in ("", "—"))
    nota_banco = ""
    if sem_banco:
        nota_banco = (
            f" <b>{sem_banco} linha(s) ainda sem o banco de destino</b>: esse dado vem do "
            "extrato conciliado, que entra no dia seguinte ao pagamento — não significa "
            "que o pagamento falhou."
        )
    story.append(Spacer(1, 6 * mm))
    story.append(
        KeepTogether(
            Paragraph(
                "Documento gerado automaticamente pelo Conecta PRO. A coluna <b>Comprovante</b> traz o "
                "identificador do PIX devolvido pelo banco (EndToEnd/código de solicitação) — é por ele "
                "que cada linha se confere no extrato." + nota_banco + " Confidencial.",
                st["small"],
            )
        )
    )

    def _hf(canvas, doc_):
        header_footer(canvas, doc_, titulo="RELATÓRIO DE PAGAMENTO", empresa=emp, pagesize=pagina)

    doc.build(story, onFirstPage=_hf, onLaterPages=_hf)
    return buf.getvalue()
