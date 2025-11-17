---
title:  "[Kubernetes] Kubernetes 클러스터 API 액세스 에러 해결"
excerpt: kubeconfig 인증서 만료로 인한 클러스터 API 사용 불가 문제를 해결하는 방법
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - k8s
  - k3s
  - kubernetes
  - Rancher
---







<br>



# 문제

K3s 클러스터 내 kubectl을 이용한 쿠버네티스 클러스터 API 작동하지 않음

```bash
$ kubectl get pod -n <namespace>
E0807 14:15:26.155304 4012452 memcache.go:265] couldn't get current server API group list: the server has asked for the client to provide credentials
E0807 14:15:26.155898 4012452 memcache.go:265] couldn't get current server API group list: the server has asked for the client to provide credentials
E0807 14:15:26.157457 4012452 memcache.go:265] couldn't get current server API group list: the server has asked for the client to provide credentials
E0807 14:15:26.157934 4012452 memcache.go:265] couldn't get current server API group list: the server has asked for the client to provide credentials
E0807 14:15:26.159294 4012452 memcache.go:265] couldn't get current server API group list: the server has asked for the client to provide credentials
error: You must be logged in to the server (the server has asked for the client to provide credentials)

```

<br>

# 원인

- `kubectl` 클라이언트가 해당 kubernetes 클러스터에 인증되어 있지 않음
- kubernetes 클러스터 인증을 위해 사용되는 kubeconfig 파일에서 인증서 만료 기한 확인 시, kubernetes cluster 인증서 만료된 것으로 보임
  ```bash
  $ kubectl config view --raw -o jsonpath='{.users[0].user.client-certificate-data}' | base64 -d | openssl x509 -noout -enddate
  notAfter=Jul 29 05:36:03 2025 GMT
  ```

  

<br>

# 해결

K3s 단에서 자체적으로 클러스터 접근을 위한 K3s credentials 파일을 업데이트하므로([참고: K3s Cluster Access](https://docs.k3s.io/cluster-access)), K3s의 새로운 kubeconfig 파일로 대체해 주면 됨

- K3s kubeconfig 파일 위치: `/etc/rancher/k3s/k3s.yaml`
- kubeconfig 파일 변경
  - (혹시 모르니) 기존 인증서 백업
    ```bash
    $ mv ~/.kube/config ~/.kube/config.bak
    ```
  - kubeconfig 업데이트
    ```bash
    $ sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
    ```
- kubectl 이용해 클러스터 API 호출 후 결과 확인
  ```bash
  $ kubectl get pod -n <my-namespace>
  NAME                                         READY   STATUS    RESTARTS   AGE
  <pod-name>							      1/1     Running   0          22d
  ```
  

<br>

# 참고



## K3s kubeconfig

`/etc/rancher/k3s/k3s.yaml`은 kubeconfig 포맷([참고: kubeconfig](https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/))의 인증서

```yaml
$ cat /etc/rancher/k3s/k3s.yaml
apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: <base64-encoded-cluster-certificate>
    server: <certificate-server>
  name: <cluster-name>
contexts:
- context:
    cluster: default
    user: default
  name: default
current-context: default
kind: Config
preferences: {}
users:
- name: default
  user:
    client-certificate-data: <base64-encoded-openssl-client-certificate>
    client-key-data: <base64-encoded-client-key>
```

- `/var/lib/rancher/k3s/server/cred/admin.kubeconfig`를 기반으로 K3s가 자동 생성한 kubeconfig 파일

- 포함하고 있는 정보

  - `clusters.cluster.certificate-authority-data`: (base64 인코딩된) 클러스터의 CA 인증서
  - `users.user.client-certificate-data`: (base64 인코딩된)클라이언트 인증서
  - `users.user.client-key-data`: (base64 인코딩된) 클라이언트 개인 키
  - `contexts.context`: 현재 context 설정
  - `current-context`: 기본 context

- K3s에 의해 갱신됨

  - K3s는 클러스터를 시작할 때 `/var/lib/rancher/k3s/server/tls` 아래에 인증서 및 키를 자동으로 생성하고 관리함
  - K3s는 인증서의 만료가 다가오면 알아서 재발급 및 교체
    - 유효 기간은 기본 1년
    - 인증서 유효 기간을 변경하고 싶을 경우, K3s 클러스터 시작 시 관련 플래그를 사용해 주면 됨
      ```bash
      k3s server \
        --cluster-init \
        --cluster-csr-ttl 43800h
      ```

    - 이미 생성된 인증서의 유효 기간은 변경되지 않음



<br>



## 비슷한 문제를 경험할 때

K3s 클러스터가 아니라, 다른 클러스터에서도 비슷한 문제를 경험할 수 있으나, 지금과 같이 kubeconfig 파일을 갱신해 주면 된다는 것을 기억하면 됨

- K3s: `/etc/rancher/k3s/k3s.yaml`
- Minikube: `minikube kubeconfig`
- EKS, GKE, AKS 등과 같은 클라우드 매니지드 클러스터: 일반적으로 단기 토큰 기반으로 인증서가 생성되며, 기본적으로 해당 클라우드 시스템에서 안내하는 방법을 따르면 됨
  - EKS: `aws eks update-kubeconfig`
  - GKE: `gcloud container clusters get-credentials`
