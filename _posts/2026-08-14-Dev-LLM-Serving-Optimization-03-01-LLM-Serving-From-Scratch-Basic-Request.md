---
title: "[LLM] LLM 서빙과 최적화: 단일 모델 서빙 시스템 - 3.1. 기본 생성 요청: 첫 기동과 낮은 처리량"
excerpt: "서비스를 직접 기동해 프로세스 구조를 관찰하고, 부하 테스트로 단일 워커의 순차 처리 병목을 재현해 보자."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - LLM-Serving
  - Transformers
  - Hugging-Face
  - Load-Test
  - vLLM
  - Apple-Silicon
  - Hands-On-LLM-Serving-and-Optimization-Study
  - Hands-On-LLM-Serving-and-Optimization-Study-Week-2
last_modified_at: 2026-08-15
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Hands-On LLM Serving and Optimization Study (LLMSO) 2주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- 실습은 Mac(Apple Silicon)에서 진행했다. vLLM은 Mac(공식 wheel 없음)과 Linux GPU 서버(Blackwell 세대 ↔ 실습 고정 버전 핀 불일치) 양쪽에서 손쉽게 뜨지 않아, 시간 제약상 트러블슈팅을 접고 lazy import로 우회해 vLLM 경로 실습은 제외했다
- 기동하면 프로세스가 3개 보인다: FastAPI 부모, multiprocessing resource_tracker, 그리고 ModelWorker 자식. 부모에는 모델이 없다 — [2편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-02-LLM-Serving-From-Scratch-Structure %})에서 코드로 본 프로세스 격리가 프로세스 목록으로 그대로 보인다
- 모델 로딩 로그에서 Hugging Face `from_pretrained()`가 받아 오는 파일들(config, 가중치, 토크나이저 3종)을 해부했다. 캐시를 열어 보면 transformers가 .bin 가중치 로드 후 백그라운드로 safetensors 변환본까지 받아 두는 동작도 관찰된다
- `/basic_generate`는 잘 동작하고, 생성 결과가 책 예제와 완전히 같다 — 기본값이 greedy decoding이라 출력이 결정적이기 때문이다
- hey 부하 테스트로 동시성을 1에서 10으로 늘려도 처리량은 약 0.9 req/s로 고정되고 p90 지연만 1.5초에서 11.2초로 늘었다. 단일 워커의 순차 처리 병목이 명확하게 재현됐다

<br>

# 실습 환경

[2편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-02-LLM-Serving-From-Scratch-Structure %})에서 해부한 코드를 이제 실제로 돌린다. 실습 환경은 Mac(Apple Silicon)이고, Python 3.12 가상 환경을 사용했다.

```shell
~$ cd ch03/single_model_llm_serving
~$ python3.12 -m venv venv
~$ source venv/bin/activate
~$ pip install -r requirements.txt
```

원본 `requirements.txt`와 달리 vLLM은 별도 파일로 분리했다. Apple Silicon에는 vLLM 공식 wheel이 없어 설치가 간단치 않고([트러블슈팅](#트러블슈팅) 참고), 4개 엔드포인트 중 vLLM이 필요한 것은 `/generate_vllm` 하나뿐이라, 나머지 세 엔드포인트 실습을 위해 vLLM까지 설치하지는 않았다.

```bash
# requirements.txt — vllm을 분리한 버전
# vllm 은 CUDA 전제라 macOS(Apple Silicon)에서는 wheel 이 없고 소스 빌드도 실패한다
#   (cmake --build . --target=_C → exit 134).
# Linux + NVIDIA GPU 에서 /generate_vllm 까지 하려면: pip install -r requirements-vllm.txt
setuptools==77.0.3
fastapi==0.115.12
uvicorn==0.24.0
pydantic==2.11.5
transformers==4.52.4
torch==2.7.0
numpy==1.26.4
debugpy==1.8.0
pytest==8.4.0
httpx==0.27.0
pytest-asyncio==1.0.0
```

PyTorch가 Apple Silicon의 GPU 백엔드(MPS, Metal Performance Shaders)를 인식하는 것도 확인해 둔다.

```shell
~$ python -c "import torch; print(torch.backends.mps.is_available())"
True
```

<br>

# 서버 기동과 프로세스 관찰

## 기동 로그 해부

`python main.py`로 서버를 띄우면, 2편에서 코드로 읽었던 초기화 순서가 로그로 흘러나온다. 모델을 처음 받는  단계의 로그다 (경로·호스트명은 정리했다).

```shell
~$ python main.py
2026-08-12 00:50:35,918 - llm.model_executor - DEBUG - ModelExecutor initialized with queues
2026-08-12 00:50:35,918 - llm.model_executor - DEBUG - Setting up worker with model: facebook/opt-125m
2026-08-12 00:50:35,918 - llm.model_executor - DEBUG - Starting worker process
2026-08-12 00:50:35,925 - llm.model_executor - DEBUG - Worker process started
INFO:     Started server process [30553]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
2026-08-12 00:50:38,341 - llm.model_worker - DEBUG - Waiting for debugger to attach...
2026-08-12 00:50:38,342 - llm.model_worker - DEBUG - Debugger attached!
2026-08-12 00:50:38,342 - llm.model_worker - DEBUG - Loading model facebook/opt-125m on device cpu
config.json: 100%|█████████████| 651/651 [00:00<00:00, 6.44MB/s]
pytorch_model.bin: 100%|███████| 251M/251M [00:25<00:00, 9.98MB/s]
generation_config.json: 100%|██| 137/137 [00:00<00:00, 1.80MB/s]
tokenizer_config.json: 100%|███| 685/685 [00:00<00:00, 9.81MB/s]
vocab.json: 899kB [00:00, 1.03MB/s]
merges.txt: 456kB [00:00, 1.21MB/s]
special_tokens_map.json: 100%|█| 441/441 [00:00<00:00, 7.09MB/s]
2026-08-12 00:51:13,921 - llm.model_worker - DEBUG - Worker initialized
2026-08-12 00:51:13,922 - llm.model_worker - DEBUG - Waiting for batch from queue...
model.safetensors: 100%|███████| 251M/251M [00:21<00:00, 11.6MB/s]
```

로그 순서대로 살펴 보자.

- **`model_executor` 로그가 먼저 나온다.** 부모 프로세스에서 `LLMEngine.__init__` → `ModelExecutor` 생성(큐 준비) → `setup_worker()`(자식 프로세스 start)가 순서대로 실행되기 때문이다. `Worker process started`는 자식 기동을 "요청"한 시점이고, 실제 자식이 임포트를 마치고 살아나는 데는 시간이 걸린다
- **그 사이 uvicorn이 먼저 뜬다.** 자식 프로세스 초기화는 비동기로 진행되므로, 부모는 곧바로 서버 기동 로그(`Uvicorn running...`)까지 진행한다. HTTP 포트는 열렸지만 모델은 아직 로딩 중인 구간이 존재한다는 뜻이다 — 프로덕션이라면 readiness 체크가 필요한 지점이다
- **3초 뒤부터 `model_worker` 로그가 나온다.** 여기서부터는 자식 프로세스의 출력이다. 모델 로딩과 다운로드가 전부 자식에서 일어난다
- `Waiting for debugger to attach... / Debugger attached!`는 실제 debugpy 연결 코드가 없는 **죽은 로그 문구**다(2편에서 코드로 확인). 디버깅 실험의 흔적으로 보인다

다운로드된 파일들은 `from_pretrained()` 한 줄이 실제로 무엇을 가져오는지 보여 준다.

| 파일 | 크기 | 정체 |
|---|---|---|
| config.json | 651B | 모델 구조 하이퍼파라미터 — opt-125m은 12 레이어, hidden 768, 헤드 12다. [1주차에 본 KV cache 공식]({% post_url 2026-08-05-AI-LLM-Optimization-02-01-LLM-Transformer-Overview %})의 상수들이 여기서 온다 |
| pytorch_model.bin | 251MB | 가중치 본체. 1.25억 파라미터 × fp32(4바이트) ≈ 500MB가 아니라 251MB인 것은 저장이 fp16이기 때문이다 (config.json의 `torch_dtype: float16`으로 확인) |
| generation_config.json | 137B | `generate()`의 기본 생성 설정 (max_length, 샘플링 여부 등) |
| tokenizer_config.json, special_tokens_map.json | 각 수백 B | 토크나이저 설정과 특수 토큰 정의 |
| vocab.json | 899KB | BPE 어휘 사전 — 토큰 문자열 → id 매핑 |
| merges.txt | 456KB | BPE 병합 규칙 — [1주차 임베딩 글]({% post_url 2026-08-05-AI-LLM-Optimization-02-03-Transformer-Explainer-Embedding %})에서 본 토큰화가 실제로 이 두 파일로 동작한다 |

마지막 줄이 흥미롭다. 워커 초기화가 끝난 **뒤에** `model.safetensors` 251MB가 한 번 더 받아진다. 로컬 캐시를 열어 보면 어떤 파일인지 확인할 수 있다.

```shell
# 캐시에 스냅샷(리비전)이 두 개 생겼다
~$ ls ~/.cache/huggingface/hub/models--facebook--opt-125m/snapshots/*/
.../27dcfa74d334bc.../:   # refs/main이 가리키는 리비전 — 실제 로드에 사용
config.json  generation_config.json  merges.txt  pytorch_model.bin  ...
.../1f9886ce095904.../:   # 별도 리비전 — 워커 초기화 17초 뒤에 받아짐
model.safetensors
```

opt-125m 저장소의 main 리비전에는 safetensors 포맷이 없어서 transformers가 pytorch_model.bin을 받아 로드했고, 그 직후 **백그라운드 스레드로 허브의 safetensors 변환본(별도 리비전)을 미리 받아 둔** 것이다. safetensors는 pickle 기반 .bin의 임의 코드 실행 위험을 제거한 가중치 직렬화 포맷으로, transformers는 가능하면 이쪽을 우선한다. 지금은 "가중치 파일에는 두 포맷이 있고, safetensors가 안전해서 선호된다" 정도면 충분하고, 포맷 내부 구조까지는 이 실습 범위 밖이다.

## 프로세스 트리 확인

서버가 뜬 상태에서 프로세스를 확인한다. Linux 예시들이 쓰는 `ss` 대신 Mac에서는 `lsof`를 쓴다.

```shell
# 8000 포트 리슨 확인
~$ lsof -nP -iTCP:8000 -sTCP:LISTEN
COMMAND   PID   USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
Python  30553 my-user  20u  IPv4 0x744d7a9c7af14579      0t0  TCP *:8000 (LISTEN)

# 메인 프로세스와 그 자식들
~$ ps -axo pid,ppid,rss,%cpu,%mem,state,etime,command | awk -v pid=30553 'NR==1 || $1==pid || $2==pid'
  PID  PPID    RSS  %CPU %MEM STAT     ELAPSED COMMAND
30553 93922  56352   0.0  0.2 S+         11:13 .../Python main.py
30797 30553   7856   0.0  0.0 S+         10:56 .../Python -c from multiprocessing.resource_tracker import main;main(4)
30798 30553  70304   0.0  0.2 S+         10:56 .../Python -c from multiprocessing.spawn import spawn_main; spawn_main(...) --multiprocessing-fork
```

프로세스 세 개의 정체는 다음과 같다.

- **30553 — FastAPI 메인 서버 (부모).** 2편에서 본 대로 여기에는 모델이 없다
- **30797 — multiprocessing resource_tracker.** 파이썬 multiprocessing이 공유 자원(세마포어 등)의 누수를 정리하려고 자동으로 띄우는 보조 프로세스다
- **30798 — ModelWorker (자식).** 커맨드라인이 `main.py`가 아니라 `spawn_main`으로 보이는 이유는 macOS의 기본 프로세스 시작 방식이 `spawn`이기 때문이다. spawn은 새 인터프리터를 띄워 필요한 것만 다시 임포트하므로 커맨드라인에 spawn_main이 노출된다. 반면 Linux의 기본값은 `fork`라서 자식의 커맨드라인이 부모와 똑같이 `python main.py`로 보인다 — 아래 예시와의 차이 중 하나다

`STAT`의 `S+`는 에러가 아니라 요청을 기다리며 잠들어 있다는 뜻이고, RSS가 부모 약 55MB·워커 약 69MB 수준인 것은 이 시점 워커가 아직 요청을 받기 전이기 때문이다(모델 텐서가 실제로 접근되기 전이라 상주 메모리에 다 잡히지 않는다).

스터디 실습 자료의 예시(Linux + NVIDIA GPU, vLLM 포함 원본 코드)와 비교하면 그림이 다르다.

<details markdown="1">
<summary><b>스터디 자료 예시: Linux + GPU 환경의 프로세스와 GPU 메모리</b></summary>

```shell
# 스터디 실습 자료 예시 출력 (Linux, RTX 4070 16GB, vLLM 포함)
~$ ps auxf | tail -n 3
root  30195  ... \_ venv/bin/python main.py     # 부모: uvicorn + FastAPI
root  30237  ...     \_ venv/bin/python main.py # 자식 1: ModelWorker (GPU 788MiB)
root  30323  ...     \_ venv/bin/python main.py # 자식 2: vLLM EngineCore (GPU 13,762MiB)

~$ nvidia-smi
# Processes:
#   PID 30237  C  venv/bin/python    788MiB     ← transformers ModelWorker
#   PID 30323  C  venv/bin/python  13762MiB     ← vLLM EngineCore
# 부모(30195)는 GPU 미사용
```

- ModelWorker(788MiB): opt-125m은 1.25억 파라미터짜리 작은 모델이라 GPU 메모리를 많이 쓰지 않는다
- vLLM EngineCore(13.7GiB): vLLM 0.9(V1 아키텍처)는 단일 GPU여도 모델 실행을 별도 EngineCore 프로세스로 분리한다. 메모리가 큰 이유는 모델이 커서가 아니라(가중치는 0.24GiB), `gpu_memory_utilization` 기본값 0.9에 따라 **KV 캐시용으로 GPU 메모리의 90%를 미리 선점**하기 때문이다
- 부모 프로세스는 GPU를 전혀 쓰지 않는다 — CPU 오케스트레이션/GPU 연산 격리가 nvidia-smi에서도 확인된다

</details>

내 환경과 예시의 차이는 세 가지로 정리된다. 명령어가 다르고(`ss` → `lsof`, `ps auxf` → `ps -axo`), 자식 프로세스 이름이 다르게 보이며(fork vs spawn), **vLLM EngineCore 프로세스가 없다**. 마지막 것은 vLLM을 설치하지 않았으니 정상이다.

<br>

# 실습: 기본 생성 요청

이제 몇 가지 테스트 케이스로 `/basic_generate` API가 예상대로 동작하는지 확인한다.

```shell
~$ curl -s -X POST http://localhost:8000/basic_generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello, I am"}' | jq
{
  "generated_text": "Hello, I am a student at the University of California, Berkeley. I am a"
}
```

동작한다. 요청 하나가 Sequence로 포장되어 task_queue를 건너 자식 프로세스에서 추론되고, result_queue로 돌아오는 [2편의 경로]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-02-LLM-Serving-From-Scratch-Structure %}) 그대로다.

![기본 생성 요청 처리 중 리소스 사용 관찰]({{site.url}}/assets/images/llmso-single-model-serving-basic-generate-resource-usage.gif){: .align-center}

<center><sup>기본 생성 요청을 처리하는 동안의 프로세스 리소스 사용 변화. 직접 캡처</sup></center>

## 왜 출력이 책 예제와 똑같은가

처음 봤을 때 의아했던 점 — 내 Mac에서 생성한 결과가 책 예제의 출력과 **토씨 하나까지 같다**. 답은 디코딩 방식에 있다. 이 서비스의 `model.generate()` 호출은 샘플링 옵션을 켜지 않았고, transformers의 기본값은 `do_sample=False`, 즉 **greedy decoding**이다. 매 스텝에서 확률이 가장 높은 토큰 하나만 고르므로, 같은 가중치에 같은 프롬프트를 넣으면 언제 어디서 돌려도 같은 토큰열이 나온다.

[1주차 출력층 글]({% post_url 2026-08-05-AI-LLM-Optimization-02-07-Transformer-Explainer-Output %})에서 본 temperature나 top-k 같은 샘플링 노브는 `do_sample=True`일 때 비로소 개입한다. 반대로 말하면, 서빙 시스템을 검증하는 지금 같은 상황에서는 greedy의 결정론이 오히려 유용하다 — 출력이 달라지면 모델 문제가 아니라 시스템 문제라고 바로 좁힐 수 있기 때문이다.

그렇다면 ChatGPT나 Claude는 왜 같은 질문에도 매번 다르게 답할까. 상용 챗 서비스는 반대로 **샘플링을 켠다.** `temperature`를 0보다 크게 두어 확률 분포를 평탄하게 만들고, `top-p`(nucleus)·`top-k`로 후보를 추린 뒤 그 안에서 무작위로 뽑는다. 매 스텝이 난수 추출이라, **seed를 고정하지 않으면** 같은 프롬프트라도 실행마다 다른 토큰열이 나온다. 이건 버그가 아니라 의도된 설계다 — greedy 출력은 반복적이고 단조로워서, 다양성과 창의성을 위해 일부러 무작위성을 넣는 것이다(일부 API는 재현용 `seed` 옵션을 따로 제공한다).

> 한 가지 더 — `temperature=0`(greedy)으로 두어도 프로덕션에서는 완전한 재현이 보장되지 않는다. GPU 커널이 배치 구성·병렬화에 따라 부동소수점 덧셈 순서를 바꾸고, 부동소수점은 결합법칙이 성립하지 않아(`a+b+c ≠ a+c+b`) 로짓이 미세하게 흔들리기 때문이다. continuous batching으로 같이 묶이는 다른 요청이 달라지면 내 결과의 argmax가 뒤집힐 수도 있다. 이 batch invariance 문제는 서빙 재현성의 별도 주제라, 여기서는 "greedy도 프로덕션에선 완전 결정론이 아니다"까지만 짚어 둔다.

## 테스트 스위트 실행

[2편에서 코드로 읽은 테스트]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-02-LLM-Serving-From-Scratch-Structure %})도 실제로 돌려 봤다.

```shell
~$ venv/bin/python -m pytest tests/test_api.py -v
# 실행 결과 (핵심 발췌)
tests/test_api.py::test_generate PASSED                                  [ 25%]
tests/test_api.py::test_generate_batch PASSED                            [ 50%]
tests/test_api.py::test_generate_stream PASSED                           [ 75%]
tests/test_api.py::test_generate_stream_concurrent PASSED                [100%]
======================== 4 passed, 2 warnings in 39.01s ========================
```

4개 테스트(기본 생성, 배치, 스트리밍, 동시 스트리밍)가 모두 통과한다. 39초가 걸린 것은 테스트가 모킹 없이 진짜 엔진과 모델을 띄우는 통합 테스트이기 때문이다. 경고 2건은 httpx 0.27의 `AsyncClient(app=...)` 문법이 deprecated라는 내용으로, 기능에는 영향이 없다.

다만 부산물이 하나 있었다. `4 passed`가 찍힌 뒤에도 **pytest 프로세스가 종료되지 않았다.** 프로세스를 확인해 보니 테스트가 띄운 ModelWorker 자식(spawn_main)과 resource_tracker가 그대로 살아 있었다.

```shell
~$ ps -axo pid,ppid,etime,stat,command | awk 'NR==1 || $2==46024 || $1==46024'
  PID  PPID  ELAPSED STAT COMMAND
46024 46023    07:52 S    .../Python -m pytest tests/test_api.py -v      # 테스트는 39초에 끝났는데 살아 있음
46135 46024    07:46 S    .../Python -c from multiprocessing.resource_tracker import main;main(12)
46136 46024    07:46 S    .../Python -c from multiprocessing.spawn import spawn_main; spawn_main(...)
```

원인은 워커의 구조다. ModelWorker는 `while True`로 큐를 기다리는 무한 루프이고 비데몬(mp.Process 기본값) 프로세스라서, 부모 인터프리터가 종료 시점에 자식 join을 기다리며 멈춘다. `python main.py`로 직접 실행할 때는 SIGINT/SIGTERM 시그널 핸들러가 cleanup을 호출하지만, pytest 경유 실행에서는 이 정리 경로가 워커를 끝내 주지 못한 것으로 보인다. 자식 프로세스를 만드는 서빙 코드는 **정상 경로만큼 종료 경로가 중요하다**는 것을 테스트가 덤으로 보여 준 셈이다.

vLLM 경로 테스트는 예상대로 임포트 단계에서 실패한다. 환경 제약이 테스트 결과로도 확인된다.

```shell
~$ venv/bin/python -m pytest tests/test_vllm.py -v
# 실행 결과 (핵심 발췌)
E       ModuleNotFoundError: No module named 'vllm'
========================= 3 failed, 1 passed in 2.50s ==========================
```

<br>

# 검증: 낮은 처리량 재현

교재는 이 서비스를 그대로 운영하면 **가장 먼저 마주칠 문제가 낮은 처리량**이라고 말한다. 재현해 본다. 간단한 HTTP 부하 테스트 도구 [hey](https://github.com/rakyll/hey)를 쓴다.

```shell
~$ brew install hey

# 동시 1개씩, 총 5개 요청
~$ hey -n 5 -c 1 -t 300 \
  -m POST \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello, I am"}' \
  http://localhost:8000/basic_generate
```

옵션은 `-n`(총 요청 수), `-c`(동시 요청 수), `-t`(요청별 제한 시간)다. 결과를 읽을 때 보는 곳은 네 군데다 — Summary의 `Total`(전체 소요)과 `Requests/sec`(처리량), Latency distribution의 p50/p90(중앙값과 꼬리 지연), Response time histogram(완료 시각 분포), 그리고 Details의 `resp wait`(서버 응답 대기 — 병목이 네트워크인지 서버인지 가른다).

첫 실행 결과의 핵심 부분이다.

```shell
# 실행 결과 (핵심 발췌)
Summary:
  Total:        5.9244 secs
  Average:      1.1849 secs
  Requests/sec: 0.8440

Details (average, fastest, slowest):
  resp wait:    1.1838 secs, 1.1013 secs, 1.2608 secs

Status code distribution:
  [200] 5 responses
```

요청 하나에 약 1.2초, 처리량 약 0.84 req/s가 이 서비스의 기준선이다. 이제 총 요청을 10개로 고정하고 동시성만 1, 2, 5, 10으로 올려 가며 반복한다.

| 동시 요청 | 총 시간 | 평균 응답 | p50 | p90 | 처리량 |
|---|---|---|---|---|---|
| 1 | 11.26초 | 1.13초 | 1.06초 | 1.54초 | 0.888 req/s |
| 2 | 10.89초 | 2.07초 | 2.08초 | 2.52초 | 0.919 req/s |
| 5 | 10.44초 | 4.20초 | 5.10초 | 6.28초 | 0.958 req/s |
| 10 | 11.21초 | 6.14초 | 6.57초 | 11.21초 | 0.892 req/s |

숫자가 말하는 것은 네 가지다.

- **동시성을 10배 높여도 처리량은 그대로다.** 0.888 → 0.919 → 0.958 → 0.892 req/s. c=5에서의 8% 개선은 측정 편차 수준이고, 유의미한 확장이 아니다
- **처리량 대신 지연만 증가한다.** 평균 응답은 1.13초 → 6.14초로 5.5배, p90은 1.54초 → 11.21초로 7배 이상 늘었다. 동시 요청 10개 중 느린 요청은 11초를 기다렸다
- **총 처리 시간이 항상 10~11초다.** 진짜 병렬 처리가 됐다면 동시성을 높일수록 총 시간이 줄어야 한다. 줄지 않았다는 것은 서버가 약 1초에 하나씩 순서대로 처리하고 있다는 뜻이다
- **네트워크 병목이 아니다.** c=10 기준 연결(DNS+dialup)은 3.4ms인데 `resp wait`가 6.14초다. 시간은 전부 서버 안에서 쓰였다

c=10의 히스토그램은 순차 처리를 시각적으로 보여 준다. 10개를 동시에 보냈는데 완료 시각이 약 1초 간격의 계단으로 늘어선다.

<details markdown="1">
<summary><b>c=10 전체 출력 (계단형 완료 패턴)</b></summary>

```shell
~$ hey -n 10 -c 10 -t 300 -m POST \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello, I am"}' \
  http://localhost:8000/basic_generate

Summary:
  Total:        11.2146 secs
  Slowest:      11.2144 secs
  Fastest:      1.0574 secs
  Average:      6.1401 secs
  Requests/sec: 0.8917

Response time histogram:
  1.057 [1]     |■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■
  2.073 [0]     |
  3.089 [1]     |■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■
  4.104 [1]     |■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■
  5.120 [1]     |■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■
  6.136 [1]     |■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■
  7.152 [1]     |■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■
  8.167 [1]     |■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■
  9.183 [1]     |■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■
  10.199 [1]    |■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■
  11.214 [1]    |■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■

Latency distribution:
  10%% in 2.1301 secs
  25%% in 4.4392 secs
  50%% in 6.5650 secs
  75%% in 10.1291 secs
  90%% in 11.2144 secs

Details (average, fastest, slowest):
  DNS+dialup:   0.0034 secs, 0.0032 secs, 0.0036 secs
  resp wait:    6.1365 secs, 1.0537 secs, 11.2108 secs

Status code distribution:
  [200] 10 responses
```

</details>

FastAPI는 요청 10개를 다 받았지만, 요청들이 ModelWorker 앞에 쌓여 한 번에 하나씩 처리되고, 뒤의 요청은 앞 요청이 끝날 때까지 기다린 것이다. 정리하면 다음과 같다.

> `/basic_generate`는 단일 ModelWorker에서 요청을 사실상 순차 처리한다. 동시 요청 수를 1개에서 10개로 늘려도 처리량은 약 0.9 req/s로 증가하지 않았고, 평균·tail 지연만 크게 증가했다. 부하가 늘면 오류가 아니라 대기 시간 누적으로 문제가 드러난다.

용어를 엄밀하게 하면 — 모든 요청이 200으로 성공했으므로 장애는 없다. 측정된 것은 "최대 처리량 약 0.9 req/s"와 "처리량 확장성이 매우 낮음"이고, 0.9 req/s가 절대적으로 낮은지는 모델·출력 토큰 수·하드웨어 목표와 비교해야 할 별개 문제다. 다만 이 실습이 보여 주려는 "낮은 처리량 문제"는 명확하게 재현됐다.

모델 워커가 추론 호출당 하나의 프롬프트만 처리하는 현재 구조에서는, LLM이 잘하는 배치 계산 능력이 놀고 있는 셈이다. [다음 글]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-02-LLM-Serving-From-Scratch-Batch-Request %})에서 배칭 지원으로 이 병목을 공략한다.

<br>

# 트러블슈팅

이번 실습은 서비스 코드보다 환경에서 더 오래 막혔다. 겪은 순서대로 남긴다.

## Linux GPU 서버: Blackwell 세대와 고정된 버전 핀

처음에는 Linux GPU 서버에서 시작했다. `pip install -r requirements.txt`까지는 순조로웠는데, 서버를 띄우자 torch가 경고를 냈고 vLLM 초기화가 죽었다.

```bash
# torch 경고 (핵심 발췌)
NVIDIA RTX PRO 6000 Blackwell Server Edition with CUDA capability sm_120
is not compatible with the current PyTorch installation.

# vLLM EngineCore 초기화 실패 (핵심 발췌)
ERROR [core.py:500] RuntimeError: CUDA error: no kernel image is available for execution on the device
RuntimeError: Engine core initialization failed. See root cause above.
```

원인은 GPU 세대와 바이너리의 불일치다. 이 GPU(Blackwell)는 compute capability **sm_120**인데, requirements가 고정한 `torch==2.7.0`(cu126 휠)이 지원하는 아키텍처 목록은 sm_50~sm_90까지라 sm_120용 커널 이미지가 아예 없다. 더 까다로운 것은 torch만 올려서는 해결되지 않는다는 점이다 — vLLM은 자체 CUDA 커널(`_C.abi3.so`)을 컴파일해 배포하는데, `vllm==0.9.0.1`의 cu126 휠에도 sm_120 코드가 없어서 **vllm 버전 핀 자체를 올려야** 한다. 교육용 코드의 버전 고정을 전부 흔드는 트러블슈팅이 되기에, 실습의 본질이 아니라고 판단하고 시간 제약상 여기서 중단했다.

뒤집어 말하면 이건 **막힌 게 아니라 접은 것**이다. 실패 원인이 순수하게 버전 핀 불일치라, 핀을 sm_120 지원 버전(CUDA 12.8 계열 torch + 그에 맞는 최신 vLLM)으로 올렸다면 이 GPU에서 정상 기동했을 공산이 크다(미검증). 두 환경 중 성공 가능성도 실익도 사실 이쪽이 가장 컸다 — Mac은 [뒤에서 보듯](#mac-vllm-소스-빌드-실패와-lazy-import) CPU로만 돌아 GPU 이점을 볼 수 없는 반면, 여기는 되면 곧바로 실제 GPU 서빙이기 때문이다.

> 여기서 얻은 일반화 하나 — 재현성을 위한 버전 핀은 시간이 지나면 **새 하드웨어와의 비호환**이라는 형태로 되돌아온다. 특히 vLLM처럼 자체 CUDA 커널을 배포하는 패키지는 torch와 GPU 아키텍처, 자기 자신의 세 축이 맞아야 돈다.

## Mac: vLLM 소스 빌드 실패와 lazy import

그래서 Mac으로 옮겼는데, 이번에는 vLLM 설치가 걸렸다. Apple Silicon용 공식 wheel이 없어 `pip install`로는 안 되고, 소스 빌드를 기본값 그대로 돌리면 CUDA를 전제한 타깃이라 `cmake --build . --target=_C`가 exit 134로 죽었다. vLLM에 CPU 전용 빌드 경로(`VLLM_TARGET_DEVICE=cpu`)가 따로 있어 더 파고들면 CPU로는 띄울 수 있었을 것으로 보이지만(미검증), 그렇게 해도 Mac GPU(MPS)는 못 써서 vLLM의 GPU 배칭 이점을 관찰하긴 어렵다. 실습의 본질이 아니라고 보고 시간 제약상 여기서 접었다.

문제는 원본 코드가 `llm/llm.py` 최상단에서 `import vllm`을 한다는 것이다. vLLM이 없으면 `/generate_vllm`만 못 쓰는 게 아니라 **앱 전체가 임포트 단계에서 죽는다**. 그래서 두 군데를 고쳤다.

```python
# llm/llm.py — [수정] vllm 최상단 import 제거.
# 원본은 여기서 vllm 을 import 해서, vllm 이 없으면 /generate_vllm 뿐 아니라
# 앱 전체가 import 단계에서 죽었다. 실제로 쓰는 generate_vllm() 안으로 옮긴다.

class LLMEngine:
    def __init__(self):
        ...
        # [수정] vLLM 모델을 여기서 만들지 않는다.
        # 원본은 __init__ 에서 즉시 생성해서, vLLM 을 안 쓰는 엔드포인트만 쓰려 해도
        # 서버가 기동조차 못 했다. 첫 /generate_vllm 요청 시점에 만든다.
        self.vllm_model = None
```

vllm 임포트를 실제 사용 지점(`generate_vllm()` 내부)으로 옮기는 lazy import, 그리고 `__init__`의 vLLM 엔진 생성을 첫 요청 시점으로 미루는 지연 초기화다. 여기에 requirements에서 vllm을 별도 파일(`requirements-vllm.txt`)로 분리해, vLLM 없는 환경에서도 나머지 세 엔드포인트가 온전히 돌게 했다.

## 결정: vLLM 실습은 제외

두 우회를 거쳐 내린 결정 — 이번 주 실습에서 vLLM 경로(`/generate_vllm`)는 제외한다. 기본·배치·스트리밍 실습은 Mac에서 전부 가능하고, vLLM 비교(3.4)는 스터디 내용과 공개 문서 기반의 사고 실험으로 갈음한다. 위의 [test_vllm 실패](#테스트-스위트-실행)가 이 결정의 기록이다.

정리하면 vLLM을 못 돌린 게 아니라, 두 환경 모두 기동까지 파고들 실익이 이번 실습 목표(수제 구현으로 원리 체득)에 비해 낮다고 보고 접은 것이다. 나중에 여유가 되면 Blackwell 서버의 버전 핀을 최신으로 올려 `/generate_vllm`까지 돌려, 3.4편의 사고 실험을 실측으로 채우는 게 자연스러운 다음 수순이다.

<br>

# 정리

- 기동 로그와 프로세스 트리에서 2편의 구조가 그대로 관찰됐다: 부모(API)에는 모델이 없고, 모델 로딩·추론은 spawn된 자식(ModelWorker)에서만 일어난다
- `from_pretrained()`는 config(구조 상수), 가중치(bin/safetensors), 토크나이저 3종(vocab, merges, config)을 받아 온다 — 1주차에 개념으로 본 것들의 파일 실체다
- 생성 출력이 책 예제와 동일한 것은 greedy decoding의 결정론 때문이고, 시스템 검증 단계에서는 이 결정론이 오히려 도움이 된다
- 통합 테스트 4개는 통과했지만, 비데몬 무한 루프 워커 때문에 pytest가 종료되지 못하는 부산물을 관찰했다 — 자식 프로세스의 종료 경로 설계도 서빙 코드의 일부다
- 부하 테스트로 병목을 재현했다: 동시성을 10배 올려도 처리량은 약 0.9 req/s에 고정되고 지연만 누적된다. 원인은 요청당 프롬프트 하나만 처리하는 단일 워커의 순차 추론이다
- 다음 글에서 배칭으로 이 병목이 얼마나 풀리는지, 그리고 어떤 한계가 남는지 측정한다

<br>

# 참고 링크

- [Hands-On LLM Serving and Optimization (O'Reilly)](https://www.oreilly.com/library/view/hands-on-llm-serving/9798341621480/)
- [실습 코드: orca3/llm-model-inference — ch03/single_model_llm_serving](https://github.com/orca3/llm-model-inference/tree/main/ch03/single_model_llm_serving)
- [hey — HTTP load generator](https://github.com/rakyll/hey)
- [safetensors (Hugging Face)](https://huggingface.co/docs/safetensors/index)
- [서빙 시스템 직접 만들기 2. 코드 구조]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-02-LLM-Serving-From-Scratch-Structure %})
- [LLM 서빙과 최적화 - 2.7. Transformer: 출력층과 샘플링]({% post_url 2026-08-05-AI-LLM-Optimization-02-07-Transformer-Explainer-Output %})

<br>
