"""Lê a caixa de e-mail e transforma boleto recebido em conta a pagar.

Fecha a cegueira que o `radar_fornecedores_service` não fecha: aquele olha o histórico de
pagamento, então só enxerga quem a empresa JÁ pagou. Boleto de fornecedor novo, cobrança
avulsa, conta de um posto recém-aberto — nada disso tem histórico, e ninguém sabe que
existe até o dinheiro sair (ou o boleto vencer, que foi o caso da Full Telecom em 19/08:
R$4,48 de juros e 30 dias sem saber que devia).

O ideal seria DDA — o banco entrega todo boleto emitido contra o CNPJ, tenha a gente
pago antes ou não. Sondado em 19/08: `dda.read`, `boleto-dda.read` e `pagamento-dda.read`
devolvem "No registered scope value for this client" no Inter, ou seja, não liberado para
a nossa aplicação. Enquanto não liberam, o e-mail é a fonte que não depende de terceiro.

⚠️ **Só cria pagável com código de barras VÁLIDO.** O `boleto_codigo` confere os dígitos
verificadores; CNPJ, número de contrato e chave de NFS-e — que também são sequências
longas num PDF — são recusados. Sem isso, o radar inventaria dívida.

⚠️ **Idempotente no BANCO**, por `uq_payable_boleto_email` (migration 42ddd4d1cb20), não
por SELECT antes do INSERT: o mesmo boleto chega mais de uma vez de verdade (fornecedor
reenvia, alguém encaminha), e duas execuções passariam as duas pela verificação.

⚠️ **Não paga nada.** Registrar a obrigação ≠ pagar. Pagamento segue com os gates de
sempre, OTP incluído.

Caixa: `BOLETO_IMAP_*` no .env; sem isso cai nas credenciais de SMTP. O host IMAP é
derivado do SMTP (`smtp.hostinger.com` → `imap.hostinger.com`) porque é o mesmo provedor.
"""

from __future__ import annotations

import email
import imaplib
import logging
import os
import re
from datetime import date, datetime, timedelta
from email.header import decode_header

from sqlalchemy import text

from modules.financial.services.boleto_codigo import achar_boletos

logger = logging.getLogger(__name__)

#: Janela de leitura. 30 dias cobre boleto enviado com antecedência sem reprocessar a
#: caixa inteira toda madrugada.
DIAS_JANELA = 30

#: Teto de mensagens por rodada — caixa grande não pode fazer a tarefa rodar por horas.
MAX_MENSAGENS = 300


def _conf() -> tuple[str, str, str, str]:
    usuario = os.getenv("BOLETO_IMAP_USER") or os.getenv("SMTP_USERNAME") or ""
    senha = os.getenv("BOLETO_IMAP_PASSWORD") or os.getenv("SMTP_PASSWORD") or ""
    host = os.getenv("BOLETO_IMAP_HOST") or (
        os.getenv("SMTP_HOST", "").replace("smtp.", "imap.") or "imap.hostinger.com")
    pasta = os.getenv("BOLETO_IMAP_FOLDER", "INBOX")
    return usuario, senha, host, pasta


def _decodificar_cabecalho(valor: str | None) -> str:
    if not valor:
        return ""
    partes = []
    for texto, codec in decode_header(valor):
        if isinstance(texto, bytes):
            partes.append(texto.decode(codec or "utf-8", "ignore"))
        else:
            partes.append(texto)
    return "".join(partes)


def _texto_do_pdf(dados: bytes) -> str:
    try:
        import pymupdf

        with pymupdf.open(stream=dados, filetype="pdf") as doc:
            return "\n".join(p.get_text() for p in doc)
    except Exception as exc:  # noqa: BLE001 — PDF ilegível não pode derrubar a rodada
        logger.warning("boleto_email: PDF ilegível (%s)", exc)
        return ""


def _remetente(cabecalho: str) -> tuple[str, str]:
    """('Nome Bonito', 'email@dominio') a partir do cabeçalho From."""
    m = re.match(r"\s*(.*?)\s*<([^>]+)>", cabecalho or "")
    if m:
        return m.group(1).strip('" ') or m.group(2).split("@")[0], m.group(2).lower()
    return (cabecalho or "").split("@")[0], (cabecalho or "").strip().lower()


#: Razão social dentro do documento: linha que termina em sufixo societário.
_RAZAO_SOCIAL = re.compile(
    r"(?m)^[ \t]*([A-ZÀ-Ú][A-ZÀ-Ú0-9&.\- ]{4,60}?\s(?:LTDA|S/?A|S\.A\.?|ME|EPP|EIRELI)\b\.?)")


def _fornecedor(nome_from: str, dominio: str, texto: str, documento: str = "") -> str:
    """Quem está cobrando. O DOCUMENTO ganha do remetente.

    Ordem: razão social impressa no boleto → nome do remetente → domínio. O boleto traz
    o cedente por obrigação; o e-mail pode vir de "cobranca@", de um portal terceirizado
    ou até de dentro de casa quando alguém encaminha — e aí o remetente aponta para a
    empresa errada. Foi o que aconteceu no primeiro teste: o PDF dizia FULL TELECOM e o
    fornecedor saiu CONECTAMAIS, que é quem encaminhou.
    """
    m = _RAZAO_SOCIAL.search(documento or "")
    if m:
        return " ".join(m.group(1).split())[:120]

    generico = re.compile(
        r"(?i)^(cobranc|cobran|financeiro|faturamento|nao-?responda|no-?reply|boleto|"
        r"atendimento|contato|sac|billing|suporte)")
    nome = (nome_from or "").strip()
    if not nome or generico.match(nome):
        alvo = (dominio.split("@")[-1] or "").split(".")[0]
        nome = alvo.upper() if alvo else "FORNECEDOR"
    return nome[:120]


def varrer_e_registrar(db, dias: int = DIAS_JANELA, criar: bool = True) -> dict:
    """Lê a caixa, acha boletos válidos e registra os que ainda não existem."""
    usuario, senha, host, pasta = _conf()
    rel = {"caixa": usuario, "mensagens": 0, "com_boleto": 0,
           "criados": 0, "ja_existiam": 0, "boletos": [], "erro": None}
    if not usuario or not senha:
        rel["erro"] = "credenciais IMAP ausentes (BOLETO_IMAP_* ou SMTP_*)"
        return rel

    desde = (date.today() - timedelta(days=dias)).strftime("%d-%b-%Y")
    try:
        M = imaplib.IMAP4_SSL(host, 993, timeout=60)
        M.login(usuario, senha)
        M.select(pasta, readonly=True)
        ok, dados = M.search(None, f'(SINCE "{desde}")')
        ids = dados[0].split()[-MAX_MENSAGENS:]
        rel["mensagens"] = len(ids)

        for num in ids:
            ok, bruto = M.fetch(num, "(RFC822)")
            if not bruto or not bruto[0]:
                continue
            msg = email.message_from_bytes(bruto[0][1])
            achados, texto_doc = _boletos_da_mensagem(msg)
            if not achados:
                continue
            rel["com_boleto"] += 1

            nome_from, endereco = _remetente(_decodificar_cabecalho(msg.get("From")))
            assunto = _decodificar_cabecalho(msg.get("Subject"))[:200]
            fornecedor = _fornecedor(nome_from, endereco, assunto, texto_doc)

            for b in achados:
                item = {
                    "fornecedor": fornecedor, "remetente": endereco,
                    "assunto": assunto, "valor": b["valor"],
                    "vencimento": b["vencimento"].isoformat() if b["vencimento"] else None,
                    "barras": b["barras"], "tipo": b["tipo"],
                }
                if criar:
                    item["situacao"] = _registrar(db, item, b)
                    rel["criados" if item["situacao"] == "criado" else "ja_existiam"] += 1
                rel["boletos"].append(item)
        M.logout()
    except Exception as exc:  # noqa: BLE001
        rel["erro"] = f"{type(exc).__name__}: {exc}"[:200]
        logger.warning("boleto_email: %s", rel["erro"])
    return rel


def _boletos_da_mensagem(msg) -> tuple[list[dict], str]:
    """(boletos válidos, texto lido) do corpo e dos PDFs anexos."""
    pedacos = []
    for parte in msg.walk():
        tipo = parte.get_content_type()
        nome = _decodificar_cabecalho(parte.get_filename())
        try:
            if tipo == "application/pdf" or nome.lower().endswith(".pdf"):
                dados = parte.get_payload(decode=True) or b""
                pedacos.append(_texto_do_pdf(dados))
            elif tipo in ("text/plain", "text/html"):
                dados = parte.get_payload(decode=True) or b""
                txt = dados.decode(parte.get_content_charset() or "utf-8", "ignore")
                # HTML quebra a linha digitável com tags no meio; tirar as tags junta
                # os dígitos que o padrão precisa ver contíguos.
                pedacos.append(re.sub(r"<[^>]+>", " ", txt))
        except Exception as exc:  # noqa: BLE001
            logger.warning("boleto_email: parte ilegível (%s)", exc)
    texto = "\n".join(pedacos)
    return achar_boletos(texto), texto


def _registrar(db, item: dict, b: dict) -> str:
    """Cria o pagável. Devolve 'criado' ou 'ja_existia'."""
    # Convênio não traz vencimento no código (água/luz/tributo). Registrar com data
    # inventada seria afirmar prazo; usamos hoje e DIZEMOS isso em notes, para a tela
    # mostrar que a data precisa de confirmação humana.
    venc = b["vencimento"] or date.today()
    nota = (
        f"Boleto recebido por e-mail de {item['remetente']} em "
        f"{datetime.now().strftime('%d/%m/%Y %H:%M')}. Assunto: {item['assunto']}. "
        f"Código de barras validado (DV confere)."
    )
    if not b["vencimento"]:
        nota += (" ⚠️ VENCIMENTO NÃO CONFIRMADO: boleto de convênio não carrega a data "
                 "no código de barras — conferir no documento antes de pagar.")

    cond = db.execute(text("SELECT condominio_id FROM payable_accounts LIMIT 1")).scalar()
    r = db.execute(text("""
        INSERT INTO payable_accounts
            (id, condominio_id, description, supplier_name, document_number,
             gross_value, net_value, issue_date, due_date, status, origem, notes,
             created_at, updated_at)
        VALUES (gen_random_uuid(), :cond, :desc, :forn, :doc, :val, :val, CURRENT_DATE,
                :venc, 'pendente', 'boleto_email', :nota, NOW(), NOW())
        ON CONFLICT DO NOTHING
    """), {"cond": cond, "desc": f"Boleto {item['fornecedor']}"[:500],
           "forn": item["fornecedor"], "doc": b["barras"][:50],
           "val": b["valor"], "venc": venc, "nota": nota})
    db.commit()
    return "criado" if r.rowcount else "ja_existia"
