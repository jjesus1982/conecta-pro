"""EFD Contribuições (SPED PIS/COFINS) — montagem do arquivo.

Por que existe
--------------
Quem entrega a EFD Contribuições hoje é a Portte Contábil, e o Jordan quer rescindir com
ela. `checar_obrigacao_sem_gerador.py` contava essa obrigação como **sem gerador no
sistema** — no dia da rescisão ela vira exposição legal com data marcada, mensal.

O que travava não era o código: era **não saber o regime**. Escriturar PIS/COFINS
chutando entre cumulativo e não-cumulativo produz arquivo legal errado com aparência de
certo. Tentei medir por três caminhos e nenhum respondia: a NFS-e de Manaus não devolve
PIS/COFINS (a tabela só tem ISS), os DARF do extrato vêm como «PAGAMENTO DARF NUMERADO»
sem o código da receita, e `retem_pis_cofins` fala da retenção do tomador, não do regime
do prestador.

**Jordan respondeu em 26/09/2026: cumulativo.** E a resposta é coerente com a lei — o
serviço de vigilância e transporte de valores está no art. 10 da Lei 10.833/2003, entre as
atividades que PERMANECEM no regime cumulativo mesmo com a pessoa jurídica no Lucro Real.

O que isso fixa, e por que fica declarado aqui em vez de espalhado
------------------------------------------------------------------
No cumulativo não há crédito a descontar, e as alíquotas são as básicas da Lei 9.718:

    PIS/PASEP   0,65%          COFINS   3,00%
    CST das operações tributadas:  01
    Código de contribuição apurada (Tabela 4.3.5):  51 — regime cumulativo, alíquota básica
    Registro 0110: COD_INC_TRIB = 2 (exclusivamente cumulativo)

Nenhum desses números é escolha deste arquivo: são o que o regime determina. Ficam em
constantes com o nome do que são, para que trocar de regime seja trocar UM lugar — e não
caçar alíquota espalhada por trinta linhas, que é a fábrica de defeito desta casa.

O que ele NÃO faz
-----------------
Não transmite, não assina e não decide o regime: recebe o regime de quem chama e RECUSA
montar se vier outro que ele não saiba escriturar. Não monta bloco C (mercadorias) nem
bloco F (demais receitas) com dados — eles saem abertos e vazios, que é o que o leiaute
pede quando não há movimento, e é honesto: a empresa vende serviço.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

logger = logging.getLogger(__name__)

#: Leiaute vigente da EFD Contribuições.
VERSAO_LEIAUTE = "006"

#: Alíquotas do regime CUMULATIVO (Lei 9.718/1998). Não são escolha: são o regime.
ALIQ_PIS_CUMULATIVO = Decimal("0.65")
ALIQ_COFINS_CUMULATIVO = Decimal("3.00")

#: CST de operação tributável a alíquota básica (Tabela 4.3.3/4.3.4).
CST_TRIBUTADA = "01"

#: Código da contribuição apurada, Tabela 4.3.5 — 51 é «regime cumulativo, alíquota
#: básica». O 01 parecido é o NÃO-cumulativo, e trocar um pelo outro passa despercebido.
COD_CONT_CUMULATIVO = "51"

#: Registro 0110, campo COD_INC_TRIB. 1 = só não-cumulativo · 2 = só cumulativo · 3 = ambos.
COD_INC_TRIB_CUMULATIVO = "2"

#: Registro 0110, campo IND_REG_CUM. 1 = regime de caixa · 2 = competência consolidada
#: (F550) · 9 = competência com escrituração DETALHADA. Aqui é 9: cada NFS-e entra no
#: bloco A com o seu documento, que é o que dá rastro nota a nota.
IND_REG_CUM_DETALHADO = "9"

#: IND_MOV dos blocos: 0 = com dados · 1 = sem dados. Bloco sem dados ainda ABRE e FECHA.
BLOCO_COM_DADOS = "0"
BLOCO_SEM_DADOS = "1"

#: Blocos que esta empresa não movimenta, e por quê. Saem abertos e vazios de propósito:
#: omiti-los invalida o arquivo, e preenchê-los com zero fabricaria operação.
BLOCOS_VAZIOS: tuple[tuple[str, str], ...] = (
    ("C", "mercadorias — a empresa vende serviço"),
    ("D", "transporte e comunicação — não é a atividade"),
    ("F", "demais operações — toda a receita está documentada em NFS-e, no bloco A"),
    ("I", "operações de instituição financeira — não se aplica"),
    ("P", "contribuição previdenciária sobre a receita bruta — não se aplica"),
    ("1", "complemento da escrituração — sem ocorrências"),
)


class RegimeNaoEscrituravelError(Exception):
    """O regime pedido não é um que este montador saiba escriturar."""


def _d(v) -> Decimal:
    """Decimal com 2 casas, arredondando como o fisco espera."""
    return Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _n(v) -> str:
    """Número no formato do SPED: vírgula decimal, sem separador de milhar."""
    return f"{_d(v):.2f}".replace(".", ",")


def _dt(d: date | None) -> str:
    return d.strftime("%d%m%Y") if d else ""


def _so_digitos(v: str | None) -> str:
    return "".join(c for c in (v or "") if c.isdigit())


@dataclass
class Tomador:
    """Participante do bloco 0150 — quem recebeu o serviço."""

    codigo: str
    nome: str
    cnpj_cpf: str
    codigo_municipio: str = ""
    inscricao_municipal: str = ""


@dataclass
class ServicoPrestado:
    """Uma NFS-e emitida. É a linha A100 mais o seu item A170."""

    numero: str
    serie: str
    chave: str
    data_emissao: date
    tomador_codigo: str
    valor_servico: Decimal
    valor_iss: Decimal = Decimal("0")
    codigo_servico: str = ""
    descricao: str = ""
    data_execucao: date | None = None
    #: situação do documento (Tabela 4.1.2): 00 = regular, 02 = cancelado
    situacao: str = "00"

    @property
    def cancelado(self) -> bool:
        return self.situacao != "00"


@dataclass
class Contabilista:
    nome: str = ""
    cpf: str = ""
    crc: str = ""
    email: str = ""
    codigo_municipio: str = ""

    @property
    def declarado(self) -> bool:
        return bool(self.nome and self.cpf and self.crc)


@dataclass
class SPEDContribuicoesManager:
    """Monta a EFD Contribuições de UM estabelecimento, num período, no CUMULATIVO."""

    cnpj: str
    razao_social: str
    uf: str
    codigo_municipio: str
    inscricao_municipal: str = ""
    inscricao_estadual: str = ""
    regime: str = "cumulativo"
    contabilista: Contabilista = field(default_factory=Contabilista)
    #: 0 = original, 1 = retificadora
    tipo_escrituracao: str = "0"
    #: Tabela do 0000, IND_NAT_PJ: 00 = sociedade empresária geral
    natureza_pj: str = "00"
    #: IND_ATIV: 0 = industrial/equiparado · 1 = prestador de serviços · 2 = outros
    indicador_atividade: str = "1"

    tomadores: dict[str, Tomador] = field(default_factory=dict)
    servicos: list[ServicoPrestado] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cnpj = _so_digitos(self.cnpj)
        if (self.regime or "").strip().lower() not in ("cumulativo", "cumulative"):
            raise RegimeNaoEscrituravelError(
                f"regime «{self.regime}» — este montador só escritura o CUMULATIVO. "
                "O não-cumulativo exige bloco de créditos (A100/A170 com NAT_BC_CRED, "
                "M100/M500) que não está escrito, e montar sem eles produziria um arquivo "
                "que o validador aceita e o fisco cobra."
            )

    # ── entrada de dados ──────────────────────────────────────────────────────────────
    def adicionar_tomador(self, t: Tomador) -> None:
        self.tomadores[t.codigo] = t

    def adicionar_servico(self, s: ServicoPrestado) -> None:
        self.servicos.append(s)

    # ── o que se apura ────────────────────────────────────────────────────────────────
    @property
    def receita_tributavel(self) -> Decimal:
        """Base de cálculo: soma dos serviços NÃO cancelados.

        A nota cancelada entra no arquivo (com COD_SIT 02, porque o número foi usado) e
        **não** entra na base. Somar cancelada é recolher sobre faturamento que não houve.
        """
        return _d(sum(s.valor_servico for s in self.servicos if not s.cancelado))

    @property
    def pis_apurado(self) -> Decimal:
        return _d(self.receita_tributavel * ALIQ_PIS_CUMULATIVO / 100)

    @property
    def cofins_apurado(self) -> Decimal:
        return _d(self.receita_tributavel * ALIQ_COFINS_CUMULATIVO / 100)

    # ── montagem ──────────────────────────────────────────────────────────────────────
    def gerar_arquivo(self, inicio: date, fim: date) -> str:
        contador: dict[str, int] = {}
        linhas: list[str] = []
        linhas += self._bloco_0(inicio, fim, contador)
        linhas += self._bloco_a(contador)
        for bloco, _motivo in BLOCOS_VAZIOS:
            linhas += self._bloco_vazio(bloco, contador)
        linhas += self._bloco_m(contador)
        linhas += self._bloco_9(contador)
        logger.info(
            "EFD Contribuições %s %s a %s: %d registros, base R$ %s, PIS R$ %s, COFINS R$ %s",
            self.cnpj, inicio, fim, len(linhas),
            self.receita_tributavel, self.pis_apurado, self.cofins_apurado,
        )
        return "\r\n".join(linhas)

    def _pipe(self, campos: list[str], contador: dict) -> str:
        contador[campos[0]] = contador.get(campos[0], 0) + 1
        return "|" + "|".join(campos) + "|"

    def _bloco_0(self, inicio: date, fim: date, c: dict) -> list[str]:
        ln = [
            self._pipe(
                ["0000", VERSAO_LEIAUTE, self.tipo_escrituracao, "", "",
                 _dt(inicio), _dt(fim), self.razao_social, self.cnpj, self.uf,
                 self.codigo_municipio, "", self.natureza_pj, self.indicador_atividade], c
            ),
            self._pipe(["0001", BLOCO_COM_DADOS], c),
        ]
        if self.contabilista.declarado:
            ln.append(self._pipe(
                ["0100", self.contabilista.nome, _so_digitos(self.contabilista.cpf),
                 self.contabilista.crc, "", "", "", "", "", "", "", "",
                 self.contabilista.email,
                 self.contabilista.codigo_municipio or self.codigo_municipio], c))
        # 0110 — o registro que DECLARA o regime. É o campo que decide o arquivo inteiro.
        ln.append(self._pipe(
            ["0110", COD_INC_TRIB_CUMULATIVO, "", "", IND_REG_CUM_DETALHADO], c))
        ln.append(self._pipe(
            ["0140", self.cnpj[:8] or "0001", self.razao_social, self.cnpj, self.uf,
             self.inscricao_estadual, self.codigo_municipio, self.inscricao_municipal, ""], c))
        for t in self.tomadores.values():
            doc = _so_digitos(t.cnpj_cpf)
            ln.append(self._pipe(
                ["0150", t.codigo, t.nome, "01058",
                 doc if len(doc) == 14 else "", doc if len(doc) == 11 else "",
                 "", t.codigo_municipio or self.codigo_municipio, "", "", "", "", ""], c))
        ln.append(self._pipe(["0990", str(sum(v for k, v in c.items() if k.startswith("0")) + 1)], c))
        return ln

    def _bloco_a(self, c: dict) -> list[str]:
        """Bloco A — serviços. Cada NFS-e é um A100 com um A170."""
        if not self.servicos:
            return self._bloco_vazio("A", c)
        antes = sum(v for k, v in c.items() if k.startswith("A"))
        ln = [self._pipe(["A001", BLOCO_COM_DADOS], c), self._pipe(["A010", self.cnpj], c)]
        for s in self.servicos:
            base = Decimal("0") if s.cancelado else _d(s.valor_servico)
            pis = _d(base * ALIQ_PIS_CUMULATIVO / 100)
            cof = _d(base * ALIQ_COFINS_CUMULATIVO / 100)
            ln.append(self._pipe(
                ["A100",
                 "1",                       # IND_OPER: 1 = serviço prestado
                 "0",                       # IND_EMIT: 0 = emissão própria
                 s.tomador_codigo, s.situacao, s.serie, "", s.numero, s.chave,
                 _dt(s.data_emissao), _dt(s.data_execucao or s.data_emissao),
                 _n(s.valor_servico), "0", "0,00",
                 _n(base), _n(pis), _n(base), _n(cof),
                 "0,00", "0,00", _n(s.valor_iss)], c))
            ln.append(self._pipe(
                ["A170", "1", s.codigo_servico or "SERVICO",
                 (s.descricao or "")[:255], _n(s.valor_servico), "0,00",
                 "", "",                    # NAT_BC_CRED / IND_ORIG_CRED: só no não-cumulativo
                 CST_TRIBUTADA, _n(base), _n(ALIQ_PIS_CUMULATIVO), _n(pis),
                 CST_TRIBUTADA, _n(base), _n(ALIQ_COFINS_CUMULATIVO), _n(cof),
                 "", ""], c))
        depois = sum(v for k, v in c.items() if k.startswith("A"))
        ln.append(self._pipe(["A990", str(depois - antes + 1)], c))
        return ln

    def _bloco_vazio(self, bloco: str, c: dict) -> list[str]:
        return [
            self._pipe([f"{bloco}001", BLOCO_SEM_DADOS], c),
            self._pipe([f"{bloco}990" if bloco != "1" else "1990", "2"], c),
        ]

    def _bloco_m(self, c: dict) -> list[str]:
        """Bloco M — a apuração. No cumulativo, os campos não-cumulativos vão zerados."""
        antes = sum(v for k, v in c.items() if k.startswith("M"))
        base, pis, cof = self.receita_tributavel, self.pis_apurado, self.cofins_apurado
        z = "0,00"
        ln = [self._pipe(["M001", BLOCO_COM_DADOS if base else BLOCO_SEM_DADOS], c)]
        if base:
            ln.append(self._pipe(
                ["M200", z, z, z, z, z, z, z, _n(pis), z, z, _n(pis), _n(pis)], c))
            ln.append(self._pipe(
                ["M210", COD_CONT_CUMULATIVO, _n(base), _n(base),
                 _n(ALIQ_PIS_CUMULATIVO), "", "", _n(pis), z, z, z, z, _n(pis)], c))
            ln.append(self._pipe(
                ["M600", z, z, z, z, z, z, z, _n(cof), z, z, _n(cof), _n(cof)], c))
            ln.append(self._pipe(
                ["M610", COD_CONT_CUMULATIVO, _n(base), _n(base),
                 _n(ALIQ_COFINS_CUMULATIVO), "", "", _n(cof), z, z, z, z, _n(cof)], c))
        depois = sum(v for k, v in c.items() if k.startswith("M"))
        ln.append(self._pipe(["M990", str(depois - antes + 1)], c))
        return ln

    def _bloco_9(self, c: dict) -> list[str]:
        """Bloco 9 — o inventário do próprio arquivo. Ele CONTA A SI MESMO.

        Cada 9900 é um registro, e o 9900 do 9900 existe. Esquecer isso é o erro clássico
        do bloco 9, e o validador do fisco recusa o arquivo inteiro por causa dele.
        """
        ln = [self._pipe(["9001", BLOCO_COM_DADOS], c)]
        # fotografia ANTES de contar os 9900 — senão o dicionário muda durante o laço
        tipos = sorted(c.items())
        n_9900 = len(tipos) + 3  # + 9900, 9990 e 9999, que também têm a sua linha
        for reg, qtd in tipos:
            ln.append(self._pipe(["9900", reg, str(qtd)], c))
        ln.append(self._pipe(["9900", "9900", str(n_9900)], c))
        ln.append(self._pipe(["9900", "9990", "1"], c))
        ln.append(self._pipe(["9900", "9999", "1"], c))
        ln.append(self._pipe(["9990", str(sum(v for k, v in c.items() if k.startswith("9")) + 1)], c))
        total = sum(c.values()) + 1
        ln.append("|" + "|".join(["9999", str(total)]) + "|")
        return ln
