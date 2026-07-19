"""Holerite PDF completo e branded (padrão-ouro Conecta Mais).

Discrimina TUDO: proventos, descontos (INSS/IRRF/VT/VR/odonto/seguro/taxa/consignado/pensão),
totais, bases (INSS/FGTS/IRRF) + depósito FGTS 8%, e campos de assinatura (funcionário + empresa).
Texto sempre dentro das caixas (Paragraph nas células). Cabe harmonioso em UMA folha A4.
"""

from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules.crm.services import pdf_branding as B

_MESES = [
    "",
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]


def _fmt_cpf(v) -> str:
    d = "".join(ch for ch in str(v or "") if ch.isdigit())
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:11]}" if len(d) == 11 else (str(v) or "—")


# CBO por cargo — extraído da folha oficial do Domínio/Portte (fonte de verdade)
_CBO_POR_CARGO = {
    "AGENTE DE PORTARIA": "5174-10",
    "LIDER DE PORTARIA": "5103-10",
    "AGENTE DE SERVICOS GERAIS": "5143-20",
    "ARTIFICE": "5143-10",
    "JARDINEIRO": "6220-10",
}


def _norm(s: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return " ".join(s.upper().split())


def _cbo(cargo: str, funcionario: dict | None = None) -> str:
    """Retorna o CBO formatado (XXXX-XX). Prioriza o valor do cadastro do funcionário,
    senão mapeia pelo cargo (folha oficial). Vazio → '—' (aguardando dado)."""
    if funcionario:
        raw = funcionario.get("cbo") or funcionario.get("cbo_codigo")
        if raw:
            d = "".join(ch for ch in str(raw) if ch.isdigit())
            if len(d) == 6:
                return f"{d[:4]}-{d[4:]}"
            return str(raw)
    return _CBO_POR_CARGO.get(_norm(cargo), "—")


def _cell(txt, st, *, bold=False, right=False, cor=None, size=8.5):
    base = st.get("cell")
    ps = ParagraphStyle(
        "c",
        parent=base,
        fontName=B.FONTE_B if bold else B.FONTE,
        alignment=2 if right else 0,
        fontSize=size,
        leading=size + 2,
        textColor=cor or B.TEXTO,
    )
    return Paragraph(str(txt), ps)


def _icone(kind: str):
    """Ícone vetorial branco, discreto (12x12pt) para o cabeçalho de seção."""
    from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, Rect

    w = colors.white
    d = Drawing(12, 12)
    if kind == "user":  # identificação
        d.add(Circle(6, 8.6, 2.1, fillColor=w, strokeColor=None))
        d.add(Polygon(points=[1.8, 1.5, 10.2, 1.5, 8.8, 5.2, 3.2, 5.2], fillColor=w, strokeColor=None))
    elif kind == "mais":  # proventos (+)
        d.add(Rect(5, 2, 2, 8, fillColor=w, strokeColor=None))
        d.add(Rect(2, 5, 8, 2, fillColor=w, strokeColor=None))
    elif kind == "menos":  # descontos (−)
        d.add(Rect(2, 5, 8, 2, fillColor=w, strokeColor=None))
    elif kind == "calc":  # bases/FGTS
        d.add(Rect(2, 1.5, 8, 9, fillColor=None, strokeColor=w, strokeWidth=1))
        d.add(Line(2, 6, 10, 6, strokeColor=w, strokeWidth=0.9))
        d.add(Line(6, 1.5, 6, 6, strokeColor=w, strokeWidth=0.9))
    return d


def _titulo(txt, st, icone="user"):
    """Cabeçalho de seção compacto (barra azul) com ícone branco discreto à esquerda."""
    p = Paragraph(
        f'<font color="#FFFFFF"><b>{txt}</b></font>',
        ParagraphStyle(
            "sec", parent=st.get("cell"), fontName=B.FONTE_B, fontSize=9, leading=12, textColor=colors.white
        ),
    )
    t = Table([[_icone(icone), p]], colWidths=[8 * mm, 170 * mm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), B.AZUL_ESCURO),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (0, 0), 7),
                ("LEFTPADDING", (1, 0), (1, 0), 2),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return t


def _slug_empregador(funcionario: dict) -> str | None:
    """Empregador VIGENTE do funcionário (employees.empresa_id → empresas.slug).

    Multi-CNPJ E3: o holerite imprime a empresa do vínculo; a competência aplica
    a regra anti-reescrita (holerites < fronteira ficam CNPJ1 para sempre).
    Sem match => None (empresa_branding cai no CNPJ1) — com aviso no log.
    """
    import logging
    import os
    import re as _re

    cpf = _re.sub(r"\D", "", str(funcionario.get("cpf") or ""))
    if not cpf:
        return None
    try:
        import psycopg2

        url = _re.sub(r"\+asyncpg|\+psycopg2?", "", os.getenv("DATABASE_URL", ""))
        conn = psycopg2.connect(url)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT e.slug FROM employees emp JOIN empresas e ON e.id = emp.empresa_id "
                    "WHERE REGEXP_REPLACE(COALESCE(emp.cpf,''),'[^0-9]','','g') = %s LIMIT 1",
                    (cpf,),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if row:
            return row[0]
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning("holerite: falha ao resolver empregador (%s)", exc)
    return None


def montar_holerite_pdf(holerite: dict, funcionario: dict | None = None) -> bytes:
    """Gera o PDF completo do holerite (uma folha A4) a partir do dict de calcular_folha_colaborador."""
    funcionario = funcionario or {}
    _mes = int(holerite.get("mes") or 0)
    _ano = int(holerite.get("ano") or 0)
    _competencia = f"{_ano:04d}-{_mes:02d}" if _mes and _ano else None
    empresa_doc = B.empresa_branding(_slug_empregador(funcionario), _competencia)
    st = B.styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=40 * mm, bottomMargin=16 * mm, leftMargin=16 * mm, rightMargin=16 * mm
    )
    W = A4[0] - 32 * mm
    mes = int(holerite.get("mes") or 0)
    comp = f"{_MESES[mes] if 0 < mes < 13 else mes}/{holerite.get('ano', '')}"
    story: list = []

    # ── Identificação (2 colunas) ──
    cargo = holerite.get("cargo", "—")
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
            _cell("Escala", st, bold=True),
            _cell(holerite.get("escala", "—"), st),
            _cell("Admissão", st, bold=True),
            _cell(funcionario.get("data_admissao", "—"), st),
        ],
        [
            _cell("CPF", st, bold=True),
            _cell(_fmt_cpf(funcionario.get("cpf")), st),
            _cell("Matrícula / PIS", st, bold=True),
            _cell(funcionario.get("pis", funcionario.get("matricula", "—")), st),
        ],
        [
            _cell("Departamento", st, bold=True),
            _cell(funcionario.get("departamento", "Operacional"), st),
            _cell("Posto", st, bold=True),
            _cell(funcionario.get("posto", "—"), st),
        ],
    ]
    t_id = Table(ident, colWidths=[30 * mm, W / 2 - 30 * mm, 28 * mm, W / 2 - 28 * mm])
    t_id.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E1F2")),
                ("BACKGROUND", (0, 0), (0, -1), B.FUNDO_CLARO),
                ("BACKGROUND", (2, 0), (2, -1), B.FUNDO_CLARO),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(_titulo("IDENTIFICAÇÃO DO COLABORADOR", st, "user"))
    story.append(t_id)
    story.append(Spacer(1, 2.5 * mm))

    # ── Proventos e Descontos (tabelas de LARGURA CHEIA, empilhadas — sem overflow) ──
    def _bloco(titulo, itens, cor_header, icone="mais"):
        tit_cell = Table([[_icone(icone), _cell(titulo, st, bold=True, cor=colors.white)]], colWidths=[7 * mm, 90 * mm])
        tit_cell.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("LEFTPADDING", (1, 0), (1, 0), 1),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        head = [
            [
                tit_cell,
                _cell("Referência", st, bold=True, cor=colors.white),
                _cell("Valor (R$)", st, bold=True, right=True, cor=colors.white),
            ]
        ]
        linhas = []
        for it in itens:
            linhas.append(
                [
                    _cell(it["descricao"], st),
                    _cell(it.get("referencia", "") or "—", st),
                    _cell(B.brl(it["valor"]).replace("R$ ", ""), st, right=True),
                ]
            )
        tb = Table(head + linhas, colWidths=[100 * mm, 45 * mm, 33 * mm])
        estilo = [
            ("BACKGROUND", (0, 0), (-1, 0), cor_header),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E1F2")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ]
        for i in range(1, len(linhas) + 1):
            if i % 2 == 0:
                estilo.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F8FAFC")))
        tb.setStyle(TableStyle(estilo))
        return tb

    prov = holerite.get("proventos", [])
    desc = holerite.get("descontos", [])
    story.append(_bloco("PROVENTOS", prov, B.AZUL_ESCURO, "mais"))
    story.append(Spacer(1, 2.5 * mm))
    story.append(_bloco("DESCONTOS", desc, colors.HexColor("#B45309"), "menos"))
    story.append(Spacer(1, 2.5 * mm))

    # ── Totais ──
    tp = holerite.get("total_proventos", 0)
    td = holerite.get("total_descontos", 0)
    liq = holerite.get("liquido", 0)
    tot = Table(
        [
            [
                _cell("Total de Proventos", st, bold=True),
                _cell(B.brl(tp), st, right=True, bold=True),
                _cell("Total de Descontos", st, bold=True),
                _cell(B.brl(td), st, right=True, bold=True),
                _cell("LÍQUIDO", st, bold=True, cor=colors.white),
                _cell(B.brl(liq), st, right=True, bold=True, cor=colors.white),
            ]
        ],
        colWidths=[34 * mm, 24 * mm, 34 * mm, 24 * mm, 32 * mm, 30 * mm],
    )
    tot.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (3, -1), 0.4, colors.HexColor("#D9E1F2")),
                ("BACKGROUND", (0, 0), (0, 0), B.FUNDO_CLARO),
                ("BACKGROUND", (2, 0), (2, 0), B.FUNDO_CLARO),
                ("BACKGROUND", (4, 0), (5, 0), B.LARANJA),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(tot)
    story.append(Spacer(1, 2.5 * mm))

    # ── Bases + FGTS ──
    b_inss = holerite.get("base_inss", 0)
    b_fgts = holerite.get("base_fgts", holerite.get("base_inss", 0))
    v_fgts = holerite.get("fgts_empresa", 0)
    b_irrf = holerite.get("base_irrf", 0)
    bases = [
        [
            _cell("Base INSS", st, bold=True, size=8),
            _cell(B.brl(b_inss), st, right=True, size=8),
            _cell("Base FGTS", st, bold=True, size=8),
            _cell(B.brl(b_fgts), st, right=True, size=8),
            _cell("FGTS 8% (depósito)", st, bold=True, size=8),
            _cell(B.brl(v_fgts), st, right=True, size=8),
            _cell("Base IRRF", st, bold=True, size=8),
            _cell(B.brl(b_irrf), st, right=True, size=8),
        ]
    ]
    t_b = Table(bases, colWidths=[22 * mm, 21 * mm, 22 * mm, 21 * mm, 30 * mm, 21 * mm, 20 * mm, 21 * mm])
    t_b.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E1F2")),
                ("BACKGROUND", (0, 0), (0, 0), B.FUNDO_CLARO),
                ("BACKGROUND", (2, 0), (2, 0), B.FUNDO_CLARO),
                ("BACKGROUND", (4, 0), (4, 0), B.FUNDO_CLARO),
                ("BACKGROUND", (6, 0), (6, 0), B.FUNDO_CLARO),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(_titulo("BASES DE CÁLCULO E FGTS", st, "calc"))
    story.append(t_b)

    # nota da fonte das horas
    fonte = holerite.get("fonte_horas_noturnas", "")
    ht = holerite.get("horas_trabalhadas_ponto", 0)
    if fonte:
        story.append(Spacer(1, 1.5 * mm))
        story.append(
            Paragraph(
                f'<font size="7" color="#6B7280">Horas trabalhadas (ponto): {ht}h · fonte dos adicionais-hora: {fonte}. '
                f"Cálculo híbrido — o DP confere e ajusta conforme a folha oficial.</font>",
                st["small"],
            )
        )

    # ── Data de PAGAMENTO + Assinaturas ──
    # A data exibida é a do PAGAMENTO (não a de assinatura — essa vem depois, no envio).
    # Sem data de pagamento confirmada → campo a preencher (aguardando dado).
    dpag = holerite.get("data_pagamento") or funcionario.get("data_pagamento")
    if dpag and hasattr(dpag, "strftime"):
        dpag = dpag.strftime("%d/%m/%Y")
    data_pag = str(dpag) if dpag else "____/____/______"
    story += B.campos_assinatura(
        st,
        funcionario_nome=holerite.get("employee_nome"),
        funcionario_cpf=_fmt_cpf(funcionario.get("cpf")),
        data_str=data_pag,
        data_prefixo="Pago em ",
        digital_funcionario=True,
        data_empresa=(str(dpag) if dpag else None),
        espaco_antes=10,
        incluir_empresa=False,  # HOLERITE: basta a assinatura do FUNCIONÁRIO (recibo de pagamento)
    )

    doc.build(
        story,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo="HOLERITE", empresa=empresa_doc),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo="HOLERITE", empresa=empresa_doc),
    )
    return buf.getvalue()
