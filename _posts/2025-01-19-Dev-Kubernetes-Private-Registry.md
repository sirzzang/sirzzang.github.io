---
title:  "[Kubernetes] Kubernetes 클러스터 docker private registry 사용 설정"
excerpt: K3s 클러스터에서 docker private registry를 사용하기
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - K8s
  - K3s
  - Rancher
  - docker
  - private registry
  - jot
---



<br>

- K3s 클러스터
- rancher
- docker private registry





<br>

# Docker Private Registry 구축



- [docker private registry](https://hub.docker.com/_/registry): Docker에서 공개한 레포지토리 공식 이미지
- [joxit docker registry ui](https://github.com/Joxit/docker-registry-ui): 간단한 오픈 소스 Docker Registry UI

<br>

```yaml
version: '3.8'

services:
  registry-ui:
    image: joxit/docker-registry-ui:2.5.2
    restart: always
    ports:
      - 30100:80
    environment:
      - SINGLE_REGISTRY=true
      - REGISTRY_TITLE=Docker Registry UI
      - DELETE_IMAGES=true
      - SHOW_CONTENT_DIGEST=true
      - NGINX_PROXY_PASS_URL=http://registry-server:5000
      - SHOW_CATALOG_NB_TAGS=true
      - CATALOG_MIN_BRANCHES=1
      - CATALOG_MAX_BRANCHES=1
      - TAGLIST_PAGE_SIZE=100
      - REGISTRY_SECURED=false
      - CATALOG_ELEMENTS_LIMIT=1000
    container_name: registry-ui

  registry-server:
    image: registry:2.8.2
    restart: always
    ports:
      - 5000:5000
    environment:
      REGISTRY_HTTP_HEADERS_Access-Control-Allow-Origin: '[http://registry-ui]'
      REGISTRY_HTTP_HEADERS_Access-Control-Allow-Methods: '[HEAD,GET,OPTIONS,DELETE]'
      REGISTRY_HTTP_HEADERS_Access-Control-Allow-Credentials: '[true]'
      REGISTRY_HTTP_HEADERS_Access-Control-Allow-Headers: '[Authorization,Accept,Cache-Control]'
      REGISTRY_HTTP_HEADERS_Access-Control-Expose-Headers: '[Docker-Content-Digest]'
      REGISTRY_STORAGE_DELETE_ENABLED: true
    volumes:
      - /mnt/sda/registry/data:/var/lib/registry
    container_name: registry-server

```





<br>

# K3s 사용 설정

- /etc/hosts: docker private registry 도메인명 설정
- /etc/docker/daemon.json: docker 설정 파일 변경
- /etc/rancher/k3s/registries.yaml: K3s registry 클러스터 registry 설정 파일 변경



<br>

## /etc/hosts

클러스터 노드 내 `/etc/hosts` 파일에 private docker registry 도메인에 대한 노드 IP에 대한 매핑 추가

```sh
127.0.0.1       localhost
127.0.1.1       <host-name>
172.20.10.231   <registry-domain>

# The following lines are desirable for IPv6 capable hosts
::1     ip6-localhost ip6-loopback
fe00::0 ip6-localnet
ff00::0 ip6-mcastprefix
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters
```

- `172.20.10.231   <registry-domain>`
  - `<registry-domain>`을 내부 IP로 직접 resolve 하도록 custom mapping 지정
  - 호스트 내에서 `<registry-domain>`이 오면 public DNS를 거치지 않고 클러스터 내 private registry 노드 IP로 resolve하기 위함
    - 이 설정이 없으면 public DNS를 거치거나 잘못된 주소를 찾을 수 있음
- K3s 클러스터 내 모든 노드에서 동일하게 설정해야 함

<br>

## /etc/docker/daemon.json

Docker 엔진 설정 파일을 수정해 private registry와 네트워킹 환경을 정의

```json
{
    "bip": "150.15.15.1/24",
    "default-address-pools": [
        {
            "base": "150.15.15.1/16",
            "size": 24
        }
    ],
    "default-runtime": "nvidia",
    "insecure-registries": [
        "<registry-domain>:<registry-port>"
    ],
    "registry-mirrors": [
        "<registry-domain>:<registry-port>"
    ],
    "runtimes": {
        "nvidia": {
            "args": [],
            "path": "/usr/local/nvidia/toolkit/nvidia-container-runtime"
        },
        "nvidia-cdi": {
            "args": [],
            "path": "/usr/local/nvidia/toolkit/nvidia-container-runtime.cdi"
        },
        "nvidia-legacy": {
            "args": [],
            "path": "/usr/local/nvidia/toolkit/nvidia-container-runtime.legacy"
        }
    }
}

```

- `bip`, `default-address-pools`
  - Docker bridge 네트워크와 기본 네트워크 풀을 직접 지정 (기본 `172.17.0.0/16` 과 충돌 방지)
- `default-runtime`
  - NVIDIA GPU가 있는 환경에서 기본 runtime을 `nvidia`로 지정
- `insecure-registries`
  - `<registry-domain>:<registry-port>` 연결 시 TLS 인증서 검증을 생략
  - HTTPS 인증서를 적용하지 않았거나 self-signed 인증서를 사용하는 경우 반드시 필요
- `registry-mirrors`
  - 기본 Docker Hub 대신 private registry를 이미지 pull 시도 우선 경로로 사용

<br>



## /etc/rancher/k3s/registries.yaml

K3s는 내부적으로 containerd를 사용하므로, 해당 컨테이너 런타임에서 사용할 registry 설정을 별도로 지정

```yaml
mirrors:
  "docker.io":
    endpoint:
      - "http://<registry-domain>:<registry-port>"

configs:
  "<registry-domain>:<registry-port>":
    tls:
      insecure_skip_verify: true

```

- `mirrors` : K3s 클러스터 내 docker 이미지 미러링 설정
  - `docker.io`(Docker Hub) 요청을 private registry로 미러링

- `configs.tls.insecure_skip_verify`
  - self-signed 또는 HTTP 기반 registry의 인증서 검증을 생략







<br>

# 결론

위 설정을 적용하면 K3s 클러스터 내에서 Docker 이미지 pull 시, **private registry**를 사용할 수 있음

- `/etc/hosts` → 도메인 해석 문제 해결
- `/etc/docker/daemon.json` → Docker 엔진이 private registry 인식
- `/etc/rancher/k3s/registries.yaml` → K3s(cluster-level) containerd 설정

<br>

사내 클러스터 환경이기 때문에 아직 적용하지 않았으나, 추후 운영 시에는 가능하다면 private registry에 대해 HTTPS + 유효한 TLS 인증서를 사용하는 것이 안전할 것으로 보임

