---
title:  "[Kubernetes] Cluster: 내 손으로 클러스터 구성하기 - 8.2. Bootstrapping the Kubernetes Control Plane"
excerpt: "Kubernetes Control Plane 컴포넌트들을 server 노드에 배포하고 시작해 보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-1

---

<br>

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

**server 노드에 kube-apiserver, kube-scheduler, kube-controller-manager를 배포하고 시작한다.**

이번 글의 목표는 **Kubernetes Control Plane 배포 및 검증**이다. [Kubernetes the Hard Way 튜토리얼의 Bootstrapping the Kubernetes Control Plane 단계](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/08-bootstrapping-kubernetes-controllers.md)를 수행한다.

- 파일 배포: jumpbox에서 server 노드로 바이너리, unit 파일, 설정 파일 전송
- Control Plane 실행: systemd로 kube-apiserver, kube-scheduler, kube-controller-manager 시작
- 동작 검증: 서비스 상태, 포트 리스닝, 클러스터 정보 확인
- RBAC 설정: kube-apiserver가 kubelet에 접근할 수 있도록 권한 부여

이전 글에서 분석한 설정 파일들을 실제로 배포하고, Control Plane이 정상적으로 동작하는지 확인한다.

![kubernetes-the-hard-way-cluster-structure-8]({{site.url}}/assets/images/kubernetes-the-hard-way-cluster-structure-8.png)

<br>

# 파일 배포

jumpbox에서 `server` 가상 머신으로 필요한 바이너리, systemd unit 파일, 설정 파일을 전송한다.

```bash
scp \
  downloads/controller/kube-apiserver \
  downloads/controller/kube-controller-manager \
  downloads/controller/kube-scheduler \
  downloads/client/kubectl \
  units/kube-apiserver.service \
  units/kube-controller-manager.service \
  units/kube-scheduler.service \
  configs/kube-scheduler.yaml \
  configs/kube-apiserver-to-kubelet.yaml \
  root@server:~/

# 출력
kube-apiserver           100%   86MB 107.8MB/s   00:00    
kube-controller-manager  100%   80MB 119.1MB/s   00:00    
kube-scheduler           100%   61MB 103.0MB/s   00:00    
kubectl                  100%   53MB  99.4MB/s   00:00    
...
```

전송된 파일을 확인한다.

```bash
ssh server ls -l /root

# 출력 (축약)
-rw------- 1 root root     9953 Jan  8 22:41 admin.kubeconfig
-rw-r--r-- 1 root root     1899 Jan  8 00:21 ca.crt
-rw------- 1 root root     3272 Jan  8 00:21 ca.key
-rw-r--r-- 1 root root      271 Jan  8 22:55 encryption-config.yaml
-rwxr-xr-x 1 root root 90243224 Jan  9 20:09 kube-apiserver          # 바이너리
-rw-r--r-- 1 root root     1442 Jan  9 20:10 kube-apiserver.service  # unit 파일
-rw-r--r-- 1 root root      727 Jan  9 20:10 kube-apiserver-to-kubelet.yaml  # RBAC 설정
...
```

<br>

# Control Plane 실행

`server` 가상 머신에 접속하여 작업을 진행한다.

```bash
ssh root@server
```

## 디렉토리 생성

설정 파일을 저장할 디렉토리를 생성한다.

```bash
mkdir -p /etc/kubernetes/config # Kubernetes 설정 파일 저장 경로
```

<br>

## 바이너리 설치

Control Plane 바이너리를 `/usr/local/bin`에 설치한다.

```bash
mv kube-apiserver \
  kube-controller-manager \
  kube-scheduler kubectl \
  /usr/local/bin/

# 확인
ls -l /usr/local/bin/kube-*
-rwxr-xr-x 1 root root 90243224 Jan  9 20:09 /usr/local/bin/kube-apiserver
-rwxr-xr-x 1 root root 83427480 Jan  9 20:09 /usr/local/bin/kube-controller-manager
-rwxr-xr-x 1 root root 64225432 Jan  9 20:09 /usr/local/bin/kube-scheduler
```

<br>

## kube-apiserver 설정

kube-apiserver가 사용할 인증서, 키, 설정 파일을 `/var/lib/kubernetes/`에 배치한다.

```bash
mkdir -p /var/lib/kubernetes/
mv ca.crt ca.key \
  kube-api-server.key kube-api-server.crt \
  service-accounts.key service-accounts.crt \
  encryption-config.yaml \
  /var/lib/kubernetes/

# 확인
ls -l /var/lib/kubernetes/
total 28
-rw-r--r-- 1 root root 1899 Jan  8 00:21 ca.crt
-rw------- 1 root root 3272 Jan  8 00:21 ca.key
-rw-r--r-- 1 root root  271 Jan  8 22:55 encryption-config.yaml
-rw-r--r-- 1 root root 2354 Jan  8 00:21 kube-api-server.crt
-rw------- 1 root root 3272 Jan  8 00:21 kube-api-server.key
-rw-r--r-- 1 root root 2004 Jan  8 00:21 service-accounts.crt
-rw------- 1 root root 3272 Jan  8 00:21 service-accounts.key
```

> **경로 선택 이유**: `/var/lib/kubernetes/`는 Kubernetes 런타임 데이터를 저장하는 관례적인 경로다. 인증서, 키 등 민감한 데이터는 여기에 저장하고, 설정 파일은 `/etc/kubernetes/config/`에 저장한다.

systemd unit 파일을 설치한다.

```bash
mv kube-apiserver.service /etc/systemd/system/
```

<br>

## kube-controller-manager 설정

kube-controller-manager의 kubeconfig를 배치하고 unit 파일을 설치한다.

```bash
mv kube-controller-manager.kubeconfig /var/lib/kubernetes/
mv kube-controller-manager.service /etc/systemd/system/
```

<br>

## kube-scheduler 설정

kube-scheduler의 kubeconfig, 설정 파일, unit 파일을 각각 배치한다.

```bash
mv kube-scheduler.kubeconfig /var/lib/kubernetes/
mv kube-scheduler.yaml /etc/kubernetes/config/
mv kube-scheduler.service /etc/systemd/system/
```

<br>

## 서비스 시작

systemd 설정을 리로드하고 서비스를 시작한다.

```bash
systemctl daemon-reload
systemctl enable kube-apiserver kube-controller-manager kube-scheduler
systemctl start kube-apiserver kube-controller-manager kube-scheduler

# enable 실행 시 출력
Created symlink /etc/systemd/system/multi-user.target.wants/kube-apiserver.service → /etc/systemd/system/kube-apiserver.service.
Created symlink /etc/systemd/system/multi-user.target.wants/kube-controller-manager.service → /etc/systemd/system/kube-controller-manager.service.
Created symlink /etc/systemd/system/multi-user.target.wants/kube-scheduler.service → /etc/systemd/system/kube-scheduler.service.
```

<br>

# 검증

## 포트 리스닝 확인

각 컴포넌트가 지정된 포트에서 리스닝하는지 확인한다.

```bash
ss -tlp | grep kube
LISTEN 0  4096  *:6443   *:*  users:(("kube-apiserver",pid=3016,fd=3))                
LISTEN 0  4096  *:10259  *:*  users:(("kube-scheduler",pid=3018,fd=3))                
LISTEN 0  4096  *:10257  *:*  users:(("kube-controller",pid=3017,fd=3))       
```

| 포트 | 컴포넌트 | 용도 |
| --- | --- | --- |
| **6443** | kube-apiserver | HTTPS API 엔드포인트. kubectl, kubelet 등이 연결 |
| **10257** | kube-controller-manager | 헬스체크 및 메트릭 엔드포인트 |
| **10259** | kube-scheduler | 헬스체크 및 메트릭 엔드포인트 |

<br>

## 서비스 상태 확인

각 컴포넌트의 systemd 서비스 상태를 확인한다.

```bash
systemctl is-active kube-apiserver kube-controller-manager kube-scheduler
active
active
active
```


상세 상태를 확인한다.

```bash
systemctl status kube-apiserver --no-pager
● kube-apiserver.service - Kubernetes API Server
     Loaded: loaded (/etc/systemd/system/kube-apiserver.service; enabled; preset: enabled)
     Active: active (running) since Fri 2026-01-09 20:23:48 KST; 1min 36s ago
       Docs: https://github.com/kubernetes/kubernetes
   Main PID: 3016 (kube-apiserver)
      Tasks: 8 (limit: 2096)
     Memory: 206.2M
        CPU: 2.860s
     CGroup: /system.slice/kube-apiserver.service
             └─3016 /usr/local/bin/kube-apiserver --allow-privileged=true ...

Jan 09 20:23:51 server kube-apiserver[3016]: I0109 20:23:51.485317 allocated clusterIPs service="default/kubernetes" ...
```

kube-scheduler와 kube-controller-manager도 동일한 방식으로 확인한다.

```bash
systemctl status kube-scheduler kube-controller-manager --no-pager
● kube-scheduler.service - Kubernetes Scheduler
     Loaded: loaded (/etc/systemd/system/kube-scheduler.service; enabled; preset: enabled)
     Active: active (running) since Fri 2026-01-09 20:23:48 KST; 2min 49s ago
...
             └─3018 /usr/local/bin/kube-scheduler --config=/etc/kubernetes/config/kube-scheduler.yaml --v=2

Jan 09 20:23:54 server kube-scheduler[3018]: successfully acquired lease kube-system/kube-scheduler
...
● kube-controller-manager.service - Kubernetes Controller Manager
     Loaded: loaded (/etc/systemd/system/kube-controller-manager.service; enabled; preset: enabled)
     Active: active (running) since Fri 2026-01-09 20:23:48 KST; 2min 49s ago
...
             └─3017 /usr/local/bin/kube-controller-manager --bind-address=0.0.0.0 --cluster-cidr=10.200.0.0/16 ...
```

로그에서 `successfully acquired lease`를 확인할 수 있다. 이는 리더 선출이 완료되었음을 의미한다.

<br>

## 클러스터 정보 확인

API Server가 정상 동작하는지 kubectl로 확인한다. admin kubeconfig를 사용한다.

[5. Generating Kubernetes Configuration Files for Authentication]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-05-2 %}) 단계에서 생성한 admin kubeconfig에는 `system:masters` 그룹에 속한 인증서가 포함되어 있다. 이 그룹은 클러스터 슈퍼유저 권한을 가지므로 모든 작업이 허용된다.

```bash
kubectl cluster-info --kubeconfig admin.kubeconfig

Kubernetes control plane is running at https://127.0.0.1:6443

To further debug and diagnose cluster problems, use 'kubectl cluster-info dump'.
```

<br>

## 리소스 확인

현재 클러스터에 노드와 Pod가 없는지 확인한다. Worker 노드를 아직 구성하지 않았으므로 비어 있어야 정상이다.

```bash
kubectl get node --kubeconfig admin.kubeconfig

No resources found
```

```bash
kubectl get pod -A --kubeconfig admin.kubeconfig

No resources found
```

하지만 kubernetes Service는 자동으로 생성된다. API Server가 시작되면 자동으로 `default` namespace에 `kubernetes` Service를 생성한다.

```bash
kubectl get service,endpoints --kubeconfig admin.kubeconfig
```

```
NAME                 TYPE        CLUSTER-IP   EXTERNAL-IP   PORT(S)   AGE
service/kubernetes   ClusterIP   10.32.0.1    <none>        443/TCP   7m30s

NAME                   ENDPOINTS        AGE
endpoints/kubernetes   10.0.2.15:6443   7m30s
```

| 리소스 | 설명 |
| --- | --- |
| `service/kubernetes` | 클러스터 내부에서 API Server에 접근하기 위한 Service. ClusterIP는 `10.32.0.1`로, `--service-cluster-ip-range`의 첫 번째 IP가 자동 할당됨 |
| `endpoints/kubernetes` | Service의 실제 백엔드 주소. `10.0.2.15:6443`은 server 노드의 IP와 API Server 포트 |

<br>

# RBAC 설정

kube-apiserver가 kubelet API에 접근할 수 있도록 RBAC을 설정한다.

## kubelet의 인가 필요성

Kubernetes 클러스터에서 인가(Authorization)는 대부분 API Server가 담당한다. 하지만 예외가 있다: **API Server가 kubelet에 직접 요청할 때**다.

API Server는 다음과 같은 상황에서 kubelet API에 직접 요청을 보낸다:

- `kubectl logs`: 컨테이너 로그 조회
- `kubectl exec`: 컨테이너 내 명령 실행  
- `kubectl top`: 노드/Pod 메트릭 조회
- Metrics Server: 리소스 사용량 수집

kubelet은 자체적인 HTTPS 서버를 실행하며, API Server의 요청을 받아 처리한다. 이 때 kubelet은 요청자가 적절한 권한을 가지고 있는지 확인해야 한다. 다음과 같은 선택지가 있다:

1. **AlwaysAllow**: 모든 요청 허용 → 보안 위험
2. **자체 구현**: kubelet이 독자적 인가 로직 → 복잡성, 이원화
3. **Webhook**: API Server에게 인가 결정 위임 → **실습에서 사용**

Webhook 모드의 장점:
- 중앙 집중식: 모든 인가 정책이 API Server의 RBAC에 집중
- 일관성: 클러스터 전체가 동일한 인가 방식 사용
- 동적 변경: RBAC 규칙만 수정하면 즉시 적용

<br>

## Webhook 인가 모드와 RBAC의 필요성

다음 단계([9. Bootstrapping the Kubernetes Worker Nodes]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-09-1 %}))에서 kubelet의 `authorization.mode`를 `Webhook`으로 설정할 예정이다. 

> **참고**: [원본 가이드](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/08-bootstrapping-kubernetes-controllers.md#rbac-for-kubelet-authorization)의 표현
> 
> 실습 원본 가이드에 에서 "This tutorial sets the Kubelet `--authorization-mode` flag to `Webhook`"이라고 나오는데, 현재 단계는 Control Plane(kube-apiserver) 구성이고 kubelet 설정이 아니다. 여기서 미리 RBAC을 설정하는 이유는, 다음 단계에서 kubelet을 Webhook 모드로 구성할 때 필요하기 때문이다. kubelet 설정 전에 권한을 미리 준비해두는 것이다.

Webhook 모드에서 kubelet은 [SubjectAccessReview API](https://kubernetes.io/docs/reference/access-authn-authz/authorization/#checking-api-access)를 사용하여 API Server에 인가 결정을 위임한다.

<br>

### 역설적인 동작 방식

처음 들으면 이상하게 들릴 수 있다: **"API Server가 kubelet에 요청을 보내는데, kubelet이 다시 API Server에게 권한을 확인한다고?"** 맞다. 이것이 Webhook 모드의 핵심 동작이다.

### 구체적인 동작 흐름

`kubectl logs` 명령을 예로 들어 전체 흐름을 살펴보자:

1. **사용자 → API Server**: `kubectl logs pod-1 --kubeconfig admin.kubeconfig`
   - kubectl이 API Server(6443)에 로그 조회 요청

2. **API Server → kubelet 요청**: kube-apiserver가 kubelet API에 요청
   - API Server가 Pod가 실행 중인 노드의 kubelet(10250)에 연결
   - 클라이언트 인증서(CN=`kubernetes`)를 제시하며 `/logs` 엔드포인트 호출

3. **kubelet → API Server 인가 확인** (SubjectAccessReview 요청):
   ```
   kubelet: "어? CN=kubernetes라는 사용자가 내 /logs에 접근하려고 하네?"
   kubelet: "내가 이 사용자에게 권한이 있는지 어떻게 알지?"
   kubelet → API Server: SubjectAccessReview 요청
       "kubernetes라는 사용자가 nodes/log 리소스에 접근할 수 있나요?"
   ```

4. **API Server RBAC 평가**:
   ```
   API Server: "ClusterRole system:kube-apiserver-to-kubelet을 확인해보니..."
   API Server: "ClusterRoleBinding system:kube-apiserver가 사용자 kubernetes와 연결되어 있고..."
   API Server: "nodes/log 리소스에 대한 권한이 있네!"
   API Server → kubelet: {"allowed": true}
   ```

5. **kubelet 처리**: 인가 결과에 따라 요청 처리
   - kubelet: "API Server가 허가했으니 로그를 반환하자"
   - kubelet → API Server → kubectl: 로그 데이터 전송

### 왜 이렇게 복잡하게?

Webhook 모드의 장점:

- **중앙 집중식 권한 관리**: 모든 인가 정책이 API Server의 RBAC에 집중됨
- **동적 정책 변경**: RBAC 규칙만 변경하면 즉시 적용 (kubelet 재시작 불필요)
- **일관된 보안 모델**: 클러스터 전체가 동일한 인가 방식 사용
- **kubelet 단순화**: kubelet이 복잡한 권한 로직을 구현할 필요 없음

만약 `authorization.mode: AlwaysAllow`로 설정하면 kubelet은 모든 요청을 무조건 허용하여 보안 위험이 발생한다.

### RBAC 설정의 필요성

따라서 kubelet을 구성하기 전에 미리 RBAC 권한을 설정해둔다. 이 설정이 없으면 위의 4번 단계에서 API Server가 `{"allowed": false}`를 반환하고, `kubectl logs`, `kubectl exec`, `kubectl top` 등의 명령이 모두 실패한다.

<br>

## RBAC 설정 파일

kube-apiserver가 kubelet API에 접근하기 위한 RBAC 설정 파일이다.

```yaml
# configs/kube-apiserver-to-kubelet.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  annotations:
    rbac.authorization.kubernetes.io/autoupdate: "true"
  labels:
    kubernetes.io/bootstrapping: rbac-defaults
  name: system:kube-apiserver-to-kubelet
rules:
  - apiGroups:
      - ""
    resources:
      - nodes/proxy
      - nodes/stats
      - nodes/log
      - nodes/spec
      - nodes/metrics
    verbs:
      - "*"
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: system:kube-apiserver
  namespace: ""
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: system:kube-apiserver-to-kubelet
subjects:
  - apiGroup: rbac.authorization.k8s.io
    kind: User
    name: kubernetes
```

### ClusterRole 분석

ClusterRole의 주요 필드를 살펴보자.

- `name: system:kube-apiserver-to-kubelet`: 역할 이름
- `apiGroups: [""]`: Core API 그룹(v1). Node 관련 리소스는 Core 그룹에 속함
- `resources`: 접근 가능한 Node 하위 리소스
- `verbs: ["*"]`: 모든 동작 허용

접근 가능한 리소스 목록은 아래와 같다.

- `nodes/proxy`: API Server → kubelet 프록시 통신
- `nodes/stats`: 노드/Pod 리소스 통계
- `nodes/log`: 컨테이너 로그 조회
- `nodes/spec`: 노드 스펙 정보
- `nodes/metrics`: Metrics Server / `kubectl top`

### ClusterRoleBinding 분석

ClusterRoleBinding은 ClusterRole을 특정 사용자에게 연결한다.

- `subjects.name: kubernetes`: 이 권한을 부여받을 사용자
- `roleRef.name: system:kube-apiserver-to-kubelet`: 부여할 ClusterRole

`subjects.name`이 `kubernetes`인 이유는 kube-apiserver의 클라이언트 인증서 CN(Common Name)이 `kubernetes`이기 때문이다. 인증서의 CN이 Kubernetes에서 사용자 이름으로 매핑된다.

```bash
# kube-api-server.crt 인증서 확인
openssl x509 -in kube-api-server.crt -text -noout | grep Subject:
        Subject: CN = kubernetes, C = US, ST = Washington, L = Seattle
```

<br>

## 설정 적용

RBAC 설정 파일을 적용한다.

```bash
kubectl apply -f kube-apiserver-to-kubelet.yaml --kubeconfig admin.kubeconfig

clusterrole.rbac.authorization.k8s.io/system:kube-apiserver-to-kubelet created
clusterrolebinding.rbac.authorization.k8s.io/system:kube-apiserver created
```

<br>

## 설정 확인

생성된 ClusterRole과 ClusterRoleBinding을 확인한다.

```bash
kubectl get clusterroles system:kube-apiserver-to-kubelet --kubeconfig admin.kubeconfig

NAME                               CREATED AT
system:kube-apiserver-to-kubelet   2026-01-09T11:38:34Z
```

```bash
kubectl get clusterrolebindings system:kube-apiserver --kubeconfig admin.kubeconfig

NAME                    ROLE                                           AGE
system:kube-apiserver   ClusterRole/system:kube-apiserver-to-kubelet   45s
```

<br>

## 기본 ClusterRole 확인

Kubernetes는 부트스트랩 시 다양한 기본 ClusterRole을 자동 생성한다. 일부를 확인해 보자.

```bash
kubectl get clusterroles --kubeconfig admin.kubeconfig | head -20

NAME                                                                   CREATED AT
admin                                                                  2026-01-09T11:23:51Z
cluster-admin                                                          2026-01-09T11:23:51Z
edit                                                                   2026-01-09T11:23:51Z
system:aggregate-to-admin                                              2026-01-09T11:23:51Z
system:aggregate-to-edit                                               2026-01-09T11:23:51Z
system:aggregate-to-view                                               2026-01-09T11:23:51Z
system:kube-controller-manager                                         2026-01-09T11:23:51Z
system:kube-scheduler                                                  2026-01-09T11:23:51Z
system:node                                                            2026-01-09T11:23:51Z
...
```

| ClusterRole | 설명 |
| --- | --- |
| `cluster-admin` | 모든 리소스에 대한 전체 권한 |
| `admin` | Namespace 내 대부분의 리소스 관리 권한 |
| `edit` | 읽기/쓰기 권한 (RBAC 수정 제외) |
| `view` | 읽기 전용 권한 |
| `system:kube-scheduler` | kube-scheduler 전용 권한 |
| `system:kube-controller-manager` | kube-controller-manager 전용 권한 |
| `system:node` | kubelet 전용 권한 |

이러한 역할들은 `kubernetes.io/bootstrapping: rbac-defaults` 레이블을 가지며, `rbac.authorization.kubernetes.io/autoupdate: "true"` 어노테이션이 설정되어 있어 Kubernetes 업그레이드 시 자동으로 업데이트된다.

<br>

# API Server 검증

HTTPS 요청으로 API Server가 정상 동작하는지 확인한다. `/version` 엔드포인트는 인증 없이 접근 가능하며, Kubernetes 버전 정보를 반환한다.


```bash
curl -s -k --cacert /var/lib/kubernetes/ca.crt \
  https://server.kubernetes.local:6443/version | jq
```

```json
{
  "major": "1",
  "minor": "32",
  "gitVersion": "v1.32.3",
  "gitCommit": "32cc146f75aad04beaaa245a7157eb35063a9f99",
  "gitTreeState": "clean",
  "buildDate": "2025-03-11T19:52:21Z",
  "goVersion": "go1.23.6",
  "compiler": "gc",
  "platform": "linux/arm64"
}
```


<br>

# server 가상머신 종료

작업이 완료되었으면 server 가상머신을 종료한다.

```bash
exit
```

<br>

# 결과

이 단계를 완료하면 다음과 같은 결과를 얻을 수 있다:

1. **Control Plane 바이너리 설치**: kube-apiserver, kube-controller-manager, kube-scheduler, kubectl을 `/usr/local/bin/`에 설치
2. **설정 파일 배치**: 인증서, kubeconfig를 `/var/lib/kubernetes/`에, 설정 파일을 `/etc/kubernetes/config/`에 배치
3. **systemd 서비스 시작**: 모든 Control Plane 컴포넌트가 정상 실행 중
4. **포트 리스닝 확인**: 
   - API Server: 6443
   - Controller Manager: 10257
   - Scheduler: 10259
5. **RBAC 설정 완료**: kube-apiserver가 kubelet API에 접근할 수 있는 권한 부여
6. **kubernetes Service 자동 생성**: ClusterIP `10.32.0.1`

<br>

이번 실습을 통해 Kubernetes Control Plane을 직접 구성해 보았다. API Server, Scheduler, Controller Manager가 각각의 역할을 수행하며, systemd로 관리되어 자동 재시작 및 부팅 시 자동 시작이 가능하다. 아직 Worker 노드가 없으므로 Pod를 실행할 수는 없지만, 클러스터의 핵심 컴포넌트들은 정상적으로 동작하고 있다.

<br>

다음 글에서는 Worker 노드(node-0, node-1)에 kubelet, kube-proxy, containerd를 구성하여 실제로 Pod를 실행할 수 있는 환경을 만든다.

