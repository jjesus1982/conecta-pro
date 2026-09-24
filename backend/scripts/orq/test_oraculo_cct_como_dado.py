#!/usr/bin/env python3
"""CCT como DADO (DGX F2): Sindicato → Funções → Eventos/Benefícios por função → Municípios.

POR QUE EXISTE
  No DGX cada Função do sindicato carrega SEUS eventos (quais rubricas se aplicam, com razão) e
  SEUS benefícios. Aqui a SINDECOMPRESTS vivia em constantes Python (`calculo_service`,
  `modules/cct`). Este oráculo afirma que a árvore virou tabela E que a tabela não mente sobre
  a folha: o que a função diz que paga é o que o holerite paga — nos dois sentidos.

O QUE AFIRMA (recontado por SQL próprio, nunca pelo serviço)
  (a) toda função da CCT com funcionário ativo tem ≥1 evento e ≥1 benefício OBRIGATÓRIO;
  (b) CONTRA-PROVA contra o holerite VISÍVEL da competência-alvo (09/2026; se ainda não há
      holerite visível nessa competência, a mais recente visível antes dela — o oráculo diz qual):
      cada adicional do holerite (periculosidade/insalubridade/ronda/noturno) é evento da função
      do colaborador, com a MESMA razão quando o holerite a declara em «%»; e todo evento
      OBRIGATÓRIO da função está no holerite. Falha lista por nome;
  (c) piso da função (`cct_cargos.piso_salarial`) ≤ salário-base do holerite;
  (d) nenhuma linha semeada/criada sem `origem_regra` (de onde veio a regra).
  Evento OPCIONAL pago a parte da função (ex.: insalubridade em Serviços Gerais) é AVISO, não
  vermelho: é exatamente a discrepância CCT × folha que vai para o §7 do relatório com nomes.

DE-PARA DE CÓDIGOS (escrito aqui à mão, de propósito — se alguém mudar o código do holerite
ou da rubrica, o oráculo tem que DISCORDAR, não concordar automaticamente):
  holerite `calculo_service` → `rubricas_folha`: 0015→0051 (periculosidade), 0016→0050
  (insalubridade), 0018→0040 (ronda 15%), 0020→0020 (noturno). Só estes quatro: 0050/0051 no
  holerite significam AFASTAMENTO, e 0040 significa HORA EXTRA — colidem com a tabela de
  rubricas (registrado no relatório da frente; não é deste oráculo consertar).

ESTADO MEDIDO NO NASCIMENTO (sandbox, 24/09/2026): tabelas não existiam → vermelho.
  0 holerite visível em 09/2026 (51 em draft); alvo cai para 07/2026 (48 ativos publicados).

COMO RODA
  docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_cct_como_dado.py
  COMPETENCIA=2026-09 (opcional) força a competência-alvo.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402

VISIVEIS = "('published','rectified','contested','paid')"
HOLERITE_PARA_RUBRICA = {"0015": "0051", "0016": "0050", "0018": "0040", "0020": "0020"}
RUBRICA_PARA_HOLERITE = {v: k for k, v in HOLERITE_PARA_RUBRICA.items()}
NOME = {"0051": "periculosidade", "0050": "insalubridade", "0040": "ronda", "0020": "noturno"}
TABELAS = ("cct_sindicatos", "cct_funcao_eventos", "cct_funcao_beneficios", "cct_municipios")

ATIVO = (
    "lower(coalesce(e.status,''))='ativo' AND coalesce(e.is_homologacao,false)=false "
    "AND coalesce(e.tipo_contrato::text,'') NOT ILIKE '%pj%' "
    "AND upper(coalesce(e.nome,'')) NOT LIKE '%TESTE%' AND upper(coalesce(e.nome,'')) NOT LIKE '%HOMOLOGA%'"
)


async def main() -> int:  # noqa: C901, PLR0912, PLR0915
    falhas: list[str] = []
    avisos: list[str] = []
    async with async_session_factory() as db:
        faltam = [tb for tb in TABELAS if not (await db.execute(text("SELECT to_regclass(:t)"), {"t": tb})).scalar()]
        col = (
            await db.execute(
                text(
                    "SELECT 1 FROM information_schema.columns WHERE table_name='cct_convencoes' AND column_name='sindicato_id'"
                )
            )
        ).first()
        if faltam or not col:
            print(
                f"FALHOU: CCT ainda não é dado — faltam tabelas {faltam}"
                + ("" if col else " e a coluna cct_convencoes.sindicato_id")
            )
            print("TOTAL cct_como_dado: 1 vermelho")
            return 1

        conv = (
            await db.execute(
                text(
                    "SELECT c.id::text, c.sindicato_trabalhadores, s.nome, "
                    " (SELECT count(*) FROM cct_municipios m WHERE m.convencao_id=c.id) "
                    "FROM cct_convencoes c LEFT JOIN cct_sindicatos s ON s.id=c.sindicato_id "
                    "WHERE c.is_vigente AND c.is_active ORDER BY c.data_inicio DESC LIMIT 1"
                )
            )
        ).first()
        if not conv or not conv[2]:
            falhas.append("convenção vigente sem sindicato_id apontando para cct_sindicatos")
        elif not conv[3]:
            falhas.append(f"convenção vigente ({conv[1]}) sem nenhum município em cct_municipios")
        else:
            print(f"convenção vigente: {conv[1]} → sindicato «{conv[2]}» · municípios: {conv[3]}")

        # (d) origem_regra em TODA linha
        for tb in TABELAS:
            n = (
                await db.execute(
                    text(f"SELECT count(*) FROM {tb} WHERE nullif(trim(coalesce(origem_regra,'')),'') IS NULL")
                )
            ).scalar()
            if n:
                falhas.append(f"(d) {tb}: {n} linha(s) sem origem_regra")

        # (a) função com ativo → ≥1 evento e ≥1 benefício obrigatório
        funcs = (
            await db.execute(
                text(
                    "SELECT c.id::text, c.cargo_nome, count(e.id) AS ativos, "
                    " (SELECT count(*) FROM cct_funcao_eventos x WHERE x.cct_cargo_id=c.id AND coalesce(x.ativo,true)) AS ev, "
                    " (SELECT count(*) FROM cct_funcao_beneficios x WHERE x.cct_cargo_id=c.id AND coalesce(x.ativo,true) AND x.obrigatorio) AS bo "
                    f"FROM cct_cargos c JOIN employees e ON e.cct_cargo_id=c.id AND {ATIVO} "
                    "GROUP BY c.id, c.cargo_nome ORDER BY 3 DESC"
                )
            )
        ).all()
        sem_cct = (
            await db.execute(text(f"SELECT count(*) FROM employees e WHERE {ATIVO} AND e.cct_cargo_id IS NULL"))
        ).scalar()
        print(f"funções com ativo: {len(funcs)} · ativos sem função da CCT (fora da conta): {sem_cct}")
        for _fid, nome, ativos, ev, bo in funcs:
            if not ev:
                falhas.append(f"(a) {nome} ({ativos} ativos): 0 eventos configurados")
            if not bo:
                falhas.append(f"(a) {nome} ({ativos} ativos): 0 benefícios obrigatórios")

        # competência-alvo
        alvo = os.getenv("COMPETENCIA", "").strip()
        if alvo:
            ano, mes = int(alvo[:4]), int(alvo[5:7])
        else:
            ano, mes = 2026, 9
        n_alvo = (
            await db.execute(
                text(
                    f"SELECT count(*) FROM hr_payslips WHERE reference_year=:a AND reference_month=:m AND status IN {VISIVEIS}"
                ),
                {"a": ano, "m": mes},
            )
        ).scalar()
        if not n_alvo:
            r = (
                await db.execute(
                    text(
                        f"SELECT reference_year, reference_month FROM hr_payslips WHERE status IN {VISIVEIS} "
                        "AND (reference_year, reference_month) < (:a, :m) ORDER BY 1 DESC, 2 DESC LIMIT 1"
                    ),
                    {"a": ano, "m": mes},
                )
            ).first()
            if not r:
                falhas.append(f"(b) nenhum holerite visível em {mes:02d}/{ano} nem antes — sem contra-prova possível")
                r = (None, None)
            else:
                print(
                    f"AVISO: 0 holerite visível em {mes:02d}/{ano} — contra-prova na última visível: {r[1]:02d}/{r[0]}"
                )
            ano, mes = r
        if ano:
            hol = (
                await db.execute(
                    text(
                        "SELECT e.nome, c.cargo_nome, c.id::text, c.piso_salarial, p.base_salary, p.earnings "
                        "FROM hr_payslips p JOIN employees e ON e.id=p.employee_id JOIN cct_cargos c ON c.id=e.cct_cargo_id "
                        f"WHERE p.reference_year=:a AND p.reference_month=:m AND p.status IN {VISIVEIS} AND {ATIVO} "
                        "ORDER BY e.nome"
                    ),
                    {"a": ano, "m": mes},
                )
            ).all()
            evs = (
                await db.execute(
                    text(
                        "SELECT cct_cargo_id::text, rubrica_codigo, razao, obrigatorio FROM cct_funcao_eventos WHERE coalesce(ativo,true)"
                    )
                )
            ).all()
            ev_func: dict[str, dict[str, tuple]] = {}
            for fid, cod, razao, obrig in evs:
                ev_func.setdefault(fid, {})[cod] = (razao, obrig)
            print(f"(b) holerites visíveis de ativos com função em {mes:02d}/{ano}: {len(hol)}")
            pagos: dict[tuple[str, str], list[str]] = {}
            por_func: dict[str, int] = {}
            for nome, fnome, fid, piso, base, earnings in hol:
                por_func[fnome] = por_func.get(fnome, 0) + 1
                eventos = ev_func.get(fid, {})
                no_hol: dict[str, str] = {}
                for it in earnings or []:
                    cod = str(it.get("codigo") or "")
                    if cod in HOLERITE_PARA_RUBRICA:
                        no_hol[HOLERITE_PARA_RUBRICA[cod]] = str(it.get("referencia") or "")
                for rub, ref in no_hol.items():
                    if rub not in eventos:
                        falhas.append(
                            f"(b) {nome} [{fnome}]: holerite paga {NOME[rub]} (rubrica {rub}) e a função NÃO tem esse evento"
                        )
                        continue
                    razao, obrig = eventos[rub]
                    m_pct = re.match(r"\s*(\d+(?:[.,]\d+)?)\s*%", ref)
                    if (
                        razao is not None
                        and m_pct
                        and abs(float(m_pct.group(1).replace(",", ".")) - float(razao)) > 0.005
                    ):
                        falhas.append(
                            f"(b) {nome} [{fnome}]: {NOME[rub]} no holerite {m_pct.group(1)}% ≠ razão da função {razao}"
                        )
                    if not obrig:
                        pagos.setdefault((fnome, rub), []).append(nome)
                for rub, (_razao, obrig) in eventos.items():
                    if obrig and rub in RUBRICA_PARA_HOLERITE and rub not in no_hol:
                        falhas.append(
                            f"(b) {nome} [{fnome}]: evento OBRIGATÓRIO {NOME[rub]} (rubrica {rub}) ausente no holerite"
                        )
                # (c) — o holerite traz a base PROPORCIONAL («16 dias (admissão/desligamento)»); a régua é a
                # base cheia: valor × 30 / dias. Sem «N dias» na referência, compara o que está lá.
                dias = 30
                for it in earnings or []:
                    if str(it.get("codigo") or "") == "0001":
                        m_d = re.match(r"\s*(\d+)\s*dias", str(it.get("referencia") or ""))
                        dias = int(m_d.group(1)) if m_d else 30
                cheia = float(base) * 30 / dias if base is not None and dias else None
                if piso is not None and cheia is not None and cheia + 0.05 < float(piso):
                    falhas.append(
                        f"(c) {nome} [{fnome}]: salário-base do holerite R$ {float(base):.2f} ({dias} dias → cheia R$ {cheia:.2f}) < piso R$ {float(piso):.2f}"
                    )
            for (fnome, rub), nomes in sorted(pagos.items()):
                avisos.append(
                    f"{fnome}: {NOME[rub]} (opcional na função) pago a {len(nomes)}/{por_func[fnome]} — {', '.join(nomes)}"
                )

    for a in avisos:
        print(f"AVISO CCT × folha: {a}")
    for f in falhas:
        print(f"  ✗ {f}")
    print(f"TOTAL cct_como_dado: {len(falhas)} vermelho(s) · {len(avisos)} aviso(s)")
    if falhas:
        print("TEST oraculo_cct_como_dado FAIL")
        return 1
    print(
        "OK cct como dado: sindicato ligado, funções com evento/benefício, holerite bate com a função, piso respeitado"
    )
    print("TEST oraculo_cct_como_dado PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
