# Pré-mortem das 10 frentes — o que vai dar errado, e a trava de cada uma (12/09/2026)

**Pedido do Jordan:** *"o que pode dar errado nessas 10 implementações? Quero um pré-mortem
detalhado, algo que possamos evitar que aconteça erros, quebras, problemas."*

**Método:** para cada frente, os modos de falha **desta casa** — não riscos genéricos. Cada
previsão abaixo tem precedente medido, com data. A pergunta do pré-mortem é uma só:
*"é 15/10/2026, a frente falhou. O que aconteceu?"*

**Regra de ouro que vale para as dez:** *nenhuma frente começa sem o oráculo que prova que ela
falhou ANTES do conserto.* Foi assim que se descobriu que a política de assinatura passava verde
estando errada (09/09) e que o José Luís prometia transferência sem transferir (11/09). Trava
escrita depois do conserto afirma o conserto, não a regra.

---

## PARTE 0 — Os cinco riscos que derrubam QUALQUER das dez

Estes não são de nenhuma frente. São do terreno, e se não forem resolvidos primeiro, as dez
falham juntas.

### 0.1 🔴 Não existe monitoramento de erro em produção
`.env` linha 176: **`SENTRY_DSN=`** — vazio. A linha 175 é o exemplo comentado. O backend já
registrou **29 vezes** *"SENTRY_DSN nao configurado — erros de produção não serão monitorados"*.
**Consequência nas dez frentes:** toda exceção nova morre no log de um container que ninguém lê.
A frente 2 (facial offline) e a 6 (foto no momento) rodam no celular do porteiro — sem Sentry,
uma quebra lá é invisível até alguém perder a jornada.
**Trava:** preencher o DSN antes da primeira linha de código das dez. É uma linha de `.env`.

### 0.2 🔴 O saldo do LLM é US$ 1,10
As frentes 3 e 4 dependem do Hermes para triagem e do agente para avisar gente. Quando o saldo
acabar, ele para **sem avisar quem está do outro lado**. E a medição de gasto/dia lê `0,00`, então
nem se sabe quantos dias restam. Decisão do dono em 07/09 foi não recarregar — **fica registrado
que as frentes 3 e 4 herdam esse limite.**

### 0.3 🟠 O hábito da casa é `docker cp`, e `docker cp` não publica
`kill -HUP 1` **não recarrega Python** (confirmado 3× em 2026: 22/04, 14/08, 24/08). E
`checar_bake_pendente` voltou de 0 para **6** em menos de 24h depois dos três bakes de ontem.
**Consequência:** código das dez frentes vai "funcionar" em teste e não estar servindo.
**Trava:** nenhuma frente é declarada pronta sem `checar_bake_pendente = 0` e sem
`checar_drift_workers` limpo.

### 0.4 🟠 Sessões paralelas disputam a imagem e o lock
Ontem, em 20 minutos: a tag `conecta-pro-mcp:latest` foi reconstruída **três vezes** por outra
sessão; o bake blue/green morreu porque o container de homologação ocupava a porta 8081; e
`mcp-server/` alternou entre limpo e com 4 arquivos não commitados.
**Trava:** antes de recriar container, provar que a imagem bate com o disco **e** que o disco bate
com o HEAD. Se houver WIP alheio, não publicar — é publicar trabalho de outra pessoa pela metade.

### 0.5 🟠 Já temos cinco módulos com código e zero rotas
`bidding` (101 arquivos), `health_occupational`, `retention`, `document_kits`, `rep_integration`.
**Consequência:** as dez frentes vão somar a uma pilha que já existe. Se a frente 9 não vier
junto, o Conecta PRO fica com 15 módulos mortos em vez de 5.

---

## FRENTE 1 — REP-P: AEJ, AFD montado e populado, INPI, atestado técnico

### O que vai dar errado
1. **Vai se implementar o AEJ e declarar conformidade sem o INPI.** O registro do programa no
   INPI é **precondição legal** para usar REP-P — não é opcional nem posterior. Sem ele, um AEJ
   perfeito não vale nada numa fiscalização, e a sensação de "resolvido" é o pior resultado
   possível: risco igual, vigilância zero.
2. **O AFD vai ser populado retroativamente e isso é falsificação.** O AFD é, por definição,
   memória **inalterável** de marcação. Preencher com as batidas históricas (que hoje vivem em
   `time_records`) cria um arquivo que afirma integridade sobre dados que passaram por edição
   manual do DP, contingência e importação do Tangerino. **Isso é pior que não ter AFD.**
3. **`rep_integration` vai ser montado e vai derrubar o boot.** São 9 arquivos que nunca rodaram
   em produção; `afd_records` tem 0 linhas. O `safe_import` do `main_production` engole falha de
   módulo em silêncio — então ele pode ser "montado" e continuar sem rota, exatamente como hoje,
   sem ninguém perceber.
4. **O NSR vai duplicar.** O AFD exige Número Sequencial de Registro contínuo e sem lacuna por
   equipamento. Com facial, contingência, web do DP e importação do Tangerino escrevendo no mesmo
   dia, a sequência quebra — e o incidente de 11/09 (1.375 jornadas duplicadas por importação de
   origem cruzada) prova que o nosso pipeline já duplica.
5. **O atestado técnico será assinado por nós mesmos sem base.** Ele é emitido pelo
   **desenvolvedor** e atesta requisitos técnicos específicos. Assinar sem cumpri-los é declaração
   falsa, com o dono como responsável.

### Como vamos saber
- Oráculo `test_oraculo_rep_p.py`, **escrito antes**, afirmando: (a) `/api/v1/.../afd` responde e
  está em `app.routes`; (b) `afd_records` cresce todo dia em que houve batida; (c) o NSR é
  **contínuo e único** por dispositivo, sem lacuna; (d) o AEJ gerado reabre e casa com o espelho
  da mesma competência; (e) existe registro INPI e atestado com data de validade no banco.
  **Hoje ele deve sair vermelho em cinco afirmações. Se sair verde, está medindo a coisa errada.**
- Caçador `checar_ponto_sem_instrumento.py`: conta pessoas com batida no mês **sem** AFD
  correspondente. Hoje: 52. Alvo: 0.

### Travas
- **Corte temporal explícito, como o de 01/08 na contabilidade:** o AFD começa numa data definida
  pelo dono, para frente. O histórico fica como está, documentado, sem fingir integridade.
- Cada origem de batida (facial, contingência, web do DP, Tangerino) carrega **identificador de
  origem** no AFD. Origem indistinguível é o buraco do NSR.
- O atestado técnico só depois de uma checklist item-por-item da Portaria, com o item e a evidência.
- **Ordem obrigatória:** INPI e atestado são jurídicos e vão para o Jordan/contador, não para
  sessão autônoma. O código sem eles é metade da frente.

---

## FRENTE 2 — Facial offline com fallback automático

### O que vai dar errado
1. **Offline vai virar porta de fraude.** Se o descriptor for comparado no aparelho e a batida
   aceita sem servidor, quem controla o aparelho controla a batida. O `distance < 0.68` do
   face-api.js é decidido no cliente — hoje o servidor confere; offline, ninguém confere.
2. **A batida offline vai chegar com o horário do celular.** Relógio de aparelho é editável.
   Batida com `created_at` do servidor e `hora` do aparelho é exatamente o defeito de fuso que
   custou 180 turnos em 11/09 — só que agora falsificável de propósito.
3. **A fila offline vai duplicar na volta do sinal.** Sem chave idempotente por
   (pessoa, minuto, dispositivo), a retentativa cria segunda batida — o mesmo mecanismo dos 1.375
   duplicados.
4. **O descriptor vai para o aparelho, e isso é dado biométrico.** LGPD trata biometria como dado
   sensível. Descriptor em `localStorage` de celular de porteiro, sem criptografia e sem prazo, é
   incidente esperando data.
5. **`SEM_ROSTO_MAX = 40` vai mascarar a falha.** Hoje o `nao_detectou` é registrado. Offline,
   a tentativa falha e **não sai do aparelho** — a estatística de falha de reconhecimento desaparece
   justamente quando mais importa.

### Como vamos saber
- Oráculo `test_oraculo_batida_offline.py`: (a) toda batida com `origem=offline` tem chave
  idempotente e **nenhuma duplicata** na janela de 20 min; (b) `hora_aparelho` e `hora_servidor`
  divergem menos que o limite declarado, e a divergência é **gravada**; (c) descriptor não é
  persistido em claro.
- Caçador `checar_batida_offline_suspeita.py`: batidas offline com divergência de relógio acima do
  limite, ou 100% de sucesso facial (taxa perfeita é sinal de que a comparação não está ocorrendo).

### Travas
- Batida offline entra como **`pendente_de_conferencia`**, nunca como batida final. O servidor
  reconfere o descriptor na sincronização; passou, vira definitiva; não passou, vira pendência do
  DP com foto.
- **Gravar as duas horas, sempre** (aparelho e servidor), e a diferença.
- Idempotência por `(employee_id, minuto, device_id)` — a mesma régua dos 20 minutos que já
  existe no importador do Tangerino.
- Descriptor no aparelho com validade curta e apagado no logout. Prazo declarado na LGPD.

---

## FRENTE 3 — Benefício ligado ao ponto + arquivo do operador + repasse ao contrato

### O que vai dar errado
1. **É a frente que mexe em DINHEIRO DE PESSOA, e o nosso motor já erra.** A auditoria de 09/09
   registra que o holerite não emite `DESC.ADIANT.SALARIAL` — o líquido sai ~40% maior que o real.
   Construir benefício sobre uma folha que já erra propaga o erro para o VT/VR.
2. **O arquivo do operador vai ser gerado errado e ninguém vai perceber até o cartão não carregar.**
   `ALELO_...txt` tem layout posicional de terceiro. Um campo deslocado gera arquivo aceito pelo
   portal e crédito na pessoa errada. E o aceite do portal **não é prova** — é o mesmo "200 que
   mente" dos dez handoffs perdidos.
3. **O repasse ao contrato vai reajustar cliente sem autorização.** Propagar o aumento do VR para
   o preço do contrato é **alterar contrato assinado**. Feito por rotina, é faturamento indevido —
   exatamente o que o case 4 da DGX diz que eles eliminaram.
4. **As colunas "anteriores" (Planejado/Trabalhado/Recebido/Direito) exigem histórico que não
   temos.** O motor deles compara com a entrega anterior. Nosso primeiro mês não tem anterior — e
   `coalesce(anterior, 0)` transforma "não sei" em "zero", que vira crédito ou débito inventado.
5. **`vt_modalidade`, `plano_odonto_ativo` e `plano_odonto_dependentes` estão fora do alembic.**
   Criadas por SQL direto em 09/09. Num banco recriado elas desaparecem **em silêncio** (o motor
   lê com `coalesce`/`try-except`) e o desconto simplesmente some.

### Como vamos saber
- Oráculo `test_oraculo_beneficio_fecha.py`: soma do que os portais pagaram = soma do que a folha
  concedeu, por competência, por pessoa. Divergência > R$ 0,01 é vermelho.
- Oráculo `test_oraculo_arquivo_operador.py`: o arquivo gerado é **relido pelo nosso próprio
  parser** e tem de reproduzir exatamente as linhas de origem (ida e volta).
- Caçador `checar_repasse_sem_aditivo.py`: contrato com preço alterado por rotina e sem aditivo
  assinado. Alvo permanente: 0.

### Travas
- **Nada de repasse automático.** O reajuste gera **pedido na Central de Aprovações** (o
  `gate_propose` já existe e já funciona — provado ontem com `excluir_documento`), e só vira preço
  depois de aditivo. Decisão de contrato é de gente.
- Primeiro mês roda em **paralelo cego**: o sistema calcula, a Pyetra confere no olho, ninguém
  publica. Dois meses de concordância antes de virar fonte.
- As três colunas fora do alembic viram migration **pela mão do Jordan** antes desta frente.
- "Sem anterior" é **estado próprio**, nunca zero.

---

## FRENTE 4 — Grid real/contratual + Mapa de Ponto com os 5 estados

### O que vai dar errado
1. **A tela vai mostrar número diferente do que o Hermes falou às 08:30.** Dois caminhos para a
   mesma resposta viram duas verdades — é o defeito da tela de férias que mostrou 15 onde havia
   19, e é a razão de `coorte_ponto` existir como régua única.
2. **"Posto descoberto" vai ser pintado para gente que não devia estar lá.** Férias, afastamento e
   demitido já derrubaram a cobrança de ponto antes; a Cintia e o Aryelton apareceram com 256
   batidas sendo afastados. Grade sem `SQL_NAO_AUSENTE_HOJE` acusa falta de quem está de licença.
3. **A grade vai ficar 1 hora errada.** `communication_notifications.created_at` é
   `timestamp without time zone` guardando UTC — `AT TIME ZONE 'America/Manaus'` **soma** 4h em vez
   de subtrair. Eu mesmo li 16:32 no lugar de 08:32 hoje. Numa grade hora a hora, isso pinta o
   turno errado.
4. **Vai ficar pesado e ninguém vai abrir.** Matriz cliente × dia × posto com 13 clientes e 65
   pessoas, recalculada a cada abertura, é consulta lenta. O `consultar_kits` deu **ReadTimeout**
   na primeira batida de ontem. Tela que demora é tela que o supervisor abandona.
5. **Os cinco estados vão virar dois.** "Atendido posto incorreto" e "atendido fora de escala"
   exigem comparar a batida com a **escala do dia** e com o **posto do geofence**. A escala esteve
   1h errada desde julho e o Francisco Ramon sai `fora_local` em 100% das batidas por cadastro de
   posto errado. Sem consertar a fonte, dois dos cinco estados nascem mentindo.

### Como vamos saber
- Oráculo `test_oraculo_grid_bate_com_a_triagem.py`: a contagem da grade e a da triagem do Hermes,
  no mesmo dia, têm de **coincidir pessoa a pessoa**. Divergência = vermelho, e diz quem.
- Oráculo já existente `test_oraculo_afastado_nao_bate.py` estendido: ninguém de férias ou afastado
  aparece como descoberto.
- Caçador `checar_tela_lenta.py`: rota da grade acima do teto de tempo declarado.

### Travas
- A grade lê **a mesma função** que a triagem, não uma consulta nova. Uma régua, duas superfícies.
- `SQL_NAO_AUSENTE_HOJE` é obrigatório na consulta da grade.
- **Proibido `AT TIME ZONE` em coluna sem fuso.** Onde a coluna é `timestamp without time zone`
  guardando UTC, a conversão é `AT TIME ZONE 'UTC' AT TIME ZONE 'America/Manaus'`. Vale um caçador
  que varre o repositório inteiro procurando o padrão errado.
- Corrigir cadastro de posto (geofence) **antes** de pintar "posto incorreto".

---

## FRENTE 5 — Conformidade de vigilante: reciclagem, CNV, nome de guerra, armamento/colete

### O que vai dar errado
1. **Vai se cadastrar a validade e não o alarme.** Campo `validade` sem varredura diária é o mesmo
   que nada — foi assim que os crachás da base deles apareceram todos "Vencido". Data guardada não
   vigia ninguém.
2. **A data vai vir do papel e o papel vai estar errado.** Reciclagem tem validade legal contada
   da **conclusão do curso**, não da emissão do certificado nem da admissão. Errar a âncora
   coloca vigilante vencido em posto — que é interdição, não multa.
3. **Armamento vai ser um número, não um controle.** `4/4` só significa algo com **série por
   arma**, responsável, data de entrega e devolução. Hoje temos `armamento` como **flag** em
   `post.py`, `employee.py` e `allocation.py`. Um contador sem série não responde "onde está a
   arma 3".
4. **`nome_social` já existe e vai colidir com `nome de guerra`.** São conceitos diferentes
   (tratamento vs. identificação operacional). Reaproveitar o campo faz o agente chamar alguém
   pelo nome de guerra numa conversa pessoal.
5. **Vai faltar o dado e o sistema vai assumir que está tudo certo.** 12 funcionários já estão sem
   telefone no cadastro. Reciclagem sem data vai cair no `coalesce` e virar "válido".

### Como vamos saber
- Oráculo `test_oraculo_vigilante_apto.py`: ninguém escalado hoje com reciclagem vencida, CNV
  vencido ou **sem data** (ausência conta como impedimento, não como ok).
- Caçador `checar_arma_sem_serie.py`: arma alocada sem número de série ou sem responsável.

### Travas
- **Ausência de dado é bloqueio, não permissão.** A régua da casa: `sensivel()` do MCP trata
  desconhecido como sensível; aqui, desconhecido é inapto.
- Série obrigatória por arma, com entrega e devolução datadas e assinadas.
- `nome_de_guerra` é coluna nova. `nome_social` continua sendo tratamento.

---

## FRENTE 6 — Foto no momento + offline-first na ronda e no checklist

### O que vai dar errado
1. **"Foto no momento" só é verdade se a câmera for a fonte.** Permitir escolher da galeria
   destrói a trava inteira, e é o caminho que todo framework oferece por padrão.
2. **Offline vai encher o aparelho e perder registro.** Ronda com foto ocupa megabytes por ponto.
   Um turno de 12h sem sinal enche a fila; sem teto e sem política de descarte, o app trava ou
   apaga — e o registro perdido é o que a ronda existia para provar.
3. **A foto vai chegar sem o ponto.** Upload de imagem e registro de ronda em requisições
   separadas cria ronda sem foto e foto órfã. É o mesmo par que quebrou a assinatura do kit.
4. **O EXIF vai ser a única prova de horário, e ele é editável.**
5. **Vai consumir a franquia de dados do porteiro.** Sem compressão e sem política de "só no
   Wi-Fi", a conta chega para ele.

### Como vamos saber
- Oráculo `test_oraculo_ronda_com_foto.py`: nenhuma ronda com `foto_obrigatoria=true` fechada sem
  imagem; nenhuma imagem órfã; toda foto com carimbo de servidor.
- Caçador `checar_fila_offline_estourando.py`: aparelho com fila acima do teto ou item com mais de
  24h sem subir.

### Travas
- Captura **exclusivamente pela câmera**, sem picker de galeria. E a verificação é no servidor:
  imagem sem carimbo de captura não fecha a ronda.
- **Transação única**: ronda + foto sobem juntas ou nenhuma sobe.
- Hora do servidor na chegada, com a hora do aparelho gravada ao lado para auditoria.
- Teto de fila declarado, compressão antes de enfileirar, e aviso ao agente quando a fila encher.

---

## FRENTE 7 — Reserva técnica, PLR sindicato %, calculado vs faturado

### O que vai dar errado
1. **Reserva técnica vai virar percentual chumbado no código.** É o defeito clássico daqui — o
   balanço que não fechava porque `"3"` estava escrito no classificador em vez de sair do plano de
   contas. Reserva técnica varia por CCT, por função e por escala. Constante codificada é a fábrica
   de defeito desta casa.
2. **PLR sindicato % vai sair da CCT errada.** Nós temos CCT do Amazonas; a régua deles é SP.
   Aplicar o percentual de uma convenção em contrato regido por outra é erro de custo direto.
3. **"Calculado vs faturado" vai expor divergência que ninguém quer ver.** Quando a coluna
   aparecer, vai mostrar contratos faturados abaixo do custo calculado. É informação boa e
   conversa difícil — e o risco real é alguém "ajustar o cálculo" para a divergência sumir.
4. **Vai mudar preço de contrato vigente.** Recalcular com reserva técnica altera o custo de
   contratos já assinados. Se isso virar preço, é reajuste unilateral.

### Como vamos saber
- Oráculo `test_oraculo_precificacao_le_a_fonte.py`: nenhum percentual de reserva técnica, PLR ou
  taxa administrativa **literal no código** — todos lidos da CCT/parâmetro no banco. O oráculo
  falha se achar número mágico.
- Oráculo `test_oraculo_calculado_vs_faturado.py`: publica a divergência e **não** a corrige;
  vermelho é conversa com o dono, não conserto automático.

### Travas
- Ler a fonte, nunca codificar a convenção (regra 1 da camada Conecta).
- Recalcular é **simulação** por padrão; virar preço exige aditivo.
- A divergência calculado×faturado é relatório para o dono, nunca gatilho de rotina.

---

## FRENTE 8 — Mapa de férias por idade do período aquisitivo

### O que vai dar errado
1. **A âncora do período aquisitivo vai ser a admissão, e às vezes não é.** Afastamento acima de 6
   meses **reinicia** o período. Quem tem histórico de INSS — a Cintia, 3 meses afastada — cai na
   faixa errada, e a faixa errada esconde exatamente o risco que o mapa existe para mostrar.
2. **A faixa `>22 meses` vai aparecer vazia e parecer boa notícia.** É o "verde cego": zero por
   não ter calculado é idêntico a zero por estar em ordem.
3. **`float(idade or 999)`** — o padrão que eu mesmo escrevi errado em 11/09: `0` é falsy, e no dia
   em que a idade é 0 o cálculo usa o default.
4. **Vai contar quem não tem direito.** Menos de 12 meses de casa não tem período aquisitivo
   completo; contar como faixa de risco polui o painel.

### Como vamos saber
- Oráculo `test_oraculo_mapa_ferias.py`: a soma das faixas = total de gente com direito; nenhuma
  faixa calculada com default; e quem teve afastamento > 6 meses tem a âncora **recalculada**.
- Contra-prova obrigatória: o oráculo tem de acusar **vermelho** num caso montado com afastamento
  longo antes de o conserto entrar.

### Travas
- Âncora = maior data entre admissão e retorno de afastamento longo. Regra escrita, uma função só.
- Faixa sem dado é **faixa própria** ("não calculado"), nunca 0 nem a primeira faixa.
- Proibido `or <default>` em número que pode ser 0.

---

## FRENTE 9 — Ligar os módulos mortos (bidding 101 arquivos, health_occupational, retention, document_kits)

### O que vai dar errado
1. **Montar vai derrubar o boot, ou pior: não derrubar.** `main_production` usa `safe_import` com
   fallback — módulo que falha é engolido em silêncio. O `rep_integration` está exatamente nesse
   estado. Ligar sem conferir `app.routes` depois dá a ilusão de ter ligado.
2. **Vai colidir com tabela que não existe.** Esses módulos foram escritos contra um schema de
   outra época. `document_kits.extra_metadata` e três colunas de `condominiums` já são
   dessincronização conhecida. 101 arquivos de `bidding` nunca rodaram contra o banco atual.
3. **Vai expor rota sem autenticação.** Medido em 11/09: as rotas de ponto
   (`/people-management/ponto/...`) **não têm dependência de autenticação nenhuma**. Ligar 100
   rotas novas sem auditar `Depends(get_current_active_user)` uma por uma abre superfície.
4. **Vai ressuscitar código que deve morrer.** Parte desses 101 arquivos provavelmente deve ser
   **apagada**, não ligada. Nas últimas semanas foram aposentadas 132 rotas do DMS genérico, 70 de
   retention, 54 de document_kits, 26 de scheduler, 63 de services. Ligar sem decidir é dívida com
   juros.
5. **Vai crescer o `checar_nao_vigiado`** (hoje 390→391). Superfície nova sem oráculo é dívida no
   dia em que nasce.

### Como vamos saber
- Caçador `checar_modulo_morto.py`: módulo com mais de N arquivos e zero rotas, **nomeado**, com
  dono e decisão (ligar ou apagar). Hoje: 5.
- Oráculo por módulo ligado: as rotas declaradas estão em `app.routes` **e** respondem, e cada uma
  tem dependência de autenticação.

### Travas
- **Decidir antes de ligar**: cada módulo recebe "ligar" ou "aposentar", por escrito, do dono.
- Ligar um por vez, com `app.routes` conferido depois — a entrega não é o `safe_import`, é a rota
  respondendo.
- Toda rota nova nasce com auth e com oráculo. Sem isso, não sobe.

---

## FRENTE 10 — Grade de tamanho, frota, totem

### O que vai dar errado
1. **A grade de tamanho vai duplicar SKU.** "Blazer Feminino M" e "BLAZER FEMININO - M" viram dois
   itens, e o estoque mínimo passa a ser conferido por metade. `cacar_fabricacao` já conta 32
   achados de dado fabricado.
2. **`Restam` negativo vai depender de KM que ninguém atualiza.** Painel de manutenção só vale com
   quilometragem alimentada; sem isso, todo veículo aparece vencido e o painel é ignorado em uma
   semana.
3. **A vistoria chegada×saída vai comparar fotos de dias diferentes.** Sem amarrar as duas pontas
   pela mesma OS e pelo mesmo condutor, "houve diferenças" acusa o motorista errado — e isso é
   acusação sobre pessoa.
4. **"Identificar o condutor na hora da multa" exige histórico de posse do veículo.** Sem registro
   datado de quem estava com o carro, o sistema vai apontar o condutor **atual**, não o da data da
   infração. Apontar o inocente é pior que não apontar.
5. **O totem vai medir simpatia, não serviço.** Avaliação anônima em totem na portaria mede quem
   passou de bom humor. Sem amarrar ao ambiente e ao turno, o dado não decide nada e vira gráfico.

### Como vamos saber
- Oráculo `test_oraculo_sku_unico.py`: nenhum par de SKU que normalize para o mesmo nome.
- Oráculo `test_oraculo_vistoria_par.py`: toda vistoria de saída tem a de chegada correspondente,
  mesma OS, mesmo condutor, mesma janela.
- Caçador `checar_frota_sem_km.py`: veículo sem atualização de KM no período.

### Travas
- SKU normalizado na escrita (a mesma régua do `_normalize`/`_sig` que o Hermes do GEDEON já usa).
- `Restam` só aparece para veículo com KM atualizado dentro do período; os outros aparecem como
  **"sem dado"**, não como vencidos.
- Multa cruza com **posse datada**; sem posse na data, o campo fica vazio e vai para decisão humana.
- Avaliação sempre com ambiente + turno + contrato. Anônima quanto à pessoa, nunca quanto ao posto.

---

## O que o Jordan pesquisou (os dois links) — veredito honesto

**Post 1** (`@githubprojects`): "10 GitHub repositories that went viral last week" — IA, coding no
browser, analytics, bancos, edição de vídeo, compressão de imagem. O slide legível é o
`ESP32-BlueJammer` (interferência em 2,4 GHz). **Nada aplicável às dez frentes.**

**Post 2** (`@matheuscastro | AI Coding`): "50 servidores MCP", com a lista real **atrás de
"comente MCP para receber na DM"**. O carrossel mostra as categorias: essenciais (GitHub, Context7,
Playwright, Filesystem, Brave Search), dev (Supabase/Postgres, **Sentry**, Docker, Kubernetes),
criadores (Figma, ElevenLabs, DaVinci), equipes (Slack, Linear, Notion, Jira, Gmail), mercado
(CoinGecko, Dune, Etherscan, Polygon.io, TradingView) e pagamentos (Stripe, Plaid, QuickBooks).

**O que serve, de verdade:**
1. **Sentry.** Não pelo MCP — pelo produto. Foi esse slide que me fez conferir, e o nosso
   `SENTRY_DSN` está **vazio** no `.env` com 29 avisos no log. Vale mais que as outras 49 linhas
   da lista somadas. → virou o risco **0.1** deste documento.
2. **Playwright**, que já usamos, é a ferramenta da frente 4 (provar a tela de fora, não por
   dentro).
3. O slide de governança deles — *"trate cada servidor como código de terceiros; comece em somente
   leitura; nunca mova dinheiro sem confirmação humana"* — é **exatamente** a decisão que o Jordan
   tomou ontem ao pôr `MCP_MODO=agente` no `mcp-ged`. Valida o que já foi feito; não ensina nada
   novo.

**O que NÃO serve:** os MCP de mercado (cripto, ações) e de criadores não têm relação com o ERP. E
a regra da casa já cobre o resto: 266 ferramentas em 4 conectores com escopo e parede. Instalar
mais MCP agora aumentaria superfície sem resolver nenhuma das dez frentes — o próprio post diz
isso melhor do que eu: *"é um menu, não uma lista de compras"*.
