---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 8. 오프라인 배포: kubespray-offline - 1. Offline Environment"
excerpt: "Kubespray 공식 문서 offline-environment.md를 분석하며, 오프라인 배포에 필요한 아티팩트, 서빙 인프라, 변수 설정 전반을 이해해보자."
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
  - Ansible
  - Nginx
  - Container-Registry
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-6

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 6주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 Kubespray 공식 문서 [`offline-environment.md`](https://github.com/kubernetes-sigs/kubespray/blob/master/docs/operations/offline-environment.md)를 분석한다.

- **아티팩트 준비**: 어떤 아티팩트가 필요하고, 왜 목록이 설정에 따라 달라지는지
- **서빙 인프라 구성**: 각 인프라의 역할과 Mirror/Cache/Reverse Proxy 개념 정리
- **변수 설정**: 서빙 인프라를 가리키는 inventory 변수 체계와 Access Control
- **admin 노드 설정**: Kubespray 실행 방식 결정(컨테이너 vs 수동)과 그 영향 범위
- **Kubespray 실행**: 최종 배포 명령

| 공식 문서 섹션 | [이전 글]({% post_url 2026-02-09-Kubernetes-Kubespray-08-02-00 %})의 5단계 매핑 |
|---|---|
| 아티팩트 준비 + 서빙 인프라 구성 | 1단계(아티팩트 준비) + 2단계(서빙 인프라 구성) + 3단계(아티팩트 배치) |
| Configure Inventory + Access Control | 4단계(변수 설정) |
| Install Kubespray Python Packages | admin 노드 설정 |
| Run Kubespray as Usual | 5단계(배포 실행) |

<br>

# 공식 문서를 읽기 전에

## 문서 구조

공식 문서 `offline-environment.md`의 구성은 대략 이렇다.

```
offline-environment.md
├── 개요 문단 (아티팩트 준비, 서빙 인프라 설정)
├── Access Control
├── Configure Inventory
├── Install Kubespray Python Packages
└── Run Kubespray as Usual
```

얼핏 보면 자연스러운 순서 같지만, 실제로 읽어 보면 헷갈리는 부분이 있다.

## Access Control의 위치

Access Control이 Configure Inventory보다 먼저 나오는 섹션으로 되어 있는데, 내용적으로는 "서빙 인프라에 인증이 걸려 있을 때 변수를 어떻게 설정하나"에 대한 이야기라, Configure Inventory의 일부로 보면 자연스럽다. 그런데 별도 섹션처럼 눈에 들어와서, 그리고 더 먼저 나와서 처음에는 독립된 단계인가 싶었다. 결론적으로는 변수 설정의 한 부분으로 묶어서 이해하면 된다.

## Install Kubespray Python Packages의 순서

이 단계가 Configure Inventory 뒤에 나오는데, 논리적으로 생각하면 **Kubespray를 어떻게 실행할지(컨테이너 이미지 vs 수동 설치)**를 먼저 결정해야 준비할 아티팩트가 달라질 수 있다. 그런데 이 결정이 문서 맨 뒤에 나오니까, 처음 읽을 때 `이걸 먼저 결정했어야 하는 거 아닌가?` 싶어서 한참 헷갈렸다.

### 이론적으로 보면

컨테이너 이미지 방식을 쓸 거면 아티팩트에 Kubespray 이미지를 추가해야 하고, PyPI 미러는 admin용으로는 불필요할 수 있다. *반대로* 수동 설치 방식을 쓸 거면 Kubespray 이미지는 필요 없지만, PyPI 미러는 필수다. 즉 이 결정이 아티팩트 준비보다 앞에 와야 논리적으로 자연스러운데, 문서에서는 맨 뒤에 나온다.

### 실무적으로 보면

한참 고민했는데, [kubespray-offline](https://github.com/kubespray-offline/kubespray-offline)의 코드를 확인해 보니 이 고민을 이미 해결하고 있었다. [`download-all.sh`](https://github.com/kubespray-offline/kubespray-offline/blob/master/download-all.sh)는 [`config.sh`](https://github.com/kubespray-offline/kubespray-offline/blob/master/config.sh)의 `ansible_in_container` 설정값에 따라:

- `false`(기본값)이면 `pypi-mirror.sh`로 PyPI 미러를 준비하고,
- `true`이면 `build-ansible-container.sh`로 Ansible 컨테이너 이미지를 빌드한다.

<br>

*다만* 여기서 주의할 점은, kubespray-offline이 빌드하는 이미지(`kubespray-offline-ansible`)는 공식 문서에서 말하는 Kubespray 컨테이너 이미지(`quay.io/kubespray/kubespray`)와 **다르다**는 것이다. `config.sh`의 주석도 "Run **ansible** in container?"이지, "Run kubespray in container?"가 아니다.

```bash
# config.sh
ansible_in_container=${ansible_in_container:-false}  # Run ansible in container?
```

`build-ansible-container.sh`가 빌드하는 이미지의 Dockerfile을 간단히 살펴 보면 아래와 같다.

```dockerfile
# ansible-container/Dockerfile (축약)
FROM python:3.8-slim
RUN apt install -y openssh-client sshpass
COPY requirements.txt /root/
RUN pip install -r /root/requirements.txt   # Ansible, Jinja2, netaddr 등
```

`python:3.8-slim` 기반에 Kubespray의 `requirements.txt`만 설치한 경량 이미지다. Kubespray 코드 자체는 포함되어 있지 않고, 실행 시 호스트의 Kubespray 디렉토리를 마운트해서 사용한다. 

<br>

결국 정리하면, 아래와 같이 비교해 볼 수 있다.

| | 공식 문서의 컨테이너 이미지 | kubespray-offline의 컨테이너 이미지 |
|---|---|---|
| 이미지 | `quay.io/kubespray/kubespray` | `kubespray-offline-ansible` (자체 빌드) |
| 내용물 | Kubespray 코드 + Python 패키지 전부 | Python + Ansible 패키지만 |
| 목적 | Kubespray 실행 환경 통째로 제공 | Ansible 실행에 필요한 Python 의존성 해결 |

둘 다 "컨테이너로 Python 패키지 설치 문제를 우회한다"는 목적은 같지만, 이미지 자체가 다르다.

<br>

*그럼에도 불구하고* 핵심은, 결정에 따라 준비하는 아티팩트가 달라지긴 하지만, **그 분기를 도구가 알아서 처리해 주는 구조**라는 것이다. 실제 워크플로우에서는 설정 파일에서 이 결정을 먼저 한 뒤 아티팩트를 준비하는 흐름이므로, 공식 문서의 순서를 두고 그렇게까지 고민할 필요가 없었던 셈이다(kubespray-offline의 상세 구조는 이후 시리즈에서 다룬다). 

공식 문서가 Install Kubespray Python Packages를 뒤쪽에 배치한 것도 결국, **공식 문서는 개념과 설정 방법을 설명하는 순서**이고, 실제 아티팩트 준비는 도구가 결정에 맞게 처리한다는 맥락으로 이해하면 되지 않을까 싶다.

> 다만, "PyPI 패키지를 다 받아놓는 게 맞는가?"라는 별도의 질문은 남아 있는데, 이건 뒤의 [Python 패키지 (Optional)](#python-패키지-optional) 섹션에서 다룬다.

## 이 글의 접근 방식

공식 문서의 큰 골자를 따라가되, [이전 글(8.2.0)]({% post_url 2026-02-09-Kubernetes-Kubespray-08-02-00 %})에서 정리한 5단계 프레임워크에 매핑하며 정리한다.

| 단계 | 하는 일 | 비유 |
|------|---------|------|
| 1. 아티팩트 준비 | 인터넷 되는 곳에서 재료 다운로드 | 식재료 장보기 |
| 2. 서빙 인프라 구성 | 내부에 파일 서버, 레지스트리, PyPI 미러 등 구축 | 냉장고/창고 세팅 |
| 3. 변수 설정 | Kubespray가 내부 인프라를 바라보도록 inventory 오버라이드 | 레시피에 "재료는 여기서 가져와" 표시 |
| 4. admin 노드 설정 | Kubespray 실행 환경 준비 (컨테이너 이미지 or pip install) | 요리사 작업대 세팅 |
| 5. Kubespray 실행 | `ansible-playbook cluster.yml` | 요리 시작 |

> **참고**: 이전 글의 5단계에서는 "아티팩트 배치(3단계)"를 별도로 분리했지만, 공식 문서에서는 아티팩트 준비와 서빙 인프라 구성 안에 자연스럽게 녹아 있다. 이 글에서는 공식 문서의 흐름을 따르되, 필요한 곳에서 5단계 프레임워크를 참조한다.

<br>

# 아티팩트 준비

인터넷 접근이 가능한 환경(Bastion 등)에서 아래 아티팩트를 미리 준비해야 한다.

| 아티팩트 | 필수 여부 | 예시 |
|---------|----------|------|
| 정적 파일 (zip, 바이너리) | 필수 | kubelet, kubeadm, kubectl, crictl, CNI 플러그인 등 |
| OS 패키지 (rpm/deb) | 필수 | containerd, conntrack, socat 등 |
| 컨테이너 이미지 | 필수 | kube-apiserver, etcd, coredns, calico 등 |
| Python 패키지 | Optional | Ansible, Jinja2, netaddr 등 (`requirements.txt`) |
| Helm 차트 | Optional | ingress-nginx, cert-manager, metrics-server 등 |

각 종류의 아티팩트마다 그에 맞는 프로토콜과 서버가 필요하다. OS 패키지는 `yum`/`apt`가 이해하는 레포 형식이어야 하고, 컨테이너 이미지는 Docker Registry API를 지원해야 하고, 정적 파일은 HTTP로 접근 가능해야 한다. 이 1:1 대응 관계는 뒤의 서빙 인프라 구성에서 다시 나온다.

## 아티팩트 목록은 설정에 따라 달라진다

모든 경우에 통용되는 하나의 아티팩트 목록은 없다. 필요한 파일, 이미지, 패키지 목록은 **Kubespray 설정에 따라 달라진다.**

- **CNI 플러그인**을 Calico로 쓰느냐, Flannel로 쓰느냐에 따라 필요한 이미지가 다르다
- **Ingress Controller**, **CoreDNS**, **metrics-server** 등을 활성화했는지에 따라 추가 이미지가 필요하다
- `helm_enabled=true`면 Helm 관련 이미지도 필요하다

이걸 해결하기 위해 Kubespray가 `generate_list.sh` 스크립트를 제공한다. 현재 설정(inventory) 기준으로 필요한 이미지, 파일, Helm 차트 목록을 자동으로 뽑아준다. 핵심은 **설정을 잘 해두고 스크립트를 돌리면 끝**이라는 것이다.

## 정적 파일

`kubectl`, `kubeadm`, `kubelet`, `crictl`, CNI 플러그인 바이너리 등의 zip/바이너리 파일이다. 온라인 환경에서는 `https://dl.k8s.io/...` 같은 공식 URL에서 직접 다운로드하지만, 오프라인에서는 이 파일들을 미리 받아서 내부 HTTP 서버로 서빙해야 한다.

## OS 패키지

containerd, kubelet 설치에 필요한 rpm/deb 패키지다. [8.1.3]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-03 %})에서 `reposync`로 미러링한 것과 같은 종류의 작업이다.

## 컨테이너 이미지

Kubespray가 배포하는 모든 시스템 컴포넌트(kube-apiserver, etcd, coredns 등)와 CNI, 애드온 이미지다. 앞서 말한 대로, 어떤 이미지가 필요한지는 설정에 따라 달라지므로 `generate_list.sh`로 목록을 뽑는 것이 핵심이다.

## Python 패키지 (Optional)

Kubespray는 Ansible 기반이고, Ansible은 Python으로 동작한다. Kubespray 실행에 필요한 Python 패키지는 `requirements.txt`에 명시되어 있다.

공식 문서는 이를 Optional로 분류한다. OS 기본 패키지 매니저가 `requirements.txt`에 명시된 Python 패키지와 버전을 전부 설치할 수 있다면, 별도로 준비할 필요가 없기 때문이다. 예를 들어 Ubuntu 24.04에서 `python3-jinja2` 같은 시스템 패키지로 Kubespray가 요구하는 Jinja2 버전이 충족되면, pip 패키지를 따로 가져올 필요가 없다.

하지만 **실무적으로는 그냥 다 받아놓는 것이 맞다.** 이유는:

- OS마다, 버전마다 어떤 패키지가 시스템에 포함되어 있는지 **사전에 100% 확인하기 번거롭다**
- 오프라인 환경에 들어가면 인터넷이 안 되니까, 그때 가서 "이 Python 패키지 버전이 OS에 없네" 하면 **이미 늦다**
- 차라리 필요할 수도 있는 건 미리 다 받아놓고, 내부 PyPI 미러로 제공하는 게 **안전하고 확실한 전략**이다

> 실제 폐쇄망 현장에서 가장 흔한 실패 원인은 "이걸 안 가져왔네..."다. 시스템의 기능적 오류보다, 시스템을 설치하기 위한 사소한 파일이 없어서 `apt-get install`이 안 돼서 다시 방문해야 하는 경우가 허다했다. 그럴 때마다 사전에 정말 모든 가능성을 꼼꼼하게 챙겨서 패키지를 들고 가야 한다는 것을 체감했다. 그런 의미에서, Kubespray가 오프라인에서 필요한 모든 것을 변수 설정과 스크립트를 통해 촘촘하게 목록화하고 다운로드하는 구조는 정말 감탄스러웠다. 그래서 "Optional이니까 안 받아도 될 수도 있다"를 판단하는 것보다 "미리 다 다운받아 챙겨 간다"는 전략에 쉽게 공감할 수 있었다.

## Helm 차트 (Optional)

`helm_enabled=true`로 설정하면, Kubespray가 Helm을 설치하고 활성화된 애드온을 Helm 차트로 배포한다. 이때 필요한 차트를 인터넷에서 pull하는데, 오프라인에서는 안 되니까 미리 받아놔야 한다.

대표적으로 아래와 같은 것이 있다.
- **ingress-nginx** (Ingress Controller)
- **cert-manager** (인증서 관리)
- **metrics-server**
- **metallb** (Bare Metal LB)
- **csi-driver-nfs** 같은 스토리지 드라이버

Python 패키지와 달리, Helm 차트는 **"다 받아놓자"가 아니라 "내가 쓸 것만 받으면 된다"**는 접근이다.

| | Python 패키지 | Helm 차트 |
|---|---|---|
| **성격** | Kubespray 실행 자체에 필요 | 사용자가 명시적으로 활성화한 애드온에만 필요 |
| **불확실성** | OS가 제공할 수도 있어서 "Optional"이지만, 불확실 | 본인이 뭘 켜고 끌지 이미 알고 있음 |
| **전략** | 미리 다 받아놓는 게 안전 | 활성화한 애드온의 차트만 가져가면 됨 |

`helm_enabled=false`면 아예 필요 없고, `true`라도 활성화한 애드온의 차트만 준비하면 된다. 물론 `generate_list.sh` 실행 시 현재 설정 기준으로 필요한 Helm 차트 목록도 자동으로 뽑아준다.

<br>

# 서빙 인프라 구성

아티팩트를 준비했으면, 내부망 노드들이 이를 가져갈 수 있도록 **서빙 인프라**를 구성해야 한다. [8.1 시리즈]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-00 %})에서 수동으로 구축했던 것들이 여기에 해당한다.

| 서빙 인프라 | 서빙 대상 | 필수 여부 |
|------------|----------|----------|
| HTTP 웹 서버 (Nginx) | 정적 파일 (zip, 바이너리) | 필수 |
| 내부 YUM/Deb 레포 | OS 패키지 (rpm/deb) | 필수 |
| 내부 컨테이너 레지스트리 | 컨테이너 이미지 | 필수 |
| 내부 PyPI 서버 | Python 패키지 | Optional |
| 내부 Helm 레지스트리 | Helm 차트 | Optional |

아티팩트 종류와 서빙 인프라가 1:1로 대응한다. 각 종류의 아티팩트마다 그에 맞는 프로토콜과 서버가 필요하기 때문이다.

## 내부 파일 서버

정적 파일(zip, 바이너리)을 HTTP로 서빙하는 내부 웹 서버다. Kubespray가 클러스터 설치 시 각 노드에서 필요한 정적 파일을 HTTP로 다운로드하는데, 온라인 환경에서는 `https://dl.k8s.io/...` 같은 공식 URL에서 바로 받지만, 오프라인에서는 내부에 이 파일들을 서빙하는 HTTP 서버가 필요하다.

```
[온라인]  k8s-node → https://dl.k8s.io/... → 바이너리 다운로드
[오프라인] k8s-node → http://admin/repo/... → 내부 파일 서버에서 다운로드
```

kubespray-offline은 실제로 Nginx 컨테이너를 이 용도의 파일 서버로 시작한다. 미리 다운로드한 바이너리/zip 파일 등을 Nginx 서빙 디렉토리에 넣어두고, Kubespray 설정에서 다운로드 URL을 내부 Nginx 서버로 향하게 바꾸는 것이다.

### Mirror, Cache, Reverse Proxy

공식 문서에서 파일 서버를 설명할 때 "HTTP reverse proxy/cache/mirror"라는 표현을 쓴다. 세 가지를 다 적은 것은 **환경에 따라 선택지가 다양하다**는 의미이며, 정적 파일을 내부에서 서빙할 수만 있으면 어떤 방식이든 상관없다.

|  | 파일 보유 | 원본 접근 필요 | 주 목적 |
|---|---|---|---|
| **Mirror** | 사전에 복제해둠 | 동기화 시에만 | 원본의 복제본 제공 |
| **Cache** | 요청 시 저장 | 첫 요청 시 필요 | 반복 요청 최적화 |
| **Reverse Proxy** | 보유하지 않음 | 매 요청마다 | 중개, 로드밸런싱, 보안 |

- **Mirror**: 원본 서버 파일을 그대로 복제해서 내부에서 서빙한다. 클라이언트는 미러 서버에 직접 요청하고, 미러는 이미 갖고 있는 파일을 준다.
- **Cache**: 클라이언트의 요청을 대신 원본에 보내고, 받아온 응답을 저장해뒀다가 같은 요청이 오면 캐시에서 응답한다. 처음엔 원본 접근이 필요하지만, 이후 반복 요청은 빠르다.
- **Reverse Proxy**: 클라이언트와 백엔드 서버 사이에서 요청을 중개한다. 로드밸런싱, SSL 종료, 보안 등이 목적이다.

완전 폐쇄망에서는 원본 접근 자체가 불가능하므로, 사실상 **Mirror 방식만 가능**하다. [8.1 시리즈]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-00 %})에서 Nginx로 정적 파일을 서빙한 것도 이 방식이다.

> **참고**: "미러"라는 개념은 여러 군데에서 사용되지만, 미러링하는 대상이 다를 뿐 원리는 같다. **원본을 복제해서 내부에서 원본 대신 서빙하고, 클라이언트 설정에서 URL만 내부 서버로 바꿔주는 구조**다. containerd의 `registry.mirrors` 설정이나, apt의 `sources.list` 수정이나, pip의 `--index-url` 변경이나 — 전부 같은 패턴이다.
>
> | 용어 | 원본 | 내부 미러 | 하는 일 |
> |------|------|----------|---------|
> | OS 패키지 레포 미러 | `archive.ubuntu.com`, `mirrorlist.centos.org` 등 | 내부 Nginx/Apache | rpm/deb 패키지를 복제해서 내부에서 설치 가능하게 |
> | 컨테이너 이미지 레지스트리 미러 | `docker.io`, `registry.k8s.io`, `quay.io` 등 | 내부 Docker Registry | 컨테이너 이미지를 복제해서 내부에서 pull 가능하게 |
> | PyPI 미러 | `pypi.org` | 내부 Nginx (simple index) | Python 패키지를 복제해서 내부에서 pip install 가능하게 |
> | 정적 파일 미러 | `dl.k8s.io`, `github.com/releases` 등 | 내부 Nginx | 바이너리/zip을 복제해서 내부에서 HTTP 다운로드 가능하게 |

## 나머지 서빙 인프라

내부 YUM/Deb 레포, 컨테이너 레지스트리, PyPI 미러, Helm 레지스트리는 8.1 시리즈에서 이미 수동으로 구축한 경험이 있다.

| 서빙 인프라 | 8.1에서 한 것 | 참조 |
|------------|-------------|------|
| 내부 YUM 레포 | reposync + createrepo + Nginx | [8.1.3]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-03 %}) |
| 내부 컨테이너 레지스트리 | Podman으로 Docker Registry 기동 | [8.1.4]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-04 %}) |
| 내부 PyPI 미러 | devpi-server | [8.1.5]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-05 %}) |

공식 문서의 설명도 동일하다. 각 서빙 인프라에 아티팩트를 채워 넣고, 내부 노드들이 접근할 수 있게 구성하면 된다. 구체적인 구축 방법은 8.1에서 이미 다뤘으니, 이 글에서는 **Kubespray가 이 인프라를 어떻게 찾아가는지** — 즉 변수 설정에 집중한다.

<br>

# 변수 설정

서빙 인프라를 구성했으면, **Kubespray가 그 인프라를 찾아갈 수 있도록 변수를 설정**해야 한다.

## 변수 오버라이드 전략

오프라인 환경에서 달라지는 변수들은 `roles/download/defaults/main/` 같은 role defaults에 이미 **온라인 기본값이 정의**되어 있다. 온라인 환경에서는 건드릴 필요가 없지만, 오프라인 환경에서는 **inventory group vars에서 내부 환경에 맞게 오버라이드**해야 한다.

예를 들어 `files_repo`는 기본값이 인터넷의 공식 URL(`https://dl.k8s.io`, `https://github.com/...` 등)을 가리킨다. 오프라인 환경에서만 이 기본값을 내부 서버 URL로 오버라이드한다.

```yaml
# group_vars/all/offline.yml
files_repo: "http://192.168.10.10/repo"
```

## 서빙 인프라에 대응하는 변수

| 변수 | 대응하는 서빙 인프라 | 설명 |
|------|-------------------|------|
| `registry_host` | 내부 컨테이너 레지스트리 | 이미지를 pull할 레지스트리 주소 (프로토콜 포함) |
| `registry_addr` | 내부 컨테이너 레지스트리 | 레지스트리의 `도메인:포트`만 (프로토콜 없이) |
| `files_repo` | 내부 HTTP 파일 서버 (Nginx) | 바이너리/zip 다운로드 URL |
| `yum_repo` / `debian_repo` / `ubuntu_repo` | 내부 OS 패키지 레포 | OS에 맞는 것 하나만 정의 |

각 변수에 대해 공식 문서가 언급하는 포인트를 정리하면:

- **`registry_host`**: 내부 레지스트리에 **같은 경로 구조**로 이미지를 push해놨다면, `registry_host`만 바꾸면 끝이다. Kubespray defaults에 각 이미지의 경로가 `registry.k8s.io/kube-apiserver`, `docker.io/calico/node` 같은 식으로 정의되어 있는데, 내부 레지스트리에도 같은 경로를 유지하면(`내부레지스트리/kube-apiserver`, `내부레지스트리/calico/node`) 개별 `*_image_repo` 변수를 일일이 오버라이드할 필요가 없다. 공식 문서가 **"make your life easier, use the same repository path"**라고 권장하는 이유다.

- **`files_repo`**: 파일을 어디에 놓든 Kubespray가 접근만 가능하면 된다. 다만 URL 경로에 `*_version`을 포함하라고 권장한다. Kubespray 업그레이드 시 버전만 바뀌면 되니까, `files_repo` 자체를 수정할 필요가 없어진다. 예: `http://내부서버/repo/v1.31.0/...`

- **`yum_repo` / `debian_repo` / `ubuntu_repo`**: 자기 OS에 맞는 것 **하나만** 정의하면 된다. 주의할 점은, 이 변수는 **Docker/Containerd 패키지 설치용**으로만 사용되고, 다른 시스템 패키지는 별도 레포에서 설치될 수 있다는 것이다. 다른 레포에서의 설치를 막고 싶으면 `system-packages` 태그를 skip하면 된다.

## 설정 예시

공식 문서가 제공하는 변수 설정 예시다. 레지스트리 관련 변수, 바이너리 다운로드 URL, OS별 레포 설정이 포함되어 있다. 

잘 살펴 보면, 패턴이 보인다. **최상위 변수(`registry_host`, `files_repo`, `yum_repo` 등)만 내부 서버로 바꿔주면**, 나머지 세부 변수들은 `{{ }}` 템플릿으로 자동 연동된다. 오프라인 환경에서 실제로 건드려야 할 변수의 수가 생각보다 적은 이유다.


```yaml
# Registry overrides
kube_image_repo: "{{ registry_host }}"
gcr_image_repo: "{{ registry_host }}"
docker_image_repo: "{{ registry_host }}"
quay_image_repo: "{{ registry_host }}"
github_image_repo: "{{ registry_host }}"

# Binary downloads
kubeadm_download_url: "{{ files_repo }}/kubernetes/v{{ kube_version }}/kubeadm"
kubectl_download_url: "{{ files_repo }}/kubernetes/v{{ kube_version }}/kubectl"
kubelet_download_url: "{{ files_repo }}/kubernetes/v{{ kube_version }}/kubelet"
# etcd is optional if you DON'T use etcd_deployment=host
etcd_download_url: "{{ files_repo }}/kubernetes/etcd/etcd-v{{ etcd_version }}-linux-{{ image_arch }}.tar.gz"
cni_download_url: "{{ files_repo }}/kubernetes/cni/cni-plugins-linux-{{ image_arch }}-v{{ cni_version }}.tgz"
crictl_download_url: "{{ files_repo }}/kubernetes/cri-tools/crictl-v{{ crictl_version }}-{{ ansible_system | lower }}-{{ image_arch }}.tar.gz"
# If using Calico
calicoctl_download_url: "{{ files_repo }}/kubernetes/calico/v{{ calico_ctl_version }}/calicoctl-linux-{{ image_arch }}"
# If using Calico with kdd
calico_crds_download_url: "{{ files_repo }}/kubernetes/calico/v{{ calico_version }}.tar.gz"
# Containerd
containerd_download_url: "{{ files_repo }}/containerd-{{ containerd_version }}-linux-{{ image_arch }}.tar.gz"
runc_download_url: "{{ files_repo }}/runc.{{ image_arch }}"
nerdctl_download_url: "{{ files_repo }}/nerdctl-{{ nerdctl_version }}-{{ ansible_system | lower }}-{{ image_arch }}.tar.gz"
get_helm_url: "{{ files_repo }}/get.helm.sh"

# Insecure registries for containerd
containerd_registries_mirrors:
  - prefix: "{{ registry_addr }}"
    mirrors:
      - host: "{{ registry_host }}"
        capabilities: ["pull", "resolve"]
        skip_verify: true

# CentOS/Redhat/AlmaLinux/Rocky Linux
docker_rh_repo_base_url: "{{ yum_repo }}/docker-ce/$releasever/$basearch"
docker_rh_repo_gpgkey: "{{ yum_repo }}/docker-ce/gpg"

# Fedora
docker_fedora_repo_base_url: "{{ yum_repo }}/docker-ce/{{ ansible_distribution_major_version }}/{{ ansible_architecture }}"
docker_fedora_repo_gpgkey: "{{ yum_repo }}/docker-ce/gpg"
containerd_fedora_repo_base_url: "{{ yum_repo }}/containerd"
containerd_fedora_repo_gpgkey: "{{ yum_repo }}/docker-ce/gpg"

# Debian
docker_debian_repo_base_url: "{{ debian_repo }}/docker-ce"
docker_debian_repo_gpgkey: "{{ debian_repo }}/docker-ce/gpg"
containerd_debian_repo_base_url: "{{ ubuntu_repo }}/containerd"
containerd_debian_repo_gpgkey: "{{ ubuntu_repo }}/containerd/gpg"
containerd_debian_repo_repokey: 'YOURREPOKEY'

# Ubuntu
docker_ubuntu_repo_base_url: "{{ ubuntu_repo }}/docker-ce"
docker_ubuntu_repo_gpgkey: "{{ ubuntu_repo }}/docker-ce/gpg"
containerd_ubuntu_repo_base_url: "{{ ubuntu_repo }}/containerd"
containerd_ubuntu_repo_gpgkey: "{{ ubuntu_repo }}/containerd/gpg"
containerd_ubuntu_repo_repokey: 'YOURREPOKEY'
```


## Access Control

서빙 인프라에 인증 설정이 걸려 있는 경우, 관련 변수를 추가로 설정해야 한다.

### 파일 서버 인증

내부 HTTP 파일 서버에 Basic Auth가 걸려 있으면, URL에 `username:password@`를 포함시킨다.

```yaml
files_repo_host: example.com
files_repo_path: /repo
files_repo_user: download
files_repo_pass: !vault |
          $ANSIBLE_VAULT;1.1;AES256
          61663232643236353864663038616361373739613338623338656434386662363539613462626661
          ...
files_repo: "https://{{ files_repo_user ~ ':' ~ files_repo_pass ~ '@' ~ files_repo_host ~ files_repo_path }}"
```

`@`, `:`, `#` 같은 특수문자가 비밀번호에 포함되어 있으면 URL이 깨지므로, `%40`, `%3A` 등으로 URL-encode 해야 한다.

### 컨테이너 레지스트리 인증

프라이빗 레지스트리에 인증이 걸려 있으면, containerd의 registry auth를 설정한다.

```yaml
registry_pass: !vault |
          $ANSIBLE_VAULT;1.1;AES256
          61663232643236353864663038616361373739613338623338656434386662363539613462626661
          ...

containerd_registry_auth:
  - registry: "{{ registry_host }}"
    username: "{{ registry_user }}"
    password: "{{ registry_pass }}"
```

### 보안 주의사항

- **`unsafe_show_logs` 주의**: Kubespray가 파일 다운로드 시 URL을 로그에 출력하는 task가 있다. URL에 비밀번호가 포함되어 있으면 **로그에 비밀번호가 그대로 노출**된다. AWX/AAP/Semaphore 같은 CI 도구에서 실행할 때는 이 Boolean을 `false`로 설정해서 로그에 URL이 찍히지 않게 해야 한다.
- **시크릿 평문 저장 금지**: 위 예시에서 비밀번호를 `!vault | ...` (Ansible Vault)로 암호화한 것은 **민감 정보를 평문으로 코드/설정 파일에 직접 적지 말라**는 보안 원칙을 따른 것이다. Ansible Vault 외에도 환경 변수 참조(`lookup('env', 'FILES_REPO_PASS')`), 별도 vars 파일 + `.gitignore`, 외부 시크릿 매니저(HashiCorp Vault, AWS Secrets Manager 등) 같은 방식을 사용할 수 있다.

<br>

# admin 노드 설정

아티팩트를 준비하고, 서빙 인프라를 구성하고, 변수를 설정했으면, 마지막으로 **admin 노드에 Kubespray 실행 환경을 준비**해야 한다.

Kubespray는 Ansible 기반이고, Ansible은 Python으로 동작한다. `requirements.txt`에 명시된 Python 패키지(Ansible, Jinja2, netaddr 등)가 admin 노드에 설치되어 있어야 한다. 온라인이면 `pip install -r requirements.txt` 한 줄이면 끝이지만, 오프라인에서는 PyPI에 접근이 안 되니까 다른 방법이 필요하다.

## 방법 1: Kubespray 컨테이너 이미지 (권장)

Kubespray가 공식 컨테이너 이미지(`quay.io/kubespray/kubespray`)를 제공하는데, 이 이미지 안에 **필요한 Python 패키지가 전부 포함**되어 있다.

공식 문서에서는 "Just copy the container image in your private container image registry and you are all set!"이라고 안내한다. 간단해 보이지만, 이 "Just copy"는 **직접 해야 하는 별도 작업**이다. 이 이미지는 K8s 클러스터 컴포넌트가 아니라 Ansible 실행 도구이므로, `generate_list.sh`가 생성하는 이미지 목록에 포함되지 않는다. 인터넷 되는 곳에서 직접 pull한 뒤, 내부 레지스트리에 push해야 한다.

> **참고**: `generate_list.sh`는 `roles/kubespray_defaults/defaults/main/download.yml`에 정의된 이미지 목록을 파싱해서 필요한 이미지 리스트를 생성한다. `download.yml`에 있는 이미지들은 전부 클러스터 컴포넌트(calico, flannel, cilium, etcd, coredns, nginx, metrics-server 등)다. `quay.io/kubespray/kubespray`(러너 이미지)는 `download.yml`에 정의되어 있지 않으므로, `generate_list.sh` 출력에 포함되지 않는다. `generate_list.sh`와 `download.yml`의 동작 방식은 이후 시리즈에서 더 자세히 살펴본다.

이미지만 내부 레지스트리에 넣어두면, 컨테이너 안에서 Kubespray를 실행할 수 있다. Python 패키지 설치를 아예 신경 쓸 필요가 없어서 가장 간편하다.

## 방법 2: 수동 설치

컨테이너를 쓰지 않고 admin 노드에 직접 설치하는 경우, 두 가지 경로가 있다.

- **DMZ 프록시 경유**: 인터넷에 간접 접근이 가능한 경우
  ```bash
  sudo pip install --proxy=https://[username:password@]proxyserver:port -r requirements.txt
  ```
- **내부 PyPI 서버 사용**: 완전 폐쇄망인 경우, 1단계에서 준비한 내부 PyPI 미러에서 설치
  ```bash
  # 필요한 패키지를 모두 내부 PyPI에 올려둔 경우
  pip install -i https://pypiserver/pypi -r requirements.txt

  # OS 패키지 매니저로 충족되지 않는 것만 설치하는 경우
  pip install -i https://pypiserver/pypi package_you_miss
  ```

## "결정"이 영향을 주는 범위

앞서 [공식 문서를 읽기 전에](#install-kubespray-python-packages의-순서)에서 고민했듯이, 이 결정에 따라 준비하는 아티팩트가 달라지긴 한다. 하지만 kubespray-offline은 `ansible_in_container` 설정으로 이를 알아서 분기 처리한다(다만, kubespray-offline이 빌드하는 이미지는 공식 Kubespray 이미지가 아니라 자체 Ansible 컨테이너라는 점은 [앞서 정리한 대로](#실무적으로-보면)다). 실제로 신경 써야 할 것은 **admin 노드에서 어떤 방식으로 실행할지**뿐이다.

<br>

# Kubespray 실행

모든 준비가 끝났으면, 일반적인 Kubespray 배포 명령을 실행한다.

```bash
ansible-playbook -i inventory/my_airgap_cluster/hosts.yaml -b cluster.yml
```

Kubespray 컨테이너 이미지를 사용하는 경우, inventory를 컨테이너 안에 마운트해서 실행한다.

```bash
docker run --rm -it \
  -v path_to_inventory/my_airgap_cluster:inventory/my_airgap_cluster \
  myprivateregistry.com/kubespray/kubespray:v2.14.0 \
  ansible-playbook -i inventory/my_airgap_cluster/hosts.yaml -b cluster.yml
```

오프라인이라고 해서 실행 명령이 달라지는 것은 아니다. **아티팩트, 서빙 인프라, 변수 설정이 제대로 되어 있으면**, Kubespray는 내부 인프라에서 필요한 파일과 이미지를 가져와서 일반 배포와 동일하게 동작한다.

<br>

# 참고 자료

- [Kubespray - Offline Environment](https://github.com/kubernetes-sigs/kubespray/blob/master/docs/operations/offline-environment.md)
- [Kubespray - contrib/offline](https://github.com/kubernetes-sigs/kubespray/tree/master/contrib/offline)

<br>
