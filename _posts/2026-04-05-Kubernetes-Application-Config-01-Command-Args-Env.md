---
title:  "[Kubernetes] 어플리케이션 설정 - 1. 컨테이너 커맨드, 인자, 환경 변수"
excerpt: "Kubernetes 파드에서 컨테이너의 커맨드, 인자, 환경 변수를 설정하는 방법을 알아보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubernetes-in-Action-2nd
  - container
  - ENTRYPOINT
  - CMD
  - command
  - args
  - environment-variable
hidden: false
---

*[Kubernetes in Action 2nd Edition](https://www.manning.com/books/kubernetes-in-action-second-edition) 8장의 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- Docker의 `ENTRYPOINT`/`CMD`에 대응하는 Kubernetes의 `command`/`args` 필드로 컨테이너 실행 커맨드와 인자를 오버라이드할 수 있다
- 환경 변수는 컨테이너 단위로만 설정 가능하며, 리터럴 값, 다른 환경 변수 참조(`$(VAR_NAME)`), 외부 소스(ConfigMap, Secret) 참조를 지원한다
- `$(VAR_NAME)` 구문은 같은 매니페스트에 정의된 변수만 참조 가능하다. 이미지/OS 변수는 셸(`sh -c`)을 통해 참조해야 한다

<br>

# 시리즈 안내

Kubernetes에서 어플리케이션을 설정하는 방법을 다루는 시리즈다. 파드 매니페스트에 직접 설정하거나, 별도의 리소스를 통해 설정하는 방식을 정리한다.

1. 컨테이너 커맨드, 인자, 환경 변수 (이 글)
2. [ConfigMap]({% post_url 2026-04-05-Kubernetes-Application-Config-02-ConfigMap %})
3. [Secret]({% post_url 2026-04-05-Kubernetes-Application-Config-03-Secret %})
4. [Downward API]({% post_url 2026-04-05-Kubernetes-Application-Config-04-Downward-API %})

<br>

ConfigMap, Secret, Downward API의 데이터를 컨테이너에 전달하는 방법은 크게 두 가지다.

1. **환경 변수** — 데이터를 컨테이너 프로세스의 환경에 직접 넣어주는 방식. 이 시리즈에서 다룬다.
2. **볼륨 마운트** — 데이터를 컨테이너의 파일 시스템에 파일로 나타나게 하는 방식. 별도 시리즈에서 다룬다.

Kubernetes 문맥에서 환경 변수 방식을 **inject**(주입), 볼륨 방식을 **project**(투사/투영)라고 표현하는 경우가 많다. 프로젝터가 스크린에 이미지를 투사하듯, 원본 데이터(ConfigMap, Secret 등)를 컨테이너 파일 시스템이라는 "스크린"에 비추는 것이다.

<br>

# 커맨드와 인자 설정

컨테이너화된 어플리케이션도 일반 어플리케이션과 마찬가지로 **커맨드라인 인자**, **환경 변수**, **파일**을 통해 설정할 수 있다.

컨테이너에서 실행되는 커맨드는 보통 컨테이너 이미지에 정의된다. Dockerfile에서 `ENTRYPOINT` 지시어로 커맨드를, `CMD` 지시어로 인자를 지정한다. 환경 변수는 `ENV` 지시어로, 설정 파일은 `COPY` 지시어로 컨테이너 이미지에 추가할 수 있다.

## Docker ENTRYPOINT와 CMD

Docker에서 컨테이너 실행 커맨드와 인자는 Dockerfile의 `ENTRYPOINT`와 `CMD` 지시어로 설정된다. 두 지시어의 동작 원리, shell form vs exec form, PID 1 문제 등은 [컨테이너 실행 명령: CMD, ENTRYPOINT]({% post_url 2026-03-06-CS-Container-CMD-Entrypoint %}) 글에서 상세히 다뤘다. 여기서는 Kubernetes 매핑에 필요한 핵심만 짚는다.

- `ENTRYPOINT`: 컨테이너 실행 커맨드 — 고정 실행 명령
- `CMD`: 기본 커맨드라인 인자 — 가변 인자

두 지시어 모두 배열 값을 받고, 컨테이너 실행 시 두 배열을 연결(concatenate)해서 최종 커맨드를 생성한다.

Kiada 0.4 어플리케이션의 Dockerfile을 예로 보자. listening port를 `--listen-port` 커맨드라인 인자로 변경 가능하게 하고, 초기 상태 메시지를 `INITIAL_STATUS_MESSAGE` 환경 변수로 설정 가능하게 수정한 버전이다.

```docker
FROM node:22-alpine
COPY app.js /app.js
COPY html/ /html

# 환경변수 설정
ENV INITIAL_STATUS_MESSAGE="This is the default status message"

# 컨테이너 시작 시 실행할 커맨드
ENTRYPOINT ["node", "app.js"] 
# 기본 커맨드라인 인자 설정: listening port 설정
CMD ["--listen-port", "8080"] 
```

Docker 컨테이너를 실행해서 동작을 확인할 수 있다.

```bash
# 기본 실행 (CMD 기본값 사용: --listen-port 8080)
docker run -p 8080:8080 luksa/kiada:0.4

# 실행 결과
Kiada - Kubernetes in Action Demo Application
---------------------------------------------
Kiada 0.4 starting...
Pod name is unknown-pod
Local hostname is 8d31534c1db2
Local IP is 0.0.0.0
Running on node unknown-node
Node IP is 0.0.0.0
Status message is This is the default status message
Listening on port 8080
```

```bash
# CMD 오버라이드: listening port를 9090으로 변경
docker run -p 9090:9090 luksa/kiada:0.4 --listen-port 9090

# 실행 결과
Kiada 0.4 starting...
Listening on port 9090
```

```bash
# ENTRYPOINT 오버라이드: node 대신 다른 커맨드 실행
docker run --entrypoint /bin/sh luksa/kiada:0.4 -c "echo hello"
hello
```

- `docker run <image> <args>`: CMD를 대체한다
- `docker run --entrypoint <executable> <image> <args>`: ENTRYPOINT를 대체한다

<details markdown="1">
<summary><b>Docker ENTRYPOINT/CMD 심화</b> — <i><a href="{% post_url 2026-03-06-CS-Container-CMD-Entrypoint %}">별도 글</a>에서 더 자세히 다룬다</i></summary>

### CMD

```docker
FROM ubuntu
CMD ["sleep", "5"] # CMD sleep 5
```

컨테이너 시작 시 실행할 기본 명령과 인자를 정의한다.

**작성 형식**

- shell form: `CMD sleep 5`
  - `/bin/sh -c`를 통해 실행된다: `/bin/sh -c CMD`
  - 셸 기능(변수 치환, 파이프 등) 사용 가능
  - PID 1이 `sh`가 되어 시그널 전달 문제 발생 가능
- exec form (권장): `CMD ["sleep", "5"]`
  - 셸을 거치지 않고 직접 실행, PID 1이 실제 프로세스가 됨
  - 첫 번째 요소는 반드시 실행파일, 명령과 인자는 별도 요소로 분리해야 한다 (`["sleep 5"]`는 잘못된 표기)

셸 기능이 필요하면 shell form + 시그널 문제를 감수하고, 그 외에는 exec form을 쓰는 것이 권장된다.

`docker run` 실행 시 커맨드라인 인자를 넘기면 CMD 전체가 완전히 대체된다.

```bash
docker run ubuntu-sleeper sleep 10
# CMD ["sleep", "5"]가 sleep 10으로 완전히 대체됨
```

### ENTRYPOINT

```docker
FROM ubuntu
ENTRYPOINT ["sleep"]
```

컨테이너가 항상 실행할 실행 파일을 정의한다. 작성 형식은 CMD와 동일하다(shell form, exec form).

`docker run` 실행 시 동작:

- 커맨드라인 인자는 ENTRYPOINT 뒤에 **추가**된다 — 대체가 아니라 append

```bash
docker run ubuntu-sleeper 10
# 실제 실행: sleep 10
```

- 인자 누락 시 기본 인자가 없으면 ENTRYPOINT만 실행되어 에러 발생

```bash
docker run ubuntu-sleeper
# sleep: missing operand → 에러
```

- 런타임 오버라이드: `--entrypoint` 플래그로 대체 가능

```bash
docker run --entrypoint sleep2.0 ubuntu-sleeper 10
# 실제 실행: sleep2.0 10
```

### CMD + ENTRYPOINT: 기본 인자 패턴

ENTRYPOINT에 실행 파일을 고정하고, CMD로 기본 인자를 제공하는 패턴이다.

```docker
FROM ubuntu
ENTRYPOINT ["sleep"]
CMD ["5"]
```

- 인자 없이 실행 시: `sleep 5` (CMD가 기본값으로 사용됨)
- 인자를 넘길 시: `sleep 10` (CMD는 무시되고 커맨드라인 인자가 사용됨)

**반드시 exec form을 써야 한다.** `CMD`와 `ENTRYPOINT`를 함께 쓸 때 둘 다 shell form이면 `CMD`가 `ENTRYPOINT`의 인자로 결합되지 않는다.

```docker
# shell form 조합 (의도대로 동작 안 함)
FROM ubuntu

# /bin/sh -c sleep
ENTRYPOINT sleep   
  
# exec form이지만 ENTRYPOINT가 shell form이면 무시됨
CMD ["5"]       
```

ENTRYPOINT가 shell form이면 `/bin/sh -c sleep`으로 실행되어, CMD 인자가 append되지 않는다. 조합 패턴에서는 반드시 둘 다 exec form(JSON 배열)으로 작성해야 한다.

exec form 조합 과정:
1. Docker 런타임이 ENTRYPOINT 배열과 CMD 배열을 단순 연결(concatenation)
2. `["sleep"]` + `["5"]` → `["sleep", "5"]` → 실행: `sleep 5`
3. `docker run` 인자가 있으면 CMD 부분만 대체: `["sleep"]` + `["10"]` → `sleep 10`

### 동작 매트릭스

| ENTRYPOINT | CMD | docker run 인자 | 실제 실행 |
| --- | --- | --- | --- |
| 없음 | `["sleep", "5"]` | 없음 | `sleep 5` |
| 없음 | `["sleep", "5"]` | `sleep 10` | `sleep 10` |
| `["sleep"]` | 없음 | 없음 | `sleep` (에러) |
| `["sleep"]` | 없음 | `10` | `sleep 10` |
| `["sleep"]` | `["5"]` | 없음 | `sleep 5` |
| `["sleep"]` | `["5"]` | `10` | `sleep 10` |

### docker run 오버라이드 규칙 정리

```bash
# CMD 대체
docker run <image> <args>

# ENTRYPOINT 대체
docker run --entrypoint <executable> <image> <args>
```

> exec form 조합: `ENTRYPOINT ["sleep"]` + `CMD ["5"]` → Docker 런타임이 두 배열을 단순 연결: `["sleep", "5"]` → `sleep 5`. shell form ENTRYPOINT: `ENTRYPOINT sleep` → `/bin/sh -c sleep`으로 실행되어 CMD 배열이 인자로 append되지 않고 무시된다. ENTRYPOINT + CMD 조합 패턴을 쓰려면 **반드시 둘 다 exec form**이어야 한다.

</details>

## Kubernetes command와 args

Kubernetes는 Docker의 두 지시어에 대응하는 두 필드를 제공한다.

| Dockerfile | Kubernetes | 설명 |
| --- | --- | --- |
| `ENTRYPOINT` | `command` | 컨테이너에서 실행되는 실행 파일. 인자를 포함할 수도 있지만 일반적으로 실행 파일만 지정 |
| `CMD` | `args` | `ENTRYPOINT` 또는 `command`로 지정된 커맨드에 전달되는 추가 인자 |

Pod spec에서 `command`나 `args`를 지정하면 각각 이미지에 정의된 `ENTRYPOINT`와 `CMD`를 오버라이드한다.

![Kubernetes command/args와 Docker ENTRYPOINT/CMD 오버라이드 관계]({{site.url}}/assets/images/k8s-in-action-book-ref-dockerfile-override.png){: .align-center}
*출처: Kubernetes in Action 2nd Edition*


```yaml
# args만 지정: CMD 오버라이드 (ENTRYPOINT는 이미지 그대로)
apiVersion: v1
kind: Pod
metadata:
  name: kiada
spec:
  containers:
  - name: kiada
    image: kiada:0.4
    args: ["--listen-port", "9090"] # CMD ["--listen-port", "8080"] 대체
```

```yaml
# command + args 모두 지정: ENTRYPOINT와 CMD 모두 오버라이드
apiVersion: v1
kind: Pod
metadata:
  name: kiada
spec:
  containers:
  - name: kiada
    image: kiada:0.4
    command: ["node", "app.js", "--profile"] # ENTRYPOINT 대체: 프로파일링 플래그 추가
    args: ["--listen-port", "8080"] # CMD 대체
```

커맨드와 인자가 두 개의 서로 다른 Dockerfile 지시어와 Pod manifest 필드로 분리되어 있는 것은 좋은 설계다. 이 분리 덕분에 커맨드와 인자를 독립적으로 오버라이드할 수 있는 유연성을 얻게 된다.

- **인자만 교체 가능:** 커맨드를 매번 다시 지정하지 않고도 인자만 바꿔서 컨테이너 실행 가능 (= CMD만 오버라이드)
- **역방향 유연성:** 반대로 필요하면 커맨드 자체도 오버라이드 가능 (`--entrypoint` 플래그)
- **독립성:** 커맨드를 오버라이드할 때 인자를 건드리지 않아도 된다. 둘이 독립적으로 오버라이드 가능하다

> **YAML 파서 주의사항**: YAML 파서가 문자열이 아닌 다른 타입으로 해석할 수 있는 값은 반드시 따옴표로 감싸야 한다.
> - 숫자: `1234` → `"1234"`
> - 불리언: `true`, `false` → `"true"`, `"false"`
> - YAML이 불리언으로 취급하는 단어들: `yes`, `no`, `on`, `off`, `y`, `n`, `t`, `f`, `null` 등 → 모두 따옴표 필요

### 커맨드 설정 (Setting the Command)

Dockerfile을 수정하고 이미지를 다시 빌드하는 대신, Pod manifest의 `command` 필드만으로 동작을 변경할 수 있다. 이미지 자체는 변경하지 않고 Pod spec의 `command` 필드만으로 동작을 변경하는 것이므로 이미지 재빌드가 불필요하다.

`command` 필드는 Dockerfile의 ENTRYPOINT와 마찬가지로 **문자열 배열**을 받는다.

```yaml
# 인라인 배열 표기: 요소가 적을 때 적합
command: ["node", "--cpu-prof", "--heap-prof", "app.js"]
```

```yaml
# 멀티라인 표기: 요소가 많아지면 가독성을 위해 이 방식이 나음
command:
- node
- --cpu-prof
- --heap-prof
- app.js
```

kiada 컨테이너에 프로파일링을 활성화하려면 `command`를 오버라이드하면 된다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: kiada
spec:
  containers:
  - name: kiada
    image: kiada:0.4
    command: ["node", "--cpu-prof", "--heap-prof", "app.js"] # ENTRYPOINT 오버라이드: --cpu-prof, --heap-prof 플래그 추가
```

### 인자 설정 (Setting Command Arguments)

커맨드라인 인자도 파드 매니페스트에서 오버라이드할 수 있다. 컨테이너 정의의 `args` 필드를 사용한다.

- `args` 필드는 Dockerfile의 CMD에 대응하며, **문자열 배열**을 받는다
- `args`만 지정하면 이미지의 CMD만 대체되고, ENTRYPOINT는 그대로 유지된다

kiada 컨테이너의 listening port를 9090으로 변경하는 예시를 보자.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: kiada
spec:
  containers:
  - name: kiada
    image: luksa/kiada:0.4
    args: ["--listen-port", "9090"] # CMD ["--listen-port", "8080"] 대체
#   멀티라인 표기:
#     args:
#     - --listen-port
#     - "9090"
    ports:
    - name: http
      containerPort: 9090
```

Dockerfile의 ENTRYPOINT(`node app.js`)는 유지되고, CMD(`--listen-port 8080`)만 `args`로 대체된다. 즉 최종 커맨드 = ENTRYPOINT + args = `["node", "app.js"]` + `["--listen-port", "9090"]`이 된다.

### command, args 지정 시 주의사항

**`command`만 지정하고 `args`를 생략하면, 이미지의 CMD도 함께 무시된다.** Dockerfile에서 CMD로 정의한 기본 인자가 적용되지 않는다.

```yaml
# Dockerfile: ENTRYPOINT ["node", "app.js"], CMD ["--listen-port", "8080"]
spec:
  containers:
  - name: kiada
    image: luksa/kiada:0.4
    command: ["node", "--cpu-prof", "app.js"]
    # args를 생략 → 이미지의 CMD ["--listen-port", "8080"]도 무시됨
    # 최종 명령: node --cpu-prof app.js (포트 인자 없음!)
```

`command`가 ENTRYPOINT를 대체하는 순간, 이미지의 CMD는 자동으로 무효화된다. CMD에 정의된 기본 인자(`--listen-port 8080`)를 유지하려면, `args`에 명시적으로 다시 지정해야 한다.

```yaml
spec:
  containers:
  - name: kiada
    image: luksa/kiada:0.4
    command: ["node", "--cpu-prof", "app.js"]
    args: ["--listen-port", "8080"] # CMD 기본 인자를 명시적으로 유지
    # 최종 명령: node --cpu-prof app.js --listen-port 8080
```

**`command`는 ENTRYPOINT(실행 파일)를 대체하고, `args`는 CMD(인자)를 대체한다.** 이 매핑을 혼동하면 의도와 다르게 동작한다.

다른 이미지 예시를 보자. 아래 Dockerfile의 ENTRYPOINT는 `python app.py`이고, CMD는 `--color red`이다. 기본 실행 시 `python app.py --color red`가 된다.

```docker
FROM python:3.6-alpine
RUN pip install flask
COPY . /opt/
EXPOSE 8080
WORKDIR /opt
ENTRYPOINT ["python", "app.py"]
CMD ["--color", "red"]
# Docker가 구성하는 기본 명령: ["python", "app.py", "--color", "red"]
```

잘못된 예시 — `command`로 인자를 넘긴 경우:

```yaml
spec:
  containers:
  - name: simple-webapp
    image: kodekloud/webapp-color
    command: ["--color", "green"]
```

- `command`는 ENTRYPOINT를 대체하므로, 원래의 `python app.py`가 사라지고 `--color green`이 실행 명령이 된다
- `args`를 생략했으므로 이미지의 CMD(`["--color", "red"]`)도 함께 무시된다
- 최종 명령은 `--color green`뿐 → `--color`라는 실행 파일은 없으므로 컨테이너 시작이 실패한다

올바른 수정 — `args`로 CMD만 대체:

```yaml
spec:
  containers:
  - name: simple-webapp
    image: kodekloud/webapp-color
    args: ["--color", "green"]
    # → python app.py --color green
```

`args`는 CMD만 대체하므로 ENTRYPOINT(`python app.py`)는 유지된다. 최종 명령은 `python app.py --color green`이 된다.

<br>

# 환경 변수 설정

컨테이너화된 어플리케이션은 환경 변수를 이용해 설정하는 경우가 많다. 커맨드와 인자처럼, 환경 변수도 파드 내 각 컨테이너 별로 설정할 수 있다.

![환경 변수가 컨테이너 단위로 설정되는 구조]({{site.url}}/assets/images/k8s-in-action-book-ref-dockerfile-env-container.png){: .align-center}
*출처: Kubernetes in Action 2nd Edition*

환경 변수는 **컨테이너 단위로만 설정 가능**하다. 파드 전체에 공통 환경 변수를 설정하고 모든 컨테이너가 상속받는 방식은 지원되지 않는다.

<details markdown="1">
<summary><b>왜 컨테이너 단위로만 지원되는가</b></summary>

기술적으로 어려운 건 아니지만, 설계 철학에 의한 의도적 선택이다. Kubernetes는 `spec.containers[].env`에 정의된 값을 kubelet이 컨테이너 런타임에 전달하는 방식이므로, `spec.env` 같은 파드 레벨 필드를 만드는 것도 가능은 하다. 하지만 굳이 하지 않는 이유가 있다.

1. **컨테이너 = 독립된 프로세스**: 환경 변수는 Linux에서 **프로세스 단위** 개념이다. 각 컨테이너는 독립된 프로세스이므로, 환경도 독립적으로 정의하는 게 자연스럽다
2. **Explicit over implicit**: 파드 안의 컨테이너들은 역할이 다르다 (앱 컨테이너 vs. envoy 사이드카 vs. init 컨테이너). 파드 레벨 env가 있으면 envoy 사이드카에 `DATABASE_PASSWORD`가 들어가는 식의 **불필요한 노출**이 생길 수 있다. 컨테이너마다 명시적으로 선언하면 "이 컨테이너에 정확히 뭐가 들어가는지"가 매니페스트만 보면 명확하다
3. **OCI 스펙과의 정합성**: 컨테이너 런타임(containerd, CRI-O)은 OCI 스펙을 따르고, OCI 스펙에서 env는 컨테이너 단위다. Kubernetes가 파드 레벨 env를 추가하면 결국 kubelet이 merge 로직을 구현해야 하는데, 이때 **우선순위 규칙**(파드 레벨 vs 컨테이너 레벨 충돌 시 어느 쪽이 이기는지)이 복잡해지고 혼란스러워진다
4. **이미 대안이 있음**: 여러 컨테이너에 같은 환경 변수를 넣고 싶으면 **ConfigMap + `envFrom`**으로 같은 ConfigMap을 각 컨테이너에 참조하면 된다. 중복은 있지만, 명시적이고 선택적이다

실제로 **PodPreset**이라는 기능이 alpha로 존재했었는데 (v1.11~v1.19), 특정 파드에 `env`, `volume`, `volumeMount`를 자동 주입하는 기능이었다. 사용률 저조와 설계 문제로 v1.20에서 제거되었다.

</details>

환경 변수의 소스는 세 가지다.

1. **리터럴 값:** 직접 값을 지정
2. **다른 환경 변수 참조:** 이미 정의된 환경 변수를 참조 → inline, `command`/`args`
3. **외부 소스:** ConfigMap, Secret 등에서 값을 가져옴

## 리터럴 값으로 설정

컨테이너 정의의 `env` 필드를 사용하여 환경 변수를 설정한다. `env` 필드는 `name`과 `value` 쌍의 리스트를 받는다.

kiada 0.4 어플리케이션은 `POD_NAME` 환경 변수에서 파드 이름을, `INITIAL_STATUS_MESSAGE`에서 상태 메시지를 읽는다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: kiada
spec:
  containers:
  - name: kiada
    image: luksa/kiada:0.4
    env:
    - name: POD_NAME
      value: kiada
    - name: INITIAL_STATUS_MESSAGE
      value: This status message is set in the pod spec.
    ports:
    - name: http
      containerPort: 8080
```

파드 매니페스트에 정의된 환경 변수 목록을 확인하려면 다음과 같이 할 수 있다.

```bash
# set env는 환경 변수 설정 커맨드이지만, --list 플래그를 붙이면 조회 모드로 동작
# 컨테이너 내부의 실제 변수가 아닌 매니페스트에 선언된 것만 표시
kubectl set env pod kiada --list
```

컨테이너 내부 실제 환경 변수 전체를 확인하려면 `exec`를 사용한다.

```bash
kubectl exec kiada -- env

# 실행 결과
# 시스템이 설정
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
HOSTNAME=kiada
# 컨테이너 이미지에서 설정
NODE_VERSION=12.19.1
YARN_VERSION=1.22.5
# 파드 매니페스트에서 설정
POD_NAME=kiada
INITIAL_STATUS_MESSAGE=This status message is set in the pod spec.
# 쿠버네티스가 자동 설정 (Service 관련 — 11장에서 다룸)
KUBERNETES_SERVICE_HOST=10.96.0.1
...
KUBERNETES_SERVICE_PORT=443
```

환경 변수의 출처는 크게 네 가지다.

1. **시스템:** `PATH`, `HOSTNAME` 등 OS/런타임이 설정
2. **컨테이너 이미지:** Dockerfile의 `ENV`로 설정 (`NODE_VERSION`, `YARN_VERSION` 등)
3. **파드 매니페스트:** `env` 필드에서 직접 설정 (`POD_NAME`, `INITIAL_STATUS_MESSAGE`)
4. **쿠버네티스:** Service 객체 관련 변수를 자동 주입 (`KUBERNETES_SERVICE_HOST` 등)

각 변수의 출처를 확인하려면 파드 매니페스트와 컨테이너 이미지의 Dockerfile을 함께 확인해야 한다.

## 다른 환경 변수 참조

환경 변수 값에 다른 환경 변수를 참조할 수 있다. `$(VAR_NAME)` 구문을 사용한다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: kiada
spec:
  containers:
  - name: kiada
    image: luksa/kiada:0.4
    env:
    - name: POD_NAME
      value: kiada
    - name: INITIAL_STATUS_MESSAGE
      value: My name is $(POD_NAME). I run NodeJS version $(NODE_VERSION).
    ports:
    - name: http
      containerPort: 8080
```

- `POD_NAME`: 같은 매니페스트에 정의되어 있으므로 `kiada`로 정상 치환된다
- `NODE_VERSION`: 이미지의 Dockerfile에서 `ENV`로 설정된 변수이므로 **치환되지 않고 문자열 그대로 남는다**

### $(VAR_NAME) 참조 규칙

**같은 매니페스트에 정의된 변수만 참조 가능하다.** 이미지의 `ENV`나 시스템 변수는 참조할 수 없다.

```yaml
# Dockerfile: ENV NODE_VERSION=12.19.1
env:
- name: MSG
  value: "NodeJS $(NODE_VERSION)" # NODE_VERSION은 이미지 ENV → 치환 안 됨
# 결과: MSG = "NodeJS $(NODE_VERSION)" (문자열 그대로)
```

**참조 대상이 먼저 정의되어 있어야 한다.** `env` 리스트에서 참조 대상이 참조하는 변수보다 위에 위치해야 한다.

```yaml
env:
- name: GREETING
  value: "Hello $(USERNAME)" # USERNAME이 아래에 정의됨 → 치환 안 됨
- name: USERNAME
  value: kiada
# 결과: GREETING = "Hello $(USERNAME)" (문자열 그대로)
```

```yaml
# 올바른 순서
env:
- name: USERNAME
  value: kiada
- name: GREETING
  value: "Hello $(USERNAME)" # USERNAME이 위에 정의됨 → 정상 치환
# 결과: GREETING = "Hello kiada"
```

**해석 불가 시 문자열 그대로 유지된다.** 참조를 resolve할 수 없으면 `$(VAR_NAME)` 문자열이 그대로 남는다.

```yaml
env:
- name: MSG
  value: "Pod is $(POD_NAME)" # POD_NAME이 env에 정의되지 않음
# 결과: MSG = "Pod is $(POD_NAME)" (문자열 그대로)
```

**리터럴 `$(VAR_NAME)`을 값으로 사용하려면** `$$(VAR_NAME)`으로 작성한다. 쿠버네티스가 `$` 하나를 제거하고 변수 치환을 건너뛴다.

```yaml
env:
- name: POD_NAME
  value: kiada
- name: TEMPLATE
  value: "Use $$(POD_NAME) syntax" # $$ → 변수 치환 건너뜀
# 결과: TEMPLATE = "Use $(POD_NAME) syntax" (리터럴 문자열)
```

## command/args에서 환경 변수 참조

매니페스트에 정의된 환경 변수를 다른 환경 변수뿐만 아니라 `command`와 `args` 필드에서도 `$(VAR_NAME)` 구문으로 참조할 수 있다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: kiada
spec:
  containers:
  - name: kiada
    image: luksa/kiada:0.4
    args:
    - --listen-port
    - $(LISTEN_PORT) # env에 정의된 LISTEN_PORT를 참조
    env:
    - name: LISTEN_PORT
      value: "8080"
    ports:
    - name: http
      containerPort: 8080
```

이 예시 자체는 포트 번호를 직접 `args`에 쓰는 것과 차이가 없다. 하지만 나중에 ConfigMap/Secret 등 외부 소스에서 환경 변수 값을 가져오게 되면, 이 참조 패턴으로 외부 설정 값을 `command`/`args`에 주입할 수 있다.

## 매니페스트에 없는 환경 변수 참조

`$(VAR_NAME)` 구문은 `command`/`args` 필드에서도 매니페스트에 정의된 변수만 참조할 수 있다. 이미지나 OS가 설정한 변수는 참조할 수 없다. 매니페스트에 없는 변수를 참조하려면 셸을 통해 커맨드를 실행하는 방식을 사용한다.

- `$(VAR_NAME)` — 쿠버네티스가 파드 생성 시점에 치환 (매니페스트 변수만 가능)
- `$VAR_NAME` 또는 `${VAR_NAME}` — 셸이 런타임에 치환 (이미지/OS 변수도 가능)
- 괄호 `()` vs 중괄호 `{}`의 차이에 주의하자

`HOSTNAME`은 OS가 설정하는 변수이므로 `$(HOSTNAME)`으로는 참조할 수 없다. 셸을 통해 `$HOSTNAME`으로 참조해야 한다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: env-var-references-in-shell
spec:
  containers:
  - name: main
    image: alpine
    command:
    - sh
    - -c
    - 'echo "Hostname is $HOSTNAME."; sleep infinity' # 셸이 $HOSTNAME을 런타임에 치환
```

`sh -c`로 실행하면 셸 프로세스가 커맨드 문자열을 해석하므로, 셸의 변수 치환(`$VAR_NAME`)이 동작한다. exec form으로 직접 실행하면 셸을 거치지 않으므로 `$VAR_NAME` 구문이 치환되지 않는다.

<br>

# 참고: 파드의 FQDN 설정

파드의 hostname과 subdomain은 파드 매니페스트에서 설정할 수 있다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: kiada-hostname
spec:
  hostname: custom-hostname
  subdomain: custom-subdomain
  containers:
  - name: kiada
    image: luksa/kiada:0.4
    ports:
    - name: http
      containerPort: 8080
```

- 기본적으로 hostname은 파드 이름과 동일하다
- `hostname` 필드로 오버라이드할 수 있다
- `subdomain` 필드를 설정하면 파드의 FQDN이 구성된다: `<hostname>.<subdomain>.<namespace>.svc.<cluster-domain>`
  - 이 FQDN은 파드 내부 전용이며, DNS로 resolve하려면 추가 설정이 필요하다

```bash
# hostname 설정된 파드에서 FQDN 확인
kubectl exec kiada-hostname -- hostname -f
custom-hostname.custom-subdomain.default.svc.cluster.local

# 기존 파드 hostname 확인
kubectl exec kiada -- hostname -f
kiada

# DNS는 동작하지 않음
kubectl exec kiada -- nslookup custom-hostname.custom-subdomain.default.svc.cluster.local

# 실행 결과
Server:         10.96.0.10
Address:        10.96.0.10:53

** server can't find custom-hostname.custom-subdomain.default.svc.cluster.local: NXDOMAIN
command terminated with exit code 1
```

<br>

# 정리

- Docker의 `ENTRYPOINT`는 Kubernetes의 `command`, `CMD`는 `args`에 대응한다. Pod spec에서 이 필드를 지정하면 이미지에 정의된 값을 오버라이드한다
- `command`만 지정하고 `args`를 생략하면 이미지의 CMD도 함께 무시된다. 필요한 인자는 `args`에 명시적으로 지정해야 한다
- 환경 변수는 컨테이너 단위로만 설정 가능하다. 리터럴 값, 다른 환경 변수 참조(`$(VAR_NAME)`), 외부 소스(ConfigMap, Secret) 참조 세 가지 방식을 지원한다
- `$(VAR_NAME)` 구문은 같은 매니페스트에 정의된 변수만 참조할 수 있다. 참조 대상이 먼저 정의되어 있어야 하고, resolve 불가 시 문자열 그대로 남는다
- 이미지/OS가 설정한 변수를 참조하려면 `sh -c`로 셸을 통해 커맨드를 실행하고 `$VAR_NAME` 구문을 사용해야 한다
- `$$(VAR_NAME)` 구문으로 리터럴 `$(VAR_NAME)` 문자열을 값에 넣을 수 있다

<br>

*다음 포스트: [어플리케이션 설정 - 2. ConfigMap]({% post_url 2026-04-05-Kubernetes-Application-Config-02-ConfigMap %})*

<br>