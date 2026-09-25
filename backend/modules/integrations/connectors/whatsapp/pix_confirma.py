"""Coleta de confirmação de chave PIX, um a um, pelo José Luís.

POR QUE EXISTE — o mecanismo, não a suspeita: **chave CPF liquida em banco DORMENTE.** Está
escrito no histórico do próprio José Luís, 18/09/2026, pela pessoa que sofreu: *"o pix foi
direcionado pra conta do next, que a anos também não usava, fui na agência e consegui ver lá
tudo certinho"*. O `endToEndId` existe, o extrato do Inter diz que pagou, e a pessoa nunca viu
o dinheiro.

Isso derruba o critério de evidência óbvio. Eu havia tratado "tem e2e no extrato" como prova de
que a chave era boa — **liquidar não é chegar**. A chave de CPF é a que qualquer banco reivindica
primeiro, muitas vezes anos atrás, numa conta que a pessoa abandonou. A chave de telefone é a
que ela registrou por vontade própria, no banco que usa hoje.

⚠️ **A RESPOSTA NUNCA É APLICADA POR ESTE MÓDULO.** Chave PIX é destino de dinheiro. Aplicar
automaticamente o que chega por WhatsApp daria a qualquer um com acesso a um telefone o poder de
redirecionar salário — e a resposta ensinaria como fazer. Aqui se GUARDA; `aplicar()` exige um
aprovador humano e é chamada de fora, por quem tem papel de financeiro.
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Pausa entre mensagens. 67 envios instantâneos marcam o número como spam, e perder o número do
# José Luís derruba grupos, rotina de turno e coleta de ponto junto. 5s → ~6min para a operação
# toda, que é barato comparado ao risco.
PAUSA_ENTRE_ENVIOS_S = 5.0

_CONFIRMA_ATUAL = re.compile(
    r"\b(sim|isso|correto|confirmo|confirmado|certo|esse|essa|este|mesmo|ok|positivo|"
    r"ta certo|esta certo|e esse|e essa|continua)\b",
    re.I,
)
# "não" isolado, "nao é", "negativo", "errado" — nunca dentro de outra palavra ("naonada").
_NEGA = re.compile(r"(?<![a-z])(nao|negativo|errad[ao]|mudou|trocou|outra conta)(?![a-z])", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_EVP = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)


def _sem_acento(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()


def chave_do_texto(txt: str) -> tuple[str | None, str | None]:
    """Extrai (chave, tipo) do que a pessoa escreveu. Devolve (None, None) se não achou.

    ⚠️ **11 dígitos é CPF e celular ao mesmo tempo** e nenhuma heurística resolve isso sozinha.
    Quando a pessoa não diz qual é, devolvo a chave com tipo `None` — ambíguo vira decisão
    humana, nunca chute. Chutar aqui manda salário para o lugar errado com aparência de acerto.
    """
    t = _sem_acento(txt or "")
    if not t.strip():
        return None, None

    if m := _EVP.search(t):
        return m.group(0), "evp"
    if m := _EMAIL.search(t):
        return m.group(0).lower(), "email"

    # o que a pessoa CHAMOU a chave — a palavra dela ganha do formato
    disse_tel = bool(re.search(r"\b(telefone|celular|fone|numero|whats|zap)\b", t, re.I))
    disse_cpf = bool(re.search(r"\bcpf\b", t, re.I))

    # +55… declarado é inequívoco
    if m := re.search(r"\+\s*55\s*[\d\s().-]{10,15}", t):
        d = re.sub(r"\D", "", m.group(0))
        return "+" + d, "telefone"

    # maior sequência de dígitos da mensagem (a pessoa costuma mandar só a chave)
    cands = [re.sub(r"\D", "", g) for g in re.findall(r"[\d\s().-]{10,}", t)]
    cands = [c for c in cands if len(c) in (10, 11, 13, 14)]
    if not cands:
        return None, None
    d = max(cands, key=len)

    if len(d) == 14:
        return d, "cnpj"
    if len(d) == 13 and d.startswith("55"):
        return "+" + d, "telefone"
    if len(d) == 10:
        return "+55" + d, "telefone"
    if len(d) == 11:
        if disse_tel and not disse_cpf:
            return "+55" + d, "telefone"
        if disse_cpf and not disse_tel:
            return d, "cpf"
        # começa com DDD do AM e 9 na sequência: indício, NÃO prova. Tipo fica None.
        return d, None
    return None, None


def confirmou_o_atual(txt: str) -> bool:
    """A pessoa disse 'sim, é essa' — e NÃO mandou chave nova."""
    chave, _ = chave_do_texto(txt)
    if chave:
        return False
    return bool(_CONFIRMA_ATUAL.search(_sem_acento(txt or "")))


async def _mandar(telefone: str | None, msg: str) -> bool:
    """True SÓ quando o serviço afirmou `status='sent'`. Ausência de erro não é entrega.

    🔴 A 1ª versão fazia `not (r.get("status") == "error")` — recusava só a falha NOMEADA. Mas
    `_send_message` devolve QUATRO formas: `sent`, `error`, `exception` e `disabled`. As duas
    últimas passavam como sucesso.

    Medido no disparo real de 25/09: quatro telefones fabricados (`92999990001/2/3/7`) ficaram
    `aguardando` — ou seja, "perguntamos e estamos esperando" — e **nenhuma mensagem saiu**
    (zero registro de `out` no `cwi_message_log`). Os outros oito devolveram `error` nomeado e
    foram corretamente para `nao_avisado`.

    O efeito é o que o `nao_avisado` existe para impedir, entrando por baixo: a pessoa que nunca
    recebeu a pergunta é contada como quem não respondeu. Na rotina de turno isso a reporta como
    OMISSA ao Jordan. Campo/estado não previsto tem de falhar FECHADO.
    """
    if not telefone:
        return False
    try:
        from modules.integrations.connectors.whatsapp.service import whatsapp_service  # noqa: PLC0415

        r = await whatsapp_service.send_custom(str(telefone), msg)
        if isinstance(r, dict) and r.get("status") == "sent":
            return True
        logger.error("pix_confirma: NÃO entregue para %s — resposta do serviço: %s",
                     telefone, (r if isinstance(r, dict) else type(r).__name__))
        return False
    except Exception as e:  # noqa: BLE001
        logger.error("pix_confirma: envio falhou para %s (%s)", telefone, e)
        return False


def mascarar(chave: str | None) -> str:
    """Mostra o suficiente para a pessoa RECONHECER a própria chave, e nada útil para um estranho.

    ⚠️ A 1ª versão mandava a chave inteira. Se o `celular` do cadastro estiver velho — e está,
    em parte da base —, isso entrega o CPF de uma pessoa ao telefone de outra. Mascarado, quem
    é dono reconhece e quem não é não aprende nada.
    """
    c = (chave or "").strip()
    if not c:
        return ""
    if "@" in c:
        u, _, d = c.partition("@")
        return f"{u[:2]}{'•' * max(len(u) - 2, 2)}@{d}"
    dig = "".join(ch for ch in c if ch.isdigit())
    if len(dig) >= 4:
        return f"{'•' * (len(dig) - 4)}{dig[-4:]}" if not c.startswith("+") else f"+55 •••••{dig[-4:]}"
    return "•" * len(c)


def _texto(primeiro: str, chave: str | None, tipo: str | None) -> str:
    cabeca = (
        f"Oi {primeiro}! Aqui é o *José Luís*, assistente da *Conecta Mais*. 👋\n\n"
        "Estamos conferindo a *chave PIX* de todo mundo. Teve caso de pagamento cair numa conta "
        "antiga que a pessoa não usava mais — o dinheiro sai daqui, o banco diz que pagou, e a "
        "pessoa não vê. Queremos evitar que aconteça com você."
    )
    if chave:
        rotulo = {"cpf": "seu CPF", "telefone": "seu telefone", "email": "seu e-mail",
                  "cnpj": "seu CNPJ", "evp": "uma chave aleatória"}.get((tipo or "").lower(), "esta chave")
        meio = (
            f"\n\nHoje seus pagamentos vão para uma chave que termina em *{mascarar(chave)}* "
            f"({rotulo}).\n\n"
            "É a conta que você *usa hoje*?\n"
            "• Se sim, responde *sim*.\n"
            "• Se não, me manda a chave certa — de preferência o *telefone* do banco que você usa."
        )
    else:
        meio = (
            "\n\nAqui no sistema *não tem chave PIX cadastrada* no seu nome.\n\n"
            "Me manda a chave da conta que você usa — de preferência o *telefone* do banco."
        )
    # ⚠️ As três linhas abaixo são o que separa esta mensagem de um golpe, e nenhuma é enfeite:
    #  · o limite do que eu peço (nunca senha/código) — quem pede isso não é a empresa;
    #  · uma SAÍDA que não passa por mim, com nome de pessoa real que ela conhece — golpista
    #    nenhum sobrevive a "confirma com o Paiva";
    #  · a retirada da PRESSA, que é a alavanca de todo golpe: nada muda se ela não responder.
    return cabeca + meio + (
        "\n\n_Só preciso da chave. *Nunca* peço senha, código do banco, cartão ou foto de "
        "documento — se alguém pedir isso em nome da Conecta, é golpe._\n"
        "_Se preferir não tratar por aqui, fala com o *Orlailson Paiva* pessoalmente, ou me "
        "procura no grupo. Em dúvida se sou eu mesmo? Confirma com o Paiva antes de responder._\n"
        "_Sem pressa: *nada muda* no seu pagamento até você confirmar._"
    )


async def pedir_confirmacoes(
    db: AsyncSession, *, enviar: bool = True, limite: int | None = None,
    so_cpf: bool = False, pausa: float = PAUSA_ENTRE_ENVIOS_S,
) -> dict[str, Any]:
    """Pergunta a chave PIX, um a um, a cada colaborador ativo com telefone.

    `enviar=False` monta tudo e não manda — é assim que se testa sem escrever no WhatsApp de
    dezenas de pessoas. `so_cpf=True` limita a quem tem chave de CPF (o grupo de risco).
    Idempotente por `employee_id`: rodar duas vezes não pergunta duas vezes.
    """
    filtro_cpf = "AND e.pix_key ~ '^[0-9]{11}$'" if so_cpf else ""
    rows = (await db.execute(text(f"""
        SELECT e.id::text AS id, e.nome,
               coalesce(nullif(e.celular,''), nullif(e.telefone,'')) AS telefone,
               coalesce(e.pix_key,'') AS chave, coalesce(e.pix_key_type,'') AS tipo
        FROM employees e
        WHERE e.status IN ('ativo','afastado_inss')
          AND coalesce(nullif(e.celular,''), nullif(e.telefone,'')) IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM pix_confirmacoes c
                          WHERE c.employee_id = e.id AND c.pedido_em IS NOT NULL)
          {filtro_cpf}
        ORDER BY e.nome
        {f'LIMIT {int(limite)}' if limite else ''}
    """))).mappings().all()

    enviados, falhas, pulados = 0, [], 0
    for i, r in enumerate(rows):
        primeiro = str(r["nome"] or "").split()[0].title()
        msg = _texto(primeiro, r["chave"] or None, r["tipo"] or None)

        await db.execute(text("""
            INSERT INTO pix_confirmacoes
                   (employee_id, nome, telefone, chave_atual, tipo_atual, pedido_em, status)
            VALUES (CAST(:e AS uuid), :n, :t, :k, :tp, now(), 'aguardando')
            ON CONFLICT (employee_id) DO UPDATE SET pedido_em = now(), updated_at = now()"""),
            {"e": r["id"], "n": r["nome"], "t": r["telefone"], "k": r["chave"] or None,
             "tp": r["tipo"] or None})

        if not enviar:
            pulados += 1
            continue

        if await _mandar(r["telefone"], msg):
            enviados += 1
        else:
            # ⚠️ ENVIO FALHOU ≠ PESSOA OMISSA. Sem esta marca o relatório diria "não respondeu"
            # sobre quem nunca recebeu a pergunta — culpando a pessoa pela minha falha de entrega.
            falhas.append(r["nome"])
            await db.execute(text(
                "UPDATE pix_confirmacoes SET status='nao_avisado', updated_at=now() "
                "WHERE employee_id = CAST(:e AS uuid)"), {"e": r["id"]})

        await db.commit()
        if pausa and i < len(rows) - 1:
            await asyncio.sleep(pausa)

    await db.commit()
    return {"candidatos": len(rows), "enviados": enviados, "sem_envio": pulados,
            "falhas_de_entrega": falhas}


def desambiguar_pelo_remetente(chave: str | None, tipo: str | None,
                               fone_remetente: str | None) -> tuple[str | None, str | None]:
    """11 dígitos que são o PRÓPRIO número de quem escreveu = telefone, não CPF.

    A prova estava de graça e eu não a usava: o Alan mandou `92993331840`, que é exatamente o
    WhatsApp de onde ele escreveu. Ninguém tem um CPF igual ao próprio celular. Isso resolve o
    caso ambíguo mais comum — a pessoa mandando o telefone do banco, que é o mesmo do WhatsApp.
    """
    if not chave or tipo or not fone_remetente:
        return chave, tipo
    d = "".join(c for c in chave if c.isdigit())
    if len(d) != 11:
        return chave, tipo
    rem = "".join(c for c in str(fone_remetente) if c.isdigit())
    # ⚠️ Não compare a string inteira: o MESMO celular aparece com 8 e com 9 dígitos no Brasil.
    # Medido no Alan — WhatsApp gravado `5592 9333 1840` (8, formato antigo) e a chave que ele
    # mandou `92 99333 1840` (9, com o nono dígito). Comparação literal nunca casaria.
    # Os 8 ÚLTIMOS dígitos sobreviveram à mudança de 2016; o DDD também. Comparo esses dois.
    def _ddd_e_final(x: str) -> tuple[str, str]:
        y = x[2:] if x.startswith("55") and len(x) >= 12 else x
        return (y[:2], y[-8:]) if len(y) >= 10 else ("", "")

    if _ddd_e_final(d) == _ddd_e_final(rem) != ("", ""):
        return "+55" + d, "telefone"
    return chave, tipo


async def registrar_resposta(db: AsyncSession, *, employee_id: str, texto: str,
                             fone_remetente: str | None = None) -> dict[str, Any]:
    """Guarda o que a pessoa respondeu. NÃO aplica nada — só registra."""
    atual = (await db.execute(text(
        "SELECT chave_atual, status FROM pix_confirmacoes WHERE employee_id = CAST(:e AS uuid)"),
        {"e": employee_id})).first()
    if not atual:
        return {"ok": False, "motivo": "não perguntei a esta pessoa"}

    if confirmou_o_atual(texto):
        await db.execute(text("""
            UPDATE pix_confirmacoes SET respondido_em=now(), texto_resposta=:t,
                   status='confirmou_atual', updated_at=now()
            WHERE employee_id = CAST(:e AS uuid)"""), {"e": employee_id, "t": texto[:2000]})
        await db.commit()
        return {"ok": True, "resultado": "confirmou a chave atual", "aplicar": False}

    chave, tipo = chave_do_texto(texto)
    chave, tipo = desambiguar_pelo_remetente(chave, tipo, fone_remetente)
    if not chave:
        # ⚠️ Um "não" SECO não é chave nem confirmação — é a pessoa dizendo que a chave atual
        # está errada e ainda não mandando a certa. Caso real de 25/09: o Nailson respondeu
        # "Sim" e, 7 minutos depois, "Não". Sem este ramo ele ficava gravado como quem
        # confirmou, e a chave errada seguia valendo com aparência de conferida.
        if _NEGA.search(_sem_acento(texto)):
            await db.execute(text("""
                UPDATE pix_confirmacoes SET respondido_em=now(), texto_resposta=:t,
                       chave_informada=NULL, tipo_informado=NULL, status='aguardando',
                       updated_at=now()
                WHERE employee_id = CAST(:e AS uuid)"""), {"e": employee_id, "t": texto[:2000]})
            await db.commit()
            return {"ok": True, "resultado": "disse que a chave atual NÃO é a certa — "
                                             "falta ele mandar a nova", "aplicar": False}
        await db.execute(text("""
            UPDATE pix_confirmacoes SET respondido_em=now(), texto_resposta=:t, updated_at=now()
            WHERE employee_id = CAST(:e AS uuid)"""), {"e": employee_id, "t": texto[:2000]})
        await db.commit()
        return {"ok": True, "resultado": "respondeu, mas não achei chave no texto",
                "aplicar": False}

    await db.execute(text("""
        UPDATE pix_confirmacoes SET respondido_em=now(), texto_resposta=:t,
               chave_informada=:k, tipo_informado=:tp, status='respondido', updated_at=now()
        WHERE employee_id = CAST(:e AS uuid)"""),
        {"e": employee_id, "t": texto[:2000], "k": chave, "tp": tipo})
    await db.commit()
    return {"ok": True, "resultado": "chave nova registrada para aprovação",
            "chave": chave, "tipo": tipo or "AMBÍGUO — humano decide", "aplicar": False}


async def pendentes_de_aprovacao(db: AsyncSession) -> list[dict[str, Any]]:
    """O que um humano precisa olhar: chave nova informada e ainda não aplicada."""
    rows = (await db.execute(text("""
        SELECT employee_id::text AS employee_id, nome, chave_atual, tipo_atual,
               chave_informada, coalesce(tipo_informado,'AMBIGUO') AS tipo_informado,
               respondido_em, texto_resposta
        FROM pix_confirmacoes
        WHERE status='respondido' AND chave_informada IS NOT NULL AND aplicado_em IS NULL
        ORDER BY respondido_em"""))).mappings().all()
    return [dict(r) for r in rows]


async def aplicar(db: AsyncSession, *, employee_id: str, aprovador: str) -> dict[str, Any]:
    """Grava a chave informada no cadastro. **Só quem tem papel de financeiro chama isto.**

    Não há caminho automático para cá de propósito: quem aprova não pode ser quem pede, e o
    pedido aqui chegou por WhatsApp — o canal menos verificável que existe nesta casa.
    """
    if not aprovador:
        return {"ok": False, "motivo": "aplicar exige aprovador humano identificado"}
    # ⚠️ Leitura por NOME, nunca por posição. `r[1]` aqui seria o tipo da chave; se alguém
    # reordenar o SELECT, `r[1]` passa a ser o NOME, a guarda `if not r[1]` aprova, e o cadastro
    # recebe `pix_key_type='JAIR SOARES DA ROCHA'` — em silêncio, num caminho de dinheiro.
    # O lado de lá (a tela de aprovação) lê as MESMAS chaves de `pendentes_de_aprovacao()`:
    # `chave_informada` e `tipo_informado`. Nome trocado de um lado tem de estourar, não cair
    # num padrão. (Lição trazida pelo terminal do fiscal em 25/09: `icms_situacao` × `icms_cst`
    # derrubou toda emissão de nota, e cada lado estava certo sozinho.)
    r = (await db.execute(text(
        "SELECT chave_informada, tipo_informado, nome FROM pix_confirmacoes "
        "WHERE employee_id = CAST(:e AS uuid) AND status='respondido'"),
        {"e": employee_id})).mappings().first()
    if not r or not r["chave_informada"]:
        return {"ok": False, "motivo": "não há chave informada para aplicar"}
    if not r["tipo_informado"]:
        return {"ok": False, "motivo": "tipo AMBÍGUO (11 dígitos = CPF ou celular). "
                                       "Confirme o tipo com a pessoa antes de aplicar."}
    await db.execute(text("""
        UPDATE employees SET pix_key=:k, pix=:k, pix_key_type=:tp, updated_at=now()
        WHERE id = CAST(:e AS uuid)"""),
        {"e": employee_id, "k": r["chave_informada"], "tp": r["tipo_informado"]})
    await db.execute(text("""
        UPDATE pix_confirmacoes SET status='aplicado', aplicado_em=now(), aplicado_por=:a,
               updated_at=now() WHERE employee_id = CAST(:e AS uuid)"""),
        {"e": employee_id, "a": aprovador[:100]})
    await db.commit()
    return {"ok": True, "nome": r["nome"], "chave": r["chave_informada"],
            "tipo": r["tipo_informado"], "aprovador": aprovador}


async def estado(db: AsyncSession) -> dict[str, Any]:
    rows = (await db.execute(text(
        "SELECT status, count(*) FROM pix_confirmacoes GROUP BY 1"))).all()
    return {"por_status": {s: n for s, n in rows}}
