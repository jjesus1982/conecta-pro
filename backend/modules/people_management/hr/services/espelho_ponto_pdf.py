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


def _pontos(d: dict) -> str:
    """Coluna PONTOS do dia — PERÍODO 1..6 no formato da folha de ponto (modelo Solides).

    28/09/2026 — o gerador tinha UMA coluna Entrada e UMA coluna Saída, então o plantão
    19:00→02:00 + 03:00→07:17 saía impresso como "19:00 … 07:17" e a parada de 1h da madrugada
    não existia no documento que o colaborador assina. O motor já pareava certo e já publica o
    detalhe: `daily_summary[].segmentos` (espelho_service.py:_segmentos, 28/09/2026). Medido no
    banco: 691 dias com `segmentos` e **388 deles com 2+ segmentos** — 56% dos plantões de
    09/2026 tinham mais de um par escondido atrás da linha única.

    `(m)` = batida lançada à mão, como no modelo. Fonte: `segmentos[].entrada_manual` /
    `saida_manual`, que o motor deriva da batida de ajuste — não é heurística deste arquivo.

    Sem a chave `segmentos` (todo espelho calculado ANTES de 28/09/2026 — ex.: 07 e 08/2026, 0 de
    3356 dias com a chave) cai no par entrada/saída único, que é o que o motor publicava. Nunca
    inventa período que o motor não pareou.
    """
    segs = [s for s in (d.get("segmentos") or []) if isinstance(s, dict)]
    if not segs:
        ent = _horario(d, "entrada", "clock_in", "entrada_1")
        sai = _horario(d, "saida", "saída", "clock_out", "saida_1")
        return "—" if (ent == "—" and sai == "—") else f"{ent} {sai} |"

    def _ponta(val, manual: bool) -> str:
        s = str(val or "")[:5]
        if not s:
            return "—"  # órfã: o motor não achou o par; o modelo deixa em branco, não chuta hora
        return ("(m)" if manual else "") + s

    partes = [
        f'{_ponta(s.get("entrada"), bool(s.get("entrada_manual")))} '
        f'{_ponta(s.get("saida"), bool(s.get("saida_manual")))} |'
        for s in segs[:6]
    ]
    # A folha tem SEIS colunas de período. Mais que isso não se corta em silêncio: diz quantos
    # ficaram de fora, porque par perdido no documento assinado é hora que ninguém vê.
    if len(segs) > 6:
        partes.append(f"(+{len(segs) - 6} períodos)")
    return " ".join(partes)


def _calendario(esp: dict) -> list[str]:
    """Todos os dias ISO do período IMPRESSO — não só os que têm batida medida.

    🔴 28/09/2026, decisão do Jordan («2»). Medido em agosto/2026: das **3.420 batidas do mês,
    só 1.390 são MEDIÇÃO** (41%). O resto é grade de escala — o Tangerino traz 65% das batidas
    em hora cheia e o `web` tem **4 horários distintos para 414 batidas** — e `FONTES_MEDIDAS`
    corretamente não conta isso. Consequência: os 68 espelhos de agosto têm média de **9,2 dias**
    num mês de 31, e a tabela deste PDF, que percorria só `dias`, saía com 9 linhas.

    ⭐ Folha de ponto de cliente com dois terços do mês AUSENTE não é folha incompleta, é folha
    que esconde. O calendário aqui faz o dia existir na página; quem não tem marcação sai
    rotulado «Sem registro eletrônico», com a grade ao lado como referência. O leitor vê que
    houve cobertura E que a marcação não existe — as duas coisas, nenhuma inventada.

    A janela sai de `periodo_de`/`periodo_ate` quando o chamador manda (a folha do kit é 26→25);
    senão, mês civil da competência. Nunca deriva de `dias`: lista rala daria janela rala, que é
    exatamente o defeito.
    """
    from calendar import monthrange
    from datetime import date as _d
    from datetime import timedelta as _td

    de = esp.get("periodo_de") or esp.get("de")
    ate = esp.get("periodo_ate") or esp.get("ate")
    try:
        if de and ate:
            d0, d1 = _d.fromisoformat(str(de)[:10]), _d.fromisoformat(str(ate)[:10])
        else:
            mes = int(esp.get("mes") or esp.get("reference_month") or 0)
            ano = int(esp.get("ano") or esp.get("reference_year") or 0)
            if not (0 < mes < 13 and ano > 2000):
                return []
            d0 = _d(ano, mes, 1)
            d1 = _d(ano, mes, monthrange(ano, mes)[1])
    except (TypeError, ValueError):
        return []
    if d1 < d0 or (d1 - d0).days > 400:
        return []  # janela absurda: melhor cair no comportamento antigo que imprimir 4 anos
    return [(d0 + _td(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def _abono(d: dict) -> str:
    """ABONO do dia — em branco quando não há justificativa aprovada (o normal hoje).

    `abono == -1` = justificativa de DIA INTEIRO: o abono vale as PREVISTAS do dia, que é o
    mecanismo pelo qual o dia não trabalhado deixa de virar desconto (SALDO fecha em zero).
    Fonte em `espelho_ponto_service.abono_por_dia` (time_justifications). Hoje a tabela tem 0
    linhas → esta coluna sai tracejada para todo mundo. Dash, nunca 00:00: zero pareceria
    "apurado e deu zero" quando a verdade é "não há lançamento de abono nesta casa".
    """
    v = d.get("abono")
    if v is None:
        return "—"
    if v == -1:
        return _dur(d.get("expected"))
    return _dur(v)


def _saldo_dia(d: dict) -> str:
    """SALDO do dia = TRABALHADAS + ABONO − PREVISTAS, com os minutos que o MOTOR já apurou.

    Não é matemática nova de folha: `worked` e `expected` são os dois números que o motor grava
    por dia, e a subtração é a mesma que ele faz no total (`hours_balance_minutes`). Só estava
    fora do papel — e é a coluna que mostra por que um dia abonado fecha em zero.
    """
    w, e = d.get("worked"), d.get("expected")
    if w is None or e is None:
        return "—"
    try:
        ab = d.get("abono")
        abm = int(e) if ab == -1 else int(ab or 0)
        return _hm(int(w) + abm - int(e))
    except (TypeError, ValueError):
        return "—"


def _abono_total(esp: dict) -> str:
    """Abono somado sobre os dias IMPRESSOS — "—" quando não há nenhum lançamento.

    Rótulo diz "(dias impressos)" de propósito: os outros números desta caixa são do MÊS CIVIL
    (`ler_espelho` filtra `time_sheets` por reference_month/year) e a tabela de dias pode ser de
    outra janela. Somar abono do período debaixo de um rótulo genérico repetiria o defeito que o
    rótulo "TOTAIS DE MM/AAAA (MÊS CIVIL)" existe para não cometer.
    """
    tot = 0
    achou = False
    for d in esp.get("dias") or []:
        if not isinstance(d, dict) or d.get("abono") is None:
            continue
        achou = True
        try:
            tot += int(d.get("expected") or 0) if d["abono"] == -1 else int(d["abono"])
        except (TypeError, ValueError):
            pass
    return _hm(tot) if achou else "—"


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


def montar_espelho_ponto_pdf(
    esp: dict, *, signatarios: list | None = None, grade: dict[str, str] | None = None
) -> bytes:
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
    # 09/09/2026 (Pyetra): a folha de ponto do kit cobre 26/x a 25/y — quando vier o período, ele aparece ao lado
    # da competência, senão o leitor acha que faltam dias no começo e no fim do mês.
    # 28/09/2026 — o período saía GRUDADO na competência ("Agosto/2026 · período 26/07… a 25/08…")
    # e agora tem linha própria ("Período impresso") logo abaixo, no bloco de identificação. Duas
    # vezes a mesma data em duas células diferentes é exatamente o "complicar" de que a Pyetra
    # reclamou. A informação não sumiu, mudou de lugar — quem procura o período acha rotulado.
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
        # 28/09/2026 — CTPS/Série, Código, Centro de Custo, Admissão e Quadro de Horários: os
        # cinco campos do cabeçalho do modelo real (auditoria/pyetra-prints/fp.pdf) que o gerador
        # não tinha. Todos de coluna que JÁ EXISTIA em `employees` (ver ler_espelho). Medido em 93
        # ativos: ctps_numero 35 · ctps_serie 34 · codigo 44 · centro_custo **0** — e no modelo do
        # Solides o Centro de Custo também sai vazio, então em branco aqui é o dado, não um furo.
        [
            _cell("CTPS / Série", bold=True),
            _cell(
                f'{esp.get("employee_ctps") or "—"}'
                f'{" / " + str(esp["employee_ctps_serie"]) if esp.get("employee_ctps_serie") else ""}'
            ),
            _cell("Código", bold=True),
            _cell(esp.get("employee_codigo") or "—"),
        ],
        [
            _cell("Admissão", bold=True),
            _cell(B.br_date(esp.get("employee_admissao")) if esp.get("employee_admissao") else "—"),
            _cell("Centro de Custo", bold=True),
            _cell(esp.get("employee_centro_custo") or "—"),
        ],
        [
            _cell("Quadro de Horários", bold=True),
            # `quadro_horarios` é None quando a escala publicada dá MAIS DE UMA janela para a
            # pessoa no período (48 de 63 pessoas na janela 26/07→25/08/2026). Escala que responde
            # três horários não é fonte de "o horário dele": diz o motivo em vez de escolher um.
            _cell(esp.get("quadro_horarios") or "— (escala do período não dá janela única)"),
            _cell("Período impresso", bold=True),
            _cell(esp.get("periodo_kit") or comp),
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
    # 28/09/2026 — colunas do modelo real: DIA/MÊS | PONTOS (período 1..6) | TRABALHADAS |
    # PREVISTAS | ABONO | SALDO | Ocorrência. "Entrada/Saída/Intervalo" viraram PONTOS porque
    # três colunas fixas não cabem um plantão de 2+ pares (388 dias medidos) — era o defeito.
    head = [
        _cell("Dia / Mês", bold=True, cor=colors.white),
        _cell("Dia", bold=True, cor=colors.white, center=True),
        _cell("Pontos (períodos 1 a 6)", bold=True, cor=colors.white, center=True),
        _cell("Trabalh.", bold=True, cor=colors.white, center=True),
        _cell("Previstas", bold=True, cor=colors.white, center=True),
        _cell("Abono", bold=True, cor=colors.white, center=True),
        _cell("Saldo", bold=True, cor=colors.white, center=True),
        _cell("Ocorrência", bold=True, cor=colors.white),
    ]
    # 28/09/2026 («2» do Jordan) — o calendário do período manda, não a lista de dias medidos.
    # `por_data` indexa o que o motor apurou; o dia que não estiver lá sai rotulado «Sem registro
    # eletrônico» com a grade ao lado. Se o calendário não puder ser derivado (competência
    # ausente, janela absurda), cai no comportamento antigo — degradar é melhor que não imprimir.
    por_data = {str(x.get("date") or x.get("data") or "")[:10]: x for x in dias}
    cal = _calendario(esp)
    grade = grade or {}
    n_sem_registro = 0
    percorrer: list[dict] = (
        [por_data.get(iso) or {"date": iso, "_sem_registro": True} for iso in cal] if cal else list(dias)
    )

    linhas = [head]
    for d in percorrer:
        sem_registro = bool(d.get("_sem_registro"))
        if sem_registro:
            n_sem_registro += 1
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
        # A grade NUNCA entra na coluna como se fosse marcação: vai entre parênteses, precedida
        # de «ref.», e o rótulo da ocorrência diz que registro eletrônico não houve. Horário de
        # escala impresso como se fosse batida é a fabricação que esta casa proíbe.
        if sem_registro:
            ref = str(grade.get(str(data)[:10]) or "").strip()
            col_pontos = f"(ref. {ref})" if ref else "—"
        else:
            col_pontos = _pontos(d)
        linhas.append(
            [
                _cell(data_fmt, size=7.5),
                _cell(dia_semana, center=True, size=7.5),
                _cell(col_pontos, center=True, size=7, cor=colors.HexColor("#94A3B8") if sem_registro else None),
                _cell(_dur(d.get("worked") if d.get("worked") is not None else d.get("horas")), center=True, size=7.5),
                _cell(_dur(d.get("expected")) if d.get("expected") is not None else "—", center=True, size=7.5),
                _cell(_abono(d), center=True, size=7.5),
                _cell(_saldo_dia(d), center=True, size=7.5),
                _cell(
                    "Sem registro eletrônico" if sem_registro else _ocorrencia(d),
                    size=7.5,
                    cor=colors.HexColor("#B45309") if sem_registro else None,
                ),
            ]
        )
    if len(linhas) == 1:
        linhas.append(
            [_cell("—", size=7.5)]
            + [_cell("—", center=True, size=7.5) for _ in range(6)]
            + [_cell("Sem lançamentos no período", size=7.5)]
        )

    t_dias = Table(
        linhas,
        colWidths=[17 * mm, 13 * mm, 54 * mm, 17 * mm, 17 * mm, 15 * mm, 15 * mm, W - 148 * mm],
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
    # Sem esta nota, «Sem registro eletrônico» é lido como FALTA — e falta é o contrário do que o
    # rótulo diz. Ela só aparece quando existe o caso, para não virar ruído em folha completa.
    if n_sem_registro:
        story.append(Spacer(1, 1.2 * mm))
        story.append(
            Paragraph(
                f"<font size=6.5 color='#B45309'>Dos {len(percorrer)} dias do período, "
                f"<b>{n_sem_registro}</b> constam <b>sem registro eletrônico de ponto</b>: não houve "
                f"marcação individual capturada pelo aplicativo. Isso <b>não</b> significa ausência "
                f"do posto — onde há escala publicada, o horário previsto aparece na coluna de "
                f"pontos entre parênteses, precedido de «ref.», apenas como referência. "
                f"Horário de escala não é marcação de ponto e não foi computado nas horas "
                f"trabalhadas deste espelho.</font>",
                st["small"],
            )
        )
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
        # 28/09/2026 — o modelo separa HORAS NOTURNAS de HORAS FICTA e o PDF imprimia só um
        # número, chamado "Adicional noturno". São duas grandezas do MESMO motor:
        # `daily_summary[].night_real` = relógio dentro de 22h–05h; `night_hours_minutes` =
        # os mesmos minutos em horas REDUZIDAS de 52'30" (a quantidade legal, base dos 20%).
        # Conferido em ADAILSON/08-2026: 2160 min de relógio ↔ 2469 reduzidos. Um rótulo só
        # apagava o relógio; agora cada número diz qual é.
        _tot_cell("Horas noturnas (22h–05h)", esp.get("horas_noturnas_reais") or "—")
        + _tot_cell("Horas ficta (noturna reduzida 52'30\")", esp.get("adicional_noturno") or _hm(esp.get("night_hours_minutes"))),
        _tot_cell("Dias faltosos", str(esp.get("faltas_dias") if esp.get("faltas_dias") is not None else esp.get("absent_days", 0)))
        + _tot_cell("Atrasos", esp.get("atrasos") or _hm(esp.get("late_minutes"))),
        _tot_cell("Saldo do período", esp.get("saldo_banco") or _hm(esp.get("hours_balance_minutes")))
        + _tot_cell("Abono lançado (dias impressos)", _abono_total(esp)),
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
    # 28/09/2026 — os totais são SEMPRE do mês civil: `ler_espelho` filtra `time_sheets` por
    # reference_month/reference_year (espelho_ponto_service.py:41) e nenhum número desta caixa
    # muda quando a tabela de dias troca de janela. Com `periodo_kit` presente a tabela acima tem
    # 31 dias de 26/08 a 25/09 (6 deles de agosto) e o rótulo "TOTAIS DO PERÍODO" fazia o PDF
    # somar um período embaixo de outro — coerente na aparência, errado. Rotular em vez de omitir
    # porque o número é fato apurado pelo motor; o que faltava era dizer de qual janela ele é.
    # Derivado de `periodo_kit` (e não de uma flag nova) para pegar TODO chamador que troca a
    # janela — inclusive o kit do GEDEON, que já tinha o mesmo defeito e é território alheio.
    rot_tot = f"TOTAIS DE {mes:02d}/{ano} (MÊS CIVIL)" if esp.get("periodo_kit") else "TOTAIS DO PERÍODO"
    story.append(_titulo(rot_tot, st))
    story.append(t_tot)

    # nota de anomalias (se houver)
    anom = int(esp.get("anomaly_count") or 0)
    if anom:
        # 28/09/2026 — `anomaly_count` vem de `time_sheets` do MÊS CIVIL, como todo número desta
        # caixa. A frase dizia "Este período possui 34 ocorrência(s)" debaixo de uma tabela de
        # 26/07→25/08: o leitor soma as 34 ao período impresso. Mesma saída do rótulo dos totais
        # (nomear a competência em vez de omitir o fato), pela mesma razão — a contagem é apurada
        # pelo motor, só não é do período que está na tabela.
        onde = f"A competência {mes:02d}/{ano} possui" if esp.get("periodo_kit") else "Este período possui"
        story.append(Spacer(1, 1.5 * mm))
        story.append(
            Paragraph(
                f'<font size="7" color="#B45309">{onde} {anom} ocorrência(s) sinalizada(s) '
                f"pelo sistema de ponto (anomalias). O DP confere e ajusta conforme as justificativas.</font>",
                st["small"],
            )
        )

    # ── DECLARAÇÃO DE RECONHECIMENTO ──
    # 28/09/2026 — está no modelo real (fp.pdf, todas as 53 páginas) e é o que dá sentido à
    # assinatura logo abaixo: sem a frase, o colaborador assina um documento que não diz o que
    # ele está reconhecendo. Texto fixo (não é dado de banco), nome e empresa vêm do espelho.
    story.append(Spacer(1, 3 * mm))
    story.append(
        Paragraph(
            '<font size="8"><b>Reconheço a exatidão e confirmo a frequência constante deste '
            f'cartão.</b></font><br/><font size="7.5" color="#374151">{esp.get("employee_name") or "—"}'
            f' — {_empresa_doc["razao"]}</font>',
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
        empresa=_empresa_doc,
    )

    # ── Bloco de autenticidade (pós-assinatura) ──
    if signatarios:
        story += B.bloco_autenticidade_assinaturas(st, signatarios=signatarios, empresa=_empresa_doc)

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
