---
title:  "[Docker] Docker Bridge Network 사용 시 IP 대역대 충돌 - 2. 해결"
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

 이전 포스트에 이어, Docker를 이용해 컨테이너를 배포할 때, Bridge Network를 사용하는 경우 발생할 수 있는 IP 대역대 충돌 문제를 해결한 과정을 기록하고자 한다.

<br>

# 해결

해결 방법은 크게 Network를 Bridge 모드로 사용하는 방법과 Host 모드로 사용하는 방법으로 나누어 볼 수 있다.

- Bridge 모드 사용
  - Docker Container 재실행(1안)
  - Bridge Network 지정해서 실행
    - Bridge Network를 직접 생성한 후, Docker Compose에서 해당 네트워크를 이용하여 Container를 실행하도록 지정(2안)
    - Docker Compose가 Docker Container를 실행할 때 사용할 Bridge Network 대역을 직접 지정(3안)
  - Bridge Network 대역대 변경(4안)
- Host 모드 사용(5안)

 ## 1안



## 2안



## 3안



## 4안



## 5안





<br>

# 결론



개발 환경이었기에 해프닝으로 치고 넘어갈 수 있지만, 실제 운영 환경에서는 큰 문제가 될 수도 있다. 요컨대, 이렇게 Bridge Network 대역이 클라이언트의 IP 대역과 동일하게 Docker Container가 배포되었다고 해 보자. 클라이언트가 보낸 요청에 대한 응답이 클라이언트에게 돌아가지 않을 수도 있고, 클라이언트가 서버에 접속도 못할 수 있다. 아찔한 일이 아닐 수 없다.

