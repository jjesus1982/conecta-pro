#!/usr/bin/env python3
"""🔒 Nenhuma rota do portal alcança dado pessoal de OUTRO funcionário.

Holerite, ASO, exame e dependente são o dado mais sensível do DP e não tinham oráculo de
escopo. A parede self-only foi fechada em 03/08 — o dispatcher injeta `current_user` nos
31 slugs — mas parede sem vigia é parede até o próximo `git push`.

**Vazamento não é bug: é incidente, e não se desfaz.** Não existe rollback para o holerite
de uma pessoa que outra já leu. Por isso este oráculo afirma o escopo por DOIS caminhos
independentes, e não por um só:

  (A) ESTRUTURAL — nenhuma das 152 rotas sob `/portal/` aceita identificador de terceiro no
      caminho (`employee_id`, `colaborador_id`, `cpf`). Quem não tem por onde pedir o dado
      de outro não vaza por engano de autorização; a identidade vem do token e ponto.
      Medido em 13/08: 0 de 152.
  (B) DE PONTA A PONTA — dois funcionários REAIS e diferentes chamam a MESMA rota de
      holerite com os tokens deles, e cada um recebe o próprio conjunto. Se a rota
      ignorasse o token e devolvesse o mesmo para os dois, (A) continuaria verde: (A) prova
      que não há por onde PEDIR o dado alheio, (B) prova que a rota não o ENTREGA sozinha.
      Uma sem a outra é meia parede — e meia parede em LGPD é parede nenhuma.
  (C) SEPARAÇÃO DE AUDIENCE — o portal exige token de audience `employee_portal`
      (`create_portal_access_token`), e um JWT de usuário do sistema, mesmo o do CEO com
      `all`, leva 401. Descobri isto errando: a primeira versão de (B) usava o JWT de admin
      e tomou 401, que eu quase reportei como "portal quebrado". Não estava quebrado — era
      a parede funcionando, e ela merece asserção própria: sem (C), alguém "conserta" o 401
      aceitando token de admin no portal e abre acesso a todo holerite de uma vez.

🔒 SÓ LEITURA, e só de quem já tem holerite publicado. O oráculo não cria usuário, não
publica documento e não lê o conteúdo dos holerites: compara os CONJUNTOS DE IDs que cada
token alcança. Provar escopo despejando dado pessoal no log da varredura seria causar o
incidente que ele existe para impedir.

Receita:
  docker exec -e PYTHONPATH=/app conecta-pro-backend \\
    python3 /app/scripts/orq/test_oraculo_lgpd_portal.py
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import sys

sys.path.insert(0, "/app")
logging.disable(logging.CRITICAL)

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from core.auth.jwt import create_access_token  # noqa: E402
from core.database.session import async_session_factory  # noqa: E402
from modules.people_management.employee_portal.auth import (  # noqa: E402
    create_portal_access_token,
)

BASE = "http://127.0.0.1:8080"
ROTA = "/api/v1/people-management/portal/my-payslips"
#: identificadores de PESSOA no caminho. `condominio_id` e afins não entram: escopo de
#: cliente é outra parede, e misturar as duas faria este oráculo acusar rota legítima.
DE_TERCEIRO = ("employee_id", "colaborador_id", "funcionario_id", "{cpf")


def _assinaturas(payload) -> set[str]:
    """Assinatura opaca de cada holerite devolvido: competência + hash curto do líquido.

    A resposta do portal NÃO traz `id` — traz `month`, `year` e valores. E só
    (month, year) não serve de identidade: todo mundo tem 07/2026, então dois funcionários
    diferentes teriam conjuntos "iguais" e o oráculo gritaria vazamento onde não há.

    O líquido entra HASHEADO. Ele distingue as pessoas, que é o que o teste precisa, e um
    hash não pode ser lido de volta — provar escopo despejando salário no log da varredura
    diária seria causar o incidente que este oráculo existe para impedir.
    """
    itens = payload if isinstance(payload, list) else (
        payload.get("items") or payload.get("data") or payload.get("payslips") or []
    )
    return {
        f"{i.get('month')}/{i.get('year')}:"
        f"{hashlib.sha256(str(i.get('net_salary')).encode()).hexdigest()[:12]}"
        for i in itens if isinstance(i, dict)
    }


async def _do_banco(db, employee_id: str) -> set[str]:
    """A MESMA assinatura, montada direto do banco — a verdade contra a qual a rota responde.

    Escrita aqui e não pedida à rota de propósito: comparar a resposta com ela mesma prova
    só que ela é consistente consigo, que é exatamente o que um vazamento também é.
    """
    linhas = (await db.execute(text(
        "SELECT reference_month AS m, reference_year AS a, net_salary AS v "
        "FROM hr_payslips WHERE employee_id = CAST(:e AS uuid) "
        "  AND status IN ('published','rectified','contested','paid')"
    ), {"e": employee_id})).mappings().all()
    return {
        f"{r['m']}/{r['a']}:{hashlib.sha256(str(float(r['v'])).encode()).hexdigest()[:12]}"
        for r in linhas
    }


async def main() -> int:
    falhas: list[str] = []

    from main_production import app  # noqa: PLC0415 — import caro

    # ── (A) estrutural ───────────────────────────────────────────────────────
    portal = [p for p in (getattr(r, "path", "") for r in app.routes) if "/portal/" in p]
    vazando = [p for p in portal if any(k in p for k in DE_TERCEIRO)]
    print(f"(A) rotas sob /portal/: {len(portal)} · com identificador de terceiro no "
          f"caminho: {len(vazando)}")
    for p in vazando:
        print(f"    ✗ {p}")
    if vazando:
        falhas.append(
            f"{len(vazando)} rota(s) do portal aceitam identificador de outra pessoa no "
            f"caminho — a identidade tem que vir do token, nunca do pedido"
        )
    if not portal:
        falhas.append("NENHUMA rota /portal/ encontrada — ou o prefixo mudou, ou o app não "
                      "montou. Verde por caminho errado é o pior tipo de verde")

    # ── (B) ponta a ponta, com duas pessoas reais e diferentes ───────────────
    async with async_session_factory() as db:
        # o portal identifica por EMPLOYEE, não por user do sistema — não exige login criado
        pessoas = (await db.execute(text(
            "SELECT e.id::text AS eid, e.nome AS nome, coalesce(e.cargo,'') AS cargo "
            "FROM employees e "
            "WHERE EXISTS (SELECT 1 FROM hr_payslips h WHERE h.employee_id = e.id "
            "          AND h.status IN ('published','rectified','contested','paid')) "
            "ORDER BY e.nome LIMIT 2"
        ))).mappings().all()
        ceo = (await db.execute(text(
            "SELECT id::text FROM users WHERE email = 'jjesus@conectamais.pro' LIMIT 1"
        ))).scalar()

    if len(pessoas) < 2:
        print(f"(B) NÃO VERIFICADO: achei {len(pessoas)} funcionário(s) com login e "
              f"holerite publicado; preciso de 2 diferentes")
        falhas.append("(B) NÃO VERIFICADO — sem duas pessoas, a comparação não prova escopo")
    else:
        alcance: list[tuple[str, set[str], set[str]]] = []
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as cli:
            for pes in pessoas:
                token = create_portal_access_token(pes["eid"], pes["nome"], pes["cargo"])
                r = await cli.get(ROTA, headers={"Authorization": f"Bearer {token}"})
                if r.status_code != 200:
                    falhas.append(f"(B) {pes['nome']} recebeu HTTP {r.status_code} em {ROTA} "
                                  f"— sem resposta não dá para comparar escopo")
                    continue
                async with async_session_factory() as db2:
                    seus = await _do_banco(db2, pes["eid"])
                recebeu = _assinaturas(r.json())
                alcance.append((pes["nome"], recebeu, seus))
                print(f"(B) {pes['nome']}: recebeu {len(recebeu)} · tem {len(seus)} no banco")

        if len(alcance) == 2:
            (n1, r1, b1), (n2, r2, b2) = alcance
            if not r1 and not r2:
                falhas.append(
                    "(B) INCONCLUSIVO: os dois receberam lista VAZIA. Escopo vazio não é "
                    "escopo provado — pode ser a parede ou pode ser a rota quebrada"
                )
            # o teste que importa: alguém recebeu holerite que pertence AO OUTRO
            for eu, meu, outro_nome, do_outro in ((n1, r1, n2, b2), (n2, r2, n1, b1)):
                invadido = meu & do_outro
                if invadido:
                    falhas.append(
                        f"🔒 VAZAMENTO: {eu} recebeu {len(invadido)} holerite(s) que "
                        f"pertencem a {outro_nome}"
                    )
            # e o complemento: recebeu tudo o que é seu, e nada além
            for nome, recebeu, seus in ((n1, r1, b1), (n2, r2, b2)):
                alheio = recebeu - seus
                if alheio:
                    falhas.append(
                        f"🔒 {nome} recebeu {len(alheio)} holerite(s) que NÃO estão entre "
                        f"os dele no banco — origem desconhecida, trate como vazamento"
                    )
                elif recebeu != seus:
                    print(f"(B) {nome}: recebeu {len(recebeu)} dos {len(seus)} dele "
                          f"(subconjunto — escopo não vaza; a falta é outro assunto)")
            if not falhas:
                print("(B) escopo íntegro: cada um recebeu só o próprio, nada do outro")

    # ── (C) token de admin não entra no portal ───────────────────────────────
    if not ceo:
        print("(C) NÃO VERIFICADO: não achei o usuário do CEO para testar a separação")
        falhas.append("(C) NÃO VERIFICADO — sem token de admin, a separação não foi provada")
    else:
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as cli:
            r = await cli.get(ROTA, headers={"Authorization": f"Bearer {create_access_token(ceo)}"})
        print(f"(C) JWT de usuário do sistema (CEO, permissão `all`) no portal: {r.status_code}")
        if r.status_code != 401:
            falhas.append(
                f"🔒 (C) token de ADMIN foi aceito no portal (HTTP {r.status_code}). A "
                f"audience `employee_portal` existe para que credencial administrativa NÃO "
                f"abra o holerite de funcionário — com ela aceita, abre o de todos de uma vez"
            )

    if falhas:
        for f in falhas:
            print(f"FALHA: {f}")
        print("TEST oraculo_lgpd_portal FAIL")
        return 1
    print("TEST oraculo_lgpd_portal PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
