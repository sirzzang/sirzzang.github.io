---
title:  "[Kubernetes] Kubernetes 환경에서의 Co-DETR 모델 추론 서빙 개선기 - 2. Docker 이미지 경량화"
excerpt: "18.5GB라는 Docker 이미지 크기를 줄여 보자."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - k8s
  - k3s
  - kubernetes
  - gpu
  - docker
  - inference
---



[1편](/dev/Dev-Kubernetes-CoDETR-Inference-Experience-1/)에서 언급했던 첫 번째 문제점, "서빙 이미지가 너무 무겁다"를 개선한 과정을 정리한다.

<br>

# 문제 상황

Co-DETR 추론 서빙용 Docker 이미지를 처음 빌드했을 때, 크기가 **18.5GB**였다. 새로운 노드에서 이미지를 풀링하는 데 **약 19분**이 소요되었다.

```bash
$ time docker pull my-registry.example.com:5000/ml-serving/co-detr-coco-app:1.0
...
real    18m43.197s
user    0m1.638s
sys     0m1.403s

$ docker images | grep co-detr
my-registry.example.com:5000/ml-serving/co-detr-coco-app   1.0   c6ae87c87cef   7 hours ago   18.5GB
```

<br>

## 왜 문제인가

- **초기 배포 및 재스케줄링 지연**: 새로운 노드에 파드가 스케줄링될 때마다 19분 대기. 노드 장애나 유지보수로 다른 노드에 재배포될 때도 마찬가지
- **노드 스토리지 중복 사용**: 여러 노드에 배포되면 각 노드마다 18.5GB씩 이미지가 저장됨
- **재배포 부담**: 모델이나 코드가 조금만 바뀌어도 전체 이미지를 다시 빌드하고 푸시해야 함
- **CI/CD 병목**: 빌드-푸시-풀 사이클이 길어져 배포 주기에 영향

한 번 풀링된 노드에서는 빠르게 시작되지만, 언제든 다른 노드로 스케줄링될 수 있다는 점을 고려하면 무시할 수 없는 오버헤드였다.

> 실제로는 RTX 4090 10장이 장착된 단일 노드에서만 추론 파드를 운영하고 있다. 하지만 향후 추론에 활용할 수 있는 노드가 늘어나거나, 기존 노드의 활용 목적이 변경될 경우를 대비해야 했다. 특정 노드에 종속되지 않고, 어떤 GPU 노드에서든 빠르게 배포될 수 있는 구조가 필요했다.

<br>

# 기존 이미지 구조

당시 Dockerfile은 아래와 같은 구조였다. [MMDetection 공식 Dockerfile](https://github.com/open-mmlab/mmdetection/blob/main/docker/Dockerfile)을 참고해 그대로 사용했는데, devel과 runtime의 차이를 인지하지 못한 채로 만든 것이었다.

<br>

## Base 이미지

```dockerfile
ARG PYTORCH="1.9.0"
ARG CUDA="11.1"
ARG CUDNN="8"

FROM pytorch/pytorch:${PYTORCH}-cuda${CUDA}-cudnn${CUDNN}-devel

ENV TORCH_CUDA_ARCH_LIST="6.0 6.1 7.0 7.5 8.0 8.6+PTX" \
    TORCH_NVCC_FLAGS="-Xfatbin -compress-all" \
    CMAKE_PREFIX_PATH="$(dirname $(which conda))/../" \
    FORCE_CUDA="1"

# Avoid Public GPG key error
# https://github.com/NVIDIA/nvidia-docker/issues/1631
RUN rm /etc/apt/sources.list.d/cuda.list \
    && rm /etc/apt/sources.list.d/nvidia-ml.list \
    && apt-key del 7fa2af80 \
    && apt-key adv --fetch-keys https://developer.download.nvidia.com/compute/cuda/repos/ubuntu1804/x86_64/3bf863cc.pub \
    && apt-key adv --fetch-keys https://developer.download.nvidia.com/compute/machine-learning/repos/ubuntu1804/x86_64/7fa2af80.pub

# Install the required packages
RUN apt-get update \
    && apt-get install -y ffmpeg libsm6 libxext6 git ninja-build libglib2.0-0 libxrender-dev libxext6 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install MMEngine and MMCV
RUN pip install openmim && \
    mim install "mmengine>=0.7.1" "mmcv==2.1.0"

RUN conda clean --all

WORKDIR /ml-inference-server

COPY ../../requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY ../../Co-DETR-coco Co-DETR-coco
RUN pip install --no-cache-dir -e ./Co-DETR-coco/.
```

<br>

## App 이미지

```dockerfile
FROM co-detr-coco-base:1.0

WORKDIR /ml-inference-server
COPY ../../app app

ENV MODEL_TYPE=co-detr-coco
```

Base 이미지 위에 애플리케이션 코드만 추가하는 구조였다. 문제는 Base 이미지 자체가 이미 18GB에 달했다는 점이다.

<br>

# 원인 분석

`docker history` 명령으로 레이어별 크기를 분석했다.

```bash
$ docker history my-registry.example.com:5000/ml-serving/co-detr-coco-app:1.0 --human=true
```

<br>

## 레이어별 크기 순위

| 순위 | 크기 | 내용 |
|------|------|------|
| 1위 | **7.82GB** | `COPY /opt/conda /opt/conda` (Conda 전체 환경) |
| 2위 | **4.57GB** | cuDNN 8.0.5.39 설치 |
| 3위 | **2.39GB** | CUDA 런타임 라이브러리 (nccl2, cublas 등) |
| 4위 | **2.24GB** | CUDA 개발 도구 (nvml-dev, nvprof 등) |
| 5위 | **772MB** | mmengine + mmcv==2.1.0 설치 |

<br>

## 주요 원인

### 1. devel 이미지 사용

```dockerfile
FROM pytorch/pytorch:${PYTORCH}-cuda${CUDA}-cudnn${CUDNN}-devel  # 문제!
```

PyTorch 공식 이미지는 여러 variant를 제공하는데, 주요한 두 가지는 다음과 같다:

| 구분 | 용도 | 포함 내용 | 크기 차이 |
|------|------|----------|----------|
| **devel** | 개발/컴파일용 | CUDA 컴파일러, 헤더 파일, 개발 도구 | +4~6GB |
| **runtime** | 배포/실행용 | CUDA 런타임만 포함 | 기준 |

devel 이미지는 CUDA 커널을 직접 컴파일해야 할 때 필요하다. 하지만 **추론 서빙 시에는 이미 컴파일된 라이브러리를 사용**하므로, runtime으로 충분하다.

> 실무에서 추론 서빙 시에는 runtime 이미지를 사용하는 것이 일반적이다. devel은 커스텀 CUDA 커널 개발이나 라이브러리 빌드 시에만 필요하다.

<br>

### 2. Conda 환경 전체 복사

```
COPY /opt/conda /opt/conda  # 7.82GB
```

베이스 이미지에서 Conda 환경 전체가 복사되어 있었다. 불필요한 패키지들도 포함되어 있었을 가능성이 높다.

<br>

### 3. 캐시 미정리

apt-get, pip, conda 캐시가 레이어에 남아 있어 이미지 크기를 불필요하게 증가시켰다.

<br>

# 개선 과정

단계별로 개선을 진행하며 효과를 측정했다.

<br>

## 1단계: runtime 이미지로 전환 (v2.0)

가장 큰 개선 효과를 기대할 수 있는 부분부터 시작했다.

```dockerfile
ARG PYTORCH="1.9.0"
ARG CUDA="11.1"
ARG CUDNN="8"

FROM pytorch/pytorch:${PYTORCH}-cuda${CUDA}-cudnn${CUDNN}-runtime  # 변경

ENV TORCH_CUDA_ARCH_LIST="6.0 6.1 7.0 7.5 8.0 8.6+PTX" \
    TORCH_NVCC_FLAGS="-Xfatbin -compress-all" \
    CMAKE_PREFIX_PATH="$(dirname $(which conda))/../" \
    FORCE_CUDA="1"

# GPG key 관련 코드 제거 (runtime 이미지에는 해당 파일이 없음)

# Install the required packages
RUN apt-get update \
    && apt-get install -y ffmpeg libsm6 libxext6 git ninja-build libglib2.0-0 libxrender-dev libxext6 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 이하 동일
```

<br>

### GPG key 관련 코드 제거

runtime 이미지로 변경하니 아래 에러가 발생했다:

```bash
rm: cannot remove '/etc/apt/sources.list.d/cuda.list': No such file or directory
```

이 GPG key 관련 코드는 devel 이미지에서 CUDA 패키지를 추가 설치할 때 발생하는 문제를 해결하기 위한 것이었다. runtime 이미지에서는 해당 파일 자체가 없으므로, 해당 RUN 명령을 제거했다.

<br>

## 2단계: apt 캐시 정리 강화 (v3.0)

```dockerfile
RUN apt-get update \
    && apt-get install -y ffmpeg libsm6 libxext6 git ninja-build libglib2.0-0 libxrender-dev libxext6 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /tmp/* /var/tmp/*  # 추가
```

<br>

## 3단계: mmcv 설치 방식 변경 (v4.0)

`mim install`은 내부적으로 소스에서 빌드하는 경우가 있어 시간이 오래 걸리고 캐시도 많이 남긴다. pre-built wheel을 직접 설치하는 방식으로 변경했다.

```dockerfile
# 기존
RUN pip install openmim && \
    mim install "mmengine>=0.7.1" "mmcv==2.1.0"

# 변경
RUN pip install openmim && \
    mim install --no-cache-dir "mmengine>=0.7.1" && \
    pip install --no-cache-dir mmcv==2.1.0 -f https://download.openmmlab.com/mmcv/dist/cu111/torch1.9.0/index.html
```

OpenMMLab에서 제공하는 pre-built wheel을 사용하면 CUDA 버전과 PyTorch 버전에 맞는 바이너리를 직접 다운로드할 수 있다.

<br>

# 개선 결과

## 이미지 크기 비교

```bash
$ docker images | grep coco-app
ml-serving/co-detr-coco-app   4.0   c58966a4e40a   10.1GB
ml-serving/co-detr-coco-app   3.0   4252a7ef48fb   10.2GB
ml-serving/co-detr-coco-app   2.0   f3add1daed28   10.2GB
ml-serving/co-detr-coco-app   1.0   c6ae87c87cef   18.5GB
```

| 버전 | 이미지 크기 | 절감량 | 주요 변경 |
|------|------------|--------|----------|
| 1.0 | 18.5GB | - | 초기 버전 (devel) |
| 2.0 | 10.2GB | **-8.3GB** | runtime 전환 |
| 3.0 | 10.2GB | - | apt 캐시 정리 (효과 미미) |
| 4.0 | 10.1GB | **-0.1GB** | mmcv pre-built wheel |

**devel → runtime 전환이 가장 큰 효과**를 보였다. 한 번의 변경으로 8GB 이상 절감되었다.

<br>

## 풀링 시간 비교

```bash
# v1.0 (18.5GB)
$ time docker pull my-registry.example.com:5000/ml-serving/co-detr-coco-app:1.0
real    18m43.197s

# v2.0 (10.2GB)
$ time docker pull my-registry.example.com:5000/ml-serving/co-detr-coco-app:2.0
real    12m26.276s
```

| 버전 | 풀링 시간 | 절감 |
|------|----------|------|
| 1.0 | 18분 43초 | - |
| 2.0 | 12분 26초 | **-6분 17초** |

약 **33% 개선**되었다.

<br>

## 빌드 시간

```bash
# v2.0: 138.9s
# v3.0: 152.9s
# v4.0: 186.6s
```

v4.0에서 빌드 시간이 늘어난 것은 mmcv wheel 다운로드 시간 때문이다. 하지만 빌드는 한 번만 하고 풀링은 여러 노드에서 반복되므로, 풀링 시간 절감이 더 중요하다.

<br>

# 한계

이미지 크기를 절반 가까이 줄였지만, 근본적인 한계가 있었다.

<br>

## 1. 여전히 큰 이미지

10GB도 결코 작은 크기가 아니다. 12분의 풀링 시간은 빠른 스케일 아웃에 여전히 부담이 된다.

<br>

## 2. 모델이 이미지에 포함됨

현재 구조의 가장 큰 문제는 **모델 파일이 이미지에 포함**되어 있다는 점이다.

```dockerfile
COPY ../../Co-DETR-coco Co-DETR-coco  # 모델 가중치 포함
```

이로 인해:
- **모델 업데이트 시 전체 재배포**: 모델만 바뀌어도 이미지 전체를 다시 빌드하고 푸시해야 함
- **모델-앱 버전 강결합**: 모델 버전과 애플리케이션 버전을 독립적으로 관리하기 어려움
- **노드별 중복 저장**: 동일한 모델 파일이 각 노드의 이미지 레이어에 중복 저장됨

> 실무에서 수 GB 규모의 모델을 이미지에 직접 포함하는 경우는 거의 없다. 일반적으로 모델은 외부 스토리지(S3, GCS, NFS 등)에서 런타임에 로드하는 방식을 사용한다.

<br>

## 3. 추가 최적화의 한계

멀티스테이지 빌드도 고려했으나, 이미지 크기 개선보다 **모델 분리** 문제가 더 근본적이라 판단했다. 이미지를 아무리 최적화해도, 모델이 포함되어 있는 한 위의 문제들은 해결되지 않는다.

<br>

# 다음 단계

이미지 경량화만으로는 한계가 있다는 것을 깨달았다. 다음 글에서는 **모델을 이미지에서 분리**하는 방식을 다룬다:

- initContainer + ephemeral volume을 이용한 모델 다운로드
- initContainer + PV를 이용한 모델 파일 공유

이를 통해 이미지는 순수하게 애플리케이션 코드와 런타임만 포함하고, 모델은 런타임에 마운트하는 구조로 개선한다.

<br>

---

# 정리

| 항목 | Before | After | 개선 |
|------|--------|-------|------|
| 이미지 크기 | 18.5GB | 10.1GB | **-45%** |
| 풀링 시간 | 19분 | 12분 | **-33%** |
| 주요 변경 | devel 이미지 | runtime 이미지 | - |

핵심은 **devel → runtime 전환**이었다. 추론 서빙에는 컴파일 도구가 필요 없으므로, runtime 이미지를 사용하는 것이 맞다.

다만, 이것만으로는 충분하지 않았다. 모델이 이미지에 포함되어 있는 구조적 문제를 해결하기 위해, 다음 글에서 initContainer 기반의 모델 분리 방식을 다룬다.

