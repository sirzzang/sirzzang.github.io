---
title: "[Nsight] Nsight 프로파일러: 3. nsys 수집과 리포트 읽기"
excerpt: "nsys로 무엇을 어떻게 수집하고, 뷰어에 뜬 리포트를 어느 순서로 읽어 병목을 판정하는지 정리해 보자."
categories:
  - Dev
toc: true
use_math: false
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - GPU
  - Nsight-Systems
  - Profiling
  - NVTX
  - PyTorch
  - Hands-On-LLM-Serving-and-Optimization-Study
  - Hands-On-LLM-Serving-and-Optimization-Study-Week-5
last_modified_at: 2026-09-05
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Hands-On LLM Serving and Optimization Study (LLMSO) 5주차 학습 중 딥다이브한 내용입니다.*

<br>

# TL;DR

- [1편]({% post_url 2026-09-03-Dev-Nsight-Profiling-01-Concepts %}#타임라인-읽기)에서 뜬 리포트는 전체 9.7초 중 GPU가 1초만 일했다. 이건 워크로드가 느린 것이 아니라 **측정 구간을 잘못 잡은 것**이다. 이 편은 거기서 출발한다
- 수집에서 먼저 정할 것은 셋이다. `--trace`로 무엇을 기록할지, `--capture-range`로 어느 구간을 뜰지, `--sample`·`--cpuctxsw`로 CPU 쪽을 켤지 끌지
- `--capture-range=cudaProfilerApi`만 붙이면 `--capture-range-end`가 기본값 `stop-shutdown`으로 남아 **대상 앱에 신호가 간다.** 서버를 감쌀 때는 `repeat`와 `--kill=none`을 함께 명시한다
- 리포트는 **타임라인에서 이상한 구간을 눈으로 찾고 아래 패널로 정량화**하는 순서로 읽는다. 반대로 가면 헤맨다
- GUI의 뷰와 CLI 리포트는 같은 엔진이다. Stats System View가 `nsys stats`, Expert System View가 `nsys analyze`다. 화면에서 찾은 것을 그대로 명령으로 옮겨 자동화할 수 있다
- 타임라인 읽기의 핵심 기술은 **CUDA API 행과 CUDA HW 행을 세로로 대조**하는 것이다. API 블록은 있는데 위 커널 행이 비어 있으면 런치 오버헤드이거나 동기화 대기다

<br>

# 배경

1편에서 Colab T4로 리포트를 하나 떠서 열어 봤다. 행 트리가 어떻게 생겼는지, 파란 막대가 GPU 연산이라는 것까지는 거기서 확인했다. 그런데 그 리포트를 조금 더 들여다보면 곧바로 걸리는 것이 있다.

**전체 9.7초 중 GPU가 실제로 일한 구간은 5.4초에서 6.5초 사이, 1초 남짓이다.** 시간을 갈라 보면 이렇게 나뉜다.

| 구간 | 길이 | 무엇 |
| --- | --- | --- |
| 0 ~ 5.4초 | 5.4초 (56%) | `import torch`와 CUDA 컨텍스트 초기화. CPU만 돈다 |
| 5.4 ~ 6.5초 | 1.1초 (11%) | 실제 GPU 연산 |
| 6.5 ~ 9.7초 | 3.2초 (33%) | **정체가 설명되지 않는 구간** |

앞의 절반이 임포트라는 것도 문제지만, 마지막 3.2초가 무엇인지 이 리포트만으로는 알 수 없다는 점이 더 걸린다. 파이썬 종료와 CUDA 컨텍스트 정리로 짐작할 뿐이고, 구간에 이름표가 없어 확인할 방법이 없다. 뒤에서 볼 NVTX가 필요해지는 이유가 여기서 이미 나온다.

이 리포트를 놓고 "GPU 사용률이 낮다"고 결론 내리면 틀린다. 워크로드가 느린 것이 아니라 **재는 구간을 잘못 잡은 것**이다. 그래서 **이 리포트의 수치는 워크로드의 성능을 말해 주지 못한다.** 커널 시간이든 사용률이든, 임포트와 정리 구간이 섞인 값이라 그대로 인용할 것이 못 된다.

수집 자체도 최소 구성이다. `-t cuda,nvtx,osrt`로 기본 트레이스만 켰고, 코드에 NVTX 주석이 없어 구간 이름표도 없다. GPU 카운터는 아예 안 켰다. 워크로드도 행렬 곱과 `relu`를 스무 번 도는 20줄짜리 스크립트라, 실제 학습이나 서빙에서 나오는 패턴과는 거리가 있다. **그러니 이 편의 어떤 숫자도 "이렇게 하면 빨라진다" 류의 결론으로 옮겨 쓸 것이 못 된다.** 실제 워크로드에 적용해 본 결과가 아니라, 도구가 무엇을 보여 주는지 확인해 본 기록이다.

그렇다고 버릴 리포트는 아니다. 수치를 성능 판정에 쓸 수 없다는 것과, 리포트를 읽는 방법을 익히는 데 쓸 수 없다는 것은 다른 이야기다. 오히려 **잘못 잡힌 리포트가 어떻게 생겼는지 알아 두는 편이** 다음번에 같은 실수를 걸러 내는 데 도움이 된다. 그래서 이 편은 두 갈래로 간다. 앞쪽은 구간을 제대로 잡고 필요한 것만 수집하는 방법, 뒤쪽은 그렇게 뜬 리포트를 어느 순서로 읽어 판정하는 방법이다. 뒤쪽에서 드는 예시는 이 리포트인데, **거기서 읽어 낼 것은 판정 자체가 아니라 판정에 이르는 절차**로 두고 본다.
<br>

# 수집

## 감싸서 실행

`nsys`가 하는 일은 대상 프로그램을 자기가 exec해서 그 프로세스와 자손 전체를 관측하는 것이다. 워크로드 코드를 고칠 필요가 없다.

```shell
# -t 는 짧은 옵션이라 값 앞에 공백, --force-overwrite 는 긴 옵션이라 등호
~# nsys profile -t cuda,nvtx,osrt -o /content/demo --force-overwrite=true python tiny.py
```

짧은 옵션과 긴 옵션의 표기가 다른 것은 문서가 명시한 규칙이다. 모든 옵션이 대소문자를 구분한다는 점도 같은 문단에 있다.

<details markdown="1">
<summary>돌리기 전에 — 어느 `nsys`가 뜨는가</summary>

노드에서 `nsys`를 쳤을 때 무엇이 실행되는지는 생각보다 불확실하다. 조사하면서 확인한 함정이 셋이다.

**하나, Ubuntu의 `apt install nvidia-cuda-toolkit`은 오래된 빌드를 끌어온다.** 이 패키지 자체에는 `nsys`도 `ncu`도 없고, Recommends로 배포판이 직접 빌드한 구버전을 딸려 온다(jammy는 2021.3.3.2, noble은 2022.4.2.50). 게다가 그렇게 깔린 `nsys`는 **PATH에 없다.** `/usr/bin`에 놓이는 것은 `nsight-sys`와 `nsys-ui`뿐이고 실행 파일은 `/usr/lib/nsight-systems/bin/nsys`에 들어간다. 2021.3 빌드는 `.nsys-rep` 포맷(2021.4 도입) 이전이라 `.qdrep`을 쓴다.

**둘, Colab에는 `nsight-systems` 패키지가 없다.** GPU 런타임 이미지의 apt 목록에 해당 항목이 아예 없고 `nsight-compute`만 있다. 그런데 `nsys`는 발견되는데, Nsight Compute 패키지가 자기 System Trace 기능을 위해 Nsight Systems 타깃 트리를 통째로 품고 있기 때문이다.

```shell
# Colab GPU 런타임. 번들된 nsys 를 PATH 에 추가한 뒤 확인
~# export PATH=$PATH:/opt/nvidia/nsight-compute/2025.1.1/host/target-linux-x64
~# nsys --version

# 실행 결과
NVIDIA Nsight Systems version 2025.1.1.0
```

**셋, CUDA Toolkit 래퍼는 `nsys`와 `ncu`를 다르게 다룬다.** `/usr/local/cuda-*/bin/nsys`는 짧은 셸 스크립트인데 특정 `nsight-systems-*` 디렉터리를 찾아 exec하고 없으면 죽는다. 즉 **CUDA 버전에 고정된다.** 반면 같은 위치의 `ncu` 래퍼는 `/opt/nvidia/nsight-compute/*`를 훑어 가장 높은 버전을 exec한다. `/usr/local/bin/nsys`는 또 다른데, 두 .deb 계열 모두 postinst에서 우선순위 0으로 `update-alternatives`를 부르기 때문에 버전과 무관하게 **마지막에 설치한 쪽이 링크를 가져간다.**

결론은 단순하다. 프로파일링 전에 `nsys --version`부터 찍어 본다.

</details>

## 무엇을 트레이스할지

`--trace`는 어떤 API 계층을 전수 기록할지 고르는 옵션이다. 아무 플래그 없이 돌리면 기본값으로 `cuda`, `opengl`, `nvtx`, `osrt` 넷을 트레이싱하고 CPU IP 샘플링과 스레드 스케줄링까지 함께 수집한다. GPU 워크로드만 볼 때 `opengl`은 쓸 일이 없으므로 보통 `-t cuda,nvtx,osrt` 정도로 좁힌다.

<details markdown="1">
<summary>알아 둘 값 셋 — `cuda`, `nccl`, `osrt`</summary>

- **`cuda`의 의미가 Blackwell에서 바뀌었다.** 지원 GPU에서는 `cuda`가 CUDA 하드웨어 트레이스(HES)를 뜻하고, GPU를 나눠 쓰는 환경(MPS·MIG·vGPU)과 Confidential Compute에서는 기존 소프트웨어 트레이스를 `cuda-sw`로 강제해야 한다. 하드웨어 트레이스가 안 되면 자동으로 내려가고, 어느 쪽을 썼는지는 Diagnostics Summary에 적힌다
- **`nccl`은 `--trace` 값이다.** 2025.6.1에 들어온 플러그인 기반 고급 트레이스이고 NCCL 2.28 이상이 필요하며, 세부 항목은 `--nccl-trace`로 조정한다(기본 조합은 `api,ce-coll,group,gpu`). 그와 **별개로** libnccl 안의 NVTX 주석에 올라타는 legacy NCCL 트레이싱이 있고, 이건 `--trace=nvtx`만 켜도 동작한다. 고급 트레이스를 켜면 legacy는 자동으로 꺼진다
- **`osrt`는 libc 전수 트레이스가 아니다.** 오래 걸리거나 스레드를 CPU에서 내릴 수 있는 함수, 즉 시스템 콜 래퍼와 pthread 동기화 호출만 본다. `--osrt-threshold` 기본값 1000ns를 크게 낮추면 결과 파일이 극단적으로 커진다고 문서가 경고한다

</details>

## 구간 제한

배경에서 본 문제를 푸는 자리다. 애초에 긴 실행을 통째로 뜨는 것은 지원 범위 밖이기도 하다.

> Nsight Systems does not officially support runs longer than 5 minutes.
>
> — [Nsight Systems User Guide](https://docs.nvidia.com/nsight-systems/UserGuide/index.html)

구간을 자르는 수단은 둘이다. 시간으로 자르는 `--delay`(기본 0초)와 `--duration`, 그리고 코드 안의 API 호출로 자르는 `--capture-range`(`none` 기본, `cudaProfilerApi`, `hotkey`, `nvtx`)다. PyTorch에서는 `torch.cuda.profiler.start()`와 `stop()`이 cudart의 `cudaProfilerStart()`·`cudaProfilerStop()`을 그대로 감싼 함수라, `--capture-range=cudaProfilerApi`가 그 구간에 맞춰 붙는다.

임포트 구간을 건너뛰는 가장 간단한 방법은 `--delay`다. 다만 초기화 시간이 실행마다 달라지므로, 반복 가능한 측정을 하려면 코드에 구간을 여는 편이 확실하다.

**여기가 사고가 나는 지점이다.** `--capture-range-end`의 기본값은 `stop-shutdown`이고 `--kill`의 기본값은 `sigterm`이다. 즉 `--capture-range=cudaProfilerApi`만 붙여 놓으면 첫 `cudaProfilerStop`에서 수집이 끝나는 데 그치지 않고 세션이 내려가면서 대상 앱에 SIGTERM이 간다. 오프라인 벤치라면 어차피 끝날 프로세스라 티가 안 나지만, 장시간 서버를 감싼 경우에는 프로파일 한 번에 서버가 죽는다.

```shell
# vLLM 문서의 서버 프로파일링 레시피를 그대로 옮긴 것. --capture-range-end 가 핵심
# (원문이 등호 없이 쓰고 있어 표기를 바꾸지 않았다)
~$ nsys profile \
    --trace-fork-before-exec=true \
    --cuda-graph-trace=node \
    --capture-range=cudaProfilerApi \
    --capture-range-end repeat \
    vllm serve <model> --profiler-config.profiler cuda
# 이후 /start_profile · /stop_profile 엔드포인트로 구간을 연다
```

사고는 같은 문서의 오프라인 레시피를 서버에 옮길 때 난다. 오프라인 쪽에는 캡처 구간 옵션이 아예 없어서, 서버용으로 바꾸며 `--capture-range=cudaProfilerApi`만 덧붙이면 `--capture-range-end`가 기본값 그대로 남는다.

`--capture-range-end`가 받는 값은 셋이다. `stop`은 수집만 멈추고 앱을 살려 두되 이후 구간을 무시하고, `stop-shutdown`(기본)은 세션을 종료하며 `--kill` 신호를 보내고, `repeat[:N][:mode]`는 구간마다 수집을 반복한다.

문서 자체가 이 부분에서 일관되지 않다는 점은 짚어 둘 필요가 있다. 옵션 표는 `stop-shutdown`이 앱을 죽인다고 적는데, 같은 CLI 문서의 일반 주석은 `cudaProfilerStart`·`Stop`으로 구간을 제어하는 앱이 "`--kill`이 설정되지 않는 한 계속 실행된다"고 적는다. 직접 확인하지 않았으므로 단정하지 않는다. 다만 **서버를 감쌀 때 `--capture-range-end=repeat`와 `--kill=none`을 함께 명시하는 것은 어느 해석에서도 안전하다.**

## CPU와 카운터 수집

`--sample`은 CPU IP·백트레이스를 주기적으로 뜨는 옵션으로, `nsys`가 앱을 직접 띄우면 기본값이 `process-tree`다. 헷갈리는 부분은 `--cpuctxsw`인데, `--sample=none`으로 둬도 앱을 띄우는 경우 여전히 `process-tree`가 기본이다. **CPU 쪽 수집을 완전히 끄려면 둘 다 명시해야 한다.** 이 조합과 그때 잃는 것은 [2편]({% post_url 2026-09-03-Dev-Nsight-Profiling-02-Environments %}#권한-없이-수집하기)에서 권한과 함께 정리했다.

`--gpu-metrics-devices`는 GPU 하드웨어 카운터를 주기적으로 표본 추출하는 옵션이다. 기본값이 `none`이라 명시하지 않으면 켜지지 않고, 켜려면 Turing 이상에 상승된 권한이 필요하다. 결과에는 한계가 하나 있는데, 문서 표현으로 `it does not know which process or context is involved`, 즉 **프로세스 귀속이 안 되는 장치 수준 정보다.** 그리고 이 옵션만 [1편의 제약 ①]({% post_url 2026-09-03-Dev-Nsight-Profiling-01-Concepts %}#-카운터-배타성)에 걸린다. `dcgm-exporter`가 도는 노드에서는 `dcgmi profile --pause`로 멈춰 두고 끝나면 재개해야 한다.

<details markdown="1">
<summary>CUDA graph와 출력 파일 이름</summary>

`--cuda-graph-trace`는 CUDA graph를 어느 단위로 기록할지 고르는 옵션이다. 기본값 `graph` 단위에서는 그래프 실행 하나가 타임라인 항목 하나로 잡히고 **내부 커널은 보이지 않는다.** 개별 커널을 보려면 `node`가 필요한데, 문서 표현으로 `may cause significant runtime overhead`다.

이 선택은 텍스트 리포트에도 반영된다. `graph` 단위에서는 그래프로 재생된 커널이 `cuda_gpu_kern_sum`에 나타나지 않고, `cuda_api_sum`에는 수천 건의 `cudaLaunchKernel` 대신 `cudaGraphLaunch`가 찍힌다. vLLM 문서가 `--cuda-graph-trace=node`를 쓰는 것도 이 때문으로 보인다. 다만 문서가 이유를 밝히지는 않는다.

`-o`가 받는 치환 패턴은 넷뿐이다. `%q{ENV_VAR}`, `%h`(호스트명), `%p`(PID), `%%`. 여러 프로세스가 같은 리포트 파일에 동시에 쓰려 하면 에러가 나므로 다중 랭크에서는 치환이 사실상 필수다.

```shell
# 런처(mpirun) 앞이 아니라 애플리케이션 앞에 nsys 를 붙인다
~$ mpirun -np 4 nsys profile -o report-%q{OMPI_COMM_WORLD_RANK} ./my_app
# torchrun 이면 %q{RANK}, Slurm 이면 %q{SLURM_PROCID}, 안 되면 %p
```

</details>

## NVTX와 PyTorch 자동 주석

NVTX(NVIDIA Tools Extension)는 코드 구간에 이름을 붙여 프로파일러 타임라인에 표시되게 하는 주석 API다. 이게 없으면 타임라인에서 커널이 forward인지 backward인지 구분할 수 없다. 뒤에서 볼 이 리포트의 가장 큰 한계도 여기서 나온다.

직접 `torch.cuda.nvtx.range_push`와 `range_pop`을 넣어도 되지만, 2026.x `nsys`에는 코드를 고치지 않고 PyTorch 연산을 자동 주석 처리하는 `--pytorch` 옵션이 있다.

```shell
# PyTorch 워크로드에 흔히 쓰이는 조합. --delay 60 은 초기화 구간을 건너뛰기 위한 것
~$ nsys profile --trace=cuda,cudnn,cublas,osrt,nvtx \
    --pytorch=functions-trace-shapes,autograd-nvtx \
    --cudabacktrace=all --python-backtrace=cuda --python-sampling=true \
    --delay=60 python my_torch_script.py
```

값은 기본값 `none`을 빼면 `functions-trace`(forward·backward·step 등에 주석), `functions-trace-shapes`(거기에 텐서 shape 추가), `autograd-nvtx`, `autograd-shapes-nvtx` 넷이고, 전부 `--trace=nvtx`를 함의하며 앞의 둘은 상호 배타다.

주의할 것 둘. `--cudabacktrace`는 CPU 샘플링이 켜져 있어야 하고 문서가 `Significant runtime overhead`라고 적은 옵션이다. 그리고 `nsys` 아래에서는 Python stdout이 페이지 버퍼링되므로 `python -u`로 띄우는 편이 낫다.

## 오버헤드

<details markdown="1">
<summary>수집 옵션이 실행 시간에 미치는 영향</summary>

측정 자체가 워크로드를 느리게 만든다. 문서가 오버헤드가 크다고 명시한 옵션은 `--cudabacktrace`, `--cuda-graph-trace=node`, `--osrt-threshold`를 크게 낮추는 것, 그리고 `--capture-range=nvtx`의 전체 문자열 매칭이다.

실행 시간이 늘어나면 타임라인의 절대 시각도 함께 늘어나므로, 오버헤드가 큰 옵션을 켠 리포트와 안 켠 리포트의 숫자를 나란히 비교하면 안 된다. 그리고 타임라인의 회색 `Profiler overhead` 행이 도구 자신이 쓴 시간인데, 이 구간의 수치는 신뢰하지 않는 편이 낫다.

조합별 오버헤드를 실측해 표로 만드는 것은 아직 하지 않았다. 여기서는 문서가 경고한 옵션만 적어 둔다.

</details>

<br>

# 리포트 읽기

여기서부터가 뷰어에 뜬 리포트를 판정하는 부분이다. 원칙이 하나 있다.

**타임라인에서 이상한 구간을 눈으로 찾고, 아래 패널로 정량화한다.** 반대 순서로 가면 헤맨다. 통계부터 보면 어느 숫자가 이상한지 판단할 기준이 없기 때문이다.

## 세 패널

<details markdown="1">
<summary>뷰어 화면 구성 — Project Explorer와 뷰 전환 드롭다운</summary>

| 패널 | 역할 |
| --- | --- |
| 왼쪽 (Project Explorer) | 열어 둔 `.nsys-rep` 목록. 여러 개 열어 비교할 때만 의미가 있다 |
| 중앙 (Timeline View) | **시간축 위의 사실.** 무슨 일이 언제, 어느 리소스에서 일어났는가 |
| 아래 (뷰 전환 드롭다운) | 같은 데이터를 집계·통계·샘플링으로 다시 본 것 |

패널 구성 자체는 [1편의 타임라인 캡처]({% post_url 2026-09-03-Dev-Nsight-Profiling-01-Concepts %}#타임라인-읽기)에서 본 그대로다. 뷰 전환 드롭다운은 아래 캡처들의 왼쪽 위에 계속 보이는 그 목록이다.

드롭다운에 뜨는 항목은 Analysis Summary, Diagnostics Summary, Stats System View, Expert System View, Events View, 그리고 CPU 샘플링 세 뷰(Top-Down·Bottom-Up·Flat)다. 아래에서 하나씩 본다.

</details>

## 먼저 볼 것: Analysis Summary와 Diagnostics Summary

남이 준 리포트를 받았을 때 가장 먼저 볼 두 곳이다. **없는 데이터를 찾아 헤매지 않으려면 무엇을 수집했는지부터 확인해야 한다.**

<details markdown="1">
<summary>Analysis Summary — 무엇을 어떤 명령으로 수집했나</summary>

![Analysis Summary]({{site.url}}/assets/images/nsight-systems-analysis-summary.png){: .align-center}

<center><sup>직접 캡처. 실행 커맨드와 대상 GPU, 세션 길이가 한 화면에 나온다. 리포트 파일 경로에 로컬 사용자명이 들어간다</sup></center>

세션 길이가 `00:09.698`, 수집 명령이 `nsys profile -t cuda,nvtx,osrt -o /content/demo --force-overwrite=true python tiny.py`로 그대로 적혀 있고, 그 아래 Target 표에 GPU(Tesla T4), 드라이버(580.82.07), OS(Ubuntu 22.04.5 LTS), CPU까지 나온다. 여기서 `--trace`에 무엇이 들어갔는지 보면 그 리포트로 답할 수 있는 질문의 범위가 정해진다. 예컨대 `nvtx`가 없으면 구간별 집계는 애초에 불가능하다.

</details>

Diagnostics Summary는 수집 중 발생한 경고와 에러를 모아 둔 곳이다. 이 리포트에서는 둘이 중요하다.

![Diagnostics Summary]({{site.url}}/assets/images/nsight-systems-diagnostics-summary.png){: .align-center}

<center><sup>직접 캡처. 화면에는 경고가 다섯 줄 뜨는데, 그중 둘이 이 리포트의 해상도 한계를 그대로 말해 준다</sup></center>

- **`No NVTX events collected. Does the process use NVTX?`** — 코드에 NVTX 주석이 없다는 뜻이다. 그래서 타임라인의 커널이 forward인지 backward인지, 어느 step에 속하는지 알 수 없다. 분석 해상도가 여기서 크게 떨어진다
- **`Installed CUDA driver version (13.0) is not supported by this build of Nsight Systems. CUDA trace will be collected using libraries for driver version 12.8`** — 앞에서 본 대로 Colab의 `nsys`가 번들 구버전이라 생긴 경고다. 12.8용 [CUPTI]({% post_url 2026-09-03-Dev-Nsight-Profiling-01-Concepts %}#cupti)로 수집됐으므로 신규 API 트레이스가 빠질 수 있다

경고만 있는 것이 아니라 수집 조건도 여기 적힌다. 이 리포트에서는 `Event 'CPU Clock (sw)', with sampling period 2000000`이라 **CPU 샘플링 주기가 2ms**였고, 백트레이스 하나당 IP 샘플 4개를 모았으며, 최종적으로 IP 샘플 1,485개가 수집됐다. 뒤에서 볼 CPU 샘플링 뷰의 표본 1,481개는 그중 대상 프로세스 몫이고, 나머지 4개는 함께 잡힌 보조 프로세스 것이다.

## 타임라인 읽는 순서

행 계층은 위에서 아래로 **하드웨어 → 프로세스 → GPU → 스레드**다. 1편에서 행 트리가 어떻게 생겼는지는 봤으니, 여기서는 읽는 순서를 정리한다.

1. **CPU** — 코어별 사용률. 여기가 꽉 차 있는데 GPU가 비어 있으면 CPU 병목을 의심한다. 다만 최상단 CPU 행은 **시스템 전체**라 같은 기계의 다른 프로세스도 함께 잡힌다. Colab처럼 노트북 서버가 같이 도는 환경이면 이 행이 검다고 곧바로 내 워크로드의 CPU 병목이라 읽으면 안 되고, 아래 프로세스별 행과 대조해야 한다
2. **CUDA HW** — GPU가 실제로 무엇을 했는지. 가장 중요한 행이다. 커널 행의 **빈 구간(gap)을 찾는 것이 대부분의 답**이다
3. **Threads의 CUDA API 행** — CPU가 호출한 CUDA 런타임 API
4. **OS runtime libraries** — `pthread_cond_wait`, `read` 같은 블로킹 호출. 갭의 원인을 찾을 때 본다
5. **Profiler overhead** — 회색. 이 구간 수치는 신뢰하지 않는다

핵심 기술은 **2번과 3번을 세로로 대조하는 것**이다.

![CUDA API 행과 CUDA HW 행 대조]({{site.url}}/assets/images/nsight-systems-timeline-api-vs-hw.png){: .align-center}

<center><sup>직접 캡처. 6초 부근에서 cudaDeviceSynchronize 블록이 굵게 잡혀 있다</sup></center>

판정은 두 행의 **겹침 여부**로 갈린다.

- API 블록은 있는데 위의 커널 행이 **비어 있으면** 문제다. 런치 오버헤드이거나, GPU가 놀고 있는데 CPU가 무언가를 기다리는 상황이다
- API 블록과 커널 행이 **겹쳐 있으면** 정상이다. CPU가 GPU 작업이 끝나기를 기다리는 중이고, 그동안 GPU는 일하고 있다

이 리포트의 `cudaDeviceSynchronize`는 **뒤쪽**이다. 6초 부근에 굵게 잡혀 있지만 같은 구간의 커널 행도 함께 차 있다. `tiny.py` 마지막의 `torch.cuda.synchronize()`가 행렬 곱이 끝나기를 기다린 것이라, 이 블록 자체는 병목이 아니다. 굵은 API 블록을 보고 바로 병목이라 읽으면 안 되는 이유가 여기 있다.

특정 API 호출과 그 결과로 실행된 커널을 잇고 싶으면 행을 우클릭해 Events View로 보내면 된다. 둘은 상관 ID로 연결된다.

## 집계로 정량화: Stats System View

타임라인에서 이상한 구간을 찾았으면 여기서 숫자로 바꾼다.

![Stats System View]({{site.url}}/assets/images/nsight-systems-stats-view.png){: .align-center}

<center><sup>직접 캡처. 왼쪽 목록에서 리포트 종류를 고르면 오른쪽에 표가 뜬다</sup></center>

- **CUDA GPU Kernel Summary** — 커널별 총 시간과 호출 수. **최적화 대상 1순위를 정하는 곳**이다
- **CUDA API Summary** — API별 시간. `cudaMemcpy`나 `cudaStreamSynchronize`가 상위면 전송이나 동기화가 병목이다
- **CUDA GPU MemOps Summary (by Size)** / **(by Time)** — HtoD·DtoH 크기와 대역폭. 목록에 둘로 나뉘어 있다
- **CUDA API Trace** — 개별 호출 나열

CUDA API Trace에서 눈에 띄는 것이 하나 있었다. **첫 `cudaLaunchKernel`이 9.014ms**다. 커널 실행 비용이 아니라, CUDA가 커널 모듈을 처음 쓰는 시점에 지연 로딩하는 비용이 첫 호출에 한꺼번에 붙은 것이다. 벤치마크할 때 워밍업으로 빼야 하는 값이다.

다만 이것이 이 리포트에서 가장 긴 런치는 아니다. 정렬해 보면 그보다 긴 런치가 뒤쪽에 더 있는데, 그쪽은 성격이 다르다. **제출 큐가 차서 CPU가 런치 호출에서 막힌 것**이라 워밍업으로 없어지지 않고, 오히려 GPU가 충분히 바쁘다는 신호다. 같은 `cudaLaunchKernel`이라도 **언제 찍혔는지**에 따라 뜻이 달라지므로, 시간순으로 정렬해 앞뒤를 함께 봐야 한다.

그리고 이 화면의 하단에는 **같은 결과를 뽑는 CLI 명령이 그대로 표시된다.** 자동화할 때는 복사해서 쓰면 된다.

```shell
# GUI 의 Stats System View 와 같은 엔진. 화면에서 고른 리포트를 그대로 옮긴다
~# nsys stats --report=cuda_gpu_kern_sum,cuda_api_sum,cuda_gpu_mem_size_sum demo.nsys-rep
```

<details markdown="1">
<summary>랭크가 여러 개일 때</summary>

다중 랭크 학습에서는 리포트가 랭크 수만큼 나온다. 파일 이름 충돌은 `-o`의 치환 패턴으로 피하지만, 그다음이 더 성가시다.

- **랭크별 리포트의 t=0이 서로 다르다.** 각 프로세스가 시작한 시점이 기준이라, 여러 리포트를 나란히 놓고 "이 시점에 랭크 3이 무엇을 했나"를 보려면 시간축을 맞추는 작업이 따로 필요하다
- 그래서 랭크 수가 늘면 GUI로 하나씩 여는 방식이 성립하지 않는다. `nsys recipe`가 여러 리포트를 묶어 분석하는 경로를 제공하는데, 이 글에서는 다루지 않는다
- 전 랭크를 동시에 수집하면 오버헤드와 파일 크기가 함께 커진다. 대개는 랭크 하나만 감싸거나, 통신 구간을 볼 때만 몇 개를 골라 뜬다

</details>

<details markdown="1">
<summary>리포트를 여러 개, 다른 형식으로 뽑기</summary>

`--report`, `--format`, `--output`은 (리포트, 형식, 출력) 삼중 튜플로 처리되므로 한 번에 여러 조합을 낼 수 있다. 랭크별 리포트가 모인 디렉터리를 통째로 넘기는 것도 된다.

`nsys export`로 SQLite로 바꾸면 임의 쿼리를 던질 수 있다. 기본 타입이 sqlite라 `--type`은 생략 가능하고, 동봉된 `sqlite3` 바이너리를 그대로 쓰면 된다. 커널 이름 패턴별 집계처럼 기본 리포트에 없는 질문을 할 때 쓴다.

</details>

## 커널 이름에서 읽히는 것

집계 표는 시간 배분만 알려 주는 것이 아니다. [1편에서 본 커널 분해]({% post_url 2026-09-03-Dev-Nsight-Profiling-01-Concepts %}#타임라인-읽기)에서 GPU 시간의 98.4%를 차지한 것은 `volta_sgemm_128x64_nn`이었다. `sgemm`은 **단정도(FP32) 행렬 곱**이라는 뜻이다.

여기서 판정이 하나 바로 나온다. **이 워크로드는 텐서 코어를 쓰지 않는다.** T4에도 텐서 코어가 있지만 FP16·INT8 경로에서만 동작하고, FP32 SIMT 경로로 도는 `sgemm` 커널은 그쪽을 타지 않는다. `tiny.py`가 `torch.randn`으로 만든 FP32 텐서를 그대로 곱하고 있으니 당연한 결과인데, 실제 학습·서빙 워크로드에서 이 이름이 보인다면 **AMP나 `bf16`이 안 걸렸다는 신호**로 읽을 수 있다. 커널 이름 하나가 정밀도 설정을 되짚어 준다.

커널 이름 계열과 그 한계는 [4편]({% post_url 2026-09-03-Dev-Nsight-Profiling-04-Ncu %}#커널-이름-되짚기)에서 따로 다룬다.

## 자동 진단: Expert System View

`nsys`에는 규칙 기반 자동 진단이 들어 있다. GUI에서는 Expert System View, CLI에서는 `nsys analyze`인데 **같은 엔진**이다.

![Expert System View]({{site.url}}/assets/images/nsight-systems-expert-system-view.png){: .align-center}

<center><sup>직접 캡처. 규칙이 걸린 구간의 시작 시각과 지속 시간, 사용률이 표로 나온다</sup></center>

이 리포트에서는 GPU 사용률이 50% 미만인 구간 둘을 짚어 줬다. 5.49초에서 129ms 동안 0.7%, 6.39초에서 64ms 동안 7.9%다. 규칙이 지적한 시작 시각을 타임라인에서 그대로 찾아가면 원인을 볼 수 있다.

다만 **규칙은 힌트일 뿐이다.** 두 번째 구간은 초기화가 아니라 마무리(동기화와 결과 회수) 쪽이라 실제로는 무해하다.

더 중요한 것은 **이 진단이 놓친 것**이다. 규칙이 짚은 총량은 194ms인데, 앞에서 본 대로 이 세션에서 GPU가 놀고 있던 시간은 8초가 넘는다. `gpu_time_util` 규칙은 GPU가 활동한 **창 안쪽**을 스캔하므로, 임포트 구간처럼 GPU 활동이 아예 없는 구간은 애초에 후보에 들어가지 않는다. 자동 진단을 완결성 점검으로 쓰면 안 되는 이유다. 규칙이 조용하다고 문제가 없는 것이 아니다.

```shell
# GUI 의 Expert System View 와 같은 규칙 엔진. --rule all 은 모든 규칙을 돌린다
# 임계값과 표시 구간 수는 GUI 우상단 Settings 에서 조정한다
~# nsys analyze --rule=all demo.nsys-rep
```

## CPU가 병목일 때: 샘플링 세 뷰

`--sample`과 `-t osrt`로 모은 콜스택을 세 가지로 보여 준다. **GPU가 놀고 CPU가 병목일 때만 의미가 있다.**

![Top-Down View]({{site.url}}/assets/images/nsight-systems-cpu-topdown.png){: .align-center}

<center><sup>직접 캡처. 루트에서 내려가며 어느 호출 경로가 전체 시간을 먹는지 본다</sup></center>

Top-Down은 루트에서 내려가며 어느 모듈이나 호출 경로가 전체 시간을 먹는지 본다. 이 리포트에서는 `libcuda`가 17.62%, `python3.13`이 16.88%였고, 표본은 1,481개가 쓰였다.

여기서 화면 위쪽의 **프로세스 선택 드롭다운**이 중요해진다. 같은 뷰를 다른 프로세스로 바꿔 보면 이렇게 된다.

<details markdown="1">
<summary>같은 Top-Down View를 보조 프로세스로 바꿔 보면</summary>

![보조 프로세스의 Top-Down View]({{site.url}}/assets/images/nsight-systems-cpu-topdown-other-process.png){: .align-center}

<center><sup>직접 캡처. 프로세스를 [8881] basename 으로 바꾸면 표본이 4개뿐이라 읽을 것이 없다</sup></center>

`[8881] basename`은 전체의 0.5%만 차지하는 보조 프로세스라 표본이 4개뿐이고, 그중 절반이 프로파일러 자신의 주입 라이브러리다. CPU 샘플링 뷰를 볼 때 **어느 프로세스를 고르고 있는지 먼저 확인해야 하는 이유**다. 표본이 적으면 비율은 뜨지만 아무 의미가 없다.

</details>

<details markdown="1">
<summary>Bottom-Up과 Flat — 나머지 두 뷰</summary>

![Bottom-Up View]({{site.url}}/assets/images/nsight-systems-cpu-bottomup.png){: .align-center}

<center><sup>직접 캡처. 리프에서 올라가며 가장 많이 실행된 함수 자체를 본다</sup></center>

Bottom-Up은 리프에서 올라가며 "가장 많이 실행된 함수 자체가 무엇인가"를 본다. 이 리포트에서는 `_PyEval_EvalFrameDefault`의 Self가 6.01%였는데, 순수 파이썬 인터프리터가 쓴 시간이다.

![Flat View]({{site.url}}/assets/images/nsight-systems-cpu-flat.png){: .align-center}

<center><sup>직접 캡처. 함수별 Self 시간과 Stack 시간을 나란히 본다</sup></center>

Flat은 함수별로 Self(자기 시간)와 Stack(스택에 포함된 시간)을 나눠 보여 준다. **Self가 높으면 그 함수가 실제 범인이고, Stack만 높으면 호출자일 뿐이다.** 이 리포트에서는 `PyImport_ImportModuleLevelObject`의 Stack이 12.15%로 임포트 비용을 그대로 보여 주고, `cudaDeviceSynchronize`의 Stack이 5.94%로 GPU 대기를 보여 준다.

</details>

한 가지 주의할 것이 있다. 이 리포트의 CPU 샘플링에는 **`[Broken backtraces] 12.96%`**가 있고 심볼이 풀리지 않은 항목도 여럿이다. 파이썬 프레임을 제대로 보려면 `--python-sampling=true`가 필요하다. 파이썬 쪽만 따로 보고 싶으면 `py-spy` 같은 전용 도구를 병행하는 편이 낫다. 앞에서 본 대로 샘플링 주기도 2ms라, 지금 수치는 대략적 경향으로만 읽는 편이 맞다.

<details markdown="1">
<summary>Events View — 원시 이벤트 목록</summary>

![Events View]({{site.url}}/assets/images/nsight-systems-events-view.png){: .align-center}

<center><sup>직접 캡처. 아무 행도 보내지 않은 상태라 안내 문구만 떠 있다</sup></center>

타임라인 행을 우클릭해 `Show in Events View`로 보낸 이벤트의 원시 목록이다. 위 캡처처럼 아무것도 보내지 않으면 안내 문구만 뜬다. 특정 커널이나 API 호출 하나를 파고들 때만 쓴다. 집계가 아니라 개별 레코드라 처음부터 여기서 시작하면 길을 잃는다.

</details>

<br>

# 판정과 다음 조치

## 이 리포트가 말해 주는 것

읽는 순서를 그대로 따라가면 판정이 나온다. 결론부터 적으면 **이 리포트는 워크로드의 성능을 말해 주지 않는다.** 측정 설계 자체를 고쳐야 하는 상태다.

| 관찰 | 판정 | 조치 |
| --- | --- | --- |
| 전체 9.7초 중 GPU 구간 1.1초, 임포트 5.4초, 정체 불명 3.2초 | 측정 구간이 잘못 잡혔다 | `--capture-range=cudaProfilerApi` 또는 `--delay` |
| `No NVTX events collected` | 구간별 해상도가 없다 | `--pytorch=functions-trace` 또는 직접 주석 |
| 첫 `cudaLaunchKernel` 9.014ms, 저사용률 구간 129ms | 워밍업이 안 빠졌다 | 반복 루프 몇 회 돌린 뒤 측정 |
| `[Broken backtraces] 12.96%`, 샘플 1,481개 · 주기 2ms | CPU 샘플 신뢰도가 낮다 | `--python-sampling=true` |
| `driver 13.0 ... using 12.8 libraries` | 일부 이벤트 누락 가능 | 측정기 버전 올리기 |

특히 앞의 둘이 중요하다. **NVTX가 없으면 실전 분석은 사실상 안 된다.** 학습이나 서빙 워크로드에서 알고 싶은 것은 "이 커널이 몇 ms"가 아니라 "한 step에서 forward가 얼마, backward가 얼마, 통신이 얼마"인데, 구간 라벨이 없으면 그 질문에 답할 수 없다. `nsys stats`의 `nvtx_gpu_proj_sum` 리포트가 구간별 GPU 시간을 바로 뽑아 주는데, 이것도 NVTX가 있어야 쓸 수 있다.

## 리포트를 남기기 전에

`.nsys-rep`를 팀에 공유하거나 저장소에 커밋하기 전에 두 가지를 확인하는 편이 좋다.

**하나, 리포트에는 실행 환경의 환경변수가 통째로 들어간다.** `nsys`가 수집 시점의 환경을 리포트 메타데이터에 기록하기 때문이다. 이 글의 데모 리포트에서 확인해 보면 Colab 런타임의 노트북 ID, 컨테이너 호스트명, 내부 주소, 세션 터널 URL이 그대로 남아 있었다. 다행히 자격증명 필드는 비어 있었고 사내·개인 식별자도 없었지만, 사내 클러스터에서 뜬 리포트라면 사정이 다르다.

주의할 점이 둘 있다. 이 값들은 줄 단위가 아니라 **세미콜론으로 이어진 단일 문자열 필드**라 줄 단위로 지우는 방식이 통하지 않는다. 그리고 `--inherit-environment`는 이름과 달리 **대상 프로세스가 물려받을 환경**을 정하는 옵션이라, 리포트 기록을 없애 주는 스위치가 아니다. 결국 공유 전에 직접 확인하고, 민감한 값이 있으면 그 환경변수를 지운 셸에서 다시 수집하는 편이 확실하다.

**둘, 파일이 커진다.** `--osrt-threshold`를 낮추거나 `--cuda-graph-trace=node`를 켜면 특히 그렇다. 리포트가 커지면 내려받는 것 자체가 병목이 되는데, 그때 [2편에서 본 Nsight Streamer]({% post_url 2026-09-03-Dev-Nsight-Profiling-02-Environments %}#nsight-streamer)가 선택지가 된다.

<br>

# 정리

읽는 순서를 절차로 정리하면 이렇다. 이 편에서 얻을 것은 아래 절차이지 리포트의 숫자가 아니다.

1. **Analysis Summary** — `--trace`에 무엇이 들어갔는지, 어느 GPU인지 확인한다. 없는 데이터를 찾아 헤매지 않기 위해서다
2. **Diagnostics Summary** — 경고를 읽는다. 무엇이 빠졌는지가 여기서 정해진다
3. **타임라인의 CUDA HW 커널 행에서 빈 구간을 찾는다.** 대부분의 답이 여기 있다
4. 그 구간에서 **CUDA API 행과 OS runtime 행을 세로로 대조**해 원인을 가른다. 동기화 대기인지, 데이터 로딩인지, CPU 전처리인지, 런치 오버헤드인지
5. **Stats System View의 Kernel Summary**로 상위 커널을 정량화한다
6. CPU 병목으로 판명된 경우에만 **Bottom-Up·Flat View**로 내려간다

| 항목 | 내용 |
| --- | --- |
| 읽는 원칙 | 타임라인에서 눈으로 찾고 아래 패널로 정량화. 반대로 가지 않는다 |
| 핵심 기술 | CUDA API 행과 CUDA HW 행을 세로로 대조 |
| GUI ↔ CLI | Stats System View는 `nsys stats`, Expert System View는 `nsys analyze` |
| 먼저 볼 곳 | Analysis Summary(무엇을 수집했나), Diagnostics Summary(무엇이 빠졌나) |
| 사고 지점 | `--capture-range`만 붙이면 기본값이 앱에 신호를 보낸다 |
| 이 리포트의 결론 | 성능 판정이 아니라 측정 설계를 고쳐야 하는 상태 |

`nsys`로 범인 구역을 좁혔으면 다음은 그 커널 하나를 파고드는 차례다. 다음 편에서 `ncu`를 같은 순서로 정리한다.

<br>

# 참고 링크

- [Nsight Systems User Guide](https://docs.nvidia.com/nsight-systems/UserGuide/index.html)
- [Nsight Systems CLI Reference](https://docs.nvidia.com/nsight-systems/UserGuide/index.html#cli-profiling)
- [NVTX Documentation](https://nvidia.github.io/NVTX/)
- [vLLM — Profiling vLLM](https://docs.vllm.ai/en/latest/contributing/profiling.html)
- [PyTorch — torch.cuda.profiler](https://docs.pytorch.org/docs/stable/cuda.html)
- [Nsight 프로파일러: 1. 개념과 동작 원리]({% post_url 2026-09-03-Dev-Nsight-Profiling-01-Concepts %})
- [Nsight 프로파일러: 2. 실행 환경별 적용]({% post_url 2026-09-03-Dev-Nsight-Profiling-02-Environments %})

<br>
