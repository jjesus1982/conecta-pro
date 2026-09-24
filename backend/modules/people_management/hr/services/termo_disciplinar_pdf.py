"""Termo de advertência / suspensão — PDF padrão-ouro Conecta Mais (DGX T1, 24/09/2026).

Antes: `disciplinary_actions.document_text` era texto puro renderizado do template (com sha256 e
assinatura digital), sem NENHUM PDF — o termo que se entrega ao colaborador e se arquiva no
prontuário não existia como documento. Este gerador NÃO reescreve o texto: pega o
`document_text` já gerado (e já hasheado/assinado) e o veste com a marca — cabeçalho, seções,
campos de assinatura (empregado + empresa + testemunhas quando há recusa) e o bloco de
autenticidade quando houve assinatura eletrônica. Mesma identidade do aviso prévio.
"""

from __future__ import annotations

import io
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules.crm.services import pdf_branding as B  # noqa: N812 — mesma grafia dos outros geradores
from modules.people_management.folha.services.holerite_pdf import _cell, _fmt_cpf, _titulo

TITULO = {
    "advertencia_verbal": "ADVERTÊNCIA VERBAL — REGISTRO",
    "advertencia_escrita": "ADVERTÊNCIA DISCIPLINAR",
    "suspensao": "SUSPENSÃO DISCIPLINAR",
    "demissao_justa_causa": "COMUNICADO DE JUSTA CAUSA",
}
_SECAO = re.compile(r"^[A-ZÀ-Ú0-9 ()/\-]{4,}:$")  # "DADOS DO FUNCIONARIO:" vira cabeçalho de seção
_LINHA_ASSINATURA = re.compile(r"^_{5,}$")


def _br(v) -> str:
    return B.br_date(v) if v else "—"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _corpo(texto: str, st: dict) -> list:
    """document_text → flowables. Pula o título (1ª linha) e o bloco de assinaturas em texto —
    esses dois saem da marca (título no cabeçalho, assinaturas nos campos oficiais)."""
    out: list = []
    linhas = (texto or "").splitlines()
    corte = next((i for i, ln in enumerate(linhas) if _LINHA_ASSINATURA.match(ln.strip())), len(linhas))
    # 1ª linha é título só quando há corpo depois dela e ela é toda maiúscula (template padrão);
    # a medida ADV-TFM-20250710 tem UMA linha de texto — pular a 1ª deixava o termo em branco.
    ini = 1 if corte > 1 and linhas and linhas[0].strip() and linhas[0].strip() == linhas[0].strip().upper() and len(linhas[0]) < 80 else 0
    for ln in linhas[ini:corte]:
        s = ln.strip()
        if not s:
            out.append(Spacer(1, 1.5 * mm))
        elif _SECAO.match(s):
            out.append(Paragraph(_esc(s[:-1]), st["h_sec"]))
        elif s[:2] in ("1.", "2.", "3.") or s.startswith("- "):
            out.append(Paragraph("&nbsp;&nbsp;&nbsp;" + _esc(s), st["corpo"]))
        else:
            out.append(Paragraph(_esc(s), st["corpo"]))
    return out


def montar_termo(acao: dict, assinaturas: list | None = None) -> bytes:
    """`acao`: linha de disciplinary_actions como dict (code, action_type, employee_name, employee_cpf,
    employee_position, employee_admission_date, incident_date, application_date, suspension_start_date,
    suspension_end_date, suspension_days, document_text, document_hash, employee_refused_sign,
    refusal_witness_*). `assinaturas`: lista do motor de assinatura (opcional)."""
    tipo = (acao.get("action_type") or "").lower()
    titulo = TITULO.get(tipo, "MEDIDA DISCIPLINAR")
    emp = B.empresa_branding_por_cpf(acao.get("employee_cpf"))
    st = B.styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=40 * mm, bottomMargin=16 * mm, leftMargin=16 * mm, rightMargin=16 * mm)
    W = A4[0] - 32 * mm
    story: list = []

    ident = [
        [_cell("Empregado", st, bold=True), _cell(acao.get("employee_name") or "—", st), _cell("CPF", st, bold=True), _cell(_fmt_cpf(acao.get("employee_cpf")), st)],
        [_cell("Cargo / Função", st, bold=True), _cell(acao.get("employee_position") or "—", st), _cell("Admissão", st, bold=True), _cell(_br(acao.get("employee_admission_date")), st)],
        [_cell("Medida nº", st, bold=True), _cell(acao.get("code") or "—", st), _cell("Ocorrido em", st, bold=True), _cell(_br(acao.get("incident_date")), st)],
    ]
    if tipo == "suspensao":
        dias = acao.get("suspension_days")
        ident.append(
            [
                _cell("Suspensão", st, bold=True),
                _cell(f"{_br(acao.get('suspension_start_date'))} a {_br(acao.get('suspension_end_date'))}", st),
                _cell("Dias", st, bold=True),
                _cell(str(dias) if dias is not None else "—", st),
            ]
        )
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
    story += [_titulo("IDENTIFICAÇÃO DO EMPREGADO", st, "user"), t_id, Spacer(1, 3 * mm)]
    story.append(_titulo("TERMO", st, "calc"))
    story.append(Spacer(1, 2 * mm))
    story += _corpo(acao.get("document_text") or "", st)
    desc = (acao.get("reason_description") or "").strip()
    if desc and desc not in (acao.get("document_text") or ""):
        story += [Paragraph("DESCRIÇÃO DA OCORRÊNCIA", st["h_sec"]), Paragraph(_esc(desc), st["corpo"])]
    if acao.get("document_hash"):
        story.append(Paragraph(f"Integridade do texto (SHA-256): {_esc(str(acao['document_hash']))[:64]}", st["small"]))
    story += B.bloco_autenticidade_assinaturas(st, signatarios=assinaturas or [], empresa=emp)
    story += B.campos_assinatura(
        st,
        funcionario_nome=acao.get("employee_name") or "—",
        funcionario_cpf=_fmt_cpf(acao.get("employee_cpf")),
        funcionario_label="Ciência do Empregado",
        responsavel_cargo="Departamento Pessoal",
        digital_funcionario=bool(acao.get("employee_signed_at")),
        digital_empresa=bool(acao.get("hr_signed_at") or acao.get("supervisor_signed_at")),
        espaco_antes=8,
        empresa=emp,
    )
    if acao.get("employee_refused_sign"):
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("<b>Recusa de assinatura</b> — testemunhas (CLT, art. 482, prática consolidada):", st["corpo"]))
        for i in (1, 2):
            n, c = acao.get(f"refusal_witness_{i}_name"), acao.get(f"refusal_witness_{i}_cpf")
            story.append(Paragraph(f"{i}. ____________________________ &nbsp; {_esc(n or '—')} · CPF {_fmt_cpf(c) if c else '—'}", st["corpo"]))
    doc.build(
        story,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo=titulo, empresa=emp),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo=titulo, empresa=emp),
    )
    return buf.getvalue()


def demo() -> None:
    texto = (
        "CARTA DE ADVERTENCIA\n\nA empresa X vem aplicar ADVERTENCIA ao funcionario:\n\nDADOS DO FUNCIONARIO:\nNome: FULANO\n\n"
        "CIENCIA:\n1. A reincidencia podera resultar em suspensao;\n\nManaus, 24/09/2026\n\n_________________________________\nEmpregador\n"
    )
    pdf = montar_termo(
        {"action_type": "suspensao", "code": "SUS-TST-1", "employee_name": "FULANO DE TAL", "employee_cpf": "52998224725",
         "suspension_days": 2, "document_text": texto, "employee_refused_sign": True, "refusal_witness_1_name": "Beltrano"}
    )
    assert pdf.startswith(b"%PDF") and len(pdf) > 3000
    fl = _corpo(texto, B.styles())
    assert sum(isinstance(f, Paragraph) for f in fl) == 6  # título fora, bloco de assinatura fora
    print("ok termo_disciplinar_pdf", len(pdf), "bytes")


if __name__ == "__main__":
    demo()
