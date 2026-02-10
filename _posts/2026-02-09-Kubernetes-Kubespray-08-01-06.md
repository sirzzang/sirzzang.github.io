---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 8. 오프라인 배포: The Hard Way - 6. Private Go Module Proxy"
excerpt: "폐쇄망 환경에서 Go 모듈 설치를 위한 사설 Go 모듈 프록시(Athens)를 구축해보자."
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
  - Go
  - Athens
  - GOPROXY
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-6

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 6주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 폐쇄망 환경에서 Go 모듈 설치를 위한 **사설 Go 모듈 프록시(Athens)**를 구축한다.

- **Athens 서버 구축**: admin에서 Athens를 컨테이너로 실행하고, 필요한 Go 모듈 캐싱
- **offline 모드 전환**: 캐시된 모듈만 서빙하도록 Athens를 offline 모드로 재시작
- **Go 클라이언트 설정**: k8s-node에서 admin의 Athens를 GOPROXY로 사용
- **정리**: 이후 kubespray-offline 실습을 위해 Athens 종료 및 설정 삭제

| 순서 | 위치 | 작업 | 목적 |
|------|------|------|------|
| 1 | admin | Athens 설치 + 온라인 모드 실행 | 사설 Go 모듈 프록시 서버 구축 |
| 2 | admin | 필요한 Go 모듈 캐싱 | 폐쇄망에서 필요한 모듈 사전 다운로드 |
| 3 | admin | offline 모드로 재시작 | 캐시된 모듈만 서빙하도록 전환 |
| 4 | k8s-node | Go 설치 + GOPROXY 설정 | 사설 Go 모듈 프록시 사용 확인 |
| 5 | admin, k8s-node | Athens 종료 + GOPROXY 설정 삭제 | 이후 실습을 위한 정리 |

<br>

# 사설 Go 모듈 프록시의 필요성

[이전 글(8.1.5)]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-05 %})에서 사설 PyPI 미러를 구축했다. 이번에는 **Go 모듈**을 폐쇄망에서 설치할 수 있어야 한다.

kubespray-offline이나 내부 Go 애플리케이션을 빌드할 때, **Go 모듈**을 미리 캐싱해두는 용도로 사용한다. 예를 들어 Helm 차트 관리 도구나 kubectl 플러그인을 직접 빌드하거나, Go 기반 모니터링 도구를 폐쇄망에서 컴파일해야 하는 경우다. 온라인 환경에서는 `go get`으로 공개 Go 모듈 프록시([proxy.golang.org](https://proxy.golang.org))에서 바로 설치하면 되지만, 폐쇄망에서는 이 서버에 접근할 수 없다.

```
[온라인]  k8s-node → proxy.golang.org → go get 모듈 다운로드
[폐쇄망]  k8s-node → admin (Athens, :3000) → 사설 Go 모듈 프록시에서 다운로드
```

[이전 글(8.1.3)]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-03 %})에서 구축한 로컬 YUM/DNF 저장소가 **리눅스 OS 패키지**(RPM)를 위한 것이고, [이전 글(8.1.5)]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-05 %})의 devpi-server가 **Python 패키지**(wheel/sdist)를 위한 것이라면, 이번에 구축하는 Athens는 **Go 모듈**(module)을 위한 동일한 역할이다.

| 저장소 | 대상 | 도구 | 프로토콜 |
|--------|------|------|----------|
| 로컬 YUM/DNF 저장소 | OS 패키지 (`.rpm`) | `dnf install` | HTTP (nginx) |
| 사설 PyPI 미러 | Python 패키지 (`.whl`) | `pip install` | HTTP (devpi-server) |
| 사설 Go 모듈 프록시 | Go 모듈 (`.mod`, `.zip`) | `go get` | HTTP (Athens) |

<br>

# 배경지식

## Go 모듈과 go get

**Go 모듈(module)**은 Go의 패키지 관리 단위다. Go 1.11부터 도입된 모듈 시스템은 의존성 관리를 `go.mod` 파일로 선언적으로 처리한다.

**go get**은 Go의 표준 패키지 관리 명령으로, 기본적으로 **VCS(버전 관리 시스템, GitHub, GitLab 등)에서 직접** 소스를 가져온다. 이 방식에는 몇 가지 문제가 있다.

- 원본 저장소가 삭제되거나 태그가 변경되면 빌드가 깨짐
- 매번 VCS에 접근하므로 느리고, rate limit에 걸릴 수 있음
- **폐쇄망에서는 외부 접근 자체가 불가능**

```
사용자: go get github.com/gin-gonic/gin
  ↓
go: GitHub에서 gin-gonic/gin 저장소 clone
  → go.mod 파싱하여 의존성 확인
  → 의존성 모듈도 각 VCS에서 다운로드
  → 설치
```

## Go Module Proxy

**Go Module Proxy**는 Go 모듈을 캐싱하고 배포하는 중간 서버다. VCS에 직접 접근하는 대신 프록시를 통해 모듈을 가져온다.

```
go get github.com/gin-gonic/gin

[일반 흐름]
  Go 클라이언트 → GitHub (직접 다운로드)

[프록시 사용 시]
  Go 클라이언트 → Go Module Proxy → (캐시 없으면) GitHub에서 가져와 캐싱
                               → (캐시 있으면) 캐시에서 즉시 응답
```

Go 클라이언트는 `GOPROXY` 환경변수로 프록시 서버 주소를 지정한다.

```bash
export GOPROXY=http://192.168.10.10:3000
```

### 공개 vs 사설 프록시

| 구분 | 예시 | 용도 |
|------|------|------|
| **공개 프록시** | `proxy.golang.org` (Go 기본값) | 인터넷 환경에서 캐싱/속도 향상 |
| **사설 프록시** | Athens, goproxy 등 자체 운영 | 폐쇄망, 사내 모듈 배포 |

Go의 기본 `GOPROXY` 값은 `https://proxy.golang.org,direct`다. `proxy.golang.org`는 Google이 운영하는 공개 모듈 프록시 서버이고, `direct`는 프록시에 모듈이 없으면 VCS에 직접 접근하라는 의미다.

### Go Module API

Go Module Proxy는 표준 API를 구현한다. 모든 Go 모듈 프록시(Athens, goproxy 등)는 이 API를 따른다.

```
GET /{module}/@v/list                → 모듈의 버전 목록
GET /{module}/@v/{version}.info      → 버전 메타데이터 (JSON)
GET /{module}/@v/{version}.mod       → go.mod 파일
GET /{module}/@v/{version}.zip       → 모듈 소스 zip
GET /{module}/@latest                → 최신 버전 정보
```

`go get`이 `go get github.com/gin-gonic/gin@v1.11.0`을 실행하면:

1. `github.com/gin-gonic/gin/@v/list` 엔드포인트에서 사용 가능한 버전 목록을 받음
2. `github.com/gin-gonic/gin/@v/v1.11.0.info`에서 버전 메타데이터 확인
3. `github.com/gin-gonic/gin/@v/v1.11.0.zip` 다운로드
4. 로컬에 설치

클라이언트(go get) 입장에서는 **Module API만 제공하면 어떤 서버든 동일하게 동작**한다.

```bash
# 기본 프록시 사용
go get github.com/gin-gonic/gin

# 사설 프록시 사용 (GOPROXY로 서버 주소만 변경)
export GOPROXY=http://192.168.10.10:3000
go get github.com/gin-gonic/gin
```

`GOPROXY`로 서버 주소만 바꾸면, go get은 공개 프록시든 사설 프록시든 동일한 방식으로 모듈을 가져온다.

## Go Module Proxy 구현체

Go Module Proxy를 구축하는 도구는 여러 가지가 있다.

| 도구 | 특징 | offline 모드 |
|------|------|:---:|
| **Athens** | Go 모듈 전용 캐싱 프록시. offline 모드 지원 | O |
| **goproxy** | 경량 Go 모듈 프록시. 단순하고 빠름 | O |
| **Nexus Repository** | 범용 아티팩트 저장소 (Go, Maven, npm, Docker 등 지원) | O |
| **JFrog Artifactory** | 범용 아티팩트 저장소. Virtual Repository로 체이닝 지원 | O |

이 실습에서는 **Athens**를 사용한다. Go 모듈 전용으로 가볍고, offline 모드를 네이티브로 지원하여 "인터넷이 될 때 외부 모듈을 캐시해두고, 폐쇄망에서는 캐시된 것만 서빙"하는 구성이 자연스럽기 때문이다.

## Athens

**Athens**는 Go 모듈 캐싱 프록시다. 외부에서 모듈을 가져와 캐싱하고, **offline 모드**로 설정하면 캐시된 모듈만 서빙할 수 있어서 폐쇄망에 적합하다.

### 동작 모드

Athens는 두 가지 모드로 동작한다.

```
[온라인 모드]
  go get gin → Athens → (캐시 없음) → GitHub/proxy.golang.org → 캐싱 → 응답

[offline 모드]
  go get gin → Athens → (캐시 확인) → 있으면 응답, 없으면 404
```

| 모드 | 동작 | 용도 |
|------|------|------|
| **온라인 모드** | 캐시에 없는 모듈을 upstream(VCS, proxy.golang.org)에서 가져와 캐싱 | 초기 모듈 캐싱 |
| **offline 모드** | 캐시된 모듈만 서빙. 외부 접근 차단 | 폐쇄망 운영 |


### 환경변수

| 변수 | 값 | 의미 |
|------|-----|------|
| `ATHENS_STORAGE_TYPE` | `disk` | 캐시 저장소 타입 (disk, memory, s3 등) |
| `ATHENS_DISK_STORAGE_ROOT` | `/var/lib/athens` | 디스크 캐시 저장 경로 |
| `ATHENS_NETWORK_MODE` | `offline` | offline 모드 활성화 (외부 VCS 접근 차단) |
| `ATHENS_DOWNLOAD_MODE` | `none` | 새 모듈 다운로드 시도 안 함 |

## GOPROXY 환경변수

Go 클라이언트가 사설 프록시를 사용하도록 설정하는 방법은 두 가지가 있다.

### 일회성 사용

```bash
export GOPROXY=http://192.168.10.10:3000
export GONOSUMDB=*
go get github.com/gin-gonic/gin
```

| 변수 | 의미 |
|------|------|
| `GOPROXY` | 모듈을 검색할 프록시 서버 URL |
| `GONOSUMDB` | checksum database 검증을 건너뛸 모듈 패턴 (`*`는 모두 건너뛰기) |

### 전역 설정 (profile)

```bash
# /etc/profile.d/go-proxy.sh (시스템 전역)
export GOPROXY=http://192.168.10.10:3000
export GONOSUMDB=*
```

전역 설정을 하면 이후 모든 `go get` 명령이 자동으로 사설 프록시를 사용한다. `GOPROXY`를 매번 지정할 필요가 없다.

> `GONOSUMDB=*`가 필요한 이유는 사설 프록시가 Go의 공식 checksum database(sum.golang.org)와 연동되지 않기 때문이다. [이전 글(8.1.5)]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-05 %})의 `trusted-host` 설정과 동일한 맥락이다.

<br>

# 실습

| 순서 | 위치 | 작업 | 목적 |
|------|------|------|------|
| 1 | admin | Athens 설치 + 온라인 모드 실행 | 사설 Go 모듈 프록시 서버 구축 |
| 2 | admin | 필요한 Go 모듈 캐싱 | 폐쇄망에서 필요한 모듈 사전 다운로드 |
| 3 | admin | offline 모드로 재시작 | 캐시된 모듈만 서빙하도록 전환 |
| 4 | k8s-node | Go 설치 + GOPROXY 설정 | 사설 Go 모듈 프록시 사용 확인 |
| 5 | admin, k8s-node | Athens 종료 + GOPROXY 설정 삭제 | 이후 실습을 위한 정리 |

## 1. [admin] Athens 설치 및 기동 (온라인 모드)

Athens는 컨테이너 이미지로 제공되므로, podman을 사용하여 실행한다.

### 모듈 저장 디렉토리 생성

```bash
root@admin:~# mkdir -p /data/athens-storage
```

Athens는 캐시된 모듈을 디스크에 저장한다. 디렉토리를 미리 생성하지 않으면 컨테이너가 시작 시 에러로 종료된다.

### 컨테이너 실행

Athens 컨테이너를 온라인 모드로 실행한다. 이 단계에서는 인터넷 접근이 가능해야 하므로, `--network host`를 사용하여 호스트 네트워크를 직접 사용한다.

```bash
root@admin:~# podman run -d \
  --name athens \
  --network host \
  -v /data/athens-storage:/var/lib/athens \
  -e ATHENS_DISK_STORAGE_ROOT=/var/lib/athens \
  -e ATHENS_STORAGE_TYPE=disk \
  -e ATHENS_PORT=:3000 \
  docker.io/gomods/athens:latest

Trying to pull docker.io/gomods/athens:latest...
Getting image source signatures
Copying blob 964a2c7bdd02 done   |
Copying blob 7764deb7d5b3 done   |
Copying blob 5af85bede67d done   |
Copying blob 32a3f0bdc711 done   |
Copying blob d8ad8cd72600 skipped: already exists
Copying blob 780258d8c79e done   |
Copying blob 64619a1c732a done   |
Copying blob 10304b5b7693 done   |
Copying blob 9ea8a5bc68b4 done   |
Copying config 70407182aa done   |
Writing manifest to image destination
853fe4657f13d5148afa7e9613e0851d765e76a430ae0058bfbc53f66488db2a
```

| 옵션 | 의미 |
|------|------|
| `--network host` | 호스트 네트워크 사용. DNS 및 외부 접근을 위해 필요 |
| `-v /data/athens-storage:/var/lib/athens` | 호스트 디렉토리를 컨테이너 캐시 경로로 마운트 |
| `-e ATHENS_STORAGE_TYPE=disk` | 캐시 저장소 타입을 디스크로 지정 |
| `-e ATHENS_DISK_STORAGE_ROOT=/var/lib/athens` | 디스크 캐시 저장 경로 |
| `-e ATHENS_PORT=:3000` | 리스닝 포트 (기본값: 3000) |

> `--network host`를 사용하는 이유는 Athens가 upstream(proxy.golang.org, GitHub 등)에서 모듈을 가져올 때 DNS resolve와 외부 인터넷 접근이 필요하기 때문이다. podman 기본 브릿지 네트워크를 사용하면 DNS가 정상 동작하지 않을 수 있다. [이전 글(8.1.2)]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-02 %})에서 구성한 bind DNS 서버의 `allow-query` 설정이 podman 브릿지 대역(10.88.0.0/16)을 포함하지 않으면 DNS 질의가 거부된다.

### 동작 확인

```bash
root@admin:~# curl http://192.168.10.10:3000
<!DOCTYPE html>
<html>
<head>
	<meta charset="utf-8"></meta>
	<title>Athens</title>
	...
<body>

	<h1>Welcome to Athens</h1>

	<h2>Configuring your client</h2>
	<pre>GOPROXY=http://192.168.10.10:3000,direct</pre>

	<h2>How to use the Athens API</h2>
	<p>Use the <a href="/catalog">catalog</a> endpoint to get a list of all modules in the proxy</p>
	...
</body>
</html>
```

Athens 서버가 정상적으로 실행되었다. 브라우저에서 `http://192.168.10.10:3000`에 접속하면 Athens 웹 페이지를 확인할 수 있다.

![Athens 웹 UI](/assets/images/athens.png)

### Troubleshooting: /var/lib/athens 디렉토리 없음

호스트에 `/data/athens-storage` 디렉토리를 생성하지 않고 컨테이너를 실행하면 다음과 같은 에러로 종료된다.

```bash
root@admin:~# podman logs athens
INFO[10:57AM]: Exporter not specified. Traces won't be exported
FATAL[10:57AM]: Could not create App	error=getting storage configuration: could not create new storage from os fs (root directory `/var/lib/athens` does not exist)
```

podman 볼륨 마운트는 호스트 디렉토리가 존재해야 정상 동작한다. `mkdir -p /data/athens-storage`로 디렉토리를 생성한 후 컨테이너를 재시작한다.

```bash
root@admin:~# mkdir -p /data/athens-storage
root@admin:~# podman rm athens
root@admin:~# podman run -d \
  --name athens \
  --network host \
  -v /data/athens-storage:/var/lib/athens \
  -e ATHENS_DISK_STORAGE_ROOT=/var/lib/athens \
  -e ATHENS_STORAGE_TYPE=disk \
  -e ATHENS_PORT=:3000 \
  docker.io/gomods/athens:latest
```

### Troubleshooting: DNS resolve 실패

Athens 컨테이너가 podman 기본 브릿지 네트워크를 사용하면, 컨테이너 내부에서 DNS resolve가 실패할 수 있다.

```bash
root@admin:/tmp/go-cache-test# go get github.com/gin-gonic/gin@latest
go: github.com/gin-gonic/gin@latest: module github.com/gin-gonic: reading http://192.168.10.10:3000/github.com/gin-gonic/@v/list: 500 Internal Server Error
```

Athens 컨테이너 내부에서 DNS 테스트를 해보면 아래와 같은 현상이 목격된다.

```bash
root@admin:~# podman exec -it athens nslookup proxy.golang.org
Server:		192.168.10.10
Address:	192.168.10.10:53

** server can't find proxy.golang.org: REFUSED
```

`REFUSED`는 DNS 서버(192.168.10.10의 bind)가 쿼리를 거부했다는 뜻이다. [이전 글(8.1.2)]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-02 %})의 `named.conf` 설정을 보면:

```
allow-query     { 127.0.0.1; 192.168.10.0/24; };
allow-recursion { 127.0.0.1; 192.168.10.0/24; };
```

podman 기본 브릿지 네트워크를 사용하면 컨테이너 IP가 `10.88.0.x` 대역이므로, `192.168.10.0/24`에 해당하지 않아 bind가 DNS 질의를 거부한다.

**해결 방법**: `--network host`로 컨테이너를 실행한다. 컨테이너가 호스트 네트워크를 직접 사용하므로 DNS 질의 출발지가 `127.0.0.1`이 되어 bind가 허용한다.

```bash
root@admin:~# podman stop athens && podman rm athens

root@admin:~# podman run -d \
  --name athens \
  --network host \
  -v /data/athens-storage:/var/lib/athens \
  -e ATHENS_DISK_STORAGE_ROOT=/var/lib/athens \
  -e ATHENS_STORAGE_TYPE=disk \
  -e ATHENS_PORT=:3000 \
  docker.io/gomods/athens:latest
```

### Troubleshooting: DNSSEC 검증 실패

VM이 2일 이상 실행 상태로 유지되면, bind DNS 서버의 **DNSSEC 트러스트 앵커**가 만료되어 DNS resolve가 실패할 수 있다.

```bash
root@admin:~# curl -LO https://go.dev/dl/go1.25.5.linux-arm64.tar.gz
curl: (6) Could not resolve host: go.dev

root@admin:~# dig +short go.dev
;; communications error to 192.168.10.10#53: timed out
```

bind 로그를 확인하면:

```bash
root@admin:~# journalctl -u named -n 20
Feb 10 23:22:45 admin named[7674]: broken trust chain resolving 'go.dev/A/IN': 8.8.8.8#53
Feb 10 23:23:24 admin named[7674]: no valid RRSIG resolving 'go.dev/DS/IN': 168.126.63.1#53
Feb 10 23:23:24 admin named[7674]:   validating dev/SOA: got insecure response; parent indicates it should be secure
```

`named.conf`에 `dnssec-validation yes`로 설정되어 있어서, bind가 DNS 응답의 DNSSEC 서명을 검증하려고 하는데, forwarder(168.126.63.1, 8.8.8.8)를 통해 받은 응답의 DNSSEC 트러스트 체인이 깨져있어서 검증에 실패한다.

**해결 방법**: 실습 환경에서는 `dnssec-validation no`로 설정하여 DNSSEC 검증을 비활성화한다.

```bash
root@admin:~# sed -i 's/dnssec-validation yes/dnssec-validation no/' /etc/named.conf
root@admin:~# systemctl restart named

root@admin:~# dig +short go.dev
216.239.32.21
216.239.34.21
216.239.36.21
216.239.38.21
```

> **DNSSEC 트러스트 앵커**는 DNSSEC 서명 체인의 최상위 출발점(루트 DNS의 공개키)이다. `dnssec-validation yes`는 관리자가 수동으로 트러스트 앵커를 관리해야 하는데, 키가 바뀌면 수동 갱신이 필요하다. 프로덕션에서는 `dnssec-validation auto`를 사용하여 RFC 5011 자동 갱신으로 트러스트 앵커를 알아서 업데이트하는 것이 권장된다.

## 2. [admin] 필요한 Go 모듈 캐싱

인터넷이 되는 상태에서, 폐쇄망 노드에서 사용할 Go 모듈을 미리 다운로드하여 Athens에 캐싱한다.

### Go 설치

```bash
root@admin:~# dnf install -y golang

# 실행 결과 (일부)
Last metadata expiration check: 0:04:21 ago on Tue 10 Feb 2026 07:10:33 PM KST.
Dependencies resolved.
==========================================================================================================
 Package                     Architecture      Version                          Repository           Size
==========================================================================================================
Installing:
 golang                      aarch64           1.25.5-1.el10_1                  appstream           1.2 M
Installing dependencies:
 golang-bin                  aarch64           1.25.5-1.el10_1                  appstream            33 M
 golang-race                 aarch64           1.25.5-1.el10_1                  appstream           1.6 M
 golang-src                  noarch            1.25.5-1.el10_1                  appstream            11 M
...
Complete!

root@admin:~# go version
go version go1.25.5 (Red Hat 1.25.5-1.el10_1) linux/arm64
```

### GOPROXY 설정

admin에서 `go get`을 실행할 때 Athens를 사용하도록 GOPROXY 환경변수를 설정한다.

```bash
root@admin:~# export GOPROXY=http://192.168.10.10:3000
root@admin:~# export GONOSUMDB=*
root@admin:~# export GOINSECURE=*
```

| 변수 | 의미 |
|------|------|
| `GOPROXY` | Athens 프록시 주소 |
| `GONOSUMDB` | checksum database 검증 건너뛰기 |
| `GOINSECURE` | HTTPS 대신 HTTP 허용 |

### 테스트 프로젝트 생성 및 모듈 캐싱

```bash
root@admin:~# mkdir -p /tmp/go-cache-test && cd /tmp/go-cache-test
root@admin:/tmp/go-cache-test# go mod init test-cache
go: creating new go.mod: module test-cache

root@admin:/tmp/go-cache-test# go get github.com/gin-gonic/gin@latest
go: downloading github.com/gin-gonic/gin v1.11.0
go: downloading github.com/gin-contrib/sse v1.1.0
go: downloading github.com/mattn/go-isatty v0.0.20
go: downloading github.com/quic-go/quic-go v0.54.0
go: downloading golang.org/x/net v0.42.0
go: downloading github.com/bytedance/sonic v1.14.0
go: downloading github.com/goccy/go-json v0.10.2
go: downloading github.com/json-iterator/go v1.1.12
...
go: added github.com/gin-gonic/gin v1.11.0
go: added golang.org/x/net v0.42.0
go: added golang.org/x/text v0.27.0
go: added golang.org/x/tools v0.34.0
go: added google.golang.org/protobuf v1.36.9

root@admin:/tmp/go-cache-test# go get google.golang.org/grpc@latest
go: downloading google.golang.org/grpc v1.78.0
...
go: added google.golang.org/genproto/googleapis/rpc v0.0.0-20251029180050-ab9386a59fda
go: added google.golang.org/grpc v1.78.0
go: upgraded google.golang.org/protobuf v1.36.9 => v1.36.10
```

`go get`을 실행하면 Athens가 upstream(proxy.golang.org, GitHub)에서 모듈을 가져와 캐싱한다. 의존성 패키지도 자동으로 다운로드된다.

### 캐시 확인

```bash
root@admin:/tmp/go-cache-test# ls -al /data/athens-storage/
total 4
drwxr-xr-x.  7 root root  102 Feb 10 20:05 .
drwxr-xr-x.  6 root root   75 Feb 10 19:12 ..
drwxr-xr-x. 22 root root 4096 Feb 10 20:05 github.com
drwxr-xr-x.  3 root root   15 Feb 10 20:04 golang.org
drwxr-xr-x.  5 root root   50 Feb 10 20:06 google.golang.org
drwxr-xr-x.  4 root root   37 Feb 10 20:05 gopkg.in
drwxr-xr-x.  3 root root   18 Feb 10 20:05 go.uber.org
```

Athens는 모듈을 `{storage-root}/{module-path}/{version}/` 구조로 저장한다. 각 버전 디렉토리에는 `.info`, `.mod`, `.zip` 파일이 포함된다.

```bash
root@admin:/tmp/go-cache-test# ls /data/athens-storage/github.com/gin-gonic/gin/
v1.11.0

root@admin:/tmp/go-cache-test# ls /data/athens-storage/github.com/gin-gonic/gin/v1.11.0/
go.mod  info  source.zip
```

### 간단한 애플리케이션 테스트

실제로 모듈이 정상적으로 동작하는지 테스트해본다.

```bash
root@admin:/tmp/go-cache-test# cat << 'EOF' > main.go
package main

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

func main() {
	r := gin.Default()

	r.GET("/ping", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"message": "pong",
		})
	})

	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"status": "ok",
		})
	})

	r.Run(":8080")
}
EOF

root@admin:/tmp/go-cache-test# go mod tidy
go: downloading github.com/stretchr/testify v1.11.1
go: downloading github.com/google/go-cmp v0.7.0
go: downloading github.com/davecgh/go-spew v1.1.1
go: downloading github.com/go-playground/assert/v2 v2.2.0
go: downloading github.com/pmezard/go-difflib v1.0.0
go: downloading gopkg.in/yaml.v3 v3.0.1

root@admin:/tmp/go-cache-test# go run main.go &
[1] 12345
[GIN-debug] [WARNING] Creating an Engine instance with the Logger and Recovery middleware already attached.
[GIN-debug] [WARNING] Running in "debug" mode. Switch to "release" mode in production.
[GIN-debug] GET    /ping                     --> main.main.func1 (3 handlers)
[GIN-debug] GET    /health                   --> main.main.func2 (3 handlers)
[GIN-debug] Listening and serving HTTP on :8080

root@admin:/tmp/go-cache-test# curl localhost:8080/ping
{"message":"pong"}

root@admin:/tmp/go-cache-test# curl localhost:8080/health
{"status":"ok"}

root@admin:/tmp/go-cache-test# kill %1
```

Athens 프록시를 통해 다운로드한 모듈이 정상적으로 동작한다.

## 3. [admin] offline 모드로 전환

모듈 캐싱이 완료되면, Athens를 **offline 모드**로 재시작한다. offline 모드에서는 외부 VCS에 접근하지 않고 캐시된 모듈만 서빙한다.

### 컨테이너 재시작

```bash
root@admin:~# podman stop athens && podman rm athens
athens
athens

root@admin:~# podman run -d \
  --name athens \
  -p 3000:3000 \
  -v /data/athens-storage:/var/lib/athens \
  -e ATHENS_DISK_STORAGE_ROOT=/var/lib/athens \
  -e ATHENS_STORAGE_TYPE=disk \
  -e ATHENS_NETWORK_MODE=offline \
  -e ATHENS_DOWNLOAD_MODE=none \
  --restart always \
  docker.io/gomods/athens:latest
b18e258657648451e85b32454d1e5c80ff2b93a61a85223cbff17db9724caf76
```

| 변수 | 값 | 의미 |
|------|-----|------|
| `ATHENS_NETWORK_MODE` | `offline` | offline 모드 활성화 (외부 VCS 접근 차단) |
| `ATHENS_DOWNLOAD_MODE` | `none` | 새 모듈 다운로드 시도 안 함 |
| `--restart always` | - | 컨테이너 재시작 정책 (항상 재시작) |

> offline 모드에서는 `--network host`가 필요 없다. 외부 인터넷 접근이 불필요하므로 기본 브릿지 네트워크를 사용해도 된다.

### 동작 확인

```bash
root@admin:~# podman ps
CONTAINER ID  IMAGE                           COMMAND               CREATED        STATUS        PORTS                   NAMES
b18e25865764  docker.io/gomods/athens:latest  athens-proxy -con...  5 seconds ago  Up 4 seconds  0.0.0.0:3000->3000/tcp  athens

root@admin:~# curl http://192.168.10.10:3000
<!DOCTYPE html>
<html>
...
	<h1>Welcome to Athens</h1>
...
</html>
```

## 4. [k8s-node] Go 설치 및 GOPROXY 설정

k8s-node에서 admin의 Athens를 GOPROXY로 사용하도록 설정한다.

### Go 설치

k8s-node는 폐쇄망이므로 yum/dnf 저장소를 사용할 수 없다. admin에서 Go 공식 tarball을 다운로드한 후 scp로 복사하여 수동 설치한다.

```bash
# [admin] Go tarball 다운로드 및 복사
root@admin:~# curl -LO https://go.dev/dl/go1.25.5.linux-arm64.tar.gz
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100    75  100    75    0     0    180      0 --:--:-- --:--:-- --:--:--   179
100 54.6M  100 54.6M    0     0  19.0M      0  0:00:02  0:00:02 --:--:-- 27.5M

root@admin:~# scp go1.25.5.linux-arm64.tar.gz root@192.168.10.11:/tmp/
go1.25.5.linux-arm64.tar.gz                                             100%   55MB 141.7MB/s   00:00
```

```bash
# [k8s-node1] Go 설치
root@week06-week06-k8s-node1:~# rm -rf /usr/local/go
root@week06-week06-k8s-node1:~# tar -C /usr/local -xzf /tmp/go1.25.5.linux-arm64.tar.gz
root@week06-week06-k8s-node1:~# echo 'export PATH=$PATH:/usr/local/go/bin' >> /etc/profile
root@week06-week06-k8s-node1:~# source /etc/profile

root@week06-week06-k8s-node1:~# go version
go version go1.25.5 linux/arm64
```

### GOPROXY 전역 설정

```bash
root@week06-week06-k8s-node1:~# cat << 'EOF' >> /etc/profile.d/go-proxy.sh
export GOPROXY=http://192.168.10.10:3000
export GONOSUMDB=*
EOF

root@week06-week06-k8s-node1:~# source /etc/profile.d/go-proxy.sh

root@week06-week06-k8s-node1:~# go env GOPROXY
http://192.168.10.10:3000
```

| 설정 | 의미 |
|------|------|
| `GOPROXY` | Athens 프록시 주소 |
| `GONOSUMDB` | checksum database 검증 건너뛰기 |

### 캐시된 모듈 설치 테스트

Athens에 캐싱된 모듈(`github.com/gin-gonic/gin`)을 설치해 본다.

```bash
root@week06-week06-k8s-node1:~# mkdir -p /tmp/test-proxy && cd /tmp/test-proxy
root@week06-week06-k8s-node1:/tmp/test-proxy# go mod init test-proxy
go: creating new go.mod: module test-proxy

root@week06-week06-k8s-node1:/tmp/test-proxy# go get github.com/gin-gonic/gin
go: downloading github.com/gin-gonic/gin v1.11.0
go: downloading github.com/gin-contrib/sse v1.1.0
go: downloading golang.org/x/net v0.42.0
go: downloading github.com/quic-go/quic-go v0.54.0
go: downloading github.com/mattn/go-isatty v0.0.20
go: downloading github.com/go-playground/validator/v10 v10.27.0
go: downloading github.com/goccy/go-yaml v1.18.0
go: downloading github.com/pelletier/go-toml/v2 v2.2.4
go: downloading github.com/ugorji/go/codec v1.3.0
go: downloading google.golang.org/protobuf v1.36.9
go: downloading github.com/bytedance/sonic v1.14.0
go: downloading github.com/goccy/go-json v0.10.2
go: downloading github.com/json-iterator/go v1.1.12
go: downloading golang.org/x/sys v0.35.0
...
go: added github.com/gin-gonic/gin v1.11.0
go: added golang.org/x/net v0.42.0
go: added golang.org/x/text v0.27.0
go: added golang.org/x/tools v0.34.0
go: added google.golang.org/protobuf v1.36.9
```

모든 모듈이 admin의 Athens 프록시(http://192.168.10.10:3000)에서 다운로드되었다. 의존성 패키지도 함께 해결되었다.

### Troubleshooting: 캐시에 없는 모듈 설치 시 에러

Athens에 캐싱되지 않은 모듈을 설치하면 에러가 발생한다.

```bash
root@week06-week06-k8s-node1:/tmp/test-proxy# go get github.com/aws/aws-sdk-go-v2/aws
go: github.com/aws/aws-sdk-go-v2/aws: no matching versions for query "upgrade"
```

`go get`의 기본 쿼리는 `"upgrade"` (최신 버전으로 업그레이드)다. Athens가 모듈 자체를 찾을 수 없으면 빈 버전 목록을 반환하므로, Go 도구 체인은 "매칭되는 버전이 없다"고 해석한다.

Athens 로그를 확인하면:

```bash
root@admin:~# podman logs athens | grep aws
INFO[2:37PM]: incoming request	http-method=GET http-path=/github.com/aws/@v/list http-status=200 request-id=5f0b34a0-a8e9-454a-bbfb-71756f82412f
INFO[2:37PM]: Athens is in offline mode, use /list endpoint	http-method=GET http-path=/github.com/aws/@latest kind=Not Found module= operation=download.LatestHandler ...
INFO[2:37PM]: incoming request	http-method=GET http-path=/github.com/aws/@latest http-status=404 request-id=3f4a51c6-8967-41bc-940c-754bdca31045
```

Athens가 offline 모드이므로 캐시에 없는 모듈은 404를 반환한다. 이는 정상 동작이다.

## 5. 정리

이후 kubespray-offline 실습에서 다른 방식으로 Go 모듈 프록시를 구성할 예정이므로, 현재 구성을 정리한다.

### admin

```bash
# Athens 컨테이너 종료
root@admin:~# podman stop athens && podman rm athens
athens
athens
```

### k8s-node

```bash
# GOPROXY 전역 설정 삭제
root@week06-week06-k8s-node1:~# rm -f /etc/profile.d/go-proxy.sh
```

<br>

# 정리

이번 글에서는 폐쇄망 환경에서 Go 모듈을 설치할 수 있도록 사설 Go 모듈 프록시(Athens)를 구축했다.

| 순서 | 위치 | 작업 | 도구 |
|------|------|------|------|
| 1 | admin | Athens 설치 + 온라인 모드 실행 | `podman run`, `--network host` |
| 2 | admin | 필요한 Go 모듈 캐싱 | `go get github.com/gin-gonic/gin` |
| 3 | admin | offline 모드로 재시작 | `ATHENS_NETWORK_MODE=offline` |
| 4 | k8s-node | Go 설치 + GOPROXY 설정 | `/etc/profile.d/go-proxy.sh`, `GOPROXY` |

Athens의 offline 모드 덕분에, 온라인 환경에서 캐싱한 모듈을 폐쇄망에서 사용할 수 있었다.

현재까지의 폐쇄망 인프라 구성 상태:

| 구성요소 | 상태 |
|----------|------|
| Network Gateway | 완료 ([8.1.1]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-01 %})) |
| NTP Server / Client | 완료 ([8.1.2]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-02 %})) |
| DNS Server / Client | 완료 ([8.1.2]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-02 %})) |
| Local Package Repository | 완료 ([8.1.3]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-03 %})) |
| Private Container Registry | 완료 ([8.1.4]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-04 %})) |
| Private PyPI Mirror | 완료 ([8.1.5]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-05 %})) |
| Private Go Module Proxy | 완료 (본 글) |

이것으로 폐쇄망 기반 인프라의 주요 구성요소 구축이 완료되었다. 각 구성요소를 수동으로 하나씩 구축하며 원리를 익혔으므로, 이후 kubespray-offline이 이 과정을 어떻게 자동화하는지 이해하기 수월할 것이다.

<br>

# 참고 자료

- [Athens GitHub Repository](https://github.com/gomods/athens)
- [Athens Documentation](https://docs.gomods.io/)
- [Go Modules Reference](https://go.dev/ref/mod)
- [Go Module Proxy Protocol](https://go.dev/ref/mod#goproxy-protocol)
- [GOPROXY Environment Variable](https://pkg.go.dev/cmd/go#hdr-Environment_variables)

<br>
