"""Relatório de Compliance NR-1 em PDF padrão-ouro Conecta Mais.

Snapshot do painel /sst/nr1/compliance (resumo geral + tabela por funcionário:
ASO / EPI / Riscos / Treinamentos / score / situação) formatado com a marca
central (pdf_branding), com data/hora de emissão — para entregar a auditor
fiscal. Todo valor vem do dict do get_nr1_compliance (fatos no banco), nunca
fabricado.
"""

from __future__ import annotations

import io
from datetime import datetime
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules.crm.services import pdf_branding as B

# reusa os helpers do padrão-ouro do holerite (mesma identidade visual)
from modules.people_management.folha.services.holerite_pdf import _cell, _titulo

_GRID = colors.HexColor("#D9E1F2")
_VERDE = colors.HexColor("#166534")
_VERMELHO = colors.HexColor("#B91C1C")
_AMARELO = colors.HexColor("#A16207")

_SITUACAO_ASO = {
    "em_dia": "Em dia",
    "vencido": "Vencido",
    "sem_aso": "Sem ASO",
}
_SITUACAO_EPI = {
    "fichas_assinadas": "Fichas assinadas",
    "ficha_pendente": "Ficha pendente",
    "sem_ficha": "Sem ficha",
    "sem_entrega_registrada": "Sem entrega",
}


def _check_txt(check: dict, mapa: dict[str, str] | None = None) -> tuple[str, colors.Color]:
    """Texto + cor do status de um check (verde ok / vermelho não / cinza sem fonte)."""
    situacao = str(check.get("situacao") or "—")
    label = (mapa or {}).get(situacao, situacao.replace("_", " ").capitalize())
    ok = check.get("ok")
    if ok is None:
        return label, B.AZUL_MEDIO
    return label, (_VERDE if ok else _VERMELHO)


def _grade(t: Table, header_row: bool = False) -> Table:
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    if header_row:
        style.append(("BACKGROUND", (0, 0), (-1, 0), B.AZUL_ESCURO))
    t.setStyle(TableStyle(style))
    return t


def montar_nr1_compliance_pdf(compliance: dict) -> bytes:
    """Gera o PDF do relatório de compliance NR-1 a partir do dict do get_nr1_compliance."""
    st = B.styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=40 * mm, bottomMargin=16 * mm, leftMargin=16 * mm, rightMargin=16 * mm
    )
    W = A4[0] - 32 * mm
    story: list = []

    resumo = compliance.get("resumo") or {}
    funcionarios = compliance.get("funcionarios") or []
    agora = datetime.now(ZoneInfo("America/Manaus"))

    # ── Emissão ──
    story.append(
        Paragraph(
            f"<b>Emitido em {agora.strftime('%d/%m/%Y às %H:%M')}</b> (America/Manaus) · "
            f"{B.EMPRESA['razao']} · CNPJ {B.EMPRESA['cnpj']} · "
            "Snapshot do painel de compliance NR-1 — score calculado exclusivamente "
            "sobre registros existentes no banco (nenhum valor estimado).",
            st["small"],
        )
    )
    story.append(Spacer(1, 3 * mm))

    # ── Resumo geral ──
    total = resumo.get("total_funcionarios_ativos", 0)
    resumo_linhas = [
        [
            _cell("Funcionários ativos", st, bold=True),
            _cell(str(total), st, right=True),
            _cell("Calçados (100% dos checks)", st, bold=True),
            _cell(str(resumo.get("calcados", 0)), st, right=True),
        ],
        [
            _cell("Descalçados", st, bold=True),
            _cell(str(resumo.get("descalcados", 0)), st, right=True),
            _cell("Funcionários com ASO vencido", st, bold=True),
            _cell(str(resumo.get("funcionarios_aso_vencido", 0)), st, right=True),
        ],
        [
            _cell("ASOs vencidos (registros)", st, bold=True),
            _cell(str(resumo.get("asos_vencidos_registros", 0)), st, right=True),
            _cell("Fichas de EPI pendentes de assinatura", st, bold=True),
            _cell(str(resumo.get("fichas_epi_pendentes_assinatura", 0)), st, right=True),
        ],
        [
            _cell("Entregas de EPI sem ficha", st, bold=True),
            _cell(str(resumo.get("entregas_epi_sem_ficha", 0)), st, right=True),
            _cell("Riscos mapeados vigentes", st, bold=True),
            _cell(str(resumo.get("riscos_mapeados_vigentes", 0)), st, right=True),
        ],
    ]
    t_resumo = Table(resumo_linhas, colWidths=[58 * mm, W / 2 - 58 * mm, 66 * mm, W / 2 - 66 * mm])
    story.append(_titulo("RESUMO GERAL", st, "calc"))
    story.append(_grade(t_resumo))
    story.append(Spacer(1, 3 * mm))

    # ── Compliance por funcionário ──
    linhas = [
        [
            _cell("Funcionário", st, bold=True, size=7.5, cor=colors.white),
            _cell("Cargo", st, bold=True, size=7.5, cor=colors.white),
            _cell("ASO", st, bold=True, size=7.5, cor=colors.white),
            _cell("EPI", st, bold=True, size=7.5, cor=colors.white),
            _cell("Riscos", st, bold=True, size=7.5, cor=colors.white),
            _cell("Trein.", st, bold=True, size=7.5, cor=colors.white),
            _cell("Score", st, bold=True, size=7.5, right=True, cor=colors.white),
            _cell("Situação", st, bold=True, size=7.5, cor=colors.white),
        ]
    ]
    for f in funcionarios:
        checks = f.get("checks") or {}
        aso_txt, aso_cor = _check_txt(checks.get("aso") or {}, _SITUACAO_ASO)
        epi_txt, epi_cor = _check_txt(checks.get("epi") or {}, _SITUACAO_EPI)
        riscos_txt, riscos_cor = _check_txt(checks.get("riscos") or {}, {"mapa_vigente": "Mapa vigente", "sem_mapa": "Sem mapa"})
        trein_txt, trein_cor = _check_txt(checks.get("treinamentos") or {}, {"sem_fonte": "Sem fonte"})
        score = int(f.get("score") or 0)
        calcado = bool(f.get("calcado"))
        score_cor = _VERDE if score >= 80 else (_AMARELO if score >= 50 else _VERMELHO)
        linhas.append(
            [
                _cell(str(f.get("nome") or "—"), st, size=7.5),
                _cell(str(f.get("cargo") or "—"), st, size=7.5),
                _cell(aso_txt, st, size=7.5, cor=aso_cor),
                _cell(epi_txt, st, size=7.5, cor=epi_cor),
                _cell(riscos_txt, st, size=7.5, cor=riscos_cor),
                _cell(trein_txt, st, size=7.5, cor=trein_cor),
                _cell(str(score), st, size=7.5, right=True, cor=score_cor),
                _cell("Calçado" if calcado else "Descalçado", st, size=7.5, bold=True,
                      cor=_VERDE if calcado else _VERMELHO),
            ]
        )
    if len(linhas) == 1:
        linhas.append([_cell("— nenhum funcionário ativo (aguardando dado) —", st), "", "", "", "", "", "", ""])
    t_func = Table(
        linhas,
        colWidths=[W - 139 * mm, 26 * mm, 18 * mm, 26 * mm, 20 * mm, 15 * mm, 13 * mm, 21 * mm],
        repeatRows=1,
    )
    story.append(_titulo("COMPLIANCE POR FUNCIONÁRIO (NR-1 / NR-6 / NR-7 / PGR)", st, "user"))
    story.append(_grade(t_func, header_row=True))

    # ── NR-1: RISCOS PSICOSSOCIAIS (canal de escuta sigiloso + inventário PGR) ──
    psico = compliance.get("psicossocial") or {}
    story.append(Spacer(1, 4 * mm))
    story.append(_titulo("RISCOS PSICOSSOCIAIS (NR-1)", st, "calc"))
    _canal = "ATIVO" if psico.get("canal_ativo") else "não configurado"
    story.append(
        Paragraph(
            f"<b>Canal de escuta:</b> {_canal} — {psico.get('canal_desc', '')} "
            f"Manifestações recebidas: <b>{psico.get('total_manifestacoes', 0)}</b>. "
            "A identidade do manifestante é preservada (sigilo/anonimato); os indicadores abaixo "
            "são anonimizados, atendendo à NR-1 (identificação de fatores de risco psicossocial).",
            st["small"],
        )
    )
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("<b>Inventário de riscos psicossociais (PGR)</b>", st["small"]))
    _inv = psico.get("inventario") or []
    _linhas_inv = [[_cell("Fator de risco psicossocial", st), _cell("Nível", st), _cell("Status", st), _cell("Medidas de controle", st)]]
    if _inv:
        for r in _inv:
            _linhas_inv.append([
                _cell(str(r.get("descricao", "")), st), _cell(str(r.get("nivel", "")), st),
                _cell(str(r.get("status", "")), st), _cell(str(r.get("medidas") or "— a definir pelo SST —"), st),
            ])
    else:
        _linhas_inv.append([_cell("— nenhum risco psicossocial inventariado ainda —", st), _cell("", st), _cell("", st), _cell("", st)])
    story.append(_grade(Table(_linhas_inv, colWidths=[W - 90 * mm, 20 * mm, 24 * mm, 46 * mm], repeatRows=1), header_row=True))
    _ind = psico.get("indicadores") or []
    if _ind:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("<b>Indicadores do canal — nº por assunto (anonimizado)</b>", st["small"]))
        _linhas_ind = [[_cell("Assunto da manifestação", st), _cell("Nº", st)]]
        for r in _ind:
            _linhas_ind.append([_cell(str(r.get("fator", "")), st), _cell(str(r.get("n", "")), st)])
        story.append(_grade(Table(_linhas_ind, colWidths=[W - 25 * mm, 25 * mm], repeatRows=1), header_row=True))

    # ── Nota de honestidade ──
    story.append(Spacer(1, 3 * mm))
    fonte_riscos = ((funcionarios[0].get("checks") or {}).get("riscos") or {}).get("fonte") if funcionarios else None
    story.append(
        Paragraph(
            "<b>Nota de veracidade:</b> cada check reflete o fato registrado no banco de dados — "
            "ASO (NR-7, gp_asos), fichas de EPI (NR-6, sst_fichas_epi), riscos (PGR, "
            f"{fonte_riscos or 'gp_risks'}) e treinamentos "
            f"({resumo.get('treinamentos_fonte') or 'sem fonte'}). "
            "Itens sem fonte não entram no score.",
            st["small"],
        )
    )

    # ── Assinatura — empresa (relatório oficial) ──
    story += B.campos_assinatura(
        st,
        data_str=B.br_date(agora.date()),
        espaco_antes=8,
        incluir_funcionario=False,
        incluir_empresa=True,
    )

    titulo = "RELATÓRIO DE COMPLIANCE NR-1"
    doc.build(
        story,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo=titulo),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo=titulo),
    )
    return buf.getvalue()
