# Fluxo Comercial Completo do Bartolo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar o ciclo comercial no chat — campo → orçamento → proposta → envio → cadência → fechamento — ligando as 7 rotas já montadas que não têm porta, sem afrouxar nenhuma parede.

**Architecture:** Cada capacidade entra como handler in-process que chama a COROUTINE do controller real, com a identidade de quem pergunta. Leitura vai por `registrar_read`; ação vai por `registrar_acao` + `criar_rascunho` (propor→aprovar) + `registrar_executor`. Nada de HTTP entre camadas, nada de conta de serviço.

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy async (asyncpg) · Postgres · registro `ToolDef`/`registrar_read`/`registrar_acao` do orquestrador.

## Global Constraints

Estas valem para TODAS as tasks. Um requisito violado aqui reprova a task inteira.

- **Propor→aprovar**: nenhuma ação executa direto. `criar_rascunho(...)` grava em `agent_drafts` inerte; o executor registrado roda com a identidade de QUEM APROVOU, nunca de quem propôs.
- **Grau fail-closed**: toda ação nova precisa entrar EXPLICITAMENTE em `_AMARELAS` (`backend/modules/ai/conversation/controllers/agente_aprovacao_controller.py`) com comentário datado justificando. Sem declaração, `grau_de()` devolve 🔴+OTP — e é assim que tem de ser.
- **Área na Central**: toda ação nova precisa de linha em `_AREA_DRAFT` (`backend/modules/operacional/controllers/redesign_builders/aprovacoes.py`), senão a tela rotula errado.
- **Canal fail-closed**: `ToolDef` nasce `canais=("interno",)`. Nada deste plano vai para o canal público — o interlocutor do canal público é um cliente identificado por telefone.
- **Dinheiro que SAI = OTP humano**, sempre. Nenhuma task deste plano move dinheiro; se alguma passar a mover, para e escala.
- **Nunca fabricar**: preço vem do catálogo ou de valor informado pela pessoa. Vazio real é dito como vazio, nunca como zero.
- **EXTERNO (sai da empresa)**: enviar ao cliente é 🟡 com resumo que nomeia o DESTINATÁRIO. O aprovador precisa ver para quem vai antes de clicar.
- **`::` é proibido dentro de `text()`**: use `cast(x AS t)`. Bind nu comparado a NULL ou dentro de `concat` também precisa de cast — mordeu 5 vezes em 27/08/2026.
- **Commits**: `git commit --no-verify -m "..." -- <arquivos>` com pathspec. Arquivo NOVO precisa de `git add <arquivo>` explícito antes. NUNCA `git add .` (índice compartilhado entre sessões).
- **Todo oráculo tem de ser PROVADO VERMELHO** por mutação antes de valer: quebre a guarda, veja o oráculo acusar, restaure e confira que o arquivo voltou idêntico.
- **Rodar dentro do container**: `docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/<x>.py`. Levar o arquivo com `docker cp` antes.

---

## File Structure

| arquivo | responsabilidade |
|---|---|
| `backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py` | **modificar** — 4 ações novas (mover estágio, enviar proposta WhatsApp, cadastrar WhatsApp, follow-up em lote) + executores |
| `backend/modules/ai/conversation/services/orquestrador/tools_read_crm.py` | **modificar** — 1 leitura nova (`sequencias_inscricoes`) |
| `backend/modules/ai/conversation/services/orquestrador/tools_comercial_doc.py` | **modificar** — 1 ToolDef nova (`gerar_apresentacao_doc`) |
| `backend/modules/ai/conversation/controllers/agente_aprovacao_controller.py` | **modificar** — declarar o grau das 4 ações novas |
| `backend/modules/operacional/controllers/redesign_builders/aprovacoes.py` | **modificar** — área CRM das 4 ações novas |
| `backend/scripts/orq/test_acao_funil_crm.py` | **criar** — oráculo das ações de funil (estágio, lote, opt-out) |
| `backend/scripts/orq/test_acao_envio_cliente.py` | **criar** — oráculo do que SAI da empresa (proposta por WhatsApp, cadastro de número) |

---

## Task 1: Mover deal de estágio no funil

Hoje o Bartolo só sabe `marcar_deal_perdido` — um assessor que só registra derrota. 46 deals estão empilhados em `proposal` há 24 dias em média, somando R$ 596.881.

**Files:**
- Modify: `backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py` (fim do arquivo)
- Modify: `backend/modules/ai/conversation/controllers/agente_aprovacao_controller.py` (`_AMARELAS`)
- Modify: `backend/modules/operacional/controllers/redesign_builders/aprovacoes.py` (`_AREA_DRAFT`)
- Test: `backend/scripts/orq/test_acao_funil_crm.py`

**Interfaces:**
- Consumes: `criar_rascunho`, `registrar_executor`, `registrar_acao`, `ROLES_COMERCIAL`, `text` (todos já importados no topo de `tools_acao_crm.py`); `_slug` (helper local do mesmo arquivo).
- Produces: `_propor_mover_estagio_deal(db, user, scope, *, deal=None, estagio=None, motivo=None, **_) -> dict` e `_exec_mover_estagio_deal(db, aprovador_user, payload: dict) -> str`. Tipo do rascunho: `"mover_estagio_deal"`.

- [ ] **Step 1: Escrever o oráculo que falha**

Criar `backend/scripts/orq/test_acao_funil_crm.py`:

```python
#!/usr/bin/env python3
"""Oráculo das ações de FUNIL — mover estágio de deal.

46 deals estavam parados em `proposal` há 24 dias (R$ 596.881) porque o Bartolo lia o
funil e não o movia: só sabia `marcar_deal_perdido`.

⭐ O que este oráculo protege: mover para `closed_won` é FECHAR VENDA — vira MRR e
contrato. Isso não pode acontecer por uma frase no chat. As demais etapas são
movimentação de funil e cabem em propor→aprovar.

Quatro invariantes:
  1. deal inexistente é RECUSADO
  2. estágio inválido é RECUSADO (o LLM inventa nome de estágio)
  3. `closed_won` é RECUSADO nesta ação (fechar tem porta própria, com decisão do dono)
  4. INÉRCIA: o caso válido vira rascunho e o `stage` do deal NÃO muda

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/test_acao_funil_crm.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

_MARCA = "ZZteste-oraculo-funil"


async def _limpar(db) -> None:
    from sqlalchemy import text as _t

    ids = (await db.execute(_t(
        "SELECT id FROM agent_drafts WHERE payload::text LIKE :m"),
        {"m": f"%{_MARCA}%"})).scalars().all()
    if ids:
        await db.execute(_t(
            "DELETE FROM communication_notifications WHERE reference_id::text = ANY(:i)"),
            {"i": [str(x) for x in ids]})
        await db.execute(_t("DELETE FROM agent_drafts WHERE id = ANY(:i)"), {"i": ids})
    await db.commit()


async def main() -> int:
    from sqlalchemy import select, text

    from core.database import async_session_factory
    from core.models.user import User
    import modules.ai.conversation.controllers.consultor_escopado_controller as C
    from modules.ai.conversation.controllers.agente_aprovacao_controller import grau_de
    from modules.ai.conversation.services.orquestrador.agir_dispatcher import _ACOES
    from modules.ai.conversation.services.orquestrador.tools_acao_crm import (
        _propor_mover_estagio_deal as P,
    )

    falhas: list[str] = []
    async with async_session_factory() as db:
        await _limpar(db)

        if "mover_estagio_deal" not in _ACOES.get("crm", {}):
            print("FALHOU: `mover_estagio_deal` não está registrada em agir_crm")
            return 1
        if grau_de("mover_estagio_deal")[0] not in ("🟡", "🔴"):
            falhas.append("grau 🔵 — mover deal muda previsão de receita")

        u = (await db.execute(select(User).where(
            User.email == "jjesus@conectamais.pro"))).scalar_one()
        scope, _ = await C._resolver_tier_e_tools(db, u)

        deal = (await db.execute(text(
            "SELECT title, stage::text FROM opportunities "
            "WHERE stage::text NOT IN ('closed_won', 'closed_lost') LIMIT 1"))).first()
        if not deal:
            print("FALHOU (pré-condição): nenhum deal aberto na base")
            return 1
        titulo, estagio_antes = deal[0], deal[1]

        r = await P(db, u, scope, deal="ZZ_NAO_EXISTE", estagio="negotiation")
        if not r.get("erro"):
            falhas.append("deal inexistente foi aceito")

        r = await P(db, u, scope, deal=titulo, estagio="estagio_inventado")
        if not r.get("erro"):
            falhas.append("estágio inválido foi aceito")

        r = await P(db, u, scope, deal=titulo, estagio="closed_won")
        if not r.get("erro"):
            falhas.append("closed_won foi aceito — FECHAR VENDA não passa por aqui")

        # ⚠️ O estágio ALVO tem de ser diferente do atual: a ação recusa "mover para onde
        # já está", e a 1ª versão deste oráculo sorteava um deal que já estava em
        # `negotiation` — reprovava o código por defeito do teste.
        destino = "qualification" if estagio_antes == "negotiation" else "negotiation"
        r = await P(db, u, scope, deal=titulo, estagio=destino, motivo=_MARCA)
        if not (r.get("draft_id") or r.get("id")):
            falhas.append(f"caso válido não virou rascunho: {str(r)[:110]}")
        depois = (await db.execute(text(
            "SELECT stage::text FROM opportunities WHERE title = :t"),
            {"t": titulo})).scalar()
        if depois != estagio_antes:
            falhas.append(f"A PROPOSTA MOVEU o deal: {estagio_antes!r} → {depois!r}")

        await _limpar(db)

    if falhas:
        for f in falhas:
            print(f"FALHOU: {f}")
        return 1
    print("OK acao_funil_crm: 4/4 — recusa deal inexistente, estágio inválido e "
          "closed_won; o válido vira rascunho e o deal NÃO se move.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Step 2: Rodar e confirmar que FALHA**

```bash
cd /opt/conecta-pro
docker cp backend/scripts/orq/test_acao_funil_crm.py \
  conecta-pro-backend:/app/scripts/orq/test_acao_funil_crm.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_acao_funil_crm.py
```
Esperado: `ImportError: cannot import name '_propor_mover_estagio_deal'` (a função ainda não existe).

- [ ] **Step 3: Implementar a ação**

Acrescentar ao FIM de `backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py`:

```python


# ── MOVER DEAL DE ESTÁGIO ──────────────────────────────────────────────────────────────
# 27/08/2026: 46 deals empilhados em `proposal` há 24 dias, R$ 596.881. O Bartolo lia o
# funil e não o movia — só sabia `marcar_deal_perdido`, um assessor que só registra derrota.
#
# ⭐ `closed_won` NÃO passa por aqui. Fechar venda vira MRR e contrato; é decisão do dono,
# com a porta própria (`POST /opportunities/{id}/close`). Uma frase no chat não fecha venda.

_ESTAGIOS_PERMITIDOS = frozenset({
    "prospecting", "qualification", "proposal", "negotiation",
})
#: Fora desta lista, recusa. `closed_won`/`closed_lost` são nomeados para a mensagem de
#: recusa poder EXPLICAR, em vez de dizer só "inválido".
_ESTAGIOS_FECHAMENTO = frozenset({"closed_won", "closed_lost"})


async def _propor_mover_estagio_deal(db, user, scope, *, deal=None, estagio=None,
                                     motivo=None, **_) -> dict[str, Any]:
    ref = str(deal or "").strip()
    novo = str(estagio or "").strip().lower()
    if not ref:
        return {"erro": "informe o deal (título ou id)"}
    if novo in _ESTAGIOS_FECHAMENTO:
        return {"erro": f"'{novo}' é FECHAMENTO e não passa por aqui: ganhar vira MRR e "
                        f"contrato, e perder tem `marcar_deal_perdido` com motivo. "
                        f"Mova só dentro do funil aberto."}
    if novo not in _ESTAGIOS_PERMITIDOS:
        return {"erro": f"estágio {novo!r} não existe. Use um de: "
                        f"{', '.join(sorted(_ESTAGIOS_PERMITIDOS))}."}

    row = (await db.execute(text(
        "SELECT id::text AS id, title, stage::text AS stage, "
        "       coalesce(value, 0) AS value "
        "FROM opportunities "
        "WHERE id::text = :r OR upper(title) = upper(:r) "
        "ORDER BY (upper(title) = upper(:r)) DESC LIMIT 1"),
        {"r": ref})).mappings().first()
    if not row:
        return {"erro": f"deal {ref!r} não existe no funil — não crio deal de passagem."}
    if row["stage"] == novo:
        return {"erro": f"o deal '{row['title'][:40]}' JÁ está em {novo}."}

    valor = float(row["value"] or 0)
    return await criar_rascunho(
        db, user, tipo="mover_estagio_deal", modulo="crm",
        gate="🟡", requires_otp=False, roles_aprovador=ROLES_COMERCIAL,
        idempotency_key=f"deal_estagio:{_slug(row['title'])}:{novo}",
        titulo=f"MOVER deal para {novo} — {row['title'][:38]}",
        resumo=(f"Aprovar move o deal '{row['title'][:50]}' "
                f"(R$ {valor:,.2f}) de {row['stage']} para {novo}. "
                f"{('Motivo: ' + str(motivo)[:120] + '. ') if motivo else ''}"
                f"Isso muda o funil e a previsão de receita."),
        payload={"opportunity_id": row["id"], "title": row["title"],
                 "de": row["stage"], "para": novo, "motivo": (motivo or None)},
    )


async def _exec_mover_estagio_deal(db, aprovador_user, payload: dict) -> str:
    from modules.crm.controllers.opportunity_controller import update_opportunity_stage
    from modules.crm.schemas.opportunity import OpportunityStageUpdate

    o = await update_opportunity_stage(
        opportunity_id=str(payload["opportunity_id"]),
        data=OpportunityStageUpdate(stage=payload["para"],
                                    notes=(payload.get("motivo") or None)),
        current_user=aprovador_user, db=db)
    return str(getattr(o, "id", payload["opportunity_id"]))


registrar_executor("mover_estagio_deal", _exec_mover_estagio_deal)

registrar_acao("crm", "mover_estagio_deal",
               "MOVER um deal de estágio no funil. dados: deal (título ou id), estagio "
               "(prospecting | qualification | proposal | negotiation), motivo. "
               "FECHAR (ganho/perdido) NÃO passa por aqui. Nasce rascunho.",
               _propor_mover_estagio_deal)
```

- [ ] **Step 4: Declarar o grau e a área**

Em `backend/modules/ai/conversation/controllers/agente_aprovacao_controller.py`, dentro de `_AMARELAS`, antes do `}` final:

```python
    # `mover_estagio_deal` (27/08/2026): muda o FUNIL e a previsão de receita, por isso
    # passou pela pergunta em vez de nascer 🔵. É 🟡 e não 🔴 porque não sai da empresa,
    # não move dinheiro e é reversível — e porque FECHAR venda foi deliberadamente
    # deixado FORA desta ação.
    "mover_estagio_deal",
```

Em `backend/modules/operacional/controllers/redesign_builders/aprovacoes.py`, na linha que já lista as ações de CRM, acrescentar:

```python
    "mover_estagio_deal": "CRM",
```

- [ ] **Step 5: Rodar o oráculo e confirmar 4/4**

```bash
cd /opt/conecta-pro
for f in modules/ai/conversation/services/orquestrador/tools_acao_crm.py \
         modules/ai/conversation/controllers/agente_aprovacao_controller.py \
         modules/operacional/controllers/redesign_builders/aprovacoes.py; do
  docker cp backend/$f conecta-pro-backend:/app/$f
done
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_acao_funil_crm.py; echo "exit=$?"
```
Esperado: `OK acao_funil_crm: 4/4 ...` e `exit=0`.

- [ ] **Step 6: Provar o oráculo VERMELHO por mutação**

```bash
cd /opt/conecta-pro
cp backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py /tmp/ok.py
python3 - <<'EOF'
p='/opt/conecta-pro/backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py'
s=open(p).read()
a='''    if novo in _ESTAGIOS_FECHAMENTO:'''
assert a in s
open(p,'w').write(s.replace(a,'''    if False:  # MUTAÇÃO: deixa closed_won passar'''))
EOF
docker cp backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py \
  conecta-pro-backend:/app/modules/ai/conversation/services/orquestrador/tools_acao_crm.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_acao_funil_crm.py
cp /tmp/ok.py backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py
docker cp backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py \
  conecta-pro-backend:/app/modules/ai/conversation/services/orquestrador/tools_acao_crm.py
diff -q /tmp/ok.py backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py
```
Esperado no mutado: `FALHOU: closed_won foi aceito — FECHAR VENDA não passa por aqui`.
Esperado no `diff`: sem saída (arquivo idêntico ao original).

- [ ] **Step 7: Commit**

```bash
cd /opt/conecta-pro
git add backend/scripts/orq/test_acao_funil_crm.py
git commit --no-verify -m "feat(crm): mover deal de estagio no funil (propor->aprovar)

46 deals empilhados em 'proposal' ha 24 dias, R\$ 596.881: o Bartolo lia o
funil e nao o movia. closed_won NAO passa por aqui — fechar vira MRR e
contrato, e e decisao do dono.

test_acao_funil_crm 4/4, provado vermelho por mutacao.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" \
  -- backend/scripts/orq/test_acao_funil_crm.py \
     backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py \
     backend/modules/ai/conversation/controllers/agente_aprovacao_controller.py \
     backend/modules/operacional/controllers/redesign_builders/aprovacoes.py
```

---

## Task 2: Enviar proposta pelo WhatsApp + cadastrar o número do cliente

10 propostas foram enviadas e estão sem resposta há 64 dias em média — todas por e-mail. WhatsApp é onde o cliente responde. A rota `POST /crm/proposals/{id}/send-whatsapp` já manda PDF + link de assinatura e rastreia em `crm_followups`; ela tem `confirmar=False` como preview.

**Files:**
- Modify: `backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py` (fim do arquivo)
- Modify: `backend/modules/ai/conversation/controllers/agente_aprovacao_controller.py` (`_AMARELAS`)
- Modify: `backend/modules/operacional/controllers/redesign_builders/aprovacoes.py` (`_AREA_DRAFT`)
- Test: `backend/scripts/orq/test_acao_envio_cliente.py`

**Interfaces:**
- Consumes: `criar_rascunho`, `registrar_executor`, `registrar_acao`, `ROLES_MONEY`, `text`, `_slug`.
- Produces: `_propor_enviar_proposta_whatsapp(db, user, scope, *, proposta=None, **_) -> dict`, `_exec_enviar_proposta_whatsapp(db, aprovador_user, payload) -> str`, `_propor_cadastrar_whatsapp(db, user, scope, *, cliente=None, numero=None, **_) -> dict`, `_exec_cadastrar_whatsapp(db, aprovador_user, payload) -> str`. Tipos: `"enviar_proposta_whatsapp"`, `"cadastrar_whatsapp"`.

- [ ] **Step 1: Escrever o oráculo que falha**

Criar `backend/scripts/orq/test_acao_envio_cliente.py`:

```python
#!/usr/bin/env python3
"""Oráculo do que SAI DA EMPRESA — proposta por WhatsApp e cadastro de número.

10 propostas estavam sem resposta há 64 dias, todas enviadas por e-mail. WhatsApp é onde
o cliente responde.

⭐ O que este oráculo protege: envio é IRREVERSÍVEL e EXTERNO. Depois que a mensagem sai,
não há desfazer. Por isso o rascunho tem de NOMEAR O DESTINATÁRIO no resumo — quem aprova
precisa ver para quem vai antes de clicar — e a proposta precisa EXISTIR de verdade.

Cinco invariantes:
  1. proposta inexistente é RECUSADA
  2. cliente sem WhatsApp cadastrado é RECUSADO (não inventa número)
  3. o resumo do rascunho NOMEIA o destinatário
  4. INÉRCIA: propor NÃO envia (nada em crm_followups muda)
  5. número inválido no cadastro é RECUSADO

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/test_acao_envio_cliente.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

_MARCA = "ZZteste-oraculo-envio"


async def _limpar(db) -> None:
    from sqlalchemy import text as _t

    ids = (await db.execute(_t(
        "SELECT id FROM agent_drafts WHERE payload::text LIKE :m"),
        {"m": f"%{_MARCA}%"})).scalars().all()
    if ids:
        await db.execute(_t(
            "DELETE FROM communication_notifications WHERE reference_id::text = ANY(:i)"),
            {"i": [str(x) for x in ids]})
        await db.execute(_t("DELETE FROM agent_drafts WHERE id = ANY(:i)"), {"i": ids})
    await db.commit()


async def main() -> int:
    from sqlalchemy import select, text

    from core.database import async_session_factory
    from core.models.user import User
    import modules.ai.conversation.controllers.consultor_escopado_controller as C
    from modules.ai.conversation.services.orquestrador.agir_dispatcher import _ACOES
    from modules.ai.conversation.services.orquestrador.tools_acao_crm import (
        _propor_cadastrar_whatsapp as CAD,
        _propor_enviar_proposta_whatsapp as ENV,
    )

    falhas: list[str] = []
    async with async_session_factory() as db:
        await _limpar(db)

        for nome in ("enviar_proposta_whatsapp", "cadastrar_whatsapp"):
            if nome not in _ACOES.get("crm", {}):
                falhas.append(f"{nome} não está registrada em agir_crm")
        if falhas:
            for f in falhas:
                print(f"FALHOU: {f}")
            return 1

        u = (await db.execute(select(User).where(
            User.email == "jjesus@conectamais.pro"))).scalar_one()
        scope, _ = await C._resolver_tier_e_tools(db, u)

        # 1 · proposta inexistente
        r = await ENV(db, u, scope, proposta="PROP-ZZ-NAO-EXISTE")
        if not r.get("erro"):
            falhas.append("proposta inexistente foi aceita para envio")

        # 4 · inércia: contar follow-ups antes e depois
        n0 = (await db.execute(text("SELECT count(*) FROM crm_followups"))).scalar()

        prop = (await db.execute(text(
            "SELECT number FROM proposals ORDER BY created_at DESC LIMIT 1"))).scalar()
        if prop:
            r = await ENV(db, u, scope, proposta=prop)
            # 2 e 3: ou recusa por falta de número, ou nomeia o destinatário
            if r.get("erro"):
                if "whatsapp" not in str(r["erro"]).lower():
                    falhas.append(f"recusa sem explicar a falta de WhatsApp: {r['erro'][:80]}")
            else:
                d = (await db.execute(text(
                    "SELECT resumo, payload->>'numero' AS numero FROM agent_drafts "
                    "WHERE tipo = 'enviar_proposta_whatsapp' "
                    "ORDER BY created_at DESC LIMIT 1"))).mappings().first() or {}
                # ⚠️ "tem algum dígito" NÃO serve como prova: o valor em R$ já tem
                # dígitos, e a 1ª versão deste teste passava com o resumo sem telefone
                # nenhum. O invariante é o NÚMERO DE DESTINO aparecer no texto que quem
                # aprova lê.
                numero = str(d.get("numero") or "")
                if not numero.strip():
                    falhas.append("rascunho criado SEM número de destino no payload")
                elif numero not in str(d.get("resumo") or ""):
                    falhas.append(f"o resumo NÃO mostra o número de destino {numero!r} — "
                                  f"quem aprova não vê para quem vai")

        n1 = (await db.execute(text("SELECT count(*) FROM crm_followups"))).scalar()
        if n0 != n1:
            falhas.append(f"PROPOR JÁ ENVIOU: crm_followups {n0} → {n1}")

        # 5 · número inválido
        cli = (await db.execute(text("SELECT name FROM clients LIMIT 1"))).scalar()
        r = await CAD(db, u, scope, cliente=cli, numero="123")
        if not r.get("erro"):
            falhas.append("número inválido foi aceito no cadastro de WhatsApp")

        await _limpar(db)

    if falhas:
        for f in falhas:
            print(f"FALHOU: {f}")
        return 1
    print("OK acao_envio_cliente: 5/5 — recusa proposta inexistente e número inválido; "
          "o rascunho NOMEIA o destinatário; e propor NÃO envia.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Step 2: Rodar e confirmar que FALHA**

```bash
cd /opt/conecta-pro
docker cp backend/scripts/orq/test_acao_envio_cliente.py \
  conecta-pro-backend:/app/scripts/orq/test_acao_envio_cliente.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_acao_envio_cliente.py
```
Esperado: `ImportError: cannot import name '_propor_cadastrar_whatsapp'`.

- [ ] **Step 3: Implementar as duas ações**

Acrescentar ao FIM de `tools_acao_crm.py`:

```python


# ── ENVIAR PROPOSTA PELO WHATSAPP · CADASTRAR O NÚMERO DO CLIENTE ─────────────────────
# 27/08/2026: 10 propostas sem resposta há 64 dias em média, TODAS por e-mail. O WhatsApp
# é onde o cliente responde — e a rota já existia, mandando PDF + link de assinatura e
# rastreando em `crm_followups`.
#
# ⚠️ ENVIO É IRREVERSÍVEL E EXTERNO. Depois que sai, não há desfazer. Por isso o resumo
# NOMEIA o destinatário: quem aprova precisa ver para quem vai ANTES de clicar. É a mesma
# regra do `enviar_proposta` por e-mail, que já usa ROLES_MONEY pelo mesmo motivo — o
# risco aqui não é dinheiro, é a empresa falando com o cliente errado.

async def _propor_enviar_proposta_whatsapp(db, user, scope, *, proposta=None,
                                           **_) -> dict[str, Any]:
    ref = str(proposta or "").strip()
    if not ref:
        return {"erro": "informe a proposta (número ou id)"}

    row = (await db.execute(text(
        "SELECT p.id::text AS id, p.number, p.status::text AS status, "
        "       coalesce(p.total, 0) AS total, "
        "       coalesce(p.client_name, '') AS cliente, "
        "       coalesce(c.whatsapp, c.phone, '') AS numero "
        "FROM proposals p "
        "LEFT JOIN clients c ON upper(c.name) = upper(p.client_name) "
        "WHERE p.id::text = :r OR upper(p.number) = upper(:r) LIMIT 1"),
        {"r": ref})).mappings().first()
    if not row:
        return {"erro": f"proposta {ref!r} não existe."}
    if not str(row["numero"] or "").strip():
        return {"erro": f"o cliente '{row['cliente'][:40]}' não tem WhatsApp cadastrado. "
                        f"Cadastre com `cadastrar_whatsapp` — eu não invento número."}

    return await criar_rascunho(
        db, user, tipo="enviar_proposta_whatsapp", modulo="crm",
        gate="🟡", requires_otp=False, roles_aprovador=ROLES_MONEY,
        idempotency_key=f"prop_wa:{_slug(row['number'] or row['id'])}",
        titulo=f"ENVIAR proposta {row['number']} por WhatsApp",
        resumo=(f"⚠️ EXTERNO: aprovar ENVIA a proposta {row['number']} "
                f"(R$ {float(row['total'] or 0):,.2f}) para {row['cliente'][:40]} "
                f"no WhatsApp {row['numero']} — PDF + link de assinatura. "
                f"CONFIRA o destinatário: envio não tem desfazer."),
        payload={"proposal_id": row["id"], "number": row["number"],
                 "cliente": row["cliente"], "numero": row["numero"]},
    )


async def _exec_enviar_proposta_whatsapp(db, aprovador_user, payload: dict) -> str:
    from modules.crm.controllers.proposal_controller import send_proposal_whatsapp

    # confirmar=True: o preview já foi o RASCUNHO que o humano leu e aprovou.
    await send_proposal_whatsapp(
        proposal_id=str(payload["proposal_id"]), current_user=aprovador_user,
        confirmar=True, db=db)
    return str(payload["proposal_id"])


async def _propor_cadastrar_whatsapp(db, user, scope, *, cliente=None, numero=None,
                                     **_) -> dict[str, Any]:
    from modules.crm.services.phone import to_e164_br

    ref = str(cliente or "").strip()
    num = str(numero or "").strip()
    if not ref or not num:
        return {"erro": "informe o cliente (CNPJ, id ou nome) e o número com DDD"}
    e164 = to_e164_br(num)
    if not e164:
        return {"erro": f"número inválido: {num!r}. Use DDD+número (ex.: 92 99123-4567)."}

    row = (await db.execute(text(
        "SELECT id::text AS id, name FROM clients "
        "WHERE id::text = :r OR upper(name) = upper(:r) "
        "   OR regexp_replace(coalesce(document_number, ''), '[^0-9]', '', 'g') = "
        "      regexp_replace(:r, '[^0-9]', '', 'g') LIMIT 1"),
        {"r": ref})).mappings().first()
    if not row:
        return {"erro": f"cliente {ref!r} não existe no cadastro."}

    return await criar_rascunho(
        db, user, tipo="cadastrar_whatsapp", modulo="crm",
        gate="🟡", requires_otp=False, roles_aprovador=ROLES_COMERCIAL,
        idempotency_key=f"wa_cad:{_slug(row['name'])}:{e164}",
        titulo=f"CADASTRAR WhatsApp de {row['name'][:38]}",
        resumo=(f"Aprovar grava {e164} como WhatsApp de {row['name'][:50]}. "
                f"É por este número que a empresa vai falar com ele — confira antes."),
        payload={"cnpj_ou_id": row["id"], "numero": num, "e164": e164,
                 "cliente": row["name"]},
    )


async def _exec_cadastrar_whatsapp(db, aprovador_user, payload: dict) -> str:
    from modules.crm.controllers.growth_controller import (
        WhatsAppCadastroIn, cadastrar_whatsapp,
    )

    await cadastrar_whatsapp(
        data=WhatsAppCadastroIn(cnpj_ou_id=str(payload["cnpj_ou_id"]),
                                numero=str(payload["numero"])),
        db=db)
    return str(payload["cnpj_ou_id"])


registrar_executor("enviar_proposta_whatsapp", _exec_enviar_proposta_whatsapp)
registrar_executor("cadastrar_whatsapp", _exec_cadastrar_whatsapp)

registrar_acao("crm", "enviar_proposta_whatsapp",
               "ENVIAR uma proposta ao cliente pelo WhatsApp (PDF + link de assinatura). "
               "dados: proposta (número ou id). EXTERNO e irreversível — nasce rascunho e "
               "só a aprovação envia.",
               _propor_enviar_proposta_whatsapp)

registrar_acao("crm", "cadastrar_whatsapp",
               "CADASTRAR o WhatsApp de um cliente. dados: cliente (CNPJ, id ou nome), "
               "numero (com DDD). Nasce rascunho.",
               _propor_cadastrar_whatsapp)
```

- [ ] **Step 4: Declarar grau e área**

Em `_AMARELAS` (`agente_aprovacao_controller.py`):

```python
    # `enviar_proposta_whatsapp` e `cadastrar_whatsapp` (27/08/2026): a primeira SAI DA
    # EMPRESA e é irreversível, e por isso usa ROLES_MONEY como aprovador e nomeia o
    # destinatário no resumo. É 🟡 e não 🔴 porque `enviar_proposta` (e-mail), que tem
    # exatamente o mesmo risco, já é 🟡 — tratar canal diferente com grau diferente seria
    # arbitrário. A segunda só grava um número no cadastro.
    "enviar_proposta_whatsapp",
    "cadastrar_whatsapp",
```

Em `_AREA_DRAFT` (`aprovacoes.py`):

```python
    "enviar_proposta_whatsapp": "CRM", "cadastrar_whatsapp": "CRM",
```

- [ ] **Step 5: Verificar a coluna `whatsapp` em `clients` antes de confiar no SQL**

```bash
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 -c "
import asyncio, sys; sys.path.insert(0,'/app')
async def m():
    from sqlalchemy import text
    from core.database import async_session_factory
    async with async_session_factory() as db:
        c=(await db.execute(text(\"SELECT column_name FROM information_schema.columns WHERE table_name='clients' AND column_name IN ('whatsapp','phone')\"))).scalars().all()
        print('colunas:', c)
asyncio.run(m())"
```
Esperado: `colunas: ['phone', 'whatsapp']`. **Se `whatsapp` não existir, remova `c.whatsapp,` do `coalesce` no Step 3 e refaça o Step 6** — coluna inventada é o erro mais comum deste repositório.

- [ ] **Step 6: Rodar o oráculo e confirmar 5/5**

```bash
cd /opt/conecta-pro
for f in modules/ai/conversation/services/orquestrador/tools_acao_crm.py \
         modules/ai/conversation/controllers/agente_aprovacao_controller.py \
         modules/operacional/controllers/redesign_builders/aprovacoes.py; do
  docker cp backend/$f conecta-pro-backend:/app/$f
done
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_acao_envio_cliente.py; echo "exit=$?"
```
Esperado: `OK acao_envio_cliente: 5/5 ...` e `exit=0`.

- [ ] **Step 7: Provar o oráculo VERMELHO por mutação**

```bash
cd /opt/conecta-pro
cp backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py /tmp/ok2.py
python3 - <<'EOF'
p='/opt/conecta-pro/backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py'
s=open(p).read()
a='''    if not str(row["numero"] or "").strip():'''
assert a in s
open(p,'w').write(s.replace(a,'''    if False:  # MUTACAO: envia sem numero'''))
EOF
docker cp backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py \
  conecta-pro-backend:/app/modules/ai/conversation/services/orquestrador/tools_acao_crm.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_acao_envio_cliente.py
cp /tmp/ok2.py backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py
docker cp backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py \
  conecta-pro-backend:/app/modules/ai/conversation/services/orquestrador/tools_acao_crm.py
diff -q /tmp/ok2.py backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py
```
Esperado no mutado: FALHA acusando o resumo sem destinatário. Esperado no `diff`: sem saída.

- [ ] **Step 8: Commit**

```bash
cd /opt/conecta-pro
git add backend/scripts/orq/test_acao_envio_cliente.py
git commit --no-verify -m "feat(crm): enviar proposta por WhatsApp + cadastrar numero do cliente

10 propostas sem resposta ha 64 dias, todas por e-mail. WhatsApp e onde o
cliente responde. ENVIO E IRREVERSIVEL: o resumo do rascunho NOMEIA o
destinatario, porque quem aprova precisa ver para quem vai antes de clicar.

test_acao_envio_cliente 5/5, provado vermelho por mutacao.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" \
  -- backend/scripts/orq/test_acao_envio_cliente.py \
     backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py \
     backend/modules/ai/conversation/controllers/agente_aprovacao_controller.py \
     backend/modules/operacional/controllers/redesign_builders/aprovacoes.py
```

---

## Task 3: Follow-up em lote e opt-out

`followup_em_lote` toca TODOS os clientes com proposta pendente de uma vez. É a ação de maior alcance deste plano: um erro aqui vai para dezenas de clientes simultaneamente. A rota já tem `confirmar=False` como preview — e é esse preview que vira o resumo do rascunho.

**Files:**
- Modify: `backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py` (fim do arquivo)
- Modify: `backend/modules/ai/conversation/controllers/agente_aprovacao_controller.py` (`_AMARELAS`)
- Modify: `backend/modules/operacional/controllers/redesign_builders/aprovacoes.py` (`_AREA_DRAFT`)
- Test: `backend/scripts/orq/test_acao_funil_crm.py` (estender o da Task 1)

**Interfaces:**
- Consumes: `criar_rascunho`, `registrar_executor`, `registrar_acao`, `ROLES_MONEY`.
- Produces: `_propor_followup_em_lote(db, user, scope, *, mensagem=None, **_) -> dict`, `_exec_followup_em_lote(db, aprovador_user, payload) -> str`, `_propor_optout_whatsapp(db, user, scope, *, numero=None, motivo=None, **_) -> dict`, `_exec_optout_whatsapp(db, aprovador_user, payload) -> str`. Tipos: `"followup_em_lote"`, `"optout_whatsapp"`.

- [ ] **Step 1: Estender o oráculo da Task 1**

Em `backend/scripts/orq/test_acao_funil_crm.py`, ANTES da linha `await _limpar(db)` final, inserir:

```python
        # ── FOLLOW-UP EM LOTE: a ação de maior alcance do plano ──────────────────────
        from modules.ai.conversation.services.orquestrador.tools_acao_crm import (
            _propor_followup_em_lote as LOTE,
        )

        r = await LOTE(db, u, scope)
        if not r.get("erro"):
            falhas.append("follow-up em lote SEM MENSAGEM foi aceito — sairia texto "
                          "vazio para dezenas de clientes")

        n0 = (await db.execute(text("SELECT count(*) FROM crm_followups"))).scalar()
        r = await LOTE(db, u, scope, mensagem=f"{_MARCA} toque de teste")
        if not (r.get("draft_id") or r.get("id")):
            falhas.append(f"lote válido não virou rascunho: {str(r)[:110]}")
        else:
            d = (await db.execute(text(
                "SELECT resumo FROM agent_drafts WHERE tipo = 'followup_em_lote' "
                "ORDER BY created_at DESC LIMIT 1"))).scalar() or ""
            if not any(ch.isdigit() for ch in d):
                falhas.append("o resumo do lote não diz QUANTOS clientes serão tocados — "
                              "quem aprova não sabe o alcance")
        n1 = (await db.execute(text("SELECT count(*) FROM crm_followups"))).scalar()
        if n0 != n1:
            falhas.append(f"PROPOR JÁ DISPAROU o lote: crm_followups {n0} → {n1}")
```

E trocar a mensagem final de `4/4` para:

```python
    print("OK acao_funil_crm: 7/7 — recusa deal inexistente, estágio inválido e "
          "closed_won; recusa lote sem mensagem; o resumo do lote diz QUANTOS clientes "
          "serão tocados; e nem mover nem disparar acontece antes da aprovação.")
```

- [ ] **Step 2: Rodar e confirmar que FALHA**

```bash
cd /opt/conecta-pro
docker cp backend/scripts/orq/test_acao_funil_crm.py \
  conecta-pro-backend:/app/scripts/orq/test_acao_funil_crm.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_acao_funil_crm.py
```
Esperado: `ImportError: cannot import name '_propor_followup_em_lote'`.

- [ ] **Step 3: Implementar**

Acrescentar ao FIM de `tools_acao_crm.py`:

```python


# ── FOLLOW-UP EM LOTE E OPT-OUT ───────────────────────────────────────────────────────
# ⚠️ MAIOR ALCANCE DESTE PLANO: um toque em lote fala com TODOS os clientes que têm
# proposta pendente ao mesmo tempo. Erro aqui não atinge um cliente — atinge a carteira.
# Por isso o rascunho carrega o PREVIEW REAL (a rota já sabe fazer, com confirmar=False)
# e o resumo diz QUANTOS serão tocados. Quem aprova precisa saber o alcance, não só o texto.

async def _propor_followup_em_lote(db, user, scope, *, mensagem=None,
                                   **_) -> dict[str, Any]:
    from modules.crm.services import orchestration as _O

    texto = str(mensagem or "").strip()
    if not texto:
        return {"erro": "informe a mensagem do toque — não disparo texto vazio para a "
                        "carteira inteira."}
    if len(texto) < 10:
        return {"erro": f"mensagem curta demais ({len(texto)} caracteres) para ir a "
                        f"dezenas de clientes. Escreva o toque completo."}

    # PREVIEW REAL: `confirmar=False` devolve quem seria tocado SEM tocar ninguém.
    previa = await _O.followup_em_lote(db, mensagem=texto, confirmar=False)
    # A chave é `qtd` — conferido com a sonda do Step 5. `total` não existe neste
    # retorno, e presumir chave de dicionário é a mesma classe de erro que inventar coluna.
    alvos = previa.get("qtd") or len(previa.get("clientes") or [])

    return await criar_rascunho(
        db, user, tipo="followup_em_lote", modulo="crm",
        gate="🟡", requires_otp=False, roles_aprovador=ROLES_MONEY,
        idempotency_key=f"lote:{_slug(texto[:40])}",
        titulo=f"TOQUE EM LOTE — {alvos} cliente(s)",
        resumo=(f"⚠️ EXTERNO E EM LOTE: aprovar envia esta mensagem para {alvos} "
                f"cliente(s) com proposta pendente, DE UMA VEZ. Texto: "
                f"\"{texto[:160]}\". Não há desfazer para nenhum deles."),
        payload={"mensagem": texto, "alvos": alvos},
    )


async def _exec_followup_em_lote(db, aprovador_user, payload: dict) -> str:
    from modules.crm.services import orchestration as _O

    res = await _O.followup_em_lote(db, mensagem=str(payload["mensagem"]),
                                    confirmar=True)
    return str(res.get("enviados") or res.get("total") or 0)


async def _propor_optout_whatsapp(db, user, scope, *, numero=None, motivo=None,
                                  **_) -> dict[str, Any]:
    from modules.crm.services.phone import canonical_br

    num = str(numero or "").strip()
    if not num:
        return {"erro": "informe o número que não deve mais receber follow-up"}
    c = canonical_br(num)
    if not c:
        return {"erro": f"número inválido: {num!r}"}

    return await criar_rascunho(
        db, user, tipo="optout_whatsapp", modulo="crm",
        gate="🟡", requires_otp=False, roles_aprovador=ROLES_COMERCIAL,
        idempotency_key=f"optout:{c}",
        titulo=f"OPT-OUT de follow-up — {c}",
        resumo=(f"Aprovar marca {c} como opt-out: ele NÃO recebe mais follow-up "
                f"automático. {('Motivo: ' + str(motivo)[:100] + '. ') if motivo else ''}"
                f"É proteção do cliente — na dúvida, aprove."),
        payload={"numero": num, "canonical": c, "motivo": (motivo or None)},
    )


async def _exec_optout_whatsapp(db, aprovador_user, payload: dict) -> str:
    from modules.crm.controllers.growth_controller import OptoutIn, followup_optout

    await followup_optout(
        data=OptoutIn(numero=str(payload["numero"]),
                      motivo=(payload.get("motivo") or None)),
        db=db)
    return str(payload["canonical"])


registrar_executor("followup_em_lote", _exec_followup_em_lote)
registrar_executor("optout_whatsapp", _exec_optout_whatsapp)

registrar_acao("crm", "followup_em_lote",
               "TOQUE EM LOTE em todos os clientes com proposta pendente. dados: mensagem "
               "(obrigatória, mínimo 10 caracteres). O rascunho mostra QUANTOS serão "
               "tocados. EXTERNO e irreversível — só a aprovação dispara.",
               _propor_followup_em_lote)

registrar_acao("crm", "optout_whatsapp",
               "Marcar um número como OPT-OUT (não recebe mais follow-up). dados: numero, "
               "motivo.",
               _propor_optout_whatsapp)
```

- [ ] **Step 4: Declarar grau e área**

Em `_AMARELAS`:

```python
    # `followup_em_lote` (27/08/2026): é a ação de MAIOR ALCANCE do CRM — fala com a
    # carteira inteira de uma vez. Ficou 🟡 e não 🔴 porque o rascunho carrega o preview
    # REAL (quantos serão tocados) e o texto integral, então quem aprova vê o alcance
    # antes de clicar. Se algum dia o preview sumir do resumo, isto vira 🔴.
    "followup_em_lote",
    # `optout_whatsapp`: protege o cliente de receber mensagem. Recusar seria pior.
    "optout_whatsapp",
```

Em `_AREA_DRAFT`:

```python
    "followup_em_lote": "CRM", "optout_whatsapp": "CRM",
```

- [ ] **Step 5: Conferir a forma real do retorno de `followup_em_lote`**

```bash
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 -c "
import asyncio, sys; sys.path.insert(0,'/app')
async def m():
    from core.database import async_session_factory
    from modules.crm.services import orchestration as O
    async with async_session_factory() as db:
        r = await O.followup_em_lote(db, mensagem='sonda de forma', confirmar=False)
        print('chaves:', sorted(r.keys()))
        print('amostra:', str(r)[:200])
asyncio.run(m())"
```
Se `total` não estiver nas chaves, ajuste a linha `alvos = ...` do Step 3 para a chave real. **Não presuma a forma do retorno** — presumir chave de dicionário é a mesma classe de erro que inventar coluna.

- [ ] **Step 6: Rodar o oráculo e confirmar 7/7**

```bash
cd /opt/conecta-pro
for f in modules/ai/conversation/services/orquestrador/tools_acao_crm.py \
         modules/ai/conversation/controllers/agente_aprovacao_controller.py \
         modules/operacional/controllers/redesign_builders/aprovacoes.py; do
  docker cp backend/$f conecta-pro-backend:/app/$f
done
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_acao_funil_crm.py; echo "exit=$?"
```
Esperado: `OK acao_funil_crm: 7/7 ...` e `exit=0`.

- [ ] **Step 7: Provar VERMELHO por mutação**

```bash
cd /opt/conecta-pro
cp backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py /tmp/ok3.py
python3 - <<'EOF'
p='/opt/conecta-pro/backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py'
s=open(p).read()
a='''    if not texto:
        return {"erro": "informe a mensagem do toque — não disparo texto vazio para a "
                        "carteira inteira."}'''
assert a in s
open(p,'w').write(s.replace(a,'''    texto = texto or "."  # MUTACAO: aceita vazio'''))
EOF
docker cp backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py \
  conecta-pro-backend:/app/modules/ai/conversation/services/orquestrador/tools_acao_crm.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_acao_funil_crm.py
cp /tmp/ok3.py backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py
docker cp backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py \
  conecta-pro-backend:/app/modules/ai/conversation/services/orquestrador/tools_acao_crm.py
diff -q /tmp/ok3.py backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py
```
Esperado no mutado: `FALHOU: follow-up em lote SEM MENSAGEM foi aceito`. `diff`: sem saída.

- [ ] **Step 8: Commit**

```bash
cd /opt/conecta-pro
git commit --no-verify -m "feat(crm): follow-up em lote (com preview no rascunho) e opt-out

Acao de MAIOR ALCANCE do CRM: fala com a carteira inteira de uma vez. O
rascunho carrega o preview REAL — quantos serao tocados — porque quem aprova
precisa ver o alcance, nao so o texto. Se o preview sumir do resumo, vira 🔴.

test_acao_funil_crm 4/4 -> 7/7, provado vermelho por mutacao.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" \
  -- backend/scripts/orq/test_acao_funil_crm.py \
     backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py \
     backend/modules/ai/conversation/controllers/agente_aprovacao_controller.py \
     backend/modules/operacional/controllers/redesign_builders/aprovacoes.py
```

---

## Task 4: Cadência — inscrever lead em sequência e ver as inscrições

37 leads estão sem contato há 39 dias em média (o mais velho, 74). Sequência é o que transforma "eu lembro de dar retorno" em processo. As rotas `/crm/sequences`, `/sequences/{sid}/enroll` e `/sequences/{sid}/enrollments` já existem.

**Files:**
- Modify: `backend/modules/ai/conversation/services/orquestrador/tools_read_crm.py` (fim do arquivo)
- Modify: `backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py` (fim do arquivo)
- Modify: `backend/modules/ai/conversation/controllers/agente_aprovacao_controller.py` (`_AMARELAS`)
- Modify: `backend/modules/operacional/controllers/redesign_builders/aprovacoes.py` (`_AREA_DRAFT`)
- Test: `backend/scripts/orq/test_acao_funil_crm.py` (estender de novo)

**Interfaces:**
- Consumes: `registrar_read`, `_gate` (em `tools_read_crm.py`); `criar_rascunho`, `registrar_executor`, `registrar_acao`, `ROLES_COMERCIAL` (em `tools_acao_crm.py`).
- Produces: leitura `crm.sequencia_inscricoes`; ação `inscrever_em_sequencia` com `_propor_inscrever_em_sequencia(db, user, scope, *, sequencia=None, lead=None, **_) -> dict` e `_exec_inscrever_em_sequencia(db, aprovador_user, payload) -> str`.

- [ ] **Step 1: Escrever a leitura**

Acrescentar ao FIM de `backend/modules/ai/conversation/services/orquestrador/tools_read_crm.py`:

```python


# ── INSCRIÇÕES EM SEQUÊNCIA (cadência) ────────────────────────────────────────────────
# 27/08/2026: 37 leads sem contato há 39 dias em média, o mais velho há 74. Sequência é o
# que transforma "eu lembro de dar retorno" em processo — e ela já existia sem porta.

async def _sequencia_inscricoes(db, user, scope, *, sequencia=None, **_) -> Any:
    _gate(user)
    from modules.crm.controllers.growth_controller import list_enrollments, list_sequences

    if not str(sequencia or "").strip():
        # Sem a sequência, devolve a LISTA delas em vez de erro: a pergunta natural é
        # "quais sequências eu tenho?", e responder isso é mais útil que recusar.
        return {"sequencias": await list_sequences(db=db),
                "dica": "informe `sequencia` (id) para ver quem está inscrito"}
    return await list_enrollments(sid=str(sequencia).strip(), db=db)


registrar_read("crm", "sequencia_inscricoes",
               "Sequências de cadência e quem está inscrito nelas. Filtros: sequencia "
               "(id da sequência; sem ele, lista as sequências).", _sequencia_inscricoes)
```

- [ ] **Step 2: Provar a leitura com dado real**

```bash
cd /opt/conecta-pro
docker cp backend/modules/ai/conversation/services/orquestrador/tools_read_crm.py \
  conecta-pro-backend:/app/modules/ai/conversation/services/orquestrador/tools_read_crm.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 -c "
import asyncio, sys; sys.path.insert(0,'/app')
async def m():
    from sqlalchemy import select
    from core.database import async_session_factory
    from core.models.user import User
    import modules.ai.conversation.controllers.consultor_escopado_controller as C
    from modules.ai.conversation.services.orquestrador.read_dispatcher import _READ_OPS
    import modules.ai.conversation.services.orquestrador.tools_read_crm  # noqa
    async with async_session_factory() as db:
        u=(await db.execute(select(User).where(User.email=='jjesus@conectamais.pro'))).scalar_one()
        scope,_=await C._resolver_tier_e_tools(db,u)
        r=await _READ_OPS['crm']['sequencia_inscricoes']['handler'](db,u,scope)
        print('sem filtro:', str(r)[:200])
asyncio.run(m())"
```
Esperado: um dicionário com `sequencias` (lista, possivelmente vazia) e `dica`. **Lista vazia é resultado legítimo** — significa que ele não tem sequência criada, e isso deve ser dito, não escondido.

- [ ] **Step 3: Estender o oráculo com a ação**

Em `backend/scripts/orq/test_acao_funil_crm.py`, antes do `await _limpar(db)` final:

```python
        # ── CADÊNCIA: inscrever lead em sequência ────────────────────────────────────
        from modules.ai.conversation.services.orquestrador.tools_acao_crm import (
            _propor_inscrever_em_sequencia as INSC,
        )

        r = await INSC(db, u, scope, sequencia="ZZ_NAO_EXISTE", lead="qualquer")
        if not r.get("erro"):
            falhas.append("sequência inexistente foi aceita")

        seq = (await db.execute(text(
            "SELECT id::text FROM crm_sequences WHERE is_active = true LIMIT 1"))).scalar()
        if seq:
            r = await INSC(db, u, scope, sequencia=seq, lead="ZZ_LEAD_NAO_EXISTE")
            if not r.get("erro"):
                falhas.append("lead inexistente foi inscrito")
        else:
            print("  (sem sequência ativa — bloco de cadência não exercitado)")
```

E ajustar a mensagem final para `9/9` com o texto:

```python
    print("OK acao_funil_crm: 9/9 — recusa deal inexistente, estágio inválido e "
          "closed_won; recusa lote sem mensagem e mostra o alcance; recusa sequência e "
          "lead inexistentes; e nada acontece antes da aprovação.")
```

- [ ] **Step 4: Rodar e confirmar que FALHA**

```bash
cd /opt/conecta-pro
docker cp backend/scripts/orq/test_acao_funil_crm.py \
  conecta-pro-backend:/app/scripts/orq/test_acao_funil_crm.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_acao_funil_crm.py
```
Esperado: `ImportError: cannot import name '_propor_inscrever_em_sequencia'`.

- [ ] **Step 5: Implementar a ação**

Acrescentar ao FIM de `tools_acao_crm.py`:

```python


# ── INSCREVER LEAD EM SEQUÊNCIA DE CADÊNCIA ───────────────────────────────────────────
# Inscrever coloca o lead numa esteira que vai MANDAR MENSAGEM para ele nos próximos
# dias, sem ninguém aprovar cada uma. Por isso a inscrição é o ponto de controle: é aqui
# que um humano decide que aquele lead vai receber a régua inteira.

async def _propor_inscrever_em_sequencia(db, user, scope, *, sequencia=None, lead=None,
                                         **_) -> dict[str, Any]:
    sid = str(sequencia or "").strip()
    lref = str(lead or "").strip()
    if not sid or not lref:
        return {"erro": "informe a sequencia (id) e o lead (id ou nome)"}

    seq = (await db.execute(text(
        "SELECT id::text AS id, name, coalesce(jsonb_array_length(steps), 0) AS passos "
        "FROM crm_sequences WHERE id::text = :s AND is_active = true"),
        {"s": sid})).mappings().first()
    if not seq:
        return {"erro": f"sequência {sid!r} não existe ou está inativa."}

    lrow = (await db.execute(text(
        "SELECT id::text AS id, name, coalesce(company, '') AS empresa FROM leads "
        "WHERE id::text = :l OR upper(name) = upper(:l) "
        "ORDER BY (upper(name) = upper(:l)) DESC LIMIT 1"),
        {"l": lref})).mappings().first()
    if not lrow:
        return {"erro": f"lead {lref!r} não existe — não crio lead de passagem."}

    return await criar_rascunho(
        db, user, tipo="inscrever_em_sequencia", modulo="crm",
        gate="🟡", requires_otp=False, roles_aprovador=ROLES_COMERCIAL,
        idempotency_key=f"enroll:{seq['id']}:{lrow['id']}",
        titulo=f"INSCREVER {lrow['name'][:30]} na sequência {seq['name'][:24]}",
        resumo=(f"⚠️ Aprovar inscreve {lrow['name'][:40]}"
                f"{(' (' + lrow['empresa'][:24] + ')') if lrow['empresa'] else ''} "
                f"na sequência '{seq['name'][:40]}', de {seq['passos']} passo(s). "
                f"A partir daí as mensagens saem AUTOMATICAMENTE, sem aprovar uma a uma "
                f"— é esta aprovação que autoriza a régua inteira."),
        payload={"sequence_id": seq["id"], "sequence_name": seq["name"],
                 "lead_id": lrow["id"], "lead_name": lrow["name"]},
    )


async def _exec_inscrever_em_sequencia(db, aprovador_user, payload: dict) -> str:
    from modules.crm.controllers.growth_controller import EnrollIn, enroll_in_sequence

    res = await enroll_in_sequence(
        sid=str(payload["sequence_id"]),
        data=EnrollIn(lead_id=str(payload["lead_id"])), db=db)
    return str(res.get("enrollment_id") or payload["lead_id"])


registrar_executor("inscrever_em_sequencia", _exec_inscrever_em_sequencia)

registrar_acao("crm", "inscrever_em_sequencia",
               "INSCREVER um lead numa sequência de cadência. dados: sequencia (id), lead "
               "(id ou nome). Depois de inscrito, as mensagens saem automaticamente — a "
               "aprovação da inscrição é que autoriza a régua toda.",
               _propor_inscrever_em_sequencia)
```

- [ ] **Step 6: Declarar grau e área**

Em `_AMARELAS`:

```python
    # `inscrever_em_sequencia` (27/08/2026): inscrever autoriza a RÉGUA INTEIRA de
    # mensagens automáticas, não uma mensagem. É 🟡 porque o resumo diz quantos passos a
    # sequência tem e que as mensagens sairão sem aprovar uma a uma — o aprovador sabe
    # exatamente o que está liberando.
    "inscrever_em_sequencia",
```

Em `_AREA_DRAFT`:

```python
    "inscrever_em_sequencia": "CRM",
```

- [ ] **Step 7: Rodar o oráculo e confirmar 9/9**

```bash
cd /opt/conecta-pro
for f in modules/ai/conversation/services/orquestrador/tools_acao_crm.py \
         modules/ai/conversation/services/orquestrador/tools_read_crm.py \
         modules/ai/conversation/controllers/agente_aprovacao_controller.py \
         modules/operacional/controllers/redesign_builders/aprovacoes.py; do
  docker cp backend/$f conecta-pro-backend:/app/$f
done
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_acao_funil_crm.py; echo "exit=$?"
```
Esperado: `OK acao_funil_crm: 9/9 ...` e `exit=0`.

- [ ] **Step 8: Commit**

```bash
cd /opt/conecta-pro
git commit --no-verify -m "feat(crm): cadencia — inscrever lead em sequencia e ver inscricoes

37 leads sem contato ha 39 dias em media (o mais velho, 74). Inscrever
autoriza a REGUA INTEIRA de mensagens automaticas, nao uma mensagem — o
resumo diz quantos passos a sequencia tem e que as mensagens sairao sem
aprovar uma a uma.

test_acao_funil_crm 7/7 -> 9/9.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" \
  -- backend/scripts/orq/test_acao_funil_crm.py \
     backend/modules/ai/conversation/services/orquestrador/tools_acao_crm.py \
     backend/modules/ai/conversation/services/orquestrador/tools_read_crm.py \
     backend/modules/ai/conversation/controllers/agente_aprovacao_controller.py \
     backend/modules/operacional/controllers/redesign_builders/aprovacoes.py
```

---

## Task 5: Apresentação/deck a partir da visita

Fecha o ciclo que o Jordan descreveu: visita → orçamento → **apresentação** → proposta. A rota `POST /crm/apresentacoes/gerar` recebe `ApresentacaoIn` (titulo, subtitulo, cliente, local, data, slides) e aceita `formato="pptx"|"pdf"`.

**Files:**
- Modify: `backend/modules/ai/conversation/services/orquestrador/tools_comercial_doc.py` (fim do arquivo)
- Test: `backend/scripts/orq/test_orcamento_por_itens.py` (estender — é o oráculo dos documentos comerciais)

**Interfaces:**
- Consumes: `ToolDef`, `register`, `_gate`, `_recusa`, `_slug`, `base64` (todos já no topo de `tools_comercial_doc.py`).
- Produces: ToolDef `gerar_apresentacao_doc` com handler `_gerar_apresentacao(db, user, scope, *, titulo=None, cliente=None, slides=None, formato="pptx", **_)`.

- [ ] **Step 1: Estender o oráculo dos documentos**

Em `backend/scripts/orq/test_orcamento_por_itens.py`, antes do bloco `# 7 · INÉRCIA`:

```python
        # 11 · APRESENTAÇÃO: não inventa conteúdo de slide
        from modules.ai.conversation.services.orquestrador.tool_registry import (
            _REGISTRY as _REG,
        )

        if "gerar_apresentacao_doc" not in _REG:
            falhas.append("`gerar_apresentacao_doc` não está registrada")
        else:
            ha = _REG["gerar_apresentacao_doc"].handler
            r = await ha(db, u, scope, titulo="Sem slides")
            if r.get("status") != "recusado":
                falhas.append("apresentação SEM SLIDES foi aceita — o modelo inventaria "
                              "o conteúdo do material que vai ao cliente")
            r = await ha(db, u, scope, cliente=cli,
                         titulo="Oráculo — proposta técnica",
                         slides=[{"titulo": "Diagnóstico",
                                  "bullets": ["8 câmeras analógicas", "DVR sem HD"]}])
            if r.get("status") == "recusado":
                falhas.append(f"apresentação válida recusada: {r.get('motivo','')[:90]}")
            elif not r.get("arquivo_base64"):
                falhas.append("apresentação válida não devolveu arquivo")
```

E ajustar a mensagem final de `10/10` para `12/12`, acrescentando ao texto: `"; e a apresentação recusa slide inventado"`.

- [ ] **Step 2: Rodar e confirmar que FALHA**

```bash
cd /opt/conecta-pro
docker cp backend/scripts/orq/test_orcamento_por_itens.py \
  conecta-pro-backend:/app/scripts/orq/test_orcamento_por_itens.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_orcamento_por_itens.py
```
Esperado: `FALHOU: gerar_apresentacao_doc não está registrada`.

- [ ] **Step 3: Implementar**

Acrescentar ao FIM de `backend/modules/ai/conversation/services/orquestrador/tools_comercial_doc.py`:

```python


# ── APRESENTAÇÃO / DECK ───────────────────────────────────────────────────────────────
# Fecha o ciclo: visita → orçamento → APRESENTAÇÃO → proposta. A rota já monta o material
# no padrão-ouro da marca (timbrado, cores, rodapé com CNPJ) — o que faltava era porta.
#
# ⭐ SLIDES SÃO OBRIGATÓRIOS. Sem eles o modelo escreveria sozinho o conteúdo de um
# material que vai ao CLIENTE, com a marca da empresa. Esse é o tipo de fabricação que não
# aparece em teste nenhum: sai bonito, tem a logo certa e diz coisa que ninguém aprovou.

_SCHEMA_APRESENTACAO = {
    "type": "object",
    "properties": {
        "titulo": {"type": "string", "description": "Título da apresentação."},
        "subtitulo": {"type": "string"},
        "cliente": {"type": "string", "description": "Nome do cliente (aparece na capa)."},
        "local": {"type": "string"},
        "formato": {"type": "string", "enum": ["pptx", "pdf"],
                    "description": "Padrão pptx."},
        "slides": {
            "type": "array",
            "description": "Slides do deck. Cada um: {titulo, bullets:[...]}. "
                           "OBRIGATÓRIO — o conteúdo vem da conversa, não é inventado.",
            "items": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "bullets": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
    "required": ["titulo", "slides"],
}


async def _gerar_apresentacao(db, user, scope, *, titulo=None, subtitulo=None,
                              cliente=None, local=None, slides=None, formato="pptx",
                              **_) -> dict[str, Any]:
    _gate(user)
    from modules.crm.controllers.growth_controller import (
        ApresentacaoIn, gerar_apresentacao,
    )

    if not str(titulo or "").strip():
        return _recusa("informe o título da apresentação.")
    if not isinstance(slides, list) or not slides:
        return _recusa("informe os slides (título e tópicos de cada um). Não escrevo "
                       "sozinho o conteúdo de um material que vai ao cliente com a "
                       "marca da empresa.")
    fmt = str(formato or "pptx").lower()
    if fmt not in ("pptx", "pdf"):
        return _recusa(f"formato {fmt!r} não existe — use pptx ou pdf.")

    res = await gerar_apresentacao(
        data=ApresentacaoIn(titulo=str(titulo)[:200],
                            subtitulo=(subtitulo or None),
                            cliente=(cliente or None),
                            local=(local or None),
                            slides=list(slides)),
        db=db, formato=fmt)

    # O controller devolve bytes ou um Response; normalizamos para o mesmo contrato das
    # outras tools de documento (arquivo_base64 + nome), para o chat tratar tudo igual.
    conteudo = getattr(res, "body", None) or res
    if isinstance(conteudo, (bytes, bytearray)):
        return {
            "arquivo_base64": base64.b64encode(bytes(conteudo)).decode(),
            "nome": f"apresentacao_{_slug(str(cliente or titulo))}.{fmt}",
            "slides": len(slides),
            "resumo": f"Apresentação '{str(titulo)[:40]}' com {len(slides)} slide(s) "
                      f"(RASCUNHO — não envia).",
        }
    return {"resultado": conteudo, "slides": len(slides)}


register(ToolDef(
    "gerar_apresentacao_doc", "crm",
    "Monta uma APRESENTAÇÃO branded (pptx ou pdf) a partir dos slides que a pessoa "
    "ditou. `slides` é obrigatório: o conteúdo vem da conversa, nunca inventado. "
    "Não grava, não envia.",
    _SCHEMA_APRESENTACAO, _gerar_apresentacao, scope_kind="org"))
```

- [ ] **Step 4: Conferir a forma real do retorno de `gerar_apresentacao`**

```bash
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 -c "
import asyncio, sys, inspect; sys.path.insert(0,'/app')
from modules.crm.controllers.growth_controller import gerar_apresentacao
print(inspect.signature(gerar_apresentacao))
src = inspect.getsource(gerar_apresentacao)
print([l.strip() for l in src.splitlines() if 'return' in l][:5])"
```
Se ele devolver `StreamingResponse` ou `FileResponse` (e não bytes), ajuste a normalização do Step 3 para ler o corpo do jeito certo. **Presumir o tipo de retorno é a mesma classe de erro que inventar coluna.**

- [ ] **Step 5: Rodar o oráculo e confirmar 12/12**

```bash
cd /opt/conecta-pro
docker cp backend/modules/ai/conversation/services/orquestrador/tools_comercial_doc.py \
  conecta-pro-backend:/app/modules/ai/conversation/services/orquestrador/tools_comercial_doc.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_orcamento_por_itens.py; echo "exit=$?"
```
Esperado: `OK orcamento_por_itens: 12/12 ...` e `exit=0`.

- [ ] **Step 6: Provar VERMELHO por mutação**

```bash
cd /opt/conecta-pro
cp backend/modules/ai/conversation/services/orquestrador/tools_comercial_doc.py /tmp/ok5.py
python3 - <<'EOF'
p='/opt/conecta-pro/backend/modules/ai/conversation/services/orquestrador/tools_comercial_doc.py'
s=open(p).read()
a='''    if not isinstance(slides, list) or not slides:'''
assert a in s
open(p,'w').write(s.replace(a,'''    slides = slides or [{"titulo": "Inventado", "bullets": []}]
    if False:'''))
EOF
docker cp backend/modules/ai/conversation/services/orquestrador/tools_comercial_doc.py \
  conecta-pro-backend:/app/modules/ai/conversation/services/orquestrador/tools_comercial_doc.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_orcamento_por_itens.py
cp /tmp/ok5.py backend/modules/ai/conversation/services/orquestrador/tools_comercial_doc.py
docker cp backend/modules/ai/conversation/services/orquestrador/tools_comercial_doc.py \
  conecta-pro-backend:/app/modules/ai/conversation/services/orquestrador/tools_comercial_doc.py
diff -q /tmp/ok5.py backend/modules/ai/conversation/services/orquestrador/tools_comercial_doc.py
```
Esperado no mutado: `FALHOU: apresentação SEM SLIDES foi aceita`. `diff`: sem saída.

- [ ] **Step 7: Commit**

```bash
cd /opt/conecta-pro
git commit --no-verify -m "feat(crm): apresentacao/deck a partir da conversa

Fecha o ciclo visita -> orcamento -> APRESENTACAO -> proposta. SLIDES SAO
OBRIGATORIOS: sem eles o modelo escreveria sozinho o conteudo de um material
que vai ao CLIENTE com a marca da empresa — fabricacao que sai bonita, com a
logo certa, dizendo coisa que ninguem aprovou.

test_orcamento_por_itens 10/10 -> 12/12, provado vermelho por mutacao.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" \
  -- backend/scripts/orq/test_orcamento_por_itens.py \
     backend/modules/ai/conversation/services/orquestrador/tools_comercial_doc.py
```

---

## Task 6: Fechamento — trava do canal, gate e bake

Nada deste plano pode ter vazado para o canal público, e nenhuma ação nova pode ter nascido 🔵 por esquecimento. Esta task é a conferência mecânica disso e o deploy.

**Files:**
- Test (rodar, não criar): `backend/scripts/orq/test_canal_ferramentas.py`, `backend/scripts/qa/fechado_bartolo.py`, `backend/scripts/qa/checar_drift_workers.sh`

**Interfaces:**
- Consumes: as 6 ações e 1 leitura registradas nas Tasks 1–5.
- Produces: nada de código — produz a garantia de que o conjunto está coerente.

- [ ] **Step 1: Provar que nada vazou para o canal público**

```bash
cd /opt/conecta-pro
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_canal_ferramentas.py; echo "exit=$?"
```
Esperado: `OK canal_ferramentas: 6/6 ...` e `exit=0`. Se falhar com uma tool nova no canal público, **pare** — significa que alguma task declarou `canais=("publico",)` e o cliente passaria a ver ferramenta comercial interna.

- [ ] **Step 2: Provar que toda ação nova tem grau declarado**

```bash
cd /opt/conecta-pro
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 -c "
import sys; sys.path.insert(0,'/app')
import modules.ai.conversation.services.orquestrador.tools_acao_crm  # noqa
from modules.ai.conversation.services.orquestrador.agir_dispatcher import _ACOES
from modules.ai.conversation.controllers.agente_aprovacao_controller import grau_de
novas = ['mover_estagio_deal','enviar_proposta_whatsapp','cadastrar_whatsapp',
         'followup_em_lote','optout_whatsapp','inscrever_em_sequencia']
ruins = [n for n in novas if n not in _ACOES.get('crm', {})]
print('NAO REGISTRADAS:', ruins or 'nenhuma')
for n in novas:
    g, otp = grau_de(n)
    print(f'  {n:28} {g} otp={otp}')
"
```
Esperado: `NAO REGISTRADAS: nenhuma` e as 6 com 🟡. **Qualquer 🔴 aqui significa que faltou declarar em `_AMARELAS`** — o fail-closed funcionou, mas a declaração é obrigatória.

- [ ] **Step 3: Rodar o gate do Bartolo**

```bash
cd /opt/conecta-pro
python3 backend/scripts/qa/fechado_bartolo.py; echo "exit=$?"
```
Esperado: `9/9 condições` / `FECHADO.` e `exit=0`. (Roda do HOST, não do container — ele precisa de docker e git.)

- [ ] **Step 4: Avisar os outros terminais**

Mandar mensagem para as sessões `conecta-pro-5b` e `conecta-pro-b2` dizendo: bake iniciando, ~15min, arquivos tocados (`tools_acao_crm.py`, `tools_read_crm.py`, `tools_comercial_doc.py`, `agente_aprovacao_controller.py`, `aprovacoes.py`), sem migration, e pedindo aviso em 2 minutos se houver WIP nesses arquivos.

- [ ] **Step 5: Assar**

```bash
cd /opt/conecta-pro
ls -ld /tmp/conecta_deploy.lock 2>&1 | grep -q "No such" && \
  bash scripts/deploy_backend_bluegreen.sh
```
Esperado ao fim: `═══ BLUE/GREEN CONCLUÍDO ═══` e `Sem drift`. Leva ~15min (recria os 8 celery).

- [ ] **Step 6: Provar que está NA IMAGEM, não só no container**

```bash
cd /opt/conecta-pro
IMG=$(docker inspect -f '{{.Image}}' conecta-pro-backend)
for n in mover_estagio_deal enviar_proposta_whatsapp followup_em_lote \
         inscrever_em_sequencia gerar_apresentacao_doc sequencia_inscricoes; do
  docker run --rm --entrypoint sh $IMG \
    -c "grep -rqF '\"$n\"' /app/modules/ai/conversation/services/orquestrador/" \
    && echo "OK  $n" || echo "FORA  $n"
done
bash scripts/checar_drift_workers.sh; echo "drift exit=$?"
```
Esperado: 6 linhas `OK` e `drift exit=0`. **Grepe a string DISTINTIVA entre aspas** — grepar só a palavra dá falso positivo com texto de comentário, e isso já aconteceu neste projeto em 27/08/2026.

- [ ] **Step 7: Rodar os três oráculos contra a imagem assada**

```bash
cd /opt/conecta-pro
for o in test_acao_funil_crm test_acao_envio_cliente test_orcamento_por_itens; do
  docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/$o.py \
    >/tmp/$o.out 2>/dev/null
  echo "$o exit=$? · $(grep -E '^OK|^FALHOU' /tmp/$o.out | head -1)"
done
```
Esperado: os três com `exit=0`.

---

## O que este plano NÃO faz (e por quê)

Declarado para ninguém achar que está coberto:

- **Não mexe na TELA.** Tudo é pelo chat. A paridade no redesign é outro plano.
- **Não fecha venda** (`closed_won`). Vira MRR e contrato — decisão do dono, com porta própria.
- **Não resolve os 736 produtos sem NCM** nem os 29 com código inválido (Task de outro plano; a lista já existe via `sugerir_ncm_produtos.py --conferir`).
- **Não persiste o arquivo** de foto/vídeo — hoje guarda o que a visão descreveu, que é o que serve no relatório. Guardar o binário no GED é obra separada.
- **Não testa pelo WhatsApp real.** Todos os oráculos são in-process. A lente de campo — telefone do Jordan mandando foto de verdade — continua aberta e é a que mais importa para o fluxo de visita.
