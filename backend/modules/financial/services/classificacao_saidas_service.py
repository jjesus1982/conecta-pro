"""Classificação das saídas do extrato — agrupada, com sugestão, decisão humana.

Por que existe: o razão só conhece **6% dos lançamentos do extrato** (268 de 4.502),
e quase só entradas. Para o razão refletir o caixa, cada saída precisa dizer o que
foi. São 1.241 saídas sem etiqueta (R$1.054.752,65) — rever uma a uma é inviável.

Medido em 2026-08-11 e é o que torna isto viável:
  • as 380 saídas ≥ R$1.000 se repetem entre apenas **183 contrapartes**;
  • **235** delas são para FUNCIONÁRIO cadastrado (R$409.174,72) → regra, não decisão;
  • 1.099 pagamentos de R$32,00 (VT+VR de diarista) já estão etiquetados.

Desenho: o sistema PROPÕE por regra e o humano CONFIRMA por grupo. Pedir
classificação do zero, uma a uma, é abandonado em três semanas.

Parede: sugestão nunca vira etiqueta sozinha. Nada aqui grava sem alguém confirmar.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Lista FECHADA. O campo livre já produziu dialeto na base: `imposto` e `impostos`,
# `outros` e `outro` convivem hoje. Categoria nova entra AQUI, não digitada.
CATEGORIAS: tuple[tuple[str, str], ...] = (
    ("salario", "Salário — funcionário CLT"),
    ("beneficio_vtvr", "Benefício — VT / VR / VA"),
    ("pj_prolabore", "PJ / Pró-labore — prestador"),
    ("socio", "Sócio — retirada, distribuição ou empréstimo"),
    ("fornecedor", "Fornecedor — serviço ou material"),
    ("imposto", "Imposto / guia — INSS, FGTS, DAS, DARF"),
    ("transferencia_interna", "Transferência entre empresas do grupo"),
    ("taxa_bancaria", "Taxa bancária"),
    ("diversos", "Diversos — pequeno valor, sem enquadramento"),
)
CATEGORIAS_VALIDAS = frozenset(k for k, _ in CATEGORIAS)

# Normaliza a contraparte: tira o código mascarado do banco e a pontuação.
_SQL_CONTRAPARTE = (
    "regexp_replace(regexp_replace(upper(coalesce(counterparty_name, "
    "regexp_replace(coalesce(description,''),'^.*?-\\s*',''))), "
    "'[^A-Z0-9 ]', ' ', 'g'), ' +', ' ', 'g')"
)

# Empresas do PRÓPRIO grupo: dinheiro entre CNPJs nossos não é despesa, é
# transferência. Sem esta regra a heurística de fornecedor sugeria "Fornecedor"
# para R$70.000 indo de uma empresa nossa para outra — sugestão errada com cara
# de certa, que é pior que não sugerir: o humano confirma em bloco e grava o erro.
_GRUPO = ("CONECTA MAIS", "CONECTAMAIS", "CONECTA PRO", "CONECTA ELETRONICA",
          "CONECTA PATRIMONIAL", "CONECTA MAIS REDES")

# SÓCIO: retirada, pró-labore, distribuição de lucro ou empréstimo. Precisa vir
# ANTES do teste de funcionário — o sócio também está em `employees`, e a regra
# sugeria "Salário — CLT" para pagamento ao dono. O enquadramento fino
# (pró-labore x distribuição x mútuo) muda o imposto e é decisão dele.
_SOCIO = ("JORDAN SANTOS DE JESUS", "JORDAN S DE JESUS", "JORDAN JESUS")

# PJ conhecidos (informados pelo Jordan em 2026-08-11). Nome novo entra aqui.
_PJ = ("PYETRA", "PEDRO", "RUAN", "RAMON", "ORLAILSON", "ELIZIEL", "DIEGO FERREIRA")
_FOLHA_TERCEIRO = ("SOLIDES", "S LIDES", "SINETRAN")
_IMPOSTO = ("RECEITA FEDERAL", "CEF MATRIZ", "CAIXA ECONOMICA", "DARF", "GPS",
            "SIMPLES NACIONAL", "PGFN", "FGTS", "INSS", "PREVID")
_TAXA = ("TARIFA", "TAXA", "IOF", "ANUIDADE", "PACOTE DE SERVICOS")

_RE_NAO_ALFA = re.compile(r"[^A-Za-z ]")


def _sugerir(contraparte: str, valor: float, e_funcionario: bool, tem_nfse: bool) -> tuple[str | None, str]:
    """(categoria_sugerida, motivo). None = o sistema não sabe; decide o humano.

    Ordem importa: o teste mais específico primeiro. Um funcionário que também é
    PJ deve cair em PJ, não em salário.
    """
    c = (contraparte or "").upper()
    if any(g in c for g in _GRUPO):
        return "transferencia_interna", "outra empresa do grupo Conecta"
    if any(x in c for x in _SOCIO):
        return "socio", "favorecido é o sócio — enquadramento fino é decisão dele"
    if any(t in c for t in _IMPOSTO):
        return "imposto", "favorecido é órgão arrecadador"
    if any(t in c for t in _FOLHA_TERCEIRO):
        return "beneficio_vtvr", "operadora de VT/VR (Sólides/Sinetran)"
    if any(p in c for p in _PJ):
        return "pj_prolabore", "prestador PJ conhecido"
    if any(t in c for t in _TAXA):
        return "taxa_bancaria", "descrição de tarifa bancária"
    if abs(valor) == 32.0:
        return "beneficio_vtvr", "R$32,00 = VT + VR de diarista"
    if e_funcionario:
        return "salario", "favorecido é funcionário cadastrado"
    if tem_nfse:
        return "fornecedor", "há NFS-e tomada deste CNPJ"
    if abs(valor) < 50:
        return "diversos", "valor pequeno, sem enquadramento"
    return None, "sem regra — precisa de decisão humana"


async def listar_grupos(db: AsyncSession, *, minimo: float = 0.0, limite: int = 60) -> dict:
    """Saídas SEM classificação, agrupadas por contraparte, com sugestão."""
    rows = (await db.execute(text(f"""
        WITH sem AS (
            SELECT {_SQL_CONTRAPARTE} AS contraparte,
                   count(*) AS n, sum(abs(amount)) AS valor,
                   min(transaction_date)::date AS de, max(transaction_date)::date AS ate,
                   max(upper(regexp_replace(coalesce(counterparty_name,
                       regexp_replace(coalesce(description,''),'^.*?-\\s*','')),'[^A-Za-z ]','','g'))) AS alvo,
                   max(coalesce(counterparty_document,'')) AS doc
            FROM bank_transactions
            WHERE amount < 0 AND justificativa_categoria IS NULL
            GROUP BY 1
            HAVING sum(abs(amount)) >= :minimo
        )
        SELECT s.contraparte, s.n, s.valor, s.de, s.ate,
               EXISTS (SELECT 1 FROM employees e WHERE e.nome IS NOT NULL AND length(e.nome) > 8
                       AND s.alvo LIKE '%' || split_part(upper(e.nome),' ',1) || '%'
                       AND s.alvo LIKE '%' || split_part(upper(e.nome),' ',
                            array_length(string_to_array(e.nome,' '),1)) || '%') AS e_func,
               EXISTS (SELECT 1 FROM nfse_tomadas_nacional t
                       WHERE upper(coalesce(t.prestador_nome,'')) <> ''
                         AND s.contraparte LIKE '%' || split_part(upper(t.prestador_nome),' ',1) || '%') AS tem_nfse
        FROM sem s
        ORDER BY s.valor DESC
        LIMIT :limite
    """), {"minimo": minimo, "limite": limite})).mappings().all()

    grupos = []
    for r in rows:
        cat, motivo = _sugerir(r["contraparte"], float(r["valor"]), r["e_func"], r["tem_nfse"])
        grupos.append({
            "contraparte": r["contraparte"].strip(),
            "movimentacoes": int(r["n"]),
            "valor": round(float(r["valor"]), 2),
            "periodo": f"{r['de']} a {r['ate']}",
            "sugestao": cat,
            "sugestao_label": dict(CATEGORIAS).get(cat, "—") if cat else "—",
            "motivo": motivo,
        })
    return {"grupos": grupos, "categorias": [{"value": k, "label": v} for k, v in CATEGORIAS]}


async def classificar_grupo(db: AsyncSession, *, contraparte: str, categoria: str,
                            responsavel: str) -> dict:
    """Aplica a categoria a TODAS as saídas sem classificação daquela contraparte.

    Só toca `amount < 0` e `justificativa_categoria IS NULL` — nunca reclassifica o
    que já foi decidido antes.
    """
    if categoria not in CATEGORIAS_VALIDAS:
        return {"ok": False, "erro": f"categoria inválida: {categoria!r}"}
    alvo = (contraparte or "").strip()
    if len(alvo) < 3:
        return {"ok": False, "erro": "contraparte muito curta para casar com segurança"}

    label = dict(CATEGORIAS)[categoria]
    r = (await db.execute(text(f"""
        UPDATE bank_transactions SET
            justificativa_categoria = :cat,
            justificativa = :just,
            justificativa_responsavel = :resp,
            justificativa_data = NOW(),
            updated_at = NOW()
        WHERE amount < 0 AND justificativa_categoria IS NULL
          AND {_SQL_CONTRAPARTE} = :alvo
        RETURNING abs(amount)
    """), {"cat": categoria, "just": label, "resp": responsavel, "alvo": alvo})).fetchall()
    await db.commit()
    total = round(sum(float(x[0]) for x in r), 2)
    return {"ok": True, "contraparte": alvo, "categoria": categoria, "categoria_label": label,
            "classificadas": len(r), "valor": total}
