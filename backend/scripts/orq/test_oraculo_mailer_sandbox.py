"""Oráculo — quem não deve receber e-mail, não recebe: sandbox e domínios reservados (24/09/2026).

Por que existe: um teste no container efêmero (banco de staging, `.env` de produção) enviou um
lembrete de cobrança REAL a um cliente. `core.mailer.destinatario_permitido` é a parede.
O que afirma: com banco de staging/sandbox só @conectamais.pro passa; em produção tudo passa.
Função pura; roda em qualquer lugar. Sai 0/1.
"""

from __future__ import annotations

import sys

from core.mailer import destinatario_permitido as ok

CASOS = [
    # RFC 2606/6761: domínio reservado nunca recebe, nem em produção — a fixture do oráculo U4
    # usava `@externo.invalid` e virava tentativa de entrega na varredura (24/09/2026).
    ("sindico@externo.invalid", "postgresql://x@postgres/conecta_pro", False),
    ("a@b.test", "postgresql://x@postgres/conecta_pro", False),
    ("x@y.example", "postgresql://x@postgres/conecta_pro", False),
    ("cliente@chacaramaiapolis.com.br", "postgresql://x@postgres-staging/conecta_pro_staging", False),
    ("jjesus@conectamais.pro", "postgresql://x@postgres-staging/conecta_pro_staging", True),
    ("cliente@chacaramaiapolis.com.br", "postgresql://x@postgres/conecta_pro", True),
    ("", "postgresql://x@postgres-staging/conecta_pro_staging", False),
]


def main() -> int:
    falhas = [f"{e} @ {u}" for e, u, esperado in CASOS if ok(e, u) is not esperado]
    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL mailer sandbox: {len(falhas)} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
