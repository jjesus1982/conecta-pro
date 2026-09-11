"""Transferir de VERDADE: a conversa inteira no WhatsApp de quem tem competência (11/09/2026).

Decisão do Jordan, 11/09: *"quando disser que vai transferir pra mim, pra Pyetra, pro Gonzaga ou
pro Paiva que realmente transfira a conversa na íntegra, não apenas diga a quem está na conversa
que vai transferir, mas que transfira de fato, e cada um de acordo com sua competência"*.

O que existia antes: `transferir_conversa` atribuía a conversa a um time do Chatwoot e, só para
`comercial` e `suporte_tecnico`, mandava um briefing com as **3 últimas** falas. Para operacional,
administrativo, DP e RH não ia nada para ninguém — a conversa era "encaminhada ao time" e morria
numa caixa que ninguém abre. O funcionário do ponto, que desde 11/09 também tem essa ferramenta,
cairia exatamente nesse buraco.

Duas regras que este módulo carrega e que não podem virar duas cópias:

1. **Competência** (palavras do dono): operacional → Paiva e Gonzaga · DP e RH → Pyetra ·
   comercial e **demais demandas** → Jordan. Setor que não estiver no mapa cai no PADRÃO (Jordan),
   porque "demais demandas é comigo" é uma regra, não uma lista.
2. **Íntegra**: vai a conversa toda, em ordem, não as últimas três falas. Com teto — a maior
   conversa medida hoje tem 206 mil caracteres (154 mensagens), e despejar isso viraria 60
   mensagens no WhatsApp de alguém. Acima do teto vão as falas MAIS RECENTES e uma linha dizendo
   quantas ficaram de fora; é melhor dizer que cortou do que cortar calado.

⚠️ Os números aqui são os que o WhatsApp resolveu, não os do papel. Três dos quatro são contas de
Manaus anteriores ao nono dígito (`5592 9xxxx` → `559 2xxxx`): o `_resolver_lid` traduz telefone →
LID tentando com e sem o 9, e é ele quem entrega. Mandar para o número "certo no papel" já entregou
mensagem a terceiro (lição de 23/08, dez handoffs perdidos).
"""
from __future__ import annotations

import logging
import os
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

TZ = ZoneInfo("America/Manaus")

#: Cada pessoa uma vez só. `whatsapp` é o número do CADASTRO — quem traduz para o LID é o envio.
JORDAN = {"nome": "Jordan Jesus", "whatsapp": os.getenv("AGENT_HANDOFF_COMERCIAL_WHATSAPP", "+5592986465328")}
PYETRA = {"nome": "Pyetra Jesus", "whatsapp": os.getenv("AGENT_HANDOFF_DP_WHATSAPP", "+5592999822705")}
GONZAGA = {"nome": "Eliziel Gonzaga", "whatsapp": os.getenv("AGENT_HANDOFF_OPERACIONAL_WHATSAPP", "+5592984997784")}
PAIVA = {"nome": "Orlailson Paiva", "whatsapp": os.getenv("AGENT_HANDOFF_OPERACIONAL2_WHATSAPP", "+5592981386006")}
PEDRO = {"nome": "Pedro Rafael", "whatsapp": os.getenv("AGENT_HANDOFF_SUPORTE_WHATSAPP", "+5592992839530")}

#: setor → quem assume. Ordem dentro de `pessoas` é a ordem de envio.
RESPONSAVEIS: dict[str, dict] = {
    "comercial": {"label": "Vendas e Projetos", "pessoas": [JORDAN]},
    "suporte_tecnico": {"label": "Suporte Técnico", "pessoas": [PEDRO]},
    "operacional": {"label": "Operacional", "pessoas": [GONZAGA, PAIVA]},
    "dp": {"label": "Departamento Pessoal", "pessoas": [PYETRA]},
    "rh": {"label": "Recursos Humanos", "pessoas": [PYETRA]},
    "administrativo": {"label": "Administrativo", "pessoas": [JORDAN]},
}
#: "comercial e demais demandas é comigo, Jordan" — setor desconhecido NÃO fica sem dono.
PADRAO = "comercial"

#: Teto do despejo. 3.400 cabe folgado no limite de uma mensagem do WhatsApp (4.096).
PEDACO = 3400
MAX_PARTES = 6


def responsaveis(setor: str | None) -> tuple[str, list[dict]]:
    """(label do setor, pessoas que assumem). Nunca devolve lista vazia."""
    cfg = RESPONSAVEIS.get((setor or "").strip().lower()) or RESPONSAVEIS[PADRAO]
    return cfg["label"], list(cfg["pessoas"])


def _quebrar(linhas: list[str]) -> list[str]:
    """Agrupa linhas em pedaços de até PEDACO caracteres, sem partir uma fala no meio."""
    partes: list[str] = []
    atual: list[str] = []
    tam = 0
    for ln in linhas:
        if atual and tam + len(ln) + 1 > PEDACO:
            partes.append("\n".join(atual))
            atual, tam = [], 0
        atual.append(ln)
        tam += len(ln) + 1
    if atual:
        partes.append("\n".join(atual))
    return partes


async def transcricao(db, conversation_id: int, quem: str = "Cliente") -> list[str]:
    """A conversa INTEIRA, em ordem, pronta para o WhatsApp — uma lista de mensagens.

    `direction`: 'in' é quem escreveu, 'out' é o José Luís. 'drf'/'mem'/'trf' são rascunho,
    memória e marcador de transferência — não são fala de ninguém e ficam de fora.
    """
    from sqlalchemy import text as sql

    rows = (await db.execute(sql(
        "SELECT direction, content, created_at FROM cwi_message_log "
        "WHERE chatwoot_conversation_id = :c AND direction IN ('in','out') "
        "AND coalesce(content,'') <> '' ORDER BY created_at ASC"), {"c": conversation_id})).fetchall()
    if not rows:
        return []
    linhas = [
        f"[{d.astimezone(TZ).strftime('%d/%m %H:%M')}] *{quem if dir_ == 'in' else 'José Luís'}:* "
        f"{str(txt).strip()}"
        for dir_, txt, d in rows
    ]
    partes = _quebrar(linhas)
    if len(partes) <= MAX_PARTES:
        return partes
    # Estourou o teto: ficam as falas MAIS RECENTES, e a primeira parte diz o que ficou de fora.
    cortadas = partes[: len(partes) - MAX_PARTES]
    faltam = sum(p.count("\n") + 1 for p in cortadas)
    mantidas = partes[len(partes) - MAX_PARTES:]
    mantidas[0] = f"_(conversa longa — as {faltam} falas anteriores ficaram no sistema)_\n" + mantidas[0]
    return mantidas


def cabecalho(label: str, quem_e_nome: str, telefone: str | None, contexto: list[str], motivo: str = "") -> str:
    """Primeira mensagem: quem, de onde, por quê — e o telefone para responder."""
    L = [
        f"🤝 *TRANSFERÊNCIA — {label}*",
        "_O José Luís passou este atendimento para você._",
        "",
        f"👤 *{quem_e_nome}*",
        f"📱 WhatsApp: *{telefone or '—'}*",
    ]
    L += [f"• {c}" for c in contexto if c]
    if motivo:
        L += ["", f"📌 *Motivo:* {motivo}"]
    L += ["", "👇 A conversa na íntegra, logo abaixo. Fale com a pessoa no número acima."]
    return "\n".join(L)


def demo() -> None:
    """Checagem mínima: competência, fallback e o teto da íntegra."""
    assert [p["nome"] for p in responsaveis("operacional")[1]] == ["Eliziel Gonzaga", "Orlailson Paiva"]
    assert responsaveis("dp")[1] == responsaveis("rh")[1] == [PYETRA]
    assert responsaveis("comercial")[1] == [JORDAN]
    # setor que ninguém previu não pode ficar sem dono — "demais demandas é comigo"
    assert responsaveis("juridico")[1] == [JORDAN]
    assert responsaveis(None)[1] == [JORDAN]
    # quebra respeita o teto e não perde linha
    linhas = [f"linha {i} " + "x" * 200 for i in range(40)]
    partes = _quebrar(linhas)
    assert all(len(p) <= PEDACO for p in partes), [len(p) for p in partes]
    assert sum(p.count("\n") + 1 for p in partes) == len(linhas)
    print(f"OK transferencia: {len(RESPONSAVEIS)} setores, {len(partes)} pedaços para 40 falas")


if __name__ == "__main__":
    demo()
