---
title: "[LLM] LLM 서빙과 최적화: vLLM on Trainium 워크샵 - 8.5.2. 데이터소스 프로비저닝과 vLLM 대시보드"
excerpt: "Grafana를 서브패스로 노출하고 Prometheus 데이터소스를 프로비저닝한 뒤, ConfigMap으로 넣은 vLLM 대시보드가 언제 목록에 뜨는지 확인해 보자."
categories:
  - Kubernetes
toc: true
use_math: false
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - EKS
  - Grafana
  - Prometheus
  - Helm
  - Ingress
  - ConfigMap
  - vLLM
  - Observability
  - Hands-On-LLM-Serving-and-Optimization-Study
  - Hands-On-LLM-Serving-and-Optimization-Study-Week-6
last_modified_at: 2026-09-12
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Hands-On LLM Serving and Optimization Study (LLMSO) 6주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- Grafana는 Prometheus와 **별개 릴리스**다. `grafana/grafana` 차트 10.5.15(앱 12.3.1)를 따로 설치한다. 오퍼레이터도 CRD도 없는 구성이라 데이터소스와 대시보드를 리소스로 선언할 수 없고, 전부 values의 프로비저닝 파일과 파드 안 파일시스템으로 들어간다
- values의 `datasources`·`dashboardProviders`·`dashboards` 셋은 이름이 비슷하지만 산출물이 다르다. 앞의 둘은 `/etc/grafana/provisioning` 아래 설정 파일이 되고, 셋째는 init container `download-dashboards`가 grafana.com에서 받아 `/var/lib/grafana/dashboards/default`에 떨구는 **JSON 파일**이 된다
- 프로비저닝된 데이터소스는 Grafana UI에서 읽기 전용으로 잠긴다. URL 한 줄을 고치는 데도 values 수정 + `helm upgrade` 경로를 타야 한다
- Prometheus에 `--web.route-prefix=/p8s`를 붙인 순간 접근 수단과 무관하게 경로가 바뀐다. Grafana 파드 안에서 확인하면 `/api/v1/query`는 404, `/p8s/api/v1/query`는 200이다. 그래서 데이터소스 URL도 `/p8s`로 고쳐야 했다
- Grafana의 대응물은 `root_url`과 `serve_from_sub_path`다. 다만 Prometheus와 달리 **`root_url`에 서브패스를 적어도 자동으로 켜지지 않는다.** `serve_from_sub_path: true`를 따로 줘야 하고, 켜면 헬스 엔드포인트도 `/grafana/api/health`로 옮겨가므로 프로브 경로를 함께 고쳐야 한다
- 대시보드 ConfigMap을 만들어도 목록에 뜨지 않는다. provider가 `type: file`이라 Grafana는 쿠버네티스 API가 아니라 **디렉터리**를 읽고, 그 디렉터리에 파일을 놓는 마운트가 빠져 있었다. `grafana_dashboard` 라벨은 이 구성과 무관하다 — 라벨을 감시하는 사이드카가 설치돼 있지 않다
- `subPath`로 마운트한 ConfigMap은 갱신이 반영되지 않는다. 대시보드 JSON을 고쳐 ConfigMap을 갱신해도 파드 안 파일은 그대로다
- Lab 마지막 단계의 `kubectl annotate deployment`는 이 구성에서 효과가 없다. 어노테이션이 Deployment 오브젝트에 붙고 파드 템플릿으로 전파되지 않았다. 출력의 `revision`이 1에서 움직이지 않은 것이 그 증거다
- 패널 값이 대부분 0인 것은 메트릭 미노출이 아니다. 순간값 패널은 요청이 돌지 않으면 0이 맞는 값이고, 누적값도 요청 9건분이라 15분 창에서 평평하다

<br>

# Grafana 프로비저닝과 서브패스 해부

[8.5.1편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-05-01-Prometheus-Metrics-Scrape %})은 Prometheus를 올려 vLLM의 `/metrics`를 수집하고, Ingress `/p8s`로 웹 UI를 열었다. Lab 4의 나머지 절반은 그 수집값을 화면으로 보는 부분이다. Grafana를 올리고, Prometheus를 데이터소스로 붙이고, vLLM 메트릭 대시보드 한 장을 만든다.

이 글의 모든 출력에서 호스트명, IP, ELB DNS 이름, 관리자 비밀번호는 예시 값으로 치환했다.

## Lab 4 후반이 만드는 오브젝트

셋이다.

- `grafana/grafana` 차트가 설치하는 Grafana 릴리스 일습 — Deployment, ClusterIP Service, ConfigMap 두 개(`grafana`, `grafana-dashboards-default`), 관리자 자격 증명 Secret
- `/grafana` 경로를 Grafana Service로 보내는 `grafana-ingress` Ingress 한 장
- vLLM 대시보드 JSON을 담은 `vllm-dashboard` ConfigMap 한 개

알아 둘 점이 하나 있다. 이 구성은 **Prometheus와 Grafana를 한 차트로 묶어 올리지 않는다.** [8.5.1편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-05-01-Prometheus-Metrics-Scrape %})이 설치한 것은 `prometheus-community/prometheus` 29.28.1이고, Grafana는 `grafana/grafana` 10.5.15로 따로 설치한다. 두 차트 어느 쪽도 prometheus-operator를 포함하지 않으므로 `ServiceMonitor`나 `GrafanaDatasource` 같은 커스텀 리소스는 이 클러스터에 존재하지 않는다. 데이터소스도 대시보드도 **values에 적어 넣는 프로비저닝 파일**로만 들어간다.

설치 명령을 실행하면 첫 줄에 `WARNING: This chart is deprecated`가 찍힌다. 차트 자체가 deprecated 표시를 달고 있다. 무엇으로 옮겨야 하는지는 이번 실습에서 확인하지 않았다.

## values가 프로비저닝하는 세 가지

결론부터 정리하면, `grafana-values.yaml`에서 실제로 무언가를 프로비저닝하는 블록은 셋이고 산출물이 서로 다르다.

| 블록 | 차트가 만드는 것 | 파드 안 위치 | 채우는 주체 |
|---|---|---|---|
| `datasources` | ConfigMap `grafana`의 `datasources.yaml` 키 | `/etc/grafana/provisioning/datasources/datasources.yaml` | Grafana가 기동하며 읽는다 |
| `dashboardProviders` | 같은 ConfigMap의 `dashboardproviders.yaml` 키 | `/etc/grafana/provisioning/dashboards/dashboardproviders.yaml` | Grafana가 기동하며 읽는다 |
| `dashboards` | ConfigMap `grafana-dashboards-default` + 다운로드 스크립트 | `/var/lib/grafana/dashboards/default/*.json` | init container `download-dashboards`가 기동 전에 내려받는다 |

선택 기준도 여기서 갈린다. 데이터소스와 provider는 **설정**이라 values에 적으면 끝이고, 대시보드는 **파일**이라 누군가 그 디렉터리에 실제로 파일을 놓아야 한다. 뒤에서 막히는 것도 세 번째 줄이다. 이 구성에서 대시보드를 추가한다는 것은 "ConfigMap을 만든다"가 아니라 "그 디렉터리에 파일이 생기게 한다"는 뜻이다.

values 전문은 다음과 같다.

```yaml
# grafana-values.yaml
persistence:
  enabled: false        # PVC를 만들지 않는다. /var/lib/grafana는 emptyDir가 된다

adminPassword: "<admin-password>"   # Secret grafana의 admin-password 키로 들어간다

service:
  type: ClusterIP       # 외부 노출은 Ingress가 맡는다. LoadBalancer를 또 만들지 않는다

datasources:
  datasources.yaml:
    apiVersion: 1
    datasources:
    - name: Prometheus
      type: prometheus
      url: http://prometheus-server.monitoring.svc.cluster.local
      access: proxy     # 브라우저가 아니라 Grafana 서버가 대신 질의한다
      isDefault: true

dashboardProviders:
  dashboardproviders.yaml:
    apiVersion: 1
    providers:
    - name: 'default'
      orgId: 1
      folder: ''
      type: file        # 쿠버네티스 API가 아니라 파일시스템을 읽는 provider다
      disableDeletion: false
      editable: true
      options:
        path: /var/lib/grafana/dashboards/default

dashboards:
  default:
    kubernetes-cluster:
      gnetId: 7249      # grafana.com 대시보드 ID
      revision: 1
      datasource: Prometheus
    kubernetes-pods:
      gnetId: 6336
      revision: 1
      datasource: Prometheus

resources:
  requests:
    cpu: 250m
    memory: 512Mi
  limits:
    cpu: 500m
    memory: 1Gi
```

### datasources

`datasources.yaml`이라는 키 이름이 그대로 파일 이름이 된다. 차트는 이 맵을 ConfigMap `grafana`의 한 키로 넣고, 파드에서 `/etc/grafana/provisioning/datasources/datasources.yaml` 자리에 마운트한다. Grafana는 기동할 때 그 디렉터리를 읽어 데이터소스를 등록한다.

```yaml
datasources:
  datasources.yaml:
    apiVersion: 1
    datasources:
    - name: Prometheus
      type: prometheus
      url: http://prometheus-server.monitoring.svc.cluster.local
      access: proxy
      isDefault: true
```

`access: proxy`는 뒤에 나오는 404와 직접 연결된다. `proxy`는 브라우저가 Prometheus에 직접 붙는 것이 아니라 **Grafana 서버 프로세스가 대신 질의하는** 모드다. 그래서 이 `url`은 사용자의 브라우저가 아니라 Grafana 파드가 해석할 수 있는 주소여야 하고, 실제로 클러스터 내부 Service DNS가 적혀 있다. 문제가 생겼을 때 확인해야 하는 곳도 브라우저가 아니라 Grafana 파드 안이다.

`isDefault: true`는 이 데이터소스를 기본값으로 만든다. 대시보드 JSON이 데이터소스를 명시하지 않아도 이것이 쓰인다.

### dashboardProviders

provider는 "대시보드를 어디서 가져올지"를 정하는 설정이다. 여기서 고른 `type: file`은 **지정한 디렉터리의 JSON 파일을 읽는** provider다.

```yaml
dashboardProviders:
  dashboardproviders.yaml:
    apiVersion: 1
    providers:
    - name: 'default'
      orgId: 1
      folder: ''
      type: file
      disableDeletion: false
      editable: true
      options:
        path: /var/lib/grafana/dashboards/default
```

`options.path`가 `/var/lib/grafana/dashboards/default`다. Grafana는 이 경로를 파일시스템에서 읽을 뿐 쿠버네티스 API를 보지 않는다. `folder: ''`라 대시보드는 폴더 없이 일반 목록에 놓이고, `editable: true`라 UI에서 수정은 가능하다.

### dashboards

`dashboards` 블록은 앞의 둘과 성격이 다르다. 설정이 아니라 **파일을 내려받는 작업 지시**다.

```yaml
dashboards:
  default:
    kubernetes-cluster:
      gnetId: 7249
      revision: 1
      datasource: Prometheus
    kubernetes-pods:
      gnetId: 6336
      revision: 1
      datasource: Prometheus
```

`default`는 위 provider 이름과 같고, `gnetId`는 grafana.com에 공개된 대시보드 번호다. 차트는 이 정보로 다운로드 스크립트를 만들어 ConfigMap에 넣고, init container `download-dashboards`가 그 스크립트를 실행해 `/var/lib/grafana/dashboards/default`에 JSON 두 개를 떨군다. 뒤에서 Dashboards 목록에 `Kubernetes Cluster`와 `Kubernetes Pods (Prometheus)` 두 개가 먼저 보이는 것이 이 결과다.

이 values에는 `sidecar` 키가 없다. 차트에는 대시보드 ConfigMap을 라벨로 감시해 파일로 떨궈 주는 사이드카 기능이 있지만 기본값이 꺼져 있고, 여기서 켜지 않았다. 이 사실이 뒤에서 대시보드가 보이지 않는 [원인](#원인)과 직결된다.

## 프로비저닝된 데이터소스의 읽기 전용 잠금

프로비저닝 파일로 등록된 데이터소스는 Grafana UI에서 수정할 수 없다. 설정 화면이 열리기는 하지만 읽기 전용으로 잠긴다. 파일이 원본이고 UI가 사본이라, UI에서 고치면 다음 기동 때 파일 값으로 되돌아가기 때문이다.

그래서 URL 한 글자를 바꾸는 데도 경로가 정해져 있다. `grafana-values.yaml`을 고치고 `helm upgrade`를 돌려야 한다. 다음 절의 수정이 그 과정을 그대로 밟는다.

## route-prefix가 바꾸는 접근 경로

결론부터 말하면, [8.5.1편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-05-01-Prometheus-Metrics-Scrape %})에서 Prometheus에 `--web.route-prefix=/p8s`를 붙인 순간 Ingress 경유만이 아니라 **Grafana가 쓰는 클러스터 내부 경로까지 함께 바뀌었다.**

| 접근 경로 | 이전 | 지금 |
|---|---|---|
| Ingress 경유 | `http://$INGRESS/` | `http://$INGRESS/p8s` |
| ClusterIP 경유 (Grafana) | `http://prometheus-server.monitoring.svc.cluster.local/` | `http://prometheus-server.monitoring.svc.cluster.local/p8s` |
| port-forward | `localhost:9090/` | `localhost:9090/p8s` |

`--web.route-prefix`가 리버스 프록시 쪽 설정이 아니기 때문이다. Prometheus 소스는 이 플래그를 "web endpoint **내부 경로**의 프리픽스"로 적고 있고, 실제로 라우터를 프리픽스로 감싼 뒤 `/api/v1`을 `/p8s/api/v1` 자리에 등록한다. 등록되지 않은 `/api/v1/query`는 어느 경로로 들어오든 404다. 범위도 API에 그치지 않는다. Prometheus 자신의 `/metrics`와 `/-/ready`까지 `/p8s` 아래로 간다.

이름이 비슷한 `--web.external-url`은 역할이 다르다.

| 플래그 | 하는 일 | 프로세스가 받는 경로가 바뀌는가 |
|---|---|---|
| `--web.route-prefix` | 내부 라우팅 테이블의 프리픽스를 정한다 | 바뀐다 |
| `--web.external-url` | 밖에서 보이는 URL을 알려 준다. 리다이렉트나 알림 링크 같은 내보내는 절대 링크를 만드는 데 쓴다 | 직접은 바뀌지 않는다 |

한 가지가 겹친다. `--web.route-prefix`를 비워 두면 Prometheus가 `--web.external-url`의 path로 그 값을 채운다. external-url만 줬는데 내부 경로가 바뀌었다면 이 기본값 때문이다.

Grafana 입장에서 이 변화가 문제인 이유는 단순하다. Grafana는 데이터소스 URL 뒤에 `/api/v1/query`를 붙여 질의한다. `url`이 `http://prometheus-server.monitoring.svc.cluster.local`인 채로 두면 `http://prometheus-server.monitoring.svc.cluster.local/api/v1/query`를 호출하게 되고, Prometheus는 그 경로를 등록하지 않았으므로 404를 돌려준다. 대시보드는 전부 No data가 된다.

## serve_from_sub_path와 root_url

Grafana 쪽 대응물은 `root_url`과 `serve_from_sub_path`다. 역할은 각각 `--web.external-url`과 `--web.route-prefix`에 대응한다. 다른 점이 하나 있는데, **Grafana는 `root_url`에 서브패스를 적어도 자동으로 켜 주지 않는다.** `serve_from_sub_path: true`를 따로 줘야 실제로 `/grafana` 아래에서 응답한다.

서브패스 설정은 별도 values 파일로 분리해 두 번째 `-f`로 얹었다.

```yaml
# grafana-subpath-values.yaml
grafana.ini:
  server:
    domain: $INGRESS                      # 셸이 전개해 실제 ELB 호스트명이 박힌다
    root_url: "http://%(domain)s/grafana/" # %(domain)s는 Grafana 내부 치환 문법이라 그대로 남는다
    serve_from_sub_path: true             # 이걸 켜야 /grafana 아래에서 응답한다

readinessProbe:
  httpGet:
    path: /grafana/api/health             # 서브패스가 켜지면 헬스도 이 경로로 옮겨간다
    port: grafana
  initialDelaySeconds: 10
  periodSeconds: 10
  failureThreshold: 6

livenessProbe:
  httpGet:
    path: /grafana/api/health
    port: grafana
  initialDelaySeconds: 60
  timeoutSeconds: 30
  failureThreshold: 10
```

`domain`과 `root_url`을 나눠 쓴 것이 눈에 띈다. heredoc이 따옴표 없이 열려 있어 `$INGRESS`는 셸이 먼저 전개하지만, `%(domain)s`는 셸 문법이 아니라 Grafana 설정 파일의 치환 문법이라 파일에 그대로 남는다. Grafana가 기동할 때 `domain` 값으로 채운다.

프로브 두 개를 함께 고친 것은 선택이 아니라 필수다. `serve_from_sub_path`를 켜면 Grafana의 모든 경로가 `/grafana` 아래로 옮겨가므로 차트 기본값인 `/api/health`는 더 이상 응답하지 않는다. Prometheus 쪽에서는 차트가 프리픽스 값을 읽어 프로브 경로를 스스로 만들어 줬지만, Grafana 차트는 그 자동 연동이 없어 values에 직접 적어야 한다.

여기까지의 작업을 하나로 묶으면 이유는 하나다. **ELB 하나에 붙은 ingress-nginx 뒤에 vLLM, Prometheus, Grafana 셋을 경로로 갈라 넣으려는 것이다.** 루트는 이미 [8.4편의 Ingress 규칙]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-04-Ingress-Nginx-Routing %}#ingress-규칙-해석)이 `path: /`로 가져갔으므로 나머지 둘은 서브패스를 받을 수밖에 없다. Ingress에 경로를 적는 것이 절반이고, 애플리케이션이 자기가 서브패스 아래에 있다는 것을 아는 것이 나머지 절반이다.

<br>

# 적용과 관찰: Grafana 설치와 서브패스 노출

## Helm 설치와 init container

저장소를 등록하고 values 파일로 설치한다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ helm repo add grafana https://grafana.github.io/helm-charts
"grafana" has been added to your repositories

ubuntu@ip-10-0-1-100:~/workshop$ helm install grafana grafana/grafana \
>   --namespace monitoring \
>   --values grafana-values.yaml

# 실행 결과 (NOTES 생략). 차트가 deprecated 경고를 먼저 찍는다
WARNING: This chart is deprecated
NAME: grafana
LAST DEPLOYED: Fri Sep 11 16:38:42 2026
NAMESPACE: monitoring
STATUS: deployed
REVISION: 1
```

<details markdown="1">
<summary><b>설치 NOTES 전문</b></summary>

```text
1. Get your 'admin' user password by running:

   kubectl get secret --namespace monitoring grafana -o jsonpath="{.data.admin-password}" | base64 --decode ; echo

2. The Grafana server can be accessed via port 80 on the following DNS name from within your cluster:

   grafana.monitoring.svc.cluster.local

   Get the Grafana URL to visit by running these commands in the same shell:
     export POD_NAME=$(kubectl get pods --namespace monitoring -l "app.kubernetes.io/name=grafana,app.kubernetes.io/instance=grafana" -o jsonpath="{.items[0].metadata.name}")
     kubectl --namespace monitoring port-forward $POD_NAME 3000

3. Login with the password from step 1 and the username: admin
#################################################################################
######   WARNING: Persistence is disabled!!! You will lose your data when   #####
######            the Grafana pod is terminated.                            #####
#################################################################################
```

</details>

릴리스 목록에서 두 차트가 별개라는 점이 그대로 보인다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ helm list -A

# 실행 결과 (발췌). grafana와 prometheus가 서로 다른 릴리스다
NAME           NAMESPACE   REVISION  STATUS    CHART              APP VERSION
grafana        monitoring  1         deployed  grafana-10.5.15    12.3.1
prometheus     monitoring  3         deployed  prometheus-29.28.1 v3.14.0
```

설치 직후 Service는 만들어졌지만 엔드포인트가 비어 있다. 파드가 아직 init container를 돌고 있기 때문이다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ kubectl get svc,ep -n monitoring grafana

# 실행 결과. ClusterIP는 잡혔는데 ENDPOINTS 열이 비어 있다
NAME              TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)   AGE
service/grafana   ClusterIP   172.20.40.242   <none>        80/TCP    4s

NAME                ENDPOINTS   AGE
endpoints/grafana               4s

ubuntu@ip-10-0-1-100:~/workshop$ kubectl get pod -n monitoring -l app.kubernetes.io/instance=grafana

# 실행 결과
NAME                      READY   STATUS            RESTARTS   AGE
grafana-9876f6f4d-tscw9   0/1     PodInitializing   0          5s
```

파드 상세를 보면 values에 적은 것들이 파드 안 어디에 어떻게 놓였는지 드러난다.

```text
# kubectl describe pod -n monitoring -l app.kubernetes.io/instance=grafana 발췌
Init Containers:
  download-dashboards:
    Image:         docker.io/curlimages/curl:8.9.1
    Args:
      -c
      mkdir -p /var/lib/grafana/dashboards/default && /bin/sh -x /etc/grafana/download_dashboards.sh
    State:          Terminated
      Reason:       Completed
      Exit Code:    0
Containers:
  grafana:
    Image:          docker.io/grafana/grafana:12.3.1
    Ports:          3000/TCP (grafana), 9094/TCP (gossip-tcp), 9094/UDP (gossip-udp), 6060/TCP (profiling)
    Liveness:       http-get http://:grafana/api/health delay=60s timeout=30s period=10s successThreshold=1 failureThreshold=10
    Readiness:      http-get http://:grafana/api/health delay=0s timeout=1s period=10s successThreshold=1 failureThreshold=3
    Mounts:
      /etc/grafana/grafana.ini from config (rw,path="grafana.ini")
      /etc/grafana/provisioning/dashboards/dashboardproviders.yaml from config (rw,path="dashboardproviders.yaml")
      /etc/grafana/provisioning/datasources/datasources.yaml from config (rw,path="datasources.yaml")
      /var/lib/grafana from storage (rw)
Volumes:
  config:
    Type:      ConfigMap (a volume populated by a ConfigMap)
    Name:      grafana
  dashboards-default:
    Type:      ConfigMap (a volume populated by a ConfigMap)
    Name:      grafana-dashboards-default
  storage:
    Type:      EmptyDir (a temporary directory that shares a pod's lifetime)
  search:
    Type:      EmptyDir (a temporary directory that shares a pod's lifetime)
```

앞 절에서 본 values 세 블록이 여기에 그대로 대응한다. `datasources`와 `dashboardProviders`는 `config` 볼륨(ConfigMap `grafana`)에서 각각 한 파일로 마운트됐고, `dashboards`는 init container가 `storage` 볼륨 안에 파일로 떨궜다. `storage`가 emptyDir인 것은 `persistence.enabled: false`의 결과다. 파드가 교체되면 그 디렉터리는 비워지고 init container가 다시 받아 온다.

컨테이너가 init `download-dashboards` 하나와 `grafana` 하나뿐이라는 점은 뒤에서 다시 쓰인다. 대시보드 ConfigMap을 감시하는 사이드카 컨테이너가 없다.

마지막으로 이벤트에 readiness 실패가 두 번 찍혔다.

```text
Warning  Unhealthy  19s (x2 over 20s)  kubelet  spec.containers{grafana}: Readiness probe failed: Get "http://10.0.5.206:3000/api/health": dial tcp 10.0.5.206:3000: connect: connection refused
```

`delay=0s`라 컨테이너가 뜨자마자 프로브가 시작됐고, Grafana가 3000 포트를 열기 전이라 연결이 거부됐다. 재시도 두 번 만에 Ready가 됐으므로 정상 과도 상태다.

<details markdown="1">
<summary><b>kubectl describe pod 전문</b></summary>

```text
Name:             grafana-9876f6f4d-tscw9
Namespace:        monitoring
Priority:         0
Service Account:  grafana
Node:             ip-10-0-5-100.us-west-2.compute.internal/10.0.5.100
Start Time:       Fri, 11 Sep 2026 16:38:42 +0000
Labels:           app.kubernetes.io/instance=grafana
                  app.kubernetes.io/name=grafana
                  app.kubernetes.io/version=12.3.1
                  helm.sh/chart=grafana-10.5.15
                  pod-template-hash=9876f6f4d
Annotations:      checksum/config: 4cc30e3c65cd439698cd491fba22fdaa9e4c7b8ef42fdf5a794a0ab61e78b6cf
                  checksum/dashboards-json-config: 9d10d83db56ff68e4a5f69e95c832c92e53bf7d421f729093611ebb3b3f44a8f
                  checksum/sc-dashboard-provider-config: e70bf6a851099d385178a76de9757bb0bef8299da6d8443602590e44f05fdf24
                  checksum/secret: d6ed161ad3488f23c7a1948c307944897a4646c86e3256623472859be360c2c1
                  kubectl.kubernetes.io/default-container: grafana
Status:           Running
IP:               10.0.5.206
IPs:
  IP:           10.0.5.206
Controlled By:  ReplicaSet/grafana-9876f6f4d
Init Containers:
  download-dashboards:
    Container ID:    containerd://048fcbe054939dad833b17fa876460b19c7c75fd90e747516df2ea566ffa9b78
    Image:           docker.io/curlimages/curl:8.9.1
    Image ID:        docker.io/curlimages/curl@sha256:8addc281f0ea517409209f76832b6ddc2cabc3264feb1ebbec2a2521ffad24e4
    Port:            <none>
    Host Port:       <none>
    SeccompProfile:  RuntimeDefault
    Command:
      /bin/sh
    Args:
      -c
      mkdir -p /var/lib/grafana/dashboards/default && /bin/sh -x /etc/grafana/download_dashboards.sh
    State:          Terminated
      Reason:       Completed
      Exit Code:    0
      Started:      Fri, 11 Sep 2026 16:38:45 +0000
      Finished:     Fri, 11 Sep 2026 16:38:45 +0000
    Ready:          True
    Restart Count:  0
    Environment:    <none>
    Mounts:
      /etc/grafana/download_dashboards.sh from config (rw,path="download_dashboards.sh")
      /var/lib/grafana from storage (rw)
      /var/run/secrets/kubernetes.io/serviceaccount from kube-api-access-9ct9w (ro)
Containers:
  grafana:
    Container ID:    containerd://f37caf776259404a3d6acc476734adc65e7fb77b6e1bd6f9fb3de12d028f56c9
    Image:           docker.io/grafana/grafana:12.3.1
    Image ID:        docker.io/grafana/grafana@sha256:2175aaa91c96733d86d31cf270d5310b278654b03f5718c59de12a865380a31f
    Ports:           3000/TCP (grafana), 9094/TCP (gossip-tcp), 9094/UDP (gossip-udp), 6060/TCP (profiling)
    Host Ports:      0/TCP (grafana), 0/TCP (gossip-tcp), 0/UDP (gossip-udp), 0/TCP (profiling)
    SeccompProfile:  RuntimeDefault
    State:           Running
      Started:       Fri, 11 Sep 2026 16:38:52 +0000
    Ready:           True
    Restart Count:   0
    Limits:
      cpu:     500m
      memory:  1Gi
    Requests:
      cpu:      250m
      memory:   512Mi
    Liveness:   http-get http://:grafana/api/health delay=60s timeout=30s period=10s successThreshold=1 failureThreshold=10
    Readiness:  http-get http://:grafana/api/health delay=0s timeout=1s period=10s successThreshold=1 failureThreshold=3
    Environment:
      POD_IP:                          (v1:status.podIP)
      GF_SECURITY_ADMIN_USER:         <set to the key 'admin-user' in secret 'grafana'>      Optional: false
      GF_SECURITY_ADMIN_PASSWORD:     <set to the key 'admin-password' in secret 'grafana'>  Optional: false
      GF_PATHS_DATA:                  /var/lib/grafana/
      GF_PATHS_LOGS:                  /var/log/grafana
      GF_PATHS_PLUGINS:               /var/lib/grafana/plugins
      GF_PATHS_PROVISIONING:          /etc/grafana/provisioning
      GF_UNIFIED_STORAGE_INDEX_PATH:  /var/lib/grafana-search/bleve
      GOMEMLIMIT:                     1073741824 (limits.memory)
    Mounts:
      /etc/grafana/grafana.ini from config (rw,path="grafana.ini")
      /etc/grafana/provisioning/dashboards/dashboardproviders.yaml from config (rw,path="dashboardproviders.yaml")
      /etc/grafana/provisioning/datasources/datasources.yaml from config (rw,path="datasources.yaml")
      /var/lib/grafana from storage (rw)
      /var/lib/grafana-search from search (rw)
      /var/run/secrets/kubernetes.io/serviceaccount from kube-api-access-9ct9w (ro)
Conditions:
  Type                        Status
  PodReadyToStartContainers   True
  Initialized                 True
  Ready                       True
  ContainersReady             True
  PodScheduled                True
Volumes:
  config:
    Type:      ConfigMap (a volume populated by a ConfigMap)
    Name:      grafana
    Optional:  false
  dashboards-default:
    Type:      ConfigMap (a volume populated by a ConfigMap)
    Name:      grafana-dashboards-default
    Optional:  false
  storage:
    Type:       EmptyDir (a temporary directory that shares a pod's lifetime)
    Medium:
    SizeLimit:  <unset>
  search:
    Type:       EmptyDir (a temporary directory that shares a pod's lifetime)
    Medium:
    SizeLimit:  <unset>
  kube-api-access-9ct9w:
    Type:                    Projected (a volume that contains injected data from multiple sources)
    TokenExpirationSeconds:  3607
    ConfigMapName:           kube-root-ca.crt
    Optional:                false
    DownwardAPI:             true
QoS Class:                   Burstable
Node-Selectors:              <none>
Tolerations:                 node.kubernetes.io/not-ready:NoExecute op=Exists for 300s
                             node.kubernetes.io/unreachable:NoExecute op=Exists for 300s
Events:
  Type     Reason     Age                From               Message
  ----     ------     ----               ----               -------
  Normal   Scheduled  29s                default-scheduler  Successfully assigned monitoring/grafana-9876f6f4d-tscw9 to ip-10-0-5-100.us-west-2.compute.internal
  Normal   Pulling    29s                kubelet            spec.initContainers{download-dashboards}: Pulling image "docker.io/curlimages/curl:8.9.1"
  Normal   Pulled     27s                kubelet            spec.initContainers{download-dashboards}: Successfully pulled image "docker.io/curlimages/curl:8.9.1" in 1.614s (1.614s including waiting). Image size: 9384907 bytes.
  Normal   Created    27s                kubelet            spec.initContainers{download-dashboards}: Created container: download-dashboards
  Normal   Started    27s                kubelet            spec.initContainers{download-dashboards}: Started container download-dashboards
  Normal   Pulling    26s                kubelet            spec.containers{grafana}: Pulling image "docker.io/grafana/grafana:12.3.1"
  Normal   Pulled     20s                kubelet            spec.containers{grafana}: Successfully pulled image "docker.io/grafana/grafana:12.3.1" in 5.565s (5.565s including waiting). Image size: 210410945 bytes.
  Normal   Created    20s                kubelet            spec.containers{grafana}: Created container: grafana
  Normal   Started    20s                kubelet            spec.containers{grafana}: Started container grafana
  Warning  Unhealthy  19s (x2 over 20s)  kubelet            spec.containers{grafana}: Readiness probe failed: Get "http://10.0.5.206:3000/api/health": dial tcp 10.0.5.206:3000: connect: connection refused
```

</details>

## 데이터소스 URL 수정

`access: proxy`라 질의를 보내는 주체가 Grafana 파드다. 그러면 판정도 파드 안에서 하면 된다. Grafana 컨테이너에서 두 경로를 각각 때려 본다.

```shell
# 현재 설정된 경로 → 404
ubuntu@ip-10-0-1-100:~/workshop$ kubectl exec -n monitoring deploy/grafana -- \
>   curl -so /dev/null -w '%{http_code}\n' \
>   "http://prometheus-server.monitoring.svc.cluster.local/api/v1/query?query=up"
404

# /p8s 붙인 경로 → 200
ubuntu@ip-10-0-1-100:~/workshop$ kubectl exec -n monitoring deploy/grafana -- \
>   curl -so /dev/null -w '%{http_code}\n' \
>   "http://prometheus-server.monitoring.svc.cluster.local/p8s/api/v1/query?query=up"
200
```

Ingress를 거치지 않고 ClusterIP로 직접 갔는데도 404다. `--web.route-prefix`가 프로세스의 라우팅 테이블을 바꾼다는 것이 추론이 아니라 실측으로 확인된다.

고칠 곳은 한 줄이다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ cat grafana-values.yaml | grep url -A3 -B3

# 실행 결과. 수정 전
    datasources:
    - name: Prometheus
      type: prometheus
      url: http://prometheus-server.monitoring.svc.cluster.local
      access: proxy
      isDefault: true

ubuntu@ip-10-0-1-100:~/workshop$ grep -n 'url:' grafana-values.yaml

# 실행 결과. 수정 후
15:      url: http://prometheus-server.monitoring.svc.cluster.local/p8s
```

<details markdown="1">
<summary><b>수정 후 grafana-values.yaml 전문</b></summary>

```yaml
persistence:
  enabled: false

adminPassword: "<admin-password>"

service:
  type: ClusterIP

datasources:
  datasources.yaml:
    apiVersion: 1
    datasources:
    - name: Prometheus
      type: prometheus
      url: http://prometheus-server.monitoring.svc.cluster.local/p8s
      access: proxy
      isDefault: true

dashboardProviders:
  dashboardproviders.yaml:
    apiVersion: 1
    providers:
    - name: 'default'
      orgId: 1
      folder: ''
      type: file
      disableDeletion: false
      editable: true
      options:
        path: /var/lib/grafana/dashboards/default

dashboards:
  default:
    kubernetes-cluster:
      gnetId: 7249
      revision: 1
      datasource: Prometheus
    kubernetes-pods:
      gnetId: 6336
      revision: 1
      datasource: Prometheus

resources:
  requests:
    cpu: 250m
    memory: 512Mi
  limits:
    cpu: 500m
    memory: 1Gi
```

</details>

프로비저닝 파일이 ConfigMap에 들어 있으므로, 반영하려면 릴리스를 올려야 한다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ helm upgrade -i grafana grafana/grafana \
>   --namespace monitoring \
>   --values grafana-values.yaml

# 실행 결과 (NOTES 생략)
WARNING: This chart is deprecated
Release "grafana" has been upgraded. Happy Helming!
NAME: grafana
LAST DEPLOYED: Fri Sep 11 16:51:45 2026
NAMESPACE: monitoring
STATUS: deployed
REVISION: 2
```

ConfigMap이 바뀌면 차트가 파드 템플릿에 박아 둔 설정 체크섬 어노테이션도 바뀐다. 그래서 이 업그레이드로 파드가 교체된다.

## Ingress /grafana 추가

규칙은 [8.5.1편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-05-01-Prometheus-Metrics-Scrape %})의 `/p8s`와 같은 모양이다. host를 적지 않고 경로만 지정한다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ cat <<EOF | kubectl apply -f -
> apiVersion: networking.k8s.io/v1
> kind: Ingress
> metadata:
>   name: grafana-ingress
>   namespace: monitoring
> spec:
>   ingressClassName: nginx
>   rules:
>   - http:
>       paths:
>       - path: /grafana
>         pathType: Prefix
>         backend:
>           service:
>             name: grafana
>             port:
>               number: 80
> EOF
ingress.networking.k8s.io/grafana-ingress created
```

이 시점에 클러스터의 Ingress는 셋이 된다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ kubectl get ingress -A

# 실행 결과. 셋 다 같은 nginx 클래스이고 같은 ELB 주소를 받는다
NAMESPACE    NAME                  CLASS   HOSTS   ADDRESS                                            PORTS   AGE
default      vllm-ingress-simple   nginx   *       <ingress-elb-id>.us-west-2.elb.amazonaws.com       80      58m
monitoring   grafana-ingress       nginx   *                                                          80      20s
monitoring   prometheus-ingress    nginx   *       <ingress-elb-id>.us-west-2.elb.amazonaws.com       80      28m
```

`grafana-ingress`의 ADDRESS가 아직 비어 있다. 컨트롤러가 status를 채우기 전의 스냅샷일 뿐이고, 백엔드는 이미 잡혀 있다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ kubectl describe ingress -n monitoring grafana-ingress

# 실행 결과 (발췌)
Ingress Class:    nginx
Rules:
  Host        Path  Backends
  ----        ----  --------
  *
              /grafana   grafana:80 (10.0.5.207:3000)
```

백엔드에 찍힌 `10.0.5.207`은 데이터소스 URL 수정으로 교체된 뒤의 파드 IP다. 설치 직후 describe에서 본 `10.0.5.206`과 다른 값인데, 파드가 바뀌었기 때문이지 다른 Grafana가 떠 있어서가 아니다.

## grafana.ini와 프로브에 반영된 값

서브패스 values를 얹기 전의 설정 파일은 `[server]` 블록이 한 줄뿐이다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ kubectl exec -n monitoring grafana-58d8c56477-cbxqc -- cat /etc/grafana/grafana.ini

# 실행 결과 (발췌). domain이 빈 문자열이고 root_url도 serve_from_sub_path도 없다
[server]
domain = ''
```

`$INGRESS`에는 ingress-nginx 컨트롤러 Service의 ELB 호스트명이 들어 있다. 이 값이 heredoc에서 전개돼 `domain`에 박힌다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ echo "INGRESS=$INGRESS"
INGRESS=<ingress-elb-id>.us-west-2.elb.amazonaws.com

ubuntu@ip-10-0-1-100:~/workshop$ helm upgrade grafana grafana/grafana -n monitoring \
>   -f grafana-values.yaml \
>   -f grafana-subpath-values.yaml
```

`-f`를 두 번 준 것은 두 파일을 병합하라는 뜻이다. 뒤에 적은 파일이 우선하고, 겹치지 않는 키는 그대로 합쳐진다.

적용 후 파드가 다시 교체됐고, `[server]` 블록이 세 줄로 늘었다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ kubectl get pod -n monitoring

# 실행 결과. grafana가 새 파드로 바뀌어 AGE가 60초다
NAME                                                READY   STATUS    RESTARTS   AGE
grafana-bf745454-nmsv8                              1/1     Running   0          60s
prometheus-kube-state-metrics-7479c8c8d8-282cv      1/1     Running   0          48m
prometheus-prometheus-node-exporter-jxlhx           1/1     Running   0          48m
prometheus-prometheus-pushgateway-b6ffc6b67-zr76f   1/1     Running   0          48m
prometheus-server-bcdb7cb94-4fvbd                   2/2     Running   0          38m

ubuntu@ip-10-0-1-100:~/workshop$ kubectl exec -n monitoring grafana-bf745454-nmsv8 -- cat /etc/grafana/grafana.ini

# 실행 결과 (발췌). %(domain)s는 치환되지 않은 채 파일에 남아 있다
[server]
domain = <ingress-elb-id>.us-west-2.elb.amazonaws.com
root_url = http://%(domain)s/grafana/
serve_from_sub_path = true
```

`root_url`에 `%(domain)s`가 그대로 남아 있는 것이 정상이다. 이 치환은 파일 생성 시점이 아니라 Grafana가 설정을 읽는 시점에 일어난다.

<details markdown="1">
<summary><b>helm get values grafana 전문 (병합 결과)</b></summary>

```text
USER-SUPPLIED VALUES:
adminPassword: <admin-password>
dashboardProviders:
  dashboardproviders.yaml:
    apiVersion: 1
    providers:
    - disableDeletion: false
      editable: true
      folder: ""
      name: default
      options:
        path: /var/lib/grafana/dashboards/default
      orgId: 1
      type: file
dashboards:
  default:
    kubernetes-cluster:
      datasource: Prometheus
      gnetId: 7249
      revision: 1
    kubernetes-pods:
      datasource: Prometheus
      gnetId: 6336
      revision: 1
datasources:
  datasources.yaml:
    apiVersion: 1
    datasources:
    - access: proxy
      isDefault: true
      name: Prometheus
      type: prometheus
      url: http://prometheus-server.monitoring.svc.cluster.local/p8s
grafana.ini:
  server:
    domain: <ingress-elb-id>.us-west-2.elb.amazonaws.com
    root_url: http://%(domain)s/grafana/
    serve_from_sub_path: true
livenessProbe:
  failureThreshold: 10
  httpGet:
    path: /grafana/api/health
    port: grafana
  initialDelaySeconds: 60
  timeoutSeconds: 30
persistence:
  enabled: false
readinessProbe:
  failureThreshold: 6
  httpGet:
    path: /grafana/api/health
    port: grafana
  initialDelaySeconds: 10
  periodSeconds: 10
resources:
  limits:
    cpu: 500m
    memory: 1Gi
  requests:
    cpu: 250m
    memory: 512Mi
service:
  type: ClusterIP
```

</details>

<br>

# 검증: 서브패스 로그인과 데이터소스

## 서브패스로 열린 로그인 화면

브라우저에서 `http://<ingress-elb-id>.us-west-2.elb.amazonaws.com/grafana/login`을 연다. 포트를 붙이지 않았고, 경로만으로 Grafana에 닿는다. 사용자명은 `admin`, 비밀번호는 values의 `adminPassword`에 적은 값이다.

![서브패스로 연 Grafana 로그인 화면]({{site.url}}/assets/images/llmso-aws-workshop-grafana-login.png){: .align-center}

<center><sup>직접 캡처. Grafana 로그인 화면이다. 사용자명에 admin이 입력돼 있고, 하단에 Grafana v12.3.1이 표시돼 있다.</sup></center>

이 시점에 ingress-nginx 하나가 세 갈래를 가르고 있다. `/`는 vLLM, `/p8s`는 Prometheus, `/grafana`는 Grafana다. [8.4편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-04-Ingress-Nginx-Routing %})은 컨트롤러를 올려 경로로 분기할 계층만 확보하고 규칙은 `/` 하나만 적용한 상태로 끝났는데, Lab 4에서 규칙 두 장이 더 붙으면서 그 분기가 실제로 돌고 있다.

## 프로비저닝된 데이터소스

Connections의 Data sources 목록에 들어가면 values에 적은 데이터소스가 그대로 있다.

![프로비저닝된 Prometheus 데이터소스]({{site.url}}/assets/images/llmso-aws-workshop-grafana-datasource-provisioned.png){: .align-center}

<center><sup>직접 캡처. Grafana의 Data sources 목록이다. Prometheus 데이터소스 하나가 http://prometheus-server.monitoring.svc.cluster.local/p8s를 가리키고 default 배지가 붙어 있다.</sup></center>

URL 끝에 `/p8s`가 붙어 있고 `default` 배지가 달려 있다. 앞에서 고친 `url` 한 줄과 `isDefault: true`가 화면에 반영된 결과다.

## Explore의 메트릭 목록

Explore에서 데이터소스를 Prometheus로 두고 메트릭 입력란에 `vllm:`을 치면 자동완성 목록이 뜬다.

![Explore의 vLLM 메트릭 자동완성]({{site.url}}/assets/images/llmso-aws-workshop-grafana-explore.png){: .align-center}

<center><sup>직접 캡처. Explore 화면의 메트릭 선택기다. vllm: 을 입력하면 vllm:cache_config_info, vllm:e2e_request_latency_seconds_bucket, vllm:generation_tokens_total, vllm:gpu_cache_usage_perc 등이 나열되고, 아직 쿼리를 실행하지 않아 오른쪽 패널은 No data다.</sup></center>

이 목록은 Grafana가 스스로 만든 것이 아니라 데이터소스에 메타데이터를 질의해 받아 온 것이다. 즉 목록이 떴다는 사실 자체가 `/p8s`를 붙인 URL로 질의가 성립한다는 증거다. 오른쪽 패널이 No data인 것은 아직 쿼리를 실행하지 않아서다.

<br>

# 적용과 관찰: vLLM 대시보드

## 대시보드 JSON

대시보드는 배스천에서 `vllm-dashboard.json` 파일로 직접 작성했다. 패널 여덟 개짜리 한 장이다. 구조를 보여 주는 두 개만 발췌하면 이렇다.

```json
{
  "id": null,
  "title": "vLLM Inference Metrics",
  "description": "Dashboard for monitoring vLLM inference performance",
  "tags": ["vllm", "inference", "llm"],
  "timezone": "browser",
  "panels": [
    {
      "id": 1,
      "title": "Total Successful Requests",
      "type": "stat",
      "targets": [
        {
          "expr": "vllm:request_success_total",
          "legendFormat": "Total Requests"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short"
        }
      },
      "gridPos": {"h": 8, "w": 6, "x": 0, "y": 0}
    },
    {
      "id": 4,
      "title": "KV Cache Usage",
      "type": "gauge",
      "targets": [
        {
          "expr": "vllm:gpu_cache_usage_perc * 100",
          "legendFormat": "KV Cache Usage %"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "percent",
          "min": 0,
          "max": 100,
          "thresholds": {
            "steps": [
              {"color": "green", "value": 0},
              {"color": "yellow", "value": 60},
              {"color": "red", "value": 80}
            ]
          }
        }
      },
      "gridPos": {"h": 8, "w": 6, "x": 18, "y": 0}
    }
  ],
  "time": {"from": "now-15m", "to": "now"},
  "refresh": "10s"
}
```

패널 하나는 `expr`(PromQL)과 `type`(시각화 종류), `gridPos`(격자 좌표)로 정의된다. `gridPos`의 `w`는 24분할 기준 너비이므로 `w: 6`은 화면 1/4이다. 문서 끝의 `time`과 `refresh`가 기본 조회 창을 `now-15m`, 자동 새로고침을 10초로 정한다.

<details markdown="1">
<summary><b>vllm-dashboard.json 전문</b></summary>

```json
{
  "id": null,
  "title": "vLLM Inference Metrics",
  "description": "Dashboard for monitoring vLLM inference performance",
  "tags": ["vllm", "inference", "llm"],
  "timezone": "browser",
  "panels": [
    {
      "id": 1,
      "title": "Total Successful Requests",
      "type": "stat",
      "targets": [
        {
          "expr": "vllm:request_success_total",
          "legendFormat": "Total Requests"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short"
        }
      },
      "gridPos": {"h": 8, "w": 6, "x": 0, "y": 0}
    },
    {
      "id": 2,
      "title": "Running Requests",
      "type": "stat",
      "targets": [
        {
          "expr": "vllm:num_requests_running",
          "legendFormat": "Running"
        }
      ],
      "gridPos": {"h": 8, "w": 6, "x": 6, "y": 0}
    },
    {
      "id": 3,
      "title": "Waiting Requests",
      "type": "stat",
      "targets": [
        {
          "expr": "vllm:num_requests_waiting",
          "legendFormat": "Waiting"
        }
      ],
      "gridPos": {"h": 8, "w": 6, "x": 12, "y": 0}
    },
    {
      "id": 4,
      "title": "KV Cache Usage",
      "type": "gauge",
      "targets": [
        {
          "expr": "vllm:gpu_cache_usage_perc * 100",
          "legendFormat": "KV Cache Usage %"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "percent",
          "min": 0,
          "max": 100,
          "thresholds": {
            "steps": [
              {"color": "green", "value": 0},
              {"color": "yellow", "value": 60},
              {"color": "red", "value": 80}
            ]
          }
        }
      },
      "gridPos": {"h": 8, "w": 6, "x": 18, "y": 0}
    },
    {
      "id": 5,
      "title": "Total Prompt Tokens",
      "type": "stat",
      "targets": [
        {
          "expr": "vllm:prompt_tokens_total",
          "legendFormat": "Prompt Tokens"
        }
      ],
      "gridPos": {"h": 8, "w": 6, "x": 0, "y": 8}
    },
    {
      "id": 6,
      "title": "Total Generated Tokens",
      "type": "stat",
      "targets": [
        {
          "expr": "vllm:generation_tokens_total",
          "legendFormat": "Generated Tokens"
        }
      ],
      "gridPos": {"h": 8, "w": 6, "x": 6, "y": 8}
    },
    {
      "id": 7,
      "title": "Request Success Over Time",
      "type": "timeseries",
      "targets": [
        {
          "expr": "vllm:request_success_total",
          "legendFormat": "Total Successful Requests"
        }
      ],
      "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8}
    },
    {
      "id": 8,
      "title": "Token Generation Over Time",
      "type": "timeseries",
      "targets": [
        {
          "expr": "vllm:prompt_tokens_total",
          "legendFormat": "Prompt Tokens"
        },
        {
          "expr": "vllm:generation_tokens_total",
          "legendFormat": "Generated Tokens"
        }
      ],
      "gridPos": {"h": 8, "w": 24, "x": 0, "y": 16}
    }
  ],
  "time": {"from": "now-15m", "to": "now"},
  "refresh": "10s"
}
```

</details>

## 패널과 쿼리

패널 여덟 개가 쓰는 쿼리는 다음과 같다.

| 패널 | 쿼리 | 종류 |
|---|---|---|
| Total Successful Requests | `vllm:request_success_total` | stat |
| Running Requests | `vllm:num_requests_running` | stat |
| Waiting Requests | `vllm:num_requests_waiting` | stat |
| KV Cache Usage | `vllm:gpu_cache_usage_perc * 100` | gauge |
| Total Prompt Tokens | `vllm:prompt_tokens_total` | stat |
| Total Generated Tokens | `vllm:generation_tokens_total` | stat |
| Request Success Over Time | `vllm:request_success_total` | timeseries |
| Token Generation Over Time | `vllm:prompt_tokens_total`, `vllm:generation_tokens_total` | timeseries |

쿼리를 그대로 읽으면 구조상 눈에 띄는 점이 둘 있다.

하나는 시계열 패널 두 개가 counter를 **원시값 그대로** 쓴다는 것이다. counter는 단조 증가하는 누적값이라 `rate()` 같은 함수를 씌우지 않으면 그래프가 계단이나 직선으로만 그려진다. 변화율을 보려는 패널에 누적값을 넣은 셈이다.

다른 하나는 `vllm:request_success_total`에 집계 함수가 없다는 것이다. 이 메트릭은 `finished_reason` 라벨을 달고 나오므로 시리즈가 하나가 아니다. `sum()` 없이 stat 패널에 넣으면 시리즈 개수만큼 값이 따로 표시된다.

## ConfigMap 생성

작성한 JSON 파일을 ConfigMap으로 만든다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ kubectl create configmap vllm-dashboard \
>   --from-file=vllm-dashboard.json \
>   -n monitoring
configmap/vllm-dashboard created

ubuntu@ip-10-0-1-100:~/workshop$ kubectl get cm -n monitoring prometheus-server vllm-dashboard

# 실행 결과. DATA는 ConfigMap이 들고 있는 키 개수다
NAME                DATA   AGE
prometheus-server   6      57m
vllm-dashboard      1      12s
```

`vllm-dashboard`의 DATA가 1인 것은 `--from-file`로 넣은 파일 하나가 `vllm-dashboard.json`이라는 키 하나가 됐다는 뜻이다. 여기까지 하고 Grafana의 Dashboards 목록을 열면 vLLM 대시보드가 보이지 않는다. [증상](#증상)과 그 원인은 뒤에서 다룬다.

## Deployment 어노테이션

Lab의 마지막 단계는 vLLM Deployment에 어노테이션 세 개를 붙이는 것이다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ kubectl annotate deployment vllm-deployment -n default \
>   prometheus.io/scrape=true \
>   prometheus.io/port=8080 \
>   prometheus.io/path=/metrics
deployment.apps/vllm-deployment annotated

ubuntu@ip-10-0-1-100:~/workshop$ kubectl describe deployments.apps | grep ^Annotations: -A3

# 실행 결과
Annotations:            deployment.kubernetes.io/revision: 1
                        prometheus.io/path: /metrics
                        prometheus.io/port: 8080
                        prometheus.io/scrape: true
```

바뀐 것은 어노테이션뿐이다. 포트를 새로 연 것도, 컨테이너 인자를 고친 것도 아니다. 노리는 메커니즘은 차트 기본 잡 `kubernetes-pods`인데, 이 잡은 `role: pod`로 파드를 발견한 뒤 `prometheus.io/scrape`가 `true`인 것만 남긴다. 여기까지는 실재하는 동작이다.

그런데 그 relabel이 읽는 것은 **파드**의 어노테이션이고, `kubectl annotate deployment`는 **Deployment 오브젝트 자신**에 붙인다. `spec.template.metadata.annotations`가 아니므로 파드로 전파되지 않는다. 위 출력이 그대로 말해 준다. 세 어노테이션이 `deployment.kubernetes.io/revision`과 같은 블록에 찍혀 있는데, 이 키는 Deployment 컨트롤러가 Deployment 오브젝트에 다는 것이다. 그리고 그 `revision`이 1에서 움직이지 않았다. 파드 템플릿이 바뀌었다면 새 ReplicaSet이 생기고 롤아웃이 돌면서 revision이 올라갔을 것이다. 롤아웃이 없었다는 것은 파드가 바뀐 적 없다는 뜻이다.

애초에 이 구성에서는 필요하지도 않다. [8.5.1편]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-05-01-Prometheus-Metrics-Scrape %})의 `vllm-metrics` 잡이 이미 같은 `/metrics`를 10초마다 긁고 있다. 어노테이션이 파드에 제대로 붙었다면 `kubernetes-pods` 잡이 같은 엔드포인트를 한 번 더 긁게 되고, 동일한 시계열이 `job` 라벨만 다른 채로 둘 들어온다. 고치는 업데이트가 아니라 중복을 만드는 업데이트가 된다.

이 단계가 왜 워크샵 절차에 들어 있는지는 확인하지 못했다. 정적 타깃을 쓰지 않고 어노테이션 방식만으로 수집하던 흐름의 흔적일 가능성은 있지만, 워크샵 원본 매니페스트를 보지 못했으므로 추정에 머문다.

<br>

# 막힘 & 해결: 마운트되지 않은 ConfigMap

## 증상

ConfigMap을 만든 뒤 Grafana의 Dashboards 목록을 열면 대시보드가 두 개뿐이다.

![ConfigMap을 만든 직후의 Dashboards 목록]({{site.url}}/assets/images/llmso-aws-workshop-grafana-dashboard-not-showing.png){: .align-center}

<center><sup>직접 캡처. ConfigMap을 만든 직후의 Dashboards 목록이다. Kubernetes Cluster와 Kubernetes Pods (Prometheus) 두 개만 있다.</sup></center>

두 개는 values의 `dashboards` 블록에 적은 `gnetId: 7249`와 `gnetId: 6336`이다. 즉 init container가 받아 온 것만 보이고, 방금 만든 `vllm-dashboard`는 없다.

## 증거

앞에서 본 파드 상세와 values를 다시 읽으면 근거가 셋 나온다.

- provider가 [`type: file`이고 `options.path`가 `/var/lib/grafana/dashboards/default`](#dashboardproviders)다. Grafana가 보는 것은 디렉터리이지 쿠버네티스 API가 아니다
- `describe pod`의 Volumes 목록은 `config`, `dashboards-default`, `storage`, `search` 넷이다. `vllm-dashboard`라는 볼륨은 없다
- 같은 출력의 Containers는 init `download-dashboards`와 `grafana` 둘뿐이다. ConfigMap을 감시하는 사이드카 컨테이너가 없다

## 원인

ConfigMap을 만들기만 하고 **파드에 마운트하지 않았다.** ConfigMap은 etcd에 있고, Grafana가 읽는 것은 파드 안 디렉터리다. 둘이 연결된 적이 없으니 그 디렉터리에는 아무것도 생기지 않았다.

`grafana_dashboard` 라벨을 떠올렸다면 그것은 다른 구성의 이야기다. 라벨 기반 자동 수집은 차트의 대시보드 사이드카가 하는 일인데, 그 기능은 기본이 꺼져 있고 이 values는 해당 키를 건드리지 않았다. 감시자가 없으니 ConfigMap에 라벨을 붙여도 달라지는 것이 없다.

## 해결

볼륨과 볼륨 마운트를 Deployment에 추가한다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ kubectl patch deployment grafana -n monitoring --type='json' -p='[
>   {
>     "op": "add",
>     "path": "/spec/template/spec/volumes/-",
>     "value": {
>       "name": "vllm-dashboard",
>       "configMap": {
>         "name": "vllm-dashboard"
>       }
>     }
>   },
>   {
>     "op": "add",
>     "path": "/spec/template/spec/containers/0/volumeMounts/-",
>     "value": {
>       "name": "vllm-dashboard",
>       "mountPath": "/var/lib/grafana/dashboards/default/vllm-dashboard.json",
>       "subPath": "vllm-dashboard.json"
>     }
>   }
> ]'
deployment.apps/grafana patched
```

`mountPath`가 디렉터리가 아니라 파일 경로이고 `subPath`로 ConfigMap의 키 하나를 지정했다. 이렇게 하면 기존 디렉터리 내용을 덮지 않고 그 자리에 파일 하나만 얹힌다. 파드 템플릿이 바뀌었으므로 롤아웃이 돈다.

```shell
ubuntu@ip-10-0-1-100:~/workshop$ kubectl get pod -n monitoring -w

# 실행 결과 (발췌). 새 파드가 Ready가 된 뒤 이전 파드가 내려간다
grafana-966d7f96-pjwsq   0/1   PodInitializing   0     2s
grafana-966d7f96-pjwsq   0/1   Running           0     3s
grafana-966d7f96-pjwsq   1/1   Running           0     14s
grafana-bf745454-nmsv8   1/1   Terminating       0     11m
```

목록을 다시 열면 대시보드가 세 개다.

![마운트 후의 Dashboards 목록]({{site.url}}/assets/images/llmso-aws-workshop-grafana-dashboard-showing.png){: .align-center}

<center><sup>직접 캡처. 볼륨 마운트를 붙이고 파드가 교체된 뒤의 Dashboards 목록이다. vLLM Inference Metrics가 추가됐고, 대시보드 JSON에 적은 inference, llm, vllm 태그가 함께 보인다.</sup></center>

이 마운트 모양은 차트가 `dashboards` values를 처리할 때 쓰는 것과 같다. 손으로 차트 동작을 재현한 셈이다. values로 관리하고 싶다면 이미 만들어 둔 ConfigMap을 붙이는 `dashboardsConfigMaps` 키가 그 자리다. 다만 이번 실습에서는 `kubectl patch`로만 적용했고, 이후 `helm upgrade`를 돌렸을 때 차트 밖에서 추가한 이 볼륨이 어떻게 되는지는 확인하지 않았다.

제약도 하나 붙는다. 쿠버네티스 문서가 적어 둔 대로 **`subPath`로 마운트한 ConfigMap은 갱신이 반영되지 않는다.** 대시보드 JSON을 고쳐 ConfigMap을 갱신해도 파드 안 파일은 그대로이고, 파드를 다시 띄워야 바뀐 내용이 들어간다.

대시보드를 열면 패널이 값을 받아 온다.

![vLLM Inference Metrics 대시보드 위쪽 패널]({{site.url}}/assets/images/llmso-aws-workshop-grafana-dashboard-1.png){: .align-center}

<center><sup>직접 캡처. vLLM Inference Metrics 대시보드의 위쪽 패널이다. Total Successful Requests에 3과 6 두 값이 나란히 표시되고, Running Requests와 Waiting Requests가 0, KV Cache Usage가 0%, Total Prompt Tokens가 210, Total Generated Tokens가 2371이다.</sup></center>

![Token Generation Over Time 패널]({{site.url}}/assets/images/llmso-aws-workshop-grafana-dashboard-2.png){: .align-center}

<center><sup>직접 캡처. 같은 대시보드를 아래로 내렸을 때 보이는 Token Generation Over Time 패널이다. Prompt Tokens와 Generated Tokens 두 계열 모두 02:04부터 02:18까지 값이 평평하다.</sup></center>

값이 거의 0이라 수집이 안 되는 것처럼 보이지만 그렇지 않다. `Running Requests`와 `Waiting Requests`, `KV Cache Usage` 셋은 순간값이라 요청이 돌고 있지 않으면 0이 맞는 값이다. No data가 아니라 0이다. 누적값 패널은 값이 있다 — 프롬프트 토큰 210개, 생성 토큰 2371개다. 그때까지 보낸 것이 테스트 요청 몇 건뿐이라 15분 창에서는 평평한 직선으로 그려진다. 앞 절에서 짚은 원시 counter 쿼리 문제가 여기에 겹친다.

`Total Successful Requests`가 한 칸이 아니라 3과 6 두 칸으로 나뉜 것도 같은 계열이다. `finished_reason` 라벨 때문에 시리즈가 둘인데 쿼리에 `sum()`이 없어 각각 표시됐다. 오른쪽 `Request Success Over Time` 패널의 계열 두 개가 3과 6에 각각 평평하게 깔린 것도 같은 이유다.

<br>

# 정리

| 질문 | 답 |
|---|---|
| Grafana는 Prometheus와 같은 릴리스인가 | 아니다. `grafana/grafana` 10.5.15 별도 릴리스다. 오퍼레이터도 CRD도 없어 데이터소스와 대시보드는 values의 프로비저닝 파일로 들어간다 |
| `datasources`와 `dashboards`는 같은 방식인가 | 아니다. 앞은 설정 파일로 마운트되고, 뒤는 init container가 파일로 내려받는다 |
| 데이터소스 URL을 UI에서 못 고치는 이유 | 프로비저닝된 데이터소스는 읽기 전용으로 잠긴다. values를 고쳐 `helm upgrade` 해야 한다 |
| URL에 `/p8s`를 왜 붙였나 | `--web.route-prefix`가 Prometheus 프로세스의 내부 라우팅 테이블을 바꿔서 ClusterIP로 직행하는 경로도 옮겨갔다. 파드 안에서 확인하면 `/api/v1/query`는 404, `/p8s/api/v1/query`는 200이다 |
| `root_url`만 고치면 되나 | 안 된다. `serve_from_sub_path: true`를 따로 켜야 Grafana가 `/grafana` 아래에서 응답한다 |
| 프로브를 왜 같이 고치나 | 서브패스가 켜지면 `/api/health`도 `/grafana/api/health`로 옮겨간다. Prometheus 차트가 자동으로 해 주던 일을 Grafana 차트에서는 values로 직접 적는다 |
| ConfigMap을 만들었는데 대시보드가 없는 이유 | Grafana가 ConfigMap을 읽지 않는다. provider가 `type: file`이라 파드 안 디렉터리만 읽고, 마운트가 빠져 있었다 |
| `grafana_dashboard` 라벨을 붙이면 되나 | 이 구성에서는 무관하다. 라벨을 감시하는 대시보드 사이드카가 설치돼 있지 않다 |
| 마운트한 JSON을 고치면 바로 반영되나 | 아니다. `subPath`로 마운트한 ConfigMap은 갱신이 반영되지 않는다. 파드를 다시 띄워야 한다 |
| `kubectl annotate deployment`의 효과 | 이 구성에서는 없다. 어노테이션이 Deployment 오브젝트에 붙고 파드 템플릿으로 전파되지 않았다. `revision`이 1에서 움직이지 않은 것이 증거다 |
| 패널 값이 왜 대부분 0인가 | 순간값 패널은 요청이 돌지 않으면 0이 맞는 값이다. 누적값도 테스트 요청 몇 건분이라 15분 창에서 평평하다. 메트릭 미노출이 아니다 |
| `Total Successful Requests`가 왜 두 칸인가 | `finished_reason` 라벨 때문에 시리즈가 둘인데 쿼리에 `sum()`이 없다 |

Lab 4에서 만든 것은 수집과 화면까지다. Prometheus가 vLLM 메트릭을 긁고, Grafana가 그것을 읽고, 대시보드 한 장이 값을 표시한다. 부하를 실제로 걸어 이 패널들이 움직이는지 확인하는 것, 그리고 CPU 사용률 기반 오토스케일링은 이후 Lab이다.

보관에 대해 알아 둘 점도 하나 있다. Prometheus에 PV가 없어서 `prometheus-server` 파드가 교체될 때마다 기존 시계열이 사라진다. Lab 진행 중 그 파드가 교체됐으므로, 대시보드에서 그 이전 구간을 조회하면 그때는 정말로 비어 있다.

<br>

# 참고 링크

- [Grafana: Provision Grafana](https://grafana.com/docs/grafana/latest/administration/provisioning/)
- [Grafana: Configure Grafana - root_url](https://grafana.com/docs/grafana/latest/setup-grafana/configure-grafana/#root_url)
- [Grafana: Configure Grafana - serve_from_sub_path](https://grafana.com/docs/grafana/latest/setup-grafana/configure-grafana/#serve_from_sub_path)
- [Grafana: Dashboard JSON model](https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/view-dashboard-json-model/)
- [grafana/grafana Helm chart values (GitHub)](https://github.com/grafana/helm-charts/blob/grafana-10.5.15/charts/grafana/values.yaml)
- [prometheus-community/prometheus Helm chart values (GitHub)](https://github.com/prometheus-community/helm-charts/blob/prometheus-29.28.1/charts/prometheus/values.yaml)
- [Prometheus: Command-line flags](https://prometheus.io/docs/prometheus/latest/command-line/prometheus/)
- [Kubernetes: ConfigMap을 볼륨으로 사용하기](https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/#add-configmap-data-to-a-volume)
- [Kubernetes: Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
- [Kubernetes: Annotations](https://kubernetes.io/docs/concepts/overview/working-with-objects/annotations/)
- [Kubernetes: Ingress - Path types](https://kubernetes.io/docs/concepts/services-networking/ingress/#path-types)
- [vLLM Documentation](https://docs.vllm.ai/)
- [08-00편: vLLM on Trainium 워크샵 개요]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-00-EKS-Workshop-Overview %})
- [08-01편: AWS 가속기 - Inferentia, Trainium, NeuronCore]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-01-AWS-Accelerators %})
- [08-02-01편: Trainium 노드그룹 구성]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-02-01-EKS-Cluster-Nodegroup %})
- [08-02-02편: Trainium 디바이스가 쿠버네티스에 노출되는 경로]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-02-02-Neuron-Device-Exposure %})
- [08-03-01편: init container 모델 컴파일과 S3 캐시]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-03-01-vLLM-Deployment %})
- [08-03-02편: LoadBalancer 서비스 노출과 추론 테스트]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-03-02-Service-LoadBalancer %})
- [08-04편: ingress-nginx L7 노출과 자체 서명 인증서]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-04-Ingress-Nginx-Routing %})
- [08-05-01편: vLLM 메트릭 수집과 서브패스 노출]({% post_url 2026-09-11-Kubernetes-LLM-Serving-Optimization-08-05-01-Prometheus-Metrics-Scrape %})

<br>
