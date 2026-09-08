"""
Email Kit Service — Conecta PRO
Envia e-mail automático quando kit é montado:
- Kit pequeno (< 10MB): anexa os documentos
- Kit grande (≥ 10MB): envia link do Drive
"""

import logging
import os
import smtplib
import ssl
import subprocess
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

logger = logging.getLogger(__name__)

# Threshold: 10MB em bytes
TAMANHO_MAX_ANEXO = 10 * 1024 * 1024

MESES_PT = {
    "01": "Janeiro",
    "02": "Fevereiro",
    "03": "Março",
    "04": "Abril",
    "05": "Maio",
    "06": "Junho",
    "07": "Julho",
    "08": "Agosto",
    "09": "Setembro",
    "10": "Outubro",
    "11": "Novembro",
    "12": "Dezembro",
}


def _get_pg() -> str:
    r = subprocess.run(  # noqa: S602, S607  # nosec
        "docker ps --format '{{.Names}}' | grep -E 'conecta.*postgres$|^postgres$' | head -1",  # noqa: S607
        shell=True,  # nosec
        capture_output=True,
        text=True,
    )
    name = r.stdout.strip()
    return name if name else "conecta-pro-postgres"


def _psql(q: str) -> list[str]:
    r = subprocess.run(  # noqa: S602  # nosec
        f'docker exec {_get_pg()} psql -U postgres -d conecta_pro -t -A -c "{q}" 2>/dev/null',
        shell=True,  # nosec
        capture_output=True,
        text=True,
    )
    return [v.strip() for v in r.stdout.strip().splitlines() if v.strip()]


class EmailKitService:
    """Serviço de envio de e-mail para kits documentais."""

    def _config_smtp(self) -> dict:
        """Obter configurações SMTP do .env."""
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

    def _buscar_email_cliente(self, client_id: str) -> str | None:
        """Buscar e-mail do cliente no banco."""
        # G1: ged_clients.contact_email é a fonte correta (clients.email é NULL para todos os kits GED)
        import re as _re
        if not _re.fullmatch(r"[0-9a-fA-F-]{36}", str(client_id or "")):  # id vai num shell: só UUID passa (08/09/2026)
            return None
        rows = _psql(f"SELECT contact_email FROM ged_clients WHERE id='{client_id}' LIMIT 1")
        if rows and rows[0].strip():
            return rows[0].strip()
        # Fallback por crm_contacts REMOVIDO (08/09/2026): era JOIN cartesiano — mandava o kit
        # (holerites) para o contato de OUTRO cliente. Sem e-mail no ged_clients, não envia.
        return None

    def _nome_mes(self, competencia: str) -> str:
        try:
            ano, mes = competencia.split("-")
            return f"{MESES_PT.get(mes, mes)} {ano}"
        except Exception:
            return competencia

    def _gerar_html_com_link(self, client_name: str, competencia: str, share_link: str, total_docs: int) -> str:
        """Gerar HTML do e-mail com link do Drive."""
        mes_nome = self._nome_mes(competencia)
        return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: Arial, sans-serif; color: #333; margin: 0; padding: 0; }}
    .header {{ background: #1E3A5F; padding: 24px; text-align: center; }}
    .header h1 {{ color: white; margin: 0; font-size: 22px; }}
    .header p {{ color: #CBD5E0; margin: 6px 0 0; font-size: 13px; }}
    .body {{ padding: 32px; }}
    .card {{ background: #F7FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 20px; margin: 20px 0; }}
    .btn {{ display: inline-block; background: #F97316; color: white; padding: 14px 28px; border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 15px; margin: 16px 0; }}
    .footer {{ background: #EDF2F7; padding: 16px; text-align: center; font-size: 11px; color: #718096; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>📁 Kit Documental — {mes_nome}</h1>
    <p>Conecta PRO · Conecta Mais Segurança e Tecnologia</p>
  </div>
  <div class="body">
    <p>Prezado(a) <strong>{client_name}</strong>,</p>
    <p>Seu kit documental referente a <strong>{mes_nome}</strong> está disponível no Google Drive.</p>
    <div class="card">
      <p><strong>📄 Total de documentos:</strong> {total_docs}</p>
      <p><strong>📅 Competência:</strong> {competencia}</p>
      <p><strong>🔒 Acesso:</strong> Qualquer pessoa com o link pode visualizar</p>
    </div>
    <center>
      <a href="{share_link}" class="btn">🗂️ Acessar Kit no Google Drive</a>
    </center>
    <p style="color:#718096;font-size:12px;">
      O link permanece disponível permanentemente. Você pode acessá-lo a qualquer momento.
    </p>
  </div>
  <div class="footer">
    Conecta Mais Segurança e Tecnologia · Sistema Conecta PRO · Este e-mail foi gerado automaticamente.
  </div>
</body>
</html>"""

    def _gerar_html_com_anexos(self, client_name: str, competencia: str, total_docs: int) -> str:
        """Gerar HTML do e-mail com anexos."""
        mes_nome = self._nome_mes(competencia)
        return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<style>
  body {{ font-family: Arial, sans-serif; color: #333; }}
  .header {{ background: #1E3A5F; padding: 24px; text-align: center; }}
  .header h1 {{ color: white; margin: 0; font-size: 22px; }}
  .body {{ padding: 32px; }}
  .footer {{ background: #EDF2F7; padding: 16px; text-align: center; font-size: 11px; color: #718096; }}
</style>
</head>
<body>
  <div class="header">
    <h1>📎 Kit Documental — {mes_nome}</h1>
  </div>
  <div class="body">
    <p>Prezado(a) <strong>{client_name}</strong>,</p>
    <p>Segue em anexo o kit documental referente a <strong>{mes_nome}</strong>.</p>
    <p><strong>{total_docs} documentos</strong> em anexo neste e-mail.</p>
  </div>
  <div class="footer">
    Conecta Mais Segurança e Tecnologia · Sistema Conecta PRO
  </div>
</body>
</html>"""

    def enviar_kit_por_email(
        self,
        client_id: str,
        competencia: str,
        share_link: str | None = None,
        destinatario_override: str | None = None,
    ) -> dict:
        """
        Enviar kit por e-mail.
        Decide automaticamente entre link e anexos baseado no tamanho.
        """
        # Buscar dados do cliente
        rows = _psql(f"SELECT name FROM clients WHERE id='{client_id}' LIMIT 1")
        if not rows:
            return {"sucesso": False, "erro": "Cliente não encontrado"}
        client_name = rows[0].strip()

        # Buscar e-mail
        email_dest = destinatario_override or self._buscar_email_cliente(client_id)
        if not email_dest:
            return {"sucesso": False, "erro": f"E-mail não cadastrado para {client_name}"}

        # Buscar documentos do kit
        docs = _psql(
            f"SELECT file_path, file_name, file_size "
            f"FROM ged_kit_documents gkd "
            f"JOIN ged_document_kits gdk ON gdk.id=gkd.kit_id "
            f"WHERE gdk.client_id='{client_id}' "
            f"AND gdk.reference_month LIKE '{competencia}%'"
        )

        total_size = 0
        arquivos = []
        for row in docs:
            p = row.split("|")
            if len(p) >= 2:
                size = int(p[2].strip() or 0) if len(p) > 2 else 0
                total_size += size
                arquivos.append({"path": p[0].strip(), "name": p[1].strip(), "size": size})

        cfg = self._config_smtp()

        # Decidir estratégia: link vs anexos
        usar_link = total_size > TAMANHO_MAX_ANEXO or share_link is not None

        # Buscar link do Drive se não fornecido
        if usar_link and not share_link:
            link_rows = _psql(
                f"SELECT share_link FROM gdrive_kits "
                f"WHERE client_id='{client_id}' "
                f"AND competencia='{competencia}' "
                f"AND status='concluido' LIMIT 1"
            )
            if link_rows:
                share_link = link_rows[0].strip()

        if usar_link and not share_link:
            return {
                "sucesso": False,
                "erro": "Kit grande mas sem link do Drive. Monte o kit no Drive primeiro.",
            }

        # Construir e-mail
        msg = MIMEMultipart("alternative" if usar_link else "mixed")
        mes_nome = self._nome_mes(competencia)
        msg["Subject"] = f"Kit Documental {client_name} — {mes_nome} | Conecta Mais"
        msg["From"] = cfg["from"]
        msg["To"] = email_dest

        if usar_link:
            html = self._gerar_html_com_link(client_name, competencia, share_link, len(arquivos))
            msg.attach(MIMEText(html, "html", "utf-8"))
        else:
            html = self._gerar_html_com_anexos(client_name, competencia, len(arquivos))
            msg.attach(MIMEText(html, "html", "utf-8"))
            for arq in arquivos:
                path = Path(arq["path"])
                if path.exists():
                    try:
                        with open(path, "rb") as f:
                            part = MIMEBase("application", "pdf")
                            part.set_payload(f.read())
                        encoders.encode_base64(part)
                        part.add_header("Content-Disposition", "attachment", filename=arq["name"])
                        msg.attach(part)
                    except Exception as e:
                        logger.warning("Falha ao anexar %s: %s", arq["name"], e)

        # Enviar — porta 465 = SSL direto (SMTP_SSL); porta 587 = STARTTLS
        try:
            _ctx = ssl.create_default_context()
            if cfg.get("ssl", cfg["port"] == 465):
                _conn: smtplib.SMTP = smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=_ctx)
            else:
                _conn = smtplib.SMTP(cfg["host"], cfg["port"])
                _conn.ehlo()
                _conn.starttls(context=_ctx)
            with _conn as server:
                if cfg["pass"]:
                    server.login(cfg["user"], cfg["pass"])
                server.sendmail(cfg["user"], email_dest, msg.as_bytes())

            logger.info(
                "E-mail enviado: %s → %s [%s]",
                client_name,
                email_dest,
                "link" if usar_link else "anexos",
            )
            return {
                "sucesso": True,
                "destinatario": email_dest,
                "estrategia": "link" if usar_link else "anexos",
                "total_docs": len(arquivos),
                "total_size_mb": round(total_size / 1024 / 1024, 2),
            }
        except Exception as e:
            logger.error("Falha ao enviar e-mail: %s", e)
            return {
                "sucesso": False,
                "erro": str(e),
                "dica": "Verificar SMTP_PASSWORD no .env — Gmail requer App Password",
            }


# Singleton
email_kit_service = EmailKitService()
