"""Emite a cobrança BANCÁRIA de uma conta a receber que já existe.

Regra do dono (07/09/2026): boleto/PIX nasce no Conecta PRO, não no app do banco — a Eletrônica
cobra pelo Inter (boleto registrado com PIX na mesma emissão) e a Patrimonial pela Cora
(boleto + PIX). O gerador do dia 1 (`gerar_recebiveis`) cria a conta a receber a partir do
contrato; este serviço emite a cobrança para ESSA conta e grava o boleto/PIX nela — nada de
segunda conta paralela (o `recurring_billing_service` criava a própria e ficou sem uso).

Banco pela empresa credora da conta (`receivable_accounts.empresa_id`, que vem do contrato).
Idempotente: conta que já tem `boleto_id`/`pix_txid` não é reemitida. Não envia nada ao cliente —
emitir é registrar a cobrança no banco; comunicar é outro passo. Dinheiro não sai daqui.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from decimal import Decimal

from modules.financial.services.recurring_billing_service import (
    _build_inter_adapter,
    _chamar_cobranca_cora,
    _get_conn,
)

logger = logging.getLogger(__name__)

PATRIMONIAL_ID = "7d79ed12-d480-4906-b2e0-2b2c4d299bab"
_SQL_CONTA = """
    SELECT r.id::text, r.code, r.customer_name, r.customer_document, r.gross_value, r.net_value, r.due_date,
           r.description, r.status::text, r.empresa_id::text, r.boleto_id, r.pix_txid,
           c.email, c.address_street, c.address_number, c.address_neighborhood, c.address_city,
           c.address_state, c.address_zipcode, c.document_number
    FROM receivable_accounts r
    LEFT JOIN clients c ON regexp_replace(coalesce(c.document_number,''), '\\D', '', 'g')
                          = regexp_replace(coalesce(r.customer_document,''), '\\D', '', 'g')
                         AND coalesce(r.customer_document,'') <> ''
    WHERE r.id::text = %s
"""


def _banco_da_conta(empresa_id: str | None) -> str:
    return "cora" if (empresa_id or "") == PATRIMONIAL_ID else "inter"


def _emitir_inter(conta: dict) -> dict:
    """Boleto registrado no Inter (cobrança v3) — devolve boleto_id, linha digitável e PIX copia-e-cola."""
    async def _run():
        adapter = _build_inter_adapter()
        try:
            return await adapter.generate_boleto(
                amount=Decimal(str(conta["valor"])), due_date=conta["vencimento"],
                payer_name=conta["nome"], payer_document=conta["documento"], description=conta["descricao"],
                payer_address=conta.get("rua"), payer_number=conta.get("numero"),
                payer_neighborhood=conta.get("bairro"), payer_city=conta.get("cidade"),
                payer_state=conta.get("uf"), payer_zip=conta.get("cep"),
            )
        finally:
            try:
                await adapter.close()
            except Exception:  # noqa: BLE001
                pass
    try:
        r = asyncio.run(_run())
        return {"success": True, "banco": "inter", "boleto_id": r.get("boleto_id") or "",
                "boleto_digitavel": r.get("digitable_line") or "", "boleto_url": r.get("pdf_url") or r.get("url") or "",
                "pix_copy_paste": r.get("pix_qrcode") or "", "txid": r.get("boleto_id") or "", "bruto": r}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "banco": "inter", "error": str(exc)[:300]}


def emitir(receivable_id: str, preview: bool = False) -> dict:
    """Emite (ou só mostra, com preview=True) a cobrança bancária de UMA conta a receber."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_SQL_CONTA, (receivable_id,))
            row = cur.fetchone()
    if not row:
        return {"ok": False, "erro": "conta a receber não encontrada"}
    (rid, code, nome, doc, bruto, liquido, venc, desc, status, empresa_id, boleto_id, pix_txid,
     email, rua, numero, bairro, cidade, uf, cep, doc_cli) = row
    banco = _banco_da_conta(empresa_id)
    documento = "".join(ch for ch in (doc or doc_cli or "") if ch.isdigit())
    valor = float(liquido or bruto or 0)
    conta = {"id": rid, "code": code or f"REC-{rid[:8]}", "nome": (nome or "cliente")[:60], "documento": documento,
             "valor": round(valor, 2), "vencimento": venc, "descricao": (desc or "Serviços")[:100],
             "email": email, "rua": rua, "numero": numero, "bairro": bairro, "cidade": cidade, "uf": uf, "cep": cep}
    base = {"ok": False, "id": rid, "cliente": conta["nome"], "valor": conta["valor"], "vencimento": str(venc),
            "banco": banco, "preview": preview}
    if status not in ("pendente", "parcial"):
        return {**base, "erro": f"conta com status {status!r} — só se emite cobrança de conta em aberto"}
    if boleto_id or pix_txid:
        return {**base, "ok": True, "situacao": "ja_emitida", "boleto_id": boleto_id, "pix_txid": pix_txid}
    if not documento or len(documento) not in (11, 14):
        return {**base, "erro": "cliente sem CPF/CNPJ válido na conta e no cadastro"}
    if not venc or venc < date.today():
        return {**base, "erro": f"vencimento {venc} já passou — ajuste a data antes de emitir"}
    if valor < 5.0:
        return {**base, "erro": "valor mínimo de cobrança bancária é R$ 5,00"}
    if preview:
        return {**base, "ok": True, "situacao": "preview", "documento": documento, "email": email}

    if banco == "cora":
        r = _chamar_cobranca_cora(conta["code"], conta["valor"], documento, conta["nome"], conta["descricao"],
                                  venc.isoformat())
    else:
        r = _emitir_inter(conta)
    if not r.get("success"):
        return {**base, "erro": f"{banco}: {r.get('error')}"}

    meta = {"banco": banco, "emitido_em": date.today().isoformat(), "resposta": {k: v for k, v in r.items() if k != "bruto"}}
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE receivable_accounts
                   SET boleto_id = %s, boleto_digitable_line = %s, boleto_url = %s, boleto_number = %s,
                       boleto_generated = TRUE, boleto_generated_at = NOW(),
                       pix_txid = %s, pix_copy_paste = %s,
                       pix_generated = (%s <> ''), pix_generated_at = CASE WHEN %s <> '' THEN NOW() ELSE pix_generated_at END,
                       metadata = coalesce(metadata, '{}'::jsonb) || CAST(%s AS jsonb), updated_at = NOW()
                 WHERE id::text = %s
                """,
                (str(r.get("txid") or r.get("boleto_id") or ""), r.get("boleto_digitavel") or "", r.get("boleto_url") or "",
                 str(r.get("boleto_id") or r.get("txid") or ""), str(r.get("txid") or ""), r.get("pix_copy_paste") or "",
                 r.get("pix_copy_paste") or "", r.get("pix_copy_paste") or "", json.dumps({"cobranca": meta}), rid),
            )
        conn.commit()
    logger.info("cobrança emitida: conta %s · %s · R$ %.2f · %s", rid, banco, valor, r.get("txid"))
    return {**base, "ok": True, "situacao": "emitida", "txid": r.get("txid"), "boleto_id": r.get("boleto_id"),
            "boleto_digitavel": r.get("boleto_digitavel"), "boleto_url": r.get("boleto_url"),
            "pix_copy_paste": (r.get("pix_copy_paste") or "")[:60]}


# Nota → conta a receber da mesma empresa, mesmo tomador e mesma competência (a nota diz
# "2026-08"; a conta diz "08/2026"). Só conta em aberto; se houver mais de uma, a de valor mais
# próximo ao da nota. NÃO cria conta: o gerador do dia 1 já cria uma por contrato/mês — nota
# sem conta é exceção que o dono precisa ver, não um buraco para o código tapar inventando
# vencimento.
_SQL_CONTA_DA_NOTA = """
    SELECT n.numero, n.tomador_nome, n.valor_servicos, n.competencia, coalesce(n.cancelada, FALSE),
           (SELECT r.id::text FROM receivable_accounts r
             WHERE r.deleted_at IS NULL AND r.empresa_id = n.empresa_id
               AND regexp_replace(coalesce(r.customer_document,''), '\\D', '', 'g')
                   = regexp_replace(coalesce(n.tomador_cnpj,''), '\\D', '', 'g')
               AND r.reference_month = substr(n.competencia, 6, 2) || '/' || substr(n.competencia, 1, 4)
               AND r.status::text IN ('pendente', 'parcial')
             ORDER BY abs(r.net_value - n.valor_servicos) LIMIT 1)
    FROM nfse_emitidas_nacional n WHERE n.chave_acesso = %s
"""


def emitir_por_nota(chave_acesso: str, preview: bool = False) -> dict:
    """Fluxo natural nota → boleto: emite a cobrança da conta a receber que corresponde à NFS-e."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_SQL_CONTA_DA_NOTA, (chave_acesso,))
            row = cur.fetchone()
    if not row:
        return {"ok": False, "erro": "NFS-e não encontrada"}
    numero, tomador, valor, comp, cancelada, rid = row
    nota = {"nota": numero, "tomador": tomador, "valor_nota": float(valor or 0), "competencia": comp}
    if cancelada:
        return {**nota, "ok": False, "erro": f"NFS-e {numero} está cancelada"}
    if not rid:
        return {**nota, "ok": False, "erro": (f"nenhuma conta a receber EM ABERTO de {tomador} na competência "
                                              f"{comp} — confira em Financeiro › Contas a receber (pode já estar paga)")}
    return {**nota, **emitir(rid, preview)}


def emitir_pendentes_mes(ano: int, mes: int, preview: bool = True) -> dict:
    """Todas as contas a receber em aberto do mês (origem contrato) ainda sem cobrança bancária."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id::text FROM receivable_accounts WHERE status IN ('pendente','parcial') "
                "AND boleto_id IS NULL AND pix_txid IS NULL AND due_date >= current_date "
                "AND extract(year from due_date) = %s AND extract(month from due_date) = %s "
                "ORDER BY due_date, customer_name", (ano, mes))
            ids = [r[0] for r in cur.fetchall()]
    itens = [emitir(i, preview=preview) for i in ids]
    return {"ano": ano, "mes": mes, "preview": preview, "total": len(itens),
            "emitidas": sum(1 for i in itens if i.get("situacao") == "emitida"),
            "erros": [i for i in itens if i.get("erro")], "itens": itens}
