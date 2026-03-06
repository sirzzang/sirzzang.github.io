---
title:  "[Docker] 호스트-컨테이너 타임존 런타임 동기화 문제"
excerpt: "bind mount한 파일이 호스트에서 바뀌었는데 컨테이너에서는 바뀌지 않는 이유에 대해 알아보자."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Docker
  - Container
  - bind mount
  - inode
  - Timezone
  - inotify
  - systemd
---

<br>

Kubernetes ConfigMap 동작 원리를 공부하다가, 2년 전 겪었던 문제가 불현듯 떠올랐다. 호스트에서 타임존을 바꿨는데 Docker 컨테이너에 반영이 안 되던 문제. 당시에는 팀장님의 도움을 받아 원리를 대강의 수준에서만 이해했는데, 지금 돌아보니 **inode와 bind mount**라는 하나의 원리로 깔끔하게 설명된다. 그리고 놀랍게도, 이 원리는 Kubernetes ConfigMap의 subPath가 업데이트되지 않는 문제와 정확히 같은 뿌리를 공유한다.

이 글에서는 Docker 컨테이너 타임존 런타임 동기화 문제를 다루고, [다른 글]({% post_url 2026-03-07-Kubernetes-ConfigMap-Inode %})에서 Kubernetes ConfigMap과의 접점을 이야기한다.

> 이전에 [Ansible을 활용한 시스템 설정 관리]({% post_url 2026-01-12-Kubernetes-Ansible-15 %}#과거-프로젝트-회고)에서 잠깐 언급했던, 시스템 설정 관리 기능 개발 중 겪은 문제다.

<br>

# TL;DR

- **문제**: 호스트 타임존 변경이 컨테이너에 실시간 반영되지 않는다.
- **원인**: bind mount는 mount 시점의 **inode**를 참조한다. `/etc/localtime`은 심볼릭 링크 대상이 바뀌어도 mount 시점에 resolve한 원래 파일의 inode를 계속 바라보고, `/etc/timezone`은 삭제-재생성 시 새 inode가 배정되어 mount가 끊긴다.
- **해결**: inotify로 호스트 타임존 변경 감지 → 별도 디렉토리에 파일 복사 → 해당 **디렉토리**를 컨테이너에 마운트

<br>

# 배경지식

## inode

inode는 파일의 메타데이터(크기, 권한, 소유자, 데이터 블록 위치 등)를 담는 자료구조다. 각 inode는 파일시스템 내에서 고유한 정수 번호(**inode 번호**)를 가지며, 이 번호가 파일의 실제 식별자다.

> 참고: inode와 파일의 관계
>
> inode는 메타데이터와 데이터 블록 위치를 담는 구조체이고, 실제 파일 내용(데이터)은 별도의 데이터 블록에 저장된다. 엄밀히 말하면 "파일 = inode"는 아니지만, 파일시스템이 파일을 식별하는 기준은 이름이 아니라 inode 번호다. **파일의 정체성(identity) = inode**이고, 파일 이름은 그 정체성을 가리키는 포인터라고 보면 된다.

파일 이름은 inode에 저장되지 않는다. 파일 이름과 inode 번호의 연결은 dentry(directory entry)가 담당한다. dentry는 "이 이름은 이 inode를 가리킨다"는 매핑으로, 경로 탐색 시 커널이 이름을 inode 번호로 변환하는 데 쓰인다.

```
파일 이름 "timezone"  ──→  dentry  ──→  inode #12345
                                          ├── 크기: 11 bytes
                                          ├── 권한: 0644
                                          └── 데이터 블록: [8000]
```

같은 이름의 파일이라도, 삭제 후 새로 생성하면 **다른 inode**가 배정된다. 이름은 같지만, 파일시스템 관점에서는 전혀 다른 파일이다.

```bash
stat /etc/timezone
# Inode: 12345  ← 현재 inode 번호

# 파일 삭제 후 같은 이름으로 재생성
rm /etc/timezone
echo "America/New_York" > /etc/timezone

stat /etc/timezone
# Inode: 67890  ← 다른 inode 번호
```

<br>

## 하드 링크와 심볼릭 링크

inode 번호가 파일의 정체성이라는 점을 바탕으로, 링크의 두 가지 종류를 구분할 수 있다.

> 이 문제 해결을 위해서는 심볼릭 링크가 중요하나, 비교를 위해 하드 링크에 대해서도 알아 본다.

### 하드 링크

하드 링크는 **같은 inode를 가리키는 또 다른 이름**이다. 이름이 다르더라도 같은 inode를 직접 가리키므로, 파일시스템 관점에서는 같은 파일이다.

```bash
echo "hello" > a.txt    # a.txt → inode #100
ln a.txt b.txt           # b.txt → inode #100 (같은 inode)

ls -i a.txt b.txt
# 100 a.txt
# 100 b.txt              ← 같은 inode 번호 → 같은 파일
```

`a.txt`를 삭제해도 inode `#100`을 가리키는 링크가 `b.txt`에 남아있으므로 데이터는 사라지지 않는다.

### 심볼릭 링크(소프트 링크)

심볼릭 링크는 자기 자신만의 별도 inode를 가지는 독립적인 파일이다. 이 파일의 내용은 **대상 파일의 경로 문자열**이다. 접근 시 커널이 그 경로를 다시 resolve해서 대상 파일의 inode를 찾아간다.

```bash
ln -s a.txt c.txt        # c.txt → 자체 inode #200, 내용: "a.txt"라는 경로 문자열
```

### 정리

두 링크의 동작 원리 차이는 아래 도식에서 나타난 것과 같다.

```
하드 링크:
a.txt  ──→  inode #100  (직접 가리킴)
b.txt  ──→  inode #100  (직접 가리킴)

심볼릭 링크:
a.txt  ──→  inode #100
c.txt  ──→  inode #200  (내용: "a.txt"라는 문자열)
             접근 시 → "a.txt" 경로를 다시 resolve → inode #100
```

- **하드 링크**: inode를 직접 가리킨다. 하드 링크 사이에 원본/사본 구분은 없고, 모두 같은 inode에 대한 동등한 이름이다. 하나를 삭제해도 같은 inode를 가리키는 다른 이름이 남아있으면 데이터는 유지된다(inode의 link count가 0이 되어야 데이터가 해제된다).
- **심볼릭 링크**: 경로 문자열을 저장한다. 대상 파일이 삭제되면 가리킬 곳이 사라져 깨진 링크(dangling link)가 된다. 심볼릭 링크의 대상을 바꾸면, 같은 이름이지만 다른 inode를 가리키게 된다.

<br>

## Linux의 타임존

Linux 시스템의 타임존은 두 파일에 의해 관리된다.

### /etc/localtime

실제 시간 변환 데이터를 담고 있는 바이너리 파일(`zoneinfo`)에 대한 **심볼릭 링크**다. glibc 등 시스템 라이브러리가 시간을 계산할 때 이 파일을 직접 읽는다.

```bash
ls -l /etc/localtime
# lrwxrwxrwx 1 root root 33 ... /etc/localtime -> /usr/share/zoneinfo/Asia/Seoul
```

타임존을 변경하면 이 심볼릭 링크의 대상이 바뀐다. 기존 링크를 삭제하고 새 대상을 가리키는 링크를 생성하는 것이다. 위의 심볼릭 링크 설명을 떠올리면, 같은 `/etc/localtime`이라는 이름이지만 가리키는 inode가 달라진다는 뜻이다.

### /etc/timezone

현재 타임존 이름을 문자열로 저장하는 일반 텍스트 파일이다. 스케줄러, 로깅 등에서 타임존 이름이 필요할 때 참조한다.

```bash
cat /etc/timezone
# Asia/Seoul
```

타임존을 변경하면 이 파일은 삭제 후 새 내용으로 재생성된다. 위의 inode 설명에 빗대어 보면, 같은 `/etc/timezone`이라는 이름이지만 새 inode가 배정된다는 뜻이다.

### 두 파일의 역할

두 파일 모두 필요하다. `/etc/localtime`만 있으면 시간 계산은 맞지만 타임존 **이름**을 알 수 없고, `/etc/timezone`만 있으면 이름은 알지만 실제 시간 변환이 안 맞을 수 있다.

타임존을 변경할 때는 `timedatectl` 등의 도구를 사용한다. `timedatectl`은 내부적으로 두 파일 모두 임시 파일을 만든 뒤 `rename()`으로 기존 파일을 원자적으로 교체한다(atomic swap). 이 방식 덕분에 교체 도중 크래시가 나도 파일이 반쯤 쓰여진 상태가 되지 않지만, 결과적으로 두 파일 모두 새 inode가 배정된다.

<br>

## bind mount

bind mount(참고: [컨테이너 파일 시스템-bind mount]({% post_url 2026-03-01-CS-Container-Filesystem %}#bind-mount))는 기존 디렉토리나 파일을 다른 경로에서도 접근할 수 있게 해 주는 메커니즘이다. 핵심은 bind mount가 mount 시점에 원본의 **inode를 참조**한다는 것이다. bind mount는 파일 단위로도, 디렉토리 단위로도 할 수 있는데, 어떤 단위로 하느냐에 따라 이후 변경 사항이 반영되는 방식이 달라진다.

### 파일 bind mount

```bash
mount --bind /src/file.txt /dst/file.txt
```

이 시점에 `/src/file.txt`의 inode가 `#12345`라면, `/dst/file.txt`도 inode `#12345`를 바라본다.

```
[mount 시점]
/src/file.txt  →  inode #12345  ←  /dst/file.txt (bind mount)
```

이 구조에서 원본 파일의 **내용만** 바뀌면(in-place write, 같은 inode에 데이터 변경) bind mount 측에서도 변경을 볼 수 있다. 그러나 원본 파일이 **삭제-재생성**되면 새 inode(`#67890`)가 배정되고, bind mount는 여전히 옛 inode(`#12345`)를 바라보므로 변경을 감지하지 못한다.

```
[삭제-재생성 후]
/src/file.txt  →  inode #67890      (새 파일)
                  inode #12345  ←  /dst/file.txt (여전히 옛 inode)
```

> 참고: 원본이 삭제되어도 bind mount 측에서 에러가 나는 것은 아니다. bind mount가 inode에 대한 참조를 잡고 있으면 커널은 해당 inode를 해제하지 않는다(열린 file descriptor가 있으면 `rm` 후에도 파일을 읽을 수 있는 것과 같은 원리다). bind mount 측에서는 **삭제 전의 옛 데이터를 정상적으로 읽을 수 있다.** 깨진 게 아니라 낡은 것이다.

### 디렉토리 bind mount

위 예시는 **파일** 하나를 bind mount한 경우다. **디렉토리**를 bind mount하면 동작이 달라진다.

디렉토리를 bind mount하면 **디렉토리의 inode**를 참조한다. 
```
[디렉토리 bind mount — mount 시점]
/src/dir/ (inode #500)  ←  /dst/dir/ (bind mount)
    └── file.txt (inode #600)
```

디렉토리 안의 개별 파일이 삭제-재생성되어도 디렉토리 자체의 inode는 변하지 않는다. bind mount 측에서 디렉토리 안의 파일에 접근하면, 그 시점에 디렉토리 내용을 다시 탐색하므로 항상 최신 파일을 볼 수 있다.
```
[디렉토리 안의 파일이 삭제-재생성된 후]
/src/dir/ (inode #500)  ←  /dst/dir/ (bind mount, 유지됨)
    └── file.txt (inode #700)  ← 새 파일이지만, 디렉토리를 통해 접근 가능
```

### 정리

정리하면 파일 수준과 디렉토리 수준에서 bind mount의 동작은 아래와 같이 달라진다.

- **파일 bind mount**: 파일의 inode를 직접 잡는다. 파일이 교체되면 끊긴다.
- **디렉토리 bind mount**: 디렉토리의 inode를 잡는다. 안의 파일이 교체되어도 디렉토리 inode는 유지되므로 최신 파일을 볼 수 있다.

<br>

## Docker의 bind mount

Docker에서 `-v` 옵션으로 호스트 파일을 컨테이너에 마운트하면, 내부적으로 위에서 설명한 Linux bind mount가 실행된다.

```bash
docker run -v /host/config.txt:/app/config.txt my-service
```

이 명령을 실행하면 Docker(정확히는 컨테이너 런타임)가 컨테이너 시작 과정에서 다음과 같은 bind mount를 수행한다.

```bash
# 호스트의 /host/config.txt를 컨테이너의 /app/config.txt에 bind mount
mount --bind /host/config.txt /app/config.txt
```

이 시점에 호스트의 `/host/config.txt`가 가리키는 inode(`#12345`)가 컨테이너 내부의 `/app/config.txt`에 연결된다. 즉, 컨테이너 시작 시점에 호스트 파일의 inode를 참조하는 것이다. 이후 컨테이너 안에서 `/app/config.txt`를 읽으면, 커널이 이 inode를 통해 데이터를 가져온다.

이후 호스트에서 일어나는 일에 따라 컨테이너에서 보이는 결과가 달라진다.

- **호스트에서 파일 내용을 in-place로 수정**: 같은 inode의 데이터가 바뀐 것이므로, 컨테이너에서 `/app/config.txt`를 읽으면 바뀐 내용이 보인다.
- **호스트에서 파일을 삭제-재생성**: 새 파일은 새 inode(`#67890`)를 받는다. 호스트의 `/host/config.txt`라는 **이름**은 이제 새 inode를 가리키지만, 컨테이너의 bind mount는 컨테이너 시작 시점에 잡은 옛 inode(`#12345`)에 연결되어 있다. 컨테이너에서 `/app/config.txt`를 읽으면 삭제 전의 옛 데이터가 나온다.

컨테이너 입장에서는 호스트 파일이 "바뀌었다"는 사실 자체를 알 수 없다. 자신이 연결된 inode가 여전히 존재하고, 그 inode의 데이터를 충실히 읽고 있을 뿐이다.

이 원리를 알고 있으면, 아래에서 다룰 문제가 **왜** 발생하는지 자명해진다.

<br>

# 문제

## 상황

Docker 컨테이너로 실행되는 서비스가 있었다. 이 서비스는 시스템 전반을 관리하는 역할이었고, 그 중 하나가 타임존이었다. 사용자가 시스템의 타임존을 조회하면 이 서비스가 응답했고, 변경 요청이 들어오면 Ansible을 통해 호스트에서 `timedatectl set-timezone`을 실행해 타임존을 바꿨다.


> 참고: 왜 `timedatectl`을 사용했는가?
>
> "심볼릭 링크를 직접 변경하고(`ln -sf`) `/etc/timezone` 파일 내용을 수정하면(`echo`) 되지 않느냐"는 의문이 들 수 있다. 수동 조작으로도 타임존 자체는 바뀌지만, `timedatectl`은 systemd의 표준 타임존 관리 도구로서 두 파일을 원자적으로 교체하고, systemd 내부 상태까지 함께 갱신한다. 수동 조작은 systemd의 관리 체계를 우회하므로 시스템 도구와의 상태 불일치가 발생할 수 있다.

서비스가 타임존을 읽는 방식은 단순했다. 컨테이너 시작 시 호스트의 `/etc/localtime`과 `/etc/timezone`을 bind mount해서, 컨테이너 안에서 그 파일을 읽었다.

```bash
docker run \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  my-service
```

요구사항은 **런타임에** 호스트의 타임존이 변경되면, 컨테이너 재시작 없이 해당 서비스에도 실시간으로 반영되어야 한다는 것이었다.

<br>

## 현상

**호스트에서 타임존을 변경해도 컨테이너에 반영되지 않았다**. 사용자가 타임존 변경 요청이 호스트 단에서 처리되었고, 실제로 호스트의 타임존은 변경되었는데, 이후 컨테이너 서비스에 타임존을 조회하면 기존 타임존이 응답으로 돌아오는 상황이었다.

Docker 컨테이너 관련 Timezone 문제를 검색하면, "컨테이너에 `/etc/localtime`과 `/etc/timezone`을 마운트하면 된다"는 글이 많다. 하지만 이건 **컨테이너 최초 실행 시**에만 해당하는 이야기다. 런타임에 호스트 타임존이 바뀌는 경우는 다른 차원의 문제다.

<br>

## 원인

배경지식 섹션에서 다룬 inode와 bind mount의 동작 원리를 적용하면, 반영이 안 되는 이유가 두 가지 경로로 설명된다.

다시 한 번, Timezone을 바꿀 때 일어나는 일에 대해 기억해 둘 필요가 있다.
- `/etc/localtime`: 심볼릭 링크 대상 변경
- `/etc/timezone`: 파일 삭제 후 재생성

### `/etc/localtime` — 심볼릭 링크 대상 변경

`/etc/localtime`은 심볼릭 링크다. 컨테이너에 이 파일을 bind mount하면, 앞서 설명한 "mount 시점의 inode를 참조한다"는 원리가 그대로 적용된다. 다만 심볼릭 링크이므로, Docker는 링크 자체가 아니라 심볼릭 링크를 resolve한 **최종 대상 파일의 inode**를 잡는다.

```
[mount 시점: Asia/Seoul]
/etc/localtime → /usr/share/zoneinfo/Asia/Seoul (inode #100)
컨테이너 내부 /etc/localtime → inode #100
```

호스트에서 심볼릭 링크의 대상을 바꿔도, 컨테이너는 mount 시점에 resolve된 원래 파일(inode `#100`)을 계속 바라본다.

```
[호스트에서 타임존 변경: America/New_York]
/etc/localtime → /usr/share/zoneinfo/America/New_York (inode #200)
컨테이너 내부 /etc/localtime → inode #100 (여전히 Seoul)
```

결과적으로, 컨테이너 시작 시점에 마운트된 `/etc/localtime` 파일을 계속 바라보는 것이다.

### `/etc/timezone` — 파일 삭제 후 재생성

`/etc/timezone`은 일반 텍스트 파일이다. 심볼릭 링크가 아니므로, bind mount 시 이 파일의 inode를 직접 잡는다.

```
[mount 시점]
/etc/timezone (inode #300, 내용: "Asia/Seoul")
컨테이너 내부 /etc/timezone → inode #300
```

타임존 변경 시 이 파일은 삭제 후 새 내용으로 재생성된다. 배경지식에서 다뤘듯, 같은 이름이라도 삭제-재생성하면 새 inode가 배정된다. 호스트의 `/etc/timezone`이라는 이름은 이제 새 inode(`#400`)를 가리키지만, 컨테이너의 bind mount는 mount 시점에 잡은 옛 inode(`#300`)에 연결되어 있다.

```
[호스트에서 타임존 변경]
/etc/timezone 삭제 (이름과 inode #300 사이의 연결(dentry)이 끊김)
/etc/timezone 재생성 (inode #400, 내용: "America/New_York")
컨테이너 내부 /etc/timezone → inode #300 (호스트에서 이름은 사라졌지만, bind mount 참조로 여전히 유효)
```

호스트에서 `/etc/timezone`이라는 이름과 inode `#300` 사이의 연결(dentry)은 끊겼지만, 컨테이너의 bind mount가 inode `#300`에 대한 참조를 유지하고 있으므로 inode 자체는 해제되지 않는다. 컨테이너는 여전히 옛 inode의 데이터("Asia/Seoul")를 읽을 수 있지만, 새로 생성된 파일(inode `#400`)의 내용("America/New_York")은 볼 수 없다.

<br>

# 시도한 대안들

## 심볼릭 링크 대상 파일 직접 마운트

심볼릭 링크를 거치지 않고, 실제 zoneinfo 파일을 직접 마운트하면 어떨까?

```bash
docker run -v /usr/share/zoneinfo/Asia/Seoul:/etc/localtime:ro ...
```

타임존이 바뀌면 마운트 대상 자체가 달라져야 하므로(Seoul 파일이 아니라 New_York 파일) 런타임 변경에 대응할 수 없다. 근본적으로 동일한 문제다.

## 환경변수 `TZ`

```bash
docker run -e TZ=Asia/Seoul ...
```

컨테이너 환경변수는 시작 시 고정된다. 런타임에 호스트 타임존이 바뀌는 것을 감지해서 환경변수를 갱신해 줘야 하는데, 그것 자체가 원래 문제와 크게 다르지 않다.

## 컨테이너 재시작

가장 단순한 방법은 호스트 타임존 변경 시 컨테이너를 재시작하는 것이다.

```bash
docker restart <container_id>
```

재시작하면 bind mount가 새로 맺어지므로 최신 inode를 잡는다. 하지만 타임존 변경할 때마다 서비스를 재시작하는 것은 불필요한 다운타임을 유발한다. 또한 대상 컨테이너의 ID를 지속적으로 추적해야 하는 운영 부담도 있다.

<br>

# 해결

## 아이디어

시도한 대안들이 모두 실패한 이유를 정리하면, 결국 **파일 수준 bind mount는 inode가 바뀌면 끊긴다**는 한 문장으로 귀결된다. 그렇다면 해결 방향은 명확하다.

1. 호스트의 타임존 변화를 **감지**한다
2. 감지한 변화를 컨테이너가 마운트할 수 있는 **별도 위치에 반영**한다
3. 컨테이너는 **그 위치에서** 타임존 정보를 가져간다

여기서 핵심은 2번과 3번의 구현 방식이다. 별도 위치에 타임존 정보를 복사해 두고 그것을 컨테이너에 마운트한다면, 마운트 방식을 어떻게 해야 할까?

<br>

## 구현 방향: 파일 마운트 vs. 디렉토리 마운트

### 파일을 마운트하고 내용만 바꾸면 안 되는가?

별도 위치에 파일을 하나 만들어 두고, 그 파일을 컨테이너에 bind mount한 뒤, 타임존 변경 시 파일 내용만 in-place로 덮어쓰면(같은 inode 유지) 동작할 수 있다. 배경지식에서 다뤘듯, 같은 inode에 대한 in-place write는 bind mount 측에서도 보이기 때문이다.

그러나 `/etc/localtime`은 바이너리 파일(zoneinfo)이다. 타임존마다 파일 크기와 내용이 완전히 다르기 때문에, 기존 파일에 내용만 덮어쓰는 것은 현실적으로 까다롭다.

> 참고: `cp -f`의 동작
>
> `cp -f`는 대상 파일이 이미 존재하고 쓰기 가능한 경우, 파일을 열어 내용을 잘라내고(truncate) 새 내용을 쓴다(in-place write). 이 경우 inode가 유지되므로, 이론적으로는 파일 수준 bind mount에서도 변경이 반영될 수 있다. 그러나 대상 파일이 쓰기 불가능한 경우에는 기존 파일을 삭제(`unlink`)하고 새로 생성하므로 inode가 바뀐다. 즉, `cp -f`의 동작은 대상 파일의 권한에 따라 달라지며, inode 유지 여부가 보장되지 않는다.

이처럼 파일 수준 bind mount + in-place write 방식은 `cp` 구현의 세부 동작에 의존하게 되므로 견고한 설계가 아니다. 반면, 아래에서 설명할 디렉토리 수준 bind mount는 이러한 세부사항과 무관하게 동작한다.

### 디렉토리를 마운트한다

**디렉토리를 bind mount**하면 이 문제를 우회할 수 있다.

- 디렉토리를 bind mount하면 **디렉토리의 inode**를 참조한다
- 디렉토리 안의 개별 파일이 삭제-재생성되어도, 디렉토리 자체의 inode는 변하지 않는다
- 컨테이너가 디렉토리 안의 파일에 접근하면, 그 시점에 디렉토리 내용을 탐색하므로 항상 **최신 파일**을 볼 수 있다

```
[디렉토리 bind mount]
/host/tz-dir/ (inode #500)  ←  컨테이너 마운트
    ├── localtime (inode #600)
    └── timezone  (inode #700)

[파일 복사로 갱신 후]
/host/tz-dir/ (inode #500)  ←  컨테이너 마운트 (유지됨)
    ├── localtime (inode #800)  ← 새 파일이지만, 디렉토리를 통해 접근 가능
    └── timezone  (inode #900)  ← 새 파일이지만, 디렉토리를 통해 접근 가능
```

mount 단위를 파일에서 디렉토리로 올리면, 안의 파일을 `cp -f`로 자유롭게 교체해도 컨테이너에서 최신 파일을 볼 수 있다.

<br>

## 구현

### 1단계: inotify 기반 타임존 변경 감시 스크립트

호스트의 `/etc/` 디렉토리에서 `localtime`, `timezone` 파일의 변경을 감시하고, 변경 시 별도 디렉토리에 복사하는 스크립트를 작성한다.

```bash
#!/bin/bash

WATCH_DIR="/etc/"
SYNC_DIR="/opt/tz-sync/timezone"

mkdir -p "$SYNC_DIR"

# 최초 실행 시 현재 타임존 파일 복사
if [ -z "$(ls -A "$SYNC_DIR")" ]; then
    echo "Directory '$SYNC_DIR' is empty. Copying initial timezone files"
    cp -f "$(readlink -f /etc/localtime)" "$SYNC_DIR/localtime"
    cp -f "/etc/timezone" "$SYNC_DIR/timezone"
fi

echo "Current Timezone: $(cat "$SYNC_DIR/timezone")"

# inotifywait로 /etc/ 감시 — moved_to 이벤트 포착
inotifywait -P -m "$WATCH_DIR" -e moved_to |
    while read path action file; do
        if [[ "$file" == "timezone" || "$file" == "localtime" ]]; then
            echo "$(date +"%Y-%m-%d %H:%M:%S") [$action]: ${WATCH_DIR}${file}"
            TARGET_FILE=$(readlink -f "${WATCH_DIR}/${file}")
            cp -f "$TARGET_FILE" "$SYNC_DIR/$file"
        fi
    done
```

동작 흐름은 다음과 같다:

1. 별도 디렉토리(`/opt/tz-sync/timezone/`)가 비어있으면 현재 타임존 파일을 초기 복사
2. `inotifywait`로 `/etc/` 디렉토리를 상시 감시
3. `moved_to` 이벤트 발생 시(타임존 관련 파일 교체) `readlink -f`로 실제 파일을 resolve
4. resolve한 파일을 별도 디렉토리에 `cp -f`로 복사

2에서 **`-P`(`--no-dereference`) 플래그**를 사용했다. 이 옵션은 심볼릭 링크를 따라가지 않고 링크 자체의 변경을 감시하도록 한다. 내부적으로 inotify watch에 `IN_DONT_FOLLOW` 플래그를 설정하여 동작한다([inotifywait(1) 매뉴얼](https://man7.org/linux/man-pages/man1/inotifywait.1.html) 참고). `/etc/localtime`이 심볼릭 링크이므로, 링크 대상 파일의 변경이 아니라 링크 자체의 교체(즉, `rename()`에 의한 `moved_to`)를 감지하기 위해 이 플래그를 사용한다.

3에서 `moved_to` 이벤트를 감시하는 이유는 `timedatectl`의 동작과도 연결된다. 배경지식에서 설명했듯이, `timedatectl`은 임시 파일을 만든 뒤 `rename()`으로 기존 파일을 원자적으로 교체한다. `rename()`은 디렉토리 입장에서 "파일이 이동해 들어온" 것이므로, inotify에서는 `moved_to` 이벤트가 발생한다. 파일 내용을 직접 수정하는 `modify`나 삭제 후 생성하는 `create`와는 다른 이벤트이기 때문에, `moved_to`를 감시해야 `timedatectl`의 변경을 정확히 포착할 수 있다.

 
> 참고: 파일 변경 방법에 따른 inotify 이벤트
>
> | 변경 방법 | 예시 | inotify 이벤트 |
> |---|---|---|
> | 파일 내용 직접 수정 | `echo "..." > file` | `modify` |
> | 파일 삭제 후 재생성 | `rm file && touch file` | `delete`, `create` |
> | `rename()`으로 교체 | `timedatectl`, `mv tmp file` | `moved_from`, `moved_to` |
>
> `timedatectl`은 `rename()`을 사용하므로, `moved_to`를 감시하지 않으면 타임존 변경을 놓치게 된다. 반대로, 이 스크립트는 `timedatectl`을 통한 변경을 전제하므로, 수동으로 파일을 직접 수정하거나(`echo`) 심볼릭 링크를 교체하면(`ln -sf`) 감지하지 못한다.

> 참고: 이 atomic swap 패턴(임시 파일 생성 → `rename()`으로 교체)은 `timedatectl`만의 방식이 아니다. Kubernetes에서 kubelet이 ConfigMap을 업데이트할 때도 새 디렉토리를 만든 뒤 `..data` 심볼릭 링크를 `rename()`으로 교체하는 동일한 패턴을 사용한다. 이에 대해서는 [다음 글]({% post_url 2026-03-07-Kubernetes-ConfigMap-Inode %})에서 자세히 다룬다.


### 2단계: systemd 서비스로 등록

이 스크립트를 systemd 서비스로 등록하여 호스트 부팅 시 자동으로 시작되도록 한다.

```ini
[Unit]
Description=Timezone sync watcher for Docker containers
After=network.target

[Service]
Type=simple
ExecStart=/opt/tz-sync/watch-timezone.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

> 참고: 위 unit 파일은 일반적인 형태로 작성한 예시다. 실제 환경에서는 프로젝트 구조에 맞게 경로나 옵션을 조정했다.

```bash
sudo systemctl enable tz-sync-watcher
sudo systemctl start tz-sync-watcher
```

### 3단계: 컨테이너에 디렉토리 마운트

개별 파일이 아니라, 별도 디렉토리를 통째로 마운트한다.

```bash
docker run \
  -v /opt/tz-sync/timezone:/mnt/timezone:ro \
  my-service
```

### 4단계: 컨테이너 내부 심볼릭 링크 재설정

3단계까지 하면 컨테이너 안에 `/mnt/timezone/` 디렉토리가 마운트되어 있지만, 컨테이너의 `/etc/localtime`이 이 파일을 바라보고 있지는 않다. 컨테이너 서비스 시작 시 기존 `/etc/localtime`을 제거하고, 마운트된 디렉토리 안의 파일로 심볼릭 링크를 재설정해야 한다.

실제로는 서비스 코드(Go)에서 컨테이너가 시작될 때마다 항상 실행되도록 처리했다. 컨테이너가 재시작되면 내부 파일시스템이 초기화되므로, 매 시작 시 심볼릭 링크를 재설정해야 한다. 결국 하는 일은 다음과 같다.

```bash
rm -f /etc/localtime
ln -sf /mnt/timezone/localtime /etc/localtime
```

<br>

## 결과 확인

호스트에서 타임존을 `Asia/Seoul`에서 `America/New_York`으로 변경하고, 각 단계별로 확인했다.

### 변경 전 — 호스트 및 동기화 디렉토리 상태

```bash
# 호스트 타임존 확인
timedatectl | grep "Time zone"
#        Time zone: Asia/Seoul (KST, +0900)

# 동기화 디렉토리 확인
ls -la /opt/tz-sync/timezone/
# localtime  timezone

cat /opt/tz-sync/timezone/timezone
# Asia/Seoul
```

### 호스트에서 타임존 변경

```bash
sudo timedatectl set-timezone America/New_York
```

### 변경 후 — 동기화 디렉토리 갱신 확인

```bash
# 동기화 디렉토리 확인
cat /opt/tz-sync/timezone/timezone
# America/New_York
```

### 변경 후 — 컨테이너 내부 반영 확인

```bash
docker exec my-service date
# ... EDT (America/New_York 반영 확인)

docker exec my-service cat /etc/timezone
# America/New_York
```

컨테이너를 재시작하지 않았음에도, 호스트의 타임존 변경이 컨테이너에 실시간으로 반영되었다.

<br>

# 정리

| 시도 | 방식 | 결과 | 실패 이유 |
|---|---|---|---|
| `/etc/localtime` bind mount | 파일 수준 bind mount | 실패 | symlink resolve 후 inode 고정 |
| zoneinfo 파일 직접 mount | 파일 수준 bind mount | 실패 | 타임존 변경 시 다른 파일을 가리켜야 함 |
| `TZ` 환경변수 | 컨테이너 시작 시 고정 | 실패 | 런타임 변경 불가 |
| 컨테이너 재시작 | mount 재설정 | 성공하나 기각 | 불필요한 다운타임 |
| **inotify + 디렉토리 mount** | **디렉토리 수준 bind mount** | **성공** | — |

핵심 원리는 하나다: **bind mount는 inode를 참조한다.** 파일 수준으로 bind mount하면 원본이 삭제-재생성될 때 inode가 바뀌어 mount가 끊긴다. 디렉토리 수준으로 mount 단위를 올리면, 디렉토리 inode는 유지되므로 내부 파일이 교체되어도 컨테이너가 최신 파일을 볼 수 있다.

그리고 이 원리는 Docker에만 국한되지 않는다. [다른 글]({% post_url 2026-03-07-Kubernetes-ConfigMap-Inode %})에서는 Kubernetes ConfigMap의 일반 mount와 subPath mount가 왜 업데이트 반영 방식이 다른지, 그것이 이 글에서 다룬 문제와 왜 같은 뿌리인지를 살펴본다.

<br>
