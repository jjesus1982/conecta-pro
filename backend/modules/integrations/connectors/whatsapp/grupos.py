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

⭐ MUDANÇA DE RUMO DO DONO — 24/09/2026, e registro aqui para este arquivo não continuar
afirmando o contrário do que está no ar. Depois de ver a captura funcionando, o Jordan decidiu,
em duas etapas:

  1. *"não trata nada no privado, tudo nos grupos, com Orlailson no Gestão, eu quero acompanhar
     todas as tratativas"* — relatório de conferência passou de DM para o grupo `Gestão`
     (`wa_grupos.recebe_relatorio`);
  2. *"quero que ele interaja e converse com naturalidade nestes 3 grupos sempre que achar
     necessário"* — os três grupos passaram a `modo = 'falar'`.

O que a parede protegia continua protegido, por peças DIFERENTES, e vale saber quais:

  · **River Park segue FORA** (nem cadastrado → `off` → ignorado por inteiro);
  · **dado pessoal não entra em grupo**: o papel `grupo` em `agent_service` NÃO recebe
    `consultar_minha_vida`, `meu_ponto_hoje` nem `historico_desta_pessoa`. Holerite de alguém
    na frente de 60 pessoas é LGPD, não preferência — e isso decorre de regra do próprio dono;
  · **teto por dia** (`max_falas_dia`, hoje 20/grupo): naturalidade não é enxurrada;
  · **operacional segue READ-ONLY**: pedido que mexe em escala vira rascunho para aprovação;
  · **`varrer_sem_resposta` NÃO persegue grupo**, em nenhum modo. Em grupo, "sem resposta" é o
    normal — o prompt diz que silêncio é o padrão, e o suspensório desfaria isso forçando
    resposta a toda mensagem.

A lição de desenho: "silêncio" e "não falar no grupo" pareciam a mesma coisa e não eram. Quando
o dono mudou uma, a outra precisou ser reimplementada em outro lugar — não reaproveitada.
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
    extra = cand.get("additional_attributes") or {}

    # ⭐ NÃO CONFIE NO NOME DO CAMPO — CONFIE NA FORMA (24/09/2026, segunda medição).
    #
    # O Orlailson postou a escala no OPERACIONAL e foi gravado como `lead` DESCONHECIDO. O
    # contato dele no Chatwoot está assim:
    #
    #     name         = "+559281386006"      ← o telefone DE VERDADE
    #     phone_number = "+224751964406008"   ← o LID, não telefone
    #     identifier   = "224751964406008@lid"
    #
    # Ou seja: `phone_number` pode carregar LID, e o telefone pode estar em `name`. No contato
    # do Jordan é o oposto (`phone_number` correto). Os dois casos existem HOJE, na mesma
    # tabela — então nenhum nome de campo é fonte confiável.
    #
    # ⚠️ E a minha guarda anterior piorou: eu descartava `name` "quando parece telefone",
    # justamente o caso em que ele É o telefone. A régua certa não é "parece número", é
    # **parece telefone BRASILEIRO** — 55 + DDD + 8 ou 9 dígitos. O LID tem 15 dígitos e não
    # começa com 55, e é isso que o separa.
    def _fone_br(v) -> str | None:
        d = "".join(c for c in str(v or "") if c.isdigit())
        if d.startswith("55") and len(d) in (12, 13):
            return d
        if len(d) in (10, 11):  # já sem DDI
            return d
        return None

    for bruto in (cand.get("phone_number"), cand.get("name"), extra.get("participant"),
                  extra.get("author"), data.get("participant"), cand.get("identifier")):
        achado = _fone_br(bruto)
        if achado:
            nome_cru = extra.get("participant_name") or extra.get("author_name")
            # `name` só é NOME quando não é o telefone que acabei de usar.
            if not nome_cru and not _fone_br(cand.get("name")):
                nome_cru = cand.get("name")
            return achado, (str(nome_cru) if nome_cru else None)

    # ⭐ A FORMA REAL, medida na primeira mensagem de verdade (24/09/2026, 08:18 no
    # OPERACIONAL). Eu tinha escrito este parser contra payload sintético e ele errou:
    #
    #   · o GRUPO é o contato da CONVERSA  → conversation.meta.sender.identifier = ...@g.us
    #   · o AUTOR é o `sender` do TOPO     → sender.phone_number = "+559286465328"
    #   · sender.identifier é um **@lid**  → "134286564950018@lid", NÃO é telefone
    #   · sender.additional_attributes     → VAZIO. Era onde eu procurava.
    #
    # Último recurso: alguns provedores prefixam o conteúdo com o autor.
    nome = extra.get("participant_name") or extra.get("author_name")
    fone = None
    m = re.match(r"^\+?(\d{10,15})\s*[:\-]\s*", str(data.get("content") or ""))
    if m:
        fone = _fone_br(m.group(1))

    # ⚠️ NENHUM outro palpite. O `identifier` @lid e o `phone_number` com LID já vazaram uma
    # vez para dentro do banco (a escala do Orlailson gravada como `lead` desconhecido). Devolver
    # None é honesto e o log abaixo diz o que veio; devolver o LID cria autor que não existe e
    # ninguém desconfia da linha.
    if not fone:
        # ⭐ DIAGNÓSTICO da forma real (24/09/2026, quando a captura foi ligada). Eu escrevi
        # este parser contra payload SINTÉTICO, porque com a captura desligada não existia
        # payload real para olhar. Se a forma do Chatwoot puser o autor num terceiro lugar, o
        # sintoma é silencioso: a mensagem entra com autor nulo e o aprendizado de tom sai sem
        # dono. Então registro a ESTRUTURA quando falho — e só quando falho.
        #
        # ⚠️ Só as CHAVES, nunca os valores: payload de grupo carrega texto de conversa e
        # telefone de terceiro, e log não é lugar de dado pessoal. As chaves bastam para
        # consertar o parser.
        try:
            logger.warning(
                "grupos: autor NÃO identificado — forma do payload: topo=%s sender=%s extra=%s",
                sorted(data)[:15], sorted(cand)[:15], sorted(extra)[:15])
        except Exception:  # noqa: BLE001
            pass
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
        r = await db.execute(text(
            "INSERT INTO wa_grupo_mensagens "
            "  (grupo_jid, chatwoot_message_id, autor_fone, autor_nome, autor_employee_id, "
            "   autor_tipo, conteudo, classificacao, relevante) "
            "VALUES (:j, :mid, :af, :an, CAST(:aid AS uuid), :at, :c, :cl, :rel) "
            "ON CONFLICT (chatwoot_message_id) WHERE chatwoot_message_id IS NOT NULL "
            "DO NOTHING RETURNING id"),
            {"j": jid, "mid": chatwoot_message_id, "af": autor_fone,
             "an": (getattr(identidade, "nome", None) or autor_nome),
             "aid": getattr(identidade, "employee_id", None),
             "at": getattr(identidade, "tipo", None),
             "c": str(conteudo)[:8000], "cl": classe, "rel": classe != "tom"})
        gravou = r.first() is not None
        await db.commit()
        # ⭐ 24/09/2026 — O `DO NOTHING` DESCARTAVA EM SILÊNCIO e esta função devolvia True de
        # qualquer jeito: sucesso vazio, o padrão de falha que esta casa já documentou três
        # vezes. Descobri do pior jeito, causando: meu replay de teste usou `id: 4137`, um id
        # PLAUSÍVEL do espaço real, e meia hora depois a mensagem verdadeira do grupo Gestão
        # nasceu com esse mesmo id — colidiu, foi descartada, e o webhook respondeu 200.
        #
        # A lição não é "não teste em produção": é que id de teste nunca pode morar no espaço
        # de id real. O oráculo desta frente usa id NEGATIVO justamente por isso, e eu
        # hand-rolei um replay positivo sem aplicar a minha própria regra.
        #
        # Agora o descarte APARECE. Não é erro (reentrega do Chatwoot é normal e o dedup é
        # desejado), por isso `info` e não `warning` — mas fica medível, e uma rajada de
        # descartes deixa de ser invisível.
        if not gravou:
            logger.info("grupos: mensagem %s do grupo %s já existia — nada gravado (dedup)",
                        chatwoot_message_id, jid)
        return gravou
    except Exception as e:  # noqa: BLE001
        # ⚠️ absorver NUNCA pode derrubar o webhook: o 200 para o Chatwoot vale mais que a
        # linha, porque 200 não reentrega e a mensagem se perderia de vez.
        await db.rollback()
        logger.warning("grupos.absorver falhou (%s): %s", jid, e)
        return False


#: Sinais de que a mensagem carrega DADO, não só conversa. Deliberadamente conservador: o que
#: não casa aqui fica como `tom`, e tom não vira registro em ficha de ninguém.
_SINAIS = (
    # 🔴 PESSOAL/DISCIPLINAR VEM PRIMEIRO, e este balde nasceu de um erro meu com consequência
    # de LGPD (24/09/2026). Eu ia usar o balde `tom` como corpus para ensinar o TOM da casa ao
    # agente — "é só conversa, não é dado". Fui olhar o que havia lá dentro e achei:
    #
    #     "Informo que foi feita aplicação de uma advertência disciplinar no Sr. <nome>"
    #
    # Advertência disciplinar NOMINAL, classificada como conversa, a um passo de ser injetada no
    # prompt como exemplo de estilo. O balde `tom` não é "o que não importa" — é "o que minha
    # régua não reconheceu", e isso inclui o que ela deveria proteger.
    #
    # Agora advertência, atestado, exame, afastamento e salário saem de `tom`, entram como
    # `pessoal`, contam como RELEVANTE (o supervisor precisa saber que houve) e ficam FORA do
    # corpus de tom e fora de qualquer citação de texto.
    ("pessoal", re.compile(
        r"\badvert[êe]ncia\b|\bdisciplinar\b|\bsuspens[ãa]o\b|\bjusta causa\b|"
        r"\batestado\b|\bexame\b|\baso\b|\bafastament|\bINSS\b|\bsal[áa]rio\b|"
        r"\bholerite\b|\bcontracheque\b|\bdemiss|\brescis|\bferias\b|\bférias\b", re.I)),
    # ⭐ ROTINA — o comunicado de praxe do posto (24/09/2026). Os grupos dos condomínios
    # despejam comunicado a cada 15 minutos, e a maior parte diz que está tudo normal:
    # "Portões de entrada e saída operando normalmente", "Bombas da piscina operando
    # normalmente", "Lixeira em ordem e sem autorizações", "Informo registro de entrada".
    #
    # Medido em 24h: 96 mensagens, 12.660 caracteres, e o `resumo_grupos` levou 17.648 tokens de
    # ENTRADA para o modelo numa única chamada. Com mais condomínios entrando isso bate no teto,
    # e o sintoma é o que o Jordan já viu: turno terminando sem texto.
    #
    # ⚠️ `rotina` não é lixo — é a PROVA de que o posto reportou. Ela CONTA no resumo ("Mirante:
    # 30 comunicados de rotina") e não é CITADA. Mesma jogada do `tom`, por outra razão: tom é
    # conversa, rotina é registro repetitivo. O que interessa ao supervisor é a exceção.
    #
    # E vem ANTES de `operacional` de propósito: "portão operando normalmente" casa com
    # `\bport[ãa]o\b` e viraria dado relevante, enchendo o resumo de nada.
    ("rotina", re.compile(
        r"(em ordem|operando normalmente|funcionando normalmente|sem autoriza|sem ocorr|"
        r"fica (o )?registr|fica registrado|registro de entrada|abastecid|"
        r"nada a relatar|tudo (tranquilo|normal|em ordem)|sem intercorr)", re.I)),
    # ⭐ A ESCALA DO DIA, e ela vem PRIMEIRO porque é o artefato mais valioso do grupo
    # (medida em 24/09/2026, a primeira mensagem real do OPERACIONAL):
    #
    #     *Prime Arena 06h às 18h*
    #     Jair Rocha - P1
    #     *Villa dos Pássaros 06h às 18h*
    #     Jeovane Nascimento - P1
    #
    # Meu classificador a leu como `tom` — conversa — porque nenhuma das minhas palavras
    # ("escala", "posto", "plantão") aparece ali. O sinal não é vocabulário, é ESTRUTURA:
    # faixa de horário `HHh às HHh` e o marcador de posição `- P1`. Nenhum dos dois acontece
    # em papo de grupo, e os dois juntos são a escala.
    #
    # ⚠️ Classificar isso como tom significava `relevante = false`, e portanto a escala do dia
    # NÃO aparecer no `resumo_grupos` — a única coisa que o supervisor mais precisa ver seria
    # justamente a que o resumo esconde. Régua de palavra-chave sobre um documento que não usa
    # as palavras: eu já tinha essa lição escrita e ela não me protegeu de escrevê-la de novo.
    ("escala_do_dia", re.compile(
        r"\d{1,2}\s*h\s*(às|as|a)\s*\d{1,2}\s*h.*?\n.*?-\s*P\d", re.I | re.S)),
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
    # ⭐ MENÇÃO A ALGUÉM NUNCA É CONVERSA (24/09/2026). O grupo Gestão trouxe um pedido de
    # troca de fardamento dos ASGs de 5 postos, com "urgência", mencionando o Jordan por
    # `mention://contact/` — e meu classificador chamou de `tom`, o que o tornaria invisível no
    # resumo. Quem menciona alguém está pedindo ação dele; nenhuma régua de vocabulário pega
    # isso porque a palavra que importa é o NOME de quem foi chamado.
    ("solicitacao", re.compile(
        r"mention://contact/|\b(solicit|urgen|preciso que|pode(ria)? (ver|pedir|providenciar)|"
        r"fardament|uniforme|material|providenci)", re.I)),
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
        # ⭐ SEGUNDO SINAL, independente do parser (23/09/2026). Todo o resto desta parede
        # depende de `jid_do_payload` achar o JID em um dos dois lugares que eu MEDI — e eu
        # medi com payload sintético, porque a captura de grupo ainda estava desligada. Se a
        # forma real do Chatwoot puser o JID num terceiro lugar, `jid` vem None, a função
        # devolve "não é grupo", a mensagem segue para o agente e o José Luís **responde no
        # grupo** — exatamente o que o dono proibiu.
        #
        # Então: se o sufixo de grupo aparecer EM QUALQUER LUGAR do payload e eu não tiver
        # conseguido extrair o JID, isto é uma mensagem de grupo que meu parser não entendeu.
        # Calo, e grito no log. O silêncio é o default seguro; o log é o que me diz que o
        # parser precisa de conserto, em vez de o grupo descobrir isso por mim.
        try:
            import json  # noqa: PLC0415

            if SUFIXO_GRUPO in json.dumps(data, default=str):
                logger.error("grupos: payload TEM %s e o parser não achou o JID — calando. "
                             "Conserte `jid_do_payload`. Chaves: %s",
                             SUFIXO_GRUPO, sorted(data)[:12])
                return True, None, None
        except Exception:  # noqa: BLE001
            pass
        return False, None, None
    cfg = await config_do_grupo(db, jid)
    if not cfg:
        # ⭐ DESCOBERTA SEM CONSENTIMENTO DE ABSORVER (24/09/2026). O fail-closed está certo —
        # grupo novo não começa a gravar conversa de terceiro sozinho — mas ele tem um custo que
        # eu ia pagar caro: o Jordan disse "vou incluir ele nos outros grupos" (os dos
        # condomínios, onde as fotos da troca de turno são postadas). Sem isto, ele me adiciona,
        # as fotos chegam, NADA acontece, e parece defeito meu.
        #
        # Então o grupo se AUTO-CADASTRA em `off`: fica registrado com nome e jid, visível na
        # tabela, e continua ignorado até alguém decidir. Descobrir não é absorver.
        await _descobrir(db, jid, data)
        # ⚠️ RELÊ depois de descobrir. Sem isto a PRIMEIRA mensagem do grupo novo volta com
        # `cfg=None` e o webhook não a absorve — e a primeira mensagem de um grupo de posto é,
        # justamente, a foto da troca de turno que motivou entrar nele. Perder exatamente o
        # primeiro registro é o tipo de defeito que ninguém nota até precisar do histórico.
        cfg = await config_do_grupo(db, jid)
        if not cfg:
            logger.info("grupos: %s não cadastrado e não registrei — ignorado", jid)
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

    # ⚠️ TETO DURO E PRIORIDADE POR EXCEÇÃO. A versão anterior devolvia 40 mensagens com 300
    # chars cada — 12k de texto que viravam 17.648 tokens de entrada, e crescendo a cada
    # condomínio novo. Aqui: `rotina` e `tom` ficam fora do texto (aparecem na contagem), e a
    # ordem é por EXCEÇÃO primeiro (ocorrência/pendência/solicitação), não por hora.
    #
    # `pessoal` entra só onde o dono autorizou dado nominal — nos grupos de condomínio não.
    relevantes = (await db.execute(text(
        f"SELECT g.nome, m.autor_nome, m.classificacao, m.conteudo, m.quando "  # noqa: S608
        f"FROM wa_grupo_mensagens m JOIN wa_grupos g ON g.jid = m.grupo_jid "
        f"WHERE {onde} AND m.relevante AND m.classificacao NOT IN ('tom','rotina') "
        f"  AND (m.classificacao <> 'pessoal' OR g.dado_pessoal_ok) "
        f"ORDER BY (m.conteudo ~* 'danific|colidiu|quebrad|defeito|troca|urgen|falta|"
        f"           ocorr[êe]ncia|problema|parad|vazament|sem energia') DESC, m.quando DESC "
        f"LIMIT 12"), p)).all()

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
        # 240 chars: cabe o que aconteceu e corta o cabeçalho repetido ("Conecta Mais –
        # Segurança e Tecnologia / Data / Posto / Turno / Agente"), que é idêntico em toda
        # mensagem e ocupava metade do orçamento sem informar nada novo.
        "dado_relevante": [{"grupo": r[0], "quem": r[1], "tipo": r[2],
                            "texto": _essencia(r[3]), "quando": _manaus(r[4])}
                           for r in relevantes],
        "pedidos_de_escala": [{"titulo": r[0], "status": r[1],
                               "quando": _manaus(r[2])} for r in pedidos],
        "onde_decidir": "/redesign/aprovacoes" if pedidos else None,
    }


async def grupo_da_conversa(db: AsyncSession, conversation_id: int | None) -> dict | None:
    """A config do grupo desta conversa do Chatwoot, ou None quando não é grupo.

    Separada de `conversa_e_grupo_calado` porque as perguntas são diferentes e confundi-las
    já custou caro nesta casa: "é grupo?" e "devo calar?" mudam de resposta de forma
    independente. Desde 24/09/2026 o Jordan quer o José Luís CONVERSANDO nos grupos, então
    "é grupo" passou a governar PROMPT e FERRAMENTAS (um grupo não é um 1:1: não se mostra
    holerite de ninguém na frente de 60 pessoas), enquanto "devo calar" governa só o silêncio.
    """
    if not conversation_id:
        return None
    try:
        r = (await db.execute(text(
            "SELECT jid, nome, modo, foco, midia_ok, max_falas_dia FROM wa_grupos "
            " WHERE chatwoot_conversation_id = :c LIMIT 1"), {"c": int(conversation_id)})).mappings().first()
    except Exception as e:  # noqa: BLE001
        logger.warning("grupos: não sei se a conversa %s é grupo (%s)", conversation_id, e)
        return None
    return dict(r) if r else None


async def falas_hoje(db: AsyncSession, jid: str) -> int:
    """Quantas vezes o José Luís já falou NESTE grupo hoje (hora de Manaus)."""
    try:
        return int((await db.execute(text(
            "SELECT count(*) FROM wa_grupo_falas WHERE grupo_jid = :j "
            "  AND quando > date_trunc('day', now() - interval '4 hours') + interval '4 hours'"),
            {"j": jid})).scalar() or 0)
    except Exception as e:  # noqa: BLE001
        # ⚠️ Falha aqui devolve 0, e 0 LIBERA a fala. É deliberado e é o oposto do resto deste
        # módulo: o teto existe para não virar ruído, não para proteger ninguém. Um erro de
        # contagem que CALASSE o agente pareceria "ele parou de funcionar", e o Jordan pediu
        # que ele conversasse.
        logger.warning("grupos: não contei as falas de %s (%s)", jid, e)
        return 0


async def conversa_e_grupo_calado(db: AsyncSession, conversation_id: int | None) -> str | None:
    """JID do grupo quando ESTA conversa do Chatwoot é um grupo que não deve ser respondido.

    ⭐ Existe porque a parede do webhook NÃO era a única porta, e eu descobri do pior jeito:
    com o Jordan mandando mensagem no grupo Gestão às 08:50 de 24/09 e o José Luís redigindo
    resposta às 08:54, quatro minutos depois, com a parede do webhook funcionando e a mensagem
    corretamente absorvida.

    A segunda porta é `tasks.varrer_sem_resposta` — um beat que procura conversa cuja última
    mensagem é de quem escreveu e que não teve resposta, e REENFILEIRA `processar_incoming`.
    Ela existe para garantir que silêncio nunca aconteça; esta parede existe para garantir que
    silêncio SEMPRE aconteça em grupo. São objetivos opostos, e a varredura ganhava por rodar
    depois. Uma mensagem de grupo, que nunca terá resposta por desenho, é candidata PERMANENTE
    da varredura durante os 90 minutos da janela dela.

    ⚠️ Por isso a trava mora aqui e é chamada de `processar_incoming`, o ponto por onde os DOIS
    caminhos passam — e por onde passará o terceiro que alguém escrever amanhã. Guardar cada
    chamador é a receita para o chamador novo nascer furado; foi assim que esta frente gastou
    uma noite.

    `None` = não é grupo calado (ou não sei) → o agente segue o caminho normal. Fail-closed
    NÃO cabe aqui: recusar na dúvida silenciaria conversa de CLIENTE, e o dano de não atender
    cliente é maior que o de uma nota interna num grupo.
    """
    if not conversation_id:
        return None
    try:
        r = (await db.execute(text(
            "SELECT jid, modo FROM wa_grupos WHERE chatwoot_conversation_id = :c LIMIT 1"),
            {"c": int(conversation_id)})).first()
    except Exception as e:  # noqa: BLE001
        logger.warning("grupos: não sei se a conversa %s é grupo (%s)", conversation_id, e)
        return None
    if r and r[1] != "falar":
        return str(r[0])
    return None


async def aprender_conversa(db: AsyncSession, *, jid: str, conversation_id: int | None) -> None:
    """Grava qual conversa do Chatwoot corresponde a este grupo. Idempotente e best-effort.

    O mapeamento se aprende do tráfego real em vez de ser cadastrado à mão: o webhook é o
    único lugar que vê o JID e o `conversation_id` juntos. E a varredura só age a partir de 3
    minutos, então a primeira mensagem do grupo já deixa o mapa pronto antes de ela olhar.
    """
    if not conversation_id:
        return
    try:
        await db.execute(text(
            "UPDATE wa_grupos SET chatwoot_conversation_id = :c "
            " WHERE jid = :j AND coalesce(chatwoot_conversation_id, -1) <> :c"),
            {"c": int(conversation_id), "j": jid})
        await db.commit()
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        logger.warning("grupos: não aprendi a conversa de %s (%s)", jid, e)


async def _descobrir(db: AsyncSession, jid: str, data: dict) -> None:
    """Registra um grupo novo em `off` (ignorado) para alguém decidir depois. Best-effort.

    ⚠️ `modo='off'` e NADA de absorção: o grupo passa a EXISTIR na tabela, com o nome que o
    Chatwoot mostra, e segue ignorado. É a diferença entre "eu não sabia que esse grupo existe"
    e "eu sei, e estou esperando decisão" — a primeira é um vão, a segunda é uma fila.

    O nome sai do payload porque é a única coisa que identifica o grupo para um humano: um JID
    `120363…@g.us` não diz a ninguém de que condomínio se trata.
    """
    nome = None
    for fonte in (((data.get("conversation") or {}).get("meta") or {}).get("sender") or {},
                  data.get("sender") or {}):
        if (n := fonte.get("name")) and str(n).strip():
            nome = str(n).strip()[:120]
            break
    try:
        # ⭐ A POLÍTICA INVERTEU, COM AUTORIZAÇÃO EXPLÍCITA (24/09/2026): *"mandei o Orlailson
        # adicionar o José Luís em todos os grupos dos postos de serviços da Conecta Mais, de
        # todos os condomínios, exclui o grupo do River Park, não trabalhamos mais neste
        # condomínio"* — Jordan.
        #
        # Antes: nada era permitido por padrão, e grupo novo nascia `off`. Isso protegia quando
        # ninguém havia decidido nada. Agora o dono decidiu em bloco, e manter `off` por padrão
        # faria cada condomínio novo exigir intervenção manual — o mesmo vão de antes, com
        # outra roupa.
        #
        # ⚠️ Então a parede deixa de ser "nada entra" e passa a ser uma LISTA DE EXCLUSÃO, e é
        # honesto dizer que isso é mais frágil: uma lista de negação só protege do que está
        # nela. Duas coisas compensam:
        #   · quem entra nasce em `observar` + `max_falas_dia = 0`. **Ele NUNCA fala em grupo de
        #     condomínio**, porque lá tem síndico e morador. Isso não é preferência — decorre da
        #     própria decisão do dono de tirar o River Park;
        #   · `midia_ok = true` porque a FOTO é a evidência da troca de turno, que é o motivo de
        #     ele estar nesses grupos.
        #
        # O River Park está cadastrado à mão como `off`, com o motivo escrito na linha, e o
        # `ON CONFLICT DO NOTHING` abaixo garante que esta descoberta nunca o reabra.
        await db.execute(text(
            "INSERT INTO wa_grupos (jid, nome, modo, midia_ok, max_falas_dia, foco) "
            "VALUES (:j, :n, 'observar', true, 0, :f) ON CONFLICT (jid) DO NOTHING"),
            {"j": jid, "n": nome or "(sem nome)",
             "f": "Grupo de posto/condomínio descoberto automaticamente. OBSERVA e absorve "
                  "foto de troca de turno; NUNCA fala (tem cliente dentro)."})
        await db.commit()
        logger.warning("grupos: DESCOBERTO grupo novo %r (%s) — em `observar`, mídia ON, "
                       "SEM permissão de falar", nome, jid)
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        logger.warning("grupos: não registrei o grupo novo %s (%s)", jid, e)


#: Palavras que tiram uma mensagem do corpus de tom, mesmo classificada como `tom`. É uma
#: SEGUNDA barreira, não a primeira: a primeira é a classificação `pessoal`. Duas porque a
#: consequência de errar aqui é dado de pessoa dentro do prompt do modelo, e classificação é
#: régua de palavra — sempre haverá a frase que ela não previu.
_FORA_DO_TOM = re.compile(
    r"advert|disciplinar|atestado|exame|afastament|sal[áa]rio|holerite|demiss|rescis|"
    r"\bCPF\b|\bRG\b|R\$\s?\d|\bsuspens", re.I)


async def corpus_de_tom(db: AsyncSession, *, jid: str | None = None, limite: int = 14) -> list[dict]:
    """Como a CASA fala, para o agente soar como colega e não como atendimento.

    ⭐ Por que isto existe: o Jordan pediu que o José Luís interagisse com naturalidade nos
    grupos, e a primeira rodada real saiu "Imagina! 😊 💙" e "Não estou conseguindo te atender
    direito agora" — tom de SAC, não de alguém que trabalha ali. O jeito de corrigir não é eu
    inventar um estilo no prompt: é mostrar como as pessoas de verdade escrevem nesses grupos.
    É o único aprendizado desta frente que tem dado real por trás.

    ⚠️ QUATRO FILTROS, e cada um tem uma razão que custou medição:

      · só `tom` — dado operacional/financeiro/pessoal não é exemplo de estilo;
      · NUNCA `pessoal`, e ainda passa por `_FORA_DO_TOM` (defesa em profundidade: achei
        advertência disciplinar nominal dentro do balde `tom`);
      · só mensagem CURTA (≤ 160 chars): o que ensina tom é a réplica do dia a dia, não o
        comunicado longo — e comunicado longo é onde mora nome de gente;
      · só de quem é da CASA (`autor_tipo` funcionário/dono). Cliente em grupo de condomínio
        não define como a empresa fala, e usar a fala dele seria pior que inútil.

    Devolve [] sem drama quando não há corpus: o agente segue com o prompt base. Ensinar tom é
    melhoria, não dependência.
    """
    p: dict[str, object] = {"lim": int(limite) * 4}
    onde = ("m.classificacao = 'tom' AND m.autor_tipo IN ('funcionario','dono') "
            "AND length(m.conteudo) BETWEEN 2 AND 160")
    if jid:
        onde += " AND m.grupo_jid = :j"
        p["j"] = jid
    try:
        rows = (await db.execute(text(
            f"SELECT m.autor_nome, m.conteudo, g.nome FROM wa_grupo_mensagens m "  # noqa: S608
            f"  JOIN wa_grupos g ON g.jid = m.grupo_jid WHERE {onde} "
            f" ORDER BY m.criado_em DESC LIMIT :lim"), p)).all()
    except Exception as e:  # noqa: BLE001
        logger.warning("grupos: corpus de tom indisponível (%s)", e)
        return []
    saida = []
    for autor, conteudo, grupo in rows:
        if _FORA_DO_TOM.search(conteudo or ""):
            continue
        saida.append({"quem": (autor or "").split()[0].title() if autor else "colega",
                      "grupo": grupo, "texto": " ".join(str(conteudo).split())[:160]})
        if len(saida) >= limite:
            break
    return saida


#: O cabeçalho que TODO comunicado de posto repete. Cortá-lo não perde informação: o grupo já
#: diz o posto, e data/turno/agente vêm nos outros campos do resumo.
#: ⚠️ SEM ÂNCORA `^`: o Ideal Flores manda "*CONDOMÍNIO IDEAL FLORES* *Conecta Mais – ...*" —
#: o nome do condomínio vem ANTES do cabeçalho, e com a âncora no início o corte não acontecia.
#: Régua ancorada num formato que só um posto segue é régua que falha nos outros.
_CABECALHO_COMUNICADO = re.compile(
    r"\*?\s*Conecta Mais[^\n]*\n+(\s*\*?\s*(Data|Posto|Turno|Agente|AGP|ronda|AGP P\d)\s*\*?\s*:?[^\n]*\n+)*",
    re.I)


def _essencia(texto: str | None) -> str:
    """O que a mensagem DIZ, sem o cabeçalho de praxe. Máx. 240 chars.

    ⚠️ Metade do orçamento de tokens do resumo era cabeçalho idêntico: "*Conecta Mais –
    Segurança e Tecnologia* / *Data*: 24/09/2026 / *Posto*: GREEN HILLS / *Turno Diurno*: 07h
    às 19h / *AGP P1*: Fernanda maciel". Repetido em cada uma das ~96 mensagens do dia. O
    supervisor não precisa reler isso doze vezes — ele precisa do que aconteceu.
    """
    t = _CABECALHO_COMUNICADO.sub("", str(texto or "")).strip()
    # Sobra do nome do condomínio antes do cabeçalho, quando havia.
    t = re.sub(r"^\*?\s*(COND[OMÍNIO]*\.?\s+)?[A-ZÁÉÍÓÚÂÊÔÃÕÇ \d\-]{4,40}\*?\s*", "", t, count=1)
    t = " ".join(t.split())
    return (t or " ".join(str(texto or "").split()))[:240]


async def expurgar(db: AsyncSession) -> dict:
    """Apaga mensagem de grupo além da retenção de CADA grupo. Roda no beat diário.

    🔴 Por que isto existe (24/09/2026, pedido do Jordan). `wa_grupos.retencao_dias` existia com
    default 90 e **nada apagava** — o campo que deveria limitar não tinha quem o lesse. É o mesmo
    erro que eu havia acabado de consertar na autorização (`dado_pessoal_ok` gravado e ignorado),
    na direção oposta: lá a permissão não valia, aqui a proteção não existia.

    ⚠️ E o que acumulava não é conversa da equipe: é DADO DE TERCEIRO. Os comunicados de portaria
    trazem nome de morador, de visitante, marca/modelo/placa de carro — hoje o Prime Arena mandou
    "VISITANTE NOME: MÔNICA MENDES, FIAT TORO, PLACA QZD 1I85, LIBERADO POR: ...". Guardar isso
    para sempre num banco nosso, sem prazo e sem finalidade declarada, é o oposto do que a
    cláusula de eliminação em 30 dias promete ao cliente.

    ⭐ 30 dias para grupo de CONDOMÍNIO (tem cliente e terceiro dentro), 90 para grupo interno.
    O número não é meu: 30 é o prazo que a minuta de contrato promete. A retenção por grupo vem
    da coluna, então o Jordan muda caso a caso sem tocar em código.

    A FALA do agente (`wa_grupo_falas`) segue a mesma régua: é registro do que NÓS dissemos, e
    não faz sentido guardar mais tempo que o contexto que a gerou.
    """
    apagadas = {}
    try:
        grupos = (await db.execute(text(
            "SELECT jid, nome, coalesce(retencao_dias, 90) AS dias FROM wa_grupos"))).mappings().all()
        for g in grupos:
            r = await db.execute(text(
                "DELETE FROM wa_grupo_mensagens WHERE grupo_jid = :j "
                "  AND criado_em < now() - make_interval(days => :d) RETURNING 1"),
                {"j": g["jid"], "d": int(g["dias"])})
            n = len(r.fetchall())
            if n:
                apagadas[g["nome"]] = n
        r2 = await db.execute(text(
            "DELETE FROM wa_grupo_falas WHERE quando < now() - interval '90 days' RETURNING 1"))
        falas = len(r2.fetchall())
        # ⚠️ RISCO F: `troca_turno_confirmacoes` guarda QUEM PROMETEU assumir posto — dado de
        # pessoa, com o texto da resposta dela. A tabela irmã (`wa_grupo_mensagens`) já tinha
        # prazo e esta não: mais um campo de retenção que existia só no meu plano. 90 dias cobre
        # a folha do mês e a auditoria do seguinte; depois disso é acúmulo sem finalidade.
        r3 = await db.execute(text(
            "DELETE FROM troca_turno_confirmacoes "
            " WHERE criado_em < now() - make_interval(days => coalesce(retencao_dias, 90)) "
            " RETURNING 1"))
        confirmacoes = len(r3.fetchall())
        await db.commit()
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        logger.error("grupos.expurgar falhou (%s)", e)
        return {"ok": False, "erro": str(e)[:160]}
    if apagadas or falas:
        logger.warning("grupos: expurgo — mensagens %s · falas %s", apagadas, falas)
    return {"ok": True, "mensagens_apagadas": apagadas, "falas_apagadas": falas,
            "confirmacoes_apagadas": confirmacoes}


async def participantes_do_grupo(jid: str) -> list[str] | None:
    """Telefones de quem está NO grupo agora, pelo Baileys. None se não consegui perguntar.

    ⭐ Isto transforma a autorização do dono em PAREDE. Ele disse, em 24/09, "no Gestão estão
    apenas José Luís, Jordan e Orlailson, pode expor qualquer informação ali" — e eu liguei a
    permissão numa coluna. Mas ela repousava num fato que ninguém vigiava: **quem está dentro
    do grupo**. Alguém adicionado amanhã, e o agente passaria a dizer nome de colaborador na
    frente de quem entrou, sem uma linha de código notar.

    Comentário na coluna não é parede. Isto é: o Baileys expõe `group-metadata` com
    `participants`, e medi no Gestão — 3 pessoas, as três que o dono nomeou.

    ⚠️ `None` (não consegui perguntar) NÃO é "mudou": é desconhecido. Quem chama decide, e a
    decisão certa é manter a autorização — derrubá-la por falha de rede transformaria uma
    indisponibilidade do Baileys em "o José Luís parou de responder direito", que é o tipo de
    falha que ninguém liga ao motivo.
    """
    import os as _os  # noqa: PLC0415

    import httpx as _httpx  # noqa: PLC0415

    # ⚠️ OS NOMES SÃO DIFERENTES DOS DOIS LADOS, e eu usei os do lado errado. No Chatwoot as
    # variáveis se chamam `BAILEYS_PROVIDER_DEFAULT_*`; no backend do Conecta são
    # `BAILEYS_API_KEY` / `BAILEYS_URL` / `BAILEYS_CONNECTION` — mesmo VALOR, outro NOME.
    #
    # 🔴 E o desenho fazia isso passar em silêncio: sem chave, `participantes_do_grupo` devolve
    # None, e None MANTÉM a autorização (por decisão: falha de rede não deve derrubar permissão).
    # Resultado: a parede que eu acabei de construir para vigiar a composição do grupo ficaria
    # INERTE, sempre respondendo "não consegui perguntar, sigo liberando" — exatamente o padrão
    # de trava que existe e não gateia nada, que eu passei o dia caçando nos outros lugares.
    #
    # Provei funcionando com a chave injetada à mão no teste, num ambiente que não era o de
    # produção. Verificar o ambiente REAL antes de anunciar era o passo que faltava.
    url = _os.getenv("BAILEYS_URL") or "http://baileys-api:3025"
    key = (_os.getenv("BAILEYS_API_KEY")
           or _os.getenv("BAILEYS_PROVIDER_DEFAULT_API_KEY") or "")
    fone = _os.getenv("BAILEYS_CONNECTION") or _os.getenv("BAILEYS_NUMERO") or "+558008804414"
    if not key:
        # Log em ERROR, não em warning: chave ausente aqui significa parede desligada, e o
        # sintoma é uma permissão que continua valendo sem ninguém conferir.
        logger.error("grupos: sem chave do Baileys — a parede da composição do grupo está "
                     "INERTE e a autorização de dado nominal segue por padrão")
        return None
    try:
        async with _httpx.AsyncClient(timeout=8.0) as cli:
            r = await cli.get(f"{url}/connections/{fone}/group-metadata",
                              params={"jid": jid}, headers={"x-api-key": key})
        if r.status_code != 200:
            logger.warning("grupos: group-metadata %s para %s", r.status_code, jid)
            return None
        saida = []
        for p in (r.json().get("participants") or []):
            # `phoneNumber` vem como "559286465328@s.whatsapp.net"; o `id` é @lid e não disca.
            pn = str(p.get("phoneNumber") or "").split("@")[0]
            if pn.isdigit():
                saida.append(pn)
        return saida or None
    except Exception as e:  # noqa: BLE001
        logger.warning("grupos: não consegui os participantes de %s (%s)", jid, e)
        return None


async def grupo_ainda_e_o_autorizado(db: AsyncSession, jid: str) -> tuple[bool, str | None]:
    """(a composição do grupo é a autorizada?, o que mudou). Fecha o vão da autorização.

    Sem lista autorizada gravada → (True, None): grupo que ninguém restringiu não é vigiado aqui.
    Baileys indisponível → (True, None): desconhecido não é mudança (ver `participantes_do_grupo`).
    Entrou alguém que não estava na lista → (False, quem), e a autorização de nome cai.
    """
    try:
        row = (await db.execute(text(
            "SELECT participantes_autorizados FROM wa_grupos WHERE jid = :j"), {"j": jid})).first()
    except Exception:  # noqa: BLE001
        return True, None
    autorizados = set(row[0] or []) if row else set()
    if not autorizados:
        return True, None
    agora = await participantes_do_grupo(jid)
    if agora is None:
        return True, None
    novos = [p for p in agora if p not in autorizados]
    if novos:
        await db.execute(text(
            "UPDATE wa_grupos SET participantes_conferidos_em = now() WHERE jid = :j"), {"j": jid})
        await db.commit()
        return False, ", ".join(novos)
    return True, None
