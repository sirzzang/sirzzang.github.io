---
title:  "[Kubernetes] Kubernetes 환경에서 PyTorch 공유 메모리 설정하기"
excerpt: Kubernetes 환경에서 PyTorch 멀티 프로세스로 Data Loader를 이용할 때 발생할 수 있는 문제 
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
  - pytorch
---



<br>

# 문제





![kubernetes-pytorch-dataloader-shm-error]({{site.url}}/assets/images/kubernetes-pytorch-dataloader-shm-error.png){: .align-center}

- k8s 환경에서 YoloX 모델 학습을 위한 컨테이너 실행
  - Argo Workflow를 이용해 데이터 추출, 전처리 등의 과정이 실행되고 난 뒤, 마지막에 실행

- 실행 시 공유 메모리 부족 문제로 컨테이너 죽음

> RuntimeError: DataLoader worker (pid 229) is killed by signal: Bus error. It is possible that dataloader's workers are out of shared memory. Please try to raise your shared memory limit.



<br>



# 원인



- PyTorch DataLoader
  - `num_process`가 1 이상의 값인 경우, multi-process data loading
    - [Multi-process data loading](https://pytorch.org/docs/stable/data.html#multi-process-data-loading)
  - DataLoader worker 간 공유 메모리를 이용해 데이터를 공유하며 로드함
- 이 과정에서 shared memory 크기가 부족했던 것
  - k8s 환경에서 컨테이너의 shared memory 영역 default size는 보통 64MiB
  - docker 컨테이너 기본 설정이 바뀌지 않는 한 그대로 override



<br>

# 해결



- Dataset 크기 및 변환 최적화
  - 노드 자원인 충분한데 굳이?
- PyTorch DataLoader의 `num_workers` 인자 값 조정
  - 노드 자원이 충분한데 굳이?
- docker container 실행 시 사용할 수 있는 옵션
  - `--shm-size`
  - `--ipc=host`
- k8s 환경에서 실행 시 사용할 수 있는 방법
  - memory 타입의 emptyDir 이용해 shared Memory 크기 설정



<br>

## emptyDir 이용 shared memory 크기 변경

- emptyDir: 파드와 수명주기를 같이 하는 임시 볼륨

  - 처음에는 비어 있음
  - medium을 `memory`로 설정할 경우, 데이터를 물리적인 디스크 대신 메모리에 저장할 수 있음

- 예시

  ```yaml
  apiVersion: v1
  kind: Pod
  metadata:
    name: example-pod
  spec:
    containers:
    - name: example-container
      image: your_docker_image
      volumeMounts:
      - mountPath: /dev/shm
        name: dshm
    volumes:
    - name: dshm
      emptyDir:
        medium: Memory
        sizeLimit: 4Gi
  
  ```

  

<br>



emptyDir를 활용해 shared memory 크기를 변경한 결과는 다음과 같다.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  generateName: training-pipeline-eb042ap-d-231122-
  namespace: argo-workflow
spec:
  entrypoint: training-pipeline
  imagePullSecrets:
  - name: docker-pull-secret
  serviceAccountName: argo-workflow-argo-workflows-workflow-controller
  templates:
  - dag:
      tasks:
      - name: train-model
        template: model-trainer
    name: training-pipeline
  - container:
      args:
      - main.py
      - --config
      - yolox_config.ini
      - --mode
      - train
      command:
      - python3
      image: sir0123/neo-mlops:model-trainer-0.0.1
      imagePullPolicy: Always
      volumeMounts:
      - mountPath: /app/datasets/COCO
        name: train-data
        readOnly: true
      - mountPath: /dev/shm # 컨테이너에 해당 emptyDir 마운트
        name: shm-empty-dir
    name: model-trainer
  volumes:
  - name: train-data
    persistentVolumeClaim:
      claimName: train-data-pvc
  - emptyDir: # shared memory 설정을 위한 emptyDir
      medium: Memory
      sizeLimit: 2Gi
    name: shm-empty-dir
```

