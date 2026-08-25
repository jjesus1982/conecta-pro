"""/identificar tem que AVISAR quando a pessoa ja concluiu — a tela depende desse aviso.

Por que existe: a KELLY tinha rosto cadastrado desde 12/08 e mesmo assim foi levada ao
passo de cadastrar o rosto, onde a captura deu erro. O backend avisava: respondia 200 com
`ja_concluiu: true` e `ja_tem_rosto: true`. A tela ignorava os dois campos e seguia para o
passo 2.

Sao DUAS portas para a mesma armadilha e eu so tinha fechado uma: o EDIWILSON levava 409
(recusa explicita) e a KELLY recebia 200 com aviso no corpo. Quem so trata o 409 conserta
metade.

Este oraculo trava o CONTRATO de que a tela depende. Se alguem remover os campos ou parar
de preenche-los, a tela volta a mandar gente cadastrar rosto que ja existe — e o oraculo
reprova antes.

Afirma a REGRA: escolhe por ESTADO (quem tem rosto e concluiu), nunca por nome.
"""

import asyncio
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database.session import SyncSessionLocal  # noqa: E402
from modules.people_management.employee_portal.controllers import (  # noqa: E402
    primeiro_acesso_controller as pa,
)


async def main() -> None:
    db = SyncSessionLocal()
    try:
        pronto = (
            db.execute(
                text(
                    "SELECT regexp_replace(coalesce(cpf,''),'\\D','','g') AS cpf, nome "
                    "FROM employees "
                    "WHERE status='ativo' AND coalesce(is_homologacao,false)=false "
                    "  AND face_descriptor IS NOT NULL AND primeiro_acesso_em IS NOT NULL "
                    "  AND coalesce(cpf,'') <> '' "
                    "ORDER BY nome LIMIT 1"
                )
            )
            .mappings()
            .first()
        )
        assert pronto, "pre-condicao: ninguem com rosto e primeiro acesso concluido"

        r = pa.identificar(pa.IdentificarBody(cpf=pronto["cpf"]), db=db)

        assert r.get("ja_tem_rosto") is True, (
            f"{pronto['nome']} tem rosto no banco e /identificar nao avisa — a tela vai manda-la cadastrar de novo"
        )
        print(f"OK  avisa ja_tem_rosto  ({pronto['nome'][:28]})")

        assert r.get("ja_concluiu") is True, f"{pronto['nome']} ja concluiu o primeiro acesso e /identificar nao avisa"
        print("OK  avisa ja_concluiu")

        # A tela mostra o e-mail do login nesse aviso — sem ele a pessoa chega no /login
        # sem saber o que digitar (20 pessoas tem tambem uma @conectamais.pro inativa).
        assert r.get("email"), "a resposta nao traz o e-mail — a tela nao tem o que exibir"
        print(f"OK  traz o e-mail do login  ({r['email']})")
    finally:
        db.close()

    print("TEST oraculo_primeiro_acesso_avisa_concluido PASS")


if __name__ == "__main__":
    asyncio.run(main())
