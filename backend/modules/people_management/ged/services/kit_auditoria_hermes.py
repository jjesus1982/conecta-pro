"""O Hermes CONFERE o kit montado — o olho que a regra codificada não tem (10/09/2026).

Por que existe. Em 09 e 10/09, montando o primeiro kit REAL (Michelangelo), quatro defeitos
chegaram ao Drive do cliente sem que nada no sistema reclamasse:

  · seis GUIAS na pasta Financeiro, porque o `else` do roteamento cobria 72 de 78 tipos;
  · `dctf_declaracao_072026_b85caae8195f.pdf` como nome de arquivo na pasta que o síndico abre;
  · 231 documentos marcados "assinado" sem um PDF atrás;
  · NFS-e de janeiro e 13º de 2025 dentro do kit de agosto.

Nenhum era exceção — todos eram uma REGRA respondendo com confiança a um caso que ela não previa.
Convenção codificada à mão é a fábrica de defeito desta casa, e ela não fica vermelha sozinha:
o arquivo chega, o contador sobe, e só o olho de quem abre a pasta percebe.

O que este módulo faz. Depois do kit sincronizado, pede ao Hermes (agente da NousResearch, com as
ferramentas `ged`/`fiscal` do ERP pelo conector `mcp-ged`) que ABRA o kit pelas ferramentas e
confira contra as regras desta casa. Ele lê o Drive de verdade, compara com o que o sistema diz, e
responde JSON. O parecer vira nota no kit.

O que NÃO faz, de propósito: não move, não apaga, não renomeia nada. Calcular folha, gerar PDF e
subir arquivo continuam determinísticos em Python — passar isso por LLM só encareceria e traria
erro onde hoje não tem. O agente entra onde é JULGAMENTO: "esse documento está no lugar certo?",
"esse arquivo é da competência do kit?", "esse nome serve para o cliente?".

E é aqui que ele aprende: cada conferência é uma passagem pelo processo repetitivo, com memória
persistente entre sessões (`/data/memories/MEMORY.md`) e skills que ele mesmo escreve — as duas
atrás de aprovação humana (`write_approval: true`), que é o desenho desta casa.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

#: Desligar sem deploy quando o crédito acabar ou o agente estiver fora do ar.
HABILITADO = (os.getenv("KIT_AUDITORIA_HERMES", "true") or "").lower() not in ("false", "0", "no")

#: As regras desta casa, na língua em que foram decididas. Cada linha nasceu de um defeito medido —
#: quando uma delas mudar, muda AQUI, e não espalhada em `if` pelo código.
REGRAS_DO_KIT = """\
Regras do kit documental da Conecta Mais (decididas pelo dono, cada uma nasceu de um defeito real):

1. PASTAS. Dentro de "<AAAA-MM> Kit Documental" existem exatamente cinco:
   - Funcionarios  → tudo que é da pessoa (contracheque, folha de ponto, recibo de adiantamento,
     comprovante de pagamento, recibo de VT/VR) e os consolidados da folha.
   - Certidoes     → só certidão negativa da empresa (CND federal/estadual/municipal, CRF FGTS, CNDT).
   - Guias         → guia de recolhimento e o comprovante de pagamento dela (DARF, DCTFWeb, FGTS,
     INSS, ISS, DAS). Guia NUNCA vai para Financeiro.
   - Beneficios    → a EMPRESA comprando e distribuindo VT/VA (boleto e relatório SINETRAM,
     relatório Sólides e os comprovantes de pagamento dos dois).
   - Financeiro    → só o que a Conecta Mais COBRA do condomínio: a NFS-e e o boleto do mês.
2. COMPETÊNCIA. Todo arquivo é da competência do kit, ou da anterior quando for guia (a guia de
   agosto recolhe julho). Documento de outro ano no kit do mês é erro.
3. NOME. O nome é o que o síndico lê. Nome interno de coletor (hash ou CNPJ cru, como
   "cnd_receita_61e697a58521.pdf") não serve.
4. ESCALA de trabalho NÃO vai no kit. Folha de ponto vai.
5. ASSINATURA. Contracheque, folha de ponto, recibo de adiantamento e recibos de VT/VR são
   assinados pelo funcionário; folha de ponto e recibo de adiantamento levam TAMBÉM a assinatura
   da empresa com ICP-Brasil.
"""

_ESQUEMA = """\
Responda SOMENTE um JSON, sem cerca de código e sem texto antes ou depois, neste formato:
{
  "veredito": "ok" | "com_ressalvas" | "reprovado",
  "achados": [
    {"gravidade": "alta"|"media"|"baixa",
     "pasta": "<pasta onde está>",
     "arquivo": "<nome do arquivo>",
     "problema": "<o que está errado, em uma frase>",
     "deveria": "<onde deveria estar ou o que deveria ser>"}
  ],
  "faltando": ["<documento que o kit deveria ter e não tem>"],
  "resumo": "<duas linhas para o dono ler>"
}
Se uma ferramenta falhar, diga isso em "resumo" e devolva "veredito":"reprovado". NUNCA invente
arquivo, número ou pasta: só afirme o que veio de uma ferramenta.
"""


def _extrair_json(texto: str) -> dict[str, Any] | None:
    """O modelo às vezes embrulha o JSON em cerca de código ou prosa. Pega o primeiro objeto válido."""
    if not texto:
        return None
    limpo = re.sub(r"^\s*```(?:json)?|```\s*$", "", texto.strip(), flags=re.M)
    inicio = limpo.find("{")
    while inicio != -1:
        for fim in range(len(limpo), inicio, -1):
            try:
                obj = json.loads(limpo[inicio:fim])
            except Exception:  # noqa: BLE001, S112 — varredura: recorte inválido é o caso comum, não erro
                continue
            if isinstance(obj, dict):
                return obj
        inicio = limpo.find("{", inicio + 1)
    return None


def _competencia(ref: date) -> str:
    """O `consultar_kit` recusa 08/2026 com 422 e aceita 08.2026 — medido em 10/09."""
    return f"{ref.month:02d}.{ref.year}"


async def auditar_kit(db, kit_id: str) -> dict[str, Any]:
    """Pede ao Hermes que confira o kit e devolve o parecer. Nunca levanta: degrada com motivo."""
    from sqlalchemy import text as sql

    if not HABILITADO:
        return {"executou": False, "motivo": "KIT_AUDITORIA_HERMES desligado"}

    row = (
        await db.execute(
            sql(
                "SELECT c.name, k.reference_month, k.google_drive_link "
                "FROM ged_document_kits k JOIN ged_clients c ON c.id = k.client_id "
                "WHERE k.id = CAST(:k AS uuid)"
            ),
            {"k": kit_id},
        )
    ).first()
    if not row:
        return {"executou": False, "motivo": f"kit {kit_id} não encontrado"}
    condominio, ref, link = row[0], row[1], row[2]
    comp = _competencia(ref)

    from modules.ai.conversation.services import hermes_client

    if not await hermes_client.hermes_disponivel():
        return {"executou": False, "motivo": "Hermes fora do ar"}

    pergunta = (
        f"Confira o kit documental do condomínio {condominio} na competência {comp}.\n\n"
        f"Use as ferramentas do conector `ged`: `consultar_kit` para abrir a ficha e a lista de "
        f"arquivos por subpasta, e `cronograma_kit` se precisar saber o que já deveria estar pronto. "
        f"Confira o que as ferramentas devolverem contra as regras abaixo.\n\n{REGRAS_DO_KIT}\n{_ESQUEMA}"
    )
    sistema = (
        "Você é o conferente do kit documental da Conecta Mais. Seu trabalho é ABRIR o kit pelas "
        "ferramentas e comparar com as regras da casa. Você não move, não apaga e não renomeia nada — "
        "só relata. Prefira relatar a propor. Nunca afirme um arquivo que uma ferramenta não devolveu."
    )

    try:
        resposta, meta = await hermes_client.perguntar_hermes([{"role": "user", "content": pergunta}], sistema)
    except Exception as exc:  # noqa: BLE001 — o parecer é um extra; kit montado não pode cair por isso
        logger.warning("auditoria Hermes do kit %s falhou: %s", kit_id, exc)
        return {"executou": False, "motivo": f"{type(exc).__name__}: {exc}"}

    parecer = _extrair_json(str(resposta))
    if parecer is None:
        return {
            "executou": False,
            "motivo": "resposta do Hermes não trouxe JSON",
            "bruto": str(resposta)[:500],
            "tokens": (meta or {}).get("tokens"),
        }

    achados = parecer.get("achados") or []
    parecer.update(
        {
            "executou": True,
            "kit_id": kit_id,
            "condominio": condominio,
            "competencia": comp,
            "link": link,
            "tokens": (meta or {}).get("tokens"),
        }
    )

    # O parecer vira NOTA no kit: quem abrir o kit amanhã lê o que o conferente viu hoje.
    nota = (
        f"[conferência Hermes {date.today():%d/%m/%Y}] {parecer.get('veredito', '?')} — "
        f"{parecer.get('resumo', '')}\n"
        + "\n".join(
            f"  · {a.get('pasta')}/{a.get('arquivo')}: {a.get('problema')} (deveria: {a.get('deveria')})"
            for a in achados[:20]
        )
    )
    try:
        await db.execute(
            sql(
                "UPDATE ged_document_kits SET notes = coalesce(notes || E'\\n\\n', '') || :n, "
                "updated_at = now() WHERE id = CAST(:k AS uuid)"
            ),
            {"n": nota, "k": kit_id},
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("não gravei a nota da conferência no kit %s: %s", kit_id, exc)

    logger.info(
        "conferência Hermes do kit %s (%s %s): %s · %d achado(s) · %s tokens",
        kit_id,
        condominio,
        comp,
        parecer.get("veredito"),
        len(achados),
        parecer.get("tokens"),
    )
    return parecer


# ── FASE DE TREINAMENTO (10/09/2026, decisão do Jordan) ───────────────────────────────────────
# "estamos na fase de treinamento e aprendizado do Hermes... vamos montar e ele aprende, depois ele
# monta os reais."
#
# O agente só aprende com o que ELE FAZ: memória e skill são escritas pelas ferramentas dele, no
# fim de uma passagem pelo processo. Aqui a passagem é o fechamento de um kit — o processo mais
# repetitivo desta casa, treze vezes por mês.
#
# As duas escritas caem em `/data/pending/` e ESPERAM aprovação humana (`write_approval: true` no
# config). É de propósito: numa casa onde o agente mexe em folha e contrato, procedimento que ele
# escreve sozinho vira regra sozinho. Quem aprova é o Jordan.

_PEDIDO_DE_APRENDIZADO = """\
Você acabou de conferir este kit. Agora REGISTRE o que aprendeu, para a próxima vez ser melhor.

1. Use a ferramenta `memory` para gravar os FATOS desta casa que você descobriu ou confirmou agora —
   coisas que valem para todo kit, não só para este condomínio. Uma entrada por fato, curta.
2. Use a ferramenta `skill_manage` (action=create ou edit) para escrever/atualizar a skill
   `conferir-kit-documental`: o PROCEDIMENTO de conferir um kit da Conecta Mais — que ferramenta
   chamar, em que ordem, o que olhar em cada pasta, e os erros que você já viu acontecer.

Não invente regra que ninguém te disse. Se algo te pareceu errado mas você não tem certeza, escreva
como DÚVIDA na memória, não como regra. Responda em UMA linha o que gravou.
"""


async def aprender_com_o_kit(db, kit_id: str, parecer: dict | None = None) -> dict:
    """Depois de conferir, o Hermes registra o que aprendeu. Escrita fica pendente de aprovação."""
    from sqlalchemy import text as sql

    if not HABILITADO:
        return {"executou": False, "motivo": "KIT_AUDITORIA_HERMES desligado"}
    row = (
        await db.execute(
            sql(
                "SELECT c.name, k.reference_month FROM ged_document_kits k JOIN ged_clients c ON c.id = k.client_id "
                "WHERE k.id = CAST(:k AS uuid)"
            ),
            {"k": kit_id},
        )
    ).first()
    if not row:
        return {"executou": False, "motivo": f"kit {kit_id} não encontrado"}

    from modules.ai.conversation.services import hermes_client

    if not await hermes_client.hermes_disponivel():
        return {"executou": False, "motivo": "Hermes fora do ar"}

    contexto = (
        f"Kit conferido: {row[0]}, competência {_competencia(row[1])}.\n"
        f"Seu parecer foi: {json.dumps(parecer or {}, ensure_ascii=False)[:2500]}\n\n"
        f"{REGRAS_DO_KIT}\n{_PEDIDO_DE_APRENDIZADO}"
    )
    try:
        resposta, meta = await hermes_client.perguntar_hermes(
            [{"role": "user", "content": contexto}],
            "Você é o conferente do kit documental da Conecta Mais, em treinamento. Registre o que "
            "aprendeu usando suas ferramentas de memória e de skill. Fato é fato; palpite é dúvida.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("aprendizado do Hermes no kit %s falhou: %s", kit_id, exc)
        return {"executou": False, "motivo": f"{type(exc).__name__}: {exc}"}
    logger.info("aprendizado do Hermes no kit %s: %s", kit_id, str(resposta)[:200])
    return {
        "executou": True,
        "kit_id": kit_id,
        "condominio": row[0],
        "registrou": str(resposta)[:600],
        "tokens": (meta or {}).get("tokens"),
        "observacao": "as escritas ficam em /data/pending do Hermes até o Jordan aprovar",
    }
