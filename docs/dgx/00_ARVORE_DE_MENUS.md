# DGX (Digiexpress) — árvore completa de menus

**Lida do DOM em 24/09/2026**, logado como `master` na empresa CONECTAMAIS PATRIMONIAL,
em https://conectamais.dgxbrasil.com.br/. Contrato de 30 dias para mapear a arquitetura
por dentro e trazer para o Conecta PRO.

11 módulos · ~150 telas. Rotas relativas ao domínio. `frontend/` e `view/` indicam telas
mais novas (SPA); `/X/Index` é o padrão MVC antigo (lista) — quase sempre com `/X/Create`
e `/X/Edit/{id}` ao lado.

## Apontamentos (ponto)
- Ausências → `/Ausencias/Index` · Dashboard de Ausências → `/frontend/DashboardAusencias/Index` · Faltas por Período → `/EntregasBeneficios/RelatorioFaltasPorPeriodo`
- Banco de Horas → `/frontend/CalcularBancoHoras/Index`
- Carga Colaboradores → `/CargaDispositivos/Index`
- Cartão de Ponto → `/CartaoPonto/Index`
- Configurações de Ponto → `/frontend/configuracoesponto`
- Controle de Pontos → `/ControlePonto/Index` · Novo Controle Ponto → `/View/controlePonto`
- Diário de Ocorrências → `/ControlePonto/Ocorrencias`
- Escalas: Feriados → `/view/feriados` · Modelos → `/ModelosEscalas/Index` · Turnos → `/Escalas/Index`
- Fechamentos → `/Apontamentos/Index`
- Integração de Batimentos → `/view/integracaoBatimentos`
- Localizações → `/Jornadas/Index`
- Relógios Ponto → `/RelogioPonto/Index`

## Comercial
- Clientes: Clientes → `/Clientes/Index` · Fontes Pagadoras → `/FontesPagadoras/Index` · Postos → `/PessoaPostos/Index`
- Contratos → `/Contratos/Index`
- Regiões → `/view/regioes`

## Configurações
- Acessos Temporários → `/view/acessosTemporarios` · Configurações → `/Configuracoes/Index`
- Departamentos de Usuários → `/view/usuarioDepartamentos` · Empresa → `/Empresas/Index`
- Log Sistema → `/LogSistema/Index` · Usuários → `/Usuarios/Index`

## Demandas
- Assuntos → `/AssuntosOcorrencias/Index` · Atendimentos → `/Atendimentos/Index` · CRM → `/Visitas/Index`
- Demandas → `/OcorrenciasAssuntoFixo/Index` · Diretórios → `/DiretoriosCliente/Index` · Feedbacks → `/Feedback/Index`

## DP/RH  ⭐ foco
- Afastamentos: Afastamentos → `/AgenteAfastamentos/Index` · Tipos de Afastamento → `/TiposAfastamento/Index`
- Benefícios: Alelo Pagamentos → `/TipoBeneficioLayouts/SolicitacaoCartao` · Entregas → `/EntregasBeneficios/Index` · Linhas de VT → `/OperadoraItinerarios/Index` · Reajustes → `/BeneficiosReajuste/Index` · Tipos de Benefícios → `/TiposBeneficios/Index`
- Benefícios Individuais → `/EmpregadoBeneficios/Index`
- Cargos → `/Cargos/Index` · Funções → `/Funcoes/Index`
- Colaboradores: Colaboradores → `/Colaboradores/Index` · Dashboard Turnover → `/frontend/DashboardAtivos/Index` · Dependentes → `/AgenteDependentes/Index` · Falhas de Importação → `/view/falhasImportacaoEmpregados` · Fotos → `/frontend/empregadofotos`
- Crachás em Lote → `/ColaboradorCracha/index`
- Cursos e Certificados: Cursos → `/AgenteCursos/Index` · Tipos → `/CursosCertificados/Index`
- Demissão em Lote → `/view/demissaolote/`
- Eventos → `/Eventos/Index` · Eventos Coletivos → `/frontend/EventosColetivos/Index`
- Férias → `/Ferias/Index`
- Medidas Disciplinares: Advertências → `/AgenteAdvertencias/Index` · Suspensões → `/EmpregadosSuspensoes/Index`
- Sindicatos → `/Sindicatos/Index` · Novo Sindicato → `/View/Sindicatos`
- Vales → `/frontend/vales`

## Faturamento
- Cobrança → `/frontend/Cobranca/index` · Dashboard → `/DashboardEvolucaoFaturamento/Index` · Faturas → `/Faturas/Index`
- Fechamento de Comissões → `/frontend/ComissoesFechamento/index` · Natureza da Operação (CFOP) → `/CFOP/Index`
- Notas Serviço → `/NotasServico/Index` · Recibos de Venda → `/PessoaRecibos/Index` · Tipos de Serviço → `/Servicos/Index`

## Financeiro
- Centros de Custo → `/CentrosCusto/Index` · Condições de Pagamento → `/CondicoesPagamento/Index` · Formas de Pagamento → `/FormasPagamento/Index`
- Contas: Análise Orçamentária → `/View/AnaliseOrcamentaria` · Conciliação → `/view/conciliacaoBancaria` · Contas a Pagar → `/ContasPagar/Index` · Contas a Receber → `/ContasReceber/Index` · Contas Bancárias → `/ContasBancarias/Index` · Contas Fixas → `/Frontend/ContasFixas` · Fluxo de Caixa → `/View/FluxoCaixa/Calendario` · Plano de Contas → `/PlanoContas/Index` · Transferências → `/TransferenciasBancarias/Index`
- Dashboard Financeiro → `/frontend/DashboardFinanceiro/Index`
- Relatórios: Centros de Custo · Contas a Pagar · Contas a Receber · Fluxo de Caixa · Plano de Contas

## Frotas
- APP Frotas: Abastecimentos · Auditorias · Checklist · Grupo de Frotas · Grupo Vistoria Checklist · Itens das Auditorias · Itens de Vistoria · Localidades · Relatório de Abastecimentos · Requisições Abastecimento · Requisições de Lavagem · Solicitações de Auditorias · Solicitações de Manutenções · Usuários Frotas
- Controle de Saída · Locações · Manutenções · Multas de Trânsito · Troca de Correia · Trocas de Óleo · Trocas de Pneu · Veículos
- Relatórios Frotas: Abastecimentos · Manutenções · Trocas de Óleo · Trocas de Pneu

## Operacional
- APP Q-Watcher: Chamados → `/SetorChamados/Index` · Dashboard Checklist · Dashboard Supervisão → `/Dashboard/Index` · Mapa por Período · Mapa Supervisão · Mapa Supervisores · Setores/Equipamentos → `/ContratoSetores/Index` · Usuários
- APP Vigilância: Alertas → `/RondaAlertas/Index` · Locais → `/RondaLojas/Index` · Mapa · Modelos → `/ModelosRondas/Index` · Usuários
- Avisos → `/Avisos/PainelAvisos` · Coberturas → `/frontend/coberturas/index` · Dashboard Chamados · Departamentos
- Grid Planejamento → `/GridPlanejamento/Index` · Livro de Ocorrências → `/frontend/livroocorrencias` · Movimentações → `/Movimentacoes/Index` · Postos → `/Postos/Index`

## SESMT
- ASO → `/SaudeOcupacional/Index` · Médicos → `/Medicos/Index` · Tipos de Exames → `/Exames/Index`

## Suprimentos
- Compras: Notas Fiscais de Entrada · Pedidos de Compras · Solicitações de Compras
- Equipamentos: Armamentos · Coletes · Comunicações Móveis · Rastreadores
- Fornecedores · Grupos Materiais/Uniformes
- Materiais: Cadastro · Estoque · Solicitação
- Uniformes/EPI: Cadastro · Entrega · Estoque · Kit
