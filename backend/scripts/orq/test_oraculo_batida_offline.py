"""Oráculo — batida OFFLINE é reconferida pelo servidor, não vale a palavra do aparelho (13/09/2026).

Frente 2 do plano de paridade com a DigiExpress/DGX. A DGX publicou no Cronos 3.61.9
"reconhecimento facial offline automático em caso de instabilidade na conexão online". Copiar isso
sem trava é abrir a porta que o pré-mortem descreve: *"se o descriptor for comparado no aparelho e
a batida aceita sem servidor, quem controla o aparelho controla a batida"*.

Cinco afirmações. Nenhuma é a fotografia do conserto — cada uma é a REGRA:

  (a) A rota de sincronização existe e está montada em `app.routes`. Sem ela a fila do aparelho
      sobe pela rota antiga `/ponto/sync`, que grava sem reconferir nada.
  (b) Toda batida `is_offline=true` tem `chave_idempotente`, e não há DUAS batidas da mesma pessoa,
      mesmo aparelho e mesmo tipo dentro da janela de 20 min. A régua dos 20 min é a mesma do
      importador do Tangerino — o mecanismo que produziu 1.375 jornadas duplicadas em 11/09.
  (c) As DUAS horas são gravadas (aparelho em `punch_timestamp`, servidor em `server_timestamp`) e
      a diferença fica em `divergencia_relogio_seg`. Relógio de celular é editável; a defesa não é
      recusar a batida, é ter o número.
  (d) Nenhuma batida offline virou DEFINITIVA sem `facial_match` reconferido no servidor. Batida
      que não passou fica `pendente_de_conferencia` — e (f) ela NÃO entra no AFD.
  (e) Um dia com >= 10 batidas offline e 100% de sucesso facial é VERMELHO. Taxa perfeita não é
      qualidade: é o sinal de que a comparação não está ocorrendo. É o inverso da armadilha do
      `SEM_ROSTO_MAX = 40`, onde a falha simplesmente não saía do aparelho.
  (f) Nenhuma linha do AFD aponta para batida `pendente_de_conferencia`. O AFD é memória
      inalterável de marcação: registrar lá uma batida que ainda pode ser recusada é afirmar
      integridade sobre um fato não confirmado.

ESTADO MEDIDO NO NASCIMENTO (staging, 13/09/2026, antes de qualquer linha de implementação):
  rota /ponto/offline/sync em app.routes: NÃO · coluna chave_idempotente: NÃO EXISTE ·
  coluna divergencia_relogio_seg: NÃO EXISTE · batidas is_offline=true no banco: 0
  (as afirmações (b)–(f) não tinham como falhar por falta de dado — o vermelho nasceu em (a) e
  nas colunas. As 3 batidas de prova foram criadas pela API depois que a rota existiu.)

Roda no container com PYTHONPATH=/app. Sai 0 = verde; 1 = vermelho.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

#: Janela de idempotência, em minutos — a mesma régua do importador do Tangerino.
JANELA_MIN = 20
#: Piso de batidas offline no dia para a taxa de sucesso dizer alguma coisa. Abaixo disso,
#: 100% é acaso e acusar seria ruído.
MIN_BATIDAS_DIA = 10

#: Status da batida que ainda espera conferência do DP. NÃO é batida final e NÃO entra no AFD.
PENDENTE = "pendente_de_conferencia"

SQL_SEM_CHAVE = """
SELECT count(*) FROM gp_clock_punches WHERE is_offline AND coalesce(chave_idempotente,'') = ''
"""

#: Duplicata real: mesma pessoa, mesmo aparelho (chave carrega o device), mesmo tipo, dentro da
#: janela — mas com chave DIFERENTE. Chave igual não duplica (unique no banco); o que duplica é a
#: retentativa que gerou chave nova, que é exatamente o defeito do importador.
SQL_DUPLICATA = f"""
SELECT a.punch_id, b.punch_id, a.employee_id::text, a.punch_type,
       a.punch_timestamp, b.punch_timestamp
FROM gp_clock_punches a
JOIN gp_clock_punches b
  ON b.employee_id = a.employee_id AND b.punch_type = a.punch_type
 AND b.id > a.id
 AND b.punch_timestamp BETWEEN a.punch_timestamp AND a.punch_timestamp + interval '{JANELA_MIN} minutes'
WHERE a.is_offline AND b.is_offline
ORDER BY a.punch_timestamp
LIMIT 20
"""

SQL_SEM_AS_DUAS_HORAS = """
SELECT punch_id, punch_timestamp, server_timestamp, divergencia_relogio_seg
FROM gp_clock_punches
WHERE is_offline
  AND (punch_timestamp IS NULL OR server_timestamp IS NULL OR divergencia_relogio_seg IS NULL)
LIMIT 20
"""

#: Definitiva = qualquer status que não seja a espera do DP. Sem facial_match reconferido no
#: servidor, uma batida offline definitiva é a palavra do aparelho tomada como prova.
SQL_DEFINITIVA_SEM_MATCH = f"""
SELECT punch_id, status, facial_match, facial_confidence
FROM gp_clock_punches
WHERE is_offline AND status <> '{PENDENTE}' AND facial_match IS NOT TRUE
LIMIT 20
"""

SQL_TAXA_PERFEITA = f"""
SELECT punch_timestamp::date d, count(*) n,
       count(*) FILTER (WHERE facial_match) ok
FROM gp_clock_punches
WHERE is_offline
GROUP BY 1
HAVING count(*) >= {MIN_BATIDAS_DIA} AND count(*) = count(*) FILTER (WHERE facial_match)
ORDER BY 1
"""

SQL_AFD_DE_PENDENTE = f"""
SELECT a.nsr, a.punch_id, p.status
FROM afd_records a
JOIN gp_clock_punches p ON p.punch_id = a.punch_id
WHERE p.status = '{PENDENTE}'
LIMIT 20
"""

ROTAS_EXIGIDAS = [
    "/api/v1/people-management/ponto/offline/sync",
    "/api/v1/people-management/ponto/offline/config",
]


async def _coluna_existe(db, tabela: str, coluna: str) -> bool:
    return bool(
        (
            await db.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = :c"
                ),
                {"t": tabela, "c": coluna},
            )
        ).scalar()
    )


async def main() -> int:  # noqa: C901, PLR0912, PLR0915
    from core.database import get_db

    falhas: list[str] = []

    # (a) a rota existe e está montada — ler app.routes, não o arquivo no disco
    try:
        from main_production import app

        rotas = {getattr(r, "path", "") for r in app.routes}
    except Exception as exc:  # noqa: BLE001
        rotas = set()
        falhas.append(f"(a) main_production não importa: {exc}")
    for r in ROTAS_EXIGIDAS:
        if r not in rotas:
            falhas.append(f"(a) rota {r} não está em app.routes — a fila do aparelho não tem onde subir reconferida")

    gen = get_db()
    db = await gen.__anext__()
    try:
        # As colunas são a precondição de (b) e (c): sem elas a afirmação não é mensurável, e
        # "não mensurável" é vermelho, nunca verde por omissão.
        tem_chave = await _coluna_existe(db, "gp_clock_punches", "chave_idempotente")
        tem_diverg = await _coluna_existe(db, "gp_clock_punches", "divergencia_relogio_seg")
        if not tem_chave:
            falhas.append("(b) gp_clock_punches.chave_idempotente não existe — a retentativa do SW duplica")
        if not tem_diverg:
            falhas.append("(c) gp_clock_punches.divergencia_relogio_seg não existe — a hora do aparelho não é confrontada")

        total_off = (
            await db.execute(text("SELECT count(*) FROM gp_clock_punches WHERE is_offline"))
        ).scalar() or 0

        # (b) chave em toda batida offline
        sem_chave = 0
        if tem_chave:
            sem_chave = (await db.execute(text(SQL_SEM_CHAVE))).scalar() or 0
            if sem_chave:
                falhas.append(f"(b) {sem_chave} batida(s) offline sem chave_idempotente")

        # (b) nenhuma duplicata na janela
        dups = (await db.execute(text(SQL_DUPLICATA))).fetchall()
        for pa, pb, emp, tipo, ta, tb in dups:
            falhas.append(
                f"(b) duplicata offline: {emp} {tipo} {ta} e {tb} (punch {pa} / {pb}) "
                f"dentro de {JANELA_MIN} min"
            )

        # (c) as duas horas + a diferença
        if tem_diverg:
            sem_horas = (await db.execute(text(SQL_SEM_AS_DUAS_HORAS))).fetchall()
            for pid, ta, ts, dv in sem_horas:
                falhas.append(
                    f"(c) batida {pid} sem as duas horas gravadas (aparelho={ta} servidor={ts} diverg={dv})"
                )

        # (d) definitiva exige match reconferido no servidor
        sem_match = (await db.execute(text(SQL_DEFINITIVA_SEM_MATCH))).fetchall()
        for pid, st, m, c in sem_match:
            falhas.append(
                f"(d) batida offline {pid} está definitiva (status={st}) com facial_match={m} "
                f"conf={c} — ninguém reconferiu o rosto no servidor"
            )

        # (e) taxa perfeita é sinal de comparação que não ocorre
        perfeitos = (await db.execute(text(SQL_TAXA_PERFEITA))).fetchall()
        for d, n, ok in perfeitos:
            falhas.append(
                f"(e) {d}: {ok}/{n} batidas offline com facial_match=true — 100% em {n} batidas "
                f"significa que a comparação não está acontecendo, não que o rosto é perfeito"
            )

        # (f) o AFD não recebe batida que ainda espera conferência
        afd_pend = (await db.execute(text(SQL_AFD_DE_PENDENTE))).fetchall()
        for nsr, pid, st in afd_pend:
            falhas.append(
                f"(f) linha AFD NSR {nsr} aponta para batida {pid} em {st} — o AFD é memória "
                f"inalterável e essa batida ainda pode ser recusada pelo DP"
            )

        pend = 0
        if total_off:
            pend = (
                await db.execute(
                    text("SELECT count(*) FROM gp_clock_punches WHERE is_offline AND status = :s"),
                    {"s": PENDENTE},
                )
            ).scalar() or 0

        print(
            f"rotas offline montadas: {sum(1 for r in ROTAS_EXIGIDAS if r in rotas)}/{len(ROTAS_EXIGIDAS)} · "
            f"batidas offline: {total_off} (pendentes de conferência: {pend}) · "
            f"sem chave: {sem_chave} · duplicatas na janela de {JANELA_MIN}min: {len(dups)} · "
            f"dias com taxa facial 100%: {len(perfeitos)}"
        )
    finally:
        await gen.aclose()

    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) na batida offline")
    print(
        "OK batida offline: sobe por rota que reconfere, tem chave idempotente, grava as duas "
        "horas com a diferença, só vira definitiva com match do servidor e não entra no AFD enquanto pende"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
