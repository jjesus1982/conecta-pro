"""O vigia que LÊ os grupos — inclusive as fotos — e joga a intercorrência no Gestão.

🔴 POR QUE EXISTE (27/09/2026). Jordan: *"preciso que ele reporte problemas, troca de turno,
fotos, erros, falhas operacionais, despadronização dos agentes de portaria, ele tem que ser um
vigia de verdade 24h monitorando os nossos grupos e jogando no gestão toda e qualquer
intercorrência"*.

E a pergunta anterior dele — *"ele vê fotos?"* — tinha uma resposta ruim: **não via**. A mídia
de grupo era gravada com a marca `📎 [analisando anexo(s)…]` e a análise só voltava para
`cwi_message_log`. Medido: **1.282 mensagens presas no marcador em 5 dias**, enquanto 1.935
imagens estavam descritas na outra tabela. Depois do conserto e do backfill, 1.248 ficaram
legíveis — e **684 mudaram de classe** ao serem reavaliadas (350 `operacional`, 33
`solicitacao`, 15 `problema_ponto`).

⭐ **É isso que esta varredura lê.** Ela não descobre nada sozinha: ela olha o que já está no
banco, com o rótulo que já existe, e decide o que merece interromper o dia de alguém.

## O Hermes é a memória do que já foi reportado

Jordan: *"o hermes entra como a memória do que já foi reportado, para não repetir"*.

Cada intercorrência publicada vira um CASO em `cwi_message_log` (`direction='cas'`,
`via='varredura'`), chaveado pelo `chatwoot_message_id` da mensagem de origem. Isso dá duas
coisas de uma vez:

  · **anti-repetição exata** — a mesma mensagem nunca é reportada duas vezes, sem tabela nova
  · **aprendizado** — o caso entra no mesmo acervo que alimenta o few-shot do `hermes_ponte`,
    então o que a supervisão respondeu depois vira sinal sobre o que valia a pena reportar

⚠️ Chave é o `chatwoot_message_id`, não o texto. Dois postos mandam relatórios quase idênticos
todo dia; deduplicar por conteúdo calaria o segundo posto.

## O que ele reporta, em ordem de gravidade

1. `problema_ponto` — alguém disse que não conseguiu bater
2. `pendencia` — algo ficou pendente e some se ninguém anotar
3. `solicitacao` — pediram alguma coisa a nós
4. `operacional` — ocorrência do posto (equipamento, acesso, segurança)
5. **despadronização** — o relatório de turno saiu fora do formato da casa

⚠️ `rotina` e `tom` NÃO viram intercorrência. `rotina` é a PROVA de que o posto reportou —
conta no rodapé como saúde, nunca como alarme. Um vigia que grita em tudo é um vigia que
ninguém lê, e isso já custou caro aqui.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Classes que viram intercorrência, da mais grave para a menos.
GRAVIDADE: dict[str, tuple[str, str]] = {
    "problema_ponto": ("🔴", "não conseguiu bater o ponto"),
    "pendencia": ("🟠", "ficou pendente"),
    "solicitacao": ("🟡", "pediram algo a nós"),
    "operacional": ("🔵", "ocorrência do posto"),
}

#: ⭐ O PADRÃO DO RELATÓRIO DE TURNO, derivado dos relatórios REAIS do banco — não inventado.
#: Formato que os agentes de portaria usam:
#:
#:     *Conecta Mais – Segurança e Tecnologia*
#:     *Data*: 27/09/2026
#:     *Posto*: Condomínio Mirantes das Flores
#:     *Turno*: Diurno 07:00 as 19:00 hrs.
#:     *Agente de Portaria P1* Alexandre Silva
#:     *COMUNICADO*  …  - Fica Registrado✅
#:
#: ⚠️ A régua é por CAMPO, não por texto exato: cada posto escreve com pontuação diferente
#: (`*Data*:` e `*Data:*`, "Vila" e "Villa", acento a mais ou a menos). Exigir o texto literal
#: acusaria de despadronizado quem só usou dois-pontos noutro lugar.
#: 🔴 ANCORADA NO COMEÇO, E NUNCA EM DESCRIÇÃO DE MÍDIA.
#:
#: A 1ª versão era só `conecta\s*mais` em qualquer lugar do texto — e o caçador mediu mais
#: falso positivo que acerto: de 524 mensagens que casavam em 24h, **147 eram DESCRIÇÃO DE
#: IMAGEM** ("A imagem enviada no atendimento da Conecta Mais mostra uma CNH…") e 120 eram
#: outra coisa. Só 257 eram relatório de verdade. Acusar a descrição de uma foto de ser
#: "relatório de turno despadronizado" é o caçador medindo a si mesmo.
#:
#: O relatório real SEMPRE abre com o cabeçalho em negrito, nas variações que os postos usam:
#: `*Conecta Mais – …*`, `**CONECTA MAIS – …*`, `*CONDOMÍNIO IDEAL FLORES * *Conecta Mais…`.
_ABRE_RELATORIO = re.compile(r"^\s*\*{1,2}[^\n]{0,90}conecta\s*mais", re.IGNORECASE)
#: Prefixos que o pipeline de mídia escreve. Nunca são relatório de turno.
_PREFIXO_MIDIA = ("🖼", "🎙", "📎", "🎥")
_CAMPOS_OBRIGATORIOS: dict[str, re.Pattern] = {
    "Data": re.compile(r"\*?data\*?\s*:?\*?\s*\d{1,2}[/.-]\d{1,2}", re.IGNORECASE),
    "Posto": re.compile(r"\*?posto\*?\s*:?\*?\s*\S", re.IGNORECASE),
    "Turno": re.compile(r"\*?turno\*?\s*:?\*?\s*\S", re.IGNORECASE),
    "Agente": re.compile(r"agente\s+de\s+portaria", re.IGNORECASE),
}

_SQL_NOVAS = """
SELECT m.id::text AS id, m.chatwoot_message_id AS cw_id, g.nome AS grupo, g.modo,
       m.autor_nome, m.autor_employee_id::text AS employee_id, m.classificacao,
       m.conteudo, m.quando
  FROM wa_grupo_mensagens m
  JOIN wa_grupos g ON g.jid = m.grupo_jid
 WHERE g.modo <> 'off'
   AND m.criado_em >= now() - make_interval(mins => :janela)
   AND m.chatwoot_message_id IS NOT NULL
   -- ⭐ O HERMES É A MEMÓRIA: se já existe caso desta mensagem, ela já foi reportada.
   AND NOT EXISTS (
     SELECT 1 FROM cwi_message_log c
      WHERE c.direction = 'cas' AND c.status = 'varredura'
        AND c.chatwoot_message_id = m.chatwoot_message_id)
 ORDER BY m.quando
"""


def _despadronizado(texto: str) -> list[str]:
    """Campos que FALTAM num relatório de turno. Lista vazia = está no padrão.

    ⚠️ Só se aplica a quem TENTOU o relatório (abre com "Conecta Mais"). Uma mensagem solta
    como "bom dia" não é relatório despadronizado — é conversa, e acusá-la seria transformar
    o vigia em chiclete.
    """
    t = (texto or "").lstrip()
    if t.startswith(_PREFIXO_MIDIA) or not _ABRE_RELATORIO.search(t):
        return []
    return [nome for nome, rx in _CAMPOS_OBRIGATORIOS.items() if not rx.search(texto)]


async def varrer(db: AsyncSession, *, janela_min: int = 60, publicar: bool = True,
                 teto: int = 12) -> dict[str, Any]:
    """Lê os grupos na janela, monta as intercorrências e publica no Gestão.

    ⚠️ `publicar=False` NÃO grava caso nenhum — dry run puro. Gravar num ensaio queimaria a
    novidade: a mensagem ficaria marcada como reportada sem ninguém ter sido avisado, e nunca
    mais sairia. É a mesma trava do `vigia.varrer`, e lá ela nasceu de um defeito real.
    """
    linhas = (await db.execute(text(_SQL_NOVAS), {"janela": janela_min})).mappings().all()

    incidentes: list[dict[str, Any]] = []
    rotina = 0
    for r in linhas:
        texto = r["conteudo"] or ""
        faltando = _despadronizado(texto)
        if r["classificacao"] in GRAVIDADE:
            icone, rotulo = GRAVIDADE[r["classificacao"]]
            incidentes.append({**r, "icone": icone, "rotulo": rotulo,
                               "ordem": list(GRAVIDADE).index(r["classificacao"])})
        elif faltando:
            # ⭐ DESPADRONIZAÇÃO NÃO VAI A JUÍZO. O campo está no relatório ou não está — é
            # fato mecânico, não avaliação. Na 1ª versão isto passava pelo juiz junto com o
            # resto e ele reprovou TUDO: 145 mensagens, zero incidentes. Não porque errou,
            # mas porque a rubrica dele fala de "problema a resolver" e campo faltando não é
            # problema do condomínio — é do formulário. Pedir juízo sobre o objetivo é como
            # se perde um requisito que o dono pediu com todas as letras.
            incidentes.append({**r, "icone": "⚪", "ordem": len(GRAVIDADE), "_mecanico": True,
                               "rotulo": f"relatório de turno SEM: {', '.join(faltando)}"})
        elif r["classificacao"] == "rotina":
            rotina += 1

    # ⭐ O REGEX TRIA, O JUIZ DECIDE. Sem este passo o ensaio de 27/09 publicava "o condomínio
    # segue tranquilo" como ocorrência.
    mecanicos = [i for i in incidentes if i.get("_mecanico")]
    a_julgar = [i for i in incidentes if not i.get("_mecanico")]
    juiz_ok = True
    if a_julgar:
        aprovados, porques, juiz_ok = await _julgar(a_julgar)
        for n, i in enumerate(a_julgar):
            i["_aprovado"] = n in aprovados
            if porques.get(n):
                i["rotulo"] = porques[n]
        rejeitados = [i for i in a_julgar if not i["_aprovado"]]
        a_julgar = [i for i in a_julgar if i["_aprovado"]]
        rotina += len(rejeitados)
    incidentes = a_julgar + mecanicos

    incidentes.sort(key=lambda x: (x["ordem"], x["grupo"]))
    if not incidentes:
        logger.info("varredura: %s mensagem(ns) na janela, nenhuma intercorrência (%s de rotina)",
                    len(linhas), rotina)
        return {"ok": True, "lidas": len(linhas), "incidentes": 0, "rotina": rotina,
                "juiz_respondeu": juiz_ok, "publicado": False}

    # ⚠️ TETO COM A VERDADE DITA. Cortar em silêncio faria o resumo parecer completo quando não
    # é — e "cobri tudo" mentiroso é pior que "cobri 12 de 30".
    mostrados, sobra = incidentes[:teto], max(0, len(incidentes) - teto)
    texto_msg = _texto(mostrados, sobra, rotina, janela_min, juiz_ok)

    publicado = False
    if publicar:
        from modules.integrations.connectors.whatsapp import supervisao as _sup
        from modules.integrations.connectors.whatsapp import vigia as _vig

        destino = await _vig._destino_gestao(db)
        if destino:
            publicado = bool(await _sup._publicar_no_grupo(int(destino), texto_msg))
        else:
            logger.warning("varredura: sem grupo de relatório — %d incidente(s) NÃO publicados",
                           len(incidentes))

    # Só vira memória depois de SAIR. Ver o docstring de `publicar=False`.
    if publicado:
        for i in mostrados:
            await db.execute(text(
                "INSERT INTO cwi_message_log (direction, phone_canonical, "
                "  chatwoot_message_id, content, status) "
                "VALUES ('cas', NULL, :cw, :corpo, 'varredura')"),
                {"cw": i["cw_id"],
                 "corpo": f'{{"p": {_json(i["conteudo"][:400])}, '
                          f'"r": {_json(i["rotulo"])}, "g": {_json(i["grupo"])}, '
                          f'"via": "varredura"}}'})
        await db.commit()

    return {"ok": True, "lidas": len(linhas), "incidentes": len(incidentes),
            "publicados": len(mostrados) if publicado else 0, "sobra": sobra,
            "rotina": rotina, "publicado": publicado, "juiz_respondeu": juiz_ok,
            "tipos": sorted({i["rotulo"] for i in mostrados})}


_RUBRICA = """Você separa INTERCORRÊNCIA de ROTINA em relatos de portaria.

INTERCORRÊNCIA é o que alguém precisa DECIDIR ou CONSERTAR hoje:
equipamento com defeito, acesso liberado sem autorização, falta de material que vai acabar,
alguém que não conseguiu bater o ponto, dano, furto, pessoa suspeita, reclamação do cliente,
agente sem render, obra irregular, risco à segurança.

ROTINA é o posto dizendo que está tudo bem, mesmo com detalhe:
"condomínio tranquilo", "lixeira sendo limpa", "churrasqueira liberada para o morador X",
"piscina com crianças e responsável", ronda concluída, foto de fachada normal, foto de
documento de visitante conferido, elevador funcionando.

⚠️ Detalhe não é problema. "A churrasqueira 01 foi liberada para a senhora Daniela" é rotina:
ninguém precisa fazer nada. "A churrasqueira foi usada sem reserva" é intercorrência.

Responda APENAS um JSON: {"incidentes": [{"i": <índice>, "porque": "<até 12 palavras>"}]}
Só inclua os índices que são intercorrência de verdade. Se nenhum for, devolva lista vazia."""


async def _julgar(candidatos: list[dict]) -> tuple[set[int], dict[int, str], bool]:
    """⭐ O JUÍZO É DE MODELO, A TRIAGEM É DE REGEX — e é aqui que o Hermes entra de verdade.

    🔴 POR QUE ISTO EXISTE. Na 1ª versão o regex decidia sozinho o que publicar, e o ensaio
    mostrou o vigia gritando *"o condomínio segue tranquilo e sem alterações"* como ocorrência,
    junto de *"a lixeira está sendo limpa"* e *"a churrasqueira foi liberada para a senhora
    Daniela"*. Isso é o defeito que o próprio docstring deste módulo proíbe: **vigia que grita
    em tudo é vigia que ninguém lê.**

    ⚠️ UMA chamada por varredura, com todos os candidatos numerados — não uma por mensagem.
    Grupo despeja 700 mensagens por dia; uma chamada cada seria custo sem fim.

    ⚠️ E o teto é ALTO de propósito: `modelo_barato()` é modelo de RACIOCÍNIO, gasta o
    orçamento pensando e devolve `content` VAZIO se o teto for curto. Em 25/09 um
    `max_tokens=300` matou o loop de aprendizado da casa por meses, sem um único erro no log.

    Devolve `(índices aprovados, motivos, juiz_respondeu)`. O terceiro valor é a honestidade:
    quando o juiz não responde, quem chama precisa SABER que está degradado.
    """
    import json as _j
    import os as _os

    from core.llm_client import modelo_barato, novo_cliente

    linhas = "\n".join(
        f'[{n}] ({c["classificacao"]}) {c["grupo"]} — {" ".join((c["conteudo"] or "").split())[:320]}'
        for n, c in enumerate(candidatos))
    try:
        client = novo_cliente(origem="whatsapp.varredura", timeout=90.0)
        model = _os.getenv("VARREDURA_MODEL") or modelo_barato()
        kw = ({"max_completion_tokens": 4000} if model.startswith(("gpt-5", "o1", "o3", "o4"))
              else {"max_tokens": 4000, "temperature": 0})
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": _RUBRICA},
                      {"role": "user", "content": linhas[:14000]}],
            **kw)
        bruto = (resp.choices[0].message.content or "").strip()
        bruto = bruto[bruto.find("{"):bruto.rfind("}") + 1] if "{" in bruto else "{}"
        dados = _j.loads(bruto or "{}")
        ok = {int(x["i"]) for x in (dados.get("incidentes") or []) if str(x.get("i","")).isdigit()
              or isinstance(x.get("i"), int)}
        porques = {int(x["i"]): str(x.get("porque") or "")[:90]
                   for x in (dados.get("incidentes") or [])
                   if isinstance(x.get("i"), int) or str(x.get("i","")).isdigit()}
        logger.info("varredura: juiz aprovou %d de %d candidatos", len(ok), len(candidatos))
        return ok, porques, True
    except Exception as exc:  # noqa: BLE001
        # ⭐ FALHA PARA O LADO SEGURO, E DIZ QUE FALHOU. Publicar tudo inundaria o Gestão;
        # publicar nada esconderia o que importa. Passa só o que a régua já considera GRAVE.
        logger.error("varredura: juiz indisponível (%s) — só o que é grave passa", exc)
        graves = {n for n, c in enumerate(candidatos)
                  if c["classificacao"] in ("problema_ponto", "pendencia")}
        return graves, {}, False


def _json(s: str) -> str:
    import json as _j
    return _j.dumps(str(s or "")[:400], ensure_ascii=False)


def _texto(incidentes: list[dict], sobra: int, rotina: int, janela_min: int,
           juiz_ok: bool = True) -> str:
    out = [f"👁 *Varredura dos grupos* — últimos {janela_min} min", ""]
    for i in incidentes:
        quem = i["autor_nome"] or "(sem nome)"
        corpo = " ".join((i["conteudo"] or "").split())
        out.append(f"{i['icone']} *{i['grupo']}* · {quem}")
        out.append(f"    _{i['rotulo']}_")
        out.append(f"    {corpo[:260]}" + ("…" if len(corpo) > 260 else ""))
    if sobra:
        out += ["", f"⚠️ *+{sobra}* não couberam nesta mensagem — vêm na próxima varredura."]
    if rotina:
        # ⭐ `rotina` no rodapé é SAÚDE, não alarme: é a prova de que os postos reportaram.
        out += ["", f"✅ {rotina} relatório(s) de rotina, sem ocorrência."]
    if not juiz_ok:
        # ⚠️ Degradação DITA. Um resumo menor por falha de juiz parecendo dia calmo é a pior
        # forma de silêncio: ninguém procura o que não sabe que faltou.
        out += ["", "⚠️ _O classificador não respondeu nesta rodada — passou só o que é grave. "
                    "Pode ter ficado coisa de fora._"]
    return "\n".join(out)
