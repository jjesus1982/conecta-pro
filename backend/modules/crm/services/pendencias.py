"""Agregador de pendências acionáveis — Bloco 8 do prompt de 11/09/2026.

O assistente só existe quando o Jordan abre uma sessão. Certidão vencendo, ASO estourando,
contrato parado em `draft` há 40 dias, obrigação fiscal a vencer, cotação expirando — nada
disso chama ninguém. As peças existiam soltas (`alertas_obrigacoes`, `status_certidoes`,
`asos_vencendo`, `negociacoes_pendentes`…) e faltava o agregador.

⭐ SEVERIDADE COM CRITÉRIO ESCRITO, não com feeling. O Bloco 8 exige o critério documentado,
e ele é este:

    critica  — tem PRAZO LEGAL vencido/vencendo, ou TRAVA FATURAMENTO. Certidão vencida
               impede emitir NFS-e e participar de licitação; ASO vencido é exposição
               trabalhista com o funcionário em campo HOJE.
    alta     — prazo legal a vencer em até 7 dias, ou dinheiro parado que já podia estar
               entrando.
    media    — prazo em até 30 dias, ou trabalho comercial esfriando.
    baixa    — informativo; serve para planejar a semana, não para hoje.

⚠️ O QUE ESTE MÓDULO NÃO FAZ: não corrige nada. Cada item traz `tool_para_agir` e quem
aciona é o humano — ou uma tool que, por sua vez, tem a parede dela. Operacional em especial
é curado à mão pelo dono: divergência aqui vira LINHA DE RELATÓRIO, nunca correção.

⚠️ Peça que falha NÃO derruba o agregador e NÃO desaparece: entra como item de severidade
`alta` dizendo que a fonte não respondeu. Agregador que engole erro de fonte mostra uma
lista curta e tranquila — e a lista curta é lida como "está tudo bem".
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

SEVERIDADES = ("critica", "alta", "media", "baixa")
_PESO = {s: i for i, s in enumerate(SEVERIDADES)}


def _dias_ate(valor: Any) -> int | None:
    """Dias até a data, aceitando ISO, DD/MM/AAAA ou já-um-número."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float)):
        return int(valor)
    t = str(valor).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return (datetime.strptime(t[:10], fmt).date() - date.today()).days
        except ValueError:
            continue
    return None


def _sev_por_prazo(dias: int | None, *, legal: bool) -> str:
    """Prazo legal pesa mais que prazo comercial — é o critério, não uma preferência."""
    if dias is None:
        return "media"
    if dias < 0:
        return "critica"
    if legal:
        return "critica" if dias <= 3 else ("alta" if dias <= 7 else "media")
    return "alta" if dias <= 7 else ("media" if dias <= 30 else "baixa")


def item(*, dominio: str, titulo: str, severidade: str, prazo: str | None,
         dias: int | None, impacto: str, acao: str, tool: str,
         entidade_id: str | None = None, ident: str | None = None) -> dict:
    return {
        "id": ident or f"{dominio}:{(entidade_id or titulo)[:60]}",
        "dominio": dominio, "titulo": titulo, "severidade": severidade,
        "prazo": prazo, "dias_restantes": dias,
        "impacto": impacto, "acao_sugerida": acao,
        "tool_para_agir": tool, "entidade_id": entidade_id,
    }


def de_obrigacoes(alertas: list[dict]) -> list[dict]:
    fora = []
    for a in alertas or []:
        dias = _dias_ate(a.get("dias_restantes"))
        fora.append(item(
            dominio="fiscal",
            titulo=f"{a.get('tipo') or 'Obrigação'} — {a.get('descricao') or ''}".strip(" —"),
            severidade=_sev_por_prazo(dias, legal=True),
            prazo=a.get("vencimento") or a.get("prazo"), dias=dias,
            impacto="obrigação com prazo legal; atraso gera multa e pode travar CND",
            acao="conferir no Onvio/eCAC e transmitir", tool="alertas_obrigacoes",
            entidade_id=a.get("empresa_slug") or a.get("empresa")))
    return fora


def de_certidoes(certidoes: list[dict]) -> list[dict]:
    fora = []
    for c in certidoes or []:
        dias = _dias_ate(c.get("validade"))
        vencida = dias is not None and dias < 0
        fora.append(item(
            dominio="fiscal",
            titulo=f"{c.get('tipo') or 'Certidão'} "
                   + ("VENCIDA" if vencida else f"vence em {dias} dias" if dias is not None
                      else f"situação: {c.get('situacao')}"),
            severidade="critica" if vencida else _sev_por_prazo(dias, legal=True),
            prazo=c.get("validade"), dias=dias,
            impacto="bloqueia emissão de NFS-e e participação em licitação",
            acao="renovar no eCAC / portal do órgão", tool="status_certidoes",
            entidade_id=c.get("tipo")))
    return fora


def de_aso(asos: list[dict], sem_aso: list[dict]) -> list[dict]:
    fora = []
    for a in asos or []:
        dias = _dias_ate(a.get("vencimento") or a.get("validade") or a.get("dias_restantes"))
        fora.append(item(
            dominio="sst",
            titulo=f"ASO de {a.get('nome') or a.get('colaborador') or '?'} "
                   + ("VENCIDO" if (dias or 0) < 0 else f"vence em {dias} dias"),
            severidade="critica" if (dias is not None and dias < 0)
                       else _sev_por_prazo(dias, legal=True),
            prazo=a.get("vencimento") or a.get("validade"), dias=dias,
            impacto="funcionário em campo sem ASO válido é exposição trabalhista e de SST",
            acao="agendar exame periódico", tool="asos_vencendo",
            entidade_id=a.get("employee_id") or a.get("id")))
    for c in sem_aso or []:
        fora.append(item(
            dominio="sst",
            titulo=f"{c.get('nome') or '?'} SEM ASO no cadastro",
            severidade="critica", prazo=None, dias=None,
            impacto="admissão sem ASO é infração; o risco de NÃO olhar é maior que o de olhar",
            acao="providenciar ASO admissional", tool="funcionarios_sem_aso",
            entidade_id=c.get("employee_id") or c.get("id")))
    return fora


def de_comercial(negociacoes: list[dict], frios: list[dict]) -> list[dict]:
    fora = []
    for n in negociacoes or []:
        dias = n.get("dias")
        fora.append(item(
            dominio="comercial",
            titulo=f"Proposta {n.get('proposta')} para {n.get('cliente_nome')} "
                   f"sem resposta há {dias} dias",
            severidade="alta" if (dias or 0) >= 15 else "media",
            prazo=None, dias=None,
            impacto="proposta esfriando; receita que já podia estar contratada",
            acao="ligar para o cliente antes de reenviar", tool="negociacoes_pendentes",
            entidade_id=n.get("proposta")))
    for f in frios or []:
        fora.append(item(
            dominio="comercial", titulo=f"Lead frio: {f.get('nome') or f.get('cliente')}",
            severidade="baixa", prazo=None, dias=None,
            impacto="lead sem toque; perde-se por silêncio, não por preço",
            acao="reativar ou arquivar", tool="leads_frios",
            entidade_id=f.get("id")))
    return fora


def de_substituicoes(subs: list[dict]) -> list[dict]:
    # ⚠️ Operacional é READ-ONLY para o agente. Isto é RELATÓRIO.
    return [item(
        dominio="operacional",
        titulo=f"Substituição pendente no posto {s.get('posto') or '?'}",
        severidade="alta", prazo=s.get("data"), dias=_dias_ate(s.get("data")),
        impacto="posto pode ficar descoberto — e escala é curada à mão pelo dono",
        acao="RELATÓRIO: leve ao Jordan; não altere escala por conta própria",
        tool="substituicoes_pendentes", entidade_id=s.get("id")) for s in subs or []]


def de_cotacoes(propostas: list[dict]) -> list[dict]:
    fora = []
    for p in propostas or []:
        dias = _dias_ate(p.get("validade_cotacao"))
        fora.append(item(
            dominio="comercial",
            titulo=f"Cotação da {p.get('numero')} "
                   + ("VENCIDA" if (dias or 0) < 0 else f"vence em {dias} dias"),
            severidade="critica" if (dias is not None and dias < 0) else "alta",
            prazo=p.get("validade_cotacao"), dias=dias,
            impacto="cotação vencida BLOQUEIA o envio da proposta (COTACAO_VENCIDA)",
            acao="pedir nova cotação ao fornecedor", tool="procedencia_da_proposta",
            entidade_id=p.get("numero")))
    return fora


def fonte_falhou(dominio: str, nome: str, erro: str) -> dict:
    return item(
        dominio=dominio, titulo=f"FONTE INDISPONÍVEL: {nome}", severidade="alta",
        prazo=None, dias=None,
        impacto=f"não consegui olhar esta fonte ({erro[:70]}) — pode haver pendência "
                f"invisível aqui",
        acao="rodar a tool direto para ver o erro completo", tool=nome)


def ordenar(itens: list[dict], severidade_minima: str = "media",
            horizonte_dias: int = 30) -> list[dict]:
    """Mais grave primeiro; dentro da mesma severidade, o prazo mais curto na frente.

    ⚠️ Item SEM prazo não vai para o fim da fila por isso: ASO ausente não tem data e é
    crítico. Ausência de prazo ordena como prazo ZERO dentro da severidade dele — quem não
    tem data é porque já estourou, não porque pode esperar.
    """
    piso = _PESO.get(severidade_minima, 2)
    fora = [i for i in itens if _PESO.get(i["severidade"], 3) <= piso]
    fora = [i for i in fora
            if i["dias_restantes"] is None or i["dias_restantes"] <= horizonte_dias]
    return sorted(fora, key=lambda i: (_PESO.get(i["severidade"], 3),
                                       i["dias_restantes"] if i["dias_restantes"] is not None
                                       else 0))
