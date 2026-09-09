"""Lê a FOLHA ANALÍTICA do contador (Onvio/Domínio) e popula o cadastro que o nosso motor precisa (09/09/2026).

Pedido do Jordan: "implementa o resto também — intrajornada, salário família, insalubridade, desconta o crédito do
trabalhador (empréstimo em folha); se pegar a folha de maio no Onvio vai estar lá esse desconto também".

O motor de folha JÁ calcula as quatro. O que faltava era o CADASTRO que as liga:
    insalubridade  → employees.insalubridade_percentual   (rubrica 223/201 na folha real, 10% do salário base)
    intrajornada   → employees.recebe_intrajornada        (rubricas 244/245/208/209)
    salário-família→ employees.dependentes (menor_14)     (rubrica 995, R$ 67,54 por quota)
    consignado     → employee_deductions                  (rubricas 269/271/273/275/9750 "DESC. EMP. CRED. TRAB Nº …")

Este importador lê o PDF da folha analítica (EXTRATO MENSAL, um bloco por funcionário), casa por CPF e devolve o
que MUDARIA. Só grava com `aplicar=True`. Idempotente: consignado é chave (funcionário × nº do contrato).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal

logger = logging.getLogger(__name__)

RE_BLOCO = re.compile(r"Empr\.:\s*(\d+)\s+(.+?)\s+Situação:\s*(\S+)\s+CPF:\s*([\d.\-]+)", re.S)
RE_CARGO = re.compile(r"Cargo:\s*\d+\s+(.+?)\s+C\.B\.O:\s*(\d+)")
RE_SALARIO = re.compile(r"Salário:\s*([\d.,]+)")
RE_HORASMES = re.compile(r"Horas Mês:\s*([\d.,]+)")
RE_INSAL = re.compile(r"\b2\d{2}\s+INSALUBRIDADE\s+([\d.,]+)\s+([\d.,]+)")
RE_INTRA = re.compile(r"\b2\d{2}\s+INTRAJORNADA\s+(DIURNO|NOTURNA)")
RE_SALFAM = re.compile(r"\b995\s+SALARIO FAMILIA\s+([\d.,]+)\s+([\d.,]+)")
# O PDF quebra a linha no meio do número do contrato ("…Nº 6221574" / "6 102,83 102,83"). Na folha real a
# REFERÊNCIA é sempre igual ao VALOR (102,83 102,83), então tudo que estiver antes desse par pertence ao contrato.
RE_CONSIG = re.compile(r"\b(\d{3,4})\s+DESC\. EMP\. CRED\. TRAB N[ºo°]?\s*([\d ]+?)\s+([\d.,]+)\s+\3\b")
RE_COMPETENCIA = re.compile(r"Compet[êe]ncia:\s*(\d{2})/(\d{4})")


def _num(s: str) -> Decimal:
    return Decimal((s or "0").replace(".", "").replace(",", "."))


def _dig(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


@dataclass
class FuncionarioFolha:
    matricula: str
    nome: str
    cpf: str
    situacao: str = ""
    cargo: str = ""
    cbo: str = ""
    salario: Decimal = Decimal("0")
    horas_mes: str = ""
    insalubridade_pct: Decimal | None = None
    intrajornada: bool = False
    quotas_salario_familia: int = 0
    consignados: list[dict] = field(default_factory=list)


def ler_folha_analitica(pdf_bytes: bytes | None = None, texto: str | None = None) -> tuple[str, list[FuncionarioFolha]]:
    """Devolve (competência 'MM/AAAA', lista de funcionários com o que a folha real diz)."""
    contratos_ok: set[str] = set()
    if texto is None:
        # PyMuPDF com sort=True dá a ESTRUTURA (um bloco por funcionário, rubrica por linha). Só ele não serve
        # para o nº do contrato do consignado: medido em 09/09/2026 na folha 05/2026, entrega 6221574 em vez de
        # 62215746 (um dígito a menos). O pdfminer erra a estrutura mas acerta os números — usamos os dois.
        import io as _io

        import fitz  # PyMuPDF

        doc = fitz.open(stream=pdf_bytes or b"", filetype="pdf")
        texto = "\n".join(pg.get_text("text", sort=True) for pg in doc)
        doc.close()
        try:
            from pdfminer.high_level import extract_text

            bruto = extract_text(_io.BytesIO(pdf_bytes or b""))
            contratos_ok = set(re.findall(r"CRED\. TRAB N[ºo°]?\s*(\d+)", re.sub(r"\s+", " ", bruto)))
        except Exception as exc:  # noqa: BLE001
            logger.warning("pdfminer não leu os contratos do consignado: %s", exc)
    texto_flat = re.sub(r"[ \t]*\n[ \t]*", " ", texto)
    comp_m = RE_COMPETENCIA.search(texto_flat) or RE_COMPETENCIA.search(texto)
    competencia = f"{comp_m.group(1)}/{comp_m.group(2)}" if comp_m else ""
    partes = texto.split("Empr.:")
    out: list[FuncionarioFolha] = []
    for parte in partes[1:]:
        bloco = "Empr.:" + parte
        m = RE_BLOCO.search(bloco)
        if not m:
            continue
        f = FuncionarioFolha(matricula=m.group(1), nome=m.group(2).strip(), cpf=_dig(m.group(4)), situacao=m.group(3))
        if (c := RE_CARGO.search(bloco)):
            f.cargo, f.cbo = c.group(1).strip(), c.group(2)
        if (s := RE_SALARIO.search(bloco)):
            f.salario = _num(s.group(1))
        if (h := RE_HORASMES.search(bloco)):
            f.horas_mes = h.group(1)
        # o PDF quebra a linha no meio do número do contrato ("…Nº 6221574" / "6 102,83") — achatar antes de
        # extrair as rubricas (medido em 09/09: contratos vinham com 1 dígito a menos).
        bloco = re.sub(r"\s*\n\s*", " ", bloco)
        if (i := RE_INSAL.search(bloco)):
            # a folha traz a referência em pontos percentuais ("10,00" = 10%) — é exatamente como
            # employees.insalubridade_percentual guarda (o motor divide por 100 na leitura).
            f.insalubridade_pct = _num(i.group(1))
        f.intrajornada = bool(RE_INTRA.search(bloco))
        if (sf := RE_SALFAM.search(bloco)):
            f.quotas_salario_familia = int(_num(sf.group(1)))
        for cod, contrato, valor in RE_CONSIG.findall(bloco):
            num = contrato.replace(" ", "")
            # completa o dígito que o PyMuPDF corta, usando a lista que o pdfminer leu inteira
            num = next((c for c in contratos_ok if c.startswith(num) and len(c) > len(num)), num)
            f.consignados.append({"codigo": cod, "contrato": num, "valor": float(_num(valor))})
        out.append(f)
    return competencia, out


async def importar(db, pdf_bytes: bytes | None = None, texto: str | None = None, aplicar: bool = False) -> dict:
    """Casa por CPF e (opcionalmente) grava. Devolve o diff, sempre — o dry-run é o padrão."""
    from sqlalchemy import text as sql

    competencia, funcs = ler_folha_analitica(pdf_bytes=pdf_bytes, texto=texto)
    rel: dict = {"competencia": competencia, "na_folha": len(funcs), "casados": 0, "sem_cadastro": [],
                 "insalubridade": [], "intrajornada": [], "salario_familia": [], "consignado": [], "aplicado": aplicar}
    for f in funcs:
        row = (await db.execute(sql(
            "SELECT id::text, nome, coalesce(insalubridade_percentual,0), coalesce(recebe_intrajornada,false), dependentes "
            "FROM employees WHERE regexp_replace(coalesce(cpf,''),'[^0-9]','','g') = :c LIMIT 1"), {"c": f.cpf})).first()
        if not row:
            rel["sem_cadastro"].append(f"{f.nome} (CPF …{f.cpf[-4:]})")
            continue
        rel["casados"] += 1
        eid, nome, insal_atual, intra_atual, deps = row[0], row[1], Decimal(str(row[2] or 0)), bool(row[3]), row[4]
        if f.insalubridade_pct is not None and abs(insal_atual - f.insalubridade_pct) > Decimal("0.001"):
            rel["insalubridade"].append(f"{nome}: {float(insal_atual):.0f}% → {float(f.insalubridade_pct):.0f}%")
            if aplicar:
                await db.execute(sql("UPDATE employees SET insalubridade_percentual = :p, updated_at = now() WHERE id = CAST(:e AS uuid)"),
                                 {"p": float(f.insalubridade_pct), "e": eid})
        if f.intrajornada and not intra_atual:
            rel["intrajornada"].append(nome)
            if aplicar:
                await db.execute(sql("UPDATE employees SET recebe_intrajornada = true, updated_at = now() WHERE id = CAST(:e AS uuid)"), {"e": eid})
        n_dep = sum(1 for d in (deps or []) if isinstance(d, dict) and d.get("menor_14")) if isinstance(deps, list) else 0
        if f.quotas_salario_familia and f.quotas_salario_familia != n_dep:
            rel["salario_familia"].append(f"{nome}: {n_dep} → {f.quotas_salario_familia} quota(s)")
            if aplicar:
                import json as _json

                novos = [d for d in (deps or []) if isinstance(d, dict) and not d.get("menor_14")] if isinstance(deps, list) else []
                novos += [{"nome": f"Dependente {i + 1} (folha {competencia})", "menor_14": True, "origem": "folha_analitica"}
                          for i in range(f.quotas_salario_familia)]
                await db.execute(sql("UPDATE employees SET dependentes = CAST(:d AS jsonb), updated_at = now() WHERE id = CAST(:e AS uuid)"),
                                 {"d": _json.dumps(novos), "e": eid})
        for c in f.consignados:
            desc = f"Empréstimo Consignado Nº {c['contrato']}"
            _mm, _aa = (competencia.split("/") + ["1", "2026"])[:2]
            ja = (await db.execute(sql(
                "SELECT id::text, valor FROM employee_deductions WHERE employee_id = CAST(:e AS uuid) AND descricao = :d "
                "AND data_inicio = make_date(:aa, :mm, 1)"),
                {"e": eid, "d": desc, "aa": int(_aa), "mm": int(_mm)})).first()
            if ja and abs(float(ja[1] or 0) - c["valor"]) < 0.01:
                continue
            rel["consignado"].append(f"{nome}: {desc} R$ {c['valor']:.2f}" + (" (atualiza)" if ja else " (novo)"))
            if aplicar:
                if ja:
                    await db.execute(sql("UPDATE employee_deductions SET valor = :v, ativo = true, updated_at = now() WHERE id = CAST(:i AS uuid)"),
                                     {"v": c["valor"], "i": ja[0]})
                else:
                    # A parcela vale SÓ na competência em que a folha real a mostrou (mesma regra da carga
                    # jan–jun): data_inicio = 1º dia, data_fim = último dia. Sem data_fim o desconto vazaria para
                    # os meses seguintes — e o Jordan avisou que "este mês não veio, vem no próximo".
                    await db.execute(sql(
                        "INSERT INTO employee_deductions (id, employee_id, tipo, descricao, valor, ativo, observacao, "
                        "data_inicio, data_fim, base_calculo, created_at, updated_at) "
                        "VALUES (gen_random_uuid(), CAST(:e AS uuid), 'consignado', :d, :v, true, :o, "
                        "make_date(:aa, :mm, 1), (make_date(:aa, :mm, 1) + INTERVAL '1 month' - INTERVAL '1 day')::date, "
                        "'liquido', now(), now())"),
                        {"e": eid, "d": desc, "v": c["valor"], "o": f"importado da folha analítica {competencia} (Onvio)",
                         "aa": int(_aa), "mm": int(_mm)})
    if aplicar:
        await db.commit()
    logger.info("folha analítica %s: %s", competencia, {k: (len(v) if isinstance(v, list) else v) for k, v in rel.items()})
    return rel
