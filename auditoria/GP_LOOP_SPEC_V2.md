# GP_LOOP — Spec v2.1 (loops aninhados com oráculo em todo nível)
*Base: o design do diálogo (v1). v2 = v1 + 7 enxertos. v2.1 = + prompt de diagnóstico read-only fundido no Item −1.*
*Regra: onde v1 acertou, não toquei. Cada linha nova traz `# [ENXERTO N]`.*
*"Loop perfeito" = v1 (o que funciona) + os 7 enxertos + diagnostica-antes-de-agir com gate humano no mapa.*

---

## CHANGELOG v1 → v2 (rastreabilidade dos 7 enxertos)
| N | Enxerto | Onde entra | Gravidade |
|---|---|---|---|
| 1 | Consolidação de arquitetura (1 bus, 1 motor/domínio) **antes** do item 0 | **Item −1** (novo) | 🔴 estrutural |
| 2 | Estado derivado do banco (não JSON forjável) + contract-test nas arestas | Nível 0 + Nível 1 | 🔴 estrutural |
| 3 | Cálculo cego **permanente** entre iterações | Nível 2 / EXECUTOR | 🟡 oráculo |
| 4 | Fonte legal certificada (CCT/tabelas hash-locadas) | **Item −0.5** (novo) | 🟡 oráculo |
| 5 | Reconciliação de **input** antes de comparar saída | Nível 2 / gate FOLHA | 🟡 oráculo |
| 6 | Mapa de cobertura do golden set (o que Domínio NÃO cobre) | **Item 0.5** (novo) | 🟡 oráculo |
| 7 | Adversarial semeado da taxonomia real S1–S7 | Nível 2 / ADVERSARIAL | 🟢 força |
| 8 | **Diagnóstico read-only ANTES de consolidar** + gate humano no mapa (FASE A→B) | **Item −1** | 🔴 anti-hipótese |

**Mantido de v1 sem mudança:** hash da certificação; ordem produtor→consumidor; humano como certificador permanente; 3 papéis (executor/adversarial/humano) nunca no mesmo ator; break humano no Nível 0; adversarial com contexto limpo + lista de ataques; trava de fase sombra/corte; não redesenhar navegação (§13.2).

---

## INVARIANTES GLOBAIS (valem em todo nível — se um quebra, é teatro)
```
I1  O ator que CALCULA nunca é o que CERTIFICA nem o que REFUTA.        (3 papéis)
I2  Nenhum gate lê o gabarito antes de produzir o que o gabarito julga. (cegueira)
I3  Todo "verde/certificado" é um FATO no banco (linha + hash), nunca
    um adjetivo num arquivo que o agente escreve.                        [ENXERTO 2]
I4  Toda referência usada como verdade (golden set, tabela legal, contrato
    de evento) é um artefato VERSIONADO e hash-locado — muda → expira.   [ENXERTO 4]
I5  O estado do loop é DERIVÁVEL (reconstruível do git + banco + testes).
    Perder o arquivo de estado não perde o progresso.                    [ENXERTO 2]
```

---

# PRÉ-REQUISITOS (rodam antes do loop-mãe, em ordem)

## Item −1 — CONSOLIDAÇÃO DE ARQUITETURA   [ENXERTO 1] 🔴
*A síntese da auditoria disse "Fase 0 bloqueia tudo". v1 pulou. Sem isso, certificar um módulo verde carimba metade de um split-brain.*
*v2.1: dividido em **FASE A (diagnóstico read-only, gate humano no mapa)** → **FASE B (consolidação)**.*
*Princípio: não se consolida sobre a HIPÓTESE da auditoria — diagnostica-se a REALIDADE, você aprova o mapa, só então corrige. É o loop aplicado a si mesmo.*

### Item −1 · FASE A — DIAGNÓSTICO READ-ONLY  (prompt de terminal pronto pra colar)
> Não corrige, não mata motor, não commita. Mapeia e PARA, entregando o mapa pra você aprovar.

```
Você é engenheiro de software sênior no Conecta PRO. Missão: mapear, por rastreabilidade
real (código + banco + rotas), TODOS os motores de cálculo duplicados e TODOS os event-buses
do domínio de Gestão de Pessoas — para elegermos UM de cada e matar os mortos. Esta é a
FASE A: DIAGNÓSTICO READ-ONLY. Você NÃO corrige, NÃO mata motor, NÃO commita. Você mapeia e
PARA, entregando o mapa pra Jordan aprovar a consolidação. Token: STEP-0-ITEM-MENOS-1-DIAG.

PRINCÍPIOS (CLAUDE.md v2 em /opt/conecta-pro/CLAUDE.md — releia §13):
§13.1 Chesterton: NÃO assuma que os motores duplos existem como a auditoria teoriza.
  INVESTIGUE. Pode ser 1 motor, 2, ou 3. Pode ser que o "morto" ainda esteja vivo servindo
  uma tela. Descubra a realidade, não confirme a hipótese.
§13.5 Dado real: cada afirmação ancorada em arquivo:linha, rota viva, ou query. Se não achar,
  escreva "não existe", não "deveria existir".
§13.3 Escopo: SÓ diagnóstico de motores de cálculo + event-buses de people_management/folha.
  Read-only em tudo.
§13.6: nada é destruído nesta fase.

CONTEXTO (hipótese da auditoria, a CONFIRMAR ou REFUTAR): suspeita de motor duplo em DP/Folha
— motor A (CCT-2026, correto) e motor B (INSS-2024, errado) servindo telas diferentes; e
múltiplos event-buses (a síntese falou em "3 buses"). Sua missão é provar quantos REALMENTE
existem, qual cada tela/rota usa, e qual é o correto.

STEP 0 — ESTADO
0.1 git status (working tree limpo? se sujo de sessão anterior, reportar antes). git branch.
0.2 Confirmar: esta fase é 100% read-only. Nenhum comando abaixo escreve.

STEP 1 — MAPEAR MOTORES DE CÁLCULO DE FOLHA
1.1 Achar TODA função/classe que calcula INSS, IRRF, FGTS, líquido, verbas:
  grep -rn "def calcul\|def compute\|inss\|irrf\|fgts\|class.*Payroll\|class.*Folha\|class.*Calc" \
    backend/modules/people_management backend/modules/financial --include=*.py \
    | grep -iE "def |class " | head -60
1.2 Para cada motor candidato: qual tabela de alíquotas usa? (2024? 2026? CCT?) Ler o topo da
  função — as constantes/tabelas que ela referencia. Citar arquivo:linha.
1.3 QUANTOS motores distintos existem que calculam a MESMA coisa (ex: 2 funções que calculam
  INSS)? Listar cada um: arquivo:linha, tabela que usa, aparência de correto/desatualizado.
1.4 Veredito STEP 1: há motor duplicado? Quantos? Qual usa tabela atual (2026/CCT) e qual antiga (2024)?

STEP 2 — QUEM CHAMA CADA MOTOR (o ponto crítico — o "morto" pode estar vivo)
2.1 Para CADA motor do STEP 1: grep quem o importa/chama:
  grep -rn "<nome_da_funcao_ou_classe>" backend/ frontend/ --include=*.py --include=*.ts --include=*.tsx
2.2 Mapear: motor A é chamado por quais rotas/telas? motor B por quais?
2.3 PONTO DECISIVO: algum motor "candidato a morto" ainda é chamado por tela/rota viva? Se sim,
  matá-lo quebraria essa tela — precisa migrar a tela pro motor bom ANTES. Documentar cada chamador.
2.4 Veredito STEP 2: mapa {motor → quem chama}. O motor errado está órfão (seguro matar) ou vivo
  (precisa migrar chamadores antes)?

STEP 3 — MAPEAR EVENT-BUSES
3.1 grep -rn "publish\|emit\|dispatch\|event_bus\|EventBus\|\.send(\|celery.*delay\|signal" \
    backend/modules/people_management --include=*.py | grep -iE "bus|event|publish|emit|dispatch" | head -40
3.2 Quantos mecanismos DISTINTOS de evento existem? Listar cada um: arquivo:linha, como publica, quem consome.
3.3 O evento dp.funcionario.admitido (ou equivalente) — por qual bus passa? O GEDEON escuta o MESMO
  bus? Se publisher usa um e consumidor escuta outro, a aresta está morta. Verificar.
3.4 Veredito STEP 3: quantos buses, qual é o "vivo de verdade" (publisher E consumer no mesmo), quais mortos.

STEP 4 — RELATÓRIO (o mapa que Jordan aprova antes de qualquer correção)
Entregar, com evidência (arquivo:linha/rota/query):
- MOTORES: quantos, qual correto (tabela 2026/CCT), qual morto, quem chama cada um.
- Plano de consolidação PROPOSTO (não executado): eleger motor X, migrar chamadores Y e Z,
  quarentenar motor morto (não deletar — §13.6).
- BUSES: quantos, qual vivo, quais mortos, quais arestas quebradas por bus-mismatch.
- Plano de consolidação de bus PROPOSTO: eleger bus único, migrar publishers/consumers.
- RISCO de cada correção proposta (o que quebra se eu matar/migrar cada peça).
- Salvar em /opt/conecta-pro/auditoria/ITEM_MENOS_1_DIAG_<data>.md.
- Nota 0-10 de completude do diagnóstico.

PARE AQUI. NÃO execute a consolidação. Entregue o mapa + plano proposto. Jordan aprova (ou
ajusta) antes da FASE B. Read-only o tempo todo.
```

### ── GATE HUMANO do Item −1 (só VOCÊ) ──
```
Você lê ITEM_MENOS_1_DIAG_<data>.md e decide, com o mapa REAL (não a hipótese):
  - qual motor por domínio é o eleito (pode divergir do palpite da auditoria)
  - qual bus é o eleito
  - aprova a ordem de migração dos chamadores vivos (o "morto" que está vivo migra ANTES de morrer)
Só depois do seu aval → FASE B. Sem mapa aprovado, FASE B não roda. (anti "consolidei sobre hipótese")
```

### Item −1 · FASE B — CONSOLIDAÇÃO  (só após o mapa aprovado)
```
função ITEM_MENOS_1_FASE_B(mapa_aprovado):
    # 1. EVENT-BUS ÚNICO (conforme o mapa, não a hipótese)
    confirmar o bus eleito no mapa; quarentenar (§13.6, não deletar) os mortos
    corrigir imports errados apontados no diagnóstico
    GATE: grep prova 0 referências vivas aos buses quarentenados
          + boot do backend limpo
          + 1 evento real percorre SÓ o bus eleito (traço no Redis)

    # 2. MOTOR ÚNICO POR DOMÍNIO (migrar chamadores vivos ANTES de quarentenar)
    para cada DOMÍNIO com motor duplicado no mapa:
        migrar cada chamador vivo (STEP 2 do diag) do motor perdedor → motor eleito
        quarentenar o motor perdedor (não deletar)
        GATE: o motor perdedor NÃO responde mais a nenhuma tela
              (grep de chamadas == 0 + E2E: a tela que usava o perdedor agora usa o eleito
               e retorna o MESMO número). Prova: dois endpoints, um valor.

    # invariante de saída: não existem 2 motores vivos calculando o mesmo domínio.
    persistir_no_banco(arch_decisions)   # [ENXERTO 2/I3] estado no banco, não em .md
```
**Por que tudo isso antes do item 0:** o gate de cálculo cego valida *um* motor. Ele é cego pro segundo motor mentindo ao lado. Diagnosticar (A), você eleger (gate), e eliminar o segundo (B) é pré-condição do gate ter sentido.

## Item −0.5 — REGISTRO DE FONTE LEGAL CERTIFICADA   [ENXERTO 4] 🟡
*"recalcular_pela_lei" precisa de uma lei que não seja a memória do agente.*
```
função ITEM_MENOS_0_5():
    criar tabela legal_reference (versionada, hash-locada):
       {tipo (inss|irrf|fgts|cct_vigilancia_2026|salario_familia|...),
        vigencia_inicio, vigencia_fim, valores(jsonb), fonte(PDF/URL da convenção),
        hash_conteudo, certificado_por, certificado_em}
    popular a partir das FONTES OFICIAIS (tabelas 2026, CCT vigilância AM 2026 — PDF)
    GATE: um humano do time (item 0 já dá a tela) CERTIFICA cada tabela
          contra o PDF oficial. Enquanto não certificada → cálculo que a usa
          fica AMARELO (não verde). A tabela é o oráculo; ela mesma tem oráculo (o PDF + humano).
    # fecha o buraco "cálculo cego e comparação erram juntos na mesma premissa".
```

## Item 0 — FEATURE DE CERTIFICAÇÃO (v1, endurecida)
*Mantida do v1 — tabela + tela de assinatura + hash de conteúdo. Ajuste único abaixo.*
```
função ITEM_0():
    [tudo do PROMPT 1 do v1: hr_certifications com hash, POST/PATCH certify/reject,
     GET fila, tela de assinatura respeitando os cards do print, E2E real, trava de perfil]
    CLASSE = CRUD_SIMPLES → gate normal (E2E + adversarial). Fecha rápido.
    AJUSTE v2: esta tabela é a ÚNICA fonte de "humano certificou".
       O GP_LOOP_STATE deixa de conter "CERTIFICADO_HUMANO" como valor escrito pelo agente;
       passa a PROJETAR o status a partir de hr_certifications + arch_decisions + testes.  [ENXERTO 2/I3]
```

## Item 0.5 — MAPA DE COBERTURA DO GOLDEN SET   [ENXERTO 6] 🟡
*51 holerites, 1 competência (03/2026), verba pobre. Cobre pouco. Mapear o que NÃO cobre.*
```
função ITEM_0_5():
    para cada CAMINHO de cálculo de folha
        (salario_base, INSS, FGTS, IRRF, 13º, férias, rescisão, adic_noturno,
         insalubridade, periculosidade, DSR, salário-família, VT/VR):
        cobre = existe no golden set Domínio linha que exercite esse caminho?
        registrar cobertura[CAMINHO] = COBERTO | NAO_COBERTO
    saída: mapa explícito. CAMINHO NAO_COBERTO → NÃO pode fechar por "bateu com Domínio"
           (não há gabarito) → cai em lei + certificação humana (amarelo até assinar).
    # impede o falso "folha validada" quando só base+INSS+FGTS de 1 mês tem gabarito.
```

---

# LOOP-MÃE (Nível 0) — GESTÃO DE PESSOAS → PRODUÇÃO
*Gate humano: VOCÊ. Sai quando os 8 cards sobrevivem à sua refutação.*
```
# PRÉ: ITEM_MENOS_1 ✔  ITEM_MENOS_0_5 ✔  ITEM_0 ✔  ITEM_0_5 ✔   (senão nem entra)

estado = PROJETAR_ESTADO()          # [ENXERTO 2] derivado, não lido de arquivo forjável
# PROJETAR_ESTADO() = função pura de (git log + hr_certifications + arch_decisions
#   + resultado dos contract-tests + suíte). Reconstruível após OOM. (I5)
# GP_LOOP_STATE.json vira CACHE dessa projeção, nunca a fonte.

# Ordem = fluxo de dados (produtor→consumidor), não ordem visual do print:
CARDS = [ Departamento_Pessoal,   # 1 produz folha/admissão/demissão/férias  (risco jurídico)
          Ponto_Eletronico,       # 2 produz batidas/justificativas          (risco jurídico 671)
          Recursos_Humanos,       # 3 recrutamento/treino/avaliação          (CRUD + cálculo leve)
          Saude_Ocupacional,      # 4 PCMSO/PPRA/EPI/CAT                      (risco jurídico eSocial SST)
          GED_Documentos_Kits,    # 5 monta kit = DOWNSTREAM do DP            (integração)
          Portal_do_Funcionario,  # 6 exibe contracheque = lê da folha        (CRUD + integração)
          Operacoes,              # 7 postos/escalas/campo  NÃO é folha        (CRUD + integração)
          Area_do_Cliente ]       # 8 portal externo kits/chamados            (CRUD + integração)

para cada CARD em CARDS:
    se estado[CARD] == CERTIFICADO_HUMANO: continue          # já fechado (fato no banco)

    resultado = LOOP_MODULO(CARD)

    # ── GATE NÍVEL 0 (só VOCÊ): refutação humana por amostra ──
    dossiê = resultado.dossiê_sobreviventes
    SE você refuta qualquer item da amostra crítica:
        registrar(o que derrubou, com evidência)            # vira ataque-regressão [ENXERTO 7]
        continue-no-mesmo-CARD com o defeito apontado
    SENÃO:
        # não escrevo "certificado" num arquivo; o fato JÁ está no banco:
        assert projeção(CARD) == verde_e_certificado          # [I3]

quando todos projetam CERTIFICADO_HUMANO: GP pronto p/ produção. FIM.
```

---

# LOOP_MODULO (Nível 1)
*Gate: cobertura total de telas + integração downstream REAL + não-regressão cruzada.*
```
função LOOP_MODULO(M):
    TELAS = descobrir_telas(M)         # varredura real do front, não lista de memória
    # invariante: nenhuma tela sai sem passar Nível 2 OU virar amarelo justificado

    enquanto existir TELA com status ∉ {VERDE, AMARELO_PENDENTE}:
        LOOP_TELA(TELA, M)

    # ── GATE de integração (o buraco real da SÍNTESE) — com contract-test [ENXERTO 2] ──
    para cada ARESTA de M (ex: DP → GEDEON, Recrutamento → DP, Ponto → Folha):
        disparar_evento_REAL(ARESTA)                 # publicar dp.funcionario.admitido ZZE2E real
        GATE_INTEGRACAO = efeito downstream observável com dado real?
                          # ex: GEDEON consumiu E montou o kit com o nome CERTO (leio o kit, não o log)
        se ¬GATE_INTEGRACAO: registrar bug; LOOP_TELA(origem ou destino)
        SENÃO:
            gravar CONTRACT_TEST(ARESTA):            # [ENXERTO 2] hash do contrato do evento
               {evento, chaves_esperadas, tipo_payload, hash}
            # entra na suíte: roda a cada fechamento de módulo; drift no payload → VERMELHO automático.

    # ── GATE de NÃO-REGRESSÃO CRUZADA [ENXERTO 2/8] ──
    # fechar M pode ter mexido em infra compartilhada (bus, tabela posts, motor).
    re-rodar TODOS os CONTRACT_TESTS dos módulos JÁ certificados
    se algum quebrou: o módulo certificado volta a AMARELO; registrar; consertar
    # produtor→consumidor reduz isso, mas não protege de edição em infra compartilhada.

    retornar dossiê(sobreviventes + prova de cada gate + lista de amarelos)
```

---

# LOOP_TELA (Nível 2) — o coração. 3 papéis, nunca o mesmo ator em dois.
```
função LOOP_TELA(T, M):
    CLASSE = classificar(T)
      # CRUD_SIMPLES  → cadastro, upload, escala, chamado          (sem cálculo legal)
      # CALCULO_FOLHA → competência mensal                          (tem golden set p/ caminhos COBERTOS)
      # RISCO_JURIDICO→ rescisão, eSocial S-2210/20/40, ponto 671   (nunca verde-automático)
    FASE = fase_do_dado(T)       # SOMBRA (Portte ainda calcula, há gabarito) | CORTE (só nós)

    repetir:
        # ─── PAPEL 1: EXECUTOR (worktree isolado, escreve) ───
        endpoints = grep_endpoints(T)
        testar_GET(T)     → dado real? (não [], não 404/500) senão corrigir
        testar_ESCRITA(T) → criar ZZE2E_ → conferir NO BANCO → editar → excluir → sumiu?
        corrigir_bugs(catálogo S1–S7 + padrões A–K)                # [ENXERTO 7] taxonomia real da casa
        py_compile + bake_durável(âncora pre-*)                     # imagem assada, não docker cp

        # ─── GATE POR CLASSE (o oráculo muda) ───
        se CLASSE == CRUD_SIMPLES:
            G = (E2E leitura+escrita verde)                          # 200 basta

        se CLASSE == CALCULO_FOLHA:
            # [ENXERTO 5] RECONCILIAR INPUT antes de comparar saída
            inputs_nossos = ler_inputs(T)                            # salário, dependentes, categoria, admissão
            inputs_dominio = inputs_assumidos_pelo_holerite(golden)
            se inputs_nossos ≠ inputs_dominio:
                registrar "divergência de INPUT (não de lógica)"; corrigir o DADO, não o cálculo; continue
            # [ENXERTO 3] CÁLCULO CEGO PERMANENTE — ator que calcula NUNCA viu o esperado, em passada nenhuma
            calc = AGENTE_CEGO.recalcular_pela_lei(inputs_nossos, legal_reference)  # usa tabela certificada [ENXERTO 4]
            # [ENXERTO 6] só compara se o caminho é COBERTO pelo golden set
            se cobertura[caminho(T)] == COBERTO:
                esperado = COMPARADOR_SEPARADO.ler_golden(holerite)  # outro ator lê o gabarito
                G = (calc == esperado ao centavo)
                    OU (divergência EXPLICADA pela lei + registrada)  # Domínio pode estar errada
            senão:  # NAO_COBERTO → não há gabarito
                G = CALCULADO_LEI_SEM_GOLDEN                          # → exige certificação humana

        se CLASSE == RISCO_JURIDICO:
            calc = AGENTE_CEGO.recalcular_pela_lei(inputs, legal_reference)
            G = "CALCULADO_NAO_TRANSMITIDO"                          # nunca verde-automático

        # ─── PAPEL 2: ADVERSARIAL (agente separado, read-only, contexto LIMPO) ───
        # NÃO recebe o raciocínio do executor. Recebe: "T alega estar pronta. Refute."
        ataques = ATAQUES_BASE ∪ ATAQUES_DA_CLASSE(CLASSE) ∪ TAXONOMIA_S1_S7 ∪ regressões_do_Nível0  # [ENXERTO 7]
        # ATAQUES_BASE = [dado_escondido, 500_sob_condição, save_que_mente, integração_morta]
        # TAXONOMIA_S1_S7 = [payload usa funcionario_nome mas handler lê name?,
        #                    filtro status=='Ativo' vs 'ativo'?, TZ +4h?, UUID em path param?,
        #                    handler órfão nunca dispara?, fire-and-forget GC'd?, 2º motor vivo?]
        refutou = adversarial_executa(ataques)      # retorna achado OU lista de ataques tentados
        se refutou: registrar defeito; volta ao EXECUTOR            # não fecha
        se adversarial "passou" SEM lista de ataques tentados: INVÁLIDO, re-roda  # adversarial preguiçoso

    até (G ∈ {verde, calculado_amarelo}) E (adversarial FALHOU em refutar COM lista de ataques)

    # ─── DEFINITION OF DONE (todos batem) ───
    DoD = G ∧ resíduo_ZZE2E==0 ∧ bake_durável ∧ sem_regressão(suíte)
          ∧ contract_tests_verdes ∧ syncs_24/7_intactos ∧ migration_revisada(se houve)
          ∧ adversarial_falhou_com_lista
          ∧ [#10 legal] (CLASSE ∈ {CALCULO_FOLHA,RISCO_JURIDICO} ⇒ tem trilha de certificação)

    se CLASSE ∈ {CALCULO_FOLHA, RISCO_JURIDICO}:
        # ─── PAPEL 3: CERTIFICADOR HUMANO (time DP/Contábil) — gate C RASTREÁVEL ───
        gerar_pacote_conferência(T, calc, esperado, divergências, cobertura, fase)
        criar hr_certifications(referencia=T, calc, esperado, hash_conteudo, status=pendente)
        estado[T] = AMARELO_PENDENTE(certificador)
        # AMARELO→VERDE só quando existe LINHA em hr_certifications
        #   {certificado_por, certificado_em, hash} com hash == hash atual do conteúdo.  [I3/I4]
        # RISCO_JURIDICO em produção = "calcula e mostra, NÃO transmite sem esse registro".
        # muda o cálculo → hash muda → certificação expira → volta a pendente (anti "certifiquei mês passado").
    senão:
        estado[T] = VERDE   # (fato: contract-tests + E2E no banco, projetável)
```

---

## Onde cada exigência sua está cravada (conferência)
- **"humano sempre confere e certifica"** → Papel 3 + I3; folha/risco nunca verde sem linha assinada com hash.
- **"agente/subagente por módulo com skill"** → EXECUTOR especializado (Papel 1); a skill melhora o cálculo, não vira juiz de si (I1).
- **gate inforjável** → cego permanente [3], adversarial isolado + lista [7], certificação-artefato com hash [I3/I4], estado projetado [2].
- **não repetir a t1-morta** → estado DERIVÁVEL (I5); OOM não perde o ponto porque o ponto é o banco+git, não a memória.
- **integração > CRUD** → Nível 1 exige efeito downstream real + contract-test que reverte no drift [2].
- **não redesenhar navegação** → §13.2; o loop entra nos 8 cards do print e conserta atrás das telas.
- **fases sombra/corte** → `FASE` no Nível 2 escolhe o oráculo (golden vivo vs lei+humano).

## O que v2 NÃO mudou de v1 (de propósito)
Hash da certificação · ordem produtor→consumidor · humano permanente · 3 papéis separados · break humano Nível 0 · adversarial contexto-limpo · trava de fase. **v1 acertou; reescrever seria o teatro que combatemos.**
```
```
