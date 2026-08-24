"""F1 — a parede que faz a etiqueta 🟡 do manifesto AGIR.

Achado que originou (23/08/2026): `tool_risk_manifest` classificava 254 ferramentas e
`server.py` tinha ZERO referências a ele. As 54 classificações que corrigi eram etiquetas
num crachá que nenhum porteiro pedia. O único filtro vivo era `tool_scopes`, que corta por
ASSUNTO — e conter risco por assunto funciona por acidente quando tema e risco coincidem, e
falha calado quando não coincidem (`enviar_whatsapp` está em "comercial" e envia ao cliente).

O que esta parede faz, num conector marcado como AGENTE (`MCP_MODO=agente`):

    read        executa normalmente
    write_low   executa normalmente (interno, reversível)
    propose     NÃO EXECUTA — vira rascunho inerte na Central de Aprovações

A regra que a define: **quem aprova não pode ser quem pede.** A versão anterior do
`aceitar_proposta` pedia `confirmar="ACEITAR"` e devolvia essa própria senha na resposta —
para um humano lendo no Cowork era um bom aviso; para um modelo que lê a resposta era um
degrau que imprime como subir. Confirmação preenchida por quem pede é formulário, não
aprovação.

E o aprovador precisa ver a CONSEQUÊNCIA, não o nome da função. "Aprovar aceitar_proposta?"
não é decisão informada; "aceitar a proposta X: gera comissão, move o deal e cria contrato"
é. Por isso `CONSEQUENCIAS` carrega o que cada ação provoca, e é isso que vai para a tela.
"""
from __future__ import annotations

import os
from typing import Any

try:
    from tool_risk_manifest import TOOL_RISK
except Exception:  # noqa: BLE001 — sem manifesto, a parede fecha (ver `classe_de`)
    TOOL_RISK = {}

# Ligado só onde o chamador é AGENTE. No conector do Jordan (Cowork) a pessoa lê e decide na
# hora — pôr a parede lá seria transformar decisão informada em fila.
MODO_AGENTE = (os.getenv("MCP_MODO") or "").strip().lower() == "agente"

# O que o APROVADOR vê. Uma linha por consequência real, em português de gente.
# Ausente = a parede ainda barra, e a tela diz que a consequência não foi declarada — o que
# é pior de ler e melhor de errar do que uma aprovação às cegas.
CONSEQUENCIAS: dict[str, list[str]] = {
    "aceitar_proposta": [
        "marca a proposta como ACEITA",
        "GERA COMISSÃO para o vendedor (nasce pendente, mas é obrigação registrada)",
        "move a oportunidade para closed_won",
        "cria um CONTRATO em rascunho",
    ],
    "fechar_folha": ["FECHA a folha do mês — depois disso o cálculo não se refaz sozinho"],
    "calcular_folha_todos": ["recalcula a folha de TODOS os colaboradores do mês"],
    "fechar_mes_ponto": ["FECHA o mês do ponto; batida nova deixa de entrar na apuração"],
    "aprovar_ferias": ["APROVA as férias — vira evento de eSocial e afeta a folha"],
    "calcular_verbas_rescisorias": ["calcula rescisão — base do TRCT e do pagamento final"],
    "concluir_admissao": ["conclui a admissão e dispara os eventos de admissão"],
    "lancar_diaria": ["LANÇA DIÁRIA — vira valor a pagar ao diarista"],
    "gerar_lote_diarias_mes": ["programa as diárias do mês inteiro — dinheiro a pagar"],
    "registrar_custo_recorrente": ["cria custo recorrente que passa a entrar no fluxo"],
    "enviar_whatsapp": ["ENVIA MENSAGEM REAL ao cliente, em nome da empresa"],
    "enviar_nps": ["dispara pesquisa de NPS ao cliente"],
    "enviar_proposta": ["ENVIA a proposta ao cliente"],
    "enviar_proposta_completa": ["ENVIA a proposta completa ao cliente"],
    "enviar_proposta_whatsapp": ["ENVIA a proposta por WhatsApp ao cliente"],
    "followup_whatsapp": ["envia follow-up ao cliente"],
    "followup_em_lote": ["envia follow-up EM LOTE — várias pessoas de uma vez"],
    "inscrever_em_sequencia": ["inscreve numa régua que passa a ENVIAR sozinha"],
    "inscrever_lead_em_sequencia": ["inscreve o lead numa régua que passa a ENVIAR sozinha"],
    "expurgar_documentos_teste": ["APAGA documentos — irreversível"],
    "ativar_contrato": ["submete o contrato, tirando-o de rascunho"],
    "gerar_parecer_juridico": ["cria PARECER JURÍDICO no nome do escritório"],
    "analisar_processo_juridico": ["cria registro de processo jurídico"],
    "montar_kit_completo": ["dispara a montagem COMPLETA do kit (vários documentos)"],
    "buscar_documento": ["dispara montagem de kit para localizar o documento"],
    "solicitar_ferias": ["cria solicitação de férias em nome do colaborador"],
}


def classe_de(nome: str) -> str:
    """Classe de risco da tool. DESCONHECIDA = `propose` — fail-closed.

    Tool nova sem etiqueta não pode executar sozinha só porque ninguém a classificou. É a
    mesma postura do `tool_scopes`: no caso desconhecido, a parede fecha.
    """
    return TOOL_RISK.get(nome) or "propose"


def precisa_aprovacao(nome: str) -> bool:
    return MODO_AGENTE and classe_de(nome) == "propose"


def consequencias(nome: str) -> list[str]:
    return CONSEQUENCIAS.get(nome) or [
        f"consequência de `{nome}` NÃO declarada em gate_propose.CONSEQUENCIAS — "
        "aprove só se souber o que ela faz"
    ]


def payload_de_aprovacao(nome: str, argumentos: dict[str, Any]) -> dict[str, Any]:
    """O que a Central mostra. Consequência primeiro, nome da função depois."""
    return {
        "acao": nome,
        "vai_acontecer": consequencias(nome),
        "argumentos": argumentos,
        "pedido_por": "agente (Bartolo)",
        "classe": classe_de(nome),
    }


# ── A PAREDE PROPRIAMENTE DITA ────────────────────────────────────────────────────────
# `on_call_tool` do FastMCP 3.4 (API pública, conferida no container antes de usar — hoje
# eu já tinha errado uma internal supondo `_tool_manager`). É AQUI que a etiqueta 🟡 do
# manifesto deixa de ser adesivo e vira porteiro: `propose` não chega a `call_next`.
class GatePropose:
    """Barra `propose` e devolve o pedido de aprovação, sem executar nada."""

    async def on_call_tool(self, context, call_next):  # noqa: ANN001
        nome = getattr(getattr(context, "message", None), "name", "") or ""
        if not precisa_aprovacao(nome):
            return await call_next(context)

        args = getattr(getattr(context, "message", None), "arguments", None) or {}
        pedido = payload_de_aprovacao(nome, dict(args))

        # LEVA o pedido ao humano. Sem isto o gate só recusa, e o dono nunca fica sabendo
        # que foi pedido — a ação morreria na conversa, invisível.
        registro = ""
        try:
            import server as _srv  # noqa: PLC0415

            r = await _srv.erp.post("/agente/pedir-aprovacao", json=pedido)
            if isinstance(r, dict) and r.get("ok"):
                registro = f"\n\n📋 {r.get('message', 'Pedido registrado.')}"
            else:
                registro = f"\n\n⚠️ NÃO consegui registrar o pedido: {str(r)[:120]}"
        except Exception as _e:  # noqa: BLE001
            # A recusa vale MESMO sem registro — a parede não depende da Central estar de
            # pé. Mas dizer que registrou sem ter registrado seria a pior das saídas.
            registro = f"\n\n⚠️ NÃO consegui registrar o pedido ({str(_e)[:90]}) — leve à mão."
        # NÃO devolve "como confirmar". A versão anterior imprimia a própria senha
        # (confirmar="ACEITAR") — degrau que ensina a subir. Aqui não há degrau: a
        # aprovação acontece em OUTRA superfície, com OUTRA pessoa.
        texto = (
            f"⛔ `{nome}` não é executada por mim. É uma ação de classe "
            f"{pedido['classe']} — precisa de aprovação humana.\n\n"
            "O que ela provocaria:\n"
            + "\n".join(f"  • {c}" for c in pedido["vai_acontecer"])
            + "\n\nEu não tenho como aprovar o que eu mesmo pedi."
            + registro
        )
        from fastmcp.exceptions import ToolError  # noqa: PLC0415

        raise ToolError(texto)


def instalar(mcp) -> bool:
    """Instala a parede. Devolve False quando o conector NÃO é de agente."""
    if not MODO_AGENTE:
        return False
    mcp.add_middleware(GatePropose())
    return True
