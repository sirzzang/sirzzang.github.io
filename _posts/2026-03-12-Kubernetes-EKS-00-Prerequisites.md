---
title:  "[EKS] EKS: 실습 환경 구성하기"
excerpt: "EKS 스터디를 위한 실습 환경을 구성해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-1

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 1주차 학습 내용을 기반으로 합니다.*



<br>

# TL;DR

이번 글에서는 **EKS 실습을 위한 사전 환경 구성**을 다룬다.

- **Terraform**: tfenv를 이용한 Terraform 설치 및 버전 관리
- **AWS CLI**: v2 설치 및 자격증명 설정
- **AWS 계정**: IAM User 생성, MFA 설정, 액세스 키 발급
- **EC2 키 페어**: EKS 워커 노드 SSH 접속을 위한 키 페어 생성

<br>

# 들어가며

[On-Premise K8s Hands-on Study]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-00 %})에서는 온프레미스 환경에서 Kubernetes 클러스터를 직접 구성하고 운영해 봤다. Kubernetes The Hard Way부터 kubeadm, Kubespray, RKE2까지 다양한 도구를 사용해 클러스터를 손수 구성하면서, 각 구성 요소의 역할과 동작 원리를 이해했다.

이번에는 AWS의 관리형 Kubernetes 서비스인 **EKS(Elastic Kubernetes Service)**를 다룬다. 온프레미스에서 직접 구성하던 컨트롤 플레인을 AWS가 관리해주는 환경에서, 클러스터 운영과 워크로드 배포에 집중한다.

EKS 실습을 시작하기 전에 필요한 도구와 환경을 준비하자.

<br>

> **사전 준비 체크리스트**
>
> - [x] Terraform 설치 (tfenv)
> - [x] AWS CLI v2 설치
> - [x] IAM User 생성 + AdministratorAccess 정책 부여
> - [x] 루트 유저 및 IAM User MFA 설정
> - [x] 액세스 키 발급 및 CSV 보관
> - [x] `aws configure`로 CLI 자격증명 설정
> - [x] `aws sts get-caller-identity`로 정상 동작 확인
> - [x] EC2 키 페어 생성

<br>

# Terraform 설치

EKS 클러스터 및 관련 인프라를 코드로 프로비저닝하기 위해 Terraform을 설치한다. 여러 버전의 Terraform을 관리할 수 있도록 **tfenv**를 사용한다.

## tfenv 설치

```bash
brew install tfenv
```

```
==> Fetching downloads for: tfenv
✔︎ Bottle tfenv (3.0.0)                                                                                           Downloaded   28.8KB/ 28.8KB
==> Installing tfenv dependency: grep
==> Pouring grep--3.12.arm64_tahoe.bottle.tar.gz
🍺  /opt/homebrew/Cellar/grep/3.12: 18 files, 1MB
==> Pouring tfenv--3.0.0.all.bottle.2.tar.gz
🍺  /opt/homebrew/Cellar/tfenv/3.0.0: 31 files, 106.7KB
```

<br>

## Terraform 버전 설치

설치 가능한 버전을 확인하고, 스터디에서 사용할 버전을 설치한다.

```bash
# 설치 가능 버전 리스트 확인
tfenv list-remote
```

```
1.15.0-alpha20260304
...
1.14.7
...
1.8.5
...
0.1.0
```

```bash
# Terraform 1.8.5 버전 설치
tfenv install 1.8.5
```

```
Installing Terraform v1.8.5
Downloading release tarball from https://releases.hashicorp.com/terraform/1.8.5/terraform_1.8.5_darwin_arm64.zip
############################################################################################################################################## 100.0%
Downloading SHA hash file from https://releases.hashicorp.com/terraform/1.8.5/terraform_1.8.5_SHA256SUMS
Installation of terraform v1.8.5 successful. To make this your default version, run 'tfenv use 1.8.5'
```

```bash
# 설치한 버전을 기본으로 설정
tfenv use 1.8.5
```

```
Switching default version to v1.8.5
Default version (when not overridden by .terraform-version or TFENV_TERRAFORM_VERSION) is now: 1.8.5
```

<br>

## 설치 확인

```bash
# tfenv로 설치한 버전 확인
tfenv list
```

```
* 1.8.5 (set by /Users/eraser/.config/tfenv/version)
```

```bash
# Terraform 버전 정보 확인
terraform version
```

```
Terraform v1.8.5
on darwin_arm64

Your version of Terraform is out of date! The latest version
is 1.14.7. You can update by downloading from https://www.terraform.io/downloads.html
```

> 최신 버전이 아니라는 경고가 나오지만, 스터디에서 사용하는 Terraform + EKS 조합에서 1.8.5를 전제로 하므로 무시해도 된다.

<br>

## 자동완성 설정

```bash
terraform -install-autocomplete
```

`.zshrc`에 자동완성 설정이 추가된다.

```bash
# .zshrc에 추가되는 내용
autoload -U +X bashcompinit && bashcompinit
complete -o nospace -C /usr/local/bin/terraform terraform
```

<br>

# AWS CLI 설치

EKS 관련 명령어(`aws eks update-kubeconfig`, `aws eks get-token` 등)가 v2에서 더 안정적으로 지원되므로, **AWS CLI v2**를 설치한다.

## 설치

macOS에서는 Homebrew 또는 공식 설치 파일을 사용할 수 있다.

```bash
# Homebrew
brew install awscli
aws --version
```

혹은 공식 설치 파일을 이용해도 된다.

```bash
# 공식 설치 파일
curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o "AWSCLIV2.pkg"
sudo installer -pkg AWSCLIV2.pkg -target /
aws --version
```

<br>

## 기존 설치 확인 및 업그레이드

이미 AWS CLI가 설치되어 있다면 버전을 확인한다.

```bash
aws --version
```

- `aws-cli/2.x.x` → v2이면 OK
- `aws-cli/1.x.x` → v1이면 v2로 업그레이드 필요

### macOS 업그레이드

```bash
# Homebrew
brew install awscli

# 또는 공식 설치 파일
curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o "AWSCLIV2.pkg"
sudo installer -pkg AWSCLIV2.pkg -target /
```

### Linux 업그레이드

```bash
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install --update
```

<br>

# AWS 계정 및 IAM 설정

## AWS 계정 생성

AWS 계정이 없다면 새로 생성한다.

![aws-account-create-1]({{site.url}}/assets/images/eks-prerequisites-account-create-1.png){: .align-center width="700"}

<br>

![aws-account-create-2]({{site.url}}/assets/images/eks-prerequisites-account-create-2.png){: .align-center width="700"}

<br>

![aws-account-create-3]({{site.url}}/assets/images/eks-prerequisites-account-create-3.png){: .align-center width="700"}

<br>

![aws-account-create-4]({{site.url}}/assets/images/eks-prerequisites-account-create-4.png){: .align-center width="700"}

<br>

![aws-account-create-5]({{site.url}}/assets/images/eks-prerequisites-account-create-5.png){: .align-center width="700"}

<br>

첫 생성 시 본인 명의 신용카드가 필요할 수 있다. 이후 과정은 생략한다. 계정 첫 생성 시, 루트 유저와 기본 리소스(기본 VPC) 등이 생성되며, AWS 계정에 숫자 ID가 부여된다. 추후 별명을 지정할 수도 있다.

> **참고: 루트 유저 vs. IAM User**
>
> AWS 계정에는 두 종류의 유저가 있다.
>
> | | 루트 유저 | IAM User |
> | --- | --- | --- |
> | **생성** | 계정당 단 하나. 자동 생성 | IAM에서 필요한 만큼 생성 |
> | **로그인** | 계정 생성 시 이메일 주소 | IAM에서 부여한 아이디 |
> | **기본 권한** | 모든 권한 자동 보유 | 없음. 별도 부여 필요 |
> | **AWS API 호출** | 불가 (Access Key 발급 불가) | 가능 (Access Key 발급 가능) |
> | **탈취 시** | 복구 매우 어려움 (삭제 불가) | 삭제 후 재생성 가능 |
> | **용도** | 계정 설정 변경, 빌링 등 관리 전용 | 일상적인 모든 작업 |
>
> 핵심은 **루트 유저는 관리용으로만 사용하고, 실제 작업은 IAM User로 하는 것**이다. 루트 유저는 탈취 시 복구가 극히 어려우므로 반드시 MFA를 설정하고, 가능한 한 사용을 자제한다. IAM User에 AdministratorAccess를 부여하면 루트 유저와 거의 동일한 권한을 가지지만, 빌링 관련 권한은 루트 유저가 별도로 허용해야 한다.
>
> 참고로 IAM User는 사람뿐 아니라 애플리케이션 등 가상 주체를 대표할 수도 있다. 


<br>

## 루트 유저 로그인

계정 생성 후 루트 유저로 로그인한다. IAM 유저가 아직 없으므로 루트 유저 로그인을 클릭한다.

![root-login-1]({{site.url}}/assets/images/eks-prerequisites-root-login-1.png){: .align-center width="700"}

<br>

![root-login-2]({{site.url}}/assets/images/eks-prerequisites-root-login-2.png){: .align-center width="700"}

<br>

![root-login-3]({{site.url}}/assets/images/eks-prerequisites-root-login-3.png){: .align-center width="700"}

<br>

![root-login-4]({{site.url}}/assets/images/eks-prerequisites-root-login-4.png){: .align-center width="700"}

<br>

로그인 후 리전을 `ap-northeast-2` (서울)로 변경한다.

![region-change]({{site.url}}/assets/images/eks-prerequisites-root-login-5.png){: .align-center width="700"}

<br>

## 루트 유저 MFA 설정

루트 유저는 계정의 모든 권한을 가지므로, 반드시 MFA를 설정한다. Google OTP 앱이 필요하다. 

![root-mfa-1]({{site.url}}/assets/images/eks-prerequisites-root-mfa-1.png){: .align-center width="700"}

<br>

![root-mfa-2]({{site.url}}/assets/images/eks-prerequisites-root-mfa-2.png){: .align-center width="700"}

디바이스로 Google OTP를 선택한다.

![root-mfa-3]({{site.url}}/assets/images/eks-prerequisites-root-mfa-3.png){: .align-center width="700"}

<br>

![root-mfa-4]({{site.url}}/assets/images/eks-prerequisites-root-mfa-4.png){: .align-center width="700"}

> 맥북 패스키를 이용해 추가로 MFA를 하나 더 설정해 놓으면 편리하다.

![root-mfa-passkey]({{site.url}}/assets/images/eks-prerequisites-root-mfa-5.png){: .align-center width="700"}

<br>

## 계정 별명 생성

IAM 유저 로그인 시 12자리 Account ID 대신 사용할 수 있는 별명(alias)을 설정한다.

![account-alias-1]({{site.url}}/assets/images/eks-prerequisites-account-alias-1.png){: .align-center width="700"}

<br>

![account-alias-2]({{site.url}}/assets/images/eks-prerequisites-account-alias-2.png){: .align-center width="700"}

<br>

![account-alias-3]({{site.url}}/assets/images/eks-prerequisites-account-alias-3.png){: .align-center width="700"}

<br>

![account-alias-4]({{site.url}}/assets/images/eks-prerequisites-account-alias-4.png){: .align-center width="700"}

<br>

## 관리 권한 가진 IAM User 생성

루트 유저는 일상적인 작업에 사용하면 안 된다. **AdministratorAccess** 정책이 부여된 IAM User를 생성한다.

![iam-user-create-1]({{site.url}}/assets/images/eks-prerequisites-iam-user-create-1.png){: .align-center width="700"}

> 다른 사람에게 계정을 공유하는 것이 아니라면, 비밀번호 재설정 옵션은 해제해도 된다.

![iam-user-create-2]({{site.url}}/assets/images/eks-prerequisites-iam-user-create-2.png){: .align-center width="700"}

**AdministratorAccess** 정책을 직접 연결한다. billing을 제외한 AWS 모든 권한을 제공한다.

![iam-user-create-3]({{site.url}}/assets/images/eks-prerequisites-iam-user-create-3.png){: .align-center width="700"}

<br>

![iam-user-create-4]({{site.url}}/assets/images/eks-prerequisites-iam-user-create-4.png){: .align-center width="700"}

> 암호는 절대로 유출되지 않도록 조심한다.

![iam-user-create-5]({{site.url}}/assets/images/eks-prerequisites-iam-user-create-5.png){: .align-center width="700"}

<br>

## IAM User MFA 설정

생성한 IAM User도 AdministratorAccess 권한을 가지고 있으므로, MFA를 설정한다.

![iam-mfa-1]({{site.url}}/assets/images/eks-prerequisites-iam-mfa-1.png){: .align-center width="700"}

<br>

![iam-mfa-2]({{site.url}}/assets/images/eks-prerequisites-iam-mfa-2.png){: .align-center width="700"}

<br>

![iam-mfa-3]({{site.url}}/assets/images/eks-prerequisites-iam-mfa-3.png){: .align-center width="700"}

<br>

## 루트 유저 로그아웃 후 IAM User 로그인

루트 유저를 로그아웃하고, 앞서 생성한 계정 별명을 이용해 IAM User로 로그인한다.

![iam-login]({{site.url}}/assets/images/eks-prerequisites-iam-login.png){: .align-center width="700"}

<br>

# IAM User 액세스 키 발급

AWS CLI에서 사용할 액세스 키를 발급한다. AWS 콘솔 → IAM → 사용자 → 해당 IAM User 선택 → **보안 자격 증명** 탭 → **액세스 키 만들기**로 이동한다.

![access-key-1]({{site.url}}/assets/images/eks-prerequisites-access-key-1.png){: .align-center width="700"}

<br>

![access-key-2]({{site.url}}/assets/images/eks-prerequisites-access-key-2.png){: .align-center width="700"}

> **Secret Access Key는 발급 시 한 번만 확인할 수 있다.** 반드시 CSV 파일을 다운로드해서 안전하게 보관한다.

<br>

# AWS CLI 자격증명 설정

## 기존 환경변수 해제

기존에 AWS 관련 환경변수가 설정되어 있다면 해제한다.

```bash
unset AWS_ACCESS_KEY_ID
unset AWS_SECRET_ACCESS_KEY
unset AWS_DEFAULT_REGION
```

<br>

## 자격증명 설정

발급받은 액세스 키로 AWS CLI 자격증명을 설정한다.

```bash
aws configure
AWS Access Key ID [None]: AKIA##########    # 액세스 키 ID 입력
AWS Secret Access Key [None]: wJalrXU#####  # 비밀 액세스 키 입력
Default region name [None]: ap-northeast-2  # 서울 리전
Default output format [None]: json          # 선택사항
```

<br>

## 자격증명 확인

설정이 정상적으로 되었는지 확인한다.

```bash
# 자격증명 설정 확인
aws configure list
```

```
      Name                    Value             Type    Location
      ----                    -----             ----    --------
   profile                <not set>             None    None
access_key     ****************XXXX shared-credentials-file
secret_key     ****************XXXX shared-credentials-file
    region           ap-northeast-2      config-file    ~/.aws/config
```

```bash
# S3 버킷 목록 조회로 정상 동작 테스트
aws s3 ls
```

```bash
# 현재 자격증명의 IAM 정보 확인
aws sts get-caller-identity
```

```json
{
    "UserId": "AIDA6XXXXXXXXXXXXX",
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:user/my-iam-user"
}
```

`aws sts get-caller-identity`가 정상적으로 IAM User 정보를 반환하면 자격증명 설정이 완료된 것이다.

<br>

# EC2 키 페어 생성

EKS 워커 노드에 SSH로 접속하기 위한 EC2 키 페어를 생성한다. **리전 단위로 한 번 생성하면** 같은 리전의 여러 EC2 인스턴스에 재사용할 수 있다.

## 콘솔에서 생성

EC2 → 네트워크 및 보안 → 키 페어 → **키 페어 생성**

![keypair-console]({{site.url}}/assets/images/eks-prerequisites-keypair-console.png){: .align-center width="700"}

## CLI로 생성

```bash
aws ec2 create-key-pair --key-name my-eks-keypair --query 'KeyMaterial' --output text > my-eks-keypair.pem
chmod 400 my-eks-keypair.pem
```

CLI로 생성한 뒤 콘솔에서 확인하면 키 페어가 등록되어 있다.

![keypair-cli-confirm]({{site.url}}/assets/images/eks-prerequisites-keypair-cli-confirm.png){: .align-center width="700"}

<br>

# 결론

EKS 실습을 위한 사전 환경 구성을 완료했다. 정리하면 다음과 같다.

| 구성 항목 | 도구/서비스 | 비고 |
| --- | --- | --- |
| **IaC** | Terraform 1.8.5 (tfenv) | 클러스터 및 인프라 프로비저닝 |
| **AWS CLI** | v2 | EKS 관련 명령어 지원 |
| **AWS 계정** | IAM User + MFA | AdministratorAccess 정책 |
| **자격증명** | `aws configure` | 액세스 키 기반 CLI 인증 |
| **SSH 접근** | EC2 키 페어 | 워커 노드 SSH 접속용 |

On-Premise K8s 스터디에서는 VirtualBox + Vagrant로 VM을 직접 프로비저닝하고 클러스터를 구성했다면, EKS 스터디에서는 Terraform으로 AWS 인프라를 프로비저닝하고 관리형 Kubernetes 서비스를 사용한다. 인프라 프로비저닝의 대상이 로컬 VM에서 클라우드 리소스로 바뀐 것이다.

다음 글에서는 본격적으로 EKS 클러스터를 배포한다.

<br>
