---
title: "[EKS] LLM 서빙과 최적화: vLLM on Trainium 워크샵 - 8.2.1. Trainium 노드그룹 구성"
excerpt: "EKS 컨트롤 플레인만 있는 상태에서 trn1.2xlarge 관리형 노드그룹을 붙이고, 미리 박혀 있던 AMI ID 때문에 막힌 지점을 풀어 보자."
categories:
  - Kubernetes
toc: true
use_math: false
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - EKS
  - AWS
  - Trainium
  - Neuron
  - eksctl
  - vLLM
  - Hands-On-LLM-Serving-and-Optimization-Study
  - Hands-On-LLM-Serving-and-Optimization-Study-Week-6
last_modified_at: 2026-09-12
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Hands-On LLM Serving and Optimization Study (LLMSO) 6주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- 워크샵이 만들어 둔 것은 EKS 컨트롤 플레인까지다. `trn1.2xlarge` 관리형 노드그룹은 실습자가 `eksctl`로 직접 붙인다. `coredns` 파드 2개가 8시간째 `Pending`인 것이 그 상태의 증거였다
- 노드그룹 네트워킹은 세 단계 필터로 정해진다 — 컨트롤 플레인과 같은 VPC → 인스턴스 타입이 제공되는 가용 영역(AZ) → 그 AZ에 있는 퍼블릭 서브넷. 인스턴스 타입이 AZ를 고르고 AZ가 서브넷을 고르므로 순서를 뒤집으면 안 된다
- 워크샵 셸에 미리 세팅돼 있던 `WORKER_AMI`가 이미 deregister된 AMI ID라 첫 배포가 `InvalidAMIID.NotFound`로 실패했다. 같은 셸에서 SSM을 직접 조회한 값과 환경변수 값이 다르다는 것 자체가, 그 값의 출처가 SSM이 아니라는 증거다
- 교훈은 두 줄이다 — AMI ID는 매번 SSM 파라미터에서 조회한다, 워크샵 환경에 미리 세팅된 값은 실제 값과 대조하고 쓴다
- 노드가 `Ready`가 되면 `aws.amazon.com/neuron: 1`과 `aws.amazon.com/neuroncore: 2`가 함께 광고된다. 칩 하나에 리소스가 왜 두 개인지는 [다음 편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-02-02-Neuron-Device-Exposure %})에서 다룬다
- `kubectl label`이 내놓는 `not labeled`는 실패가 아니라 no-op이다. `eksctl`이 노드 join 시점에 같은 라벨을 이미 심어 두기 때문이다

<br>

# 실습 환경

이 글은 워크샵 Lab 1의 스텝 1~6과 8~9에 해당한다. 스텝 7(Neuron device plugin 재설치와 스케줄러 확장 설치)은 성격이 달라 [08-02-02편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-02-02-Neuron-Device-Exposure %})에서 따로 다룬다. 워크샵 전체 구성과 아키텍처는 [08-00편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-00-EKS-Workshop-Overview %}), Trainium과 NeuronCore 배경지식은 [08-01편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-01-AWS-Accelerators %})에 있다.

작업은 전부 워크샵이 제공하는 배스천(bastion) 인스턴스에 SSH로 붙어서 진행한다. 아래 출력의 셸 프롬프트 `ubuntu@ip-10-0-1-100`이 그 인스턴스다. 이 글의 모든 출력에서 계정 ID, 클러스터명, VPC·서브넷·인스턴스 ID, 호스트명, IP는 예시 값으로 치환했다. 다만 **AMI ID 두 개(`ami-08695d32a8bb6c5a5`, `ami-0e08c07b0376ba3f8`)는 그대로 뒀다** — 두 값이 다르다는 사실 자체가 이 글 후반부 트러블슈팅의 증거이기 때문이다.

## 워크샵이 미리 만들어 둔 것

컨트롤 플레인은 이미 떠 있고, 워커 노드는 하나도 없는 상태에서 시작한다.

```shell
# kubeconfig를 갱신해 컨트롤 플레인에 붙는다
ubuntu@ip-10-0-1-100:~/workshop$ aws eks update-kubeconfig --region $AWS_REGION --name $CLUSTER_NAME
Added new context arn:aws:eks:us-west-2:123456789012:cluster/my-neuron-cluster to /home/ubuntu/.kube/config

# 워커 노드가 없으니 coredns가 배치될 곳이 없다
ubuntu@ip-10-0-1-100:~/workshop$ kubectl get pod -A
NAMESPACE     NAME                       READY   STATUS    RESTARTS   AGE
kube-system   coredns-75cb89d95b-6lz4d   0/1     Pending   0          8h
kube-system   coredns-75cb89d95b-k6csj   0/1     Pending   0          8h

# 컨트롤 플레인 엔드포인트는 정상 응답한다
ubuntu@ip-10-0-1-100:~/workshop$ kubectl cluster-info
Kubernetes control plane is running at https://ABCDEF0123456789.gr7.us-west-2.eks.amazonaws.com
CoreDNS is running at https://ABCDEF0123456789.gr7.us-west-2.eks.amazonaws.com/api/v1/namespaces/kube-system/services/kube-dns:dns/proxy
```

`coredns` 2개가 8시간째 `Pending`이라는 것은 클러스터가 고장 났다는 뜻이 아니라, 스케줄 대상 노드가 아직 하나도 없다는 뜻이다. 워크샵 환경이 만들어진 시점부터 이 상태로 대기해 온 것이고, 노드그룹을 붙이는 순간 두 파드가 함께 배치된다.

<details markdown="1">
<summary><b>aws eks update-kubeconfig 이후 ~/.kube/config 전문</b></summary>

```yaml
apiVersion: v1
clusters:
- cluster:
    # 인증서 본문은 앞부분만 남기고 생략했다
    certificate-authority-data: LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCk1J...(생략)
    server: https://ABCDEF0123456789.gr7.us-west-2.eks.amazonaws.com
  name: arn:aws:eks:us-west-2:123456789012:cluster/my-neuron-cluster
contexts:
- context:
    cluster: arn:aws:eks:us-west-2:123456789012:cluster/my-neuron-cluster
    user: arn:aws:eks:us-west-2:123456789012:cluster/my-neuron-cluster
  name: arn:aws:eks:us-west-2:123456789012:cluster/my-neuron-cluster
current-context: arn:aws:eks:us-west-2:123456789012:cluster/my-neuron-cluster
kind: Config
preferences: {}
users:
- name: arn:aws:eks:us-west-2:123456789012:cluster/my-neuron-cluster
  user:
    # 토큰을 파일에 저장하지 않고, 호출 때마다 aws eks get-token으로 받아 온다
    exec:
      apiVersion: client.authentication.k8s.io/v1beta1
      args:
      - --region
      - us-west-2
      - eks
      - get-token
      - --cluster-name
      - my-neuron-cluster
      - --output
      - json
      command: aws
```

</details>

![EKS 컨트롤 플레인만 생성되어 있는 상태]({{site.url}}/assets/images/llmso-aws-workshop-lab1-eks-control-plane.png){: .align-center}
<center><sup>직접 캡처. 클러스터명은 익명화를 위해 블러 처리했다. 표시한 대로 노드 0개, 노드 그룹 0개 상태다</sup></center>

콘솔에서도 같은 상태가 보인다. 클러스터는 활성이고 쿠버네티스 버전은 1.33인데, 노드와 노드 그룹은 둘 다 0이다. 노드 목록에 뜬 `Unauthorized`는 콘솔 로그인 주체가 클러스터의 access entry에 없어서 나는 것이고, 배스천 셸의 `kubectl`은 정상 동작한다.

## 도구 설치

배스천에는 `kubectl`과 `eksctl`이 이미 깔려 있고, 나머지를 워크샵 스크립트가 설치한다.

| 도구 | 설치 방법 | 확인한 버전 |
|---|---|---|
| AWS CLI v2 | `awscli-exe-linux-x86_64.zip` 내려받아 `./aws/install --update` | `aws-cli/2.36.43` |
| Helm | `get-helm-3` 스크립트 | `v3.22.0+g144ca65` |
| jq | `apt install` | `jq-1.6` |
| python3-pip, unzip | `apt install` | - |
| kubectl 자동완성 | `source <(kubectl completion bash)` + `~/.bashrc` 추가 | - |

`apt update` 자체는 배스천이 퍼블릭 서브넷에 있어 그대로 통과한다. 여기서 설치하는 Helm은 뒤에서 S3 CSI 드라이버를 깔 때, 그리고 [08-02-02편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-02-02-Neuron-Device-Exposure %})에서 Neuron device plugin을 다시 깔 때 쓴다.

## 미리 세팅된 환경변수

워크샵 문서는 아래 변수들을 설정하라고 안내한다.

```bash
export AWS_REGION=us-west-2
export CLUSTER_NAME=my-neuron-cluster
export EKS_VERSION=1.33
export INSTANCE_TYPE=trn1.2xlarge
export DESIRED_NODES=1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export BUCKET_NAME=vllm-models-cache-${AWS_ACCOUNT_ID}

# 워커 노드 AMI: amazon-linux-2023 + neuron 경로 → Neuron 가속기용 EKS 최적화 AMI다
export WORKER_AMI=$(aws ssm get-parameter \
    --name /aws/service/eks/optimized-ami/1.33/amazon-linux-2023/x86_64/neuron/recommended/image_id \
    --region $AWS_REGION \
    --query "Parameter.Value" \
    --output text)

echo "$CLUSTER_NAME $WORKER_AMI $AWS_ACCOUNT_ID $BUCKET_NAME"
```

그런데 배스천에 붙어 보니 이 값들이 전부 이미 설정돼 있었다. 그래서 다시 설정하지 않고 지나갔는데, 그 판단이 뒤에서 노드그룹 배포를 막는다.

```shell
# env 전문 중 워크샵이 심어 둔 변수만 발췌했다
ubuntu@ip-10-0-1-100:~/workshop$ env
...
CLUSTER_NAME=my-neuron-cluster
EKS_VERSION=1.33
AWS_REGION=us-west-2
DESIRED_NODES=1
BUCKET_NAME=vllm-models-cache-123456789012
AWS_ACCOUNT_ID=123456789012
WORKER_AMI=ami-08695d32a8bb6c5a5     # 미리 박혀 있던 AMI ID
INSTANCE_TYPE=trn1.2xlarge
...

# 같은 셸, 같은 리전에서 SSM 파라미터를 직접 조회해 본 결과
ubuntu@ip-10-0-1-100:~/workshop$ aws ssm get-parameter \
>     --name /aws/service/eks/optimized-ami/1.33/amazon-linux-2023/x86_64/neuron/recommended/image_id \
>     --region $AWS_REGION \
>     --query "Parameter.Value" \
>     --output text
ami-0e08c07b0376ba3f8                # 환경변수에 박혀 있던 값과 다르다

ubuntu@ip-10-0-1-100:~/workshop$ echo "$CLUSTER_NAME $WORKER_AMI $AWS_ACCOUNT_ID $BUCKET_NAME"
my-neuron-cluster ami-08695d32a8bb6c5a5 123456789012 vllm-models-cache-123456789012
```

`WORKER_AMI`가 SSM 조회 결과와 다르다. 워크샵 문서가 안내하는 명령은 `aws ssm get-parameter`로 값을 받아 오는 것인데, 셸에 이미 들어 있던 값은 그 결과와 일치하지 않았다. 이 불일치가 [막힘 & 해결: 존재하지 않는 AMI](#막힘--해결-존재하지-않는-ami)에서 다룰 사고의 출발점이다.

노드 접속용 SSH 키를 만드는 옵션 단계도 있지만, 이 실습에서는 AWS Systems Manager Session Manager로 워커 노드에 붙는 편이 간단했다. 노드그룹 IAM 정책에 `AmazonSSMManagedInstanceCore`가 이미 들어가 있어 추가 설정이 필요 없다.

<br>

# 클러스터 네트워킹 해부

노드그룹을 붙이려면 VPC ID, 서브넷 ID, 보안그룹 ID를 `ClusterConfig`에 사람이 직접 채워 넣어야 한다. 세 값은 각각 다른 이유로 필요하고, 구하는 순서도 정해져 있다 — **VPC는 클러스터에서 캐내고, AZ는 인스턴스 타입이 정하고, 서브넷은 그 AZ 안에서 고른다.**

## 클러스터와 같은 VPC에 붙어야 하는 이유

EKS 컨트롤 플레인은 사용자 VPC의 서브넷에 cross-account ENI를 꽂아 워커 노드와 통신한다. 노드가 다른 VPC에 있으면 kubelet이 API 서버에 등록되지 못한다. 그래서 노드그룹은 반드시 클러스터와 같은 VPC 안에 만들어야 한다.

여기에 이 실습 특유의 사정이 하나 더 붙는다. 이 클러스터는 `eksctl`이 만든 것이 아니라 워크샵의 CloudFormation이 미리 만든 것이다. `eksctl`은 자기가 만든 스택이 없으면 VPC를 추론할 근거가 없으므로, `vpc.id`·`vpc.subnets`·`vpc.securityGroup`을 설정 파일로 받아야 한다. 그래서 클러스터에서 직접 조회한다.

```shell
# 클러스터가 쓰고 있는 VPC를 캐낸다
ubuntu@ip-10-0-1-100:~/workshop$ VPC_ID=$(aws eks describe-cluster --name $CLUSTER_NAME --region $AWS_REGION \
>   --query 'cluster.resourcesVpcConfig.vpcId' --output text)

# 0.0.0.0/0 기본 경로를 가진 라우트 테이블 = 인터넷 게이트웨이로 나가는 경로
ubuntu@ip-10-0-1-100:~/workshop$ PUBLIC_ROUTE_TABLE=$(aws ec2 describe-route-tables \
>   --filters "Name=vpc-id,Values=$VPC_ID" "Name=route.destination-cidr-block,Values=0.0.0.0/0" \
>   --query 'RouteTables[0].RouteTableId' --output text)
ubuntu@ip-10-0-1-100:~/workshop$ echo "$VPC_ID $PUBLIC_ROUTE_TABLE"
vpc-0abc1234def567890 rtb-0abc1234def567890
```

`eksctl`이 이 상황을 어떻게 인식하는지는 나중에 노드그룹 생성 로그 첫 줄에 그대로 나온다 — `no eksctl-managed CloudFormation stacks found ... will attempt to create nodegroup(s) on non eksctl-managed cluster`.

## 가용 영역을 제한하는 인스턴스 타입

`trn1.2xlarge`는 리전의 모든 가용 영역에 있지 않다. 그래서 서브넷을 고르기 전에 인스턴스 타입이 제공되는 AZ부터 구한다.

```shell
# 인스턴스 타입이 제공되는 AZ 목록을 배열로 받는다
ubuntu@ip-10-0-1-100:~/workshop$ SUPPORTED_AZS=($(aws ec2 describe-instance-type-offerings \
>   --location-type availability-zone \
>   --filters "Name=instance-type,Values=$INSTANCE_TYPE" \
>   --query 'InstanceTypeOfferings[*].Location' --output text))
ubuntu@ip-10-0-1-100:~/workshop$ echo "$SUPPORTED_AZS"
us-west-2b

# 각 AZ에서 퍼블릭 서브넷을 하나씩 골라 배열에 담는다
ubuntu@ip-10-0-1-100:~/workshop$ VALID_SUBNETS=()
ubuntu@ip-10-0-1-100:~/workshop$ for az in "${SUPPORTED_AZS[@]}"; do
>   subnet=$(aws ec2 describe-subnets \
>     --filters "Name=vpc-id,Values=$VPC_ID" "Name=map-public-ip-on-launch,Values=true" "Name=availability-zone,Values=$az" \
>     --query 'Subnets[0].SubnetId' --output text)
>   [ "$subnet" != "None" ] && [ "$subnet" != "" ] && VALID_SUBNETS+=("$subnet")
> done
ubuntu@ip-10-0-1-100:~/workshop$ echo ${VALID_SUBNETS[0]}
subnet-0aaa1111bbb222233
ubuntu@ip-10-0-1-100:~/workshop$ echo ${VALID_SUBNETS[1]}
subnet-0ccc4444ddd555566

# 서로 다른 AZ의 퍼블릭 서브넷이 2개 미만이면 여기서 중단한다
ubuntu@ip-10-0-1-100:~/workshop$ [ ${#VALID_SUBNETS[@]} -lt 2 ] && { echo "Error: Need at least 2 public subnets in AZs that support $INSTANCE_TYPE"; exit 1; }

ubuntu@ip-10-0-1-100:~/workshop$ PUBLIC_SUBNET_1=${VALID_SUBNETS[0]}
ubuntu@ip-10-0-1-100:~/workshop$ PUBLIC_SUBNET_2=${VALID_SUBNETS[1]}
ubuntu@ip-10-0-1-100:~/workshop$ AZ_1=$(aws ec2 describe-subnets --subnet-ids $PUBLIC_SUBNET_1 --query 'Subnets[0].AvailabilityZone' --output text)
ubuntu@ip-10-0-1-100:~/workshop$ AZ_2=$(aws ec2 describe-subnets --subnet-ids $PUBLIC_SUBNET_2 --query 'Subnets[0].AvailabilityZone' --output text)
ubuntu@ip-10-0-1-100:~/workshop$ echo $AZ_1 $AZ_2
us-west-2b us-west-2d
```

여기서 출력 하나를 잘못 읽을 뻔했다. `echo "$SUPPORTED_AZS"`가 `us-west-2b` 하나만 찍어서 "제공 AZ가 하나뿐"이라고 적어 뒀는데, bash에서 배열을 `"$arr"`로 참조하면 `"${arr[0]}"`와 같아 **첫 원소만 출력된다.** 전체를 보려면 `"${SUPPORTED_AZS[@]}"`여야 한다. 실제로 제공 AZ가 둘 이상이었다는 증거는 같은 출력 안에 있다 — `${VALID_SUBNETS[1]}`이 값을 내놓았고 `AZ_2`가 `us-west-2d`로 나왔다.

이 차이가 중요한 이유는 `ClusterConfig`의 `vpc.subnets.public`이 서로 다른 AZ의 서브넷을 2개 이상 요구하기 때문이다. 워크샵 스크립트가 `[ ${#VALID_SUBNETS[@]} -lt 2 ]`에서 조기 종료하도록 만들어 둔 것도 같은 이유다. 인스턴스 타입이 AZ를 고르고 AZ가 서브넷을 고르는 순서라, 이 순서를 뒤집으면 노드그룹 생성 단계에서 용량 또는 미지원 오류로 넘어간다.

## 퍼블릭 서브넷을 쓰는 이유

서브넷 필터가 `map-public-ip-on-launch=true`라는 점이 핵심이다. 이 조건에 맞는 서브넷에 뜬 인스턴스는 퍼블릭 IP를 자동으로 받는다.

노드가 바깥으로 나가야 할 곳이 적지 않다.

- `public.ecr.aws` — Neuron device plugin, Neuron scheduler, vLLM 컨테이너 이미지
- EKS 퍼블릭 API 엔드포인트 — kubelet 등록과 통신
- SSM — Session Manager로 노드에 접속
- S3, Hugging Face — 모델 가중치와 컴파일 캐시

앞서 `PUBLIC_ROUTE_TABLE`을 `route.destination-cidr-block=0.0.0.0/0`으로 찾은 것은 인터넷 게이트웨이(IGW) 기본 경로가 있는 라우트 테이블을 고른 것이다. 노드에 퍼블릭 IP를 직접 붙여 IGW로 내보내는 구성이고, 실제로 그렇게 됐다는 증거는 뒤에서 볼 [노드 등록 결과](#노드-등록-결과)에 있다 — `ExternalIP`와 `ExternalDNS`가 채워져 있다. 프라이빗 서브넷 + NAT 게이트웨이 구성이었다면 이 필드가 비어 있다.

> 이 VPC에 NAT 게이트웨이가 아예 없는지는 직접 조회하지 않았다. 확인한 범위는 "노드에 퍼블릭 IP가 붙었고 IGW 경로가 있는 서브넷을 골랐다"까지다.

<br>

# 적용과 관찰: 노드그룹과 스토리지

## ClusterConfig 작성

앞에서 구한 값들을 heredoc으로 전개해 `eks_nodegroup.yaml`을 만든다. 전개 결과는 다음과 같다.

```yaml
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig
metadata:
  name: my-neuron-cluster
  region: us-west-2
  version: "1.33"
# eksctl이 만든 클러스터가 아니므로 VPC/서브넷/보안그룹을 직접 지정한다
vpc:
  id: vpc-0abc1234def567890
  subnets:
    public:
      us-west-2b: { id: subnet-0aaa1111bbb222233 }
      us-west-2d: { id: subnet-0ccc4444ddd555566 }
  securityGroup: sg-0abc1234def567890
managedNodeGroups:
- name: neuron-trn1-2x
  ami: ami-08695d32a8bb6c5a5        # 환경변수에서 전개된 값. 이 값이 문제였다
  amiFamily: AmazonLinux2023
  subnets: ["subnet-0aaa1111bbb222233", "subnet-0ccc4444ddd555566"]
  iam:
    attachPolicyARNs:
    - arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy
    - arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly
    - arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
    - arn:aws:iam::aws:policy/AmazonS3FullAccess
    - arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy
  instanceType: trn1.2xlarge
  desiredCapacity: 1
  volumeSize: 100
  volumeType: gp2
  ssh:
     allow: true
     publicKeyPath: ~/.ssh/id_rsa.pub
```

`ami`를 직접 지정하면 `amiFamily`도 함께 지정해야 `eksctl`이 부트스트랩 방식을 결정할 수 있다. IAM 정책 5개는 각각 다음을 담당한다.

| 정책 | 용도 |
|---|---|
| `AmazonEKSWorkerNodePolicy` | kubelet이 클러스터에 등록하고 노드 정보를 갱신 |
| `AmazonEC2ContainerRegistryReadOnly` | ECR에서 컨테이너 이미지 pull |
| `AmazonSSMManagedInstanceCore` | Session Manager로 노드 셸 접속 |
| `AmazonS3FullAccess` | 모델 캐시 버킷 읽기·쓰기 (뒤의 S3 CSI 드라이버가 사용) |
| `AmazonEKS_CNI_Policy` | VPC CNI가 ENI·보조 IP를 파드에 할당 |

<details markdown="1">
<summary><b>heredoc으로 eks_nodegroup.yaml을 생성하는 명령 전문</b></summary>

```shell
ubuntu@ip-10-0-1-100:~/workshop$ cat > eks_nodegroup.yaml <<EOF
> apiVersion: eksctl.io/v1alpha5
> kind: ClusterConfig
> metadata:
>   name: $CLUSTER_NAME
>   region: $AWS_REGION
>   version: "$EKS_VERSION"
> vpc:
>   id: $VPC_ID
>   subnets:
>     public:
>       $AZ_1: { id: $PUBLIC_SUBNET_1 }
>       $AZ_2: { id: $PUBLIC_SUBNET_2 }
>   securityGroup: $(aws eks describe-cluster --name $CLUSTER_NAME --region $AWS_REGION --query 'cluster.resourcesVpcConfig.clusterSecurityGroupId' --output text)
> managedNodeGroups:
> - name: neuron-trn1-2x
>   ami: $WORKER_AMI
>   amiFamily: AmazonLinux2023
>   subnets: ["$PUBLIC_SUBNET_1", "$PUBLIC_SUBNET_2"]
>   iam:
>     attachPolicyARNs:
>     - arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy
>     - arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly
>     - arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
>     - arn:aws:iam::aws:policy/AmazonS3FullAccess
>     - arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy
>   instanceType: $INSTANCE_TYPE
>   desiredCapacity: $DESIRED_NODES
>   volumeSize: 100
>   volumeType: gp2
>   ssh:
>      allow: true
>      publicKeyPath: ~/.ssh/id_rsa.pub
> EOF
```

heredoc은 작성 시점의 변수 값을 그대로 굽는다. 즉 `$WORKER_AMI`가 낡은 값이면 그 값이 YAML에 박히고, 나중에 환경변수만 고쳐도 파일은 바뀌지 않는다.

</details>

## 노드그룹 배포

첫 시도는 AMI를 찾지 못해 실패했다. 증상과 원인, 해결은 [막힘 & 해결: 존재하지 않는 AMI](#막힘--해결-존재하지-않는-ami)에 따로 정리했고, 여기서는 AMI를 바로잡고 재실행한 결과를 본다.

```shell
# 노드그룹 생성 (3~4분 소요)
ubuntu@ip-10-0-1-100:~/workshop$ eksctl create nodegroup --config-file=eks_nodegroup.yaml

# 실행 결과 (발췌)
2026-09-11 12:36:21 [!]  no eksctl-managed CloudFormation stacks found for "my-neuron-cluster", will attempt to create nodegroup(s) on non eksctl-managed cluster
2026-09-11 12:36:21 [ℹ]  nodegroup "neuron-trn1-2x" will use "ami-0e08c07b0376ba3f8" [AmazonLinux2023/1.33]
2026-09-11 12:39:12 [ℹ]  1 task: { install Neuron device plugin }
2026-09-11 12:39:12 [ℹ]  as you are using the EKS-Optimized Accelerated AMI with an inf1 instance type, the AWS Neuron Kubernetes device plugin was automatically installed.
	to skip installing it, use --install-neuron-plugin=false.
2026-09-11 12:39:12 [ℹ]  node "ip-10-0-5-100.us-west-2.compute.internal" is ready
2026-09-11 12:39:12 [✔]  created 1 managed nodegroup(s) in cluster "my-neuron-cluster"
```

첫 줄의 `[!]` 경고는 정상이다. 컨트롤 플레인이 `eksctl`이 아니라 워크샵 CloudFormation으로 만들어졌기 때문에 나오는 것이고, 노드그룹 생성 자체는 그대로 진행된다.

눈여겨볼 것은 `install Neuron device plugin`이다. `eksctl`이 노드그룹을 만든 뒤 Neuron device plugin을 알아서 설치했다. 메시지 문구는 `inf1 instance type`이라고 쓰지만 실제 인스턴스 타입은 `trn1.2xlarge`이고, `--install-neuron-plugin=false`로 끌 수 있다고 안내한다. 이 자동 설치분이 나중에 Helm으로 다시 까는 쪽과 충돌하는데, 그 이야기는 [08-02-02편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-02-02-Neuron-Device-Exposure %})에서 다룬다.

<details markdown="1">
<summary><b>eksctl create nodegroup 전체 출력</b></summary>

```shell
ubuntu@ip-10-0-1-100:~/workshop$ eksctl create nodegroup --config-file=eks_nodegroup.yaml
2026-09-11 12:36:21 [!]  no eksctl-managed CloudFormation stacks found for "my-neuron-cluster", will attempt to create nodegroup(s) on non eksctl-managed cluster
2026-09-11 12:36:21 [ℹ]  nodegroup "neuron-trn1-2x" will use "ami-0e08c07b0376ba3f8" [AmazonLinux2023/1.33]
2026-09-11 12:36:21 [ℹ]  using SSH public key "/home/ubuntu/.ssh/id_rsa.pub" as "eksctl-my-neuron-cluster-nodegroup-neuron-trn1-2x-xx:xx:xx:xx:xx:xx"
2026-09-11 12:36:22 [ℹ]  1 nodegroup (neuron-trn1-2x) was included (based on the include/exclude rules)
2026-09-11 12:36:22 [ℹ]  will create a CloudFormation stack for each of 1 managed nodegroups in cluster "my-neuron-cluster"
2026-09-11 12:36:22 [ℹ]  1 task: { 1 task: { 1 task: { create managed nodegroup "neuron-trn1-2x" } } }
2026-09-11 12:36:22 [ℹ]  building managed nodegroup stack "eksctl-my-neuron-cluster-nodegroup-neuron-trn1-2x"
2026-09-11 12:36:22 [ℹ]  deploying stack "eksctl-my-neuron-cluster-nodegroup-neuron-trn1-2x"
2026-09-11 12:36:22 [ℹ]  waiting for CloudFormation stack "eksctl-my-neuron-cluster-nodegroup-neuron-trn1-2x"
2026-09-11 12:36:52 [ℹ]  waiting for CloudFormation stack "eksctl-my-neuron-cluster-nodegroup-neuron-trn1-2x"
2026-09-11 12:37:26 [ℹ]  waiting for CloudFormation stack "eksctl-my-neuron-cluster-nodegroup-neuron-trn1-2x"
2026-09-11 12:39:12 [ℹ]  waiting for CloudFormation stack "eksctl-my-neuron-cluster-nodegroup-neuron-trn1-2x"
2026-09-11 12:39:12 [ℹ]  1 task: { install Neuron device plugin }
2026-09-11 12:39:12 [ℹ]  created "ClusterRole.rbac.authorization.k8s.io/neuron-device-plugin"
2026-09-11 12:39:12 [ℹ]  created "kube-system:ServiceAccount/neuron-device-plugin"
2026-09-11 12:39:12 [ℹ]  created "kube-system:ClusterRoleBinding.rbac.authorization.k8s.io/neuron-device-plugin"
2026-09-11 12:39:12 [ℹ]  created "kube-system:DaemonSet.apps/neuron-device-plugin"
2026-09-11 12:39:12 [ℹ]  as you are using the EKS-Optimized Accelerated AMI with an inf1 instance type, the AWS Neuron Kubernetes device plugin was automatically installed.
	to skip installing it, use --install-neuron-plugin=false.
2026-09-11 12:39:12 [✔]  created 0 nodegroup(s) in cluster "my-neuron-cluster"
2026-09-11 12:39:12 [ℹ]  nodegroup "neuron-trn1-2x" has 1 node(s)
2026-09-11 12:39:12 [ℹ]  node "ip-10-0-5-100.us-west-2.compute.internal" is ready
2026-09-11 12:39:12 [ℹ]  waiting for at least 1 node(s) to become ready in "neuron-trn1-2x"
2026-09-11 12:39:12 [ℹ]  nodegroup "neuron-trn1-2x" has 1 node(s)
2026-09-11 12:39:12 [ℹ]  node "ip-10-0-5-100.us-west-2.compute.internal" is ready
2026-09-11 12:39:12 [✔]  created 1 managed nodegroup(s) in cluster "my-neuron-cluster"
2026-09-11 12:39:12 [ℹ]  checking security group configuration for all nodegroups
2026-09-11 12:39:12 [ℹ]  all nodegroups have up-to-date cloudformation templates
```

`created 0 nodegroup(s)`와 `created 1 managed nodegroup(s)`가 나란히 찍히는데, 앞쪽은 비관리형(unmanaged) 노드그룹 개수이고 뒤쪽이 이번에 만든 관리형 노드그룹이다.

</details>

## 노드 등록 결과

노드 하나가 `Ready` 상태로 등록됐다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ kubectl wait --for=condition=Ready nodes --all --timeout=300s
node/ip-10-0-5-100.us-west-2.compute.internal condition met

ubuntu@ip-10-0-1-100:~/workshop$ kubectl get nodes -o wide

# 실행 결과 (일부 열 생략)
NAME                                       STATUS   ROLES    AGE     VERSION                INTERNAL-IP   EXTERNAL-IP     CONTAINER-RUNTIME
ip-10-0-5-100.us-west-2.compute.internal   Ready    <none>   6m14s   v1.33.13-eks-cb19647   10.0.5.100    203.0.113.10    containerd://2.2.5+unknown
```

`EXTERNAL-IP`가 채워져 있다 — [퍼블릭 서브넷을 쓰는 이유](#퍼블릭-서브넷을-쓰는-이유)에서 말한 구성이 실제로 적용된 결과다. `describe node`에서 확인할 부분은 두 군데다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ kubectl describe node

# 실행 결과 (Labels 발췌) - eksctl이 join 시점에 심은 라벨 2개
Labels:             alpha.eksctl.io/cluster-name=my-neuron-cluster
                    alpha.eksctl.io/nodegroup-name=neuron-trn1-2x
                    ...
                    eks.amazonaws.com/nodegroup-image=ami-0e08c07b0376ba3f8
                    node.kubernetes.io/instance-type=trn1.2xlarge
                    topology.kubernetes.io/zone=us-west-2b

# 실행 결과 (Capacity / Allocatable 발췌)
Capacity:
  aws.amazon.com/neuron:      1
  aws.amazon.com/neuroncore:  2
  cpu:                        8
  ephemeral-storage:          104779756Ki
  memory:                     32332248Ki
  pods:                       58
Allocatable:
  aws.amazon.com/neuron:      1
  aws.amazon.com/neuroncore:  2
  cpu:                        7910m
  ephemeral-storage:          95491281146
  memory:                     31315416Ki
  pods:                       58
```

칩 하나짜리 노드인데 확장 리소스(extended resource)가 두 종류 광고된다. `aws.amazon.com/neuron`이 1, `aws.amazon.com/neuroncore`가 2다. 왜 두 개인지, 그리고 이 둘을 섞어 쓰면 어떤 문제가 생기는지는 [08-02-02편의 "리소스가 두 개 광고되는 이유"]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-02-02-Neuron-Device-Exposure %}#리소스가-두-개-광고되는-이유)에서 다룬다. 확장 리소스와 device plugin 할당 메커니즘 자체가 낯설다면 [GenAI on K8s 10.1편]({% post_url 2026-06-07-Kubernetes-GenAI-on-K8s-10-01-GPU-Resources-and-K8s-Allocation %})이 배경이 된다.

<details markdown="1">
<summary><b>kubectl describe node 전체 출력</b></summary>

머신 고유 식별자(Machine ID, System UUID, Boot ID) 행은 제거했고, 호스트명·IP·인스턴스 ID·시작 템플릿 ID는 예시 값으로 치환했다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ kubectl describe node
Name:               ip-10-0-5-100.us-west-2.compute.internal
Roles:              <none>
Labels:             alpha.eksctl.io/cluster-name=my-neuron-cluster
                    alpha.eksctl.io/nodegroup-name=neuron-trn1-2x
                    beta.kubernetes.io/arch=amd64
                    beta.kubernetes.io/instance-type=trn1.2xlarge
                    beta.kubernetes.io/os=linux
                    eks.amazonaws.com/capacityType=ON_DEMAND
                    eks.amazonaws.com/nodegroup=neuron-trn1-2x
                    eks.amazonaws.com/nodegroup-image=ami-0e08c07b0376ba3f8
                    eks.amazonaws.com/sourceLaunchTemplateId=lt-0abc1234def567890
                    eks.amazonaws.com/sourceLaunchTemplateVersion=1
                    failure-domain.beta.kubernetes.io/region=us-west-2
                    failure-domain.beta.kubernetes.io/zone=us-west-2b
                    k8s.io/cloud-provider-aws=<hash>
                    kubernetes.io/arch=amd64
                    kubernetes.io/hostname=ip-10-0-5-100.us-west-2.compute.internal
                    kubernetes.io/os=linux
                    node.kubernetes.io/instance-type=trn1.2xlarge
                    topology.k8s.aws/network-node-layer-1=nn-xxxxxxxxxxxxxxxxx
                    topology.k8s.aws/network-node-layer-2=nn-xxxxxxxxxxxxxxxxx
                    topology.k8s.aws/network-node-layer-3=nn-xxxxxxxxxxxxxxxxx
                    topology.k8s.aws/zone-id=usw2-az1
                    topology.kubernetes.io/region=us-west-2
                    topology.kubernetes.io/zone=us-west-2b
Annotations:        alpha.kubernetes.io/provided-node-ip: 10.0.5.100
                    node.alpha.kubernetes.io/ttl: 0
                    volumes.kubernetes.io/controller-managed-attach-detach: true
CreationTimestamp:  Fri, 11 Sep 2026 12:37:57 +0000
Taints:             <none>
Unschedulable:      false
Lease:
  HolderIdentity:  ip-10-0-5-100.us-west-2.compute.internal
  AcquireTime:     <unset>
  RenewTime:       Fri, 11 Sep 2026 12:42:41 +0000
Conditions:
  Type             Status  LastHeartbeatTime                 LastTransitionTime                Reason                       Message
  ----             ------  -----------------                 ------------------                ------                       -------
  MemoryPressure   False   Fri, 11 Sep 2026 12:39:28 +0000   Fri, 11 Sep 2026 12:37:54 +0000   KubeletHasSufficientMemory   kubelet has sufficient memory available
  DiskPressure     False   Fri, 11 Sep 2026 12:39:28 +0000   Fri, 11 Sep 2026 12:37:54 +0000   KubeletHasNoDiskPressure     kubelet has no disk pressure
  PIDPressure      False   Fri, 11 Sep 2026 12:39:28 +0000   Fri, 11 Sep 2026 12:37:54 +0000   KubeletHasSufficientPID      kubelet has sufficient PID available
  Ready            True    Fri, 11 Sep 2026 12:39:28 +0000   Fri, 11 Sep 2026 12:38:06 +0000   KubeletReady                 kubelet is posting ready status
Addresses:
  InternalIP:   10.0.5.100
  ExternalIP:   203.0.113.10
  InternalDNS:  ip-10-0-5-100.us-west-2.compute.internal
  Hostname:     ip-10-0-5-100.us-west-2.compute.internal
  ExternalDNS:  ec2-203-0-113-10.us-west-2.compute.amazonaws.com
Capacity:
  aws.amazon.com/neuron:      1
  aws.amazon.com/neuroncore:  2
  cpu:                        8
  ephemeral-storage:          104779756Ki
  hugepages-1Gi:              0
  hugepages-2Mi:              0
  memory:                     32332248Ki
  pods:                       58
Allocatable:
  aws.amazon.com/neuron:      1
  aws.amazon.com/neuroncore:  2
  cpu:                        7910m
  ephemeral-storage:          95491281146
  hugepages-1Gi:              0
  hugepages-2Mi:              0
  memory:                     31315416Ki
  pods:                       58
System Info:
  Kernel Version:             6.12.103-127.188.amzn2023.x86_64
  OS Image:                   Amazon Linux 2023.12.20260831
  Operating System:           linux
  Architecture:               amd64
  Container Runtime Version:  containerd://2.2.5+unknown
  Kubelet Version:            v1.33.13-eks-cb19647
ProviderID:                   aws:///us-west-2b/i-0abc1234def56789
Non-terminated Pods:          (5 in total)
  Namespace                   Name                          CPU Requests  CPU Limits  Memory Requests  Memory Limits  Age
  ---------                   ----                          ------------  ----------  ---------------  -------------  ---
  kube-system                 aws-node-9nzqc                50m (0%)      0 (0%)      0 (0%)           0 (0%)         4m54s
  kube-system                 coredns-75cb89d95b-6lz4d      100m (1%)     0 (0%)      70Mi (0%)        170Mi (0%)     8h
  kube-system                 coredns-75cb89d95b-k6csj      100m (1%)     0 (0%)      70Mi (0%)        170Mi (0%)     8h
  kube-system                 kube-proxy-fntzm              100m (1%)     0 (0%)      0 (0%)           0 (0%)         4m54s
  kube-system                 neuron-device-plugin-vfwks    0 (0%)        0 (0%)      0 (0%)           0 (0%)         3m39s
Allocated resources:
  (Total limits may be over 100 percent, i.e., overcommitted.)
  Resource                   Requests    Limits
  --------                   --------    ------
  cpu                        350m (4%)   0 (0%)
  memory                     140Mi (0%)  340Mi (1%)
  ephemeral-storage          0 (0%)      0 (0%)
  hugepages-1Gi              0 (0%)      0 (0%)
  hugepages-2Mi              0 (0%)      0 (0%)
  aws.amazon.com/neuron      0           0
  aws.amazon.com/neuroncore  0           0
Events:
  Type     Reason                   Age                    From                   Message
  ----     ------                   ----                   ----                   -------
  Normal   Starting                 4m51s                  kube-proxy
  Normal   Starting                 4m57s                  kubelet                Starting kubelet.
  Warning  InvalidDiskCapacity      4m57s                  kubelet                invalid capacity 0 on image filesystem
  Normal   NodeHasSufficientMemory  4m57s (x3 over 4m57s)  kubelet                Node ip-10-0-5-100.us-west-2.compute.internal status is now: NodeHasSufficientMemory
  Normal   NodeHasNoDiskPressure    4m57s (x3 over 4m57s)  kubelet                Node ip-10-0-5-100.us-west-2.compute.internal status is now: NodeHasNoDiskPressure
  Normal   NodeHasSufficientPID     4m57s (x3 over 4m57s)  kubelet                Node ip-10-0-5-100.us-west-2.compute.internal status is now: NodeHasSufficientPID
  Normal   NodeAllocatableEnforced  4m57s                  kubelet                Updated Node Allocatable limit across pods
  Normal   Synced                   4m54s                  cloud-node-controller  Node synced successfully
  Normal   RegisteredNode           4m53s                  node-controller        Node ip-10-0-5-100.us-west-2.compute.internal event: Registered Node ip-10-0-5-100.us-west-2.compute.internal in Controller
  Normal   NodeReady                4m45s                  kubelet
```

`Non-terminated Pods`에 `neuron-device-plugin-vfwks`가 이미 올라와 있고, `Pending`이던 `coredns` 2개도 이 노드에 배치됐다.

</details>

노드그룹 자체는 콘솔에서도 확인할 수 있다.

![eksctl이 생성한 관리형 노드 그룹]({{site.url}}/assets/images/llmso-aws-workshop-lab1-eks-node-group.png){: .align-center}
<center><sup>직접 캡처. 클러스터명이 들어가는 영역(상단 경로, 시작 템플릿 이름)은 익명화를 위해 블러 처리했다. 노드 그룹 <code>neuron-trn1-2x</code>가 원하는 크기 1, 표시한 AMI 릴리스 버전 <code>ami-0e08c07b0376ba3f8</code>로 활성 상태다</sup></center>

EKS 워커 노드가 등록될 때 노드 쪽에서 어떤 파일과 프로세스가 관여하는지는 [EKS 워커 노드 구성 결과]({% post_url 2026-03-12-Kubernetes-EKS-01-01-05-EKS-Cluster-Worker-Node-Result %})에 정리해 둔 것이 있다.

## kubectl label이 no-op인 이유

워크샵 절차에는 노드에 노드그룹 라벨을 붙이는 단계가 있는데, 실행하면 `not labeled`가 나온다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ NODE_NAME=$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')
ubuntu@ip-10-0-1-100:~/workshop$ kubectl label node $NODE_NAME alpha.eksctl.io/nodegroup-name=neuron-trn1-2x
node/ip-10-0-5-100.us-west-2.compute.internal not labeled
```

`kubectl label`의 응답은 세 가지로 갈린다.

| 출력 | 의미 |
|---|---|
| `node/... labeled` | 라벨이 없었고 새로 붙였다 |
| `node/... not labeled` | 키와 값이 이미 완전히 같다 → 변경 없음 (이번 경우) |
| `error: 'alpha...' already has a value (X), and --overwrite is false` | 같은 키에 다른 값이 있다 → 이때만 실제 문제 |

이미 붙어 있는 이유는 `eksctl`로 만든 관리형 노드그룹이기 때문이다. 노드가 join할 때 `eksctl`이 `alpha.eksctl.io/cluster-name`과 `alpha.eksctl.io/nodegroup-name`을 함께 심는다. 앞의 `describe node` 출력 첫 두 줄이 그 결과다. 워크샵의 `kubectl label` 단계는 `eksctl` 외부에서 만든 노드그룹까지 커버하려는 보험용 명령이고, `eksctl`로 만든 경우에는 항상 no-op이 된다.

## 모델 캐시용 S3 버킷

vLLM이 모델을 Neuron용으로 컴파일한 산출물을 캐시할 버킷을 만든다. 컴파일 결과를 여기에 올려 두고 재사용하는 과정은 [8.3.1편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-03-01-vLLM-Deployment %})에서 다룬다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ echo $BUCKET_NAME
vllm-models-cache-123456789012
ubuntu@ip-10-0-1-100:~/workshop$ aws s3 mb "s3://$BUCKET_NAME" --region "$AWS_REGION"
make_bucket: vllm-models-cache-123456789012
ubuntu@ip-10-0-1-100:~/workshop$ aws s3 ls
2026-09-11 13:18:09 vllm-models-cache-123456789012
```

![생성된 모델 캐시용 S3 버킷]({{site.url}}/assets/images/llmso-aws-workshop-lab1-s3-preparation.png){: .align-center}
<center><sup>직접 캡처. 버킷 이름에 AWS 계정 ID가 포함되어 있어 해당 영역만 블러 처리했다. 리전은 us-west-2다</sup></center>

## S3 CSI 드라이버 설치

버킷을 파드 안에서 파일시스템처럼 쓰기 위해 Mountpoint for Amazon S3 CSI 드라이버를 Helm으로 설치한다.

```shell
# 차트 저장소 등록
ubuntu@ip-10-0-1-100:~/workshop$ helm repo add aws-mountpoint-s3-csi-driver https://awslabs.github.io/mountpoint-s3-csi-driver
"aws-mountpoint-s3-csi-driver" has been added to your repositories
ubuntu@ip-10-0-1-100:~/workshop$ helm repo update
...Successfully got an update from the "aws-mountpoint-s3-csi-driver" chart repository

# kube-system 네임스페이스에 설치
ubuntu@ip-10-0-1-100:~/workshop$ helm upgrade --install aws-mountpoint-s3-csi-driver \
>     --namespace kube-system \
>     aws-mountpoint-s3-csi-driver/aws-mountpoint-s3-csi-driver
Release "aws-mountpoint-s3-csi-driver" does not exist. Installing it now.
NAME: aws-mountpoint-s3-csi-driver
LAST DEPLOYED: Fri Sep 11 13:27:33 2026
NAMESPACE: kube-system
STATUS: deployed
REVISION: 1
TEST SUITE: None
NOTES:
Thank you for using Mountpoint for Amazon S3 CSI Driver v2.8.0.

# 설치 결과 확인: 컨트롤러 1개 + 노드 DaemonSet 1개
ubuntu@ip-10-0-1-100:~/workshop$ kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-mountpoint-s3-csi-driver
NAME                                 READY   STATUS    RESTARTS   AGE
s3-csi-controller-5df587766f-sr6rn   1/1     Running   0          14s
s3-csi-node-th8j4                    3/3     Running   0          14s
```

`s3-csi-node`는 노드마다 뜨는 DaemonSet이라 워커 노드 1개인 이 클러스터에서는 파드도 1개다. 버킷 접근 권한은 앞서 노드그룹 IAM에 붙인 `AmazonS3FullAccess`로 확보되어 있다.

<br>

# 검증: vLLM 배포를 받을 수 있는 상태

질문은 이것이다 — 클러스터가 vLLM 배포를 받을 수 있는 상태인가. 워크샵이 제시하는 최종 확인 절차를 그대로 돌려 본다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ echo "=== Cluster Status ===" && kubectl get nodes
=== Cluster Status ===
NAME                                       STATUS   ROLES    AGE   VERSION
ip-10-0-5-100.us-west-2.compute.internal   Ready    <none>   50m   v1.33.13-eks-cb19647

ubuntu@ip-10-0-1-100:~/workshop$ echo -e "\n=== Neuron Devices ===" && kubectl describe nodes -l alpha.eksctl.io/nodegroup-name=neuron-trn1-2x | grep "aws.amazon.com/neuron"
=== Neuron Devices ===
  aws.amazon.com/neuron:      1          # Capacity
  aws.amazon.com/neuroncore:  2
  aws.amazon.com/neuron:      1          # Allocatable
  aws.amazon.com/neuroncore:  2
  aws.amazon.com/neuron      0           0    # Allocated (요청/제한 합계)
  aws.amazon.com/neuroncore  0           0

ubuntu@ip-10-0-1-100:~/workshop$ echo -e "\n=== Storage Classes ===" && kubectl get storageclass
=== Storage Classes ===
NAME   PROVISIONER             RECLAIMPOLICY   VOLUMEBINDINGMODE      ALLOWVOLUMEEXPANSION   AGE
gp2    kubernetes.io/aws-ebs   Delete          WaitForFirstConsumer   false                  9h

ubuntu@ip-10-0-1-100:~/workshop$ echo -e "\n=== Current Namespace ===" && kubectl config get-contexts
=== Current Namespace ===
CURRENT   NAME                                                       CLUSTER                                                    AUTHINFO
*         arn:aws:eks:us-west-2:123456789012:cluster/my-neuron-cluster   arn:aws:eks:us-west-2:123456789012:cluster/my-neuron-cluster   arn:aws:eks:us-west-2:123456789012:cluster/my-neuron-cluster
```

`grep`이 6줄을 내놓는 것은 `describe node`가 같은 리소스 이름을 `Capacity`·`Allocatable`·`Allocated resources` 세 블록에서 각각 출력하기 때문이다. 마지막 두 줄의 `0 0`은 아직 이 리소스를 요청한 파드가 없다는 뜻이다.

워크샵이 정리한 "지금까지 구성한 것" 네 항목을 위 출력과 맞춰 보면 이렇게 대응된다.

| 워크샵이 말하는 구성 요소 | 대응하는 확인 결과 | 비고 |
|---|---|---|
| Base EKS Cluster (Kubernetes 1.33) | `kubectl get nodes`의 `v1.33.13-eks-cb19647` | VPC CNI는 `aws-node` 파드로, OIDC는 워크샵 CFN이 설정 |
| Neuron 관리형 노드그룹 (`trn1.2xlarge`) | 노드 1개 `Ready`, `instance-type=trn1.2xlarge` | 워크샵 요약문은 스토리지를 500GB라고 적지만, 이 실습의 `ClusterConfig`는 `volumeSize: 100`이다. `ephemeral-storage` 약 100GiB가 그 결과 |
| Neuron device plugin | `aws.amazon.com/neuron`·`neuroncore`가 광고됨 | `eksctl`이 자동 설치한 것. 교체는 [08-02-02편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-02-02-Neuron-Device-Exposure %}) |
| S3 모델 캐시 | `aws s3 ls`의 버킷 + `s3-csi-*` 파드 `Running` | StorageClass는 아직 `gp2`뿐이고, S3 볼륨을 PV·PVC로 붙이는 것은 [8.3.1편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-03-01-vLLM-Deployment %})이다 |

반대 방향의 확인도 해 두면 좋다. device plugin이 죽으면 `allocatable`에서 확장 리소스가 사라지고 파드가 `Pending`에 머무는데, 그 케이스는 [EKS GPU 트러블슈팅 3.1편]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-01-GPU-Pod-Pending %})에 정리해 둔 것이 있다.

<br>

# 막힘 & 해결: 존재하지 않는 AMI

## 증상

노드그룹 생성 첫 시도가 CloudFormation 스택을 만들기도 전에 끊겼다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ eksctl create nodegroup --config-file=eks_nodegroup.yaml
2026-09-11 12:24:37 [!]  no eksctl-managed CloudFormation stacks found for "my-neuron-cluster", will attempt to create nodegroup(s) on non eksctl-managed cluster
2026-09-11 12:24:37 [ℹ]  nodegroup "neuron-trn1-2x" will use "ami-08695d32a8bb6c5a5" [AmazonLinux2023/1.33]
Error: unable to find image "ami-08695d32a8bb6c5a5": operation error EC2: DescribeImages, https response error StatusCode: 400, RequestID: <uuid>, api error InvalidAMIID.NotFound: The image id '[ami-08695d32a8bb6c5a5]' does not exist
```

`eksctl`은 스택을 올리기 전에 `DescribeImages`로 AMI 존재 여부를 확인하고, 여기서 걸리면 바로 중단한다. AWS가 `does not exist`라고 답했으므로 권한 문제가 아니라 조회하는 리전에 그 AMI가 없다는 뜻이다.

## 증거

원인을 좁히는 결정적 증거는 [미리 세팅된 환경변수](#미리-세팅된-환경변수)에 이미 나와 있었다.

| 값 | 출처 |
|---|---|
| `ami-08695d32a8bb6c5a5` | 배스천 셸의 `WORKER_AMI` 환경변수 |
| `ami-0e08c07b0376ba3f8` | 같은 셸, 같은 리전에서 `aws ssm get-parameter`로 조회한 결과 |

같은 셸에서 같은 리전을 보고 있는데 두 값이 다르다. 부팅 시 UserData가 SSM에서 값을 받아 심었다면 두 값은 같아야 한다. **다르다는 사실 자체가 `WORKER_AMI`의 출처가 SSM이 아니라는 증거**다. 즉 어딘가에 하드코딩된 값이다.

## 원인

가능한 설명이 세 가지 있는데, "값이 어디서 왔나"와 "왜 지금 안 되나" 두 축에서 갈린다.

| 가설 | 값의 출처 | 실패 메커니즘 | 판정 |
|---|---|---|---|
| (a) 부팅 후 SSM 값이 교체됨 | SSM (부팅 시 조회) | 실습 중에 새 릴리스가 나와 구 AMI가 deregister | **배제** |
| (b) 리전 불일치 | 템플릿에 박힌 다른 리전(us-east-1) AMI | AMI ID는 리전 스코프라 us-west-2에서 조회하면 존재하지 않음 | 가능하지만 약함 |
| (c) 템플릿 노후화 | 워크샵 CloudFormation·부트스트랩에 하드코딩된 AMI ID | 작성 시점 이후 릴리스가 지나가며 구 AMI가 deregister | **1순위** |

(a)는 위의 증거 하나로 탈락한다. 출처가 SSM이 아니므로 SSM 값이 바뀌었는지 여부는 애초에 관계가 없다. 타이밍으로도 성립하지 않는다 — SSM이 반환한 최신 AMI는 `amazon-eks-node-al2023-x86_64-neuron-1.33-v20260903`, 생성일 2026-09-03으로 실습 8일 전이다. EKS AMI 릴리스는 배스천이 켜져 있던 8시간 사이에 일어나는 일이 아니다.

(b)가 약한 이유는 워크샵 템플릿의 통상적인 작성 방식 때문이다. 여러 리전을 지원하려고 마음먹었다면 보통 CloudFormation Mappings로 리전별 AMI를 매핑하거나 애초에 SSM 파라미터를 참조한다. 한 리전 값만 박아 놓고 다른 리전에서도 쓰게 하는 구성은 상대적으로 드물다.

(c)를 1순위로 보는 근거는 같은 환경에 독립적인 증거가 하나 더 있다는 점이다. 워크샵 환경의 `.env`에 들어 있던 Hugging Face 토큰도 만료되어 있어 새로 발급해야 했다. 토큰과 AMI ID는 서로 아무 관계가 없는 값인데, **환경 구축 시점에 박혀서 그 후로 갱신되지 않았다**는 동일한 실패 양상을 보인다. 리전 불일치 가설로는 토큰 만료를 설명할 수 없지만, 템플릿 노후화 가설은 둘을 한 번에 설명한다.

여기서 "워크샵이 설계된 시점과 지금이 다르다"가 가리키는 것이 분명해진다. 워크샵 환경 템플릿이 만들어진 시점의 AWS 리소스 스냅샷이 그대로 굳어 있는데, 그 뒤 AWS 쪽에서만 시간이 흘렀다는 뜻이다. `/aws/service/eks/optimized-ami/1.33/.../recommended/image_id`가 가리키는 AMI는 새 릴리스마다 바뀌고 구버전은 일정 기간 후 deregister되므로, 굳어 있던 값은 언젠가 반드시 깨진다.

결국 이 사고의 본질은 불일치다. 워크샵 문서 본문은 `aws ssm get-parameter`로 AMI를 조회하라고 지시하는데, 환경 부트스트랩은 그 지시를 따르지 않고 값을 박아 뒀다.

> 정확히 어느 파일에 하드코딩되어 있었는지(CloudFormation UserData인지, `.bashrc`인지, 별도 부트스트랩 스크립트인지)는 확인하지 못했다. 워크샵 환경의 소스를 열어 보지 않았기 때문에, 이 글에서 단정할 수 있는 범위는 "SSM이 아닌 어딘가에 하드코딩되어 있었다"까지다.

## 해결

SSM에서 다시 받아 환경변수를 덮어쓰고, 그 AMI가 실제로 존재하는지 먼저 검증한 뒤 YAML을 재생성했다.

```shell
# 1. SSM에서 최신 AMI를 다시 받아 환경변수를 덮어쓴다
ubuntu@ip-10-0-1-100:~/workshop$ export AWS_REGION=us-west-2
ubuntu@ip-10-0-1-100:~/workshop$ export WORKER_AMI=$(aws ssm get-parameter \
>     --name /aws/service/eks/optimized-ami/1.33/amazon-linux-2023/x86_64/neuron/recommended/image_id \
>     --region $AWS_REGION \
>     --query "Parameter.Value" \
>     --output text)
ubuntu@ip-10-0-1-100:~/workshop$ echo $WORKER_AMI
ami-0e08c07b0376ba3f8

# 2. 실제로 존재하는지 확인한다. eksctl이 내부적으로 하는 것과 같은 호출이라,
#    여기서 통과하면 eksctl도 통과한다
ubuntu@ip-10-0-1-100:~/workshop$ aws ec2 describe-images --image-ids $WORKER_AMI --region $AWS_REGION \
>   --query 'Images[0].[ImageId,Name,CreationDate]' --output text
ami-0e08c07b0376ba3f8   amazon-eks-node-al2023-x86_64-neuron-1.33-v20260903     2026-09-03T22:42:42.000Z
```

환경변수만 고쳐서는 부족하다. `eks_nodegroup.yaml`은 heredoc으로 만들 때 이미 낡은 값이 구워진 파일이라, 같은 heredoc을 다시 실행해 파일을 재생성해야 한다. 재생성 결과는 `ami:` 한 줄만 달라진다.

```diff
 managedNodeGroups:
 - name: neuron-trn1-2x
-  ami: ami-08695d32a8bb6c5a5
+  ami: ami-0e08c07b0376ba3f8
   amiFamily: AmazonLinux2023
```

이 상태로 `eksctl create nodegroup`을 다시 실행한 결과가 [노드그룹 배포](#노드그룹-배포)의 출력이다.

재실행 전에 한 가지 더 확인해 둘 것이 있다. YAML에 `ssh.publicKeyPath: ~/.ssh/id_rsa.pub`가 들어 있어, 그 파일이 없으면 여기서도 막힌다. 노드 접속을 Session Manager로 할 생각이면 `ssh:` 블록을 아예 지우는 편이 간단하고, 남겨 둘 거면 `ssh-keygen`으로 키를 만들어 두면 된다.

교훈은 두 줄이다.

- AMI ID는 하드코딩하거나 셸 히스토리의 값을 재사용하지 말고, 매번 SSM 파라미터에서 조회한다
- 워크샵 환경에 미리 세팅된 값은 그대로 믿지 말고 실제 값과 대조하고 쓴다. 이번 실습에서는 AMI ID와 Hugging Face 토큰이 둘 다 여기에 걸렸다

<br>

# 정리

| 단계 | 한 일 | 확인 지점 |
|---|---|---|
| 실습 환경 | 배스천에 AWS CLI·Helm·jq 설치, kubeconfig 갱신 | `coredns` 2개가 `Pending` = 노드 없음 |
| 네트워킹 | VPC → 인스턴스 타입 제공 AZ → 퍼블릭 서브넷 순으로 값 확보 | 서로 다른 AZ의 퍼블릭 서브넷 2개 |
| 노드그룹 | `eksctl create nodegroup`으로 `trn1.2xlarge` 1대 | 노드 `Ready`, `ExternalIP` 부여됨 |
| 스토리지 | 모델 캐시 버킷 + Mountpoint S3 CSI 드라이버 | `s3-csi-controller`·`s3-csi-node` `Running` |
| 막힘 | 미리 박힌 `WORKER_AMI`가 deregister된 AMI | SSM 조회값과 환경변수값의 불일치 |

이 편에서 확보한 것은 vLLM 배포를 받을 수 있는 클러스터 상태다. 노드가 `Ready`이고, Neuron 확장 리소스가 광고되고, 모델 캐시용 스토리지가 붙어 있다.

남은 질문은 광고된 리소스 쪽에 있다. 칩 하나짜리 노드인데 `aws.amazon.com/neuron: 1`과 `aws.amazon.com/neuroncore: 2`가 함께 나온다. 이 둘이 같은 하드웨어를 두 가지 단위로 센 것이라면, 스케줄러는 그 사실을 어떻게 아는가. [08-02-02편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-02-02-Neuron-Device-Exposure %})에서 노드 안으로 들어가 커널 디바이스 노드와 device plugin 소켓까지 확인한다.

<br>

# 참고 링크

- [Amazon EKS 최적화 AMI ID 조회 (AWS 문서)](https://docs.aws.amazon.com/eks/latest/userguide/retrieve-ami-id.html)
- [Amazon EKS VPC 및 서브넷 요구 사항 (AWS 문서)](https://docs.aws.amazon.com/eks/latest/userguide/network-reqs.html)
- [eksctl: Managed Nodegroups](https://eksctl.io/usage/eks-managed-nodes/)
- [awslabs/mountpoint-s3-csi-driver](https://github.com/awslabs/mountpoint-s3-csi-driver)
- [AWS Neuron Documentation](https://awsdocs-neuron.readthedocs-hosted.com/)
- [Kubernetes: Device Plugins](https://kubernetes.io/docs/concepts/extend-kubernetes/compute-storage-net/device-plugins/)
- [08-00편: vLLM on Trainium 워크샵 개요]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-00-EKS-Workshop-Overview %})
- [08-01편: AWS 가속기 - Inferentia, Trainium, NeuronCore]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-01-AWS-Accelerators %})
- [08-02-02편: Trainium 디바이스가 쿠버네티스에 노출되는 경로]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-02-02-Neuron-Device-Exposure %})
- [GenAI on K8s 10.1편: GPU 자원 개요와 K8s 할당 메커니즘]({% post_url 2026-06-07-Kubernetes-GenAI-on-K8s-10-01-GPU-Resources-and-K8s-Allocation %})
- [EKS 클러스터 워커 노드 구성 결과]({% post_url 2026-03-12-Kubernetes-EKS-01-01-05-EKS-Cluster-Worker-Node-Result %})
- [EKS GPU 트러블슈팅 3.1편: Device Plugin 비활성화 시 파드 Pending]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-01-GPU-Pod-Pending %})

<br>
