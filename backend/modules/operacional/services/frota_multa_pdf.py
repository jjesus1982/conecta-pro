"""Multa de trânsito — PDF padrão-ouro Conecta Mais (DGX V3, 24/09/2026).

A F10 registrou a multa, o condutor sugerido pela posse datada, a indicação e o desconto em folha.
O que não existia era o PAPEL: o DGX tem «PDF detalhes» na tela de multas, e aqui a multa é
exatamente o documento que se entrega ao condutor indicado (é dele a pontuação) e que instrui o
recurso. Este gerador NÃO calcula nada — veste a linha de `frota_multas` com a marca.

Mesma identidade dos outros geradores (`pdf_branding`): cabeçalho com a logo cheia, tabelas com
grade azul-clara, campos de assinatura (ciência do condutor + empresa) e rodapé oficial.
"""

from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules.crm.services import pdf_branding as B  # noqa: N812 — mesma grafia dos outros geradores
from modules.people_management.folha.services.holerite_pdf import _cell, _fmt_cpf, _titulo

_ST_MULTA = {
    "recebida": "Recebida",
    "indicada": "Condutor indicado",
    "paga": "Paga",
    "recorrida": "Em recurso",
    "desconto_em_folha": "Desconto em folha",
}
_ST_RECURSO = {"pendente": "Pendente", "deferido": "Deferido", "parcial": "Parcial", "indeferido": "Indeferido"}


def _esc(s) -> str:
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _br(v) -> str:
    return B.br_date(v) if v else "—"


def _grade(linhas: list, larguras: list) -> Table:
    tb = Table(linhas, colWidths=larguras)
    tb.setStyle(
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
    return tb


def montar_multa(m: dict) -> bytes:
    """`m`: linha de `frota_multas` como dict, com placa/modelo/marca do veículo e os nomes do
    condutor indicado (`condutor_nome`, `condutor_cpf`) e do sugerido (`sugerido_nome`)."""
    st = B.styles()
    emp = B.empresa_branding()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=40 * mm, bottomMargin=16 * mm, leftMargin=16 * mm, rightMargin=16 * mm
    )
    W = A4[0] - 32 * mm
    c1, c2 = 32 * mm, W / 2 - 32 * mm
    story: list = []

    hora = m.get("hora")
    quando = _br(m.get("data_infracao")) + (f" às {hora.strftime('%H:%M')}" if hora else "")
    story += [
        _titulo("AUTO DE INFRAÇÃO", st, "calc"),
        _grade(
            [
                [
                    _cell("Multa nº", st, bold=True),
                    _cell(f"#{m.get('id')}", st),
                    _cell("Órgão", st, bold=True),
                    _cell(_esc(m.get("orgao")) or "—", st),
                ],
                [
                    _cell("Auto", st, bold=True),
                    _cell(_esc(m.get("auto_infracao")) or "—", st),
                    _cell("Código", st, bold=True),
                    _cell(_esc(m.get("codigo_infracao")) or "—", st),
                ],
                [
                    _cell("Data / hora", st, bold=True),
                    _cell(quando, st),
                    _cell("Pontos", st, bold=True),
                    _cell(str(m.get("pontos")) if m.get("pontos") is not None else "—", st),
                ],
                [
                    _cell("Local", st, bold=True),
                    _cell(_esc(m.get("local")) or "—", st),
                    _cell("Situação", st, bold=True),
                    _cell(_ST_MULTA.get(m.get("status"), m.get("status") or "—"), st),
                ],
            ],
            [c1, c2, c1, c2],
        ),
        Spacer(1, 3 * mm),
        _titulo("VEÍCULO E CONDUTOR", st, "user"),
        _grade(
            [
                [
                    _cell("Placa", st, bold=True),
                    _cell(_esc(m.get("placa")), st),
                    _cell("Veículo", st, bold=True),
                    _cell(f"{_esc(m.get('marca')) or ''} {_esc(m.get('modelo')) or ''}".strip() or "—", st),
                ],
                [
                    _cell("Condutor indicado", st, bold=True),
                    _cell(_esc(m.get("condutor_nome")) or "— não indicado —", st),
                    _cell("CPF", st, bold=True),
                    _cell(_fmt_cpf(m.get("condutor_cpf")) if m.get("condutor_cpf") else "—", st),
                ],
                [
                    _cell("Sugerido pelo sistema", st, bold=True),
                    _cell(_esc(m.get("sugerido_nome")) or "— sem posse datada —", st),
                    _cell("Indicado em", st, bold=True),
                    _cell(_br(m.get("indicado_em")), st),
                ],
            ],
            [c1, c2, c1, c2],
        ),
        Spacer(1, 3 * mm),
        _titulo("VALORES", st, "money"),
        _grade(
            [
                [
                    _cell("Valor", st, bold=True),
                    _cell(B.brl(m.get("valor")), st),
                    _cell("Com desconto", st, bold=True),
                    _cell(B.brl(m.get("valor_com_desconto")) if m.get("valor_com_desconto") else "—", st),
                ],
                [
                    _cell("Vencimento", st, bold=True),
                    _cell(_br(m.get("vencimento")), st),
                    _cell("Conta a pagar", st, bold=True),
                    _cell(str(m.get("payable_id"))[:8] + "…" if m.get("payable_id") else "não gerada", st),
                ],
                [
                    _cell("Desconto em folha", st, bold=True),
                    _cell("Sim" if m.get("desconto_folha") else "Não", st),
                    _cell("Paga em", st, bold=True),
                    _cell(_br(m.get("paga_em")), st),
                ],
            ],
            [c1, c2, c1, c2],
        ),
    ]
    if m.get("recurso_lancado_em") or m.get("cabe_recurso"):
        story += [
            Spacer(1, 3 * mm),
            _titulo("RECURSO", st, "calc"),
            _grade(
                [
                    [
                        _cell("Cabe recurso", st, bold=True),
                        _cell("Sim" if m.get("cabe_recurso") else "Não", st),
                        _cell("Lançado em", st, bold=True),
                        _cell(_br(m.get("recurso_lancado_em")), st),
                    ],
                    [
                        _cell("Resultado", st, bold=True),
                        _cell(_ST_RECURSO.get(m.get("recurso_resultado"), m.get("recurso_resultado") or "—"), st),
                        _cell("Observação", st, bold=True),
                        _cell(_esc(m.get("recurso_observacao")) or "—", st),
                    ],
                ],
                [c1, c2, c1, c2],
            ),
        ]
    if m.get("descricao"):
        story += [
            Spacer(1, 3 * mm),
            Paragraph("DESCRIÇÃO DA INFRAÇÃO", st["h_sec"]),
            Paragraph(_esc(m.get("descricao")), st["corpo"]),
        ]
    story.append(
        Paragraph(
            "A indicação do condutor responde ao art. 257 §7º do CTB. Este documento é registro interno da "
            "Conecta Mais e não substitui a notificação do órgão autuador.",
            st["small"],
        )
    )
    story += B.campos_assinatura(
        st,
        funcionario_nome=m.get("condutor_nome") or "—",
        funcionario_cpf=_fmt_cpf(m.get("condutor_cpf")) if m.get("condutor_cpf") else "—",
        funcionario_label="Ciência do Condutor",
        responsavel_cargo="Frota / Administrativo",
        espaco_antes=8,
        empresa=emp,
    )
    doc.build(
        story,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo="MULTA DE TRÂNSITO", empresa=emp),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo="MULTA DE TRÂNSITO", empresa=emp),
    )
    return buf.getvalue()


def demo() -> None:
    from datetime import date, time

    pdf = montar_multa(
        {
            "id": 7,
            "placa": "ABC1D23",
            "modelo": "Onix",
            "marca": "Chevrolet",
            "data_infracao": date(2026, 9, 10),
            "hora": time(14, 30),
            "local": "Av. Djalma Batista, 1000",
            "orgao": "DETRAN-AM",
            "auto_infracao": "AM12345678",
            "codigo_infracao": "7455",
            "pontos": 5,
            "valor": 195.23,
            "valor_com_desconto": 156.18,
            "vencimento": date(2026, 10, 5),
            "status": "recorrida",
            "condutor_nome": "FULANO DE TAL",
            "condutor_cpf": "52998224725",
            "sugerido_nome": "FULANO DE TAL",
            "cabe_recurso": True,
            "recurso_lancado_em": date(2026, 9, 15),
            "recurso_resultado": "pendente",
            "descricao": "Transitar em velocidade superior à máxima permitida em até 20%.",
        }
    )
    assert pdf.startswith(b"%PDF") and len(pdf) > 3000
    # sem recurso: o bloco some e o PDF continua válido
    curto = montar_multa({"id": 8, "placa": "XYZ9K88", "valor": 88.38, "status": "recebida"})
    assert curto.startswith(b"%PDF") and len(curto) < len(pdf)
    print("ok frota_multa_pdf", len(pdf), "bytes")


if __name__ == "__main__":
    demo()
