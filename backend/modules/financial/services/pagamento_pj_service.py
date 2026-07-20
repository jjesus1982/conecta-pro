"""Folha de PAGAMENTO PJ (prestadores) — Multi-CNPJ.

PJ NÃO entram na folha CLT (holerite/INSS/FGTS/eSocial) — são pagos contra nota fiscal
via PIX, pelo banco da EMPRESA de origem:
- Eletrônica → Inter: disparo AUTOMÁTICO por chave PIX, com gate de OTP (igual diaristas).
- Patrimonial → Cora: a API do Cora NÃO paga por chave PIX (adapter levanta NotImplemented),
  então gera-se a LISTA pra pagar no app do Cora; a conciliação vem pelo extrato.

DINHEIRO QUE SAI: o disparo real (Inter) passa SEMPRE por confirmar=True + OTP válido.
Nota fiscal: de competência >= FRONTEIRA_NF (2026-08), o item fica 'aguardando_nf' até a
nota do prestador ser marcada — só então entra no lote pagável.

Reaproveita a máquina de OTP dos diaristas: tabela `inter_lote_otp`, e-mail do Jordan
(`_enviar_otp_email`) e o InterAdapter.enviar_pix. Salário fixo + VA/VT (R$22+R$10 = R$32/
dia útil). Diego e afins podem ser pagos pela conta de outro (pagamento_via_employee_id).
"""

from __future__ import annotations

import calendar
import logging
import os
import re
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import psycopg2
import psycopg2.extras
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

FRONTEIRA_NF = "2026-08"          # a partir daqui, exige nota fiscal
VA_DIA = float(os.getenv("PJ_VA_DIA", "22.00"))   # vale alimentação/refeição por dia útil
VT_DIA = float(os.getenv("PJ_VT_DIA", "10.00"))   # vale transporte por dia útil
VA_VT_DIA = VA_DIA + VT_DIA
LIMITE_LOTE = float(os.getenv("CONECTA_LIMITE_DIARIO_PAGAMENTOS", "100000.00"))
OTP_TTL_SECONDS = int(os.getenv("CONECTA_PAYMENT_OTP_TTL_SECONDS", "600"))

_BANCO = {"conecta_eletronica": ("Inter", "077"), "conecta_patrimonial": ("Cora", "403")}


def _url() -> str:
    return re.sub(r"\+asyncpg|\+psycopg2?", "", os.getenv("DATABASE_URL", ""))


def dias_uteis(mes: int, ano: int) -> int:
    """Dias úteis (seg-sex) do mês. Feriados não descontados (aproximação p/ VA/VT)."""
    n = calendar.monthrange(ano, mes)[1]
    return sum(1 for d in range(1, n + 1) if date(ano, mes, d).weekday() < 5)


def _tipo_pix(chave: str) -> str:
    c = (chave or "").strip()
    d = re.sub(r"\D", "", c)
    if "@" in c:
        return "EMAIL"
    if len(d) == 11 and c == d:
        return "CPF"
    if len(d) == 14 and c == d:
        return "CNPJ"
    if c.startswith("+") or (len(d) in (12, 13) and d.startswith("55")):
        return "TELEFONE"
    if len(d) in (10, 11):
        return "TELEFONE"
    return "EVP"


# ─────────────────────────────────────────────────────────── cálculo (preview) ──
def calcular_folha_pj(mes: int, ano: int, va_vt_dia: float = VA_VT_DIA) -> dict:
    """Calcula a folha PJ do mês, roteada por banco. NÃO grava nem paga (preview puro)."""
    comp = f"{ano:04d}-{mes:02d}"
    exige_nf = comp >= FRONTEIRA_NF
    dias = dias_uteis(mes, ano)
    conn = psycopg2.connect(_url())
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT e.id, e.nome, e.cpf, e.salario_base, e.pix_key, "
            "       e.pagamento_via_employee_id, e.status, emp.slug AS empresa "
            "FROM employees e JOIN empresas emp ON emp.id = e.empresa_id "
            "WHERE e.tipo_contrato = 'pj' AND LOWER(e.status) IN ('pj_ativo','pj_pendente') "
            "ORDER BY emp.slug, e.nome"
        )
        pjs = cur.fetchall()
    finally:
        conn.close()

    riders: dict[str, list] = {}
    for p in pjs:
        if p["pagamento_via_employee_id"]:
            riders.setdefault(str(p["pagamento_via_employee_id"]), []).append(p)

    linhas = []
    for p in pjs:
        if p["pagamento_via_employee_id"]:
            continue
        salario = float(p["salario_base"] or 0)
        meus = riders.get(str(p["id"]), [])
        soma_riders = sum(float(r["salario_base"] or 0) for r in meus)
        va_vt = round(dias * va_vt_dia * (1 + len(meus)), 2)  # VA/VT de cada pessoa do PIX
        total = round(salario + soma_riders + va_vt, 2)
        banco, codigo = _BANCO.get(p["empresa"], ("?", "?"))
        linhas.append({
            "employee_id": str(p["id"]), "nome": p["nome"], "cpf": p["cpf"],
            "empresa": p["empresa"], "banco": banco, "banco_codigo": codigo,
            "pix_key": p["pix_key"], "pix_pronto": bool(p["pix_key"]),
            "salario": salario,
            "junto": [{"nome": r["nome"], "valor": float(r["salario_base"] or 0)} for r in meus],
            "va_vt": va_vt, "total": total, "nf_exigida": exige_nf,
        })
    linhas.sort(key=lambda x: (x["empresa"], x["nome"]))
    total_geral = round(sum(l["total"] for l in linhas), 2)
    por_banco: dict[str, float] = {}
    for l in linhas:
        por_banco[l["banco"]] = round(por_banco.get(l["banco"], 0.0) + l["total"], 2)
    return {
        "competencia": comp, "dias_uteis": dias, "va_vt_dia": va_vt_dia,
        "exige_nota_fiscal": exige_nf, "pagamentos": linhas,
        "total_geral": total_geral, "por_banco": por_banco,
        "sem_pix_cadastrado": [l["nome"] for l in linhas if not l["pix_pronto"]],
        "gate": "OTP humano obrigatório antes de disparar (dinheiro que sai)",
    }


# ───────────────────────────────────────────────────────────── persistência ──
async def _ensure(db: AsyncSession) -> None:
    await db.execute(text(
        """CREATE TABLE IF NOT EXISTS financial_pagamentos_pj (
            id SERIAL PRIMARY KEY,
            competencia VARCHAR(7) NOT NULL,
            employee_id UUID,
            empresa_slug VARCHAR(40),
            banco VARCHAR(20),
            beneficiario VARCHAR(200),
            cpf VARCHAR(20),
            pix_key TEXT,
            salario NUMERIC,
            va_vt NUMERIC,
            valor NUMERIC NOT NULL,
            nf_exigida BOOLEAN DEFAULT FALSE,
            nf_ok BOOLEAN DEFAULT FALSE,
            status VARCHAR(20) NOT NULL DEFAULT 'a_revisar',
            descricao TEXT,
            e2e_ref VARCHAR(80),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (competencia, beneficiario)
        )"""))
    await db.execute(text(
        """CREATE TABLE IF NOT EXISTS inter_lote_otp (
            id SERIAL PRIMARY KEY, lote_id VARCHAR(64), code VARCHAR(6),
            expires_at TIMESTAMPTZ, used BOOLEAN DEFAULT FALSE, created_at TIMESTAMPTZ DEFAULT NOW()
        )"""))
    await db.commit()


def _status_de(l: dict) -> str:
    """Deriva o status do item pela regra: sem_pix → aguardando_nf → pagar_no_app (Cora) → a_revisar."""
    if not l["pix_pronto"]:
        return "sem_pix"
    if l["nf_exigida"]:  # de agosto em diante, sem nota não paga
        return "aguardando_nf"
    if l["banco"] == "Cora":
        return "pagar_no_app"   # Cora não paga por chave via API
    return "a_revisar"          # Inter, com PIX e sem pendência de NF


async def programar_folha_pj(db: AsyncSession, mes: int, ano: int,
                             va_vt_dia: float = VA_VT_DIA) -> dict:
    """Materializa a folha PJ do mês em financial_pagamentos_pj (idempotente por
    competência+beneficiário; NÃO sobrescreve item já 'pago'). NÃO move dinheiro."""
    await _ensure(db)
    folha = calcular_folha_pj(mes, ano, va_vt_dia)
    comp = folha["competencia"]
    novos = atualizados = 0
    for l in folha["pagamentos"]:
        st = _status_de(l)
        res = await db.execute(text(
            """INSERT INTO financial_pagamentos_pj
                 (competencia, employee_id, empresa_slug, banco, beneficiario, cpf, pix_key,
                  salario, va_vt, valor, nf_exigida, status, descricao)
               VALUES (:comp,:eid,:emp,:banco,:ben,:cpf,:pix,:sal,:vavt,:val,:nfe,:st,:desc)
               ON CONFLICT (competencia, beneficiario) DO UPDATE SET
                  pix_key=EXCLUDED.pix_key, valor=EXCLUDED.valor, salario=EXCLUDED.salario,
                  va_vt=EXCLUDED.va_vt, banco=EXCLUDED.banco, empresa_slug=EXCLUDED.empresa_slug,
                  nf_exigida=EXCLUDED.nf_exigida,
                  status=CASE WHEN financial_pagamentos_pj.status='pago'
                              THEN financial_pagamentos_pj.status ELSE EXCLUDED.status END,
                  updated_at=NOW()
               WHERE financial_pagamentos_pj.status <> 'pago'
               RETURNING (xmax=0) AS inserted"""),
            {"comp": comp, "eid": l["employee_id"], "emp": l["empresa"], "banco": l["banco"],
             "ben": l["nome"], "cpf": l["cpf"], "pix": l["pix_key"], "sal": l["salario"],
             "vavt": l["va_vt"], "val": l["total"], "nfe": l["nf_exigida"], "st": st,
             "desc": f"Folha PJ {comp} — {l['empresa']}"})
        row = res.first()
        if row is not None:
            novos += 1 if row[0] else 0
            atualizados += 0 if row[0] else 1
    await db.commit()
    return {"ok": True, "competencia": comp, "programados": novos, "atualizados": atualizados,
            "resumo": folha["por_banco"], "total": folha["total_geral"]}


async def listar_lote(db: AsyncSession, mes: int, ano: int) -> dict:
    await _ensure(db)
    comp = f"{ano:04d}-{mes:02d}"
    rows = (await db.execute(text(
        "SELECT id, empresa_slug, banco, beneficiario, pix_key, valor, salario, va_vt, "
        "nf_exigida, nf_ok, status FROM financial_pagamentos_pj "
        "WHERE competencia=:c ORDER BY banco, beneficiario"), {"c": comp})).mappings().all()
    itens = [dict(r) for r in rows]
    for i in itens:
        i["valor"] = float(i["valor"] or 0)
        i["salario"] = float(i["salario"] or 0)
        i["va_vt"] = float(i["va_vt"] or 0)
    inter = [i for i in itens if i["banco"] == "Inter"]
    cora = [i for i in itens if i["banco"] == "Cora"]
    return {
        "competencia": comp, "itens": itens,
        "inter_pagaveis": [i for i in inter if i["status"] == "a_revisar"],
        "cora_lista_app": [i for i in cora if i["status"] in ("pagar_no_app", "aguardando_nf")],
        "pendencias": [i for i in itens if i["status"] in ("sem_pix", "aguardando_nf")],
        "total": round(sum(i["valor"] for i in itens), 2),
    }


# ─────────────────────────────────────────────────────────────── OTP (Inter) ──
async def gerar_otp_lote(db: AsyncSession, mes: int, ano: int) -> dict:
    """Gera 1 OTP (e-mail ao Jordan) que libera o lote INTER (Eletrônica). Não move dinheiro."""
    await _ensure(db)
    comp = f"{ano:04d}-{mes:02d}"
    r = (await db.execute(text(
        "SELECT COUNT(*) n, COALESCE(SUM(valor),0) t FROM financial_pagamentos_pj "
        "WHERE competencia=:c AND banco='Inter' AND status='a_revisar'"), {"c": comp})).mappings().first()
    n, total = int(r["n"]), float(r["t"])
    if n == 0:
        return {"ok": False, "mensagem": "Nenhum item Inter elegível (a_revisar com PIX)."}
    if total > LIMITE_LOTE:
        return {"ok": False, "mensagem": f"Lote R$ {total:.2f} excede o limite R$ {LIMITE_LOTE:.2f}."}
    lote_id = str(uuid.uuid4())
    code = f"{secrets.randbelow(900000) + 100000}"
    exp = datetime.now(UTC) + timedelta(seconds=OTP_TTL_SECONDS)
    await db.execute(text(
        "INSERT INTO inter_lote_otp (lote_id, code, expires_at, used) VALUES (:l,:c,:e,false)"),
        {"l": lote_id, "c": code, "e": exp})
    await db.commit()
    email = os.getenv("JORDAN_EMAIL", "jjesus@conectamais.pro")
    try:
        from modules.integrations.inter.services.payment_service import _enviar_otp_email
        await _enviar_otp_email(email, code, total, f"folha PJ {comp} (Inter)", f"{n} prestador(es)")
    except Exception as exc:  # noqa: BLE001
        logger.warning("OTP folha PJ: falha ao enviar email: %s", exc)
    return {"ok": True, "lote_id": lote_id, "quantidade": n, "total": total,
            "message": f"Código enviado para {email}", "expires_in_seconds": OTP_TTL_SECONDS}


async def _validar_otp(db: AsyncSession, lote_id: str, code: str) -> None:
    now = datetime.now(UTC)
    row = (await db.execute(text(
        "SELECT id, code FROM inter_lote_otp WHERE lote_id=:l AND used=false AND expires_at>:n "
        "ORDER BY created_at DESC LIMIT 1"), {"l": lote_id, "n": now})).mappings().first()
    if not row:
        raise ValueError("Código expirado ou inexistente. Gere um novo.")
    if str(row["code"]) != str(code).strip():
        raise ValueError("Código OTP incorreto.")
    await db.execute(text("UPDATE inter_lote_otp SET used=true WHERE id=:i"), {"i": row["id"]})


async def executar_lote(db: AsyncSession, mes: int, ano: int, *, confirmar: bool = False,
                        otp_code: str | None = None, lote_id: str | None = None) -> dict:
    """Paga o lote INTER (Eletrônica) via PIX. confirmar=False → PRÉVIA. confirmar=True + OTP
    válido → envia os PIX (DINHEIRO SAI). Os itens Cora ficam na lista pra pagar no app."""
    await _ensure(db)
    comp = f"{ano:04d}-{mes:02d}"
    rows = (await db.execute(text(
        "SELECT id, beneficiario, pix_key, valor FROM financial_pagamentos_pj "
        "WHERE competencia=:c AND banco='Inter' AND status='a_revisar' ORDER BY id"),
        {"c": comp})).mappings().all()
    itens = [dict(i) for i in rows]
    total = round(sum(float(i["valor"]) for i in itens), 2)
    prev = {"competencia": comp, "itens": len(itens), "total": total, "limite": LIMITE_LOTE,
            "dentro_do_limite": total <= LIMITE_LOTE,
            "beneficiarios": [{"nome": i["beneficiario"], "valor": float(i["valor"])} for i in itens]}
    if not confirmar:
        prev["preview"] = True
        prev["aviso"] = "Prévia — nada foi pago. Gere o OTP e confirme para pagar o lote Inter."
        return prev
    if not itens:
        return {"ok": False, "mensagem": "Nenhum item Inter elegível."}
    if total > LIMITE_LOTE:
        return {"ok": False, "mensagem": f"Lote R$ {total:.2f} excede o limite R$ {LIMITE_LOTE:.2f}."}
    if not lote_id or not otp_code:
        return {"ok": False, "otp_requerido": True, "mensagem": "OTP obrigatório. Gere o código e informe-o."}
    try:
        await _validar_otp(db, lote_id, otp_code)
    except ValueError as exc:
        return {"ok": False, "otp_invalido": True, "mensagem": str(exc)}
    except Exception:  # noqa: BLE001
        await db.rollback()
        return {"ok": False, "otp_invalido": True, "mensagem": "Código de lote inválido. Gere um novo."}

    from modules.integrations.banking.adapters.base import BankCredentials
    from modules.integrations.banking.adapters.inter import InterAdapter
    adapter = InterAdapter(BankCredentials(
        client_id=os.getenv("INTER_CLIENT_ID", ""), client_secret=os.getenv("INTER_CLIENT_SECRET", ""),
        certificate_path=os.getenv("INTER_CERT_PATH"), private_key_path=os.getenv("INTER_KEY_PATH"),
        agency=os.getenv("INTER_AGENCY"), account=os.getenv("INTER_ACCOUNT"),
        environment=os.getenv("INTER_ENVIRONMENT", "production")))
    pagos, falhas = [], []
    try:
        for i in itens:
            try:
                resp = await adapter.enviar_pix(
                    chave=i["pix_key"], tipo_chave=_tipo_pix(i["pix_key"]),
                    valor=Decimal(str(i["valor"])), nome_recebedor=i["beneficiario"],
                    descricao=f"Folha PJ {comp} (Conecta Mais Eletrônica)")
                ref = (resp or {}).get("endToEndId") or (resp or {}).get("codigoSolicitacao") or (resp or {}).get("id") or "ok"
                await db.execute(text(
                    "UPDATE financial_pagamentos_pj SET status='pago', e2e_ref=:r, updated_at=NOW() WHERE id=:id"),
                    {"r": str(ref)[:80], "id": i["id"]})
                pagos.append({"nome": i["beneficiario"], "valor": float(i["valor"]), "ref": str(ref)[:80]})
            except Exception as e:  # noqa: BLE001
                logger.error("Falha ao pagar PJ %s: %s", i["id"], e)
                falhas.append({"nome": i["beneficiario"], "erro": str(e)[:160]})
        await db.commit()
    finally:
        try:
            await adapter.close()
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "competencia": comp, "pagos": pagos, "falhas": falhas,
            "total_pago": round(sum(p["valor"] for p in pagos), 2)}


async def marcar_nota_fiscal(db: AsyncSession, item_id: int, ok: bool = True) -> dict:
    """Marca a nota fiscal do prestador como recebida — libera o item p/ o lote (se Inter)."""
    await _ensure(db)
    novo = ("a_revisar" if ok else "aguardando_nf")
    await db.execute(text(
        "UPDATE financial_pagamentos_pj SET nf_ok=:ok, "
        "status=CASE WHEN :ok AND banco='Inter' THEN 'a_revisar' "
        "            WHEN :ok AND banco='Cora' THEN 'pagar_no_app' "
        "            ELSE 'aguardando_nf' END, updated_at=NOW() "
        "WHERE id=:id AND status<>'pago'"), {"ok": ok, "id": item_id})
    await db.commit()
    return {"ok": True, "item_id": item_id, "nf_ok": ok, "status": novo}
