"""GEDEON — Emissão automática da CND Estadual (SEFAZ-AM, não-contribuinte ICMS).

Fluxo real (decifrado do portal GAE/Struts):
  GET  emitirCertidaoNegativaNaoContPortal.do        → cookies/sessão (JSESSIONID)
  resolve reCAPTCHA v2 (sitekey abaixo) via 2captcha  → token
  POST mesma URL: nrDocumento=CNPJ, csCompleto=S, method=emitir, g-recaptcha-response=token
  resposta = PDF da certidão (ou HTML de resultado/erro)

Detecta NEGATIVA / POSITIVA COM EFEITO DE NEGATIVA / POSITIVA (Jordan tem parcelamentos,
então pode vir "positiva com efeito de negativa" — ainda válida — ou positiva pura — alertar).
"""

from __future__ import annotations

import logging
import re

import httpx

from modules.gedeon.services.captcha_solver import resolver_recaptcha_v2

logger = logging.getLogger(__name__)

SEFAZ_URL = (
    "https://sistemas.sefaz.am.gov.br/GAE/mnt/dividaAtiva/certidaoNegativa/emitirCertidaoNegativaNaoContPortal.do"
)
# o reCAPTCHA renderiza neste iframe (v2 INVISÍVEL)
SEFAZ_CAPTCHA_PAGE = "https://sistemas.sefaz.am.gov.br/GAE/html/recaptcha-script.html"
SITEKEY = "6Ld0oc4rAAAAAC_WFwEcD5Fx2sWOnwYg2wRIcYpc"  # pragma: allowlist secret


def _pdf_text(pdf: bytes) -> str:
    try:
        import fitz

        doc = fitz.open(stream=pdf, filetype="pdf")
        return "\n".join(p.get_text() for p in doc).upper()
    except Exception:
        return ""


def _classificar(texto: str) -> tuple[bool | None, str]:
    """(regular, situacao) a partir do texto da certidão."""
    t = texto.upper()
    if "EFEITO DE NEGATIVA" in t or "POSITIVA COM EFEITO" in t:
        return True, "positiva_com_efeito_negativa"  # parcelado — ainda regular p/ kit
    if "CERTID" in t and "NEGATIVA" in t and "POSITIVA" not in t:
        return True, "negativa"
    if "POSITIVA" in t:
        return False, "positiva"  # débito sem parcelamento — ALERTAR
    return None, "indeterminado"


def emitir_cnd_sefaz_am(cnpj: str) -> dict:
    """Emite a CND Estadual SEFAZ-AM. Devolve {ok, regular, situacao, pdf, mensagem}."""
    cnpj_d = re.sub(r"\D", "", cnpj)
    out: dict = {
        "portal": "SEFAZ-AM",
        "cnpj": cnpj_d,
        "ok": False,
        "regular": None,
        "situacao": None,
        "pdf": None,
        "mensagem": None,
    }
    try:
        with httpx.Client(
            verify=False, timeout=90, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}
        ) as cli:
            cli.get(SEFAZ_URL)  # estabelece sessão (JSESSIONID)
            token = resolver_recaptcha_v2(SITEKEY, SEFAZ_CAPTCHA_PAGE, invisible=True)
            r = cli.post(
                SEFAZ_URL,
                data={
                    "nrDocumento": cnpj_d,
                    "csCompleto": "S",
                    "g-recaptcha-response": token,
                    "method": "emitir",
                },
            )
            ct = (r.headers.get("content-type") or "").lower()
            is_pdf = "pdf" in ct or r.content[:4] == b"%PDF"
            if is_pdf:
                pdf = r.content
                regular, situacao = _classificar(_pdf_text(pdf))
                out.update(
                    ok=True,
                    regular=regular,
                    situacao=situacao,
                    pdf=pdf,
                    mensagem=f"PDF emitido ({len(pdf)} bytes), situação={situacao}",
                )
            else:
                # HTML de resultado/erro — extrai mensagem visível
                txt = re.sub(r"<[^>]+>", " ", r.text)
                txt = re.sub(r"\s+", " ", txt).strip()
                msg = re.search(r"(certid[ãa]o[^.]{0,120}|d[ée]bito[^.]{0,120}|erro[^.]{0,120})", txt, re.I) or [
                    None,
                    "",
                ]
                out["mensagem"] = (msg[0] if msg else txt[:200]) or "Sem PDF — resposta HTML"
                logger.warning("SEFAZ-AM não retornou PDF (status %s, ct=%s)", r.status_code, ct)
    except Exception as exc:
        out["mensagem"] = f"erro: {exc}"
        logger.warning("SEFAZ-AM emitir_cnd falhou: %s", exc)
    return out
