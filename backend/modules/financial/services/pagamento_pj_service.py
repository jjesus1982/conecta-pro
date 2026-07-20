"""Folha de PAGAMENTO PJ (prestadores) — Multi-CNPJ.

PJ NÃO entram na folha CLT (holerite/INSS/FGTS/eSocial) — são pagos contra nota fiscal
via PIX, pelo banco da EMPRESA de origem (Eletrônica→Inter, Patrimonial→Cora). Este
serviço CALCULA a folha PJ do mês (salário fixo + VA/VT só dias úteis), AGREGANDO quem é
pago pela conta de OUTRO (ex.: Diego → Eliziel: um PIX só, com os dois salários).

DINHEIRO QUE SAI: este serviço só CALCULA/PREVÊ, roteando cada pagamento pro banco certo.
O disparo do PIX passa SEMPRE pelo gate de OTP humano — nunca automático.

Nota fiscal: de competência >= FRONTEIRA_NF (2026-08), o prestador precisa emitir nota
antes de liberar o pagamento (marcado em `nf_exigida`; a checagem da nota é no gate).
"""

from __future__ import annotations

import calendar
import os
import re
from datetime import date

import psycopg2
import psycopg2.extras

# A partir desta competência (agosto/2026), exige emissão de nota fiscal do prestador.
FRONTEIRA_NF = "2026-08"

# Banco por empresa de origem (E7: bank_accounts.empresa_id segrega de verdade).
_BANCO = {"conecta_eletronica": ("Inter", "077"), "conecta_patrimonial": ("Cora", "403")}


def _url() -> str:
    return re.sub(r"\+asyncpg|\+psycopg2?", "", os.getenv("DATABASE_URL", ""))


def dias_uteis(mes: int, ano: int) -> int:
    """Dias úteis (seg-sex) do mês. Feriados NÃO são descontados aqui (aproximação p/ VA/VT)."""
    n = calendar.monthrange(ano, mes)[1]
    return sum(1 for d in range(1, n + 1) if date(ano, mes, d).weekday() < 5)


def calcular_folha_pj(mes: int, ano: int, va_vt_dia: float = 0.0) -> dict:
    """Calcula a folha PJ do mês, roteada por banco. NÃO dispara pagamento (só preview).

    va_vt_dia: valor do VA/VT por dia útil (0 até o Jordan confirmar a regra/valor).
    """
    comp = f"{ano:04d}-{mes:02d}"
    exige_nf = comp >= FRONTEIRA_NF
    dias = dias_uteis(mes, ano)

    conn = psycopg2.connect(_url())
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT e.id, e.nome, e.cpf, e.salario_base, e.pix_key, e.pix_key_type, "
            "       e.pagamento_via_employee_id, e.status, emp.slug AS empresa "
            "FROM employees e JOIN empresas emp ON emp.id = e.empresa_id "
            "WHERE e.tipo_contrato = 'pj' AND LOWER(e.status) IN ('pj_ativo','pj_pendente') "
            "ORDER BY emp.slug, e.nome"
        )
        pjs = cur.fetchall()
    finally:
        conn.close()

    # Riders: prestadores pagos pela conta de OUTRO (pagamento_via_employee_id).
    riders: dict[str, list] = {}
    for p in pjs:
        via = p["pagamento_via_employee_id"]
        if via:
            riders.setdefault(str(via), []).append(p)

    linhas = []
    for p in pjs:
        if p["pagamento_via_employee_id"]:
            continue  # é rider — o valor dele entra no total do PAGADOR
        salario = float(p["salario_base"] or 0)
        meus = riders.get(str(p["id"]), [])
        soma_riders = sum(float(r["salario_base"] or 0) for r in meus)
        va_vt = round(dias * va_vt_dia, 2)  # VA/VT só dias úteis
        total = round(salario + soma_riders + va_vt, 2)
        banco, codigo = _BANCO.get(p["empresa"], ("?", "?"))
        linhas.append({
            "nome": p["nome"], "empresa": p["empresa"], "banco": banco, "banco_codigo": codigo,
            "pix_key": p["pix_key"], "pix_pronto": bool(p["pix_key"]),
            "salario": salario,
            "junto": [{"nome": r["nome"], "valor": float(r["salario_base"] or 0)} for r in meus],
            "va_vt": va_vt, "total": total,
            "nf_exigida": exige_nf, "status_cadastro": p["status"],
        })

    linhas.sort(key=lambda x: (x["empresa"], x["nome"]))
    total_geral = round(sum(l["total"] for l in linhas), 2)
    por_banco: dict[str, float] = {}
    for l in linhas:
        por_banco[l["banco"]] = round(por_banco.get(l["banco"], 0.0) + l["total"], 2)
    sem_pix = [l["nome"] for l in linhas if not l["pix_pronto"]]

    return {
        "competencia": comp, "dias_uteis": dias, "va_vt_dia": va_vt_dia,
        "exige_nota_fiscal": exige_nf, "pagamentos": linhas,
        "total_geral": total_geral, "por_banco": por_banco,
        "sem_pix_cadastrado": sem_pix,  # aguardando autocadastro do prestador
        "gate": "OTP humano obrigatório antes de disparar (dinheiro que sai)",
    }
