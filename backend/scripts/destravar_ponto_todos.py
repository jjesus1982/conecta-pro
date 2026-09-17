#!/usr/bin/env python3
"""Destrava TODO MUNDO que não consegue bater o ponto pelo app (11/09/2026).

Jordan: *"resolva todos os problemas, preciso que todos batam ponto normalmente"*.

O levantamento, feito contra o banco e não por suposição — 12 pessoas de 52 travadas, em três
situações com causas diferentes:

  A) SEM CONTA no portal (2). Não conseguem nem entrar. Têm e-mail e CPF e nenhum telefone.
  B) SEM ROSTO cadastrado (4). O app não tem com o que comparar.
  C) TÊM TUDO e o app não registra há 14 dias (6). E o padrão delas conta a história: cinco
     cadastraram o rosto entre 11 e 12/08, bateram UMA ou duas vezes e nunca mais — é a mesma
     janela do episódio em que 14 pessoas recadastraram o rosto na guarita, no escuro. A
     referência ficou ruim e elas voltaram para o Tangerino em vez de reclamar.

O QUE ESTE SCRIPT FAZ, por situação:
  A → cria a conta (senha = CPF, como no resto da casa) e manda o link.
  B → nada a limpar; manda a instrução de cadastrar o rosto.
  C → LIMPA a referência para o app voltar a pedir o cadastro, e manda a instrução.

⚠️ NÃO limpa referência cadastrada nos últimos 7 dias: a CINTIA recadastrou em 08/09 e ainda
não bateu — a referência dela é nova, e apagá-la seria trocar uma coisa que talvez funcione por
uma certeza de retrabalho.

Cada pessoa recebe a mensagem pelo canal que ALCANÇA ela: WhatsApp quando o número existe lá
(conferido na hora), e-mail quando não. Quem não tem canal nenhum sai nomeado.

    python3 backend/scripts/destravar_ponto_todos.py
    python3 backend/scripts/destravar_ponto_todos.py --aplicar
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import smtplib
import ssl
import sys
import uuid
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

sys.path.insert(0, "/app")

DIAS_SEM_APP = 14
DIAS_REFERENCIA_NOVA = 7
PORTAL = "https://erp.conectamais.pro/modulos/meu-espaco"

_SQL = """
SELECT e.id::text AS eid, e.nome, coalesce(e.email,'') AS email, coalesce(e.cpf,'') AS cpf,
       coalesce(nullif(e.celular,''), e.telefone,'') AS fone,
       (SELECT u.email FROM users u WHERE u.employee_id = e.id AND u.is_active
         ORDER BY u.last_login DESC NULLS LAST LIMIT 1) AS email_login,
       (e.face_descriptor IS NOT NULL) AS tem_rosto,
       e.face_enrolled_at,
       (SELECT count(*) FROM gp_clock_punches p WHERE p.employee_id = e.id
          AND p.device_type IN ('mobile','web')
          AND p.punch_timestamp > current_date - make_interval(days => :dias)) AS app_recente
  FROM employees e
 WHERE coalesce(e.status,'ativo') = 'ativo' AND coalesce(e.is_homologacao,false) = false
   AND (e.tipo_contrato = 'clt' OR e.tipo_contrato IS NULL)
 ORDER BY e.nome
"""

MSG = {
    "A": (
        "Oi, {primeiro}! Aqui é o José Luís, da Conecta Mais — eu cuido da organização do "
        "ponto junto com a Pyetra Jesus.\n\n"
        "Acabei de criar seu acesso ao app do ponto. Para entrar:\n"
        "• Endereço: {portal}\n• E-mail: {email}\n• Senha: seu CPF, só os números\n\n"
        "Na primeira vez ele vai pedir para cadastrar seu rosto. Faça num lugar claro, de "
        "frente para a luz — é essa foto que o app usa depois para te reconhecer.\n\n"
        "Qualquer coisa, me chama aqui."
    ),
    "B": (
        "Oi, {primeiro}! Aqui é o José Luís, da Conecta Mais — eu cuido da organização do "
        "ponto junto com a Pyetra Jesus.\n\n"
        "Vi aqui que falta cadastrar seu rosto no app do ponto. Entre em {portal} (e-mail "
        "{email}, senha é seu CPF só os números) e faça o cadastro num lugar claro, de "
        "frente para a luz.\n\n"
        "Enquanto isso, se precisar bater e não conseguir, use o botão *registrar para o DP "
        "validar* — sua batida fica guardada do mesmo jeito."
    ),
    "C": (
        "Oi, {primeiro}! Aqui é o José Luís, da Conecta Mais — eu cuido da organização do "
        "ponto junto com a Pyetra Jesus.\n\n"
        "Descobri por que o app não estava te reconhecendo: a foto de referência do seu "
        "rosto ficou ruim. Já limpei ela aqui.\n\n"
        "Agora é só entrar em {portal} (e-mail {email}, senha é seu CPF só os números) que "
        "ele vai pedir para cadastrar seu rosto de novo. Faça num lugar claro, de frente "
        "para a luz — leva uns 10 segundos e resolve.\n\n"
        "Se ainda assim não der, use o botão *registrar para o DP validar* e me avisa."
    ),
}


def _enviar_email(cfg, server, para: str, assunto: str, corpo: str) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"] = cfg["from"]
    msg["To"] = para
    msg.attach(
        MIMEText(
            "<div style='font-family:Arial,sans-serif;font-size:15px;"
            "white-space:pre-wrap'>" + corpo.replace("*", "") + "</div>",
            "html",
            "utf-8",
        )
    )
    server.sendmail(cfg["user"], para, msg.as_bytes())
    return True


async def main() -> int:
    from sqlalchemy import text

    from core.auth.security import hash_password
    from core.database import async_session_factory
    from modules.integrations.connectors.whatsapp.service import whatsapp_service

    aplicar = "--aplicar" in sys.argv
    async with async_session_factory() as db:
        linhas = (await db.execute(text(_SQL), {"dias": DIAS_SEM_APP})).mappings().all()

    plano = []
    for r in linhas:
        if not r["email_login"]:
            plano.append({**dict(r), "situacao": "A"})
        elif not r["tem_rosto"]:
            plano.append({**dict(r), "situacao": "B"})
        elif int(r["app_recente"]) == 0:
            nova = (
                r["face_enrolled_at"] is not None
                and (datetime.now() - r["face_enrolled_at"]).days < DIAS_REFERENCIA_NOVA
            )
            if nova:
                print(
                    f"  PULO {r['nome']}: referência de "
                    f"{r['face_enrolled_at'].strftime('%d/%m')} é nova demais para apagar"
                )
                continue
            plano.append({**dict(r), "situacao": "C"})

    for p in plano:
        print(
            f"  {p['situacao']}  {p['nome'][:34]:36} "
            f"{'cria conta + ' if p['situacao'] == 'A' else ''}"
            f"{'limpa referência + ' if p['situacao'] == 'C' else ''}avisa"
        )
    if not aplicar:
        print(f"\nENSAIO: {len(plano)} pessoa(s) seriam destravadas. Rode com --aplicar.")
        return 0

    porta = int(os.getenv("SMTP_PORT", "465"))
    cfg = {
        "host": os.getenv("SMTP_HOST", "smtp.hostinger.com"),
        "port": porta,
        "user": os.getenv("SMTP_USERNAME", ""),
        "pass": os.getenv("SMTP_PASSWORD", ""),
        "from": f"{os.getenv('SMTP_FROM_NAME', 'Conecta Mais')} "
        f"<{os.getenv('SMTP_FROM_EMAIL', os.getenv('SMTP_USERNAME', ''))}>",
    }
    ctx = ssl.create_default_context()
    server = (
        smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=ctx)
        if porta == 465
        else smtplib.SMTP(cfg["host"], cfg["port"])
    )
    if porta != 465:
        server.starttls(context=ctx)
    if cfg["pass"]:
        server.login(cfg["user"], cfg["pass"])

    feito, sem_canal, backup = [], [], []
    try:
        for p in plano:
            async with async_session_factory() as db:
                email_login = p["email_login"]
                if p["situacao"] == "A" and p["email"]:
                    email_login = p["email"].strip().lower()
                    await db.execute(
                        text(
                            "INSERT INTO users (id, email, password_hash, name, role, is_active, "
                            " employee_id, created_at) VALUES (gen_random_uuid(), :e, :ph, :n, "
                            " 'funcionario', true, CAST(:eid AS uuid), now())"
                        ),
                        {
                            "e": email_login,
                            "ph": hash_password(re.sub(r"\D", "", p["cpf"])),
                            "n": p["nome"],
                            "eid": p["eid"],
                        },
                    )
                if p["situacao"] == "C":
                    d = (
                        await db.execute(
                            text("SELECT face_descriptor::text FROM employees WHERE id = CAST(:e AS uuid)"),
                            {"e": p["eid"]},
                        )
                    ).scalar()
                    backup.append({"employee_id": p["eid"], "nome": p["nome"], "descriptor": d})
                    await db.execute(
                        text(
                            "UPDATE employees SET face_descriptor = NULL, biometria_facial = false, "
                            " face_enrolled_at = NULL, updated_at = now() WHERE id = CAST(:e AS uuid)"
                        ),
                        {"e": p["eid"]},
                    )
                await db.commit()

            texto = MSG[p["situacao"]].format(
                primeiro=(p["nome"].split()[0].title()), portal=PORTAL, email=email_login or p["email"]
            )
            canal = None
            d = re.sub(r"\D", "", p["fone"] or "")
            if len(d) == 11 and d[2] == "9" and await whatsapp_service._resolve_jid("55" + d):
                try:
                    res = await whatsapp_service.send_custom(d, texto)
                    if str((res or {}).get("status", "")).lower() in ("sent", "ok", "success"):
                        canal = f"WhatsApp {d}"
                except Exception:  # noqa: BLE001
                    canal = None
            if not canal and p["email"]:
                try:
                    _enviar_email(cfg, server, p["email"], "Conecta Mais — seu acesso ao ponto", texto)
                    canal = f"e-mail {p['email']}"
                except Exception as exc:  # noqa: BLE001
                    print(f"  e-mail falhou para {p['nome']}: {exc}")
            if canal:
                feito.append(f"{p['situacao']} {p['nome']} → {canal}")
                print(f"  ok {p['nome'][:32]:34} {canal}")
            else:
                sem_canal.append(p["nome"])
            await asyncio.sleep(3)
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001
            pass

    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("/app/uploads", exist_ok=True)
    caminho = f"/app/uploads/destravar_ponto_{carimbo}.json"
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(
            {"avisados": feito, "sem_canal": sem_canal, "referencias_limpas": backup}, f, ensure_ascii=False, indent=1
        )
    async with async_session_factory() as db:
        await db.execute(
            text(
                "INSERT INTO gp_audit_logs (id, timestamp, action, entity, entity_id, description, "
                " source_module, actor_user_id, actor_user_name, actor_user_role, actor_user_module, "
                " extra_data) VALUES (CAST(:i AS uuid), (now() AT TIME ZONE 'America/Manaus'), "
                " 'ponto.destrave_em_lote', 'employees', 'lote', :d, 'people_management.ponto', "
                " 'jordan', 'Jordan Jesus (autorização em 11/09/2026)', 'dono', 'ponto', CAST(:x AS jsonb))"
            ),
            {
                "i": str(uuid.uuid4()),
                "d": f"{len(feito)} pessoa(s) destravadas para bater ponto",
                "x": json.dumps(
                    {"avisados": len(feito), "sem_canal": sem_canal, "backup": caminho}, ensure_ascii=False
                ),
            },
        )
        await db.commit()
    print(f"\nAPLICADO: {len(feito)} avisadas · {len(sem_canal)} sem canal: {', '.join(sem_canal) or '—'}")
    print(f"registro e reversão em {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
