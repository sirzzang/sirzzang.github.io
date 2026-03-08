---
title:  "[Container] 컨테이너 파일 시스템"
excerpt: "물리 디스크에서 컨테이너 루트 파일시스템까지, 컨테이너가 파일 시스템을 구성하는 원리를 살펴보자."
categories:
  - CS
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Linux
  - Container
  - OverlayFS
  - Union File System
  - Copy-on-Write
  - Storage Driver
  - Mount Namespace

---

<br>

컨테이너 안에서 `/bin/sh`를 실행하면, 그 파일은 어디에서 오는 걸까? 물리 디스크에 저장된 이미지 데이터가 어떻게 컨테이너의 루트 파일시스템(`/`)이 되는지, 그 과정을 아래 순서 관점에서 정리해 본다.

```
이미지(tar.gz) → 풀기(스토리지 드라이버) → 합치기(OverlayFS) → 격리(namespace) → 사용(VFS)
```

<br>

# TL;DR

1. **이미지는 압축 파일 묶음**: 여러 레이어(`tar.gz`)로 구성
2. **스토리지 드라이버가 레이어를 푼다**: 압축 해제하여 호스트 디스크에 디렉토리로 저장하는 유저스페이스 모듈
3. **OverlayFS가 하나로 합친다**: 리눅스 커널이 제공하는 Union File System. lower(읽기 전용) + upper(쓰기) = merged(통합 뷰). Copy-on-Write로 lower를 보호
4. **mount namespace + pivot_root로 격리**: merged 디렉토리를 컨테이너만의 독립된 `/`로 만듦
5. **컨테이너가 파일을 읽으면**: VFS가 투명하게 OverlayFS → ext4로 중개. 컨테이너는 OverlayFS 위라는 사실을 모름

<br>

# 배경 지식: 리눅스 스토리지

## 파일 시스템

데이터를 디스크에 어떻게 구조화해서 저장할지 정의하는 체계다. 크게 두 종류로 나뉜다.

- **블록 디바이스 기반 파일 시스템**: 물리적 디스크 위에 데이터를 저장한다. ext4, xfs, btrfs 등. 일반적으로 "파일 시스템"이라 하면 이쪽을 말한다.
- **논리적/가상 파일 시스템**: 물리적 블록 디바이스가 없다. 다른 소스를 파일 시스템 인터페이스로 보여준다. OverlayFS(기존 디렉토리들을 조합), tmpfs(RAM), procfs/sysfs(커널 메모리) 등.

## 마운트

파일 시스템을 디렉토리 트리의 특정 지점에 연결하는 작업이다. 블록 디바이스 기반이든 논리적 파일 시스템이든 동일하다.

```bash
mount -t ext4 /dev/sda1 /mnt/data        # 블록 디바이스 기반
mount -t overlay overlay -o ... /merged  # 논리적 파일 시스템
mount -t proc proc /proc                 # 가상 파일 시스템
mount --bind /src /dst                   # bind mount (디렉토리 연결)
```

마운트 포인트에 접근하면, 해당 파일 시스템의 드라이버가 호출된다. 마운트 포인트 디렉토리에 기존 파일이 있었다면, 마운트 기간 동안 가려지고 마운트된 파일 시스템의 내용만 보인다.

```bash
$ ls /mnt/data
original.txt                # 기존 파일

$ mount /dev/sdb1 /mnt/data
$ ls /mnt/data
disk_content.txt            # 마운트된 파일 시스템 내용만 보임 (original.txt는 가려짐)

$ umount /mnt/data
$ ls /mnt/data
original.txt                # 언마운트하면 다시 보임
```

보통 마운트 포인트는 빈 디렉토리를 사용하는 것이 관례다.

### bind mount {#bind-mount}

`mount --bind`는 새로운 파일 시스템을 마운트하는 것이 아니라, **기존 디렉토리를 다른 경로에서도 접근할 수 있게** 해 주는 것이다. 원본과 bind mount된 경로는 같은 데이터를 가리키며, 한쪽에서 변경하면 다른 쪽에도 반영된다.

```bash
mount --bind /src /dst
# /dst에 접근하면 /src의 내용이 보임
```

컨테이너에서는 호스트 디렉토리를 컨테이너 안에 연결하는 볼륨 마운트(`-v /host/path:/container/path`)의 원리가 된다.

### 마운트 테이블

마운트를 수행하면 커널의 **마운트 테이블**에 항목이 추가된다. 마운트 테이블은 "**무엇을**(파일 시스템 소스) → **어디에**(경로)" 매핑이다. 소스는 블록 디바이스(`/dev/sda1`)일 수도, OverlayFS나 procfs 같은 논리적 파일 시스템일 수도 있다.

## VFS (Virtual File System)

커널이 다양한 파일 시스템을 **동일한 인터페이스로 추상화**하기 위해 사용하는 계층이다.

```
              사용자 프로세스
                  | open(), read(), write()
                  ↓
┌──────────────────────────────────┐
│    VFS (통합 인터페이스)             │
└──────────────────────────────────┘
     |           |            |
  ┌──┘           |            └──┐
  ↓              ↓               ↓
ext4 driver   OverlayFS        procfs
  ↓            driver            ↓
물리 블록          ↓             커널 메모리
             다른 디렉토리
```

각 파일 시스템(ext4, OverlayFS, procfs 등)은 자신만의 커널 드라이버를 가지고 있다. 사용자는 어떤 파일 시스템이든 구분 없이 동일한 `open()`, `read()`, `write()` 시스템 콜을 사용하고, VFS가 경로를 한 단계씩 따라가다가 마운트 포인트를 만나면 해당 파일 시스템의 드라이버로 처리를 넘긴다.

<a id="드라이버의-의미"></a>
> 참고: 드라이버의 의미
>
> 드라이버는 원래 무언가를 구동/제어하는 소프트웨어라는 넓은 의미를 가진다.
> - 장치 드라이버 (USB, GPU 등): 하드웨어 ↔ OS 간 통신
> - 파일 시스템 드라이버 (ext4, OverlayFS 등): 파일 시스템별 읽기/쓰기 처리
> - 데이터베이스 드라이버: 애플리케이션 ↔ DB 간 통신

```
open("/var/lib/.../merged/bin/sh")

/ → ext4로 처리
/var → ext4로 계속
/var/lib/.../merged → 마운트 포인트 발견 → OverlayFS로 전환
/bin/sh → OverlayFS가 upper/lower 탐색
```

```
open("/etc/hostname")

/ → ext4로 처리
/etc → ext4로 계속
/hostname → ext4가 inode 조회 → 블록 디바이스에서 데이터 읽기
```

```
read("/dev/sda")

/ → ext4로 처리
/dev → tmpfs(devtmpfs) 마운트 포인트 발견 → devtmpfs로 전환
/sda → 디바이스 파일(블록 디바이스) → 디바이스 드라이버 호출
```

같은 `open()`, `read()` 호출이지만, 경로에 따라 VFS가 다른 드라이버를 호출하는 것이다.

## 슈퍼블록

파일 시스템 전체의 메타데이터를 담는 커널 구조체(`struct super_block`)다. "이 파일 시스템은 어떤 종류이고, 어떤 연산을 지원하는가"에 대한 정보가 들어 있다. 구조체는 동일하지만, 출처가 다르다.

- **블록 디바이스 기반 FS**: 디스크에 슈퍼블록이 기록되어 있고, 마운트 시 커널 메모리에도 복사됨
- **논리적 FS (OverlayFS 등)**: 디스크에 슈퍼블록이 없고, **마운트 시 메모리에만 생성**됨

<br>

# 전체 흐름 미리보기

컨테이너 내부에서 `/bin/sh`를 실행할 때, 물리 디스크의 데이터가 컨테이너 프로세스까지 도달하는 전체 경로는 다음과 같다.

```
물리 디스크 (/dev/sda)
    ↓ 파티셔닝 + 포맷
파일 시스템 (ext4, xfs)
    ↓ mount                                     ┐
호스트 디렉토리 트리  ← 일반 디렉토리 구조                
    ↓ [1]                                       │ 
레이어 디렉토리들    ← 이미지 레이어가 풀린 디렉토리           -- VFS
    ↓ [2]                                       │  
merged           ← 레이어들이 하나로 합쳐진 뷰        
    ↓ [3]                                       ┘
컨테이너 루트 파일시스템 (/)

[1] 스토리지 드라이버: 이미지 pull → 레이어 압축 해제하여 디렉토리로 저장
[2] OverlayFS: mount -t overlay ... (레이어 합성)
[3] mount namespace + pivot_root (격리)
```

[VFS](#vfs-virtual-file-system)는 위 흐름의 특정 단계가 아니라, ext4 마운트부터 OverlayFS 마운트까지 **모든 파일 접근을 중개하는 추상화 계층**이다.

이 글에서는 위 흐름을 다섯 단계로 나누어 살펴본다.

<br>

# 1. 이미지는 압축 파일 묶음이다

[컨테이너 이미지]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-1 %})는 여러 개의 **레이어**로 구성되어 있으며, 각 레이어는 `tar.gz` 형태의 압축 파일로 레지스트리에 저장되어 있다. 이미지를 pull하면 이 압축 파일들을 받아오는 것이다.

```
컨테이너 이미지 (Registry)
├── Layer 1: base-layer.tar.gz        (OS 기본 파일)
├── Layer 2: app-layer.tar.gz         (애플리케이션 파일)
└── Layer 3: config-layer.tar.gz      (설정 파일)
```

<br>

# 2. 스토리지 드라이버가 레이어를 푼다

## 개념

스토리지 드라이버(snapshotter)란, **이미지 레이어를 디스크에 어떻게 저장하고 관리할지 정의하는 유저스페이스 모듈**이다. 여기서 '드라이버'는 [배경 지식에서 설명한 것처럼](#드라이버의-의미) 무언가를 구동하는 소프트웨어라는 넓은 의미다. 이미지 pull 시 레이어를 압축 해제하여 호스트의 일반 파일 시스템(ext4 등) 위에 디렉토리로 저장하고, 컨테이너 실행 시 [다음 단계](#3-overlayfs가-하나로-합친다)인 OverlayFS에 전달할 mount 명령을 조립한다.

```
Container Runtime
      ↓
Storage Driver (유저스페이스)    ← 레이어 저장, mount 명령 조립
      ↓
OverlayFS (커널)               ← 레이어 합성, 쓰기 격리
      ↓
Filesystem (ext4, xfs, etc.)
      ↓
Disk (hardware)
```

<br>

## 구현체

컨테이너 런타임별로 자체 스토리지 드라이버 구현을 가지고 있다.

```
                     OverlayFS (kernel)
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
   dockerd          containerd        Podman/CRI-O
   overlay2         snapshotter       overlay driver
```

> Docker와 Podman/CRI-O는 이 모듈을 **"스토리지 드라이버"**라고 부르고, containerd는 **"snapshotter"**라고 부른다. 이름은 다르지만, 이미지 레이어를 디스크에 저장하고 OverlayFS mount 명령을 조립하는 유저스페이스 모듈이라는 점은 동일하다.

<br>

## 이미지 pull에서 레이어 저장까지

이미지 pull부터 레이어가 디렉토리로 준비되기까지의 일반적인 흐름은 다음과 같다.

```
Registry에서 pull
    ↓ 이미지 blob(레이어 tar.gz, manifest, config) 다운로드
로컬에 저장
    ↓ 스토리지 드라이버가 각 레이어를 압축 해제
레이어 디렉토리들 (각 레이어가 파일시스템 디렉토리로 풀림)
```

런타임별 구체적인 저장 경로는 다르다.

| 단계 | dockerd (overlay2) | containerd (overlayfs snapshotter) |
|------|--------------------|------------------------------------|
| 원본 blob 저장 | 압축 해제 후 원본 tar 미보관 (digest 매핑 정보는 유지) | Content Store (`io.containerd.content.v1.content/blobs/sha256/`) |
| 레이어 압축 해제 | `overlay2/{layer-id}/diff/` | `io.containerd.snapshotter.v1.overlayfs/snapshots/{id}/fs/` |

각 스토리지 드라이버가 관리하는 것은 다음과 같다.

```
overlay2 (dockerd storage driver)
  - 레이어별 디렉토리 구조 (diff/, link/, work/, etc.)
  - 메타데이터 관리 (lower, upper path tracking)
  - 레이어 캐싱 전략 (build cache optimization)
```

```
overlayfs snapshotter (containerd snapshotter)
  - Content Store에 blob 저장 (압축 상태 보존)
  - Snapshot으로 압축 해제 (prepare → commit)
  - 레이어 재사용 (동일 digest 공유)

Content Store (blobs/sha256/...)     ← tar.gz 압축 상태
  ↓  snapshotter가 압축 해제
Snapshot 디렉토리 (snapshots/{id}/fs/)  ← 레이어 디렉토리
```

> 각 런타임별 실제 디렉토리 구조 비교는 [Docker와 containerd 이미지 관리 비교 - 2편]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-2 %}#실제-디렉토리-구조-확인)을 참고한다.

<br>

# 3. OverlayFS가 하나로 합친다

이전 단계에서 스토리지 드라이버가 레이어를 디렉토리로 풀어 놓았다. 이제 이 디렉토리들을 하나의 통합된 파일시스템으로 합쳐야 한다. 이 역할을 하는 것이 **OverlayFS**다.

## Union File System

여러 디렉토리를 하나로 합쳐서 보여 주는 파일 시스템을 Union File System이라 한다.

```
Layer 3 (top)   ──┐
Layer 2         ──┼──  Unified filesystem view
Layer 1 (base)  ──┘
```

### 컨테이너에서의 활용

컨테이너는 이 구조 위에 쓰기 레이어를 얹는다.

```
[Container Filesystem]
Writable Layer (per container)  ←─ 쓰기 가능, 변경 기록
    │
Image Layer 3        ──┐
Image Layer 2        ──┼───────── 읽기 전용, 공유
Image Layer 1 (base) ──┘
```

이 구조가 컨테이너의 설계 철학과 맞아떨어진다.

1. **불변성(Immutability)**: 이미지 레이어는 읽기 전용이므로, 여러 컨테이너가 공유해도 불변성이 보장된다.
  ```
  Container A (writable layer)  ──┐
                                  ├── Shared image layers (read-only)
  Container B (writable layer)  ──┘
  ```
2. **디스크 효율성**: 같은 베이스 이미지를 쓰는 컨테이너가 100개 실행되더라도, 베이스 레이어는 한 번만 저장하면 된다.
3. **빠른 컨테이너 생성**: 이미지 전체를 복사하지 않고, 얇은 쓰기 레이어만 추가하면 된다.
4. **레이어 캐싱**: 이미지 빌드 시에도 변경된 레이어만 새로 만들면 된다.

<br>

## OverlayFS 구조

OverlayFS는 리눅스 커널이 지원하는 Union File System 구현체이며, [논리적 파일 시스템](#파일-시스템)의 한 종류다. 물리적 블록 디바이스 없이 기존 디렉토리들을 입력으로 받아 합성해서 보여준다. 대부분의 배포판에서 커널 모듈(`overlay.ko`)로 제공된다.

```
Upper (writable)    ──┐
                      ├──  Merged (unified single view)
Lower (read-only)   ──┘
```

네 가지 디렉토리로 구성된다.
- **Lower**: 읽기 전용 베이스 레이어. 여러 개를 `:` 로 구분하여 쌓을 수 있음
- **Upper**: 변경 사항이 기록되는 쓰기 가능 레이어
- **Work**: 파일 변경 작업 시 중간 상태를 숨기기 위해 사용하는 임시 디렉토리
- **Merged**: Lower와 Upper를 합친 통합된 파일시스템 뷰

[마운트](#마운트) 명령으로 이 디렉토리들을 합성한다.

```
mount  -t overlay  overlay  -o <옵션>          /merged
        ── [1] ──  ─ [2] ─  ── [3] ──          ─ [4] ─

[1] 파일 시스템 타입: overlay
[2] 디바이스(소스): 논리적 FS라 블록 디바이스가 없고, 관례상 타입명을 반복
[3] 옵션: lowerdir, upperdir, workdir 지정
[4] 마운트 포인트: 합성 결과가 보이는 경로
```

```bash
mount -t overlay overlay \
  -o lowerdir=/lower1:/lower2,upperdir=/upper,workdir=/work \
  /merged
```

- `lowerdir=/lower1:/lower2`: 읽기 전용 레이어. `:`로 구분하여 여러 개를 쌓으며, 왼쪽이 위(우선순위 높음)
- `upperdir=/upper`: 쓰기 가능 레이어. 모든 변경 사항이 여기에 기록됨
- `workdir=/work`: OverlayFS가 내부적으로 사용하는 임시 디렉토리. upperdir과 같은 파일 시스템에 있어야 함
- `/merged`: 마운트 포인트. lower + upper가 합쳐진 통합 뷰가 이 경로에 나타남

<br>

## 파일 연산 {#copy-on-write-cow}

Union File System의 핵심 원칙은 **Lower(읽기 전용)를 절대 건드리지 않고, 모든 변경을 Upper(쓰기 가능)에만 기록**하는 것이다. 이 원칙을 대표하는 동작이 **Copy-on-Write (CoW)**다. Lower의 파일을 수정하면 해당 파일 전체를 Upper로 복사한 뒤(copy-up) 수정하기 때문에 이런 이름이 붙었다. CoW는 Union File System이라면 공통적으로 가지는 동작이며, OverlayFS는 이를 **파일 단위**로 구현한다. 삭제 역시 Lower를 건드리지 않고 Upper에만 기록(whiteout)한다는 점에서 같은 원칙을 따른다.

OverlayFS가 각 파일 연산을 처리하는 방식은 다음과 같다.

### 파일 읽기

Upper에 없으면 Lower에서 직접 읽는다.

```
Upper: (없음)
Lower: file.txt ← 여기서 직접 읽음
Merged → Lower의 file.txt
```

### 파일 생성

Upper에 직접 생성한다.

```
Upper: new.txt ← 직접 생성
Lower: (없음)
Merged → Upper의 new.txt
```

### 파일 수정: CoW

Lower의 파일을 Upper로 복사한 후 수정한다 (copy-up). copy-up 시 파일 데이터뿐 아니라 퍼미션, xattr 등 메타데이터도 함께 복사된다. Lower의 원본은 유지된다.

```
Upper: file.txt (수정됨) ← Lower에서 복사 후 수정
Lower: file.txt (원본 유지)
Merged → Upper의 file.txt (수정본)
```

### 파일 삭제: whiteout

Upper에 whiteout 파일(`.wh.<파일명>`)을 생성하여 삭제를 표시한다. Lower의 원본은 유지되지만 Merged에서는 보이지 않는다.

```
Upper: .wh.file.txt (whiteout 파일)
Lower: file.txt (원본 유지)
Merged → file.txt 안 보임
```

디렉토리를 삭제할 경우, Upper에 해당 디렉토리를 생성하고 그 안에 `.wh..wh..opq`(opaque whiteout) 파일을 둔다. 이렇게 하면 Lower의 동명 디렉토리 내용이 모두 가려지고, Upper의 새 내용만 Merged에 나타난다. 디렉토리를 삭제한 뒤 같은 이름으로 재생성하는 경우에도 이 메커니즘이 사용된다.

```
Upper: dir/.wh..wh..opq (opaque whiteout)
Lower: dir/a.txt, dir/b.txt
Merged → dir/ (비어 있음, Lower 내용 가려짐)
```

<br>

## 스토리지 드라이버가 조립한 OverlayFS 마운트

[2장](#2-스토리지-드라이버가-레이어를-푼다)에서 스토리지 드라이버가 이미지 레이어를 디렉토리로 풀어 놓았다. 컨테이너가 실행되면, 스토리지 드라이버는 이 디렉토리들을 OverlayFS의 lower/upper에 매핑하여 mount 명령을 조립한다.

```
이미지 레이어 디렉토리들 (2장)       →  lowerdir (읽기 전용)
컨테이너 전용 디렉토리 (새로 생성)    →  upperdir (쓰기 가능) + workdir (임시)
        │
        ↓  mount -t overlay
        │
   merged (통합 뷰)
        │
        ↓  [4장] 컨테이너 rootfs로 격리
```

대표적인 런타임별로 어떻게 이를 수행하는지 확인해 보자.

### dockerd (overlay2)

```bash
mount -t overlay overlay \
  -o lowerdir=overlay2/{layer3-id}/diff:overlay2/{layer2-id}/diff:overlay2/{layer1-id}/diff,\
     upperdir=overlay2/{container-id}/diff,\
     workdir=overlay2/{container-id}/work \
  overlay2/{container-id}/merged
```

- `lowerdir`: [이미지 레이어](#이미지-pull에서-레이어-저장까지)들의 `diff/` 디렉토리 (읽기 전용, 공유)
- `upperdir`: 컨테이너 생성 시 새로 만든 `diff/` 디렉토리 (컨테이너 전용)
- `merged`: 컨테이너의 rootfs가 되는 통합 뷰

### containerd (overlayfs snapshotter)

```bash
mount -t overlay overlay \
  -o lowerdir=snapshots/{id3}/fs:snapshots/{id2}/fs:snapshots/{id1}/fs,\
     upperdir=snapshots/{active-id}/fs,\
     workdir=snapshots/{active-id}/work \
  /run/containerd/.../rootfs
```

- `lowerdir`: committed snapshot들의 `fs/` 디렉토리 (읽기 전용, 공유)
- `upperdir`: 컨테이너 생성 시 prepare한 active snapshot의 `fs/` (컨테이너 전용)
- `merged`: `/run/containerd/` 아래에 마운트되어 컨테이너의 rootfs가 됨

이렇게 조립된 merged 디렉토리는 아직 호스트의 특정 경로에 있는 일반 디렉토리일 뿐이다. 이것을 컨테이너만의 루트(`/`)로 만드는 것이 [다음 단계](#4-mount-namespace--pivot_root로-격리)의 역할이다.

> 각 런타임별 실제 디렉토리 구조의 상세 비교는 [스토리지 드라이버 구현 비교 - 2편]({% post_url 2025-12-12-Dev-Container-Duplicate-Container-Images-2 %}#실제-디렉토리-구조-확인)을 참고한다.

<br>

## 격리 vs. 공유

컨테이너마다 별도의 OverlayFS를 마운트하면 독립 [슈퍼블록](#슈퍼블록)이 생성되고, 각 컨테이너의 파일시스템 메타데이터가 분리된다. 독립 슈퍼블록은 격리의 원인이 아니라, 컨테이너마다 별도의 OverlayFS를 마운트한 **결과**이다.

```
컨테이너1:
  / → overlay sb #1
      ├── /app → 컨테이너1의 변경사항
      └── /data → 컨테이너1의 데이터

컨테이너2:
  / → overlay sb #2  // sb #1과 별도 객체
      ├── /app → 컨테이너2의 변경사항
      └── /data → 컨테이너2의 데이터
```

하지만 **실제 데이터(lower 레이어)는 공유**된다. 디스크에는 한 벌만 존재한다.

```bash
# 디스크에는 한 벌만 존재
/var/lib/containerd/io.../snapshots/
├── 1/  # base layer (여러 컨테이너가 공유)
│   └── bin/sh
├── 2/  # app layer (여러 컨테이너가 공유)
│   └── app/binary
├── 3/  # container1 writable (독립)
│   └── tmp/file1
└── 4/  # container2 writable (독립)
    └── tmp/file2

# 메모리에는 슈퍼블록이 여러 개
super_block1 # → lower: 1,2 / upper: 3
super_block2 # → lower: 1,2 / upper: 4
```

<details>
<summary>커널 수준에서 보기: 컨테이너별 슈퍼블록 생성 (의사 코드)</summary>

<br>

아래는 리눅스 커널의 실제 구조체(`struct super_block`, `s_type`, `s_root` 등)를 기반으로, 컨테이너별로 독립 슈퍼블록이 생성되는 과정을 단순화한 의사 코드이다. 실제 구현은 [`fs/overlayfs/super.c`](https://github.com/torvalds/linux/blob/master/fs/overlayfs/super.c)에 있다.

```c
// 컨테이너 1
struct super_block *sb1 = alloc_super();
sb1->s_type = &overlay_fs_type;
sb1->s_root = dentry1;  // /merged1의 루트
// lower: layer1, layer2
// upper: container1-upper

// 컨테이너 2
struct super_block *sb2 = alloc_super();  // 별도 메모리 할당
sb2->s_type = &overlay_fs_type;
sb2->s_root = dentry2;  // /merged2의 루트
// lower: layer1, layer2 (같은 레이어 재사용)
// upper: container2-upper (다른 upper!)
```

</details>

<br>

# 4. mount namespace + pivot_root로 격리

이전 단계에서 OverlayFS가 만든 merged 디렉토리는 아직 호스트의 특정 경로(`/var/lib/.../merged`)에 있는 일반 디렉토리일 뿐이다. 이것을 컨테이너만의 루트(`/`)로 만들고, 다른 컨테이너와 격리하는 것이 이 단계의 역할이다.

| 격리 메커니즘 | 역할 | 결과 |
|---|---|---|
| pivot_root | merged를 `/`로 교체 | 호스트 파일시스템 접근 차단 |
| mount namespace | 독립된 마운트 테이블 부여 | 마운트 변경이 서로 격리 |

<br>

## pivot_root

merged 디렉토리를 컨테이너의 루트(`/`)로 만들려면, 프로세스의 루트 파일시스템을 교체해야 한다.

### chroot의 한계

전통적으로 루트를 바꾸는 방법은 `chroot`다. 그러나 chroot는 프로세스의 **겉보기 루트 경로만** 변경할 뿐, 마운트 포인트 자체는 그대로 남기 때문에 탈출이 가능하다.

```bash
# chroot 탈출 예시 (root 권한 필요)
chroot /tmp/jail /bin/bash    # /tmp/jail이 새 루트(/)가 됨

# 이 상태에서 cd ../.. 만으로는 탈출 불가
# → 커널이 /에서 ..을 /로 해석하므로 루트 위로 올라갈 수 없음

# 탈출: 중첩 chroot 트릭
mkdir breakout
chroot breakout    # [1] 루트가 breakout으로 바뀜. 단, cwd는 변경되지 않음
                   #     → cwd가 새 루트 바깥에 위치하게 됨
cd ../../../..     # [2] cwd가 루트 밖이므로 ..로 실제 루트까지 이동 가능
chroot .           # [3] 실제 루트를 루트로 설정 → 탈출 완료
```

핵심은 `chroot`가 **루트만 바꾸고 현재 작업 디렉토리(cwd)는 건드리지 않는다**는 점이다. chroot 전에 열어둔 파일 디스크립터(`fchdir`)로 탈출하는 방법도 있다. 근본적으로 chroot는 경로 해석의 시작점만 바꾸는 것이라, 마운트 구조를 건드리지 않아 격리가 불완전하다.

### pivot_root

`pivot_root`는 **실제 마운트 포인트 자체를 교체**하는 시스템 콜이다. 새 루트를 마운트하고, 기존 루트를 분리하여 완전히 제거할 수 있다.

```bash
# 의사 코드: 컨테이너 런타임(runc)이 내부적으로 수행하는 작업
mount -t overlay overlay -o lowerdir=...,upperdir=...,workdir=... /new_root
cd /new_root
pivot_root . ./old_root   # /new_root를 /로, 기존 /를 ./old_root로
umount -l ./old_root       # 기존 루트 완전 분리 → 호스트 파일시스템 접근 불가
```

chroot와 달리 기존 루트가 마운트 트리에서 완전히 제거되므로, 상대 경로나 파일 디스크립터로 탈출할 수 없다.

<br>

## mount namespace

### 개념

pivot_root로 루트를 교체하더라도, 호스트와 같은 [마운트 테이블](#마운트)을 공유하면 컨테이너의 mount/umount가 호스트에 영향을 준다. mount namespace는 Linux 커널의 namespace 기능 중 하나로, 프로세스에게 **독립된 마운트 테이블**을 부여하여 이를 격리한다.

새 mount namespace를 만들면 부모의 마운트 테이블이 복사되고, 이후 한쪽에서 mount/umount해도 다른 쪽에 영향을 주지 않는다.

```
부모 프로세스 (마운트 테이블 A)
    │
    ├── unshare(CLONE_NEWNS)
    │
    └── 자식 프로세스 (마운트 테이블 A')  ← A의 복사본
        │
        ├── 자식이 mount/umount → A'만 변경, A는 무관
        └── 부모가 mount/umount → A만 변경, A'는 무관
```

### 컨테이너에서의 사용

컨테이너 런타임(runc 등)은 `clone(CLONE_NEWNS)` 또는 `unshare(CLONE_NEWNS)` 시스템 콜을 직접 호출하여 컨테이너 프로세스에 독립된 mount namespace를 부여한다. `unshare` 명령어로 동일한 동작을 수동으로 확인해 볼 수 있다.

```bash
# 새 mount namespace에서 셸 실행
sudo unshare --mount /bin/bash

# 이 셸 안에서의 mount/umount는 호스트에 영향을 주지 않음
mount -t tmpfs tmpfs /mnt
# → 호스트에서는 /mnt에 아무것도 마운트되지 않음
```


## 최종 마운트 테이블

mount namespace + pivot_root를 거치면, 호스트와 컨테이너는 각자의 마운트 테이블을 갖게 된다.

> 실제 컨테이너 런타임은 먼저 mount namespace를 생성한 뒤, 그 안에서 pivot_root를 호출한다. 이 글에서는 이해를 위해 pivot_root(무엇을 하는지)를 먼저 설명하고, mount namespace(어떻게 격리하는지)를 이어서 설명했다.


**호스트 마운트 테이블**

| 소스 | 경로 | 설명 |
|------|------|------|
| `/dev/sda1` (ext4) | `/` | 호스트 루트 |
| overlay (container1) | `/var/lib/.../merged1` | 컨테이너1용 OverlayFS |
| overlay (container2) | `/var/lib/.../merged2` | 컨테이너2용 OverlayFS |
| proc | `/proc` | 호스트 proc |
| sysfs | `/sys` | 호스트 sysfs |

**컨테이너 마운트 테이블** (호스트에서 복사 후 독립)

| 소스 | 경로 | 설명 |
|------|------|------|
| overlay (container1) | `/` | pivot_root로 merged를 루트(`/`)에 매핑 |
| proc (새 인스턴스) | `/proc` | 커널이 새로 생성 (PID namespace 기반) |
| tmpfs (새 인스턴스) | `/dev` | 새로운 빈 tmpfs 생성 |

overlay는 호스트에서 만든 OverlayFS 마운트를 pivot_root로 `/`에 매핑한 것이고, proc과 tmpfs는 호스트 것을 공유하는 게 아니라 컨테이너마다 커널이 **새 인스턴스를 생성**한다.

<br>

<br>

# 부록: 컨테이너 시작 시 실행 순서

지금까지 살펴본 1~4단계를 시간 순서로 정리하면 다음과 같다.

1~2단계는 고수준 런타임(containerd)이, 3~7단계는 저수준 런타임(runc)이 담당한다.

```
호스트:    /var/lib/.../merged/bin/sh
                        ↓
컨테이너:                  /bin/sh
```

1. **스토리지 드라이버가 이미지 레이어 준비** [containerd]: Content Store → Snapshotter가 압축 해제 → 레이어 디렉토리들 준비
2. **OverlayFS 마운트** [containerd]: `mount -t overlay ... /run/.../merged`. lower에 이미지 레이어들(읽기 전용), upper에 새 쓰기 레이어를 지정하여 merged(통합 뷰) 생성
3. **mount namespace 생성** [runc]: `unshare(CLONE_NEWNS)`로 호스트와 독립된 마운트 테이블 생성
4. **pivot_root** [runc]: merged 디렉토리를 새로운 `/`로 설정하고, 기존 호스트 루트 분리
5. **필수 파일시스템 마운트** [runc]: `mount -t proc proc /proc`, `mount -t sysfs sysfs /sys`, `mount -t tmpfs tmpfs /dev`
6. **[bind mount](#bind-mount) (볼륨)** [runc]: `mount --bind /host/data /app/data` 등
7. **컨테이너 프로세스 시작** [runc]: `exec /entrypoint.sh`

<br>

# 5. 컨테이너의 파일 접근

1~4단계를 거쳐 루트 파일시스템이 구성된 이후, 컨테이너 안에서의 파일 접근은 일반적인 리눅스 프로세스와 동일하게 [VFS](#vfs-virtual-file-system)를 통해 처리된다. 컨테이너 프로세스는 자신이 OverlayFS 위에서 동작한다는 사실을 알지 못한다.

컨테이너 안에서 `open("/bin/sh")`를 호출하면, VFS는 이 프로세스의 `/`가 OverlayFS 마운트 포인트임을 인식하고 OverlayFS 드라이버를 호출한다. [4단계](#4-mount-namespace--pivot_root가-격리한다)에서 `pivot_root`를 수행했기 때문에, 이 프로세스의 `/` 자체가 OverlayFS merged 디렉토리다. OverlayFS는 upper → lower 순서로 파일을 탐색하고, 실제 데이터는 lower가 위치한 파일 시스템(ext4 등)의 드라이버를 다시 호출하여 읽는다.

```
open("/bin/sh")
    ↓ syscall
VFS: /는 OverlayFS 마운트 포인트 → OverlayFS 드라이버 호출
    ↓
OverlayFS: upper에서 탐색 → 없음 → lower에서 탐색 → 있음
    ↓
ext4 드라이버: lower 디렉토리에서 실제 데이터 읽기
```

파일을 수정하면 [CoW](#copy-on-write-cow)가 발생한다. OverlayFS가 lower의 원본을 upper로 복사한 뒤 수정을 반영하며, 이 과정에서 실제 디스크 I/O는 하위 파일 시스템 드라이버(ext4 등)에 위임한다.

```
write("/etc/config")
    ↓ syscall
VFS → OverlayFS 드라이버: upper에 없음 → copy-up 시작
    ↓ ext4_read()로 lower에서 원본 읽기
    ↓ ext4_write()로 upper에 복사
    ↓ upper의 복사본에 ext4_write()로 수정 반영
```

이처럼 OverlayFS는 upper/lower 탐색과 copy-up 로직만 담당하고, 실제 디스크 I/O는 하위 파일 시스템 드라이버에 위임한다. VFS가 이 전체를 투명하게 중개하기 때문에, 컨테이너 프로세스 입장에서는 일반 파일 시스템과 다를 바가 없다.

<br>

# 결론

컨테이너의 파일 시스템은 하나의 파이프라인으로 구성된다.

```
이미지(tar.gz) → 풀기(스토리지 드라이버) → 합치기(OverlayFS) → 격리(namespace) → 사용(VFS)
```

1. **이미지 레이어**(`tar.gz`)를 스토리지 드라이버가 디렉토리로 풀고
2. **OverlayFS**가 그 디렉토리들을 lower/upper로 합쳐 하나의 통합 뷰(merged)를 만들고
3. **pivot_root + mount namespace**가 merged를 컨테이너만의 독립된 `/`로 격리하고
4. 컨테이너가 파일에 접근하면 **VFS**가 투명하게 OverlayFS → ext4로 중개하며, **CoW**가 lower를 보호한다

이 모든 과정이 끝나면, 컨테이너 프로세스 입장에서는 일반 리눅스 파일 시스템과 다를 바가 없다.
