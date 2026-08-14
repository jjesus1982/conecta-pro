#!/usr/bin/env python3
"""Critério de aceite EXECUTÁVEL do módulo Fiscal/Contabilidade (ordem de fechamento 14/08/2026).

Sai 0 só quando as 10 condições passam. Enquanto sair vermelho, o módulo não fechou.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/fechado_fiscal.py

# O CORTE — e por que ele é medido no VENCIMENTO, não na competência

Decisão do Jordan (14/08): o histórico até 31/07 serviu para homologar e está encerrado. O que
importa é de **01/08/2026 em diante**, nos DOIS CNPJs.

Aplicar esse corte à *competência* seria medir a coisa errada, e o número mostra por quê:

    competência 07/2026  →  vence 07/08 (FGTS, eSocial) e 20/08 (DAS, INSS, IRRF)
    competência 08/2026  →  vence em SETEMBRO

**O que está vivo em agosto é a competência 07.** A 08 nem deveria existir hoje:
`calendario_service.garantir_ate_hoje` só cria até a última competência ENCERRADA, de
propósito — "criar obrigação de mês aberto encheria a tela de prazo que ainda não existe".
Forçar a competência 08 agora quebraria esse desenho para satisfazer a régua.

Então o corte aqui é `data_vencimento >= 2026-08-01`: é a data que gera multa, é a que o
Jordan enxerga, e ela captura a competência 07 (vencendo agora) e a 08 (quando nascer, em
setembro). Nada anterior a 01/08 é medido.

# A regra do "regime CERTO" — evidência, nunca legislação

`calendario_service` recusa deduzir da lei quais obrigações a empresa tem, e a recusa está
certa: "deduzir da legislação seria eu decidindo o enquadramento dela". Este gate mantém a
mesma disciplina e só afirma o que a NOSSA base prova:

  * obrigação derivada de FOLHA (FGTS/INSS/IRRF/ESOCIAL) pertence ao CNPJ que tem os
    `hr_payslips` daquela competência. Medido em 14/08: a folha é da Patrimonial desde
    06/2026 (51 holerites em 07/2026, FGTS R$7.922,32) e as obrigações de folha da
    competência 07 estão na ELETRÔNICA, que não tem folha desde maio.
  * DAS só existe em `simples_nacional`. É definição do tributo, não enquadramento.

O que este gate NÃO decide, e fica para o Jordan: se a Eletrônica sem folha ainda deve
ESOCIAL sem movimento, e se a Patrimonial (serviço, Simples III) precisa de certidão
ESTADUAL. Ambos estão marcados no relatório, não silenciados aqui.
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from datetime import date

RAIZ = "/opt/conecta-pro"
#: Estamos DENTRO do container? (o molde do operacional chamava isto de NO_CONTAINER, que lia
#: ao contrário do que significa). Dentro do container não existe `docker` — as travas rodam
#: local; no host, só a que precisa do Postgres passa por `docker exec`.
DENTRO = os.path.isdir("/app/modules") and not os.path.isdir(os.path.join(RAIZ, "backend/scripts/qa"))
BASE = "/app" if DENTRO else os.path.join(RAIZ, "backend")

#: O corte declarado pelo Jordan em 14/08/2026. Medido no VENCIMENTO — ver docstring.
CORTE = date(2026, 8, 1)

#: Obrigações que nascem da folha. Se a empresa não tem holerite na competência, a
#: obrigação não é dela — quem tem a folha responde por elas.
TIPOS_DE_FOLHA = ("FGTS", "INSS", "IRRF", "ESOCIAL", "FGTS_CONSIGNADO")

#: Certidões exigidas dos DOIS CNPJs. Saiu do conjunto REAL da Eletrônica (medido 14/08),
#: menos `registro_cnpj`, que é cadastro e não certidão.
#: ⚠️ `certidao_negativa_estadual` é ICMS — se o Jordan confirmar que a Patrimonial (serviço
#: puro, CNAE 8111-7/00) não precisa dela, tire desta tupla. É a única linha a mudar.
CERTIDOES_EXIGIDAS = (
    "certidao_negativa_federal",
    "certidao_negativa_inss",
    "certidao_negativa_fgts",
    "certidao_negativa_trabalhista",
    "certidao_negativa_municipal",
    "certidao_negativa_estadual",
    "alvara_funcionamento",
)

#: As 5 telas de cálculo da F1 — o motor devolve o número e a tela descarta o corpo.
CALCULADORAS = ("calc-simples", "calc-lucro-real", "calc-comparativo",
                "calc-limite-simples", "calc-retencoes")

#: As 8 tools mínimas do agente fiscal (F4).
TOOLS_FISCAIS = ("calcular_das", "calcular_lucro_real", "comparar_regimes",
                 "calcular_retencoes", "obrigacoes_do_mes", "certidoes_vencendo",
                 "guias_pendentes", "propor_baixa_obrigacao")

MEU = ("modules/fiscal", "modules/fiscal_contabil", "modules/government_integrations",
       "/fiscal", "/government")


def _ok(cond: bool, titulo: str, detalhe: str = "") -> bool:
    print(f"  {'✅' if cond else '❌'} {titulo}" + (f" — {detalhe}" if detalhe else ""))
    return cond


def _rodar(script: str, precisa_banco: bool = False) -> str:
    """Roda uma trava e devolve stdout+stderr.

    `precisa_banco` só importa no host: a trava que confronta o Postgres não alcança o banco
    de fora, então vai por `docker exec`. Dentro do container tudo roda local.
    """
    if DENTRO:
        cmd, cwd = [sys.executable, f"/app/scripts/qa/{script}"], "/app"
    elif precisa_banco:
        cmd = ["docker", "exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend",
               "python3", f"/app/scripts/qa/{script}"]
        cwd = None
    else:
        caminho = os.path.join(RAIZ, "backend/scripts/qa", script)
        if not os.path.exists(caminho):
            raise FileNotFoundError(script)
        cmd, cwd = [sys.executable, caminho], RAIZ
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900, cwd=cwd,
                       env={**os.environ, "PYTHONPATH": BASE})
    return r.stdout + r.stderr


# ─────────────────────────────────────────────────────────────────── 1 a 4: agosto no banco

async def _condicoes_de_banco() -> list[tuple[bool, str, str]]:
    sys.path.insert(0, BASE)
    from sqlalchemy import text  # noqa: PLC0415

    from core.database import async_session_factory  # noqa: PLC0415

    out: list[tuple[bool, str, str]] = []
    async with async_session_factory() as db:
        empresas = (await db.execute(text(
            "SELECT id::text, slug, regime_tributario, replace(replace(replace(cnpj,'.',''),'/',''),'-','') "
            "FROM empresas WHERE status = 'ativa' ORDER BY slug"))).fetchall()

        # 1 · CERTIDÕES — exigidas, válidas, e com data DO EMISSOR.
        # Três defeitos distintos, e o gate separa: faltando · vencida · data impossível.
        # A `certidao_negativa_estadual` da Eletrônica foi emitida 11/08 e "vence" 09/08:
        # validade anterior à emissão é dado fabricado, não certidão vencida.
        faltando, vencidas, sem_emissao, impossiveis = [], [], [], []
        for _id, slug, _reg, cnpj in empresas:
            for tipo in CERTIDOES_EXIGIDAS:
                r = (await db.execute(text(
                    "SELECT issue_date, expiry_date FROM ged_certidoes "
                    "WHERE cnpj = :c AND document_type = :t LIMIT 1"),
                    {"c": cnpj, "t": tipo})).first()
                if not r:
                    faltando.append(f"{slug}/{tipo}")
                    continue
                emissao, validade = r
                if emissao is None:
                    sem_emissao.append(f"{slug}/{tipo}")
                elif validade and validade < emissao:
                    impossiveis.append(f"{slug}/{tipo}")
                if validade is None or validade < date.today():
                    vencidas.append(f"{slug}/{tipo}")
        det = (f"{len(faltando)} faltando · {len(vencidas)} vencida(s) · "
               f"{len(sem_emissao)} sem data do emissor · {len(impossiveis)} com validade < emissão")
        if faltando:
            det += f"\n       faltando: {', '.join(faltando)}"
        if vencidas:
            det += f"\n       vencidas: {', '.join(vencidas)}"
        if sem_emissao:
            det += f"\n       sem emissão: {', '.join(sem_emissao)}"
        if impossiveis:
            det += f"\n       validade < emissão: {', '.join(impossiveis)}"
        out.append((not (faltando or vencidas or sem_emissao or impossiveis),
                    "1 · certidões dos 2 CNPJs válidas, com data do emissor", det))

        # 2 · OBRIGAÇÕES vencendo de 01/08 em diante, cada uma no CNPJ que a evidência sustenta.
        problemas: list[str] = []
        linhas = (await db.execute(text(
            "SELECT e.slug, e.regime_tributario, o.empresa_id::text, o.tipo, "
            "       o.competencia_ano, o.competencia_mes, o.data_vencimento "
            "  FROM fiscal_obligations o JOIN empresas e ON e.id = o.empresa_id "
            " WHERE o.active AND o.data_vencimento >= :corte "
            " ORDER BY e.slug, o.data_vencimento"), {"corte": CORTE})).fetchall()

        sem_nada = [s for _i, s, _r, _c in empresas
                    if not any(ln[0] == s for ln in linhas)]
        for s in sem_nada:
            problemas.append(f"{s}: NENHUMA obrigação vencendo de 08/2026 em diante")

        for slug, regime, emp_id, tipo, ano, mes, _venc in linhas:
            if tipo == "DAS" and regime != "simples_nacional":
                problemas.append(f"{slug}: DAS em empresa {regime} (DAS só existe no Simples)")
            if tipo in TIPOS_DE_FOLHA and mes:
                # quem tem a FOLHA daquela competência responde pela obrigação de folha
                dono = (await db.execute(text(
                    "SELECT e.slug FROM hr_payslips p JOIN empresas e ON e.id = p.empresa_id "
                    " WHERE extract(year from p.competence_start) = :a "
                    "   AND extract(month from p.competence_start) = :m "
                    " GROUP BY e.slug ORDER BY count(*) DESC LIMIT 1"),
                    {"a": ano, "m": mes})).scalar()
                if dono and dono != slug:
                    problemas.append(
                        f"{slug}: {tipo} de {mes:02d}/{ano} — a folha dessa competência é da {dono}")
        out.append((not problemas, "2 · obrigações de 08/2026 em diante no CNPJ e regime certos",
                    f"{len(linhas)} obrigação(ões) medida(s), {len(problemas)} problema(s)"
                    + ("\n       " + "\n       ".join(problemas) if problemas else "")))

        # 3 · GUIAS — obrigação vencida há mais de 5 dias sem valor nem recibo é prazo cego.
        # Só de 01/08 em diante: as de abr–jul são "status não conciliado do período de
        # homologação", decisão do Jordan, e NÃO se persegue retroativamente.
        sem_guia = (await db.execute(text(
            "SELECT e.slug, o.tipo, o.data_vencimento "
            "  FROM fiscal_obligations o JOIN empresas e ON e.id = o.empresa_id "
            " WHERE o.active AND o.data_vencimento >= :corte "
            "   AND o.data_vencimento < CURRENT_DATE - 5 "
            "   AND o.status <> 'cumprida' "
            "   AND (o.numero_recibo IS NULL OR o.numero_recibo = '') "
            "   AND o.valor_devido IS NULL "
            " ORDER BY o.data_vencimento"), {"corte": CORTE})).fetchall()
        out.append((not sem_guia, "3 · obrigação vencida há >5 dias tem guia",
                    f"{len(sem_guia)} sem guia"
                    + ("\n       " + "\n       ".join(
                        f"{s}/{t} venceu {v}" for s, t, v in sem_guia) if sem_guia else "")))

        # 4 · NFS-e — contrato ativo fatura no mês, pelo CNPJ dele.
        # Vale só depois que o mês roda: dia 14 quase ninguém emitiu ainda, e isso é normal,
        # não defeito. O gate mede e mostra; fecha sozinho no fim do mês.
        hoje = date.today()
        sem_nota = (await db.execute(text(
            "SELECT e.slug, count(*) FROM contracts c JOIN empresas e ON e.id = c.empresa_id "
            " WHERE c.status::text = 'active' "
            "   AND NOT EXISTS (SELECT 1 FROM nfse_emitidas_nacional n "
            "                    WHERE n.empresa_id = c.empresa_id "
            "                      AND n.data_emissao >= :ini) "
            " GROUP BY e.slug ORDER BY e.slug"), {"ini": hoje.replace(day=1)})).fetchall()
        det4 = " · ".join(f"{s}: {n} contrato(s) sem nota no mês" for s, n in sem_nota) or "todos faturaram"
        out.append((not sem_nota, "4 · contrato ativo com NFS-e no mês, pelo CNPJ certo", det4))

        # 6 · ROTINAS — o sino sem falha recorrente, e o espelho do eSocial gravando.
        falhas = (await db.execute(text(
            "SELECT title, count(*) FROM communication_notifications "
            " WHERE created_at > now() - interval '48 hours' AND title ILIKE '%Tarefa agendada falhou%' "
            " GROUP BY title ORDER BY 2 DESC"))).fetchall()
        ultima = (await db.execute(text(
            "SELECT max(consultada_em) FROM esocial_espelho_janelas"))).scalar()
        espelho_ok = ultima is not None and (
            hoje - (ultima.date() if hasattr(ultima, "date") else ultima)).days <= 2
        det6 = f"{len(falhas)} tarefa(s) falhando em 48h · espelho consultado {ultima or 'NUNCA'}"
        if falhas:
            det6 += "\n       " + "\n       ".join(f"{t.replace('Tarefa agendada falhou: ','')} ({n}×)"
                                                   for t, n in falhas)
        out.append((not falhas and espelho_ok, "6 · rotinas: sino limpo e espelho gravando", det6))

    return out


# ─────────────────────────────────────────────────────────────── 5 e 8: código, sem banco

def _c5_calculadoras() -> tuple[bool, str]:
    """5 · as 5 telas de cálculo exibem o número.

    Regra da casa: *"Calculado" sem número é defeito, não sucesso.* `type:"form"` no ModuleView
    exibe só `d.message`, então uma tela de cálculo assim responde "DAS calculado" e joga fora
    os R$13.030 que o motor devolveu.

    ⚠️ O contrato é `submit.showResult` — opt-in, de propósito: a maioria dos forms é AÇÃO, e
    despejar o corpo da resposta neles seria ruído. Medir a presença de `type:"form"` sozinho
    acusa as 5 injustamente; foi o que o raio-x de 14/08 concluiu, lendo a linha 495 do
    ModuleView sem ver o ramo do `showResult` na 568. As duas pontas já existem desde 09-10/08
    (`8e8181d8` no front, `4e3a905b` no builder) — este critério guarda contra a REGRESSÃO.

    Estático nas duas pontas. Que o painel de fato pinte na tela é lente de NAVEGADOR, e está
    declarada em NÃO COBERTO no relatório.
    """
    try:
        with open(f"{BASE}/modules/operacional/controllers/redesign_builders/fiscal.py",
                  encoding="utf-8") as f:
            builder = f.read()
    except OSError as e:  # noqa: BLE001
        return False, f"não li o builder: {e}"

    # O front não existe dentro do container do backend. Sem ele, metade do contrato fica
    # POR VERIFICAR — e por verificar não é verde. "NÃO VERIFICADO" é resultado válido;
    # "passou" sem evidência não é.
    caminho_front = f"{RAIZ}/frontend/src/components/redesign/ModuleView.tsx"
    if not os.path.exists(caminho_front):
        return False, ("NÃO VERIFICADO: o ModuleView não é alcançável daqui — "
                       "rode este gate no HOST para medir a ponta do front")
    with open(caminho_front, encoding="utf-8") as f:
        front = f.read()

    mudas = []
    for calc in CALCULADORAS:
        m = re.search(rf'out\["{re.escape(calc)}"\]\s*=\s*\{{(.{{0,1600}}?)\n    \}}', builder, re.S)
        if not m:
            mudas.append(f"{calc} (bloco não encontrado)")
        elif '"showResult": True' not in m.group(1):
            mudas.append(calc)
    if "showResult" not in front:
        return False, "o ModuleView não honra showResult — as 5 telas ficam mudas"
    return not mudas, f"{5 - len(mudas)}/5 com showResult, e o ModuleView honra" + (
        f" · sem painel: {', '.join(mudas)}" if mudas else "")


def _c8_tools() -> tuple[bool, str]:
    """8 · as 8 tools do agente fiscal registradas, e o agente sem SQL próprio."""
    achadas = set()
    for raiz, _d, arqs in os.walk(BASE + "/modules"):
        if "_quarentena" in raiz or "__pycache__" in raiz:
            continue
        for a in arqs:
            if not a.endswith(".py"):
                continue
            try:
                with open(os.path.join(raiz, a), encoding="utf-8") as f:
                    src = f.read()
            except OSError:
                continue
            for t in TOOLS_FISCAIS:
                if re.search(rf'ToolDef\([^)]*["\']{t}["\']', src, re.S) or \
                   re.search(rf'name\s*=\s*["\']{t}["\']', src):
                    achadas.add(t)
    faltam = [t for t in TOOLS_FISCAIS if t not in achadas]
    return not faltam, f"{len(achadas)}/{len(TOOLS_FISCAIS)} registradas" + (
        f" · faltam: {', '.join(faltam)}" if faltam else "")


# ────────────────────────────────────────────────────────── 7, 9 e 10: travas e oráculos

def _c7_beats() -> tuple[bool, str]:
    try:
        saida = _rodar("checar_beats.py", precisa_banco=True)  # precisa do celery_app registrado
    except Exception as e:  # noqa: BLE001
        return False, f"não rodou: {e}"
    m = re.search(r"(\d+)\s+achado", saida)
    n = int(m.group(1)) if m else (0 if "0 achado" in saida or "nenhum" in saida.lower() else -1)
    if n < 0:
        return False, "saída não reconhecida (trava mudou de formato?)"
    return n == 0, f"{n} achado(s)"


def _c9_travas() -> tuple[bool, str]:
    """9 · repositorio · vocabulario · rotas_frontend == 0 no bloco fiscal/government."""
    total, detalhe = 0, []
    for script, precisa_banco in (("checar_repositorio.py", False),
                                  ("checar_vocabulario.py", True),
                                  ("checar_rotas_frontend.py", False)):
        try:
            saida = _rodar(script, precisa_banco=precisa_banco)
        except Exception as e:  # noqa: BLE001
            detalhe.append(f"{script}: não rodou ({e})")
            total += 1
            continue
        n = sum(1 for ln in saida.splitlines()
                if any(p in ln for p in MEU) and ("CRITICO" in ln or "x /api/v1/" in ln))
        total += n
        detalhe.append(f"{script.replace('checar_','').replace('.py','')}: {n}")
    return total == 0, " · ".join(detalhe)


def _c10_oraculos() -> tuple[bool, str]:
    """10 · os 6 oráculos do fiscal verdes."""
    orq = os.path.join(BASE, "scripts/orq")
    testes = sorted(a for a in os.listdir(orq)
                    if re.search(r"(fiscal|contabil|esocial)", a) and a.endswith(".py"))
    vermelhos = []
    for t in testes:
        r = subprocess.run([sys.executable, os.path.join(orq, t)],
                           capture_output=True, text=True, timeout=600,
                           cwd=BASE, env={**os.environ, "PYTHONPATH": BASE})
        if r.returncode != 0:
            vermelhos.append(t.replace("test_oraculo_", "").replace("test_", "").replace(".py", ""))
    return not vermelhos, f"{len(testes) - len(vermelhos)}/{len(testes)} verdes" + (
        f" · vermelhos: {', '.join(vermelhos)}" if vermelhos else "")


def main() -> int:
    print("\n╔══ FECHADO? · Fiscal / Contabilidade ═══════════════════════════════════")
    print(f"║  corte: vencimento >= {CORTE.isoformat()} · nada anterior é medido")
    print("╚════════════════════════════════════════════════════════════════════════\n")

    resultados: list[bool] = []

    print("AGOSTO EM DIANTE — o que fecha")
    de_banco = asyncio.run(_condicoes_de_banco())
    for ok, titulo, det in de_banco[:4]:
        resultados.append(_ok(ok, titulo, det))

    print("\nO QUE SUSTENTA")
    for cond, titulo in ((_c5_calculadoras, "5 · as 5 calculadoras exibem o número"),):
        ok, det = cond()
        resultados.append(_ok(ok, titulo, det))
    ok, titulo, det = de_banco[4]
    resultados.append(_ok(ok, titulo, det))
    for cond, titulo in ((_c7_beats, "7 · checar_beats sem achados (importa · existe · PRODUZ)"),
                         (_c8_tools, "8 · as 8 tools do agente fiscal registradas"),
                         (_c9_travas, "9 · travas zeradas em fiscal/government"),
                         (_c10_oraculos, "10 · oráculos do fiscal verdes")):
        ok, det = cond()
        resultados.append(_ok(ok, titulo, det))

    verdes = sum(resultados)
    print(f"\n  {verdes}/{len(resultados)} condições verdes")
    if verdes < len(resultados):
        print("  ❌ O MÓDULO NÃO FECHOU.\n")
        return 1
    print("  ✅ FECHADO.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
