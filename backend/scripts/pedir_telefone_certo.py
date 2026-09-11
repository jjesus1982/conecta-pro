#!/usr/bin/env python3
"""Pede o número certo a quem está com telefone quebrado no cadastro (11/09/2026).

Nasce de um pedido do Jordan — "manda mensagem pros três perguntando o número certo" — e de uma
ironia que precisa estar escrita: **esses três são exatamente quem NÃO recebe WhatsApp.** O
telefone no cadastro deles não existe lá; é por isso que estão na lista. Mandar por WhatsApp
seria repetir o defeito e chamar de solução.

Então vai por E-MAIL, que é o canal que alcança: os três têm e-mail no cadastro.

Mesma disciplina do `aviso_assinatura_service`, e pelas mesmas razões: manda para PESSOA DE
VERDADE, então `--enviar` é obrigatório (o padrão é ensaio), um e-mail por pessoa, e quem não
tem canal nenhum aparece nomeado no fim em vez de sumir.

    python3 backend/scripts/pedir_telefone_certo.py            # ensaio: mostra e não manda
    python3 backend/scripts/pedir_telefone_certo.py --enviar
"""
from __future__ import annotations

import os
import re
import smtplib
import ssl
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

sys.path.insert(0, "/app")

ASSUNTO = "Conecta Mais — confirma seu WhatsApp, por favor"


def _celular_valido(bruto: str) -> bool:
    d = re.sub(r"\D", "", bruto or "")
    return len(d) == 11 and d[2] == "9" and "11" <= d[:2] <= "99"


def _corpo(nome: str, no_cadastro: str) -> str:
    primeiro = (nome or "").split()[0].title() if nome else ""
    return f"""<div style="font-family:Arial,sans-serif;font-size:15px;color:#222;line-height:1.6">
<p>Olá, {primeiro}!</p>
<p>Aqui é a Conecta Mais. Estamos conferindo os contatos do time e o número que temos no seu
cadastro está incompleto — aparece como <b>{no_cadastro}</b>, e por isso as nossas mensagens no
WhatsApp (lembrete de ponto, documento para assinar, comunicado) <b>não estão chegando até você</b>.</p>
<p><b>Você pode responder este e-mail com o seu número de WhatsApp completo?</b><br>
Com DDD e os nove dígitos — por exemplo: (92) 99999-9999.</p>
<p>É rapidinho e resolve. Obrigado!</p>
<p style="color:#666;font-size:13px">Conecta Mais — Segurança e Tecnologia<br>
Se preferir, fale com a gente pelo 0800 880 4414.</p>
</div>"""


def main() -> int:
    import asyncio

    enviar = "--enviar" in sys.argv

    async def _alvos():
        from sqlalchemy import text

        from core.database import async_session_factory
        from modules.integrations.connectors.whatsapp.identidade import SEM_VINCULO

        async with async_session_factory() as db:
            linhas = (await db.execute(text(
                "SELECT nome, coalesce(nullif(celular,''), telefone, '') AS fone, "
                "       coalesce(email,'') AS email FROM employees "
                " WHERE lower(coalesce(status,'ativo')) <> ALL(:sv) "
                "   AND coalesce(is_homologacao,false) = false ORDER BY nome"),
                {"sv": list(SEM_VINCULO)})).mappings().all()
        # mesma régua da trava: celular BR de 11 dígitos. Sem telefone NENHUM é outro caso —
        # ali não há o que confirmar, há o que cadastrar, e quem faz isso é o DP.
        return [r for r in linhas if r["fone"] and not _celular_valido(r["fone"])]

    alvos = asyncio.run(_alvos())
    if not alvos:
        print("nenhum telefone malformado — nada a pedir")
        return 0

    sem_email = [r["nome"] for r in alvos if not r["email"]]
    com_email = [r for r in alvos if r["email"]]
    for r in alvos:
        print(f"  {r['nome']:36} {r['fone']:18} {r['email'] or '⚠️ SEM E-MAIL — não há como perguntar'}")
    if not enviar:
        print(f"\nENSAIO: {len(com_email)} e-mail(s) seriam enviados. Rode com --enviar para mandar.")
        return 0

    porta = int(os.getenv("SMTP_PORT", "465"))
    cfg = {"host": os.getenv("SMTP_HOST", "smtp.hostinger.com"), "port": porta,
           "user": os.getenv("SMTP_USERNAME", os.getenv("SMTP_USER", "")),
           "pass": os.getenv("SMTP_PASSWORD", ""),
           "from": f"{os.getenv('SMTP_FROM_NAME', 'Conecta Mais')} "
                   f"<{os.getenv('SMTP_FROM_EMAIL', os.getenv('SMTP_USERNAME', 'noreply@conectamais.pro'))}>"}
    ctx = ssl.create_default_context()
    server = (smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=ctx) if porta == 465
              else smtplib.SMTP(cfg["host"], cfg["port"]))
    if porta != 465:
        server.starttls(context=ctx)
    if cfg["pass"]:
        server.login(cfg["user"], cfg["pass"])
    enviados = 0
    try:
        for r in com_email:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = ASSUNTO
            msg["From"] = cfg["from"]
            msg["To"] = r["email"]
            msg.attach(MIMEText(_corpo(r["nome"], r["fone"]), "html", "utf-8"))
            try:
                server.sendmail(cfg["user"], r["email"], msg.as_bytes())
                enviados += 1
                print(f"  enviado: {r['nome']} -> {r['email']}")
            except Exception as exc:  # noqa: BLE001 — um e-mail ruim não cala os outros
                print(f"  FALHOU: {r['nome']} -> {r['email']}: {exc}")
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001
            pass
    if sem_email:
        print(f"\nSEM CANAL NENHUM ({len(sem_email)}): {', '.join(sem_email)} — telefone quebrado "
              "e sem e-mail. Só alguém do posto consegue perguntar a essas pessoas.")
    print(f"TOTAL pedidos enviados: {enviados}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
