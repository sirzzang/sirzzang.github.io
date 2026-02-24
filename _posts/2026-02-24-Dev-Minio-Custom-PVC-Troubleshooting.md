---
title:  "[Kubernetes] MinIO Helm 배포 시 Custom PVC가 무시되는 문제 해결"
excerpt: "distributed 모드에서 existingClaim이 조용히 무시되는 원인을 분석하고, standalone 전환과 SSD 마운트를 통해 루트 파티션 과부하를 해결한 경험을 정리한다."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - K3s
  - MinIO
  - Helm
  - PV
  - PVC
  - trouble-shooting
---

<br>

2025년 초, 현장에 배포된 K3s 클러스터에서 MinIO를 운영하던 중 루트 파티션이 90%까지 차오르며 워크플로우가 중단되는 문제가 발생했다. 원인은 MinIO Helm chart의 `distributed` 모드에서 `persistence.existingClaim`이 **조용히 무시**되고, K3s 기본 StorageClass가 루트 파티션 하위에 PV를 생성하는 구조에 있었다.

당시에는 급하게 해결하고 넘어갔는데, 최근 리눅스 스토리지와 Kubernetes 스토리지 구조를 공부하면서 이 문제를 다시 꺼내 정리하게 되었다. 이 글에서는 문제의 원인 분석부터 SSD 증설, `standalone` 모드 전환을 통한 해결, 그리고 데이터 이관 과정에서의 삽질까지 복기한다.

<br>

# TL;DR

| 구분 | 내용 |
| --- | --- |
| **현상** | 루트 파티션 90% 사용, 워크플로우 중단 |
| **원인** | `distributed` 모드에서 `existingClaim` 무시 → K3s default StorageClass가 루트 파티션에 PV 생성 |
| **해결** | SSD 증설 → `standalone` 모드 전환 → `existingClaim`으로 SSD 경로의 PVC 연결 |
| **핵심** | StatefulSet의 `volumeClaimTemplates`는 `existingClaim`과 본질적으로 충돌한다 |

<br>

# 문제

## 현상: 루트 파티션 용량 부족

시스템이 배포된 현장 중 한 곳에서 K3s 클러스터 내 워크플로우 실행이 중지되는 현상이 발생했다. 보통 이런 경우 CPU 사용량, 디스크 사용량을 먼저 확인하게 되는데, 서버 접속 시부터 상황이 심상치 않았다.

```bash
System information as of Fri Feb  7 02:07:58 PM KST 2025

  System load:  0.35                Temperature:             35.0 C
  Usage of /:   85.4% of 231.70GB   Processes:               349
  Memory usage: 13%                 Users logged in:         1
  Swap usage:   1%                  IPv4 address for enp8s0: 172.5.1.97
```

**루트 파티션이 231.70GB 중 85.4%를 사용** 중이었다. `df -h`로 확인하니 실제로는 90%까지 차 있었다.

```bash
$ df -h
Filesystem                       Size  Used Avail Use% Mounted on
tmpfs                            3.2G  2.8M  3.2G   1% /run
/dev/mapper/ubuntu--vg-lv--0     232G  198G   23G  90% /
tmpfs                             16G     0   16G   0% /dev/shm
tmpfs                            5.0M     0  5.0M   0% /run/lock
/dev/nvme0n1p2                   2.0G  129M  1.7G   8% /boot
/dev/sda                         3.6T   65G  3.4T   2% /mnt/data
tmpfs                            3.2G  4.0K  3.2G   1% /run/user/1000
```

<br>

## 용량 분석: 루트 파티션은 누가 먹고 있는가

루트 파티션의 사용량을 추적해 보았다.

```bash
$ sudo du -sh /var/lib/*
# ...
137G  /var/lib       # /var/lib 전체
18G   /var/lib/docker
119G  /var/lib/rancher
# ...
```

```bash
$ sudo du -sh /var/lib/rancher/k3s/*
565M  agent
177M  data
145M  server
118G  storage
```

`/var/lib/rancher/k3s/storage`가 **118GB**를 차지하고 있었다. 이 디렉토리는 K3s의 기본 StorageClass인 `local-path`가 PV를 생성하는 경로다.

```bash
$ sudo du -sh /var/lib/rancher/k3s/storage/*
 20M  pvc-2df3a114-..._label-studio_label-studio-ls-pvc
118G  pvc-84164975-..._minio_export-minio-1
```

118GB 중 거의 전부가 **MinIO의 PVC** 하나에 집중되어 있었다. 루트 파티션 232GB 중 절반 이상을 MinIO가 혼자 쓰고 있었던 셈이다.

<br>

## 클러스터 상태 확인

MinIO의 배포 상태를 확인했다.

```bash
$ kubectl get all -n minio
NAME          READY   STATUS    RESTARTS   AGE
pod/minio-0   1/1     Running   0          87d
pod/minio-2   1/1     Running   0          87d
pod/minio-1   0/1     Pending   0          13d

NAME                     READY   AGE
statefulset.apps/minio   2/3     87d
```

```bash
$ kubectl get pvc -n minio
NAME             STATUS   VOLUME       CAPACITY   ACCESS MODES   STORAGECLASS   AGE
export-minio-2   Bound    pvc-44a76..  200Gi      RWO            local-path     87d
export-minio-0   Bound    pvc-4c779..  200Gi      RWO            local-path     87d
export-minio-1   Bound    pvc-84164..  200Gi      RWO            local-path     87d
```

```bash
$ helm list -n minio
NAME    NAMESPACE  REVISION  STATUS    CHART        APP VERSION
minio   minio      1         deployed  minio-5.2.0  RELEASE.2024-04-18T19-09-19Z
```

핵심적인 사실이 눈에 들어왔다.

- MinIO가 **StatefulSet**으로 배포되어 있다 (Pod 이름이 `minio-0`, `minio-1`, `minio-2`)
- PVC 이름이 `export-minio-0`, `export-minio-1`, `export-minio-2`로 자동 생성되어 있다
- 모든 PVC가 `local-path` StorageClass를 사용하고 있다

values.yaml에서 `persistence.existingClaim`을 지정했음에도, **해당 PVC는 사용되지 않고** `local-path`가 루트 파티션에 PV를 생성하고 있었다.

<br>

## 작업 제약

상황에는 일정 압박과 시간 압박이 동시에 있었다.

**일정 압박**: 시연 일정이 약 2주 뒤로 잡혀 있었다.

- 시연을 위해 라벨링 파이프라인을 돌려야 했다
  - 카메라 약 3,000대에서 영상을 수신하고, 프레임을 추출해 MinIO에 저장하는 구조
  - 파라미터: `duration=200` (카메라당 최대 200초 연결), `max_frames=100` (최대 100장 추출)
  - 예상 데이터량: 100장 × 3,000대 = **최대 300,000장**의 프레임 + annotation JSON
- 루트 파티션 잔여 용량 23GB로는 파이프라인 실행 자체가 불가능

**시간 압박**: 폐쇄망 환경에서 원격 지원과 현장 출장이 병행되는 구조였다.

- 현장 서버가 폐쇄망에 있어 직접 SSH 접속이 불가능했다. 소프트웨어 작업(클러스터 상태 확인, 원인 분석, Helm 재배포 등)은 현장 담당자와 화면 공유를 통해 원격으로 안내해야 했다
- SSD 물리 장착은 원격으로 해결할 수 없는 작업이라, 직접 현장에 가서 디스크를 설치했다
- 원격 세션과 현장 출장의 일정을 조율하고, 문제 확인 → SSD 장착 → 소프트웨어 해결을 최소한의 왕복으로 끝내야 했다

<br>

# 배경 지식

> 이 섹션은 문제의 원인을 이해하기 위한 최소한의 배경을 다룬다. StatefulSet, volumeClaimTemplates, Helm Chart의 조건부 렌더링에 대한 딥다이브는 추후 별도 글에서 다룰 예정이다.

## distributed 모드와 standalone 모드

MinIO Helm chart(v5.2.0)는 `mode` 값에 따라 완전히 다른 Kubernetes 리소스를 생성한다.

| 구분 | `distributed` (기본값) | `standalone` |
| --- | --- | --- |
| 리소스 | StatefulSet | Deployment |
| Pod 수 | 여러 개 (erasure coding) | 1개 |
| PVC 생성 | `volumeClaimTemplates`로 자동 생성 | `existingClaim` 또는 기본 PVC 참조 |
| `existingClaim` 동작 | **무시됨** | 정상 동작 |

핵심은 **StatefulSet의 `volumeClaimTemplates`**에 있다. StatefulSet은 각 Pod마다 별도의 PVC를 자동 생성하는데(`export-{statefulset명}-{ordinal}` 형식), 이 메커니즘이 `existingClaim`과 본질적으로 충돌한다. `existingClaim`은 하나의 PVC를 지정하는 것인데, StatefulSet은 Pod마다 별도 PVC가 필요하기 때문이다.

MinIO chart의 [statefulset.yaml 템플릿](https://github.com/minio/minio/blob/master/helm/minio/templates/statefulset.yaml#L251)을 보면, `volumeClaimTemplates`에서 `export`라는 이름으로 PVC 스펙을 정의한다. `existingClaim`을 참조하는 로직 자체가 없다.

반면 [deployment.yaml 템플릿](https://github.com/minio/minio/blob/master/helm/minio/templates/deployment.yaml#L197)에서는 `existingClaim`이 지정되어 있으면 해당 PVC를, 아니면 `minio.fullname`으로 생성된 PVC를 참조한다.

<br>

## K3s local-path provisioner

K3s는 기본 StorageClass로 `local-path`를 제공한다. 이 프로비저너는 PVC가 요청되면 **`/var/lib/rancher/k3s/storage`** 경로 아래에 hostPath 기반으로 PV를 동적 생성한다. 이 경로는 루트 파티션(`/`)에 위치하므로, PV에 데이터가 쌓이면 곧바로 루트 파티션 사용량이 증가한다.

<br>

## 문제 정리

결국 문제의 전체 경로는 다음과 같다.

```
values.yaml: mode=distributed (기본값)
    ↓
Helm이 StatefulSet 템플릿 렌더링
    ↓
volumeClaimTemplates로 export-minio-{0,1,2} PVC 자동 생성
    ↓
persistence.existingClaim 무시됨 (참조 로직 자체가 없음)
    ↓
local-path StorageClass가 /var/lib/rancher/k3s/storage에 PV 생성
    ↓
MinIO 데이터가 루트 파티션에 축적 → 용량 부족
```

<br>

# 해결

## 전략

1. SSD 증설 → `/mnt/data`에 마운트
2. SSD 경로에 PV 디렉토리 생성 → PV/PVC 매니페스트 작성
3. MinIO values.yaml에서 `mode: standalone` + `existingClaim` 지정 → 재배포

> SSD 물리 장착, 파티션 생성, 포맷(`mkfs.ext4`), fstab 등록, 마운트 적용 과정의 상세는 [리눅스 스토리지 기초]({% post_url 2026-02-24-CS-Linux-Storage-01 %}) 시리즈에서 다룬다. 여기서는 Kubernetes 관점의 해결 과정에 집중한다.

<br>

## SSD 마운트 (요약)

서버에 Samsung SSD 870(2TB, 1TB)을 SATA 포트로 장착하고, `/mnt/data`에 ext4로 마운트했다. fstab에 UUID로 등록하여 부팅 시 자동 마운트되도록 설정했다.

![ssd]({{site.url}}/assets/images/ssd.jpg){: .align-center}
<center><sup>설치한 디스크</sup></center>

![ssd-installation]({{site.url}}/assets/images/ssd-installation.jpg){: .align-center}
<center><sup>SATA 포트를 통해 장착</sup></center>

```bash
$ df -h | grep mnt
/dev/sda        3.6T   65G  3.4T   2% /mnt/data
```

<br>

## PV 디렉토리 생성 및 권한 설정

SSD 마운트 경로 아래에 MinIO PV용 디렉토리를 생성했다.

```bash
$ cd /mnt/data
$ sudo mkdir minio-pv
$ sudo chmod 777 minio-pv
```

권한을 `777`로 설정하지 않으면 MinIO Pod가 디렉토리에 접근하지 못한다.

```
ERROR Unable to use the driver /export: driver access denied
```

> **주의**: `chmod 777`은 빠른 해결을 위한 임시 조치다. production 환경에서는 Pod의 `securityContext.fsGroup`을 설정하거나, initContainer에서 `chown`을 실행하는 방식이 권장된다.

<br>

## PV/PVC 매니페스트 작성

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: minio-pv
  namespace: minio
spec:
  capacity:
    storage: 3Ti
  volumeMode: Filesystem
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: minio-storage-class
  nodeAffinity:
    required:
      nodeSelectorTerms:
        - matchExpressions:
            - key: kubernetes.io/hostname
              operator: In
              values:
                - server01-mlops01
  hostPath:
    path: "/mnt/data/minio-pv"
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: minio-pvc
  namespace: minio
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: minio-storage-class
  resources:
    requests:
      storage: 1Ti
```

hostPath PV에 `nodeAffinity`를 수동으로 지정했다. SSD가 장착된 노드(`server01-mlops01`)에서만 PV가 사용되도록 하기 위함이다.

> **참고**: 이 구성은 사실상 `local` PV 타입의 패턴을 hostPath로 직접 구현한 것이다. `local` PV는 `nodeAffinity`가 필수이고 스케줄러가 노드 위치를 인식하지만, hostPath는 스케줄러가 노드를 인식하지 못한다. 운영 환경에서는 `local` PV나 CSI 기반 로컬 스토리지(OpenEBS, TopoLVM 등)를 고려하는 것이 바람직하다.

```bash
$ kubectl apply -f minio-pv-pvc.yaml
```

<br>

## values.yaml 변경 및 재배포

```yaml
persistence:
  enabled: true
  existingClaim: "minio-pvc"

mode: standalone
```

변경 사항은 두 가지다.

1. **`mode: standalone`**: Deployment로 배포되어 `existingClaim`이 정상 동작하도록 변경
2. **`persistence.existingClaim: "minio-pvc"`**: 위에서 생성한 SSD 경로의 PVC를 지정

```bash
$ helm uninstall minio -n minio
$ helm install minio -n minio ./minio-5.2.0.tgz --values minio-values.yaml
```

> `distributed` → `standalone` 전환은 **erasure coding을 포기**하는 것을 의미한다. 데이터 복제/복구가 필요한 환경에서는 대신 custom StorageClass를 SSD 경로로 등록하고, distributed 모드를 유지하는 방법을 검토해야 한다. 이 현장에서는 단일 노드 + 백업 정책으로 충분한 상황이었다.

<br>

# 데이터 이관 삽질기

MinIO를 재배포한 뒤, 기존 데이터(`/var/lib/rancher/k3s/storage` 아래의 PVC 디렉토리)를 새 PV 경로(`/mnt/data/minio-pv`)로 이관해야 했다. 단순해 보이는 작업이었지만, 예상치 못한 문제들이 연달아 발생했다.

<br>

## 파일 복사

### 1차 시도: `cp`로 복사 → 버킷이 보이지 않음

```bash
$ sudo cp -r /var/lib/rancher/k3s/storage/pvc-84164975-..._minio_export-minio-1/ /mnt/data/minio-pv/
```

복사는 완료되었으나, MinIO 콘솔에서 **버킷이 하나도 보이지 않았다**. 파일 자체는 디스크에 존재하는데 MinIO가 인식하지 못하는 상태였다.

### 원인: MinIO 메타데이터 구조

MinIO는 버킷 데이터 외에 `.minio.sys/` 등의 **숨김 디렉토리**에 메타데이터를 저장한다. 버킷 목록, 오브젝트 메타데이터, IAM 정보 등이 이 숨김 파일들에 포함되어 있다. `cp`로 복사할 때 숨김 파일이 누락되면 MinIO는 해당 데이터를 인식하지 못한다.


### 2차 시도: `rsync`로 숨김 파일 포함 복사 → 성공

```bash
$ sudo rsync -av /var/lib/rancher/k3s/storage/pvc-84164975-..._minio_export-minio-1/ /mnt/data/minio-pv/
```

`rsync -a`(archive 모드)는 숨김 파일, 심볼릭 링크, 퍼미션 등을 보존하여 복사한다. 이 방식으로 복사한 뒤에는 MinIO 콘솔에서 버킷이 정상적으로 표시되었다.

> `cp` 자체도 `-a` 옵션을 사용하면 숨김 파일을 포함하여 복사할 수 있다. 다만 대용량 데이터 이관에서는 `rsync`가 중단 후 재개, 진행률 표시 등에서 유리하다.

<br>

## Disk Pressure로 인한 Pod 축출

데이터 이관 과정에서 루트 파티션의 잔여 용량이 임계치 이하로 떨어지자, kubelet이 **disk pressure** 상태를 감지하고 Pod를 축출(evict)하기 시작했다. MinIO뿐 아니라 같은 노드의 다른 워크로드에도 영향이 미쳤다.

```
Status:   Failed
Reason:   Evicted
Message:  The node was low on resource: ephemeral-storage.
          Threshold quantity: 12439225938, available: 34765552Ki.
```

kubelet의 eviction threshold(기본값: 노드 전체 용량의 약 15%)에 도달하면, `BestEffort` QoS 클래스의 Pod부터 축출된다. 축출된 Pod는 데이터 복사 중간에 죽어버리므로, 이관 작업을 안전하게 진행하려면 MinIO Pod를 먼저 중지(`scale down`)한 상태에서 복사해야 했다.

<br>

## PV 재배포 시 경로 변경 불가

기존 PV의 `hostPath.path`를 변경하려고 시도했으나, **PV 스펙은 생성 후 변경할 수 없다**(immutable). 경로를 바꾸려면 기존 PV/PVC를 삭제하고 새로 생성해야 한다. StatefulSet이 자동 생성한 PVC(`export-minio-*`)는 StatefulSet을 삭제해도 남아 있으므로(데이터 보존 설계), 수동으로 정리가 필요하다.

```bash
$ kubectl delete pvc export-minio-0 export-minio-1 export-minio-2 -n minio
```

<br>

# 결과

재배포 후 MinIO 콘솔에서 버킷이 정상 표시되었고, 이후 라벨링 파이프라인을 수차례 실행하면서 데이터가 SSD에 정상적으로 축적되는 것을 확인했다.

![minio-new-bucket]({{site.url}}/assets/images/minio-new-bucket.png){: .align-center}

파이프라인을 여러 차례 실행한 뒤 디스크 사용량을 확인했을 때, 데이터가 SSD 경로에 쌓이고 루트 파티션은 안정적으로 유지되고 있었다.

```bash
$ df -h
Filesystem                       Size  Used Avail Use%  Mounted on
/dev/mapper/ubuntu--vg-lv--0     232G   80G  140G  37%  /
/dev/sda                         3.6T  960G  2.5T  28%  /mnt/data
```

- 루트 파티션: 90% → **37%**로 감소 (MinIO 데이터 118GB가 빠져나간 효과)
- SSD(`/mnt/data`): 파이프라인 실행으로 약 960GB 데이터 축적, 잔여 공간 2.5TB 확보

<br>

# 에필로그: PR #21689과 레포 archive

이 문제를 겪으면서, `distributed` 모드에서 `existingClaim`이 조용히 무시되는 것이 다른 사용자들에게도 혼란을 줄 수 있겠다는 생각이 들었다. 그래서 MinIO 공식 레포에 [PR #21689](https://github.com/minio/minio/pull/21689)를 올렸다.

## PR 내용

- **NOTES.txt**: `distributed` 모드 + `existingClaim` 설정 시 경고 메시지 출력
- **values.yaml**: `existingClaim`의 제한사항을 명시하는 주석 보강
- 대안 제시: standalone 전환 또는 custom StorageClass 사용

```
WARNING: persistence.existingClaim is set but will be ignored in distributed mode.

In distributed mode, MinIO automatically creates multiple PersistentVolumeClaims
using StatefulSet's volumeClaimTemplates for erasure coding.
Your specified PVC 'my-custom-pvc' will not be used.
```

## 결과

PR을 올린 것은 2025년 11월이었다. 리뷰나 코멘트 없이 open 상태로 남아 있었고, 2026년 2월 13일 **레포 자체가 archive** 되면서 PR은 영구히 열린 상태로 남게 되었다.

MinIO 레포 archive는 갑작스러운 것이 아니라, 수 년에 걸친 변화의 끝이었다.

| 시점 | 사건 |
| --- | --- |
| 2021년 | Apache 2.0 → **GNU AGPLv3** 라이선스 변경 |
| 2022~2023년 | Nutanix, Weka 등 라이선스 위반 소송 |
| 2025년 5월 | 커뮤니티 에디션에서 **Admin Console 제거** |
| 2025년 10월 | 보안 취약점 공개 시점에 바이너리/Docker 배포 중단 |
| 2025년 12월 | **유지보수 모드** 선언 |
| 2026년 2월 | 레포 **archive** (read-only 전환) |

MinIO는 사실상 오픈소스 프로젝트로서의 생명을 마감하고, 상용 제품(**AIStor**)으로 완전히 전환했다. AGPLv3 라이선스 덕분에 커뮤니티 포크([Pigsty](https://github.com/pgsty/minio) 등)가 가능하긴 하지만, 공식 Helm chart가 더 이상 관리되지 않는다는 점은 운영 환경에서 MinIO를 사용하는 모든 팀이 인지해야 할 사안이다.

돌이켜 보면, 이 PR은 머지되지 못했지만, 문제를 분석하고 해결 방안을 정리하는 과정 자체가 StatefulSet의 스토리지 동작, Helm 템플릿의 조건부 렌더링, K3s의 StorageClass 구조를 깊이 이해하는 계기가 되었다.

<br>

# 정리 및 후속 과제

## 이 글에서 다룬 것

- `distributed` 모드에서 `existingClaim`이 무시되는 원인과 해결
- SSD 증설 후 `standalone` 모드로 전환하여 루트 파티션 과부하 해소
- 데이터 이관 시 주의사항 (숨김 파일, disk pressure, PV immutability)

## 관련 글

- [리눅스 스토리지 기초 - 1. 블록 디바이스, 파티션, 파일 시스템]({% post_url 2026-02-24-CS-Linux-Storage-01 %}): 이 글에서 SSD 마운트 과정을 요약만 했는데, 블록 디바이스부터 파티션, 파일 시스템, 마운트까지의 전체 개념을 다룬다

## 후속 글 예정

- **Kubernetes - StatefulSet 스토리지 딥다이브**: `volumeClaimTemplates` 동작 원리, PVC 라이프사이클, Helm 템플릿 조건부 렌더링, StorageClass와 동적 프로비저닝
