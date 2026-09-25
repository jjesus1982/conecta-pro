"""Z7 — o orçamento do fornecedor virando nota: markup, preenchimento e o limite do Bartolo.

Nasceu em 25/09/2026, de três pedidos do dono feitos com a tela `?t=nfe-nova` aberta:

  1. «quando selecionar o condomínio, já preencher todas as informações nos campos subsequentes»
  2. «botão pra eu anexar documentos ou fotos, que são orçamentos que os fornecedores mandam,
      daí o nosso sistema lê e já lança os produtos»
  3. «ter ali o Bartolo […] nessa lista o custo do material do nosso fornecedor, acrescenta
      mais 40% de markup e manda emitir a nota para este cliente»

Dois dos três JÁ existiam e estavam noutra tela — o preenchimento acontecia no servidor sem a
tela contar, e a leitura por LLM morava em `?t=nfe-do-arquivo`. O que este oráculo vigia é o
que passou a existir, e principalmente o que NÃO pode passar a existir.

O QUE ELE AFIRMA
  (a) `aplicar_markup` faz markup, não margem, e guarda o custo ao lado. Confundir os dois é
      emitir nota pelo preço de compra. Markup 0/vazio/negativo não mexe em preço nenhum —
      não se inventa margem por omissão.
  (b) `_itens_limpos` RECUSA item sem descrição e item sem preço legível, e nunca completa.
      Esta é a parede entre «o modelo leu um PDF» e «isso virou preço de nota fiscal».
  (c) A tela `nfe-nova` declara as duas portas (`prefill` do orçamento e `fill` no cliente) e o
      campo de markup — e a lista `_CAMPOS_DEST` bate campo a campo com os `dest_*` da tela.
      Se divergirem, trocar de cliente deixa endereço velho na tela: parece conferido e não é.
  (d) **O Bartolo não transmite.** A ação `nota_do_orcamento` está registrada, é 🔵, e o
      módulo dela não chama nada que vá à SEFAZ. É o item mais importante daqui: o clique
      irreversível tem UM lugar — a tela com OTP —, e uma segunda porta pelo chat esvaziaria
      aquela. A primeira vez que um modelo entendesse «esse cliente» errado, a nota já estaria
      autorizada no CNPJ de outro.

VERMELHO ANTES: em 25/09, antes desta frente, (a) e (b) davam ImportError — `aplicar_markup` e
`tools_acao_fiscal_nota` não existiam — e (c) falhava em todos os três itens.
"""

from __future__ import annotations

import ast
import asyncio
import pathlib
import sys
from decimal import Decimal

_ORQ = str(pathlib.Path(__file__).resolve().parent)
if _ORQ not in sys.path:
    sys.path.insert(0, _ORQ)

#: O que o módulo de ação do chat não pode CHAMAR nem IMPORTAR. Não é lista de boas intenções:
#: é AST no arquivo, porque a intenção não sobrevive ao próximo que editar o arquivo.
#:
#: Por AST e não por grep, e isto foi medido na primeira execução: o grep ingênuo reprovou o
#: arquivo por causa da frase «**Não emite e não transmite nada**» — texto que o aprovador LÊ
#: na Central, escrito exatamente para deixar o limite claro. Uma régua que reprova a frase
#: que explica a regra é régua errada, e afrouxá-la seria a resposta preguiçosa. O certo é
#: medir chamada e import, que é o que faz mal.
_PROIBIDO_NO_CHAT = (
    "transmitir",
    "autorizar_nfe",
    "enviar_sefaz",
    "emitir_nfe",
    "nfe_provider",
    "_exigir_ambiente",
    "emissor",
)


async def main() -> int:
    from core.database import async_session_factory

    falhas: list[str] = []
    medidas: list[str] = []

    # ── (a) markup é markup, e o custo fica ───────────────────────────────────────────
    from modules.fiscal.services.orcamento_para_nota import aplicar_markup

    base = [
        {
            "descricao": "cabo",
            "quantidade": Decimal("2"),
            "valor_unitario": Decimal("100"),
            "desconto_percent": Decimal("0"),
        }
    ]
    r = aplicar_markup([dict(base[0])], 40)[0]
    if r["valor_unitario"] != Decimal("140.00"):
        falhas.append(f"(a) markup 40% sobre custo 100 deu {r['valor_unitario']}, esperado 140.00")
    if r.get("custo_unitario") != Decimal("100"):
        falhas.append(f"(a) o custo do fornecedor não ficou guardado: {r.get('custo_unitario')!r}")
    if r["valor_total"] != Decimal("280.00"):
        falhas.append(f"(a) total de 2 × 140 deu {r['valor_total']}, esperado 280.00")
    # margem ≠ markup: 40% de markup é 28,57% de margem sobre a venda
    if r.get("margem_percent") != Decimal("28.57"):
        falhas.append(f"(a) margem devolvida {r.get('margem_percent')!r}, esperado 28.57 (markup 40% ≠ margem 40%)")
    for vazio in (0, "", None, -5):
        intacto = aplicar_markup([dict(base[0])], vazio)[0]
        if intacto["valor_unitario"] != Decimal("100"):
            falhas.append(
                f"(a) markup {vazio!r} mexeu no preço ({intacto['valor_unitario']}) — omissão não inventa margem"
            )
    medidas.append("markup 40%: custo 100 → venda 140, margem 28,57%, custo preservado")

    # ── (b) a parede entre o que o modelo leu e o preço da nota ──────────────────────
    from modules.ai.conversation.services.orquestrador.tools_acao_fiscal_nota import _itens_limpos

    aceitos, recusas = _itens_limpos(
        [
            {"descricao": "Cabo coaxial RG59", "quantidade": 10, "valor_unitario": "12,50"},
            {"descricao": "", "valor_unitario": 99},
            {"descricao": "Conector BNC", "valor_unitario": 0},
            {"descricao": "Fonte 12V", "valor_unitario": "ilegível"},
        ]
    )
    if len(aceitos) != 1:
        falhas.append(f"(b) aceitou {len(aceitos)} item(ns), esperado 1 — só o que tem descrição E preço")
    if len(recusas) != 3:
        falhas.append(f"(b) explicou {len(recusas)} recusa(s), esperado 3 — recusa sem motivo não ensina nada")
    if aceitos and aceitos[0]["valor_unitario"] != 12.5:
        falhas.append(f"(b) não leu vírgula decimal brasileira: {aceitos[0]['valor_unitario']!r}")
    if not _itens_limpos([])[1]:
        falhas.append("(b) lista vazia passou calada — tinha de recusar explicando")
    medidas.append(f"itens do modelo: 1 aceito, {len(recusas)} recusados com motivo")

    # ── (c) a tela declara as portas, e a lista de campos bate com ela ───────────────
    from modules.operacional.controllers.redesign_builders import _dgx_z3_tela_nfe as z3

    async with async_session_factory() as db:
        telas = await z3.telas(db)
    nova = telas.get("nfe-nova") or {}
    pre = nova.get("prefill") or {}
    if "nfe-ler-orcamento" not in str(pre.get("endpoint") or ""):
        falhas.append("(c) `nfe-nova` não tem o botão de anexar orçamento — o dono pediu ele ONDE se emite")
    if not pre.get("sobrescreve"):
        falhas.append("(c) o prefill do orçamento não sobrescreve — itens do orçamento anterior ficariam na tela")
    campos = {f.get("key"): f for f in (nova.get("fields") or []) if isinstance(f, dict)}
    if "markup_percent" not in campos:
        falhas.append("(c) a tela não tem campo de markup — o botão de anexar leria custo e emitiria pelo custo")
    fill = (campos.get("cliente_id") or {}).get("fill") or {}
    if "nfe-cliente-dados" not in str(fill.get("endpoint") or ""):
        falhas.append("(c) escolher o cliente não preenche os `dest_*` na tela")
    if not fill.get("sobrescreve"):
        falhas.append("(c) o preenchimento do cliente não sobrescreve — trocar de cliente deixaria endereço velho")
    na_tela = {k for k in campos if k.startswith("dest_")}
    if na_tela != set(z3._CAMPOS_DEST):
        falhas.append(
            f"(c) `_CAMPOS_DEST` divergiu da tela — só na tela: {sorted(na_tela - set(z3._CAMPOS_DEST))}, "
            f"só na lista: {sorted(set(z3._CAMPOS_DEST) - na_tela)}"
        )
    medidas.append(f"tela nfe-nova: prefill + fill + markup, {len(na_tela)} campos de destinatário casando")

    # ── (d) o Bartolo prepara, e para antes da SEFAZ ─────────────────────────────────
    from modules.ai.conversation.services.orquestrador.agir_dispatcher import _ACOES

    achou = "nota_do_orcamento" in (_ACOES.get("fiscal") or {})
    if not achou:
        falhas.append("(d) a ação `nota_do_orcamento` não está registrada — o Bartolo não sabe fazer nada com o anexo")
    caminho = pathlib.Path("/app/modules/ai/conversation/services/orquestrador/tools_acao_fiscal_nota.py")
    fonte = caminho.read_text()
    arvore = ast.parse(fonte)
    tocados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call):  # o que ele CHAMA
            alvo = no.func
            nome = getattr(alvo, "attr", None) or getattr(alvo, "id", None)
            if nome:
                tocados.add(str(nome))
        elif isinstance(no, ast.Import):  # o que ele TRAZ
            tocados.update(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom):
            tocados.add(no.module or "")
            tocados.update(a.name for a in no.names)
    for proibido in _PROIBIDO_NO_CHAT:
        atingidos = [t for t in tocados if proibido in t]
        if atingidos:
            falhas.append(
                f"(d) o módulo do chat chama/importa {atingidos} — transmitir tem UM lugar, e é a tela com OTP"
            )
    if 'gate="🔵"' not in fonte:
        falhas.append("(d) a ação mudou de gate — rascunho de nota é 🔵; se virou 🔴 alguém a fez transmitir")
    medidas.append("ação do chat: registrada, 🔵, sem uma linha que vá à SEFAZ")

    # ── (e) o CONTRATO de chaves entre a tela e o emissor ────────────────────────────
    #
    # O defeito mais caro do dia, e o mais silencioso: `rd_nfe_nova` entregava ao emissor as
    # chaves `icms_situacao`/`pis_situacao`/`cofins_situacao`, e `nfe_provider._montar_nfe()`
    # lê `icms_cst`/`pis_cst`/`cofins_cst`. Nomes PARECIDOS. O dicionário chegava gordo, a
    # leitura vinha vazia, e o emissor recusava com «Item 1 sem CST/CSOSN de ICMS» em TODA
    # emissão desta tela — inclusive homologação. A tela nunca tinha emitido uma NF-e.
    #
    # Nada disso aparece em teste de unidade dos dois lados: cada um está certo sozinho. O
    # que quebra é o CONTRATO, e contrato só se afirma olhando os dois ao mesmo tempo. Por
    # isso este item lê, por AST, TODA chave que o emissor pede de um item, e exige que o
    # construtor da tela entregue cada uma. Renomear de qualquer lado fica vermelho.
    fonte_prov = pathlib.Path("/app/modules/financial/integrations/nfe_provider.py").read_text()
    pedidas: set[str] = set()
    for no in ast.walk(ast.parse(fonte_prov)):
        # `item.get("chave")` / `item["chave"]` dentro do laço de itens do emissor
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and no.func.attr == "get":
            alvo = no.func.value
            if isinstance(alvo, ast.Name) and alvo.id == "item" and no.args:
                if isinstance(no.args[0], ast.Constant) and isinstance(no.args[0].value, str):
                    pedidas.add(no.args[0].value)
        elif isinstance(no, ast.Subscript) and isinstance(no.value, ast.Name) and no.value.id == "item":
            if isinstance(no.slice, ast.Constant) and isinstance(no.slice.value, str):
                pedidas.add(no.slice.value)

    fonte_z3 = pathlib.Path(
        "/app/modules/operacional/controllers/redesign_builders/_dgx_z3_tela_nfe.py"
    ).read_text()
    # Regex e não AST aqui, de propósito: o trecho é um dicionário DENTRO de uma
    # compreensão de lista dentro de outro dicionário — fatiar texto para o `ast.parse`
    # engolir produz código que não fecha. O que importa afirmar é «a chave X é escrita
    # neste bloco», e isso um regex de chave literal responde sem ambiguidade.
    import re as _re  # noqa: PLC0415

    corpo = fonte_z3.split('"items": [', 1)
    entregues: set[str] = (
        set(_re.findall(r'"([a-z_]+)":', corpo[1].split("for it in itens", 1)[0])) if len(corpo) > 1 else set()
    )
    if not entregues:
        falhas.append("(e) não consegui ler o dicionário de itens da tela — o contrato ficou sem vigia")
    faltando = sorted(k for k in pedidas if k not in entregues)
    if faltando:
        falhas.append(
            f"(e) o emissor pede {faltando} de cada item e a tela NÃO entrega — "
            f"é assim que «Item 1 sem CST/CSOSN» volta"
        )
    medidas.append(f"contrato tela×emissor: {len(pedidas)} chave(s) pedidas, todas entregues")

    print(" · ".join(medidas))
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) no caminho orçamento → nota")
    print(
        "OK orçamento → nota: markup guarda o custo e não se confunde com margem, item sem preço é "
        "recusado, a tela de emissão tem as duas portas e o Bartolo prepara sem transmitir"
    )
    print(f"TOTAL desvios Z7: {len(falhas)}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        print("TOTAL desvios Z7: >0")
        sys.exit(1)
