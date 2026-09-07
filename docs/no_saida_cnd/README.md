# Nó de saída das CNDs — o robô sai pela internet do seu PC

**Por quê.** A Caixa (CRF/FGTS) bloqueia o IP da VPS na borda (403 até com navegador real) e o
TST (CNDT) não responde a ele. Empresas que vendem "robô de certidão" saem por IP residencial.
Nós fazemos o mesmo sem serviço pago: o seu PC abre UMA conexão SSH para a VPS e, por ela, a
VPS ganha um proxy SOCKS cuja saída é a SUA internet. O robô de CND (já existente) usa esse
proxy quando ele está de pé; quando não está, sai direto (SEFAZ-AM e SEMEF funcionam assim).

**O que já está feito na VPS (07/09/2026).**
- usuário `cndtunnel`, sem shell, aceita só encaminhamento para `127.0.0.1:1080` (chave restrita);
- `cnd_watcher.sh` detecta a porta 1080 e exporta `CND_PROXY=socks5://127.0.0.1:1080`;
- provado: com o túnel de pé, o Chromium do robô sai pelo proxy (teste com api.ipify.org).

**O que você faz no PC (uma vez).**
1. Copie a chave privada `rotinas/no_saida_cnd_ed25519` da VPS para o PC (fora do git, nunca por chat):
   `scp root@82.25.75.74:/opt/conecta-pro/rotinas/no_saida_cnd_ed25519 %USERPROFILE%\.ssh\no_saida_cnd`
2. Windows 10/11 já tem OpenSSH. Salve `no_saida_cnd.bat` (abaixo) e deixe rodando (ou agende
   no Agendador de Tarefas "ao iniciar sessão"). macOS/Linux: `no_saida_cnd.sh`.
3. Na VPS, `ss -ltn | grep 1080` mostra a porta quando o túnel está vivo. Depois disso, o botão
   "Emitir CNDs" do GEDEON (e o auto-retry de 6 h) já saem pelo seu IP.

**Limites, sem disfarce.** Enquanto o PC estiver desligado ou sem internet, o túnel cai e o robô
volta a sair direto (Caixa/TST falham; SEFAZ/SEMEF seguem). A Caixa ainda não tem robô escrito
(`caixa()` não existe no `cnd_robot.py`); com o túnel de pé dá para escrever e TESTAR contra o
portal de verdade — sem o túnel, não há como provar seletor nenhum daqui. Captcha continua sendo
do 2captcha (centavos).
