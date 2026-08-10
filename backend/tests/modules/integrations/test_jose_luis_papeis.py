"""Time multi-agente por PAPÉIS no motor atual (Item 1, opção (a)).

O desenho original era o Hermes orquestrando subagentes. **Bloqueado por fato**:
o sidecar não devolve `tool_calls` (provado em 2026-08-09) — roteá-lo apagaria as
47 tools do ERP em silêncio e o agente passaria a responder de cabeça.

Opção (a), que o Jordan aceitou: especializar no motor que já existe, por
subconjunto de tools + foco de prompt, com roteamento DETERMINÍSTICO. Mesmo
molde de `classify_situacao`/`TRAVA_SITUACAO` (followups.py), que já é como a
casa faz classificação sem LLM.

Invariante que não pode cair: agente EXTERNO nunca herda tool de consultor
INTERNO. Todo papel externo é subconjunto de TOOLS — nunca de MANAGER_TOOLS.
"""

import pytest

from modules.integrations.connectors.whatsapp import agent_service as ag


def test_papeis_existem_e_cobrem_o_time():
    """O time que o Jordan pediu: pré-venda/vendas, pós-venda, suporte técnico,
    suporte administrativo. Marketing não é papel de atendimento — é quem gera o
    lead antes da conversa existir."""
    assert set(ag._PAPEIS) == {"sdr", "pos_venda", "suporte_tecnico", "administrativo"}


def test_todo_papel_externo_e_subconjunto_de_tools():
    """A fronteira interno×externo: nenhum papel externo pode ganhar tool que não
    esteja em TOOLS. Herdar do conjunto do gerente vazaria margem/folha p/ anônimo."""
    permitidas = {t["function"]["name"] for t in ag.TOOLS} | {
        t["function"]["name"] for t in ag.TOOLS_COTACAO
    }
    for papel, cfg in ag._PAPEIS.items():
        extras = set(cfg["tools"]) - permitidas
        assert not extras, f"papel {papel} pede tool fora de TOOLS: {sorted(extras)}"


def test_todo_papel_tem_foco_de_prompt():
    for papel, cfg in ag._PAPEIS.items():
        assert cfg["foco"].strip(), f"papel {papel} sem foco de prompt"
        assert "PAPEL" in cfg["foco"], f"papel {papel} não se anuncia no prompt"


@pytest.mark.parametrize(
    "texto,esperado",
    [
        # suporte técnico — equipamento com problema
        ("a câmera do bloco B parou de gravar", "suporte_tecnico"),
        ("o portão não abre mais", "suporte_tecnico"),
        ("o interfone está mudo", "suporte_tecnico"),
        # administrativo — dinheiro/documento
        ("preciso da segunda via do boleto", "administrativo"),
        ("não recebi a nota fiscal desse mês", "administrativo"),
        ("quero falar sobre o contrato", "administrativo"),
        # pós-venda / relacionamento (cliente da base, sem sinal específico)
        ("bom dia, tudo bem?", "pos_venda"),
    ],
)
def test_papel_do_cliente_da_base(texto, esperado):
    """Cliente JÁ da base: o papel sai do assunto, não da venda."""
    assert ag._papel_por_texto(texto, e_cliente=True) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "quero portaria para meu condomínio",
        "quanto custa um agente de portaria?",
        "a câmera do bloco B parou de gravar",  # nem sinal técnico muda: não é cliente
        "bom dia",
    ],
)
def test_quem_nao_e_cliente_e_sempre_sdr(texto):
    """Número anônimo é SEMPRE prospecção. Um desconhecido dizendo 'minha câmera
    quebrou' não pode cair no papel que consulta conta — é justamente o vetor de
    quem tenta se passar por cliente."""
    assert ag._papel_por_texto(texto, e_cliente=False) == "sdr"


def test_sdr_nao_alcanca_tool_de_conta():
    """SDR fala com anônimo: nada de consultar_minha_conta / abrir_ordem_servico."""
    tools_sdr = set(ag._PAPEIS["sdr"]["tools"])
    assert "consultar_minha_conta" not in tools_sdr
    assert "abrir_ordem_servico" not in tools_sdr


def test_papel_de_cliente_nao_cota_preco():
    """Cotação é ferramenta de prospecção. Cliente da base que quer preço novo é
    cross-sell — vai para o Jordan, não para a tabela."""
    for papel in ("pos_venda", "suporte_tecnico", "administrativo"):
        assert "simular_preco" not in ag._PAPEIS[papel]["tools"]


def test_tools_do_papel_saem_do_conjunto_ativo(monkeypatch):
    """O papel FILTRA o conjunto ativo; nunca acrescenta nada por fora dele."""
    monkeypatch.delenv("AGENT_COTA_EM_CHAT", raising=False)
    ativas = {t["function"]["name"] for t in ag._tools_ativas(owner=False)}
    for papel in ag._PAPEIS:
        do_papel = {t["function"]["name"] for t in ag._tools_ativas(owner=False, papel=papel)}
        assert do_papel <= ativas, f"papel {papel} extrapolou o conjunto ativo"


def test_gerente_ignora_papel(monkeypatch):
    """O modo gerente (interno, é o Jordan) não é afetado pelo roteamento externo."""
    monkeypatch.setenv("AGENT_COTA_EM_CHAT", "true")
    assert ag._tools_ativas(owner=True, papel="sdr") is ag.MANAGER_TOOLS
    assert ag._system_prompt(owner=True, papel="sdr") is ag.MANAGER_PROMPT


def test_prompt_do_papel_soma_ao_base_sem_apagar_travas(monkeypatch):
    """O foco do papel é ADITIVO: as regras invioláveis do SYSTEM_PROMPT continuam."""
    monkeypatch.delenv("AGENT_COTA_EM_CHAT", raising=False)
    p = ag._system_prompt(owner=False, papel="suporte_tecnico")
    assert ag.SYSTEM_PROMPT in p
    assert "PAPEL" in p
    assert "NUNCA informe preços" in p  # trava original intacta


def test_sem_papel_o_comportamento_e_o_de_hoje(monkeypatch):
    """Default sem papel = exatamente o que roda hoje. Roteamento é aditivo."""
    monkeypatch.delenv("AGENT_COTA_EM_CHAT", raising=False)
    assert ag._tools_ativas(owner=False) is ag.TOOLS
    assert ag._system_prompt(owner=False) is ag.SYSTEM_PROMPT
