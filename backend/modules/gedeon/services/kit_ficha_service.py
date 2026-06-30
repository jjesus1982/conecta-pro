"""GEDEON — Ficha individualizada do kit por condomínio (montagem ponto-a-ponto pela Pyetra/Jordan).

Junta, para um condomínio + competência:
  - completude real (4 blocos) + arquivos por subpasta (lê o Drive);
  - CHECKLIST de eventos AUTO-detectados (contratações, demissões, férias) + manuais;
  - pendências de rescisão.
O checklist manual é guardado em JSON no volume uploads (sem migration; durável).
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import date

from sqlalchemy import text

CHECKLIST_DIR = "/app/uploads/kit_checklists"
TIPOS_EVENTO = [
    "contratacao",
    "demissao",
    "ferias",
    "migracao_posto",
    "entrada_outro_posto",
    "atestado",
    "afastamento",
    "observacao",
]


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper().strip()


def _mes_comp(competencia: str) -> tuple[int, int]:
    return int(competencia.split(".")[1]), int(competencia.split(".")[0])


def _mes_kit(competencia: str) -> tuple[int, int]:
    a, m = _mes_comp(competencia)
    return (a, m + 1) if m < 12 else (a + 1, 1)


def _client_id_do_condominio(db, condominio: str) -> str | None:
    """Casa o nome GEDEON ('IDEAL FLORES') ao cliente ('CONDOMINIO IDEAL FLORES DA CIDADE')."""
    toks = {t for t in _norm(condominio).split() if len(t) > 2 and t not in ("DOS", "DAS", "DE")}
    rows = db.execute(text("SELECT id, name FROM clients")).fetchall()
    for cid, nome in rows:
        ntoks = set(_norm(nome).split())
        if toks and toks <= ntoks:
            return str(cid)
    return None


def funcionarios_do_condominio(db, competencia: str, condominio: str, folha_nomes: list[str] | None = None) -> set[str]:
    """Nomes (normalizados) dos funcionários do condomínio = folha do kit ∪ alocações ativas."""
    nomes: set[str] = set(_norm(n) for n in (folha_nomes or []))
    cid = _client_id_do_condominio(db, condominio)
    if cid:
        rows = db.execute(
            text("""
            SELECT DISTINCT e.nome FROM employees e
            JOIN allocations a ON a.employee_id = e.id
            JOIN posts p ON a.post_id = p.id
            WHERE p.client_id = :cid"""),
            {"cid": cid},
        ).fetchall()
        nomes |= {_norm(r[0]) for r in rows}
    return nomes


def _pertence(nome_emp: str, nomes_cond: set[str]) -> bool:
    a = set(_norm(nome_emp).split())
    if len(a) < 2:
        return False
    for n in nomes_cond:
        b = set(n.split())
        if a <= b or b <= a:
            return True
    return False


def eventos_auto(db, competencia: str, condominio: str, nomes_cond: set[str]) -> list[dict]:
    """Contratações (admissão no mês trabalhado), demissões (no mês do kit) e férias do condomínio."""
    ca, cm = _mes_comp(competencia)  # mês trabalhado (competência)
    ka, km = _mes_kit(competencia)  # mês do kit (entrega)
    comp_ini = f"{ca}-{cm:02d}-01"
    comp_fim = f"{ka}-{km:02d}-01"
    kit_a2, kit_m2 = (ka, km + 1) if km < 12 else (ka + 1, 1)
    kit_fim = f"{kit_a2}-{kit_m2:02d}-01"
    ev: list[dict] = []

    # contratações: admissão na competência ou no mês do kit
    for nome, dt in db.execute(
        text(
            "SELECT nome, data_admissao FROM employees "
            "WHERE data_admissao >= :i AND data_admissao < :f ORDER BY data_admissao"
        ),
        {"i": comp_ini, "f": kit_fim},
    ).fetchall():
        if _pertence(nome, nomes_cond):
            ev.append(
                {
                    "tipo": "contratacao",
                    "auto": True,
                    "funcionario": nome,
                    "data": str(dt),
                    "descricao": f"Contratação em {dt}",
                }
            )

    # demissões: no mês do kit (rescisão processada)
    for nome, dt in db.execute(
        text(
            "SELECT nome, data_demissao FROM employees "
            "WHERE data_demissao >= :i AND data_demissao < :f ORDER BY data_demissao"
        ),
        {"i": f"{ca}-{cm:02d}-01", "f": kit_fim},
    ).fetchall():
        if _pertence(nome, nomes_cond):
            ev.append(
                {
                    "tipo": "demissao",
                    "auto": True,
                    "funcionario": nome,
                    "data": str(dt),
                    "descricao": f"Demissão em {dt} — anexar TRCT + verbas",
                }
            )

    # férias: docs de aviso prévio de férias no Onvio (qualquer categoria) p/ funcionários do cond
    for (nome_arq,) in db.execute(
        text(
            "SELECT nome_arquivo FROM onvio_documents "
            "WHERE nome_arquivo ILIKE '%ferias%' OR nome_arquivo ILIKE '%férias%'"
        )
    ).fetchall():
        m = re.split(r"[-_]", nome_arq)
        pessoa = m[-1].replace(".pdf", "").strip()
        if _pertence(pessoa, nomes_cond):
            ev.append(
                {
                    "tipo": "ferias",
                    "auto": True,
                    "funcionario": pessoa.title(),
                    "data": None,
                    "descricao": f"Férias (Onvio: {nome_arq[:40]})",
                }
            )
    return ev


# ── checklist manual (JSON no volume uploads) ────────────────────────────────
def _path_checklist(competencia: str, condominio: str) -> str:
    os.makedirs(CHECKLIST_DIR, exist_ok=True)
    return f"{CHECKLIST_DIR}/{competencia}__{_slug(condominio)}.json"


def eventos_manuais(competencia: str, condominio: str) -> list[dict]:
    p = _path_checklist(competencia, condominio)
    if os.path.exists(p):
        try:
            return json.load(open(p))
        except Exception:
            return []
    return []


def add_evento(
    competencia: str,
    condominio: str,
    tipo: str,
    descricao: str,
    funcionario: str | None = None,
    data: str | None = None,
    autor: str | None = None,
) -> dict:
    evs = eventos_manuais(competencia, condominio)
    novo = {
        "id": f"{int(date.today().strftime('%Y%m%d'))}{len(evs):03d}",
        "tipo": tipo,
        "auto": False,
        "funcionario": funcionario,
        "data": data,
        "descricao": descricao,
        "autor": autor,
    }
    evs.append(novo)
    json.dump(evs, open(_path_checklist(competencia, condominio), "w"), ensure_ascii=False, indent=2)
    return novo


def remove_evento(competencia: str, condominio: str, evento_id: str) -> bool:
    evs = eventos_manuais(competencia, condominio)
    novos = [e for e in evs if e.get("id") != evento_id]
    if len(novos) == len(evs):
        return False
    json.dump(novos, open(_path_checklist(competencia, condominio), "w"), ensure_ascii=False, indent=2)
    return True


def _nomes_da_folha(svc, condominio: str, competencia: str) -> list[str]:
    """Lê a 'Folha de Pagamento.pdf' do kit e extrai os nomes dos funcionários (inclui demitidos)."""
    import io

    from googleapiclient.http import MediaIoBaseDownload

    from modules.gedeon.services.inter_kit_service import extrair_funcionarios_folha
    from modules.gedeon.services.kit_layout import pasta_kit_arquivo

    try:
        folder = pasta_kit_arquivo(condominio, competencia, "Folha de Pagamento.pdf")
        it = (
            svc.files()
            .list(
                q=f"'{folder}' in parents and name='Folha de Pagamento.pdf' and trashed=false",
                fields="files(id)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
            .get("files", [])
        )
        if not it:
            return []
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, svc.files().get_media(fileId=it[0]["id"]))
        d = False
        while not d:
            _, d = dl.next_chunk()
        return [n for n, _r in extrair_funcionarios_folha(buf.getvalue())]
    except Exception:
        return []


def ficha(competencia: str, condominio: str) -> dict:
    """Ficha completa do kit de um condomínio: completude + arquivos + checklist (auto+manual)."""
    from core.database.session import get_sync_db
    from modules.gdrive.services.gdrive_service import gdrive_service
    from modules.gedeon.services.kit_completude_service import _ler_kit

    if not gdrive_service._service:
        gdrive_service.check_status()
    svc = gdrive_service._service
    kit = _ler_kit(svc, condominio, competencia) if svc else {}

    # nomes da FOLHA do condomínio (fonte confiável) + alocações → pertinência dos eventos
    folha_nomes = _nomes_da_folha(svc, condominio, competencia) if svc else []
    with get_sync_db() as db:
        nomes_cond = funcionarios_do_condominio(db, competencia, condominio, folha_nomes)
        auto = eventos_auto(db, competencia, condominio, nomes_cond)
    manuais = eventos_manuais(competencia, condominio)

    return {
        "competencia": competencia,
        "condominio": condominio,
        "completude": kit.get("completion_percentage", 0),
        "status": kit.get("status"),
        "total_docs": kit.get("total", 0),
        "drive_link": kit.get("drive_link"),
        "checklist": kit.get("checklist", []),
        "subpastas": kit.get("subpastas", []),
        "eventos": {"auto": auto, "manuais": manuais},
        "tipos_evento": TIPOS_EVENTO,
    }
