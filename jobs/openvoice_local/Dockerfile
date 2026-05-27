FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NLTK_DATA=/usr/local/share/nltk_data

ARG OPENVOICE_REPO=https://github.com/myshell-ai/OpenVoice.git
ARG OPENVOICE_REF=74a1d147b17a8c3092dd5430504bd83ef6c7eb23
ARG MELOTTS_REF=209145371cff8fc3bd60d7be902ea69cbdb7965a

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    pkg-config \
    libavformat-dev \
    libavcodec-dev \
    libavdevice-dev \
    libavutil-dev \
    libavfilter-dev \
    libswscale-dev \
    libswresample-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv --system-site-packages /opt/openvoice-venv

RUN printf 'Cython<3\n' > /tmp/openvoice-build-constraints.txt \
    && /opt/openvoice-venv/bin/pip install --upgrade pip setuptools wheel \
    && /opt/openvoice-venv/bin/pip install 'Cython<3'

RUN git clone ${OPENVOICE_REPO} /opt/OpenVoice \
    && cd /opt/OpenVoice \
    && git checkout ${OPENVOICE_REF}

RUN PIP_CONSTRAINT=/tmp/openvoice-build-constraints.txt /opt/openvoice-venv/bin/pip install /opt/OpenVoice

RUN PIP_CONSTRAINT=/tmp/openvoice-build-constraints.txt /opt/openvoice-venv/bin/pip install git+https://github.com/myshell-ai/MeloTTS.git@${MELOTTS_REF}

RUN /opt/openvoice-venv/bin/python -m unidic download

RUN mkdir -p ${NLTK_DATA} \
    && /opt/openvoice-venv/bin/python -c "import nltk; nltk.download('averaged_perceptron_tagger_eng', download_dir='${NLTK_DATA}', quiet=True)"

RUN rm -rf /opt/OpenVoice/checkpoints_v2 \
    && ln -s /models/openvoice/checkpoints_v2 /opt/OpenVoice/checkpoints_v2 \
    && rm -rf /opt/OpenVoice/.git /root/.cache/pip /tmp/openvoice-build-constraints.txt

WORKDIR /app
COPY jobs/video_ai/openvoice_tts.py /app/openvoice_tts.py

ENTRYPOINT ["/opt/openvoice-venv/bin/python", "/app/openvoice_tts.py"]
