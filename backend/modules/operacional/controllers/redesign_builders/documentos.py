"""Documentos/GED (T1) — override do _build_documentos + telas kits e pastas (leitura real).

A completude do kit vem do GOOGLE DRIVE, não do banco — decisão do Jordan em 15/08/2026.
Ver o comentário em `_visao()` para os números que motivaram.
"""

import asyncio
import logging
import os
import re
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.controllers.redesign_data_controller import (
    IC,
    S,
    _helpers,
    _scalar,
    b,
    doc,
    t,
)

# Espelho FECHADO de `modules/gedeon/services/consultor_service.py:24`
# (AREAS_VALIDAS = {montagem, checklist, intercorrencias, folha}). Existe como constante única
# porque DOIS forms deste arquivo mandam `area` para o mesmo validador — duplicar a lista era
# como as duas divergirem do backend ao mesmo tempo. Mudou lá? muda aqui, e o oráculo
# test_oraculo_area_consultor_gedeon.py fica vermelho até alguém mudar.
_AREAS_GEDEON = [
    ("montagem", "Montagem do kit"),
    ("checklist", "Checklist do kit"),
    ("intercorrencias", "Intercorrências do mês"),
    ("folha", "Folha da competência"),
]
_CAMPOS_AREA_GEDEON = [
    {
        "key": "area",
        "label": "Área*",
        "type": "select",
        "span": "span 1",
        "value": "checklist",  # o ModuleView semeia o estado com `value` — sem isto o select abre vazio
        "options": [{"value": v, "label": lbl} for v, lbl in _AREAS_GEDEON],
    }
]


def _chip_ver_documento(doc_id, file_path, mime_type, nome=None) -> list:
    """Chip «Ver documento» de UMA linha de `ged_kit_documents` — habilitado só quando abre.

    Medido em 28/09/2026 sobre os 6.024 documentos da tabela, e é a razão de o chip ser
    condicional em vez de otimista (chip que promete e dá erro custa mais que chip cinza):

      · 3.365 caminho local que EXISTE em disco  → abre
      ·   430 caminho local que NÃO existe (416 relativos resolvidos contra GED_STORAGE_BASE
              =/opt/conecta-pro/storage/ged, diretório que não existe nem no contêiner nem no
              host, + 14 absolutos apagados) → cinza
      · 1.862 sem `file_path` (registro existe, arquivo nunca chegou) → cinza
      ·   323 URL do Google Drive → cinza: a rota responde 307 e o `fetch` com Bearer do
              `lib/pdf.ts` morre no CORS do redirect cross-origin
      ·    44 `/inter/*` (comprovante bancário) → cinza, vai pelo Financeiro

    `fmt` sai do mime REAL: 138 destes documentos são `text/html` (folha de ponto gerada), e
    prometer PDF para eles seria a mesma mentira em outra ponta.
    """
    from modules.people_management.ged.services.document_collector_service import GED_STORAGE_BASE

    url = f"/api/v1/people-management/ged/documents/{doc_id}/download"
    fp = (file_path or "").strip()
    if not fp:
        return [doc("Ver documento", disabled=True, motivo="Sem arquivo: o registro existe, o arquivo não")]
    if fp.startswith(("http://", "https://")):
        onde = "no Google Drive" if "google" in fp else "em URL externa"
        return [doc("Ver documento", disabled=True, motivo=f"Está {onde} — abra pela pasta do kit")]
    if fp.startswith("/inter/"):
        return [doc("Ver documento", disabled=True, motivo="Comprovante bancário: abra pelo Financeiro (Inter)")]
    if not os.path.isfile(fp if os.path.isabs(fp) else os.path.join(GED_STORAGE_BASE, fp)):
        return [doc("Ver documento", disabled=True, motivo="Arquivo não está no disco deste servidor")]
    ext = "html" if (mime_type or "") == "text/html" else "pdf"
    # `filename` porque o botão "Baixar" do DocButtons vira `a.download=doc.filename` e, sem ele,
    # o blob: URL salva com nome aleatório — o arquivo chega na pasta da Pyetra sem dizer o que é.
    # a "/" sai porque o nome real traz competência ("Comprovante PIX Folha 08/2026") e barra em
    # nome de arquivo é o navegador quem resolve — cada um de um jeito
    limpo = (nome or "documento")[:80].replace("/", "-")
    return [doc("Ver documento", url, fmt=ext, mode="blob", filename=f"{limpo}.{ext}")]


def _blocos_do_contrato() -> dict:
    """O que cada cliente deve ter no kit, lido dos CONTRATOS ativos.

    Sem isto o checklist é o mesmo para todos: cobra folha, ponto e VT de quem não tem um
    funcionário alocado. Síncrona pelo mesmo motivo do `_completude_drive` — vai por
    `asyncio.to_thread`.
    """
    from core.database.session import get_sync_db
    from modules.gedeon.services.kit_completude_service import blocos_por_condominio

    with get_sync_db() as db:
        return blocos_por_condominio(db)


def _completude_drive(competencia: str, blocos: dict | None = None) -> dict:
    """Completude REAL do kit, lida do Google Drive.

    Síncrona de propósito — a API do Drive é bloqueante. Por isso o chamador usa
    `asyncio.to_thread`: chamar direto travaria o event loop do FastAPI e a tela inteira
    ficaria pendurada esperando o Google.
    """
    from modules.gedeon.services.kit_completude_service import completude_kits

    return completude_kits(competencia, blocos)


#: 29/09/2026 — logger de MÓDULO. O arquivo tinha `_log` criado DENTRO de duas funções, e as
#: funções novas do fim do arquivo o usariam sem existir. Um logger no módulo, não três locais.
_log = logging.getLogger(__name__)

SLUG = "documentos"

logger = logging.getLogger(__name__)
_ICO_D = "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6"

EXTRA_MENU: list[dict] = [
    {"id": "hermes-classificar", "label": "Classificar documento (Hermes)", "icon": _ICO_D},
    {
        "id": "intercorrencias",
        "label": "Intercorrências do mês",
        "icon": "M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11",
    },
    {
        "id": "ged-coleta-historico",
        "label": "GED — histórico da coleta",
        "icon": "M3 3v18h18",
        "grupo": "GED — coleta e config",
    },
    {
        "id": "ged-coleta-executar",
        "label": "GED — executar coleta agora",
        "icon": "M3 3v18h18",
        "grupo": "GED — coleta e config",
    },
    {
        "id": "ged-tipos-documento",
        "label": "GED — tipos de documento",
        "icon": "M3 3v18h18",
        "grupo": "GED — coleta e config",
    },
    {
        "id": "ged-coleta-automatica",
        "label": "GED — coleta automática",
        "icon": "M3 3v18h18",
        "grupo": "GED — coleta e config",
    },
    {
        "id": "ged-coleta-configurar",
        "label": "GED — configurar coleta",
        "icon": "M3 3v18h18",
        "grupo": "GED — coleta e config",
    },
    {"id": "ged-agendamento", "label": "Agendamento de envio do GED", "icon": _ICO_D, "grupo": "GED — coleta e config"},
    {
        "id": "ged-agendamento-pm",
        "label": "Agendamento do GED (envio)",
        "icon": _ICO_D,
        "grupo": "GED — coleta e config",
    },
    # 29/09/2026 — as duas telas que faltavam para a Pyetra não depender de terminal. A
    # conferência vem ANTES de «Documentos por kit» no menu de propósito: conferir é o passo
    # que se faz primeiro, e ordem de menu é instrução de uso.
    {
        "id": "kits-conferir",
        "label": "Conferir kits do mês",
        "icon": "M3 3v18h18",
        "grupo": "Kits documentais",
    },
    {
        "id": "kit-definir-condominio",
        "label": "Definir condomínio de quem ficou sem",
        "icon": "M3 3v18h18",
        "grupo": "Kits documentais",
    },
    {"id": "kit-documentos", "label": "Documentos por kit", "icon": "M3 3v18h18", "grupo": "Kits documentais"},
    {
        "id": "kits-conferencia",
        "label": "Conferência dos kits (ATLAS)",
        "icon": "M3 3v18h18",
        "grupo": "Kits documentais",
    },
    {
        "id": "kits-assinaturas-pendentes",
        "label": "Central de assinaturas",
        "icon": "M3 3v18h18",
        "grupo": "Kits documentais",
    },
    {
        "id": "kits-entrega-status",
        "label": "Entrega dos kits (status)",
        "icon": "M3 3v18h18",
        "grupo": "Kits documentais",
    },
    {
        "id": "kit-entrega-preparar",
        "label": "Preparar entrega de kit",
        "icon": "M3 3v18h18",
        "grupo": "Kits documentais",
    },
    {
        "id": "kit-entrega-marcar",
        "label": "Marcar kit como entregue",
        "icon": "M3 3v18h18",
        "grupo": "Kits documentais",
    },
    {
        "id": "kit-anexar-comprovante",
        "label": "Anexar comprovante do banco (exceção)",
        "icon": "M3 3v18h18",
        "grupo": "Kits documentais",
    },
    {"id": "kit-faturar", "label": "Faturar kit (boleto)", "icon": "M3 3v18h18", "grupo": "Kits documentais"},
    {
        "id": "kit-checklist-evento",
        "label": "Registrar evento no checklist do kit",
        "icon": "M3 3v18h18",
        "grupo": "Kits documentais",
    },
    {"id": "kits-montar", "label": "Montar kits do mês", "icon": _ICO_D, "grupo": "Kits documentais"},
    {"id": "kits-pdfs-mes", "label": "Gerar PDFs dos kits do mês", "icon": _ICO_D, "grupo": "Kits documentais"},
    {"id": "kit-real-mes", "label": "Gerar kits reais do mês", "icon": _ICO_D, "grupo": "Kits documentais"},
    {"id": "gedeon-panorama", "label": "GEDEON — panorama", "icon": "M3 3v18h18", "grupo": "GEDEON"},
    {"id": "gedeon-alinhamento-dp", "label": "GEDEON — alinhamento DP", "icon": "M3 3v18h18", "grupo": "GEDEON"},
    {"id": "gedeon-funcionarios", "label": "GEDEON — funcionários da folha", "icon": "M3 3v18h18", "grupo": "GEDEON"},
    {"id": "gedeon-funcionario", "label": "GEDEON — visão por funcionário", "icon": "M3 3v18h18", "grupo": "GEDEON"},
    {
        "id": "gedeon-assinaturas-pendentes",
        "label": "GEDEON — VT/VR não assinados",
        "icon": "M3 3v18h18",
        "grupo": "GEDEON",
    },
    {"id": "gedeon-perguntar", "label": "Consultor GEDEON", "icon": _ICO_D, "grupo": "GEDEON"},
    {"id": "gedeon-intercorrencia", "label": "Registrar intercorrência", "icon": _ICO_D, "grupo": "GEDEON"},
    {"id": "gedeon-perguntar-arquivo", "label": "Consultor GEDEON — com anexo", "icon": _ICO_D, "grupo": "GEDEON"},
    {"id": "cnd-emitir", "label": "Certidões — emitir (robô)", "icon": "M3 3v18h18", "grupo": "Certidões"},
    {"id": "cnd-upload", "label": "Certidões — subir PDF", "icon": "M3 3v18h18", "grupo": "Certidões"},
    {"id": "certidoes-avisar", "label": "Certidões — avisar cliente", "icon": "M3 3v18h18", "grupo": "Certidões"},
    {
        "id": "assinaturas-empresa-lote",
        "label": "Assinar em lote (empresa)",
        "icon": "M3 3v18h18",
        "grupo": "Assinaturas",
    },
    {"id": "assinaturas-cobrar-lote", "label": "Cobrar quem não assinou", "icon": "M3 3v18h18", "grupo": "Assinaturas"},
    {"id": "assinatura-solicitar", "label": "Solicitar assinatura", "icon": _ICO_D, "grupo": "Assinaturas"},
    {"id": "sophia-indexar", "label": "Indexar acervo (SOPHIA)", "icon": _ICO_D, "grupo": "Acervo (SOPHIA)"},
    {"id": "sophia-reindexar", "label": "Re-indexar acervo (SOPHIA v2)", "icon": _ICO_D, "grupo": "Acervo (SOPHIA)"},
    {"id": "ingestao-historica", "label": "Ingestão histórica do Drive", "icon": _ICO_D, "grupo": "Acervo (SOPHIA)"},
    {"id": "sophia-perguntar", "label": "Perguntar ao acervo (SOPHIA)", "icon": _ICO_D, "grupo": "Acervo (SOPHIA)"},
]


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)
    n_ged = await _scalar(db, "SELECT count(*) FROM ged_kit_documents")
    n_signed = await _scalar(db, "SELECT count(*) FROM ged_kit_documents WHERE is_signed=true")

    async def _visao():
        # ── A VERDADE DO KIT É O DRIVE — decisão do Jordan em 15/08/2026 ─────────
        #
        # Esta tela contava o BANCO e por isso divergia da clássica, que lê o Drive. Duas
        # telas, dois números, nenhuma sozinha dizendo a verdade: em 15/08 o banco mostrava
        # 8 kits de agosto com ZERO slots, enquanto o Drive já tinha as 35 certidões
        # replicadas nos 7 postos — Ideal Flores, Mirante, Prime e Michelangelo em 20%,
        # que é 2 de 10 blocos.
        #
        # A tela clássica JÁ passou por isto, e está escrito no código dela: "a antiga Kits
        # Documentais (completude via banco, mostrava 0.0%) foi substituída pela dashboard
        # real de completude (lê o Google Drive)". A troca resolveu lá e deixou o redesign
        # para trás — com os mesmos números que motivaram o abandono do outro.
        #
        # ⚠️ SE O DRIVE NÃO RESPONDER, A TELA DIZ ISSO. Não cai no banco em silêncio:
        # número de outra fonte com a mesma etiqueta é fabricação, e foi assim que o
        # `hr/aggregator` anunciava 52 funcionários fixos quando o banco falhava.
        # ⚠️ COMPETÊNCIA ≠ MÊS CORRENTE. O kit da competência X é ENTREGUE em X+1: o que
        # se monta e se entrega ao longo de agosto é o trabalho de JULHO, e mora na pasta
        # "Agosto". Pedindo o mês corrente (08) a tela lia a pasta "Setembro", que hoje só
        # tem as certidões adiantadas — 5 arquivos. Daí os 20% idênticos em todos os sete,
        # com 24 a 35 arquivos reais em cada kit de agosto. Medido em 19/08/2026.
        _n = datetime.now()
        _m, _a = (_n.month - 1, _n.year) if _n.month > 1 else (12, _n.year - 1)
        comp = f"{_m:02d}.{_a}"
        # A leitura do Drive custava 15 s A CADA abertura da tela (medido 07/09/2026: 195 leituras
        # SSL na API do Google). O kit do mês anterior muda devagar; 15 min de cache no Redis
        # bastam — e a chave leva a competência, então a virada do mês não lê cache velho.
        drive, erro = None, ""
        _ck = f"redesign:documentos:drive:{comp}"
        try:
            from core.cache.redis import cache_get, cache_set

            drive = await cache_get(_ck)
        except Exception:  # noqa: BLE001 — sem Redis, lê o Drive como antes
            drive = None
        # Cache "velho serve, novo chega atrás": a leitura fria do Drive leva ~20 s e a tela ficava
        # em "carregando…" toda vez que o cache de 15 min expirava (medido 07/09/2026 pelo navegador).
        # Guarda por 6 h; passados 15 min, devolve o que tem e renova em segundo plano.
        import time as _time

        async def _ler_e_guardar():
            blocos = await asyncio.to_thread(_blocos_do_contrato)
            d = await asyncio.to_thread(_completude_drive, comp, blocos)
            if isinstance(d, dict):
                d["_lido_em"] = _time.time()
                try:
                    await cache_set(_ck, d, ttl=6 * 3600)
                except Exception:  # noqa: BLE001
                    pass
            return d

        if isinstance(drive, dict) and _time.time() - float(drive.get("_lido_em") or 0) > 900:
            try:
                asyncio.get_running_loop().create_task(_ler_e_guardar())
            except Exception:  # noqa: BLE001
                pass
        if not isinstance(drive, dict):
            drive = None
            try:
                drive = await _ler_e_guardar()
            except Exception as exc:  # noqa: BLE001
                erro = str(exc)[:70]

        acervo = {
            "title": "Acervo no banco (histórico)",
            "rows": [
                {"left": "Arquivos registrados", "right": f"{n_ged:,}".replace(",", "."), **S["mut"]},
                {"left": "Assinados", "right": f"{n_signed:,}".replace(",", "."), **S["ok"]},
                {"left": "Pendentes de assinatura", "right": str((n_ged or 0) - (n_signed or 0)), **S["warn"]},
            ],
        }

        if drive:
            # Maior completude primeiro. Ordenar pelos PIORES escondia justamente o que
            # avançou: em 15/08 os 4 postos com as certidões estavam em 20% e os primeiros
            # 8 da lista crescente eram todos 0% — a tela mostraria só zeros e pareceria
            # que a montagem não tinha feito nada.
            kits = sorted(drive.get("kits") or [], key=lambda k: -(k.get("completion_percentage") or 0))[:10]
            kpis = [
                {"v": str(drive.get("total_kits") or 0), "l": "Kits do mês", "icon": IC["cal"], "color": "#0F1B3A"},
                {
                    "v": f"{drive.get('media_completude') or 0}%",
                    "l": "Completude média",
                    "icon": IC["shield"],
                    "color": "#0F1B3A",
                },
                {
                    "v": str(drive.get("kits_completos") or 0),
                    "l": "Completos",
                    "icon": IC["shield"],
                    "color": "#16A34A",
                },
                {"v": str(drive.get("kits_pendentes") or 0), "l": "Pendentes", "icon": IC["cal"], "color": "#B4690E"},
            ]
            linhas = [
                {
                    "left": (k.get("condominio") or "—")[:34],
                    "right": f"{k.get('completion_percentage') or 0}%",
                    **(
                        S["ok"]
                        if (k.get("completion_percentage") or 0) >= 100
                        else S["warn"]
                        if (k.get("completion_percentage") or 0) > 0
                        else S["mut"]
                    ),
                }
                for k in kits
            ] or [{"left": "Nenhum kit no Drive", "right": "0", **S["mut"]}]
            sub = f"Kits do mês ({comp}) — lido do Google Drive"
        else:
            kpis = [
                {"v": "—", "l": "Kits do mês", "icon": IC["cal"], "color": "#6B7280"},
                {"v": "—", "l": "Completude média", "icon": IC["shield"], "color": "#6B7280"},
                {"v": f"{n_ged:,}".replace(",", "."), "l": "Arquivos no banco", "icon": IC["cal"], "color": "#0F1B3A"},
                {"v": f"{n_signed:,}".replace(",", "."), "l": "Assinados", "icon": IC["shield"], "color": "#16A34A"},
            ]
            linhas = [
                {"left": "Não foi possível ler o Google Drive", "right": "—", **S["warn"]},
                {"left": erro or "sem detalhe", "right": "", **S["mut"]},
            ]
            sub = f"Kits do mês ({comp}) — Google Drive indisponível"

        return {
            "title": "Visão geral",
            "sub": sub,
            "cta": "Enviar documento",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": kpis,
            "panels": [{"title": "Completude por condomínio", "rows": linhas}, acervo],
            # PILOTO DA FUNDAÇÃO (docs nível-tela) — prova os 3 modos do DocButtons com ROTAS
            # VERIFICADAS (curl 200): blob (ZIP do kit mais recente, nativo GED) · json (export
            # conciliação {content,filename} via export_format=csv) · disabled (honesto, botão off).
            # Vira o EXEMPLO-ÂNCORA que os builders de cada território replicam.
            "docs": [
                doc(
                    "Kit mais recente (ZIP)",
                    "/api/v1/ged/kits/31c7bed9-ae21-4a48-9b36-ae64576d44a8/download-zip",
                    fmt="zip",
                    mode="blob",
                ),
                doc(
                    "SPED (aguardando)",
                    disabled=True,
                    motivo="Aguardando emissão real — botão liga quando o arquivo existir",
                ),
            ],
        }

    await safe("visao", _visao())
    # Arquivos (ged_kit_documents) — com "Ver documento" por LINHA.
    # O comentário que ficou aqui até 28/09/2026 dizia «SEM download por-doc: a rota serve
    # ged_documents (tabela VAZIA)» e foi a razão de a coluna ficar desligada por um mês. Era
    # FALSO: existem DUAS rotas de download de documento, e o comentário olhou a errada.
    #   · /api/v1/ged/documents/{id}/download  → modules/ged/.../document_controller.py, esta sim
    #     faz select(GedDocument) sobre ged_documents (vazia).
    #   · /api/v1/people-management/ged/documents/{id}/download → modules/people_management/ged/
    #     .../document_controller.py:259 faz select(KitDocument), e kit_document.py:133 aponta
    #     para `ged_kit_documents`. É esta que a tela usa, e ela sempre esteve no ar.
    await safe(
        "arquivos",
        tbl(
            "Arquivos",
            f"{n_ged} documentos · «Ver documento» abre na tela (sem baixar ZIP de 43 para olhar um)",
            "Enviar documento",
            ["Documento", "Tipo", "Colaborador", "Assinado"],
            "2fr 1.4fr 1.6fr 0.9fr",
            "SELECT coalesce(g.document_name,'—'), coalesce(g.document_type::text,'—'), coalesce(e.nome,'—'), g.is_signed, "
            "g.id, g.file_path, g.mime_type "
            "FROM ged_kit_documents g LEFT JOIN employees e ON e.id=g.employee_id ORDER BY g.created_at DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t((r[1] or "—").replace("_", " ")),
                t(r[2]),
                b("Assinado", "ok") if r[3] else b("Pendente", "warn"),
            ],
            docsfn=lambda r: _chip_ver_documento(r[4], r[5], r[6], r[0]),
        ),
    )

    # Kits de documentos por competência — ged_document_kits (58). PILOTO row.docs: cada kit ganha
    # "Baixar ZIP" via /ged/kits/{id}/download-zip (rota nativa verificada, 200 application/zip).
    _kit_tone = {
        "completo": "ok",
        "aprovado": "ok",
        "enviado": "ok",
        "concluido": "ok",
        "em_montagem": "warn",
        "pendente": "warn",
        "montando": "warn",
    }
    await safe(
        "kits",
        tbl(
            "Kits de documentos",
            f"{await _scalar(db, 'SELECT count(*) FROM ged_document_kits')} kits — kit MATERIALIZADO pelo sistema (documentos gerados: contracheques, comprovantes, escalas); o kit ENTREGUE ao cliente é o do Drive, na Visão",
            "—",
            ["Competência", "Colaboradores", "Docs", "Assinados", "Completude", "Status"],
            "1fr 1fr 0.8fr 0.8fr 1fr 1.1fr",
            "SELECT id, to_char(reference_month,'MM/YYYY'), total_employees, total_documents, documents_signed, completion_percentage, coalesce(status::text,'—') "
            "FROM ged_document_kits ORDER BY reference_month DESC NULLS LAST, completion_percentage DESC LIMIT 200",
            lambda r: [
                t(r[1] or "—", 600, "#0F1B3A"),
                t(f"{int(r[2] or 0)}"),
                t(f"{int(r[3] or 0)}"),
                t(f"{int(r[4] or 0)}"),
                t(f"{float(r[5] or 0):.0f}%", 600),
                b((r[6] or "—").replace("_", " ").capitalize(), _kit_tone.get((r[6] or "").lower(), "info")),
            ],
            docsfn=lambda r: [doc("Kit ZIP", f"/api/v1/ged/kits/{r[0]}/download-zip", fmt="zip", mode="blob")],
            actionsfn=lambda r: [
                {
                    "title": f"Gerar os PDFs do kit {r[1]}",
                    "endpoint": f"/api/v1/ged/kits/{r[0]}/generate-pdfs",
                    "method": "POST",
                    "btnLabel": "Gerar PDFs",
                    "submitLabel": "Gerar agora",
                    "btnStyle": "outline",
                    "okMsg": "Geração dos PDFs disparada. Recarregue.",
                    "fields": [],
                },
                {  # POST /ged/kits/{kit_id}/solicitar-assinaturas — gate do envio depende disto
                    "title": f"Solicitar assinaturas dos funcionários — kit {r[1]}",
                    "sub": "Cria os pedidos de assinatura (sig_signature_requests) para os documentos do kit. Não envia e-mail.",
                    "endpoint": f"/api/v1/ged/kits/{r[0]}/solicitar-assinaturas",
                    "method": "POST",
                    "btnLabel": "Solicitar assinaturas",
                    "submitLabel": "Solicitar",
                    "btnStyle": "outline",
                    "okMsg": "Pedidos de assinatura criados. Recarregue.",
                    "fields": [],
                },
                {
                    "title": f"Anexar as NFS-e ao kit {r[1]}",
                    "sub": "Junta as NFS-e reais do cliente na competência. Não emite nota.",
                    "endpoint": f"/api/v1/ged/kits/{r[0]}/add-nfse",
                    "method": "POST",
                    "btnLabel": "Anexar NFS-e",
                    "submitLabel": "Anexar agora",
                    "btnStyle": "outline",
                    "okMsg": "NFS-e anexadas. Recarregue.",
                    "fields": [],
                },
                {
                    "title": f"Enviar o kit {r[1]} ao cliente por e-mail",
                    "sub": "Efeito EXTERNO: o cliente recebe agora, com o link do Drive.",
                    "endpoint": f"/api/v1/people-management/ged/kits/{r[0]}/send-email",
                    "method": "POST",
                    "btnLabel": "Enviar",
                    "submitLabel": "Enviar ao cliente agora",
                    "btnStyle": "primary",
                    "okMsg": "Kit enviado ao cliente. Recarregue.",
                    "fields": [],
                },
            ],
        ),
    )

    # Pastas (GED / Drive) — ged_folders (8)
    await safe(
        "pastas",
        tbl(
            "Pastas",
            f"{await _scalar(db, 'SELECT count(*) FROM ged_folders')} pastas",
            "—",
            ["Pasta", "Código", "Tipo", "Nível", "Status"],
            "1.8fr 1.2fr 1.1fr 0.7fr 0.9fr",
            "SELECT coalesce(name,'—'), coalesce(code,'—'), coalesce(folder_type::text,'—'), level, coalesce(status::text,'—') "
            "FROM ged_folders ORDER BY coalesce(path,'') LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t(r[1]),
                t((r[2] or "—").replace("_", " ").capitalize()),
                t(f"{int(r[3] or 0)}"),
                b((r[4] or "—").capitalize(), "ok" if (r[4] or "").lower() in ("ativa", "ativo", "active") else "mut"),
            ],
        ),
    )

    # ── FIOS SOLTOS DE GED/GEDEON (2026-08-10) ────────────────────────────────────────
    # As de QUERY PARAM (sophia, hermes, kits do mês, agendamento) foram ligadas depois, com
    # o `submit.query` que o ModuleView ganhou. As de {id} no caminho viraram ação por LINHA
    # na tabela de kits e na de intercorrências, logo abaixo — é o lugar delas: o id vem da
    # linha, e não de um UUID colado à mão.
    out["gedeon-perguntar"] = {
        "title": "Consultor GEDEON",
        "sub": "Pergunta ancorada nos kits reais do GED. É consulta — não altera documento.",
        "cta": "Perguntar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/gedeon/consultor/perguntar",
            "okMsg": "Consulta respondida",
            "showResult": True,
        },
        "fields": [
            # `area` é lista FECHADA no backend: gedeon/services/consultor_service.py:24
            # AREAS_VALIDAS = {montagem, checklist, intercorrencias, folha}. Era texto livre com
            # placeholder "Ex.: folha, documentos, kit" — DOIS dos três valores sugeridos eram
            # recusados. Medido em 28/09 contra o container: {"area":"documentos"} → HTTP 422
            # "Área inválida 'documentos'. Válidas: checklist, folha, intercorrencias, montagem";
            # {"area":"kit"} → HTTP 422 igual. Select com os 4 valores reais + default checklist.
            *_CAMPOS_AREA_GEDEON,
            {"key": "condominio", "label": "Condomínio", "type": "text", "span": "span 1"},
            {"key": "competencia", "label": "Competência", "type": "text", "span": "span 1", "ph": "AAAA-MM"},
            {
                "key": "pergunta",
                "label": "Pergunta*",
                "type": "textarea",
                "span": "span 2",
                "ph": "Ex.: quais documentos faltam no kit deste mês?",
            },
        ],
    }
    out["gedeon-intercorrencia"] = {
        "title": "Registrar intercorrência do mês",
        "sub": "Contratação, demissão, falta — o que aconteceu no condomínio e afeta o kit (e, se marcar, a folha).",
        "cta": "Registrar",
        "type": "form",
        "submit": {"endpoint": "/api/v1/gedeon/consultor/intercorrencias", "okMsg": "Intercorrência registrada"},
        "fields": [
            {"key": "condominio", "label": "Condomínio*", "type": "text", "span": "span 1"},
            {
                "key": "tipo",
                "label": "Tipo*",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione",
                "options": [
                    {"value": "contratacao", "label": "Contratação"},
                    {"value": "demissao", "label": "Demissão"},
                    {"value": "falta", "label": "Falta"},
                    {"value": "afastamento", "label": "Afastamento"},
                    {"value": "outro", "label": "Outro"},
                ],
            },
            {"key": "funcionario", "label": "Colaborador", "type": "text", "span": "span 1"},
            {"key": "data_evento", "label": "Data do evento", "type": "date", "span": "span 1"},
            {"key": "competencia", "label": "Competência", "type": "text", "span": "span 1", "ph": "AAAA-MM"},
            {
                "key": "impacto_folha",
                "label": "Impacta a folha?",
                "type": "select",
                "span": "span 1",
                "ph": "Não",
                "options": [{"value": "false", "label": "Não"}, {"value": "true", "label": "Sim"}],
            },
            {"key": "descricao", "label": "O que aconteceu*", "type": "textarea", "span": "span 2"},
        ],
    }
    out["sophia-indexar"] = {
        "title": "Indexar acervo (SOPHIA)",
        "sub": "Varre e indexa o acervo completo de documentos. Pesado — rode fora do horário de pico.",
        "cta": "Indexar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/gedeon/sophia/indexar",
            "okMsg": "Indexação disparada",
            "confirm": "A indexação varre TODO o acervo e consome bastante máquina. Confirma?",
        },
        "fields": [],
    }
    # ── 29/09/2026 — A PYETRA PRECISA ESCOLHER O MÊS. ───────────────────────────────────
    # Medido: as três telas de kit tinham a competência EMBUTIDA no endpoint, fixada no mês
    # corrente. Em 29/09 o botão gerava setembro, e o kit que ela entrega agora é **agosto**
    # (salário em arrears). Ela não usa terminal: sem campo, o mês certo era inalcançável.
    #
    # ⭐ E esta tela apontava para `/ged/kits/montar`, que fixa `date.today()` DENTRO da rota e
    # não aceita parâmetro. O orquestrador de verdade é o do GEDEON — `/gedeon/kits/montagem` —
    # que já aceita competência, condomínios e blocos, roda no celery e devolve `task_id`.
    # Ele já usa `_competencia_anterior()` como padrão: o Gedeon sempre soube que o kit de
    # setembro é competência agosto. A tela é que não perguntava.
    #
    # ⚠️ O Gedeon usa competência **MM.AAAA (ponto)** e o `gerar-docs-mes` usa **MM/AAAA
    # (barra)**. Dois formatos para a mesma coisa, e é a pessoa que paga pelo deslize — por isso
    # o rótulo e o placeholder dizem o formato de cada tela, sem abreviar.
    _ant = (date.today().replace(day=1) - timedelta(days=1))
    _comp_ant = f"{_ant.month:02d}.{_ant.year}"
    # ── 29/09/2026 · CONFERIR KITS DO MÊS ────────────────────────────────────────────────
    # A Pyetra reclamou de kit com documento de outro condomínio («salvei o Kit do Mirante e
    # veio informação do Fiori»). Medido em 28/09: o EULER FELIPE tinha documento em TRÊS kits
    # — Laranjeiras (onde trabalhou), Mirante e Prime Arena. Dois clientes recebiam folha de
    # pagamento de um estranho: é vazamento de dado pessoal, não desorganização.
    #
    # Até hoje a única forma de consertar era um script meu no terminal. Esta tela põe isso na
    # mão dela, com ENSAIO por padrão: ela vê quem sai de qual kit e POR QUÊ antes de aplicar.
    # ⭐ Mostrar o motivo é o que permite ela DISCORDAR — sem isso a tela pede fé, não decisão.
    out["kits-conferir"] = {
        "title": "Conferir kits do mês",
        "sub": (
            f"Compara cada kit com quem realmente trabalhou naquele condomínio na competência. "
            f"O padrão é {_ant:%m/%Y} e «Ensaio» — em ensaio NADA é alterado, só listado, "
            "com o motivo de cada linha. Remove apenas o VÍNCULO pessoa×kit: o PDF continua no "
            "disco e o documento continua existindo para a pessoa."
        ),
        "cta": "Conferir",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/kits-conferir",
            "okMsg": "Conferência concluída — veja a tabela.",
            "showResult": True,
        },
        "fields": [
            {
                "key": "competencia",
                "label": "Competência (MM/AAAA)*",
                "type": "text",
                "value": f"{_ant:%m/%Y}",
                "ph": f"Ex.: {_ant:%m/%Y} — use BARRA nesta tela",
            },
            {
                "key": "acao",
                "label": "O que fazer*",
                "type": "select",
                "value": "ensaio",
                "options": [
                    {"value": "ensaio", "label": "Ensaio — só mostrar, não alterar"},
                    {"value": "aplicar", "label": "Aplicar — remover os vínculos indevidos"},
                ],
            },
        ],
    }

    # ── 29/09/2026 · QUEM FICOU SEM CONDOMÍNIO ───────────────────────────────────────────
    # O roster acha o condomínio pelo `posto_id` gravado na batida, e resolve 60 de 63. As que
    # sobram não têm posto em NENHUMA batida do mês, e aí só um humano sabe. Em 28/09 eu
    # perguntei ao Jordan por WhatsApp e escrevi a resposta numa constante de script — o que não
    # serve, porque a Pyetra não edita Python e decisão de produção não mora em código.
    #
    # ⚠️ NÃO oferece «deduzir pela alocação»: a alocação diz onde a pessoa está HOJE, e as datas
    # dela são ficção (a do RILEM ao GREEN HILLS diz 01/01/2026 num condomínio que abriu em
    # 01/09). Deduzir ali foi o erro que o Jordan pegou. A tela pergunta em vez de chutar.
    _conds = await _condominios_do_mes(db)
    out["kit-definir-condominio"] = {
        "title": "Definir condomínio de quem ficou sem",
        "sub": (
            "Use quando «Conferir kits do mês» listar alguém como «sem condomínio». Acontece "
            "quando as batidas da pessoa no mês não gravaram o posto — então o sistema não tem "
            "como saber, e pergunta em vez de chutar. Fica registrado com o seu nome."
        ),
        "cta": "Definir",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/kit-definir-condominio",
            "okMsg": "Condomínio definido — rode «Conferir kits do mês» de novo para ver o efeito.",
        },
        "fields": [
            {
                "key": "competencia",
                "label": "Competência (MM/AAAA)*",
                "type": "text",
                "value": f"{_ant:%m/%Y}",
                "ph": f"Ex.: {_ant:%m/%Y}",
            },
            {
                "key": "employee_id",
                "label": "Colaborador*",
                "type": "select",
                "span": "span 2",
                "options": await _sem_condominio_opcoes(db, f"{_ant:%Y-%m}-01"),
            },
            {
                "key": "condominio",
                "label": "Condomínio onde trabalhou nesse mês*",
                "type": "select",
                "span": "span 2",
                "options": _conds,
            },
            {
                "key": "motivo",
                "label": "Como você sabe? (fica no registro)",
                "type": "textarea",
                "span": "span 2",
                "max": 300,
                "ph": "Ex.: cobriu o posto no lugar de outra pessoa; confirmado com a supervisão.",
            },
        ],
    }

    out["kits-montar"] = {
        "title": "Montar kits do mês (Gedeon)",
        "sub": (
            f"Dispara o orquestrador do Gedeon para a competência escolhida. O padrão é "
            f"**{_comp_ant}** — o mês ANTERIOR, porque o kit entregue agora documenta o mês "
            "fechado. Roda em fila e devolve um número de tarefa para acompanhar; nada "
            "acontece na hora. Deixe os blocos em branco para montar tudo."
        ),
        "cta": "Montar kits",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/gedeon/kits/montagem",
            "okMsg": "Montagem enfileirada — acompanhe em «Conferência dos kits (ATLAS)».",
            "confirm": "Dispara a montagem do kit da competência informada. Confirma?",
        },
        "fields": [
            {
                "key": "competencia",
                "label": "Competência (MM.AAAA)*",
                "type": "text",
                "value": _comp_ant,
                "ph": f"Ex.: {_comp_ant} — use PONTO, não barra (é o formato do Gedeon)",
            },
            {
                "key": "blocos",
                "label": "Blocos (vazio = todos)",
                "type": "multiselect",
                "span": "span 2",
                "options": [
                    {"value": b, "label": l}
                    for b, l in (
                        ("folha", "Folha (contracheques)"),
                        ("guias", "Guias (INSS/FGTS/ISS)"),
                        ("pagamentos", "Pagamentos (comprovantes do banco)"),
                        ("vavt", "VA / VT"),
                        ("rescisao", "Rescisões"),
                        ("cnds", "CNDs e CRF"),
                        ("nfse", "NFS-e / DANFSe"),
                        ("ponto", "Folha de ponto"),
                        ("sistema", "Documentos do sistema"),
                    )
                ],
            },
        ],
    }

    # ── Rotas de QUERY PARAM ligadas SEM tela de campo (2026-08-10) ──────────────────
    # O renderizador manda JSON no CORPO e estas rotas leem QUERY. Mas o endpoint do form
    # aceita query fixa (padrao ja usado no financeiro: "...sync-recebidos?dias=30"), e
    # endpoint sem parametro de corpo IGNORA o corpo. Entao query derivavel = botao que
    # funciona, sem uma linha de frontend e sem rota nova.
    #
    # E nao e so conveniencia: os defaults destas rotas estao CONGELADOS em marco/2026
    # (mes=3, ano=2026, reference_month="2026-03-01"). Um botao seco geraria documento da
    # competencia errada em silencio. Embutir o mes corrente CORRIGE isso.
    _hoje = date.today()
    _comp = f"{_hoje.year:04d}-{_hoje.month:02d}"
    # 29/09/2026 — as duas rotas abaixo leem QUERY, e `submit.query` manda os campos na URL
    # preservando o que já está fixo no endpoint (ModuleView.tsx:739). Então dar o campo à
    # Pyetra não custou rota nova: custou trocar a competência embutida por um campo com o mês
    # anterior como padrão. O comportamento de quem só clica continua o mesmo.
    out["kits-pdfs-mes"] = {
        "title": "Gerar PDFs dos kits",
        "sub": (
            f"Gera os PDFs de todos os kits da competência escolhida. O padrão é {_ant:%m/%Y} "
            "(mês anterior), que é o kit entregue agora. O campo é o PRIMEIRO DIA do mês — o "
            "padrão da própria rota está preso em março/2026, então o campo não é opcional na "
            "prática: em branco, ela geraria março."
        ),
        "cta": "Gerar PDFs",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/ged/kits/generate-all-pdfs",
            "query": True,
            "okMsg": "Geração dos PDFs disparada",
            "confirm": "Gera os PDFs de TODOS os kits da competência informada. Confirma?",
        },
        "fields": [
            {
                "key": "reference_month",
                "label": "Competência — primeiro dia do mês*",
                "type": "date",
                "value": f"{_ant:%Y-%m}-01",
                "ph": "AAAA-MM-01",
            },
        ],
    }
    out["kit-real-mes"] = {
        "title": "Gerar kits reais",
        "sub": (
            f"Monta os kits reais (com documento de verdade) da competência escolhida. O padrão "
            f"é **{_ant:%m/%Y}**. Em branco a rota cai no default dela, que é março/2026."
        ),
        "cta": "Gerar kits",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/ged/kit-real/gerar-todos",
            "query": True,
            "okMsg": "Geração dos kits reais disparada",
            "confirm": "Gera os kits reais de TODOS os clientes na competência informada. Confirma?",
        },
        "fields": [
            {
                "key": "mes",
                "label": "Mês*",
                "type": "select",
                "value": str(_ant.month),
                "options": [{"value": str(m), "label": f"{m:02d}"} for m in range(1, 13)],
            },
            {
                "key": "ano",
                "label": "Ano*",
                "type": "select",
                "value": str(_ant.year),
                "options": [{"value": str(a), "label": str(a)} for a in range(_ant.year - 1, _ant.year + 2)],
            },
        ],
    }
    out["sophia-reindexar"] = {
        "title": "Re-indexar acervo (SOPHIA v2)",
        "sub": "Refaz os embeddings do acervo na versão 2. Mais pesado que indexar — use "
        "quando a busca estiver devolvendo resultado ruim.",
        "cta": "Re-indexar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/gedeon/sophia/reindexar",
            "okMsg": "Re-indexação disparada",
            "confirm": "Re-indexar refaz o acervo INTEIRO e consome bastante máquina. Confirma?",
        },
        "fields": [],
    }
    out["ingestao-historica"] = {
        "title": "Ingestão histórica do Drive",
        "sub": "Processa os ZIPs históricos da pasta do Drive e alimenta a SOPHIA. "
        "Idempotente por arquivo já processado.",
        "cta": "Processar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/people-management/ged/documents/ingestao/historica",
            "okMsg": "Ingestão histórica disparada",
            "confirm": "Processa TODOS os ZIPs históricos da pasta. Demorado. Confirma?",
        },
        "fields": [],
    }

    # ── Rotas de QUERY PARAM com entrada do usuário (submit.query) ──────────────────
    # O renderizador ganhou `submit.query`: os campos viram query string em vez de ficarem
    # só no corpo. Opt-in — sem a flag nada muda nos ~200 forms existentes.
    out["sophia-perguntar"] = {
        "title": "Perguntar ao acervo (SOPHIA)",
        "sub": "Busca em linguagem natural sobre TODO o acervo indexado. Se vier vazio, "
        "provavelmente falta indexar — use 'Indexar acervo' antes.",
        "cta": "Perguntar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/gedeon/sophia/perguntar",
            "query": True,
            "okMsg": "Consulta respondida",
            "showResult": True,
        },
        "fields": [
            {
                "key": "pergunta",
                "label": "Pergunta*",
                "type": "textarea",
                "span": "span 2",
                "ph": "Ex.: em que mês entregamos o último atestado do condomínio X?",
            },
            {"key": "cliente_id", "label": "Cliente (id)", "type": "text", "span": "span 1"},
            {"key": "funcionario_id", "label": "Colaborador (id)", "type": "text", "span": "span 1"},
            {"key": "modulo", "label": "Módulo", "type": "text", "span": "span 1", "ph": "Ex.: folha, sst, fiscal"},
            {"key": "competencia", "label": "Competência", "type": "text", "span": "span 1", "ph": "AAAA-MM"},
        ],
    }
    out["gedeon-perguntar-arquivo"] = {
        "title": "Consultor GEDEON — analisando um anexo",
        "sub": "Anexe PDF, DOCX, TXT ou CSV e pergunte sobre ele. O arquivo NÃO é guardado "
        "no acervo — é lido para responder.",
        "cta": "Analisar",
        "type": "form",
        # SEM `query`: a rota declara os campos como `Form(...)` (consultor_controller.py:77-80),
        # e `Form` lê SÓ o corpo multipart. Com `query: True` o ModuleView punha area/pergunta na
        # URL e NÃO no FormData (ModuleView.tsx:743 pula o append quando há query) — o backend caía
        # nos defaults e devolvia HTTP 200, então ninguém percebia. Medido em 28/09 contra o
        # container, mesmo arquivo nos dois casos:
        #   · `?area=documentos&pergunta=quantas+faltas`  → HTTP 200, e a linha gravada em
        #     gedeon_consultas veio area='checklist' (default do Form) com
        #     pergunta='Analise este documento no contexto do fechamento do kit.' — a pergunta
        #     da Pyetra foi DESCARTADA em silêncio.
        #   · `-F area=checklist -F pergunta='quantas faltas'` → HTTP 200 e a linha gravada
        #     preservou a pergunta dela.
        # Com os campos no corpo o validador de `area` volta a ser alcançável (era inalcançável
        # por este form: `-F area=documentos` dá 422, `?area=documentos` não dava).
        "submit": {
            "endpoint": "/api/v1/gedeon/consultor/perguntar-arquivo",
            "multipart": True,
            "okMsg": "Análise concluída",
            "showResult": True,
        },
        "fields": [
            {"key": "arquivo", "label": "Arquivo*", "type": "file", "span": "span 2"},
            *_CAMPOS_AREA_GEDEON,
            {"key": "condominio", "label": "Condomínio", "type": "text", "span": "span 1"},
            {"key": "competencia", "label": "Competência", "type": "text", "span": "span 1", "ph": "AAAA-MM"},
            {"key": "pergunta", "label": "Pergunta*", "type": "textarea", "span": "span 2"},
        ],
    }
    out["hermes-classificar"] = {
        "title": "Classificar documento (Hermes)",
        "sub": "Diz em que categoria do GED um documento se encaixa, a partir do nome e de "
        "um trecho do conteúdo. Só classifica — não move nem grava nada.",
        "cta": "Classificar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/gedeon/hermes/classificar",
            "query": True,
            "okMsg": "Documento classificado",
            "showResult": True,
        },
        "fields": [
            {
                "key": "nome_arquivo",
                "label": "Nome do arquivo*",
                "type": "text",
                "span": "span 2",
                "ph": "Ex.: DARF_08_2026.pdf",
            },
            {
                "key": "conteudo_preview",
                "label": "Trecho do conteúdo",
                "type": "textarea",
                "span": "span 2",
                "ph": "Cole as primeiras linhas — ajuda quando o nome é genérico",
            },
        ],
    }
    out["ged-agendamento"] = {
        "title": "Agendamento de envio do GED",
        "sub": "Quando e por onde o kit vai para o cliente. Campos em branco não são "
        "alterados — o backend só aceita as chaves conhecidas.",
        "cta": "Salvar agendamento",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/ged/config/schedule",
            "method": "PUT",
            "okMsg": "Agendamento salvo",
            "showResult": True,
        },
        "fields": [
            {
                "key": "ativo",
                "label": "Agendamento ativo?",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione",
                "options": [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}],
            },
            {
                "key": "envio_automatico",
                "label": "Envio automático?",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione",
                "options": [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}],
            },
            {"key": "dia_envio", "label": "Dia do mês", "type": "number", "span": "span 1", "ph": "Ex.: 5"},
            {"key": "hora_envio", "label": "Hora", "type": "text", "span": "span 1", "ph": "HH:MM"},
            {
                "key": "canal_envio",
                "label": "Canal",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione",
                "options": [
                    {"value": "email", "label": "E-mail"},
                    {"value": "whatsapp", "label": "WhatsApp"},
                    {"value": "portal", "label": "Portal do cliente"},
                ],
            },
            {
                "key": "destinatarios",
                "label": "Destinatários",
                "type": "text",
                "span": "span 1",
                "ph": "e-mails separados por vírgula",
            },
            {
                "key": "incluir_kits",
                "label": "Incluir kits?",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione",
                "options": [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}],
            },
            {
                "key": "incluir_certidoes",
                "label": "Incluir certidões?",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione",
                "options": [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}],
            },
        ],
    }

    # Intercorrencias (2026-08-10): a criacao ja tinha tela; TRATAR e EXCLUIR levam {id} no
    # caminho, entao vivem como acao por LINHA desta listagem.
    await safe(
        "intercorrencias",
        tbl(
            "Intercorrências",
            "Eventos do mês que afetam o kit (e, quando marcado, a folha)",
            "—",
            ["Condomínio", "Tipo", "Colaborador", "Evento", "Folha", "Status"],
            "1.6fr 1fr 1.4fr 1fr 0.7fr 0.9fr",
            "SELECT id, coalesce(condominio,'—'), coalesce(tipo::text,'—'), coalesce(funcionario,'—'), "
            "data_evento, coalesce(impacto_folha,false), coalesce(status::text,'aberta') "
            "FROM gedeon_intercorrencias ORDER BY created_at DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[1], 600, "#0F1B3A"),
                t((r[2] or "—").capitalize()),
                t(r[3]),
                t(str(r[4]) if r[4] else "—"),
                b("Sim", "bad") if r[5] else b("Não", "mut"),
                b((r[6] or "—").capitalize(), "ok" if (r[6] or "").lower() == "tratada" else "warn"),
            ],
            actionsfn=lambda r: (
                None
                if (r[6] or "").lower() == "tratada"
                else [
                    {
                        "title": f"Marcar como tratada — {r[1]}",
                        "endpoint": f"/api/v1/gedeon/consultor/intercorrencias/{r[0]}/tratar",
                        "method": "PATCH",
                        "btnLabel": "Tratar",
                        "submitLabel": "Marcar como tratada",
                        "btnStyle": "primary",
                        "okMsg": "Intercorrência tratada. Recarregue a tela.",
                        "fields": [],
                    },
                    {
                        "title": f"Excluir a intercorrência de {r[1]}",
                        "sub": "Use só quando o registro foi feito por engano — some do histórico.",
                        "endpoint": f"/api/v1/gedeon/consultor/intercorrencias/{r[0]}",
                        "method": "DELETE",
                        "btnLabel": "Excluir",
                        "submitLabel": "Excluir registro",
                        "btnStyle": "outline",
                        "okMsg": "Intercorrência excluída. Recarregue a tela.",
                        "fields": [],
                    },
                ]
            ),
        ),
    )

    out["ged-agendamento-pm"] = {
        "title": "Agendamento do GED — salvar como esta",
        "sub": "Grava a configuracao de envio corrente. Rota DIFERENTE da tela 'Agendamento "
        "de envio do GED': aquela edita os campos, esta persiste o estado atual.",
        "cta": "Salvar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/people-management/ged/config/schedule",
            "okMsg": "Agendamento salvo",
            "showResult": True,
        },
        "fields": [],
    }

    out["assinatura-solicitar"] = {
        "title": "Solicitar assinatura de documento",
        "sub": "Abre o pedido de assinatura. Os signatários vao em LISTA — o exemplo no campo mostra a forma esperada.",
        "cta": "Solicitar",
        "type": "form",
        "submit": {"endpoint": "/api/v1/signatures/requests", "okMsg": "Assinatura solicitada", "showResult": True},
        "fields": [
            {"key": "title", "label": "Titulo*", "type": "text", "span": "span 2"},
            {
                "key": "document_type",
                "label": "Tipo do documento*",
                "type": "text",
                "span": "span 1",
                "ph": "ex.: contrato, holerite",
            },
            {"key": "document_id", "label": "Documento (id)*", "type": "text", "span": "span 1"},
            {"key": "document_name", "label": "Nome do arquivo", "type": "text", "span": "span 1"},
            {"key": "expires_in_days", "label": "Expira em (dias)", "type": "number", "span": "span 1"},
            {
                "key": "signers",
                "label": "Signatarios*",
                "type": "json",
                "span": "span 2",
                "ph": '[{"nome": "Jordan Jesus", "email": "jordan@exemplo.com", "cpf": "000.000.000-00"}]',
            },
        ],
    }

    await _ligar_kits_20260908(db, out)
    await _ligar_lote3_20260908(db, out)
    await _ligar_lote4_20260908(db, out)
    await _ligar_lote5_20260908(db, out)
    return out


async def _ligar_kits_20260908(db, out: dict) -> None:
    """LIGAR 08/09/2026: rotas do orquestrador de kits que só existiam por API/MCP."""
    from modules.gedeon.controllers import (
        orquestrador_controller as O,  # noqa: N812  # alias curto pré-existente, usado em todo o arquivo
    )
    from modules.operacional.controllers.redesign_builders._ligar_generico import (
        chamar,
        painel_de_dict,
        selecionar,
        tabela_de_lista,
    )

    comp = O._competencia_anterior()
    try:
        conds = await chamar(O.condominios_elegiveis_endpoint, db)
        lista = conds if isinstance(conds, list) else (conds or {}).get("condominios", [])
        opts = [
            {
                "value": (c.get("nome") if isinstance(c, dict) else str(c)),
                "label": (c.get("nome") if isinstance(c, dict) else str(c)),
            }
            for c in lista
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("kits: condominios elegíveis: %s", exc)
        opts = []
    if not opts:  # o serviço pode falhar fora (Drive/SSL): cai para os clientes do GED, que é a lista real dos kits
        try:
            from sqlalchemy import text as _t

            opts = [
                {"value": n, "label": n}
                for (n,) in (
                    await db.execute(
                        _t("SELECT name FROM ged_clients WHERE coalesce(is_active,true) ORDER BY name LIMIT 100")
                    )
                ).fetchall()
            ]
        except Exception:  # noqa: BLE001
            await db.rollback()
    # Leitura SEM tocar o Drive na página: a conferência ATLAS vem só do cache em memória do
    # processo (o lote percorre o Drive e segura um lock — isso é para a API/MCP, não para um GET
    # de tela); a completude já está na tela "visao" (mesmo cache Redis). Assinaturas = banco.
    try:
        cached = O._ATLAS_LOTE_CACHE.get(comp)
        if cached:
            selos = cached[1].get("selos") or cached[1].get("condominios") or cached[1]
            linhas = [
                {
                    "condominio": k,
                    **(
                        {kk: vv for kk, vv in v.items() if not isinstance(vv, (list, dict))}
                        if isinstance(v, dict)
                        else {"selo": v}
                    ),
                }
                for k, v in (selos.items() if isinstance(selos, dict) else [])
            ]
            out["kits-conferencia"] = tabela_de_lista(
                f"Conferência dos kits — {comp}",
                "Selo ATLAS por condomínio (última conferência em cache, ~90 s).",
                linhas,
            )
        else:
            out["kits-conferencia"] = painel_de_dict(
                f"Conferência dos kits — {comp}",
                "Nenhuma conferência em cache neste processo.",
                {
                    "como_conferir": "peça ao assistente 'conferir os kits do mês' (MCP consultar_kits) ou chame GET /gedeon/kits/conferir-lote — a varredura lê o Drive e leva ~20 s"
                },
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("kits conferencia: %s", exc)
    # Assinaturas pendentes pelo BANCO (assinatura universal), não pelo Drive: o serviço do kit lê o
    # Drive numa thread e derrubou o worker (08/09/2026, "free(): corrupted unsorted chunks").
    try:
        from sqlalchemy import text as _t

        # 09/09: virou a CENTRAL DE ASSINATURAS do gestor — o que espera a EMPRESA vem primeiro, com o botão "Assinar"
        # (POST /signatures/{id}/sign, papel admin/operator) e o PDF para ler antes. O que espera o funcionário é
        # assinado por ele no portal (meu-espaço); aqui só aparece para cobrança.
        rows = (
            await db.execute(
                _t(
                    "SELECT coalesce(signer_name,'—'), lower(coalesce(signer_type::text,'—')), coalesce(document_type,'—'), coalesce(title, reference_code, '—'), "
                    "status::text, expires_at, id::text, access_token FROM sig_signature_requests WHERE status::text IN ('PENDING','SIGNING') "
                    "AND (expires_at IS NULL OR expires_at > now()) ORDER BY (lower(signer_type::text) = 'company') DESC, created_at DESC LIMIT 300"
                )
            )
        ).fetchall()
        linhas = [
            {
                "signatario": r[0],
                "papel": {"company": "EMPRESA (você)", "employee": "funcionário (portal)", "customer": "cliente"}.get(
                    r[1], r[1]
                ),
                "documento": r[3],
                "tipo": r[2],
                "status": r[4],
                "expira_em": r[5].strftime("%d/%m") if r[5] else "—",
                "_id": r[6],
                "_papel": r[1],
                "_tok": r[7],
            }
            for r in rows
        ]
        n_emp = sum(1 for l in linhas if l["_papel"] == "company")
        out["kits-assinaturas-pendentes"] = tabela_de_lista(
            "Central de assinaturas",
            f"{n_emp} documento(s) esperam a SUA assinatura · {len(linhas) - n_emp} esperam funcionários (portal) ou clientes. Assinatura eletrônica com hash SHA-256; o PDF assinado volta para o kit na hora.",
            linhas,
            cols=["signatario", "papel", "documento", "tipo", "status", "expira_em"],
            docsfn=lambda it: [doc("Ver PDF", f"/api/v1/signatures/{it['_id']}/documento", fmt="pdf", mode="blob")],
            # Empresa: botão de assinar. Funcionário/cliente: botão de COBRAR — até 17/09/2026 a
            # linha dele só tinha "Ver", e cobrar era coisa de terminal. O Jordan: «preciso
            # mandar os documentos pelo sistema, tudo no frontend».
            actionsfn=lambda it: (
                [
                    {
                        "title": f"Assinar como empresa — {it['documento']}",
                        "sub": "Registra a sua assinatura eletrônica (nome, CPF/CNPJ da empresa, data, hash) e carimba o selo no PDF.",
                        "endpoint": f"/api/v1/signatures/{it['_id']}/sign",
                        "method": "POST",
                        "btnLabel": "Assinar",
                        "submitLabel": "Assinar agora",
                        "btnStyle": "primary",
                        "okMsg": "Assinado. O kit já aponta para o PDF assinado. Recarregue.",
                        "fields": [],
                    }
                ]
                if it["_papel"] == "company"
                else [
                    {
                        "title": f"Cobrar assinatura — {it['signatario']}",
                        "sub": "Manda o link do Meu Espaço por WhatsApp e e-mail, direto na aba de assinar. Cobra a PESSOA: se ela tem vários documentos parados, recebe UMA mensagem com todos.",
                        "endpoint": f"/api/v1/signatures/{it['_id']}/cobrar",
                        "method": "POST",
                        "btnLabel": "Cobrar",
                        "submitLabel": "Enviar agora",
                        "btnStyle": "primary",
                        "okMsg": "Cobrança enviada.",
                        "fields": [],
                    }
                ]
                if it["_papel"] == "employee"
                else []
            ),
        )
        n_func = sum(1 for l in linhas if l["_papel"] == "employee")
        out["assinaturas-cobrar-lote"] = {
            "title": "Cobrar todo mundo que não assinou",
            "sub": f"{n_func} funcionário(s) com documento parado. Manda o link do Meu Espaço por WhatsApp e e-mail, "
            "um aviso por pessoa com tudo que ela tem. Quem já assinou não recebe nada — a fila lê o status "
            "na hora. Quem foi cobrado nos últimos 3 dias também fica de fora: lembrete diário vira spam e a "
            "pessoa aprende a ignorar o remetente.",
            "cta": "Cobrar pendentes",
            "type": "form",
            "submit": {
                "endpoint": "/api/v1/signatures/cobrar-pendentes",
                "okMsg": "Cobrança disparada. Recarregue a central.",
                "showResult": True,
            },
            "fields": [
                {
                    "key": "limite",
                    "label": "Máximo de pessoas neste disparo",
                    "type": "number",
                    "span": "span 1",
                    "value": "60",
                }
            ],
        }
        out["assinaturas-empresa-lote"] = {
            "title": "Assinar tudo que espera a empresa",
            "sub": f"{n_emp} documento(s) pendentes da sua assinatura. Assina em lote, um a um pelo mesmo motor; um documento com problema não derruba os outros.",
            "cta": "Assinar em lote",
            "type": "form",
            "submit": {
                "endpoint": "/api/v1/signatures/empresa/assinar-lote",
                "okMsg": "Lote assinado. Recarregue a central.",
                "showResult": True,
            },
            "fields": [
                {
                    "key": "limite",
                    "label": "Máximo de documentos neste lote",
                    "type": "number",
                    "span": "span 1",
                    "value": "60",
                }
            ],
        }
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.warning("kits assinaturas: %s", str(exc)[:120])
    try:
        from sqlalchemy import text as _t

        rows = (
            await db.execute(
                _t(
                    "SELECT g.name, to_char(k.reference_month,'MM/YYYY'), k.sent_at, coalesce(k.sent_method,'—'), coalesce(k.sent_to,'—'), "
                    "coalesce(k.google_drive_link,'') <> '' FROM ged_document_kits k JOIN ged_clients g ON g.id=k.client_id "
                    "WHERE to_char(k.reference_month,'MM.YYYY') = :c ORDER BY g.name"
                ),
                {"c": comp},
            )
        ).fetchall()  # competência do orquestrador é MM.AAAA
        linhas = [
            {
                "condominio": r[0],
                "competencia": r[1],
                "entregue_em": r[2].strftime("%d/%m %H:%M") if r[2] else "—",
                "canal": r[3],
                "para": r[4],
                "no_drive": bool(r[5]),
            }
            for r in rows
        ]
        out["kits-entrega-status"] = tabela_de_lista(
            f"Entrega dos kits — {comp}",
            "Entregue? Quando, por qual canal e para quem (ged_document_kits). Um condomínio por linha.",
            linhas,
            cols=["condominio", "competencia", "entregue_em", "canal", "para", "no_drive"],
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.warning("kits entrega status: %s", exc)
    # 09/09/2026 (decisão do Jordan, opção 2): o comprovante de pagamento do kit REAL é o PDF oficial do banco,
    # baixado do internet banking e anexado aqui — a API da Cora não devolve comprovante (6 caminhos, todos 404) e
    # o do Villa Dei Fiori é o PDF do Cora com autenticação própria. Documento anexado fica intocável: a montagem
    # automática não regera por cima nem o Drive substitui.
    try:
        from sqlalchemy import text as _t

        _k = (
            await db.execute(
                _t(
                    "SELECT k.id::text, g.name, to_char(k.reference_month,'MM/YYYY') FROM ged_document_kits k "
                    "JOIN ged_clients g ON g.id = k.client_id ORDER BY k.reference_month DESC NULLS LAST, g.name LIMIT 60"
                )
            )
        ).fetchall()
        _e = (
            await db.execute(
                _t(
                    "SELECT id::text, nome FROM employees WHERE coalesce(status,'ativo') = 'ativo' ORDER BY nome LIMIT 400"
                )
            )
        ).fetchall()
        out["kit-anexar-comprovante"] = {
            "title": "Anexar comprovante do banco ao kit (exceção)",
            "sub": "O padrão é o comprovante GERADO pelo Conecta PRO, com os dados do extrato — é o que entra no kit "
            "sozinho. Use esta tela só quando precisar do PDF oficial do banco num caso específico: o "
            "arquivo anexado substitui o gerado naquele documento e fica protegido (a montagem automática "
            "não sobrescreve o que foi anexado à mão).",
            "cta": "Anexar",
            "type": "form",
            "submit": {
                "endpoint": "/api/v1/people-management/ged/documents",
                "multipart": True,
                "okMsg": "Comprovante anexado ao kit. Recarregue.",
                "showResult": True,
            },
            "fields": [
                selecionar("kit_id", "Kit*", [{"value": r[0], "label": f"{r[1]} — {r[2]}"} for r in _k], "span 2"),
                selecionar("employee_id", "Colaborador*", [{"value": r[0], "label": r[1]} for r in _e], "span 2"),
                selecionar(
                    "document_type",
                    "Tipo*",
                    [
                        {"value": v, "label": l}
                        for v, l in (
                            ("comprovante_pagamento", "Comprovante de pagamento (salário/adiantamento)"),
                            ("comprovante_vt", "Comprovante de VT"),
                            ("comprovante_vr", "Comprovante de VR"),
                        )
                    ],
                    "span 1",
                ),
                {
                    "key": "document_name",
                    "label": "Nome do documento",
                    "type": "text",
                    "span": "span 1",
                    "ph": "Comprovante de Pagamento de Salário — Fulano",
                },
                {
                    "key": "notes",
                    "label": "Observação",
                    "type": "text",
                    "span": "span 2",
                    "value": "comprovante oficial do banco (anexado à mão)",
                },
                {"key": "file", "label": "PDF do comprovante*", "type": "file", "span": "span 2"},
            ],
        }
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.warning("kit-anexar-comprovante: %s", exc)

    out["kit-entrega-preparar"] = {
        "title": "Preparar entrega de kit",
        "sub": "Monta o pacote de entrega (ZIP/links) do kit do condomínio. Não envia nada.",
        "cta": "Preparar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/gedeon/kits/entrega/preparar",
            "query": True,
            "okMsg": "Entrega preparada",
            "showResult": True,
        },
        "fields": [
            selecionar("condominio", "Condomínio*", opts),
            {"key": "competencia", "label": "Competência (AAAA-MM)", "type": "text", "span": "span 1", "ph": comp},
        ],
    }
    out["kit-entrega-marcar"] = {
        "title": "Marcar kit como entregue",
        "sub": "Registra que o kit chegou ao cliente e por qual canal. Só registra.",
        "cta": "Marcar",
        "type": "form",
        "submit": {"endpoint": "/api/v1/gedeon/kits/entrega/marcar", "okMsg": "Entrega registrada"},
        "fields": [
            selecionar("condominio", "Condomínio*", opts),
            {"key": "competencia", "label": "Competência (AAAA-MM)", "type": "text", "span": "span 1", "ph": comp},
            selecionar(
                "canal",
                "Canal*",
                [
                    {"value": v, "label": l}
                    for v, l in (
                        ("email", "E-mail"),
                        ("whatsapp", "WhatsApp"),
                        ("drive", "Google Drive"),
                        ("presencial", "Presencial"),
                    )
                ],
                "span 1",
            ),
            {"key": "obs", "label": "Observação", "type": "textarea", "span": "span 2"},
        ],
    }
    out["kit-faturar"] = {
        "title": "Faturar kit (boleto)",
        "sub": "Emite a cobrança do kit no banco. A NFS-e NÃO sai por aqui: o caminho pelo provedor antigo (Ábaco) foi desligado; a nota vai pelo Portal Nacional.",
        "cta": "Faturar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/gedeon/kits/faturar",
            "okMsg": "Faturamento disparado",
            "showResult": True,
            "confirm": "Emite boleto REAL no banco para este condomínio. Confirma?",
        },
        "fields": [
            selecionar("condominio", "Condomínio*", opts),
            {"key": "competencia", "label": "Competência (AAAA-MM)", "type": "text", "span": "span 1", "ph": comp},
            selecionar("tipo", "O que emitir*", [{"value": "boleto", "label": "Boleto (Inter/Cora)"}], "span 1"),
            selecionar(
                "confirmar",
                "Modo*",
                [{"value": "false", "label": "Só simular (padrão)"}, {"value": "true", "label": "EMITIR de verdade"}],
                "span 2",
            ),
        ],
    }
    out["kit-checklist-evento"] = {
        "title": "Registrar evento no checklist do kit",
        "sub": "Admissão, demissão, afastamento, férias… o que muda o kit da competência.",
        "cta": "Registrar",
        "type": "form",
        "submit": {"endpoint": "/api/v1/gedeon/kits/checklist", "okMsg": "Evento registrado"},
        "fields": [
            selecionar("condominio", "Condomínio*", opts),
            {"key": "competencia", "label": "Competência (AAAA-MM)", "type": "text", "span": "span 1", "ph": comp},
            selecionar(
                "tipo",
                "Tipo*",
                [
                    {"value": v, "label": v.capitalize()}
                    for v in ("admissao", "demissao", "afastamento", "ferias", "substituicao", "outro")
                ],
                "span 1",
            ),
            {"key": "funcionario", "label": "Funcionário", "type": "text", "span": "span 1"},
            {"key": "data", "label": "Data", "type": "date", "span": "span 1"},
            {"key": "descricao", "label": "Descrição*", "type": "textarea", "span": "span 2"},
        ],
    }


def _lista(res) -> bool:
    from modules.operacional.controllers.redesign_builders._ligar_generico import _lista_em

    return bool(_lista_em(res))


async def _ligar_lote3_20260908(db, out: dict) -> None:
    """LIGAR lote 3 (08/09/2026): rotas que existiam sem tela. Cada bloco é independente (try/except + rollback)."""
    import logging as _lg

    from sqlalchemy import text as _T  # noqa: N812  # alias curto pré-existente, usado em todo o arquivo

    from modules.operacional.controllers.redesign_builders._ligar_generico import (
        chamar,
        painel_de_dict,
        selecionar,
        tabela_de_lista,
    )
    from modules.operacional.controllers.redesign_data_controller import _helpers, b, t

    _log = _lg.getLogger(__name__)
    _, _safe, tbl = _helpers(db)
    _SN = [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}]

    def _fd(v, fmt="%d/%m/%Y"):
        try:
            return v.strftime(fmt) if v else "—"
        except Exception:  # noqa: BLE001
            return str(v or "—")

    async def _n(sql):
        try:
            return (await db.execute(_T(sql))).scalar() or 0
        except Exception:  # noqa: BLE001
            await db.rollback()
            return 0

    try:  # GET /ged/config/document-types
        from modules.ged.controllers import (
            ged_config_controller as Gc,  # noqa: N812  # alias curto pré-existente, usado em todo o arquivo
        )

        res = await chamar(Gc.get_document_types, db)
        out["ged-tipos-documento"] = tabela_de_lista(
            "GED — tipos de documento",
            "Catálogo de tipos usado nos kits (obrigatório/ativo) · fonte: ged_document_types",
            res,
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _log.warning("ged-tipos-documento: %s", exc)
    try:  # GET/POST /ged/coleta-automatica
        row = (
            await db.execute(
                _T(
                    "SELECT enabled, cron_expr, timezone, last_run, last_status, updated_at, updated_by FROM ged_coleta_config ORDER BY id LIMIT 1"
                )
            )
        ).first()
        painel = {
            "ligada": bool(row[0]) if row else False,
            "cron": row[1] if row else None,
            "fuso": row[2] if row else None,
            "ultima_execucao": _fd(row[3], "%d/%m/%Y %H:%M") if row and row[3] else "nunca",
            "ultimo_status": row[4] if row else None,
            "atualizado_em": _fd(row[5], "%d/%m/%Y %H:%M") if row and row[5] else None,
            "atualizado_por": row[6] if row else None,
        }
        out["ged-coleta-automatica"] = painel_de_dict(
            "GED — coleta automática",
            "Robô que busca guias/notas nos portais todo mês (tarefa auto_collect_task lê esta configuração) · fonte: ged_coleta_config",
            painel,
            kpis_de=["ligada", "cron", "ultima_execucao", "ultimo_status"],
        )
        out["ged-coleta-configurar"] = {
            "title": "GED — configurar coleta automática",
            "sub": "Liga/desliga o robô e define o cron (ex.: 0 6 21 * * = dia 21 às 06:00). É a configuração que a tarefa Celery lê — diferente do 'agendamento de envio' dos kits.",
            "cta": "Salvar",
            "type": "form",
            "submit": {
                "endpoint": "/api/v1/ged/coleta-automatica",
                "okMsg": "Configuração salva. Recarregue.",
                "showResult": True,
            },
            "fields": [
                selecionar("enabled", "Ligada?", _SN, "span 1"),
                {
                    "key": "cron_expr",
                    "label": "Cron*",
                    "type": "text",
                    "span": "span 1",
                    "value": (row[1] if row else "0 6 21 * *") or "0 6 21 * *",
                },
            ],
        }
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _log.warning("ged-coleta: %s", exc)
    try:  # POST /gedeon/cnd/emitir + POST /gedeon/cnd/upload
        # DEFEITO MEDIDO 28/09/2026 — o formulário oferecia uma palavra que o validador recusa:
        # este form mandava document_type="federal"/"caixa", mas gedeon/cnd_controller.py:169 faz
        # `if document_type not in PORTAL_OFICIAL` e as CHAVES de PORTAL_OFICIAL (:32-42) são
        # "certidao_negativa_federal"/"certidao_negativa_fgts" → 2 de 2 envios do payload antigo
        # davam HTTP 400 "document_type inválido p/ upload manual"; 2 de 2 do novo passam (medido
        # chamando a validação e o endpoint com PDF de teste). Confirmação cruzada: :174 faz
        # {v: k for k, v in DOCTYPE.items()}.get(document_type) — só resolve recebendo o doctype.
        # 2º defeito: o CNPJ vinha FIXO da Patrimonial (WHERE slug='conecta_patrimonial'), e a
        # certidão que falta é a da ELETRÔNICA — 35710481000103, FGTS venceu em 2026-09-17
        # (-11 dias na medição), enquanto a da Patrimonial estava válida. A tela não alcançava o
        # único caso que importava. Certidão é POR CNPJ → select das duas, sem default.
        from modules.gedeon.controllers.cnd_controller import PORTAL_OFICIAL  # leitura (arquivo de outro dono)

        empresas = (
            await db.execute(_T("SELECT cnpj, razao_social FROM empresas ORDER BY razao_social"))
        ).all()
        opc_empresa = [{"value": e[0], "label": f"{e[1]} — {e[0]}"} for e in empresas]
        links = " · ".join(f"{v['nome']}: {v['url']}" for v in PORTAL_OFICIAL.values())
        out["cnd-emitir"] = {
            "title": "Certidões — emitir pelo robô",
            "sub": "Enfileira a emissão para o robô (SEFAZ-AM, CNDT, Prefeitura). Federal e Caixa são manuais: emita no portal e suba o PDF ao lado. Escolha a empresa — a certidão é por CNPJ.",
            "cta": "Emitir",
            "type": "form",
            "submit": {
                "endpoint": "/api/v1/gedeon/cnd/emitir",
                "okMsg": "Emissão enfileirada — acompanhe em Certidões (CND).",
                "showResult": True,
            },
            "fields": [
                selecionar("cnpj", "Empresa (CNPJ)*", opc_empresa, "span 1"),
                {
                    "key": "portais",
                    "label": "Portais",
                    "type": "multiselect",
                    "span": "span 1",
                    "options": [
                        {"value": v, "label": l}
                        for v, l in (
                            ("sefaz_am", "SEFAZ-AM"),
                            ("cndt", "CNDT (TST)"),
                            ("prefeitura", "Prefeitura de Manaus"),
                        )
                    ],
                },
            ],
        }
        out["cnd-upload"] = {
            "title": "Certidões — subir PDF emitido manualmente",
            "sub": (
                "Federal (RFB/PGFN) e FGTS (Caixa) não têm robô: emita no portal oficial, suba o PDF aqui "
                "e a validade é lida do próprio documento. Portais — "
                + links
                + " (a página da Caixa abre com o CNPJ da Eletrônica preenchido; para a Patrimonial, troque o CNPJ na própria página)."
            ),
            "cta": "Enviar",
            "type": "form",
            "submit": {
                "endpoint": "/api/v1/gedeon/cnd/upload",
                "multipart": True,
                "okMsg": "Certidão registrada. Recarregue.",
                "showResult": True,
            },
            "fields": [
                selecionar(
                    "document_type",
                    "Tipo*",
                    # value = a CHAVE de PORTAL_OFICIAL (o que o validador aceita); label = legível
                    [{"value": k, "label": l} for k, l in (
                        ("certidao_negativa_federal", "Federal — RFB/PGFN"),
                        ("certidao_negativa_fgts", "FGTS — Caixa"),
                    )],
                    "span 1",
                ),
                selecionar("cnpj", "Empresa (CNPJ)*", opc_empresa, "span 1"),
                {"key": "file", "label": "PDF da certidão*", "type": "file", "span": "span 2"},
            ],
        }
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _log.warning("cnd: %s", exc)
    try:  # POST /whatsapp/send/certificate-alert
        out["certidoes-avisar"] = await tbl(
            "Certidões — avisar cliente por WhatsApp",
            "Avisa o síndico/cliente que uma certidão vence (ou venceu). Informe telefone e nome; o resto vem da certidão · fonte: ged_certidoes",
            "—",
            ["Certidão", "Tipo", "Validade", "Situação"],
            "2.2fr 1fr 0.9fr 1fr",
            "SELECT coalesce(name,'—'), coalesce(document_type,'—'), expiry_date, (expiry_date - current_date) FROM ged_certidoes WHERE expiry_date IS NOT NULL ORDER BY expiry_date ASC LIMIT 200",
            lambda r: [
                t(r[0][:60], 600, "#0F1B3A"),
                t(r[1]),
                t(_fd(r[2])),
                b(
                    "Vencida" if (r[3] or 0) < 0 else (f"Vence em {r[3]}d" if (r[3] or 0) <= 30 else "Válida"),
                    "bad" if (r[3] or 0) < 0 else "warn" if (r[3] or 0) <= 30 else "ok",
                ),
            ],
            actionsfn=lambda r: [
                {
                    "title": f"Avisar por WhatsApp — {r[0][:40]}",
                    "endpoint": "/api/v1/whatsapp/send/certificate-alert",
                    "method": "POST",
                    "btnLabel": "Avisar cliente",
                    "btnStyle": "outline",
                    "submitLabel": "Enviar WhatsApp",
                    "okMsg": "Aviso enviado.",
                    "fields": [
                        {"key": "phone", "label": "Telefone (com DDD)*", "type": "text", "span": "span 1"},
                        {"key": "client_name", "label": "Nome do cliente*", "type": "text", "span": "span 1"},
                        {
                            "key": "certificate_type",
                            "label": "Certidão",
                            "type": "text",
                            "span": "span 1",
                            "value": r[1],
                        },
                        {
                            "key": "expiry_date",
                            "label": "Validade",
                            "type": "text",
                            "span": "span 1",
                            "value": _fd(r[2]),
                        },
                        {
                            "key": "days_remaining",
                            "label": "Dias restantes",
                            "type": "number",
                            "span": "span 1",
                            "value": int(r[3] or 0),
                        },
                    ],
                }
            ],
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _log.warning("certidoes-avisar: %s", exc)


async def _ligar_lote4_20260908(db, out: dict) -> None:
    """LIGAR lote 4 (08/09/2026): rotas que existiam sem tela (vereditos B e C). Blocos independentes (try/except + rollback).
    Regra da casa: a página nunca chama Drive/robô/governo — leituras do Drive viram formulários GET que o usuário dispara."""
    import logging as _lg
    from datetime import date as _dt

    from sqlalchemy import text as _T  # noqa: N812  # alias curto pré-existente, usado em todo o arquivo

    from modules.operacional.controllers.redesign_data_controller import _helpers, b, t

    _log = _lg.getLogger(__name__)
    _, _safe, tbl = _helpers(db)
    _SN = [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}]
    hoje = _dt.today()  # noqa: F841  # pré-existente

    def _fd(v, fmt="%d/%m/%Y"):
        try:
            return v.strftime(fmt) if v else "—"
        except Exception:  # noqa: BLE001
            return str(v or "—")

    async def _n(sql):
        try:
            return (await db.execute(_T(sql))).scalar() or 0
        except Exception:  # noqa: BLE001
            await db.rollback()
            return 0

    def _consulta(key, titulo, sub, endpoint, fields, method="GET"):
        """Form de CONSULTA: dispara o GET com query e mostra o resultado (a página não chama nada ao abrir)."""
        out[key] = {
            "title": titulo,
            "sub": sub,
            "cta": "Consultar",
            "type": "form",
            "submit": {
                "endpoint": endpoint,
                "method": method,
                "query": True,
                "okMsg": "Consulta feita — veja o resultado.",
                "showResult": True,
            },
            "fields": fields,
        }

    try:  # GET /ged/kits/{kit_id} — documentos por kit, por SQL (a rota fica redundante)
        out["kit-documentos"] = await tbl(
            "Documentos por kit",
            f"{await _n('SELECT count(*) FROM ged_kit_documents')} documentos em kits · últimos 300 · «Ver documento» abre na tela · fonte: ged_kit_documents × ged_document_kits",
            "—",
            ["Kit", "Colaborador", "Documento", "Tipo", "Assinado", "Gerado em"],
            "0.8fr 1.8fr 2fr 1fr 0.8fr 0.9fr",
            "SELECT to_char(k.reference_month,'MM/YYYY'), coalesce(e.nome, d.employee_id::text, '—'), coalesce(d.document_name,'—'), coalesce(d.document_type,'—'), coalesce(d.is_signed,false), d.created_at, "
            "d.id, d.file_path, d.mime_type "
            "FROM ged_kit_documents d LEFT JOIN ged_document_kits k ON k.id=d.kit_id LEFT JOIN employees e ON e.id=d.employee_id ORDER BY d.created_at DESC LIMIT 300",
            lambda r: [
                t(r[0] or "—", 600, "#0F1B3A"),
                t(r[1][:36]),
                t(r[2][:50]),
                b(r[3].replace("_", " ").capitalize(), "info"),
                b("Sim" if r[4] else "Não", "ok" if r[4] else "mut"),
                t(_fd(r[5])),
            ],
            docsfn=lambda r: _chip_ver_documento(r[6], r[7], r[8], r[2]),
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _log.warning("kit-documentos: %s", exc)
    _consulta(
        "gedeon-panorama",
        "GEDEON — panorama dos kits",
        "Kits por condomínio, pendências e intercorrências da competência (AAAA-MM; vazio = mês anterior).",
        "/api/v1/gedeon/consultor/panorama",
        [{"key": "competencia", "label": "Competência (AAAA-MM)", "type": "text", "span": "span 1"}],
    )
    _consulta(
        "gedeon-alinhamento-dp",
        "GEDEON — alinhamento DP",
        "Folha do kit × espelho Sólides + afastamentos de um condomínio. Lê o Drive quando você clica.",
        "/api/v1/gedeon/kits/dp/alinhamento",
        [
            {"key": "condominio", "label": "Condomínio (nome da pasta)*", "type": "text", "span": "span 1"},
            {"key": "competencia", "label": "Competência (MM.AAAA)", "type": "text", "span": "span 1"},
        ],
    )
    _consulta(
        "gedeon-funcionarios",
        "GEDEON — funcionários da folha do condomínio",
        "Lista quem está na folha do kit (para a visão por funcionário). Lê o Drive quando você clica.",
        "/api/v1/gedeon/kits/funcionarios",
        [
            {"key": "condominio", "label": "Condomínio*", "type": "text", "span": "span 1"},
            {"key": "competencia", "label": "Competência (MM.AAAA)", "type": "text", "span": "span 1"},
        ],
    )
    _consulta(
        "gedeon-funcionario",
        "GEDEON — visão por funcionário",
        "Todos os documentos de uma pessoa no kit. Lê o Drive quando você clica.",
        "/api/v1/gedeon/kits/funcionario",
        [
            {"key": "funcionario", "label": "Funcionário*", "type": "text", "span": "span 2"},
            {"key": "condominio", "label": "Condomínio", "type": "text", "span": "span 1"},
            {"key": "competencia", "label": "Competência (MM.AAAA)", "type": "text", "span": "span 1"},
        ],
    )
    _consulta(
        "gedeon-assinaturas-pendentes",
        "GEDEON — quem não assinou VT/VR (Sólides)",
        "Pendências de assinatura dos recibos de VT/VR. Lê o Drive quando você clica.",
        "/api/v1/gedeon/kits/assinaturas",
        [
            {"key": "condominio", "label": "Condomínio", "type": "text", "span": "span 1"},
            {"key": "competencia", "label": "Competência (MM.AAAA)", "type": "text", "span": "span 1"},
        ],
    )


async def _ligar_lote5_20260908(db, out: dict, me=None) -> None:
    """LIGAR lote 5 (08/09/2026): rotas do people-management/users/SST que só existiam por API. Blocos independentes."""
    import logging as _lg
    from datetime import date as _dt

    from sqlalchemy import text as _T  # noqa: N812  # alias curto pré-existente, usado em todo o arquivo

    from modules.operacional.controllers.redesign_builders._ligar_generico import (
        selecionar,
    )
    from modules.operacional.controllers.redesign_data_controller import _helpers, b, t

    _log = _lg.getLogger(__name__)
    _, _safe, tbl = _helpers(db)
    _SN = [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}]
    hoje = _dt.today()  # noqa: F841  # pré-existente

    def _fd(v, fmt="%d/%m/%Y"):
        try:
            return v.strftime(fmt) if v else "—"
        except Exception:  # noqa: BLE001
            return str(v or "—")

    async def _n(sql):
        try:
            return (await db.execute(_T(sql))).scalar() or 0
        except Exception:  # noqa: BLE001
            await db.rollback()
            return 0

    async def _emps():
        try:
            return [
                {"value": str(i), "label": n}
                for i, n in (
                    await db.execute(_T("SELECT id, nome FROM employees WHERE status='ativo' ORDER BY nome LIMIT 400"))
                ).fetchall()
            ]
        except Exception:  # noqa: BLE001
            await db.rollback()
            return []

    def _consulta(key, titulo, sub, endpoint, fields, method="GET"):
        out[key] = {
            "title": titulo,
            "sub": sub,
            "cta": "Consultar",
            "type": "form",
            "submit": {
                "endpoint": endpoint,
                "method": method,
                "query": True,
                "okMsg": "Consulta feita — veja o resultado.",
                "showResult": True,
            },
            "fields": fields,
        }

    try:  # GET /ged/coleta-automatica/history — por SQL
        out["ged-coleta-historico"] = await tbl(
            "GED — histórico da coleta automática",
            f"{await _n('SELECT count(*) FROM ged_coleta_logs')} execuções · fonte: ged_coleta_logs",
            "—",
            ["Quando", "Tipo", "Status", "Disparo", "Duração", "Novos", "Onvio", "Kits", "Certidões", "Erros"],
            "1fr 0.7fr 0.7fr 0.8fr 0.6fr 0.5fr 0.5fr 0.5fr 0.6fr 1fr",
            "SELECT run_at, coalesce(run_type,'—'), coalesce(status,'—'), coalesce(triggered_by,'—'), duration_ms, coalesce(sync_novos,0), coalesce(onvio_matched,0), coalesce(kits_assembled,0), coalesce(certidoes_atualizadas,0), coalesce(erros::text,'') "
            "FROM ged_coleta_logs ORDER BY run_at DESC LIMIT 100",
            lambda r: [
                t(_fd(r[0], "%d/%m/%Y %H:%M")),
                t(r[1]),
                b(
                    r[2].capitalize(),
                    "ok"
                    if r[2] in ("ok", "success", "sucesso")
                    else "bad"
                    if r[2] in ("erro", "error", "failed")
                    else "info",
                ),
                t(r[3]),
                t(f"{(r[4] or 0) // 1000}s"),
                t(str(r[5])),
                t(str(r[6])),
                t(str(r[7])),
                t(str(r[8])),
                t((r[9] or "")[:40] or "—"),
            ],
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _log.warning("ged-coleta-historico: %s", exc)
    out["ged-coleta-executar"] = {  # POST /ged/coleta-automatica/run
        "title": "GED — executar coleta agora",
        "sub": "Dispara a coleta (Onvio → kits → certidões) fora do cron. Roda no Celery; acompanhe no histórico.",
        "cta": "Executar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/ged/coleta-automatica/run",
            "okMsg": "Coleta enfileirada — veja o histórico em alguns minutos.",
            "showResult": True,
        },
        "fields": [
            {"key": "mes_ref", "label": "Mês de referência (AAAA-MM, opcional)", "type": "text", "span": "span 1"},
            selecionar("force_resync", "Forçar ressincronização?", _SN, "span 1"),
        ],
    }


# =============================================================================
# 29/09/2026 · AS DUAS AÇÕES QUE TIRAM A PYETRA DO TERMINAL
#
# Até hoje, conferir um kit torto e resolver quem ficou sem condomínio só era possível por
# script meu. Ela não usa terminal — então a capacidade existia e não era dela.
#
# A regra NÃO mora aqui: mora em `kit_roster_service`, a mesma que o script consome. Duas
# cópias divergiriam na primeira mudança, e esta regra mudou três vezes em um dia.
# =============================================================================
router = APIRouter()


def _comp_de_texto(txt: str) -> date:
    """«08/2026» → date(2026, 8, 1). Recusa o resto em vez de adivinhar.

    Aceita barra E ponto porque o Gedeon usa MM.AAAA e esta tela usa MM/AAAA — duas convenções
    vivas no mesmo produto, e quem erraria o separador é a pessoa, não o código.
    """
    m = re.match(r"^\s*(\d{1,2})\s*[/.]\s*(\d{4})\s*$", str(txt or ""))
    if not m:
        raise HTTPException(
            status_code=400,
            detail="Informe a competência como MM/AAAA (ex.: 08/2026).",
        )
    mes, ano = int(m.group(1)), int(m.group(2))
    if not 1 <= mes <= 12:
        raise HTTPException(status_code=400, detail=f"Mês inválido: {mes}.")
    return date(ano, mes, 1)


async def _condominios_do_mes(db) -> list[dict]:
    """Opções de condomínio para a competência anterior — só quem teve batida no mês."""
    from starlette.concurrency import run_in_threadpool

    from core.database.session import get_sync_db
    from modules.people_management.ged.services.kit_roster_service import condominios_conhecidos

    ant = date.today().replace(day=1) - timedelta(days=1)

    def _ler() -> list[str]:
        with get_sync_db() as sdb:
            return condominios_conhecidos(sdb, ant)

    try:
        return [{"value": c, "label": c} for c in await run_in_threadpool(_ler)]
    except Exception as exc:  # noqa: BLE001 — select vazio é melhor que tela que não abre
        _log.warning("condominios do mes: %s", exc)
        return []


async def _sem_condominio_opcoes(db, comp_iso: str) -> list[dict]:
    """Opções de colaborador para quem bateu no mês e o sistema não sabe onde."""
    from starlette.concurrency import run_in_threadpool

    from core.database.session import get_sync_db
    from modules.people_management.ged.services.kit_roster_service import sem_condominio

    comp = date.fromisoformat(comp_iso)

    def _ler() -> list[tuple[str, str, int]]:
        with get_sync_db() as sdb:
            return [(e, n, q) for e, (n, q) in sem_condominio(sdb, comp).items()]

    try:
        itens = sorted(await run_in_threadpool(_ler), key=lambda x: -x[2])
    except Exception as exc:  # noqa: BLE001
        _log.warning("sem_condominio opcoes: %s", exc)
        return []
    if not itens:
        # Lista vazia é RESULTADO, não erro: diz isso em vez de deixar um select mudo.
        return [{"value": "", "label": "— ninguém pendente nesta competência —"}]
    return [{"value": e, "label": f"{n} ({q} batida(s) no mês)"} for e, n, q in itens]


@router.post("/action/kits-conferir")
async def rd_kits_conferir(
    current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)
) -> dict:
    """Confere os kits da competência contra quem realmente trabalhou lá. ENSAIO por padrão.

    ⭐ `acao=ensaio` é o default no builder E aqui: quem chamar sem dizer nada NÃO altera nada.
    Ato destrutivo nunca é o caminho de menos digitação.

    Remove apenas o VÍNCULO pessoa×kit em `ged_kit_documents`. O PDF no disco não é tocado e o
    documento continua existindo para a pessoa — o que estava errado era ele estar no kit de
    outro condomínio (medido: o EULER FELIPE aparecia em TRÊS, dois clientes recebendo folha de
    pagamento de um estranho).

    Guarda em `ged_kit_documents_removidos_<data>_tela` antes de remover e confere por LEITURA
    POSTERIOR: «DELETE n» do driver não é prova, e isso já custou caro nesta casa.
    """
    from starlette.concurrency import run_in_threadpool

    from core.database.session import get_sync_db
    from modules.people_management.ged.services.kit_roster_service import (
        aplicar_reconciliacao,
        plano_reconciliacao,
    )

    if (getattr(current_user, "role", "") or "") not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="Acesso restrito à administração e ao DP.")

    comp = _comp_de_texto(payload.get("competencia"))
    acao = (str(payload.get("acao") or "ensaio")).strip().lower()
    if acao not in ("ensaio", "aplicar"):
        raise HTTPException(status_code=400, detail="Ação deve ser «ensaio» ou «aplicar».")
    quem = (
        getattr(current_user, "name", None) or getattr(current_user, "email", None) or "desconhecido"
    )

    def _trabalho() -> dict:
        # ⭐ O ato destrutivo mora no SERVIÇO, não aqui. Antes havia um bloco de apagar nesta
        # ação e outro no script do terminal — duas cópias de um DELETE divergem na primeira
        # correção, e a que fica atrás é a que apaga errado.
        with get_sync_db() as sdb:
            if acao != "aplicar":
                return plano_reconciliacao(sdb, comp)
            try:
                return aplicar_reconciliacao(sdb, comp, quem)
            except RuntimeError as exc:  # aborto do serviço (backup incompleto, leitura não confere)
                raise HTTPException(status_code=500, detail=str(exc)) from exc

    plano = await run_in_threadpool(_trabalho)
    r = plano["resumo"]
    rows: list[dict] = []
    for x in plano["linhas"]:
        rows.append(
            {
                "cells": [
                    t(x["condominio"][:34], 600, "#0F1B3A"),
                    t(x["pessoa"][:32]),
                    b(x["acao"][:38], "bad" if x["employee_id"] else "mut"),
                    t(x["motivo"], 400, "#475569"),
                ]
            }
        )
    for x in plano["sem_condominio"]:
        rows.append(
            {
                "cells": [
                    t("— sem condomínio —", 600, "#B45309"),
                    t(x["pessoa"][:32]),
                    b("precisa de decisão sua", "warn"),
                    t(
                        f"{x['batidas']} batida(s) no mês e nenhuma gravou o posto. Use «Definir "
                        f"condomínio de quem ficou sem» — o sistema não deduz, porque deduzir "
                        f"pela alocação já pôs gente no condomínio errado.",
                        400,
                        "#B45309",
                    ),
                ]
            }
        )
    aplicado = plano.get("aplicado")
    msg = (
        f"Competência {r['competencia']} · {r['kits']} kit(s) de cliente · "
        f"{r['pessoas_no_roster']} pessoa(s) no roster · "
        + (
            (
                f"{aplicado} linha(s) de documento removida(s), reversível em "
                f"`{plano.get('backup')}`. "
                if aplicado
                # Zero removido não ganha frase de backup: «reversível em None» é ruído que
                # faz a pessoa procurar uma tabela que não existe.
                # «Já estão de acordo» seria contradição quando há pendência: a frase e o
                # aviso de pendência sairiam na MESMA mensagem dizendo coisas opostas.
                else (
                    "Nada a remover — nenhum vínculo indevido entre os que o sistema sabe julgar. "
                    if r["sem_condominio"]
                    else "Nada a remover — os kits estão de acordo com quem trabalhou. "
                )
            )
            if aplicado is not None
            else f"ENSAIO — nada foi alterado. {r['a_remover']} vínculo(s) a remover. "
        )
        + (f"{r['kits_sem_roster']} kit(s) sem roster (não tocados). " if r["kits_sem_roster"] else "")
        + (f"⚠️ {r['sem_condominio']} pessoa(s) sem condomínio." if r["sem_condominio"] else "Ninguém sem condomínio.")
    )
    return {
        "ok": True,
        "message": msg,
        "tabela": {
            "cols": ["Condomínio", "Colaborador", "O que acontece", "Por quê"],
            "grid": "1.1fr 1.1fr 1fr 2.4fr",
            "rows": rows,
        },
    }


@router.post("/action/kit-definir-condominio")
async def rd_kit_definir_condominio(
    current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)
) -> dict:
    """Grava o condomínio de quem o dado não sabe. É decisão HUMANA, e fica com nome e data.

    Por que existe: o roster acha o condomínio pelo `posto_id` gravado na batida e resolve a
    maioria. Quem não tem posto em nenhuma batida do mês não tem fonte — e a alternativa
    tentadora (deduzir pela alocação) é justamente o erro que o Jordan pegou: a alocação diz
    onde a pessoa está HOJE, e as datas dela são ficção.

    Grava em `kit_condominio_manual`, chave (pessoa, competência) — a mesma pessoa não tem dois
    condomínios no mês. Reenviar CORRIGE em vez de duplicar, porque errar e refazer é normal.
    """
    from starlette.concurrency import run_in_threadpool

    from core.database.session import get_sync_db
    from modules.people_management.ged.services.kit_roster_service import (
        TABELA_MANUAL,
        condominios_conhecidos,
    )

    if (getattr(current_user, "role", "") or "") not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="Acesso restrito à administração e ao DP.")

    comp = _comp_de_texto(payload.get("competencia"))
    eid = str(payload.get("employee_id") or "").strip()
    cond = str(payload.get("condominio") or "").strip()
    motivo = str(payload.get("motivo") or "").strip()[:300]
    if not eid:
        raise HTTPException(status_code=400, detail="Escolha o colaborador.")
    if not cond:
        raise HTTPException(status_code=400, detail="Escolha o condomínio.")
    quem = (
        getattr(current_user, "name", None) or getattr(current_user, "email", None) or "desconhecido"
    )

    def _gravar() -> dict:
        with get_sync_db() as sdb:
            # O condomínio tem de ser um que EXISTIU na competência. Sem esta trava, um nome
            # digitado ou colado de outro mês criaria um oitavo grupo silencioso — e o Green
            # Hills (aberto em 01/09) é a prova de que "condomínio que existe" não basta:
            # precisa ter existido NAQUELE mês.
            validos = condominios_conhecidos(sdb, comp)
            if cond not in validos:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"«{cond}» não teve ninguém batendo ponto em {comp:%m/%Y}. "
                        f"Opções desta competência: {', '.join(validos) or '(nenhuma)'}."
                    ),
                )
            nome = sdb.execute(
                text("SELECT nome FROM employees WHERE id::text = :e"), {"e": eid}
            ).scalar()
            if not nome:
                raise HTTPException(status_code=404, detail="Colaborador não encontrado.")
            sdb.execute(
                text(
                    f"INSERT INTO {TABELA_MANUAL} "  # noqa: S608 — constante do serviço
                    " (employee_id, competencia, condominio, motivo, definido_por) "
                    "VALUES (CAST(CAST(:e AS text) AS uuid), :c, :cond, :m, :q) "
                    "ON CONFLICT (employee_id, competencia) DO UPDATE SET "
                    "  condominio = EXCLUDED.condominio, motivo = EXCLUDED.motivo, "
                    "  definido_por = EXCLUDED.definido_por, "
                    "  definido_em = (now() AT TIME ZONE 'America/Manaus')"
                ),
                {"e": eid, "c": comp, "cond": cond, "m": motivo or None, "q": quem},
            )
            sdb.commit()
            # PROVA POR LEITURA POSTERIOR
            conf = sdb.execute(
                text(
                    f"SELECT condominio FROM {TABELA_MANUAL} "  # noqa: S608
                    " WHERE employee_id::text = :e AND competencia = :c"
                ),
                {"e": eid, "c": comp},
            ).scalar()
            if conf != cond:
                raise HTTPException(
                    status_code=500,
                    detail=f"A gravação não se confirmou na leitura (achei «{conf}»).",
                )
            return {"nome": nome, "cond": cond}

    r = await run_in_threadpool(_gravar)
    return {
        "ok": True,
        "message": (
            f"{r['nome']} → {r['cond']} em {comp:%m/%Y}, registrado com o seu nome. "
            "Rode «Conferir kits do mês» de novo para ver o efeito."
        ),
    }
