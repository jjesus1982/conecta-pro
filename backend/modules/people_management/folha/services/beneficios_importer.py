"""Relatórios de benefícios (Sólides e SINETRAM) → modalidade do VT por funcionário e conferência do kit (09/09/2026).

Regra do Jordan, 09/09/2026:
  - **Vale-refeição: todo mundo pelo Sólides** (cartão de benefícios).
  - **Vale-transporte tem DUAS modalidades**: quem tem condução própria recebe como *mobilidade* no cartão Sólides
    (usa o saldo livre para abastecer); quem pega ônibus recebe crédito na carteirinha do SINETRAM.

Sem isso o kit não fecha: o total do boleto do SINETRAM só cobre uma parte do VT, e a outra parte está dentro do
pedido do Sólides. O relatório do Sólides traz ALIMENTAÇÃO e MOBILIDADE por colaborador; o do SINETRAM traz CPF,
nome, nº do cartão e valor. Deste par sai:
    employees.vt_modalidade = 'solides' | 'sinetram'
e a conferência VT/VR do mês (o que cada portal pagou × o que a folha descontou).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal

logger = logging.getLogger(__name__)

RE_LINHA_SOLIDES = re.compile(r"^(.+?)\s+(\d{11})\s+(.+?)\s+([\d.,]+)(?:\s+([\d.,]+))?\s*$")
# o nome quebra em duas linhas ("CELIANE GARCIA DE" / "SOUSA"): casar até o nº do cartão, que tem formato fixo
RE_LINHA_SINETRAM = re.compile(r"(\d{3}\.\d{3}\.\d{3}-\d{2})\s+(.+?)\s+(\d{2}\.\d{2}\.\d{8}-\d)\s+R\$\s*([\d.,]+)")
RE_PEDIDO_SOLIDES = re.compile(r"N[úu]mero do Pedido.*?#?(\d+)", re.S)
# o "#332373" do nº do pedido vem ENTRE o rótulo e o valor no texto extraído — casar até o R$
RE_TOTAL_SOLIDES = re.compile(r"Valor Total do Pedido.*?R\$\s*([\d.,]+)", re.S)
# "Relatório de 12 colaboradores (Agosto/2026)" — a competência do pedido, no rodapé
RE_COMP_SOLIDES = re.compile(r"\((\w+)/(\d{4})\)")
MESES = {"janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
         "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}


def _dec(s: str | None) -> Decimal:
    t = (s or "0").strip().replace("R$", "").strip()
    # "6546.00" (Sólides, ponto decimal) e "1.234,56" (SINETRAM, padrão BR)
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return Decimal(t)
    except Exception:  # noqa: BLE001
        return Decimal("0")


def _dig(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def _texto(pdf_bytes: bytes) -> str:
    import io as _io

    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return "\n".join(pg.get_text("text", sort=True) for pg in doc)
    finally:
        doc.close()
        del _io


@dataclass
class LinhaBeneficio:
    cpf: str
    nome: str
    alimentacao: Decimal = Decimal("0")
    mobilidade: Decimal = Decimal("0")
    cartao: str = ""


@dataclass
class Pedido:
    origem: str  # 'solides' | 'sinetram'
    numero: str = ""
    total: Decimal = Decimal("0")
    linhas: list[LinhaBeneficio] = field(default_factory=list)
    competencia: str = ""  # 'YYYY-MM' — só o Sólides imprime; o SINETRAM vem do nome do arquivo ou do par
    arquivo: str = ""


def ler_solides(pdf_bytes: bytes) -> Pedido:
    return parse_solides_texto(_texto(pdf_bytes))


def parse_solides_texto(t: str) -> Pedido:
    """Lê o TEXTO do relatório (ou do arquivo que nós geramos — frente 03, ida e volta)."""
    p = Pedido(origem="solides")
    if (m := RE_COMP_SOLIDES.search(t)) and m.group(1).lower() in MESES:
        p.competencia = f"{m.group(2)}-{MESES[m.group(1).lower()]:02d}"
    if (m := RE_PEDIDO_SOLIDES.search(t)):
        p.numero = m.group(1)
    if (m := RE_TOTAL_SOLIDES.search(t)):
        p.total = _dec(m.group(1))
    for linha in t.splitlines():
        linha = linha.strip()
        if not linha or "CNPJ" in linha or "NOME DO COLABORADOR" in linha:
            continue
        m = RE_LINHA_SOLIDES.match(linha)
        if not m:
            continue
        nome, cpf, _emp, v1, v2 = m.groups()
        p.linhas.append(LinhaBeneficio(cpf=_dig(cpf), nome=nome.strip(), alimentacao=_dec(v1), mobilidade=_dec(v2)))
    return p


def ler_sinetram(pdf_bytes: bytes) -> Pedido:
    return parse_sinetram_texto(_texto(pdf_bytes))


def parse_sinetram_texto(t: str) -> Pedido:
    p = Pedido(origem="sinetram")
    if (m := re.search(r"Compet[êe]ncia\s*(\d{4})-(\d{2})", t)):
        p.competencia = f"{m.group(1)}-{m.group(2)}"
    if (m := re.search(r"N[ºo°]?\s*DO PEDIDO\s*(\d+)", t, re.I)):
        p.numero = m.group(1)
    if (m := re.search(r"VALOR DO PEDIDO[^\n]*?R\$\s*([\d.,]+)", t, re.I)):
        p.total = _dec(m.group(1))
    # o layout quebra a linha do colaborador; achatar antes
    flat = re.sub(r"\s*\n\s*", " ", t)
    for cpf, nome, cartao, valor in RE_LINHA_SINETRAM.findall(flat):
        # o resto do nome vem depois do valor/produto ("… SOUSA"); recompor pelo trecho seguinte é frágil,
        # então guardamos o que veio antes do cartão — o CPF é a chave de casamento, não o nome.
        p.linhas.append(LinhaBeneficio(cpf=_dig(cpf), nome=re.sub(r"\s+", " ", nome).strip(), mobilidade=_dec(valor), cartao=cartao))
    return p


def ler_pedidos_em(caminhos: list[str]) -> list[Pedido]:
    """Classifica cada PDF pelo conteúdo (o nome do arquivo mente) e devolve os pedidos lidos.

    SINETRAM não imprime competência: sai de `MM.YYYY`/`MM-YYYY` no nome do arquivo ou, na falta,
    do relatório do Sólides da MESMA pasta — ambíguo (dois Sólides na pasta) fica em branco, e
    quem chama decide. Nunca assume o mês corrente."""
    import os

    out: list[Pedido] = []
    for c in caminhos:
        try:
            with open(c, "rb") as f:
                t = _texto(f.read())
        except Exception as e:  # noqa: BLE001 — pdf estranho não derruba a leitura dos outros
            logger.warning("benefício: não li %s: %s", c, e)
            continue
        if "SINETRAM" in t.upper() or ("DO PEDIDO" in t.upper() and "CART" in t.upper()):
            p = parse_sinetram_texto(t)
        elif "Relatório de Benefícios" in t or "Sólides" in t or "Solides" in t:
            p = parse_solides_texto(t)
        else:
            continue
        if not p.linhas:
            continue
        p.arquivo = c
        if p.origem == "sinetram" and not p.competencia and (m := re.search(r"(\d{2})[._-](\d{4})", os.path.basename(c))):
            p.competencia = f"{m.group(2)}-{m.group(1)}"
        out.append(p)
    for p in out:
        if p.origem == "sinetram" and not p.competencia:
            irmaos = {q.competencia for q in out if q.origem == "solides" and q.competencia
                      and os.path.dirname(q.arquivo) == os.path.dirname(p.arquivo)}
            if len(irmaos) == 1:
                p.competencia = irmaos.pop()
    return out


async def importar_modalidade(db, solides: bytes | None = None, sinetram: bytes | None = None, aplicar: bool = False) -> dict:
    """Define a modalidade do VT de cada funcionário a partir dos dois relatórios do mês."""
    from sqlalchemy import text as sql

    rel: dict = {"solides": {}, "sinetram": {}, "mudancas": [], "sem_cadastro": [], "aplicado": aplicar}
    alvos: dict[str, str] = {}
    if solides:
        p = ler_solides(solides)
        rel["solides"] = {"pedido": p.numero, "total": float(p.total), "colaboradores": len(p.linhas),
                          "com_mobilidade": sum(1 for x in p.linhas if x.mobilidade > 0)}
        for x in p.linhas:
            if x.mobilidade > 0:
                alvos[x.cpf] = "solides"
    if sinetram:
        p = ler_sinetram(sinetram)
        rel["sinetram"] = {"pedido": p.numero, "total": float(p.total), "colaboradores": len(p.linhas)}
        for x in p.linhas:
            alvos[x.cpf] = "sinetram"
    for cpf, modalidade in alvos.items():
        row = (await db.execute(sql(
            "SELECT id::text, nome, coalesce(vt_modalidade,'') FROM employees "
            "WHERE regexp_replace(coalesce(cpf,''),'[^0-9]','','g') = :c LIMIT 1"), {"c": cpf})).first()
        if not row:
            rel["sem_cadastro"].append(f"CPF …{cpf[-4:]}")
            continue
        if row[2] != modalidade:
            rel["mudancas"].append(f"{row[1]}: {row[2] or '—'} → {modalidade}")
            if aplicar:
                await db.execute(sql("UPDATE employees SET vt_modalidade = :m, updated_at = now() WHERE id = CAST(:e AS uuid)"),
                                 {"m": modalidade, "e": row[0]})
    if aplicar:
        await db.commit()
    logger.info("benefícios: %s", {k: (len(v) if isinstance(v, list) else v) for k, v in rel.items()})
    return rel


async def conferir_kit(db, kit_id: str, solides: bytes | None = None, sinetram: bytes | None = None) -> dict:
    """O que os portais pagaram × o que a folha do kit concedeu. É a conferência que hoje a Pyetra faz no olho."""
    from sqlalchemy import text as sql

    kit = (await db.execute(sql("SELECT reference_month FROM ged_document_kits WHERE id = CAST(:k AS uuid)"), {"k": kit_id})).scalar()
    out: dict = {"kit_id": kit_id, "competencia": kit.strftime("%m/%Y") if kit else "", "divergencias": []}
    pagos: dict[str, dict] = {}
    if solides:
        p = ler_solides(solides)
        out["solides_total"] = float(p.total)
        for x in p.linhas:
            pagos.setdefault(x.cpf, {"nome": x.nome, "va": Decimal("0"), "vt": Decimal("0")})
            pagos[x.cpf]["va"] += x.alimentacao
            pagos[x.cpf]["vt"] += x.mobilidade
    if sinetram:
        p = ler_sinetram(sinetram)
        out["sinetram_total"] = float(p.total)
        for x in p.linhas:
            pagos.setdefault(x.cpf, {"nome": x.nome, "va": Decimal("0"), "vt": Decimal("0")})
            pagos[x.cpf]["vt"] += x.mobilidade
    do_kit = (await db.execute(sql(
        "SELECT DISTINCT regexp_replace(coalesce(e.cpf,''),'[^0-9]','','g'), e.nome FROM ged_kit_documents k "
        "JOIN employees e ON e.id = k.employee_id WHERE k.kit_id = CAST(:k AS uuid)"), {"k": kit_id})).fetchall()
    cpfs_kit = {r[0]: r[1] for r in do_kit}
    for cpf, nome in cpfs_kit.items():
        if cpf and cpf not in pagos:
            out["divergencias"].append(f"{nome}: está no kit e NÃO aparece em nenhum relatório de benefício do mês")
    for cpf, d in pagos.items():
        if cpf not in cpfs_kit:
            out["divergencias"].append(f"{d['nome']}: recebeu benefício e não está no kit deste condomínio")
    out["conferidos"] = len(cpfs_kit)
    return out
