#!/usr/bin/env python3
"""Critério de aceite EXECUTÁVEL do módulo Operacional (ordem de fechamento T4).

Sai 0 só quando as 7 condições passam. Enquanto sair vermelho, o módulo não fechou.

Por que existe: "fechado" vinha sendo afirmado em prosa. Aqui é comando — cada condição
imprime ✅/❌ com o número que a sustenta, e o exit code decide. Condições 5, 6 e 7 nascem
nesta ordem (não existiam em trava nenhuma).

Uso:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/fechado_operacional.py
    (as condições 1-3 chamam as travas no host; rode do host para tê-las completas)
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys

RAIZ = "/opt/conecta-pro"
NO_CONTAINER = os.path.isdir("/app/modules") and not os.path.isdir(os.path.join(RAIZ, "backend/scripts/qa"))

# Vocabulário REAL de gp_clock_punches.status, medido em 13/08/2026:
#   approved 6458 · pending 1275 · fora_local 103 · normal 5 · regular 2
# 'cancelado' e 'rejected' (usados em 10 filtros) NÃO existem na coluna → filtro inerte.
STATUS_REAIS = {"approved", "pending", "fora_local", "normal", "regular"}
LITERAIS_FANTASMA = ("cancelado", "rejected", "canceled", "cancelada")


def _ok(cond: bool, titulo: str, detalhe: str = "") -> bool:
    print(f"  {'✅' if cond else '❌'} {titulo}" + (f" — {detalhe}" if detalhe else ""))
    return cond


MEU = ("modules/operacional", "modules/campo", "/operacional", "/campo")


def _rodar(script: str, no_container: bool) -> str:
    """Roda uma trava e devolve stdout+stderr. checar_vocabulario precisa do banco → container."""
    if no_container:
        cmd = ["docker", "exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend",
               "python3", f"/app/scripts/qa/{script}"]
        cwd = None
    else:
        caminho = os.path.join(RAIZ, "backend/scripts/qa", script)
        if not os.path.exists(caminho):
            raise FileNotFoundError(script)
        cmd, cwd = [sys.executable, caminho], RAIZ
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900, cwd=cwd)
    return r.stdout + r.stderr


def _t1_repositorio() -> tuple[bool, str]:
    """1 · chamadas a método que o repositório não tem, no bloco '── operacional:'."""
    try:
        saida = _rodar("checar_repositorio.py", no_container=False)
    except Exception as e:  # noqa: BLE001
        return False, f"não rodou: {e}"
    m = re.search(r"──\s*operacional:\s*(\d+)\s*chamada", saida)
    n = int(m.group(1)) if m else 0
    return n == 0, f"{n} chamada(s) a método inexistente"


def _t2_vocabulario() -> tuple[bool, str]:
    """2 · literal de status que a coluna não tem. Só CRITICO conta (ATENCAO = ruído conhecido).

    Roda no container: a trava confronta a coluna no banco, e o host não alcança o Postgres.
    """
    try:
        saida = _rodar("checar_vocabulario.py", no_container=True)
    except Exception as e:  # noqa: BLE001
        return False, f"não rodou: {e}"
    if "[CRITICO]" not in saida and "TOTAL" not in saida:
        return False, "saída não reconhecida (trava mudou de formato?)"
    linhas, reais, legitimos = saida.splitlines(), 0, 0
    for i, ln in enumerate(linhas):
        if "[CRITICO]" not in ln or not any(p in ln for p in MEU):
            continue
        alvo = re.search(r"(\w+)\.(\w+)\s", linhas[i + 1] if i + 1 < len(linhas) else "")
        falta = re.findall(r"'([^']+)'", linhas[i + 2] if i + 2 < len(linhas) else "")
        if alvo and falta and set(falta) <= _dominio_do_modelo(alvo.group(1), alvo.group(2)):
            legitimos += 1  # o literal É do domínio declarado; a coluna só não tem linha assim ainda
        else:
            reais += 1
    det = f"{reais} literal(is) fora do vocabulário da coluna"
    if legitimos:
        det += f" (+{legitimos} do domínio declarado, não contam)"
    return reais == 0, det


def _dominio_do_modelo(tabela: str, coluna: str) -> set[str]:
    """Valores que o MODELO daquela tabela declara para aquela coluna.

    A trava compara o literal com os valores OBSERVADOS. Numa tabela quase vazia isso
    acusa código correto: occurrences tem 4 linhas, todas 'cancelada', então filtrar
    por 'aberta' vira CRITICO — sendo 'aberta' o default do próprio modelo.
    Ancorar no modelo DA TABELA (e não em qualquer enum do repo) é o que separa esse
    falso-positivo do caso real: 'cancelado'/'rejected' existem como enum em time_bank
    e substitution, mas nenhum governa gp_clock_punches — lá o filtro é inerte mesmo,
    em 7843 linhas.
    """
    base = (RAIZ + "/backend" if os.path.isdir(RAIZ + "/backend") else "/app") + "/modules"
    for raiz, _d, arqs in os.walk(base):
        if "_quarentena" in raiz:
            continue
        for a in arqs:
            if not a.endswith(".py"):
                continue
            try:
                with open(os.path.join(raiz, a), encoding="utf-8") as f:
                    src = f.read()
            except OSError:
                continue
            if f'__tablename__ = "{tabela}"' not in src:
                continue
            # aceita as DUAS formas do repo: `col: Mapped[...] = mapped_column(...)`
            # e o estilo antigo `col = Column(...)`. O leitor só sabia a primeira e
            # devolvia domínio vazio para gp_clock_punches, que usa a segunda.
            m = re.search(rf"^\s+{coluna}\s*(?::[^=\n]*)?=\s*(?:mapped_column|Column)\("
                          rf"[^\n]*?default=(\w+)\.", src, re.M)
            if not m:
                continue
            # aceita `class X(StrEnum)` e `class X(enum.StrEnum)` — o modelo do ponto
            # usa a segunda forma e o leitor devolvia domínio vazio por causa disso.
            enum = re.search(rf"class {m.group(1)}\((?:enum\.)?StrEnum\):(.*?)(?=^class |\Z)",
                             src, re.M | re.S)
            if enum:
                return set(re.findall(r'=\s*"([^"]+)"', enum.group(1)))
    return set()


def _t3_rotas_frontend() -> tuple[bool, str]:
    """3 · chamada do front a rota que o backend não tem, ALCANÇÁVEL por tela."""
    try:
        saida = _rodar("checar_rotas_frontend.py", no_container=False)
    except Exception as e:  # noqa: BLE001
        return False, f"não rodou: {e}"
    if "alcançáveis" not in saida:
        return False, "saída não reconhecida (trava mudou de formato?)"
    # bloco por arquivo: "    N  caminho/arquivo.ts" seguido de linhas "        x /api/v1/..."
    linhas = saida.splitlines()[saida.splitlines().index(
        next(ln for ln in saida.splitlines() if "alcançáveis" in ln)):]
    total, quant, minhas = 0, 0, False
    for ln in linhas:
        m = re.match(r"\s+(\d+)\s+\S+$", ln)
        if m:
            if minhas:
                total += quant
            quant, minhas = int(m.group(1)), False
        elif "x /api/v1/" in ln and any(p in ln for p in MEU):
            minhas = True
    if minhas:
        total += quant
    return total == 0, f"{total} chamada(s) alcançável(is) para rota inexistente"


async def _condicoes_de_banco() -> list[tuple[bool, str, str]]:
    """5, 6 e 7 — as que nascem nesta ordem. Todas contra o banco, não contra código."""
    sys.path.insert(0, "/app" if NO_CONTAINER else os.path.join(RAIZ, "backend"))
    from sqlalchemy import text  # noqa: PLC0415

    from core.database import async_session_factory  # noqa: PLC0415

    out: list[tuple[bool, str, str]] = []
    async with async_session_factory() as db:
        # PISO declarado pelo Jordan (operacional_apuracao_regra.piso_dado_valido):
        # tudo anterior a 01/08/2026 serviu para VALIDAR o sistema, não é operação.
        # O critério lê a regra do banco em vez de carregar a data no código — se o
        # piso mudar, o aceite acompanha sem precisar de deploy.
        try:
            piso = (await db.execute(text(
                "SELECT valor FROM operacional_apuracao_regra "
                "WHERE chave='piso_dado_valido' AND ativo LIMIT 1"))).scalar()
        except Exception:  # noqa: BLE001 — tabela ainda não existe neste ambiente
            await db.rollback()
            piso = None
        # asyncpg exige objeto date no parâmetro tipado — string crua estoura
        # com "'str' object has no attribute 'toordinal'".
        from datetime import date as _d  # noqa: PLC0415
        piso = _d.fromisoformat(piso) if piso else _d(1900, 1, 1)
        # 5 · DISCIPLINAR — medida aplicada há >7 dias sem ciência nem recusa formalizada.
        # O silêncio é o defeito: sanção que a empresa não prova ter comunicado.
        n = (await db.execute(text("""
            SELECT count(*) FROM disciplinary_actions
            WHERE status::text = 'aplicada'
              AND employee_signed_at IS NULL
              AND coalesce(employee_refused_sign, false) = false
              AND created_at < now() - interval '7 days'
              AND created_at >= :piso
        """), {"piso": piso})).scalar() or 0
        # Nem toda pendente é sanção não comunicada: as 5 de hoje são carga histórica
        # (todas criadas em 02/07/2026, approved_at NULL, códigos de 2025-07 a 2026-05).
        # O papel assinado provavelmente existe — o que falta é o registro dele aqui.
        # A lacuna é real de qualquer forma: sem registro, a empresa não prova.
        antes_piso = (await db.execute(text("""
            SELECT count(*) FROM disciplinary_actions
            WHERE status::text = 'aplicada' AND employee_signed_at IS NULL
              AND coalesce(employee_refused_sign, false) = false
              AND created_at < :piso
        """), {"piso": piso})).scalar() or 0
        out.append((n == 0, f"disciplinar: 0 medida aplicada >7d sem registro de ciência (desde {piso})",
                    f"{n} sem registro"
                    + (f" · {antes_piso} anterior(es) ao piso não contam (validação do sistema)"
                       if antes_piso else "")))

        # 6 · APURAÇÃO — batida não-aprovada entrando no cálculo SEM marcação.
        # Não julga se pending deve contar (é regra de negócio do Jordan): julga se entra
        # em silêncio. A marcação vive em operacional_apuracao_regra.
        try:
            regra = (await db.execute(text(
                "SELECT count(*) FROM operacional_apuracao_regra WHERE ativo"))).scalar() or 0
        except Exception:  # noqa: BLE001 — tabela ainda não existe
            await db.rollback()
            regra = 0
        nao_aprov = (await db.execute(text("""
            SELECT count(*) FROM gp_clock_punches
            WHERE punch_timestamp > greatest(now() - interval '30 days', CAST(:piso AS timestamp))
              AND coalesce(status,'') <> 'approved'
        """), {"piso": piso})).scalar() or 0
        out.append((regra > 0 or nao_aprov == 0,
                    "apuração: nenhuma batida não-aprovada entra sem regra declarada",
                    f"{nao_aprov} não-aprovadas em 30d, regra declarada: {'sim' if regra else 'NÃO'}"))

        # 7 · TABELA MORTA — aba lendo tabela com 0 linhas havendo equivalente viva.
        # Vazio "honesto" que na verdade é a tabela errada mente pior que erro.
        pares = [("diarist_schedules", "diaria_diaristas"),
                 ("diarist_assignments", "diaria_diaristas"),
                 ("diarist_payments", "financial_pagamentos_diaristas")]
        mortas_com_viva = []
        for morta, viva in pares:
            try:
                m = (await db.execute(text(f"SELECT count(*) FROM {morta}"))).scalar() or 0  # noqa: S608
                v = (await db.execute(text(f"SELECT count(*) FROM {viva}"))).scalar() or 0  # noqa: S608
            except Exception:  # noqa: BLE001
                await db.rollback()
                continue
            if m == 0 and v > 0 and _builder_le(morta):
                mortas_com_viva.append(f"{morta}(0) vs {viva}({v})")
        out.append((not mortas_com_viva, "tabela morta: nenhuma aba na fonte morta havendo viva",
                    "; ".join(mortas_com_viva) or "nenhuma"))
    return out


def _fonte(nome: str) -> str:
    base = (RAIZ + "/backend" if os.path.isdir(RAIZ + "/backend") else "/app")
    return f"{base}/modules/operacional/controllers/redesign_builders/{nome}"


def _builder_le(tabela: str) -> bool:
    """Alguma ABA OFERECIDA no menu é montada em cima dessa tabela?

    Mencionar a tabela no arquivo não basta para condenar: handler de ação fora do
    menu pode citá-la sem que ninguém veja. O defeito é a tela que o gerente ABRE
    estar sentada numa fonte morta. Então olha só os blocos out["slug"] = ... e só
    os slugs que o menu realmente oferece.
    """
    try:
        with open(_fonte("operacional.py"), encoding="utf-8") as f:
            src = f.read()
        with open(_fonte("_op_grupos.py"), encoding="utf-8") as f:
            menu = f.read()
    except OSError:
        return False
    for m in re.finditer(r'out\["([\w-]+)"\]\s*=', src):
        slug, ini = m.group(1), m.end()
        if f'("{slug}"' not in menu:  # aba não oferecida no menu → não é a tela de ninguém
            continue
        # janela = daqui até a PRÓXIMA aba. Fronteira exata sob qualquer aninhamento
        # de try/except. Janela fixa (1400) ou cortada no `except` vazava para os
        # blocos vizinhos e acusava telas que nunca tocaram a tabela.
        prox = src.find('out["', ini)
        janela = src[ini:prox if prox > ini else len(src)]
        # sem comentários: o critério julga o que a aba CONSULTA, não o que eu escrevi
        # sobre ela. O comentário explicando a remoção da aba morta citava o nome da
        # tabela e se auto-acusava.
        codigo = "\n".join(ln for ln in janela.splitlines() if not ln.lstrip().startswith("#"))
        if tabela in codigo:
            return True
    return False


def _cond4_oraculos() -> tuple[bool, str]:
    """4 · os oráculos do operacional continuam verdes."""
    d = os.path.join(RAIZ, "backend/scripts/orq")
    if not os.path.exists(d):
        return False, "pasta de oráculos não encontrada (rode do host)"
    alvos = sorted(f for f in os.listdir(d)
                   if f.startswith(("test_oraculo_op_", "test_acao_op_", "test_read_operacional")))
    falhas = []
    for f in alvos:
        try:
            r = subprocess.run(["docker", "exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend",
                                "python3", f"/app/scripts/orq/{f}"],
                               capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                falhas.append(f)
        except Exception:  # noqa: BLE001
            falhas.append(f"{f}(erro)")
    return (not falhas), (f"{len(alvos) - len(falhas)}/{len(alvos)} verdes"
                          + (f" · vermelhos: {', '.join(falhas)}" if falhas else ""))


def main() -> int:
    print("FECHADO_OPERACIONAL — critério de aceite executável\n")
    res: list[bool] = []

    if NO_CONTAINER:
        print("  ⚠️  rodando dentro do container: condições 1-4 exigem o host (puladas)\n")
    else:
        print("[código]")
        for titulo, fn in (
            ("1 · repositório: 0 chamada a método inexistente", _t1_repositorio),
            ("2 · vocabulário: 0 CRITICO em operacional/campo", _t2_vocabulario),
            ("3 · rotas do front: 0 inexistente alcançável por tela", _t3_rotas_frontend),
        ):
            ok, det = fn()
            res.append(_ok(ok, titulo, det))
        ok4, det4 = _cond4_oraculos()
        res.append(_ok(ok4, "4 · oráculos do operacional verdes", det4))

    print("\n[dado]")
    if NO_CONTAINER or "--so-dado" in sys.argv:
        # dentro do container: o banco é alcançável daqui
        for ok, titulo, det in asyncio.run(_condicoes_de_banco()):
            n = {"disciplinar": 5, "apuração": 6, "tabela": 7}[titulo.split(":")[0].split()[0]]
            res.append(_ok(ok, f"{n} · {titulo}", det))
    else:
        # no host o Postgres não é alcançável (vive no container) — delega o bloco [dado]
        r = subprocess.run(["docker", "exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend",
                            "python3", "/app/scripts/qa/fechado_operacional.py", "--so-dado"],
                           capture_output=True, text=True, timeout=300)
        linhas = [ln for ln in r.stdout.splitlines()
                  if re.match(r"\s*[✅❌] [567] ·", ln)]
        for ln in linhas:
            print(f"  {ln.strip()}")
            res.append(ln.strip().startswith("✅"))
        if not linhas:
            print(f"  ❌ bloco [dado] não retornou — {r.stderr.strip()[-200:]}")
            res.append(False)

    fechado = all(res)
    print(f"\n{'✅ MÓDULO FECHADO' if fechado else '❌ NÃO FECHADO'} — {sum(res)}/{len(res)} condições")
    return 0 if fechado else 1


if __name__ == "__main__":
    raise SystemExit(main())
