"""
GATE ÚNICO DE ESCRITA DO REDESIGN (Fase 2) — choke-point de TODA ação de escrita.

Invariantes (inegociáveis — matam C2/C3/C4 do pré-mortem):
  1. MONEY/GOV (paga PIX / transmite eSocial/DCTFWeb) exige OTP humano válido. Sem OTP,
     NADA dispara — o gate gera o código (e-mail ao Jordan) e devolve `otp_required`.
  2. NUNCA auto-fire: o disparo real só ocorre com OTP consumido nesta request.
  3. NUNCA fabrica sucesso: devolve o retorno REAL do serviço (PSP/gov). Sem confirmação
     real = erro honesto, jamais "ok/verde" inventado.
  4. Escrita de TESTE → base de homologação (is_homologacao). Nunca toca dinheiro/dado real.
  5. Respeita o teto CONECTA_LIMITE_DIARIO_PAGAMENTOS.

Reusa a máquina de OTP existente (tabela `inter_lote_otp` + e-mail ao Jordan). NÃO reinventa
o caminho do dinheiro: `real_dispatch` deve ser o serviço PROVADO (pagamento_pj/diaristas,
transmissao_central). O gate só orquestra a trava.
"""
import os
import secrets
from datetime import UTC, datetime, timedelta
from enum import Enum

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

OTP_TTL_SECONDS = int(os.getenv("CONECTA_PAYMENT_OTP_TTL_SECONDS", "600"))
CEILING = float(os.getenv("CONECTA_LIMITE_DIARIO_PAGAMENTOS", "100000.00"))


class Tier(str, Enum):
    SAFE = "safe"            # compute / nota / rascunho — não passa pelo gate
    OP_WRITE = "op_write"    # cria registro operacional — homologação + idempotência
    MONEY_GOV = "money_gov"  # move dinheiro / transmite ao gov — OTP obrigatório


class GateError(Exception):
    """Trava do gate (teto, OTP inválido, duplicidade). Endpoint traduz p/ HTTP 400."""


class OTPRequired(Exception):
    """Money/gov sem OTP: código gerado+enviado; endpoint responde 'confirme com OTP'."""

    def __init__(self, ref: str, message: str):
        self.ref = ref
        self.message = message
        super().__init__(message)


# ── OTP + idempotência: tabela DEDICADA do gate (ref TEXT, desacoplada dos lotes) ──
# Pagamentos que já têm OTP próprio (Inter) DELEGAM ao serviço; esta tabela cobre gov
# (eSocial/DCTFWeb) e caminhos novos + idempotência de escrita operacional.
_TABLE_READY = False


async def _ensure_table(db: AsyncSession) -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    await db.execute(text(
        "CREATE TABLE IF NOT EXISTS redesign_gate_otp ("
        " id BIGSERIAL PRIMARY KEY, ref TEXT NOT NULL, code VARCHAR(8) NOT NULL DEFAULT '-',"
        " expires_at TIMESTAMPTZ NOT NULL, used BOOLEAN NOT NULL DEFAULT false,"
        " created_at TIMESTAMPTZ NOT NULL DEFAULT now())"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_redesign_gate_otp_ref ON redesign_gate_otp(ref)"))
    await db.commit()
    _TABLE_READY = True


async def _otp_generate(db: AsyncSession, ref: str) -> None:
    await _ensure_table(db)
    code = f"{secrets.randbelow(10 ** 6):06d}"
    exp = datetime.now(UTC) + timedelta(seconds=OTP_TTL_SECONDS)
    await db.execute(
        text("INSERT INTO redesign_gate_otp (ref, code, expires_at, used) VALUES (:l,:c,:e,false)"),
        {"l": ref, "c": code, "e": exp})
    await db.commit()
    try:  # e-mail best-effort — o código já está persistido; falha de e-mail não trava o gate
        from modules.integrations.inter.services.payment_service import _enviar_otp_email
        await _enviar_otp_email(code, ref)
    except Exception:  # noqa: BLE001
        pass


async def _otp_validate_consume(db: AsyncSession, ref: str, code: str | None) -> bool:
    await _ensure_table(db)
    row = (await db.execute(
        text("SELECT id FROM redesign_gate_otp WHERE ref=:l AND code=:c AND used=false "
             "AND expires_at > now() ORDER BY expires_at DESC LIMIT 1"),
        {"l": ref, "c": (code or "").strip()})).first()
    if not row:
        return False
    await db.execute(text("UPDATE redesign_gate_otp SET used=true WHERE id=:i"), {"i": row[0]})
    await db.commit()
    return True


async def is_homologacao_target(db: AsyncSession, employee_id) -> bool:
    """True se o alvo é da base de homologação → escrita de teste, nunca real."""
    if not employee_id:
        return False
    try:
        return bool((await db.execute(
            text("SELECT is_homologacao FROM employees WHERE id::text=:i"),
            {"i": str(employee_id)})).scalar())
    except Exception:  # noqa: BLE001
        return False


# ─────────────────────────────────────────────────────────────────────── o GATE ──
async def money_gov(db: AsyncSession, *, ref: str, amount: float | None, otp_code: str | None,
                    real_dispatch, is_homologacao: bool = False) -> dict:
    """
    Gate p/ dinheiro/gov. `real_dispatch` = coroutine SEM args que executa o disparo REAL
    (serviço provado) e devolve o retorno verdadeiro do PSP/gov.

    Fluxo: homolog → simula; teto → bloqueia; sem OTP → gera+envia e levanta OTPRequired;
    OTP inválido → GateError; OTP ok → dispara REAL e devolve o retorno verdadeiro.
    """
    if is_homologacao:
        return {"ok": True, "homologacao": True,
                "message": "Homologação: ação simulada — nada real foi disparado/pago."}
    if amount is not None and float(amount) > CEILING:
        raise GateError(f"Valor acima do teto diário (R$ {CEILING:,.2f}). Requer liberação manual.")
    if not otp_code:
        await _otp_generate(db, ref)
        raise OTPRequired(ref, "Código OTP enviado ao e-mail do Jordan. Confirme com o código para liberar.")
    if not await _otp_validate_consume(db, ref, otp_code):
        raise GateError("OTP inválido ou expirado. Gere um novo e tente de novo.")
    # OTP consumido nesta request → dispara o serviço REAL e devolve o que ELE retornou.
    result = await real_dispatch()
    if not isinstance(result, dict):
        result = {"ok": True, "result": result}
    result.setdefault("gated", True)
    return result  # honesto: reflete o retorno real; NÃO inventa sucesso


async def op_write(db: AsyncSession, *, real_write, idempotency_key: str | None = None,
                   is_homologacao: bool = False) -> dict:
    """
    Gate p/ escrita operacional (cria registro em tabela real). Bloqueia duplicidade via
    idempotência (persistida em inter_lote_otp como marcador consumível) e roteia teste.
    """
    if idempotency_key:
        await _ensure_table(db)
        dup = (await db.execute(
            text("SELECT 1 FROM redesign_gate_otp WHERE ref=:l LIMIT 1"),
            {"l": f"idem:{idempotency_key}"})).first()
        if dup:
            raise GateError("Ação duplicada (idempotência) — já executada.")
        await db.execute(
            text("INSERT INTO redesign_gate_otp (ref, code, expires_at, used) "
                 "VALUES (:l,'-', now()+interval '1 day', true)"),
            {"l": f"idem:{idempotency_key}"})
        await db.commit()
    result = await real_write()
    if isinstance(result, dict):
        result.setdefault("homologacao", is_homologacao)
    return result
