"""GEDEON — Emissão de CND pela UI: o funcionário dispara a emissão real (robô host via
ponte Redis), acompanha o status e baixa o PDF. Atualiza ged_certidoes (validade real).
"""

from __future__ import annotations

import datetime
import json
import os
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.auth.dependencies import get_current_user

router = APIRouter(prefix="/gedeon/cnd", tags=["GEDEON — CND"])

CNPJ_EMPRESA = os.getenv("NFSE_MANAUS_CNPJ", "35710481000103")
# portais com emissão automática FUNCIONANDO (Federal/Caixa = manual-assistido)
PORTAIS_OK = ["sefaz_am", "cndt", "prefeitura"]
PORTAIS_MANUAIS = ["federal", "caixa"]
DOCTYPE = {
    "sefaz_am": "certidao_negativa_estadual",
    "cndt": "certidao_negativa_trabalhista",
    "prefeitura": "certidao_negativa_municipal",
    "federal": "certidao_negativa_federal",
    "caixa": "certidao_negativa_fgts",
}
# portais sem emissão automática → o funcionário emite no portal oficial e sobe o PDF
PORTAL_OFICIAL = {
    "certidao_negativa_federal": {
        "nome": "CND Federal (Receita/PGFN)",
        "url": "https://servicos.receitafederal.gov.br/servico/certidoes",
    },
    "certidao_negativa_fgts": {
        "nome": "CRF — FGTS (Caixa)",
        # a raiz /consultacrf/ dá Forbidden (WAF); a página real é consultaEmpregador.jsf
        # (com o CNPJ já pré-preenchido p/ o funcionário só clicar em Consultar)
        "url": f"https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf?cnpj={CNPJ_EMPRESA}",
    },
}
VALIDADE_PADRAO = {"certidao_negativa_federal": 180, "certidao_negativa_fgts": 30}


class EmitirCNDRequest(BaseModel):
    cnpj: str | None = None
    portais: list[str] | None = None  # None = todos os que funcionam


def _redis():
    import redis

    return redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/1"))


@router.post("/emitir", summary="Dispara a emissão real das CNDs (assíncrono via robô)")
def emitir_cnd(req: EmitirCNDRequest, current_user=Depends(get_current_user)) -> dict:
    cnpj = req.cnpj or CNPJ_EMPRESA
    portais = req.portais or PORTAIS_OK
    portais = [p for p in portais if p in DOCTYPE]
    if not portais:
        raise HTTPException(status_code=400, detail="nenhum portal válido")
    try:
        r = _redis()
        r.set("gedeon:cnd:request", json.dumps({"cnpj": cnpj, "portais": portais}), ex=1800)
        r.set("gedeon:cnd:status", json.dumps({"state": "enfileirado", "cnpj": cnpj}), ex=1800)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"não foi possível enfileirar: {exc}")
    return {"status": "enfileirado", "cnpj": cnpj, "portais": portais}


@router.get("/status", summary="Status da emissão + CNDs registradas")
def status_cnd(current_user=Depends(get_current_user)) -> dict:
    from sqlalchemy import text

    from core.database.session import get_sync_db

    out: dict = {"emissao": {"state": "idle"}, "certidoes": [], "manuais": PORTAL_OFICIAL}
    try:
        raw = _redis().get("gedeon:cnd:status")
        if raw:
            out["emissao"] = json.loads(raw)
    except Exception:
        pass
    # CNDs atuais (as 3 automáticas) do banco
    try:
        with get_sync_db() as db:
            rows = db.execute(
                text(
                    "SELECT document_type, name, issuing_body, issue_date, expiry_date, "
                    "notes, alerta_ativo, file_path FROM ged_certidoes "
                    "WHERE document_type = ANY(:dts) ORDER BY document_type"
                ),
                {"dts": list(DOCTYPE.values())},
            ).fetchall()
            for r in rows:
                notes = {}
                try:
                    notes = json.loads(r[5]) if r[5] else {}
                except Exception:
                    pass
                out["certidoes"].append(
                    {
                        "document_type": r[0],
                        "name": r[1],
                        "orgao": r[2],
                        "emissao": str(r[3]) if r[3] else None,
                        "validade": str(r[4]) if r[4] else None,
                        "situacao": notes.get("situacao"),
                        "alerta": r[6],
                        "tem_pdf": bool(r[7]),
                    }
                )
    except Exception:
        pass
    return out


def _extrair_validade(txt: str):
    """Lê a validade do PDF. Trata intervalo do CRF/FGTS ('Validade: 07/06/2026 a
    06/07/2026' → pega a data FINAL) e o 'Válida até DD/MM/AAAA' da Federal."""
    txt = txt or ""
    # intervalo "validade ... DD/MM/AAAA a/até/- DD/MM/AAAA" → data final
    m = re.search(r"validade[:\s]*?\d{2}/\d{2}/\d{4}\s*(?:a|at[ée]|-)\s*(\d{2}/\d{2}/\d{4})", txt, re.I)
    if not m:
        m = re.search(r"(?:v[áa]lid[ao]\s+at[ée]|validade)[:\s]*?(\d{2}/\d{2}/\d{4})", txt, re.I)
    if m:
        try:
            return datetime.datetime.strptime(m.group(1), "%d/%m/%Y").date()
        except Exception:
            return None
    return None


def _classificar(txt: str):
    t = (txt or "").upper()
    if "EFEITO DE NEGATIVA" in t or "POSITIVA COM EFEITO" in t:
        return True, "positiva_com_efeito_negativa"
    if "NEGATIVA" in t and "POSITIVA" not in t:
        return True, "negativa"
    if "REGULARIDADE" in t or "REGULAR" in t:  # CRF FGTS diz "regularidade"
        return True, "regular"
    if "POSITIVA" in t:
        return False, "positiva"
    return None, "indeterminado"


@router.post("/upload", summary="Sobe o PDF de uma CND emitida manualmente (Federal/FGTS)")
async def upload_cnd(
    document_type: str = Form(...),
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
) -> dict:
    """Registra a CND emitida manualmente: salva o PDF, lê validade/situação, grava em
    ged_certidoes e replica no kit. Mesmo destino das automáticas."""
    if document_type not in PORTAL_OFICIAL:
        raise HTTPException(status_code=400, detail="document_type inválido p/ upload manual")
    content = await file.read()
    if content[:4] != b"%PDF":
        raise HTTPException(status_code=400, detail="arquivo não é um PDF")

    portal_key = {v: k for k, v in DOCTYPE.items()}.get(document_type, document_type)
    os.makedirs("/app/uploads/cnds", exist_ok=True)
    path = f"/app/uploads/cnds/{portal_key}_manual.pdf"
    with open(path, "wb") as fh:
        fh.write(content)

    # lê texto p/ validade + situação
    txt = ""
    try:
        import fitz

        txt = "\n".join(p.get_text() for p in fitz.open(stream=content, filetype="pdf"))
    except Exception:
        pass
    regular, situacao = _classificar(txt)
    validade = _extrair_validade(txt)
    if validade is None:
        validade = datetime.date.today() + datetime.timedelta(days=VALIDADE_PADRAO.get(document_type, 90))

    from sqlalchemy import text

    from core.database.session import get_sync_db

    notes = '{"situacao": "%s", "fonte": "upload manual (Conecta PRO)"}' % situacao
    with get_sync_db() as db:
        body = PORTAL_OFICIAL[document_type]["nome"]
        row = db.execute(
            text("SELECT id FROM ged_certidoes WHERE document_type=:dt LIMIT 1"), {"dt": document_type}
        ).fetchone()
        if row:
            db.execute(
                text(
                    "UPDATE ged_certidoes SET expiry_date=:v, issue_date=:i, file_path=:f, "
                    "notes=:n, issuing_body=:b, alerta_ativo=:a, updated_at=now() WHERE id=:id"
                ),
                {
                    "v": validade,
                    "i": datetime.date.today(),
                    "f": path,
                    "n": notes,
                    "b": body,
                    "a": regular is not True,
                    "id": row[0],
                },
            )
        else:
            db.execute(
                text(
                    "INSERT INTO ged_certidoes (id,name,document_type,issuing_body,issue_date,"
                    "expiry_date,file_path,notes,alerta_ativo,created_at,updated_at) VALUES "
                    "(gen_random_uuid(),:nm,:dt,:b,:i,:v,:f,:n,:a,now(),now())"
                ),
                {
                    "nm": body,
                    "dt": document_type,
                    "b": body,
                    "i": datetime.date.today(),
                    "v": validade,
                    "f": path,
                    "n": notes,
                    "a": regular is not True,
                },
            )
        db.commit()

    # replica no kit do mês corrente
    try:
        from modules.gedeon.services.cnd_kit_service import arquivar_cnds
        from modules.gedeon.services.kit_orchestrator import CONDOMINIOS_PADRAO

        h = datetime.date.today()
        m, a = (h.month - 1, h.year) if h.month > 1 else (12, h.year - 1)
        arquivar_cnds(f"{m:02d}.{a}", CONDOMINIOS_PADRAO, dry_run=False)
    except Exception:
        pass

    return {
        "ok": True,
        "document_type": document_type,
        "situacao": situacao,
        "validade": str(validade) if validade else None,
    }


@router.get("/pdf/{document_type}", summary="Baixa o PDF da CND")
def baixar_pdf(document_type: str, current_user=Depends(get_current_user)):
    from sqlalchemy import text

    from core.database.session import get_sync_db

    with get_sync_db() as db:
        row = db.execute(
            text("SELECT file_path, name FROM ged_certidoes WHERE document_type=:dt LIMIT 1"), {"dt": document_type}
        ).fetchone()
    if not row or not row[0] or not os.path.exists(row[0]):
        raise HTTPException(status_code=404, detail="PDF não encontrado — emita a CND primeiro")
    return FileResponse(row[0], media_type="application/pdf", filename=f"{document_type}.pdf")
