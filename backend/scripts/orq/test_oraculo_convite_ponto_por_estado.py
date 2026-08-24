"""Quem JA tem conta nao recebe convite de primeiro acesso — recebe COMO ENTRAR.

Por que existe: em 23/08/2026 a Erika e a Kelly receberam "faca seu primeiro acesso:
1) CPF ... 3) cadastre seu rosto". As duas tinham conta E rosto desde 21/07 e 12/08.
E a tela de /login pede E-MAIL e senha — a mensagem nao dizia o e-mail em lugar nenhum,
entao elas cairiam no login sem saber o que digitar.

Agravante medido no mesmo dia: 20 funcionarios ativos tem DUAS contas, a pessoal (ativa)
e uma @conectamais.pro (INATIVA, sobra da carga inicial). Quem tentar a corporativa nao
entra. Por isso o oraculo exige o e-mail da conta ATIVA dentro da mensagem, nao um
generico "seu e-mail".

Afirma a REGRA, nao a fotografia: escolhe as pessoas por ESTADO (tem rosto / nao tem),
nunca por nome — quem sai da empresa nao pode quebrar o teste.
"""

import asyncio
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database.session import SyncSessionLocal  # noqa: E402
from modules.people_management.human_resources.controllers.ativacao_ponto_controller import (  # noqa: E402
    _disparar,
    _msg_login_texto,
    _msg_texto,
)

_SQL_COM_CONTA = """
SELECT CAST(e.id AS TEXT) AS id, e.nome,
       (SELECT u.email FROM users u
         WHERE CAST(u.employee_id AS TEXT)=CAST(e.id AS TEXT) AND u.is_active
         ORDER BY u.last_login DESC NULLS LAST LIMIT 1) AS email_login
FROM employees e
WHERE e.status='ativo' AND coalesce(e.is_homologacao,false)=false
  AND (e.tipo_contrato='clt' OR e.tipo_contrato IS NULL)
  AND e.face_descriptor IS NOT NULL
  AND EXISTS (SELECT 1 FROM users u
               WHERE CAST(u.employee_id AS TEXT)=CAST(e.id AS TEXT) AND u.is_active)
ORDER BY e.nome LIMIT 1
"""

_SQL_SEM_ROSTO = """
SELECT CAST(id AS TEXT) AS id, nome FROM employees
WHERE status='ativo' AND coalesce(is_homologacao,false)=false
  AND (tipo_contrato='clt' OR tipo_contrato IS NULL)
  AND face_descriptor IS NULL
ORDER BY nome LIMIT 1
"""


async def main() -> None:
    db = SyncSessionLocal()
    try:
        com = db.execute(text(_SQL_COM_CONTA)).mappings().first()
        assert com, "pre-condicao: nenhum ativo com rosto e conta ativa"

        # dry_run NAO envia nada — so devolve a decisao de rota/mensagem.
        r = await _disparar(db, [com["id"]], ["email", "whatsapp"], dry_run=True)
        alvo = r["resultados"][0]
        assert alvo["modo"] == "login", (
            f"{com['nome']} tem conta e rosto e ainda receberia primeiro acesso (modo={alvo['modo']})"
        )
        assert alvo["link"].endswith("/login"), f"link errado: {alvo['link']}"
        print(f"OK  quem tem conta vai pro /login  ({com['nome'][:28]})")

        # A mensagem tem que dizer O E-MAIL DA CONTA ATIVA — a tela de login pede e-mail.
        msg = _msg_login_texto(com["nome"], com["email_login"], alvo["link"])
        assert com["email_login"] in msg, "a mensagem nao diz o e-mail da conta ativa"
        assert "CPF" in msg, "a mensagem nao diz que a senha e o CPF"
        print(f"OK  mensagem carrega o e-mail da conta ativa  ({com['email_login']})")

        # Suspenders: o defeito exato foi MANDAR cadastrar rosto e fazer os 3 passos.
        # A mensagem pode citar o rosto — desde que para dizer que NAO precisa.
        # tira o negrito do WhatsApp: "*não* precisa" tem que casar com "não precisa"
        baixo = msg.lower().replace("*", "")
        assert "cadastre seu rosto" not in baixo, "voltou a mandar cadastrar o rosto"
        assert "3 passos" not in baixo and "são 3 passos" not in baixo, (
            "voltou a mandar os 3 passos do primeiro acesso a quem ja tem conta"
        )
        if "primeiro acesso" in baixo:
            assert "não precisa" in baixo, "cita primeiro acesso sem dizer que a pessoa NAO precisa fazer"
        print("OK  nao manda cadastrar rosto nem refazer o primeiro acesso")

        # E o outro lado da regra: quem NAO tem rosto continua indo pro primeiro acesso.
        sem = db.execute(text(_SQL_SEM_ROSTO)).mappings().first()
        if sem:
            r2 = await _disparar(db, [sem["id"]], ["email"], dry_run=True)
            a2 = r2["resultados"][0]
            assert a2["modo"] == "primeiro_acesso", f"{sem['nome']} nao tem rosto e deixou de receber o primeiro acesso"
            assert a2["link"].endswith("/primeiro-acesso"), f"link errado: {a2['link']}"
            assert "rosto" in _msg_texto(sem["nome"], a2["link"]).lower()
            print(f"OK  quem nao tem rosto continua no /primeiro-acesso  ({sem['nome'][:28]})")
        else:
            print("--  nenhum ativo sem rosto hoje: o outro lado da regra nao foi exercido")
    finally:
        db.close()

    print("TEST oraculo_convite_ponto_por_estado PASS")


if __name__ == "__main__":
    asyncio.run(main())
