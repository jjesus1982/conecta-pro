"""Acha conta de acesso amarrada à pessoa ERRADA. READ-ONLY — só relata.

POR QUE EXISTE — 25/09/2026. O Antonio Carlos Castro Gama relatou TRÊS vezes (17/09, 19/09 e
25/09) que o app do ponto mostrava a tela da "Graciene". A causa não estava no aparelho dele: a
conta da GRACIENE PEREIRA DE CASTRO está no e-mail `eliaelkalebecastroaraujo@gmail.com` — e o
Jordan confirmou que **Eliael Kalebe Castro Araújo não é mais funcionário, nem CLT nem diarista**.
Uma pessoa que saiu da empresa é o login de uma pessoa que está ativa.

⚠️ A PRIMEIRA RÉGUA QUE EU ESCREVI NÃO SERVIA. Ela procurava "e-mail que não contém o primeiro
nome" e devolveu 14 casos, dos quais **12 eram falso positivo** — gente usa apelido e inicial:
`theusfallss` para Matheus, `kpdocs93` para Kelly Patrícia, `ng447391` para Nailson Garcia,
`santoslyce30` para Vanderlice Santos. Nenhum defeito. Se eu tivesse reportado os 14, mandaria o
dono conferir 12 cadastros corretos — a mesma armadilha do caçador que mede o regex, não o código.

AS QUATRO REGRAS QUE VALEM, e todas comparam o e-mail com O CADASTRO, não com uma expectativa
de formato:

  1. e-mail usado por MAIS DE UM funcionário          → dois entram na conta um do outro
  2. e-mail cujo nome é o nome de OUTRA pessoa da base → é o caso Graciene/Eliael
  3. e-mail de quem NÃO é mais funcionário             → ex-funcionário como login de ativo
  4. dois logins ATIVOS para o mesmo funcionário       → um deles ninguém controla

Uso:  docker exec -e PYTHONPATH=/app conecta-pro-backend \
          python3 /app/scripts/qa/auditar_identidade_contas.py
"""

from __future__ import annotations

import asyncio
import re
import sys
import unicodedata

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402


def _n(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().upper()
    return " ".join(s.split())


def e_o_proprio_nome(email: str, nome: str) -> bool:
    """O e-mail é da própria pessoa, em QUALQUER ordem?

    ⚠️ A 2ª versão desta régua comparava substring na MESMA ORDEM e errou 4 de 6:
    `souzadasilvaalexandre96` É o Alexandre Souza da Silva, `mauriciochagaschagas466` É o
    Mauricio Chagas, `oscarsoarescostafilho` É o Oscar Soares da Costa Filho. Gente escreve o
    próprio nome fora de ordem, dobrado e sem preposição.

    Regra que aguenta: se a MAIORIA dos tokens do nome (4+ letras) aparece nas letras do e-mail,
    é dele. Não exige ordem, não exige completude.
    """
    letras = re.sub(r"[^a-z]", "", (email or "").split("@")[0].lower())
    toks = [t for t in _n(nome).lower().split() if len(t) >= 4]
    if not toks or not letras:
        return False
    achados = sum(1 for t in toks if t in letras)
    return achados >= max(2, (len(toks) + 1) // 2)


async def main() -> None:
    achados: list[tuple[str, str]] = []
    async with async_session_factory() as db:
        pessoas = (await db.execute(text("""
            SELECT e.id::text AS id, e.nome, coalesce(e.status,'') AS status
            FROM employees e"""))).mappings().all()
        contas = (await db.execute(text("""
            SELECT u.id::text AS uid, lower(coalesce(u.email,'')) AS email, u.is_active,
                   u.employee_id::text AS eid, e.nome AS dono, coalesce(e.status,'') AS status
            FROM users u LEFT JOIN employees e ON e.id = u.employee_id
            WHERE coalesce(u.email,'') <> ''"""))).mappings().all()

        # 1 — mesmo e-mail em mais de um funcionário
        por_email: dict[str, set[str]] = {}
        for c in contas:
            if c["eid"]:
                por_email.setdefault(c["email"], set()).add(c["dono"] or c["eid"])
        for email, donos in por_email.items():
            if len(donos) > 1:
                achados.append(("🔴 MESMO E-MAIL, PESSOAS DIFERENTES",
                                f"{email} → {' | '.join(sorted(donos))}"))

        # 2 — o nome no e-mail é o de OUTRA pessoa da base (comparação contra o cadastro)
        nomes = [(p["nome"], _n(p["nome"]).replace(" ", "").lower(), p["status"]) for p in pessoas]
        for c in contas:
            if not c["eid"] or not c["is_active"]:
                continue
            local = c["email"].split("@")[0]
            so_letras = re.sub(r"[^a-z]", "", local)
            if len(so_letras) < 12:      # local curto (inicial+número) não é afirmação de nome
                continue
            if e_o_proprio_nome(c["email"], c["dono"]):
                continue                 # é o próprio dono, em qualquer ordem
            for nome, chave, st in nomes:
                if nome == c["dono"] or len(chave) < 14:
                    continue
                # o e-mail contém o nome COMPLETO de outra pessoa (14+ letras = não é coincidência)
                if chave[:18] in so_letras or so_letras in chave:
                    achados.append(("🔴 E-MAIL DE OUTRA PESSOA DO CADASTRO",
                                    f"conta de {c['dono']} usa {c['email']} — "
                                    f"é o nome de {nome} (status {st or '—'})"))
                    break

        # 3 — o nome do e-mail não existe em ninguém ATIVO (candidato a ex-funcionário)
        #     Só reporta quando o local part é longo o bastante para AFIRMAR um nome.
        nomes_ativos = [p["nome"] for p in pessoas
                        if p["status"] in ("ativo", "pj_ativo", "afastado_inss")]
        for c in contas:
            if not c["eid"] or not c["is_active"]:
                continue
            so_letras = re.sub(r"[^a-z]", "", c["email"].split("@")[0])
            if len(so_letras) < 18:
                continue
            if e_o_proprio_nome(c["email"], c["dono"]):
                continue
            if not any(e_o_proprio_nome(c["email"], a) for a in nomes_ativos):
                achados.append(("🟠 E-MAIL NÃO CORRESPONDE A NINGUÉM ATIVO",
                                f"conta de {c['dono']} usa {c['email']} — "
                                "nome não bate com nenhum funcionário ativo"))

        # 4 — dois logins ATIVOS para o mesmo funcionário
        por_pessoa: dict[str, list[str]] = {}
        for c in contas:
            if c["eid"] and c["is_active"]:
                por_pessoa.setdefault(f"{c['dono']}", []).append(c["email"])
        for dono, emails in por_pessoa.items():
            if len(emails) > 1:
                achados.append(("🟠 DOIS LOGINS ATIVOS PARA A MESMA PESSOA",
                                f"{dono} → {' | '.join(sorted(emails))}"))

        # CONTROLE — sem isto eu não sei se a régua está viva ou se a base é que é limpa
        print(f"varridos: {len(contas)} contas · {len(pessoas)} pessoas no cadastro\n")

    if not achados:
        print("nenhum achado — e a linha acima prova que a varredura rodou sobre dado real")
        return
    vistos: set[str] = set()
    for tipo, detalhe in sorted(achados):
        if detalhe in vistos:
            continue
        vistos.add(detalhe)
        print(f"{tipo}\n    {detalhe}")
    print(f"\nTOTAL: {len(vistos)} achado(s)")


if __name__ == "__main__":
    asyncio.run(main())
