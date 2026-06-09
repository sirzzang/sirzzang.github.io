---
title: "[GenAI] GenAI on K8s: 9.3 - 보안 배포 실습: 5단계 검증 + GPU 트러블슈팅"
excerpt: "Ch9 인프라를 실제로 배포하고, ECR 공급망부터 Bottlerocket host, PSS, Secret 주입까지 5단계 보안 검증을 수행한다. GPU 추론 시도 중 만난 Bottlerocket ephemeral-storage 문제도 다룬다."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - GenAI
  - Security
  - EKS
  - Terraform
  - Bottlerocket
  - PSS
  - Secrets-Store-CSI
  - Pod-Identity
  - Troubleshooting
  - Kubernetes-for-Generative-AI-Solutions
  - Kubernetes-for-Generative-AI-Solutions-Chapter-9
use_math: false
---

*[Kubernetes for Generative AI Solutions(Packt 2025, ISBN 978-1-83620-993-5, 저자 Ashok Srirama / Sukirti Gupta)](https://github.com/PacktPublishing/Kubernetes-for-Generative-AI-Solutions) 9장의 학습 내용을 바탕으로 합니다*

<br>

[이전 글]({% post_url 2026-05-24-Kubernetes-GenAI-on-K8s-09-02-Security-Infrastructure-Code %})에서 분석한 Terraform 코드를 실제로 배포하고, 보안 기능이 동작하는지 5단계 검증을 수행한다.

<br>

# TL;DR

- Ch9 보안 베스트 프랙티스의 적용 현황은 세 갈래다: terraform 자동(ECR, Bottlerocket, IMDSv2 토큰, CSI, Pod Identity) / 배포 시 kubectl·aws(PSS, HF secret) / 미적용(hop_limit=1, securityContext)
- ECR: AES256 암호화 + IMMUTABLE + Enhanced Scanning(CONTINUOUS + SCAN_ON_PUSH) 확인
- Host: 3대 모두 Bottlerocket OS, IMDSv2 Required 확인
- PSS: `baseline` enforce로 privileged 파드가 **Forbidden**으로 차단되는 것을 확인
- **Secret 주입이 이 챕터의 핵심**: Secrets Manager → CSI → env·파일 두 경로로 토큰이 파드에 도달
- GPU 추론 시도 시 Bottlerocket의 **데이터 볼륨(xvdb) 18GB 부족**으로 ephemeral-storage eviction 루프 발생 → 원인 규명 후 Ch10으로 이연

<br>

# 적용 현황

[이전 글]({% post_url 2026-05-24-Kubernetes-GenAI-on-K8s-09-02-Security-Infrastructure-Code %})의 코드가 보여주는 보안 베스트 프랙티스의 적용 방식은 세 갈래로 갈린다.

| 베스트 프랙티스 | 적용 | 검증 단계 |
|---|---|---|
| ECR 암호화(AES256) | terraform 자동 | Step 2 |
| Tag immutability | terraform 자동 | Step 2 |
| Enhanced Scanning | terraform 자동 | Step 2 |
| Host: Bottlerocket | terraform 자동 | Step 3 |
| Host: IMDSv2(토큰 강제) | EKS 모듈 기본값으로 자동 | Step 3 |
| Host: IMDS `hop_limit=1` | **미적용**(기본 2) | — |
| Pod Security Standards | 배포 시 `kubectl label` | Step 4 |
| Secrets Store CSI + provider | terraform 자동 | Step 5 |
| 최소권한 IAM + Pod Identity | terraform 자동 | Step 5 |
| HF 토큰 → Secrets Manager + SPC + 앱배포 | 배포 시 aws·kubectl | Step 5 |
| 런타임 securityContext/limit | **미적용**(deploy yaml에 없음) | — |

<br>

# Step 1 — terraform apply

한 번의 apply로 EKS·VPC·addon(ALB, Karpenter, EBS CSI, Secrets Store CSI)·IRSA·ECR을 일괄 생성한다.

```bash
$ terraform init
# ... 모듈·provider 다운로드
Terraform has been successfully initialized!

$ terraform plan
# Plan: 110 to add, 0 to change, 0 to destroy.

$ terraform apply -auto-approve   # ~15-20분
# Apply complete!
```

kubeconfig 갱신 후 노드 상태 확인:

```bash
$ aws eks --region ap-northeast-2 update-kubeconfig --name eks-demo
$ kubectl get nodes

# 실행 결과
NAME                 STATUS   ROLES    AGE   VERSION
ip-10-0-2-136...     Ready    <none>   12m   v1.32.12-eks-f69f56f
ip-10-0-29-75...     Ready    <none>   12m   v1.32.12-eks-f69f56f
ip-10-0-42-85...     Ready    <none>   12m   v1.32.12-eks-f69f56f
```

HuggingFace 토큰을 Secrets Manager에 등록한다:

```bash
$ aws secretsmanager create-secret \
    --name hugging-face-secret \
    --secret-string "$HF_TOKEN" \
    --region ap-northeast-2

# 실행 결과
{ "ARN": "arn:aws:secretsmanager:ap-northeast-2:123456789012:secret:hugging-face-secret-AbCdEf",
  "Name": "hugging-face-secret" }
```

![EC2 콘솔 — eks-mng CPU 노드 인스턴스]({{site.url}}/assets/images/genai-on-k8s-ch09-ec2-cpu-nodes.png){: .align-center}

<br>

# Step 2 — 공급망 보안 검증 (ECR)

```bash
# 암호화 타입 확인
$ aws ecr describe-repositories --repository-names my-llama-finetuned \
    --query 'repositories[0].encryptionConfiguration.encryptionType' \
    --output text --region ap-northeast-2

# 실행 결과
AES256

# 태그 불변성 확인
$ aws ecr describe-repositories --repository-names my-llama-finetuned \
    --query 'repositories[0].imageTagMutability' \
    --output text --region ap-northeast-2

# 실행 결과
IMMUTABLE

# 스캔 설정 확인
$ aws ecr get-registry-scanning-configuration --region ap-northeast-2

# 실행 결과
{ "scanType": "ENHANCED",
  "rules": [
    { "scanFrequency": "SCAN_ON_PUSH",   "repositoryFilters": [{ "filter": "my-llama-finetuned" }] },
    { "scanFrequency": "CONTINUOUS_SCAN", "repositoryFilters": [{ "filter": "my-llama-finetuned" }] }
  ] }
```

공급망 3중 확인 완료: **AES256** 암호화, **IMMUTABLE** 태그, **ENHANCED**(Inspector) 스캔(push 시 + 지속).

<br>

# Step 3 — Host 보안 검증 (Bottlerocket)

```bash
$ kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.nodeInfo.osImage}{"\n"}{end}'

# 실행 결과
ip-10-0-2-136...    Bottlerocket OS 1.62.0 (aws-k8s-1.32)
ip-10-0-29-75...    Bottlerocket OS 1.62.0 (aws-k8s-1.32)
ip-10-0-42-85...    Bottlerocket OS 1.62.0 (aws-k8s-1.32)
```

3대 모두 **Bottlerocket OS** = host 공격면 최소화 확인.

**IMDSv2**(`http_tokens=required`)는 `eks.tf`에 명시하지 않았어도 `terraform-aws-modules/eks` 모듈 기본값으로 적용되어 있다. EC2 콘솔에서 "IMDSv2: Required"로 확인할 수 있다.

![EC2 인스턴스 요약 — IMDSv2: Required]({{site.url}}/assets/images/genai-on-k8s-ch09-imdsv2-required.png){: .align-center}

다만 `hop_limit`은 기본 **2**라 컨테이너 → 노드 IMDS 차단(`hop_limit=1`)은 미적용이다. 미적용인 건 IMDSv2가 아니라 hop_limit 하드닝뿐이다.

<br>

# Step 4 — Pod Security Standards (PSS)

namespace에 PSS 라벨을 적용한다:

```bash
$ kubectl label --overwrite namespace default \
    pod-security.kubernetes.io/enforce=baseline \
    pod-security.kubernetes.io/warn=restricted \
    pod-security.kubernetes.io/audit=restricted

# 실행 결과
namespace/default labeled
```

privileged 파드를 생성 시도하면 **baseline enforce에 의해 차단**된다:

```bash
$ kubectl run pss-demo --image=nginx --privileged

# 실행 결과
Error from server (Forbidden): pods "pss-demo" is forbidden:
  violates PodSecurity "baseline:latest": privileged
```

`enforce=baseline`이 privileged 파드를 실제 차단하는 것을 확인했다. `warn=restricted`도 걸어뒀기 때문에 이후 모든 파드 생성 시 restricted 경고가 뜨지만, enforce가 아니므로 생성은 된다.

<br>

# Step 5 — Secret 주입 검증 (CSI + Pod Identity)

**이 챕터의 핵심**이다. CPU 노드만으로 secret 주입 전체를 검증한다.

```bash
# CSI driver + provider DaemonSet 확인
$ kubectl get ds -n kube-system | grep secrets-store
secrets-store-csi-driver              ...
secrets-store-csi-driver-provider-aws ...

# Pod Identity association 확인
$ aws eks list-pod-identity-associations --cluster-name eks-demo --region ap-northeast-2 \
    --query "associations[?serviceAccount=='my-llama-sa']"

# 실행 결과
[ { "namespace": "default",
    "serviceAccount": "my-llama-sa",
    "associationId": "a-xxxxxxxxxxxx" } ]
```

SecretProviderClass와 SA를 생성하고, CPU 전용 테스트 파드를 배포한다:

```bash
$ kubectl apply -f inference/secret-provider-class.yaml
secretproviderclass.../aws-secret-provider-class created

$ kubectl create serviceaccount my-llama-sa -n default
serviceaccount/my-llama-sa created

$ kubectl apply -f inference/secret-test-pod.yaml
Warning: would violate PodSecurity "restricted:latest": ...
pod/secret-test created

$ kubectl get pod secret-test

# 실행 결과
NAME          READY   STATUS    RESTARTS   AGE
secret-test   1/1     Running   0          30s
```

> `warn=restricted` 경고가 떴지만 `enforce=baseline`이라 생성은 된다. warn vs enforce 차이를 눈으로 확인할 수 있다.

secret이 두 경로로 모두 들어왔는지 확인한다:

```bash
# 경로 A: env 주입 (secretKeyRef)
$ kubectl exec secret-test -- env | grep HUGGING_FACE
HUGGING_FACE_HUB_TOKEN=hf_***

# 경로 B: 파일 마운트 (CSI)
$ kubectl exec secret-test -- cat /mnt/secrets-store/hugging-face-secret
hf_***
```

**env·파일 두 경로 모두에 동일 토큰으로 주입** = Secrets Manager → CSI → 파드 흐름 성공. **이 챕터의 핵심 검증 완료.**

<br>

# Step 6 — GPU 추론 시도 + 트러블슈팅

## GPU 없이 배포 → Pending 확인

```bash
$ kubectl apply -f inference/finetuned-inf-deploy.yaml
deployment.apps/my-llama-finetuned-deployment created
service/my-llama-finetuned-svc created

$ kubectl describe pod -l app.kubernetes.io/name=my-llama-finetuned | grep -A5 Events

# 실행 결과
Warning  FailedScheduling  ...  0/3 nodes are available: 3 Insufficient nvidia.com/gpu.
```

`nvidia.com/gpu: 1` 요청이 CPU 노드에 맞지 않아 Pending — 예상대로다.

## GPU 노드 켜기 → 노드는 Ready, 그러나 파드는 eviction

`eks.tf`의 `eks-gpu-mng`를 On-Demand로 apply하면 GPU 노드가 합류한다:

```bash
$ kubectl get nodes -o wide | grep nvidia

# 실행 결과
ip-10-0-35-212...   Ready   ...   Bottlerocket OS 1.62.0 (aws-k8s-1.32-nvidia)

$ kubectl get node ip-10-0-35-212... -o jsonpath='{.status.allocatable.nvidia\.com/gpu}'
1
```

![EKS 콘솔 — 노드그룹 2개(eks-mng, eks-gpu-mng)]({{site.url}}/assets/images/genai-on-k8s-ch09-eks-console-nodegroups.png){: .align-center}

![EC2 콘솔 — eks-gpu-mng 노드 = g6.2xlarge(L4)]({{site.url}}/assets/images/genai-on-k8s-ch09-ec2-gpu-node-g6.png){: .align-center}

GPU 노드는 Ready이고 `nvidia.com/gpu: 1`을 광고하지만, 파드는 스케줄 후 `ContainerCreating`에서 죽고 다시 Pending — eviction 루프에 빠진다.

## 원인 — GPU가 아니라 ephemeral-storage(디스크)

```bash
$ kubectl get pod my-llama-finetuned-...-98x5q \
    -o jsonpath='{.status.reason}{"\t"}{.status.message}'

# 실행 결과
Evicted    The node was low on resource: ephemeral-storage.
           Threshold quantity: 2888722137, available: 84Ki.
```

GPU 노드의 디스크 용량을 보면 **데이터 볼륨이 18GB**뿐이다:

```bash
$ kubectl describe node ip-10-0-35-212... | grep -A4 Allocatable

# 실행 결과 (발췌)
Allocatable:
  ephemeral-storage:  16258590282     # ~16.25GB
  nvidia.com/gpu:     1
```

### 근본 원인: Bottlerocket의 볼륨 구조

Bottlerocket은 볼륨이 둘이다:
- `/dev/xvda`(OS 볼륨) — 루트 파일시스템, 읽기전용
- `/dev/xvdb`(**데이터 볼륨**) — 컨테이너 이미지 + ephemeral-storage가 여기 쌓인다

`eks.tf`에서 키운 100GB는 `xvda`(OS 볼륨)로 갔고, 정작 이미지가 쌓이는 **`xvdb` 데이터 볼륨은 AMI 기본 18GB** 그대로였다. `k8s4genai/my-llama:32`는 모델을 구워넣은 대형 이미지라 추출 중 18GB를 다 채우면 kubelet이 ephemeral-storage threshold에서 파드를 evict한다.

### 수정 — 데이터 볼륨(xvdb)을 키워야 한다

```hcl
eks-gpu-mng = {
  # ...
  block_device_mappings = {
    xvdb = {                          # OS가 아니라 데이터 볼륨!
      device_name = "/dev/xvdb"
      ebs = {
        volume_size           = 100   # 18GB → 100GB
        volume_type           = "gp3"
        encrypted             = true
        delete_on_termination = true
      }
    }
  }
}
```

> Bottlerocket에서는 OS(`xvda`)가 아니라 **데이터 볼륨(`xvdb`)**을 키워야 대형 이미지가 들어간다.

## 결정 — Ch10으로 이연

이 챕터의 핵심인 **secret 주입은 Step 5에서 이미 완료**됐다. GPU 추론 Running은 보안 개념 검증에 필수가 아니고, Ch10(GPU 최적화)이 같은 클러스터 위에서 같은 대형 이미지를 5 replica로 띄우므로, fix를 코드에 반영해 두고 **Ch10에서 데이터 볼륨을 키워 GPU 추론을 이어가기로 결정**했다.

<br>

# Teardown

```bash
$ kubectl delete -f inference/finetuned-inf-deploy.yaml --ignore-not-found
$ kubectl delete pod secret-test --ignore-not-found
$ kubectl delete -f inference/secret-provider-class.yaml --ignore-not-found

$ terraform destroy -auto-approve

$ aws secretsmanager delete-secret \
    --secret-id hugging-face-secret \
    --force-delete-without-recovery \
    --region ap-northeast-2
```

destroy 완료 후 orphan audit(과금원 잔존 확인):

| 카테고리 | 결과 |
|---|---|
| EKS 클러스터 / EC2(running) / NAT GW / 미연결 EIP | 0 |
| orphan EBS(available) / ELB·NLB·ALB | 0 |
| ECR repo 3종 / Secrets Manager | 0 |
| VPC(eks-demo) / 잔여 ENI / IAM role / 로그그룹 | 0 |

<br>

# 정리

| 단계 | 검증 내용 | 결과 |
|---|---|---|
| Step 1 | terraform apply + 노드 3대 Ready | 성공 |
| Step 2 | ECR: AES256 / IMMUTABLE / ENHANCED | 성공 |
| Step 3 | 노드 OS = Bottlerocket, IMDSv2 = Required | 성공 |
| Step 4 | privileged 파드 Forbidden(PSS baseline) | 성공 |
| **Step 5** | **secret env·파일 두 경로 주입(이 챕터 핵심)** | **성공** |
| Step 6 | GPU 추론 시도 → ephemeral-storage eviction | 원인 규명, Ch10 이연 |

Step 5까지가 Ch9 보안 챕터의 본질이다. GPU 추론은 보안 개념 검증과 무관하며, Bottlerocket의 xvdb 데이터 볼륨 크기 문제는 Ch10에서 해결한다.

<br>

# 참고 링크

- [Kubernetes for Generative AI Solutions — GitHub](https://github.com/PacktPublishing/Kubernetes-for-Generative-AI-Solutions)
- [Bottlerocket 데이터 볼륨 설정](https://bottlerocket.dev/en/os/latest/#/api/settings/kubernetes/)
- [EKS Pod Identity 소개](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html)
- [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [Secrets Store CSI Driver](https://secrets-store-csi-driver.sigs.k8s.io/)
- [ECR Enhanced Scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-enhanced.html)

<br>
