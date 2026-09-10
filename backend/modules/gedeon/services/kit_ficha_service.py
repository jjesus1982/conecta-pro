"""GEDEON — Ficha individualizada do kit por condomínio (montagem ponto-a-ponto pela Pyetra/Jordan).

Junta, para um condomínio + competência:
  - completude real (4 blocos) + arquivos por subpasta (lê o Drive);
  - CHECKLIST de eventos AUTO-detectados (contratações, demissões, férias) + manuais;
  - pendências de rescisão.
O checklist manual é guardado em JSON no volume uploads (sem migration; durável).
"""

from __future__ import annotations

import json
import logging
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
    # 09/09: o nome do condomínio pode estar em clients.trading_name ou em condominiums.name (cliente = empresa
    # tomadora, condomínio = local do serviço — caso Conecta Village); antes só clients.name casava
    rows = db.execute(
        text(
            "SELECT id, name FROM clients UNION ALL SELECT id, trading_name FROM clients WHERE trading_name IS NOT NULL "
            "UNION ALL SELECT client_id, name FROM condominiums"
        )
    ).fetchall()
    for cid, nome in rows:
        if _norm(nome) == _norm(condominio):
            return str(cid)
    for cid, nome in rows:
        ntoks = set(_norm(nome).split())
        if toks and toks <= ntoks:
            return str(cid)
    return None


def funcionarios_do_condominio(db, competencia: str, condominio: str, folha_nomes: list[str] | None = None) -> set[str]:
    """Nomes (normalizados) dos funcionários do condomínio = folha do kit ∪ alocações ativas."""
    nomes: set[str] = {_norm(n) for n in (folha_nomes or [])}
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

    # ── Férias: o BANCO é a fonte, não o nome do arquivo ──────────────────────────────────────
    # 10/09/2026 — o Hermes, conferindo o kit do Michelangelo, achou "Férias de Antonio Vieira
    # registradas 4x nos eventos". O banco tem UMA férias aprovada dele (15/06 a 14/07).
    #
    # A versão anterior varria TODOS os `onvio_documents` cujo nome contivesse "ferias", de
    # QUALQUER mês, partia o nome do arquivo em pedaços e chamava o último de "a pessoa". Sem
    # filtro de competência, sem dedup e sem olhar `referente_a_employee_id`, que existe. Quatro
    # arquivos de meses diferentes viravam quatro férias no mesmo kit.
    vistos: set[tuple] = set()
    for nome, ini, fim, st in db.execute(
        text(
            "SELECT e.nome, v.start_date, v.end_date, v.status "
            "  FROM hr_vacation_requests v JOIN employees e ON e.id = v.employee_id "
            " WHERE v.status::text NOT IN ('REJECTED','CANCELLED') "
            "   AND v.start_date <= CAST(:fim AS date) AND v.end_date >= CAST(:ini AS date)"
        ),
        {"ini": comp_ini, "fim": kit_fim},
    ).fetchall():
        if not _pertence(nome, nomes_cond):
            continue
        chave = (_norm(nome), ini, fim)
        if chave in vistos:
            continue
        vistos.add(chave)
        ev.append(
            {
                "tipo": "ferias",
                "auto": True,
                "funcionario": nome.title(),
                "data": ini.isoformat() if ini else None,
                "descricao": f"Férias de {ini:%d/%m} a {fim:%d/%m}" + (f" ({st})" if st else ""),
            }
        )

    # Complemento: aviso de férias no Onvio DA COMPETÊNCIA, só para quem o banco não tem. O nome
    # sai de `referente_a_employee_id` quando existe; o nome do arquivo é o último recurso.
    for nome_arq, emp_nome in db.execute(
        text(
            "SELECT o.nome_arquivo, coalesce(e.nome,'') "
            "  FROM onvio_documents o LEFT JOIN employees e ON e.id = o.referente_a_employee_id "
            " WHERE (o.nome_arquivo ILIKE '%ferias%' OR o.nome_arquivo ILIKE '%férias%') "
            "   AND coalesce(o.mes_ref,'') IN (:comp, :kit)"
        ),
        {"comp": competencia, "kit": f"{km:02d}.{ka}"},
    ).fetchall():
        pessoa = emp_nome or re.split(r"[-_]", nome_arq)[-1].replace(".pdf", "").strip()
        if not _pertence(pessoa, nomes_cond):
            continue
        chave = (_norm(pessoa), None, None)
        if chave in vistos or any(_norm(pessoa) == v[0] for v in vistos):
            continue
        vistos.add(chave)
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
    with open(_path_checklist(competencia, condominio), "w") as _fh:
        json.dump(evs, _fh, ensure_ascii=False, indent=2)
    return novo


def remove_evento(competencia: str, condominio: str, evento_id: str) -> bool:
    evs = eventos_manuais(competencia, condominio)
    novos = [e for e in evs if e.get("id") != evento_id]
    if len(novos) == len(evs):
        return False
    with open(_path_checklist(competencia, condominio), "w") as _fh:
        json.dump(novos, _fh, ensure_ascii=False, indent=2)
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


logger = logging.getLogger(__name__)

_SQL_ASSINATURAS = text("""
    SELECT d.document_name,
           coalesce(e.nome, '') AS funcionario,
           bool_or(r.signer_type::text = 'employee' AND r.status::text IN ('SIGNED','COMPLETED')) AS func_ok,
           bool_or(r.signer_type::text = 'employee' AND r.status::text = 'PENDING')                AS func_pend,
           bool_or(r.signer_type::text = 'company'  AND r.status::text IN ('SIGNED','COMPLETED')) AS emp_ok,
           bool_or(r.signer_type::text = 'company'  AND r.status::text = 'PENDING')                AS emp_pend
      FROM ged_kit_documents d
      JOIN ged_document_kits k ON k.id = d.kit_id
      JOIN ged_clients g       ON g.id = k.client_id
      LEFT JOIN employees e    ON e.id = d.employee_id
      JOIN sig_signature_requests r ON CAST(r.document_id AS TEXT) = CAST(d.id AS TEXT)
     WHERE upper(btrim(g.name)) = upper(btrim(:cond))
       AND k.reference_month = CAST(:ref AS date)
     GROUP BY d.id, d.document_name, e.nome
     ORDER BY coalesce(e.nome,''), d.document_name
""")


def assinaturas_do_kit(db, competencia: str, condominio: str) -> dict:
    """Estado de assinatura de cada documento do kit — a regra 5, que a listagem do Drive não conta.

    10/09/2026 — o Hermes, conferindo o kit do Michelangelo, escreveu no parecer: "Regra 5
    (assinatura) não é verificável pela listagem — aguardando dado". Estava certo: `consultar_kit`
    devolvia nome, id e link de cada arquivo, e o estado da assinatura mora no BANCO. Duas das cinco
    regras que ele confere eram cegas.

    Ele não fingiu que checou — disse que não dava. É por isso que o dado vai até ele, e não o
    contrário.
    """
    mes, ano = competencia.split(".")
    ref = f"{ano}-{int(mes):02d}-01"
    # O nome chega em três línguas: o canônico do `ged_clients`, o do posto e o falado
    # ("MICHELANGELO"). Resolver aqui é o que impede a quarta — e sem isso a consulta devolvia
    # ZERO com dez assinaturas pendentes no banco, que é pior que devolver erro.
    from modules.gedeon.services.kit_layout import nome_pasta_condominio

    alvo = nome_pasta_condominio(condominio) or condominio
    try:
        linhas = db.execute(_SQL_ASSINATURAS, {"cond": alvo, "ref": ref}).mappings().all()
        if not linhas and alvo.strip():
            # nome falado que não resolveu: aceita UM cliente que contenha o termo. Dois ou mais
            # é ambiguidade, e chutar em assinatura é pior do que dizer que não sei.
            cands = (
                db.execute(
                    text("SELECT name FROM ged_clients WHERE upper(name) LIKE '%' || upper(:t) || '%'"),
                    {"t": alvo.strip()},
                )
                .scalars()
                .all()
            )
            if len(cands) == 1:
                linhas = db.execute(_SQL_ASSINATURAS, {"cond": cands[0], "ref": ref}).mappings().all()
    except Exception as exc:  # noqa: BLE001 — a ficha vale sem isto; melhor dizer que não sei
        logger.warning("assinaturas do kit %s %s: %s", condominio, competencia, exc)
        return {"disponivel": False, "motivo": str(exc)[:120]}

    def _estado(ok: bool, pend: bool) -> str:
        return "assinado" if ok else ("pendente" if pend else "—")

    docs = [
        {
            "documento": r["document_name"],
            "funcionario": r["funcionario"] or "—",
            "assinatura_funcionario": _estado(r["func_ok"], r["func_pend"]),
            "assinatura_empresa": _estado(r["emp_ok"], r["emp_pend"]),
        }
        for r in linhas
    ]
    return {
        "disponivel": True,
        "documentos_que_pedem_assinatura": len(docs),
        "funcionario_assinou": sum(1 for d in docs if d["assinatura_funcionario"] == "assinado"),
        "funcionario_pendente": sum(1 for d in docs if d["assinatura_funcionario"] == "pendente"),
        "empresa_assinou": sum(1 for d in docs if d["assinatura_empresa"] == "assinado"),
        "empresa_pendente": sum(1 for d in docs if d["assinatura_empresa"] == "pendente"),
        "por_documento": docs,
    }


def ficha(competencia: str, condominio: str) -> dict:
    """Ficha completa do kit de um condomínio: completude + arquivos + checklist (auto+manual)."""
    from core.database.session import get_sync_db
    from modules.gdrive.services.gdrive_service import gdrive_service
    from modules.gedeon.services import kit_cache

    if not gdrive_service._service:
        gdrive_service.check_status()
    svc = gdrive_service._service
    kit = kit_cache.ler_kit(svc, condominio, competencia) if svc else {}

    # nomes da FOLHA do condomínio (fonte confiável) + alocações → pertinência dos eventos
    folha_nomes = kit_cache.nomes_folha(svc, condominio, competencia) if svc else []
    with get_sync_db() as db:
        nomes_cond = funcionarios_do_condominio(db, competencia, condominio, folha_nomes)
        auto = eventos_auto(db, competencia, condominio, nomes_cond)
        assinaturas = assinaturas_do_kit(db, competencia, condominio)
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
        "assinaturas": assinaturas,
        "tipos_evento": TIPOS_EVENTO,
    }
