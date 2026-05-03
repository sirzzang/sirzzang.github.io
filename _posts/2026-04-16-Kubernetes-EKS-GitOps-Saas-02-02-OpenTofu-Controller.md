---
title: "[EKS] GitOps 기반 SaaS: 테넌트 인프라 배포 - 2. Tofu Controller"
excerpt: "Tofu Controller로 Terraform CRD를 Git에 push하면 인프라가 생기고, 삭제하면 인프라가 사라지도록 GitOps 기반 인프라 배포를 진행해 보자."
categories:
  - Kubernetes
toc: true
hidden: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - Terraform
  - GitOps
  - Flux
  - Tofu-Controller
  - SaaS
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-6
---

*[최영락](https://www.linkedin.com/in/ianychoi/)님의 AWS EKS Workshop Study(AEWS) 6주차 학습 내용을 기반으로 합니다.*


<br>

# TL;DR

- Tofu Controller(tf-controller)는 Kubernetes **Terraform CRD**를 감시하여 `terraform plan/apply`를 자동 실행하는 GitOps 도구다
- Terraform CRD YAML을 Git에 push하면, Flux가 변경을 감지하고 tf-controller가 tf-runner Pod를 띄워 AWS 인프라를 생성한다
- `destroyResourcesOnDeletion: true` 설정 덕분에 CRD 파일을 Git에서 삭제하면 AWS 리소스도 자동으로 정리(destroy)된다
- 이 실습은 "테넌트 **인프라** 배포"이지 "**앱** 배포"가 아니다. 앱 배포(HelmRelease)는 이후 별도 실습에서 다룬다

<br>

# Tofu Controller 동작 원리

[이전 포스트]({% post_url 2026-04-16-Kubernetes-EKS-GitOps-Saas-02-01-Terraform-Module %})에서는 Terraform CLI를 직접 실행하여 `tenant-apps` 모듈이 어떤 AWS 리소스를 만드는지 확인했다. 이번에는 그 모듈을 **GitOps 파이프라인 위에 올린다**. 핵심은 Tofu Controller(이하 tf-controller)다.

tf-controller는 Kubernetes 클러스터 안에서 동작하는 컨트롤러로, **Terraform CRD**(Custom Resource Definition)를 감시한다. 여기서 Terraform CRD란 "어떤 Terraform 모듈을 어떤 변수로 실행할지"를 선언하는 Kubernetes 매니페스트(manifest)다. 실행되어야 할 AWS 리소스 자체가 아니라, **Terraform 실행 명세서**라고 생각하면 된다.

전체 흐름은 다음과 같다.

![Tofu Controller 동작 흐름]({{site.url}}/assets/images/eks-w6-tofu-controller-flow.png){: .align-center}

각 구성 요소의 역할을 정리하면 다음과 같다.

| 구성 요소 | 역할 | 수명 |
|-----------|------|------|
| **tf-controller** | Terraform CRD를 감시하는 컨트롤러 (Deployment) | 상시 실행 |
| **tf-runner** | 실제 `terraform` 명령을 실행하는 Pod | 1회성 (plan/apply 완료 후 종료) |
| **Terraform CRD** | "이 모듈을, 이 변수로 실행하라"는 선언 | Git에 존재하는 한 유지 |

## tf-controller 실행 상태 확인

`flux-system` 네임스페이스의 Pod 목록을 보면 tf-controller가 실행 중인 것을 확인할 수 있다.

```bash
$ kubectl get po -n flux-system
NAME                                           READY   STATUS      RESTARTS        AGE
capacitor-dc778678d-th54n                      1/1     Running     4 (7h15m ago)   40h
ecr-credentials-sync-29619810-4dr8f            0/1     Completed   0               20s
flux-operator-6d6f8cbc94-lcxqt                 1/1     Running     0               40h
helm-controller-b7bbcf854-z94kj                1/1     Running     0               40h
kustomize-controller-77c78b7f4d-zld4m          1/1     Running     0               40h
notification-controller-58cfb55954-xr7nc       1/1     Running     0               40h
pool-1-tf-runner                               1/1     Running     0               51s
source-controller-6c64896f47-q8z96             1/1     Running     0               40h
tf-controller-7b8cb5d4-m2cdx                   1/1     Running     0               40h
```

두 가지를 주목해서 살펴 본다.

1. **`pool-1-tf-runner`**: AGE가 51s로 매우 짧다. tf-controller가 기존 `pool-1` 테넌트의 Terraform CRD를 주기적으로 reconcile하면서 띄운 runner Pod다. plan/apply가 끝나면 종료되므로 AGE가 항상 짧은 것이 정상이다.
2. **`ecr-credentials-sync-29619810-4dr8f`**: STATUS가 `Completed`이고, 이름 끝에 숫자+해시가 붙어 있다. 이것은 컨트롤러가 아니라 **CronJob이 주기적으로 띄우는 Job Pod**다. ECR(Elastic Container Registry) 인증 토큰은 12시간마다 만료되는데, Flux의 source-controller나 helm-controller가 ECR에서 이미지와 차트를 pull하려면 유효한 토큰이 필요하다. 이 CronJob이 5분마다 실행되어 `ecr-credentials` Secret을 갱신한다.
    ```bash
    $ kubectl get cronjob -n flux-system ecr-credentials-sync
    NAME                   SCHEDULE      SUSPEND   ACTIVE   LAST SCHEDULE   AGE
    ecr-credentials-sync   */5 * * * *   False     0        2m2s            41h
    ```

<br>

# Terraform CRD 생성

`example-tenant`를 위한 Terraform CRD 파일을 만들어 보자.

## CRD 매니페스트 작성

`application-plane/production/tenants/` 경로에 `example-tenant-terraform-crd.yaml`을 생성한다.

```yaml
---
apiVersion: infra.contrib.fluxcd.io/v1alpha2
kind: Terraform
metadata:
  name: example-tenant
  namespace: flux-system
spec:
  path: ./terraform/modules/tenant-apps
  interval: 1m
  approvePlan: auto
  destroyResourcesOnDeletion: true
  sourceRef:
    kind: GitRepository
    name: terraform-v0-0-1
  vars:
    - name: tenant_id
      value: example-tenant
    - name: "enable_producer"
      value: true
    - name: "enable_consumer"
      value: true
  writeOutputsToSecret:
    name: example-tenant-infra-output
```

주요 필드를 살펴보면 다음과 같다.

| 필드 | 값 | 의미 |
|------|-----|------|
| `spec.path` | `./terraform/modules/tenant-apps` | Git 저장소 내 Terraform 모듈 경로 |
| `spec.sourceRef` | `GitRepository/terraform-v0-0-1` | 모듈을 가져올 Git 소스 |
| `spec.vars` | `tenant_id`, `enable_producer`, `enable_consumer` | 모듈에 전달할 변수 |
| `spec.approvePlan` | `auto` | plan 결과를 자동 승인하여 바로 apply |
| `spec.destroyResourcesOnDeletion` | `true` | CRD 삭제 시 `terraform destroy` 자동 실행 |
| `spec.writeOutputsToSecret` | `example-tenant-infra-output` | apply 결과(output)를 K8s Secret에 저장 |

`approvePlan: auto`는 plan 결과를 사람이 확인하지 않고 바로 apply하겠다는 뜻이다. 실습 환경에서는 편리하지만, 프로덕션에서는 승인 절차를 두는 것이 안전하다.

## sourceRef 확인

`sourceRef`가 가리키는 `terraform-v0-0-1`은 Git 태그 `v0.0.1`을 참조하는 GitRepository 리소스다.

```bash
$ kubectl get GitRepository terraform-v0-0-1 -n flux-system -o yaml
```

<details markdown="1">
<summary><b>전체 출력</b></summary>

```yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: terraform-v0-0-1
  namespace: flux-system
  labels:
    kustomize.toolkit.fluxcd.io/name: sources
    kustomize.toolkit.fluxcd.io/namespace: flux-system
spec:
  interval: 300s
  ref:
    tag: v0.0.1
  secretRef:
    name: flux-system
  timeout: 60s
  url: http://10.x.x.x:3000/admin/eks-saas-gitops.git
status:
  artifact:
    revision: v0.0.1@sha1:2d19a84a88a6ded7c9aa8ac76508452e3f1d48b2
  conditions:
    - reason: Succeeded
      status: "True"
      type: Ready
```

</details>

핵심은 `spec.ref.tag: v0.0.1`이다. tf-controller는 이 GitRepository를 통해 태그 `v0.0.1` 시점의 Terraform 모듈 코드를 pull하여 사용한다. 태그가 고정되어 있으므로 모듈 버전이 의도치 않게 변경될 걱정은 없다.

```bash
$ git tag
v0.0.1
```

## kustomization.yaml에 등록

CRD 파일을 만들었다고 끝이 아니다. `kustomization.yaml`에 새 파일을 등록해야 Flux가 인식한다. [Flux 아키텍처 분석]({% post_url 2026-04-16-Kubernetes-EKS-GitOps-Saas-02-00-02-Cluster-Flux-Architecture %}) 포스트에서 살펴본 것처럼, Kustomize의 `resources` 목록에 없는 파일은 폴더에 존재하더라도 Flux가 무시한다.

```yaml
# application-plane/production/tenants/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - basic
  - advanced
  - premium
  - example-tenant-terraform-crd.yaml  # 추가
```

![kustomization.yaml에 CRD 등록]({{site.url}}/assets/images/eks-w6-kustomization-add-crd.png){: .align-center}

<br>

# Git Push 및 Flux 조정

## 변경 사항 커밋 및 푸시

작성한 CRD 파일과 수정한 `kustomization.yaml`을 Git에 push한다.

```bash
$ cd /home/ec2-user/environment/gitops-gitea-repo/
$ git add .
$ git commit -m "Added example terraform CRD for testing"
$ git push origin main
```

## Flux reconcile 트리거

Flux는 기본적으로 `interval`에 설정된 주기마다 Git 변경을 감지하지만, 즉시 반영하고 싶다면 수동으로 reconcile을 트리거할 수 있다.

```bash
$ flux reconcile source git flux-system
► annotating GitRepository flux-system in flux-system namespace
✔ GitRepository annotated
◎ waiting for GitRepository reconciliation
✔ fetched revision refs/heads/main@sha1:c4c06b2bd36014dae4e3dfeb2f3b50c50e9c8ec6
```

## tf-runner Pod 생성 확인

reconcile이 완료되면 tf-controller가 새로 추가된 Terraform CRD를 감지하고, `example-tenant-tf-runner` Pod를 생성한다.

```
Flux Kustomization(dataplane-tenants)
  → Terraform CRD(example-tenant) 감지
    → tf-controller
      → Pod/example-tenant-tf-runner 생성
```

여기서 Flux의 역할과 tf-controller의 역할을 구분할 필요가 있다. Flux는 tf-controller라는 도구를 HelmRelease로 설치한 주체일 뿐이고, **tf-runner Pod를 직접 띄우는 것은 tf-controller**다.

| 계층 | 역할 | 생성 주체 |
|------|------|-----------|
| HelmRelease/tf-controller | tf-controller 설치 선언 | Flux Kustomization(infrastructure) |
| Deployment/tf-controller | tf-controller 본체 (상시) | helm-controller가 차트를 풀어서 생성 |
| **Pod/example-tenant-tf-runner** | **terraform plan/apply 실행기 (1회성)** | **tf-controller가 Terraform CRD를 보고 직접 생성** |

tf-runner Pod는 IRSA(IAM Roles for Service Accounts)가 연결된 `tf-runner` ServiceAccount로 실행되며, 이를 통해 AWS API(SQS, DynamoDB, IAM 생성)에 대한 권한을 얻는다.

```bash
$ kubectl get po -n flux-system -l app.kubernetes.io/name=tf-runner
NAME                       READY   STATUS    RESTARTS   AGE
example-tenant-tf-runner   1/1     Running   0          18s
```

## tf-runner 로그 모니터링

tf-runner Pod의 로그를 보면 Terraform이 실행되는 전체 과정을 확인할 수 있다.

```bash
$ kubectl logs po/example-tenant-tf-runner -n flux-system -f
```

핵심 로그를 단계별로 발췌하면 다음과 같다.

**init 단계** — Terraform 초기화:

```text
{"logger":"runner.terraform","msg":"initializing","instance-id":"..."}
```

**plan 단계** — 변경 계획 생성:

```text
{"logger":"runner.terraform","msg":"creating a plan","instance-id":"..."}
{"logger":"runner.terraform","msg":"save the plan","instance-id":"..."}
```

**apply 단계** — 리소스 생성:

```text
{"logger":"runner.terraform","msg":"running apply","instance-id":"..."}
random_string.random_suffix: Creating...
random_string.random_suffix: Creation complete after 0s [id=s2v]
aws_sqs_queue.consumer_sqs[0]: Creating...
module.producer_irsa_role[0].aws_iam_role.this[0]: Creating...
module.consumer_irsa_role[0].aws_iam_role.this[0]: Creating...
aws_dynamodb_table.consumer_ddb[0]: Creating...
# ... (중간 생략) ...
Apply complete! Resources: 11 added, 0 changed, 0 destroyed.
```

**outputs 단계** — 결과 저장:

```text
Outputs:

consumer = {
  "irsa_role" = "arn:aws:iam::123456789012:role/consumer-role-example-tenant"
}
producer = {
  "irsa_role" = "arn:aws:iam::123456789012:role/producer-role-example-tenant"
}
{"logger":"runner.terraform","msg":"write outputs to secret","instance-id":"..."}
{"logger":"runner.terraform","msg":"cleanup TmpDir","instance-id":"..."}
```

총 11개의 AWS 리소스가 생성되었다. 이전 포스트에서 `terraform plan`으로 확인했던 것과 동일한 리소스(SQS, DynamoDB, IAM Role, IAM Policy, SSM Parameter 등)가 만들어진 것이다.

![tf-runner apply 로그]({{site.url}}/assets/images/eks-w6-tf-runner-apply-logs.png){: .align-center}

<details markdown="1">
<summary><b>tf-runner 전체 로그 (apply)</b></summary>

```text
Starting the runner... version  sha
{"level":"info","ts":"...","logger":"runner.terraform","msg":"preparing for Upload and Extraction","instance-id":""}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"write backend config","instance-id":"","path":"/tmp/flux-system-example-tenant/terraform/modules/tenant-apps","config":"backend_override.tf"}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"write config to file","instance-id":"","filePath":"/tmp/flux-system-example-tenant/terraform/modules/tenant-apps/backend_override.tf"}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"looking for path","instance-id":"","file":"terraform"}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"creating new terraform","instance-id":"...","workingDir":"/tmp/flux-system-example-tenant/terraform/modules/tenant-apps","execPath":"/usr/local/bin/terraform"}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"setting envvars","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"getting envvars from os environments","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"setting up the input variables","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"mapping the Spec.Values","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"mapping the Spec.Vars","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"mapping the Spec.VarsFrom","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"generating the template founds"}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"main.tf.tpl not found, skipping"}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"initializing","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"mapping the Spec.BackendConfigsFrom","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"workspace select"}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"creating a plan","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"save the plan","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"loading plan from secret","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"running apply","instance-id":"..."}
random_string.random_suffix: Creating...
random_string.random_suffix: Creation complete after 0s [id=s2v]
aws_sqs_queue.consumer_sqs[0]: Creating...
module.producer_irsa_role[0].aws_iam_role.this[0]: Creating...
module.consumer_irsa_role[0].aws_iam_role.this[0]: Creating...
aws_dynamodb_table.consumer_ddb[0]: Creating...
module.producer_irsa_role[0].aws_iam_role.this[0]: Creation complete after 0s [id=producer-role-example-tenant]
module.consumer_irsa_role[0].aws_iam_role.this[0]: Creation complete after 0s [id=consumer-role-example-tenant]
aws_dynamodb_table.consumer_ddb[0]: Creation complete after 7s [id=consumer-example-tenant-s2v]
aws_ssm_parameter.dedicated_consumer_ddb[0]: Creating...
aws_ssm_parameter.dedicated_consumer_ddb[0]: Creation complete after 0s [id=/example-tenant/consumer_ddb]
aws_sqs_queue.consumer_sqs[0]: Still creating... [10s elapsed]
aws_sqs_queue.consumer_sqs[0]: Still creating... [20s elapsed]
aws_sqs_queue.consumer_sqs[0]: Creation complete after 25s [id=https://sqs.ap-northeast-2.amazonaws.com/123456789012/consumer-example-tenant-s2v]
aws_ssm_parameter.dedicated_consumer_sqs[0]: Creating...
aws_ssm_parameter.dedicated_consumer_sqs[0]: Creation complete after 0s [id=/example-tenant/consumer_sqs]
aws_iam_policy.producer-iampolicy[0]: Creating...
aws_iam_policy.consumer-iampolicy[0]: Creating...
aws_iam_policy.producer-iampolicy[0]: Creation complete after 0s [id=arn:aws:iam::123456789012:policy/producer-policy-example-tenant]
aws_iam_policy.consumer-iampolicy[0]: Creation complete after 0s [id=arn:aws:iam::123456789012:policy/consumer-policy-example-tenant]
module.producer_irsa_role[0].aws_iam_role_policy_attachment.this["policy"]: Creating...
module.consumer_irsa_role[0].aws_iam_role_policy_attachment.this["policy"]: Creating...
module.producer_irsa_role[0].aws_iam_role_policy_attachment.this["policy"]: Creation complete after 0s [id=producer-role-example-tenant/arn:aws:iam::123456789012:policy/producer-policy-example-tenant]
module.consumer_irsa_role[0].aws_iam_role_policy_attachment.this["policy"]: Creation complete after 0s [id=consumer-role-example-tenant/arn:aws:iam::123456789012:policy/consumer-policy-example-tenant]

Apply complete! Resources: 11 added, 0 changed, 0 destroyed.

Outputs:

consumer = {
  "irsa_role" = "arn:aws:iam::123456789012:role/consumer-role-example-tenant"
}
producer = {
  "irsa_role" = "arn:aws:iam::123456789012:role/producer-role-example-tenant"
}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"creating outputs","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"write outputs to secret","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"cleanup TmpDir","instance-id":"...","tmpDir":"/tmp/flux-system-example-tenant"}
```

</details>

<br>

# AWS 리소스 검증

tf-runner가 생성한 AWS 리소스를 직접 확인해 보자.

## DynamoDB 테이블

```bash
$ aws dynamodb list-tables
{
    "TableNames": [
        "consumer-example-tenant-s2v",
        "consumer-pool-1-bbi"
    ]
}
```

기존에 `pool-1` 테넌트의 테이블만 있었는데, `consumer-example-tenant-s2v`가 새로 추가되었다.

![DynamoDB 테이블 생성 확인]({{site.url}}/assets/images/eks-w6-dynamodb-created.png){: .align-center}

## SQS 큐

```bash
$ aws sqs list-queues
{
    "QueueUrls": [
        "https://sqs.ap-northeast-2.amazonaws.com/123456789012/argoworkflows-deployment-queue",
        "https://sqs.ap-northeast-2.amazonaws.com/123456789012/argoworkflows-offboarding-queue",
        "https://sqs.ap-northeast-2.amazonaws.com/123456789012/argoworkflows-onboarding-queue",
        "https://sqs.ap-northeast-2.amazonaws.com/123456789012/consumer-example-tenant-s2v",
        "https://sqs.ap-northeast-2.amazonaws.com/123456789012/consumer-pool-1-bbi",
        "https://sqs.ap-northeast-2.amazonaws.com/123456789012/eks-saas-gitops"
    ]
}
```

마찬가지로 `consumer-example-tenant-s2v` 큐가 새로 생성되었다.

![SQS 큐 생성 확인]({{site.url}}/assets/images/eks-w6-sqs-created.png){: .align-center}

<br>

# GitOps 방식의 리소스 삭제

생성을 확인했으니 이제 삭제다. GitOps에서 리소스 삭제는 **파일 삭제**로 수행한다. CRD에 `destroyResourcesOnDeletion: true`를 설정해 두었기 때문에, CRD가 클러스터에서 사라지면 tf-controller가 `terraform destroy`를 실행하여 AWS 리소스까지 정리한다.

## CRD 파일 삭제 및 kustomization.yaml 수정

```bash
$ rm application-plane/production/tenants/example-tenant-terraform-crd.yaml
```

`kustomization.yaml`에서도 참조를 제거한다.

```yaml
# application-plane/production/tenants/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - basic
  - advanced
  - premium
  # example-tenant-terraform-crd.yaml 제거됨
```

## 커밋, 푸시, reconcile

```bash
$ git add .
$ git commit -m "Removed Terraform CRD and reference from kustomization.yaml"
$ git push origin main
$ flux reconcile source git flux-system
► annotating GitRepository flux-system in flux-system namespace
✔ GitRepository annotated
◎ waiting for GitRepository reconciliation
✔ fetched revision refs/heads/main@sha1:531e8336e2a508a53fe70a69374549d50902b137
```

![Gitea에서 CRD 파일 삭제 확인]({{site.url}}/assets/images/eks-w6-gitea-crd-removed.png){: .align-center}

## tf-runner destroy 로그 확인

reconcile이 완료되면 tf-controller가 CRD 삭제를 감지하고, 다시 tf-runner Pod를 띄워 `terraform destroy`를 실행한다.

```bash
$ kubectl logs po/example-tenant-tf-runner -n flux-system -f
```

핵심 로그를 발췌하면 다음과 같다.

```text
{"logger":"runner.terraform","msg":"running apply","instance-id":"..."}
module.consumer_irsa_role[0].aws_iam_role_policy_attachment.this["policy"]: Destroying...
module.producer_irsa_role[0].aws_iam_role_policy_attachment.this["policy"]: Destroying...
aws_iam_policy.consumer-iampolicy[0]: Destroying...
module.consumer_irsa_role[0].aws_iam_role.this[0]: Destroying...
aws_iam_policy.producer-iampolicy[0]: Destroying...
module.producer_irsa_role[0].aws_iam_role.this[0]: Destroying...
aws_ssm_parameter.dedicated_consumer_ddb[0]: Destroying...
aws_dynamodb_table.consumer_ddb[0]: Destroying...
aws_ssm_parameter.dedicated_consumer_sqs[0]: Destroying...
aws_sqs_queue.consumer_sqs[0]: Destroying...
random_string.random_suffix: Destroying...

Apply complete! Resources: 0 added, 0 changed, 11 destroyed.
```

생성할 때와 정확히 대칭적으로, 11개 리소스가 모두 삭제되었다.

<details markdown="1">
<summary><b>tf-runner 전체 로그 (destroy)</b></summary>

```text
Starting the runner... version  sha
{"level":"info","ts":"...","logger":"runner.terraform","msg":"preparing for Upload and Extraction","instance-id":""}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"write backend config","instance-id":"","path":"/tmp/flux-system-example-tenant/terraform/modules/tenant-apps","config":"backend_override.tf"}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"write config to file","instance-id":"","filePath":"/tmp/flux-system-example-tenant/terraform/modules/tenant-apps/backend_override.tf"}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"looking for path","instance-id":"","file":"terraform"}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"creating new terraform","instance-id":"...","workingDir":"/tmp/flux-system-example-tenant/terraform/modules/tenant-apps","execPath":"/usr/local/bin/terraform"}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"setting envvars","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"getting envvars from os environments","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"setting up the input variables","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"mapping the Spec.Values","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"mapping the Spec.Vars","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"mapping the Spec.VarsFrom","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"generating the template founds"}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"main.tf.tpl not found, skipping"}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"initializing","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"mapping the Spec.BackendConfigsFrom","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"workspace select"}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"creating a plan","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"save the plan","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"loading plan from secret","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"running apply","instance-id":"..."}
module.consumer_irsa_role[0].aws_iam_role_policy_attachment.this["policy"]: Destroying... [id=consumer-role-example-tenant/arn:aws:iam::123456789012:policy/consumer-policy-example-tenant]
module.producer_irsa_role[0].aws_iam_role_policy_attachment.this["policy"]: Destroying... [id=producer-role-example-tenant/arn:aws:iam::123456789012:policy/producer-policy-example-tenant]
module.consumer_irsa_role[0].aws_iam_role_policy_attachment.this["policy"]: Destruction complete after 0s
aws_iam_policy.consumer-iampolicy[0]: Destroying... [id=arn:aws:iam::123456789012:policy/consumer-policy-example-tenant]
module.consumer_irsa_role[0].aws_iam_role.this[0]: Destroying... [id=consumer-role-example-tenant]
module.producer_irsa_role[0].aws_iam_role_policy_attachment.this["policy"]: Destruction complete after 0s
aws_iam_policy.producer-iampolicy[0]: Destroying... [id=arn:aws:iam::123456789012:policy/producer-policy-example-tenant]
module.producer_irsa_role[0].aws_iam_role.this[0]: Destroying... [id=producer-role-example-tenant]
aws_iam_policy.consumer-iampolicy[0]: Destruction complete after 1s
aws_ssm_parameter.dedicated_consumer_ddb[0]: Destroying... [id=/example-tenant/consumer_ddb]
aws_ssm_parameter.dedicated_consumer_ddb[0]: Destruction complete after 0s
aws_dynamodb_table.consumer_ddb[0]: Destroying... [id=consumer-example-tenant-s2v]
aws_iam_policy.producer-iampolicy[0]: Destruction complete after 1s
aws_ssm_parameter.dedicated_consumer_sqs[0]: Destroying... [id=/example-tenant/consumer_sqs]
aws_ssm_parameter.dedicated_consumer_sqs[0]: Destruction complete after 0s
aws_sqs_queue.consumer_sqs[0]: Destroying... [id=https://sqs.ap-northeast-2.amazonaws.com/123456789012/consumer-example-tenant-s2v]
module.consumer_irsa_role[0].aws_iam_role.this[0]: Destruction complete after 2s
module.producer_irsa_role[0].aws_iam_role.this[0]: Destruction complete after 2s
aws_dynamodb_table.consumer_ddb[0]: Destruction complete after 7s
aws_sqs_queue.consumer_sqs[0]: Still destroying... [10s elapsed]
aws_sqs_queue.consumer_sqs[0]: Still destroying... [20s elapsed]
aws_sqs_queue.consumer_sqs[0]: Still destroying... [30s elapsed]
aws_sqs_queue.consumer_sqs[0]: Still destroying... [40s elapsed]
aws_sqs_queue.consumer_sqs[0]: Still destroying... [50s elapsed]
aws_sqs_queue.consumer_sqs[0]: Still destroying... [1m0s elapsed]
aws_sqs_queue.consumer_sqs[0]: Still destroying... [1m10s elapsed]
aws_sqs_queue.consumer_sqs[0]: Still destroying... [1m20s elapsed]
aws_sqs_queue.consumer_sqs[0]: Still destroying... [1m30s elapsed]
aws_sqs_queue.consumer_sqs[0]: Still destroying... [1m40s elapsed]
aws_sqs_queue.consumer_sqs[0]: Still destroying... [1m50s elapsed]
aws_sqs_queue.consumer_sqs[0]: Still destroying... [2m0s elapsed]
aws_sqs_queue.consumer_sqs[0]: Destruction complete after 2m10s
random_string.random_suffix: Destroying... [id=s2v]
random_string.random_suffix: Destruction complete after 0s

Apply complete! Resources: 0 added, 0 changed, 11 destroyed.
{"level":"info","ts":"...","logger":"runner.terraform","msg":"finalize the output secrets","instance-id":"..."}
{"level":"info","ts":"...","logger":"runner.terraform","msg":"cleanup TmpDir","instance-id":"...","tmpDir":"/tmp/flux-system-example-tenant"}
```

</details>

## AWS 리소스 삭제 확인

```bash
$ aws dynamodb list-tables
{
    "TableNames": [
        "consumer-pool-1-bbi"
    ]
}
```

`consumer-example-tenant-*` 테이블이 사라졌다.

```bash
$ aws sqs list-queues
{
    "QueueUrls": [
        "https://sqs.ap-northeast-2.amazonaws.com/123456789012/argoworkflows-deployment-queue",
        "https://sqs.ap-northeast-2.amazonaws.com/123456789012/argoworkflows-offboarding-queue",
        "https://sqs.ap-northeast-2.amazonaws.com/123456789012/argoworkflows-onboarding-queue",
        "https://sqs.ap-northeast-2.amazonaws.com/123456789012/consumer-pool-1-bbi",
        "https://sqs.ap-northeast-2.amazonaws.com/123456789012/eks-saas-gitops"
    ]
}
```

`consumer-example-tenant-*` 큐도 사라졌다. **파일을 추가하면 인프라가 생기고, 파일을 삭제하면 인프라가 사라진다.** Git이 Single Source of Truth라는 GitOps의 핵심 원칙이 그대로 적용된 것이다.

<br>

# "인프라 배포" vs "앱 배포"

이번 실습에서 정확히 무엇을 했는지 정리할 필요가 있다.

## 이번 실습에서 한 일

Terraform CRD를 Git에 push하여 `example-tenant`를 위한 **AWS 인프라**(SQS, DynamoDB, IAM Role, IAM Policy, SSM Parameter)만 생성하고 삭제했다. 테넌트에 대한 HelmRelease(앱 배포)는 추가하지 않았다.

## 인프라 추가 vs 앱 버전 업데이트

두 흐름 모두 "Git push하면 Flux가 감지하여 자동 반영"이라는 패턴은 동일하지만, push하는 내용과 결과가 다르다.

| | 인프라 배포 (이번 실습) | 앱 배포 (이후 실습) |
|---|---|---|
| Git에 push하는 것 | Terraform CRD YAML | 소스 코드 변경 |
| Flux가 하는 일 | Tofu Controller로 인프라 생성 | HelmRelease로 Pod 재배포 |
| 결과 | AWS 리소스 생성 | 새 버전 컨테이너 배포 |

## 현재 상태

환경 세팅 시 `install.sh`가 이미 `pool-1` 테넌트에 대한 인프라와 앱을 함께 배포해 두었다. 이번 실습에서는 `example-tenant`의 인프라만 추가했다가 다시 삭제한 것이다.

```
install.sh 실행 시 이미 만들어진 것:
├── pool-1 네임스페이스
│   ├── Producer Pod (공유)       ← HelmRelease/pool-1로 배포
│   ├── Consumer Pod (공유)       ← HelmRelease/pool-1로 배포
│   ├── 공유 SQS 큐              ← Terraform CRD(pool-1)로 생성
│   └── 공유 DynamoDB 테이블      ← Terraform CRD(pool-1)로 생성
```

```
실습 전:  pool-1(앱+인프라)
실습 후:  pool-1(앱+인프라) + example-tenant(인프라만) → 삭제됨
```

이후 실습에서 테넌트에 대한 HelmRelease까지 추가하면, 그때 비로소 **인프라 + 앱이 완성된 테넌트 환경**이 된다.

<br>

# 정리

이번 포스트에서는 Tofu Controller를 통해 GitOps 기반 인프라 배포의 전체 사이클(생성, 검증, 삭제)을 경험했다.

## 핵심 설정값

| 설정 | 값 | 의미 |
|------|-----|------|
| `approvePlan` | `auto` | plan 자동 승인 후 apply |
| `destroyResourcesOnDeletion` | `true` | CRD 삭제 시 `terraform destroy` 자동 실행 |
| `writeOutputsToSecret` | Secret 이름 | apply 결과를 K8s Secret에 저장 |
| `sourceRef` | GitRepository 참조 | Terraform 모듈을 가져올 Git 소스 |
| `interval` | `1m` | reconcile 주기 |

`destroyResourcesOnDeletion: true`는 편리하지만 양면성이 있다. 의도적으로 테넌트를 오프보딩할 때는 파일 삭제만으로 인프라까지 깔끔하게 정리되어 편리하다. 반면, 실수로 파일을 삭제하거나 잘못된 브랜치를 push하면 프로덕션 인프라가 날아갈 수 있다. 프로덕션 환경에서는 브랜치 보호 규칙(branch protection)이나 별도의 승인 절차를 반드시 함께 구성해야 한다.

## GitOps 사이클 요약

```
[생성]  YAML 추가 → git push → Flux 감지 → tf-controller → terraform apply → AWS 리소스 생성
[삭제]  YAML 삭제 → git push → Flux 감지 → tf-controller → terraform destroy → AWS 리소스 삭제
```

두 흐름이 완전히 대칭적이다. "어떤 인프라가 존재해야 하는가"를 Git에 선언하면, 클러스터가 그 상태를 자동으로 맞춘다.

이번 실습에서는 테넌트 인프라만 다루었다. 다음 실습에서는 HelmRelease를 추가하여 테넌트에 실제 SaaS 앱(Producer, Consumer)을 배포하는 과정을 살펴볼 예정이다.

<br>
