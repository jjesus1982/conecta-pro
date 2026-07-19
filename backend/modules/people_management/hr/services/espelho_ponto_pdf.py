"""Espelho de Ponto — PDF legal (Portaria MTP 671/2021), padrão-ouro Conecta Mais.

Gera o espelho MENSAL de ponto a partir do que o MOTOR já calculou na tabela
`time_sheets` (horas, extras 50/100, adicional noturno, DSR, faltas, atrasos,
anomalias) + o array `daily_summary` (por dia). NÃO recalcula nada — apenas
renderiza o que já está calculado.

Cabeçalho: empregador (CONECTAMAIS ELETRONICA LTDA / CNPJ) + empregado
(nome/matrícula/CPF/PIS/cargo) + competência. Tabela diária (data, entrada, saída,
intervalo, horas, ocorrência). Totais legais. Bloco de assinaturas (funcionário +
empresa) e — quando já assinado — o bloco de AUTENTICIDADE das assinaturas.

Cabe harmonioso; a tabela diária pode passar para uma 2ª página (mês de 31 dias),
mas o cabeçalho/rodapé da marca se repetem em todas as páginas.
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
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]
_DOW = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def _fmt_cpf(v) -> str:
    d = "".join(ch for ch in str(v or "") if ch.isdigit())
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:11]}" if len(d) == 11 else (str(v or "") or "—")


def _fmt_pis(v) -> str:
    d = "".join(ch for ch in str(v or "") if ch.isdigit())
    return f"{d[:3]}.{d[3:8]}.{d[8:10]}-{d[10]}" if len(d) == 11 else (str(v or "") or "—")


def _hm(minutes) -> str:
    """Minutos (int) → 'HH:MM'. Tolerante a None/negativos."""
    try:
        m = int(round(float(minutes or 0)))
    except (TypeError, ValueError):
        return "—"
    sinal = "-" if m < 0 else ""
    m = abs(m)
    return f"{sinal}{m // 60:02d}:{m % 60:02d}"


def _dur(v) -> str:
    """Duração de uma célula diária. Já vem 'HH:MM' → passa; numérico → trata como minutos."""
    if v is None or v == "":
        return "—"
    if isinstance(v, str):
        return v if ":" in v else (_hm(v) if v.replace(".", "", 1).lstrip("-").isdigit() else v)
    return _hm(v)


def _horario(d: dict, *chaves: str) -> str:
    """Primeiro valor não-vazio dentre as chaves (entrada/saída/intervalo — tolerante ao motor)."""
    for k in chaves:
        val = d.get(k)
        if val:
            s = str(val)
            # normaliza 'HH:MM:SS' → 'HH:MM'
            if len(s) >= 5 and s[2:3] == ":":
                return s[:5]
            return s
    return "—"


def _ocorrencia(d: dict) -> str:
    """Deriva a ocorrência legível do dia a partir do daily_summary do motor."""
    nota = d.get("notes") or d.get("ocorrencia") or d.get("occurrence")
    if nota:
        return str(nota)
    if d.get("is_absent") or d.get("falta"):
        return "Falta"
    if d.get("is_holiday") or d.get("feriado"):
        return "Feriado"
    if d.get("is_dsr") or d.get("dsr"):
        return "DSR"
    ov = d.get("overtime") or d.get("overtime_minutes")
    if ov and float(ov or 0) > 0:
        return f"Hora extra ({_dur(ov)})"
    la = d.get("late") or d.get("late_minutes")
    if la and float(la or 0) > 0:
        return f"Atraso ({_dur(la)})"
    return "Normal"


def _cell(txt, *, bold=False, right=False, center=False, cor=None, size=8):
    ps = ParagraphStyle(
        "c",
        fontName=B.FONTE_B if bold else B.FONTE,
        fontSize=size,
        leading=size + 2.5,
        textColor=cor or B.TEXTO,
        alignment=1 if center else (2 if right else 0),
    )
    return Paragraph(str(txt), ps)


def _titulo(txt: str, st: dict):
    """Cabeçalho de seção (barra azul) — mesmo estilo do holerite."""
    p = Paragraph(
        f'<font color="#FFFFFF"><b>{txt}</b></font>',
        ParagraphStyle("sec", fontName=B.FONTE_B, fontSize=9, leading=12, textColor=colors.white),
    )
    t = Table([[p]], colWidths=[178 * mm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), B.AZUL_ESCURO),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (0, 0), 7),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return t


def montar_espelho_ponto_pdf(esp: dict, *, signatarios: list | None = None) -> bytes:
    """Gera o PDF do espelho de ponto a partir do dict lido de `time_sheets`.

    `esp` traz os campos do time_sheet (já em horas formatadas ou minutos) + a lista
    `dias` (daily_summary) + os dados do empregado. `signatarios` (opcional) vem do
    UniversalSignatureService.status() para carimbar o bloco de autenticidade.
    """
    st = B.styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=40 * mm, bottomMargin=16 * mm, leftMargin=16 * mm, rightMargin=16 * mm
    )
    W = A4[0] - 32 * mm
    mes = int(esp.get("mes") or esp.get("reference_month") or 0)
    ano = esp.get("ano") or esp.get("reference_year") or ""
    comp = f"{_MESES[mes] if 0 < mes < 13 else mes}/{ano}"
    # Multi-CNPJ E3: empregador vigente × competência (anti-reescrita)
    _empresa_doc = B.empresa_branding_por_cpf(
        esp.get("employee_cpf"), f"{int(ano):04d}-{mes:02d}" if mes and str(ano).isdigit() else None
    )
    story: list = []

    # ── EMPREGADOR + EMPREGADO ──
    ident = [
        [
            _cell("Empregador", bold=True),
            _cell(_empresa_doc["razao"]),
            _cell("CNPJ", bold=True),
            _cell(_empresa_doc["cnpj"]),
        ],
        [
            _cell("Empregado", bold=True),
            _cell(esp.get("employee_name") or "—"),
            _cell("Competência", bold=True),
            _cell(comp),
        ],
        [
            _cell("Cargo / Função", bold=True),
            _cell(esp.get("position_name") or "—"),
            _cell("Matrícula", bold=True),
            _cell(esp.get("employee_registration") or "—"),
        ],
        [
            _cell("CPF", bold=True),
            _cell(_fmt_cpf(esp.get("employee_cpf"))),
            _cell("PIS/PASEP", bold=True),
            _cell(_fmt_pis(esp.get("employee_pis"))),
        ],
        [
            _cell("Jornada contratual", bold=True),
            _cell(esp.get("work_schedule_name") or esp.get("escala") or "—"),
            _cell("Posto / Local", bold=True),
            _cell(esp.get("condominium_name") or esp.get("posto") or "—"),
        ],
    ]
    t_id = Table(ident, colWidths=[32 * mm, W / 2 - 32 * mm, 28 * mm, W / 2 - 28 * mm])
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
    story.append(_titulo("IDENTIFICAÇÃO", st))
    story.append(t_id)
    story.append(Spacer(1, 2.5 * mm))

    # ── TABELA DIÁRIA ──
    dias = esp.get("dias") or []
    head = [
        _cell("Data", bold=True, cor=colors.white),
        _cell("Dia", bold=True, cor=colors.white, center=True),
        _cell("Entrada", bold=True, cor=colors.white, center=True),
        _cell("Saída", bold=True, cor=colors.white, center=True),
        _cell("Intervalo", bold=True, cor=colors.white, center=True),
        _cell("Horas", bold=True, cor=colors.white, center=True),
        _cell("Ocorrência", bold=True, cor=colors.white),
    ]
    linhas = [head]
    for d in dias:
        data = d.get("date") or d.get("data") or ""
        # data 'YYYY-MM-DD' → 'DD/MM'
        dia_semana = ""
        data_fmt = str(data)
        try:
            from datetime import date as _date

            dt = _date.fromisoformat(str(data)[:10])
            data_fmt = dt.strftime("%d/%m")
            dia_semana = _DOW[dt.weekday()]
        except Exception:  # noqa: BLE001
            pass
        linhas.append(
            [
                _cell(data_fmt, size=7.5),
                _cell(dia_semana, center=True, size=7.5),
                _cell(_horario(d, "entrada", "clock_in", "entrada_1"), center=True, size=7.5),
                _cell(_horario(d, "saida", "saída", "clock_out", "saida_1"), center=True, size=7.5),
                _cell(_horario(d, "intervalo", "break", "intervalo_str") if (d.get("intervalo") or d.get("break")) else "—", center=True, size=7.5),
                _cell(_dur(d.get("worked") if d.get("worked") is not None else d.get("horas")), center=True, size=7.5),
                _cell(_ocorrencia(d), size=7.5),
            ]
        )
    if len(linhas) == 1:
        linhas.append([_cell("—", size=7.5)] + [_cell("—", center=True, size=7.5) for _ in range(4)] + [_cell("—", center=True, size=7.5), _cell("Sem lançamentos no período", size=7.5)])

    t_dias = Table(
        linhas,
        colWidths=[20 * mm, 14 * mm, 24 * mm, 24 * mm, 26 * mm, 22 * mm, W - 130 * mm],
        repeatRows=1,
    )
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), B.AZUL_ESCURO),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E1F2")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    for i in range(1, len(linhas)):
        if i % 2 == 0:
            estilo.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F8FAFC")))
    t_dias.setStyle(TableStyle(estilo))
    story.append(_titulo("REGISTRO DIÁRIO DE JORNADA", st))
    story.append(t_dias)
    story.append(Spacer(1, 2.5 * mm))

    # ── TOTAIS DO PERÍODO ──
    def _tot_cell(rot, val, *, destaque=False):
        return [
            _cell(rot, bold=True, size=8, cor=colors.white if destaque else None),
            _cell(val, right=True, bold=True, size=8, cor=colors.white if destaque else None),
        ]

    totais_rows = [
        _tot_cell("Horas trabalhadas", esp.get("horas_trabalhadas") or _hm(esp.get("hours_worked_minutes")), destaque=True)
        + _tot_cell("Horas previstas", esp.get("horas_previstas") or _hm(esp.get("hours_expected_minutes"))),
        _tot_cell("Extras 50%", esp.get("extras_50") or _hm(esp.get("overtime_50_minutes")))
        + _tot_cell("Extras 100%", esp.get("extras_100") or _hm(esp.get("overtime_100_minutes"))),
        _tot_cell("Adicional noturno", esp.get("adicional_noturno") or _hm(esp.get("night_hours_minutes")))
        + _tot_cell("Saldo banco de horas", esp.get("saldo_banco") or _hm(esp.get("hours_balance_minutes"))),
        _tot_cell("Faltas (dias)", str(esp.get("faltas_dias") if esp.get("faltas_dias") is not None else esp.get("absent_days", 0)))
        + _tot_cell("Atrasos", esp.get("atrasos") or _hm(esp.get("late_minutes"))),
        _tot_cell("DSR (dias com direito)", str(esp.get("dsr_dias") if esp.get("dsr_dias") is not None else esp.get("work_days_worked", 0)))
        + _tot_cell("DSR perdidos (dias)", str(esp.get("dsr_perdidos") if esp.get("dsr_perdidos") is not None else esp.get("dsr_lost_days", 0))),
    ]
    t_tot = Table(totais_rows, colWidths=[38 * mm, 22 * mm, 38 * mm, W - 98 * mm])
    t_tot.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E1F2")),
                ("BACKGROUND", (0, 0), (1, 0), B.LARANJA),
                ("BACKGROUND", (0, 1), (0, -1), B.FUNDO_CLARO),
                ("BACKGROUND", (2, 1), (2, -1), B.FUNDO_CLARO),
                ("BACKGROUND", (2, 0), (3, 0), B.FUNDO_CLARO),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(_titulo("TOTAIS DO PERÍODO", st))
    story.append(t_tot)

    # nota de anomalias (se houver)
    anom = int(esp.get("anomaly_count") or 0)
    if anom:
        story.append(Spacer(1, 1.5 * mm))
        story.append(
            Paragraph(
                f'<font size="7" color="#B45309">Este período possui {anom} ocorrência(s) sinalizada(s) '
                f"pelo sistema de ponto (anomalias). O DP confere e ajusta conforme as justificativas.</font>",
                st["small"],
            )
        )

    # ── Assinaturas (funcionário homologa + empresa) ──
    story += B.campos_assinatura(
        st,
        funcionario_nome=esp.get("employee_name"),
        funcionario_cpf=_fmt_cpf(esp.get("employee_cpf")),
        funcionario_label="Assinatura do Funcionário (homologação)",
        digital_funcionario=True,
        espaco_antes=8,
        incluir_empresa=True,
    )

    # ── Bloco de autenticidade (pós-assinatura) ──
    if signatarios:
        story += B.bloco_autenticidade_assinaturas(st, signatarios=signatarios)

    # nota legal
    story.append(Spacer(1, 3 * mm))
    story.append(
        Paragraph(
            '<font size="6.5" color="#6B7280">Espelho de ponto emitido nos termos da Portaria MTP nº 671/2021 '
            "(art. 74 e seguintes da CLT). Registro eletrônico de jornada consolidado a partir das batidas do "
            "colaborador. A homologação pelo funcionário é feita por assinatura eletrônica (data/hora + hash "
            "SHA-256) no Portal do Funcionário (Meu Espaço).</font>",
            st["small"],
        )
    )

    doc.build(
        story,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo="ESPELHO DE PONTO", empresa=_empresa_doc),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo="ESPELHO DE PONTO", empresa=_empresa_doc),
    )
    return buf.getvalue()
