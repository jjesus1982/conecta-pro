"""Observabilidade do barramento de eventos — READ-ONLY.

Mostra a orquestra tocando: quem publica o quê, com que frequência, e quem reage.

POR QUE LEITOR E NAO SUBSCRIBER
  O `publish()` faz `xadd` no Redis ANTES de qualquer handler (maxlen=10000 por stream),
  entao todo evento ja fica gravado e replayavel mesmo sem assinante. Registrar um
  subscriber de log exigiria uma linha em `main_production.py` -- zona proibida -- e
  acrescentaria caminho de codigo em producao para obter o que ja esta no Redis.
  Ler custa nada e nao muda comportamento nenhum.

ATENCAO: o bus publica no Redis **db 1** (`redis://.../1`), nao no db 0. Medir o db 0
faz parecer que o barramento esta morto -- foi o erro que gerou este script.

Rodar no host:
    cd /opt/conecta-pro && python3 backend/scripts/orquestra_eventos.py
    python3 backend/scripts/orquestra_eventos.py --ultimos 20     # fluxo recente
"""

import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DB = "1"


def _redis(*args: str) -> str:
    pw = re.search(r"^REDIS_PASSWORD=(.*)$", (RAIZ / ".env").read_text(), re.M)
    cmd = ["docker", "exec", "conecta-pro-redis", "redis-cli"]
    if pw:
        cmd += ["-a", pw.group(1).strip(), "--no-auth-warning"]
    cmd += ["-n", DB, *args]
    try:
        # S603: argv montado aqui, sem shell e sem entrada externa — nao ha injecao.
        return subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout  # noqa: S603
    except Exception as exc:  # noqa: BLE001 — observabilidade nunca derruba nada
        sys.stderr.write(f"redis indisponivel: {exc}\n")
        return ""


def catalogo() -> dict[str, str]:
    """CONSTANTE -> 'valor.do.evento' declarados em EventTypes."""
    bus = RAIZ / "backend/infrastructure/event_bus/bus.py"
    return dict(re.findall(r'^\s+([A-Z_]{4,})\s*=\s*"([a-z][a-z0-9_.]+)"', bus.read_text(), re.M))


def quem_escuta() -> dict[str, set[str]]:
    """evento -> modulos com `.subscribe(` no mesmo arquivo que cita o EventTypes.

    PISO, nao teto: a SOPHIA registra 15 padroes com wildcard em runtime e nao aparece aqui.
    """
    cat = catalogo()
    sub: dict[str, set[str]] = defaultdict(set)
    mods = RAIZ / "backend/modules"
    for m in mods.iterdir():
        if not m.is_dir() or m.name.startswith(("_", "graphify")):
            continue
        for f in m.rglob("*.py"):
            s = str(f)
            if "pycache" in s or "quarentena" in s:
                continue
            try:
                t = f.read_text(errors="ignore")
            except OSError:
                # S112: arquivo ilegivel e ruido esperado numa varredura; pular e correto.
                continue
            if ".subscribe(" not in t:
                continue
            for c in re.findall(r"EventTypes\.([A-Z_]{4,})", t):
                if c in cat:
                    sub[cat[c]].add(m.name)
    return sub


def main() -> None:
    n_ultimos = 0
    if "--ultimos" in sys.argv:
        n_ultimos = int(sys.argv[sys.argv.index("--ultimos") + 1])

    streams = sorted(x for x in _redis("--scan", "--pattern", "conecta:stream:*").split() if x)
    if not streams:
        print("Nenhum stream em conecta:stream:* (db 1). O bus nao publicou nada ainda.")
        return

    tipos: Counter = Counter()
    por_stream: dict[str, int] = {}
    recentes: list[tuple[str, str]] = []
    for s in streams:
        por_stream[s] = int((_redis("XLEN", s) or "0").strip() or 0)
        bruto = _redis("XRANGE", s, "-", "+", "COUNT", "1000").splitlines()
        for i, linha in enumerate(bruto):
            if linha.strip() == "event_type" and i + 1 < len(bruto):
                ev = bruto[i + 1].strip()
                tipos[ev] += 1
                recentes.append((s.split(":")[-1], ev))

    sub = quem_escuta()
    total = sum(por_stream.values())
    print(f"=== BARRAMENTO — {total} eventos gravados (Redis db {DB}) ===\n")
    print("por stream:")
    for s, n in sorted(por_stream.items(), key=lambda x: -x[1]):
        if n:
            print(f"  {n:5}  {s.split(':')[-1]}")

    print(f"\n=== TIPOS QUE DISPARAM ({len(tipos)}) — 🔊 tem quem reaja · 🔇 ninguem reage ===")
    for ev, n in tipos.most_common():
        ouvintes = sub.get(ev)
        marca = "🔊" if ouvintes else "🔇"
        alvo = f"→ {','.join(sorted(ouvintes))}" if ouvintes else "(sem handler in-process)"
        print(f"  {marca} {n:4}  {ev:38} {alvo}")

    mudos = [e for e in tipos if not sub.get(e)]
    print(f"\nresumo: {len(tipos)} tipos disparam · {len(tipos)-len(mudos)} com reacao · {len(mudos)} sem")
    declarados = set(catalogo().values())
    print(f"        {len(declarados)} declarados no catalogo · {len(declarados - set(tipos))} nunca dispararam")

    if n_ultimos:
        print(f"\n=== FLUXO RECENTE (ultimos {n_ultimos}) ===")
        for stream, ev in recentes[-n_ultimos:]:
            print(f"  {stream:14} {ev}")


if __name__ == "__main__":
    main()
