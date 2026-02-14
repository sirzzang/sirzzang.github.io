---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 8. 오프라인 배포: The Hard Way - 3. Local Package Repository"
excerpt: "폐쇄망 환경에서 OS 패키지 설치를 위한 로컬 YUM/DNF 저장소를 구축해보자."
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
  - DNF
  - YUM
  - RPM
  - reposync
  - createrepo
  - nginx
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-6
hidden: true

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 6주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 폐쇄망 환경에서 OS 패키지 설치를 위한 **로컬 YUM/DNF 저장소**를 구축한다.

- **저장소 미러링**: admin에서 `reposync`로 BaseOS, AppStream, Extras 저장소를 로컬에 동기화
- **웹 서버 서빙**: nginx로 미러링된 패키지를 HTTP로 제공
- **클라이언트 설정**: k8s-node에서 admin을 패키지 저장소로 사용하도록 `.repo` 파일 생성
- **정리**: 이후 kubespray-offline 실습을 위해 nginx 제거

| 순서 | 위치 | 작업 | 목적 |
|------|------|------|------|
| 1 | admin | `reposync` + nginx 설정 | 패키지 저장소 구축 및 HTTP 서빙 |
| 2 | k8s-node | `.repo` 파일 생성 | admin을 패키지 저장소로 지정 |
| 3 | admin | nginx 제거 | 이후 실습을 위한 정리 |

<br>

# 로컬 패키지 저장소의 필요성

[이전 글(8.1.2)]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-02 %})에서 NTP와 DNS 서버를 구축했다. 이제 k8s-node에서 **소프트웨어 패키지를 설치**할 수 있어야 한다.

Kubernetes 클러스터를 구성하려면 containerd, kubelet 등 다양한 패키지가 필요하다. 온라인 환경에서는 Rocky Linux 공식 저장소(`dl.rockylinux.org`)에서 바로 패키지를 다운로드하면 되지만, 폐쇄망에서는 이 저장소에 접근할 수 없다.

```
[온라인]  k8s-node → dl.rockylinux.org → 패키지 다운로드
[폐쇄망]  k8s-node → admin (nginx) → 로컬에 미러링된 패키지 다운로드
```

admin에 **로컬 패키지 저장소**를 구축하여, 내부망 노드들이 패키지를 설치할 수 있도록 해야 한다. 이 구성은 결국 **외부 저장소의 패키지를 admin에 통째로 복사(미러링)**하고, **웹 서버로 서빙**하는 것이다.

<br>

# 배경지식

## RPM과 DNF

Rocky Linux(RHEL 계열)의 패키지 관리 체계는 두 계층으로 구성된다.

| 계층 | 도구 | 역할 |
|------|------|------|
| 저수준 | **RPM** (Red Hat Package Manager) | 개별 `.rpm` 패키지의 설치/제거/조회 |
| 고수준 | **DNF** (Dandified YUM) | **의존성 자동 해결**, 저장소 관리, 패키지 그룹 관리 |

RPM은 단일 패키지만 처리할 수 있어서, 패키지 A가 패키지 B에 의존하면 사용자가 직접 B를 먼저 설치해야 한다. DNF는 이 의존성을 자동으로 해결해 준다.

```
사용자: dnf install containerd
  ↓
DNF: containerd 의존성 확인
  → runc, libseccomp, ... 필요
  → 저장소에서 모든 의존 패키지 다운로드
  → 올바른 순서로 설치
```

DNF는 YUM(Yellowdog Updater Modified)의 후속 프로젝트다. Python 3 기반으로 재작성되었으며, 더 빠른 의존성 해결 알고리즘(`libsolv`)과 메타데이터 처리 성능이 개선되었다. Rocky Linux 10에서는 DNF가 기본 패키지 관리자이고, `yum` 명령어도 DNF로의 심볼릭 링크다.

| 항목 | YUM | DNF |
|------|-----|-----|
| 시기 | 2003년~ | 2015년~ (Fedora 22부터 기본) |
| 기반 | Python 2 | Python 3 |
| 의존성 해결 | 자체 구현 | libsolv (SAT solver 기반) |
| 메타데이터 처리 | Python 구현 | librepo + libcomps (C 라이브러리) |

## 패키지 저장소(Repository)의 구조

DNF가 패키지를 다운로드하려면 **저장소(Repository)**가 필요하다. 저장소는 RPM 패키지 파일과 메타데이터로 구성되며, 메타데이터가 없으면 DNF는 저장소를 인식하지 못한다.

```
/data/repos/rocky/10/baseos/
├── Packages/                          # RPM 패키지 파일들
│   ├── ModemManager-1.22.0-7.el10.aarch64.rpm
│   ├── NetworkManager-1.54.0-1.el10.aarch64.rpm
│   ├── bash-5.2.32-1.el10.aarch64.rpm
│   └── ...                            # (수천 개)
├── repodata/                          # 메타데이터
│   ├── repomd.xml                     # 마스터 인덱스
│   ├── *-primary.xml.gz               # 패키지 이름, 버전, 의존성
│   ├── *-filelists.xml.gz             # 각 패키지 포함 파일 목록
│   ├── *-other.xml.gz                 # 변경 로그 등 부가 정보
│   ├── *-comps-*.xml                  # 패키지 그룹 정보
│   └── *-updateinfo.xml.gz            # 보안 업데이트 어드바이저리
└── mirrorlist                         # 미러 서버 목록 (미러링 시 포함됨)
```

### repomd.xml: 마스터 인덱스

`repomd.xml`은 저장소의 **마스터 인덱스**다. DNF 클라이언트가 저장소에 접속하면 **가장 먼저 이 파일을 다운로드**한다. 다른 모든 메타데이터 파일의 위치와 체크섬(hash)이 이 파일에 기록되어 있어, 클라이언트는 이 정보를 기반으로 나머지 메타데이터를 순차적으로 가져온다.

DNF 클라이언트의 저장소 접근 흐름은 다음과 같다.

1. repomd.xml 다운로드: 메타데이터 파일 위치 + 체크섬 확인
2. primary.xml.gz 다운로드: 패키지 이름, 버전, 의존성 정보 확보
3. 의존성 계산: 설치에 필요한 패키지 목록 결정
4. Packages/ 에서 .rpm 파일 다운로드
5. RPM으로 설치

### 메타데이터 파일별 역할

| 메타데이터 | 역할 |
|-----------|------|
| `repomd.xml` | 마스터 인덱스. 다른 메타데이터의 위치·크기·체크섬 기록 |
| `primary.xml.gz` | 패키지 이름, 버전, 아키텍처, **의존성 정보**. DNF가 의존성을 계산할 때 핵심적으로 사용 |
| `filelists.xml.gz` | 각 패키지에 포함된 파일 경로 목록. `dnf provides /usr/bin/python3` 같은 명령에 사용 |
| `other.xml.gz` | 변경 로그(changelog) 등 부가 정보 |
| `comps-*.xml` | 패키지 그룹 정의. `dnf groupinstall "Development Tools"` 시 사용 |
| `updateinfo.xml.gz` | 보안 업데이트, 버그 수정 등의 어드바이저리 정보 |

> `repomd.xml`이 손상되거나 누락되면 DNF는 "저장소를 찾을 수 없다"는 에러를 출력한다. 저장소 미러링 시 메타데이터가 정상적으로 복사되었는지 확인하는 것이 중요하다.

## Rocky Linux 10 기본 저장소

Rocky Linux 10에는 3개의 기본 저장소가 활성화되어 있다.

| 저장소 | repo id | 용도 | 예시 패키지 |
|--------|---------|------|------------|
| **BaseOS** | `baseos` | OS 핵심 패키지. 시스템 동작에 필수적인 기반 소프트웨어 | kernel, systemd, NetworkManager, bash |
| **AppStream** | `appstream` | 애플리케이션 패키지. 개발 도구, 서버 소프트웨어, 런타임 등 | python3, gcc, nginx, nodejs, container-tools |
| **Extras** | `extras` | 추가 패키지. EPEL 릴리스, 커뮤니티 패키지 등 | epel-release, elrepo-release |

BaseOS와 AppStream의 분리는 RHEL 8부터 도입된 구조다. **BaseOS는 OS 수명주기 동안 안정적으로 유지**되는 패키지이고, **AppStream은 더 자주 업데이트**될 수 있는 애플리케이션 수준의 패키지다. 이전(RHEL 7 이하)에는 `base`와 `updates`로 나뉘어 있었다.

| 특성 | BaseOS | AppStream |
|------|--------|-----------|
| 업데이트 주기 | 보안/버그 수정 위주 | 새 버전 업스트림 가능 |
| 라이프사이클 | OS 전체 수명과 동일 | 모듈별 다를 수 있음 |
| 패키지 형태 | 전통적 RPM | RPM + **모듈(Module Stream)** |

AppStream의 모듈 스트림은 같은 패키지의 여러 버전을 병렬로 제공하는 기능이다. 예를 들어 `nodejs:18`과 `nodejs:20` 스트림이 동시에 제공되어, 사용자가 필요한 버전을 선택할 수 있다.

## 미러링 도구

### reposync

`reposync`는 **원격 저장소의 패키지를 로컬 디렉토리로 동기화(미러링)**하는 도구다. `dnf-plugins-core` 패키지에 포함되어 있다.

| 옵션 | 의미 |
|------|------|
| `--repoid` | 동기화할 저장소 ID (예: `baseos`, `appstream`) |
| `--download-metadata` | 패키지뿐 아니라 **메타데이터(`repodata/`)까지 함께 다운로드** |
| `-p` | 저장할 로컬 경로 |

`--download-metadata` 옵션이 핵심이다. 이 옵션 없이 패키지만 다운로드하면 `repodata/` 디렉토리가 생성되지 않아, DNF 클라이언트가 저장소를 인식할 수 없다.

```
reposync --download-metadata 사용 시:
  /data/repos/rocky/10/baseos/
  ├── Packages/     ← RPM 파일들
  └── repodata/     ← 메타데이터 (DNF가 인식 가능)

reposync만 사용 시 (--download-metadata 없이):
  /data/repos/rocky/10/baseos/
  └── Packages/     ← RPM 파일만 (DNF가 인식 못 함)
      → createrepo로 별도 메타데이터 생성 필요
```

### createrepo

`createrepo`는 **로컬 디렉토리의 RPM 파일들로부터 메타데이터(`repodata/`)를 생성**하는 도구다. reposync에서 `--download-metadata`를 사용하면 원본 저장소의 메타데이터를 그대로 가져오므로 별도로 createrepo를 실행할 필요가 없다. 하지만 다음과 같은 경우에는 createrepo가 필요하다.

| 상황 | createrepo 필요 여부 |
|------|---------------------|
| `reposync --download-metadata` | 불필요 (원본 메타데이터 자동 다운로드) |
| `reposync` (메타데이터 없이) | **필요** |
| 커스텀 RPM 패키지를 추가한 경우 | **필요** (메타데이터 재생성) |
| RPM 파일을 직접 모아놓은 디렉토리 | **필요** |

이 실습에서는 `--download-metadata`를 사용하므로 createrepo를 설치하되 직접 실행하지는 않는다.

## 저장소 서빙

DNF 클라이언트는 HTTP, HTTPS, FTP, file 프로토콜로 저장소에 접근할 수 있다.

| 프로토콜 | 예시 baseurl | 용도 |
|----------|-------------|------|
| `http://` | `http://192.168.10.10/rocky/10/baseos` | 네트워크를 통한 접근 (가장 일반적) |
| `https://` | `https://repo.example.com/rocky/10/baseos` | TLS 암호화 접근 |
| `ftp://` | `ftp://192.168.10.10/rocky/10/baseos` | FTP 서버 접근 (레거시) |
| `file://` | `file:///data/repos/rocky/10/baseos` | 로컬 파일시스템 직접 접근 |

<br>

폐쇄망에서 여러 노드가 접근해야 하므로, **HTTP 웹 서버(nginx)로 패키지를 서빙**하는 것이 일반적이다. 

이번 실습에서도 이 구조를 사용한다.

```
[admin]
/data/repos/rocky/10/baseos/          ← 실제 파일 위치
/data/repos/rocky/10/appstream/
/data/repos/rocky/10/extras/
         ↓  nginx (listen :80)
http://192.168.10.10/rocky/10/baseos/      ← URL로 접근 가능
http://192.168.10.10/rocky/10/appstream/
http://192.168.10.10/rocky/10/extras/

[k8s-node]
/etc/yum.repos.d/internal-rocky.repo
  baseurl=http://192.168.10.10/rocky/10/baseos
```

## 클라이언트 저장소 설정

DNF 클라이언트의 저장소 설정은 `/etc/yum.repos.d/` 디렉토리의 `.repo` 파일로 관리된다.

```ini
[internal-baseos]                              # 저장소 ID (고유 식별자)
name=Internal Rocky 10 BaseOS                  # 표시 이름
baseurl=http://192.168.10.10/rocky/10/baseos   # 저장소 URL
enabled=1                                      # 활성화 여부 (1=활성, 0=비활성)
gpgcheck=0                                     # GPG 서명 검증 비활성화 (내부 저장소)
```

| 설정 | 의미 |
|------|------|
| `baseurl` | 저장소의 기본 URL. `repodata/`가 있는 디렉토리를 가리켜야 함 |
| `enabled` | 이 저장소를 사용할지 여부 (`1`: 활성, `0`: 비활성) |
| `gpgcheck` | RPM 패키지의 GPG 서명을 검증할지 여부 |

> 프로덕션 환경에서는 `gpgcheck=1`로 설정하고 GPG 키를 등록하는 것이 보안상 바람직하다. 이 실습에서는 편의를 위해 비활성화한다.

기존 외부 저장소 설정(`.repo` 파일)을 제거하고 내부 저장소 설정만 남기면, 노드는 외부 저장소에 접근하지 않고 admin의 로컬 저장소만 사용하게 된다.

<br>

# 실습

| 순서 | 위치 | 작업 | 목적 |
|------|------|------|------|
| 1 | admin | 패키지 설치 + reposync + nginx 설정 | 로컬 저장소 구축 및 서빙 |
| 2 | k8s-node | `.repo` 파일 생성 + 동작 확인 | 내부 저장소 클라이언트 설정 |
| 3 | admin | nginx 제거 | 이후 실습을 위한 정리 |

## 1. [admin] 로컬 저장소 구축

admin에서 외부 저장소를 로컬에 미러링하고, nginx로 서빙한다.

### 필요 패키지 설치

```bash
root@admin:~# dnf install -y dnf-plugins-core createrepo nginx

# 실행 결과
...
Installed:
  createrepo_c-1.1.2-4.el10.aarch64
  nginx-2:1.26.3-1.el10.aarch64
  nginx-core-2:1.26.3-1.el10.aarch64
  ...
Complete!
```

| 패키지 | 용도 |
|--------|------|
| `dnf-plugins-core` | `reposync` 명령 제공 (이미 설치되어 있을 수 있음) |
| `createrepo` | 메타데이터 생성 도구 (커스텀 패키지 추가 시 필요) |
| `nginx` | 패키지 서빙용 웹 서버 |

### 저장소 동기화 (reposync)

현재 활성화된 저장소를 확인한 뒤, 로컬 디렉토리에 동기화한다.

```bash
# 미러 저장 디렉토리 생성
root@admin:~# mkdir -p /data/repos/rocky/10
root@admin:~# cd /data/repos/rocky/10

# 현재 활성화된 저장소 확인
root@admin:/data/repos/rocky/10# dnf repolist
repo id                                           repo name
appstream                                         Rocky Linux 10 - AppStream
baseos                                            Rocky Linux 10 - BaseOS
extras                                            Rocky Linux 10 - Extras
```

3개의 저장소를 순서대로 동기화한다. 전체 약 **12분** 소요된다.

```bash
# BaseOS 동기화 (~3분 소요)
root@admin:/data/repos/rocky/10# dnf reposync --repoid=baseos --download-metadata -p /data/repos/rocky/10
Rocky Linux 10 - BaseOS                                              9.4 MB/s |  30 MB     00:03
(1/1474): ModemManager-glib-1.22.0-7.el10.aarch64.rpm               657 kB/s | 313 kB     00:00
...
(1474/1474): zsh-5.9-15.el10.aarch64.rpm                            8.1 MB/s | 3.3 MB     00:00

root@admin:/data/repos/rocky/10# du -sh /data/repos/rocky/10/baseos/
6.2G	/data/repos/rocky/10/baseos/

# AppStream 동기화 (~9분 소요)
root@admin:/data/repos/rocky/10# dnf reposync --repoid=appstream --download-metadata -p /data/repos/rocky/10
Rocky Linux 10 - AppStream                                           8.1 MB/s |  23 MB     00:02
(1/5219): 389-ds-base-snmp-3.1.3-5.el10_1.aarch64.rpm               537 kB/s |  44 kB     00:00
...

root@admin:/data/repos/rocky/10# du -sh /data/repos/rocky/10/appstream/
14G	/data/repos/rocky/10/appstream/

# Extras 동기화 (수 초)
root@admin:/data/repos/rocky/10# dnf reposync --repoid=extras --download-metadata -p /data/repos/rocky/10
...

root@admin:/data/repos/rocky/10# du -sh /data/repos/rocky/10/extras/
66M	/data/repos/rocky/10/extras/
```

| 저장소 | 패키지 수 | 크기 | 소요 시간 |
|--------|----------|------|-----------|
| BaseOS | 1,474 | ~6.2G | ~3분 |
| AppStream | 5,219 | ~14G | ~9분 |
| Extras | 26 | ~66M | 수 초 |

> 동기화 후 전체 용량은 약 **20GB**다. admin의 디스크를 120GB로 설정한 이유 중 하나다.

메타데이터가 정상적으로 다운로드되었는지 확인한다.

```bash
root@admin:/data/repos/rocky/10# ls -l /data/repos/rocky/10/baseos/repodata/
total 30836
-rw-r--r--. 1 root root    62360 Feb  8 20:21 ...-comps-BaseOS.aarch64.xml.xz
-rw-r--r--. 1 root root 10561544 Feb  8 20:21 ...-primary.sqlite.xz
-rw-r--r--. 1 root root   343464 Feb  8 20:21 ...-other.sqlite.xz
...
-rw-r--r--. 1 root root     4449 Feb  8 20:21 repomd.xml
```

`repodata/` 디렉토리에 `repomd.xml`과 메타데이터 파일들이 있다면 정상이다. `--download-metadata` 옵션 덕분에 원본 저장소의 메타데이터가 그대로 복사되었다.

### 웹 서버 설정 (nginx)

미러링된 패키지를 HTTP로 서빙하기 위해 nginx를 설정한다.

```bash
root@admin:~# cat <<EOF > /etc/nginx/conf.d/repos.conf
server {
    listen 80;
    server_name repo-server;

    location /rocky/10/ {
        autoindex on;                 # 디렉터리 목록 표시
        autoindex_exact_size off;     # 파일 크기를 보기 좋은 단위(KB/MB/GB)로 표시
        autoindex_localtime on;       # 서버 로컬 시간으로 표시
        root /data/repos;
    }
}
EOF

root@admin:~# systemctl enable --now nginx
Created symlink '/etc/systemd/system/multi-user.target.wants/nginx.service' → '/usr/lib/systemd/system/nginx.service'.
```

nginx의 `location`과 `root` 설정이 결합되어 최종 파일 경로가 결정된다. nginx는 요청 URI의 전체 경로를 `root`에 붙여 파일을 찾는다.

```
요청: GET /rocky/10/baseos/repodata/repomd.xml
  → root(/data/repos) + URI(/rocky/10/baseos/repodata/repomd.xml)
  → /data/repos/rocky/10/baseos/repodata/repomd.xml
```

이 매핑이 맞으려면 `root`가 `/data/repos`이고, 실제 파일이 `/data/repos/rocky/10/baseos/` 아래에 있어야 한다.

| nginx 설정 | 의미 |
|-----------|------|
| `listen 80` | 80번 포트로 HTTP 요청 수신 |
| `location /rocky/10/` | URL 경로 `/rocky/10/` 이하의 요청을 처리 |
| `root /data/repos` | 파일 시스템 루트. URI와 결합하여 최종 경로 결정 |
| `autoindex on` | 디렉토리 내 파일 목록을 HTML로 표시 (패키지 목록 탐색 가능) |

서비스 상태를 확인한다.

```bash
root@admin:~# systemctl status nginx.service --no-pager
● nginx.service - The nginx HTTP and reverse proxy server
     Loaded: loaded (/usr/lib/systemd/system/nginx.service; enabled; preset: disabled)
     Active: active (running) since Sun 2026-02-08 21:17:16 KST; 5s ago
   Main PID: 8328 (nginx)
...

root@admin:~# ss -tnlp | grep nginx
LISTEN 0  511  0.0.0.0:80  0.0.0.0:*  users:(("nginx",pid=8332,fd=6),...)
```

### 접속 확인

HTTP로 저장소에 접근할 수 있는지 확인한다.

```bash
root@admin:~# curl http://192.168.10.10/rocky/10/
<html>
<head><title>Index of /rocky/10/</title></head>
<body>
<h1>Index of /rocky/10/</h1><hr><pre><a href="../">../</a>
<a href="appstream/">appstream/</a>                                         08-Feb-2026 20:41       -
<a href="baseos/">baseos/</a>                                            08-Feb-2026 20:21       -
<a href="extras/">extras/</a>                                            08-Feb-2026 21:15       -
</pre><hr></body>
</html>
```

3개의 저장소 디렉토리가 모두 표시되면 정상이다. `autoindex on` 설정으로 인해 브라우저에서 `http://192.168.10.10/rocky/10/baseos/`에 접속하면 패키지 목록을 탐색할 수도 있다.

## 2. [k8s-node] 클라이언트 설정

k8s-node에서 기존 외부 저장소 설정을 백업하고, admin의 로컬 저장소를 바라보도록 설정한다.

### k8s-node1

```bash
# 기존 repo 파일 확인
root@week06-week06-k8s-node1:~# tree /etc/yum.repos.d/
/etc/yum.repos.d/
├── rocky-addons.repo
├── rocky-devel.repo
├── rocky-extras.repo
└── rocky.repo

# 기존 repo 파일 백업
root@week06-week06-k8s-node1:~# mkdir /etc/yum.repos.d/backup
root@week06-week06-k8s-node1:~# mv /etc/yum.repos.d/*.repo /etc/yum.repos.d/backup/

# 내부 저장소 설정 파일 생성
root@week06-week06-k8s-node1:~# cat <<EOF > /etc/yum.repos.d/internal-rocky.repo
[internal-baseos]
name=Internal Rocky 10 BaseOS
baseurl=http://192.168.10.10/rocky/10/baseos
enabled=1
gpgcheck=0

[internal-appstream]
name=Internal Rocky 10 AppStream
baseurl=http://192.168.10.10/rocky/10/appstream
enabled=1
gpgcheck=0

[internal-extras]
name=Internal Rocky 10 Extras
baseurl=http://192.168.10.10/rocky/10/extras
enabled=1
gpgcheck=0
EOF
```

캐시를 초기화하고 내부 저장소가 정상적으로 인식되는지 확인한다.

```bash
# 기존 캐시 삭제
root@week06-week06-k8s-node1:~# dnf clean all
18 files removed

# 내부 저장소 목록 확인
root@week06-week06-k8s-node1:~# dnf repolist
repo id                                               repo name
internal-appstream                                    Internal Rocky 10 AppStream
internal-baseos                                       Internal Rocky 10 BaseOS
internal-extras                                       Internal Rocky 10 Extras

# 메타데이터 캐시 생성
root@week06-week06-k8s-node1:~# dnf makecache
Internal Rocky 10 BaseOS                                             242 kB/s | 4.3 kB     00:00
Internal Rocky 10 AppStream                                          420 kB/s | 4.3 kB     00:00
Internal Rocky 10 Extras                                              78 kB/s | 6.2 kB     00:00
Metadata cache created.
```

기존 외부 저장소 대신 `internal-*` 저장소 3개만 표시되면 정상이다. 패키지 설치가 정상 동작하는지 확인한다.

```bash
# 패키지 설치 테스트
root@week06-week06-k8s-node1:~# dnf install -y nfs-utils

# 실행 결과
...
Upgrading:
 libnfsidmap               aarch64               1:2.8.3-0.el10                  internal-baseos                61 k
 nfs-utils                 aarch64               1:2.8.3-0.el10                  internal-baseos               476 k
...
Complete!

# 패키지가 내부 저장소에서 설치되었는지 확인
root@week06-week06-k8s-node1:~# dnf info nfs-utils | grep -i repo
Repository   : @System
From repo    : internal-baseos
```

`From repo : internal-baseos`로 표시되어, admin의 로컬 저장소에서 패키지가 설치된 것을 확인할 수 있다.

## 3. [admin] 정리

이후 kubespray-offline 실습에서 다른 방식으로 패키지 저장소를 구성할 예정이므로, nginx를 제거한다.

```bash
root@admin:~# systemctl disable --now nginx && dnf remove -y nginx

# 실행 결과
Removed '/etc/systemd/system/multi-user.target.wants/nginx.service'.
...
Removed:
  nginx-2:1.26.3-1.el10.aarch64          nginx-core-2:1.26.3-1.el10.aarch64
  nginx-filesystem-2:1.26.3-1.el10.noarch  rocky-logos-httpd-100.4-7.el10.noarch
Complete!
```

nginx를 제거한 뒤의 상태를 정리하면:

| 구성 요소 | 위치 | 삭제 후 상태 |
|-----------|------|-------------|
| `.repo` 파일 (`internal-rocky.repo`) | k8s-node | 그대로 존재 |
| nginx (웹 서버) | admin | 삭제됨 |
| 미러링된 패키지 (`/data/repos/rocky/10/`) | admin | 그대로 존재 |

`.repo` 파일은 k8s-node에 있는 **클라이언트 설정**이고, nginx는 admin에 있는 **서버**다. 서로 독립적이므로 admin에서 nginx를 삭제해도 node의 설정 파일이 지워지지는 않는다. 다만 웹 서버가 없으므로 `dnf install` 시 패키지 다운로드는 실패하게 된다.

> 미러링된 패키지 파일은 admin에 남아 있으므로, 나중에 nginx를 다시 올리면 node 쪽 설정 수정 없이 바로 동작한다.

<br>

# 정리

이번 글에서는 폐쇄망 환경에서 OS 패키지를 설치할 수 있도록 로컬 YUM/DNF 저장소를 구축했다.

| 순서 | 위치 | 작업 | 도구 |
|------|------|------|------|
| 1 | admin | 외부 저장소를 로컬에 미러링 | `reposync --download-metadata` |
| 2 | admin | 미러링된 패키지를 HTTP로 서빙 | nginx |
| 3 | k8s-node | admin을 패키지 저장소로 설정 | `/etc/yum.repos.d/internal-rocky.repo` |

현재까지의 폐쇄망 인프라 구성 상태:

| 구성요소 | 상태 |
|----------|------|
| Network Gateway | 완료 ([8.1.1]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-01 %})) |
| NTP Server / Client | 완료 ([8.1.2]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-02 %})) |
| DNS Server / Client | 완료 ([8.1.2]({% post_url 2026-02-09-Kubernetes-Kubespray-08-01-02 %})) |
| Local Package Repository | 완료 (본 글) |
| Private Container Registry | 미구성 |

<br>

# 참고 자료

- [Red Hat - Creating a local repository](https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/9/html/managing_software_with_the_dnf_tool/assembly_creating-a-local-repository_managing-software-with-the-dnf-tool)
- [DNF Documentation](https://dnf.readthedocs.io/)
- [Rocky Linux Repository Information](https://wiki.rockylinux.org/rocky/repo/)

<br>
