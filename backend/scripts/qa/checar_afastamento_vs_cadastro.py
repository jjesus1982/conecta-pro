#!/usr/bin/env python3
"""Afastamento aberto e cadastro dizendo outra coisa.

Origem: 17/09/2026. O dono avisou que a Cintia estava afastada e que não devíamos mandar
mensagem para ela. O sistema **já sabia**: `sst_afastamentos` tinha o acidente de trajeto de
21/05/2026, CID T07, CAT transmitida, estabilidade até 21/05/2027. O que não sabia era
`employees.status` — dizia `ativo` desde então, quatro meses.

Isso importa porque **todo disparo decide pelo cadastro**, não pelo afastamento:

    lembrete_ponto          AND e.status = 'ativo'
    aviso de assinatura     AND lower(status) IN ('ativo','afastado_inss','suspenso')
    recibo VT/VR do kit     AND lower(status) IN ('ativo','afastado_inss','suspenso')

Com o cadastro errado, quem está em casa há meses continua sendo cobrado, lembrado de bater
ponto e contado como gente em serviço. A última batida da Cintia foi 29/03; o lembrete de
ponto a alcançava mesmo assim.

O contrário também acusa: cadastro `afastado_inss`/`suspenso` sem nenhum afastamento aberto é
a outra metade da mesma mentira — alguém voltou e ninguém encerrou o registro.

    python3 backend/scripts/qa/checar_afastamento_vs_cadastro.py

Linha canônica: `TOTAL: <n> cadastro(s) em desacordo com o afastamento`. Exit 1 quando há achado.
"""

from __future__ import annotations

import subprocess
import sys

#: Caminho absoluto: ruff S607 recusa executável parcial.
DOCKER = "/usr/bin/docker"  # nosec B607

#: Status de cadastro que AFIRMAM afastamento. Fora daqui, o cadastro diz "está trabalhando"
#: (ativo, pj_*) ou "foi embora" (inativo, demitido) — e nenhum dos dois combina com um
#: afastamento aberto.
STATUS_DE_AFASTAMENTO = ("afastado_inss", "suspenso")

SQL = """
SELECT 'ABERTO_SEM_CADASTRO|' || e.nome || '|' || a.tipo || '|' || a.data_inicio || '|' || coalesce(e.status,'')
  FROM sst_afastamentos a JOIN employees e ON e.id = a.employee_id
 WHERE a.status = 'ativo' AND a.data_retorno IS NULL
   AND lower(coalesce(e.status,'')) NOT IN ('afastado_inss','suspenso')
   -- Quem saiu da empresa não precisa carregar afastamento aberto, mas isso é OUTRO achado:
   -- o registro é que deveria ter sido encerrado. Entra na conta.
UNION ALL
SELECT 'CADASTRO_SEM_ABERTO|' || e.nome || '|-|-|' || coalesce(e.status,'')
  FROM employees e
 WHERE lower(coalesce(e.status,'')) IN ('afastado_inss','suspenso')
   AND NOT EXISTS (SELECT 1 FROM sst_afastamentos a
                    WHERE a.employee_id = e.id AND a.status = 'ativo' AND a.data_retorno IS NULL)
ORDER BY 1
"""


def main() -> int:
    saida = subprocess.run(  # noqa: S603  # nosec B603 - argv fixo, sem shell
        [DOCKER, "exec", "conecta-pro-postgres", "psql", "-U", "postgres", "-d", "conecta_pro", "-tA", "-c", SQL],
        capture_output=True,
        text=True,
        check=False,
    )
    if saida.returncode != 0:
        print(f"FALHOU: não deu para consultar o banco: {saida.stderr.strip()[:200]}")
        print("TOTAL: 1 cadastro(s) em desacordo com o afastamento")
        return 1

    achados = [linha for linha in saida.stdout.splitlines() if linha.strip()]
    for linha in achados:
        especie, nome, tipo, inicio, status = (linha.split("|") + ["", "", "", "", ""])[:5]
        if especie == "ABERTO_SEM_CADASTRO":
            print(f"  ✗ {nome[:30]:<30} afastado desde {inicio} ({tipo}) e o cadastro diz «{status}»")
        else:
            print(f"  ✗ {nome[:30]:<30} cadastro diz «{status}» e não há afastamento aberto")
    print(f"TOTAL: {len(achados)} cadastro(s) em desacordo com o afastamento")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())
