#!/usr/bin/env python3
"""O link que mandamos para o funcionário assinar tem de CHEGAR na aba de assinar.

Origem: 17/09/2026. O Jordan: «o link de assinatura de documentos de alguns funcionários não
está abrindo, dá erro e direciona pro conecta pro versão clássica, outros chegam na área do
funcionário e não tem nada lá». Medido no nginx: 296 acessos a `/portal-funcionario/login` de
**69 IPs distintos**, e 2.884 idas para `/login?notice=portal`.

A cadeia que estava quebrada, ponta a ponta:

    aviso_assinatura_service manda    https://…/portal-funcionario/login   ← portal DESLIGADO
    a página-casca responde           location.replace('/login?notice=portal')
                                                                  └─ o destino morre aqui
    a pessoa entra com Google         /auth/callback → router.replace('/redesign')  ← fixo
    e cai no painel da empresa.

Eram três defeitos independentes na mesma linha reta, e cada um sozinho bastava para perder a
pessoa. O comentário no serviço até acertava que `/meu-espaco` dá 404 — errou o caminho: o
certo é `/modulos/meu-espaco`, e `?t=assinar` abre direto na aba.

## As regras afirmadas

1. Nada no código emite link para o portal desligado (`/portal-funcionario`).
2. `/portal-funcionario/*` responde redirect permanente para `/modulos/meu-espaco` — pelo
   servidor, não por JavaScript, que depende do chunk carregar.
3. `/modulos/meu-espaco?t=assinar` sem sessão manda para o login CARREGANDO o destino, com o
   `t=assinar` intacto. É a aba de assinar o motivo do link existir.
4. O destino pós-login é decidido num lugar só, e o callback do Google honra o destino
   guardado — foi por ele que os 69 se perderam.
5. Meu Espaço abre para QUALQUER papel. Ele não é módulo do menu, e o layout só o liberava
   para `role='funcionario'`: agente, líder, gerente, supervisor, suporte e admin viam
   «Página fora do menu». Eram 17 dos 32 recibos ainda por assinar.

Esta trava mede a SAÍDA do servidor em produção, não o código-fonte: o `docker cp` não apaga
arquivo e o build do front pode ficar para trás, então perguntar ao HTTP é o único jeito
honesto de saber o que a pessoa recebe.

    python3 backend/scripts/orq/test_link_assinatura_chega.py

Linha canônica: `TOTAL: <n> elo(s) quebrado(s) no link de assinatura`. Exit 1 quando há achado.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import urllib.parse

#: Caminho absoluto: ruff S607 recusa executável parcial, e aqui a entrada é constante.
CURL = "/usr/bin/curl"  # nosec B607
GIT = "/usr/bin/git"  # nosec B607

BASE = os.environ.get("QA_BASE", "https://erp.conectamais.pro")
RAIZ = pathlib.Path(__file__).resolve().parents[3]

#: O portal antigo. Qualquer menção a ele num link emitido é o defeito de 17/09 voltando.
PORTAL_MORTO = "/portal-funcionario"

#: Onde o funcionário tem de chegar, e a aba que o link precisa abrir.
DESTINO = "/modulos/meu-espaco"
ABA_ASSINAR = "t=assinar"


def _http(caminho: str) -> tuple[int, str]:
    """Devolve (status, Location) sem seguir o redirect. curl porque é o que mede de fora."""
    saida = subprocess.run(  # noqa: S603  # nosec B603 - argv fixo, sem shell, entrada constante
        [CURL, "-s", "-o", "/dev/null", "-w", "%{http_code} %{redirect_url}", "--max-time", "20", f"{BASE}{caminho}"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    partes = saida.split(" ", 1)
    return (int(partes[0]) if partes[0].isdigit() else 0, partes[1] if len(partes) > 1 else "")


def _emissores_do_portal_morto() -> list[str]:
    """Arquivos que ainda montam um link para o portal desligado.

    Ignora comentário e a própria trava: o que importa é string virando URL. `git grep`
    respeita o .gitignore, então não vasculha node_modules nem worktrees de agente.
    """
    try:
        bruto = subprocess.run(  # noqa: S603  # nosec B603 - argv fixo, sem shell, entrada constante
            [GIT, "grep", "-n", PORTAL_MORTO, "--", "backend/", "frontend/src/"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            check=False,
        ).stdout
    except OSError:
        return []

    achados = []
    for linha in bruto.splitlines():
        try:
            arquivo, _num, texto = linha.split(":", 2)
        except ValueError:
            continue
        if pathlib.Path(arquivo).name == pathlib.Path(__file__).name:
            continue
        nu = texto.strip()
        if nu.startswith(("#", "//", "*", "/*")):
            continue  # comentário explicando o desligamento não emite link
        # `id: 'portal-funcionario'` é chave de card do painel, não URL.
        if re.search(r"""id:\s*['"]portal-funcionario['"]""", nu) or "'portal-funcionario'," in nu:
            continue
        achados.append(f"{arquivo}: {nu[:100]}")
    return achados


sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from _fixtures import exige_host  # noqa: E402


def main() -> int:
    exige_host("lê o código-fonte do frontend e o git do repositório")
    quebras: list[str] = []

    # ── 1. Ninguém mais emite o link morto ───────────────────────────────────
    for emissor in _emissores_do_portal_morto():
        quebras.append(f"código ainda emite o portal desligado → {emissor}")

    # ── 2. O portal antigo redireciona pelo SERVIDOR para o lugar certo ──────
    for velho in (f"{PORTAL_MORTO}/login", f"{PORTAL_MORTO}/dashboard", f"{PORTAL_MORTO}/documentos"):
        status, destino = _http(velho)
        if status not in (301, 307, 308):
            quebras.append(f"{velho} respondeu {status} — devia ser redirect do servidor")
        elif DESTINO not in destino:
            quebras.append(f"{velho} → {destino or '(sem Location)'} — devia ir para {DESTINO}")

    # ── 3. O link de assinatura carrega o destino até o login ────────────────
    alvo = f"{DESTINO}?{ABA_ASSINAR}"
    status, destino = _http(alvo)
    if status in (301, 307, 308):
        if "/login" not in destino:
            quebras.append(f"{alvo} → {destino} — sem sessão devia cair no /login")
        else:
            guardado = urllib.parse.unquote(
                urllib.parse.parse_qs(urllib.parse.urlparse(destino).query).get("redirect", [""])[0]
            )
            if DESTINO not in guardado:
                quebras.append(f"{alvo}: o login não guardou o destino (redirect={guardado!r})")
            elif ABA_ASSINAR not in guardado:
                quebras.append(
                    f"{alvo}: o destino chegou ao login SEM a aba de assinar (redirect={guardado!r}) "
                    "— a pessoa loga e cai na home com as abas todas"
                )
    elif status != 200:
        quebras.append(f"{alvo} respondeu {status}")

    # ── 4. O destino pós-login vive num lugar só, e o Google o honra ─────────
    unico = RAIZ / "frontend/src/lib/destino-pos-login.ts"
    if not unico.exists():
        quebras.append("frontend/src/lib/destino-pos-login.ts sumiu — o destino voltou a ser copiado")
    callback = RAIZ / "frontend/src/app/auth/callback/page.tsx"
    if callback.exists():
        fonte = callback.read_text(encoding="utf8")
        if "resgatarDestino" not in fonte:
            quebras.append(
                "auth/callback não resgata o destino guardado — quem entra pelo Google "
                "(o caminho que o aviso manda usar) perde o link de assinatura outra vez"
            )

    # ── 5. Meu Espaço abre para QUALQUER papel, não só role='funcionario' ────
    #
    # Este elo não aparece no HTTP: a rota responde 200 e só a tela mostra «Página fora do
    # menu». Foi assim que passou despercebido — o curl dizia verde. A prova é estrutural:
    # a liberação da área pessoal tem de vir ANTES do teste `!currentModule`, e fora do
    # `if (isSelfService)`, senão quem é agente/líder/gerente bate no erro.
    layout = RAIZ / "frontend/src/app/modulos/layout.tsx"
    if layout.exists():
        fonte = layout.read_text(encoding="utf8")
        pos_libera = fonte.find("if (inSelfServiceArea) {")
        pos_self = fonte.find("if (isSelfService) {")
        pos_menu = fonte.find("if (!currentModule) {")
        if pos_libera < 0:
            quebras.append("modulos/layout.tsx não libera a área pessoal — Meu Espaço voltou a depender do menu")
        elif pos_menu >= 0 and pos_libera > pos_menu:
            quebras.append(
                "modulos/layout.tsx testa `!currentModule` ANTES de liberar a área pessoal — "
                "quem não é role='funcionario' volta a ver «Página fora do menu»"
            )
        elif 0 <= pos_self < pos_libera:
            quebras.append(
                "a liberação da área pessoal voltou para dentro de `if (isSelfService)` — "
                "agente, líder, gerente e supervisor perdem o acesso ao próprio Meu Espaço"
            )

    # ── 6. A tela de login é UMA, e veste a identidade do redesign ──────────
    #
    # 17/09/2026, o dono: «a tela de login dos funcionários que receberam o link é a antiga,
    # do clássico, não é do redesign». Existiam DUAS telas: `/login`, com Google, rosto e
    # primeiro acesso, e `/redesign/login`, bonita e mais fraca — sem nada disso e jogando
    # fora todo destino que não começasse com `/redesign`, o defeito de hoje de manhã.
    #
    # Estrutural, não HTTP, pelo mesmo motivo dos elos 4 e 5: a tela é client-side, o HTML que
    # o curl recebe vem vazio, e grep em chunk publicado MENTE — o deploy reinjeta os chunks
    # antigos de propósito (anti-ChunkLoadError), então a frase velha continua no disco do
    # container para sempre.
    login = RAIZ / "frontend/src/app/login/page.tsx"
    if not login.exists():
        quebras.append("frontend/src/app/login/page.tsx sumiu — a tela que todo link aponta")
    else:
        fonte = login.read_text(encoding="utf8")
        if "rd-root" not in fonte or "redesign.css" not in fonte:
            quebras.append("a tela /login perdeu a identidade do redesign (rd-root + redesign.css)")
        for velho in ("Bem-vindo de volta", "v2.0.0"):
            if velho in fonte:
                quebras.append(f"a tela /login voltou a mostrar o clássico: {velho!r}")
        # Nenhum recurso pode ter se perdido na troca de roupa. Cada um destes é uma porta de
        # entrada que alguém usa: o Google é o caminho que o próprio aviso manda usar, e o
        # rosto é como porteiro e ASG entram sem digitar.
        for recurso, marca in (
            ("Google", "/api/v1/auth/google"),
            ("entrar com o rosto", "ScanFace"),
            ("primeiro acesso", "/primeiro-acesso"),
            ("destino do link", "destinoPosLogin"),
            ("destino na ida ao Google", "guardarDestino"),
        ):
            if marca not in fonte:
                quebras.append(f"a tela /login perdeu «{recurso}» ({marca})")

    # A segunda tela não pode voltar a autenticar: duas telas divergem, e foi a fraca que o
    # guard do redesign mandava todo mundo usar.
    duplicata = RAIZ / "frontend/src/app/redesign/login/page.tsx"
    if duplicata.exists() and "/api/v1/auth/login" in duplicata.read_text(encoding="utf8"):
        quebras.append("/redesign/login voltou a ser uma segunda tela de login — tem de só encaminhar para /login")

    for q in quebras:
        print(f"  ✗ {q}")
    print(f"TOTAL: {len(quebras)} elo(s) quebrado(s) no link de assinatura")
    return 1 if quebras else 0


if __name__ == "__main__":
    sys.exit(main())
