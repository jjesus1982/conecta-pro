"""Curator da memória que aprende (5.5). Barra fabricação: memória não-ancorada
NÃO vira autoritativa. Reusa groundedness (número) + checagem de entidade real."""
from __future__ import annotations

import re

from sqlalchemy import text

from modules.ai.conversation.services.garantia import groundedness

_DIRETORIA = {"admin"}  # feedback permanente confiável


async def _entidades_existem(db, fato: str) -> tuple[bool, list[str]]:
    # extrai CNPJs citados; se citar CNPJ, tem que existir em clients/empresas
    cnpjs = re.findall(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}", fato)
    faltando = []
    for c in cnpjs:
        dig = re.sub(r"\D", "", c)
        row = (await db.execute(text(
            "SELECT 1 FROM clients WHERE regexp_replace(coalesce(document_number,''),'\\D','','g')=:d "
            "UNION SELECT 1 FROM empresas WHERE regexp_replace(coalesce(cnpj,''),'\\D','','g')=:d LIMIT 1"),
            {"d": dig})).first()
        if not row:
            faltando.append(c)
    return (len(faltando) == 0, faltando)


async def curar(db, *, fato: str, origem: str, fonte: str, autor_role: str,
                 fonte_conversa: dict) -> dict:
    veredito: dict = {"checks": {}}
    # 1) ancoragem numérica: números do fato têm que estar na fonte da conversa
    g = groundedness.verificar(fato, fonte_conversa or {})
    veredito["checks"]["numeros"] = g
    numeros_ok = g.get("ok", True)
    # 2) ancoragem de entidade
    ent_ok, faltando = await _entidades_existem(db, fato)
    veredito["checks"]["entidades"] = {"ok": ent_ok, "faltando": faltando}
    # 3) confiança
    autor_confiavel = (fonte == "feedback_gestor" and autor_role in _DIRETORIA)
    confidence = 1.0 if autor_confiavel else (0.8 if (numeros_ok and ent_ok) else 0.3)
    # 4) decisão: só ativa se ancorado (número+entidade) OU diretoria explícita
    if autor_confiavel or (numeros_ok and ent_ok):
        status = "ativo"
    else:
        status = "pendente_revisao"
    veredito["confidence"] = confidence
    return {"status": status, "confidence": confidence, "veredito": veredito}


# ─────────────────────────────────────────────────────────────────────────────
# TESTE-ÂNCORA (padrão 5.1: sem pytest, `python memoria_curator.py`, só asserts)
# Bancada throwaway: precisa de DB real (clients.document_number / empresas.cnpj)
# para checar ancoragem de entidade. Roda em container descartável, nunca contra
# o backend vivo.
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import asyncio

    from core.database.session import get_async_db_session

    async def _main() -> None:
        async with get_async_db_session() as db:
            # descobre um CNPJ real (empresas) e um CPF/CNPJ inexistente pra fixture
            row = (await db.execute(text(
                "SELECT cnpj FROM empresas WHERE cnpj IS NOT NULL LIMIT 1"))).first()
            assert row is not None, "precisa de ao menos 1 empresa com cnpj cadastrado na bancada"
            cnpj_real = row[0]
            cnpj_falso = "00.000.000/0001-00"
            # garante que o CNPJ falso realmente não existe em nenhuma das tabelas
            faker_check = (await db.execute(text(
                "SELECT 1 FROM clients WHERE regexp_replace(coalesce(document_number,''),'\\D','','g')=:d "
                "UNION SELECT 1 FROM empresas WHERE regexp_replace(coalesce(cnpj,''),'\\D','','g')=:d LIMIT 1"),
                {"d": re.sub(r"\D", "", cnpj_falso)})).first()
            assert faker_check is None, "fixture ruim: CNPJ 'falso' existe de verdade na bancada"

            fonte_conversa = {"saldo": "R$ 9.125,56", "postos": 7}

            # (a) número FORA da fonte -> pendente_revisao
            r_a = await curar(
                db,
                fato="O saldo da conta é R$ 50.000,00.",
                origem="cfo_ia",
                fonte="llm_destilado",
                autor_role="",
                fonte_conversa=fonte_conversa,
            )
            assert r_a["status"] == "pendente_revisao", f"(a) esperado pendente_revisao, veio {r_a}"
            assert r_a["veredito"]["checks"]["numeros"]["ok"] is False, r_a
            print("TESTE (a) [numero fora da fonte -> pendente_revisao] PASS:", r_a["status"])

            # (b) CNPJ inexistente -> pendente_revisao + faltando != []
            r_b = await curar(
                db,
                fato=f"A empresa cliente é o CNPJ {cnpj_falso}.",
                origem="cfo_ia",
                fonte="llm_destilado",
                autor_role="",
                fonte_conversa=fonte_conversa,
            )
            assert r_b["status"] == "pendente_revisao", f"(b) esperado pendente_revisao, veio {r_b}"
            assert r_b["veredito"]["checks"]["entidades"]["ok"] is False, r_b
            assert r_b["veredito"]["checks"]["entidades"]["faltando"] != [], r_b
            print("TESTE (b) [CNPJ inexistente -> pendente_revisao+faltando] PASS:", r_b["veredito"]["checks"]["entidades"])

            # (c) número da fonte + entidade real (sem entidade estranha) -> ativo
            r_c = await curar(
                db,
                fato=f"Temos 7 postos ativos para o CNPJ {cnpj_real}.",
                origem="cfo_ia",
                fonte="llm_destilado",
                autor_role="",
                fonte_conversa=fonte_conversa,
            )
            assert r_c["status"] == "ativo", f"(c) esperado ativo, veio {r_c}"
            print("TESTE (c) [ancorado numero+entidade -> ativo] PASS:", r_c["status"])

            # (d) autor diretoria (feedback_gestor + role admin) -> ativo mesmo sem número/entidade
            r_d = await curar(
                db,
                fato="O cliente prefere ser contatado só por WhatsApp, nunca por e-mail.",
                origem="cfo_ia",
                fonte="feedback_gestor",
                autor_role="admin",
                fonte_conversa=fonte_conversa,
            )
            assert r_d["status"] == "ativo", f"(d) esperado ativo (diretoria), veio {r_d}"
            assert r_d["confidence"] == 1.0, r_d
            print("TESTE (d) [autor diretoria -> ativo] PASS:", r_d["status"])

        print("\nTODOS OS TESTES DE memoria_curator.py PASSARAM")

    asyncio.run(_main())
