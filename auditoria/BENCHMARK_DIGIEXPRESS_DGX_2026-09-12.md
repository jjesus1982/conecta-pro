# DigiExpress / DGX — o que copiar, e por quê (12/09/2026)

**Origem:** proposta nº 665_2026 e apresentação de 73 páginas enviadas pelo Jordan em 12/09/2026
(`uploads/jordan_20260912/`), mais pesquisa no site, no LinkedIn e nas lojas de aplicativos.
**Pedido do dono:** *"os processos deles aliados à nossa tecnologia vai destravar o Conecta PRO de
uma vez por todas"* · *"precisamos pegar tudo de bom que eles têm, tudo"*.

**Leitura do dono, e ela está certa:** onde as duas coisas se sobrepõem, o deles é mais maduro,
mais fluido e **funciona**. O nosso é melhor de projeto e não funciona em várias frentes.
Maturidade ganha de arquitetura quando o cliente está esperando.

---

## 1. Quem é a empresa — a calibração que muda a conclusão

| | |
|---|---|
| Fundada | 1996 (30 anos) |
| Sede | Rua Emma Gobbi Soncini 109, Jd. Bom Clima, **Guarulhos/SP** |
| Funcionários | **11 a 50** (LinkedIn) |
| Seguidores LinkedIn | 51 |
| Arquitetura | SOA desde 2005 |
| Clientes nomeados no site | **68** |
| Apps publicados | **9** (Android; 4 também em iOS) |
| Preço para a Conecta Mais | R$ 1.700/mês + R$ 300/mês cloud, adesão isenta, validade 5 dias |
| Telefones | (11) 2788-3040 · comercial (11) 91152-4355 · suporte (11) 91598-3092 |
| Atendimento | seg–qui 8h30–17h30, sex até 16h30 |

**A vantagem deles não é tamanho nem dinheiro.** É uma equipe menor que a nossa lista de módulos,
rodando 30 anos no MESMO nicho, com os mesmos clientes reclamando. O que eles têm e não se compra
é o **catálogo de casos**. O que se pode copiar é exatamente isso — porque está visível nas telas.

**Escala real, medida nas lojas:**

| App | Versão | Última release | Instalações | Nota |
|---|---|---|---|---|
| Controle de Acesso | 2.66.0 | 11/01/2026 | **10.000+** | 4,1 (52) |
| Cronos (ponto facial) | **3.76.1** | **08/07/2026** | 1.000+ | 4,4 (19) |
| Q-Watcher | 7.91.4 | 09/12/2025 | 1.000+ | 3,7 (25) |
| Escoltas | 2.86.1 | — | — | — |

Cadência do Cronos em 2026: 15/04 → 21/05 → 15/06 → 08/07. **Mensal.**

⚠️ Nota de release do Cronos 3.61.9, e é a coisa mais importante desta pesquisa para o nosso ponto:
**"reconhecimento facial offline automático em caso de instabilidade na conexão online"** +
"otimização do número de chamadas à API". É o defeito que nos custou a semana (`nao_detectou`,
tela travada) — eles já resolveram e publicaram.

**Multi-tenant por subdomínio:** os screenshots do deck vêm de bases REAIS de clientes —
`betalimp.dgxbrasil.com.br`, `s.digiexpressapp.com.br`, `VALESECURITY.COM.BR`, `Macor SP`
(o arquivo do Alelo), `Comando G8` (base do faturamento de escolta), `Beta Serviços`,
`Unity Serviços`, `FMT Brasil`, `Bimbo do Brasil`, `TJ Campinas`.

---

## 2. Inventário completo do produto

### 2.1 DGX — ERP (4 linhas)
| Produto | O que é |
|---|---|
| **Patrimonial** | contrato + SLA para segurança patrimonial e limpeza |
| **Escolta** | da solicitação ao boletim de medição; inclui Escala, Cartão de Ponto e Benefícios |
| **Gerenciadora de Escolta** | produto do OUTRO lado: para quem CONTRATA escolta. Módulos Frete, Operação de Embarque e Obsoletos |
| **Pronta Resposta** | furto/roubo de veículo com rastreador: ocorrência, localização, dashboard |

### 2.2 DGX — Facilities (6 módulos)
Controle de Acesso e Monitoramento de Presença (picos de acesso, tempo de carga/descarga) ·
**Escolta Online** (portal do CLIENTE pedir escolta, confirmação automática por e-mail) ·
Gestão de Demanda (com arquivo virtual de documentos por contratada) ·
**Gestão de Limpeza Pública com IA** (cidadão manda foto por hashtag em rede social, filtro por IA) ·
**Gestão de Multa** (leitura automática DETRAN + pagamento + recurso judicial) ·
Mapa de Ponto.

### 2.3 DGX — Aplicativos (9)
- **Controle de Acesso** em TRÊS versões produtizadas:
  - *Empresarial*: facial, cálculo de adicional noturno e HE, Portaria 671
  - *Residencial*: RE, selfie, HE, **cerca geográfica** ← é o nosso caso de condomínio
  - *Eventos*: QR code, inserção de colete, entradas/saídas
- **Cronos** — ponto facial, online e offline
- **Q-Watcher** — supervisão + manutenção por QR: rotinas, checklists, chamados, indicadores, **controle de resíduos**
- **Rondas (Vigilância)** — vistoria por QR com câmera, **salva offline sem internet**
- **Frotas** — checklist, QR, manutenção preditiva, abastecimento, multas
- **Escolta** — folha operacional, sincronização automática
- **Cronograma de Visita** — grid de datas, relatórios filtráveis, **integração CRM**, lembrete automático
- **Gestão de Leiturista** — leitura/medição/inspeção para concessionárias
- **Avaliação (Totem e Tablet)** — feedback do cliente

---

## 3. Os PROCESSOS — o que as telas ensinam, campo por campo

Esta é a parte que vale. Não é a lista de features: é o detalhe que só aparece depois de anos.

### 3.1 Operação — postos e cobertura
- **Mapa de Ponto** codificado por cor, com cinco estados: `OK` · `atendido com atraso` ·
  **`atendido - posto incorreto`** · **`atendido - fora de escala`** · **`descoberto`**.
  Integra relógio biométrico + app Controle de Acesso + Cronos na MESMA tela.
- **Grid de Planejamento**: matriz cliente × dia do mês com `real/contratual` — `0/1`, `5/6`,
  `18/19`, `74/76`, `21/26` — pintada quando falta gente. Ao lado, painel de CNH vencendo e de
  **crachás vencidos**.
- **Diário de Ocorrência**: grade com Chapa, Setor (empresa+contrato), Função, Escala,
  Entrada1/Saída1/Entrada2/Saída2, Folga, Justificativa, **Responsável** — "corrija seus
  batimentos em tempo real". É a mesa de correção, não um relatório.
- **Movimentações**: Motivo (alocação de vaga · a pedido do supervisor · demissão · treinamento),
  **Função Origem→Destino**, **Turno Origem→Destino**, Contrato Origem→Efetivo, **Reserva Técnica**.
  Com dashboard por mês, motivo e turno de destino.
- **Dashboard de Ausências** cortado por gênero, período (diurno/noturno), **posto coberto sim/não**,
  evento (atestado médico, folga, licença paternidade, falta, atestado de acompanhamento,
  licença nojo, atestado de comparecimento, apresentação à justiça), posto, função,
  **dia da semana** e **supervisor**.

### 3.2 Comercial — precificação de contrato de mão de obra
Ficha de contrato com: `Cálculo` (POR HORA / POR MONTANTE), Segmento, Supervisor, Abreviação,
Início/Término/Inativação, R$ Materiais, Compl Materiais, **Taxa Admin %**, **PLR Sindicato %**,
Código Empresa, **Total Calculado vs Total Faturado**, Período de Faturamento (Mensal/Manual),
Centro de Custo, **☑ Ignorar alerta de posto descoberto**, **☑ Reserva Técnica**.

Nove modos de cálculo: Montante · Hora · Valor Fechado (postos/horas mês/total) · Horas Mensais ·
Horas Diárias · Horas Noturnas (com Vlr Hora Noturna separado) · Dias Fixos · **Dias Fixos 5x2** ·
**Dias Fixos 6x1** · **Dias Fixos Sábados, Domingos e Feriados (SDF)**.

### 3.3 Benefícios — o módulo mais sofisticado do sistema
Tela de cálculo por colaborador, e as colunas são a regra:
`Planejado (ant) · Trabalhado (ant) · Recebido (ant) · Direito (ant) · Saldo Anterior · Previsão ·
+ Ponto · − Ponto · Crédito/Débito · Qtde · Unitário · Total`
— com o **Mapa de Frequência dia a dia DENTRO do cálculo** e a "Frequência da Entrega Anterior".

- **Cálculo integrado ao ponto considerando horas mínimas para recebimento, créditos e débitos.**
- **Gera o arquivo do operador**: `ALELO_020420241428_4_MacorSP.txt`, com Gerado Por / Data /
  Total / nº Colaboradores / Pagamento.
- Catálogo com **linha de ônibus real**: operadora, código, cidade, UF (CMT-RMSP/BOM-CRÉDITO 8,55;
  VT EM ESPÉCIE 14,00; GUARULHOS MUNICIPAL 5,50; CONSÓRCIO 123 SJC 5,20; RÁPIDO LUXO JUNDIAÍ).
- Benefícios individuais com Modo Pagamento (Dinheiro/Cartão), Inclusão e **Cancelamento**:
  planos de saúde, seguro, medicina do trabalho, integração ônibus+CPTM+metrô.
- **Reajuste com REPASSE**: aprovação com `R$ Contrato / R$ Unitário / R$ Repasse` por contratante
  e função, com Ano Vigência e nº Beneficiários. **O aumento do VR chega ao preço do cliente.**
- Reajuste de CESTA BÁSICA, VR ADM, VR DOBRA, VR ESCOLTA, VR PATRIMONIAL, VR SERVIÇOS. E **PLR**.

### 3.4 DP/RH
- Colaborador: RE, **Nome de Guerra**, RG, CPF, CNH, **CNV** (Carteira Nacional de Vigilante).
  Contadores de status: Ativo · Inativo · Afastado · Demitido · **Falecido** · Férias · Suspenso · Ausente.
- **Cursos/reciclagem** com `Reciclável = SIM` e `Validade = 2 anos`, por pessoa, com local,
  conclusão e vencimento: FORMAÇÃO · RECICLAGEM ESCOLTA ARMADA · RECICLAGEM PATRIMONIAL ·
  RECICLAGEM VSPP. (Exigência da Polícia Federal.)
- Recrutamento: Abertura da Vaga, Grau de Instrução, Escala, Início da Seleção, Qtde Vaga,
  **Candidatos Aptos**, **Candidatos Solicitados**. Status: preenchido/aprovação/aberto/superlotado/aguardando.
- **Mapa de Férias com legenda por idade do período aquisitivo**: <12 meses · 12–16 · 17–19 ·
  20–22 · **>22 meses**, com contagem em cada faixa. É o painel de risco de férias vencendo.
- Catálogo de eventos: FT SEMANAL/MENSAL por posto e turno, TROCA FOLGA, ADICIONAL NOTURNO 20%,
  AUXÍLIO DOENÇA, ESCOLTA-DESCONTO COM OFICINA, ESCOLTA-CRÉDITO DE SERVIÇO, ESCOLTA-VALE,
  ESCOLTA-MULTA DE TRÂNSITO.
- **Sindicatos**: 20+, com Convênio, Telefone, **Mês Dissídio**, Tipo PATRONAL/LABORAL e botão
  Pagamento. **Cálculo de pagamentos sindicais.**
- Rescisões: Aviso, Último Doc, Exames, Afastamento, Pagamento, Pagamento Rescisão, **Pagamento
  FGTS**, Centro de Custo, Conta Bancária, **Plano de Contas Rescisão** (`1781 - FGTS - RESCISÃO`),
  com o catálogo CLT de motivos. E **Fechamento de Vales por FT** / como Eventos.
- Também: Medidas Disciplinares · Alocação em Filiais · **Pensionistas** · Afastamentos ·
  **Carta de Retorno de Afastamento** · Documentos Admissionais · **Crachás e Crachás em Lote**.

### 3.5 Ponto — e a conformidade
- App **CRONOS**: facial, **online e offline**, sem limite de aparelhos, batimento via navegador,
  batimento com senha, **solicitação de selfie**, justificativa pré-aprovada, aviso de falta de
  batimento ou batimento irregular, monitoramento em tempo real, cálculo de eventos personalizado,
  **canal direto com o RH com envio e recebimento de documentos**, convocações e avisos.
  Declara: *"atendendo rigorosamente todas as exigências da **Portaria 671**"*.
- **Localizações**: batida no Google Maps com **raio desenhado**; `latitude/longitude` por apontamento.
- **Assinatura digital do cartão de ponto** com login + senha + facial, com Motivo de Recusa e
  contadores Aberto/Aprovado/Rejeitado. (Medido na base do deck: `Aberto 2535 · Aprovado 2` — a
  adoção é quase nula. O recurso existe; o hábito não.)
- Espelho impresso com CNPJ do emitente, CTPS, Série, PIS, Cargo, Contrato, **Posto**, Escala
  (`12X36 18:00 AS 06:00`), Local de Prestação, **EVENTOS CALCULADOS** (`13 - ADICIONAL NOTURNO
  20% → 107:00`, `142 - HORAS NOTURNAS REDUZIDAS → 015:17`) e, por dia, 3 pares de entrada/saída,
  Situação, Férias, **Banco de Horas Dia / Acumulado**, Eventos/Ref.
- **Fechamento de Folha**: configuração de cálculo com Tolerância, Tipo (FOLGA TRABALHADA),
  Intrajornada (mínimo/tolerância/arredondamento), Atraso, HE 50%, HE 100%, Adicional Noturno,
  **Horas Noturnas Reduzidas**, Descanso na Hora Noturna, Hora Noturna por Jornada, Adicional
  Feriado, Horas Folga Trabalhada, Período/Tipo de FT, Valor/Hora FT, Trabalho em feriado, Carga
  Mensal. Mais **Sequências de escala** (entrada/saída ×3 por número de sequência).

⚠️ **E O LIMITE DELES, que o diagrama de fluxo confessa:** no diagrama, todos os módulos são
retângulos; só `FOLHA` e `CONTABILIDADE` são desenhados como **bandeiras**. A tela de Apontamentos
tem um dropdown de **Leiaute**: `Pontomatic · Domínio · TOTVS RM · Datamace · Datamace V2 · Sage ·
Protheus · GI`. **Eles não calculam folha — exportam apontamento para folha de terceiro.**
(O terceiro da Conecta Mais é o Domínio, que está na lista.)

### 3.6 Frotas
Grade com KM Atual, **Próx. Troca Óleo / Restam**, **Próx. Troca Pneu / Restam**, Próx. Troca
Correia — `Restam` fica **negativo e vermelho** quando venceu.
**Vistorias de entrega e devolução**: `Status do Checklist` (Ok/Avariado) × `Status de Saída`
(Sem diferenças / **Houve diferenças** / Aguardando checklist), por placa e condutor, com **foto
por área do veículo** (dianteira com iluminação, lateral direita) e avaliação Bom/Ruim —
comparando CHEGADA vs SAÍDA lado a lado, com KM e horário de cada.
Abastecimentos: valor/litro, litros, valor, condutor, **data de aprovação**.
Manutenção: valor mão de obra / peças / total, data de liberação, forma de pagamento, e
**gera manutenções periódicas ao finalizar**.
Multas: Nº AIT, **Nº Renainf**, Nº Notificação, Boleto, infração por extenso, e
**"o sistema indica o condutor que estava com o veículo na hora da multa"**.

### 3.7 Facilities / Q-Watcher / Demandas / Chamados
- **Q-Watcher**: checklist por ambiente e grupo (Copa/Diretoria, Sala/Recepção, Banheiros/Noturno)
  com Ordem, Período, Frequência, Grupo, Tempo, Horários, **Foto obrigatória (sim/não)** e
  **Indicar quantidade (sim/não)**. Planejamento em calendário mensal/semanal/diário.
  Mapa por período: `diário · semanal · quinzenal · mensal · bimestral · trimestral · semestral ·
  anual`, em grade ambiente × dia. Dashboards Bom/Ruim/N/A por cliente e Realizado/Não Realizado.
  Mapa de supervisores no Google Maps. Clientes nas telas: Diageo, Brasilprev, Dow, Waters,
  Amgen, AbbVie, Banco do Brasil.
- **Chamados**: o CLIENTE abre pelo próprio celular num link consciente do LOCAL
  (`VOCÊ ESTÁ NO(A): EMPRESA DE LIMPEZA - COPA`) com título, solicitante, descrição e **foto**;
  cai no app do supervisor. Clientes: Bimbo do Brasil (7 unidades), FMT Brasil.
- **Demandas**: Prioridade (Baixa/Média/Alta), Prazo, **Tempo Gasto**, Assunto (Almoxarifado,
  Manutenções, Preventiva, RH, Compras), Cliente, Colaborador, anexos, **Código OS**, Conclusão,
  Finalização. Dashboard com abas: Demandas · **SLA** · Materiais utilizados · **Materiais em
  falta** · Colaboradores · Grid. Clientes: TJ Campinas, Cidade Judiciária, Barueri.
- **Avaliações**: totem/tablet/QR com carinhas (N/A · ótimo · bom · regular · ruim) por item do
  ambiente (assento, mesas, cadeiras, paredes, portas / privada, piso), **câmera por item**,
  dashboards por ambiente, e **links compartilháveis** — com e sem identificação obrigatória.
  Tipos: avaliação de Contratos · Departamentos · Clientes · **Propostas**.

### 3.8 Rondas
QR Code substituindo o bastão. Registro com `LATITUDE/LONGITUDE` por ponto, item, descrição,
ação, observação, **ocorrência SIM/NÃO** e **foto** (as telas mostram a foto do adesivo QR na
parede). **Mapa de Rondas**: grade ponto × dia do mês com a contagem de rondas, **vermelha quando
abaixo do alvo**, agrupada por empresa. O app **salva offline** quando não há internet.

### 3.9 Suprimentos e Compras
Uniformes/EPI com **grade de tamanho** (P/M/G/GG/EXG) e `Mínimo · Máximo · Pendente · Atual · Valor`
por SKU. Entregas individual e **em lote**, com Solicitação → Separação → Entrega, motivo
(Admissão), prazo de entrega, anexo, e situação **Devolvido**.
**Alocação de Equipamentos: `ARMAMENTO 4/4` · `COLETE 4/4`.**
Solicitações de materiais com aprovação (Aberta/Atendida/Parcial/Rejeitada), centro de custo de
origem e **destino**.
Compras: Solicitação → **Cotação** (fornecedor, forma e condição de pagamento, prazo, total) →
**Nota Fiscal de entrada** (produtos, serviços, impostos, frete, seguro, desconto, despesas
acessórias) com **☑ Gera Conta a Pagar**, plano de contas e forma de pagamento.
Unidades de medida com **mapeamento para `Unidade NFe`**.

### 3.10 Faturamento e Financeiro
- **NFS-e**: pipeline `aprovar nota → gerar arquivo remessa → transmitir para prefeitura →
  processar retorno → impressão RPS`. Emissão de nota **e de boleto** (exemplo real: NFS-e da
  Prefeitura de São Paulo, RPS nº 16035 Série A, com boleto Itaú 341-7).
  ⚠️ O exemplo é a NFS-e **de São Paulo**, que tem sistema próprio. **Manaus é ABRASF 2.04 e o
  material não mostra.** Não afirmar que atende sem perguntar.
- Contas a Pagar com **coluna Aprovado** e status Aberta/Paga/Vencida/Cancelada/Processo.
- Contas a Receber com Duplicata, Sacado e status **Protestado**.
- **Contas Fixas** recorrentes com `Tipo de Conta`, `Período`, `Vencimento` expresso como regra
  (`1º DIA FIXO (MÊS CORRENTE)`, `23º DIA FIXO`, `28º DIA FIXO`) e **`Gerado Até`**.
- Centros de custo **hierárquicos** (código `10.1`, `10.10`, `10.100` com coluna `Relação` = pai).
- Extrato bancário com **Plano de Conta por movimento** e saldo corrente linha a linha.
- Dashboard: A Pagar · Em Atraso · A Receber · Em Atraso + Lucro/Prejuízo, e receita/despesa por
  empresa. Faturamento acumulado por mês e **Top 10 clientes** por faturamento.
- **Escolta – faturamento por fechamento de missão**, com status `aguardando fechamento ·
  finalizada · missão cancelada · fechamento cancelado · **nota fiscal emitida** · cancelada com
  operação · **nota fiscal emitida parcialmente**`.

### 3.11 Escolta (linha inteira que não temos)
Missão com Origem/Destino por extenso, Data Solicitação, Data Programada, **Saída Base, Km Saída
Base, Início Viagem, Km Início Viagem, Chegada Origem, Km Chegada Origem, Início Missão**.
**Quadro Operacional**: viatura por `PREFIXO`, **Rodízio (sim/não)**, Operação, **Equipe (dupla)**,
Entrada/Saída, Obs. Equipe, Retorno, Cliente, Origem, Destino, Atualização, MCT, **Rádio**.
Legenda: `VTR disponível · em missão · urbana · viagem · manutenção · rodízio · equipes na base ·
equipes retornando`. Painel operacional com **12 abas**.
OS com rastreamento no mapa e marcos: `início de viagem → troca de condutor → chegada na operação
→ início de operação → término de operação`.
Clientes nas telas: Bayer, TNT, FedEx, UPS do Brasil, Claro, Rede Globo, TV Globo, Record,
GPA, Fast Shop, Panini, Skymark, Apisul, Marlog, Viktoria Cargas, Invictus.

---

## 4. O que eles NÃO têm — o nosso terreno

Nas 73 páginas e no site inteiro, **zero menção** a:
`eSocial` · `FGTS Digital` · `EFD-Reinf` · `DCTFWeb` · `SPED Fiscal/Contábil` · `eCAC` ·
`SEFAZ/NF-e` · `Simples Nacional` · `certidões negativas`.

E também não têm:
- **Cálculo de folha** (exportam para Domínio/TOTVS/Sage/Protheus).
- **GED com kit documental** e assinatura **ICP-Brasil A1 qualificada** de contrato. (A assinatura
  deles é do espelho de ponto, com login+senha+facial — outra coisa, e mais fraca juridicamente.)
- Agente de WhatsApp, orquestrador, MCP. (Têm IA em UM lugar: filtro de foto na limpeza pública.)
- Portal do colaborador na web.

**Encaixe regional**: todos os sindicatos são SP/DF; todas as linhas de VT são da Grande SP; a
NFS-e do exemplo é paulistana; e a proposta cobra **deslocamento e estadia fora de Guarulhos e
Grande São Paulo por conta do cliente** — de Guarulhos a Manaus, a cada implantação e cada suporte.

---

## 5. Estado MEDIDO do Conecta PRO (12/09/2026)

### 5.1 A conformidade do ponto — o achado mais grave
A Portaria 671 exige, para ponto 100% software (REP-P): registro do programa no **INPI**, geração
de **AFD assinado digitalmente**, exportação do **AEJ** (Arquivo Eletrônico de Jornada) e
**Atestado Técnico + Termo de Responsabilidade** entregue ao empregador.

| Exigência | Conecta PRO |
|---|---|
| AFD | existe: `modules/hr/rep_integration`, com SHA-256 por linha |
| AFD montado na API | **NÃO** — `rep_integration` não está em `main_production.py`. Zero rotas |
| AFD com dado | **`afd_records`: 0 registros.** Nunca usado |
| AEJ | **zero menções no repositório** |
| REP-P | **zero menções** |
| INPI | **zero** |
| Atestado Técnico | o único no código é o do **EPI** — coisa diferente |

**52 pessoas batem ponto todo dia num programa que não é um REP-P constituído.** O módulo AFD está
no disco, montado em lugar nenhum, com zero linhas. Isso não é falta de feature: é exposição.
O CRONOS deles anuncia a conformidade; o nosso não a tem.

### 5.2 Paridade de cadastro e processo

| Item deles | Conecta PRO (medido por grep em `backend/modules/`) |
|---|---|
| PLR | só **tipo de evento** de folha (`payroll_event`, `payslip`); sem cálculo nem distribuição |
| Crachás / em lote | só um **campo** no cadastro; não gera crachá |
| Pensionistas | pensão alimentícia é **calculada**; sem cadastro de beneficiário |
| Carta de retorno de afastamento | 1 arquivo — raso |
| Medidas disciplinares | 49 arquivos — coberto |
| Frotas | 13 arquivos |
| Suprimentos/estoque | 65 arquivos — coberto |
| Representantes/comissão | 22 arquivos — coberto |
| Nome de guerra · CNV · reciclagem com validade | **não existe** |
| Alocação de armamento/colete | **não existe** |
| Sindicato com mês de dissídio e pagamento | parcial (CCT existe) |
| Mapa de férias por idade do período aquisitivo | **não existe** |
| Reajuste de benefício com repasse ao contrato | **não existe** |
| Grade de tamanho de uniforme com mínimo/máximo | **não existe** |

E a nossa própria auditoria de 09/09 (`ANALISE_DOCS_REAIS_vs_CONECTA_PRO_20260909.md`) já registra
que o holerite não emite: `DESC.ADIANT.SALARIAL`, salário-família, insalubridade por posto,
consignado, reflexo de DSR sobre extras, dias normais proporcionais na admissão.

---

## 6. Ordem de ataque

Critério: primeiro o que é **jurídico**, depois o que **muda o número**, depois o que **muda a
tela**. A régua da casa — dinheiro, tributo e órgão público antes de cosmética.

**1. Conformidade do ponto (REP-P).** AEJ + montar e popular o AFD + registro INPI + atestado
técnico e termo de responsabilidade. Único item da lista que é risco legal acumulando todo dia.

**2. Facial offline com fallback automático.** Eles publicaram (Cronos 3.61.9). É o defeito que
nos custou a semana. Copiar o comportamento: reconhecimento local quando a conexão oscila, e
menos chamadas de API.

**3. Benefício ligado ao ponto, com as colunas deles.** `Planejado/Trabalhado/Recebido/Direito
(anterior) · Saldo · Previsão · ±Ponto · Crédito-Débito`, mapa de frequência dentro do cálculo,
horas mínimas para recebimento, geração do arquivo do operador, e **reajuste com repasse ao
contrato**. A nossa auditoria já diz que o VT/VR não fecha; esta é a forma que fecha.

**4. Mapa de Ponto com os cinco estados + Grid de Planejamento `real/contratual`.** Os dados já
existem (a triagem do Hermes de hoje separou exatamente esses casos — em prosa). Falta a tela que
o Paiva e o Gonzaga abririam todo dia.

**5. Conformidade de vigilante.** Reciclagem com validade de 2 anos por pessoa, CNV, nome de
guerra, e alocação de armamento e colete. Exigência de Polícia Federal, custo baixo, risco alto.

**6. Precificação com os nove modos + reserva técnica + PLR sindicato % + calculado vs faturado.**

**7. Mapa de férias por idade do período aquisitivo** (a faixa `>22 meses` é o alarme de dobra).

**8. Uniforme/EPI com grade de tamanho** e entrega em lote.

**9. Frotas: `Restam` negativo em vermelho, vistoria chegada×saída com foto por área, e o condutor
identificado na hora da multa.**

**10. Checklist com foto obrigatória por item** (Q-Watcher) e **chamado aberto pelo cliente com o
local já preenchido pelo QR**.

### O que NÃO copiar
- **A interface.** Grade densa de 2005; funciona porque o operador decorou, não porque é boa.
- **O recorte regional**: sindicatos SP/DF, linhas de ônibus da Grande SP, NFS-e paulistana.
- **A arquitetura de folha** (exportar em vez de calcular) — ali o nosso desenho é melhor e é
  vantagem competitiva, não dívida.

---

## 7. Fontes
- `uploads/jordan_20260912/Apresentacao.pdf` — 73 páginas, lidas integralmente (60 visualmente,
  13 por texto). Metadados: PowerPoint de Arthur Campelo, criado 29/10/2025, modificado 02/07/2026.
- `uploads/jordan_20260912/Proposta.pdf` — proposta nº 665_2026, 12 páginas, assinada por
  Adriana Senedese Varo, Gerente Administrativa.
- https://www.dgxbrasil.com.br — produtos, 68 clientes, contatos, apps
- https://www.linkedin.com/company/digi-express-soluções-inteligentes — 11–50 funcionários
- apkcombo / apkpure — versões, datas, instalações, notas e changelog dos apps
- https://www.gov.br/trabalho-e-emprego/.../rep e Portaria MTP 671/2021 — exigências do REP-P
- https://www.gesoper.com.br/site/ — concorrente (Sollução Informática, desde 1986, 13 módulos)
