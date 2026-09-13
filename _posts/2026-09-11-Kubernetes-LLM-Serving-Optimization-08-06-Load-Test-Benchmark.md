---
title: "[LLM] LLM 서빙과 최적화: vLLM on Trainium 워크샵 - 8.6. 부하 테스트와 llmperf 벤치마크"
excerpt: "자작 스크립트와 llmperf로 vLLM에 부하를 걸고, 두 도구가 낸 수치를 나란히 놓을 수 있는지 확인해 보자."
categories:
  - Kubernetes
toc: true
use_math: false
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - EKS
  - vLLM
  - llmperf
  - Ray
  - Benchmark
  - Load-Testing
  - Trainium
  - Observability
  - Hands-On-LLM-Serving-and-Optimization-Study
  - Hands-On-LLM-Serving-and-Optimization-Study-Week-6
last_modified_at: 2026-09-13
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Hands-On LLM Serving and Optimization Study (LLMSO) 6주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- Lab 5가 클러스터에 만드는 것은 `performance-testing` 네임스페이스와 러너 파드 하나뿐이다. 부하는 그 파드 안에서 자작 스크립트 `basic_load_test.py`와 llmperf 두 도구로 건다
- `basic_load_test.py`가 찍는 `Tokens per Second: 54.1`은 처리량이 아니다. 분모가 월클록이 아니라 지연 시간의 **합**이라 동시성을 올려도 오르지 않고, 분자도 토큰이 아니라 `text.split()`으로 센 단어 수다. P99는 표본 30개에서 인덱스 29를 집으므로 최댓값 그 자체다
- 두 도구는 vLLM의 **서로 다른 엔드포인트**를 친다. llmperf는 Ray actor로 `/chat/completions`를 스트리밍으로, 자작 스크립트는 레거시 `/completions`를 비스트리밍으로 친다. llmperf가 내려받는 파일도 모델 가중치가 아니라 소스에 하드코딩된 토크나이저다
- 1차 실행은 완료 50건 / 에러 0건, TTFT mean 0.254초, E2E mean 1.184초, 전체 335.40 tok/s다. 유효 동시성은 4 부근에 잡히는데, Little's Law의 L은 **클라이언트 측 in-flight**라 이 값만으로 서버 병목을 판정할 수 없다
- 두 도구의 처리량 수치는 **나란히 놓을 수 없다.** 분모(지연 시간 합 vs 월클록), 분자(단어 수 vs 토큰 수), 워크로드(고정 프롬프트 vs 가우시안 샘플링)가 모두 다르다
- 부하 직후 대시보드 어디에도 게이지가 값을 물고 있는 장면이 없다. 14초 부하를 10초 간격으로 긁어 표본이 한두 개고 counter만 계단으로 남는다. 디코드 스텝은 초당 약 107회로 HBM 820 GiB/s의 약 27%, 출력 토큰 100만 개당 약 `$1.11`이다

<br>

# 두 부하 생성기 해부

[8.5.2편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-05-02-Grafana-vLLM-Dashboard %})에서 대시보드 한 장이 붙었지만 패널은 대부분 0이었다. 요청이 돌지 않았기 때문이다. Lab 5는 그 위에 부하를 걸어 패널이 실제로 움직이는지 보는 Lab이다.

부하를 거는 도구가 둘인데 성격이 다르다. 워크샵이 먼저 쓰는 `basic_load_test.py`는 요청이 왕복하는지, 실패가 없는지를 보는 기능 확인용이고, 찍히는 처리량 수치를 그대로 받아들일 대상은 아니다. 뒤에 쓰는 llmperf는 토큰 단위 지표를 재도록 설계된 벤치마크 도구이고, TTFT와 토큰 간 지연을 따로 낸다. 두 도구가 같은 서버를 쳤지만 **수치를 같은 축에 올릴 수는 없다** — 이유는 [두 도구 수치의 비교 가능성](#두-도구-수치의-비교-가능성)에서 다룬다.

이 글의 모든 출력에서 호스트명, 클러스터 이름, ELB DNS 이름은 예시 값으로 치환했다.

## Lab 5가 만드는 오브젝트

워크샵이 Lab 5 목표로 내건 항목은 다섯이다. 단일 요청의 지연 시간과 정확성을 보는 기본 기능 확인, llmperf를 쓴 성능 검증, CPU·메모리·Neuron 장치 사용량 확인, Prometheus·Grafana·CloudWatch 지표 수집, 그리고 부하와 모니터링 데이터의 상관관계 확인이다. 함께 적힌 관찰 지표 목록에는 확장 행동(오토스케일링에 걸리는 시간과 효과)과 경보 상태도 들어 있다.

실제로 한 범위는 이보다 좁다. CloudWatch는 [8.5.1편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-05-01-Prometheus-Metrics-Scrape %})에서 이미 배포하지 않았고 이 편에서도 설치 흔적이 없다. 오토스케일링과 경보도 이 편 범위 밖이다. 남는 것은 부하를 걸고, Neuron 사용률을 보고, Prometheus와 Grafana에 남은 흔적을 읽는 것까지다.

클러스터에 새로 만드는 오브젝트는 둘뿐이다. `performance-testing` 네임스페이스와, 그 안에 뜨는 `performance-test-runner` 파드 하나다. 파드 안에서 파이썬 패키지를 깔고 스크립트를 복사해 넣는 것이 전부이고, Deployment도 Job도 Service도 만들지 않는다.

## 설치 목록과 실제 사용 목록

설치 명령이 깔라고 적은 것과 스크립트가 실제로 부르는 것이 갈린다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ kubectl exec -it performance-test-runner -n performance-testing -- bash -c "
> pip install requests asyncio aiohttp numpy matplotlib pandas locust
> "
```

일곱 개를 깔지만 `basic_load_test.py`가 `import`하는 것은 여섯 줄이고, 그중 표준 라이브러리가 아닌 것은 하나다.

```python
import requests            # 유일한 서드파티 의존성
import time                # 표준 라이브러리
import concurrent.futures  # 표준 라이브러리
import statistics          # 표준 라이브러리
import json                # 표준 라이브러리
from datetime import datetime  # 표준 라이브러리
```

나머지 여섯 개의 사정은 이렇다.

| 패키지 | 설치된 버전 | 이 실습에서의 쓰임 |
|---|---|---|
| `requests` | 2.34.2 | 스크립트가 쓰는 유일한 서드파티 패키지 |
| `asyncio` | 4.0.0 | PyPI의 폐기 패키지. 코드가 없다 |
| `aiohttp` | 3.14.3 | 쓰지 않는다. 스크립트는 스레드 기반이다 |
| `numpy` | 2.2.6 | 쓰지 않는다. 통계는 표준 `statistics`로 낸다 |
| `matplotlib` | 3.10.9 | 쓰지 않는다. 그래프를 그리지 않는다 |
| `pandas` | 2.3.3 | 쓰지 않는다 |
| `locust` | 2.46.0 | 쓰지 않는다. locustfile이 없다 |

`asyncio`부터가 함정이다. PyPI의 `asyncio` 4.0.0은 배포 설명에 "Deprecated backport of asyncio; use the stdlib package instead"와 "**Do not install this package.**"가 적혀 있는 빈 껍데기다. asyncio는 Python 3.4부터 표준 라이브러리이므로 `pip install asyncio`는 필요가 없고, 이 패키지는 코드를 담고 있지 않아 표준 라이브러리를 가리지도 않는다. 실습에 해가 없는 대신 설치 목록의 실수다.

`locust`는 부하 테스트 프레임워크가 맞지만 이 실습에서 한 번도 돌지 않는다. locustfile을 작성한 적이 없고, 파드의 `/scripts`에 들어 있는 파일도 하나뿐이다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ kubectl exec -n performance-testing performance-test-runner -- ls /scripts
basic_load_test.py
```

깔리는 김에 딸려 오는 것도 있다. `pip list`에 `pytest` 9.1.1이 보이는데 `pip install` 목록에는 없다. locust 2.46.0의 직접 의존성이라 함께 설치된 것이고, `flask`·`gevent`·`pyzmq`·`msgpack`도 같은 경로로 들어온다. 쓰지 않는 패키지 하나를 목록에 적으면 그 의존성 트리가 통째로 이미지에 들어온다.

## 자작 스크립트 basic_load_test

결론부터 적으면 이 스크립트는 **요청이 왕복하는지 확인하는 도구**이고, 마지막에 찍는 `Tokens per Second` 값은 서버 처리량으로 읽으면 안 된다. 이유는 요청을 보내는 방식과 지표를 계산하는 방식 두 군데에 나뉘어 있다.

### 요청 경로와 동시성 모델

요청부는 이렇게 생겼다.

```python
def single_request(self, request_id):
    """Send a single completion request"""
    start_time = time.time()
    try:
        response = requests.post(
            # 레거시 completions 엔드포인트다. chat/completions가 아니다
            f"{self.base_url}/completions",
            headers={"Content-Type": "application/json"},
            json={
                "model": "tinyLlama/TinyLlama-1.1B-Chat-v1.0",
                # 프롬프트는 request_id만 바뀌는 고정 문장이다
                "prompt": f"Request {request_id}: Tell me about artificial intelligence",
                "max_tokens": 100,
                "temperature": 0.7
            },
            timeout=60
        )
        # 응답을 전부 받은 뒤의 시각. 왕복 시간 하나만 남는다
        end_time = time.time()
```

여기서 짚을 것이 셋이다.

첫째, 치는 엔드포인트가 `/v1/completions`다. OpenAI 호환 서버의 **레거시 completions**이고 채팅 템플릿을 태우지 않는다. 뒤에서 쓰는 llmperf는 `/v1/chat/completions`를 친다. 두 테스트가 같은 서버의 서로 다른 라우트를 치는 셈이고, [8.3.1편의 OpenAI 호환 라우트]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-03-01-vLLM-Deployment %}#openai-호환-라우트)에서 확인한 두 라우트가 각각 한 번씩 쓰인다.

둘째, 스트리밍을 쓰지 않는다. `stream: true`를 넣지 않았으므로 응답 전체가 한 번에 온다. 그래서 잴 수 있는 값이 `end_time - start_time` 하나뿐이고, TTFT(첫 토큰까지 걸린 시간)와 토큰 간 지연을 나눌 수 없다.

셋째, 동시성은 스레드 풀이다.

```python
# asyncio도 멀티프로세스도 아니다. 블로킹 requests 호출을 스레드 N개가 나눠 돈다
with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
    ...
    futures = [executor.submit(self.single_request, i) for i in range(total_requests)]
    for future in concurrent.futures.as_completed(futures):
        self.results.append(future.result())
```

`aiohttp`와 `asyncio`를 깔아 놓고 정작 쓰는 것은 `concurrent.futures`다. 각 스레드가 블로킹 `requests.post`를 돌리므로, 네트워크 대기 중에는 GIL을 놓아 다섯 요청이 실제로 겹친다.

`run_load_test`에는 시간 기반 분기(`duration_seconds`)도 들어 있지만 이번 실행에서는 타지 않는다. `__main__`이 넘기는 인자가 요청 수뿐이기 때문이다.

```python
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python basic_load_test.py <vllm_url> [requests] [workers]")
        sys.exit(1)

    base_url = sys.argv[1]
    total_requests = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    max_workers = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    tester = VLLMLoadTester(base_url, max_workers)
    # duration_seconds를 넘기지 않으므로 시간 기반 분기는 죽은 코드다
    tester.run_load_test(total_requests=total_requests)
```

### 지표 산출식 세 가지

출력에 찍히는 숫자 셋이 이름과 다른 것을 재고 있다. 남의 스크립트를 받아 쓸 때 가장 먼저 볼 지점이라 세 개를 함께 놓는다.

**하나. "tokens"는 토큰이 아니다.**

```python
"tokens": len(response.json().get("choices", [{}])[0].get("text", "").split()),
```

`text.split()`은 공백으로 쪼갠 결과이므로 여기서 세는 것은 **단어 수**다. 요청 페이로드의 `max_tokens`가 100인데 출력의 `Average Tokens per Response`가 50.5로 찍히는 데에는 이것이 크게 작용한다. 토큰이 100개 생성돼도 영어 문장에서 토큰은 대체로 단어보다 잘게 쪼개지므로 공백 기준 단어 수는 그 절반쯤이 된다. 다만 이것만이 원인은 아니다. 뒤의 [부하 이후의 대시보드 상태](#부하-이후의-대시보드-상태)에서 보듯 기본 부하 테스트에서는 `finished_reason="stop"` 계열도 함께 올랐으므로, 100토큰을 채우지 못하고 먼저 끝난 응답이 섞여 있다. 어느 쪽이든 이 값이 모델 토크나이저를 태워 센 값이 아니라는 점은 그대로다.

**둘. 처리량의 분모가 월클록이 아니다.**

```python
total_tokens = sum(tokens_per_request)
total_time = sum(latencies)          # 벽시계 경과 시간이 아니라 지연 시간의 합이다
print(f"Tokens per Second: {total_tokens/total_time:.1f}")
```

`sum(latencies)`는 요청 30건의 지연 시간을 전부 더한 값이다. 다섯 스레드가 병렬로 돌아 실제 경과 시간이 짧아져도 이 합은 줄지 않는다. 즉 이 수치는 **요청을 하나씩 순차로 돌렸다고 가정했을 때의 환산값**이고, 동시성을 올려도 값이 오르지 않는 구조다.

실제 출력으로 검산하면 맞아떨어진다. 응답당 단어 50.5개 × 30건 = 1515, 평균 지연 0.93초 × 30건 = 27.9초다. 출력의 `Total Time`이 28.0초이므로 `1515 / 28.0 = 54.1`이 된다. 0.93은 소수 둘째 자리까지 반올림된 표시값이라 27.9와 28.0의 차이가 여기서 생긴다. 뒤에서 볼 1차 실행의 `Tokens per Second: 54.1`이 정확히 이 값이다.

**셋. 표본 30개의 P99는 최댓값이다.**

```python
print(f"95th Percentile: {sorted(latencies)[int(len(latencies)*0.95)]:.2f}s")
print(f"99th Percentile: {sorted(latencies)[int(len(latencies)*0.99)]:.2f}s")
```

`int(30 * 0.99)`은 29이고, 30개짜리 리스트의 마지막 인덱스도 29다. 보간도 하지 않으므로 P99는 정렬된 지연 시간의 마지막 원소, 즉 최댓값 그 자체가 된다. 실행 결과에서 P99와 Max가 1차는 둘 다 `1.66`, 2차는 둘 다 `1.91`로 같은 것이 그 결과다. 표본이 100개 이하면 이 식의 P99는 항상 최댓값이다. `int(n × 0.99)`가 `n - 1`과 같아지는 조건이 `n ≤ 100`이다.

<details markdown="1">
<summary><b>basic_load_test.py 전문</b></summary>

```python
#!/usr/bin/env python3
import requests
import time
import concurrent.futures
import statistics
import json
from datetime import datetime

class VLLMLoadTester:
    def __init__(self, base_url, max_workers=10):
        self.base_url = base_url.rstrip('/')
        self.max_workers = max_workers
        self.results = []

    def single_request(self, request_id):
        """Send a single completion request"""
        start_time = time.time()
        try:
            response = requests.post(
                f"{self.base_url}/completions",
                headers={"Content-Type": "application/json"},
                json={
                    "model": "tinyLlama/TinyLlama-1.1B-Chat-v1.0",
                    "prompt": f"Request {request_id}: Tell me about artificial intelligence",
                    "max_tokens": 100,
                    "temperature": 0.7
                },
                timeout=60
            )
            end_time = time.time()

            if response.status_code == 200:
                return {
                    "request_id": request_id,
                    "status": "success",
                    "latency": end_time - start_time,
                    "tokens": len(response.json().get("choices", [{}])[0].get("text", "").split()),
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "request_id": request_id,
                    "status": "error",
                    "latency": end_time - start_time,
                    "error_code": response.status_code,
                    "timestamp": datetime.now().isoformat()
                }
        except Exception as e:
            end_time = time.time()
            return {
                "request_id": request_id,
                "status": "exception",
                "latency": end_time - start_time,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def run_load_test(self, total_requests=100, duration_seconds=None):
        """Run load test with specified parameters"""
        print(f"Starting load test with {self.max_workers} workers")
        print(f"Target: {self.base_url}")

        start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            if duration_seconds:
                # Duration-based testing
                request_id = 0
                futures = []

                while time.time() - start_time < duration_seconds:
                    future = executor.submit(self.single_request, request_id)
                    futures.append(future)
                    request_id += 1
                    time.sleep(0.1)  # Small delay between request submissions

                # Wait for all requests to complete
                for future in concurrent.futures.as_completed(futures):
                    self.results.append(future.result())
            else:
                # Request count-based testing
                futures = [executor.submit(self.single_request, i) for i in range(total_requests)]

                for future in concurrent.futures.as_completed(futures):
                    self.results.append(future.result())
                    if len(self.results) % 10 == 0:
                        print(f"Completed {len(self.results)}/{total_requests} requests")

        self.analyze_results()

    def analyze_results(self):
        """Analyze and print test results"""
        if not self.results:
            print("No results to analyze")
            return

        successful_requests = [r for r in self.results if r["status"] == "success"]
        failed_requests = [r for r in self.results if r["status"] != "success"]

        if successful_requests:
            latencies = [r["latency"] for r in successful_requests]
            tokens_per_request = [r.get("tokens", 0) for r in successful_requests if "tokens" in r]

            print("\n=== LOAD TEST RESULTS ===")
            print(f"Total Requests: {len(self.results)}")
            print(f"Successful: {len(successful_requests)} ({len(successful_requests)/len(self.results)*100:.1f}%)")
            print(f"Failed: {len(failed_requests)} ({len(failed_requests)/len(self.results)*100:.1f}%)")

            print(f"\n=== LATENCY STATISTICS ===")
            print(f"Average Latency: {statistics.mean(latencies):.2f}s")
            print(f"Median Latency: {statistics.median(latencies):.2f}s")
            print(f"95th Percentile: {sorted(latencies)[int(len(latencies)*0.95)]:.2f}s")
            print(f"99th Percentile: {sorted(latencies)[int(len(latencies)*0.99)]:.2f}s")
            print(f"Min Latency: {min(latencies):.2f}s")
            print(f"Max Latency: {max(latencies):.2f}s")

            if tokens_per_request:
                print(f"\n=== TOKEN STATISTICS ===")
                print(f"Average Tokens per Response: {statistics.mean(tokens_per_request):.1f}")
                total_tokens = sum(tokens_per_request)
                total_time = sum(latencies)
                print(f"Tokens per Second: {total_tokens/total_time:.1f}")

        if failed_requests:
            print(f"\n=== FAILURE ANALYSIS ===")
            error_types = {}
            for req in failed_requests:
                error_type = req.get("error_code", req.get("error", "unknown"))
                error_types[error_type] = error_types.get(error_type, 0) + 1

            for error, count in error_types.items():
                print(f"{error}: {count} requests")

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python basic_load_test.py <vllm_url> [requests] [workers]")
        sys.exit(1)

    base_url = sys.argv[1]
    total_requests = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    max_workers = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    tester = VLLMLoadTester(base_url, max_workers)
    tester.run_load_test(total_requests=total_requests)
```

</details>

## llmperf

llmperf는 Ray 프로젝트가 공개한 LLM 엔드포인트 벤치마크 도구다. 여러 백엔드(OpenAI 호환, Anthropic, SageMaker, Vertex 등)를 같은 인터페이스로 치고, TTFT와 토큰 간 지연을 요청 단위로 기록한다. 워크샵은 이 도구를 "업계 표준 벤치마킹"이라고 부르는데, 레포는 **2024년 12월 9일부터 archived 상태**다. 마지막 푸시가 그날이고 이후 읽기 전용으로 잠겼다. 도구가 널리 쓰인 것과 지금도 유지되는 것은 다른 문제이므로, 그대로 가져다 쓸 때 알아 둘 점이다.

레포에는 실행 진입점이 둘 있다. 이번에 쓰는 것은 부하 테스트용 `token_benchmark_ray.py`이고, 다른 하나는 응답 정확성을 보는 `llm_correctness.py`다.

### 실행 구조

이름에 `ray`가 붙은 대로 Ray를 쓴다. 동작은 이렇다.

- `--num-concurrent-requests N`만큼 파이썬 스레드를 띄운다
- 각 스레드가 `@ray.remote`로 선언된 `OpenAIChatCompletionsClient` actor를 하나씩 만든다
- 정확히는 actor 하나만 담은 `ray.util.ActorPool`을 스레드마다 따로 만든다. actor 여러 개를 공유 풀에 넣는 구조가 아니다
- 그래서 스레드 하나가 물고 있는 요청은 항상 한 건이고, 그 한 건이 끝나야 다음 건이 들어간다. 전체 in-flight가 `--num-concurrent-requests`로 고정되는 것이 이 구조의 결과다
- 결과를 거둬 가는 `get_next_ready()`는 기본이 논블로킹이라, 응답이 오지 않은 동안에도 스레드가 빈 결과를 받아 루프를 계속 돈다. 대기하는 동안 CPU를 쓴다는 뜻이다
- actor가 실제 HTTP 호출을 하는데, 이때 `"stream": true`를 붙여 SSE 청크를 하나씩 받으며 첫 청크 도착 시각으로 TTFT를 잰다

실행 로그에 `Started a local Ray instance.`가 찍히는 것이 그 결과다. 파드 안에 Ray 클러스터가 하나 뜬 것이고, 별도 Ray 클러스터를 붙일 필요는 없다.

스트리밍을 쓴다는 점이 자작 스크립트와 갈리는 지점이다. 첫 토큰 도착 시각을 따로 찍을 수 있으므로 TTFT와 E2E를 나눠 낼 수 있다.

### 워크로드 생성 방식

워크샵이 "실제와 유사한 매개변수"라고 부른 것의 실체는 가우시안 샘플링이다. llmperf 소스의 `sample_random_positive_int(mean, stddev)`가 **요청마다** 입력 목표 길이와 `max_tokens`를 새로 뽑는다. 이번 실행에서는 입력이 평균 256 / 표준편차 50, 출력이 평균 100 / 표준편차 20이다.

길이를 흩뿌리는 것으로 흉내내는 것은 넷이다.

- **프리필 비용의 분산** — 입력 길이가 고정이면 TTFT 분포가 인위적으로 좁아진다
- **배치 구성의 이질성** — continuous batching은 길이가 제각각인 시퀀스를 한 배치에 섞는다
- **KV 캐시 점유 변동** — 시퀀스마다 잡아먹는 캐시 양이 달라진다
- **완료 시점의 산포** — 출력 길이가 다르면 요청이 끝나는 시점이 흩어진다

흉내내지 못하는 것도 하나 있다. 이 도구는 도착 과정(arrival process)이 없는 **폐루프(closed-loop)** 부하 생성기다. in-flight 요청 수가 항상 `--num-concurrent-requests`로 고정되므로, 요청 하나가 끝나야 다음 하나가 들어간다. 서버가 느려지면 부하도 따라 줄어든다는 뜻이다. 실제 트래픽은 개루프(open-loop)에 가까워서 서버가 느려져도 요청이 계속 도착하고 큐가 쌓인다. 폐루프 측정에서는 그 큐 폭증이 재현되지 않는다.

프롬프트 집합 자체는 매번 같다. 소스에 `random.seed(11111)`이 하드코딩돼 있어 같은 플래그로 돌리면 같은 길이 수열이 나온다. 이번에 두 번 돌린 결과가 그 증거다. 두 실행의 `number_input_tokens` 백분위가 소수점 끝까지 일치한다 — p90 `326.7`, p95 `353.44999999999993`, p99 `406.72999999999996`에 min `131`, max `418`까지 같다. 두 실행의 평균이 259.78과 260.52로 조금 다른 것은 토크나이즈 오차 때문이 아니다. `number_input_tokens`는 완성된 프롬프트를 다시 센 값이 아니라 `sample_random_positive_int`가 뽑은 **목표 정수 그 자체**다. 소스에서 `randomly_sample_sonnet_lines_prompt`가 프롬프트와 뽑은 정수를 함께 돌려주고, 클라이언트가 그 정수를 `number_input_tokens`에 그대로 싣는다. min이 `131`, max가 `418`로 정수인 것도 그래서다. 그렇다면 남는 설명은 어떤 프롬프트가 실제로 쓰였는지가 실행마다 달랐다는 쪽이다. 각 스레드는 `request_index`를 동시성 수만큼 건너뛰며 도는데, 50건을 채우는 순간 나머지 스레드의 진행이 잘리므로 스레드별 완료 건수가 매번 같지 않다. 다만 2차 실행의 개별 응답을 남기지 않아 이 설명을 실측으로 확인하지는 못했다.

### 토크나이저 고정과 모델 미적재

실행하면 파일 네 개를 내려받는다. `tokenizer_config.json`, `tokenizer.model`, `tokenizer.json`, `special_tokens_map.json`으로 합쳐 2.4 MB 남짓이다. 모델 가중치가 아니다.

llmperf 소스는 토크나이저를 `LlamaTokenizerFast.from_pretrained("hf-internal-testing/llama-tokenizer")`로 고정해서 부른다. `--model`에 무엇을 넣든 이 레포에서 받는다. Hugging Face에서 그 레포의 파일 목록을 확인하면 방금 받은 네 개와 정확히 일치한다.

의도는 소스 주석에 적혀 있다. 토큰 수를 Llama 토크나이저로 센다고 못박고, 하나의 토크나이저를 쓰는 것이 서로 다른 LLM을 비교할 때 더 공정하다고 설명한다. 모델마다 어휘 크기가 다르면 같은 문장의 토큰 수가 달라져 tok/s를 비교할 수 없으니, 측정 기준을 하나로 고정한 것이다. 뒤집어 말하면 llmperf가 찍는 `number_output_tokens`는 **TinyLlama가 실제로 생성한 토큰 수가 아니라** Llama 토크나이저로 다시 센 값이다. `--model` 플래그는 요청 body의 `model` 필드로만 실린다.

가중치를 로드할 수단 자체가 없다는 부수 증거도 로그에 남아 있다.

```text
[transformers] PyTorch was not found. Models won't be available and only tokenizers, configuration and file/data utilities can be used.
```

llmperf 설치 목록에 `transformers`는 있지만 `torch`는 없다. 토크나이저와 설정 파일만 다룰 수 있는 상태라 모델을 올릴 수 없다.

같은 줄 아래에 뜨는 `HF_TOKEN` 경고는 공개 레포에 익명으로 접근할 때 나오는 rate limit 안내다. 네 파일 모두 진행률 100%로 받았으므로 실습에 영향이 없다.

<br>

# 적용과 관찰: 두 도구로 부하 걸기

## 러너 파드와 기본 부하 테스트

### 네임스페이스와 러너 파드

부하를 거는 주체는 클러스터 안의 파드 하나다. 배스천에서 직접 쏘지 않고 파드를 두는 것은 부하 생성기와 서버 사이의 네트워크 경로를 클러스터 안으로 넣기 위해서인데, 이번 구성에서는 그 파드가 다시 외부 ELB 주소를 치므로 경로가 클러스터 밖으로 한 번 나갔다 돌아온다.

```yaml
# performance-test-pod.yaml
apiVersion: v1
kind: Pod
metadata:
  name: performance-test-runner
  namespace: performance-testing
spec:
  containers:
  - name: performance-tester
    image: python:3.10-slim              # 부하 생성기만 돌리는 최소 이미지
    command: ["sleep", "infinity"]       # 붙어서 exec 할 수 있도록 계속 살려 둔다
    resources:
      requests:
        cpu: 500m
        memory: 1Gi
      limits:
        cpu: 2000m                       # CPU 상한 2코어. 뒤의 유효 동시성 해석에서 다시 쓴다
        memory: 4Gi
    volumeMounts:
    - name: test-scripts
      mountPath: /scripts
  volumes:
  - name: test-scripts
    emptyDir: {}                         # 파드가 사라지면 스크립트도 결과도 함께 사라진다
  restartPolicy: Never
```

```shell
ubuntu@ip-10-0-1-100:~/workshop$ kubectl create namespace performance-testing
namespace/performance-testing created

ubuntu@ip-10-0-1-100:~/workshop$ kubectl apply -f performance-test-pod.yaml
pod/performance-test-runner created

ubuntu@ip-10-0-1-100:~/workshop$ kubectl get pod -n performance-testing

# 실행 결과
NAME                      READY   STATUS    RESTARTS   AGE
performance-test-runner   1/1     Running   0          37s
```

`limits.cpu: 2000m`은 그냥 넘길 값이 아니다. 이 2코어 안에서 파이썬 스레드 다섯 개, Ray actor 프로세스 다섯 개, raylet이 함께 돌게 된다. [클라이언트 측 in-flight와 서버 측 대기열](#클라이언트-측-in-flight와-서버-측-대기열)에서 이 값이 다시 나온다.

`emptyDir`도 마찬가지다. llmperf 클론과 벤치마크 결과 JSON이 전부 여기 들어가므로, 파드를 지우면 결과 파일도 같이 없어진다.

### 환경 변수와 엔드포인트

워크샵은 시작에서 변수 여섯 개를 export한다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ export AWS_REGION=us-west-2
ubuntu@ip-10-0-1-100:~/workshop$ export CLUSTER_NAME=my-neuron-cluster
ubuntu@ip-10-0-1-100:~/workshop$ export MONITORING_NAMESPACE=monitoring
ubuntu@ip-10-0-1-100:~/workshop$ export VLLM_ENDPOINT=$(kubectl get service vllm-service -n default -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
ubuntu@ip-10-0-1-100:~/workshop$ export VLLM_NAMESPACE=default
ubuntu@ip-10-0-1-100:~/workshop$ export VLLM_URL="http://$VLLM_ENDPOINT:8080/v1"

ubuntu@ip-10-0-1-100:~/workshop$ echo "vLLM Endpoint: $VLLM_URL"
vLLM Endpoint: http://<elb-id>.us-west-2.elb.amazonaws.com:8080/v1
```

이 중 뒤에 실제로 쓰이는 것은 `VLLM_ENDPOINT`와 `VLLM_URL` 둘뿐이다. `AWS_REGION`·`CLUSTER_NAME`·`MONITORING_NAMESPACE`를 참조하는 명령이 이 Lab 전체에 하나도 없고, `VLLM_NAMESPACE`도 바로 다음 줄의 `echo`에서만 쓰인다. `kubectl` 호출은 전부 `-n performance-testing`이나 `-n default`를 직접 적는다.

주소도 확인해 둘 필요가 있다. `VLLM_URL`이 가리키는 것은 [8.3.2편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-03-02-Service-LoadBalancer %})에서 만든 `vllm-service`의 CLB이고 포트가 8080이다. [8.4편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-04-Ingress-Nginx-Routing %})에서 포트 없는 접근 경로를 만들어 뒀지만 이번 부하는 그쪽을 쓰지 않는다. 즉 부하 트래픽은 ingress-nginx 컨트롤러를 거치지 않고 `vllm-service` CLB로 직행한다.

### 패키지 설치

파드 안에서 `pip install`을 돌린다. 출력에서 결론에 해당하는 부분만 보면 이렇다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ kubectl exec -it performance-test-runner -n performance-testing -- bash -c "
> pip install requests asyncio aiohttp numpy matplotlib pandas locust
> "

# 실행 결과 (발췌). 일곱 개를 적었는데 62개가 깔린다
Collecting requests
  Downloading requests-2.34.2-py3-none-any.whl (73 kB)
Collecting asyncio
  Downloading asyncio-4.0.0-py3-none-any.whl (5.6 kB)
...
Successfully installed aiohappyeyeballs-2.7.1 aiohttp-3.14.3 ... asyncio-4.0.0 ... locust-2.46.0 ... matplotlib-3.10.9 ... numpy-2.2.6 pandas-2.3.3 ... pytest-9.1.1 ... requests-2.34.2 ...
WARNING: Running pip as the 'root' user can result in broken permissions and conflicting behaviour with the system package manager. It is recommended to use a virtual environment instead: https://pip.pypa.io/warnings/venv
```

`asyncio-4.0.0`이 5.6 kB짜리 wheel로 받아지는 것이 눈에 띈다. 앞에서 본 대로 코드가 없는 배포판이라 크기가 이 정도다.

<details markdown="1">
<summary><b>설치 후 pip list 전문</b></summary>

```text
Package            Version
------------------ ------------
aiohappyeyeballs   2.7.1
aiohttp            3.14.3
aiosignal          1.4.0
async-timeout      5.0.1
asyncio            4.0.0
attrs              26.1.0
bidict             0.23.1
blinker            1.9.0
brotli             1.2.0
certifi            2026.7.22
charset-normalizer 3.5.1
click              8.5.0
ConfigArgParse     1.7.7
contourpy          1.3.2
cycler             0.12.1
exceptiongroup     1.3.1
Flask              3.1.3
flask-cors         6.0.5
Flask-Login        0.6.3
fonttools          4.65.0
frozenlist         1.8.0
gevent             25.9.1
geventhttpclient   2.3.9
greenlet           3.5.5
h11                0.16.0
idna               3.19
iniconfig          2.3.0
itsdangerous       2.2.0
Jinja2             3.1.6
kiwisolver         1.5.1
locust             2.46.0
MarkupSafe         3.0.3
matplotlib         3.10.9
msgpack            1.2.2
multidict          6.8.0
numpy              2.2.6
packaging          26.3
pandas             2.3.3
pillow             12.3.0
pip                23.0.1
pluggy             1.6.0
propcache          0.5.2
psutil             7.2.2
Pygments           2.21.0
pyparsing          3.3.2
pytest             9.1.1
python-dateutil    2.9.0.post0
python-engineio    4.14.0
python-socketio    5.16.4
pytz               2026.3.post1
pyzmq              27.2.0
requests           2.34.2
setuptools         79.0.1
simple-websocket   1.1.0
six                1.17.0
tomli              2.4.1
typing_extensions  4.16.0
tzdata             2026.3
urllib3            2.7.0
websocket-client   1.9.2
Werkzeug           3.1.8
wheel              0.46.3
wsproto            1.3.2
yarl               1.24.5
zope.event         6.2
zope.interface     8.6
```

</details>

스크립트는 배스천에서 작성해 `kubectl cp`로 파드에 넣는다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ kubectl cp basic_load_test.py performance-testing/performance-test-runner:/scripts/
ubuntu@ip-10-0-1-100:~/workshop$ kubectl exec -n performance-testing performance-test-runner -- ls /scripts
basic_load_test.py
```

### 기본 부하 테스트 실행

요청 30건, 워커 5개로 돌린다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ export VLLM_ENDPOINT=$(kubectl get service vllm-service -n default -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
ubuntu@ip-10-0-1-100:~/workshop$ export VLLM_URL="http://$VLLM_ENDPOINT:8080/v1"

# 세 번째 인자 5가 max_workers, 두 번째 인자 30이 총 요청 수다
ubuntu@ip-10-0-1-100:~/workshop$ kubectl exec -it performance-test-runner -n performance-testing -- python /scripts/basic_load_test.py $VLLM_URL 30 5
Starting load test with 5 workers
Target: http://<elb-id>.us-west-2.elb.amazonaws.com:8080/v1
Completed 10/30 requests
Completed 20/30 requests
Completed 30/30 requests

=== LOAD TEST RESULTS ===
Total Requests: 30
Successful: 30 (100.0%)
Failed: 0 (0.0%)

=== LATENCY STATISTICS ===
Average Latency: 0.93s
Median Latency: 1.03s
95th Percentile: 1.56s
99th Percentile: 1.66s
Min Latency: 0.16s
Max Latency: 1.66s

=== TOKEN STATISTICS ===
Average Tokens per Response: 50.5
Tokens per Second: 54.1
```

같은 명령을 한 번 더 돌린 결과도 크게 다르지 않다.

| 항목 | 1차 | 2차 |
|---|---|---|
| 성공 / 실패 | 30 / 0 | 30 / 0 |
| Average Latency | 0.93s | 1.02s |
| Median Latency | 1.03s | 0.98s |
| 95th Percentile | 1.56s | 1.76s |
| 99th Percentile | 1.66s | 1.91s |
| Min / Max Latency | 0.16s / 1.66s | 0.16s / 1.91s |
| Average Tokens per Response | 50.5 | 54.9 |
| Tokens per Second | 54.1 | 54.0 |

두 실행에서 `Tokens per Second`가 54.1과 54.0으로 붙어 있는 것이 눈에 띈다. 응답당 단어 수는 50.5와 54.9로 8% 넘게 차이 나는데 처리량 수치는 거의 그대로다. 분모가 지연 시간의 합이라 단어가 늘면 지연도 같이 늘어 상쇄되기 때문이다. 이 수치가 서버 처리량이 아니라 **요청 한 건의 평균 생성 속도**에 가깝다는 것이 여기서 드러난다.

P99와 Max가 1차 `1.66`, 2차 `1.91`로 각각 같은 것도 앞에서 본 인덱스 계산 그대로다.

### neuron-top과 Grafana 관찰

부하가 도는 동안 노드에서 `neuron-top`을 띄우면 NeuronCore 사용률이 움직인다.

![기본 부하 테스트 중의 neuron-top]({{site.url}}/assets/images/llmso-aws-workshop-performance-test-basic-neurontop.gif){: .align-center}

<center><sup>직접 캡처. 기본 부하 테스트를 도는 동안의 neuron-top 화면이다. NeuronCore v2 Utilization의 NC0과 NC1이 아이들 구간 0.00%에서 83% 부근까지 함께 올랐다가 다시 0으로 떨어지는 구간이 두 번 나온다.</sup></center>

읽을 것이 셋이다.

첫째, `ND0` 아래 `NC0`과 `NC1` 두 막대가 **함께** 올라간다. [8.3.1편의 칩 1개 요청과 코어 2개 텐서 병렬]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-03-01-vLLM-Deployment %}#칩-1개-요청과-코어-2개-텐서-병렬)에서 정리한 대로 `TENSOR_PARALLEL_SIZE=2`라 가중치가 두 코어에 쪼개져 있고, 한 요청이 두 코어를 함께 쓴다. 한쪽만 오르는 그림이 아니다.

둘째, 부하 구간이 두 번 나온다. 기본 부하 테스트를 두 번 돌린 것과 대응한다.

셋째, `Memory Usage Summary`의 Device Used Memory가 3.6 GB로 부하와 무관하게 일정하다. Tensors 2.1 GB, Constants 285.3 MB, Model Code 222.0 MB, Model Scratchpad 1.0 GB가 그 내역인데, 이 값들은 모델이 올라간 시점에 확정되고 요청이 늘어도 움직이지 않는다.

같은 시점의 Grafana 대시보드는 이렇다.

![기본 부하 테스트 직후의 vLLM 대시보드]({{site.url}}/assets/images/llmso-aws-workshop-performance-test-basic-grafana.png){: .align-center}

<center><sup>직접 캡처. 기본 부하 테스트 직후의 vLLM Inference Metrics 대시보드다. 왼쪽 stat 패널에 47과 22 두 값이 표시되고, 그 오른쪽 두 패널은 0, KV Cache Usage는 0%이며, Total Prompt Tokens가 850, Total Generated Tokens가 7131이다. Request Success Over Time에서 두 계열이 02:30 부근에 각각 47과 22로 올라 평평해진다.</sup></center>

여기서 바로 눈에 걸리는 것이 있다. **부하를 걸었는데 게이지 패널이 전부 0이다.** 0 두 개와 0%가 그대로다. 값을 물고 있는 순간이 캡처에 잡히지 않았고, 대신 그 두 패널의 스파크라인에 뾰족한 스파이크 자국만 남았다.

누적값 패널은 반대로 값이 올라 그 높이에 머물러 있다. Total Prompt Tokens 850, Total Generated Tokens 7131이고, `Request Success Over Time`의 두 계열도 02:30 부근에 한 번 오른 뒤 평평하다. 부하가 끝났는데 그래프가 내려오지 않는 것이다.

두 현상 모두 지표가 안 잡힌 것이 아니라 창의 문제다. 자세한 것은 뒤의 [부하 지속 시간과 스크레이프 간격](#부하-지속-시간과-스크레이프-간격)에서 정리한다.

화면 위쪽 네 패널 중 두 번째와 세 번째는 캡처에 제목이 보이지 않는다. 이 둘을 `Running Requests`와 `Waiting Requests`로 지목한 근거는 [8.5.2편의 패널과 쿼리]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-05-02-Grafana-vLLM-Dashboard %}#패널과-쿼리)에서 정리한 대시보드 JSON의 `gridPos` 배치다. 위쪽 행이 `x: 0` Total Successful Requests, `x: 6` Running Requests, `x: 12` Waiting Requests, `x: 18` KV Cache Usage 순이고, 맨 오른쪽 게이지가 KV Cache Usage인 것이 화면과 맞는다. 첫 패널에 `Total Requests`라는 글자가 두 번 찍힌 것도 그 JSON의 `legendFormat` 값이 `Total Requests`이기 때문이다.

## llmperf 토큰 벤치마크

### llmperf 설치

같은 파드 안에 git을 깔고 레포를 클론한 뒤 editable 모드로 설치한다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ kubectl exec -it performance-test-runner -n performance-testing -- bash -c "
> pip install --upgrade pip && \
> apt-get update && apt-get install -y git && \
> cd /tmp && \
> git clone https://github.com/ray-project/llmperf.git && \
> cd llmperf && \
> pip install ray && \
> pip install -e .
> "

# 실행 결과 (발췌)
Building wheels for collected packages: LLMPerf, docopt
  Building editable for LLMPerf (pyproject.toml) ... done
Successfully built LLMPerf docopt
Successfully installed LLMPerf-0.1.0 ... boto3-1.43.92 ... google-cloud-aiplatform-1.133.0 ... litellm-1.73.6.post1 ... openai-3.13.0 ... tokenizers-0.23.2 transformers-5.17.0 ...
```

설치 목록을 보면 왜 무거운지 알 수 있다. llmperf가 여러 백엔드를 지원하는 도구라 `boto3`(SageMaker/Bedrock), `google-cloud-aiplatform`(Vertex), `litellm`, `openai`가 전부 딸려 온다. 이번 실습은 그중 OpenAI 호환 어댑터 하나만 쓴다.

여기서 `torch`가 목록에 없다는 점이 앞에서 본 `PyTorch was not found` 경고와 이어진다. `transformers`는 깔리지만 모델을 올릴 백엔드가 없다.

<details markdown="1">
<summary><b>llmperf 설치 출력 전문 (발췌 확장)</b></summary>

```text
Building wheels for collected packages: LLMPerf, docopt
  Building editable for LLMPerf (pyproject.toml) ... done
  Created wheel for LLMPerf: filename=llmperf-0.1.0-0.editable-py3-none-any.whl size=6173
  Building wheel for docopt (pyproject.toml) ... done
  Created wheel for docopt: filename=docopt-0.6.2-py2.py3-none-any.whl size=13783
Successfully built LLMPerf docopt
Installing collected packages: docopt, zipp, websockets, truststore, tqdm, tenacity, sniffio, shellingham,
 safetensors, regex, python-dotenv, pydantic-core, pycparser, pyasn1, protobuf, opentelemetry-api, num2words,
 mdurl, jmespath, jiter, httpcore, hf-xet, grpcio, google-crc32c, fsspec, docutils, docstring_parser, colorama,
 annotated-types, annotated-doc, tiktoken, rsa, pydantic, pyasn1-modules, proto-plus, markdown-it-py,
 importlib-metadata, httpcore2, googleapis-common-protos, google-resumable-media, cffi, botocore, anyio,
 seaborn, s3transfer, rich, httpx2, httpx, grpcio-status, cryptography, awscli, typer, openai, huggingface-hub,
 grpc-google-iam-v1, google-auth, boto3, tokenizers, google-genai, google-api-core, transformers, litellm,
 google-cloud-core, google-cloud-storage, google-cloud-resource-manager, google-cloud-bigquery,
 google-cloud-aiplatform, LLMPerf
  Attempting uninstall: protobuf
    Found existing installation: protobuf 7.36.1
    Uninstalling protobuf-7.36.1:
      Successfully uninstalled protobuf-7.36.1
Successfully installed LLMPerf-0.1.0 annotated-doc-0.0.5 annotated-types-0.8.0 anyio-4.15.1 awscli-1.46.1
 boto3-1.43.92 botocore-1.43.92 cffi-2.1.1 colorama-0.4.6 cryptography-50.0.1 docopt-0.6.2
 docstring_parser-0.18.0 docutils-0.19 fsspec-2026.7.0 google-api-core-2.36.0 google-auth-2.58.0
 google-cloud-aiplatform-1.133.0 google-cloud-bigquery-3.45.0 google-cloud-core-2.7.0
 google-cloud-resource-manager-1.18.0 google-cloud-storage-3.14.1 google-crc32c-1.8.0 google-genai-1.46.0
 google-resumable-media-2.10.2 googleapis-common-protos-1.75.3 grpc-google-iam-v1-0.14.5 grpcio-1.83.1
 grpcio-status-1.83.1 hf-xet-1.6.0 httpcore-1.0.9 httpcore2-2.12.0 httpx-0.28.1 httpx2-2.12.0
 huggingface-hub-1.31.0 importlib-metadata-9.0.1 jiter-0.16.0 jmespath-1.1.0 litellm-1.73.6.post1
 markdown-it-py-4.2.0 mdurl-0.1.2 num2words-0.5.14 openai-3.13.0 opentelemetry-api-1.44.0 proto-plus-1.28.4
 protobuf-6.33.6 pyasn1-0.6.4 pyasn1-modules-0.4.2 pycparser-3.0 pydantic-2.4.2 pydantic-core-2.10.1
 python-dotenv-1.2.3 regex-2026.9.10 rich-15.0.0 rsa-4.7.2 s3transfer-0.19.2 safetensors-0.8.0 seaborn-0.13.2
 shellingham-1.5.4 sniffio-1.3.1 tenacity-9.1.4 tiktoken-0.14.0 tokenizers-0.23.2 tqdm-4.70.1
 transformers-5.17.0 truststore-0.10.4 typer-0.27.2 websockets-15.0.1 zipp-4.1.0
```

</details>

### 벤치마크 실행과 요약 지표

실행 명령은 이렇다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ kubectl exec -it performance-test-runner -n performance-testing -- bash -c "
> cd /tmp/llmperf && \
> export OPENAI_API_KEY=EMPTY && \
> export OPENAI_API_BASE=$VLLM_URL && \
> python token_benchmark_ray.py \
>     --model 'tinyLlama/TinyLlama-1.1B-Chat-v1.0' \
>     --mean-input-tokens 256 \
>     --stddev-input-tokens 50 \
>     --mean-output-tokens 100 \
>     --stddev-output-tokens 20 \
>     --max-num-completed-requests 50 \
>     --timeout 600 \
>     --num-concurrent-requests 5 \
>     --results-dir 'result_outputs' \
>     --llm-api openai \
>     --additional-sampling-params '{\"temperature\": 0.7}'
> "
```

플래그를 읽는 방법은 이렇다.

| 플래그 | 값 | 의미 |
|---|---|---|
| `--mean-input-tokens` / `--stddev-input-tokens` | 256 / 50 | 요청마다 입력 목표 길이를 이 정규분포에서 새로 뽑는다 |
| `--mean-output-tokens` / `--stddev-output-tokens` | 100 / 20 | 요청마다 `max_tokens`를 이 정규분포에서 새로 뽑는다 |
| `--max-num-completed-requests` | 50 | 쏜 개수가 아니라 **응답까지 받은** 개수가 50이 되면 종료한다 |
| `--timeout` | 600 | 벤치마크 전체가 600초를 넘기면 강제 종료 |
| `--num-concurrent-requests` | 5 | in-flight 요청 수를 5로 유지한다. 하나 끝나면 바로 다음을 채운다 |
| `--llm-api` | `openai` | vLLM이 OpenAI 호환 API를 내므로 이 어댑터를 고른다 |
| `--results-dir` | `result_outputs` | 결과 JSON을 `/tmp/llmperf/result_outputs/`에 남긴다 |

`OPENAI_API_KEY=EMPTY`는 인증을 쓰지 않는 서버라도 클라이언트가 값을 요구하므로 넣는 더미다.

실행하면 토크나이저를 받고, Ray를 띄우고, 진행바를 돌린다.

```text
[transformers] PyTorch was not found. Models won't be available and only tokenizers, configuration and file/data utilities can be used.
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
tokenizer_config.json: 100%|████████████████████| 1.54k/1.54k [00:00<00:00, 6.73MB/s]
tokenizer.model: reconstructing file: 100%|██████|  500kB /  500kB, 49.6kB/s
tokenizer.json: 100%|███████████████████████████| 1.84M/1.84M [00:00<00:00, 96.3MB/s]
special_tokens_map.json: 100%|██████████████████| 411/411 [00:00<00:00, 2.75MB/s]
2026-09-11 17:36:10,895	WARNING services.py:2248 -- WARNING: The object store is using /tmp/ray instead of /dev/shm because /dev/shm has only 67108864 bytes available. This will harm performance! You may be able to free up space by deleting files in /dev/shm. If you are inside a Docker container, you can increase /dev/shm size by passing '--shm-size=1.18gb' to 'docker run' (or add it to the run_options list in a Ray cluster config). Make sure to set this to more than 30% of available RAM.
2026-09-11 17:36:12,015	INFO worker.py:2024 -- Started a local Ray instance.
100%|███████████████████████████████████████████| 50/50 [00:14<00:00,  3.37it/s]
```

**부하가 실제로 걸린 시간은 14초다.** 진행바의 `[00:14<00:00, 3.37it/s]`가 그것이고, 이 값이 뒤에서 대시보드 해석의 근거가 된다.

요약 출력에서 평균과 대표 백분위만 뽑으면 이렇다.

```text
inter_token_latency_s
    p50 = 0.011646842673179055
    p99 = 0.01633074445592667
    mean = 0.011929198805297702
ttft_s
    p50 = 0.24166843249986414
    p99 = 0.5874693769191432
    mean = 0.25382229144015583
end_to_end_latency_s
    p50 = 1.1816258570015634
    p99 = 1.595307278520304
    mean = 1.1840654935201018
request_output_throughput_token_per_s
    p50 = 85.85188762728757
    p99 = 100.37890278194183
    mean = 85.14205464367159
number_input_tokens
    p50 = 260.0
    mean = 259.78
number_output_tokens
    p50 = 98.0
    mean = 99.44
Number Of Errored Requests: 0
Overall Output Throughput: 335.40081105324157
Number Of Completed Requests: 50
Completed Requests Per Minute: 202.3737797988183
```

<details markdown="1">
<summary><b>1차 실행 요약 출력 전문</b></summary>

```text
\Results for token benchmark for tinyLlama/TinyLlama-1.1B-Chat-v1.0 queried with the openai api.

inter_token_latency_s
    p25 = 0.010734593266560559
    p50 = 0.011646842673179055
    p75 = 0.012783824410808785
    p90 = 0.014086878769863042
    p95 = 0.014920037618991189
    p99 = 0.01633074445592667
    mean = 0.011929198805297702
    min = 0.009936854961848393
    max = 0.016460548978624926
    stddev = 0.0016259885666846672
ttft_s
    p25 = 0.1198926682527599
    p50 = 0.24166843249986414
    p75 = 0.3657679822481441
    p90 = 0.4566385881018505
    p95 = 0.4921339287519004
    p99 = 0.5874693769191432
    mean = 0.25382229144015583
    min = 0.05319087899988517
    max = 0.6646659329999238
    stddev = 0.1465119196859053
end_to_end_latency_s
    p25 = 1.0490269097508644
    p50 = 1.1816258570015634
    p75 = 1.3501864862510047
    p90 = 1.5149360793981033
    p95 = 1.5539014966994726
    p99 = 1.595307278520304
    mean = 1.1840654935201018
    min = 0.6958902700025646
    max = 1.6141548109990254
    stddev = 0.22494242157600097
request_output_throughput_token_per_s
    p25 = 78.21846377874049
    p50 = 85.85188762728757
    p75 = 93.14675708796825
    p90 = 98.22231625194384
    p95 = 99.07860689922708
    p99 = 100.37890278194183
    mean = 85.14205464367159
    min = 60.7469997947286
    max = 100.62024035601551
    stddev = 10.538462015961171
number_input_tokens
    p25 = 230.75
    p50 = 260.0
    p75 = 281.25
    p90 = 326.7
    p95 = 353.44999999999993
    p99 = 406.72999999999996
    mean = 259.78
    min = 131
    max = 418
    stddev = 52.449116254884295
number_output_tokens
    p25 = 88.0
    p50 = 98.0
    p75 = 114.0
    p90 = 120.1
    p95 = 122.1
    p99 = 129.01999999999998
    mean = 99.44
    min = 62
    max = 130
    stddev = 15.865711970363341
Number Of Errored Requests: 0
Overall Output Throughput: 335.40081105324157
Number Of Completed Requests: 50
Completed Requests Per Minute: 202.3737797988183
```

</details>

같은 설정으로 한 번 더 돌리면 `Overall Output Throughput: 340.6702900640951`이 나온다. 1차 대비 1.6% 차이라 실행 간 편차 범위다. 플래그를 바꾼 대조가 아니므로 이 편에서는 1차를 주 사례로 쓴다.

### Ray object store 경고

실행 로그 중간에 붙은 경고 한 줄은 따로 읽어 둘 만하다.

```text
WARNING: The object store is using /tmp/ray instead of /dev/shm because /dev/shm has only 67108864 bytes available. This will harm performance!
```

`67108864`는 64 MiB다. 이 값이 어디서 왔는지가 먼저다. EC2 인스턴스나 호스트 설정이 아니라 **컨테이너 런타임의 기본값**이다. containerd의 CRI 구현이 샌드박스 `/dev/shm` 크기를 `defaultShmSize = int64(1024 * 1024 * 64)`로 잡아 두고 있고, 파드 스펙에서 따로 지정하지 않으면 그대로 적용된다. 즉 여기서 말하는 `/dev/shm`은 배스천의 것이 아니라 `performance-test-runner` 파드 안의 것이다.

Ray가 이 경고를 내는 이유는 plasma object store를 공유 메모리에 두려 하기 때문이다. 공간이 부족하면 디스크 기반 `/tmp/ray`로 떨어지고, 큰 객체를 actor 사이로 옮길 때 느려진다.

다만 **이 워크로드에서는 영향이 없다고 본다.** Ray는 태스크나 actor 메서드의 반환값이 `max_direct_call_object_size`(기본 100 KiB) 이하이면 plasma에 넣지 않고 응답 메시지에 인라인으로 실어 소유자의 인메모리 스토어에 둔다. llmperf actor가 주고받는 것은 요청 하나의 지표 딕셔너리와 생성된 텍스트 정도라 요청당 1~2 KB 수준이고, 임계값보다 두 자릿수 작다. 즉 요청을 주고받는 경로에 plasma가 끼지 않는다.

단정할 수 있는 범위는 여기까지다. `/dev/shm`을 키워 다시 돌린 대조 실험은 하지 않았으므로, 실제로 수치가 그대로인지는 확인하지 않았다.

경고가 제안하는 해결책도 이 환경에는 그대로 들어맞지 않는다. `docker run --shm-size=1.18gb`는 도커 런타임의 플래그이고, 쿠버네티스 파드에는 그런 필드가 없다. 파드에서 같은 효과를 내려면 `emptyDir`에 `medium: Memory`를 주고 `/dev/shm`에 마운트하는 방식이 알려져 있는데, 이번에 적용해 보지 않았으므로 **[미검증]**이다.

### 부하 이후의 대시보드 상태

Prometheus UI에서 `vllm:request_success_total`을 직접 조회하면 두 번의 부하가 계단 두 개로 남아 있다.

![Prometheus에서 조회한 vllm:request_success_total]({{site.url}}/assets/images/llmso-aws-workshop-vllm-request-total.png){: .align-center}

<center><sup>직접 캡처. Prometheus UI에서 vllm:request_success_total을 1시간 창으로 조회한 그래프다. finished_reason="length"와 finished_reason="stop" 두 계열이 17:30 부근에 각각 약 47과 약 22로 오르고, 17:36 부근에는 length 계열만 약 101까지 다시 오른다.</sup></center>

두 계열의 움직임이 갈린다. 17:30 부근의 기본 부하 테스트에서는 둘 다 올랐는데, 17:36 부근의 llmperf 벤치마크에서는 `length`만 47에서 101로 오르고 `stop`은 22에 그대로 있다. **llmperf가 보낸 50건이 전부 `length`로 끝났다**는 뜻이다.

llmperf가 요청마다 `max_tokens`를 지정하고, 프롬프트도 모델이 스스로 끝맺지 않도록 구성하기 때문에 생성이 EOS가 아니라 길이 상한에서 멈춘다. 반대로 기본 부하 테스트는 `max_tokens: 100`을 주긴 하지만 짧은 고정 프롬프트라 모델이 먼저 끝내는 응답이 섞인다. 그래서 `stop`이 함께 올랐다.

같은 시점의 Grafana 대시보드는 이렇다.

![llmperf 벤치마크 직후의 vLLM 대시보드]({{site.url}}/assets/images/llmso-aws-workshop-llmperf-benchmark-dashboard.png){: .align-center}

<center><sup>직접 캡처. llmperf 벤치마크 직후의 vLLM Inference Metrics 대시보드다. 조회 창이 Last 3 minutes이고 새로고침이 10s이며, 왼쪽 stat 패널에 101과 22 두 값, 그 오른쪽 두 패널은 0, KV Cache Usage는 0%, Total Prompt Tokens가 15156, Total Generated Tokens가 12438이다.</sup></center>

시계를 맞춰 보면 두 그림이 같은 사건을 가리킨다. 실행 로그의 타임스탬프가 `2026-09-11 17:36:10`(UTC)이고, Prometheus UI도 UTC로 그리므로 17:36 계단이 그것이다. Grafana는 KST로 표시하므로 같은 사건이 `02:36`에 찍힌다. 두 화면의 계단 위치가 정확히 아홉 시간 차이로 맞는다.

`Total Successful Requests` stat 패널의 두 칸이 101과 22인 것도 Prometheus 그래프의 두 계열 최종값 그대로다. [8.5.2편의 패널과 쿼리]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-05-02-Grafana-vLLM-Dashboard %}#패널과-쿼리)에서 짚은 대로 쿼리에 `sum()`이 없어 `finished_reason` 시리즈가 따로 표시되는데, 그 덕에 두 칸 중 한 칸만 움직이는 장면이 그대로 보인다. `sum()`이 붙어 있었다면 123 하나로 합쳐져 `length`만 늘었다는 사실이 화면에서 사라졌을 것이다.

여기서도 게이지 셋은 0이다. 부하가 방금 끝난 직후인데 Running도 Waiting도 0이고 KV Cache Usage도 0%다. 이 중 `KV Cache Usage`는 [8.5.2편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-05-02-Grafana-vLLM-Dashboard %})에서 정리한 대로 Neuron에서 동시 시퀀스 슬롯 네 칸 중 몇 칸이 찼는지를 재므로 0·25·50·75·100%로만 움직인다. 이 패널이 가질 수 있는 값 자체가 다섯 개다.

두 대시보드 캡처를 나란히 볼 때 주의할 점이 하나 있다. 조회 창이 다르다 — 기본 부하 테스트 쪽은 `02:19`부터 `02:33`까지 약 14분 창이고, llmperf 쪽은 `Last 3 minutes`다. llmperf 쪽 그래프의 기울기가 완만해 보이는 것은 부하가 느슨해서가 아니라 가로축이 다섯 배 가까이 확대돼 있기 때문이다.

<br>

# 검증: 측정값 해석과 대시보드 대조

## 요약 출력과 원본 JSON 대조

llmperf는 화면에 찍는 요약과 별개로 결과 파일 두 개를 남긴다. 요청별 기록을 담은 개별 응답 배열과, 백분위·평균을 계산해 둔 summary JSON이다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ kubectl exec -it performance-test-runner -n performance-testing -- find /tmp/llmperf/result_outputs -name "*.json" -exec cat {} \;
```

개별 응답은 이런 레코드가 요청 수만큼 이어진 배열이다.

```json
{
    "error_code": null,
    "error_msg": "",
    "inter_token_latency_s": 0.010063429028516459,
    "ttft_s": 0.05724931800068589,
    "end_to_end_latency_s": 1.05680307700095,
    "request_output_throughput_token_per_s": 99.3562587818862,
    "number_total_tokens": 357,
    "number_output_tokens": 105,
    "number_input_tokens": 252
},
{
    "error_code": null,
    "error_msg": "",
    "inter_token_latency_s": 0.011119221556918532,
    "ttft_s": 0.16580839300877415,
    "end_to_end_latency_s": 1.078680176011403,
    "request_output_throughput_token_per_s": 89.92470813607923,
    "number_total_tokens": 367,
    "number_output_tokens": 97,
    "number_input_tokens": 270
}
```

`number_total_tokens`가 입력과 출력의 합이라는 것도 여기서 확인된다. 첫 레코드가 `252 + 105 = 357`이다.

summary JSON과 화면 요약을 대조하면 값이 소수점 15자리까지 전부 같다. `results_ttft_s_mean`이 `0.25382229144015583`, `results_end_to_end_latency_s_mean`이 `1.1840654935201018`, `results_mean_output_throughput_token_per_s`가 `335.40081105324157`로 화면에 찍힌 값 그대로다. 불일치는 한 건도 없다. 화면 요약은 JSON을 다시 계산한 것이 아니라 같은 값을 포맷만 바꿔 출력한 것으로 읽힌다.

순서에 대한 주의가 하나 있다. 이 `find -exec cat` 덤프는 두 번째 실행이 아니라 **첫 번째 실행의 결과 파일**이다. summary JSON의 `results_mean_output_throughput_token_per_s`가 `335.40081105324157`로 1차 요약값과 같기 때문이다. 기록에 붙은 순서가 실행 순서와 어긋난 것이므로, 아래 값은 전부 1차 것으로 읽어야 한다.

<details markdown="1">
<summary><b>summary JSON 전문</b></summary>

```json
{
    "version": "2023-08-31",
    "name": "tinyLlama-TinyLlama-1-1B-Chat-v1-0_256_100_summary",
    "model": "tinyLlama/TinyLlama-1.1B-Chat-v1.0",
    "mean_input_tokens": 256,
    "stddev_input_tokens": 50,
    "mean_output_tokens": 100,
    "stddev_output_tokens": 20,
    "num_concurrent_requests": 5,
    "additional_sampling_params_temperature": 0.7,
    "results_inter_token_latency_s_quantiles_p25": 0.010734593266560559,
    "results_inter_token_latency_s_quantiles_p50": 0.011646842673179055,
    "results_inter_token_latency_s_quantiles_p75": 0.012783824410808785,
    "results_inter_token_latency_s_quantiles_p90": 0.014086878769863042,
    "results_inter_token_latency_s_quantiles_p95": 0.014920037618991189,
    "results_inter_token_latency_s_quantiles_p99": 0.01633074445592667,
    "results_inter_token_latency_s_mean": 0.011929198805297702,
    "results_inter_token_latency_s_min": 0.009936854961848393,
    "results_inter_token_latency_s_max": 0.016460548978624926,
    "results_inter_token_latency_s_stddev": 0.0016259885666846672,
    "results_ttft_s_quantiles_p25": 0.1198926682527599,
    "results_ttft_s_quantiles_p50": 0.24166843249986414,
    "results_ttft_s_quantiles_p75": 0.3657679822481441,
    "results_ttft_s_quantiles_p90": 0.4566385881018505,
    "results_ttft_s_quantiles_p95": 0.4921339287519004,
    "results_ttft_s_quantiles_p99": 0.5874693769191432,
    "results_ttft_s_mean": 0.25382229144015583,
    "results_ttft_s_min": 0.05319087899988517,
    "results_ttft_s_max": 0.6646659329999238,
    "results_ttft_s_stddev": 0.1465119196859053,
    "results_end_to_end_latency_s_quantiles_p25": 1.0490269097508644,
    "results_end_to_end_latency_s_quantiles_p50": 1.1816258570015634,
    "results_end_to_end_latency_s_quantiles_p75": 1.3501864862510047,
    "results_end_to_end_latency_s_quantiles_p90": 1.5149360793981033,
    "results_end_to_end_latency_s_quantiles_p95": 1.5539014966994726,
    "results_end_to_end_latency_s_quantiles_p99": 1.595307278520304,
    "results_end_to_end_latency_s_mean": 1.1840654935201018,
    "results_end_to_end_latency_s_min": 0.6958902700025646,
    "results_end_to_end_latency_s_max": 1.6141548109990254,
    "results_end_to_end_latency_s_stddev": 0.22494242157600097,
    "results_request_output_throughput_token_per_s_quantiles_p25": 78.21846377874049,
    "results_request_output_throughput_token_per_s_quantiles_p50": 85.85188762728757,
    "results_request_output_throughput_token_per_s_quantiles_p75": 93.14675708796825,
    "results_request_output_throughput_token_per_s_quantiles_p90": 98.22231625194384,
    "results_request_output_throughput_token_per_s_quantiles_p95": 99.07860689922708,
    "results_request_output_throughput_token_per_s_quantiles_p99": 100.37890278194183,
    "results_request_output_throughput_token_per_s_mean": 85.14205464367159,
    "results_request_output_throughput_token_per_s_min": 60.7469997947286,
    "results_request_output_throughput_token_per_s_max": 100.62024035601551,
    "results_request_output_throughput_token_per_s_stddev": 10.538462015961171,
    "results_number_input_tokens_quantiles_p25": 230.75,
    "results_number_input_tokens_quantiles_p50": 260.0,
    "results_number_input_tokens_quantiles_p75": 281.25,
    "results_number_input_tokens_quantiles_p90": 326.7,
    "results_number_input_tokens_quantiles_p95": 353.44999999999993,
    "results_number_input_tokens_quantiles_p99": 406.72999999999996,
    "results_number_input_tokens_mean": 259.78,
    "results_number_input_tokens_min": "131",
    "results_number_input_tokens_max": "418",
    "results_number_input_tokens_stddev": 52.449116254884295,
    "results_number_output_tokens_quantiles_p25": 88.0,
    "results_number_output_tokens_quantiles_p50": 98.0,
    "results_number_output_tokens_quantiles_p75": 114.0,
    "results_number_output_tokens_quantiles_p90": 120.1,
    "results_number_output_tokens_quantiles_p95": 122.1,
    "results_number_output_tokens_quantiles_p99": 129.01999999999998,
    "results_number_output_tokens_mean": 99.44,
    "results_number_output_tokens_min": "62",
    "results_number_output_tokens_max": "130",
    "results_number_output_tokens_stddev": 15.865711970363341,
    "results_num_requests_started": 50,
    "results_error_rate": 0.0,
    "results_number_errors": 0,
    "results_error_code_frequency": "{}",
    "results_mean_output_throughput_token_per_s": 335.40081105324157,
    "results_num_completed_requests": 50,
    "results_num_completed_requests_per_min": 202.3737797988183,
    "timestamp": 1789148187
}
```

</details>

## 클라이언트 측 in-flight와 서버 측 대기열

요약 지표를 두 방향으로 나눠 보면 같은 숫자가 나온다.

- 전체 처리량 ÷ 요청당 처리량 = `335.40 / 85.14 = 3.94`
- Little's Law로 계산한 평균 in-flight 요청 수 = `3.37 req/s × 1.184초 = 3.99`

동시성을 5로 지정했는데 실효값이 4 부근에 잡힌 것이다. [8.3.1편의 neuron_config.json에 확정된 값]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-03-01-vLLM-Deployment %}#neuron_configjson에-확정된-값)에서 확인한 `MAX_NUM_SEQS: "4"`와 `pa_num_blocks: 4`, 그리고 기동 로그의 `Maximum concurrency for 1024 tokens per request: 4.00x`가 마침 같은 4다. 그래서 "서버의 배치 상한이 병목"이라는 결론이 바로 나올 것 같지만, **이 산술만으로는 그 결론이 서지 않는다.**

Little's Law의 L이 무엇을 세는지가 문제다. `L = λ × W`에서 W로 넣은 값은 `end_to_end_latency_s`이고, 이 값은 클라이언트가 요청을 보낸 시점부터 스트림이 끝날 때까지의 시간이다. 서버가 다섯 번째 요청을 큐에 세워 두고 있어도, 그 요청은 클라이언트 입장에서 여전히 응답을 기다리는 **in-flight** 상태라 W에 포함된다. 즉 여기서 계산되는 L은 클라이언트 측 in-flight 요청 수이지 서버가 동시에 처리하는 시퀀스 수가 아니다.

이 구분이 결론을 뒤집는다. 서버의 배치 상한 4가 병목이었다면 클라이언트 측 in-flight는 지정한 값인 **5에 가까워야 한다.** 네 개는 돌고 하나는 큐에서 대기하더라도 클라이언트에게는 다섯 개 모두 대기 중이기 때문이다. 실측 L이 3.94라는 것은 오히려 **클라이언트가 다섯 개를 계속 채워 넣지 못했다**는 쪽을 가리킨다.

클라이언트 쪽에 그럴 만한 이유가 있다. 러너 파드의 CPU 상한이 2코어인데, 그 안에서 파이썬 스레드 다섯 개와 Ray actor 프로세스 다섯 개, 그리고 raylet이 함께 돈다. 요청 하나가 끝나고 다음 요청을 만들어 보내기까지의 클라이언트 측 처리에 지연이 끼면 in-flight가 5를 채우지 못한다.

두 가설을 가르는 것은 서버 측 게이지다.

| 관측 | 판정 |
|---|---|
| `vllm:num_requests_running`이 4에 붙어 있고 `vllm:num_requests_waiting > 0` | 서버 병목. 배치 상한이 큐를 만들고 있다 |
| `vllm:num_requests_running`이 3~4에서 오르내리고 `vllm:num_requests_waiting = 0` | 클라이언트 병목. 서버는 슬롯이 남는데 요청이 안 들어온다 |

두 메트릭 모두 [8.5.1편의 수집 대상 /metrics]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-05-01-Prometheus-Metrics-Scrape %}#수집-대상-metrics)에서 확인한 대로 vLLM이 이미 내보내고 있고, 대시보드에도 패널이 있다. 그런데 캡처에 찍힌 값은 둘 다 0이다. 부하가 도는 동안의 값이 남아 있지 않아 이번 데이터로는 판정할 수 없다. 왜 남지 않았는지가 다음 절이다.

## 부하 지속 시간과 스크레이프 간격

대시보드에서 눈에 걸린 것이 셋이었다. 게이지가 0이고, counter 그래프가 안 내려오고, stat 패널이 두 칸이다. 셋 다 같은 자리에서 설명된다.

**부하가 스크레이프 간격에 비해 짧다.** [8.5.1편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-05-01-Prometheus-Metrics-Scrape %})에서 vLLM 잡의 `scrape_interval`을 전역 15초를 덮어 10초로 내려 뒀는데, llmperf 부하는 진행바에 찍힌 대로 14초다. 10초 간격으로 긁으면 부하 구간에 걸리는 표본이 **한두 개**다. 기본 부하 테스트는 더 짧다. 월클록이 출력에 없어 정확한 값은 알 수 없지만, 지연 시간 총합 28.0초를 유효 동시성 4~5로 나누면 5.6~7초 정도로 추정된다(**[미검증]** — 스크립트가 경과 시간을 찍지 않아 확인할 수단이 없다). 그렇다면 표본이 한 개 잡힐까 말까다.

**게이지는 캡처 시점에 이미 0으로 돌아와 있다.** `vllm:num_requests_running`과 `vllm:num_requests_waiting`, `vllm:gpu_cache_usage_perc`는 스크레이프 순간의 상태를 그대로 찍는 순간값이다. 부하가 끝나면 즉시 0이 되고, stat 패널은 창의 마지막 값을 보여주므로 0이 나온다. 두 패널의 스파크라인에 남은 뾰족한 자국이 부하 구간에 잡힌 그 한두 개 표본이다. 짧은 부하를 10초 간격으로 긁으면 이렇게 보인다. 부하를 실제로 걸면 이 패널들이 움직이는지 [8.5.2편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-05-02-Grafana-vLLM-Dashboard %})이 다음 편으로 넘겨 둔 물음의 답이 이것이다. 움직이기는 하는데, 이 해상도에서는 스파이크 한 점으로만 남는다.

**counter는 내려오지 않는 것이 정상이다.** `vllm:request_success_total`과 토큰 계열은 단조 증가하는 누적값이라 한 번 오르면 그 높이에 머문다. `Request Success Over Time`과 `Token Generation Over Time`이 계단 모양으로 올라 평평해진 것은 부하가 계속되고 있어서가 아니라 counter를 원시값 그대로 그렸기 때문이다. 변화율을 보려면 `rate()`를 씌워야 한다. 8.5.2편이 "누적값도 요청 9건분이라 15분 창에서 평평하다"고 적은 것과 같은 성질의 반대편이다. 그때는 올라간 적이 없어서 평평했고, 지금은 올라간 뒤라 평평하다.

**`sum()`이 없어 두 칸으로 나뉜다.** `vllm:request_success_total`은 `finished_reason` 라벨로 시리즈가 둘인데, [8.5.2편의 패널과 쿼리]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-05-02-Grafana-vLLM-Dashboard %}#패널과-쿼리)의 대시보드 JSON은 stat 패널과 시계열 패널 **양쪽 다** `sum()`을 걸지 않았다. 이번에는 그 덕에 llmperf 요청이 전부 `length`로 끝났다는 사실이 화면에 그대로 드러났지만, 총 성공 건수를 한 숫자로 읽으려던 패널로서는 의도한 동작이 아니다.

이 창 문제를 피하려면 부하를 스크레이프 간격보다 충분히 길게 끌거나 스크레이프 간격을 내려야 하는데, 어느 쪽도 이번에 시도하지 않았다.

## 두 도구 수치의 비교 가능성

결론부터 적으면 **두 도구의 처리량 수치는 나란히 놓을 수 없다.** 기본 부하 테스트의 `Tokens per Second: 54.1`과 llmperf의 `Overall Output Throughput: 335.40`을 비교해 "6배 빨라졌다"고 읽고 싶어지지만, 두 숫자가 재는 대상이 세 층위에서 다르다.

**분모가 다르다.** 기본 부하 테스트는 `sum(latencies)`로 나눈다. 요청 30건의 지연 시간을 전부 더한 값이므로 병렬로 돌아 실제 경과 시간이 줄어도 이 합은 줄지 않는다. llmperf의 `Overall Output Throughput`은 벤치마크 전체의 월클록 경과 시간으로 나눈다. 앞쪽은 순차 환산값, 뒤쪽은 실제 처리량이다.

**분자가 다르다.** 기본 부하 테스트의 "tokens"는 `text.split()`으로 센 공백 분할 단어 수다. llmperf의 `number_output_tokens`는 Llama 토크나이저로 센 토큰 수다. 같은 응답을 재도 후자가 두 배 가까이 크게 나온다.

**워크로드가 다르다.** 기본 부하 테스트는 짧은 고정 프롬프트에 `max_tokens: 100`이고 비스트리밍 `/completions`를 친다. llmperf는 입력 256±50 / 출력 100±20을 요청마다 새로 뽑고 스트리밍 `/chat/completions`를 친다. 출력 길이는 양쪽이 100토큰 부근으로 비슷하지만, 입력은 열 토큰 남짓한 고정 문장과 256토큰 부근의 샘플링된 프롬프트로 자릿수가 다르다. 프리필에 드는 비용이 서로 다른 워크로드다.

동시성도 같은 값이었다는 점을 짚어 둘 필요가 있다. 기본 부하 테스트는 `basic_load_test.py $VLLM_URL 30 5`로 워커 5개, llmperf도 `--num-concurrent-requests 5`다. 양쪽 다 클라이언트 동시 5이므로 "순차 대 병렬"의 대비가 아니다.

그래서 두 수치의 격차를 continuous batching의 효과로 읽을 수 없다. 배치 효과를 실제로 재려면 다른 조건은 그대로 두고 llmperf의 `--num-concurrent-requests`만 1과 5로 바꿔 돌린 대조가 필요한데, 그 실험은 하지 않았다. 모니터링 리소스를 정리한 뒤에야 이 점을 확인해서, 다시 돌릴 환경이 남아 있지 않았다.

## 디코드 스텝 속도와 HBM 대역폭

요약 출력의 `inter_token_latency_s`를 디코드 스텝 시간으로 그냥 읽으면 안 된다. llmperf 소스에서 이 값은 `end_to_end_latency_s`를 출력 토큰 수로 나눈 값이라 **TTFT가 섞여 있다.** 프리필에 쓴 시간을 출력 토큰 전체에 골고루 흩뿌린 셈이다.

같은 이유로, 요청당 처리량 85.14 tok/s와 ITL 역수 84가 비슷하다는 것도 교차 검증이 아니다. `request_output_throughput`이 정확히 `출력토큰수 / E2E`이고 ITL이 `E2E / 출력토큰수`이므로, 두 값은 같은 양을 뒤집은 값이다. 서로를 확인해 주지 못한다.

TTFT를 빼고 계산하면 스텝 시간이 이렇게 나온다.

```text
디코드 구간  = E2E mean - TTFT mean = 1.1841 - 0.2538 = 0.9303 s
스텝당 시간  = 0.9303 / 99.44 = 0.00935 s = 9.35 ms
스텝 속도    = 1 / 0.00935 = 약 107 steps/s
```

디코딩은 스텝마다 가중치 전체를 HBM에서 한 번 읽는 메모리 대역폭 바운드 연산이다. TinyLlama 1.1B를 BF16으로 올리면 약 2.2 GB이므로 소비 대역폭은 이렇게 추정된다.

```text
2.2 GB × 107 steps/s = 약 235 GB/s
Trainium 칩 HBM 대역폭 820 GiB/s (= 약 880 GB/s) 대비 약 27%
```

대역폭이 70% 넘게 남아 있다는 뜻이다. 디코드는 원리상 대역폭에 먼저 걸리는 연산인데 실측 소비가 27%에 그쳤다는 것은, 이 구성에서 스텝 속도를 묶고 있는 것이 대역폭이 아니라는 뜻이 된다. 그렇다면 스텝 한 번에 처리하는 시퀀스 수를 늘려 같은 대역폭으로 더 많은 토큰을 낼 여지가 있다. 작은 모델에서 이런 그림이 나오는 이유는 가중치 스트리밍보다 스텝당 고정 오버헤드가 커서다. [8.3.1편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-03-01-vLLM-Deployment %})에서 확인한 대로 `enable_bucketing: false`에 `seq_len: 1024`라 어텐션이 항상 1024 길이로 계산되고, 커널 디스패치 비용도 매 스텝 붙는다.

다만 이것도 클라이언트 측 값으로 서버 내부를 추정한 것이다. 서버 측 정답에 해당하는 것은 vLLM이 이미 내보내고 있는 `vllm:time_per_output_token_seconds` 히스토그램이다. 이 값은 프리필을 빼고 디코드 스텝만 재므로, 위 계산이 맞는지 직접 대조할 수 있다. [8.5.2편의 패널과 쿼리]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-05-02-Grafana-vLLM-Dashboard %}#패널과-쿼리)에 이 패널이 없어 이번에는 조회하지 않았다.

## 출력 토큰 100만 개당 비용

절댓값 335.4 tok/s만으로는 잘 나온 수치인지 판단할 수 없다. 추론 서빙에서 비교 가능한 단위로 흔히 쓰는 것이 출력 토큰 100만 개당 비용이다.

```text
시간당 출력 토큰  = 335.4 tok/s × 3600 = 1,207,440 tokens/hour
trn1.2xlarge 온디맨드 (us-west-2) = $1.34/hr
100만 토큰당      = 1.34 / 1.20744 = 약 $1.11 / 1M output tokens
```

단가는 2026년 9월 us-west-2 온디맨드(Linux, 공유 테넌시) 기준 `$1.34375/hr`을 반올림한 값이다. 리전과 시점에 따라 바뀌므로 다시 계산할 때는 조회 시점의 값을 쓰는 편이 맞다.

이 숫자에 붙는 한정이 둘이다.

첫째, **인스턴스 요금만 센 값이다.** EKS 컨트롤 플레인, CLB 두 대, S3 모델 캐시, 워크샵 배스천 인스턴스가 전부 빠져 있다. 실제로 무엇이 계속 과금되는지는 [남아 있는 자원](#남아-있는-자원)에 정리한다.

둘째, **부하가 14초짜리 벤치마크에서 나온 값이다.** 실제 서비스는 트래픽이 들쭉날쭉하고 유휴 구간에도 인스턴스 요금이 붙으므로, 이 수치는 서버가 계속 포화 상태일 때의 하한에 가깝다. 앞에서 본 대로 이 실행이 실제로 서버를 포화시켰는지도 게이지 없이는 확정할 수 없다.

<br>

# 삭제 범위와 남는 자원

## 정리 명령이 지우는 범위

워크샵이 마지막에 실행하는 정리는 한 줄이다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ echo "Cleaning up performance testing resources..."
Cleaning up performance testing resources...

# 네임스페이스 하나만 지운다
ubuntu@ip-10-0-1-100:~/workshop$ kubectl delete namespace performance-testing
namespace "performance-testing" deleted
```

이 명령의 범위는 `performance-testing` 네임스페이스와 그 안의 것들까지다. 구체적으로는 `performance-test-runner` 파드, 그 안에 깔았던 패키지들, 그리고 `emptyDir`에 들어 있던 것 전부다. `emptyDir`에는 llmperf 클론과 `result_outputs/`의 결과 JSON이 함께 들어 있으므로 **벤치마크 원본 데이터도 이때 사라진다.** 결과를 남기려면 삭제 전에 `kubectl cp`로 빼 두거나 배스천으로 옮겨야 한다.

vLLM 서빙과 모니터링 스택은 다른 네임스페이스에 있으므로 이 명령에 영향을 받지 않는다.

## 남아 있는 자원

정리 후에도 계속 살아 있는 것과 함께 사라지는 것을 나누면 이렇다.

| 자원 | 상태 | 비고 |
|---|---|---|
| `neuron-trn1-2x` 노드그룹 (`trn1.2xlarge`) | 남는다 | 시간당 과금이 계속된다. 비용의 대부분 |
| EKS 컨트롤 플레인 | 남는다 | 클러스터 단위 시간당 요금 |
| `vllm-service` CLB | 남는다 | [8.3.2편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-03-02-Service-LoadBalancer %})에서 만든 것 |
| `ingress-nginx-controller` CLB | 남는다 | [8.4편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-04-Ingress-Nginx-Routing %})에서 차트가 만든 것. CLB가 두 대다 |
| S3 모델 캐시 버킷 | 남는다 | 컴파일 산출물이 들어 있다 |
| 워크샵 인스턴스 (`t3.2xlarge`) | 남는다 | 배스천 |
| Prometheus / Grafana 시계열과 대시보드 | 남는다 (파드가 교체되면 사라진다) | 이 정리 명령의 대상이 아니다. PV를 비활성으로 설치해 EBS 볼륨이 따로 없다 |

마지막 줄은 [8.5.1편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-05-01-Prometheus-Metrics-Scrape %})과 [8.5.2편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-05-02-Grafana-vLLM-Dashboard %})에서 설치 시 나온 `WARNING: Persistence is disabled!!!`가 가리키던 그것이다. 이번 부하로 쌓인 시계열도 `prometheus-server` 파드가 교체되면 함께 없어진다.

이 편에서 확인한 것은 위 한 줄짜리 명령이 어디까지 지우는지까지다. 전체 실습 환경을 어떤 순서로 내려야 하는지는 실제로 해 보지 않았으므로 이 글에서 다루는 범위 밖이다.

<br>

# 정리

| 질문 | 답 |
|---|---|
| Lab 5가 클러스터에 만드는 것은 | `performance-testing` 네임스페이스와 러너 파드 하나뿐이다. Deployment도 Job도 Service도 없다 |
| 깔린 패키지를 다 쓰나 | 아니다. 스크립트가 쓰는 서드파티는 `requests` 하나다. locust는 locustfile이 없어 돌지 않고, PyPI `asyncio`는 코드가 없는 폐기 패키지다 |
| `Tokens per Second: 54.1`이 서버 처리량인가 | 아니다. 분모가 지연 시간의 합이라 동시성을 올려도 오르지 않는다. 분자도 토큰이 아니라 공백 분할 단어 수다 |
| P99가 Max와 같은 이유 | 표본 30개에서 `int(30*0.99)`가 29라 정렬된 마지막 원소를 집는다. 표본 100개 미만이면 항상 최댓값이다 |
| 두 도구가 같은 엔드포인트를 치나 | 아니다. 자작 스크립트는 비스트리밍 `/completions`, llmperf는 스트리밍 `/chat/completions`다 |
| llmperf가 모델을 받나 | 아니다. 소스에 하드코딩된 `hf-internal-testing/llama-tokenizer`의 파일 네 개(약 2.4 MB)를 받는다. `torch`가 없어 가중치를 올릴 수단도 없다 |
| `--model` 값은 어디에 쓰이나 | 요청 body의 `model` 필드뿐이다. 토큰 계산에는 쓰이지 않는다 |
| "실제와 유사한 매개변수"의 실체 | 요청마다 입력 길이와 `max_tokens`를 가우시안에서 새로 뽑는 것이다. 도착 과정은 없는 폐루프라 큐 폭증은 재현되지 않는다 |
| 두 실행의 프롬프트가 같은 이유 | 소스에 `random.seed(11111)`이 하드코딩돼 있다. 두 실행의 입력 토큰 백분위가 소수점 끝까지 같다 |
| `/dev/shm` 64 MiB 경고는 어디서 오나 | containerd CRI의 샌드박스 기본값 `defaultShmSize`다. 파드 안 `/dev/shm`을 가리키고, 이 워크로드에서는 요청 경로에 plasma가 끼지 않아 영향이 없다고 본다 |
| 유효 동시성 3.94는 서버 병목의 증거인가 | 아니다. Little's Law의 L은 클라이언트 측 in-flight다. 서버 병목이면 오히려 5에 가까워야 한다. 판정에는 `vllm:num_requests_running`과 `vllm:num_requests_waiting`이 필요하다 |
| 두 도구의 처리량을 비교할 수 있나 | 없다. 분모·분자·워크로드가 모두 다르고, 동시성은 양쪽 다 5로 같았다. 배치 효과를 재려면 동시성만 바꾼 대조가 필요한데 하지 않았다 |
| 부하를 걸었는데 게이지가 왜 0인가 | 부하가 14초인데 스크레이프 간격이 10초라 표본이 한두 개고, 캡처 시점에는 이미 0으로 돌아와 있다. 스파크라인의 스파이크가 그 표본이다 |
| counter 그래프가 왜 안 내려오나 | 누적값을 원시 그대로 그렸기 때문이다. 변화율을 보려면 `rate()`가 필요하다 |
| llmperf 요청이 전부 `length`로 끝난 이유 | 요청마다 `max_tokens`가 지정돼 EOS가 아니라 길이 상한에서 멈춘다. `stop` 계열이 22에서 안 움직이는 것이 증거다 |
| ITL과 요청당 처리량이 맞아떨어지는 게 검증인가 | 아니다. 같은 양을 뒤집은 값이다. TTFT를 빼고 계산한 디코드 스텝은 약 107 steps/s다 |
| 출력 토큰 100만 개당 비용 | 인스턴스 요금만 세면 약 `$1.11`이다. 컨트롤 플레인·CLB 두 대·S3·배스천은 빠져 있다 |
| 정리 명령이 지우는 범위 | `performance-testing` 네임스페이스까지다. 노드그룹, 컨트롤 플레인, CLB 두 대, S3 버킷, 배스천은 그대로 남는다 |

8.5.2편이 다음 편으로 넘겨 둔 물음은 부하를 걸면 이 패널들이 실제로 움직이는가였다. 움직였다. 다만 확인된 방식이 예상과 달랐다. 게이지는 부하가 끝난 뒤의 캡처에 0으로 찍혔고, 부하의 흔적은 스파크라인의 스파이크와 counter 계단으로만 남았다. 14초짜리 부하를 10초 간격으로 긁는 조합에서는 이것이 정상 동작이다. 관측 스택을 세운 것과 그 스택으로 무언가를 판정할 수 있는 것 사이에 간격이 있고, 이번 데이터에서는 그 간격이 유효 동시성 3.94를 서버 병목으로 귀속시킬 수 없다는 형태로 드러났다.

수치 해석에서 얻은 것은 도구가 찍는 숫자의 이름과 그 산출식을 따로 봐야 한다는 쪽이다. `Tokens per Second`가 처리량이 아니고, `Average Tokens per Response`가 토큰 수가 아니고, P99가 백분위가 아니고, `inter_token_latency_s`가 디코드 스텝 시간이 아니었다. 네 경우 모두 산출식을 읽고서야 무엇을 재고 있는지 알 수 있었다.

남은 Lab은 CPU 사용률 기반 HPA다. 부하를 거는 쪽까지는 이 편에서 확인했고, 그 부하에 파드 수가 반응하는지는 [8.7편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-07-Scaling %})에서 다룬다. 다만 그 편에서 확인되는 것은 파드 수가 늘어나는 장면이 아니라 노드도 파드도 늘릴 수 없는 자원 제약 쪽이다. 이번 데이터로 판정하지 못한 `vllm:num_requests_running`과 `vllm:num_requests_waiting`도 부하 지속 시간을 스크레이프 간격보다 길게 잡아 다시 볼 대상이다. 뒤쪽 지표는 8.7편에서 CPU를 대신할 스케일 신호 후보로 다시 나온다.

<br>

# 참고 링크

- [llmperf (GitHub)](https://github.com/ray-project/llmperf)
- [llmperf: token_benchmark_ray.py](https://github.com/ray-project/llmperf/blob/main/token_benchmark_ray.py)
- [llmperf: src/llmperf/utils.py](https://github.com/ray-project/llmperf/blob/main/src/llmperf/utils.py)
- [llmperf: OpenAIChatCompletionsClient](https://github.com/ray-project/llmperf/blob/main/src/llmperf/ray_clients/openai_chat_completions_client.py)
- [llmperf: common_metrics.py](https://github.com/ray-project/llmperf/blob/main/src/llmperf/common_metrics.py)
- [Hugging Face: hf-internal-testing/llama-tokenizer](https://huggingface.co/hf-internal-testing/llama-tokenizer)
- [vLLM: Metrics 설계 문서](https://docs.vllm.ai/en/latest/design/metrics.html)
- [Ray: ray_config_def.h (GitHub)](https://github.com/ray-project/ray/blob/master/src/ray/common/ray_config_def.h)
- [containerd: CRI 샌드박스 기본 shm 크기 (GitHub)](https://github.com/containerd/containerd/blob/main/internal/cri/server/podsandbox/helpers_linux.go)
- [AWS Neuron: Trainium 아키텍처](https://awsdocs-neuron.readthedocs-hosted.com/en/latest/general/arch/neuron-hardware/trainium.html)
- [Amazon EC2 Trn1 인스턴스](https://aws.amazon.com/ec2/instance-types/trn1/)
- [Locust Documentation](https://docs.locust.io/)
- [PyPI: asyncio](https://pypi.org/project/asyncio/)
- [8.0편: 개요와 워크샵 아키텍처]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-00-EKS-Workshop-Overview %})
<br>
