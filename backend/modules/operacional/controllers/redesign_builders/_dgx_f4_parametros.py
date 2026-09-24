"""DGX F4 — Parâmetros do sistema por CNPJ (24/09/2026).

O DGX tem 127 parâmetros `{nome, valor, chaveEmpresa}` e UMA tela de Configurações em seções.
Aqui: `system_configs` ganha `valor_por_empresa` jsonb ({cnpj: valor}); o leitor é
`core/parametros.py` (empresa → global → default); esta frente semeia os parâmetros do DGX que
fazem sentido na casa com o VALOR QUE O CÓDIGO USA HOJE (nunca inventado — sem fonte, NULL e
editável) e dá a porta: tela `parametros` (uma coluna por empresa do grupo, Editar por linha)
e `parametro-editar` (form), ambas gravando por `parametro-salvar` com histórico.

Plugada em `configuracoes.py` (router + MENU + `telas(db, out)`); prefixo `_` = o discovery pula.
Deep-links: `/redesign/configuracoes?t=parametros` e `?t=parametro-editar`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text

from core import parametros
from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

_ICO = "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33"
_ND = "#0F1B3A"

MENU: list[dict] = [
    {"id": "parametros", "label": "Parâmetros do sistema", "icon": _ICO, "grupo": "Parâmetros"},
    {"id": "parametro-editar", "label": "Editar parâmetro", "icon": _ICO, "grupo": "Parâmetros"},
]

_SEM_FONTE = "sem fonte no código — valor a definir pelo dono"


def _s(chave, nome, valor, tipo, grupo, descricao, origem, dgx=None) -> dict:
    return {
        "chave": chave,
        "nome": nome,
        "valor": valor,
        "tipo": tipo,
        "grupo": grupo,
        "descricao": descricao,
        "origem": origem,
        "dgx": dgx,
    }


#: Valor = o que o código usa HOJE (origem citada). None = não existe no código: fica NULL,
#: editável, e nenhum chamador lê com default — o oráculo (e) garante isso.
SEED: list[dict] = [
    # ── folha / apontamento ──
    _s(
        "folha.adiantamento_percentual",
        "Adiantamento salarial (%)",
        "40",
        "float",
        "folha",
        "Percentual do salário base pago como adiantamento no dia 20 (rubrica 1045). 0 desliga a regra.",
        "calculo_service.ADIANTAMENTO_PERCENTUAL = 0.40",
    ),
    _s(
        "folha.dia_apontamento",
        "Dia de apontamento",
        None,
        "integer",
        "folha",
        "Dia do mês em que o apontamento da folha é fechado (DGX: DiaApontamento).",
        _SEM_FONTE,
        "DiaApontamento",
    ),
    _s(
        "folha.dias_antes_lancar_ausencia",
        "Dias antes de lançar ausência",
        None,
        "integer",
        "folha",
        "Quantos dias após a falta o sistema lança a ausência na folha (DGX: DiasAntesLancarAusencia).",
        _SEM_FONTE,
        "DiasAntesLancarAusencia",
    ),
    # ── ponto ──
    _s(
        "ponto.tolerancia_entrada_min",
        "Tolerância de entrada (min)",
        "15",
        "integer",
        "ponto",
        "Minutos de atraso tolerados antes de o painel cobrar e o quadro marcar 'atrasado'. Vale para os dois lados (antecipado dentro da tolerância não é hora extra).",
        "coorte_ponto.TOLERANCIA_ENTRADA_MIN = 15 · presence_controller.TOLERANCIA_ATRASO = 15 min",
        "ToleranciaIntegracaoBatimentos",
    ),
    _s(
        "ponto.geofence_raio_padrao_m",
        "Raio padrão do geofence (m)",
        "150",
        "integer",
        "ponto",
        "Raio em metros usado quando o posto é cadastrado sem raio próprio (DGX: CONTROLE_ACESSO_RAIO_MAXIMO).",
        "models/post.py geofence_raio_metros default=150",
        "CONTROLE_ACESSO_RAIO_MAXIMO",
    ),
    _s(
        "ponto.facial_obrigatoria",
        "Facial obrigatória",
        None,
        "boolean",
        "ponto",
        "Se a batida exige reconhecimento facial para valer (hoje o limiar vive em ponto.facial.limiar_distancia).",
        _SEM_FONTE,
    ),
    _s(
        "ponto.arredondamento_min",
        "Arredondamento das batidas (min)",
        None,
        "integer",
        "ponto",
        "Arredonda a batida para múltiplos de N minutos ao apurar horas. Vazio = sem arredondamento.",
        _SEM_FONTE,
    ),
    # ── fechamento ──
    _s(
        "fechamento.dia_fechamento_ponto",
        "Dia de fechamento do ponto",
        None,
        "integer",
        "fechamento",
        "Dia do mês em que o ponto da competência é fechado (DGX: DiasFechamento).",
        _SEM_FONTE,
        "DiasFechamento",
    ),
    _s(
        "fechamento.dias_limite_faturamento",
        "Dias limite para faturar",
        None,
        "integer",
        "fechamento",
        "Dias após o fechamento para emitir o faturamento do mês (DGX: DiasLimiteFaturamento).",
        _SEM_FONTE,
        "DiasLimiteFaturamento",
    ),
    _s(
        "fechamento.linhas_grid",
        "Linhas por página nas grades",
        None,
        "integer",
        "fechamento",
        "Quantidade de linhas exibidas por página nas grades de fechamento (DGX: LinhasGridFechamento = 50).",
        _SEM_FONTE,
        "LinhasGridFechamento",
    ),
    # ── benefícios ──
    _s(
        "beneficios.vt_desconto_pct",
        "Desconto de VT (%)",
        "4",
        "float",
        "beneficios",
        "Percentual do salário base descontado a título de vale-transporte (CCT SINDECOMPRESTS: 4%, não os 6% da lei).",
        "calculo_service.DESC_VT_PCT = 0.04",
    ),
    _s(
        "beneficios.vr_desconto_pct",
        "Desconto de VR (%)",
        "1",
        "float",
        "beneficios",
        "Percentual do salário base descontado a título de vale-refeição.",
        "calculo_service.DESC_VR_PCT = 0.01",
    ),
    _s(
        "beneficios.vt_valor_dia",
        "VT por dia (R$)",
        "10.00",
        "float",
        "beneficios",
        "Valor do vale-transporte por dia trabalhado.",
        "calculo_service.VT_DIA = 10.00",
    ),
    _s(
        "beneficios.vr_valor_dia",
        "VR por dia (R$)",
        "22.00",
        "float",
        "beneficios",
        "Valor do vale-refeição por dia trabalhado.",
        "calculo_service.VR_DIA = 22.00",
    ),
    _s(
        "beneficios.dias_vt_vr_modo",
        "Dias de VT/VR — modo",
        "escala",
        "string",
        "beneficios",
        "Como contar os dias que geram VT/VR: 'escala' = 12x36 pelos dias da escala, 44h pelos dias úteis reais (VR sem sábado).",
        "calculo_service.dias_vt_vr()",
    ),
    _s(
        "beneficios.dias_vt_vr_12x36",
        "Dias de VT/VR na 12x36",
        "15",
        "integer",
        "beneficios",
        "Dias de escala que geram VT e VR na 12x36.",
        "calculo_service.DIAS_TRAB_ESCALA['12x36'] = 15",
    ),
    # ── financeiro ──
    _s(
        "financeiro.cobranca_dias_a_vencer_email",
        "Cobrança: dias antes do vencimento",
        None,
        "integer",
        "financeiro",
        "Quantos dias antes do vencimento o e-mail de cobrança automático sai (DGX: CRDiasAVencerEmailAuto).",
        _SEM_FONTE,
        "CRDiasAVencerEmailAuto",
    ),
    _s(
        "financeiro.cobranca_dias_vencidos_email",
        "Cobrança: dias após vencido",
        None,
        "integer",
        "financeiro",
        "Quantos dias após o vencimento o e-mail de cobrança automático sai (DGX: CRDiasVencidosEmailAuto).",
        _SEM_FONTE,
        "CRDiasVencidosEmailAuto",
    ),
    # ── fiscal ──
    _s(
        "fiscal.nfse_envio_automatico",
        "NFS-e: envio automático",
        None,
        "boolean",
        "fiscal",
        "Se a NFS-e é transmitida automaticamente ao fechar o faturamento (DGX: NotasServicoEnvioAutomatico).",
        _SEM_FONTE,
        "NotasServicoEnvioAutomatico",
    ),
    _s(
        "fiscal.nfse_valor_proporcional_dias",
        "NFS-e: dias do valor proporcional",
        None,
        "integer",
        "fiscal",
        "Base de dias para NFS-e proporcional em contrato iniciado/encerrado no meio do mês (DGX: 30).",
        _SEM_FONTE,
        "NotaServicoDiasContratoValorProporcional",
    ),
    # ── empresa ──
    _s(
        "empresa.dominio",
        "Domínio",
        "www.conectamais.pro",
        "string",
        "empresa",
        "Domínio institucional impresso nos documentos (DGX: DominioPatrimonialOnline).",
        "pdf_branding.EMPRESA['site']",
        "DominioPatrimonialOnline",
    ),
    _s(
        "empresa.email_remetente",
        "E-mail remetente",
        "noreply@conectamais.pro",
        "email",
        "empresa",
        "Remetente dos e-mails do sistema.",
        "settings.SMTP_FROM_EMAIL",
    ),
    # ── senha (só a estrutura) ──
    _s(
        "senha.qtd_digitos",
        "Senha: tamanho mínimo",
        None,
        "integer",
        "senha",
        "Tamanho mínimo da senha (DGX: SenhaQtdDigitos).",
        _SEM_FONTE,
        "SenhaQtdDigitos",
    ),
    _s(
        "senha.maiusculas",
        "Senha: exige maiúsculas",
        None,
        "boolean",
        "senha",
        "Exige ao menos uma letra maiúscula.",
        _SEM_FONTE,
        "SenhaComMaiusculas",
    ),
    _s(
        "senha.minusculas",
        "Senha: exige minúsculas",
        None,
        "boolean",
        "senha",
        "Exige ao menos uma letra minúscula.",
        _SEM_FONTE,
        "SenhaComMinusculas",
    ),
    _s(
        "senha.numeros",
        "Senha: exige números",
        None,
        "boolean",
        "senha",
        "Exige ao menos um número.",
        _SEM_FONTE,
        "SenhaComNumeros",
    ),
    _s(
        "senha.simbolos",
        "Senha: exige símbolos",
        None,
        "boolean",
        "senha",
        "Exige ao menos um símbolo.",
        _SEM_FONTE,
        "SenhaComSimbolos",
    ),
    _s(
        "senha.dias_expiracao",
        "Senha: dias para expirar",
        None,
        "integer",
        "senha",
        "Dias até a senha expirar. Vazio = não expira.",
        _SEM_FONTE,
        "SenhaDiasExpiracao",
    ),
]

_DDL = ("ALTER TABLE system_configs ADD COLUMN IF NOT EXISTS valor_por_empresa jsonb NOT NULL DEFAULT '{}'::jsonb",)
_SEED_SQL = text(
    "INSERT INTO system_configs (id, chave, nome, valor, valor_padrao, tipo, valor_type, grupo, descricao, metadata, "
    " is_editavel, scope) VALUES (gen_random_uuid(), :chave, :nome, :valor, :valor, CAST(:tipo AS setting_type), :tipo, "
    " :grupo, :descricao, CAST(:meta AS jsonb), true, 'global') ON CONFLICT (chave) DO NOTHING"
)


async def _ensure(db) -> None:
    for ddl in _DDL:
        await db.execute(text(ddl))
    for s in SEED:
        await db.execute(
            _SEED_SQL,
            {
                "chave": s["chave"],
                "nome": s["nome"],
                "valor": s["valor"],
                "tipo": s["tipo"],
                "grupo": s["grupo"],
                "descricao": s["descricao"],
                "meta": json.dumps({"origem": s["origem"], "dgx": s["dgx"], "frente": "dgx-f4"}),
            },
        )


async def _empresas(db) -> list[tuple[str, str]]:
    """[(cnpj só dígitos, nome)] das empresas ativas do grupo — uma coluna por empresa na tela."""
    rows = await db.execute(
        text(
            "SELECT regexp_replace(cnpj, '\\D', '', 'g'), coalesce(nome_fantasia, razao_social) FROM empresas "
            "WHERE coalesce(status, 'ativa') IN ('ativa', 'ativo', 'active') ORDER BY is_principal DESC NULLS LAST, razao_social"
        )
    )
    return [(r[0], r[1]) for r in rows.all() if r[0]]


def _validar(valor: str, tipo: str) -> None:
    t = (tipo or "string").lower()
    try:
        if t in ("integer", "int"):
            int(valor)
        elif t in ("float", "decimal", "numeric"):
            Decimal(valor.replace(",", "."))
        elif t in ("boolean", "bool"):
            if valor.strip().lower() not in ("true", "false", "1", "0", "sim", "nao", "não"):
                raise ValueError
        elif t in ("json", "list"):
            json.loads(valor)
    except (ValueError, InvalidOperation, json.JSONDecodeError) as e:
        raise ValueError(f"'{valor}' não serve para um parâmetro do tipo {t}") from e


async def salvar(db, chave: str, empresa, valor, quem: str) -> dict:
    """Grava valor global (empresa vazia) ou por CNPJ; append no `historico` (quem, quando, de → para).
    Valor vazio por empresa REMOVE a exceção (volta ao global); vazio no global zera o valor."""
    await _ensure(db)
    chave = (chave or "").strip()
    e = parametros.so_digitos(empresa)
    row = (
        await db.execute(
            text(
                "SELECT valor, valor_por_empresa, coalesce(nullif(tipo::text,'string'), valor_type, 'string'), is_editavel, is_sensivel "
                "FROM system_configs WHERE chave = :c AND ativo"
            ),
            {"c": chave},
        )
    ).first()
    if row is None:
        raise ValueError(f"parâmetro {chave!r} não existe")
    if not row[3]:
        raise ValueError(f"parâmetro {chave!r} não é editável")
    empresas = dict(await _empresas(db))
    if e and e not in empresas:
        raise ValueError(f"CNPJ {e} não é empresa do grupo")
    novo = str(valor if valor is not None else "").strip()
    if novo:
        _validar(novo, row[2])
        if row[2] in ("float", "decimal", "numeric"):
            novo = novo.replace(",", ".")
    antigo = (row[1] or {}).get(e) if e else row[0]
    if (antigo or "") == novo:
        return {"ok": True, "message": f"{chave}: nada mudou."}
    mascara = bool(row[4])
    evento = {
        "quando": datetime.now(UTC).isoformat(timespec="seconds"),
        "quem": quem,
        "empresa": e or "global",
        "de": "***" if mascara and antigo else antigo,
        "para": "***" if mascara and novo else novo,
    }
    if e:
        sql = (
            "UPDATE system_configs SET valor_por_empresa = CASE WHEN :v = '' THEN valor_por_empresa - CAST(:e AS text) "
            "ELSE valor_por_empresa || jsonb_build_object(CAST(:e AS text), CAST(:v AS text)) END, "
        )
    else:
        sql = "UPDATE system_configs SET valor = nullif(:v, ''), "
    sql += (
        "historico = coalesce(historico, '[]'::jsonb) || jsonb_build_array(CAST(:h AS jsonb)), "
        "updated_at = now(), updated_by = :q WHERE chave = :c"
    )
    await db.execute(text(sql), {"v": novo, "e": e, "h": json.dumps(evento), "q": quem[:100], "c": chave})
    await db.commit()
    parametros.invalidar()
    alvo = empresas.get(e, "global") if e else "global"
    de = evento["de"] or "—"
    para = evento["para"] or ("— (volta ao global)" if e else "—")
    return {"ok": True, "message": f"{chave} ({alvo}): {de} → {para}. Registrado no histórico."}


async def telas(db, out: dict) -> None:
    from modules.operacional.controllers.redesign_data_controller import b, t

    await _ensure(db)
    await db.commit()
    emps = await _empresas(db)
    rows = (
        await db.execute(
            text(
                "SELECT chave, coalesce(descricao, ''), valor, coalesce(valor_por_empresa, '{}'::jsonb), coalesce(grupo, '(sem grupo)'), "
                "coalesce(nullif(tipo::text,'string'), valor_type, 'string'), coalesce(metadata->>'origem', ''), is_editavel, is_sensivel, "
                "jsonb_array_length(coalesce(historico, '[]'::jsonb)) FROM system_configs WHERE ativo ORDER BY 5, 1"
            )
        )
    ).all()
    opc_emp = [{"value": "", "label": "Global (todas as empresas)"}] + [
        {"value": c, "label": f"{n} · {c}"} for c, n in emps
    ]

    def _v(valor, sens):
        if valor is None or str(valor).strip() == "":
            return "—"
        return "********" if sens else str(valor)[:48]

    def _linha(r):
        chave, desc, valor, vpe, grupo, tipo, origem, edit, sens, nhist = r
        cells = [
            t(chave, 600, _ND),
            t(desc[:90] or "—", 400, "#64748B"),
            b(_v(valor, sens), "info" if valor not in (None, "") else "mut"),
        ]
        for c, _n in emps:
            cells.append(
                b(_v(vpe.get(c), sens), "ok") if vpe.get(c) not in (None, "") else t("= global", 400, "#94A3B8")
            )
        cells.append(
            t(f"{tipo} · {origem[:60] or '—'}" + (f" · {nhist} alteração(ões)" if nhist else ""), 400, "#64748B")
        )
        acoes = []
        if edit:
            acoes.append(
                {
                    "title": f"Editar {chave}",
                    "sub": desc[:160] or None,
                    "endpoint": f"/api/v1/redesign/action/parametro-salvar?chave={chave}",
                    "method": "POST",
                    "btnLabel": "Editar",
                    "submitLabel": "Salvar",
                    "btnStyle": "outline",
                    "confirm": f"Alterar o parâmetro {chave}? Fica registrado no histórico (quem, quando, de → para).",
                    "okMsg": "Parâmetro salvo. Recarregue a tela.",
                    "fields": [
                        {"key": "empresa", "label": "Vale para", "type": "select", "options": opc_emp, "value": ""},
                        {
                            "key": "valor",
                            "label": f"Valor ({tipo}) — vazio por empresa volta ao global",
                            "type": "text",
                            "value": "" if sens else (valor or ""),
                        },
                    ],
                }
            )
        return {"cells": cells, "actions": acoes, "filtro": grupo}

    grupos: dict[str, int] = {}
    for r in rows:
        grupos[r[4]] = grupos.get(r[4], 0) + 1
    n_emp = sum(1 for r in rows if r[3])
    out["parametros"] = {
        "title": "Parâmetros do sistema",
        "sub": (
            f"{len(rows)} parâmetro(s) em {len(grupos)} seções · {n_emp} com valor por empresa · "
            "regra de leitura: valor da empresa → global → padrão do código. Vazio = 'sem fonte, a definir'. "
            "Filtre pela seção no seletor."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Parâmetro, descrição ou origem…",
        "grid": " ".join(["1.5fr", "2.2fr", "0.9fr"] + ["0.9fr"] * len(emps) + ["1.8fr"]),
        "cols": ["Parâmetro", "Descrição", "Global"] + [n for _c, n in emps] + ["Tipo · origem"],
        "rows": [_linha(r) for r in rows],
        "panels": [
            {
                "title": "Seções (DGX: Configurações em 13 seções)",
                "rows": [{"left": g, "right": str(n)} for g, n in sorted(grupos.items())],
            }
        ],
    }
    out["parametro-editar"] = {
        "title": "Editar parâmetro",
        "sub": (
            "Escolha o parâmetro, para quem vale (global ou uma empresa do grupo) e o valor. "
            "Por empresa, valor vazio remove a exceção e volta ao global. Toda alteração fica no histórico."
        ),
        "cta": "Salvar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/parametro-salvar",
            "gated": True,
            "confirm": "Alterar um parâmetro do sistema muda o comportamento para todos. Confirma?",
            "okMsg": "Parâmetro salvo.",
        },
        "fields": [
            {
                "key": "chave",
                "label": "Parâmetro*",
                "type": "select",
                "span": "span 2",
                "options": [{"value": "", "label": "— escolha —"}]
                + [{"value": r[0], "label": f"{r[4]} · {r[0]} (global: {_v(r[2], r[8])})"} for r in rows if r[7]],
            },
            {
                "key": "empresa",
                "label": "Vale para",
                "type": "select",
                "span": "span 1",
                "options": opc_emp,
                "value": "",
            },
            {
                "key": "valor",
                "label": "Valor",
                "type": "text",
                "span": "span 1",
                "ph": "vazio por empresa = volta ao global",
            },
        ],
    }


router = APIRouter()


@router.post("/action/parametro-salvar")
async def _salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), chave: str | None = None, db=Depends(get_db)
) -> dict:
    """FORM/linha da tela: grava global ou por CNPJ com histórico. Só administração (mesma trava do módulo)."""
    from modules.operacional.controllers.redesign_data_controller import _is_admin_user

    if not _is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Parâmetros do sistema: só administração.")
    quem = (
        getattr(current_user, "email", None)
        or getattr(current_user, "name", None)
        or str(getattr(current_user, "id", ""))
    )
    try:
        return await salvar(db, chave or payload.get("chave"), payload.get("empresa"), payload.get("valor"), quem=quem)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
