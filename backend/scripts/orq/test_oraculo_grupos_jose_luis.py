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

        # ── 3 · grupo NOVO: cala, entra OBSERVANDO e SEM poder falar ──
        # ⚠️ ESTA ASSERÇÃO JÁ ESTAVA ERRADA UMA VEZ, e do jeito que eu mais critico: ela
        # afirmava `cfg is None` — a FOTOGRAFIA de quando grupo novo era ignorado sem registro.
        # Em 24/09 o Jordan autorizou os grupos dos postos em bloco, a descoberta passou a
        # auto-cadastrar em `observar`, e o oráculo ficou VERMELHO sobre comportamento correto.
        # Oráculo que reprova uma melhoria é oráculo que vai ser desligado.
        #
        # A REGRA, que sobrevive à mudança: grupo novo CALA, nasce sem permissão de falar
        # (`max_falas_dia = 0`) e não vira `falar` sozinho. O que muda é o registro; o que não
        # muda é que ninguém ganha voz por ser adicionado a um grupo.
        #
        # ⚠️ E ele POLUIU a tabela de produção: o payload usava `name="T"`, e um grupo chamado
        # "T" apareceu no cadastro junto dos condomínios reais. Teste que escreve em produção
        # limpa o que escreveu — daí o `finally`.
        fantasma = f"1203639{uuid.uuid4().int % 10**11}@g.us"
        try:
            calar, visto, cfg = await grp.deve_calar(db, _payload(fantasma, "trocar plantao", -1))
            assert calar is True, "grupo novo tem de CALAR"
            if cfg:
                assert cfg["modo"] != "falar", "grupo novo nasceu podendo falar — nunca"
                assert int(cfg.get("max_falas_dia") or 0) == 0, \
                    "grupo novo nasceu com cota de fala — em grupo de condomínio há cliente dentro"
            n = (await db.execute(text("SELECT count(*) FROM wa_grupo_mensagens WHERE grupo_jid = :j"),
                                  {"j": fantasma})).scalar()
            assert n == 0, "grupo novo absorveu mensagem na descoberta — descobrir não é absorver"
            print("OK grupo novo: cala, observa e NÃO pode falar")
        finally:
            await db.execute(text("DELETE FROM wa_grupos WHERE jid = :j"), {"j": fantasma})
            await db.commit()

        # ── 3b · o EX-CLIENTE continua fora, e isso é decisão do dono ──
        rp = (await db.execute(text(
            "SELECT modo, max_falas_dia FROM wa_grupos WHERE nome ILIKE '%river park%'"))).first()
        if rp:
            assert rp[0] == "off" and int(rp[1] or 0) == 0, (
                "o grupo do River Park saiu de `off` — a Conecta Mais não trabalha mais neste "
                "condomínio (Jordan, 24/09/2026) e ele não pode ser absorvido nem respondido")
            print("OK River Park (ex-cliente) segue em `off`")

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

        # ── 6 · A SEGUNDA PORTA: `processar_incoming` recusa conversa de grupo ──
        # ⭐ Esta é a asserção que nasceu de um defeito REAL, não de imaginação (24/09/2026).
        # A parede do webhook estava certa, a mensagem do Jordan no Gestão foi absorvida
        # certa, e quatro minutos depois o José Luís redigiu resposta: `varrer_sem_resposta`
        # reenfileira `processar_incoming` sem passar pelo webhook. Um beat cujo propósito é
        # garantir que silêncio nunca aconteça, contra uma parede cujo propósito é garantir
        # que ele sempre aconteça.
        #
        # Então o oráculo afirma o PONTO COMPARTILHADO, não o webhook: toda conversa mapeada a
        # grupo não-`falar` tem de ser reconhecida como calada. E a irmã do caminho feliz:
        # conversa que NÃO é grupo não pode ser calada, senão eu silenciei cliente.
        mapeadas = (await db.execute(text(
            "SELECT chatwoot_conversation_id, nome, modo FROM wa_grupos "
            " WHERE chatwoot_conversation_id IS NOT NULL"))).all()
        assert mapeadas, ("nenhum grupo mapeado a conversa do Chatwoot — a trava de "
                          "`processar_incoming` não tem o que consultar e a varredura volta a furar")
        for conv, nome, modo in mapeadas:
            calado = await grp.conversa_e_grupo_calado(db, conv)
            if modo == "falar":
                assert calado is None, f"grupo {nome!r} em modo falar não deveria ser calado"
            else:
                assert calado, (f"conversa {conv} é o grupo {nome!r} em {modo!r} e NÃO foi "
                                f"reconhecida — `varrer_sem_resposta` responderia nele")
        # o controle: um id de conversa que não é grupo nenhum
        livre = max(c for c, _, _ in mapeadas) + 100000
        assert await grp.conversa_e_grupo_calado(db, livre) is None, \
            "conversa que não é grupo foi calada — isto silenciaria cliente"
        print(f"OK processar_incoming recusa as {len(mapeadas)} conversas de grupo, e só elas")

        # ── 7 · a varredura não mira grupo (senão grita 'SEM resposta' para sempre) ──
        from modules.integrations.connectors.whatsapp import tasks as _tk  # noqa: PLC0415
        assert "wa_grupos" in _tk.varrer_sem_resposta.__doc__ or True  # doc é livre
        import inspect  # noqa: PLC0415
        fonte = inspect.getsource(_tk.varrer_sem_resposta)
        assert "wa_grupos" in fonte, (
            "`varrer_sem_resposta` voltou a não excluir grupo: cada mensagem de grupo vira "
            "WARNING 'SEM resposta' por rodada durante 90min, sobre algo que está certo")
        print("OK varrer_sem_resposta exclui grupo em observação")

    print("TEST oraculo_grupos_jose_luis PASS")


if __name__ == "__main__":
    asyncio.run(main())
