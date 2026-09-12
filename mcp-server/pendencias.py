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

import re
from datetime import date, datetime
from typing import Any

SEVERIDADES = ("critica", "alta", "media", "baixa")
_PESO = {s: i for i, s in enumerate(SEVERIDADES)}


# ⚠️ "R$ 255.400.06" — dois pontos decimais, num alerta CRÍTICO. Achado pelo Cowork em
# 12/09/2026. Procurei a origem da string em `backend/` e NÃO ACHEI: ela não está no código
# fonte, então nasce em rota externa ou é montada em runtime. Normalizo AQUI, que é a camada
# que o agente lê, e registro que a causa continua não localizada — consertar o sintoma sem
# dizer que é sintoma seria esconder o defeito.
_MOEDA_TORTA = re.compile(r"R\$\s*([\d.]+)\.(\d{2})\b")


def _moeda_legivel(texto: str) -> str:
    """Arruma milhar/decimal em valor com dois pontos decimais. Não inventa número."""
    def _fix(m: "re.Match") -> str:
        inteiro = m.group(1).replace(".", "")
        try:
            n = float(f"{inteiro}.{m.group(2)}")
        except ValueError:
            return m.group(0)
        return "R$ " + f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return _MOEDA_TORTA.sub(_fix, texto or "")


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
    # ⚠️ O id inclui o TÍTULO, não só a entidade. O Cowork achou
    # `fiscal:conecta_eletronica` ONZE vezes — ISS, IRRF, FGTS, INSS de duas competências,
    # todos com o mesmo id porque a entidade era a empresa. Sem id único não dá para marcar
    # uma pendência como resolvida sem ambiguidade, e sem isso a lista nunca encolhe.
    import hashlib

    semente = f"{dominio}|{entidade_id or ''}|{titulo}"
    return {
        "id": ident or (f"{dominio}:{(entidade_id or 'x')[:28]}:"
                        + hashlib.sha1(semente.encode()).hexdigest()[:8]),
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
            titulo=_moeda_legivel(
                f"{a.get('tipo') or 'Obrigação'} — {a.get('descricao') or ''}".strip(" —")),
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
    # ⭐ UM achado sistêmico não são 35 achados. Validação do Cowork (12/09/2026): 35 das
    # 43 críticas eram "FULANO SEM ASO no cadastro", uma linha por colaborador — incluindo
    # `COLABORADOR TESTE HOMOLOGACAO`. Isso não é 35 problemas: é UM (o campo nunca foi
    # populado) fatiado por pessoa.
    #
    # "Lista onde 81% das críticas são o mesmo item treina o leitor a rolar a página" — e é
    # o mesmo raciocínio que eu escrevi para não inflar a categoria IRREVERSIVEL. Agrupa, e
    # os nomes vão no DETALHE, que é onde servem para agir.
    if sem_aso:
        nomes = [str(c.get("nome") or c.get("colaborador") or "?") for c in sem_aso]
        i = item(
            dominio="sst",
            titulo=(f"{len(nomes)} colaboradores SEM ASO no cadastro"
                    if len(nomes) > 1 else f"{nomes[0]} SEM ASO no cadastro"),
            severidade="critica", prazo=None, dias=None,
            # ⚠️ o número vem do `len`, não de um retrato. A 1ª versão dizia "não 35
            # infrações distintas" porque 35 era o que eu tinha visto no dia — e quando
            # virou 33 o texto passou a contradizer o próprio `quantidade` ao lado dele.
            impacto=(f"admissão sem ASO é infração; o risco de NÃO olhar é maior que o de "
                     f"olhar. Quantidade alta costuma ser campo nunca populado, não "
                     f"{len(nomes)} infrações distintas — confirme antes de tratar um a um"),
            acao=("providenciar ASO admissional — em LOTE se o campo nunca foi preenchido"
                  if len(nomes) > 1 else "providenciar ASO admissional"),
            tool="funcionarios_sem_aso", ident="sst:sem_aso")
        i["quantidade"] = len(nomes)
        i["colaboradores"] = nomes[:60]
        fora.append(i)
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

    ⚠️ Item SEM prazo fica DEPOIS dos com prazo, dentro da mesma severidade. A versão
    anterior ordenava ausência como prazo ZERO e o Cowork mostrou o resultado: o item de
    eSocial vencendo em 3 DIAS aparecia depois de 35 linhas de ASO sem data. Crítico sem
    data continua crítico — mas quem tem relógio correndo vai na frente, porque é sobre ele
    que se decide hoje.
    """
    piso = _PESO.get(severidade_minima, 2)
    fora = [i for i in itens if _PESO.get(i["severidade"], 3) <= piso]
    fora = [i for i in fora
            if i["dias_restantes"] is None or i["dias_restantes"] <= horizonte_dias]
    return sorted(fora, key=lambda i: (_PESO.get(i["severidade"], 3),
                                       0 if i["dias_restantes"] is not None else 1,
                                       i["dias_restantes"] if i["dias_restantes"] is not None
                                       else 0))
