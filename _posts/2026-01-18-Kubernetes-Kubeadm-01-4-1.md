---
title:  "[Kubernetes] Cluster: Kubeadm을 이용해 클러스터 구성하기 - 1.4.1. 편의 도구 설치"
excerpt: "kubectl 관련 편의 도구를 설치하여 클러스터 관리 환경을 구성해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-3
hidden: true

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 3주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글의 목표는 **kubectl 편의 도구 설치**이다.

- **kubectl 자동 완성**: kubectl, kubeadm 자동 완성 및 alias 설정
- **kubecolor**: kubectl 출력 컬러 표시
- **kubectx/kubens**: context 및 namespace 간편 전환
- **kube-ps1**: 프롬프트에 현재 context/namespace 표시
- **Helm**: Kubernetes 패키지 관리 도구
- **k9s**: 터미널 기반 Kubernetes 대시보드

<br>

# 들어가며

[이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-4 %})에서 kubeadm init을 실행하여 컨트롤 플레인을 구성했다. 이번 글에서는 클러스터 관리를 위한 편의 도구들을 설치한다.

<br>

# 편의 도구 설치

클러스터 관리를 위한 도구들을 설치한다.

## kubectl 자동 완성

```bash
# 현재 세션에 즉시 적용
source <(kubectl completion bash)   # kubectl 자동 완성
source <(kubeadm completion bash)   # kubeadm 자동 완성

# 영구 설정 (다음 로그인부터 자동 적용)
echo 'source <(kubectl completion bash)' >> /etc/profile   # kubectl
echo 'source <(kubeadm completion bash)' >> /etc/profile   # kubeadm

# kubectl을 k로 alias
alias k=kubectl
complete -o default -F __start_kubectl k   # k에도 자동 완성 적용
echo 'alias k=kubectl' >> /etc/profile
echo 'complete -o default -F __start_kubectl k' >> /etc/profile

# 테스트
k get node
# NAME      STATUS     ROLES           AGE   VERSION
# k8s-ctr   NotReady   control-plane   27m   v1.32.11
```

이제 `k`만 입력해도 `kubectl`처럼 동작하고, Tab 자동 완성도 사용할 수 있다.

<br>

## kubecolor 설치

kubectl 출력을 컬러로 표시해주는 도구다.

```bash
# kubecolor 설치
dnf install -y 'dnf-command(config-manager)'   # config-manager 플러그인 설치
dnf config-manager --add-repo https://kubecolor.github.io/packages/rpm/kubecolor.repo   # 저장소 추가
dnf install -y kubecolor

# 테스트 (출력이 컬러로 표시됨)
kubecolor get node
kubecolor describe node

# alias 설정 (kc로 짧게 사용)
alias kc=kubecolor
echo 'alias kc=kubecolor' >> /etc/profile
```

![kubecolor-result]({{site.url}}/assets/images/kubecolor-result.png){: .align-center}


<br>

## kubectx, kubens 설치

context와 namespace를 쉽게 전환할 수 있는 도구다.
- **kubectx**: 여러 클러스터(context) 간 전환
- **kubens**: 네임스페이스 간 전환

```bash
# 설치
dnf install -y git
git clone https://github.com/ahmetb/kubectx /opt/kubectx
ln -s /opt/kubectx/kubectx /usr/local/bin/kubectx   # context 전환 도구
ln -s /opt/kubectx/kubens /usr/local/bin/kubens     # namespace 전환 도구

# 테스트
kubens                  # 네임스페이스 목록 (현재 선택된 것 하이라이트)
kubens kube-system      # kube-system으로 전환
kubectl get pod         # -n 옵션 없이도 kube-system의 Pod 조회
kubens default          # 다시 default로 복귀

kubectx                 # context 목록 (현재는 1개뿐)
```

<br>

## kube-ps1 설치

bash 프롬프트에 현재 context와 namespace를 표시한다.

```bash
# kube-ps1 설치
git clone https://github.com/jonmosco/kube-ps1.git /root/kube-ps1

# bash_profile 설정
cat << "EOT" >> /root/.bash_profile
source /root/kube-ps1/kube-ps1.sh
KUBE_PS1_SYMBOL_ENABLE=true
function get_cluster_short() {
  echo "$1" | cut -d . -f1
}
KUBE_PS1_CLUSTER_FUNCTION=get_cluster_short
KUBE_PS1_SUFFIX=') '
PS1='$(kube_ps1)'$PS1
EOT

# 자동 root 전환 설정 (Vagrant용)
echo "sudo su -" >> /home/vagrant/.bashrc
```
![kubeps1-result]({{site.url}}/assets/images/kubeps1-result.png){: .align-center}

<br>

## Helm 설치

Kubernetes 패키지 관리 도구다.

```bash
# Helm 3 설치 (버전 지정)
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | DESIRED_VERSION=v3.18.6 bash
# Downloading https://get.helm.sh/helm-v3.18.6-linux-arm64.tar.gz
# Verifying checksum... Done.
# Preparing to install helm into /usr/local/bin
# helm installed into /usr/local/bin/helm

# 버전 확인
helm version
# version.BuildInfo{Version:"v3.18.6", GitCommit:"b76a950f6835474e0906b96c9ec68a2eff3a6430", GitTreeState:"clean", GoVersion:"go1.24.6"}
```

<br>

## k9s 설치

터미널 기반 Kubernetes 대시보드다.

```bash
# k9s 설치
CLI_ARCH=amd64
if [ "$(uname -m)" = "aarch64" ]; then CLI_ARCH=arm64; fi
wget https://github.com/derailed/k9s/releases/latest/download/k9s_linux_${CLI_ARCH}.tar.gz
tar -xzf k9s_linux_*.tar.gz
chown root:root k9s
mv k9s /usr/local/bin/
chmod +x /usr/local/bin/k9s

# 실행 테스트
k9s
# 종료: Ctrl+C 또는 :q
```

![k9s-result]({{site.url}}/assets/images/k9s-result.png){: .align-center}


<br>

## 설정 적용

```bash
# 셸 재시작하여 /etc/profile 설정 적용
exit   # root -> vagrant
exit   # vagrant -> host

# 다시 접속 (vagrant 로그인 시 자동으로 root 전환됨)
vagrant ssh k8s-ctr

# context 이름 변경 (선택, 기본 이름이 너무 길어서)
kubectl config rename-context "kubernetes-admin@kubernetes" "HomeLab"
# Context "kubernetes-admin@kubernetes" renamed to "HomeLab".

kubens default   # 기본 네임스페이스 확인
```
![k-result.png]({{site.url}}/assets/images/k-result.png){: .align-center}

<br>

[다음 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-5 %})에서는 Flannel CNI를 설치한다.

<br>
