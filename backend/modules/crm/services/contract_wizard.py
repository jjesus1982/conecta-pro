"""Solicitação de contrato assistida — o que falta, e como completar.

Nasce de 21/08/2026: o contrato do Green Hills só existiu porque eu chamei a rota por
`curl`. Ninguém no jurídico, no chat ou no Cowork conseguia pedir "gera o contrato do
Green Hills" — e quando o render recusa por dado faltando, a mensagem morre no log.

Este módulo é a ponte. Ele NÃO renderiza: pergunta ao banco o que já existe, devolve em
forma de PERGUNTA o que falta, e sabe gravar as respostas nos lugares certos.

Por que perguntar em vez de assumir: cada campo que falta tem casa própria — o
representante legal vive em `crm_contacts`, a composição em `contract_items`, o dia de
vencimento em `contracts`. Preencher no lugar errado é o defeito que gerou o
`contract_render` (nome da Eletrônica ao lado do CNPJ da Patrimonial).

REGRA DE DINHEIRO: a soma dos itens tem de bater com `monthly_value`. Sem isso o contrato
sairia com uma composição que não fecha com o valor que o cliente aceitou — e é o valor
por extenso, no meio do instrumento, que vira disputa.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Só estes dois emitem contrato. Decisão do Jordan (21/08): vale para chat, jurídico e
# Cowork — a superfície muda, a parede é a mesma.
EMITENTES = {"jjesus@conectamais.pro", "pjesus@conectamais.pro"}


class ErroDeItem(ValueError):
    """Validação de ITEM da composição, com código próprio.

    ⭐ 18/09/2026 — §3 e §4 da SPEC de emissão. Antes, TODA falha de validação voltava como
    `403 SEM_PERMISSAO / "Esta ação é restrita."` porque o controller mapeava qualquer recusa
    para 403. Um agente que lê 403 conclui que não tem acesso e PARA, ou pede credencial ao
    usuário — quando bastava corrigir o payload. 403 fica para autorização de verdade.
    """

    def __init__(self, codigo: str, mensagem: str, **extra) -> None:
        self.codigo, self.extra = codigo, extra
        super().__init__(mensagem)


# Chaves que o item da composição aceita. ⚠️ É a lista REAL, medida no INSERT abaixo — não a
# que eu imaginava: a quantidade é `qtd`, não `quantidade`, e `subtotal` nunca existiu.
# O `subtotal` era descartado em silêncio e a soma dava 0, então a trava de dinheiro
# reclamava do VALOR ("ajuste os subtotais") quando o defeito era o NOME DO CAMPO. Mandar o
# dono ajustar um valor que está certo é o pior tipo de mensagem de erro.
CHAVES_DO_ITEM = ("nome", "descricao", "qtd", "quantidade", "total", "tipo",
                  "vencimento", "notes")
LIMITE_NOME_ITEM = 200   # contract_items.service_name é varchar(200) — medido no DDL


def _validar_itens(itens: list) -> None:
    """Recusa na BORDA, com código e campo. Nada de 500 e nada de descarte silencioso."""
    for pos, i in enumerate(itens or [], start=1):
        if not isinstance(i, dict):
            raise ErroDeItem("ITEM_INVALIDO", f"O item {pos} não é um objeto.",
                             posicao=pos)
        desconhecidas = [k for k in i if k not in CHAVES_DO_ITEM]
        if desconhecidas:
            raise ErroDeItem(
                "CAMPO_DESCONHECIDO",
                f"Item {pos} ({i.get('nome') or 'sem nome'}): campo(s) "
                f"{desconhecidas} não existe(m).",
                posicao=pos, campos_desconhecidos=desconhecidas,
                campos_aceitos=list(CHAVES_DO_ITEM),
                dica=("Descartar campo em silêncio faria você achar que gravou. "
                      "O valor da linha é `total`; a quantidade é `qtd` (ou `quantidade`)."))
        nome = str(i.get("nome") or "")
        if len(nome) > LIMITE_NOME_ITEM:
            raise ErroDeItem(
                "CAMPO_LONGO_DEMAIS",
                f"Item {pos}: `nome` tem {len(nome)} caracteres e o limite é "
                f"{LIMITE_NOME_ITEM}.",
                posicao=pos, campo="nome", tamanho=len(nome),
                limite=LIMITE_NOME_ITEM,
                dica=("`nome` é o rótulo curto da tabela de composição. O detalhamento do "
                      "que está sendo fornecido vai em `descricao`, que não tem limite."))



class NaoAutorizado(PermissionError):
    pass


def pode_emitir(user) -> bool:
    email = (getattr(user, "email", "") or "").strip().lower()
    return email in EMITENTES


def exigir_emitente(user) -> None:
    if not pode_emitir(user):
        raise NaoAutorizado(
            "Emitir contrato é restrito ao Jordan e à Pyetra. Consultar e listar contratos segue liberado."
        )


@dataclass
class Pendencia:
    campo: str
    pergunta: str  # o que o agente pergunta ao humano, em português
    onde: str  # onde o dado será gravado — some no relatório, não no contrato
    exemplo: str = ""


@dataclass
class Situacao:
    contrato: str
    cliente: str
    valor_mensal: Decimal
    modelo_id: str | None
    modelo_nome: str | None
    pendencias: list[Pendencia] = field(default_factory=list)

    @property
    def pronto(self) -> bool:
        return not self.pendencias


_SQL = """
SELECT c.id::text AS cid, c.contract_number, c.monthly_value, c.payment_day,
       c.grace_period_days, c.start_date, c.end_date, c.template_id::text AS template_id,
       c.tipo_servico::text AS tipo_servico,
       c.contract_type::text AS contract_type, c.total_value, c.description, c.sla_config,
       cl.name AS cliente, cl.id::text AS client_id,
       t.name AS modelo_nome,
       (SELECT count(*) FROM contract_items i
         WHERE i.contract_id = c.id AND coalesce(i.is_active, true)) AS n_itens,
       (SELECT k.name FROM crm_contacts k
         WHERE k.client_id = c.client_id
           AND (k.role ILIKE '%representante%' OR k.role ILIKE '%s%ndic%' OR k.role ILIKE '%legal%' OR k.role ILIKE '%presidente%' OR k.role ILIKE '%diretor%' OR k.role ILIKE '%s%cio%' OR k.role ILIKE '%administrador%' OR k.role ILIKE '%procurador%' OR k.role ILIKE '%titular%')
         ORDER BY k.is_primary DESC NULLS LAST LIMIT 1) AS representante,
       (SELECT k.notes FROM crm_contacts k
         WHERE k.client_id = c.client_id
           AND (k.role ILIKE '%representante%' OR k.role ILIKE '%s%ndic%' OR k.role ILIKE '%legal%' OR k.role ILIKE '%presidente%' OR k.role ILIKE '%diretor%' OR k.role ILIKE '%s%cio%' OR k.role ILIKE '%administrador%' OR k.role ILIKE '%procurador%' OR k.role ILIKE '%titular%')
         ORDER BY k.is_primary DESC NULLS LAST LIMIT 1) AS representante_cpf
FROM contracts c
LEFT JOIN clients cl ON cl.id = c.client_id
LEFT JOIN contract_templates t ON t.id = c.template_id
WHERE c.id::text = :k OR c.contract_number = :k
"""


async def diagnosticar(db: AsyncSession, chave: str) -> Situacao:
    """O que já existe e o que falta para este contrato virar instrumento."""
    r = (await db.execute(text(_SQL), {"k": chave})).mappings().first()
    if not r:
        raise LookupError(f"Contrato não encontrado: {chave}")

    s = Situacao(
        contrato=r["contract_number"],
        cliente=r["cliente"] or "—",
        valor_mensal=Decimal(str(r["monthly_value"] or 0)),
        modelo_id=r["template_id"],
        modelo_nome=r["modelo_nome"],
    )

    if not r["template_id"]:
        s.pendencias.append(
            Pendencia(
                "template_id",
                "Qual modelo de contrato usar? (o contrato ainda não está vinculado a nenhum)",
                "contracts.template_id",
            )
        )
    if not r["representante"]:
        s.pendencias.append(
            Pendencia(
                "representante",
                f"Quem assina pelo {r['cliente'] or 'cliente'}? Preciso do nome completo do "
                "representante legal (síndico).",
                "crm_contacts",
                "Hely Carvalho",
            )
        )
    if not (r["representante_cpf"] or "").strip():
        s.pendencias.append(
            Pendencia("representante_cpf", "Qual o CPF de quem assina?", "crm_contacts", "562.043.372-20")
        )
    # Contrato de valor ÚNICO (fornecimento + instalação) não tem mensalidade, carência nem
    # vigência: perguntar dia de vencimento a quem contratou uma obra é perguntar por algo
    # que o instrumento não vai citar — e a resposta iria para uma coluna que ninguém lê.
    if (r["contract_type"] or "").strip().lower() == "one_time":
        s.pendencias.extend(_pendencias_one_time(r))
        return s

    if not r["payment_day"]:
        s.pendencias.append(
            Pendencia("payment_day", "Em que dia do mês vence a mensalidade?", "contracts.payment_day", "8")
        )
    if not r["grace_period_days"]:
        s.pendencias.append(
            Pendencia(
                "grace_period_days",
                "Em quantos dias vence o PRIMEIRO pagamento, contados da assinatura?",
                "contracts.grace_period_days",
                "90",
            )
        )
    if not r["n_itens"]:
        s.pendencias.append(
            Pendencia(
                "itens",
                "Como se compõe o valor mensal? Preciso da quantidade e do subtotal de cada "
                f"função — a soma tem de fechar em {r['monthly_value']}.",
                "contract_items",
                "AGP Diurno 2 = 10605.78 · AGP Noturno 2 = 11494.22",
            )
        )
    if not r["start_date"] or not r["end_date"]:
        s.pendencias.append(
            Pendencia(
                "vigencia",
                "Qual o período de vigência (início e término)?",
                "contracts.start_date/end_date",
                "01/09/2026 a 31/08/2028",
            )
        )
    return s


def _pendencias_one_time(r) -> list[Pendencia]:
    """O que falta num contrato de valor ÚNICO — e só o que o instrumento realmente cita."""
    sla = r["sla_config"] if isinstance(r["sla_config"], dict) else {}
    faltam: list[Pendencia] = []

    if not (r["total_value"] and Decimal(str(r["total_value"])) > 0):
        faltam.append(Pendencia("valor_total", "Qual o valor TOTAL do serviço?", "contracts.total_value", "46320"))
    if not (r["description"] or "").strip():
        faltam.append(
            Pendencia(
                "objeto_resumo",
                "Descreva em uma frase o que será entregue (vai para a Cláusula 1ª).",
                "contracts.description",
                "controle de acesso por biometria facial; automação dos portões; CFTV",
            )
        )
    if not str(sla.get("proposta_numero") or "").strip():
        faltam.append(
            Pendencia(
                "proposta_numero",
                "Qual a proposta comercial que originou este contrato? Ela integra o "
                "instrumento e é citada na Cláusula 1ª.",
                "contracts.sla_config->proposta_numero",
                "PROP-2026-00001",
            )
        )
    if not r["n_itens"]:
        faltam.append(
            Pendencia(
                "itens",
                "Como se parcela o pagamento? Preciso de cada parcela com tipo "
                "(entrada · parcela · retida), valor e vencimento — a soma tem de fechar em "
                f"{r['total_value']}.",
                "contract_items",
                "entrada 23160 · parcela 7720 em 30 dias · parcela 7720 em 60 dias · retida 7720",
            )
        )
    return faltam


async def completar(db: AsyncSession, chave: str, **dados) -> list[str]:
    """Grava as respostas NO LUGAR CERTO de cada uma. Devolve o que foi feito."""
    # ⚠️ `commit` vem em `dados` porque a assinatura é `**dados` e Python não aceita
    # parâmetro depois de var-keyword. Consumido aqui para não vazar no payload.
    commit = bool(dados.pop("commit", True))
    r = (await db.execute(text(_SQL), {"k": chave})).mappings().first()
    if not r:
        raise LookupError(f"Contrato não encontrado: {chave}")
    feitos: list[str] = []

    if dados.get("template_id"):
        # o `tipo_servico` do contrato herda o do MODELO quando está vazio. Escolher o
        # modelo já é declarar a natureza do serviço, e sem isto quem resolve a contratada
        # é só o modelo (funciona, mas a lista de contratos mostra "Serviço —" e um contrato
        # sem modelo depois vira ambiguidade que o render RECUSA). `coalesce` para nunca
        # sobrescrever uma declaração que alguém já fez à mão.
        await db.execute(
            text(
                "UPDATE contracts c SET template_id = CAST(:t AS uuid), "
                "  tipo_servico = coalesce(nullif(c.tipo_servico::text,''), t.service_type), "
                "  updated_at = now() "
                "FROM contract_templates t WHERE t.id = CAST(:t AS uuid) AND c.id::text = :c"
            ),
            {"t": dados["template_id"], "c": r["cid"]},
        )
        feitos.append("modelo vinculado ao contrato")

    if dados.get("representante"):
        existe = (
            await db.execute(
                text(
                    # ⭐ 18/09/2026 — `ORDER BY` IDÊNTICO ao do render. Este SELECT tinha
                    # `LIMIT 1` sem ordenação nenhuma, e o render
                    # (`contract_render._SQL_REPRESENTANTE`) usa
                    # `ORDER BY is_primary DESC, created_at`. Com mais de um contato que casa
                    # o filtro de papel — o cliente do CTR-2026-00022 tem DOIS — o wizard
                    # gravava numa linha e o PDF lia outra. Era exatamente o bug reportado:
                    # `gravado_agora: [...]` e o texto renderizado sem mudar.
                    #
                    # A lição é a régua, não o caso: duas consultas que precisam apontar para
                    # a MESMA linha têm de ordenar igual, ou uma delas escolhe sozinha.
                    "SELECT id::text FROM crm_contacts WHERE client_id::text=:c "
                    "AND (role ILIKE '%representante%' OR role ILIKE '%s%ndic%' OR role ILIKE '%legal%' OR role ILIKE '%presidente%' OR role ILIKE '%diretor%' OR role ILIKE '%s%cio%' OR role ILIKE '%administrador%' OR role ILIKE '%procurador%' OR role ILIKE '%titular%') "
                    "ORDER BY is_primary DESC NULLS LAST, created_at LIMIT 1"
                ),
                {"c": r["client_id"]},
            )
        ).scalar()
        cpf = (dados.get("representante_cpf") or "").strip()
        if existe:
            await db.execute(
                text(
                    # `role` só muda se vier `representante_cargo`: sobrescrever com vazio
                    # apagaria "Síndica" de um cadastro que já estava certo.
                    "UPDATE crm_contacts SET name=:n, notes=coalesce(nullif(:cpf,''), notes), "
                    "role=coalesce(nullif(:cargo,''), role), "
                    "updated_at=now() WHERE id::text=:i"
                ),
                {"n": dados["representante"], "cpf": cpf, "i": existe,
                 "cargo": (dados.get("representante_cargo") or "").strip()},
            )
        else:
            await db.execute(
                text(
                    "INSERT INTO crm_contacts (id, client_id, name, role, notes, is_primary, created_at, updated_at) "
                    "VALUES (:i, CAST(:c AS uuid), :n, :cargo, :cpf, false, now(), now())"
                ),
                {"i": str(uuid.uuid4()), "c": r["client_id"], "n": dados["representante"],
                 "cpf": cpf,
                 "cargo": (dados.get("representante_cargo") or "").strip()
                          or "Representante legal"},
            )
        feitos.append(f"representante legal: {dados['representante']}")
    elif dados.get("representante_cpf"):
        await db.execute(
            text(
                # ⚠️ este UPDATE não tinha LIMIT: escrevia o CPF em TODOS os contatos que
                # casavam o papel. No cliente do 00022 isso são dois, e um deles nem é o que
                # o render usa. Agora aponta para a MESMA linha que o render lê.
                "UPDATE crm_contacts SET notes=:cpf, updated_at=now() WHERE id = ("
                "  SELECT id FROM crm_contacts WHERE client_id::text=:c "
                "   AND (role ILIKE '%representante%' OR role ILIKE '%s%ndic%' OR role ILIKE '%legal%' OR role ILIKE '%presidente%' OR role ILIKE '%diretor%' OR role ILIKE '%s%cio%' OR role ILIKE '%administrador%' OR role ILIKE '%procurador%' OR role ILIKE '%titular%') "
                "   ORDER BY is_primary DESC NULLS LAST, created_at LIMIT 1)"
            ),
            {"cpf": dados["representante_cpf"], "c": r["client_id"]},
        )
        feitos.append("CPF do representante gravado")

    campos = {"payment_day": "dia de vencimento", "grace_period_days": "carência do 1º pagamento"}
    for col, rot in campos.items():
        if dados.get(col) is not None:
            await db.execute(
                text(f"UPDATE contracts SET {col}=:v, updated_at=now() WHERE id::text=:c"),  # noqa: S608
                {"v": int(dados[col]), "c": r["cid"]},
            )
            feitos.append(f"{rot}: {dados[col]}")

    unico = (r["contract_type"] or "").strip().lower() == "one_time"

    if unico:
        if dados.get("valor_total") is not None:
            await db.execute(
                text("UPDATE contracts SET total_value=:v, updated_at=now() WHERE id::text=:c"),
                {"v": Decimal(str(dados["valor_total"])), "c": r["cid"]},
            )
            feitos.append(f"valor total: {dados['valor_total']}")
        if dados.get("objeto_resumo"):
            await db.execute(
                text("UPDATE contracts SET description=:d, updated_at=now() WHERE id::text=:c"),
                {"d": str(dados["objeto_resumo"]).strip(), "c": r["cid"]},
            )
            feitos.append("objeto do contrato gravado")
        # parâmetros de emissão no saco por contrato — mesma prateleira de `visita_numero`
        # no modelo de manutenção. `||` preserva o que já estava lá.
        emis = {
            k: dados[k]
            for k in (
                "proposta_numero",
                "prazo_exec_dias",
                "conecta_plus_valor",
                "foro",
                "cidade_assinatura",
                "homologacao_dias",
                "garantia_meses",
                "cortesia_meses",
                "multa_atraso_dia",
                "multa_teto_pct",
            )
            if dados.get(k) not in (None, "")
        }
        if emis:
            # `coalesce` NÃO basta: a coluna pode guardar o JSON `null` (que não é SQL NULL),
            # e `'null'::jsonb || '{...}'::jsonb` devolve um ARRAY `[null, {...}]`, não um
            # objeto — o parâmetro some sem erro nenhum e a pendência volta na cara do
            # usuário. Medido no CTR-2026-00022. `jsonb_typeof` é o único teste honesto.
            await db.execute(
                text(
                    "UPDATE contracts SET sla_config = "
                    "  CASE WHEN jsonb_typeof(sla_config) = 'object' THEN sla_config "
                    "       ELSE '{}'::jsonb END || CAST(:j AS jsonb), "
                    "  updated_at=now() WHERE id::text=:c"
                ),
                {"j": json.dumps(emis), "c": r["cid"]},
            )
            feitos.append("parâmetros de emissão: " + ", ".join(sorted(emis)))

    # ⭐ 18/09/2026 — §1 da SPEC. `foro` e `cidade_assinatura` estavam SÓ no bloco `if unico:`
    # logo acima: em contrato recorrente, passá-los era descartado em silêncio. São cláusula
    # de todo instrumento, então gravam sempre. As outras chaves daquele bloco (prazo de
    # execução, homologação, garantia) são de serviço único de verdade e ficam lá.
    foro_cidade = {k: str(dados[k]).strip() for k in ("foro", "cidade_assinatura")
                   if dados.get(k) not in (None, "")}
    if foro_cidade and not unico:      # no único o bloco `emis` acima já gravou
        await db.execute(
            text(
                "UPDATE contracts SET sla_config = "
                "  CASE WHEN jsonb_typeof(sla_config) = 'object' THEN sla_config "
                "       ELSE '{}'::jsonb END || CAST(:j AS jsonb), "
                "  updated_at=now() WHERE id::text=:c"
            ),
            {"j": json.dumps(foro_cidade), "c": r["cid"]},
        )
        feitos.append("foro/praça de assinatura: " + ", ".join(sorted(foro_cidade)))

    itens = dados.get("itens")
    if itens:
        _validar_itens(itens)
        # TRAVA DE DINHEIRO: a composição tem de fechar com o valor acordado. Um contrato
        # cuja tabela não soma o valor por extenso é convite a disputa.
        soma = sum(Decimal(str(i.get("total") or 0)) for i in itens)
        # no serviço único a régua é o TOTAL (e ele pode ter acabado de ser gravado, duas
        # linhas acima — por isso lê o dado novo, não o `r` que veio do início da função)
        if unico:
            alvo = Decimal(str(dados.get("valor_total") or r["total_value"] or 0))
            rotulo = "valor total"
        else:
            alvo = Decimal(str(r["monthly_value"] or 0))
            rotulo = "valor mensal"
        if soma != alvo:
            raise ErroDeItem(
                "COMPOSICAO_NAO_FECHA",
                f"A composição soma {soma} e o {rotulo} do contrato é {alvo}.",
                soma_recebida=float(soma), valor_esperado=float(alvo),
                diferenca=float(alvo - soma),
                dica=("Ajuste os valores de `total` dos itens (ou o valor do contrato) até "
                      "fechar. O contrato não pode sair com tabela que não soma o valor "
                      "por extenso — é convite a disputa."))
        await db.execute(text("DELETE FROM contract_items WHERE contract_id::text=:c"), {"c": r["cid"]})
        for i in itens:
            # `quantidade` é apelido aceito de `qtd`: o exemplo do schema dizia uma coisa e o
            # código lia outra, e quem escreveu `quantidade: 1` viu `quantity: 0` gravado.
            qtd = int(i.get("qtd") or i.get("quantidade") or 0)
            total = Decimal(str(i.get("total") or 0))
            # no único, `service_type` carrega o PAPEL da parcela (entrada/parcela/retida),
            # que é o que o render lê para montar a Cláusula 3.2; no recorrente segue sendo
            # o tipo de serviço, como sempre foi.
            st = (i.get("tipo") or "parcela") if unico else (r["tipo_servico"] or "maodeobra")
            await db.execute(
                text(
                    "INSERT INTO contract_items (id, contract_id, service_type, service_name, description, "
                    "quantity, unit_price, total_price, notes, is_active, created_at) "
                    "VALUES (:i, CAST(:c AS uuid), :st, :n, :d, :q, :u, :t, :ob, true, now())"
                ),
                {
                    "i": str(uuid.uuid4()),
                    "c": r["cid"],
                    "st": st,
                    "n": i.get("nome") or "—",
                    "d": i.get("descricao") or "",
                    "q": qtd,
                    "u": (total / qtd) if qtd else total,
                    "t": total,
                    "ob": i.get("vencimento") or i.get("notes") or None,
                },
            )
        feitos.append(f"composição gravada ({len(itens)} itens, soma {soma})")

    # ⭐ 18/09/2026 — §5 da SPEC: ATOMICIDADE. Este `commit` era o primeiro de dois, e
    # acontecia ANTES do render. Emissão que falhava no render (o caso do CTR-2026-00025)
    # deixava `payment_day`, `grace_period_days`, `sla_config` e os itens
    # APAGADOS-E-REINSERIDOS no banco, com a resposta dizendo `ok: false`. O dono mediu:
    # `grace_period_days` foi de 60 para 30 e os `contract_items` ganharam ids novos a cada
    # tentativa recusada. Uma tentativa abortada por engano sobrescrevia itens de um contrato
    # que já estava certo.
    #
    # Agora quem chama decide. O único chamador é a emissão, que confirma DEPOIS de o
    # documento existir — falhou, nada muda. O default segue `True` para não mudar o
    # comportamento de nenhum chamador futuro que não saiba disso.
    if commit:
        await db.commit()
    return feitos


# ── BRIEFING de contrato NOVO ─────────────────────────────────────────────────────────
# Pedido do Jordan (21/08): ao solicitar um contrato novo, o sistema tem de perguntar o
# que é preciso ANTES de tentar montar — que serviço, se é misto, quem é o cliente, quantos
# de cada função. Vale igual no jurídico, no chat e no Cowork.
#
# O catálogo de funções NÃO é inventado aqui: vem de `cct_cargos`, a convenção coletiva
# vigente, que é quem define o piso de cada função. Oferecer função fora da CCT seria
# vender o que não se sabe custear.

# Serviços que a Conecta Mais presta, e as funções da CCT que cada um mobiliza.
CATALOGO = {
    "portaria": {
        "rotulo": "Portaria / Controle de acesso",
        "cargos": ["PORTEIROS AGENTE DE PORTARIA GUARDETE", "CONTROLADOR DE ACESSO", "LIDER DE PORTARIA"],
        "modelo_service_type": "portaria_mao_de_obra",
    },
    "servicos_gerais": {
        "rotulo": "Serviços gerais / Limpeza (ASG)",
        "cargos": [
            "SERVICOS GERAIS FAXINEIRO",
            "LIDER DE SERVICOS GERAIS",
            "ENCARREGADO DE SERVICOS GERAIS E SUPERVISOR",
        ],
        "modelo_service_type": "servicos_gerais",
    },
    "jardinagem": {
        "rotulo": "Jardinagem",
        "cargos": ["JARDINEIROS", "LIDER DE JARDINAGEM"],
        "modelo_service_type": "jardinagem",
    },
    "piscina": {"rotulo": "Piscina", "cargos": ["PISCINEIRO"], "modelo_service_type": "piscina"},
    "zeladoria": {
        "rotulo": "Zeladoria",
        "cargos": ["ZELADOR RESIDENTE CONDOMINIOS"],
        "modelo_service_type": "zeladoria",
    },
    # A eletrônica tem DUAS naturezas comerciais, e até 09/09/2026 o catálogo só conhecia
    # uma: todo negócio eletrônico caía no modelo de MANUTENÇÃO, que é mensal. Um
    # fornecimento com instalação — controle de acesso, CFTV novo — não é mensalidade: é
    # valor fechado, com entrada, parcelas e parcela retida até o Termo de Entrega.
    # Emitir um pelo modelo do outro põe no instrumento uma cláusula de reajuste anual
    # sobre um serviço que acaba em 60 dias.
    "eletronica": {
        "rotulo": "Segurança eletrônica — MANUTENÇÃO mensal (CFTV, cancelas, cerca)",
        "cargos": [],
        "modelo_service_type": "manutencao_cftv",
    },
    # Portaria remota: mensal, eletrônica, com locação de equipamento. É a TERCEIRA
    # natureza eletrônica — manutenção mantém o que já existe, instalação fornece e
    # instala, remota opera à distância e aluga. Sem esta linha o modelo criado em
    # 10/09/2026 existia e ninguém conseguia escolhê-lo pela tela.
    "portaria_remota": {
        "rotulo": "Portaria REMOTA — central 24h + locação de equipamentos (mensal)",
        "cargos": [],
        "modelo_service_type": "portaria_remota",
    },
    "eletronica_instalacao": {
        "rotulo": "Segurança eletrônica — FORNECIMENTO e instalação (valor único)",
        "cargos": [],
        "modelo_service_type": "eletronica_servico_unico",
        "natureza": "one_time",
    },
}


async def briefing(
    db: AsyncSession,
    *,
    servicos: list[str] | None = None,
    cliente_cnpj: str | None = None,
    cliente_nome: str | None = None,
) -> dict:
    """O questionário de um contrato NOVO, já respondendo o que o banco sabe.

    Duas passadas de propósito: na primeira o usuário só diz QUAIS serviços; na segunda,
    com os serviços escolhidos, o briefing devolve as funções daquele(s) serviço(s) com o
    piso da CCT — perguntar "quantos agentes?" antes de saber que é portaria seria pedir
    para o usuário adivinhar o formulário.
    """
    servicos = [s.strip().lower() for s in (servicos or []) if s and s.strip()]
    invalidos = [s for s in servicos if s not in CATALOGO]
    if invalidos:
        return {
            "status": "servico_desconhecido",
            "invalidos": invalidos,
            "servicos_disponiveis": [{"chave": k, "rotulo": v["rotulo"]} for k, v in CATALOGO.items()],
            "resumo": f"Não conheço o(s) serviço(s) {', '.join(invalidos)}. Escolha entre os disponíveis.",
        }

    # cliente: existe no cadastro?
    cli = None
    if cliente_cnpj or cliente_nome:
        so_num = "".join(ch for ch in (cliente_cnpj or "") if ch.isdigit())
        cli = (
            (
                await db.execute(
                    text(
                        "SELECT id::text, name, document_number FROM clients "
                        "WHERE (:d <> '' AND regexp_replace(coalesce(document_number,''), '\\D', '', 'g') = :d) "
                        "   OR (:n <> '' AND name ILIKE '%' || :n || '%') LIMIT 1"
                    ),
                    {"d": so_num, "n": (cliente_nome or "").strip()},
                )
            )
            .mappings()
            .first()
        )

    if not servicos:
        return {
            "status": "briefing",
            "etapa": "1 de 2 — que serviço será contratado",
            "cliente_encontrado": dict(cli) if cli else None,
            "perguntas": [
                {
                    "campo": "servicos",
                    "pergunta": "Que serviço(s) este contrato cobre? Pode ser mais de um "
                    "(contrato misto) — responda com as chaves.",
                    "opcoes": [{"chave": k, "rotulo": v["rotulo"]} for k, v in CATALOGO.items()],
                },
                {
                    "campo": "cliente",
                    "pergunta": (
                        "Qual o cliente? Informe CNPJ (puxo nome e endereço da Receita) "
                        "ou o nome, se já estiver no cadastro."
                        if not cli
                        else f"Confirma que o cliente é {cli['name']} ({cli['document_number']})?"
                    ),
                },
            ],
            "resumo": "Para montar o contrato preciso saber o serviço e o cliente. "
            "Depois pergunto a composição de cada função.",
        }

    # etapa 2: funções da CCT para os serviços escolhidos
    nomes = [c for s in servicos for c in CATALOGO[s]["cargos"]]
    pisos = []
    if nomes:
        pisos = [
            dict(r)
            for r in (
                await db.execute(
                    text(
                        "SELECT cargo_nome, piso_salarial FROM cct_cargos "
                        "WHERE coalesce(is_active,true) AND cargo_nome = ANY(:n) ORDER BY cargo_nome"
                    ),
                    {"n": nomes},
                )
            )
            .mappings()
            .all()
        ]

    modelos = [
        dict(r)
        for r in (
            await db.execute(
                text(
                    "SELECT id::text, name, service_type FROM contract_templates "
                    "WHERE coalesce(is_active,true) ORDER BY name"
                )
            )
        )
        .mappings()
        .all()
    ]
    tipos = {CATALOGO[s]["modelo_service_type"] for s in servicos}
    sugeridos = [m for m in modelos if m["service_type"] in tipos]

    misto = len(servicos) > 1
    return {
        "status": "briefing",
        "etapa": "2 de 2 — composição e condições",
        "servicos": [CATALOGO[s]["rotulo"] for s in servicos],
        "contrato_misto": misto,
        "cliente_encontrado": dict(cli) if cli else None,
        "funcoes_disponiveis": pisos,
        "modelos_sugeridos": sugeridos,
        "modelos_todos": modelos,
        "perguntas": [
            {
                "campo": "itens",
                "pergunta": "Quantos profissionais de cada função, em que turno, e qual o "
                "subtotal mensal de cada linha? A soma será o valor do contrato.",
                "exemplo": "AGP Diurno 2 = 10605.78 · AGP Noturno 2 = 11494.22",
            },
            {"campo": "valor_mensal", "pergunta": "Qual o valor mensal fechado com o cliente?"},
            {"campo": "vigencia", "pergunta": "Início e prazo (em meses).", "exemplo": "01/09/2026, 24 meses"},
            {"campo": "payment_day", "pergunta": "Dia do mês em que vence a mensalidade.", "exemplo": "8"},
            {"campo": "grace_period_days", "pergunta": "Em quantos dias vence o primeiro pagamento?", "exemplo": "90"},
            {
                "campo": "representante",
                "pergunta": "Nome e CPF de quem assina pelo cliente (síndico/representante legal).",
            },
        ]
        + (
            [
                {
                    "campo": "template_id",
                    "pergunta": "Ainda não há modelo cadastrado para este serviço — qual usar?",
                    "opcoes": modelos,
                }
            ]
            if not sugeridos
            else []
        ),
        "aviso": (
            "Contrato MISTO: hoje o modelo cadastrado é de PORTARIA. Um contrato que "
            "some portaria com outro serviço precisa de modelo próprio ou de aditivo — "
            "não monte no de portaria sem revisar o objeto."
            if misto
            else None
        ),
        "resumo": (
            f"Serviço(s): {', '.join(CATALOGO[s]['rotulo'] for s in servicos)}"
            + (" (MISTO)" if misto else "")
            + f" · {len(pisos)} função(ões) da CCT disponíveis"
            + (f" · modelo sugerido: {sugeridos[0]['name']}" if sugeridos else " · SEM modelo para este serviço")
        ),
    }


# ── CRIAR contrato novo, já ligado ao modelo ──────────────────────────────────────────
# O furo que o Jordan apontou em 23/08: havia briefing (o que perguntar) e emissão (render
# do que já existe), e NADA que criasse o contrato entre os dois. `criar_contrato` do MCP é
# o create genérico do CRM — não grava template_id, tipo_servico nem empresa_id, então o
# contrato nascia sem modelo e o render RECUSAVA. As três superfícies ficavam pela metade.
EMPRESA_POR_TIPO = {
    # mão de obra humanizada é da Patrimonial; segurança eletrônica é da Eletrônica.
    # Mesma regra que `contract_render.resolver_contratada` aplica na hora de imprimir —
    # aqui ela decide na hora de CRIAR, para as duas nunca divergirem.
    "maodeobra": "7d79ed12-d480-4906-b2e0-2b2c4d299bab",
    "portaria_mao_de_obra": "7d79ed12-d480-4906-b2e0-2b2c4d299bab",
    "servicos_gerais": "7d79ed12-d480-4906-b2e0-2b2c4d299bab",
    "jardinagem": "7d79ed12-d480-4906-b2e0-2b2c4d299bab",
    "piscina": "7d79ed12-d480-4906-b2e0-2b2c4d299bab",
    "zeladoria": "7d79ed12-d480-4906-b2e0-2b2c4d299bab",
    "manutencao_cftv": "619a3df1-8bce-49ce-b77a-04f80a0e8491",
    "portaria_remota": "619a3df1-8bce-49ce-b77a-04f80a0e8491",
    "seguranca_eletronica": "619a3df1-8bce-49ce-b77a-04f80a0e8491",
    # fornecimento + instalação: eletrônica, como toda segurança eletrônica (09/09/2026)
    "eletronica_servico_unico": "619a3df1-8bce-49ce-b77a-04f80a0e8491",
}


async def criar_contrato(
    db: AsyncSession,
    *,
    cliente_documento: str,
    modalidade: str,
    valor_mensal: float,
    vigencia_inicio: str,
    vigencia_meses: int = 12,
    dia_vencimento: int | None = None,
    renovacao_aviso_dias: int = 30,
    carencia_dias: int | None = None,
    proposal_id: str | None = None,
) -> dict:
    """Cria o contrato JÁ ligado ao modelo, ao tipo de serviço e à empresa emitente.

    Recusa em vez de inventar:
      · cliente que não está no CRM — cadastrar cliente é decisão comercial, não do gerador;
      · modalidade fora do catálogo;
      · modalidade sem modelo cadastrado (o contrato nasceria impossível de renderizar).
    """
    from datetime import date, timedelta  # noqa: PLC0415

    if modalidade not in CATALOGO:
        return {
            "status": "modalidade_desconhecida",
            "informada": modalidade,
            "disponiveis": [{"chave": k, "rotulo": v["rotulo"]} for k, v in CATALOGO.items()],
        }
    tipo = CATALOGO[modalidade]["modelo_service_type"]
    natureza = CATALOGO[modalidade].get("natureza") or "recurring"
    unico = natureza == "one_time"

    doc = "".join(c for c in (cliente_documento or "") if c.isdigit())
    cli = (
        (
            await db.execute(
                text(
                    "SELECT id::text, name FROM clients "
                    "WHERE regexp_replace(coalesce(document_number,''),'[^0-9]','','g') = :d"
                ),
                {"d": doc},
            )
        )
        .mappings()
        .first()
    )
    if not cli:
        return {
            "status": "cliente_nao_cadastrado",
            "documento": cliente_documento,
            "resumo": "Não há cliente com este CNPJ no CRM. Cadastre o cliente antes — "
            "não crio contrato para cliente que não existe.",
        }

    tpl = (
        (
            await db.execute(
                text(
                    "SELECT id::text, name FROM contract_templates "
                    "WHERE service_type = :t AND coalesce(is_active, true) "
                    "ORDER BY version DESC LIMIT 1"
                ),
                {"t": tipo},
            )
        )
        .mappings()
        .first()
    )
    if not tpl:
        return {
            "status": "sem_modelo",
            "tipo_servico": tipo,
            "resumo": f"Não há modelo cadastrado para '{tipo}'. Sem modelo o contrato nasce impossível de emitir.",
        }

    try:
        ini = date.fromisoformat(str(vigencia_inicio)[:10])
    except ValueError:
        return {
            "status": "data_invalida",
            "vigencia_inicio": vigencia_inicio,
            "resumo": "Informe a vigência no formato AAAA-MM-DD.",
        }
    meses = int(vigencia_meses or 12)
    ano, mes = divmod((ini.month - 1) + meses, 12)
    try:
        fim = ini.replace(year=ini.year + ano, month=mes + 1) - timedelta(days=1)
    except ValueError:  # 31 de mês que o mês-alvo não tem
        fim = ini.replace(year=ini.year + ano, month=mes + 1, day=28) - timedelta(days=1)

    ultimo = (
        await db.execute(text("SELECT max(contract_number) FROM contracts WHERE contract_number ~ '^CTR-[0-9]{4}-'"))
    ).scalar() or f"CTR-{ini.year}-00000"
    numero = f"CTR-{ini.year}-{int(ultimo.rsplit('-', 1)[-1]) + 1:05d}"

    await db.execute(
        text("""
        INSERT INTO contracts
            (id, contract_number, client_id, template_id, empresa_id, tipo_servico,
             contract_type, status, name, monthly_value, total_value, payment_day,
             start_date, end_date,
             renewal_notification_days, notice_period_days, grace_period_days,
             proposal_id, is_active, created_at, updated_at)
        VALUES (gen_random_uuid(), :n, CAST(:c AS uuid), CAST(:t AS uuid), CAST(:e AS uuid),
                :ts, :nat, 'draft', :nome, :v, :tot, :pd, :ini, :fim, :rn, 30, :car,
                CAST(:prop AS uuid), true, now(), now())"""),
        {
            "n": numero,
            "c": cli["id"],
            "t": tpl["id"],
            "e": EMPRESA_POR_TIPO.get(tipo),
            "ts": tipo,
            "nome": f"{CATALOGO[modalidade]['rotulo']} — {cli['name']}",
            # A NATUREZA vem da modalidade. Sem isto, um fornecimento com instalação nascia
            # `recurring` com o valor da obra em `monthly_value` — o contrato passaria a
            # anunciar mensalidade de R$ 46 mil e a entrar no MRR como receita recorrente.
            "nat": natureza,
            "v": (0 if unico else valor_mensal),
            "tot": (valor_mensal if unico else 0),
            "pd": (None if unico else dia_vencimento),
            "ini": ini,
            "fim": (None if unico else fim),
            # grace_period_days é NOT NULL COM default: passar None explícito ANULA o default
            # e viola a constraint. Sem carência negociada, o valor é 0, não nulo.
            "rn": renovacao_aviso_dias,
            "car": carencia_dias or 0,
            # a origem fica rastreada: de qual proposta este contrato nasceu
            "prop": proposal_id,
        },
    )
    await db.commit()

    sit = await diagnosticar(db, numero)
    return {
        "status": "criado",
        "contrato": numero,
        "cliente": cli["name"],
        "proposta_origem": proposal_id,
        "modelo": tpl["name"],
        "tipo_servico": tipo,
        "vigencia": f"{ini.isoformat()} a {fim.isoformat()} ({meses} meses)",
        "pronto_para_emitir": sit.pronto,
        "perguntas": [{"campo": p.campo, "pergunta": p.pergunta, "exemplo": p.exemplo} for p in sit.pendencias],
        "resumo": (
            f"{numero} criado para {cli['name']} pelo modelo '{tpl['name']}'. "
            + ("Pronto para emitir." if sit.pronto else f"Faltam {len(sit.pendencias)} informação(ões).")
        ),
    }
