---
title:  "[Kubernetes] MinIO Custom PV 연결"
excerpt: Helm으로 배포한 MinIO에서 SSD 마운트를 이용해 PV를 구성하는 방법과 주의사항
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - k8s
  - k3s
  - kubernetes
  - MinIO
  - helm
---



<br>

# 문제

- 시스템이 배포된 현장 중 한 곳에서 K3s 클러스터 내 워크플로우 실행이 중지되는 현상 발생
  > 보통 이런 경우, 경험적으로 CPU 사용량, 디스크 사용량을 먼저 확인해야 함

- **루트 파티션 용량 부족** 확인
  ![minio-root-partition-storage]({{site.url}}/assets/images/minio-root-partition-storage.png)

- 시스템 내 오브젝트 스토리지로 MinIO 사용 중
  - helm을 이용해 배포
  - 추출한 프레임, 각 프레임 별 annotation json을 저장하는 용도로 사용

- MinIO가 루트 파티션 내 디렉토리들을 PV로 사용함에 따라 **루트 파티션 과부하** 발생
  
  ![k3s-storage-pv]({{site.url}}/assets/images/k3s-storage-pv.png)
  
  > *참고*: 왜 이 디렉토리를 PV로 사용했는가
  >
  > - [후술할 항목에서와 같이](https://sirzzang.github.io/dev/Dev-Minio-Existing-PVC/#minio-valuesyaml-%EB%B3%80%EA%B2%BD) values.yaml의 `mode` 항목 값을 `distributed`로 주고 배포했기 때문
  > - MinIO가 statefulset으로 배포되어 있었는데, 배포에 사용한 helm chart 버전에서 values.yaml의 `mode` 항목 기본값이 `distributed`였음
  
- 목표: **SSD를 추가하고 해당 경로를 MinIO PV로 연결하여 루트 파티션 부담 해소**

<br>

 

# 해결

다음과 같은 해결 전략을 이용해 위의 문제 상황을 해결하고자 함

1. SSD 설치 및 `/mnt/data` 마운트
2. PV 디렉토리 생성 및 권한 설정
3. MinIO 재배포
   - PV/PVC 매니페스트 작성 후 적용
   - MinIO values.yaml 수정 후 재배포

<br>

## 디스크 증설 후 마운트



### SSD 설치



![ssd]({{site.url}}/assets/images/ssd.jpg)
<center><sup>설치할 녀석들</sup></center>

![ssd-installation]({{site.url}}/assets/images/ssd-installation.jpg)
<center><sup>SATA 포트를 통해 장착</sup></center>

<br>

### SSD 인식 확인

서버에 SSD를 물리적으로 장착한 뒤, 리눅스에서 디스크 인식 여부 확인

```bash
sudo fdisk -l
```
```bash
Disk /dev/sda: 1.82 TiB, 2000398034016 bytes, 3907029168 sectors
Disk model: Samsung SSD 870
Units: sectors of 1 * 512 = 512 bytes
...
Disk /dev/sdb: 931.51 GiB, 1000204886016 bytes, 1953525168 sectors
Disk model: Samsung SSD 870
Units: sectors of 1 * 512 = 512 bytes
```

- 새로 장착한 SSD가 /dev/sda, /dev/sdb 등으로 표시되는지 확인
- 만약 인식되지 않으면 케이블 연결, SATA 포트 등을 점검해야 함



<br>



### 파티션 생성 및 포맷

fdisk를 이용해 새 SSD에 파티션을 생성하고, ext4 파일 시스템으로 포맷해야 함

```bash
sudo fdisk /dev/sda
```
- `n` → `p` → `Enter` → `Enter` → `w` 순서로 파티션 생성 후 저장

<br>

```
sudo mkfs.ext4 /dev/sda
```
```bash
mke2fs 1.47.0 (5-Feb-2023)
Discarding device blocks: done
Creating filesystem with 488278646 4k blocks and 122101760 inodes
Filesystem UUID: <uuid> # uuid 확인
Superblock backups stored on blocks:
				....
```

- 출력 중에 block device ID가 `UUID=<uuid>` 줄을 통해 표시되므로, 나중에 fstab에 등록하기 위해 복사해 둠


<br>

### 마운트 경로 생성

SSD를 마운트할 디렉토리를 생성해야 함

```bash
sudo mkdir -p /mnt/data
sudo mkdir -p /mnt/sdb
sudo mkdir -p /mnt/sdc
```
- `/mnt/data`를 주 마운트 경로로 사용할 예정

<br>

### fstab 등록 (자동 마운트 설정)

/etc/fstab 파일을 수정하여 부팅 시 자동으로 마운트되도록 설정함

```
sudo blkid
```
```
/dev/sda: UUID="abcd-1234" TYPE="ext4"
/dev/sdb: UUID="efgh-5678" TYPE="ext4"
```
- UUID 확인
- [디스크 파티션 포맷](https://sirzzang.github.io/dev/Dev-Minio-Existing-PVC/#%ED%8C%8C%ED%8B%B0%EC%85%98-%EC%83%9D%EC%84%B1-%EB%B0%8F-%ED%8F%AC%EB%A7%B7) 시 생성되는 UUID와 동일


> 참고: `blkid`를 통한 UUID 확인
>
> ```bash
> $ sudo blkid
> ...
> /dev/sda: UUID="<uuid>" BLOCK_SIZE="4096" TYPE="ext4"
> /dev/sdb: UUID="<uuid>" BLOCK_SIZE="4096" TYPE="ext4"
> ...
> ```
> - SSD는 블록 단위로 데이터를 읽고 쓰는 장치(block device)
> - 새 디스크 장착 후 포맷 시, block device ID가 생성됨
> - `blkid`: block device의 정보를 보여 주는 리눅스 명령어
> - `blkid`를 통해 각 디스크/파티션의 정보(장치 이름, 파일 시스템 타입, UUID 등) 확인 가능 


<br>

```
sudo vi /etc/fstab
```
```
UUID=abcd-1234  /mnt/data  ext4  defaults  0  0
UUID=efgh-5678  /mnt/sdb   ext4  defaults  0  0
```

- 위와 같이 fstab 설정 추가
- fstab 설정 추가 후 파일 예시

  ```bash
  # /etc/fstab: static file system information.
  #
  # Use 'blkid' to print the universally unique identifier for a
  # device: this may be used with UUID= as a more robust way to name devices
  # that works even if disks are added and removed. See fstab(5).
  #
  # <file system> <mount point>		<type>	<options>				<dump>	<pass>
  # / was on /dev/sda3 during curtin installation
  UUID=<uuid> /mnt/data                      ext4     defaults        0 0 # 추가
  UUID=<uuid> /mnt/sdb											 ext4			defaults				0 0 # 추가
  ...
  ```

<br>

### 마운트 적용

fstab 변경 후 시스템에 적용

```bash
sudo mount -a
sudo systemctl daemon-reload
```

- mount 시 systemd가 설정 파일을 읽도록 daemon-reload 명령어를 실행하라는 안내 확인 가능

  ```bash
  sudo mount -a
  mount: (hint) your fstab has been modified, but systemd still uses
  			 the old version; use 'systemctl daemon-reload' to reload.
  ```

<br>

```
df -h
```
```
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda        1.8T   28K  1.7T   1% /mnt/data
/dev/sdb        1.8T   28K  1.7T   1% /mnt/sdb
```

- 마운트 상태 확인

<br>



> 참고: `systemctl daemon-reload`
>
> 리눅스 시스템에서 `systemd` 프로세스로 하여금 설정 파일을 다시 읽도록 강제로 갱신
>
> - 대부분의 리눅스 시스템에서는 `systemd`라는 init 시스템 사용
> - 부팅 과정에서 `/etc/fstab` 파일을 읽고, 안에 정의된 파일 시스템을 mount unit으로 변환해 관리함
>   - 예를 들어, `UUID=abcd-1234 /mnt/data ext4 defaults 0 0`와 같은 줄을 읽고, `mnt-data.mount`와 같은 내부 유닛으로 등록함
>   - 즉, `systemd`가 fstab 파일을 읽고 “이 장치를 이렇게 마운트하라”고 기억하고 있는 것
> - fstab 수정 시, `systemd`는 메모리에 예전 내용을 가지고 있기 때문에, 갱신 내용이 반영되지 않음
> - 따라서 fstab 파일에 새 UUID를 추가하는 등의 수정이 발생했을 때, 해당 내용을 다시 읽도록 명령해야 함
>   - fstab 고친 직후, mount 관련 경고가 뜰 때는 꼭 실행해 주어야 함

<br>

### (주의) SSD 제거 시 부팅 문제

- 나중에 SSD를 제거하면, /etc/fstab에 등록된 UUID가 존재하지 않아 부팅이 멈출 수 있음
- 이 경우 **fstab에서 해당 항목을 주석 처리하거나 삭제**해야 함

<br>



## PV 디렉토리 생성 및 권한 설정

MinIO PV로 사용할 디렉토리를 SSD 마운트 경로 아래에 생성

```
cd /mnt/data
sudo mkdir minio-pv
sudo chmod 777 minio-pv
```

- 권한을 777로 설정하지 않으면 MinIO Pod가 디렉토리에 접근하지 못할 수 있음
  > 실제 권한 설정 없이 이하 과정을 진행할 경우, MinIO 배포 시  아래와 같은 에러 발생
  >
  > `ERROR Unable to use the driver /export: driver access denied`


<br>



## MinIO 재배포

### PV, PVC 
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
            - key: kubernetes.io/hostname # SSD 증설 후 PV 생성한 호스트
              operator: In
              values:
                - # 호스트명
  hostPath:
    path: "/mnt/data/minio-pv" # SSD 마운트 경로 내 PV 디렉토리
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

- 매니페스트 작성
  - PV `nodeSelector`: SSD 설치한 노드로 선택해야 함

<br>

```shell
kubectl apply minio-pv-pvc.yaml
```

- PV, PVC 배포

 

<br>

### MinIO values.yaml 변경

```yaml
# 생략
persistence:
  enabled: true
  existingClaim: "minio-pvc"
# 생략
mode: standalone 
# 생략
```

Helm을 이용해 MinIO를 배포할 경우 사용되는 values.yaml에서 `persistence` 항목 변경 후 재배포

- `distributed` 모드로 배포하면 ~~`Helm이 자동으로 PVC를 생성하고 `/` 하위 디렉토리를 PV로 사용~~ ([다른 글]()에서 더 자세히 알아볼 예정이나, 이 표현은 엄밀히는 맞지 않는 표현이었고) 반드시 동적 프로비저닝을 통해 여러 개의 PVC를 자동 생성해야 함
  - [distributed 모드에서는 statefulset으로 배포됨](https://github.com/minio/minio/blob/master/helm/minio/templates/statefulset.yaml#L1)
  - [`persistence.existingClaim`에 PVC를 지정하더라도 무시됨](https://github.com/minio/minio/blob/master/helm/minio/templates/statefulset.yaml#L251)
    - `export`라는 이름으로 PersistentVolumeClaim을 자동으로 생성
    - 해당 PVC는 K3s default stoage class를 이용해 PV를 제공함
      - ([다른 글]()에서 더 자세히 알아보겠으나) default storage class 경로를 마운트한 SSD 경로로 잡아 주거나, 해당 SSD를 storage class로 등록했더라면 distributed 모드에서도 사용 가능했을 수 있음
    - K3s default storage class의 경우  `/` 파티션에 있는 `/var/lib/rancher/k3s` 하위 디렉토리를 PV로 이용하게 됨
- ~~`standalone` 모드에서만 기존 PVC를 사용 가능~~ ([다른 글]()에서 더 자세히 알아볼 예정이나 이건 틀린 표현이었고) `standalone` 모드에서는 `existingClaim`을 통해 기존 PVC를 사용해야 함
  - [standalone 모드에서는 **단일 파드**로 구성된 deployment로 배포됨](https://github.com/minio/minio/blob/master/helm/minio/templates/deployment.yaml#L1)
  - [`persistence.existingClaim`에 PVC 지정 시 명시된 PVC를 사용하고, 그렇지 않은 경우 default로 `minio.fullname` 이름의 PVC를 참조함](https://github.com/minio/minio/blob/master/helm/minio/templates/deployment.yaml#L197)
    - 어떤 경우든, 해당 PVC가 미리 설정되어 있어야 함
    - 즉, `standalone` 모드를 사용하면 `existingClaim`을 파싱하여 사용하게 되는데, 이 때 `existingClaim`에 해당하는 PVC는 PV 바인딩 전이더라도 생성되어 있어야 함([주석](https://github.com/minio/minio/blob/RELEASE.2024-04-18T19-09-19Z/helm/minio/values.yaml#L150)에도 이 내용이 명시되어 있음)
- 결과적으로, values.yaml의 mode 값이 `distributed`인 경우, **persistence.existingClaim** 값을 주고 배포하더라도, `/` 파티션 하위에 k3s default storage class에 의해 `export-0`, `export-1` 등의 이름으로 생성되는 디렉토리를 PV로 이용하게 됨
  - PV 디렉토리가 위치하는 노드가 원하는 노드인지 역시 보장되지 않음
  - values.yaml의 기본값이 `distributed`이므로, 해당 값을 바꾸지 않은 상태에서는 `persistence.existingClaim` 값을 아무리 지정하더라도 무시됨



<br>

### 재배포

```shell
helm uninstall minio -n minio
helm install minio -n minio ./minio.5.2.0.tgz --values minio-values.yaml
```

<br>







# 결론

> **해결 방안 요약**
>
> - SSD 설치 → 파티션 포맷 → UUID 확인 → fstab 등록 → 마운트
> - PV 디렉토리 생성 → 권한 설정
> - PV/PVC 작성 → MinIO values.yaml 수정 → 재배포
> - systemd 특성(`daemon-reload`)과 fstab 주의사항 숙지 필요



## 결과

이후 MinIO 버킷 생성 시, `/mnt/data` 디렉토리 하위에 폴더가 생성되는 것을 확인할 수 있음

![minio-new-bucket]({{site.url}}/assets/images/minio-new-bucket.png)

<br>



## 추가 고려 사항

- 루트 파티션 부담이 실제로 해소되는지 지속적으로 모니터링
- 기존 데이터 이관
  - `/mnt/data/minio` → `/mnt/data/minio-pv`
  - 이관 시, 권한 문제 발생 가능 → `chown`/`chmod` 필요
  - 이관 후, 기존에 수집한 데이터까지 활용한 운영 방한 검토 필요
- 추후 MinIO PVC 확장 또는 다른 노드에 SSD 추가 시 PV/PVC 전략 재검토 및 고도화 필요

