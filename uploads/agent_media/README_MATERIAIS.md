# Biblioteca de materiais do José Luis (leia-me)

Coloque AQUI os arquivos que o José Luis pode ENVIAR aos clientes no WhatsApp:
fotos da empresa/central, apresentações em PDF, vídeos institucionais/promocionais.

## Como funciona
- Todo arquivo desta pasta fica disponível para o José Luis na hora (sem rebuild).
- Ele decide enviar quando agrega ao atendimento (ex.: cliente pediu apresentação),
  sempre apresentando o material com uma frase antes.

## Regras de nomeação (IMPORTANTE)
O José Luis escolhe o material PELO NOME do arquivo — nomeie de forma descritiva,
em minúsculas com hífens:
- apresentacao-portaria-remota.pdf
- foto-central-monitoramento.jpg
- video-institucional-conecta-mais.mp4
- apresentacao-servicos-condominios.pdf

## Como subir do MacBook (terminal)
Do seu Mac, mande os arquivos para esta pasta no VPS (use o IP):

    scp ~/Desktop/conecta-materiais/*.pdf  root@82.25.75.74:/opt/conecta-pro/uploads/agent_media/
    scp ~/Desktop/conecta-materiais/*.jpg  root@82.25.75.74:/opt/conecta-pro/uploads/agent_media/
    scp ~/Desktop/conecta-materiais/*.mp4  root@82.25.75.74:/opt/conecta-pro/uploads/agent_media/

Os arquivos ficam disponíveis para o José Luís NA HORA (volume montado, sem rebuild).
Não precisa reiniciar nada. Depois de subir, me avise que eu confirmo a listagem.

## Limites e cuidados
- Máx ~60MB por arquivo (limite prático do WhatsApp; vídeos: prefira até 16MB).
- NUNCA coloque tabelas de preço, propostas de clientes ou documentos internos.
- Formatos bons: .pdf, .jpg, .png, .mp4
- Este README não aparece para o José Luis (ignorado pela listagem).
