#!/usr/bin/env python3
"""Os caçadores rodam todo dia — e só reclamam quando a dívida CRESCE.

Os dois caçadores nasceram com 63 pistas em aberto (40 de fabricação, 23 de vocabulário).
Ligá-los cru na varredura diária faria o sino tocar vermelho toda madrugada com o mesmo
número — e sino que toca sempre é sino que ninguém escuta. Foi por isso que ficaram de fora,
e ficar de fora contradiz a regra da casa: skill só age quando invocada, check age sempre.

Saída: **linha de base**, o mesmo desenho do oráculo de período fechado. O que já existe fica
registrado; o que ENTRAR depois é regressão e acusa. Assim a dívida velha não vira ruído e
fabricação nova não passa.

Baixar a linha de base (consertou algo) é automático. Subir exige `--gravar` explícito e a
decisão escrita na mensagem do commit — deixar a dívida crescer é decisão, não acidente.

⭐ A base só se move com MEDIÇÃO VERIFICADA. Em 23/08/2026 uma rodada em que os caçadores
não responderam (container em recreate, saída vazia) foi lida como "0 pistas", a base
BAIXOU sozinha para 0, e a partir daí toda noite acusou "0 → 25 REGRESSÃO" por dez dias
seguidos — a dívida era a mesma de sempre (25 a 27). Sino que toca todo dia com o mesmo
número é sino que ninguém lê: foi assim que os 3 agentes do GEDEON ficaram 3 dias mortos.
Agora cada caçador tem uma LINHA CANÔNICA; sem ela a rodada é NÃO VERIFICADA, acusa, e a
base fica onde estava.

Aos domingos (ou com `--gates`) rodam também os critérios de aceite `fechado_*.py` e a
`varredura_op_acoes.py`: o número de condições ✅ de cada um entra na base e só acusa
quando CAI. Eles existiam desde agosto e nenhum caminho os invocava.

    python3 backend/scripts/qa/checar_regressao.py            # confere
    python3 backend/scripts/qa/checar_regressao.py --gravar   # (re)grava a base
    python3 backend/scripts/qa/checar_regressao.py --gates    # força os gates semanais
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent

#: FORA do repositório de propósito. A base é escrita SOZINHA quando a dívida cai, e um
#: arquivo versionado alterado por cron deixa o working tree sujo indefinidamente — nenhum
#: terminal vai commitar isso. Pela nossa própria regra, ` M` = outro terminal para e espera:
#: a automação dispararia a regra da parede falsamente.
BASE = Path("/var/lib/conecta/qa_baseline.json")


#: caçador -> como contar as pistas na saída dele. Devolve None quando a saída NÃO tem a
#: linha canônica do caçador — é o que separa "0 pistas" de "não rodou".
def _n(padrao: str, saida: str, zero: str | None = None) -> int | None:
    m = re.search(padrao, saida, re.M)
    if m:
        return int(m.group(1))
    return 0 if (zero and zero in saida) else None


CACADORES = {
    # Nota de HOMOLOGAÇÃO contada como receita real. Nasceu de erro MEU em 24/09: a conciliação
    # da NFS-e, rodada com as empresas em homologação, gravou duas notas de teste minhas
    # (R$ 1.500) na tabela que a precificação lê como faturamento. A trava não confia na coluna
    # `ambiente` — ela cruza com o que o sistema SABE ter emitido em teste, porque campo errado
    # é exatamente o defeito. CONTADA: tem de ser 0 e ficar em 0.
    "checar_homologacao_na_receita.py": lambda s: _n(r"^TOTAL: (\d+) nota\(s\) de teste contada", s),
    # Dia em que a pessoa trabalhou e a batida de ENTRADA (ou saída) não existe. Não é atraso e
    # não é falta: sem a batida, o mapa de ponto chuta e a conferência de atraso da X2 tinha 64%
    # de "atraso" que era isto (medido em 24/09/2026). CONTADA: dívida de operação com dono —
    # acusa se CRESCER. Enquanto o dia está aqui, ele fica FORA da conta de dinheiro, de propósito.
    "checar_batida_faltando.py": lambda s: _n(r"^TOTAL dias com batida faltando: (\d+)", s),
    # Contrato de valor único ATIVO sem nenhuma cobrança: o cronograma mora em
    # `contract_items` e o contas a receber não sabe dele — dinheiro contratado que não vira
    # boleto. Órfã desde que nasceu; ligada em 17/09/2026.
    "checar_contrato_sem_cobranca.py": lambda s: _n(r"^TOTAL contratos de valor único ativos sem cobrança: (\d+)", s),
    # Texto INTERNO (margem, custo, nota do vendedor) no material que vai para o cliente.
    # Órfã desde que nasceu; ligada em 17/09/2026. Verde hoje: 0 de 12 propostas.
    "checar_vazamento_interno.py": lambda s: _n(r"^TOTAL propostas com texto interno no material do cliente: (\d+)", s),
    # Lê o TOTAL da linha "N pista(s) em …", não as linhas listadas: o caçador corta a lista
    # em 12 por família e escreve "(+8 não listadas)" — contar linhas dava 25 onde eram 37.
    "cacar_fabricacao.py": lambda s: _n(r"^(\d+) pista\(s\) em", s, "nenhuma assinatura de fabricação"),
    # `__tablename__` sem tabela em schema nenhum (t6, 07/09/2026): o censo de uso real não vê
    # esta família por construção. 58 na estreia (gov_* 29, email_* 6, campo_* 4, wa_* 4).
    "checar_tabela_fantasma.py": lambda s: _n(r"fantasmas (\d+) \(", s, "fantasmas 0"),
    "checar_vocabulario.py": lambda s: _n(r"\((\d+) crítica\(s\)", s, "nenhuma divergência"),
    # varchar(N) com valor encostado no teto e comprimentos variados — o `varchar(20)` que
    # passou meses porque o nome tinha exatamente 20 (missão de 06/09/2026).
    "checar_varchar_teto.py": lambda s: _n(r"^TOTAL:\s*(\d+) coluna", s),
    # Coluna `*_id` de um tipo contra o `id` de outro. Nasceu da bateria E2E de 14/09/2026:
    # `time_sheets.employee_id` é VARCHAR e `employees.id` é UUID, e um NOT IN entre os dois
    # derrubou com 500 o endpoint que calcula e fecha o espelho da Portaria 671 — em TODA
    # competência, sem ninguém ver. Na estreia acusa 8, sendo 7 minas ainda não pisadas.
    "checar_id_tipo_divergente.py": lambda s: _n(r"^TOTAL:\s*(\d+) coluna\(s\) com tipo divergente", s),
    # Alocação ATIVA de quem já saiu: a cobertura do posto conta gente que não trabalha
    # mais lá. Eram 4 em 13/09/2026 (demissões de 22/07 a 24/08), e é exatamente o número
    # que dispara o alarme de posto descoberto. Alvo permanente: 0.
    "checar_alocacao_de_quem_saiu.py": lambda s: _n(r"^TOTAL:\s*(\d+) alocação\(ões\) ativa\(s\) de quem saiu", s),
    # Holerite de mês que nem começou (94 de nov/dez-2026 criados em 03/08) e holerite sem
    # `source_system` (12 em 08/2026): ambos poluíam a tela DP → Folha: Conecta × Portte.
    "checar_holerite_de_mes_futuro.py": lambda s: _n(r"^TOTAL:\s*(\d+) holerite\(s\) impossível\(eis\)", s),
    # Desde 13/09/2026 o pull do Sólides/Tangerino está desligado (decisão do Jordan):
    # quem não bate pelo app não tem ponto NENHUM. Eram 7 no dia do desligamento — 4 que
    # nunca usaram e 3 que usavam e pararam em agosto. Alvo: 0.
    "checar_pessoa_fora_do_app_de_ponto.py": lambda s: _n(r"^TOTAL:\s*(\d+) pessoa\(s\) sem ponto pelo Conecta PRO", s),
    # ASO que não prova exame: 96 dos 97 assinados pelo mesmo médico, 3 datas, zero
    # documento anexado, todos carregados em 16/03/2026. Os "25 vencidos" da tela saem daí.
    "checar_aso_sem_lastro.py": lambda s: _n(r"^TOTAL:\s*(\d+) ASO\(s\) sem lastro", s),
    # Selfie da batida: o app tirava, mandava, e o construtor do PunchService não passava
    # o campo — 829 batidas de 09/2026 com facial e GPS e ZERO com foto. Sem ela não dá
    # para ver farda, barba nem se a pessoa está no posto. Conta só a partir de 14/09.
    "checar_batida_sem_foto.py": lambda s: _n(r"^TOTAL:\s*(\d+) batida\(s\) sem foto", s),
    # O INVERSO do botão morto: rota que ESCREVE e nenhuma tela chama — o mapa do que
    # obriga o dono a ir ao terminal (pedido do Jordan, 13/09/2026). Estreia em 338.
    # Pesado (constrói os 32 módulos + varre os builders): ~3 min.
    "checar_capacidade_sem_botao.py": lambda s: _n(r"^TOTAL:\s*(\d+) capacidade\(s\) sem botão", s),
    # Origem do sino com volume e ninguém abre — 5.387 avisos em 30 dias, 19 abertos (06/09).
    "checar_sino_surdo.py": lambda s: _n(r"^TOTAL:\s*(\d+) origem", s),
    # Rotina que martela o provedor de LLM falhando: 30.800 chamadas/dia com 0 ok (07/09).
    "checar_llm_martelando.py": lambda s: _n(r"^TOTAL:\s*(\d+) origem", s),
    # Tela do redesign que nenhum oráculo nem regra proativa cita (o "mapa do não-vigiado").
    # Pesado (constrói os 32 módulos): ~5 min.
    "checar_nao_vigiado.py": lambda s: _n(r"^TOTAL:\s*(\d+) tela", s),
    # Endpoint que uma tela do redesign chama e o app não tem (ou não tem com aquele método).
    # 3 na estreia (07/09/2026): {ano}/{mes} e {client_id} literais + rota que nunca existiu.
    "checar_botao_morto.py": lambda s: _n(r"^TOTAL:\s*(\d+) botão", s),
    # ── 13/09/2026: os nove caçadores das 10 frentes de paridade com a DGX. Cada um nasceu
    # junto com a frente que o mediu; a linha canônica foi lida do CÓDIGO de cada script, não
    # do relatório (relatório envelhece, `print` não).
    #
    # Módulo com código e ZERO rotas montadas. Nasce em 4 e só cai por DECISÃO do dono
    # (ligar ou aposentar) — a frente 9 provou que os 4 foram podados de propósito em 08/09
    # e que "ligar" o bidding significa restaurar 97 handlers e 14 defeitos revisados.
    "checar_modulo_morto.py": lambda s: _n(r"^TOTAL módulos mortos:\s*(\d+)", s, "TOTAL módulos mortos: 0"),
    # Pessoa com batida no mês e SEM linha AFD desde o corte (13/09). É a medida de que o
    # ponto tem instrumento legal — não de que o instrumento foi constituído (isso é o INPI).
    "checar_ponto_sem_instrumento.py": lambda s: _n(r"^TOTAL pessoas sem instrumento: (\d+)", s),
    # Batida offline com relógio do aparelho fora do limite, duplicata por chave, ou dia com
    # taxa facial 100% (taxa perfeita = a comparação não ocorreu).
    "checar_batida_offline_suspeita.py": lambda s: _n(r"^TOTAL batidas offline suspeitas: (\d+)", s),
    # Contrato com preço alterado por rotina e sem aditivo assinado. Alvo permanente: 0 —
    # reajuste de benefício vira PEDIDO na Central, nunca preço.
    "checar_repasse_sem_aditivo.py": lambda s: _n(r"^TOTAL repasses sem aditivo:\s*(\d+)", s),
    # Arma/colete alocado sem número de série ou sem responsável. Contador sem série não é
    # controle: não responde "onde está a arma 3".
    "checar_arma_sem_serie.py": lambda s: _n(r"^TOTAL armas sem série/responsável: (\d+)", s),
    # Item da fila offline da ronda parado há mais de 24h no aparelho. Mede o RASTRO da fila
    # (o servidor não enxerga o que não subiu).
    "checar_fila_offline_estourando.py": lambda s: _n(r"^TOTAL itens offline atrasados: (\d+)", s),
    # Veículo sem leitura de KM no período: sem isso o painel de manutenção marca TODOS como
    # vencidos e é ignorado em uma semana.
    "checar_frota_sem_km.py": lambda s: _n(
        r"^TOTAL veículos sem KM no período: (\d+)", s, "TOTAL veículos sem KM no período: 0"
    ),
}

#: Estáticos: rodam no HOST, onde os caminhos do repositório existem. Pôr o
#: `checar_repositorio` no container fez ele achar 0 — a raiz lá é /app, não
#: /opt/conecta-pro/backend, e "zero achados" por caminho errado é o pior tipo de verde.
CACADORES_HOST = {
    # A data que gravamos do banco é a que o BANCO enxerga, no fuso de Manaus. A Cora devolve
    # `createdAt` em UTC e recorta o extrato dela pela data LOCAL — tudo entre 20h e meia-noite
    # daqui caía no dia seguinte nos nossos livros. Medido em 18/09/2026: 77 de 486 lançamentos
    # (15%) no dia errado, R$ 110.057,03, inclusive um débito de R$ 27.000. Corrigidos 76; o
    # que sobra CRUZA A VIRADA DO MÊS (R$ 200 de 01/08 para 31/07) e mexe em competência
    # apurada — dívida conhecida, com dono, esperando decisão. CONTADA: acusa se CRESCER.
    "checar_data_do_banco_no_fuso.py": lambda s: _n(r"^TOTAL: (\d+) lançamento\(s\) com data fora do fuso", s),
    # O mesmo `:p` em `SET col = :p` e em `CASE WHEN :p = ...` vira UM `$1` com dois tipos
    # deduzidos (varchar × text) e o asyncpg recusa a query inteira — 500 mudo. Derrubou o
    # `executar_lote_inter` em 22/09 e o webhook da Cora (efetivada/cancelada) desde sempre;
    # os dois provados por `prepare()` no sandbox em 24/09/2026. Cura: CAST em todo uso.
    "checar_parametro_ambiguo.py": lambda s: _n(r"^TOTAL parâmetros ambíguos: (\d+)", s),
    # Escala 12x36 lançada na paridade OPOSTA às batidas: a grade diz dia sim/dia não nos ímpares
    # e a pessoa bate nos pares. Não é defeito de código — é a grade no dia errado, e faz o ponto,
    # o benefício e a cobertura mentirem juntos. Achado em 24/09/2026 ao corrigir o plantão
    # noturno (frentes V1/W1): 4 casos (RILEM 53/53 batidas fora, ADEILSON 93%, MAIARA 100%).
    # CONTADA: dívida de cadastro com dono — acusa se CRESCER.
    "checar_escala_paridade.py": lambda s: _n(r"^TOTAL escalas na paridade errada: (\d+)", s),
    # A casa tem OITO pareadores de batida (varredura estática da frente X4, 24/09/2026). Três já
    # falam a mesma língua (folha, fechamento, tela do DP) desde V1/W1/X4; o espelho LEGAL — o PDF
    # que o colaborador assina e vai para a homologação — ainda tem régua própria. Este oráculo
    # afirma que os três casados continuam casados e que espelho assinado não é reescrito.
    "test_oraculo_x4_pareador_unico.py": lambda s: _n(r"^TOTAL desvios: (\d+)", s),
    # O espelho LEGAL — o PDF que o colaborador assina — entrou na régua única em 24/09 (Y1).
    # Antes, ele datava o turno noturno no dia seguinte e acusava FALTA em dia trabalhado.
    # Espelho assinado é imutável: o oráculo relê os 19 protegidos e exige 0 reescritos.
    "test_oraculo_y1_espelho_regua.py": lambda s: _n(r"^TOTAL desvios: (\d+)", s),
    # As duas réguas de pareamento discordam em 133,27 h (59 pessoa×dia) por causa do DADO, não
    # do código: tipo de batida errado no aparelho, batida duplicada, virada de meia-noite. A
    # trava conta as divergências — cair é bom, crescer é a operação piorando.
    "test_oraculo_y2_direcao_batida.py": lambda s: _n(r"^TOTAL desvios: (\d+)", s),
    # O skill-retrieval está ENCOLHENDO o prompt e não escondendo as nossas skills. Ele tem
    # duas fases que puxam o custo em direções opostas (compacta / injeta); se a compactação
    # parar, o plugin passa a CUSTAR em silêncio — medido: 26.793 com a adaptação da casa
    # removida contra 26.569 sem plugin nenhum. Confere a adaptação lendo o arquivo instalado,
    # porque de dentro de um processo novo ela é invisível (ordem de import).
    "checar_hermes_skill_retrieval.py": lambda s: _n(
        r"^TOTAL: (\d+) falha\(s\) no skill-retrieval", s, "TOTAL: 0 falha"
    ),
    # O Hermes só enxerga, do conector `conecta`, o que CONSEGUE executar. Medido em
    # 18/09/2026 no dump real: o catálogo era 83% do payload de cada turno, e das 146
    # ferramentas daquele conector 142 recusavam SEMPRE (ele exige identidade por chamada, que
    # o Hermes não sabe mandar). Limitar o `include` às 4 que executam cortou 46.843 → 26.540
    # tokens de entrada por turno. Acusa nos DOIS sentidos: lista vazia (volta o desperdício) e
    # lista defasada (vira parede quando alguém liberar mais acesso).
    "checar_hermes_so_ve_o_que_executa.py": lambda s: _n(
        r"^TOTAL: (\d+) divergência\(s\) entre o que o Hermes", s, "TOTAL: 0 divergência"
    ),
    # O que está no CONTRATO foi para a NOTA? O dono explicou em 18/09/2026 por que o MIRANTE
    # não fechava — «tiramos a jardinagem» —, e a nota sabia disso desde agosto enquanto o
    # contrato, o MRR e o contas a receber seguiam com os R$ 1.500 por mais de um mês, sem
    # nada acusar. Na estreia: 7 clientes batendo ao centavo, 4 divergindo, R$ 39.338,33 de
    # serviço prestado e NÃO faturado. HOST porque fala com o postgres por docker exec.
    "checar_contrato_vs_nota.py": lambda s: _n(
        r"^TOTAL: (\d+) cliente\(s\) com contrato e nota divergentes", s, "TOTAL: 0 cliente"
    ),
    # Tool do MCP que ESCREVE e não se declara escritora: a classe `read` é a que o
    # `gate_propose` deixa passar sem humano. Órfã desde que nasceu; ligada em 17/09/2026.
    "checar_mcp_declara_escrita.py": lambda s: _n(r"^TOTAL tools de escrita sem declarar: (\d+)", s),
    # Afastamento aberto e cadastro dizendo outra coisa. A Cintia estava afastada desde 21/05
    # (acidente de trajeto, CAT transmitida) e `employees.status` dizia 'ativo' havia quatro
    # meses — e é pelo CADASTRO que todo disparo decide para quem manda: o lembrete de ponto
    # exige status='ativo' e a alcançava, com a última batida dela em 29/03. Acusa os dois
    # lados: afastado que o cadastro ignora, e cadastro afastado sem registro aberto.
    # Container de produção rodando imagem SEM TAG ou AUSENTE do daemon. Em 19/09/2026 os 9
    # containers (backend + 8 workers) rodaram por horas uma camada cuja tag tinha sumido, e
    # `checar_drift_workers.sh` disse "sem drift" — ele compara os containers ENTRE SI, então
    # todos errados juntos passa. Quem acusou foi `checar_mcp_tools`, por acidente: ele lê uma
    # peça de parede que por acaso mora no backend. Os 8 workers não tinham vigia nenhum.
    # Separa os dois estados de propósito: SEM TAG é drift recuperável, AUSENTE é recriar que
    # falha — e `docker images -q` não lista imagem sem tag, o que já me fez ler um pelo outro.
    "checar_imagem_sumida.py": lambda s: _n(
        r"^TOTAL: (\d+) container\(es\) rodando imagem sem tag ou ausente", s, "TOTAL: 0 container"
    ),
    "checar_afastamento_vs_cadastro.py": lambda s: _n(
        r"^TOTAL: (\d+) cadastro\(s\) em desacordo", s, "TOTAL: 0 cadastro"
    ),
    # Conta ativa de quem não trabalha mais aqui. Nasceu do print do Antônio Carlos com o app
    # logado na conta da Graciene (17/09/2026): puxando o fio, 13 contas ativas de demitidos,
    # inativos e suspensos — 4 delas com e-mail @conectamais.pro, que o dono acreditava existir
    # só para ele e para a Pyetra. Desativar fecha o login e não apaga histórico nenhum.
    "checar_acesso_de_quem_saiu.py": lambda s: _n(r"^TOTAL: (\d+) conta\(s\) ativa\(s\)", s, "TOTAL: 0 conta"),
    # Task agendada cujo `except Exception` loga e devolve normal: a task fica SUCCESS e o
    # task_falha (que só vê exceção) não avisa. Foi assim que o razão parou 27 dias (07/09/2026).
    "checar_beat_engole_falha.py": lambda s: _n(r"^TOTAL: (\d+) task\(s\) que engolem falha", s, "TOTAL: 0 task"),
    # Nasceu do MVP de fechamento de `services`: 4 de 6 rotas em 500 porque o controller
    # chamava método que o repositório nunca teve. 139 chamadas assim no sistema.
    # Lê a linha canônica TOTAL: soma as DUAS travas (método inexistente + forma errada).
    # A versão anterior lia só "N chamada(s)" e ignorava a trava de forma — teria deixado
    # passar exatamente os 2 casos que estouravam o dashboard de serviços.
    "checar_repositorio.py": lambda s: _n(r"^TOTAL:\s*(\d+)", s),
    # Espelho da de cima, do outro lado da parede: frontend chamando rota que o backend não
    # tem. Nasceu do mesmo MVP (slaService pedindo /services/sla onde existe /sla-configs).
    # 666 na estreia, 84 alcançáveis por tela — as 35 literais confirmadas 404 por HTTP.
    "checar_rotas_frontend.py": lambda s: _n(r"^TOTAL:\s*(\d+)", s),
    # Ideia do T1: contra qual fonte DE FORA cada número foi provado, e quando. Os outros
    # oráculos comparam exibido == banco — os dois lados nossos; se o banco estiver errado,
    # ficam verdes. Foi o caso do extrato (880 duplicatas, 94 sinais invertidos).
    "checar_oraculo_externo.py": lambda s: _n(r"^TOTAL:\s*(\d+)", s),
    # Tabela com 0 linhas: 463 de 686 em 06/09/2026. Nascer morto nunca acusou nada — agora
    # tabela nova sem dado é regressão. Host porque cruza com o log do nginx.
    "checar_uso_real.py": lambda s: _n(r"^TOTAL:\s*(\d+) tabela", s),
    # Registro criado DEPOIS do disparo externo (a cotação de 31/08). AST no host.
    "checar_irreversivel.py": lambda s: _n(r"^TOTAL:\s*(\d+) fun", s),
    # Verdade de domínio curada × código × banco × vigência. Nasceu pegando FAIXAS_INSS_2026
    # com a tabela de 2024 num arquivo e a de 2026 no outro (06/09/2026).
    "checar_dominio.py": lambda s: _n(r"^TOTAL:\s*(\d+) diverg", s),
    # O que está no ar por docker cp (docker diff). Cai a zero sozinho depois do bake.
    "checar_bake_pendente.py": lambda s: _n(r"^TOTAL:\s*(\d+) arquivo", s),
    # ── 13/09/2026, frente 4. HOST os dois: o primeiro bate por HTTP na porta do backend
    # (QA_BASE, default 8081) e o segundo varre o REPOSITÓRIO cruzando com o information_schema
    # — dentro do container a raiz é /app e a varredura voltaria 0, que é o pior tipo de verde.
    #
    # Tela do redesign acima do teto de tempo (QA_TETO_S, default 3s). Tela que demora é tela
    # que o supervisor abandona.
    "checar_tela_lenta.py": lambda s: _n(r"^TOTAL telas lentas: (\d+)", s, "TOTAL telas lentas: 0"),
    # `AT TIME ZONE 'America/Manaus'` aplicado direto a coluna `timestamp without time zone`
    # que guarda UTC: SOMA 4h em vez de subtrair. Nasce em 3 dívidas reais fora do ponto
    # (financial_pagamentos_pj.updated_at e opportunities.updated_at).
    "checar_at_time_zone_sem_fuso.py": lambda s: _n(
        r"^TOTAL conversões erradas: (\d+)", s, "TOTAL conversões erradas: 0"
    ),
    # ── 15/09/2026, vídeo errodp.mp4. O bake do backend de 00:47 passou a emitir `fieldsRef` e
    # `verDaLinha` no contrato das telas; o frontend que lê essas chaves ficou compilado no host
    # e não foi publicado. As 29 telas do redesign morriam em «Algo deu errado» — a Pyetra
    # reportou as duas que tentou abrir. Backend 200 nos dois lados; o erro era só no navegador.
    # HOST porque precisa falar com os DOIS containers: a API de um e o bundle publicado do outro.
    "checar_contrato_front_back.py": lambda s: _n(r"^TOTAL:\s*(\d+) chave", s),
    # ── 15/09/2026. O Jordan abriu a lista de pagamento dos diaristas e disse «fora do padrão»:
    # um nome em caixa mista no meio de 28 em CAIXA ALTA, porque `criar_diarista` gravava a
    # caixa como a pessoa digitou. Cosmético — mas o caçador vigia junto o que não é: diarista
    # que trabalhou no mês e está sem CPF ou sem PIX não entra no lote e some da lista sem nada
    # apitar. HOST: fala com o postgres por docker exec.
    "checar_diarista_impagavel.py": lambda s: _n(r"^TOTAL:\s*(\d+) diarista", s),
    # ── 22/09/2026. No VT+VR alguns receberam em banco que não usam (a da Graciene caiu em
    # conta negativa) e o Jordan mandou revisar tudo antes do adiantamento. Sete defeitos —
    # dois em gente que ia receber naquele dia: telefone gravado com tipo CPF. E um PJ com o
    # próprio telefone sem +55 etiquetado como CPF: nem passa no dígito verificador, nunca
    # chegaria. A API do Inter NÃO consulta DICT (404 medido), então a prova de destino só
    # vem do histórico de pagamento, onde o banco devolve `recebedor.nome`. HOST: postgres.
    "checar_chave_pix.py": lambda s: _n(r"^TOTAL chaves PIX com defeito:\s*(\d+)", s),
    # ── 22/09/2026. O Jordan, três vezes no mesmo dia: «tudo o que estamos fazendo pelo
    # terminal tem que funcionar no frontend, não podemos ficar reféns do terminal». Os
    # três defeitos daquele dia tinham a mesma forma e nenhum caçador pegava: tela servida
    # fora de todo menu, e ação que nenhuma tela chama. O `checar_capacidade_sem_botao`
    # EXCLUI /redesign/action/ dizendo «ela É a porta» — e não é. HOST: precisa da API e
    # dos JSONs de menu do frontend ao mesmo tempo.
    "checar_tela_sem_porta.py": lambda s: _n(r"^TOTAL:\s*(\d+) sem porta", s),
}


#: Roda no HOST. Os caçadores precisam do BANCO e do código como está no container; o
#: caçador do arsenal precisa do REPOSITÓRIO e do crontab, que só existem no host. Misturar
#: os dois ambientes foi o primeiro erro deste script: dentro do container o ARSENAL_SKILLS
#: "não existia" e as contagens saíam diferentes (27 em vez de 40) porque a raiz é outra.
_EXEC_CONTAINER = ["docker", "exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend", "python3", "/app/scripts/qa/"]


#: Travas de SIM/NÃO: não contam dívida, passam ou reprovam. Ligadas pelo EXIT CODE e nunca
#: por parser da saída — em 24/08/2026 seis medições por regex sobre texto erraram nos dois
#: sentidos no mesmo dia (três inflaram, três zeraram). Formato de saída muda; exit code é
#: comportamento. É a mesma troca que a condição 2 do gate do Bartolo fez: de grep para sonda.
#: (onde, o que impede, teto em segundos). O teto é POR TRAVA: a de desmonte re-executa cada
#: oráculo que escreve (60+, até 420s cada) e estourava o teto único de 15min todo dia —
#: "NÃO VERIFICADO" permanente é o mesmo que não ter trava.
TRAVAS_BINARIAS = {
    # As três do conector MCP, órfãs desde que nasceram e ligadas em 17/09/2026. Binárias
    # porque não há dívida a contar: ou o changelog conta a verdade, ou não; ou o container
    # roda a imagem da tag, ou está à deriva; ou os 21 aceites passam, ou não.
    #
    # A de imagem é irmã do `checar_drift_workers`, e pela mesma razão: `docker cp` e build
    # avulso deixam container rodando imagem que a tag já não aponta.
    "checar_changelog_mcp.py": ("host", "changelog do MCP dizendo ao agente que nada mudou", 300),
    "checar_imagem_mcp.py": ("host", "conector rodando imagem diferente da tag", 300),
    # Só `test_aceites_cowork.py`: o `test_regressao_mcp` é do `checar_etiqueta_de_risco`
    # (glob de mcp-server/test_*.py), e ele ESCREVE no sandbox a cada execução.
    "checar_regressao_mcp.py": ("host", "os 21 aceites do prompt do conector", 900),
    "checar_beats.py": ("container", "rotina agendada que roda e NÃO PRODUZ", 900),
    "checar_periodo_do_servidor.py": ("container", "competência/data vinda do MODELO e não do servidor", 900),
    # CONTAINER, não host: ela varre /app/scripts/orq. No host esse caminho não existe, o
    # glob volta vazio e ela imprime "0 · 0 · 0 · 0" com exit=0 — verde por caminho errado,
    # que é o pior tipo de verde e já mordeu aqui (o checar_repositorio achava 0 no container
    # pelo motivo espelhado). Liguei errado na primeira vez; a saída zerada denunciou.
    "checar_desmonte_comportamento.py": ("container", "oráculo que escreve em produção e deixa linha", 5400),
    # Motor responde 200 e não produz frase. Existia desde 24/08 e nenhum caminho a invocava —
    # a própria trava de órfãs acusou por dias e ninguém ligou (06/09/2026).
    "checar_sucesso_vazio.py": ("container", "o motor do chat devolve 200 sem frase", 300),
    # `from X import Y` com X apagado do disco: o servidor ou o celery cai no BOOT, um bake
    # por vez (07/09/2026: analytics, ai/contract_analysis, ai/signature). Lê o disco: host.
    "checar_import_orfao.py": ("host", "import de topo para módulo que não existe mais", 300),
    # Cobertura rotas × telas (08/09/2026): toda rota montada precisa de chamador — redesign, interno
    # (MCP/Hermes/tasks/robôs/cron), alias, externo (webhook) ou dono. Fechou em 0 · 0 com 1220 rotas;
    # rota nova sem tela volta a acusar aqui. Leva ~1 min (enumera as rotas dentro do container).
    "checar_cobertura_rotas.py": (
        "host",
        "rota montada sem chamador no redesign nem interno (nenhum/classico > 0)",
        300,
    ),
    # A inversa (sugestão da auditoria t6, 08/09): "toda chamada tem rota?" — varre frontend/src e reprova chamada
    # alcançável pelo redesign (grafo de imports a partir das raízes do redesign/apps vivos) a rota que não existe.
    # Foi assim que apareceram 14 rotas apagadas por veredito errado (portal do funcionário, sino).
    "checar_chamadas_sem_rota.py": (
        "host",
        "chamada do frontend alcançável pelo redesign a rota que o backend não tem",
        900,
    ),
    # `docker cp` copia, nunca apaga: handler apagado do repositório ficou no container e as duas travas acima mediram
    # um fantasma (0 · 0) até o bake de 09/09 reconstruir a imagem e o 404 aparecer no layout raiz.
    "checar_fantasmas_container.py": (
        "host",
        "arquivo .py no container que o repositório não tem (hot-copy não apaga)",
        300,
    ),
    # Oráculo no git não protege ninguém; oráculo na imagem protege. A varredura da meia-noite roda DENTRO do
    # container: hoje, 3 vezes, um arquivo ficou no disco e fora da imagem porque o bake fechou o contexto antes.
    "checar_oraculos_no_container.py": (
        "host",
        "oráculo ou caçador que existe no disco e NÃO roda (fora do container)",
        300,
    ),
    # Registro do servidor vazio ou encolhido (rotas, tools, executores pela guarda, regras,
    # beats, builders) — a família do "código desligado". Guarda a última contagem no banco.
    "checar_registros_servidor.py": ("container", "registro VAZIO ou que ENCOLHEU no processo do servidor", 600),
    # As travas do conector MCP existiam desde 23/08 e NINGUÉM as rodava (medido em 11/09, ao
    # abrir o escopo `pessoas` para o Hermes). `test_read_nao_escreve` estava verde com 13
    # ferramentas etiquetadas `read` fazendo PUT/PATCH/DELETE — `read` é a classe que o
    # gate_propose deixa passar sem humano. Este caçador só as EXECUTA; a régua fica junto do
    # código que ela vigia.
    "checar_etiqueta_de_risco.py": (
        "host",
        "trava do conector MCP falhando (etiqueta de risco, manifesto, identidade)",
        300,
    ),
    # O conector serve o que DIZ que serve? Medido pela rota (`tools/list`), não pelo log —
    # que anunciou "42 de 254" por 19 dias enquanto servia 266, porque `remove_tool` não
    # existe no fastmcp 4.0.3 e o `except: pass` engolia (11/09/2026).
    "checar_escopo_mcp.py": ("host", "conector MCP servindo ferramenta fora do escopo declarado", 300),
    # Ferramenta que existe no catálogo e ESTOURA ao ser chamada. `justificativas_ponto_pendentes`
    # nunca funcionou (rota devolve lista, anotação diz dict) e ninguém viu, porque nada a chamava.
    # Só chama leitura sem argumento obrigatório; recusa de parede não conta como defeito.
    "checar_tool_quebrada.py": ("host", "tool de leitura do MCP que estoura ao ser chamada", 900),
    # O telefone do funcionário existe no WhatsApp? Perguntado AO WhatsApp, um número por vez.
    # A casa nunca soube se a mensagem chegava: o envio para um JID inexistente registra
    # sucesso. Medido em 11/09 — 5 cadastros sem o nono dígito (a MEIRE entre eles) e 6 cujo
    # número não existe, dois deles com 13 lembretes de ponto cada, todos no vazio.
    "checar_telefone_funcionario.py": (
        "host",
        "telefone de funcionário malformado (mensagem da empresa não chega)",
        900,
    ),
}

#: ⚠️ `test_oraculo_todos_batem_ponto.py` NÃO entra aqui: oráculo roda na varredura da meia-noite
#: (`scripts/orq`, glob automático), e repetir a chamada faria o mesmo vermelho tocar duas vezes.
#: Fica registrado aqui só para quem vier procurar: a pergunta "todo mundo consegue bater?" é
#: vigiada, e é vigiada lá.

#: Critérios de aceite por módulo. Cada um imprime ✅/❌ por condição; o que entra na base é
#: a CONTAGEM de ✅ — condição vermelha por decisão humana pendente (destinatário, crédito de
#: LLM) é estado conhecido, não regressão. Acusa só quando o número CAI. Semanal (domingo)
#: porque são pesados e alguns exercitam um turno real do agente.
GATES = {
    "fechado_bartolo.py": ("host", 1200),
    "fechado_contratos.py": ("host", 1200),
    "fechado_fiscal.py": ("host", 1200),
    "fechado_gedeon.py": ("container", 1200),
    "fechado_financeiro.py": ("container", 1500),
    "fechado_operacional.py": ("container", 1200),
    "varredura_op_acoes.py": ("container", 900),
}

#: Órfã DECLARADA: existe, ninguém roda, e está escrito por quê e de quem é. Exceção com dono
#: e motivo — não gaveta. Sem esta lista o detector abaixo reprova, que é o correto: trava que
#: ninguém invoca é exatamente a doença que o arsenal veio curar (o `tool_risk_manifest`
#: classificava 254 tools e nenhum código o consultava).
ORFAS_DECLARADAS: dict[str, str] = {
    # `checar_desmonte_oraculos.py` foi APAGADA em 24/08/2026, não promovida a contada: ela
    # acusou 26 oráculos e acertou 1 (96% de falso positivo). Dar linha de base a um detector
    # assim institucionaliza o ruído em vez de removê-lo. Quem mede desmonte agora é
    # `checar_desmonte_comportamento.py`, que EXECUTA em vez de ler o fonte.
    "provar_desmonte.py": "utilitário com argumentos (<oráculo> <tabela>): prova o desmonte "
    "de UM oráculo recém-escrito. Invocado à mão pela skill "
    "oraculo-conecta/entregue-de-verdade. Dono: quem escreve oráculo "
    "que escreve.",
    # Ferramenta de MÃO da esteira de botões (14/09/2026). Fica de fora da varredura diária
    # DE PROPÓSITO: ela pergunta "lista sem forma de criar/mexer?" e é ruidosa por
    # construção — o Portal do Funcionário é leitura por natureza e ela acusa 11 lá. Sino
    # que toca todo dia é sino que ninguém lê. Quem mede a esteira na varredura é
    # `checar_capacidade_sem_botao.py`, que pergunta o inverso e tem alvo acionável.
    # Dono: quem estiver trabalhando a esteira do Jordan (ver o relatório de 14/09).
    "checar_acao_faltando.py": "ferramenta de mão da esteira de botões: lista sem forma de "
    "criar/mexer. Ruidosa por construção (tela de leitura "
    "aparece como achado) — por isso não entra na diária. "
    "Dono: quem trabalha a esteira.",
}

#: Prefixos que contam como TRAVA neste diretório. `fechado_*` e `varredura_*` ficaram fora
#: do glob até 06/09/2026 — cinco critérios de aceite executáveis, nenhum caminho invocando,
#: e o detector de órfãs sem enxergá-los: ponto cego do próprio vigia.
_PREFIXOS = ("checar_", "cacar_", "fechado_", "varredura_", "provar_")


def _travas_no_disco() -> set[str]:
    return {p.name for p in AQUI.glob("*.py") if p.name.startswith(_PREFIXOS)}


def _cmd(script: str, onde: str) -> list[str]:
    return (
        [sys.executable, str(AQUI / script)]
        if onde == "host"
        else _EXEC_CONTAINER[:-1] + [_EXEC_CONTAINER[-1] + script]
    )


def _rodar(script: str) -> tuple[int | None, str]:
    """(pistas, saída). pistas=None quando a saída não tem a linha canônica: NÃO VERIFICADO."""
    if script in CACADORES_HOST:
        cmd, conta = _cmd(script, "host"), CACADORES_HOST[script]
    else:
        cmd, conta = _cmd(script, "container"), CACADORES[script]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)  # noqa: S603
    except subprocess.TimeoutExpired:
        return None, "(não terminou em 30min)"
    saida = r.stdout + r.stderr
    return conta(saida), saida


def _gate(script: str, onde: str, teto: int) -> tuple[int | None, int | None, str]:
    """(✅, ❌, última linha). None quando não rodou — gate que não responde não conta."""
    try:
        r = subprocess.run(_cmd(script, onde), capture_output=True, text=True, timeout=teto)  # noqa: S603
    except subprocess.TimeoutExpired:
        return None, None, f"não terminou em {teto // 60}min"
    saida = r.stdout + r.stderr
    ok, nok = saida.count("✅"), saida.count("❌")
    if ok + nok == 0:
        return None, None, (saida.strip().splitlines() or ["sem saída"])[-1][:100]
    return ok, nok, (saida.strip().splitlines() or [""])[-1][:100]


def _avisar_no_sino(falhou: list[str]) -> None:
    """Publica no sino reusando o caminho da varredura (dedup por dia já embutido)."""
    corpo = (
        "Trava mecânica acusou REGRESSÃO:\n- "
        + "\n- ".join(falhou)
        + "\n\nCódigo novo trouxe fabricação de valor ou lista literal que a coluna não "
        "tem. Rodar à mão:\n"
        "docker exec conecta-pro-backend python3 /app/scripts/qa/cacar_fabricacao.py"
    )
    cmd = _EXEC_CONTAINER[:-1] + [
        "/app/modules/notifications/tasks_oraculos.py",
        "--avisar",
        "Travas de QA: regressão",
        corpo,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
    print(f"  sino: {(r.stdout or r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr) else 'sem resposta'}")


def main() -> int:
    gravar = "--gravar" in sys.argv
    BASE.parent.mkdir(parents=True, exist_ok=True)
    base = json.loads(BASE.read_text()) if BASE.exists() else {}
    agora, falhou = {}, []
    _memo_falhas = base.pop("_falhas", {})
    base["_falhas"] = _memo_falhas  # só leitura aqui; regravada no fim

    for script in {**CACADORES, **CACADORES_HOST}:
        n, saida = _rodar(script)
        antes = base.get(script)
        if n is None:
            # Saída sem a linha canônica: o caçador NÃO respondeu. Não é zero — e a base não
            # se move. Foi assim que ela caiu a 0 em 23/08 e acusou regressão por dez dias.
            ultima = (saida.strip().splitlines() or ["sem saída"])[-1][:90]
            falhou.append(f"{script}: NÃO VERIFICADO (sem a linha canônica: {ultima}) — base intacta")
            print(f"  x {script}: NÃO VERIFICADO — {ultima}")
            continue
        agora[script] = n
        if antes is None:
            print(f"  {script}: {n} pista(s) — sem linha de base ainda")
            continue
        if n > antes and gravar:
            print(f"  {script}: {antes} -> {n}  (+{n - antes}, ACEITO como base por --gravar)")
        elif n > antes:
            falhou.append(f"{script}: {antes} -> {n} (+{n - antes} NOVA(s))")
            print(f"  x {script}: {antes} -> {n}  REGRESSÃO")
        elif n < antes:
            print(f"  {script}: {antes} -> {n}  (−{antes - n}, dívida caiu)")
        else:
            print(f"  {script}: {n} (estável)")

    # O caçador do arsenal não tem dívida aceitável: ou o documento confere, ou não confere.
    # Este roda no HOST mesmo: precisa de docs/, skills/_plugin e crontab.
    r = subprocess.run([sys.executable, str(AQUI / "checar_arsenal.py")], capture_output=True, text=True)  # noqa: S603
    if r.returncode != 0:
        falhou.append("checar_arsenal: o arsenal diverge do sistema")
        print("  x checar_arsenal: o arsenal diverge do sistema")
        print("\n".join("     " + ln for ln in r.stdout.splitlines() if ln.strip().startswith("x")))
    else:
        print("  checar_arsenal: confere")

    # A parede do agente: no git, na imagem e apontando para rota que existe. Também sem
    # dívida aceitável. Ligada aqui porque a lição do dia em que ela nasceu foi justamente
    # esta — o `tool_risk_manifest` classificava 254 tools e NINGUÉM o consultava. Trava que
    # ninguém roda é a mesma doença que ela veio curar.
    if gravar:
        # `--gravar` regrava a LINHA DE BASE: só os caçadores contados importam. As travas de
        # sim/não, os gates e a parede do agente não têm base — rodá-los aqui só atrasaria a
        # gravação (a de desmonte leva ~1h) e colidiria com a varredura da meia-noite.
        print("  (--gravar: travas binárias, gates e checar_mcp_tools pulados — não têm base)")
        r = subprocess.CompletedProcess([], 0, "", "")
    else:
        r = subprocess.run(  # noqa: S603
            [sys.executable, str(AQUI / "checar_mcp_tools.py")], capture_output=True, text=True, timeout=600
        )
    if r.returncode != 0:
        falhou.append(
            "checar_mcp_tools: a parede do agente está fora do git, fora da "
            "imagem, ou apontando para rota que não existe"
        )
        print("  x checar_mcp_tools: a parede do agente diverge")
        print("\n".join("     " + ln for ln in r.stdout.splitlines() if ln.strip().startswith("-")))
    else:
        print("  checar_mcp_tools: confere")

    # As travas de sim/não, pelo exit code.
    for script, (onde, oque, teto) in ({} if gravar else TRAVAS_BINARIAS).items():
        try:
            r = subprocess.run(_cmd(script, onde), capture_output=True, text=True, timeout=teto)  # noqa: S603
        except subprocess.TimeoutExpired:
            falhou.append(f"{script}: não respondeu em {teto // 60}min — NÃO VERIFICADO, não aprovado")
            print(f"  x {script}: não respondeu (NÃO VERIFICADO)")
            continue
        if r.returncode != 0:
            falhou.append(f"{script}: {oque}")
            print(f"  x {script}: {oque}")
            for ln in (r.stdout or r.stderr).splitlines()[-6:]:
                print("     " + ln)
        elif "NÃO VERIFICADO" in (r.stdout or ""):
            # exit 0 com "NÃO VERIFICADO" = a trava não teve o que medir (sem uso). Não é
            # "confere" — é o terceiro estado, dito de frente, sem reprovar.
            print(f"  ~ {script}: NÃO VERIFICADO (sem uso, nada a medir)")
        else:
            print(f"  {script}: confere")

    # ── a trava que vigia o próprio arsenal ────────────────────────────────────
    # Nasceu de uma medição em 24/08/2026: 12 travas no disco e QUATRO que nenhum caminho
    # invocava — inclusive a `checar_beats`, escrita no dia anterior justamente contra
    # "rotina que roda e não produz". Trava órfã é pior que trava ausente: ela dá a impressão
    # de cobertura que não existe, e o custo de escrevê-la já foi pago.
    orfas = (
        _travas_no_disco()
        - set(CACADORES)
        - set(CACADORES_HOST)
        - set(TRAVAS_BINARIAS)
        - set(GATES)
        - set(ORFAS_DECLARADAS)
        - {"checar_regressao.py", "checar_arsenal.py", "checar_mcp_tools.py"}
    )
    if orfas:
        falhou.append("trava órfã (existe no disco e nenhum caminho invoca): " + ", ".join(sorted(orfas)))
        print(f"  x arsenal: {len(orfas)} trava(s) órfã(s) — " + ", ".join(sorted(orfas)))
        print(
            "     Ligue em CACADORES/CACADORES_HOST (conta dívida) ou TRAVAS_BINARIAS "
            "(passa/reprova), ou declare em ORFAS_DECLARADAS com DONO e MOTIVO."
        )
    else:
        print(f"  arsenal: 0 trava órfã ({len(ORFAS_DECLARADAS)} declarada(s) com dono)")

    # ── gates semanais: critérios de aceite por módulo ─────────────────────────
    # A base guarda quantas condições ✅ cada gate tinha; acusa quando o número CAI. Sobe
    # sozinho quando melhora — conserto não exige cerimônia, retrocesso exige explicação.
    import datetime as _dt

    if "--gates" in sys.argv or (_dt.date.today().isoweekday() == 7 and not gravar):
        print("── gates semanais (critérios de aceite) ──")
        for script, (onde, teto) in GATES.items():
            ok, nok, ultima = _gate(script, onde, teto)
            chave = f"gate:{script}"
            if ok is None:
                falhou.append(f"{script}: gate NÃO VERIFICADO ({ultima}) — base intacta")
                print(f"  x {script}: NÃO VERIFICADO — {ultima}")
                continue
            antes = base.get(chave)
            agora[chave] = ok
            if antes is None:
                print(f"  {script}: {ok} ✅ / {nok} ❌ — sem linha de base ainda")
            elif ok < antes:
                falhou.append(f"{script}: {antes} → {ok} condições ✅ (RETROCEDEU {antes - ok})")
                print(f"  x {script}: {antes} -> {ok} ✅  RETROCESSO")
            else:
                print(f"  {script}: {ok} ✅ / {nok} ❌" + (f"  (+{ok - antes}, avançou)" if ok > antes else ""))

    def _melhorou(k: str, v: int) -> bool:
        return v > base.get(k, -1) if k.startswith("gate:") else v < base.get(k, 10**9)

    if gravar or any(_melhorou(k, v) for k, v in agora.items()):
        # Dívida baixa sozinha; gate sobe sozinho. O contrário exige --gravar. Chave que não
        # foi VERIFICADA nesta rodada fica com o valor que tinha — nunca some, nunca zera.
        nova = {k: v for k, v in base.items() if k != "_falhas"}
        nova["_falhas"] = base.get("_falhas", {})
        for k, v in agora.items():
            if gravar:
                nova[k] = v
            elif k.startswith("gate:"):
                nova[k] = max(v, base.get(k, v))
            else:
                nova[k] = min(v, base.get(k, v))
        BASE.write_text(json.dumps(nova, indent=2) + "\n")
        print(f"  linha de base atualizada: {nova}")

    # O sino só toca com NOVIDADE: trava que passou a falhar, ou que voltou a passar. A mesma
    # falha repetida fica no log e volta ao sino toda segunda. Sem isto, "0 -> 25 REGRESSÃO"
    # tocou dez noites seguidas (28/08–06/09/2026) e ninguém abriu nenhuma.
    import datetime as _dt2

    chaves_agora = {f.split(":")[0] for f in falhou}
    chaves_antes = set((base.get("_falhas") or {}).keys())
    hoje = _dt2.date.today().isoformat()
    base_falhas = {k: (base.get("_falhas") or {}).get(k, hoje) for k in chaves_agora}
    try:
        atual = json.loads(BASE.read_text()) if BASE.exists() else {}
        atual["_falhas"] = base_falhas
        BASE.write_text(json.dumps(atual, indent=2) + "\n")
    except OSError as exc:
        print(f"  (não gravei _falhas na base: {exc})")
    novidade = chaves_agora != chaves_antes
    if chaves_antes - chaves_agora:
        print(f"  voltaram a passar: {', '.join(sorted(chaves_antes - chaves_agora))}")
    if falhou and (novidade or _dt2.date.today().isoweekday() == 1):
        # Sem isto a trava vira log que ninguém lê: o alerta do sino saía só da varredura de
        # oráculos, e regressão de fabricação ficava em /var/log esperando alguém abrir.
        _avisar_no_sino(
            [
                f + (f"  (desde {base_falhas.get(f.split(':')[0])})" if f.split(":")[0] in chaves_antes else "  NOVA")
                for f in falhou
            ]
        )
    elif falhou:
        print("  sino: sem novidade desde a rodada anterior — em silêncio (volta na segunda)")
    if falhou:
        print("\nREGRESSÃO — código novo trouxe fabricação ou vocabulário fantasma:")
        for f in falhou:
            print(f"  {f}")
        print(
            f"\nConserte, ou (se for dívida aceita) suba a base com --gravar e escreva a "
            f"decisão na mensagem do commit — a base mora em {BASE}, fora do git de "
            f"propósito. Deixar a dívida crescer tem que ser decisão escrita."
        )
        return 1
    print("\nsem regressão")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
