# Dockerfile - ERP Conecta Mais Backend
# Multi-stage build para imagem otimizada

# ===========================================
# Stage 1: Builder
# ===========================================
FROM python:3.12-slim AS builder

WORKDIR /app

# Criar /tmp e instalar dependências de build
RUN mkdir -p /tmp && chmod 1777 /tmp && \
    apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar dependências
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

# ===========================================
# Stage 2: Runtime
# ===========================================
FROM python:3.12-slim AS runtime

WORKDIR /app

# Criar /tmp e instalar dependências runtime
RUN mkdir -p /tmp && chmod 1777 /tmp && \
    apt-get update && apt-get install -y \
    libpq5 \
    curl \
    procps \
    redis-tools \
    && rm -rf /var/lib/apt/lists/*

# Instalar Docker CLI (para OpenClaw remediação)
RUN curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.5.1.tgz \
    | tar xz --strip-components=1 -C /usr/local/bin docker/docker \
    && chmod +x /usr/local/bin/docker

# Criar usuário não-root com acesso ao Docker socket
# GID 988 = grupo docker do host para acesso ao /var/run/docker.sock
# ⚠️ UID/GID FIXOS EM 999 — 28/08/2026, e a causa foi cara de achar. `groupadd -r` /
# `useradd -r` pegam o PRÓXIMO id de sistema livre. Ao instalar `ffmpeg`, as dependências
# dele criaram usuários de sistema e tomaram o 999, então o `erp` nasceu 995 na imagem
# nova — e o container não conseguiu escrever em `/app/logs/app.log`, que no HOST pertence
# ao 999. Sintoma: green subia, morria em loop com PermissionError, e o deploy abortava
# com "não ficou saudável em 420s". Nada a ver com o ffmpeg em si.
#
# Volume montado do host tem dono NUMÉRICO: o nome do usuário dentro do container é
# irrelevante. Instalar QUALQUER pacote novo podia repetir isto — por isso o id é fixado,
# não descoberto.
RUN groupadd -r erp && groupadd -g 988 docker-host && \
    useradd -r -g erp -G docker-host erp && \
    mkdir -p /app/logs

# Copiar wheels do builder
COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache /wheels/*

# Instalar Celery separadamente
RUN pip install --no-cache-dir celery[redis]==5.4.0 kombu==5.4.2 flower==2.0.1

# Copiar código
COPY --chown=erp:erp . .

# Ajustar permissões
RUN chown -R erp:erp /app/logs

# Mudar para usuário não-root
# ⭐ ffmpeg DEPOIS do `useradd` — e a ORDEM é o conserto, não um detalhe (28/08/2026).
# Extrai QUADROS de vídeo por mudança de cena para a visão analisar o que se VÊ além do
# que foi falado: o Jordan filma a visita narrando, e até aqui os quadros não eram vistos
# por ninguém.
#
# ⚠️ Instalar isto ANTES do `useradd` quebrou o deploy duas vezes, e o sintoma não tinha
# relação aparente: as dependências do ffmpeg criam usuários de sistema e OCUPAM o uid/gid
# 999, então o `erp` nascia 995 e o container não conseguia escrever em `/app/logs`, que
# no host pertence ao 999 numérico. O deploy só dizia "green não ficou saudável em 420s".
# Fixar `-u 999` também não resolve: o gid 999 já está tomado nesse ponto e o build falha
# com "GID already exists". A ordem resolve os dois.
RUN apt-get update && apt-get install -y ffmpeg \
    && rm -rf /var/lib/apt/lists/*

USER erp

# Variáveis de ambiente
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Expor porta
EXPOSE ${PORT}

# Comando de início - FastAPI com Uvicorn (versao producao)
CMD ["uvicorn", "main_production:app", "--host", "0.0.0.0", "--port", "8080", "--timeout-graceful-shutdown", "25"]
