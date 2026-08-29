---
title: "[LLM] LLM 서빙과 최적화: 고급 최적화 기법 - 7.2.2. speculative decoding 실습: 네 가지 변형 벤치마크와 측정 검증"
excerpt: "vLLM에서 vanilla, n-gram, EAGLE-3 변형을 동시성 1과 16으로 실측해 보자."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - LLM-Serving
  - Speculative-Decoding
  - vLLM
  - EAGLE
  - N-gram
  - Blackwell
  - Hands-On-LLM-Serving-and-Optimization-Study
  - Hands-On-LLM-Serving-and-Optimization-Study-Week-4
last_modified_at: 2026-08-29
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Hands-On LLM Serving and Optimization Study (LLMSO) 4주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- 책의 speculative decoding 실습(Qwen3-32B, 4개 변형 × 동시성 2개)을 A100 Colab 대신 **공용 RTX PRO 6000 Blackwell(96GB) 노드**에서 재현했다. 동시성 1의 배속이 저자의 실습 결과와 거의 그대로 겹친다(ngram·improved 1% 이내, eagle3 +6%) — Blackwell 특수성은 없었다
- **eagle3만 전 구간에서 이긴다**: 동시성 1에서 2.06배, 16에서 보정 기준 1.70배. ngram은 동시성 16에서 0.94배로 **부호가 바뀐다** — 배치가 차면 버려지는 draft 토큰이 그대로 처리량 손실이다
- 동시성 16의 TTFT 3.3초는 변형의 특성이 아니라 **Triton 커널 JIT 컴파일 아티팩트**였다. vLLM 경고 로그와 1:1로 대응하고, 스톨을 빼면 네 변형 전부 저자 duration의 3% 이내에 붙는다
- 처리량 순서를 설명하는 것은 수락 길이의 최댓값이 아니라 **일관성**이다: ngram은 1.00~5.09(효율 31%)로 출렁이고 eagle3는 1.92~2.59(56%)로 좁다
- 같은 GPU의 다른 실측, 16GB 데스크톱 사례와 겹쳐 보면 동시성 1 배속은 환경 불문 수렴하고, 동시성 16과 TTFT는 환경·측정 조건을 탄다 — 벤치 수치는 로그와 함께 읽어야 한다

<br>

# 실험 설계

[7.2.1편]({% post_url 2026-08-29-Dev-LLM-Serving-Optimization-07-02-01-Speculative-Decoding-Concept %})의 두 명제 — 배치가 차면 이득의 부호가 바뀐다, 성능은 수락이 좌우한다 — 를 실측으로 확인하는 것이 목표다. 책 7장의 실습 구성을 그대로 따른다.

- **target**: `Qwen/Qwen3-32B` bf16 (가중치 61GiB). 네 변형 모두 동일
- **변형 4종**: draft만 바꾼다

  | 변형 | draft | draft 크기 | K (제안 토큰) | 비고 |
  |------|-------|-----------|---------------|------|
  | vanilla | 없음 | — | — | 기준선 |
  | ngram | 모델 아님 — prompt lookup | 0 | 6 | 매칭 창 4~6 |
  | improved ngram | 같은 방식, 창만 다름 | 0 | 4 | 매칭 창 2~128 |
  | eagle3 | `RedHatAI/Qwen3-32B-speculator.eagle3` | 2.9GiB | 3 | Qwen3-32B 전용 학습 |

- **부하 2종**: 동시성 1(저부하 — memory-bound가 지배하는, speculative decoding이 이겨야 하는 구간)과 16(고부하 — 배치가 연산을 채우는 구간)
- **벤치**: `vllm bench serve` + [Spec-Bench](https://github.com/hemingkx/Spec-Bench)의 `question.jsonl` 프롬프트, 요청 16개, 요청당 출력 512토큰

실험의 두 축이 곧 글의 뼈대다. 가로축은 draft의 비용과 품질 — 오버헤드가 거의 없는 n-gram에서 학습된 2.9GiB drafter까지 — 이고, 세로축은 동시성이다. improved ngram은 기본 n-gram에서 매칭 창을 2~128로 넓혀 발동 기회를 늘리고, K는 6에서 4로 줄여 빗나간 추측 하나당 손해를 줄인 설정이다.

이 실습은 GPU 요구 사양의 문턱이 높은 편이다. target 가중치만 61GiB라 80GB급 VRAM이 필요한데, 책 저자의 기준 환경인 Colab A100-80GB는 유료 크레딧이 상당히 들고, 그 이하 GPU에서는 ([뒤에서 볼 16GB 사례](#16gb-gpu에서의-역효과)처럼) 실습의 결론 자체가 뒤집혀 보인다.

<br>

# 환경 구성

책이 제공하는 [실습 원본 노트북](https://github.com/orca3/llm-model-inference/blob/main/ch07/SpecDecode.ipynb)은 Colab A100-SXM4-80GB를 기준으로 작성되어 있다. 이 실습은 그 대신 RTX PRO 6000 Blackwell Server Edition(96GB GDDR7) GPU 1장에서 진행했다 — 여러 사용자가 함께 쓰는 공용 GPU 노드라, 유휴 시간대를 이용했다.

이 환경에서는 원본 노트북을 그대로 옮겨 실행하면 안 된다. 이유는 두 갈래다. 하나는 Blackwell이라는 하드웨어이고, 다른 하나는 공용 노드라는 운영 환경이다. 그래서 실습 파일을 손봐서 사용했다. 실제 사용한 파일은 [수정한 노트북]({{site.url}}/assets/data/llmso-ch07-speculative-decoding/llmso-ch07-speculative-decoding.ipynb)과 [setup.sh]({{site.url}}/assets/data/llmso-ch07-speculative-decoding/setup.sh)에서 볼 수 있다. 무엇을 어떻게 고쳤는지 확인해 본다.

전체 실행 환경은 다음과 같다.

| 항목 | 값 |
|------|-----|
| GPU | RTX PRO 6000 Blackwell 96GB × 1 (sm_120), tp=1 |
| 소프트웨어 | vLLM 0.27.1, torch 2.13.0+cu132, flashinfer 0.6.16.post3, Python 3.12 |
| 서버 옵션 | `--max-model-len 2048 --gpu-memory-utilization 0.90` |
| 실측 메모리 (vanilla 기동 로그 기준) | 가중치 등 적재 61.96GiB (순수 가중치 61.03GiB), KV cache 22.06GiB (90,368 토큰), CUDA graph 0.91GiB — 변형마다 조금씩 다르다 |
| attention | FlashAttention 2, CUDA graph 정상 캡처 |

## sm_120과 소프트웨어 스택의 함정

RTX PRO 6000 Blackwell은 compute capability 12.0(sm_120)으로, 데이터센터 Blackwell(B200, sm_100)과 아키텍처 코드가 다르다. 배포 채널에 sm_120 커널이 빠진 wheel이 섞여 있던 시기가 있어, "설치는 되는데 실행이 안 되는" 실패가 흔하다. 

처음 만나는 함정도 아니다 — [3.1편의 트러블슈팅]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-01-LLM-Serving-From-Scratch-Basic-Request %}#linux-gpu-서버-blackwell-세대와-고정된-버전-핀)에서 같은 GPU가 교육용 코드의 버전 핀(torch 2.7.0, vllm 0.9.0.1)에 sm_120 커널이 없어 기동에 실패했다. 사실 당시 "핀을 sm_120 지원 버전으로 올렸다면 정상 기동했을 공산이 크다(미검증)"로 접어 두고 넘어간 적이 있는데, 이번 실습은 그 추정의 실증이기도 하다 — 핀을 버리고 최신 stable로 가자 같은 GPU에서 문제없이 실습할 수 있었다. 

증상별 대응은 다음과 같고, 핵심은 **각 실패가 61GiB를 다운로드하기 전에 잡히도록 순서를 짜는 것**이다.

| 증상 | 대응 | 어디서 잡히나 |
|------|------|---------------|
| `no kernel image is available` | wheel에 sm_120 커널 없음 → nightly로 교체 | setup.sh 3단계 (3초) |
| FlashInfer JIT의 컴파일러 부재 | gcc·ninja·cuda-toolkit 설치 | setup.sh 2단계 경고 |
| CUDA graph 캡처 실패 | `--enforce-eager` — 단 네 변형 전부에 넣어야 비교가 성립 | setup.sh 4단계 |
| eagle3만 실패 | vanilla + ngram 2종만으로도 실습의 결론은 나옴 | — |

버전 핀도 하나 버렸다. 원본 노트북은 `vllm==0.11.0`을 고정한다. 구형 핀을 유지할수록 sm_120 같은 신형 아키텍처에서 커널이 빠진 wheel을 만날 확률이 올라가고, GPU가 A100이 아닌 이상 책의 절대 수치는 어차피 재현되지 않는다. **재현할 것은 절대 수치가 아니라 변형 간 상대 차이**라고 목표를 정리하면 최신 stable을 쓰는 쪽이 맞다. 설치는 uv의 `--torch-backend=auto`로 드라이버에 맞는 CUDA 빌드의 torch를 고르게 했다 — Blackwell에서 torch와 CUDA의 불일치는 곧 "sm_120 인식 실패"라서, 여기서부터 걸러야 한다.

## setup.sh: 실패 조기화 순서

환경 준비는 노트북에 넣지 않고 [setup.sh]({{site.url}}/assets/data/llmso-ch07-speculative-decoding/setup.sh)로 분리했다. 설계 원칙은 스크립트 머리의 주석 그대로다.

```bash
# 순서 원칙: 싼 게 먼저 깨지게 한다.
#   드라이버 확인(0초) -> venv(1분) -> torch sm_120 커널(3초) -> 0.6B vLLM 스모크(2분) -> 32B 62GB 다운로드
# Blackwell 은 "설치는 되는데 커널이 없어서 실행이 안 되는" 실패가 흔해서,
# 62GB 받은 다음에 알게 되면 반나절이 날아간다.
```

단계 중 두 가지를 주목하면 좋다. 먼저 Python 버전 고정이다. 검색하면 Blackwell 관련 워크어라운드가 쏟아지지만, 이 환경에서 실제로 밟은 함정은 Blackwell이 아니라 **Python 3.10과 flashinfer의 조합**이었다.

```bash
# 3.12 를 고정하는 이유 (추측 아님, 실제 prerequisite 시도에서 재현):
#   flashinfer 0.6.16.post3 의 comm/fd_exchange.py 가 `array.array[int]` 를 어노테이션에 쓰는데
#   그 모듈에 `from __future__ import annotations` 가 없어서 import 시점에 평가된다.
#   array.array 가 subscriptable 해진 건 Python 3.12 부터(CPython gh-98658) -> 3.10/3.11 은 즉사:
#     TypeError: 'type' object is not subscriptable
#   vLLM 은 torch.compile 백엔드 초기화에서 flashinfer.comm 을 import 하므로 엔진이 아예 못 뜬다.
"$UV" venv --python 3.12 .venv

# 위 버그의 회귀 테스트. 3.11 이하면 여기서 죽고, 62GB 받기 전에 끝난다.
./.venv/bin/python -c "import sys, array; array.array[int]; print('ok')"
```

flashinfer는 `requires_python >=3.10`이라고 선언하지만 실제로는 3.12 미만에서 import 시점에 죽는다. 선언과 실동작이 다른 의존성은 이렇게 한 줄짜리 회귀 테스트로 박아 두면, 나중에 커널을 잘못 골랐을 때도 첫 셀에서 걸린다.

다음은 스모크 테스트다. torch가 sm_120 커널을 실제로 갖고 있는지는 import만으로 안 잡히므로 matmul을 한 번 돌려 보고(3초), 이어서 61GiB를 받기 전에 1.2GB짜리 Qwen3-0.6B로 이 노트북이 쓸 경로 전체 — `vllm serve` + `--speculative-config` + OpenAI API 호출 — 를 통과시킨다.

```python
# setup.sh 3단계가 heredoc으로 실행하는 python 스니펫
# import 만으로는 안 잡힌다. 커널을 실제로 띄워봐야 'no kernel image' 가 나온다.
a = torch.randn(2048, 2048, device="cuda", dtype=torch.bfloat16)
assert f"sm_{cc[0]}{cc[1]}" in torch.cuda.get_arch_list(), "wheel 에 sm_120 커널 없음"
```

```bash
# 32B 를 받기 전에, 이 노트북이 쓰는 경로(서빙 + speculative-config + OpenAI API)를 싸게 통과시킨다.
./.venv/bin/vllm serve Qwen/Qwen3-0.6B \
  --port "$PORT" --max-model-len 2048 --gpu-memory-utilization 0.15 \
  --speculative-config '{"method":"ngram","num_speculative_tokens":4,"prompt_lookup_min":2,"prompt_lookup_max":8}' \
  > smoke.log 2>&1 &
```

결과적으로 [앞의 증상별 대응 표](#sm_120과-소프트웨어-스택의-함정)에 준비해 둔 Blackwell 대응 — nightly 교체, `--enforce-eager`, 양자화 회피 — 은 하나도 쓸 일이 없었고, 스택은 최신 stable 그대로 떴다. 

## 노트북 수정: 공용 노드 안전 장치

원본 노트북은 Colab 단독 환경을 전제한다. 공용 노드에서는 그 전제가 사고로 이어질 수 있어 다음을 고쳤다.

| 원본 | 변경 | 이유 |
|------|------|------|
| `pkill -f "vllm serve"` | GPU PID 기반 정리 ([헬퍼 함수 해부](#헬퍼-함수-해부) 참고) | 원본대로면 **노드의 다른 vLLM 서버까지 죽는다** |
| port 8000 | 8111 | 공용 노드에서 8000은 이미 물려 있을 수 있음 |
| `--disable-log-requests` | 삭제 | 이후 vLLM에서 제거된 플래그. 안 고치면 서버 기동 셀이 전부 즉시 실패 |
| `--gpu-memory-utilization 0.95` | 0.90 | 96GB 중 모델 적재만 62GiB. 파편화 여유 |
| 결과를 한 파일에 append | 변형별 파일 분리 | 원본 plot 셀은 JSON **행 순서**로 변형을 구분한다 — 중간에 한 번 실패·재실행하면 그래프가 조용히 틀린다 |

마지막 항목이 이 표에서 제일 위험한 함정이다. 벤치가 한 번이라도 실패한 뒤 재실행하면 행 순서가 밀리는데, plot 셀은 에러 없이 **잘못된 라벨의 그래프**를 그려 준다. 결과 파일을 `results/{변형}.json`으로 분리하고 로드할 때 파일별로 마지막 2행(동시성 2개)만 집으면 재실행에 안전해진다.

GPU 지정에도 함정이 하나 있다. `CUDA_VISIBLE_DEVICES=1`만 쓰면 CUDA가 GPU를 "빠른 순"으로 재정렬한 인덱스를 쓰기 때문에 1번이 `nvidia-smi`의 1번이 아닐 수 있다.

```python
# torch import 보다 먼저 잡아야 먹는다.
os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"   # CUDA 인덱스 == nvidia-smi 인덱스
os.environ["CUDA_VISIBLE_DEVICES"] = "1"
```

노트북 첫 셀에는 커널 가드도 넣었다. VS Code Remote-SSH의 Jupyter 커널은 `sys.executable`만 venv를 가리키고 `PATH`는 아니라서, 그대로 두면 `%%bash` 셀의 `vllm` 호출이 `command not found`로 죽는다. 첫 셀에서 3.12 미만이거나 venv가 아니면 assert로 멈추고, venv의 bin을 PATH 맨 앞에 주입한다. 이 가드 덕에 커널만 맞으면 `%%bash`의 `vllm serve`와 subprocess의 `vllm bench serve`가 전부 같은 venv를 쓴다.

## 헬퍼 함수 해부

수정한 노트북([전체 파일]({{site.url}}/assets/data/llmso-ch07-speculative-decoding/llmso-ch07-speculative-decoding.ipynb))의 헬퍼는 셋이다.

**`run_vllm_bench_spec()`** — `vllm bench serve`를 subprocess로 감싸는 벤치 실행기다. 변형 이름을 받아 결과 파일을 `results/{variant}.json`으로 분리하고, 데이터셋(`--dataset-name spec_bench`), 프롬프트 수(16), 출력 길이(512), 동시성(`--max-concurrency`)을 인자로 조립한 뒤 출력을 실시간으로 흘려 보여 준다. 벤치 자체를 새로 짜는 게 아니라 vLLM에 내장된 벤치 하네스를 쓰는 것이라, 우리가 정하는 것은 워크로드 모양뿐이다.

**`check_vllm_status()`** — 서버 기동 대기. 32B 가중치 로딩은 첫 회에 수 분이 걸리므로, `/health` 엔드포인트를 10초 간격으로 폴링하면서 매 회 로그 파일의 마지막 2줄을 같이 출력한다. 고정 sleep 대신 폴링인 이유는 다음 함수와 같고, 로그 tail을 섞는 이유는 기동이 실패했을 때 폴링 메시지만 보고 있지 않기 위해서다.

**`free_gpu()`** — 이 노트북에서 가장 공들인 함수다. 변형을 바꿀 때마다 이전 서버를 내리고 VRAM 61GiB가 실제로 반납된 뒤 다음 서버를 올려야 하는데, 흔히 쓰는 두 패턴이 여기서는 다 틀린다.

```python
# 발췌: 예외 처리·로그 일부 생략. 전체 코드는 글 말미의 노트북 파일 참고
def _gpu_procs(gpu):
    """GPU 를 점유 중인 '내' PID 들. 공용 노드라 남의 프로세스는 절대 건드리지 않는다."""
    out = subprocess.run(
        ["nvidia-smi", "-i", str(gpu), "--query-compute-apps=pid", "--format=csv,noheader"],
        capture_output=True, text=True).stdout.split()
    mine = []
    for s in out:
        try:
            if os.stat(f"/proc/{int(s)}").st_uid == os.getuid():   # 내 프로세스만
                mine.append(int(s))
        except (ValueError, FileNotFoundError, ProcessLookupError):
            pass
    return mine

def free_gpu(gpu=1, timeout=180):
    """서버를 죽이고 VRAM 이 '실제로' 반납될 때까지 기다린다."""
    for sig in (signal.SIGTERM, signal.SIGKILL):      # 정중히 -> 강제로
        for pid in _gpu_procs(gpu):
            os.kill(pid, sig)
        deadline = time.time() + (timeout if sig == signal.SIGTERM else 30)
        while time.time() < deadline:
            if not _gpu_procs(gpu):                   # GPU 가 비었나 (프로세스 기준)
                time.sleep(3)                         # 드라이버가 반납을 마칠 여유
                print(f"GPU{gpu} 정리 완료 (used={_gpu_used(gpu)})")
                return
            time.sleep(3)
    raise RuntimeError(f"GPU{gpu} 를 못 비웠다. 수동 확인 필요")
```

- **`pkill -f "vllm serve"`를 쓰지 않는 이유**: vLLM은 API 서버 프로세스 아래에 EngineCore 자식 프로세스를 띄우는데, 자식의 cmdline은 `vllm serve`와 매칭되지 않아 pkill에서 살아남는다. 살아남은 자식이 VRAM을 쥔 채로 다음 변형이 뜨면 OOM이다. 그래서 문자열 매칭 대신 **GPU가 직접 알려 주는 점유 PID**(`nvidia-smi --query-compute-apps`)를 죽인다. 여기에 `/proc/<pid>`의 소유자 검사를 더해 내 프로세스만 대상으로 한다 — 공용 노드에서 남의 서버를 죽이지 않기 위한 최소한의 예의다
- **고정 `sleep(N)`을 쓰지 않는 이유**: 61GiB 반납은 시점이 일정하지 않아 고정 대기로는 못 맞춘다. 덜 비워진 상태에서 다음 서버가 뜨면 역시 OOM이므로, "프로세스가 사라졌는가"를 조건으로 대기하고 SIGTERM이 안 먹으면 SIGKILL로 올린다

<br>

# 적용과 관찰: 네 변형 벤치마크

## 변형별 서버 기동

변형은 서버 기동 옵션 `--speculative-config`로만 갈린다. 네 기동 명령의 차이가 곧 실험 변수다.

```bash
# vanilla: speculative 옵션 없음 (기준선)
nohup vllm serve Qwen/Qwen3-32B \
  --port 8111 --max-model-len 2048 --gpu-memory-utilization 0.90 \
  > vllm-vanilla.log 2>&1 &

# n-gram: 모델 없는 draft. 매칭 창 4~6, 6토큰 제안
nohup vllm serve Qwen/Qwen3-32B \
  --speculative-config '{
    "method": "ngram",
    "num_speculative_tokens": 6,
    "prompt_lookup_min": 4,
    "prompt_lookup_max": 6
}' \
  --port 8111 --max-model-len 2048 --gpu-memory-utilization 0.90 \
  > vllm-ngram.log 2>&1 &

# improved ngram: 창을 2~128로 넓히고 (발동 기회 확대), K는 4로 (빗나간 추측의 비용 축소)
nohup vllm serve Qwen/Qwen3-32B \
  --speculative-config '{
    "method": "ngram",
    "num_speculative_tokens": 4,
    "prompt_lookup_min": 2,
    "prompt_lookup_max": 128
}' \
  --port 8111 --max-model-len 2048 --gpu-memory-utilization 0.90 \
  > vllm-ngram_improved.log 2>&1 &

# eagle3: Qwen3-32B 전용으로 학습된 2.9GiB drafter, 3토큰 제안
nohup vllm serve Qwen/Qwen3-32B \
  --speculative-config '{
    "method": "eagle3",
    "model": "RedHatAI/Qwen3-32B-speculator.eagle3",
    "num_speculative_tokens": 3
  }' \
  --port 8111 --max-model-len 2048 --gpu-memory-utilization 0.90 \
  > vllm-eagle3.log 2>&1 &
```

절차는 변형마다 동일하다: `free_gpu(1)` → 서버 기동 → `check_vllm_status()` → 동시성 1 벤치 → 동시성 16 벤치. 네 변형 × 동시성 2개, 총 8회가 전부 `completed=16`으로 완주했다.

## 실측 결과

지표는 [3.3편의 서빙 지표]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %}#서빙-지표-ttft와-tpot)에서 정의한 TTFT(첫 토큰까지의 시간)·TPOT(출력 토큰당 시간)·ITL(토큰 간 지연)을 그대로 쓴다. 먼저 동시성 1 — speculative decoding이 이겨야 하는 구간이다.

| 변형 | out tok/s | vs vanilla | TPOT |
|------|-----------|------------|------|
| vanilla | 22.3 | 1.00배 | 44.8ms |
| ngram (K=6) | 23.6 | 1.06배 | 42.3ms |
| improved ngram (K=4) | 26.1 | 1.17배 | 38.1ms |
| **eagle3 (K=3)** | **46.0** | **2.06배** | **21.6ms** |

ngram은 있는 듯 없는 듯한 개선(6%), improved ngram은 17%, eagle3는 2배다. [7.2.1편의 이득 원리]({% post_url 2026-08-29-Dev-LLM-Serving-Optimization-07-02-01-Speculative-Decoding-Concept %}#이득의-원리-가중치-읽기-1회당-생성-토큰-수) 그대로 — 배치 1의 decode는 가중치 61GiB를 읽는 동안 연산이 놀고 있으므로, 후보를 잘 맞히는 draft일수록 그 노는 연산을 토큰으로 바꾼다.

동시성 16으로 올리면 그림이 뒤집힌다.

| 변형 | out tok/s (실측) | vs vanilla (실측) | 보정 | TPOT |
|------|------------------|-------------------|------|------|
| vanilla | 332.0 | 1.00배 | 1.00배 | 47.4ms |
| ngram | 279.2 | 0.84배 | **0.94배** | 47.4ms |
| improved ngram | 324.7 | 0.98배 | 0.98배 | 43.3ms |
| **eagle3** | **460.2** | 1.39배 | **1.70배** | **25.6ms** |

![Total token throughput by concurrency]({{site.url}}/assets/images/llmso-ch07-specdecode-total-token-throughput.png){: .align-center width="760"}

<center><sup>직접 실측한 결과 그래프. 동시성 1에서 eagle3가 2배를 만들고, 동시성 16에서 ngram이 vanilla 아래로 떨어진다. 총 토큰(입력+출력) 처리량 기준이라 본문의 출력 tok/s 표와 절대값은 다르고 비율 관계는 같다</sup></center>

**ngram은 동시성 16에서 vanilla보다 느리다.** 배치가 차면 GPU는 이미 compute-bound라 버려지는 draft 토큰의 검증 연산이 그대로 처리량 손실이 된다 — 제안에 비용이 없는 draft라도 검증 연산에는 비용이 있다. eagle3는 이 구간에서도 이기지만 이득 폭은 2.06배에서 1.70배로 줄어든다. "보정" 열이 왜 필요한지는 다음 절에서 다룬다 — 실측 그대로 읽으면 ngram의 손해(0.84배)를 과장하고 eagle3의 이득(1.39배)을 과소평가하게 된다.

> 참고: 표에서 TPOT과 ITL이 갈라지는 것도 speculative decoding의 특징이다. 일반 decode에서는 스텝당 토큰이 1개라 두 지표가 같은 값이고([3.3편의 서빙 지표]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %}#서빙-지표-ttft와-tpot) 참고), 책과 [7.1편]({% post_url 2026-08-29-Dev-LLM-Serving-Optimization-07-01-LLM-Serving-Advanced-Techniques-Overview %})이 이 기법의 이득을 ITL로 부르는 것도 그 통상 등식 위에서다. 그런데 eagle3의 동시성 1 수치는 TPOT 21.6ms, ITL 48.3ms로 두 배 넘게 차이 난다. 수락된 토큰 묶음이 스텝 단위로 한꺼번에 도착하기 때문에, 벤치 도구가 도착 이벤트 사이 간격으로 재는 ITL은 스텝 시간(≈ vanilla의 44.8ms)에 머물고, 전체 시간을 토큰 수로 나눈 TPOT만 절반이 된다. 즉 기법이 토큰당 지연을 못 줄인 게 아니라 계측 방식의 차이이고, 실질은 TPOT 열이 보여 준다 — 벤치의 ITL 지표로만 보면 "안 빨라졌다"고 오독할 수 있다.

<details markdown="1">
<summary><b>eagle3 원시 벤치 출력 (동시성 1 / 16)</b></summary>

```bash
============ Serving Benchmark Result ============
Successful requests:                     16
Benchmark duration (s):                  177.97
Request throughput (req/s):              0.09
Output token throughput (tok/s):         46.03
Mean TTFT (ms):                          92.93
Mean TPOT (ms):                          21.59
Mean ITL (ms):                           48.30
==================================================

============ Serving Benchmark Result ============
Successful requests:                     16
Benchmark duration (s):                  17.48
Request throughput (req/s):              0.92
Output token throughput (tok/s):         460.17
Mean TTFT (ms):                          3324.69
Mean TPOT (ms):                          25.60
Mean ITL (ms):                           57.45
==================================================
```

</details>

<br>

# 검증

앞 절의 표를 그대로 결론으로 확정할 수 없었던 것이, 실측값에 기법의 성질로 보기 어려운 이상값이 섞여 있었다 — 동시성 16의 TTFT가 특정 변형에서만 수십 배 튄다. 벤치 수치에는 기법과 무관한 요인(일회성 컴파일, 데워진 캐시, 측정 순서)이 끼어들 수 있고, 걸러내지 않으면 아티팩트를 하드웨어나 기법의 특성으로 오독하게 된다. 그래서 이상값의 원인을 로그에서 추적하고, 보정한 수치를 저자의 독립 측정과 대조해 재현이 성립하는지 확인했다. 같은 로그에서 처리량 순서를 만드는 실제 변수(수락 길이)도 확인할 수 있었다.

## TTFT@16 오염과 보정

동시성 16의 TTFT를 그래프로 보면 이상한 점이 바로 보인다.

![Mean TTFT vs Mean TPOT at concurrency 16]({{site.url}}/assets/images/llmso-ch07-specdecode-ttft-tpot-conc16.png){: .align-center width="760"}

<center><sup>직접 실측한 결과 그래프. ngram과 eagle3의 TTFT만 3.3초로 튀어 있다 — 변형의 특성이라면 improved ngram은 왜 멀쩡한가</sup></center>

ngram 3295ms, eagle3 3325ms인데 vanilla 142ms, improved ngram 121ms다. 튄 두 개가 공교롭게 둘 다 speculative 변형이라 "speculative decoding이 TTFT를 희생한다"는 결론으로 이어지기 쉽고, 실제로 그 방향의 효과가 이론상 존재하기도 한다 — [7.2.1편의 적용 한계]({% post_url 2026-08-29-Dev-LLM-Serving-Optimization-07-02-01-Speculative-Decoding-Concept %}#효과가-사라지는-조건)에서 본 대로 이 기법은 ITL을 위해 TTFT를 다소 내줄 수 있고, 저자의 A100 실측에서도 eagle3의 TTFT는 vanilla보다 약 50ms 높다. 기대와 부호가 일치하니 그럴듯해 보인다. 하지만 두 가지가 어긋난다. 크기가 다르고(수십 ms가 아니라 3초대), 같은 speculative 변형인 improved ngram은 121ms로 vanilla보다도 깨끗하다 — 같은 방식(ngram)의 두 설정이 정반대로 나온 시점에서 원인은 기법이 아니다. 서버 로그를 열면 vLLM이 답을 직접 알려 주고 있다.

```
WARNING [jit_monitor.py:135] Triton kernel JIT compilation during inference: _topk_topp_kernel.
This causes a latency spike; consider extending warmup to cover this shape/config.
```

| 변형 | TTFT@16 | `_topk_topp_kernel` JIT 발생 구간 |
|------|---------|-----------------------------------|
| vanilla | 142ms | 경고 없음 |
| ngram | **3295ms** | **동시성 16 벤치 도중** |
| improved ngram | 121ms | 동시성 1 벤치 끝자락 |
| eagle3 | **3325ms** | **동시성 16 벤치 도중** |

JIT 발생 구간과 TTFT 이상이 네 변형에서 예외 없이 1:1로 일치한다. 16개 요청이 한꺼번에 들어온 직후 컴파일이 걸리면 그 구간의 생성이 멈춰 서고, 첫 토큰이 그만큼 늦어진 것이 TTFT 3.3초다. eagle3 로그의 처리량 램프에 흔적이 그대로 남아 있다.

```bash
14:27:12  WARNING  Triton kernel JIT compilation during inference: _topk_topp_kernel
14:27:13  Running: 16 reqs, Avg generation throughput:  92.4 tokens/s   # 배치는 다 찼는데
14:27:23  Running: 13 reqs, Avg generation throughput: 614.4 tokens/s   # 다음 창은 6.6배
```

즉 **동시성 16의 TTFT는 변형의 성질이 아니라 일회성 컴파일 아티팩트다.** improved ngram은 우연히 동시성 1 구간에서 같은 커널을 컴파일해 둬서 깨끗했을 뿐이다. 그래서 보정값을 만들었다: 깨끗한 변형들의 TTFT 수준(약 130ms)을 기준으로, TTFT 초과분을 duration에서 빼고 배속을 다시 계산한 것이 앞 표의 "보정" 열이다.

다만 이 진단에서 직접 관측한 것과 역산한 것은 구분해 둘 필요가 있다. JIT 경고의 발생 시각과 변형별 1:1 대응은 로그에서 직접 관측한 사실이다. 반면 스톨의 크기 3.2초는 직접 잰 값이 아니라 TTFT에서 거꾸로 계산한 값이다(3,325ms − 130ms). 그래서 이 3.2초를 근거로 다시 "스톨이 TTFT 3.3초를 만들었다"고 말하면 순환 논증이 된다 — 설명에 쓴 값이 설명하려는 값에서 나왔으니 맞아떨어지는 것이 당연하다. 순환을 벗어나는 근거는 다음 절의 대조다: 같은 3.2초를 TTFT가 아니라 duration에서 빼고, 그 결과를 저자의 독립 측정과 비교한다 — 두 값 모두 3.2초의 산출에 쓰이지 않았다. 남는 확정 방법은 같은 서버에서 동시성 16 벤치를 연속 2회 돌려 2회차 TTFT가 130ms대로 떨어지는지 보는 것인데(일회성 컴파일은 두 번 일어날 수 없다), 이 확인은 노드 사정상 아직 실행하지 못했다.

> 참고로 동시성 16 벤치는 동시성 1 벤치가 같은 프롬프트로 먼저 돈 뒤라 prefix cache가 데워진 상태에서 시작한다(로그 기준 적중률 40.3%). 저자 노트북도 같은 순서라 변형 간·저자와의 비교는 성립하지만, 동시성 16의 절대값을 냉시작 처리량으로 인용하면 안 된다.

## 저자 결과와의 대조

보정이 임의 조작이 아니라는 근거가 저자(A100 80GB, vLLM 0.11.0) 결과와의 대조다. 먼저 동시성 1은 보정 없이도 거의 그대로 재현된다.

| 변형 | 저자 (A100) | 이 실습 (Blackwell) |
|------|-------------|---------------------|
| ngram | 1.06배 | 1.06배 |
| improved ngram | 1.16배 | 1.17배 |
| eagle3 | 1.95배 | 2.06배 |

절대값도 붙는다(vanilla 23.3 → 22.3 tok/s, eagle3 45.4 → 46.0). GPU도 vLLM 버전도 다른데 배속이 이렇게 겹치는 이유는, 동시성 1 decode가 메모리 대역폭 지배라 두 카드의 대역폭 차이가 분자·분모에서 약분되기 때문이다.

동시성 16은 처음에는 벌어져 보였다 — eagle3가 저자 1.65배 대 실측 1.39배. 그런데 JIT 스톨을 duration에서 빼기만 하면 네 변형 전부가 저자 duration의 3% 이내로 착지한다.

| 변형 | 실측 dur | 스톨 | 보정 dur | 저자 dur | 보정 배속 | 저자 배속 |
|------|----------|------|----------|----------|-----------|-----------|
| vanilla | 24.4s | 0.0s | 24.4s | 24.2s | 1.00배 | 1.00배 |
| ngram | 29.3s | 3.2s | **26.2s** | **25.6s** | 0.94배 | 0.95배 |
| improved | 25.1s | 0.0s | 25.1s | 25.5s | 0.98배 | 0.96배 |
| eagle3 | 17.5s | 3.2s | **14.3s** | **14.7s** | 1.70배 | 1.65배 |

이 표가 두 가지를 동시에 증명한다. 첫째, JIT 스톨 진단이 맞다 — 3.2초가 실재했고 duration에 그대로 더해져 있었다. 둘째, 이 환경이 저자 실험을 충실히 재현했다 — Blackwell 특수성은 없다. 대조하지 않았다면 "Blackwell에서는 eagle3의 배치 이득이 A100보다 작다(1.39배 대 1.65배)"라는 틀린 하드웨어 결론을 낼 뻔했다. **벤치 수치의 최고의 sanity check는 독립된 원본 결과와의 대조다.**

## 수락 길이: 최댓값이 아니라 일관성

그럼 왜 eagle3만 이기는가. 서버 로그의 수락 길이([7.2.1편의 정의]({% post_url 2026-08-29-Dev-LLM-Serving-Optimization-07-02-01-Speculative-Decoding-Concept %}#수락률과-수락-길이) — iteration당 확정 토큰 수)를 시간 순으로 뽑아 분포를 보면 그 이유를 알 수 있다.

| 변형 | K | 수락 길이 중앙값 | 최소~최대 | 효율 (수락 길이 / (K+1)) |
|------|---|------------------|-----------|--------------------------|
| ngram | 6 | 2.18 | **1.00~5.09** | 31% |
| improved ngram | 4 | 1.83 | 1.33~3.04 | 37% |
| **eagle3** | 3 | 2.22 | **1.92~2.59** | **56%** |

최댓값만 보면 ngram이 5.09로 셋 중 제일 높다. 프롬프트에 반복되는 n-gram이 있을 때는 6토큰을 통째로 맞히기 때문이다. **문제는 최솟값이다** — 매칭이 없으면 1.00 — draft 전부 거부 — 까지 떨어지고, 그때마다 6토큰 분량의 검증 연산이 폐기된다. eagle3는 천장(최댓값)이 2.59로 낮은 대신 바닥(최솟값)이 1.92 아래로 안 내려간다. 처리량 순서(eagle3 > improved > ngram)는 최댓값 순서가 아니라 정확히 **효율 열의 순서**다. 수락은 최댓값이 아니라 일관성이 결정하고, 분산이 곧 낭비다.

여담으로 이 분석에는 함정이 하나 있었다. 로그에서 수락 길이를 `sort`로 정렬해 끝부분만 보면 최댓값들만 눈에 들어와, "ngram이 수락 최고"라는 정반대 결론이 나온다. 시계열 지표는 시간 순으로 봐야 한다.

<br>

# 환경과 워크로드가 바꾸는 결과

같은 실습을 다른 환경에서 돌린 두 사례와 비교해 보자. 어디까지가 기법의 성질이고 어디부터가 환경의 성질인지가 갈라진다.

## 16GB GPU에서의 역효과

스터디에서 공유된 다른 환경의 결과도 있다. 데스크톱 GPU(VRAM 16GB)에서 Qwen3-8B-FP8로 같은 실습을 시도한 경우인데, 그 환경에서는 **동시성 1의 vanilla부터 GPU 사용률이 98%로 찍혔고, speculative decoding을 켜자 오히려 느려졌다**. vanilla 자체는 이미 49.8 tok/s(TPOT 20.1ms)로 잘 돌고 있었다.

[7.2.1편의 적용 조건]({% post_url 2026-08-29-Dev-LLM-Serving-Optimization-07-02-01-Speculative-Decoding-Concept %}#효과가-사라지는-조건) — 이득이 나려면 가중치를 읽는 동안 노는 연산이 있어야 한다 — 의 대우, 즉 **노는 연산이 없으면 이득도 없다**를 보여 주는 사례다. 여기서 노는 연산이란 memory-bound decode에서 스텝 시간을 가중치 읽기가 채우는 동안 연산 유닛이 비는 구간을 말한다. 추가 연산(draft 실행, 후보 검증)을 이 구간에 겹쳐 넣을 수 있으면 스텝 시간이 늘지 않아 추가 시간이 거의 없는데, 8B 모델은 32B의 4분의 1 파라미터라 읽을 바이트가 적어 이 구간 자체가 짧고, FP8 양자화는 읽을 바이트를 다시 절반으로 줄여 구간을 더 좁힌다. 겹쳐 넣을 자리가 없으면 추측·검증 연산은 스텝 시간에 그대로 더해진다. GPU 사용률 98%라는 지표만으로 compute-bound라고 단정할 수는 없지만(사용률은 커널이 도는 시간의 비율이지 연산 포화도가 아니다), 이 사례에서 관찰된 결과는 그 예측과 방향이 같았다 — **speculative decoding을 켠 쪽의 처리량이 vanilla보다 낮았다**. 요구 환경이 안 되는 상태의 실습 결과도 이 기법을 이해하는 데는 유효한 데이터인 이유다.

## 같은 GPU에서의 다른 실측과 비교

같은 스터디의 다른 멤버가 [같은 GPU(RTX PRO 6000 Blackwell 96GB)로 이 벤치를 돌린 정리 글](https://velog.io/@limes22/Speculative-Decoding-%EB%B2%A4%EC%B9%98%EB%A7%88%ED%81%AC)을 공유했다. 측정 환경의 타당성 검증(두 워커 노드에서 vanilla를 재측정해 0.2~1.8% 차이 확인)까지 갖춘 실측이라 대조 상대로 삼기 좋다. 아래에서는 이 글을 멤버 실측이라 적는다. 환경은 vLLM 0.28.0(이 실습은 0.27.1)이다.

| eagle3 배속 | 저자 (A100) | 이 실습 | 멤버 실측 |
|-------------|-------------|---------|------------|
| 동시성 1 | 1.95배 | 2.06배 | 2.11배 |
| 동시성 16 | 1.65배 | 1.70배 (보정) | 1.83배 |

<br>

결과를 해석해 보자.

- **동시성 1은 세 환경에서 수렴한다.** ngram(1.06/1.06/1.07)과 improved(1.16/1.17/1.18)까지 포함해 배속이 사실상 같다 — memory-bound 구간에서는 하드웨어 차이가 약분된다는 앞 절의 설명이 제3의 환경에서도 성립한다
- **동시성 16은 벌어진다** (1.65/1.70/1.83). compute-bound 구간은 커널·버전·스케줄링의 영향이 그대로 남는 구간이라는 방증인데, 어느 요인이 얼마인지는 이 데이터만으로 가릴 수 없다
- **TTFT 관찰이 다르다.** 멤버 실측의 동시성 16 TTFT는 네 변형 모두 124~142ms로 깨끗했다(동시성 16의 vanilla 129ms 대 eagle3 142ms, 약 +10%). 이 실습에서 만난 3.3초짜리 JIT 스파이크가 멤버 실측에서는 나타나지 않았다는 뜻인데, 원인이 vLLM 버전 차이인지 워밍업 경로 차이인지는 확인하지 못했다. 같은 하드웨어에서도 측정 조건에 따라 TTFT 결론이 "미미한 비용"과 "3.3초 스파이크"로 갈릴 수 있다는 것 자체가, [검증 절](#검증)의 교훈 — 수치는 로그와 함께 읽어야 한다 — 을 다른 각도에서 보여 준다
- **n-gram 분석의 각도가 상호 보완적이다.** 멤버 실측은 발동 횟수로 분석했다 — 8,159토큰 생성 동안 n-gram draft가 429회(약 5%)밖에 시도되지 않은 반면 eagle3는 3,556회 발동했다는 것이다. 이 글의 수락 길이 분포와 합치면 n-gram의 실패가 온전히 그려진다: **잘 발동하지도 않고(5%), 발동해도 들쭉날쭉하다(1.00~5.09)**

## 여담: 저자 실험 설계가 n-gram에 불리한 이유

그런데 실험 결과에서 왜 n-gram이 유독 나빴을까. 발동률과 수락 길이 분포를 보다 보면, **기법 자체의 결함이라기보다 애초에 이 실험 워크로드가 n-gram에 불리하게 짜여 있었던 건 아닐까**하는 생각이 든다. 

측정값에서 역산하면 입력은 요청당 약 123토큰, 출력은 512토큰이다. prompt lookup은 지금까지의 시퀀스에서 최근 토큰 패턴과 같은 대목을 찾아 그 뒤에 왔던 토큰을 제안하는 방식이라, 찾아볼 원천 텍스트가 클수록 유리하다. 그런데 입력이 123토큰뿐이면 매칭이 성립할 기회 자체가 드물다 — n-gram은 사실상 자기가 방금 생성한 출력 안에서만 매칭하고 있었고, 위의 발동률 5%가 그 결과다. 발동해도 문제가 남는다. 이 워크로드의 출력 512토큰은 입력을 되풀이하는 성격이 아니라 자유 생성이라, 매칭된 뒤에 실제로 같은 토큰이 이어질(수락될) 확률도 낮다.

그렇다면 설계가 달랐다면 어땠을까. 프롬프트를 길게 주고 출력이 그 내용을 되풀이하는 과제 — 문서 다듬기, RAG 인용, 코드 편집, 긴 요약 — 였거나 JSON·SQL처럼 구조화된 출력을 시켰다면, [7.2.1편에서 정리한 n-gram의 주 적용 조건]({% post_url 2026-08-29-Dev-LLM-Serving-Optimization-07-02-01-Speculative-Decoding-Concept %}#n-gram-모델-없는-추측)에 정확히 들어와 발동률과 수락률이 함께 올라갔을 수도 있었을 것 같다 — 물론 이 방향의 재실험은 해 보지 않았으므로 추정이다. 그러니 이 실습에서 얻을 수 있는 인사이트 중 하나는 "n-gram은 별로다"가 아니라 **"draft 방식은 워크로드에 매칭돼야 한다"**이다. 입력 재사용이 큰 워크로드는 다음 실습 주제인 LMCache(고급 KV 캐싱)의 주제이기도 하다.

<br>

# 정리

- 동시성 1에서 eagle3 2.06배, improved ngram 1.17배, ngram 1.06배. 동시성 16에서는 ngram이 0.94배(보정)로 부호가 바뀌고 eagle3만 1.70배로 남는다 — 배치가 차면 이득이 줄거나 손해로 바뀐다는 명제의 실측 확인
- 동시성 1 배속은 저자(A100)·이 실습·멤버 실측(같은 GPU)에서 전부 수렴한다. memory-bound 구간의 배속은 하드웨어가 약분되는 값이라 재현성이 좋고, compute-bound 구간(동시성 16)과 TTFT는 환경·측정 조건을 탄다
- 동시성 16의 TTFT 3.3초는 Triton 커널 JIT 아티팩트였다. vLLM 경고 로그와의 1:1 대응으로 진단하고, 저자 duration과의 3% 이내 일치로 교차 검증했다. 벤치 수치는 원본 결과·로그와 대조하기 전에는 결론으로 승격하지 않는 것이 안전하다
- 처리량 순서는 수락 길이의 효율(일관성)이 설명한다. ngram은 최댓값이 제일 높지만 분산이 커서 진다 — 분산이 곧 낭비다
- 공용 노드 실습의 안전 장치 — GPU PID·소유자 기반 정리, 포트 분리, 변형별 결과 파일 — 는 벤치의 정확성 장치이기도 했다

실습 파일은 [수정한 노트북]({{site.url}}/assets/data/llmso-ch07-speculative-decoding/llmso-ch07-speculative-decoding.ipynb)과 [setup.sh]({{site.url}}/assets/data/llmso-ch07-speculative-decoding/setup.sh)에 있다. 다음 실습은 입력 재사용이 큰 워크로드를 speculative decoding의 반대편, 캐싱 쪽에서 받는 답인 LMCache다.

<br>

# 참고 링크

- [Hands-On LLM Serving and Optimization (O'Reilly)](https://www.oreilly.com/library/view/hands-on-llm-serving/9798341621480/)
- [책 원본 실습 노트북 (SpecDecode.ipynb)](https://github.com/orca3/llm-model-inference/blob/main/ch07/SpecDecode.ipynb)
- [Spec-Bench](https://github.com/hemingkx/Spec-Bench)
- [RedHatAI/Qwen3-32B-speculator.eagle3 (Hugging Face)](https://huggingface.co/RedHatAI/Qwen3-32B-speculator.eagle3)
- [vLLM Speculative Decoding 문서](https://docs.vllm.ai/en/latest/features/spec_decode.html)
- [스터디 멤버의 같은 GPU 실측 — Speculative Decoding 벤치마크 (velog)](https://velog.io/@limes22/Speculative-Decoding-%EB%B2%A4%EC%B9%98%EB%A7%88%ED%81%AC)
- [7.1편: 고급 최적화 기법 개요]({% post_url 2026-08-29-Dev-LLM-Serving-Optimization-07-01-LLM-Serving-Advanced-Techniques-Overview %})
- [7.2.1편: speculative decoding 원리]({% post_url 2026-08-29-Dev-LLM-Serving-Optimization-07-02-01-Speculative-Decoding-Concept %})

<br>
