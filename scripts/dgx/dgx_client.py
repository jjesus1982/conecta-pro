#!/usr/bin/env python3
"""Cliente do DGX (trial da Conecta Mais) para a passagem completa de 24/09/2026.

Login por Playwright (o formulário é MVC com antiforgery + Cloudflare), cookies passados a um
`requests.Session` para os formulários `/X/Index`, `/X/Incluir`, `/X/Salvar`, `/X/Lista`, e Bearer de
`GET /Usuarios/token` (JWT 15 min, renovado sozinho) para `/api/<area>/<entidade>/{combo,filtro,{id}}`.

    from dgx_client import DGX
    d = DGX()                       # loga como Master na PATRIMONIAL
    html = d.get("/Colaboradores/Index").text
    form = d.form("/Colaboradores/Incluir")         # {action, method, fields:{name: {type, options}}}
    r = d.salvar("/Colaboradores/Salvar", {...})    # POST x-www-form-urlencoded com o antiforgery
    lista = d.api_post("/api/RH/Colaboradores/filtro", {})  # {lista, total, legendas}
    combo = d.api_get("/api/RH/Funcoes/combo")
    d.page  # a página Playwright, para clicar o que não é formulário (telas /view/ e /frontend/)

Regras: tudo que criar lá se chama "TESTE CP <frente>" e é apagado no fim quando houver Excluir.
NUNCA gravar a senha do banco que vaza em /api/Escoltas/Filiais (achado de segurança, já registrado).
"""
from __future__ import annotations

import json
import re
import time

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE = "https://conectamais.dgxbrasil.com.br"
USER, PASS, EMPRESA = "Master", "ConectaMais23092026", "CONECTAMAIS PATRIMONIAL"


class DGX:
    def __init__(self, headless: bool = True):
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=headless)
        self.ctx = self.browser.new_context(locale="pt-BR", timezone_id="America/Manaus")
        self.page = self.ctx.new_page()
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) ConectaPRO-DGX-teste"
        self._tok, self._tok_at = None, 0.0
        self.login()

    # ---------- sessão ----------
    def login(self) -> None:
        p = self.page
        p.goto(f"{BASE}/Usuarios/Logon", wait_until="domcontentloaded")
        p.get_by_role("combobox").first.select_option(EMPRESA)
        p.locator("#tbUsuario").fill(USER)
        p.locator('input[name="Password"]').fill(PASS)
        p.get_by_role("button", name="Entrar").click()
        try:
            p.wait_for_url(re.compile(r"/Home"), timeout=20000)
        except Exception:
            p.goto(f"{BASE}/Home/Index", wait_until="domcontentloaded")
        assert "Logon" not in p.url, f"login falhou: {p.url}"
        self.sync_cookies()

    def sync_cookies(self) -> None:
        for c in self.ctx.cookies():
            if "dgxbrasil" in c["domain"]:
                self.s.cookies.set(c["name"], c["value"], domain=c["domain"], path=c["path"])

    def token(self) -> str:
        if not self._tok or time.time() - self._tok_at > 600:
            r = self.s.get(f"{BASE}/Usuarios/token", timeout=30)
            r.raise_for_status()
            self._tok, self._tok_at = json.loads(r.text)["token"], time.time()
        return self._tok

    # ---------- MVC ----------
    def get(self, path: str, **kw) -> requests.Response:
        r = self.s.get(BASE + path, timeout=60, **kw)
        if "/Usuarios/Logon" in r.url:
            self.login()
            r = self.s.get(BASE + path, timeout=60, **kw)
        return r

    def form(self, path: str) -> dict:
        """Lê o formulário de um modal `/X/Incluir` (ou `/X/Edit/{id}`): action, campos, opções."""
        html = self.get(path).text
        soup = BeautifulSoup(html, "lxml")
        f = soup.find("form") or soup
        campos: dict[str, dict] = {}
        for el in f.find_all(["input", "select", "textarea"]):
            nome = el.get("name") or el.get("id")
            if not nome:
                continue
            item = {"tag": el.name, "type": el.get("type", el.name), "value": el.get("value", "")}
            if el.name == "select":
                item["options"] = [(o.get("value", ""), o.get_text(strip=True)) for o in el.find_all("option")]
            campos[nome] = item
        return {"action": (f.get("action") if f is not soup else None), "method": (f.get("method") if f is not soup else None),
                "fields": campos, "html_len": len(html)}

    def salvar(self, path: str, dados: dict, referer: str | None = None) -> requests.Response:
        """POST de formulário MVC. Inclui o antiforgery se o modal tiver."""
        dados = dict(dados)
        if "__RequestVerificationToken" not in dados:
            tok = self._antiforgery(referer or path.replace("/Salvar", "/Incluir"))
            if tok:
                dados["__RequestVerificationToken"] = tok
        r = self.s.post(BASE + path, data=dados, timeout=60, headers={"X-Requested-With": "XMLHttpRequest",
                                                                       "Referer": BASE + (referer or "/")})
        return r

    def _antiforgery(self, path: str) -> str | None:
        try:
            html = self.get(path).text
        except Exception:
            return None
        m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', html)
        return m.group(1) if m else None

    def lista(self, path: str, **params) -> list[dict]:
        """Tabela HTML de `/X/Lista` ou `/X/Index` → linhas como dicts pelo cabeçalho."""
        soup = BeautifulSoup(self.get(path, params=params).text, "lxml")
        t = soup.find("table")
        if not t:
            return []
        heads = [th.get_text(" ", strip=True) for th in t.find_all("th")]
        out = []
        for tr in t.find_all("tr")[1:]:
            tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if tds:
                out.append(dict(zip(heads, tds)) if heads else {"cells": tds})
        return out

    def botoes(self, path: str) -> list[str]:
        """Textos de todos os botões/links de ação de uma tela — para o inventário 'botão a botão'."""
        soup = BeautifulSoup(self.get(path).text, "lxml")
        out = []
        for el in soup.find_all(["button", "a"]):
            t = el.get_text(" ", strip=True)
            if t and (el.name == "button" or "btn" in " ".join(el.get("class", [])) or el.get("onclick")):
                out.append(t)
        return sorted(set(out))

    # ---------- REST ----------
    def api_get(self, path: str, **params):
        r = self.s.get(BASE + path, params=params, timeout=60, headers={"Authorization": f"Bearer {self.token()}"})
        return self._j(r)

    def api_post(self, path: str, body: dict | None = None):
        r = self.s.post(BASE + path, json=body or {}, timeout=60, headers={"Authorization": f"Bearer {self.token()}"})
        return self._j(r)

    @staticmethod
    def _j(r: requests.Response):
        try:
            return {"status": r.status_code, "json": r.json()}
        except ValueError:
            return {"status": r.status_code, "text": r.text[:2000]}

    def close(self) -> None:
        try:
            self.browser.close()
            self._pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    d = DGX()
    print("login ok:", d.page.url)
    print("token:", d.token()[:30], "…")
    print("funções (combo):", str(d.api_get("/api/RH/Funcoes/combo"))[:300])
    f = d.form("/Cargos/Incluir")
    print("form Cargos/Incluir:", f["action"], list(f["fields"])[:12])
    print("botões Colaboradores/Index:", d.botoes("/Colaboradores/Index")[:15])
    d.close()
