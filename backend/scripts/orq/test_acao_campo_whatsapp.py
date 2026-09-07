"""Oráculo — ETAPA 2: o Jordan GRAVA no comercial pelo WhatsApp (28/08/2026).

Ele perguntou: "o José Luís não monta, mas manda o Bartolo montar? e o Bartolo devolve?".
A resposta medida foi que essa ida e volta NÃO existe — e não é necessária.
`criar_orcamento` é UMA função: o Bartolo a chama com o usuário autenticado da tela; aqui
ela é chamada com o MESMO usuário, resolvido pelo telefone do dono. Uma ponte a menos e
uma identidade a menos para errar.

TRÊS PAREDES EM SÉRIE, e o oráculo exercita as três:
  1. a allow-list — ação fora dela não passa, mesmo existindo no Bartolo
  2. o RBAC de módulo, dentro do dispatcher, com a identidade real do dono
  3. o `_propor_*`, que cria RASCUNHO — nada entra no funil nem sai da empresa sem clique

⚠️ E o que ficou FORA é a parte que importa: contrato (🔴 OTP, vira MRR), envio ao cliente
(sai da empresa e não volta) e mudança de funil (mexe nas métricas). Decisão de mesa, não
de corredor de condomínio.
"""
import asyncio
import sys
import uuid

sys.path.insert(0, "/app")

FALHAS: list[str] = []


def checar(cond: bool, titulo: str, detalhe: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FALHA'} · {titulo}{(' — ' + detalhe) if detalhe else ''}")
    if not cond:
        FALHAS.append(titulo)


async def main() -> int:
    import main_production  # noqa: F401,PLC0415

    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.ai.conversation.services.orquestrador import agir_dispatcher as AD
    from modules.integrations.connectors.whatsapp import agent_service as A

    def nomes(sch):
        return {(x.get("function") or {}).get("name") for x in sch}

    checar("agir_comercial" in nomes(A._tools_ativas(owner=True)),
           "o SERVIDOR entrega agir_comercial ao DONO")
    checar("agir_comercial" not in nomes(A._tools_ativas(owner=False)),
           "o CLIENTE não enxerga agir_comercial",
           "vazou para o canal público!" if "agir_comercial" in
           nomes(A._tools_ativas(owner=False)) else "")

    acoes = next((d for d in (getattr(AD, a, None) for a in dir(AD))
                  if isinstance(d, dict) and d.get("crm")), {}).get("crm") or {}
    fantasma = sorted(set(A._ACOES_CAMPO) - set(acoes))
    checar(not fantasma, "toda ação liberada existe no Bartolo",
           f"inexistentes: {fantasma}" if fantasma else f"{len(A._ACOES_CAMPO)} ações")

    # ⭐ O QUE FICOU DE FORA — a parte cara. Se qualquer uma destas entrar na allow-list,
    # o Jordan pode ativar contrato ou mandar proposta ao cliente de dentro de um corredor.
    PROIBIDAS = ("ativar_contrato", "criar_contrato", "atualizar_contrato",
                 "enviar_proposta", "enviar_proposta_whatsapp", "marcar_deal_perdido",
                 "mover_estagio_deal", "followup_em_lote", "resolver_propostas")
    vazou = sorted(set(A._ACOES_CAMPO) & set(PROIBIDAS))
    checar(not vazou, "nenhuma ação de CONTRATO, ENVIO ou FUNIL na allow-list",
           f"vazaram: {vazou}" if vazou else "")

    for proibida in ("ativar_contrato", "enviar_proposta_whatsapp"):
        r = await A._exec_manager_tool("agir_comercial", {"acao": proibida, "dados": {}}, 76)
        checar(r.get("status") == "recusado",
               f"executor RECUSA {proibida}", str(r)[:70])

    # caminho feliz: nasce RASCUNHO, e o funil NÃO muda
    async with async_session_factory() as db:
        antes = (await db.execute(text("SELECT count(*) FROM proposals"))).scalar()
    r = await A._exec_manager_tool("agir_comercial", {"acao": "criar_orcamento", "dados": {
        # ⚠️ TÍTULO ÚNICO POR RODADA: `criar_rascunho` tem `idempotency_key`, e com
        # título fixo a 2ª execução devolve o rascunho ANTERIOR — sem `gate` na
        # resposta — e o oráculo falha por culpa da própria fixture. Mesmo erro do
        # CNPJ que inventei hoje e que já existia no banco.
        "cliente": "Condomínio Residencial The Sun",
        "titulo": f"__ORACULO_ETAPA2__ {uuid.uuid4().hex[:8]}",
        "empresa": "eletronica",
        "itens": [{"descricao": "Câmera IP PoE", "qtd": 2, "valor_unit": 1.0}]}}, 76)
    checar(bool(r.get("draft_id")), "ação liberada cria RASCUNHO", str(r)[:80])
    checar(r.get("gate") == "🟡", "o rascunho carrega o grau", f"gate={r.get('gate')}")
    async with async_session_factory() as db:
        depois = (await db.execute(text("SELECT count(*) FROM proposals"))).scalar()
        if r.get("draft_id"):
            await db.execute(text("DELETE FROM agent_drafts "
                                  "WHERE id::text = :i"), {"i": r["draft_id"]})
            await db.commit()
    checar(antes == depois, "NADA entrou no funil sem aprovação",
           f"proposals {antes} → {depois}")

    print()
    if FALHAS:
        print(f"  ❌ {len(FALHAS)} FALHA(S): {', '.join(FALHAS)}")
        return 1
    print("  ✅ ele monta em campo, e nada vale sem o clique dele.")
    return 0


sys.exit(asyncio.run(main()))
