"""Recibo de Vale-Transporte e Vale-Refeição (padrão-ouro Conecta Mais).

Documento próprio (separado do holerite) que registra os benefícios VT/VR concedidos
na competência, a co-participação do funcionário (descontada) e o líquido recebido,
com declaração de recebimento e assinaturas (funcionário digital via Portal + empresa).

Uma folha A4, branded, texto sempre dentro das caixas.
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
    _MESES,
    _cbo,
    _cell,
    _fmt_cpf,
    _titulo,
)


def _brl_num(v) -> str:
    return B.brl(v).replace("R$ ", "")


def montar_recibo_vt_vr_pdf(
    holerite: dict,
    funcionario: dict | None = None,
    vt_concedido: float | None = None,
    signatarios: list | None = None,
) -> bytes:
    """Gera o PDF do recibo de VT e VR a partir do dict de calcular_folha_colaborador.

    vt_concedido: valor do crédito de vale-transporte concedido (tarifa × dias). Quando
    não informado, o campo fica em branco (aguardando dado) — nunca inventado.
    """
    funcionario = funcionario or {}
    st = B.styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=40 * mm, bottomMargin=16 * mm, leftMargin=16 * mm, rightMargin=16 * mm
    )
    W = A4[0] - 32 * mm
    mes = int(holerite.get("mes") or 0)
    comp = f"{_MESES[mes] if 0 < mes < 13 else mes}/{holerite.get('ano', '')}"
    cargo = holerite.get("cargo", "—")
    story: list = []

    # ── Identificação ──
    ident = [
        [
            _cell("Funcionário", st, bold=True),
            _cell(holerite.get("employee_nome", "—"), st),
            _cell("Competência", st, bold=True),
            _cell(comp, st),
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
            _cell("Posto", st, bold=True),
            _cell(funcionario.get("posto", "—"), st),
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

    # ── Benefícios (VT + VR) — dias/valores conforme a escala (calculados na folha) ──
    vr_dia = float(holerite.get("vr_dia") or 22.0)
    vt_dia = float(holerite.get("vt_dia") or 10.0)
    dias_vr = int(holerite.get("dias_vr") or 0)
    dias_vt = int(holerite.get("dias_vt") or 0)
    co_vr = float(holerite.get("desconto_vr") or 0)
    co_vt = float(holerite.get("desconto_vt") or 0)
    vr_conc = float(holerite.get("vr_concedido") or (vr_dia * dias_vr))
    # VT concedido: override manual (param) tem prioridade; senão o valor calculado pela escala
    if vt_concedido is None:
        vt_concedido = float(holerite.get("vt_concedido") or 0)
    vr_liq = vr_conc - co_vr
    tem_vt = bool(vt_concedido)
    vt_liq = (vt_concedido - co_vt) if tem_vt else None

    def _c(txt, right=False, bold=False):
        return _cell(txt, st, right=right, bold=bold)

    head = [
        [
            _cell("Benefício", st, bold=True, cor=colors.white),
            _cell("Referência", st, bold=True, cor=colors.white),
            _cell("Concedido", st, bold=True, right=True, cor=colors.white),
            _cell("Co-part.", st, bold=True, right=True, cor=colors.white),
            _cell("Líquido", st, bold=True, right=True, cor=colors.white),
        ]
    ]
    linhas = [
        [
            _c("Vale-Refeição"),
            _c(f"{dias_vr} dias × R$ {vr_dia:.2f}".replace(".", ",")),
            _c(_brl_num(vr_conc), right=True),
            _c(_brl_num(co_vr), right=True),
            _c(_brl_num(vr_liq), right=True, bold=True),
        ],
        [
            _c("Vale-Transporte"),
            _c(f"{dias_vt} dias × R$ {vt_dia:.2f}".replace(".", ",") if tem_vt else "crédito no cartão-transporte"),
            _c(_brl_num(vt_concedido) if tem_vt else "—", right=True),
            _c(_brl_num(co_vt), right=True),
            _c(_brl_num(vt_liq) if tem_vt else "—", right=True, bold=True),
        ],
    ]
    t_ben = Table(head + linhas, colWidths=[38 * mm, 55 * mm, 29 * mm, 27 * mm, 29 * mm])
    t_ben.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), B.AZUL_ESCURO),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E1F2")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#F8FAFC")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(_titulo("BENEFÍCIOS CONCEDIDOS", st, "mais"))
    story.append(t_ben)
    story.append(Spacer(1, 3 * mm))

    # ── Total recebido ──
    total_liq = vr_liq + (vt_liq if tem_vt else 0)
    tot = Table(
        [
            [
                _cell("Total líquido recebido em benefícios", st, bold=True, cor=colors.white),
                _cell(B.brl(total_liq) + ("" if tem_vt else "  + VT"), st, right=True, bold=True, cor=colors.white),
            ]
        ],
        colWidths=[128 * mm, 50 * mm],
    )
    tot.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), B.LARANJA),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(tot)

    # citação legal da co-participação (letras menores) — transparência com o funcionário
    story.append(Spacer(1, 1.5 * mm))
    story.append(
        Paragraph(
            '<font size="7" color="#6B7280">A co-participação (coluna "Co-part.") é a parcela do benefício '
            "legalmente descontada do colaborador, <b>conforme a Lei nº 7.418/1985</b>; o restante do custo é "
            "assumido pela empresa.</font>",
            st["small"],
        )
    )

    if not tem_vt:
        story.append(Spacer(1, 1 * mm))
        story.append(
            Paragraph(
                '<font size="7" color="#6B7280">Valor concedido de vale-transporte a preencher conforme a tarifa/'
                "crédito do cartão da competência (o DP informa).</font>",
                st["small"],
            )
        )

    # ── Declaração ──
    story.append(Spacer(1, 4 * mm))
    nome = holerite.get("employee_nome", "—")
    story.append(
        Paragraph(
            f"<b>DECLARAÇÃO.</b> Declaro que recebi da <b>{B.EMPRESA['nome']}</b> (CNPJ {B.EMPRESA['cnpj']}) "
            f"os valores de vale-transporte e vale-refeição referentes à competência <b>{comp}</b>, na forma da "
            f"Lei nº 7.418/1985 e da Convenção Coletiva de Trabalho da categoria, com a co-participação legal "
            f"descontada em folha, nada mais tendo a reclamar quanto a estes benefícios no período.",
            st["corpo"],
        )
    )

    # ── Assinaturas (digital, mesmo padrão do holerite) ──
    # Empresa assina na DATA DO PAGAMENTO (sistema coleta data + assinatura do CEO);
    # o funcionário assina depois, no recebimento (Portal do Funcionário).
    dpag = holerite.get("data_pagamento") or funcionario.get("data_pagamento")
    if dpag and hasattr(dpag, "strftime"):
        dpag = dpag.strftime("%d/%m/%Y")
    data_pag = str(dpag) if dpag else "____/____/______"
    story += B.campos_assinatura(
        st,
        funcionario_nome=nome,
        funcionario_cpf=_fmt_cpf(funcionario.get("cpf")),
        data_str=data_pag,
        data_prefixo="Pago em ",
        digital_funcionario=True,
        data_empresa=(str(dpag) if dpag else None),
        espaco_antes=8,
        incluir_empresa=False,  # Recibo VT/VR: comprovante de recebimento — só o FUNCIONÁRIO assina
    )

    # Autenticidade branded: assinatura já coletada (motor universal) → bloco padrão-ouro.
    story += B.bloco_autenticidade_assinaturas(st, signatarios=signatarios)

    doc.build(
        story,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo="RECIBO VT / VR"),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo="RECIBO VT / VR"),
    )
    return buf.getvalue()
