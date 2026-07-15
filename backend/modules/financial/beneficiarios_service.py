"""Agenda de beneficiários PIX (favoritos) — como no app do Inter.

Digitar o nome → carrega a chave PIX + dados. Auto-salva todo beneficiário novo a cada
pagamento (upsert por chave). Seed inicial vem do que JÁ existe: pagamentos passados
(inter_payments), funcionários, diaristas e fornecedores.

Dado real sempre: nunca fabrica chave. Dedup por chave_pix (uma chave = um beneficiário).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_DDL = """
CREATE TABLE IF NOT EXISTS financial_beneficiarios (
    id            BIGSERIAL PRIMARY KEY,
    nome          VARCHAR(180) NOT NULL,
    chave_pix     VARCHAR(140),
    tipo_chave    VARCHAR(20),
    cpf_cnpj      VARCHAR(20),
    categoria     VARCHAR(30) DEFAULT 'avulso',   -- fornecedor|diarista|funcionario|pessoa|avulso
    origem        VARCHAR(30),                     -- pagamento|supplier|employee|diarist|manual
    vezes_pago    INTEGER DEFAULT 0,
    ultimo_pagamento DATE,
    ativo         BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT now(),
    updated_at    TIMESTAMP DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_benef_chave
    ON financial_beneficiarios (lower(chave_pix)) WHERE chave_pix IS NOT NULL AND chave_pix <> '';
CREATE INDEX IF NOT EXISTS ix_benef_nome ON financial_beneficiarios (lower(nome));
"""

_TESTE = {"", "0", "00000000000", "e2e_teste", "teste"}


async def _ensure(db: AsyncSession) -> None:
    for stmt in _DDL.strip().split(";\n"):
        s = stmt.strip()
        if s:
            await db.execute(text(s))
    await db.commit()


def _norm_chave(chave: str | None) -> str:
    return (chave or "").strip()


async def upsert_beneficiario(db: AsyncSession, *, nome: str | None, chave_pix: str | None,
                              tipo_chave: str | None = None, cpf_cnpj: str | None = None,
                              categoria: str = "avulso", origem: str = "pagamento",
                              contar_pagamento: bool = False) -> bool:
    """Insere ou atualiza um beneficiário pela chave PIX. Idempotente.

    contar_pagamento=True incrementa vezes_pago e marca ultimo_pagamento (uso no fluxo de pagar).
    Ignora entradas de teste / sem chave. NÃO commita (quem chama controla a transação)."""
    chave = _norm_chave(chave_pix)
    nome = (nome or "").strip()
    if not chave or chave.lower() in _TESTE or not nome or nome.lower() in _TESTE:
        return False
    await db.execute(text("""
        INSERT INTO financial_beneficiarios
            (nome, chave_pix, tipo_chave, cpf_cnpj, categoria, origem,
             vezes_pago, ultimo_pagamento, updated_at)
        VALUES (:nome, :chave, :tipo, :doc, :cat, :orig,
                :vz, CASE WHEN :cnt THEN CURRENT_DATE ELSE NULL END, now())
        ON CONFLICT (lower(chave_pix)) WHERE chave_pix IS NOT NULL AND chave_pix <> ''
        DO UPDATE SET
            nome = COALESCE(NULLIF(EXCLUDED.nome, ''), financial_beneficiarios.nome),
            tipo_chave = COALESCE(EXCLUDED.tipo_chave, financial_beneficiarios.tipo_chave),
            cpf_cnpj = COALESCE(EXCLUDED.cpf_cnpj, financial_beneficiarios.cpf_cnpj),
            categoria = CASE WHEN financial_beneficiarios.categoria = 'avulso'
                             THEN EXCLUDED.categoria ELSE financial_beneficiarios.categoria END,
            vezes_pago = financial_beneficiarios.vezes_pago + CASE WHEN :cnt THEN 1 ELSE 0 END,
            ultimo_pagamento = CASE WHEN :cnt THEN CURRENT_DATE ELSE financial_beneficiarios.ultimo_pagamento END,
            ativo = TRUE,
            updated_at = now()
    """), {"nome": nome, "chave": chave, "tipo": (tipo_chave or None), "doc": (cpf_cnpj or None),
           "cat": categoria, "orig": origem, "vz": (1 if contar_pagamento else 0),
           "cnt": contar_pagamento})
    return True


async def buscar(db: AsyncSession, q: str = "", limite: int = 12) -> list[dict[str, Any]]:
    """Autocomplete: retorna beneficiários cujo nome/chave/doc casa com q, mais usados primeiro."""
    await _ensure(db)
    like = f"%{(q or '').strip().lower()}%"
    rows = (await db.execute(text("""
        SELECT id, nome, chave_pix, tipo_chave, cpf_cnpj, categoria, vezes_pago
        FROM financial_beneficiarios
        WHERE ativo = TRUE AND chave_pix IS NOT NULL AND chave_pix <> ''
          AND (:q = '' OR lower(nome) LIKE :like OR lower(chave_pix) LIKE :like
               OR lower(coalesce(cpf_cnpj,'')) LIKE :like)
        ORDER BY vezes_pago DESC, lower(nome) ASC
        LIMIT :lim
    """), {"q": (q or "").strip(), "like": like, "lim": limite})).mappings().all()
    return [dict(r) for r in rows]


async def seed_de_fontes(db: AsyncSession) -> dict[str, int]:
    """Popula a agenda com o que já existe (idempotente). Roda 1x, mas seguro repetir."""
    await _ensure(db)
    add = 0

    async def _seed(sql: str, cat: str, orig: str, params: dict | None = None):
        nonlocal add
        try:
            rows = (await db.execute(text(sql), params or {})).mappings().all()
        except Exception:
            return
        for r in rows:
            ok = await upsert_beneficiario(
                db, nome=r.get("nome"), chave_pix=r.get("chave"),
                tipo_chave=r.get("tipo"), cpf_cnpj=r.get("doc"), categoria=cat, origem=orig)
            add += 1 if ok else 0

    # 1) pagamentos passados (inter_payments) — captura fornecedores já pagos (ex.: Saúde Manaus)
    await _seed("""
        SELECT DISTINCT ON (lower(destinatario->>'chave'))
               destinatario->>'nome_recebedor' AS nome,
               destinatario->>'chave' AS chave,
               destinatario->>'tipo_chave' AS tipo,
               NULL AS doc
        FROM inter_payments
        WHERE payment_type='pix' AND destinatario->>'chave' IS NOT NULL
    """, cat="pessoa", orig="pagamento")
    # 2) fornecedores (suppliers)
    await _seed("""
        SELECT name AS nome, pix_key AS chave, pix_key_type AS tipo, cpf_cnpj AS doc
        FROM suppliers WHERE pix_key IS NOT NULL AND pix_key <> ''
    """, cat="fornecedor", orig="supplier")
    # 3) funcionários (employees.pix_key)
    await _seed("""
        SELECT nome, pix_key AS chave, pix_key_type AS tipo, cpf AS doc
        FROM employees WHERE pix_key IS NOT NULL AND pix_key <> ''
    """, cat="funcionario", orig="employee")
    # 4) diaristas (diaria_diaristas.pix)
    await _seed("""
        SELECT nome, pix AS chave, NULL AS tipo, cpf AS doc
        FROM diaria_diaristas WHERE pix IS NOT NULL AND pix <> ''
    """, cat="diarista", orig="diarist")

    await db.commit()
    total = (await db.execute(text("SELECT count(*) FROM financial_beneficiarios"))).scalar()
    return {"processados": add, "total_agenda": int(total or 0)}
