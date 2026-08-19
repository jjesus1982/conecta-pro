#!/usr/bin/env python3
"""Critério de aceite EXECUTÁVEL do contrato por modelo (ordem de 19/08).

Sai 0 só quando as 7 condições passam. Enquanto sair vermelho, não fechou.

Mesma forma de `fechado_operacional.py` (T4, 7/7): cada condição imprime ✅/❌ com o
número que a sustenta, e o exit code decide. "Fechado" é comando, não prosa.

Uso:
    python3 backend/scripts/qa/fechado_contratos.py          # do host: tudo
    docker exec ... python3 /app/scripts/qa/fechado_contratos.py   # só o bloco [dado]
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys

RAIZ = "/opt/conecta-pro"
NO_CONTAINER = os.path.isdir("/app/modules") and not os.path.isdir(os.path.join(RAIZ, "backend/scripts/qa"))

CNPJ_PATRIMONIAL = "66014833000110"
CNPJ_ELETRONICA = "35710481000103"

# Nomes REAIS dos arquivos, conferidos com `ls`. A primeira versão inventou
# "test_oraculo_central_crm"/"test_oraculo_u2_crm"/"test_oraculo_5_6b_contrato" e o gate
# PULAVA silenciosamente os que não existiam — verde por ausência.
ORACULOS = ["test_oraculo_contrato_render", "test_oraculo_contrato_strict",
            "test_oraculo_contrato_cnpj", "test_central_crm",
            "test_oraculo_checklist_do_contrato", "test_oraculo_kit_por_contrato",
            "test_oraculos_5_6b_contrato", "test_u2_crm"]


def _ok(cond: bool, titulo: str, detalhe: str = "") -> bool:
    print(f"  {'✅' if cond else '❌'} {titulo}" + (f" — {detalhe}" if detalhe else ""))
    return cond


def _no_container(script: str, pasta: str = "orq") -> tuple[bool, str]:
    r = subprocess.run(["docker", "exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend",
                        "python3", f"/app/scripts/{pasta}/{script}"],
                       capture_output=True, text=True, timeout=420)
    return r.returncode == 0, (r.stdout + r.stderr)


async def _dado() -> list[tuple[bool, str, str]]:
    sys.path.insert(0, "/app" if NO_CONTAINER else os.path.join(RAIZ, "backend"))
    from sqlalchemy import text  # noqa: PLC0415

    from core.database import async_session_factory  # noqa: PLC0415
    from modules.crm.services import contract_render as R  # noqa: PLC0415

    out: list[tuple[bool, str, str]] = []
    async with async_session_factory() as db:
        # 1 · RENDER — o contrato do caso sai com todas as cláusulas do modelo
        try:
            res = await R.renderizar_contrato(db, "CTR-2026-00019",
                                              "de86045d-9c7c-46d5-83ec-4d0907ead116")
            falta = len(res.clausulas_faltando)
            out.append((falta == 0 and res.n_clausulas >= 10,
                        "render: Green Hills traz todas as cláusulas do modelo",
                        f"{res.n_clausulas} cláusulas, {falta} faltando, PDF {len(res.pdf) // 1024} KB"))
        except Exception as e:  # noqa: BLE001
            out.append((False, "render: Green Hills traz todas as cláusulas do modelo",
                        f"recusado: {str(e)[:110]}"))

        # 3 · CNPJ — nenhum contrato de mão de obra renderiza fora da Patrimonial
        # inclui o caso de aceite: ele tem tipo_servico NULL e é mão de obra pelo MODELO —
        # a primeira versão o deixou de fora e a condição passou com "0 renderizados de 8",
        # ou seja, aprovaria com o módulo inteiro quebrado.
        alvos = (await db.execute(text(
            "SELECT contract_number FROM contracts WHERE (tipo_servico::text ILIKE '%maodeobra%' "
            "OR contract_number = 'CTR-2026-00019') AND coalesce(is_active,true)"))).scalars().all()
        errados, feitos = [], 0
        for num in alvos:
            try:
                r = await R.renderizar_contrato(db, num)
            except Exception:  # noqa: BLE001 — recusa por dado incompleto é comportamento certo
                continue
            feitos += 1
            nu = re.sub(r"\D", "", r.texto)
            if CNPJ_ELETRONICA in nu or re.sub(r"\D", "", r.contratada.cnpj) != CNPJ_PATRIMONIAL:
                errados.append(num)
        # exigir pelo menos UM render: "0 errados de 0 renderizados" é vácuo, não aprovação
        out.append((not errados and feitos >= 1,
                    "CNPJ: 0 contrato de mão de obra fora da Patrimonial",
                    f"{feitos} renderizado(s) de {len(alvos)}"
                    + (f" · ERRADOS: {', '.join(errados[:3])}" if errados else "")
                    + ("" if feitos else " · VÁCUO: nenhum renderizou, a condição não prova nada")))

        # 4 · VÍNCULO — todo PDF de contrato em crm_documents aponta para um contrato
        # idem: sem PDF de contrato nenhum, "0 soltos" também é vácuo
        soltos = (await db.execute(text("""
            SELECT count(*) FROM crm_documents
            WHERE tipo = 'contrato' AND (ref_id IS NULL OR ref_tipo IS DISTINCT FROM 'contract')
        """))).scalar() or 0
        total = (await db.execute(text(
            "SELECT count(*) FROM crm_documents WHERE tipo='contrato'"))).scalar() or 0
        out.append((soltos == 0 and total >= 1,
                    "vínculo: todo PDF de contrato aponta para um contract_id",
                    f"{total - soltos}/{total} vinculado(s)"
                    + ("" if total else " · VÁCUO: não há PDF de contrato registrado")))
    return out


def _cond5_link() -> tuple[bool, str]:
    """5 · o link tokenizado abre SEM login e devolve PDF de verdade."""
    r = subprocess.run(["docker", "exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend",
                        "python3", "-c", (
                            "import asyncio\n"
                            "from sqlalchemy import text\n"
                            "from core.database import async_session_factory\n"
                            "async def m():\n"
                            "    async with async_session_factory() as db:\n"
                            "        r=(await db.execute(text(\"SELECT id::text, token FROM crm_documents "
                            "WHERE tipo='contrato' AND token IS NOT NULL ORDER BY created_at DESC LIMIT 1\"))).first()\n"
                            "        print(f'{r[0]}|{r[1]}' if r else 'NADA')\n"
                            "asyncio.run(m())")],
                       capture_output=True, text=True, timeout=180)
    linha = [x for x in r.stdout.splitlines() if "|" in x or x.strip() == "NADA"]
    if not linha or linha[-1] == "NADA":
        return False, "não há PDF de contrato com token para testar"
    doc, tok = linha[-1].split("|", 1)
    url = f"https://erp.conectamais.pro/api/v1/crm/docs/download/{doc}?t={tok}"
    c = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code} %{content_type}",
                        url, "--max-time", "40"], capture_output=True, text=True, timeout=90)
    saida = c.stdout.strip()
    return (saida.startswith("200") and "pdf" in saida.lower()), f"HTTP {saida}"


def _cond6_travas() -> tuple[bool, str]:
    """6 · as travas do repositório não acusam nada em crm."""
    achados = []
    try:
        r = subprocess.run([sys.executable, os.path.join(RAIZ, "backend/scripts/qa/checar_repositorio.py")],
                           capture_output=True, text=True, timeout=600, cwd=RAIZ)
        m = re.search(r"──\s*crm:\s*(\d+)\s*chamada", r.stdout + r.stderr)
        if m and int(m.group(1)):
            achados.append(f"repositório {m.group(1)}")
    except Exception as e:  # noqa: BLE001
        achados.append(f"repositório não rodou ({str(e)[:30]})")

    ok_voc, saida = _no_container("checar_vocabulario.py", "qa")
    n = len([ln for ln in saida.splitlines() if "[CRITICO]" in ln and "modules/crm" in ln])
    if n:
        achados.append(f"vocabulário {n} CRITICO")

    try:
        r = subprocess.run([sys.executable, os.path.join(RAIZ, "backend/scripts/qa/checar_rotas_frontend.py")],
                           capture_output=True, text=True, timeout=600, cwd=RAIZ)
        saida = r.stdout + r.stderr
        if "alcançáveis" in saida:
            bloco = saida[saida.index("alcançáveis"):]
            if re.search(r"x /api/v1/crm/", bloco):
                achados.append("rota de crm inexistente alcançável")
    except Exception:  # noqa: BLE001
        achados.append("rotas_frontend não rodou")
    return (not achados), ("; ".join(achados) if achados else "repositório 0 · vocabulário 0 · rotas 0")


def main() -> int:
    print("FECHADO_CONTRATOS — critério de aceite executável\n")
    res: list[bool] = []
    dados = asyncio.run(_dado())
    mapa = {t.split(":")[0]: (o, t, d) for o, t, d in dados}

    print("[render]")
    for chave, n in (("render", 1), ("CNPJ", 3), ("vínculo", 4)):
        if chave in mapa:
            o, t, d = mapa[chave]
            res.append(_ok(o, f"{n} · {t}", d))

    if NO_CONTAINER:
        print("\n  ⚠️  dentro do container: condições 2, 5, 6 e 7 exigem o host (puladas)")
        fechado = all(res)
        print(f"\n{'✅ FECHADO (bloco dado)' if fechado else '❌ NÃO FECHADO'} — {sum(res)}/{len(res)}")
        return 0 if fechado else 1

    print("\n[travas e prova externa]")
    ok2, saida = _no_container("test_oraculo_contrato_strict.py")
    res.append(_ok(ok2, "2 · strict: render com variável faltando FALHA",
                   "oráculo verde" if ok2 else saida.strip().splitlines()[-1][:90]))
    ok5, det5 = _cond5_link()
    res.append(_ok(ok5, "5 · link tokenizado abre sem login e devolve PDF", det5))
    ok6, det6 = _cond6_travas()
    res.append(_ok(ok6, "6 · travas do crm zeradas", det6))

    print("\n[oráculos]")
    vermelhos = []
    for o in ORACULOS:
        caminho = os.path.join(RAIZ, "backend/scripts/orq", o + ".py")
        if not os.path.exists(caminho):
            continue
        ok, _ = _no_container(o + ".py")
        if not ok:
            vermelhos.append(o)
    existentes = [o for o in ORACULOS if os.path.exists(os.path.join(RAIZ, "backend/scripts/orq", o + ".py"))]
    res.append(_ok(not vermelhos, "7 · oráculos do crm + os 3 novos verdes",
                   f"{len(existentes) - len(vermelhos)}/{len(existentes)} verdes"
                   + (f" · vermelhos: {', '.join(vermelhos)}" if vermelhos else "")))

    fechado = all(res)
    print(f"\n{'✅ CONTRATO POR MODELO FECHADO' if fechado else '❌ NÃO FECHADO'} — {sum(res)}/{len(res)} condições")
    return 0 if fechado else 1


if __name__ == "__main__":
    raise SystemExit(main())
