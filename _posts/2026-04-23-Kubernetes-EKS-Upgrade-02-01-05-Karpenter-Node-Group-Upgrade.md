---
title: "[EKS] EKS 업그레이드: Karpenter 노드 업그레이드"
excerpt: "Karpenter가 관리하는 노드를 Drift와 Disruption Budget을 활용해 제어된 방식으로 업그레이드하는 워크샵 내용을 정리해 보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - EKS-Upgrade
  - Karpenter
  - Drift
  - Disruption-Budget
  - ArgoCD
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-7
hidden: true
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 7주차 학습 내용을 기반으로 합니다.*

> 이 글의 실습 섹션은 워크샵에서 제공하는 의도된 흐름과 결과를 기반으로 작성했다. 실습 환경에서 ArgoCD 싱크가 정상 동작하지 않아 직접 재현하지 못했기 때문에, 워크샵 내용을 중심으로 Karpenter 노드 업그레이드의 개념과 절차를 정리한다.

<br>

# TL;DR

- Karpenter는 노드 그룹(MNG, ASG)이 아닌 **NodePool/EC2NodeClass** 리소스로 노드를 관리하므로, 업그레이드 방식이 Managed Node Group과 근본적으로 다르다
- **Drift**: EC2NodeClass의 AMI를 변경하면 Karpenter가 기존 노드와 desired 상태의 차이를 감지하고, 새 노드를 프로비저닝한 뒤 기존 노드를 교체한다
- **Disruption Budget**: NodePool의 `spec.disruption.budgets`로 한 번에 교체되는 노드 수를 제어할 수 있다
- 워크샵에서는 checkout 앱을 10개로 스케일 아웃하여 Karpenter 노드를 2대로 늘린 뒤, AMI를 1.31로 변경하고 Disruption Budget(`nodes: "1"`)을 적용하여 **한 대씩 롤링 교체**되는 것을 확인한다

<br>

# Karpenter 노드 업그레이드 개요

Karpenter는 스케줄링되지 못한 파드(unschedulable Pod)의 리소스 요청을 분석하여 적절한 크기의 노드를 직접 프로비저닝하는 오픈소스 오토스케일러다. EC2 Auto Scaling Group이나 Managed Node Group 같은 외부 인프라를 거치지 않고 직접 EC2 인스턴스를 관리하므로, 노드 업그레이드 방식도 다르다.

Karpenter에서 노드 업그레이드에 활용할 수 있는 메커니즘은 크게 세 가지다.

| 메커니즘 | 설명 | 용도 |
|----------|------|------|
| **Drift** | 노드의 현재 상태와 desired 상태의 차이를 감지하여 자동 교체 | AMI 변경, NodePool 설정 변경 시 |
| **expireAfter** | 노드가 지정된 시간 이상 실행되면 자동 만료 | 주기적 노드 교체, 보안 패치 |
| **Disruption Budget** | 한 번에 교체 가능한 노드 수/비율을 제한 | 대규모 클러스터에서 점진적 업그레이드 |

<br>

# Drift

Drift는 Karpenter의 핵심 업그레이드 메커니즘이다. EC2NodeClass나 NodePool의 설정이 변경되면, Karpenter가 기존 노드와 새 설정 사이의 차이(drift)를 감지하고 롤링 방식으로 노드를 교체한다.

교체 과정은 다음과 같다.

```text
AMI 변경 감지 (Drift 발생)
    ↓
새 노드 프로비저닝 (새 AMI로)
    ↓
기존 노드 Cordon (새 파드 스케줄링 차단)
    ↓
기존 노드의 파드 축출 (Kubernetes Eviction API)
    ↓
기존 노드 Terminate
```

AMI 지정 방식에 따라 Drift 동작이 다르다.

## AMI를 직접 지정하는 경우

`EC2NodeClass`의 `amiSelectorTerms`에 AMI ID, 이름, 태그 등으로 직접 지정하는 방식이다. AMI를 변경하면 Karpenter가 기존 노드의 AMI와 새 설정의 AMI가 다른 것을 감지하고 Drift를 발생시킨다. 환경별로 검증된 AMI를 순차적으로 승격(promote)시키고 싶을 때 적합하다.

```yaml
apiVersion: karpenter.k8s.aws/v1
kind: EC2NodeClass
metadata:
  name: default
spec:
  amiSelectorTerms:
    # AMI ID를 직접 지정
    - id: ami-0f676a166352f02ab
```

## EKS 최적화 AMI를 사용하는 경우

`alias` 필드를 사용하면 EKS 최적화 AMI를 자동으로 선택한다. `alias`는 `family@version` 형식이며, `version`을 `latest`로 설정하면 Karpenter가 SSM 파라미터를 모니터링하다가 새 AMI가 릴리스되면 자동으로 Drift를 발생시킨다.

```yaml
apiVersion: karpenter.k8s.aws/v1
kind: EC2NodeClass
metadata:
  name: default
spec:
  amiSelectorTerms:
    # latest: 새 AMI 릴리스 시 자동 Drift
    - alias: al2023@latest
```

> `latest`는 사전 프로덕션 환경에서 자동 업그레이드를 받기에 편리하지만, 프로덕션에서는 특정 버전을 고정(pin)하여 하위 환경에서 먼저 검증한 뒤 승격하는 것을 권장한다.

<br>

# TTL (expireAfter)

`NodePool`의 `spec.disruption.expireAfter`를 설정하면, 노드가 지정된 시간만큼 실행된 뒤 자동으로 만료(expire) 처리된다. 만료된 노드는 Karpenter가 교체 노드를 프로비저닝한 뒤 삭제한다.

주기적으로 노드를 교체하여 보안 패치를 적용하거나, 장기 실행 노드의 리소스 단편화를 해소하는 데 유용하다.

<br>

# Disruption Budget

대규모 클러스터에서 Drift가 수백 개 노드에 동시에 발생하면, 모든 노드가 한꺼번에 교체되어 서비스에 영향을 줄 수 있다. `NodePool`의 `spec.disruption.budgets`로 이를 제어할 수 있다.

## 기본 동작

Disruption Budget이 정의되지 않으면, Karpenter는 기본적으로 전체 노드의 **10%**만 동시에 교체한다. Budget은 Drift, Empty, Underutilized 등 자발적(voluntary) disruption에만 적용되며, 노드 장애 같은 비자발적 disruption에는 적용되지 않는다.

## Budget 예시

### Drift 시 한 대씩 교체

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: default
spec:
  disruption:
    budgets:
      - nodes: "1"
        reasons:
          - Drifted
      - nodes: "100%"
        reasons:
          - Empty
          - Underutilized
```

Drift로 인한 교체는 한 대씩만, Empty/Underutilized는 제한 없이 진행된다.

### 업무 시간 중 교체 금지

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: default
spec:
  disruption:
    budgets:
      - schedule: "0 9 * * mon-fri"
        duration: 8h
        nodes: 0
      - nodes: 10
```

평일 09:00~17:00에는 자발적 disruption을 완전히 차단하고, 그 외 시간에는 최대 10대까지만 동시 교체한다.

### 모든 자발적 disruption 차단

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: default
spec:
  disruption:
    budgets:
      - nodes: 0
```

미션 크리티컬 워크로드가 실행 중인 NodePool에서, 자발적 disruption을 완전히 막고 싶을 때 사용한다.

<br>

# 실습 환경 확인

워크샵 실습 환경에는 이미 Karpenter가 설치되어 있고, `default` NodePool과 `default` EC2NodeClass가 적용되어 있다.

## NodePool/EC2NodeClass 확인

```bash
~$ kubectl describe nodepool
~$ kubectl describe ec2nodeclass
```

확인할 수 있는 주요 설정은 다음과 같다.

| 항목 | 설정 |
|------|------|
| Disruption Budget | `nodes: 10%` (기본값) |
| 노드 레이블 | `Team: checkout` |
| Taint | `dedicated=CheckoutApp:NoSchedule` |
| NodeClassRef | `default` EC2NodeClass |
| AMI ID | `ami-0f676a166352f02ab` (1.30용) |

## Karpenter 노드 확인

```bash
~$ kubectl get nodes -l team=checkout

# 실행 결과
NAME                                       STATUS   ROLES    AGE     VERSION
ip-10-0-12-111.us-west-2.compute.internal   Ready    <none>   3h57m   v1.30.14-eks-f69f56f
```

Karpenter가 프로비저닝한 노드가 1대 있고, **v1.30** 버전이다.

## Taint 확인

```bash
~$ kubectl get nodes -l team=checkout \
    -o jsonpath="{range .items[*]}{.metadata.name} {.spec.taints[?(@.effect=='NoSchedule')]}{\"\n\"}{end}"

# 실행 결과
ip-10-0-12-111.us-west-2.compute.internal {"effect":"NoSchedule","key":"dedicated","value":"CheckoutApp"}
```

`dedicated=CheckoutApp:NoSchedule` taint이 적용되어 있어, toleration이 있는 checkout 파드만 이 노드에 스케줄링된다.

## checkout 앱 확인

```bash
~$ kubectl get pods -n checkout -o wide

# 실행 결과
NAME                             READY   STATUS    RESTARTS   AGE     IP           NODE
checkout-5fdd57d475-xxxxx        1/1     Running   0          3h59m   10.0.14.167   ip-10-0-12-111.us-west-2.compute.internal
checkout-redis-75bcf8cd59-xxxxx  1/1     Running   0          3h59m   10.0.4.32     ip-10-0-12-111.us-west-2.compute.internal
```

checkout 앱과 checkout-redis가 Karpenter 노드에서 실행 중이다. checkout은 PersistentVolume이 연결된 Stateful 워크로드다.

<br>

# 워크샵 실습 흐름

워크샵의 의도된 흐름은 다음과 같다.

1. checkout 앱을 스케일 아웃하여 Karpenter 노드를 **2대로 늘린다** (Disruption Budget 시연을 위해)
2. 1.31용 AMI ID를 확인한다
3. EC2NodeClass의 AMI를 1.31로 변경하고, NodePool에 Disruption Budget을 추가한다
4. ArgoCD 싱크 후 Karpenter가 Drift를 감지하여 **한 대씩** 노드를 교체한다

## 1단계: checkout 앱 스케일 아웃

GitOps 저장소(`eks-gitops-repo/apps/checkout/deployment.yaml`)에서 checkout 앱의 레플리카를 1에서 10으로 변경한다.

![deployment.yaml에서 replicas 변경]({{site.url}}/assets/images/eks-upgrade-karpenter-scale-checkout.png){: .align-center}

```bash
~$ cd ~/environment/eks-gitops-repo
~$ git add apps/checkout/deployment.yaml
~$ git commit -m "scale checkout app"
~$ git push --set-upstream origin main
```

ArgoCD가 변경을 감지하여 싱크하면(또는 수동으로 `argocd app sync checkout` 실행), 기존 노드 1대로는 10개 파드의 리소스 요청을 감당할 수 없으므로, Karpenter가 **추가 노드를 프로비저닝**한다.

```bash
~$ kubectl get nodes -l team=checkout

# 실행 결과 (노드 2대)
NAME                                        STATUS   ROLES    AGE     VERSION
ip-10-0-12-111.us-west-2.compute.internal   Ready    <none>   4h13m   v1.30.14-eks-f69f56f
ip-10-0-41-46.us-west-2.compute.internal    Ready    <none>   21s     v1.30.14-eks-f69f56f
```

둘 다 **v1.30**이다. Karpenter가 EC2NodeClass에 설정된 현재 AMI(1.30용)로 노드를 프로비저닝했기 때문이다.

## 2단계: 1.31용 AMI ID 확인

SSM 파라미터에서 1.31 EKS 최적화 AMI ID를 조회한다.

```bash
~$ aws ssm get-parameter \
    --name /aws/service/eks/optimized-ami/1.31/amazon-linux-2023/x86_64/standard/recommended/image_id \
    --region ${AWS_REGION} \
    --query "Parameter.Value" --output text

# 실행 결과
ami-0c4dea04571b1b508
```

## 3단계: EC2NodeClass AMI 변경 + Disruption Budget 추가

두 가지 변경을 진행한다.

**EC2NodeClass(`default-ec2nc.yaml`):** `amiSelectorTerms`의 AMI ID를 1.31용으로 교체한다.

![EC2NodeClass AMI 변경]({{site.url}}/assets/images/eks-upgrade-karpenter-ec2nodeclass-ami.png){: .align-center}

**NodePool(`default-np.yaml`):** `spec.disruption.budgets`에 Drift 시 한 대씩만 교체하는 budget을 추가한다.

```yaml
budgets:
  - nodes: "1"
    reasons:
      - Drifted
```

![NodePool Disruption Budget 추가]({{site.url}}/assets/images/eks-upgrade-karpenter-nodepool-budget.png){: .align-center}

변경 사항을 커밋하고 푸시한다.

```bash
~$ git add apps/karpenter/default-ec2nc.yaml apps/karpenter/default-np.yaml
~$ git commit -m "disruption changes"
~$ git push --set-upstream origin main
```

## 4단계: ArgoCD 싱크 및 Drift 확인

ArgoCD로 karpenter 앱을 싱크한다.

```bash
~$ argocd app sync karpenter
```

싱크가 완료되면, Karpenter 컨트롤러가 EC2NodeClass의 AMI 변경을 감지하고 기존 노드에 Drift를 발생시킨다. Disruption Budget(`nodes: "1"`)에 따라 **한 대씩** 교체가 진행된다.

Karpenter 컨트롤러 로그로 과정을 확인할 수 있다.

```bash
~$ kubectl -n karpenter logs deployment/karpenter -c controller --tail=33
```

<details markdown="1">
<summary><b>Karpenter 컨트롤러 로그 (워크샵 결과)</b></summary>

```json
{"level":"INFO","message":"disrupting nodeclaim(s) via replace, terminating 1 nodes (2 pods) ip-10-0-41-46.us-west-2.compute.internal/c4.large/spot and replacing with node from types c5.large, c4.large, m6a.large, r4.large, m5.large and 40 other(s)","reason":"drifted"}
{"level":"INFO","message":"created nodeclaim","NodePool":{"name":"default"},"NodeClaim":{"name":"default-j882g"}}
{"level":"INFO","message":"launched nodeclaim","instance-type":"c4.large","zone":"us-west-2c","capacity-type":"spot"}
{"level":"INFO","message":"registered nodeclaim","Node":{"name":"ip-10-0-38-70.us-west-2.compute.internal"}}
{"level":"INFO","message":"initialized nodeclaim","Node":{"name":"ip-10-0-38-70.us-west-2.compute.internal"}}
{"level":"INFO","message":"tainted node","Node":{"name":"ip-10-0-41-46.us-west-2.compute.internal"},"taint.Key":"karpenter.sh/disrupted"}
{"level":"INFO","message":"deleted node","Node":{"name":"ip-10-0-41-46.us-west-2.compute.internal"}}
{"level":"INFO","message":"deleted nodeclaim","NodeClaim":{"name":"default-6swc4"}}
{"level":"INFO","message":"disrupting nodeclaim(s) via replace, terminating 1 nodes (8 pods) ip-10-0-12-111.us-west-2.compute.internal/m6i.large/spot and replacing with node from types c5.large, c4.large, m6a.large, r4.large, m5.large and 40 other(s)","reason":"drifted"}
{"level":"INFO","message":"created nodeclaim","NodePool":{"name":"default"},"NodeClaim":{"name":"default-ct7nn"}}
{"level":"INFO","message":"launched nodeclaim","instance-type":"c4.large","zone":"us-west-2a","capacity-type":"spot"}
{"level":"INFO","message":"registered nodeclaim","Node":{"name":"ip-10-0-12-207.us-west-2.compute.internal"}}
{"level":"INFO","message":"initialized nodeclaim","Node":{"name":"ip-10-0-12-207.us-west-2.compute.internal"}}
{"level":"INFO","message":"tainted node","Node":{"name":"ip-10-0-12-111.us-west-2.compute.internal"},"taint.Key":"karpenter.sh/disrupted"}
{"level":"INFO","message":"deleted node","Node":{"name":"ip-10-0-12-111.us-west-2.compute.internal"}}
{"level":"INFO","message":"deleted nodeclaim","NodeClaim":{"name":"default-q9tgw"}}
```

</details>

로그를 보면, Karpenter가 두 노드를 **순차적으로** 교체하는 것을 확인할 수 있다.

1. 먼저 `ip-10-0-41-46` 노드를 교체: 새 NodeClaim 생성 → 새 노드 프로비저닝 → 기존 노드 taint → 파드 축출 → 기존 노드 삭제
2. 첫 번째 교체가 완료된 뒤, `ip-10-0-12-111` 노드를 동일한 과정으로 교체

`nodes: "1"` budget 덕분에 한 대씩만 교체되어, 서비스 가용성이 유지된다.

## 5단계: 업그레이드 결과 확인

모든 교체가 완료되면, Karpenter 노드가 **v1.31**로 업그레이드된 것을 확인할 수 있다.

```bash
~$ kubectl get nodes -l team=checkout

# 실행 결과
NAME                                        STATUS   ROLES    AGE     VERSION
ip-10-0-12-207.us-west-2.compute.internal   Ready    <none>   4m5s    v1.31.14-eks-ecaa3a6
ip-10-0-38-70.us-west-2.compute.internal    Ready    <none>   5m48s   v1.31.14-eks-ecaa3a6
```

checkout 파드도 새 노드에서 정상 실행 중이다.

```bash
~$ kubectl get pods -n checkout -o wide
```

<details markdown="1">
<summary><b>checkout 파드 상세 출력</b></summary>

```text
NAME                              READY   STATUS    RESTARTS   AGE     IP            NODE
checkout-5fdd57d475-xxxxx         1/1     Running   0          4m18s   10.0.3.90     ip-10-0-12-207.us-west-2.compute.internal
checkout-5fdd57d475-xxxxx         1/1     Running   0          4m18s   10.0.3.56     ip-10-0-12-207.us-west-2.compute.internal
checkout-5fdd57d475-xxxxx         1/1     Running   0          6m3s    10.0.34.117   ip-10-0-38-70.us-west-2.compute.internal
checkout-5fdd57d475-xxxxx         1/1     Running   0          4m18s   10.0.46.239   ip-10-0-38-70.us-west-2.compute.internal
checkout-5fdd57d475-xxxxx         1/1     Running   0          6m3s    10.0.35.57    ip-10-0-38-70.us-west-2.compute.internal
checkout-5fdd57d475-xxxxx         1/1     Running   0          4m18s   10.0.3.179    ip-10-0-12-207.us-west-2.compute.internal
checkout-5fdd57d475-xxxxx         1/1     Running   0          4m18s   10.0.45.116   ip-10-0-38-70.us-west-2.compute.internal
checkout-5fdd57d475-xxxxx         1/1     Running   0          4m18s   10.0.13.42    ip-10-0-12-207.us-west-2.compute.internal
checkout-5fdd57d475-xxxxx         1/1     Running   0          4m18s   10.0.3.17     ip-10-0-12-207.us-west-2.compute.internal
checkout-5fdd57d475-xxxxx         1/1     Running   0          4m18s   10.0.40.78    ip-10-0-38-70.us-west-2.compute.internal
checkout-redis-75bcf8cd59-xxxxx   1/1     Running   0          4m18s   10.0.12.140   ip-10-0-12-207.us-west-2.compute.internal
```

</details>

10개의 checkout 파드와 checkout-redis 파드가 두 개의 새 노드에 고르게 분산되어 실행 중이다.

<br>

# Managed Node Group 업그레이드와의 비교

| 항목 | Managed Node Group | Karpenter |
|------|-------------------|-----------|
| 노드 관리 주체 | EKS (ASG 기반) | Karpenter 컨트롤러 |
| 업그레이드 트리거 | MNG 버전 변경 (Terraform/콘솔/CLI) | EC2NodeClass AMI 변경 → Drift 감지 |
| 롤링 제어 | `max_unavailable_percentage` | **Disruption Budget** (`nodes`, `schedule`) |
| AMI 선택 | Launch Template 또는 EKS 기본 AMI | `amiSelectorTerms` (ID/alias) |
| 프로비저닝 방식 | ASG capacity 조정 | Karpenter가 직접 EC2 인스턴스 프로비저닝 |
| Stateful 워크로드 | PDB 존중 (cordon → drain) | PDB 존중 (Eviction API) |

핵심 차이는 **제어 평면**이다. MNG는 AWS가 ASG를 통해 노드 라이프사이클을 관리하고, Karpenter는 자체 컨트롤러가 직접 EC2 인스턴스를 프로비저닝/삭제한다. 따라서 업그레이드도 MNG는 노드 그룹 설정 변경으로, Karpenter는 EC2NodeClass의 AMI 변경 + Drift로 이루어진다.

<br>

# 정리

이 글에서는 Karpenter가 관리하는 노드를 업그레이드하는 방법을 정리했다. EC2NodeClass에서 AMI를 변경하면 Karpenter가 Drift를 감지하여 자동으로 노드를 교체하고, Disruption Budget으로 교체 속도를 제어할 수 있다.

현재까지의 노드 업그레이드 상황을 정리하면 다음과 같다.

| 노드 유형 | 노드 그룹 | 전략 | 상태 |
|-----------|-----------|------|------|
| Managed Node Group | `initial` | In-Place | 1.31 완료 |
| Managed Node Group | `blue-mng` → `green-mng` | Blue-Green | 1.31 완료 |
| Karpenter | `default` NodePool | **Drift + Disruption Budget** | **1.31 완료 (이 글)** |
| Self-managed / Fargate | default-selfmng, fp-profile | AMI 교체 / Deployment 재시작 | 다음 글 |

<br>

# 참고 링크

- [Karpenter Disruption](https://karpenter.sh/docs/concepts/disruption/)
- [Karpenter NodePool](https://karpenter.sh/docs/concepts/nodepools/)
- [Karpenter EC2NodeClass](https://karpenter.sh/docs/concepts/nodeclasses/)
- [Amazon EKS Optimized AMIs](https://docs.aws.amazon.com/eks/latest/userguide/eks-optimized-ami.html)

<br>
