"""Férias completas como no DGX (U2, 24/09/2026): aviso (individual e em lote), recibo timbrado, conta a
pagar e cobertura do posto — em cima do que já existe, sem recalcular nada.

Onde cada coisa mora (cavado):
- Férias: `hr_vacation_requests` (fonte canônica; status EN). Ganha aqui `payable_id`, `cobertura_id` e
  `aviso_gerado_em` (ADD COLUMN IF NOT EXISTS em `ensure`).
- Cálculo: EXATAMENTE o da calculadora `ferias-calc` (`redesign_data_controller.rd_action_ferias_calc`):
  `clt_calculator.calcular_ferias` + INSS/IRRF sobre férias + 1/3 (abono isento). `calcular()` repete
  a mesma sequência com os dias/abono gravados na férias — o oráculo compara os dois líquidos (Δ = 0).
  13º adiantado (`advance_13th`) é só um SIM/NÃO no papel: a calculadora não o apura e nada é inventado.
- Aviso: o layout é o de `vacation_controller.gerar_aviso_previo_ferias` (art. 135 CLT), extraído para
  `story_aviso` — o endpoint individual e o lote montam a MESMA página; o lote só põe PageBreak entre elas.
- Recibo: `pdf_branding` (padrão-ouro), empregador por CPF×competência como o holerite; só o
  funcionário assina (mesma decisão de 21/08 para holerite/recibo).
- Conta: `PayableService.create_account` (o mesmo da tela «Registrar conta» e do T4), condomínio da
  empresa, vencimento = início − 2 dias corridos (art. 145 CLT; se já passou, hoje), favorecido = o
  colaborador (nome; PIX vai nas notas). Idempotente por `payable_id`. NÃO paga: pagamento é o fluxo
  gated do Financeiro.
- Cobertura: `cobertura_service.registrar(motivo="ferias")` (F8) — que já cria a movimentação
  `cobertura_de_ferias` da F5. Idempotente por `cobertura_id`.
"""

from __future__ import annotations

import hashlib
import io
import os
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import text

DDL = (
    "ALTER TABLE hr_vacation_requests ADD COLUMN IF NOT EXISTS payable_id uuid",
    "ALTER TABLE hr_vacation_requests ADD COLUMN IF NOT EXISTS cobertura_id uuid",
    "ALTER TABLE hr_vacation_requests ADD COLUMN IF NOT EXISTS aviso_gerado_em timestamptz",
)
_ensured = False  # ponytail: DDL idempotente uma vez por processo — ALTER TABLE pega lock mesmo sem mudar nada
TIPO_AVISO = "aviso_ferias"
DIAS_ANTES_PAGAMENTO = 2  # art. 145 CLT: pagamento até 2 dias antes do início — dias CORRIDOS (a lei não diz úteis)

SQL_FERIAS = """
SELECT h.id::text, h.employee_id::text, e.nome, e.cpf, coalesce(e.cargo,''), e.data_admissao, e.salario_base,
       e.pix_key, e.matricula, h.status, h.request_code, h.start_date, h.end_date, h.return_date,
       h.days_requested, coalesce(h.sell_days,0), coalesce(h.advance_13th,false), h.payable_id::text,
       h.cobertura_id::text, h.aviso_gerado_em, p.start_date, p.end_date, e.cliente_nome, e.posto_atual_nome, h.hr_notes
FROM hr_vacation_requests h JOIN employees e ON e.id = h.employee_id
LEFT JOIN hr_vacation_periods p ON p.id = h.period_id
"""


class FeriasErro(ValueError):  # noqa: N818 — nome em PT-BR, padrão da casa
    def __init__(self, status: int, msg: str) -> None:
        super().__init__(msg)
        self.status = status


async def ensure(db) -> None:
    global _ensured
    if _ensured:
        return
    for s in DDL:
        await db.execute(text(s))
    await db.commit()
    _ensured = True


def _br(d) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def _row(r) -> dict:
    ini, fim = r[11], r[12]
    if r[20] and r[21]:
        aq_ini, aq_fim = r[20], r[21]
    elif ini:  # mesma derivação do aviso individual de hoje (sem período ligado)
        aq_fim = ini - timedelta(days=1)
        aq_ini = aq_fim.replace(year=aq_fim.year - 1) + timedelta(days=1)
    else:
        aq_ini = aq_fim = None
    return {
        "id": r[0],
        "employee_id": r[1],
        "nome": r[2],
        "cpf": r[3],
        "cargo": r[4] or "Agente de Segurança",
        "admissao": r[5],
        "salario_base": Decimal(str(r[6] or 0)),
        "pix_key": r[7],
        "matricula": r[8],
        "status": (r[9] or "").upper(),
        "request_code": r[10],
        "inicio": ini,
        "fim": fim,
        # retorno = dia seguinte ao fim (como o aviso individual sempre fez); `return_date` do banco vem igual ao fim
        # nas férias sincronizadas do Sólides (medido em EIDY, 09/2026) — não é confiável para o papel
        "retorno": fim + timedelta(days=1) if fim else None,
        "dias": int(r[14] or ((fim - ini).days + 1 if ini and fim else 30)),
        "abono_dias": int(r[15] or 0),
        "adiantamento_13": bool(r[16]),
        "payable_id": r[17],
        "cobertura_id": r[18],
        "aviso_gerado_em": r[19],
        "aquisitivo_ini": aq_ini,
        "aquisitivo_fim": aq_fim,
        "cliente": r[22],
        "posto_nome": r[23],
        "hr_notes": r[24],
    }


async def carregar(db, vid: str) -> dict:
    r = (await db.execute(text(SQL_FERIAS + " WHERE h.id::text = :v"), {"v": str(vid)})).fetchone()
    if not r:
        raise FeriasErro(404, "Férias não encontrada.")
    return _row(r)


async def ids_do_mes(db, mes: str, cliente: str | None = None, cargo: str | None = None) -> list[str]:
    """Férias APROVADAS com início no mês `AAAA-MM`, filtro opcional por cliente/cargo do colaborador."""
    sql = "SELECT h.id::text FROM hr_vacation_requests h JOIN employees e ON e.id = h.employee_id WHERE h.status = 'APPROVED' AND to_char(h.start_date,'YYYY-MM') = :m"
    p: dict = {"m": mes}
    if cliente:
        sql += " AND e.cliente_nome = :c"
        p["c"] = cliente
    if cargo:
        sql += " AND e.cargo = :g"
        p["g"] = cargo
    return [x[0] for x in (await db.execute(text(sql + " ORDER BY e.nome"), p)).fetchall()]


# ----------------------------------------------------------------------------- cálculo
def calcular(f: dict) -> dict:
    """A MESMA sequência de `rd_action_ferias_calc` (calculadora ferias-calc), com os dias/abono da férias."""
    from modules.people_management.common.utils.clt_calculator import calcular_ferias, calcular_inss, calcular_irrf

    if f["salario_base"] <= 0:
        raise FeriasErro(422, f"{f['nome']} está sem salário base cadastrado — o recibo não inventa valor.")
    dias = min(max(f["dias"], 1), 30)
    abono = min(max(f["abono_dias"], 0), 10)
    r = calcular_ferias(f["salario_base"], dias, abono)
    base = r["valor_ferias"] + r["terco_constitucional"]  # abono pecuniário é isento
    inss = calcular_inss(base)
    irrf = calcular_irrf(base - inss)
    return {
        **f,
        "dias": dias,
        "abono_dias": abono,
        "valor_ferias": r["valor_ferias"],
        "terco": r["terco_constitucional"],
        "abono_valor": r["abono_pecuniario"],
        "terco_abono": r["terco_abono"],
        "total_bruto": r["total_bruto"],
        "inss": inss,
        "irrf": irrf,
        "liquido": r["total_bruto"] - inss - irrf,
        "pagar_ate": f["inicio"] - timedelta(days=DIAS_ANTES_PAGAMENTO) if f["inicio"] else None,
    }


async def calcular_id(db, vid: str) -> dict:
    return calcular(await carregar(db, vid))


# ----------------------------------------------------------------------------- aviso (art. 135)
def story_aviso(d: dict, st: dict) -> list:
    """Página do AVISO DE FÉRIAS — usada pelo endpoint individual (`vacation_controller`) e pelo lote.
    `d`: employee_name, cargo, admission_date, period_start, period_end, vacation_start, vacation_end,
    vacation_days, return_date, notice_date (strings já formatadas); opcionais abono_dias (int),
    adiantamento_13 (bool)."""
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    from modules.crm.services import pdf_branding as B  # noqa: N812

    body, cell = st["corpo"], st["cell"]
    linhas = [
        [Paragraph(f"<b>Empregado(a):</b> {d['employee_name']}", cell)],
        [Paragraph(f"<b>Cargo:</b> {d['cargo']}", cell)],
        [Paragraph(f"<b>Data de Admissão:</b> {d['admission_date']}", cell)],
        [Paragraph(f"<b>Período Aquisitivo:</b> {d['period_start']} a {d['period_end']}", cell)],
    ]
    if d.get("abono_dias") is not None:
        linhas.append(
            [
                Paragraph(
                    f"<b>Abono pecuniário (art. 143):</b> {d['abono_dias']} dia(s)"
                    if d["abono_dias"]
                    else "<b>Abono pecuniário (art. 143):</b> não",
                    cell,
                )
            ]
        )
    if d.get("adiantamento_13") is not None:
        linhas.append([Paragraph(f"<b>Adiantamento do 13º:</b> {'sim' if d['adiantamento_13'] else 'não'}", cell)])
    box = Table(linhas, colWidths=[178 * mm])
    box.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, B.AZUL_ESCURO),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E1F2")),
                ("BACKGROUND", (0, 0), (-1, -1), B.FUNDO_CLARO),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story = [*B.secao("DADOS DO EMPREGADO", st), box, Spacer(1, 5 * mm), *B.secao("COMUNICADO", st)]
    story.append(Paragraph(f"Prezado(a) <b>{d['employee_name']}</b>,", body))
    story.append(
        Paragraph(
            f"Comunicamos que suas férias estão programadas para o período de <b>{d['vacation_start']}</b> a "
            f"<b>{d['vacation_end']}</b> ({d['vacation_days']} dias), conforme artigo 135 da CLT e CCT SINDECOMPRESTS 2026.",
            body,
        )
    )
    story.append(
        Paragraph(
            "O pagamento das férias será efetuado com antecedência mínima de 2 (dois) dias, conforme determina o artigo 145 da CLT.",
            body,
        )
    )
    story.append(Paragraph(f"Retorno previsto: <b>{d['return_date']}</b>.", body))
    story += B.campos_assinatura(
        st,
        funcionario_nome=d["employee_name"],
        data_str=d["notice_date"],
        digital_funcionario=True,
        digital_empresa=True,
        data_empresa=d["notice_date"],
        espaco_antes=14,
    )
    return story


def _dados_aviso(f: dict) -> dict:
    return {
        "employee_name": f["nome"],
        "cargo": f["cargo"],
        "admission_date": _br(f["admissao"]) if f["admissao"] else "Não informada",
        "period_start": _br(f["aquisitivo_ini"]),
        "period_end": _br(f["aquisitivo_fim"]),
        "vacation_start": _br(f["inicio"]),
        "vacation_end": _br(f["fim"]),
        "vacation_days": str(f["dias"]),
        "return_date": _br(f["retorno"]),
        "notice_date": date.today().strftime("%d/%m/%Y"),
        "abono_dias": f["abono_dias"],
        "adiantamento_13": f["adiantamento_13"],
    }


def _doc(buf, top_mm=40):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate

    return SimpleDocTemplate(
        buf, pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=top_mm * mm, bottomMargin=16 * mm
    )


def _build(story: list, titulo: str, empresa: dict | None = None) -> bytes:
    from modules.crm.services import pdf_branding as B  # noqa: N812

    buf = io.BytesIO()
    hf = lambda cv, dc: B.header_footer(cv, dc, titulo=titulo, empresa=empresa)  # noqa: E731
    _doc(buf).build(story, onFirstPage=hf, onLaterPages=hf)
    return buf.getvalue()


async def pdf_aviso(db, vid: str) -> bytes:
    """Aviso de UMA pessoa, com o empregador dela (CPF × competência), como o holerite."""
    from modules.crm.services import pdf_branding as B  # noqa: N812

    f = await carregar(db, vid)
    empresa = B.empresa_branding_por_cpf(f["cpf"], f["inicio"].strftime("%Y-%m") if f["inicio"] else None)
    return _build(story_aviso(_dados_aviso(f), B.styles()), "AVISO DE FÉRIAS", empresa)


async def pdf_aviso_lote(db, ids: list[str]) -> bytes:
    """UM PDF, uma página por pessoa — cada página com o empregador da pessoa (o lote pode misturar CNPJs,
    por isso são PDFs individuais emendados, não um story só)."""
    if not ids:
        raise FeriasErro(400, "Nenhuma férias aprovada no filtro — não há aviso a gerar.")
    partes = [await pdf_aviso(db, vid) for vid in ids]
    if len(partes) == 1:
        return partes[0]
    import fitz  # PyMuPDF — já na imagem (o kit GEDEON emenda PDFs com ele)

    saida = fitz.open()
    for pdf in partes:
        with fitz.open(stream=pdf, filetype="pdf") as d:
            saida.insert_pdf(d)
    return saida.tobytes()


async def enfileirar_aviso(db, vid: str, pdf: bytes, user_id=None) -> dict | None:
    """Grava o PDF individual (a assinatura estampa o selo SOBRE ele) e abre o pedido de assinatura do
    funcionário — mesmo helper do holerite; idempotente por (aviso_ferias, id da férias)."""
    from modules.signatures.helpers.solicitar_assinatura_documento import garantir_solicitacao_assinatura

    f = await carregar(db, vid)
    pasta = os.path.join(os.getenv("UPLOADS_DIR", "/app/uploads"), "ferias")
    os.makedirs(pasta, exist_ok=True)
    path = os.path.join(pasta, f"aviso_{vid}.pdf")
    with open(path, "wb") as fh:
        fh.write(pdf)
    r = await garantir_solicitacao_assinatura(
        db,
        document_type=TIPO_AVISO,
        document_id=vid,
        title=f"Aviso de férias {_br(f['inicio'])} — {f['nome']}",
        document_path=path,
        document_hash=hashlib.sha256(pdf).hexdigest(),
        employee_id=f["employee_id"],
        employee_name=f["nome"],
        employee_document=f["cpf"],
        requested_by=user_id,
    )
    await db.execute(text("UPDATE hr_vacation_requests SET aviso_gerado_em = now() WHERE id::text = :v"), {"v": vid})
    await db.commit()
    return r


# ----------------------------------------------------------------------------- recibo
async def pdf_recibo(db, vid: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    from modules.crm.services import pdf_branding as B  # noqa: N812

    c = calcular(await carregar(db, vid))
    if c["status"] != "APPROVED":
        raise FeriasErro(409, "Recibo só de férias APROVADA.")
    comp = c["inicio"].strftime("%Y-%m") if c["inicio"] else None
    empresa = B.empresa_branding_por_cpf(c["cpf"], comp)
    st = B.styles()
    cell, cellr, cellh, body = st["cell"], st["cellr"], st["cellh"], st["corpo"]
    W = 178 * mm

    def caixa(pares):
        tb = Table(
            [[Paragraph(f"<b>{k}:</b> {v}", cell) for k, v in pares[i : i + 2]] for i in range(0, len(pares), 2)],
            colWidths=[W / 2, W / 2],
        )
        tb.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.6, B.AZUL_ESCURO),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E1F2")),
                    ("BACKGROUND", (0, 0), (-1, -1), B.FUNDO_CLARO),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return tb

    story = [
        *B.secao("DADOS DO EMPREGADO", st),
        caixa(
            [
                ("Empregado(a)", c["nome"]),
                ("CPF", c["cpf"] or "—"),
                ("Matrícula", c["matricula"] or "—"),
                ("Cargo", c["cargo"]),
                ("Admissão", _br(c["admissao"])),
                ("Salário base", B.brl(c["salario_base"])),
            ]
        ),
        Spacer(1, 4 * mm),
        *B.secao("FÉRIAS", st),
        caixa(
            [
                ("Período aquisitivo", f"{_br(c['aquisitivo_ini'])} a {_br(c['aquisitivo_fim'])}"),
                ("Gozo", f"{_br(c['inicio'])} a {_br(c['fim'])} ({c['dias']} dias)"),
                ("Retorno", _br(c["retorno"])),
                ("Abono pecuniário", f"{c['abono_dias']} dia(s)" if c["abono_dias"] else "não"),
                ("Adiantamento do 13º", "sim (apurado na folha)" if c["adiantamento_13"] else "não"),
                ("Pagamento até (art. 145)", _br(c["pagar_ate"])),
            ]
        ),
        Spacer(1, 4 * mm),
        *B.secao("DEMONSTRATIVO", st),
    ]

    linhas = [
        [
            Paragraph("Descrição", cellh),
            Paragraph("Referência", cellh),
            Paragraph("Proventos", cellh),
            Paragraph("Descontos", cellh),
        ]
    ]

    def ln(desc, ref, prov=None, desc_v=None):
        linhas.append(
            [
                Paragraph(desc, cell),
                Paragraph(ref, cellr),
                Paragraph(B.brl(prov) if prov is not None else "", cellr),
                Paragraph(B.brl(desc_v) if desc_v is not None else "", cellr),
            ]
        )

    ln("Férias", f"{c['dias']} dias", c["valor_ferias"])
    ln("1/3 constitucional sobre férias", "33,33%", c["terco"])
    if c["abono_dias"]:
        ln("Abono pecuniário (art. 143 CLT)", f"{c['abono_dias']} dias", c["abono_valor"])
        ln("1/3 sobre abono", "33,33%", c["terco_abono"])
    ln("INSS sobre férias + 1/3", "tabela 2026", None, c["inss"])
    ln("IRRF sobre férias + 1/3", "tabela 2026", None, c["irrf"])
    linhas.append(
        [
            Paragraph("<b>Totais</b>", cell),
            Paragraph("", cellr),
            Paragraph(f"<b>{B.brl(c['total_bruto'])}</b>", cellr),
            Paragraph(f"<b>{B.brl(c['inss'] + c['irrf'])}</b>", cellr),
        ]
    )
    linhas.append(
        [
            Paragraph("<b>LÍQUIDO A RECEBER</b>", cell),
            Paragraph("", cellr),
            Paragraph("", cellr),
            Paragraph(f"<b>{B.brl(c['liquido'])}</b>", cellr),
        ]
    )
    tb = Table(linhas, colWidths=[W * 0.46, W * 0.18, W * 0.18, W * 0.18])
    tb.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), B.AZUL_ESCURO),
                ("BOX", (0, 0), (-1, -1), 0.6, B.AZUL_ESCURO),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D9E1F2")),
                ("BACKGROUND", (0, -2), (-1, -1), B.FUNDO_CLARO),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story += [tb, Spacer(1, 5 * mm)]
    story.append(
        Paragraph(
            f"Recebi de <b>{empresa.get('razao') or empresa.get('nome') or 'CONECTAMAIS ELETRONICA LTDA'}</b> a importância líquida de "
            f"<b>{B.brl(c['liquido'])}</b> referente às férias do período aquisitivo acima, com gozo de {_br(c['inicio'])} a "
            f"{_br(c['fim'])}, conforme artigos 129 a 145 da CLT. Os valores são os mesmos da calculadora de férias do "
            f"Conecta PRO (rubricas de férias e 1/3 seguem a folha da competência).",
            body,
        )
    )
    story += B.campos_assinatura(
        st,
        funcionario_nome=c["nome"],
        funcionario_cpf=c["cpf"],
        incluir_empresa=False,
        data_str=date.today().strftime("%d/%m/%Y"),
        digital_funcionario=True,
        espaco_antes=10,
    )
    return _build(story, "RECIBO DE FÉRIAS", empresa)


# ----------------------------------------------------------------------------- conta a pagar (art. 145)
async def gerar_conta(db, vid: str, user_id) -> dict:
    import modules.clients.models.condominium  # noqa: F401 — o mapper de PayableAccount referencia `condominiums`; fora do app (oráculo/script) ninguém o carrega
    from modules.financial.schemas.payable import PayableAccountCreate
    from modules.financial.services.contas_fixas import COND_EMPRESA
    from modules.financial.services.payable_service import PayableService

    await ensure(db)
    c = calcular(await carregar(db, vid))
    if c["payable_id"]:
        raise FeriasErro(409, f"Esta férias já tem conta a pagar ({c['payable_id'][:8]}…) — uma conta por férias.")
    if c["status"] != "APPROVED":
        raise FeriasErro(409, "Só férias APROVADA gera conta a pagar.")
    venc = c["pagar_ate"]
    if venc < date.today():
        venc = date.today()  # o prazo legal já passou: vence hoje, e o papel diz qual era o prazo
    conta = await PayableService(db).create_account(
        PayableAccountCreate(
            condominio_id=COND_EMPRESA,
            description=f"Férias {c['nome']} — {_br(c['inicio'])} a {_br(c['fim'])} ({c['dias']}d)"[:500],
            document_number=(c["request_code"] or vid)[:50],
            gross_value=c["liquido"],
            due_date=venc,
            competence_date=c["inicio"].replace(day=1),
            supplier_name=c["nome"][:200],
            notes=(
                f"Férias {c['request_code']} · líquido da calculadora CLT (férias {B_brl(c['valor_ferias'])} + 1/3 {B_brl(c['terco'])}"
                f"{f' + abono {B_brl(c["abono_valor"])} + 1/3 {B_brl(c["terco_abono"])}' if c['abono_dias'] else ''} − INSS {B_brl(c['inss'])} − IRRF {B_brl(c['irrf'])})"
                f" · pagar até {_br(c['pagar_ate'])} (art. 145 CLT) · PIX {c['pix_key'] or 'sem chave cadastrada'}"
                f" · gerada pela tela Férias → Gerar conta. NÃO PAGA: o pagamento segue o fluxo do Financeiro."
                + (f" · {c['hr_notes']}" if c.get("hr_notes") else "")
            ),
        ),
        user_id,
    )
    pid = str(conta.id)
    await db.execute(
        text("UPDATE hr_vacation_requests SET payable_id = CAST(:p AS uuid), updated_at = now() WHERE id::text = :v"),
        {"p": pid, "v": vid},
    )
    await db.commit()
    return {"payable_id": pid, "valor": c["liquido"], "vencimento": venc, "nome": c["nome"], "pix": c["pix_key"]}


def B_brl(v) -> str:  # noqa: N802 — alias curto para as notas da conta
    from modules.crm.services.pdf_branding import brl

    return brl(v)


# ----------------------------------------------------------------------------- cobertura (F8 → F5)
async def postos_do_periodo(db, employee_id: str, ini: date, fim: date) -> list[tuple[str, str]]:
    """Postos onde o coberto tem turno no período (o que fica descoberto); senão o posto atual do cadastro."""
    rows = (
        await db.execute(
            text(
                "SELECT DISTINCT p.id::text, p.name FROM shifts s JOIN posts p ON p.id = s.post_id "
                "WHERE s.employee_id = CAST(:e AS uuid) AND s.is_active AND NOT s.is_off_day AND s.status <> 'cancelled' "
                "AND s.shift_date BETWEEN :i AND :f ORDER BY p.name"
            ),
            {"e": employee_id, "i": ini, "f": fim},
        )
    ).fetchall()
    if rows:
        return [(r[0], r[1]) for r in rows]
    r = (
        await db.execute(
            text(
                "SELECT posto_atual_id::text, posto_atual_nome FROM employees WHERE id = CAST(:e AS uuid) AND posto_atual_id IS NOT NULL"
            ),
            {"e": employee_id},
        )
    ).fetchone()
    return [(r[0], r[1] or "posto atual")] if r else []


async def registrar_cobertura(
    db, vid: str, substituto_id: str, posto_id: str | None, observacao: str | None, user_id, user_nome: str
) -> dict:
    from modules.operacional.services import cobertura_service as cs

    await ensure(db)
    f = await carregar(db, vid)
    if f["cobertura_id"]:
        raise FeriasErro(
            409, f"Esta férias já tem cobertura registrada ({f['cobertura_id'][:8]}…) — veja Operacional → Coberturas."
        )
    if f["status"] != "APPROVED":
        raise FeriasErro(409, "Cobertura só de férias APROVADA (a F5 exige férias aprovadas do coberto).")
    if not substituto_id:
        raise FeriasErro(422, "Informe o substituto.")
    if not posto_id:
        postos = await postos_do_periodo(db, f["employee_id"], f["inicio"], f["fim"])
        if not postos:
            raise FeriasErro(422, f"{f['nome']} não tem turno no período nem posto atual — informe o posto.")
        posto_id = postos[0][0]
    try:
        r = await cs.registrar(
            db,
            coberto_id=f["employee_id"],
            cobertura_id=substituto_id,
            post_id=posto_id,
            inicio=f["inicio"],
            fim=f["fim"],
            motivo="ferias",
            observacao=f"férias {f['request_code']}" + (f" · {observacao}" if observacao else ""),
            user_id=user_id,
            user_nome=user_nome,
        )
    except cs.CoberturaErro as exc:
        await db.rollback()
        raise FeriasErro(exc.status, str(exc)) from exc
    await db.execute(
        text("UPDATE hr_vacation_requests SET cobertura_id = CAST(:c AS uuid), updated_at = now() WHERE id::text = :v"),
        {"c": r["cobertura_id"], "v": vid},
    )
    await db.commit()
    return r


async def descobertos(db) -> list[dict]:
    """Férias aprovadas ainda em curso/futuras SEM cobertura registrada — o posto fica descoberto."""
    await ensure(db)
    rows = (
        await db.execute(
            text(
                SQL_FERIAS
                + " WHERE h.status = 'APPROVED' AND h.cobertura_id IS NULL AND h.end_date >= CURRENT_DATE ORDER BY h.start_date, e.nome"
            )
        )
    ).fetchall()
    out = []
    for r in rows:
        f = _row(r)
        postos = await postos_do_periodo(db, f["employee_id"], f["inicio"], f["fim"])
        out.append(
            {
                "vacation_id": f["id"],
                "nome": f["nome"],
                "inicio": f["inicio"],
                "fim": f["fim"],
                "dias": f["dias"],
                "posto": ", ".join(p[1] for p in postos) or "sem posto conhecido",
                "posto_id": postos[0][0] if postos else None,
            }
        )
    return out


# ----------------------------------------------------------------------------- ficha por pessoa
async def ficha(db, employee_id: str) -> dict:
    """Seções que o painel de resultado renderiza (`{secao: {campo: valor}}` e `[{nome, valor}]`)."""
    from modules.people_management.hr.services import mapa_ferias as mf
    from modules.people_management.hr.services.vacation_service import VacationService

    await ensure(db)
    try:
        saldo = await VacationService(db).calculate_vacation_balance(employee_id)
    except ValueError as exc:
        raise FeriasErro(404, str(exc)) from exc
    linha = next((x for x in await mf.mapa(db) if x["employee_id"] == employee_id), None)
    sec: dict = {
        "saldo": {
            "colaborador": saldo.get("employee_name"),
            "dias_de_direito": saldo.get("dias_direito"),
            "dias_gozados": saldo.get("dias_gozados"),
            "saldo_dias": saldo.get("dias_saldo"),
            **({"observacao": saldo["message"]} if saldo.get("message") else {}),
        },
        "mapa_art_133": (
            {
                "faixa": linha["faixa"],
                "ancora": _br(linha["ancora"]),
                "idade_meses": linha["idade_meses"],
                "limite_para_gozo": _br(linha["limite"]),
                "vence_em_dias": linha["dias_para_limite"],
                "vencida_dobra": "SIM" if linha["vencida"] else "não",
            }
            if linha
            else {"—": "fora do mapa (sem vínculo ativo)"}
        ),
        "periodos_aquisitivos": [
            {
                "nome": f"{_br(r[0])} a {_br(r[1])}",
                "valor": f"direito {r[2] or 0}d · gozados {r[3] or 0}d · vendidos {r[4] or 0}d · saldo {r[5] or 0}d · limite {_br(r[6])}",
            }
            for r in (
                await db.execute(
                    text(
                        "SELECT start_date, end_date, days_entitled, days_used, days_sold, days_remaining, limit_date FROM hr_vacation_periods WHERE employee_id::text = :e ORDER BY start_date"
                    ),
                    {"e": employee_id},
                )
            ).fetchall()
        ]
        or [{"nome": "—", "valor": "nenhum período aquisitivo gravado (aguardando dado)"}],
    }
    gozos = []
    for r in (
        await db.execute(
            text(SQL_FERIAS + " WHERE h.employee_id::text = :e ORDER BY h.start_date DESC"), {"e": employee_id}
        )
    ).fetchall():
        f = _row(r)
        partes = [f"{f['dias']}d · {f['status'].lower()}"]
        if f["abono_dias"]:
            partes.append(f"abono {f['abono_dias']}d")
        if f["adiantamento_13"]:
            partes.append("13º adiantado")
        partes.append(
            "aviso gerado " + f["aviso_gerado_em"].strftime("%d/%m/%Y") if f["aviso_gerado_em"] else "sem aviso gerado"
        )
        partes.append(f"conta a pagar {f['payable_id'][:8]}…" if f["payable_id"] else "sem conta a pagar")
        partes.append(f"cobertura {f['cobertura_id'][:8]}…" if f["cobertura_id"] else "sem cobertura")
        if f["status"] == "APPROVED":
            partes.append(f"recibo: /api/v1/redesign/ferias/{f['id']}/recibo/pdf")
        gozos.append({"nome": f"{_br(f['inicio'])} a {_br(f['fim'])} [{f['id'][:8]}]", "valor": " · ".join(partes)})
    sec["gozos"] = gozos or [{"nome": "—", "valor": "nenhuma férias solicitada"}]
    sec["avisos_para_assinar"] = [
        {"nome": r[0] or "aviso", "valor": f"{str(r[1]).lower()} · {r[2].strftime('%d/%m/%Y') if r[2] else '—'}"}
        for r in (
            await db.execute(
                text(
                    "SELECT title, status, created_at FROM sig_signature_requests WHERE document_type = :t AND signer_id::text = :e ORDER BY created_at DESC LIMIT 12"
                ),
                {"t": TIPO_AVISO, "e": employee_id},
            )
        ).fetchall()
    ] or [{"nome": "—", "valor": "nenhum aviso enfileirado para assinatura"}]
    return sec
