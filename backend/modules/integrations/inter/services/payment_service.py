"""D7 — InterPaymentService: preparar/aprovar/executar/cancelar pagamentos Inter.

Defesa em profundidade:
  preparado → aprovado (2FA OTP) → executado (Inter API) → confirmado (extrato sync)
  OU cancelado (a qualquer ponto antes de executado)

REGRAS INVIOLÁVEIS:
  - Registro DB ANTES de qualquer chamada Inter
  - FOR UPDATE lock antes de qualquer transição de estado
  - Idempotência: cada payment_id executa Inter no máximo 1x
  - Limite diário R$5.000 verificado em prepare()
  - Saldo mínimo R$100 sempre preservado
"""

import json
import logging
import os
import secrets
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

LIMITE_DIARIO = Decimal(os.getenv("CONECTA_LIMITE_DIARIO_PAGAMENTOS", "5000.00"))
SALDO_MINIMO = Decimal(os.getenv("CONECTA_SALDO_MINIMO_RESTANTE", "100.00"))
OTP_TTL_SECONDS = int(os.getenv("CONECTA_PAYMENT_OTP_TTL_SECONDS", "300"))

TIPOS_VALIDOS = {"boleto", "pix", "darf", "gps", "ted_interno"}


class PaymentError(Exception):
    pass


class LimiteDiarioError(PaymentError):
    pass


class SaldoInsuficienteError(PaymentError):
    pass


class OTPInvalidoError(PaymentError):
    pass


class StatusInvalidoError(PaymentError):
    pass


class IdempotenciaError(PaymentError):
    pass


class InterPaymentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── helpers ───────────────────────────────────────────────────────────────

    async def _audit(
        self,
        payment_id: str,
        user_id: str | None,
        status_from: str | None,
        status_to: str,
        motivo: str = "",
        ip: str = "",
    ) -> None:
        await self.db.execute(
            text("""
                INSERT INTO inter_payment_audit
                    (payment_id, user_id, status_from, status_to, ip_address, motivo, created_at)
                VALUES
                    (:pid, :uid, :sf, :st, :ip, :mot, NOW())
            """),
            {"pid": payment_id, "uid": user_id, "sf": status_from, "st": status_to, "ip": ip, "mot": motivo},
        )

    async def _get_saldo_inter(self) -> Decimal:
        """Consulta saldo Inter — Redis cache D6 primeiro, depois adapter direto."""
        try:
            import json as _json

            from core.cache.redis import get_redis

            redis = await get_redis()
            cached = await redis.get("inter:saldo:cache")
            if cached:
                data = _json.loads(cached)
                return Decimal(str(data.get("disponivel", 0)))
        except Exception:
            pass
        try:
            from modules.integrations.banking.adapters.base import BankCredentials
            from modules.integrations.banking.adapters.inter import InterAdapter

            adapter = InterAdapter(
                BankCredentials(
                    client_id=os.getenv("INTER_CLIENT_ID", ""),
                    client_secret=os.getenv("INTER_CLIENT_SECRET", ""),
                    certificate_path=os.getenv("INTER_CERT_PATH"),
                    private_key_path=os.getenv("INTER_KEY_PATH"),
                    environment=os.getenv("INTER_ENVIRONMENT", "production"),
                )
            )
            ok = await adapter.authenticate()
            if not ok:
                return Decimal("0")
            balance = await adapter.get_balance()
            await adapter.close()
            return Decimal(str(balance.available))
        except Exception as exc:
            logger.warning("D7 _get_saldo_inter falhou: %s", exc)
            return Decimal("0")

    async def _get_consumido_hoje(self) -> Decimal:
        row = (await self.db.execute(text("SELECT get_limite_diario_consumido()"))).scalar()
        return Decimal(str(row or 0))

    # ── preparar ──────────────────────────────────────────────────────────────

    async def preparar(
        self,
        payment_type: str,
        destinatario: dict,
        valor: float,
        data_pagamento: date,
        prepared_by: str,
        observacoes: str = "",
        categoria: str = "outro",
        origem: str = "inter",
    ) -> dict[str, Any]:
        """Cria registro com status='preparado'. Sem chamada ao banco.

        categoria: classifica a saída (pro_labore | transferencia | fornecedor | imposto |
        diarista | aluguel | folha | reembolso | outro) — é o que torna a conciliação automática
        e os números fidedignos (o Jordan categoriza cada saída ao pagar pelo Conecta PRO).

        origem: 'inter' (Eletrônica, padrão — fluxo provado inalterado) ou 'cora' (Patrimonial).
        No Cora o gate OTP da casa é idêntico; a diferença é só o EXECUTOR (executar → _chamar_cora)
        e o saldo é do Cora (a checagem de saldo Inter é pulada). O marcador vai no destinatario."""
        valor_d = Decimal(str(valor))
        origem = (origem or "inter").lower()

        if payment_type not in TIPOS_VALIDOS:
            raise PaymentError(f"payment_type inválido: {payment_type}. Válidos: {TIPOS_VALIDOS}")

        if valor_d <= 0:
            raise PaymentError(f"valor deve ser > 0 (recebido: {valor_d})")

        if data_pagamento < date.today():
            raise PaymentError(f"data_pagamento não pode ser no passado: {data_pagamento}")

        # Validar campos mínimos por tipo
        _validar_destinatario(payment_type, destinatario)

        # Verificar limite diário
        consumido = await self._get_consumido_hoje()
        if consumido + valor_d > LIMITE_DIARIO:
            disponivel = LIMITE_DIARIO - consumido
            raise LimiteDiarioError(
                f"Limite diário R${LIMITE_DIARIO} atingido. "
                f"Consumido hoje: R${consumido:.2f}. "
                f"Disponível: R${disponivel:.2f}."
            )

        # Verificar saldo Inter (só quando a origem é o Inter — o Cora tem saldo próprio
        # e a saída só se concretiza após aprovação no app do Cora).
        if origem == "inter":
            saldo = await self._get_saldo_inter()
            if saldo > 0 and saldo - valor_d < SALDO_MINIMO:
                raise SaldoInsuficienteError(
                    f"Saldo Inter insuficiente. Saldo: R${saldo:.2f}, "
                    f"Valor: R${valor_d:.2f}, Mínimo residual: R${SALDO_MINIMO:.2f}"
                )

        # Marca a origem no destinatario (jsonb) — executar lê pra rotear o executor.
        if origem != "inter":
            destinatario = {**destinatario, "_origem": origem}

        import uuid

        payment_id = str(uuid.uuid4())

        await self.db.execute(
            text("""
                INSERT INTO inter_payments
                    (id, payment_type, destinatario, valor, data_pagamento,
                     status, prepared_by, observacoes, categoria, created_at, updated_at)
                VALUES
                    (:id, :pt, cast(:dest as jsonb), :valor, :dp,
                     'preparado', :pb, :obs, :cat, NOW(), NOW())
            """),
            {
                "id": payment_id,
                "pt": payment_type,
                "dest": json.dumps(destinatario),
                "valor": float(valor_d),
                "dp": data_pagamento,
                "pb": prepared_by,
                "obs": observacoes,
                "cat": (categoria or "outro"),
            },
        )
        await self._audit(payment_id, prepared_by, None, "preparado", "preparado por usuário")
        await self.db.commit()

        logger.info("D7 preparar: id=%s tipo=%s valor=%.2f", payment_id, payment_type, valor_d)
        return {
            "id": payment_id,
            "status": "preparado",
            "payment_type": payment_type,
            "valor": float(valor_d),
            "data_pagamento": data_pagamento.isoformat(),
        }

    # ── gerar OTP ─────────────────────────────────────────────────────────────

    async def gerar_otp(self, payment_id: str, user_id: str) -> dict[str, Any]:
        """Gera OTP 6 dígitos, salva no DB, envia email Jordan."""
        row = (
            (
                await self.db.execute(
                    text("SELECT id, status, valor, payment_type, destinatario FROM inter_payments WHERE id = :id"),
                    {"id": payment_id},
                )
            )
            .mappings()
            .first()
        )

        if not row:
            raise PaymentError(f"payment_id não encontrado: {payment_id}")
        if row["status"] != "preparado":
            raise StatusInvalidoError(f"OTP só pode ser gerado para status='preparado' (atual: {row['status']})")

        code = f"{secrets.randbelow(900000) + 100000}"
        expires_at = datetime.now(UTC) + timedelta(seconds=OTP_TTL_SECONDS)

        # Invalidar OTPs anteriores não usados
        await self.db.execute(
            text("UPDATE inter_payment_otp SET used = true WHERE payment_id = :pid AND used = false"),
            {"pid": payment_id},
        )

        import uuid

        otp_id = str(uuid.uuid4())
        await self.db.execute(
            text("""
                INSERT INTO inter_payment_otp (id, payment_id, code, expires_at, used, created_at)
                VALUES (:id, :pid, :code, :exp, false, NOW())
            """),
            {"id": otp_id, "pid": payment_id, "code": code, "exp": expires_at},
        )
        await self.db.commit()

        # Enviar email com OTP
        valor = row["valor"]
        payment_type = row["payment_type"]
        dest = row["destinatario"] if isinstance(row["destinatario"], dict) else json.loads(row["destinatario"])
        dest_label = dest.get("chave") or dest.get("codigo_barras", "")[:20] or dest.get("nome", "destinatário")

        email_destino = os.getenv("JORDAN_EMAIL", "jjesus@conectamais.pro")
        await _enviar_otp_email(email_destino, code, valor, payment_type, dest_label)

        logger.info("D7 gerar_otp: payment_id=%s otp_id=%s email=%s", payment_id, otp_id, email_destino)
        return {
            "otp_id": otp_id,
            "message": f"Email com código OTP enviado para {email_destino}",
            "expires_in_seconds": OTP_TTL_SECONDS,
        }

    # ── aprovar ───────────────────────────────────────────────────────────────

    async def aprovar(self, payment_id: str, otp_code: str, user_id: str, ip: str = "") -> dict[str, Any]:
        """Valida OTP e muda status para 'aprovado'. Ainda NÃO chama Inter."""
        # FOR UPDATE — lock pessimista
        row = (
            (
                await self.db.execute(
                    text("SELECT id, status, valor FROM inter_payments WHERE id = :id FOR UPDATE"),
                    {"id": payment_id},
                )
            )
            .mappings()
            .first()
        )

        if not row:
            raise PaymentError(f"payment_id não encontrado: {payment_id}")
        if row["status"] != "preparado":
            raise StatusInvalidoError(f"Só é possível aprovar status='preparado' (atual: {row['status']})")

        now = datetime.now(UTC)
        otp_row = (
            (
                await self.db.execute(
                    text("""
                SELECT id, code, expires_at, used FROM inter_payment_otp
                WHERE payment_id = :pid AND used = false AND expires_at > :now
                ORDER BY created_at DESC LIMIT 1
            """),
                    {"pid": payment_id, "now": now},
                )
            )
            .mappings()
            .first()
        )

        if not otp_row:
            raise OTPInvalidoError("Nenhum OTP válido encontrado. Gere um novo OTP.")
        if otp_row["code"] != otp_code:
            raise OTPInvalidoError("Código OTP incorreto.")

        # Marcar OTP como usado
        await self.db.execute(
            text("UPDATE inter_payment_otp SET used = true WHERE id = :id"),
            {"id": str(otp_row["id"])},
        )

        approved_at = now
        await self.db.execute(
            text("""
                UPDATE inter_payments
                SET status = 'aprovado', approved_by = :uid, approved_at = :at,
                    approval_otp_used = :otp, updated_at = NOW()
                WHERE id = :id AND status = 'preparado'
            """),
            {"uid": user_id, "at": approved_at, "otp": otp_code, "id": payment_id},
        )
        await self._audit(payment_id, user_id, "preparado", "aprovado", "OTP validado", ip)
        await self.db.commit()

        logger.info("D7 aprovar: payment_id=%s aprovado por user=%s", payment_id, user_id)
        return {"id": payment_id, "status": "aprovado", "approved_at": approved_at.isoformat()}

    # ── executar ──────────────────────────────────────────────────────────────

    async def executar(self, payment_id: str, user_id: str | None = None) -> dict[str, Any]:
        """Chama Inter. Apenas após status='aprovado'. Idempotente (max 1x)."""
        # FOR UPDATE — lock pessimista
        row = (
            (
                await self.db.execute(
                    text("""
                SELECT id, status, payment_type, destinatario, valor, data_pagamento
                FROM inter_payments WHERE id = :id FOR UPDATE
            """),
                    {"id": payment_id},
                )
            )
            .mappings()
            .first()
        )

        if not row:
            raise PaymentError(f"payment_id não encontrado: {payment_id}")
        if row["status"] == "executado":
            raise IdempotenciaError(f"payment_id={payment_id} já foi executado (idempotência)")
        if row["status"] != "aprovado":
            raise StatusInvalidoError(f"Só é possível executar status='aprovado' (atual: {row['status']})")

        # Atomic: status='aprovado' → 'executado' — se UPDATE retornar 0 rows, alguém já executou
        updated = (
            await self.db.execute(
                text("""
                UPDATE inter_payments SET status = 'executado', executed_at = NOW(), updated_at = NOW()
                WHERE id = :id AND status = 'aprovado'
            """),
                {"id": payment_id},
            )
        ).rowcount

        if updated == 0:
            raise IdempotenciaError(f"Race condition detectada em payment_id={payment_id}. Abortando.")

        await self.db.commit()

        # Chamar Inter conforme tipo
        payment_type = row["payment_type"]
        dest = row["destinatario"] if isinstance(row["destinatario"], dict) else json.loads(row["destinatario"])
        valor = Decimal(str(row["valor"]))
        data_pgto = row["data_pagamento"]

        inter_response: dict = {}
        inter_payment_id: str | None = None
        erro: str | None = None
        origem = (dest.get("_origem") or "inter").lower()  # 'inter' (padrão) | 'cora'

        try:
            if origem == "cora":
                inter_response, inter_payment_id = await _chamar_cora(
                    self.db, payment_type, dest, valor, data_pgto, code=payment_id)
            else:
                inter_response, inter_payment_id = await _chamar_inter(payment_type, dest, valor, data_pgto)
        except Exception as exc:
            erro = str(exc)
            logger.error("D7 executar: banco (%s) falhou payment_id=%s: %s", origem, payment_id, exc)
            # Marcar como erro — NÃO tentar de novo automaticamente (perigoso)
            await self.db.execute(
                text("""
                    UPDATE inter_payments
                    SET status = 'erro', inter_response = cast(:resp as jsonb), updated_at = NOW()
                    WHERE id = :id
                """),
                {"resp": json.dumps({"erro": erro}), "id": payment_id},
            )
            await self._audit(payment_id, user_id, "executado", "erro", f"Inter falhou: {erro}")
            await self.db.commit()
            raise PaymentError(f"Inter API falhou: {erro}") from exc

        # VALIDAÇÃO DE SUCESSO REAL — o Inter só confirmou se retornou um identificador
        # (endToEndId/codigoSolicitacao) E não sinalizou success=false. Um 401/erro do Inter
        # devolve {"success": false, ...} SEM lançar exceção — nunca pode virar 'executado'.
        sucesso = bool(inter_payment_id) and inter_response.get("success") is not False
        if not sucesso:
            detalhe = (
                inter_response.get("detail")
                or inter_response.get("error")
                or "Inter não confirmou o pagamento (sem comprovante). Nada foi pago."
            )
            await self.db.execute(
                text("""
                    UPDATE inter_payments
                    SET status = 'erro', inter_response = cast(:resp as jsonb), updated_at = NOW()
                    WHERE id = :id
                """),
                {"resp": json.dumps(inter_response), "id": payment_id},
            )
            await self._audit(payment_id, user_id, "executado", "erro", f"Inter recusou/não confirmou: {detalhe}")
            await self.db.commit()
            logger.error("D7 executar: Inter NÃO confirmou payment_id=%s resp=%s", payment_id, inter_response)
            # Boleto reemitido/atualizado: o Inter valida a data contra a CIP e recusa quando
            # não bate (o app resolve por consulta interna que a API não expõe). Mensagem clara.
            if payment_type == "boleto" and ("vencimento" in detalhe.lower() or "inválid" in detalhe.lower()):
                raise PaymentError(
                    "Este boleto foi recusado pelo Banco Inter na validação de vencimento — "
                    "geralmente é boleto reemitido/2ª via ou atualizado, cujo registro na CIP "
                    "difere do código. A API do Inter não permite consultar esse dado antes de pagar. "
                    "Pague este boleto pelo app do Inter e depois marque como 'pago pelo app Inter' "
                    "na tela de Pagamentos de Diaristas/Financeiro para conciliar."
                )
            raise PaymentError(f"Inter não confirmou o pagamento: {detalhe}")

        # O Inter ACEITOU o pedido, mas pagamento por API entra numa fila e pode ficar
        # AGUARDANDO_APROVACAO. Grava o status REAL (não assume 'executado'/concluído).
        novo_status = _map_status_inter(inter_response.get("status"))
        await self.db.execute(
            text("""
                UPDATE inter_payments
                SET inter_payment_id = :ipid,
                    inter_response = cast(:resp as jsonb),
                    status = :st,
                    updated_at = NOW()
                WHERE id = :id
            """),
            {"ipid": inter_payment_id, "resp": json.dumps(inter_response), "st": novo_status, "id": payment_id},
        )
        await self._audit(
            payment_id, user_id, "executado", novo_status,
            f"Inter aceitou (cod={inter_payment_id}); status Inter={inter_response.get('status')}",
        )
        await self.db.commit()

        # AGENDA — auto-salva o beneficiário PIX (como o app do Inter): próxima vez basta o nome.
        # Não-fatal: uma falha aqui NUNCA pode afetar o pagamento já concluído.
        if payment_type == "pix" and dest.get("chave"):
            try:
                from modules.financial.beneficiarios_service import upsert_beneficiario
                doc = (dest.get("chave") if (dest.get("tipo_chave") or "").upper() in ("CPF", "CNPJ")
                       else dest.get("cpf") or dest.get("cpf_cnpj"))
                await upsert_beneficiario(
                    self.db, nome=dest.get("nome_recebedor") or dest.get("nome"),
                    chave_pix=dest.get("chave"), tipo_chave=dest.get("tipo_chave"),
                    cpf_cnpj=doc, categoria="avulso", origem="pagamento", contar_pagamento=True)
                await self.db.commit()
            except Exception as _e:  # noqa: BLE001
                logger.warning("Auto-salvar beneficiário falhou (ignorado): %s", _e)
                await self.db.rollback()

        logger.info("D7 executar: payment_id=%s cod=%s status_inter=%s -> %s",
                    payment_id, inter_payment_id, inter_response.get("status"), novo_status)
        return {
            "id": payment_id,
            "status": novo_status,
            "aguardando_aprovacao": novo_status == "aguardando_aprovacao",
            "inter_payment_id": inter_payment_id,
            "status_inter": inter_response.get("status"),
            "mensagem": (
                # Cora: toda saída por API fica INITIATED e EXIGE aprovação no app (doc oficial;
                # não há como desligar pela API). Inter: você já desativou a aprovação → paga direto.
                ("Transferência/pagamento INICIADO no Cora — abra o app Cora e APROVE para concluir "
                 "(o Cora exige essa aprovação no celular; o valor sai da Patrimonial só após você aprovar)."
                 if origem == "cora" else
                 "Pagamento CRIADO no Inter, mas AGUARDANDO SUA APROVAÇÃO no app do Inter "
                 "(ou desative a exigência de aprovação de pagamentos por API nas configurações do Inter).")
                if novo_status == "aguardando_aprovacao"
                else ("Pagamento iniciado no Cora." if origem == "cora" else "Pagamento aceito pelo Inter.")
            ),
            "inter_response": inter_response,
        }

    # ── monitorar status real no Inter ────────────────────────────────────────

    async def atualizar_status_inter(self, payment_id: str) -> dict[str, Any]:
        """MONITOR: consulta o status REAL do pagamento no Inter e atualiza nosso registro.
        É como saber, em tempo real, se o Inter já concluiu, se está aguardando aprovação, ou
        se rejeitou. Não move dinheiro (só leitura no Inter)."""
        row = (
            (
                await self.db.execute(
                    text("SELECT id, status, inter_payment_id FROM inter_payments WHERE id = :id"),
                    {"id": payment_id},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            raise PaymentError(f"payment_id não encontrado: {payment_id}")
        cod = row["inter_payment_id"]
        if not cod:
            return {"id": payment_id, "status": row["status"], "status_inter": None,
                    "mensagem": "Pagamento ainda não enviado ao Inter (sem código de solicitação)."}

        import os as _os

        from modules.integrations.banking.adapters.base import BankCredentials
        from modules.integrations.banking.adapters.inter import InterAdapter

        adapter = InterAdapter(
            BankCredentials(
                client_id=_os.getenv("INTER_CLIENT_ID", ""),
                client_secret=_os.getenv("INTER_CLIENT_SECRET", ""),
                certificate_path=_os.getenv("INTER_CERT_PATH"),
                private_key_path=_os.getenv("INTER_KEY_PATH"),
                environment=_os.getenv("INTER_ENVIRONMENT", "production"),
            )
        )
        try:
            consulta = await adapter.consultar_pix_pagamento(cod)
        finally:
            try:
                await adapter.close()
            except Exception:  # noqa: BLE001
                pass

        if not consulta.get("success"):
            return {"id": payment_id, "status": row["status"], "status_inter": None,
                    "erro": consulta.get("detail") or consulta.get("error"),
                    "mensagem": "Não foi possível consultar o status no Inter agora."}

        status_inter = consulta.get("status", "")
        novo = _map_status_inter(status_inter)
        if novo != row["status"]:
            await self.db.execute(
                text("UPDATE inter_payments SET status = :st, updated_at = NOW() WHERE id = :id"),
                {"st": novo, "id": payment_id},
            )
            await self._audit(payment_id, None, row["status"], novo, f"Status Inter={status_inter}")
            await self.db.commit()

        msg = {
            "aguardando_aprovacao": "Aguardando SUA aprovação no app do Inter (o dinheiro ainda NÃO saiu).",
            "confirmado": "Pagamento CONCLUÍDO — o dinheiro saiu da conta.",
            "erro": "Pagamento REJEITADO/cancelado pelo Inter.",
        }.get(novo, "Em processamento.")
        return {
            "id": payment_id, "status": novo, "status_inter": status_inter,
            "historico": consulta.get("historico", []), "erros": consulta.get("erros", []),
            "mensagem": msg,
        }

    # ── cancelar ──────────────────────────────────────────────────────────────

    async def cancelar(self, payment_id: str, motivo: str, user_id: str, ip: str = "") -> dict[str, Any]:
        """Cancela se ainda não executado."""
        row = (
            (
                await self.db.execute(
                    text("SELECT id, status FROM inter_payments WHERE id = :id FOR UPDATE"),
                    {"id": payment_id},
                )
            )
            .mappings()
            .first()
        )

        if not row:
            raise PaymentError(f"payment_id não encontrado: {payment_id}")
        if row["status"] in ("executado", "confirmado"):
            raise StatusInvalidoError(f"Não é possível cancelar status='{row['status']}'")
        if row["status"] == "cancelado":
            return {"id": payment_id, "status": "cancelado", "motivo": "já cancelado"}

        status_from = row["status"]
        await self.db.execute(
            text("""
                UPDATE inter_payments
                SET status = 'cancelado', cancelled_at = NOW(), cancelled_by = :uid,
                    cancel_reason = :reason, updated_at = NOW()
                WHERE id = :id
            """),
            {"uid": user_id, "reason": motivo, "id": payment_id},
        )
        await self._audit(payment_id, user_id, status_from, "cancelado", motivo, ip)
        await self.db.commit()

        logger.info("D7 cancelar: payment_id=%s motivo=%s", payment_id, motivo)
        return {"id": payment_id, "status": "cancelado", "motivo": motivo}

    # ── listar + audit ────────────────────────────────────────────────────────

    async def listar(
        self,
        status: str | None = None,
        payment_type: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        limit: int = 100,
    ) -> list[dict]:
        where = ["1=1"]
        params: dict = {"limit": limit}
        if status:
            where.append("status = :status")
            params["status"] = status
        if payment_type:
            where.append("payment_type = :pt")
            params["pt"] = payment_type
        if from_date:
            where.append("data_pagamento >= :fd")
            params["fd"] = from_date
        if to_date:
            where.append("data_pagamento <= :td")
            params["td"] = to_date

        rows = (
            (
                await self.db.execute(
                    text(f"""
                SELECT id, payment_type, valor, data_pagamento, status,
                       inter_payment_id, approved_at, executed_at, observacoes,
                       COALESCE(categoria, 'outro') AS categoria, created_at
                FROM inter_payments WHERE {" AND ".join(where)}
                ORDER BY created_at DESC LIMIT :limit
            """),
                    params,
                )
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]

    async def audit_log(self, payment_id: str) -> list[dict]:
        rows = (
            (
                await self.db.execute(
                    text("""
                SELECT id, payment_id, user_id, status_from, status_to,
                       ip_address, motivo, created_at
                FROM inter_payment_audit WHERE payment_id = :pid ORDER BY created_at
            """),
                    {"pid": payment_id},
                )
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]

    async def saldo_resumo(self) -> dict[str, Any]:
        consumido = await self._get_consumido_hoje()
        saldo_inter = await self._get_saldo_inter()
        return {
            "saldo_inter": float(saldo_inter),
            "limite_diario": float(LIMITE_DIARIO),
            "consumido_hoje": float(consumido),
            "disponivel_hoje": float(LIMITE_DIARIO - consumido),
            "limite_restante": float(LIMITE_DIARIO - consumido),
        }


# ── helpers independentes ─────────────────────────────────────────────────────


def _map_status_inter(status_inter: str | None) -> str:
    """Mapeia o status do Inter para o status interno. Default seguro = aguardando_aprovacao
    (NUNCA assume concluído sem o Inter confirmar REALIZADO/APROVADO)."""
    s = (status_inter or "").upper()
    if s in ("REALIZADO", "APROVADO", "EFETIVADO", "EFETUADO", "PROCESSADO", "CONCLUIDO", "PAGO", "TRANSACAO_APROVADA"):
        return "confirmado"
    if s in ("REJEITADO", "CANCELADO", "FALHA", "ERRO", "NAO_REALIZADO", "TRANSACAO_REJEITADA"):
        return "erro"
    # AGUARDANDO_APROVACAO, REQUER_APROVACAO, PENDENTE, EM_PROCESSAMENTO, AGENDADO, vazio…
    return "aguardando_aprovacao"


def _validar_destinatario(payment_type: str, dest: dict) -> None:
    required: dict[str, list[str]] = {
        "boleto": ["codigo_barras"],
        "pix": ["chave"],  # tipo_chave é opcional: o Inter auto-detecta (destinatario.tipo='CHAVE')
        "darf": ["periodo_apuracao", "codigo_receita"],
        "gps": ["competencia", "codigo_pagamento"],
        "ted_interno": ["agencia", "conta", "banco"],
    }
    if payment_type not in required:
        raise PaymentError(f"payment_type inválido: {payment_type}. Válidos: {set(required)}")
    # PIX via copia-e-cola (QR dinâmico, ex. VT/VR do Sólides): o brcode substitui a
    # chave — o Inter liquida a COBRANÇA no PSP (mantém txid/conciliação do emissor).
    if payment_type == "pix" and dest.get("pix_copia_e_cola"):
        return
    campos = required[payment_type]
    faltando = [c for c in campos if not dest.get(c)]
    if faltando:
        raise PaymentError(f"destinatario faltando campos para {payment_type}: {faltando}")


async def _enviar_otp_email(email: str, code: str, valor: float, payment_type: str, dest: str) -> None:
    try:
        from core.mailer import send_email

        html = f"""
        <!DOCTYPE html><html><head><meta charset="utf-8"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                     background:#f4f4f5; padding:40px 0;">
          <div style="max-width:480px; margin:0 auto; background:#fff; border-radius:12px;
                      padding:40px; box-shadow:0 1px 3px rgba(0,0,0,0.1);">
            <div style="text-align:center; margin-bottom:24px;">
              <h1 style="color:#0A2540; font-size:20px; margin:0;">Conecta PRO — Autorização de Pagamento</h1>
            </div>
            <div style="background:#fff3cd; border:1px solid #ffc107; border-radius:8px;
                        padding:16px; margin-bottom:24px;">
              <p style="color:#856404; margin:0; font-weight:600;">⚠️ PAGAMENTO AGUARDANDO APROVAÇÃO</p>
            </div>
            <table style="width:100%; border-collapse:collapse; margin-bottom:24px;">
              <tr><td style="color:#64748b; padding:8px 0;">Tipo:</td>
                  <td style="color:#0f172a; font-weight:600;">{payment_type.upper()}</td></tr>
              <tr><td style="color:#64748b; padding:8px 0;">Valor:</td>
                  <td style="color:#0f172a; font-weight:700; font-size:18px;">R$ {valor:.2f}</td></tr>
              <tr><td style="color:#64748b; padding:8px 0;">Destinatário:</td>
                  <td style="color:#0f172a;">{dest}</td></tr>
            </table>
            <div style="background:#0A2540; border-radius:12px; padding:24px; text-align:center;
                        margin-bottom:24px;">
              <p style="color:#94a3b8; margin:0 0 8px; font-size:13px;">Código de Autorização (válido 5min)</p>
              <p style="color:#FF6B35; font-size:40px; font-weight:700; letter-spacing:8px; margin:0;">
                {code}
              </p>
            </div>
            <p style="color:#ef4444; font-size:13px; text-align:center;">
              ⚠️ NUNCA compartilhe este código. Após aprovação, o pagamento é EXECUTADO imediatamente.
            </p>
          </div>
        </body></html>
        """
        await send_email(email, f"[Conecta PRO] OTP Pagamento R${valor:.2f} — {payment_type.upper()}", html)
    except Exception as exc:
        logger.warning("D7 _enviar_otp_email falhou (%s) — continuando sem email", exc)


def _mod10(num: str) -> int:
    """Dígito verificador mod10 (usado nos campos da linha digitável do boleto bancário)."""
    soma, peso = 0, 2
    for d in reversed(num):
        p = int(d) * peso
        soma += p if p < 10 else p - 9
        peso = 1 if peso == 2 else 2
    return (10 - (soma % 10)) % 10


def _normalizar_codigo_boleto(codigo: str) -> str:
    """Normaliza para a LINHA DIGITÁVEL (o formato que a API do Inter aceita de forma confiável).

    - 47/48 dígitos (linha digitável já) → mantém.
    - 44 dígitos (código de barras lido do QR/ITF pela câmera) → converte:
        * boleto bancário (não começa com 8) → linha digitável de 47.
        * arrecadação (começa com 8) → mantém 44 (conversão p/ 48 é feita pelo Inter).
    - outro tamanho → devolve só os dígitos (deixa o Inter validar).
    """
    b = "".join(c for c in (codigo or "") if c.isdigit())
    if len(b) in (47, 48):
        return b
    if len(b) == 44 and not b.startswith("8"):
        campo1, campo2, campo3 = b[0:4] + b[19:24], b[24:34], b[34:44]
        return (f"{campo1}{_mod10(campo1)}{campo2}{_mod10(campo2)}"
                f"{campo3}{_mod10(campo3)}{b[4]}{b[5:19]}")
    return b


async def _chamar_inter(payment_type: str, dest: dict, valor: Decimal, data_pgto: date) -> tuple[dict, str | None]:
    """Despacha para o método correto do InterAdapter conforme tipo."""
    import os

    from modules.integrations.banking.adapters.base import BankCredentials
    from modules.integrations.banking.adapters.inter import InterAdapter

    adapter = InterAdapter(
        BankCredentials(
            client_id=os.getenv("INTER_CLIENT_ID", ""),
            client_secret=os.getenv("INTER_CLIENT_SECRET", ""),
            certificate_path=os.getenv("INTER_CERT_PATH"),
            private_key_path=os.getenv("INTER_KEY_PATH"),
            environment=os.getenv("INTER_ENVIRONMENT", "production"),
        )
    )

    try:
        ok = await adapter.authenticate()
        if not ok:
            raise PaymentError("Falha ao autenticar com Inter (mTLS/OAuth2)")

        if payment_type == "boleto":
            result = await adapter.pagar_boleto(
                codigo_barras=_normalizar_codigo_boleto(dest["codigo_barras"]),
                valor=valor,
                data_pagamento=data_pgto,
            )
        elif payment_type == "pix" and dest.get("pix_copia_e_cola"):
            # QR dinâmico (cobrança no PSP, ex. Sólides/contaswap): paga o COPIA-E-COLA —
            # o Inter liquida a cobrança e o txid é preservado (o emissor baixa sozinho).
            result = await adapter.enviar_pix_copia_e_cola(
                brcode=dest["pix_copia_e_cola"],
                valor=valor,
                descricao=dest.get("descricao", "") or f"PIX para {dest.get('nome_recebedor', '')}",
            )
        elif payment_type == "pix":
            # tipo_chave é OPCIONAL: o Inter auto-detecta (destinatario.tipo='CHAVE').
            # Usar .get evita KeyError "'tipo_chave'" quando a tela não o envia.
            result = await adapter.enviar_pix(
                chave=dest["chave"],
                tipo_chave=dest.get("tipo_chave", ""),
                valor=valor,
                nome_recebedor=dest.get("nome_recebedor", ""),
                descricao=dest.get("descricao", ""),
            )
        elif payment_type == "darf":
            result = await adapter.pagar_darf(
                periodo_apuracao=dest["periodo_apuracao"],
                codigo_receita=dest["codigo_receita"],
                valor=valor,
                referencia=dest.get("referencia", ""),
            )
        elif payment_type == "gps":
            result = await adapter.pagar_gps(
                competencia=dest["competencia"],
                codigo_pagamento=dest["codigo_pagamento"],
                valor=valor,
                identificador=dest.get("identificador", ""),
            )
        elif payment_type == "ted_interno":
            result = await adapter.transferir_ted(
                agencia=dest["agencia"],
                conta=dest["conta"],
                banco=dest["banco"],
                nome=dest.get("nome", ""),
                cpf_cnpj=dest.get("cpf_cnpj", ""),
                valor=valor,
            )
        else:
            raise PaymentError(f"Tipo desconhecido: {payment_type}")

        inter_id = (
            result.get("codigoSolicitacao")
            or result.get("endToEndId")
            or result.get("payment_id")  # boleto/tributo: codigoTransacao
            or result.get("autenticacao")
            or result.get("nosso_numero")
        )
        return result, inter_id

    finally:
        await adapter.close()


async def _chamar_cora(db, payment_type: str, dest: dict, valor: Decimal,
                       data_pgto: date, *, code: str) -> tuple[dict, str | None]:
    """Executa a saída pela CORA (Patrimonial) via cora_pagamento_service — espelha o
    contrato de _chamar_inter: devolve (raw, id). O Cora só faz BOLETO e TED por dados
    bancários; PIX de saída NÃO existe no Cora (§4.4, doc oficial). DARF/GPS pela Cora
    exigem dados do pagador que a tela atual não coleta → bloqueado honesto por enquanto.
    Toda saída Cora volta INITIATED e exige aprovação no app (não simula liquidação)."""
    from modules.integrations.banking.services import cora_pagamento_service as cps

    centavos = int((valor * 100).quantize(Decimal("1")))
    descricao = (dest.get("descricao") or dest.get("nome") or "Pagamento").strip()

    if payment_type == "boleto":
        res = await cps.pagar_boleto(db, linha_digitavel=dest["codigo_barras"],
                                     descricao=descricao, code=code)
    elif payment_type == "ted_interno":
        conta = "".join(c for c in (dest.get("conta") or "") if c.isdigit())
        agencia = "".join(c for c in (dest.get("agencia") or "") if c.isdigit())[:4]
        destino = {
            "bank_code": (dest.get("banco") or "").strip(),
            "account_number": conta,   # COM dígito, ≤13
            "branch_number": agencia,  # ≤4
            "holder": {"name": (dest.get("nome") or "").strip(),
                       "document": {"identity": "".join(c for c in (dest.get("documento") or "") if c.isdigit())}},
            "account_type": (dest.get("account_type") or "CHECKING"),
        }
        res = await cps.transferir(db, destination=destino, valor_centavos=centavos,
                                   descricao=descricao, code=code, category=dest.get("category"))
    elif payment_type == "darf":
        nome = (dest.get("payer_name") or "").strip()
        ident = "".join(c for c in (dest.get("payer_document") or "") if c.isdigit())
        venc = (dest.get("vencimento") or "").strip()
        if not (nome and ident and venc):
            raise PaymentError("Para DARF pela Cora, informe nome e CPF/CNPJ do contribuinte e o "
                               "vencimento (AAAA-MM-DD) — o Cora exige esses dados.")
        data = {"name": nome, "code": (dest.get("codigo_receita") or "").strip(), "identity": ident,
                "type": "DARF", "reference_date": (dest.get("periodo_apuracao") or "").strip(),
                "due_date": venc, "amount": {"main": centavos}}
        res = await cps.pagar_guia(db, tipo="darf", data=data, descricao=descricao, code=code)
    elif payment_type == "gps":
        nome = (dest.get("payer_name") or "").strip()
        ident = "".join(c for c in (dest.get("payer_document") or "") if c.isdigit())
        idtype = (dest.get("identification_type") or "").strip().upper()
        if not (nome and ident and idtype in ("NIT", "PIS", "PASEP")):
            raise PaymentError("Para GPS pela Cora, informe nome, a identidade (NIT/PIS/PASEP) e o "
                               "tipo de identificação — o Cora exige esses dados.")
        data = {"name": nome, "code": (dest.get("codigo_pagamento") or "").strip(), "identity": ident,
                "identification_type": idtype, "competence": (dest.get("competencia") or "").strip(),
                "amount": {"other_entity": 0, "inss": centavos, "charge": 0}}
        res = await cps.pagar_guia(db, tipo="gps", data=data, descricao=descricao, code=code)
    elif payment_type == "pix":
        raise PaymentError(
            "O Cora não envia PIX de saída (nem por chave, nem copia-e-cola) — é regra da API do "
            "próprio Cora. Para pagar da Patrimonial, use TED por dados bancários, ou pague pelo Inter.")
    else:
        raise PaymentError(
            f"Pela Cora ainda não dá para '{payment_type}'. Use o Inter para este tipo por enquanto.")

    raw = res.get("raw") if isinstance(res, dict) else {}
    if not isinstance(raw, dict):
        raw = {}
    raw.setdefault("status", "INITIATED")
    return raw, res.get("payment_id")
