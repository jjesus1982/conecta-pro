"""GEDEON — Montagem do kit pela UI: dispara o orquestrador (assíncrono via Celery) +
painel de completude lendo a estrutura real do Drive (subpastas por condomínio).

Mantém o agendamento (dia 28) intacto; isto é o acionamento MANUAL + acompanhamento.
"""

from __future__ import annotations

import threading
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from core.auth.dependencies import get_current_user

router = APIRouter(prefix="/gedeon/kits", tags=["GEDEON — Montagem"])

COMP_RE = r"^(0[1-9]|1[0-2])\.\d{4}$"
_FOLDER_MIME = "application/vnd.google-apps.folder"


BLOCOS_VALIDOS = ["folha", "guias", "pagamentos", "vavt", "rescisao", "cnds", "nfse", "ponto"]


class MontarKitRequest(BaseModel):
    competencia: str | None = None  # MM.YYYY; None = mês anterior (salário em arrears)
    condominios: list[str] | None = None  # None = todos os padrão
    blocos: list[str] | None = None  # None = tudo; subconjunto de BLOCOS_VALIDOS (incremental)


def _competencia_anterior() -> str:
    h = date.today()
    m, a = h.month - 1, h.year
    if m < 1:
        m, a = 12, a - 1
    return f"{m:02d}.{a}"


@router.post("/montagem", summary="Dispara a montagem do kit do mês (assíncrono)")
def montar_kit(req: MontarKitRequest, current_user=Depends(get_current_user)) -> dict:
    """Enfileira o orquestrador (gedeon.montar_kits_mensais) e devolve o task_id p/ acompanhar."""
    from modules.gedeon.tasks.orquestrador_tasks import montar_kits_mensais_task

    comp = req.competencia or _competencia_anterior()
    blocos = req.blocos
    if blocos is not None:
        invalidos = [b for b in blocos if b not in BLOCOS_VALIDOS]
        if invalidos:
            raise HTTPException(status_code=400, detail=f"blocos inválidos: {invalidos}")
        blocos = [b for b in BLOCOS_VALIDOS if b in blocos]  # ordem canônica, dedup
    try:
        # queue explícita = mesma rota do beat (filas usam exchange customizado;
        # .delay() sem queue não casa o binding e a task não é consumida).
        task = montar_kits_mensais_task.apply_async(
            args=[comp, req.condominios, blocos],
            queue="gov.batch",
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Não foi possível enfileirar a montagem: {exc}")
    return {"task_id": task.id, "competencia": comp, "blocos": blocos or "todos", "status": "enfileirado"}


# etapas esperadas (p/ a UI desenhar o progresso antes do resultado chegar)
ETAPAS_ESPERADAS = [
    "onvio_sessao",
    "onvio_sync",
    "onvio_folha_contracheques",
    "onvio_guias",
    "inter",
    "inss_tributario",
    "va_vt",
    "rescisao",
    "cnds",
    "nfse_danfse",
]


@router.get("/montagem/{task_id}", summary="Status da montagem")
def status_montagem(task_id: str, current_user=Depends(get_current_user)) -> dict:
    """Estado da task: PENDING/STARTED/SUCCESS/FAILURE + etapas (ok/erro) quando concluída."""
    from celery.result import AsyncResult

    from celery_app import app

    res = AsyncResult(task_id, app=app)
    out: dict = {"task_id": task_id, "state": res.state, "etapas_esperadas": ETAPAS_ESPERADAS}
    if res.successful():
        rel = res.result if isinstance(res.result, dict) else {}
        etapas = rel.get("etapas", {})
        out["competencia"] = rel.get("competencia")
        out["resumo"] = rel.get("resumo")
        out["etapas"] = {k: {"ok": bool(v.get("ok")), "erro": v.get("erro")} for k, v in etapas.items()}
    elif res.failed():
        out["erro"] = str(res.result)
    else:
        # ainda rodando: lê o progresso ao vivo gravado pelo orquestrador no Redis
        out["progresso"] = _montagem_progresso(task_id)
    out["ponto"] = _ponto_status()  # robô de ponto assinado (host) — status via Redis
    return out


def _montagem_progresso(task_id: str) -> dict:
    """Progresso ao vivo da montagem (etapas em running/ok/erro), escrito pelo orquestrador."""
    try:
        import json
        import os

        import redis

        r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/1"))
        raw = r.get(f"gedeon:montagem:progresso:{task_id}")
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return {"etapas": {}}


def _ponto_status() -> dict:
    """Status do robô de ponto (Sólides) — escrito pelo vigia do host em gedeon:ponto:status."""
    try:
        import json
        import os

        import redis

        r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/1"))
        raw = r.get("gedeon:ponto:status")
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return {"state": "idle"}


def _invalidar_kit(comp: str, cond: str) -> None:
    """Limpa todos os caches do kit após uma mutação (upload/delete) — dado fresco na hora."""
    from modules.gedeon.services import kit_cache

    kit_cache.invalidar(cond, comp)
    _FICHA_CACHE.pop((comp, cond), None)
    _ATLAS_CACHE.pop((comp, cond), None)
    _COMPLETUDE_CACHE.pop(comp, None)


@router.post("/upload", summary="Anexa um arquivo ao kit de um condomínio (upload manual)")
async def upload_kit(
    competencia: str = Form(..., regex=COMP_RE),
    condominio: str = Form(...),
    file: UploadFile = File(...),
    subpasta: str | None = Form(None),  # opcional: força a subpasta; senão classifica pelo nome
    current_user=Depends(get_current_user),
) -> dict:
    """Sobe um arquivo manual (TRCT digitalizado, atestado, ou qualquer doc que não vem do
    Sólides/Onvio/Inter) direto na subpasta certa do kit do condomínio, no Drive."""
    import os
    import tempfile

    from modules.gdrive.services.gdrive_service import gdrive_service
    from modules.gedeon.services.kit_layout import (
        SUBPASTAS,
        _garantir_pasta,
        garantir_pasta_kit,
        pasta_kit_arquivo,
    )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="arquivo vazio")
    nome = os.path.basename(file.filename or "anexo.pdf")

    if not gdrive_service._service:
        gdrive_service.check_status()
    if not gdrive_service._service:
        raise HTTPException(status_code=503, detail="Google Drive não conectado")

    # destino: subpasta forçada (se válida) OU classificada pelo nome do arquivo
    if subpasta and subpasta in SUBPASTAS:
        base = garantir_pasta_kit(condominio, competencia)
        folder = _garantir_pasta({}, subpasta, base) if base else None
    else:
        folder = pasta_kit_arquivo(condominio, competencia, nome)
    if not folder:
        raise HTTPException(status_code=502, detail="não foi possível criar a pasta do kit")

    fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(nome)[1] or ".pdf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        ok = gdrive_service.fazer_upload_arquivo(tmp, folder, nome)
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
    if not ok:
        raise HTTPException(status_code=502, detail="falha no upload ao Drive")
    _invalidar_kit(competencia, condominio)  # ficha/ATLAS/completude refletem o novo anexo
    return {"ok": True, "condominio": condominio, "competencia": competencia, "arquivo": nome, "bytes": len(content)}


@router.delete("/arquivo", summary="Exclui (lixeira) um arquivo do kit de um condomínio")
def excluir_arquivo_kit(
    file_id: str = Query(...),
    condominio: str = Query(...),
    nome: str | None = Query(None),
    competencia: str | None = Query(None, regex=COMP_RE),
    current_user=Depends(get_current_user),
) -> dict:
    """Manda o arquivo pra LIXEIRA do Drive (recuperável). Segurança: só exclui se o arquivo
    estiver mesmo dentro de uma subpasta do kit deste condomínio (e o nome conferir)."""
    from modules.gdrive.services.gdrive_service import gdrive_service
    from modules.gedeon.services.kit_layout import garantir_pasta_kit

    comp = competencia or _competencia_anterior()
    if not gdrive_service._service:
        gdrive_service.check_status()
    svc = gdrive_service._service
    if not svc:
        raise HTTPException(status_code=503, detail="Google Drive não conectado")

    base = garantir_pasta_kit(condominio, comp)
    if not base:
        raise HTTPException(status_code=404, detail="kit do condomínio não encontrado")
    subs = {
        f["id"]
        for f in svc.files()
        .list(
            q=f"'{base}' in parents and trashed=false",
            fields="files(id)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
        .get("files", [])
    }
    try:
        meta = svc.files().get(fileId=file_id, fields="name,parents", supportsAllDrives=True).execute()
    except Exception:
        raise HTTPException(status_code=404, detail="arquivo não encontrado")
    if not (set(meta.get("parents", [])) & subs):
        raise HTTPException(status_code=403, detail="arquivo não pertence ao kit deste condomínio")
    if nome and meta.get("name") != nome:
        raise HTTPException(status_code=400, detail="nome do arquivo não confere")
    svc.files().update(fileId=file_id, body={"trashed": True}, supportsAllDrives=True).execute()
    _invalidar_kit(comp, condominio)  # ficha/ATLAS/completude refletem a remoção
    return {"ok": True, "arquivo": meta.get("name"), "condominio": condominio}


_FICHA_CACHE: dict = {}  # (comp,cond) -> (ts, resultado)
_FICHA_TTL = 60


@router.get("/ficha", summary="Ficha individualizada do kit de um condomínio (montagem ponto-a-ponto)")
def ficha_kit(
    condominio: str = Query(...),
    competencia: str | None = Query(None, regex=COMP_RE),
    refresh: bool = Query(False, description="força reler o Drive (ignora o cache)"),
    current_user=Depends(get_current_user),
) -> dict:
    """Ficha do kit (lê o Drive — pesado). CACHEADO ~60s p/ não sobrecarregar durante montagem."""
    import time

    from modules.gedeon.services.kit_ficha_service import ficha

    comp = competencia or _competencia_anterior()
    chave = (comp, condominio)
    cached = _FICHA_CACHE.get(chave)
    if cached and not refresh and (time.time() - cached[0]) < _FICHA_TTL:
        return {**cached[1], "_cache": True}
    if refresh:  # fura também o cache dos hotspots do Drive (pós-coleta/montagem)
        from modules.gedeon.services import kit_cache

        kit_cache.invalidar(condominio, comp)
    out = ficha(comp, condominio)
    _FICHA_CACHE[chave] = (time.time(), out)
    return out


_ATLAS_CACHE: dict = {}  # (comp,cond) -> (ts, resultado)
_ATLAS_TTL = 90


@router.get("/conferir", summary="ATLAS — conferência automática do kit (selo conferido)")
def conferir_kit_endpoint(
    condominio: str = Query(...),
    competencia: str | None = Query(None, regex=COMP_RE),
    refresh: bool = Query(False, description="força reconferir (ignora o cache)"),
    current_user=Depends(get_current_user),
) -> dict:
    """Confere a COERÊNCIA do kit (nº salários x funcionários, VT/VR por ativo, CNDs
    válidas, ponto/NFS-e/boleto) e devolve o selo 'conferido' ou 'reprovado'. Cacheado ~90s."""
    import time

    from modules.gedeon.services.kit_atlas_service import conferir_kit

    comp = competencia or _competencia_anterior()
    chave = (comp, condominio)
    cached = _ATLAS_CACHE.get(chave)
    if cached and not refresh and (time.time() - cached[0]) < _ATLAS_TTL:
        return {**cached[1], "_cache": True}
    if refresh:
        from modules.gedeon.services import kit_cache

        kit_cache.invalidar(condominio, comp)
    try:
        out = conferir_kit(comp, condominio)
        _ATLAS_CACHE[chave] = (time.time(), out)
        return out
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


_ATLAS_LOTE_CACHE: dict = {}  # comp -> (ts, resultado)
_ATLAS_LOTE_LOCKS: dict = {}  # comp -> Lock (single-flight do lote)


@router.get("/conferir-lote", summary="ATLAS — selo de conferência de TODOS os condomínios (dashboard)")
def conferir_lote_endpoint(
    competencia: str | None = Query(None, regex=COMP_RE),
    refresh: bool = Query(False),
    current_user=Depends(get_current_user),
) -> dict:
    """Confere todos os condomínios de uma vez e devolve só o selo+resumo de cada um —
    p/ o dashboard pintar o selo nos cards sem disparar N chamadas. Cacheado ~90s
    (reusa o kit_cache já aquecido pela completude)."""
    import time

    from modules.gedeon.services.kit_atlas_service import conferir_kit
    from modules.gedeon.services.kit_completude_service import condominios_do_workspace

    comp = competencia or _competencia_anterior()
    cached = _ATLAS_LOTE_CACHE.get(comp)
    if cached and not refresh and (time.time() - cached[0]) < _ATLAS_TTL:
        return {**cached[1], "_cache": True}
    # single-flight por competência (mesmo padrão do /completude): sob navegação
    # concorrente fria, o CIC observou 1×503 transitório aqui — concorrentes agora
    # esperam o lote em voo e reusam.
    lk = _ATLAS_LOTE_LOCKS.setdefault(comp, threading.Lock())
    with lk:
        cached = _ATLAS_LOTE_CACHE.get(comp)
        if cached and not refresh and (time.time() - cached[0]) < _ATLAS_TTL:
            return {**cached[1], "_cache": True}
        selos: dict = {}
        for cond in condominios_do_workspace():
            try:
                r = conferir_kit(comp, cond)
                selos[cond] = {"selo": r["selo"], "resumo": r["resumo"]}
            except Exception as exc:  # um condomínio com erro não derruba o lote
                selos[cond] = {"selo": "indisponivel", "erro": str(exc)}
        out = {"competencia": comp, "selos": selos}
        _ATLAS_LOTE_CACHE[comp] = (time.time(), out)
        return out


class FaturarKitRequest(BaseModel):
    condominio: str
    competencia: str | None = None
    tipo: str = "ambos"  # nfse | boleto | ambos
    confirmar: bool = False  # SEGURANÇA: False = só preview (não emite nada)
    optante_simples: bool = False


@router.post("/faturar", summary="Emitir NFS-e e/ou boleto do kit (confirmar=false → preview)")
async def faturar_kit(req: FaturarKitRequest, current_user=Depends(get_current_user)) -> dict:
    """Fatura o condomínio do kit (NFS-e nativa + boleto Inter). Por SEGURANÇA, sem
    confirmar=true devolve apenas o PREVIEW do que seria emitido — não cria nota/cobrança real."""
    from modules.gedeon.services.kit_faturamento_service import emitir_faturamento

    if req.tipo not in ("nfse", "boleto", "ambos"):
        raise HTTPException(status_code=400, detail="tipo deve ser nfse | boleto | ambos")
    comp = req.competencia or _competencia_anterior()
    try:
        return await emitir_faturamento(
            comp, req.condominio, tipo=req.tipo, confirmar=req.confirmar, optante_simples=req.optante_simples
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/dp/alinhamento", summary="Alinhamento DP — folha do kit x espelho Sólides + afastamentos")
def alinhamento_dp_endpoint(
    condominio: str = Query(...),
    competencia: str | None = Query(None, regex=COMP_RE),
    current_user=Depends(get_current_user),
) -> dict:
    from modules.gedeon.services.kit_dp_service import alinhamento_dp

    return alinhamento_dp(competencia or _competencia_anterior(), condominio)


@router.get("/condominios", summary="Condomínios elegíveis (escala — clients com contrato ativo)")
def condominios_elegiveis_endpoint(current_user=Depends(get_current_user)) -> dict:
    from modules.gedeon.services.kit_dp_service import condominios_elegiveis

    return condominios_elegiveis()


@router.get("/funcionarios", summary="Funcionários da folha do condomínio (p/ a visão por funcionário)")
def listar_funcionarios_endpoint(
    condominio: str = Query(...),
    competencia: str | None = Query(None, regex=COMP_RE),
    current_user=Depends(get_current_user),
) -> dict:
    from modules.gedeon.services.kit_funcionario_service import listar_funcionarios

    return listar_funcionarios(competencia or _competencia_anterior(), condominio)


@router.get("/funcionario", summary="Visão por funcionário (todos os docs de uma pessoa)")
def visao_funcionario_endpoint(
    funcionario: str = Query(...),
    condominio: str | None = Query(None),
    competencia: str | None = Query(None, regex=COMP_RE),
    current_user=Depends(get_current_user),
) -> dict:
    from modules.gedeon.services.kit_funcionario_service import visao_funcionario

    return visao_funcionario(competencia or _competencia_anterior(), funcionario, condominio)


@router.post("/entrega/preparar", summary="Prepara a entrega do kit (gera capa/índice + selo). NÃO envia.")
def preparar_entrega_endpoint(
    condominio: str = Query(...),
    competencia: str | None = Query(None, regex=COMP_RE),
    current_user=Depends(get_current_user),
) -> dict:
    """Gera a capa/índice do kit (com selo ATLAS) e sobe no Drive. O envio ao cliente
    é MANUAL (segurança) — aqui só preparamos e registramos o estado."""
    from modules.gedeon.services.kit_entrega_service import preparar_entrega

    try:
        return preparar_entrega(competencia or _competencia_anterior(), condominio)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


class MarcarEntregueRequest(BaseModel):
    condominio: str
    competencia: str | None = None
    canal: str = "manual"  # whatsapp | email | impresso | manual
    obs: str = ""


@router.post("/entrega/marcar", summary="Marca o kit como entregue ao cliente (entrega manual)")
def marcar_entregue_endpoint(req: MarcarEntregueRequest, current_user=Depends(get_current_user)) -> dict:
    from modules.gedeon.services.kit_entrega_service import marcar_entregue

    autor = getattr(current_user, "email", None) or getattr(current_user, "username", None)
    return marcar_entregue(
        req.competencia or _competencia_anterior(), req.condominio, canal=req.canal, obs=req.obs, autor=autor
    )


@router.get("/entrega/status", summary="Status de entrega do kit (não_preparado/preparado/entregue)")
def status_entrega_endpoint(
    condominio: str = Query(...),
    competencia: str | None = Query(None, regex=COMP_RE),
    current_user=Depends(get_current_user),
) -> dict:
    from modules.gedeon.services.kit_entrega_service import status_entrega

    return status_entrega(competencia or _competencia_anterior(), condominio)


@router.get("/assinaturas", summary="Pendências de assinatura (quem não assinou VT/VR no Sólides)")
def pendencias_assinatura_endpoint(
    condominio: str | None = Query(None),
    competencia: str | None = Query(None, regex=COMP_RE),
    current_user=Depends(get_current_user),
) -> dict:
    """Lista, por condomínio, quem está na folha mas ainda não tem o recibo de VT/VR
    assinado no Sólides — p/ a Pyetra cobrar antes de fechar o kit."""
    from modules.gedeon.services.kit_assinatura_service import pendencias_assinatura

    return pendencias_assinatura(competencia or _competencia_anterior(), condominio)


class EventoChecklist(BaseModel):
    competencia: str | None = None
    condominio: str
    tipo: str
    descricao: str
    funcionario: str | None = None
    data: str | None = None


@router.post("/checklist", summary="Adiciona um evento manual ao checklist do condomínio")
def add_checklist(req: EventoChecklist, current_user=Depends(get_current_user)) -> dict:
    from modules.gedeon.services.kit_ficha_service import TIPOS_EVENTO, add_evento

    if req.tipo not in TIPOS_EVENTO:
        raise HTTPException(status_code=400, detail=f"tipo inválido (use {TIPOS_EVENTO})")
    comp = req.competencia or _competencia_anterior()
    autor = getattr(current_user, "email", None) or getattr(current_user, "username", None)
    return add_evento(comp, req.condominio, req.tipo, req.descricao, req.funcionario, req.data, autor)


@router.delete("/checklist", summary="Remove um evento manual do checklist")
def del_checklist(
    condominio: str = Query(...),
    evento_id: str = Query(...),
    competencia: str | None = Query(None, regex=COMP_RE),
    current_user=Depends(get_current_user),
) -> dict:
    from modules.gedeon.services.kit_ficha_service import remove_evento

    ok = remove_evento(competencia or _competencia_anterior(), condominio, evento_id)
    if not ok:
        raise HTTPException(status_code=404, detail="evento não encontrado")
    return {"ok": True}


_COMPLETUDE_CACHE: dict = {}  # competencia -> (timestamp, resultado)
# 10 min: ler o Drive frio custa ~30s e travava a dashboard do GED a cada 90s.
# Mutações via API (upload/delete/montagem) invalidam na hora (_invalidar_kit);
# escrita externa (robôs direto no Drive) aparece em até 10 min ou no botão
# "Atualizar" da tela (refresh=true).
_COMPLETUDE_TTL = 600  # segundos
_COMPLETUDE_LOCKS: dict = {}  # competencia -> Lock (single-flight da varredura do Drive)


@router.get("/completude", summary="Completude REAL dos kits + checklist (lê o Drive)")
def completude_kits_endpoint(
    competencia: str | None = Query(None, regex=COMP_RE, examples=["05.2026"]),
    refresh: bool = Query(False, description="força reler o Drive (ignora o cache)"),
    current_user=Depends(get_current_user),
) -> dict:
    """% de montagem por condomínio calculado da estrutura real do Drive, com o
    checklist do que cada kit deve conter (folha, ponto, guias, CNDs, NFS-e...).
    Sem `competencia` usa o mês anterior. CACHEADO ~90s (ler o Drive é pesado; sem cache,
    abrir a dashboard durante uma montagem sobrecarrega o backend). `refresh=true` força reler."""
    import time

    from modules.gedeon.services.kit_completude_service import completude_kits

    comp = competencia or _competencia_anterior()
    cached = _COMPLETUDE_CACHE.get(comp)
    if cached and not refresh and (time.time() - cached[0]) < _COMPLETUDE_TTL:
        return {**cached[1], "_cache": True}
    if refresh:
        from modules.gedeon.services import kit_cache

        kit_cache.invalidar(competencia=comp)
    # SINGLE-FLIGHT por competência: N abas/usuários abrindo a dashboard fria
    # disparavam N varreduras completas do Drive em paralelo — já derrubou o
    # backend (restart 16/07 com 2 navegações simultâneas). Concorrentes esperam
    # a varredura em voo e reusam o resultado.
    lk = _COMPLETUDE_LOCKS.setdefault(comp, threading.Lock())
    with lk:
        cached = _COMPLETUDE_CACHE.get(comp)
        if cached and not refresh and (time.time() - cached[0]) < _COMPLETUDE_TTL:
            return {**cached[1], "_cache": True}
        try:
            out = completude_kits(comp)
            _COMPLETUDE_CACHE[comp] = (time.time(), out)
            return out
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))


def _eh_util(d: date) -> bool:
    return d.weekday() < 5  # seg-sex (sem feriados municipais)


def _nesimo_dia_util(ano: int, mes: int, n: int) -> date:
    from datetime import timedelta

    d, cont = date(ano, mes, 1), 0
    while True:
        if _eh_util(d):
            cont += 1
            if cont >= n:
                return d
        d += timedelta(days=1)


def _mais_dias_uteis(d: date, n: int) -> date:
    from datetime import timedelta

    while n > 0:
        d += timedelta(days=1)
        if _eh_util(d):
            n -= 1
    return d


@router.get("/cronograma", summary="Cronograma do mês: quando cada documento deve estar pronto")
def cronograma(
    competencia: str | None = Query(None, regex=COMP_RE, examples=["05.2026"]),
    current_user=Depends(get_current_user),
) -> dict:
    """Datas-chave da rotina (no mês de entrega = competência + 1): salário no 5º dia útil
    → contracheques p/ assinatura (48h); VT/VR no dia 16 → recibos p/ assinatura (48h).
    Permite montar o kit conforme cada bloco fica pronto, sem deixar p/ a última hora."""
    from datetime import timedelta

    comp = competencia or _competencia_anterior()
    m, a = int(comp[:2]), int(comp[3:])
    # mês de entrega/pagamento = competência + 1 (salário em arrears)
    rm, ra = (m + 1, a) if m < 12 else (1, a + 1)

    d5 = _nesimo_dia_util(ra, rm, 5)  # pagamento de salários
    d_env_cc = _mais_dias_uteis(d5, 1)  # envio dos contracheques p/ assinatura
    assin_cc = d_env_cc + timedelta(days=2)  # 48h p/ assinar
    d16 = date(ra, rm, 16)  # pagamento VT/VR
    d_env_vavt = date(ra, rm, 17)  # envio dos recibos VT/VR p/ assinatura
    assin_vavt = d_env_vavt + timedelta(days=2)
    hoje = date.today()

    def passo(titulo, data, blocos, prazo=None, obs=None):
        return {
            "titulo": titulo,
            "data": data.isoformat() if data else None,
            "prazo": prazo.isoformat() if prazo else None,
            "blocos": blocos,
            "obs": obs,
            "vencido": bool(data and data < hoje),
        }

    etapas = [
        passo("Folha e contracheques disponíveis", d5, ["folha"], obs="Sai junto com o fechamento da folha (Onvio)."),
        passo(
            "Salários pagos (Banco Inter)",
            d5,
            ["pagamentos"],
            obs="Até o 5º dia útil. Gera os comprovantes de salário + INSS + boletos.",
        ),
        passo(
            "Folha de ponto enviada p/ assinatura (Sólides)",
            d_env_cc,
            ["ponto"],
            prazo=assin_cc,
            obs="Funcionários têm 48h. Depois, buscar os assinados (folha de ponto).",
        ),
        passo(
            "Guias e impostos (FGTS, DCTFWeb, INSS)", None, ["guias"], obs="Conforme o contador disponibiliza no Onvio."
        ),
        passo("VT/VR pagos", d16, ["vavt"], obs="Dia 16. Gera os comprovantes de VT/VR (Inter)."),
        passo(
            "Recibos de VT/VR enviados p/ assinatura (Sólides)",
            d_env_vavt,
            ["vavt", "ponto"],
            prazo=assin_vavt,
            obs="48h p/ assinar. Os recibos assinados vêm do GED do Sólides.",
        ),
        passo("Notas fiscais e boletos", None, ["nfse"], obs="Conforme as NFS-e do mês são emitidas."),
        passo("Certidões (CNDs)", None, ["cnds"], obs="Validade de meses — atualizar quando vencer."),
    ]
    return {
        "competencia": comp,
        "mes_entrega": f"{rm:02d}.{ra}",
        "hoje": hoje.isoformat(),
        "etapas": etapas,
    }


@router.get("/painel", summary="Painel de completude dos kits (lê o Drive)")
def painel_kits(
    competencia: str = Query(..., regex=COMP_RE, examples=["05.2026"]),
    current_user=Depends(get_current_user),
) -> dict:
    """Para cada condomínio: contagem de docs por subpasta + link do Drive."""
    from modules.gdrive.services.gdrive_service import gdrive_service
    from modules.gedeon.services.kit_layout import SUBPASTAS, garantir_pasta_kit, mes_kit_de_competencia
    from modules.gedeon.services.kit_orchestrator import CONDOMINIOS_PADRAO

    if not gdrive_service._service:
        gdrive_service.check_status()
    svc = gdrive_service._service
    if not svc:
        raise HTTPException(status_code=503, detail="Google Drive não conectado")

    def _list(parent_id: str, extra: str = "") -> list[dict]:
        q = f"'{parent_id}' in parents and trashed=false" + extra
        return (
            svc.files()
            .list(
                q=q,
                fields="files(id,name,mimeType)",
                pageSize=300,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
            .get("files", [])
        )

    condominios = []
    for cond in CONDOMINIOS_PADRAO:
        base = garantir_pasta_kit(cond, competencia)
        link, subs, total = None, [], 0
        if base:
            try:
                meta = svc.files().get(fileId=base, fields="webViewLink", supportsAllDrives=True).execute()
                link = meta.get("webViewLink")
            except Exception:
                pass
            folders = {f["name"]: f["id"] for f in _list(base) if f["mimeType"] == _FOLDER_MIME}
            for sp in SUBPASTAS:
                fid = folders.get(sp)
                n = len([x for x in _list(fid) if x["mimeType"] != _FOLDER_MIME]) if fid else 0
                subs.append({"nome": sp, "docs": n})
                total += n
        condominios.append(
            {
                "condominio": cond,
                "total": total,
                "subpastas": subs,
                "drive_link": link,
            }
        )
    return {
        "competencia": competencia,
        "mes_kit": mes_kit_de_competencia(competencia),
        "condominios": condominios,
    }
