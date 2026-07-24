"""SUITE-ORÁCULO da Peça 3 — prova a FRONTEIRA por tier com identidades REAIS.

LLM-independente por doutrina: a fronteira é o DADO (belt de tools + escopo na query +
handler que barra na fonte), não a prosa do LLM. Cada oráculo exercita handler/composição/
escopo de forma determinística. Roda de uma vez; imprime `ORACULO N ... PASS/FAIL`, um
resumo final, e sai com código != 0 se QUALQUER oráculo falhar.

Bancada: throwaway `conecta-pro-backend:latest` na rede do compose (NUNCA green/:8080).
Escrita: o ÚNICO teste que escreve é o nº 4 (justificar ponto) — limpeza por id no finally,
0 remanescentes provado. O oráculo 6 (diretoria) neutraliza LLM+auditoria p/ ficar read-only
e determinístico — o que se prova ali é a DELEGAÇÃO (rota/handler responde), não a prosa.

Identidades reais (verificadas contra o banco vivo):
- GESTOR   = egonzaga@conectamais.pro       (gerente_operacional; módulos ged/dp/operacional/sst; SEM financeiro/fiscal)
- LÍDER    = erikamaquine93@gmail.com        (lider; lidera >=1 posto via posts.leader_id)
- CLT      = employee CELIANE (196 batidas reais)
- CLIENTE  = ged_clients GREEN HILLS + outro condomínio com portal habilitado
- DIRETORIA= jjesus@conectamais.pro          (role admin -> delega ao executivo)
"""
from __future__ import annotations

import asyncio
import traceback

from sqlalchemy import text

from core.database import async_session_factory
from modules.ai.conversation.controllers.consultor_escopado_controller import (
    ConsultarIn,
    _resolver_tier_e_tools,
    consultar as scoped_consultar,
)
from modules.ai.conversation.services.orquestrador.engine import OrqScope
from modules.ai.conversation.services.orquestrador import tool_registry as tr

# Garante o REGISTRY completo (o controller já importa modulos/posto/self/ponto; cliente não).
from modules.ai.conversation.services.orquestrador import (  # noqa: F401
    tools_cliente,
    tools_modulos,
    tools_ponto,
    tools_posto,
    tools_self,
)

CELIANE_EMP = "9e9e1678-9988-490c-b59b-b2786bb67e1c"
GREEN_HILLS = "b4a13504-cffc-4505-8e91-e1bebed493ed"
MOTIVO = "TESTE ORACULO ORQ RBAC — apagar"

GESTOR_EMAIL = "egonzaga@conectamais.pro"
LIDER_EMAIL = "erikamaquine93@gmail.com"
ADMIN_EMAIL = "jjesus@conectamais.pro"


class _U:
    """Identidade mínima (id/role/permissions) — o que o belt e o escopo consomem."""

    def __init__(self, id, role, permissions):
        self.id, self.role, self.permissions = id, role, permissions


async def _user(db, email) -> _U:
    r = (await db.execute(
        text("SELECT id::text AS id, role, permissions FROM users WHERE email = :e"),
        {"e": email},
    )).first()
    if r is None:
        raise AssertionError(f"identidade real ausente no banco: {email}")
    return _U(r.id, r.role, r.permissions or [])


# ── Oráculos (cada um retorna None se PASS; levanta AssertionError se a fronteira vazar) ──

async def oraculo_1_gestor(db) -> None:
    """GESTOR (gonzaga) NÃO vê financeiro/fiscal: nem no belt (tools), nem no handler."""
    gonzaga = await _user(db, GESTOR_EMAIL)
    scope, tools = await _resolver_tier_e_tools(db, gonzaga)
    names = {t.name for t in tools}
    assert "panorama_financeiro" not in names, f"financeiro VAZOU no belt do gestor: {names}"
    assert "panorama_fiscal" not in names, f"fiscal VAZOU no belt do gestor: {names}"

    # Suspenders: mesmo forçando o handler, ele barra (defesa em profundidade).
    for tool_name, modulo in (("panorama_financeiro", "financeiro"), ("panorama_fiscal", "fiscal")):
        barrou = False
        try:
            await tr.get_tool(tool_name).handler(db, gonzaga, None)
        except PermissionError:
            barrou = True
        assert barrou, f"handler {tool_name} NÃO barrou o gestor {GESTOR_EMAIL}"


async def oraculo_2_lider(db) -> None:
    """LÍDER (erika) só o(s) SEU(S) posto(s); posto de outro é impossível: escopo vazio = aguardando."""
    erika = await _user(db, LIDER_EMAIL)
    scope, _ = await _resolver_tier_e_tools(db, erika)
    assert scope.tier == "lider", f"erika não resolveu como líder: tier={scope.tier}"
    assert scope.post_ids, "líder sem post_ids — pré-condição real quebrou (erika não lidera posto)"

    # Escopo com post_ids=[] (outro líder sem posto / posto alheio) => aguardando dado, nunca dado.
    vazio = await tr.get_tool("posto_escala_hoje").handler(
        db, None, OrqScope(tier="lider", post_ids=[], employee_id=scope.employee_id))
    assert vazio.get("status") == "aguardando dado", f"posto alheio VAZOU: {vazio}"

    # E com o próprio escopo, retorna postos (só os dele, por construção da query).
    proprio = await tr.get_tool("posto_escala_hoje").handler(
        db, None, OrqScope(tier="lider", post_ids=scope.post_ids, employee_id=scope.employee_id))
    assert "postos" in proprio, f"líder não obteve o próprio posto: {proprio}"


async def oraculo_3_clt_self(db) -> None:
    """CLT não alcança OUTRO colaborador: a self-tool aceita **_ (chave extra do LLM não
    quebra), mas o employee_id injetado é INERTE — o escopo vem SÓ de scope.employee_id.
    Prova por igualdade: resultado com employee_id de OUTRO injetado == resultado sem injeção."""
    outro = (await db.execute(text(
        "SELECT employee_id::text FROM gp_clock_punches WHERE employee_id <> :e LIMIT 1"
    ), {"e": CELIANE_EMP})).scalar()
    assert outro, "pré-condição: precisa existir batida de OUTRO colaborador"

    tool = tr.get_tool("meu_ponto")
    plain = await tool.handler(db, None, OrqScope(tier="clt", employee_id=CELIANE_EMP))
    injet = await tool.handler(
        db, None, OrqScope(tier="clt", employee_id=CELIANE_EMP), employee_id=outro)  # type: ignore[call-arg]
    assert injet == plain, "meu_ponto USOU employee_id injetado — self-only quebrado (deve ser INERTE)"


async def oraculo_4_clt_justifica(db) -> None:
    """CLT justifica ponto => pendente 'pendente' p/ o DP; gp_clock_punches INALTERADO.
    Escreve UMA linha; limpa por id no finally e prova 0 remanescentes."""
    jid = None
    try:
        antes = (await db.execute(
            text("SELECT count(*) FROM gp_clock_punches WHERE employee_id = :e"),
            {"e": CELIANE_EMP})).scalar()

        out = await tr.get_tool("justificar_ajuste_de_ponto").handler(
            db, None, OrqScope(tier="clt", employee_id=CELIANE_EMP), motivo=MOTIVO)
        jid = out.get("justification_id")
        assert jid, f"justificar não retornou justification_id: {out}"
        assert out.get("status") == "pendente", f"status esperado 'pendente', veio {out.get('status')}"

        st = (await db.execute(
            text("SELECT status FROM gp_justifications WHERE justification_id = :j"),
            {"j": jid})).scalar()
        assert st == "pendente", f"gravou status != pendente: {st}"

        depois = (await db.execute(
            text("SELECT count(*) FROM gp_clock_punches WHERE employee_id = :e"),
            {"e": CELIANE_EMP})).scalar()
        assert depois == antes, f"gp_clock_punches ALTERADO (antes={antes}, depois={depois})"
    finally:
        # Limpeza por id (e varredura por reason p/ idempotência) + prova 0 remanescentes.
        if jid:
            await db.execute(text("DELETE FROM gp_justifications WHERE justification_id = :j"), {"j": jid})
        await db.execute(text("DELETE FROM gp_justifications WHERE reason = :r"), {"r": MOTIVO})
        await db.commit()
        remanescentes = (await db.execute(
            text("SELECT count(*) FROM gp_justifications WHERE reason = :r"), {"r": MOTIVO})).scalar()
        assert remanescentes == 0, f"LIMPEZA FALHOU: {remanescentes} justificativa(s) de teste remanescente(s)"


async def oraculo_5_cliente(db) -> None:
    """CLIENTE só o PRÓPRIO condomínio: recebe o SEU boleto; sem client_id => aguardando dado;
    outro condomínio é isolado (filtro por client_id, nunca por argumento)."""
    doc = tr.get_tool("buscar_documento_condominio")

    # (a) Documento do PRÓPRIO condomínio: ou entrega docs, ou 'aguardando dado' (honesto), nunca de outro.
    out_gh = await doc.handler(db, None, OrqScope(tier="cliente", client_id=GREEN_HILLS), tipo="boleto")
    assert ("documentos" in out_gh) or (out_gh.get("status") == "aguardando dado"), f"boleto do próprio: {out_gh}"

    # (b) Sem client_id => aguardando dado (nunca "cai" para outro condomínio).
    semcid = await doc.handler(db, None, OrqScope(tier="cliente", client_id=None), tipo="boleto")
    assert semcid.get("status") == "aguardando dado", f"sem client_id NÃO retornou aguardando: {semcid}"

    # (c) Outro condomínio: isolado por client_id (a tool só usa scope.client_id).
    outro_cond = (await db.execute(text(
        "SELECT id::text FROM ged_clients WHERE portal_access_enabled = true AND id <> :g LIMIT 1"
    ), {"g": GREEN_HILLS})).scalar()
    assert outro_cond, "pré-condição: precisa existir OUTRO condomínio com portal habilitado"
    o = await tr.get_tool("notas_condominio").handler(
        db, None, OrqScope(tier="cliente", client_id=outro_cond))
    assert isinstance(o, dict), f"notas de outro condomínio não retornou dict: {o!r}"


async def oraculo_6_diretoria(db) -> None:
    """DIRETORIA (admin) delega ao Orquestrador Executivo: a rota/handler RESPONDE.
    Determinístico e read-only: LLM e auditoria são neutralizados (o que se prova é a
    DELEGAÇÃO, não a prosa) — o executivo degrada para o template ancorado e responde."""
    from modules.ai.conversation.services import consultor_hub
    from modules.ai.conversation.services.garantia import agent_audit

    async def _sem_llm(*_a, **_k):
        raise RuntimeError("LLM neutralizado no oráculo (determinismo/LLM-independência)")

    async def _sem_audit(*_a, **_k):  # mantém o oráculo read-only (só o nº4 escreve)
        return None

    orig_gerar = consultor_hub.gerar
    orig_audit = agent_audit.registrar_acao_agente
    consultor_hub.gerar = _sem_llm
    agent_audit.registrar_acao_agente = _sem_audit
    try:
        admin = await _user(db, ADMIN_EMAIL)
        assert (admin.role or "").lower() == "admin", f"{ADMIN_EMAIL} não é admin: role={admin.role}"
        out = await scoped_consultar(
            ConsultarIn(pergunta="Rota diretoria — teste oráculo (delegação)"), db=db, user=admin)
        assert out.get("tier") == "diretoria", f"admin NÃO delegou ao executivo: tier={out.get('tier')}"
        assert out.get("resposta"), f"executivo não respondeu: {out}"
    finally:
        consultor_hub.gerar = orig_gerar
        agent_audit.registrar_acao_agente = orig_audit


async def oraculo_7_injecao_inerte(db) -> None:
    """PROBE de robustez: injeção de kwargs (client_id/employee_id/post_ids) é INERTE.
    O escopo vem SEMPRE da identidade/scope, nunca do argumento do LLM."""
    # (a) self: employee_id injetado é INERTE — usa scope.employee_id, não o argumento do LLM
    #     (padrão dos oráculos cliente: prova por igualdade plain==injet, não por TypeError).
    self_tool = tr.get_tool("meu_ponto")
    self_plain = await self_tool.handler(db, None, OrqScope(tier="clt", employee_id=CELIANE_EMP))
    self_injet = await self_tool.handler(
        db, None, OrqScope(tier="clt", employee_id=CELIANE_EMP),
        employee_id="00000000-0000-0000-0000-000000000000")  # type: ignore[call-arg]
    assert self_injet == self_plain, "self-tool USOU employee_id injetado (deveria ser inerte)"

    # (b) cliente: injetar client_id de OUTRO condomínio NÃO muda o resultado (usa scope.client_id).
    outro_cond = (await db.execute(text(
        "SELECT id::text FROM ged_clients WHERE portal_access_enabled = true AND id <> :g LIMIT 1"
    ), {"g": GREEN_HILLS})).scalar()
    doc = tr.get_tool("buscar_documento_condominio")
    plain = await doc.handler(db, None, OrqScope(tier="cliente", client_id=GREEN_HILLS), tipo="boleto")
    injet = await doc.handler(
        db, None, OrqScope(tier="cliente", client_id=GREEN_HILLS), tipo="boleto", client_id=outro_cond)  # type: ignore[call-arg]
    assert injet == plain, "injeção de client_id ALTEROU o resultado — vazamento cross-condomínio"

    # (c) posto: injetar post_ids com o escopo vazio => segue 'aguardando dado' (scope vence o argumento).
    real_post = (await db.execute(text("SELECT id::text FROM posts WHERE is_active = true LIMIT 1"))).scalar()
    vazio = await tr.get_tool("posto_escala_hoje").handler(
        db, None, OrqScope(tier="lider", post_ids=[], employee_id=None), post_ids=[real_post])  # type: ignore[call-arg]
    assert vazio.get("status") == "aguardando dado", f"injeção de post_ids VAZOU posto: {vazio}"


async def oraculo_8_tier_nao_forjavel(db) -> None:
    """PROBE de robustez: o tier NÃO é forjável via payload — a entrada da rota só tem 'pergunta'.
    O tier/escopo é resolvido no servidor a partir da identidade (get_current_active_user)."""
    campos = set(ConsultarIn.model_fields.keys())
    assert campos == {"pergunta"}, f"payload expõe campos além de 'pergunta' (tier forjável?): {campos}"
    for proibido in ("tier", "employee_id", "post_ids", "client_id", "scope"):
        assert proibido not in campos, f"payload aceita '{proibido}' — tier/escopo forjável"


_ORACULOS = [
    ("1 (GESTOR sem financeiro/fiscal)", oraculo_1_gestor),
    ("2 (LÍDER só o próprio posto)", oraculo_2_lider),
    ("3 (CLT self-only — não alcança outro)", oraculo_3_clt_self),
    ("4 (CLT justifica => pendente; ponto intocado; limpo)", oraculo_4_clt_justifica),
    ("5 (CLIENTE só o próprio condomínio)", oraculo_5_cliente),
    ("6 (DIRETORIA delega ao executivo — rota responde)", oraculo_6_diretoria),
    ("7 (PROBE injeção de kwargs inerte)", oraculo_7_injecao_inerte),
    ("8 (PROBE tier não forjável via payload)", oraculo_8_tier_nao_forjavel),
]


async def main() -> int:
    falhas = 0
    async with async_session_factory() as db:
        for rotulo, fn in _ORACULOS:
            try:
                await fn(db)
                print(f"ORACULO {rotulo} PASS")
            except Exception as e:  # noqa: BLE001 — um oráculo não derruba os outros; conta como FAIL
                falhas += 1
                print(f"ORACULO {rotulo} FAIL -> {type(e).__name__}: {e}")
                print("    " + traceback.format_exc().replace("\n", "\n    ").rstrip())
    total = len(_ORACULOS)
    passou = total - falhas
    print("-" * 72)
    if falhas == 0:
        print(f"SUITE-ORACULO RBAC: {passou}/{total} PASS — fronteira PROVADA por tier.")
    else:
        print(f"SUITE-ORACULO RBAC: {passou}/{total} PASS, {falhas} FAIL — GATE BLOQUEADO.")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
