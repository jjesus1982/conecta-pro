"""PPP — Perfil Profissiográfico Previdenciário em PDF padrão-ouro Conecta Mais.

Renderiza o dict montado pelo endpoint GET /sst/ppp/{employee_id} (dados
administrativos, lotação/atribuições, exposição a fatores de risco, exames
médicos e responsáveis) em 1-2 páginas A4 com a marca central (pdf_branding).

Documento OFICIAL da EMPRESA para o INSS (Lei 8.213/91 Art. 58 § 4º +
IN INSS 128/2022) — assinatura da EMPRESA (incluir_empresa=True), sem campo
de assinatura do funcionário. Campos ausentes ficam "—" (aguardando dado),
nunca inventados.
"""

from __future__ import annotations

import io
from datetime import date

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

_GRID = colors.HexColor("#D9E1F2")


def _br(v) -> str:
    """dd/mm/aaaa a partir de date OU string ISO; vazio → '—'."""
    if not v:
        return "—"
    s = str(v)[:10]
    try:
        return date.fromisoformat(s).strftime("%d/%m/%Y")
    except ValueError:
        return B.br_date(v)


def _grade(t: Table, header_row: bool = False) -> Table:
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]
    if header_row:
        style.append(("BACKGROUND", (0, 0), (-1, 0), B.AZUL_ESCURO))
    t.setStyle(TableStyle(style))
    return t


def montar_ppp_pdf(ppp: dict, funcionario_extra: dict | None = None) -> bytes:
    """Gera o PDF do PPP a partir do dict do endpoint /sst/ppp/{employee_id}.

    ppp: {empresa, funcionario, atividades, fatores_risco, exames_medicos,
          responsavel_tecnico, observacoes, base_legal, esocial...}
    funcionario_extra: dict extra do employees (cbo etc.) — opcional.
    """
    funcionario_extra = funcionario_extra or {}
    st = B.styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=40 * mm, bottomMargin=16 * mm, leftMargin=16 * mm, rightMargin=16 * mm
    )
    W = A4[0] - 32 * mm
    story: list = []

    emp = ppp.get("empresa") or {}
    func = ppp.get("funcionario") or {}
    # Multi-CNPJ: marca resolvida pelo empregador vigente do funcionário (competência atual —
    # PPP é documento corrente). empresa_branding_por_cpf faz fail-closed pós-fronteira.
    _marca = B.empresa_branding_por_cpf(func.get("cpf"), date.today().strftime("%Y-%m"))
    nome = func.get("nome") or "—"
    cargo = func.get("cargo") or "—"

    # ── I. Dados administrativos ──
    ident = [
        [
            _cell("Empregador", st, bold=True),
            _cell(_marca["razao"], st),
            _cell("CNPJ", st, bold=True),
            _cell(_marca["cnpj"], st),
        ],
        [
            _cell("CNAE", st, bold=True),
            _cell(emp.get("cnae") or "—", st),
            _cell("Emitido em", st, bold=True),
            _cell(date.today().strftime("%d/%m/%Y"), st),
        ],
        [
            _cell("Trabalhador", st, bold=True),
            _cell(nome, st),
            _cell("CPF", st, bold=True),
            _cell(_fmt_cpf(func.get("cpf")), st),
        ],
        [
            _cell("Cargo / Função", st, bold=True),
            _cell(cargo, st),
            _cell("CBO", st, bold=True),
            _cell(_cbo(cargo, funcionario_extra), st),
        ],
        [
            _cell("Admissão", st, bold=True),
            _cell(_br(func.get("data_admissao")), st),
            _cell("Demissão", st, bold=True),
            _cell(_br(func.get("data_demissao")), st),
        ],
    ]
    t_id = Table(ident, colWidths=[30 * mm, W / 2 - 30 * mm, 24 * mm, W / 2 - 24 * mm])
    story.append(_titulo("I. DADOS ADMINISTRATIVOS", st, "user"))
    story.append(_grade(t_id))
    story.append(Spacer(1, 3 * mm))

    # ── II. Lotação e atribuições ──
    linhas = [
        [
            _cell("Período", st, bold=True, cor=colors.white),
            _cell("Cargo / Função", st, bold=True, cor=colors.white),
            _cell("Setor", st, bold=True, cor=colors.white),
            _cell("Descrição das atividades", st, bold=True, cor=colors.white),
        ]
    ]
    for atv in ppp.get("atividades") or []:
        linhas.append(
            [
                _cell(str(atv.get("periodo") or "—"), st),
                _cell(str(atv.get("cargo") or "—"), st),
                _cell(str(atv.get("setor") or "—"), st),
                _cell(str(atv.get("descricao") or "—"), st),
            ]
        )
    if len(linhas) == 1:
        linhas.append([_cell("— sem registros (aguardando dado) —", st), "", "", ""])
    t_atv = Table(linhas, colWidths=[38 * mm, 34 * mm, 24 * mm, W - 96 * mm], repeatRows=1)
    story.append(_titulo("II. LOTAÇÃO E ATRIBUIÇÕES", st, "calc"))
    story.append(_grade(t_atv, header_row=True))
    story.append(Spacer(1, 3 * mm))

    # ── III. Exposição a fatores de risco ──
    linhas = [
        [
            _cell("Agente", st, bold=True, cor=colors.white),
            _cell("Tipo", st, bold=True, cor=colors.white),
            _cell("Intensidade", st, bold=True, cor=colors.white),
            _cell("Técnica utilizada", st, bold=True, cor=colors.white),
            _cell("EPI / EPC", st, bold=True, cor=colors.white),
        ]
    ]
    for fr in ppp.get("fatores_risco") or []:
        linhas.append(
            [
                _cell(str(fr.get("agente") or "—"), st),
                _cell(str(fr.get("tipo") or "—"), st),
                _cell(str(fr.get("intensidade") or "—"), st),
                _cell(str(fr.get("tecnica_utilizada") or "—"), st),
                _cell(str(fr.get("epi_epc") or "—"), st),
            ]
        )
    if len(linhas) == 1:
        linhas.append([_cell("— sem fatores de risco registrados (aguardando dado) —", st), "", "", "", ""])
    t_fr = Table(linhas, colWidths=[W - 122 * mm, 24 * mm, 24 * mm, 40 * mm, 34 * mm], repeatRows=1)
    story.append(_titulo("III. EXPOSIÇÃO A FATORES DE RISCO", st, "menos"))
    story.append(_grade(t_fr, header_row=True))
    story.append(Spacer(1, 3 * mm))

    # ── IV. Exames médicos (ASO) ──
    linhas = [
        [
            _cell("Data", st, bold=True, cor=colors.white),
            _cell("Tipo de exame", st, bold=True, cor=colors.white),
            _cell("Status", st, bold=True, cor=colors.white),
        ]
    ]
    for ex in ppp.get("exames_medicos") or []:
        linhas.append(
            [
                _cell(_br(ex.get("data_agendamento")), st),
                _cell(str(ex.get("tipo") or "—").capitalize(), st),
                _cell(str(ex.get("status") or "—").replace("_", " ").capitalize(), st),
            ]
        )
    if len(linhas) == 1:
        linhas.append([_cell("— sem exames registrados (aguardando dado) —", st), "", ""])
    t_ex = Table(linhas, colWidths=[30 * mm, W - 70 * mm, 40 * mm], repeatRows=1)
    story.append(_titulo("IV. EXAMES MÉDICOS OCUPACIONAIS (ASO)", st, "mais"))
    story.append(_grade(t_ex, header_row=True))
    story.append(Spacer(1, 3 * mm))

    # ── V. Responsáveis pelas informações ──
    resp = ppp.get("responsavel_tecnico") or {}
    t_resp = Table(
        [
            [
                _cell("Responsável técnico", st, bold=True),
                _cell(str(resp.get("nome") or "—"), st),
                _cell("Registro", st, bold=True),
                _cell(str(resp.get("registro") or "—"), st),
            ],
            [
                _cell("Especialidade", st, bold=True),
                _cell(str(resp.get("especialidade") or "—"), st),
                _cell("Representante legal", st, bold=True),
                _cell(_marca["ceo"], st),
            ],
        ],
        colWidths=[36 * mm, W / 2 - 36 * mm, 34 * mm, W / 2 - 34 * mm],
    )
    story.append(_titulo("V. RESPONSÁVEIS PELAS INFORMAÇÕES", st, "user"))
    story.append(_grade(t_resp))

    # ── Base legal + observações ──
    story.append(Spacer(1, 3 * mm))
    base_legal = ppp.get("base_legal") or "Lei 8.213/91 Art. 58 § 4º + IN INSS 128/2022"
    obs = ppp.get("observacoes")
    texto = f"<b>Base legal:</b> {base_legal}."
    if obs:
        texto += f" <b>Observações:</b> {obs}"
    story.append(Paragraph(texto, st["small"]))

    # ── Assinatura — SÓ da empresa (documento oficial da EMPRESA para o INSS) ──
    story += B.campos_assinatura(
        st,
        data_str=B.br_date(date.today()),
        espaco_antes=8,
        incluir_funcionario=False,
        incluir_empresa=True,
        empresa=_marca,
    )

    titulo = "PPP — PERFIL PROFISSIOGRÁFICO PREVIDENCIÁRIO"
    doc.build(
        story,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo=titulo, empresa=_marca),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo=titulo, empresa=_marca),
    )
    return buf.getvalue()
