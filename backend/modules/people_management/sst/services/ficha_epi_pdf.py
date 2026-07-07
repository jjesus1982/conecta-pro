"""Ficha de EPI — PDF padrão-ouro Conecta Mais (NR-6 / NR-1).

Documento de entrega de EPI com: identificação do colaborador, tabela dos EPIs
entregues (nome, CA, quantidade, datas), termo de responsabilidade NR-6 e campo
de assinatura DIGITAL — somente do FUNCIONÁRIO (incluir_empresa=False, mesmo
padrão dos recibos de recebimento).

Uma folha A4, branded (pdf_branding), texto sempre dentro das caixas.
Quando a ficha já está assinada, o bloco de autenticidade exibe o hash REAL
gravado em portal_digital_signatures — nunca fabricado.
"""

from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules.crm.services import pdf_branding as B

# reusa os helpers do padrão-ouro do holerite (mesma identidade visual)
from modules.people_management.folha.services.holerite_pdf import (
    _cbo,
    _cell,
    _fmt_cpf,
    _titulo,
)

def _br_date(v) -> str:
    """dd/mm/aaaa a partir de date OU string ISO (itens da ficha são snapshot JSON)."""
    if not v:
        return "—"
    s = str(v)[:10]
    try:
        from datetime import date as _d

        return _d.fromisoformat(s).strftime("%d/%m/%Y")
    except ValueError:
        return B.br_date(v)


_TERMO_NR6 = (
    "<b>TERMO DE RESPONSABILIDADE (NR-6).</b> Declaro que recebi da "
    "<b>{empresa}</b> (CNPJ {cnpj}), gratuitamente, os Equipamentos de Proteção "
    "Individual (EPI) relacionados nesta ficha, em perfeito estado de conservação e "
    "funcionamento, com orientação sobre o uso correto. Comprometo-me, nos termos do "
    "item 6.7 da NR-6 e do art. 158 da CLT, a: usá-los apenas para a finalidade a que "
    "se destinam; responsabilizar-me pela guarda e conservação; comunicar qualquer "
    "alteração que os torne impróprios para uso; e cumprir as determinações do "
    "empregador sobre o uso adequado. Estou ciente de que a recusa injustificada ao "
    "uso do EPI constitui ato faltoso (CLT, art. 158, parágrafo único, alínea b) e de "
    "que devo devolver os equipamentos em caso de desligamento ou substituição."
)


def montar_ficha_epi_pdf(ficha: dict, funcionario: dict | None = None) -> bytes:
    """Gera o PDF da Ficha de EPI a partir do dict de sst_fichas_epi (to_dict).

    ficha: {ficha_id, employee_nome, itens: [{epi_nome, ca, quantidade,
            data_entrega, data_validade}], status, assinatura_hash, assinado_em}
    funcionario: dict do employees (cpf, cargo, posto) — campos ausentes ficam
    "—" (aguardando dado), nunca inventados.
    """
    funcionario = funcionario or {}
    st = B.styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=40 * mm, bottomMargin=16 * mm, leftMargin=16 * mm, rightMargin=16 * mm
    )
    W = A4[0] - 32 * mm
    story: list = []

    nome = ficha.get("employee_nome") or funcionario.get("nome") or "—"
    cargo = funcionario.get("cargo") or "—"

    # ── Identificação ──
    ident = [
        [
            _cell("Funcionário", st, bold=True),
            _cell(nome, st),
            _cell("Ficha nº", st, bold=True),
            _cell(str(ficha.get("ficha_id", "—"))[:8].upper(), st),
        ],
        [
            _cell("Cargo / Função", st, bold=True),
            _cell(cargo, st),
            _cell("CBO", st, bold=True),
            _cell(_cbo(cargo, funcionario), st),
        ],
        [
            _cell("CPF", st, bold=True),
            _cell(_fmt_cpf(funcionario.get("cpf")), st),
            _cell("Emitida em", st, bold=True),
            _cell(_br_date(ficha.get("created_at")), st),
        ],
    ]
    t_id = Table(ident, colWidths=[30 * mm, W / 2 - 30 * mm, 24 * mm, W / 2 - 24 * mm])
    t_id.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E1F2")),
                ("BACKGROUND", (0, 0), (0, -1), B.FUNDO_CLARO),
                ("BACKGROUND", (2, 0), (2, -1), B.FUNDO_CLARO),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(_titulo("IDENTIFICAÇÃO DO COLABORADOR", st, "user"))
    story.append(t_id)
    story.append(Spacer(1, 3 * mm))

    # ── EPIs entregues ──
    linhas = [
        [
            _cell("EPI", st, bold=True, cor=colors.white),
            _cell("CA", st, bold=True, cor=colors.white),
            _cell("Qtd.", st, bold=True, right=True, cor=colors.white),
            _cell("Entrega", st, bold=True, cor=colors.white),
            _cell("Validade", st, bold=True, cor=colors.white),
        ]
    ]
    for item in ficha.get("itens") or []:
        linhas.append(
            [
                _cell(str(item.get("epi_nome") or "—"), st),
                _cell(str(item.get("ca") or "—"), st),
                _cell(str(item.get("quantidade") or 1), st, right=True),
                _cell(_br_date(item.get("data_entrega")), st),
                _cell(_br_date(item.get("data_validade")), st),
            ]
        )
    if len(linhas) == 1:
        linhas.append([_cell("— sem itens (aguardando dado) —", st), "", "", "", ""])
    t_epi = Table(linhas, colWidths=[W - 96 * mm, 22 * mm, 14 * mm, 30 * mm, 30 * mm], repeatRows=1)
    t_epi.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E1F2")),
                ("BACKGROUND", (0, 0), (-1, 0), B.AZUL_ESCURO),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(_titulo("EQUIPAMENTOS DE PROTEÇÃO INDIVIDUAL ENTREGUES", st, "doc"))
    story.append(t_epi)

    # ── Termo de responsabilidade NR-6 ──
    story.append(Spacer(1, 4 * mm))
    story.append(
        Paragraph(_TERMO_NR6.format(empresa=B.EMPRESA["nome"], cnpj=B.EMPRESA["cnpj"]), st["corpo"])
    )

    # ── Autenticidade (só quando REALMENTE assinada) ──
    assinado_em = ficha.get("assinado_em")
    ass_hash = ficha.get("assinatura_hash")
    if ficha.get("status") == "assinada" and ass_hash:
        story.append(Spacer(1, 3 * mm))
        story.append(
            Paragraph(
                f"<b>ASSINADA DIGITALMENTE</b> pelo funcionário via Conecta PRO em "
                f"{_br_date(assinado_em)} · "
                f"Hash SHA-256: <font size=7>{ass_hash}</font>",
                st["small"],
            )
        )
        data_str = _br_date(assinado_em) if assinado_em else None
    else:
        data_str = None

    # ── Assinatura — SÓ do funcionário (padrão dos recibos: incluir_empresa=False) ──
    story += B.campos_assinatura(
        st,
        funcionario_nome=nome,
        funcionario_cpf=_fmt_cpf(funcionario.get("cpf")),
        data_str=data_str,
        data_prefixo="Assinada em " if data_str else "",
        digital_funcionario=True,
        espaco_antes=8,
        incluir_empresa=False,  # Ficha de EPI: termo de recebimento — só o FUNCIONÁRIO assina
    )

    doc.build(
        story,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo="FICHA DE EPI — NR-6"),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo="FICHA DE EPI — NR-6"),
    )
    return buf.getvalue()
