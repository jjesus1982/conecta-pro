"""Os 59 oráculos rodam sozinhos todo dia; vermelho vira alerta no sino.

Um oráculo compara o que a tela MOSTRA com o que o banco TEM. Existiam 59, rodados à mão —
o que significa que só denunciavam divergência quando alguém lembrava. Em 11/08/2026, sete
estavam vermelhos e ninguém sabia; nenhum era defeito de produto: eram testes presos a
e-mail de gente que saiu, a tools renomeadas e a telas que mudaram de forma de propósito.
Teste que ninguém roda apodrece em silêncio e depois se confunde com bug.

**Roda no container do BACKEND, por cron do host — não em worker Celery.** A primeira versão
era uma tarefa Celery na fila `gov.batch`, e foi errada duas vezes:
  • os limites da fila (300s/600s) matavam a varredura de ~15min a SIGKILL, e morte por
    sinal não dispara `task_failure` — a tarefa feita para quebrar o silêncio morria calada;
  • medido depois: um oráculo tem pico de **894 MB** (importa o app inteiro) e todo worker
    tem limite de 2 GB com 1,39 GB já em uso. A varredura derrubaria por OOM o worker que
    cuida de gov, financeiro e integrações — de madrugada, toda noite.
O backend tem 6 GB com ~2 GB livres e é onde os 59 sempre foram rodados à mão.

Verde = silêncio absoluto. O sino só toca quando há o que fazer; sino que toca todo dia é
sino que ninguém escuta. A dedução por dia é a mesma de `task_falha` — índice único parcial
em (user_id, extra_data->>'idempotency_key') decide no banco, não na aplicação.

Subprocess por oráculo, não import: cada um é um script com `asyncio.run(main())` e
`SystemExit`, e alguns mexem no registry global de tools — no mesmo processo um contaminaria
o outro. É também exatamente como são invocados à mão.

Uso (o cron do host chama assim):
    docker exec -e PYTHONPATH=/app conecta-pro-backend \\
        python3 /app/modules/notifications/tasks_oraculos.py --varrer
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_DIR = Path(os.getenv("ORQ_DIR", "/app/scripts/orq"))

#: Teto por oráculo. O mais lento (RBAC, 8 sub-oráculos) leva ~1min; 5 é folga com margem.
_TIMEOUT_ORACULO_S = 300

#: Teto do lote. Medido em 06/09/2026: 143 arquivos em 2.714s — o teto de 45min foi batido
#: e 18 oráculos ficaram "não rodados" sem ninguém decidir isso. Roda à 00:00 sem ninguém
#: usando o sistema; 90 é folga. Os mais lentos saem nomeados no log (ver `lentos`).
_TIMEOUT_LOTE_S = 90 * 60

#: Exit code que um oráculo usa para dizer "não deu para medir hoje" — provedor de LLM sem
#: saldo, pré-condição de dado ausente. Nem verde nem vermelho; vai para o resumo como
#: BLOQUEADO. Definido em `scripts/orq/_fixtures.bloqueado`.
_EXIT_BLOQUEADO = 3

#: Motivo que parece INFRA (conexão caiu, container recriado no meio) e merece segunda
#: chance. Assert que falhou não merece: rodar de novo só dobra o tempo do lote.
_INFRA = ("connection", "connect", "refused", "operationalerror", "não terminou",
          "timeout", "timed out", "reset by peer", "eof")


def _oraculos() -> list[Path]:
    # Só `test_*.py`. A pasta também guarda importadores e semeadores (`importar_*`,
    # `carregar_*`, `semear_*`) que exigem argumento e saíam como VERMELHO todo dia com
    # "uso: arquivo.xlsx" — três dos treze vermelhos de 06/09/2026 eram isso.
    return sorted(_DIR.glob("test_*.py"))


def varrer() -> dict:
    """Roda todos os oráculos em sequência. Devolve o resumo — nunca levanta."""
    arquivos = _oraculos()
    if not arquivos:
        return {"total": 0, "verdes": 0, "vermelhos": 0, "nao_rodados": 0,
                "falhas": [{"oraculo": str(_DIR), "motivo": "nenhum oráculo encontrado — "
                                                            "a varredura virou casca"}]}

    env = {**os.environ, "PYTHONPATH": "/app"}
    limite = time.monotonic() + _TIMEOUT_LOTE_S
    verdes: list[str] = []
    vermelhos: list[tuple[str, str]] = []
    bloqueados: list[tuple[str, str]] = []
    duracao: dict[str, int] = {}

    for arq in arquivos:
        if time.monotonic() > limite:
            continue  # a sobra vira "não rodado" abaixo — lote estourado não é sucesso parcial
        t0 = time.monotonic()
        estado, motivo = _rodar(arq, env)
        if estado == "vermelho" and any(x in motivo.lower() for x in _INFRA):
            # Segunda chance SÓ para cara de infra. Duas varreduras manuais de 11/08 vieram
            # com 38 e 17 "falhas" que eram outra sessão recriando o container no meio — a
            # conexão morre e tudo dali em diante estoura junto. Assert que falhou não ganha
            # segunda chance: repetir só dobrava o tempo do lote (13 vermelhos × 2 em 06/09).
            time.sleep(5)
            estado, motivo = _rodar(arq, env)
        duracao[arq.name] = int(time.monotonic() - t0)
        if estado == "ok":
            verdes.append(arq.name)
        elif estado == "bloqueado":
            bloqueados.append((arq.name, motivo))
        else:
            vermelhos.append((arq.name, motivo))

    feitos = set(verdes) | {n for n, _ in vermelhos} | {n for n, _ in bloqueados}
    nao_rodados = [a.name for a in arquivos if a.name not in feitos]
    lentos = sorted(duracao.items(), key=lambda kv: -kv[1])[:5]
    return {"total": len(arquivos), "verdes": len(verdes), "vermelhos": len(vermelhos),
            "nao_rodados": len(nao_rodados), "nomes_nao_rodados": nao_rodados,
            "falhas": [{"oraculo": n, "motivo": m} for n, m in vermelhos],
            "bloqueados": [{"oraculo": n, "motivo": m} for n, m in bloqueados],
            "lentos": [{"oraculo": n, "s": d} for n, d in lentos],
            "duracao_total_s": sum(duracao.values())}


def _rodar(arq: Path, env: dict) -> tuple[str, str]:
    """Roda um oráculo. Devolve (estado, motivo), estado ∈ ok·vermelho·bloqueado — nunca levanta."""
    try:
        r = subprocess.run([sys.executable, str(arq)], env=env, capture_output=True,
                           text=True, timeout=_TIMEOUT_ORACULO_S)
        saida = (r.stdout or "") + (r.stderr or "")
        if r.returncode == 0:
            return "ok", ""
        if r.returncode == _EXIT_BLOQUEADO:
            return "bloqueado", _motivo(saida, marca="BLOQUEADO")
        return "vermelho", _motivo(saida)
    except subprocess.TimeoutExpired:
        return "vermelho", f"não terminou em {_TIMEOUT_ORACULO_S}s"
    except Exception as exc:  # noqa: BLE001 — um oráculo quebrado não derruba a varredura
        return "vermelho", f"{type(exc).__name__}: {exc}"


def _motivo(saida: str, marca: str | None = None) -> str:
    """Última linha útil da saída — quase sempre a mensagem do assert."""
    linhas = [ln.strip() for ln in saida.splitlines() if ln.strip()]
    for ln in reversed(linhas):
        if marca and ln.startswith(marca):
            return ln[len(marca):].lstrip(": ")[:160]
        if not marca and ("Error" in ln or "assert" in ln.lower() or "FAIL" in ln):
            return ln[:160]
    return (linhas[-1][:160] if linhas else "sem saída")


def mensagem(resumo: dict) -> str:
    """Corpo do alerta no sino — cabe pouco, então diz o essencial.

    Contagem primeiro (que sempre cabe), depois os nomes, e o aviso explícito de quantos
    ficaram de fora do texto: um corte silencioso aqui esconderia justamente o oráculo que
    ninguém viu.
    """
    vermelhos = resumo["falhas"]
    partes = [f"{len(vermelhos)} de {resumo['total']} oráculos vermelhos."]
    if resumo["nao_rodados"]:
        partes.append(f"{resumo['nao_rodados']} não rodaram (lote estourou o tempo).")
    mostrados = vermelhos[:6]
    partes += [f"{f['oraculo'].removeprefix('test_').removesuffix('.py')}: {f['motivo']}"
               for f in mostrados]
    if len(vermelhos) > len(mostrados):
        partes.append(f"(+{len(vermelhos) - len(mostrados)} não listados — ver o log da varredura)")
    bloqueados = resumo.get("bloqueados") or []
    if bloqueados:
        # Bloqueado não é defeito, mas também não é silêncio: "não deu para medir" dito em
        # voz alta é o que separa NÃO VERIFICADO de verde por omissão.
        partes.append(f"{len(bloqueados)} BLOQUEADO(s) (não deu para medir): " + "; ".join(
            f"{b['oraculo'].removeprefix('test_').removesuffix('.py')}: {b['motivo'][:80]}"
            for b in bloqueados[:3]))
    return " ".join(partes)


def publicar_no_sino(resumo: dict, anterior: dict | None = None) -> int:
    """Grava o alerta para cada admin ativo. Devolve quantos receberam.

    Reusa a mecânica de `task_falha`: mesma tabela, mesmos destinatários (conta de serviço
    fora — robô recebendo alerta é ruído que treina gente a ignorar o sino) e a mesma chave
    de idempotência, que deixa a deduplicação atômica no banco.
    """
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from sqlalchemy import text

    from core.database.session import SyncSessionLocal
    from modules.notifications.task_falha import _SQL_DESTINATARIOS, _SQL_SINO

    dia = datetime.now(ZoneInfo("America/Manaus")).strftime("%Y-%m-%d")
    corpo = (
        f"{mensagem(resumo)}\n\n"
        f"{comparar(resumo, anterior)}\n\n"
        f"Um oráculo compara o que a tela mostra com o que o banco tem. Vermelho é "
        f"divergência — ou defeito de produto, ou o próprio oráculo preso a uma versão "
        f"antiga da tela. Rodar à mão para ver o detalhe:\n"
        f"docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/<arquivo>"
    )
    extra = json.dumps({
        "idempotency_key": f"oraculos_diarios:{dia}",
        "origem": "oraculos_diarios", "familia": "sistema", "severidade": "critico",
        "vermelhos": resumo["vermelhos"], "nao_rodados": resumo["nao_rodados"],
    })
    n = resumo["vermelhos"]
    titulo = (f"{n} oráculo vermelho" if n == 1 else f"{n} oráculos vermelhos") if n else \
        f"{resumo['nao_rodados']} oráculos não rodaram"
    with SyncSessionLocal() as db:
        destinatarios = [r[0] for r in db.execute(text(_SQL_DESTINATARIOS)).fetchall()]
        for uid in destinatarios:
            db.execute(text(_SQL_SINO), {"uid": uid, "title": titulo, "body": corpo,
                                         "extra": extra})
        db.commit()
    return len(destinatarios)


#: Onde fica o "rodou". `system_configs` já existe para isto (chave única, todo o resto com
#: default) e estava vazia — nenhuma migração, nenhuma tabela nova.
_CHAVE_BATIDA = "oraculos.ultima_varredura"

_SQL_BATER = """
    INSERT INTO system_configs (id, chave, valor, descricao, grupo)
    VALUES (gen_random_uuid(), :chave, :valor,
            'Instante da última varredura dos oráculos (vigiado por orq.checar_varredura_ausente)',
            'oraculos')
    ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor, updated_at = NOW()
"""


def bater_ponto(resumo: dict) -> None:
    """Registra que a varredura ACONTECEU — verde ou vermelha, tanto faz.

    Sem isto, silêncio no sino significa duas coisas opostas: "tudo verde" e "o cron nunca
    rodou". É a mesma ambiguidade que deixou os 59 oráculos apodrecerem sem ninguém notar.
    A batida é o que permite alguém perguntar "quando foi a última vez?" e ter resposta.
    """
    import json
    from datetime import UTC, datetime

    from sqlalchemy import text

    from core.database.session import SyncSessionLocal

    valor = json.dumps({
        "em": datetime.now(UTC).isoformat(timespec="seconds"),
        "total": resumo["total"], "verdes": resumo["verdes"],
        "vermelhos": resumo["vermelhos"], "nao_rodados": resumo["nao_rodados"],
        # Os NOMES, não só a contagem: sem eles não dá para dizer se o vermelho de hoje é o
        # mesmo de ontem (ninguém mexeu) ou outro (consertaram um e quebraram outro).
        "falharam": sorted(f["oraculo"] for f in resumo["falhas"]),
        "bloqueados": sorted(b["oraculo"] for b in resumo.get("bloqueados") or []),
        "lentos": resumo.get("lentos") or [],
        "duracao_total_s": resumo.get("duracao_total_s", 0),
    })
    with SyncSessionLocal() as db:
        db.execute(text(_SQL_BATER), {"chave": _CHAVE_BATIDA, "valor": valor})
        db.commit()


def rodada_anterior() -> dict | None:
    """Resumo da última varredura, para comparar. None se não houver."""
    import json as _json

    from sqlalchemy import text

    from core.database.session import SyncSessionLocal

    with SyncSessionLocal() as db:
        bruto = db.execute(text("SELECT valor FROM system_configs WHERE chave = :c"),
                           {"c": _CHAVE_BATIDA}).scalar()
    if not bruto:
        return None
    try:
        return _json.loads(bruto)
    except Exception:  # noqa: BLE001 — batida ilegível é o mesmo que não ter
        return None


def mudou(resumo: dict, antes: dict | None) -> bool:
    """Houve notícia desde a rodada anterior? (novo, resolvido, bloqueio mudou, não-rodado mudou)

    É o que decide se o sino toca. O mesmo vermelho repetido não é notícia: em 30 dias o sino
    recebeu 5.387 avisos e o dono abriu 19 (medido em 06/09/2026) — um a mais por dia com o
    mesmo conteúdo só afunda o que importa. Segunda-feira o vermelho parado volta a tocar.
    """
    if antes is None:
        return True
    agora = {f["oraculo"] for f in resumo["falhas"]}
    bloq = {b["oraculo"] for b in resumo.get("bloqueados") or []}
    return (agora != set(antes.get("falharam") or [])
            or bloq != set(antes.get("bloqueados") or [])
            or resumo.get("nao_rodados", 0) != antes.get("nao_rodados", 0))


def comparar(resumo: dict, antes: dict | None) -> str:
    """Uma linha dizendo se a rodada ANDOU — resolvido, novo, ou parado.

    Alarme que só repete "9 vermelhos" todo dia vira ruído e ensina a ignorar. O que muda o
    comportamento de quem lê é saber se alguém está consertando.
    """
    agora = {f["oraculo"] for f in resumo["falhas"]}
    if antes is None:
        return f"primeira rodada registrada ({len(agora)} vermelho(s))."
    ontem = set(antes.get("falharam") or [])
    resolvidos, novos, teimosos = ontem - agora, agora - ontem, agora & ontem
    bloq_antes = set(antes.get("bloqueados") or [])
    bloq_agora = {b["oraculo"] for b in resumo.get("bloqueados") or []}
    if not agora and ontem:
        return f"RESOLVIDO: os {len(ontem)} vermelho(s) da rodada anterior sumiram."
    partes = []
    if bloq_agora - bloq_antes:
        partes.append(f"{len(bloq_agora - bloq_antes)} passou a BLOQUEADO")
    if bloq_antes - bloq_agora:
        partes.append(f"{len(bloq_antes - bloq_agora)} desbloqueado(s)")
    if resolvidos:
        partes.append(f"{len(resolvidos)} resolvido(s)")
    if novos:
        partes.append(f"{len(novos)} NOVO(s): {', '.join(sorted(novos)[:3])}")
    if teimosos:
        partes.append(f"{len(teimosos)} sem mexer desde a rodada anterior")
    return ("Comparado à rodada anterior: " + "; ".join(partes) + ".") if partes else \
        "Nada mudou desde a rodada anterior."


def _self_check() -> None:
    """Sem banco: a mensagem tem que caber no sino e nunca esconder corte."""
    falso = {"total": 59, "vermelhos": 9, "nao_rodados": 1, "nomes_nao_rodados": ["test_y.py"],
             "verdes": 49, "falhas": [{"oraculo": f"test_x{i}.py", "motivo": "AssertionError: algo"}
                                      for i in range(9)]}
    msg = mensagem(falso)
    assert msg.startswith("9 de 59 oráculos vermelhos."), msg
    assert "não rodaram" in msg and "+3 não listados" in msg, msg
    assert _motivo("linha 1\nAssertionError: tela vazia\n") == "AssertionError: tela vazia"
    assert _motivo("") == "sem saída"
    assert _motivo("x\nBLOQUEADO: LLM sem saldo\n", marca="BLOQUEADO") == "LLM sem saldo"
    bloq = {"total": 59, "vermelhos": 0, "nao_rodados": 0, "verdes": 58, "falhas": [],
            "bloqueados": [{"oraculo": "test_papel_fornecedor.py", "motivo": "LLM sem saldo"}]}
    assert "1 BLOQUEADO(s)" in mensagem(bloq) and "papel_fornecedor: LLM sem saldo" in mensagem(bloq)
    assert "passou a BLOQUEADO" in comparar(bloq, {"falharam": [], "bloqueados": []})
    assert "desbloqueado" in comparar({"falhas": [], "bloqueados": []},
                                      {"falharam": [], "bloqueados": ["a"]})
    limpo = {"total": 59, "vermelhos": 0, "nao_rodados": 0, "verdes": 59, "falhas": []}
    assert mensagem(limpo) == "0 de 59 oráculos vermelhos."

    # A comparação entre rodadas é o que separa alarme de ruído.
    f = lambda ns: {"falhas": [{"oraculo": n, "motivo": ""} for n in ns]}  # noqa: E731
    assert "primeira rodada" in comparar(f(["a"]), None)
    assert "RESOLVIDO" in comparar(f([]), {"falharam": ["a", "b"]})
    assert "2 resolvido" in comparar(f(["c"]), {"falharam": ["a", "b", "c"]})
    assert "1 NOVO" in comparar(f(["a", "z"]), {"falharam": ["a"]})
    assert "sem mexer" in comparar(f(["a"]), {"falharam": ["a"]})
    assert comparar(f([]), {"falharam": []}) == "Nada mudou desde a rodada anterior."
    assert mudou(f(["a"]), None) and not mudou({"falhas": [{"oraculo": "a"}], "bloqueados": [], "nao_rodados": 0},
                                            {"falharam": ["a"], "bloqueados": [], "nao_rodados": 0})
    assert mudou({"falhas": [{"oraculo": "a"}], "bloqueados": [], "nao_rodados": 2},
                 {"falharam": ["a"], "bloqueados": [], "nao_rodados": 0})
    print("self-check OK\n" + msg)


def avisar(titulo: str, corpo: str, chave: str = "trava_qa") -> int:
    """Publica um aviso avulso no sino, com a mesma dedução por dia da varredura.

    Existe para as travas mecânicas: elas rodam no HOST (precisam do repositório e do
    crontab) e não têm banco. Sem esta porta, regressão de fabricação virava linha em
    /var/log esperando alguém abrir — check que ninguém escuta é o mesmo que não ter check.
    """
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from sqlalchemy import text

    from core.database.session import SyncSessionLocal
    from modules.notifications.task_falha import _SQL_DESTINATARIOS, _SQL_SINO

    dia = datetime.now(ZoneInfo("America/Manaus")).strftime("%Y-%m-%d")
    extra = json.dumps({"idempotency_key": f"{chave}:{dia}", "origem": chave,
                        "familia": "sistema", "severidade": "critico"})
    with SyncSessionLocal() as db:
        destinatarios = [r[0] for r in db.execute(text(_SQL_DESTINATARIOS)).fetchall()]
        for uid in destinatarios:
            db.execute(text(_SQL_SINO), {"uid": uid, "title": titulo[:100],
                                         "body": corpo[:500], "extra": extra})
        db.commit()
    return len(destinatarios)


if __name__ == "__main__":
    if "--avisar" in sys.argv:
        i = sys.argv.index("--avisar")
        n = avisar(sys.argv[i + 1], sys.argv[i + 2] if len(sys.argv) > i + 2 else "")
        print(f"aviso publicado para {n} destinatário(s)")
        raise SystemExit(0)
    if "--varrer" not in sys.argv:
        _self_check()
        raise SystemExit(0)

    inicio = time.time()
    resumo = varrer()
    dur = int(time.time() - inicio)
    print(f"[oraculos] {resumo['verdes']} verdes, {resumo['vermelhos']} vermelhos, "
          f"{len(resumo['bloqueados'])} bloqueados, {resumo['nao_rodados']} não rodados em {dur}s")
    for f in resumo["falhas"]:
        print(f"  x {f['oraculo']} — {f['motivo']}")
    for b in resumo["bloqueados"]:
        print(f"  ? {b['oraculo']} — BLOQUEADO: {b['motivo']}")
    for n in resumo["nomes_nao_rodados"]:
        print(f"  - {n} — não rodou (lote estourou o teto)")
    print("  mais lentos: " + ", ".join(f"{l['oraculo']} {l['s']}s" for l in resumo["lentos"]))
    try:
        # A linha do DELTA vai para o log de propósito: é a que muda quando alguém mexe, e é
        # a que um canal humano (sino, ou o que vier) deve mostrar primeiro.
        print("[oraculos] " + comparar(resumo, rodada_anterior()))
    except Exception as exc:  # noqa: BLE001
        print(f"[oraculos] sem comparação com a rodada anterior: {type(exc).__name__}: {exc}")

    _ANTERIOR = None
    try:
        _ANTERIOR = rodada_anterior()  # ANTES de bater ponto, senão compara consigo mesma
    except Exception:  # noqa: BLE001
        pass
    try:
        bater_ponto(resumo)  # antes do sino: "rodou" vale mesmo quando não há o que avisar
    except Exception as exc:  # noqa: BLE001 — não perder a varredura por causa da batida
        print(f"[oraculos] NÃO consegui bater ponto: {type(exc).__name__}: {exc}")

    from datetime import date as _date
    ha_problema = bool(resumo["falhas"] or resumo["nao_rodados"])
    segunda = _date.today().isoweekday() == 1
    if not mudou(resumo, _ANTERIOR) and not (segunda and ha_problema):
        # Nada novo desde ontem: silêncio no sino (o log tem tudo). Vermelho parado volta a
        # tocar toda segunda — para não sumir de vista, sem tocar todo dia.
        print("[oraculos] sem novidade desde a rodada anterior — sino em silêncio")
        raise SystemExit(1 if ha_problema else 0)
    if not ha_problema and not resumo["bloqueados"]:
        raise SystemExit(0)  # verde de verdade
    try:
        n = publicar_no_sino(resumo, _ANTERIOR)
        print(f"[oraculos] alerta publicado no sino para {n} destinatário(s)")
    except Exception as exc:  # noqa: BLE001 — falhar ao avisar não pode esconder a varredura
        print(f"[oraculos] NÃO consegui publicar no sino: {type(exc).__name__}: {exc}")
    raise SystemExit(1)
