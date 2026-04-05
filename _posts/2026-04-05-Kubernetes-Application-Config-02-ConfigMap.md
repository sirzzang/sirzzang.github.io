---
title:  "[Kubernetes] 어플리케이션 설정 - 2. ConfigMap"
excerpt: "ConfigMap을 이용해 설정 데이터를 파드에서 분리하고 환경 변수로 주입하는 방법을 알아보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubernetes-in-Action-2nd
  - ConfigMap
  - envFrom
  - configMapKeyRef
  - environment-variable
  - immutable
hidden: true
---

*[Kubernetes in Action 2nd Edition](https://www.manning.com/books/kubernetes-in-action-second-edition) 8장의 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- ConfigMap은 설정 데이터를 파드 매니페스트에서 분리하여 별도 오브젝트로 관리하는 Kubernetes API 오브젝트다
- `configMapKeyRef`로 단일 항목을, `envFrom`으로 전체 항목을 환경 변수로 주입할 수 있다. 일반적으로 ConfigMap은 `envFrom`, Secret은 `env[].valueFrom`을 사용한다
- 환경 변수로 주입된 ConfigMap은 컨테이너 재시작 전까지 반영되지 않지만, 볼륨 마운트 방식은 자동 반영된다
- `immutable: true`로 ConfigMap 변경을 방지하여 설정 일관성과 API 서버 부하 감소를 도모할 수 있다

<br>

# ConfigMap 소개

[이전 포스트]({% post_url 2026-04-05-Kubernetes-Application-Config-01-Command-Args-Env %})에서는 설정값을 파드 매니페스트에 직접 하드코딩하는 방법을 다뤘다. 컨테이너 이미지에 하드코딩하는 것보다는 낫지만, 환경(개발/스테이징/프로덕션)마다 별도의 매니페스트를 관리해야 한다는 한계가 있다.

여러 환경에서 동일한 파드 정의를 재사용하려면, 설정을 매니페스트에서 분리하는 것이 좋다. 이를 위해 설정값을 **ConfigMap** 오브젝트에 저장하고, 파드에서 이를 참조하는 방식을 사용한다.

ConfigMap은 **키-값 쌍의 목록**을 담는 쿠버네티스 API 오브젝트다.

- 값은 짧은 문자열부터 설정 파일 수준의 긴 구조화된 텍스트까지 가능하다
- 파드는 ConfigMap의 키-값 항목을 하나 이상 참조할 수 있다
- 하나의 파드가 여러 ConfigMap을 참조할 수 있고, 여러 파드가 동일한 ConfigMap을 공유할 수 있다

애플리케이션이 쿠버네티스에 종속되지 않도록, 보통 Kubernetes REST API로 ConfigMap을 직접 읽지 않는다. 대신 ConfigMap의 키-값 쌍을 다음 두 가지 방식으로 컨테이너에 전달한다.

- **환경 변수**로 전달
- **configMap 볼륨**을 통해 컨테이너 파일시스템에 파일로 마운트

[이전 포스트]({% post_url 2026-04-05-Kubernetes-Application-Config-01-Command-Args-Env %})에서 배운 환경 변수 참조 기법을 활용하면, ConfigMap 항목을 환경 변수로 노출한 뒤 커맨드라인 인수에 전달할 수도 있다.

ConfigMap을 사용하면 설정을 파드가 아닌 별도 오브젝트에 저장하므로, 환경별로 별도의 ConfigMap 매니페스트를 유지하기만 하면 된다. 파드는 ConfigMap을 **이름으로 참조**하기 때문에, 동일한 파드 매니페스트를 모든 환경에 배포하면서도 환경별로 다른 설정을 적용할 수 있다.

<br>

# ConfigMap 생성

## kubectl create configmap

명령형 커맨드 `kubectl create configmap`을 사용하면 ConfigMap을 빠르게 생성할 수 있다.

```bash
# ConfigMap 생성: --from-literal로 키-값 쌍 지정
kubectl create configmap kiada-config \
	--from-literal staus-message="This status message is set in the kiada-config ConfigMap"

# 실행 결과
# configmap/kiada-config created
```

ConfigMap의 키는 영숫자, 대시(`-`), 밑줄(`_`), 점(`.`)만 허용된다. 위 커맨드는 `kiada-config`이라는 ConfigMap 오브젝트를 생성하며, 키와 값은 `--from-literal` 인수로 지정한다.

`--from-literal` 외에도 파일에서 키-값 쌍을 가져올 수 있다. 아래 표는 사용 가능한 방법을 정리한 것이다.

| 방법 | 설명 |
| --- | --- |
| `--from-literal` | 키와 리터럴 값을 ConfigMap에 삽입 (예: `--from-literal mykey=myvalue`) |
| `--from-file` | 파일 내용을 ConfigMap에 삽입. 인수에 따라 동작이 달라짐. 파일명만 지정하면 파일 기본 이름이 키가 되고, `key=file` 형식이면 지정한 키에 파일 내용이 저장되며, 디렉터리 지정 시 각 파일이 개별 항목으로 포함된다(서브디렉터리, 심볼릭 링크 등은 무시) |
| `--from-env-file` | 지정한 파일의 각 줄을 개별 항목으로 삽입 (예: `--from-env-file myfile.env`). 파일은 `key=value` 형식이어야 함 |

<details markdown="1">
<summary><b>--from-file의 동작 원리: 파일 내용을 통째로 하나의 값으로 넣는다</b></summary>

**1. 파일명만 지정: `--from-file <파일>`**

```bash
# 테스트 파일 생성
echo '{"port": 8080, "debug": true}' > /tmp/config.json

# ConfigMap 생성 (파일명이 키가 됨)
kubectl create configmap fromfile-test1 --from-file /tmp/config.json

# 실행 결과
# configmap/fromfile-test1 created
```

```bash
# 결과 확인: data 항목 아래에 파일명 config.json이 키가 됨
kubectl get configmap fromfile-test1 -o yaml

# 실행 결과
# apiVersion: v1
# data:
#   config.json: |
#     {"port": 8080, "debug": true}
# kind: ConfigMap
# metadata:
#   creationTimestamp: "2026-03-30T16:00:33Z"
#   name: fromfile-test1
#   namespace: default
#   resourceVersion: "2201"
#   uid: 202ebc8b-b83d-4323-b80b-8ea7e4276ff1
```

```bash
# 정리
kubectl delete configmap fromfile-test1
```

**2. 키를 직접 지정: `--from-file <키>=<파일>`**

```bash
# ConfigMap 생성 (키를 app-config으로 직접 지정)
kubectl create configmap fromfile-test2 --from-file app-config=/tmp/config.json

# 실행 결과
# configmap/fromfile-test2 created
```

```bash
# 결과 확인: 파일명 대신 원하는 키 이름을 쓸 수 있음
kubectl get configmap fromfile-test2 -o yaml

# 실행 결과
# apiVersion: v1
# data:
#   app-config: |
#     {"port": 8080, "debug": true}
# kind: ConfigMap
# metadata:
#   creationTimestamp: "2026-03-30T16:01:55Z"
#   name: fromfile-test2
#   namespace: default
#   resourceVersion: "2309"
#   uid: bc2f351e-717c-4ab4-8faf-b42916017595
```

```bash
# 정리
kubectl delete configmap fromfile-test2
```

**3. 디렉터리 지정: `--from-file <디렉터리>/`**

```bash
# 테스트 디렉터리 구성
mkdir -p /tmp/config-dir/subdir
echo "listen 80;" > /tmp/config-dir/app.conf
echo "host=localhost" > /tmp/config-dir/db.conf
echo "ignored" > /tmp/config-dir/subdir/nested.conf
ln -s /tmp/config-dir/app.conf /tmp/config-dir/app-link.conf
```

```bash
# 디렉터리 구조 확인
ls -la /tmp/config-dir/

# 실행 결과
# app.conf          ← 일반 파일
# app-link.conf -> /tmp/config-dir/app.conf  ← 심볼릭 링크
# db.conf           ← 일반 파일
# subdir/           ← 서브디렉터리
```

```bash
# ConfigMap 생성
kubectl create configmap fromfile-test3 --from-file /tmp/config-dir/

# 실행 결과
# configmap/fromfile-test3 created
```

```bash
# 결과 확인: 일반 파일만 포함됨
kubectl get configmap fromfile-test3 -o yaml

# 실행 결과
# apiVersion: v1
# data:
#   app.conf: |
#     listen 80;
#   db.conf: |
#     host=localhost
# kind: ConfigMap
# ...
# (심볼릭 링크 app-link.conf → 무시됨)
# (서브디렉터리 subdir/nested.conf → 무시됨)
```

```bash
# 정리
kubectl delete configmap fromfile-test3
rm -rf /tmp/config-dir /tmp/config.json
```

디렉터리 안의 **일반 파일만** 각각 하나의 키-값 항목이 된다. 서브디렉터리(`subdir/`), 심볼릭 링크(`app-link.conf`)는 무시된다.

</details>

ConfigMap 생성 시 보통 여러 항목을 포함한다.

- `--from-literal`, `--from-file`, `--from-env-file` 인수를 여러 번 반복 가능
- `--from-literal`과 `--from-file`은 자유롭게 조합하여 사용 가능
- `--from-env-file`은 단독으로만 사용해야 함 (다른 인수와 함께 사용 시 오류 발생)

<details markdown="1">
<summary><b>인수 조합 규칙에 따른 동작 원리</b></summary>

**1. `--from-literal` 여러 번 반복**

```bash
# 여러 리터럴 값으로 ConfigMap 생성
kubectl create configmap multi-literal \
	--from-literal env=production \
	--from-literal debug=false \
	--from-literal version=2.1.0

# 결과 확인
kubectl get configmap multi-literal -o yaml
# data:
#   debug: "false"
#   env: production
#   version: 2.1.0

# 정리
kubectl delete configmap multi-literal
```

**2. `--from-literal` + `--from-file` 함께 사용 (허용)**

```bash
# 테스트 파일 생성
echo '{"port": 8080}' > /tmp/app.json

# literal과 file 조합으로 ConfigMap 생성
kubectl create configmap mixed-config \
	--from-literal env=production \
	--from-literal debug=false \
	--from-file /tmp/app.json

# 결과 확인: literal과 file 항목이 모두 포함됨
kubectl get configmap mixed-config -o yaml
# data:
#   app.json: '{"port": 8080}'
#   debug: "false"
#   env: production

# 정리
kubectl delete configmap mixed-config
```

**3. `--from-env-file` 사용**

```bash
# env 파일 생성
cat > /tmp/app.env << 'EOF'
DB_HOST=localhost
DB_PORT=5432
LOG_LEVEL=info
EOF

# env 파일에서 ConfigMap 생성
kubectl create configmap env-config \
	--from-env-file /tmp/app.env

# 결과 확인: 파일의 각 줄이 개별 키-값 항목이 됨
kubectl get configmap env-config -o yaml
# data:
#   DB_HOST: localhost
#   DB_PORT: "5432"
#   LOG_LEVEL: info

# 정리
kubectl delete configmap env-config
```

**4. `--from-env-file` + `--from-literal` 함께 사용 (오류)**

```bash
# --from-env-file과 --from-literal을 함께 사용하면 오류 발생
kubectl create configmap bad-config \
	--from-env-file /tmp/app.env \
	--from-literal extra=value
# error: from-env-file cannot be combined with from-file or from-literal
```

**5. `--from-env-file` + `--from-file` 함께 사용 (오류)**

```bash
# --from-env-file과 --from-file을 함께 사용해도 오류 발생
kubectl create configmap bad-config2 \
	--from-env-file /tmp/app.env \
	--from-file /tmp/app.json
# error: from-env-file cannot be combined with from-file or from-literal

# 정리
rm /tmp/app.json /tmp/app.env
```

</details>

## YAML 매니페스트로 생성

ConfigMap은 YAML 매니페스트 파일로도 생성할 수 있다. 아래와 같은 매니페스트를 작성한 뒤 `kubectl apply`로 적용한다.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: kiada-config # ConfigMap 이름
data: # ConfigMap key-value pairs
  status-message: "This status message is set in the kiada-config config map"
```

## 파일에서 생성 (--dry-run)

`kubectl create configmap` 커맨드에 `--dry-run=client` 옵션을 사용하면 실제로 API 서버에 오브젝트를 생성하지 않고 **오브젝트 정의만 생성**할 수 있다.

```bash
# 텍스트 파일과 바이너리 파일 조합하여 ConfigMap 매니페스트 생성
kubectl create configmap dummy-config \
	--from-file=dummy.txt \
	--from-file=dummy.bin \
	--dry-run=client -o yaml > dummy-configmap.yaml
```

`-o yaml` 옵션으로 YAML 형식을 표준 출력에 출력하고, 이를 파일로 리다이렉트한다. 생성된 ConfigMap을 확인하면 파일 2개가 각각 하나의 항목으로 저장되어 있다. `kubectl`은 파일 내용을 분석하여 **저장 위치를 자동으로 결정**한다.

```yaml
apiVersion: v1
binaryData: # 바이트 시퀀스 → Base64 인코딩
  dummy.bin: n2VW39IEkyQ6Jxo+rdo5J06Vi7cz5X...
data: # 평문 그대로 저장
  dummy.txt: |-
    This is a text file with multiple lines
    that you can use to test the creation of
    a ConfigMap in Kubernetes. 
kind: ConfigMap
metadata:
  name: dummy-config
```

- `data`: UTF-8 텍스트로 읽을 수 있는 파일이 평문 그대로 저장된다
- `binaryData`: UTF-8이 아닌 바이트 시퀀스가 포함된 파일이 Base64로 인코딩되어 저장된다. YAML/JSON은 바이너리 데이터를 직접 표현할 수 없으므로 Base64 인코딩이 필요하다
- `kubectl`이 자동으로 `data`와 `binaryData`를 구분하므로, 사용자가 직접 판단할 필요 없다
- 실무에서는 대부분 텍스트 설정 파일을 다루므로 `data` 필드만 사용하게 된다

> ConfigMap 매니페스트를 파일에서 생성할 때, 파일의 각 줄 끝에 **불필요한 공백(trailing whitespace)**이 없는지 확인해야 한다. 줄 끝에 공백이 있으면 ConfigMap 항목이 따옴표로 감싸진 문자열(quoted string)로 포맷되어 가독성이 크게 떨어진다.

```bash
# 줄 끝에 공백이 있는 파일 vs 없는 파일 비교
kubectl create configmap dummy-config \
  --from-file=dummy.yaml \
  --from-file=dummy-bad.yaml \
  --dry-run=client -o yaml

# 실행 결과
# apiVersion: v1
# data:
#   # 줄 끝에 공백이 있는 파일 → quoted string으로 포맷됨 (가독성 나쁨)
#   dummy-bad.yaml: "dummy: \\n  name: dummy-bad.yaml\\n  note: This\n    ..."
#
#   # 줄 끝에 공백이 없는 파일 → 깔끔한 멀티라인 문자열
#   dummy.yaml: |
#     dummy:
#       name: dummy.yaml
#       note: This file is correctly formatted with no trailing spaces.
```

- `dummy-bad.yaml`: 첫 번째 줄 끝에 불필요한 공백이 있어 `\n` 이스케이프가 포함된 한 줄 문자열로 출력된다
- `dummy.yaml`: 공백 없이 깔끔하게 작성되어 `|` (파이프라인) 기호를 사용한 멀티라인 문자열로 출력된다

<br>

# ConfigMap 환경 변수 주입

## 단일 항목 주입: configMapKeyRef

ConfigMap의 특정 항목 하나를 환경 변수로 주입하려면, 환경 변수 정의에서 `value` 필드 대신 `valueFrom` 필드를 사용하여 ConfigMap 항목을 참조한다.

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
      # 고정 값 대신 ConfigMap 키에서 값을 가져옴
      valueFrom:
        configMapKeyRef:
          name: kiada-config       # ConfigMap 이름
          key: status-message      # ConfigMap 내의 키
          optional: true           # ConfigMap 또는 키가 없어도 컨테이너 실행 가능
    ports:
    - name: http
      containerPort: 8080
```

- `valueFrom.configMapKeyRef`로 ConfigMap을 참조한다
  - `name`: 참조할 ConfigMap 이름
  - `key`: ConfigMap 내의 키
  - `optional`: `true`로 설정하면 ConfigMap이나 키가 없어도 컨테이너가 실행된다

```bash
# 파드 생성 및 환경 변수 확인
kubectl apply -f pod.kiada.env-valueFrom.yaml

# 실행 결과
# pod/kiada created

kubectl exec kiada -- env

# 실행 결과 (주요 부분)
# INITIAL_STATUS_MESSAGE=This is the default status message
# POD_NAME=kiada
# HOSTNAME=kiada
```

> ConfigMap 참조가 `optional`로 표시되지 않은 경우, 참조된 ConfigMap이나 키가 없으면 해당 컨테이너만 시작이 차단된다. 파드 자체는 정상적으로 스케줄링되고, 다른 컨테이너는 정상 시작된다. 해당 ConfigMap을 생성하면 차단된 컨테이너가 시작된다.

## 전체 항목 주입: envFrom

`env` 필드로 항목을 하나씩 지정하는 대신, `envFrom` 필드를 사용하면 ConfigMap의 **모든 항목을 한 번에** 환경 변수로 주입할 수 있다.

- `env`: 항목별로 키를 지정하여 환경 변수 이름을 자유롭게 매핑 가능
- `envFrom`: ConfigMap의 키가 그대로 환경 변수 이름이 됨 → 키 이름이 환경 변수 형식에 맞아야 한다
  - 키 이름 변환은 접두사(prefix) 추가만 가능
  - 예: ConfigMap 키가 `status-message`이면 어플리케이션이 `INITIAL_STATUS_MESSAGE`를 기대하는 경우, 키 이름 자체를 변경해야 한다

`envFrom`을 사용하기 전에, 기존 ConfigMap의 키 이름을 환경 변수 형식에 맞게 변경한 새 매니페스트로 교체해야 한다.

```bash
# 기존 kiada-config을 envFrom에 맞는 키 이름으로 교체
kubectl replace -f cm.kiada-config.envFrom.yaml

# 실행 결과
# configmap/kiada-config replaced

# 확인
kubectl get configmap kiada-config -o yaml

# 실행 결과
# apiVersion: v1
# data:
#   ANOTHER_CONFIG_MAP_ENTRY: This is another entry in the kiada-config ConfigMap.
#   INITIAL_STATUS_MESSAGE: This status message is set in the kiada-config ConfigMap.
#   YET_ANOTHER_ENTRY: This is yet another entry in the kiada-config ConfigMap.
# kind: ConfigMap
# ...
```

`replace`는 기존 오브젝트를 삭제하고 새 매니페스트로 교체하는 커맨드다. 대상이 존재하지 않으면 `NotFound` 에러가 발생한다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: kiada
spec:
  containers:
  - name: kiada
    image: luksa/kiada:0.4
    envFrom:
    - configMapRef:
        name: kiada-config   # 주입할 ConfigMap 이름 (키 지정 없이 전체 주입)
        optional: true       # ConfigMap이 없어도 컨테이너 실행 가능
    ports:
    - name: http
      containerPort: 8080
```

- `configMapRef`에는 ConfigMap 이름만 지정하고, 개별 키는 지정하지 않는다 → ConfigMap의 모든 키-값 쌍이 환경 변수로 주입된다
- `configMapKeyRef`와 마찬가지로 `optional` 설정이 가능하다
- `optional`이 아닌 경우(기본값), 참조된 ConfigMap이 존재할 때까지 컨테이너 시작이 차단된다

```bash
# 파드 생성 후 환경변수 확인
kubectl exec kiada -- env

# 실행 결과 (주요 부분)
# INITIAL_STATUS_MESSAGE=This status message is set in the kiada-config ConfigMap.
# ANOTHER_CONFIG_MAP_ENTRY=This is another entry in the kiada-config ConfigMap.
# YET_ANOTHER_ENTRY=This is yet another entry in the kiada-config ConfigMap.
```

`configMapKeyRef`로 단일 항목만 주입했을 때는 `INITIAL_STATUS_MESSAGE`만 있었지만, `envFrom`으로 전체 주입하면 `ANOTHER_CONFIG_MAP_ENTRY`, `YET_ANOTHER_ENTRY` 등 ConfigMap의 모든 키가 환경 변수로 들어온다.

## 여러 ConfigMap 주입과 접두사

`envFrom` 필드는 리스트를 받으므로, 여러 ConfigMap의 항목을 조합할 수 있다.

- 두 ConfigMap에 동일한 키가 있으면 마지막에 지정된 ConfigMap이 우선한다
- `envFrom`과 `env`를 함께 사용할 수 있다: 하나의 ConfigMap은 전체 주입, 다른 ConfigMap은 특정 항목만 주입
- `env` 필드에 설정된 환경 변수가 `envFrom`으로 설정된 환경 변수보다 우선한다

각 ConfigMap에 선택적 접두사(prefix)를 설정할 수도 있다. 항목이 컨테이너 환경에 주입될 때, 접두사가 각 키 앞에 추가되어 환경 변수 이름이 된다.

```yaml
envFrom:
- configMapRef:
    name: kiada-config
  prefix: CONFIG_    # 접두사 설정
```

- ConfigMap의 키가 `INITIAL_STATUS_MESSAGE`이면, 환경 변수 이름은 `CONFIG_INITIAL_STATUS_MESSAGE`가 된다
- 여러 ConfigMap을 주입할 때 키 충돌을 방지하는 데 유용하다
- 접두사를 생략하면 ConfigMap의 키가 그대로 환경 변수 이름이 된다

<br>

# envFrom vs env[].valueFrom 비교

ConfigMap이나 Secret의 환경 변수 주입 방식은 `envFrom`(전체 주입)과 `env[].valueFrom`(단일 주입)으로 나뉜다.

- `envFrom.configMapRef` / `envFrom.secretRef`: ConfigMap이나 Secret의 모든 키-값 쌍을 한 번에 환경 변수로 주입
- `env[].valueFrom.configMapKeyRef` / `env[].valueFrom.secretKeyRef`: ConfigMap이나 Secret에서 특정 키 하나만 골라서 환경 변수로 주입

성능 차이는 무시할 수 있다. 환경 변수는 컨테이너 프로세스 시작 시 메모리에 한 번 로드되고, ConfigMap/Secret 자체가 최대 1MB 제한이 있어서 환경 변수 수백 개가 들어가도 메모리/CPU 오버헤드는 미미하다. 핵심적인 차이는 **운영/보안/가독성** 관점에서 나타난다.

| 관점 | `envFrom` (전체 주입) | `env[].valueFrom` (단일 주입) |
| --- | --- | --- |
| **명시성** | 어떤 환경 변수가 주입되는지 매니페스트만 보면 알기 어려움 | 정확히 어떤 키를 어떤 이름으로 쓰는지 명확함 |
| **이름 충돌** | ConfigMap 키가 그대로 환경 변수 이름이 되어, 다른 ConfigMap이나 시스템 변수와 충돌 가능 | 환경 변수 이름을 직접 지정하므로 충돌 방지 |
| **불필요한 노출** | Secret을 전체 주입하면, 컨테이너가 필요로 하지 않는 민감 데이터까지 환경에 노출 | 필요한 것만 노출하므로 최소 권한 원칙에 부합 |
| **관리 편의성** | ConfigMap 키가 많고 대부분 필요할 때 편리 | 키가 많으면 매니페스트가 장황해짐 |
| **키 이름 매핑** | ConfigMap 키가 그대로 환경 변수 이름이 됨 (prefix만 추가 가능) | 환경 변수 이름을 자유롭게 지정 가능 |

**유스케이스별 선택 기준:**

- **`envFrom`이 적합한 경우**: ConfigMap에 담긴 키-값 쌍이 대부분 또는 전부 해당 컨테이너에 필요하고, 환경 변수 이름이 ConfigMap 키 이름과 동일해도 괜찮을 때. 예를 들어, 앱 전용 설정 ConfigMap(`APP_PORT`, `APP_LOG_LEVEL`, `APP_DEBUG` 등)을 통째로 주입하는 경우
- **`env[].valueFrom`이 적합한 경우**: ConfigMap/Secret에서 일부 키만 필요하거나, 환경 변수 이름을 ConfigMap 키와 다르게 매핑해야 할 때(예: ConfigMap 키는 `db-password`인데 앱은 `DATABASE_PASSWORD`를 기대). Secret인 경우에는 필요한 키만 노출하는 것이 보안상 안전하다

> ConfigMap은 `envFrom`으로 편하게 쓰되, Secret은 `env[].valueFrom`으로 필요한 것만 주입하라.

<br>

# ConfigMap 업데이트와 삭제

대부분의 쿠버네티스 API 오브젝트와 마찬가지로, ConfigMap은 매니페스트 파일을 수정한 뒤 `kubectl apply`로 언제든지 업데이트할 수 있다.

## kubectl edit

API 오브젝트를 빠르게 수정하려면 `kubectl edit` 커맨드를 사용할 수 있다.

```bash
# 기본 텍스트 에디터에서 ConfigMap 매니페스트를 직접 수정
kubectl edit configmap kiada-config
```

에디터를 닫으면 kubectl이 변경 사항을 Kubernetes API에 전송한다. JSON 형식으로 수정하려면 `-o json` 옵션을 사용한다.

```bash
# JSON 형식으로 수정
kubectl edit configmap kiada-config -o json
```

## 환경 변수 방식의 업데이트 동작

ConfigMap을 업데이트하면, **이미 실행 중인 파드의 환경 변수 값은 변경되지 않는다.** 컨테이너가 재시작되면(크래시, liveness probe 실패 등) 새 컨테이너는 업데이트된 값을 사용한다.

> configMap 볼륨 방식(환경 변수 대신 파일로 마운트)으로 ConfigMap 항목을 노출하면, ConfigMap 업데이트 시 실행 중인 모든 컨테이너에 자동 반영된다. 컨테이너 재시작이 필요 없다.

## 불변성 문제

컨테이너의 가장 중요한 속성 중 하나는 **불변성(immutability)**이다. 동일한 컨테이너(또는 파드)의 여러 인스턴스 간에 차이가 없음을 보장한다.

환경 변수로 주입된 ConfigMap을 변경하면:

- 실행 중인 인스턴스에는 영향 없다
- 일부 인스턴스가 재시작되거나 새 인스턴스가 생성되면, 새로운 설정이 적용된다
- 결과적으로 다른 설정을 가진 파드들이 혼재하게 되어, 시스템의 일부가 나머지와 다르게 동작할 수 있다

실행 중인 파드가 사용 중인 ConfigMap의 변경을 허용할지 여부를 신중하게 고려해야 한다.

## immutable ConfigMap

ConfigMap의 값이 변경되는 것을 방지하려면, `immutable: true`로 설정한다.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: my-immutable-configmap
data:
  mykey: myvalue
  another-key: another-value
immutable: true   # ConfigMap 값 변경 방지
```

immutable ConfigMap의 `data` 또는 `binaryData` 필드를 변경하려고 하면 API 서버가 차단한다.

```bash
# immutable ConfigMap 생성
kubectl apply -f cm.immutable-configmap.yaml

# 실행 결과
# configmap/my-immutable-configmap created

# 수정 시도 → 차단됨
kubectl edit cm my-immutable-configmap

# 실행 결과
# error: configmaps "my-immutable-configmap" is invalid

kubectl replace -f /var/folders/.../kubectl-edit-xxx.yaml

# 실행 결과
# The ConfigMap "my-immutable-configmap" is invalid:
#   data: Forbidden: field is immutable when `immutable` is set
```

immutable ConfigMap의 이점은 다음과 같다.

- 이 ConfigMap을 사용하는 **모든 파드가 동일한 설정 값을 사용**함을 보장한다
- 다른 설정이 필요한 파드는 새로운 ConfigMap을 생성하여 사용한다
- **성능 이점**: immutable로 표시되면 워커 노드의 kubelet이 ConfigMap 변경 알림을 받을 필요가 없으므로 API 서버 부하가 감소한다

## 삭제 동작

ConfigMap은 `kubectl delete` 커맨드로 삭제할 수 있다.

- 실행 중인 파드는 영향 없이 계속 실행된다 (컨테이너가 재시작되기 전까지)
- 컨테이너가 재시작될 때, ConfigMap 참조가 `optional`로 표시되지 않았으면 컨테이너 실행이 실패한다

<br>

# 볼륨 마운트 방식 미리보기

ConfigMap은 환경 변수 외에 **볼륨 마운트**로도 전달할 수 있다. 볼륨으로 마운트하면 ConfigMap의 각 키가 **파일 이름**, 값이 **파일 내용**이 되어 컨테이너 파일 시스템에 나타난다. `nginx.conf`나 `application.properties`처럼 설정 파일 자체를 컨테이너 내부에 배치해야 할 때 쓴다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: webapp
spec:
  containers:
  - name: webapp
    image: nginx
    volumeMounts:
    - name: config-volume
      mountPath: /etc/config  # 마운트 경로
  volumes:
  - name: config-volume
    configMap:
      name: app-config  # 참조할 ConfigMap
```

이렇게 하면 `/etc/config/` 아래에 ConfigMap의 키가 파일로 생긴다.

```bash
/etc/config/APP_COLOR   # 내용: blue
/etc/config/APP_MODE    # 내용: prod
```

내부적으로 kubelet은 **심볼릭 링크 체인**(타임스탬프 디렉토리 + `..data` 링크)을 사용해 atomic update를 수행한다. ConfigMap이 업데이트되면 kubelet이 새 타임스탬프 디렉토리를 만들고, `..data` 심볼릭 링크를 `rename()` 시스템 콜로 원자적으로 교체한다. 이를 통해 **모든 파일이 동시에** 새 버전을 가리키게 된다.

```bash
# 마운트된 ConfigMap 디렉토리의 실제 구조
/etc/config/
├── ..data           → ..2024_03_06_09_00_00.123456/   # 심볼릭 링크
├── ..2024_03_06_09_00_00.123456/                       # 실제 데이터 디렉토리
│   ├── APP_COLOR    # 내용: blue
│   └── APP_MODE     # 내용: prod
├── APP_COLOR        → ..data/APP_COLOR                 # 심볼릭 링크
└── APP_MODE         → ..data/APP_MODE                  # 심볼릭 링크
```

환경 변수 방식과 달리 볼륨 마운트는 **파드 재시작 없이 ConfigMap 변경이 자동 반영**된다. 다만 즉시 반영되는 것은 아니고, kubelet 동기화 주기 + 캐시 전파 지연만큼의 전파 지연이 있다.

한 가지 주의할 점은 `subPath` 마운트다. `subPath`는 ConfigMap의 특정 키 하나를 컨테이너의 특정 경로에 마운트할 때 사용하는데, 내부적으로 **개별 파일을 직접 bind mount**한다. 이 경우 심볼릭 링크 체인을 거치지 않고 mount 시점에 resolve된 **최종 파일의 inode**를 직접 잡기 때문에, kubelet이 `..data` 링크를 아무리 교체해도 **자동 반영이 되지 않는다.** 파드를 재시작해야 최신 값이 반영된다.

*inode 수준의 상세 분석은 [ConfigMap 업데이트와 bind mount]({% post_url 2026-03-07-Kubernetes-ConfigMap-Inode %}) 글을 참고한다.*

<br>

# 정리

- ConfigMap은 **키-값 쌍**을 담는 API 오브젝트로, 설정 데이터를 파드 매니페스트에서 분리하여 관리한다
- `kubectl create configmap` 커맨드로 리터럴, 파일, 디렉터리, env 파일에서 ConfigMap을 생성할 수 있다
- 환경 변수 주입에는 두 가지 방식이 있다
  - `configMapKeyRef`: 단일 항목을 지정하여 주입
  - `envFrom` + `configMapRef`: ConfigMap 전체를 한 번에 주입
- ConfigMap은 `envFrom`으로 편하게, Secret은 `env[].valueFrom`으로 필요한 것만 주입하는 것이 실무적 원칙이다
- 환경 변수로 주입된 ConfigMap은 컨테이너 재시작 전까지 반영되지 않는다
- `immutable: true`로 ConfigMap 변경을 방지하면 설정 일관성과 API 서버 부하 감소를 도모할 수 있다
- 볼륨 마운트 방식은 파드 재시작 없이 자동 반영되지만, subPath 마운트는 예외다

<br>

---

**참고 자료**

- [Configure a Pod to Use a ConfigMap](https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/) — `envFrom` vs `env[].valueFrom` 예시 포함
- [ConfigMaps | Kubernetes](https://kubernetes.io/docs/concepts/configuration/configmap/) — ConfigMap 개념 및 사용법
- [Stack Overflow: When should I use envFrom for configmaps?](https://stackoverflow.com/questions/66352023/when-should-i-use-envfrom-for-configmaps) — envFrom 유스케이스 토론
- [Stack Overflow: Why should I mount a secret or configmap?](https://stackoverflow.com/questions/67536226/why-should-i-mount-a-secret-or-configmap-in-kubernetes) — 볼륨 마운트를 선택하는 이유

*다음 포스트: [어플리케이션 설정 - 3. Secret]({% post_url 2026-04-05-Kubernetes-Application-Config-03-Secret %})*
