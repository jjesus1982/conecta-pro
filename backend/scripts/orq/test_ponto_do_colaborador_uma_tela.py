"""Oráculo: a aba «Ponto do colaborador» sabe DE QUAL BATIDA cada hora veio.

A REGRA que este arquivo guarda (não a fotografia de nenhum mês, pessoa ou punch_id):

  1. `espelho_service._segmentos` devolve `entrada_punch_id`/`saida_punch_id` em cada segmento —
     o id da batida que originou cada ponta, e `None` na ponta que não existe. Era aqui o
     defeito: o segmento saía com a HORA e mais nada, e a foto da batida só é endereçável por
     `punch_id` (`GET /ponto/batida/{punch_id}/foto`). Sem o id, a tela teria de reencontrar a
     batida pela HORA — e hora não identifica batida nesta casa (há 3 «entrada» no MESMO segundo).

  2. `dias_com_segmentos` completa o espelho GRAVADO cujos segmentos existem mas NÃO trazem id.
     «Tem segmentos» ≠ «tem segmentos úteis»: `segmentos` começou a ser gravado algumas horas
     antes de os ids serem acrescentados, então existe safra de espelho com a chave externa
     presente e zero id dentro. Uma guarda que olhasse só a chave externa pularia a derivação e
     a tela perderia foto, local e status — foi o que aconteceu (medido: 0 células de foto num
     período que tinha 24).

  3. O plantão declara TODOS os dias civis que as batidas dele tocam, e o conjunto sai dos
     `punch_timestamp` — nunca do calendário. Um 12x36 noturno começa 19:00 de um dia e termina
     07:17 do outro: a rota de aprovação decide UM dia civil por chamada, então aprovar só o dia
     de início deixa o plantão metade aprovado com cara de aprovado.
     CONTROLE obrigatório: plantão diurno tem UM dia civil só — uma regra que responde «dois»
     sempre não prova nada.

  4. Status é o que o banco diz, e ignorância se declara: verde SÓ com todas `approved`;
     parcial aparece como parcial; segmento SEM id vira «recalcule o espelho», nunca «sem
     batida» (isso seria afirmar o contrário do que a própria linha, com hora, mostra).

  5. Sobre dado REAL: na competência com mais espelhos, todo segmento de par fechado que chega à
     tela tem os dois ids, e esses ids EXISTEM em `gp_clock_punches`. Id que não existe = foto em
     404 e status inventado. É a regra 1 medida contra o banco em vez de fixture.

Roda no container:
    docker exec -e PYTHONPATH=/app -w /app conecta-pro-backend \
        python scripts/orq/test_ponto_do_colaborador_uma_tela.py
"""

from datetime import datetime, timedelta

from sqlalchemy import text

from core.database.session import SyncSessionLocal
from modules.people_management.hr.services.espelho_ponto_service import ler_espelho
from modules.people_management.hr.services.espelho_service import _parear, _segmentos
from modules.people_management.ponto.controllers.punch_controller import dias_com_segmentos


def _batida(pid: str, tipo: str, ts: str) -> dict:
    return {
        "punch_id": pid,
        "punch_type": tipo,
        "punch_timestamp": datetime.fromisoformat(ts),
        "status": "pending",
        "device_type": "mobile",
        "justification_id": "",
    }


def regra_1_segmento_diz_de_qual_batida_veio() -> None:
    """Par fechado ⇒ os DOIS ids; órfão ⇒ id na ponta que existe e None na que falta."""
    orfaos: list[dict] = []
    pares, _ = _parear(
        [
            _batida("p1", "entrada", "2026-07-27T19:00"),
            _batida("p2", "saida", "2026-07-28T02:00"),
            _batida("p3", "entrada", "2026-07-28T03:00"),  # sem saída: fica órfã
        ],
        orfaos_out=orfaos,
    )
    segs = _segmentos(pares, orfaos)
    fechados = [s for s in segs if not s["incompleto"]]
    assert len(fechados) == 1, segs
    # `.get` e não `[...]`: chave AUSENTE é o defeito que esta regra guarda, e um KeyError cru
    # esconde a frase que explica o defeito. Campo ausente falha FECHADO, com o motivo à vista.
    assert fechados[0].get("entrada_punch_id") == "p1", (
        f"o segmento não diz de qual batida veio a ENTRADA: {fechados[0]!r}"
    )
    assert fechados[0].get("saida_punch_id") == "p2", (
        f"o segmento não diz de qual batida veio a SAÍDA: {fechados[0]!r}"
    )
    orf = [s for s in segs if s["incompleto"]]
    assert len(orf) == 1, segs
    assert orf[0].get("entrada_punch_id") == "p3", f"órfã sem id da ponta que EXISTE: {orf[0]!r}"
    assert orf[0].get("saida_punch_id") is None, (
        f"órfã ganhou id numa ponta que não tem batida — id inventado: {orf[0]!r}"
    )
    # A hora NÃO muda: o acréscimo é de identidade, não de apuração.
    assert (fechados[0]["entrada"], fechados[0]["saida"], fechados[0]["minutos"]) == ("19:00", "02:00", 420), fechados
    print("OK 1 · cada ponta do segmento diz de qual batida veio (e a ponta ausente vem None)")


def regra_2_segmento_gravado_sem_id_e_completado() -> None:
    """Espelho GRAVADO com `segmentos` e sem id dentro tem de ser completado, não pulado."""
    with SyncSessionLocal() as s:
        alvo = s.execute(
            text(
                "SELECT CAST(employee_id AS TEXT), reference_month, reference_year "
                "  FROM time_sheets "
                " WHERE coalesce(is_deleted,false)=false AND daily_summary IS NOT NULL "
                "   AND EXISTS (SELECT 1 FROM jsonb_array_elements(daily_summary::jsonb) e "
                "                WHERE e ? 'segmentos' AND jsonb_array_length(e->'segmentos') > 0) "
                " ORDER BY reference_year DESC, reference_month DESC LIMIT 1"
            )
        ).first()
        if not alvo:
            print("OK 2 · nenhum espelho com `segmentos` gravado ainda — regra sem sujeito, 1 pega")
            return
        eid, mes, ano = str(alvo[0]), int(alvo[1]), int(alvo[2])
        esp = ler_espelho(s, eid, mes, ano)
        assert esp, f"time_sheet {mes:02d}/{ano} existe e `ler_espelho` devolveu nada"
        dias = dias_com_segmentos(s, esp, mes, ano)

    # CONTA os dias que têm par fechado e mede quantos saem sem id. Zero é a regra.
    com_par = sem_id = 0
    for d in dias:
        fechados = [x for x in (d.get("segmentos") or []) if isinstance(x, dict) and not x.get("incompleto")]
        if not fechados:
            continue
        com_par += 1
        if not any(x.get("entrada_punch_id") or x.get("saida_punch_id") for x in fechados):
            sem_id += 1
    assert com_par > 0, (
        f"{mes:02d}/{ano} de {eid}: espelho escolhido por ter `segmentos` gravado e nenhum dia "
        "chegou com par fechado — a leitura de segmentos está desligada, o oráculo está sem lastro"
    )
    assert sem_id == 0, (
        f"{sem_id} de {com_par} dia(s) de {mes:02d}/{ano} chegaram à tela com segmento SEM id de "
        "batida: sem id não há foto, nem local, nem status — `dias_com_segmentos` pulou a derivação "
        "porque olhou a chave `segmentos` em vez do id que a tela consome"
    )
    print(f"OK 2 · {mes:02d}/{ano}: {com_par} dia(s) com par fechado, {sem_id} sem id de batida")


def regra_3_plantao_noturno_declara_os_dois_dias_civis() -> None:
    """O conjunto de dias civis do plantão sai das batidas; diurno dá UM, noturno dá DOIS."""

    def civis(batidas: list[dict]) -> list[str]:
        """O que o builder faz: dia civil de cada batida do plantão, na ordem, sem repetir."""
        orfaos: list[dict] = []
        pares, _ = _parear(batidas, orfaos_out=orfaos)
        segs = _segmentos(pares, orfaos)
        ids = [p for s in segs for p in (s["entrada_punch_id"], s["saida_punch_id"]) if p]
        por_id = {b["punch_id"]: b["punch_timestamp"].date().isoformat() for b in batidas}
        out: list[str] = []
        for i in ids:
            if por_id[i] not in out:
                out.append(por_id[i])
        return out

    noturno = civis(
        [
            _batida("n1", "entrada", "2026-07-27T19:00"),
            _batida("n2", "saida", "2026-07-28T02:00"),
            _batida("n3", "entrada", "2026-07-28T03:00"),
            _batida("n4", "saida", "2026-07-28T07:17"),
        ]
    )
    assert noturno == ["2026-07-27", "2026-07-28"], (
        f"plantão 19:00→07:17 tem de declarar os DOIS dias civis; declarou {noturno}. "
        "Com um só, aprovar o plantão deixa 3 de 4 batidas pendentes e a tela diz «aprovado»"
    )
    # CONTROLE: diurno é UM dia civil. Sem esta irmã, «sempre dois» passaria.
    diurno = civis(
        [
            _batida("d1", "entrada", "2026-07-27T08:00"),
            _batida("d2", "saida_almoco", "2026-07-27T12:00"),
            _batida("d3", "retorno_almoco", "2026-07-27T13:00"),
            _batida("d4", "saida", "2026-07-27T17:00"),
        ]
    )
    assert diurno == ["2026-07-27"], f"plantão diurno inventou dia civil a mais: {diurno}"
    print("OK 3 · noturno declara 2 dias civis, diurno declara 1 (derivado das batidas)")


def regra_4_status_nao_inventa_nem_cala() -> None:
    # Import aqui e não no topo: `departamento_pessoal` PRIMEIRO. O discovery de builders importa
    # `departamento_pessoal`, que importa `_dgx_f7_ponto`; importar o filho antes do pai faz a
    # descoberta topar num módulo meio-inicializado e cospe um «circular import» no meio da saída
    # do oráculo — ruído que faz uma execução verde parecer quebrada.
    from modules.operacional.controllers.redesign_builders import departamento_pessoal  # noqa: F401,PLC0415
    from modules.operacional.controllers.redesign_builders._dgx_f7_ponto import (  # noqa: PLC0415
        _status_do_conjunto,
    )

    ok = _status_do_conjunto([{"status": "approved"}, {"status": "approved"}])
    assert "Aprovado" in ok["v"] and ok["color"] == "#16A34A", ok
    parcial = _status_do_conjunto([{"status": "approved"}, {"status": "pending"}])
    assert parcial["v"] == "1 de 2 aprovadas", f"meio caminho não pode virar verde: {parcial}"
    rep = _status_do_conjunto([{"status": "approved"}, {"status": "rejected"}])
    assert rep["v"] == "Reprovado", rep
    aguarda = _status_do_conjunto([{"status": "pending"}, {"status": "normal"}])
    assert aguarda["v"] == "Aguardando conferência", aguarda
    rosto = _status_do_conjunto([{"status": "pendente_de_conferencia"}])
    assert rosto["v"] == "Rosto em reconferência", f"reconferência do servidor não é decisão do DP: {rosto}"
    # Sem id ⇒ desconhecido. «sem batida» numa linha que mostra hora é afirmar o oposto do que a
    # linha mostra: é converter «não me informa» em «não existe».
    sem_id = _status_do_conjunto([], tem_id=False)
    assert "recalcule" in sem_id["v"], f"segmento sem id virou afirmação sobre o banco: {sem_id}"
    vazio = _status_do_conjunto([], tem_id=True)
    assert vazio["v"] == "sem batida", vazio
    print("OK 4 · verde só com todas aprovadas · parcial é parcial · sem id declara ignorância")


def regra_5_dado_real_os_ids_existem() -> None:
    """Na competência com mais espelhos: todo par fechado tem os dois ids, e eles EXISTEM."""
    with SyncSessionLocal() as s:
        comp = s.execute(
            text(
                "SELECT reference_year, reference_month FROM time_sheets "
                " WHERE coalesce(is_deleted,false)=false GROUP BY 1,2 "
                " ORDER BY count(*) DESC, 1 DESC, 2 DESC LIMIT 1"
            )
        ).first()
        assert comp, "nenhum time_sheet no banco — oráculo sem lastro"
        ano, mes = int(comp[0]), int(comp[1])
        ids_tela: set[str] = set()
        pares = faltando = 0
        for (eid,) in s.execute(
            text(
                "SELECT CAST(employee_id AS TEXT) FROM time_sheets "
                " WHERE reference_month=:m AND reference_year=:y AND coalesce(is_deleted,false)=false "
                " LIMIT 15"
            ),
            {"m": mes, "y": ano},
        ).all():
            esp = ler_espelho(s, eid, mes, ano)
            if esp is None:
                continue
            for d in dias_com_segmentos(s, esp, mes, ano):
                for seg in d.get("segmentos") or []:
                    if not isinstance(seg, dict) or seg.get("incompleto"):
                        continue
                    pares += 1
                    pe, ps = seg.get("entrada_punch_id"), seg.get("saida_punch_id")
                    if not (pe and ps):
                        faltando += 1
                        continue
                    ids_tela.update((pe, ps))
        assert pares > 0, f"{mes:02d}/{ano}: nenhum par fechado na amostra — sem lastro"
        assert faltando == 0, (
            f"{faltando} de {pares} par(es) fechado(s) de {mes:02d}/{ano} chegaram à tela sem os "
            "dois ids de batida — a foto e o status daquela linha não têm como ser buscados"
        )
        achados = {
            r[0]
            for r in s.execute(
                text("SELECT punch_id FROM gp_clock_punches WHERE punch_id = ANY(string_to_array(CAST(:i AS text),','))"),
                {"i": ",".join(sorted(ids_tela))},
            ).all()
        }
    fantasmas = sorted(ids_tela - achados)
    assert not fantasmas, (
        f"{len(fantasmas)} id(s) citado(s) pela tela NÃO existem em gp_clock_punches (ex.: "
        f"{fantasmas[:3]}) — a foto daria 404 e o status seria inventado"
    )
    print(f"OK 5 · {mes:02d}/{ano}: {pares} par(es) fechado(s), {len(ids_tela)} id(s), todos no banco")


def regra_6_turno_em_curso_nao_e_pendencia() -> None:
    """Entrada de HÁ POUCO sem saída é turno em andamento, não batida faltando.

    Protege o botão «Registrar batida»: cobrar a saída de quem ainda está no posto é cobrar o
    futuro, e a tela marca o segmento como `em_curso` para dizer isso em vez de acusar falta.
    """
    agora = datetime.now()
    orfaos: list[dict] = []
    pares, _ = _parear([_batida("c1", "entrada", (agora - timedelta(hours=2)).isoformat(timespec="minutes"))], orfaos_out=orfaos)
    segs = _segmentos(pares, orfaos)
    assert len(segs) == 1 and segs[0]["incompleto"], segs
    assert segs[0].get("em_curso") is True, f"entrada de 2h atrás virou pendência de DP: {segs[0]!r}"
    assert segs[0].get("entrada_punch_id") == "c1", segs[0]
    velha = _parear([_batida("v1", "entrada", "2026-01-02T08:00")], orfaos_out=(o2 := []))
    s2 = _segmentos(velha[0], o2)
    assert s2[0].get("em_curso") is False, f"entrada de janeiro não é turno em andamento: {s2[0]!r}"
    print("OK 6 · turno em andamento não é batida faltando (e o de janeiro é)")


def main() -> None:
    regra_1_segmento_diz_de_qual_batida_veio()
    regra_2_segmento_gravado_sem_id_e_completado()
    regra_3_plantao_noturno_declara_os_dois_dias_civis()
    regra_4_status_nao_inventa_nem_cala()
    regra_5_dado_real_os_ids_existem()
    regra_6_turno_em_curso_nao_e_pendencia()
    print("TODOS OS ORÁCULOS OK")


if __name__ == "__main__":
    main()
