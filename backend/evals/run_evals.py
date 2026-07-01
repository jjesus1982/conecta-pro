"""Evals enxutos do José Luís — golden-set rodado ANTES de cada deploy do agente.

Roda cada conversa do golden_set.json pelo agente REAL (gerar_resposta: modelo + prompt +
schemas de tools reais), com as EXECUÇÕES de tool stubadas (zero efeito colateral: não envia
WhatsApp, não alerta, não grava lead). Avalia cada resposta com:
  • checagens determinísticas (forbid/require_any/expect_tool/forbid_tool)
  • juiz-IA (LLM-as-judge) contra o critério do caso

Uso (dentro do container):
  docker exec -w /app -e PYTHONPATH=/app conecta-pro-backend python evals/run_evals.py
Sai com código !=0 se QUALQUER caso 'critical' falhar (serve de gate de deploy).
"""
import asyncio
import json
import os
import re
import sys

from sqlalchemy import text

import modules.integrations.connectors.whatsapp.agent_service as A
from core.database.session import async_session_factory

HERE = os.path.dirname(os.path.abspath(__file__))
JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL", "gpt-5.1")
BASE_CONV = 970000
TEST_PHONE = "5592970009999"  # não-owner, last-8 = 92970009999[-8:] -> usado no fixture

# Respostas canônicas das tools (stub) — plausíveis o bastante p/ o agente seguir o fluxo.
CANNED = {
    "buscar_cliente": {"existe": False},
    "consultar_cnpj": {"razao_social": "CONDOMINIO TESTE LTDA", "situacao": "ATIVA",
                       "municipio": "Manaus", "uf": "AM", "cnae": "8111-7/00"},
    "registrar_lead": {"ok": True},
    "listar_materiais": {"materiais": [{"nome_arquivo": "catalogo_conectamais.pdf", "tipo": "pdf"},
                                       {"nome_arquivo": "video_portaria.mp4", "tipo": "video"}]},
    "enviar_material": {"ok": True, "enviado": "catalogo_conectamais.pdf"},
    "enviar_link_assinatura": {"ok": True, "enviado": True, "number": "PROP-TESTE",
                               "instrucao": "O link JÁ foi enviado. NÃO repita o link, só uma frase curta."},
    "consultar_minha_conta": {"contratos": [], "ordens_servico": [], "notas": []},
    "agendar_visita": {"ok": True, "detalhe": "solicitação registrada"},
    "consultar_agenda": {"horarios_livres": ["09:00", "14:00"]},
    "transferir_conversa": {"ok": True, "setor": "comercial"},
    "abrir_ordem_servico": {"ok": True, "os": "OS-9999"},
    "sugerir_cross_sell": {"sugestao": None},
}

TOOL_CALLS: list[tuple[str, dict]] = []


async def _recorder(name, args, conversation_id):  # substitui A._exec_tool (cliente)
    TOOL_CALLS.append((name, args or {}))
    # Espelha a TRAVA real do enviar_link_assinatura: só "envia" se o cliente pediu explicitamente.
    # (Sem isso, o stub devolvia sucesso e o agente alucinava ter mandado — diferente de produção.)
    if name == "enviar_link_assinatura":
        from modules.crm.services.followups import pede_assinatura  # noqa: PLC0415
        async with async_session_factory() as db:
            li = (await db.execute(text(
                "SELECT content FROM cwi_message_log WHERE chatwoot_conversation_id=:c "
                "AND direction='in' ORDER BY id DESC LIMIT 1"), {"c": conversation_id})).first()
        if not pede_assinatura(li[0] if li else None):
            return {"ok": False, "nao_pediu": True,
                    "instrucao": "O cliente NÃO pediu o link — NÃO envie. Diga que pode deixar pronto "
                                 "pra assinatura quando ele quiser. O Jordan será avisado e decide."}
    return CANNED.get(name, {"ok": True})


async def _seed(db, conv, phone, history, user):
    msgs = list(history or []) + [["in", user]]
    for i, (role, txt) in enumerate(msgs):
        await db.execute(text(
            "INSERT INTO cwi_message_log (direction, phone_canonical, chatwoot_conversation_id, "
            "content, status, created_at) VALUES (:d,:p,:c,:t,'recv', now() + make_interval(secs => :i))"),
            {"d": role, "p": phone, "c": conv, "t": txt, "i": i})
    await db.commit()


async def _teardown(db, conv, phone):
    await db.execute(text("DELETE FROM cwi_message_log WHERE chatwoot_conversation_id=:c"), {"c": conv})
    await db.execute(text("DELETE FROM crm_followups WHERE phone_canonical=:p AND template='eval'"), {"p": phone})
    await db.commit()


def _check_deterministico(case, resposta, tool_names):
    falhas = []
    for rgx in case.get("forbid", []):
        if re.search(rgx, resposta or "", re.IGNORECASE):
            falhas.append(f"continha padrão proibido /{rgx}/")
    req = case.get("require_any")
    if req and not any(s.lower() in (resposta or "").lower() for s in req):
        falhas.append(f"não citou nenhum de {req}")
    et = case.get("expect_tool")
    if et and et not in tool_names:
        falhas.append(f"não chamou a ferramenta esperada '{et}' (chamou: {tool_names or 'nenhuma'})")
    for ft in case.get("forbid_tool", []):
        if ft in tool_names:
            falhas.append(f"chamou ferramenta proibida '{ft}'")
    return falhas


async def _judge(client, case, resposta):
    sys_p = ("Você é um auditor rígido de qualidade de um agente de atendimento por WhatsApp de uma "
             "empresa de segurança (Conecta Mais). Avalie SE a resposta do agente cumpre o CRITÉRIO. "
             "Seja exigente: qualquer violação do que é proibido = reprovado. Responda em JSON "
             '{"pass": true|false, "score": 0-10, "reason": "curto"}.')
    usr_p = (f"CRITÉRIO (o que é certo e o que é proibido):\n{case['criteria']}\n\n"
             f"RESPOSTA DO AGENTE:\n\"\"\"{resposta}\"\"\"\n\n"
             "A resposta cumpre o critério sem violar nenhuma proibição?")
    try:
        r = await client.chat.completions.create(
            model=JUDGE_MODEL,
            messages=[{"role": "system", "content": sys_p}, {"role": "user", "content": usr_p}],
            response_format={"type": "json_object"},
        )
        d = json.loads(r.choices[0].message.content or "{}")
        return bool(d.get("pass")), int(d.get("score", 0)), str(d.get("reason", ""))[:200]
    except Exception as e:  # noqa: BLE001
        return False, 0, f"juiz falhou: {e}"


async def main():
    with open(os.path.join(HERE, "golden_set.json"), encoding="utf-8") as f:
        cases = json.load(f)

    # stub das execuções de tool (zero efeito colateral)
    A._exec_tool = _recorder

    # fixture de acompanhamento: uma proposta real 'sent' p/ vincular ao telefone de teste
    prop_id = None
    async with async_session_factory() as db:
        r = (await db.execute(text(
            "SELECT id FROM proposals WHERE status IN ('sent','viewed') AND is_active=true "
            "ORDER BY created_at DESC LIMIT 1"))).first()
        prop_id = str(r[0]) if r else None

    from openai import AsyncOpenAI  # noqa: PLC0415
    client = AsyncOpenAI()

    resultados = []
    for idx, case in enumerate(cases):
        conv = BASE_CONV + idx
        phone = TEST_PHONE
        TOOL_CALLS.clear()
        async with async_session_factory() as db:
            await _teardown(db, conv, phone)  # limpa resíduo
            if case.get("fixture") == "acompanhamento" and prop_id:
                await db.execute(text(
                    "INSERT INTO crm_followups (phone_canonical, proposal_id, canal, template, status, "
                    "enviado_em, created_at, updated_at) VALUES (:p,:pid,'whatsapp','eval','enviado', "
                    "now(), now(), now())"), {"p": phone, "pid": prop_id})
                await db.commit()
            await _seed(db, conv, phone, case.get("history"), case["user"])

        try:
            resposta = await A.gerar_resposta(conv)
        except Exception as e:  # noqa: BLE001
            resposta = None
            print(f"  [{case['id']}] ERRO ao gerar: {e}")
        tool_names = [n for n, _ in TOOL_CALLS]

        async with async_session_factory() as db:
            await _teardown(db, conv, phone)

        if not resposta:
            resultados.append({"id": case["id"], "ok": False, "score": 0,
                               "reason": "resposta vazia/erro", "crit": case.get("critical", False),
                               "tools": tool_names, "resp": ""})
            continue

        det = _check_deterministico(case, resposta, tool_names)
        if det:
            resultados.append({"id": case["id"], "ok": False, "score": 0, "reason": "; ".join(det),
                               "crit": case.get("critical", False), "tools": tool_names, "resp": resposta})
            continue
        jp, js, jr = await _judge(client, case, resposta)
        resultados.append({"id": case["id"], "ok": jp, "score": js, "reason": jr,
                           "crit": case.get("critical", False), "tools": tool_names, "resp": resposta})

    # ---- relatório ----
    print("\n" + "=" * 80)
    print("EVALS JOSÉ LUÍS — golden-set")
    print("=" * 80)
    passou = sum(1 for r in resultados if r["ok"])
    crit_fail = [r for r in resultados if not r["ok"] and r["crit"]]
    for r in resultados:
        ic = "✅" if r["ok"] else ("❌" if r["crit"] else "⚠️ ")
        tag = " [CRÍTICO]" if (r["crit"] and not r["ok"]) else ""
        print(f"{ic} {r['id']:22} nota {r['score']}/10{tag}")
        if not r["ok"]:
            print(f"     motivo: {r['reason']}")
            print(f"     resp:   {(r['resp'] or '')[:160].replace(chr(10),' ')}")
            if r["tools"]:
                print(f"     tools:  {r['tools']}")
    print("-" * 80)
    media = round(sum(r["score"] for r in resultados) / max(1, len(resultados)), 1)
    print(f"PASSOU {passou}/{len(resultados)} | nota média {media}/10 | "
          f"críticos reprovados: {len(crit_fail)}")
    print("=" * 80)
    sys.exit(1 if crit_fail else 0)


if __name__ == "__main__":
    asyncio.run(main())
