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

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Só estes dois emitem contrato. Decisão do Jordan (21/08): vale para chat, jurídico e
# Cowork — a superfície muda, a parede é a mesma.
EMITENTES = {"jjesus@conectamais.pro", "pjesus@conectamais.pro"}


class NaoAutorizado(PermissionError):
    pass


def pode_emitir(user) -> bool:
    email = (getattr(user, "email", "") or "").strip().lower()
    return email in EMITENTES


def exigir_emitente(user) -> None:
    if not pode_emitir(user):
        raise NaoAutorizado(
            "Emitir contrato é restrito ao Jordan e à Pyetra. "
            "Consultar e listar contratos segue liberado.")


@dataclass
class Pendencia:
    campo: str
    pergunta: str      # o que o agente pergunta ao humano, em português
    onde: str          # onde o dado será gravado — some no relatório, não no contrato
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
       cl.name AS cliente, cl.id::text AS client_id,
       t.name AS modelo_nome,
       (SELECT count(*) FROM contract_items i
         WHERE i.contract_id = c.id AND coalesce(i.is_active, true)) AS n_itens,
       (SELECT k.name FROM crm_contacts k
         WHERE k.client_id = c.client_id
           AND (k.role ILIKE '%representante%' OR k.role ILIKE '%s%ndic%' OR k.role ILIKE '%legal%')
         ORDER BY k.is_primary DESC NULLS LAST LIMIT 1) AS representante,
       (SELECT k.notes FROM crm_contacts k
         WHERE k.client_id = c.client_id
           AND (k.role ILIKE '%representante%' OR k.role ILIKE '%s%ndic%' OR k.role ILIKE '%legal%')
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

    s = Situacao(contrato=r["contract_number"], cliente=r["cliente"] or "—",
                 valor_mensal=Decimal(str(r["monthly_value"] or 0)),
                 modelo_id=r["template_id"], modelo_nome=r["modelo_nome"])

    if not r["template_id"]:
        s.pendencias.append(Pendencia(
            "template_id",
            "Qual modelo de contrato usar? (o contrato ainda não está vinculado a nenhum)",
            "contracts.template_id"))
    if not r["representante"]:
        s.pendencias.append(Pendencia(
            "representante",
            f"Quem assina pelo {r['cliente'] or 'cliente'}? Preciso do nome completo do "
            "representante legal (síndico).",
            "crm_contacts", "Hely Carvalho"))
    if not (r["representante_cpf"] or "").strip():
        s.pendencias.append(Pendencia(
            "representante_cpf", "Qual o CPF de quem assina?", "crm_contacts",
            "562.043.372-20"))
    if not r["payment_day"]:
        s.pendencias.append(Pendencia(
            "payment_day", "Em que dia do mês vence a mensalidade?", "contracts.payment_day", "8"))
    if not r["grace_period_days"]:
        s.pendencias.append(Pendencia(
            "grace_period_days",
            "Em quantos dias vence o PRIMEIRO pagamento, contados da assinatura?",
            "contracts.grace_period_days", "90"))
    if not r["n_itens"]:
        s.pendencias.append(Pendencia(
            "itens",
            "Como se compõe o valor mensal? Preciso da quantidade e do subtotal de cada "
            f"função — a soma tem de fechar em {r['monthly_value']}.",
            "contract_items", "AGP Diurno 2 = 10605.78 · AGP Noturno 2 = 11494.22"))
    if not r["start_date"] or not r["end_date"]:
        s.pendencias.append(Pendencia(
            "vigencia", "Qual o período de vigência (início e término)?",
            "contracts.start_date/end_date", "01/09/2026 a 31/08/2028"))
    return s


async def completar(db: AsyncSession, chave: str, **dados) -> list[str]:
    """Grava as respostas NO LUGAR CERTO de cada uma. Devolve o que foi feito."""
    r = (await db.execute(text(_SQL), {"k": chave})).mappings().first()
    if not r:
        raise LookupError(f"Contrato não encontrado: {chave}")
    feitos: list[str] = []

    if dados.get("template_id"):
        await db.execute(text("UPDATE contracts SET template_id=CAST(:t AS uuid), updated_at=now() "
                              "WHERE id::text=:c"), {"t": dados["template_id"], "c": r["cid"]})
        feitos.append("modelo vinculado ao contrato")

    if dados.get("representante"):
        existe = (await db.execute(text(
            "SELECT id::text FROM crm_contacts WHERE client_id::text=:c "
            "AND (role ILIKE '%representante%' OR role ILIKE '%s%ndic%') LIMIT 1"),
            {"c": r["client_id"]})).scalar()
        cpf = (dados.get("representante_cpf") or "").strip()
        if existe:
            await db.execute(text("UPDATE crm_contacts SET name=:n, notes=coalesce(nullif(:cpf,''), notes), "
                                  "updated_at=now() WHERE id::text=:i"),
                             {"n": dados["representante"], "cpf": cpf, "i": existe})
        else:
            await db.execute(text(
                "INSERT INTO crm_contacts (id, client_id, name, role, notes, is_primary, created_at, updated_at) "
                "VALUES (:i, CAST(:c AS uuid), :n, 'Representante legal', :cpf, false, now(), now())"),
                {"i": str(uuid.uuid4()), "c": r["client_id"], "n": dados["representante"], "cpf": cpf})
        feitos.append(f"representante legal: {dados['representante']}")
    elif dados.get("representante_cpf"):
        await db.execute(text(
            "UPDATE crm_contacts SET notes=:cpf, updated_at=now() WHERE client_id::text=:c "
            "AND (role ILIKE '%representante%' OR role ILIKE '%s%ndic%')"),
            {"cpf": dados["representante_cpf"], "c": r["client_id"]})
        feitos.append("CPF do representante gravado")

    campos = {"payment_day": "dia de vencimento", "grace_period_days": "carência do 1º pagamento"}
    for col, rot in campos.items():
        if dados.get(col) is not None:
            await db.execute(text(f"UPDATE contracts SET {col}=:v, updated_at=now() WHERE id::text=:c"),  # noqa: S608
                             {"v": int(dados[col]), "c": r["cid"]})
            feitos.append(f"{rot}: {dados[col]}")

    itens = dados.get("itens")
    if itens:
        # TRAVA DE DINHEIRO: a composição tem de fechar com o valor acordado. Um contrato
        # cuja tabela não soma o valor por extenso é convite a disputa.
        soma = sum(Decimal(str(i.get("total") or 0)) for i in itens)
        mensal = Decimal(str(r["monthly_value"] or 0))
        if soma != mensal:
            raise ValueError(
                f"A composição soma {soma} e o valor mensal do contrato é {mensal}. "
                "Ajuste os subtotais — o contrato não pode sair com tabela que não fecha.")
        await db.execute(text("DELETE FROM contract_items WHERE contract_id::text=:c"), {"c": r["cid"]})
        for i in itens:
            qtd = int(i.get("qtd") or 0)
            total = Decimal(str(i.get("total") or 0))
            await db.execute(text(
                "INSERT INTO contract_items (id, contract_id, service_type, service_name, description, "
                "quantity, unit_price, total_price, is_active, created_at) "
                "VALUES (:i, CAST(:c AS uuid), :st, :n, :d, :q, :u, :t, true, now())"),
                {"i": str(uuid.uuid4()), "c": r["cid"], "st": r["tipo_servico"] or "maodeobra",
                 "n": i.get("nome") or "—", "d": i.get("descricao") or "",
                 "q": qtd, "u": (total / qtd) if qtd else total, "t": total})
        feitos.append(f"composição gravada ({len(itens)} itens, soma {soma})")

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
        "cargos": ["PORTEIROS AGENTE DE PORTARIA GUARDETE", "CONTROLADOR DE ACESSO",
                   "LIDER DE PORTARIA"],
        "modelo_service_type": "portaria_mao_de_obra",
    },
    "servicos_gerais": {
        "rotulo": "Serviços gerais / Limpeza (ASG)",
        "cargos": ["SERVICOS GERAIS FAXINEIRO", "LIDER DE SERVICOS GERAIS",
                   "ENCARREGADO DE SERVICOS GERAIS E SUPERVISOR"],
        "modelo_service_type": "servicos_gerais",
    },
    "jardinagem": {
        "rotulo": "Jardinagem",
        "cargos": ["JARDINEIROS", "LIDER DE JARDINAGEM"],
        "modelo_service_type": "jardinagem",
    },
    "piscina": {"rotulo": "Piscina", "cargos": ["PISCINEIRO"], "modelo_service_type": "piscina"},
    "zeladoria": {"rotulo": "Zeladoria", "cargos": ["ZELADOR RESIDENTE CONDOMINIOS"],
                  "modelo_service_type": "zeladoria"},
    "eletronica": {
        "rotulo": "Segurança eletrônica / CFTV (sem mão de obra fixa)",
        "cargos": [], "modelo_service_type": "manutencao_cftv",
    },
}


async def briefing(db: AsyncSession, *, servicos: list[str] | None = None,
                   cliente_cnpj: str | None = None, cliente_nome: str | None = None) -> dict:
    """O questionário de um contrato NOVO, já respondendo o que o banco sabe.

    Duas passadas de propósito: na primeira o usuário só diz QUAIS serviços; na segunda,
    com os serviços escolhidos, o briefing devolve as funções daquele(s) serviço(s) com o
    piso da CCT — perguntar "quantos agentes?" antes de saber que é portaria seria pedir
    para o usuário adivinhar o formulário.
    """
    servicos = [s.strip().lower() for s in (servicos or []) if s and s.strip()]
    invalidos = [s for s in servicos if s not in CATALOGO]
    if invalidos:
        return {"status": "servico_desconhecido", "invalidos": invalidos,
                "servicos_disponiveis": [{"chave": k, "rotulo": v["rotulo"]} for k, v in CATALOGO.items()],
                "resumo": f"Não conheço o(s) serviço(s) {', '.join(invalidos)}. Escolha entre os disponíveis."}

    # cliente: existe no cadastro?
    cli = None
    if cliente_cnpj or cliente_nome:
        so_num = "".join(ch for ch in (cliente_cnpj or "") if ch.isdigit())
        cli = (await db.execute(text(
            "SELECT id::text, name, document_number FROM clients "
            "WHERE (:d <> '' AND regexp_replace(coalesce(document_number,''), '\\D', '', 'g') = :d) "
            "   OR (:n <> '' AND name ILIKE '%' || :n || '%') LIMIT 1"),
            {"d": so_num, "n": (cliente_nome or "").strip()})).mappings().first()

    if not servicos:
        return {
            "status": "briefing",
            "etapa": "1 de 2 — que serviço será contratado",
            "cliente_encontrado": dict(cli) if cli else None,
            "perguntas": [
                {"campo": "servicos",
                 "pergunta": "Que serviço(s) este contrato cobre? Pode ser mais de um "
                             "(contrato misto) — responda com as chaves.",
                 "opcoes": [{"chave": k, "rotulo": v["rotulo"]} for k, v in CATALOGO.items()]},
                {"campo": "cliente",
                 "pergunta": ("Qual o cliente? Informe CNPJ (puxo nome e endereço da Receita) "
                              "ou o nome, se já estiver no cadastro."
                              if not cli else
                              f"Confirma que o cliente é {cli['name']} ({cli['document_number']})?")},
            ],
            "resumo": "Para montar o contrato preciso saber o serviço e o cliente. "
                      "Depois pergunto a composição de cada função.",
        }

    # etapa 2: funções da CCT para os serviços escolhidos
    nomes = [c for s in servicos for c in CATALOGO[s]["cargos"]]
    pisos = []
    if nomes:
        pisos = [dict(r) for r in (await db.execute(text(
            "SELECT cargo_nome, piso_salarial FROM cct_cargos "
            "WHERE coalesce(is_active,true) AND cargo_nome = ANY(:n) ORDER BY cargo_nome"),
            {"n": nomes})).mappings().all()]

    modelos = [dict(r) for r in (await db.execute(text(
        "SELECT id::text, name, service_type FROM contract_templates "
        "WHERE coalesce(is_active,true) ORDER BY name"))).mappings().all()]
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
            {"campo": "itens",
             "pergunta": "Quantos profissionais de cada função, em que turno, e qual o "
                         "subtotal mensal de cada linha? A soma será o valor do contrato.",
             "exemplo": "AGP Diurno 2 = 10605.78 · AGP Noturno 2 = 11494.22"},
            {"campo": "valor_mensal", "pergunta": "Qual o valor mensal fechado com o cliente?"},
            {"campo": "vigencia", "pergunta": "Início e prazo (em meses).", "exemplo": "01/09/2026, 24 meses"},
            {"campo": "payment_day", "pergunta": "Dia do mês em que vence a mensalidade.", "exemplo": "8"},
            {"campo": "grace_period_days",
             "pergunta": "Em quantos dias vence o primeiro pagamento?", "exemplo": "90"},
            {"campo": "representante",
             "pergunta": "Nome e CPF de quem assina pelo cliente (síndico/representante legal)."},
        ]
        + ([{"campo": "template_id",
             "pergunta": "Ainda não há modelo cadastrado para este serviço — qual usar?",
             "opcoes": modelos}] if not sugeridos else []),
        "aviso": ("Contrato MISTO: hoje o modelo cadastrado é de PORTARIA. Um contrato que "
                  "some portaria com outro serviço precisa de modelo próprio ou de aditivo — "
                  "não monte no de portaria sem revisar o objeto."
                  if misto else None),
        "resumo": (f"Serviço(s): {', '.join(CATALOGO[s]['rotulo'] for s in servicos)}"
                   + (" (MISTO)" if misto else "")
                   + f" · {len(pisos)} função(ões) da CCT disponíveis"
                   + (f" · modelo sugerido: {sugeridos[0]['name']}" if sugeridos else
                      " · SEM modelo para este serviço")),
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
}


async def criar_contrato(db: AsyncSession, *, cliente_documento: str, modalidade: str,
                         valor_mensal: float, vigencia_inicio: str,
                         vigencia_meses: int = 12, dia_vencimento: int | None = None,
                         renovacao_aviso_dias: int = 30,
                         carencia_dias: int | None = None) -> dict:
    """Cria o contrato JÁ ligado ao modelo, ao tipo de serviço e à empresa emitente.

    Recusa em vez de inventar:
      · cliente que não está no CRM — cadastrar cliente é decisão comercial, não do gerador;
      · modalidade fora do catálogo;
      · modalidade sem modelo cadastrado (o contrato nasceria impossível de renderizar).
    """
    from datetime import date, timedelta  # noqa: PLC0415

    if modalidade not in CATALOGO:
        return {"status": "modalidade_desconhecida", "informada": modalidade,
                "disponiveis": [{"chave": k, "rotulo": v["rotulo"]} for k, v in CATALOGO.items()]}
    tipo = CATALOGO[modalidade]["modelo_service_type"]

    doc = "".join(c for c in (cliente_documento or "") if c.isdigit())
    cli = (await db.execute(text(
        "SELECT id::text, name FROM clients "
        "WHERE regexp_replace(coalesce(document_number,''),'[^0-9]','','g') = :d"),
        {"d": doc})).mappings().first()
    if not cli:
        return {"status": "cliente_nao_cadastrado", "documento": cliente_documento,
                "resumo": "Não há cliente com este CNPJ no CRM. Cadastre o cliente antes — "
                          "não crio contrato para cliente que não existe."}

    tpl = (await db.execute(text(
        "SELECT id::text, name FROM contract_templates "
        "WHERE service_type = :t AND coalesce(is_active, true) "
        "ORDER BY version DESC LIMIT 1"), {"t": tipo})).mappings().first()
    if not tpl:
        return {"status": "sem_modelo", "tipo_servico": tipo,
                "resumo": f"Não há modelo cadastrado para '{tipo}'. Sem modelo o contrato "
                          "nasce impossível de emitir."}

    try:
        ini = date.fromisoformat(str(vigencia_inicio)[:10])
    except ValueError:
        return {"status": "data_invalida", "vigencia_inicio": vigencia_inicio,
                "resumo": "Informe a vigência no formato AAAA-MM-DD."}
    meses = int(vigencia_meses or 12)
    ano, mes = divmod((ini.month - 1) + meses, 12)
    try:
        fim = ini.replace(year=ini.year + ano, month=mes + 1) - timedelta(days=1)
    except ValueError:  # 31 de mês que o mês-alvo não tem
        fim = ini.replace(year=ini.year + ano, month=mes + 1, day=28) - timedelta(days=1)

    ultimo = (await db.execute(text(
        "SELECT max(contract_number) FROM contracts WHERE contract_number ~ '^CTR-[0-9]{4}-'"
    ))).scalar() or f"CTR-{ini.year}-00000"
    numero = f"CTR-{ini.year}-{int(ultimo.rsplit('-', 1)[-1]) + 1:05d}"

    await db.execute(text("""
        INSERT INTO contracts
            (id, contract_number, client_id, template_id, empresa_id, tipo_servico,
             contract_type, status, name, monthly_value, payment_day, start_date, end_date,
             renewal_notification_days, notice_period_days, grace_period_days,
             is_active, created_at, updated_at)
        VALUES (gen_random_uuid(), :n, CAST(:c AS uuid), CAST(:t AS uuid), CAST(:e AS uuid),
                :ts, 'recurring', 'draft', :nome, :v, :pd, :ini, :fim, :rn, 30, :car,
                true, now(), now())"""),
        {"n": numero, "c": cli["id"], "t": tpl["id"], "e": EMPRESA_POR_TIPO.get(tipo),
         "ts": tipo, "nome": f"{CATALOGO[modalidade]['rotulo']} — {cli['name']}",
         "v": valor_mensal, "pd": dia_vencimento, "ini": ini, "fim": fim,
         # grace_period_days é NOT NULL COM default: passar None explícito ANULA o default
         # e viola a constraint. Sem carência negociada, o valor é 0, não nulo.
         "rn": renovacao_aviso_dias, "car": carencia_dias or 0})
    await db.commit()

    sit = await diagnosticar(db, numero)
    return {
        "status": "criado", "contrato": numero, "cliente": cli["name"],
        "modelo": tpl["name"], "tipo_servico": tipo,
        "vigencia": f"{ini.isoformat()} a {fim.isoformat()} ({meses} meses)",
        "pronto_para_emitir": sit.pronto,
        "perguntas": [{"campo": p.campo, "pergunta": p.pergunta, "exemplo": p.exemplo}
                      for p in sit.pendencias],
        "resumo": (f"{numero} criado para {cli['name']} pelo modelo '{tpl['name']}'. "
                   + ("Pronto para emitir." if sit.pronto
                      else f"Faltam {len(sit.pendencias)} informação(ões).")),
    }
