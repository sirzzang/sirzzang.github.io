---
title: "[EKS] EKS 업그레이드: Self-managed 노드 및 Fargate 업그레이드"
excerpt: "Self-managed 노드는 Launch Template AMI 교체로, Fargate는 Deployment 재시작만으로 업그레이드할 수 있다."
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
  - Self-managed-Node-Group
  - Fargate
  - Terraform
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-7
hidden: true
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 7주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- **Self-managed 노드**: Launch Template의 AMI를 1.31용으로 교체하고 `terraform apply`를 실행하면, 기존 노드가 새 AMI로 교체된다
- **Fargate**: Control Plane이 이미 1.31이므로, Deployment를 재시작(`kubectl rollout restart`)하면 새 파드가 1.31 Fargate 노드에 스케줄링된다
- 둘 다 핵심 원리는 동일하다: **새 버전의 노드를 프로비저닝하고, 기존 파드를 재배치**하는 것

<br>

# Self-managed 노드 업그레이드

Self-managed 노드는 EKS가 라이프사이클을 관리하지 않으므로, 사용자가 직접 AMI를 교체해야 한다. 이 워크숍에서는 Terraform으로 프로비저닝되어 있으므로, `base.tf`의 AMI ID만 변경하면 된다.

## 현재 상태 확인

```bash
~$ kubectl get nodes -l node.kubernetes.io/lifecycle=self-managed

# 실행 결과
NAME                                        STATUS   ROLES    AGE     VERSION
ip-10-0-30-153.us-west-2.compute.internal   Ready    <none>   4h19m   v1.30.14-eks-f69f56f
ip-10-0-44-249.us-west-2.compute.internal   Ready    <none>   4h19m   v1.30.14-eks-f69f56f
```

Self-managed 노드 2대가 **v1.30**으로 실행 중이다. `team=carts` 레이블이 붙어 있어 carts 앱이 이 노드에서 실행된다.

## 업그레이드 절차

1.31용 EKS 최적화 AMI ID를 조회한다.

```bash
~$ aws ssm get-parameter \
    --name /aws/service/eks/optimized-ami/1.31/amazon-linux-2023/x86_64/standard/recommended/image_id \
    --region $AWS_REGION \
    --query "Parameter.Value" --output text

# 실행 결과
ami-0c4dea04571b1b508
```

`base.tf`에서 Self-managed 노드 그룹의 AMI ID를 위 값으로 교체한다.

![Self-managed 노드 AMI 변경]({{site.url}}/assets/images/eks-upgrade-selfmng-ami.png){: .align-center}

```bash
~$ cd ~/environment/terraform
~$ terraform plan && terraform apply -auto-approve
```

Terraform이 Launch Template을 업데이트하고, Auto Scaling Group의 인스턴스를 새 AMI로 교체한다.

## 결과 확인

```bash
~$ kubectl get nodes -l node.kubernetes.io/lifecycle=self-managed

# 실행 결과
NAME                                       STATUS   ROLES    AGE   VERSION
ip-10-0-13-35.us-west-2.compute.internal   Ready    <none>   27s   v1.31.14-eks-ecaa3a6
ip-10-0-8-246.us-west-2.compute.internal   Ready    <none>   60s   v1.31.14-eks-ecaa3a6
```

두 노드 모두 **v1.31**로 업그레이드되었다.

<br>

# Fargate 업그레이드

Fargate는 파드 단위로 격리된 컴퓨트 환경을 제공하며, 노드를 직접 관리하지 않는다. Control Plane이 이미 업그레이드된 상태에서 파드를 재시작하면, 새 파드는 **업그레이드된 Kubernetes 버전의 Fargate 노드**에 스케줄링된다.

## 현재 상태 확인

```bash
~$ kubectl get pods -n assets -o wide

# 실행 결과
NAME                      READY   STATUS    RESTARTS   AGE   IP            NODE
assets-784b5f5656-xxxxx   1/1     Running   0          31m   10.0.14.147   fargate-ip-10-0-14-147.us-west-2.compute.internal
```

```bash
# Fargate 노드의 Kubernetes 버전 확인
~$ kubectl get node $(kubectl get pods -n assets -o jsonpath='{.items[0].spec.nodeName}') -o wide

# 실행 결과 (VERSION 컬럼)
NAME                                                STATUS   ROLES    AGE    VERSION
fargate-ip-10-0-14-147.us-west-2.compute.internal   Ready    <none>   5h1m   v1.30.14-eks-f69f56f
```

Fargate 노드가 아직 **v1.30**이다.

## 업그레이드 절차

Deployment를 재시작하면 된다.

```bash
# Deployment 재시작
~$ kubectl rollout restart deployment assets -n assets

# 새 파드가 Ready될 때까지 대기
~$ kubectl wait --for=condition=Ready pods --all -n assets --timeout=180s
```

## 결과 확인

```bash
~$ kubectl get pods -n assets -o wide

# 실행 결과
NAME                      READY   STATUS    RESTARTS   AGE    IP           NODE
assets-7996d6586b-xxxxx   1/1     Running   0          3m9s   10.0.11.49   fargate-ip-10-0-11-49.us-west-2.compute.internal
```

```bash
~$ kubectl get node $(kubectl get pods -n assets -o jsonpath='{.items[0].spec.nodeName}') -o wide

# 실행 결과 (VERSION 컬럼)
NAME                                               STATUS   ROLES    AGE     VERSION
fargate-ip-10-0-11-49.us-west-2.compute.internal   Ready    <none>   2m32s   v1.31.14-eks-f69f56f
```

새 Fargate 노드가 **v1.31**로 프로비저닝된 것을 확인할 수 있다.

<br>

# 정리

모든 노드 유형의 업그레이드가 완료되었다.

| 노드 유형 | 노드 그룹 | 전략 | 상태 |
|-----------|-----------|------|------|
| Managed Node Group | `initial` | In-Place | 1.31 완료 |
| Managed Node Group | `blue-mng` → `green-mng` | Blue-Green | 1.31 완료 |
| Karpenter | `default` NodePool | Drift + Disruption Budget | 1.31 완료 |
| Self-managed | `default-selfmng` | **AMI 교체 (Terraform)** | **1.31 완료 (이 글)** |
| Fargate | `fp-profile` | **Deployment 재시작** | **1.31 완료 (이 글)** |

핵심은 모두 동일하다. **새 버전의 노드를 프로비저닝하고, 기존 파드를 재배치**하는 것이다. 방법만 노드 유형에 따라 달라진다.

| 노드 유형 | 업그레이드 방법 |
|-----------|----------------|
| Managed Node Group | EKS가 ASG를 통해 롤링 교체 |
| Self-managed | Launch Template AMI 교체 → ASG 인스턴스 교체 |
| Karpenter | EC2NodeClass AMI 변경 → Drift 감지 → 자동 교체 |
| Fargate | Deployment 재시작 → 새 버전 노드에 스케줄링 |

<br>

# 참고 링크

- [Amazon EKS Self-managed Node Groups](https://docs.aws.amazon.com/eks/latest/userguide/worker.html)
- [Amazon EKS on Fargate](https://docs.aws.amazon.com/eks/latest/userguide/fargate.html)
- [Updating a Self-managed Node Group](https://docs.aws.amazon.com/eks/latest/userguide/update-workers.html)

<br>
