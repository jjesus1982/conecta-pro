"""Fase 5.4 — Onda A: cobrança (🟡), proposta comercial (🟡), kit (🔵).

Cada ação grava um PENDENTE na tabela nativa via base.propor. NENHUMA executa:
- cobrança: inter_cobrancas status 'PENDENTE' (a emissão real fica no CobrancaService.emitir humano)
- proposta: proposals status 'draft' (envio/assinatura ficam no proposal_controller humano)
- kit: ged_document_kits status 'proposto' (a montagem/envio ficam no kit_orchestrator humano)
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from ..tool_registry import ToolDef, register
from .base import GATES, ROLES_COMERCIAL, ROLES_KIT_OP, propor  # noqa: F401

# ───────────────────────── cobrança (🟡, dinheiro que ENTRA) ─────────────────

_ARGS_COBRANCA = {
    "type": "object",
    "properties": {
        "cliente_crm_id": {"type": "string", "description": "ID do cliente no CRM (obrigatório)."},
        "valor": {"type": "number", "minimum": 0.01, "description": "Valor da cobrança (R$)."},
        "vencimento": {"type": "string", "description": "Data de vencimento AAAA-MM-DD."},
        "descricao": {"type": "string", "maxLength": 500},
    },
    "required": ["cliente_crm_id", "valor", "vencimento"],
}


async def _propor_cobranca(
    db, user, scope, *, cliente_crm_id: str, valor: float,
    vencimento: str, descricao: str = "", **_
) -> dict[str, Any]:
    if not cliente_crm_id or float(valor) <= 0:
        return {"erro": "cliente e valor (>0) são obrigatórios"}
    try:
        venc_date = date.fromisoformat(vencimento)
    except (TypeError, ValueError):
        return {"erro": "vencimento inválido (esperado AAAA-MM-DD)"}
    idem = f"cobranca:{cliente_crm_id}:{float(valor):.2f}:{vencimento}"

    # valor é coluna numeric(15,2); asyncpg tipa um Python float como float8, e
    # numeric=float8 compara após CAST numeric->double (epsilon de ponto flutuante
    # — 12.34 nunca bate exato). Bind como Decimal (idioma exato p/ numeric).
    valor_decimal = Decimal(f"{float(valor):.2f}")

    async def _inserir(db) -> str:
        # Idempotência NATIVA (defesa em profundidade, achado da review T2): mesmo
        # que a checagem do sino em base.propor não pegue (ex.: notificação antiga
        # desativada, ou outra origem chamando este callback com key distinta),
        # NUNCA duplicamos o PENDENTE na tabela nativa — molde tools_ponto
        # (SELECT-existing antes do INSERT).
        # vencimento é coluna `date`; asyncpg exige o TIPO NATIVO no bind (mesmo com
        # CAST no SQL o driver já prepara o parâmetro como date client-side) — texto
        # cru quebra ("'str' object has no attribute 'toordinal'"). Por isso usamos
        # venc_date (datetime.date parseado acima), não a string recebida do LLM.
        existente = (await db.execute(text(
            "SELECT id::text FROM inter_cobrancas "
            "WHERE status = 'PENDENTE' "
            "  AND pagador->>'cliente_crm_id' = :cli "
            "  AND valor = :valor AND vencimento = :venc LIMIT 1"),
            {"cli": cliente_crm_id, "valor": valor_decimal, "venc": venc_date})).scalar()
        if existente:
            return existente

        local_id = str(uuid.uuid4())
        seu_numero = f"CPRO-{local_id[:8].upper()}"
        await db.execute(text("""
            INSERT INTO inter_cobrancas
                (id, seu_numero, valor, vencimento, status, descricao, pagador, created_at, updated_at)
            VALUES
                (:id, :sn, :valor, :venc, 'PENDENTE', :desc, CAST(:pag AS jsonb), NOW(), NOW())
        """), {"id": local_id, "sn": seu_numero, "valor": valor_decimal,
               "venc": venc_date, "desc": descricao or "",
               "pag": json.dumps({"cliente_crm_id": cliente_crm_id,
                                  "origem": "agente_proposta"})})
        return local_id

    return await propor(
        db, user=user, scope=scope, dominio="cobranca", gate="🟡",
        roles_aprovador=ROLES_COMERCIAL, idempotency_key=idem,
        titulo="[Proposta] Emitir cobrança",
        corpo=f"Cobrança de R$ {float(valor):.2f} (venc. {vencimento}) — {descricao or 'sem descrição'}. Aguarda sua aprovação.",
        action_url="/financeiro/cobrancas",
        tool="propor_cobranca",
        args={"cliente_crm_id": cliente_crm_id, "valor": float(valor), "vencimento": vencimento},
        entity_type="inter_cobranca", inserir=_inserir,
    )


COBRANCA_TOOL: ToolDef = register(ToolDef(
    "propor_cobranca", "crm",
    "Propor a emissão de uma cobrança a um cliente (fica PENDENTE de aprovação; não emite nada).",
    _ARGS_COBRANCA, _propor_cobranca, scope_kind="org",
))


# ───────────────────────── proposta comercial (🟡, draft) ───────────────────

_ARGS_PROPOSTA = {
    "type": "object",
    "properties": {
        "client_name": {"type": "string", "minLength": 2, "description": "Nome do cliente (obrigatório)."},
        "title": {"type": "string", "minLength": 2, "description": "Título da proposta."},
        "valor_total": {"type": "number", "minimum": 0, "description": "Valor total (R$)."},
        "descricao": {"type": "string", "maxLength": 2000},
    },
    "required": ["client_name", "title", "valor_total"],
}


async def _propor_proposta(
    db, user, scope, *, client_name: str, title: str,
    valor_total: float, descricao: str = "", **_
) -> dict[str, Any]:
    client_name = (client_name or "").strip()
    title = (title or "").strip()
    if len(client_name) < 2 or len(title) < 2:
        return {"erro": "client_name e title são obrigatórios"}
    idem = f"proposta:{client_name}:{title}:{float(valor_total):.2f}"

    # NOTA schema×brief: proposals.subtotal/discount_value/taxes/total são
    # `double precision` (float8) na tabela real — NÃO numeric(15,2) como
    # inter_cobrancas.valor (onde Decimal era o idioma exato). Aqui o idioma
    # exato do driver p/ float8 é float nativo; Decimal quebraria o bind
    # asyncpg (float8 espera float, não Decimal). status/proposal_type
    # confirmados em modules/crm/models/proposal.py: ProposalStatus.DRAFT
    # ("draft") e ProposalType.SERVICE ("service").
    valor_total = float(valor_total)

    async def _inserir(db) -> str:
        # Idempotência NATIVA (defesa em profundidade, molde cobrança/tools_ponto):
        # mesmo que a checagem do sino em base.propor não pegue, NUNCA duplicamos
        # o DRAFT na tabela nativa — SELECT-existing antes do INSERT.
        existente = (await db.execute(text(
            "SELECT id::text FROM proposals "
            "WHERE status = 'draft' AND client_name = :cli AND title = :ttl "
            "  AND total = :val LIMIT 1"),
            {"cli": client_name, "ttl": title, "val": valor_total})).scalar()
        if existente:
            return existente

        pid = str(uuid.uuid4())
        number = f"PROP-{pid[:8].upper()}"
        # NOTA schema×brief: proposals.created_by_id tem FK NOT NULL-less mas
        # ENFORCED p/ users(id) (proposals_created_by_id_fkey, ON DELETE SET
        # NULL) — diferente de inter_cobrancas.pagador (jsonb solto, sem FK).
        # Um :uid bindado direto quebraria (FK violation) se o propositor não
        # existir em `users` (não deveria acontecer em produção — usuário
        # autenticado sempre existe — mas é a defesa correta e barata: mesmo
        # padrão do resto do arquivo, "nunca confiar cegamente no dado de
        # entrada"). Subquery valida a existência em 1 round-trip: usuário
        # real → grava o id; id inexistente → grava NULL (nunca falha o
        # INSERT do draft por causa disso).
        await db.execute(text("""
            INSERT INTO proposals
                (id, number, version, client_name, title, description, proposal_type,
                 subtotal, discount_value, taxes, total, installments, issue_date,
                 status, created_by_id, is_active, created_at, updated_at)
            VALUES
                (:id, :num, 1, :cli, :ttl, :desc, 'service',
                 :val, 0, 0, :val, 1, :hoje,
                 'draft', (SELECT id FROM users WHERE id = :uid), true, now(), now())
        """), {"id": pid, "num": number, "cli": client_name, "ttl": title,
               "desc": descricao or None, "val": valor_total,
               "hoje": date.today(), "uid": str(getattr(user, "id", None))})
        return pid

    return await propor(
        db, user=user, scope=scope, dominio="proposta", gate="🟡",
        roles_aprovador=ROLES_COMERCIAL, idempotency_key=idem,
        titulo="[Proposta] Enviar proposta comercial",
        corpo=f"Proposta '{title}' para {client_name} (R$ {valor_total:.2f}) em rascunho. Aguarda sua revisão/envio.",
        action_url="/crm/propostas",
        tool="propor_proposta_comercial",
        args={"client_name": client_name, "title": title, "valor_total": valor_total},
        entity_type="proposal", inserir=_inserir,
    )


PROPOSTA_TOOL: ToolDef = register(ToolDef(
    "propor_proposta_comercial", "crm",
    "Criar um RASCUNHO de proposta comercial (fica draft; o envio/assinatura ao cliente é aprovado por humano).",
    _ARGS_PROPOSTA, _propor_proposta, scope_kind="org",
))


# ───────────────────────── kit documental (🔵, reversível interno) ───────────

_ARGS_KIT = {
    "type": "object",
    "properties": {
        "client_id": {"type": "string", "description": "ID do cliente/condomínio do kit."},
        "tipo_kit": {"type": "string", "minLength": 2, "description": "Tipo/modelo do kit documental."},
        "descricao": {"type": "string", "maxLength": 500},
    },
    "required": ["client_id", "tipo_kit"],
}


async def _propor_kit(
    db, user, scope, *, client_id: str, tipo_kit: str, descricao: str = "", **_
) -> dict[str, Any]:
    if not client_id or len((tipo_kit or "").strip()) < 2:
        return {"erro": "client_id e tipo_kit são obrigatórios"}

    # NOTA DIVERGÊNCIA schema×brief (Step 1 do brief, \d ged_document_kits real):
    # a tabela NÃO tem coluna `tipo` (o esqueleto do brief assumia); o grão real é
    # 1 kit por (client_id, reference_month) — UNIQUE constraint
    # ged_document_kits_client_id_reference_month_key, sem discriminador de tipo.
    # client_id é uuid com FK ENFORCED p/ ged_clients(id) (diferente de
    # inter_cobrancas.pagador, jsonb solto sem FK) — validamos aqui p/ falhar com
    # {"erro":...} em vez de estourar IntegrityError dentro de propor(). tipo_kit/
    # descricao (texto livre vindo do LLM) vão para `notes` (única coluna de texto
    # livre da tabela). reference_month (NOT NULL, sem default) não é arg exposto
    # ao LLM — é derivado como 1º dia do mês corrente (mesmo idioma de
    # `date.today()` usado em proposals.issue_date acima: mês implícito = "agora").
    try:
        client_uuid = uuid.UUID(str(client_id))
    except (ValueError, AttributeError, TypeError):
        return {"erro": "client_id inválido (esperado UUID de ged_clients)"}

    existe_cliente = (await db.execute(text(
        "SELECT 1 FROM ged_clients WHERE id = :cid"), {"cid": str(client_uuid)})).scalar()
    if not existe_cliente:
        return {"erro": f"cliente {client_id} não encontrado em ged_clients"}

    ref_month = date.today().replace(day=1)
    idem = f"kit:{client_id}:{tipo_kit}"

    async def _inserir(db) -> str:
        # Idempotência NATIVA sobre o grão REAL da tabela: (client_id,
        # reference_month) — ver NOTA acima (não (client_id, tipo_kit), que não
        # existe como chave). Um cliente só tem 1 kit por mês (qualquer status).
        # client_id aqui é ged_clients.id — o ESPAÇO da FK real
        # (ged_document_kits.client_id -> ged_clients.id), das 59 linhas reais e da
        # UI (GET /ged/kits). O loop fecha pelo fluxo humano real: auto_assemble
        # (get-or-create por (client_id, reference_month) em ged_clients.id) ACHA e
        # complementa este 'proposto', e a UI (KitDetalheModal) o exibe.
        # (NÃO por kit_real_controller.montar_kit_guiado: é rota órfã sem chamador
        # e resolve via clients.id — espaço que descasa; não é a ponte humana.)
        existente = (await db.execute(text(
            "SELECT id::text FROM ged_document_kits "
            "WHERE client_id = :cid AND reference_month = :rm LIMIT 1"),
            {"cid": str(client_uuid), "rm": ref_month})).scalar()
        if existente:
            return existente

        kid = str(uuid.uuid4())
        notas = f"[proposto via IA] tipo={tipo_kit}" + (f" — {descricao}" if descricao else "")
        await db.execute(text("""
            INSERT INTO ged_document_kits
                (id, client_id, reference_month, status, notes, created_at, updated_at)
            VALUES
                (:id, :cid, :rm, 'proposto', :notes, now(), now())
        """), {"id": kid, "cid": str(client_uuid), "rm": ref_month, "notes": notas})
        return kid

    return await propor(
        db, user=user, scope=scope, dominio="kit", gate="🔵",
        roles_aprovador=ROLES_KIT_OP, idempotency_key=idem,
        titulo="[Proposta] Montar kit documental",
        corpo=f"Kit '{tipo_kit}' para cliente {client_id} (mês {ref_month.strftime('%m/%Y')}). "
              f"Aguarda aprovação p/ montar/enviar.",
        action_url="/documentos/kits",
        tool="propor_kit",
        args={"client_id": client_id, "tipo_kit": tipo_kit},
        entity_type="ged_document_kit", inserir=_inserir,
    )


KIT_TOOL: ToolDef = register(ToolDef(
    "propor_kit", "ged",
    "Propor a montagem de um kit documental (fica 'proposto'; a montagem/envio é aprovada por humano).",
    _ARGS_KIT, _propor_kit, scope_kind="org",
))

ONDA_A_TOOLS = [COBRANCA_TOOL, PROPOSTA_TOOL, KIT_TOOL]


if __name__ == "__main__":
    import asyncio
    import os

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    class _U:
        id = "00000000-0000-0000-0000-0000000000ff"
        role = "comercial"

    class _S:
        tier = "gestor"

    async def _limpar(db, idem_like: str) -> None:
        ids = [x for x in (await db.execute(text(
            "SELECT id::text FROM communication_notifications "
            "WHERE extra_data->>'idempotency_key' LIKE :k"), {"k": idem_like})).scalars().all()]
        if ids:
            await db.execute(text("DELETE FROM communication_notifications WHERE id = ANY(:i)"), {"i": ids})
        await db.commit()

    async def main() -> None:
        eng = create_async_engine(os.environ["DATABASE_URL"])
        Session = async_sessionmaker(eng, expire_on_commit=False)
        async with Session() as db:
            cob_ids: list[str] = []
            aud_ids: list[str] = []
            prop_ids: list[str] = []
            kit_ids: list[str] = []
            ged_kit_client_ids: list[str] = []
            try:
                # baseline: nenhuma cobrança RECEBIDA/executada deve mudar
                recebidas_antes = (await db.execute(text(
                    "SELECT count(*) FROM inter_cobrancas WHERE status <> 'PENDENTE'"))).scalar()

                venc = "2099-12-31"  # data marcada de teste (nunca real)
                r = await _propor_cobranca(db, _U(), _S(),
                    cliente_crm_id="TESTE-5.4-CLI", valor=12.34, vencimento=venc,
                    descricao="__TESTE_5.4__ cobranca")
                assert r["status"] == "pendente", r
                eid = r["entity_id"]
                cob_ids.append(eid)

                # a linha nasceu PENDENTE (nunca emitida)
                st = (await db.execute(text(
                    "SELECT status FROM inter_cobrancas WHERE id = :i"), {"i": eid})).scalar()
                assert st == "PENDENTE", f"status inesperado: {st}"

                # estado de execução INTOCADO
                recebidas_depois = (await db.execute(text(
                    "SELECT count(*) FROM inter_cobrancas WHERE status <> 'PENDENTE'"))).scalar()
                assert recebidas_depois == recebidas_antes, "cobrança executada mudou (não deveria)"

                # idempotência (sino: mesma idempotency_key → duplicado, inserir não roda de novo)
                r2 = await _propor_cobranca(db, _U(), _S(),
                    cliente_crm_id="TESTE-5.4-CLI", valor=12.34, vencimento=venc,
                    descricao="__TESTE_5.4__ cobranca")
                assert r2.get("duplicado") is True, r2

                # idempotência NATIVA (defesa em profundidade, "não confie só no sino"):
                # desativa a notificação do sino (simula um pendente cujo alerta já foi
                # arquivado) e propõe de novo com os MESMOS cliente/valor/vencimento — o
                # precheck do sino em base.propor filtra is_active=true, então NÃO acha
                # duplicado ali; quem tem que barrar a 2ª linha é o SELECT-existing dentro
                # do próprio _inserir, sobre a tabela nativa.
                idem_key = f"cobranca:TESTE-5.4-CLI:{12.34:.2f}:{venc}"
                await db.execute(text(
                    "UPDATE communication_notifications SET is_active = false "
                    "WHERE extra_data->>'idempotency_key' = :k"), {"k": idem_key})
                await db.commit()

                r3 = await _propor_cobranca(db, _U(), _S(),
                    cliente_crm_id="TESTE-5.4-CLI", valor=12.34, vencimento=venc,
                    descricao="__TESTE_5.4__ cobranca (sino desativado)")
                if r3.get("entity_id") and r3["entity_id"] not in cob_ids:
                    cob_ids.append(r3["entity_id"])  # defesa: se a idempotência NATIVA falhar, limpa mesmo assim
                assert r3["status"] == "pendente", r3
                assert r3["entity_id"] == eid, \
                    f"idempotência NATIVA falhou: criou 2ª linha na tabela nativa ({r3['entity_id']} != {eid})"
                n_pendentes = (await db.execute(text(
                    "SELECT count(*) FROM inter_cobrancas WHERE status = 'PENDENTE' "
                    "AND pagador->>'cliente_crm_id' = 'TESTE-5.4-CLI'"))).scalar()
                assert n_pendentes == 1, \
                    f"idempotência NATIVA falhou: esperado 1 pendente na tabela nativa, veio {n_pendentes}"
                print("SUBTESTE cobrança: idempotência NATIVA (sino desativado, tabela nativa não duplica) PASS")

                # RBAC (d): a tool só aparece no belt de quem tem o módulo 'crm'.
                from ..tool_registry import tools_for_modules
                assert COBRANCA_TOOL.module == "crm", COBRANCA_TOOL.module
                nomes_crm = {t.name for t in tools_for_modules({"crm"})}
                nomes_financeiro = {t.name for t in tools_for_modules({"financeiro"})}
                assert "propor_cobranca" in nomes_crm, nomes_crm
                assert "propor_cobranca" not in nomes_financeiro, \
                    "propor_cobranca vazou p/ módulo 'financeiro' (RBAC de módulo quebrado)"
                print("SUBTESTE cobrança: RBAC de módulo (só 'crm' vê a tool) PASS")

                # aprovador correto (e): propositor REAL excluído do conjunto de aprovadores
                # (roles reais — ROLES_COMERCIAL=('admin',), não existe role 'comercial').
                from modules.notifications.proativo import entrega
                assert ROLES_COMERCIAL == ("admin",), ROLES_COMERCIAL
                admins = await entrega.resolver_usuarios_por_roles(db, ROLES_COMERCIAL)
                assert admins, "esperado >=1 admin ativo no banco p/ provar aprovador"

                class _UAdmin:
                    def __init__(self, uid: str) -> None:
                        self.id = uid
                    role = "admin"

                venc4 = "2099-12-30"  # 2ª data de teste p/ não colidir c/ idem_key acima
                r4 = await _propor_cobranca(db, _UAdmin(admins[0]), _S(),
                    cliente_crm_id="TESTE-5.4-CLI2", valor=99.90, vencimento=venc4,
                    descricao="__TESTE_5.4__ cobranca (propositor admin real)")
                if r4.get("entity_id"):
                    cob_ids.append(r4["entity_id"])
                if len(admins) >= 2:
                    assert r4["status"] == "pendente", r4
                    aps = r4.get("aprovadores") or []
                    assert admins[0] not in aps, \
                        f"propositor admin real não pode aprovar a própria cobrança: {aps}"
                    assert set(aps) == set(admins) - {admins[0]}, (aps, admins)
                    print(f"SUBTESTE cobrança: aprovador correto (propositor excluído; "
                          f"{len(admins)} admins → {len(aps)} aprovadores) PASS")
                else:
                    # tenant com 1 só admin: propositor==único aprovador possível → fail-closed
                    assert "erro" in r4, r4
                    print("SUBTESTE cobrança: aprovador correto (1 admin: propositor==único → fail-closed) PASS")

                print("SUBTESTE cobrança PASS (pendente criado, execução intocada, idempotente [sino+nativa], "
                      "RBAC módulo, aprovador correto)")

                # ── proposta comercial ──
                prop_sent_antes = (await db.execute(text(
                    "SELECT count(*) FROM proposals WHERE status = 'sent'"))).scalar()

                cli_p, ttl_p = "__TESTE_5.4__ Cliente", "__TESTE_5.4__ Título"
                rp = await _propor_proposta(db, _U(), _S(),
                    client_name=cli_p, title=ttl_p, valor_total=999.99, descricao="teste")
                assert rp["status"] == "pendente", rp
                pid = rp["entity_id"]
                prop_ids.append(pid)

                # (a) nasceu draft
                st_p = (await db.execute(text(
                    "SELECT status FROM proposals WHERE id = :i"), {"i": pid})).scalar()
                assert st_p == "draft", f"proposta nasceu {st_p}, esperado draft"

                # (b) ZERO envio/execução: nenhuma proposta 'sent' foi tocada
                prop_sent_depois = (await db.execute(text(
                    "SELECT count(*) FROM proposals WHERE status = 'sent'"))).scalar()
                assert prop_sent_depois == prop_sent_antes, "proposta enviada mudou (não deveria)"

                # idempotência (sino): mesma idempotency_key → duplicado, inserir não roda de novo
                rp2 = await _propor_proposta(db, _U(), _S(),
                    client_name=cli_p, title=ttl_p, valor_total=999.99)
                assert rp2.get("duplicado") is True, rp2
                # NOTA: o caminho `duplicado` de base.propor devolve entity_id cru
                # (tipo do driver, ex. UUID) sem str() — diferente do caminho normal
                # (que sempre faz str(entity_id)); normaliza os dois lados aqui
                # (comportamento de base.py é escopo de outra task, já testado à parte).
                assert str(rp2["entity_id"]) == str(pid), rp2

                # (c) idempotência NATIVA (defesa em profundidade, "não confie só no sino"):
                # desativa a notificação do sino e propõe de novo com os MESMOS
                # client_name/title/valor_total — o precheck do sino em base.propor
                # filtra is_active=true, então NÃO acha duplicado ali; quem tem que
                # barrar a 2ª linha é o SELECT-existing dentro do próprio _inserir,
                # sobre a tabela nativa proposals.
                idem_key_p = f"proposta:{cli_p}:{ttl_p}:{999.99:.2f}"
                await db.execute(text(
                    "UPDATE communication_notifications SET is_active = false "
                    "WHERE extra_data->>'idempotency_key' = :k"), {"k": idem_key_p})
                await db.commit()

                rp3 = await _propor_proposta(db, _U(), _S(),
                    client_name=cli_p, title=ttl_p, valor_total=999.99,
                    descricao="teste (sino desativado)")
                if rp3.get("entity_id") and rp3["entity_id"] not in prop_ids:
                    prop_ids.append(rp3["entity_id"])  # defesa: se a idempotência NATIVA falhar, limpa mesmo assim
                assert rp3["status"] == "pendente", rp3
                assert rp3["entity_id"] == pid, \
                    f"idempotência NATIVA falhou: criou 2ª linha em proposals ({rp3['entity_id']} != {pid})"
                n_drafts = (await db.execute(text(
                    "SELECT count(*) FROM proposals WHERE status = 'draft' "
                    "AND client_name = :cli AND title = :ttl"), {"cli": cli_p, "ttl": ttl_p})).scalar()
                assert n_drafts == 1, f"idempotência NATIVA falhou: esperado 1 draft, veio {n_drafts}"
                print("SUBTESTE proposta: idempotência NATIVA (sino desativado, tabela nativa não duplica) PASS")

                # (d) RBAC: a tool só aparece no belt de quem tem o módulo 'crm'.
                assert PROPOSTA_TOOL.module == "crm", PROPOSTA_TOOL.module
                nomes_crm_p = {t.name for t in tools_for_modules({"crm"})}
                nomes_financeiro_p = {t.name for t in tools_for_modules({"financeiro"})}
                assert "propor_proposta_comercial" in nomes_crm_p, nomes_crm_p
                assert "propor_proposta_comercial" not in nomes_financeiro_p, \
                    "propor_proposta_comercial vazou p/ módulo 'financeiro' (RBAC de módulo quebrado)"
                print("SUBTESTE proposta: RBAC de módulo (só 'crm' vê a tool) PASS")

                # (e) aprovador correto: propositor REAL (admin) excluído do conjunto
                # de aprovadores (reusa `admins`/`_UAdmin` resolvidos no bloco de cobrança acima).
                cli_p2, ttl_p2 = "__TESTE_5.4__ Cliente2", "__TESTE_5.4__ Título2"
                rp4 = await _propor_proposta(db, _UAdmin(admins[0]), _S(),
                    client_name=cli_p2, title=ttl_p2, valor_total=1234.56,
                    descricao="teste (propositor admin real)")
                if rp4.get("entity_id"):
                    prop_ids.append(rp4["entity_id"])
                if len(admins) >= 2:
                    assert rp4["status"] == "pendente", rp4
                    aps_p = rp4.get("aprovadores") or []
                    assert admins[0] not in aps_p, \
                        f"propositor admin real não pode aprovar a própria proposta: {aps_p}"
                    assert set(aps_p) == set(admins) - {admins[0]}, (aps_p, admins)
                    print(f"SUBTESTE proposta: aprovador correto (propositor excluído; "
                          f"{len(admins)} admins → {len(aps_p)} aprovadores) PASS")
                else:
                    assert "erro" in rp4, rp4
                    print("SUBTESTE proposta: aprovador correto (1 admin: propositor==único → fail-closed) PASS")

                print("SUBTESTE proposta PASS (draft criado, sent intocado, idempotente [sino+nativa], "
                      "RBAC módulo, aprovador correto)")

                # ── kit documental ──
                # Cliente de teste PRÓPRIO em ged_clients (marcado __TESTE_5.4__), não
                # um condomínio real: ged_document_kits só permite 1 kit por
                # (client_id, reference_month) — usar um condomínio real de produção
                # colidiria com o kit real do mês corrente (a maioria já tem um
                # 'em_montagem' para o mês atual) e o teste veria "duplicado" contra
                # a linha de produção em vez de provar a criação do 'proposto'.
                cli_kit_id = str(uuid.uuid4())
                await db.execute(text(
                    "INSERT INTO ged_clients (id, name, type, is_active, created_at, updated_at) "
                    "VALUES (:id, '__TESTE_5.4__ Cliente Kit', 'condominio', true, now(), now())"),
                    {"id": cli_kit_id})
                await db.commit()
                ged_kit_client_ids.append(cli_kit_id)

                rk = await _propor_kit(db, _U(), _S(),
                    client_id=cli_kit_id, tipo_kit="__TESTE_5.4__ kit")
                assert rk["status"] == "pendente", rk
                kid = rk["entity_id"]
                kit_ids.append(kid)

                # (a) nasceu 'proposto' (nunca outro status — nunca executado)
                st = (await db.execute(text(
                    "SELECT status FROM ged_document_kits WHERE id = :i"), {"i": kid})).scalar()
                assert st == "proposto", f"kit nasceu {st}, esperado proposto"

                # (b) ZERO geração/execução: só a linha 'proposto' criada acima existe
                #     para este cliente de teste (kit_orchestrator/_gerar_kit_real
                #     JAMAIS chamado por este código).
                n_kits_cliente = (await db.execute(text(
                    "SELECT count(*) FROM ged_document_kits WHERE client_id = :c"),
                    {"c": cli_kit_id})).scalar()
                assert n_kits_cliente == 1, f"esperado 1 kit (proposto) p/ cliente teste, veio {n_kits_cliente}"

                # (c) idempotência (sino): mesma idempotency_key → duplicado, inserir não roda de novo
                rk2 = await _propor_kit(db, _U(), _S(),
                    client_id=cli_kit_id, tipo_kit="__TESTE_5.4__ kit")
                assert rk2.get("duplicado") is True, rk2
                assert str(rk2["entity_id"]) == str(kid), rk2

                # idempotência NATIVA (defesa em profundidade, "não confie só no sino"):
                # desativa a notificação do sino e propõe de novo — quem tem que
                # barrar a 2ª linha é o SELECT-existing dentro do próprio _inserir,
                # sobre o grão REAL da tabela (client_id, reference_month), não
                # (client_id, tipo_kit) como o brief original assumia.
                idem_key_k = f"kit:{cli_kit_id}:__TESTE_5.4__ kit"
                await db.execute(text(
                    "UPDATE communication_notifications SET is_active = false "
                    "WHERE extra_data->>'idempotency_key' = :k"), {"k": idem_key_k})
                await db.commit()

                rk3 = await _propor_kit(db, _U(), _S(),
                    client_id=cli_kit_id, tipo_kit="__TESTE_5.4__ kit (sino desativado)")
                if rk3.get("entity_id") and rk3["entity_id"] not in kit_ids:
                    kit_ids.append(rk3["entity_id"])  # defesa: se a idempotência NATIVA falhar, limpa mesmo assim
                assert rk3["status"] == "pendente", rk3
                assert rk3["entity_id"] == kid, \
                    f"idempotência NATIVA falhou: criou 2ª linha em ged_document_kits ({rk3['entity_id']} != {kid})"
                n_kits_cliente2 = (await db.execute(text(
                    "SELECT count(*) FROM ged_document_kits WHERE client_id = :c"),
                    {"c": cli_kit_id})).scalar()
                assert n_kits_cliente2 == 1, \
                    f"idempotência NATIVA falhou: esperado 1 kit, veio {n_kits_cliente2}"
                print("SUBTESTE kit: idempotência (sino + NATIVA, grão client_id+reference_month) PASS")

                # (d) RBAC: a tool só aparece no belt de quem tem o módulo 'ged'.
                assert KIT_TOOL.module == "ged", KIT_TOOL.module
                nomes_ged = {t.name for t in tools_for_modules({"ged"})}
                nomes_financeiro_k = {t.name for t in tools_for_modules({"financeiro"})}
                assert "propor_kit" in nomes_ged, nomes_ged
                assert "propor_kit" not in nomes_financeiro_k, \
                    "propor_kit vazou p/ módulo 'financeiro' (RBAC de módulo quebrado)"
                print("SUBTESTE kit: RBAC de módulo (só 'ged' vê a tool) PASS")

                # (e) aprovador correto: propositor REAL (admin) excluído do conjunto
                # de aprovadores. ROLES_KIT_OP = ('admin', 'gerente_operacional');
                # reusa `admins`/`_UAdmin` resolvidos no bloco de cobrança acima (todo
                # admin ∈ resolução de ROLES_KIT_OP, pois 'admin' é um dos roles).
                assert ROLES_KIT_OP == ("admin", "gerente_operacional"), ROLES_KIT_OP
                aprovadores_kit_possiveis = await entrega.resolver_usuarios_por_roles(db, ROLES_KIT_OP)
                assert aprovadores_kit_possiveis, "esperado >=1 admin/gerente_operacional ativo no banco"

                cli_kit_id2 = str(uuid.uuid4())
                await db.execute(text(
                    "INSERT INTO ged_clients (id, name, type, is_active, created_at, updated_at) "
                    "VALUES (:id, '__TESTE_5.4__ Cliente Kit2', 'condominio', true, now(), now())"),
                    {"id": cli_kit_id2})
                await db.commit()
                ged_kit_client_ids.append(cli_kit_id2)

                rk4 = await _propor_kit(db, _UAdmin(admins[0]), _S(),
                    client_id=cli_kit_id2, tipo_kit="__TESTE_5.4__ kit (propositor admin real)")
                if rk4.get("entity_id"):
                    kit_ids.append(rk4["entity_id"])
                if len(aprovadores_kit_possiveis) >= 2:
                    assert rk4["status"] == "pendente", rk4
                    aps_k = rk4.get("aprovadores") or []
                    assert admins[0] not in aps_k, \
                        f"propositor admin real não pode aprovar o próprio kit: {aps_k}"
                    assert set(aps_k) == set(aprovadores_kit_possiveis) - {admins[0]}, \
                        (aps_k, aprovadores_kit_possiveis)
                    print(f"SUBTESTE kit: aprovador correto (propositor excluído; "
                          f"{len(aprovadores_kit_possiveis)} possíveis → {len(aps_k)} aprovadores) PASS")
                else:
                    assert "erro" in rk4, rk4
                    print("SUBTESTE kit: aprovador correto (fail-closed: propositor==único possível) PASS")

                # RBAC de entrada: client_id inválido/inexistente é recusado ANTES do
                # INSERT (fail-closed amigável, sem estourar a FK ged_document_kits_client_id_fkey).
                r_invalido = await _propor_kit(db, _U(), _S(),
                    client_id="não-é-uuid", tipo_kit="__TESTE_5.4__ kit")
                assert "erro" in r_invalido, r_invalido
                r_inexistente = await _propor_kit(db, _U(), _S(),
                    client_id=str(uuid.uuid4()), tipo_kit="__TESTE_5.4__ kit")
                assert "erro" in r_inexistente, r_inexistente
                print("SUBTESTE kit: client_id inválido/inexistente recusado (fail-closed, sem tocar a FK) PASS")

                print("SUBTESTE kit PASS (proposto criado, ZERO geração/execução, idempotente [sino+nativa], "
                      "RBAC módulo, aprovador correto)")
                print("TODOS OS SUBTESTES DE onda_a.py PASSARAM")
            finally:
                if cob_ids:
                    await db.execute(text("DELETE FROM inter_cobrancas WHERE id = ANY(:i)"), {"i": cob_ids})
                    # audit_logs (append-only p/ uso real; aqui é resíduo de TESTE, mesmo
                    # padrão de limpeza usado no __main__ de base.py) — 1 linha por
                    # chamada de propor(), sempre com details->>'entity_id' ∈ cob_ids.
                    await db.execute(text(
                        "DELETE FROM audit_logs WHERE details->>'entity_id' = ANY(:i)"),
                        {"i": cob_ids})
                await _limpar(db, "cobranca:TESTE-5.4-CLI:%")
                await _limpar(db, "cobranca:TESTE-5.4-CLI2:%")
                if prop_ids:
                    await db.execute(text("DELETE FROM proposals WHERE id = ANY(:i)"), {"i": prop_ids})
                    await db.execute(text(
                        "DELETE FROM audit_logs WHERE details->>'entity_id' = ANY(:i)"),
                        {"i": prop_ids})
                await _limpar(db, "proposta:__TESTE_5.4__%")
                if kit_ids:
                    await db.execute(text("DELETE FROM ged_document_kits WHERE id = ANY(:i)"), {"i": kit_ids})
                    await db.execute(text(
                        "DELETE FROM audit_logs WHERE details->>'entity_id' = ANY(:i)"),
                        {"i": kit_ids})
                if ged_kit_client_ids:
                    # rede de segurança: FK ON DELETE CASCADE de ged_document_kits já
                    # limpou pelo client_id acima, mas cobre o caso de o teste ter
                    # falhado ANTES de capturar o entity_id em kit_ids.
                    await db.execute(text(
                        "DELETE FROM ged_document_kits WHERE client_id = ANY(:i)"),
                        {"i": ged_kit_client_ids})
                    await db.execute(text("DELETE FROM ged_clients WHERE id = ANY(:i)"), {"i": ged_kit_client_ids})
                await _limpar(db, "kit:%__TESTE_5.4__%")
                await db.commit()
                rem = (await db.execute(text(
                    "SELECT count(*) FROM inter_cobrancas WHERE pagador->>'cliente_crm_id' IN "
                    "('TESTE-5.4-CLI', 'TESTE-5.4-CLI2')"))).scalar()
                rem_audit = (await db.execute(text(
                    "SELECT count(*) FROM audit_logs WHERE details->>'tool' = 'propor_cobranca' "
                    "AND details->>'entity_id' = ANY(:i)"), {"i": cob_ids})).scalar()
                assert rem == 0, f"remanescentes cobranca={rem}"
                assert rem_audit == 0, f"remanescentes audit_logs={rem_audit}"
                rem_p = (await db.execute(text(
                    "SELECT count(*) FROM proposals WHERE client_name LIKE '__TESTE_5.4__%'"))).scalar()
                rem_audit_p = (await db.execute(text(
                    "SELECT count(*) FROM audit_logs WHERE details->>'tool' = 'propor_proposta_comercial' "
                    "AND details->>'entity_id' = ANY(:i)"), {"i": prop_ids})).scalar()
                assert rem_p == 0, f"remanescentes proposals={rem_p}"
                assert rem_audit_p == 0, f"remanescentes audit_logs proposta={rem_audit_p}"
                rem_k = (await db.execute(text(
                    "SELECT count(*) FROM ged_document_kits WHERE client_id = ANY(:i)"),
                    {"i": ged_kit_client_ids})).scalar()
                rem_kc = (await db.execute(text(
                    "SELECT count(*) FROM ged_clients WHERE id = ANY(:i)"),
                    {"i": ged_kit_client_ids})).scalar()
                rem_audit_k = (await db.execute(text(
                    "SELECT count(*) FROM audit_logs WHERE details->>'tool' = 'propor_kit' "
                    "AND details->>'entity_id' = ANY(:i)"), {"i": kit_ids})).scalar()
                assert rem_k == 0, f"remanescentes ged_document_kits={rem_k}"
                assert rem_kc == 0, f"remanescentes ged_clients (teste)={rem_kc}"
                assert rem_audit_k == 0, f"remanescentes audit_logs kit={rem_audit_k}"
        await eng.dispose()

    asyncio.run(main())
