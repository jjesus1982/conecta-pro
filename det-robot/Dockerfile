FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

ENV DEBIAN_FRONTEND=noninteractive TZ=America/Manaus

# Xvfb (display virtual) + x11vnc (VNC) + noVNC/websockify (VNC no browser) + fluxbox (WM leve)
RUN apt-get update && apt-get install -y --no-install-recommends \
      xvfb x11vnc novnc websockify fluxbox openssl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir playwright==1.47.0 fastapi==0.111.0 uvicorn==0.30.0 httpx==0.27.0

WORKDIR /app
COPY robot.py .

# 6080 = noVNC (login supervisionado) | 8099 = API de controle do robô
EXPOSE 6080 8099
CMD ["python", "robot.py"]
