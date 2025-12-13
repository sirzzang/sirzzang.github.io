---
title:  "[Container] Docker와 containerd 이미지 관리 비교 - 1. 컨테이너 이미지와 런타임"
excerpt: 컨테이너 이미지의 구조, 런타임에 대해 알아 보자.
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - container
  - docker
  - containerd
  - container-image
  - oci
  - container-runtime

---

동일한 이미지를 `docker`와 `crictl`로 확인했을 때 크기가 다르게 나타난 현상을 분석하면서, 컨테이너 이미지와 런타임의 동작 원리를 정리했다. 이 글에서는 **이미지와 컨테이너에 대한 간단한 배경 지식**을 정리해 본다.

<br>

# 이미지

간단히 말하면, **컨테이너를 실행하기 위한 환경(파일시스템과 메타데이터)을 패키징한 읽기 전용 템플릿**이다. 여러 컨테이너들이 공유할 수 있다. **읽기 전용**이기 때문에, 컨테이너들이 **항상 같은 환경**에서 시작함을 보장한다.

이미지에는 아래와 같은 내용이 들어 있다.
- 애플리케이션 코드, 라이브러리, 의존성
- 런타임 환경 (Python, Node 등)
- 환경변수, 실행 명령, 진입점 등의 설정 

> 참고: 이미지에 대한 다양한 정의
>
> * [OCI 공식 문서](https://github.com/opencontainers/image-spec/blob/main/spec.md): This specification defines an OCI Image, consisting of an image manifest, an image index (optional), a set of filesystem layers, and a configuration.
> * [Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/containers/images/): A container image represents binary data that encapsulates an application and all its software dependencies.
> * [Docker 공식 문서](https://docs.docker.com/get-started/docker-overview/#images): An image is a read-only template with instructions for creating a Docker container.

<br>

```bash
Image: OCI Image Spec 준수
├── manifest (목차)
├── config.json (이미지 ID = sha256 해시)
└── layers (tar.gz)
    ├── layer1.tar.gz (sha256:aaa...)
    ├── layer2.tar.gz (sha256:bbb...)
    └── layer3.tar.gz (sha256:ccc...)
```

조금 더 구체적으로는, **OCI 표준(OCI Image Spec)에 따라 구성된 아래 세 가지 요소의 조합**을 의미한다. 
- Manifest: 이미지 목차. 어떤 config와 layers로 구성되는가
- Config JSON: 이미지 실행 설정
  - 이미지 파일 시스템 레이어 정보: 어떤 Layer들을 가지고 있는가
  - 이미지 메타데이터: 환경변수, 기본 실행 명령어, 진입점
- Layers: 파일 시스템 변경 사항
  - 이전 Layer 대비 변경 사항(추가, 수정, 삭제 등)들이 `tar.gz` 형태로 압축되어 저장됨
  - 층층이 쌓아 올려져, 최종 **컨테이너 파일 시스템**을 구성함


> 참고: OCI 표준이 정의하는 것
>
> - 이미지 포맷 (Image Spec): manifest 구조, config JSON 구조, layer 저장 방식 등
> - 런타임 스펙 (Runtime Spec): 컨테이너 실행 방법, 파일시스템 마운트, cgroups/namespaces 설정 등

<br>

## 이미지 ID

이미지를 식별하기 위한 해시값이다. 엄밀하게는, 위의 이미지 구조에서, **config JSON의 sha256 해시값**을 의미한다.
```bash
이미지 ID = sha256(이미지 config JSON)
```
```bash
Manifest (목차)
  ↓
Config JSON       →  sha256(config) = 이미지 ID
  ↓
Layers (tar.gz들)
```

<br>

이미지 ID는 `docker build` 등 빌드 도구를 이용한 **이미지 빌드 시점에 결정**된다.
1. 각 레이어 생성: 레이어별 sha256 해시 계산
2. config JSON 생성: 위에서 생성한 레이어 해시 포함
3. 이미지 ID 생성: config JSON의 sha256 해시

<br>

### 이미지의 동일성

이미지가 동일하다는 것은 이미지 ID가 동일하다는 것이다. 그리고 **동일한 이미지 ID를 가진 이미지는 바이트 단위로 완전히 동일한 이미지**임이 보장된다.

<br>

이것이 보장되는 이유는 SHA256 해시의 특성 때문이다:
- **결정론적 해시**: 같은 입력 데이터는 항상 같은 해시값을 생성한다
- **충돌 저항성**: 입력 데이터가 1비트라도 다르면 완전히 다른 해시값이 나온다. 해시 충돌(서로 다른 입력이 같은 해시를 생성) 확률이 극히 낮아 실질적으로 불가능하다

빌드 과정에서의 SHA256 해시 체인을 보자:
- 각 레이어(`tar.gz`)의 내용이 sha256 해시로 식별됨
- config JSON은 이 레이어 해시들을 포함하여 생성됨
- 이미지 ID는 config JSON의 sha256 해시임

<br>

따라서 **이미지 ID가 같다면 → config JSON이 같고 → config JSON이 같다면 포함된 레이어 해시들이 같고 → 레이어 해시가 같다면 레이어 내용이 바이트 단위로 동일**함이 보장되는 것이다.

주의할 점은, **같은 Dockerfile을 가지고 만든 이미지여도, 항상 같은 이미지 ID를 갖는 것이 보장되지 않는다**는 것이다. 
- 빌드 시점마다 빌드 과정의 해시 체인에 입력되는 아래와 같은 데이터가 달라질 수 있다:
  - 빌드 시 포함되는 파일의 타임스탬프
  - 빌드 시각(빌드 타임스탬프)
  - `apt-get update` 등 매번 다른 결과를 가져올 수 있는 레이어
  - ...
- 빌드 도구에 따라 아래 방식에서 차이가 있을 수 있다.
  - 레이어 생성 방식
  - 빌드 히스토리 기록 방식
  - 타임스탬프 등 파일 메타데이터 처리
  - 레이어 최적화 방식

> 참고: 다양한 빌드 도구
>
>- Docker: 풀스택, 가장 널리 사용
>- nerdctl: containerd용 Docker 호환 CLI
>- BuildKit: 고성능 빌드 엔진 (Docker 내부에서도 사용)
>- kaniko: 데몬리스, CI/CD 환경에 적합
>- buildah: Podman 생태계, 스크립트 빌드 가능

<br>

따라서, 아래와 같은 경우에는 이미지 ID가 같지 않을 수 있다.
- 같은 Dockerfile을 가지고 이미지를 재빌드하는 경우
- 같은 Dockerfile을 다른 빌드 도구를 이용해 빌드하는 경우

<br>

다만, **일단 한 번 빌드되어 결정된 이미지 ID는 불변이다**. 따라서 **한 번 빌드된 이미지를 어떤 레지스트리에 push/pull하는 것은 이미지 ID가 동일함을 보장**하지만, 같은 도구 혹은 다른 도구로 Dockerfile을 빌드 혹은 재빌드하는 것은 동일한 이미지 ID를 보장하지 않는다.


<br>

# 컨테이너

컨테이너란, **이미지 위에 쓰기 레이어를 얹고, 격리된 환경에서 실행되는 프로세스**를 의미한다. 이미지는 읽기 전용이므로, 컨테이너 실행 중 발생하는 파일 변경은 쓰기 레이어에 기록된다. 컨테이너가 삭제되면 쓰기 레이어도 함께 삭제된다.

```
Container = 이미지(읽기 전용) + 쓰기 가능 레이어 + 격리된 프로세스
```

<br>

# 컨테이너 런타임

 컨테이너 런타임이란, **컨테이너를 생성·실행·관리하는 시스템**을 말한다. 이미지를 기반으로 격리된 프로세스를 생성하고, 그 생명주기를 관리하는 역할을 한다. 넓은 의미에서는 컨테이너 관리뿐만 아니라, 이미지 pull/push, 네트워킹, 스토리지 관리까지 포함한다. 대표적으로 `dockerd`와 `containerd`가 있다.

## dockerd

`dockerd`는 Docker 데몬으로, **containerd를 사용**한다. **컨테이너 실행은 containerd에 위임**하고, 빌드, 네트워킹, 볼륨 관리 등의 기능을 얹은 형태이다.

```
┌───────────────────────────────────────┐
│              dockerd                   │
│  ┌────────┬─────────┬──────────────┐  │
│  │ Build  │ Network │ Volume Mgmt  │  │  <- Docker 추가 기능
│  └────────┴─────────┴──────────────┘  │
│              ↓ (사용)                   │
│  ┌──────────────────────────────────┐ │
│  │      containerd (별도 프로세스)      │ │  <- 컨테이너 런타임
│  └──────────────────────────────────┘ │
└───────────────────────────────────────┘
```

> 참고: 왜 이런 구조가 되었는가?
>
> 역사적인 이유다. 
> - **초기 Docker**: 모든 기능(이미지 관리, 컨테이너 실행, 빌드, 네트워킹 등)이 `dockerd` 하나의 프로세스에 통합되어 있었다.
> - **containerd 분리**: 이후 컨테이너 런타임 부분만 분리되어 `containerd`가 별도 프로세스로 탄생했다.
> - **현재 구조**: Docker는 하위 호환성을 위해 이미지 관리는 기존 방식(`/var/lib/docker`)을 유지하고, `containerd`에는 **컨테이너 실행 부분만 위임**하는 구조가 되었다. 따라서 `containerd`는 별도 프로세스이지만, `dockerd`가 `containerd`의 API를 호출하여 사용하는 관계이다.

<br>

## containerd

`containerd`는 **순수 컨테이너 런타임**이다. 이미지 pull, 컨테이너 생성·실행 등 핵심 기능만 담당하며, 빌드 기능은 없다.

```
Image storage: /var/lib/containerd
    ↓
containerd (default namespace)
    ↓
Container execution
```

<br>

### containerd의 네임스페이스

containerd는 내부적으로 **네임스페이스**를 사용하여 이미지와 컨테이너를 격리 관리한다. 누가 containerd를 사용하느냐에 따라 다른 네임스페이스에 저장된다.

| 사용 주체 | 네임스페이스 |
|----------|-------------|
| Docker (dockerd) | `moby` |
| Kubernetes | `k8s.io` |
| 미지정 시 기본값 | `default` |

> 참고: Kubernetes와 containerd
>
> Kubernetes 환경에서는 네트워크, 볼륨 관리 등을 Kubernetes가 담당하므로, 순수 런타임인 containerd만으로 충분하다. 이것이 Kubernetes가 Docker 의존성을 제거하고 containerd를 직접 사용하게 된 배경이다.

<br>

### containerd의 저장 구조

containerd는 이미지를 두 단계로 관리한다:
1. **Content Store**: 이미지 blob(레이어 tar.gz 등)을 압축 상태로 저장
  - 경로: `io.containerd.content.v1.content/blobs/sha256/`
2. **Snapshotter**: 컨테이너 실행 시 레이어를 압축 해제하여 파일시스템으로 제공
  - 경로: `io.containerd.snapshotter.v1.overlayfs/snapshots/`

<br>

## dockerd vs containerd 비교

| 항목 | dockerd | containerd |
|------|---------|------------|
| 역할 | 풀스택 컨테이너 플랫폼 | 순수 컨테이너 런타임 |
| 빌드 기능 | O | X |
| 이미지 저장 경로 | `/var/lib/docker` | `/var/lib/containerd` |
| Kubernetes 연동 | 과거 dockershim 필요 (현재 제거됨) | CRI로 직접 연동 |

> 참고: dockerd의 네임스페이스
> - dockerd는 자체적으로 네임스페이스 개념이 없지만, 내부적으로 containerd를 사용할 때 `moby` 네임스페이스를 사용함
> - 다만 dockerd는 이미지를 containerd가 아닌 `/var/lib/docker`에서 자체 관리하므로, containerd의 `moby` 네임스페이스에서 Docker 이미지를 **직접 볼 수는 없음**


<br>

---

*다음 글에서는 이 배경 지식을 바탕으로, 컨테이너 레이어가 어떻게 파일 시스템에서 관리되고, 컨테이너 런타임과 어떻게 통신할 수 있는지에 대해 다룬다.*
