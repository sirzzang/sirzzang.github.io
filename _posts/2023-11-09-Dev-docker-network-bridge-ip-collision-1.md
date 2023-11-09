---
title:  "[Docker] Docker Bridge Network 사용 시 IP 대역대 충돌 - 1. 문제"
excerpt: Docker Bridge Network를 사용해 컨테이너를 배포할 때, IP 대역 충돌에 주의해야 한다.
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Docker
  - Docker Container
  - Docker Compose
  - Docker Network
  - Bridge
---

 회사에서 Docker를 이용해 컨테이너를 배포한 뒤, Bridge Network 사용으로 인해 발생했던 문제 및 그 원인을 기록하고자 한다. 인증, 인가를 담당하는 Account 서버에서는 오픈소스 LDAP 서버 구현체인 [OpenLDAP](https://www.openldap.org/)을 사용하는데, OpenLDAP 서버를 팀 내 개발 서버에 컨테이너로 배포하고자 했을 때 겪은 문제이다.

<br>

# 개요

 팀 내에서 사용하고 있는 개발 서버는 Dell R550, R650 총 두 대로, 회사 내 사설망의 `172.42.X.X` 대역에서 다음과 같은 IP를 할당 받아 사용하고 있다.

- R550: `172.42.10.112`
- R650: `172.42.10.110`

  내가 사용하고 있는 PC는 회사 내 사설망의 `172.22.X.X` 대역에서 아래의 IP를 할당 받아 사용하고 있다.

- `172.22.10.119`

  개발은 개인 PC에서 진행하며, 개발이 완료된 서비스를 팀 서버 R550에 배포한다. 개인 PC에서 SSH를 이용해 팀 서버에 접속한다.

<br>

# 문제

OpenLDAP 컨테이너를 R550 서버에 배포한 뒤, 갑자기 개인 PC에서 R550 서버로 SSH 접속이 되지 않는 문제가 발생했다. 문제를 인지한 후, R650 서버와 R550 서버에 핑을 날려 봤는데, R550 서버에만 가지 않는다.

![docker-bridge-ping-error]({{site.url}}/assets/images/docker-bridge-ping-error.png)

 컨테이너를 배포하는 과정에서 문제가 있어서 서버를 죽인 것인가(~~*그랬다면 큰일이다.....*~~) 했는데, 로컬에서 R650 서버로 SSH 접속한 뒤, R650 서버에서 R550 서버로 SSH 접속해 본 결과, 문제가 없이 접속되는 것을 보니 서버가 죽지는 않았다.

![r550-not-dead-1]({{site.url}}/assets/images/r550-not-dead-1.png)

![r550-not-dead-2]({{site.url}}/assets/images/r550-not-dead-2.png)

<center><sup>정리하다 보니, 로그인이 되는 시점의 터미널 출력에서부터 문제의 원인을 파악할 수 있었다(...)</sup></center>



네트워크에 뭔가 문제가 생긴 것 같긴 하고, 그게 Docker Container 배포와 관련된 것 같은데, 원인이 무엇인지 쉽사리 파악할 수 없었다.



<br>

# 분석

 팀장님께 도움을 청해 OpenLDAP 컨테이너가 실행되며 생성된 Bridge 네트워크 때문임을 알 수 있었다.





## 배포에 사용한 Docker Compose 파일





## 서버 네트워크 확인





## 원인



