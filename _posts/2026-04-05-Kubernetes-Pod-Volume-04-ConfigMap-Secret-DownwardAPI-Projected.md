---
title:  "[Kubernetes] Pod 볼륨 - 4. configMap, secret, downwardAPI, projected 볼륨"
excerpt: "ConfigMap, Secret, Downward API 데이터를 볼륨으로 컨테이너에 파일로 주입하는 방법과 projected 볼륨을 정리한다."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubernetes-in-Action-2nd
  - volume
  - configMap
  - secret
  - downwardAPI
  - projected
  - fsGroup
  - file-permissions
hidden: true
---

*[Kubernetes in Action 2nd Edition](https://www.manning.com/books/kubernetes-in-action-second-edition) 9장의 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- `configMap` 볼륨은 ConfigMap 항목을 컨테이너 파일로 노출하며, ConfigMap 업데이트 시 심볼릭 링크 교체를 통해 원자적으로 자동 반영된다
- `secret` 볼륨은 `configMap` 볼륨과 거의 동일하지만, `secretName` 필드를 사용하고 `tmpfs`(인메모리)에 저장되어 보안성이 높다
- 파일 권한은 `defaultMode`/`mode`로 설정하고, non-root 프로세스의 접근은 `securityContext.fsGroup`으로 그룹 소유권을 변경하여 해결한다
- `projected` 볼륨은 ConfigMap, Secret, Downward API 등 여러 소스의 파일을 하나의 디렉토리에 합칠 수 있다
- 모든 Pod에는 Kubernetes API 접근용 `kube-api-access` projected 볼륨이 자동 주입된다

<br>

[어플리케이션 설정]({% post_url 2026-04-05-Kubernetes-Application-Config-01-Command-Args-Env %}) 시리즈에서 ConfigMap, Secret, Downward API의 데이터를 **환경 변수**로 컨테이너에 주입하는 방법을 다뤘다. 이 글에서는 같은 데이터를 **볼륨을 통해 파일로** 컨테이너에 주입하는 방식을 정리한다. 환경 변수 방식은 작은 단일 행 값에 적합하고, 긴 여러 줄의 설정 파일은 볼륨으로 전달하는 것이 더 적합하다.

5장에서 TLS 트래픽을 처리하는 Envoy 사이드카와 함께 kiada Pod를 배포할 때, Envoy 설정 파일과 TLS 인증서/키를 컨테이너 이미지에 직접 저장했다. 하지만 이는 올바른 방법이 아니다. 설정 파일은 ConfigMap에, 인증서와 개인 키는 Secret에 저장하고 볼륨으로 컨테이너에 주입하면 이미지를 다시 빌드하지 않고도 파일을 업데이트할 수 있다.

> **Note:** ConfigMap이나 Secret에 저장 가능한 정보의 최대 크기는 etcd에 의해 결정되며, 현재 약 1MB이다.

<br>

# configMap 볼륨

`configMap` 볼륨은 ConfigMap 항목을 개별 파일로 사용할 수 있게 해준다. 컨테이너에서 실행 중인 프로세스가 이 파일들을 읽어 값을 가져올 수 있다. 주로 대용량 설정 파일을 컨테이너에 전달하는 데 사용되지만, 작은 값에도 사용할 수 있으며, `env`나 `envFrom` 필드와 결합하여 큰 항목은 파일로, 나머지는 환경 변수로 전달할 수도 있다.

## Pod에 configMap 볼륨 추가하기

ConfigMap 항목을 컨테이너 파일시스템에서 파일로 사용하려면, configMap 볼륨을 정의하고 컨테이너에 마운트한다.

- `envoy-config` 볼륨: `kiada-ssl-config` ConfigMap을 가리키는 configMap 볼륨
- 마운트 경로: envoy 컨테이너의 `/etc/envoy` 경로에 마운트

```yaml
# Chapter09/pod.kiada-ssl.configmap-volume.yaml
apiVersion: v1
kind: Pod
metadata:
  name: kiada-ssl
spec:
  volumes:
  - name: envoy-config
    configMap:
      name: kiada-ssl-config
  containers:
  - name: kiada
    image: luksa/kiada:0.4
    env:
    - name: POD_NAME
      valueFrom:
        fieldRef:
          fieldPath: metadata.name
    - name: POD_IP
      valueFrom:
        fieldRef:
          fieldPath: status.podIP
    - name: NODE_NAME
      valueFrom:
        fieldRef:
          fieldPath: spec.nodeName
    - name: NODE_IP
      valueFrom:
        fieldRef:
          fieldPath: status.hostIP
    - name: INITIAL_STATUS_MESSAGE
      valueFrom:
        configMapKeyRef:
          name: kiada-ssl-config
          key: status-message
          optional: true
    ports:
    - name: http
      containerPort: 8080
  - name: envoy
    image: luksa/kiada-ssl-proxy:0.1
    volumeMounts:
    - name: envoy-config
      mountPath: /etc/envoy
      readOnly: true
    ports:
    - name: https
      containerPort: 8443
    - name: admin
      containerPort: 9901
```

Pod의 configMap 볼륨이 존재하지 않는 ConfigMap을 참조하면 컨테이너가 실행될 수 없다.

```bash
kubectl apply -f pod.kiada-ssl.configmap-volume.yaml
# pod/kiada-ssl created

# ContainerCreating 상태에서 멈춰 있음
kubectl get po kiada-ssl -w
# NAME        READY   STATUS              RESTARTS   AGE
# kiada-ssl   0/2     ContainerCreating   0          7m58s

kubectl describe pod kiada-ssl
# ...
# Events:
#   Type     Reason       Age                    From               Message
#   ----     ------       ----                   ----               -------
#   Normal   Scheduled    9m17s                  default-scheduler  Successfully assigned default/kiada-ssl to kind-worker2
#   Warning  FailedMount  3m5s (x11 over 9m17s)  kubelet            MountVolume.SetUp failed for volume "envoy-config" : configmap "kiada-ssl-config" not found
```

## optional 설정

볼륨에서 누락된 ConfigMap을 참조하면, 해당 볼륨이 마운트된 컨테이너뿐만 아니라 Pod의 **모든 컨테이너**가 시작되지 않는다. Pod의 모든 볼륨은 컨테이너가 시작되기 전에 설정되어야 하기 때문이다.

이는 환경 변수 방식과 다른 동작이다. 환경 변수의 경우 존재하지 않는 ConfigMap을 참조하면 **해당 컨테이너만** 시작이 차단되고, 다른 컨테이너의 시작을 막지는 않았다. 반면 볼륨은 Pod 레벨에서 설정되므로, kubelet이 볼륨 설정 단계를 통과하지 못하면 컨테이너 생성 단계 자체로 진행하지 않는다. `FailedMount` 이벤트가 먼저 뜨고, 이미지 pull 이벤트(`Pulling image ...`)는 볼륨 마운트가 성공한 이후에야 나타난다.

환경 변수 설정 방식에서 optional 설정을 할 수 있었듯, 볼륨 정의에도 `optional: true`를 추가할 수 있다. 볼륨이 optional이고 ConfigMap이 존재하지 않으면 볼륨이 생성되지 않으며, 해당 볼륨을 마운트하지 않은 채 컨테이너가 시작된다.

```yaml
volumes:
- name: envoy-config
  configMap:
    name: kiada-ssl-config
    optional: true # ConfigMap이 존재하지 않을 때 Pod 정상 시작
```

혹은 ConfigMap을 생성하여 Pod가 정상 시작되도록 한다. 아래는 Envoy 사이드카 프록시 설정을 담은 ConfigMap이다.

<details markdown="1">
<summary>kiada-ssl-config ConfigMap (cm.kiada-ssl-config.yaml)</summary>

```yaml
# Chapter09/cm.kiada-ssl-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: kiada-ssl-config
data:
  # kiada 앱이 표시하는 상태 메시지 — 환경변수 STATUS_MESSAGE로 주입됨
  status-message: "This status message is set in the kiada-ssl-config ConfigMap"

  # Envoy 프록시 설정 파일 전문 (YAML 멀티라인 리터럴 블록)
  envoy.yaml: |

    # ── Envoy 관리(Admin) 인터페이스 ──
    # 9901 포트에서 Envoy 내부 상태/통계를 확인할 수 있는 관리 엔드포인트
    admin:
      access_log:
      - name: envoy.access_log
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.access_loggers.file.v3.FileAccessLog
          path: /tmp/envoy.admin.log
      address:
        socket_address:
          protocol: TCP
          address: 0.0.0.0
          port_value: 9901

    static_resources:
      # ── 리스너: 클라이언트 요청을 수신하는 진입점 ──
      listeners:
      - name: listener_0
        address:
          socket_address:
            address: 0.0.0.0
            port_value: 8443            # HTTPS 수신 포트
        filter_chains:
        # TLS 설정 — Secret 볼륨에서 마운트된 인증서/키 파일 참조
        - transport_socket:
            name: envoy.transport_sockets.tls
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.DownstreamTlsContext
              common_tls_context:
                tls_certificates:
                - certificate_chain:
                    filename: "/etc/certs/example-com.crt"   # TLS 인증서
                  private_key:
                    filename: "/etc/certs/example-com.key"   # TLS 개인키
          filters:
          # HTTP 연결 관리자 — 수신된 HTTPS 요청을 라우팅
          - name: envoy.filters.network.http_connection_manager
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
              stat_prefix: ingress_http
              route_config:
                name: local_route
                virtual_hosts:
                - name: local_service
                  domains: ["*"]        # 모든 호스트명에 매칭
                  routes:
                  - match:
                      prefix: "/"       # 모든 경로를 kiada 클러스터로 전달
                    route:
                      cluster: service_kiada_localhost
              http_filters:
              - name: envoy.filters.http.router
                typed_config:
                  "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router

      # ── 클러스터: 트래픽을 전달할 업스트림(백엔드) 정의 ──
      # 같은 Pod 내 localhost:8080의 kiada 컨테이너로 프록시
      clusters:
      - name: service_kiada_localhost
        connect_timeout: 0.25s
        type: STATIC                    # DNS 조회 없이 고정 IP 사용
        load_assignment:
          cluster_name: service_kiada_localhost
          endpoints:
          - lb_endpoints:
            - endpoint:
                address:
                  socket_address:
                    address: 127.0.0.1  # 같은 Pod의 kiada 컨테이너
                    port_value: 8080    # kiada HTTP 포트
```

이 ConfigMap은 두 개의 키를 포함한다:
1. `status-message`: kiada 앱이 환경변수로 사용하는 상태 메시지
2. `envoy.yaml`: Envoy 프록시의 전체 설정 파일

Envoy 설정의 흐름은 `클라이언트 → [listener_0 :8443 HTTPS] → TLS 종료 → HTTP 라우팅 → [cluster: localhost:8080] → kiada 컨테이너`이다.

</details>

ConfigMap을 생성하면 Pod가 정상적으로 시작된다.

```bash
kubectl apply -f cm.kiada-ssl-config.yaml
# configmap/kiada-ssl-config created

kubectl get po kiada-ssl -w
# NAME        READY   STATUS              RESTARTS   AGE
# kiada-ssl   0/2     ContainerCreating   0          4s
# kiada-ssl   2/2     Running             0          66s

# configmap 마운트 확인
kubectl exec kiada-ssl -c envoy -- ls /etc/envoy
# envoy.yaml
# status-message
```

`describe` 이벤트를 보면, `FailedMount` 이벤트 이후 ConfigMap이 생성되자 이미지 pull과 컨테이너 생성이 순서대로 진행되는 것을 확인할 수 있다.

## 특정 항목만 선택적으로 투영(project)하기

Envoy는 `status-message` 파일이 필요 없지만, kiada 컨테이너가 사용하므로 ConfigMap에서 제거할 수는 없다. `items` 필드를 사용하면 **특정 항목만 볼륨에 포함**되도록 설정할 수 있다.

- 각 항목은 `key`(ConfigMap의 키)와 `path`(볼륨 내 파일 경로)를 명시해야 한다
- 여기에 나열되지 않은 항목은 볼륨에 포함되지 않는다

```yaml
# Chapter09/pod.kiada-ssl.configmap-volume-clean.yaml
apiVersion: v1
kind: Pod
metadata:
  name: kiada-ssl
spec:
  volumes:
  - name: envoy-config
    configMap:
      name: kiada-ssl-config
      # envoy.yaml만 선택적으로 마운트하여 불필요한 status-message 파일을 제외
      items:
      - key: envoy.yaml        # ConfigMap의 키
        path: envoy.yaml       # 볼륨 내 파일 경로 (/etc/envoy/envoy.yaml)
  containers:
  - name: kiada
    image: luksa/kiada:0.4
    env:
    - name: POD_NAME
      valueFrom:
        fieldRef:
          fieldPath: metadata.name
    - name: POD_IP
      valueFrom:
        fieldRef:
          fieldPath: status.podIP
    - name: NODE_NAME
      valueFrom:
        fieldRef:
          fieldPath: spec.nodeName
    - name: NODE_IP
      valueFrom:
        fieldRef:
          fieldPath: status.hostIP
    - name: INITIAL_STATUS_MESSAGE
      valueFrom:
        configMapKeyRef:
          name: kiada-ssl-config
          key: status-message
          optional: true
    ports:
    - name: http
      containerPort: 8080
  - name: envoy
    image: luksa/kiada-ssl-proxy:0.1
    volumeMounts:
    - name: envoy-config
      mountPath: /etc/envoy
      readOnly: true
    ports:
    - name: https
      containerPort: 8443
    - name: admin
      containerPort: 9901
```

이 방식으로 하나의 ConfigMap에서 일부 항목은 환경 변수로, 다른 항목은 파일로 노출할 수 있다.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: my-config
data:
  DB_HOST: "localhost"        # ← 환경 변수로 주입
  DB_PORT: "5432"             # ← 환경 변수로 주입
  nginx.conf: |               # ← 파일로 마운트
    server { listen 80; ... }
```

```yaml
spec:
  containers:
  - name: app
    # 일부 항목은 환경 변수로 노출
    env:
    - name: DB_HOST
      valueFrom:
        configMapKeyRef:
          name: my-config
          key: DB_HOST
    - name: DB_PORT
      valueFrom:
        configMapKeyRef:
          name: my-config
          key: DB_PORT
    # 다른 항목은 파일로 노출
    volumeMounts:
    - name: config-vol
      mountPath: /etc/nginx
  volumes:
  - name: config-vol
    configMap:
      name: my-config
      items:                    # ← 특정 항목만 선택
      - key: nginx.conf         # ConfigMap의 이 key만
        path: nginx.conf        # 이 파일명으로 마운트
```

## ConfigMap 업데이트 자동 반영

ConfigMap을 업데이트해도 환경 변수로 주입된 값은 업데이트되지 않는다. 그러나 **`configMap` 볼륨을 사용하여 파일로 주입하면, ConfigMap의 변경 사항이 자동으로 파일에 반영**된다. 파일 업데이트까지 최대 1분 정도 소요될 수 있다.

```bash
kubectl patch cm kiada-ssl-config --type merge -p '{"data":{"status-message":"새로운 상태 메시지"}}'
# configmap/kiada-ssl-config patched

kubectl exec kiada-ssl -c envoy -- cat /etc/envoy/status-message
# 새로운 상태 메시지
```

<br>

# configMap 볼륨의 동작 원리

configMap 볼륨을 실제로 사용하기 전에, 그 동작 방식을 이해해 두지 않으면 예상치 못한 동작을 디버깅하는 데 많은 시간을 소비하게 될 수 있다. 두 가지 주의할 점이 있다: **볼륨 마운트가 기존 파일에 미치는 영향**과 **심볼릭 링크를 이용한 원자적 업데이트 방식**이다.

## 볼륨 마운트가 기존 파일에 미치는 영향

컨테이너 파일시스템의 디렉토리에 볼륨을 마운트하면, 컨테이너 이미지에서 해당 디렉토리에 원래 존재하던 **모든 파일에 접근할 수 없게** 된다. 하위 디렉토리도 마찬가지다.

![configMap 볼륨 마운트 시 기존 파일 가림 효과]({{site.url}}/assets/images/k8s-vol-04-configmap-mount-effect.png){: .align-center}

예를 들어, Unix 시스템에서 중요한 설정 파일이 위치하는 `/etc` 디렉토리에 configMap 볼륨을 마운트하면, ConfigMap이 제공하는 파일만 볼 수 있고 `/etc`에 원래 있어야 할 다른 모든 파일이 숨겨진다. 이 문제는 볼륨 마운트 시 `subPath` 필드를 사용하여 완화할 수 있다.

`subPath`를 사용하면 전체 볼륨을 `/etc`에 마운트하는 대신, `mountPath`와 `subPath` 필드의 조합으로 특정 파일만 마운트할 수 있다.

## 심볼릭 링크를 이용한 원자적(atomic) 업데이트

일부 애플리케이션은 설정 파일의 변경을 감시하고 업데이트가 감지되면 자동으로 설정을 다시 로드한다. 그러나 대용량 파일이나 여러 파일을 사용하는 경우, 모든 업데이트가 완전히 기록되기 전에 변경을 감지할 수 있다. 애플리케이션이 부분적으로만 업데이트된 파일을 읽으면 정상적으로 동작하지 않을 수 있다.

![심볼릭 링크를 이용한 원자적 업데이트 방식]({{site.url}}/assets/images/k8s-vol-04-configmap-atomic-update.png){: .align-center}

Kubernetes는 이를 방지하기 위해 configMap 볼륨의 모든 파일이 **원자적으로(atomically)** 업데이트되도록 보장한다. 이는 심볼릭 파일 링크를 사용하여 달성된다.

```bash
kubectl exec kiada-ssl -c envoy -- ls -lA /etc/envoy
# total 4
# drwxr-xr-x 2 root root 4096 Apr  2 04:44 ..2026_04_02_04_44_46.2464981237
# lrwxrwxrwx 1 root root   32 Apr  2 04:44 ..data -> ..2026_04_02_04_44_46.2464981237
# lrwxrwxrwx 1 root root   17 Apr  2 04:38 envoy.yaml -> ..data/envoy.yaml
# lrwxrwxrwx 1 root root   21 Apr  2 04:38 status-message -> ..data/status-message
```

디렉토리 구조를 해석하면 다음과 같다:

```
..2026_04_02_04_44_46.2464981237/   ← 실제 데이터가 있는 타임스탬프 디렉토리 (스냅샷)
..data →  ..2026_04_02_04_44_46.2464981237   ← 현재 활성 스냅샷을 가리키는 심링크
envoy.yaml → ..data/envoy.yaml              ← 현재 데이터를 가리킴
status-message → ..data/status-message       ← 현재 데이터를 가리킴
```

볼륨에 투영된 ConfigMap 항목들은 `..data`라는 하위 디렉토리 내의 파일 경로를 가리키는 심볼릭 링크이다. `..data` 자체도 심볼릭 링크로, 타임스탬프가 포함된 이름의 디렉토리를 가리킨다. 애플리케이션이 읽는 파일 경로는 두 단계의 연속적인 심볼릭 링크를 통해 실제 파일로 해석된다.

원자적 업데이트는 다음 순서로 이루어진다:

1. ConfigMap이 변경되면 새 타임스탬프 디렉토리 생성 (예: `..2026_04_02_05_00_00.xxx`)
2. 새 데이터를 그 디렉토리에 작성
3. `..data` 심링크를 새 디렉토리로 **한 번에 교체** (symlink swap)
4. 이전 타임스탬프 디렉토리 삭제

타임스탬프 디렉토리는 항상 **하나만** 존재하고, 이전 버전은 남지 않는다.

> **Note:** 볼륨 마운트 정의에 `subPath`를 사용하면 이 메커니즘이 사용되지 않는다. 대신 파일이 대상 디렉토리에 직접 기록되며, ConfigMap을 수정해도 업데이트되지 않는다. 이를 우회하려면, 전체 볼륨을 다른 디렉토리에 마운트하고 원하는 위치에 해당 디렉토리 내 파일을 가리키는 심볼릭 링크를 만들면 된다. 이 심볼릭 링크는 컨테이너 이미지에서 미리 만들어 둘 수 있다.

<br>

# secret 볼륨

Secret은 ConfigMap과 크게 다르지 않으므로, Pod에 `secret` 볼륨을 추가하는 것도 `configMap` 볼륨을 추가하는 것과 거의 동일하다.

## Pod에 secret 볼륨 정의하기

TLS 인증서와 개인 키를 `kiada-ssl` Pod의 `envoy` 컨테이너에 주입하려면, 새로운 `volume`과 `volumeMount`를 정의해야 한다.

- `configMap` 볼륨과 마찬가지로, `defaultMode`와 `mode` 필드로 파일 권한 설정 가능
- `optional` 필드를 `true`로 설정하면 참조하는 Secret이 없어도 Pod가 시작된다
- **차이점은 두 가지뿐**: 볼륨 타입이 `configMap` 대신 `secret`이고, 참조하는 Secret 이름을 `name` 대신 **`secretName`** 필드에 지정한다

```yaml
# Chapter09/pod.kiada-ssl.secret-volume.yaml
apiVersion: v1
kind: Pod
metadata:
  name: kiada-ssl
spec:
  volumes:
  - name: cert-and-key
    secret:
      secretName: kiada-tls
      items:
      - key: tls.crt
        path: example-com.crt
      - key: tls.key
        path: example-com.key
  - name: envoy-config
    configMap:
      name: kiada-ssl-config
      items:
      - key: envoy.yaml
        path: envoy.yaml
  containers:
  - name: kiada
    image: luksa/kiada:0.4
    env:
    - name: POD_NAME
      valueFrom:
        fieldRef:
          fieldPath: metadata.name
    - name: POD_IP
      valueFrom:
        fieldRef:
          fieldPath: status.podIP
    - name: NODE_NAME
      valueFrom:
        fieldRef:
          fieldPath: spec.nodeName
    - name: NODE_IP
      valueFrom:
        fieldRef:
          fieldPath: status.hostIP
    - name: INITIAL_STATUS_MESSAGE
      valueFrom:
        configMapKeyRef:
          name: kiada-ssl-config
          key: status-message
          optional: true
    ports:
    - name: http
      containerPort: 8080
  # 범용 envoyproxy/envoy 이미지로 교체
  - name: envoy
    image: envoyproxy/envoy:v1.31-latest
    volumeMounts:
    - name: cert-and-key
      mountPath: /etc/certs
      readOnly: true
    - name: envoy-config
      mountPath: /etc/envoy
      readOnly: true
    ports:
    - name: https
      containerPort: 8443
    - name: admin
      containerPort: 9901
```

![secret 볼륨과 configMap 볼륨을 함께 사용하는 Pod 구조]({{site.url}}/assets/images/k8s-vol-04-secret-volume-structure.png){: .align-center}

## secret 볼륨의 파일 읽기

`secret` 볼륨을 통해 Secret의 항목을 컨테이너에 주입하면, Secret 오브젝트의 YAML에서는 Base64로 인코딩되어 있지만, 파일로 기록될 때 값이 자동으로 디코딩된다. 애플리케이션이 파일을 읽을 때 별도로 디코딩할 필요가 없다.

```bash
kubectl apply -f pod.kiada-ssl.secret-volume.yaml
# pod/kiada-ssl created

kubectl exec kiada-ssl -c envoy -- cat /etc/certs/example-com.crt
# -----BEGIN CERTIFICATE-----
# MIIFkzCCA3ugAwIBAgIUQhQiuF
# ...
# 6RCfeDoOuVaHo0M+m8Li5MYrVt2YbV0wikmMEoJ9wL8SscMMyd+y
# -----END CERTIFICATE-----
```

> **Note:** `secret` 볼륨의 파일은 인메모리 파일시스템(`tmpfs`)에 저장되므로, 디스크에 기록되지 않아 탈취될 위험이 더 적다.

<br>

# 파일 권한 및 소유권

보안을 강화하려면 `configMap`, 특히 `secret` 볼륨의 파일 권한을 제한하는 것이 좋다. 그러나 권한을 변경하면, 그룹 소유권도 올바르게 설정하지 않는 한 컨테이너 내 프로세스가 파일에 접근하지 못할 수 있다.

## 기본 파일 권한

`secret`과 `configMap` 볼륨의 기본 파일 권한은 `rw-r--r--`(8진수 `0644`)이다.

## defaultMode로 기본 권한 변경

볼륨 내 파일의 기본 권한은 볼륨 정의의 `defaultMode` 필드로 변경할 수 있다.

```yaml
volumes:
- name: cert-and-key
  secret:
    secretName: kiada-tls
    defaultMode: 0740 # rwxr----- (owner: rwx, group: r, others: 없음)
    items:
    - key: tls.crt
      path: example-com.crt
    - key: tls.key
      path: example-com.key
```

> **Note:** YAML 매니페스트에서 파일 권한을 지정할 때, 반드시 **앞에 0을 포함**해야 한다. 이 0은 값이 8진수임을 나타내며, 생략하면 10진수로 해석되어 의도하지 않은 권한이 설정될 수 있다. JSON 매니페스트에서는 10진수 표기를 사용한다. `kubectl get -o yaml`로 확인하면 파일 권한이 10진수로 표시되는데, 예를 들어 420이라는 값은 8진수 `0644`의 10진수 등가값이다.

`secret`이나 `configMap` 볼륨의 파일은 **심볼릭 링크**이다. 심볼릭 링크 자체는 항상 `rwxrwxrwx` 권한을 보여주지만 이는 의미가 없고, 시스템은 대상 파일의 권한을 사용한다. 실제 파일의 권한을 보려면 `ls -lL`로 심볼릭 링크를 따라가야 한다.

## mode로 개별 파일 권한 설정

개별 파일에 대한 권한을 설정하려면, 각 항목의 `key`와 `path` 옆에 `mode` 필드를 지정한다.

```yaml
volumes:
- name: cert-and-key
  secret:
    secretName: kiada-tls
    items:
    - key: tls.key
      path: example-com.key
      mode: 0640 # example-com.key 파일을 rw-r------로 설정
```

## fsGroup으로 그룹 소유권 변경

기본 권한 `rw-r--r--`에서는 others 읽기 권한으로 누구나 파일을 읽을 수 있다. 보안 목적으로 `rw-r-----`(`0640`)로 제한하면, 볼륨 파일의 소유자가 항상 `root:root`이기 때문에 non-root 프로세스가 파일을 읽지 못하게 된다.

```bash
# 현재 프로세스는 envoy 사용자(uid=101)로 실행
kubectl exec kiada-ssl -c envoy -- id envoy
# uid=101(envoy) gid=101(envoy) groups=101(envoy)

# 볼륨 내 파일들은 root 사용자, root 그룹 소유
kubectl exec kiada-ssl -c envoy -- ls -lL /etc/certs
# total 8
# -rw-r--r-- 1 root root 1992 Apr  2 10:35 example-com.crt
# -rw-r--r-- 1 root root 3268 Apr  2 10:35 example-com.key
```

envoy 프로세스(`uid=101`)는 `root` 그룹에 속하지 않으며, `root` 사용자도 아니다. 권한을 `0640`으로 제한하면 파일에 접근할 수 없게 되고, Envoy 프록시는 개인 키 파일을 읽지 못해 시작에 실패한다.

Pod 스펙의 `securityContext.fsGroup` 설정을 통해 이 문제를 해결한다.

- 해당 Pod에 마운트된 **모든 볼륨**의 파일 그룹 소유자를 변경한다
- Pod 내 **모든 컨테이너의 프로세스**에 (기존 그룹에 더해) **supplemental group**으로 추가한다

```yaml
# Chapter09/pod.kiada-ssl.secret-volume-permissions.yaml
apiVersion: v1
kind: Pod
metadata:
  name: kiada-ssl
spec:
  securityContext:
    fsGroup: 101 # 볼륨에 마운트된 파일의 그룹을 변경함
  volumes:
  - name: cert-and-key
    secret:
      secretName: kiada-tls
      items:
      - key: tls.crt
        path: example-com.crt
      - key: tls.key
        path: example-com.key
        mode: 0640
  - name: envoy-config
    configMap:
      name: kiada-ssl-config
      items:
      - key: envoy.yaml
        path: envoy.yaml
  containers:
  - name: kiada
    image: luksa/kiada:0.4
    env:
    - name: POD_NAME
      valueFrom:
        fieldRef:
          fieldPath: metadata.name
    - name: POD_IP
      valueFrom:
        fieldRef:
          fieldPath: status.podIP
    - name: NODE_NAME
      valueFrom:
        fieldRef:
          fieldPath: spec.nodeName
    - name: NODE_IP
      valueFrom:
        fieldRef:
          fieldPath: status.hostIP
    - name: INITIAL_STATUS_MESSAGE
      valueFrom:
        configMapKeyRef:
          name: kiada-ssl-config
          key: status-message
          optional: true
    ports:
    - name: http
      containerPort: 8080
  - name: envoy
    image: envoyproxy/envoy:v1.31-latest
    volumeMounts:
    - name: cert-and-key
      mountPath: /etc/certs
      readOnly: true
    - name: envoy-config
      mountPath: /etc/envoy
      readOnly: true
    ports:
    - name: https
      containerPort: 8443
    - name: admin
      containerPort: 9901
```

볼륨과 파일들은 GID 101인 `envoy` 그룹이 소유하게 되므로, `0640` 권한으로도 envoy 프로세스가 파일을 읽을 수 있다.

```bash
kubectl apply -f pod.kiada-ssl.secret-volume-permissions.yaml
# pod/kiada-ssl created

# 두 파일 모두 그룹이 root -> envoy(101)로 변경됨
kubectl exec kiada-ssl -c envoy -- ls -lL /etc/certs
# total 8
# -rw-r--r-- 1 root envoy 1992 Apr  2 11:14 example-com.crt
# -rw-r----- 1 root envoy 3268 Apr  2 11:14 example-com.key
```

볼륨의 **사용자(user) 소유권**도 변경할 수 있는지 궁금할 수 있다. 현재로서는 **그룹(group) 소유권만 변경** 가능하다. 그 이유는 다음과 같다:

- `fsGroup`은 Linux의 supplemental group 메커니즘을 활용한다. 서로 다른 UID로 실행되는 여러 컨테이너가 **같은 그룹을 공유**하면서 볼륨 파일에 접근할 수 있다
- 파일의 user 소유자를 임의로 변경하면 보안 경계가 무너질 수 있다
- 실무적으로 `fsGroup` + 적절한 파일 권한(`0640` 등)이면 대부분의 접근 제어 시나리오를 커버할 수 있다
- 정말로 특정 UID로 파일을 소유해야 하는 경우, `securityContext.runAsUser`로 컨테이너 프로세스의 실행 UID를 변경하거나, initContainer에서 `chown`을 수행하는 방법을 사용할 수 있다

<br>

# downwardAPI 볼륨

ConfigMap과 Secret과 마찬가지로, Pod 메타데이터도 `downwardAPI` 볼륨 타입을 사용하여 컨테이너의 파일시스템에 파일로 프로젝션할 수 있다.

## Pod에 downwardAPI 볼륨 추가하기

컨테이너 내부의 파일에 Pod 이름을 제공해야 한다고 가정하자. 아래 매니페스트는 Pod 이름이 `/etc/pod/name.txt` 파일에 기록되도록 하는 예시이다.

```yaml
volumes:
- name: metadata
  # 볼륨에 파일 하나가 생성됨
  # 파일 이름은 name.txt이며, Pod의 이름을 담고 있음
  downwardAPI:
    items:
    - path: name.txt
      fieldRef:
        fieldPath: metadata.name
containers:
- name: foo
  ...
  # 이 볼륨은 컨테이너의 /etc/pod 경로에 마운트됨
  volumeMounts:
  - name: metadata
    mountPath: /etc/pod
```

`configMap` 및 `secret` 볼륨과 마찬가지로, `defaultMode` 필드로 기본 파일 권한을, `mode` 필드로 개별 파일 권한을 설정할 수 있다.

## fieldRef와 resourceFieldRef

Downward API 볼륨에 프로젝션되는 각 항목은 Pod 오브젝트의 필드를 참조하는 `fieldRef` 또는 컨테이너의 리소스 필드를 참조하는 `resourceFieldRef`를 사용한다.

리소스 필드의 경우, **볼륨은 Pod 레벨에서 정의되므로 어느 컨테이너의 리소스를 참조하는지 명확하지 않기 때문에** `containerName` 필드를 반드시 지정해야 한다. 환경 변수와 마찬가지로, `divisor`를 지정하여 값을 원하는 단위로 변환할 수 있다.

```yaml
volumes:
- name: pod-info
  downwardAPI:
    items:
    # fieldRef: Pod 오브젝트의 필드 참조
    - path: labels
      fieldRef:
        fieldPath: metadata.labels
    - path: annotations
      fieldRef:
        fieldPath: metadata.annotations
    # resourceFieldRef: 컨테이너의 리소스 필드 참조
    # 볼륨은 Pod 레벨이므로 containerName 필수
    - path: cpu-limit
      resourceFieldRef:
        containerName: my-app  # 어느 컨테이너의 리소스인지 명시
        resource: limits.cpu
        divisor: 1m            # 밀리코어 단위로 변환
    - path: memory-limit
      resourceFieldRef:
        containerName: my-app
        resource: limits.memory
        divisor: 1Mi           # MiB 단위로 변환
```

<br>

# projected 볼륨

지금까지 ConfigMap, Secret, 그리고 Pod 오브젝트 자체의 값을 주입하기 위해 세 가지 볼륨 타입을 사용하는 방법을 봤다. `volumeMount` 정의에서 `subPath` 필드를 사용하지 않는 한, 서로 다른 소스의 파일들을 **동일한 파일 디렉토리에 주입**할 수 없다. 이때 `projected` 볼륨을 사용한다.

## 여러 소스를 하나로 합치기

`projected` 볼륨을 사용하면 **여러 ConfigMap, Secret, Downward API의 정보를 하나의 볼륨으로 합칠 수 있다**. `configMap`, `secret`, `downwardAPI` 볼륨과 동일한 기능을 제공하면서, 하나의 볼륨에 여러 소스를 모을 수 있는 것이 핵심이다.

```yaml
# 예시: ConfigMap + Secret + Downward API를 하나의 projected 볼륨으로 합치기
volumes:
- name: all-in-one
  projected:
    sources:
    - configMap:
        name: my-config
        items:
        - key: app.conf
          path: config/app.conf
    - secret:
        name: my-secret
        items:
        - key: tls.crt
          path: certs/tls.crt
        - key: tls.key
          path: certs/tls.key
          mode: 0640
    - downwardAPI:
        items:
        - path: metadata/pod-name
          fieldRef:
            fieldPath: metadata.name
        - path: metadata/pod-namespace
          fieldRef:
            fieldPath: metadata.namespace
containers:
- name: app
  image: my-app:latest
  volumeMounts:
  - name: all-in-one
    mountPath: /etc/app
    readOnly: true
# 결과 디렉토리 구조:
# /etc/app/
#   config/app.conf         ← ConfigMap
#   certs/tls.crt           ← Secret
#   certs/tls.key           ← Secret
#   metadata/pod-name       ← Downward API
#   metadata/pod-namespace  ← Downward API
```

![projected 볼륨으로 여러 소스를 하나의 디렉토리에 합치기]({{site.url}}/assets/images/k8s-vol-04-projected-volume.png){: .align-center}

> **Note:** `projected` 볼륨은 Pod의 ServiceAccount와 연결된 토큰도 노출할 수 있다. 각 Pod는 ServiceAccount에 연결되어 있으며, Pod는 이 토큰을 사용하여 Kubernetes API에 인증할 수 있다.

## kiada-ssl Pod에 projected 볼륨 적용

kiada-ssl Pod의 envoy 컨테이너에 projected 볼륨을 적용해 보자. 이전 버전에서는 두 개의 볼륨을 사용했다.

- **이전 구조 (볼륨 2개, 마운트 경로 2개)**:
  - `secret` 볼륨 (`cert-and-key`) → `/etc/certs`에 마운트
  - `configMap` 볼륨 (`envoy-config`) → `/etc/envoy`에 마운트
- **새 구조 (projected 볼륨 1개, 마운트 경로 1개)**:
  - `projected` 볼륨 (`etc-envoy`) → `/etc/envoy` **하나에** 모두 마운트

먼저 `kiada-ssl-config` ConfigMap의 envoy.yaml에서 TLS 인증서 경로를 변경해야 한다.

```bash
kubectl edit configmap kiada-ssl-config
# certificate_chain:
#     filename: "/etc/envoy/certs/example-com.crt"   # /etc/certs → /etc/envoy/certs로 변경
# private_key:
#     filename: "/etc/envoy/certs/example-com.key"    # /etc/certs → /etc/envoy/certs로 변경
```

<details markdown="1">
<summary>projected 볼륨을 사용하는 Pod 매니페스트 (pod.kiada-ssl.projected-volume.yaml)</summary>

```yaml
# Chapter09/pod.kiada-ssl.projected-volume.yaml
apiVersion: v1
kind: Pod
metadata:
  name: kiada-ssl
spec:
  securityContext:
    fsGroup: 101
  volumes:
  - name: etc-envoy
    # 하나의 projected 타입 볼륨만 필요
    projected:
      # 모아서 보여 줄 파일 소스 목록
      sources:
      - configMap:
          name: kiada-ssl-config
          items:
          - key: envoy.yaml
            path: envoy.yaml
      - secret:
          name: kiada-tls
          items:
          - key: tls.crt
            path: certs/example-com.crt
          - key: tls.key
            path: certs/example-com.key
            mode: 0640
  containers:
  - name: kiada
    image: luksa/kiada:0.4
    env:
    - name: POD_NAME
      valueFrom:
        fieldRef:
          fieldPath: metadata.name
    - name: POD_IP
      valueFrom:
        fieldRef:
          fieldPath: status.podIP
    - name: NODE_NAME
      valueFrom:
        fieldRef:
          fieldPath: spec.nodeName
    - name: NODE_IP
      valueFrom:
        fieldRef:
          fieldPath: status.hostIP
    - name: INITIAL_STATUS_MESSAGE
      valueFrom:
        configMapKeyRef:
          name: kiada-ssl-config
          key: status-message
          optional: true
    ports:
    - name: http
      containerPort: 8080
  - name: envoy
    image: envoyproxy/envoy:v1.31-latest
    # 하나의 볼륨만 마운트하면 됨
    volumeMounts:
    - name: etc-envoy
      mountPath: /etc/envoy
      readOnly: true
    ports:
    - name: https
      containerPort: 8443
    - name: admin
      containerPort: 9901
```

</details>

projected 볼륨의 소스 정의는 이전 섹션에서 만든 `configMap` 및 `secret` 볼륨과 크게 다르지 않다. 다른 볼륨에서 배운 모든 것이 그대로 적용되지만, 이제는 하나의 볼륨에 여러 소스의 정보를 채울 수 있다.

```bash
kubectl apply -f pod.kiada-ssl.projected-volume.yaml
# pod/kiada-ssl created

kubectl exec kiada-ssl -c envoy -- ls -LR /etc/envoy
# /etc/envoy:       ← ConfigMap에서 온 파일을 포함
# certs
# envoy.yaml
#
# /etc/envoy/certs: ← Secret에서 온 파일을 포함
# example-com.crt
# example-com.key
```

## kube-api-access 볼륨

Pod를 자세히 살펴보면, 모든 Pod에 **내장(built-in) projected 볼륨**이 자동으로 추가되어 모든 컨테이너에 마운트되는 것을 알 수 있다.

```bash
kubectl get pod kiada-ssl -o yaml | yq .spec.volumes
```

```yaml
- name: etc-envoy
  projected:
    defaultMode: 420
    sources:
      - configMap:
          items:
            - key: envoy.yaml
              path: envoy.yaml
          name: kiada-ssl-config
      - secret:
          items:
            - key: tls.crt
              path: certs/example-com.crt
            - key: tls.key
              mode: 416
              path: certs/example-com.key
          name: kiada-tls
- name: kube-api-access-xstt9     # 자동 생성된 built-in projected 볼륨
  projected:
    defaultMode: 420
    sources:
      - serviceAccountToken:      # ServiceAccount 토큰 (3607초 후 만료)
          expirationSeconds: 3607
          path: token
      - configMap:                # 클러스터 CA 인증서
          items:
            - key: ca.crt
              path: ca.crt
          name: kube-root-ca.crt
      - downwardAPI:              # Pod의 네임스페이스
          items:
            - fieldRef:
                apiVersion: v1
                fieldPath: metadata.namespace
              path: namespace
```

볼륨 이름 `kube-api-access`에서 알 수 있듯이, 이 볼륨은 **Pod가 Kubernetes API에 접근하는 데 필요한 정보**를 담고 있다. 세 개의 파일이 포함되어 있으며, 각각 다른 소스에서 가져온다:

| 파일 | 소스 | 설명 |
|------|------|------|
| `token` | `serviceAccountToken` | Pod의 ServiceAccount에 대한 JWT 토큰. `expirationSeconds: 3607`으로 설정되어 kubelet이 만료 전에 자동 갱신한다. API 호출 시 `Authorization: Bearer <토큰>` 헤더로 인증에 사용된다 |
| `ca.crt` | `configMap` (`kube-root-ca.crt`) | 클러스터 루트 CA 인증서. API 서버의 HTTPS 인증서를 검증할 때 사용한다 |
| `namespace` | `downwardAPI` | Pod가 속한 네임스페이스 이름. 클라이언트 라이브러리가 API 호출 시 네임스페이스를 알아야 하므로 자동 제공된다 |

이 정보들을 사용하여 컨테이너 내부에서 API Server를 호출할 수 있다:

```bash
# 컨테이너 내부에서
TOKEN=$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)
NAMESPACE=$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)
CACERT=/var/run/secrets/kubernetes.io/serviceaccount/ca.crt

curl --cacert $CACERT \
     -H "Authorization: Bearer $TOKEN" \
     https://kubernetes.default.svc/api/v1/namespaces/$NAMESPACE/pods
```

> **Note:** `kube-api-access` projected 볼륨은 Pod 스펙에서 `automountServiceAccountToken: false`로 설정하여 개별 Pod에 대해 비활성화할 수 있다. 대부분의 Pod는 Kubernetes API에 접근할 필요가 없으므로, **최소 권한 원칙(principle of least privilege)**에 따라 이 설정을 적용하거나 ServiceAccount 자체에서 구성하는 것이 좋다.

<br>

# 기타 볼륨 타입

`kubectl explain pod.spec.volumes` 명령을 실행하면, 이 글에서 다루지 않은 많은 볼륨 타입 목록을 확인할 수 있다. 주요 타입은 다음과 같다:

- **`persistentVolumeClaim`** — PersistentVolumeClaim 리소스를 참조하여 Pod가 영구 스토리지를 요청할 수 있게 한다. Kubernetes는 기존 PersistentVolume에 바인딩하거나 새로운 PV를 생성한다
- **`ephemeral`** — Pod의 수명 동안만 존재하는 임시 볼륨을 생성한다. PersistentVolumeClaim의 인라인 템플릿을 정의하며, Kubernetes가 이를 사용해 PV를 동적으로 프로비저닝하고 바인딩한다. 기능적으로는 `persistentVolumeClaim` 볼륨과 동일하지만, 단일 Pod 인스턴스 전용으로 사용된다. Pod가 삭제되면 볼륨도 자동으로 삭제된다
- **`awsElasticBlockStore`, `azureDisk`, `gcePersistentDisk` 등** — 이전에는 스토리지 기술이 제공하는 볼륨을 직접 참조하는 데 사용되었으나, 대부분 **deprecated** 되었다. 이제는 `persistentVolumeClaim`이나 `ephemeral` 볼륨 타입을 통해 CSI 드라이버로 프로비저닝하는 방식을 사용해야 한다
- **`csi`** — Container Storage Interface의 약자로, 별도의 PVC나 PV 없이 Pod 매니페스트에서 직접 CSI 드라이버를 구성할 수 있는 볼륨 타입이다. 단, 이 방식을 지원하는 CSI 드라이버는 일부에 한정된다. 대부분의 경우 `persistentVolumeClaim`이나 `ephemeral` 볼륨 사용이 권장된다

이 글에서 다룬 것은 Pod의 라이프사이클을 넘어 지속되지 않는 **임시(ephemeral) 볼륨**에 해당한다. 영구 스토리지는 훨씬 넓고 복잡한 주제이므로, 별도로 다룬다.

<br>

# 정리

- `configMap` 볼륨은 ConfigMap 항목을 파일로 컨테이너에 주입한다. ConfigMap 업데이트 시 심볼릭 링크 교체를 통해 원자적으로 자동 반영된다 (`subPath` 사용 시 제외)
- `secret` 볼륨은 `configMap` 볼륨과 거의 동일하며, `tmpfs`(인메모리)에 저장되어 보안성이 높다. `secretName` 필드로 Secret을 참조한다
- `downwardAPI` 볼륨은 Pod 메타데이터와 컨테이너 리소스 정보를 파일로 프로젝션한다. `resourceFieldRef` 사용 시 `containerName`을 반드시 지정해야 한다
- `projected` 볼륨은 ConfigMap, Secret, Downward API 등 여러 소스의 정보를 하나의 볼륨으로 합칠 수 있다
- 모든 Pod에는 `kube-api-access` projected 볼륨이 자동 주입되어 API 인증 토큰, CA 인증서, 네임스페이스 정보를 제공한다. 불필요하면 `automountServiceAccountToken: false`로 비활성화한다
- 파일 권한은 `defaultMode`/`mode`로 설정하고, non-root 프로세스의 접근은 `securityContext.fsGroup`으로 그룹 소유권을 변경하여 해결한다
- 그 외 많은 볼륨 타입은 더 이상 Pod에 직접 구성하지 않고, `persistentVolumeClaim`, `ephemeral`, 또는 `csi` 볼륨을 사용해야 한다

<br>
