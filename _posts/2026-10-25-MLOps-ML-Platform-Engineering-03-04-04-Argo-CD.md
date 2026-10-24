---
title: "[Argo CD] 머신러닝 플랫폼 엔지니어링: K8s와 CI/CD - 3.4.4. Argo CD"
excerpt: "Argo CD를 Kustomize로 설치하고 Gitea의 Helm 차트를 동기화해, CI가 올린 이미지 태그가 클러스터 배포로 이어지는 과정을 확인해 보자."
categories:
  - mlops-foundation
  - k8s-operations
  - study
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Argo-CD
  - GitOps
  - Kustomize
  - Helm
  - envsubst
  - Machine-Learning-Platform-Engineering-Study
  - Machine-Learning-Platform-Engineering-Study-Week-1
use_math: false
last_modified_at: 2026-10-25
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Machine Learning Platform Engineering Study 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- Argo CD가 Gitea의 Helm 차트를 읽어 `online-ml-svc` 네임스페이스에 앱을 배포했다. CI의 차트 갱신 커밋과 Argo CD의 동기화 revision이 일치했다
- 설치 디렉터리는 Kustomize 구성이므로 `kubectl apply -k`로 적용했다. `-f`로 패치 파일까지 리소스로 보내자 설치가 일부만 진행됐다
- `repoURL`에 Mac LAN IP를 넣는 과정에서 변수 표기 안의 역슬래시 때문에 치환이 실패했다. 파일을 고치고 `envsubst` 출력의 IP를 확인한 뒤 적용했다

<br>

# GitOps와 Argo CD

책 3.4.2절에 대응하는 실습이다. 설치는 [책 저자 저장소](https://github.com/vmallya-123/kubeflow-argo)의 Argo CD v2.6.7 구성을 따른다. GitOps는 Git에 선언한 목표 상태를 실제 시스템에 반영하는 운영 방식이고, Argo CD는 Kubernetes 리소스의 목표 상태와 실제 상태를 비교해 동기화하는 도구다.

[3.4.3편]({% post_url 2026-10-25-MLOps-ML-Platform-Engineering-03-04-03-CI-Workflow %})의 CI는 이미지 태그를 Helm 차트에 커밋했다. Argo CD는 이 차트를 렌더링해 Kubernetes 매니페스트를 만들고, 실제 리소스와 차이가 있으면 동기화한다. CI 잡에 클러스터 접속 정보를 넣지 않아도 Git 변경이 배포로 이어지는 구조다.

```mermaid
flowchart LR
    G[Git의 Helm 차트<br/>목표 상태] --> R[Argo CD<br/>렌더링과 상태 비교]
    K[Kubernetes 리소스<br/>실제 상태] --> R
    R -->|동기화| K
```
<center><sup>출처: 『머신러닝 플랫폼 엔지니어링』 그림 3.14. AI를 이용해 재구성했다</sup></center>

동기화(sync)는 목표 매니페스트를 클러스터에 반영하는 작업이다. 자동 동기화는 Git 변경에 따른 차이를 자동으로 적용한다. `selfHeal`은 클러스터에서 직접 바뀐 상태도 Git의 목표 상태로 되돌리는 설정이고, `prune`은 Git에서 사라진 리소스를 동기화 중 삭제하는 설정이다. 이번에는 자동 동기화와 `selfHeal: true`를 켰고 `prune`은 기본값인 비활성 상태로 두었다([v2.6 자동 동기화 문서](https://argo-cd.readthedocs.io/en/release-2.6/user-guide/auto_sync/)).

`Synced`는 비교한 목표 상태와 실제 상태가 일치한다는 뜻이다. `Healthy`는 리소스 종류별 상태 검사 기준을 만족한다는 뜻이다. 둘을 함께 확인하되 앱의 모든 HTTP 동작을 검증했다는 뜻으로 넓히지는 않는다.

<br>

# Argo CD 워크로드 해부

설치 결과는 Deployment 6개와 StatefulSet 1개였다. Git 조회와 매니페스트 생성은 repo-server, 상태 비교와 배포는 application-controller, 웹 UI와 API는 server가 맡는다([v2.6 아키텍처](https://argo-cd.readthedocs.io/en/release-2.6/operator-manual/architecture/)).

| 컴포넌트 | 리소스 | 역할 | v2.6.7의 주요 포트 |
|---|---|---|---|
| `argocd-server` | Deployment | 웹 UI, API, 인증·권한 처리 | Service 80/443 → 파드 8080, metrics 8083 |
| `argocd-repo-server` | Deployment | Git 조회와 Helm·Kustomize 렌더링 | gRPC 8081, metrics 8084 |
| `argocd-application-controller` | StatefulSet | 목표·실제 상태 비교, 동기화와 상태 기록 | metrics 8082 |
| `argocd-redis` | Deployment | 매니페스트·상태 조회 결과 캐시 | 6379 |
| `argocd-dex-server` | Deployment | 외부 인증 제공자와 SSO 연결 | 5556/5557/5558 |
| `argocd-applicationset-controller` | Deployment | ApplicationSet으로 여러 Application 생성 | webhook 7000, metrics 8080 |
| `argocd-notifications-controller` | Deployment | 앱 이벤트 알림 | metrics 9001 |

포트는 [v2.6.7 설치 매니페스트](https://github.com/argoproj/argo-cd/blob/v2.6.7/manifests/install.yaml)의 Service와 컨테이너 설정을 기준으로 한다. server의 Service 포트 두 개는 같은 파드 포트 8080으로 연결된다.

application-controller는 파드 이름의 순번을 이용해 여러 인스턴스에 관리 클러스터를 나눠 맡길 수 있다. 이를 샤딩(sharding)이라고 한다. 이 버전의 [고가용성 구성](https://argo-cd.readthedocs.io/en/release-2.6/operator-manual/high_availability/)은 StatefulSet의 안정적인 이름과 replica 설정을 사용한다. 실습에서는 `argocd-application-controller-0` 한 개가 담당했다.

## 상태 비교와 설정 저장

Application은 소스 저장소·경로·리비전과 배포 대상을 선언하는 Kubernetes 사용자 정의 리소스다. controller는 이를 읽고 repo-server에 매니페스트 생성을 요청한다. repo-server가 차트를 렌더링하면 controller가 실제 Kubernetes 리소스와 비교하고 결과를 Application의 `status`에 기록한다.

v2.6의 `timeout.reconciliation` 기본값은 180초다. 실습의 `argocd-cm`에는 이 값을 따로 설정하지 않았다. 이 주기 외에 클러스터 이벤트나 수동 새로 고침도 상태 비교를 일으킬 수 있다.

| 저장 위치 | 내용 |
|---|---|
| Application·AppProject | 앱 소스·목표와 프로젝트 정책 |
| `argocd-cm` | 전역 설정과 이번 설치의 Kustomize·diff 설정 |
| `argocd-cmd-params-cm` | 컴포넌트 실행 옵션 |
| `argocd-rbac-cm` | 권한 정책 |
| `argocd-secret` | 비밀번호 해시·서명 키 등 |
| `argocd-initial-admin-secret` | 초기 admin 비밀번호 |
| repository 라벨의 Secret | 비공개 저장소 등에 필요한 접속 정보 |

이 실습은 admin 로그인과 공개 Gitea 저장소 조회를 사용했다. 실제 감지 지연 시간은 재지 않았다. Dex를 통한 외부 로그인, ApplicationSet 생성, 알림 전송도 시험하지 않았다.

## Kustomize로 설치하는 방식

Kustomize는 기본 Kubernetes 매니페스트에 패치와 공통 설정을 합쳐 최종 매니페스트를 만드는 도구다. kubectl에 내장되어 있으며 `kubectl kustomize`로 결과를 출력하고 `kubectl apply -k`로 빌드와 적용을 이어서 실행한다([Kubernetes 문서](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/)).

설치 저장소의 `argocd/kustomization.yaml`은 Argo CD v2.6.7의 커밋 `5bcd846fa16e4b19d8f477de7da50ec0aef320e5`를 참조한다. 여기에 `argocd` 네임스페이스와 설정 패치를 합친다. repo-server 패치는 init 컨테이너로 Kustomize v4.0.5 바이너리를 준비하고, ConfigMap은 그 경로와 Kubeflow 리소스의 일부 차이 무시 규칙을 등록한다.

전략적 병합 패치(strategic merge patch)는 Kubernetes 리소스 구조에 맞춰 일부 필드를 합치는 패치다. 예를 들어 컨테이너 목록에서는 `name`으로 대상을 찾아 `volumeMounts` 등을 덧붙인다. 패치 파일에는 완전한 Deployment를 만들기 위한 모든 필드가 들어 있지 않아도 된다.

| 명령 | 입력 해석 | 이번 디렉터리에서의 결과 |
|---|---|---|
| `kubectl apply -f 디렉터리/` | 파일 각각을 Kubernetes 리소스로 적용 | Kustomization과 불완전한 패치에서 오류 |
| `kubectl apply -k 디렉터리/` | kustomization의 리소스·패치를 합쳐 적용 | 원격 기본 리소스와 패치를 합쳐 설치 |

설치 시 `patchesStrategicMerge`와 `vars`의 deprecated 경고가 나왔다. [Kustomize v5.0.0 릴리스](https://github.com/kubernetes-sigs/kustomize/releases/tag/kustomize%2Fv5.0.0)는 대안으로 `patches`와 `replacements`를 안내한다. 경고 후 리소스 생성은 완료됐다. clone한 구성을 변경하는 `kustomize edit fix`는 실행하지 않았다.

v2.6.7은 책의 설치 구성을 재현하기 위한 버전이다. 2026년 10월 기준 최근 세 minor 버전만 패치를 제공하는 [Argo CD 릴리스 정책](https://argo-cd.readthedocs.io/en/stable/developer-guide/release-process-and-cadence/)의 지원 범위에서 벗어나 있다.

<br>

# 적용과 관찰

실습 경로 `~/ml-study`는 실습 저장소 경로를 줄인 표기다. 인프라 설정은 `chapters/ch03-infra/argocd`, CI 저장소는 `chapters/app-ci`에 있다.

## 설치와 웹 접속

```bash
# Argo CD 설치 구성을 받아 Kustomize로 적용
cd ~/ml-study/chapters/ch03-infra
mkdir -p argocd/apps
cd argocd
git clone https://github.com/vmallya-123/kubeflow-argo
kubectl apply -k kubeflow-argo/argocd/
kubectl get pod -n argocd -w
```

설치 후 일곱 파드가 모두 `1/1 Running`이었다. 웹 접속용 Service는 `argocd-nodeport.yaml`로 저장해 적용했다. kind의 호스트 포트 매핑은 [3.3.1편]({% post_url 2026-10-24-MLOps-ML-Platform-Engineering-03-03-01-Kind-Cluster-API-Access %})의 클러스터 설정에 들어 있다.

```yaml
# argocd-nodeport.yaml: Mac 30001에서 Argo CD HTTPS로 연결
apiVersion: v1
kind: Service
metadata:
  name: argocd-server-nodeport
  namespace: argocd
spec:
  type: NodePort
  selector:
    app.kubernetes.io/name: argocd-server
  ports:
    - name: https
      protocol: TCP
      port: 443
      targetPort: 8080
      nodePort: 30001
```

```bash
# 서비스 생성과 실제 연결 대상 확인
kubectl apply -f argocd-nodeport.yaml
kubectl get svc,ep -n argocd argocd-server-nodeport

# 실행 결과의 주소·포트
# Service: 10.96.23.99, 443:30001/TCP
# Endpoints: 10.244.0.15:8080
```

`https://localhost:30001`로 접속했다. 기본 자체 서명 인증서 때문에 브라우저에 인증서 경고가 표시된다. 초기 admin 비밀번호는 `argocd` 네임스페이스의 `argocd-initial-admin-secret`에서 확인한다.

## Application 등록

repo-server가 읽을 저장소를 `apps/hello-joker.yaml`에 선언했다. `repoURL`에는 실습 당시 Mac LAN IP를 넣었다. repo-server 파드의 `localhost`는 그 파드 자신을 가리키므로 Mac에서 쓰던 `localhost:30000`을 그대로 쓸 수 없다.

```yaml
# apps/hello-joker.yaml: envsubst로 MYPC를 치환하기 전 템플릿
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: hello-joker
  namespace: argocd
spec:
  destination:
    namespace: online-ml-svc
    server: https://kubernetes.default.svc
  project: default
  source:
    helm:
      valueFiles:
        - values.yaml
    path: hello-joker
    repoURL: http://${MYPC}:30000/mlops/gitea-ci-example
    targetRevision: HEAD
  syncPolicy:
    automated:
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

`path`는 Git 저장소 안의 차트 디렉터리이고, `targetRevision: HEAD`는 저장소의 기본 브랜치를 따른다. `destination.server`는 배포할 Kubernetes API 주소다. `CreateNamespace=true`로 대상 네임스페이스를 동기화 때 만들 수 있다.

`envsubst`는 표준 입력의 `$이름`·`${이름}`을 환경 변수 값으로 치환하는 GNU gettext 도구다. macOS의 `ipconfig getifaddr en0`으로 실습에 사용한 네트워크 인터페이스의 IP를 조회하고 `export`로 자식 프로세스에도 전달했다. 인터페이스 이름은 실제 연결에 맞춰야 한다.

```bash
# 파일을 적용하기 전에 변수 치환 결과를 확인
export MYPC=$(ipconfig getifaddr en0)
envsubst < apps/hello-joker.yaml | grep repoURL

# 실행 결과
# repoURL: http://192.168.0.78:30000/mlops/gitea-ci-example

# 치환한 매니페스트를 표준 입력으로 적용
envsubst < apps/hello-joker.yaml | kubectl apply -f -
kubectl get app -n argocd hello-joker

# 실행 결과
# NAME          SYNC STATUS   HEALTH STATUS
# hello-joker   Synced        Healthy
```

![Argo CD hello-joker 동기화 결과]({{site.url}}/assets/images/mlpe-ch03-argocd-synced.png){: .align-center}
<center><sup>직접 캡처. hello-joker Application의 상태가 Healthy와 Synced로 표시된다.</sup></center>

`online-ml-svc`에는 `hello-joker-84f7c45f84` ReplicaSet의 파드 세 개가 `1/1 Running`으로 올라왔다. Service는 `10.96.176.107`, `8083:32681/TCP`였다. 이 NodePort는 앞선 Helm 실습의 고정 포트와 별개로 이번 차트에서 생성된 값이다.

## CI에서 배포까지 이어지는 흐름

2026-10-24 23시 20분의 읽기 전용 확인에서 Argo CD의 revision은 CI가 올린 차트 커밋 `37ae87f`였다. Deployment도 CI 이미지 태그 `9fc8cad1`을 사용했다.

```bash
# 동기화한 Git 커밋과 실제 Deployment 이미지 확인
kubectl --context kind-ml-study -n argocd get app hello-joker \
  -o jsonpath='sync={.status.sync.status} health={.status.health.status} revision={.status.sync.revision}'
# sync=Synced health=Healthy revision=37ae87f75b2f…

kubectl --context kind-ml-study -n online-ml-svc get deploy hello-joker \
  -o jsonpath='{.spec.replicas} {.spec.template.spec.containers[0].image}'
# 3 <dockerhub-user>/hello-joker:9fc8cad1
```

| 단계 | 확인한 값 |
|---|---|
| 앱 코드·워크플로 push | `9fc8cad` |
| CI 이미지 빌드·push | 태그 `9fc8cad1` |
| CI의 values.yaml 갱신 | 커밋 `37ae87f` |
| Argo CD 동기화 | revision `37ae87f75b2f…`, Synced·Healthy |
| Deployment | replicas 3, 이미지 태그 `9fc8cad1` |

이 연결로 코드 변경에서 배포 설정까지 추적할 수 있다. Deployment의 파드 교체 동작은 [3.3.3편]({% post_url 2026-10-24-MLOps-ML-Platform-Engineering-03-03-03-Pod-ReplicaSet-Deployment %})에서 다룬다. 이번 기록은 최초 동기화와 이미지 일치를 확인했으며, 후속 변경의 롤링 업데이트 중 요청 성공률이나 selfHeal·prune 동작을 따로 시험하지 않았다.

<br>

# 트러블슈팅

## 사례 1: Kustomize 구성을 일반 리소스로 적용

### 증상: Kustomization 종류 조회와 Deployment 검증 실패

처음에는 `kubectl apply -f kubeflow-argo/argocd/`로 설치했다. 일부 리소스가 만들어진 뒤 두 종류의 오류가 나왔다.

```text
# 첫 설치 시 생성 결과와 핵심 오류
configmap/argocd-cm created
namespace/argocd created
no matches for kind "Kustomization" in version "kustomize.config.k8s.io/v1beta1"
Deployment.apps "argocd-repo-server" is invalid
spec.selector: Required value
spec.template.spec.containers[0].image: Required value
```

### 증거: 기본 리소스 대신 로컬 파일만 적용

`-f`는 로컬 `kustomization.yaml` 자체를 리소스로 전송했다. repo-server에 추가할 필드만 담은 `add-custom-kustomize.yaml`도 완전한 Deployment로 전송했다. 원격 Argo CD 기본 구성은 `kustomization.yaml`의 `resources`에 들어 있으므로 이 명령에서 불러오지 않았다.

ConfigMap은 파일에 네임스페이스가 없어 현재 컨텍스트의 `default`에 만들어졌다. 이후 `kubectl get cm argocd-cm -n default`와 `-n argocd`를 각각 실행했을 때 두 곳에 같은 이름의 ConfigMap이 있었다.

### 원인: 패치 입력과 완성된 매니페스트의 혼동

Kustomization은 이 설치에서 클라이언트가 읽는 빌드 설정이다. 서버에 Kustomization CRD를 설치해서 해결할 문제가 아니다. `argocd-repo-server` 패치는 기본 Deployment와 합쳐져야 selector와 이미지가 채워진다.

### 해결: -k로 적용 후 불필요한 ConfigMap 정리

`kubectl apply -k kubeflow-argo/argocd/`로 CRD, 권한, Service, 워크로드가 생성됐다. `argocd`의 정상 ConfigMap과 `default`에 남은 ConfigMap을 확인한 뒤, `default` 쪽만 삭제했다.

```bash
# 두 네임스페이스의 같은 이름을 구분해 확인한 후 남은 리소스 정리
kubectl get cm argocd-cm -n default
kubectl get cm argocd-cm -n argocd
kubectl delete cm argocd-cm -n default
# configmap "argocd-cm" deleted from default namespace
```

## 사례 2: repoURL의 변수 치환 실패

### 증상: 생성된 Application에 변수 표기 잔류

`envsubst`를 거쳐 적용했는데도 Application의 `repoURL`에 IP 대신 변수 표기가 남았다. `created`는 리소스를 API 서버에 저장했다는 결과여서, 저장소 조회 성공은 Application 상태로 별도 확인해야 했다.

### 증거: 파일 안 중괄호 앞의 역슬래시

당시 파일을 출력한 기록에는 다음 값이 있었다. 단순히 달러 앞에 역슬래시가 붙은 형태와 구별해야 한다.

```yaml
# 실패 당시 파일의 repoURL
repoURL: http://$\{MYPC\}:30000/mlops/gitea-ci-example
```

### 원인: envsubst가 인식하는 변수 문법의 손상

`envsubst`가 인식하는 형태는 `$MYPC` 또는 `${MYPC}`다. 실제 파일의 `$\{MYPC\}`는 이 문법에 맞지 않아 그대로 통과했다. 로컬에서 세 형태를 비교해도 차이가 드러난다.

```bash
# 변수 표기만 비교하는 로컬 재현
export MYPC=192.168.0.78
printf '%s\n' '${MYPC}' '\${MYPC}' '$\{MYPC\}' | envsubst

# 실행 결과
# 192.168.0.78
# \192.168.0.78
# $\{MYPC\}
```

따옴표 있는 heredoc인 `<<'EOF'`는 셸 치환을 억제해 `${MYPC}`를 파일에 보존한다. 이렇게 정상 변수 표기를 보존한 템플릿은 나중에 `envsubst`로 처리할 수 있다. 역슬래시가 들어간 정확한 편집 과정은 기록에 남아 있지 않다.

### 해결: 변수 표기 수정과 치환 결과 확인

파일의 역슬래시를 제거해 `${MYPC}`로 고친 뒤, `envsubst` 출력에 실제 IP가 들어가는지 확인하고 다시 적용했다. 당시에는 `sed`로 파일 전체의 역슬래시를 지웠다. `sed`는 텍스트를 찾아 바꾸는 도구이며, 이 파일에는 다른 역슬래시 용도가 없었다.

```bash
# 당시 파일의 역슬래시 제거와 치환 결과 확인
sed -i '' 's/[\]//g' apps/hello-joker.yaml
grep -n repoURL apps/hello-joker.yaml
envsubst < apps/hello-joker.yaml | grep repoURL
envsubst < apps/hello-joker.yaml | kubectl apply -f -
```

수정된 Application이 `Synced`·`Healthy`가 됐다. 일반적인 YAML에서는 다른 문자열의 이스케이프도 의미가 있을 수 있으므로 `repoURL`의 변수 표기를 직접 고치는 편이 수정 범위를 좁힌다.

## 재발 방지

Kustomize 입력은 `kubectl kustomize kubeflow-argo/argocd/`로 최종 매니페스트를 먼저 볼 수 있다. 환경 변수 템플릿도 `envsubst` 출력과 적용 후 `spec.source.repoURL`을 함께 확인한다.

Mac LAN IP를 쓰면 DHCP로 주소가 바뀔 때 Application도 갱신해야 한다. 클러스터 내부 Service 주소 `http://gitea-http.gitea.svc.cluster.local:3000/mlops/gitea-ci-example`는 Mac 주소 변경에 대한 의존성을 줄이는 대안이다. 이번 Argo CD 실습에서는 이 주소로 전환하지 않았다. 호출 주체별 주소 구분은 [3.4.2편]({% post_url 2026-10-24-MLOps-ML-Platform-Engineering-03-04-02-Gitea-Address-Troubleshooting %})에 있다.

<br>

# 정리

CI가 테스트·이미지·차트 변경을 만들고, Argo CD가 차트를 클러스터에 반영하는 흐름까지 연결했다. ML 플랫폼에서는 상시 실행되는 실험 추적 서비스나 서빙 구성 요소의 선언적 배포에 같은 구조를 적용할 수 있다. 학습 실행의 재시도와 산출물 관리는 [MLOps와 GitOps]({% post_url 2026-04-27-Articles-GitOps-And-Training-Task %})에서 다룬 워크플로 관리와 함께 설계할 부분이다.

이번 구성의 핵심은 repo-server가 소스를 읽고 controller가 목표와 실제 상태를 맞춘다는 역할 분담이다.

<br>

# 참고 링크

- [책 저자의 설치 저장소](https://github.com/vmallya-123/kubeflow-argo)
- [Argo CD v2.6 아키텍처](https://argo-cd.readthedocs.io/en/release-2.6/operator-manual/architecture/)
- [Argo CD v2.6 자동 동기화](https://argo-cd.readthedocs.io/en/release-2.6/user-guide/auto_sync/)
- [Kubernetes의 Kustomize 사용법](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/)
- [GNU gettext envsubst](https://www.gnu.org/software/gettext/manual/html_node/envsubst-Invocation.html)

<br>
