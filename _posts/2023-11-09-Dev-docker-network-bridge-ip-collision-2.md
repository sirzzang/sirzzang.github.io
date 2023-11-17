---
title:  "[Docker] Docker Bridge Network 사용 시 IP 충돌 - 2. 해결"
excerpt: Docker Bridge Network를 사용해 컨테이너를 배포하며 생기는 IP 대역대 충돌 문제를 해결하는 방법
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

이 문제를 해결하기 위한 방법은 크게 Docker Network를 Bridge 모드로 사용하는 방법과 Host 모드로 사용하는 방법으로 나누어 볼 수 있다.

- Bridge 모드로 사용할 경우, Docker Container가 연결되는 Docker Bridge Network 대역대가 충돌 가능성이 있는 IP 대역대가 되지 않도록 조정해 주면 된다.

- Host 모드로 사용할 경우, Docker Container가 호스트 네트워크 스택을 사용하기 때문에, 그냥 실행해 주면 된다.

  > *참고*: Host IP 충돌 가능성은 없을까?
  >
  > 요청하는 Host와 Docker Container가 실행되는 Host의 IP가 겹치면 어떻게 하나 하는 생각을 할 수 있을 텐데, 그럴 일은 거의 없어 보인다. 
  >
  > - 요청 Host와 Docker Host가 같은 사설망 대역에 있을 경우, 애초에 같은 IP가 할당될 수가 없다. 만약 충돌이 났다면, 인프라 차원에서 설정이 잘못된 것이다.
  > - 요청 Host와 Docker Host가 서로 다른 사설망에 있고, 우연히 각 사설망에서 두 호스트가 같은 IP를 쓰고 있다고 한다면, 그 상황에 맞는 라우팅 혹은 게이트웨이 설정이 되어 있을 것이다. 



이를 바탕으로, 문제를 해결할 수 있는 방법을 다음과 같이 정리해 볼 수 있다.

- Bridge 모드 사용
  - Docker Container 재실행(1안)
  - Bridge Network 지정해서 실행
    - Bridge Network를 직접 생성한 후, Docker Compose에서 해당 네트워크를 이용하여 Container를 실행하도록 지정(2안)
    - Docker Compose가 Docker Container를 실행할 때 사용할 Bridge Network 대역을 직접 지정(3안)
  - Bridge Network 대역대 변경(4안)
- Host 모드 사용(5안)

<br>

 ## 1안



## 2안



## 3안



## 4안



## 5안





<br>

# 결론



 개발 환경이었기에 해프닝으로 치고 넘어갈 수 있지만, 실제 운영 환경에서는 큰 문제가 될 수도 있다. 요컨대, 이렇게 Bridge Network 대역이 클라이언트의 IP 대역과 동일하게 Docker Container가 배포되었다고 해 보자. 클라이언트가 보낸 요청에 대한 응답이 클라이언트에게 돌아가지 않을 수도 있고, 클라이언트가 서버에 접속도 못할 수 있다. 아찔한 일이 아닐 수 없다.

