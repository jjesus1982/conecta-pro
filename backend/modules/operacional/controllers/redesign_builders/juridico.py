"""Jurídico (T1) — override do _build_juridico com telas novas (leitura real).
Ação legal (parecer/transmitir) fica GATED. Ver auditoria/parity/DIVISAO_3T.md."""
from sqlalchemy import text

from sqlalchemy import text as _sql
import logging
from modules.operacional.controllers.redesign_data_controller import (
    IC, S, _ICF, _fmtdate, _helpers, _scalar, b, brl, doc, t,
)

SLUG = "juridico"

logger = logging.getLogger(__name__)
_ICO_J = "M12 2l7 4v6c0 5-3 8-7 10-4-2-7-5-7-10V6z"

EXTRA_MENU: list[dict] = [  # det-comunicacoes já vem do EXTRA_MENU do monólito
    {"id": "det-comunicacao-arquivo", "label": "Ingerir comunicação do DET (arquivo)", "icon": "M3 3v18h18"},
    {"id": "processo-analisar-arquivo", "label": "Analisar processo (arquivo)", "icon": "M3 3v18h18"},
    {"id": "prazos", "label": "Prazos", "icon": "M3 3v18h18"},
    {"id": "playbook", "label": "Playbook jurídico", "icon": "M3 3v18h18"},
    {"id": "escritorio-consultas", "label": "Consultas ao escritório", "icon": "M3 3v18h18"},
    {"id": "escritorio-consulta-nova", "label": "Registrar consulta ao escritório", "icon": "M3 3v18h18"},
    {"id": "det-status", "label": "DET — status", "icon": "M3 3v18h18"},
    {"id": "det-comunicacao-texto", "label": "Ingerir comunicação do DET (texto)", "icon": "M3 3v18h18"},
    {"id": "processo-analisar", "label": "Analisar processo (texto)", "icon": "M3 3v18h18"},
    {"id": "conhecimento-novo", "label": "Adicionar conhecimento", "icon": "M3 3v18h18"},
    {"id": "parecer-novo", "label": "Gerar parecer", "icon": "M3 3v18h18"},
    {"id": "analise-nova", "label": "Analisar documento", "icon": "M3 3v18h18"},
    {"id": "contrato-novo-modelo", "label": "Solicitar contrato novo", "icon": _ICO_J},
    {"id": "consultor-perguntar", "label": "Consultor jurídico", "icon": _ICO_J},
    {"id": "det-coletar", "label": "Coletar DET", "icon": _ICO_J},
    {"id": "det-robo-login", "label": "Login do robô DET", "icon": _ICO_J},
    {"id": "conhecimento-seed", "label": "Semear base de conhecimento", "icon": _ICO_J},
    {"id": "consultor-arquivo", "label": "Consultor jurídico — com anexo", "icon": _ICO_J},
]


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)
    n_proc = await _scalar(db, "SELECT count(*) FROM juridico_processos")

    async def _visao():
        st = (await db.execute(text("SELECT status::text, count(*) FROM juridico_processos GROUP BY status ORDER BY count(*) DESC"))).fetchall()
        tp = (await db.execute(text("SELECT tipo::text, count(*) FROM juridico_processos GROUP BY tipo ORDER BY count(*) DESC LIMIT 6"))).fetchall()
        n_conh = await _scalar(db, "SELECT count(*) FROM juridico_conhecimento")
        n_ctr = await _scalar(db, "SELECT count(*) FROM client_contracts")
        return {"title": "Visão geral", "sub": "Jurídico — dados reais", "cta": "Novo processo", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": str(n_proc), "l": "Processos", "icon": _ICF["chart"], "color": "#0F1B3A"},
                    {"v": str(await _scalar(db, "SELECT count(*) FROM juridico_processos WHERE escalonar=true") or 0), "l": "Escalonados", "icon": IC["alert"], "color": "#C2410C"},
                    {"v": str(n_conh), "l": "Base de conhecimento", "icon": IC["cal"], "color": "#0F1B3A"},
                    {"v": str(n_ctr), "l": "Contratos", "icon": _ICF["hand"], "color": "#0F1B3A"},
                ],
                "panels": [
                    {"title": "Processos por status", "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["info"]} for s, c in st] or [{"left": "Sem processos", "right": "0", **S["mut"]}]},
                    {"title": "Processos por tipo", "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["warn"]} for s, c in tp] or [{"left": "—", "right": "0", **S["mut"]}]},
                ]}

    await safe("visao", _visao())
    await safe("processos", tbl("Processos", f"{n_proc} processos", "Novo processo",
        ["Número", "Tipo", "Reclamante", "Status"], "1.4fr 1.2fr 1.8fr 0.9fr",
        "SELECT coalesce(numero,'—'), coalesce(tipo::text,'—'), coalesce(reclamante,'—'), status::text, id::text FROM juridico_processos ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ')), t(r[2]), b(r[3] or "—", "info")],
        actionsfn=lambda r: [{"title": f"Enviar processo {r[0]} ao escritório (CQB)", "sub": "Manda o dossiê por e-mail ao escritório. Simule antes.",
                              "endpoint": f"/api/v1/juridico/processos/{r[4]}/enviar-cqb", "method": "POST", "btnLabel": "Enviar CQB",
                              "submitLabel": "Enviar", "btnStyle": "outline", "okMsg": "Envio processado — veja a mensagem.",
                              "fields": [{"key": "destinatario", "label": "E-mail do escritório", "type": "text", "span": "span 2", "value": ""},
                                         {"key": "confirmar", "label": "Modo (false = simular)", "type": "text", "span": "span 1", "value": "false"}]}]))

    # DET — Comunicações (Domicílio Eletrônico Trabalhista). Serve tanto o EXTRA_MENU
    # 'det-comunicacoes' quanto o item de menu json 'processos-det' (mesma fonte real).
    _det_tone = {"nova": "warn", "aberta": "warn", "pendente": "warn", "respondida": "ok", "encerrada": "ok", "ciente": "ok", "arquivada": "mut"}

    def _det_screen():
        # id na 1ª coluna p/ o docsfn (PDF por-linha da comunicação DET). Rota curl-provada:
        # GET /api/v1/juridico/det/comunicacoes/{id}/pdf → 200 application/pdf ~363KB.
        return tbl(
            "DET — Comunicações", f"{n_det} comunicações", "—",
            ["Título", "Tipo", "Órgão", "Número", "Prazo", "Status"], "1.9fr 1fr 1.3fr 0.9fr 0.9fr 0.9fr",
            "SELECT id, coalesce(titulo,'—'), coalesce(tipo,'—'), coalesce(orgao,'—'), coalesce(numero,'—'), coalesce(prazo,'—'), coalesce(status,'—') "
            "FROM juridico_det_comunicacoes ORDER BY created_at DESC NULLS LAST LIMIT 200",
            lambda r: [t((r[1] or '—')[:52], 600, "#0F1B3A"), t(r[2]), t((r[3] or '—')[:30]), t(r[4]), t(r[5]),
                       b((r[6] or '—').capitalize(), _det_tone.get((r[6] or '').lower(), "info"))],
            docsfn=lambda r: [doc("Comunicação (PDF)", f"/api/v1/juridico/det/comunicacoes/{r[0]}/pdf", fmt="pdf")])
    n_det = await _scalar(db, "SELECT count(*) FROM juridico_det_comunicacoes")
    await safe("det-comunicacoes", _det_screen())
    await safe("processos-det", _det_screen())

    # Contratos (jurídico) — `contracts`, a tabela canônica.
    # Lia `client_contracts`, que é a PONTE DE FATURAMENTO: só recebe contrato quando ele
    # é ATIVADO (_bridge_contract_to_billing). Resultado: a tela mostrava 10 de 15 e
    # escondia justamente os `draft` — que são os que precisam do PDF para ser ASSINADOS.
    # O Green Hills (CTR-2026-00019) não aparecia aqui no dia em que foi montado.
    out["contrato-novo-modelo"] = tela_contrato_novo()

    await safe("contratos", tbl(
        "Contratos", f"{await _scalar(db, 'SELECT count(*) FROM contracts')} contratos · "
        "clique em Baixar para gerar o instrumento completo pelo modelo cadastrado", "—",
        ["Contrato", "Cliente", "Serviço", "Início", "Fim", "Mensal", "Status"],
        "1.1fr 1.6fr 1.1fr 0.85fr 0.85fr 1fr 0.9fr",
        "SELECT coalesce(c.contract_number,'—'), coalesce(cl.name,'—'), "
        "coalesce(c.tipo_servico::text,'—'), c.start_date, c.end_date, c.monthly_value, "
        "coalesce(c.status::text,'—'), c.template_id::text, c.id::text "
        "FROM contracts c LEFT JOIN clients cl ON cl.id=c.client_id "
        "WHERE coalesce(c.is_active,true) ORDER BY c.start_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—')[:34]), t((r[2] or '—').replace('_', ' ')),
                   t(_fmtdate(r[3])), t(_fmtdate(r[4])),
                   t(brl(r[5]) if r[5] is not None else '—', 600),
                   b((r[6] or '—').capitalize(), "ok" if (r[6] or '').lower() in ("active", "ativo", "vigente") else "mut")],
        # o botão só aparece em quem TEM modelo vinculado: oferecer download que devolve
        # 422 é pior que não oferecer.
        docsfn=lambda r: ([doc("Contrato completo (PDF)",
                               f"/api/v1/crm/contracts/{r[0]}/pdf-modelo", fmt="pdf")] if r[7] else
                          [doc("Resumo do contrato (PDF)",
                               f"/api/v1/crm/contracts/{r[0]}/pdf", fmt="pdf")])))

    # Base de conhecimento jurídico — juridico_conhecimento
    await safe("conhecimento", tbl(
        "Base de conhecimento", f"{await _scalar(db, 'SELECT count(*) FROM juridico_conhecimento')} itens", "—",
        ["Título", "Tipo", "Área", "Desfecho"], "2fr 1fr 1.1fr 1.4fr",
        "SELECT coalesce(titulo,'—'), coalesce(tipo::text,'—'), coalesce(area,'—'), coalesce(desfecho,'—') "
        "FROM juridico_conhecimento WHERE coalesce(ativo,true)=true ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t((r[0] or '—')[:60], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ')), t(r[2]), t((r[3] or '—')[:50])]))

    # 'escritorio' (juridico_escritorio_consultas) NÃO wirado: só contém linha de teste
    # (__probe_frontend__) → fica honesto "aguardando dado" até haver consulta real.

    # Análises (contratos/documentos) — juridico_analises (resultado é JSON → extrai resumo)
    def _risk_b(v):
        try:
            n = float(v)
        except (TypeError, ValueError):
            return b(str(v or "—"), "info")
        return b(f"risco {n:.0f}", "bad" if n >= 67 else "warn" if n >= 34 else "ok")
    await safe("analise", tbl(
        "Análises", f"{await _scalar(db, 'SELECT count(*) FROM juridico_analises')} análises", "—",
        ["Nome", "Tipo", "Parecer", "Risco"], "1.5fr 1fr 2fr 0.9fr",
        "SELECT coalesce(nome,'—'), coalesce(tipo::text,'—'), coalesce(resultado->>'resumo', resultado::text, '—'), score_risco "
        "FROM juridico_analises ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t((r[0] or '—')[:48], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ')), t((r[2] or '—')[:75]), _risk_b(r[3])]))

    # Riscos jurídicos — Exposição trabalhista por funcionário. FIDELIDADE: reusa o MESMO
    # serviço do clássico (riscos_service.riscos_trabalhista) → os números batem. Sync → thread.
    try:
        import asyncio

        from core.database.session import SyncSessionLocal
        from modules.juridico import riscos_service

        def _sync_riscos():
            sdb = SyncSessionLocal()
            try:
                return riscos_service.riscos_trabalhista(sdb)
            finally:
                sdb.close()

        rk = await asyncio.to_thread(_sync_riscos)
        det = rk.get("detalhado", []) or []
        _VLBL0 = {"fgts_multa_40": "FGTS+multa 40%", "aviso_previo": "Aviso prévio",
                  "ferias_prop_mais_terco": "Férias+1/3", "decimo_terceiro_prop": "13º",
                  "diferenca_piso_retroativa": "Dif. piso"}
        _por_tipo = " · ".join(f"{_VLBL0.get(k, k)} {brl(v)}"
                               for k, v in sorted((rk.get("por_tipo") or {}).items(), key=lambda x: -(x[1] or 0))
                               if v)

        _VLBL = {  # rótulos do clássico (fidelidade — o clássico vence)
            "fgts_multa_40": "FGTS + multa 40%", "aviso_previo": "Aviso prévio",
            "ferias_prop_mais_terco": "Férias prop. + 1/3", "decimo_terceiro_prop": "13º proporcional",
            "diferenca_piso_retroativa": "Diferença de piso", "horas_extras_noturno": "Horas extras/noturno",
            "adicionais_risco": "Adicionais de risco",
        }

        def _verbas_tags(v: dict) -> str:
            xs = [_VLBL.get(k, k.replace('_', ' ')) for k, vv in (v or {}).items()
                  if isinstance((vv or {}).get('valor'), (int, float)) and (vv or {}).get('valor')]
            return " · ".join(xs)

        out["riscos"] = {
            "title": "Riscos Jurídicos — Exposição trabalhista",
            "sub": (f"Exposição estimada total {brl(rk.get('total_exposicao_estimada', 0))} · "
                    f"{rk.get('funcionarios_com_risco', 0)} de {rk.get('funcionarios_analisados', 0)} "
                    f"colaboradores com risco (estimativa, não provisão)"
                    + (f" · Por tipo de verba: {_por_tipo}" if _por_tipo else "")),
            "cta": "—", "type": "table", "searchHint": "Buscar colaborador…",
            "grid": "1.8fr 1.3fr 0.8fr 1fr 1.9fr",
            "cols": ["Colaborador", "Cargo", "Meses casa", "Exposição estimada", "Verbas"],
            "rows": [{"cells": [
                t(d.get("nome") or "—", 600, "#0F1B3A"),
                t(d.get("cargo") or "—"),
                t(str(d.get("meses_de_casa")) if d.get("meses_de_casa") is not None else "—"),
                t(brl(d.get("exposicao_estimada") or 0), 600, "#0F1B3A"),
                t(_verbas_tags(d.get("verbas")) or "—"),
            ]} for d in det[:300]],
        }
        # Seção Tributário (mesmo serviço do clássico) → painéis abaixo da tabela (tela composta)
        try:
            def _sync_trib():
                sdb = SyncSessionLocal()
                try:
                    return riscos_service.riscos_tributario(sdb)
                finally:
                    sdb.close()

            tb = await asyncio.to_thread(_sync_trib)
            enq = tb.get("enquadramento", {}) or {}
            _nt = {"alto": "bad", "atenção": "warn", "atencao": "warn", "medio": "warn", "baixo": "ok"}
            out["riscos"]["panelGrid"] = "1fr 1fr"
            out["riscos"]["panels"] = [
                {"title": "Tributário — Enquadramento (Simples × Lucro Real)", "rows": [
                    {"left": "Faturamento anualizado", "right": brl(enq.get("faturamento_anualizado", 0)), **S["info"]},
                    {"left": "Teto do Simples (anual)", "right": brl(enq.get("teto_simples_anual", 0)), **S["info"]},
                    {"left": "Ocupação do teto", "right": f"{enq.get('ocupacao_teto_pct', '—')}%", **S["warn"]},
                    {"left": "Pode optar pelo Simples?", "right": "Sim" if enq.get("pode_simples") else "Não",
                     **(S["ok"] if enq.get("pode_simples") else S["bad"])},
                ]},
                {"title": "Riscos tributários identificados", "rows": [
                    {"left": (r.get("tema") or "—")[:64], "right": (r.get("nivel") or "—").capitalize(),
                     **S[_nt.get((r.get("nivel") or "").lower(), "info")]}
                    for r in (tb.get("riscos") or [])
                ] or [{"left": "Nenhum risco tributário", "right": "OK", **S["ok"]}]},
            ]
        except Exception:  # noqa: BLE001 — tributário não derruba a tabela trabalhista
            pass
    except Exception:  # noqa: BLE001 — riscos não derruba o resto do módulo
        pass

    # ── FIOS SOLTOS DO JURIDICO (2026-08-10) ────────────────────────────────────────
    # DE FORA: /det/ingest-robo (o ROBO empurra, com x_robo_token — quem chama nao e
    # tela) e /consultor/perguntar-arquivo (mistura query param com upload multipart;
    # o renderizador manda multipart OU json, nao os dois — form ai sairia quebrado).
    out["consultor-perguntar"] = {
        "title": "Consultor jurídico",
        "sub": "Pergunta ancorada nos processos e contratos reais. É CONSULTA — não gera "
               "parecer assinado nem peça processual.",
        "cta": "Perguntar", "type": "form",
        # showResult: a resposta E o produto. Sem a flag a tela diria "Consulta feita" e
        # descartaria o texto — botao mudo. Opt-in; ignorada ate o front subir.
        "submit": {"endpoint": "/api/v1/juridico/consultor/perguntar",
                   "okMsg": "Consulta respondida", "showResult": True},
        "fields": [
            {"key": "area", "label": "Área*", "type": "select", "span": "span 1", "ph": "Selecione",
             "options": [{"value": "trabalhista", "label": "Trabalhista"},
                         {"value": "civel", "label": "Cível"},
                         {"value": "tributaria", "label": "Tributária"}]},
            {"key": "contrato_id", "label": "Contrato (id) — opcional", "type": "text", "span": "span 1"},
            {"key": "pergunta", "label": "Pergunta*", "type": "textarea", "span": "span 2",
             "ph": "Ex.: qual o risco de passivo em rescisão sem justa causa neste contrato?"},
        ],
    }
    out["det-coletar"] = {
        "title": "Coletar DET (Domicílio Eletrônico Trabalhista)",
        "sub": "Dispara a coleta da caixa do DET pelo robô e registra as mensagens no ERP.",
        "cta": "Coletar agora", "type": "form",
        "submit": {"endpoint": "/api/v1/juridico/det/robo/coletar",
                   "okMsg": "Coleta disparada — as mensagens aparecem em Comunicações DET",
                   "confirm": "Dispara a coleta no gov.br pelo robô. Confirma?"},
        "fields": [],
    }
    out["det-robo-login"] = {
        "title": "Login supervisionado do robô DET",
        "sub": "Sobe o navegador do robô no noVNC para você fazer o login do gov.br à mão. "
               "Use quando a coleta falhar por sessão expirada.",
        "cta": "Abrir login", "type": "form",
        "submit": {"endpoint": "/api/v1/juridico/det/robo/login",
                   "okMsg": "Navegador do robô aberto — conclua o login no noVNC"},
        "fields": [],
    }
    out["conhecimento-seed"] = {
        "title": "Semear base de conhecimento jurídico",
        "sub": "Carrega os casos e procedimentos reais na base do consultor. Idempotente — "
               "rodar de novo não duplica.",
        "cta": "Semear", "type": "form",
        "submit": {"endpoint": "/api/v1/juridico/conhecimento/seed", "okMsg": "Base semeada"},
        "fields": [],
    }

    out["consultor-arquivo"] = {
        "title": "Consultor jurídico — com anexo",
        "sub": "Anexe contrato, notificação ou peça e pergunte sobre o documento. O arquivo é lido para responder, não fica guardado.",
        "cta": "Analisar", "type": "form",
        "submit": {"endpoint": "/api/v1/juridico/consultor/perguntar-arquivo",
                   "multipart": True, "query": True,
                   "okMsg": "Análise concluída", "showResult": True},
        "fields": [
            {"key": "arquivo", "label": "Arquivo*", "type": "file", "span": "span 2"},
            {"key": "area", "label": "Área", "type": "text", "span": "span 2", "ph": "Ex.: trabalhista, cível, tributária"},
            {"key": "pergunta", "label": "Pergunta*", "type": "textarea", "span": "span 2"},
        ],
    }

    # 'det-coletar-auto' aposentada 08/09/2026: a rota /det/coletar era um stub (coletadas: 0 fixo).
    # O caminho real é o robô ('Coletar DET').

    await _ligar_jur_20260908(db, out)
    await _ligar_lote4_20260908(db, out)
    return out


# ── AÇÃO: solicitar contrato novo pelo modelo ─────────────────────────────────────────
# Terceira superfície da mesma capacidade (chat e Cowork são as outras). Todas passam pelo
# MESMO serviço — `contract_wizard.criar_contrato` — para a regra de quem pode emitir e a
# resolução do CNPJ nunca divergirem entre as entradas.
from fastapi import APIRouter, Body, Depends, HTTPException  # noqa: E402

from core.auth.dependencies import CurrentActiveUser  # noqa: E402
from core.database import get_db  # noqa: E402

# o dispatcher do redesign inclui automaticamente o `router` de cada builder de módulo
router = APIRouter()


@router.post("/action/contrato-novo-modelo")
async def _rd_contrato_novo(current_user: CurrentActiveUser,
                            payload: dict = Body(default={}), db=Depends(get_db)) -> dict:
    """Cria contrato já ligado ao modelo, ao tipo de serviço e ao CNPJ emitente."""
    from modules.crm.services import contract_wizard as W

    try:
        W.exigir_emitente(current_user)
    except W.NaoAutorizado as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    falta = [rot for rot, k in (("CNPJ do cliente", "cliente_documento"),
                                ("modalidade", "modalidade"),
                                ("valor mensal", "valor_mensal"),
                                ("início da vigência", "vigencia_inicio"))
             if not str(payload.get(k) or "").strip()]
    if falta:
        raise HTTPException(status_code=400, detail="Informe: " + ", ".join(falta))
    try:
        r = await W.criar_contrato(
            db, cliente_documento=str(payload["cliente_documento"]),
            modalidade=str(payload["modalidade"]),
            valor_mensal=float(str(payload["valor_mensal"]).replace(",", ".")),
            vigencia_inicio=str(payload["vigencia_inicio"])[:10],
            vigencia_meses=int(payload.get("vigencia_meses") or 12),
            dia_vencimento=int(payload["dia_vencimento"]) if payload.get("dia_vencimento") else None,
            renovacao_aviso_dias=int(payload.get("renovacao_aviso_dias") or 30),
            carencia_dias=int(payload["carencia_dias"]) if payload.get("carencia_dias") else None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if r.get("status") != "criado":
        # recusa de negócio (cliente fora do CRM, modalidade sem modelo) sobe como 400 com o
        # texto que a pessoa lê — não como sucesso silencioso
        raise HTTPException(status_code=400, detail=r.get("resumo") or r.get("status"))
    pend = r.get("perguntas") or []
    return {"ok": True, "message": (
        f"{r['contrato']} criado para {r['cliente']} pelo modelo '{r['modelo']}' "
        f"({r['vigencia']}). "
        + ("Pronto para emitir o PDF na tela de Contratos."
           if r.get("pronto_para_emitir")
           else "Faltam: " + "; ".join(p["pergunta"] for p in pend[:4])))}


def tela_contrato_novo() -> dict:
    """Formulário do jurídico. `valor_mensal` e `vigencia_inicio` sem default de propósito:
    contrato com valor ou data chutados vai para assinatura assim."""
    return {
        "title": "Solicitar contrato novo (pelo modelo)",
        "sub": "Cria o contrato já ligado ao modelo, ao tipo de serviço e ao CNPJ emitente "
               "correto — mão de obra pela Patrimonial, segurança eletrônica pela "
               "Eletrônica. Recusa cliente que não esteja no CRM.",
        "cta": "Criar contrato", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/contrato-novo-modelo", "gated": False,
                   "confirm": "Criar o contrato com estes dados?",
                   "okMsg": "Contrato criado."},
        "fields": [
            {"name": "cliente_documento", "label": "CNPJ do cliente", "type": "text",
             "placeholder": "00.000.000/0001-00", "required": True},
            {"name": "modalidade", "label": "Modalidade", "type": "select", "required": True,
             "options": [{"value": "portaria", "label": "Portaria / Controle de acesso"},
                         {"value": "servicos_gerais", "label": "Serviços gerais / Limpeza (ASG)"},
                         {"value": "jardinagem", "label": "Jardinagem"},
                         {"value": "piscina", "label": "Piscina"},
                         {"value": "zeladoria", "label": "Zeladoria"},
                         {"value": "eletronica", "label": "Segurança eletrônica / CFTV"}]},
            {"name": "valor_mensal", "label": "Valor mensal (R$)", "type": "number",
             "required": True},
            {"name": "vigencia_inicio", "label": "Início da vigência", "type": "date",
             "required": True},
            {"name": "vigencia_meses", "label": "Vigência (meses)", "type": "number",
             "default": 12},
            {"name": "dia_vencimento", "label": "Dia do vencimento", "type": "number"},
            {"name": "renovacao_aviso_dias", "label": "Aviso de não renovação (dias)",
             "type": "number", "default": 30},
            {"name": "carencia_dias", "label": "Carência do 1º pagamento (dias)",
             "type": "number"},
        ],
    }


async def _ligar_jur_20260908(db, out: dict) -> None:
    """LIGAR 08/09/2026: prazos, playbook, escritório, DET, processos por texto, conhecimento, parecer, análise."""
    from modules.juridico import conhecimento_controller as K, det_controller as D, escritorio_controller as E, hub_controller as H
    from modules.operacional.controllers.redesign_builders._ligar_generico import chamar, painel_de_dict, selecionar, tabela_de_lista
    for key, fn, titulo, sub, kw in (
        ("prazos", H.listar_prazos, "Prazos jurídicos", "Prazos manuais + automáticos (vencimento/renovação/reajuste dos contratos).", {"incluir_automaticos": True, "status": None}),
        ("playbook", K.listar_playbook, "Playbook jurídico", "Regras da casa: o que fazer em cada situação (6 entradas + o que você adicionar).", {}),
        ("escritorio-consultas", E.listar_consultas, "Consultas ao escritório", "O que foi perguntado ao escritório externo, quando e quanto custou.", {"resolvido_por": None, "area": None, "data_inicio": None, "data_fim": None, "limit": 200}),
    ):
        try:
            res = await chamar(fn, db, **kw)
            out[key] = tabela_de_lista(titulo, sub, res)
        except Exception as exc:  # noqa: BLE001
            logger.warning("juridico %s: %s", key, exc)
    try:
        roi = await chamar(E.roi, db, meses=12)
        if isinstance(roi, dict) and "escritorio-consultas" in out:
            out["escritorio-consultas"]["sub"] += " · ROI 12 meses: " + " · ".join(f"{k} {v}" for k, v in roi.items() if not isinstance(v, (list, dict)))[:160]
    except Exception:  # noqa: BLE001
        pass
    try:
        import asyncio as _aio
        st = await _aio.wait_for(chamar(D.status, db), timeout=5)
        try:
            rb = await _aio.wait_for(chamar(D.robo_status, db), timeout=3)  # o robô pausado segura 15 s; a página não espera
        except Exception as exc:  # noqa: BLE001
            rb = {"robo": f"indisponível: {str(exc)[:60] or 'sem resposta em 3 s'}"}
        out["det-status"] = painel_de_dict("DET — status", "Domicílio Eletrônico Trabalhista: comunicações ingeridas e situação do robô de coleta.", {**(st if isinstance(st, dict) else {"status": st}), "robo": rb})
    except Exception as exc:  # noqa: BLE001
        logger.warning("det status: %s", exc)
    emp = []
    try:
        emp = [{"value": str(i), "label": n} for i, n in (await db.execute(_sql("SELECT id, nome FROM employees WHERE status='ativo' ORDER BY nome LIMIT 300"))).fetchall()]
    except Exception:  # noqa: BLE001
        await db.rollback()
    _AREAS = [{"value": v, "label": v.capitalize()} for v in ("trabalhista", "tributario", "civel", "contratual", "lgpd", "administrativo", "outro")]
    out["escritorio-consulta-nova"] = {
        "title": "Registrar consulta ao escritório", "sub": "Registra a consulta feita ao escritório externo (ou resolvida internamente) e o custo. Alimenta o ROI.",
        "cta": "Registrar", "type": "form", "submit": {"endpoint": "/api/v1/juridico/escritorio/consultas", "okMsg": "Consulta registrada"},
        "fields": [{"key": "assunto", "label": "Assunto*", "type": "text", "span": "span 2"}, selecionar("area", "Área", _AREAS, "span 1"),
                   selecionar("resolvido_por", "Resolvido por*", [{"value": "interno", "label": "Interno (Conecta)"}, {"value": "escritorio", "label": "Escritório externo"}, {"value": "ia", "label": "Consultor IA"}], "span 1"),
                   {"key": "custo", "label": "Custo (R$)", "type": "number", "span": "span 1"}, {"key": "data", "label": "Data", "type": "date", "span": "span 1"},
                   {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2"}]}
    out["det-comunicacao-texto"] = {
        "title": "Ingerir comunicação do DET (texto)", "sub": "Cole o texto da comunicação recebida no DET; o sistema classifica, extrai prazo e registra.",
        "cta": "Ingerir", "type": "form", "submit": {"endpoint": "/api/v1/juridico/det/comunicacao", "okMsg": "Comunicação registrada", "showResult": True},
        "fields": [{"key": "texto", "label": "Texto da comunicação*", "type": "textarea", "span": "span 2"}]}
    out["processo-analisar"] = {
        "title": "Analisar processo (texto)", "sub": "Cole a petição/notificação; a análise extrai pedidos, entidades e monta o dossiê. Não envia nada.",
        "cta": "Analisar", "type": "form", "submit": {"endpoint": "/api/v1/juridico/processos", "okMsg": "Processo analisado", "showResult": True},
        "fields": [{"key": "numero", "label": "Número do processo", "type": "text", "span": "span 1"}, {"key": "tipo", "label": "Tipo", "type": "text", "span": "span 1", "ph": "trabalhista"},
                   selecionar("employee_id", "Colaborador envolvido", emp), {"key": "texto", "label": "Texto*", "type": "textarea", "span": "span 2"}]}
    out["conhecimento-novo"] = {
        "title": "Adicionar conhecimento", "sub": "Precedente, tese ou regra que o consultor jurídico passa a considerar.",
        "cta": "Salvar", "type": "form", "submit": {"endpoint": "/api/v1/juridico/conhecimento", "okMsg": "Conhecimento adicionado"},
        "fields": [selecionar("tipo", "Tipo*", [{"value": v, "label": v.capitalize()} for v in ("precedente", "tese", "regra", "modelo")], "span 1"), selecionar("area", "Área*", _AREAS, "span 1"),
                   {"key": "titulo", "label": "Título*", "type": "text", "span": "span 2"}, {"key": "palavras_chave", "label": "Palavras-chave", "type": "text", "span": "span 2"},
                   {"key": "resumo", "label": "Resumo", "type": "textarea", "span": "span 2"}, {"key": "fundamentacao", "label": "Fundamentação", "type": "textarea", "span": "span 2"},
                   {"key": "desfecho", "label": "Desfecho", "type": "text", "span": "span 1"}, {"key": "fonte", "label": "Fonte", "type": "text", "span": "span 1"}]}
    out["parecer-novo"] = {
        "title": "Gerar parecer", "sub": "Parecer jurídico em PDF no padrão da casa, a partir do contexto informado (usa o provedor de IA).",
        "cta": "Gerar", "type": "form", "submit": {"endpoint": "/api/v1/juridico/pareceres", "okMsg": "Parecer gerado", "showResult": True},
        "fields": [selecionar("area", "Área*", _AREAS, "span 1"), {"key": "titulo", "label": "Título*", "type": "text", "span": "span 1"},
                   {"key": "contexto", "label": "Contexto / pergunta*", "type": "textarea", "span": "span 2"}]}
    out["analise-nova"] = {
        "title": "Analisar documento", "sub": "Análise de cláusulas e riscos de um documento colado (usa o provedor de IA).",
        "cta": "Analisar", "type": "form", "submit": {"endpoint": "/api/v1/juridico/analises", "okMsg": "Análise registrada", "showResult": True},
        "fields": [{"key": "nome", "label": "Nome do documento*", "type": "text", "span": "span 2"}, {"key": "conteudo", "label": "Conteúdo*", "type": "textarea", "span": "span 2"}]}


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

    emp = []
    try:
        emp = [{"value": str(i), "label": n} for i, n in (await db.execute(_T("SELECT id, nome FROM employees WHERE status='ativo' ORDER BY nome LIMIT 400"))).fetchall()]
    except Exception:  # noqa: BLE001
        await db.rollback()
    out["det-comunicacao-arquivo"] = {  # POST /juridico/det/comunicacao/upload (multipart)
        "title": "Ingerir comunicação do DET (arquivo)", "sub": "Suba o PDF baixado do DET; o sistema extrai o texto, classifica, acha o prazo e registra — igual à versão texto.",
        "cta": "Ingerir", "type": "form", "submit": {"endpoint": "/api/v1/juridico/det/comunicacao/upload", "multipart": True, "okMsg": "Comunicação registrada", "showResult": True},
        "fields": [{"key": "arquivo", "label": "PDF da comunicação*", "type": "file", "span": "span 2", "accept": ".pdf"}]}
    out["processo-analisar-arquivo"] = {  # POST /juridico/processos/upload (multipart)
        "title": "Analisar processo (arquivo)", "sub": "Suba a petição/notificação em PDF; a análise extrai pedidos, entidades e monta o dossiê. Não envia nada.",
        "cta": "Analisar", "type": "form", "submit": {"endpoint": "/api/v1/juridico/processos/upload", "multipart": True, "okMsg": "Processo analisado", "showResult": True},
        "fields": [{"key": "arquivo", "label": "PDF*", "type": "file", "span": "span 2", "accept": ".pdf"}, {"key": "numero", "label": "Número do processo", "type": "text", "span": "span 1"},
                   {"key": "tipo", "label": "Tipo", "type": "text", "span": "span 1", "ph": "trabalhista"}, selecionar("employee_id", "Colaborador envolvido", emp)]}
