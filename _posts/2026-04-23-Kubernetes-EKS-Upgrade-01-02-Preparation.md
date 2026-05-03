---
title: "[EKS] EKS 업그레이드: 업그레이드 준비"
excerpt: "EKS 클러스터 업그레이드 전에 확인해야 할 사전 요구사항, Upgrade Insights, 체크리스트, PDB 설정 등을 정리해 보자."
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
  - EKS-Upgrade-Insights
  - PodDisruptionBudget
  - ArgoCD
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-7
hidden: true
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 7주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- 업그레이드 전 사전 요구사항 확인 필수: **서브넷 IP 여유**(최소 5개), **IAM 역할** 존재, **KMS 키 권한**(Secrets 암호화 시)
- **EKS Upgrade Insights**를 활용하면 Deprecated API, 애드온 호환성, 컴포넌트 버전 스큐 등을 자동으로 점검할 수 있다
- 업그레이드 대상 K8s 버전별 릴리즈 노트를 확인하고, 각 애드온(CoreDNS, kube-proxy, VPC CNI 등)의 호환 버전을 체크해야 한다
- Deprecated API를 사용하는 매니페스트는 `kubectl-convert`로 마이그레이션할 수 있다
- **PodDisruptionBudget(PDB)**과 **TopologySpreadConstraints**를 설정하여 Data Plane 업그레이드 시 워크로드 가용성을 보장한다
- GitOps(ArgoCD) 또는 Helm Charts로 애플리케이션을 패키징하면, 업그레이드 과정에서의 일관된 배포가 용이하다

<br>

# 업그레이드 워크플로우

EKS 클러스터 업그레이드는 다음과 같은 워크플로우를 따른다.

```text
업그레이드 시작
    ↓
주요 변경사항 파악 (EKS/K8s 버전별)
    ↓
Deprecation Policy 확인 및 매니페스트 수정
    ↓
EKS Control Plane & Data Plane 업그레이드
    ↓
애드온 의존성 업그레이드
    ↓
업그레이드 완료
```

이 글에서는 "업그레이드 시작" 전에 확인하고 준비해야 할 사항들을 다룬다.

<br>

# EKS Upgrade Insights

[EKS Upgrade Insights](https://docs.aws.amazon.com/eks/latest/userguide/cluster-insights.html)는 Amazon EKS가 제공하는 자동 점검 기능이다. 모든 EKS 클러스터에 대해 주기적으로 업그레이드 준비 상태를 검사하고, 문제가 발견되면 권장 조치를 제시한다.

## Insights가 검사하는 항목

| 검사 항목 | 설명 |
|-----------|------|
| Deprecated/Removed API 사용 | 다음 버전에서 제거될 API를 사용하는 리소스 탐지 |
| Kubelet 버전 스큐 | 워커 노드의 kubelet 버전이 업그레이드 후에도 스큐 정책을 준수하는지 확인 |
| kube-proxy 버전 스큐 | kube-proxy 버전이 새 버전과 호환되는지 확인 |
| EKS 애드온 호환성 | 설치된 EKS 애드온이 대상 K8s 버전과 호환되는지 확인 |
| Amazon Linux 2 호환성 | AL2 노드 존재 여부 확인 (AL2 지원 종료 대비) |
| 클러스터 상태 이상 | 업그레이드를 방해할 수 있는 클러스터 상태 문제 탐지 |

## Insights 상태

각 Insight의 리소스에는 심각도 수준이 표시된다.

| 상태 | 의미 |
|------|------|
| **PASSING** | 문제 없음 |
| **ERROR** | 다음 마이너 버전에서 제거될 API 사용 중. 업그레이드 후 동작 불가 |
| **WARNING** | 2개 이상 뒤의 버전에서 제거 예정. 즉시 조치 필요 없지만 주의 |
| **UNKNOWN** | 백엔드 처리 오류로 확인 불가 |

## CLI로 Insights 조회

대상 버전(예: 1.31)에 대한 Upgrade Insights를 조회할 수 있다.

```bash
# 대상 버전의 Upgrade Insights 조회
~$ aws eks list-insights \
    --filter kubernetesVersions=1.31 \
    --cluster-name $CLUSTER_NAME | jq .
```

특정 Insight의 상세 정보를 확인하려면 `describe-insight` 명령을 사용한다.

```bash
# 특정 Insight 상세 조회
~$ aws eks describe-insight \
    --cluster-name $CLUSTER_NAME \
    --id <insight-id>
```

## 콘솔에서 확인

EKS 콘솔에서도 Upgrade Insights를 확인할 수 있다.

1. [Amazon EKS 콘솔](https://console.aws.amazon.com/eks/home) 접속
2. 클러스터 목록에서 대상 클러스터 선택
3. Cluster info 탭에서 **Upgrade Insights** 확인

![EKS Upgrade Insights 콘솔 - 목록]({{site.url}}/assets/images/eks-upgrade-insights-console-1.png){: .align-center}

![EKS Upgrade Insights 콘솔 - 상세]({{site.url}}/assets/images/eks-upgrade-insights-console-2.png){: .align-center}

> Cluster Insights는 주기적으로 자동 업데이트된다. 수동 새로고침은 불가능하며, 문제를 수정한 후에도 반영까지 시간이 걸릴 수 있다.

## (참고) Deprecated API 매니페스트 마이그레이션

Upgrade Insights에서 Deprecated API 사용이 발견되면, `kubectl-convert` 플러그인을 사용해 매니페스트를 새 API 버전으로 변환할 수 있다.

```bash
# 매니페스트의 API 버전을 apps/v1으로 변환
~$ kubectl convert -f deployment.yaml --output-version apps/v1
```

예를 들어, 워크샵의 orders Deployment 매니페스트에 대해 실행하면 다음과 같다.

```bash
~$ kubectl convert -f manifests/base-application/orders/deployment.yaml --output-version apps/v1
```

<details markdown="1">
<summary><b>변환 결과 출력</b></summary>

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  labels:
    app.kubernetes.io/created-by: eks-workshop
    app.kubernetes.io/type: app
  name: orders
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/component: service
      app.kubernetes.io/instance: orders
      app.kubernetes.io/name: orders
  strategy:
    rollingUpdate:
      maxSurge: 25%
      maxUnavailable: 25%
    type: RollingUpdate
  template:
    metadata:
      annotations:
        prometheus.io/path: /actuator/prometheus
        prometheus.io/port: "8080"
        prometheus.io/scrape: "true"
      labels:
        app.kubernetes.io/component: service
        app.kubernetes.io/created-by: eks-workshop
        app.kubernetes.io/instance: orders
        app.kubernetes.io/name: orders
    spec:
      containers:
      - env:
        - name: JAVA_OPTS
          value: -XX:MaxRAMPercentage=75.0 -Djava.security.egd=file:/dev/urandom
        - name: SPRING_DATASOURCE_WRITER_URL
          valueFrom:
            secretKeyRef:
              key: url
              name: orders-db
        # ... DB 연결 환경변수 생략 ...
        envFrom:
        - configMapRef:
            name: orders
        image: public.ecr.aws/aws-containers/retail-store-sample-orders:0.4.0
        imagePullPolicy: IfNotPresent
        livenessProbe:
          httpGet:
            path: /actuator/health/liveness
            port: 8080
          initialDelaySeconds: 45
          periodSeconds: 3
        name: orders
        ports:
        - containerPort: 8080
          name: http
          protocol: TCP
        resources:
          limits:
            memory: 1Gi
          requests:
            cpu: 250m
            memory: 1Gi
        securityContext:
          capabilities:
            drop:
            - ALL
          readOnlyRootFilesystem: true
          runAsNonRoot: true
          runAsUser: 1000
        volumeMounts:
        - mountPath: /tmp
          name: tmp-volume
      nodeSelector:
        type: OrdersMNG
      serviceAccountName: orders
      tolerations:
      - effect: NoSchedule
        key: dedicated
        operator: Equal
        value: OrdersApp
      volumes:
      - emptyDir:
          medium: Memory
        name: tmp-volume
```

</details>

이미 `apps/v1`을 사용하고 있는 매니페스트라면, 변환 결과도 동일하게 `apps/v1`으로 출력된다. Deprecated API를 사용하는 매니페스트가 있을 때 이 도구로 새 버전으로 변환한 뒤 적용하면 된다.

![Upgrade Insights ERROR 예시]({{site.url}}/assets/images/eks-upgrade-insights-error-example.jpeg){: .align-center}

> `kubectl-convert`는 별도 플러그인으로 설치가 필요하다. [설치 가이드](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/#install-kubectl-convert-plugin)를 참고하자. 변환 후에는 원본 매니페스트를 백업하고, `kubectl apply`로 다시 적용해야 한다.

<br>

# 기본 사전 요구사항 확인

EKS 클러스터 업그레이드를 시작하기 전에, 다음 세 가지 기본 요구사항을 반드시 확인해야 한다.

## 서브넷 가용 IP 주소

EKS Control Plane 업그레이드 시, 클러스터 생성 시 지정한 서브넷에서 **최소 5개의 가용 IP 주소**가 필요하다.

```bash
# 서브넷별 가용 IP 주소 확인
~$ aws ec2 describe-subnets --subnet-ids \
    $(aws eks describe-cluster --name ${CLUSTER_NAME} \
    --query 'cluster.resourcesVpcConfig.subnetIds' \
    --output text) \
    --query 'Subnets[*].[SubnetId,AvailabilityZone,AvailableIpAddressCount]' \
    --output table
```

IP가 부족한 경우, [UpdateClusterConfiguration](https://aws.amazon.com/blogs/containers/enhanced-vpc-flexibility-modify-subnets-and-security-groups-in-amazon-eks/) API로 새 서브넷을 추가하거나, VPC에 추가 CIDR 블록을 연결하여 IP 풀을 확장할 수 있다.

## IAM 역할

클러스터의 IAM 역할이 계정에 존재하고, 올바른 assume role policy가 설정되어 있어야 한다.

```bash
# 클러스터 IAM 역할 확인
~$ ROLE_ARN=$(aws eks describe-cluster --name ${CLUSTER_NAME} \
    --query 'cluster.roleArn' --output text)
~$ aws iam get-role --role-name ${ROLE_ARN##*/} \
    --query 'Role.AssumeRolePolicyDocument'
```

## KMS 키 권한 (Secrets 암호화 시)

클러스터에서 Secrets 암호화가 활성화되어 있다면, 클러스터 IAM 역할에 AWS KMS 키에 대한 권한이 있어야 한다.

<br>

# 업그레이드 체크리스트

## 애드온 및 서드파티 도구 호환성

업그레이드 전에, 클러스터에 설치된 모든 API 의존 컴포넌트를 파악해야 한다.

```bash
# -system 네임스페이스로 핵심 컴포넌트 확인
~$ kubectl get ns | grep -e '-system'
```

주요 애드온별 호환성 확인 및 업그레이드 리소스는 다음과 같다.

| 애드온 | 업그레이드 참고 |
|--------|----------------|
| Amazon VPC CNI | 한 번에 1 마이너 버전만 업그레이드 가능 |
| kube-proxy | [kube-proxy 업데이트 가이드](https://docs.aws.amazon.com/eks/latest/userguide/managing-kube-proxy.html) |
| CoreDNS | [CoreDNS 업데이트 가이드](https://docs.aws.amazon.com/eks/latest/userguide/managing-coredns.html) |
| AWS Load Balancer Controller | [설치 가이드 - 버전 호환성](https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/deploy/installation/#supported-kubernetes-versions) |
| Amazon EBS/EFS CSI Driver | [EBS CSI](https://docs.aws.amazon.com/eks/latest/userguide/ebs-csi.html) / [EFS CSI](https://docs.aws.amazon.com/eks/latest/userguide/efs-csi.html) |
| Metrics Server | [GitHub](https://github.com/kubernetes-sigs/metrics-server) |
| Cluster Autoscaler | Deployment의 이미지 버전 변경. [GitHub Releases](https://github.com/kubernetes/autoscaler/tree/master/cluster-autoscaler#releases) |
| Karpenter | [Karpenter 문서](https://karpenter.sh/docs/getting-started/getting-started-with-karpenter/) |

## EKS 버전별 릴리즈 노트

대상 Kubernetes 버전의 EKS 문서에서 주요 변경사항을 반드시 확인한다.

- [EKS 1.31](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions-standard.html#kubernetes-1-31)
- [EKS 1.32](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions-standard.html#kubernetes-1-32)
- [EKS 1.33](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions-standard.html#kubernetes-1-33)

## 클러스터 백업

업그레이드 전 [Velero](https://velero.io/) 같은 도구를 이용해 클러스터 데이터를 백업해두는 것을 권장한다. 문제 발생 시 복원 포인트로 활용할 수 있다.

<br>

# 보안 그룹 확인

EKS가 클러스터 생성 시 자동으로 만드는 **클러스터 보안 그룹**(Cluster Security Group)의 기본 규칙을 이해하고 있어야 한다. 이 보안 그룹은 `eks-cluster-sg-<cluster-name>-<unique-id>` 형식의 이름을 가지며, 다음 태그로 식별할 수 있다.

![EKS 클러스터 보안 그룹 태그]({{site.url}}/assets/images/eks-upgrade-sg-tags.png){: .align-center}

| 태그 키 | 값 |
|---------|-----|
| `kubernetes.io/cluster/<cluster-name>` | `owned` |
| `aws:eks:cluster-name` | `<cluster-name>` |
| `Name` | `eks-cluster-sg-<cluster-name>-<unique-id>` |

## 기본 규칙

클러스터 보안 그룹의 기본 규칙은 다음과 같다.

| 방향 | 프로토콜 | 포트 | 소스/대상 |
|------|---------|------|----------|
| 인바운드 | All | All | Self (같은 보안 그룹) |
| 아웃바운드 | All | All | 0.0.0.0/0 (IPv4) / ::/0 (IPv6) |

![EKS 보안 그룹 기본 규칙]({{site.url}}/assets/images/eks-upgrade-sg-default-rules.png){: .align-center}
<center><sup>인바운드는 같은 보안 그룹(Self) 내 모든 트래픽을 허용하고, 아웃바운드는 모든 목적지로 허용한다.</sup></center>

이 보안 그룹은 다음 리소스에 자동으로 연결된다.

- 클러스터 프로비저닝 시 생성되는 2~4개의 ENI (Control Plane ↔ Data Plane 통신용)
- Managed Node Group의 ENI

## 커스텀 보안 그룹 사용 시

커스텀 보안 그룹을 사용하고 있다면, 업그레이드 과정에서 Control Plane과 노드 간 통신이 차단되지 않도록 최소한 다음 아웃바운드 규칙이 필요하다.

| 방향 | 프로토콜 | 포트 | 대상 |
|------|---------|------|------|
| Outbound | TCP | 443 | Cluster Security Group |
| Outbound | TCP | 10250 | Cluster Security Group |
| Outbound (DNS) | TCP/UDP | 53 | Cluster Security Group |

![EKS 보안 그룹 트래픽 제한 시 필수 규칙]({{site.url}}/assets/images/eks-upgrade-sg-restricting-traffic.png){: .align-center}
<center><sup>커스텀 보안 그룹으로 트래픽을 제한할 경우, API 서버(443), kubelet(10250), DNS(53) 포트는 반드시 열어두어야 한다.</sup></center>

<br>

# 애플리케이션 배포 관리

업그레이드 과정에서 애플리케이션을 일관되게 배포하려면, 표준화된 패키징 도구를 사용하는 것이 좋다.

## Helm Charts

Helm은 Kubernetes 애플리케이션을 패키지(Chart)로 관리하고, 표준화된 형식으로 배포할 수 있게 해주는 도구다. 업그레이드 시 Chart 버전을 관리하면, 환경 간 일관된 배포가 가능하다.

## GitOps (ArgoCD)

GitOps는 Git 저장소를 단일 진실의 원천(Single Source of Truth)으로 삼아 애플리케이션을 배포하는 방식이다. 이 워크숍에서는 ArgoCD를 사용하여 애플리케이션을 관리한다.

ArgoCD는 Git 저장소의 매니페스트를 기반으로 Kubernetes 클러스터의 상태를 지속적으로 동기화한다. 업그레이드 과정에서 매니페스트 변경이 필요할 때, Git에 커밋하면 ArgoCD가 자동으로 클러스터에 반영한다.

> 이 워크숍에서는 ArgoCD를 GitOps 도구로 활용하여, 업그레이드 과정에서의 애플리케이션 배포를 관리한다.

<br>

# PodDisruptionBudget 설정

Data Plane 업그레이드 시 워커 노드를 drain하면, 해당 노드의 파드가 축출(evict)된다. 이때 핵심 서비스의 가용성을 보장하려면, [PodDisruptionBudget(PDB)](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/#pod-disruption-budgets)과 [TopologySpreadConstraints](https://kubernetes.io/docs/concepts/workloads/pods/pod-topology-spread-constraints/)를 설정해야 한다.

## PDB 예시

아래 PDB는 `orders` Deployment에서 최소 1개의 파드가 항상 가용하도록 보장한다.

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-pdb
  namespace: orders
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app.kubernetes.io/component: service
      app.kubernetes.io/instance: orders
      app.kubernetes.io/name: orders
```

## PDB 동작 확인

PDB가 설정된 상태에서 노드를 drain하면, PDB 조건을 위반하는 파드 축출은 거부된다.

```bash
# PDB 상태 확인
~$ kubectl get pdb orders-pdb -n orders

# 실행 결과
NAME         MIN AVAILABLE   MAX UNAVAILABLE   ALLOWED DISRUPTIONS   AGE
orders-pdb   1               N/A               0                     5s
```

노드를 drain할 때 PDB가 동작하는 것을 확인할 수 있다.

```bash
# 노드 drain 시도
~$ kubectl drain "$nodeName" --ignore-daemonsets --force --delete-emptydir-data

# PDB 위반 시 에러 발생
error when evicting pods/"orders-xxxxx-yyyyy" -n "orders" (will retry after 5s):
Cannot evict pod as it would violate the pod's disruption budget.
```

레플리카가 1인 Deployment에 `minAvailable: 1` PDB를 설정하면, 새 파드가 다른 노드에 스케줄링되기 전까지는 기존 파드를 축출할 수 없다. 따라서 가용성 요구사항에 맞게 레플리카 수와 PDB 값을 조정해야 한다.

> 워크로드를 여러 가용 영역(AZ)과 호스트에 분산하는 TopologySpreadConstraints를 함께 설정하면, 노드 업그레이드 시 워크로드가 자동으로 새 Data Plane으로 마이그레이션될 가능성이 높아진다.

<br>

# 정리

EKS 클러스터 업그레이드를 시작하기 전에 확인해야 할 준비사항을 정리하면 다음과 같다.

| 단계 | 확인 사항 |
|------|-----------|
| 사전 요구사항 | 서브넷 가용 IP(5개 이상), IAM 역할, KMS 키 권한 |
| Upgrade Insights | Deprecated API, 애드온 호환성, 컴포넌트 버전 스큐 점검 |
| 릴리즈 노트 | 대상 K8s 버전의 EKS 릴리즈 노트 확인 |
| 애드온 호환성 | CoreDNS, kube-proxy, VPC CNI 등 각 애드온의 호환 버전 확인 |
| 보안 그룹 | CP-노드 간 통신 규칙 확인 |
| 클러스터 백업 | Velero 등으로 클러스터 데이터 백업 |
| PDB 설정 | 핵심 서비스에 PodDisruptionBudget 적용 |
| 배포 관리 | Helm Charts 또는 GitOps(ArgoCD) 활용 |

다음 글에서는 실습 환경을 확인하고, 본격적으로 업그레이드를 실행해 본다.

<br>

# 참고 링크

- [Amazon EKS Cluster Upgrades Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html)
- [EKS Upgrade Insights](https://docs.aws.amazon.com/eks/latest/userguide/cluster-insights.html)
- [Kubernetes PodDisruptionBudget](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/#pod-disruption-budgets)
- [Kubernetes TopologySpreadConstraints](https://kubernetes.io/docs/concepts/workloads/pods/pod-topology-spread-constraints/)
- [kubectl-convert 설치](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/#install-kubectl-convert-plugin)

<br>
