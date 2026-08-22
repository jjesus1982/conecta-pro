"""
Utilitário de envio de email via SMTP.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from core.config import settings
from core.logging import logger


async def send_email(to_email: str, subject: str, html_body: str,
                     anexos: list[tuple[str, bytes]] | None = None) -> bool:
    """
    Envia email via SMTP.

    Args:
        anexos: lista de (nome_do_arquivo, conteudo). Opcional — sem anexo o e-mail sai
            exatamente como antes ("alternative"); com anexo o container vira "mixed",
            porque "alternative" trata as partes como versões do MESMO conteúdo e o cliente
            de e-mail escolhe uma — o anexo simplesmente não aparece.

    Returns:
        True se enviou com sucesso, False caso contrário.
    """
    if not settings.SMTP_HOST:
        logger.warning("SMTP não configurado — email não enviado")
        return False

    msg = MIMEMultipart("mixed" if anexos else "alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    for nome, conteudo in (anexos or []):
        from email.mime.application import MIMEApplication  # noqa: PLC0415

        parte = MIMEApplication(conteudo, _subtype="pdf")
        parte.add_header("Content-Disposition", "attachment", filename=nome)
        msg.attach(parte)

    try:
        if settings.SMTP_USE_TLS:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)

        if settings.SMTP_USERNAME:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)

        server.sendmail(settings.SMTP_FROM_EMAIL, to_email, msg.as_string())
        server.quit()

        logger.info(f"Email enviado para {to_email}: {subject}")
        return True

    except Exception as e:
        logger.error(f"Falha ao enviar email para {to_email}: {e}")
        return False


def build_reset_password_email(name: str, reset_url: str) -> str:
    """Gera HTML do email de reset de senha."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f4f4f5; padding: 40px 0;">
      <div style="max-width: 480px; margin: 0 auto; background: #fff; border-radius: 12px; padding: 40px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
        <div style="text-align: center; margin-bottom: 32px;">
          <h1 style="color: #0f172a; font-size: 22px; margin: 0;">Conecta PRO</h1>
        </div>
        <p style="color: #334155; font-size: 15px; line-height: 1.6;">
          Olá <strong>{name}</strong>,
        </p>
        <p style="color: #334155; font-size: 15px; line-height: 1.6;">
          Recebemos uma solicitação para redefinir a senha da sua conta.
          Clique no botão abaixo para criar uma nova senha:
        </p>
        <div style="text-align: center; margin: 32px 0;">
          <a href="{reset_url}"
             style="display: inline-block; background: #2563eb; color: #fff; padding: 12px 32px;
                    border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 15px;">
            Redefinir Senha
          </a>
        </div>
        <p style="color: #64748b; font-size: 13px; line-height: 1.6;">
          Este link expira em <strong>30 minutos</strong>. Se você não solicitou
          a redefinição de senha, ignore este email.
        </p>
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;">
        <p style="color: #94a3b8; font-size: 12px; text-align: center;">
          © 2025 Conecta PRO — Gestão Inteligente para Vigilância Patrimonial
        </p>
      </div>
    </body>
    </html>
    """
