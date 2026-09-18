"""Assinatura eletrônica do contrato — Conecta Mais assina, cliente assina por link.

Fecha o ciclo que faltava: até 21/08/2026 o contrato saía em PDF e a assinatura acontecia
fora do sistema. Agora o instrumento é firmado no próprio Conecta PRO, com evidência.

Reusa o MOTOR UNIVERSAL (`modules/signatures`), que já existia e já fazia tudo:
`criar_solicitacao_assinatura` com signatários em ordem, `assinar` para quem tem login e
`assinar_por_token` para quem recebe o link. Não escrevi motor de assinatura nenhum — o
que faltava era ninguém ter ligado o contrato nele.

ORDEM DOS SIGNATÁRIOS (decisão do Jordan, 21/08): a CONTRATADA assina primeiro, pelo
painel; depois o link vai para o cliente. Faz sentido no fluxo comercial — não se manda
para o síndico assinar um documento que a própria empresa ainda não firmou.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

BASE_PUBLICA = "https://erp.conectamais.pro"
# o motor lê o PDF de origem de `req.document_path` para carimbar o selo. Sem ele, só o
# assinante que trouxer os bytes na mão consegue firmar — e o cliente, que assina pela rota
# pública `/signatures/public/{token}`, NUNCA traz. Persistir aqui é o que faz o link do
# cliente funcionar sem tocar no motor.
PASTA_CONTRATOS = os.environ.get("CONECTA_UPLOADS", "/app/uploads") + "/contratos_assinatura"


@dataclass
class Solicitacao:
    request_id_empresa: str | None
    request_id_cliente: str | None
    token_cliente: str | None
    link_cliente: str | None
    documento_hash: str
    token_empresa: str | None = None
    link_empresa: str | None = None
    pin_empresa: str | None = None
    pin_cliente: str | None = None


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class AssinaturaJaAberta(RuntimeError):
    """Já existe lote ativo de assinatura para este contrato.

    ⚠️ Não é erro de permissão nem falha: é a segunda abertura sendo barrada. Reabrir exige
    CANCELAR o lote anterior primeiro — e cancelar é decisão de quem está com o contrato na
    mão, porque o lote antigo pode ter assinatura real dentro dele.
    """


async def abrir_assinatura(
    db: AsyncSession,
    contract_id: str,
    pdf: bytes,
    *,
    contratante_nome: str,
    representante: str,
    representante_cpf: str,
    representante_email: str | None,
    contratada_nome: str,
    assinante_empresa: str,
    assinante_empresa_id: uuid.UUID | None,
    solicitado_por: uuid.UUID | None = None,
) -> Solicitacao:
    """Abre a solicitação de assinatura das duas partes para este contrato."""
    from modules.signatures.services.universal_signature_service import (
        SignerInput,
        SignerType,
        UniversalSignatureService,
    )

    # ⭐ 18/09/2026 — §8 da SPEC: a guarda vive AQUI, não nos controllers.
    # Três portas chamam esta função (rota do redesign, `POST /crm/contracts/{id}/
    # abrir-assinatura`, e a tool `abrir_assinatura_contrato`) e só UMA tinha guarda — a do
    # redesign. As outras duas inseriam um par novo a cada chamada, e foi assim que o
    # CTR-2026-00022 ficou com dois lotes. Guarda replicada em N chamadores é guarda que um
    # chamador novo esquece; guarda na função é a mesma regra para todos.
    ja_aberta = (await db.execute(
        text("SELECT count(*) FROM sig_signature_requests "
             " WHERE reference_code = :k "
             "   AND upper(coalesce(status,'')) NOT IN "
             "       ('CANCELLED','CANCELED','CANCELADA','EXPIRED','EXPIRADA')"),
        {"k": contract_id})).scalar() or 0
    if ja_aberta:
        raise AssinaturaJaAberta(
            f"O contrato {contract_id} já tem coleta de assinatura aberta "
            f"({ja_aberta} signatário(s) ativo(s)).")

    doc_hash = _sha256(pdf)
    os.makedirs(PASTA_CONTRATOS, exist_ok=True)
    caminho = f"{PASTA_CONTRATOS}/{contract_id}_{doc_hash[:12]}.pdf"
    with open(caminho, "wb") as fh:
        fh.write(pdf)
    svc = UniversalSignatureService(db)
    res = await svc.criar_solicitacao_assinatura(
        document_type="contrato",
        document_id=str(uuid.uuid4()),
        title=f"Contrato {contract_id} — {contratante_nome}",
        signers=[
            # ordem 1: a empresa. Não se pede ao síndico que assine o que a Conecta Mais
            # ainda não firmou.
            SignerInput(
                signer_type=SignerType.COMPANY, signer_name=assinante_empresa, signer_id=assinante_empresa_id, order=1
            ),
            # ordem 2: o cliente, por link único
            SignerInput(
                signer_type=SignerType.CUSTOMER,
                signer_name=representante,
                signer_document=representante_cpf,
                signer_email=representante_email,
                order=2,
            ),
        ],
        document_name=f"Contrato {contract_id} — {contratante_nome}",
        document_path=caminho,
        document_hash=doc_hash,
        requested_by=solicitado_por,
        purpose="signature",
        expires_in_days=30,
        reference_code=contract_id,
        metadata={"contrato": contract_id, "contratada": contratada_nome},
    )

    pedidos = res.get("requests") or []
    emp = next((p for p in pedidos if str(p.get("signer_type", "")).endswith("company")), None)
    cli = next((p for p in pedidos if str(p.get("signer_type", "")).endswith("customer")), None)
    token = (cli or {}).get("public_token")
    tk_emp = (emp or {}).get("public_token")
    return Solicitacao(
        request_id_empresa=str(emp.get("id")) if emp else None,
        request_id_cliente=str(cli.get("id")) if cli else None,
        token_cliente=token,
        link_cliente=f"{BASE_PUBLICA}/assinar/contrato/{token}" if token else None,
        documento_hash=doc_hash,
        token_empresa=tk_emp,
        link_empresa=f"{BASE_PUBLICA}/assinar/contrato/{tk_emp}" if tk_emp else None,
        pin_empresa=(emp or {}).get("public_pin"),
        pin_cliente=(cli or {}).get("public_pin"),
    )


async def assinar_pela_empresa(
    db: AsyncSession,
    contract_id: str,
    *,
    nome: str,
    pdf: bytes,
    usuario_id: uuid.UUID | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """A Conecta Mais firma o contrato pelo painel (ordem 1).

    Só coleta a assinatura; quem faz a prova criptográfica e a trilha é o motor universal.
    """
    from modules.signatures.services.universal_signature_service import (
        SignatureEvidence,
        SignerType,
        UniversalSignatureService,
    )

    req = (
        await db.execute(
            text(
                "SELECT id FROM sig_signature_requests WHERE reference_code = :k "
                "AND signer_type = 'company' AND signed_at IS NULL "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"k": contract_id},
        )
    ).scalar()
    if not req:
        raise ValueError(f"não há solicitação da empresa em aberto para {contract_id}")

    svc = UniversalSignatureService(db)
    return await svc.assinar(
        request_id=req,
        signer_type=SignerType.COMPANY,
        signer_id=usuario_id,
        signer_name=nome,
        evidence=SignatureEvidence(
            ip_address=ip, user_agent=user_agent, extra={"contrato": contract_id, "origem": "painel"}
        ),
        # o motor RECUSA registrar sem o documento de origem — ele carimba o selo no PDF.
        # Recusa honesta: sem isso ficaria assinatura registrada sem papel assinado.
        pdf_bytes=pdf,
    )


def _html(titulo: str, corpo: str, rodape: str = "") -> str:
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;color:#1F2937;max-width:600px">'
        f'<div style="background:#16277D;padding:18px 22px;border-bottom:4px solid #F26522">'
        f'<span style="color:#fff;font-size:18px;font-weight:bold">Conecta Mais</span></div>'
        f'<div style="padding:22px"><h2 style="color:#16277D;margin:0 0 12px">{titulo}</h2>'
        f"{corpo}</div>"
        f'<div style="padding:14px 22px;background:#F3F4F6;font-size:12px;color:#6B7280">'
        f"{rodape or 'Mensagem automática do Conecta PRO — não responda a este e-mail.'}"
        "</div></div>"
    )


async def _carta_de_apresentacao(db: AsyncSession, contract_id: str) -> str:
    """O QUE está sendo assinado, em quatro linhas, lido do contrato.

    Pedido do Jordan (09/09/2026): o convite era um aviso seco — "há um documento para
    assinar". Quem recebe é um síndico ou uma presidente de associação que falou com a
    Conecta há semanas; abrir um e-mail que não diz o objeto nem o valor faz a pessoa
    hesitar antes de clicar, e hesitar num link é o comportamento certo dela.

    ⚠️ Nada é inventado: cada linha só aparece se o banco tiver o dado. Um resumo com
    "valor a combinar" num convite de assinatura seria pior que resumo nenhum.
    """
    r = (
        (
            await db.execute(
                text(
                    "SELECT coalesce(cl.name, c.name) AS cliente, c.description, "
                    "       c.contract_type::text AS tipo, c.monthly_value, c.total_value, "
                    "       c.tipo_servico::text AS tipo_servico, t.service_type "
                    "FROM contracts c "
                    "LEFT JOIN clients cl ON cl.id = c.client_id "
                    "LEFT JOIN contract_templates t ON t.id = c.template_id "
                    "WHERE c.contract_number = :k OR c.id::text = :k"
                ),
                {"k": contract_id},
            )
        )
        .mappings()
        .first()
    )
    if not r:
        return ""

    def _brl(v) -> str:
        return f"R$ {v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")

    linhas = []
    if r["description"]:
        linhas.append(("Objeto", str(r["description"]).strip()))
    if (r["tipo"] or "") == "one_time":
        if r["total_value"]:
            linhas.append(("Valor", f"{_brl(r['total_value'])} — serviço único, parcelado conforme a Cláusula 3ª"))
    elif r["monthly_value"]:
        linhas.append(("Valor", f"{_brl(r['monthly_value'])} por mês"))
    # A CONTRATADA vem da MESMA regra que o instrumento usa (`resolver_contratada`), nunca
    # de `contracts.empresa_id` nem de `empresas.razao_social`. Dois motivos, os dois já
    # medidos nesta casa: o `empresa_id` gravado já contradisse a regra (CTR-2026-00019 em
    # 19/08), e a Receita registra "CONECTAMAIS" tudo junto enquanto o contrato assina
    # "Conecta Mais". Carta que anuncia uma empresa e contrato que diz outra é o pior
    # defeito possível num convite de assinatura.
    try:
        from modules.crm.services.contract_render import resolver_contratada  # noqa: PLC0415

        ctda = resolver_contratada(r["tipo_servico"], r["service_type"])
        linhas.append(("Contratada", f"{ctda.razao_social} · CNPJ {ctda.cnpj}"))
    except Exception:  # noqa: BLE001 — sem tipo declarado a regra RECUSA; a carta segue sem a linha
        pass

    if not linhas:
        return ""
    itens = "".join(
        f'<tr><td style="padding:4px 10px 4px 0;color:#6B7280;vertical-align:top;'
        f'white-space:nowrap">{k}</td><td style="padding:4px 0">{v}</td></tr>'
        for k, v in linhas
    )
    return (
        f'<table style="margin:16px 0;border-left:3px solid #F26522;padding-left:14px;font-size:14px">{itens}</table>'
    )


async def convidar_para_assinar(
    db: AsyncSession, contract_id: str, *, para: str, link: str, nome: str = "", papel: str = ""
) -> bool:
    """Avisa um signatário de que há documento esperando a assinatura dele.

    Manda o LINK, nunca o código: o código vai depois, para o e-mail que a pessoa informar
    na própria tela. Link e código no mesmo e-mail transformam dois fatores em um.
    """
    from core.mailer import send_email  # noqa: PLC0415

    quem = f"<p>Olá, {nome}.</p>" if nome else ""
    posicao = f"<p>Você consta como <b>{papel}</b> neste instrumento.</p>" if papel else ""
    carta = await _carta_de_apresentacao(db, contract_id)
    return await send_email(
        para,
        f"Contrato {contract_id} — pronto para sua assinatura",
        _html(
            "Seu contrato está pronto para assinatura",
            quem + "<p>Agradecemos a confiança na Conecta Mais. Segue o contrato que "
            "formaliza o que combinamos, pronto para sua assinatura eletrônica.</p>"
            + carta
            + f"<p>O instrumento é o de número <b>{contract_id}</b>.</p>"
            + posicao
            + '<p style="margin:22px 0"><a href="'
            + link
            + '" '
            'style="background:#F26522;color:#fff;text-decoration:none;padding:14px 26px;'
            'border-radius:8px;font-weight:bold;display:inline-block">'
            "Ler e assinar o contrato</a></p>"
            + "<p>Na tela você lê o contrato inteiro, informa nome, CPF e e-mail, e recebe "
            "um <b>código de validação</b> no seu e-mail para concluir a assinatura.</p>"
            + f'<p style="font-size:12px;color:#6B7280">Se o botão não abrir, copie este '
            f"endereço: {link}</p>",
        ),
    )


async def notificar_apos_assinatura(db: AsyncSession, contract_id: str, pdf: bytes) -> dict:
    """Manda a via para quem acabou de assinar e, se todos assinaram, avisa as partes.

    Nunca derruba a assinatura: e-mail que falha vira log, não exceção — a assinatura já
    está registrada e não pode ser perdida porque o SMTP piscou.

    Só manda para quem INFORMOU e-mail. Sem endereço, não há para onde mandar — e inventar
    destinatário a partir do cadastro do cliente é mandar contrato assinado para quem não
    pediu.
    """
    from core.mailer import send_email  # noqa: PLC0415

    partes = await manifesto_do_contrato(db, contract_id)
    faltam = [m for m in partes if not m["assinado"]]
    completo = bool(partes) and not faltam

    emails = (
        (
            await db.execute(
                text(
                    "SELECT signer_name, signer_email, signed_at IS NOT NULL AS assinou "
                    "FROM sig_signature_requests WHERE reference_code = :k AND signer_email IS NOT NULL "
                    "AND signer_email <> '' ORDER BY signature_order"
                ),
                {"k": contract_id},
            )
        )
        .mappings()
        .all()
    )

    anexo = [(f"Contrato {contract_id}.pdf", pdf)]
    enviados: list[str] = []

    # 1 · via para quem assinou (cada um recebe a sua no ato)
    for e in emails:
        if not e["assinou"]:
            continue
        pendencia = (
            "<p>Assim que as demais partes assinarem, você receberá a via final com o manifesto completo.</p>"
            if faltam
            else ""
        )
        ok = await send_email(
            e["signer_email"],
            f"Contrato {contract_id} — sua via assinada",
            _html(
                "Sua assinatura foi registrada",
                f"<p>Olá, {e['signer_name']}.</p>"
                f"<p>Segue em anexo o contrato <b>{contract_id}</b> com sua assinatura "
                "eletrônica registrada. O manifesto ao final traz data, hora, endereço IP "
                "e o código de verificação de cada assinatura.</p>" + pendencia,
            ),
            anexos=anexo,
        )
        if ok:
            enviados.append(e["signer_email"])

    # 2 · todas as partes assinaram: avisa TODO MUNDO que informou e-mail
    if completo:
        nomes = ", ".join(m["nome"] for m in partes)
        for e in emails:
            await send_email(
                e["signer_email"],
                f"Contrato {contract_id} — assinado por todas as partes",
                _html(
                    "Contrato concluído",
                    f"<p>O contrato <b>{contract_id}</b> foi assinado por todas as partes: "
                    f"{nomes}.</p><p>A via final, com o manifesto de assinaturas, segue "
                    "em anexo.</p>",
                ),
                anexos=anexo,
            )

    return {"completo": completo, "enviados": enviados, "faltam": [m["nome"] for m in faltam]}


# `sig_signature_requests` (1.749 linhas — o motor está em uso de verdade). O hash da
# assinatura fica em sig_signatures; o do documento assinado, na própria solicitação.
_SQL_ASSIN = """
SELECT r.signer_type::text AS papel, r.signer_name AS nome, r.signed_at,
       -- o hash da ASSINATURA (sig_signatures), não o do documento: é ele que
       -- `GET /signatures/verify/{hash}` aceita. Imprimir o do documento fazia o código
       -- rotulado "Verificação" não verificar nada.
       coalesce(s.signature_hash, r.signed_document_hash, r.document_hash, '') AS hash,
       r.signing_ip
FROM sig_signature_requests r
LEFT JOIN sig_signatures s ON s.id = r.signature_id
WHERE r.reference_code = :k AND r.signed_at IS NOT NULL
ORDER BY r.signature_order, r.signed_at
"""


async def manifesto_do_contrato(db: AsyncSession, contract_id: str) -> list[dict]:
    """TODOS os signatários — assinados e pendentes — para o manifesto ao final do PDF.

    Diferente de `assinaturas_do_contrato`, que só devolve quem já assinou (o bloco de
    assinatura não pode carimbar quem não firmou). O manifesto mostra os dois estados:
    é a trilha de auditoria, e uma trilha que esconde o pendente não é trilha.
    """
    try:
        linhas = (
            (
                await db.execute(
                    text("""
            SELECT r.signer_type::text AS papel, r.signer_name AS nome, r.signer_document AS doc,
                   r.signed_at, r.signing_ip, r.signing_user_agent AS agente,
                   coalesce(s.signature_hash, r.signed_document_hash, r.document_hash, '') AS hash,
                   r.id::text AS req, r.signature_order AS ordem
            FROM sig_signature_requests r
            LEFT JOIN sig_signatures s ON s.id = r.signature_id
            WHERE r.reference_code = :k
              -- ⭐ 18/09/2026 — §8 da SPEC. Esta query lia TODOS os lotes e IGNORAVA o
              -- `status`, e o manifesto do CTR-2026-00022 saía com quatro linhas
              -- contraditórias: duas "#1 CONTRATADA" (uma Assinado 10/09, outra Pendente) e
              -- duas "#2 CONTRATANTE Pendente". Não era dado corrompido — eram DUAS
              -- aberturas de assinatura (09/09 23:56 e 11/09 18:07), cada uma criando o par
              -- completo, e a linha CANCELLED impressa como "Pendente" porque a situação era
              -- deduzida só de `signed_at IS NOT NULL`.
              --
              -- ⚠️ NÃO usei constraint UNIQUE (reference_code, signature_order), que foi o
              -- pedido literal: ela apagaria HISTÓRICO. No 00022 a ordem 1 do lote antigo
              -- está SIGNED — é a assinatura real do Jordan, sobre outro hash de documento.
              -- Apagar ou cancelar essa linha seria reescrever o que aconteceu.
              --
              -- O manifesto é a trilha do INSTRUMENTO ATUAL: lê o lote mais recente e
              -- descarta cancelado/expirado. O histórico segue no banco, inteiro.
              AND upper(coalesce(r.status, '')) NOT IN
                  ('CANCELLED', 'CANCELED', 'CANCELADA', 'EXPIRED', 'EXPIRADA')
              AND coalesce(r.document_id::text, '') = coalesce((
                    SELECT r2.document_id::text FROM sig_signature_requests r2
                     WHERE r2.reference_code = r.reference_code
                       AND upper(coalesce(r2.status, '')) NOT IN
                           ('CANCELLED', 'CANCELED', 'CANCELADA', 'EXPIRED', 'EXPIRADA')
                     ORDER BY r2.created_at DESC LIMIT 1), '')
            ORDER BY r.signature_order"""),
                    {"k": contract_id},
                )
            )
            .mappings()
            .all()
        )
    except Exception:  # noqa: BLE001
        await db.rollback()
        return []
    return [
        {
            "papel": "CONTRATADA" if "company" in (r["papel"] or "") else "CONTRATANTE",
            "nome": r["nome"] or "",
            "doc": r["doc"] or "",
            "quando": r["signed_at"].strftime("%d/%m/%Y às %H:%M:%S") if r["signed_at"] else "",
            "assinado": r["signed_at"] is not None,
            "ip": r["signing_ip"] or "",
            "agente": (r["agente"] or "")[:60],
            "hash": r["hash"] or "",
            "req": r["req"],
            "ordem": r["ordem"],
        }
        for r in linhas
    ]


async def assinaturas_do_contrato(db: AsyncSession, contract_id: str) -> list[dict]:
    """As assinaturas JÁ coletadas — é o que o bloco final do PDF exibe.

    Devolve lista vazia quando ninguém assinou: o contrato então sai com "Aguardando
    assinatura eletrônica", que é honesto. Nunca inventa carimbo.
    """
    try:
        linhas = (await db.execute(text(_SQL_ASSIN), {"k": contract_id})).mappings().all()
    except Exception:  # noqa: BLE001 — tabela/coluna ausente neste ambiente
        await db.rollback()
        return []
    saida = []
    for r in linhas:
        papel = "contratada" if "company" in (r["papel"] or "") else "contratante"
        quando = r["signed_at"]
        saida.append(
            {
                "papel": papel,
                "nome": r["nome"],
                "quando": quando.strftime("%d/%m/%Y às %H:%M") if quando else "",
                "hash": r["hash"] or "",
                "ip": r["signing_ip"] or "",
            }
        )
    return saida


# Cópia de arquivo para quem enviou. Pedido do Jordan em 10/09/2026, com o motivo dele:
# "no meu e-mail vai aparecer enviado via Conecta PRO pelo noreply e os e-mails que foram
# enviados, assim tenho como printar e mandar pros clientes".
#
# O problema real: a síndica do Maiápolis disse que não recebeu nada, e não havia como
# provar o contrário — o log do servidor não serve de prova para um cliente. Agora cada
# envio deixa um comprovante na caixa de quem mandou, com a lista de destinatários, data e
# hora, pronto para imprimir.
#
# ⚠️ A cópia NÃO leva o botão de assinar. O link de assinatura é pessoal do signatário:
# quem o tem começa a assinatura, e o código de validação vai para o e-mail que a pessoa
# digitar na tela — não para o cadastrado. Um comprovante feito para ser impresso e
# encaminhado no WhatsApp não pode carregar dentro dele a chave de assinar o contrato.
COPIA_PARA = "jjesus@conectamais.pro"


async def copia_de_envio(
    db: AsyncSession, contract_id: str, *, destinatarios: list[str], papel: str = "", quando: str = ""
) -> bool:
    """Comprovante de envio para o arquivo de quem mandou. Nunca derruba o envio real."""
    from core.mailer import send_email  # noqa: PLC0415

    if not destinatarios:
        return False
    carta = await _carta_de_apresentacao(db, contract_id)
    linhas = "".join(f"<li><b>{d}</b></li>" for d in destinatarios)
    quem = f" como <b>{papel}</b>" if papel else ""
    try:
        return await send_email(
            COPIA_PARA,
            f"Cópia — convite de assinatura do contrato {contract_id} enviado",
            _html(
                "Comprovante de envio",
                f"<p>O convite para assinar o contrato <b>{contract_id}</b>{quem} foi "
                f"enviado pelo Conecta PRO{(' em ' + quando) if quando else ''} para:</p>"
                f'<ul style="line-height:1.7">{linhas}</ul>'
                + carta
                + "<p>Cada destinatário recebeu o convite com o próprio link de "
                "assinatura. Este é o teor da mensagem que chegou a eles.</p>"
                + '<p style="font-size:12px;color:#6B7280">O link de assinatura é pessoal '
                "e não é reproduzido nesta cópia, para que ela possa ser impressa e "
                "encaminhada com segurança.</p>",
                rodape="Cópia automática para o arquivo — Conecta PRO",
            ),
        )
    except Exception as e:  # noqa: BLE001 — comprovante que falha não invalida o envio
        import logging  # noqa: PLC0415

        logging.getLogger(__name__).warning(f"cópia de envio de {contract_id} falhou: {e}")
        return False
