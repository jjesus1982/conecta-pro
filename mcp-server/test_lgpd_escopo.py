"""Ferramenta que toca PESSOA sem escopo LGPD declarado não sobe.

Bloco 7 do prompt de 11/09/2026. O `folha_dp` expõe CPF, holerite, ASO e dado de saúde
ocupacional — dado pessoal, parte dele sensível. O Jordan foi explícito: *"não pretendo
abrir esse domínio por conta própria; preciso que o sistema DECLARE o escopo, em vez de eu
decidir caso a caso"*.

⭐ FAIL-CLOSED. Classificar 55 ferramentas à mão erra em algumas, e a errada tem de errar
para o lado que protege: `lgpd_escopo.nivel()` devolve `sensivel` para quem não está na
tabela. Esta trava impede que o erro fique invisível — tool nova que toca pessoa REPROVA o
build até alguém decidir o nível dela.

⚠️ A trava mede o CÓDIGO da ferramenta, não o nome. `folha_dashboard` e `baixar_holerite_pdf`
têm a mesma palavra no nome e níveis opostos; o que separa é a rota que cada uma chama.

    python test_lgpd_escopo.py
"""
from __future__ import annotations

import inspect
import re
from datetime import date

import lgpd_escopo as L
import server as S
from tool_risk_manifest import TOOL_RISK

# Rotas e termos que indicam contato com pessoa identificável ou dado sensível.
_TOCA_PESSOA = re.compile(
    r"people-management|/folha|/ponto|/aso\b|holerite|rescis|ferias|colaborador|"
    r"funcionario|/epi|esocial|beneficiari", re.I)
# ferramentas genéricas que tocam pessoa só porque despacham outras — classificar não ajuda
_DESPACHANTES = {"ensaiar", "no_sandbox", "executar_em_segundo_plano",
                 "pendencias_acionaveis", "conecta_pro_capabilities", "consultar_auditoria"}


def _tools_que_tocam_pessoa() -> list[str]:
    fora = []
    for nome in sorted(TOOL_RISK):
        if nome in _DESPACHANTES or not hasattr(S, nome):
            continue
        try:
            src = inspect.getsource(getattr(S, nome))
        except Exception:  # noqa: BLE001
            continue
        if _TOCA_PESSOA.search(src) or _TOCA_PESSOA.search(nome):
            fora.append(nome)
    return fora


def test_toda_tool_de_pessoa_tem_nivel() -> None:
    sem = [n for n in _tools_que_tocam_pessoa() if n not in L.NIVEL]
    assert not sem, (
        f"{len(sem)} ferramenta(s) tocam dado de pessoa e não têm nível LGPD declarado:\n"
        "    " + "\n    ".join(sem)
        + "\n  Classifique em lgpd_escopo.NIVEL: agregado | identificado_operacional | "
          "sensivel.\n  Sem classe elas são tratadas como `sensivel` — o que protege, mas "
          "esconde a decisão.")
    print(f"OK as {len(_tools_que_tocam_pessoa())} tools de pessoa têm nível declarado")


def test_nivel_desconhecido_e_sensivel() -> None:
    """A postura fail-closed tem de estar no CÓDIGO, não só na intenção."""
    assert L.nivel("tool_que_nunca_existiu") == L.SENSIVEL, (
        "tool desconhecida não caiu em `sensivel` — o padrão deixou de proteger")
    print("OK desconhecida cai em `sensivel`")


def test_niveis_sao_os_tres() -> None:
    validos = {L.AGREGADO, L.OPERACIONAL, L.SENSIVEL}
    # NAO_SE_APLICA não entra em NIVEL: ele é a ausência de dado pessoal, declarada em
    # SEM_DADO_PESSOAL. Misturar os dois conjuntos faria "não se aplica" parecer um nível
    # de acesso, e ele é o contrário disso.
    assert not (set(L.NIVEL.values()) & {L.NAO_SE_APLICA}), (
        "NAO_SE_APLICA foi usado como nível em NIVEL — declare em SEM_DADO_PESSOAL")
    assert not (set(L.NIVEL) & L.SEM_DADO_PESSOAL), (
        f"nas duas listas: {set(L.NIVEL) & L.SEM_DADO_PESSOAL}")
    errados = {n: v for n, v in L.NIVEL.items() if v not in validos}
    assert not errados, f"nível fora dos três: {errados}"
    assert validos <= set(L.O_QUE_SIGNIFICA), "falta a tradução de algum nível"
    print(f"OK {len(L.NIVEL)} classificações, todas nos três níveis")


def test_holerite_e_cpf_sao_sensiveis() -> None:
    """Âncora explícita: se estas mudarem de lado, é erro, não decisão."""
    for nome in ("baixar_holerite_pdf", "ficha_funcionario", "buscar_funcionario_por_cpf",
                 "calcular_verbas_rescisorias", "asos_vencendo"):
        assert L.nivel(nome) == L.SENSIVEL, f"{nome} deixou de ser sensível"
    for nome in ("folha_dashboard", "estatisticas_funcionarios"):
        assert L.nivel(nome) == L.AGREGADO, f"{nome} virou mais restrito que precisa"
    print("OK holerite/CPF/ASO sensíveis; dashboard agregado")


def test_concessao_tem_validade_e_limite() -> None:
    """Autorização sem prazo vira permanente por esquecimento."""
    c = L.CONCESSAO
    assert c["tools"], "concessão vazia"
    assert c["concedido_por"] and c["motivo"], "concessão sem autor ou sem motivo"
    assert date.fromisoformat(c["valido_ate"]) > date.fromisoformat(c["concedido_em"]), \
        "validade da concessão não é posterior à concessão"
    assert all(L.nivel(t) == L.SENSIVEL for t in c["tools"]), (
        "a concessão só faz sentido sobre tool SENSÍVEL — as outras não precisam dela")
    # o que ela deliberadamente NÃO cobre
    for proibida in ("baixar_holerite_pdf", "buscar_funcionario_por_cpf"):
        assert not L.concessao_vale_para(proibida), (
            f"{proibida} entrou na concessão de operação normal — holerite individual e CPF "
            f"exigem pedido específico")
    print(f"OK concessão de {len(c['tools'])} tools, com autor, motivo e validade "
          f"{c['valido_ate']}")


def test_declaracao_chega_ao_agente() -> None:
    d = L.declarar("baixar_holerite_pdf")
    assert d["lgpd_nivel"] == L.SENSIVEL and d["lgpd_autorizado"] is False
    assert "pedido específico" in d["lgpd_aviso"]
    d2 = L.declarar("asos_vencendo")
    assert d2["lgpd_autorizado"] is True and "concessão" in d2["lgpd_aviso"].lower()
    d3 = L.declarar("folha_dashboard")
    assert d3["lgpd_nivel"] == L.AGREGADO and "lgpd_autorizado" not in d3
    # ⭐ o que NÃO toca pessoa não pode sair rotulado como dado sensível
    d4 = L.declarar("inter_saldo")
    assert d4["lgpd_nivel"] == L.NAO_SE_APLICA, d4
    assert "lgpd_autorizado" not in d4, "saldo da empresa não precisa de autorização LGPD"
    for t in ("baixar_proposta_pdf", "baixar_contrato_pdf", "listar_clientes"):
        assert L.nivel(t) == L.NAO_SE_APLICA, f"{t} voltou a ser tratado como sensível"
    print("OK a declaração diz o nível E se está autorizado, antes do acesso")


if __name__ == "__main__":
    for fn in (test_toda_tool_de_pessoa_tem_nivel, test_nivel_desconhecido_e_sensivel,
               test_niveis_sao_os_tres, test_holerite_e_cpf_sao_sensiveis,
               test_concessao_tem_validade_e_limite, test_declaracao_chega_ao_agente):
        fn()
        print(f"PASS {fn.__name__}")
    print("TEST test_lgpd_escopo PASS")
