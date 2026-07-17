"""
ContractMigratorAgent — Migração de Contratos entre Empresas
Fase 3 do Mega Prompt Multi-Empresa

Fluxo de migração:
1. Analisar contrato (tipo de serviço → empresa destino)
2. Simular impacto tributário
3. Migrar com histórico completo
4. Gerar aditivo contratual
5. Notificar cliente
6. Registrar para auditoria
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

logger = logging.getLogger(__name__)

# Mapeamento de tipo de serviço → empresa
SERVICOS_HUMANIZADOS = [
    "vigilancia",
    "vigilancia_patrimonial",
    "portaria_presencial",
    "portaria_24h",
    "portaria_12x36",
    "limpeza",
    "limpeza_conservacao",
    "jardinagem",
    "facilities",
    "recepcao",
    "zeladoria",
    "manutencao_predial",
]

SERVICOS_ELETRONICOS = [
    "portaria_remota",
    "monitoramento",
    "monitoramento_24h",
    "cftv",
    "alarmes",
    "controle_acesso",
    "automacao",
    "seguranca_eletronica",
]


@dataclass
class AnaliseContrato:
    contrato_id: int
    tipo_servico: str
    empresa_atual_slug: str
    empresa_destino_slug: str
    deve_migrar: bool
    motivo: str
    # Impacto tributário
    imposto_atual_mes: float
    imposto_destino_mes: float
    economia_mensal: float
    economia_anual: float
    # Pendências
    pendencias: list[str] = field(default_factory=list)
    pode_migrar_imediatamente: bool = True


@dataclass
class ResultadoMigracao:
    contrato_id: int
    empresa_origem_slug: str
    empresa_destino_slug: str
    data_migracao: date
    sucesso: bool
    mensagem: str
    aditivo_gerado: bool = False
    notificacao_enviada: bool = False
    historico_id: str | None = None


@dataclass
class SimulacaoMigracao:
    contrato_id: int
    empresa_destino_slug: str
    receita_bruta_mes: float
    # Impostos
    impostos_origem_mes: float
    impostos_destino_mes: float
    economia_impostos_mes: float
    economia_impostos_anual: float
    # Margem
    margem_origem: float
    margem_destino: float
    ganho_margem: float
    # Decisão
    vale_migrar: bool
    recomendacao: str
    liminares_aplicadas: list[str] = field(default_factory=list)


class ContractMigratorAgent:
    """
    Agente de IA para migração de contratos entre empresas do grupo.

    Regras de negócio:
    - Serviços HUMANIZADOS → conecta_patrimonial (Simples Nacional)
    - Serviços ELETRÔNICOS → conecta_eletronica (Lucro Real → Simples)

    Liminares Patrimonial (quando concedidas):
    - pis_cofins_zero: PIS/COFINS = 0 nas NFS-e
    - inss_nao_retido: INSS não retido na fonte
    """

    def classificar_servico(self, tipo_servico: str) -> dict:
        """Classifica o tipo de serviço e retorna empresa destino."""
        ts = tipo_servico.lower().strip()
        if any(s in ts for s in SERVICOS_HUMANIZADOS):
            return {
                "categoria": "humanizado",
                "empresa_destino": "conecta_patrimonial",
                "regime_destino": "simples_nacional",
                "motivo": f"Serviço '{tipo_servico}' é humanizado → Conecta Mais Patrimonial (Simples Nacional Anexo III)",
            }
        if any(s in ts for s in SERVICOS_ELETRONICOS):
            return {
                "categoria": "eletronico",
                "empresa_destino": "conecta_eletronica",
                "regime_destino": "lucro_real",
                "motivo": f"Serviço '{tipo_servico}' é eletrônico → Conecta Mais Eletrônica",
            }
        return {
            "categoria": "indefinido",
            "empresa_destino": "conecta_eletronica",
            "regime_destino": "lucro_real",
            "motivo": f"Tipo '{tipo_servico}' não mapeado — mantendo na Eletrônica por padrão",
        }

    def analisar_contrato(
        self,
        contrato_id: int,
        tipo_servico: str,
        empresa_atual_slug: str,
        receita_bruta_mes: float,
        custo_direto_mes: float = 0.0,
        rbt12_destino: float = 600000.0,
        liminares_patrimonial: list[str] | None = None,
    ) -> AnaliseContrato:
        """
        Analisa se contrato deve ser migrado e para qual empresa.
        Calcula impacto tributário da migração.
        """
        from modules.financial.agents.tax_calculator import TaxCalculatorAgent

        tax = TaxCalculatorAgent()
        liminares = liminares_patrimonial or []

        classificacao = self.classificar_servico(tipo_servico)
        empresa_destino = classificacao["empresa_destino"]
        deve_migrar = empresa_destino != empresa_atual_slug

        # Calcular impostos na empresa atual
        if empresa_atual_slug == "conecta_eletronica":
            calc_atual = tax.calcular_lucro_real(
                receita_mes=Decimal(str(receita_bruta_mes)),
                receita_trimestre=Decimal(str(receita_bruta_mes * 3)),
            )
            imposto_atual = float(calc_atual.total_impostos_mes)
        else:
            calc_atual = tax.calcular_simples(
                receita_mes=Decimal(str(receita_bruta_mes)),
                rbt12=Decimal(str(rbt12_destino)),
                liminares=liminares,
            )
            imposto_atual = float(calc_atual.valor_das)

        # Calcular impostos na empresa destino
        if empresa_destino == "conecta_eletronica":
            calc_dest = tax.calcular_lucro_real(
                receita_mes=Decimal(str(receita_bruta_mes)),
                receita_trimestre=Decimal(str(receita_bruta_mes * 3)),
            )
            imposto_destino = float(calc_dest.total_impostos_mes)
        else:
            calc_dest = tax.calcular_simples(
                receita_mes=Decimal(str(receita_bruta_mes)),
                rbt12=Decimal(str(rbt12_destino)),
                liminares=liminares,
            )
            imposto_destino = float(calc_dest.valor_das)

        economia_mes = imposto_atual - imposto_destino

        pendencias = []
        if empresa_destino == "conecta_patrimonial":
            pendencias.append("⚠️ Conecta Patrimonial está em abertura — aguardar CNPJ")
            pendencias.append("📋 Gerar aditivo contratual informando novo CNPJ faturador")
            if "pis_cofins_zero" not in liminares:
                pendencias.append("⚖️ Liminar PIS/COFINS ainda não concedida")
            if "inss_nao_retido" not in liminares:
                pendencias.append("⚖️ Liminar INSS ainda não concedida")

        return AnaliseContrato(
            contrato_id=contrato_id,
            tipo_servico=tipo_servico,
            empresa_atual_slug=empresa_atual_slug,
            empresa_destino_slug=empresa_destino,
            deve_migrar=deve_migrar,
            motivo=classificacao["motivo"],
            imposto_atual_mes=imposto_atual,
            imposto_destino_mes=imposto_destino,
            economia_mensal=round(economia_mes, 2),
            economia_anual=round(economia_mes * 12, 2),
            pendencias=pendencias,
            pode_migrar_imediatamente=len([p for p in pendencias if "abertura" in p]) == 0,
        )

    def simular_migracao(
        self,
        contrato_id: int,
        tipo_servico: str,
        empresa_atual_slug: str,
        empresa_destino_slug: str,
        receita_bruta_mes: float,
        custo_direto_mes: float,
        custo_indireto_mes: float = 0.0,
        rbt12: float = 600000.0,
        liminares: list[str] | None = None,
    ) -> SimulacaoMigracao:
        """Simula impacto completo da migração antes de executar."""
        from modules.financial.agents.profitability_analyzer import ProfitabilityAnalyzerAgent

        analyzer = ProfitabilityAnalyzerAgent()
        liminares = liminares or []

        regime_origem = "lucro_real" if empresa_atual_slug == "conecta_eletronica" else "simples_nacional"
        regime_destino = "lucro_real" if empresa_destino_slug == "conecta_eletronica" else "simples_nacional"
        lim_origem = [] if empresa_atual_slug == "conecta_eletronica" else liminares
        lim_destino = [] if empresa_destino_slug == "conecta_eletronica" else liminares

        rent_origem = analyzer.calcular_rentabilidade(
            receita_bruta_mes=Decimal(str(receita_bruta_mes)),
            custo_direto_mes=Decimal(str(custo_direto_mes)),
            custo_indireto_mes=Decimal(str(custo_indireto_mes)),
            tipo_servico=tipo_servico,
            empresa_slug=empresa_atual_slug,
            regime=regime_origem,
            rbt12=Decimal(str(rbt12)),
            liminares=lim_origem,
        )

        rent_destino = analyzer.calcular_rentabilidade(
            receita_bruta_mes=Decimal(str(receita_bruta_mes)),
            custo_direto_mes=Decimal(str(custo_direto_mes)),
            custo_indireto_mes=Decimal(str(custo_indireto_mes)),
            tipo_servico=tipo_servico,
            empresa_slug=empresa_destino_slug,
            regime=regime_destino,
            rbt12=Decimal(str(rbt12)),
            liminares=lim_destino,
        )

        economia_mes = float(rent_destino.lucro_liquido_mes - rent_origem.lucro_liquido_mes)
        vale_migrar = economia_mes > 0

        recomendacao = (
            f"✅ Migrar para {empresa_destino_slug}: ganho de R$ {economia_mes:,.2f}/mês "
            f"(margem {float(rent_origem.margem_liquida_percentual):.1f}% → {float(rent_destino.margem_liquida_percentual):.1f}%)"
            if vale_migrar
            else f"❌ Não migrar: {empresa_atual_slug} é mais vantajoso neste cenário"
        )

        return SimulacaoMigracao(
            contrato_id=contrato_id,
            empresa_destino_slug=empresa_destino_slug,
            receita_bruta_mes=receita_bruta_mes,
            impostos_origem_mes=float(rent_origem.impostos_mes),
            impostos_destino_mes=float(rent_destino.impostos_mes),
            economia_impostos_mes=float(rent_origem.impostos_mes - rent_destino.impostos_mes),
            economia_impostos_anual=float((rent_origem.impostos_mes - rent_destino.impostos_mes) * 12),
            margem_origem=float(rent_origem.margem_liquida_percentual),
            margem_destino=float(rent_destino.margem_liquida_percentual),
            ganho_margem=float(rent_destino.margem_liquida_percentual - rent_origem.margem_liquida_percentual),
            vale_migrar=vale_migrar,
            recomendacao=recomendacao,
            liminares_aplicadas=lim_destino,
        )

    async def migrar_contrato(
        self,
        contrato_id: int | str,
        empresa_origem_slug: str,
        empresa_destino_slug: str,
        data_migracao: date | None = None,
        gerar_aditivo: bool = True,
        db=None,
        usuario_id: str | None = None,
    ) -> ResultadoMigracao:
        """
        Executa a migração do contrato de verdade (contracts.empresa_id) e grava
        o aditivo de transferência como ContractAddendum (trilha de auditoria).

        `contrato_id` é o UUID de contracts.id. Sem `db`, mantém o comportamento
        legado (só log) para compatibilidade.
        """
        data_migracao = data_migracao or date.today()

        if db is None:
            logger.info(
                "Migração (modo legado, sem persistência): contrato=%s %s->%s",
                contrato_id, empresa_origem_slug, empresa_destino_slug,
            )
            return ResultadoMigracao(
                contrato_id=contrato_id,
                empresa_origem_slug=empresa_origem_slug,
                empresa_destino_slug=empresa_destino_slug,
                data_migracao=data_migracao,
                sucesso=True,
                mensagem=f"Contrato {contrato_id}: migração simulada (sem sessão de banco)",
                aditivo_gerado=False,
            )

        from sqlalchemy import text

        from modules.empresas.services.empresa_lookup import get_empresa, invalidate_cache

        origem = await get_empresa(db, slug=empresa_origem_slug)
        destino = await get_empresa(db, slug=empresa_destino_slug)

        row = (await db.execute(
            text("SELECT id, contract_number, name, empresa_id FROM contracts WHERE id = :cid"),
            {"cid": str(contrato_id)},
        )).fetchone()
        if not row:
            return ResultadoMigracao(
                contrato_id=contrato_id,
                empresa_origem_slug=empresa_origem_slug,
                empresa_destino_slug=empresa_destino_slug,
                data_migracao=data_migracao,
                sucesso=False,
                mensagem=f"Contrato {contrato_id} não encontrado",
            )
        if row.empresa_id and str(row.empresa_id) != str(origem["id"]):
            return ResultadoMigracao(
                contrato_id=contrato_id,
                empresa_origem_slug=empresa_origem_slug,
                empresa_destino_slug=empresa_destino_slug,
                data_migracao=data_migracao,
                sucesso=False,
                mensagem=(
                    f"Contrato {row.contract_number} não pertence a {empresa_origem_slug} "
                    "(empresa atual divergente — conferir antes de migrar)"
                ),
            )

        await db.execute(
            text("UPDATE contracts SET empresa_id = :dest, updated_at = NOW() WHERE id = :cid"),
            {"dest": str(destino["id"]), "cid": str(row.id)},
        )

        historico_id: str | None = None
        if gerar_aditivo:
            texto = self.gerar_texto_aditivo(
                contrato_id=row.contract_number or str(row.id),
                empresa_origem=empresa_origem_slug,
                empresa_destino=empresa_destino_slug,
                cnpj_destino=destino.get("cnpj"),
                data_vigencia=data_migracao,
                razao_origem=origem.get("razao_social"),
                cnpj_origem=origem.get("cnpj"),
                razao_destino=destino.get("razao_social"),
                nome_contrato=row.name,
            )
            addendum = (await db.execute(
                text(
                    "INSERT INTO contract_addendums "
                    "(id, contract_id, addendum_number, addendum_type, effective_date, "
                    " description, reason, signed, is_active, created_by, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :cid, :num, 'other', :eff, :descr, :reason, "
                    " false, true, :uid, NOW(), NOW()) RETURNING id"
                ),
                {
                    "cid": str(row.id),
                    "num": f"TRANSF-{row.contract_number}-{data_migracao.strftime('%y%m%d')}"[:30],
                    "eff": data_migracao,
                    "descr": texto,
                    "reason": (
                        "Transferência de titularidade — segmentação do Grupo Conecta Mais "
                        "(Nota de Comunicação de 19/05/2026; arts. 421/422 CC)"
                    ),
                    "uid": str(usuario_id) if usuario_id else None,
                },
            )).fetchone()
            historico_id = str(addendum.id) if addendum else None

        await db.commit()
        invalidate_cache()

        logger.info(
            "Migração PERSISTIDA: contrato=%s (%s) %s->%s aditivo=%s por=%s",
            row.contract_number, row.id, empresa_origem_slug, empresa_destino_slug,
            historico_id, usuario_id,
        )

        return ResultadoMigracao(
            contrato_id=str(row.id),
            empresa_origem_slug=empresa_origem_slug,
            empresa_destino_slug=empresa_destino_slug,
            data_migracao=data_migracao,
            sucesso=True,
            mensagem=(
                f"Contrato {row.contract_number} migrado de {empresa_origem_slug} "
                f"para {empresa_destino_slug} em {data_migracao.isoformat()}"
            ),
            aditivo_gerado=historico_id is not None,
            notificacao_enviada=False,
            historico_id=historico_id,
        )

    def gerar_texto_aditivo(
        self,
        contrato_id: int | str,
        empresa_origem: str,
        empresa_destino: str,
        cnpj_destino: str | None = None,
        data_vigencia: date | None = None,
        razao_origem: str | None = None,
        cnpj_origem: str | None = None,
        razao_destino: str | None = None,
        nome_contrato: str | None = None,
    ) -> str:
        """Gera texto do aditivo de transferência.

        Qualificação legal usa a RAZÃO SOCIAL oficial da Receita (regra do PRD:
        razão exata em campos legais; nome de exibição fica para o restante).
        """
        data_vigencia = data_vigencia or date.today()
        cedente = razao_origem or empresa_origem.replace("_", " ").title()
        cessionaria = razao_destino or empresa_destino.replace("_", " ").title()
        cnpj_cedente = cnpj_origem or "-"
        cnpj_cessionaria = cnpj_destino or "(CNPJ em processo de abertura)"
        objeto = f" ({nome_contrato})" if nome_contrato else ""

        return f"""ADITIVO DE TRANSFERÊNCIA DE TITULARIDADE CONTRATUAL

Contrato nº: {contrato_id}{objeto}
Data de vigência: {data_vigencia.strftime("%d/%m/%Y")}

Considerando a reorganização societária do Grupo Conecta Mais, comunicada por
meio da Nota de Comunicação de 19/05/2026, e com fundamento nos princípios da
autonomia privada e da liberdade contratual (arts. 421 e 422 do Código Civil),
as partes estabelecem:

1. O presente contrato, até então de titularidade de {cedente}
   (CNPJ {cnpj_cedente}), passa à titularidade de {cessionaria}
   (CNPJ {cnpj_cessionaria}), a partir de {data_vigencia.strftime("%d/%m/%Y")}.

2. Todas as condições comerciais, valores, prazos, garantias e obrigações
   permanecem integralmente inalterados, sem qualquer descontinuidade na
   execução dos serviços.

3. O faturamento (emissão de NFS-e) e a cobrança passarão a ser realizados
   pela CESSIONÁRIA a partir da data de vigência deste aditivo.

4. Este aditivo é parte integrante do contrato original, ao qual se vincula
   para todos os fins legais.

As partes concordam com os termos acima.

Manaus, {data_vigencia.strftime("%d/%m/%Y")}

_______________________________     _______________________________
CONTRATANTE                         {cedente}
                                    (CEDENTE)

                                    _______________________________
                                    {cessionaria}
                                    (CESSIONÁRIA)
"""

    def analisar_lote_por_tipo(
        self,
        contratos: list[dict],
        empresa_atual_slug: str = "conecta_eletronica",
        liminares_patrimonial: list[str] | None = None,
    ) -> dict:
        """
        Analisa uma lista de contratos e separa humanizados vs eletrônicos.

        contratos: lista de dicts com {contrato_id, tipo_servico, receita_mes}
        """
        liminares = liminares_patrimonial or []
        humanizados = []
        eletronicos = []
        indefinidos = []
        total_economia_anual = 0.0

        for c in contratos:
            analise = self.analisar_contrato(
                contrato_id=c.get("contrato_id", 0),
                tipo_servico=c.get("tipo_servico", ""),
                empresa_atual_slug=empresa_atual_slug,
                receita_bruta_mes=c.get("receita_mes", 0),
                liminares_patrimonial=liminares,
            )
            if analise.empresa_destino_slug == "conecta_patrimonial":
                humanizados.append(analise)
            elif analise.empresa_destino_slug == "conecta_eletronica":
                eletronicos.append(analise)
            else:
                indefinidos.append(analise)
            total_economia_anual += analise.economia_anual

        return {
            "total_contratos": len(contratos),
            "humanizados": len(humanizados),
            "eletronicos": len(eletronicos),
            "indefinidos": len(indefinidos),
            "economia_anual_total": round(total_economia_anual, 2),
            "detalhes_humanizados": [
                {
                    "contrato_id": a.contrato_id,
                    "tipo": a.tipo_servico,
                    "destino": a.empresa_destino_slug,
                    "economia_anual": a.economia_anual,
                    "pendencias": a.pendencias,
                }
                for a in humanizados
            ],
            "detalhes_eletronicos": [
                {
                    "contrato_id": a.contrato_id,
                    "tipo": a.tipo_servico,
                    "destino": a.empresa_destino_slug,
                }
                for a in eletronicos
            ],
        }
