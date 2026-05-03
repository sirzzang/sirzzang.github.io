---
title: "[EKS] GitOps 기반 SaaS: 클러스터 환경 확인 - 1. Flux 리소스 개요"
excerpt: "실습 환경에 이미 배포된 네임스페이스와 Flux 리소스를 확인하고, Gitea 저장소 접근을 설정하자."
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
  - Flux
  - GitOps
  - Gitea
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-6
---

*[최영락](https://www.linkedin.com/in/ianychoi/)님의 AWS EKS Workshop Study(AEWS) 6주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- 실습 환경에는 EKS 클러스터, ECR, Gitea, Flux 등이 이미 프로비저닝되어 있다
- `flux get all`로 Flux가 관리하는 전체 리소스(GitRepository, HelmRepository, HelmRelease, Kustomization 등)를 한눈에 확인할 수 있다
- Flux 리소스는 소스(Source) → 배포(HelmRelease/Kustomization) → 이미지 자동화(ImageUpdateAutomation)의 계층 구조를 이룬다
- Gitea 저장소 접근을 설정하고 마이크로서비스 저장소(producer, consumer, payments)를 복제하여 실습 준비를 완료한다

<br>

# 사전 프로비저닝된 리소스 확인

[이전 포스트]({% post_url 2026-04-16-Kubernetes-EKS-GitOps-Saas-01-01-04-Installation-Result %})에서 CloudFormation으로 실습 환경 설치를 완료했다. 이번에는 설치 스크립트가 무엇을 만들었는지 확인해 보자.


## 주요 구성 요소

설치가 완료된 후, 다음 리소스가 이미 프로비저닝되어 있다.

| 구성 요소 | 설명 |
| --- | --- |
| Amazon EKS 클러스터 | Flux, Argo Workflows 등 애드온 포함 |
| Amazon ECR | 애플리케이션 컨테이너 이미지 및 Helm 차트 저장소 |
| Gitea 저장소 | GitOps 릴리스, 앱 템플릿, 마이크로서비스 코드 |
| AWS 리소스 | 정상 작동을 위한 네트워킹, IAM 등 |

## 네임스페이스 확인

`kubectl get ns` 명령으로 클러스터에 생성된 네임스페이스를 확인한다.

```bash
$ kubectl get ns
NAME                 STATUS   AGE
argo-events          Active   35h
argo-workflows       Active   35h
aws-system           Active   35h
default              Active   36h
flux-system          Active   36h
karpenter            Active   35h
kube-node-lease      Active   36h
kube-public          Active   36h
kube-system          Active   36h
kubecost             Active   35h
onboarding-service   Active   35h
pool-1               Active   35h
```

기본 네임스페이스(`default`, `kube-system`, `kube-node-lease`, `kube-public`)를 제외한 주요 네임스페이스의 역할은 다음과 같다.

| 네임스페이스 | 역할 |
| --- | --- |
| `flux-system` | Flux 컨트롤러와 GitOps 파이프라인 관리 |
| `argo-events` | 이벤트 기반 워크플로우 트리거 |
| `argo-workflows` | CI/CD 파이프라인 실행 엔진 |
| `aws-system` | AWS Load Balancer Controller 등 AWS 연동 컴포넌트 |
| `karpenter` | 노드 오토스케일링 |
| `kubecost` | 비용 모니터링 |
| `onboarding-service` | 테넌트 온보딩 서비스 |
| `pool-1` | 멀티 테넌트 풀 환경 (공유 네임스페이스) |

<br>

# Flux 리소스 전체 조회

Flux는 이 SaaS 솔루션의 핵심 엔진이다. Git 저장소와 ECR의 변경 사항을 감시하여, 클러스터 상태를 선언된 상태와 일치시키는 역할을 한다. `flux get all` 명령으로 Flux가 관리하는 전체 리소스를 확인할 수 있다.

## 리소스 유형별 확인

`flux get all` 출력은 리소스 유형별로 구분되어 있다. 각 유형에서 핵심만 발췌하면 다음과 같다.

모든 리소스가 `READY=True` 상태인 것을 확인할 수 있다.

<details markdown="1">
<summary><b>flux get all 전체 출력</b></summary>

```text
$ flux get all
NAME                    REVISION                SUSPENDED       READY   MESSAGE
ocirepository/capacitor v0.4.8@sha256:1efcb443  False           True    stored artifact for digest 'v0.4.8@sha256:1efcb443'

NAME                            REVISION                        SUSPENDED       READY   MESSAGE
gitrepository/flux-system       refs/heads/main@sha1:b792d408   False           True    stored artifact for revision 'refs/heads/main@sha1:b792d408'
gitrepository/terraform-v0-0-1  v0.0.1@sha1:2d19a84a            False           True    stored artifact for revision 'v0.0.1@sha1:2d19a84a'

NAME                                    REVISION        SUSPENDED       READY   MESSAGE
helmrepository/argo                     sha256:77d58f2f False           True    stored artifact: revision 'sha256:77d58f2f'
helmrepository/eks-charts               sha256:d5d7cd31 False           True    stored artifact: revision 'sha256:d5d7cd31'
helmrepository/helm-application-chart                   False           True    Helm repository is Ready
helmrepository/helm-tenant-chart                        False           True    Helm repository is Ready
helmrepository/karpenter                                False           True    Helm repository is Ready
helmrepository/kubecost                                 False           True    Helm repository is Ready
helmrepository/metrics-server           sha256:ba69c5bb False           True    stored artifact: revision 'sha256:ba69c5bb'
helmrepository/tf-controller            sha256:1fcad0f6 False           True    stored artifact: revision 'sha256:1fcad0f6'

NAME                                                    REVISION        SUSPENDED       READY   MESSAGE
helmchart/flux-system-argo-events                       2.4.3           False           True    pulled 'argo-events' chart with version '2.4.3'
helmchart/flux-system-argo-workflows                    0.40.11         False           True    pulled 'argo-workflows' chart with version '0.40.11'
helmchart/flux-system-aws-load-balancer-controller      1.6.2           False           True    pulled 'aws-load-balancer-controller' chart with version '1.6.2'
helmchart/flux-system-karpenter                         1.4.0           False           True    pulled 'karpenter' chart with version '1.4.0'
helmchart/flux-system-kubecost                          2.1.0           False           True    pulled 'cost-analyzer' chart with version '2.1.0'
helmchart/flux-system-metrics-server                    3.11.0          False           True    pulled 'metrics-server' chart with version '3.11.0'
helmchart/flux-system-onboarding-service                0.0.1           False           True    pulled 'application-chart' chart with version '0.0.1'
helmchart/flux-system-pool-1                            0.0.1           False           True    pulled 'helm-tenant-chart' chart with version '0.0.1'
helmchart/flux-system-tf-controller                     0.16.0-rc.4     False           True    pulled 'tf-controller' chart with version '0.16.0-rc.4'

NAME                                            LAST SCAN               SUSPENDED       READY   MESSAGE
imagerepository/consumer-image-repository       2026-04-26T02:40:08Z    False           True    successful scan: found 2 tags
imagerepository/payments-image-repository       2026-04-26T02:40:08Z    False           True    successful scan: found 2 tags
imagerepository/producer-image-repository       2026-04-26T02:40:08Z    False           True    successful scan: found 2 tags

NAME                                    IMAGE                                                            TAG                     READY   MESSAGE
imagepolicy/consumer-image-policy       123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/consumer       prd-20260424T144014Z    True    Latest image tag for ... resolved to prd-20260424T144014Z
imagepolicy/payments-image-policy       123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/payments       prd-20260424T143957Z    True    Latest image tag for ... resolved to prd-20260424T143957Z
imagepolicy/producer-image-policy       123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/producer       prd-20260424T144033Z    True    Latest image tag for ... resolved to prd-20260424T144033Z

NAME                                                            LAST RUN                SUSPENDED       READY   MESSAGE
imageupdateautomation/consumer-update-automation-pooled-envs    2026-04-26T02:36:46Z    False           True    repository up-to-date
imageupdateautomation/consumer-update-automation-tenants        2026-04-26T02:40:10Z    False           True    repository up-to-date
imageupdateautomation/payments-update-automation-pooled-envs    2026-04-26T02:36:45Z    False           True    repository up-to-date
imageupdateautomation/payments-update-automation-tenants        2026-04-26T02:40:09Z    False           True    repository up-to-date
imageupdateautomation/producer-update-automation-pooled-envs    2026-04-26T02:36:46Z    False           True    repository up-to-date
imageupdateautomation/producer-update-automation-tenants        2026-04-26T02:40:10Z    False           True    repository up-to-date

NAME                                            REVISION        SUSPENDED       READY   MESSAGE
helmrelease/argo-events                         2.4.3           False           True    Helm install succeeded for release argo-events/argo-events.v1 with chart argo-events@2.4.3
helmrelease/argo-workflows                      0.40.11         False           True    Helm install succeeded for release argo-workflows/argo-workflows.v1 with chart argo-workflows@0.40.11
helmrelease/aws-load-balancer-controller        1.6.2           False           True    Helm install succeeded for release aws-system/aws-load-balancer-controller.v1 with chart aws-load-balancer-controller@1.6.2
helmrelease/karpenter                           1.4.0           False           True    Helm install succeeded for release karpenter/karpenter.v1 with chart karpenter@1.4.0
helmrelease/kubecost                            2.1.0           False           True    Helm install succeeded for release kubecost/kubecost.v1 with chart cost-analyzer@2.1.0
helmrelease/metrics-server                      3.11.0          False           True    Helm install succeeded for release kube-system/metrics-server.v1 with chart metrics-server@3.11.0
helmrelease/onboarding-service                  0.0.1           False           True    Helm install succeeded for release onboarding-service/onboarding-service.v1 with chart application-chart@0.0.1
helmrelease/pool-1                              0.0.1           False           True    Helm upgrade succeeded for release pool-1/pool-1.v2 with chart helm-tenant-chart@0.0.1
helmrelease/tf-controller                       0.16.0-rc.4     False           True    Helm install succeeded for release flux-system/tf-controller.v1 with chart tf-controller@0.16.0-rc.4

NAME                                    REVISION                        SUSPENDED       READY   MESSAGE
kustomization/capacitor                 v0.4.8@sha256:1efcb443          False           True    Applied revision: v0.4.8@sha256:1efcb443
kustomization/controlplane              refs/heads/main@sha1:b792d408   False           True    Applied revision: refs/heads/main@sha1:b792d408
kustomization/dataplane-pooled-envs     refs/heads/main@sha1:b792d408   False           True    Applied revision: refs/heads/main@sha1:b792d408
kustomization/dataplane-tenants         refs/heads/main@sha1:b792d408   False           True    Applied revision: refs/heads/main@sha1:b792d408
kustomization/dependencies              refs/heads/main@sha1:b792d408   False           True    Applied revision: refs/heads/main@sha1:b792d408
kustomization/flux-system               refs/heads/main@sha1:b792d408   False           True    Applied revision: refs/heads/main@sha1:b792d408
kustomization/infrastructure            refs/heads/main@sha1:b792d408   False           True    Applied revision: refs/heads/main@sha1:b792d408
kustomization/sources                   refs/heads/main@sha1:b792d408   False           True    Applied revision: refs/heads/main@sha1:b792d408
```

</details>

### 소스(Source) 리소스

Flux가 감시하는 대상을 정의한다.

```text
# Git 저장소 소스
NAME                            REVISION                        READY
gitrepository/flux-system       refs/heads/main@sha1:b792d408   True
gitrepository/terraform-v0-0-1  v0.0.1@sha1:2d19a84a            True

# Helm 차트 저장소 (총 8개 중 발췌)
NAME                                    REVISION        READY
helmrepository/argo                     sha256:77d58f2f True
helmrepository/eks-charts               sha256:d5d7cd31 True
helmrepository/karpenter                                True
helmrepository/tf-controller            sha256:1fcad0f6 True
```

### 배포(Deployment) 리소스

소스에서 가져온 차트와 설정을 실제로 클러스터에 배포한다.

```text
# Helm 릴리스 - 실제 배포 단위 (총 9개 중 발췌)
NAME                                     REVISION    READY
helmrelease/argo-events                  2.4.3       True
helmrelease/karpenter                    1.4.0       True
helmrelease/tf-controller                0.16.0-rc.4 True

# Kustomization - GitRepository 기반 구성 관리 (총 8개 중 발췌)
NAME                                REVISION                        READY
kustomization/flux-system           refs/heads/main@sha1:b792d408   True
kustomization/infrastructure        refs/heads/main@sha1:b792d408   True
kustomization/controlplane          refs/heads/main@sha1:b792d408   True
```

### 이미지 자동화(Image Automation) 리소스

ECR의 새 이미지 태그를 감지하고 자동으로 Git에 반영한다.

```text
# 이미지 저장소 감시
NAME                                          LAST SCAN               READY
imagerepository/consumer-image-repository     2026-04-26T02:40:08Z    True
imagerepository/producer-image-repository     2026-04-26T02:40:08Z    True
imagerepository/payments-image-repository     2026-04-26T02:40:08Z    True

# 이미지 자동 업데이트 (총 6개 중 발췌)
NAME                                                         LAST RUN               READY
imageupdateautomation/consumer-update-automation-pooled-envs 2026-04-26T02:36:46Z   True
imageupdateautomation/producer-update-automation-tenants     2026-04-26T02:40:10Z   True
```



## 리소스 유형별 역할 정리

출력에서 확인할 수 있는 Flux 리소스 유형과 역할을 정리하면 다음과 같다.

| 리소스 유형 | 역할 | 수량 |
| --- | --- | --- |
| `gitrepository` | Flux가 변경 사항을 감시하는 Git 저장소 | 2개 |
| `ocirepository` | OCI 아티팩트 저장소 (Capacitor UI) | 1개 |
| `helmrepository` | Helm 차트가 저장된 저장소 위치 (ECR 포함) | 8개 |
| `helmchart` | 각 HelmRepository에서 가져온 Helm 차트 | 9개 |
| `helmrelease` | 실제 배포 단위 (하나의 차트 → 여러 테넌트 배포 가능) | 9개 |
| `kustomization` | GitRepository를 가리키는 진입점, 구성 관리 | 8개 |
| `imagerepository` | ECR 이미지 태그 자동 감시 | 3개 |
| `imagepolicy` | 이미지 태그 선택 정책 | 3개 |
| `imageupdateautomation` | 새 이미지 감지 시 Git에 자동 커밋 | 6개 |

> 여기서 `kustomization`은 `kubectl kustomize`로 알려진 Kustomize 도구가 아니다. Flux의 Kustomization CRD(`kustomize.toolkit.fluxcd.io/v1`)로, GitRepository 등 소스를 클러스터에 적용하는 진입점 역할을 한다.

## HelmRepository 8개 vs HelmRelease 9개

HelmRepository는 8개인데 HelmRelease는 9개로, 수가 일치하지 않는다. HelmRepository는 "차트 저장소(서버)"이고 HelmRelease는 "해당 저장소에서 특정 차트를 골라 설치한 인스턴스"이므로 N:M 관계가 성립한다. 아래 표를 보면, `argo` 저장소 하나에서 차트 2개를 가져오기 때문에 이런 차이가 발생한다.

| HelmRepository | HelmRelease |
| --- | --- |
| **argo** | **argo-events, argo-workflows** (2개) |
| eks-charts | aws-load-balancer-controller |
| helm-application-chart | onboarding-service |
| helm-tenant-chart | pool-1 |
| karpenter | karpenter |
| kubecost | kubecost |
| metrics-server | metrics-server |
| tf-controller | tf-controller |

8개 HelmRepository + `argo`에서 1개 추가 = **9개 HelmRelease**가 된다.

## `flux get all` vs `flux tree`

`flux get all`은 Flux가 관리하는 리소스의 **입력 선언**(소스, 릴리스 정의 등)을 보여 준다. 반면 `flux tree kustomization <이름>`은 특정 Kustomization이 실제로 생성한 **Kubernetes 리소스**(Deployment, Service 등)를 트리 형태로 보여 준다.

- `flux get all` → "Flux에 무엇을 선언했는가?" (입력)
- `flux tree` → "그 선언의 결과로 무엇이 생성되었는가?" (출력)

전체 환경 파악에는 `flux get all`이 유용하고, 특정 릴리스의 배포 결과를 추적할 때는 `flux tree`가 유용하다.

<br>

# Gitea 저장소 설정

이 실습에서 Git 저장소는 Gitea에 호스팅되어 있다. 저장소에 접근하기 위한 설정을 진행하자.

## 접근 설정

Gitea 웹 인터페이스에 접속하기 위해 다음 스크립트를 실행한다. 출력된 Public URL을 브라우저에서 열어 로그인할 수 있다.

```bash
# Gitea 접속 정보 확인
export GITEA_PRIVATE_IP=$(kubectl get configmap saas-infra-outputs \
  -n flux-system -o jsonpath='{.data.gitea_url}')
export GITEA_PUBLIC_IP=$(kubectl get configmap saas-infra-outputs \
  -n flux-system -o jsonpath='{.data.gitea_public_url}')
export GITEA_PORT="3000"

# SSM Parameter Store에서 관리자 비밀번호 조회
export GITEA_ADMIN_PASSWORD=$(aws ssm get-parameter \
  --name "/eks-saas-gitops/gitea-admin-password" \
  --with-decryption --query 'Parameter.Value' --output text)

echo "Public URL: $GITEA_PUBLIC_IP"
echo "Username: admin"
echo "Password: $GITEA_ADMIN_PASSWORD"
```

```text
Public URL: http://<Public-IP>:3000
Username: admin
Password: <password>
```

출력된 URL로 접속하면 로그인 화면이 나타난다.

![Gitea 로그인 화면]({{site.url}}/assets/images/eks-w6-gitea-login.png){: .align-center}

`admin` 계정과 출력된 비밀번호로 로그인하면 대시보드를 확인할 수 있다.

![Gitea 대시보드]({{site.url}}/assets/images/eks-w6-gitea-dashboard.png){: .align-center}

> URL에 접속이 되지 않을 경우, AWS 콘솔에서 보안 그룹 설정에 본인 IP 주소를 추가해야 한다.

## 저장소 접근 변수 설정

Gitea 토큰과 저장소 경로를 환경 변수로 설정한다.

```bash
# Gitea 인증 토큰 조회
export GITEA_TOKEN=$(kubectl get configmap saas-infra-outputs \
  -n flux-system -o jsonpath='{.data.gitea_token}')

# 저장소 경로 설정
export REPO_PATH="/home/ec2-user/environment/microservice-repos"
export GITOPS_REPO_PATH="/home/ec2-user/environment/gitops-gitea-repo"
mkdir -p $REPO_PATH
```

실습에서 export하는 변수들은 모두 Git 저장소 접근에 필요한 정보다.

```text
GITEA_PRIVATE_IP       → Gitea 서버 클러스터 내부 IP
GITEA_PUBLIC_IP        → 브라우저에서 접근할 때 쓰는 외부 IP
GITEA_PORT             → 3000번 포트
GITEA_TOKEN            → 인증 토큰 (push/pull 권한)
GITEA_ADMIN_PASSWORD   → 웹 UI 로그인용
```

이 변수들은 **누가 사용하느냐**에 따라 두 갈래로 나뉜다.

1. **사람(실습 참가자)**: 방금 설정한 셸 환경 변수로 터미널에서 직접 `git clone`, `git push` 등을 수행한다.
2. **Flux(자동화)**:Kubernetes Secret(`flux-system` 네임스페이스)에 같은 접속 정보가 저장되어 있다. GitRepository CRD가 `secretRef`로 이 Secret을 참조하고, Flux 컨트롤러는 이 정보로 Gitea를 주기적으로 polling하여 변경 사항을 감지한다.

같은 Git 저장소에 접근하기 위한 인증 정보이지만, 사람용은 셸 변수로 export하고 Flux용은 Kubernetes Secret에 저장되어 있는 것이다.

## 마이크로서비스 저장소 복제

실습에 필요한 마이크로서비스 저장소 3개를 복제한다.

```bash
cd $REPO_PATH

# 마이크로서비스 저장소 복제
git clone http://admin:${GITEA_TOKEN}@${GITEA_PRIVATE_IP}:${GITEA_PORT}/admin/producer.git
git clone http://admin:${GITEA_TOKEN}@${GITEA_PRIVATE_IP}:${GITEA_PORT}/admin/consumer.git
git clone http://admin:${GITEA_TOKEN}@${GITEA_PRIVATE_IP}:${GITEA_PORT}/admin/payments.git

# 복제 결과 확인
ls -la $REPO_PATH
```

```text
total 0
drwxrwxr-x. 5 ec2-user ec2-user 54 ...
drwxrwxr-x. 4 ec2-user ec2-user 93 ... consumer
drwxrwxr-x. 4 ec2-user ec2-user 93 ... payments
drwxrwxr-x. 4 ec2-user ec2-user 93 ... producer
```

GitOps 저장소(`gitops-gitea-repo`)는 이미 설치 과정에서 복제되어 있다.

```bash
ls -la $GITOPS_REPO_PATH
```

```text
drwxr-xr-x. 9 ec2-user ec2-user 156 ...
drwxr-xr-x. 3 ec2-user ec2-user  24 ... application-plane
drwxr-xr-x. 3 ec2-user ec2-user  24 ... clusters
drwxr-xr-x. 3 ec2-user ec2-user  24 ... control-plane
drwxr-xr-x. 4 ec2-user ec2-user  56 ... helm-charts
drwxr-xr-x. 4 ec2-user ec2-user  36 ... infrastructure
drwxr-xr-x. 3 ec2-user ec2-user  21 ... terraform
```

## GitRepository CRD 연동 확인

Flux가 Gitea 저장소와 정상적으로 연동되어 있는지 확인한다.

```bash
$ kubectl -n flux-system get gitrepository
NAME               URL                                                AGE   READY   STATUS
flux-system        http://<Gitea-IP>:3000/admin/eks-saas-gitops.git   40h   True    stored artifact for revision 'refs/heads/main@sha1:b792d408...'
terraform-v0-0-1   http://<Gitea-IP>:3000/admin/eks-saas-gitops.git   40h   True    stored artifact for revision 'v0.0.1@sha1:2d19a84a...'
```

`flux-system`과 `terraform-v0-0-1` 두 GitRepository가 모두 `READY=True` 상태라면, Flux가 Gitea 저장소를 정상적으로 감시하고 있는 것이다.

<br>

# 정리

설치 후 클러스터 환경 상태를 정리하면 다음과 같다.

| 구성 요소 | 역할 | 확인 명령 |
| --- | --- | --- |
| 네임스페이스 | 워크로드 격리 | `kubectl get ns` |
| Flux 전체 리소스 | GitOps 파이프라인 관리 | `flux get all` |
| GitRepository | Git 소스 연동 | `kubectl -n flux-system get gitrepository` |
| HelmRelease | 애드온 및 서비스 배포 | `flux get helmreleases` |
| ImageUpdateAutomation | 이미지 자동 반영 | `flux get image update` |
| Gitea 저장소 | 마이크로서비스 코드 관리 | `ls $REPO_PATH` |

이번 포스트에서는 실습 환경에 무엇이 배포되어 있는지를 전체적으로 확인했다. 다음 포스트에서는 이 Flux 리소스들이 어떤 아키텍처로 구성되어 있는지, Kustomization의 계층 구조와 의존 관계를 분석한다.

<br>