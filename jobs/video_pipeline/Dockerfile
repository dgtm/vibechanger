FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates ffmpeg git libgl1 libglib2.0-0 \
    python3.10 python3.10-dev python3-pip python3-setuptools python3-wheel \
    pkg-config libavformat-dev libavcodec-dev libavdevice-dev libavutil-dev libavfilter-dev libswscale-dev libswresample-dev \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.10 /usr/local/bin/python \
    && ln -sf /usr/bin/pip3 /usr/local/bin/pip \
    && python -m pip install --upgrade "pip<25" "setuptools<82" wheel

FROM base AS cosyvoice

ARG COSYVOICE_REPO=https://github.com/FunAudioLLM/CosyVoice.git
ARG COSYVOICE_REF=main
RUN python -m pip install --upgrade "numpy==1.26.4"
RUN git clone --recursive --depth 1 --branch ${COSYVOICE_REF} ${COSYVOICE_REPO} /opt/CosyVoice \
    && grep -Evi 'deepspeed|tensorrt|onnxruntime-gpu' /opt/CosyVoice/requirements.txt > /tmp/cosyvoice-req.txt \
    && pip install --no-build-isolation -r /tmp/cosyvoice-req.txt

RUN python -c "import numpy; print(numpy.__version__)"

COPY jobs/video_pipeline/requirements_cosyvoice.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY jobs/video_pipeline/cosyvoice3_tts.py /app/cosyvoice3_tts.py
COPY jobs/video_pipeline/main_cosyvoice.py /app/main.py
CMD ["python", "/app/main.py"]

FROM base AS video-post

ENV FFMPEG_PATH=/usr/bin/ffmpeg \
    MUSETALK_HOME=/opt/MuseTalk \
    PYTHONPATH=/opt/MuseTalk

ARG MUSETALK_REPO=https://github.com/TMElyralab/MuseTalk.git
ARG MUSETALK_REF=main

COPY jobs/video_pipeline/requirements.torch.txt /tmp/requirements.torch.txt
RUN pip install -r /tmp/requirements.torch.txt
# RUN python -c "import torch; print('torch', torch.__version__, 'cuda', torch.version.cuda, 'available', torch.cuda.is_available())"
RUN pip install --no-cache-dir -U openmim \
    && mim install mmengine \
    && pip install --no-build-isolation chumpy==0.70
RUN mim install "mmcv==2.0.1"
RUN mim install "mmdet==3.1.0"
RUN mim install "mmpose==1.1.0"

RUN git clone --depth 1 --branch ${MUSETALK_REF} ${MUSETALK_REPO} ${MUSETALK_HOME}
WORKDIR ${MUSETALK_HOME}
RUN pip install -r requirements.txt \
    && rm -rf ${MUSETALK_HOME}/models \
    && ln -s /models ${MUSETALK_HOME}/models
RUN python -c "import torch, torchaudio; print('torch', torch.__version__, 'torchaudio', torchaudio.__version__, 'cuda', torch.version.cuda)"

WORKDIR /app
COPY jobs/video_pipeline/requirements_video_post.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt
COPY jobs/video_pipeline/text_style_transform.py /app/text_style_transform.py
COPY jobs/video_pipeline/main_video_post.py /app/main.py
CMD ["python", "/app/main.py"]
