"""Oráculo — o ponto do Conecta PRO é um REP-P de verdade (Portaria MTP 671/2021)? (12/09/2026)

Por que existe: 52 pessoas batem ponto todo dia num programa que não é um REP-P constituído.
`hr/rep_integration` existia no disco com zero rotas e `afd_records` com zero linhas; AEJ, INPI e
atestado técnico não existiam no repositório. Isso não é feature faltando — é exposição.

Cinco afirmações, nenhuma delas cópia da tabela que vigia:

  (a) as rotas do AFD e do AEJ estão em `app.routes` — montadas sob /people-management/ponto/afd.
  (b) toda batida >= CORTE (13/09/2026 00:00 Manaus) de empregado com CPF tem linha AFD (tipo 7).
      O AFD começa no corte e vai para frente; o histórico anterior fica intocado de propósito.
  (c) o NSR é contínuo (1..N sem lacuna) e único por dispositivo, e a corrente de hash SHA-256
      dos tipo 7 fecha (cada hash cobre os campos 1-7 + o hash anterior).
  (d) o AEJ da competência corrente reabre (cada tipo tem o nº de campos do Anexo VI), o trailer
      confere e a contagem de marcações (tipo 05) casa com gp_clock_punches da mesma competência
      para empregados com CPF.
  (e) existe registro do instrumento legal com data: INPI (número + data), atestado técnico
      (emissor + data + validade vigente) e termo de responsabilidade. Ausência é VERMELHO — e fica
      vermelho até o Jordan preencher `rep_instrumento_legal`: é decisão jurídica dele.

Estado medido no nascimento (12/09/2026, staging com REP_P_CORTE=2026-09-01 para ter dado):
(a) 0 rotas 'afd'; (b) 1.112 batidas sem AFD em 11 dias; (c) nenhum dispositivo; (d) módulo rep_p
não existe; (e) tabela vazia. Vermelho nas cinco.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

#: nº de campos por tipo de registro do AEJ (Anexo VI, versão 002)
CAMPOS_AEJ = {"01": 10, "02": 4, "03": 4, "04": 7, "05": 9, "06": 3, "07": 6, "08": 7, "99": 9}


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db

    falhas: list[str] = []
    hoje = datetime.now(ZoneInfo("America/Manaus"))

    # (a) rotas montadas
    try:
        from main_production import app

        rotas = [r.path for r in app.routes if "/afd" in r.path]
    except Exception as exc:  # noqa: BLE001
        rotas = []
        falhas.append(f"(a) não consegui carregar main_production: {exc}")
    for precisa in ("/ponto/afd/records", "/ponto/afd/rep-p/aej", "/ponto/afd/rep-p/arquivo"):
        if not any(r.endswith(precisa) for r in rotas):
            falhas.append(f"(a) rota {precisa} não está em app.routes — o AFD/AEJ não é alcançável")

    try:
        from modules.hr.rep_integration.services import rep_p
    except Exception as exc:  # noqa: BLE001
        rep_p = None
        falhas.append(f"(b/d) módulo rep_p não importa: {exc}")
    # sem o módulo, a mesma régua dele: o corte real, ou REP_P_CORTE (só para medir no staging)
    corte = rep_p.CORTE if rep_p else datetime.fromisoformat(os.environ.get("REP_P_CORTE", "2026-09-13T00:00:00"))

    gen = get_db()
    db = await gen.__anext__()

    # (b) batida >= corte sem linha AFD
    # ⚠️ 18/09/2026 — `pendente_de_conferencia` FORA, como em `rep_p.gerar_afd_pendentes`.
    # A batida offline que ainda não passou na reconferência do rosto não entra no AFD DE
    # PROPÓSITO (frente 02, 13/09): o AFD é memória inalterável, e escrever nele um fato que
    # o DP ainda pode recusar é afirmar integridade sobre o que não está confirmado — o NSR
    # não volta atrás. O oráculo copiou o WHERE sem essa linha e acusou a batida da GRACIENE
    # de 14/09 como lacuna legal. Era a regra funcionando.
    faltam = (
        await db.execute(
            text("""
        SELECT p.punch_timestamp::date d, count(*) FROM gp_clock_punches p
        JOIN employees e ON e.id = p.employee_id
        LEFT JOIN afd_records a ON a.punch_id = p.punch_id
        WHERE p.punch_timestamp >= :c AND a.id IS NULL
          AND p.status <> 'pendente_de_conferencia'
          AND length(regexp_replace(coalesce(e.cpf,''),'\\D','','g')) = 11
        GROUP BY 1 ORDER BY 1"""),
            {"c": corte},
        )
    ).all()

    # …e a garantia no sentido inverso, que faltava: pendente NÃO PODE ter linha AFD. Sem
    # esta, bastaria alguém afrouxar o filtro do gerador para o AFD passar a carregar batida
    # que ainda pode ser recusada, e nada acusaria.
    indevidas = (
        await db.execute(
            text("""
        SELECT count(*) FROM gp_clock_punches p
        JOIN afd_records a ON a.punch_id = p.punch_id
        WHERE p.status = 'pendente_de_conferencia'""")
        )
    ).scalar()
    if indevidas:
        falhas.append(
            f"(b) {indevidas} batida(s) `pendente_de_conferencia` COM linha AFD — o AFD "
            "recebeu marcação que o DP ainda pode recusar, e o NSR não volta atrás"
        )
    desde_corte = (
        await db.execute(text("SELECT count(*) FROM gp_clock_punches WHERE punch_timestamp >= :c"), {"c": corte})
    ).scalar()
    for d, n in faltam:
        falhas.append(f"(b) {d:%d/%m}: {n} batida(s) sem linha AFD")
    if not desde_corte:
        print(f"(b) ainda não há batida desde o corte {corte:%d/%m/%Y} — sem dado, não é verde")

    # (c) NSR contínuo e único por dispositivo + corrente de hash
    devs = (
        await db.execute(
            text("""
        SELECT d.serial_number, count(*), min(a.nsr), max(a.nsr), count(DISTINCT a.nsr)
        FROM afd_records a JOIN rep_devices d ON d.id = a.device_id GROUP BY 1 ORDER BY 1""")
        )
    ).all()
    if not devs and desde_corte:
        falhas.append("(c) nenhuma linha AFD em nenhum dispositivo")
    for serial, n, lo, hi, dist in devs:
        if lo != 1 or n != dist or hi - lo + 1 != n:
            falhas.append(f"(c) {serial}: NSR {lo}..{hi}, {n} linhas, {dist} distintos — há lacuna ou repetição")
        linhas = (
            await db.execute(
                text("""
            SELECT a.afd_line, a.record_type FROM afd_records a JOIN rep_devices d ON d.id = a.device_id
            WHERE d.serial_number = :s ORDER BY a.nsr"""),
                {"s": serial},
            )
        ).all()
        ant = None
        for linha, tipo in linhas:
            if tipo != "7":
                continue
            base, h = linha[:73], linha[73:]
            if hashlib.sha256((base + (ant or "")).encode("latin-1")).hexdigest() != h:
                falhas.append(f"(c) {serial}: corrente de hash quebra no NSR {linha[:9]}")
                break
            ant = h

    # (d) AEJ reabre e casa com as batidas da competência
    if rep_p:
        emps = (
            (
                await db.execute(
                    text(
                        "SELECT DISTINCT regexp_replace(em.cnpj,'\\D','','g') FROM empresas em "
                        "JOIN employees e ON e.empresa_id = em.id JOIN gp_clock_punches p ON p.employee_id = e.id "
                        "WHERE p.punch_timestamp >= :i"
                    ),
                    {"i": datetime(hoje.year, hoje.month, 1)},
                )
            )
            .scalars()
            .all()
        )
        if not emps:
            falhas.append("(d) nenhum empregador com batida na competência — não dá para montar AEJ")
        for cnpj in emps:
            try:
                nome, txt, qt = await rep_p.montar_aej(db, cnpj, hoje.year, hoje.month)
            except Exception as exc:  # noqa: BLE001
                falhas.append(f"(d) AEJ de {cnpj} não monta: {exc}")
                continue
            linhas = [l for l in txt.split("\r\n") if l]
            cont: dict[str, int] = {}
            for l in linhas[:-1]:
                t = l[:2]
                cont[t] = cont.get(t, 0) + 1
                if t not in CAMPOS_AEJ or len(l.split("|")) != CAMPOS_AEJ[t]:
                    falhas.append(f"(d) AEJ {cnpj}: linha não reabre no leiaute: {l[:60]}")
                    break
            trailer = linhas[-2].split("|")
            esperado = ["99"] + [str(cont.get(t, 0)) for t in ("01", "02", "03", "04", "05", "06", "07", "08")]
            if trailer != esperado:
                falhas.append(f"(d) AEJ {cnpj}: trailer {trailer} ≠ contagem real {esperado}")
            n_banco = (
                await db.execute(
                    text("""
                SELECT count(*) FROM gp_clock_punches p JOIN employees e ON e.id = p.employee_id
                JOIN empresas em ON em.id = e.empresa_id
                WHERE regexp_replace(em.cnpj,'\\D','','g') = :c AND p.punch_timestamp >= :i
                  AND length(regexp_replace(coalesce(e.cpf,''),'\\D','','g')) = 11"""),
                    {"c": cnpj, "i": datetime(hoje.year, hoje.month, 1)},
                )
            ).scalar()
            if cont.get("05", 0) != n_banco:
                falhas.append(f"(d) AEJ {cnpj}: {cont.get('05', 0)} marcações no arquivo, {n_banco} no banco")
            print(
                f"AEJ {nome}: {cont.get('05', 0)} marcações · {cont.get('03', 0)} vínculos · "
                f"{cont.get('02', 0)} REP · {cont.get('04', 0)} horários"
            )

    # (e) instrumento legal
    try:
        inst = (
            await db.execute(text("SELECT tipo, numero, emissor, data_emissao, validade FROM rep_instrumento_legal"))
        ).all()
    except Exception as exc:  # noqa: BLE001
        inst = []
        falhas.append(f"(e) tabela rep_instrumento_legal não existe: {str(exc)[:80]}")
    por_tipo = {r[0]: r for r in inst}
    inpi = por_tipo.get("INPI")
    if not inpi or not inpi[1] or not inpi[3]:
        falhas.append("(e) sem registro do programa no INPI (número + data) — precondição legal do REP-P")
    at = por_tipo.get("ATESTADO_TECNICO")
    if not at or not at[2] or not at[3] or not at[4] or at[4] < date.today():
        falhas.append("(e) sem atestado técnico vigente (emissor + data + validade) — art. 89 da Portaria 671")
    if not por_tipo.get("TERMO_RESPONSABILIDADE") or not por_tipo["TERMO_RESPONSABILIDADE"][3]:
        falhas.append("(e) sem termo de responsabilidade com data")

    print(
        f"rotas afd: {len(rotas)} · corte {corte:%d/%m/%Y} · batidas desde o corte: {desde_corte} · "
        f"dias com batida sem AFD: {len(faltam)} · dispositivos: {len(devs)} · instrumentos: {len(inst)}"
    )
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) no REP-P")
    print(
        "OK REP-P: rotas montadas, toda batida desde o corte tem AFD, NSR contínuo com hash fechado, "
        "AEJ reabre e casa com o banco, instrumento legal registrado"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
