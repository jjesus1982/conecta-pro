"""Aviso Prévio — PDF padrão-ouro Conecta Mais (Lei 12.506/2011 / CLT art. 487-491).

Comunicado formal de aviso prévio ao colaborador: identificação do empregador e do
empregado, modalidade (trabalhado ou indenizado), data de início da contagem, dias
concedidos (30 + 3/ano de serviço, teto 90 — Lei 12.506), projeção do último dia de
trabalho, e os campos de assinatura EMPLOYEE + COMPANY (política já mapeada).

Uma folha A4, branded (pdf_branding), texto sempre dentro das caixas — mesma identidade
visual do holerite/ficha de EPI. Quando o documento já foi assinado eletronicamente, o
bloco de autenticidade exibe os hashes REAIS coletados pelo motor de assinatura — nunca
fabricados.
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
    """dd/mm/aaaa a partir de date OU string ISO; '—' quando ausente."""
    if not v:
        return "—"
    s = str(v)[:10]
    try:
        from datetime import date as _d

        return _d.fromisoformat(s).strftime("%d/%m/%Y")
    except ValueError:
        return B.br_date(v)


_MODALIDADE_LABEL = {
    "trabalhado": "AVISO PRÉVIO TRABALHADO",
    "indenizado": "AVISO PRÉVIO INDENIZADO",
}

_TEXTO_TRABALHADO = (
    "Comunicamos que, nos termos dos artigos 487 a 491 da CLT e da Lei nº 12.506/2011, "
    "fica V. Sa. cientificado(a) do <b>AVISO PRÉVIO</b>, na modalidade <b>TRABALHADO</b>, "
    "referente ao encerramento do seu contrato de trabalho junto à <b>{empresa}</b> "
    "(CNPJ {cnpj}). Durante o período do aviso, permanecem em vigor todos os direitos e "
    "deveres decorrentes do contrato de trabalho, sendo assegurada a redução de 2 (duas) "
    "horas na jornada diária ou a dispensa de 7 (sete) dias corridos ao final do período, "
    "à escolha do(a) empregado(a) (CLT, art. 488)."
)

_TEXTO_INDENIZADO = (
    "Comunicamos que, nos termos dos artigos 487 a 491 da CLT e da Lei nº 12.506/2011, "
    "fica V. Sa. cientificado(a) do <b>AVISO PRÉVIO</b>, na modalidade <b>INDENIZADO</b>, "
    "referente ao encerramento do seu contrato de trabalho junto à <b>{empresa}</b> "
    "(CNPJ {cnpj}). O período do aviso prévio será indenizado e integrará o tempo de "
    "serviço para todos os efeitos legais (CLT, art. 487, §1º), sendo o respectivo valor "
    "quitado no Termo de Rescisão do Contrato de Trabalho (TRCT)."
)

_NOTA_LEI_12506 = (
    "O prazo do aviso prévio observa a proporcionalidade da Lei nº 12.506/2011: 30 (trinta) "
    "dias, acrescidos de 3 (três) dias por ano completo de serviço prestado ao mesmo "
    "empregador, até o limite total de 90 (noventa) dias."
)


def montar_aviso_previo_pdf(dados: dict, funcionario: dict | None = None) -> bytes:
    """Gera o PDF do Aviso Prévio no padrão-ouro Conecta Mais.

    dados: {
        termination_id, employee_nome, modalidade ('trabalhado'|'indenizado'),
        notice_start_date, notice_period_days, last_working_day,
        anos_servico (opcional), assinaturas (lista do status do motor, opcional)
    }
    funcionario: dict do employees (cpf, cargo, data_admissao) — ausentes ficam '—'.
    """
    funcionario = funcionario or {}
    # Multi-CNPJ E3: empregador vigente do funcionário (rescisão usa a empresa do vínculo;
    # demitidos antigos não fizeram flip => resolvem CNPJ1 naturalmente)
    _empresa_doc = B.empresa_branding_por_cpf(funcionario.get('cpf'))
    st = B.styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=40 * mm, bottomMargin=16 * mm, leftMargin=16 * mm, rightMargin=16 * mm
    )
    W = A4[0] - 32 * mm
    story: list = []

    nome = dados.get("employee_nome") or funcionario.get("nome") or "—"
    cargo = funcionario.get("cargo") or "—"
    modalidade = (dados.get("modalidade") or "").lower()
    if modalidade not in ("trabalhado", "indenizado"):
        modalidade = "indenizado"  # default seguro; a modalidade real vem do processo
    modalidade_label = _MODALIDADE_LABEL[modalidade]
    dias = dados.get("notice_period_days")
    dias_txt = f"{int(dias)} dias" if dias else "—"

    # ── Identificação do empregado ──
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
            _cell("Processo nº", st, bold=True),
            _cell(str(dados.get("termination_id", "—"))[:8].upper(), st),
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
    story.append(_titulo("IDENTIFICAÇÃO DO EMPREGADO", st, "user"))
    story.append(t_id)
    story.append(Spacer(1, 3 * mm))

    # ── Empregador ──
    emp = [
        [
            _cell("Empregador", st, bold=True),
            _cell(_empresa_doc["razao"], st),
        ],
        [
            _cell("CNPJ", st, bold=True),
            _cell(_empresa_doc["cnpj"], st),
        ],
    ]
    t_emp = Table(emp, colWidths=[26 * mm, W - 26 * mm])
    t_emp.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E1F2")),
                ("BACKGROUND", (0, 0), (0, -1), B.FUNDO_CLARO),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(_titulo("EMPREGADOR", st, "user"))
    story.append(t_emp)
    story.append(Spacer(1, 3 * mm))

    # ── Condições do aviso ──
    cond = [
        [
            _cell("Modalidade", st, bold=True, cor=colors.white),
            _cell("Início da contagem", st, bold=True, cor=colors.white),
            _cell("Dias concedidos", st, bold=True, cor=colors.white),
            _cell("Último dia de trabalho", st, bold=True, cor=colors.white),
        ],
        [
            _cell(modalidade.capitalize(), st),
            _cell(_br_date(dados.get("notice_start_date")), st),
            _cell(dias_txt, st),
            _cell(_br_date(dados.get("last_working_day")), st),
        ],
    ]
    t_cond = Table(cond, colWidths=[W / 4] * 4)
    t_cond.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E1F2")),
                ("BACKGROUND", (0, 0), (-1, 0), B.AZUL_ESCURO),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(_titulo("CONDIÇÕES DO AVISO PRÉVIO", st, "calc"))
    story.append(t_cond)
    story.append(Spacer(1, 4 * mm))

    # ── Comunicado ──
    texto = _TEXTO_TRABALHADO if modalidade == "trabalhado" else _TEXTO_INDENIZADO
    story.append(Paragraph(texto.format(empresa=_empresa_doc["razao"], cnpj=_empresa_doc["cnpj"]), st["corpo"]))
    story.append(Paragraph(_NOTA_LEI_12506, st["corpo"]))

    # ── Autenticidade (só quando REALMENTE assinado) ──
    assinaturas = dados.get("assinaturas") or []
    story += B.bloco_autenticidade_assinaturas(st, signatarios=assinaturas)

    # ── Campos de assinatura — EMPLOYEE + COMPANY (política aviso_previo) ──
    story += B.campos_assinatura(
        st,
        funcionario_nome=nome,
        funcionario_cpf=_fmt_cpf(funcionario.get("cpf")),
        funcionario_label="Ciência do Empregado",
        espaco_antes=10,
    )

    doc.build(
        story,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo=modalidade_label, empresa=_empresa_doc),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo=modalidade_label, empresa=_empresa_doc),
    )
    return buf.getvalue()
