/**
 * PM2 Ecosystem — CTO Monitor Bot
 * Gerencia o bot Telegram bidirecional do CTO Autônomo (Sprint 1).
 *
 * Uso:
 *   pm2 start ecosystem_monitor.config.js
 *   pm2 reload ecosystem_monitor.config.js
 *   pm2 delete ecosystem_monitor.config.js
 */
module.exports = {
  apps: [
    {
      name: "cto-monitor-bot",
      script: "agents/cto/monitor_bot.py",
      interpreter: "python3",
      cwd: "/opt/conecta-pro",

      // Reinício automático com back-off
      restart_delay: 5000,    // 5s entre restarts
      max_restarts: 10,       // máx 10 restarts antes de parar
      min_uptime: "10s",      // deve ficar online pelo menos 10s

      // Logs
      out_file: "agents/cto/monitor_bot_pm2.log",
      error_file: "agents/cto/monitor_bot_pm2_err.log",
      merge_logs: false,
      time: true,

      // Variáveis de ambiente
      env: {
        MONITOR_BOT_TOKEN: "<TOKEN-TELEGRAM-REVOGADO-2026-08-11>", // pragma: allowlist secret
        TELEGRAM_CHAT_ID: "5536961034",
      },
    },
  ],
};
