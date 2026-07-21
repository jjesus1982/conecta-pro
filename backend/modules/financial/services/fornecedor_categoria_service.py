"""Categorização de FORNECEDORES + cadastro a partir das notas REAIS recebidas.

As notas tomadas (nfse_tomadas_nacional) e as NF-e de entrada (nfe_entradas) vêm com o
emitente (CNPJ+nome). Aqui derivamos a CATEGORIA do fornecedor (contabilidade, advocacia,
seg. trabalho, tecnologia, material, PJ…) e cadastramos/atualizamos o emitente em
`suppliers` — SÓ com dado REAL das notas (zero mock). A `suppliers.category` é a fonte da
verdade e é editável (override manual pelo Jordan).
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# condomínio-tenant usado pelos suppliers (matriz)
_COND_MATRIZ = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

CATEGORIAS = [
    "contabilidade", "advocacia", "seg_trabalho", "tecnologia", "beneficios",
    "seg_eletronica", "manutencao", "material", "pj", "outros",
]

# Mapa EXPLÍCITO por CNPJ (14 díg) — os regulares, categorizados à mão pela realidade.
CATEGORIA_POR_CNPJ: dict[str, str] = {
    "10461302000110": "tecnologia",     # SÓLIDES (RH/ponto)
    "36249489000187": "advocacia",      # CRUZ QUEIROZ & BERNARDINO ADVOGADOS
    "29243860000138": "contabilidade",  # PORTTE CONTÁBIL
    "24626902000104": "tecnologia",     # ECONDOS SISTEMAS
    "05892015000125": "seg_eletronica", # INVIOLÁVEL MARINGÁ
    "05774975000352": "beneficios",     # SERVDONTO (odontológico)
    "24989208000143": "tecnologia",     # ONE PORT
    "41339889000113": "seg_trabalho",   # MBD SILVA (MB Consultoria — SST)
    "25256038000150": "tecnologia",     # TANGERINO
    "05634834000172": "material",       # WTEC MÓVEIS E EQUIPAMENTOS
    "14843592000118": "tecnologia",     # ONE SUPPORT
    "02351877001124": "tecnologia",     # LWSA (Locaweb)
    "82901000000127": "material",       # INTELBRAS
    "34052649000178": "tecnologia",     # CORA TECNOLOGIA
    "37058073000144": "tecnologia",     # ZAPSIGN
    "10838823000144": "seg_eletronica", # DELTA ALARMES
    "39968633000123": "material",       # PPA AMAZONAS (equip. seg. eletrônica)
    "62427266000172": "manutencao",     # TRZ PNEUS
}

# Heurística por palavra no nome (fallback quando não está no mapa explícito).
_REGRAS_NOME: list[tuple[str, str]] = [
    ("ADVOG", "advocacia"), ("ADVOCACIA", "advocacia"),
    ("CONTABIL", "contabilidade"), ("CONTÁBIL", "contabilidade"),
    ("ODONTOLOG", "beneficios"), ("PLANO DE ASSIST", "beneficios"), ("ODONTO", "beneficios"),
    ("SEGURANCA DO TRAB", "seg_trabalho"), ("SEGURANÇA DO TRAB", "seg_trabalho"), ("SST", "seg_trabalho"),
    ("ALARME", "seg_eletronica"), ("MONITORAMENTO", "seg_eletronica"), ("CFTV", "seg_eletronica"),
    ("PNEU", "manutencao"), ("AUTOMOTIV", "manutencao"), ("MANUTENCAO", "manutencao"), ("MANUTENÇÃO", "manutencao"),
    ("TECNOLOGIA", "tecnologia"), ("SISTEMAS", "tecnologia"), ("SOFTWARE", "tecnologia"), ("INFORMATICA", "tecnologia"),
    ("COMERCIO", "material"), ("COMÉRCIO", "material"), ("INDUSTRIA", "material"), ("INDÚSTRIA", "material"),
    ("MATERIAIS", "material"), ("EQUIPAMENTOS", "material"), ("DESCARTAVEIS", "material"), ("LOCADORA", "material"),
]


def _cnpj14(v: str | None) -> str:
    return re.sub(r"\D", "", v or "")


def categoria_de(cnpj: str | None, nome: str | None, is_material: bool = False,
                 cnpjs_pj: set[str] | None = None) -> str:
    """Deriva a categoria: PJ contratado → mapa explícito → NF-e=material → heurística → outros."""
    dig = _cnpj14(cnpj)
    if cnpjs_pj and dig in cnpjs_pj:
        return "pj"
    if dig in CATEGORIA_POR_CNPJ:
        return CATEGORIA_POR_CNPJ[dig]
    up = (nome or "").upper()
    for chave, cat in _REGRAS_NOME:
        if chave in up:
            return cat
    if is_material:
        return "material"
    return "outros"


async def sincronizar_fornecedores(db: AsyncSession) -> dict:
    """Cadastra/atualiza em `suppliers` TODOS os emitentes reais das notas (serviços+material),
    com a categoria derivada. Idempotente por cpf_cnpj. NÃO inventa fornecedor — só o que
    tem nota no banco. Preserva a categoria se o Jordan já tiver feito override (só preenche
    quando está vazia)."""
    # CNPJs dos PJ contratados (categoria 'pj')
    pj_rows = (await db.execute(text(
        "SELECT DISTINCT regexp_replace(COALESCE(pix_key,''),'[^0-9]','','g') d FROM employees "
        "WHERE tipo_contrato='pj' AND pix_key ~ '^[0-9]{14}$'"))).fetchall()
    cnpjs_pj = {r.d for r in pj_rows if r.d}

    # Emitentes reais: serviços (nfse_tomadas) + materiais (nfe_entradas)
    servicos = (await db.execute(text(
        "SELECT regexp_replace(COALESCE(prestador_cnpj,''),'[^0-9]','','g') cnpj, "
        "MAX(prestador_nome) nome FROM nfse_tomadas_nacional "
        "WHERE COALESCE(prestador_cnpj,'')<>'' GROUP BY 1"))).fetchall()
    materiais = (await db.execute(text(
        "SELECT regexp_replace(COALESCE(emitente_cnpj,''),'[^0-9]','','g') cnpj, "
        "MAX(emitente_nome) nome FROM nfe_entradas WHERE COALESCE(emitente_cnpj,'')<>'' GROUP BY 1"))).fetchall()

    emitentes: dict[str, tuple[str, bool]] = {}
    for r in servicos:
        if len(r.cnpj) in (11, 14):
            emitentes[r.cnpj] = (r.nome, False)
    for r in materiais:
        if len(r.cnpj) in (11, 14):
            # material só define is_material se ainda não veio como serviço
            nome, _ = emitentes.get(r.cnpj, (r.nome, True))
            emitentes[r.cnpj] = (nome, True if r.cnpj not in {s.cnpj for s in servicos} else False)

    novos = atualizados = 0
    for cnpj, (nome, is_mat) in emitentes.items():
        cat = categoria_de(cnpj, nome, is_material=is_mat, cnpjs_pj=cnpjs_pj)
        tipo = "pj" if cat == "pj" else ("material" if is_mat else "servico")
        # existe (comparando por DÍGITOS, não pela grafia com pontos)?
        existe = (await db.execute(text(
            "SELECT id, category FROM suppliers "
            "WHERE regexp_replace(COALESCE(cpf_cnpj,''),'[^0-9]','','g')=:cnpj "
            "AND condominio_id=:cond LIMIT 1"),
            {"cnpj": cnpj, "cond": _COND_MATRIZ})).first()
        if existe:
            # preenche categoria só se estiver vazia (respeita override manual do Jordan)
            if not (existe.category or "").strip():
                await db.execute(text(
                    "UPDATE suppliers SET category=:cat, updated_at=NOW() WHERE id=:id"),
                    {"cat": cat, "id": existe.id})
                atualizados += 1
        else:
            await db.execute(text(
                "INSERT INTO suppliers (id, condominio_id, cpf_cnpj, name, supplier_type, "
                "category, status, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :cond, :cnpj, :nome, :tipo, :cat, 'ativo', NOW(), NOW())"),
                {"cond": _COND_MATRIZ, "cnpj": cnpj, "nome": (nome or "")[:180], "tipo": tipo, "cat": cat})
            novos += 1
    await db.commit()
    return {"ok": True, "emitentes_reais": len(emitentes), "novos": novos,
            "categorias_preenchidas": atualizados, "pj_cnpjs": len(cnpjs_pj)}
