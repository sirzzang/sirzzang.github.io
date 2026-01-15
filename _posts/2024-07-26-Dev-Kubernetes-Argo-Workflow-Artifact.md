---
title:  "[Kubernetes] Argo Workflow Artifact 기능 사용하기"
excerpt: K3s 환경에 배포된 Argo Workflow에서 Object Storage를 Artifact 저장소로 설정하는 방법 
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - k8s
  - k3s
  - kubernetes
  - Argo Workflow
  - MinIO
---

<br>

Argo Workflow를 이용해 Object Detection Model을 학습하고 배포하기 위한 ML Pipeline을 개발하던 중, Argo Workflow의 Artifact 전달 기능을 사용해 볼 기회가 생겼다. 이에 어떤 기술적 문제를 해결해야 했고, Argo Workflow의 Artifact 기능을 어떻게 활용할 수 있었는지 기록해 두고자 한다.

- [Argo Workflow](https://argoproj.github.io/workflows/)
- [Argo Workflow Artifact](https://argo-workflows.readthedocs.io/en/latest/walk-through/artifacts/)

> *참고*: Helm 이용해 Argo Workflow 배포하기
>
> [Argo Helm](https://github.com/argoproj/argo-helm)을 참고해 Kubernetes 환경에 Argo Workflow를 배포할 수 있다.
>
> ```bash
> kubectl apply -n argo --create-namespace -f https://github.com/argoproj/argo-workflows/releases/download/v3.5.6/install.yaml
> ```


<br>



# 개요

## 상황

Pipeline의 Object Detection Model은 Input으로 **이미지**와 각 이미지 별 객체 bbox 정보를 포함하고 있는 **메타데이터**를 받아, Output으로 **모델**(*이라 표현하기는 애매하지만, 어쨌든 학습된 모델*)을 만들어 낸다. 각 데이터 별 포맷은 다음과 같다.

- Input
  - 이미지: `.png` 형태의 데이터
  - 메타데이터: [COCO Dataset](https://cocodataset.org/#home) Annotation 형태의 JSON 데이터
- Output
  - 모델: [onnx](https://onnx.ai/) 데이터

Pipeline은 ~~아주~~ 간략하~~고 큼지막하~~게 다음 단계로 구성된다.

- 데이터셋 준비: Object Detection Model에 사용될 데이터셋을 추출하고, 전처리한다.
- 모델 학습: 준비한 데이터셋을 Object Detection Model에 넣어 학습한 뒤, `.onnx` 형태의 모델을 만들어 낸다.
- 모델 배포: `.onnx` 형태의 모델을 배포한다.



<br>



## 문제

 위와 같은 상황에서 마주쳤던 문제 중 하나는 **데이터를 어떻게 전달할 것인가**였다. 특히 그 중에서도,

1. 데이터셋 준비 태스크에서 모델 학습 태스크로 넘어갈 때, JSON과 이미지 데이터를 어떻게 전달할 것인가와,
1. 모델 학습 태크스크에서 모델 배포 태스크로 넘어갈 때, onnx 데이터를 어떻게 전달할 것인가

가 주된 고민이었다.

<br>

## 대안

 데이터 전달의 방식으로 다음과 같은 방법들을 고민해 보았다.

- Message Queue: 데이터 전달을 위해 Message Queue의 Topic을 두고, Pipeline 각 태스크 별로 Message Queue의 Topic을 구독해 데이터를 주고 받음
- Argo Workflow Artifact: Argo Workflow에서 지원하는 Artifact 기능을 이용해, Pipeline 태스크 간 파일 전달
  - 태스크의 실행 결과로 생성되는 파일을 Artifact로서 전달할 수 있음
- Persistent Volume 이용: Argo Workflow의 각 태스크가 동일한 PV를 바라보도록 함

 결과적으로는 데이터셋 준비 시 JSON, onnx 데이터 전달을 위해서는 Argo Workflow의 Artifact 기능을, 이미지 데이터 전달을 위해서 Persistent Volume을 이용하기로 했다.

- Message Queue의 경우, 데이터 크기 전달 측면에서 문제가 있다.
  - 전달할 수 있는 데이터 크기가 정해져 있다. 설정을 통해 변경할 수는 있으나, 변경한다 하더라도 그보다 더 큰 크기의 데이터가 오면 문제가 된다.
  - 이를 극복하기 위해 데이터를 나눠서 전달할 수도 있다. 그러나 이 역시 데이터 유실의 위험이 있다.
- 파이프라인 태스크 간에 전달되기만 하면 되는 데이터는 Argo Worfklow의 Artifact를 이용하나, 모델 학습 시 로컬에 존재해야 하는 데이터는 Persistent Volume을 이용한다.



<br>



# Artifact 기능 사용하기

Argo Workflow의 Artifact 기능을 사용하기 위해서는, Artifact 저장소를 설정한 뒤, Artifact를 이용하는 YAML Manifest를 작성해 주면 된다.



<br>

## Artifact 저장소 설정

Argo Workflow의 Artifact 기능을 이용하기 위해서는 Argo Workflow가 사용할 수 있는 Artifact 저장소를 설정해 주어야 한다. Argo Workflow는 Artifact 저장소로 [S3와 호환되는 object storage를 지원](https://argo-workflows.readthedocs.io/en/latest/configure-artifact-repository/)하고 있다. 따라서 S3와 호환되는 오픈소스 Object Storage인 MinIO를 Artifact 저장소로 사용하기로 결정했다.



<br>

### MinIO 배포

Kubernetes 환경에서 MinIO를 배포할 수 있는 방법은 여러 가지가 있다. 그 중, [Helm을 이용해 배포하는 방식](https://min.io/docs/minio/kubernetes/upstream/operations/install-deploy-manage/deploy-operator-helm.html)을 선택했다.

```bash
$ helm repo add minio https://charts.min.io/
$ helm install minio minio/minio \
	--namespace minio --create-namespace \
	--set mode=standalone \
	--set replicas=1 \
	--set resources.requests.memory=1Gi \
	--set service.type=NodePort \
	--set service.nodePort=32002 \
	--set consoleService.type=NodePort \
	--set rootUser=admin \
	--set rootPassword=password
```

- `--set`을 통해 조정할 수 있는 값들은 [minio helm values](https://github.com/minio/minio/blob/master/helm/minio/values.yaml)를 참고하면 된다.



<br>



### MinIO Bucket 생성

Argo Workflow의 Artifact 저장소로 사용하기 위한 Bucket을 생성한다.

![minio-artifact-store]({{site.url}}/assets/images/minio-artifact-store.png){: .align-center}

<br>



### Argo Workflow Namespace에 MinIO 접속 Secret 배포

Argo Workflow가 배포된 namespace에 MinIO에 접속하기 위한 Secret을 배포한다.

- `minio-secret.yaml`

  ```yaml
  apiVersion: v1
  kind: Secret
  metadata:
    name: minio-secret
    namespace: argo # NOTE: check argo namespace
  type: Opaque
  stringData:
    accessKey: admin
    secretKey: password
  ```

  > *참고*: Argo Workflow가 배포된 namespace 확인하는 방법
  >
  > Argo Workflow가 어떤 namespace에 배포되었는지 모른다면, 아래와 같이 확인하면 된다.
  >
  > ```bash
  > $ kubectl get namespaces | grep argo
  > ```

- 배포

  ```bash
  $ kubectl apply -f minio-secret.yaml
  ```

<br>





### Argo Workflow Controller Configmap 변경

[공식 문서](https://argo-workflows.readthedocs.io/en/latest/configure-artifact-repository/#s3-compatible-artifact-repository-bucket-such-as-aws-gcs-minio-and-alibaba-cloud-oss)를 참고해 Argo Workflow Controller의 Configmap을 변경한다.

- 아래의 값을 Argo Workflow Controller Configmap의 Data 영역에 추가한다.

  ```
  data:
    config: |
      artifactRepository:
        s3:
          bucket: argo-artifact-store
          endpoint: minio.minio.svc.cluster.local:9000
          insecure: true
          accessKeySecret:
            name: minio-secret
            key: accessKey
          secretKeySecret:
            name: minio-secret
            key: secretKey
  ```

  - `config` 키의 값으로 `artifactRepoistory` 설정 값을 추가한다.
  - `config` 값 내 `artifactRepository.s3.endpoint`으로 MinIO 파드가 배포된 클러스터 내에서 사용할 수 있는 FQDN 형태의 DNS를 사용했다.

  > *참고*: Argo Workflow Configmap 확인하는 방법
  >
  > Argo Workflow Controller의 Configmap 명을 모른다면, 아래와 같이 확인할 수 있다.
  >
  > ```bash
  > $ kubectl get configmap -n <my-argo-workflow-namespace>
  > ```
  >
  > 아래와 같은 예시 결과를 확인할 수 있는데, 확인할 수 있는 것 중 `workflow-controller-configmap`이 들어간 것이 Workflow Configmap 명이다.
  >
  > ```bash
  > $ kubectl get configmap -n argo-workflow
  > NAME                                                         DATA   AGE
  > kube-root-ca.crt                                             1      4d22h
  > workflow-controller-configmap   0      4d22h
  > ```

- `kubectl edit` 커맨드를 이용해 변경한다.

  ```bash
  $ kubectl edit configmap workflow-controller-configmap -n argo
  ```

  ![argo-workflow-controller-configmap]({{site.url}}/assets/images/argo-workflow-controller-configmap.png)



<br>

## Artifact 이용 매니페스트 작성

위와 같이 Argo Artifact Workflow를 설정한 후, Artifact를 이용하는 Argo Workflow 매니페스트를 작성하면 된다. 해당 방법은 이 포스트의 범위를 넘어난다고 판단해 생략한다.

- [Argo Workflow Artifact Example](https://argo-workflows.readthedocs.io/en/latest/walk-through/artifacts/)

<br>



# 결론

Artifact 저장소를 설정한 뒤, Artifact로 데이터를 넘기는 Manifest를 작성한다. 그리고 Workflow를 실행하면, 아래와 같이 파이프라인 태스크 간에 Artifact 파일이 넘어가는 것을 확인할 수 있다. 

![argo-workflow-artifact-result]({{site.url}}/assets/images/argo-workflow-artifact-result.png){: .align-center}



Artifact 저장소로 설정한 MinIO의 Bucket을 확인하면, 아래와 같이 `.tgz` 형태의 파일이 저장되어 있는 것을 확인할 수 있다.

![argo-workflow-minio-result]({{site.url}}/assets/images/minio-artifact-store.png){: .align-center}
