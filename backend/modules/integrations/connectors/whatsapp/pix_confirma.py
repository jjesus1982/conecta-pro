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
    if not telefone:
        return False
    try:
        from modules.integrations.connectors.whatsapp.service import whatsapp_service  # noqa: PLC0415

        r = await whatsapp_service.send_custom(str(telefone), msg)
        return not (isinstance(r, dict) and r.get("status") == "error")
    except Exception as e:  # noqa: BLE001
        logger.error("pix_confirma: envio falhou para %s (%s)", telefone, e)
        return False


def _texto(primeiro: str, chave: str | None, tipo: str | None) -> str:
    cabeca = (
        f"Oi {primeiro}! Aqui é o José Luís, da Conecta Mais. 👋\n\n"
        "Estamos conferindo a *chave PIX* de todo mundo, porque teve caso de pagamento cair "
        "numa conta antiga que a pessoa não usava mais — o dinheiro sai daqui, o banco diz que "
        "pagou, e a pessoa não vê. Queremos evitar que isso aconteça com você."
    )
    if chave:
        rotulo = {"cpf": "seu CPF", "telefone": "seu telefone", "email": "seu e-mail",
                  "cnpj": "seu CNPJ", "evp": "uma chave aleatória"}.get((tipo or "").lower(), "esta chave")
        meio = (
            f"\n\nHoje seus pagamentos vão para *{chave}* ({rotulo}).\n\n"
            "Essa é a chave da conta que você *usa hoje*?\n"
            "• Se sim, me responde *sim*.\n"
            "• Se não, me manda a chave certa — de preferência o *telefone* do banco que você usa."
        )
    else:
        meio = (
            "\n\nAqui no sistema *não tem chave PIX cadastrada* no seu nome.\n\n"
            "Me manda a chave da conta que você usa — de preferência o *telefone* do banco."
        )
    return cabeca + meio + (
        "\n\n_Só preciso da chave. Nunca peço senha, código do banco nem foto de cartão — "
        "se alguém pedir isso em nome da Conecta, é golpe._"
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


async def registrar_resposta(db: AsyncSession, *, employee_id: str, texto: str) -> dict[str, Any]:
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
    if not chave:
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
    r = (await db.execute(text(
        "SELECT chave_informada, tipo_informado, nome FROM pix_confirmacoes "
        "WHERE employee_id = CAST(:e AS uuid) AND status='respondido'"),
        {"e": employee_id})).first()
    if not r or not r[0]:
        return {"ok": False, "motivo": "não há chave informada para aplicar"}
    if not r[1]:
        return {"ok": False, "motivo": "tipo AMBÍGUO (11 dígitos = CPF ou celular). "
                                       "Confirme o tipo com a pessoa antes de aplicar."}
    await db.execute(text("""
        UPDATE employees SET pix_key=:k, pix=:k, pix_key_type=:tp, updated_at=now()
        WHERE id = CAST(:e AS uuid)"""), {"e": employee_id, "k": r[0], "tp": r[1]})
    await db.execute(text("""
        UPDATE pix_confirmacoes SET status='aplicado', aplicado_em=now(), aplicado_por=:a,
               updated_at=now() WHERE employee_id = CAST(:e AS uuid)"""),
        {"e": employee_id, "a": aprovador[:100]})
    await db.commit()
    return {"ok": True, "nome": r[2], "chave": r[0], "tipo": r[1], "aprovador": aprovador}


async def estado(db: AsyncSession) -> dict[str, Any]:
    rows = (await db.execute(text(
        "SELECT status, count(*) FROM pix_confirmacoes GROUP BY 1"))).all()
    return {"por_status": {s: n for s, n in rows}}
