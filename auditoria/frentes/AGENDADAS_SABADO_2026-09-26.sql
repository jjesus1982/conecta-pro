BEGIN;
INSERT INTO wa_mensagens_agendadas (telefone, nome, texto, quando, motivo, criado_por)
SELECT coalesce(nullif(e.celular,''), e.telefone),
       e.nome,
'Bom dia, Malaquias! Aqui é o José Luís. 👋

Olhei suas batidas dos últimos dias e notei uma coisa: *31 delas entraram por contingência* (aquele caminho manual, por mensagem) e só *1 pelo aplicativo*.

Contingência funciona e o seu ponto está registrado — mas ela entra sem foto e sem localização, e aí o DP precisa validar uma por uma. Para você é mais trabalho, e o fechamento demora mais.

Queria entender o que está acontecendo, sem cobrança nenhuma:

• O aplicativo *abre* no seu celular?
• Ele reconhece seu rosto, ou trava no reconhecimento?
• Você consegue *entrar* com seu login?
• Ou é o sinal no posto que não ajuda?

Me conta o que acontece quando você tenta — com print, se puder. Se for problema do app ou do seu acesso, eu abro no DP e alguém resolve. *Você não perde ponto por causa de falha do aplicativo*, isso eu quero deixar claro.',
       TIMESTAMPTZ '2026-09-26 08:00:00-04',
       'desvio de canal: 31 batidas por contingencia x 1 pelo app em 14 dias',
       'jose_luis (pedido do Jordan, 25/09)'
FROM employees e WHERE unaccent(upper(e.nome)) LIKE '%MALAQUIAS%' LIMIT 1;
COMMIT;
BEGIN;
INSERT INTO wa_mensagens_agendadas (telefone, nome, texto, quando, motivo, criado_por)
SELECT coalesce(nullif(e.celular,''), e.telefone), e.nome,
'Oi ' || initcap(split_part(e.nome,' ',1)) || '! Aqui é o José Luís. 👋

Você me relatou um problema com o aplicativo do ponto há alguns dias, e eu não quero que isso fique só no relato.

Primeiro, uma coisa que eu confirmei olhando o sistema e quero que você saiba: *batida por contingência conta como batida*. Ela entra no seu ponto do mesmo jeito — não vira falta, não desconta. Se o app falhar e você registrar por mensagem, seu ponto está garantido.

Agora, pra gente consertar de verdade, me ajuda com três coisas?

1️⃣ O que exatamente acontece — o app *não abre*, abre e *trava*, ou abre e a *câmera não reconhece* seu rosto?
2️⃣ Acontece *sempre* ou só às vezes (num horário, num posto)?
3️⃣ Qual o modelo do seu celular? (Configurações → Sobre o telefone)

O item 3 é o que mais falta: hoje o sistema *não registra* qual aparelho fez a batida, então não temos como saber se é um modelo específico. Sua resposta é o único jeito de descobrir.

Se puder mandar um *print* da tela quando falhar, melhor ainda.',
  TIMESTAMPTZ '2026-09-26 09:00:00-04',
  'relatou falha do app; coletar sintoma + modelo (device_id nao e gravado: 2 de 1953 batidas)',
  'jose_luis (pedido do Jordan, 25/09)'
FROM employees e
WHERE right(regexp_replace(coalesce(e.celular,'')||coalesce(e.telefone,''),'\D','','g'),8)
      IN ('81148752','93979268','86032758','91361770','94536609','91174301')
  AND coalesce(nullif(e.celular,''), e.telefone) IS NOT NULL;
COMMIT;
