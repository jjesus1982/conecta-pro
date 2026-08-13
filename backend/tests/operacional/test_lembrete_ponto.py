"""Lembretes de ponto por WhatsApp — o que quebra se a lógica quebrar.

Canal é Baileys no número da empresa: o teto de 3 mensagens por turno e o
"para na batida" são requisitos, não preferências. Estes testes guardam isso.
"""

import asyncio

from modules.operacional import lembrete_ponto
from modules.operacional.lembrete_ponto import SQL_PENDENTES, etapa_para


def test_etapa_para_janelas_exatas():
    assert etapa_para(-15) == -15  # 15 min antes do turno
    assert etapa_para(0) == 0  # no horário
    assert etapa_para(10) == 10  # 10 min depois, sem batida


def test_etapa_para_fora_das_janelas_nao_envia():
    for delta in (-60, -16, -14, -1, 1, 9, 11, 120):
        assert etapa_para(delta) is None


def test_sql_pendentes_usa_fuso_manaus_e_exclui_pj_e_homologacao():
    sql = SQL_PENDENTES.lower()
    assert "america/manaus" in sql
    assert "current_date" not in sql  # UTC viraria o dia às 20h
    assert "is_homologacao" in sql
    assert "'pj'" in sql
    assert "gp_clock_punches" in sql  # para na batida
    assert "ponto_lembrete_log" in sql  # dedup


def test_sql_nao_exclui_quem_esta_sem_telefone():
    """Requisito do Jordan: é obrigatório, não exclui ninguém.

    Quem ainda não tem telefone continua saindo na query (e é contado como
    pulado); no dia em que o número for preenchido, passa a receber sozinho,
    sem ninguém mexer em lista. Vale igual para funcionário novo.
    """
    sql = SQL_PENDENTES.lower()
    assert "telefone is not null" not in sql
    assert "celular is not null" not in sql


def test_normalizar_telefone_aceita_formatos_do_cadastro():
    """Os formatos que realmente aparecem no banco, todos válidos."""
    from modules.operacional.lembrete_ponto import normalizar_telefone

    assert normalizar_telefone("(92) 98463-5566") == "92984635566"
    assert normalizar_telefone("92 98584-7540") == "92985847540"
    assert normalizar_telefone("92984319426") == "92984319426"
    assert normalizar_telefone("9293979268") == "9293979268"  # 10 dígitos, fixo


def test_normalizar_telefone_recusa_os_quebrados_do_cadastro():
    """Números reais que existem hoje e fariam o envio falhar.

    Não completar DDD é decisão consciente: chutar '92' manda mensagem da empresa
    para um desconhecido. Melhor não enviar e reportar para o RH corrigir.
    """
    from modules.operacional.lembrete_ponto import normalizar_telefone

    assert normalizar_telefone("(99) 1361-770") is None  # 9 dígitos (Anilson)
    assert normalizar_telefone("929848631485") is None  # 12 dígitos (Euler)
    assert normalizar_telefone("982064669") is None  # sem DDD (Jeovane)
    assert normalizar_telefone(None) is None
    assert normalizar_telefone("") is None
    assert normalizar_telefone("00987654321") is None  # DDD inexistente
    assert normalizar_telefone("92884635566") is None  # 11 dígitos sem o 9 do celular


def test_telefone_invalido_nao_envia_e_e_contado(monkeypatch):
    enviados = []

    async def _fake_enviar(tel, msg):
        enviados.append(tel)
        return True

    monkeypatch.setattr(lembrete_ponto, "PONTO_LEMBRETE_ENABLED", True)
    monkeypatch.setattr(lembrete_ponto, "_optout", lambda db, tel: False)
    monkeypatch.setattr(lembrete_ponto, "_enviar", _fake_enviar)
    db = _FakeDB([dict(_LINHA, telefone="(99) 1361-770")])
    r = asyncio.run(lembrete_ponto.rodar_lembretes(db))
    assert r["pulados_telefone_invalido"] == 1
    assert r["enviados"] == 0
    assert enviados == []


def test_telefone_formatado_e_limpo_antes_de_enviar(monkeypatch):
    """O que chega no WhatsApp tem que ser só dígito, não '(92) 98463-5566'."""
    enviados = []

    async def _fake_enviar(tel, msg):
        enviados.append(tel)
        return True

    monkeypatch.setattr(lembrete_ponto, "PONTO_LEMBRETE_ENABLED", True)
    monkeypatch.setattr(lembrete_ponto, "_optout", lambda db, tel: False)
    monkeypatch.setattr(lembrete_ponto, "_enviar", _fake_enviar)
    db = _FakeDB([dict(_LINHA, telefone="(92) 98463-5566")])
    r = asyncio.run(lembrete_ponto.rodar_lembretes(db))
    assert r["enviados"] == 1
    assert enviados == ["92984635566"]


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.inserts = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        if "FROM shifts" in sql:
            return _FakeResult(self.rows)
        if "INSERT INTO ponto_lembrete_log" in sql:
            self.inserts.append(params)
        return _FakeResult([])

    def commit(self):
        pass


_LINHA = {
    "shift_id": "s1",
    "employee_id": "e1",
    "nome": "FULANO",
    "telefone": "92999999999",
    "posto": "PRIME",
    "hora": "06:00",
    "delta_min": -15,
}


def test_dry_run_nao_envia(monkeypatch):
    enviados = []
    monkeypatch.setattr(lembrete_ponto, "PONTO_LEMBRETE_ENABLED", False)
    monkeypatch.setattr(lembrete_ponto, "_enviar", lambda *a, **k: enviados.append(a))
    db = _FakeDB([dict(_LINHA)])
    r = asyncio.run(lembrete_ponto.rodar_lembretes(db))
    assert r["dry_run"] is True
    assert enviados == []
    assert db.inserts == []


def test_sem_telefone_e_contado_nao_silencioso(monkeypatch):
    monkeypatch.setattr(lembrete_ponto, "PONTO_LEMBRETE_ENABLED", True)
    monkeypatch.setattr(lembrete_ponto, "_optout", lambda db, tel: False)
    db = _FakeDB([dict(_LINHA, telefone=None, delta_min=0)])
    r = asyncio.run(lembrete_ponto.rodar_lembretes(db))
    assert r["pulados_sem_telefone"] == 1
    assert r["enviados"] == 0


def test_optout_bloqueia_envio(monkeypatch):
    monkeypatch.setattr(lembrete_ponto, "PONTO_LEMBRETE_ENABLED", True)
    monkeypatch.setattr(lembrete_ponto, "_optout", lambda db, tel: True)
    db = _FakeDB([dict(_LINHA)])
    r = asyncio.run(lembrete_ponto.rodar_lembretes(db))
    assert r["pulados_optout"] == 1
    assert r["enviados"] == 0


def test_envia_e_grava_log(monkeypatch):
    async def _fake_enviar(tel, msg):
        return True

    monkeypatch.setattr(lembrete_ponto, "PONTO_LEMBRETE_ENABLED", True)
    monkeypatch.setattr(lembrete_ponto, "_optout", lambda db, tel: False)
    monkeypatch.setattr(lembrete_ponto, "_enviar", _fake_enviar)
    db = _FakeDB([dict(_LINHA)])
    r = asyncio.run(lembrete_ponto.rodar_lembretes(db))
    assert r["enviados"] == 1
    assert len(db.inserts) == 1
    assert db.inserts[0]["e"] == -15


def test_minuto_fora_da_janela_nao_envia_mesmo_vindo_do_sql(monkeypatch):
    """Guarda contra atraso do beat: se o minuto já passou, não dispara atrasado."""

    async def _fake_enviar(tel, msg):
        return True

    monkeypatch.setattr(lembrete_ponto, "PONTO_LEMBRETE_ENABLED", True)
    monkeypatch.setattr(lembrete_ponto, "_optout", lambda db, tel: False)
    monkeypatch.setattr(lembrete_ponto, "_enviar", _fake_enviar)
    db = _FakeDB([dict(_LINHA, delta_min=-7)])
    r = asyncio.run(lembrete_ponto.rodar_lembretes(db))
    assert r["enviados"] == 0


def test_teto_por_rodada_nao_corta_em_silencio(monkeypatch):
    async def _fake_enviar(tel, msg):
        return True

    monkeypatch.setattr(lembrete_ponto, "PONTO_LEMBRETE_ENABLED", True)
    monkeypatch.setattr(lembrete_ponto, "TETO_POR_RODADA", 2)
    monkeypatch.setattr(lembrete_ponto, "_optout", lambda db, tel: False)
    monkeypatch.setattr(lembrete_ponto, "_enviar", _fake_enviar)
    db = _FakeDB([dict(_LINHA, shift_id=f"s{i}") for i in range(5)])
    r = asyncio.run(lembrete_ponto.rodar_lembretes(db))
    assert r["enviados"] == 2
    assert r["teto_rodada"] == 3
