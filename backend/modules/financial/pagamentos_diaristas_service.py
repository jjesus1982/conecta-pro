"""Pagamentos de diaristas (VT+VR diário) — elo Operacional → Financeiro.

Quando o gerente operacional (Eliziel Gonzaga) programa a escala de diaristas de um dia,
o Financeiro DEIXA PROGRAMADO o pagamento do benefício diário (VT R$10 + VR R$22 = R$32)
para cada diarista escalado — com a chave PIX — numa fila que o Jordan REVISA e paga EM LOTE
(via Banco Inter, com aprovação OTP). Também cobre o caso do CLT que cobre a falta de outro.

Este é o lado INBOUND da comunicação bidirecional Operacional↔Financeiro: a ação operacional
(escala) vira pagamento programado no Financeiro. NUNCA paga sozinho — o Jordan revisa e aprova.
"""
from __future__ import annotations

import logging
import os
from datetime import date as _date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Benefício diário (configurável). VT + VR = 32,00.
VALE_TRANSPORTE = 10.00
VALE_ALIMENTACAO = 22.00
VALOR_VT_VR = VALE_TRANSPORTE + VALE_ALIMENTACAO  # 32.00

_DDL = """
CREATE TABLE IF NOT EXISTS financial_pagamentos_diaristas (
    id               BIGSERIAL PRIMARY KEY,
    data_referencia  DATE        NOT NULL,
    diarist_id       UUID,
    beneficiario     TEXT        NOT NULL,
    cpf              VARCHAR(14),
    pix_key          TEXT,
    valor            NUMERIC(12,2) NOT NULL DEFAULT 32.00,
    tipo             VARCHAR(20) NOT NULL DEFAULT 'vt_vr',   -- vt_vr | cobertura_clt
    origem           VARCHAR(30) NOT NULL DEFAULT 'escala',  -- escala | manual
    schedule_id      UUID,
    condominio_id    UUID,
    status           VARCHAR(20) NOT NULL DEFAULT 'a_revisar', -- a_revisar|aprovado|pago|cancelado|sem_pix
    inter_payment_id BIGINT,
    descricao        TEXT,
    created_by       VARCHAR(64),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pag_diarista_dia
    ON financial_pagamentos_diaristas (data_referencia, diarist_id, tipo)
    WHERE diarist_id IS NOT NULL;
"""


# Guard de processo: DDL (CREATE TABLE IF NOT EXISTS / ALTER) pega AccessExclusiveLock
# mesmo com a tabela existente — rodar por request causava DEADLOCK sob concorrência
# (crash do worker, 502). Roda uma vez por processo; se falhar, rollback e re-tenta depois.
_SCHEMA_READY = False


async def _ensure(db: AsyncSession) -> None:
    global _SCHEMA_READY  # noqa: PLW0603
    if _SCHEMA_READY:
        return
    try:
        for stmt in _DDL.strip().split(";\n"):
            s = stmt.strip()
            if s:
                await db.execute(text(s))
        # competência (MM/AAAA) para o pagamento mensal de diárias (FLUXO 2, dia 15)
        await db.execute(text(
            "ALTER TABLE financial_pagamentos_diaristas ADD COLUMN IF NOT EXISTS competencia VARCHAR(7)"))
        await db.commit()
    except Exception:  # noqa: BLE001
        await db.rollback()
        raise
    _SCHEMA_READY = True


async def programar_diarias_mensais(db: AsyncSession, mes: int, ano: int,
                                    data_pagamento: str | None = None,
                                    user_id: str | None = None) -> dict[str, Any]:
    """Gera o LOTE do dia 15 a partir do resumo mensal de diárias (FLUXO 2).

    Soma as diárias trabalhadas de cada diarista no mês (Operacional) → cria 1 pagamento por
    pessoa (valor = total do mês) no Financeiro, status 'a_revisar' (ou 'sem_pix'). Idempotente
    por (competência, diarista). O Jordan revisa e paga em lote via `executar_lote`.
    """
    await _ensure(db)
    comp = f"{int(mes):02d}/{int(ano)}"
    # data do pagamento: default dia 15 do mês SEGUINTE à competência
    if data_pagamento:
        dpag = _date.fromisoformat(data_pagamento)
    else:
        m2, a2 = (mes + 1, ano) if mes < 12 else (1, ano + 1)
        dpag = _date(a2, m2, 15)
    # total por diarista no mês (com pix/cpf do cadastro de diárias)
    rows = await db.execute(text(
        """SELECT d.nome, d.cpf, d.pix, COUNT(*) AS qtd, COALESCE(SUM(l.valor),0) AS valor
           FROM diaria_lancamentos l JOIN diaria_diaristas d ON d.id = l.diarista_id
           WHERE EXTRACT(MONTH FROM l.data)=:m AND EXTRACT(YEAR FROM l.data)=:a
           GROUP BY d.nome, d.cpf, d.pix HAVING COALESCE(SUM(l.valor),0) > 0
           ORDER BY d.nome"""), {"m": mes, "a": ano})
    pessoas = rows.mappings().all()
    novos = sem_pix = 0
    for p in pessoas:
        pix = (p.get("pix") or "").strip()
        # idempotência: já existe o pagamento dessa competência p/ essa pessoa?
        ex = await db.execute(text(
            "SELECT id FROM financial_pagamentos_diaristas WHERE competencia=:c AND beneficiario=:b AND tipo='diaria_mensal'"),
            {"c": comp, "b": p["nome"]})
        if ex.first():
            continue
        status = "a_revisar" if pix else "sem_pix"
        if not pix:
            sem_pix += 1
        await db.execute(text(
            """INSERT INTO financial_pagamentos_diaristas
                 (data_referencia, beneficiario, cpf, pix_key, valor, tipo, origem, status,
                  competencia, descricao, created_by)
               VALUES (:d,:ben,:cpf,:pix,:valor,'diaria_mensal','diarias', :st, :comp, :desc, :uid)"""),
            {"d": dpag, "ben": p["nome"], "cpf": p.get("cpf"), "pix": pix or None,
             "valor": float(p["valor"]), "st": status, "comp": comp,
             "desc": f"Diárias {comp}: {int(p['qtd'])} diária(s) trabalhada(s)",
             "uid": str(user_id) if user_id else None})
        novos += 1
    await db.commit()
    lote = await listar(db, data=dpag.isoformat())
    return {
        "competencia": comp, "data_pagamento": dpag.isoformat(),
        "diaristas": len(pessoas), "programados_novos": novos, "sem_pix": sem_pix,
        "total_a_pagar": sum(x["valor"] for x in lote if x["status"] in ("a_revisar", "aprovado")),
        "lote": lote,
    }


async def programar_do_dia(db: AsyncSession, data: str, user_id: str | None = None) -> dict[str, Any]:
    """Lê a escala de diaristas de `data` (YYYY-MM-DD) e PROGRAMA o pagamento VT+VR de cada um.

    Idempotente: não duplica o mesmo diarista/dia/tipo. Marca 'sem_pix' quem não tem chave PIX
    cadastrada (Gonzaga precisa completar o cadastro). Retorna o lote programado.
    """
    await _ensure(db)
    dref = _date.fromisoformat(data) if isinstance(data, str) else data
    # diaristas escalados no dia (join com o cadastro p/ pegar nome + pix)
    rows = await db.execute(text(
        """
        SELECT s.id AS schedule_id, s.diarist_id, s.condominio_id,
               d.nome, d.cpf, d.pix
        FROM diarist_schedules s
        JOIN diarists d ON d.id = s.diarist_id
        WHERE s.data_trabalho = :data
          AND COALESCE(s.ativo, TRUE) = TRUE
          AND lower(COALESCE(s.status::text,'')) NOT IN ('cancelado','cancelled')
        """), {"data": dref})
    escalados = rows.mappings().all()

    programados = 0
    sem_pix = 0
    for e in escalados:
        pix = (e.get("pix") or "").strip()
        status = "a_revisar" if pix else "sem_pix"
        if not pix:
            sem_pix += 1
        res = await db.execute(text(
            """
            INSERT INTO financial_pagamentos_diaristas
                (data_referencia, diarist_id, beneficiario, cpf, pix_key, valor, tipo, origem,
                 schedule_id, condominio_id, status, descricao, created_by)
            VALUES
                (:data, :did, :nome, :cpf, :pix, :valor, 'vt_vr', 'escala',
                 :sid, :cond, :status, :desc, :uid)
            ON CONFLICT (data_referencia, diarist_id, tipo) WHERE diarist_id IS NOT NULL
            DO NOTHING
            RETURNING id
            """),
            {"data": dref, "did": e["diarist_id"], "nome": e["nome"], "cpf": e.get("cpf"),
             "pix": pix or None, "valor": VALOR_VT_VR, "sid": e["schedule_id"],
             "cond": e.get("condominio_id"), "status": status,
             "desc": f"VT R$ {VALE_TRANSPORTE:.2f} + VR R$ {VALE_ALIMENTACAO:.2f} (diária {data})",
             "uid": str(user_id) if user_id else None})
        if res.first():
            programados += 1
    await db.commit()
    lote = await listar(db, data=data)
    return {
        "data": data,
        "escalados": len(escalados),
        "programados_novos": programados,
        "sem_pix": sem_pix,
        "total_a_pagar": sum(float(x["valor"]) for x in lote if x["status"] in ("a_revisar", "aprovado")),
        "lote": lote,
    }


# ── ELO DO DIA (FLUXO 2 diário): diária LANÇADA hoje → VT+VR programado hoje ──
async def listar_lancados_do_dia(db: AsyncSession, data: str | _date) -> dict[str, Any]:
    """Diaristas com diária LANÇADA no dia (diaria_lancamentos × diaria_diaristas), com a flag
    `ja_programado_vt_vr` (já existe VT+VR origem='diarias_dia' não cancelado p/ o dia).
    Tudo lido do banco real — dia sem lançamento devolve itens=[] honesto."""
    await _ensure(db)
    dref = _date.fromisoformat(data) if isinstance(data, str) else data
    if not (await db.execute(text("SELECT to_regclass('public.diaria_lancamentos')"))).scalar():
        return {"data": dref.isoformat(), "total_diaristas": 0, "total_lancamentos": 0, "itens": [],
                "aviso": "Nenhuma diária lançada ainda (tabela de lançamentos não existe)."}
    rows = await db.execute(text(
        """SELECT l.id AS lancamento_id, l.diarista_id, d.nome, l.funcao, l.posto, l.turno,
                  l.valor, d.cpf, d.pix, d.telefone
           FROM diaria_lancamentos l JOIN diaria_diaristas d ON d.id = l.diarista_id
           WHERE l.data = :d
           ORDER BY d.nome, l.id"""), {"d": dref})
    lanc = rows.mappings().all()
    prog = await db.execute(text(
        """SELECT lower(beneficiario) FROM financial_pagamentos_diaristas
           WHERE data_referencia = :d AND tipo = 'vt_vr' AND origem = 'diarias_dia'
             AND status <> 'cancelado'"""), {"d": dref})
    ja_programados = {r[0] for r in prog.all()}
    itens = [{
        "lancamento_id": r["lancamento_id"], "diarista_id": r["diarista_id"], "nome": r["nome"],
        "funcao": r["funcao"], "posto": r["posto"], "turno": r["turno"],
        "valor_diaria": float(r["valor"]),
        "tem_pix": bool((r["pix"] or "").strip()), "tem_cpf": bool((r["cpf"] or "").strip()),
        "telefone": r["telefone"],
        "ja_programado_vt_vr": (r["nome"] or "").lower() in ja_programados,
    } for r in lanc]
    return {"data": dref.isoformat(),
            "total_diaristas": len({i["diarista_id"] for i in itens}),
            "total_lancamentos": len(itens), "itens": itens}


async def programar_vt_vr_dos_lancados(db: AsyncSession, data: str | _date,
                                       created_by: str | None = None) -> dict[str, Any]:
    """Programa o VT+VR (R$32) de cada diarista DISTINTO com diária LANÇADA no dia.

    origem='diarias_dia' — NUNCA mistura com origem='escala' (FLUXO 1): são fontes distintas.
    Idempotente por (data_referencia, beneficiario, tipo='vt_vr', origem='diarias_dia',
    status<>'cancelado'). Sem PIX no cadastro → status 'sem_pix' (NUNCA fabrica chave)."""
    await _ensure(db)
    dref = _date.fromisoformat(data) if isinstance(data, str) else data
    if not (await db.execute(text("SELECT to_regclass('public.diaria_lancamentos')"))).scalar():
        return {"data": dref.isoformat(), "programados_novos": 0, "ja_programados": 0, "sem_pix": 0,
                "total_a_pagar_do_dia": 0.0, "itens": [],
                "aviso": "Nenhuma diária lançada ainda (tabela de lançamentos não existe)."}
    # 1 linha por diarista DISTINTO lançado no dia (dados reais do cadastro)
    rows = await db.execute(text(
        """SELECT d.id AS diarista_id, d.nome, d.cpf, d.pix,
                  array_agg(l.id ORDER BY l.id) AS lanc_ids,
                  array_agg(DISTINCT l.funcao || ' @ ' || l.posto) AS servicos,
                  COUNT(*) AS qtd
           FROM diaria_lancamentos l JOIN diaria_diaristas d ON d.id = l.diarista_id
           WHERE l.data = :d
           GROUP BY d.id, d.nome, d.cpf, d.pix
           ORDER BY d.nome"""), {"d": dref})
    pessoas = rows.mappings().all()
    novos = ja = sem_pix = 0
    itens: list[dict[str, Any]] = []
    for p in pessoas:
        # idempotência manual (diaristas FLUXO 2 têm id INT → fora do índice único de diarist_id UUID)
        ex = await db.execute(text(
            """SELECT id FROM financial_pagamentos_diaristas
               WHERE data_referencia = :d AND lower(beneficiario) = lower(:b)
                 AND tipo = 'vt_vr' AND origem = 'diarias_dia' AND status <> 'cancelado'
               LIMIT 1"""), {"d": dref, "b": p["nome"]})
        if ex.first():
            ja += 1
            itens.append({"diarista_id": p["diarista_id"], "nome": p["nome"],
                          "valor": VALOR_VT_VR, "resultado": "ja_programado"})
            continue
        pix = (p.get("pix") or "").strip()
        status = "a_revisar" if pix else "sem_pix"
        if not pix:
            sem_pix += 1
        lanc_ids = ", ".join(f"#{i}" for i in (p["lanc_ids"] or []))
        servicos = "; ".join(p["servicos"] or [])
        await db.execute(text(
            """INSERT INTO financial_pagamentos_diaristas
                 (data_referencia, beneficiario, cpf, pix_key, valor, tipo, origem, status,
                  descricao, created_by)
               VALUES (:d, :ben, :cpf, :pix, :valor, 'vt_vr', 'diarias_dia', :st, :desc, :uid)"""),
            {"d": dref, "ben": p["nome"], "cpf": p.get("cpf"), "pix": pix or None,
             "valor": VALOR_VT_VR, "st": status,
             "desc": (f"VT R$ {VALE_TRANSPORTE:.2f} + VR R$ {VALE_ALIMENTACAO:.2f} — "
                      f"diária(s) lançada(s) em {dref.isoformat()} (lançamentos {lanc_ids}: {servicos})"),
             "uid": str(created_by) if created_by else None})
        novos += 1
        itens.append({"diarista_id": p["diarista_id"], "nome": p["nome"], "valor": VALOR_VT_VR,
                      "resultado": "programado" if pix else "programado_sem_pix", "status": status})
    await db.commit()
    total = (await db.execute(text(
        """SELECT COALESCE(SUM(valor), 0) FROM financial_pagamentos_diaristas
           WHERE data_referencia = :d AND tipo = 'vt_vr' AND origem = 'diarias_dia'
             AND status IN ('a_revisar', 'aprovado')"""), {"d": dref})).scalar()
    return {"data": dref.isoformat(), "programados_novos": novos, "ja_programados": ja,
            "sem_pix": sem_pix, "total_a_pagar_do_dia": float(total or 0), "itens": itens}


async def adicionar_manual(db: AsyncSession, data: str, beneficiario: str, pix_key: str,
                           quantidade: int = 1, valor: float | None = None, tipo: str = "cobertura_clt",
                           cpf: str | None = None, user_id: str | None = None) -> dict[str, Any]:
    """Adiciona um pagamento avulso ao lote.

    Casos reais:
    - CLT que cobriu a falta de outro → recebe VT+VR (quantidade=1).
    - Líder que leva N ajudantes → recebe o VT+VR de todos num PIX só (quantidade=N → R$32×N).
      Ex.: Francisco leva 2 ajudantes → quantidade=2 → R$64.
    """
    await _ensure(db)
    dref = _date.fromisoformat(data) if isinstance(data, str) else data
    q = max(1, int(quantidade or 1))
    val = float(valor) if valor is not None else VALOR_VT_VR * q
    desc = (f"VT+VR de {q} ajudante(s) (líder recebe o benefício da equipe)" if tipo == "cobertura_clt" and q > 1
            else "Cobertura de falta (CLT) — VT+VR" if tipo == "cobertura_clt"
            else f"VT+VR x{q}" if q > 1 else "Pagamento avulso")
    r = await db.execute(text(
        """INSERT INTO financial_pagamentos_diaristas
             (data_referencia, beneficiario, cpf, pix_key, valor, tipo, origem, status, descricao, created_by)
           VALUES (:data,:ben,:cpf,:pix,:valor,:tipo,'manual',
                   :st, :desc, :uid) RETURNING id"""),
        {"data": dref, "ben": beneficiario, "cpf": cpf, "pix": (pix_key or "").strip() or None,
         "valor": val, "tipo": tipo, "st": "a_revisar" if (pix_key or "").strip() else "sem_pix",
         "desc": desc, "uid": str(user_id) if user_id else None})
    await db.commit()
    return {"ok": True, "id": int(r.scalar()), "valor": val, "quantidade": q}


async def listar(db: AsyncSession, data: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    await _ensure(db)
    where = []
    params: dict[str, Any] = {}
    if data:
        where.append("data_referencia = :data")
        params["data"] = _date.fromisoformat(data) if isinstance(data, str) else data
    if status:
        where.append("status = :status"); params["status"] = status
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = await db.execute(text(
        f"""SELECT id, data_referencia, diarist_id, beneficiario, cpf, pix_key, valor, tipo,
                   origem, status, inter_payment_id, descricao, created_at
            FROM financial_pagamentos_diaristas {clause}
            ORDER BY data_referencia DESC, beneficiario"""), params)
    out = []
    for r in rows.mappings().all():
        out.append({
            "id": r["id"], "data_referencia": r["data_referencia"].isoformat() if r["data_referencia"] else None,
            "diarist_id": str(r["diarist_id"]) if r["diarist_id"] else None,
            "beneficiario": r["beneficiario"], "cpf": r["cpf"], "pix_key": r["pix_key"],
            "valor": float(r["valor"]), "tipo": r["tipo"], "origem": r["origem"], "status": r["status"],
            "inter_payment_id": r["inter_payment_id"], "descricao": r["descricao"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        })
    return out


async def resumo(db: AsyncSession) -> dict[str, Any]:
    """Resumo para o painel do Financeiro / CFO cross-módulo."""
    await _ensure(db)
    r = await db.execute(text(
        """SELECT
             COUNT(*) FILTER (WHERE status='a_revisar') AS a_revisar,
             COALESCE(SUM(valor) FILTER (WHERE status='a_revisar'),0) AS valor_a_revisar,
             COUNT(*) FILTER (WHERE status='sem_pix') AS sem_pix,
             COUNT(*) FILTER (WHERE status='pago') AS pagos
           FROM financial_pagamentos_diaristas"""))
    m = r.mappings().first() or {}
    return {
        "a_revisar_qtd": int(m.get("a_revisar") or 0),
        "a_revisar_valor": float(m.get("valor_a_revisar") or 0),
        "sem_pix_qtd": int(m.get("sem_pix") or 0),
        "pagos_qtd": int(m.get("pagos") or 0),
    }


# Trava de segurança do lote (dinheiro que sai). MESMA fonte da verdade do D7 avulso:
# .env CONECTA_LIMITE_DIARIO_PAGAMENTOS. Um único knob controla os dois limites.
LIMITE_LOTE_DIARIO = float(os.getenv("CONECTA_LIMITE_DIARIO_PAGAMENTOS", "5000.00"))


def _tipo_pix(chave: str) -> str:
    c = (chave or "").strip()
    if "@" in c:
        return "EMAIL"
    dig = "".join(ch for ch in c if ch.isdigit())
    if len(dig) == 14:
        return "CNPJ"
    if len(dig) == 11:
        return "CPF"          # diaristas usam CPF como chave
    if len(c) >= 32:
        return "EVP"          # chave aleatória
    if c.startswith("+") or len(dig) in (12, 13):
        return "TELEFONE"
    return "CPF"


async def executar_lote(
    db: AsyncSession, ids: list[int] | None = None, data: str | None = None,
    confirmar: bool = False, user_id: str | None = None,
) -> dict[str, Any]:
    """Paga o lote de diaristas via PIX (Banco Inter). confirmar=False → PRÉVIA (não envia).

    DINHEIRO QUE SAI — só executa com confirmar=True (ação humana). Trava: limite R$5.000/lote,
    só paga itens 'a_revisar' com PIX. Marca cada um 'pago' e guarda o e2e/id do Inter.
    """
    await _ensure(db)
    # seleciona o lote elegível
    where = ["status='a_revisar'", "pix_key IS NOT NULL"]
    params: dict[str, Any] = {}
    if ids:
        where.append("id = ANY(:ids)"); params["ids"] = ids
    if data:
        where.append("data_referencia = :data")
        params["data"] = _date.fromisoformat(data) if isinstance(data, str) else data
    rows = await db.execute(text(
        f"SELECT id, beneficiario, pix_key, valor FROM financial_pagamentos_diaristas "
        f"WHERE {' AND '.join(where)} ORDER BY id"), params)
    itens = rows.mappings().all()
    total = sum(float(i["valor"]) for i in itens)

    prev = {
        "itens": len(itens), "total": total, "limite": LIMITE_LOTE_DIARIO,
        "dentro_do_limite": total <= LIMITE_LOTE_DIARIO,
        "beneficiarios": [{"id": i["id"], "nome": i["beneficiario"], "valor": float(i["valor"])} for i in itens],
    }
    if not confirmar:
        prev["preview"] = True
        prev["aviso"] = "Prévia — nada foi pago. Envie com confirmar=true para pagar em lote."
        return prev
    if not itens:
        return {"ok": False, "mensagem": "Nenhum item elegível (a_revisar com PIX)."}
    if total > LIMITE_LOTE_DIARIO:
        return {"ok": False, "mensagem": f"Lote de R$ {total:.2f} excede o limite de R$ {LIMITE_LOTE_DIARIO:.2f}."}

    # ENVIO REAL via Inter (enviar_pix por item)
    import os as _os
    from decimal import Decimal
    from modules.integrations.banking.adapters.base import BankCredentials
    from modules.integrations.banking.adapters.inter import InterAdapter
    adapter = InterAdapter(BankCredentials(
        client_id=_os.getenv("INTER_CLIENT_ID", ""), client_secret=_os.getenv("INTER_CLIENT_SECRET", ""),
        certificate_path=_os.getenv("INTER_CERT_PATH"), private_key_path=_os.getenv("INTER_KEY_PATH"),
        agency=_os.getenv("INTER_AGENCY"), account=_os.getenv("INTER_ACCOUNT"),
        environment=_os.getenv("INTER_ENVIRONMENT", "production")))
    pagos, falhas = [], []
    try:
        for i in itens:
            try:
                resp = await adapter.enviar_pix(
                    chave=i["pix_key"], tipo_chave=_tipo_pix(i["pix_key"]),
                    valor=Decimal(str(i["valor"])), nome_recebedor=i["beneficiario"],
                    descricao="VT+VR diária (Conecta PRO)")
                ref = (resp or {}).get("endToEndId") or (resp or {}).get("codigoSolicitacao") or (resp or {}).get("id") or "ok"
                await db.execute(text(
                    "UPDATE financial_pagamentos_diaristas SET status='pago', descricao=descricao||' | e2e:'||:ref, updated_at=now() WHERE id=:id"),
                    {"ref": str(ref)[:60], "id": i["id"]})
                pagos.append({"id": i["id"], "nome": i["beneficiario"], "valor": float(i["valor"]), "ref": str(ref)[:60]})
            except Exception as e:  # noqa: BLE001
                logger.error("Falha ao pagar diarista %s: %s", i["id"], e)
                falhas.append({"id": i["id"], "nome": i["beneficiario"], "erro": str(e)[:120]})
        await db.commit()
    finally:
        try:
            await adapter.close()
        except Exception:
            pass
    return {"ok": True, "pagos": len(pagos), "falhas": len(falhas), "total_pago": sum(p["valor"] for p in pagos),
            "detalhe_pagos": pagos, "detalhe_falhas": falhas}


async def cancelar(db: AsyncSession, pagamento_id: int) -> dict[str, Any]:
    await _ensure(db)
    await db.execute(text(
        "UPDATE financial_pagamentos_diaristas SET status='cancelado', updated_at=now() "
        "WHERE id=:id AND status IN ('a_revisar','sem_pix')"), {"id": pagamento_id})
    await db.commit()
    return {"ok": True}


def _extrair_nome_pix(descricao: str) -> str | None:
    """Extrai o nome do beneficiário da descrição de um PIX enviado do extrato Inter."""
    import re
    d = (descricao or "").strip()
    if not d:
        return None
    m = re.search(r"Cp\s*:\s*\d+\s*-\s*(.+)$", d)
    nome = m.group(1) if m else None
    if not nome:
        m2 = re.search(r"-\s*[\d\s]*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]+)$", d)
        nome = m2.group(1) if m2 else None
    if not nome:
        return None
    nome = re.sub(r"^[\d\s]+", "", nome)
    nome = re.sub(r"\s+", " ", nome).strip().title()
    return nome if len(nome) >= 5 and not nome.replace(" ", "").isdigit() else None


async def sugestoes_cadastro_historico(db: AsyncSession, dias: int = 30, valor: float = VALOR_VT_VR) -> dict[str, Any]:
    """Sugere diaristas a CADASTRAR a partir do histórico real de PIX de R$32 (VT+VR).

    Read-only. O histórico traz o NOME (não o CPF/chave PIX) — então cada sugestão vira um
    cadastro que o Gonzaga completa com CPF (obrigatório) + chave PIX na estrutura existente.
    Não mostra quem já está cadastrado."""
    rows = await db.execute(text(
        """SELECT COALESCE(descricao, raw_payload->>'description','') AS d, COUNT(*) AS n
           FROM inter_transactions
           WHERE abs(valor)=:v AND data_lancamento >= CURRENT_DATE - make_interval(days => :dias)
           GROUP BY 1"""), {"v": valor, "dias": dias})
    por_nome: dict[str, int] = {}
    for r in rows.mappings().all():
        nome = _extrair_nome_pix(r["d"])
        if nome:
            por_nome[nome] = por_nome.get(nome, 0) + int(r["n"])
    # já cadastrados (por nome, case-insensitive)
    ex = await db.execute(text("SELECT lower(nome) FROM diarists"))
    cadastrados = {row[0] for row in ex.all()}
    sugestoes = [
        {"nome": n, "pagamentos_periodo": c, "ja_cadastrado": n.lower() in cadastrados}
        for n, c in sorted(por_nome.items(), key=lambda x: -x[1])
    ]
    novos = [s for s in sugestoes if not s["ja_cadastrado"]]
    return {
        "dias": dias, "valor_referencia": valor,
        "total_nomes": len(sugestoes), "a_cadastrar": len(novos),
        "sugestoes": sugestoes,
        "aviso": "O histórico traz o nome, não o CPF/chave PIX. Cadastre cada um (CPF obrigatório) e adicione a chave PIX.",
    }
