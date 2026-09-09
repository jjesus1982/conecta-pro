"""Documentos/GED (T1) — override do _build_documentos + telas kits e pastas (leitura real).

A completude do kit vem do GOOGLE DRIVE, não do banco — decisão do Jordan em 15/08/2026.
Ver o comentário em `_visao()` para os números que motivaram.
"""

import asyncio
from datetime import date, datetime

import logging
from modules.operacional.controllers.redesign_data_controller import (
    IC,
    S,
    _helpers,
    _scalar,
    b,
    doc,
    t,
)


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


SLUG = "documentos"

logger = logging.getLogger(__name__)
_ICO_D = "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6"

EXTRA_MENU: list[dict] = [
    {"id": "ged-coleta-historico", "label": "GED — histórico da coleta", "icon": "M3 3v18h18"},
    {"id": "ged-coleta-executar", "label": "GED — executar coleta agora", "icon": "M3 3v18h18"},
    {"id": "kit-documentos", "label": "Documentos por kit", "icon": "M3 3v18h18"},
    {"id": "gedeon-panorama", "label": "GEDEON — panorama", "icon": "M3 3v18h18"},
    {"id": "gedeon-alinhamento-dp", "label": "GEDEON — alinhamento DP", "icon": "M3 3v18h18"},
    {"id": "gedeon-funcionarios", "label": "GEDEON — funcionários da folha", "icon": "M3 3v18h18"},
    {"id": "gedeon-funcionario", "label": "GEDEON — visão por funcionário", "icon": "M3 3v18h18"},
    {"id": "gedeon-assinaturas-pendentes", "label": "GEDEON — VT/VR não assinados", "icon": "M3 3v18h18"},
    {"id": "ged-tipos-documento", "label": "GED — tipos de documento", "icon": "M3 3v18h18"},
    {"id": "ged-coleta-automatica", "label": "GED — coleta automática", "icon": "M3 3v18h18"},
    {"id": "ged-coleta-configurar", "label": "GED — configurar coleta", "icon": "M3 3v18h18"},
    {"id": "cnd-emitir", "label": "Certidões — emitir (robô)", "icon": "M3 3v18h18"},
    {"id": "cnd-upload", "label": "Certidões — subir PDF", "icon": "M3 3v18h18"},
    {"id": "certidoes-avisar", "label": "Certidões — avisar cliente", "icon": "M3 3v18h18"},
    {"id": "kits-conferencia", "label": "Conferência dos kits (ATLAS)", "icon": "M3 3v18h18"},
    {"id": "kits-assinaturas-pendentes", "label": "Central de assinaturas", "icon": "M3 3v18h18"},
    {"id": "kits-entrega-status", "label": "Entrega dos kits (status)", "icon": "M3 3v18h18"},
    {"id": "kit-entrega-preparar", "label": "Preparar entrega de kit", "icon": "M3 3v18h18"},
    {"id": "kit-entrega-marcar", "label": "Marcar kit como entregue", "icon": "M3 3v18h18"},
    {"id": "assinaturas-empresa-lote", "label": "Assinar em lote (empresa)", "icon": "M3 3v18h18"},
    {"id": "kit-faturar", "label": "Faturar kit (boleto)", "icon": "M3 3v18h18"},
    {"id": "kit-checklist-evento", "label": "Registrar evento no checklist do kit", "icon": "M3 3v18h18"},
    {"id": "gedeon-perguntar", "label": "Consultor GEDEON", "icon": _ICO_D},
    {"id": "gedeon-intercorrencia", "label": "Registrar intercorrência", "icon": _ICO_D},
    {"id": "sophia-indexar", "label": "Indexar acervo (SOPHIA)", "icon": _ICO_D},
    {"id": "kits-montar", "label": "Montar kits do mês", "icon": _ICO_D},
    {"id": "kits-pdfs-mes", "label": "Gerar PDFs dos kits do mês", "icon": _ICO_D},
    {"id": "kit-real-mes", "label": "Gerar kits reais do mês", "icon": _ICO_D},
    {"id": "sophia-reindexar", "label": "Re-indexar acervo (SOPHIA v2)", "icon": _ICO_D},
    {"id": "ingestao-historica", "label": "Ingestão histórica do Drive", "icon": _ICO_D},
    {"id": "sophia-perguntar", "label": "Perguntar ao acervo (SOPHIA)", "icon": _ICO_D},
    {"id": "gedeon-perguntar-arquivo", "label": "Consultor GEDEON — com anexo", "icon": _ICO_D},
    {"id": "hermes-classificar", "label": "Classificar documento (Hermes)", "icon": _ICO_D},
    {"id": "ged-agendamento", "label": "Agendamento de envio do GED", "icon": _ICO_D},
    {
        "id": "intercorrencias",
        "label": "Intercorrências do mês",
        "icon": "M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11",
    },
    {"id": "ged-agendamento-pm", "label": "Agendamento do GED (envio)", "icon": _ICO_D},
    {"id": "assinatura-solicitar", "label": "Solicitar assinatura", "icon": _ICO_D},
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
    # Arquivos (ged_kit_documents) — SEM download por-doc: a rota /ged/documents/{id}/download
    # serve ged_documents (tabela VAZIA), não ged_kit_documents. Download real = ZIP do kit (abaixo).
    # Gap registrado na MATRIZ: falta rota servindo ged_kit_documents.file_path por-doc (759 têm arquivo).
    await safe(
        "arquivos",
        tbl(
            "Arquivos",
            f"{n_ged} documentos",
            "Enviar documento",
            ["Documento", "Tipo", "Colaborador", "Assinado"],
            "2fr 1.4fr 1.6fr 0.9fr",
            "SELECT coalesce(g.document_name,'—'), coalesce(g.document_type::text,'—'), coalesce(e.nome,'—'), g.is_signed "
            "FROM ged_kit_documents g LEFT JOIN employees e ON e.id=g.employee_id ORDER BY g.created_at DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t((r[1] or "—").replace("_", " ")),
                t(r[2]),
                b("Assinado", "ok") if r[3] else b("Pendente", "warn"),
            ],
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
            {"key": "area", "label": "Área*", "type": "text", "span": "span 1", "ph": "Ex.: folha, documentos, kit"},
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
    out["kits-montar"] = {
        "title": "Montar kits do mês",
        "sub": "Cria o kit dos clientes ativos que ainda não têm kit no mês corrente. Não sobrescreve kit existente.",
        "cta": "Montar",
        "type": "form",
        "submit": {"endpoint": "/api/v1/ged/kits/montar", "okMsg": "Kits montados"},
        "fields": [],
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
    out["kits-pdfs-mes"] = {
        "title": f"Gerar PDFs dos kits — {_hoje.month:02d}/{_hoje.year}",
        "sub": "Gera os PDFs de todos os kits da competência corrente. A competência é a de "
        "hoje, não a do sistema (o padrão da rota está preso em março/2026).",
        "cta": "Gerar PDFs",
        "type": "form",
        "submit": {
            "endpoint": f"/api/v1/ged/kits/generate-all-pdfs?reference_month={_comp}-01",
            "okMsg": "Geração dos PDFs disparada",
            "confirm": f"Gera os PDFs de TODOS os kits de {_hoje.month:02d}/{_hoje.year}. Confirma?",
        },
        "fields": [],
    }
    out["kit-real-mes"] = {
        "title": f"Gerar kits reais — {_hoje.month:02d}/{_hoje.year}",
        "sub": "Monta os kits reais (com documento de verdade) da competência corrente.",
        "cta": "Gerar kits",
        "type": "form",
        "submit": {
            "endpoint": f"/api/v1/ged/kit-real/gerar-todos?mes={_hoje.month}&ano={_hoje.year}",
            "okMsg": "Geração dos kits reais disparada",
            "confirm": f"Gera os kits reais de TODOS os clientes em {_hoje.month:02d}/{_hoje.year}. Confirma?",
        },
        "fields": [],
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
        # multipart + query: o ARQUIVO vai no corpo, os demais campos na URL. Foi para isto
        # que o submit.query passou a valer também no caminho multipart.
        "submit": {
            "endpoint": "/api/v1/gedeon/consultor/perguntar-arquivo",
            "multipart": True,
            "query": True,
            "okMsg": "Análise concluída",
            "showResult": True,
        },
        "fields": [
            {"key": "arquivo", "label": "Arquivo*", "type": "file", "span": "span 2"},
            {"key": "area", "label": "Área*", "type": "text", "span": "span 1", "ph": "Ex.: folha, documentos"},
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
            actionsfn=lambda r: None
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
            ],
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
    from modules.gedeon.controllers import orquestrador_controller as O
    from modules.operacional.controllers.redesign_builders._ligar_generico import chamar, painel_de_dict, selecionar, tabela_de_lista
    comp = O._competencia_anterior()
    try:
        conds = await chamar(O.condominios_elegiveis_endpoint, db)
        lista = conds if isinstance(conds, list) else (conds or {}).get("condominios", [])
        opts = [{"value": (c.get("nome") if isinstance(c, dict) else str(c)), "label": (c.get("nome") if isinstance(c, dict) else str(c))} for c in lista]
    except Exception as exc:  # noqa: BLE001
        logger.warning("kits: condominios elegíveis: %s", exc); opts = []
    if not opts:  # o serviço pode falhar fora (Drive/SSL): cai para os clientes do GED, que é a lista real dos kits
        try:
            from sqlalchemy import text as _t
            opts = [{"value": n, "label": n} for (n,) in (await db.execute(_t("SELECT name FROM ged_clients WHERE coalesce(is_active,true) ORDER BY name LIMIT 100"))).fetchall()]
        except Exception:  # noqa: BLE001
            await db.rollback()
    # Leitura SEM tocar o Drive na página: a conferência ATLAS vem só do cache em memória do
    # processo (o lote percorre o Drive e segura um lock — isso é para a API/MCP, não para um GET
    # de tela); a completude já está na tela "visao" (mesmo cache Redis). Assinaturas = banco.
    try:
        cached = O._ATLAS_LOTE_CACHE.get(comp)
        if cached:
            selos = cached[1].get("selos") or cached[1].get("condominios") or cached[1]
            linhas = [{"condominio": k, **({kk: vv for kk, vv in v.items() if not isinstance(vv, (list, dict))} if isinstance(v, dict) else {"selo": v})} for k, v in (selos.items() if isinstance(selos, dict) else [])]
            out["kits-conferencia"] = tabela_de_lista(f"Conferência dos kits — {comp}", "Selo ATLAS por condomínio (última conferência em cache, ~90 s).", linhas)
        else:
            out["kits-conferencia"] = painel_de_dict(f"Conferência dos kits — {comp}", "Nenhuma conferência em cache neste processo.",
                                                    {"como_conferir": "peça ao assistente 'conferir os kits do mês' (MCP consultar_kits) ou chame GET /gedeon/kits/conferir-lote — a varredura lê o Drive e leva ~20 s"})
    except Exception as exc:  # noqa: BLE001
        logger.warning("kits conferencia: %s", exc)
    # Assinaturas pendentes pelo BANCO (assinatura universal), não pelo Drive: o serviço do kit lê o
    # Drive numa thread e derrubou o worker (08/09/2026, "free(): corrupted unsorted chunks").
    try:
        from sqlalchemy import text as _t
        # 09/09: virou a CENTRAL DE ASSINATURAS do gestor — o que espera a EMPRESA vem primeiro, com o botão "Assinar"
        # (POST /signatures/{id}/sign, papel admin/operator) e o PDF para ler antes. O que espera o funcionário é
        # assinado por ele no portal (meu-espaço); aqui só aparece para cobrança.
        rows = (await db.execute(_t(
            "SELECT coalesce(signer_name,'—'), lower(coalesce(signer_type::text,'—')), coalesce(document_type,'—'), coalesce(title, reference_code, '—'), "
            "status::text, expires_at, id::text, access_token FROM sig_signature_requests WHERE status::text IN ('PENDING','SIGNING') "
            "AND (expires_at IS NULL OR expires_at > now()) ORDER BY (lower(signer_type::text) = 'company') DESC, created_at DESC LIMIT 300"))).fetchall()
        linhas = [{"signatario": r[0], "papel": {"company": "EMPRESA (você)", "employee": "funcionário (portal)", "customer": "cliente"}.get(r[1], r[1]),
                   "documento": r[3], "tipo": r[2], "status": r[4], "expira_em": r[5].strftime("%d/%m") if r[5] else "—", "_id": r[6], "_papel": r[1], "_tok": r[7]} for r in rows]
        n_emp = sum(1 for l in linhas if l["_papel"] == "company")
        out["kits-assinaturas-pendentes"] = tabela_de_lista(
            "Central de assinaturas", f"{n_emp} documento(s) esperam a SUA assinatura · {len(linhas) - n_emp} esperam funcionários (portal) ou clientes. Assinatura eletrônica com hash SHA-256; o PDF assinado volta para o kit na hora.",
            linhas, cols=["signatario", "papel", "documento", "tipo", "status", "expira_em"],
            docsfn=lambda it: [doc("Ver PDF", f"/api/v1/signatures/{it['_id']}/documento", fmt="pdf", mode="blob")],
            actionsfn=lambda it: [{
                "title": f"Assinar como empresa — {it['documento']}", "sub": "Registra a sua assinatura eletrônica (nome, CPF/CNPJ da empresa, data, hash) e carimba o selo no PDF.",
                "endpoint": f"/api/v1/signatures/{it['_id']}/sign", "method": "POST", "btnLabel": "Assinar", "submitLabel": "Assinar agora",
                "btnStyle": "primary", "okMsg": "Assinado. O kit já aponta para o PDF assinado. Recarregue.", "fields": []}] if it["_papel"] == "company" else [])
        out["assinaturas-empresa-lote"] = {
            "title": "Assinar tudo que espera a empresa", "sub": f"{n_emp} documento(s) pendentes da sua assinatura. Assina em lote, um a um pelo mesmo motor; um documento com problema não derruba os outros.",
            "cta": "Assinar em lote", "type": "form",
            "submit": {"endpoint": "/api/v1/signatures/empresa/assinar-lote", "okMsg": "Lote assinado. Recarregue a central.", "showResult": True},
            "fields": [{"key": "limite", "label": "Máximo de documentos neste lote", "type": "number", "span": "span 1", "value": "60"}]}
    except Exception as exc:  # noqa: BLE001
        await db.rollback(); logger.warning("kits assinaturas: %s", str(exc)[:120])
    try:
        from sqlalchemy import text as _t
        rows = (await db.execute(_t(
            "SELECT g.name, to_char(k.reference_month,'MM/YYYY'), k.sent_at, coalesce(k.sent_method,'—'), coalesce(k.sent_to,'—'), "
            "coalesce(k.google_drive_link,'') <> '' FROM ged_document_kits k JOIN ged_clients g ON g.id=k.client_id "
            "WHERE to_char(k.reference_month,'MM.YYYY') = :c ORDER BY g.name"), {"c": comp})).fetchall()  # competência do orquestrador é MM.AAAA
        linhas = [{"condominio": r[0], "competencia": r[1], "entregue_em": r[2].strftime("%d/%m %H:%M") if r[2] else "—", "canal": r[3], "para": r[4], "no_drive": bool(r[5])} for r in rows]
        out["kits-entrega-status"] = tabela_de_lista(f"Entrega dos kits — {comp}", "Entregue? Quando, por qual canal e para quem (ged_document_kits). Um condomínio por linha.", linhas,
                                                     cols=["condominio", "competencia", "entregue_em", "canal", "para", "no_drive"])
    except Exception as exc:  # noqa: BLE001
        await db.rollback(); logger.warning("kits entrega status: %s", exc)
    out["kit-entrega-preparar"] = {
        "title": "Preparar entrega de kit", "sub": "Monta o pacote de entrega (ZIP/links) do kit do condomínio. Não envia nada.",
        "cta": "Preparar", "type": "form",
        "submit": {"endpoint": "/api/v1/gedeon/kits/entrega/preparar", "query": True, "okMsg": "Entrega preparada", "showResult": True},
        "fields": [selecionar("condominio", "Condomínio*", opts), {"key": "competencia", "label": "Competência (AAAA-MM)", "type": "text", "span": "span 1", "ph": comp}]}
    out["kit-entrega-marcar"] = {
        "title": "Marcar kit como entregue", "sub": "Registra que o kit chegou ao cliente e por qual canal. Só registra.",
        "cta": "Marcar", "type": "form",
        "submit": {"endpoint": "/api/v1/gedeon/kits/entrega/marcar", "okMsg": "Entrega registrada"},
        "fields": [selecionar("condominio", "Condomínio*", opts), {"key": "competencia", "label": "Competência (AAAA-MM)", "type": "text", "span": "span 1", "ph": comp},
                   selecionar("canal", "Canal*", [{"value": v, "label": l} for v, l in (("email", "E-mail"), ("whatsapp", "WhatsApp"), ("drive", "Google Drive"), ("presencial", "Presencial"))], "span 1"),
                   {"key": "obs", "label": "Observação", "type": "textarea", "span": "span 2"}]}
    out["kit-faturar"] = {
        "title": "Faturar kit (boleto)", "sub": "Emite a cobrança do kit no banco. A NFS-e NÃO sai por aqui: o caminho pelo provedor antigo (Ábaco) foi desligado; a nota vai pelo Portal Nacional.",
        "cta": "Faturar", "type": "form",
        "submit": {"endpoint": "/api/v1/gedeon/kits/faturar", "okMsg": "Faturamento disparado", "showResult": True,
                   "confirm": "Emite boleto REAL no banco para este condomínio. Confirma?"},
        "fields": [selecionar("condominio", "Condomínio*", opts), {"key": "competencia", "label": "Competência (AAAA-MM)", "type": "text", "span": "span 1", "ph": comp},
                   selecionar("tipo", "O que emitir*", [{"value": "boleto", "label": "Boleto (Inter/Cora)"}], "span 1"),
                   selecionar("confirmar", "Modo*", [{"value": "false", "label": "Só simular (padrão)"}, {"value": "true", "label": "EMITIR de verdade"}], "span 2")]}
    out["kit-checklist-evento"] = {
        "title": "Registrar evento no checklist do kit", "sub": "Admissão, demissão, afastamento, férias… o que muda o kit da competência.",
        "cta": "Registrar", "type": "form",
        "submit": {"endpoint": "/api/v1/gedeon/kits/checklist", "okMsg": "Evento registrado"},
        "fields": [selecionar("condominio", "Condomínio*", opts), {"key": "competencia", "label": "Competência (AAAA-MM)", "type": "text", "span": "span 1", "ph": comp},
                   selecionar("tipo", "Tipo*", [{"value": v, "label": v.capitalize()} for v in ("admissao", "demissao", "afastamento", "ferias", "substituicao", "outro")], "span 1"),
                   {"key": "funcionario", "label": "Funcionário", "type": "text", "span": "span 1"}, {"key": "data", "label": "Data", "type": "date", "span": "span 1"},
                   {"key": "descricao", "label": "Descrição*", "type": "textarea", "span": "span 2"}]}


def _lista(res) -> bool:
    from modules.operacional.controllers.redesign_builders._ligar_generico import _lista_em
    return bool(_lista_em(res))


async def _ligar_lote3_20260908(db, out: dict) -> None:
    """LIGAR lote 3 (08/09/2026): rotas que existiam sem tela. Cada bloco é independente (try/except + rollback)."""
    import logging as _lg
    from sqlalchemy import text as _T
    from modules.operacional.controllers.redesign_data_controller import _helpers, t, b, brl
    from modules.operacional.controllers.redesign_builders._ligar_generico import chamar, painel_de_dict, selecionar, tabela_de_lista
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
            await db.rollback(); return 0

    try:  # GET /ged/config/document-types
        from modules.ged.controllers import ged_config_controller as Gc
        res = await chamar(Gc.get_document_types, db)
        out["ged-tipos-documento"] = tabela_de_lista("GED — tipos de documento", "Catálogo de tipos usado nos kits (obrigatório/ativo) · fonte: ged_document_types", res)
    except Exception as exc:  # noqa: BLE001
        await db.rollback(); _log.warning("ged-tipos-documento: %s", exc)
    try:  # GET/POST /ged/coleta-automatica
        row = (await db.execute(_T("SELECT enabled, cron_expr, timezone, last_run, last_status, updated_at, updated_by FROM ged_coleta_config ORDER BY id LIMIT 1"))).first()
        painel = {"ligada": bool(row[0]) if row else False, "cron": row[1] if row else None, "fuso": row[2] if row else None,
                  "ultima_execucao": _fd(row[3], "%d/%m/%Y %H:%M") if row and row[3] else "nunca", "ultimo_status": row[4] if row else None,
                  "atualizado_em": _fd(row[5], "%d/%m/%Y %H:%M") if row and row[5] else None, "atualizado_por": row[6] if row else None}
        out["ged-coleta-automatica"] = painel_de_dict("GED — coleta automática", "Robô que busca guias/notas nos portais todo mês (tarefa auto_collect_task lê esta configuração) · fonte: ged_coleta_config", painel, kpis_de=["ligada", "cron", "ultima_execucao", "ultimo_status"])
        out["ged-coleta-configurar"] = {
            "title": "GED — configurar coleta automática", "sub": "Liga/desliga o robô e define o cron (ex.: 0 6 21 * * = dia 21 às 06:00). É a configuração que a tarefa Celery lê — diferente do 'agendamento de envio' dos kits.",
            "cta": "Salvar", "type": "form", "submit": {"endpoint": "/api/v1/ged/coleta-automatica", "okMsg": "Configuração salva. Recarregue.", "showResult": True},
            "fields": [selecionar("enabled", "Ligada?", _SN, "span 1"), {"key": "cron_expr", "label": "Cron*", "type": "text", "span": "span 1", "value": (row[1] if row else "0 6 21 * *") or "0 6 21 * *"}]}
    except Exception as exc:  # noqa: BLE001
        await db.rollback(); _log.warning("ged-coleta: %s", exc)
    try:  # POST /gedeon/cnd/emitir + POST /gedeon/cnd/upload (decisão do dono 07/09: certidões só da Patrimonial)
        emp = (await db.execute(_T("SELECT cnpj, razao_social FROM empresas WHERE slug='conecta_patrimonial' LIMIT 1"))).first()
        cnpj = emp[0] if emp else ""
        out["cnd-emitir"] = {
            "title": "Certidões — emitir pelo robô", "sub": f"Enfileira a emissão para o robô (SEFAZ-AM, CNDT, Prefeitura). Federal e Caixa são manuais: emita no portal e suba o PDF ao lado. Empresa: {emp[1] if emp else '—'}.",
            "cta": "Emitir", "type": "form", "submit": {"endpoint": "/api/v1/gedeon/cnd/emitir", "okMsg": "Emissão enfileirada — acompanhe em Certidões (CND).", "showResult": True},
            "fields": [{"key": "cnpj", "label": "CNPJ", "type": "text", "span": "span 1", "value": cnpj},
                       {"key": "portais", "label": "Portais", "type": "multiselect", "span": "span 1", "options": [{"value": v, "label": l} for v, l in (("sefaz_am", "SEFAZ-AM"), ("cndt", "CNDT (TST)"), ("prefeitura", "Prefeitura de Manaus"))]}]}
        out["cnd-upload"] = {
            "title": "Certidões — subir PDF emitido manualmente", "sub": "Federal (RFB/PGFN) e FGTS (Caixa) não têm robô: suba o PDF e a validade é lida do próprio documento.",
            "cta": "Enviar", "type": "form", "submit": {"endpoint": "/api/v1/gedeon/cnd/upload", "multipart": True, "okMsg": "Certidão registrada. Recarregue.", "showResult": True},
            "fields": [selecionar("document_type", "Tipo*", [{"value": v, "label": l} for v, l in (("federal", "Federal — RFB/PGFN"), ("caixa", "FGTS — Caixa"))], "span 1"),
                       {"key": "cnpj", "label": "CNPJ", "type": "text", "span": "span 1", "value": cnpj},
                       {"key": "file", "label": "PDF da certidão*", "type": "file", "span": "span 2"}]}
    except Exception as exc:  # noqa: BLE001
        await db.rollback(); _log.warning("cnd: %s", exc)
    try:  # POST /whatsapp/send/certificate-alert
        out["certidoes-avisar"] = await tbl(
            "Certidões — avisar cliente por WhatsApp", "Avisa o síndico/cliente que uma certidão vence (ou venceu). Informe telefone e nome; o resto vem da certidão · fonte: ged_certidoes", "—",
            ["Certidão", "Tipo", "Validade", "Situação"], "2.2fr 1fr 0.9fr 1fr",
            "SELECT coalesce(name,'—'), coalesce(document_type,'—'), expiry_date, (expiry_date - current_date) FROM ged_certidoes WHERE expiry_date IS NOT NULL ORDER BY expiry_date ASC LIMIT 200",
            lambda r: [t(r[0][:60], 600, "#0F1B3A"), t(r[1]), t(_fd(r[2])), b("Vencida" if (r[3] or 0) < 0 else (f"Vence em {r[3]}d" if (r[3] or 0) <= 30 else "Válida"), "bad" if (r[3] or 0) < 0 else "warn" if (r[3] or 0) <= 30 else "ok")],
            actionsfn=lambda r: [{"title": f"Avisar por WhatsApp — {r[0][:40]}", "endpoint": "/api/v1/whatsapp/send/certificate-alert", "method": "POST",
                                  "btnLabel": "Avisar cliente", "btnStyle": "outline", "submitLabel": "Enviar WhatsApp", "okMsg": "Aviso enviado.",
                                  "fields": [{"key": "phone", "label": "Telefone (com DDD)*", "type": "text", "span": "span 1"},
                                             {"key": "client_name", "label": "Nome do cliente*", "type": "text", "span": "span 1"},
                                             {"key": "certificate_type", "label": "Certidão", "type": "text", "span": "span 1", "value": r[1]},
                                             {"key": "expiry_date", "label": "Validade", "type": "text", "span": "span 1", "value": _fd(r[2])},
                                             {"key": "days_remaining", "label": "Dias restantes", "type": "number", "span": "span 1", "value": int(r[3] or 0)}]}])
    except Exception as exc:  # noqa: BLE001
        await db.rollback(); _log.warning("certidoes-avisar: %s", exc)


async def _ligar_lote4_20260908(db, out: dict) -> None:
    """LIGAR lote 4 (08/09/2026): rotas que existiam sem tela (vereditos B e C). Blocos independentes (try/except + rollback).
    Regra da casa: a página nunca chama Drive/robô/governo — leituras do Drive viram formulários GET que o usuário dispara."""
    import logging as _lg
    from datetime import date as _dt
    from sqlalchemy import text as _T
    from modules.operacional.controllers.redesign_data_controller import _helpers, t, b, brl
    from modules.operacional.controllers.redesign_builders._ligar_generico import chamar, painel_de_dict, selecionar, tabela_de_lista
    _log = _lg.getLogger(__name__)
    _, _safe, tbl = _helpers(db)
    _SN = [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}]
    hoje = _dt.today()

    def _fd(v, fmt="%d/%m/%Y"):
        try:
            return v.strftime(fmt) if v else "—"
        except Exception:  # noqa: BLE001
            return str(v or "—")

    async def _n(sql):
        try:
            return (await db.execute(_T(sql))).scalar() or 0
        except Exception:  # noqa: BLE001
            await db.rollback(); return 0

    def _consulta(key, titulo, sub, endpoint, fields, method="GET"):
        """Form de CONSULTA: dispara o GET com query e mostra o resultado (a página não chama nada ao abrir)."""
        out[key] = {"title": titulo, "sub": sub, "cta": "Consultar", "type": "form",
                    "submit": {"endpoint": endpoint, "method": method, "query": True, "okMsg": "Consulta feita — veja o resultado.", "showResult": True},
                    "fields": fields}

    try:  # GET /ged/kits/{kit_id} — documentos por kit, por SQL (a rota fica redundante)
        out["kit-documentos"] = await tbl(
            "Documentos por kit", f"{await _n('SELECT count(*) FROM ged_kit_documents')} documentos em kits · últimos 300 · fonte: ged_kit_documents × ged_document_kits", "—",
            ["Kit", "Colaborador", "Documento", "Tipo", "Assinado", "Gerado em"], "0.8fr 1.8fr 2fr 1fr 0.8fr 0.9fr",
            "SELECT to_char(k.reference_month,'MM/YYYY'), coalesce(e.nome, d.employee_id::text, '—'), coalesce(d.document_name,'—'), coalesce(d.document_type,'—'), coalesce(d.is_signed,false), d.created_at "
            "FROM ged_kit_documents d LEFT JOIN ged_document_kits k ON k.id=d.kit_id LEFT JOIN employees e ON e.id=d.employee_id ORDER BY d.created_at DESC LIMIT 300",
            lambda r: [t(r[0] or "—", 600, "#0F1B3A"), t(r[1][:36]), t(r[2][:50]), b(r[3].replace("_", " ").capitalize(), "info"), b("Sim" if r[4] else "Não", "ok" if r[4] else "mut"), t(_fd(r[5]))])
    except Exception as exc:  # noqa: BLE001
        await db.rollback(); _log.warning("kit-documentos: %s", exc)
    _consulta("gedeon-panorama", "GEDEON — panorama dos kits", "Kits por condomínio, pendências e intercorrências da competência (AAAA-MM; vazio = mês anterior).",
              "/api/v1/gedeon/consultor/panorama", [{"key": "competencia", "label": "Competência (AAAA-MM)", "type": "text", "span": "span 1"}])
    _consulta("gedeon-alinhamento-dp", "GEDEON — alinhamento DP", "Folha do kit × espelho Sólides + afastamentos de um condomínio. Lê o Drive quando você clica.",
              "/api/v1/gedeon/kits/dp/alinhamento", [{"key": "condominio", "label": "Condomínio (nome da pasta)*", "type": "text", "span": "span 1"}, {"key": "competencia", "label": "Competência (MM.AAAA)", "type": "text", "span": "span 1"}])
    _consulta("gedeon-funcionarios", "GEDEON — funcionários da folha do condomínio", "Lista quem está na folha do kit (para a visão por funcionário). Lê o Drive quando você clica.",
              "/api/v1/gedeon/kits/funcionarios", [{"key": "condominio", "label": "Condomínio*", "type": "text", "span": "span 1"}, {"key": "competencia", "label": "Competência (MM.AAAA)", "type": "text", "span": "span 1"}])
    _consulta("gedeon-funcionario", "GEDEON — visão por funcionário", "Todos os documentos de uma pessoa no kit. Lê o Drive quando você clica.",
              "/api/v1/gedeon/kits/funcionario", [{"key": "funcionario", "label": "Funcionário*", "type": "text", "span": "span 2"}, {"key": "condominio", "label": "Condomínio", "type": "text", "span": "span 1"}, {"key": "competencia", "label": "Competência (MM.AAAA)", "type": "text", "span": "span 1"}])
    _consulta("gedeon-assinaturas-pendentes", "GEDEON — quem não assinou VT/VR (Sólides)", "Pendências de assinatura dos recibos de VT/VR. Lê o Drive quando você clica.",
              "/api/v1/gedeon/kits/assinaturas", [{"key": "condominio", "label": "Condomínio", "type": "text", "span": "span 1"}, {"key": "competencia", "label": "Competência (MM.AAAA)", "type": "text", "span": "span 1"}])


async def _ligar_lote5_20260908(db, out: dict, me=None) -> None:
    """LIGAR lote 5 (08/09/2026): rotas do people-management/users/SST que só existiam por API. Blocos independentes."""
    import logging as _lg
    from datetime import date as _dt
    from sqlalchemy import text as _T
    from modules.operacional.controllers.redesign_data_controller import _helpers, t, b, brl
    from modules.operacional.controllers.redesign_builders._ligar_generico import chamar, painel_de_dict, selecionar, tabela_de_lista
    _log = _lg.getLogger(__name__)
    _, _safe, tbl = _helpers(db)
    _SN = [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}]
    hoje = _dt.today()

    def _fd(v, fmt="%d/%m/%Y"):
        try:
            return v.strftime(fmt) if v else "—"
        except Exception:  # noqa: BLE001
            return str(v or "—")

    async def _n(sql):
        try:
            return (await db.execute(_T(sql))).scalar() or 0
        except Exception:  # noqa: BLE001
            await db.rollback(); return 0

    async def _emps():
        try:
            return [{"value": str(i), "label": n} for i, n in (await db.execute(_T("SELECT id, nome FROM employees WHERE status='ativo' ORDER BY nome LIMIT 400"))).fetchall()]
        except Exception:  # noqa: BLE001
            await db.rollback(); return []

    def _consulta(key, titulo, sub, endpoint, fields, method="GET"):
        out[key] = {"title": titulo, "sub": sub, "cta": "Consultar", "type": "form",
                    "submit": {"endpoint": endpoint, "method": method, "query": True, "okMsg": "Consulta feita — veja o resultado.", "showResult": True},
                    "fields": fields}

    try:  # GET /ged/coleta-automatica/history — por SQL
        out["ged-coleta-historico"] = await tbl(
            "GED — histórico da coleta automática", f"{await _n('SELECT count(*) FROM ged_coleta_logs')} execuções · fonte: ged_coleta_logs", "—",
            ["Quando", "Tipo", "Status", "Disparo", "Duração", "Novos", "Onvio", "Kits", "Certidões", "Erros"], "1fr 0.7fr 0.7fr 0.8fr 0.6fr 0.5fr 0.5fr 0.5fr 0.6fr 1fr",
            "SELECT run_at, coalesce(run_type,'—'), coalesce(status,'—'), coalesce(triggered_by,'—'), duration_ms, coalesce(sync_novos,0), coalesce(onvio_matched,0), coalesce(kits_assembled,0), coalesce(certidoes_atualizadas,0), coalesce(erros::text,'') "
            "FROM ged_coleta_logs ORDER BY run_at DESC LIMIT 100",
            lambda r: [t(_fd(r[0], "%d/%m/%Y %H:%M")), t(r[1]), b(r[2].capitalize(), "ok" if r[2] in ("ok", "success", "sucesso") else "bad" if r[2] in ("erro", "error", "failed") else "info"), t(r[3]),
                       t(f"{(r[4] or 0) // 1000}s"), t(str(r[5])), t(str(r[6])), t(str(r[7])), t(str(r[8])), t((r[9] or "")[:40] or "—")])
    except Exception as exc:  # noqa: BLE001
        await db.rollback(); _log.warning("ged-coleta-historico: %s", exc)
    out["ged-coleta-executar"] = {  # POST /ged/coleta-automatica/run
        "title": "GED — executar coleta agora", "sub": "Dispara a coleta (Onvio → kits → certidões) fora do cron. Roda no Celery; acompanhe no histórico.",
        "cta": "Executar", "type": "form", "submit": {"endpoint": "/api/v1/ged/coleta-automatica/run", "okMsg": "Coleta enfileirada — veja o histórico em alguns minutos.", "showResult": True},
        "fields": [{"key": "mes_ref", "label": "Mês de referência (AAAA-MM, opcional)", "type": "text", "span": "span 1"}, selecionar("force_resync", "Forçar ressincronização?", _SN, "span 1")]}
