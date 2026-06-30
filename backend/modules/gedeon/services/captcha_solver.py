"""GEDEON — Solver de reCAPTCHA (2captcha) p/ emissão automática de CNDs.

Os portais de CND (SEFAZ-AM, Receita, Caixa) protegem a emissão com reCAPTCHA v2.
Este módulo resolve o reCAPTCHA via 2captcha: manda sitekey+URL → recebe o token.
Volume baixo (~10 CNDs/ano) → custo de centavos. Chave em TWOCAPTCHA_API_KEY.

API 2captcha: POST in.php (method=userrecaptcha) → id; GET res.php (poll) → token.
"""

from __future__ import annotations

import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

_IN = "https://2captcha.com/in.php"
_RES = "https://2captcha.com/res.php"


class CaptchaError(Exception):
    pass


def resolver_recaptcha_v2(sitekey: str, pageurl: str, timeout_s: int = 180, invisible: bool = False) -> str:
    """Resolve um reCAPTCHA v2 e devolve o g-recaptcha-response (token). Lança CaptchaError.
    invisible=True para reCAPTCHA v2 invisível (botão com classe g-recaptcha + data-callback)."""
    key = os.getenv("TWOCAPTCHA_API_KEY", "").strip()
    if not key:
        raise CaptchaError("TWOCAPTCHA_API_KEY não configurada")

    payload = {
        "key": key,
        "method": "userrecaptcha",
        "googlekey": sitekey,
        "pageurl": pageurl,
        "json": 1,
    }
    if invisible:
        payload["invisible"] = 1
    with httpx.Client(timeout=30) as cli:
        r = cli.post(_IN, data=payload)
        d = r.json()
        if d.get("status") != 1:
            raise CaptchaError(f"2captcha in.php recusou: {d.get('request')}")
        cap_id = d["request"]
        logger.info("2captcha: captcha enviado id=%s, aguardando solução...", cap_id)

        # poll (a solução de reCAPTCHA v2 leva ~15-40s)
        deadline = time.time() + timeout_s
        time.sleep(15)
        while time.time() < deadline:
            rr = cli.get(_RES, params={"key": key, "action": "get", "id": cap_id, "json": 1})
            dd = rr.json()
            if dd.get("status") == 1:
                logger.info("2captcha: token recebido (id=%s)", cap_id)
                return dd["request"]
            if dd.get("request") != "CAPCHA_NOT_READY":
                raise CaptchaError(f"2captcha res.php erro: {dd.get('request')}")
            time.sleep(5)
    raise CaptchaError("2captcha: timeout aguardando solução")


def saldo() -> float | None:
    """Saldo da conta 2captcha (USD). None se sem chave/erro."""
    key = os.getenv("TWOCAPTCHA_API_KEY", "").strip()
    if not key:
        return None
    try:
        with httpx.Client(timeout=15) as cli:
            r = cli.get(_RES, params={"key": key, "action": "getbalance", "json": 1})
            return float(r.json().get("request"))
    except Exception:
        return None
