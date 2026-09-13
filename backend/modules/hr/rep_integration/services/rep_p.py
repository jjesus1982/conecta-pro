"""REP-P — AFD (Anexo I) e AEJ (Anexo VI) da Portaria MTP 671/2021, a partir de gp_clock_punches.

Frente 01 (12/09/2026). Leiautes copiados do gov.br (leiaute-do-arquivo-fonte-de-dados-afd.pdf,
versão 004; leiaute-do-arquivo-eletronico-de-jornada-aej.pdf, versão 002).

Decisões que este módulo carrega:
- CORTE: só batida >= 13/09/2026 00:00 (Manaus) vira linha AFD. O AFD é memória inalterável;
  preencher o histórico (Tangerino, ajustes do DP) seria afirmar integridade sobre dado editado.
  `REP_P_CORTE` no ambiente serve SÓ para medir no staging.
- Um "dispositivo" (rep_devices) por (empregador, origem da batida): o NSR é contínuo por
  dispositivo e o unique (device_id, nsr) do banco é a trava. Alocação serializada por
  pg_advisory_xact_lock — foi o buraco previsto no pré-mortem (1.375 jornadas duplicadas em 11/09).
- `punch_timestamp` é hora de parede de Manaus (medido: entrada mediana +50 min do início da
  escala; se fosse UTC daria +240). Fuso fixo -0400: Manaus não tem horário de verão.
- Sem CPF de 11 dígitos não há linha (o campo é obrigatório) — a pessoa aparece no caçador
  checar_ponto_sem_instrumento.py, nunca com CPF inventado.
- Nº do INPI vem de rep_instrumento_legal; enquanto vazio, o campo sai em branco e o oráculo
  test_oraculo_rep_p.py (e) fica vermelho de propósito.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

MANAUS = ZoneInfo("America/Manaus")
FUSO = "-0400"
#: hora de parede de Manaus (naive, como a coluna). Override só para medir no staging.
CORTE = datetime.fromisoformat(os.environ.get("REP_P_CORTE", "2026-09-13T00:00:00"))
VERSAO_AFD = "004"
VERSAO_AEJ = "002"
ASSINATURA = "ASSINATURA_DIGITAL_EM_ARQUIVO_P7S".ljust(100)
#: desenvolvedor do PTRP/REP-P (tipo 1 campos 12-13; AEJ tipo 08). É a própria empresa.
DESENVOLVEDOR = {"cnpj": "35710481000103", "razao": "CONECTAMAIS ELETRONICA LTDA",
                 "email": "jjesus@conectamais.pro", "programa": "Conecta PRO"}
#: campo 6 do tipo 7 — identificador do coletor (Anexo I): 01 mobile, 02 browser, 03 desktop,
#: 04 dispositivo eletrônico, 05 outro. Origem desconhecida cai em 05, nunca é inventada.
COLETOR = {"mobile": "01", "conecta_pro_app": "01", "facial": "01",
           "web": "02", "ajuste_dp": "02", "manual": "02",
           "tangerino": "05", "contingencia": "05"}
#: AEJ tipo 05 campo 5. 'extra' e desconhecidos viram 'D' (desconsiderada) com motivo.
TP_MARC = {"entrada": "E", "retorno_almoco": "E", "saida": "S", "saida_almoco": "S"}
#: AEJ tipo 05 campo 7 — só o que é inclusão manual é 'I'; o resto decide pela existência de NSR.
FONTE_MANUAL = {"ajuste_dp", "manual"}


def crc16_kermit(s: str) -> str:
    """CRC-16/KERMIT (CCITT-TRUE), hex maiúsculo sem 0x — o Anexo I dá '123456789' -> 2189."""
    crc = 0
    for b in s.encode("latin-1"):
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return f"{crc:04X}"


assert crc16_kermit("123456789") == "2189"


def dh(v: datetime) -> str:
    """Campo DH: AAAA-MM-ddThh:mm:00ZZZZZ (segundos fixos em 00)."""
    return f"{v:%Y-%m-%dT%H:%M}:00{FUSO}"


def _digitos(v: str | None) -> str:
    return re.sub(r"\D", "", v or "")


def _a(v: str | None, n: int) -> str:
    """Campo alfanumérico: começa à esquerda, sobra vira espaço, corta no tamanho."""
    return (v or "")[:n].ljust(n)


def linha_tipo7(nsr: int, marcacao: datetime, cpf: str, gravacao: datetime,
                coletor: str, offline: bool, hash_anterior: str | None) -> tuple[str, str]:
    """Registro tipo 7 (marcação REP-P), 137 posições. Hash SHA-256 dos campos 1-7 + hash anterior."""
    base = f"{nsr:09d}7{dh(marcacao)}{cpf.zfill(12)}{dh(gravacao)}{coletor}{'1' if offline else '0'}"
    h = hashlib.sha256((base + (hash_anterior or "")).encode("latin-1")).hexdigest()
    return base + h, h


def linha_tipo2(nsr: int, gravacao: datetime, cpf_responsavel: str, cnpj: str,
                razao: str, local: str) -> str:
    """Registro tipo 2 (identificação do empregador no REP), 331 posições, com CRC-16."""
    base = (f"{nsr:09d}2{dh(gravacao)}{_a(cpf_responsavel, 14)}1{_a(cnpj, 14)}{_a('', 14)}"
            f"{_a(razao, 150)}{_a(local, 100)}")
    return base + crc16_kermit(base)


def linha_tipo1(cnpj: str, razao: str, inpi: str, ini: date, fim: date, geracao: datetime) -> str:
    """Cabeçalho (302 posições). Campo 7 = nº INPI (REP-P); vazio sai em branco, nunca zeros."""
    base = (f"{'0' * 9}11{_a(cnpj, 14)}{_a('', 14)}{_a(razao, 150)}{_a(inpi, 17)}"
            f"{ini:%Y-%m-%d}{fim:%Y-%m-%d}{dh(geracao)}{VERSAO_AFD}1{_a(DESENVOLVEDOR['cnpj'], 14)}"
            f"{_a('', 30)}")
    return base + crc16_kermit(base)


def linha_tipo9(qt: dict[str, int]) -> str:
    return "9" * 9 + "".join(f"{qt.get(t, 0):09d}" for t in "234567") + "9"


async def instrumento(db: AsyncSession) -> dict[str, dict[str, Any]]:
    """rep_instrumento_legal por tipo (INPI, ATESTADO_TECNICO, TERMO_RESPONSABILIDADE)."""
    rows = (await db.execute(text(
        "SELECT tipo, numero, emissor, data_emissao, validade FROM rep_instrumento_legal "
        "ORDER BY data_emissao DESC NULLS LAST"))).mappings().all()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        out.setdefault(r["tipo"], dict(r))
    return out


async def _empresa(db: AsyncSession, cnpj: str) -> dict[str, Any] | None:
    r = (await db.execute(text(
        "SELECT id, razao_social, regexp_replace(cnpj,'\\D','','g') cnpj FROM empresas "
        "WHERE regexp_replace(cnpj,'\\D','','g') = :c"), {"c": _digitos(cnpj)})).mappings().first()
    return dict(r) if r else None


async def _dispositivo(db: AsyncSession, empresa: dict[str, Any], origem: str) -> str:
    """Um rep_devices por (empregador, origem). Cria na primeira batida; serial é a chave."""
    serial = f"REP-P-{empresa['cnpj']}-{origem.upper()}"
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:s))"), {"s": serial})
    await db.execute(text(
        "INSERT INTO rep_devices (id, condominio_id, manufacturer, model, serial_number, "
        " device_name, description, status, is_active) "
        "VALUES (gen_random_uuid(), :emp, 'conecta_pro', 'rep_p', :s, :nome, :desc, 'online', true) "
        "ON CONFLICT (serial_number) DO NOTHING"),
        {"emp": empresa["id"], "s": serial, "nome": f"REP-P {origem} — {empresa['razao_social']}"[:100],
         "desc": f"coletor virtual do REP-P: batidas de origem '{origem}' de {empresa['razao_social']}"})
    return (await db.execute(text("SELECT id::text FROM rep_devices WHERE serial_number=:s"),
                             {"s": serial})).scalar_one()


async def gerar_afd_desde_corte(db: AsyncSession, commit: bool = True) -> dict[str, Any]:
    """Idempotente: toda batida >= CORTE sem linha AFD ganha uma (unique em afd_records.punch_id).

    Chamada pelo hook de registrar_batida (commit=False: a transação é da batida) e pela rota
    POST /ponto/afd/rep-p/gerar. Retorna o que gerou e o que NÃO pôde gerar (sem CPF / sem
    empregador) — isso é dívida, não silêncio.
    """
    pend = (await db.execute(text("""
        SELECT p.punch_id, p.device_type, p.is_offline, p.punch_timestamp, e.empresa_id::text emp,
               regexp_replace(coalesce(e.cpf,''),'\\D','','g') cpf, e.nome
        FROM gp_clock_punches p
        JOIN employees e ON e.id = p.employee_id
        LEFT JOIN afd_records a ON a.punch_id = p.punch_id
        WHERE p.punch_timestamp >= :corte AND a.id IS NULL
        ORDER BY p.punch_timestamp, p.id"""), {"corte": CORTE})).mappings().all()
    geradas, sem_cpf, sem_empresa = 0, set(), set()
    grupos: dict[tuple[str, str], list] = defaultdict(list)
    for p in pend:
        if len(p["cpf"]) != 11:
            sem_cpf.add(p["nome"])
        elif not p["emp"]:
            sem_empresa.add(p["nome"])
        else:
            grupos[(p["emp"], p["device_type"] or "web")].append(p)

    cpf_resp = (await db.execute(text(
        "SELECT regexp_replace(coalesce(cpf,''),'\\D','','g') FROM employees "
        "WHERE nome = 'Jordan Santos de Jesus' LIMIT 1"))).scalar() or ""
    agora = datetime.now(MANAUS).replace(tzinfo=None)
    for (emp_id, origem), lote in grupos.items():
        emp = (await db.execute(text(
            "SELECT id, razao_social, regexp_replace(cnpj,'\\D','','g') cnpj FROM empresas "
            "WHERE id::text = :i"), {"i": emp_id})).mappings().first()
        if not emp:
            sem_empresa.update(p["nome"] for p in lote)
            continue
        dev = await _dispositivo(db, dict(emp), origem)
        ult = (await db.execute(text(
            "SELECT nsr, line_hash, record_type FROM afd_records WHERE device_id = CAST(:d AS uuid) "
            "ORDER BY nsr DESC LIMIT 1"), {"d": dev})).first()
        nsr, hash_ant = (ult[0], ult[1] if ult[2] == "7" else None) if ult else (0, None)
        if not ult:
            nsr = 1
            l2 = linha_tipo2(nsr, agora, cpf_resp, emp["cnpj"], emp["razao_social"], "")
            await db.execute(text(
                "INSERT INTO afd_records (id, device_id, condominio_id, nsr, record_type, afd_line, "
                " line_hash, cnpj, company_name, is_valid, is_exported, created_at) "
                "VALUES (gen_random_uuid(), CAST(:d AS uuid), CAST(:emp AS uuid), :nsr, '2', :l, "
                " :h, :cnpj, :rz, true, false, now())"),
                {"d": dev, "emp": emp_id, "nsr": nsr, "l": l2, "h": hashlib.sha256(l2.encode()).hexdigest(),
                 "cnpj": emp["cnpj"], "rz": emp["razao_social"][:150]})
        for p in lote:
            nsr += 1
            linha, h = linha_tipo7(nsr, p["punch_timestamp"], p["cpf"], agora,
                                   COLETOR.get(origem, "05"), bool(p["is_offline"]), hash_ant)
            await db.execute(text(
                "INSERT INTO afd_records (id, device_id, condominio_id, nsr, record_type, afd_line, "
                " record_date, record_time, line_hash, punch_id, origem, is_valid, is_exported, created_at) "
                "VALUES (gen_random_uuid(), CAST(:d AS uuid), CAST(:emp AS uuid), :nsr, '7', :l, "
                " :dt, :tm, :h, :pid, :org, true, false, now())"),
                {"d": dev, "emp": emp_id, "nsr": nsr, "l": linha, "dt": p["punch_timestamp"].date(),
                 "tm": p["punch_timestamp"].time().replace(microsecond=0), "h": h,
                 "pid": p["punch_id"], "org": origem})
            hash_ant = h
            geradas += 1
    if commit:
        await db.commit()
    return {"corte": CORTE.isoformat(), "pendentes": len(pend), "geradas": geradas,
            "sem_cpf": sorted(sem_cpf), "sem_empresa": sorted(sem_empresa)}


async def montar_afd(db: AsyncSession, cnpj: str, origem: str, ini: date, fim: date) -> tuple[str, str]:
    """Arquivo AFD de um dispositivo (empregador+origem) no período. Devolve (nome, conteúdo).

    NSR do tipo 2 e do tipo 7 são os gravados; cabeçalho e trailer são montados na hora, como o
    Anexo I manda ("000000000" e "999999999"). Linhas CRLF, ISO-8859-1 fica por conta de quem grava.
    """
    emp = await _empresa(db, cnpj)
    if not emp:
        raise ValueError(f"empregador {cnpj} não está em empresas")
    inpi = ((await instrumento(db)).get("INPI") or {}).get("numero") or ""
    serial = f"REP-P-{emp['cnpj']}-{origem.upper()}"
    rows = (await db.execute(text("""
        SELECT a.record_type, a.afd_line FROM afd_records a
        JOIN rep_devices d ON d.id = a.device_id
        WHERE d.serial_number = :s AND (a.record_type <> '7' OR (a.record_date BETWEEN :i AND :f))
        ORDER BY a.nsr"""), {"s": serial, "i": ini, "f": fim})).all()
    qt: dict[str, int] = defaultdict(int)
    for t, _ in rows:
        qt[t] += 1
    linhas = [linha_tipo1(emp["cnpj"], emp["razao_social"], inpi, ini, fim,
                          datetime.now(MANAUS).replace(tzinfo=None))]
    linhas += [l for _, l in rows]
    linhas.append(linha_tipo9(qt))
    linhas.append(ASSINATURA)
    nome = f"AFD{inpi or 'SEM_INPI'}{emp['cnpj']}REP_P_{origem}.txt"
    return nome, "\r\n".join(linhas) + "\r\n"


async def montar_aej(db: AsyncSession, cnpj: str, ano: int, mes: int) -> tuple[str, str, dict[str, int]]:
    """AEJ (Anexo VI, versão 002) de um empregador na competência. Devolve (nome, conteúdo, contagens).

    Cobre TODAS as marcações da competência (também as anteriores ao corte): marcação com NSR no
    AFD é fonte 'O' com idRep; ajuste do DP é 'I'; o resto (Tangerino, histórico) é 'T'. Sem
    tipo 07 (ausências/banco de horas): não há pipeline real para isso — está no relatório.
    """
    emp = await _empresa(db, cnpj)
    if not emp:
        raise ValueError(f"empregador {cnpj} não está em empresas")
    ini = date(ano, mes, 1)
    fim = date(ano + (mes == 12), mes % 12 + 1, 1)
    inpi = ((await instrumento(db)).get("INPI") or {}).get("numero") or ""
    marc = (await db.execute(text("""
        SELECT p.employee_id::text emp, e.nome, regexp_replace(coalesce(e.cpf,''),'\\D','','g') cpf,
               p.punch_timestamp ts, p.punch_type, p.device_type, d.serial_number serial,
               j.reason motivo_just,
               (SELECT string_agg(to_char(s.planned_start_time,'HH24MI')||'-'||to_char(s.planned_end_time,'HH24MI')
                                  ||'-'||s.planned_break_minutes, ',')
                  FROM shifts s WHERE s.employee_id = p.employee_id AND s.shift_date = p.punch_timestamp::date
                  AND NOT s.is_off_day) hor
        FROM gp_clock_punches p
        JOIN employees e ON e.id = p.employee_id
        LEFT JOIN afd_records a ON a.punch_id = p.punch_id
        LEFT JOIN rep_devices d ON d.id = a.device_id
        LEFT JOIN gp_justifications j ON j.justification_id = p.justification_id
        WHERE e.empresa_id::text = :emp AND p.punch_timestamp >= :i AND p.punch_timestamp < :f
          AND length(regexp_replace(coalesce(e.cpf,''),'\\D','','g')) = 11
        ORDER BY p.employee_id, p.punch_timestamp, p.id"""),
        {"emp": str(emp["id"]), "i": datetime.combine(ini, datetime.min.time()),
         "f": datetime.combine(fim, datetime.min.time())})).mappings().all()

    reps: dict[str, int] = {}
    vinc: dict[str, int] = {}
    horarios: dict[str, str] = {}
    r02, r03, r04, r05 = [], [], [], []
    seq: dict[str, int] = defaultdict(int)
    for m in marc:
        if m["emp"] not in vinc:
            vinc[m["emp"]] = len(vinc) + 1
            r03.append(f"03|{vinc[m['emp']]}|{m['cpf']}|{m['nome'][:150]}")
        id_rep = ""
        if m["serial"]:
            if m["serial"] not in reps:
                reps[m["serial"]] = len(reps) + 1
                r02.append(f"02|{reps[m['serial']]}|3|{inpi}")
            id_rep = str(reps[m["serial"]])
        tp = TP_MARC.get(m["punch_type"], "D")
        motivo = ""
        if tp == "D":
            motivo = f"tipo de marcação '{m['punch_type']}' não mapeado"
        if tp == "E":
            seq[m["emp"]] += 1
        elif seq[m["emp"]] == 0:
            seq[m["emp"]] = 1
        if m["device_type"] in FONTE_MANUAL:
            fonte = "I"
            motivo = motivo or m["motivo_just"] or "ajuste manual do DP sem justificativa vinculada"
        else:
            fonte = "O" if m["serial"] else "T"
        cod = ""
        if tp == "E" and m["hor"]:
            h = m["hor"].split(",")[0]
            if h not in horarios:
                e1, s1, br = h.split("-")
                dur = ((int(s1[:2]) * 60 + int(s1[2:])) - (int(e1[:2]) * 60 + int(e1[2:]))) % 1440 - int(br)
                horarios[h] = f"04|{h}|{max(dur, 0)}|{e1}|{s1}||"
                r04.append(horarios[h])
            cod = h
        r05.append(f"05|{vinc[m['emp']]}|{dh(m['ts'])}|{id_rep}|{tp}|{seq[m['emp']]}|{fonte}|{cod}|{motivo[:150]}")

    r01 = (f"01|1|{emp['cnpj']}|||{emp['razao_social'][:150]}|{ini:%Y-%m-%d}|"
           f"{fim - timedelta(days=1):%Y-%m-%d}|{dh(datetime.now(MANAUS).replace(tzinfo=None))}|{VERSAO_AEJ}")
    from core.config.settings import settings  # tardio: o módulo é importado por oráculo fora do app
    r08 = (f"08|{DESENVOLVEDOR['programa']}|{settings.app_version[:8]}|1|{DESENVOLVEDOR['cnpj']}|"
           f"{DESENVOLVEDOR['razao']}|{DESENVOLVEDOR['email']}")
    qt = {"01": 1, "02": len(r02), "03": len(r03), "04": len(r04), "05": len(r05), "06": 0, "07": 0, "08": 1}
    r99 = "99|" + "|".join(str(qt[k]) for k in ("01", "02", "03", "04", "05", "06", "07", "08"))
    linhas = [r01, *r02, *r03, *r04, *r05, r08, r99, ASSINATURA]
    nome = f"AEJ_{emp['cnpj']}_{ano:04d}{mes:02d}.txt"
    return nome, "\r\n".join(linhas) + "\r\n", qt
