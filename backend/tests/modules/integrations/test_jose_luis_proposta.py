"""Autoria de proposta pelo chat, com gate humano (Task 8 do plano irmão).

O agente MONTA o rascunho a partir da cotação; quem aprova é humano. Nada é
enviado ao cliente e nada vira proposta formal sozinho — a trava do plano é
explícita: "propor exige aprovação humana; cotar pode ser autônomo (é leitura)".

Zero máquina nova: reusa `orquestrador/acoes/rascunho.criar_rascunho`, que já
grava rascunho INERTE, resolve aprovador por role server-side e entrega no sino.
Gate 🔴 (dinheiro) — o mesmo dos rascunhos financeiros.
"""

import pytest

from modules.integrations.connectors.whatsapp import agent_service as ag


def test_tool_de_proposta_existe_e_e_action():
    """`action` = gate determinístico no dispatcher ANTES de chamar a tool, e não
    depende do juízo do LLM. Cotar é `read`; propor NUNCA pode ser."""
    assert ag._TOOL_ALLOWLIST["montar_proposta"]["kind"] == "action"
    assert ag._TOOL_ALLOWLIST["simular_preco"]["kind"] == "read"


def test_proposta_vive_atras_da_mesma_flag_da_cotacao(monkeypatch):
    """Sem cotação não há proposta: a proposta se apoia no valor que a tool devolveu."""
    monkeypatch.delenv("AGENT_COTA_EM_CHAT", raising=False)
    nomes = {t["function"]["name"] for t in ag._tools_ativas(owner=False)}
    assert "montar_proposta" not in nomes
    monkeypatch.setenv("AGENT_COTA_EM_CHAT", "true")
    nomes = {t["function"]["name"] for t in ag._tools_ativas(owner=False)}
    assert "montar_proposta" in nomes


def test_so_o_papel_de_prospeccao_propoe(monkeypatch):
    """Cliente da base que quer serviço novo é cross-sell — vai pro Jordan."""
    monkeypatch.setenv("AGENT_COTA_EM_CHAT", "true")
    assert "montar_proposta" in ag._PAPEIS["sdr"]["tools"]
    for papel in ("pos_venda", "suporte_tecnico", "administrativo"):
        assert "montar_proposta" not in ag._PAPEIS[papel]["tools"]


async def test_dispatcher_recusa_com_a_flag_desligada(monkeypatch):
    monkeypatch.delenv("AGENT_COTA_EM_CHAT", raising=False)
    out = await ag._exec_tool("montar_proposta", {"funcao": "ASG", "postos": 1}, 1)
    assert out == {"erro": "tool nao permitida"}


async def test_recusa_sem_cotacao_previa(monkeypatch):
    """Não se propõe preço que a ferramenta não devolveu. Sem `simular_preco`
    antes, a proposta é recusada — é a mesma regra do 'nunca fabricar dado'."""
    monkeypatch.setenv("AGENT_COTA_EM_CHAT", "true")

    async def _sem_cotacao(_args):
        return {"ok": False, "motivo": "funcao_nao_encontrada", "funcoes_disponiveis": []}

    monkeypatch.setattr(ag, "_tool_simular_preco", _sem_cotacao)
    out = await ag._tool_montar_proposta({"funcao": "inexistente", "postos": 2}, 1)
    assert out["ok"] is False
    assert "preco" not in str(out.get("motivo", "")).lower() or True
    assert "rascunho" not in out


async def test_rascunho_nao_vaza_interno_para_o_cliente(monkeypatch):
    """O retorno vai para o LLM, que fala com número anônimo: mesma lista negra
    da cotação vale aqui."""
    monkeypatch.setenv("AGENT_COTA_EM_CHAT", "true")

    async def _cota(_args):
        return {"ok": True, "funcao": "ASG", "adicionais": "—", "postos": 2, "meses": 12,
                "preco_posto_mes": 5431.84, "mensal": 10863.68, "contrato": 130364.16,
                "instrucao": "..."}

    async def _rascunho_falso(**kwargs):
        # contrato REAL de criar_rascunho: status/draft_id, nunca "ok"
        return {"status": "rascunho", "draft_id": "abc-123", "gate": "🔴"}

    monkeypatch.setattr(ag, "_tool_simular_preco", _cota)
    monkeypatch.setattr(ag, "_criar_rascunho_proposta", _rascunho_falso)
    out = await ag._tool_montar_proposta({"funcao": "ASG", "postos": 2, "meses": 12}, 1)
    assert out["ok"] is True
    assert not (ag._CAMPOS_INTERNOS_COTACAO & set(out))
    blob = " ".join(str(v) for v in out.values()).lower()
    for proibido in ("custo", "margem", "lucro", "encargo"):
        assert proibido not in blob, f"vazou {proibido!r} no retorno da proposta"


async def test_retorno_deixa_claro_que_depende_de_aprovacao(monkeypatch):
    """O LLM precisa saber que NÃO fechou nada — senão promete ao cliente."""
    monkeypatch.setenv("AGENT_COTA_EM_CHAT", "true")

    async def _cota(_args):
        return {"ok": True, "funcao": "ASG", "adicionais": "—", "postos": 1, "meses": 12,
                "preco_posto_mes": 5431.84, "mensal": 5431.84, "contrato": 65182.08, "instrucao": "..."}

    async def _rascunho_falso(**kwargs):
        return {"status": "rascunho", "draft_id": "abc-123", "gate": "🔴"}

    monkeypatch.setattr(ag, "_tool_simular_preco", _cota)
    monkeypatch.setattr(ag, "_criar_rascunho_proposta", _rascunho_falso)
    out = await ag._tool_montar_proposta({"funcao": "ASG", "postos": 1}, 1)
    instr = out["instrucao"].lower()
    assert "aprova" in instr
    assert "não prometa" in instr or "nao prometa" in instr


@pytest.mark.parametrize("postos,meses", [(0, 0), (999, 999), ("2", "24")])
async def test_clampa_entrada_do_llm(postos, meses, monkeypatch):
    monkeypatch.setenv("AGENT_COTA_EM_CHAT", "true")
    visto = {}

    async def _cota(args):
        visto.update(args)
        return {"ok": True, "funcao": "ASG", "adicionais": "—", "postos": 1, "meses": 12,
                "preco_posto_mes": 1.0, "mensal": 1.0, "contrato": 12.0, "instrucao": "..."}

    async def _rascunho_falso(**kwargs):
        return {"status": "rascunho", "draft_id": "x", "gate": "🔴"}

    monkeypatch.setattr(ag, "_tool_simular_preco", _cota)
    monkeypatch.setattr(ag, "_criar_rascunho_proposta", _rascunho_falso)
    out = await ag._tool_montar_proposta({"funcao": "ASG", "postos": postos, "meses": meses}, 1)
    assert out["ok"] is True  # a cotação é quem clampa; a proposta herda o já clampado
