"""Regime tributário POR CNPJ — Bloco 2 do prompt de 11/09/2026.

Os tributos cadastrados eram PIS 1,65% + COFINS 7,6% **não-cumulativos** + ISS 5%. Não
cumulativo é Lucro Real. Não havia nenhum parâmetro de DAS/Simples — e a Patrimonial é
optante (Anexo III). Resultado: quem precificava fora do ERP fazia gross-up por DAS, quem
precificava dentro fazia por PIS/COFINS/ISS, e os dois não podem estar certos. A diferença
entre 14,25% de carga e uma faixa do Anexo III é a margem inteira de um contrato.

⭐ NÃO ESTIMA ALÍQUOTA. As FAIXAS abaixo são a LC 123/2006 — fato público, verificável, e
por isso podem estar no código. O RBT12 é dado da empresa e muda todo mês; sem ele
cadastrado, a resposta é `NAO_CADASTRADO` e a precificação RECUSA. Errar imposto para menos
vira prejuízo silencioso que só aparece no fechamento.

⚠️ POLÍTICA DE ATUALIZAÇÃO, exigida pelo Bloco 2.4: o RBT12 é LIDO do cadastro, nunca
recalculado na hora. Recalcular a cada leitura faria a mesma proposta ter dois preços em
dias diferentes sem ninguém decidir nada. `atualizado_em` vai no retorno para o consumidor
saber se está lendo dado velho; acima de 60 dias o retorno traz aviso de defasagem.

⚠️ FATOR R: o enquadramento entre Anexo III e V depende de folha/receita >= 28%. Aqui o
anexo vem do CADASTRO (`empresas.anexo_simples`), que é decisão da contabilidade — este
módulo não reenquadra ninguém. Se o fator R mudar, quem muda o cadastro é quem tem a
competência.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# LC 123/2006. (limite_rbt12, aliquota_nominal, parcela_a_deduzir)
FAIXAS = {
    "III": [
        (180_000.00, 0.0600, 0.00),
        (360_000.00, 0.1120, 9_360.00),
        (720_000.00, 0.1320, 17_640.00),
        (1_800_000.00, 0.1600, 35_640.00),
        (3_600_000.00, 0.2100, 125_640.00),
        (4_800_000.00, 0.3300, 648_000.00),
    ],
    "IV": [
        (180_000.00, 0.0450, 0.00),
        (360_000.00, 0.0900, 8_100.00),
        (720_000.00, 0.1020, 12_420.00),
        (1_800_000.00, 0.1400, 39_780.00),
        (3_600_000.00, 0.2200, 183_780.00),
        (4_800_000.00, 0.3300, 828_000.00),
    ],
}
TETO_SIMPLES = 4_800_000.00
DIAS_PARA_DEFASAR = 60


class RegimeNaoCadastrado(Exception):
    """Recusa explícita. Estimar alíquota é o que o Bloco 2 proíbe."""

    def __init__(self, cnpj: str, faltando: str) -> None:
        self.cnpj, self.faltando = cnpj, faltando
        super().__init__(f"Regime tributário incompleto para {cnpj}: falta {faltando}.")


@dataclass(frozen=True)
class Regime:
    cnpj: str
    razao_social: str
    regime: str
    anexo: str | None
    rbt12: float | None
    aliquota_efetiva: float | None
    fonte: str
    atualizado_em: str | None
    # carga usada no gross-up quando NÃO é Simples
    tributos_sobre_servico: dict | None = None

    @property
    def defasado(self) -> bool:
        if not self.atualizado_em:
            return True
        try:
            return date.fromisoformat(self.atualizado_em[:10]) < date.today() - timedelta(
                days=DIAS_PARA_DEFASAR)
        except ValueError:
            return True

    def carga_total(self) -> float:
        """A fração do PREÇO que vira imposto. É com ela que se faz o gross-up."""
        if self.regime == "simples_nacional":
            if self.aliquota_efetiva is None:
                raise RegimeNaoCadastrado(self.cnpj, "RBT12 (para calcular a alíquota efetiva)")
            return float(self.aliquota_efetiva)
        t = self.tributos_sobre_servico or {}
        return round(sum(float(v) for v in t.values()), 6)

    def para_dict(self) -> dict:
        d = {
            "cnpj": self.cnpj, "razao_social": self.razao_social,
            "regime": self.regime, "anexo": self.anexo,
            "rbt12": self.rbt12, "aliquota_efetiva": self.aliquota_efetiva,
            "fonte": self.fonte, "atualizado_em": self.atualizado_em,
        }
        if self.tributos_sobre_servico:
            d["tributos_sobre_servico"] = self.tributos_sobre_servico
        try:
            d["carga_total"] = self.carga_total()
            d["carga_total_pct"] = f"{d['carga_total'] * 100:.2f}%"
        except RegimeNaoCadastrado as e:
            d["carga_total"] = None
            d["nao_da_para_precificar"] = str(e)
        if self.defasado and self.regime == "simples_nacional":
            d["aviso"] = (
                f"RBT12 atualizado em {self.atualizado_em or 'nunca'} — a alíquota do "
                f"Simples muda TODO MÊS com o faturamento. Confirme antes de fechar preço."
            )
        return d


def aliquota_efetiva(anexo: str, rbt12: float) -> float:
    """(RBT12 × alíquota nominal − parcela a deduzir) / RBT12, pela LC 123.

    Zero de faturamento não dá alíquota zero: a empresa nova paga a 1ª faixa. Dividir por
    zero aqui daria `inf` ou 0 dependendo da ordem, e as duas respostas estão erradas.
    """
    faixas = FAIXAS.get((anexo or "").upper().strip())
    if not faixas:
        raise RegimeNaoCadastrado("?", f"anexo do Simples válido (recebi {anexo!r})")
    if rbt12 is None:
        raise RegimeNaoCadastrado("?", "RBT12")
    if rbt12 > TETO_SIMPLES:
        raise RegimeNaoCadastrado(
            "?", f"enquadramento — RBT12 de {rbt12:,.2f} estourou o teto do Simples "
                 f"({TETO_SIMPLES:,.2f}). A empresa precisa de novo regime no cadastro")
    if rbt12 <= 0:
        return faixas[0][1]  # empresa nova: 1ª faixa, alíquota nominal
    for limite, nominal, deduzir in faixas:
        if rbt12 <= limite:
            return round((rbt12 * nominal - deduzir) / rbt12, 6)
    return faixas[-1][1]


async def resolver(db: AsyncSession, cnpj: str) -> Regime:
    """O regime desta empresa. RECUSA quando falta o que muda o preço."""
    so_digitos = "".join(c for c in str(cnpj or "") if c.isdigit())
    r = (await db.execute(text(
        "SELECT cnpj, razao_social, regime_tributario, anexo_simples, "
        "       rbt12::float AS rbt12, fonte_regime, regime_atualizado_em::text AS atualizado "
        "  FROM empresas "
        " WHERE regexp_replace(coalesce(cnpj,''),'[^0-9]','','g') = :c"),
        {"c": so_digitos})).mappings().first()
    if not r:
        raise RegimeNaoCadastrado(so_digitos, "a própria empresa no cadastro")
    regime = (r["regime_tributario"] or "").strip().lower()
    if not regime:
        raise RegimeNaoCadastrado(r["cnpj"], "regime_tributario em `empresas`")

    efetiva = None
    if regime == "simples_nacional":
        if r["rbt12"] is not None:
            efetiva = aliquota_efetiva(r["anexo_simples"], float(r["rbt12"]))
    tributos = None
    if regime in ("lucro_real", "lucro_presumido"):
        # os mesmos que já estavam em crm_pricing_params, agora AMARRADOS ao CNPJ
        p = dict((await db.execute(text(
            "SELECT chave, valor::float FROM crm_pricing_params "
            " WHERE chave IN ('pis','cofins','iss')"))).all())
        tributos = {"pis": p.get("pis", 0.0165), "cofins": p.get("cofins", 0.076),
                    "iss": p.get("iss", 0.05)}
    return Regime(
        cnpj=r["cnpj"], razao_social=r["razao_social"], regime=regime,
        anexo=r["anexo_simples"], rbt12=r["rbt12"], aliquota_efetiva=efetiva,
        fonte=r["fonte_regime"] or "cadastro `empresas` (sem fonte declarada)",
        atualizado_em=r["atualizado"], tributos_sobre_servico=tributos,
    )


async def listar(db: AsyncSession) -> list[dict]:
    """Todas as empresas do grupo, com o regime de cada uma."""
    cnpjs = (await db.execute(text(
        "SELECT cnpj FROM empresas ORDER BY razao_social"))).scalars().all()
    fora = []
    for c in cnpjs:
        try:
            fora.append((await resolver(db, c)).para_dict())
        except RegimeNaoCadastrado as e:
            fora.append({"cnpj": c, "regime": "NAO_CADASTRADO", "carga_total": None,
                         "nao_da_para_precificar": str(e),
                         "dica": "Cadastre `regime_tributario` (e `anexo_simples` + `rbt12` "
                                 "se for Simples) na tabela `empresas`."})
    return fora


def envelope_recusa(e: RegimeNaoCadastrado) -> dict:
    return {
        "ok": False, "codigo": "REGIME_NAO_CADASTRADO", "http": 422,
        "mensagem": str(e),
        "dica": ("Cadastre em `empresas`: `regime_tributario`, e para Simples também "
                 "`anexo_simples` e `rbt12` (faturamento dos últimos 12 meses). NÃO estimo "
                 "alíquota — imposto errado para menos é prejuízo que só aparece no "
                 "fechamento."),
        "cnpj": e.cnpj, "faltando": e.faltando,
    }
