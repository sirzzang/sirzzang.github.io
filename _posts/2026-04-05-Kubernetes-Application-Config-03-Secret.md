---
title:  "[Kubernetes] 어플리케이션 설정 - 3. Secret"
excerpt: "Secret을 이용해 민감 데이터를 관리하고 파드에 전달하는 방법과 보안 고려사항을 알아보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubernetes-in-Action-2nd
  - Secret
  - TLS
  - docker-registry
  - security
  - etcd
hidden: true
---

*[Kubernetes in Action 2nd Edition](https://www.manning.com/books/kubernetes-in-action-second-edition) 8장의 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- Secret은 ConfigMap과 구조적으로 유사하지만, 민감 데이터를 안전하게 처리하기 위해 설계된 별도의 API 오브젝트다
- Secret의 `data` 필드는 Base64 인코딩, `stringData` 필드는 평문(쓰기 전용)이다. `type` 필드로 Secret 유형을 구분한다
- Secret은 필요한 파드가 있는 노드에만 배포되고, 워커 노드에서 메모리(tmpfs)에만 저장된다
- 환경 변수로 Secret을 주입하면 로그/자식 프로세스를 통해 노출될 위험이 있으므로, 볼륨 마운트 방식을 권장한다
- Kubernetes Secret만으로는 보안이 충분하지 않을 수 있으며, HashiCorp Vault 같은 외부 Secret 관리 도구로 보완하는 것이 좋다

<br>

# Secret 소개

ConfigMap에 자격 증명이나 암호화 키 같은 민감 데이터도 저장할 수 있다고 생각할 수 있지만, 이는 최선의 방법이 아니다. 보안이 필요한 데이터를 위해 쿠버네티스는 **Secret**이라는 별도의 오브젝트 유형을 제공한다.

Secret은 ConfigMap과 크게 다르지 않다. 키-값 쌍을 포함하며, 환경 변수와 파일을 컨테이너에 주입하는 데 사용할 수 있다. 사실 Secret은 ConfigMap보다 먼저 도입되었다. 하지만 초기에는 값이 Base64로 인코딩되어야 했기 때문에 평문 데이터를 저장할 때 사용하기 불편했다. 이런 이유로 ConfigMap이 나중에 도입된 것이다. 시간이 지나면서 둘 다 평문과 바이너리 Base64 인코딩 데이터를 모두 지원하게 되어 기능이 수렴했다.

비슷하지만, 각각 점진적으로 발전했기 때문에 몇 가지 차이가 있다.

## ConfigMap과 Secret의 필드 차이

Secret의 구조는 ConfigMap과 약간 다르다.

| Secret | ConfigMap | 설명 |
| --- | --- | --- |
| `data` | `binaryData` | 키-값 쌍의 맵. 값은 Base64 인코딩 문자열 |
| `stringData` | `data` | 키-값 쌍의 맵. 값은 평문 문자열. Secret의 `stringData`는 **쓰기 전용** |
| `immutable` | `immutable` | 오브젝트에 저장된 데이터를 업데이트할 수 있는지 여부를 나타내는 불리언 값 |
| `type` | - | Secret의 유형을 나타내는 문자열. 임의의 값을 설정할 수 있지만, 몇 가지 내장 유형에는 특별한 요구 사항이 있음 |

- Secret의 `data` 필드는 ConfigMap의 `binaryData`에 대응한다. Base64 인코딩 문자열로 바이너리 값을 저장한다
- Secret의 `stringData` 필드는 ConfigMap의 `data`에 대응한다. 평문 값을 저장한다

> `data` 필드의 값은 YAML/JSON이 바이너리 데이터를 직접 지원하지 않으므로 Base64로 인코딩되어야 한다. 단, 이 인코딩은 매니페스트 내에서만 적용된다. Secret을 컨테이너에 주입할 때 쿠버네티스가 값을 디코딩하므로, 어플리케이션은 원본 형태 그대로 값을 읽을 수 있다.

`stringData` 필드는 **쓰기 전용**이다.

- 수동 인코딩 없이 평문 값을 추가할 수 있다
- API에서 Secret을 조회하면 `stringData` 필드는 나타나지 않고, 추가한 내용이 `data` 필드에 Base64 인코딩 문자열로 표시된다
- ConfigMap의 `data`/`binaryData`와 다른 동작이다. ConfigMap은 추가한 필드에 그대로 저장되어 조회 시에도 해당 필드에 나타난다

ConfigMap과 마찬가지로 `immutable: true`로 설정하여 불변으로 표시할 수 있다. ConfigMap에는 `type`이 없지만, Secret에는 `type` 필드가 있으며 주로 프로그래밍적 처리에 사용된다.

## 내장 Secret 유형

Secret 생성 시 내장 유형으로 설정하면, 해당 유형에 정의된 요구 사항을 충족해야 한다. 다양한 쿠버네티스 컴포넌트가 특정 키 아래 특정 형식의 값을 기대하기 때문이다.

| 내장 Secret 유형 | 설명 |
| --- | --- |
| **`Opaque`** | 임의의 키에 시크릿 데이터를 저장. `type` 필드 없이 Secret을 생성하면 Opaque로 생성됨 |
| **`bootstrap.kubernetes.io/token`** | 새 클러스터 노드 부트스트랩 시 사용하는 토큰 |
| `kubernetes.io/basic-auth` | 기본 인증에 필요한 자격 증명 저장. `username`과 `password` 키 필수 |
| **`kubernetes.io/dockercfg`** | Docker 이미지 레지스트리 접근 자격 증명. `.dockercfg` 키 필수 (레거시 Docker 설정 파일 형식) |
| `kubernetes.io/dockerconfigjson` | Docker 레지스트리 접근 자격 증명 (최신 형식). `.dockerconfigjson` 키 필수 (`~/.docker/config.json` 내용) |
| `kubernetes.io/service-account-token` | 쿠버네티스 서비스 어카운트를 식별하는 토큰 |
| `kubernetes.io/ssh-auth` | SSH 인증용 개인 키 저장. `ssh-privatekey` 키 필수 |
| **`kubernetes.io/tls`** | TLS 인증서와 개인 키 저장. `tls.crt`와 `tls.key` 키 필수 |

## 쿠버네티스가 Secret을 저장하는 방식

ConfigMap과 Secret의 필드 이름 차이 외에도, 쿠버네티스는 보안을 강화하기 위해 Secret을 특별하게 처리한다.

- Secret 데이터는 해당 Secret이 필요한 파드가 실행되는 노드에만 배포된다
- 워커 노드에서 Secret은 항상 **메모리에만 저장**되며 물리적 저장소에 기록되지 않는다
- 이러한 처리 덕분에 민감 데이터 유출 가능성이 줄어든다

따라서 **민감 데이터는 반드시 Secret에만 저장**하고 ConfigMap에는 저장하지 않아야 한다.

<br>

# Secret 생성

## kubectl create secret

ConfigMap과 마찬가지로 `kubectl create` 커맨드로 Secret을 생성할 수 있다.

```bash
# Generic(Opaque) Secret 생성
kubectl create secret generic kiada-secret-config \
  --from-literal status-message="This status message is set in the kiada-secret-config Secret"

# 실행 결과
# secret "kiada-secret-config" created
```

ConfigMap과 달리, `kubectl create secret` 뒤에 **Secret 유형**을 반드시 지정해야 한다. 여기서는 `generic`을 사용했다.

> ConfigMap과 마찬가지로 Secret의 최대 크기는 약 1MB이다.

## YAML 매니페스트로 생성

`kubectl create secret`은 클러스터에 직접 생성하지만, Secret도 Kubernetes API 오브젝트이므로 YAML 매니페스트로도 생성할 수 있다.

- 보안상 Secret의 YAML 매니페스트를 버전 관리 시스템에 저장하는 것은 권장하지 않는다
- ConfigMap보다 `kubectl create secret` 커맨드를 더 자주 사용하게 된다
- YAML 매니페스트가 필요하면 `--dry-run=client -o yaml`을 사용한다

```bash
# 자격 증명을 포함한 Secret YAML 매니페스트 생성
kubectl create secret generic my-credentials \
  --from-literal user=my-username \
  --from-literal pass=my-password \
  --dry-run=client -o yaml

# 실행 결과
# apiVersion: v1
# data:
#   pass: bXktcGFzc3dvcmQ=     # Base64 인코딩된 값
#   user: bXktdXNlcm5hbWU=     # Base64 인코딩된 값
# kind: Secret
# metadata:
#   creationTimestamp: null
#   name: my-credentials
```

`kubectl create` + `--dry-run=client -o yaml`을 사용하면 Base64 인코딩을 직접 할 필요 없이 매니페스트를 생성할 수 있다. 또는 `stringData` 필드를 사용하여 인코딩을 피할 수도 있다.

### stringData 필드 사용

모든 민감 데이터가 바이너리는 아니므로, `data` 필드 대신 `stringData`를 사용하여 평문 값을 지정할 수 있다.

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: my-credentials
stringData:              # data 대신 stringData 사용
  user: my-username
  pass: my-password
```

- `stringData`는 **쓰기 전용**이다. 값을 설정할 때만 사용할 수 있다
- `kubectl get -o yaml`로 조회하면 `stringData` 필드는 나타나지 않고, `data` 필드에 Base64 인코딩된 값으로 표시된다

> Secret의 항목은 항상 Base64 인코딩된 값으로 표시되므로, ConfigMap보다 읽기 불편하다. 가능하면 ConfigMap을 사용하되, 보안을 편의성 때문에 희생해서는 안 된다.

## TLS Secret

TLS 인증서와 개인 키가 필요한 경우, 컨테이너 이미지에 저장하는 대신 Secret에 저장하는 것이 더 적절하다.

```bash
# TLS Secret 생성
kubectl create secret tls kiada-tls \
  --cert example-com.crt \
  --key example-com.key
```

- `tls` 유형의 Secret `kiada-tls`를 생성한다
- 인증서는 `example-com.crt`, 개인 키는 `example-com.key` 파일에서 읽어온다

## Docker 레지스트리 Secret

프라이빗 컨테이너 레지스트리에서 이미지를 풀하려면 인증 자격 증명이 필요하다. `kubectl create secret docker-registry`로 생성할 수 있다.

```bash
# 직접 자격 증명 지정
kubectl create secret docker-registry pull-secret \
  --docker-server=<registry-server> \
  --docker-username=<username> \
  --docker-password=<password> \
  --docker-email=<email>

# 또는 로컬 Docker 설정 파일에서 생성
kubectl create secret docker-registry pull-secret \
  --from-file $HOME/.docker/config.json
```

Secret 생성 후, 파드 매니페스트의 `spec.imagePullSecrets`에서 참조한다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: private-image
spec:
  imagePullSecrets:
  - name: pull-secret       # Docker 레지스트리 Secret 이름
  containers:
  - name: private
    image: docker.io/me/my-private-image  # 프라이빗 이미지
```

쿠버네티스가 `pull-secret`의 자격 증명을 사용하여 프라이빗 이미지를 풀한다.

<br>

# Secret 사용

ConfigMap과 동일한 방식으로 Secret을 사용할 수 있다. 환경 변수를 설정하거나 컨테이너 파일 시스템에 파일을 생성할 수 있다. 파일 방식은 볼륨 마운트를 다루는 장에서 살펴보기로 하고, 여기서는 환경 변수 방식만 살펴보자.

## 환경 변수로 주입

먼저 Secret을 생성한다.

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: kiada-secret-config
stringData:
  status-message: "This status message is set in the kiada-secret-config Secret."
```

```bash
# Secret 생성
kubectl apply -f secret.kiada-secret-config.yaml
```

`valueFrom.secretKeyRef`를 사용하여 Secret의 특정 항목을 환경 변수로 주입한다.

```yaml
# pod.kiada.env-valueFrom-secretKeyRef.yaml
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
      valueFrom:
        secretKeyRef:           # configMapKeyRef 대신 secretKeyRef 사용
          name: kiada-secret
          key: status-message
          optional: true
    ports:
    - name: http
      containerPort: 8080
```

- `valueFrom.secretKeyRef`로 Secret의 특정 키 값을 환경 변수에 주입한다
- `optional: true`로 설정하면 Secret이 존재하지 않아도 파드 생성이 가능하다

`env.valueFrom` 대신 `envFrom`으로 Secret 전체를 주입할 수도 있다. [이전 포스트]({% post_url 2026-04-05-Kubernetes-Application-Config-02-ConfigMap %})에서 `configMapRef`를 사용한 것과 동일한 방식인데, `configMapRef` 대신 `secretRef`를 사용한다.

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
    envFrom:
    - secretRef:                # configMapRef 대신 secretRef 사용
        name: kiada-secret
        optional: true
    ports:
    - name: http
      containerPort: 8080
```

## Secret을 환경 변수로 주입해도 되는가

Secret을 환경 변수로 주입하는 방식은 ConfigMap과 동일하지만, **보안 위험**이 있어 권장하지 않는다.

- 어플리케이션이 에러 리포트나 시작 시 로그에 환경 변수를 출력하면 Secret이 노출될 수 있다
- 자식 프로세스가 부모 프로세스의 모든 환경 변수를 상속하므로, 서드파티 프로세스를 호출하면 Secret이 유출될 수 있다

> 더 나은 방법은 Secret을 **파일로** 컨테이너에 주입하는 것이다. secret volume을 사용하면 공격자에게 노출될 가능성이 줄어든다.

<br>

# Secret 보안 한계

Secret에 민감 데이터를 저장하는 것이 ConfigMap보다 낫지만, Secret이 생각만큼 안전하지 않을 수 있다. 핵심 과제는 Secret에 대한 접근 통제와 저장 방식이다.

## Secret 매니페스트의 값은 인코딩일 뿐 암호화가 아니다

Secret의 값이 암호화되어 있다고 오해하기 쉽지만, 실제로는 Base64 **인코딩**일 뿐이다. Secret에 접근할 수 있는 사람이라면 누구나 쉽게 디코딩하여 민감 데이터를 읽을 수 있다.

## Secret이 암호화 없이 저장될 수 있다

Secret은 Kubernetes API 서버 뒤의 키-값 저장소인 etcd에 다른 리소스와 함께 저장된다. 암호화가 활성화되지 않으면 Secret이 디스크에 평문으로 저장되며, 공격자가 디스크나 etcd에 직접 접근하면 모든 Secret을 볼 수 있다.

## 다른 사용자가 Kubernetes API로 Secret을 읽을 수 있다

Secret 및 기타 Kubernetes API 리소스에 대한 접근은 RBAC(역할 기반 접근 제어)로 제어된다. RBAC 규칙이 잘못 구성되거나 사용자 역할이 과도하게 허용적이면 Secret이 의도치 않게 노출될 수 있다.

- 파드에 주입된 Secret도 어플리케이션이 침해되면 유출 가능하다
- 환경 변수를 로그에 출력하는 단순한 동작만으로도 Secret이 유출될 수 있다

## Secret의 자동 교체 없음

인증 토큰 등의 보안을 개선하는 한 가지 방법은 정기적인 자동 교체다. Kubernetes Secret에는 이러한 기능이 없다. Secret이 업데이트되면 secret volume의 파일을 자동 갱신하는 것은 지원하지만, Secret 값 자체의 자동 교체는 수동으로 해야 한다.

## 외부 Secret 관리 도구로 보완

위 문제들의 권장 해결책은 HashiCorp Vault 같은 전용 외부 Secret 관리 도구를 사용하는 것이다. 강력한 암호화, 세분화된 접근 제어, 자동 Secret 교체, 상세한 감사 로그, 동적 Secret 생성을 제공한다.

<br>

# Secret vs ConfigMap 비교

Secret과 ConfigMap은 구조적으로 유사하지만, 몇 가지 중요한 차이가 있다. 여기서는 주입 방식, 저장 방식, 노드 배포 차이를 정리한다. ConfigMap의 기본 개념은 [이전 포스트]({% post_url 2026-04-05-Kubernetes-Application-Config-02-ConfigMap %})를 참고하자.

## 환경 변수 주입 방식

환경 변수로 주입할 때는 ConfigMap이든 Secret이든 동일한 방식으로 동작한다.

- kubelet이 컨테이너 시작 전에 API 서버에서 값을 가져온다
- 컨테이너 런타임에 환경 변수로 전달한다

## 볼륨 마운트 방식 차이

### tmpfs vs 디스크

볼륨 마운트 방식을 사용할 때 저장 매체가 다르다.

- **ConfigMap 볼륨**: 워커 노드의 **디스크(파일시스템)**에 기록된다. kubelet이 ConfigMap 데이터를 노드의 로컬 디스크에 쓰고, 그걸 컨테이너에 마운트한다. 노드 재부팅 전까지 디스크에 남아있을 수 있다
- **Secret 볼륨**: 워커 노드의 **tmpfs(RAM 기반 파일시스템)**에만 저장된다. 디스크에 절대 기록되지 않으며, 노드가 꺼지면 데이터가 사라진다

```bash
# Secret이 마운트된 파드 안에서 확인하면:
$ mount | grep secret
tmpfs on /var/run/secrets/kubernetes.io/serviceaccount type tmpfs (ro,relatime)

# ConfigMap이 마운트된 경우:
# 일반 파일시스템으로 마운트됨 (노드 디스크 기반)
```

### 마운트 디렉토리 내부 구조

마운트 디렉토리 내부 구조 자체는 동일하다.

```
/etc/config/                     <- 마운트 포인트
├── ..data -> ..2026_03_31_01_23  <- 심볼릭 링크 (타임스탬프 디렉터리를 가리킴)
├── ..2026_03_31_01_23/           <- 실제 데이터가 있는 타임스탬프 디렉터리
│   ├── key1                      <- 실제 파일 (키 = 파일명, 값 = 파일 내용)
│   └── key2
├── key1 -> ..data/key1           <- 심볼릭 링크
└── key2 -> ..data/key2           <- 심볼릭 링크
```

- 키가 마운트 디렉토리 내부 파일 이름이 되고, 값이 해당 파일의 내용이 된다
- **심볼릭 링크 기반의 atomic update**: ConfigMap/Secret이 업데이트되면, kubelet이 새 타임스탬프 디렉터리를 만들고 `..data` 심볼릭 링크만 갈아치운다. 앱이 읽는 도중에 일부만 업데이트된 상태(partial update)를 만나지 않는다

### 업데이트 자동 반영

환경 변수 방식과 달리, 볼륨 마운트 방식은 파드 재시작 없이 ConfigMap/Secret 업데이트가 자동 반영된다(반영까지 기본 약 60초 정도 걸림). subPath로 마운트하는 경우는 제외다.

- **환경 변수**: 프로세스 시작 시 메모리에 한 번 복사되는 값이다. 프로세스의 환경 블록에 고정되기 때문에, 외부 원본이 바뀌어도 이미 실행 중인 프로세스의 메모리에 있는 값은 그대로다
- **볼륨**: 컨테이너의 파일 시스템에 마운트된 경로다. 컨테이너가 파일을 읽을 때마다 그 시점의 파일 내용을 읽게 되므로, kubelet이 백그라운드에서 마운트된 파일을 갱신하면 어플리케이션은 자연스럽게 다음 번 읽기 때 새 값을 읽게 된다

## etcd 저장 차이

- **ConfigMap**: etcd에 평문으로 저장된다
- **Secret**: etcd에 Base64 인코딩으로 저장된다(기본값). `EncryptionConfiguration`을 설정하면 AES-CBC, AES-GCM 등으로 암호화할 수 있다

## 노드 배포 차이

- **ConfigMap**: 노드에 캐시되며, 해당 노드의 파드가 참조하지 않아도 남아있을 수 있다
- **Secret**: 해당 Secret을 사용하는 파드가 실행 중인 노드에만 배포된다. 파드가 종료되면 kubelet이 Secret의 로컬 복사본을 삭제한다

<br>

# 정리

Secret은 ConfigMap과 구조적으로 유사하지만, 민감 데이터를 안전하게 다루기 위한 별도의 오브젝트다. `data`(Base64 인코딩), `stringData`(쓰기 전용 평문), `type`(유형 구분) 필드가 핵심이고, `kubectl create secret`이나 YAML 매니페스트로 생성할 수 있다. TLS Secret과 Docker 레지스트리 Secret 같은 내장 유형도 지원한다.

Secret을 컨테이너에 주입할 때는 환경 변수 방식보다 볼륨 마운트 방식이 보안상 권장된다. 환경 변수는 로그나 자식 프로세스를 통해 노출될 위험이 있기 때문이다. 또한 쿠버네티스가 Secret을 필요한 노드에만 배포하고 메모리(tmpfs)에만 저장하는 등의 보호 메커니즘을 제공하지만, Base64 인코딩은 암호화가 아니고 etcd 저장 시 평문일 수 있으며 RBAC 설정 오류로 노출될 수 있다는 한계가 있다. 보안이 중요한 환경에서는 HashiCorp Vault 같은 외부 Secret 관리 도구를 함께 사용하는 것이 좋다.

<br>
