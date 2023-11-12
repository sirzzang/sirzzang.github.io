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

 팀 내에서 사용하고 있는 개발 서버는 Dell R550, R650 총 두 대로, 회사 내 사설망의 `172.42.10.X` 대역에서 다음과 같은 IP를 할당 받아 사용하고 있다.

- R550: `172.42.10.112`
- R650: `172.42.10.110`

내가 사용하고 있는 PC는 회사 내 사설망의 `172.22.10.X` 대역에서 아래의 IP를 할당 받아 사용하고 있다.

- `172.22.10.119`

개발은 개인 PC에서 진행하며, 개발이 완료된 서비스를 팀 서버 R550에 배포한다. 개인 PC에서 SSH를 이용해 팀 서버에 접속한다.



# 문제

OpenLDAP 컨테이너를 R550 서버에 배포한 뒤, 갑자기 개인 PC에서 R550 서버로 SSH 접속이 되지 않는 문제가 발생했다. 문제를 인지한 후, R650 서버와 R550 서버에 핑을 날려 봤는데, R550 서버에만 가지 않는다.

![docker-bridge-ping-error]({{site.url}}/assets/images/docker-bridge-ping-error.png){: .align-center}

 컨테이너를 배포하는 과정에서 문제가 있어서 서버를 죽인 것인가(...) 했는데, 로컬에서 R650 서버로 SSH 접속한 뒤, R650 서버에서 R550 서버로 SSH 접속해 본 결과, 문제가 없이 접속되는 것을 보니 서버가 죽지는 않았다.

![r550-not-dead-1]({{site.url}}/assets/images/r550-not-dead-1.png){: .align-center}

![r550-not-dead-2]({{site.url}}/assets/images/r550-not-dead-2.png){: .align-center}

<center><sup>정리하다 보니, 로그인이 되는 시점의 터미널 출력에서부터 문제의 원인이 보인다. <sup></center>



네트워크에 뭔가 문제가 생긴 것 같긴 하고, 그게 Docker Container 배포와 관련된 것 같은데, 원인이 무엇인지 쉽사리 파악할 수 없었다.



<br>

# 분석

 팀장님께 도움을 청해 OpenLDAP 컨테이너가 실행되며 생성된 Bridge 네트워크 때문임을 알 수 있었다.



## 배포에 사용한 Docker Compose 파일

OpenLDAP 컨테이너를 배포하기 위해 사용한 Docker Compose 파일은 다음과 같다(*일부 생략 및 변형*).

```yaml
version: "3.8"
services:
  openldap:
    image: osixia/openldap:latest
    container_name: openldap
    restart: always
    ports:
      - 3899:389
      - 6366:636
    environment: # 생략
    tty: true
    stdin_open: true
    volumes: # 일부 변형
      - ./data/slapd.d/database:/var/lib/ldap
      - ./data/slapd.d/config:/etc/ldap/slapd.d
    command:
      - --copy-service # prevent default ldif overwritten
      - --loglevel=debug
```



Docker Compose를 이용해 Docker container를 실행하게 되면, 네트워크 관련 특별한 설정이 없는 한, Compose는 앱 컨테이너마다 단일 네트워크를 생성한다. 

> *참고*: [Networking in Compose](https://docs.docker.com/compose/networking/)
>
> By default Compose sets up a single [network](https://docs.docker.com/engine/reference/commandline/network_create/) for your app. Each container for a service joins the default network and is both reachable by other containers on that network, and discoverable by them at a hostname identical to the container name. 

Docker 엔진에서 기본으로 생성하는 네트워크는 브릿지 모드이기 때문에, Compose에 의해 OpenLDAP 컨테이너가 실행될 때, 브릿지 네트워크가 생성되며, 해당 컨테이너는 Compose에 의해 생성된 네트워크에 바인딩된다.

<br>



## 서버 네트워크 확인



R550 서버에서 `docker network ls` 명령을 통해 Docker network 상태를 확인해 보자.

![r550-docker-network-ls]({{site.url}}/assets/images/r550-docker-network-ls.png){: .align-center}

<center><sup>문제를 해결하기 전까지 서버 상태는 모두 R650 서버에서 R550 서버로 접속해 확인했다.</sup></center>

 Docker 설치 시 기본으로 생성되는 `bridge` 네트워크 외에, OpenLDAP을 띄울 때 필요한 브릿지 네트워크가 생성된 것을 확인할 수 있다.

 실제로 `docker inspect` 명령을 통해 해당 네트워크를 확인해 보면 다음의 사항을 확인할 수 있다.

- OpenLDAP 컨테이너를 띄우며 생성된 bridge 네트워크는 `172.22.0.0/16` IP 대역을 사용한다.
- OpenLDAP 컨테이너가 해당 네트워크에 바인딩 되어, 해당 대역에서 `172.22.0.2` IP를 할당 받았다.

```bash
docker network inspect 80cb5a0c
```

```json
[
    {
        "Name": "XXXX-openldap_default",
        "Id": "80cb5a0c07bc3f230fd8655614c0ac169cbcb9349f4ef674abc5d65330bdab5a",
        "Created": "2023-11-08T02:58:03.842920392Z",
        "Scope": "local",
        "Driver": "bridge",
        "EnableIPv6": false,
        "IPAM": {
            "Driver": "default",
            "Options": null,
            "Config": [
                {
                    "Subnet": "172.22.0.0/16",
                    "Gateway": "172.22.0.1"
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
            "3a73b76055e15fe9efaeb5c91fb5326ec782453cbe7f29d536e52c5fd5609d3d": {
                "Name": "openldap", // OpenLDAP 컨테이너
                "EndpointID": "372ea6a6c9c303a1e80b1c70868b02e60a7cf39d13503ca2f7db1066b6d1b81d",
                "MacAddress": "02:42:ac:16:00:02",
                "IPv4Address": "172.22.0.2/16", // 172.22.0.2. IP 할당
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

`ifconfig`를 통해 R550 서버의 네트워크 인터페이스를 확인해 보자.

![r550-ifconfig]({{site.url}}/assets/images/r550-ifconfig.png){: .align-center}

R550 호스트에 기본적으로 존재하는 Network Interface 외에, Docker에 의해 생성된 Bridge 네트워크 인터페이스, veth 네트워크 인터페이스가 할당되어 있음을 확인할 수 있다.

- `lo`: Loopback Interface. `127.0.0.0/8` 대역의 IP를 처리함
- `eno8303`: NIC를 통해 외부와 연결되는 Network Interface. IP `172.42.10.112`를 통해 외부와 연결됨
- `br-80cb5a0c07bc`: Docker Compose에 의해 생성된 Virtual Interface
  - 해당 네트워크에 바인딩되는 Docker Container가 생성될 때마다 `172.22.0.1/16`  대역에서 IP를 할당함
  - 호스트의 네트워크 인터페이스 및 Docker Container의 네트워크 인터페이스와 바인딩되어, 자신에게 바인딩된 Docker Container와 호스트 사이의 통신을 가능하게 함
    - 호스트 네트워크 인터페이스: 호스트에서 외부로 나갈 수 있는 호스트 인터페이스(NIC)
    - Docker Container 인터페이스: Docker Container에서 호스트로의 연결을 담당하는 `eth0` 인터페이스
- `docker0`: Docker 생성 시 기본으로 생성되는 Virtual Interface
- `veth4ac7512`: Docker Container(*여기서는 OpenLDAP 컨테이너*)에 할당된 `eth0` 인터페이스와 통신하기 위해 할당된 Virtual Ethernet Interface
  - Docker Container 생성 시 호스트에 할당됨
  - Bridge 네트워크와 바인딩됨
  - 생성된 Docker Container 내부의 `eth0` 인터페이스와 통신함

<br>



Docker Network의 동작을 고려하여, OpenLDAP 컨테이너를 실행한 뒤의 R550 서버의 네트워크 환경을 다음과 같이 도식화할 수 있다.

![openldap-docker-network.png]({{site.url}}/assets/images/openldap-docker-network.png){: .align-center}

- OpenLDAP 컨테이너가 실행되며, Compose에 의해 Bridge 네트워크가 생성되었다.
  - 해당 Bridge 네트워크 대역은 Host의 네트워크와 분리된다.
- OpenLDAP 컨테이너는 생성된 Bridge 네트워크에 바인딩되어 컨테이너 Host 및 그 외부와 통신할 수 있다.
  - OpenLDAP 컨테이너가 생성되는 순간, Host에 Virtual Ethernet Interface `veth4ac7512`가 할당되며 이것이 생성된 Bridge 네트워크와 바인딩된다.
  - OpenLDAP 컨테이너 내부에서 `eth0` 인터페이스가 할당되고, 이 인터페이스가 Host의 Virtual Ethernet Interface `veth4ac7512`와 바인딩된다.



> *참고*: `docker0` 인터페이스
>
> 호스트에서 확인할 수 있는 `docker0` 인터페이스는 docker 설치 시 기본으로 설치되는 `bridge`라는 이름의 Bridge 네트워크이다.
>
> - `docker network inspect`를 통해 확인한 `bridge` 네트워크는 `172.17.0.1`이라는 게이트웨이를 가지고 있다.
>
>   ```bash
>   [
>       {
>           "Name": "bridge",
>           "Id": "f36f914ad8019f24b429f06516fa188538e409149d53b033acaf9a6f0f947ede",
>           "Created": "2023-10-30T07:15:51.631144202Z",
>           "Scope": "local",
>           "Driver": "bridge",
>           "EnableIPv6": false,
>           "IPAM": {
>               "Driver": "default",
>               "Options": null,
>               "Config": [
>                   {
>                       "Subnet": "172.17.0.0/16",
>                       "Gateway": "172.17.0.1"
>                   }
>               ]
>           },
>           "Internal": false,
>           "Attachable": false,
>           "Ingress": false,
>           "ConfigFrom": {
>               "Network": ""
>           },
>           "ConfigOnly": false,
>           "Containers": {},
>           "Options": {
>               "com.docker.network.bridge.default_bridge": "true",
>               "com.docker.network.bridge.enable_icc": "true",
>               "com.docker.network.bridge.enable_ip_masquerade": "true",
>               "com.docker.network.bridge.host_binding_ipv4": "0.0.0.0",
>               "com.docker.network.bridge.name": "docker0",
>               "com.docker.network.driver.mtu": "1500"
>           },
>           "Labels": {}
>       }
>   ]
>   ```
>
> - 해당 게이트웨이는 호스트에서 `ifconfig`를 통해 확인할 수 있는 `docker0` 인터페이스이다.
>
> - 해당 포스트에서는 OpenLDAP 컨테이너를 가정하기 때문에 위와 같이 도식화되었으나, 일반적으로 docker container를 Bridge 모드로 실행할 경우, 기본적으로 생성되어 있는 `bridge` 네트워크에 바인딩된다.



> *참고*: 컨테이너 내 네트워크 인터페이스 확인
>
> Docker Container 실행 후, 컨테이너 내부에서 네트워크 인터페이스를 확인하면 다음과 같이 `eth0`, `lo` 인터페이스가 있는 것을 확인할 수 있다. OpenLDAP 컨테이너는 아니고, 다른 컨테이너를 확인했다.
>
> ![docker-container-inner-network]({{site.url}}/assets/images/docker-container-inner-network.png)
>
> - `lo` 인터페이스는 컨테이너 내부에서의 Loopback Interface이다.
> - `eth0` 인터페이스는 외부와 통신하기 위한 Interface이다. 호스트의 `veth`로 시작하는 인터페이스와 쌍을 이룬다.



<br>



## 원인



 문제는 이와 같은 네트워크 상황에서 호스트의 라우팅 테이블에 Docker Bridge 네트워크 게이트웨이도 모두 등록된다는 데에 있다.

 이를 확인하기 위해 호스트의 라우팅 테이블을 `route` 커맨드를 통해 확인해 보았다. 문제 상황 당시 시점에서 확인한 결과는 아니지만, Docker의 Bridge Network가 라우팅 테이블에 등록된다는 사실을 확인하기 위해 R650 호스트의 상황을 참조해 보았다.

![r650-routing-table]({{site.url}}/assets/images/r650-routing-table.png){: .align-center}

`br`로 시작하는 Docker Bridge 네트워크 인터페이스들이 모두 라우팅테이블에 등록되어 있다. 이것은 **해당 IP 대역의 IP 주소를 가진 패킷은 호스트 내부의 라우팅 테이블에서 처리된다**는 것을 의미한다.

<br>

결과적으로 이 포스트를 작성하는 계기가 된 문제 상황에서, 내 로컬 PC에서 R550 서버로 보낸 패킷은 R550 서버로 잘 전송되나, 그 응답 패킷이 내 로컬 PC로 전송되지 못하게 된다. `172.22.10.119` 가 목적지인 IP 패킷인데, 이 패킷은 R550 호스트 라우팅 테이블에 의해, 호스트 내에서 `br-80cbXXX` 브릿지 네트워크 대역으로 전달되어 처리되기 때문이다. 

이를테면, 다음과 같은 상황이다.

![r550-ip-collision]({{site.url}}/assets/images/r550-ip-collision.png){: .align-center}

- SSH 요청 패킷이 `172.42.10.112` IP를 통해 R550 서버로 전송된다
- SSH 응답 패킷이 R550 서버로부터 `172.22.10.119` IP를 통해 내 로컬 PC로 전송되어야 하나, 파란색 루트를 따라 호스트 내부 Bridge 네트워크 대역으로 전송된다.
  - 물론 이 네트워크 대역에는 `172.22.10.119` IP를 할당 받은 컨테이너가 없기 때문에, 해당 패킷은 유실된다.
- 내 로컬 PC는 요청을 보낸 후, 응답을 받지 못하게 된다.



<br>

로컬 PC가 속한 네트워크 대역과 R550 서버 호스트 내부에서 격리된 Bridge 네트워크 대역의 subnet mask도 다르고, gateway도 다르지 않나 궁금하기도 했었는데, 불행히도 IP 패킷 자체만으로는 어떤 게이트웨이를 택해야 할지 알 수 없다(참고: [How does an IP packet know which gateway to take?](https://serverfault.com/questions/904366/how-does-an-ip-packet-know-which-gateway-to-take)). ~~패킷에 게이트웨이가 적혀 있다고 한들, 게이트웨이 IP도 사설망 대역에서는 겹칠 수 있기 때문에, 의미가 없다~~.

어떻게 하다 보니, 운이 좋지 않게 Docker Compose에 의해 할당된 Bridge 네트워크가 `172.22.X.X` 대역를 사용하도록 했고, 이것이 내 로컬 PC가 속한 사설망 대역과 겹쳐 버린 것이다.

개발 환경이었기에 해프닝이었다고 넘어갈 수 있지만, 실제 운영 환경에서는 큰 문제가 될 수도 있다. 요컨대, 이렇게 Bridge Network 대역이 클라이언트의 IP 대역과 동일하게 Docker Container가 배포되었다고 해 보자. 클라이언트가 보낸 요청에 대한 응답이 클라이언트에게 돌아가지 않을 수도 있고, 클라이언트가 서버에 접속도 못할 수 있다. 아찔한 일이 아닐 수 없다.

<br>

## Bridge 네트워크 대역의 할당



이쯤 되니, 궁금하지 않을 수 없다.

> 왜 전에는 같은 문제가 발생하지 않았는가?

 이전에 OpenLDAP 컨테이너를 실행할 때는 똑같은 Docker Compose 파일을 이용해 컨테이너를 배포했음에도 불구하고 









R550 서버 내 라우팅 테이블에 의해 NIC를 통해 외부 망으로 빠져 나오지 못
