---
title:  "[Kubernetes] Kubernetes 환경에서 GPU Time Slicing 사용하기 - 3. 적용"
excerpt: NVIDIA GPU에 GPU Time Slicing을 실제로 적용해보자.
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - k8s
  - k3s
  - kubernetes
  - gpu
  - time slicing
---



<br>

[지난 글](https://sirzzang.github.io/dev/Dev-Kubernetes-GPU-Time-Slicing-2/)에서 쿠버네티스 환경에서 GPU Time Slicing이 어떻게 동작하는지, 그리고 Time Slicing ConfigMap을 어떻게 구성하는지 알아보았다. 이번 글에서는 실제로 Time Slicing을 적용하는 방법과 적용 사례, 그리고 사용 시 주의해야 할 한계점들을 살펴본다.

<br>



# 적용 방법

NVIDIA GPU에 Time Slicing을 적용하는 방법은 GPU Operator 배포 여부에 따라 달라진다.

<br>

## GPU Operator 이용

GPU Operator가 배포되어 있다면, Time Slicing 설정을 담은 ConfigMap을 생성하고, ClusterPolicy를 변경해 주면 된다.

> 참고: [NVIDIA GPU Operator 공식 문서](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/gpu-sharing.html#about-configuring-gpu-time-slicing)

<br>

### 1. ConfigMap 생성

NVIDIA Device Plugin에 적용될 ConfigMap을 GPU Operator 네임스페이스에 생성한다.

```yaml
# time-slicing-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: time-slicing-config
data:
  any: |-
    version: v1
    flags:
      migStrategy: none
    sharing:
      timeSlicing:
        renameByDefault: false
        failRequestsGreaterThanOne: false
        resources:
          - name: nvidia.com/gpu
            replicas: 4
```

```bash
kubectl create -n gpu-operator -f time-slicing-config.yaml
```

<br>

### 2. ClusterPolicy 변경

ConfigMap을 ClusterPolicy에 연결한다. Device Plugin이 해당 ConfigMap을 읽을 수 있도록 설정하는 것이다.

**클러스터 전체에 적용하는 경우:**

```bash
kubectl patch clusterpolicies.nvidia.com/cluster-policy \
    -n gpu-operator --type merge \
    -p '{"spec": {"devicePlugin": {"config": {"name": "time-slicing-config", "default": "any"}}}}'
```

* `name`: ConfigMap 이름
* `default`: ConfigMap의 `data.<key>` 중 기본으로 적용할 키

**노드별로 다르게 적용하는 경우:**

```bash
kubectl patch clusterpolicies.nvidia.com/cluster-policy \
    -n gpu-operator --type merge \
    -p '{"spec": {"devicePlugin": {"config": {"name": "time-slicing-config-fine"}}}}'
```

`default` 필드를 지정하지 않으면, 모든 노드에 자동으로 적용되지 않는다. 이 경우, 노드에 라벨을 붙여서 특정 설정을 적용해야 한다.

<br>

### 3. (선택) 노드 라벨 적용

노드별로 다른 설정을 적용하려면, 해당 노드에 ConfigMap의 `data.<key>`를 라벨로 붙여 주면 된다.

```bash
kubectl label node <node-name> nvidia.com/device-plugin.config=<config.data.key>
```

예를 들어, Tesla-T4 GPU가 있는 노드에 `tesla-t4` 설정을 적용하려면:

```bash
kubectl label node <node-name> nvidia.com/device-plugin.config=tesla-t4
```

여러 노드에 한 번에 적용하려면 셀렉터를 사용한다:

```bash
kubectl label node \
    --selector=nvidia.com/gpu.product=Tesla-T4 \
    nvidia.com/device-plugin.config=tesla-t4
```

<br>

### 적용 흐름

ClusterPolicy가 업데이트되면, 다음과 같은 흐름으로 Time Slicing이 적용된다.

```text
ConfigMap 생성
    ↓
ClusterPolicy 업데이트
    ↓
GPU Operator가 device-plugin DaemonSet 재시작
    ↓
각 노드의 Device Plugin이 물리 GPU × replicas 개수로 보고
    ↓
Kubernetes는 논리적으로 더 많은 GPU가 있다고 인식
    ↓
여러 Pod가 같은 물리 GPU의 /dev/nvidia0 접근
    ↓
NVIDIA Driver가 커널 수준에서 Time Slicing 수행
```

<br>

## GPU Operator 없이 설정

GPU Operator 없이 직접 NVIDIA Device Plugin을 배포한 경우, ConfigMap을 생성하고 DaemonSet에서 마운트하면 된다.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: nvidia-device-plugin-config
  namespace: kube-system
data:
  config.yaml: |
    version: v1
    sharing:
      timeSlicing:
        replicas: 4
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: nvidia-device-plugin-daemonset
  namespace: kube-system
spec:
  selector:
    matchLabels:
      name: nvidia-device-plugin-ds
  template:
    spec:
      containers:
      - name: nvidia-device-plugin-ctr
        image: nvcr.io/nvidia/k8s-device-plugin:v0.14.0
        volumeMounts:
        - name: device-plugin-config
          mountPath: /etc/kubernetes/device-plugins/config
      volumes:
      - name: device-plugin-config
        configMap:
          name: nvidia-device-plugin-config
```

<br>

## GPU Operator 배포 전에 미리 설정

GPU Operator를 배포하기 전에 미리 Time Slicing ConfigMap을 만들어 두고, Helm Chart 배포 시 옵션으로 지정할 수도 있다.

```bash
# 네임스페이스 및 ConfigMap 생성
kubectl create namespace gpu-operator
kubectl create -f time-slicing-config.yaml -n gpu-operator

# Helm 차트 배포
helm install gpu-operator nvidia/gpu-operator \
    -n gpu-operator \
    --version=v25.10.0 \
    --set devicePlugin.config.name=time-slicing-config
```


<br>

# 적용 사례

RTX 4090 GPU 10개가 장착된 노드에 Time Slicing을 적용한 사례를 소개한다.

<br>

## 전제 조건

GPU Operator가 배포되어 있다.

```bash
$ kubectl get deployments -n gpu-operator
NAME                                         READY   UP-TO-DATE   AVAILABLE   AGE
gpu-operator                                 1/1     1            1           19d
gpu-operator-node-feature-discovery-gc       1/1     1            1           19d
gpu-operator-node-feature-discovery-master   1/1     1            1           19d

$ kubectl get daemonsets -n gpu-operator
NAME                                         DESIRED   CURRENT   READY   ...
gpu-feature-discovery                        8         8         8       ...
nvidia-device-plugin-daemonset               8         8         8       ...
nvidia-operator-validator                    8         8         8       ...
```

<br>

## ConfigMap 생성

GPU product 이름을 확인한 후, ConfigMap을 생성한다. 노드의 GPU product 레이블을 확인하면 된다.

```bash
$ kubectl get node <node-name> --show-labels | grep gpu.product
# nvidia.com/gpu.product=NVIDIA-GeForce-RTX-4090
```
<br>

```yaml
# time-slicing-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: time-slicing-config
data:
  nvidia-geforce-rtx-4090: |-
    version: v1
    flags:
      migStrategy: none
    sharing:
      timeSlicing:
        resources:
        - name: nvidia.com/gpu
          replicas: 2
```

```bash
$ kubectl create -n gpu-operator -f time-slicing-config.yaml
configmap/time-slicing-config created

$ kubectl describe configmaps -n gpu-operator time-slicing-config
Name:         time-slicing-config
Namespace:    gpu-operator
...
Data
====
nvidia-geforce-rtx-4090:
----
version: v1
flags:
  migStrategy: none
sharing:
  timeSlicing:
    resources:
    - name: nvidia.com/gpu
      replicas: 2
```

<br>

## ClusterPolicy 변경

ConfigMap을 ClusterPolicy에 연결한다. `default`를 지정하지 않아 모든 노드에 자동 적용되지 않도록 했다.

```bash
$ kubectl patch clusterpolicies.nvidia.com/cluster-policy \
    -n gpu-operator --type merge \
    -p '{"spec": {"devicePlugin": {"config": {"name": "time-slicing-config"}}}}'
clusterpolicy.nvidia.com/cluster-policy patched
```

ClusterPolicy가 변경되면, GPU Operator Controller가 변경을 감지하고 NVIDIA Device Plugin DaemonSet을 재시작한다.

<br>

## 노드 라벨 적용

Time Slicing을 적용할 노드에 라벨을 붙인다.

```bash
$ kubectl label node my-node nvidia.com/device-plugin.config=nvidia-geforce-rtx-4090
```

<br>

## 적용 결과 확인

노드의 GPU 리소스가 replicas 수만큼 증가했는지 확인한다.

```bash
$ kubectl describe node my-node | grep -A 10 Allocatable
Allocatable:
  cpu:                96
  ephemeral-storage:  933679851198
  hugepages-1Gi:      0
  hugepages-2Mi:      0
  memory:             131605904Ki
  nvidia.com/gpu:     20    # 물리 GPU 10개 × replicas 2 = 20개
  pods:               110
```

노드 라벨도 확인해 보자.

```bash
$ kubectl describe node my-node | grep nvidia.com/gpu
nvidia.com/gpu.count=10
nvidia.com/gpu.product=NVIDIA-GeForce-RTX-4090-SHARED  # -SHARED 접미사
nvidia.com/gpu.replicas=2
nvidia.com/gpu.sharing-strategy=time-slicing           # Time Slicing 적용됨
```

GPU Feature Discovery에 의해 다음 라벨들이 자동으로 붙는다.
* `nvidia.com/<resource-name>.replicas=<replicas-count>`
* `nvidia.com/<resource-name>.product=<product-name>-SHARED`
* `nvidia.com/<resource-name>.sharing-strategy=time-slicing`

<br>

## 파드 배포 확인

이제 GPU를 요청하는 파드를 20개까지 배포할 수 있다.

```bash
$ kubectl get deployments.apps -n inference-namespace inference-pod
NAME                  READY   UP-TO-DATE   AVAILABLE   AGE
inference-pod         20/20   20           20          81d
```


<br>

# 한계 및 주의사항

<br>

## Fault Isolation 부재

[지난 글](https://sirzzang.github.io/dev/Dev-Kubernetes-GPU-Time-Slicing-1/#time-slicing의-한계)에서 다뤘듯이, Time Slicing은 물리적으로 격리되어 있지 않기 때문에 Fault Isolation이 제공되지 않는다.

* **메모리 관리**: 각 파드가 사용할 GPU 메모리를 제한할 방법이 없음
* **장애 전파**: 한 파드의 GPU 오류가 다른 파드에 영향 가능
* **신뢰할 수 있는 워크로드에만 사용 권장**: 내부 통제된 모델 추론 등

<br>

## DCGM-Exporter 제한

DCGM-Exporter는 GPU Time Slicing이 적용된 컨테이너의 메트릭을 개별 컨테이너 단위로 수집하지 못한다. Time Slicing이 적용된 환경에서는 GPU 메트릭이 컨테이너별로 분리되지 않고 전체 GPU 단위로만 수집된다.

<br>

## ConfigMap 변경 모니터링 미지원

GPU Operator는 Time Slicing ConfigMap의 변경을 자동으로 모니터링하지 않는다. ConfigMap을 변경한 후에는 NVIDIA Device Plugin DaemonSet을 수동으로 재시작해야 한다.

```bash
kubectl rollout restart daemonset nvidia-device-plugin-daemonset -n gpu-operator
```

<br>

## replicas 값 제한

`replicas` 값은 반드시 **2 이상**이어야 한다. 1로 설정하면 Device Plugin이 시작되지 않는다.

```text
error parsing config file: unmarshal error: error unmarshaling JSON: 
while decoding JSON: number of replicas must be >= 2
```

[NVIDIA 공식 문서](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/gpu-sharing.html)와 [k8s-device-plugin GitHub 저장소](https://github.com/NVIDIA/k8s-device-plugin)를 확인해 보았으나, [**replicas 수가 2보다 작으면 에러임을 확인할 수는 있으나**](https://github.com/NVIDIA/k8s-device-plugin/blob/main/api/config/v1/replicas.go#L254), 왜 2 이상이어야 하는지에 대한 명시적인 설명은 찾을 수 없었다. 

<br>

논리적으로 추측해 보면, 다음과 같은 이유들이 있을 수 있다.

* **개념적 이유**: Time Slicing의 목적은 GPU 공유(sharing)인데, `replicas=1`은 사실상 공유가 아니라 독점 할당이다. `replicas=1`이면 1개 파드만 사용하므로 기본 동작과 동일하고, `replicas=2`가 되어야 비로소 최소 2개 파드가 공유 가능해진다.
* **기술적 이유**: Time Slicing은 GPU를 공유하는 워크로드들이 서로 인터리브(interleave)할 수 있게 해주는 메커니즘인데, `replicas=1`이면 인터리브할 대상이 없어 Time Slicing의 의미가 없다.
* **설계 의도**: NVIDIA 입장에서는, Time Slicing 없이 사용하고 싶으면 `sharing` 섹션 자체를 삭제하고, Time Slicing을 켜려면 최소 2개는 나눠야 의미가 있다는 것을 명확하게 구분하고 싶었던 것으로 보인다.

<br>

## 설정 변경 시 기존 파드

Time Slicing 설정을 변경해도, 이미 스케줄링된 파드는 영향을 받지 않는다. 예를 들어, `replicas: 2`로 설정하여 20개 파드를 띄운 후 `replicas: 1`(또는 설정 제거)로 변경하더라도, 기존 20개 파드는 계속 실행된다. 

이는 쿠버네티스의 파드 라이프사이클과 GPU 리소스의 특성 때문이다.

* **스케줄링 완료 후**: 스케줄링이 완료된 파드는 더 이상 스케줄러가 관여하지 않는다. Allocatable 리소스는 **새 파드의 스케줄링 가능 여부**를 판단하는 데만 사용되며, 이미 실행 중인 파드를 제거하는 기준으로는 사용되지 않는다.
* **GPU는 Eviction 대상이 아님**: Kubelet의 eviction은 메모리, 디스크, PID 등 [특정 리소스의 실제 사용량](https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/#eviction-signals)을 기준으로 동작하는데, GPU는 이 eviction 대상 리소스 목록에 포함되지 않는다. 따라서 GPU Allocatable이 변해도 eviction이 발생하지 않는다.


<br>

# 참고

* [NVIDIA GPU Operator - Time Slicing GPUs in Kubernetes](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/gpu-sharing.html)
* [NVIDIA k8s-device-plugin GitHub](https://github.com/NVIDIA/k8s-device-plugin)
