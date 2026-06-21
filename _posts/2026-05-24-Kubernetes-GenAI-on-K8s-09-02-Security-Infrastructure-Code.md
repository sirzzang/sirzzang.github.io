---
title: "[GenAI] GenAI on K8s: 9.2 - 보안 인프라 코드 분석: EKS + Secret 주입 흐름"
excerpt: "Ch9 Terraform 코드를 따라가며 EKS 보안 설계(Bottlerocket, IMDSv2, Pod Identity, ECR 공급망)와 Secrets Store CSI Driver의 secret 주입 흐름을 분석해 보자."
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
  - Secrets-Store-CSI
  - Pod-Identity
  - IRSA
  - ECR
  - Kubernetes-for-Generative-AI-Solutions
  - Kubernetes-for-Generative-AI-Solutions-Chapter-9
use_math: false
hidden: true
---

*[Kubernetes for Generative AI Solutions(Packt 2025, ISBN 978-1-83620-993-5, 저자 Ashok Srirama / Sukirti Gupta)](https://github.com/PacktPublishing/Kubernetes-for-Generative-AI-Solutions) 9장의 학습 내용을 바탕으로 합니다*

<br>

[이전 글]({% post_url 2026-05-24-Kubernetes-GenAI-on-K8s-09-01-Security-Defense-in-Depth %})에서 defense in depth와 K8s 보안 영역별 개념을 정리했다. 이번 글에서는 그 개념들이 **실제 Terraform 코드**에 어떻게 적용되어 있는지 분석한다.

코드 읽는 순서는 `eks.tf`(클러스터 토대·host 보안) → `addons.tf`(secret 주입 백본) → `iam.tf`(Pod Identity) → `ecr.tf`(공급망)다. 클러스터를 세우고, 그 위 secret 흐름(addons→iam)을 묶어 본 뒤, 마지막에 이미지 공급망을 본다.

<br>

# TL;DR

- `eks.tf`는 Bottlerocket AMI로 host 공격면을 최소화하고, IMDSv2는 EKS 모듈 기본값으로 자동 적용된다(명시 코드 없이도 `http_tokens=required`)
- `addons.tf`의 Secrets Store CSI Driver는 etcd를 거치지 않고 외부 store → 파드 tmpfs로 secret을 직행시킨다. `syncSecret=true`는 편의(env 주입)와 보안(etcd 미경유) 사이의 트레이드오프다
- `iam.tf`는 Pod Identity로 `hugging-face-secret*` 하나에만 권한을 묶는 최소권한 정책을 보여준다. 같은 클러스터에서 IRSA(EBS CSI)와 Pod Identity(앱)가 공존한다
- `ecr.tf`는 모델 이미지(`my-llama-finetuned`)에만 IMMUTABLE + CONTINUOUS_SCAN을 걸어 자산 가치에 맞춘 차등 보안 정책을 적용한다
- secret 한 줄 흐름: Secrets Manager → CSI Driver + provider-aws → 파드 tmpfs(파일) + 동기화된 K8s Secret(env)

<br>

# `eks.tf` — 클러스터 토대 + host 보안

```hcl
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.36"
  cluster_name    = local.name       # "eks-demo"
  cluster_version = "1.32"
  enable_cluster_creator_admin_permissions = true
  cluster_endpoint_public_access           = true

  eks_managed_node_groups = {
    eks-mng = {
      instance_types = ["m5.large", "m6i.large", "m7i.large"]
      ami_type       = "BOTTLEROCKET_x86_64"   # host 보안
      max_size = 3; desired_size = 3
      capacity_type = "SPOT"
    }
    # eks-gpu-mng = { ... }   # 보안 데모는 GPU 불필요 → 주석 처리
  }
}
```

보안 챕터의 주제(secret 주입, Pod Identity, 공급망 스캔)는 워크로드 종류와 무관하다. GPU 없이 CPU 노드만으로 모든 개념을 보여줄 수 있어, GPU 노드그룹은 주석 처리되어 있다.

## Bottlerocket AMI

`ami_type = "BOTTLEROCKET_x86_64"`로 host 보안을 확보한다.

| 항목 | 일반 AL2023 | Bottlerocket |
|---|---|---|
| 루트 파일시스템 | 읽기/쓰기 | **읽기 전용**(immutable) |
| 패키지 매니저 | 있음 | **없음**(공격 표면 축소) |
| 업데이트 | in-place | **atomic**(이미지 교체·롤백) |
| 용도 | 범용 | 컨테이너 전용 |

## IMDSv2 — 코드에 없지만 적용되어 있다

`eks.tf`에 `metadata_options`가 명시되어 있지 않지만, `terraform-aws-modules/eks` 관리형 노드그룹이 런치템플릿 `metadata_options` **기본값**으로 `http_tokens="required"` + `http_put_response_hop_limit=2`를 설정한다. 따라서 **IMDSv2 토큰 강제는 이미 적용되어 있고**, 미적용인 건 `hop_limit=1` 하드닝뿐이다.

컨테이너 → 노드 IMDS까지 막으려면 노드그룹에 `metadata_options`를 명시해 hop을 1로 내린다:

```hcl
eks-mng = {
  instance_types   = ["m5.large", ...]
  ami_type         = "BOTTLEROCKET_x86_64"
  metadata_options = {
    http_endpoint               = "enabled"
    http_tokens                 = "required"   # IMDSv2 강제
    http_put_response_hop_limit = 1            # 컨테이너에서 IMDS 접근 차단
    instance_metadata_tags      = "enabled"
  }
}
```

## 실습 편의를 위해 보안을 양보한 설정들

이 코드에는 실습을 단순하게 만들려고 일부러 보안을 느슨하게 둔 설정이 섞여 있다.

| 설정 | 왜 느슨한가 | 프로덕션이라면 |
|---|---|---|
| `enable_cluster_creator_admin_permissions = true` | 추가 RBAC 설정 없이 바로 `kubectl`이 되지만, 최소권한 위반 | `false`로 끄고 필요한 사용자·역할에만 RBAC으로 명시 부여 |
| `cluster_endpoint_public_access = true` | API 서버가 인터넷에 공개되어 공격 표면이 넓다 | `public_access_cidrs`로 IP 화이트리스트하거나 private endpoint로 전환 |
| `llama_fine_tuning_irsa` 의 `AmazonS3FullAccess` | 계정 내 모든 S3 버킷에 전체 권한을 주는 과대권한 | 필요한 버킷·경로에만 최소 권한 정책 작성 |

`llama_fine_tuning_irsa`의 과대권한은 뒤에서 살펴볼 `iam.tf`의 최소권한 정책과 대비되는 나쁜 예시다.

<br>

# `addons.tf` — Secret 주입 백본 + 클러스터 애드온

```hcl
module "eks_blueprints_addons" {
  enable_aws_load_balancer_controller          = true
  enable_secrets_store_csi_driver              = true   # secret 전용 CSI driver
  enable_secrets_store_csi_driver_provider_aws = true   # AWS provider
  secrets_store_csi_driver = {
    values = ["syncSecret:\n  enabled: true"]            # K8s Secret 미러링
  }
  secrets_store_csi_driver_provider_aws = {
    values = ["tolerations:\n  - operator: Exists"]      # 전 노드 배포
  }
  eks_addons = {
    aws-ebs-csi-driver = {
      service_account_role_arn = module.ebs_csi_driver_irsa.iam_role_arn  # IRSA
    }
    eks-pod-identity-agent = {}   # Pod Identity 전제
    metrics-server = {}; coredns = {}; kube-proxy = {}; vpc-cni = {}
  }
}
```

## 두 가지 secret 주입 경로 — 네이티브 vs CSI

K8s에서 secret을 파드에 넣는 코어(내장) 방식은 `Secret` 객체를 만들어 **etcd에 저장**하고, kubelet이 파일 volume 또는 env로 마운트하는 것이다. Secrets Store CSI Driver는 이를 대체하는 게 아니라, **외부 store에서 가져와 마운트하는 별개의 애드온 경로**다.

![네이티브 Secret(etcd·kubelet) vs Secrets Store CSI(외부 store·애드온) 경로 비교]({{site.url}}/assets/images/genai-on-k8s-ch09-native-secret-vs-csi-paths.svg){: .align-center}

| | 네이티브 Secret (코어) | Secrets Store CSI (애드온) |
|---|---|---|
| source of truth | K8s `Secret` 객체(**etcd**) | **AWS Secrets Manager**(클러스터 외부) |
| 마운트 주체 | kubelet(내장) | CSI Driver + AWS provider(DaemonSet) |
| etcd 경유 | 함(base64 = 사실상 평문) | **안 함**(파드 tmpfs에만) |
| 회전·IAM·감사 | 제한적 | Secrets Manager가 제공 |

> **용어 주의**: "CSI"(Container Storage Interface)는 원래 EBS 같은 디스크 볼륨을 붙이는 표준 플러그인 틀이다. **Secrets Store CSI Driver**는 그 틀에 얹은 *secret 전용* 드라이버이고, provider 플러그인으로 여러 백엔드(AWS/Vault/Azure)를 붙일 수 있다.

## Driver + Provider, 그리고 노드-로컬 흐름

| 구성요소 | 역할 |
|---|---|
| Secrets Store CSI **Driver** | CSI 표준 인터페이스. "secret을 volume으로" 마운트하는 공통 층(backend 모름) |
| **provider-aws** | driver의 플러그인. 실제로 Secrets Manager / SSM에서 값을 가져옴 |

![Secrets Store CSI 노드-로컬 흐름]({{site.url}}/assets/images/genai-on-k8s-ch09-secrets-store-csi-flow.svg){: .align-center}

흐름은 노드 안에서 닫힌다: 파드가 볼륨을 요청하면 kubelet이 CSI driver 노드 플러그인을 호출하고, driver가 AWS provider를 거쳐 Secrets Manager에서 값을 fetch(이때 Pod Identity 자격증명 사용)해 파드 tmpfs에 파일로 올린다. **etcd를 거치지 않는다**는 게 이 경로의 핵심이다.

## syncSecret — 편의 vs 보안 트레이드오프

CSI Driver의 기본 일은 secret을 파드에 **파일**로 마운트하는 것뿐이다. 그 자체로는 네이티브 K8s `Secret` 객체를 만들지 않는다.

| | `false`(driver 기본값) | `true`(ch9 설정) |
|---|---|---|
| 파드에 노출 | `/mnt/secrets-store/...` 파일 | 파일 + K8s `Secret` 객체 추가 동기화(etcd) |
| 앱이 읽는 법 | 파일 읽기 | 파일 + **env `valueFrom.secretKeyRef`** |

`false`여도 secret을 못 쓰는 게 아니라 **파일로는 쓸 수 있다**. 다만 env 변수로 주입하려면(`secretKeyRef`) K8s Secret 객체가 필요한데, `false`면 그게 없어 env 방식만 불가하다.

CSI Driver를 쓰는 본래 목적이 *etcd를 안 거치는 것*이기 때문에, `syncSecret=true`는 그 이점을 일부 되돌린다(etcd에 사본을 만든다). ch9이 `true`를 쓴 이유는 deploy가 HF 토큰을 `secretKeyRef`로 **env 주입**하기 때문이다 — **편의(env 주입) vs 보안(etcd 미경유)** 트레이드오프다.

## Provider tolerations + pod-identity-agent

provider-aws는 **DaemonSet**이라 모든 노드에서 떠야 그 노드의 Pod도 secret을 마운트할 수 있다. `tolerations: [{operator: Exists}]`는 어떤 taint(GPU 노드 taint 포함)든 무조건 견뎌 전 노드 배포를 보장한다.

`eks-pod-identity-agent` 애드온은 Pod Identity가 동작하는 전제로, 노드에서 Pod에 임시 자격증명을 주입한다.

## EBS CSI가 IAM을 필요로 하는 이유

EBS CSI controller는 PVC 요청 시 실제 AWS API(`ec2:CreateVolume`, `AttachVolume` 등)를 호출해 EBS를 프로비저닝한다. 그 권한이 IAM Role로 필요하며, 방식은 **IRSA**다. 같은 파일의 Karpenter는 **Pod Identity**(`create_pod_identity_association = true`)를 쓴다 — 한 클러스터에 IRSA(구방식)와 Pod Identity(신방식)가 혼용된다.

## gp2 → gp3 default StorageClass 전환

| | gp2 | gp3 |
|---|---|---|
| IOPS | 3 IOPS/GB(용량 비례) | baseline **3,000 고정** |
| Throughput | 용량 비례 | baseline **125 MB/s** + 독립 구매 |
| 가격 | $0.10/GB·월 | **$0.08/GB·월(-20%)** |

EKS가 자동 생성한 gp2 StorageClass의 `is-default-class`를 `false`로, 새 gp3를 default로 만든다. 이후 annotation 없이 생성되는 PVC는 gp3를 쓴다.

<br>

# `iam.tf` — Pod Identity + 최소권한 Secret 정책

```hcl
# trust policy — Pod Identity의 표식
data "aws_iam_policy_document" "my_llama_app_trust_policy" {
  statement {
    actions    = ["sts:AssumeRole", "sts:TagSession"]
    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]   # Pod Identity
    }
  }
}

# 최소권한: hugging-face-secret 하나에만 GetSecretValue/DescribeSecret
resource "aws_iam_policy" "hf_secrets_access_policy" {
  # Resource = "secret:hugging-face-secret*"
}

# association: ns=default의 SA my-llama-sa에 이 Role을 연결
resource "aws_eks_pod_identity_association" "my_llama_sa_pod_identity" {
  cluster_name    = module.eks.cluster_name
  namespace       = "default"
  service_account = "my-llama-sa"
  role_arn        = aws_iam_role.my_llama_app_role.arn
}
```

## IRSA vs Pod Identity — 한 클러스터에 공존

| | IRSA(Ch5 / EBS CSI) | Pod Identity(Ch9 `iam.tf`) |
|---|---|---|
| trust principal | `oidc.eks.../id/...`(OIDC provider ARN) | **`pods.eks.amazonaws.com`**(서비스 principal) |
| 사전 준비 | 클러스터마다 OIDC provider 등록 | **불필요**(agent 애드온만) |
| SA 연결 | SA annotation `eks.amazonaws.com/role-arn` | **association 리소스**(클러스터·ns·sa·role) |
| 멀티클러스터 | Role trust가 OIDC ARN 종속 → 재사용 어려움 | trust가 일반 principal → 같은 Role **재사용 쉬움** |

trust의 principal이 `pods.eks.amazonaws.com`인 것이 Pod Identity의 표식이다. 자격증명 흐름은 Pod(`my-llama-sa`) → `eks-pod-identity-agent`가 임시 자격증명 주입 → `AssumeRole` → `hf_secrets_access_policy` 권한으로 Secrets Manager 호출이다.

## 최소권한 vs 과대권한

`Resource = "secret:hugging-face-secret*"`로 그 secret 하나에만 `GetSecretValue`/`DescribeSecret`를 허용한다. 이 Role이 탈취돼도 다른 secret은 읽히지 않는다.

`eks.tf`의 fine-tune IRSA가 `AmazonS3FullAccess`(과대권한)인 것과 정확히 대비되는 모범 사례다.

> association은 "ns=default의 SA `my-llama-sa`에 이 Role을 연결"한다는 선언일 뿐이고, SA 객체 자체는 워크로드 매니페스트(`finetuned-inf-deploy.yaml`의 `serviceAccount: my-llama-sa`)에서 만들어진다 — association이 이름표를 예약해 두고, 실제 SA는 배포 시점에 생긴다.

<br>

# `ecr.tf` — 공급망 보안 (암호화·immutable·스캔)

```hcl
resource "aws_ecr_repository" "my-llama"           { image_tag_mutability = "MUTABLE" }
resource "aws_ecr_repository" "my-llama-finetuned" { image_tag_mutability = "IMMUTABLE" }
resource "aws_ecr_repository" "rag-app"            { }   # default MUTABLE

resource "aws_ecr_registry_scanning_configuration" "ecr_scanning_configuration" {
  scan_type = "ENHANCED"
  rule {
    scan_frequency    = "CONTINUOUS_SCAN"
    repository_filter { filter = "my-llama-finetuned" }
  }
  rule {
    scan_frequency    = "SCAN_ON_PUSH"
    repository_filter { filter = "my-llama-finetuned" }
  }
}
```

## 이미지 암호화

ECR은 기본적으로 S3 SSE(AES256)로 at-rest 암호화를 하므로 코드 없이 자동 적용된다. 더 강하게는 KMS 고객 관리 키(`encryption_type = "KMS"` + `kms_key`)로 키 회전·감사를 붙일 수 있다.

## Basic vs Enhanced Scanning

| | Basic | Enhanced(Amazon Inspector) |
|---|---|---|
| 범위 | OS 패키지 CVE | **OS + 언어 패키지**(pip/npm 등) CVE |
| 정보 | 제한적 | CVSS 점수·수정 가이드 |
| 과금 | 무료 | 이미지당 과금 |

GenAI 이미지는 torch/transformers 같은 언어 패키지가 핵심 공격면이라, 그걸 잡는 Enhanced가 적합하다.

## 두 스캔 빈도를 함께 거는 이유

`SCAN_ON_PUSH`는 push 그 순간 1회 스캔하고, `CONTINUOUS_SCAN`은 이후 새 CVE가 공개될 때마다 이미 저장된 이미지를 재스캔한다. 둘 다 걸면 "올릴 때는 깨끗했지만 나중에 발견된 취약점"까지 커버한다.

## 차등 정책 — 모델은 불변, 앱은 가변

`my-llama-finetuned`만 IMMUTABLE인 것은 fine-tuned 모델 이미지가 재현성·감사 추적이 생명이라 같은 태그 덮어쓰기를 막아야 하기 때문이다. `rag-app`과 `my-llama`는 앱 코드라 자주 재빌드되어 MUTABLE이 편하다. 스캔도 가장 민감한 `my-llama-finetuned` 한 repo에만 CONTINUOUS를 걸어, 이미지당 과금되는 Enhanced 비용을 자산 가치에 맞춰 집중시킨다.

<br>

# 워크로드 코드 — Secret이 파드까지 도달하는 경로

인프라가 깔아 둔 토대 위에서, 두 매니페스트가 secret을 파드까지 실제로 가져온다.

## SecretProviderClass — fetch/sync/auth 세 블록

```yaml
kind: SecretProviderClass
spec:
  provider: aws
  secretObjects:                       # (sync) → 네이티브 K8s Secret 생성
  - secretName: hugging-face-secret
    type: Opaque
    data:
    - objectName: hugging-face-secret
      key: token
  parameters:
    objects: |                         # (fetch) ← Secrets Manager에서 가져올 대상
      - objectName: "hugging-face-secret"
        objectType: "secretsmanager"
    usePodIdentity: "true"             # (auth) Pod Identity로 Secrets Manager 호출
```

| 블록 | 방향 | 역할 |
|---|---|---|
| `parameters.objects` | **fetch**(외부 → 클러스터) | Secrets Manager의 어느 시크릿을 가져올지 |
| `secretObjects` | **sync**(CSI → K8s Secret) | 가져온 값을 네이티브 K8s Secret으로도 만든다 |
| `usePodIdentity` | **auth** | fetch를 어떤 자격증명으로 할지 — `"true"` = Pod Identity |

`parameters.objects`만 있으면 secret은 파일로만 마운트된다. `secretObjects`가 있어야(= `syncSecret.enabled=true`와 짝) 네이티브 K8s Secret이 생겨서, deploy가 `env.secretKeyRef`로 토큰을 받을 수 있다. 이 동기화된 Secret은 SPC를 volume으로 마운트한 파드가 살아있는 동안에만 존재한다.

## Deploy — 이중 secret 경로

```yaml
containers:
- image: k8s4genai/my-llama:32
  resources: { limits: { nvidia.com/gpu: 1 } }
  env:
  - name: HUGGING_FACE_HUB_TOKEN         # 경로 A: env 주입
    valueFrom:
      secretKeyRef: { name: hugging-face-secret, key: token }
  volumeMounts:
  - name: aws-sm-secrets                 # 경로 B: 파일 마운트
    mountPath: "/mnt/secrets-store"
    readOnly: true
serviceAccount: my-llama-sa              # Pod Identity 고리
volumes:
- name: aws-sm-secrets
  csi:
    driver: secrets-store.csi.k8s.io
    volumeAttributes: { secretProviderClass: "aws-secret-provider-class" }
```

| 경로 | 코드 | 전제 |
|---|---|---|
| **A. env** | `env.secretKeyRef` | SPC의 `secretObjects` + `syncSecret=true`로 만든 K8s Secret |
| **B. 파일** | `volumeMounts /mnt/secrets-store` | CSI volume |

겉보기엔 중복이지만, **경로 B(volume 마운트)가 있어야 경로 A가 성립**한다. 동기화된 K8s Secret은 SPC를 마운트하는 파드가 떠 있는 동안에만 유지되기 때문에, 앱이 env만 읽더라도 volume을 함께 둔다.

### `kubectl create secret`이 아니라 이 방식인 이유

가장 근본적인 이유는 **"secret을 애초에 Secrets Manager로 관리하기로 했다"는 전제**다. 그 전제가 있으면 `kubectl create secret`은 Secrets Manager의 값을 손으로 꺼내 클러스터 etcd에 복사하는 셈이 되어, source of truth가 둘로 갈라지고 회전 시 수동 재동기화가 필요하며 드리프트가 생긴다.

| 축 | `kubectl create secret` | SecretProviderClass + Secrets Manager |
|---|---|---|
| 진실원천 | etcd(복사본) | 외부 Secrets Manager(단일) |
| 회전 | 수동 재생성 | SM이 회전, 파드는 재마운트로 반영 |
| 접근제어·감사 | K8s RBAC만 | IAM + CloudTrail 감사 |
| 노출 표면 | 값이 etcd·생성 명령에 남음 | 파일 경로만 쓰면 etcd 미경유 |

### serviceAccount와 실패 지점

`my-llama-sa`가 `iam.tf`의 Pod Identity association 대상이다. SA가 없거나 association이 안 걸리면, CSI provider가 Secrets Manager를 호출할 자격증명을 못 받아 **secret mount 단계에서 AccessDenied**로 파드가 못 뜬다.

<br>

# 정리 — secret 한 줄 흐름

```text
Secrets Manager (hugging-face-secret)     ← 단일 진실원천
   │  ← SPC parameters.objects (fetch)
   │  ← usePodIdentity=true (Pod Identity 자격증명)
   ▼
CSI Driver + provider-aws (노드 DaemonSet)
   ├─ /mnt/secrets-store 파일 마운트 (경로 B)
   └─ syncSecret → 네이티브 K8s Secret 생성 (파드 수명에 묶인 임시본)
          │
          ▼  env.secretKeyRef (경로 A)
   파드: HUGGING_FACE_HUB_TOKEN
   (serviceAccount: my-llama-sa로 떠야 Pod Identity가 작동)
```

| 인프라 파일 | 보안 포인트 |
|---|---|
| `eks.tf` | Bottlerocket(host), IMDSv2(기본값), 실습 편의 양보 설정 식별 |
| `addons.tf` | 네이티브 vs CSI 경로, syncSecret 트레이드오프 |
| `iam.tf` | Pod Identity, 최소권한(`hugging-face-secret*`만) |
| `ecr.tf` | Enhanced Scanning + IMMUTABLE + 차등 CONTINUOUS |
| SPC + Deploy | fetch/sync/auth 세 블록, 이중 secret 경로 |

이 코드들이 실제로 동작하는지 [다음 글]({% post_url 2026-05-24-Kubernetes-GenAI-on-K8s-09-03-Security-Deployment-Verification %})에서 배포 후 5단계 검증으로 확인한다.

<br>

# 참고 링크

- [Kubernetes for Generative AI Solutions — GitHub](https://github.com/PacktPublishing/Kubernetes-for-Generative-AI-Solutions)
- [Secrets Store CSI Driver](https://secrets-store-csi-driver.sigs.k8s.io/)
- [Secrets Store CSI Driver — AWS Provider](https://github.com/aws/secrets-store-csi-driver-provider-aws)
- [EKS Pod Identity 소개](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html)
- [ECR Enhanced Scanning(Amazon Inspector)](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-enhanced.html)
- [terraform-aws-modules/eks](https://github.com/terraform-aws-modules/terraform-aws-eks)

<br>
