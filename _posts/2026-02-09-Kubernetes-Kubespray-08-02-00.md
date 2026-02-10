---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 8. 오프라인 배포: kubespray-offline - 0. Overview"
excerpt: "kubespray-offline이 무엇을, 왜 자동화하는지 이해하기 위한  청사진을 그려보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubespray
  - Air-Gapped
  - Offline
  - kubespray-offline
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-6

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 6주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 kubespray-offline을 이해하기 위한 **전체 청사진**을 그린다.

- **오프라인 배포 5단계**: 아티팩트 준비 → 서빙 인프라 구성 → 아티팩트 배치 → 변수 설정 → 배포 실행의 흐름
- **공식 문서 지도**: Kubespray 오프라인 관련 공식 문서 3종이 각각 어떤 단계를 다루는지
- **자동화 도구 지형**: `contrib/offline` 스크립트와 kubespray-offline 프로젝트의 역할과 커버리지 차이
- **8.2 시리즈 로드맵**: 개념(공식 문서) → 구현(kubespray-offline) 순서로 진행되는 시리즈 구조

<br>

# 들어가며

[8.1 시리즈]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-00 %})에서는 폐쇄망 기반 인프라를 한 땀 한 땀 수동으로 구축했다. NTP, DNS, 로컬 패키지 저장소, 사설 컨테이너 레지스트리, PyPI 미러까지 — 각각이 왜 필요한지, 어떻게 동작하는지를 직접 경험했다.

이제 8.2에서는 **이 작업들을 자동화해주는 도구**를 살펴본다.

8.1에서 수동으로 한 것들을 떠올려 보면:

| 수동 구축 (8.1) | 자동화 (8.2) |
|---|---|
| Nginx로 패키지 저장소 서빙 | kubespray-offline이 자동 구성 |
| Podman으로 레지스트리 기동 | kubespray-offline이 자동 기동 |
| devpi로 PyPI 미러 구축 | kubespray-offline이 자동 구축 |
| 이미지 태깅 + Push 수작업 | 스크립트가 목록 생성 + 일괄 Push |
| inventory 변수 수동 설정 | 일부 자동 생성 |

8.1에서 직접 해봤기 때문에, kubespray-offline이 **무엇을** 자동화하는지, **왜** 그런 구조로 만들어졌는지를 더 깊이 이해할 수 있다.

다만, kubespray-offline의 코드를 바로 분석하기 전에, Kubespray 공식 문서가 오프라인 배포를 어떻게 안내하고 있는지를 먼저 이해해야 한다. 공식 문서는 **"왜 필요하고, 뭘 설정해야 하는지"**를 설명하는 가이드이고, kubespray-offline은 **그 가이드를 자동화한 구현체**이기 때문이다. 가이드를 모르면 구현체가 왜 그렇게 생겼는지 알 수 없다.

<br>

그래서 8.2 시리즈는 **개념(공식 문서) → 구현(kubespray-offline)** 순서로 진행된다.

아래와 같은 흐름을 기억해 두면 도움이 된다.
```
[개념] 공식 문서로 "무엇을, 왜" 이해
    │
    │  이걸 수동으로 하면 힘드니까
    ▼
[도구] contrib/offline 스크립트
    │
    │  이것만으로도 부족한 부분이 있어서
    ▼
[구현] kubespray-offline이 어떻게 자동화하는지
```

이번 글에서는 이 흐름 전체를 조감하기 위한 **프레임워크 두 가지** — 오프라인 배포 5단계, 공식 문서 + 자동화 도구의 지형도 — 를 정리한다.

<br>

# 오프라인 배포 5단계

폐쇄망에서 Kubespray로 클러스터를 배포하려면, 크게 5단계를 거쳐야 한다. 이 프레임워크를 먼저 머릿속에 잡아두면, 이후 공식 문서를 읽든 kubespray-offline 코드를 분석하든 **지금 어느 단계 이야기인지** 바로 파악할 수 있다.

```
[1단계] 아티팩트 준비
  필요한 파일/이미지 목록 생성 → 다운로드
      ▼
[2단계] 서빙 인프라 구성
  파일 서버(Nginx), 컨테이너 레지스트리, PyPI 미러 등 기동
      ▼
[3단계] 아티팩트 배치
  다운로드한 파일을 서빙 인프라에 업로드/배치
      ▼
[4단계] Kubespray 변수 설정
  오프라인 환경에 맞게 inventory 변수 조정
      ▼
[5단계] 배포 실행
  ansible-playbook으로 클러스터 배포
```

각 단계를 좀 더 구체적으로 풀어 보면 다음과 같다.

| 단계 | 핵심 질문 | 구체적 작업 |
|------|-----------|------------|
| **1. 아티팩트 준비** | 뭘 다운로드해야 하나? | 바이너리(kubelet, kubeadm 등), 컨테이너 이미지, OS 패키지 목록 생성 + 다운로드 |
| **2. 서빙 인프라 구성** | 어디서 서빙하나? | Nginx(파일 서버), Docker Registry(이미지), PyPI 미러 등 기동 |
| **3. 아티팩트 배치** | 어떻게 올리나? | 파일을 Nginx 디렉토리에 배치, 이미지를 레지스트리에 Push |
| **4. 변수 설정** | Kubespray에 어떻게 알려주나? | 다운로드 URL, 레지스트리 주소, 미러 설정 등 inventory 변수 수정 |
| **5. 배포 실행** | 어떻게 배포하나? | `ansible-playbook cluster.yml` 실행 |

8.1에서 수동 구축한 것을 이 프레임워크에 매핑해 볼 수 있다.

| 단계 | 8.1에서 한 것 |
|------|-------------|
| 1. 아티팩트 준비 | reposync로 패키지 동기화, 이미지 Pull, pip download로 Python 패키지 다운로드 |
| 2. 서빙 인프라 구성 | Nginx 기동, Registry 기동, devpi 기동 |
| 3. 아티팩트 배치 | createrepo로 메타데이터 생성, 이미지 태깅 + Push, 패키지 업로드 |
| 4. 변수 설정 | *(8.1에서는 클러스터 배포까지 진행하지 않았다)* |
| 5. 배포 실행 | *(8.1에서는 클러스터 배포까지 진행하지 않았다)* |

<br>

# Kubespray 공식 문서 지도

Kubespray에는 오프라인 배포와 관련된 공식 문서가 3종 있다. 각 문서가 5단계 중 어디에 해당하는지를 먼저 파악해두면, 문서를 읽을 때 맥락을 잡기가 훨씬 수월하다.

```
Offline environment (전체 가이드)
  ├── "뭘 다운로드해야 하나?" → downloads.md 참조
  │     └── 다운로드 메커니즘 상세, 변수 제어 방식
  └── "어디서 다운로드하나?" → mirror.md 참조
        └── 공식 미러 목록, 미러 설정 방법
```

| 문서 | 다루는 내용 | 5단계 매핑 |
|------|-----------|-----------|
| **Offline environment** | 오프라인 배포 **전체 가이드**: 필요한 아티팩트 종류, 서빙 인프라 구성 방법, inventory 변수 설정 | 1~4단계 전반 |
| **Downloads** | Kubespray의 **다운로드 메커니즘** 상세: 어떤 변수로 URL/버전을 제어하는지, 다운로드 최적화 옵션 | 1단계 심화 |
| **Mirror** | 공식 **미러 서버 목록**과 미러 설정 방법 | 4단계 관련 |

각 문서의 성격을 정리하면:

- **Offline environment**: 오프라인 배포의 전체 그림을 잡아주는 핵심 문서다. "어떤 아티팩트가 필요하고, 어떤 서빙 인프라를 구성하고, 어떤 변수를 설정하라"를 안내한다. 나머지 두 문서를 참조하는 상위 문서 역할을 한다.
- **Downloads**: Kubespray 내부에서 다운로드가 어떻게 동작하는지를 다룬다. `download_run_once`, `download_localhost` 같은 변수가 어떻게 동작하는지, 다운로드 병렬화/캐시 같은 최적화 옵션은 뭐가 있는지를 상세하게 설명한다.
- **Mirror**: 공식 미러 목록과 미러 변수 설정 방법을 다룬다. 본래 목적은 느린 지역에서 다운로드 속도를 개선하기 위한 것이지만, 오프라인 환경에서 내부 서버를 미러로 설정할 때도 같은 변수 체계를 사용하므로 함께 이해해야 한다.

<br>

# 자동화 도구 지형

## 가이드 문서와 실행 도구

앞서 살펴본 공식 문서는 **"왜 필요하고, 뭘 설정해야 하는지"**를 알려주는 가이드다. 실제로 이 작업을 수행하는 것은 별도의 도구들이다.

```
[가이드 문서] ─ 개념/설정 방법
├── offline-environment.md     → 오프라인 배포 전체 가이드
├── downloads.md               → 다운로드 메커니즘 상세
└── mirror.md                  → 미러 목록/설정

[실행 도구] ─ 실제 자동화
├── contrib/offline (Kubespray 공식 스크립트)
│   ├── generate_list.sh
│   ├── manage-offline-files.sh
│   └── manage-offline-container-images.sh
└── kubespray-offline (외부 레포) ← 이번 시리즈 실습에서 사용
    └── contrib/offline 스크립트를 래핑 + 추가 기능 제공
```

## contrib/offline

Kubespray 저장소에 포함된 공식 편의 스크립트다. 가이드 문서에서 말하는 작업 중 **1단계(아티팩트 준비)와 3단계(아티팩트 배치)를 자동화**해준다.

| 스크립트 | 역할 |
|----------|------|
| `generate_list.sh` | 필요한 파일/이미지 목록 자동 생성 |
| `manage-offline-files.sh` | 바이너리/파일 다운로드 + 내부 서버 업로드 |
| `manage-offline-container-images.sh` | 이미지 다운로드 + 레지스트리 Push |

핵심 기능에 집중한 스크립트 모음이라, 그 외의 작업(서빙 인프라 구성, 변수 설정, admin 노드 셋업 등)은 **직접 해야 한다**.

## kubespray-offline

contrib/offline 스크립트를 **내부적으로 사용하면서**, 서빙 인프라 구성부터 admin 노드 셋업까지 한번에 처리해주는 **올인원 래퍼**다.

```
kubespray-offline
├── contrib/offline 스크립트를 내부적으로 사용 (래핑)
├── + 추가 편의 기능
│   ├── containerd 로컬 설치 스크립트
│   ├── Nginx 웹 서버 자동 시작
│   ├── Docker 레지스트리 자동 시작
│   └── 이미지 로드 + Push 자동화
└── + OS별 패키지 레포 준비 자동화
```

## 5단계 커버리지 비교

contrib/offline이 1, 3단계에 집중하는 반면, kubespray-offline은 1~4단계를 폭넓게 커버한다.

| 단계 | contrib/offline | kubespray-offline |
|------|-----------------|-------------------|
| 1. 아티팩트 준비 | `generate_list.sh` 등으로 자동화 | contrib 스크립트를 래핑하여 사용 |
| 2. 서빙 인프라 구성 | 직접 해야 함 | Nginx, 레지스트리 자동 시작 |
| 3. 아티팩트 배치 | `manage-offline-*.sh`로 자동화 | contrib 스크립트 래핑 + 추가 자동화 |
| 4. 변수 설정 | 직접 해야 함 | 일부 자동 생성 |
| 5. 배포 실행 | 직접 해야 함 | 직접 해야 함 |

정리하면, 이런 관계다.

```
offline-environment.md (문서)
  "이런 아티팩트가 필요하고, 이런 서빙 인프라를 구성하고, 이렇게 변수를 설정해라"
       │
       │ 이걸 수동으로 하면 힘드니까
       ▼
contrib/offline (스크립트)
  "목록 생성, 다운로드, 업로드를 자동화해줄게"
       │
       │ 이것만으로도 부족한 부분이 있어서
       ▼
kubespray-offline (외부 레포)
  "contrib/offline 스크립트를 래핑 + 서빙 인프라까지 한번에"
```

이 지형도를 머릿속에 넣어두면, 이후 시리즈에서 공식 문서의 어떤 개념이 kubespray-offline의 어떤 코드로 구현되었는지를 대응시키며 읽을 수 있다.

<br>

# 참고 자료

- [Kubespray - Offline Environment](https://kubespray.io/#/docs/offline-environment)
- [Kubespray - Downloads](https://kubespray.io/#/docs/downloads)
- [Kubespray - Public Download Mirror](https://kubespray.io/#/docs/mirror)
- [Kubespray - contrib/offline](https://github.com/kubernetes-sigs/kubespray/tree/master/contrib/offline)

<br>
