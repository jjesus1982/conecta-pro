"""TRCT — Termo de Rescisão do Contrato de Trabalho (PDF padrão-ouro Conecta Mais).

Segue o modelo oficial do TRCT: identificação do empregador e do empregado, tipo de
rescisão, discriminação das VERBAS RESCISÓRIAS (saldo de salário, aviso prévio, 13º
proporcional por avos do ano civil, férias proporcionais do período aquisitivo + 1/3,
férias vencidas + 1/3), a parcela indenizatória da MULTA DE FGTS (40%), as DEDUÇÕES
(INSS e IRRF) e o LÍQUIDO a receber, além dos campos de assinatura EMPLOYEE + COMPANY.

As verbas NÃO são recalculadas aqui: consomem EXATAMENTE o dict produzido por
TerminationService.calculate_severance (clt_calculator), o mesmo que a tela mostra.
O saldo de FGTS é ESTIMADO (8% sobre a remuneração × meses) e vem rotulado como tal.

Uma folha A4, branded (pdf_branding), texto sempre dentro das caixas — mesma identidade
visual do holerite. Quando assinado, o bloco de autenticidade exibe os hashes REAIS.
"""

from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules.crm.services import pdf_branding as B

# Reusa os helpers do padrão-ouro do holerite (mesma identidade visual)
from modules.people_management.folha.services.holerite_pdf import (
    _cbo,
    _cell,
    _fmt_cpf,
    _titulo,
)


def _br_date(v) -> str:
    if not v:
        return "—"
    s = str(v)[:10]
    try:
        from datetime import date as _d

        return _d.fromisoformat(s).strftime("%d/%m/%Y")
    except ValueError:
        return B.br_date(v)


_TIPO_LABEL = {
    "involuntary": "Dispensa sem justa causa (por iniciativa do empregador)",
    "voluntary": "Pedido de demissão (por iniciativa do empregado)",
    "just_cause": "Dispensa por justa causa",
    "mutual_agreement": "Rescisão por acordo (CLT art. 484-A)",
    "contract_end": "Término de contrato por prazo determinado",
    "retirement": "Aposentadoria",
}


def montar_trct_pdf(calc: dict, funcionario: dict | None = None, meta: dict | None = None) -> bytes:
    """Gera o PDF do TRCT a partir do dict de TerminationService.calculate_severance.

    calc: dict com as verbas JÁ calculadas (chaves float, mesmas da tela):
        saldo_salario, aviso_previo_indenizado, aviso_previo_dias,
        ferias_vencidas, terco_ferias_vencidas, ferias_proporcionais,
        terco_ferias_proporcionais, decimo_terceiro_proporcional,
        avos_decimo_terceiro, avos_ferias_proporcionais,
        multa_fgts_40, saldo_fgts_estimado, fgts_estimado,
        total_proventos, inss, irrf, total_descontos, total_liquido,
        employee_name, termination_type, last_working_day.
    funcionario: dict do employees (cpf, cargo, data_admissao) — ausentes ficam '—'.
    meta: {termination_id, notice_type, assinaturas} — contexto do processo.
    """
    funcionario = funcionario or {}
    # Multi-CNPJ E3: empregador vigente do funcionário (rescisão usa a empresa do vínculo;
    # demitidos antigos não fizeram flip => resolvem CNPJ1 naturalmente)
    _empresa_doc = B.empresa_branding_por_cpf(funcionario.get('cpf'))
    meta = meta or {}
    st = B.styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=40 * mm, bottomMargin=16 * mm, leftMargin=16 * mm, rightMargin=16 * mm
    )
    W = A4[0] - 32 * mm
    story: list = []

    nome = calc.get("employee_name") or funcionario.get("nome") or "—"
    cargo = funcionario.get("cargo") or "—"
    tipo = str(calc.get("termination_type") or meta.get("termination_type") or "")
    # termination_type pode vir como Enum → normaliza para o value
    tipo = tipo.split(".")[-1].lower() if "." in tipo else tipo.lower()
    tipo_label = _TIPO_LABEL.get(tipo, tipo or "—")

    def _f(k) -> float:
        try:
            return float(calc.get(k) or 0)
        except (TypeError, ValueError):
            return 0.0

    # ── Identificação empregado + empregador ──
    ident = [
        [
            _cell("Empregado", st, bold=True),
            _cell(nome, st),
            _cell("CPF", st, bold=True),
            _cell(_fmt_cpf(funcionario.get("cpf")), st),
        ],
        [
            _cell("Cargo / Função", st, bold=True),
            _cell(cargo, st),
            _cell("CBO", st, bold=True),
            _cell(_cbo(cargo, funcionario), st),
        ],
        [
            _cell("Admissão", st, bold=True),
            _cell(_br_date(funcionario.get("data_admissao")), st),
            _cell("Afastamento", st, bold=True),
            _cell(_br_date(calc.get("last_working_day")), st),
        ],
        [
            _cell("Empregador", st, bold=True),
            _cell(_empresa_doc["razao"], st),
            _cell("CNPJ", st, bold=True),
            _cell(_empresa_doc["cnpj"], st),
        ],
    ]
    t_id = Table(ident, colWidths=[26 * mm, W / 2 - 26 * mm, 22 * mm, W / 2 - 22 * mm])
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
    story.append(_titulo("IDENTIFICAÇÃO", st, "user"))
    story.append(t_id)
    story.append(Spacer(1, 2 * mm))
    story.append(
        Paragraph(f"<b>Causa do afastamento:</b> {tipo_label}", st["small"])
    )
    story.append(Spacer(1, 3 * mm))

    # ── Verbas rescisórias (proventos) ──
    def _linha(desc, ref, valor):
        return [_cell(desc, st), _cell(ref, st), _cell(B.brl(valor), st, right=True)]

    avos_13 = calc.get("avos_decimo_terceiro")
    avos_fer = calc.get("avos_ferias_proporcionais")
    aviso_dias = calc.get("aviso_previo_dias")

    verbas = [
        [
            _cell("Verba", st, bold=True, cor=colors.white),
            _cell("Referência", st, bold=True, cor=colors.white),
            _cell("Valor", st, bold=True, right=True, cor=colors.white),
        ],
        _linha("Saldo de salário", "dias trab. no mês", _f("saldo_salario")),
        _linha(
            "Aviso prévio indenizado",
            f"{int(aviso_dias)} dias" if aviso_dias else "—",
            _f("aviso_previo_indenizado"),
        ),
        _linha(
            "13º salário proporcional",
            f"{int(avos_13)}/12 avos" if avos_13 is not None else "—",
            _f("decimo_terceiro_proporcional"),
        ),
        _linha(
            "Férias proporcionais",
            f"{int(avos_fer)}/12 avos" if avos_fer is not None else "—",
            _f("ferias_proporcionais"),
        ),
        _linha("1/3 sobre férias proporcionais", "constitucional", _f("terco_ferias_proporcionais")),
    ]
    # Férias vencidas só aparecem quando existem (evita linha zerada ruidosa).
    if _f("ferias_vencidas") > 0 or _f("terco_ferias_vencidas") > 0:
        verbas.append(_linha("Férias vencidas", "30 dias", _f("ferias_vencidas")))
        verbas.append(_linha("1/3 sobre férias vencidas", "constitucional", _f("terco_ferias_vencidas")))
    verbas.append(
        [
            _cell("TOTAL DE PROVENTOS", st, bold=True),
            _cell("", st),
            _cell(B.brl(_f("total_proventos")), st, bold=True, right=True),
        ]
    )
    t_verbas = Table(verbas, colWidths=[W - 78 * mm, 42 * mm, 36 * mm], repeatRows=1)
    t_verbas.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E1F2")),
                ("BACKGROUND", (0, 0), (-1, 0), B.AZUL_ESCURO),
                ("BACKGROUND", (0, -1), (-1, -1), B.FUNDO_CLARO),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(_titulo("VERBAS RESCISÓRIAS", st, "mais"))
    story.append(t_verbas)
    story.append(Spacer(1, 3 * mm))

    # ── Deduções (INSS + IRRF) ──
    deducoes = [
        [
            _cell("Dedução", st, bold=True, cor=colors.white),
            _cell("Base / Referência", st, bold=True, cor=colors.white),
            _cell("Valor", st, bold=True, right=True, cor=colors.white),
        ],
        _linha("INSS", "saldo salário + 13º", _f("inss")),
        _linha("IRRF", "tabela progressiva", _f("irrf")),
        [
            _cell("TOTAL DE DEDUÇÕES", st, bold=True),
            _cell("", st),
            _cell(B.brl(_f("total_descontos")), st, bold=True, right=True),
        ],
    ]
    t_ded = Table(deducoes, colWidths=[W - 78 * mm, 42 * mm, 36 * mm], repeatRows=1)
    t_ded.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E1F2")),
                ("BACKGROUND", (0, 0), (-1, 0), B.AZUL_ESCURO),
                ("BACKGROUND", (0, -1), (-1, -1), B.FUNDO_CLARO),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(_titulo("DEDUÇÕES", st, "menos"))
    story.append(t_ded)
    story.append(Spacer(1, 3 * mm))

    # ── Líquido + FGTS estimado ──
    liquido = _f("total_liquido")
    multa_fgts = _f("multa_fgts_40")
    saldo_fgts = _f("saldo_fgts_estimado")
    fgts_est = bool(calc.get("fgts_estimado"))
    fgts_suffix = " (estimado)" if fgts_est else ""
    resumo = [
        [
            _cell("Multa rescisória do FGTS (40%)" + fgts_suffix, st, bold=True),
            _cell(B.brl(multa_fgts), st, right=True),
        ],
        [
            _cell(f"Saldo de FGTS{fgts_suffix}", st),
            _cell(B.brl(saldo_fgts), st, right=True),
        ],
        [
            _cell("LÍQUIDO A RECEBER", st, bold=True, cor=colors.white, size=10),
            _cell(B.brl(liquido), st, bold=True, right=True, cor=colors.white, size=10),
        ],
    ]
    t_resumo = Table(resumo, colWidths=[W - 46 * mm, 46 * mm])
    t_resumo.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E1F2")),
                ("BACKGROUND", (0, -1), (-1, -1), B.AZUL_ESCURO),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(_titulo("RESUMO", st, "calc"))
    story.append(t_resumo)

    # Nota de veracidade do FGTS estimado (não fabricar valor legal).
    if fgts_est:
        story.append(Spacer(1, 2 * mm))
        story.append(
            Paragraph(
                "O saldo e a multa de FGTS são <b>ESTIMADOS</b> (8% sobre a remuneração × meses "
                "trabalhados) e devem ser conferidos com o extrato oficial da Caixa Econômica "
                "Federal antes da homologação. As tabelas de INSS/IRRF seguem a legislação "
                "vigente aplicada pelo motor de cálculo do Conecta PRO.",
                st["small"],
            )
        )

    # ── Autenticidade (só quando REALMENTE assinado) ──
    story += B.bloco_autenticidade_assinaturas(
        st, signatarios=meta.get("assinaturas") or [], empresa=_empresa_doc
    )

    # ── Campos de assinatura — EMPLOYEE + COMPANY (política rescisao) ──
    story += B.campos_assinatura(
        st,
        funcionario_nome=nome,
        funcionario_cpf=_fmt_cpf(funcionario.get("cpf")),
        funcionario_label="Assinatura do Empregado",
        espaco_antes=8,
        empresa=_empresa_doc,
    )

    titulo = "TRCT — TERMO DE RESCISÃO"
    doc.build(
        story,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo=titulo, empresa=_empresa_doc),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo=titulo, empresa=_empresa_doc),
    )
    return buf.getvalue()
