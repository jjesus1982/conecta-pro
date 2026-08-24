"""O encaminhamento só cala o agente se o humano REALMENTE foi avisado.

Entre 16/06 e 11/08 nove leads ouviram "já passei pro Jordan" e ficaram
esperando: o aviso saía para um endereço fantasma no WhatsApp, e mesmo assim o
código gravava o marcador 'trf' (agente calado 12h) e devolvia o nome do
responsável. Cliente sem o robô e sem o humano, no minuto mais quente.

Este teste trava as DUAS pontas da regra: aviso entregue -> silencia; aviso
não entregue -> NÃO silencia e o agente é instruído a continuar.
"""

import asyncio
from contextlib import asynccontextmanager

import pytest

from modules.integrations.connectors.whatsapp import agent_service as S


class _FakeDB:
    def __init__(self, sql):
        self.sql = sql

    async def execute(self, stmt, params=None):
        q = str(stmt)
        self.sql.append((q, params or {}))
        # o sino precisa de pelo menos um admin, senão não há INSERT para observar
        linhas = [("admin-uid",)] if "FROM users" in q else []

        class _R:
            def first(self_inner):
                return None

            def fetchall(self_inner):
                return linhas

        return _R()

    async def commit(self):
        pass


def _montar(monkeypatch, entregue: bool):
    """Prepara o cenário: assign_team OK, envio de WhatsApp entregue ou não."""
    sql: list = []

    @asynccontextmanager
    async def _factory():
        yield _FakeDB(sql)

    class _Svc:
        async def assign_team(self, conv, team):
            return {"status": "assigned"}

    monkeypatch.setattr(S, "async_session_factory", _factory)
    monkeypatch.setattr(S, "_resolve_lead_id", lambda db, c: asyncio.sleep(0, result=None))
    monkeypatch.setattr(S, "_enviar_whatsapp_direto", lambda n, m: asyncio.sleep(0, result=entregue))
    import modules.integrations.connectors.whatsapp.service as svc_mod

    monkeypatch.setattr(svc_mod, "whatsapp_service", _Svc())
    return sql


def _tem_trf(sql) -> bool:
    return any("INSERT INTO cwi_message_log" in q for q, _ in sql)


@pytest.mark.asyncio
async def test_aviso_entregue_silencia_o_agente(monkeypatch):
    sql = _montar(monkeypatch, entregue=True)
    out = await S._tool_transferir_conversa({"setor": "comercial"}, 999)
    assert out["ok"] is True
    assert out.get("responsavel")
    assert _tem_trf(sql), "aviso entregue tem de gravar 'trf' e calar o agente"


@pytest.mark.asyncio
async def test_aviso_perdido_nao_cala_o_agente(monkeypatch):
    sql = _montar(monkeypatch, entregue=False)
    out = await S._tool_transferir_conversa({"setor": "comercial"}, 999)
    assert out["ok"] is False
    assert "responsavel" not in out
    assert not _tem_trf(sql), "sem aviso entregue o agente NÃO pode ficar calado"
    assert any("communication_notifications" in q for q, _ in sql), "a perda tem de aparecer no sino"
