---
title:  "[Kubernetes] Kubernetes 환경에서의 Co-DETR 모델 추론 서빙 개선기 - 1. 개요"
excerpt: "Co-DETR 모델 추론 서빙을 개선하게 된 이유: Torchserve에서 FastAPI로의 전환, 그리고 발견한 문제점들"
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
  - time slicing
---



회사 MLOps 서비스에서 사용하는 모델의 추론 서빙 방식을 개선한 경험에 대해 정리하고자 한다. 

<br>

# 개요

회사 MLOps에서 고성능 객체 인식 모델 Co-DETR을 서빙한다. Attention을 객체 인식에 접목한 DETR 기반의 Transformer 모델로, 높은 정확도를 보이지만 무거워서 실시간 분석에는 부적합하다.

> 서비스 관점에서 보기에 꽤나 괜찮은 객체 인식 성능을 보여 준다. 자동차 안 운전석에 앉아 있는 사람이라던가, 건물 외벽 유리에 비친 사람까지도 잡아 낸다. 심지어 객체 크기가 아주 작아도 잡아 낸다.

<br>

여러 프레임워크에서 오픈 소스를 제공하는데, 우리는 [MMDetection](https://github.com/open-mmlab/mmdetection)의 [Co-DETR Large](https://download.openmmlab.com/mmdetection/v3.0/codetr/co_dino_5scale_swin_large_16e_o365tococo-614254c9.pth)를 사용한다. MMDetection은 OpenMMLab에서 개발한 PyTorch 기반 객체 탐지 프레임워크로, 다양한 최신 모델들을 쉽게 사용할 수 있도록 제공한다.

- 백본: Swin-L (Swin Transformer Large)
- 모델 크기: 900 MiB
- 파라미터: 2.18억 개
- **운영 특성**:
  - GPU 메모리: 피크 시 9~10GB (RTX 4090 24GB의 40%)
  - 추론 시간: 0.2초/프레임 (1280×720)
  - 실시간 처리: 어려움 (5 FPS)

<br>

고성능 LLM은 크기가 수백 Gi에 달하는 경우도 많고, 모델 파라미터 개수도 비교도 안 되게 많기 때문에 귀여워 보일 수 있지만, 그래도 내가 실무에서 만져봤던 모델 중에는 무거운 축에 속하는 모델이다. 초반에는 굉장히 초보적인 수준에서 모델을 서빙하다, 점차 문제점을 개선해 나갔다. 시간이 지나 돌이켜 보니 나중에 더 큰 모델을 서빙하기 위해서는 어떻게 해야 할까 생각하게 된 계기가 되었기에, 그 과정을 기록해 두고자 한다.



<br>

# 서빙 환경

- K3s + Docker: 현재는 containerd를 사용하고 있으나, 기존 레거시 시스템에서는 Docker를 컨테이너 런타임으로 사용했다
- GPU: RTX 4090 10장
- 서빙 프레임워크: FastAPI
  - 기존에 Torchserve를 이용해 서빙하다, 의존성 관리의 어려움과 mar 파일 특수성의 한계를 느껴, FastAPI를 이용해 직접 추론 API 서버를 만드는 방식으로 변경했다

<br>

# Torchserve

Pytorch 모델을 서빙하기 위한 서빙 프레임워크로, **프로덕션 환경에서 필요한 기능들을 내장**하고 있다.

- Dynamic batching: 여러 요청을 자동으로 묶어 처리
- 모델 버저닝 및 A/B 테스팅 지원
- Prometheus 메트릭 연동
- PyTorch 팀과 AWS가 공동 개발하여 TorchScript 등 PyTorch 고유 기능 지원 우수
- AWS SageMaker와 자연스러운 통합

특히 **단순한 PyTorch 모델 서빙에는 매우 효과적**이다.

<br>

## 우리 환경에서의 문제점

하지만 **MMDetection처럼 복잡한 의존성 체인을 가진 프레임워크와 함께 사용하면** 다음과 같은 문제들이 두드러진다.

<br>

### 1. 의존성 지옥

Torchserve를 사용하기 위해서는 아래 의존성이 정확히 맞아 떨어져야 한다.

```text
TorchServe
  ↓
PyTorch
  ↓
CUDA Toolkit
  ↓
cuDNN
  ↓
NVIDIA Driver
```

이 중 하나라도 호환성 매트릭스 상에서 맞지 않으면, 작동하지 않는다.

```bash
# 작동하는 조합
TorchServe 0.8.2
├─ PyTorch 2.0.1
│  ├─ CUDA 11.8
│  │  ├─ cuDNN 8.7
│  │  └─ NVIDIA Driver >= 520.61
│  └─ torchvision 0.15.2
└─ Python 3.10
```

```bash
# 작동하지 않는 조합
TorchServe 0.8.2
├─ PyTorch 2.0.1
│  ├─ CUDA 11.7  # ← 11.8 아님!
│  │  └─ Error: CUDA version mismatch!
```

<br>

게다가 MMDetection 프레임워크를 쓰면, MMDetection의 의존성 체인에 의한 추가 제약이 따른다.

```bash
mmdet==3.0.0
  ├─ mmcv-full==2.0.0
  │   ├─ torch==2.0.1
  │   ├─ CUDA 11.8
  │   └─ ...
  └─ mmengine==0.7.0
```

<br>

초보자 입장에서, 프레임워크를 파악하기 전에, 돌려보는 것부터가 너무 힘들다. 기능 탐구는 고사하고, 갖가지 에러를 마주하게 된다.

- CUDA 버전 불일치: `CUDA error: no kernel image is available for execution on the device`
- mmcv 컴파일 실패: `ERROR: Could not build wheels for mmcv-full`
- torchserve 버전 충돌: `ImportError: cannot import name 'packaging_version' from 'pkg_resources'`
- ...


<br>

### 2. 설정의 복잡성

Torchserve는 프로덕션에 필요한 기능들을 내장하고 있지만, **제대로 된 성능을 내기 위해서는 섬세한 설정이 필요**하다.

<br>

예를 들어, Dynamic Batching을 활성화하기 위해서는 아래와 같이 설정해야 한다.

```properties
# config.properties
batch_size=32           # 최대 배치 크기
batch_delay=2           # 대기 시간 (ms 또는 초)
default_workers_per_model=2
```

<br>

실제 실험한 결과, 1280*720 프레임 기준으로 Dynamic Batching 적용 시 배치 크기에 따라 성능이 개선되는 것을 확인할 수 있다:

| 설정 | 프레임 수 | 총 소요 시간 | 프레임당 추론 시간 |
|------|----------|------------|-----------------|
| 기본 (설정 없음) | 1 | 0.5초 | 0.5초 |
| batch_size=32, batch_delay=2 | 32 | 14.4초 | **0.45초** |
| batch_size=64, batch_delay=4 | 64 | 27.8초 | **0.43초** |

<br>

하지만 초기에는 아래와 같은 문제가 있었다.
- 의존성 문제로 Torchserve를 실행하는 것만으로도 벅참
- 설정 최적화까지 신경 쓸 여유가 없었음

<br>

**3. mar 파일의 번거로움**

Torchserve에서 추론을 하기 위해서는 handler class를 작성해야 한다. `initialize`, `preprocess`, `inference`, `postprocess` 4개의 메서드를 구현해야 한다.

```python
class MMdetHandler(BaseHandler):
    def initialize(self, context):
        """모델 로드 및 초기화"""
        model_dir = properties.get('model_dir')
        checkpoint = os.path.join(model_dir, serialized_file)
        self.model = init_detector(config_file, checkpoint, self.device)
    
    def preprocess(self, data):
        """요청 데이터를 모델 입력 형태로 변환"""
        images = []
        for row in data:
            image = row.get('data') or row.get('body')
            if isinstance(image, str):
                image = base64.b64decode(image)
            image = mmcv.imfrombytes(image)
            images.append(image)
        return images
    
    def inference(self, data):
        """모델 추론 실행"""
        return inference_detector(self.model, data)
    
    def postprocess(self, data):
        """추론 결과를 응답 형태로 변환"""
        output = []
        for data_sample in data:
            # bbox, labels, scores 추출
            pred_instances = data_sample.pred_instances
            # threshold 적용 및 포맷팅
            # ... (생략)
        return output
```

<br>
handler를 작성하고 나면, 작성한 handler와 모델 파일을 `.mar` 파일로 패키징해야 한다:

```bash
torch-model-archiver --model-name co_detr \
  --version 1.0 \
  --serialized-file model.pth \
  --handler mmdet_handler.py \
  --extra-files config.py \
  --export-path model-store/
```

<br>

이후 Torchserve를 재시작해야 반영된다:

```bash
torchserve --stop
torchserve --start --model-store model-store/ --models all
```

<br>
여기서 느낀 문제점은 아래와 같다.

1. **프레임워크 종속적인 구조**
   - Torchserve의 handler 구조에 맞춰 작성해야 함
   - `context`, `properties`, `manifest` 등 Torchserve 전용 객체 사용
2. **모델 변경 시마다 반복 작업**
   - 새 모델 추가할 때마다 handler 새로 작성
   - preprocess/postprocess 로직이 모델마다 다를 수 있음
3. **mar 파일 빌드 필수**

<br>

## 우리의 선택

이러한 이유로 우리 팀은 FastAPI로 전환했다. Torchserve가 나쁜 프레임워크가 아니라, **우리 상황(MMDetection + 서비스 기능 실험을 위한 잦은 모델 변경 + 커스텀 로직 필요)에 맞지 않았다**는 것이 더 정확한 표현이다.

<br>

# FastAPI

FastAPI를 선택한 이유는 팀 내에서 모델 서빙 프레임워크에 종속되지 말아 보자는 합의가 있었기 때문이다. 주로,

- 팀에서 원하는 방식으로 추론 입출력 전처리 및 후처리를 할 수 있다
- 이미지 Batch 처리를 원하는 방식으로 할 수 있다
- 모델을 직접 다루는 과정에서 파일 저장 등 커스텀 로직을 구현할 수 있다

와 같은 이유였다.

<br>

## 추론 성능 비교

그렇다고 하더라도, 추론 성능이 떨어지면 FastAPI를 사용할 수 없다. 확인을 위해 실제 측정한 결과, 1280×720 해상도 이미지 한 장당, **FastAPI가 2배 이상 빠르다.**


| 프레임워크 | 프레임당 추론 시간 | 비고 |
|-----------|-----------------|------|
| **FastAPI** | **0.2초** | 요청 즉시 처리 |
| Torchserve + Dynamic Batching | 0.43초 | 배치 오버헤드 |

<br>

> 참고: 왜 FastAPI가 더 빠를까?
>
> Torchserve의 Dynamic Batching은 **고트래픽 환경**에서 GPU 활용률을 높이기 위한 기능이다. 초당 수십~수백 개의 요청이 들어올 때, 이들을 묶어서 배치 처리하면 GPU를 효율적으로 사용할 수 있다.
> 
> 하지만 **저트래픽 환경**에서는 오히려 역효과가 발생할 수도 있다.
>
> ```
> [고트래픽]
> 요청 100개/초 → 32개씩 묶음 → GPU 병렬 처리 → 효율 증가
> 
> [저트래픽]  
> 요청 1개 도착 → batch_delay 대기 (다른 요청 기다림)
>            → 타임아웃 → 1개만 처리
>            → 불필요한 지연 발생
> ```
> 
> **FastAPI**가 요청을 즉시 처리하고 프레임워크 오버헤드가 최소화되어, 우리 상황과 같은 저트래픽 환경에서 더 빠른 성능을 보인 게 아니었을까 싶다.

<br>

## FastAPI의 장점

```python
# 모델 로드
model = init_detector(config, checkpoint, device)

# 추론 엔드포인트
@app.post("/inference")
async def inference(images: List[UploadFile]):
    # 전처리
    img_arrays = [await img.read() for img in images]
    
    # 추론
    results = inference_detector(model, img_arrays)
    
    # 후처리 (원하는 대로)
    return custom_postprocess(results)
```

- 코드 수정 → 재시작만 하면 즉시 반영
- 전처리/후처리를 원하는 대로 커스터마이징
- 디버깅 용이 (일반 Python 코드)
- 별도의 서빙 프레임워크 학습 부담이 적음

<br>

## FastAPI의 단점

다만, 추론 서빙 프레임워크 없이 기능을 직접 구현해야 했기에, 아래와 같은 한계가 있었다.

1. **Dynamic Batching 부재**
   - Torchserve는 동시 요청을 자동으로 묶어 배치 처리
   - FastAPI는 직접 큐 기반 배치 처리를 구현해야 함
   - 구현하지 않으면 GPU 활용률이 낮아짐

2. **모니터링 인프라 부재**
   - Prometheus 메트릭, 구조화된 로깅을 직접 구현
   - Torchserve는 `/metrics` 엔드포인트 자동 제공

3. **동시성 처리의 복잡성**
   - MMDetection의 추론 함수가 순차적으로 실행되는 방식이라서, FastAPI의 동시 요청 처리와 맞지 않음
   - 여러 요청을 동시에 처리하려면 별도의 스레드 풀 등을 구성해야 함

<br>

## 솔직한 회고

**솔직히 말하면**, 당시에는 Torchserve를 세밀하게 다뤄 볼 여유가 없었다:

- 의존성 문제로 3주 소요 → 설정 최적화까지 엄두 안 남
- mar 파일 재빌드 부담 → 잦은 모델 실험에 병목
- 빠른 서비스 출시 압박 → 추론 서빙은 자동 라벨링 기능의 일부였기에, 일단 돌아가게만 만들고 기능 기획과 백엔드 API 개발에 집중해야 했음

<br>

FastAPI로 전환한 후, 결과적으로 **당시에 더 중요했던 서비스 기획 및 기능 개발에 집중할 수 있었다**. 

나중에 서비스 기획이 안정되고 기능 변경이 줄어든 시점에, 회고 차원에서 Torchserve를 다시 들여다봤다. 당시에 보지 못했던 것들이 보였고, 조금만 더 여유가 있었다면 다르게 접근할 수 있지 않았을까 하는 아쉬움이 진하게 남는다. 

<br>

**완벽한 선택이 아니라, 당시 상황에서 최선의 선택**이었다. 

<br>

# 문제점

이렇게 FastAPI를 이용해 쿠버네티스 환경에서 Co-DETR 추론 서빙을 진행하던 도중, 아래와 같은 문제를 발견했다.
- 서빙 이미지가 너무 무겁다
- GPU 활용률이 너무 낮다

<br>

## 1. 서빙 이미지가 너무 무겁다

Co-DETR 추론 서빙용 Docker 이미지가 **18.5GB**에 달했다. 새로운 노드에 파드가 스케줄링될 때마다 이미지 풀링에 약 19분이 소요되었고, 이는 빠른 배포와 장애 복구에 큰 부담이 되었다.

자세한 원인 분석과 개선 과정은 **[2편. Docker 이미지 경량화](/dev/Dev-Kubernetes-CoDETR-Inference-Experience-2/)**에서 다룬다.

<br>

## 2. GPU 활용률이 너무 낮다

RTX 4090 24GB GPU 10개를 보유하고 있었지만, 실제 활용률은 매우 낮았다.

<br>

### GPU 메모리 활용률

Co-DETR 모델을 추론하는 FastAPI 파드의 GPU 메모리 사용량을 측정한 결과는 다음과 같다.

- 모델 로드 시: **2.4GB**
- 추론 평균: **7.4GB**  
- 추론 피크: **9.6GB**

즉, 24GB 중 최대 9.6GB만 사용하여 **메모리 활용률이 40% 수준**이었다. 나머지 14GB 이상의 메모리가 유휴 상태로 남아있었다.

<br>

# 개선 작업

이러한 문제를 해결하기 위해 아래와 같은 작업을 진행했다. 

1. 단일 파드 추론 개선: 하나의 파드 내에서 추론이 이루어지는 방식 자체를 개선
  1. 추론 서빙 이미지 개선
  2. initContainer + ephemeral volume을 이용한 모델 다운로드 방식 도입
  3. initContainer + PV를 이용한 모델 파일 공유 방식 도입
2. 클러스터 차원에서의 GPU 활용률 개선: RTX 4090 GPU 10장의 활용률을, 최대한 높이기 위한 개선
  1. FastAPI worker 수 증가
  2. Time Slicing 적용
  3. FastAPI worker 수 증가 + Time Slicing 적용

> 진행하면서, 왜 실무에서 권장되는 방법론에 대한 사전 조사 없이 이렇게 서빙을 하고 있었을까 반성했다. 특히, **FastAPI worker 수 증가**는, 기존에 고려하지 못하다가 최근에 우연한 계기로 알게 되어 사후적으로 진행해 본 방식이다. FastAPI를 이용해 추론 서빙을 하고 있었으면서도, 이 방법을 고려해 보지 못했다는 게 부끄러웠다. 개발 속도가 빨라야 했고, 팀 차원에서도 맨 땅에 헤딩하듯 진행하던 일이었으니 어쩔 수 없다고 위안을 삼아 보지만, 이제는 그러지 말아야겠음을 뼈저리게 깨닫는다.

<br>

더 해봤으면 좋겠지만 진행해 보지 못하거나 혹은 진행하지 않은 것은 다음과 같다.

1. 이미지 멀티 스테이지 빌드: `1.1.` 추론 서빙 이미지 개선 과정에서 진행해 보고 싶었으나, 해당 단계를 진행하던 도중, 이미지 빌드를 더 파는 것은 서빙 성능 개선에 큰 효과가 없겠다 싶어 다음 단계로 넘어 갔다. 
2. NFS 기반 모델 파일 공유: `1.3.` 이후에, PV 말고 네트워크 기반으로 공유 가능한 스토리지를 이용해 서빙하는 게 1단계에서는 최선일 것이라는 생각이 들었다. 다만, 아직 NFS에 대해 잘 몰라서 진행해 보지 못했다. 추론 서빙 시 실무에서 자주 사용되는 방법이라고 들어, 어떻게든 기회를 마련해 도입해 보고 싶다.
3. MIG: `2.2.` 진행 과정에, GPU 분할에 대해 파보게 되며 진행해 보고 싶었으나, MIG가 지원되는 GPU를 접할 수 없어 진행해 보지 못했다.

<br>

# 앞으로의 계획

지금은 위의 개선 내용을 적용하여, FastAPI 기반의 추론 서빙을 어느 정도 안정적으로 운영 중이다. 다만, 위에서 기술했듯 우리의 구현에 단점이 명확하고, 대규모 환경에서는 서빙 프레임워크를 쓰는 것이 일반적이기 때문에, 지금의 상황이 최선이라고 생각하지 않는다.

<br>

추론 서빙을 개선하는 동안 시간이 지난 만큼, 서비스 기획과 기능도 수 차례 바뀌어 왔다. 현재 형상에서 서비스 트래픽이 많은 상황이 아니기 때문에, 굳이 다시 Torchserve로 전환할 이유는 없어 보인다. 다만, **트래픽이 급증하면**, Triton으로의 전환을 고려하고 있다.

<br>

Triton을 고려하는 이유는 다음과 같다:
- Torchserve에 비해 다양한 모델 포맷을 지원한다
- Model Repository 기능을 지원하여, 모델 추가가 쉽다
- NVIDIA GPU에 최적화되어 있다
- 모델 버저닝, A/B 테스팅 등 프로덕션 기능이 지원된다

<br>
예상하는 전환 시점은, 다음과 같다:
- 일 요청 > 10,000건 (초당 수십 건 이상)
- 여러 모델을 동시에 서빙해야 할 때
- GPU 리소스 효율성이 비즈니스에 critical할 때

<br>
다만, 이제는 추론 서빙 운영에 대한 이해도가 예전보다는 늘었고, 서비스 형상이 급격하게 변화할 일은 적을 것이라 보이기에, Triton 전환을 대비해 선제적으로 학습해야 하지 않을까 생각한다. 또 다시 학습 부담으로 인해 최선이 아닌 선택을 하게 되는 상황을 막기 위해서.

<br>

---

# 참고: 리소스 이해 및 모니터링

추론 서빙을 개선하는 과정에서, 다양한 리소스 모니터링 명령어를 사용하고, 메모리 사용량을 기준으로 개선 효과를 측정할 필요가 있었다.

이에, **[1.5편. 배경 지식: 추론 서빙의 리소스 사용 이해](/dev/Dev-Kubernetes-CoDETR-Inference-Experience-1-5/)**에서 아래와 같은 사항을 다뤄 보고자 한다:

- 추론 파이프라인에서 GPU 메모리와 시스템 메모리(RAM)가 각각 어떻게 사용되는지
- `kubectl top`, `ps aux`, `free -h`, `nvidia-smi` 등 명령어별로 측정하는 대상이 어떻게 다른지
- Kubernetes 리소스 설정 시 어떤 값을 기준으로 해야 하는지

