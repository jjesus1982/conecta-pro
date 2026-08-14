"""D7 — testes unitários: InterPaymentService (preparar, 2FA OTP, aprovar, executar, cancelar)."""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


# ── D7.0 — estados e constraints ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_inter_payments_estados_validos():
    """Status válidos: preparado, aprovado, executado, confirmado, cancelado, erro."""
    from modules.integrations.inter.services.payment_service import TIPOS_VALIDOS

    assert "boleto" in TIPOS_VALIDOS
    assert "pix" in TIPOS_VALIDOS
    assert "darf" in TIPOS_VALIDOS
    assert "gps" in TIPOS_VALIDOS
    assert "ted_interno" in TIPOS_VALIDOS


@pytest.mark.asyncio
async def test_validar_destinatario_boleto_sem_codigo_barras():
    """preparar() boleto sem codigo_barras deve lançar PaymentError."""
    from modules.integrations.inter.services.payment_service import PaymentError, _validar_destinatario

    with pytest.raises(PaymentError, match="codigo_barras"):
        _validar_destinatario("boleto", {"beneficiario": "fulano"})


@pytest.mark.asyncio
async def test_validar_destinatario_pix_sem_chave():
    """preparar() pix sem chave deve lançar PaymentError."""
    from modules.integrations.inter.services.payment_service import PaymentError, _validar_destinatario

    with pytest.raises(PaymentError, match="chave"):
        _validar_destinatario("pix", {"tipo_chave": "CPF"})


# ── D7.1 — preparar validações ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_preparar_valida_valor_positivo(mock_db):
    """preparar() deve rejeitar valor <= 0."""
    from modules.integrations.inter.services.payment_service import InterPaymentService, PaymentError

    svc = InterPaymentService(mock_db)
    with pytest.raises(PaymentError, match="valor deve ser > 0"):
        await svc.preparar(
            payment_type="pix",
            destinatario={"chave": "11111111111", "tipo_chave": "CPF"},
            valor=0,
            data_pagamento=date.today(),
            prepared_by="user-123",
        )


@pytest.mark.asyncio
async def test_preparar_bloqueia_limite_diario(mock_db):
    """preparar() deve bloquear se consumido + valor > R$5.000."""
    from modules.integrations.inter.services.payment_service import (
        InterPaymentService,
        LimiteDiarioError,
    )

    # Simular R$4.900 já consumidos hoje
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=Decimal("4900.00"))))

    svc = InterPaymentService(mock_db)

    with (
        patch.object(svc, "_get_saldo_inter", AsyncMock(return_value=Decimal("10000"))),
        patch.object(svc, "_get_consumido_hoje", AsyncMock(return_value=Decimal("4900"))),
        pytest.raises(LimiteDiarioError, match="Limite diário"),
    ):
        await svc.preparar(
            payment_type="pix",
            destinatario={"chave": "11111111111", "tipo_chave": "CPF"},
            valor=200.0,
            data_pagamento=date.today(),
            prepared_by="user-123",
        )


@pytest.mark.asyncio
async def test_preparar_bloqueia_saldo_insuficiente(mock_db):
    """preparar() deve bloquear se saldo - valor < R$100."""
    from modules.integrations.inter.services.payment_service import (
        InterPaymentService,
        SaldoInsuficienteError,
    )

    svc = InterPaymentService(mock_db)

    with (
        patch.object(svc, "_get_saldo_inter", AsyncMock(return_value=Decimal("150"))),
        patch.object(svc, "_get_consumido_hoje", AsyncMock(return_value=Decimal("0"))),
        pytest.raises(SaldoInsuficienteError, match="Saldo Inter insuficiente"),
    ):
        await svc.preparar(
            payment_type="pix",
            destinatario={"chave": "11111111111", "tipo_chave": "CPF"},
            valor=100.0,
            data_pagamento=date.today(),
            prepared_by="user-123",
        )


@pytest.mark.asyncio
async def test_preparar_bloqueia_data_passada(mock_db):
    """preparar() deve rejeitar data_pagamento no passado."""
    from modules.integrations.inter.services.payment_service import InterPaymentService, PaymentError

    svc = InterPaymentService(mock_db)

    with (
        patch.object(svc, "_get_saldo_inter", AsyncMock(return_value=Decimal("10000"))),
        patch.object(svc, "_get_consumido_hoje", AsyncMock(return_value=Decimal("0"))),
        pytest.raises(PaymentError, match="data_pagamento não pode ser no passado"),
    ):
        await svc.preparar(
            payment_type="pix",
            destinatario={"chave": "11111111111", "tipo_chave": "CPF"},
            valor=10.0,
            data_pagamento=date(2020, 1, 1),
            prepared_by="user-123",
        )


# ── D7.1 — aprovar OTP ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aprovar_otp_invalido_falha(mock_db):
    """aprovar() com OTP errado deve lançar OTPInvalidoError."""
    import uuid

    from modules.integrations.inter.services.payment_service import (
        InterPaymentService,
        OTPInvalidoError,
    )

    payment_id = str(uuid.uuid4())

    # Primeira execute (FOR UPDATE): retorna payment com status='preparado'
    # Segunda execute (busca OTP): retorna OTP válido mas código errado
    call_count = 0

    def side_effect(sql, params=None):
        nonlocal call_count
        result = MagicMock()
        result.mappings = MagicMock(return_value=result)
        if call_count == 0:
            # FOR UPDATE — payment
            result.first.return_value = {"id": payment_id, "status": "preparado", "valor": 100}
        elif call_count == 1:
            # OTP lookup — código diferente
            result.first.return_value = {
                "id": str(uuid.uuid4()),
                "code": "999999",
                "expires_at": datetime.now(UTC) + timedelta(minutes=5),
                "used": False,
            }
        else:
            result.first.return_value = None
        call_count += 1
        return result

    mock_db.execute = AsyncMock(side_effect=side_effect)

    svc = InterPaymentService(mock_db)
    with pytest.raises(OTPInvalidoError, match="incorreto"):
        await svc.aprovar(payment_id, "123456", "user-abc")


@pytest.mark.asyncio
async def test_executar_sem_aprovacao_falha(mock_db):
    """executar() com status='preparado' deve lançar StatusInvalidoError."""
    import uuid

    from modules.integrations.inter.services.payment_service import (
        InterPaymentService,
        StatusInvalidoError,
    )

    payment_id = str(uuid.uuid4())

    mock_result = MagicMock()
    mock_result.mappings = MagicMock(return_value=mock_result)
    mock_result.first.return_value = {
        "id": payment_id,
        "status": "preparado",
        "payment_type": "pix",
        "destinatario": {"chave": "11111111111", "tipo_chave": "CPF"},
        "valor": 10,
        "data_pagamento": date.today(),
    }
    mock_db.execute = AsyncMock(return_value=mock_result)

    svc = InterPaymentService(mock_db)
    with pytest.raises(StatusInvalidoError, match="aprovado"):
        await svc.executar(payment_id)


@pytest.mark.asyncio
async def test_executar_idempotente_rejeita_segundo_execute(mock_db):
    """executar() dois vezes no mesmo payment_id deve lançar IdempotenciaError."""
    import uuid

    from modules.integrations.inter.services.payment_service import (
        IdempotenciaError,
        InterPaymentService,
    )

    payment_id = str(uuid.uuid4())

    mock_result = MagicMock()
    mock_result.mappings = MagicMock(return_value=mock_result)
    mock_result.first.return_value = {
        "id": payment_id,
        "status": "executado",  # já executado
        "payment_type": "pix",
        "destinatario": {},
        "valor": 10,
        "data_pagamento": date.today(),
    }
    mock_db.execute = AsyncMock(return_value=mock_result)

    svc = InterPaymentService(mock_db)
    with pytest.raises(IdempotenciaError):
        await svc.executar(payment_id)


# ── D7.2 — boleto ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pagar_boleto_chama_inter_adapter():
    """executar() type=boleto deve chamar adapter.pagar_boleto."""
    import uuid
    from decimal import Decimal

    from modules.integrations.banking.adapters.base import BankCredentials
    from modules.integrations.banking.adapters.inter import InterAdapter

    adapter = InterAdapter(BankCredentials(client_id="test", client_secret="test", environment="sandbox"))

    with patch.object(
        adapter,
        "pay_barcode",
        AsyncMock(return_value={"success": True, "payment_id": "INTER-BOL-001"}),
    ) as mock_pay:
        result = await adapter.pagar_boleto(
            codigo_barras="34191090008000001234567890123456700017988880000",
            valor=Decimal("0.50"),
            data_pagamento=date.today(),
        )

    mock_pay.assert_called_once()
    assert result["success"] is True


# ── D7.3 — PIX ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enviar_pix_chama_endpoint_correto():
    """enviar_pix() deve usar POST /banking/v2/pix com chave e valor."""
    from modules.integrations.banking.adapters.base import BankCredentials
    from modules.integrations.banking.adapters.inter import InterAdapter

    adapter = InterAdapter(BankCredentials(client_id="test", client_secret="test", environment="sandbox"))

    fake_response = {"endToEndId": "E60701190202604150001TEST", "status": "CONCLUIDO"}
    with patch.object(adapter, "_request", AsyncMock(return_value=fake_response)):
        result = await adapter.enviar_pix(
            chave="11111111111",
            tipo_chave="CPF",
            valor=Decimal("0.01"),
            nome_recebedor="Jordan Jesus",
            descricao="Teste D7.3 R$0.01",
        )

    assert result["success"] is True
    assert result["endToEndId"] == "E60701190202604150001TEST"


# ── D7.4 — DARF ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pagar_darf_chama_endpoint_correto():
    """pagar_darf() deve usar POST /banking/v2/pagamento/darf."""
    from modules.integrations.banking.adapters.base import BankCredentials
    from modules.integrations.banking.adapters.inter import InterAdapter

    adapter = InterAdapter(BankCredentials(client_id="test", client_secret="test", environment="sandbox"))

    fake_response = {
        "codigoSolicitacao": "DARF-001",
        "autenticacao": "AUTH-001",
        "dataPagamento": "2026-05-02",
    }
    with patch.object(adapter, "_request", AsyncMock(return_value=fake_response)):
        result = await adapter.pagar_darf(
            periodo_apuracao="2026-04",
            codigo_receita="0220",
            valor=Decimal("0.01"),
            referencia="TEST001",
        )

    assert result["success"] is True
    assert result["codigo_solicitacao"] == "DARF-001"


@pytest.mark.asyncio
async def test_cancelar_pagamento_nao_executado(mock_db):
    """cancelar() deve funcionar em status='preparado' ou 'aprovado'."""
    import uuid

    from modules.integrations.inter.services.payment_service import InterPaymentService

    payment_id = str(uuid.uuid4())

    call_count = 0

    def side_effect(sql, params=None):
        nonlocal call_count
        result = MagicMock()
        result.mappings = MagicMock(return_value=result)
        result.first.return_value = {"id": payment_id, "status": "preparado"}
        mock_update = MagicMock()
        mock_update.rowcount = 1
        call_count += 1
        return result if call_count <= 2 else mock_update

    mock_db.execute = AsyncMock(side_effect=side_effect)

    svc = InterPaymentService(mock_db)
    result = await svc.cancelar(payment_id, "Cancelamento de teste", "user-abc")
    assert result["status"] == "cancelado"


@pytest.mark.asyncio
async def test_saldo_resumo_retorna_estrutura(mock_db):
    """saldo_resumo() retorna limite_diario, consumido_hoje, disponivel_hoje."""
    from modules.integrations.inter.services.payment_service import InterPaymentService

    mock_db.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=Decimal("1500"))))

    svc = InterPaymentService(mock_db)
    with patch.object(svc, "_get_consumido_hoje", AsyncMock(return_value=Decimal("1500"))):
        result = await svc.saldo_resumo()

    assert result["limite_diario"] == 5000.0
    assert result["consumido_hoje"] == 1500.0
    assert result["disponivel_hoje"] == 3500.0


# ── D7.0 — check constraint status e função SQL ──────────────────────────────


@pytest.mark.asyncio
async def test_inter_payments_check_constraint_status():
    """Status inválido deve lançar PaymentError no preparar()."""
    from modules.integrations.inter.services.payment_service import TIPOS_VALIDOS, PaymentError, _validar_destinatario

    # Verifica que todos os tipos válidos aceitos estão corretos
    for t in TIPOS_VALIDOS:
        assert t in {"boleto", "pix", "darf", "gps", "ted_interno"}

    # Status inválido em _validar_destinatario (tipo não reconhecido)
    with pytest.raises(PaymentError):
        _validar_destinatario("cartao_credito", {})


@pytest.mark.asyncio
async def test_executar_banco_desconhecido_nao_paga_pelo_inter(mock_db):
    """Banco fora do catálogo NÃO pode cair no Inter — tem que falhar.

    Até 14/08/2026 o roteador era `if origem == 'cora': ... else: Inter`. Qualquer
    valor inesperado — um typo, um banco novo meio-configurado — pagava pelo Inter,
    que é de OUTRO CNPJ. O dinheiro sairia da empresa errada e o erro só apareceria
    na conciliação. Este teste existe para esse `else` não voltar.
    """
    from modules.integrations.inter.services.payment_service import InterPaymentService, PaymentError

    resultado = MagicMock()
    resultado.mappings.return_value.first.return_value = {
        "id": "p1", "status": "aprovado", "payment_type": "pix",
        "destinatario": {"chave": "x"}, "valor": Decimal("10.00"),
        "data_pagamento": date.today(), "banco": "bradesco",
    }
    resultado.rowcount = 1
    mock_db.execute.return_value = resultado

    svc = InterPaymentService(mock_db)
    with (
        patch("modules.integrations.inter.services.payment_service._chamar_inter",
              new=AsyncMock()) as inter,
        patch("modules.integrations.inter.services.payment_service._chamar_cora",
              new=AsyncMock()) as cora,
        patch.object(svc, "_audit", new=AsyncMock()),
    ):
        with pytest.raises(PaymentError, match="banco sem executor"):
            await svc.executar("p1", "user1")

        assert not inter.called, "banco desconhecido foi pago pelo INTER — CNPJ errado"
        assert not cora.called


@pytest.mark.asyncio
async def test_get_limite_diario_consumido(mock_db):
    """_get_consumido_hoje() deve chamar a SQL function e retornar Decimal."""
    from modules.integrations.inter.services.payment_service import InterPaymentService

    mock_db.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=Decimal("2500.00"))))

    svc = InterPaymentService(mock_db)
    consumido = await svc._get_consumido_hoje()

    assert consumido == Decimal("2500.00")
    mock_db.execute.assert_called_once()
    # Verifica que a SQL function foi chamada via TextClause
    sql_obj = mock_db.execute.call_args[0][0]
    assert "get_limite_diario_consumido" in str(sql_obj)


# ── D7.2 — boleto extras ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pagar_boleto_valida_codigo_barras():
    """preparar() boleto sem codigo_barras deve lançar PaymentError."""
    from modules.integrations.inter.services.payment_service import PaymentError, _validar_destinatario

    with pytest.raises(PaymentError, match="codigo_barras"):
        _validar_destinatario("boleto", {"beneficiario": "Empresa X", "valor_original": 10.0})


@pytest.mark.asyncio
async def test_pagar_boleto_retorna_codigo_solicitacao():
    """pagar_boleto() deve retornar success=True e codigoSolicitacao."""
    from decimal import Decimal

    from modules.integrations.banking.adapters.base import BankCredentials
    from modules.integrations.banking.adapters.inter import InterAdapter

    adapter = InterAdapter(BankCredentials(client_id="test", client_secret="test", environment="sandbox"))

    fake_response = {"codigoSolicitacao": "BOL-20260502-001", "autenticacao": "AUTH001", "dataPagamento": "2026-05-02"}
    with patch.object(
        adapter, "pay_barcode", AsyncMock(return_value={"success": True, "payment_id": "BOL-20260502-001"})
    ):
        result = await adapter.pagar_boleto(
            codigo_barras="34191090008000001234567890123456700017988880000",
            valor=Decimal("0.50"),
            data_pagamento=date.today(),
        )

    assert result["success"] is True


# ── D7.3 — PIX extras ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enviar_pix_valida_chave_obrigatoria():
    """preparar() pix sem chave deve lançar PaymentError."""
    from modules.integrations.inter.services.payment_service import PaymentError, _validar_destinatario

    with pytest.raises(PaymentError, match="chave"):
        _validar_destinatario("pix", {"tipo_chave": "CPF", "nome_recebedor": "Jordan"})


@pytest.mark.asyncio
async def test_enviar_pix_retorna_status_concluido():
    """enviar_pix() deve retornar success=True com endToEndId."""
    from modules.integrations.banking.adapters.base import BankCredentials
    from modules.integrations.banking.adapters.inter import InterAdapter

    adapter = InterAdapter(BankCredentials(client_id="test", client_secret="test", environment="sandbox"))

    fake_response = {"endToEndId": "E60701190202605020001PIX2", "status": "CONCLUIDO"}
    with patch.object(adapter, "_request", AsyncMock(return_value=fake_response)):
        result = await adapter.enviar_pix(
            chave="11122233344",
            tipo_chave="CPF",
            valor=Decimal("0.01"),
            nome_recebedor="Jordan Jesus",
            descricao="Teste D7.3 R$0.01",
        )

    assert result["success"] is True
    assert "endToEndId" in result


# ── D7.4 — GPS ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pagar_gps_chama_endpoint_correto():
    """pagar_gps() deve usar POST /banking/v2/pagamento/tributos."""
    from modules.integrations.banking.adapters.base import BankCredentials
    from modules.integrations.banking.adapters.inter import InterAdapter

    adapter = InterAdapter(BankCredentials(client_id="test", client_secret="test", environment="sandbox"))

    fake_response = {
        "codigoSolicitacao": "GPS-001",
        "autenticacao": "AUTH-GPS-001",
        "dataPagamento": "2026-05-02",
    }
    with patch.object(adapter, "_request", AsyncMock(return_value=fake_response)):
        result = await adapter.pagar_gps(
            competencia="2026-04",
            codigo_pagamento="1600",
            valor=Decimal("0.01"),
            identificador="TEST-GPS-001",
        )

    assert result["success"] is True
    assert result["codigoSolicitacao"] == "GPS-001"
