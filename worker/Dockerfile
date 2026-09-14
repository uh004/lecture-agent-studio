FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SAL_USE_VCLPLUGIN=svp \
    SOFFICE_CMD=/usr/bin/soffice \
    PDFTOPPM_CMD=/usr/bin/pdftoppm \
    FFMPEG_CMD=/usr/bin/ffmpeg \
    FFPROBE_CMD=/usr/bin/ffprobe

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        fontconfig \
        fonts-liberation \
        fonts-nanum \
        fonts-noto-cjk \
        libreoffice-impress \
        poppler-utils \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

COPY worker/fonts.conf /etc/fonts/local.conf
RUN fc-cache -f

WORKDIR /app

COPY worker/requirements.txt /app/worker/requirements.txt
RUN pip install --no-cache-dir -r /app/worker/requirements.txt

COPY src /app/src
COPY worker /app/worker

CMD ["python", "-m", "worker"]
