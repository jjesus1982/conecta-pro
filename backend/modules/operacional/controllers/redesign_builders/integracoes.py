"""Integrações (T1) — delega ao _build_integracoes e ESTENDE com logs (chamadas de
integração) e sync (histórico de sincronização Sólides). Leitura real."""

from datetime import date

from modules.operacional.controllers.redesign_data_controller import (
    _build_integracoes,
    _helpers,
    b,
    t,
)

SLUG = "integracoes"
_ICO_I = "M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"

EXTRA_MENU: list[dict] = [
    # 17/09/2026: este bloco de 8 estava COLADO 3 VEZES aqui — 24 linhas na sidebar
    # onde cabiam 8. O Jordan: «a side bar tá gigante, me perco diante de tanta coisa».
    # `checar_menu_duplicado.py` agora falha se voltar.
    {"id": "inter-categorizacao", "label": "Inter — categorização", "icon": "M3 3v18h18"},
    {"id": "inter-categorias-stats", "label": "Inter — estatísticas de categorização", "icon": "M3 3v18h18"},
    {"id": "inter-categorias-auto", "label": "Inter — auto-categorizar mês", "icon": "M3 3v18h18"},
    {"id": "onvio-documentos", "label": "Onvio — documentos", "icon": "M3 3v18h18"},
    {"id": "onvio-historico", "label": "Onvio — execuções", "icon": "M3 3v18h18"},
    {"id": "onvio-stats", "label": "Onvio — estatísticas", "icon": "M3 3v18h18"},
    {"id": "onvio-status", "label": "Onvio — sessão", "icon": "M3 3v18h18"},
    {"id": "gdrive-desconectar", "label": "Google Drive — desconectar", "icon": "M3 3v18h18"},
    {"id": "gdrive-status", "label": "Google Drive — status", "icon": "M3 3v18h18"},
    {"id": "solides-sincronizar-escalas", "label": "Sincronizar escalas (Sólides)", "icon": "M3 3v18h18"},
    {"id": "onvio-reclassificar", "label": "Reclassificar (Onvio)", "icon": _ICO_I},
    {"id": "solides-sincronizar", "label": "Sincronizar ponto (Sólides)", "icon": _ICO_I},
    {"id": "drive-conectar", "label": "Conectar Google Drive", "icon": _ICO_I},
    {"id": "drive-desconectar", "label": "Desconectar Google Drive", "icon": _ICO_I},
    {"id": "onvio-extrair", "label": "Extrair valores (Onvio)", "icon": _ICO_I},
    {"id": "solides-vincular-kits", "label": "Vincular benefícios aos kits", "icon": _ICO_I},
    {"id": "inter-sync-cobrancas", "label": "Sincronizar cobrancas (Inter)", "icon": _ICO_I},
    {"id": "inter-hermes-linkar", "label": "Vincular extrato aos kits (Hermes)", "icon": _ICO_I},
    {"id": "whatsapp-nfse", "label": "Avisar NFS-e por WhatsApp", "icon": _ICO_I},
]


async def build(db) -> dict:
    out = await _build_integracoes(db)  # base: visao, solides
    _, _safe, tbl = _helpers(db)

    # Logs de integração (chamadas HTTP) — integration_logs
    _lvl = {
        "error": "bad",
        "erro": "bad",
        "critical": "bad",
        "warn": "warn",
        "warning": "warn",
        "info": "info",
        "debug": "mut",
    }
    try:
        out["logs"] = await tbl(
            "Logs de integração",
            "Chamadas recentes (webhooks/API)",
            "—",
            ["Horário", "Método", "Path", "HTTP", "Nível"],
            "1fr 0.8fr 1.9fr 0.7fr 0.8fr",
            "SELECT to_char(created_at,'DD/MM HH24:MI'), coalesce(method,'—'), coalesce(path,'—'), response_status_code, coalesce(level::text,'—') "
            "FROM integration_logs ORDER BY created_at DESC LIMIT 200",
            lambda r: [
                t(r[0] or "—"),
                b(r[1] or "—", "info"),
                t((r[2] or "—")[:46]),
                b(str(r[3]), "ok" if r[3] and 200 <= r[3] < 400 else "bad") if r[3] is not None else t("—"),
                b((r[4] or "—").capitalize(), _lvl.get((r[4] or "").lower(), "info")),
            ],
        )
    except Exception:  # noqa: BLE001
        pass

    # Histórico de sincronização Sólides — solides_sync_log
    _st = {
        "completed": "ok",
        "success": "ok",
        "concluido": "ok",
        "failed": "bad",
        "error": "bad",
        "partial": "warn",
        "running": "warn",
        "in_progress": "warn",
    }
    try:
        out["sync"] = await tbl(
            "Sincronizações (Sólides)",
            "Histórico de sync (RH/ponto)",
            "—",
            ["Entidade", "Tipo", "Direção", "Proc.", "Criados", "Atualiz.", "Falhas", "Status"],
            "1fr 0.9fr 1.5fr 0.7fr 0.7fr 0.7fr 0.7fr 0.9fr",
            "SELECT coalesce(entity_type::text,'—'), coalesce(sync_type::text,'—'), coalesce(direction::text,'—'), "
            "items_processed, items_created, items_updated, items_failed, coalesce(status::text,'—') "
            "FROM solides_sync_log ORDER BY started_at DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0] or "—", 600, "#0F1B3A"),
                t((r[1] or "—").replace("_", " ")),
                t(
                    (r[2] or "—")
                    .replace("solides_to_conecta", "Sólides → Conecta")
                    .replace("conecta_to_solides", "Conecta → Sólides")
                    .replace("_", " ")
                ),
                t(str(int(r[3] or 0))),
                t(str(int(r[4] or 0))),
                t(str(int(r[5] or 0))),
                b(str(int(r[6] or 0)), "bad" if (r[6] or 0) > 0 else "mut"),
                b((r[7] or "—").capitalize(), _st.get((r[7] or "").lower(), "info")),
            ],
        )
    except Exception:  # noqa: BLE001
        pass

    # Fio solto (2026-08-10): a reclassificação do Onvio existia no backend sem botão.
    out["onvio-reclassificar"] = {
        "title": "Reclassificar lançamentos (Onvio)",
        "sub": "Reprocessa a classificação contábil dos lançamentos importados do Onvio. "
        "Não apaga lançamento — só reclassifica.",
        "cta": "Reclassificar",
        "type": "form",
        "submit": {"endpoint": "/api/v1/onvio/reclassificar", "okMsg": "Reclassificação disparada"},
        "fields": [],
    }
    out["solides-sincronizar"] = {
        "title": "Sincronizar ponto com o Sólides Tangerino",
        "sub": "Puxa as batidas do Sólides para o ERP. Só LÊ do Sólides — não escreve lá.",
        "cta": "Sincronizar agora",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/people-management/ponto/sincronizar-solides",
            "okMsg": "Sincronização de ponto disparada",
        },
        "fields": [],
    }
    out["drive-conectar"] = {
        "title": "Conectar Google Drive",
        "sub": "Inicia a conexão usada pelo GED para guardar e buscar os kits.",
        "cta": "Conectar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/people-management/ged/config/drive/connect",
            "okMsg": "Conexão com o Drive iniciada",
        },
        "fields": [],
    }
    out["drive-desconectar"] = {
        "title": "Desconectar Google Drive",
        "sub": "Encerra a conexão. O GED para de guardar e buscar kits no Drive até reconectar.",
        "cta": "Desconectar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/people-management/ged/config/drive/disconnect",
            "method": "DELETE",
            "okMsg": "Google Drive desconectado",
            "confirm": "Desconectar o Drive interrompe o GED de guardar e buscar kits. Confirma?",
        },
        "fields": [],
    }
    # Query fixa no endpoint (padrão já usado no financeiro): rota que lê QUERY funciona
    # sem tela de campo quando o valor é derivável. Ver nota longa em documentos.py.
    _h = date.today()
    out["onvio-extrair"] = {
        "title": "Extrair valores dos documentos (Onvio)",
        "sub": "Lê os documentos importados e extrai os valores. Só processa o que ainda não "
        "foi extraído — rodar de novo não refaz o que já saiu.",
        "cta": "Extrair",
        "type": "form",
        "submit": {"endpoint": "/api/v1/onvio/extrair-valores", "okMsg": "Extração disparada"},
        "fields": [],
    }
    out["solides-vincular-kits"] = {
        "title": f"Vincular benefícios aos kits — {_h.month:02d}/{_h.year}",
        "sub": "Liga os benefícios do Sólides aos kits da competência corrente (VT/VR).",
        "cta": "Vincular",
        "type": "form",
        "submit": {
            "endpoint": f"/api/v1/integrations/solides/beneficios/vincular-kits?mes_ref={_h.month:02d}.{_h.year}",
            "okMsg": "Vinculação disparada",
        },
        "fields": [],
    }

    out["inter-sync-cobrancas"] = {
        "title": "Sincronizar status das cobrancas (Inter)",
        "sub": "Consulta a API do Inter e atualiza o status das cobrancas a receber. So LE "
        "do banco - não emite cobranca nem baixa nada sozinho.",
        "cta": "Sincronizar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/financeiro/inter/cobrancas/sincronizar-status",
            "okMsg": "Sincronizacao disparada",
            "showResult": True,
        },
        "fields": [],
    }
    out["inter-hermes-linkar"] = {
        "title": f"Vincular extrato do Inter aos kits - {_h.month:02d}/{_h.year}",
        "sub": "Liga cada transação do extrato ao documento certo do kit. Vinculo - não move dinheiro.",
        "cta": "Vincular",
        "type": "form",
        "submit": {
            "endpoint": f"/api/v1/financeiro/inter/hermes/linkar?mes_ref={_h.year}-{_h.month:02d}",
            "okMsg": "Vinculacao disparada",
            "showResult": True,
        },
        "fields": [],
    }
    out["whatsapp-nfse"] = {
        "title": "Avisar o cliente da NFS-e por WhatsApp",
        "sub": "Manda a notificação da nota emitida. Efeito EXTERNO: a mensagem sai agora.",
        "cta": "Enviar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/whatsapp/send/nfse-notification",
            "okMsg": "Notificação enviada",
            "showResult": True,
            "confirm": "Envia a mensagem ao cliente AGORA. Confirma?",
        },
        "fields": [  # 08/09/2026: a rota exige JSON (phone, client_name, nfse_number, value); mandava user_id na query → 422
            {"key": "phone", "label": "WhatsApp do cliente*", "type": "text", "span": "span 1", "ph": "+5592..."},
            {"key": "client_name", "label": "Nome do cliente*", "type": "text", "span": "span 1"},
            {"key": "nfse_number", "label": "Número da NFS-e*", "type": "text", "span": "span 1"},
            {"key": "value", "label": "Valor (R$)*", "type": "number", "span": "span 1"},
        ],
    }

    await _ligar_lote3_20260908(db, out)
    await _ligar_lote4_20260908(db, out)
    return out


async def _ligar_lote3_20260908(db, out: dict) -> None:
    """LIGAR lote 3 (08/09/2026): rotas que existiam sem tela. Cada bloco é independente (try/except + rollback)."""
    import logging as _lg

    from sqlalchemy import text as _T  # noqa: N812  # alias curto pré-existente, usado em todo o arquivo

    from modules.operacional.controllers.redesign_builders._ligar_generico import (
        painel_de_dict,
    )
    from modules.operacional.controllers.redesign_data_controller import _helpers

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

    try:  # GET /gdrive/status (por SQL — a página nunca chama o Drive)
        row = (
            await db.execute(
                _T(
                    "SELECT owner_email, is_connected, token_expiry, root_folder_id, kits_folder_id, updated_at FROM gdrive_config ORDER BY updated_at DESC NULLS LAST LIMIT 1"
                )
            )
        ).first()
        painel = {
            "conectado": bool(row[1]) if row else False,
            "conta": row[0] if row else None,
            "token_expira_em": _fd(row[2], "%d/%m/%Y %H:%M") if row and row[2] else None,
            "pasta_raiz": row[3] if row else None,
            "pasta_kits": row[4] if row else None,
            "atualizado_em": _fd(row[5], "%d/%m/%Y %H:%M") if row and row[5] else None,
        }
        out["gdrive-status"] = painel_de_dict(
            "Google Drive — status da conexão",
            "Conta conectada e pastas usadas pelos kits · fonte: gdrive_config (sem chamar o Drive)",
            painel,
            kpis_de=["conectado", "conta", "token_expira_em"],
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _log.warning("gdrive-status: %s", exc)
    out["solides-sincronizar-escalas"] = {  # POST /people-management/ponto/sync-escalas
        "title": "Sincronizar escalas (Sólides)",
        "sub": f"Traz as escalas de trabalho cadastradas no Sólides para solides_work_schedules ({await _n('SELECT count(*) FROM solides_work_schedules')} hoje). Diferente da sincronização de batidas.",
        "cta": "Sincronizar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/people-management/ponto/sync-escalas",
            "okMsg": "Escalas sincronizadas.",
            "showResult": True,
        },
        "fields": [],
    }


async def _ligar_lote4_20260908(db, out: dict) -> None:
    """LIGAR lote 4 (08/09/2026): rotas que existiam sem tela (vereditos B e C). Blocos independentes (try/except + rollback).
    Regra da casa: a página nunca chama Drive/robô/governo — leituras do Drive viram formulários GET que o usuário dispara."""
    import logging as _lg
    from datetime import date as _dt

    from sqlalchemy import text as _T  # noqa: N812  # alias curto pré-existente, usado em todo o arquivo

    from modules.operacional.controllers.redesign_builders._ligar_generico import (
        painel_de_dict,
    )
    from modules.operacional.controllers.redesign_data_controller import _helpers, b, brl, t

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

    try:  # POST /financeiro/inter/transacoes/{id}/categorizar (ação por linha) — tabela por SQL
        out["inter-categorizacao"] = await tbl(
            "Inter — categorização das transações (Hermes)",
            f"{await _n('SELECT count(*) FROM inter_transaction_categorias')} transações categorizadas · corrigir a categoria por linha sobrescreve a IA · fonte: inter_transaction_categorias",
            "—",
            ["Data", "Título", "Valor", "Categoria", "IA", "Confiança", "Observação"],
            "0.8fr 2fr 0.9fr 1.1fr 0.5fr 0.7fr 1.4fr",
            "SELECT tx.id::text, tx.data_lancamento, coalesce(tx.titulo, tx.descricao, '—'), tx.valor, coalesce(c.categoria,'—'), coalesce(c.sugerido_por_ia,false), c.confianca_sugestao, coalesce(c.observacao,'') "
            "FROM inter_transaction_categorias c JOIN inter_transactions tx ON tx.id=c.transaction_id ORDER BY tx.data_lancamento DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(_fd(r[1])),
                t(r[2][:60], 600, "#0F1B3A"),
                t(brl(r[3]) if r[3] is not None else "—", 600),
                b(r[4].replace("_", " ").capitalize(), "info"),
                t("IA" if r[5] else "humano"),
                t(f"{int((r[6] or 0) * 100)}%" if r[6] is not None else "—"),
                t(r[7][:50] or "—"),
            ],
            actionsfn=lambda r: [
                {
                    "title": f"Corrigir categoria — {r[2][:40]}",
                    "endpoint": f"/api/v1/financeiro/inter/transacoes/{r[0]}/categorizar",
                    "method": "POST",
                    "btnLabel": "Corrigir",
                    "btnStyle": "outline",
                    "submitLabel": "Salvar categoria",
                    "okMsg": "Categoria corrigida (a IA não sobrescreve mais). Recarregue.",
                    "fields": [
                        {"key": "categoria", "label": "Categoria*", "type": "text", "span": "span 1", "value": r[4]},
                        {"key": "observacao", "label": "Observação", "type": "text", "span": "span 1", "value": r[7]},
                    ],
                }
            ],
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _log.warning("inter-categorizacao: %s", exc)
    _consulta(
        "inter-categorias-stats",
        "Inter — estatísticas da categorização",
        "Quantas transações do mês foram categorizadas, por quem (IA/humano) e por categoria. Mês no formato MM.AAAA.",
        "/api/v1/financeiro/inter/categorias/stats",
        [
            {
                "key": "mes_ref",
                "label": "Mês (MM.AAAA)*",
                "type": "text",
                "span": "span 1",
                "value": hoje.strftime("%m.%Y"),
            }
        ],
    )
    out["inter-categorias-auto"] = {  # POST /financeiro/inter/categorias/auto-processar
        "title": "Inter — auto-categorizar o mês",
        "sub": "Roda a categorização automática para todos os colaboradores do mês (o beat só faz VT/VR). Não paga nada.",
        "cta": "Processar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/financeiro/inter/categorias/auto-processar",
            "query": True,
            "okMsg": "Processado — veja o resultado.",
            "showResult": True,
        },
        "fields": [
            {
                "key": "mes_ref",
                "label": "Mês (AAAA-MM, opcional)",
                "type": "text",
                "span": "span 1",
                "value": hoje.strftime("%Y-%m"),
            }
        ],
    }

    try:  # GET /onvio/documentos, /onvio/historico, /onvio/stats — por SQL
        out["onvio-documentos"] = await tbl(
            "Onvio — documentos importados",
            f"{await _n('SELECT count(*) FROM onvio_documents')} documentos · fonte: onvio_documents",
            "—",
            ["Arquivo", "Categoria", "Mês ref.", "Data Onvio", "Extração", "Revisão"],
            "2.2fr 1fr 0.8fr 0.9fr 0.9fr 0.7fr",
            "SELECT coalesce(nome_arquivo,'—'), coalesce(categoria,'—'), coalesce(mes_ref,'—'), data_onvio, coalesce(metodo_extracao,'—'), coalesce(revisao_manual,false) "
            "FROM onvio_documents ORDER BY data_onvio DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0][:60], 600, "#0F1B3A"),
                b(r[1], "info"),
                t(r[2]),
                t(_fd(r[3])),
                t(r[4]),
                b("Revisar" if r[5] else "OK", "warn" if r[5] else "ok"),
            ],
        )
        out["onvio-historico"] = await tbl(
            "Onvio — execuções de sincronização",
            f"{await _n('SELECT count(*) FROM onvio_sync_log')} execuções · cron do host dia 7 às 07:00 · fonte: onvio_sync_log",
            "—",
            ["Quando", "Mês ref.", "Status", "Baixados", "Novos", "Erros", "Duração"],
            "1fr 0.8fr 0.8fr 0.7fr 0.7fr 0.6fr 0.7fr",
            "SELECT created_at, coalesce(mes_ref,'—'), coalesce(status,'—'), coalesce(docs_baixados,0), coalesce(docs_novos,0), coalesce(docs_erro,0), duracao_s FROM onvio_sync_log ORDER BY created_at DESC LIMIT 200",
            lambda r: [
                t(_fd(r[0], "%d/%m/%Y %H:%M")),
                t(r[1]),
                b(
                    r[2].capitalize(),
                    "ok" if r[2] in ("ok", "sucesso", "success") else "bad" if r[2] in ("erro", "error") else "info",
                ),
                t(str(r[3])),
                t(str(r[4])),
                b(str(r[5]), "bad" if r[5] else "mut"),
                t(f"{r[6]:.0f}s" if r[6] else "—"),
            ],
        )
        st = (
            await db.execute(
                _T("SELECT coalesce(categoria,'—'), count(*) FROM onvio_documents GROUP BY 1 ORDER BY 2 DESC")
            )
        ).fetchall()
        ult = (await db.execute(_T("SELECT max(data_onvio), max(created_at) FROM onvio_documents"))).first()
        painel = {
            "total": sum(r[1] for r in st),
            "categorias": len(st),
            "ultimo_documento": _fd(ult[0]) if ult and ult[0] else "—",
            "ultima_importacao": _fd(ult[1], "%d/%m/%Y %H:%M") if ult and ult[1] else "—",
            "por_categoria": [{"categoria": r[0], "qtde": r[1]} for r in st],
        }
        out["onvio-stats"] = painel_de_dict(
            "Onvio — estatísticas",
            "Documentos por categoria e última importação · fonte: onvio_documents",
            painel,
            kpis_de=["total", "categorias", "ultimo_documento", "ultima_importacao"],
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _log.warning("onvio: %s", exc)
    _consulta(
        "onvio-status",
        "Onvio — sessão do robô",
        "Diz se a sessão do Onvio (renovada pelo cron das 04:00) está válida. Lê o Redis quando você clica.",
        "/api/v1/onvio/status",
        [],
    )
    out["gdrive-desconectar"] = {  # POST /gdrive/desconectar
        "title": "Google Drive — desconectar (OAuth)",
        "sub": "Revoga a conexão OAuth do Drive (gdrive_config.is_connected=false). O botão 'desconectar' do GED só renomeia o arquivo de credencial — este é o que desconecta de verdade.",
        "cta": "Desconectar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/gdrive/desconectar",
            "confirm": "Desconectar o Google Drive? Os kits deixam de ser montados até reconectar.",
            "okMsg": "Drive desconectado.",
        },
        "fields": [],
    }
