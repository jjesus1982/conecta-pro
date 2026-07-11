"""
Webhook Controller — Receptor de notificações do Banco Inter
Processa eventos: PIX recebido, boleto pago, devolução
Concilia automaticamente com receivable/payable_accounts
"""

import json
import logging
import os
import uuid

from fastapi import APIRouter, Header, HTTPException, Request

router = APIRouter(prefix="/webhooks", tags=["Webhooks — Inter"])
logger = logging.getLogger(__name__)
INTER_WEBHOOK_SECRET = os.getenv("INTER_WEBHOOK_SECRET", "")  # pragma: allowlist secret

_CREDENTIALS_FILE = "/opt/conecta-pro/credentials/.env.credentials"


def _validar_assinatura_inter(body: bytes, signature: str | None) -> bool:
    """
    Valida assinatura do webhook Inter usando a CA cert.
    Inter assina o payload com chave privada; verificamos com a chave pública da CA.
    Se CA não configurada ou assinatura ausente → aceita (mTLS valida no proxy).
    """
    ca_path = os.getenv("INTER_WEBHOOK_CA_PATH", "")
    if not ca_path or not signature:
        return True
    try:
        import base64

        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.x509 import load_pem_x509_certificate

        with open(ca_path, "rb") as f:
            cert = load_pem_x509_certificate(f.read())
        pub_key = cert.public_key()
        sig_bytes = base64.b64decode(signature)
        pub_key.verify(sig_bytes, body, padding.PKCS1v15(), hashes.SHA256())
        return True
    except Exception as exc:
        logger.warning("Assinatura Inter inválida: %s", exc)
        return False


def _load_inter_credentials() -> dict:
    """Carrega credenciais Inter do arquivo .env.credentials (igual ao banking_controller)."""
    creds: dict = {}
    try:
        with open(_CREDENTIALS_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    creds[key.strip()] = value.strip()
    except FileNotFoundError:
        pass
    return creds


def _get_conn():
    import psycopg2

    database_url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    return psycopg2.connect(database_url)


def _log_webhook(payload: dict, event_type: str, path: str) -> None:
    """Persiste recebimento do webhook em integration_logs."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO integration_logs (
                id, log_type, level, status,
                retry_count, is_retry, timestamp,
                method, path, request_body, created_at
            ) VALUES (
                %s, 'webhook_delivery', 'info', 'success',
                0, false, NOW(),
                'POST', %s, %s, NOW()
            )
            """,
            (str(uuid.uuid4()), path, json.dumps(payload)[:4000]),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as exc:
        logger.warning("Falha ao gravar integration_logs: %s", exc)


async def _processar_pix_recebido(pix_data: dict) -> dict:
    """Processa PIX recebido e atualiza receivable_account."""
    conn = _get_conn()
    cur = conn.cursor()

    try:
        e2e_id = pix_data.get("endToEndId", "")
        txid = pix_data.get("txid", "")
        valor = float(pix_data.get("valor", 0))
        pagador = pix_data.get("pagador", {})
        pagador_cnpj = pagador.get("cnpj", pagador.get("cpf", ""))
        pagador_nome = pagador.get("nome", "")

        # Buscar bank_account_id do Inter
        cur.execute("SELECT id FROM bank_accounts WHERE bank_code = '077' LIMIT 1")
        ba_row = cur.fetchone()
        bank_account_id = str(ba_row[0]) if ba_row else None

        # Salvar na tabela de transações
        cur.execute(
            """
            INSERT INTO bank_transactions (
                id, bank_account_id, transaction_type, category,
                amount, description, transaction_date,
                counterparty_name, counterparty_document,
                reconciliation_status, external_id,
                created_at, updated_at
            ) VALUES (
                gen_random_uuid(), %s::uuid, 'credito', 'pix_recebido',
                %s, %s, NOW(),
                %s, %s, 'pendente', %s,
                NOW(), NOW()
            )
            ON CONFLICT (external_id) WHERE external_id IS NOT NULL
            DO UPDATE SET updated_at = NOW()
            RETURNING id
            """,
            (
                bank_account_id,
                valor,
                f"PIX recebido - {pagador_nome} - {txid}",
                pagador_nome,
                pagador_cnpj,
                e2e_id or None,
            ),
        )
        tx_row = cur.fetchone()
        tx_id = str(tx_row[0]) if tx_row else None

        # Auto-sync para cashflow_entries
        if tx_id:
            try:
                from modules.financial.services.auto_sync_service import sync_single_transaction

                sync_single_transaction(tx_id)
            except Exception:
                pass  # sync é best-effort, não bloqueia webhook

        # Tentar conciliar por txid
        if txid:
            cur.execute(
                """
                UPDATE receivable_accounts SET
                    status = 'recebido',
                    data_recebimento = CURRENT_DATE,
                    transacao_bancaria_id = %s,
                    updated_at = NOW()
                WHERE pix_txid = %s
                  AND status = 'pendente'
                RETURNING id
                """,
                (tx_id, txid),
            )
            rec = cur.fetchone()
            if rec:
                conn.commit()
                return {
                    "conciliado": True,
                    "receivable_id": str(rec[0]),
                    "e2e_id": e2e_id,
                    "valor": valor,
                    "metodo": "txid",
                }

        # Fallback: conciliar por valor + janela de 7 dias
        cur.execute(
            """
            UPDATE receivable_accounts SET
                status = 'recebido',
                data_recebimento = CURRENT_DATE,
                transacao_bancaria_id = %s,
                updated_at = NOW()
            WHERE id = (
                SELECT id FROM receivable_accounts
                WHERE ABS(net_value - %s) <= 0.01
                  AND status = 'pendente'
                  AND due_date >= CURRENT_DATE - INTERVAL '7 days'
                  AND ativo IS NOT FALSE
                  AND deleted_at IS NULL
                ORDER BY due_date ASC
                LIMIT 1
            )
            RETURNING id
            """,
            (tx_id, valor),
        )
        rec = cur.fetchone()
        conn.commit()
        return {
            "conciliado": rec is not None,
            "receivable_id": str(rec[0]) if rec else None,
            "e2e_id": e2e_id,
            "valor": valor,
            "tx_salva": tx_id is not None,
            "metodo": "valor" if rec else "nenhum",
        }

    except Exception as e:
        conn.rollback()
        logger.error("Erro processar PIX: %s", e)
        return {"erro": str(e)}
    finally:
        cur.close()
        conn.close()


async def _processar_boleto_pago(boleto_data: dict) -> dict:
    """Processa notificação de boleto pago."""
    conn = _get_conn()
    cur = conn.cursor()

    try:
        boleto_id = boleto_data.get("codigoSolicitacao", "")
        valor = float(boleto_data.get("valorTotal", 0) or 0)
        situacao = str(boleto_data.get("situacao", "")).upper()

        # Só PAGAMENTO concilia. EXPIRADO/CANCELADO/A_RECEBER etc. são registrados e
        # ignorados — antes deste guard, QUALQUER evento marcaria a fatura como recebida.
        if situacao not in ("PAGO", "RECEBIDO", "MARCADO_RECEBIDO"):
            return {"boleto_id": boleto_id, "situacao": situacao, "conciliado": False,
                    "ignorado": "evento não é de pagamento"}

        cur.execute(
            """
            UPDATE receivable_accounts SET
                status = 'recebido',
                data_recebimento = CURRENT_DATE,
                updated_at = NOW()
            WHERE (boleto_number ILIKE %s OR pix_txid = %s)
              AND status = 'pendente'
            RETURNING id
            """,
            (f"%{boleto_id}%", boleto_id),
        )
        rec = cur.fetchone()
        conn.commit()
        return {
            "boleto_id": boleto_id,
            "conciliado": rec is not None,
            "receivable_id": str(rec[0]) if rec else None,
            "valor": valor,
        }
    except Exception as e:
        conn.rollback()
        logger.error("Erro processar boleto: %s", e)
        return {"erro": str(e)}
    finally:
        cur.close()
        conn.close()


@router.post(
    "/inter/pix",
    summary="Webhook PIX — notificações Inter",
    include_in_schema=False,
)
async def webhook_pix(
    request: Request,
    x_inter_webhook_signature: str | None = Header(None),
):
    """
    Receptor de webhooks PIX do Banco Inter.
    Processa: PIX recebidos, devoluções, confirmações.
    Concilia automaticamente com receivable_accounts.
    """
    try:
        body = await request.body()
        if not _validar_assinatura_inter(body, x_inter_webhook_signature):
            logger.warning("Webhook PIX: assinatura inválida — rejeitado")
            raise HTTPException(status_code=401, detail="Assinatura inválida")
        payload = json.loads(body)
        logger.info("Webhook PIX Inter: %s", str(payload)[:200])
        _log_webhook(payload, "pix", "/webhooks/inter/pix")

        pix_list = payload.get("pix", [payload])
        resultados = []
        for pix in pix_list:
            resultado = await _processar_pix_recebido(pix)
            resultados.append(resultado)

        return {"status": "ok", "processados": resultados}

    except Exception as e:
        logger.error("Webhook PIX erro: %s", e)
        return {"status": "erro", "detalhe": str(e)}


@router.post(
    "/inter/boleto",
    summary="Webhook Boleto — notificações Inter",
    include_in_schema=False,
)
async def webhook_boleto(request: Request):
    """Receptor de webhooks de boleto pago do Banco Inter."""
    try:
        body = await request.body()
        payload = json.loads(body)
        logger.info("Webhook Boleto Inter: %s", str(payload)[:200])
        _log_webhook(payload, "boleto", "/webhooks/inter/boleto")
        # O Inter envia LISTA de eventos ([{...}, ...]); aceitar também dict único
        # e envelope {"boletos": [...]}. Antes: lista crua estourava 'list' has no .get.
        if isinstance(payload, list):
            eventos = payload
        elif isinstance(payload, dict):
            eventos = payload.get("boletos", [payload])
        else:
            eventos = []
        resultados = [await _processar_boleto_pago(ev) for ev in eventos if isinstance(ev, dict)]
        return {"status": "ok", "processados": len(resultados), "resultados": resultados}
    except Exception as e:
        logger.error("Webhook Boleto erro: %s", e)
        return {"status": "erro", "detalhe": str(e)}


def _build_inter_adapter():
    """
    Constrói InterAdapter com credenciais do .env.credentials
    (mesmo padrão do banking_controller._get_banking_service).
    """
    from modules.integrations.banking.adapters import BankCredentials
    from modules.integrations.banking.adapters.inter import InterAdapter

    env = _load_inter_credentials()
    inter_client_id = env.get("INTER_CLIENT_ID") or os.getenv("INTER_CLIENT_ID")
    inter_secret = env.get("INTER_CLIENT_SECRET") or os.getenv("INTER_CLIENT_SECRET")
    inter_cert = env.get("INTER_CERT_PATH") or os.getenv("INTER_CERT_PATH")
    inter_key = env.get("INTER_KEY_PATH") or os.getenv("INTER_KEY_PATH")
    inter_env = env.get("INTER_ENVIRONMENT") or os.getenv("INTER_ENVIRONMENT", "production")

    if not all([inter_client_id, inter_secret, inter_cert, inter_key]):
        return None, "Credenciais Inter não configuradas"

    creds = BankCredentials(
        client_id=inter_client_id,
        client_secret=inter_secret,
        certificate_path=inter_cert,
        private_key_path=inter_key,
        environment=inter_env,
    )
    return InterAdapter(creds), None


@router.post("/inter/configurar", summary="Configurar webhooks no painel Inter")
async def configurar_webhooks_inter():
    """
    Registra os webhooks no Banco Inter apontando para
    os endpoints do Conecta PRO.
    """
    adapter, erro = _build_inter_adapter()
    if adapter is None:
        raise HTTPException(status_code=503, detail=erro)

    base_url = os.getenv("APP_BASE_URL", "https://erp.conectamais.pro")
    try:
        pix_result = await adapter.register_pix_webhook(f"{base_url}/api/v1/webhooks/inter/pix")
        boleto_result = await adapter.register_boleto_webhook(f"{base_url}/api/v1/webhooks/inter/boleto")
        return {
            "pix_webhook": pix_result,
            "boleto_webhook": boleto_result,
            "urls_registradas": {
                "pix": f"{base_url}/api/v1/webhooks/inter/pix",
                "boleto": f"{base_url}/api/v1/webhooks/inter/boleto",
            },
        }
    finally:
        await adapter.close()


@router.get("/inter/status", summary="Status dos webhooks configurados")
async def status_webhooks():
    """Consulta webhooks configurados no Inter."""
    adapter, erro = _build_inter_adapter()
    if adapter is None:
        return {"configurado": False, "motivo": erro}

    try:
        pix = await adapter.get_pix_webhook()
        return {"pix": pix, "configurado": pix.get("success", False)}
    finally:
        await adapter.close()


@router.post(
    "/inter/pagamento-pix",
    summary="Webhook — PIX enviado confirmado",
    include_in_schema=False,
)
async def webhook_pagamento_pix(request: Request):
    """
    Notificação quando PIX enviado é confirmado pelo Inter.
    Atualiza payable_account para status pago.
    """
    try:
        body = await request.body()
        payload = json.loads(body)
        logger.info("Webhook PIX enviado: %s", str(payload)[:200])
        _log_webhook(payload, "pagamento_pix", "/webhooks/inter/pagamento-pix")

        txid = payload.get("txid", "")
        valor = float(payload.get("valor", 0))
        e2e_id = payload.get("endToEndId", "")
        conciliado = False

        if txid or e2e_id:
            conn = _get_conn()
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    UPDATE payable_accounts SET
                        status = 'pago',
                        transacao_bancaria_id = %s,
                        updated_at = NOW()
                    WHERE (transacao_bancaria_id = %s OR comprovante_id = %s)
                      AND status = 'pendente'
                    RETURNING id
                    """,
                    (e2e_id or txid, txid, e2e_id),
                )
                row = cur.fetchone()
                conciliado = row is not None
                conn.commit()
            finally:
                cur.close()
                conn.close()

        return {"status": "ok", "tipo": "pagamento_pix", "valor": valor, "conciliado": conciliado}
    except Exception as e:
        logger.error("Webhook pagamento PIX erro: %s", e)
        return {"status": "erro", "detalhe": str(e)}


@router.post(
    "/inter/pagamento-boleto",
    summary="Webhook — Boleto pago por você confirmado",
    include_in_schema=False,
)
async def webhook_pagamento_boleto(request: Request):
    """
    Notificação quando boleto que você pagou é confirmado.
    Atualiza payable_account para status pago.
    """
    try:
        body = await request.body()
        payload = json.loads(body)
        logger.info("Webhook boleto pago: %s", str(payload)[:200])
        _log_webhook(payload, "pagamento_boleto", "/webhooks/inter/pagamento-boleto")

        payment_id = payload.get("codigoPagamento", payload.get("idPagamento", ""))
        valor = float(payload.get("valor", payload.get("valorPago", 0)))
        conciliado = False

        if payment_id:
            conn = _get_conn()
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    UPDATE payable_accounts SET
                        status = 'pago',
                        transacao_bancaria_id = %s,
                        updated_at = NOW()
                    WHERE (transacao_bancaria_id = %s OR comprovante_id = %s)
                      AND status = 'pendente'
                    RETURNING id
                    """,
                    (payment_id, payment_id, payment_id),
                )
                row = cur.fetchone()
                conciliado = row is not None
                conn.commit()
            finally:
                cur.close()
                conn.close()

        return {"status": "ok", "tipo": "pagamento_boleto", "valor": valor, "conciliado": conciliado}
    except Exception as e:
        logger.error("Webhook pagamento boleto erro: %s", e)
        return {"status": "erro", "detalhe": str(e)}


@router.post(
    "/inter/recorrencia",
    summary="Webhook — Recorrência PIX Automático",
    include_in_schema=False,
)
async def webhook_recorrencia(request: Request):
    """Notificação de eventos de recorrência PIX Automático."""
    try:
        body = await request.body()
        payload = json.loads(body)
        logger.info("Webhook recorrência: %s", str(payload)[:200])
        _log_webhook(payload, "recorrencia", "/webhooks/inter/recorrencia")
        return {"status": "ok", "tipo": "recorrencia", "payload": payload}
    except Exception as e:
        logger.error("Webhook recorrência erro: %s", e)
        return {"status": "erro", "detalhe": str(e)}


@router.post(
    "/inter/cobranca-recorrente",
    summary="Webhook — Cobrança Recorrente confirmada",
    include_in_schema=False,
)
async def webhook_cobranca_recorrente(request: Request):
    """
    Notificação quando cobrança recorrente é paga.
    Atualiza receivable_account do cliente.
    """
    try:
        body = await request.body()
        payload = json.loads(body)
        logger.info("Webhook cobrança recorrente: %s", str(payload)[:200])
        _log_webhook(payload, "cobranca_recorrente", "/webhooks/inter/cobranca-recorrente")

        txid = payload.get("txid", "")
        valor = float(payload.get("valor", 0))
        conciliado = False

        if txid:
            conn = _get_conn()
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    UPDATE receivable_accounts SET
                        status = 'recebido',
                        data_recebimento = CURRENT_DATE,
                        updated_at = NOW()
                    WHERE pix_txid = %s
                      AND status = 'pendente'
                    RETURNING id, client_id
                    """,
                    (txid,),
                )
                row = cur.fetchone()
                conciliado = row is not None
                if row:
                    logger.info("Cobrança recorrente conciliada: %s", row[0])
                conn.commit()
            finally:
                cur.close()
                conn.close()

        return {"status": "ok", "tipo": "cobranca_recorrente", "valor": valor, "conciliado": conciliado}
    except Exception as e:
        logger.error("Webhook cobrança recorrente erro: %s", e)
        return {"status": "erro", "detalhe": str(e)}
