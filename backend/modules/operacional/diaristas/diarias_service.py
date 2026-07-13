"""Diárias de diaristas — modelo da planilha do Jordan (DIARISTAS_MARCO_2026).

Cadastros (Operacional): funções, turnos, postos/condomínios, tabela de preços (Função|Turno→valor),
diaristas. Gonzaga LANÇA a diária escolhendo tudo em lista suspensa — o valor sai automático da
tabela de preços. O RESUMO por diarista vira o lote a pagar (Financeiro, dia 15).

Tudo pré-cadastrado (seed da planilha real): 6 funções, 8 preços, ~10 postos, 32 diaristas.
"""
from __future__ import annotations

import logging
import re
from datetime import date as _date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── Validação de cadastro (CPF/PIX/contato) — NUNCA fabricar dado ────────────
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def normalizar_cpf(cpf: str | None) -> str:
    """Só dígitos."""
    return re.sub(r"\D", "", cpf or "")


def cpf_valido(cpf: str | None) -> bool:
    """Valida CPF pelos dígitos verificadores (módulo 11). Rejeita sequências repetidas."""
    d = normalizar_cpf(cpf)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for i in (9, 10):
        soma = sum(int(d[j]) * ((i + 1) - j) for j in range(i))
        dv = (soma * 10) % 11
        if dv == 10:
            dv = 0
        if dv != int(d[i]):
            return False
    return True


def telefone_valido(telefone: str | None) -> bool:
    """Telefone plausível: 10 a 13 dígitos (DDD+número, com ou sem +55)."""
    dig = re.sub(r"\D", "", telefone or "")
    return 10 <= len(dig) <= 13


def validar_pix(pix: str | None) -> tuple[str | None, str | None]:
    """Valida o FORMATO da chave PIX por tipo. Retorna (chave_normalizada, erro).

    Tipos aceitos: CPF (11 dígitos válidos), telefone (+55..., 10-13 dígitos),
    e-mail, chave aleatória (UUID). NUNCA deriva/preenche chave sozinho.
    """
    c = (pix or "").strip()
    if not c:
        return None, "Chave PIX é obrigatória — sem ela o diarista fica impagável. Peça a chave ao diarista."
    if "@" in c:
        if _EMAIL_RE.match(c):
            return c.lower(), None
        return None, f"Chave PIX '{c}' não é um e-mail válido."
    if _UUID_RE.match(c):
        return c.lower(), None
    dig = re.sub(r"\D", "", c)
    if c.startswith("+"):
        if 10 <= len(dig) <= 13:
            return "+" + dig, None
        return None, f"Chave PIX telefone '{c}' inválida — use +55 + DDD + número (10 a 13 dígitos)."
    if len(dig) == 11 and dig == c.replace(".", "").replace("-", "").replace(" ", ""):
        if cpf_valido(dig):
            return dig, None
        return None, (f"Chave PIX '{c}' tem 11 dígitos mas não é um CPF válido (dígitos verificadores "
                      "não conferem). Se for telefone, informe com +55 na frente.")
    if len(dig) in (10, 12, 13) and dig == re.sub(r"[\s()\-.]", "", c):
        return "+" + dig if len(dig) in (12, 13) else dig, None
    if len(dig) == 14 and dig == re.sub(r"[./\-\s]", "", c):
        return None, "Chave PIX CNPJ não é aceita para diarista (pessoa física) — use CPF, telefone, e-mail ou chave aleatória."
    return None, (f"Chave PIX '{c}' com formato não reconhecido. Aceitos: CPF (11 dígitos válidos), "
                  "telefone (+55 + DDD + número), e-mail ou chave aleatória (UUID).")

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
    # contato do diarista (colunas novas — idempotente)
    "ALTER TABLE diaria_diaristas ADD COLUMN IF NOT EXISTS telefone VARCHAR(20)",
    "ALTER TABLE diaria_diaristas ADD COLUMN IF NOT EXISTS email VARCHAR(200)",
]


# Guard de processo: o DDL (CREATE TABLE IF NOT EXISTS) pega AccessExclusiveLock
# mesmo com a tabela já existente — rodar a CADA request causa DEADLOCK sob
# concorrência e derrubava o worker (502 no site inteiro). Roda uma vez por processo.
_SCHEMA_READY = False


async def ensure_e_seed(db: AsyncSession) -> None:
    """Cria as tabelas e SEMEIA os cadastros da planilha (idempotente — só se vazio).

    Idempotente por PROCESSO: após a 1ª execução bem-sucedida, vira no-op (as
    tabelas já existem e estão semeadas). Evita o AccessExclusiveLock por request
    que causava deadlock. Se o DDL falhar (ex.: deadlock na 1ª corrida concorrente),
    faz rollback e não marca pronto — a próxima chamada tenta de novo, sem crashar.
    """
    global _SCHEMA_READY  # noqa: PLW0603
    if _SCHEMA_READY:
        return
    try:
        for ddl in _DDL:
            await db.execute(text(ddl))
    except Exception:  # noqa: BLE001
        await db.rollback()
        raise
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
    _SCHEMA_READY = True


# ── Cadastros (para as listas suspensas) ─────────────────────────────────────
async def cadastros(db: AsyncSession) -> dict[str, Any]:
    """Tudo que o Gonzaga seleciona em lista suspensa + a tabela de preços."""
    await ensure_e_seed(db)
    funcoes = [r[0] for r in (await db.execute(text("SELECT nome FROM diaria_funcoes WHERE ativo ORDER BY nome"))).all()]
    turnos = [r[0] for r in (await db.execute(text("SELECT nome FROM diaria_turnos WHERE ativo ORDER BY id"))).all()]
    postos = [r[0] for r in (await db.execute(text("SELECT nome FROM diaria_postos WHERE ativo ORDER BY nome"))).all()]
    todos = (await db.execute(text(
        "SELECT id, nome, cpf, pix, telefone, email, COALESCE(ativo, TRUE) FROM diaria_diaristas ORDER BY nome"))).all()
    # dropdown de lançamento: SÓ ativos (inativo não recebe diária nova)
    diaristas = [{"id": r[0], "nome": r[1], "tem_pix": bool((r[3] or "").strip()), "tem_cpf": bool((r[2] or "").strip())}
                 for r in todos if r[6]]
    # gestão de cadastro: TODOS (com flag ativo), dados completos — tela interna
    diaristas_gestao = [{"id": r[0], "nome": r[1], "cpf": r[2], "pix": r[3], "telefone": r[4],
                         "email": r[5], "ativo": bool(r[6]),
                         "tem_pix": bool((r[3] or "").strip()), "tem_cpf": bool((r[2] or "").strip())}
                        for r in todos]
    precos = [{"funcao": r[0], "turno": r[1], "valor": float(r[2])}
              for r in (await db.execute(text("SELECT funcao, turno, valor FROM diaria_precos WHERE ativo ORDER BY funcao, turno"))).all()]
    return {"funcoes": funcoes, "turnos": turnos, "postos": postos, "diaristas": diaristas,
            "diaristas_gestao": diaristas_gestao, "precos": precos}


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


async def listar_lancamentos(db: AsyncSession, mes: int | None = None, ano: int | None = None,
                             data: str | None = None) -> dict[str, Any]:
    """Lançamentos do mês (mes+ano) OU de um dia exato (data=YYYY-MM-DD). `data` tem precedência."""
    await ensure_e_seed(db)
    if data:
        dref = _date.fromisoformat(data) if isinstance(data, str) else data
        where, params = "l.data = :d", {"d": dref}
        mes, ano = dref.month, dref.year
    else:
        where, params = "EXTRACT(MONTH FROM l.data)=:m AND EXTRACT(YEAR FROM l.data)=:a", {"m": mes, "a": ano}
    rows = await db.execute(text(
        f"""SELECT l.id, l.data, d.nome, l.funcao, l.posto, l.turno, l.valor, l.observacao
           FROM diaria_lancamentos l JOIN diaria_diaristas d ON d.id=l.diarista_id
           WHERE {where}
           ORDER BY l.data, d.nome"""), params)
    itens = [{"id": r[0], "data": r[1].isoformat(), "diarista": r[2], "funcao": r[3],
              "posto": r[4], "turno": r[5], "valor": float(r[6]), "observacao": r[7]}
             for r in rows.all()]
    out: dict[str, Any] = {"mes": mes, "ano": ano, "total_lancamentos": len(itens),
                           "total_valor": sum(i["valor"] for i in itens), "itens": itens}
    if data:
        out["data"] = dref.isoformat()
    return out


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


# ── Cadastro de diarista (CPF + PIX válidos obrigatórios; contato) ────────────
async def atualizar_diarista(db: AsyncSession, diarista_id: int, cpf: str | None = None,
                             pix: str | None = None, nome: str | None = None,
                             telefone: str | None = None, email: str | None = None,
                             ativo: bool | None = None) -> dict[str, Any]:
    """Atualiza nome/cpf/pix/telefone/email/ativo com validação. NÃO permite limpar CPF/PIX
    (viraria cadastro impagável). Inativar = ativo=false (some dos dropdowns de lançamento)."""
    await ensure_e_seed(db)
    atual = (await db.execute(text(
        "SELECT id, telefone, email FROM diaria_diaristas WHERE id=:id"), {"id": diarista_id})).first()
    if not atual:
        return {"ok": False, "http_status": 404, "mensagem": f"Diarista {diarista_id} não encontrado."}

    sets, params = [], {"id": diarista_id}
    if cpf is not None:
        cpf_n = normalizar_cpf(cpf)
        if not cpf_n:
            return {"ok": False, "mensagem": "Não é permitido limpar o CPF — sem CPF o diarista fica impagável."}
        if not cpf_valido(cpf_n):
            return {"ok": False, "mensagem": f"CPF '{cpf}' inválido (dígitos verificadores não conferem). Confira o documento com o diarista."}
        sets.append("cpf=:cpf"); params["cpf"] = cpf_n
    if pix is not None:
        if not (pix or "").strip():
            return {"ok": False, "mensagem": "Não é permitido limpar a chave PIX — sem PIX o diarista fica impagável."}
        pix_n, erro = validar_pix(pix)
        if erro:
            return {"ok": False, "mensagem": erro}
        sets.append("pix=:pix"); params["pix"] = pix_n
    if nome:
        sets.append("nome=:nome"); params["nome"] = nome.strip()
    if telefone is not None:
        tel = (telefone or "").strip()
        if tel:
            if not telefone_valido(tel):
                return {"ok": False, "mensagem": f"Telefone '{telefone}' inválido — use DDD + número (10 a 13 dígitos)."}
            sets.append("telefone=:tel"); params["tel"] = tel
        else:
            # limpar telefone só se sobrar e-mail (novo ou existente) — exige ao menos 1 contato
            email_final = (email or "").strip() if email is not None else (atual[2] or "").strip()
            if not email_final:
                return {"ok": False, "mensagem": "Não é possível remover o telefone: o diarista ficaria sem nenhum contato (informe um e-mail antes)."}
            sets.append("telefone=NULL")
    if email is not None:
        em = (email or "").strip()
        if em:
            if not _EMAIL_RE.match(em):
                return {"ok": False, "mensagem": f"E-mail '{email}' inválido."}
            sets.append("email=:email"); params["email"] = em.lower()
        else:
            tel_final = (telefone or "").strip() if telefone is not None else (atual[1] or "").strip()
            if not tel_final:
                return {"ok": False, "mensagem": "Não é possível remover o e-mail: o diarista ficaria sem nenhum contato (informe um telefone antes)."}
            sets.append("email=NULL")
    if ativo is not None:
        sets.append("ativo=:ativo"); params["ativo"] = bool(ativo)
    if not sets:
        return {"ok": False, "mensagem": "Nada para atualizar."}
    await db.execute(text(f"UPDATE diaria_diaristas SET {', '.join(sets)} WHERE id=:id"), params)
    await db.commit()
    return {"ok": True}


async def criar_diarista(db: AsyncSession, nome: str, cpf: str | None = None, pix: str | None = None,
                         telefone: str | None = None, email: str | None = None) -> dict[str, Any]:
    """Cadastra diarista. OBRIGATÓRIOS: nome, CPF válido (módulo 11), chave PIX com formato
    plausível e ao menos um contato (telefone OU e-mail). NUNCA fabrica/deriva dado."""
    await ensure_e_seed(db)
    nome = (nome or "").strip()
    if not nome:
        return {"ok": False, "mensagem": "Nome é obrigatório."}
    cpf_n = normalizar_cpf(cpf)
    if not cpf_n:
        return {"ok": False, "mensagem": "CPF é obrigatório no cadastro — sem CPF o diarista fica impagável. Peça o documento ao diarista."}
    if not cpf_valido(cpf_n):
        return {"ok": False, "mensagem": f"CPF '{cpf}' inválido (dígitos verificadores não conferem). Confira o documento com o diarista — nunca chute."}
    pix_n, erro = validar_pix(pix)
    if erro:
        return {"ok": False, "mensagem": erro}
    tel = (telefone or "").strip() or None
    em = (email or "").strip() or None
    if not tel and not em:
        return {"ok": False, "mensagem": "Informe pelo menos um contato: telefone ou e-mail."}
    if tel and not telefone_valido(tel):
        return {"ok": False, "mensagem": f"Telefone '{telefone}' inválido — use DDD + número (10 a 13 dígitos)."}
    if em and not _EMAIL_RE.match(em):
        return {"ok": False, "mensagem": f"E-mail '{email}' inválido."}
    r = await db.execute(text(
        """INSERT INTO diaria_diaristas (nome, cpf, pix, telefone, email)
           VALUES (:n,:c,:p,:t,:e) ON CONFLICT (lower(nome)) DO NOTHING RETURNING id"""),
        {"n": nome, "c": cpf_n, "p": pix_n, "t": tel, "e": em.lower() if em else None})
    row = r.first()
    await db.commit()
    return {"ok": True, "id": int(row[0]) if row else None, "ja_existia": row is None}


async def remover_diarista(db: AsyncSession, diarista_id: int) -> dict[str, Any]:
    """Apaga o diarista. Se ele já tem lançamentos de diária (FK/histórico), NÃO apaga de
    verdade (perderia o histórico e violaria a FK) — INATIVA (ativo=false), somem das listas.
    Sem histórico → apaga a linha. Nunca destrói dado de pagamento."""
    await ensure_e_seed(db)
    existe = (await db.execute(text(
        "SELECT nome FROM diaria_diaristas WHERE id=:id"), {"id": diarista_id})).first()
    if not existe:
        return {"ok": False, "http_status": 404, "mensagem": f"Diarista {diarista_id} não encontrado."}
    tem_lanc = (await db.execute(text(
        "SELECT 1 FROM diaria_lancamentos WHERE diarista_id=:id LIMIT 1"), {"id": diarista_id})).first()
    if tem_lanc:
        await db.execute(text("UPDATE diaria_diaristas SET ativo=false WHERE id=:id"), {"id": diarista_id})
        await db.commit()
        return {"ok": True, "apagado": False, "inativado": True,
                "mensagem": f"'{existe[0]}' tem lançamentos de diária no histórico — foi INATIVADO "
                            "(sai das listas) em vez de apagado, para preservar o histórico de pagamento."}
    await db.execute(text("DELETE FROM diaria_diaristas WHERE id=:id"), {"id": diarista_id})
    await db.commit()
    return {"ok": True, "apagado": True, "inativado": False, "mensagem": f"Diarista '{existe[0]}' removido."}
