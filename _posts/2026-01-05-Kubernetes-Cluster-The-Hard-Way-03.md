---
title:  "[Kubernetes] Cluster: 내 손으로 클러스터 구성하기 - 3. Provisioning Compute Resoures"
excerpt: "클러스터 구성에 필요한 모든 머신 정보를 Machine Database에 정리하고, SSH 키 기반 인증과 호스트명 설정을 통해 자동화된 스크립트 실행 기반을 마련해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-1
hidden: true

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글의 목표는 **클러스터 구성에 필요한 컴퓨트 리소스(VM) 정보 정리 및 SSH 접속 환경 설정**이다. [Kubernetes the Hard Way 튜토리얼의 Provisioning Compute Resources 단계](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/03-compute-resources.md)를 따라 진행한다.

- 클러스터 머신 정보를 담은 Machine Database(`machines.txt`) 구축
- Jumpbox에서 각 노드로의 비밀번호 없는 SSH 키 인증 설정
- 호스트명(FQDN) 기반 네트워크 접근성 검증

![kubernetes-the-hard-way-cluster-structure-3]({{site.url}}/assets/images/kubernetes-the-hard-way-cluster-structure-3.png)

<br>

# 컴퓨트 리소스 프로비저닝

Kubernetes 클러스터를 구성하기 위해서는 컨트롤 플레인을 호스팅할 머신과 컨테이너가 실행될 워커 노드 머신들이 필요하다. 이 단계에서는 클러스터 구성에 필요한 머신들의 정보를 정리하고, 각 머신 간 SSH 접속이 가능하도록 네트워크 설정을 진행한다.

> "컴퓨트 리소스 프로비저닝"은 Kubernetes 자체의 개념이 아니라, 클라우드/인프라 분야에서 사용하는 용어이다. 원본 튜토리얼(Kubernetes the Hard Way)은 클라우드에서 VM 인스턴스를 생성하는 과정을 고려하여 "프로비저닝"이라고 표현한 것으로 보인다. Kubernetes는 이미 존재하는 머신 위에서 동작하는 오케스트레이션 플랫폼이므로, 컴퓨트 리소스 프로비저닝은 Kubernetes의 개념이 아니라 클러스터 구성 전 인프라 준비 단계이다.

<br>

## Machine Database

Machine Database는 클러스터를 구성하는 모든 머신의 정보를 한 곳에 정리한 텍스트 파일이다. 각 머신의 IP 주소, FQDN(Fully Qualified Domain Name), 호스트명, Pod 서브넷 정보를 저장한다.

> `machines.txt` 파일은 Kubernetes 자체의 개념이 아니라, 이 튜토리얼(Kubernetes the Hard Way)에서 여러 머신에 반복적으로 명령을 실행하기 위해 만든 편의용 텍스트 파일이다. Kubernetes 공식 문서나 표준에는 없는 개념이며, 실습의 자동화를 위한 도구이다.

<br>

텍스트 형식으로, 아래와 같은 스키마를 갖는다.
```bash
IPV4_ADDRESS FQDN HOSTNAME POD_SUBNET

# 예시
192.168.10.100 server.kubernetes.local server
192.168.10.101 node-0.kubernetes.local node-0 10.200.0.0/24
192.168.10.102 node-1.kubernetes.local node-1 10.200.1.0/24
```

### Pod 서브넷

Pod 서브넷이란, 각 워커 노드에 할당될 Pod 네트워크 대역을 의미한다. Kubernetes는 각 노드마다 **고유한** Pod CIDR 범위를 할당하여 Pod 간 통신을 관리한다. 예컨대, 위의 파일에서 `10.200.0.0/24`는 node-0에 할당될 Pod 네트워크 대역이다.

다만, 컨트롤 플레인(server)은 kubelet이 동작하지 않으므로 Pod 서브넷 설정이 필요 없다.

원본 튜토리얼에서는 각 머신이 서로 통신 가능하고 jumpbox에서 접근 가능한 한, 어떤 IP 주소든 할당 가능하다고 명시되어 있다.


### Machine Database 생성

`machines.txt` 파일을 생성하여 각 머신의 정보를 저장한다:

```bash
# (jumpbox) #
# machines.txt 생성
cat <<EOF > machines.txt
192.168.10.100 server.kubernetes.local server
192.168.10.101 node-0.kubernetes.local node-0 10.200.0.0/24
192.168.10.102 node-1.kubernetes.local node-1 10.200.1.0/24
EOF

# 생성 확인
cat machines.txt
```


```
192.168.10.100 server.kubernetes.local server
192.168.10.101 node-0.kubernetes.local node-0 10.200.0.0/24
192.168.10.102 node-1.kubernetes.local node-1 10.200.1.0/24
```

<br>

이 파일은 이후 스크립트에서 반복문으로 읽어 각 머신에 명령을 실행할 때 사용된다.


<br>

## SSH 접속 설정

클러스터 내 모든 머신에 대한 설정 작업은 SSH를 통해 원격으로 수행한다. 따라서 각 머신에 root 계정으로 SSH 접속이 가능해야 한다.

<br>

### root SSH 접근 설정

기본적으로 Debian 시스템은 보안상의 이유로 root 계정의 SSH 접근을 비활성화한다. 하지만 이 튜토리얼에서는 편의를 위해 root SSH 접근을 활성화한다. 거듭 강조하지만, 프로덕션 환경에서는 보안상 권장되지 않으며, 일반 사용자 계정과 sudo를 사용하는 것이 좋다.

우리 실습 환경에서는 [이전 글]({{site.url}}/kubernetes/Kubernetes-Cluster-The-Hard-Way-02/)에서 이미 root SSH 접근이 설정되어 있다.


따라서 간단히 설정만 확인한다.
```bash
# (jumpbox) #
# SSH 설정에서 암호 인증 및 root 로그인 허용 여부 확인
grep "^[^#]" /etc/ssh/sshd_config | grep -E "(PasswordAuthentication|PermitRootLogin)"
```


```
PasswordAuthentication yes
PermitRootLogin yes
```

<br>

만약 root SSH 접근이 비활성화되어 있다면, 각 머신에 접속하여 다음과 같이 설정할 수 있다. 원본 가이드를 참고하여 기록해 둔다.

1. 일반 사용자 계정으로 SSH 접속 후 root로 전환:
```bash
su - root
```

2. `/etc/ssh/sshd_config` 파일 수정:
```bash
sed -i \
  's/^#*PermitRootLogin.*/PermitRootLogin yes/' \
  /etc/ssh/sshd_config
```

3. SSH 서버 재시작:
```bash
systemctl restart sshd
```

이 방법은 다른 환경에서 root SSH 접근을 설정해야 할 때 유용하다.

<br>

### SSH 키 생성 및 분배

비밀번호 없이 SSH 접속을 위해 SSH 키 쌍을 생성하고 각 머신에 공개키를 분배한다. 이를 통해 이후 작업에서 매번 비밀번호를 입력할 필요 없이 자동화된 스크립트 실행이 가능하다.

```bash
# (jumpbox) #
# SSH 키 쌍 생성 (-N "": 비밀번호 없음)
ssh-keygen -t rsa -N "" -f /root/.ssh/id_rsa
```


```
Generating public/private rsa key pair.
Your identification has been saved in /root/.ssh/id_rsa
Your public key has been saved in /root/.ssh/id_rsa.pub
The key fingerprint is:
SHA256:aDLSpbBcevXmv8+EfobiYSPjD82yEindP9rbkcxcEN4 root@jumpbox
...
```

### SSH 키 복사 및 authorized_keys 설정

먼저, 생성한 공개키를 각 머신에 복사하여 비밀번호 없이 SSH 접속이 가능하도록 설정한다.

```bash
# (jumpbox) #
while read IP FQDN HOST SUBNET; do
  # sshpass -p 'qwe123': 지정된 비밀번호로 자동 인증
  # -o StrictHostKeyChecking=no: 처음 접속 시 호스트 키 확인(yes/no) 건너뛰기
  # ssh-copy-id: 로컬의 id_rsa.pub 내용을 원격 서버의 authorized_keys에 추가
  sshpass -p 'qwe123' \
    ssh-copy-id -o StrictHostKeyChecking=no \
    root@${IP}
done < machines.txt
```

- `ssh-copy-id` 명령어
  - 로컬의 공개키(`~/.ssh/id_rsa.pub`)를 원격 서버의 `~/.ssh/authorized_keys` 파일에 자동으로 추가
  - `authorized_keys`에 공개키가 등록되면, 해당 개인키를 가진 클라이언트는 비밀번호 없이 SSH 접속 가능
- `while read IP FQDN HOST SUBNET; do ... done < machines.txt` 구문
  - `machines.txt` 파일의 각 줄을 읽어서 공백으로 구분된 4개의 필드(IP, FQDN, HOST, SUBNET)를 변수에 할당
  - 각 줄마다 반복문 내부의 명령을 실행
  - 이를 통해 여러 머신에 동일한 작업 자동 수행 가능

<br>
이후, authorized_keys 파일을 확인해 보자.

```bash
# (jumpbox) #
# 키 복사 확인
while read IP FQDN HOST SUBNET; do
  ssh -n root@${IP} cat /root/.ssh/authorized_keys
done < machines.txt
```


```
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCb1Odbh5jtHiH/H5MOVb34XHvYU/lm45T9/4CJPkjipmQho9zyQJ2slg0+GimVKP+y3Yx633IyzFCEjUTcumYGZtFHotKnVUcEmwhZCfW9Cu9mSag5CATtdR94DOL8WDO20mQDUeJ/DkXsiHNO+uUw9JAD+RuG8LVCw9FJ7kX0U36e55X74Jd/bCYbXhmTTRWyJn09SRdmoMDqFscuQi7iv+JZmXonS+fSZfidpqRJFg/xbLtYAjyJI71qBdLe/Hmk3H/nRYAHEciQw1LRHVFFwCdvUbb0BNtGQRQJ/eJxO0IiMJ9dqHq2L1/WUN8em8YUm3dMWtft/zGK+ZF1sRuDzSKRqGsunhkER+jYrB2EwLGZEHJTJ/CbBOiq+0ZASv6UKRgyLS+tf3qk8joBLYUpxvLpt7VzpPqicTUXQ4tN2dvGWH8JRjI0b+di1NBO7npteNXwXwnzklag6d25wnuxtqScX1ShJ212ErAccBlcYmiREITmcw5Y3GcxlltIfZc= root@jumpbox
...
```

각 머신의 `authorized_keys` 파일에 jumpbox의 공개키가 등록되어 있음을 확인할 수 있다.

<br>

### IP 기반 SSH 접속 확인

SSH 키 분배가 완료되었으므로, 이제 비밀번호 없이 각 머신에 접속할 수 있다. 머신 데이터베이스에서 IP를 읽어 SSH 접속을 확인한다:

```bash
# (jumpbox) #
# 비밀번호 없이 각 노드의 hostname 출력 테스트
while read IP FQDN HOST SUBNET; do
  ssh -n root@${IP} hostname
done < machines.txt
```


```
server
node-0
node-1
```

<br>

## Hostname 설정

Hostname이란, **시스템의 이름을 나타내는 식별자**로, 네트워크에서 머신을 식별하는 데 사용되며, IP 주소보다 기억하기 쉽고 관리하기 편리하다. 

이 단계에서 Hostname을 설정하는 이유는 다음과 같다:
1. **편의성**: jumpbox에서 각 머신에 명령을 실행할 때 IP 대신 호스트명 사용 가능
2. **클러스터 내 통신**: Kubernetes 클라이언트들이 API 서버에 접근할 때 IP 주소 대신 호스트명을 사용한다. 이는 인증서 기반 인증과 호환되며, IP 변경 시에도 유연한 대응 가능

<br>

우리 실습 환경에서는 이미 [이전 글]({{site.url}}/kubernetes/Kubernetes-Cluster-The-Hard-Way-01/)에서 `init_cfg.sh`로 설정해 두었다.

앞에서와 마찬가지로, 설정이 잘 되었는지만 확인한다.

```bash
# (jumpbox) #
# 모든 노드에서 FQDN(정규화된 도메인 이름) 확인
while read IP FQDN HOST SUBNET; do
  ssh -n root@${IP} hostname --fqdn
done < machines.txt
```


```
server.kubernetes.local
node-0.kubernetes.local
node-1.kubernetes.local
```

<br>

만약 설정이 되어 있지 않았다면, 원본 가이드를 따라 아래와 같이 hostname을 설정하면 된다.

```bash
# hostname 설정
while read IP FQDN HOST SUBNET; do
    CMD="sed -i 's/^127.0.1.1.*/127.0.1.1\t${FQDN} ${HOST}/' /etc/hosts"
    ssh -n root@${IP} "$CMD"
    ssh -n root@${IP} hostnamectl set-hostname ${HOST}
    ssh -n root@${IP} systemctl restart systemd-hostnamed
done < machines.txt
```
- `hostnamectl set-hostname`: 시스템의 hostname을 설정한다
- `systemctl restart systemd-hostnamed`: hostname 변경사항을 적용하기 위해 서비스를 재시작한다

<br>

## hosts 파일 설정

`/etc/hosts` 파일은 호스트명과 IP 주소의 매핑을 저장하는 로컬 DNS 역할을 한다. 이 파일에 각 머신의 정보를 추가하면, DNS 서버 없이도 호스트명으로 접근할 수 있다.

> *참고*: hosts 파일 동작 원리
> - 시스템이 호스트명을 IP로 변환할 때, 먼저 `/etc/hosts` 파일을 확인한다
> - 해당 호스트명이 있으면 그 IP 주소를 사용하고, 없으면 DNS 서버에 쿼리한다
> - 각 노드의 `/etc/hosts`에 모든 클러스터 노드 정보가 있으면, 호스트명으로 서로 접근할 수 있다

<br>

역시나 우리 실습 환경에서는 이미 `/etc/hosts` 파일이 설정되어 있다. 설정 확인 및 호스트명으로 SSH 접속이 가능한지 테스트한다.

```bash
# (jumpbox) #
# 각 노드의 hosts 파일 내용 확인
while read IP FQDN HOST SUBNET; do
  ssh -n root@${IP} cat /etc/hosts
done < machines.txt
```


```
127.0.0.1       localhost
::1     localhost ip6-localhost ip6-loopback
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters
192.168.10.10  jumpbox
192.168.10.100 server.kubernetes.local server 
192.168.10.101 node-0.kubernetes.local node-0
192.168.10.102 node-1.kubernetes.local node-1
```

```bash
# (jumpbox) #
# 호스트명으로 접속 테스트
while read IP FQDN HOST SUBNET; do
  ssh -n root@${HOST} hostname
done < machines.txt
```


```
server
node-0
node-1
```

마찬가지로, 원본 가이드에서 hosts 파일을 설정하여 각 머신의 `/etc/hosts`에 추가하는 방법만 기록해 둔다.

1. Jumpbox의 /etc/hosts에 추가
```bash
cat hosts >> /etc/hosts
```

2. 각 원격 머신의 /etc/hosts에 추가
```bash
while read IP FQDN HOST SUBNET; do
  scp hosts root@${HOST}:~/
  ssh -n root@${HOST} "cat hosts >> /etc/hosts"
done < machines.txt
```


<br>


# 결과

이 단계를 완료하면 다음과 같은 결과를 얻을 수 있다:

1. **Machine Database 생성**: `machines.txt` 파일에 모든 머신 정보가 정리되어 있다
2. **SSH 키 기반 인증**: 비밀번호 없이 모든 머신에 SSH 접속이 가능하다
3. **호스트명 기반 접속**: IP 주소 대신 호스트명으로 접속할 수 있다

```bash
# (jumpbox) #
# IP로 접속 확인
while read IP FQDN HOST SUBNET; do
  ssh -n root@${IP} hostname
done < machines.txt

# 호스트명으로 접속 확인
ssh root@server hostname
ssh root@node-0 hostname
ssh root@node-1 hostname
```


```
server
node-0
node-1
```

모든 머신에 IP와 호스트명 모두로 SSH 접속이 가능하면 성공이다.

<br>

이번 단계를 통해 클러스터를 구성할 모든 머신의 정보를 정리하고, 각 머신 간 SSH 접속이 가능하도록 네트워크 환경을 구성했다. `machines.txt` 파일을 통해 머신 정보를 중앙에서 관리할 수 있게 되었고, SSH 키 기반 인증과 호스트명 설정을 통해 이후 단계에서 자동화된 스크립트 실행이 가능한 기반을 마련했다.

<br> 

다음 단계에서는 Kubernetes 클러스터의 보안을 위한 CA(Certificate Authority) 설정 및 TLS 인증서 생성 작업을 진행한다.

