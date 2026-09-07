@echo off
title Conecta PRO - no de saida das CNDs (deixe aberto)
:loop
echo [%date% %time%] abrindo tunel para a VPS...
ssh -N -R 127.0.0.1:1080 -i "%USERPROFILE%\.ssh\no_saida_cnd" -o IdentitiesOnly=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new cndtunnel@82.25.75.74
echo [%date% %time%] tunel caiu, reconectando em 20 s...
timeout /t 20 /nobreak >nul
goto loop
