"""A parede de grupo do José Luís continua fechada, e o pedido de escala continua virando aprovação.

Por que existe. Em 23/09/2026 o Jordan pôs o José Luís em três grupos e pediu silêncio. O
silêncio é uma PAREDE no webhook (`grupos.deve_calar`), não instrução de prompt — e parede se
remove sem ninguém notar, porque remover não quebra nada visível: o agente simplesmente começa a
responder no grupo, que é exatamente o que o dono não quer. Nenhum teste de unidade pega isso;
só uma asserção sobre o COMPORTAMENTO pega.

⭐ Afirma a REGRA, não a fotografia:

- não fixa os três JIDs de hoje (grupo entra e sai) — afirma que **todo** grupo cadastrado em
  modo `observar` cala, e que grupo **não cadastrado** cala E não absorve;
- não fixa o nome do Orlailson — afirma que quem tem `users.role` de supervisão E vínculo vivo
  vira papel `supervisor`, e quem não tem, não;
- não conta mensagens (o volume muda todo dia) — afirma o invariante: `tom` nunca é `relevante`.

⚠️ A armadilha que este oráculo evita de propósito: importar `grupos` e testar só que
`deve_calar` devolve True. Isso é o oráculo cúmplice de 8/8 verde sobre capacidade morta — mede a
RECUSA e nunca o caminho feliz. Aqui toda recusa tem a irmã: o grupo `observar` cala **e**
absorve; o não cadastrado cala **e não** absorve. As duas direções, senão é meia trava.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from core.database import async_session_factory  # noqa: E402
from sqlalchemy import text  # noqa: E402


def _payload(jid: str, conteudo: str, mid: int, fone: str = "92981386006") -> dict:
    return {
        "event": "message_created", "message_type": "incoming", "content": conteudo, "id": mid,
        "conversation": {"id": 1, "meta": {"sender": {"identifier": jid, "name": "T"}}},
        "sender": {"identifier": jid, "name": "T",
                   "additional_attributes": {"participant": fone, "participant_name": "T"}},
    }


async def main() -> None:
    from modules.integrations.connectors.whatsapp import grupos as grp
    from modules.integrations.connectors.whatsapp import supervisao as sup

    async with async_session_factory() as db:
        # ── 1 · grupo cadastrado em `observar`: cala E absorve (as duas direções) ──
        obs = (await db.execute(text(
            "SELECT jid, nome FROM wa_grupos WHERE modo = 'observar' ORDER BY nome LIMIT 1"))).first()
        assert obs, "nenhum grupo em modo observar — a frente do José Luís foi desligada?"
        jid, nome = obs[0], obs[1]

        mid = -abs(uuid.uuid4().int % 10**8)  # id NEGATIVO: não colide com id real do Chatwoot
        try:
            calar, visto, cfg = await grp.deve_calar(db, _payload(jid, "faltou no posto hoje", mid))
            assert calar is True, f"grupo {nome!r} em observar NÃO calou — o agente responderia lá"
            assert visto == jid and cfg, "a parede não reconheceu o grupo cadastrado"

            gravou = await grp.absorver(db, jid=jid, conteudo="faltou no posto hoje",
                                        chatwoot_message_id=mid, autor_fone=None, autor_nome="oraculo")
            assert gravou, "calou mas NÃO absorveu — observador que não aprende é só censura"
            print(f"OK grupo {nome!r} em observar: cala e absorve")

            # ── 2 · o invariante do tom: conversa nunca é dado relevante ──
            ruim = (await db.execute(text(
                "SELECT count(*) FROM wa_grupo_mensagens WHERE classificacao = 'tom' AND relevante"))).scalar()
            assert ruim == 0, f"{ruim} mensagens de TOM marcadas como relevantes — tom viraria ficha"
            print("OK tom nunca é relevante (invariante, não contagem)")
        finally:
            await db.execute(text("DELETE FROM wa_grupo_mensagens WHERE chatwoot_message_id = :m"),
                             {"m": mid})
            await db.commit()

        # ── 3 · grupo NÃO cadastrado: cala E não absorve ──
        fantasma = f"1203639{uuid.uuid4().int % 10**11}@g.us"
        calar, visto, cfg = await grp.deve_calar(db, _payload(fantasma, "trocar plantao", -1))
        assert calar is True and cfg is None, "grupo não cadastrado tem de calar com cfg None"
        n = (await db.execute(text("SELECT count(*) FROM wa_grupo_mensagens WHERE grupo_jid = :j"),
                              {"j": fantasma})).scalar()
        assert n == 0, "grupo não cadastrado absorveu mensagem — é o River Park entrando"
        print("OK grupo não cadastrado: cala e NÃO absorve")

        # ── 4 · pedido de escala é reconhecido, e relato do passado NÃO é ──
        assert sup.classificar_pedido("preciso trocar meu plantao de sabado"), "pedido de troca não reconhecido"
        assert sup.classificar_pedido("nao vou poder ir amanha"), "falta anunciada não reconhecida"
        assert sup.classificar_pedido("ontem o Eduardo cobriu o plantao") is None, \
            "relato do PASSADO virou pedido — abriria rascunho para coisa já resolvida"
        assert sup.classificar_pedido("o portao esta com defeito") is None, \
            "defeito de equipamento virou pedido de escala"
        print("OK classificador de pedido: reconhece pedido, ignora relato e defeito")

        # ── 5 · supervisão vem do RBAC, e a conta sem vínculo vivo NÃO passa ──
        # Afirma a REGRA: existe pelo menos um supervisor alcançável, e toda conta com papel de
        # supervisão cujo colaborador perdeu o vínculo é barrada. Não fixa nome de pessoa.
        contas = (await db.execute(text(
            "SELECT u.employee_id, u.name, e.status FROM users u "
            "  JOIN employees e ON e.id = u.employee_id "
            " WHERE u.is_active AND u.role = ANY(:p)"), {"p": list(sup.PAPEIS_SUPERVISAO)})).all()
        assert contas, "nenhuma conta com papel de supervisão — o Orlailson perderia a visão"

        from modules.integrations.connectors.whatsapp.identidade import quem_e
        vivos = 0
        for emp, quem, status in contas:
            ident = await quem_e(db, (await db.execute(text(
                "SELECT telefone FROM employees WHERE id = :e"), {"e": str(emp)})).scalar() or "")
            papel = await sup.papel_de_supervisao(db, ident)
            if status in ("inativo", "candidato", "pj_pendente"):
                assert papel is None, (
                    f"{quem} tem conta de supervisão e colaborador {status} — e PASSOU. "
                    f"As duas condições viraram uma.")
            elif papel:
                vivos += 1
        assert vivos >= 1, "nenhum supervisor com vínculo vivo resolveu — a visão da operação caiu"
        print(f"OK supervisão pelo RBAC: {vivos} com vínculo vivo, contas sem vínculo barradas")

    print("TEST oraculo_grupos_jose_luis PASS")


if __name__ == "__main__":
    asyncio.run(main())
