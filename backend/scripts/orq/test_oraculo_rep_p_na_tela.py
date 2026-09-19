"""Oráculo: a tela do AFD não mente sobre o instrumento legal do REP-P.

Nasceu em 19/09/2026, junto com a superfície que ele vigia — a regra da casa é que toda tela
nova nasce vigiada, e eu tinha acabado de quebrá-la criando `rep-p-instrumento` sem oráculo.

O que se trava aqui não é a existência da tela (isso `checar_nao_vigiado` já cobraria), é a
COERÊNCIA entre três coisas que precisam contar a mesma história:

  1. `rep_instrumento_legal` no banco — o que de fato está registrado;
  2. o aviso na tabela do AFD — «⚠️ INSTRUMENTO LEGAL INCOMPLETO — falta …»;
  3. o formulário `rep-p-instrumento` — o botão que resolve o aviso.

Por que isto importa mais que parecer: o nome do arquivo AFD carrega o número do INPI
(Anexo I da Portaria 671). Sem o instrumento, ele sai como `AFDSEM_INPI<cnpj>REP_P.txt` e é
recusado numa fiscalização. Uma tela que esconde essa falta faz alguém entregar um arquivo
que não vale; uma que alarma sem motivo ensina a ignorar o alarme. As duas quebram a mesma
confiança, então o oráculo afirma nos DOIS sentidos.

Afirma a REGRA, não a fotografia: vale com o instrumento vazio (o caso de hoje) e vale
depois que o Jordan registrar os três. READ-ONLY — não grava instrumento nenhum.

Roda no container (PYTHONPATH=/app).
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402

SLUG_FORM = "rep-p-instrumento"
SLUG_TABELA = "afd"
ROTA = "/api/v1/people-management/ponto/afd/rep-p/instrumento"
TIPOS = ("INPI", "ATESTADO_TECNICO", "TERMO_RESPONSABILIDADE")


async def main() -> None:
    # Chama a função que monta ESTAS duas telas, não o builder inteiro: é o mesmo código que
    # o servidor executa e custa segundos em vez de montar as 81 telas do DP.
    from modules.operacional.controllers.redesign_builders.departamento_pessoal import (
        _afd_e_justificativa,
    )

    async with async_session_factory() as db:
        registrados = {r[0] for r in (await db.execute(text("SELECT tipo FROM rep_instrumento_legal"))).all()}
        faltam = [t for t in TIPOS if t not in registrados]

        out: dict = {}
        await _afd_e_justificativa(db, out)

        # 1 · o botão existe e aponta para a rota que grava
        form = out.get(SLUG_FORM)
        assert form, (
            f"a tela '{SLUG_FORM}' sumiu do DP — sem ela o aviso do AFD volta a apontar um "
            "defeito sem oferecer saída, e o número do INPI só entra por SQL na mão. "
            "⚠️ `safe()` ENGOLE exceção: uma tela que some assim não dá erro em lugar nenhum."
        )
        endpoint = ((form.get("submit") or {}).get("endpoint")) or ""
        assert endpoint == ROTA, f"o formulário aponta para {endpoint!r}, não para {ROTA!r}"
        campos = {f.get("key") for f in (form.get("fields") or [])}
        assert {"tipo", "data_emissao"} <= campos, f"faltam campos obrigatórios no formulário: {campos}"

        # 2 · o aviso do AFD conta a MESMA história do banco, nos dois sentidos
        afd = out.get(SLUG_TABELA)
        assert afd, "a tabela do AFD sumiu do DP — é a tela que a fiscalização pede primeiro"
        sub = str(afd.get("sub") or "")
        alarmou = "INSTRUMENTO LEGAL INCOMPLETO" in sub

        if faltam:
            assert alarmou, (
                f"faltam {faltam} em rep_instrumento_legal e a tela do AFD NÃO avisa — quem "
                "baixar o arquivo entrega um AFD com «SEM_INPI» no nome, recusado em "
                "fiscalização, sem nunca ter sido avisado."
            )
            for t in faltam:
                assert t in sub, f"o aviso não nomeia {t}: {sub[-180:]!r}"
        else:
            assert not alarmou, (
                "os três instrumentos estão registrados e a tela do AFD continua alarmando — "
                "alarme sem motivo é o que ensina todo mundo a ignorar alarme."
            )

        print(f"OK 1 · botão '{SLUG_FORM}' existe e grava em {ROTA}")
        print(
            f"OK 2 · tela e banco contam a mesma história: "
            f"{len(registrados)}/3 registrado(s), aviso {'ligado' if alarmou else 'desligado'}"
            + (f", nomeando {', '.join(faltam)}" if faltam else "")
        )
    print("TEST oraculo_rep_p_na_tela PASS")


if __name__ == "__main__":
    asyncio.run(main())
