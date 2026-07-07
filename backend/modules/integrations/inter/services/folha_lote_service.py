"""Pagamento de folha EM LOTE via Banco Inter — 1 OTP libera o posto inteiro.

Jordan escolhe o posto → confere a lista (chave + líquido, cada chave verificada por histórico) →
UM código OTP libera todos os PIX do lote. Sem trava artificial de valor (a conta Inter do Jordan
não tem limite prático para folha), mas com LOG completo, OTP humano obrigatório e trava
ANTI-DUPLICIDADE: quem já recebeu ~o líquido nesta competência (no extrato) NÃO entra no lote.

DINHEIRO QUE SAI — só executa com o OTP correto (ação humana). Nunca paga sozinho.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

OTP_TTL_SECONDS = 600


def _tipo_pix(chave: str, tipo: str | None = None) -> str:
    if tipo:
        return tipo.upper()
    c = (chave or "").strip()
    if "@" in c:
        return "EMAIL"
    dig = "".join(ch for ch in c if ch.isdigit())
    if len(dig) == 14:
        return "CNPJ"
    if len(dig) == 11:
        return "CPF"
    if len(c) >= 32:
        return "EVP"
    if c.startswith("+") or len(dig) in (12, 13):
        return "TELEFONE"
    return "CPF"


async def _ja_pago_competencia(db: AsyncSession, nome: str, valor: float, competencia: str) -> dict | None:
    """Detecta se a pessoa JÁ recebeu ~esse valor nesta competência (evita pagar 2x).
    Casa por nome (1º+último token) no extrato, valor ±R$1, dentro do mês da competência."""
    import unicodedata

    def _n(s: str) -> str:
        s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
        return " ".join(s.upper().split())

    toks = _n(nome).split()
    if not toks:
        return None
    try:
        mm, aaaa = competencia.split("/")
        # folha da competência costuma ser paga no mês seguinte; olhamos competência e mês seguinte
        ini = date(int(aaaa), int(mm), 1)
        fim = (ini + timedelta(days=75))
    except Exception:  # noqa: BLE001
        return None
    row = (await db.execute(text("""
        SELECT data_lancamento, valor,
               COALESCE(detalhes_destinatario->>'nome', regexp_replace(descricao,'^.*-','')) AS receb
        FROM inter_transactions
        WHERE tipo_operacao='D'
          AND data_lancamento BETWEEN :ini AND :fim
          AND abs(valor - :val) <= 1.00
          AND upper(translate(COALESCE(detalhes_destinatario->>'nome',descricao),
                'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇáàâãäéèêëíìîïóòôõöúùûüç',
                'AAAAAEEEEIIIIOOOOOUUUUCAAAAAEEEEIIIIOOOOOUUUUC'))
              LIKE '%' || :p || '%' || :u || '%'
        ORDER BY data_lancamento DESC LIMIT 1
    """), {"ini": ini, "fim": fim, "val": valor, "p": toks[0], "u": toks[-1]})).mappings().first()
    if row:
        return {"data": str(row["data_lancamento"]), "valor": float(row["valor"]), "receb": (row["receb"] or "").strip()}
    return None


async def preparar_lote(
    db: AsyncSession, posto: str, competencia: str,
    itens: list[dict], user_id: str,
) -> dict[str, Any]:
    """Cria o lote (inter_payments status='preparado', categoria='folha', mesmo lote_id).
    Pula quem já foi pago nesta competência (anti-duplicidade). Não move dinheiro."""
    # sincroniza o extrato recente (best-effort) para a trava anti-duplicidade enxergar
    # pagamentos de hoje/ontem (ex.: Oscar pago agora no Villa dos Pássaros).
    try:
        from modules.integrations.inter.inter_sync_service import InterSyncService
        await InterSyncService(db).sincronizar_extrato(dias=5)
    except Exception as exc:  # noqa: BLE001
        logger.warning("preparar_lote: sync de extrato falhou (segue mesmo assim): %s", exc)

    lote_id = str(uuid.uuid4())
    hoje = date.today()
    criados, pulados = [], []
    for it in itens:
        nome = (it.get("nome") or "").strip()
        chave = (it.get("chave") or "").strip()
        valor = float(it.get("valor") or 0)
        if not chave or valor <= 0:
            pulados.append({"nome": nome, "motivo": "sem chave ou valor"})
            continue
        dup = await _ja_pago_competencia(db, nome, valor, competencia)
        if dup:
            pulados.append({"nome": nome, "motivo": f"já pago em {dup['data']} (R$ {dup['valor']:.2f})"})
            continue
        pid = str(uuid.uuid4())
        dest = {"chave": chave, "tipo_chave": _tipo_pix(chave, it.get("tipo_chave")), "nome": nome}
        await db.execute(text("""
            INSERT INTO inter_payments
              (id, payment_type, destinatario, valor, data_pagamento, status, prepared_by,
               observacoes, categoria, lote_id, created_at, updated_at)
            VALUES (:id,'pix',CAST(:dest AS jsonb),:valor,:dt,'preparado',:uid,
               :obs,'folha',:lote,now(),now())
        """), {"id": pid, "dest": json.dumps(dest), "valor": valor, "dt": hoje,
               "uid": user_id, "obs": f"Folha {competencia} — {nome} ({posto})", "lote": lote_id})
        criados.append({"id": pid, "nome": nome, "chave": chave, "valor": valor})
    await db.commit()
    total = sum(c["valor"] for c in criados)
    return {
        "lote_id": lote_id, "posto": posto, "competencia": competencia,
        "itens": criados, "total": total, "quantidade": len(criados),
        "pulados": pulados,
        "mensagem": f"Lote preparado: {len(criados)} pagamentos, total R$ {total:.2f}. "
                    f"{len(pulados)} pulados." if criados else "Nenhum pagamento a preparar (todos já pagos ou sem chave).",
    }


async def gerar_otp_lote(db: AsyncSession, lote_id: str, user_id: str) -> dict[str, Any]:
    """Gera UM OTP para o lote inteiro e envia por email ao Jordan."""
    rows = (await db.execute(text(
        "SELECT count(*) n, COALESCE(sum(valor),0) total FROM inter_payments "
        "WHERE lote_id=:l AND status='preparado'"), {"l": lote_id})).mappings().first()
    if not rows or rows["n"] == 0:
        raise ValueError("Lote sem pagamentos preparados.")
    code = f"{secrets.randbelow(900000) + 100000}"
    exp = datetime.now(UTC) + timedelta(seconds=OTP_TTL_SECONDS)
    await db.execute(text("UPDATE inter_lote_otp SET used=true WHERE lote_id=:l AND used=false"), {"l": lote_id})
    await db.execute(text(
        "INSERT INTO inter_lote_otp (lote_id, code, expires_at, used) VALUES (:l,:c,:e,false)"),
        {"l": lote_id, "c": code, "e": exp})
    await db.commit()
    email = os.getenv("JORDAN_EMAIL", "jjesus@conectamais.pro")
    try:
        from modules.integrations.inter.services.payment_service import _enviar_otp_email
        await _enviar_otp_email(email, code, float(rows["total"]), "folha (lote)",
                                f"{rows['n']} funcionários")
    except Exception as exc:  # noqa: BLE001
        logger.warning("falha ao enviar email OTP lote: %s", exc)
    logger.info("folha lote gerar_otp: lote=%s n=%s total=%.2f email=%s", lote_id, rows["n"], float(rows["total"]), email)
    return {"lote_id": lote_id, "quantidade": rows["n"], "total": float(rows["total"]),
            "message": f"OTP enviado para {email}", "expires_in_seconds": OTP_TTL_SECONDS}


async def executar_lote(db: AsyncSession, lote_id: str, otp_code: str, user_id: str) -> dict[str, Any]:
    """Valida o OTP e paga TODOS os PIX do lote via Inter. Sem trava de valor; log completo.
    Cada pagamento vira executado + guarda o e2e/id do Inter → depois o loop de conciliação
    casa cada saída com a categoria 'folha' automaticamente."""
    now = datetime.now(UTC)
    otp = (await db.execute(text("""
        SELECT id, code FROM inter_lote_otp
        WHERE lote_id=:l AND used=false AND expires_at > :now
        ORDER BY created_at DESC LIMIT 1
    """), {"l": lote_id, "now": now})).mappings().first()
    if not otp:
        raise ValueError("Nenhum OTP válido para este lote. Gere um novo.")
    if otp["code"] != str(otp_code):
        raise ValueError("Código OTP incorreto.")
    await db.execute(text("UPDATE inter_lote_otp SET used=true WHERE id=:id"), {"id": str(otp["id"])})

    itens = (await db.execute(text(
        "SELECT id, destinatario, valor FROM inter_payments "
        "WHERE lote_id=:l AND status='preparado' ORDER BY created_at"), {"l": lote_id})).mappings().all()
    if not itens:
        await db.commit()
        return {"ok": False, "mensagem": "Nenhum pagamento preparado no lote."}

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
            dest = i["destinatario"] if isinstance(i["destinatario"], dict) else json.loads(i["destinatario"])
            nome = dest.get("nome", ""); chave = dest.get("chave", "")
            try:
                resp = await adapter.enviar_pix(
                    chave=chave, tipo_chave=_tipo_pix(chave, dest.get("tipo_chave")),
                    valor=Decimal(str(i["valor"])), nome_recebedor=nome,
                    descricao="Folha (Conecta PRO)")
                if resp.get("success") is False:
                    raise RuntimeError(resp.get("detail") or resp.get("error") or "Inter recusou")
                ref = resp.get("codigoSolicitacao") or resp.get("endToEndId") or ""
                if not ref:
                    raise RuntimeError("Inter não retornou código de solicitação (não confirmou)")
                from modules.integrations.inter.services.payment_service import _map_status_inter
                st = _map_status_inter(resp.get("status"))
                await db.execute(text("""
                    UPDATE inter_payments SET status=:st, executed_at=now(),
                      approved_by=:uid, approval_otp_used=:otp, inter_payment_id=:ref,
                      inter_response=CAST(:resp AS jsonb), updated_at=now()
                    WHERE id=:id
                """), {"st": st, "uid": user_id, "otp": str(otp_code), "ref": str(ref)[:60],
                       "resp": json.dumps(resp), "id": str(i["id"])})
                pagos.append({"id": str(i["id"]), "nome": nome, "valor": float(i["valor"]),
                              "ref": str(ref)[:60], "status": st})
            except Exception as e:  # noqa: BLE001
                logger.error("folha lote: falha ao pagar %s: %s", nome, e)
                await db.execute(text(
                    "UPDATE inter_payments SET status='erro', cancel_reason=:m, updated_at=now() WHERE id=:id"),
                    {"m": str(e)[:200], "id": str(i["id"])})
                falhas.append({"nome": nome, "valor": float(i["valor"]), "erro": str(e)[:150]})
        await db.commit()
    finally:
        try:
            await adapter.close()
        except Exception:  # noqa: BLE001
            pass
    aguardando = sum(1 for p in pagos if p.get("status") == "aguardando_aprovacao")
    logger.info("folha lote executar: lote=%s pagos=%d falhas=%d aguardando=%d", lote_id, len(pagos), len(falhas), aguardando)
    return {"ok": True, "lote_id": lote_id, "pagos": len(pagos), "falhas": len(falhas),
            "aguardando_aprovacao": aguardando,
            "total_pago": sum(p["valor"] for p in pagos), "detalhe_pagos": pagos, "detalhe_falhas": falhas,
            "aviso": (f"{aguardando} pagamento(s) CRIADOS no Inter aguardando aprovação no app do Inter "
                      "(o dinheiro só sai após aprovar). Considere desativar a exigência de aprovação "
                      "de pagamentos por API nas configurações do Inter.") if aguardando else None}
