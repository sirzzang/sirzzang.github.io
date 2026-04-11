---
title:  "[Kubernetes] Pod 볼륨 - 7. PV 관리와 Ephemeral PersistentVolume"
excerpt: "PVC 리사이징, 볼륨 스냅샷/복원, 그리고 Pod 수명 주기에 종속되는 Ephemeral PersistentVolume을 알아보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubernetes-in-Action-2nd
  - volume
  - PersistentVolume
  - resize
  - VolumeSnapshot
  - ephemeral-volume
  - volumeClaimTemplate
---

*[Kubernetes in Action 2nd Edition](https://www.manning.com/books/kubernetes-in-action-second-edition) 10장의 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- PVC 용량은 **늘리기만** 가능하다. StorageClass의 `allowVolumeExpansion: true`와 프로비저너의 resize 지원이 필요하며, 실제 파일시스템 리사이즈는 **Pod 재생성 시** 수행된다
- **VolumeSnapshot**으로 PV의 특정 시점 백업을 생성하고, `dataSourceRef`로 새 PVC를 복원할 수 있다. CSI 드라이버의 스냅샷 기능 지원이 필요하다
- **Ephemeral PersistentVolume**은 Pod 생성 시 PVC가 자동 생성되고, Pod 삭제 시 PVC도 함께 삭제된다. 일반 PV의 모든 기능(스냅샷, 리사이즈 등)을 사용하면서도 수명 주기만 Pod에 종속된다

<br>

# 시리즈 안내

이 글은 Pod 볼륨 시리즈의 7편이다.

1. [볼륨 소개]({% post_url 2026-04-05-Kubernetes-Pod-Volume-01-Introduction %})
2. [emptyDir]({% post_url 2026-04-05-Kubernetes-Pod-Volume-02-emptyDir %})
3. [image 볼륨과 hostPath]({% post_url 2026-04-05-Kubernetes-Pod-Volume-03-Image-Volume-HostPath %})
4. [configMap, secret, downwardAPI, projected 볼륨]({% post_url 2026-04-05-Kubernetes-Pod-Volume-04-ConfigMap-Secret-DownwardAPI-Projected %})
5. [PersistentVolume, PersistentVolumeClaim, StorageClass]({% post_url 2026-04-05-Kubernetes-Pod-Volume-05-PV-PVC-StorageClass %})
6. [정적 프로비저닝과 노드 로컬 PersistentVolume]({% post_url 2026-04-05-Kubernetes-Pod-Volume-06-Static-Provisioning %})
7. PV 관리와 Ephemeral PersistentVolume (이 글)

<br>

# PVC 리사이징

[이전 글들]({% post_url 2026-04-05-Kubernetes-Pod-Volume-05-PV-PVC-StorageClass %})에서 PV의 생성, 사용, 삭제 라이프사이클을 다뤘다. 이 섹션에서는 운영 중인 PV의 관리를 다룬다.

## 전제 조건

PVC의 용량을 변경하려면 세 가지 조건이 필요하다.

| 조건 | 설명 |
| --- | --- |
| **동적 프로비저닝된 PVC** | 정적 프로비저닝된 PVC는 리사이즈 불가 |
| **StorageClass의 `allowVolumeExpansion`** | `true`로 설정되어 있어야 함 (`kubectl get sc`로 확인) |
| **프로비저너의 resize 구현** | CSI 드라이버가 볼륨 확장을 실제로 구현해야 함 |

크기는 **늘리기만 가능**하고 줄일 수는 없다.

```bash
kubectl get sc
# NAME                 PROVISIONER             ALLOWVOLUMEEXPANSION
# standard (default)   rancher.io/local-path   false
```

Kind 클러스터의 `rancher.io/local-path`는 `allowVolumeExpansion`이 `false`이고, 프로비저너 자체도 resize를 구현하지 않으므로 리사이즈가 불가능하다. 클라우드 환경(GKE, EKS, AKS)에서 정상 동작한다.

## 리사이즈 절차

기존 PVC의 `resources.requests.storage`를 수정하면 된다.

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: quiz-data
spec:
  resources:
    requests:
      storage: 10Gi       # 1Gi → 10Gi로 변경
  accessModes:
  - ReadWriteOncePod
```

```bash
kubectl apply -f pvc.quiz-data.yaml
```

apply 후에도 `kubectl get pvc`의 CAPACITY는 바로 바뀌지 않는다. CAPACITY 열은 PVC의 요청값이 아니라 **실제 바인딩된 PV의 크기**를 보여주기 때문이다.

`kubectl describe pvc`로 확인하면 `FileSystemResizePending` Condition이 표시된다.

```
Conditions:
  Type                      Status    Message
  ----                      ------    -------
  FileSystemResizePending   True      Waiting for user to (re-)start a pod
                                      to finish file system resize of volume on node.
```

**파일시스템 리사이즈는 Pod가 볼륨을 마운트하는 시점에 수행된다.** 따라서 해당 PVC를 사용하는 Pod를 삭제하고 다시 생성해야 리사이즈가 완료된다.

```bash
kubectl delete po quiz
kubectl apply -f pod.quiz.yaml

# 리사이즈 완료 확인
kubectl get pvc quiz-data
# NAME        STATUS   VOLUME        CAPACITY   ACCESS MODES
# quiz-data   Bound    pvc-ed36b...  10Gi       RWOP
```

PVC의 `spec`은 대부분 불변(immutable)이다. 바인딩된 PVC에서 수정할 수 있는 필드는 `resources.requests`(용량)와 `volumeAttributesClassName`뿐이다. StorageClass를 바꾸고 싶다면 새 PVC를 만들어야 한다.

<br>

# 볼륨 스냅샷과 복원

Kubernetes는 PV의 **특정 시점 스냅샷**을 생성하고, 스냅샷으로부터 새 PV를 복원하는 것을 지원한다. 기반 CSI 드라이버가 스냅샷 기능(`CREATE_DELETE_SNAPSHOT`)을 지원해야 한다.

Kind의 `local-path-provisioner`는 CSI 드라이버가 아니므로 스냅샷을 지원하지 않는다. GKE, EKS 같은 클라우드 환경이나, CSI Hostpath Driver, Longhorn 등을 설치한 환경에서 실습할 수 있다.

## VolumeSnapshotClass

스냅샷을 생성하려면 먼저 `VolumeSnapshotClass`를 만든다. [StorageClass]({% post_url 2026-04-05-Kubernetes-Pod-Volume-05-PV-PVC-StorageClass %})와 유사한 개념으로, CSI 드라이버와 삭제 정책을 지정한다.

```yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshotClass
metadata:
  name: pd-csi
driver: pd.csi.storage.gke.io
deletionPolicy: Delete
```

| 필드 | 설명 |
| --- | --- |
| `driver` | 스냅샷 생성에 사용할 CSI 드라이버 |
| `deletionPolicy` | `Delete`이면 VolumeSnapshot 삭제 시 VolumeSnapshotContent도 함께 삭제 |

## VolumeSnapshot 생성

실제 스냅샷을 요청하려면 `VolumeSnapshot` 오브젝트를 생성한다.

```yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: quiz-data-1
spec:
  volumeSnapshotClassName: pd-csi
  source:
    persistentVolumeClaimName: quiz-data
```

VolumeSnapshot이 생성되면 시스템이 자동으로 `VolumeSnapshotContent`을 만든다. 이 관계는 PVC와 PV의 관계와 정확히 동일하다.

| 요청 오브젝트 (네임스페이스 범위) | 실제 리소스 (클러스터 범위) |
| --- | --- |
| PersistentVolumeClaim (PVC) | PersistentVolume (PV) |
| VolumeSnapshot | VolumeSnapshotContent |

```bash
# 스냅샷 상태 확인
kubectl get vs   # volumesnapshot 축약형
# NAME          READYTOUSE   SOURCEPVC   RESTORESIZE   AGE
# quiz-data-1   true         quiz-data   10Gi          66s
```

## 스냅샷에서 PV 복원

스냅샷으로부터 새 PVC를 복원하려면 `dataSourceRef`에 VolumeSnapshot을 지정한다.

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: quiz-data-from-snapshot
spec:
  resources:
    requests:
      storage: 10Gi
  accessModes:
  - ReadWriteOncePod
  dataSourceRef:
    apiGroup: snapshot.storage.k8s.io
    kind: VolumeSnapshot
    name: quiz-data-1
```

`dataSourceRef`에서 VolumeSnapshot을 참조할 때는 `apiGroup: snapshot.storage.k8s.io`를 **반드시 명시**해야 한다. PVC를 참조할 때는 core 그룹이므로 생략 가능하지만, VolumeSnapshot은 다른 API 그룹에 속하기 때문이다.

| 소스 종류 | `apiGroup` | 예시 |
| --- | --- | --- |
| PersistentVolumeClaim (복제) | 생략 가능 | `kind: PersistentVolumeClaim` |
| VolumeSnapshot (복원) | **필수** | `apiGroup: snapshot.storage.k8s.io` + `kind: VolumeSnapshot` |

StorageClass의 `volumeBindingMode`가 `WaitForFirstConsumer`인 경우, 이 PVC를 사용하는 **Pod를 생성해야** 복원 프로세스가 시작된다.

<br>

# Ephemeral PersistentVolume

지금까지 다룬 PV는 Pod와 독립적인 수명 주기를 가진다. 하지만 때로는 PV의 기능(용량 보장, 네트워크 스토리지, 스냅샷 등)은 필요하되, **Pod 종료 시 자동으로 정리**되길 원하는 경우가 있다. 이때 `ephemeral` 볼륨 타입을 사용한다.

## ephemeral 볼륨 타입

`ephemeral` 볼륨은 Pod 매니페스트 안에 PVC 템플릿(`volumeClaimTemplate`)을 내장한다. Pod 생성 시 이 템플릿으로 PVC가 자동 생성되고, Pod 삭제 시 PVC도 함께 삭제된다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: demo-ephemeral
spec:
  volumes:
  - name: my-volume
    ephemeral:
      volumeClaimTemplate:
        spec:
          accessModes:
          - ReadWriteOnce
          resources:
            requests:
              storage: 1Gi
  containers:
  - name: main
    image: busybox
    command:
    - sh
    - -c
    - |
      touch /mnt/ephemeral/file-created-by-$HOSTNAME.txt ;
      sleep infinity
    volumeMounts:
    - mountPath: /mnt/ephemeral
      name: my-volume
  terminationGracePeriodSeconds: 0
```

## volumeClaimTemplate

Pod가 생성되면 ephemeral volume controller가 PVC를 자동 생성한다. PVC 이름은 **`{Pod 이름}-{볼륨 이름}`** 형식이다.

```bash
kubectl apply -f pod.demo-ephemeral.yaml

# 자동 생성된 PVC 확인
kubectl get pvc | grep ephemeral
# demo-ephemeral-my-volume   Bound    pvc-16f7b...   1Gi   RWO   standard

# PV도 자동 생성됨 (Reclaim Policy: Delete)
kubectl get pv pvc-16f7b075-063a-48c1-9b37-b7a3194a33f2
# NAME          CAPACITY   RECLAIM POLICY   STATUS   CLAIM
# pvc-16f7b...  1Gi        Delete           Bound    default/demo-ephemeral-my-volume
```

Pod 내부에서 볼륨을 정상적으로 사용할 수 있다.

```bash
kubectl exec demo-ephemeral -- ls /mnt/ephemeral
# file-created-by-demo-ephemeral.txt
```

## Pod 삭제 시 자동 정리

Ephemeral PVC의 수명 주기는 Pod에 종속되어 있다. Pod를 삭제하면 PVC → PV → 기반 스토리지까지 연쇄 삭제된다.

```bash
kubectl delete po demo-ephemeral

# PVC, PV 모두 자동 삭제됨
kubectl get pvc | grep ephemeral
# (결과 없음)
```

## emptyDir vs ephemeral vs 일반 PVC 비교

|  | 일반 PVC + PV | Ephemeral PVC + PV | emptyDir |
| --- | --- | --- | --- |
| **PVC 생성 주체** | 사용자가 직접 | Pod 생성 시 **자동** | PVC 없음 |
| **PV 프로비저닝** | 동적 또는 정적 | 동적 | PV 없음 (노드 로컬) |
| **실제 스토리지** | 네트워크/클라우드 블록 등 | 네트워크/클라우드 블록 등 | 노드 메모리 또는 디스크 |
| **수명 주기** | Pod과 **독립적** | Pod에 **종속** | Pod에 **종속** |
| **데이터 지속성** | Pod 삭제 후에도 유지 | Pod 삭제 시 소멸 | Pod 삭제 시 소멸 |
| **용량 보장** | StorageClass에 따라 다양 | StorageClass에 따라 다양 | 노드 자원에 제한 |
| **스냅샷/리사이즈** | 가능 | 가능 | 불가 |
| **사용 사례** | DB 데이터, 장기 보관 | 고성능 임시 작업 공간 | 컨테이너 간 파일 공유, 캐시 |

Ephemeral PV의 핵심은 **일반 PV와 완전히 동일한 기능**을 가지면서 수명 주기만 Pod에 묶여 있다는 것이다. `emptyDir`로는 부족하지만(용량 보장, 성능, IOPS 등) Pod보다 오래 살 필요는 없는 임시 스토리지가 필요할 때 사용한다. 예를 들어, ML 학습 중간 체크포인트를 고성능 SSD에 저장하되 학습 Pod이 끝나면 자동 정리되길 원하는 경우다.

<br>

# 정리

- **PVC 리사이징**: 동적 프로비저닝 + `allowVolumeExpansion: true` + 프로비저너 지원이 필요하다. 크기는 늘리기만 가능하고, 파일시스템 리사이즈는 Pod 재생성 시 완료된다
- **VolumeSnapshot**: CSI 드라이버가 스냅샷을 지원하면 PV의 특정 시점 백업을 생성할 수 있다. VolumeSnapshot과 VolumeSnapshotContent는 PVC와 PV의 관계와 동일하다
- **스냅샷 복원**: `dataSourceRef`에 VolumeSnapshot을 지정하여 새 PVC를 생성한다. VolumeSnapshot은 `apiGroup: snapshot.storage.k8s.io`를 반드시 명시해야 한다
- **Ephemeral PV**: `ephemeral` 볼륨 타입으로 Pod 매니페스트에 PVC 템플릿을 내장한다. Pod 생성 시 PVC가 자동 생성되고, Pod 삭제 시 PVC와 PV까지 연쇄 삭제된다
- Ephemeral PV는 일반 PV의 모든 기능을 가지면서 수명 주기만 Pod에 종속된다. `emptyDir`보다 강력하지만 Pod와 함께 사라지는 임시 스토리지가 필요할 때 사용한다

<br>
