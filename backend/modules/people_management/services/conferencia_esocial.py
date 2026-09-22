"""A lista de empregados do eSocial bate com a nossa? — perguntado ao governo.

Origem: 22/09/2026. O Jordan, depois de pagar o adiantamento: «quando formos gerar a
segunda parcela de 60% o nosso sistema tem que ir no eSocial, conferir naquele dia a lista
de empregados, pois tivemos novas contratações, e isso tem que ser permanente».

Isso importa porque já mordeu: o GEILSON estava `ativo` no nosso cadastro e o eSocial
tinha um S-2299 dele de 30/06/2026 com motivo 11 — transferência para a Conecta Mais
Patrimonial, sem rescisão. Ninguém no sistema sabia. Sem esta conferência, a diferença só
aparece quando o contador reclama ou quando alguém não recebe.

⚠️ DOIS LIMITES REAIS, medidos, e a tela precisa dizer os dois:

1. **A consulta é por CPF, sempre.** Testado em 22/09 contra o governo: omitir `cpfTrab`
   devolve HTTP 500. Então o eSocial CONFIRMA ou DESMENTE quem já está no nosso cadastro,
   e NÃO revela uma admissão que exista só lá. Quem entrou e não foi cadastrado aqui é
   invisível para esta conferência — a fonte disso é o processo de admissão do DP.

2. **O governo bloqueia consulta nos dias 1 a 7 de cada mês** (`dia_bloqueado`). E o saldo
   de 60% cai no 5º dia útil — 07/10/2026, o ÚLTIMO dia bloqueado. Ou seja: no dia de
   gerar o saldo, não dá para perguntar nada de novo. Por isso esta função NUNCA finge
   ter consultado hoje: devolve sempre a DATA da última leitura, e quem usa o resultado
   tem de mostrar essa data ao lado do veredito. Espelho velho apresentado como fresco é
   pior que espelho nenhum.

O beat `esocial-espelho-sync` (09:10, diário) mantém o espelho o mais novo possível nos
dias em que o governo deixa. Esta função só LÊ o espelho — não gasta acesso do orçamento
de 10/dia.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text

#: Motivos de desligamento que NÃO encerram o vínculo com o grupo — transferência entre
#: empresas do mesmo grupo (tabela 19 do eSocial). O Geilson saiu da Eletrônica para a
#: Patrimonial com motivo 11: para a folha ele continua sendo nosso, noutro CNPJ.
_MOTIVOS_TRANSFERENCIA = {"10", "11"}

#: O governo recusa consulta entre os dias 1 e 7 (ver esocial_eventos_client.dia_bloqueado).
_DIAS_BLOQUEADOS = set(range(1, 8))


async def conferir_lista_esocial(db: Any, *, hoje: date | None = None) -> dict[str, Any]:
    """Compara a nossa lista de ATIVOS com o que o eSocial recebeu, pessoa a pessoa."""
    hoje = hoje or date.today()

    ultima = (await db.execute(text("SELECT max(baixado_em)::date FROM esocial_eventos_espelho"))).scalar()

    # Desligamento (S-2299) mais recente de cada CPF, com o motivo — o motivo decide se o
    # vínculo acabou ou só mudou de CNPJ dentro do grupo.
    deslig = {
        r["cpf"]: {"quando": r["quando"], "motivo": r["motivo"]}
        for r in (
            await db.execute(
                text(
                    "SELECT DISTINCT ON (cpf_trabalhador) cpf_trabalhador AS cpf, dt_evento AS quando, "
                    "       (regexp_match(xml_completo, '<[^>]*mtvDeslig>([^<]+)<'))[1] AS motivo "
                    "  FROM esocial_eventos_espelho "
                    " WHERE tipo = 'S-2299' AND download_status = 'ok' "
                    " ORDER BY cpf_trabalhador, dt_evento DESC NULLS LAST"
                )
            )
        )
        .mappings()
        .all()
    }

    nossos = [
        dict(r)
        for r in (
            await db.execute(
                text(
                    "SELECT e.nome, regexp_replace(coalesce(e.cpf,''),'\\D','','g') AS cpf, e.status "
                    "  FROM employees e "
                    " WHERE e.status = 'ativo' AND coalesce(e.is_homologacao,false) = false "
                    " ORDER BY e.nome"
                )
            )
        )
        .mappings()
        .all()
    ]

    vistos = {
        r["cpf"]
        for r in (await db.execute(text("SELECT DISTINCT cpf_trabalhador AS cpf FROM esocial_eventos_espelho")))
        .mappings()
        .all()
    }

    desligados, transferidos, sem_cpf, nunca_consultados = [], [], [], []
    for p in nossos:
        if not p["cpf"]:
            sem_cpf.append(p["nome"])
            continue
        d = deslig.get(p["cpf"])
        if d:
            item = {"nome": p["nome"], "quando": str(d["quando"] or "?"), "motivo": d["motivo"] or "?"}
            (transferidos if (d["motivo"] or "") in _MOTIVOS_TRANSFERENCIA else desligados).append(item)
        elif p["cpf"] not in vistos:
            nunca_consultados.append(p["nome"])

    bloqueado = hoje.day in _DIAS_BLOQUEADOS
    return {
        "ok": True,
        "ativos_no_cadastro": len(nossos),
        # ATIVO aqui e DESLIGADO no governo — a folha pagaria quem não é mais empregado.
        "desligados_no_esocial": desligados,
        # Transferência entre empresas do grupo: continua sendo nosso, noutro CNPJ.
        "transferidos_no_grupo": transferidos,
        "sem_cpf_no_cadastro": sem_cpf,
        # O espelho nunca alcançou esta pessoa — ausência de evento NÃO é prova de nada.
        "nunca_consultados": nunca_consultados,
        "espelho_de": str(ultima) if ultima else None,
        "consulta_bloqueada_hoje": bloqueado,
        "limite": (
            "A consulta do eSocial é por CPF: ela confirma ou desmente quem já está no "
            "cadastro, e NÃO revela admissão que exista só no governo."
        ),
    }


def resumo_em_texto(r: dict[str, Any]) -> str:
    """Uma linha para colar na resposta da tela — sempre com a DATA do espelho."""
    if not r.get("ok"):
        return ""
    partes = []
    if r["desligados_no_esocial"]:
        partes.append(
            "🚨 DESLIGADO no eSocial e ATIVO aqui: "
            + "; ".join(
                f"{x['nome']} (desde {x['quando']}, motivo {x['motivo']})" for x in r["desligados_no_esocial"][:5]
            )
        )
    if r["transferidos_no_grupo"]:
        partes.append(
            "↔ transferido para outra empresa do grupo: "
            + "; ".join(f"{x['nome']} ({x['quando']})" for x in r["transferidos_no_grupo"][:5])
        )
    if r["sem_cpf_no_cadastro"]:
        partes.append(f"{len(r['sem_cpf_no_cadastro'])} sem CPF no cadastro (não dá para conferir)")
    if r["nunca_consultados"]:
        partes.append(f"{len(r['nunca_consultados'])} que o espelho ainda não alcançou")
    freq = f"espelho de {r['espelho_de']}" if r["espelho_de"] else "espelho VAZIO"
    if r["consulta_bloqueada_hoje"]:
        freq += " · o governo BLOQUEIA consulta nos dias 1–7, então hoje não dá para atualizar"
    corpo = " · ".join(partes) if partes else "nenhuma divergência"
    return f"eSocial ({freq}): {corpo}."
