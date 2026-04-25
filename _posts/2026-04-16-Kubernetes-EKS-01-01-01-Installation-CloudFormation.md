---
title: "[EKS] GitOps 기반 SaaS: 실습 환경 구성 - 1. CloudFormation 코드 분석"
excerpt: "EKS SaaS GitOps 워크숍의 1단계 부트스트랩 코드(vs-code-ec2.yaml)를 분석해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - CloudFormation
  - SSM
  - EC2
  - IaC
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-6
---

*[최영락](https://www.linkedin.com/in/ianychoi/)님의 AWS EKS Workshop Study(AEWS) 6주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- CFN은 Terraform과 목적은 같지만 문법과 실행 방식이 다른 **AWS 자체 IaC(Infrastructure as Code) 도구**다
- 템플릿 구조: **Parameters → Resources → Outputs** 
- 핵심: SSMDocument의 `runCommand`가 EC2 부팅 후 code-server 설치, CLI 도구 설치, `install.sh` 실행까지 모두 순차 처리
- 제공된 템플릿은 `WaitCondition`으로 내부 Terraform 완료까지 스택 완료를 보류하는 구조다

<br>

# CloudFormation vs Terraform

[이전 1주차 배포 개요 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-00-Installation-Overview %})에서 eksctl이 내부적으로 CloudFormation을 사용한다는 점을 다뤘다. 이번 워크숍의 부트스트랩도 바로 그 CloudFormation을 사용한다.

CloudFormation과 Terraform은 둘 다 "AWS 리소스를 코드로 만든다"는 목적은 같지만, 문법과 실행 방식이 완전히 다르다. 서로 호환되지 않는다.

| 항목 | CloudFormation | Terraform |
|---|---|---|
| 제공처 | AWS 자체 | HashiCorp (3rd-party) |
| 파일 형식 | YAML/JSON | HCL |
| 실행 위치 | AWS 클라우드 (CFN 서비스가 직접 실행) | 로컬/CI에서 `terraform apply` |
| 상태 저장 | AWS가 알아서 관리 (스택) | `tfstate` 파일을 직접 관리 |
| 멀티 클라우드 | AWS 전용 | AWS/GCP/Azure 등 |

<br>

# CloudFormation 핵심 문법

CFN 템플릿에서 자주 등장하는 문법을 Terraform과 비교하면 다음과 같다.

| 문법 | 의미 | Terraform 등가물 |
|---|---|---|
| `!Ref ResourceName` | 다른 리소스의 ID/이름 참조 | `aws_vpc.this.id` |
| `!Sub "${EnvironmentName}-foo"` | 문자열 보간(interpolation) | `"${var.env}-foo"` |
| `!GetAZs ""` | 현재 리전의 AZ 목록 가져오기 | `data "aws_availability_zones"` |
| `!Select [0, list]` | 리스트에서 N번째 선택 | `element(list, 0)` |
| `Type: AWS::EC2::VPC` | 리소스 타입 선언 | `resource "aws_vpc"` |
| `DeletionPolicy: Retain` | 스택 삭제 시 리소스 보존 | `lifecycle { prevent_destroy }` |
| `DependsOn: Foo` | 명시적 의존성 | `depends_on = [aws_x.foo]` |

실제 코드에서 어떻게 쓰이는지 예시를 보자. CFN의 `PublicSubnet` 정의이다.

```yaml
PublicSubnet:
  Properties:
    VpcId: !Ref VPC                          # VPC 리소스의 ID
    AvailabilityZone: !Select [0, !GetAZs ""]  # 첫 번째 AZ
    Tags:
      - Key: Name
        Value: !Sub ${EnvironmentName}-vscode-subnet  # 변수 보간
```

같은 구성을 Terraform으로 나타내 보자.

```hcl
data "aws_availability_zones" "available" {}

resource "aws_subnet" "public" {
  vpc_id            = aws_vpc.this.id
  availability_zone = data.aws_availability_zones.available.names[0]
  tags = {
    Name = "${var.environment_name}-vscode-subnet"
  }
}
```

같은 리소스를 만들지만 문법이 전혀 다르다는 것을 알 수 있다. 이 차이를 머릿속에 넣어 두고, 아래 템플릿 코드를 읽어 보자.

<br>

# 코드 구조 한눈에 보기

CFN 템플릿은 항상 **Parameters → Resources → Outputs** 3단 구조다.

```
AWSTemplateFormatVersion: 2010-09-09      ← 스펙 버전 (고정값)
Description: ...                          ← 설명

Parameters: { ... }   ← 사용자 입력값 (콘솔 폼으로 보임)
Resources:  { ... }   ← 실제로 만들 AWS 리소스들
Outputs:    { ... }   ← 만든 후 보여줄 값 (URL, 비밀번호 위치 등)
```

전체 코드는 아래 접은 글에서 확인할 수 있다.

<details markdown="1">
<summary><b>vs-code-ec2.yaml 전체 코드</b></summary>

```yaml
AWSTemplateFormatVersion: 2010-09-09

Description: This stack creates an EC2 instance with VS Code server environment for the Solution Guidance on Building SaaS applications on Amazon EKS using GitOps

Parameters:
  EnvironmentName:
    Description: An environment name that is prefixed to resource names
    Type: String
    Default: "eks-saas-gitops"
  InstanceType:
    Description: EC2 instance type
    Type: String
    Default: t3.large
    AllowedValues:
      - t3.medium
      - t3.large
      - t3.xlarge
    ConstraintDescription: Must be a valid EC2 instance type
  AllowedIP:
    Description: Allowed IP address for connecting to the VSCode server and Gitea (CIDR)
    AllowedPattern: ^([0-9]{1,3}\.){3}[0-9]{1,3}/([0-9]|[1-2][0-9]|3[0-2])$
    ConstraintDescription: Must be a valid IP CIDR range of the form x.x.x.x/x
    Type: String
    Default: 0.0.0.0/0
  LatestAmiId:
    Type: "AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>"
    Default: "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"

Resources:
  ################## PERMISSIONS AND ROLES #################
  EC2Role:
    Type: AWS::IAM::Role
    Properties:
      RoleName: eks-saas-gitops-admin
      Tags:
        - Key: Environment
          Value: !Sub ${EnvironmentName}
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal:
              Service:
                - ec2.amazonaws.com
                - ssm.amazonaws.com
                - eks.amazonaws.com
                - codebuild.amazonaws.com
            Action:
              - sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/AdministratorAccess
      Path: "/"

  ################## ARTIFACTS BUCKET ###############
  OutputBucket:
    Type: AWS::S3::Bucket
    DeletionPolicy: Retain
    Properties:
      VersioningConfiguration:
        Status: Enabled
      AccessControl: Private
      BucketEncryption:
        ServerSideEncryptionConfiguration:
          - ServerSideEncryptionByDefault:
              SSEAlgorithm: AES256
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true

  ################## VPC etc ######################
  VPC:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: "10.0.0.0/16"
      EnableDnsHostnames: true
      EnableDnsSupport: true
      Tags:
        - Key: Name
          Value: eks-saas-gitops-vscode-vpc
        - Key: Environment
          Value: !Sub ${EnvironmentName}

  PublicSubnet:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref VPC
      CidrBlock: "10.0.1.0/24"
      AvailabilityZone: !Select [0, !GetAZs ""]
      MapPublicIpOnLaunch: true
      Tags:
        - Key: Name
          Value: !Sub ${EnvironmentName}-vscode-subnet
        - Key: Environment
          Value: !Sub ${EnvironmentName}

  InternetGateway:
    Type: AWS::EC2::InternetGateway
    Properties:
      Tags:
        - Key: Name
          Value: !Sub ${EnvironmentName}-vscode-igw

  AttachGateway:
    Type: AWS::EC2::VPCGatewayAttachment
    Properties:
      VpcId: !Ref VPC
      InternetGatewayId: !Ref InternetGateway

  PublicRouteTable:
    Type: AWS::EC2::RouteTable
    Properties:
      VpcId: !Ref VPC
      Tags:
        - Key: Name
          Value: !Sub ${EnvironmentName}-vscode-rt

  PublicRoute:
    Type: AWS::EC2::Route
    DependsOn: AttachGateway
    Properties:
      RouteTableId: !Ref PublicRouteTable
      DestinationCidrBlock: 0.0.0.0/0
      GatewayId: !Ref InternetGateway

  PublicSubnetRouteTableAssociation:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Properties:
      SubnetId: !Ref PublicSubnet
      RouteTableId: !Ref PublicRouteTable

  ################## SSM Bootstrap for VS Code ##################
  SSMDocument:
    Type: AWS::SSM::Document
    Properties:
      Tags:
        - Key: Environment
          Value: !Sub ${EnvironmentName}
      DocumentType: Command
      Content:
        schemaVersion: "2.2"
        description: Bootstrap VS Code Instance
        parameters:
          allowedIp:
            type: String
            description: Allowed IP address
            default: ""
        mainSteps:
          - action: aws:runShellScript
            name: VSCodebootstrap
            inputs:
              runCommand:
                - "#!/bin/bash"
                - "mkdir -p /home/ec2-user/environment"
                - "chown -R ec2-user:ec2-user /home/ec2-user/environment"
                - "curl -fsSL https://code-server.dev/install.sh | sudo -u ec2-user sh"
                - "export CODER_PASSWORD=$(openssl rand -base64 12)"
                - "mkdir -p /home/ec2-user/.config/code-server/"
                - "echo 'bind-addr: 0.0.0.0:8080' > /home/ec2-user/.config/code-server/config.yaml"
                - "echo 'auth: password' >> /home/ec2-user/.config/code-server/config.yaml"
                - "echo password: $CODER_PASSWORD >> /home/ec2-user/.config/code-server/config.yaml"
                - "chown -R ec2-user:ec2-user /home/ec2-user/.config/"
                - 'aws ssm put-parameter --name ''coder-password'' --type ''String'' --value "$CODER_PASSWORD" --overwrite'
                - "yum update -y"
                - "yum install -y docker && systemctl start docker && systemctl enable docker"
                - "yum install -y vim git jq bash-completion moreutils gettext yum-utils perl-Digest-SHA"
                - "yum install -y git-lfs"
                - "yum install -y tree"
                - curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
                - "chmod +x kubectl && mv kubectl /usr/local/bin/"
                - "/usr/local/bin/kubectl completion bash > /etc/bash_completion.d/kubectl"
                - "curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash"
                - "/usr/local/bin/helm completion bash > /etc/bash_completion.d/helm"
                - curl --silent --location "https://github.com/fluxcd/flux2/releases/download/v2.7.5/flux_2.7.5_$(uname -s)_amd64.tar.gz" | tar xz -C /tmp
                - "mv /tmp/flux /usr/local/bin"
                - "/usr/local/bin/flux completion bash > /etc/bash_completion.d/flux"
                - "wget https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O /usr/bin/yq && sudo chmod +x /usr/bin/yq"
                - "yum-config-manager --add-repo https://rpm.releases.hashicorp.com/AmazonLinux/hashicorp.repo"
                - "yum -y install terraform"
                - export TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds:60")
                - export AWS_REGION=$(curl -H "X-aws-ec2-metadata-token:${TOKEN}" -s http://169.254.169.254/latest/meta-data/placement/availability-zone | sed 's/\(.*\)[a-z]/\1/')  && echo "export AWS_REGION=${AWS_REGION}" >> /home/ec2-user/.bashrc
                - export ALLOWED_IP="{{allowedIp}}"
                - "git clone https://github.com/aws-samples/eks-saas-gitops.git /home/ec2-user/environment/eks-saas-gitops; echo 'solution=true' > /home/ec2-user/environment/eks-saas-gitops/terraform/workshop/terraform.tfvars"
                - "chown -R ec2-user:ec2-user /home/ec2-user/environment"
                - "sudo -u ec2-user nohup /usr/bin/code-server --port 8080 --host 0.0.0.0 > /dev/null 2>&1 &"
                - "export WAIT_HANDLE_URL=$(aws ssm get-parameter --name '/eks-saas-gitops/waitcondition-url' --query 'Parameter.Value' --output text --region $AWS_REGION)"
                - "cd /home/ec2-user/environment/eks-saas-gitops/terraform"
                - "chmod +x install.sh"
                - 'sudo -u ec2-user ./install.sh ${AWS_REGION} "{{allowedIp}}" > /home/ec2-user/environment/terraform-install.log 2>&1'
                - 'if [ $? -eq 0 ]; then'
                - '  curl -X PUT -H ''Content-Type: application/json'' --data-binary ''{"Status" : "SUCCESS", "Reason" : "Environment Completed", "UniqueId" : "123456", "Data" : "Complete"}'' "$WAIT_HANDLE_URL"'
                - 'else'
                - '  curl -X PUT -H ''Content-Type: application/json'' --data-binary ''{"Status" : "FAILURE", "Reason" : "Terraform installation failed", "UniqueId" : "123456", "Data" : "Failed"}'' "$WAIT_HANDLE_URL"'
                - 'fi'

  SSMBootstrapAssociation:
    Type: AWS::SSM::Association
    Properties:
      Name: !Ref SSMDocument
      Parameters:
        allowedIp: [!Ref AllowedIP]
      OutputLocation:
        S3Location:
          OutputS3BucketName: !Ref OutputBucket
          OutputS3KeyPrefix: bootstrapoutput
      Targets:
        - Key: tag:SSMBootstrapSaaSGitOps
          Values:
            - Active

  ################## WAIT CONDITION ##################
  WaitHandle:
    Type: AWS::CloudFormation::WaitConditionHandle

  WaitCondition:
    Type: AWS::CloudFormation::WaitCondition
    DependsOn: SSMBootstrapAssociation
    Properties:
      Handle: !Ref WaitHandle
      Timeout: "2000"

  WaitConditionUrlParameter:
    Type: "AWS::SSM::Parameter"
    Properties:
      Name: !Sub /${EnvironmentName}/waitcondition-url
      Type: "String"
      Value: !Ref WaitHandle

  ################## Instance Profile ##################
  EC2InstanceProfile:
    Type: AWS::IAM::InstanceProfile
    Properties:
      Path: "/"
      Roles:
        - Ref: EC2Role

  EC2Instance:
    Type: AWS::EC2::Instance
    Properties:
      ImageId: !Ref LatestAmiId
      InstanceType: !Ref InstanceType
      SubnetId: !Ref PublicSubnet
      IamInstanceProfile: !Ref EC2InstanceProfile
      SecurityGroupIds:
        - !Ref EC2SecurityGroup
      Tags:
        - Key: Name
          Value: !Sub ${EnvironmentName}-Instance
        - Key: SSMBootstrapSaaSGitOps
          Value: Active
        - Key: Environment
          Value: !Sub ${EnvironmentName}

  EC2SecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      VpcId: !Ref VPC
      GroupName: EC2SecurityGroup
      GroupDescription: Allow SSH and Code-Server access
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 8080
          ToPort: 8080
          CidrIp: !Ref AllowedIP
          Description: Allow HTTP traffic from provided prefix
      SecurityGroupEgress:
        - IpProtocol: "-1"
          CidrIp: 0.0.0.0/0
      Tags:
        - Key: Name
          Value: eks-saas-gitops-vscode-sg
        - Key: Environment
          Value: !Sub ${EnvironmentName}

Outputs:
  VsCodeIdeUrl:
    Description: The URL to access VS Code IDE
    Value: !Sub "http://${EC2Instance.PublicDnsName}:8080/?folder=/home/ec2-user/environment"
  VsCodePassword:
    Description: The VS Code IDE password
    Value: !Sub "https://${AWS::Region}.console.aws.amazon.com/systems-manager/parameters/coder-password"
```

</details>

<br>

# Parameters

사용자가 CFN 콘솔에서 채우는 입력값 4개가 정의되어 있다.

```yaml
Parameters:
  EnvironmentName:
    Type: String
    Default: "eks-saas-gitops"       # 리소스 이름 접두사
  InstanceType:
    Type: String
    Default: t3.large                # EC2 사양
  AllowedIP:
    Type: String
    Default: 0.0.0.0/0               # 8080 포트 허용 CIDR
  LatestAmiId:
    Type: "AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>"
    Default: "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
```

`LatestAmiId`는 다른 파라미터와 성격이 다르다. **AMI ID를 하드코딩하지 않고 SSM Parameter Store에서 자동 조회**한다. `AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>` 타입으로 선언하면, CFN이 스택 생성 시점에 해당 SSM 파라미터 경로에서 최신 Amazon Linux 2023 AMI ID를 가져온다. Terraform에서 `data "aws_ami"` 블록으로 최신 AMI를 조회하는 것과 동일한 역할이다.

<br>

# Resources

Resources 섹션에서 생성되는 리소스를 그룹별로 정리하면 다음과 같다.

| 그룹 | 리소스 | 역할 |
|---|---|---|
| **IAM** | `EC2Role` | `AdministratorAccess` 정책이 붙은 IAM Role |
| | `EC2InstanceProfile` | EC2가 Role을 사용할 수 있도록 묶음 |
| **Storage** | `OutputBucket` | SSM 부트스트랩 로그 저장용 S3 |
| **Network** | `VPC` (10.0.0.0/16) | VS Code EC2가 위치할 VPC |
| | `PublicSubnet` (10.0.1.0/24) | 퍼블릭 서브넷 |
| | `InternetGateway` + `AttachGateway` | 인터넷 게이트웨이 연결 |
| | `PublicRouteTable` + `PublicRoute` | 퍼블릭 라우팅 |
| | `EC2SecurityGroup` | 8080 포트만 AllowedIP에서 허용 |
| **Compute** | `EC2Instance` | Amazon Linux 2023, `SSMBootstrapSaaSGitOps=Active` 태그로 SSM 트리거 |
| **Bootstrap** | `SSMDocument` | 부팅 후 실행할 셸 스크립트 |
| | `SSMBootstrapAssociation` | 위 태그를 가진 EC2에 SSMDocument 적용 |
| | `WaitHandle` / `WaitCondition` | 부트스트랩 완료까지 스택 생성 대기 |
| | `WaitConditionUrlParameter` | 완료 신호 전송용 URL을 SSM에 저장 |

각 그룹을 하나씩 살펴보자.

## IAM

`EC2Role`은 `AdministratorAccess` 정책이 붙은 IAM Role이다. `AssumeRolePolicyDocument`에서 **ec2, ssm, eks, codebuild** 4개 서비스가 이 Role을 assume할 수 있도록 허용한다. `EC2InstanceProfile`은 EC2 인스턴스가 이 Role을 사용할 수 있도록 묶어주는 리소스다.


```yaml
EC2Role:
  Type: AWS::IAM::Role
  Properties:
    RoleName: eks-saas-gitops-admin
    AssumeRolePolicyDocument:
      Statement:
        - Effect: Allow
          Principal:
            Service:              # 이 4개 서비스가 Role을 assume 가능
              - ec2.amazonaws.com
              - ssm.amazonaws.com
              - eks.amazonaws.com
              - codebuild.amazonaws.com
          Action:
            - sts:AssumeRole
    ManagedPolicyArns:
      - arn:aws:iam::aws:policy/AdministratorAccess  # AWS 전체 권한

EC2InstanceProfile:
  Type: AWS::IAM::InstanceProfile  # EC2가 위 Role을 사용하려면 반드시 필요
  Properties:
    Roles:
      - Ref: EC2Role               # EC2Role과 연결
```

## Storage

SSM 부트스트랩 로그를 저장하는 S3 버킷이다. `DeletionPolicy: Retain`으로 스택을 삭제해도 버킷이 남도록 설정하고, 서버 측 AES-256 암호화와 Public Access 차단을 걸어 두었다.


```yaml
OutputBucket:
  Type: AWS::S3::Bucket
  DeletionPolicy: Retain            # 스택 삭제해도 버킷은 보존
  Properties:
    VersioningConfiguration:
      Status: Enabled                # 오브젝트 버전 관리 활성화
    BucketEncryption:
      ServerSideEncryptionConfiguration:
        - ServerSideEncryptionByDefault:
            SSEAlgorithm: AES256     # 서버 측 AES-256 암호화
    PublicAccessBlockConfiguration:  # Public Access 전면 차단
      BlockPublicAcls: true
      BlockPublicPolicy: true
      IgnorePublicAcls: true
      RestrictPublicBuckets: true
```


## Network


VPC(`10.0.0.0/16`)와 PublicSubnet(`10.0.1.0/24`)을 만들고, InternetGateway + PublicRouteTable로 인터넷 라우팅을 구성한다. SecurityGroup은 `AllowedIP`에서 **8080 포트만 인바운드 허용**, 아웃바운드는 전체 오픈이다.


```yaml
VPC:
  Type: AWS::EC2::VPC
  Properties:
    CidrBlock: "10.0.0.0/16"
    Tags:
      - Key: Name
        Value: eks-saas-gitops-vscode-vpc  # 2단계 Terraform이 이 태그로 VPC를 찾음

PublicSubnet:
  Type: AWS::EC2::Subnet
  Properties:
    VpcId: !Ref VPC
    CidrBlock: "10.0.1.0/24"
    MapPublicIpOnLaunch: true

EC2SecurityGroup:
  Type: AWS::EC2::SecurityGroup
  Properties:
    SecurityGroupIngress:
      - IpProtocol: tcp
        FromPort: 8080
        ToPort: 8080
        CidrIp: !Ref AllowedIP       # code-server 접속 포트
    SecurityGroupEgress:
      - IpProtocol: "-1"
        CidrIp: 0.0.0.0/0            # Egress 전체 오픈
```

여기서 **VPC 태그 `eks-saas-gitops-vscode-vpc`가 중요**하다. 2단계에서 실행되는 Terraform이 이 태그를 기준으로 CFN VPC를 찾아 VPC peering을 설정하기 때문이다.

## Compute


Amazon Linux 2023 기반 EC2 인스턴스다. 핵심은 `SSMBootstrapSaaSGitOps=Active` 태그인데, 이 태그가 SSMBootstrapAssociation의 트리거 조건과 매칭되어 SSMDocument가 자동 실행된다.


```yaml
EC2Instance:
  Type: AWS::EC2::Instance
  Properties:
    ImageId: !Ref LatestAmiId          # SSM에서 조회한 최신 AL2023 AMI
    InstanceType: !Ref InstanceType    # 기본값 t3.large
    SubnetId: !Ref PublicSubnet        # 위에서 만든 퍼블릭 서브넷에 배치
    IamInstanceProfile: !Ref EC2InstanceProfile  # AdministratorAccess Role 연결
    SecurityGroupIds:
      - !Ref EC2SecurityGroup          # 8080 포트만 열린 SG
    Tags:
      - Key: SSMBootstrapSaaSGitOps
        Value: Active                  # ★ 이 태그가 SSM Association 트리거
```

## Bootstrap

가장 중요한 부분이다. SSM(AWS Systems Manager)의 **SSMDocument**(실행할 셸 스크립트), **SSMBootstrapAssociation**(Document를 EC2에 적용하는 트리거), **WaitCondition**(부트스트랩 완료까지 스택 대기) 3종 세트가 EC2 부팅 후 자동 프로비저닝을 담당한다.

먼저 `SSMDocument`다. 외부 파일이 아니라 **이 CFN 템플릿 안에 인라인으로 정의**된 리소스다. 셸 스크립트 전체가 `runCommand` 배열 안에 들어 있다.

```yaml
SSMDocument:
  Type: AWS::SSM::Document            # SSM Document를 CFN 리소스로 직접 정의
  Properties:
    DocumentType: Command              # "원격 명령 실행" 타입
    Content:
      schemaVersion: "2.2"
      mainSteps:
        - action: aws:runShellScript   # 셸 스크립트 실행 액션
          name: VSCodebootstrap
          inputs:
            runCommand:                # ★ 여기에 셸 명령이 순서대로 나열됨
              - "#!/bin/bash"
              - "mkdir -p /home/ec2-user/environment"
              - ...                    # (14단계 — 다음 섹션에서 상세 분석)
```

그 다음 `SSMBootstrapAssociation`이 이 Document를 **어떤 EC2에 적용할지** 연결한다.

```yaml
SSMBootstrapAssociation:
  Type: AWS::SSM::Association          # Document와 대상 EC2를 연결
  Properties:
    Name: !Ref SSMDocument             # 위에서 정의한 SSMDocument를 참조
    Parameters:
      allowedIp: [!Ref AllowedIP]      # CFN 파라미터를 Document에 전달
    Targets:
      - Key: tag:SSMBootstrapSaaSGitOps
        Values:
          - Active                     # ★ 이 태그를 가진 EC2에 자동 적용
```

즉, EC2 인스턴스에 `SSMBootstrapSaaSGitOps=Active` 태그가 붙는 순간 → Association이 매칭 → SSMDocument의 `runCommand`가 자동 실행되는 구조다. `runCommand` 안에 담긴 셸 스크립트의 내용이 다음 섹션의 분석 대상이다.

<br>

# SSMDocument runCommand 분석

SSMDocument의 `runCommand`에 담긴 셸 명령이 EC2 부팅 후 순차 실행되며, 이 안에서 최종적으로 Terraform까지 호출된다. 주요 명령을 발췌하면 다음과 같다.

```bash
#!/bin/bash

# --- 1) 작업 디렉터리 생성 ---
mkdir -p /home/ec2-user/environment

# --- 2) code-server 설치 + 비밀번호 랜덤 생성 ---
curl -fsSL https://code-server.dev/install.sh | sudo -u ec2-user sh
export CODER_PASSWORD=$(openssl rand -base64 12)

# --- 3) code-server 설정 파일 작성 ---
echo 'bind-addr: 0.0.0.0:8080' > /home/ec2-user/.config/code-server/config.yaml
echo 'auth: password' >> /home/ec2-user/.config/code-server/config.yaml
echo "password: $CODER_PASSWORD" >> /home/ec2-user/.config/code-server/config.yaml

# --- 4) 비밀번호를 SSM Parameter Store에 저장 ---
aws ssm put-parameter --name 'coder-password' --type 'String' --value "$CODER_PASSWORD" --overwrite

# --- 5) yum update + 기본 패키지 설치 ---
yum update -y
yum install -y docker vim git jq bash-completion ...

# --- 6) CLI 바이너리 설치 ---
curl -LO ".../kubectl" && chmod +x kubectl && mv kubectl /usr/local/bin/
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
curl --silent --location ".../flux_2.7.5_..." | tar xz -C /tmp && mv /tmp/flux /usr/local/bin
yum -y install terraform

# --- 7) EC2 메타데이터에서 AWS_REGION 추출 (IMDSv2) ---
export TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds:60")
export AWS_REGION=$(curl -H "X-aws-ec2-metadata-token:${TOKEN}" \
  -s .../placement/availability-zone | sed 's/\(.*\)[a-z]/\1/')

# --- 8) ALLOWED_IP 환경변수 세팅 ---
export ALLOWED_IP="{{allowedIp}}"

# --- 9) 워크숍 저장소 클론 ---
git clone https://github.com/aws-samples/eks-saas-gitops.git \
  /home/ec2-user/environment/eks-saas-gitops

# --- 10) ★ code-server 백그라운드 실행 (이 시점부터 브라우저 접속 가능) ---
sudo -u ec2-user nohup /usr/bin/code-server --port 8080 --host 0.0.0.0 > /dev/null 2>&1 &

# --- 11) WaitHandle URL을 SSM에서 조회 ---
export WAIT_HANDLE_URL=$(aws ssm get-parameter \
  --name '/eks-saas-gitops/waitcondition-url' --query 'Parameter.Value' --output text)

# --- 12) Terraform 디렉터리 이동 + 실행 권한 부여 ---
cd /home/ec2-user/environment/eks-saas-gitops/terraform
chmod +x install.sh

# --- 13) ★ install.sh 실행 (여기서 Terraform이 전체 인프라 배포) ---
sudo -u ec2-user ./install.sh ${AWS_REGION} "{{allowedIp}}" \
  > /home/ec2-user/environment/terraform-install.log 2>&1

# --- 14) 종료 코드에 따라 WaitHandle에 SUCCESS/FAILURE 신호 전송 ---
if [ $? -eq 0 ]; then
  curl -X PUT -H 'Content-Type: application/json' \
    --data-binary '{"Status":"SUCCESS","Reason":"Environment Completed",...}' "$WAIT_HANDLE_URL"
else
  curl -X PUT -H 'Content-Type: application/json' \
    --data-binary '{"Status":"FAILURE","Reason":"Terraform installation failed",...}' "$WAIT_HANDLE_URL"
fi
```

실행 순서를 표로 요약하면 다음과 같다.

| 순서 | 명령 요약 |
|---|---|
| 1 | 작업 디렉터리 생성 |
| 2 | code-server 설치 + 비밀번호 랜덤 생성 |
| 3 | code-server 설정 파일 작성 |
| 4 | 비밀번호를 SSM Parameter Store에 저장 |
| 5 | yum update + 기본 패키지 설치 (Docker, vim, git, jq 등) |
| 6 | CLI 바이너리 설치 (kubectl, helm, flux, yq, terraform) |
| 7 | EC2 메타데이터에서 AWS_REGION 추출 (IMDSv2) |
| 8 | ALLOWED_IP 환경변수 세팅 |
| 9 | 워크숍 저장소 클론 |
| **10** | **code-server 백그라운드 실행** |
| 11 | WAIT_HANDLE_URL을 SSM에서 조회 |
| 12 | Terraform 디렉터리 이동 + 실행 권한 부여 |
| **13** | **install.sh 실행** |
| 14 | 종료 코드에 따라 WaitHandle에 SUCCESS/FAILURE 신호 전송 |

핵심 포인트가 있다. 10번 시점에 code-server는 이미 떠 있어서 브라우저로 접속할 수 있지만, **13번 `install.sh`가 끝나기 전까지 EKS, Flux, Gitea 등 실습 환경은 아직 사용할 수 없다.** `install.sh`가 내부적으로 `terraform init/plan/apply`를 실행하며 본 실습 인프라를 모두 배포하기 때문이다.

"별도의 2단계 워크플로"가 아니라, **하나의 SSM 스크립트 안에서 code-server 실행 → `install.sh`(Terraform 배포) → 완료 신호까지 모두 순차 처리**되는 구조다.

<br>

# WaitCondition의 역할

CFN은 기본적으로 **EC2 인스턴스가 "Running" 상태가 되면 해당 리소스 생성이 끝난 것**으로 판단한다. 그러나 이 워크숍에서는 EC2 내부에서 ~30분짜리 Terraform 작업이 끝나야 진짜 완료다. 이 갭을 메우는 것이 `WaitCondition`이다.

```yaml
WaitHandle:
  Type: AWS::CloudFormation::WaitConditionHandle

WaitCondition:
  Type: AWS::CloudFormation::WaitCondition
  DependsOn: SSMBootstrapAssociation
  Properties:
    Handle: !Ref WaitHandle
    Timeout: "2000"                    # 약 33분

WaitConditionUrlParameter:
  Type: "AWS::SSM::Parameter"
  Properties:
    Name: !Sub /${EnvironmentName}/waitcondition-url
    Type: "String"
    Value: !Ref WaitHandle             # 신호 전송용 URL을 SSM에 저장
```

동작 흐름은 다음과 같다.

1. CFN이 `WaitCondition` 리소스를 만들고 **최대 2000초(약 33분) 대기** 시작
2. `WaitConditionUrlParameter`를 통해 신호 전송용 URL이 SSM Parameter Store에 저장됨
3. EC2 내부 SSM 스크립트가 11번에서 이 URL을 조회하고, 13번 `install.sh` 실행이 끝나면 14번에서 해당 URL로 `curl -X PUT '{"Status":"SUCCESS",...}'` 신호를 전송
4. **신호를 받으면** → CFN 스택이 `CREATE_COMPLETE`
5. **신호 없이 타임아웃** → `CREATE_FAILED`

즉, CFN 스택의 `CREATE_COMPLETE`는 단순히 EC2가 부팅된 시점이 아니라, **EC2 내부의 Terraform 작업까지 모두 끝난 시점**을 의미한다. 참가자 입장에서 "스택 완료 → 바로 실습 시작"이 성립하는 이유가 이것이다.

<br>

# Outputs

스택 배포가 끝나면 CFN 콘솔의 "출력" 탭에 두 가지 값이 표시된다.

```yaml
Outputs:
  VsCodeIdeUrl:
    # EC2 퍼블릭 DNS를 보간해 VS Code 접속 URL 생성
    Value: !Sub "http://${EC2Instance.PublicDnsName}:8080/?folder=/home/ec2-user/environment"
  VsCodePassword:
    # SSM Parameter Store 콘솔 링크 (비밀번호는 4번에서 저장됨)
    Value: !Sub "https://${AWS::Region}.console.aws.amazon.com/systems-manager/parameters/coder-password"
```

| 출력 | 내용 |
|---|---|
| `VsCodeIdeUrl` | VS Code 웹 IDE 접속 URL (`http://<EC2 Public DNS>:8080/...`) |
| `VsCodePassword` | SSM Parameter Store의 `coder-password` 콘솔 링크 |

스택 배포 완료 후 이 두 값을 클릭하면 바로 VS Code 웹 IDE에 접속할 수 있다. 

> 실제 콘솔 출력 탭 화면과 접속 과정은 [설치 결과 확인]({% post_url 2026-04-16-Kubernetes-EKS-01-01-04-Installation-Result %})에서 스크린샷으로 확인한다.

<br>

# CloudFormation의 역할 범위

이 워크숍에서 CFN은 **"Terraform을 돌릴 환경을 만들기 위한 부팅 패드"** 역할만 한다. AWS 워크숍은 보통 "참가자 PC에 아무것도 안 깔게 한다"는 원칙이 있어서, 콘솔 클릭 한 번으로 환경을 띄울 수 있는 CFN을 부트스트랩 단계에 사용한다.

본 실습 인프라(EKS, Flux, Gitea 등)는 결국 Terraform으로 배포되므로, **GitOps 학습의 본질은 Terraform 세계에 있다.**

<br>

# 정리

- 이 파일(`vs-code-ec2.yaml`)은 **100% CloudFormation 전용**이다. Terraform이 읽을 수 없다
- 역할은 **"실습용 EC2 + 그 안에서 Terraform을 돌릴 부팅 환경"** 만들기까지다
- EC2 내부에서 SSM 부트스트랩 → `install.sh` → **Terraform 세계로 진입**한다
- `WaitCondition` 덕분에 CFN `CREATE_COMPLETE` = EC2 부팅 완료가 아니라 **내부 Terraform까지 끝난 시점**을 의미한다

다음 글에서는 13번에서 실행되는 `install.sh`가 내부적으로 어떤 Terraform 모듈을 호출하는지 분석한다.

<br>
