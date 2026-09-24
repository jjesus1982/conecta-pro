"""Grupos do WhatsApp: observar, absorver e — só quando falta dado — falar.

Por que existe (23/09/2026). O Jordan pôs o José Luís em três grupos (Gestão, OPERACIONAL,
Escritório) e pediu que ele ficasse calado, aprendendo o tom, para depois virar ponto de apoio
do Orlailson Paiva, que está sobrecarregado.

⭐ A MEDIÇÃO QUE MUDOU O PLANO. O agente disse a ele "eu literalmente não recebo" mensagem de
grupo. É verdade, mas não pelo motivo que ele supôs. Medi o caminho elo por elo com uma
mensagem real no grupo OPERACIONAL às 22:59 de 23/09:

    Chatwoot recebeu:  event=groups.activity · jid=120363285473431324@g.us
                       unreadCount=1 · lastMessageAt=1790218737143

Sem texto, sem autor — um CONTADOR. Quem transforma mensagem em contador é o `baileys-api`
(`connection.ts:812`, `if (!this.groupsEnabled)`), e quem manda `groupsEnabled: false` é o
Chatwoot, porque `BAILEYS_WHATSAPP_GROUPS_ENABLED` não está definida (o default do Ruby é
`'false'`; o default da API do Baileys é `true`). Ou seja: a capacidade "captura de grupo",
que a especificação chamava de "o principal, precisa que desenvolvam", é UMA VARIÁVEL.

⚠️ E é exatamente por isso que este arquivo vem ANTES de ligar a variável. Com a chave ligada
e sem esta parede, a primeira mensagem do grupo Gestão cairia no agente, que responde por
padrão — o oposto do que o dono pediu. O próprio agente escreveu a régua:
**"silêncio tem que ser regra técnica, não minha boa vontade."**

A parede mora no WEBHOOK, antes do enfileiramento. Não é instrução de prompt, não é `foco` de
papel, não é julgamento do modelo: em modo `observar` o agente não é NEM CHAMADO. Prompt se
desobedece; caminho que não executa, não.
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Sufixo de JID de grupo no WhatsApp. Broadcast e newsletter têm outros e não entram aqui.
SUFIXO_GRUPO = "@g.us"

#: Modos. `observar` = lê e NUNCA responde. `falar` = lê e pode falar quando falta dado.
#: `off` = ignora por completo (nem absorve) — é o default de quem não está cadastrado, e é o
#: que mantém o River Park fora por decisão do dono.
MODOS = ("observar", "falar", "off")


def e_grupo(identificador: str | None) -> bool:
    """O remetente é um GRUPO? Decidido pelo JID, não pelo nome."""
    return bool(identificador) and str(identificador).strip().endswith(SUFIXO_GRUPO)


def jid_do_payload(data: dict) -> str | None:
    """Extrai o JID do grupo do payload do Chatwoot, olhando os dois lugares possíveis.

    ⚠️ Os dois: `sender.identifier` e `conversation.meta.sender.identifier`. O webhook já
    fazia isso para telefone e nome porque o Chatwoot manda um ou o outro dependendo do
    evento — aqui vale a mesma lição, e descobrir isso de novo custaria o mesmo dia.
    """
    for fonte in (data.get("sender") or {},
                  ((data.get("conversation") or {}).get("meta") or {}).get("sender") or {}):
        ident = fonte.get("identifier") or fonte.get("phone_number")
        if e_grupo(ident):
            return str(ident).strip()
    return None


def autor_do_payload(data: dict) -> tuple[str | None, str | None]:
    """(telefone, nome) de QUEM FALOU no grupo — não do grupo.

    ⚠️ Em mensagem de grupo o Chatwoot põe o grupo em `sender` e o autor em outro lugar. Sem
    isto, absorver o grupo daria "quem disse" = nome do grupo, e todo aprendizado de tom sairia
    atribuído ao grupo em vez de à pessoa — inútil para saber como a CASA fala.
    """
    cand = (data.get("sender") or {})
    # o fazer-ai põe o autor em `additional_attributes` quando a conversa é de grupo
    extra = cand.get("additional_attributes") or {}
    fone = extra.get("participant") or extra.get("author") or data.get("participant")
    nome = extra.get("participant_name") or extra.get("author_name")
    if not fone:
        # fallback: o conteúdo às vezes vem prefixado com o autor pelo próprio provedor
        m = re.match(r"^\+?(\d{10,15})\s*[:\-]\s*", str(data.get("content") or ""))
        if m:
            fone = m.group(1)
    return (str(fone) if fone else None), (str(nome) if nome else None)


async def config_do_grupo(db: AsyncSession, jid: str) -> dict | None:
    """A linha de `wa_grupos`, ou `None` para grupo não cadastrado.

    ⚠️ Não cadastrado = `None` = IGNORA. Fail-closed de propósito: grupo novo em que alguém
    adicione este número não começa a ser absorvido sozinho. Absorver conversa de terceiro sem
    decisão registrada é o oposto do que o item 7 da especificação pede.
    """
    r = (await db.execute(text(
        "SELECT jid, nome, modo, foco, midia_ok, max_falas_dia, retencao_dias "
        "  FROM wa_grupos WHERE jid = :j"), {"j": jid})).mappings().first()
    return dict(r) if r else None


async def absorver(db: AsyncSession, *, jid: str, conteudo: str | None,
                   chatwoot_message_id: int | None, autor_fone: str | None,
                   autor_nome: str | None, identidade=None) -> bool:
    """Grava a mensagem do grupo. Devolve True se gravou.

    A classificação nasce em `tom` e só muda por decisão de um classificador — ver
    `classificar`. O default é o mais barato de reverter: rotular como dado comercial o que é
    conversa enche a ficha do cliente de ruído, e ruído em ficha ninguém tira depois.
    """
    if not conteudo or not str(conteudo).strip():
        return False
    classe = classificar(conteudo)
    try:
        await db.execute(text(
            "INSERT INTO wa_grupo_mensagens "
            "  (grupo_jid, chatwoot_message_id, autor_fone, autor_nome, autor_employee_id, "
            "   autor_tipo, conteudo, classificacao, relevante) "
            "VALUES (:j, :mid, :af, :an, CAST(:aid AS uuid), :at, :c, :cl, :rel) "
            "ON CONFLICT (chatwoot_message_id) WHERE chatwoot_message_id IS NOT NULL "
            "DO NOTHING"),
            {"j": jid, "mid": chatwoot_message_id, "af": autor_fone,
             "an": (getattr(identidade, "nome", None) or autor_nome),
             "aid": getattr(identidade, "employee_id", None),
             "at": getattr(identidade, "tipo", None),
             "c": str(conteudo)[:8000], "cl": classe, "rel": classe != "tom"})
        await db.commit()
        return True
    except Exception as e:  # noqa: BLE001
        # ⚠️ absorver NUNCA pode derrubar o webhook: o 200 para o Chatwoot vale mais que a
        # linha, porque 200 não reentrega e a mensagem se perderia de vez.
        await db.rollback()
        logger.warning("grupos.absorver falhou (%s): %s", jid, e)
        return False


#: Sinais de que a mensagem carrega DADO, não só conversa. Deliberadamente conservador: o que
#: não casa aqui fica como `tom`, e tom não vira registro em ficha de ninguém.
_SINAIS = (
    ("operacional", re.compile(
        r"\bfalt(a|ou|ando)\b|\batestado\b|\bsubstitut|\bescala\b|\bposto\b|\bplant[ãa]o\b|"
        r"\bcobrir\b|\bfolga\b|\bturno\b|\bronda\b|\bocorr[êe]ncia\b|\bchave\b|"
        r"\bport[ãa]o\b|\bc[âa]mera\b|\bnobreak\b|\bsem energia\b", re.I)),
    ("financeiro", re.compile(
        r"\bboleto\b|\bnota fiscal\b|\bnfs?-?e\b|\bpagamento\b|\bpix\b|\bcobran[çc]a\b|"
        r"\bvencimento\b|\binadimpl", re.I)),
    ("comercial", re.compile(
        r"\bproposta\b|\bor[çc]amento\b|\bcontrato\b|\bcliente novo\b|\bfornecedor\b|"
        r"\bcota[çc][ãa]o\b|\bR\$\s?\d", re.I)),
    ("pendencia", re.compile(
        r"\bpendente\b|\bcobrar\b|\bat[ée] (hoje|amanh[ãa]|segunda|sexta)\b|\bprazo\b|"
        r"\bquem vai\b|\bfica de\b", re.I)),
)


def classificar(texto: str) -> str:
    """`tom` | `operacional` | `financeiro` | `comercial` | `pendencia`.

    ⚠️ Determinístico e na ENTRADA, custo zero — mesma escolha do `classify_situacao` das
    travas do José Luís. Um classificador por LLM aqui custaria uma chamada por mensagem de
    grupo, e grupo despeja: a conversa do dia 23/09 já tinha o diagnóstico certo — "se todo
    grupo despejar tudo, viramos ruído".
    """
    t = str(texto or "")
    for classe, rx in _SINAIS:
        if rx.search(t):
            return classe
    return "tom"


async def deve_calar(db: AsyncSession, data: dict) -> tuple[bool, str | None, dict | None]:
    """A PAREDE. Devolve (calar?, jid_do_grupo, config).

    Chamada no webhook ANTES de enfileirar o agente:
      · não é grupo               → (False, None, None)  — fluxo 1:1 intocado
      · grupo não cadastrado      → (True,  jid,  None)  — ignora, nem absorve
      · modo observar             → (True,  jid,  cfg)   — absorve e CALA
      · modo falar                → (False, jid,  cfg)   — absorve e o agente decide
    """
    jid = jid_do_payload(data)
    if not jid:
        return False, None, None
    cfg = await config_do_grupo(db, jid)
    if not cfg:
        logger.info("grupos: %s não cadastrado — ignorado (fail-closed)", jid)
        return True, jid, None
    return (cfg["modo"] != "falar"), jid, cfg


async def resumo(db: AsyncSession, *, jid: str | None = None, horas: int = 24) -> dict:
    """O que passou nos grupos observados — SOB DEMANDA, nunca empurrado.

    O José Luís pediu isso na conversa de 23/09 e o Jordan concordou pelo motivo certo:
    "se todo grupo despejar tudo, viramos ruído". Então ninguém recebe resumo automático de
    grupo; alguém PERGUNTA e o resumo se monta na hora.

    ⚠️ Não devolve a conversa inteira. `tom` (bom dia, figurinha, combinação de churrasco)
    entra só como CONTAGEM — é a separação que o José Luís propôs entre tom e dado, e é o que
    mantém isto a uma distância honesta de vigiar o time. O texto só aparece do que foi
    classificado como dado relevante.
    """
    p: dict[str, object] = {"h": str(int(horas))}  # asyncpg exige str no `|| ' hours'`
    onde = "quando > now() - (:h || ' hours')::interval"
    if jid:
        onde += " AND grupo_jid = :j"
        p["j"] = jid

    por_classe = (await db.execute(text(
        f"SELECT g.nome, m.classificacao, count(*) FROM wa_grupo_mensagens m "  # noqa: S608
        f"JOIN wa_grupos g ON g.jid = m.grupo_jid WHERE {onde} "
        f"GROUP BY 1, 2 ORDER BY 1, 3 DESC"), p)).all()

    relevantes = (await db.execute(text(
        f"SELECT g.nome, m.autor_nome, m.classificacao, m.conteudo, m.quando "  # noqa: S608
        f"FROM wa_grupo_mensagens m JOIN wa_grupos g ON g.jid = m.grupo_jid "
        f"WHERE {onde} AND m.relevante AND m.classificacao <> 'tom' "
        f"ORDER BY m.quando DESC LIMIT 40"), p)).all()

    # Pedido de escala já virou rascunho: o resumo aponta para a Central, não repete o pedido
    # como se ainda estivesse solto. Sem isto o Jordan leria o mesmo pedido em dois lugares e
    # não saberia se já havia algo a decidir.
    pedidos = (await db.execute(text(
        "SELECT titulo, status, created_at FROM agent_drafts WHERE tipo = 'escala_pedido' "
        "AND created_at > now() - (:h || ' hours')::interval ORDER BY created_at DESC LIMIT 20"),
        {"h": str(int(horas))})).all()

    # ⚠️ O banco guarda UTC (certo); o resumo é lido por GENTE em Manaus. Devolver
    # "03:22" para uma mensagem das 23:22 é resumo errado, não detalhe de formato — é o
    # irmão do `punch_timestamp` que já custou caro no operacional.
    def _manaus(dt):
        return (dt - timedelta(hours=4)).strftime("%d/%m %H:%M") if dt else None

    return {
        "janela_horas": int(horas),
        "fuso": "America/Manaus (UTC-4)",
        "conversa_por_grupo": [{"grupo": r[0], "classificacao": r[1], "mensagens": r[2]} for r in por_classe],
        "dado_relevante": [{"grupo": r[0], "quem": r[1], "tipo": r[2],
                            "texto": (r[3] or "")[:300], "quando": _manaus(r[4])}
                           for r in relevantes],
        "pedidos_de_escala": [{"titulo": r[0], "status": r[1],
                               "quando": _manaus(r[2])} for r in pedidos],
        "onde_decidir": "/redesign/aprovacoes" if pedidos else None,
    }
