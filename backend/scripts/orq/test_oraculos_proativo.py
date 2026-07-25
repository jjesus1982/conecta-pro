"""SUITE-ORÁCULO da Fase 5.3 (Proativo) — a prova formal e reprodutível das
garantias do proativo, contra o DADO/IDENTIDADES REAIS. É o gate que autoriza o
deploy (T9): nada passa se um oráculo falhar.

LLM-independente por doutrina: a fronteira é o DADO/EFEITO (detecção == query,
RBAC == destinatário no banco, dedup == estado, groundedness == número do
template, digest == linha consolidada), NUNCA a prosa do LLM. O redator é
neutralizado para o caminho determinístico (template) durante `_avaliar`; o
oráculo de groundedness exercita a lógica REAL do redator com um `gerar_fn`
mockado. O MODEL_CHAIN quebrado (gpt-5 em fix paralelo) NÃO afeta o gate.

Os 6 oráculos (spec Fase 5.3):
  1. Detecção real hoje == query-fonte (self-oracle p/ as 7 regras).
  2. RBAC: financeiro (caixa/aging) SÓ p/ admin — ZERO p/ gestor/funcionário
     (query negativa no banco); operacional alcança admin+gestores, não os demais.
  3. Anti-spam/dedup: avaliar 2x → 0 novo na 2ª; regra que estoura NÃO resolve
     seus alertas (isolamento por regra).
  4. Digest: N persistentes → 1 notificação consolidada por destinatário; RBAC no
     corpo (gestor sem financeiro); 2x/dia não duplica.
  5. Groundedness: número do alerta == número da query (template determinístico);
     fabricação (número extra) barrada.
  6. Nunca fabricar: regra sem dado → silêncio honesto (0 achados, list vazia,
     NÃO exceção).
  (+) Prova 7 / limpeza: 0 remanescentes do que a suite criou (diff pre/pós por
     id/correlation_id — NUNCA por janela de tempo ou UPDATE em massa: não apaga
     dado real de produção).
  (+) MUTAÇÃO-TESTE: injeta um vazamento RBAC sintético e prova que o oráculo 2 o
     PEGA (o gate morde — não é vacuamente verde).

Bancada: throwaway `conecta-pro-backend` na rede do compose (NUNCA green/:8080).
Roda de uma vez; imprime `ORACULO N ... PASS/FAIL`, resumo final, exit != 0 se
QUALQUER oráculo falhar. Se um oráculo falhar de VERDADE → é finding, não se
ajusta o teste pra passar.
"""
from __future__ import annotations

import asyncio
import json
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text

from core.database import async_session_factory

# Módulos sob prova
from modules.notifications.proativo import estado, redator
from modules.notifications.proativo.entrega import resolver_usuarios_por_roles
from modules.notifications.proativo.redator import redigir as _redigir_real
from modules.notifications.proativo.regras import REGISTRY, Regra
from modules.notifications.proativo.tasks import _avaliar, _digest

MARK = "__ORC53__"  # marcador único dos seeds sintéticos (dupla garantia de limpeza)

# Fonte-de-verdade por regra p/ o oráculo 1 (self-oracle: count == len(detectar)).
_FONTES = {
    "posto_descoberto":
        "SELECT count(*) FROM posts WHERE is_active "
        "AND current_headcount < required_headcount",
    "certidao_vencendo":
        "SELECT count(*) FROM ged_certidoes "
        "WHERE expiry_date <= (now() AT TIME ZONE 'America/Manaus')::date + 30",
    "aging_reforcado":
        "SELECT count(*) FROM receivable_accounts "
        "WHERE due_date < current_date "
        "AND coalesce(status::text,'') NOT ILIKE '%pag%' "
        "AND coalesce(status::text,'') NOT ILIKE '%cancel%'",
    "justificativa_parada":
        "SELECT count(*) FROM gp_justifications "
        "WHERE lower(coalesce(status,'')) IN ('pending','pendente') "
        "AND created_at < now() - interval '48 hours'",
    "juridico_prazo":
        "SELECT count(*) FROM juridico_prazos "
        "WHERE data_limite <= (now() AT TIME ZONE 'America/Manaus')::date + 7 "
        "AND lower(coalesce(status,'')) NOT IN ('cumprido')",
    "recrutamento_parado":
        "SELECT count(*) FROM candidates "
        "WHERE coalesce(is_active,true) AND coalesce(is_deleted,false)=false "
        "AND lower(coalesce(status,'')) IN ('em_analise','em_análise','triagem','entrevista') "
        "AND updated_at < now() - interval '7 days'",
}


class OracleFail(AssertionError):
    pass


async def _redigir_template(regra, achado, **_kw):
    """Neutraliza o LLM: usa SEMPRE o template determinístico (title, body).
    _avaliar redige via `redator.redigir` (lookup no módulo em tempo de chamada)."""
    return regra.template(achado.dados)


async def main() -> int:
    results: list[tuple[int, str, bool, str]] = []

    def record(n: int, desc: str, ok: bool, detail: str = "") -> None:
        status = "PASS" if ok else "FAIL"
        results.append((n, desc, ok, detail))
        print(f"ORACULO {n} {desc} ... {status}{(' — ' + detail) if detail else ''}")

    # Patch determinístico do redator p/ _avaliar (restaurado no finally).
    _orig_redigir = redator.redigir
    redator.redigir = _redigir_template  # type: ignore[assignment]

    async with async_session_factory() as db:
        # ── SNAPSHOT PRÉ-TESTE (limpeza cirúrgica por diff, não por tempo) ──
        pre_state = set((await db.execute(text(
            "SELECT correlation_id FROM proativo_alert_state"))).scalars().all())
        pre_notif = set((await db.execute(text(
            "SELECT id::text FROM communication_notifications "
            "WHERE extra_data->>'origem' IN ('proativo','proativo_digest')"))).scalars().all())
        pre_list = list(pre_notif) or ['']
        pre_state_list = list(pre_state) or ['']

        # Identidades reais por role (RBAC vive aqui).
        admins = await resolver_usuarios_por_roles(db, ("admin",))
        gerentes = await resolver_usuarios_por_roles(db, ("gerente_operacional",))
        supervisores = await resolver_usuarios_por_roles(db, ("supervisor",))
        funcionarios = await resolver_usuarios_por_roles(db, ("funcionario", "agente", "lider"))

        try:
            # ══════════════ ORÁCULO 1 — DETECÇÃO REAL == QUERY ══════════════
            try:
                nums: dict[str, int] = {}
                for nome, sql in _FONTES.items():
                    src = int((await db.execute(text(sql))).scalar() or 0)
                    achados = await REGISTRY[nome].detectar(db)
                    assert isinstance(achados, list), f"{nome}: detectar não retornou list"
                    if nome == "aging_reforcado":
                        # agregado: 1 achado sse existe vencido; e n == count-fonte
                        assert len(achados) == (1 if src > 0 else 0), \
                            f"aging: len={len(achados)} src={src}"
                        if achados:
                            assert achados[0].dados["n"] == src, \
                                f"aging n={achados[0].dados['n']} != src={src}"
                    else:
                        assert len(achados) == src, \
                            f"{nome}: len(detectar)={len(achados)} != fonte={src}"
                    nums[nome] = src
                # caixa: sem count-SQL puro (saldo vivo) → invariante saldo<limiar, limiar>0
                achados_caixa = await REGISTRY["caixa_baixo_cnpj"].detectar(db)
                for a in achados_caixa:
                    assert a.dados["saldo"] < a.dados["limiar"] and a.dados["limiar"] > 0, \
                        f"caixa invariante quebrada: {a.dados}"
                nums["caixa_baixo_cnpj"] = len(achados_caixa)
                detalhe = " ".join(f"{k.split('_')[0]}={v}" for k, v in nums.items())
                record(1, "detecção real == query-fonte (7 regras)", True, detalhe)
            except Exception as exc:
                record(1, "detecção real == query-fonte (7 regras)", False,
                       f"{type(exc).__name__}: {exc}")

            # ══════════════ ORÁCULO 6 — NUNCA FABRICAR (silêncio honesto) ══════
            # (roda antes de _avaliar; independe de escrita). Regra com fonte 0 →
            # list vazia, NÃO None, NÃO exceção.
            try:
                vazias: list[str] = []
                for nome, sql in _FONTES.items():
                    src = int((await db.execute(text(sql))).scalar() or 0)
                    achados = await REGISTRY[nome].detectar(db)  # não pode levantar
                    assert isinstance(achados, list), f"{nome} não retornou list"
                    if src == 0:
                        assert achados == [], f"{nome}: fonte 0 mas achados={achados}"
                        vazias.append(nome)
                assert vazias, ("nenhuma regra vazia hoje p/ provar silêncio — "
                                "esperado ao menos juridico/recrutamento vazios")
                record(6, "regra sem dado → 0 achados, list vazia (não exceção)",
                       True, f"vazias-honestas: {', '.join(vazias)}")
            except Exception as exc:
                record(6, "regra sem dado → 0 achados, list vazia (não exceção)",
                       False, f"{type(exc).__name__}: {exc}")

            # ══════════════ SETUP p/ 2 e 3 — rodar _avaliar 2x ══════════════
            avaliar_ok = True
            r1 = r2 = None
            try:
                r1 = await _avaliar(db)
                r2 = await _avaliar(db)
            except Exception as exc:
                avaliar_ok = False
                print(f"  [setup _avaliar falhou] {type(exc).__name__}: {exc}")

            # ══════════════ ORÁCULO 2 — RBAC (query negativa no banco) ══════════
            try:
                assert avaliar_ok and r1 is not None, "setup _avaliar falhou"
                # (a) NEGATIVA: 0 notif financeira do proativo p/ gestor/funcionário
                nao_admin = list({*gerentes, *supervisores, *funcionarios})
                vaz = 0
                if nao_admin:
                    vaz = int((await db.execute(text(
                        "SELECT count(*) FROM communication_notifications "
                        "WHERE user_id = ANY(:g) AND extra_data->>'origem'='proativo' "
                        "AND extra_data->>'familia'='financeiro' "
                        "AND id::text <> ALL(:pre)"),
                        {"g": nao_admin, "pre": pre_list})).scalar() or 0)
                assert vaz == 0, f"vazou financeiro p/ não-admin: {vaz}"
                # (b) POSITIVA GERAL: TODA notif proativa criada foi p/ user cujo role
                #     está em roles_destino da SUA família (nunca do achado/LLM).
                fam_roles = {r.familia: r.roles_destino for r in REGISTRY.values()}
                linhas = (await db.execute(text(
                    "SELECT extra_data->>'familia' AS fam, user_id::text AS uid "
                    "FROM communication_notifications "
                    "WHERE extra_data->>'origem'='proativo' AND id::text <> ALL(:pre)"),
                    {"pre": pre_list})).mappings().all()
                for ln in linhas:
                    esperados = set(await resolver_usuarios_por_roles(
                        db, fam_roles.get(ln["fam"], ())))
                    assert ln["uid"] in esperados, \
                        f"destinatário {ln['uid']} fora dos roles da família {ln['fam']}"
                # (c) operacional (se houver): alcança admin/gestores, não os demais
                op_dest = set((await db.execute(text(
                    "SELECT user_id::text FROM communication_notifications "
                    "WHERE extra_data->>'origem'='proativo' "
                    "AND extra_data->>'familia'='operacional' AND id::text <> ALL(:pre)"),
                    {"pre": pre_list})).scalars().all())
                permitido_op = set(admins) | set(gerentes) | set(supervisores)
                assert op_dest.issubset(permitido_op), \
                    f"operacional fora de admin+gestores: {op_dest - permitido_op}"
                record(2, "RBAC financeiro só admin (negativa) + destino por role",
                       True, f"0 vazamento; {len(linhas)} notif(s) roteadas por role; "
                              f"op={len(op_dest)}")
            except Exception as exc:
                record(2, "RBAC financeiro só admin (negativa) + destino por role",
                       False, f"{type(exc).__name__}: {exc}")

            # ══════════════ ORÁCULO 3 — DEDUP + ISOLAMENTO POR REGRA ══════════
            try:
                assert avaliar_ok and r1 is not None and r2 is not None, "setup _avaliar falhou"
                # (a) dedup: 2ª rodada 0 novos; persistentes cobrem os novos da 1ª
                assert r2["novos"] == 0, f"2ª rodada gerou novos: {r2}"
                assert r2["persistentes"] >= r1["novos"], (r1, r2)
                # (b) isolamento: 1 regra estoura → OUTRA segue, e os alertas da que
                #     falhou NÃO são resolvidos. REGISTRY controlado (só sintético).
                boom_cid = f"t3_boom:{MARK}"
                ok_cid = f"t3_ok:{MARK}"
                orig = dict(REGISTRY)
                try:
                    for cid, rg in ((boom_cid, "t3_boom"), (ok_cid, "t3_ok")):
                        await db.execute(text(
                            "INSERT INTO proativo_alert_state "
                            "(correlation_id, regra, severidade, title, body, "
                            " destinatarios, first_seen_at, last_seen_at, resolved_at, "
                            " notified_individually) VALUES (:c, :r, 'info', 't', 'b', "
                            " '[]'::jsonb, now(), now(), NULL, true)"),
                            {"c": cid, "r": rg})
                    await db.commit()

                    async def _boom(_db):
                        raise RuntimeError("t3 falha forçada")

                    async def _empty(_db):
                        return []

                    REGISTRY.clear()
                    REGISTRY["t3_boom"] = Regra(
                        nome="t3_boom", familia="t3", severidade="info",
                        roles_destino=("admin",), action_url="/",
                        detectar=_boom, template=lambda d: ("t", "b"))
                    REGISTRY["t3_ok"] = Regra(
                        nome="t3_ok", familia="t3", severidade="info",
                        roles_destino=("admin",), action_url="/",
                        detectar=_empty, template=lambda d: ("t", "b"))
                    res3 = await _avaliar(db)
                    boom_ativo = (await db.execute(text(
                        "SELECT resolved_at IS NULL FROM proativo_alert_state "
                        "WHERE correlation_id=:c"), {"c": boom_cid})).scalar()
                    ok_resolvido = (await db.execute(text(
                        "SELECT resolved_at IS NOT NULL FROM proativo_alert_state "
                        "WHERE correlation_id=:c"), {"c": ok_cid})).scalar()
                    assert boom_ativo is True, \
                        "alerta da regra que FALHOU foi resolvido (isolamento quebrado)"
                    assert ok_resolvido is True, \
                        "regra seguinte não rodou (loop parou na exceção)"
                    assert res3["resolvidos"] >= 1, res3
                finally:
                    REGISTRY.clear()
                    REGISTRY.update(orig)
                    await db.execute(text(
                        "DELETE FROM proativo_alert_state WHERE correlation_id = ANY(:c)"),
                        {"c": [boom_cid, ok_cid]})
                    await db.commit()
                record(3, "dedup 2ª rodada 0 novos + isolamento por regra", True,
                       f"novos2={r2['novos']} persist2={r2['persistentes']}; "
                       f"boom_ativo={boom_ativo} ok_resolvido={ok_resolvido}")
            except Exception as exc:
                await db.rollback()
                record(3, "dedup 2ª rodada 0 novos + isolamento por regra", False,
                       f"{type(exc).__name__}: {exc}")

            # ══════════════ ORÁCULO 4 — DIGEST consolidado + RBAC + dedup diário ══
            try:
                hoje = datetime.now(ZoneInfo("America/Manaus")).strftime("%Y-%m-%d")
                assert admins, "esperado >=1 admin p/ o teste de digest"
                assert set(gerentes).isdisjoint(set(admins)), \
                    "admin e gerente_operacional devem ser disjuntos p/ o RBAC valer"
                # marcadores: 2 financeiro (admin) + 1 operacional (admin+gerente)
                dgt_c1 = f"caixa_baixo:{MARK}_DGT1:2026-07"     # financeiro
                dgt_c2 = f"certidao:{MARK}_DGT2:2026-12-31"     # documentos (admin)
                dgt_c3 = f"posto_descoberto:{MARK}_DGT3"        # operacional
                t1, t2, t3 = ("[TESTE] Caixa baixo DGT1", "[TESTE] Certidão DGT2",
                              "[TESTE] Posto DGT3")
                await estado.transicionar(db, correlation_id=dgt_c1, regra="caixa_baixo_cnpj",
                                          severidade="critico", title=t1, body="b",
                                          destinatarios=admins)
                await estado.transicionar(db, correlation_id=dgt_c2, regra="certidao_vencendo",
                                          severidade="atencao", title=t2, body="b",
                                          destinatarios=admins)
                await estado.transicionar(db, correlation_id=dgt_c3, regra="posto_descoberto",
                                          severidade="critico", title=t3, body="b",
                                          destinatarios=admins + gerentes)
                await db.commit()

                async def _corpos_novos(uid: str) -> list[str]:
                    return list((await db.execute(text(
                        "SELECT body FROM communication_notifications "
                        "WHERE user_id=:u AND extra_data->>'origem'='proativo_digest' "
                        "AND id::text <> ALL(:pre)"),
                        {"u": uid, "pre": pre_list})).scalars().all())

                # dedup diário depende de já existir digest:uid:hoje. Snapshot da
                # pré-existência (digest real das 07h) ANTES de _digest → oráculo
                # determinístico nos 2 mundos.
                async def _tem_digest_hoje(uid: str) -> bool:
                    return (await db.execute(text(
                        "SELECT 1 FROM communication_notifications WHERE user_id=:u "
                        "AND extra_data->>'correlation_id'=:c LIMIT 1"),
                        {"u": uid, "c": f"digest:{uid}:{hoje}"})).first() is not None

                admin0 = admins[0]
                ger0 = gerentes[0] if gerentes else None
                admin0_prehad = await _tem_digest_hoje(admin0)
                ger0_prehad = (await _tem_digest_hoje(ger0)) if ger0 else True
                dg = await _digest(db)

                if not admin0_prehad:
                    # caminho de criação: 1 notif ÚNICA consolidando as 3 condições
                    corpos_admin = await _corpos_novos(admin0)
                    assert len(corpos_admin) == 1, \
                        f"digest do admin deveria ser 1 notif única, veio {len(corpos_admin)}"
                    assert all(m in corpos_admin[0] for m in (t1, t2, t3)), \
                        f"digest do admin deveria consolidar as 3: {corpos_admin[0]!r}"
                    # RBAC: gestor vê SÓ operacional, nunca financeiro/documentos
                    if ger0 and not ger0_prehad:
                        corpos_ger = await _corpos_novos(ger0)
                        assert len(corpos_ger) == 1, \
                            f"digest do gestor deveria ser 1 notif, veio {len(corpos_ger)}"
                        assert t3 in corpos_ger[0], "gestor deveria ver o item operacional"
                        assert t1 not in corpos_ger[0] and t2 not in corpos_ger[0], \
                            f"RBAC vazou financeiro/doc pro gestor: {corpos_ger[0]!r}"
                    # funcionário sem persistente seu → 0 digest
                    if funcionarios:
                        corpos_func = await _corpos_novos(funcionarios[0])
                        assert corpos_func == [], \
                            f"funcionario sem persistente recebeu digest: {corpos_func}"
                    # dedup diário: 2ª chamada não cria novo
                    dg2 = await _digest(db)
                    assert dg2["notificacoes"] == 0, f"2ª chamada duplicou: {dg2}"
                    corpos_admin2 = await _corpos_novos(admin0)
                    assert len(corpos_admin2) == 1, \
                        f"digest do admin duplicou na 2ª rodada: {len(corpos_admin2)}"
                    record(4, "digest 1 consolidado/destinatário + RBAC + dedup diário",
                           True, f"admin=1 (3 itens); gestor sem financeiro; func=0; "
                                 f"2ª rodada 0 novos ({dg})")
                else:
                    # digest real das 07h já existia → prova o DEDUP diário direto:
                    # _digest não cria 2º p/ o admin (correlation_id determinístico).
                    corpos_admin = await _corpos_novos(admin0)
                    assert corpos_admin == [], \
                        f"dedup diário falhou: digest duplicado p/ admin: {corpos_admin}"
                    record(4, "digest dedup diário (digest real das 07h já existia)",
                           True, f"admin já tinha digest hoje → 0 novo (dedup ok); {dg}")
            except Exception as exc:
                await db.rollback()
                record(4, "digest 1 consolidado/destinatário + RBAC + dedup diário",
                       False, f"{type(exc).__name__}: {exc}")

            # ══════════════ ORÁCULO 5 — GROUNDEDNESS (número == query) ══════════
            try:
                from modules.notifications.proativo.regras import Achado
                regra = REGISTRY["posto_descoberto"]
                # (a) número do template == número dos dados (da query)
                achado = Achado(correlation_id="posto_descoberto:__ORC5__",
                                dados={"post_id": "x", "posto": "Portaria Central",
                                       "faltam": 2, "req": 3, "cur": 1})
                _t, body_tpl = regra.template(achado.dados)
                assert str(achado.dados["faltam"]) in body_tpl, \
                    f"número da query ausente no template: {body_tpl!r}"
                # se há posto descoberto REAL, o número vem da fonte viva
                reais = await regra.detectar(db)
                if reais:
                    _tt, bb = regra.template(reais[0].dados)
                    assert str(reais[0].dados["faltam"]) in bb, \
                        f"número real ({reais[0].dados['faltam']}) ausente: {bb!r}"

                # (b) fabricação barrada: LLM inventa "40%" extra → REJEITADO → template
                regra_caixa = REGISTRY["caixa_baixo_cnpj"]
                achado_caixa = Achado(
                    correlation_id="caixa_baixo:__ORC5__:2026-07",
                    dados={"cnpj": "CONECTA ELETRONICA", "banco": "Banco Inter",
                           "saldo": 242073.20, "limiar": 10000.0, "usou_fallback": True})
                _tc, body_caixa_tpl = regra_caixa.template(achado_caixa.dados)

                async def gerar_fabricado(**_kw):
                    return ("O caixa da CONECTA ELETRONICA está em R$ 242.073,20, 40% "
                            "abaixo do limiar de R$ 10.000,00.", {})
                _, body_fab = await _redigir_real(regra_caixa, achado_caixa,
                                                  gerar_fn=gerar_fabricado)
                assert body_fab == body_caixa_tpl, \
                    f"fabricação NÃO barrada — LLM inventou número: {body_fab!r}"

                # (c) omissão barrada: LLM esquece o limiar → REJEITADO → template
                async def gerar_omisso(**_kw):
                    return ("O caixa da CONECTA ELETRONICA está baixo, R$ 242.073,20.", {})
                _, body_om = await _redigir_real(regra_caixa, achado_caixa,
                                                 gerar_fn=gerar_omisso)
                assert body_om == body_caixa_tpl, f"omissão NÃO barrada: {body_om!r}"

                # (d) conjunto exato → ACEITO (o número do LLM == números da query)
                async def gerar_ok(**_kw):
                    return ("O caixa da CONECTA ELETRONICA está em R$ 242.073,20, "
                            "abaixo do piso de R$ 10.000,00.", {})
                _, body_ok = await _redigir_real(regra_caixa, achado_caixa,
                                                 gerar_fn=gerar_ok)
                assert body_ok != body_caixa_tpl and "242.073,20" in body_ok, \
                    "conjunto exato deveria ser aceito"
                record(5, "groundedness: número==query; fabricação/omissão barradas",
                       True, "template grounded; +40% rejeitado; omissão rejeitada; "
                             "conjunto-exato aceito")
            except Exception as exc:
                record(5, "groundedness: número==query; fabricação/omissão barradas",
                       False, f"{type(exc).__name__}: {exc}")

            # ══════════════ MUTAÇÃO-TESTE — o gate MORDE? ══════════════
            # Injeta um vazamento RBAC sintético (notif financeira p/ um não-admin) e
            # prova que a query negativa do oráculo 2 o PEGA (>0). Sem isso, o oráculo
            # 2 poderia estar vacuamente verde. Limpa por id no finally.
            mut_id = None
            try:
                alvo = (gerentes or funcionarios or [None])[0]
                if alvo is None:
                    record(0, "MUTAÇÃO-TESTE RBAC (gate morde)", True,
                           "sem não-admin no banco p/ injetar — pulado")
                else:
                    extra = json.dumps({"correlation_id": f"MUT:{MARK}", "familia": "financeiro",
                                        "severidade": "critico", "origem": "proativo"})
                    mut_id = (await db.execute(text(
                        "INSERT INTO communication_notifications "
                        "(id, tenant_id, user_id, title, body, type, reference_type, "
                        " reference_id, action_url, extra_data, is_active, sent_at, created_at) "
                        "VALUES (gen_random_uuid(), :u, :u, '[MUT] vazamento', 'x', 'alerta', "
                        " 'proativo', NULL, '/x', CAST(:e AS jsonb), true, "
                        " (now() AT TIME ZONE 'America/Manaus'), (now() AT TIME ZONE 'America/Manaus')) "
                        "RETURNING id::text"), {"u": alvo, "e": extra})).scalar()
                    await db.commit()
                    vaz_mut = int((await db.execute(text(
                        "SELECT count(*) FROM communication_notifications "
                        "WHERE user_id = :u AND extra_data->>'origem'='proativo' "
                        "AND extra_data->>'familia'='financeiro' "
                        "AND id::text <> ALL(:pre)"),
                        {"u": alvo, "pre": pre_list})).scalar() or 0)
                    # o oráculo 2 usa exatamente esta query negativa → vaz_mut>0 = PEGOU
                    assert vaz_mut >= 1, "mutação não foi detectada — oráculo 2 é vacuoso!"
                    record(0, "MUTAÇÃO-TESTE RBAC (gate morde)", True,
                           f"vazamento injetado detectado pela query negativa (vaz={vaz_mut})")
            except Exception as exc:
                await db.rollback()
                record(0, "MUTAÇÃO-TESTE RBAC (gate morde)", False,
                       f"{type(exc).__name__}: {exc}")
            finally:
                if mut_id:
                    await db.execute(text(
                        "DELETE FROM communication_notifications WHERE id::text = :i"),
                        {"i": mut_id})
                    await db.commit()

        finally:
            # ══════ PROVA 7 / LIMPEZA — 0 remanescentes (diff pre/pós por id) ══════
            redator.redigir = _orig_redigir  # type: ignore[assignment]
            await db.rollback()  # garante sessão limpa antes do delete
            await db.execute(text(
                "DELETE FROM communication_notifications "
                "WHERE extra_data->>'origem' IN ('proativo','proativo_digest') "
                "AND id::text <> ALL(:pre)"), {"pre": pre_list})
            await db.execute(text(
                "DELETE FROM proativo_alert_state WHERE correlation_id <> ALL(:pre)"),
                {"pre": pre_state_list})
            # varredura extra pelos marcadores sintéticos (dupla garantia)
            await db.execute(text(
                "DELETE FROM proativo_alert_state WHERE correlation_id LIKE :m"),
                {"m": f"%{MARK}%"})
            await db.execute(text(
                "DELETE FROM communication_notifications "
                "WHERE extra_data->>'correlation_id' LIKE :m"), {"m": f"%{MARK}%"})
            await db.commit()
            rem_n = int((await db.execute(text(
                "SELECT count(*) FROM communication_notifications "
                "WHERE extra_data->>'origem' IN ('proativo','proativo_digest') "
                "AND id::text <> ALL(:pre)"), {"pre": pre_list})).scalar() or 0)
            rem_s = int((await db.execute(text(
                "SELECT count(*) FROM proativo_alert_state WHERE correlation_id <> ALL(:pre)"),
                {"pre": pre_state_list})).scalar() or 0)
            limpeza_ok = (rem_n == 0 and rem_s == 0)
            record(7, "limpeza: 0 remanescentes do que a suite criou (diff pre/pós)",
                   limpeza_ok, f"remanescentes notif={rem_n} state={rem_s}")

    # ══════════════ RESUMO ══════════════
    core_oráculos = [r for r in results if r[0] in (1, 2, 3, 4, 5, 6, 7)]
    falhas = [r for r in results if not r[2]]
    passed = sum(1 for r in core_oráculos if r[2])
    total = len(core_oráculos)
    print("\n" + "═" * 64)
    print(f"RESUMO: {passed}/{total} oráculos-núcleo PASS"
          + (f"  |  MUTAÇÃO-TESTE {'PASS' if all(r[2] for r in results if r[0]==0) else 'FAIL'}"
             if any(r[0] == 0 for r in results) else ""))
    if falhas:
        print("FALHAS (findings — NÃO ajustar o teste, é o gate mordendo):")
        for n, desc, _ok, det in falhas:
            print(f"  ✗ ORACULO {n} {desc} — {det}")
        print("═" * 64)
        print("GATE: BLOQUEADO — deploy (T9) NÃO autorizado.")
        return 1
    print("═" * 64)
    print(f"OK oráculo proativo ({passed}/{total}) — GATE LIBERADO p/ T9.")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        traceback.print_exc()
        code = 2
    raise SystemExit(code)
