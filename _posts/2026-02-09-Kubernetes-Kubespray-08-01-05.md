---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 8. 오프라인 배포: The Hard Way - 5. Private PyPI Mirror"
excerpt: "폐쇄망 환경에서 Python 패키지 설치를 위한 사설 PyPI 미러(devpi-server)를 구축해보자."
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
  - PyPI
  - devpi
  - pip
  - Python
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-6
hidden: true

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 6주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 폐쇄망 환경에서 Python 패키지 설치를 위한 **사설 PyPI 미러(devpi-server)**를 구축한다.

- **devpi-server 구축**: admin에서 devpi-server를 설치하고, 인덱스를 생성
- **패키지 업로드**: kubespray 실행에 필요한 Python 패키지를 사설 저장소에 업로드
- **pip 클라이언트 설정**: k8s-node에서 admin의 devpi-server를 패키지 저장소로 사용
- **정리**: 이후 kubespray-offline 실습을 위해 devpi-server 종료 및 설정 삭제

| 순서 | 위치 | 작업 | 목적 |
|------|------|------|------|
| 1 | admin | devpi-server 설치 + 인덱스 생성 | 사설 PyPI 서버 구축 |
| 2 | admin | 패키지 다운로드 + 업로드 | 폐쇄망에서 필요한 패키지 사전 등록 |
| 3 | k8s-node | `pip.conf` 설정 + 패키지 설치 | 사설 PyPI 서버 사용 확인 |
| 4 | admin, k8s-node | devpi 종료 + pip.conf 삭제 | 이후 실습을 위한 정리 |

<br>

# 사설 PyPI 미러의 필요성

[이전 글(8.1.4)]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-04 %})에서 사설 컨테이너 레지스트리를 구축했다. 이번에는 **Python 패키지**를 폐쇄망에서 설치할 수 있어야 한다.

Kubespray는 **Ansible 기반**으로 동작하며, Ansible은 Python으로 작성된 도구다. Kubespray를 실행하려면 `jmespath`(JSON 필터링), `netaddr`(IP 주소 계산) 등의 Python 패키지가 필요하다. 온라인 환경에서는 `pip install`로 공개 PyPI([pypi.org](https://pypi.org))에서 바로 설치하면 되지만, 폐쇄망에서는 이 서버에 접근할 수 없다.

```
[온라인]  k8s-node → pypi.org → pip install 패키지 다운로드
[폐쇄망]  k8s-node → admin (devpi-server, :3141) → 사설 PyPI 서버에서 다운로드
```

[이전 글(8.1.3)]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-03 %})에서 구축한 로컬 YUM/DNF 저장소가 **리눅스 OS 패키지**(RPM)를 위한 것이라면, 이번에 구축하는 devpi-server는 **Python 패키지**(wheel/sdist)를 위한 동일한 역할이다.

| 저장소 | 대상 | 도구 | 프로토콜 |
|--------|------|------|----------|
| 로컬 YUM/DNF 저장소 | OS 패키지 (`.rpm`) | `dnf install` | HTTP (nginx) |
| 사설 PyPI 미러 | Python 패키지 (`.whl`) | `pip install` | HTTP (devpi-server) |

<br>

# 배경지식

## PyPI와 pip

**PyPI(Python Package Index)**는 Python 패키지의 공식 저장소다. 현재 50만 개 이상의 프로젝트가 등록되어 있으며, `pip install` 명령의 기본 다운로드 소스다.

**pip**는 Python의 표준 패키지 관리자로, PyPI에서 패키지를 다운로드하고 설치한다.

```
사용자: pip install requests
  ↓
pip: PyPI 서버에 requests 검색
  → 의존성 확인 (charset_normalizer, idna, urllib3, certifi)
  → 모든 패키지 다운로드
  → 설치
```

## Simple Repository API (PEP 503)

pip과 PyPI 서버 사이의 통신은 **PEP 503 Simple Repository API**로 표준화되어 있다. 모든 PyPI 호환 저장소(devpi, pypiserver, Nexus 등)는 이 API를 구현한다.

```
GET /simple/                    → 패키지 목록 (HTML)
GET /simple/requests/           → requests의 모든 버전/파일 링크 (HTML)
GET /packages/requests-2.31.whl → 실제 파일 다운로드
```

pip이 `pip install requests`를 실행하면:

1. `/simple/requests/` 엔드포인트에서 사용 가능한 버전 목록을 HTML로 받음
2. 현재 Python 버전, OS, 아키텍처에 맞는 최적의 파일을 선택
3. `.whl`(wheel) 또는 `.tar.gz`(sdist) 파일을 다운로드
4. 로컬에 설치

클라이언트(pip) 입장에서는 **Simple API만 제공하면 어떤 서버든 동일하게 동작**한다. 서버마다 다른 것은 캐싱, 미러링, 인덱스 체이닝 같은 서버 측 관리 기능이다.

```bash
# 기본 PyPI 서버 사용
pip install requests

# 사설 서버 사용 (--index-url로 서버 주소만 변경)
pip install requests --index-url http://192.168.10.10:3141/root/prod/+simple
```

`--index-url`로 서버 주소만 바꾸면, pip은 공개 PyPI든 사설 서버든 동일한 방식으로 패키지를 가져온다.

## PyPI 저장소 구현체

PyPI 호환 저장소를 구축하는 도구는 여러 가지가 있다.

| 도구 | 특징 | 인덱스 체이닝 |
|------|------|:---:|
| **devpi** | 캐싱 프록시 + 사설 저장소 + 인덱스 체이닝. PyPI 전용 경량 도구 | O |
| **Bandersnatch** | pypi.org 전체를 로컬에 복사하는 순수 미러. 업로드 불가 | X |
| **pypiserver** | 디렉토리의 파일을 Simple API로 서빙하는 단순한 저장소 | X |
| **pip2pi** | 오프라인용. 패키지를 디렉토리에 받아 Simple API 형태로 생성 | X |
| **Nexus Repository** | 범용 아티팩트 저장소 (PyPI, Maven, npm, Docker 등 지원) | O |
| **JFrog Artifactory** | 범용 아티팩트 저장소. Virtual Repository로 체이닝 지원 | O |

이 실습에서는 **devpi**를 사용한다. PyPI 전용으로 가볍고, 인덱스 체이닝을 네이티브로 지원하여 "인터넷이 될 때 외부 패키지를 캐시해두고, 폐쇄망에서는 캐시된 것만 서빙"하는 구성이 자연스럽기 때문이다.

## devpi

**devpi**(DEVelopment Package Index)는 PyPI 캐싱 프록시이자 사설 패키지 저장소다. 세 가지 구성 요소로 이루어져 있다.

| 구성 요소 | 역할 |
|-----------|------|
| **devpi-server** | PyPI 미러/사설 패키지 저장소 서버 |
| **devpi-client** | devpi 서버에 패키지 업로드/인덱스 관리 CLI |
| **devpi-web** | 웹 UI (선택 사항) |

### 인덱스 체이닝 (bases)

devpi의 핵심 기능은 **인덱스(index)** 단위의 패키지 관리와 **체이닝(chaining)**이다. 각 인덱스는 독립된 PyPI 저장소처럼 동작하며, `bases` 설정으로 상위 인덱스를 지정할 수 있다.

```
root/pypi          ← 외부 pypi.org를 캐싱하는 미러 인덱스 (기본 제공, 업로드 불가)
  ↑ bases
root/prod          ← 사내 패키지를 올리는 인덱스 (업로드 가능)
```

`bases`는 **"이 인덱스에 패키지가 없으면, 여기서 찾아봐"**라는 상위 인덱스 지정이다. 체이닝이 가능하여, 하위 인덱스에서 상위 인덱스까지 순서대로 탐색한다.

```
pip install requests
  → root/prod에 requests 있나? → 없음
  → bases인 root/pypi에 있나? → 있음 (pypi.org에서 캐시) → 설치
```

| 인덱스 | 타입 | 용도 | 업로드 |
|--------|------|------|:---:|
| `root/pypi` | mirror | 외부 pypi.org의 캐싱 미러 | X |
| `root/prod` | stage | 사내 패키지 저장소 | O |

이 구조의 장점은, `root/prod`에 사내 패치 버전의 패키지를 올리면 내부 사용자는 자동으로 패치 버전을 받고, 나머지 패키지는 공식 PyPI에서 캐시되어 내려온다는 것이다. 하나의 인덱스 URL(`root/prod`)만 설정하면 **로컬 패키지 + 공개 PyPI 패키지를 모두 사용**할 수 있다.

```
클라이언트(pip)는 하나의 URL만 알면 됨:
  pip install --index-url http://admin:3141/root/prod/+simple/ requests
  → devpi 서버가 root/prod → root/pypi 순서로 알아서 찾아줌
```

> Nexus나 Artifactory도 서버 측 체이닝을 지원하지만, PyPI뿐 아니라 Maven, npm, Docker 등을 함께 관리하는 범용 도구라 무겁다. PyPI 전용으로 가볍게 쓸 수 있으면서 네이티브 인덱스 체이닝을 지원하는 도구는 devpi가 거의 유일하다. pypiserver 같은 가벼운 도구는 서버 측 체이닝이 없어서 `pip`의 `--extra-index-url`로 클라이언트 측에서 처리해야 하는데, 우선순위 제어가 불편하고 보안 이슈(dependency confusion)가 생길 수 있다.

### +simple 엔드포인트

devpi 서버의 URL에는 두 가지 접근 경로가 있다.

| URL | 용도 |
|-----|------|
| `http://192.168.10.10:3141/root/prod` | 웹 UI (사람이 브라우저로 탐색) |
| `http://192.168.10.10:3141/root/prod/+simple` | **pip 전용 API 엔드포인트** (PEP 503 Simple API) |

pip 설정에서는 반드시 **`+simple`이 붙은 URL**을 사용해야 한다. `+simple` 없이 접근하면 pip이 패키지 목록을 파싱할 수 없다.

## pip 클라이언트 설정

pip이 사설 PyPI 서버를 사용하도록 설정하는 방법은 두 가지가 있다.

### 일회성 사용

```bash
pip install jmespath \
  --index-url http://192.168.10.10:3141/root/prod/+simple \
  --trusted-host 192.168.10.10
```

| 옵션 | 의미 |
|------|------|
| `--index-url` | 패키지를 검색할 PyPI 서버 URL |
| `--trusted-host` | HTTPS 인증서 검증을 건너뛸 호스트 (HTTP 서버 사용 시 필요) |

### 전역 설정 (pip.conf)

```ini
# /etc/pip.conf (시스템 전역) 또는 ~/.config/pip/pip.conf (사용자별)
[global]
index-url = http://192.168.10.10:3141/root/prod/+simple
trusted-host = 192.168.10.10
timeout = 60
```

전역 설정을 하면 이후 모든 `pip install` 명령이 자동으로 사설 서버를 사용한다. `--index-url`을 매번 지정할 필요가 없다.

> `trusted-host`가 필요한 이유는 사설 서버가 HTTP로 동작하기 때문이다. pip은 기본적으로 HTTPS만 신뢰하므로, HTTP 서버를 사용하려면 명시적으로 신뢰 호스트로 등록해야 한다. [이전 글(8.1.4)]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-04 %})의 insecure registry 설정과 동일한 맥락이다.

<br>

# 실습

| 순서 | 위치 | 작업 | 목적 |
|------|------|------|------|
| 1 | admin | devpi-server 설치 + 기동 | 사설 PyPI 서버 구축 |
| 2 | admin | 인덱스 생성 + 패키지 업로드 | 폐쇄망 필요 패키지 등록 |
| 3 | k8s-node | pip.conf 설정 + 패키지 설치 | 사설 PyPI 서버 사용 확인 |
| 4 | admin, k8s-node | 정리 | 이후 실습을 위한 원복 |

## 1. [admin] devpi-server 설치 및 기동

### 패키지 설치

```bash
root@admin:~# pip install devpi-server devpi-client devpi-web

# 실행 결과 (일부)
Collecting devpi-server
  Downloading devpi_server-6.19.0-py3-none-any.whl.metadata (8.9 kB)
Collecting devpi-client
  Downloading devpi_client-7.2.0-py3-none-any.whl.metadata (5.8 kB)
Collecting devpi-web
  Downloading devpi_web-5.0.1-py3-none-any.whl.metadata (6.0 kB)
...
Successfully installed ... devpi-client-7.2.0 devpi-server-6.19.0 devpi-web-5.0.1 ...
```

```bash
root@admin:~# pip list | grep devpi
devpi-client              7.2.0
devpi-common              4.1.0
devpi-server              6.19.0
devpi-web                 5.0.1
```

| 패키지 | 용도 |
|--------|------|
| `devpi-server` | PyPI 미러/사설 패키지 저장소 서버 |
| `devpi-client` | 서버에 로그인, 인덱스 생성, 패키지 업로드 등 관리 CLI |
| `devpi-web` | 웹 UI. 브라우저에서 패키지를 탐색하고 검색 가능 (선택) |
| `devpi-common` | server/client/web의 공통 라이브러리 (자동 설치) |

> root로 `pip install`하면 시스템 전역 Python 경로(`/usr/lib/python3.x/site-packages/`)에 설치되어 OS 패키지 매니저(dnf)와 충돌할 수 있다는 경고가 나온다. 실무에서는 `python3 -m venv`로 가상환경을 만들어 사용하는 것이 권장되지만, 일회성 실습 VM이므로 무시해도 된다.

### 서버 초기화

```bash
# 데이터 디렉토리 생성 및 초기화
root@admin:~# devpi-init --serverdir /data/devpi_data
2026-02-09 21:11:49,939 INFO  NOCTX Loading node info from /data/devpi_data/.nodeinfo
2026-02-09 21:11:49,940 INFO  NOCTX generated uuid: b2cbac63b4384c31954af796058dec06
2026-02-09 21:11:49,940 INFO  NOCTX wrote nodeinfo to: /data/devpi_data/.nodeinfo
2026-02-09 21:11:49,943 INFO  NOCTX DB: Creating schema
2026-02-09 21:11:50,027 INFO  [Wtx-1] setting password for user 'root'
2026-02-09 21:11:50,027 INFO  [Wtx-1] created user 'root'
2026-02-09 21:11:50,027 INFO  [Wtx-1] created root user
2026-02-09 21:11:50,027 INFO  [Wtx-1] created root/pypi index
2026-02-09 21:11:50,030 INFO  [Wtx-1] fswriter0: committed at 0

root@admin:~# ls -al /data/devpi_data/
total 28
drwxr-xr-x. 2 root root    60 Feb  9 21:11 .
drwxr-xr-x. 5 root root    53 Feb  9 21:11 ..
-rw-------. 1 root root    72 Feb  9 21:11 .nodeinfo
-rw-r--r--. 1 root root     1 Feb  9 21:11 .serverversion
-rw-r--r--. 1 root root 20480 Feb  9 21:11 .sqlite
```

`devpi-init`은 서버 데이터 디렉토리를 초기화한다. `--serverdir`을 지정하지 않으면 기본값은 `~/.devpi/server`다. 초기화 시 `root` 사용자와 `root/pypi` 인덱스(외부 PyPI 미러)가 자동으로 생성된다.

### 서버 기동

```bash
# 백그라운드로 devpi-server 기동
root@admin:~# nohup devpi-server \
  --serverdir /data/devpi_data \
  --host 0.0.0.0 \
  --port 3141 \
  > /var/log/devpi.log 2>&1 &
[1] 10519
```

| 옵션 | 의미 |
|------|------|
| `--serverdir` | 데이터 디렉토리 경로 |
| `--host 0.0.0.0` | 모든 네트워크 인터페이스에서 접속 허용 (외부 접근 가능) |
| `--port 3141` | 리스닝 포트 (기본값: 3141, 파이 π ≈ 3.141의 유머) |

> 프로덕션에서는 systemd 서비스로 등록하여 상시 구동하는 것이 바람직하다. 이 실습에서는 `nohup`으로 간단히 백그라운드 실행한다.

### 동작 확인

```bash
# 포트 리스닝 확인
root@admin:~# ss -tnlp | grep devpi-server
LISTEN 0      1024         0.0.0.0:3141      0.0.0.0:*    users:(("devpi-server",pid=10519,fd=8))

# 로그 확인
root@admin:~# tail -f /var/log/devpi.log
2026-02-09 21:12:58,236 INFO  [IDX] Indexer queue size ~ 31
2026-02-09 21:12:59,885 INFO  [IDX] Committing 2500 new documents to search index.
2026-02-09 21:13:03,875 INFO  [IDX] Indexer queue size ~ 80
...
```

devpi-web을 설치했으므로, 브라우저에서 `http://192.168.10.10:3141`에 접속하면 웹 UI를 확인할 수 있다.

![devpi 웹 UI - root/pypi 인덱스](/assets/images/devpi-web-root-pypi-index.png)

## 2. [admin] 인덱스 생성 및 패키지 업로드

### devpi 서버 연결 및 로그인

```bash
# 서버 연결
root@admin:~# devpi use http://192.168.10.10:3141
Warning: insecure http host, trusted-host will be set for pip
using server: http://192.168.10.10:3141/ (not logged in)
no current index: type 'devpi use -l' to discover indices
...

# 로그인 (초기 root 비밀번호는 빈 문자열)
root@admin:~# devpi login root --password ""
logged in 'root', credentials valid for 10.00 hours
```

### 인덱스 생성

`root/prod` 인덱스를 생성하고, `bases=root/pypi`로 체이닝을 설정한다. 이렇게 하면 `root/prod`에 없는 패키지는 자동으로 `root/pypi`(외부 PyPI 캐시)에서 탐색한다.

```bash
# prod 인덱스 생성 (bases=root/pypi로 체이닝)
root@admin:~# devpi index -c prod bases=root/pypi
http://192.168.10.10:3141/root/prod?no_projects=:
      type=stage
      bases=root/pypi
      volatile=True
      acl_upload=root
      acl_toxresult_upload=:ANONYMOUS:
      mirror_whitelist=
  mirror_whitelist_inheritance=intersection

# 인덱스 목록 확인
root@admin:~# devpi index -l
root/prod
root/pypi
```

![devpi 웹 UI - root/prod, root/pypi 인덱스 목록](/assets/images/devpi-web-root-indices.png)

| 인덱스 | 타입 | 설명 |
|--------|------|------|
| `root/pypi` | mirror | 외부 pypi.org 캐싱 미러 (자동 생성, 업로드 불가) |
| `root/prod` | stage | 사내 패키지 저장소 (업로드 가능, root/pypi 체이닝) |

### 패키지 다운로드 및 업로드

kubespray 실행에 필요한 Python 패키지를 미리 다운로드하여 `root/prod` 인덱스에 업로드한다.

```bash
# 필요한 패키지 다운로드
root@admin:~# pip download jmespath netaddr -d /tmp/pypi-packages
...
root@admin:~# tree /tmp/pypi-packages/
/tmp/pypi-packages/
├── jmespath-1.1.0-py3-none-any.whl
└── netaddr-1.3.0-py3-none-any.whl
```

| 패키지 | 용도 |
|--------|------|
| `jmespath` | JSON 데이터 검색/필터링 쿼리 언어. Ansible이 JSON 필터링에 사용 |
| `netaddr` | IP 주소/네트워크 주소 계산 라이브러리. Ansible이 네트워크 변수 처리에 사용 |

```bash
# root/prod 인덱스로 전환
root@admin:~# devpi use root/prod

# 패키지 업로드
root@admin:~# devpi upload /tmp/pypi-packages/*
file_upload of jmespath-1.1.0-py3-none-any.whl to http://192.168.10.10:3141/root/prod/
file_upload of netaddr-1.3.0-py3-none-any.whl to http://192.168.10.10:3141/root/prod/

# 업로드된 패키지 확인
root@admin:~# devpi list
jmespath
netaddr
```

### Troubleshooting: root/pypi에 업로드 시 에러

`devpi use`로 `root/pypi` 인덱스를 선택한 상태에서 업로드하면 다음과 같은 에러가 발생한다.

```bash
root@admin:~# devpi use root/pypi
Warning: insecure http host, trusted-host will be set for pip
current devpi index: http://192.168.10.10:3141/root/pypi (logged in as root)
...

root@admin:~# devpi upload /tmp/pypi-packages/*
The current index http://192.168.10.10:3141/root/pypi does not support upload.
Most likely, it is a mirror.
```

`root/pypi`는 mirror 타입이라 업로드가 불가능하다. `devpi use root/prod`로 인덱스를 전환한 뒤 업로드해야 한다. `root/prod`는 `bases=root/pypi`로 체이닝되어 있으므로, 직접 업로드한 패키지와 PyPI 미러 패키지를 모두 탐색할 수 있다.

업로드된 패키지의 실제 저장 위치를 확인한다.

```bash
root@admin:~# tree /data/devpi_data/+files/
/data/devpi_data/+files/
    └── root
        └── prod
            └── +f
                ├── a56
                │   └── 63118de4908c9
                │       └── jmespath-1.1.0-py3-none-any.whl
                └── c2c
                    └── 6a8ebe5554ce3
                    └── netaddr-1.3.0-py3-none-any.whl
```

devpi는 패키지를 콘텐츠 주소(content-addressable) 방식으로 저장한다. 파일명의 SHA256 해시를 디렉토리 경로로 사용하여 중복 저장을 방지한다.

![devpi 웹 UI - netaddr 검색 결과](/assets/images/devpi-web-search-netaddr.png)

## 3. [k8s-node] pip 설정 및 패키지 설치

k8s-node에서 admin의 devpi-server를 PyPI 저장소로 사용하도록 설정한다.

### pip.conf 전역 설정

```bash
# pip 전역 설정 파일 생성
root@week06-week06-k8s-node1:~# cat <<EOF > /etc/pip.conf
[global]
index-url = http://192.168.10.10:3141/root/prod/+simple
trusted-host = 192.168.10.10
timeout = 60
EOF
```

| 설정 | 의미 |
|------|------|
| `index-url` | 패키지 검색 서버. 반드시 `+simple` 엔드포인트 사용 |
| `trusted-host` | HTTP 서버 신뢰 설정 (HTTPS 미사용 시 필요) |
| `timeout` | 연결 타임아웃 (초) |

### 업로드된 패키지 설치 테스트

`root/prod`에 직접 업로드한 패키지(`netaddr`)를 설치해 본다.

```bash
root@week06-week06-k8s-node1:~# pip list | grep -i netaddr
root@week06-week06-k8s-node1:~# pip install netaddr
Looking in indexes: http://192.168.10.10:3141/root/prod/+simple
Collecting netaddr
  Downloading http://192.168.10.10:3141/root/prod/%2Bf/c2c/6a8ebe5554ce3/netaddr-1.3.0-py3-none-any.whl (2.3 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2.3/2.3 MB 7.0 MB/s eta 0:00:00
Installing collected packages: netaddr
Successfully installed netaddr-1.3.0

root@week06-week06-k8s-node1:~# pip list | grep -i netaddr
netaddr                   1.3.0
```

`Looking in indexes: http://192.168.10.10:3141/root/prod/+simple`이 표시되어, `pip.conf`의 설정이 적용되고 있음을 확인할 수 있다. 다운로드 URL에 `/root/prod/` 경로가 포함되어 있으므로, admin의 사설 저장소에서 패키지를 가져온 것이다.

### 체이닝된 패키지 설치 테스트

`root/prod`에 직접 업로드하지 않은 패키지(`cryptography`)를 설치해 본다. `bases=root/pypi` 체이닝이 정상 동작하면, devpi가 자동으로 외부 PyPI에서 캐시하여 제공한다.

```bash
root@week06-week06-k8s-node1:~# pip install cryptography
Looking in indexes: http://192.168.10.10:3141/root/prod/+simple
Collecting cryptography
  Downloading http://192.168.10.10:3141/root/pypi/%2Bf/de0/f5f4ec8711ebc/cryptography-46.0.4-cp311-abi3-manylinux_2_34_aarch64.whl (4.3 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.3/4.3 MB 3.4 MB/s eta 0:00:00
Collecting cffi>=2.0.0 (from cryptography)
  Downloading http://192.168.10.10:3141/root/pypi/%2Bf/b21/e08af67b8a103/cffi-2.0.0-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.whl (220 kB)
Collecting pycparser (from cffi>=2.0.0->cryptography)
  Downloading http://192.168.10.10:3141/root/pypi/%2Bf/b72/7414169a36b7d/pycparser-3.0-py3-none-any.whl (48 kB)
Installing collected packages: pycparser, cffi, cryptography
Successfully installed cffi-2.0.0 cryptography-46.0.4 pycparser-3.0
```

다운로드 URL을 보면 `/root/pypi/` 경로에서 가져오고 있다. `root/prod`에는 `cryptography`가 없지만, **체이닝된 `root/pypi`에서 외부 PyPI를 캐시하여 자동으로 제공**한 것이다. 의존성 패키지(`cffi`, `pycparser`)도 함께 해결되었다.

| 패키지 | 출처 | 경로 |
|--------|------|------|
| `netaddr` | `root/prod` (직접 업로드) | `/root/prod/%2Bf/...` |
| `cryptography` | `root/pypi` (외부 PyPI 캐시) | `/root/pypi/%2Bf/...` |

### Troubleshooting: 체이닝 없이 외부 패키지 설치 시 에러

`root/prod` 인덱스에 `bases=root/pypi` 체이닝이 설정되어 있지 않으면, 직접 업로드한 패키지만 설치할 수 있다. 체이닝 없이 외부 패키지를 설치하면 다음과 같은 에러가 발생한다.

```bash
root@week06-week06-k8s-node1:~# pip install cryptography
Looking in indexes: http://192.168.10.10:3141/root/prod/+simple
ERROR: Could not find a version that satisfies the requirement cryptography (from versions: none)
ERROR: No matching distribution found for cryptography
```

`root/prod`에 `cryptography`가 없고, 상위 인덱스를 탐색할 체이닝도 없기 때문이다. `devpi index root/prod bases=root/pypi`로 체이닝을 설정하면 해결된다.

```bash
# admin에서 인덱스 설정 확인
root@admin:~# devpi index root/prod
http://192.168.10.10:3141/root/prod:
  type=stage
  bases=root/pypi        ← 이 설정이 있어야 외부 패키지 탐색 가능
  volatile=True
  acl_upload=root
  ...
```

## 4. 정리

이후 kubespray-offline 실습에서 다른 방식으로 PyPI 저장소를 구성할 예정이므로, 현재 구성을 정리한다.

### admin

```bash
# devpi-server 프로세스 종료
root@admin:~# pkill -f "devpi-server --serverdir /data/devpi_data"
```

### k8s-node

```bash
# pip 전역 설정 삭제
root@week06-week06-k8s-node1:~# rm -f /etc/pip.conf
```

<br>

# 정리

이번 글에서는 폐쇄망 환경에서 Python 패키지를 설치할 수 있도록 사설 PyPI 미러(devpi-server)를 구축했다.

| 순서 | 위치 | 작업 | 도구 |
|------|------|------|------|
| 1 | admin | devpi-server 설치 + 인덱스 생성 | `devpi-init`, `devpi index -c prod` |
| 2 | admin | 패키지 다운로드 + 업로드 | `pip download`, `devpi upload` |
| 3 | k8s-node | pip.conf 설정 + 패키지 설치 | `/etc/pip.conf`, `pip install` |

devpi의 인덱스 체이닝(`bases=root/pypi`) 덕분에, 직접 업로드한 패키지와 외부 PyPI 캐시 패키지를 하나의 인덱스 URL로 통합하여 사용할 수 있었다.

현재까지의 폐쇄망 인프라 구성 상태:

| 구성요소 | 상태 |
|----------|------|
| Network Gateway | 완료 ([8.1.1]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-01 %})) |
| NTP Server / Client | 완료 ([8.1.2]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-02 %})) |
| DNS Server / Client | 완료 ([8.1.2]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-02 %})) |
| Local Package Repository | 완료 ([8.1.3]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-03 %})) |
| Private Container Registry | 완료 ([8.1.4]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-04 %})) |
| Private PyPI Mirror | 완료 (본 글) |

이것으로 폐쇄망 기반 인프라의 모든 구성요소 구축이 완료되었다. 각 구성요소를 수동으로 하나씩 구축하며 원리를 익혔으므로, 이후 kubespray-offline이 이 과정을 어떻게 자동화하는지 이해하기 수월할 것이다.

<br>

# 참고 자료

- [PEP 503 – Simple Repository API](https://peps.python.org/pep-0503/)
- [devpi Documentation](https://devpi.net/docs/devpi/stable/)
- [devpi GitHub Repository](https://github.com/devpi/devpi)
- [pip Configuration](https://pip.pypa.io/en/stable/topics/configuration/)
- [PyPI - The Python Package Index](https://pypi.org/)

<br>
