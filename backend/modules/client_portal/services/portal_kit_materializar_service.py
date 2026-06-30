"""Onda 2 — Materializa os documentos LOCAIS no kit do portal.

Os robôs já baixaram os arquivos no servidor (/app/uploads/ponto, /solides_ged, /onvio).
Este serviço os INDEXA em ged_document_kits + ged_kit_documents com file_path REAL, mapeando
cada documento → condomínio (ged_client) pelo mesmo escopo-por-nome do Raio-X
(employee → allocations(active) → posts(match nome) → condominios → clients → CNPJ → ged_clients).

NÃO espelha o Drive: a fonte são os arquivos locais. Idempotente (pula file_path já indexado).
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import date

from sqlalchemy import text

from modules.client_portal.services.portal_operacao_service import _norm, ALIAS_POSTO  # reusa normalização

PONTO_DIR = "/app/uploads/ponto"
SOLIDES_DIR = "/app/uploads/solides_ged"
ONVIO_DIR = "/app/uploads/onvio"

GENERICOS = {"CONDOMINIO", "RESIDENCIAL", "VILLAGE", "VILLA", "EDIFICIO", "DA", "DE", "DO", "DOS", "DAS", "CIDADE"}


def _mapa_funcionarios(db) -> dict:
    """Constrói: emp_id→ged_client_id, nome_norm→emp_id (via escopo-por-nome do Raio-X)."""
    posts = db.execute(text("SELECT id, name, client_id FROM posts")).mappings().all()
    geds = db.execute(
        text(
            """SELECT g.id AS gid, g.name AS gnome, g.cnpj, c.id AS cliente_id, cond.nome AS cond_nome
               FROM ged_clients g
               LEFT JOIN clients c ON regexp_replace(c.document_number,'[^0-9]','','g')
                                    = regexp_replace(COALESCE(g.cnpj,''),'[^0-9]','','g') AND g.cnpj IS NOT NULL
               LEFT JOIN condominios cond ON cond.client_id=c.id"""
        )
    ).mappings().all()
    # post_id → ged_client_id
    post2ged: dict = {}
    for g in geds:
        cond_nome = g["cond_nome"] or g["gnome"]
        toks = [t for t in _norm(cond_nome).split() if len(t) > 3 and t not in GENERICOS]
        alias = ALIAS_POSTO.get(_norm(cond_nome))
        for p in posts:
            pn = _norm(p["name"])
            if (g["cliente_id"] and str(p["client_id"] or "") == str(g["cliente_id"])) \
               or (alias and alias.upper() in pn) or any(t in pn for t in toks):
                post2ged[str(p["id"])] = str(g["gid"])
    # emp → ged via allocations active
    emp2ged: dict = {}
    nome2emp: dict = {}
    rows = db.execute(
        text(
            """SELECT DISTINCT e.id, e.nome, a.post_id FROM allocations a
               JOIN employees e ON e.id=a.employee_id WHERE a.status='active'"""
        )
    ).mappings().all()
    for r in rows:
        gid = post2ged.get(str(r["post_id"]))
        if gid:
            emp2ged[str(r["id"])] = gid
        nome2emp[_norm(r["nome"])] = str(r["id"])
    # índice de tokens por ged_client (p/ casar nome de CONDOMÍNIO no arquivo onvio)
    ged_tokens: dict = {}
    for g in geds:
        cond_nome = g["cond_nome"] or g["gnome"]
        toks = {t for t in _norm(cond_nome).split() if len(t) > 3 and t not in GENERICOS}
        if toks:
            ged_tokens[str(g["gid"])] = toks
    return {"emp2ged": emp2ged, "nome2emp": nome2emp, "ged_tokens": ged_tokens}


def _ged_por_condominio(texto: str, mapa: dict) -> str | None:
    """Casa um texto (nome de arquivo onvio) ao ged_client pelo nome do condomínio."""
    palavras = set(_norm(texto).split())
    melhor, mx = None, 0
    for gid, toks in mapa["ged_tokens"].items():
        inter = len(toks & palavras)
        if inter > mx:
            melhor, mx = gid, inter
    return melhor


def _ged_por_nome(nome: str, mapa: dict) -> tuple[str | None, str | None]:
    """nome do funcionário → (emp_id, ged_client_id) por subconjunto de tokens."""
    alvo = set(_norm(nome).split())
    alvo = {t for t in alvo if len(t) > 2}
    if not alvo:
        return None, None
    for nome_norm, emp_id in mapa["nome2emp"].items():
        b = set(nome_norm.split())
        if alvo <= b or b <= alvo:
            return emp_id, mapa["emp2ged"].get(emp_id)
    return None, None


def _kit_id(db, client_id: str, ref_month: date, cache: dict) -> str:
    """Find-or-create ged_document_kit (client_id, reference_month)."""
    key = (client_id, ref_month.isoformat())
    if key in cache:
        return cache[key]
    kid = db.execute(
        text("SELECT id FROM ged_document_kits WHERE client_id=:c AND reference_month=:m"),
        {"c": client_id, "m": ref_month},
    ).scalar()
    if not kid:
        import uuid

        kid = str(uuid.uuid4())
        db.execute(
            text(
                """INSERT INTO ged_document_kits (id, client_id, reference_month, status, total_documents,
                       documents_signed, completion_percentage, created_at, updated_at)
                   VALUES (:id,:c,:m,'em_montagem',0,0,0,NOW(),NOW())"""
            ),
            {"id": kid, "c": client_id, "m": ref_month},
        )
    cache[key] = str(kid)
    return str(kid)


def _ja_indexado(db, file_path: str) -> bool:
    return bool(db.execute(text("SELECT 1 FROM ged_kit_documents WHERE file_path=:f LIMIT 1"), {"f": file_path}).scalar())


def _inserir_doc(db, kit_id: str, emp_id: str | None, tipo: str, nome: str, file_path: str, assinado: bool, origem: str):
    import uuid

    size = os.path.getsize(file_path) if os.path.exists(file_path) else None
    mime = "text/html" if file_path.endswith(".html") else "application/pdf"
    db.execute(
        text(
            """INSERT INTO ged_kit_documents (id, kit_id, employee_id, document_type, document_name, file_path,
                   file_size_bytes, mime_type, is_signed, source_module, auto_generated, created_at, updated_at)
               VALUES (:id,:kit,:emp,:tipo,:nome,:fp,:sz,:mime,:sig,:org,true,NOW(),NOW())"""
        ),
        {"id": str(uuid.uuid4()), "kit": kit_id, "emp": emp_id, "tipo": tipo, "nome": nome,
         "fp": file_path, "sz": size, "mime": mime, "sig": assinado, "org": origem},
    )


def materializar(competencia_default: str = "2026-06") -> dict:
    """Indexa os arquivos locais nos kits do portal. competencia_default p/ docs sem mês próprio."""
    from core.database.session import get_sync_db

    ref_default = date(int(competencia_default.split("-")[0]), int(competencia_default.split("-")[1]), 1)
    stats = {"ponto": 0, "solides": 0, "onvio": 0, "sem_cliente": 0, "ja_indexado": 0}
    cache_kit: dict = {}

    with get_sync_db() as db:
        mapa = _mapa_funcionarios(db)

        # 1) PONTO — /ponto/<emp_id>/<MM.YYYY>/*.html (mapeia limpo)
        if os.path.isdir(PONTO_DIR):
            for emp_id in os.listdir(PONTO_DIR):
                gid = mapa["emp2ged"].get(emp_id)
                base = os.path.join(PONTO_DIR, emp_id)
                if not os.path.isdir(base):
                    continue
                if not gid:
                    stats["sem_cliente"] += 1
                    continue
                for mes in os.listdir(base):
                    m = re.match(r"(\d{2})\.(\d{4})", mes)
                    ref = date(int(m.group(2)), int(m.group(1)), 1) if m else ref_default
                    mdir = os.path.join(base, mes)
                    if not os.path.isdir(mdir):
                        continue
                    for fn in os.listdir(mdir):
                        fp = os.path.join(mdir, fn)
                        if not os.path.isfile(fp):
                            continue
                        if _ja_indexado(db, fp):
                            stats["ja_indexado"] += 1
                            continue
                        kit = _kit_id(db, gid, ref, cache_kit)
                        _inserir_doc(db, kit, emp_id, "ponto", f"Folha de Ponto {mes}", fp, True, "dp")
                        stats["ponto"] += 1

        # 2) SOLIDES — manifesto (assinados)
        mpath = os.path.join(SOLIDES_DIR, "manifesto.json")
        if os.path.exists(mpath):
            TIPO_LABEL = {"vale_vt_vr": "Recibo VT/VR Assinado", "ferias": "Recibo de Férias Assinado",
                          "decimo_terceiro": "Recibo 13º Assinado"}
            for d in json.load(open(mpath)):
                fp = os.path.join(SOLIDES_DIR, d["arquivo"])
                if not os.path.exists(fp):
                    continue
                if _ja_indexado(db, fp):
                    stats["ja_indexado"] += 1
                    continue
                emp_id, gid = _ged_por_nome(d["funcionario"], mapa)
                if not gid:
                    stats["sem_cliente"] += 1
                    continue
                kit = _kit_id(db, gid, ref_default, cache_kit)
                _inserir_doc(db, kit, emp_id, d["tipo"], TIPO_LABEL.get(d["tipo"], d.get("label", d["tipo"])), fp, True, "gedeon")
                stats["solides"] += 1

        # 3) ONVIO — /onvio/<tipo>/<MM.YYYY>/<arquivo>. Nome do arquivo = condomínio OU funcionário.
        if os.path.isdir(ONVIO_DIR):
            for tipo in os.listdir(ONVIO_DIR):
                tdir = os.path.join(ONVIO_DIR, tipo)
                if not os.path.isdir(tdir) or tipo.startswith("_"):
                    continue
                for mes in os.listdir(tdir):
                    mdir = os.path.join(tdir, mes)
                    if not os.path.isdir(mdir):
                        continue
                    m = re.match(r"(\d{2})\.(\d{4})", mes)
                    ref = date(int(m.group(2)), int(m.group(1)), 1) if m else ref_default
                    for fn in os.listdir(mdir):
                        fp = os.path.join(mdir, fn)
                        if not os.path.isfile(fp):
                            continue
                        if _ja_indexado(db, fp):
                            stats["ja_indexado"] += 1
                            continue
                        base = re.sub(r"\.(pdf|html?|xml)$", "", fn, flags=re.I)
                        base = re.sub(r"\d{2}\.\d{4}", " ", base).replace("_", " ")
                        if "geral" in _norm(base) or "conecta mais" in _norm(base):
                            stats["sem_cliente"] += 1  # docs gerais (escritório) não vão pro kit do cliente
                            continue
                        # tenta condomínio primeiro (folha/guias), depois funcionário (contracheque)
                        gid = _ged_por_condominio(base, mapa)
                        emp_id = None
                        if not gid:
                            emp_id, gid = _ged_por_nome(base, mapa)
                        if not gid:
                            stats["sem_cliente"] += 1
                            continue
                        kit = _kit_id(db, gid, ref, cache_kit)
                        assinado = tipo in ("contracheque", "recibo_folha", "ferias")
                        _inserir_doc(db, kit, emp_id, tipo, tipo.replace("_", " ").title(), fp, assinado, "fiscal")
                        stats["onvio"] += 1

        # 4) recomputa totais de cada kit tocado
        for kit_id in set(cache_kit.values()):
            db.execute(
                text(
                    """UPDATE ged_document_kits k SET
                         total_documents = (SELECT COUNT(*) FROM ged_kit_documents WHERE kit_id=k.id),
                         documents_signed = (SELECT COUNT(*) FROM ged_kit_documents WHERE kit_id=k.id AND is_signed),
                         updated_at = NOW()
                       WHERE k.id=:kid"""
                ),
                {"kid": kit_id},
            )
        db.commit()
    stats["kits_tocados"] = len(cache_kit)
    return stats
