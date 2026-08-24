#!/usr/bin/env python3
"""Os caçadores rodam todo dia — e só reclamam quando a dívida CRESCE.

Os dois caçadores nasceram com 63 pistas em aberto (40 de fabricação, 23 de vocabulário).
Ligá-los cru na varredura diária faria o sino tocar vermelho toda madrugada com o mesmo
número — e sino que toca sempre é sino que ninguém escuta. Foi por isso que ficaram de fora,
e ficar de fora contradiz a regra da casa: skill só age quando invocada, check age sempre.

Saída: **linha de base**, o mesmo desenho do oráculo de período fechado. O que já existe fica
registrado; o que ENTRAR depois é regressão e acusa. Assim a dívida velha não vira ruído e
fabricação nova não passa.

Baixar a linha de base (consertou algo) é automático. Subir exige commit no
`.baseline.json` — deixar a dívida crescer é decisão, não acidente.

    python3 backend/scripts/qa/checar_regressao.py            # confere
    python3 backend/scripts/qa/checar_regressao.py --gravar   # (re)grava a base
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent

#: FORA do repositório de propósito. A base é escrita SOZINHA quando a dívida cai, e um
#: arquivo versionado alterado por cron deixa o working tree sujo indefinidamente — nenhum
#: terminal vai commitar isso. Pela nossa própria regra, ` M` = outro terminal para e espera:
#: a automação dispararia a regra da parede falsamente.
BASE = Path("/var/lib/conecta/qa_baseline.json")

#: caçador -> como contar as pistas na saída dele
CACADORES = {
    "cacar_fabricacao.py": lambda s: sum(
        1 for ln in s.splitlines() if ln.startswith("   ") and ":" in ln),
    "checar_vocabulario.py": lambda s: sum(
        1 for ln in s.splitlines() if ln.strip().startswith("[CRITICO]")),
}

#: Estáticos: rodam no HOST, onde os caminhos do repositório existem. Pôr o
#: `checar_repositorio` no container fez ele achar 0 — a raiz lá é /app, não
#: /opt/conecta-pro/backend, e "zero achados" por caminho errado é o pior tipo de verde.
CACADORES_HOST = {
    # Nasceu do MVP de fechamento de `services`: 4 de 6 rotas em 500 porque o controller
    # chamava método que o repositório nunca teve. 139 chamadas assim no sistema.
    # Lê a linha canônica TOTAL: soma as DUAS travas (método inexistente + forma errada).
    # A versão anterior lia só "N chamada(s)" e ignorava a trava de forma — teria deixado
    # passar exatamente os 2 casos que estouravam o dashboard de serviços.
    "checar_repositorio.py": lambda s: next(
        (int(ln.split(":")[1]) for ln in s.splitlines() if ln.startswith("TOTAL:")), 0),
    # Espelho da de cima, do outro lado da parede: frontend chamando rota que o backend não
    # tem. Nasceu do mesmo MVP (slaService pedindo /services/sla onde existe /sla-configs).
    # 666 na estreia, 84 alcançáveis por tela — as 35 literais confirmadas 404 por HTTP.
    "checar_rotas_frontend.py": lambda s: next(
        (int(ln.split(":")[1]) for ln in s.splitlines() if ln.startswith("TOTAL:")), 0),
    # Ideia do T1: contra qual fonte DE FORA cada número foi provado, e quando. Os outros
    # oráculos comparam exibido == banco — os dois lados nossos; se o banco estiver errado,
    # ficam verdes. Foi o caso do extrato (880 duplicatas, 94 sinais invertidos).
    "checar_oraculo_externo.py": lambda s: next(
        (int(ln.split(":")[1]) for ln in s.splitlines() if ln.startswith("TOTAL:")), 0),
}


#: Roda no HOST. Os caçadores precisam do BANCO e do código como está no container; o
#: caçador do arsenal precisa do REPOSITÓRIO e do crontab, que só existem no host. Misturar
#: os dois ambientes foi o primeiro erro deste script: dentro do container o ARSENAL_SKILLS
#: "não existia" e as contagens saíam diferentes (27 em vez de 40) porque a raiz é outra.
_EXEC_CONTAINER = ["docker", "exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend",
                   "python3", "/app/scripts/qa/"]


#: Travas de SIM/NÃO: não contam dívida, passam ou reprovam. Ligadas pelo EXIT CODE e nunca
#: por parser da saída — em 24/08/2026 seis medições por regex sobre texto erraram nos dois
#: sentidos no mesmo dia (três inflaram, três zeraram). Formato de saída muda; exit code é
#: comportamento. É a mesma troca que a condição 2 do gate do Bartolo fez: de grep para sonda.
TRAVAS_BINARIAS = {
    "checar_beats.py": ("container", "rotina agendada que roda e NÃO PRODUZ"),
    "checar_periodo_do_servidor.py": ("container",
                                      "competência/data vinda do MODELO e não do servidor"),
    "checar_desmonte_comportamento.py": ("host",
                                         "oráculo que escreve em produção e deixa linha"),
}

#: Órfã DECLARADA: existe, ninguém roda, e está escrito por quê e de quem é. Exceção com dono
#: e motivo — não gaveta. Sem esta lista o detector abaixo reprova, que é o correto: trava que
#: ninguém invoca é exatamente a doença que o arsenal veio curar (o `tool_risk_manifest`
#: classificava 254 tools e nenhum código o consultava).
ORFAS_DECLARADAS = {
    # 26 achados hoje (18 sem entrada, 8 sem saída). Ligar como binária deixaria o
    # checar_regressao vermelho para TODOS os terminais até o T4 fechar os 18 que faltam.
    # Vira contada, com linha de base, assim que ele publicar a linha `TOTAL:`.
    "checar_desmonte_oraculos.py": "T4, em curso — 3 de 21 fechados; vira contada ao ter TOTAL:",
}


def _travas_no_disco() -> set[str]:
    return {p.name for p in AQUI.glob("checar_*.py")} | {p.name for p in AQUI.glob("cacar_*.py")}


def _rodar(script: str) -> tuple[int, str]:
    if script in CACADORES_HOST:
        cmd = [sys.executable, str(AQUI / script)]
        conta = CACADORES_HOST[script]
    else:
        cmd = _EXEC_CONTAINER[:-1] + [_EXEC_CONTAINER[-1] + script]
        conta = CACADORES[script]
    r = subprocess.run(cmd, capture_output=True, text=True)
    saida = r.stdout + r.stderr
    return conta(saida), saida


def _avisar_no_sino(falhou: list[str]) -> None:
    """Publica no sino reusando o caminho da varredura (dedup por dia já embutido)."""
    corpo = ("Trava mecânica acusou REGRESSÃO:\n- " + "\n- ".join(falhou) +
             "\n\nCódigo novo trouxe fabricação de valor ou lista literal que a coluna não "
             "tem. Rodar à mão:\n"
             "docker exec conecta-pro-backend python3 /app/scripts/qa/cacar_fabricacao.py")
    cmd = _EXEC_CONTAINER[:-1] + ["/app/modules/notifications/tasks_oraculos.py",
                                  "--avisar", "Travas de QA: regressão", corpo]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(f"  sino: {(r.stdout or r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr) else 'sem resposta'}")


def main() -> int:
    gravar = "--gravar" in sys.argv
    BASE.parent.mkdir(parents=True, exist_ok=True)
    base = json.loads(BASE.read_text()) if BASE.exists() else {}
    agora, falhou = {}, []

    for script in {**CACADORES, **CACADORES_HOST}:
        n, _ = _rodar(script)
        agora[script] = n
        antes = base.get(script)
        if antes is None:
            print(f"  {script}: {n} pista(s) — sem linha de base ainda")
            continue
        if n > antes:
            falhou.append(f"{script}: {antes} -> {n} (+{n - antes} NOVA(s))")
            print(f"  x {script}: {antes} -> {n}  REGRESSÃO")
        elif n < antes:
            print(f"  {script}: {antes} -> {n}  (−{antes - n}, dívida caiu)")
        else:
            print(f"  {script}: {n} (estável)")

    # O caçador do arsenal não tem dívida aceitável: ou o documento confere, ou não confere.
    # Este roda no HOST mesmo: precisa de docs/, skills/_plugin e crontab.
    r = subprocess.run([sys.executable, str(AQUI / "checar_arsenal.py")],
                       capture_output=True, text=True)
    if r.returncode != 0:
        falhou.append("checar_arsenal: o arsenal diverge do sistema")
        print("  x checar_arsenal: o arsenal diverge do sistema")
        print("\n".join("     " + ln for ln in r.stdout.splitlines() if ln.strip().startswith("x")))
    else:
        print("  checar_arsenal: confere")

    # A parede do agente: no git, na imagem e apontando para rota que existe. Também sem
    # dívida aceitável. Ligada aqui porque a lição do dia em que ela nasceu foi justamente
    # esta — o `tool_risk_manifest` classificava 254 tools e NINGUÉM o consultava. Trava que
    # ninguém roda é a mesma doença que ela veio curar.
    r = subprocess.run([sys.executable, str(AQUI / "checar_mcp_tools.py")],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        falhou.append("checar_mcp_tools: a parede do agente está fora do git, fora da "
                      "imagem, ou apontando para rota que não existe")
        print("  x checar_mcp_tools: a parede do agente diverge")
        print("\n".join("     " + ln for ln in r.stdout.splitlines()
                        if ln.strip().startswith("-")))
    else:
        print("  checar_mcp_tools: confere")

    # As travas de sim/não, pelo exit code.
    for script, (onde, oque) in TRAVAS_BINARIAS.items():
        cmd = ([sys.executable, str(AQUI / script)] if onde == "host"
               else _EXEC_CONTAINER[:-1] + [_EXEC_CONTAINER[-1] + script])
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        except subprocess.TimeoutExpired:
            falhou.append(f"{script}: não respondeu em 15min — NÃO VERIFICADO, não aprovado")
            print(f"  x {script}: não respondeu (NÃO VERIFICADO)")
            continue
        if r.returncode != 0:
            falhou.append(f"{script}: {oque}")
            print(f"  x {script}: {oque}")
            for ln in (r.stdout or r.stderr).splitlines()[-6:]:
                print("     " + ln)
        else:
            print(f"  {script}: confere")

    # ── a trava que vigia o próprio arsenal ────────────────────────────────────
    # Nasceu de uma medição em 24/08/2026: 12 travas no disco e QUATRO que nenhum caminho
    # invocava — inclusive a `checar_beats`, escrita no dia anterior justamente contra
    # "rotina que roda e não produz". Trava órfã é pior que trava ausente: ela dá a impressão
    # de cobertura que não existe, e o custo de escrevê-la já foi pago.
    orfas = _travas_no_disco() - set(CACADORES) - set(CACADORES_HOST) - set(TRAVAS_BINARIAS) \
        - set(ORFAS_DECLARADAS) - {"checar_regressao.py", "checar_arsenal.py",
                                   "checar_mcp_tools.py"}
    if orfas:
        falhou.append("trava órfã (existe no disco e nenhum caminho invoca): "
                      + ", ".join(sorted(orfas)))
        print(f"  x arsenal: {len(orfas)} trava(s) órfã(s) — " + ", ".join(sorted(orfas)))
        print("     Ligue em CACADORES/CACADORES_HOST (conta dívida) ou TRAVAS_BINARIAS "
              "(passa/reprova), ou declare em ORFAS_DECLARADAS com DONO e MOTIVO.")
    else:
        print(f"  arsenal: 0 trava órfã ({len(ORFAS_DECLARADAS)} declarada(s) com dono)")

    if gravar or any(agora.get(k, 0) < base.get(k, 10**9) for k in agora):
        # Baixar a base é automático — conserto não deve exigir cerimônia. Subir, não.
        nova = {k: min(v, base.get(k, v)) if not gravar else v for k, v in agora.items()}
        BASE.write_text(json.dumps(nova, indent=2) + "\n")
        print(f"  linha de base atualizada: {nova}")

    if falhou:
        # Sem isto a trava vira log que ninguém lê: o alerta do sino saía só da varredura de
        # oráculos, e regressão de fabricação ficava em /var/log esperando alguém abrir.
        _avisar_no_sino(falhou)
        print("\nREGRESSÃO — código novo trouxe fabricação ou vocabulário fantasma:")
        for f in falhou:
            print(f"  {f}")
        print("\nConserte, ou (se for dívida aceita) suba a base com --gravar e COMMITE o "
              ".baseline.json — deixar a dívida crescer tem que ser decisão escrita.")
        return 1
    print("\nsem regressão")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
