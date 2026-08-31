"""Entrevista de levantamento — o agente PERGUNTA, uma por vez, e grava em campo.

31/08/2026. Jordan: *"isso tudo quem tinha que perguntar era o bartolo e o josé luis. temos
que treinar eles para agirem como consultores, analistas de segurança eletrônica e
patrimonial, e ir registrando cada resposta a cada pergunta, fazer uma pergunta por vez"*.

A crítica é justa: no dia inteiro de hoje, quem perguntou "qual cabo?", "existe infra?",
"aproveita o rack?" foi um HUMANO. O agente foi espectador do próprio levantamento.

⭐ O questionário abaixo NÃO foi inventado: é a transcrição do que de fato se perguntou
hoje, e cada linha provou que importa porque cada uma mudou a cotação ou o dimensionamento.
Checklist escrito do zero descreve o projeto imaginado; este descreve o real.

TRÊS REGRAS QUE VÊM DO DIA:

1. **UMA pergunta por vez.** Não é estilo: é o que funciona com ele. Responde em rajada,
   curto, do celular. Uma parede de dez perguntas volta com uma resposta — e hoje as doze
   foram respondidas porque foram feitas uma a uma.
2. **Ordem por VALOR DE DESTRAVE**, não por ordem de lista. "Quantos pontos de concentração"
   destrava quatro itens; "dias de gravação" destrava um. Pergunta o de quatro primeiro.
3. **Nunca perguntar o que já foi respondido.** É o pior defeito possível aqui — mata a
   confiança na primeira conversa. Por isso a pergunta só nasce depois de LER `parametros`.

E a pergunta sabe DE QUEM é a resposta: campo (medição), síndica (decisão do cliente),
fornecedor (spec técnica) ou o Jordan (decisão comercial). Perguntar a ele algo que só a
síndica sabe é ruído.
"""
from __future__ import annotations

from sqlalchemy import text

#: Cada entrada: o parâmetro que ela preenche, de quem é a resposta, e o que destrava.
#: `destrava` é a lista de itens de material que ficam bloqueados enquanto ela não vier —
#: é o que ordena a fila, e é medido, não opinado.
QUESTIONARIO: tuple[dict, ...] = (
    {"param": "racks", "dono": "campo",
     "pergunta": "Quantos pontos de concentração (racks) o projeto vai ter? "
                 "Contando o da administração, que já existe.",
     "porque": "é a incógnita que trava mais coisa no orçamento",
     "destrava": ("Rack", "Nobreak", "Switch GIGA", "Cabo")},
    {"param": "nobreak_rack_administracao", "dono": "campo",
     "pergunta": "O rack de 16U da administração já tem nobreak? "
                 "Se já tiver, não precisa comprar um para ele.",
     "porque": "muda a quantidade de nobreak", "destrava": ("Nobreak",)},
    {"param": "dias_gravacao", "dono": "síndica",
     "pergunta": "Quantos dias de gravação o condomínio quer guardar? "
                 "É o que define o tamanho do HD.",
     "porque": "dimensiona a capacidade de armazenamento", "destrava": ("HD de vigilância",)},
    {"param": "metragem_cabo", "dono": "campo",
     "pergunta": "Qual a metragem estimada de cabo? "
                 "Backbone entre os racks mais a descida de cada câmera.",
     "porque": "não existe regra que produza metros sem medir", "destrava": ("Cabo",)},
    {"param": "metragem_eletrocalha", "dono": "campo",
     "pergunta": "Qual a metragem de eletrocalha/eletroduto? A infra é nova, então entra tudo.",
     "porque": "acompanha o cabo", "destrava": ("Eletrocalha",)},
)


def _respondido(params: dict, chave: str) -> bool:
    d = (params or {}).get(chave) or {}
    return isinstance(d, dict) and d.get("valor") is not None and bool(d.get("origem"))


async def proxima_pergunta(db, visit_report_id: str) -> dict | None:
    """A pergunta ABERTA de maior valor de destrave, ou None se não há o que perguntar.

    Ordena por quantos itens ela destrava — decrescente. Empate mantém a ordem do
    questionário, que já reflete a ordem em que as coisas importaram na prática.
    """
    params = (await db.execute(text(
        "SELECT coalesce(parametros,'{}'::jsonb) FROM crm_visit_reports WHERE id::text = :i"),
        {"i": visit_report_id})).scalar() or {}
    abertas = [q for q in QUESTIONARIO if not _respondido(params, q["param"])]
    if not abertas:
        return None
    abertas.sort(key=lambda q: -len(q["destrava"]))
    q = dict(abertas[0])
    q["abertas_restantes"] = len(abertas)
    return q


async def registrar_resposta(db, visit_report_id: str, param: str, valor,
                             origem: str) -> dict:
    """Grava a resposta em CAMPO (jsonb), com origem. Nunca em prosa.

    ⚠️ `origem` é obrigatória e não tem default. Um valor sem origem é ignorado pelo
    dimensionador de propósito — número sem origem é palpite com cara de fato.
    """
    if not origem or not str(origem).strip():
        return {"erro": "toda resposta precisa de ORIGEM (quem disse e quando)."}
    conhecidos = {q["param"] for q in QUESTIONARIO}
    if param not in conhecidos:
        return {"erro": f"{param!r} não está no questionário. Conhecidos: "
                        f"{', '.join(sorted(conhecidos))}"}
    r = await db.execute(text(
        "UPDATE crm_visit_reports "
        # asyncpg não infere o tipo de um bind dentro de jsonb_build_object
        # (IndeterminateDatatypeError). Montar o objeto inteiro como texto e cast UMA vez
        # resolve, e mantém valor e origem sempre juntos — parâmetro sem origem não existe.
        "SET parametros = coalesce(parametros,'{}'::jsonb) || cast(:obj as jsonb), "
        "    updated_at = now() "
        "WHERE id::text = :i RETURNING cliente_nome"),
        {"obj": __import__("json").dumps({param: {"valor": valor, "origem": origem}}),
         "i": visit_report_id})
    row = r.first()
    if row is None:
        return {"erro": f"não achei a visita {visit_report_id!r}"}
    await db.commit()
    return {"status": "gravado", "obra": row[0], "parametro": param, "valor": valor}


async def placar(db, visit_report_id: str) -> dict:
    """Quantas respostas faltam e quantos itens estão travados nelas."""
    from modules.crm.services.dimensionador import dimensionar_visita  # noqa: PLC0415

    params = (await db.execute(text(
        "SELECT coalesce(parametros,'{}'::jsonb) FROM crm_visit_reports WHERE id::text = :i"),
        {"i": visit_report_id})).scalar() or {}
    abertas = [q for q in QUESTIONARIO if not _respondido(params, q["param"])]
    d = await dimensionar_visita(db, visit_report_id)
    travados = [l["item"] for l in d.get("linhas", []) if l["quantidade"] is None]
    return {"perguntas_abertas": len(abertas), "itens_travados": len(travados),
            "travados": travados,
            "respondidas": len(QUESTIONARIO) - len(abertas), "total": len(QUESTIONARIO)}
