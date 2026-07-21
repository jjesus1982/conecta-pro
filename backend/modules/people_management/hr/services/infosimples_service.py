"""Encaixe da API Infosimples para verificação de candidatos (KYC/due-diligence por CPF).

INERTE até existir `INFOSIMPLES_TOKEN` no ambiente (raiz `/opt/conecta-pro/.env`).
Sem token, `habilitado()` é False e os checks caem em 'pendente' (não fabrica nada).

Contrato v2 (documentado pela Infosimples):
  POST https://api.infosimples.com/api/v2/consultas/<path>
  form: token, timeout(=600), + args da consulta
  resposta JSON: {code, code_message, data:[...], site_receipts:[urls_pdf], errors, header}
    code == 200  → sucesso; data traz os campos; site_receipts traz o(s) PDF(s) da certidão.

⚠️ A interpretação de `data` (nada consta × consta) é best-effort e deve ser conferida
contra a PRIMEIRA resposta real quando o token chegar (ver `_tem_consta`).
"""
from __future__ import annotations

import os
import re
from typing import Any

import httpx

_BASE = "https://api.infosimples.com/api/v2/consultas"

# apelido interno → PATH EXATO do serviço na API Infosimples (usa BARRAS, não hífen)
CONSULTAS = {
    "antecedentes_pf": "antecedentes-criminais/pf/emit",   # SINIC — antecedentes criminais nacional
    "mandados_prisao": "cnj/mandados-prisao",              # BNMP — mandados de prisão em aberto
    "cndt": "tribunal/tst/cndt",                           # débitos trabalhistas (nacional)
    "receita_cpf": "receita-federal/cpf",                  # situação cadastral do CPF
    "improbidade": "cnj/improbidade",                      # improbidade administrativa + inelegibilidade
    "trabalho_escravo": "sit/trabalho-escravo",            # lista suja do trabalho escravo
    "ceis": "portal-transparencia/ceis",                   # inidôneos/suspensos
    "cnep": "portal-transparencia/cnep",                   # empresas punidas
    "trf_unificada": "tribunal/trf/cert-unificada",        # Justiça Federal unificada (TRF2-5)
    "trf1": "tribunal/trf1/certidao",                      # TRF1 (cobre o AM)
}


def _token() -> str:
    return (os.getenv("INFOSIMPLES_TOKEN") or "").strip()


def habilitado() -> bool:
    """True só quando o token está configurado — o gate que mantém tudo inerte."""
    return bool(_token())


def consultar(consulta_key: str, params: dict[str, Any], timeout: int = 600) -> dict[str, Any]:
    """Consulta genérica. Retorna {ok, inativo, code, code_message, data, receipts, msg}.
    NUNCA levanta — erro/timeout/sem-token vira ok=False (o chamador trata como 'pendente')."""
    tok = _token()
    if not tok:
        return {"ok": False, "inativo": True, "msg": "INFOSIMPLES_TOKEN ausente"}
    path = CONSULTAS.get(consulta_key, consulta_key)
    body = {"token": tok, "timeout": timeout}
    body.update({k: v for k, v in params.items() if v not in (None, "")})
    try:
        r = httpx.post(f"{_BASE}/{path}", data=body, timeout=timeout + 30)
        j = r.json()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "msg": f"falha na chamada Infosimples ({str(e)[:60]})"}
    code = j.get("code")
    return {
        "ok": code == 200,
        "code": code,
        "code_message": j.get("code_message"),
        "data": j.get("data") or [],
        "receipts": j.get("site_receipts") or [],
        "raw": j,
    }


def baixar_receipt(url: str) -> bytes | None:
    """Baixa o PDF de um site_receipt. Retorna bytes do PDF ou None."""
    if not url:
        return None
    try:
        r = httpx.get(url, timeout=90, follow_redirects=True)
        if r.content[:4] == b"%PDF":
            return r.content
    except Exception:  # noqa: BLE001
        return None
    return None


def primeiro_pdf(res: dict[str, Any]) -> bytes | None:
    """Primeiro PDF válido dentre os site_receipts da resposta."""
    for u in (res.get("receipts") or []):
        b = baixar_receipt(u if isinstance(u, str) else (u.get("url") if isinstance(u, dict) else ""))
        if b:
            return b
    return None


# palavras que, presentes no texto da resposta, indicam REGISTRO/PENDÊNCIA (não "nada consta")
_MARCA_CONSTA = re.compile(
    r"\b(consta[m]?\b(?!\s+nada)|positiv|inadimpl|mandado|em aberto|processo|apenad|conden|sanç|inid[oô]ne|suspens|impedid)",
    re.IGNORECASE,
)
_MARCA_NADA = re.compile(r"nada\s+consta|nao\s+consta|não\s+consta|negativ|sem\s+registro", re.IGNORECASE)


def certidao_negativa(res: dict[str, Any]) -> bool:
    """True se a resposta traz flag CONFIÁVEL de certidão negativa (nada consta) —
    melhor que regex. Ex.: antecedentes PF devolve `conseguiu_emitir_certidao_negativa`."""
    for d in (res.get("data") or []):
        if isinstance(d, dict):
            for k in ("conseguiu_emitir_certidao_negativa", "certidao_negativa", "nada_consta", "consta_nada"):
                if d.get(k) is True:
                    return True
    return False


def _tem_consta(res: dict[str, Any]) -> bool | None:
    """Best-effort: True se a resposta indica REGISTRO, False se 'nada consta', None se ambíguo.
    ⚠️ Conferir contra a resposta real quando o token chegar."""
    import json as _json
    blob = _json.dumps(res.get("data") or [], ensure_ascii=False).lower()
    if not blob or blob == "[]":
        blob = _json.dumps(res.get("raw") or {}, ensure_ascii=False).lower()
    if _MARCA_NADA.search(blob) and not _MARCA_CONSTA.search(blob):
        return False
    if _MARCA_CONSTA.search(blob):
        return True
    return None
