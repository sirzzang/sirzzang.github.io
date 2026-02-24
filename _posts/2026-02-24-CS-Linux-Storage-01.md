---
title:  "[CS] 리눅스 스토리지 기초 - 1. 블록 디바이스, 파티션, 파일 시스템"
excerpt: "디스크가 '쓸 수 있는 공간'이 되기까지의 과정을 살펴보자."
categories:
  - CS
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Linux
  - Storage
  - Block Device
  - Partition
  - File System
  - ext4
  - xfs
  - MBR
  - GPT
---

<br>

리눅스에서 디스크를 사용하려면 세 가지 단계를 거친다: 디스크 인식(블록 디바이스) → 파티션 나누기 → 파일 시스템으로 포맷. 이 글에서는 물리적 디스크가 "쓸 수 있는 공간"이 되기까지의 과정을 살펴본다.

> 장치 파일과 디바이스 드라이버 구조에 대한 기본 개념은 [Everything is a File 철학]({% post_url 2026-01-31-CS-Everything-is-a-File %})과 [리눅스 디바이스 드라이버 구조]({% post_url 2026-02-01-CS-Linux-Device-Driver %})를 참고하자.

<br>

# TL;DR

- **블록 디바이스**: 디스크처럼 고정 크기 블록 단위로 데이터를 읽고 쓰는 장치. `/dev/sda`, `/dev/nvme0n1` 등
- **파티션**: 하나의 디스크를 논리적으로 나눈 영역. MBR(2TB 제한)과 GPT(사실상 무제한) 방식이 있다
- **파일 시스템**: 파티션 위에 데이터를 구조화하는 방식. ext4, xfs, btrfs 등
- **흐름**: 디스크 인식 → 파티션 생성 → 파일 시스템 포맷 → 마운트(다음 글)

<br>

# 블록 디바이스와 캐릭터 디바이스

리눅스에서 장치는 크게 두 종류로 나뉜다.

| 구분 | 블록 디바이스 | 캐릭터 디바이스 |
|------|-------------|---------------|
| 데이터 단위 | 고정 크기 블록(보통 512B~4KB) | 바이트 스트림 |
| 랜덤 접근 | 가능 | 불가 (순차) |
| 예시 | `/dev/sda`, `/dev/nvme0n1` | `/dev/tty`, `/dev/null` |
| 용도 | 디스크, SSD | 터미널, 시리얼 포트, GPU |

`/dev` 디렉토리에서 장치 파일을 확인할 수 있다.

```bash
ls -l /dev/sda /dev/tty
# brw-rw---- 1 root disk 8, 0 ... /dev/sda
# crw-rw-rw- 1 root tty  5, 0 ... /dev/tty
```

출력의 첫 글자가 장치 타입을 나타낸다. `b`는 블록 디바이스, `c`는 캐릭터 디바이스다. `8, 0`과 `5, 0`은 각각 major/minor 번호다.

## major/minor 번호

- **major 번호**: 어떤 드라이버가 이 장치를 담당하는지 식별 (예: 8 = SCSI 디스크 드라이버)
- **minor 번호**: 같은 드라이버가 담당하는 여러 장치 중 어떤 것인지 식별 (예: 0 = 첫 번째 디스크)

## 디스크 인식 확인

```bash
# 연결된 블록 디바이스 목록
lsblk
# NAME   SIZE TYPE MOUNTPOINT
# sda    500G disk
# ├─sda1  50G part /
# └─sda2 450G part /home

# 파티션 테이블 정보
fdisk -l /dev/sda
```

<!-- TODO: 블록 디바이스 내부 구조 (섹터, 블록, I/O 스케줄러) -->

<br>

# 파티션

## 파티션이란

하나의 물리적 디스크를 논리적으로 나누는 것이다. 운영체제는 각 파티션을 독립적인 스토리지 영역으로 다룬다.

```
lsblk
NAME   SIZE TYPE MOUNTPOINT
sda    500G disk
├─sda1  50G part /
├─sda2  20G part /boot
└─sda3 430G part /home

sdb    1TB  disk
└─sdb1  1TB part /mnt/data
```

여기서 자주 혼동되는 세 가지 개념을 구분할 필요가 있다.

- **파티션**: 디스크의 물리적 영역 (`sda1`)
- **파일 시스템**: 그 파티션에 설치된 데이터 구조 (`ext4`, `xfs`)
- **마운트 포인트**: 파일 시스템이 디렉토리 트리에 연결된 경로 (`/`, `/home`)

```bash
물리적 계층:
디스크 sda → 파티션 sda1 (ext4로 포맷됨)
디스크 sdb → 파티션 sdb1 (xfs로 포맷됨)

논리적 계층 (VFS):
/ (sda1의 ext4가 마운트됨)
├── bin/
├── var/
└── mnt/
    └── data/  (sdb1의 xfs를 여기에 마운트 가능)
```

## 파티션 테이블: MBR vs. GPT

파티션 테이블은 디스크의 파티션 정보를 기록하는 방식이다.

| 구분 | MBR (Master Boot Record) | GPT (GUID Partition Table) |
|------|--------------------------|----------------------------|
| 최대 디스크 크기 | 2TB | 사실상 무제한 (약 9.4ZB) |
| 최대 파티션 수 | 4개 (주 파티션) | 128개 |
| 부팅 방식 | BIOS | UEFI |
| 안정성 | 단일 복사본 | 헤더/테이블 이중 백업 |

### MBR의 2TB 제한

MBR은 512바이트 섹터를 기본 단위로 쓰고, 주소를 32비트로 표현한다.

```
2^32 × 512B = 4,294,967,296 × 512 = 2,199,023,255,552B ≈ 2TB
```

32비트 주소 공간으로 512바이트 섹터를 가리키면, 최대 약 2TB까지만 주소 지정이 가능하다.

### GPT의 해결

GPT는 64비트 LBA(Logical Block Addressing)를 사용해 이 제한을 없앴다.

<!-- TODO: 실무에서 1.82T SSD를 다루는 사례 추가 -->

## 파티셔닝 도구

| 도구 | 대상 | 특징 |
|------|------|------|
| `fdisk` | MBR | 대화형, 전통적 |
| `gdisk` | GPT | fdisk의 GPT 버전 |
| `parted` | MBR/GPT 모두 | 스크립트 가능, 범용 |

<br>

# 파일 시스템

파티션을 나눴으면 그 위에 파일 시스템을 만들어야 한다. 파일 시스템은 데이터를 디스크에 어떻게 구조화해서 저장할지 정의하는 체계다.

## 종류

크게 두 가지로 나뉜다.

### 블록 디바이스 기반 파일 시스템

물리적 디스크(블록 디바이스) 위에 데이터를 저장한다. 일반적으로 "파일 시스템"이라 하면 이쪽을 말한다.

- ext4, xfs, btrfs 등

### 논리적/가상 파일 시스템

물리적 블록 디바이스가 없다. 다른 소스를 파일 시스템 인터페이스로 보여준다.

| 파일 시스템 | 데이터 소스 |
|------------|-----------|
| OverlayFS | 기존 디렉토리들을 조합 |
| tmpfs | RAM |
| procfs, sysfs | 커널 메모리 |
| bindfs | 다른 디렉토리의 뷰 |

## ext4 vs. xfs vs. btrfs

| 항목 | ext4 | xfs | btrfs |
|------|------|-----|-------|
| 저널링 | 메타데이터+데이터 | 메타데이터만 | CoW 기반 |
| 확장 | 가능 | 가능 | 가능 |
| 축소 | 가능 | **불가** | 가능 |
| inode 할당 | 포맷 시 고정 | 동적 할당 | 동적 할당 |
| 최대 파일 크기 | 16TB | 8EB | 16EB |
| K8s PV 용도 | 범용, 기본값 | 대용량/고성능 | 스냅샷 활용 |

<!-- TODO: 저널링 방식 상세 (write-ahead logging, CoW) -->
<!-- TODO: inode 할당 방식 차이 상세 -->
<!-- TODO: K8s PV 용도에서의 선택 기준 실무 사례 -->

## mkfs로 포맷하기

```bash
# ext4로 포맷
mkfs.ext4 /dev/sdb1

# xfs로 포맷
mkfs.xfs /dev/sdb1

# 포맷 결과 확인
lsblk -f
# NAME   FSTYPE LABEL UUID                                 MOUNTPOINT
# sdb1   ext4         a1b2c3d4-...                         /mnt/data
```

<br>

# 정리

디스크를 사용 가능한 스토리지로 만드는 과정을 정리하면 다음과 같다.

```
물리적 디스크 (/dev/sda)
    ↓ 파티셔닝 (fdisk, gdisk, parted)
파티션 (/dev/sda1, /dev/sda2)
    ↓ 포맷 (mkfs.ext4, mkfs.xfs)
파일 시스템 (ext4, xfs)
    ↓ 마운트 (mount)
디렉토리 트리에 연결 (/mnt/data)
```

이 글에서는 마운트 전까지, 즉 블록 디바이스 인식 → 파티션 분할 → 파일 시스템 생성까지를 다뤘다. 파일 시스템이 준비되었으면 마운트를 통해 디렉토리 트리에 연결해야 한다.
