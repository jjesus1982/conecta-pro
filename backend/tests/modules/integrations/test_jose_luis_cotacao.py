"""Cotação do José Luís: o preço sai da tabela CCT e o INTERNO não vaza.

O interlocutor é um número de WhatsApp ANÔNIMO. Margem/custo/encargo/lucro
saindo daqui não é erro de formatação — é vazamento de dado interno para
um prospect (ou um concorrente).
"""

import pytest

from modules.integrations.connectors.whatsapp import agent_service as ag

# Espelha o retorno REAL de pricing_cct.calcular_funcao (lido em 2026-08-09).
RESULTADO_CCT = {
    "funcao": "AGP P1 Noturno",
    "adicionais": "Noturno, Hora red.",
    "salario_base": 1670.0,
    "adic_noturno": 334.0,
    "adic_hora_reduzida": 133.6,
    "adic_ronda": 0.0,
    "adic_risco": 0.0,
    "salario_bruto": 2137.6,
    "encargos": 1309.06,
    "encargos_pct": 0.6124,
    "vt": 64.5,
    "vr": 330.0,
    "beneficios": 639.5,
    "repasse": 306.5,
    "repasse_pct": 0.075,
    "custo_total": 4392.66,
    "tributos_pct": 0.1425,
    "margem": 0.15,
    "divisor": 0.7075,
    "preco": 6208.71,
    "markup_pct": 0.4134,
    "lucro_liquido": 931.31,
}


def test_projecao_calcula_mensal_e_contrato():
    out = ag._cotacao_publica(RESULTADO_CCT, postos=3, meses=12)
    assert out["ok"] is True
    assert out["funcao"] == "AGP P1 Noturno"
    assert out["postos"] == 3
    assert out["meses"] == 12
    assert out["preco_posto_mes"] == 6208.71
    assert out["mensal"] == round(6208.71 * 3, 2)
    assert out["contrato"] == round(6208.71 * 3 * 12, 2)


def test_fixture_cobre_toda_a_lista_negra():
    """Guarda do guarda: se _CAMPOS_INTERNOS_COTACAO ganhar um campo e o fixture não,
    o teste de vazamento passaria sem testar nada."""
    faltando = ag._CAMPOS_INTERNOS_COTACAO - set(RESULTADO_CCT)
    assert not faltando, f"fixture desatualizado, faltam: {sorted(faltando)}"


def test_projecao_nao_vaza_nenhum_campo_interno():
    """A trava que importa. Se este teste cair, é vazamento — não é cosmético."""
    out = ag._cotacao_publica(RESULTADO_CCT, postos=1, meses=12)
    vazados = ag._CAMPOS_INTERNOS_COTACAO & set(out)
    assert not vazados, f"campo interno no retorno público: {sorted(vazados)}"


def test_projecao_nao_vaza_valor_interno_em_nenhum_texto():
    """Nem por chave, nem embutido numa string (ex.: instrucao com o custo dentro).

    Deriva a lista do próprio _CAMPOS_INTERNOS_COTACAO: campo novo na lista negra
    passa a ser cobrado aqui sozinho, sem ninguém lembrar de editar o teste."""
    out = ag._cotacao_publica(RESULTADO_CCT, postos=1, meses=12)
    blob = " ".join(str(v) for v in out.values())
    publicos = {str(out[k]) for k in ("preco_posto_mes", "mensal", "contrato", "postos", "meses")}
    for chave in ag._CAMPOS_INTERNOS_COTACAO:
        val = str(RESULTADO_CCT[chave])
        if val in publicos or len(val) < 4:  # números curtos colidem por acaso
            continue
        assert val not in blob, f"valor interno {chave}={val} apareceu no retorno"


@pytest.mark.parametrize(
    "postos,meses,postos_ok,meses_ok",
    [(0, 0, 1, 1), (-5, -1, 1, 1), (999, 999, 200, 60), ("3", "24", 3, 24), (None, None, 1, 12)],
)
def test_projecao_clampa_entrada_do_llm(postos, meses, postos_ok, meses_ok):
    """postos/meses vêm do LLM (portanto do cliente). Nunca confiar no valor cru."""
    out = ag._cotacao_publica(RESULTADO_CCT, postos=postos, meses=meses)
    assert out["postos"] == postos_ok
    assert out["meses"] == meses_ok


# ── gate da flag ─────────────────────────────────────────────────────────────


def test_tool_ausente_com_flag_desligada(monkeypatch):
    """Default = comportamento de hoje. Sem a flag, o agente não sabe cotar."""
    monkeypatch.delenv("AGENT_COTA_EM_CHAT", raising=False)
    assert ag._tools_ativas(owner=False) is ag.TOOLS
    nomes = {t["function"]["name"] for t in ag._tools_ativas(owner=False)}
    assert "simular_preco" not in nomes


def test_tool_presente_com_flag_ligada(monkeypatch):
    monkeypatch.setenv("AGENT_COTA_EM_CHAT", "true")
    nomes = {t["function"]["name"] for t in ag._tools_ativas(owner=False)}
    assert "simular_preco" in nomes


def test_modo_gerente_nao_ganha_a_tool(monkeypatch):
    """MANAGER_TOOLS é o conjunto INTERNO. O Jordan já cota na tela do redesign;
    misturar os conjuntos é justamente o risco que o plano proíbe."""
    monkeypatch.setenv("AGENT_COTA_EM_CHAT", "true")
    assert ag._tools_ativas(owner=True) is ag.MANAGER_TOOLS
    nomes = {t["function"]["name"] for t in ag._tools_ativas(owner=True)}
    assert "simular_preco" not in nomes


async def test_dispatcher_recusa_com_flag_desligada(monkeypatch):
    """Defesa em profundidade: mesmo que o LLM invente a chamada, o dispatcher barra."""
    monkeypatch.delenv("AGENT_COTA_EM_CHAT", raising=False)
    out = await ag._exec_tool("simular_preco", {"funcao": "AGP P1 Diurno"}, conversation_id=1)
    # "nao permitida" (barrado pelo gate), NÃO "desconhecida" (que passaria por acidente
    # antes da tool existir e deixaria o teste verde sem testar o gate).
    assert out == {"erro": "tool nao permitida"}


# ── a tool, com um banco de mentira (o banco de verdade é provado na Task 4) ──

FUNCOES_FAKE = [
    {"nome": "AGP P1 Diurno", "salario_base": 1670.0, "jornada_dias": 15, "noturno": False,
     "hora_reduzida": False, "ronda": False, "periculosidade": False, "insalubridade": False},
    {"nome": "AGP P1 Noturno", "salario_base": 1670.0, "jornada_dias": 15, "noturno": True,
     "hora_reduzida": True, "ronda": False, "periculosidade": False, "insalubridade": False},
]


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *_a, **_k):
        return _FakeResult(self._rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False


def _fingir_banco(monkeypatch, rows=FUNCOES_FAKE):
    monkeypatch.setattr(ag, "async_session_factory", lambda: _FakeDB(rows))


async def test_funcao_inexistente_devolve_lista_real_e_nao_chuta(monkeypatch):
    """'Nunca fabricar dado': sem match, devolve as funções REAIS, não um preço."""
    monkeypatch.setenv("AGENT_COTA_EM_CHAT", "true")
    _fingir_banco(monkeypatch)
    out = await ag._tool_simular_preco({"funcao": "astronauta", "postos": 2})
    assert out["ok"] is False
    assert out["motivo"] == "funcao_nao_encontrada"
    assert "AGP P1 Diurno" in out["funcoes_disponiveis"]
    assert not any(k in out for k in ("preco_posto_mes", "mensal", "contrato"))


async def test_sem_funcao_pede_a_funcao_em_vez_de_cotar(monkeypatch):
    monkeypatch.setenv("AGENT_COTA_EM_CHAT", "true")
    _fingir_banco(monkeypatch)
    out = await ag._tool_simular_preco({"postos": 2})
    assert out["motivo"] == "funcao_nao_informada"
    assert out["funcoes_disponiveis"] == ["AGP P1 Diurno", "AGP P1 Noturno"]


async def test_match_parcial_e_sem_acento(monkeypatch):
    """O cliente escreve 'agp p1 noturno'; a tabela tem 'AGP P1 Noturno'."""
    monkeypatch.setenv("AGENT_COTA_EM_CHAT", "true")
    _fingir_banco(monkeypatch)
    vistos = {}

    async def _falso_calcular(_db, row, *_a, **_k):
        vistos["nome"] = row["nome"]
        return dict(RESULTADO_CCT)

    from modules.crm.services import pricing_cct

    monkeypatch.setattr(pricing_cct, "calcular_funcao", _falso_calcular)
    out = await ag._tool_simular_preco({"funcao": "p1 noturno", "postos": 2, "meses": 24})
    assert vistos["nome"] == "AGP P1 Noturno"
    assert out["ok"] is True
    assert out["mensal"] == round(RESULTADO_CCT["preco"] * 2, 2)
    assert not (ag._CAMPOS_INTERNOS_COTACAO & set(out))


# ── política do prompt ───────────────────────────────────────────────────────


def test_prompt_sem_bloco_de_preco_por_padrao(monkeypatch):
    monkeypatch.delenv("AGENT_COTA_EM_CHAT", raising=False)
    assert ag._system_prompt(owner=False) is ag.SYSTEM_PROMPT
    assert "COTAÇÃO EM CHAT" not in ag._system_prompt(owner=False)
    assert "NUNCA informe preços" in ag._system_prompt(owner=False)


def test_prompt_com_bloco_quando_ligado(monkeypatch):
    monkeypatch.setenv("AGENT_COTA_EM_CHAT", "true")
    p = ag._system_prompt(owner=False)
    assert "COTAÇÃO EM CHAT" in p
    assert "simular_preco" in p
    # A proibição original continua no texto (nada foi deletado) e o bloco vem DEPOIS:
    # a exceção é nomeada explicitamente, senão o modelo fica com duas regras sem hierarquia.
    assert p.index("NUNCA informe preços") < p.index("COTAÇÃO EM CHAT")


def test_prompt_do_gerente_intocado(monkeypatch):
    monkeypatch.setenv("AGENT_COTA_EM_CHAT", "true")
    assert ag._system_prompt(owner=True) is ag.MANAGER_PROMPT


async def test_falha_no_banco_nao_derruba_o_atendimento(monkeypatch):
    monkeypatch.setenv("AGENT_COTA_EM_CHAT", "true")

    def _explode():
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(ag, "async_session_factory", _explode)
    out = await ag._tool_simular_preco({"funcao": "AGP P1 Diurno"})
    assert out.get("erro")
    assert "preco_posto_mes" not in out
