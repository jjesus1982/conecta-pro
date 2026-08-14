#!/usr/bin/env python3
"""QA de responsivo/mobile do módulo Operacional (redesign), no navegador de verdade.

O que mede — cinco defeitos que só aparecem em tela pequena, cada um com número:

  1. ROLAGEM LATERAL  documentElement.scrollWidth > innerWidth. É o defeito clássico:
     a página inteira desliza para o lado e o usuário perde metade do conteúdo.
  2. VAZAMENTO SOLTO ultrapassa a borda direita SEM estar dentro de um container
     com rolagem própria. A distinção é tudo: tabela larga rolando dentro do
     próprio container é o padrão CERTO, não defeito. A primeira versão deste
     script contava os dois juntos e acusou 2.365 "vazamentos" numa tela onde
     TODOS estavam contidos e a página nem deslizava. Ia reportar 0/30 quebrado.
  3. TEXTO MIÚDO     font-size <= 11px em texto visível. Abaixo disso não se lê em
     celular sem dar zoom. O corte é 11 e não 12 porque 12px é o mínimo aceito —
     contá-lo acusava 102 elementos corretos numa tela só.
  4. ALVO DE TOQUE   botão/link com menos de 32px de altura, IGNORANDO `sr-only`
     (link de pular para o conteúdo, que é 1px por desenho e existe justamente
     para acessibilidade — acusá-lo era acusar a solução de ser problema).
  5. TELA VAZIA      a tela carregou mas não trouxe conteúdo (o "Aguardando dado"
     que já derrubou este módulo em 12/08).

Roda com o Chromium headless do container. Mata o que sobe ao terminar.

    python3 scripts/qa_responsivo_operacional.py
"""
from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

BASE = "https://erp.conectamais.pro"
# Autentica por TOKEN, não por senha. A senha de serviço do QA antigo está morta
# (login devolve 401 "Credenciais invalidas"), e com ela o teste media a TELA DE
# LOGIN 30 vezes achando que media o operacional — o front guarda o token em
# localStorage.access_token e no cookie auth_token.
#   docker exec -e PYTHONPATH=/app conecta-pro-backend python3 -c \
#     "from core.auth.jwt import create_access_token; print(create_access_token(subject='<user_id>'))"
import os  # noqa: E402

TOKEN = os.getenv("QA_TOKEN", "").strip()

# Aparelhos reais, não números redondos. O 360 é o Android mediano do time de campo;
# o 390 é o iPhone da linha atual; o 768 é o tablet da portaria.
APARELHOS = [
    ("Android 360", 360, 800, 3.0, True),
    ("iPhone 390", 390, 844, 3.0, True),
    ("Tablet 768", 768, 1024, 2.0, True),
]

# As telas que o gerente abre de fato no operacional.
TELAS = [
    ("Presença ao vivo", "presenca-hoje"),
    ("Escalas — grade", "escalas-grade"),
    ("Turnos", "turnos"),
    ("Apuração de horas", "banco-horas-apuracao"),
    ("Ausentes hoje", "ausentes-hoje"),
    ("Diárias", "diarias"),
    ("Fechamento diaristas", "diaristas-fechamento"),
    ("Medidas administrativas", "medidas-administrativas"),
    ("Rondas", "rondas"),
    ("Comunicados", "comunicados"),
]

JS_MEDIR = """
() => {
  const vw = window.innerWidth;
  const doc = document.documentElement;
  const vaza = [];
  const miudo = [];
  const alvos = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none') continue;
    // 2 · vaza pela direita (tolerância de 2px p/ arredondamento)
    if (r.right > vw + 2 && r.width > 24) {
      // contido num ancestral que rola na horizontal? entao e desenho, nao defeito
      let p = el.parentElement, contido = false;
      while (p && p !== document.body) {
        const ps = getComputedStyle(p);
        if (['auto','scroll'].includes(ps.overflowX) && p.scrollWidth > p.clientWidth + 2) { contido = true; break; }
        p = p.parentElement;
      }
      if (!contido) {
        vaza.push({tag: el.tagName.toLowerCase(), cls: (el.className||'').toString().slice(0,60),
                   right: Math.round(r.right), w: Math.round(r.width),
                   txt: (el.textContent||'').trim().slice(0,40)});
      }
    }
    // 3 · texto miúdo (só em quem tem texto próprio)
    const proprio = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (proprio) {
      const fs = parseFloat(st.fontSize);
      if (fs && fs <= 11) miudo.push({fs: fs, cls: (el.className||'').toString().slice(0,30),
                                      txt: (el.textContent||'').trim().slice(0,40)});
    }
    // 4 · alvo de toque
    const oculto = (el.className||'').toString().includes('sr-only');
    if (!oculto && ['BUTTON','A'].includes(el.tagName) && r.height > 0 && r.height < 32
        && (el.textContent||'').trim()) {
      alvos.push({h: Math.round(r.height), w: Math.round(r.width),
                  cls: (el.className||'').toString().slice(0,30),
                  txt: (el.textContent||'').trim().slice(0,32)});
    }
  }
  const corpo = (document.body.innerText || '').trim();
  return {
    vw,
    scrollW: doc.scrollWidth,
    rolagem: doc.scrollWidth > vw + 2,
    vaza: vaza.slice(0, 6),
    n_vaza: vaza.length,
    miudo: miudo.slice(0, 4),
    n_miudo: miudo.length,
    alvos: alvos.slice(0, 4),
    n_alvos: alvos.length,
    chars: corpo.length,
    aguardando: /aguardando dado|sem dados|nenhum registro/i.test(corpo),
  };
}
"""


def main() -> int:
    if not TOKEN:
        print("Defina QA_TOKEN. Sem token o teste mede a tela de LOGIN e mente.")
        return 2
    achados: list[str] = []
    linhas: list[tuple] = []

    with sync_playwright() as pw:
        nav = pw.chromium.launch(headless=True,
                                 args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            for nome_ap, w, h, dpr, mobile in APARELHOS:
                ctx = nav.new_context(ignore_https_errors=True,
                                      viewport={"width": w, "height": h},
                                      device_scale_factor=dpr, is_mobile=mobile,
                                      has_touch=mobile)
                ctx.add_cookies([{"name": "auth_token", "value": TOKEN,
                                  "domain": "erp.conectamais.pro", "path": "/"}])
                pg = ctx.new_page()
                pg.add_init_script(f"localStorage.setItem('access_token', {TOKEN!r});")
                pg.goto(f"{BASE}/redesign/operacional", wait_until="domcontentloaded", timeout=45000)
                pg.wait_for_timeout(3000)
                if "/login" in pg.url:
                    print(f"  !! {nome_ap}: token não autenticou (caiu em {pg.url})")
                    ctx.close()
                    continue

                for rotulo, slug in TELAS:
                    try:
                        pg.goto(f"{BASE}/redesign/operacional?t={slug}",
                                wait_until="domcontentloaded", timeout=45000)
                        pg.wait_for_timeout(2600)
                        m = pg.evaluate(JS_MEDIR)
                    except Exception as e:  # noqa: BLE001
                        linhas.append((nome_ap, rotulo, "ERRO", str(e)[:50]))
                        achados.append(f"{nome_ap} · {rotulo}: não carregou — {str(e)[:60]}")
                        continue

                    problemas = []
                    if m["rolagem"]:
                        problemas.append(f"rolagem lateral ({m['scrollW']}px > {m['vw']}px)")
                    if m["n_vaza"]:
                        problemas.append(f"{m['n_vaza']} vazamento(s) SOLTO(s)")
                    if m["n_miudo"]:
                        problemas.append(f"{m['n_miudo']} texto(s) <12px")
                    if m["n_alvos"]:
                        problemas.append(f"{m['n_alvos']} alvo(s) <32px")
                    if m["chars"] < 200:
                        problemas.append(f"tela quase vazia ({m['chars']} chars)")

                    linhas.append((nome_ap, rotulo, "OK" if not problemas else "PROBLEMA",
                                   "; ".join(problemas) or f"{m['chars']} chars"))
                    if problemas:
                        det = "; ".join(problemas)
                        achados.append(f"{nome_ap} · {rotulo}: {det}")
                        for v in m["vaza"][:3]:
                            achados.append(f"      vaza: <{v['tag']} class='{v['cls']}'> "
                                           f"right={v['right']}px larg={v['w']}px  \"{v['txt']}\"")
                        for t in m["miudo"][:2]:
                            achados.append(f"      miúdo: {t['fs']}px class='{t.get('cls','')}'  \"{t['txt']}\"")
                        for a in m["alvos"][:2]:
                            achados.append(f"      alvo: {a['h']}x{a.get('w','?')}px class='{a.get('cls','')}'  \"{a['txt']}\"")
                ctx.close()
        finally:
            nav.close()

    print(f"\n{'aparelho':14} {'tela':26} {'status':10} detalhe")
    print("─" * 108)
    for ap, tela, st, det in linhas:
        print(f"{ap:14} {tela[:26]:26} {st:10} {det[:52]}")

    ruins = [x for x in linhas if x[2] != "OK"]
    print(f"\n{len(linhas) - len(ruins)}/{len(linhas)} combinações tela×aparelho sem problema")
    if achados:
        print("\nACHADOS:")
        for a in achados:
            print(f"  {a}")
    return 1 if ruins else 0


if __name__ == "__main__":
    raise SystemExit(main())
