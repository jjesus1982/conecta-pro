"""
DominioExporterAgent — Exportação para Domínio TOTVS
Gera arquivos no formato que o sistema Domínio/TOTVS aceita para importação pelo contador.
"""

import logging
from datetime import datetime
from decimal import Decimal

logger = logging.getLogger(__name__)


class DominioExporterAgent:
    """Exporta dados contábeis no formato Domínio TOTVS"""

    # Plano de Contas padrão para segurança patrimonial
    PLANO_CONTAS = {
        # RECEITAS
        "3.1.1.01": "Receita de Vigilância Patrimonial",
        "3.1.1.02": "Receita de Portaria Remota",
        "3.1.1.03": "Receita de Segurança Eletrônica",
        "3.1.1.04": "Receita de Portaria Humanizada",
        "3.1.2.01": "Deduções de Receita - ISS",
        "3.1.2.02": "Deduções de Receita - PIS",
        "3.1.2.03": "Deduções de Receita - COFINS",
        # CUSTOS
        "4.1.1.01": "Salários e Ordenados - Agentes de Portaria",
        "4.1.1.02": "Salários e Ordenados - Supervisores",
        "4.1.1.03": "Salários e Ordenados - Administrativo",
        "4.1.2.01": "INSS Patronal",
        "4.1.2.02": "FGTS",
        "4.1.2.03": "13º Salário",
        "4.1.2.04": "Férias",
        "4.1.3.01": "Uniformes e EPI",
        "4.1.3.02": "Equipamentos e Materiais",
        "4.1.4.01": "Terceiros - Vigilância Temporária",
        # DESPESAS
        "5.1.1.01": "Despesas Administrativas Gerais",
        "5.1.2.01": "Aluguel",
        "5.1.2.02": "Energia Elétrica",
        "5.1.2.03": "Telefone e Internet",
        "5.1.3.01": "Honorários Contábeis",
        "5.1.4.01": "IRPJ",
        "5.1.4.02": "CSLL",
        "5.1.4.03": "DAS - Simples Nacional",
        # ATIVO/PASSIVO simplificado
        "1.1.1.01": "Caixa",
        "1.1.1.02": "Bancos Conta Corrente",
        "1.1.2.01": "Clientes - Duplicatas a Receber",
        "2.1.1.01": "Fornecedores",
        "2.1.2.01": "Obrigações Trabalhistas",
        "2.1.3.01": "Obrigações Tributárias",
    }

    def exportar_lancamentos(
        self,
        empresa_slug: str,
        periodo: str,  # "YYYY-MM"
        lancamentos: list[dict],
    ) -> dict:
        """
        Gera arquivo de lançamentos no formato Domínio TOTVS (layout TXT padrão).
        Retorna conteúdo do arquivo e metadados.
        """
        try:
            ano, mes = periodo.split("-")
            linhas = []

            # Cabeçalho do arquivo
            linhas.append(self._gerar_cabecalho(empresa_slug, periodo))

            total_debitos = Decimal("0")
            total_creditos = Decimal("0")

            for lanc in lancamentos:
                linha = self._formatar_lancamento(lanc)
                linhas.append(linha)
                valor = Decimal(str(lanc.get("valor", 0)))
                if lanc.get("tipo") == "D":
                    total_debitos += valor
                else:
                    total_creditos += valor

            # Rodapé
            linhas.append(self._gerar_rodape(total_debitos, total_creditos, len(lancamentos)))

            conteudo = "\r\n".join(linhas)

            return {
                "sucesso": True,
                "empresa": empresa_slug,
                "periodo": periodo,
                "total_lancamentos": len(lancamentos),
                "total_debitos": float(total_debitos),
                "total_creditos": float(total_creditos),
                "balanceado": abs(total_debitos - total_creditos) < Decimal("0.01"),
                "nome_arquivo": f"LANCAMENTOS_{empresa_slug.upper()}_{ano}{mes}.TXT",
                "conteudo": conteudo,
                "formato": "DOMINIO_TOTVS_V12",
            }
        except Exception as e:
            logger.error(f"Erro ao exportar lançamentos: {e}")
            return {"sucesso": False, "erro": str(e)}

    def exportar_clientes(self, empresa_slug: str, clientes: list[dict]) -> dict:
        """Exporta cadastro de clientes no formato Domínio TOTVS"""
        try:
            linhas = []
            linhas.append("TIPO|CODIGO|NOME|CNPJ_CPF|IE|MUNICIPIO|UF|CEP|ENDERECO|TELEFONE|EMAIL")

            for i, cliente in enumerate(clientes, 1):
                codigo = str(cliente.get("id", i)).zfill(6)
                nome = self._sanitizar(cliente.get("nome", ""), 60)
                cnpj = self._formatar_cnpj(cliente.get("cnpj", ""))
                municipio = self._sanitizar(cliente.get("municipio", "MANAUS"), 40)
                uf = cliente.get("uf", "AM")
                cep = self._formatar_cep(cliente.get("cep", ""))
                endereco = self._sanitizar(cliente.get("endereco", ""), 60)
                telefone = self._formatar_telefone(cliente.get("telefone", ""))
                email = cliente.get("email", "")[:60]

                linha = f"CLI|{codigo}|{nome}|{cnpj}||{municipio}|{uf}|{cep}|{endereco}|{telefone}|{email}"
                linhas.append(linha)

            conteudo = "\r\n".join(linhas)
            return {
                "sucesso": True,
                "empresa": empresa_slug,
                "total_clientes": len(clientes),
                "nome_arquivo": f"CLIENTES_{empresa_slug.upper()}.TXT",
                "conteudo": conteudo,
                "formato": "DOMINIO_TOTVS_CLIENTES_V12",
            }
        except Exception as e:
            logger.error(f"Erro ao exportar clientes: {e}")
            return {"sucesso": False, "erro": str(e)}

    def exportar_nfse_para_dominio(
        self,
        empresa_slug: str,
        periodo: str,
        notas: list[dict],
    ) -> dict:
        """
        Exporta NFS-e emitidas no formato que o Domínio TOTVS importa como receitas.
        Gera lançamentos contábeis automáticos para cada nota.
        """
        try:
            lancamentos_gerados = []

            for nota in notas:
                valor_bruto = Decimal(str(nota.get("valor_servico", 0)))
                iss = Decimal(str(nota.get("iss", 0)))
                pis = Decimal(str(nota.get("pis", 0)))
                cofins = Decimal(str(nota.get("cofins", 0)))

                # D — Clientes / C — Receita de Serviço
                lancamentos_gerados.append(
                    {
                        "data": nota.get("data_emissao", datetime.now().strftime("%d/%m/%Y")),
                        "historico": f"NFS-e {nota.get('numero', '')} - {nota.get('tomador', '')}",
                        "conta_debito": "1.1.2.01",
                        "conta_credito": self._conta_receita_por_servico(nota.get("tipo_servico", "")),
                        "valor": float(valor_bruto),
                        "tipo": "D",
                        "complemento": nota.get("numero", ""),
                    }
                )

                # Dedução ISS
                if iss > 0:
                    lancamentos_gerados.append(
                        {
                            "data": nota.get("data_emissao", datetime.now().strftime("%d/%m/%Y")),
                            "historico": f"ISS NFS-e {nota.get('numero', '')}",
                            "conta_debito": "3.1.2.01",
                            "conta_credito": "2.1.3.01",
                            "valor": float(iss),
                            "tipo": "D",
                        }
                    )

                # Dedução PIS/COFINS (Lucro Real)
                if pis > 0:
                    lancamentos_gerados.append(
                        {
                            "data": nota.get("data_emissao", datetime.now().strftime("%d/%m/%Y")),
                            "historico": f"PIS NFS-e {nota.get('numero', '')}",
                            "conta_debito": "3.1.2.02",
                            "conta_credito": "2.1.3.01",
                            "valor": float(pis),
                            "tipo": "D",
                        }
                    )

                if cofins > 0:
                    lancamentos_gerados.append(
                        {
                            "data": nota.get("data_emissao", datetime.now().strftime("%d/%m/%Y")),
                            "historico": f"COFINS NFS-e {nota.get('numero', '')}",
                            "conta_debito": "3.1.2.03",
                            "conta_credito": "2.1.3.01",
                            "valor": float(cofins),
                            "tipo": "D",
                        }
                    )

            return self.exportar_lancamentos(empresa_slug, periodo, lancamentos_gerados)
        except Exception as e:
            logger.error(f"Erro ao exportar NFS-e para Domínio: {e}")
            return {"sucesso": False, "erro": str(e)}

    def gerar_plano_contas(self, empresa_slug: str) -> dict:
        """Exporta plano de contas no formato Domínio TOTVS"""
        linhas = ["CODIGO|DESCRICAO|TIPO|NATUREZA|NIVEL|REDUZIDA"]
        for codigo, descricao in self.PLANO_CONTAS.items():
            partes = codigo.split(".")
            nivel = len(partes)
            natureza = "D" if codigo.startswith("1") or codigo.startswith("4") or codigo.startswith("5") else "C"
            tipo = "A"  # Analítica
            reduzida = codigo.replace(".", "")[-4:]
            linhas.append(f"{codigo}|{descricao}|{tipo}|{natureza}|{nivel}|{reduzida}")

        conteudo = "\r\n".join(linhas)
        return {
            "sucesso": True,
            "empresa": empresa_slug,
            "total_contas": len(self.PLANO_CONTAS),
            "nome_arquivo": f"PLANO_CONTAS_{empresa_slug.upper()}.TXT",
            "conteudo": conteudo,
            "formato": "DOMINIO_TOTVS_PLANO_CONTAS_V12",
        }

    def _gerar_cabecalho(self, empresa: str, periodo: str) -> str:
        ano, mes = periodo.split("-")
        return (
            f"CAB|DOMINIO|V12|{empresa.upper()}|{mes}/{ano}|{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}|CONECTAPRO"
        )

    def _gerar_rodape(self, debitos: Decimal, creditos: Decimal, total: int) -> str:
        return f"ROD|{total}|{float(debitos):.2f}|{float(creditos):.2f}"

    def _formatar_lancamento(self, lanc: dict) -> str:
        data = lanc.get("data", "")
        historico = self._sanitizar(lanc.get("historico", ""), 50)
        conta_d = lanc.get("conta_debito", "")
        conta_c = lanc.get("conta_credito", "")
        valor = f"{float(lanc.get('valor', 0)):.2f}"
        complemento = lanc.get("complemento", "")
        return f"LAN|{data}|{historico}|{conta_d}|{conta_c}|{valor}|{complemento}"

    def _conta_receita_por_servico(self, tipo_servico: str) -> str:
        mapa = {
            "vigilancia": "3.1.1.01",
            "portaria_remota": "3.1.1.02",
            "eletronica": "3.1.1.03",
            "portaria_humanizada": "3.1.1.04",
        }
        return mapa.get(tipo_servico, "3.1.1.01")

    def _sanitizar(self, texto: str, max_len: int) -> str:
        return (texto or "").replace("|", " ").replace("\n", " ")[:max_len]

    def _formatar_cnpj(self, cnpj: str) -> str:
        digits = "".join(filter(str.isdigit, cnpj or ""))
        if len(digits) == 14:
            return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
        return cnpj

    def _formatar_cep(self, cep: str) -> str:
        digits = "".join(filter(str.isdigit, cep or ""))
        if len(digits) == 8:
            return f"{digits[:5]}-{digits[5:]}"
        return cep

    def _formatar_telefone(self, tel: str) -> str:
        digits = "".join(filter(str.isdigit, tel or ""))
        if len(digits) == 11:
            return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
        if len(digits) == 10:
            return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
        return tel
