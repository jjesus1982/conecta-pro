"""SUITE-ORÁCULO da Fase 5.4 (propor→aprovar) — a prova formal, executável e
MUTAÇÃO-TESTADA de que as PAREDES INVIOLÁVEIS das 6 tools de ação seguram, e de
que a suite MORDE (falha) se alguém regredir. É o gate antes do deploy.

Doutrina (molde da suite 5.3, test_oraculos_proativo.py): a fronteira provada é o
DADO/EFEITO no banco (estado de execução == baseline, RBAC == belt/módulo,
propositor-excluído == conjunto de aprovadores retornado, idempotência == 1 linha
nativa + N notificações, audit == 1 linha append-only), NUNCA a prosa do LLM. Cada
inviolável = 1 oráculo, provado por diff/baseline (antes==depois), não por alegação.

Os 8 oráculos (spec Fase 5.4):
  1. LLM NUNCA executa — as 6 tools criam só PENDENTE na tabela nativa; o estado
     de EXECUÇÃO fica intocado (inter_payments 'executado'; recibo_s2230 NOT NULL;
     proposals 'sent'; inter_cobrancas cobranca_id_inter NOT NULL; allocations/posts;
     ged_document_kits fora de 'proposto').
  2. Dinheiro que SAI sem OTP = impossível — propor_lote cria 'preparado', 0
     'executado'; o handler não importa/chama gerar_otp/executar_lote/enviar_pix.
  3. eSocial NÃO transmite — propor_esocial cria 'proposto', recibo_s2230 intocado,
     S-1200 (Portte) recusado ANTES do INSERT; handler não chama transmitir_evento_sst.
  4. 3 papéis / propositor EXCLUÍDO (NÃO-VÁCUO) — propositor ADMIN REAL é removido
     do conjunto de aprovadores; se sobrar 0, fail-closed (proposta não registrada).
  5. RBAC de módulo — cada tool só no belt do SEU módulo (crm/ged/operacional/dp),
     nunca em outro; user_modules de um não-admin real (sem o módulo) não a traz.
  6. Idempotência — 2 propostas idênticas = 1 pendente nativa + N notificações
     (não 2N), p/ lote, esocial, cobrança e substituição.
  7. Operacional READ-ONLY — propor_substituicao não escreve allocations/posts.
  8. Audit append-only / nunca fabricar — cada propor grava exatamente 1 linha em
     audit_logs e a proposta reflete os args (sem número inventado).

MUTAÇÃO-TESTE (prova que a suite morde; molde 5.3):
  M1 — base.propor sem exclusão do propositor → oráculo 4 FALHA.
  M2 — tools_for_modules devolvendo tudo → oráculo 5 FALHA (vazamento).
  M3 — handler de lote chamando execução (stub) → oráculo 1/2 FALHA.
Se uma mutação NÃO derrubar o oráculo, o oráculo é fraco.

Bancada: throwaway `docker run --rm --memory=2g` (2 redes docker), NUNCA backend
vivo/green:8080 (OOM). Escreve no DB REAL — todo seed carrega o sentinel
`__TESTE_5.4__`; limpeza cirúrgica por id/sentinel no finally (0 remanescentes,
NUNCA apaga dado real). Imprime PASS/FAIL por oráculo + resultado das 3 mutações;
exit 0 só se os 8 oráculos PASS E as 3 mutações MORDEREM.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import json
import os
import textwrap
import traceback
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# ── Unidades sob prova (import de TODAS as ondas → registra as 6 tools) ──
from modules.ai.conversation.services.orquestrador.acoes import base, onda_a, onda_b, onda_c
from modules.ai.conversation.services.orquestrador.acoes.base import (
    ROLES_COMERCIAL, ROLES_KIT_OP, ROLES_MONEY, propor as base_propor,
)
from modules.ai.conversation.services.orquestrador.tool_registry import (
    all_tools, tools_for_modules,
)
from core.auth.module_scope import user_modules
from modules.notifications.proativo import entrega

MARK = "__TESTE_5.4__"  # sentinel: TODO seed carrega isto (limpeza + nunca-real)


class OracleFail(AssertionError):
    pass


class _U:
    def __init__(self, uid) -> None:
        self.id = uid


class _S:
    tier = "gestor"


class _RealUser:
    """Espelha um usuário REAL (role + permissions do banco) p/ o RBAC de módulo."""
    def __init__(self, uid, role, permissions) -> None:
        self.id = uid
        self.role = role
        self.permissions = permissions


def _mk(*parts: str) -> str:
    return ":".join((MARK, *parts, uuid.uuid4().hex[:8]))


def _code_symbols(fn) -> set[str]:
    """Nomes REALMENTE chamados/importados no corpo de `fn` (via AST — não
    substring, p/ não confundir menção em COMENTÁRIO com chamada de código).
    Usado p/ provar que o handler não CHAMA execução."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.name.split(".")[-1])
                if a.asname:
                    names.add(a.asname)
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                names.add(a.name)
                if a.asname:
                    names.add(a.asname)
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                names.add(f.id)
            elif isinstance(f, ast.Attribute):
                names.add(f.attr)
    return names


async def main() -> int:  # noqa: C901 (suite única e linear, como o molde 5.3)
    results: list[tuple[str, str, bool, str]] = []

    def record(n, desc: str, ok: bool, detail: str = "") -> None:
        results.append((n, desc, ok, detail))
        tag = "PASS" if ok else "FAIL"
        rot = f"ORACULO {n}" if isinstance(n, int) else str(n)
        print(f"{rot} {desc} ... {tag}{(' — ' + detail) if detail else ''}")

    eng = create_async_engine(os.environ["DATABASE_URL"])
    Session = async_sessionmaker(eng, expire_on_commit=False)

    # ids criados (limpeza cirúrgica por id no finally)
    cob_ids: list[str] = []
    prop_ids: list[str] = []
    sub_ids: list[str] = []
    lote_ids: list[str] = []
    esoc_ids: list[str] = []
    ged_client_ids: list[str] = []
    audit_entity_ids: list[str] = []  # todo entity_id que gerou linha de audit

    async with Session() as db:
        try:
            # ── identidades REAIS ──
            admins = await entrega.resolver_usuarios_por_roles(db, ("admin",))
            assert len(admins) >= 2, (
                f"esperado >=2 admins reais p/ o oráculo 4 ser NÃO-VÁCUO, veio {len(admins)}")
            prop = admins[0]                 # PROPOSITOR = admin real (não-vácuo)
            emp_id = (await db.execute(text("SELECT id::text FROM empresas LIMIT 1"))).scalar()
            assert emp_id, "esperado >=1 empresa (CNPJ) real"
            # não-admin real SEM módulo (permissions vazio) → belt de ação = 0.
            nao_admin_row = (await db.execute(text(
                "SELECT id::text, role, permissions::text FROM users "
                "WHERE coalesce(is_active,true) AND lower(coalesce(role,'')) <> 'admin' "
                "  AND (permissions IS NULL OR permissions::text IN ('null','[]','{}')) "
                "LIMIT 1"))).first()
            assert nao_admin_row, "esperado >=1 usuário real NÃO-admin p/ o RBAC"
            _perms_raw = nao_admin_row[2]
            try:
                _perms = json.loads(_perms_raw) if _perms_raw else []
            except (ValueError, TypeError):
                _perms = []
            user_nao_admin = _RealUser(nao_admin_row[0], nao_admin_row[1], _perms or [])

            # ── baselines de ESTADO DE EXECUÇÃO (o que NÃO pode mudar) ──
            async def _scalar(sql: str) -> int:
                return int((await db.execute(text(sql))).scalar() or 0)

            exec_lote_0 = await _scalar("SELECT count(*) FROM inter_payments WHERE status='executado'")
            tx_esoc_0 = await _scalar("SELECT count(*) FROM sst_afastamentos WHERE recibo_s2230 IS NOT NULL")
            prop_sent_0 = await _scalar("SELECT count(*) FROM proposals WHERE status='sent'")
            cob_emit_0 = await _scalar("SELECT count(*) FROM inter_cobrancas WHERE cobranca_id_inter IS NOT NULL")
            kit_exec_0 = await _scalar("SELECT count(*) FROM ged_document_kits WHERE status <> 'proposto'")

            # cliente GED de teste PRÓPRIO (kit exige 1 por (client_id, mês); não usar real)
            cli_kit = str(uuid.uuid4())
            await db.execute(text(
                "INSERT INTO ged_clients (id, name, type, is_active, created_at, updated_at) "
                "VALUES (:id, :n, 'condominio', true, now(), now())"),
                {"id": cli_kit, "n": f"{MARK} Cliente Kit"})
            await db.commit()
            ged_client_ids.append(cli_kit)

            # ════════════════ SETUP: 1 chamada por tool (propositor = admin real) ══
            r_cob = await onda_a._propor_cobranca(
                db, _U(prop), _S(), cliente_crm_id=f"{MARK}CLI", valor=12.34,
                vencimento="2099-12-31", descricao=f"{MARK} cobranca")
            if r_cob.get("entity_id"):
                cob_ids.append(r_cob["entity_id"]); audit_entity_ids.append(r_cob["entity_id"])

            r_prop = await onda_a._propor_proposta(
                db, _U(prop), _S(), client_name=f"{MARK} Cliente",
                title=f"{MARK} Titulo", valor_total=999.99, descricao="t")
            if r_prop.get("entity_id"):
                prop_ids.append(r_prop["entity_id"]); audit_entity_ids.append(r_prop["entity_id"])

            r_kit = await onda_a._propor_kit(
                db, _U(prop), _S(), client_id=cli_kit, tipo_kit=f"{MARK} kit")
            if r_kit.get("entity_id"):
                audit_entity_ids.append(r_kit["entity_id"])

            aloc_b = await _scalar("SELECT count(*) FROM allocations")
            posts_b = await _scalar("SELECT count(*) FROM posts")
            r_sub = await onda_b._propor_substituicao(
                db, _U(prop), _S(), post_id=f"{MARK}POSTO", data="2099-01-01",
                ausente_employee_id="EMP-A", substituto_employee_id="EMP-B", motivo=MARK)
            aloc_a = await _scalar("SELECT count(*) FROM allocations")
            posts_a = await _scalar("SELECT count(*) FROM posts")
            if r_sub.get("entity_id"):
                sub_ids.append(r_sub["entity_id"]); audit_entity_ids.append(r_sub["entity_id"])

            r_lote = await onda_c._propor_lote(
                db, _U(prop), _S(), posto=f"{MARK}POSTO", competencia="2099-01",
                itens=[{"nome": f"{MARK} Fulano", "chave": "teste@teste", "valor": 1.00}])
            if r_lote.get("entity_id"):
                lote_ids.append(r_lote["entity_id"]); audit_entity_ids.append(r_lote["entity_id"])

            ref_esoc = f"{MARK}ESOC-0001"
            r_esoc = await onda_c._propor_esocial(
                db, _U(prop), _S(), tipo_evento="S-2230", referencia=ref_esoc,
                empresa_id=emp_id, payload={"marca": MARK})
            if r_esoc.get("entity_id"):
                esoc_ids.append(r_esoc["entity_id"]); audit_entity_ids.append(r_esoc["entity_id"])

            for nome, r in (("cobranca", r_cob), ("proposta", r_prop), ("kit", r_kit),
                            ("substituicao", r_sub), ("lote", r_lote), ("esocial", r_esoc)):
                assert r.get("status") == "pendente", f"setup {nome} não criou pendente: {r}"

            # ════════════════ ORÁCULO 1 — LLM NUNCA EXECUTA (6 tools) ══════════════
            try:
                # cada pendente nasceu no status NATIVO (nunca executado)
                st_cob = (await db.execute(text("SELECT status FROM inter_cobrancas WHERE id=:i"),
                                           {"i": r_cob["entity_id"]})).scalar()
                st_prop = (await db.execute(text("SELECT status FROM proposals WHERE id=:i"),
                                            {"i": r_prop["entity_id"]})).scalar()
                st_kit = (await db.execute(text("SELECT status FROM ged_document_kits WHERE id=:i"),
                                           {"i": r_kit["entity_id"]})).scalar()
                st_sub = (await db.execute(text("SELECT status FROM op_substituicao_propostas WHERE id=:i"),
                                           {"i": r_sub["entity_id"]})).scalar()
                sts_lote = [x for x in (await db.execute(text(
                    "SELECT DISTINCT status FROM inter_payments WHERE lote_id=:l"),
                    {"l": r_lote["entity_id"]})).scalars().all()]
                st_esoc = (await db.execute(text(
                    "SELECT status FROM esocial_transmissao_propostas WHERE id=cast(:i as uuid)"),
                    {"i": r_esoc["entity_id"]})).scalar()
                assert st_cob == "PENDENTE", st_cob
                assert st_prop == "draft", st_prop
                assert st_kit == "proposto", st_kit
                assert st_sub == "pendente", st_sub
                assert sts_lote == ["preparado"], sts_lote
                assert st_esoc == "proposto", st_esoc
                # o ESTADO DE EXECUÇÃO permanece intocado (antes == depois)
                assert await _scalar("SELECT count(*) FROM inter_payments WHERE status='executado'") == exec_lote_0
                assert await _scalar("SELECT count(*) FROM sst_afastamentos WHERE recibo_s2230 IS NOT NULL") == tx_esoc_0
                assert await _scalar("SELECT count(*) FROM proposals WHERE status='sent'") == prop_sent_0
                assert await _scalar("SELECT count(*) FROM inter_cobrancas WHERE cobranca_id_inter IS NOT NULL") == cob_emit_0
                assert await _scalar("SELECT count(*) FROM ged_document_kits WHERE status<>'proposto'") == kit_exec_0
                record(1, "LLM nunca executa: 6 pendentes criados, execução intocada",
                       True, "cob=PENDENTE prop=draft kit=proposto sub=pendente lote=preparado esoc=proposto")
            except Exception as exc:
                await db.rollback()
                record(1, "LLM nunca executa: 6 pendentes criados, execução intocada",
                       False, f"{type(exc).__name__}: {exc}")

            # ════════════════ ORÁCULO 2 — DINHEIRO SEM OTP = IMPOSSÍVEL ════════════
            # (a) leitura: o handler de lote não importa/chama execução; (b) baseline
            # reforçado por uma criação NOVA de lote (função compartilhada com M3).
            try:
                syms_lote = _code_symbols(onda_c._propor_lote)
                for proib in ("executar_lote", "gerar_otp_lote", "enviar_pix",
                              "executar_pagamento", "enviar_pagamento"):
                    assert proib not in syms_lote, f"handler de lote CHAMA/IMPORTA {proib!r} (execução!)"
                ok2, det2, lid2 = await _check_money_exec(db, onda_c._propor_lote, prop, "CHK")
                if lid2:
                    lote_ids.append(lid2); audit_entity_ids.append(lid2)
                assert ok2, det2
                record(2, "dinheiro sem OTP impossível: lote 'preparado', 0 'executado', "
                          "sem símbolo de execução", True, det2)
            except Exception as exc:
                await db.rollback()
                record(2, "dinheiro sem OTP impossível", False, f"{type(exc).__name__}: {exc}")

            # ════════════════ ORÁCULO 3 — eSOCIAL NÃO TRANSMITE ═══════════════════
            try:
                syms_es = _code_symbols(onda_c._propor_esocial)
                for proib in ("transmitir_evento_sst", "transmitir_evento", "assinar_evento",
                              "enviar_evento", "transmitir"):
                    assert proib not in syms_es, f"handler eSocial CHAMA/IMPORTA {proib!r} (transmissão!)"
                # recibo_s2230 intocado (baseline global; setup já criou o 'proposto')
                assert await _scalar(
                    "SELECT count(*) FROM sst_afastamentos WHERE recibo_s2230 IS NOT NULL") == tx_esoc_0
                # S-1200 (folha, Portte) RECUSADO ANTES do INSERT
                ref_folha = f"{MARK}FOLHA-0001"
                r_folha = await onda_c._propor_esocial(
                    db, _U(prop), _S(), tipo_evento="S-1200", referencia=ref_folha, empresa_id=emp_id)
                assert "erro" in r_folha and "escopo" in r_folha["erro"], r_folha
                n_folha = int((await db.execute(text(
                    "SELECT count(*) FROM esocial_transmissao_propostas WHERE referencia = :r"),
                    {"r": ref_folha})).scalar() or 0)
                assert n_folha == 0, f"S-1200 gravou {n_folha} proposta(s) (deveria recusar antes do INSERT)"
                record(3, "eSocial não transmite: 'proposto', recibo intocado, S-1200 recusado",
                       True, f"tx=={tx_esoc_0}; S-1200→erro, 0 linha")
            except Exception as exc:
                await db.rollback()
                record(3, "eSocial não transmite", False, f"{type(exc).__name__}: {exc}")

            # ════════════════ ORÁCULO 4 — 3 PAPÉIS / PROPOSITOR EXCLUÍDO (NÃO-VÁCUO) ═
            try:
                await _oraculo_4(db, base_propor, admins, audit_entity_ids)
                record(4, "propositor ADMIN real excluído dos aprovadores + fail-closed",
                       True, f"{len(admins)} admins → propositor removido; 0-aprovador ⇒ recusa")
            except Exception as exc:
                await db.rollback()
                record(4, "propositor ADMIN real excluído dos aprovadores + fail-closed",
                       False, f"{type(exc).__name__}: {exc}")

            # ════════════════ ORÁCULO 5 — RBAC DE MÓDULO ══════════════════════════
            try:
                _oraculo_5(tools_for_modules, user_modules, user_nao_admin, admins)
                record(5, "RBAC de módulo: cada tool só no seu belt; não-admin sem módulo não a vê",
                       True, f"não-admin role={user_nao_admin.role!r} → 0 tool de ação")
            except Exception as exc:
                record(5, "RBAC de módulo", False, f"{type(exc).__name__}: {exc}")

            # ════════════════ ORÁCULO 6 — IDEMPOTÊNCIA (lote, esoc, cob, subst) ════
            try:
                async def _native_count(sql: str, params: dict) -> int:
                    return int((await db.execute(text(sql), params)).scalar() or 0)

                async def _notif_count(key: str) -> int:
                    return int((await db.execute(text(
                        "SELECT count(*) FROM communication_notifications "
                        "WHERE extra_data->>'idempotency_key' = :k"), {"k": key})).scalar() or 0)

                casos = [
                    ("cobranca", r_cob,
                     lambda: onda_a._propor_cobranca(db, _U(prop), _S(), cliente_crm_id=f"{MARK}CLI",
                                                     valor=12.34, vencimento="2099-12-31", descricao="dup"),
                     f"cobranca:{MARK}CLI:12.34:2099-12-31",
                     "SELECT count(*) FROM inter_cobrancas WHERE pagador->>'cliente_crm_id'=:v AND status='PENDENTE'",
                     {"v": f"{MARK}CLI"}),
                    ("substituicao", r_sub,
                     lambda: onda_b._propor_substituicao(db, _U(prop), _S(), post_id=f"{MARK}POSTO",
                                                         data="2099-01-01", ausente_employee_id="EMP-A",
                                                         substituto_employee_id="EMP-B"),
                     f"substituicao:{MARK}POSTO:2099-01-01:EMP-A",
                     "SELECT count(*) FROM op_substituicao_propostas WHERE post_id=:v AND status='pendente'",
                     {"v": f"{MARK}POSTO"}),
                    ("lote", r_lote,
                     lambda: onda_c._propor_lote(db, _U(prop), _S(), posto=f"{MARK}POSTO",
                                                 competencia="2099-01",
                                                 itens=[{"nome": "x", "chave": "k", "valor": 1.00}]),
                     f"lote:{MARK}POSTO:2099-01:1.00",
                     "SELECT count(DISTINCT lote_id) FROM inter_payments WHERE strpos(observacoes, :v) > 0",
                     {"v": f"({MARK}POSTO)"}),
                    ("esocial", r_esoc,
                     lambda: onda_c._propor_esocial(db, _U(prop), _S(), tipo_evento="S-2230",
                                                    referencia=ref_esoc, empresa_id=emp_id),
                     f"esocial:{ref_esoc}:S-2230",
                     "SELECT count(*) FROM esocial_transmissao_propostas WHERE referencia=:v AND status='proposto'",
                     {"v": ref_esoc}),
                ]
                detalhes = []
                for nome, r1, call2, key, native_sql, native_p in casos:
                    n_apr = len(r1.get("aprovadores") or [])
                    assert n_apr >= 1, f"{nome}: 1ª proposta sem aprovadores (setup inválido)"
                    r2 = await call2()
                    assert r2.get("duplicado") is True, f"{nome}: 2ª idêntica não marcada duplicado: {r2}"
                    n_nat = await _native_count(native_sql, native_p)
                    assert n_nat == 1, f"{nome}: {n_nat} linhas nativas (esperado 1 pendente)"
                    n_notif = await _notif_count(key)
                    assert n_notif == n_apr, f"{nome}: {n_notif} notificações (esperado N={n_apr}, não 2N)"
                    detalhes.append(f"{nome}: 1 nativa/{n_notif} notif")
                record(6, "idempotência: 2 idênticas = 1 pendente nativa + N notif (não 2N)",
                       True, "; ".join(detalhes))
            except Exception as exc:
                await db.rollback()
                record(6, "idempotência", False, f"{type(exc).__name__}: {exc}")

            # ════════════════ ORÁCULO 7 — OPERACIONAL READ-ONLY ═══════════════════
            try:
                assert aloc_a == aloc_b, f"allocations mudou: {aloc_b}→{aloc_a}"
                assert posts_a == posts_b, f"posts mudou: {posts_b}→{posts_a}"
                record(7, "operacional read-only: substituição não escreve allocations/posts",
                       True, f"allocations={aloc_a} posts={posts_a} (inalterados)")
            except Exception as exc:
                record(7, "operacional read-only", False, f"{type(exc).__name__}: {exc}")

            # ════════════════ ORÁCULO 8 — AUDIT append-only / nunca fabricar ═══════
            try:
                for nome, eid in (("cobranca", r_cob["entity_id"]), ("proposta", r_prop["entity_id"]),
                                  ("kit", r_kit["entity_id"]), ("substituicao", r_sub["entity_id"]),
                                  ("lote", r_lote["entity_id"]), ("esocial", r_esoc["entity_id"])):
                    n_aud = int((await db.execute(text(
                        "SELECT count(*) FROM audit_logs WHERE details->>'entity_id' = :e "
                        "AND action = 'agent_action' AND category = 'agent'"),
                        {"e": str(eid)})).scalar() or 0)
                    assert n_aud == 1, f"{nome}: {n_aud} linhas de audit (esperado exatamente 1)"
                # nunca fabricar: a proposta reflete os args (cobrança valor==12.34 no banco E no audit)
                val_nat = (await db.execute(text(
                    "SELECT valor FROM inter_cobrancas WHERE id=:i"), {"i": r_cob["entity_id"]})).scalar()
                assert float(val_nat) == 12.34, f"valor nativo divergente: {val_nat}"
                aud_args = (await db.execute(text(
                    "SELECT details->'args'->>'valor' FROM audit_logs "
                    "WHERE details->>'entity_id' = :e"), {"e": r_cob["entity_id"]})).scalar()
                assert aud_args is not None and abs(float(aud_args) - 12.34) < 1e-9, \
                    f"audit args.valor divergente/inventado: {aud_args}"
                record(8, "audit append-only (1 linha/propor) + proposta reflete args (sem inventar)",
                       True, "6× exatamente 1 audit; cobrança valor==12.34 (banco==audit)")
            except Exception as exc:
                record(8, "audit append-only + nunca fabricar", False, f"{type(exc).__name__}: {exc}")

            # ════════════════ MUTAÇÃO-TESTE — a suite MORDE? ══════════════════════
            # M1: base.propor SEM exclusão do propositor → oráculo 4 deve FALHAR.
            m1_ok, m1_det = await _expect_bite(
                lambda: _oraculo_4(db, _propor_MUT_sem_exclusao, admins, audit_entity_ids))
            record("MUTAÇÃO M1", "quebra exclusão do propositor → oráculo 4", m1_ok, m1_det)
            await db.rollback()

            # M2: tools_for_modules devolve TUDO → oráculo 5 deve FALHAR (vazamento).
            def _tfm_vaza(_mods):
                return all_tools()
            m2_ok, m2_det = await _expect_bite_sync(
                lambda: _oraculo_5(_tfm_vaza, user_modules, user_nao_admin, admins))
            record("MUTAÇÃO M2", "quebra filtro de módulo (vaza tudo) → oráculo 5", m2_ok, m2_det)

            # M3: handler de lote chama execução (stub) → oráculo 1/2 deve FALHAR.
            async def _lote_MUT_executa(db, user, scope, **kw):
                r = await onda_c._propor_lote(db, user, scope, **kw)
                if r.get("entity_id"):
                    await db.execute(text(
                        "UPDATE inter_payments SET status='executado' WHERE lote_id=:l"),
                        {"l": r["entity_id"]})
                    await db.commit()
                return r
            m3_ok, m3_det, lid_mut = await _expect_bite_money(
                db, _lote_MUT_executa, prop)
            if lid_mut:
                lote_ids.append(lid_mut); audit_entity_ids.append(lid_mut)
            record("MUTAÇÃO M3", "handler de lote chama execução → oráculo 1/2", m3_ok, m3_det)
            await db.rollback()

        finally:
            # ══════════════ LIMPEZA — 0 remanescentes (por id + sentinel) ══════════
            await db.rollback()
            # audit (append-only em produção; aqui é resíduo de TESTE, por entity_id)
            if audit_entity_ids:
                await db.execute(text("DELETE FROM audit_logs WHERE details->>'entity_id' = ANY(:i)"),
                                 {"i": [str(x) for x in audit_entity_ids]})
            # NOTA: sentinel casado por strpos LITERAL (não LIKE) — MARK contém '_',
            # que em LIKE é curinga e poderia varrer DADO REAL. strpos é substring exata.
            M = {"m": MARK}
            # notificações do sino (todas carregam o sentinel na idempotency_key)
            await db.execute(text(
                "DELETE FROM communication_notifications "
                "WHERE strpos(coalesce(extra_data->>'idempotency_key',''), :m) > 0"), M)
            # tabelas nativas (por id + rede de segurança por sentinel literal)
            if cob_ids:
                await db.execute(text("DELETE FROM inter_cobrancas WHERE id = ANY(:i)"), {"i": cob_ids})
            await db.execute(text(
                "DELETE FROM inter_cobrancas WHERE strpos(coalesce(pagador->>'cliente_crm_id',''), :m) > 0"), M)
            if prop_ids:
                await db.execute(text("DELETE FROM proposals WHERE id = ANY(:i)"), {"i": prop_ids})
            await db.execute(text("DELETE FROM proposals WHERE strpos(coalesce(client_name,''), :m) > 0"), M)
            if sub_ids:
                await db.execute(text("DELETE FROM op_substituicao_propostas WHERE id = ANY(:i)"), {"i": sub_ids})
            await db.execute(text("DELETE FROM op_substituicao_propostas WHERE strpos(coalesce(post_id,''), :m) > 0"), M)
            for lid in lote_ids:
                await db.execute(text("DELETE FROM inter_payments WHERE lote_id = :l"), {"l": lid})
            await db.execute(text("DELETE FROM inter_payments WHERE strpos(coalesce(observacoes,''), :m) > 0"), M)
            if esoc_ids:
                await db.execute(text("DELETE FROM esocial_transmissao_propostas WHERE id = ANY(:i)"), {"i": esoc_ids})
            await db.execute(text("DELETE FROM esocial_transmissao_propostas WHERE strpos(coalesce(referencia,''), :m) > 0"), M)
            if ged_client_ids:
                await db.execute(text("DELETE FROM ged_document_kits WHERE client_id = ANY(:i)"), {"i": ged_client_ids})
                await db.execute(text("DELETE FROM ged_clients WHERE id = ANY(:i)"), {"i": ged_client_ids})
            await db.commit()

            # PROVA de limpeza: 0 remanescentes por sentinel LITERAL (query independente)
            async def _rem(sql: str) -> int:
                return int((await db.execute(text(sql), M)).scalar() or 0)

            rem = {}
            rem["cobranca"] = await _rem("SELECT count(*) FROM inter_cobrancas WHERE strpos(coalesce(pagador->>'cliente_crm_id',''), :m) > 0")
            rem["proposta"] = await _rem("SELECT count(*) FROM proposals WHERE strpos(coalesce(client_name,''), :m) > 0")
            rem["substituicao"] = await _rem("SELECT count(*) FROM op_substituicao_propostas WHERE strpos(coalesce(post_id,''), :m) > 0")
            rem["lote"] = await _rem("SELECT count(*) FROM inter_payments WHERE strpos(coalesce(observacoes,''), :m) > 0")
            rem["esocial"] = await _rem("SELECT count(*) FROM esocial_transmissao_propostas WHERE strpos(coalesce(referencia,''), :m) > 0")
            rem["ged_kit"] = await _rem("SELECT count(*) FROM ged_document_kits k JOIN ged_clients c ON c.id=k.client_id WHERE strpos(coalesce(c.name,''), :m) > 0")
            rem["ged_cli"] = await _rem("SELECT count(*) FROM ged_clients WHERE strpos(coalesce(name,''), :m) > 0")
            rem["notif"] = await _rem("SELECT count(*) FROM communication_notifications WHERE strpos(coalesce(extra_data->>'idempotency_key',''), :m) > 0")
            rem["audit"] = 0
            if audit_entity_ids:
                rem["audit"] = int((await db.execute(text(
                    "SELECT count(*) FROM audit_logs WHERE details->>'entity_id' = ANY(:i)"),
                    {"i": [str(x) for x in audit_entity_ids]})).scalar() or 0)
            total_rem = sum(rem.values())
            if total_rem == 0:
                print(f"\nLIMPEZA OK — 0 remanescentes ({', '.join(f'{k}={v}' for k, v in rem.items())})")
            else:
                print(f"\nLIMPEZA FALHOU — remanescentes: {rem}")
            record("LIMPEZA", "0 remanescentes do que a suite criou", total_rem == 0,
                   f"total={total_rem}")

    await eng.dispose()

    # ══════════════ RESUMO ══════════════
    oraculos = [r for r in results if isinstance(r[0], int)]
    mutacoes = [r for r in results if isinstance(r[0], str) and r[0].startswith("MUTAÇÃO")]
    limpeza = [r for r in results if r[0] == "LIMPEZA"]
    n_pass = sum(1 for r in oraculos if r[2])
    n_bite = sum(1 for r in mutacoes if r[2])
    print("\n" + "═" * 68)
    print(f"RESUMO: {n_pass}/{len(oraculos)} oráculos PASS  |  "
          f"{n_bite}/{len(mutacoes)} mutações MORDERAM  |  "
          f"limpeza {'OK' if limpeza and limpeza[0][2] else 'FALHOU'}")
    falhas = [r for r in results if not r[2]]
    if falhas:
        print("FALHAS (findings — é o gate mordendo, NÃO ajustar o teste):")
        for n, desc, _ok, det in falhas:
            print(f"  ✗ {n} {desc} — {det}")
        print("═" * 68)
        print("GATE: BLOQUEADO.")
        return 1
    print("═" * 68)
    print(f"OK suite 5.4 ({n_pass}/{len(oraculos)} oráculos + {n_bite}/{len(mutacoes)} mutações) — GATE LIBERADO.")
    return 0


# ───────────────────────── oráculos reutilizáveis (p/ mutação) ──────────────

async def _oraculo_4(db, propor_fn, admins, audit_entity_ids) -> bool:
    """Propositor ADMIN real EXCLUÍDO do conjunto de aprovadores (NÃO-VÁCUO) +
    fail-closed quando só o propositor resolveria. Testado contra `propor_fn`
    (real = base.propor; mutado = sem a exclusão → deve derrubar este oráculo)."""
    prop = admins[0]
    # (a) NÃO-VÁCUO: admin real propõe → é removido; sobra o resto dos admins.
    entity_a = str(uuid.uuid4())
    audit_entity_ids.append(entity_a)

    async def _fake_a(_db) -> str:
        return entity_a

    r = await propor_fn(
        db, user=_U(prop), scope=_S(), dominio=f"o4{MARK}", gate="🟡",
        roles_aprovador=ROLES_MONEY, idempotency_key=_mk("o4a"),
        titulo=f"[{MARK}] o4a", corpo="c", action_url="/x", tool="propor_o4a",
        args={}, entity_type="teste", inserir=_fake_a)
    assert r.get("status") == "pendente", f"o4(a): esperado pendente, veio {r}"
    aps = [str(a) for a in (r.get("aprovadores") or [])]
    assert str(prop) not in aps, f"o4: propositor admin NÃO pode aprovar a si mesmo: {aps}"
    assert set(aps) == {str(a) for a in admins} - {str(prop)}, (aps, admins)
    assert len(aps) >= 1, "o4: NÃO-VÁCUO — deveria sobrar >=1 aprovador"

    # (b) FAIL-CLOSED: se só o propositor resolveria → 0 aprovador → recusa (inserir não roda).
    orig = entrega.resolver_usuarios_por_roles
    only = str(prop)
    chamou = {"n": 0}

    async def _resolver_so_ele(_db, roles):
        return [only]

    async def _boom(_db) -> str:
        chamou["n"] += 1
        return "x"

    entrega.resolver_usuarios_por_roles = _resolver_so_ele
    try:
        r2 = await propor_fn(
            db, user=_U(only), scope=_S(), dominio=f"o4{MARK}", gate="🔴",
            roles_aprovador=ROLES_MONEY, idempotency_key=_mk("o4b"),
            titulo=f"[{MARK}] o4b", corpo="c", action_url="/x", tool="propor_o4b",
            args={}, entity_type="teste", inserir=_boom)
    finally:
        entrega.resolver_usuarios_por_roles = orig
    assert "erro" in r2, f"o4(b): fail-closed deveria recusar (só o propositor), veio {r2}"
    assert chamou["n"] == 0, "o4(b): inserir rodou apesar de 0 aprovador (fail-closed quebrado)"
    return True


def _oraculo_5(tools_for_modules_fn, user_modules_fn, user_nao_admin, admins) -> bool:
    """Cada tool só no belt do SEU módulo, nunca em outro; e um não-admin real (sem
    o módulo) não recebe a tool. Testado contra `tools_for_modules_fn` (real; mutado
    = devolve tudo → deve derrubar este oráculo por vazamento)."""
    esperado = {
        "propor_cobranca": "crm", "propor_proposta_comercial": "crm", "propor_kit": "ged",
        "propor_substituicao": "operacional", "propor_lote_pagamento": "dp", "propor_esocial": "dp",
    }
    outros = {"crm", "ged", "dp", "operacional", "financeiro", "fiscal", "juridico", "sst"}
    for tool_name, mod in esperado.items():
        no_belt = {t.name for t in tools_for_modules_fn({mod})}
        assert tool_name in no_belt, f"{tool_name} ausente do belt do próprio módulo {mod!r}"
        for outro in outros - {mod}:
            fora = {t.name for t in tools_for_modules_fn({outro})}
            assert tool_name not in fora, f"{tool_name} VAZOU p/ módulo {outro!r} (RBAC de módulo quebrado)"
    # user_modules: não-admin real sem módulo → 0 tool de ação no seu belt
    mods_nao_admin = user_modules_fn(user_nao_admin)
    belt_nao_admin = {t.name for t in tools_for_modules_fn(mods_nao_admin)}
    for tool_name in esperado:
        assert tool_name not in belt_nao_admin, \
            f"{tool_name} apareceu p/ não-admin (módulos={mods_nao_admin})"
    return True


async def _check_money_exec(db, lote_handler, prop, tag):
    """Cria um lote NOVO e prova: nasce 'preparado' e o count de 'executado' não
    muda. Compartilhado entre o oráculo 2 (real) e a mutação M3 (handler que executa
    → esta função deve levantar AssertionError = oráculo morde)."""
    exec_antes = int((await db.execute(text(
        "SELECT count(*) FROM inter_payments WHERE status='executado'"))).scalar() or 0)
    r = await lote_handler(
        db, _U(prop), _S(), posto=f"{MARK}POSTO{tag}", competencia="2099-02",
        itens=[{"nome": f"{MARK} Z", "chave": "z@z", "valor": 2.00}])
    lid = r.get("entity_id")
    assert r.get("status") == "pendente", f"lote {tag}: esperado pendente, veio {r}"
    sts = [x for x in (await db.execute(text(
        "SELECT DISTINCT status FROM inter_payments WHERE lote_id=:l"), {"l": lid})).scalars().all()]
    assert sts == ["preparado"], f"lote {tag}: status {sts} (esperado só 'preparado')"
    exec_depois = int((await db.execute(text(
        "SELECT count(*) FROM inter_payments WHERE status='executado'"))).scalar() or 0)
    assert exec_depois == exec_antes, \
        f"lote {tag}: 'executado' mudou {exec_antes}→{exec_depois} (dinheiro sem OTP!)"
    return True, f"lote {tag}: preparado; executado=={exec_depois}", lid


async def _propor_MUT_sem_exclusao(db, *, user, roles_aprovador, idempotency_key=None, **_kw):
    """MUTAÇÃO M1: cópia de base.propor com o BUG — NÃO exclui o propositor do
    conjunto de aprovadores (3 papéis quebrados). Só computa/retorna aprovadores
    (não escreve no banco); suficiente p/ o oráculo 4 observar a regressão."""
    aprovadores = await entrega.resolver_usuarios_por_roles(db, roles_aprovador)
    if not aprovadores:
        return {"erro": "sem aprovador (fail-closed)"}
    return {"status": "pendente", "aprovadores": aprovadores}


# ───────────────────────── helpers de mutação ──────────────────────────────

async def _expect_bite(coro_factory):
    """A mutação MORDE se o oráculo (async) FALHA sob ela."""
    try:
        await coro_factory()
    except (AssertionError, OracleFail) as exc:
        return True, f"mordeu ({type(exc).__name__}: {exc})"
    return False, "NÃO mordeu — oráculo passou sob mutação (oráculo FRACO!)"


async def _expect_bite_sync(fn):
    """Idem, p/ oráculo síncrono."""
    try:
        fn()
    except (AssertionError, OracleFail) as exc:
        return True, f"mordeu ({type(exc).__name__}: {exc})"
    return False, "NÃO mordeu — oráculo passou sob mutação (oráculo FRACO!)"


async def _expect_bite_money(db, lote_handler, prop):
    """M3: roda _check_money_exec com o handler mutado; MORDE se ele levantar."""
    lid = None
    try:
        _ok, _det, lid = await _check_money_exec(db, lote_handler, prop, "MUT")
    except (AssertionError, OracleFail) as exc:
        return True, f"mordeu ({type(exc).__name__}: {exc})", lid
    return False, "NÃO mordeu — oráculo 1/2 passou sob mutação (oráculo FRACO!)", lid


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        traceback.print_exc()
        code = 2
    raise SystemExit(code)
