"""Avisa o funcionário, POR E-MAIL, que há documento esperando a assinatura dele.

🔴 POR QUE ISTO EXISTE. A notificação in-app já existia e funcionava — 165 avisos
`document_pending` para 58 pessoas, com título e mensagem corretos. Mas `portal_notifications`
não tem canal nenhum: ela é PASSIVA, e só aparece para quem entra no portal por conta
própria. Medido em 21/08/2026: **6 de 165 lidas**, e 51 recibos + 67 holerites parados
desde 15/07.

O funcionário é porteiro ou ASG. Ele não entra num portal web para descobrir que tem tarefa
— alguém precisa avisar. 52 de 53 têm e-mail cadastrado.

Sem isto, o kit do condomínio não passa de 70%: os 30% que faltam são exatamente os
documentos que dependem de uma assinatura que ninguém sabe que está pendente.

⚠️ MANDA E-MAIL DE VERDADE, para pessoas de verdade. Por isso:
  - `dry_run=True` é o PADRÃO. Enviar exige passar `dry_run=False` explicitamente.
  - Um e-mail por PESSOA, com todos os documentos dela juntos — não um por documento.
    Quem tem 5 pendências recebe 1 aviso, não 5.
  - Reenvio respeita `_JANELA_DIAS`: ninguém recebe o mesmo lembrete dois dias seguidos.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: Intervalo mínimo entre dois lembretes para a MESMA pessoa. Lembrete diário vira spam e
#: some junto com o resto; a pessoa aprende a ignorar o remetente.
_JANELA_DIAS = 3

# /meu-espaco dava 404 (medido 07/09/2026); a entrada do colaborador (CPF) é /portal-funcionario/login.
PORTAL_URL = os.getenv("PORTAL_URL", "https://erp.conectamais.pro/portal-funcionario/login")

#: `portal_notifications.notification_type` é ENUM no banco (document_pending,
#: schedule_update, payslip_available, warning_issued, general, system). Criar um valor
#: novo exigiria migration, e alembic/versions é zona proibida sem autorização do Jordan.
#: Então o lembrete usa 'system' e se distingue pelo TÍTULO — que é também o que a janela
#: de reenvio consulta. Se um dia houver migration, vira um tipo próprio.
_TITULO_LEMBRETE = "Lembrete de assinatura enviado por e-mail"

_SQL_PENDENTES = text(
    """
    SELECT e.id::text AS eid, e.nome, e.email, coalesce(e.celular, e.telefone, '') AS fone,
           count(*) AS qtd,
           string_agg(DISTINCT r.document_type, ',') AS tipos,
           max(r.created_at) AS mais_recente
      FROM sig_signature_requests r
      JOIN employees e ON e.id = r.signer_id
     WHERE r.status = 'PENDING' AND r.signer_type = 'employee'
       -- 🔴 SÓ AVISA SOBRE O QUE DÁ PARA ASSINAR. Desde 21/08 a assinatura FALHA se não
       -- houver PDF (antes registrava "assinado" sem documento). Medido no mesmo dia: de
       -- 1.334 solicitações pendentes, 958 NÃO TÊM PDF — 679 nunca tiveram e 250 apontam
       -- para arquivo sumido. Avisar sobre elas manda a pessoa bater numa porta fechada e
       -- ensina que o aviso não vale nada. O e-mail promete só o que o portal entrega.
       AND coalesce(r.document_path,'') <> ''
       -- Dono, 07/09/2026: "podem receber pelo app ou pelo WhatsApp" — quem tem celular
       -- também é avisado (231 notificações no portal em 30 dias, 1 lida).
       AND (coalesce(e.email,'') <> '' OR coalesce(e.celular, e.telefone, '') <> '')
       AND lower(coalesce(e.status,'')) IN ('ativo','afastado_inss','suspenso')
       AND NOT EXISTS (
             SELECT 1 FROM portal_notifications n
              WHERE n.employee_id = e.id
                AND n.title = :titulo_lembrete
                AND n.created_at > now() - make_interval(days => :janela))
     GROUP BY e.id, e.nome, e.email, coalesce(e.celular, e.telefone, '')
     ORDER BY count(*) DESC
    """
)

# `portal_notifications.id` é INTEGER com sequência própria — não é uuid como nas outras
# tabelas da casa. Gerar o id aqui dá "column id is of type integer but expression is of
# type uuid", e o INSERT falha DEPOIS do e-mail já ter saído: a pessoa recebe e o sistema
# não registra, então o próximo lembrete a alcança de novo. Deixar a sequência trabalhar.
_SQL_REGISTRA = text(
    "INSERT INTO portal_notifications (employee_id, notification_type, title, message, "
    "  is_read, created_at) "
    "VALUES (CAST(:eid AS uuid), 'system', :titulo, :msg, false, now())"
)

_ROTULO = {
    "payslip": "holerite",
    "recibo_vt_vr": "recibo de vale-transporte e vale-alimentação",
    "espelho_ponto": "espelho de ponto",
    "contract": "contrato de trabalho",
    "prorrogacao_contrato": "prorrogação de contrato",
    "comunicado": "comunicado",
    "aviso_previo": "aviso prévio",
    "rescisao": "rescisão",
    "kit_documento": "documento do kit",
}


def _config_smtp() -> dict:
    """Mesma leitura de `email_kit_service._config_smtp` — o SMTP da casa é um só."""
    from_name = os.getenv("SMTP_FROM_NAME", "Conecta PRO")
    from_email = os.getenv("SMTP_FROM_EMAIL", os.getenv("SMTP_USERNAME", "noreply@conectamais.pro"))
    port = int(os.getenv("SMTP_PORT", "465"))
    return {
        "host": os.getenv("SMTP_HOST", "smtp.hostinger.com"),
        "port": port,
        "user": os.getenv("SMTP_USERNAME", os.getenv("SMTP_USER", "")),
        "pass": os.getenv("SMTP_PASSWORD", ""),
        "from": f"{from_name} <{from_email}>",
        "ssl": port == 465,
    }


def _lista_legivel(tipos: str, qtd: int) -> str:
    nomes = [_ROTULO.get(t.strip(), t.strip().replace("_", " ")) for t in (tipos or "").split(",") if t.strip()]
    nomes = sorted(set(nomes))
    if not nomes:
        return f"{qtd} documento(s)"
    if len(nomes) == 1:
        return f"{qtd} documento(s): {nomes[0]}"
    return f"{qtd} documento(s): " + ", ".join(nomes[:-1]) + f" e {nomes[-1]}"


def _html(nome: str, resumo: str) -> str:
    primeiro = (nome or "").split()[0].capitalize() if nome else "Olá"
    return f"""<html><body style="font-family:Arial,Helvetica,sans-serif;color:#1f2937">
  <p>Olá, {primeiro}.</p>
  <p>Você tem <b>{resumo}</b> aguardando a sua assinatura no portal do funcionário.</p>
  <p style="margin:24px 0">
    <a href="{PORTAL_URL}" style="background:#047857;color:#fff;padding:12px 22px;
       border-radius:6px;text-decoration:none;font-weight:bold">Assinar agora</a>
  </p>
  <p style="font-size:13px;color:#6b7280">
    Entre com o seu CPF. Se tiver dúvida sobre o acesso, procure o Departamento Pessoal.
  </p>
  <p style="font-size:12px;color:#9ca3af">Conecta Mais — mensagem automática, não responda este e-mail.</p>
</body></html>"""


def avisar_pendentes(db, dry_run: bool = True, limite: int | None = None) -> dict:
    """Um e-mail por PESSOA com tudo que ela tem para assinar. `dry_run=True` por padrão."""
    linhas = db.execute(_SQL_PENDENTES, {"janela": _JANELA_DIAS, "titulo_lembrete": _TITULO_LEMBRETE}).mappings().all()
    if limite:
        linhas = linhas[:limite]

    rel: dict = {
        "dry_run": dry_run,
        "pessoas": len(linhas),
        "documentos": sum(int(r["qtd"]) for r in linhas),
        "enviados": 0,
        "falhas": 0,
        "amostra": [f"{r['nome'][:26]} — {_lista_legivel(r['tipos'], r['qtd'])}" for r in linhas[:5]],
    }
    if dry_run or not linhas:
        return rel

    cfg = _config_smtp()
    ctx = ssl.create_default_context()
    server = None
    try:
        if cfg["ssl"]:
            server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=ctx)
        else:
            server = smtplib.SMTP(cfg["host"], cfg["port"])
            server.starttls(context=ctx)
        if cfg["pass"]:
            server.login(cfg["user"], cfg["pass"])
    except Exception as exc:  # noqa: BLE001 — sem SMTP, o WhatsApp ainda sai
        logger.warning("aviso de assinatura: SMTP indisponível: %s", exc)
        rel["erro_smtp"] = str(exc)[:120]
        server = None
    rel["whatsapp"] = 0
    try:
        for r in linhas:
            resumo = _lista_legivel(r["tipos"], r["qtd"])
            canais: list[str] = []
            if server and r["email"]:
                try:
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = "Você tem documento para assinar — Conecta Mais"
                    msg["From"] = cfg["from"]
                    msg["To"] = r["email"]
                    msg.attach(MIMEText(_html(r["nome"], resumo), "html", "utf-8"))
                    server.sendmail(cfg["user"], r["email"], msg.as_bytes())
                    canais.append(f"e-mail {r['email']}")
                except Exception as exc:  # noqa: BLE001 — um e-mail ruim não cala os outros
                    logger.warning("aviso de assinatura (e-mail) para %s: %s", r["nome"], exc)
            if r.get("fone"):
                try:
                    if enviar_whatsapp(r["fone"], mensagem_whatsapp(r["nome"], resumo)):
                        canais.append(f"WhatsApp {r['fone']}")
                        rel["whatsapp"] += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("aviso de assinatura (WhatsApp) para %s: %s", r["nome"], exc)
            if not canais:
                rel["falhas"] += 1
                continue
            # Registra o lembrete: é ele que segura o reenvio dentro da janela.
            db.execute(_SQL_REGISTRA, {"eid": r["eid"], "titulo": _TITULO_LEMBRETE,
                                       "msg": f"{' + '.join(canais)} — {resumo}"})
            rel["enviados"] += 1
    finally:
        if server:
            try:
                server.quit()
            except Exception:  # noqa: BLE001
                pass
    return rel


def mensagem_whatsapp(nome: str, resumo: str) -> str:
    primeiro = (nome or "").split()[0].title() if nome else ""
    return (f"Olá, {primeiro}! Aqui é a Conecta Mais. Você tem {resumo} para assinar no portal do "
            f"colaborador. Entre com seu CPF em {PORTAL_URL} e assine — leva um minuto. "
            f"Se não conseguir entrar, responda aqui que a gente ajuda.")


def enviar_whatsapp(fone: str, texto: str) -> bool:
    """Manda pelo mesmo serviço do CRM (Chatwoot/Baileys). Síncrono: roda o coroutine num loop
    próprio, numa thread, porque quem chama (a task do beat) não está num event loop."""
    import asyncio
    import concurrent.futures

    from modules.integrations.connectors.whatsapp.service import send_text_message

    def _run():
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(send_text_message(fone, texto))
        finally:
            loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        r = ex.submit(_run).result(timeout=60) or {}
    return str(r.get("status", "")).lower() in ("sent", "ok", "success", "queued") or bool(r.get("id") or r.get("message_id"))

    try:
        for r in linhas:
            resumo = _lista_legivel(r["tipos"], r["qtd"])
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = "Você tem documento para assinar — Conecta Mais"
                msg["From"] = cfg["from"]
                msg["To"] = r["email"]
                msg.attach(MIMEText(_html(r["nome"], resumo), "html", "utf-8"))
                server.sendmail(cfg["user"], r["email"], msg.as_bytes())
                # Registra o lembrete: é ele que segura o reenvio dentro da janela.
                db.execute(
                    _SQL_REGISTRA,
                    {
                        "eid": r["eid"],
                        "titulo": _TITULO_LEMBRETE,
                        "msg": f"E-mail enviado para {r['email']} — {resumo}",
                    },
                )
                rel["enviados"] += 1
            except Exception as exc:  # noqa: BLE001 — um e-mail ruim não cala os outros
                rel["falhas"] += 1
                logger.warning("aviso de assinatura para %s: %s", r["nome"], exc)
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001
            pass
    return rel
