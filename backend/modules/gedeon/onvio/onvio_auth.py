#!/usr/bin/env python3
"""
GEDEON Fase 3 — Onvio Headless Auth via HTTP (sem Playwright)

Fluxo OIDC completo:
  1. POST /api/security/v1/oidc/login  → URL Auth0 (auth.thomsonreuters.com)
  2. GET  identifier page              → form com state
  3. POST email (username step)        → redireciona para password
  4. POST senha (password step)        → redireciona para MFA
  5. POST MFA via email OTP            → IMAP lê código do inbox
  6. Salva cookies no Redis (TTL 16h)

Config:
  IMAP_PASSWORD: senha do inbox de ONVIO_EMAIL no imap.titan.email
  Se vazio, entra em modo interativo (pede código na stdin).

Seletores e endpoints confirmados por inspeção real (2026-04-17):
  - POST body: {"type":"clientcenter","sp":"clientcenter","lang":"pt-BR",
                "redirectUri":"https://onvio.com.br/clientcenter/pt/"}
  - MFA email trigger: POST mfa-login-options com action=email::1
  - OTP input name: code
"""

import email
import imaplib
import json
import os
import re
import ssl
import time
from datetime import datetime

import redis
import requests
from bs4 import BeautifulSoup

try:
    from dotenv import load_dotenv

    load_dotenv("/opt/conecta-pro/.env")
except ImportError:
    pass  # dotenv opcional — vars podem vir do ambiente do container

# ── Configuração ─────────────────────────────────────────────────────────────

ONVIO_URL = "https://onvio.com.br/clientcenter/pt/auth"
ONVIO_EMAIL = "administracao@conectamaistech.com.br"
ONVIO_PASS = os.getenv("ONVIO_PASS", "")

# IMAP para leitura automática do código MFA via e-mail
IMAP_SERVER = "imap.titan.email"
IMAP_PORT = 993
IMAP_PASSWORD = os.getenv("ONVIO_IMAP_PASSWORD", "")  # pragma: allowlist secret

REDIS_KEY = "onvio:session"
REDIS_TTL = 57600  # 16 horas
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/1")

# ── HTTP Session ──────────────────────────────────────────────────────────────

_SESSION = requests.Session()
_SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _soup(r: requests.Response) -> BeautifulSoup:
    return BeautifulSoup(r.text, "html.parser")


def _state(soup: BeautifulSoup) -> str:
    inp = soup.find("input", {"name": "state"})
    if not inp:
        raise RuntimeError("State input não encontrado na página")
    return inp["value"]


def _read_otp_from_imap(timeout_s: int = 90) -> str | None:
    """Lê o código OTP do email de MFA via IMAP. Retorna None se não encontrar."""
    if not IMAP_PASSWORD:
        return None

    deadline = time.time() + timeout_s
    print("  [IMAP] Aguardando email OTP...")

    while time.time() < deadline:
        try:
            ctx = ssl.create_default_context()
            imap = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT, ssl_context=ctx)
            imap.login(ONVIO_EMAIL, IMAP_PASSWORD)
            imap.select("INBOX")
            _, msgs = imap.search(None, 'UNSEEN FROM "thomsonreuters.com"')
            ids = msgs[0].split()
            if ids:
                _, data = imap.fetch(ids[-1], "(RFC822)")
                msg = email.message_from_bytes(data[0][1])
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                            break
                else:
                    body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

                # Procura código de 6 dígitos isolado em linha própria
                # Ignora contextos CSS (#color), URLs e atributos HTML
                otp = None
                for line in body.split("\n"):
                    stripped = line.strip()
                    # Linha com apenas 6 dígitos (possível espaço antes/depois)
                    if re.match(r"^\d{6}$", stripped):
                        otp = stripped
                        break
                # Fallback: 6 dígitos não precedidos por # (CSS) nem em URL
                if not otp:
                    clean = re.sub(r"#[0-9a-fA-F]{3,6}", "", body)
                    clean = re.sub(r"https?://\S+", "", clean)
                    found = re.findall(r"(?<![/\-=&])\b(\d{6})\b(?![/\-=&])", clean)
                    non_zero = [c for c in found if c not in ("000000",)]
                    if non_zero:
                        otp = non_zero[0]
                if otp:
                    imap.logout()
                    print(f"  [IMAP] Código encontrado: {otp}")
                    return otp
            imap.logout()
        except Exception as e:
            print(f"  [IMAP] Erro: {e}")

        time.sleep(5)

    return None


# ── Auth Flow ─────────────────────────────────────────────────────────────────


def login_onvio() -> dict:
    # Sessão fresca a cada execução — sem cookies residuais de runs anteriores
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        }
    )

    # STEP 1 — página inicial (obtém cookies de sessão)
    print("[1/6] Carregando página de auth Onvio...")
    s.headers["Accept"] = "text/html,application/xhtml+xml,*/*"
    s.get(ONVIO_URL, timeout=30)

    # STEP 2 — POST OIDC para obter URL Auth0
    print("[2/6] Iniciando OIDC login...")
    s.headers.update(
        {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://onvio.com.br",
            "Referer": ONVIO_URL,
        }
    )
    r2 = s.post(
        "https://onvio.com.br/api/security/v1/oidc/login",
        json={
            "type": "clientcenter",
            "sp": "clientcenter",
            "lang": "pt-BR",
            "redirectUri": "https://onvio.com.br/clientcenter/pt/",
        },
        allow_redirects=False,
        timeout=30,
    )
    auth0_url = r2.headers.get("location") or r2.headers.get("Location")
    if not auth0_url:
        raise RuntimeError(f"OIDC login falhou: {r2.status_code} — {r2.text[:200]}")
    print("  Auth0 URL obtida ✅")

    # STEP 3 — GET página de identificador Auth0
    print("[3/6] Carregando página de login Auth0...")
    s.headers.update({"Accept": "text/html,application/xhtml+xml,*/*", "Referer": "https://onvio.com.br/"})
    r3 = s.get(auth0_url, timeout=30)
    soup3 = _soup(r3)
    state = _state(soup3)
    login_url = r3.url

    # STEP 4 — POST email
    print("[4/6] Enviando e-mail...")
    s.headers.update(
        {
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://auth.thomsonreuters.com",
            "Referer": login_url,
        }
    )
    r4 = s.post(
        login_url,
        data={
            "state": state,
            "username": ONVIO_EMAIL,
            "js-available": "true",
            "webauthn-available": "false",
            "is-brave": "false",
            "webauthn-platform-available": "false",
            "action": "default",
        },
        timeout=30,
    )
    soup4 = _soup(r4)
    state4 = _state(soup4)
    pwd_url = r4.url

    if "password" not in r4.url and not soup4.find("input", {"type": "password"}):
        raise RuntimeError(f"Esperado página de senha, obteve: {r4.url[:100]}")

    # STEP 5 — POST senha
    print("[5/6] Enviando senha...")
    s.headers["Referer"] = pwd_url
    r5 = s.post(
        pwd_url,
        data={"state": state4, "password": ONVIO_PASS, "action": "default"},
        timeout=30,
    )

    # Verifica se autenticou ou se está na página de MFA
    if "onvio.com.br" in r5.url and "auth" not in r5.url:
        print("  Login completo sem MFA ✅")
        return _extract_session(s, r5)

    # Auth0 pode redirecionar para resume (device já conhecido) ou MFA
    if "authorize/resume" in r5.url:
        print("  Auth0 resume state detectado — processando auto-submit form...")
        soup_resume = _soup(r5)
        form = soup_resume.find("form")
        if form and form.get("action"):
            hidden = {
                i["name"]: i.get("value", "") for i in form.find_all("input", {"type": "hidden"}) if i.get("name")
            }
            print(f"  POST → {form['action'][:80]} | campos: {list(hidden.keys())}")
            s.headers.update(
                {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": "https://auth.thomsonreuters.com",
                    "Referer": r5.url,
                }
            )
            r_resume = s.post(form["action"], data=hidden, allow_redirects=True, timeout=30)
            print(f"  Após resume POST: {r_resume.url[:120]}")
            if "onvio.com.br" in r_resume.url:
                print("  Login via resume completo ✅")
                return _extract_session_with_token(s, r_resume)
            # Atualizar r5 para continuar fluxo MFA se necessário
            r5 = r_resume

    if "mfa" in r5.url or "mfa" in r5.text.lower():
        print("[6/6] MFA requerido — disparando email OTP...")
        soup5 = _soup(r5)
        state5 = _state(soup5)
        mfa_url = r5.url

        s.headers["Referer"] = mfa_url
        r6 = s.post(
            mfa_url,
            data={"state": state5, "action": "email::1"},
            timeout=30,
        )
        otp_url = r6.url
        soup6 = _soup(r6)
        state6 = _state(soup6)

        print("  Email OTP disparado. Aguardando código...")

        # Tenta ler o código via IMAP
        otp_code = _read_otp_from_imap(timeout_s=90)

        if not otp_code:
            print("\n  ⚠️  IMAP não configurado ou código não encontrado.")
            print(f"  Verifique o inbox de {ONVIO_EMAIL} e informe o código:")
            otp_code = input("  Código OTP (6 dígitos): ").strip()

        if not otp_code:
            raise RuntimeError("Código OTP não fornecido")

        # POST código OTP
        print(f"  Submetendo OTP {otp_code}...")
        s.headers["Referer"] = otp_url
        r7 = s.post(
            otp_url,
            data={"state": state6, "code": otp_code, "action": "default"},
            allow_redirects=True,
            timeout=30,
        )

        if "onvio.com.br" in r7.url:
            # SPA Angular troca o code pelo token via /auth-code/session
            return _extract_session_with_token(s, r7)

        # Possível auto-submit form (Auth0 form_post)
        soup7 = _soup(r7)
        form = soup7.find("form")
        if form and form.get("action"):
            hidden = {i["name"]: i.get("value", "") for i in form.find_all("input", {"type": "hidden"})}
            r8 = s.post(form["action"], data=hidden, timeout=30)
            if "onvio.com.br" in r8.url:
                print("  Auth0 callback completo ✅")
                return _extract_session_with_token(s, r8)

        raise RuntimeError(f"Login falhou após MFA. URL final: {r7.url[:150]}")

    raise RuntimeError(f"Estado inesperado após senha. URL: {r5.url[:150]}")


def _extract_session_with_token(s: requests.Session, final_resp: requests.Response) -> dict:
    """
    Fluxo completo de troca de tokens:
      1. POST /api/security/v1/oidc/auth-code/session  → JWT (tokenValue)
      2. POST /api/security/v3/sessions/jwt             → LongToken (UDS session)
      3. Usar Authorization: UDSLongToken <LongToken>   em todas as chamadas
    """
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(final_resp.url)
    qs = parse_qs(parsed.query)
    code = (qs.get("code") or [None])[0]
    state = (qs.get("state") or [None])[0]

    jwt_token = None
    long_token = None

    if code:
        print("  [1/2] Trocando code OAuth pelo JWT (tokenValue)...")
        s.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://onvio.com.br",
                "Referer": "https://onvio.com.br/clientcenter/pt/",
            }
        )
        token_url = "https://onvio.com.br/api/security/v1/oidc/auth-code/session"
        form_data = {"code": code}
        if state:
            form_data["state"] = state
        # Endpoint JAX-RS com @FormParam — exige x-www-form-urlencoded no body
        r_token = s.post(token_url, data=form_data, timeout=30)
        print(f"  auth-code/session: {r_token.status_code}")

        try:
            data = r_token.json()
            jwt_token = (
                data.get("tokenValue")  # Onvio JWT (campo real)
                or data.get("accessToken")
                or data.get("access_token")
                or data.get("token")
                or data.get("id_token")
            )
            if jwt_token:
                print(f"  ✅ JWT obtido ({len(jwt_token)} chars)")
        except Exception:
            print(f"  Token response (text): {r_token.text[:200]}")

        # Passo 2: trocar JWT pelo LongToken (UDS session token)
        if jwt_token:
            print("  [2/2] Obtendo UDS LongToken...")
            s.headers.update(
                {
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {jwt_token}",
                    "Origin": "https://onvio.com.br",
                    "Referer": "https://onvio.com.br/clientcenter/pt/",
                }
            )
            r_long = s.post(
                "https://onvio.com.br/api/security/v3/sessions/jwt",
                json=None,
                timeout=30,
            )
            print(f"  v3/sessions/jwt: {r_long.status_code}")
            try:
                long_data = r_long.json()
                long_token = long_data.get("LongToken") or long_data.get("token")
                if long_token:
                    print(f"  ✅ LongToken obtido ({len(long_token)} chars)")
                else:
                    print(f"  ⚠️  LongToken não encontrado: {long_data}")
            except Exception:
                print(f"  v3/sessions/jwt response: {r_long.text[:200]}")
    else:
        print("  ⚠️  URL sem code — usando apenas cookies Auth0")

    cookies = {c.name: c.value for c in s.cookies}
    auth0_cookies = {k: v for k, v in cookies.items() if k.startswith("auth0") or k in ("did", "did_compat")}
    onvio_cookies = {k: v for k, v in cookies.items() if k not in auth0_cookies}

    return {
        "cookies": cookies,
        "auth0_cookies": auth0_cookies,
        "onvio_cookies": onvio_cookies,
        "uds_token": jwt_token,  # JWT (para referência)
        "long_token": long_token,  # LongToken — usar em Authorization: UDSLongToken
        "final_url": final_resp.url,
        "extracted_at": time.time(),
        "extracted_at_iso": datetime.utcnow().isoformat() + "Z",
    }


def _extract_session(s: requests.Session, final_resp: requests.Response) -> dict:
    """Alias para retrocompatibilidade."""
    return _extract_session_with_token(s, final_resp)


# ── Redis ─────────────────────────────────────────────────────────────────────


def save_to_redis(session_data: dict) -> bool:
    r = redis.from_url(REDIS_URL)
    r.setex(REDIS_KEY, REDIS_TTL, json.dumps(session_data))
    print("\n✅ Sessão salva no Redis")
    print(f"   Key:     {REDIS_KEY}")
    print(f"   TTL:     {REDIS_TTL // 3600}h ({REDIS_TTL}s)")
    print(f"   Cookies: {list(session_data['cookies'].keys())}")
    print(f"   UDS Token: {'✅' if session_data.get('uds_token') else '❌ não obtido'}")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🔐 GEDEON Onvio Auth — Iniciando login OIDC...\n")
    session_data = login_onvio()
    save_to_redis(session_data)
    print("\n✅ Concluído. Backend pode usar onvio:session do Redis.")
    print(f"   URL final: {session_data['final_url'][:100]}")
