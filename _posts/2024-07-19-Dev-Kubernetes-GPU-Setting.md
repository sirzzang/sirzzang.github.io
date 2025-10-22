---
title:  "<<TODO>> [Kubernetes] Kubernetes 환경에서 NVIDIA GPU 사용하기"
excerpt: Kubernetes 환경에서 GPU 사용할 수 있도록 설정하기
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - k8s
  - gpu
---







K8s 환경에서 GPU가 있는 노드를 사용하기 위해서는 Kubernetes version이 1.10 이상이어야 하며, 클러스터 내에 [NVIDIA device plugin](https://github.com/NVIDIA/k8s-device-plugin)을 배포해야 한다.

- GPU 노드 Prerequisites
  - NVIDIA driver 설치
  - [NVIDIA docker](https://github.com/NVIDIA/nvidia-docker) 혹은 [NVIDIA container toolkit](https://github.com/NVIDIA/nvidia-container-toolkit) 설치
    - NVIDIA docker는 현재 deprecated로, NVIDIA container toolkit을 사용할 것을 권장하고 있음
    - NVIDIA container toolkit 설치를 위한 [NVIDIA 공식 가이드](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
  - docker runtime으로 NVIDIA docker container runtime 설정
- K8s cluster에 NVIDIA k8s gpu plugin 배포
  - daemonset 방식 배포: 권장되는 방식
    - 공식 제공되는 yaml 파일 직접 배포
    - [helm을 이용한 배포](https://github.com/NVIDIA/k8s-device-plugin?tab=readme-ov-file#configuring-the-device-plugins-helm-chart)
  - 수동 배포



<br>

# NVIDIA device plugin

Kubernetes 클러스터 환경에서 GPU를 활용할 수 있도록 해 주는 플러그인이다. NVIDIA에서 공식적으로 제공하는 [Kubernetes device plugin](https://kubernetes.io/docs/concepts/extend-kubernetes/compute-storage-net/device-plugins/) 구현체이다.



## Kubernetes device plugin

Kubernetes에서 시스템 하드웨어 리소스를 사용하기 위해서는 kubelet에게 하드웨어 리소스를 등록하고, 사용할 수 있도록 해야 한다. 이를 위해 Kubernetes는 클러스터의 kubelet에게 시스템 하드웨어 리소스를 알릴 수 있도록 device plugin framework를 제공한다. 각 하드웨어 리소스 공급 업체는 Kubernetes가 제공하는 device plugin framework를 구현하기만 하면 된다.

 말하자면 인터페이스인 셈인데, 공식 문서를 잠깐 참고하면, gRPC 기반 서비스인 것으로 보인다.

```
service DevicePlugin {
      // GetDevicePluginOptions returns options to be communicated with Device Manager.
      rpc GetDevicePluginOptions(Empty) returns (DevicePluginOptions) {}

      // ListAndWatch returns a stream of List of Devices
      // Whenever a Device state change or a Device disappears, ListAndWatch
      // returns the new list
      rpc ListAndWatch(Empty) returns (stream ListAndWatchResponse) {}

      // Allocate is called during container creation so that the Device
      // Plugin can run device specific operations and instruct Kubelet
      // of the steps to make the Device available in the container
      rpc Allocate(AllocateRequest) returns (AllocateResponse) {}

      // GetPreferredAllocation returns a preferred set of devices to allocate
      // from a list of available ones. The resulting preferred allocation is not
      // guaranteed to be the allocation ultimately performed by the
      // devicemanager. It is only designed to help the devicemanager make a more
      // informed allocation decision when possible.
      rpc GetPreferredAllocation(PreferredAllocationRequest) returns (PreferredAllocationResponse) {}

      // PreStartContainer is called, if indicated by Device Plugin during registration phase,
      // before each container start. Device plugin can run device specific operations
      // such as resetting the device before making devices available to the container.
      rpc PreStartContainer(PreStartContainerRequest) returns (PreStartContainerResponse) {}
}
```



<br>



# GPU node 설정



TODO



<br>

# K8s cluster에 GPU node 추가하기



## daemonset 배포

```bash
$ kubectl get nodes
NAME          STATUS   ROLES                  AGE    VERSION
XXXXXXX-mam   Ready    control-plane,master   3d2h   v1.27.9+k3s1
XXXXXXX02     Ready    <none>                 23h    v1.27.9+k3s1
```

- k8s cluster 구성
  - master: non GPU node
  - worker: GPU node



```bash
$ helm upgrade -i nvdp nvdp/nvidia-device-plugin \
	--namespace nvidia-device-plugin \
	--create-namespace \
	--version 0.16.0
```

- master node에 접속해 NVIDIA k8s device plugin daemonset 배포

  - helm을 이용한 배포 방식 선택

  



```bash
$ kubectl get daemonset nvdp-nvidia-device-plugin -n nvidia-device-plugin
NAME                        DESIRED   CURRENT   READY   UP-TO-DATE   AVAILABLE   NODE SELECTOR   AGE
nvdp-nvidia-device-plugin   0         0         0       0            0           <none>          23s
```

- daemonset 확인
  - 현재 클러스터 내에서 GPU가 있는 node가 인식되지 않은 상태로, device plugin pod가 어디에도 배포되지 않은 것을 확인할 수 있음



## GPU node 라벨링

![nvidia-gpu-present-label]({{site.url}}/assets/images/nvidia-gpu-present-label.png){: .align-center}{: width="500"}

- NVIDIA device plugin helm chart의 `values.yaml` 파일을 보면, daemonset 노드 중 `nvidia.com/gpu.present` 라벨이 붙어 있는 것을 인식한다는 것을 알 수 있음

  - [values.yaml](https://github.com/NVIDIA/k8s-device-plugin/blob/main/deployments/helm/nvidia-device-plugin/values.yaml)
  - trouble shooting 참고 링크: https://github.com/NVIDIA/k8s-device-plugin/issues/708
  



```bash
 $ kubectl label nodes XXXXXXX02 nvidia.com/gpu.present=true
```

- 클러스터에 추가하고자 하는 GPU  node에 해당 라벨 추가

  - 노드 정보 확인

    ```bash
    $ kubectl describe node XXXXXXX02
    Name:               XXXXXXX02
    Roles:              <none>
    Labels:             beta.kubernetes.io/arch=amd64
                        beta.kubernetes.io/instance-type=k3s
                        beta.kubernetes.io/os=linux
                        kubernetes.io/arch=amd64
                        kubernetes.io/hostname=innonew02
                        kubernetes.io/os=linux
                        node.kubernetes.io/instance-type=k3s
                        nvidia.com/gpu.present=true # 라벨 추가됨
    Annotations:        alpha.kubernetes.io/provided-node-ip: 172.40.10.22
                        flannel.alpha.coreos.com/backend-data: {"VNI":1,"VtepMAC":"3e:3d:a4:26:52:a6"}
                        flannel.alpha.coreos.com/backend-type: vxlan
                        flannel.alpha.coreos.com/kube-subnet-manager: true
                        flannel.alpha.coreos.com/public-ip: 172.40.10.22
                        k3s.io/hostname: innonew02
                        k3s.io/internal-ip: 172.40.10.22
                        k3s.io/node-args: ["agent","--docker"]
                        k3s.io/node-config-hash: AITGS3UENG3OLFRETTJ3T6FVBFULREX5XXK5TORDBNAAOFCPL2DQ====
                        k3s.io/node-env:
                          {"K3S_DATA_DIR":"/var/lib/rancher/k3s/data/dd87b6b4674aaf5776fcb1cec91f293bca5b6bbdb02dac95e866c2cf6a86ab4e","K3S_NODE_NAME":"innonew02","...
                        management.cattle.io/pod-limits: {"cpu":"150m","ephemeral-storage":"1Gi","memory":"192Mi"}
                        management.cattle.io/pod-requests: {"cpu":"100m","ephemeral-storage":"50Mi","memory":"128Mi","pods":"8"}
                        node.alpha.kubernetes.io/ttl: 0
                        volumes.kubernetes.io/controller-managed-attach-detach: true
    (...)                    
    ```



노드 라벨링 추가 시, 해당 노드의 라벨이 인식되며, daemonset에 의해 파드가 배포된다.

```bash
$ kubectl get daemonset nvdp-nvidia-device-plugin -n nvidia-device-plugin
NAME                        DESIRED   CURRENT   READY   UP-TO-DATE   AVAILABLE   NODE SELECTOR   AGE
nvdp-nvidia-device-plugin   1         1         1       1            1           <none>          1h
```



<br>



# K8s 클러스터 내 GPU 사용 확인



```yaml
apiVersion: v1
kind: Pod
metadata:
  name: gpu-pod
spec:
  restartPolicy: Never
  containers:
    - name: cuda-container
      image: nvcr.io/nvidia/k8s/cuda-sample:vectoradd-cuda10.2
      resources:
        limits:
          nvidia.com/gpu: 1 # requesting 1 GPU
  tolerations:
  - key: nvidia.com/gpu
    operator: Exists
    effect: NoSchedule
```



```bash
$ kubectl apply -f gpu-test.yaml
```

- GPU 사용하는 테스트 파드 배포

  - 정상적으로 실행된다면, toleration에 의해 GPU가 있는 노드에 스케쥴링됨

    

```bash
$ kubectl logs gpu-pod
[Vector addition of 50000 elements]
Copy input data from the host memory to the CUDA device
CUDA kernel launch with 196 blocks of 256 threads
Copy output data from the CUDA device to the host memory
Test PASSED
Done
```

- pod 실행 로그 확인
  - 정상적으로 실행되었음을 확인할 수 있음
