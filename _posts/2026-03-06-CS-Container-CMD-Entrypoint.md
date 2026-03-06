---
title:  "[Container] 컨테이너 실행 명령: CMD, ENTRYPOINT"
excerpt: "Docker CMD와 ENTRYPOINT에 대해 알아보자."
categories:
  - CS
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Container
  - Docker
  - CMD
  - ENTRYPOINT
---

<br>

Docker의 `CMD`와 `ENTRYPOINT`는 항상 헷갈리는 주제다. 대충 알고 있으면서도 정확히 뭐가 다르고, 어떻게 조합되며, Kubernetes에서는 어떻게 매핑되는지 명확하게 정리한 적이 없어 정리해 보고자 한다.

<br>

# TL;DR

- **CMD**: 컨테이너 시작 시 실행할 기본 명령. `docker run` 인자로 **완전히 대체**됨
- **ENTRYPOINT**: 컨테이너가 항상 실행할 고정 명령. `docker run` 인자가 **뒤에 추가**됨
- **CMD + ENTRYPOINT**: ENTRYPOINT로 실행 파일을 고정하고, CMD로 기본 인자를 제공하는 패턴
- **exec form 권장**: shell form은 PID 1 문제로 시그널 전달이 안 되어 graceful shutdown이 불가능
- **Kubernetes 매핑**: `command` = ENTRYPOINT, `args` = CMD

<br>

# 들어가며

`CMD`와 `ENTRYPOINT`는 Dockerfile 문법이지만, 빌드된 이미지에는 OCI 표준 형식으로 저장된다. 따라서 Docker가 아닌 다른 OCI 호환 런타임(containerd, CRI-O 등)에서도 동일하게 동작한다. 이 글에서는 관례상 Docker를 기준으로 설명한다.

<br>

# 전제: 컨테이너의 생명주기

컨테이너는 특정 프로세스(웹 서버, DB, 배치 작업 등)를 실행하기 위한 격리된 환경이다. VM처럼 OS를 호스팅하는 것이 아니다. 따라서 컨테이너의 생명주기는 **메인 프로세스의 생명주기**와 같다.

- 컨테이너 시작 시, 지정된 메인 프로세스가 **PID 1**로 실행된다
- PID 1이 종료되면 컨테이너도 즉시 종료된다

<br>

이 원칙을 체감할 수 있는 사례는 아래와 같다. Dockerfile 마지막이 `CMD ["bash"]`로 끝나는 커스텀 이미지 `my-image`가 있다고 하자.

```dockerfile
FROM ubuntu
# ... 생략 ...
CMD ["bash"]
```

이 이미지를 그냥 실행하면 컨테이너가 바로 종료된다.

```bash
docker run my-image
docker ps      # 아무것도 없음
docker ps -a   # Exited 상태로 존재
```

종료 흐름을 따라가 보면 아래와 같다.

1. `bash`는 stdin에 연결된 TTY(pseudo-terminal)가 있어야 동작하는 셸 프로그램이다
2. `docker run`은 기본적으로 TTY를 컨테이너에 연결하지 않는다
3. `bash`가 TTY를 찾지 못해 즉시 종료된다
4. PID 1이 종료됐으므로 컨테이너도 종료된다

<br>

해결 방법은 두 가지다.

첫째, 호스트에서 TTY를 제공한다. TTY는 이미지 안에 있는 것이 아니라, 호스트가 컨테이너에 제공하는 리소스다.

```bash
docker run -it my-image
# -i: stdin 연결 (interactive)
# -t: TTY 할당
```

> **TTY와 PTY**: TTY(teletypewriter)는 원래 물리적인 텔레타이프 단말기를 뜻했고, 현대 리눅스에서는 터미널 장치 전반을 가리키는 상위 개념으로 쓰인다. PTY(pseudo-terminal)는 소프트웨어로 에뮬레이션한 가상 터미널로, TTY의 한 종류다(`/dev/pts/*`). `bash` 같은 대화형 셸은 사용자의 키보드 입력을 받고 화면에 출력하기 위해 이 터미널 장치가 필요하다. `-t` 플래그는 컨테이너에 PTY를 할당하고, `-i`는 호스트의 stdin을 컨테이너에 연결하여 대화형 입력이 가능하게 한다.

둘째, `docker run` 시 실행 명령을 직접 넘긴다. 이렇게 하면 이미지의 `CMD ["bash"]`가 대체된다.

```bash
docker run my-image sleep 5
# bash 대신 sleep 5가 PID 1로 실행됨
# 5초 후 sleep이 종료되면 컨테이너도 종료됨
```

물론 `sleep 5`도 5초 후에는 종료되지만, 핵심은 CMD를 대체하여 원하는 프로세스를 실행할 수 있다는 점이다. 이것이 바로 다음에 다룰 CMD의 오버라이드 동작이다.

<br>

# CMD: 기본 실행 명령

## 정의

컨테이너 시작 시 실행할 **기본 명령과 인자**를 정의한다. `docker run` 실행 시 커맨드라인 인자를 넘기면, CMD 전체가 완전히 대체된다.

Dockerfile에 CMD나 ENTRYPOINT가 여러 번 나오면 **마지막 것만 유효**하다. 이전 것들은 모두 무시된다. 이는 CMD와 ENTRYPOINT가 `RUN`처럼 빌드 중 순차 실행되는 명령어가 아니라, 이미지 메타데이터(OCI config)에 단일 값으로 저장되는 **선언적 설정**이기 때문이다. 여러 번 선언하면 마지막 값이 이전 값을 덮어쓴다. 멀티스테이지 빌드나 긴 Dockerfile에서 흔히 겪는 실수이므로 주의해야 한다.

<br>

## 작성 형식

CMD는 **shell form**과 **exec form** 두 가지로 작성할 수 있다.

### shell form

```dockerfile
CMD sleep 5
# Docker가 구성하는 명령: ["/bin/sh", "-c", "sleep 5"]
```

`/bin/sh -c`를 통해 실행된다. 즉, 실제로는 `/bin/sh -c "sleep 5"`가 실행되는 셈이다. 환경변수 치환, 파이프, 리다이렉션 등 셸 기능을 그대로 쓸 수 있다.

```dockerfile
CMD echo "port: $PORT"           # $PORT가 치환됨
CMD cat access.log | grep ERROR  # 파이프 동작
```

### exec form (권장)

```dockerfile
CMD ["sleep", "5"]
# Docker가 구성하는 명령: ["sleep", "5"]
```

셸을 거치지 않고 직접 실행된다. 배열의 첫 번째 요소가 실행 파일이고, 나머지가 인자다.

**주의**: 명령과 인자는 배열의 **별도 요소**로 분리해야 한다. `["sleep 5"]`는 `sleep 5`라는 이름의 실행 파일을 찾으려 하므로 잘못된 형식이다.

<br>

## docker run에서의 동작: CMD 완전 대체

`docker run` 실행 시 커맨드라인 인자를 넘기면, CMD 전체가 대체된다. 다음과 같은 Dockerfile로 빌드한 `my-image` 이미지가 있다고 하자.

```dockerfile
FROM ubuntu
CMD ["sleep", "5"]
# Docker가 구성하는 기본 명령: ["sleep", "5"]
```

```bash
docker run my-image sleep 10
# CMD ["sleep", "5"]가 ["sleep", "10"]으로 완전히 대체됨
# 실제 실행: sleep 10
```

<br>

# ENTRYPOINT: 고정 실행 명령

## 정의

컨테이너가 **항상 실행할 실행 파일**을 정의한다. CMD와의 핵심 차이는 `docker run` 인자에 의한 **오버라이드 동작**이다. CMD는 인자를 넘기면 전체가 대체되지만, ENTRYPOINT는 인자가 뒤에 추가된다.

<br>

## 작성 형식

CMD와 동일하게 shell form과 exec form으로 작성할 수 있으며, 규칙도 같다. 이번에는 `my-image`를 ENTRYPOINT로 다시 정의해 보자.

### shell form

```dockerfile
FROM ubuntu
ENTRYPOINT sleep
# Docker가 구성하는 명령: ["/bin/sh", "-c", "sleep"]
```

CMD의 shell form과 마찬가지로 `/bin/sh -c`를 통해 실행된다.

### exec form (권장)

```dockerfile
FROM ubuntu
ENTRYPOINT ["sleep"]
# Docker가 구성하는 명령: ["sleep"]
```

셸을 거치지 않고 직접 실행된다.

<br>

## docker run에서의 동작: 인자 추가

`docker run` 실행 시 커맨드라인 인자는 ENTRYPOINT **뒤에 추가**된다. CMD와 달리 대체가 아니라 append다.

```bash
docker run my-image 10
# 실제 실행: sleep 10
```

인자를 누락하면 기본 인자가 없으므로 ENTRYPOINT만 실행되어 에러가 발생한다.

```bash
docker run my-image
# sleep: missing operand → 에러
```

<br>

## ENTRYPOINT 오버라이드

`--entrypoint` 플래그로 이미지에 정의된 ENTRYPOINT를 대체할 수 있다.

```bash
docker run --entrypoint sleep2.0 my-image 10
# 실제 실행: sleep2.0 10
```

<br>

# CMD vs ENTRYPOINT

CMD와 ENTRYPOINT는 둘 다 "컨테이너 시작 시 실행할 명령"을 정의하고, 작성 형식(shell form, exec form)도 동일하다. 핵심 차이는 **`docker run` 인자에 대한 오버라이드 동작**이다.

| | CMD | ENTRYPOINT |
|---|---|---|
| `docker run` 인자 | **완전 대체** | **뒤에 추가**(append) |
| 설계 의도 | 기본값 — 사용자가 바꿀 수 있다 | 고정값 — 이 컨테이너는 항상 이 실행 파일을 돌린다 |
| 오버라이드 방법 | `docker run <image> <args>` | `docker run --entrypoint <exec> <image>` |

이 차이로 인해 둘을 조합하는 패턴(ENTRYPOINT로 실행 파일을 고정, CMD로 기본 인자 제공)이 가능해진다. 이 패턴은 뒤에서 자세히 다룬다.

<br>

# shell form의 한계

앞서 CMD와 ENTRYPOINT 모두 shell form과 exec form으로 작성할 수 있다고 했다. 그런데 왜 exec form이 권장될까? shell form에는 두 가지 근본적인 한계가 있다.

<br>

## PID 1과 작성 형식의 관계

CMD와 ENTRYPOINT의 차이는 오버라이드 동작(대체 vs 추가)이지, **PID 1이 뭐가 되느냐가 아니다.** PID 1을 결정하는 것은 작성 형식이다.

| | shell form | exec form |
|---|---|---|
| **CMD** | PID 1 = `/bin/sh` | PID 1 = 지정된 실행 파일 |
| **ENTRYPOINT** | PID 1 = `/bin/sh` | PID 1 = 지정된 실행 파일 |

shell form은 CMD든 ENTRYPOINT든 `/bin/sh -c`로 감싸지므로 PID 1이 `sh`가 된다. exec form은 지정된 실행 파일이 직접 PID 1이 된다. 이 차이가 아래에서 다룰 시그널 전달 문제의 원인이다.

<br>

## `/bin/sh` 의존성

shell form은 빌드 타임(Dockerfile)과 런타임(`docker run`) 모두에서 `/bin/sh -c`를 가정한다. 이미지에 `/bin/sh`가 없으면 shell form 명령은 실행 자체가 실패한다.

`/bin/sh`가 없는 대표적인 케이스는 **scratch 이미지**와 **distroless 이미지**다. 이런 이미지에서는 exec form이 강제된다.

```dockerfile
FROM scratch
COPY myapp /myapp
CMD ["/myapp"]   # exec form 강제. shell form 쓰면 /bin/sh 없어서 실패
# Docker가 구성하는 명령: ["/myapp"]
```

<br>

ubuntu, debian, alpine, centos 등 범용 베이스 이미지에는 보통 `/bin/sh`가 있다. 다만 alpine은 `/bin/bash`는 없고 `/bin/sh`(ash)만 있어서, bash 전용 문법을 shell form에 쓰면 깨질 수 있다.

따라서 범용 베이스 이미지 기반이면 실무에서 `/bin/sh` 부재로 깨지는 경우는 드물다. 그럼에도 불구하고 exec form이 명시적이고 이식성이 높아 권장된다.

<br>

## PID 1 문제와 시그널 전달

**시그널**은 프로세스에게 종료, 중단 같은 신호를 보내는 OS 메커니즘이다. 대표적으로 `SIGTERM`(정상 종료 요청), `SIGINT`(인터럽트), `SIGKILL`(강제 종료)이 있다.

`docker stop` 실행 시 Docker는 컨테이너 PID 1에게 `SIGTERM`을 보내고, **grace period**(기본 10초) 동안 프로세스가 종료되기를 기다린다. 이 시간 내에 종료되지 않으면 `SIGKILL`을 보내 강제 종료한다. grace period는 `docker stop -t <seconds>`로 조정할 수 있다. PID 1이 `SIGTERM`을 받아 graceful shutdown(진행 중인 요청 마무리, 파일 플러시 등)을 수행하고 종료하는 것이 정상 흐름이다.

shell form으로 실행하면 프로세스 트리가 다음과 같이 구성된다.

```dockerfile
CMD sleep 100
# Docker가 구성하는 명령: ["/bin/sh", "-c", "sleep 100"]
```

```
PID 1: /bin/sh -c sleep 100
└── PID 7: sleep 100          # sh의 자식 프로세스
```

PID 1은 `sh`이고, 실제 프로세스(`sleep`)는 `sh`의 자식 프로세스다. 문제는 **`sh`가 시그널을 자식에게 전달하지 않는다**는 점이다.

```
docker stop
  → SIGTERM → PID 1 (sh)
  → sh는 자기 자신만 종료, 자식 정리 없음
  → PID 1 소멸 → 커널이 나머지 프로세스에 SIGKILL
  → 실제 프로세스(nginx 등) graceful shutdown 기회 없음
  (또는 grace period 10초 경과 후 Docker가 SIGKILL 전송)
```

`/bin/sh`(dash, ash 등 컨테이너에서 자주 쓰이는 경량 sh 포함)는 `SIGTERM`을 받으면 자식 프로세스를 건드리지 않고 자기 자신만 종료한다. 전달하지 않는다는 건 자식에게 SIGTERM을 보내지 않는다는 뜻이고, kill하거나 wait하는 동작도 없다. PID 1이 죽으면 커널은 컨테이너 내 나머지 모든 프로세스에 `SIGKILL`을 보낸다.

결국 실제 프로세스(`sleep`, 또는 웹 서버라면 nginx/gunicorn 등)는 `SIGTERM`을 한 번도 받지 못한 채 `SIGKILL`로 강제 종료된다. **graceful shutdown이 불가능**하다.

> `bash`는 `trap`으로 시그널 핸들러를 직접 구현하면 자식에게 전달하도록 만들 수는 있으나, 그건 명시적으로 작성한 경우이고 기본 동작은 아니다. 컨테이너에서 shell form은 대부분 dash나 ash 계열이라 그 옵션조차 없다.

<br>

## PID 1 확인 방법

shell form과 exec form의 PID 1 차이는 `docker top`이나 컨테이너 내부의 `ps`로 직접 확인할 수 있다.

```bash
# shell form: `CMD sleep 100`
$ docker run -d --name shell-test my-image
$ docker top shell-test
PID   USER   COMMAND
  1   root   /bin/sh -c sleep 100
  7   root   sleep 100
```

PID 1이 `/bin/sh`이고, 실제 프로세스 `sleep`은 자식 프로세스다.

```bash
# exec form: `CMD ["sleep", "100"]`
$ docker run -d --name exec-test my-image
$ docker top exec-test
PID   USER   COMMAND
  1   root   sleep 100
```

PID 1이 `sleep` 자체다. `docker stop` 시 `SIGTERM`이 바로 전달된다.

> `docker exec <container> ps aux`로 컨테이너 내부에서도 확인할 수 있다. 다만 이미지에 `ps`가 설치되어 있어야 한다. `docker top`은 호스트에서 실행하므로 이미지에 별도 도구가 필요 없다.

<br>

## 그럼 shell form은 왜 존재하는가?

exec form은 셸을 거치지 않기 때문에 환경변수 치환, 파이프, 리다이렉션, `&&` 등 셸 문법을 쓸 수 없다.

```dockerfile
# 환경변수 치환
CMD echo "port: $PORT"           # shell form: $PORT가 치환됨
CMD ["echo", "port: $PORT"]      # exec form: "$PORT"가 문자 그대로 출력됨

# 파이프
CMD cat access.log | grep ERROR      # shell form: 동작
CMD ["cat access.log | grep ERROR"]  # exec form: 불가능
```

exec form에서 셸 기능이 필요하면 직접 `sh`를 명시해야 한다.

```dockerfile
CMD ["/bin/sh", "-c", "echo port: $PORT"]
```

이렇게 하면 shell form과 동일한 동작이다. shell form은 이 패턴을 간단하게 쓰는 문법적 편의 형식이라고 볼 수 있다.

결국, 언제나 그렇듯 **트레이드오프**다. 셸 기능이 필요하면 shell form을 쓰되 시그널 문제를 감수해야 하고, 그렇지 않으면 exec form이 기본 선택이다. 셸 기능과 시그널 전달이 모두 필요하다면, exec form에서 `/bin/sh -c`를 직접 명시하면서 스크립트 내에서 `exec`로 실제 프로세스를 PID 1로 교체하는 방식이 그럴 듯한 해법이다.

<br>

# CMD + ENTRYPOINT: 기본 인자 패턴

## 조합 방식

ENTRYPOINT에 실행 파일을 고정하고, CMD로 기본 인자를 제공하는 패턴이다. `my-image`를 다시 한 번 바꿔 보자.

```dockerfile
FROM ubuntu
ENTRYPOINT ["sleep"]
CMD ["5"]
# Docker가 구성하는 기본 명령: ["sleep", "5"] → sleep 5
```

- 인자 없이 실행: `sleep 5` — CMD가 기본값으로 사용됨
- 인자를 넘기면: `sleep 10` — CMD는 무시되고 커맨드라인 인자가 사용됨

<br>

## exec form 필수

CMD와 ENTRYPOINT를 함께 쓸 때는 **반드시 둘 다 exec form**(JSON 배열)으로 작성해야 한다.

shell form의 CMD는 `/bin/sh -c CMD` 형태로 해석되기 때문에, ENTRYPOINT와의 인자 결합이 의도대로 동작하지 않는다. 예를 들어:

```dockerfile
# 둘 다 shell form — 의도대로 동작하지 않음
ENTRYPOINT sleep
CMD 5
# Docker 내부에서 구성되는 명령: ["/bin/sh", "-c", "sleep", "/bin/sh", "-c", "5"]
# → sh -c는 첫 번째 인자("sleep")만 명령으로 실행하고,
#   나머지("/bin/sh", "-c", "5")는 셸의 위치 매개변수($0, $1, $2)로 전달되어 무시됨
# → 결과적으로 sleep이 인자 없이 실행됨 (CMD가 사실상 무시됨)
```

이 동작은 [Docker 공식 문서의 CMD/ENTRYPOINT 상호작용 매트릭스](https://docs.docker.com/reference/dockerfile/#understand-how-cmd-and-entrypoint-interact)에 명시되어 있다. ENTRYPOINT가 shell form이면 CMD의 형식에 관계없이 CMD는 무시된다.

exec form으로 작성하면 Docker가 두 배열을 단순히 연결(concatenate)한다.

```dockerfile
# 둘 다 exec form — 정상 동작
ENTRYPOINT ["sleep"]
CMD ["5"]
# 최종 명령: ["sleep", "5"] → sleep 5
```

Docker는 exec form의 ENTRYPOINT 배열 뒤에 exec form의 CMD 배열을 그대로 이어 붙여 최종 실행 명령을 만든다. shell form이 끼면 각각이 `/bin/sh -c`로 감싸져 결합이 깨진다.

<br>

## 동작 매트릭스

| ENTRYPOINT | CMD | docker run 인자 | 실제 실행 |
|---|---|---|---|
| 없음 | `["sleep", "5"]` | 없음 | `sleep 5` |
| 없음 | `["sleep", "5"]` | `sleep 10` | `sleep 10` |
| `["sleep"]` | 없음 | 없음 | `sleep` (에러) |
| `["sleep"]` | 없음 | `10` | `sleep 10` |
| `["sleep"]` | `["5"]` | 없음 | `sleep 5` |
| `["sleep"]` | `["5"]` | `10` | `sleep 10` |

<br>

## docker run 오버라이드 규칙 정리

```bash
# CMD 대체: 이미지 뒤에 인자를 넘김
docker run <image> <args>

# ENTRYPOINT 대체: --entrypoint 플래그 사용
docker run --entrypoint <executable> <image> <args>
```

<br>

# Kubernetes에서의 매핑

## command와 args

Kubernetes Pod spec의 `command`와 `args`는 각각 Docker의 ENTRYPOINT와 CMD에 대응한다.

| Kubernetes | Docker / OCI |
|---|---|
| `command` | `ENTRYPOINT` |
| `args` | `CMD` |

Pod spec에서 `command`나 `args`를 지정하면 이미지에 정의된 ENTRYPOINT/CMD를 오버라이드한다.

주의할 점은, **`command`만 지정하고 `args`를 생략하면 이미지의 CMD도 함께 무시**된다는 것이다. Docker의 `--entrypoint`가 ENTRYPOINT만 대체하는 것과 다르다.

| Image ENTRYPOINT | Image CMD | `command` | `args` | 실행 결과 |
|---|---|---|---|---|
| `[sleep]` | `[5]` | 미지정 | 미지정 | `sleep 5` |
| `[sleep]` | `[5]` | `[sleep2.0]` | 미지정 | `sleep2.0` (CMD `5` 무시!) |
| `[sleep]` | `[5]` | 미지정 | `[10]` | `sleep 10` |
| `[sleep]` | `[5]` | `[sleep2.0]` | `[10]` | `sleep2.0 10` |

두 번째 행이 핵심이다. `command`를 지정하면 이미지의 CMD가 자동으로 사용되지 않으므로, `command`를 쓸 때는 필요한 인자를 `args`로 반드시 함께 지정해야 한다.

<br>

## 예시

CMD만 오버라이드:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-image-pod
spec:
  containers:
    - name: sleeper
      image: my-image
      args: ["10"]  # CMD 오버라이드 → sleep 10
```

ENTRYPOINT와 CMD 모두 오버라이드:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-image-pod
spec:
  containers:
    - name: sleeper
      image: my-image
      command: ["sleep2.0"]  # ENTRYPOINT 오버라이드
      args: ["10"]           # CMD 오버라이드
      # → sleep2.0 10
```

<br>

## 흔한 실수

### 숫자 타입 에러

`command`와 `args`의 모든 요소는 **문자열**이어야 한다. 숫자를 따옴표 없이 넘기면 YAML이 숫자 타입으로 파싱하고, Kubernetes API가 타입 불일치 에러를 반환한다.

```yaml
# 잘못된 예시 — 1200이 숫자 타입으로 파싱됨
spec:
  containers:
  - name: ubuntu
    image: ubuntu
    command:
      - "sleep"
      - 1200
```

```
Error from server (BadRequest): Pod in version "v1" cannot be handled as a Pod:
json: cannot unmarshal number into Go struct field Container.spec.containers.command of type string
```

수정은 간단하다. 숫자를 따옴표로 감싸면 된다.

```yaml
# 올바른 예시
command:
  - "sleep"
  - "1200"
```

<br>

### command와 args의 잘못된 매핑

`command`는 ENTRYPOINT(실행 파일)를 대체하고, `args`는 CMD(인자)를 대체한다. 이 매핑을 혼동하면 의도와 다르게 동작한다. 다음 Dockerfile로 빌드된 이미지가 있다고 하자.

```dockerfile
FROM python:3.6-alpine
RUN pip install flask
COPY . /opt/
EXPOSE 8080
WORKDIR /opt
ENTRYPOINT ["python", "app.py"]
CMD ["--color", "red"]
# Docker가 구성하는 기본 명령: ["python", "app.py", "--color", "red"]
```

이 이미지의 ENTRYPOINT는 `python app.py`이고, CMD는 `--color red`다. 기본 실행 시 `python app.py --color red`가 된다.

여기서 색상을 green으로 바꾸고 싶어서 아래처럼 작성하면 문제가 생긴다.

```yaml
# 잘못된 예시 — command가 ENTRYPOINT를 대체함
spec:
  containers:
  - name: simple-webapp
    image: kodekloud/webapp-color
    command: ["--color", "green"]
```

`command`는 ENTRYPOINT를 대체하므로, 원래의 `python app.py`가 사라지고 `--color green`이 실행 명령이 된다. 게다가 `args`를 생략했으므로 이미지의 CMD(`["--color", "red"]`)도 함께 무시된다. 앞서 언급한 "`command`만 지정하면 CMD도 무시된다"는 규칙이 그대로 적용되는 사례다. 즉 최종 명령은 `--color green --color red`가 아니라 `--color green`뿐이다. `--color`라는 실행 파일은 없으므로 컨테이너가 시작에 실패한다. 

올바른 방법은 `args`를 사용하는 것이다. `args`는 CMD만 대체하므로 ENTRYPOINT(`python app.py`)는 유지된다.

```yaml
# 올바른 예시 — args로 CMD만 대체
spec:
  containers:
  - name: simple-webapp
    image: kodekloud/webapp-color
    args: ["--color", "green"]
    # → python app.py --color green
```

<br>

# 정리

| 구분 | CMD | ENTRYPOINT |
|---|---|---|
| 역할 | 기본 명령/인자 | 고정 실행 파일 |
| `docker run` 인자 | 완전 대체 | 뒤에 추가(append) |
| 런타임 오버라이드 | `docker run <image> <args>` | `docker run --entrypoint <exec> <image>` |
| Kubernetes 대응 | `args` | `command` |

Dockerfile 작성 시 기억할 점:

- **exec form을 기본으로 쓴다.** shell form은 PID 1 문제로 `SIGTERM`이 실제 프로세스에 전달되지 않아 graceful shutdown이 불가능하다. 이는 CMD와 ENTRYPOINT 모두에 해당한다.
- **ENTRYPOINT + CMD 조합**으로 실행 파일은 고정하고 기본 인자를 제공하는 패턴이 가장 유연하다. 이 조합에서는 반드시 둘 다 exec form이어야 한다.
- **셸 기능이 필요하면** exec form에서 `/bin/sh -c`를 직접 명시하는 것이 shell form의 편의성과 exec form의 명시성을 모두 취하는 방법이다.

Kubernetes에서는 용어가 달라져 혼동하기 쉽지만, `command` = ENTRYPOINT, `args` = CMD라는 매핑만 기억하면 된다.

<br>
