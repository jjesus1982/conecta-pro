"""Margem por (empresa, linha de negócio, natureza do item) — Bloco 1 do prompt de 11/09/2026.

Antes havia UM escalar para o grupo inteiro: `{"chave":"margem","valor":0.15}`. Isso é falso
desde que existe a operação de eletrônica — serviço alocado, venda de equipamento e mão de
obra de instalação têm estrutura de custo e de risco diferentes. Consequência real: toda
proposta de eletrônica era precificada FORA do ERP, numa planilha, com margem decidida a
dedo, e a do The Sun nasceu com 32% na manutenção sem registro de por quê.

⭐ A CONVENÇÃO VIAJA COM O NÚMERO. Jordan confirmou em 11/09/2026, respondendo à pergunta
bloqueante: é **margem sobre o preço de venda**, a mesma do 15% que já estava cadastrado.
Num item de custo R$ 100.000:

    margem 35% sobre o preço  ->  preço R$ 153.846   (custo / (1 - margem))
    markup 35% sobre o custo  ->  preço R$ 135.000   (custo * (1 + markup))

São R$ 18.846 de diferença por proposta. Guardar o número sem a convenção é guardar metade
do dado — por isso ela vai na coluna E no retorno de toda tool que usa margem.

⚠️ SEM FALLBACK SILENCIOSO. Combinação não cadastrada RECUSA com `MARGEM_NAO_CADASTRADA`.
Cair para 15% quando a margem de eletrônica é 35% ou 40% é errar o preço para MENOS e só
descobrir no fechamento — prejuízo que não aparece em lugar nenhum até tarde.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

NATUREZAS = ("servico_alocado", "produto", "mao_de_obra_tecnica")
LINHAS = ("patrimonial", "eletronica")


class MargemNaoCadastrada(Exception):
    """Recusa explícita. Quem chama devolve 422 com a dica de onde cadastrar."""

    def __init__(self, empresa: str, linha: str, natureza: str,
                 disponiveis: list[dict] | None = None) -> None:
        self.empresa, self.linha, self.natureza = empresa, linha, natureza
        self.disponiveis = disponiveis or []
        super().__init__(
            f"Não há margem cadastrada para ({empresa}, {linha}, {natureza}).")


@dataclass(frozen=True)
class Margem:
    """A margem E a procedência dela. Parâmetro de dinheiro sem procedência ninguém confia."""

    valor: float
    convencao: str
    label: str
    confirmado_por: str | None
    confirmado_em: str | None
    empresa_cnpj: str
    linha_negocio: str
    natureza_item: str

    def preco(self, custo: float) -> float:
        """Preço a partir do custo, na convenção declarada."""
        if self.convencao == "markup_sobre_custo":
            return round(float(custo) * (1 + self.valor), 2)
        # margem_sobre_preco (padrão): custo / (1 - margem)
        return round(float(custo) / (1 - self.valor), 2)

    def memoria(self, custo: float) -> dict:
        """A linha da memória de cálculo. É isto que aparece na proposta, por ITEM.

        O Bloco 1 é explícito: "se a memória de cálculo mostrar uma margem só, está errado".
        Por isso cada linha carrega a sua margem, o percentual e de onde ele veio.
        """
        p = self.preco(custo)
        return {
            "custo": round(float(custo), 2),
            "preco": p,
            "lucro": round(p - float(custo), 2),
            "margem": self.valor,
            "margem_pct": f"{self.valor * 100:.2f}%",
            "convencao": self.convencao,
            "natureza_item": self.natureza_item,
            "linha_negocio": self.linha_negocio,
            "origem_do_parametro": self.label,
            "confirmado_por": self.confirmado_por,
            "confirmado_em": self.confirmado_em,
        }


def _so_digitos(v: str) -> str:
    return "".join(c for c in str(v or "") if c.isdigit())


async def listar(db: AsyncSession, *, empresa: str | None = None,
                 linha_negocio: str | None = None,
                 natureza_item: str | None = None) -> list[dict]:
    """TODAS as margens que casam com o filtro. Sem filtro, todas — nunca um escalar."""
    cond, params = [], {}
    if empresa:
        cond.append("empresa_cnpj = :e")
        params["e"] = _so_digitos(empresa)
    if linha_negocio:
        cond.append("linha_negocio = :l")
        params["l"] = linha_negocio
    if natureza_item:
        cond.append("natureza_item = :n")
        params["n"] = natureza_item
    onde = (" WHERE " + " AND ".join(cond)) if cond else ""
    rs = (await db.execute(text(
        "SELECT empresa_cnpj, linha_negocio, natureza_item, margem::float AS margem, "
        "       convencao, label, confirmado_por, confirmado_em::text AS confirmado_em "
        f"  FROM crm_pricing_margens{onde} "
        " ORDER BY linha_negocio, natureza_item"), params)).mappings().all()
    return [dict(r) for r in rs]


async def resolver(db: AsyncSession, *, empresa_cnpj: str, linha_negocio: str,
                   natureza_item: str) -> Margem:
    """A margem desta combinação. RECUSA se não existir — nunca chuta 15%."""
    linhas = await listar(db, empresa=empresa_cnpj, linha_negocio=linha_negocio,
                          natureza_item=natureza_item)
    if not linhas:
        raise MargemNaoCadastrada(
            _so_digitos(empresa_cnpj), linha_negocio, natureza_item,
            disponiveis=await listar(db))
    r = linhas[0]
    return Margem(
        valor=float(r["margem"]), convencao=r["convencao"], label=r["label"],
        confirmado_por=r["confirmado_por"], confirmado_em=r["confirmado_em"],
        empresa_cnpj=r["empresa_cnpj"], linha_negocio=r["linha_negocio"],
        natureza_item=r["natureza_item"],
    )


def envelope_recusa(e: MargemNaoCadastrada) -> dict:
    """O 422 que o Bloco 1 especifica, com a lista do que EXISTE para o agente escolher."""
    return {
        "ok": False, "codigo": "MARGEM_NAO_CADASTRADA", "http": 422,
        "mensagem": str(e),
        "dica": ("Cadastre em definir_parametros_precificacao, ou classifique o item como "
                 + " | ".join(NATUREZAS) + "."),
        "combinacao_pedida": {"empresa_cnpj": e.empresa, "linha_negocio": e.linha,
                              "natureza_item": e.natureza},
        "margens_cadastradas": e.disponiveis,
    }
