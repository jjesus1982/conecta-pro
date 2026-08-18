"""
ObligationsMonitorAgent — Monitor de Obrigações Multi-Empresa
Fase 7 do Mega Prompt

Cada empresa tem obrigações diferentes conforme seu regime:

CONECTA ELETRÔNICA (Lucro Real):
- Mensal: EFD ICMS/IPI, EFD Contribuições, DCTF (até dia 15)
- Trimestral: IRPJ/CSLL (DARF até último dia útil do mês seguinte)
- Anual: ECD (até junho), ECF (até julho), DIRF (fevereiro)

CONECTA PATRIMONIAL (Simples Nacional):
- Mensal: PGDAS-D (até dia 20), DAS (vencimento do DAS)
- Anual: DEFIS (março), DASN (se ME)
- Dispensada: EFD, ECD, ECF, DCTF
"""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

logger = logging.getLogger(__name__)


@dataclass
class ObrigacaoCalendario:
    empresa_slug: str
    empresa_nome: str
    tipo: str
    descricao: str
    periodo_referencia: str  # "MM/YYYY"
    data_vencimento: date
    status: str  # pendente, em_andamento, concluida, atrasada
    regime: str
    valor_estimado: float | None = None
    urgencia: str = "normal"  # critica, alta, normal, baixa
    link_sistema: str | None = None


@dataclass
class CalendarioGrupo:
    mes: int
    ano: int
    total_obrigacoes: int
    criticas: int  # vencem em até 5 dias
    atrasadas: int
    pendentes: int
    concluidas: int
    por_empresa: dict[str, list[ObrigacaoCalendario]] = field(default_factory=dict)
    consolidado: list[ObrigacaoCalendario] = field(default_factory=list)


class ObligationsMonitorAgent:
    """
    Monitor de obrigações fiscais/contábeis multi-empresa.
    Gera calendário consolidado do grupo.

    ⚠️ **ESTE É UM SEGUNDO CALENDÁRIO, e ele é um MOLDE — não lê o banco.**

    As listas abaixo derivam o calendário do REGIME, por constante. Ele não consulta
    `fiscal_obligations`, então **não sabe** valor devido, número de recibo nem se a obrigação
    já foi cumprida: tudo que venceu aparece como "atrasada", mesmo pago. Quem tem o dado real
    é `fiscal_contabil/obrigacoes/calendario_service.py`, que deriva o dia da competência mais
    recente da própria empresa.

    Isto importa porque é ESTE agente que alimenta as rotas `/obrigacoes/calendario/*` e a
    consulta `calendario_obrigacoes` do chat — ou seja, é este o calendário que o Jordan vê.

    ⭐ **FGTS: dia 20, não 7.** Medido em 18/08/2026 — com o dia 7 cravado aqui, o painel
    dizia "FGTS venceu 07/08, ATRASADA" num dia 18 em que o vencimento real ainda estava dois
    dias à frente. O FGTS Digital recolhe no dia **20** (a guia da Portte diz "pagar até
    20/08/2026"), e a mesma correção já tinha sido feita no `calendario_service` — mas não
    alcançava aqui, porque são dois calendários. Alarme falso ensina a ignorar o painel.

    A unificação (este agente passar a ler `fiscal_obligations`) fica pendente e é o conserto
    de verdade; corrigir constante é remendo enquanto houver duas fontes para a mesma data.
    """

    OBRIGACOES_LUCRO_REAL = [
        # (tipo, descricao, dia_vencimento, frequencia, link)
        ("EFD_ICMS_IPI", "SPED EFD ICMS/IPI", 15, "mensal", "https://www.sped.fazenda.gov.br/"),
        ("EFD_CONTRIBUICOES", "SPED EFD Contribuições (PIS/COFINS)", 10, "mensal", "https://www.sped.fazenda.gov.br/"),
        (
            "DCTF",
            "DCTF — Declaração de Débitos e Créditos Tributários Federais",
            15,
            "mensal",
            "https://www.gov.br/receitafederal/",
        ),
        ("IRPJ_CSLL_ESTIMATIVA", "IRPJ/CSLL — Estimativa Mensal (DARF)", 30, "mensal", None),
        ("FGTS_GUIA", "FGTS — FGTS Digital (DAE)", 20, "mensal", "https://www.gov.br/fgtsdigital/"),  # dia 20, NÃO 7 — ver nota abaixo
        ("INSS_GPS", "INSS/GPS — Contribuição Previdenciária", 20, "mensal", None),
        ("ISS_AVULSO", "ISS — Imposto Sobre Serviços (Manaus)", 10, "mensal", "https://semef.manaus.am.gov.br/"),
    ]

    OBRIGACOES_LUCRO_REAL_ANUAIS = [
        ("DIRF", "DIRF — Declaração do IR Retido na Fonte", 2, 28, "anual"),
        ("ECD", "SPED ECD — Escrituração Contábil Digital", 6, 30, "anual"),
        ("ECF", "SPED ECF — Escrituração Contábil Fiscal", 7, 31, "anual"),
        ("RAIS", "RAIS — Relação Anual de Informações Sociais", 3, 31, "anual"),
    ]

    OBRIGACOES_SIMPLES = [
        (
            "PGDAS_D",
            "PGDAS-D — Programa Gerador do Documento de Arrecadação",
            20,
            "mensal",
            "https://www8.receita.fazenda.gov.br/SimplesNacional/",
        ),
        (
            "DAS",
            "DAS — Documento de Arrecadação do Simples Nacional",
            20,
            "mensal",
            "https://www8.receita.fazenda.gov.br/SimplesNacional/",
        ),
        ("FGTS_GUIA", "FGTS — FGTS Digital (DAE)", 20, "mensal", "https://www.gov.br/fgtsdigital/"),  # dia 20, NÃO 7 — ver nota abaixo
        ("ISS_AVULSO", "ISS — Imposto Sobre Serviços (Manaus)", 10, "mensal", "https://semef.manaus.am.gov.br/"),
    ]

    OBRIGACOES_SIMPLES_ANUAIS = [
        ("DEFIS", "DEFIS — Declaração de Informações Socioeconômicas e Fiscais", 3, 31, "anual"),
        ("RAIS", "RAIS — Relação Anual de Informações Sociais", 3, 31, "anual"),
    ]

    def _ultimo_dia_util(self, ano: int, mes: int) -> date:
        """Retorna o último dia útil do mês (simplificado: último dia não fim de semana)."""
        ultimo = date(ano, mes, calendar.monthrange(ano, mes)[1])
        while ultimo.weekday() >= 5:  # 5=sábado, 6=domingo
            ultimo -= timedelta(days=1)
        return ultimo

    def _vencimento(self, ano: int, mes: int, dia: int) -> date:
        """Calcula data de vencimento, ajustando para dia útil se necessário."""
        try:
            d = date(ano, mes, min(dia, calendar.monthrange(ano, mes)[1]))
        except ValueError:
            d = date(ano, mes, calendar.monthrange(ano, mes)[1])
        # Mover para próxima segunda se cair em fim de semana
        while d.weekday() >= 5:
            d += timedelta(days=1)
        return d

    def _urgencia(self, vencimento: date, hoje: date) -> str:
        delta = (vencimento - hoje).days
        if delta < 0:
            return "atrasada"
        if delta <= 5:
            return "critica"
        if delta <= 15:
            return "alta"
        return "normal"

    def gerar_calendario_empresa(
        self,
        empresa_slug: str,
        empresa_nome: str,
        regime: str,
        mes: int,
        ano: int,
        hoje: date | None = None,
    ) -> list[ObrigacaoCalendario]:
        """Gera calendário de obrigações de uma empresa para o mês/ano."""
        hoje = hoje or date.today()
        obrigacoes = []
        periodo = f"{mes:02d}/{ano}"

        if regime == "lucro_real":
            for tipo, desc, dia, _freq, link in self.OBRIGACOES_LUCRO_REAL:
                venc = self._vencimento(ano, mes, dia)
                status = "atrasada" if venc < hoje else "pendente"
                obrigacoes.append(
                    ObrigacaoCalendario(
                        empresa_slug=empresa_slug,
                        empresa_nome=empresa_nome,
                        tipo=tipo,
                        descricao=desc,
                        periodo_referencia=periodo,
                        data_vencimento=venc,
                        status=status,
                        regime=regime,
                        urgencia=self._urgencia(venc, hoje),
                        link_sistema=link,
                    )
                )
            # Anuais no mês correspondente
            for tipo, desc, mes_venc, dia_venc, _ in self.OBRIGACOES_LUCRO_REAL_ANUAIS:
                if mes_venc == mes:
                    venc = self._vencimento(ano, mes_venc, dia_venc)
                    status = "atrasada" if venc < hoje else "pendente"
                    obrigacoes.append(
                        ObrigacaoCalendario(
                            empresa_slug=empresa_slug,
                            empresa_nome=empresa_nome,
                            tipo=tipo,
                            descricao=desc,
                            periodo_referencia=f"Exercício {ano}",
                            data_vencimento=venc,
                            status=status,
                            regime=regime,
                            urgencia=self._urgencia(venc, hoje),
                        )
                    )
        else:  # simples_nacional
            for tipo, desc, dia, _freq, link in self.OBRIGACOES_SIMPLES:
                venc = self._vencimento(ano, mes, dia)
                status = "atrasada" if venc < hoje else "pendente"
                obrigacoes.append(
                    ObrigacaoCalendario(
                        empresa_slug=empresa_slug,
                        empresa_nome=empresa_nome,
                        tipo=tipo,
                        descricao=desc,
                        periodo_referencia=periodo,
                        data_vencimento=venc,
                        status=status,
                        regime=regime,
                        urgencia=self._urgencia(venc, hoje),
                        link_sistema=link,
                    )
                )
            for tipo, desc, mes_venc, dia_venc, _ in self.OBRIGACOES_SIMPLES_ANUAIS:
                if mes_venc == mes:
                    venc = self._vencimento(ano, mes_venc, dia_venc)
                    status = "atrasada" if venc < hoje else "pendente"
                    obrigacoes.append(
                        ObrigacaoCalendario(
                            empresa_slug=empresa_slug,
                            empresa_nome=empresa_nome,
                            tipo=tipo,
                            descricao=desc,
                            periodo_referencia=f"Exercício {ano}",
                            data_vencimento=venc,
                            status=status,
                            regime=regime,
                            urgencia=self._urgencia(venc, hoje),
                        )
                    )

        return sorted(obrigacoes, key=lambda o: o.data_vencimento)

    def gerar_calendario_grupo(self, mes: int, ano: int, hoje: date | None = None) -> CalendarioGrupo:
        """Gera calendário consolidado de TODAS as empresas do grupo."""
        hoje = hoje or date.today()

        empresas = [
            ("conecta_eletronica", "Conecta Mais Eletrônica", "lucro_real"),
            ("conecta_patrimonial", "Conecta Mais Patrimonial", "simples_nacional"),
        ]

        por_empresa: dict[str, list[ObrigacaoCalendario]] = {}
        consolidado: list[ObrigacaoCalendario] = []

        for slug, nome, regime in empresas:
            obs = self.gerar_calendario_empresa(slug, nome, regime, mes, ano, hoje)
            por_empresa[slug] = obs
            consolidado.extend(obs)

        consolidado.sort(key=lambda o: o.data_vencimento)

        criticas = sum(1 for o in consolidado if o.urgencia == "critica")
        atrasadas = sum(1 for o in consolidado if o.status == "atrasada")
        pendentes = sum(1 for o in consolidado if o.status == "pendente")
        concluidas = sum(1 for o in consolidado if o.status == "concluida")

        return CalendarioGrupo(
            mes=mes,
            ano=ano,
            total_obrigacoes=len(consolidado),
            criticas=criticas,
            atrasadas=atrasadas,
            pendentes=pendentes,
            concluidas=concluidas,
            por_empresa=por_empresa,
            consolidado=consolidado,
        )

    def alertar_vencimentos(self, dias_antecedencia: int = 10) -> list[dict]:
        """Retorna obrigações próximas de vencer de todas as empresas."""
        hoje = date.today()
        cal = self.gerar_calendario_grupo(hoje.month, hoje.year, hoje)
        alertas = []
        for ob in cal.consolidado:
            delta = (ob.data_vencimento - hoje).days
            if -5 <= delta <= dias_antecedencia:
                alertas.append(
                    {
                        "empresa": ob.empresa_nome,
                        "empresa_slug": ob.empresa_slug,
                        "tipo": ob.tipo,
                        "descricao": ob.descricao,
                        "vencimento": ob.data_vencimento.isoformat(),
                        "dias_restantes": delta,
                        "urgencia": ob.urgencia,
                        "status": ob.status,
                        "link": ob.link_sistema,
                    }
                )
        return sorted(alertas, key=lambda a: a["dias_restantes"])

    def obrigacoes_dispensadas_simples(self) -> list[str]:
        """Lista obrigações das quais Simples Nacional é dispensado."""
        return [
            "EFD ICMS/IPI",
            "EFD Contribuições",
            "DCTF",
            "ECD — Escrituração Contábil Digital",
            "ECF — Escrituração Contábil Fiscal",
            "CSLL mensal",
        ]
