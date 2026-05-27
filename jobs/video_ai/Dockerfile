FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 \
    FFMPEG_PATH=/usr/bin/ffmpeg \
    MUSETALK_HOME=/opt/MuseTalk \
    PYTHONPATH=/opt/MuseTalk

ARG MUSETALK_REPO=https://github.com/TMElyralab/MuseTalk.git
ARG MUSETALK_REF=main

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    ffmpeg \
    git \
    libgl1 \
    libglib2.0-0 \
    python3.10 \
    python3.10-dev \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.10 /usr/local/bin/python \
    && ln -sf /usr/bin/pip3 /usr/local/bin/pip \
    && python -m pip install --upgrade "pip<25" "setuptools<82" wheel

RUN pip install torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 \
    --index-url https://download.pytorch.org/whl/cu118

RUN pip install --no-cache-dir -U openmim

RUN mim install mmengine

RUN mim install "mmcv==2.0.1"

RUN mim install "mmdet==3.1.0"

RUN pip install --no-build-isolation chumpy==0.70

RUN mim install "mmpose==1.1.0"

RUN git clone --depth 1 --branch ${MUSETALK_REF} ${MUSETALK_REPO} ${MUSETALK_HOME}

WORKDIR ${MUSETALK_HOME}

RUN pip install -r requirements.txt

RUN rm -rf ${MUSETALK_HOME}/models \
    && ln -s /models ${MUSETALK_HOME}/models

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    libavformat-dev \
    libavcodec-dev \
    libavdevice-dev \
    libavutil-dev \
    libavfilter-dev \
    libswscale-dev \
    libswresample-dev \
    && rm -rf /var/lib/apt/lists/*

ARG COSYVOICE_REPO=https://github.com/FunAudioLLM/CosyVoice.git
ARG COSYVOICE_REF=main
RUN git clone --recursive --depth 1 --branch ${COSYVOICE_REF} ${COSYVOICE_REPO} /opt/CosyVoice \
    && pip install --no-build-isolation -r /opt/CosyVoice/requirements.txt

COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY cosyvoice3_tts.py /app/cosyvoice3_tts.py
COPY text_style_transform.py /app/text_style_transform.py
COPY main.py /app/main.py

CMD ["python", "/app/main.py"]
