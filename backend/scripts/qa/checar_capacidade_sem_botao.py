#!/usr/bin/env python3
"""CAPACIDADE SEM BOTÃO: o sistema sabe fazer e nenhuma tela oferece — o mapa do terminal.

Origem (13/09/2026, pedido do Jordan): «percebi vários botões, funções e recursos que
deveriam ter para incluir, baixar, excluir, adicionar etc, isso em todos os módulos,
tanto que todas as vezes tive que recorrer ao terminal, quando o correto é fazer isso no
front end». O caso que abriu a conversa foi CLIENTE: dá para criar contato, proposta,
contrato, comissão, produto e condomínio — cliente, não. Lead novo nunca vira proposta.

É o INVERSO do `checar_botao_morto`. Aquele pergunta «a tela chama algo que não existe?».
Este pergunta «existe algo que a tela nunca chama?» — e é esta pergunta que manda o dono
para o `psql`.

Só conta rota que ESCREVE (POST/PUT/PATCH/DELETE): GET sem tela é dado que ninguém vê,
e isso o `checar_uso_real` já mapeia. O que dói é a AÇÃO existir sem porta.

Fora de escopo de propósito, porque acusar isso seria ruído diário:
  • auth, health, webhook, callback e retorno de gateway — não são botão de usuário;
  • rota do próprio redesign (`/redesign/action/...`) — ela É a porta;
  • rota de portal público por token (o portal tem tela própria, fora do ModuleView);
  • rota interna de agente/orquestrador (Hermes, oráculo, varredura).

    docker exec -e PYTHONPATH=/app conecta-pro-backend \
        python3 /app/scripts/qa/checar_capacidade_sem_botao.py             # resumo
    ... checar_capacidade_sem_botao.py --detalhe                           # rota a rota

Linha canônica: `TOTAL: <n> capacidade(s) sem botão`. Exit 1 quando há achado.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys

sys.path.insert(0, "/app" if os.path.isdir("/app") else os.path.join(os.path.dirname(__file__), "..", ".."))

ESCREVE = {"POST", "PUT", "PATCH", "DELETE"}

#: Famílias que não são botão de usuário. Cada uma com a razão, para ninguém alargar a
#: lista por conveniência depois.
FORA = (
    (r"/auth/|/login|/logout|/token|/refresh", "autenticação"),
    (r"/health|/ready|/metrics|/ping", "saúde do serviço"),
    (r"/webhook|/callback|/retorno|/notificacao/inter|/pix/receb", "entrada de terceiro"),
    (r"/redesign/action/", "é a própria porta do redesign"),
    (r"/portal/|/painel-ponto|/public/", "portal público com tela própria"),
    (r"/hermes|/orquestr|/agente|/oraculo|/qa/|/internal/", "rotina interna, não tela"),
    (r"/docs|/openapi|/redoc", "documentação"),
)


def _fora(caminho: str) -> str | None:
    for rx, razao in FORA:
        if re.search(rx, caminho, re.I):
            return razao
    return None


def _familia(caminho: str) -> str:
    """Primeiro segmento significativo depois de /api/v1 — agrupa o relatório."""
    partes = [p for p in caminho.split("/") if p and not p.startswith("{")]
    for i, p in enumerate(partes):
        if p not in ("api", "v1"):
            return "/".join(partes[i : i + 2]) if len(partes) > i + 1 else p
    return caminho


def _endpoints(o, acc: list[tuple[str, str]]) -> None:
    if isinstance(o, dict):
        if isinstance(o.get("endpoint"), str):
            acc.append((o["endpoint"].split("?")[0], (o.get("method") or "POST").upper()))
        for v in o.values():
            _endpoints(v, acc)
    elif isinstance(o, list):
        for v in o:
            _endpoints(v, acc)


async def main() -> int:
    detalhe = "--detalhe" in sys.argv

    import main_production  # noqa: PLC0415 — primeiro, sempre
    from core.database import async_session_factory  # noqa: PLC0415
    from modules.operacional.controllers import redesign_data_controller as RD  # noqa: PLC0415

    # 1. Tudo que o app sabe FAZER.
    rotas: list[tuple[str, str]] = []

    def walk(routes, prefix=""):
        for r in routes:
            p, ms = getattr(r, "path", None), getattr(r, "methods", None)
            if p and ms:
                for m in ms:
                    if m.upper() in ESCREVE:
                        rotas.append((prefix + p, m.upper()))
            if getattr(r, "routes", None):
                walk(r.routes, prefix + (p or ""))

    walk(main_production.app.routes)
    rotas = sorted(set(rotas))

    # 2. Tudo que ALGUMA tela chama. Compara com `{param}` normalizado: a tela monta
    #    `/contratos/abc-123` e a rota é `/contratos/{id}` — é a mesma porta.
    chamadas: set[tuple[str, str]] = set()
    async with async_session_factory() as db:
        for mod, build in sorted(RD.BUILDERS.items()):
            try:
                out = await build(db)
            except Exception as exc:  # noqa: BLE001
                print(f"   ! {mod}: não construiu ({str(exc)[:70]}) — as rotas dele contam como sem botão")
                continue
            acc: list[tuple[str, str]] = []
            _endpoints(json.loads(json.dumps(out, default=str)), acc)
            chamadas |= set(acc)

    # 2b. Endpoint que aparece só EM CONDIÇÃO (ação de linha que existe quando o status
    #     pede) some da medição do contrato renderizado: se hoje todo cliente está ativo,
    #     o botão "Ativar" não é emitido e a rota pareceria órfã. Ela não é. Por isso a
    #     leitura do CONTRATO é unida à leitura do CÓDIGO dos builders — o que o código
    #     sabe chamar conta como coberto, mesmo que hoje nenhuma linha o exiba.
    import pathlib as _pl  # noqa: PLC0415

    _dir = _pl.Path(RD.__file__).parent / "redesign_builders"
    _lit = re.compile(r"""["'](/api/v1/[^"'\s{}]*(?:\{[a-z_]+\}[^"'\s{}]*)*)["']""")
    literais: set[str] = set()
    for _f in list(_dir.rglob("*.py")) + [_pl.Path(RD.__file__)]:
        try:
            literais |= set(_lit.findall(_f.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            pass
    # f-string com interpolação vira prefixo: /api/v1/clients/{cid}/activate -> guarda o
    # texto antes e depois do buraco, e a comparação abaixo casa por prefixo+sufixo.
    literais |= {re.sub(r"\{[^}]*\}", "{}", x) for x in literais}

    def _no_codigo(caminho: str) -> bool:
        alvo = re.sub(r"\{[^}]*\}", "{}", caminho)
        if alvo in literais:
            return True
        # `f"/api/v1/clients/{cid}/activate"` chega como `/api/v1/clients/` + `/activate`
        cauda = alvo.rstrip("/").rsplit("{}", 1)[-1]
        cabeca = alvo.split("{}", 1)[0]
        return bool(cauda) and any(
            x.startswith(cabeca) and x.endswith(cauda) for x in literais
        )

    # 2c. O redesign tem porta PRÓPRIA para várias ações: a tela chama
    #     `/redesign/action/contract-activate`, que por dentro faz o mesmo que
    #     `/crm/contracts/{id}/activate`. A rota crua parece órfã e não está: o botão
    #     existe, só entra por outra porta. Casa pelo NOME — os dois últimos segmentos
    #     significativos da rota contra o nome da ação.
    acoes_redesign = {
        ep.rsplit("/", 1)[-1].split("?")[0].lower()
        for ep, _ in chamadas
        if "/redesign/action/" in ep
    }
    acoes_redesign |= {a.replace("_", "-") for a in acoes_redesign}

    def _tem_acao_equivalente(caminho: str) -> bool:
        segs = [x for x in caminho.split("/") if x and not x.startswith("{") and x not in ("api", "v1")]
        if not segs:
            return False
        cauda = segs[-1].lower()
        if cauda in acoes_redesign:
            return True
        # `contracts` + `activate` -> `contract-activate` / `contrato-activate`
        if len(segs) >= 2:
            base = segs[-2].lower().rstrip("s")
            for sep in ("-", "_"):
                if f"{base}{sep}{cauda}" in acoes_redesign:
                    return True
        return False

    def coberta(caminho: str, metodo: str) -> bool:
        rx = re.compile("^" + re.sub(r"\\\{[^}]+\\\}", r"[^/]+", re.escape(caminho)) + "$")
        if any(m == metodo and rx.match(ep) for ep, m in chamadas):
            return True
        return _no_codigo(caminho) or _tem_acao_equivalente(caminho)

    # 3. O que sobra.
    achados: list[tuple[str, str, str]] = []
    ignoradas = 0
    for caminho, metodo in rotas:
        if _fora(caminho):
            ignoradas += 1
            continue
        if not coberta(caminho, metodo):
            achados.append((_familia(caminho), metodo, caminho))

    por_familia: dict[str, list[tuple[str, str]]] = {}
    for fam, metodo, caminho in achados:
        por_familia.setdefault(fam, []).append((metodo, caminho))

    for fam, itens in sorted(por_familia.items(), key=lambda x: -len(x[1])):
        print(f"   {len(itens):3}  {fam}")
        if detalhe:
            for metodo, caminho in sorted(itens):
                print(f"          {metodo:<7} {caminho}")

    print(
        f"\n   {len(rotas)} rota(s) que escrevem · {ignoradas} fora de escopo · "
        f"{len(chamadas)} chamada(s) de tela em {len(RD.BUILDERS)} módulo(s)"
    )
    print(f"\nTOTAL: {len(achados)} capacidade(s) sem botão")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
