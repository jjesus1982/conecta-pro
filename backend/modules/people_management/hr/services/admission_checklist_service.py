"""Checklist de admissão do colaborador (pós-aprovação do candidato).

Cada etapa entre "aprovado" e "trabalhando legalmente" vira um item com status
(pendente/ok/nao_aplicavel). Itens `gate_humano=True` NÃO podem ser marcados
automaticamente — exigem confirmação humana (ex.: transmissão do eSocial S-2200,
laudo "apto" do ASO), na mesma lógica do "irreversível/legal = gate".

O que o sistema JÁ tem (docs, PIX, contrato, salário-família) nasce 'ok'; o resto
'pendente' pro RH completar sem esquecer nada.
"""

from typing import Any

# ordem, key, label, categoria, obrigatório por lei, precisa de confirmação humana (gate)
ITENS: list[dict[str, Any]] = [
    {"ordem": 1, "key": "documentos_pessoais", "label": "Documentos pessoais (RG, CPF, comprovante de endereço)",
     "categoria": "Documentação", "obrigatorio_legal": True, "gate_humano": False},
    {"ordem": 2, "key": "foto_3x4", "label": "Foto 3x4",
     "categoria": "Documentação", "obrigatorio_legal": False, "gate_humano": False},
    {"ordem": 3, "key": "ctps_pis", "label": "CTPS / PIS-PASEP",
     "categoria": "Documentação", "obrigatorio_legal": True, "gate_humano": False},
    {"ordem": 4, "key": "aso_admissional", "label": "Exame admissional (ASO) — laudo APTO",
     "categoria": "Saúde ocupacional", "obrigatorio_legal": True, "gate_humano": True},
    {"ordem": 5, "key": "esocial_s2200", "label": "eSocial S-2200 (admissão) transmitido",
     "categoria": "eSocial", "obrigatorio_legal": True, "gate_humano": True},
    {"ordem": 6, "key": "contrato_assinado", "label": "Contrato de trabalho assinado no portal",
     "categoria": "Contrato", "obrigatorio_legal": True, "gate_humano": False},
    {"ordem": 7, "key": "contrato_experiencia", "label": "Contrato de experiência (45+45) definido",
     "categoria": "Contrato", "obrigatorio_legal": False, "gate_humano": False},
    {"ordem": 8, "key": "vale_transporte", "label": "Opção de vale-transporte declarada (aceite/recusa)",
     "categoria": "Benefícios", "obrigatorio_legal": False, "gate_humano": False},
    {"ordem": 9, "key": "dados_bancarios", "label": "Chave PIX / dados bancários",
     "categoria": "Financeiro", "obrigatorio_legal": True, "gate_humano": False},
    {"ordem": 10, "key": "salario_familia", "label": "Salário-família avaliado",
     "categoria": "Financeiro", "obrigatorio_legal": False, "gate_humano": False},
    {"ordem": 11, "key": "epi_uniforme", "label": "EPI / uniforme entregue",
     "categoria": "Operacional", "obrigatorio_legal": False, "gate_humano": False},
    {"ordem": 12, "key": "integracao", "label": "Integração / treinamento admissional",
     "categoria": "Operacional", "obrigatorio_legal": False, "gate_humano": False},
]

# Itens que a lei exige ANTES do início do trabalho (bloqueiam a legalidade da admissão).
BLOQUEIAM_INICIO = {"aso_admissional", "esocial_s2200"}


def itens_auto_ok(ctx: dict[str, Any]) -> set[str]:
    """Dado o contexto do colaborador, quais itens já nascem 'ok'.
    ctx: tem_docs, tem_pis, tem_pix, tem_contrato, salfam_avaliado (bools)."""
    ok: set[str] = set()
    if ctx.get("tem_docs"):
        ok.add("documentos_pessoais")
    if ctx.get("tem_pis"):
        ok.add("ctps_pis")
    if ctx.get("tem_pix"):
        ok.add("dados_bancarios")
    if ctx.get("tem_contrato"):
        ok.add("contrato_assinado")
    if ctx.get("salfam_avaliado"):
        ok.add("salario_familia")
    if ctx.get("contrato_experiencia"):
        ok.add("contrato_experiencia")
    return ok


def montar_itens(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Lista de itens já com o status inicial resolvido (ok/pendente)."""
    auto = itens_auto_ok(ctx)
    out = []
    for it in ITENS:
        out.append({**it, "status": "ok" if it["key"] in auto else "pendente"})
    return out


def resumo(itens: list[dict[str, Any]]) -> dict[str, Any]:
    """Contadores + se ainda há bloqueio legal para o início do trabalho."""
    def _k(i: dict[str, Any]) -> str:
        return i.get("item_key") or i.get("key") or ""
    total = len(itens)
    ok = sum(1 for i in itens if i.get("status") == "ok")
    obrig_pend = [_k(i) for i in itens if i.get("obrigatorio_legal") and i.get("status") != "ok"]
    bloqueios = [_k(i) for i in itens if _k(i) in BLOQUEIAM_INICIO and i.get("status") != "ok"]
    return {
        "total": total, "concluidos": ok, "pendentes": total - ok,
        "obrigatorios_pendentes": obrig_pend,
        "pode_iniciar": len(bloqueios) == 0,
        "bloqueios_legais": bloqueios,
    }
