"""Diárias de diaristas — modelo da planilha do Jordan (DIARISTAS_MARCO_2026).

Cadastros (Operacional): funções, turnos, postos/condomínios, tabela de preços (Função|Turno→valor),
diaristas. Gonzaga LANÇA a diária escolhendo tudo em lista suspensa — o valor sai automático da
tabela de preços. O RESUMO por diarista vira o lote a pagar (Financeiro, dia 15).

Tudo pré-cadastrado (seed da planilha real): 6 funções, 8 preços, ~10 postos, 32 diaristas.
"""
from __future__ import annotations

import logging
from datetime import date as _date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── Seed da planilha real (março/2026) ───────────────────────────────────────
_FUNCOES = ["AGENTE DE PORTARIA", "AUX. SERVIÇOS GERAIS", "AJUDANTE", "JARDINEIRO", "SUPERVISÃO ASG", "GERENTE"]
_TURNOS = ["DIURNO", "NOTURNO", "MEIO PERÍODO", "ÚNICO"]  # ÚNICO = "—" (funções sem turno)
_POSTOS = ["IDEAL FLORES", "LARANJEIRAS VILLAGE", "VILA DEI FIORI", "VILLA DOS PASSAROS", "PRIME",
           "PRIME ARENA", "MIRANTE", "MICHELANGELO", "PARISE VILLAGE", "PISCINAS"]
# (funcao, turno, valor) — turno só se aplica a AGENTE DE PORTARIA; demais usam 'ÚNICO'
_PRECOS = [
    ("AGENTE DE PORTARIA", "DIURNO", 90.00),
    ("AGENTE DE PORTARIA", "NOTURNO", 100.00),
    ("AGENTE DE PORTARIA", "MEIO PERÍODO", 30.00),
    ("AUX. SERVIÇOS GERAIS", "ÚNICO", 70.00),
    ("AJUDANTE", "ÚNICO", 70.00),
    ("JARDINEIRO", "ÚNICO", 80.00),
    ("SUPERVISÃO ASG", "ÚNICO", 70.00),
    ("GERENTE", "ÚNICO", 90.00),
]
_DIARISTAS = [
    "ADAILSON SERRA", "ANTONIO DINIZ", "CARLOS EDUARDO", "CINTIA OLIVEIRA", "CONCEIÇÃO LIMA",
    "DANIEL VIDAL", "DIEGO FERREIRA", "EDWILSON CORREA", "EIDY CULIER", "ELIZIEL GONZAGA",
    "ERIKA CRISTINA", "FANUEL GONZAGA", "FERNANDA VINHOTE", "FERNANDO MIGUEL", "FERNANDO SIMPLICIO",
    "FRANCISCO RAMON", "GEILSON RODRIGUES", "GISELE ALVES", "JEOVANE NASCIMENTO", "JONATHA DINIZ",
    "JONILSON MARTINS", "KEYSON SILVA", "LIVIA CARISE", "LOIDE FLORES", "MAIARA MUNIZ",
    "MARCELINO SILVA", "MARTA PINHEIRO", "MATHEUS HENRIQUE", "MAURICIO CHAGAS", "MEIRE GABRIELA",
    "RILEM SOUZA", "SILVANA AMAZONAS",
]

_DDL = [
    "CREATE TABLE IF NOT EXISTS diaria_funcoes (id SERIAL PRIMARY KEY, nome TEXT UNIQUE NOT NULL, ativo BOOLEAN DEFAULT TRUE)",
    "CREATE TABLE IF NOT EXISTS diaria_turnos (id SERIAL PRIMARY KEY, nome TEXT UNIQUE NOT NULL, ativo BOOLEAN DEFAULT TRUE)",
    "CREATE TABLE IF NOT EXISTS diaria_postos (id SERIAL PRIMARY KEY, nome TEXT UNIQUE NOT NULL, ativo BOOLEAN DEFAULT TRUE)",
    """CREATE TABLE IF NOT EXISTS diaria_precos (
         id SERIAL PRIMARY KEY, funcao TEXT NOT NULL, turno TEXT NOT NULL DEFAULT 'ÚNICO',
         valor NUMERIC(10,2) NOT NULL, ativo BOOLEAN DEFAULT TRUE,
         UNIQUE (funcao, turno))""",
    """CREATE TABLE IF NOT EXISTS diaria_diaristas (
         id SERIAL PRIMARY KEY, nome TEXT NOT NULL, cpf VARCHAR(14), pix TEXT,
         funcoes TEXT[], ativo BOOLEAN DEFAULT TRUE, created_at TIMESTAMPTZ DEFAULT now())""",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_diaria_diarista_nome ON diaria_diaristas (lower(nome))",
    """CREATE TABLE IF NOT EXISTS diaria_lancamentos (
         id SERIAL PRIMARY KEY, data DATE NOT NULL, diarista_id INT NOT NULL REFERENCES diaria_diaristas(id),
         funcao TEXT NOT NULL, posto TEXT NOT NULL, turno TEXT NOT NULL DEFAULT 'ÚNICO',
         valor NUMERIC(10,2) NOT NULL, observacao TEXT, status VARCHAR(20) DEFAULT 'lancado',
         created_by VARCHAR(64), created_at TIMESTAMPTZ DEFAULT now())""",
]


async def ensure_e_seed(db: AsyncSession) -> None:
    """Cria as tabelas e SEMEIA os cadastros da planilha (idempotente — só se vazio)."""
    for ddl in _DDL:
        await db.execute(text(ddl))
    # seeds (só quando a tabela está vazia)
    if not (await db.execute(text("SELECT 1 FROM diaria_funcoes LIMIT 1"))).first():
        for f in _FUNCOES:
            await db.execute(text("INSERT INTO diaria_funcoes (nome) VALUES (:n) ON CONFLICT DO NOTHING"), {"n": f})
    if not (await db.execute(text("SELECT 1 FROM diaria_turnos LIMIT 1"))).first():
        for t in _TURNOS:
            await db.execute(text("INSERT INTO diaria_turnos (nome) VALUES (:n) ON CONFLICT DO NOTHING"), {"n": t})
    if not (await db.execute(text("SELECT 1 FROM diaria_postos LIMIT 1"))).first():
        for p in _POSTOS:
            await db.execute(text("INSERT INTO diaria_postos (nome) VALUES (:n) ON CONFLICT DO NOTHING"), {"n": p})
    if not (await db.execute(text("SELECT 1 FROM diaria_precos LIMIT 1"))).first():
        for func, turno, valor in _PRECOS:
            await db.execute(text("INSERT INTO diaria_precos (funcao,turno,valor) VALUES (:f,:t,:v) ON CONFLICT DO NOTHING"),
                             {"f": func, "t": turno, "v": valor})
    if not (await db.execute(text("SELECT 1 FROM diaria_diaristas LIMIT 1"))).first():
        for nome in _DIARISTAS:
            await db.execute(text("INSERT INTO diaria_diaristas (nome) VALUES (:n) ON CONFLICT DO NOTHING"), {"n": nome})
    await db.commit()


# ── Cadastros (para as listas suspensas) ─────────────────────────────────────
async def cadastros(db: AsyncSession) -> dict[str, Any]:
    """Tudo que o Gonzaga seleciona em lista suspensa + a tabela de preços."""
    await ensure_e_seed(db)
    funcoes = [r[0] for r in (await db.execute(text("SELECT nome FROM diaria_funcoes WHERE ativo ORDER BY nome"))).all()]
    turnos = [r[0] for r in (await db.execute(text("SELECT nome FROM diaria_turnos WHERE ativo ORDER BY id"))).all()]
    postos = [r[0] for r in (await db.execute(text("SELECT nome FROM diaria_postos WHERE ativo ORDER BY nome"))).all()]
    diaristas = [{"id": r[0], "nome": r[1], "tem_pix": bool(r[2])}
                 for r in (await db.execute(text("SELECT id, nome, pix FROM diaria_diaristas WHERE ativo ORDER BY nome"))).all()]
    precos = [{"funcao": r[0], "turno": r[1], "valor": float(r[2])}
              for r in (await db.execute(text("SELECT funcao, turno, valor FROM diaria_precos WHERE ativo ORDER BY funcao, turno"))).all()]
    return {"funcoes": funcoes, "turnos": turnos, "postos": postos, "diaristas": diaristas, "precos": precos}


async def preco_de(db: AsyncSession, funcao: str, turno: str | None) -> float | None:
    """Valor automático da diária pela chave Função|Turno (turno só p/ Agente de Portaria)."""
    t = (turno or "ÚNICO").upper()
    if funcao.upper() != "AGENTE DE PORTARIA":
        t = "ÚNICO"
    r = await db.execute(text("SELECT valor FROM diaria_precos WHERE upper(funcao)=upper(:f) AND upper(turno)=upper(:t) AND ativo"),
                         {"f": funcao, "t": t})
    v = r.scalar()
    return float(v) if v is not None else None


# ── Lançamento (Gonzaga registra a diária) ───────────────────────────────────
async def lancar(db: AsyncSession, data: str, diarista_id: int, funcao: str, posto: str,
                 turno: str | None = None, observacao: str | None = None,
                 user_id: str | None = None) -> dict[str, Any]:
    await ensure_e_seed(db)
    valor = await preco_de(db, funcao, turno)
    if valor is None:
        return {"ok": False, "mensagem": f"Sem preço cadastrado para {funcao}|{turno or 'ÚNICO'}."}
    t = "ÚNICO" if funcao.upper() != "AGENTE DE PORTARIA" else (turno or "ÚNICO").upper()
    dref = _date.fromisoformat(data) if isinstance(data, str) else data
    r = await db.execute(text(
        """INSERT INTO diaria_lancamentos (data, diarista_id, funcao, posto, turno, valor, observacao, created_by)
           VALUES (:d,:did,:f,:p,:t,:v,:obs,:u) RETURNING id"""),
        {"d": dref, "did": diarista_id, "f": funcao, "p": posto, "t": t, "v": valor,
         "obs": observacao, "u": str(user_id) if user_id else None})
    await db.commit()
    return {"ok": True, "id": int(r.scalar()), "valor": valor, "turno": t}


async def listar_lancamentos(db: AsyncSession, mes: int, ano: int) -> dict[str, Any]:
    await ensure_e_seed(db)
    rows = await db.execute(text(
        """SELECT l.id, l.data, d.nome, l.funcao, l.posto, l.turno, l.valor, l.observacao
           FROM diaria_lancamentos l JOIN diaria_diaristas d ON d.id=l.diarista_id
           WHERE EXTRACT(MONTH FROM l.data)=:m AND EXTRACT(YEAR FROM l.data)=:a
           ORDER BY l.data, d.nome"""), {"m": mes, "a": ano})
    itens = [{"id": r[0], "data": r[1].isoformat(), "diarista": r[2], "funcao": r[3],
              "posto": r[4], "turno": r[5], "valor": float(r[6]), "observacao": r[7]}
             for r in rows.all()]
    return {"mes": mes, "ano": ano, "total_lancamentos": len(itens),
            "total_valor": sum(i["valor"] for i in itens), "itens": itens}


async def excluir_lancamento(db: AsyncSession, lancamento_id: int) -> dict[str, Any]:
    await ensure_e_seed(db)
    await db.execute(text("DELETE FROM diaria_lancamentos WHERE id=:id AND status='lancado'"), {"id": lancamento_id})
    await db.commit()
    return {"ok": True}


# ── Resumo por diarista (a lista de pagamento do dia 15) ──────────────────────
async def resumo_diarista(db: AsyncSession, mes: int, ano: int) -> dict[str, Any]:
    await ensure_e_seed(db)
    rows = await db.execute(text(
        """SELECT d.id, d.nome, l.funcao, COUNT(*) AS qtd, COALESCE(SUM(l.valor),0) AS valor,
                  d.pix, d.cpf
           FROM diaria_lancamentos l JOIN diaria_diaristas d ON d.id=l.diarista_id
           WHERE EXTRACT(MONTH FROM l.data)=:m AND EXTRACT(YEAR FROM l.data)=:a
           GROUP BY d.id, d.nome, l.funcao, d.pix, d.cpf
           ORDER BY d.nome, l.funcao"""), {"m": mes, "a": ano})
    itens = [{"diarista_id": r[0], "diarista": r[1], "funcao": r[2], "qtd_diarias": int(r[3]),
              "valor": float(r[4]), "tem_pix": bool(r[5]), "tem_cpf": bool(r[6])} for r in rows.all()]
    # total por pessoa (soma de todas as funções) — o que cai no PIX
    por_pessoa: dict[int, dict[str, Any]] = {}
    for i in itens:
        p = por_pessoa.setdefault(i["diarista_id"], {"diarista": i["diarista"], "valor": 0.0, "qtd": 0,
                                                      "tem_pix": i["tem_pix"], "tem_cpf": i["tem_cpf"]})
        p["valor"] += i["valor"]; p["qtd"] += i["qtd_diarias"]
    return {"mes": mes, "ano": ano, "por_funcao": itens,
            "por_pessoa": list(por_pessoa.values()),
            "total": sum(i["valor"] for i in itens),
            "total_diarias": sum(i["qtd_diarias"] for i in itens)}


async def resumo_gerencial(db: AsyncSession, mes: int, ano: int) -> dict[str, Any]:
    """Resumos por posto e por função (visão gerencial / BI)."""
    await ensure_e_seed(db)
    por_posto = [{"posto": r[0], "qtd": int(r[1]), "valor": float(r[2])} for r in (await db.execute(text(
        """SELECT posto, COUNT(*), SUM(valor) FROM diaria_lancamentos
           WHERE EXTRACT(MONTH FROM data)=:m AND EXTRACT(YEAR FROM data)=:a GROUP BY posto ORDER BY SUM(valor) DESC"""),
        {"m": mes, "a": ano})).all()]
    por_funcao = [{"funcao": r[0], "qtd": int(r[1]), "valor": float(r[2])} for r in (await db.execute(text(
        """SELECT funcao, COUNT(*), SUM(valor) FROM diaria_lancamentos
           WHERE EXTRACT(MONTH FROM data)=:m AND EXTRACT(YEAR FROM data)=:a GROUP BY funcao ORDER BY SUM(valor) DESC"""),
        {"m": mes, "a": ano})).all()]
    return {"mes": mes, "ano": ano, "por_posto": por_posto, "por_funcao": por_funcao}


# ── Cadastro de diarista (completar CPF obrigatório + PIX) ────────────────────
async def atualizar_diarista(db: AsyncSession, diarista_id: int, cpf: str | None = None,
                             pix: str | None = None, nome: str | None = None) -> dict[str, Any]:
    await ensure_e_seed(db)
    sets, params = [], {"id": diarista_id}
    if cpf is not None:
        sets.append("cpf=:cpf"); params["cpf"] = cpf
    if pix is not None:
        sets.append("pix=:pix"); params["pix"] = pix
    if nome:
        sets.append("nome=:nome"); params["nome"] = nome
    if not sets:
        return {"ok": False, "mensagem": "Nada para atualizar."}
    await db.execute(text(f"UPDATE diaria_diaristas SET {', '.join(sets)} WHERE id=:id"), params)
    await db.commit()
    return {"ok": True}


async def criar_diarista(db: AsyncSession, nome: str, cpf: str | None = None, pix: str | None = None) -> dict[str, Any]:
    await ensure_e_seed(db)
    r = await db.execute(text(
        "INSERT INTO diaria_diaristas (nome, cpf, pix) VALUES (:n,:c,:p) ON CONFLICT (lower(nome)) DO NOTHING RETURNING id"),
        {"n": nome, "c": cpf, "p": pix})
    row = r.first()
    await db.commit()
    return {"ok": True, "id": int(row[0]) if row else None, "ja_existia": row is None}
