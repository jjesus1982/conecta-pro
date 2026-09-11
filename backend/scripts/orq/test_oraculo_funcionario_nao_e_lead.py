"""Oráculo — quem é da casa não vira lead nem ouve "me confirma o CNPJ" (11/09/2026).

Origem, medida nas 2.074 mensagens do José Luís: dos 98 números que falaram com ele **64 são
de funcionários**, e 25 deles estavam cadastrados como LEAD. O `agent_service.py` tinha 7.379
linhas e ZERO consultas a `employees`: o único caminho de identidade na entrada era
`_match_or_create_lead`, que ou casa um lead ou cria um. O retrato do defeito é a conversa do
Rene em 10/09 — a automação de SAÍDA sabia o turno e o condomínio dele; a de ENTRADA pediu o
CNPJ de um porteiro.

Este oráculo afirma a REGRA, não a fotografia:

  1. Telefone que resolve a um funcionário ativo devolve `tipo='funcionario'` e `e_da_casa`.
  2. O papel `funcionario` existe e seu conjunto de ferramentas NÃO contém nada de venda nem
     conta de cliente. Papel é parede, não sugestão.
  3. O prompt desse papel NÃO é o prompt de vendas. Medido em 11/09: com a instrução apenas
     ADITIVA, o modelo resolveu o ponto do Rene e ainda pediu o CNPJ dele no fim.
  4. Nenhum LEAD novo (criado a partir de 11/09/2026) tem telefone de funcionário ativo. Os
     anteriores são a dívida conhecida — o que não pode é CRESCER.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date

#: o dia em que a entrada passou a enxergar funcionário. CAST no SQL, sempre: asyncpg
#: recusa parâmetro sem tipo declarado — e COM o CAST passa a exigir um `date` de verdade,
#: nunca a string. As duas metades da mesma lição (§103 do kit); só o par funciona.
CORTE = "2026-09-11"

#: nada disso pertence a uma conversa com gente da casa
PROIBIDAS_NO_PAPEL = ("registrar_lead", "simular_preco", "montar_proposta",
                      "consultar_minha_conta", "enviar_link_assinatura", "agendar_visita")


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db
    from modules.integrations.connectors.whatsapp.agent_service import (
        _PAPEIS,
        SYSTEM_PROMPT,
        _system_prompt,
        _tools_ativas,
    )
    from modules.integrations.connectors.whatsapp.identidade import SEM_VINCULO, quem_e

    falhas: list[str] = []
    gen = get_db()
    db = await gen.__anext__()

    # 1) o telefone de quem é da casa resolve a funcionário
    # ⚠️ era `LIMIT 20` — amostra decidindo veredito. Com 65 ativos ela acerta quase sempre e
    # cala exatamente sobre os que ficaram de fora do corte: o funcionário 21 poderia voltar a
    # ser lead sem este oráculo dizer nada. Medir o conjunto inteiro custa 45 linhas a mais de
    # consulta; supor que a amostra representa custa o oráculo inteiro (11/09/2026).
    fones = [r[0] for r in (await db.execute(text(
        "SELECT coalesce(nullif(celular,''), telefone) FROM employees "
        " WHERE coalesce(status,'ativo') = 'ativo' "
        "   AND length(regexp_replace(coalesce(nullif(celular,''),telefone,''),'[^0-9]','','g')) >= 10 "))).fetchall()]
    sem_identidade = 0
    for f in fones:
        ident = await quem_e(db, f)
        if ident.tipo != "funcionario" or not ident.e_da_casa:
            falhas.append(f"telefone de funcionário ativo resolveu como '{ident.tipo}' — viraria lead")
        elif not ident.employee_id:
            # da casa mas sem QUEM: é o estado de ambiguidade, e ele é correto — só não pode
            # passar despercebido, porque essa pessoa perde as ferramentas de ponto.
            sem_identidade += 1

    # 5) chave de telefone que casa com mais de uma pessoa. Não é falha do código: é cadastro
    # que precisa de mão, e enquanto durar há gente sem acesso ao próprio ponto pelo WhatsApp.
    # o MESMO filtro de `_SQL_FUNCIONARIO` (`<> 'inativo'`, não `= 'ativo'`): trava que mede
    # um conjunto diferente do código que ela vigia é a versão silenciosa de não medir nada.
    ambiguos = (await db.execute(text(
        "SELECT count(*) FROM (SELECT right(regexp_replace(coalesce(nullif(celular,''),telefone,''),"
        "  '[^0-9]','','g'),8) k FROM employees "
        " WHERE lower(coalesce(status,'ativo')) <> ALL(:sem_vinculo) "
        "   AND length(regexp_replace(coalesce(nullif(celular,''),telefone,''),'[^0-9]','','g')) >= 8 "
        " GROUP BY 1 HAVING count(*) > 1) x"), {"sem_vinculo": list(SEM_VINCULO)})).scalar() or 0
    if ambiguos:
        falhas.append(f"{ambiguos} chave(s) de telefone casam com MAIS DE UM funcionário ativo — "
                      "essas pessoas ficam sem ferramenta de ponto (identidade ambígua, e o "
                      "sistema se recusa a escolher). Corrigir o cadastro.")

    # 2) o papel é uma parede
    cfg = _PAPEIS.get("funcionario")
    if not cfg:
        falhas.append("o papel 'funcionario' sumiu de _PAPEIS — todo funcionário volta a ser SDR")
    else:
        tools = {t["function"]["name"] for t in _tools_ativas(False, "funcionario")}
        for proibida in PROIBIDAS_NO_PAPEL:
            if proibida in tools:
                falhas.append(f"o papel 'funcionario' enxerga '{proibida}' — é ferramenta de cliente")
        if "meu_ponto_hoje" not in tools:
            falhas.append("o papel 'funcionario' perdeu `meu_ponto_hoje` — responderia ponto no chute")

    # 3) o prompt dele não é o de vendas
    p = _system_prompt(False, "funcionario")
    if SYSTEM_PROMPT[:400] in p:
        falhas.append("o papel 'funcionario' voltou a carregar o SYSTEM_PROMPT de vendas — "
                      "foi assim que o Rene levou 'me confirma o CNPJ' depois do ponto resolvido")
    if "NUNCA peça CNPJ" not in p:
        falhas.append("sumiu a regra explícita de não pedir CNPJ ao funcionário")

    # 4) nenhum lead NOVO com telefone de funcionário
    novos = (await db.execute(text(
        "SELECT l.name, l.phone FROM leads l JOIN employees e "
        "  ON right(regexp_replace(coalesce(l.phone,''),'[^0-9]','','g'),8) "
        "   = right(regexp_replace(coalesce(nullif(e.celular,''),e.telefone,''),'[^0-9]','','g'),8) "
        " WHERE l.created_at >= CAST(:corte AS date) "
        "   AND length(regexp_replace(coalesce(nullif(e.celular,''),e.telefone,''),'[^0-9]','','g')) >= 10 "
        "   AND coalesce(e.status,'ativo') = 'ativo'"), {"corte": date.fromisoformat(CORTE)})).fetchall()
    for nome, fone in novos:
        falhas.append(f"lead novo criado com telefone de funcionário: {nome} ({fone})")

    antigos = (await db.execute(text(
        "SELECT count(*) FROM leads l JOIN employees e "
        "  ON right(regexp_replace(coalesce(l.phone,''),'[^0-9]','','g'),8) "
        "   = right(regexp_replace(coalesce(nullif(e.celular,''),e.telefone,''),'[^0-9]','','g'),8) "
        " WHERE l.created_at < CAST(:corte AS date) "
        "   AND length(regexp_replace(coalesce(nullif(e.celular,''),e.telefone,''),'[^0-9]','','g')) >= 10"),
        {"corte": date.fromisoformat(CORTE)})).scalar()
    print(f"funcionários conferidos: {len(fones)} (TODOS os ativos com telefone) · "
          f"identidade ambígua: {sem_identidade} · "
          f"leads-funcionário ANTES do corte (dívida conhecida): {antigos}")
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s): funcionário voltando a ser tratado como lead")
    print("OK: funcionário é identificado pelo telefone, tem papel próprio e não vira lead")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
