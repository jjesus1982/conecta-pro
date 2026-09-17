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

from modules.crm.services import pdf_branding as B  # noqa: N812

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


#: 09/09/2026 (Jordan): o VT tem duas modalidades — carteirinha do SINETRAM (ônibus) ou saldo de mobilidade no
#: cartão Sólides (quem tem condução própria). O VR é sempre no cartão Sólides.
_MODALIDADE = {
    "sinetram": "creditado na carteirinha do SINETRAM",
    "solides": "creditado como mobilidade no cartão Sólides",
}


def _periodo_uso(mes: int, ano: int) -> str:
    """Janela de uso do crédito: dia 17 da competência ao dia 16 do mês seguinte (padrão do recibo real)."""
    from datetime import date as _date

    try:
        ini = _date(int(ano), int(mes), 17)
    except (TypeError, ValueError):
        return "—"
    fim = _date(ini.year + (1 if ini.month == 12 else 0), 1 if ini.month == 12 else ini.month + 1, 16)
    return f"{ini:%d/%m/%Y} a {fim:%d/%m/%Y}"


def _onde_entrou(funcionario: dict) -> str:
    """Onde o crédito entrou de verdade — não o canal de sempre.

    Origem: 16/09/2026. O Sólides caiu e a empresa pagou VT e VR por PIX na conta de cada um,
    para ninguém ficar sem condução. O recibo continuava declarando «vale-refeição no cartão
    Sólides», e o funcionário assinaria que recebeu num cartão onde nada entrou. Recibo é
    documento: declarar canal errado é declarar recebimento errado.

    `pago_via_pix` é preenchido pelo controller quando existe pagamento REAL registrado na
    competência. Sem ele, mantém a redação de sempre.
    """
    if funcionario.get("e_pj"):
        # PJ não tem vale-transporte da Lei 7.418/1985 nem desconto em folha: o que recebe é
        # AJUDA DE CUSTO de transporte e alimentação, prevista no contrato de prestação de
        # serviços. Origem: 17/09/2026 — sete prestadores receberam VT/VR no lote e o recibo
        # de CLT os faria declarar vínculo empregatício que não existe.
        quando = funcionario.get("data_pagamento")
        return "paga por PIX na conta do prestador" + (f", em {quando}" if quando else "")
    if funcionario.get("pago_via_pix"):
        quando = funcionario.get("data_pagamento")
        vt_sinetran = funcionario.get("vt_pelo_sinetran")
        base = "vale-refeição por PIX na conta do colaborador"
        base += (
            "; vale-transporte pela carteirinha do SINETRAM"
            if vt_sinetran
            else "; vale-transporte por PIX na conta do colaborador"
        )
        return base + (f", em {quando}" if quando else "")
    return "vale-refeição no cartão Sólides; vale-transporte " + _MODALIDADE.get(
        funcionario.get("vt_modalidade") or "", "na modalidade contratada"
    )


def _rotulo_doc(funcionario: dict) -> str:
    """CPF ou CNPJ conforme o número que está no campo — não conforme o tipo de vínculo."""
    d = "".join(c for c in str(funcionario.get("cpf") or "") if c.isdigit())
    return "CNPJ" if len(d) == 14 else "CPF"


def _razao(funcionario: dict) -> str:
    """Razão social só quando ela existe e é diferente do nome — senão a linha vira eco."""
    r = str(funcionario.get("razao_social") or "").strip()
    nome = str(funcionario.get("nome") or "").strip()
    return r if r and r.casefold() != nome.casefold() else "—"


def _declaracao(funcionario: dict, empresa: dict, comp: str, periodo: str, onde: str) -> str:
    """O texto que a pessoa assina — CLT e PJ não podem assinar o mesmo.

    Origem: 17/09/2026. Sete prestadores PJ receberam VT/VR no lote do Jordan. O recibo de CLT
    invoca a Lei nº 7.418/1985 (vale-transporte de EMPREGADO) e fala em «co-participação legal
    descontada em folha». PJ não tem folha nem vale-transporte legal: assinando esse texto, o
    prestador declara vínculo empregatício que não existe — e o documento vira prova contra a
    empresa numa eventual reclamação. Para PJ é ajuda de custo por contrato de prestação.
    """
    quem = f"<b>{empresa['nome']}</b> (CNPJ {empresa['cnpj']})"
    if funcionario.get("e_pj"):
        return (
            f"<b>DECLARAÇÃO.</b> Declaro que recebi da {quem} os valores de ajuda de custo de "
            f"transporte e alimentação referentes ao período de <b>{comp}</b> ({onde}), "
            f"para utilização no período de <b>{periodo}</b>, nos termos do contrato de "
            f"prestação de serviços firmado entre as partes, nada mais tendo a reclamar quanto "
            f"a estes valores no período."
        )
    return (
        f"<b>DECLARAÇÃO.</b> Declaro que recebi da {quem} os valores de vale-transporte e "
        f"vale-refeição referentes à competência <b>{comp}</b> ({onde}), para utilização no "
        f"período de <b>{periodo}</b>, na forma da Lei nº 7.418/1985 e da Convenção Coletiva de "
        f"Trabalho da categoria, com a co-participação legal descontada em folha, nada mais "
        f"tendo a reclamar quanto a estes benefícios no período."
    )


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
    _mes = int(holerite.get("mes") or 0)
    _ano = int(holerite.get("ano") or 0)
    # O empregador/contratante sai do CPF da PESSOA. Para PJ o campo `cpf` carrega o CNPJ
    # dela (é o que o recibo exibe), e isso não casa com `employees.cpf` — o branding caía no
    # default e o recibo do Orlailson saía como CONECTA MAIS ELETRÔNICA quando quem pagou foi a
    # PATRIMONIAL. `cpf_vinculo` é o CPF de verdade, só para resolver a empresa.
    _empresa_doc = B.empresa_branding_por_cpf(
        funcionario.get("cpf_vinculo") or funcionario.get("cpf"),
        f"{_ano:04d}-{_mes:02d}" if _mes and _ano else None,
    )
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
            _cell("Prestador" if funcionario.get("e_pj") else "Funcionário", st, bold=True),
            _cell(holerite.get("employee_nome", "—"), st),
            _cell("Competência", st, bold=True),
            _cell(comp, st),
        ],
        [
            _cell("Cargo / Função", st, bold=True),
            _cell(cargo, st),
            _cell("Razão social" if funcionario.get("e_pj") else "CBO", st, bold=True),
            _cell(_razao(funcionario) if funcionario.get("e_pj") else _cbo(cargo, funcionario), st),
        ],
        [
            # O rótulo segue o NÚMERO, não o vínculo: prestador sem CNPJ cadastrado recebe
            # por CPF, e chamar CPF de CNPJ num recibo é erro de documento. (17/09/2026 — o
            # recibo da Pyetra saiu "CNPJ 016.132.302-22", que é o CPF dela.)
            _cell(_rotulo_doc(funcionario), st, bold=True),
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

    # O QUE FOI PAGO vence o que a folha calculou. Origem: 16/09/2026 — o recibo do ADAILSON
    # dizia VR 15 × R$ 22 = R$ 330 e VT 15 × R$ 10 = R$ 150, enquanto na conta dele entraram
    # R$ 308 e R$ 116. A folha multiplica dias-padrão por valor unitário; o pagamento saiu da
    # contagem real de dias. Recibo assinado com valor diferente do que entrou na conta é
    # problema trabalhista, não divergência de relatório.
    def _qtd_exata(valor: float, unit: float, atual: int) -> int | None:
        """Quantidade só quando ela MULTIPLICA de verdade.

        Arredondar dava linha que não fecha: R$ 116 com unitário R$ 10 virava «12 × 10,00 =
        116,00». Num recibo que alguém assina, conta que não bate é conta errada — melhor a
        coluna vazia do que um número inventado.
        """
        if not unit:
            return atual
        n = valor / unit
        return int(round(n)) if abs(n - round(n)) < 0.001 else None

    if holerite.get("vr_pago") is not None:
        vr_conc = float(holerite["vr_pago"])
        dias_vr = _qtd_exata(vr_conc, vr_dia, dias_vr)
    if holerite.get("vt_pago") is not None:
        vt_concedido = float(holerite["vt_pago"])
        dias_vt = _qtd_exata(vt_concedido, vt_dia, dias_vt)
    vr_liq = vr_conc - co_vr
    tem_vt = bool(vt_concedido)
    vt_liq = (vt_concedido - co_vt) if tem_vt else None

    def _c(txt, right=False, bold=False):
        return _cell(txt, st, right=right, bold=bold)

    # 09/09/2026: o recibo REAL usa os códigos da folha (218 VT, 219 VR) e separa valor unitário × quantidade.
    head = [
        [
            _cell("Cód", st, bold=True, cor=colors.white),
            _cell("Benefício", st, bold=True, cor=colors.white),
            _cell("Valor unit.", st, bold=True, right=True, cor=colors.white),
            _cell("Qtd", st, bold=True, right=True, cor=colors.white),
            _cell("Concedido", st, bold=True, right=True, cor=colors.white),
            _cell("Co-part.", st, bold=True, right=True, cor=colors.white),
            _cell("Líquido", st, bold=True, right=True, cor=colors.white),
        ]
    ]
    linhas = [
        [
            _c("219"),
            _c("Vale-Refeição"),
            _c(_brl_num(vr_dia), right=True),
            _c(str(dias_vr) if dias_vr is not None else "—", right=True),
            _c(_brl_num(vr_conc), right=True),
            _c(_brl_num(co_vr), right=True),
            _c(_brl_num(vr_liq), right=True, bold=True),
        ],
        [
            _c("218"),
            _c("Vale-Transporte"),
            _c(_brl_num(vt_dia), right=True),
            _c(str(dias_vt) if (tem_vt and dias_vt is not None) else "—", right=True),
            _c(_brl_num(vt_concedido) if tem_vt else "—", right=True),
            _c(_brl_num(co_vt), right=True),
            _c(_brl_num(vt_liq) if tem_vt else "—", right=True, bold=True),
        ],
    ]
    t_ben = Table(head + linhas, colWidths=[11 * mm, 38 * mm, 22 * mm, 12 * mm, 26 * mm, 24 * mm, 25 * mm])
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

    # citação legal da co-participação (letras menores) — transparência com o funcionário.
    # PJ não entra: não há desconto em folha nem Lei 7.418/1985 para prestador, e a nota
    # afirmaria uma coisa que a própria coluna dele mostra como 0,00.
    if not funcionario.get("e_pj"):
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
            _declaracao(funcionario, _empresa_doc, comp, _periodo_uso(_mes, _ano), _onde_entrou(funcionario)),
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
        empresa=_empresa_doc,
    )

    # Autenticidade branded: assinatura já coletada (motor universal) → bloco padrão-ouro.
    story += B.bloco_autenticidade_assinaturas(st, signatarios=signatarios, empresa=_empresa_doc)

    doc.build(
        story,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo="RECIBO VT / VR", empresa=_empresa_doc),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo="RECIBO VT / VR", empresa=_empresa_doc),
    )
    return buf.getvalue()
