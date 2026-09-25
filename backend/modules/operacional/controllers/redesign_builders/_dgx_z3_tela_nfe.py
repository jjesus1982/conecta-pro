"""DGX Z3 — A tela de emitir NF-e (modelo 55) e o DANFE (24/09/2026).

O dono pediu «preciso urgente emitir notas fiscais». Antes desta frente havia MOTOR e não havia
PORTA: `financial/integrations/nfe_provider.py` monta, assina e transmite a NF-e pela PyNFe e
sabe cancelar com `xJust`; `fiscal_contabil/notas_fiscais/nfe/controller.py` tem a chave de
acesso, o XML e o envio à SEFAZ-AM — mas o seu bloco «Endpoints» termina VAZIO (medido em
24/09: 476 linhas, zero rotas). As tabelas `nfes` (90 colunas) e `nfe_itens` (35) já existiam
com 2 notas, ambas REJEITADAS. Ninguém no ERP tinha como emitir uma nota de mercadoria.

A REGRA QUE NÃO SE QUEBRA
-------------------------
Nota fiscal autorizada em produção é IRREVERSÍVEL. Por isso:

  · o campo `ambiente` de `nfe-nova` nasce em **homologação** (e o oráculo fica vermelho se
    alguém trocar o padrão);
  · `nfe-nova` NUNCA transmite em produção — escolher «produção» ali grava o rascunho e manda
    a pessoa para a tela `nfe-producao`, que é `gated: True` + `confirm` + OTP humano, o mesmo
    padrão do pagamento em lote desta casa (`redesign_write_gate.money_gov`);
  · `nfe-preview` é leitura pura: nenhuma linha dela tem ação de escrita;
  · o DANFE de homologação — e o de qualquer nota que ainda não esteja autorizada — sai com a
    faixa «SEM VALOR FISCAL» atravessando a página, como o leiaute exige.

  Esta frente **não transmitiu em produção nenhuma vez**, nem para testar.

O que foi cavado ANTES de construir
-----------------------------------
  · **Não existe gerador de DANFE nesta casa.** `nfe_provider._emitir_sync` devolve
    `"pdf_danfe": None`; a PyNFe traz um `processamento/danfe.py`, mas ele desenha o leiaute
    dela e não conhece a marca. O DANFE aqui é reportlab + `crm/services/pdf_branding`
    (`marca_canvas`/`rodape_canvas`), que já é o timbre dos outros 28 geradores.
  · **O emitente deixou de ser fixo** (DGX Z2, 24/09/2026): a identidade fiscal vem de
    `empresas` pelo CNPJ da própria nota (`emissor.carregar_emitente`), e o provider recusa
    com `EMITENTE_INCOMPLETO` nomeando o campo que falta. A Patrimonial segue bloqueada —
    não por código, mas porque não tem Inscrição Estadual cadastrada, e sem IE a SEFAZ-AM
    rejeita 209. Assim que a IE entrar em `empresas`, a nota dela sai por este mesmo caminho.
  · **A empresa emitente vem da tabela `empresas`** (slug, cnpj, inscricao_estadual,
    regime_tributario, certificado_a1_path/senha, codigo_municipio_ibge) — não de constante
    nova. CRT sai do regime: lucro_real → 3, simples_nacional → 1.
  · **Produto**: a frente Z1 está criando `fin_produtos`. Enquanto ela não chega, a lista de
    produtos sai de `nfe_compras_estoque` (o estoque VIVO, 147 itens com NCM real das NF-e de
    compra) e a tela **declara isso**. Quando `fin_produtos` existir, ela passa a ser a fonte
    sem tocar neste arquivo.
  · **Destinatário**: `clients` (29 clientes, com `document_number`, `state_registration` e
    endereço completo) ou avulso digitado — venda de material acontece nos dois jeitos.

O que NÃO faz (e por quê, em uma linha cada)
--------------------------------------------
  · Não toca `nfe_provider.py` nem `notas_fiscais/nfe/controller.py` — são da frente Z2.
  · Não cria `fin_produtos` — é da frente Z1.
  · Não cria o título em contas a receber sozinho: OFERECE o caminho que já existe
    (`/api/v1/redesign/action/receivable-novo`) depois da autorização. Dinheiro não nasce
    de efeito colateral de emissão.

Prefixo `_` = o discovery pula. `fiscal.py` expõe o `router` e chama `telas(db, out)` no fim do
`build()`; as abas entram no FIM do `EXTRA_MENU` do fiscal. DDL idempotente em `_ensure`.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser, require_permission
from core.database import get_db

logger = logging.getLogger(__name__)

# ── ANTES do import do data_controller ───────────────────────────────────────────────────────
# O ciclo é real e fecha aqui: este módulo importa o `redesign_data_controller`, que no fim do
# seu import roda `_discover_module_builders()`, que importa `fiscal.py`, que importa ESTE módulo
# de volta. Medido em 24/09: com `EXTRA_MENU` declarado depois do import, o fiscal subia com
# «partially initialized module has no attribute 'EXTRA_MENU'» e o módulo inteiro caía fora do
# redesign. Tudo que o `fiscal.py` lê de mim — `router` e `EXTRA_MENU` — nasce ACIMA do import.
router = APIRouter()

IDS = ("nfe-nova", "nfe-preview", "nfes-emitidas", "nfe-producao")

EXTRA_MENU: list[dict] = [
    {"id": "nfe-nova", "label": "Emitir NF-e (produto)", "icon": "M3 3v18h18", "grupo": "Notas fiscais"},
    {"id": "nfe-preview", "label": "Conferir antes de transmitir", "icon": "M3 3v18h18", "grupo": "Notas fiscais"},
    {"id": "nfes-emitidas", "label": "NF-e emitidas (produto)", "icon": "M3 3v18h18", "grupo": "Notas fiscais"},
    {"id": "nfe-producao", "label": "NF-e — transmitir em PRODUÇÃO", "icon": "M3 3v18h18", "grupo": "Notas fiscais"},
]

from modules.operacional.controllers.redesign_data_controller import (  # noqa: E402
    b,
    brl,
    doc,
    t,
)

_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"
_GATE = [Depends(require_permission("module:fiscal"))]
#: condomínio "empresa da casa" — o mesmo id que as 2 notas existentes usam.
_COND = "00000000-0000-0000-0000-000000000001"

# ─────────────────────────────────────────────────────────────────────────────────────────────
# DDL — só ADD COLUMN IF NOT EXISTS. Nenhum UPDATE: as 2 notas que já existiam nasceram antes
# de haver coluna `ambiente` e ficam «(não registrado)», nunca adivinhadas para 'producao'.
# ─────────────────────────────────────────────────────────────────────────────────────────────
_DDL = [
    "ALTER TABLE nfes ADD COLUMN IF NOT EXISTS ambiente varchar(16)",
    "ALTER TABLE nfes ADD COLUMN IF NOT EXISTS c_stat varchar(8)",
    "ALTER TABLE nfes ADD COLUMN IF NOT EXISTS cliente_id uuid",
    "ALTER TABLE nfes ADD COLUMN IF NOT EXISTS empresa_slug varchar(40)",
    "ALTER TABLE nfes ADD COLUMN IF NOT EXISTS destinatario_ind_ie varchar(2)",
    "ALTER TABLE nfes ADD COLUMN IF NOT EXISTS destinatario_cod_municipio varchar(10)",
    "ALTER TABLE nfes ADD COLUMN IF NOT EXISTS justificativa_cancelamento text",
    "ALTER TABLE nfes ADD COLUMN IF NOT EXISTS data_cancelamento timestamptz",
    "ALTER TABLE nfes ADD COLUMN IF NOT EXISTS protocolo_cancelamento varchar(40)",
    "ALTER TABLE nfes ADD COLUMN IF NOT EXISTS criado_por varchar(120)",
    "CREATE INDEX IF NOT EXISTS ix_nfes_status_criacao ON nfes (status, created_at DESC)",
]


async def _ensure(db: AsyncSession) -> None:
    for sql in _DDL:
        await db.execute(text(sql))
    await db.commit()


# ─────────────────────────────────────────────────────────────────────────────────────────────
# REGRAS PURAS — o oráculo importa ESTAS. Sem banco, sem rede.
# ─────────────────────────────────────────────────────────────────────────────────────────────
AMBIENTES = (
    ("homologacao", "HOMOLOGAÇÃO — teste, sem valor fiscal (padrão)"),
    ("producao", "PRODUÇÃO — vale de verdade, irreversível"),
)
#: código do ambiente na SEFAZ: 1 = produção, 2 = homologação (mesma convenção do NFeConfig).
COD_AMBIENTE = {"homologacao": "2", "producao": "1"}

#: CFOPs de saída que esta casa usa. 5xxx = dentro do estado · 6xxx = outro estado · 7xxx = exterior.
CFOPS = (
    ("5102", "5102 — Venda de mercadoria adquirida de terceiros (dentro do AM)"),
    ("5101", "5101 — Venda de produção do estabelecimento (dentro do AM)"),
    ("5933", "5933 — Prestação de serviço tributado pelo ISSQN (dentro do AM)"),
    ("5949", "5949 — Outra saída de mercadoria não especificada (dentro do AM)"),
    ("5915", "5915 — Remessa para conserto ou reparo (dentro do AM)"),
    ("6102", "6102 — Venda de mercadoria adquirida de terceiros (outro estado)"),
    ("6101", "6101 — Venda de produção do estabelecimento (outro estado)"),
    ("6933", "6933 — Prestação de serviço tributado pelo ISSQN (outro estado)"),
    ("6949", "6949 — Outra saída de mercadoria não especificada (outro estado)"),
)

FINALIDADES = (
    ("1", "1 — Normal"),
    ("2", "2 — Complementar"),
    ("3", "3 — Ajuste"),
    ("4", "4 — Devolução/retorno"),
)

IND_IE = (
    ("9", "9 — Não contribuinte do ICMS (condomínio, pessoa física, órgão público)"),
    ("1", "1 — Contribuinte do ICMS (exige Inscrição Estadual)"),
    ("2", "2 — Contribuinte isento de inscrição"),
)

FRETES = (
    ("9", "9 — Sem frete"),
    ("0", "0 — Por conta do emitente (CIF)"),
    ("1", "1 — Por conta do destinatário (FOB)"),
    ("2", "2 — Por conta de terceiros"),
)

STATUS_TOM = {
    "rascunho": "warn",
    "enviada": "info",
    "autorizada": "ok",
    "rejeitada": "bad",
    "denegada": "bad",
    "cancelada": "bad",
}

#: mínimo do campo `xJust` no evento de cancelamento da SEFAZ (leiaute 4.00).
MIN_JUSTIFICATIVA = 15


def so_digitos(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


def dec(v, padrao="0") -> Decimal:
    """Número do formulário → Decimal. Aceita '1.234,56' e '1234.56'; vazio vira o padrão."""
    s = str(v if v not in (None, "") else padrao).strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except Exception:  # noqa: BLE001 — texto que não é número é problema de validação, não crash
        raise HTTPException(status_code=422, detail=f"«{v}» não é um número válido. Use 1234,56.")


def validar_nfe(cab: dict, itens: list[dict]) -> list[str]:
    """Tudo que impede esta NF-e de ser autorizada, em mensagens que ENSINAM a corrigir.

    Lista vazia = pode transmitir. Cada frase diz o campo, por que a SEFAZ exige e o que fazer —
    a rejeição do fisco vem horas depois e custa uma nota inutilizada; esta vem antes e de graça.
    """
    p: list[str] = []
    uf_emit = (cab.get("emitente_uf") or "AM").upper()
    uf_dest = (cab.get("destinatario_uf") or "").upper()

    # ── emitente ────────────────────────────────────────────────────────────────────────
    if len(so_digitos(cab.get("emitente_cnpj"))) != 14:
        p.append("Empresa emitente sem CNPJ válido (14 dígitos). Escolha a empresa que emite.")
    if not (cab.get("natureza_operacao") or "").strip():
        p.append(
            "Natureza da operação em branco. É o texto que descreve a operação na NF-e "
            "(ex.: «VENDA DE MERCADORIA», «REMESSA PARA CONSERTO») — máximo 60 caracteres."
        )

    # ── destinatário: a SEFAZ rejeita a nota inteira por um destes ──────────────────────
    docn = so_digitos(cab.get("destinatario_cpf_cnpj"))
    if len(docn) not in (11, 14):
        p.append(
            "Destinatário sem CPF/CNPJ válido. CNPJ tem 14 dígitos e CPF tem 11 — "
            "escolha um cliente cadastrado ou digite o documento do destinatário avulso."
        )
    if not (cab.get("destinatario_razao_social") or "").strip():
        p.append("Destinatário sem razão social/nome. A SEFAZ exige o nome de quem recebe.")
    if len(uf_dest) != 2:
        p.append("Destinatário sem UF (2 letras, ex.: AM). Sem a UF não dá para decidir o CFOP.")
    for campo, rotulo in (
        ("destinatario_logradouro", "logradouro"),
        ("destinatario_bairro", "bairro"),
        ("destinatario_municipio", "município"),
    ):
        if not (cab.get(campo) or "").strip():
            p.append(
                f"Endereço do destinatário sem {rotulo}. O leiaute da NF-e exige o endereço "
                "completo de quem recebe — complete o cadastro do cliente ou digite no avulso."
            )
    if len(so_digitos(cab.get("destinatario_cep"))) != 8:
        p.append("Destinatário sem CEP de 8 dígitos. Ex.: 69050-001 → 69050001.")
    if len(so_digitos(cab.get("destinatario_cod_municipio"))) != 7:
        p.append(
            "Destinatário sem código IBGE do município (7 dígitos). Manaus é 1302603 — "
            "sem ele a SEFAZ não localiza o município do destinatário."
        )
    ind_ie = str(cab.get("destinatario_ind_ie") or "9")
    if ind_ie == "1" and not so_digitos(cab.get("destinatario_ie")):
        p.append(
            "Destinatário marcado como CONTRIBUINTE do ICMS (indicador 1) e sem Inscrição "
            "Estadual. Preencha a IE; se ele não for contribuinte, marque o indicador 9; "
            "se for isento de inscrição, marque o 2."
        )

    # ── itens ───────────────────────────────────────────────────────────────────────────
    if not itens:
        p.append("A nota não tem nenhum item. Escolha ao menos um produto.")
    for i, it in enumerate(itens, start=1):
        nome = (it.get("descricao") or it.get("codigo") or "sem descrição")[:40]
        ncm = so_digitos(it.get("ncm"))
        if len(ncm) != 8:
            p.append(
                f"Item {i} «{nome}»: NCM ausente ou com {len(ncm)} dígito(s). A SEFAZ exige o "
                "NCM de 8 dígitos de cada produto (é ele que define a tributação) — cadastre o "
                "NCM do produto antes de emitir."
            )
        cfop = so_digitos(it.get("cfop"))
        if len(cfop) != 4:
            p.append(
                f"Item {i} «{nome}»: CFOP ausente ou inválido. São 4 dígitos — venda dentro do "
                "estado começa com 5 (ex.: 5102), para outro estado com 6 (ex.: 6102)."
            )
        elif len(uf_dest) == 2:
            esperado = "5" if uf_dest == uf_emit else "6"
            if cfop[0] not in ("5", "6", "7"):
                p.append(f"Item {i} «{nome}»: CFOP {cfop} não é de SAÍDA (começa com 5, 6 ou 7).")
            elif cfop[0] != esperado:
                dentro = uf_dest == uf_emit
                p.append(
                    f"Item {i} «{nome}»: CFOP {cfop} incompatível com o destino. O destinatário "
                    f"está {'no mesmo estado' if dentro else 'em outro estado'} "
                    f"({uf_emit} → {uf_dest}), então o CFOP tem de começar com {esperado} "
                    f"(ex.: {esperado}102 para venda de mercadoria)."
                )
        if not (it.get("descricao") or "").strip():
            p.append(f"Item {i}: sem descrição. A SEFAZ exige a descrição do produto (até 120 caracteres).")
        if not (it.get("unidade") or "").strip():
            p.append(f"Item {i} «{nome}»: sem unidade comercial (UN, CX, MT, PC…).")
        try:
            q = Decimal(str(it.get("quantidade") or 0))
            vu = Decimal(str(it.get("valor_unitario") or 0))
        except Exception:  # noqa: BLE001
            p.append(f"Item {i} «{nome}»: quantidade e valor unitário têm de ser números.")
            continue
        if q <= 0:
            p.append(f"Item {i} «{nome}»: quantidade tem de ser maior que zero.")
        if vu <= 0:
            p.append(f"Item {i} «{nome}»: valor unitário tem de ser maior que zero.")
        if Decimal(str(it.get("valor_desconto") or 0)) > q * vu:
            p.append(f"Item {i} «{nome}»: desconto maior que o valor do item.")
    return p


def exigir(pendencias: list[str]) -> None:
    """Pendências → HTTP 422 com TODAS elas numeradas. Uma volta, não uma de cada vez."""
    if not pendencias:
        return
    corpo = "\n".join(f"{i}. {m}" for i, m in enumerate(pendencias, start=1))
    raise HTTPException(
        status_code=422,
        detail=(
            f"A NF-e não pode ser emitida — {len(pendencias)} pendência(s):\n{corpo}"
            if len(pendencias) > 1
            else f"A NF-e não pode ser emitida — {corpo[3:]}"
        ),
    )


def validar_justificativa(texto: str | None) -> str:
    """Justificativa de cancelamento: 15 a 255 caracteres (campo `xJust`, leiaute 4.00)."""
    j = (texto or "").strip()
    if len(j) < MIN_JUSTIFICATIVA:
        raise HTTPException(
            status_code=422,
            detail=(
                f"A justificativa tem {len(j)} caractere(s). A SEFAZ exige no mínimo "
                f"{MIN_JUSTIFICATIVA} — escreva o motivo real do cancelamento "
                "(ex.: «mercadoria devolvida pelo cliente antes da entrega»)."
            ),
        )
    if len(j) > 255:
        raise HTTPException(status_code=422, detail="A justificativa passa de 255 caracteres (limite da SEFAZ).")
    return j


def _linha_de(calc: dict, rotulo: str) -> dict | None:
    """A linha de PIS ou de COFINS no cálculo da régua Z4.

    Compara pelo COMEÇO do rótulo porque a régua junta os dois numa linha só no caso da ZFM
    («PIS / COFINS», CST 06, alíquota zero). Comparar por igualdade perdia esse caso e caía
    no padrão — e o padrão, CST 07, não é a mesma coisa que CST 06 no XML.
    """
    alvo = rotulo.lower()
    for x in calc.get("linhas") or []:
        r = str(x.get("rotulo") or "").lower()
        if r == alvo or r.startswith(alvo + " /") or alvo in r.split(" / "):
            return x
    return None


def _cst_da_linha(linha: dict | None) -> str:
    """CST de PIS/COFINS a partir da linha da régua Z4 — ou «07» (isenta), o padrão dela.

    A linha traz o CST dentro de `origem_regra`, em texto («CST 09 — suspenso por decisão
    judicial»), porque ela foi escrita para uma TELA ler. Aqui ele é extraído para ir ao XML.
    Ler o número de dentro da frase é feio; a alternativa era duplicar a regra de PIS/COFINS
    deste lado, e duplicar regra fiscal é pior que um regex.

    ⚠️ ESCRITO ERRADO NA PRIMEIRA VEZ, e o defeito era silencioso: eu li `linha["origem"]`,
    que não existe — a chave é `origem_regra`. `.get()` devolveu None, o regex não casou, e a
    função caiu no padrão «07». A NF-e 5/2 de homologação saiu com **PIS/COFINS CST 07** em
    vez do **CST 09** da liminar (processo 1038495-94.2024.4.01.3200). Valor zero nos dois
    casos, então nenhum total denunciava; o que muda é o que a nota DECLARA ao fisco — 07 é
    «operação isenta», 09 é «exigibilidade suspensa por decisão judicial». Declarar isenção
    onde há liminar é abrir mão do fundamento e enfraquecer o próprio processo.
    """
    import re as _re  # noqa: PLC0415

    m = _re.search(r"CST\s*(\d{2})", str((linha or {}).get("origem_regra") or ""))
    return m.group(1) if m else "07"


def _aliq_da_linha(linha: dict | None) -> float:
    """Alíquota da linha da régua (o `valor` das linhas de PIS/COFINS é a ALÍQUOTA, em %).

    Ausente = 0. Nunca «a alíquota de sempre»: alíquota presumida é imposto pago a mais.
    """
    try:
        return float((linha or {}).get("valor") or 0)
    except (TypeError, ValueError):
        return 0.0


def calcular_totais(itens: list[dict], valor_frete=0) -> dict:
    """Totais da nota. ICMS/PIS/COFINS saem da alíquota de CADA item — sem alíquota, zero.

    Os itens nascem com CST 40 (ICMS isento — Zona Franca) e PIS/COFINS 07 (operação isenta),
    que é o que esta casa pratica em Manaus; por isso o normal é tributo zero e o total bater
    com produtos − desconto + frete. Quem mudar o CST mudará a alíquota, e a conta segue.
    """
    prod = desc = icms = pis = cof = Decimal("0")
    for it in itens:
        q = Decimal(str(it.get("quantidade") or 0))
        vu = Decimal(str(it.get("valor_unitario") or 0))
        vd = Decimal(str(it.get("valor_desconto") or 0))
        base = q * vu - vd
        prod += q * vu
        desc += vd
        icms += (base * Decimal(str(it.get("icms_aliquota") or 0)) / 100).quantize(Decimal("0.01"))
        pis += (base * Decimal(str(it.get("pis_aliquota") or 0)) / 100).quantize(Decimal("0.01"))
        cof += (base * Decimal(str(it.get("cofins_aliquota") or 0)) / 100).quantize(Decimal("0.01"))
    frete = Decimal(str(valor_frete or 0))
    return {
        "produtos": prod,
        "desconto": desc,
        "frete": frete,
        "icms": icms,
        "pis": pis,
        "cofins": cof,
        "total": prod - desc + frete,
    }


def formatar_chave(chave: str | None) -> str:
    """Chave de 44 dígitos em blocos de 4 — é assim que ela aparece no DANFE."""
    c = so_digitos(chave)
    return " ".join(c[i : i + 4] for i in range(0, len(c), 4)) if len(c) == 44 else (chave or "—")


def xml_preview(cab: dict, itens: list[dict]) -> str:
    """XML da NF-e **montado para CONFERÊNCIA** — não assinado, não transmitido.

    Deliberadamente escrito aqui com `xml.etree` da stdlib e não com a PyNFe: o preview tem de
    funcionar sem certificado e sem rede, e o XML que vai ao fisco é o do emissor (frente Z2).
    Quem confere precisa ver os campos que a SEFAZ vai ler, e é isso que este devolve.
    """
    ns = "http://www.portalfiscal.inf.br/nfe"
    tot = calcular_totais(itens, cab.get("valor_frete"))
    nfe = ET.Element("NFe", {"xmlns": ns})
    inf = ET.SubElement(
        nfe, "infNFe", {"versao": "4.00", "Id": f"NFe{so_digitos(cab.get('chave_acesso')) or '0' * 44}"}
    )

    ide = ET.SubElement(inf, "ide")
    for tag, val in (
        ("cUF", "13"),
        ("natOp", (cab.get("natureza_operacao") or "")[:60]),
        ("mod", "55"),
        ("serie", str(cab.get("serie") or 1)),
        ("nNF", str(cab.get("numero") or "")),
        (
            "dhEmi",
            (cab.get("data_emissao") or datetime.now(UTC)).isoformat()
            if not isinstance(cab.get("data_emissao"), str)
            else cab["data_emissao"],
        ),
        ("tpNF", "1"),
        ("idDest", "1" if (cab.get("destinatario_uf") or "AM") == (cab.get("emitente_uf") or "AM") else "2"),
        ("cMunFG", "1302603"),
        ("tpImp", "1"),
        ("tpEmis", "1"),
        ("tpAmb", COD_AMBIENTE.get(cab.get("ambiente") or "homologacao", "2")),
        ("finNFe", str(cab.get("finalidade") or "1")),
        ("indFinal", "1"),
        ("indPres", "9"),
        ("procEmi", "0"),
        ("verProc", "ConectaPRO-1.0"),
    ):
        ET.SubElement(ide, tag).text = str(val)

    emit = ET.SubElement(inf, "emit")
    ET.SubElement(emit, "CNPJ").text = so_digitos(cab.get("emitente_cnpj"))
    ET.SubElement(emit, "xNome").text = (cab.get("emitente_razao_social") or "")[:60]
    ET.SubElement(emit, "IE").text = so_digitos(cab.get("emitente_ie"))
    ET.SubElement(emit, "CRT").text = str(cab.get("emitente_crt") or "3")

    dest = ET.SubElement(inf, "dest")
    docn = so_digitos(cab.get("destinatario_cpf_cnpj"))
    ET.SubElement(dest, "CNPJ" if len(docn) == 14 else "CPF").text = docn
    ET.SubElement(dest, "xNome").text = (cab.get("destinatario_razao_social") or "")[:60]
    ender = ET.SubElement(dest, "enderDest")
    for tag, val in (
        ("xLgr", cab.get("destinatario_logradouro")),
        ("nro", cab.get("destinatario_numero") or "S/N"),
        ("xBairro", cab.get("destinatario_bairro")),
        ("cMun", so_digitos(cab.get("destinatario_cod_municipio"))),
        ("xMun", cab.get("destinatario_municipio")),
        ("UF", cab.get("destinatario_uf")),
        ("CEP", so_digitos(cab.get("destinatario_cep"))),
        ("cPais", "1058"),
        ("xPais", "BRASIL"),
    ):
        ET.SubElement(ender, tag).text = str(val or "")
    ET.SubElement(dest, "indIEDest").text = str(cab.get("destinatario_ind_ie") or "9")
    if so_digitos(cab.get("destinatario_ie")):
        ET.SubElement(dest, "IE").text = so_digitos(cab.get("destinatario_ie"))

    for i, it in enumerate(itens, start=1):
        det = ET.SubElement(inf, "det", {"nItem": str(i)})
        prod = ET.SubElement(det, "prod")
        q = Decimal(str(it.get("quantidade") or 0))
        vu = Decimal(str(it.get("valor_unitario") or 0))
        for tag, val in (
            ("cProd", it.get("codigo") or str(i)),
            ("xProd", (it.get("descricao") or "")[:120]),
            ("NCM", so_digitos(it.get("ncm"))),
            ("CFOP", so_digitos(it.get("cfop"))),
            ("uCom", it.get("unidade") or "UN"),
            ("qCom", f"{q:.4f}"),
            ("vUnCom", f"{vu:.4f}"),
            ("vProd", f"{q * vu:.2f}"),
            ("indTot", "1"),
        ):
            ET.SubElement(prod, tag).text = str(val or "")
        if Decimal(str(it.get("valor_desconto") or 0)) > 0:
            ET.SubElement(prod, "vDesc").text = f"{Decimal(str(it['valor_desconto'])):.2f}"
        imp = ET.SubElement(det, "imposto")
        icms = ET.SubElement(ET.SubElement(imp, "ICMS"), "ICMS40")
        ET.SubElement(icms, "orig").text = str(it.get("icms_origem") or "0")
        ET.SubElement(icms, "CST").text = str(it.get("icms_cst") or "40")
        pis = ET.SubElement(ET.SubElement(imp, "PIS"), "PISNT")
        ET.SubElement(pis, "CST").text = str(it.get("pis_cst") or "07")
        cof = ET.SubElement(ET.SubElement(imp, "COFINS"), "COFINSNT")
        ET.SubElement(cof, "CST").text = str(it.get("cofins_cst") or "07")

    icmstot = ET.SubElement(ET.SubElement(inf, "total"), "ICMSTot")
    for tag, val in (
        ("vBC", "0.00"),
        ("vICMS", f"{tot['icms']:.2f}"),
        ("vProd", f"{tot['produtos']:.2f}"),
        ("vFrete", f"{tot['frete']:.2f}"),
        ("vSeg", "0.00"),
        ("vDesc", f"{tot['desconto']:.2f}"),
        ("vPIS", f"{tot['pis']:.2f}"),
        ("vCOFINS", f"{tot['cofins']:.2f}"),
        ("vNF", f"{tot['total']:.2f}"),
    ):
        ET.SubElement(icmstot, tag).text = val
    transp = ET.SubElement(inf, "transp")
    ET.SubElement(transp, "modFrete").text = str(cab.get("modalidade_frete") or "9")
    pag = ET.SubElement(ET.SubElement(inf, "pag"), "detPag")
    ET.SubElement(pag, "tPag").text = str(cab.get("meio_pagamento") or "15")
    ET.SubElement(pag, "vPag").text = f"{tot['total']:.2f}"
    if (cab.get("informacoes_complementares") or "").strip():
        ET.SubElement(ET.SubElement(inf, "infAdic"), "infCpl").text = cab["informacoes_complementares"][:5000]

    ET.indent(nfe, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(nfe, encoding="unicode")


# ─────────────────────────────────────────────────────────────────────────────────────────────
# DANFE — Documento Auxiliar da NF-e, no leiaute usual, com o timbre da casa.
# ─────────────────────────────────────────────────────────────────────────────────────────────
def precisa_faixa_sem_valor_fiscal(cab: dict) -> bool:
    """A faixa «SEM VALOR FISCAL» é obrigatória em homologação — e em tudo que não está
    autorizado em produção. Um rascunho impresso não é documento fiscal, nem em produção."""
    return (cab.get("ambiente") or "homologacao") != "producao" or (cab.get("status") or "") != "autorizada"


def danfe_pdf(cab: dict, itens: list[dict], orientacao: str = "retrato") -> bytes:
    """DANFE em PDF — o desenho vive em `modules/fiscal/services/danfe_layout.py` (frente AB1).

    Aqui ficava um leiaute próprio, «com a nossa cara». Medido em 25/09/2026 contra o DANFE
    real da empresa (NF-e 10.026, emitida pelo nfemais): faltavam o canhoto, o bloco
    DANFE/entrada-saída/folha, o endereço e a IE do emitente, a data do protocolo, a
    fatura/duplicatas, o transportador/volumes, o cálculo do ISSQN e o «reservado ao fisco»;
    o cálculo do imposto trazia campos que o MOC não nomeia; a tabela de itens estava sem CST,
    BC ICMS, V. ICMS, V. IPI, %ICMS e %IPI; e os itens eram TRUNCADOS depois do que coubesse
    na página. O leiaute do DANFE é normativo (MOC da NF-e, Anexo «Manual de Especificações
    Técnicas do DANFE»): sair diferente não é estilo, é não conformidade.

    `orientacao` = 'retrato' (padrão) ou 'paisagem' — as duas formas que o MOC prevê.
    A tarja «SEM VALOR FISCAL» continua sendo decidida AQUI, pela regra desta tela.
    """
    from modules.fiscal.services.danfe_layout import danfe as _desenhar  # noqa: PLC0415

    return _desenhar(cab, itens, orientacao=orientacao, sem_valor_fiscal=precisa_faixa_sem_valor_fiscal(cab))


def _br_dt(v) -> str:
    """Data/hora em formato brasileiro. Texto ISO ('2026-09-24T17:53') também vira DD/MM/AAAA —
    a prova visual do DANFE saiu com a data ao contrário quando a origem era string."""
    if not v:
        return "—"
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return v[:16].replace("T", " ")
    return v.strftime("%d/%m/%Y %H:%M")


def _br_doc(v) -> str:
    d = so_digitos(v)
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return d or "—"


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Leitura do banco
# ─────────────────────────────────────────────────────────────────────────────────────────────
_SQL_NFE = """
SELECT id::text, numero, serie, chave_acesso, status, coalesce(ambiente,'') AS amb,
       destinatario_razao_social, destinatario_cpf_cnpj, destinatario_ie, destinatario_uf,
       destinatario_logradouro, destinatario_numero, destinatario_bairro,
       destinatario_municipio, coalesce(destinatario_cod_municipio,'') , destinatario_cep,
       coalesce(destinatario_ind_ie,'9'), natureza_operacao, finalidade, data_emissao,
       emitente_cnpj, emitente_razao_social, coalesce(emitente_ie,''), emitente_uf, emitente_crt,
       coalesce(empresa_slug,''), modalidade_frete, coalesce(valor_total_frete,0),
       coalesce(valor_total_nota,0), protocolo_autorizacao, motivo_rejeicao, coalesce(c_stat,''),
       informacoes_complementares, justificativa_cancelamento, meio_pagamento,
       coalesce(xml_autorizado,'')
FROM nfes WHERE active IS NOT false
"""

_CAMPOS_NFE = (
    "id",
    "numero",
    "serie",
    "chave_acesso",
    "status",
    "ambiente",
    "destinatario_razao_social",
    "destinatario_cpf_cnpj",
    "destinatario_ie",
    "destinatario_uf",
    "destinatario_logradouro",
    "destinatario_numero",
    "destinatario_bairro",
    "destinatario_municipio",
    "destinatario_cod_municipio",
    "destinatario_cep",
    "destinatario_ind_ie",
    "natureza_operacao",
    "finalidade",
    "data_emissao",
    "emitente_cnpj",
    "emitente_razao_social",
    "emitente_ie",
    "emitente_uf",
    "emitente_crt",
    "empresa_slug",
    "modalidade_frete",
    "valor_frete",
    "valor_total_nota",
    "protocolo_autorizacao",
    "motivo_rejeicao",
    "c_stat",
    "informacoes_complementares",
    "justificativa_cancelamento",
    "meio_pagamento",
    "xml_autorizado",
)


async def carregar_nota(db: AsyncSession, nfe_id: str) -> tuple[dict, list[dict]]:
    r = (await db.execute(text(_SQL_NFE + " AND id::text = :i"), {"i": nfe_id})).first()
    if not r:
        raise HTTPException(status_code=404, detail="NF-e não encontrada.")
    cab = dict(zip(_CAMPOS_NFE, r, strict=False))
    itens = [
        {
            "codigo": x[0],
            "descricao": x[1],
            "ncm": x[2],
            "cfop": x[3],
            "unidade": x[4],
            "quantidade": x[5],
            "valor_unitario": x[6],
            "valor_desconto": x[7],
            "icms_cst": x[8],
            "icms_aliquota": x[9],
            "pis_cst": x[10],
            "pis_aliquota": x[11],
            "cofins_cst": x[12],
            "cofins_aliquota": x[13],
            "icms_csosn": x[14],
            "icms_origem": x[15],
            "icms_base_calculo": x[16],
            "icms_valor": x[17],
        }
        for x in (
            await db.execute(
                text(
                    "SELECT codigo_produto, descricao, ncm, cfop, unidade, quantidade, valor_unitario, "
                    # ⚠️ SEM `coalesce(icms_cst,'40')`. O default mascarava item gravado sem
                    # CST: a nota ia à SEFAZ com CST 40 (isenta) que ninguém decidiu. Item sem
                    # CST tem de CHEGAR vazio ao emissor, para ele recusar — e ele recusa.
                    " coalesce(valor_desconto,0), coalesce(icms_cst,''), coalesce(icms_aliquota,0), "
                    " coalesce(pis_cst,'07'), coalesce(pis_aliquota,0), coalesce(cofins_cst,'07'), "
                    " coalesce(cofins_aliquota,0), coalesce(icms_csosn,''), coalesce(icms_origem,'0'), "
                    " coalesce(icms_base_calculo,0), coalesce(icms_valor,0) "
                    "FROM nfe_itens WHERE nfe_id::text = :i ORDER BY numero_item"
                ),
                {"i": nfe_id},
            )
        ).fetchall()
    ]
    #: COSTURA ENTRE DUAS FRENTES, medida em produção em 24/09/2026 com a primeira nota
    #: autorizada daqui: o DANFE saía com cabeçalho, chave, protocolo e a tarja «SEM VALOR
    #: FISCAL» — e **sem uma linha de produto**. A Z3 lê os itens de `nfe_itens`; a Z2 decidiu
    #: não popular essa tabela («os itens vivem no XML guardado, que é a fonte legal»). Cada
    #: frente estava certa sozinha e o documento saía inválido.
    #:
    #: O remendo NÃO é popular `nfe_itens` no emissor: isso cria uma segunda cópia que pode
    #: divergir do que foi ao fisco. Lê-se do XML autorizado, que é o que a SEFAZ carimbou —
    #: assim o DANFE não tem como discordar da nota. `nfe_itens` continua sendo o caminho das
    #: notas montadas pela tela (rascunho, antes de transmitir), e tem precedência quando existe.
    if not itens and cab.get("xml_autorizado"):
        itens = _itens_do_xml(str(cab["xml_autorizado"]))
    return cab, itens


#: Namespace do leiaute 4.00. O `nfeProc` guardado traz o `protNFe` com prefixo (`ns0:`) e a
#: `NFe` sem — por isso a busca é por sufixo de tag, não por caminho com prefixo fixo.
_NS_NFE = "{http://www.portalfiscal.inf.br/nfe}"


def _itens_do_xml(xml: str) -> list[dict]:
    """Itens lidos do XML que a SEFAZ autorizou. Nunca levanta: DANFE sem item é ruim,
    DANFE que estoura é pior — quem chama já trata lista vazia."""

    def txt(no, tag: str, padrao: str = "") -> str:
        achado = no.find(f"{_NS_NFE}{tag}")
        return (achado.text or padrao) if achado is not None else padrao

    #: `defusedxml`, não o ET da stdlib: o conteúdo vem do banco, mas quem o pôs lá foi uma
    #: resposta da SEFAZ — é entrada externa, e bomba de entidade XML é barata de montar.
    from defusedxml.ElementTree import fromstring as _parse  # noqa: PLC0415 — só este caminho

    try:
        raiz = _parse(xml)
    except ET.ParseError:
        logger.warning("DANFE: XML guardado não é XML válido; itens ficam vazios.")
        return []
    fora = []
    for det in raiz.iter(f"{_NS_NFE}det"):
        prod = det.find(f"{_NS_NFE}prod")
        if prod is None:
            continue
        imp = det.find(f"{_NS_NFE}imposto")
        icms = pis = cofins = None
        if imp is not None:
            # ICMS00/ICMS40/ICMSSN102… — o grupo tem nome variável; pega-se o primeiro filho.
            gi = imp.find(f"{_NS_NFE}ICMS")
            icms = next(iter(gi), None) if gi is not None else None
            gp = imp.find(f"{_NS_NFE}PIS")
            pis = next(iter(gp), None) if gp is not None else None
            gc = imp.find(f"{_NS_NFE}COFINS")
            cofins = next(iter(gc), None) if gc is not None else None
        fora.append(
            {
                "codigo": txt(prod, "cProd"),
                "descricao": txt(prod, "xProd"),
                "ncm": txt(prod, "NCM"),
                "cfop": txt(prod, "CFOP"),
                "unidade": txt(prod, "uCom"),
                "quantidade": Decimal(txt(prod, "qCom", "0") or "0"),
                "valor_unitario": Decimal(txt(prod, "vUnCom", "0") or "0"),
                "valor_desconto": Decimal(txt(prod, "vDesc", "0") or "0"),
                "icms_cst": txt(icms, "CST") or txt(icms, "CSOSN") if icms is not None else "40",
                "icms_aliquota": Decimal(txt(icms, "pICMS", "0") or "0") if icms is not None else Decimal(0),
                "pis_cst": txt(pis, "CST", "07") if pis is not None else "07",
                "pis_aliquota": Decimal(txt(pis, "pPIS", "0") or "0") if pis is not None else Decimal(0),
                "cofins_cst": txt(cofins, "CST", "07") if cofins is not None else "07",
                "cofins_aliquota": Decimal(txt(cofins, "pCOFINS", "0") or "0") if cofins is not None else Decimal(0),
            }
        )
    return fora


async def _empresas(db: AsyncSession) -> list[dict]:
    rows = (
        await db.execute(
            text(
                "SELECT slug, razao_social, cnpj, coalesce(inscricao_estadual,''), "
                " coalesce(regime_tributario,''), coalesce(certificado_a1_path,''), "
                " coalesce(certificado_a1_senha,''), coalesce(codigo_municipio_ibge,'1302603'), "
                " coalesce(inscricao_suframa,'') "
                "FROM empresas WHERE coalesce(status,'ativa') = 'ativa' ORDER BY is_principal DESC, slug"
            )
        )
    ).fetchall()
    return [
        {
            "slug": r[0],
            "razao": r[1],
            "cnpj": so_digitos(r[2]),
            "ie": so_digitos(r[3]),
            "regime": r[4],
            "cert_path": r[5],
            "cert_senha": r[6],
            "cod_mun": r[7],
            "suframa": r[8],
            "crt": "1" if "simples" in (r[4] or "") else "3",
        }
        for r in rows
    ]


async def _produtos(db: AsyncSession) -> tuple[list[dict], str]:
    """(produtos, fonte). `fin_produtos` (frente Z1) quando existir; senão o estoque vivo.

    ⚠️ CONSERTO DE 25/09/2026 — esta função NUNCA tinha usado o cadastro fiscal.

    Ela pedia `unidade` e `preco_venda`. A tabela tem `unidade_comercial`, e **não tem preço de
    venda nenhum** — por decisão do dono em 24/09: *«nos produtos cadastrados, deixem sem valor,
    quando eu for fazer os orçamentos eu edito o preço, porque os preços variam muito»*. Duas
    colunas com nome errado, `UndefinedColumnError` a cada carregamento da tela, e o
    `except Exception` engolindo tudo e caindo calado no estoque de COMPRAS.

    O estrago não era cosmético. `fin_produtos` tem 95 produtos com dado FISCAL de verdade —
    NCM conferido, CST, CFOP padrão dentro e fora da UF, CEST, origem. `nfe_compras_estoque` tem
    o NCM que o FORNECEDOR escreveu na nota de compra dele. A tela emitia com o segundo e
    ANUNCIAVA isso como se fosse verdade: «cadastro fiscal próprio ainda não existe, então o NCM
    é o da última compra». O cadastro existia. A tela é que não conseguia lê-lo.

    Pior ainda para quem lê o orçamento anexado: `casar_produtos` (frente Z5) sempre leu
    `fin_produtos` corretamente. Então o leitor casava contra 95 produtos e a tela oferecia 147
    outros — o código que voltava do casamento podia nem existir na lista do `<select>`.

    O `except` continua, porque `fin_produtos` de fato não existe em toda base (a Z1 é recente),
    mas agora ele é ESTREITO e FALA. Exceção larga e muda foi o que escondeu isto.
    """
    try:
        rows = (
            await db.execute(
                text(
                    "SELECT coalesce(codigo,id::text), descricao, coalesce(ncm,''), "
                    " coalesce(unidade_comercial,'UN'), coalesce(icms_entrada_cst,''), "
                    " coalesce(icms_entrada_fonte,''), coalesce(origem,'0') "
                    "FROM fin_produtos WHERE coalesce(ativo, true) ORDER BY descricao LIMIT 400"
                )
            )
        ).fetchall()
        if rows:
            return (
                [
                    # sem `preco`: o catálogo fiscal não guarda preço de venda, e inventar 0,00
                    # aqui seria oferecer um preço que ninguém decidiu.
                    {
                        "codigo": r[0],
                        "descricao": r[1],
                        "ncm": so_digitos(r[2]),
                        "unidade": r[3],
                        "preco": None,
                        # O FATO fiscal viaja com o produto: como a mercadoria ENTROU é o que
                        # decide CFOP e CST da saída, e sem ele a régua da Z4 recusa — que é o
                        # certo. Antes o catálogo parava na descrição e o fato não chegava.
                        "icms_entrada_cst": r[4],
                        "icms_entrada_fonte": r[5],
                        "origem": r[6],
                    }
                    for r in rows
                ],
                "fin_produtos",
            )
        logger.warning("[z3] fin_produtos existe e está VAZIA — caindo no estoque de compras")
    except ProgrammingError as e:  # tabela/coluna ausente — e agora aparece no log
        await db.rollback()
        logger.warning("[z3] não consegui ler fin_produtos (%s) — caindo no estoque de compras", e)
    rows = (
        await db.execute(
            text(
                "SELECT item_code, descricao, coalesce(ncm,''), coalesce(unidade,'UN'), "
                " coalesce(avg_cost, unit_cost, 0) "
                "FROM nfe_compras_estoque WHERE coalesce(ativo, true) ORDER BY descricao LIMIT 400"
            )
        )
    ).fetchall()
    return (
        [
            {
                "codigo": r[0],
                "descricao": r[1],
                "ncm": so_digitos(r[2]),
                "unidade": r[3],
                "preco": r[4],
                # o estoque de COMPRAS não sabe como a mercadoria entrou para efeito de saída:
                # vazio, e a régua da Z4 recusa com mensagem que ensina. Não se inventa CST.
                "icms_entrada_cst": "",
                "icms_entrada_fonte": "",
                "origem": "0",
            }
            for r in rows
        ],
        "nfe_compras_estoque",
    )


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Transmissão — o ÚNICO ponto que fala com a SEFAZ. Chama o emissor da casa, não reimplementa.
# ─────────────────────────────────────────────────────────────────────────────────────────────
async def transmitir(db: AsyncSession, nfe_id: str, ambiente: str) -> dict:
    """Manda a nota à SEFAZ pelo emissor da casa (`financial/integrations/nfe_provider`) e grava
    o que ELE devolveu. Nunca fabrica «autorizada»: se o provider não responde, a nota fica
    como estava e o motivo real vai para `motivo_rejeicao`."""
    from uuid import UUID as _UUID

    cab, itens = await carregar_nota(db, nfe_id)
    if (cab.get("status") or "") not in ("rascunho", "rejeitada"):
        raise HTTPException(
            status_code=400,
            detail=f"Esta nota está «{cab.get('status')}» — só rascunho ou rejeitada pode ser transmitida.",
        )
    exigir(validar_nfe(cab, itens))

    emps = {e["slug"]: e for e in await _empresas(db)}
    emp = emps.get(cab.get("empresa_slug") or "") or {}
    if not emp:
        raise HTTPException(status_code=422, detail="Empresa emitente da nota não está cadastrada em «empresas».")
    if not emp["ie"]:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{emp['razao']} não tem Inscrição Estadual cadastrada. A SEFAZ não autoriza NF-e "
                "de mercadoria sem IE — cadastre a IE da empresa (Configurações → Empresas) ou "
                "emita por um CNPJ que tenha."
            ),
        )

    # DGX Z2: o emitente deixou de ser fixo. A identidade fiscal vem de `empresas` pelo CNPJ da
    # própria nota, e o emissor recusa (EMITENTE_INCOMPLETO) se faltar um campo legal.
    from modules.financial.integrations import nfe_provider as prov
    from modules.fiscal_contabil.notas_fiscais.nfe.emissor import carregar_emitente

    try:
        emitente = await carregar_emitente(db, cnpj=so_digitos(cab["emitente_cnpj"]))
        prov.conferir_emitente(emitente)
    except prov.NFeError as e:
        raise HTTPException(status_code=422, detail=e.message) from e
    except LookupError as e:
        raise HTTPException(
            status_code=422,
            detail=f"CNPJ {_br_doc(cab['emitente_cnpj'])} não está cadastrado em «empresas».",
        ) from e
    if not emp["cert_path"]:
        raise HTTPException(status_code=422, detail=f"{emp['razao']} está sem certificado A1 cadastrado.")

    nfe_data = {
        "serie": cab["serie"],
        "natureza_operacao": cab["natureza_operacao"],
        "finalidade": str(cab["finalidade"] or "1"),
        "informacoes_complementares": cab.get("informacoes_complementares") or "",
        "indicador_destino": "1" if (cab["destinatario_uf"] or "AM") == (cab["emitente_uf"] or "AM") else "2",
        "destinatario": {
            "cnpj" if len(so_digitos(cab["destinatario_cpf_cnpj"])) == 14 else "cpf": so_digitos(
                cab["destinatario_cpf_cnpj"]
            ),
            "razao_social": cab["destinatario_razao_social"],
            "indicador_ie": cab["destinatario_ind_ie"],
            "inscricao_estadual": so_digitos(cab["destinatario_ie"]),
            "inscricao_suframa": emp.get("suframa") or "",
            "endereco": {
                "logradouro": cab["destinatario_logradouro"],
                "numero": cab["destinatario_numero"],
                "bairro": cab["destinatario_bairro"],
                "municipio": cab["destinatario_municipio"],
                "cod_municipio": so_digitos(cab["destinatario_cod_municipio"]),
                "uf": cab["destinatario_uf"],
                "cep": so_digitos(cab["destinatario_cep"]),
            },
        },
        "items": [
            {
                "codigo": it["codigo"],
                "descricao": it["descricao"],
                "ncm": so_digitos(it["ncm"]),
                "cfop": so_digitos(it["cfop"]),
                "unidade": it["unidade"],
                "quantidade": float(it["quantidade"] or 0),
                "valor_unitario": float(it["valor_unitario"] or 0),
                "desconto": float(it["valor_desconto"] or 0),
                # ⚠️ NOMES EXATOS do que `nfe_provider._montar_nfe()` lê. Eram
                # `icms_situacao`/`pis_situacao`/`cofins_situacao` — chaves que o emissor
                # NUNCA leu. O resultado era `cst` vazio e a recusa «Item 1 sem CST/CSOSN de
                # ICMS» em toda emissão desta tela, homologação inclusive. Chave com nome
                # parecido é pior que chave ausente: o dicionário fica gordo e a leitura vem
                # vazia, e nada no caminho reclama até o fim.
                "icms_cst": it.get("icms_cst") or "",
                "icms_csosn": it.get("icms_csosn") or "",
                "icms_origem": it.get("icms_origem") or "0",
                "icms_aliquota": it.get("icms_aliquota") or 0,
                "icms_base_calculo": it.get("icms_base_calculo"),
                "icms_valor": it.get("icms_valor") or 0,
                "icms_desonerado": it.get("icms_desonerado") or 0,
                "icms_motivo_desoneracao": it.get("icms_motivo_desoneracao") or "",
                "pis_cst": it.get("pis_cst") or "07",
                "pis_aliquota": it.get("pis_aliquota") or 0,
                "cofins_cst": it.get("cofins_cst") or "07",
                "cofins_aliquota": it.get("cofins_aliquota") or 0,
            }
            for it in itens
        ],
    }

    provider = prov.create_nfe_provider(emp["cert_path"], emp["cert_senha"], ambiente=COD_AMBIENTE[ambiente], uf="AM")
    try:
        r = await provider.emitir_nfe(nfe_data, _UUID(nfe_id), int(cab["numero"] or 0), emitente)
    except Exception as e:  # noqa: BLE001 — falha local NUNCA vira "autorizada"
        await db.execute(
            text("UPDATE nfes SET motivo_rejeicao = :m, updated_at = now() WHERE id::text = :i"),
            {"m": f"Falha ao transmitir ({ambiente}): {str(e)[:900]}", "i": nfe_id},
        )
        await db.commit()
        raise HTTPException(
            status_code=502,
            detail=f"A SEFAZ/emissor não concluiu a transmissão ({ambiente}): {str(e)[:400]}. A nota segue como rascunho.",
        ) from e

    await db.execute(
        text(
            "UPDATE nfes SET status = CAST(:st AS text), chave_acesso = coalesce(nullif(:ch,''), chave_acesso), "
            " protocolo_autorizacao = nullif(:pr,''), motivo_rejeicao = nullif(:mo,''), "
            " c_stat = nullif(:cs,''), xml_autorizado = nullif(:xml,''), ambiente = :amb, "
            # O CAST está nas DUAS ocorrências de `:st` de propósito. O mesmo parâmetro serve
            # `SET status = :st` (a coluna é varchar) e a comparação com literal aqui (text); o
            # asyncpg deduz os dois tipos e levanta `AmbiguousParameterError: text versus
            # character varying`. Provado por `prepare()` em 24/09/2026 — e castar só UM lado
            # NÃO resolve, também medido. Sem isso o botão «Transmitir» morre no 1º clique, em
            # silêncio: foi assim que o webhook da Cora passou meses sem marcar transação.
            " data_autorizacao = CASE WHEN CAST(:st AS text) = 'autorizada' THEN now() "
            "                         ELSE data_autorizacao END, "
            " updated_at = now() WHERE id::text = :i"
        ),
        {
            "st": r.get("status") or "enviada",
            "ch": r.get("chave_acesso") or "",
            "pr": r.get("protocolo") or "",
            "mo": r.get("motivo") or "",
            "cs": r.get("codigo_status") or "",
            "xml": r.get("xml_autorizado") or "",
            "amb": ambiente,
            "i": nfe_id,
        },
    )
    await db.commit()
    return {
        "ok": r.get("status") == "autorizada",
        "status": r.get("status"),
        "ambiente": ambiente,
        "chave": r.get("chave_acesso"),
        "protocolo": r.get("protocolo"),
        "message": f"[{r.get('codigo_status')}] {r.get('motivo')}",
    }


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Documentos (GET)
# ─────────────────────────────────────────────────────────────────────────────────────────────
@router.get("/nfe/{nfe_id}/danfe/pdf", dependencies=_GATE)
async def rd_nfe_danfe(
    nfe_id: str,
    current_user: CurrentActiveUser,
    orientacao: str = Query("retrato", pattern="^(retrato|paisagem)$"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """DANFE no leiaute do MOC. `?orientacao=paisagem` devolve a outra forma prevista na norma —
    mesmos blocos, mesma ordem, mais itens por página."""
    cab, itens = await carregar_nota(db, nfe_id)
    pdf = danfe_pdf(cab, itens, orientacao=orientacao)
    nome = f"DANFE_{cab.get('numero') or 'rascunho'}_{so_digitos(cab.get('chave_acesso'))[:12] or 'sem-chave'}.pdf"
    return Response(
        content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{nome}"'}
    )


@router.get("/nfe/{nfe_id}/xml", dependencies=_GATE)
async def rd_nfe_xml(nfe_id: str, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)) -> Response:
    """XML autorizado quando existe (o que foi ao fisco); senão o montado para conferência."""
    cab, itens = await carregar_nota(db, nfe_id)
    xml = cab.get("xml_autorizado") or xml_preview(cab, itens)
    nome = f"NFe_{cab.get('numero') or 'rascunho'}.xml"
    return Response(
        content=xml, media_type="application/xml", headers={"Content-Disposition": f'inline; filename="{nome}"'}
    )


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Ações (POST)
# ─────────────────────────────────────────────────────────────────────────────────────────────
#: Os campos do destinatário na tela `nfe-nova`, na ordem em que aparecem. Existe como lista
#: porque DOIS caminhos precisam dela e não podem divergir: preencher ao escolher o cliente, e
#: LIMPAR ao voltar para «avulso». A lista repetida à mão nos dois lugares é o jeito conhecido
#: de deixar um campo velho na tela depois da troca de cliente.
_CAMPOS_DEST: tuple[str, ...] = (
    "dest_documento",
    "dest_razao",
    "dest_ie",
    "dest_ind_ie",
    "dest_logradouro",
    "dest_numero",
    "dest_bairro",
    "dest_municipio",
    "dest_uf",
    "dest_cep",
    "dest_email",
    "dest_cod_municipio",
)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# DUAS PORTAS QUE FALTAVAM NA TELA DE EMISSÃO — 25/09/2026
#
# O dono, depois de abrir `?t=nfe-nova` pela primeira vez:
#
#   «quando selecionar o condomínio, já preencher todas as informações do condomínio nos campos
#    subsequentes; outra coisa que vai facilitar muito a minha vida é o botão pra eu anexar
#    documentos ou fotos, que são orçamentos que os fornecedores mandam, daí o nosso sistema lê
#    e já lança os produtos […] acrescenta mais 40% de markup e manda emitir a nota.»
#
# Os dois já existiam — e é isso que interessa registrar, porque foi a terceira vez na semana:
#
#   · O preenchimento do destinatário SEMPRE funcionou, só que invisível. `rd_nfe_nova` lê o
#     endereço de `clients` e IGNORA o que estiver digitado nos `dest_*` (linha ~1155). A nota
#     saía certa; a TELA é que ficava muda, e campos marcados com `*` continuavam vazios
#     depois da escolha. O dono lia aquilo como «faltou preencher» — e tinha razão em ler
#     assim. Não é dado errado, é a tela não contando o que o servidor já sabe.
#   · A leitura do orçamento por LLM existe inteira na frente Z5, em `?t=nfe-do-arquivo`:
#     `itens_do_arquivo` + `casar_produtos`. O que faltava era ela estar ONDE ele está.
#
# Capacidade que só existe noutra tela não existe para quem trabalha. Nenhum motor novo aqui:
# `/action/nfe-ler-orcamento` chama o MESMO serviço da Z5 e devolve no contrato `{campos}` que
# o `prefill` do front já fala desde o DP. O que é de fato novo é só o markup.
# ═════════════════════════════════════════════════════════════════════════════════════════════


@router.post("/action/nfe-cliente-dados", dependencies=_GATE)
async def rd_nfe_cliente_dados(
    current_user: CurrentActiveUser,
    payload: dict = Body(default_factory=dict),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Devolve o destinatário de um cliente no contrato `{campos}` — para a tela MOSTRAR.

    Não decide nada: quem manda na nota continua sendo o `rd_nfe_nova`, que relê o cliente do
    banco na hora de emitir. Se esta rota calar, a nota sai igual — some só a conferência
    visual. Por isso ela é leitura pura e nunca levanta 500 por cliente sem endereço.
    """
    cid = str(payload.get("cliente_id") or "").strip()
    if not cid or cid == "avulso":
        # AVULSO limpa os campos: o endereço do cliente anterior ficando na tela é pior que
        # campo vazio — parece conferido e não é.
        return {"ok": True, "campos": dict.fromkeys(_CAMPOS_DEST, ""), "documento": "destinatário avulso"}
    c = (
        await db.execute(
            text(
                "SELECT name, coalesce(document_number,''), coalesce(state_registration,''), "
                " coalesce(address_street,''), coalesce(address_number,''), coalesce(address_neighborhood,''), "
                " coalesce(address_city,''), coalesce(address_state,''), coalesce(address_zipcode,''), "
                " coalesce(email,'') FROM clients WHERE id::text = :i"
            ),
            {"i": cid},
        )
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    municipio = (c[6] or "").strip()
    campos = {
        "dest_documento": so_digitos(c[1]),
        "dest_razao": c[0] or "",
        "dest_ie": so_digitos(c[2]),
        # IE preenchida = contribuinte do ICMS (1). Sem IE, «não contribuinte» (9). É a MESMA
        # dedução que `rd_nfe_nova` faz ao emitir — escrita aqui para a tela mostrar o que o
        # servidor decidiria, e não uma segunda regra que possa divergir dela.
        "dest_ind_ie": "1" if so_digitos(c[2]) else "9",
        "dest_logradouro": c[3] or "",
        "dest_numero": (c[4] or "S/N"),
        "dest_bairro": c[5] or "",
        "dest_municipio": municipio,
        "dest_uf": (c[7] or "AM").upper(),
        "dest_cep": so_digitos(c[8]),
        "dest_email": c[9] or "",
        # O cadastro de cliente não guarda código IBGE. Manaus a casa sabe de cor; fora dela
        # fica VAZIO de propósito, para o validador cobrar. Chutar código de município é
        # rejeição na SEFAZ e, pior, é nota autorizada no município errado.
        "dest_cod_municipio": "1302603" if municipio.strip().lower() == "manaus" else "",
    }
    faltando = [k for k in ("dest_logradouro", "dest_bairro", "dest_municipio", "dest_cep") if not campos[k]]
    return {
        "ok": True,
        "campos": campos,
        "documento": (c[0] or "cliente")[:40],
        "aviso": (
            "Cadastro do cliente sem " + ", ".join(x.replace("dest_", "") for x in faltando) + " — complete abaixo."
            if faltando
            else ""
        ),
    }


@router.post("/action/nfe-ler-orcamento", dependencies=_GATE)
async def rd_nfe_ler_orcamento(
    current_user: CurrentActiveUser,
    arquivo: UploadFile = File(...),
    alvo: str = Form(""),
    vals: str = Form(""),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Orçamento do fornecedor (PDF/foto/planilha) → itens da nota, já com markup.

    Reusa `itens_do_arquivo` + `casar_produtos` da frente Z5: um motor de leitura só. O que
    muda aqui é o destino — em vez de gravar rascunho, devolve `{campos}` e o formulário desta
    tela se preenche. Nada é gravado: quem confere é o dono, antes de emitir.

    O markup sai de `markup_percent` do próprio formulário (o front manda os valores atuais em
    `vals`). Zero ou vazio = preço como veio no arquivo, sem acréscimo — nunca se inventa
    margem por omissão.
    """
    import json  # noqa: PLC0415

    from modules.fiscal.services import orcamento_para_nota as z5  # noqa: PLC0415

    dados = await arquivo.read()
    if not dados:
        raise HTTPException(status_code=422, detail="Arquivo vazio.")
    if len(dados) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo muito grande (máx 15MB).")
    try:
        atuais = json.loads(vals) if vals else {}
    except ValueError:
        atuais = {}
    markup = (atuais or {}).get("markup_percent") or 0

    try:
        lido = await z5.itens_do_arquivo(db, arquivo.filename or "orcamento", dados)
        itens = await z5.casar_produtos(db, lido["itens"])
        itens = z5.aplicar_markup(itens, markup)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if not itens:
        raise HTTPException(
            status_code=422,
            detail="Não achei item com descrição E preço nesse arquivo. Se for foto, tente uma mais nítida.",
        )

    # O 1º item vai nos campos soltos; o resto no JSON de itens adicionais — é o formato que
    # `rd_nfe_nova` já consome, sem tocar no emissor.
    # NCM só do produto que CASOU. `ncm_sugerido` é «o NCM do produto mais parecido» — e
    # parecido não é o mesmo. Eu cheguei a escrever `ncm or ncm_sugerido` aqui e é um erro
    # da mesma família do CEP que quase gravei hoje: campo PREENCHIDO com o valor provável
    # convence quem confere; campo VAZIO pergunta. Um NCM errado que parece certo é a
    # rejeição da SEFAZ de 11/04/2026 («Informado NCM inexistente») esperando a vez — ou,
    # pior que rejeição, uma nota AUTORIZADA com classificação fiscal errada.
    # A sugestão não se perde: vai no aviso, em texto, para a pessoa decidir.
    def _br(v, casas: int = 2) -> str:
        """Decimal → texto que uma PESSOA lê num campo de dinheiro, no formato daqui.

        `str(Decimal)` devolve «320.0000000000» num campo cujo exemplo é «450,00», e
        `Decimal.normalize()` chega a devolver «4E+1» para 40. Nenhum dos dois é errado como
        número e os dois são errados como TELA: quem confere um valor de nota lê vírgula e
        duas casas. O `dec()` do formulário aceita as duas formas, então o que decide aqui é
        a leitura, não o parser.
        """
        from decimal import ROUND_HALF_UP  # noqa: PLC0415

        d = z5.para_decimal(v, 10)
        if casas == 0:  # quantidade: 4.0000 → «4», 1.5000 → «1,5»
            texto = format(d.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP).normalize(), "f")
        else:
            texto = format(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")
        return texto.replace(".", ",")

    def _campos_do_item(i: dict) -> dict:
        casou = bool(i.get("produto_id"))
        return {
            "codigo": (i.get("produto_codigo") or "") if casou else "",
            "descricao": i["descricao"],
            "ncm": (i.get("ncm") or "") if casou else "",
            "unidade": i.get("unidade") or "UN",
            "quantidade": _br(i["quantidade"], 0),
            "valor_unitario": _br(i["valor_unitario"]),
        }

    p, *resto = itens
    prim = _campos_do_item(p)
    campos = {
        "descricao": prim["descricao"],
        "ncm": prim["ncm"],
        "unidade": prim["unidade"],
        "quantidade": prim["quantidade"],
        "valor_unitario": prim["valor_unitario"],
        # `produto` é o <select> do cadastro fiscal: só preenche quando o casamento foi CERTO.
        "produto": prim["codigo"],
        "itens_extras": json.dumps([_campos_do_item(i) for i in resto], ensure_ascii=False),
    }
    sem_produto = [i for i in itens if not i.get("produto_id")]
    total = sum(float(i["valor_total"]) for i in itens)
    m = z5.para_decimal(markup, 4)
    # A sugestão de NCM não some — ela sai do campo e vai para o TEXTO, onde é lida como
    # sugestão e não confundida com dado conferido.
    sugestoes = [
        f"«{i['descricao'][:30]}» talvez NCM {i['ncm_sugerido']}" for i in sem_produto if i.get("ncm_sugerido")
    ]
    return {
        "ok": True,
        "campos": campos,
        "documento": (lido.get("documento") or "orçamento")[:40],
        "aviso": (
            f"{len(itens)} item(ns), total R$ {total:,.2f}".replace(",", "·").replace(".", ",").replace("·", ".")
            + (
                f" · markup de {_br(m, 0)}% aplicado sobre o custo do fornecedor"
                if m > 0
                else " · SEM markup (preço do arquivo)"
            )
            + (
                f" · {len(sem_produto)} SEM produto no cadastro fiscal — escolha o produto antes de emitir"
                if sem_produto
                else ""
            )
            + (f" · sugestões: {'; '.join(sugestoes[:3])}" if sugestoes else "")
        ),
    }


@router.post("/action/nfe-nova", dependencies=_GATE)
async def rd_nfe_nova(  # noqa: PLR0912, PLR0915
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Monta a NF-e, recusa com a mensagem que ensina, grava o rascunho e — SÓ em homologação —
    transmite. Escolher «produção» aqui grava o rascunho e manda para a tela gated."""
    # ANTES de qualquer commit: `_ensure` commita, o commit EXPIRA o `current_user` da sessão, e
    # ler `.email` depois disso dispara um lazy-load fora do greenlet → MissingGreenlet (HTTP 500).
    # Medido em 24/09 no container efêmero, no primeiro caminho feliz.
    quem = (getattr(current_user, "email", None) or "sistema")[:120]
    await _ensure(db)
    ambiente = (payload.get("ambiente") or "homologacao").strip()
    if ambiente not in COD_AMBIENTE:
        raise HTTPException(status_code=422, detail="Ambiente inválido. Use homologação ou produção.")

    emps = {e["slug"]: e for e in await _empresas(db)}
    emp = emps.get((payload.get("empresa") or "").strip())
    if not emp:
        raise HTTPException(
            status_code=422,
            detail="Escolha a empresa que emite — é ela que define CNPJ, certificado, série e tributação.",
        )

    # ── destinatário: cliente cadastrado OU avulso digitado ─────────────────────────────
    cliente_id = (payload.get("cliente_id") or "").strip()
    if cliente_id and cliente_id != "avulso":
        c = (
            await db.execute(
                text(
                    "SELECT id::text, name, coalesce(document_number,''), coalesce(state_registration,''), "
                    " coalesce(address_street,''), coalesce(address_number,''), coalesce(address_neighborhood,''), "
                    " coalesce(address_city,''), coalesce(address_state,''), coalesce(address_zipcode,''), "
                    " coalesce(email,'') FROM clients WHERE id::text = :i"
                ),
                {"i": cliente_id},
            )
        ).first()
        if not c:
            raise HTTPException(status_code=422, detail="Cliente não encontrado.")
        dest = {
            "cliente_id": c[0],
            "destinatario_cpf_cnpj": so_digitos(c[2]),
            "destinatario_razao_social": c[1],
            "destinatario_ie": so_digitos(c[3]),
            "destinatario_logradouro": c[4],
            "destinatario_numero": c[5] or "S/N",
            "destinatario_bairro": c[6],
            "destinatario_municipio": c[7],
            "destinatario_uf": (c[8] or "AM").upper(),
            "destinatario_cep": so_digitos(c[9]),
            "destinatario_email": c[10],
            # o cadastro do cliente não guarda o código IBGE: quem for de Manaus usa 1302603,
            # os outros precisam do código digitado (o validador cobra e explica).
            "destinatario_cod_municipio": so_digitos(payload.get("dest_cod_municipio"))
            or ("1302603" if (c[7] or "").strip().lower() == "manaus" else ""),
            "destinatario_ind_ie": (payload.get("dest_ind_ie") or ("1" if so_digitos(c[3]) else "9")),
        }
    else:
        dest = {
            "cliente_id": None,
            "destinatario_cpf_cnpj": so_digitos(payload.get("dest_documento")),
            "destinatario_razao_social": (payload.get("dest_razao") or "").strip(),
            "destinatario_ie": so_digitos(payload.get("dest_ie")),
            "destinatario_logradouro": (payload.get("dest_logradouro") or "").strip(),
            "destinatario_numero": (payload.get("dest_numero") or "S/N").strip(),
            "destinatario_bairro": (payload.get("dest_bairro") or "").strip(),
            "destinatario_municipio": (payload.get("dest_municipio") or "").strip(),
            "destinatario_uf": (payload.get("dest_uf") or "").strip().upper(),
            "destinatario_cep": so_digitos(payload.get("dest_cep")),
            "destinatario_email": (payload.get("dest_email") or "").strip(),
            "destinatario_cod_municipio": so_digitos(payload.get("dest_cod_municipio")),
            "destinatario_ind_ie": (payload.get("dest_ind_ie") or "9"),
        }

    # ── itens: o do formulário + os extras em JSON ──────────────────────────────────────
    cfop = so_digitos(payload.get("cfop"))
    prods = {p["codigo"]: p for p in (await _produtos(db))[0]}
    itens: list[dict] = []
    cod = (payload.get("produto") or "").strip()
    if cod:
        base = prods.get(cod, {})
        itens.append(
            {
                "codigo": cod,
                "descricao": (payload.get("descricao") or base.get("descricao") or "").strip(),
                "ncm": so_digitos(payload.get("ncm")) or base.get("ncm") or "",
                "cfop": cfop,
                "unidade": (payload.get("unidade") or base.get("unidade") or "UN").strip(),
                "quantidade": dec(payload.get("quantidade"), "1"),
                "valor_unitario": dec(payload.get("valor_unitario")),
                "valor_desconto": dec(payload.get("valor_desconto")),
            }
        )
    extras = payload.get("itens_extras") or []
    if isinstance(extras, str):
        import json as _json

        try:
            extras = _json.loads(extras or "[]")
        except ValueError:
            raise HTTPException(
                status_code=422, detail="«Itens adicionais» não é um JSON válido. Deixe [] se não houver."
            )
    for e in extras if isinstance(extras, list) else []:
        base = prods.get(str(e.get("codigo") or ""), {})
        itens.append(
            {
                "codigo": str(e.get("codigo") or "")[:60],
                "descricao": str(e.get("descricao") or base.get("descricao") or ""),
                "ncm": so_digitos(e.get("ncm")) or base.get("ncm") or "",
                "cfop": so_digitos(e.get("cfop")) or cfop,
                "unidade": str(e.get("unidade") or base.get("unidade") or "UN"),
                "quantidade": dec(e.get("quantidade"), "1"),
                "valor_unitario": dec(e.get("valor_unitario")),
                "valor_desconto": dec(e.get("valor_desconto")),
            }
        )

    # ═════════════════════════════════════════════════════════════════════════════════════
    # A TRIBUTAÇÃO DE CADA ITEM VEM DA RÉGUA DA Z4 — conserto de 25/09/2026
    #
    # Até hoje esta tela NUNCA emitiu uma NF-e, e o motivo era invisível: o `INSERT INTO
    # nfe_itens` gravava `icms_cst = '40'` fixo, e o `nfe_data` entregava a chave
    # `icms_situacao` a um emissor que lê `icms_cst`. Nome diferente = campo vazio = o
    # provider recusava com «Item 1 sem CST/CSOSN de ICMS» em TODA tentativa, inclusive em
    # homologação. Só apareceu quando se tentou emitir de ponta a ponta pela tela.
    #
    # Os dois defeitos apontam para o mesmo erro de fundo: a tela estava ESCOLHENDO
    # tributação (o '40' fixo) em vez de perguntar à régua. Agora ela pergunta, item a item,
    # a `tributacao_nfe.calcular()` — a mesma função que o simulador e o oráculo Z4 usam. Se
    # a régua recusa (mercadoria sem fonte de entrada conhecida), a nota nem é gravada: a
    # recusa sobe como 422 que ENSINA, em vez de virar rascunho que ninguém sabe por que
    # falhou.
    from modules.fiscal.services import tributacao_nfe as tn  # noqa: PLC0415

    dest_trib = {
        "uf": (dest.get("destinatario_uf") or "AM").strip().upper(),
        "cnpj": dest.get("destinatario_cpf_cnpj") or "",
        "inscricao_estadual": dest.get("destinatario_ie") or "",
        "indicador_ie": dest.get("destinatario_ind_ie") or "9",
        "suframa": "",
    }
    for it in itens:
        base_prod = prods.get(it["codigo"], {})
        try:
            calc = await tn.calcular(
                db,
                emp["cnpj"],
                {
                    "ncm": it["ncm"],
                    "valor": it["valor_unitario"],
                    "quantidade": it["quantidade"],
                    "origem": base_prod.get("origem") or "0",
                    "icms_entrada_cst": base_prod.get("icms_entrada_cst") or "",
                    "icms_entrada_fonte": base_prod.get("icms_entrada_fonte") or "",
                },
                dest_trib,
            )
        except Exception as e:  # noqa: BLE001 — falha da régua não vira nota sem tributação
            raise HTTPException(
                status_code=422,
                detail=f"Não consegui tributar «{it['descricao'][:40]}»: {e}",
            ) from e
        if calc.get("bloqueios"):
            raise HTTPException(status_code=422, detail=" ".join(calc["bloqueios"]))
        if not calc.get("cst_ou_csosn"):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"«{it['descricao'][:40]}»: {calc.get('mensagem_fiscal') or 'sem tributação com fonte'} "
                    "Registre como a mercadoria entrou em «Registrar como a mercadoria entrou» "
                    "antes de emitir — o sistema não inventa CST."
                ),
            )
        cst = str(calc["cst_ou_csosn"])
        # CSOSN tem 3 dígitos (101, 500…); CST tem 2. É isso que separa os dois campos no XML.
        eh_csosn = len(cst) == 3 and cst in tn.CSOSN_TODOS
        it["icms_cst"] = "" if eh_csosn else cst
        it["icms_csosn"] = cst if eh_csosn else ""
        it["icms_origem"] = str(base_prod.get("origem") or "0")
        it["icms_aliquota"] = calc.get("aliquota") or 0
        it["icms_base_calculo"] = calc.get("base") or 0
        it["icms_valor"] = calc.get("valor") or 0
        it["icms_desonerado"] = (calc.get("deson") or {}).get("valor") or 0
        it["icms_motivo_desoneracao"] = (calc.get("deson") or {}).get("motivo") or ""
        it["cfop"] = so_digitos(calc.get("cfop")) or it["cfop"]
        it["mensagem_fiscal"] = calc.get("mensagem_fiscal") or ""
        # PIS/COFINS saem das LINHAS da mesma régua — inclusive o CST 09 da liminar.
        for rotulo, chave in (("PIS", "pis"), ("COFINS", "cofins")):
            linha = _linha_de(calc, rotulo)
            it[f"{chave}_cst"] = _cst_da_linha(linha)
            it[f"{chave}_aliquota"] = _aliq_da_linha(linha)

    serie = int(dec(payload.get("serie"), "2"))  # 2 = série do Conecta PRO (ver a tela)
    cab = {
        **dest,
        "empresa_slug": emp["slug"],
        "emitente_cnpj": emp["cnpj"],
        "emitente_razao_social": emp["razao"],
        "emitente_ie": emp["ie"],
        "emitente_uf": "AM",
        "emitente_crt": emp["crt"],
        "natureza_operacao": (payload.get("natureza_operacao") or "").strip()[:60],
        "finalidade": (payload.get("finalidade") or "1").strip(),
        "ambiente": ambiente,
        "serie": serie,
        "modalidade_frete": (payload.get("modalidade_frete") or "9").strip(),
        "valor_frete": dec(payload.get("valor_frete")),
        "meio_pagamento": (payload.get("meio_pagamento") or "15").strip(),
        "informacoes_complementares": (payload.get("informacoes_complementares") or "").strip(),
    }
    exigir(validar_nfe(cab, itens))
    tot = calcular_totais(itens, cab["valor_frete"])

    numero = int(
        (
            await db.execute(
                text("SELECT coalesce(max(numero), 0) + 1 FROM nfes WHERE emitente_cnpj = :c AND serie = :s"),
                {"c": emp["cnpj"], "s": serie},
            )
        ).scalar()
        or 1
    )
    nfe_id = (
        await db.execute(
            text(
                "INSERT INTO nfes (id, condominio_id, tipo, finalidade, status, serie, numero, "
                " natureza_operacao, data_emissao, emitente_cnpj, emitente_razao_social, emitente_ie, "
                " emitente_uf, emitente_crt, empresa_slug, cliente_id, destinatario_cpf_cnpj, "
                " destinatario_razao_social, destinatario_ie, destinatario_email, destinatario_uf, "
                " destinatario_logradouro, destinatario_numero, destinatario_bairro, "
                " destinatario_municipio, destinatario_cod_municipio, destinatario_cep, "
                " destinatario_ind_ie, modalidade_frete, forma_pagamento, meio_pagamento, "
                " valor_pagamento, valor_total_produtos, valor_total_icms, valor_total_pis, "
                " valor_total_cofins, valor_total_frete, valor_total_desconto, valor_total_nota, "
                " informacoes_complementares, is_zfm, ambiente, criado_por, active, created_at, updated_at) "
                "VALUES (gen_random_uuid(), CAST(:cond AS uuid), 'saida', :fin, 'rascunho', :serie, :num, "
                " :nat, now(), :ecnpj, :erazao, :eie, 'AM', :ecrt, :slug, CAST(nullif(:cli,'') AS uuid), "
                " :dcnpj, :drazao, :die, :demail, :duf, :dlog, :dnum, :dbai, :dmun, :dcmun, :dcep, :dind, "
                " :frete, '0', :meio, :total, :prod, :icms, :pis, :cofins, :vfrete, :desc, :total, "
                " :info, true, :amb, :quem, true, now(), now()) RETURNING id::text"
            ),
            {
                "cond": _COND,
                "fin": cab["finalidade"],
                "serie": serie,
                "num": numero,
                "nat": cab["natureza_operacao"],
                "ecnpj": emp["cnpj"],
                "erazao": emp["razao"],
                "eie": emp["ie"],
                "ecrt": emp["crt"],
                "slug": emp["slug"],
                "cli": dest.get("cliente_id") or "",
                "dcnpj": dest["destinatario_cpf_cnpj"],
                "drazao": dest["destinatario_razao_social"][:60],
                "die": dest["destinatario_ie"],
                "demail": dest.get("destinatario_email") or "",
                "duf": dest["destinatario_uf"],
                "dlog": dest["destinatario_logradouro"][:60],
                "dnum": dest["destinatario_numero"][:10],
                "dbai": dest["destinatario_bairro"][:60],
                "dmun": dest["destinatario_municipio"][:60],
                "dcmun": dest["destinatario_cod_municipio"],
                "dcep": dest["destinatario_cep"],
                "dind": dest["destinatario_ind_ie"],
                "frete": cab["modalidade_frete"],
                "meio": cab["meio_pagamento"],
                "total": float(tot["total"]),
                "prod": float(tot["produtos"]),
                "icms": float(tot["icms"]),
                "pis": float(tot["pis"]),
                "cofins": float(tot["cofins"]),
                "vfrete": float(tot["frete"]),
                "desc": float(tot["desconto"]),
                "info": cab["informacoes_complementares"],
                "amb": ambiente,
                "quem": quem,
            },
        )
    ).scalar()
    for i, it in enumerate(itens, start=1):
        q = Decimal(str(it["quantidade"]))
        vu = Decimal(str(it["valor_unitario"]))
        await db.execute(
            text(
                "INSERT INTO nfe_itens (id, nfe_id, numero_item, codigo_produto, descricao, ncm, cfop, "
                " unidade, quantidade, valor_unitario, valor_total, valor_desconto, icms_origem, icms_cst, "
                " icms_csosn, icms_aliquota, icms_base_calculo, icms_valor, pis_cst, cofins_cst, created_at) "
                "VALUES (gen_random_uuid(), CAST(:n AS uuid), :i, :cod, :desc, :ncm, :cfop, :un, :q, :vu, "
                " :vt, :vd, :orig, :cst, :csosn, :aliq, :bc, :vicms, :pis, :cof, now())"
            ),
            {
                "n": nfe_id,
                "i": i,
                "cod": it["codigo"][:60],
                "desc": it["descricao"][:120],
                "ncm": so_digitos(it["ncm"]),
                "cfop": so_digitos(it["cfop"]),
                "un": it["unidade"][:6],
                "q": float(q),
                "vu": float(vu),
                "vt": float(q * vu),
                "vd": float(it["valor_desconto"]),
                # gravado do que a RÉGUA devolveu. Era '0','40','07','07' fixos — constante
                # em coluna fiscal é a fábrica de defeito desta casa.
                "orig": it.get("icms_origem") or "0",
                "cst": it.get("icms_cst") or "",
                "csosn": it.get("icms_csosn") or "",
                "aliq": float(it.get("icms_aliquota") or 0),
                "bc": float(it.get("icms_base_calculo") or 0),
                "vicms": float(it.get("icms_valor") or 0),
                "pis": it.get("pis_cst") or "07",
                "cof": it.get("cofins_cst") or "07",
            },
        )
    await db.commit()

    if ambiente == "producao":
        return {
            "ok": True,
            "nfe_id": nfe_id,
            "numero": numero,
            "serie": serie,
            "valor_total": float(tot["total"]),
            "message": (
                f"Rascunho {numero}/{serie} de R$ {tot['total']:.2f} gravado PARA PRODUÇÃO — e NADA "
                "foi transmitido. Nota em produção é irreversível: confira em «Conferir antes de "
                "transmitir» e depois use «NF-e — transmitir em PRODUÇÃO», que pede confirmação "
                "e código OTP."
            ),
        }
    r = await transmitir(db, nfe_id, "homologacao")
    return {
        "ok": True,
        "nfe_id": nfe_id,
        "numero": numero,
        "serie": serie,
        "valor_total": float(tot["total"]),
        "status": r.get("status"),
        "chave": r.get("chave"),
        "message": f"HOMOLOGAÇÃO (sem valor fiscal) — nota {numero}/{serie}: {r.get('message')}",
    }


@router.post("/action/nfe-transmitir-homologacao", dependencies=_GATE)
async def rd_nfe_transmitir_homolog(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Reenvia um rascunho/rejeitada à SEFAZ de HOMOLOGAÇÃO — o caminho de corrigir e tentar de novo."""
    await _ensure(db)
    nfe_id = (payload.get("nfe_id") or "").strip()
    if not nfe_id:
        raise HTTPException(status_code=422, detail="Escolha a nota.")
    return await transmitir(db, nfe_id, "homologacao")


@router.post("/action/nfe-producao", dependencies=_GATE)
async def rd_nfe_producao(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """PRODUÇÃO — irreversível. Passa pelo gate único de escrita: confirmação humana + OTP no
    e-mail do Jordan. Sem OTP consumido nesta request, NADA vai à SEFAZ."""
    from modules.operacional.controllers.redesign_write_gate import GateError, OTPRequired, money_gov

    await _ensure(db)
    nfe_id = (payload.get("nfe_id") or "").strip()
    if not nfe_id:
        raise HTTPException(status_code=422, detail="Escolha o rascunho que vai a produção.")
    cab, itens = await carregar_nota(db, nfe_id)
    exigir(validar_nfe(cab, itens))  # o que a SEFAZ rejeitaria, recusamos antes de gastar a numeração
    valor = float(cab.get("valor_total_nota") or 0)
    otp = (payload.get("otp_code") or "").strip()
    ref = (payload.get("_gate_ref") or "").strip() or f"nfe-producao:{nfe_id}"

    async def _dispatch():
        return await transmitir(db, nfe_id, "producao")

    try:
        return await money_gov(
            db,
            ref=ref,
            amount=valor,
            otp_code=otp,
            real_dispatch=_dispatch,
            label="nfe_producao",
            dest=f"NF-e {cab.get('numero')}/{cab.get('serie')} · {(cab.get('destinatario_razao_social') or '')[:40]}",
        )
    except OTPRequired as e:
        return {
            "otp_required": True,
            "ref": e.ref,
            "message": (
                f"NF-e {cab.get('numero')}/{cab.get('serie')} de R$ {valor:.2f} para "
                f"{(cab.get('destinatario_razao_social') or '')[:40]} preparada para PRODUÇÃO. "
                f"Isto é IRREVERSÍVEL. {e.message}"
            ),
        }
    except GateError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/action/nfe-cancelar", dependencies=_GATE)
async def rd_nfe_cancelar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Cancela uma NF-e AUTORIZADA (evento 110111). Justificativa de 15+ caracteres — regra da
    SEFAZ. Cancelamento em PRODUÇÃO passa pelo mesmo gate humano da emissão."""
    from uuid import UUID as _UUID

    from modules.financial.integrations.nfe_provider import NFeError, create_nfe_provider
    from modules.operacional.controllers.redesign_write_gate import GateError, OTPRequired, money_gov

    await _ensure(db)
    nfe_id = (payload.get("nfe_id") or "").strip()
    justificativa = validar_justificativa(payload.get("justificativa"))
    cab, _itens = await carregar_nota(db, nfe_id)
    if (cab.get("status") or "") != "autorizada":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Esta nota está «{cab.get('status')}» — só nota AUTORIZADA pode ser cancelada. "
                "Rejeitada não existe na SEFAZ: corrija e transmita de novo."
            ),
        )
    if len(so_digitos(cab.get("chave_acesso"))) != 44:
        raise HTTPException(
            status_code=400, detail="Nota sem chave de acesso de 44 dígitos — não há o que cancelar na SEFAZ."
        )

    emps = {e["slug"]: e for e in await _empresas(db)}
    emp = emps.get(cab.get("empresa_slug") or "") or next(iter(emps.values()), None)
    if not emp or not emp["cert_path"]:
        raise HTTPException(status_code=422, detail="Empresa emitente sem certificado A1 cadastrado.")
    ambiente = cab.get("ambiente") or "homologacao"

    async def _dispatch():
        provider = create_nfe_provider(emp["cert_path"], emp["cert_senha"], ambiente=COD_AMBIENTE[ambiente], uf="AM")
        try:
            # DGX Z2: o evento 110111 exige o protocolo de autorização e o CNPJ do emitente.
            r = await provider.cancelar_nfe(
                so_digitos(cab["chave_acesso"]),
                justificativa,
                _UUID(nfe_id),
                str(cab.get("protocolo_autorizacao") or ""),
                so_digitos(cab["emitente_cnpj"]),
            )
        except NFeError as e:
            raise HTTPException(status_code=502, detail=f"A SEFAZ não cancelou: {e.message}") from e
        await db.execute(
            text(
                "UPDATE nfes SET status = 'cancelada', justificativa_cancelamento = :j, "
                " data_cancelamento = now(), protocolo_cancelamento = nullif(:p,''), updated_at = now() "
                "WHERE id::text = :i"
            ),
            {"j": justificativa, "p": str(r.get("protocolo") or "")[:40], "i": nfe_id},
        )
        await db.commit()
        return {
            "ok": True,
            "message": f"NF-e {cab.get('numero')}/{cab.get('serie')} cancelada. {r.get('mensagem') or ''}".strip(),
        }

    if ambiente != "producao":
        return await _dispatch()

    otp = (payload.get("otp_code") or "").strip()
    ref = (payload.get("_gate_ref") or "").strip() or f"nfe-cancelar:{nfe_id}"
    try:
        return await money_gov(
            db,
            ref=ref,
            amount=None,
            otp_code=otp,
            real_dispatch=_dispatch,
            label="nfe_cancelar",
            dest=str(cab.get("numero")),
        )
    except OTPRequired as e:
        return {
            "otp_required": True,
            "ref": e.ref,
            "message": f"Cancelamento em PRODUÇÃO da NF-e {cab.get('numero')}. {e.message}",
        }
    except GateError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Telas
# ─────────────────────────────────────────────────────────────────────────────────────────────
def _sel(key, label, opcoes, span="span 1", valor=None, ph=None) -> dict:
    d = {
        "key": key,
        "label": label,
        "type": "select",
        "span": span,
        "options": [{"value": v, "label": l} for v, l in opcoes],
    }
    if valor is not None:
        d["value"] = valor
    if ph:
        d["ph"] = ph
    return d


def _txt(key, label, span="span 1", valor=None, ph=None) -> dict:
    d = {"key": key, "label": label, "type": "text", "span": span}
    if valor is not None:
        d["value"] = valor
    if ph:
        d["ph"] = ph
    return d


async def telas(db, out: dict | None = None) -> dict:  # noqa: PLR0915 — quatro telas, lineares
    await _ensure(db)
    out = out if out is not None else {}

    emps = await _empresas(db)
    produtos, fonte_prod = await _produtos(db)
    clientes = (
        await db.execute(
            text(
                "SELECT id::text, name, coalesce(document_number,''), coalesce(address_city,'') "
                "FROM clients WHERE coalesce(ativo, true) ORDER BY name LIMIT 300"
            )
        )
    ).fetchall()

    _sem_ie = [e["razao"] for e in emps if not e["ie"]]
    aviso_emp = (
        f" ATENÇÃO: {', '.join(_sem_ie)} está sem Inscrição Estadual cadastrada — sem IE a SEFAZ não autoriza NF-e de mercadoria."
        if _sem_ie
        else ""
    )

    # ── 1) EMITIR ───────────────────────────────────────────────────────────────────────
    out["nfe-nova"] = {
        "title": "Emitir NF-e de produto (modelo 55)",
        "sub": (
            "Emite em HOMOLOGAÇÃO por padrão: a nota vai à SEFAZ de teste, o DANFE sai com a faixa "
            "«SEM VALOR FISCAL» e nada disso vale como documento fiscal — é assim que se confere "
            "antes de valer. Escolher PRODUÇÃO aqui só GRAVA o rascunho; transmitir de verdade é "
            "na tela «NF-e — transmitir em PRODUÇÃO», com confirmação e código OTP, porque nota "
            "autorizada em produção é IRREVERSÍVEL. A empresa escolhida define CNPJ, certificado, "
            "série e tributação."
            + aviso_emp
            + (
                f" Produtos vindos de «{fonte_prod}»"
                + (
                    " — cadastro fiscal próprio ainda não existe, então o NCM é o da última compra; confira antes de emitir."
                    if fonte_prod != "fin_produtos"
                    else "."
                )
            )
        ),
        "cta": "Gravar e emitir em homologação",
        "type": "form",
        "submit": {
            "endpoint": _ACT + "nfe-nova",
            "okMsg": "NF-e processada — veja o resultado.",
            "showResult": True,
            "confirm": "Confere: empresa, destinatário, itens e AMBIENTE. Emitir?",
        },
        # Anexar o orçamento do fornecedor e deixar a tela se preencher. O motor é o da Z5
        # (`?t=nfe-do-arquivo`); aqui ele só ganhou a porta no lugar onde se emite.
        "prefill": {
            "endpoint": _ACT + "nfe-ler-orcamento",
            "alvo": "orcamento",
            "label": "Anexar orçamento do fornecedor e preencher",
            "hint": "PDF, planilha ou foto da lista de material — preenche os itens com o markup abaixo",
            "accept": "image/*,.pdf,.xlsx,.xls,.csv",
            "sobrescreve": True,
        },
        "fields": [
            _sel(
                "empresa",
                "Empresa que emite*",
                [
                    (
                        e["slug"],
                        f"{e['razao']} — CNPJ {_br_doc(e['cnpj'])}"
                        + (" · SEM IE" if not e["ie"] else f" · IE {e['ie']}"),
                    )
                    for e in emps
                ],
                "span 2",
                valor=(emps[0]["slug"] if emps else None),
            ),
            _sel(
                "ambiente",
                "Ambiente*",
                list(AMBIENTES),
                "span 1",
                valor="homologacao",
            ),
            # Série 2 = a do Conecta PRO. Decisão do dono em 25/09/2026, «corte limpo»: a série 1
            # é do emissor de terceiro (nfemais), que parou na NF-e nº 10.026. Continuar nela
            # exigiria que o nfemais não emitisse NEM UMA depois da virada — se emitisse, os dois
            # pegariam o mesmo número e a SEFAZ recusaria com 539, queimando o número.
            # Com série própria o risco é zero e dá para ver onde foi a virada.
            _txt("serie", "Série*", "span 1", valor="2"),
            _sel(
                "cliente_id",
                "Destinatário — cliente cadastrado",
                [("avulso", "— AVULSO: vou digitar o destinatário abaixo —")]
                + [(str(c[0]), f"{c[1]} — {_br_doc(c[2])}" + (f" · {c[3]}" if c[3] else "")) for c in clientes],
                "span 2",
                valor="avulso",
            )
            | {
                # Escolher o cliente preenche os `dest_*` NA TELA. O emissor já relia o cliente
                # do banco ao emitir (a nota sempre saiu certa); o que faltava era a tela dizer
                # isso. `sobrescreve` porque trocar de cliente tem de trocar o endereço inteiro:
                # endereço do cliente anterior sobrando na tela parece conferido e não é.
                "fill": {"endpoint": _ACT + "nfe-cliente-dados", "campo": "cliente_id", "sobrescreve": True},
            },
            _txt("dest_documento", "Avulso — CNPJ ou CPF*", "span 1", ph="35710481000103"),
            _txt("dest_razao", "Avulso — razão social / nome*", "span 1"),
            _sel("dest_ind_ie", "Destinatário é contribuinte do ICMS?*", list(IND_IE), "span 2", valor="9"),
            _txt("dest_ie", "Inscrição Estadual (se contribuinte)", "span 1"),
            _txt("dest_cep", "CEP*", "span 1", ph="69050001"),
            _txt("dest_logradouro", "Logradouro*", "span 2"),
            _txt("dest_numero", "Número*", "span 1", valor="S/N"),
            _txt("dest_bairro", "Bairro*", "span 1"),
            _txt("dest_municipio", "Município*", "span 1", ph="Manaus"),
            _txt("dest_uf", "UF*", "span 1", valor="AM"),
            _txt("dest_cod_municipio", "Código IBGE do município*", "span 1", valor="1302603"),
            _txt("dest_email", "E-mail (recebe o XML/DANFE)", "span 1"),
            _txt("natureza_operacao", "Natureza da operação*", "span 2", valor="VENDA DE MERCADORIA"),
            _sel("cfop", "CFOP*", list(CFOPS), "span 2", valor="5102"),
            _sel("finalidade", "Finalidade*", list(FINALIDADES), "span 1", valor="1"),
            _sel(
                "produto",
                "Produto*",
                [
                    (
                        p["codigo"],
                        f"{p['codigo']} — {p['descricao'][:48]}"
                        + (f" · NCM {p['ncm']}" if p["ncm"] else " · SEM NCM (cadastre antes)"),
                    )
                    for p in produtos
                ],
                "span 2",
            ),
            _txt("descricao", "Descrição na nota (vazio = a do produto)", "span 2"),
            _txt("ncm", "NCM (vazio = o do produto)", "span 1", ph="85258900"),
            _txt("unidade", "Unidade", "span 1", valor="UN"),
            _txt("quantidade", "Quantidade*", "span 1", valor="1"),
            _txt("valor_unitario", "Valor unitário (R$)*", "span 1", ph="450,00"),
            # Markup sobre o CUSTO do fornecedor, usado pelo botão de anexar orçamento acima.
            # Não mexe em valor digitado à mão — só no que for lido do arquivo. Markup ≠ margem:
            # 40% de markup sobre custo 100 dá preço 140, que é 28,6% de margem sobre a venda.
            _txt("markup_percent", "Markup sobre o custo do orçamento (%)", "span 1", valor="40"),
            _txt("valor_desconto", "Desconto (R$)", "span 1", valor="0"),
            {
                "key": "itens_extras",
                "label": "Itens adicionais (JSON) — deixe [] se a nota tem um item só",
                "type": "json",
                "span": "span 2",
                "value": "[]",
                "ph": '[{"codigo": "CAM-002", "quantidade": 3, "valor_unitario": 320.00}]',
            },
            _sel("modalidade_frete", "Frete", list(FRETES), "span 1", valor="9"),
            _txt("valor_frete", "Valor do frete (R$)", "span 1", valor="0"),
            {
                "key": "informacoes_complementares",
                "label": "Dados adicionais (vão no campo infCpl da nota)",
                "type": "textarea",
                "span": "span 2",
            },
        ],
    }

    # ── 2) CONFERIR ANTES DE TRANSMITIR (leitura pura) ──────────────────────────────────
    rascunhos = (
        await db.execute(text(_SQL_NFE + " AND status IN ('rascunho','rejeitada') ORDER BY created_at DESC LIMIT 60"))
    ).fetchall()
    linhas_prev = []
    for r in rascunhos:
        cab = dict(zip(_CAMPOS_NFE, r, strict=False))
        _, itens = await carregar_nota(db, cab["id"])
        pend = validar_nfe(cab, itens)
        tot = calcular_totais(itens, cab["valor_frete"])
        linhas_prev.append(
            {
                "cells": [
                    t(f"{cab['numero']}/{cab['serie']}", 600, _ND),
                    t((cab["destinatario_razao_social"] or "—")[:34]),
                    t(str(len(itens))),
                    t(brl(tot["produtos"])),
                    t(brl(tot["icms"]) + " / " + brl(tot["pis"]) + " / " + brl(tot["cofins"])),
                    t(brl(tot["total"]), 600),
                    b(
                        ("PRODUÇÃO" if cab["ambiente"] == "producao" else "Homologação")
                        if cab["ambiente"]
                        else "(não registrado)",
                        "bad" if cab["ambiente"] == "producao" else "info",
                    ),
                    b("Pronta para transmitir", "ok")
                    if not pend
                    else b(f"{len(pend)} pendência(s): " + " | ".join(pend), "bad"),
                ],
                "docs": [doc("Ver XML montado", f"/api/v1/redesign/nfe/{cab['id']}/xml", fmt="xml")],
            }
        )
    out["nfe-preview"] = {
        "title": "Conferir antes de transmitir",
        "sub": (
            "O XML montado e o cálculo dos tributos de cada rascunho, com o que está FALTANDO em "
            "vermelho — produto sem NCM, destinatário incompleto, CFOP incompatível com a UF do "
            "destino. Nada é transmitido nesta tela: é só leitura. Corrigido, transmita em "
            "«NF-e emitidas» (homologação) ou na tela de produção."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar destinatário…",
        "cols": [
            "Nº/Série",
            "Destinatário",
            "Itens",
            "Produtos",
            "ICMS / PIS / COFINS",
            "Total",
            "Ambiente",
            "Situação",
        ],
        "grid": "0.8fr 1.6fr 0.5fr 0.9fr 1.3fr 0.9fr 0.9fr 2.4fr",
        "rows": linhas_prev,
    }

    # ── 3) EMITIDAS ─────────────────────────────────────────────────────────────────────
    todas = (await db.execute(text(_SQL_NFE + " ORDER BY created_at DESC NULLS LAST LIMIT 200"))).fetchall()
    linhas = []
    for r in todas:
        c = dict(zip(_CAMPOS_NFE, r, strict=False))
        st = (c["status"] or "").lower()
        motivo = (c["motivo_rejeicao"] or "").strip()
        acoes = []
        if st == "autorizada":
            acoes.append(
                {
                    "title": f"Cancelar a NF-e {c['numero']}/{c['serie']} de {(c['destinatario_razao_social'] or '')[:40]}",
                    "endpoint": _ACT + "nfe-cancelar",
                    "method": "POST",
                    "btnLabel": "Cancelar",
                    "submitLabel": "Cancelar na SEFAZ",
                    "btnStyle": "outline",
                    "okMsg": "Cancelamento enviado. Recarregue.",
                    "fields": [
                        {"key": "nfe_id", "type": "hidden", "value": c["id"]},
                        {
                            "key": "justificativa",
                            "label": "Justificativa* (mínimo 15 caracteres — exigência da SEFAZ)",
                            "type": "textarea",
                            "span": "span 2",
                            "value": "",
                            "ph": "mercadoria devolvida pelo cliente antes da entrega",
                        },
                    ],
                }
            )
        elif st in ("rascunho", "rejeitada"):
            acoes.append(
                {
                    "title": f"Transmitir a NF-e {c['numero']}/{c['serie']} à SEFAZ de HOMOLOGAÇÃO (sem valor fiscal)",
                    "endpoint": _ACT + "nfe-transmitir-homologacao",
                    "method": "POST",
                    "btnLabel": "Transmitir (homologação)",
                    "submitLabel": "Transmitir em homologação",
                    "btnStyle": "primary",
                    "okMsg": "Transmitida. Recarregue.",
                    "fields": [{"key": "nfe_id", "type": "hidden", "value": c["id"]}],
                }
            )
        if st == "autorizada":
            acoes.append(
                {
                    # OFERECE o caminho que já existe (`receivable-condicao`, o mesmo endpoint e os
                    # mesmos campos do form «Registrar conta a receber» do financeiro) — não cria
                    # nada sozinho. Emitir nota e lançar título são duas decisões, não um efeito
                    # colateral: quem emite escolhe o vencimento.
                    "title": f"Lançar o título a receber da NF-e {c['numero']}/{c['serie']} — nada é criado sem você confirmar",
                    "endpoint": _ACT + "receivable-condicao",
                    "method": "POST",
                    "btnLabel": "Lançar a receber",
                    "submitLabel": "Registrar a conta a receber",
                    "btnStyle": "outline",
                    "okMsg": "Conta a receber registrada.",
                    "fields": [
                        {
                            "key": "description",
                            "type": "text",
                            "label": "Descrição*",
                            "span": "span 2",
                            "value": f"NF-e {c['numero']}/{c['serie']} — {(c['destinatario_razao_social'] or '')[:40]}",
                        },
                        {
                            "key": "customer_name",
                            "type": "text",
                            "label": "Cliente/Sacado",
                            "span": "span 1",
                            "value": (c["destinatario_razao_social"] or "")[:60],
                        },
                        {
                            "key": "valor",
                            "type": "text",
                            "label": "Valor (R$)*",
                            "span": "span 1",
                            "value": f"{float(c['valor_total_nota'] or 0):.2f}",
                        },
                        {"key": "due_date", "type": "date", "label": "Vencimento*", "span": "span 1", "value": ""},
                    ],
                }
            )
        linhas.append(
            {
                "cells": [
                    t(f"{c['numero'] or '—'}/{c['serie'] or '—'}", 600, _ND),
                    t(formatar_chave(c["chave_acesso"]), 400) if c["chave_acesso"] else t("— sem chave —"),
                    t((c["destinatario_razao_social"] or "—")[:30]),
                    t(brl(c["valor_total_nota"] or 0), 600),
                    b((c["status"] or "—").capitalize(), STATUS_TOM.get(st, "info")),
                    b(
                        ("PRODUÇÃO" if c["ambiente"] == "producao" else "Homologação")
                        if c["ambiente"]
                        else "(não registrado)",
                        "bad" if c["ambiente"] == "producao" else "info",
                    ),
                    # o xMotivo INTEIRO: é ele que ensina a corrigir. Truncar seria esconder.
                    t(motivo or (c["justificativa_cancelamento"] or "—")),
                ],
                "docs": [
                    doc("Ver XML", f"/api/v1/redesign/nfe/{c['id']}/xml", fmt="xml"),
                    doc("DANFE (PDF)", f"/api/v1/redesign/nfe/{c['id']}/danfe/pdf", fmt="pdf"),
                ],
                **({"actions": acoes} if acoes else {}),
            }
        )
    _aut = sum(1 for r in todas if (r[4] or "") == "autorizada")
    out["nfes-emitidas"] = {
        "title": "NF-e emitidas (produto, modelo 55)",
        "sub": (
            f"{len(todas)} nota(s) · {_aut} autorizada(s). O DANFE de homologação sai com a faixa "
            "«SEM VALOR FISCAL». A coluna do fim traz o xMotivo INTEIRO da SEFAZ — é o texto que diz "
            "exatamente o que corrigir. Cancelar só vale para nota AUTORIZADA e exige justificativa "
            "de 15+ caracteres (regra da SEFAZ); rejeitada não existe no fisco: corrija e transmita "
            "de novo. As notas anteriores a esta tela aparecem com ambiente «(não registrado)» — "
            "não dá para adivinhar em qual ambiente elas foram."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar destinatário, chave, motivo…",
        "cols": [
            "Nº/Série",
            "Chave de acesso",
            "Destinatário",
            "Valor",
            "Status",
            "Ambiente",
            "Motivo da SEFAZ (xMotivo)",
        ],
        "grid": "0.7fr 2.4fr 1.3fr 0.9fr 0.9fr 0.9fr 2.6fr",
        "rows": linhas,
    }

    # ── 4) PRODUÇÃO (gated) ─────────────────────────────────────────────────────────────
    prontas = [
        dict(zip(_CAMPOS_NFE, r, strict=False))
        for r in (
            await db.execute(
                text(
                    _SQL_NFE
                    + " AND status IN ('rascunho','rejeitada') AND coalesce(ambiente,'') = 'producao' ORDER BY created_at DESC LIMIT 40"
                )
            )
        ).fetchall()
    ]
    out["nfe-producao"] = {
        "title": "NF-e — transmitir em PRODUÇÃO",
        "sub": (
            "ISTO EMITE NOTA FISCAL DE VERDADE. Uma vez autorizada, a nota existe no fisco e só sai "
            "por cancelamento (prazo de 24 h) ou carta de correção. Por isso o caminho é gated: "
            "confirmação humana + código OTP no e-mail do Jordan, o mesmo gate do pagamento em lote. "
            "Só aparecem aqui os rascunhos que você marcou como PRODUÇÃO em «Emitir NF-e» e que já "
            "passaram na conferência."
        ),
        "cta": "TRANSMITIR em produção",
        "type": "form",
        "submit": {
            "endpoint": _ACT + "nfe-producao",
            "gated": True,
            "confirm": "Isto emite a NOTA FISCAL EM PRODUÇÃO, de verdade e sem volta. Confirma?",
            "okMsg": "Transmitida — veja o retorno da SEFAZ.",
            "showResult": True,
        },
        "fields": [
            _sel(
                "nfe_id",
                "Rascunho marcado para PRODUÇÃO*",
                [
                    (
                        p["id"],
                        f"{p['numero']}/{p['serie']} — {(p['destinatario_razao_social'] or '')[:36]} — R$ {float(p['valor_total_nota'] or 0):,.2f}",
                    )
                    for p in prontas
                ],
                "span 2",
                ph="— escolha o rascunho —" if prontas else "— nenhum rascunho marcado para produção —",
            )
        ],
    }
    return out
