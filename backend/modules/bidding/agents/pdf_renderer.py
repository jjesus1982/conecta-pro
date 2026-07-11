"""
PDF Renderer para documentos de licitacao
==========================================
Renderiza documentos gerados pelo CompilerAgent em PDF usando reportlab.

Cada tipo de documento tem layout profissional com:
- Cabecalho com dados da empresa
- Formatacao adequada (fontes, margens, tabelas)
- Rodape com numeracao de paginas
"""

import io
import logging
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from modules.crm.services import pdf_branding as B

logger = logging.getLogger(__name__)

# Diretorio padrao para salvar PDFs
PDF_OUTPUT_DIR = Path("/opt/conecta-pro/backend/media/bidding/proposals")

# Dados da empresa para cabecalho (marca centralizada)
COMPANY_HEADER = {
    "razao_social": B.EMPRESA["nome"],
    "cnpj": B.EMPRESA["cnpj"],
    "inscricao_municipal": "45177801",
    "endereco": B.EMPRESA["endereco"],
}


# ──────────────────────────────────────────────
# Estilos customizados
# ──────────────────────────────────────────────


def _build_styles() -> dict[str, ParagraphStyle]:
    """Cria estilos customizados para os documentos de licitacao."""
    base = getSampleStyleSheet()

    styles = {
        "company_name": ParagraphStyle(
            "CompanyName",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=14,
            alignment=TA_CENTER,
            spaceAfter=2 * mm,
            textColor=B.AZUL_ESCURO,
        ),
        "company_info": ParagraphStyle(
            "CompanyInfo",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            alignment=TA_CENTER,
            spaceAfter=1 * mm,
            textColor=colors.HexColor("#444444"),
        ),
        "doc_title": ParagraphStyle(
            "DocTitle",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            alignment=TA_CENTER,
            spaceBefore=8 * mm,
            spaceAfter=6 * mm,
            textColor=B.AZUL_ESCURO,
        ),
        "section_title": ParagraphStyle(
            "SectionTitle",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            spaceBefore=5 * mm,
            spaceAfter=3 * mm,
            textColor=B.AZUL_ESCURO,
        ),
        "body": ParagraphStyle(
            "BodyText2",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            alignment=TA_JUSTIFY,
            spaceBefore=2 * mm,
            spaceAfter=2 * mm,
        ),
        "body_bold": ParagraphStyle(
            "BodyBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            alignment=TA_JUSTIFY,
            spaceBefore=2 * mm,
            spaceAfter=2 * mm,
        ),
        "body_center": ParagraphStyle(
            "BodyCenter",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            alignment=TA_CENTER,
            spaceBefore=2 * mm,
            spaceAfter=2 * mm,
        ),
        "small": ParagraphStyle(
            "SmallText",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#666666"),
        ),
        "signature": ParagraphStyle(
            "Signature",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            alignment=TA_CENTER,
            spaceBefore=15 * mm,
            spaceAfter=2 * mm,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            alignment=TA_CENTER,
            textColor=colors.white,
        ),
        "table_cell": ParagraphStyle(
            "TableCell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            alignment=TA_LEFT,
        ),
        "table_cell_right": ParagraphStyle(
            "TableCellRight",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            alignment=TA_RIGHT,
        ),
        "table_cell_bold": ParagraphStyle(
            "TableCellBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            alignment=TA_LEFT,
        ),
        "table_total": ParagraphStyle(
            "TableTotal",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            alignment=TA_RIGHT,
        ),
        "ref_line": ParagraphStyle(
            "RefLine",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            spaceBefore=3 * mm,
            spaceAfter=3 * mm,
        ),
    }
    return styles


# ──────────────────────────────────────────────
# Page template helpers (header/footer)
# ──────────────────────────────────────────────

# Cores da marca centralizada (moldura visual padrao-ouro)
_HEADER_COLOR = B.AZUL_ESCURO
_LINE_COLOR = B.AZUL_MEDIO


def _create_doc_template(buffer: io.BytesIO, title: str = "Documento") -> SimpleDocTemplate:
    """Creates a SimpleDocTemplate with brand margins (top 40mm / bottom 16mm) and metadata."""
    return SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=title,
        author=COMPANY_HEADER["razao_social"],
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=40 * mm,
        bottomMargin=16 * mm,
    )


# ──────────────────────────────────────────────
# Shared building blocks
# ──────────────────────────────────────────────


def _build_doc_title(styles: dict, title: str) -> list:
    """Returns flowables for document title."""
    return [
        Spacer(1, 5 * mm),
        Paragraph(title, styles["doc_title"]),
        HRFlowable(width="100%", thickness=0.5, color=_LINE_COLOR, spaceAfter=4 * mm),
    ]


def _build_ref_block(styles: dict, orgao: str, modalidade: str, numero_edital: str) -> list:
    """Returns flowables for the reference/addressee block."""
    elements = []
    if orgao:
        elements.append(Paragraph(f"Ao<br/><b>{orgao}</b>", styles["body"]))
        elements.append(Spacer(1, 3 * mm))
    ref = f"Ref.: {modalidade} - Edital n. {numero_edital}" if modalidade and numero_edital else ""
    if ref:
        elements.append(Paragraph(ref, styles["ref_line"]))
        elements.append(Spacer(1, 3 * mm))
    return elements


def _build_signature_block(styles: dict, variaveis: dict) -> list:
    """Returns flowables for the signature block (marca centralizada, assinatura digital da empresa).

    Documento de licitacao e assinado SO pela empresa (CEO default JORDAN JESUS). Reaproveita o
    helper de marca B.campos_assinatura para o padrao visual, ocultando a coluna de
    "funcionario" (nao se aplica a proposta de licitacao).
    """
    data_hoje = B.br_date(datetime.utcnow())
    representante = variaveis.get("representante") or variaveis.get("representante_legal") or None
    # Licitação: só a EMPRESA (representante legal) assina — sem coluna de funcionário.
    flowables = B.campos_assinatura(
        responsavel_nome=representante,
        cidade="Manaus/AM",
        data_str=data_hoje,
        digital_empresa=True,
        data_empresa=data_hoje,
        incluir_funcionario=False,
    )
    return flowables


# ──────────────────────────────────────────────
# Document-specific renderers
# ──────────────────────────────────────────────


def _render_carta_proposta(content: str, variaveis: dict, styles: dict) -> list:
    """Builds flowable elements for Carta Proposta Comercial."""
    elements = []
    elements.extend(_build_doc_title(styles, "CARTA PROPOSTA COMERCIAL"))
    elements.extend(
        _build_ref_block(
            styles,
            variaveis.get("orgao", ""),
            variaveis.get("modalidade", ""),
            variaveis.get("numero_edital", ""),
        )
    )

    elements.append(Paragraph("Prezados Senhores,", styles["body"]))
    elements.append(Spacer(1, 3 * mm))

    intro = (
        f"A empresa <b>{variaveis.get('razao_social', '')}</b>, inscrita no CNPJ sob o n. "
        f"<b>{variaveis.get('cnpj', '')}</b>, Inscricao Municipal n. "
        f"{variaveis.get('inscricao_municipal', '')}, "
        f"com sede em {variaveis.get('endereco', '')}, por intermedio de seu representante legal "
        f"infra-assinado, apresenta a Vossa Senhoria proposta comercial para prestacao dos servicos "
        f"objeto do Edital em referencia, nos termos a seguir:"
    )
    elements.append(Paragraph(intro, styles["body"]))

    # 1. OBJETO
    elements.append(Paragraph("1. OBJETO", styles["section_title"]))
    elements.append(Paragraph(variaveis.get("objeto", "[OBJETO]"), styles["body"]))

    # 2. VALORES — as a small table
    elements.append(Paragraph("2. VALORES", styles["section_title"]))
    valor_data = [
        ["Descricao", "Valor", "Extenso"],
        [
            "Valor Mensal",
            variaveis.get("valor_mensal", ""),
            variaveis.get("valor_mensal_extenso", ""),
        ],
        [
            f"Valor Total ({variaveis.get('prazo_contrato', '12')} meses)",
            variaveis.get("valor_total", ""),
            variaveis.get("valor_total_extenso", ""),
        ],
    ]
    valor_table = Table(valor_data, colWidths=[4.5 * cm, 4 * cm, 8.5 * cm])
    valor_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _HEADER_COLOR),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f5f5f5")],
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(valor_table)

    # 3. VALIDADE
    elements.append(Paragraph("3. VALIDADE DA PROPOSTA", styles["section_title"]))
    prazo_val = variaveis.get("prazo_validade", "60")
    elements.append(
        Paragraph(
            f"Esta proposta tem validade de {prazo_val} (sessenta) dias corridos, "
            f"contados da data de sua apresentacao.",
            styles["body"],
        )
    )

    # 4. PRAZO
    elements.append(Paragraph("4. PRAZO DE EXECUCAO", styles["section_title"]))
    prazo_contrato = variaveis.get("prazo_contrato", "12")
    elements.append(
        Paragraph(
            f"O prazo de execucao dos servicos sera de {prazo_contrato} ({prazo_contrato}) meses, "
            f"conforme estabelecido no Edital, podendo ser prorrogado nos termos da legislacao vigente.",
            styles["body"],
        )
    )

    # 5. DADOS BANCARIOS
    elements.append(Paragraph("5. DADOS BANCARIOS", styles["section_title"]))
    bank_data = [
        ["Campo", "Dados"],
        ["Banco", variaveis.get("banco", "")],
        ["Agencia", variaveis.get("agencia", "")],
        ["Conta Corrente", variaveis.get("conta", "")],
        ["Titular", variaveis.get("razao_social", "")],
        ["CNPJ", variaveis.get("cnpj", "")],
    ]
    bank_table = Table(bank_data, colWidths=[4.5 * cm, 12.5 * cm])
    bank_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _HEADER_COLOR),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("FONTNAME", (1, 1), (-1, -1), "Helvetica"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f5f5f5")],
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(bank_table)

    # 6. DECLARACOES
    elements.append(Paragraph("6. DECLARACOES", styles["section_title"]))
    elements.append(Paragraph("Declaramos que:", styles["body"]))
    declaracoes = [
        (
            "a) Nos precos propostos estao inclusos todos os custos diretos e indiretos, "
            "encargos sociais, trabalhistas, previdenciarios, fiscais, comerciais, taxas, "
            "seguros, deslocamentos, bem como quaisquer outros custos que incidam ou venham "
            "a incidir sobre o objeto licitado;"
        ),
        (
            "b) Temos pleno conhecimento das condicoes e peculiaridades inerentes a natureza "
            "dos servicos, assumindo total responsabilidade por esse fato;"
        ),
        "c) Atendemos a todos os requisitos de habilitacao constantes do Edital;",
        (
            "d) Nao possuimos em nosso quadro societario servidor publico da ativa, ou "
            "empregado de empresa publica ou de sociedade de economia mista;"
        ),
        (
            "e) Nao possuimos, em nossa cadeia produtiva, empregados executando trabalho "
            "degradante ou forcado, observando o disposto nos incisos III e IV do art. 1o "
            "e no inciso III do art. 5o da Constituicao Federal;"
        ),
        (
            "f) Cumprimos as exigencias de reserva de cargos para pessoa com deficiencia e "
            "para reabilitado da Previdencia Social, previstas em lei e em outras normas "
            "especificas."
        ),
    ]
    for decl in declaracoes:
        elements.append(Paragraph(decl, styles["body"]))

    # 7. CONTATO
    elements.append(Paragraph("7. CONTATO", styles["section_title"]))
    elements.append(Paragraph(f"Telefone: {variaveis.get('telefone', '')}", styles["body"]))
    elements.append(Paragraph(f"E-mail: {variaveis.get('email', '')}", styles["body"]))

    # Signature
    elements.extend(_build_signature_block(styles, variaveis))

    return elements


def _render_planilha_custos(content: str, variaveis: dict, styles: dict, pricing_data: dict | None) -> list:
    """Builds flowable elements for Planilha de Custos."""
    elements = []
    elements.extend(_build_doc_title(styles, "PLANILHA DE COMPOSICAO DE CUSTOS E FORMACAO DE PRECOS"))

    # Company info block
    info_items = [
        ("Empresa", variaveis.get("razao_social", "")),
        ("CNPJ", variaveis.get("cnpj", "")),
        ("Edital", variaveis.get("numero_edital", "[N/A]")),
        ("Orgao", variaveis.get("orgao", "[N/A]")),
    ]

    if pricing_data:
        regime = pricing_data.get("regime_tributario", "lucro_real").upper().replace("_", " ")
        cenario_nome = pricing_data.get("cenario_recomendado", "moderado").upper()
        info_items.append(("Regime Tributario", regime))
        info_items.append(("Cenario", cenario_nome))

    info_data = [[k, v] for k, v in info_items]
    info_table = Table(info_data, colWidths=[4.5 * cm, 12.5 * cm])
    info_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("FONTNAME", (1, 0), (-1, -1), "Helvetica"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f0f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(info_table)
    elements.append(Spacer(1, 5 * mm))

    if not pricing_data:
        elements.append(
            Paragraph(
                "<i>[Dados de precificacao nao disponiveis - executar PRICER primeiro]</i>",
                styles["body"],
            )
        )
        return elements

    # Extract pricing scenario
    cenario_recomendado = pricing_data.get("cenario_recomendado", "moderado")
    cenarios = pricing_data.get("cenarios", [])
    cenario = None
    for c in cenarios:
        if c.get("tipo") == cenario_recomendado:
            cenario = c
            break
    if not cenario and cenarios:
        cenario = cenarios[0]
    if not cenario:
        elements.append(Paragraph("<i>[Nenhum cenario disponivel]</i>", styles["body"]))
        return elements

    mdo = cenario.get("custo_mao_de_obra", {})

    def _money(val):
        """Format a value as R$ string."""
        if val is None:
            return "R$ 0,00"
        try:
            v = float(val)
            int_part = int(v)
            dec_part = round((v - int_part) * 100)
            int_str = f"{int_part:,}".replace(",", ".")
            return f"R$ {int_str},{dec_part:02d}"
        except (ValueError, TypeError):
            return f"R$ {val}"

    def _cost_section(title: str, rows: list, total_label: str = "", total_val: str = "") -> list:
        elems = [Paragraph(title, styles["section_title"])]
        data = []
        for label, val in rows:
            formatted = val if isinstance(val, str) and val.endswith("%") else _money(val)
            data.append([label, formatted])
        if total_label:
            data.append([f"<b>{total_label}</b>", f"<b>{_money(total_val)}</b>"])

        table_data = []
        for row in data:
            table_data.append(
                [
                    Paragraph(row[0], styles["table_cell"]),
                    Paragraph(row[1], styles["table_cell_right"]),
                ]
            )

        t = Table(table_data, colWidths=[12 * cm, 5 * cm])
        style_cmds = [
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
            (
                "ROWBACKGROUNDS",
                (0, 0),
                (-1, -2),
                [colors.white, colors.HexColor("#f8f8f8")],
            ),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]
        if total_label:
            style_cmds.append(("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8e8e8")))
            style_cmds.append(("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"))
        t.setStyle(TableStyle(style_cmds))
        elems.append(t)
        return elems

    # 1. Mao de obra
    elements.extend(
        _cost_section(
            "1. MAO DE OBRA - REMUNERACAO",
            [
                ("1.1 Salario Base", mdo.get("salario_base", "0.00")),
                (
                    "1.2 Adicional Periculosidade (30%)",
                    mdo.get("adicional_periculosidade", "0.00"),
                ),
                (
                    "1.3 Adicional Noturno (20%)",
                    mdo.get("adicional_noturno", "0.00"),
                ),
                (
                    "1.4 Adicional Insalubridade",
                    mdo.get("adicional_insalubridade", "0.00"),
                ),
                ("1.5 Horas Extras", mdo.get("horas_extras", "0.00")),
            ],
            "SUBTOTAL REMUNERACAO",
            mdo.get("total_remuneracao", "0.00"),
        )
    )
    elements.append(Spacer(1, 3 * mm))

    # 2. Encargos
    elements.extend(
        _cost_section(
            "2. ENCARGOS SOCIAIS E TRABALHISTAS",
            [
                ("2.1 INSS Patronal (20%)", mdo.get("inss_patronal", "0.00")),
                ("2.2 FGTS (8%)", mdo.get("fgts", "0.00")),
                (
                    "2.3 Terceiros/Sistema S (5,8%)",
                    mdo.get("terceiros_sistema_s", "0.00"),
                ),
                (
                    "2.4 Provisao Ferias (12,1%)",
                    mdo.get("provisao_ferias", "0.00"),
                ),
                (
                    "2.5 Provisao 13o Salario (8,93%)",
                    mdo.get("provisao_13o", "0.00"),
                ),
                (
                    "2.6 Provisao Rescisao (5,2%)",
                    mdo.get("provisao_rescisao", "0.00"),
                ),
            ],
            "TOTAL ENCARGOS",
            mdo.get("total_encargos", "0.00"),
        )
    )
    elements.append(Spacer(1, 3 * mm))

    # 3. Beneficios
    elements.extend(
        _cost_section(
            "3. BENEFICIOS",
            [
                ("3.1 Vale Transporte", mdo.get("vale_transporte", "0.00")),
                ("3.2 Vale Alimentacao", mdo.get("vale_alimentacao", "0.00")),
                (
                    "3.3 Assistencia Medica",
                    mdo.get("assistencia_medica", "0.00"),
                ),
                ("3.4 Seguro de Vida", mdo.get("seguro_vida", "0.00")),
                ("3.5 Uniforme/EPI", mdo.get("uniforme_epi", "0.00")),
            ],
            "SUBTOTAL BENEFICIOS",
            mdo.get("total_beneficios", "0.00"),
        )
    )
    elements.append(Spacer(1, 3 * mm))

    # 4. Total mao de obra
    elements.extend(
        _cost_section(
            "4. CUSTO TOTAL MAO DE OBRA",
            [
                (
                    "Qtd. Profissionais",
                    str(mdo.get("quantidade_profissionais", 0)),
                ),
                (
                    "Custo Unitario/Mes",
                    mdo.get("custo_mensal_unitario", "0.00"),
                ),
            ],
            "TOTAL MAO DE OBRA/MES",
            mdo.get("custo_mensal_total", "0.00"),
        )
    )
    elements.append(Spacer(1, 3 * mm))

    # 5. Custos indiretos
    elements.extend(
        _cost_section(
            "5. CUSTOS INDIRETOS",
            [],
            "TOTAL CUSTOS INDIRETOS",
            cenario.get("custos_indiretos", "0.00"),
        )
    )
    elements.append(Spacer(1, 3 * mm))

    # 6. Custo total direto
    elements.extend(
        _cost_section(
            "6. CUSTO TOTAL DIRETO",
            [],
            "CUSTO TOTAL DIRETO",
            cenario.get("custo_total_direto", "0.00"),
        )
    )
    elements.append(Spacer(1, 3 * mm))

    # 7. BDI
    bdi_pct = cenario.get("bdi_percentual", "0")
    margem_pct = cenario.get("margem_lucro_percentual", "0")
    elements.extend(
        _cost_section(
            "7. BDI - BENEFICIOS E DESPESAS INDIRETAS",
            [
                ("7.1 Administracao Central", "6,00%"),
                ("7.2 Seguro/Garantia", "1,00%"),
                ("7.3 Risco", "1,50%"),
                ("7.4 Despesas Financeiras", "0,80%"),
                ("7.5 Margem de Lucro", f"{margem_pct}%"),
                ("7.6 Tributos", "(ver item 8)"),
            ],
            f"BDI TOTAL ({bdi_pct}%)",
            cenario.get("valor_bdi", "0.00"),
        )
    )
    elements.append(Spacer(1, 3 * mm))

    # 8. Impostos
    impostos = cenario.get("impostos_detalhamento", {})
    imp_rows = [(nome.upper().replace("_", " "), f"{val}%") for nome, val in impostos.items()]
    elements.extend(
        _cost_section(
            "8. IMPOSTOS E TRIBUTOS",
            imp_rows,
            "TOTAL IMPOSTOS",
            cenario.get("total_impostos", "0.00"),
        )
    )
    elements.append(Spacer(1, 3 * mm))

    # 9. Lucro
    elements.extend(
        _cost_section(
            "9. LUCRO",
            [
                (
                    f"Margem de Lucro ({margem_pct}%)",
                    cenario.get("valor_lucro", "0.00"),
                )
            ],
        )
    )
    elements.append(Spacer(1, 3 * mm))

    # 10. RESUMO — highlighted
    prazo = pricing_data.get("prazo_contrato_meses", variaveis.get("prazo_contrato", 12))
    elements.append(Paragraph("10. RESUMO GERAL", styles["section_title"]))
    resumo_data = [
        [
            Paragraph("<b>Descricao</b>", styles["table_header"]),
            Paragraph("<b>Valor</b>", styles["table_header"]),
        ],
        [
            Paragraph("PRECO MENSAL", styles["table_cell_bold"]),
            Paragraph(_money(cenario.get("preco_mensal", "0.00")), styles["table_total"]),
        ],
        [
            Paragraph("PRECO ANUAL", styles["table_cell_bold"]),
            Paragraph(_money(cenario.get("preco_anual", "0.00")), styles["table_total"]),
        ],
        [
            Paragraph(f"PRECO TOTAL CONTRATO ({prazo} meses)", styles["table_cell_bold"]),
            Paragraph(
                _money(cenario.get("preco_total_contrato", "0.00")),
                styles["table_total"],
            ),
        ],
    ]
    resumo_table = Table(resumo_data, colWidths=[12 * cm, 5 * cm])
    resumo_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _HEADER_COLOR),
                ("BACKGROUND", (0, -1), (-1, -1), B.LARANJA),
                ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -2),
                    [colors.white, colors.HexColor("#f5f5f5")],
                ),
            ]
        )
    )
    elements.append(resumo_table)

    # Signature
    elements.extend(_build_signature_block(styles, variaveis))

    return elements


def _render_declaracao(content: str, variaveis: dict, styles: dict, titulo: str) -> list:
    """Builds flowable elements for a generic declaration document.

    Parses the text content from the CompilerAgent into paragraphs and renders
    them with professional formatting. Works for all declaration types.
    """
    elements = []
    elements.extend(_build_doc_title(styles, titulo.upper()))
    elements.extend(
        _build_ref_block(
            styles,
            variaveis.get("orgao", ""),
            variaveis.get("modalidade", ""),
            variaveis.get("numero_edital", ""),
        )
    )

    # Parse content into paragraphs - skip header lines already rendered
    lines = content.strip().split("\n")

    skip_until_body = True
    body_lines = []
    for line in lines:
        stripped = line.strip()
        if skip_until_body:
            if stripped.startswith("A empresa") or stripped.startswith("DECLARA"):
                skip_until_body = False
                body_lines.append(stripped)
            continue
        body_lines.append(stripped)

    # Reconstruct paragraphs (blank line = paragraph break)
    current_para = []
    for line in body_lines:
        if line.startswith("___"):
            break
        if line.startswith("Manaus-AM,"):
            break

        if line == "":
            if current_para:
                text = " ".join(current_para)
                elements.append(Paragraph(text, styles["body"]))
                current_para = []
        else:
            current_para.append(line)

    if current_para:
        text = " ".join(current_para)
        elements.append(Paragraph(text, styles["body"]))

    # Signature
    elements.extend(_build_signature_block(styles, variaveis))

    return elements


def _render_checklist(content: str, variaveis: dict, styles: dict) -> list:
    """Renders checklist de habilitacao as PDF with checkbox-style items."""
    elements = []
    elements.extend(_build_doc_title(styles, "CHECKLIST DE DOCUMENTOS PARA HABILITACAO"))

    info_text = (
        f"Empresa: <b>{variaveis.get('razao_social', '')}</b><br/>"
        f"CNPJ: {variaveis.get('cnpj', '')}<br/>"
        f"Edital: {variaveis.get('numero_edital', '[N/A]')}<br/>"
        f"Orgao: {variaveis.get('orgao', '[N/A]')}<br/>"
        f"Data de Verificacao: {datetime.utcnow().strftime('%d/%m/%Y')}"
    )
    elements.append(Paragraph(info_text, styles["body"]))
    elements.append(Spacer(1, 5 * mm))

    lines = content.strip().split("\n")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("CHECKLIST DE DOCUMENTOS"):
            continue
        if stripped.startswith("====="):
            continue
        if stripped.startswith("Empresa:") or stripped.startswith("CNPJ:"):
            continue
        if stripped.startswith("Edital:"):
            continue
        if stripped.startswith("Orgao:") or stripped.startswith("Data de Verificacao:"):
            continue
        if stripped.startswith("-----"):
            continue

        if stripped.isupper() and not stripped.startswith("["):
            elements.append(Paragraph(stripped, styles["section_title"]))
        elif stripped.startswith("[ ]"):
            item_text = stripped[3:].strip()
            elements.append(Paragraph(f"\u2610  {item_text}", styles["body"]))
        elif stripped.startswith("- "):
            elements.append(Paragraph(f"\u2022  {stripped[2:]}", styles["small"]))
        elif stripped.startswith("___"):
            elements.append(Spacer(1, 10 * mm))
            elements.append(Paragraph("___________________________________", styles["body_center"]))
        else:
            elements.append(Paragraph(stripped, styles["body"]))

    return elements


def _render_raw_text(content: str, styles: dict, titulo: str) -> list:
    """Fallback renderer: wraps raw text content into PDF paragraphs."""
    elements = []
    elements.extend(_build_doc_title(styles, titulo.upper()))

    for line in content.strip().split("\n"):
        stripped = line.strip()
        if not stripped:
            elements.append(Spacer(1, 3 * mm))
        elif stripped.startswith("===") or stripped.startswith("---"):
            elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
        else:
            elements.append(Paragraph(stripped, styles["body"]))

    return elements


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────


def render_pdf(
    document_content: str,
    document_type: str,
    variaveis: dict | None = None,
    pricing_data: dict | None = None,
    titulo: str = "Documento",
) -> bytes:
    """
    Renders a document generated by CompilerAgent into PDF bytes.

    Args:
        document_content: The text content from DocumentoGerado.conteudo.
        document_type: The TipoDocumento value (e.g. 'carta_proposta').
        variaveis: Dict of variables used in the document
            (from DocumentoGerado.variaveis_preenchidas).
        pricing_data: Pricing data dict (needed for planilha_custos rendering).
        titulo: Document title for the PDF metadata.

    Returns:
        PDF file contents as bytes.
    """
    if variaveis is None:
        variaveis = {}

    styles = _build_styles()
    buffer = io.BytesIO()
    doc = _create_doc_template(buffer, title=titulo)

    if document_type == "carta_proposta":
        elements = _render_carta_proposta(document_content, variaveis, styles)
        header_titulo = "CARTA PROPOSTA"
    elif document_type == "planilha_custos":
        elements = _render_planilha_custos(document_content, variaveis, styles, pricing_data)
        header_titulo = "PLANILHA DE CUSTOS"
    elif document_type.startswith("declaracao_"):
        elements = _render_declaracao(document_content, variaveis, styles, titulo)
        header_titulo = "DECLARACAO"
    elif document_type == "checklist_habilitacao":
        elements = _render_checklist(document_content, variaveis, styles)
        header_titulo = "HABILITACAO"
    else:
        elements = _render_raw_text(document_content, styles, titulo)
        header_titulo = "LICITACAO"

    doc.build(
        elements,
        onFirstPage=lambda c, d: B.header_footer(c, d, titulo=header_titulo),
        onLaterPages=lambda c, d: B.header_footer(c, d, titulo=header_titulo),
    )
    return buffer.getvalue()


def save_pdf(
    pdf_bytes: bytes,
    filename: str,
    subdirectory: str = "",
) -> str:
    """
    Saves PDF bytes to the proposals directory.

    Args:
        pdf_bytes: The raw PDF content.
        filename: Filename (e.g. 'carta_proposta_edital_001.pdf').
        subdirectory: Optional subdirectory inside the proposals folder.

    Returns:
        Absolute path to the saved file.
    """
    target_dir = PDF_OUTPUT_DIR
    if subdirectory:
        target_dir = target_dir / subdirectory

    target_dir.mkdir(parents=True, exist_ok=True)

    filepath = target_dir / filename
    filepath.write_bytes(pdf_bytes)
    logger.info(f"PDF salvo: {filepath} ({len(pdf_bytes)} bytes)")
    return str(filepath)
