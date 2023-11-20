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

<br>

 이전 포스트에 이어, Docker를 이용해 컨테이너를 배포할 때, Bridge Network를 사용하는 경우 발생할 수 있는 IP 대역대 충돌 문제를 해결한 과정을 기록하고자 한다.

<br>

# TL;DR



결과적으로, 위 문제 상황에서는 Docker Compose를 통해 OpenLDAP 컨테이너를 실행할 때마다 Bridge 타입의 새로운 Docker Network가 생성되었고, 하필 문제가 발생한 시점에는 Docker 엔진의 할당 원리에 의해 차례로 IP 대역이 할당되다가 `172.22.0.0/16` 대역이 할당된 것이다. *공교롭게도* 이 타이밍에 할당된 IP 대역이 로컬 PC가 사용하는 IP 주소 대역과 일치해 버렸다. 그래서 로컬 PC의 요청 패킷에 대한 응답 패킷은 되돌아 오지 못하고, R550 서버 내부에 격리되어 생성된 Docker Network로 들어가 버린다. 

 참으로 공교로운 타이밍이다. 그러나 Docker Network의 동작 원리에 대해 알고 있었다면, 문제의 원인을 짚어내는 게 그렇게 어렵지는 않았을 것이라는 생각도 든다. Docker Container를 중지한 뒤, 다시 SSH 접속을 시도하면, 문제 없이 잘 동작함을 확인할 수 있다.

![stop-openldap-container]({{site.url}}/assets/images/stop-openldap-container.png){: .align-center}

![ping-after-docker-container-down]({{site.url}}/assets/images/ping-after-docker-container-down.png){: .align-center}

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

Docker Container를 다시 실행하면 된다. Docker 엔진이 IP 대역대를 차례로 할당하기 때문에, 다시 실행하면 `172.22.X.X`와 겹치지 않는 다음 대역대의 네트워크가 할당된다.

새롭게 컨테이너를 실행했을 때, 아까와 동일하게 `XXXX-openldap_default` 네트워크가 생성되는 것을 확인할 수 있다.

![restart-docker-container]({{site.url}}/assets/images/restart-docker-container.png){: .align-center}{:width="500"}

새롭게 사용하고 있는 Docker Brdige 네트워크를 검사해 보면, 해당 브릿지 네트워크가 `172.23.0.0/16` IP 대역대를 사용하고 있음을 확인할 수 있다.

```bash
$ docker network inspect 160ca
[
    {
        "Name": "gaia-openldap_default",
        "Id": "160ca8630a4247f6f0fa316e5274355bff45c75517a5032cfbde3701ab0a07e5",
        "Created": "2023-11-08T05:09:20.161718881Z",
        "Scope": "local",
        "Driver": "bridge",
        "EnableIPv6": false,
        "IPAM": {
            "Driver": "default",
            "Options": null,
            "Config": [
                {
                    "Subnet": "172.23.0.0/16", # 겹치지 않는 네트워크 대역대
                    "Gateway": "172.23.0.1"
                }
            ]
        },
        "Internal": false,
        "Attachable": false,
        "Ingress": false,
        "ConfigFrom": {
            "Network": ""
        },
        "ConfigOnly": false,
        "Containers": {
            "e6724619d39bc00357044f7dc5939d0bc09170d27a5c777e34fdad4e5abcbe0d": {
                "Name": "openldap",
                "EndpointID": "b705a1af644b3a78336214a0b833dbf3e871df9cba3fa5711cf29ea224428bba",
                "MacAddress": "02:42:ac:17:00:02",
                "IPv4Address": "172.23.0.2/16",
                "IPv6Address": ""
            }
        },
        "Options": {},
        "Labels": {
            "com.docker.compose.network": "default",
            "com.docker.compose.project": "gaia-openldap",
            "com.docker.compose.version": "2.21.0"
        }
    }
]
```



<br>

로컬 PC의 IP 대역대와 겹치지 않는다. 문제가 해결되었는지 확인하기 위해, 로컬 PC에서 SSH 접속을 시도해 본다.

![restart-docker-container-result]({{site.url}}/assets/images/restart-docker-container-result.png){: .align-center}{: .width="500"}

문제는 해결되었지만, 별로 좋은 해결책은 아니다. 어쩌다가 운 나쁘게 문제가 발생했던 것처럼, 어쩌다가 운 좋게 얻어 걸릴 수도 있는 방법이다.

<br>





## 2안



## 3안



## 4안



## 5안





<br>

# 결론



 개발 환경이었기에 해프닝으로 치고 넘어갈 수 있지만, 실제 운영 환경에서는 큰 문제가 될 수도 있다. 요컨대, 이렇게 Bridge Network 대역이 클라이언트의 IP 대역과 동일하게 Docker Container가 배포되었다고 해 보자. 클라이언트가 보낸 요청에 대한 응답이 클라이언트에게 돌아가지 않을 수도 있고, 클라이언트가 서버에 접속도 못할 수 있다. 아찔한 일이 아닐 수 없다.

 참으로 공교로운 타이밍이다. 그러나 Docker Network의 동작 원리에 대해 알고 있었다면, 문제의 원인을 짚어내는 게 그렇게 어렵지는 않았을 것이라는 생각도 든다.
