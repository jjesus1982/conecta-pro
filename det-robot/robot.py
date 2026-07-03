"""Robô DET — login gov.br com captcha AUTOMÁTICO (2Captcha) + perfil persistente.

Estratégia (near-100% automático):
- O robô resolve o hCaptcha do gov.br sozinho (2Captcha).
- No 1º login (supervisionado via noVNC), Jordan só digita o código 2FA do app gov.br
  e marca "não solicitar novamente neste navegador".
- O PERFIL do navegador é persistente (/state/profile) → depois disso o robô loga
  100% automático (captcha resolvido + navegador confiável, sem 2FA), reusando a sessão.

Endpoints:
  POST /login/iniciar  → login supervisionado (noVNC) — captcha auto, Jordan faz só o 2FA
  GET  /login/status
  POST /coletar        → login/coleta 100% automático (headless), lê o DET
"""
import os, time, threading, queue
from urllib.parse import urlencode

import httpx
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, pkcs12
from fastapi import FastAPI
from playwright.sync_api import sync_playwright

PFX_PATH = os.environ.get("DET_PFX_PATH", "/cert/certificado.pfx")
PFX_PASS = os.environ.get("CERTIFICATE_PASSWORD", "Conecta123")
TWO = os.environ.get("TWOCAPTCHA_API_KEY", "").strip()
PROFILE = "/state/profile"          # perfil persistente (cookies + confiança do navegador)
PEM_DIR = "/dev/shm/detcert"
DISPLAY = ":99"
DET_HOME = "https://det.sit.trabalho.gov.br/"
AUTH = "https://sso.acesso.gov.br/authorize?" + urlencode({
    "response_type": "code", "client_id": "det.sit.trabalho.gov.br",
    "scope": "openid email profile govbr_confiabilidades govbr_empresa",
    "redirect_uri": "https://det.sit.trabalho.gov.br/acessogov", "nonce": "n", "state": "s"})

_STEALTH_JS = """
  Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
  Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR','pt','en']});
  Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
  window.chrome = window.chrome || { runtime: {} };
"""

app = FastAPI(title="Robô DET")
_estado = {"login_em_andamento": False, "logado": False, "ultima_msg": "ocioso"}
_LIVE = {"pw": None, "ctx": None, "page": None}
_CMD = queue.Queue()
_RES = {}
_RES_EVT = threading.Event()


def _ler_caixa(page):
    caps = []
    page.on("response", lambda r: ("det-backend" in r.url or "/rest/" in r.url) and caps.append(f"{r.request.method} {r.url}"))
    for r in ["https://det.sit.trabalho.gov.br/detweb/caixaPostal","https://det.sit.trabalho.gov.br/detweb/comunicados","https://det.sit.trabalho.gov.br/servicos"]:
        try: page.goto(r, wait_until="networkidle", timeout=40000); page.wait_for_timeout(3000)
        except Exception: pass
    for t in ["Caixa Postal","Caixa de Entrada","Comunicados","Mensagens","Caixa"]:
        try:
            el = page.get_by_text(t, exact=False)
            if el.count() > 0: el.first.click(timeout=5000); page.wait_for_timeout(3500); break
        except Exception: pass
    try: conteudo = page.locator("body").inner_text()[:4000]
    except Exception: conteudo = ""
    expirou = "/login" in page.url or "sso.acesso" in page.url
    # extrai as mensagens estruturadas (tipo, orgao, data, assunto)
    mensagens = []
    try:
        import re as _re
        linhas = [l.strip() for l in conteudo.split("\n") if l.strip()]
        i = 0
        tipos = ("Notificação", "Notificacao", "Aviso", "Intimação", "Intimacao", "Comunicado", "Edital")
        meses = "jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez"
        while i < len(linhas):
            if linhas[i] in tipos and i + 3 < len(linhas):
                orgao = linhas[i+1]
                data = linhas[i+2] if _re.search(rf"\d+\s+({meses})", linhas[i+2], _re.I) else None
                assunto = linhas[i+3] if data else linhas[i+2]
                mensagens.append({"tipo": linhas[i], "orgao": orgao, "data": data, "assunto": assunto})
                i += 4 if data else 3
            else:
                i += 1
    except Exception:
        pass
    return {"ok": not expirou, "url": page.url, "expirou": expirou, "total": len(mensagens),
            "mensagens": mensagens, "conteudo_caixa": conteudo,
            "msg": ("Sessao expirada" if expirou else f"Caixa lida: {len(mensagens)} mensagens")}

_INIT_JS = """
  window.__hcap = { cbs: [], injected: null, opts: {} };
  let _hc;
  Object.defineProperty(window, 'hcaptcha', {
    configurable: true, get(){ return _hc; },
    set(v){ _hc = v; try {
      const oR=v.render; v.render=function(c,o){ window.__hcap.opts=o||{}; if(o&&typeof o.callback==='function')window.__hcap.cbs.push(o.callback); return oR.apply(this,arguments); };
      v.execute=function(id,o){ const a=o&&o.async; const w=new Promise(r=>{const t=setInterval(()=>{if(window.__hcap.injected){clearInterval(t);r({response:window.__hcap.injected,key:window.__hcap.injected});}},400);}); return a?w:undefined; };
      v.getResponse=function(){ return window.__hcap.injected||''; };
    } catch(e){} }
  });
"""


def _pem():
    os.makedirs(PEM_DIR, exist_ok=True)
    cp, kp = f"{PEM_DIR}/c.pem", f"{PEM_DIR}/k.pem"
    if os.path.exists(cp) and os.path.exists(kp):
        return cp, kp
    key, cert, extra = pkcs12.load_key_and_certificates(open(PFX_PATH, "rb").read(), PFX_PASS.encode())
    pem = cert.public_bytes(Encoding.PEM)
    for c in (extra or []):
        pem += c.public_bytes(Encoding.PEM)
    open(cp, "wb").write(pem)
    open(kp, "wb").write(key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()))
    return cp, kp


def _solve_hcaptcha(sitekey, pageurl, rqdata=None, timeout=220):
    payload = {"key": TWO, "method": "hcaptcha", "sitekey": sitekey, "pageurl": pageurl, "invisible": 1, "json": 1, "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
    if rqdata:
        payload["data"] = rqdata
    with httpx.Client(timeout=30) as cli:
        d = cli.post("https://2captcha.com/in.php", data=payload).json()
        if d.get("status") != 1:
            raise RuntimeError(f"2captcha in.php: {d.get('request')}")
        cid = d["request"]
        dl = time.time() + timeout
        time.sleep(12)
        while time.time() < dl:
            dd = cli.get("https://2captcha.com/res.php", params={"key": TWO, "action": "get", "id": cid, "json": 1}).json()
            if dd.get("status") == 1:
                return dd["request"]
            if dd.get("request") != "CAPCHA_NOT_READY":
                raise RuntimeError(f"2captcha: {dd.get('request')}")
            time.sleep(5)
    raise RuntimeError("2captcha timeout")


def _persistent_ctx(pw, headless: bool):
    cert, key = _pem()
    os.makedirs(PROFILE, exist_ok=True)
    os.system("pkill -9 -f chrome-linux/chrome 2>/dev/null; pkill -9 -f chrome_crashpad 2>/dev/null; sleep 1; rm -f %s/Singleton* 2>/dev/null" % PROFILE)
    return pw.chromium.launch_persistent_context(
        PROFILE, headless=headless,
        ignore_default_args=["--enable-automation"],
        args=["--no-sandbox","--disable-dev-shm-usage","--disable-blink-features=AutomationControlled","--start-maximized","--window-position=0,0","--window-size=1440,860","--kiosk"],
        client_certificates=[
            {"origin": "https://certificado.sso.acesso.gov.br", "certPath": cert, "keyPath": key},
            {"origin": "https://sso.acesso.gov.br", "certPath": cert, "keyPath": key}],
        ignore_https_errors=True,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        viewport={"width": 1440, "height": 900})


def _passo_captcha(page):
    """Clica no certificado e resolve o hCaptcha (2Captcha), com retry se 'Captcha inválido'."""
    for tent in range(6):
        try:
            page.click("#login-certificate", timeout=8000, force=True)
        except Exception:
            page.evaluate("document.getElementById('login-certificate')?.click()")
        page.wait_for_timeout(3500)
        info = page.evaluate("""()=>{const o=(window.__hcap&&window.__hcap.opts)||{}; let s=o.sitekey;
          if(!s){let e=document.querySelector('[data-sitekey]'); if(e)s=e.getAttribute('data-sitekey');}
          return {sitekey:s||'93b08d40-d46c-400a-ba07-6f91cda815b9', rqdata:o.rqdata||null};}""")
        token = _solve_hcaptcha(info["sitekey"], page.url, info.get("rqdata"))
        page.evaluate("""(tok)=>{ window.__hcap.injected=tok;
          document.querySelectorAll('textarea[name=\"h-captcha-response\"],textarea[name=\"g-recaptcha-response\"]').forEach(e=>{e.value=tok;});
          (window.__hcap.cbs||[]).forEach(cb=>{try{cb(tok);}catch(e){}}); }""", token)
        page.wait_for_timeout(7000)
        try:
            body = page.locator("body").inner_text().lower()
        except Exception:
            body = ""
        u = page.url
        if ("duas etapas" in body) or ("codigo de acesso" in body) or ("cdigo de acesso" in body) or ("certificado.sso" in u) or ("det.sit.trabalho.gov.br" in u and "sso.acesso" not in u):
            return True  # avançou (2FA ou DET)
        # captcha rejeitado → recarrega e tenta de novo
        try:
            page.goto(AUTH, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2500)
        except Exception:
            pass
    return False



# ── login supervisionado (noVNC): captcha auto, humano só faz o 2FA ──────────
def _sh(cmd):
    import subprocess
    return subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _subir_vnc():
    os.environ["DISPLAY"] = DISPLAY  # stack (Xvfb/x11vnc/websockify) já sobe no entrypoint do container




def _fluxo_login():
    _estado.update(login_em_andamento=True, logado=False, ultima_msg="subindo navegador…")
    try:
        _subir_vnc()
        with sync_playwright() as pw:
            os.environ["DISPLAY"] = DISPLAY
            ctx = _persistent_ctx(pw, headless=False)
            ctx.add_init_script(_STEALTH_JS)
            ctx.add_init_script(_INIT_JS)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(AUTH, wait_until="networkidle", timeout=60000)
            if "det.sit.trabalho.gov.br" in page.url and "sso" not in page.url and "/login" not in page.url:
                _estado.update(logado=True, ultima_msg="já estava logado (sessão válida) — mantendo viva")
                try: page.goto("https://det.sit.trabalho.gov.br/servicos", wait_until="networkidle", timeout=40000)
                except Exception: pass
                _LIVE.update(ctx=ctx, page=page)
                _loop_comandos(ctx, page); return
            _estado["ultima_msg"] = "robô insistindo no captcha (2Captcha)…"
            got = False
            try:
                got = _passo_captcha(page)
            except Exception as e:
                _estado["ultima_msg"] = f"captcha: {e}"
            if got:
                _estado["ultima_msg"] = "✅ CAPTCHA PASSOU! AGORA VOCÊ: digite o código 2FA no noVNC e marque 'não pedir novamente'."
            else:
                _estado["ultima_msg"] = "captcha não passou após 6 tentativas — pode tentar você mesmo no noVNC ou reiniciar."
            # aguarda até 12 min o humano concluir o 2FA
            dl = time.time() + 900
            dentro = False
            _clicou_entrar = False
            while time.time() < dl:
                time.sleep(3)
                u = page.url
                if ("det.sit.trabalho.gov.br" in u and "sso.acesso" not in u and "certificado.sso" not in u
                        and "/login" not in u):
                    dentro = True; break
                # se caiu no /login do DET (gov.br ja autenticado), clica Entrar pra completar
                if "det.sit.trabalho.gov.br/login" in u and not _clicou_entrar:
                    try:
                        el = page.get_by_text("Entrar com gov.br", exact=False)
                        if el.count() > 0:
                            el.first.click(timeout=6000); _clicou_entrar = True; time.sleep(6)
                    except Exception:
                        pass
            if dentro:
                try: page.goto("https://det.sit.trabalho.gov.br/servicos", wait_until="networkidle", timeout=40000)
                except Exception: pass
                _estado.update(logado=True, ultima_msg="✅ login concluído — sessão VIVA (pronto p/ ler a caixa)")
                _LIVE.update(ctx=ctx, page=page)
                _loop_comandos(ctx, page); return
            else:
                _estado["ultima_msg"] = "tempo esgotado — reinicie o login"
                ctx.close()
    except Exception as e:
        _estado["ultima_msg"] = f"erro: {e}"
    finally:
        _estado["login_em_andamento"] = False


def _push_backend(res):
    """Empurra as mensagens lidas pro ERP (auto-coleta periódica)."""
    try:
        msgs = res.get("mensagens") if isinstance(res, dict) else None
        if not msgs:
            return
        httpx.post(f"{BACKEND}/api/v1/juridico/det/ingest-robo",
                   headers={"x-robo-token": os.environ.get("DET_ROBO_TOKEN", "conecta-det-robo-2026")},
                   json={"mensagens": msgs}, timeout=30)
    except Exception:
        pass


def _debug_detalhe(page):
    """Descobre como abrir uma mensagem: dumpa os elementos clicáveis + tenta clicar a 1ª."""
    try:
        page.goto("https://det.sit.trabalho.gov.br/caixapostal", wait_until="networkidle", timeout=40000)
        page.wait_for_timeout(3000)
    except Exception:
        pass
    # dump de elementos das linhas de mensagem
    info = page.evaluate("""()=>{
      const out={rows:[], links:[], botoes:[]};
      document.querySelectorAll('tr, .lista-mensagem, [class*=mensagem], [class*=item]').forEach((el,i)=>{
        if(i<8){ const t=(el.innerText||'').trim().slice(0,60); if(t) out.rows.push({tag:el.tagName, cls:el.className.slice(0,40), txt:t}); }
      });
      document.querySelectorAll('a[href],button').forEach((el,i)=>{ if(i<20){ const t=(el.innerText||'').trim().slice(0,30); const h=el.getAttribute('href')||''; if(t||h.includes('mensag')||h.includes('comunic')) out.links.push({txt:t, href:h.slice(0,60), id:el.id}); }});
      return out;
    }""")
    # tenta clicar na 1ª mensagem (assunto)
    detalhe = ""
    novas_paginas = []
    page.context.on("page", lambda p: novas_paginas.append(p.url))
    for sel in ["a:has-text('FGTS')", "a:has-text('Notificação')", "tr:has-text('FGTS')", "[class*=assunto]"]:
        try:
            el = page.locator(sel).first
            if el.count() > 0:
                el.click(timeout=6000); page.wait_for_timeout(4000)
                detalhe = page.locator("body").inner_text()[:1200]
                break
        except Exception:
            continue
    return {"ok": True, "url": page.url, "dom": info, "detalhe": detalhe,
            "novas_paginas": novas_paginas, "downloads_hint": "ver se abriu PDF/nova aba"}


def _loop_comandos(ctx, page):
    """Mantém a sessão VIVA e processa comandos NA MESMA THREAD (Playwright é thread-affine).
    Keep-alive: ping a cada 5 min; auto-coleta+push ao ERP a cada 30 min."""
    prox_ping = time.time() + 300
    prox_coleta = time.time() + 60   # 1ª coleta automática 1 min após o login
    while True:
        try:
            cmd = _CMD.get(timeout=30)
        except Exception:
            cmd = None
        if cmd == "coletar":
            try: _RES["coletar"] = _ler_caixa(page)
            except Exception as e: _RES["coletar"] = {"ok": False, "msg": f"erro: {e}"}
            _RES_EVT.set()
        elif cmd == "debug_detalhe":
            try: _RES["debug"] = _debug_detalhe(page)
            except Exception as e: _RES["debug"] = {"ok": False, "msg": f"erro: {e}"}
            _RES_EVT.set()
        elif cmd == "parar":
            break
        # AUTO-COLETA periódica: lê a caixa e empurra ao ERP a cada 30 min
        if time.time() >= prox_coleta:
            prox_coleta = time.time() + 1800
            try:
                res = _ler_caixa(page)
                _push_backend(res)
                _estado["ultima_msg"] = f"auto-coleta: {res.get('total', 0)} mensagens enviadas ao ERP"
            except Exception:
                pass
        # keep-alive periódico
        if time.time() >= prox_ping:
            prox_ping = time.time() + 300
            try:
                page.goto("https://det.sit.trabalho.gov.br/servicos", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(1500)
                if "/login" in page.url or "sso.acesso" in page.url:
                    _estado.update(logado=False, ultima_msg="sessão expirou — re-logando…")
                    # tenta re-login automático (sessão gov.br costuma reaproveitar → sem captcha)
                    page.goto(AUTH, wait_until="networkidle", timeout=60000)
                    if not ("det.sit.trabalho.gov.br" in page.url and "sso" not in page.url and "/login" not in page.url):
                        try: _passo_captcha(page)
                        except Exception: pass
                        t = time.time() + 120
                        while time.time() < t:
                            if "det.sit.trabalho.gov.br/login" in page.url:
                                try: page.get_by_text("Entrar com gov.br", exact=False).first.click(timeout=6000); time.sleep(6)
                                except Exception: pass
                            if "det.sit.trabalho.gov.br" in page.url and "sso" not in page.url and "/login" not in page.url:
                                break
                            time.sleep(3)
                    if "det.sit.trabalho.gov.br" in page.url and "/login" not in page.url and "sso" not in page.url:
                        _estado.update(logado=True, ultima_msg="✅ sessão renovada automaticamente")
            except Exception:
                pass
    ctx.close()


@app.post("/login/iniciar")
def login_iniciar():
    if _estado["login_em_andamento"]:
        return {"ok": True, "msg": "login já em andamento", "novnc_url": "/det-vnc/vnc.html?autoconnect=1&resize=scale&path=det-vnc/websockify"}
    threading.Thread(target=_fluxo_login, daemon=True).start()
    return {"ok": True, "msg": "Abra o noVNC. O captcha é resolvido sozinho; digite só o código 2FA do app gov.br e marque 'não pedir novamente'.",
            "novnc_url": "/det-vnc/vnc.html?autoconnect=1&resize=scale&path=det-vnc/websockify"}


@app.get("/login/status")
def login_status():
    return {**_estado, "sessao_salva": os.path.isdir(PROFILE) and bool(os.listdir(PROFILE))}


# ── coleta 100% automática (headless, reusa o perfil confiável) ──────────────
@app.post("/coletar")
def coletar():
    if _LIVE.get("page") is None or not _estado.get("logado"):
        return {"ok": False, "msg": "sem sessao viva - faca o login (/login/iniciar)"}
    _RES_EVT.clear(); _RES.pop("coletar", None)
    _CMD.put("coletar")
    if _RES_EVT.wait(timeout=120):
        return _RES.get("coletar", {"ok": False, "msg": "sem resultado"})
    return {"ok": False, "msg": "timeout na leitura"}


@app.post("/debug/detalhe")
def debug_detalhe():
    if _LIVE.get("page") is None or not _estado.get("logado"):
        return {"ok": False, "msg": "sem sessao viva"}
    _RES_EVT.clear(); _RES.pop("debug", None)
    _CMD.put("debug_detalhe")
    if _RES_EVT.wait(timeout=90):
        return _RES.get("debug", {"ok": False})
    return {"ok": False, "msg": "timeout"}


@app.get("/health")
def health():
    return {"ok": True, "perfil": os.path.isdir(PROFILE) and bool(os.listdir(PROFILE))}


def _auto_login_boot():
    """Watchdog: mantém o DET SEMPRE logado. Re-tenta o login até passar (captcha é inconsistente)."""
    time.sleep(5)
    while True:
        if not _estado.get("logado") and not _estado.get("login_em_andamento"):
            if os.path.isdir(PROFILE) and os.listdir(PROFILE):
                _estado["ultima_msg"] = "watchdog: tentando login…"
                try:
                    _fluxo_login()   # bloqueia enquanto logado (loop de comandos); volta se cair
                except Exception:
                    pass
        time.sleep(60)   # se caiu/falhou, tenta de novo em 1 min


if __name__ == "__main__":
    import uvicorn
    threading.Thread(target=_auto_login_boot, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8099)
