---
title:  "[Docker] Docker Private Registry 구축"
excerpt: 간단한 도커 사설 저장소 구축하기
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - docker
  - private registry
  - joxit
---



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

