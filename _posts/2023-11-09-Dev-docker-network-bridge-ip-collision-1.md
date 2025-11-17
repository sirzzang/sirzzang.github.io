---
title:  "[Docker] Docker Bridge Network 사용 시 IP 충돌 - 1. 문제"
excerpt: Docker Bridge Network를 사용해 컨테이너를 배포할 때 발생할 수 있는 IP 대역대 충돌 문제
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

 회사에서 Docker를 이용해 컨테이너를 배포한 뒤, Bridge Network 사용으로 인해 발생했던 문제 및 그 원인을 기록하고자 한다. 인증, 인가를 담당하는 Account 서버에서는 오픈소스 LDAP 서버 구현체인 [OpenLDAP](https://www.openldap.org/)을 사용하는데, OpenLDAP 서버를 팀 내 개발 서버에 컨테이너로 배포하고자 했을 때 겪은 문제이다.

<br>

# 개요

 팀 내에서 사용하고 있는 개발 서버는 Dell R550, R650 총 두 대로, 회사 내 사설망의 `172.42.10.X` 대역에서 다음과 같은 IP를 할당 받아 사용하고 있다.

- R550: `172.42.10.112`
- R650: `172.42.10.110`

내가 사용하고 있는 PC는 회사 내 사설망의 `172.22.10.X` 대역에서 아래의 IP를 할당 받아 사용하고 있다.

- `172.22.10.119`

개발은 개인 PC에서 진행하며, 개발이 완료된 서비스를 팀 서버 R550에 배포한다. 개인 PC에서 SSH를 이용해 팀 서버에 접속한다.



<br>

# 문제

OpenLDAP 컨테이너를 R550 서버에 배포한 뒤, 갑자기 개인 PC에서 R550 서버로 SSH 접속이 되지 않는 문제가 발생했다. 문제를 인지한 후, R650 서버와 R550 서버에 핑을 날려 봤는데, R550 서버에만 가지 않는다.

![docker-bridge-ping-error]({{site.url}}/assets/images/docker-bridge-ping-error.png){: .align-center}

 컨테이너를 배포하는 과정에서 문제가 있어서 서버를 죽인 것인가(...) 했는데, 로컬에서 R650 서버로 SSH 접속한 뒤, R650 서버에서 R550 서버로 SSH 접속해 본 결과, 문제가 없이 접속되는 것을 보니 서버가 죽지는 않았다.

![r550-not-dead-1]({{site.url}}/assets/images/r550-not-dead-1.png){:width="600"}{: .align-center}

![r550-not-dead-2]({{site.url}}/assets/images/r550-not-dead-2.png){:width="600"}{: .align-center}

<center><sup>정리하다 보니, 로그인이 되는 시점의 터미널 출력에서부터 문제의 원인이 보인다. </sup></center>



네트워크에 뭔가 문제가 생긴 것 같긴 하고, 그게 Docker Container 배포와 관련된 것 같은데, 원인이 무엇인지 쉽사리 파악할 수 없었다.



<br>

# 분석

 팀장님께 도움을 청해 OpenLDAP 컨테이너가 실행되며 생성된 Bridge Network 때문임을 알 수 있었다. ~~브릿지 네트워크한테 먹혀 버렸다고 하셨다~~



## 배포에 사용한 Docker Compose 파일

OpenLDAP 컨테이너를 배포하기 위해 사용한 Docker Compose 파일은 다음과 같다.

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
    environment:
      # 생략
    tty: true
    stdin_open: true
    volumes:
      - ./data/slapd.d/database:/var/lib/ldap
      - ./data/slapd.d/config:/etc/ldap/slapd.d
    command:
      - --copy-service
      - --loglevel=debug
```



Docker Compose를 이용해 Docker container를 실행하게 되면, 네트워크 관련 특별한 설정이 없는 한, Compose는 앱 컨테이너마다 단일 네트워크를 생성한다. 

> *참고*: [Networking in Compose](https://docs.docker.com/compose/networking/)
>
> By default Compose sets up a single [network](https://docs.docker.com/engine/reference/commandline/network_create/) for your app. Each container for a service joins the default network and is both reachable by other containers on that network, and discoverable by them at a hostname identical to the container name. 

Docker 엔진에서 기본으로 생성하는 네트워크는 Bridge 모드이기 때문에, Compose에 의해 OpenLDAP 컨테이너가 실행될 때, Bridge 네트워크가 생성되며, 해당 컨테이너는 Compose에 의해 생성된 네트워크에 바인딩된다.

<br>



## 서버 네트워크 확인



R550 서버에서 `docker network ls` 명령을 통해 Docker network 상태를 확인해 보자.

![r550-docker-network-ls]({{site.url}}/assets/images/r550-docker-network-ls.png){: .align-center}

<center><sup>문제를 해결하기 전까지 서버 상태는 모두 R650 서버에서 R550 서버로 접속해 확인했다.</sup></center>

 Docker 설치 시 기본으로 생성되는 `bridge` 네트워크 외에, OpenLDAP을 띄울 때 필요한 브릿지 네트워크가 생성된 것을 확인할 수 있다.

 실제로 `docker inspect` 명령을 통해 해당 네트워크를 확인해 보면 다음의 사항을 확인할 수 있다.

- OpenLDAP 컨테이너를 띄우며 생성된 Bridge 네트워크는 `172.22.0.0/16` IP 대역을 사용한다.
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
                "Name": "openldap", # OpenLDAP 컨테이너
                "EndpointID": "372ea6a6c9c303a1e80b1c70868b02e60a7cf39d13503ca2f7db1066b6d1b81d",
                "MacAddress": "02:42:ac:16:00:02",
                "IPv4Address": "172.22.0.2/16", # 172.22.0.2 IP 할당
                "IPv6Address": ""
            }
        },
        "Options": {},
        "Labels": {
            "com.docker.compose.network": "default",
            "com.docker.compose.project": "XXXX-openldap",
            "com.docker.compose.version": "2.21.0"
        }
    }
]
```

<br>

`ifconfig`를 통해 R550 서버의 네트워크 인터페이스를 확인해 보자.

![r550-ifconfig]({{site.url}}/assets/images/r550-ifconfig.png){: .align-center}

R550 호스트에 기본적으로 존재하는 Network Interface 외에, Docker에 의해 생성된 Bridge 네트워크 인터페이스, veth 네트워크 인터페이스가 할당되어 있음을 확인할 수 있다.

- `lo`: Loopback Interface. `127.0.0.0/8` 대역의 IP를 처리한다.
- `eno8303`: NIC를 통해 외부와 연결되는 Network Interface. IP `172.42.10.112`를 통해 외부와 연결된다.
- `br-80cb5a0c07bc`: Docker Compose에 의해 생성된 Virtual Interface. `172.22.0.0/16` 대역의 IP를 처리한다. Host와 분리된 네트워크 영역이다.
  - 해당 네트워크에 바인딩되는 Docker Container가 생성될 때마다 `172.22.0.0/16`  대역에서 IP를 할당한다.
  - 호스트의 네트워크 인터페이스 및 Docker Container의 네트워크 인터페이스와 바인딩되어, 자신에게 바인딩된 Docker Container와 호스트 사이의 통신을 가능하게 함
    - 호스트 네트워크 인터페이스: 호스트에서 외부로 나갈 수 있는 인터페이스(NIC)
    - Docker Container 인터페이스: Docker Container에서 호스트로의 연결을 담당하는 `eth0` 인터페이스
- `docker0`: Docker 생성 시 기본으로 생성되는 Virtual Interface
- `veth4ac7512`: Docker Container(여기서는 OpenLDAP 컨테이너)에 할당된 `eth0` 인터페이스와 통신하기 위해 할당된 Virtual Ethernet Interface
  - Docker Container 생성 시 호스트에 할당됨
  - Bridge 네트워크와 바인딩됨
  - 생성된 Docker Container 내부의 `eth0` 인터페이스와 통신함

> *참고*: 컨테이너 내 네트워크 인터페이스 확인
>
> Docker Container 실행 후, 컨테이너 내부에서 네트워크 인터페이스를 확인하면 다음과 같이 `eth0`, `lo` 인터페이스가 있는 것을 확인할 수 있다. OpenLDAP 컨테이너는 아니고, 다른 컨테이너를 확인했다.
>
> ![docker-container-inner-network]({{site.url}}/assets/images/docker-container-inner-network.png)
>
> - `lo` 인터페이스는 컨테이너 내부에서의 Loopback Interface이다.
> - `eth0` 인터페이스는 외부와 통신하기 위한 Interface이다. 호스트의 `veth`로 시작하는 인터페이스와 쌍을 이룬다.

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
> - 해당 게이트웨이는 호스트에서 `ifconfig`를 통해 확인할 수 있는 `docker0` 인터페이스이다. 즉, `bridge` 네트워크는 `docker0` 인터페이스를 사용한다.
>
>   ```bash
>   br-80cb5a0c07bc: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
>           inet 172.22.0.1  netmask 255.255.0.0  broadcast 172.22.255.255
>           inet6 fe80::42:a4ff:fe3f:b900  prefixlen 64  scopeid 0x20<link>
>           ether 02:42:a4:3f:b9:00  txqueuelen 0  (Ethernet)
>           RX packets 10  bytes 280 (280.0 B)
>           RX errors 0  dropped 0  overruns 0  frame 0
>           TX packets 1053  bytes 44674 (44.6 KB)
>           TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0
>
>   docker0: flags=4099<UP,BROADCAST,MULTICAST>  mtu 1500
>           inet 172.17.0.1  netmask 255.255.0.0  broadcast 172.17.255.255
>           ether 02:42:56:eb:d5:1c  txqueuelen 0  (Ethernet)
>           RX packets 0  bytes 0 (0.0 B)
>           RX errors 0  dropped 0  overruns 0  frame 0
>           TX packets 0  bytes 0 (0.0 B)
>           TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0
>
>   eno8303: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
>           inet 172.42.10.112  netmask 255.255.255.0  broadcast 172.42.10.255
>           inet6 fe80::2288:10ff:febb:932  prefixlen 64  scopeid 0x20<link>
>           ether 20:88:10:bb:09:32  txqueuelen 1000  (Ethernet)
>           RX packets 6352084  bytes 2470991108 (2.4 GB)
>           RX errors 0  dropped 1217831  overruns 0  frame 0
>           TX packets 3397947  bytes 1084531860 (1.0 GB)
>           TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0
>           device interrupt 17
>   ```
>
> -  일반적으로 docker container를 `docker` 커맨드를 이용하여 Bridge 모드의 네트워크를 이용하도록 실행할 경우, 기본적으로 생성되어 있는 `bridge` 네트워크에 바인딩된다.
>
>   ```bash
>   docker run --network bridge [이미지:태그]
>   ```
>   



<br>

## 원인



 문제는 이와 같은 네트워크 상황에서 **호스트의 라우팅 테이블에 Docker Bridge 네트워크 게이트웨이도 모두 등록**된다는 데에 있다.

 이를 확인하기 위해 호스트의 라우팅 테이블을 `route` 커맨드를 통해 확인해 보았다. 문제 상황 당시 시점에서 확인한 결과는 아니지만, Docker의 Bridge Network가 라우팅 테이블에 등록된다는 사실을 확인하기 위해 R650 호스트의 상황을 참고했다.

![r650-routing-table]({{site.url}}/assets/images/r650-routing-table.png){: .width="600"}{: .align-center}

`br`로 시작하는 Docker Bridge 네트워크 인터페이스들이 모두 라우팅테이블에 등록되어 있다. 이를 통해 **브릿지 네트워크 대역의 IP 주소를 가진 패킷이 라우팅 테이블에 따라 호스트 내부에서 처리된다**는 것을 알 수 있다.

<br>

결과적으로 이 포스트를 작성하는 계기가 된 문제 상황에서, 내 로컬 PC에서 R550 서버로 보낸 패킷은 R550 서버로 잘 전송되나, 그 응답 패킷이 내 로컬 PC로 전송되지 못하게 된다. `172.22.10.119` 가 목적지인 IP 패킷인데, 이 패킷은 R550 호스트 라우팅 테이블에 의해, 호스트 내에서 `br-80cbXXX` 브릿지 네트워크 대역으로 전달되어 처리되기 때문이다. 

이를테면, 다음과 같은 상황이다.

![r550-ip-collision]({{site.url}}/assets/images/r550-ip-collision.png){: .align-center}

- SSH 요청 패킷이 `172.42.10.112` IP를 통해 R550 서버로 전송된다
- SSH 응답 패킷이 R550 서버로부터 `172.22.10.119` IP를 통해 내 로컬 PC로 전송되어야 하나, 파란색 루트를 따라 호스트 내부 Bridge 네트워크 대역으로 전송된다.
  - 물론 이 네트워크 대역에는 `172.22.10.119` IP를 할당 받은 컨테이너가 없기 때문에, 해당 패킷은 목적지를 찾지 못하고 유실된다.
- 내 로컬 PC는 요청을 보낸 후, 응답을 받지 못하게 된다.



<br>

로컬 PC가 속한 네트워크 대역과 R550 서버 호스트 내부에서 격리된 Bridge 네트워크 대역의 subnet mask도 다르고, gateway도 다르지 않나 궁금하기도 했었다. 그러나 불행히도 IP 패킷 자체만으로는 어떤 게이트웨이를 택해야 할지 알 수 없다(참고: [How does an IP packet know which gateway to take?](https://serverfault.com/questions/904366/how-does-an-ip-packet-know-which-gateway-to-take)). 패킷에 게이트웨이가 적혀 있다고 한들, 게이트웨이 IP도 사설망 대역에서는 겹칠 수 있기 때문에, 의미가 없다.

결과적으로 이 문제는, 

- Docker Compose에 의해 OpenLDAP 컨테이너가 실행되며 생성된 Bridge 네트워크가,
- 어쩌다 보니 ~~운이 좋지 않게도~~ 서버 내에서 격리된 `172.22.X.X` 대역를 사용하는 것이었고, 
- 이것이 내 로컬 PC가 속한 사설망 대역과 겹쳐 버렸기 때문에, 
- Host에서 보낸 패킷에 대한 응답이 정상적으로 돌아오지 못해

발생한 문제였다. 

<br>



## Bridge 네트워크 대역의 할당



이쯤 되니, 대관절 **왜 갑자기 이런 문제가 발생한 것인지**가 궁금하지 않을 수 없다. 이 문제가 발생하기 전에도 계속해서 OpenLDAP 컨테이너를 실행할 때 똑같은 과정을 거쳤다. Docker Compose 파일에서 네트워크 관련 설정을 바꾼 것도 아니었다. 그러나 Host에서의 접속이 막히는 것과 같은 상황은 발생하지 않았다.

Docker 엔진이 Bridge 네트워크가 생성될 때마다 그 대역을 할당하는 방식에서 그 이유를 찾을 수 있었다. Docker Daemon은 새로운 네트워크를 생성할 때마다 `172.N.0.0/16`에서 `N`을 1씩 증가시키는 방식으로 생성한다. Docker 엔진이 내부 로직에 의해 사용 가능한 서브넷 대역을 찾아 할당하는 것이다.

 할당 범위는 Docker Daemon 설정에 따라 달라지지만, 보통 `172.16.0.0/16` 대역부터 시작한다. 할당 가능한 대역이 남아 있지 않으면, 다른 IP 대역대를 사용하게 된다. 엔진 내부적으로 다른 IP 대역대를 사용할 수도 있지만, 설정 값을 바꿔주어야 할 수도 있다.

<br>

 실제로 Docker Network를 생성하며, IP 대역대가 어떻게 할당되는지 확인해 볼 수 있다. 아무런 Docker Network도 생성하지 않은 최초 상태에서 기본으로 생성되어 있는 Bridge 네트워크 `bridge`의 gateway는 `172.17.0.1`로, `172.17.0.0/16` 대역을 사용한다.

![docker-network-default]({{site.url}}/assets/images/docker-network-default.png){: .width="600"}{: .align-center} 

```json
[
    {
        "Name": "bridge",
        "Id": "2d2d07068b079c8598aa50eb178885ef9b40c0b80945ab6f371531c253efdaf6",
        "Created": "2023-11-09T05:44:29.238126817Z",
        "Scope": "local",
        "Driver": "bridge",
        "EnableIPv6": false,
        "IPAM": {
            "Driver": "default",
            "Options": null,
            "Config": [
                {
                    "Subnet": "172.17.0.0/16",
                    "Gateway": "172.17.0.1"
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
        "Containers": {},
        "Options": {
            "com.docker.network.bridge.default_bridge": "true",
            "com.docker.network.bridge.enable_icc": "true",
            "com.docker.network.bridge.enable_ip_masquerade": "true",
            "com.docker.network.bridge.host_binding_ipv4": "0.0.0.0",
            "com.docker.network.bridge.name": "docker0",
            "com.docker.network.driver.mtu": "1500"
        },
        "Labels": {}
    }
]
```



이 상태에서 `bridge1` 네트워크를 생성해 보자.

```bash
$ docker network create bridge1
```

![docker-network-after-creating-bridge1]({{site.url}}/assets/images/docker-network-after-creating-bridge1.png){: width="500"}{: .align-center}



생성된 `bridge1` 네트워크를 확인해 보면, `bridge1` 네트워크는 `bridge` 네트워크에 이어 `172.17.0.0/16` 대역을 사용한다.

```bash
$ docker network inspect bridge1
```

![docker-network-bridge1]({{site.url}}/assets/images/docker-network-bridge1.png){: .width="600"}{: .align-center}

계속해서 Docker Network를 생성한다. `172.31.0.0/16` 대역을 넘어간 이후, `192.168.0.0/20` 대역부터 네트워크 대역이 할당됨을 확인할 수 있다.

![docker-network-after-creating-bridge20]({{site.url}}/assets/images/docker-network-after-creating-bridge20.png){: width="500"}{: .align-center}

![docker-network-bridge16-bridge20]({{site.url}}/assets/images/docker-network-bridge16-bridge20.png){: .align-center}

> *참고*: docker network prune
>
> 위의 실험을 진행한 후, 사용하지 않는 네트워크를 모두 삭제하기 위해 `prune` 커맨드를 이용하면 좋다. 현재 사용되고 있지 않은 모든 네트워크를 삭제해 준다.
>
> ![docker-network-prune]({{site.url}}/assets/images/docker-network-prune.png){: width="500"}



