#!/usr/bin/env python3
"""A cobrança de assinatura tem de tentar os DOIS números antes de desistir.

Origem: 17/09/2026. A Bianca Hellem estava havia meses sem receber a cobrança com o número
certo cadastrado **a um campo de distância**: o WhatsApp de verdade (92 99220-8640, o mesmo
da chave PIX) estava em `employees.telefone`, e `employees.celular` tinha `92988887777`
digitado à mão, que não existe no WhatsApp. A query lê `coalesce(celular, telefone)` — parava
no primeiro, mandava para o número morto, e o relatório dizia «enviado».

Medido no mesmo dia: **8 de 74** pessoas ativas têm `celular` e `telefone` diferentes. Cada
uma delas é uma chance de a cobrança bater na porta errada e ninguém perceber.

## As regras afirmadas

1. Quando o primeiro número é recusado, o envio TENTA O SEGUNDO.
2. Quando o segundo é aceito, o lembrete registrado nomeia o número que de fato recebeu —
   senão o histórico mente sobre onde a mensagem caiu.
3. Número na lista de opt-out (`crm_followup_optout`) NÃO é tentado — nem como segunda
   opção. É a mesma lista que o lembrete de ponto respeita desde que nasceu; a cobrança a
   ignorava, e um «pare de me mandar mensagem» valia num canal e não no outro.
4. Quando o primeiro é aceito, o segundo NÃO é tentado: ninguém recebe a mesma cobrança duas
   vezes.

A trava mede a SAÍDA da função — ela chama `avisar_pendentes` de verdade, com o envio de
WhatsApp e o SMTP dublados, sobre um pendente que ela mesma cria. Nada sai para ninguém e
nada fica no banco: tudo roda dentro de uma transação que termina em `rollback`.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
        /app/scripts/orq/test_cobranca_tenta_os_dois_numeros.py

Linha canônica: `TOTAL: <n> falha(s) na cobranca de dois numeros`. Exit 1 quando há achado.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "/app")

#: Números de fachada. Só existem dentro da transação que é desfeita no fim, e o envio está
#: dublado — nenhuma mensagem sai. Prefixo 9290000 não pertence a ninguém em Manaus.
FONE_MORTO = "92900000001"
FONE_VIVO = "92900000002"


def main() -> int:
    from sqlalchemy import text

    from core.database.session import get_sync_db
    from modules.signatures.services import aviso_assinatura_service as serv

    falhas: list[str] = []
    chamadas: list[str] = []

    #: SMTP inalcançável de propósito: o serviço segue sem e-mail (`server = None`) e o que
    #: sobra para medir é exatamente o WhatsApp.
    serv._config_smtp = lambda: {  # noqa: SLF001
        "host": "127.0.0.1",
        "port": 1,
        "ssl": False,
        "user": "x@x",
        "pass": "",
        "from": "x@x",
    }

    def envio_dublado(fone: str, texto: str) -> bool:
        chamadas.append(fone)
        return fone == FONE_VIVO

    with get_sync_db() as db:
        try:
            eid = db.execute(
                text(
                    """SELECT id::text FROM employees
                        WHERE coalesce(is_homologacao,false) = false
                          AND lower(coalesce(status,'')) = 'ativo'
                        ORDER BY created_at LIMIT 1"""
                )
            ).scalar()
            base = db.execute(
                text("SELECT tenant_id::text, requested_by::text FROM sig_signature_requests LIMIT 1")
            ).first()
            if not eid or not base:
                print("FALHOU: sem funcionário ativo ou sem solicitação existente para espelhar")
                print("TOTAL: 1 falha(s) na cobranca de dois numeros")
                return 1

            db.execute(
                text("UPDATE employees SET celular = :c, telefone = :t WHERE id = :e"),
                {"c": FONE_MORTO, "t": FONE_VIVO, "e": eid},
            )
            db.execute(
                text(
                    """INSERT INTO sig_signature_requests
                       (id, tenant_id, title, status, priority, purpose, signer_name,
                        reminder_frequency, requested_by, created_at, updated_at,
                        signer_id, signer_type, document_type, document_path)
                       VALUES (gen_random_uuid(), :tid, 'ZZ oráculo dois números', 'PENDING',
                               'NORMAL', 'OTHER', 'ZZ oráculo', 'NONE', :req, now(), now(),
                               :e, 'employee', 'recibo_vt_vr', '/tmp/zz-oraculo.pdf')"""
                ),
                {"tid": base[0], "req": base[1], "e": eid},
            )

            serv.enviar_whatsapp = envio_dublado

            # 1 · primeiro número morto → tem de cair no segundo
            rel = serv.avisar_pendentes(db, dry_run=False, employee_id=eid, ignorar_janela=True)
            if chamadas != [FONE_MORTO, FONE_VIVO]:
                falhas.append(
                    f"não tentou os dois números: tentou {chamadas or 'nenhum'} (esperado {[FONE_MORTO, FONE_VIVO]})"
                )
            if rel.get("whatsapp") != 1 or rel.get("enviados") != 1:
                falhas.append(f"relatório não contou o envio do segundo número: {rel}")

            # 2 · o lembrete registrado nomeia o número que recebeu, não o que recusou
            msg = (
                db.execute(
                    text(
                        """SELECT message FROM portal_notifications
                        WHERE employee_id = :e AND title = :t
                        ORDER BY created_at DESC LIMIT 1"""
                    ),
                    {"e": eid, "t": serv._TITULO_LEMBRETE},  # noqa: SLF001
                ).scalar()
                or ""
            )
            if FONE_VIVO not in msg or FONE_MORTO in msg:
                falhas.append(f"o lembrete não nomeia o número que recebeu: {msg!r}")

            # 3 · número na lista de opt-out NÃO é tentado, nem como segunda opção
            chamadas.clear()
            db.execute(
                text("INSERT INTO crm_followup_optout (phone_canonical, motivo) VALUES (:p, 'ZZ oráculo')"),
                {"p": FONE_VIVO},
            )
            serv.avisar_pendentes(db, dry_run=False, employee_id=eid, ignorar_janela=True)
            if FONE_VIVO in chamadas:
                falhas.append(f"mandou para número em opt-out: {chamadas}")
            db.execute(text("DELETE FROM crm_followup_optout WHERE phone_canonical = :p"), {"p": FONE_VIVO})

            # 4 · primeiro número vivo → o segundo NÃO é tentado (nada de cobrança dobrada)
            chamadas.clear()
            serv.enviar_whatsapp = lambda fone, texto: chamadas.append(fone) or True
            serv.avisar_pendentes(db, dry_run=False, employee_id=eid, ignorar_janela=True)
            if chamadas != [FONE_MORTO]:
                falhas.append(f"mandou para o segundo número mesmo com o primeiro aceito: {chamadas}")
        finally:
            db.rollback()

    for f in falhas:
        print(f"FALHOU: {f}")
    print(f"TOTAL: {len(falhas)} falha(s) na cobranca de dois numeros")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
