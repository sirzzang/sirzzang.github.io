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

결과적으로, 이 문제 상황은 Docker Container가 실행되며 생성된 Docker Network 때문에 발생한 것이다. Docker Compose를 통해 OpenLDAP 컨테이너를 실행할 때마다 Bridge 타입의 새로운 Docker Network가 생성되었고, Docker 엔진에 의해 차례로 IP 대역이 할당되다가 `172.22.0.0/16` 대역이 할당된 것이다. *공교롭게도* 이 IP 대역이 로컬 PC가 사용하는 IP 주소 대역과 일치해 버렸다. 그래서 로컬 PC의 요청 패킷에 대한 응답 패킷은 되돌아 오지 못하고, R550 서버 내부에 격리되어 생성된 Docker Network로 들어가 버린다.

 참으로 얄궂은 타이밍이지만, Docker Network의 동작 원리에 대해 알고 있었다면 문제 원인을 짚어내는 게 그렇게 어렵지는 않았을 것이라는 생각도 든다.

 Docker Container를 중지한 뒤, 다시 핑을 날려 보면, 문제 없이 잘 동작함을 확인할 수 있다.

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
  - Docker Container 재실행(**1안**)
  - Bridge Network 지정해서 실행
    - Bridge Network를 직접 생성한 후, Docker Compose에서 해당 네트워크를 이용하여 Container를 실행하도록 지정(**2안**)
    - Docker Compose가 Docker Container를 실행할 때 사용할 Bridge Network 대역을 직접 지정(**3안**)
  - Bridge Network 대역대 변경(**4안**)
- Host 모드 사용(**5안**)

이 대안들 중 어떤 것을 사용하더라도, 앞에서 발생했던 문제는 발생하지 않는다. 즉, 로컬 PC에서 핑을 날릴 때 응답이 돌아오고, SSH 접속도 된다.

<br>



## 1안

Docker Container를 다시 실행하면 된다. Docker 엔진이 IP 대역대를 차례로 할당하기 때문에, 다시 실행하면 `172.22.X.X`와 겹치지 않는 다음 대역대의 네트워크가 할당된다.

새롭게 컨테이너를 실행했을 때, 아까와 동일하게 `XXXX-openldap_default` 네트워크가 생성되는 것을 확인할 수 있다.

![restart-docker-container]({{site.url}}/assets/images/restart-docker-container.png){: .align-center}{: width="500"}

새롭게 사용하고 있는 Docker Brdige 네트워크를 검사해 보면, 해당 브릿지 네트워크가 `172.23.0.0/16` IP 대역대를 사용하고 있음을 확인할 수 있다.

```bash
$ docker network inspect 160ca
[
    {
        "Name": "XXXX-openldap_default",
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
            "com.docker.compose.project": "XXXX-openldap",
            "com.docker.compose.version": "2.21.0"
        }
    }
]
```

로컬 PC의 IP 대역대와 겹치지 않는다. 문제가 해결되었는지 확인하기 위해, 로컬 PC에서 핑을 날려 보면 성공한다. 문제는 해결되었지만, **별로 좋은 해결책은 아니다**. 어쩌다가 운 나쁘게 문제가 발생했던 것처럼, 어쩌다가 운 좋게 얻어 걸릴 수도 있는 방법이다.

<br>





## 2안

로컬 PC와 겹치지 않는 대역으로 브릿지 네트워크를 만든 뒤, Docker Compose가 이 네트워크를 이용하여 Docker Container를 실행하도록 한다. 자동으로 네트워크를 생성하지 않고, 이미 생성된 네트워크를 사용하게 된다.

- Docker Network 생성

  ```bash
  docker network create --driver=bridge --subnet=172.20.0.0/16 --ip-range=172.20.5.0/24 --gateway=172.20.0.1 bridge_network_test
  ```

  - `--driver`: 네트워크 드라이버 모드
  - `--subnet`: 할당할 서브넷. CIDR 형태로 작성
  - `--ip-range`: 서브넷 안에서 IP 주소를 할당할 대역
  - `--gateway`: Docker Network 게이트웨이 주소

- 생성한 Docker Network 확인

  ![docker-network-test]({{site.url}}/assets/images/docker-network-test.png){: .align-center}

  ```bash
  $ docker network inspect e9d0f
  [
      {
          "Name": "bridge_network_test",
          "Id": "e9d0fb6a0d8446d6fe4b302b1e786a4a99222bef289335e62ab82a75c607beec",
          "Created": "2023-11-08T05:25:11.012806083Z",
          "Scope": "local",
          "Driver": "bridge",
          "EnableIPv6": false,
          "IPAM": {
              "Driver": "default",
              "Options": {},
              "Config": [
                  {
                      "Subnet": "172.20.0.0/16",
                      "IPRange": "172.20.5.0/24",
                      "Gateway": "172.20.0.1"
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
          "Options": {},
          "Labels": {}
      }
  ]
  ```

 

이제 아래와 같이 Docker Compose 파일을 변경한다.

```yaml
version: "3.8"
services:
  openldap:
    image: osixia/openldap:latest
    restart: always
    networks:
      - bridge_network_test # 사용할 네트워크
    ports:
      - 3899:389
      - 6366:636
    environment: # 생략
    tty: true
    stdin_open: true
    volumes: # 생략
    command:
      - --copy-service
      - --loglevel=debug
networks:
  bridge_network_test:
    external: true
```

- `services.[서비스명].networks`: 해당 서비스 컨테이너가 사용할 네트워크를 지정한다
- `networks.[네트워크명].external`: Docker Compose 파일 외부에 있는 네트워크를 사용하도록 설정한다
  - 해당 옵션을 `true`로 설정할 경우, Docker Compose가 네트워크를 만들지 않는다([external 항목](https://docs.docker.com/compose/compose-file/06-networks/#external))



<br>

OpenLDAP 컨테이너를 다시 실행한 뒤 확인해 보자. 생성한 `bridge_network_test`를 검사하면, 실행된 OpenLDAP 컨테이너가 `172.20.5.0` IP를 할당 받아 실행된 것을 확인할 수 있다.

![docker-network-test-result]({{site.url}}/assets/images/docker-network-test-result.png){: .align-center}

 R550 호스트 네트워크를 살펴 보면, `bridge_network_test`를 만들 때 사용했던 네트워크 대역이 `br-e9d0fb6a0d84`로서 생성되어 있음을 확인할 수 있다.

```bash
$ ifconfig
br-e9d0fb6a0d84: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500 # bridge_network_test
        inet 172.20.0.1  netmask 255.255.0.0  broadcast 172.20.255.255
        inet6 fe80::42:91ff:fe31:4f44  prefixlen 64  scopeid 0x20<link>
        ether 02:42:91:31:4f:44  txqueuelen 0  (Ethernet)
        RX packets 0  bytes 0 (0.0 B)
        RX errors 0  dropped 0  overruns 0  frame 0
        TX packets 5  bytes 526 (526.0 B)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0

docker0: flags=4099<UP,BROADCAST,MULTICAST>  mtu 1500
        inet 172.17.0.1  netmask 255.255.0.0  broadcast 172.17.255.255
        ether 02:42:56:eb:d5:1c  txqueuelen 0  (Ethernet)
        RX packets 0  bytes 0 (0.0 B)
        RX errors 0  dropped 0  overruns 0  frame 0
        TX packets 0  bytes 0 (0.0 B)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0

eno8303: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
        inet 172.42.10.112  netmask 255.255.255.0  broadcast 172.42.10.255
        inet6 fe80::2288:10ff:febb:932  prefixlen 64  scopeid 0x20<link>
        ether 20:88:10:bb:09:32  txqueuelen 1000  (Ethernet)
        RX packets 6371081  bytes 2475931760 (2.4 GB)
        RX errors 0  dropped 1217831  overruns 0  frame 0
        TX packets 3411198  bytes 1085830427 (1.0 GB)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0
        device interrupt 17

eno8403: flags=4099<UP,BROADCAST,MULTICAST>  mtu 1500
        ether 20:88:10:bb:09:33  txqueuelen 1000  (Ethernet)
        RX packets 0  bytes 0 (0.0 B)
        RX errors 0  dropped 0  overruns 0  frame 0
        TX packets 0  bytes 0 (0.0 B)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0
        device interrupt 18

lo: flags=73<UP,LOOPBACK,RUNNING>  mtu 65536
        inet 127.0.0.1  netmask 255.0.0.0
        inet6 ::1  prefixlen 128  scopeid 0x10<host>
        loop  txqueuelen 1000  (Local Loopback)
        RX packets 10333003  bytes 1195162378 (1.1 GB)
        RX errors 0  dropped 0  overruns 0  frame 0
        TX packets 10333003  bytes 1195162378 (1.1 GB)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0

veth88e0dbe: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
        inet6 fe80::ac2c:71ff:fee5:dc69  prefixlen 64  scopeid 0x20<link>
        ether ae:2c:71:e5:dc:69  txqueuelen 0  (Ethernet)
        RX packets 0  bytes 0 (0.0 B)
        RX errors 0  dropped 0  overruns 0  frame 0
        TX packets 15  bytes 1322 (1.3 KB)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0
```



<br>





## 3안

위와 거의 비슷하나, Docker Compose에 의해 만들어지는 Docker Network를 지정한 뒤, 해당 네트워크에 바인딩하여 Docker Container를 실행한다.  아래와 같이 Docker Compose 파일을 작성해 주면 된다.

```yaml
version: "3.8"
services:
  openldap:
    image: osixia/openldap:latest
    restart: always
    networks:
      my_bridge_network:
    ports:
      - 3899:389
      - 6366:636
    environment: # 생략
    tty: true
    stdin_open: true
    volumes: # 생략
    command:
      - --copy-service
      - --loglevel=debug
networks:
  my_bridge_network:
    ipam:
    	driver: bridge
      config:
        - subnet: 172.20.0.0/16
          ip_range: 172.20.5.0/24
          gateway: 172.20.0.1
```

- `service.[서비스명].networks`: 사용할 네트워크를 지정한다. 해당 서비스가 바인딩될 `my_bridge_network`를 지정했다.
- `networks.my_bridge_network`: Docker Compose는 해당 네트워크를 생성한다
  - `ipam`: IP 주소 관리(IP Address Management)를 위한 설정 항목이다. `docker network` 커맨드에 설정했던 옵션과 동일한 값을 설정해 준다

<br>

Docker Compose를 이용하여 OpenLDAP 컨테이너를 실행한 뒤, Docker Network를 확인한다. Docker Compose에 의해 만들어진 `my_bridge_network`가 생성됨을 확인할 수 있다.

![my-bridge-network]({{site.url}}/assets/images/my-bridge-network.png){: .align-center}{: width="500"}

```bash
$ docker network inspect 2debf2
[
    {
        "Name": "XXXX-openldap_my_bridge_network",
        "Id": "2debf2abcbbe72fe6d0d6f6ec637eb2ecbf209b26e639eeaa961a38cfb19c87b",
        "Created": "2023-11-08T05:39:14.171038051Z",
        "Scope": "local",
        "Driver": "bridge",
        "EnableIPv6": false,
        "IPAM": {
            "Driver": "default",
            "Options": null,
            "Config": [
                {
                    "Subnet": "172.20.0.0/16",
                    "IPRange": "172.20.5.0/24",
                    "Gateway": "172.20.0.1"
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
            "f96a6af007ef249b63b160dec8da144fd1f4a2936c7faf8d0be74e92232d8e89": {
                "Name": "XXXX-openldap-openldap-1",
                "EndpointID": "61effc55ab1739ff63a1694efacf6a090e988eb52ba6ebf26b88008dc106cc9a",
                "MacAddress": "02:42:ac:14:05:00",
                "IPv4Address": "172.20.5.0/16",
                "IPv6Address": ""
            }
        },
        "Options": {},
        "Labels": {
            "com.docker.compose.network": "my_bridge_network",
            "com.docker.compose.project": "XXXX-openldap",
            "com.docker.compose.version": "2.21.0"
        }
    }
]
```

2안과 마찬가지로 R550 호스트에서도 해당하는 네트워크 인터페이스를 찾을 수 있으며, 로컬 PC에서 핑을 날릴 수 있다.

<br>



## 4안

Docker 설정에 의해, 엔진이 할당하는 Bridge Network의 대역을 변경하는 방법이다. 지금까지 나왔던 방법에 비해 더 근본적인 방법이라 보이지만, 서버 설정을 변경해야 하기 때문에, 실제로 진행하지는 못했다. 다만, 참고 자료를 통해 어떤 방법을 사용할 수 있는지 알아 본 방법을 정리해 두고자 한다.

### dockerd 커맨드 이용

Docker daemon 제어를 위한 `dockerd` 커맨드를 이용해, Bridge 네트워크가 할당되는 영역을 조정해 준다. `--default-address-pool` 옵션을 이용하면 된다. 다만, 해당 커맨드를 이용해 설정 변경을 적용하기 위해서는 Docker Network에 등록되어 있는 다른 네트워크들을 모두 먼저 제거해야 한다고 한다.

```bash
dockerd --default-address-pools base=10.10.0.0/16,size=24
```

![dockerd-options]({{site.url}}/assets/images/dockerd-options.png){: .align-center}



### docker daemon 설정 변경

Docker Daemon 설정 파일에서 [Default Bridge Network 관련 설정](https://docs.docker.com/engine/reference/commandline/dockerd/#daemon-configuration-file)을 [변경해 준다](https://docs.docker.com/network/drivers/bridge/#configure-the-default-bridge-network). Docker Daemon 설정 파일은 `/etc/docker/daemon.json`이다. 해당 위치에 설정 파일이 없을 수도 있는데, 생성하면 된다.

```json
{
  "allow-nondistributable-artifacts": [],
  "api-cors-header": "",
  "authorization-plugins": [],
  "bip": "",
  "bridge": "",
  "cgroup-parent": "",
  "containerd": "/run/containerd/containerd.sock",
  "containerd-namespace": "docker",
  "containerd-plugin-namespace": "docker-plugins",
  "data-root": "",
  "debug": true,
  // 여기를 변경하면 된다
  "default-address-pools": [
    {
      "base": "172.30.0.0/16",
      "size": 24
    },
    {
      "base": "172.31.0.0/16",
      "size": 24
    }
  ],
  // 생략
}
```



> *참고*: docker daemon 설정 적용 변경기
>
> 다른 서버에서도 계속 관련 문제가 반복되어 daemon 설정을 변경해 주었다.
>
> - `/etc/docker/daemon.json` 생성 후 default address pool 지정
>
>   ```json
>   {
>           "bip": "10.0.0.1/24",
>           "default-address-pools": [
>                   {
>                           "base": "10.10.0.1/16",
>                           "size": 28
>                   }
>           ]
>   }
>   ```
>
> - docker 재시작
>
>   ```bash
>   user@r650:/etc/docker$ sudo systemctl restart docker
>   ```
>
> - ip 대역 확인
>
>   ```bash
>   user@r650:~$ ifconfig
>   
>   ...
>   docker0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
>           inet 10.0.0.1  netmask 255.255.255.0  broadcast 10.0.0.255
>           inet6 fe80::42:25ff:fedd:1b9a  prefixlen 64  scopeid 0x20<link>
>           ether 02:42:25:dd:1b:9a  txqueuelen 0  (Ethernet)
>           RX packets 407  bytes 32558 (32.5 KB)
>           RX errors 0  dropped 0  overruns 0  frame 0
>           TX packets 456  bytes 4148963 (4.1 MB)
>           TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0
>   ...
>   ```
>   
> - 주의
>
>   - 기존의 설정 하에서 브릿지 네트워크를 생성해 동작하고 있던 컨테이너의 경우, docker daemon 설정을 변경하더라도 기존의 브릿지 네트워크를 잡아서 동작하게 된다.
>   - 따라서 문제가 되던 컨테이너를 중지한 후, 도커 네트워크를 정리한 뒤에(`docker prune`을 이용하면 간단하다), 다시 컨테이너를 실행하도록 하자.











<br>



## 5안



Docker Compose가 컨테이너를 실행할 때, 호스트 모드로 실행하라고 하면 된다. Docker Compose 파일을 아래와 같이 수정하면 된다. 

```yaml
version: "3.8"
services:
  openldap:
    image: osixia/openldap:latest
    restart: always
    network_mode: host
    environment: # 생략
    tty: true
    stdin_open: true
    volumes: # 생략   
    command:
      - --copy-service
      - --loglevel=debug
```

- 실행되는 컨테이너가 호스트의 네트워크 스택을 동일하게 사용하기 때문에, 호스트 포트를 컨테이너 포트로 매핑하는 것이 의미가 없다. 따라서 `ports` 항목을 삭제한다.
- 아래와 같이, `docker run` 커맨드를 `--network=host` 옵션과 함께 실행하는 것과 동일한 방식이다.

  ```bash
  docker run --rm -d --network host --name my_nginx nginx
  ```



<br>

컨테이너를 실행한 뒤 Docekr Network를 확인하면, 기본으로 존재하던 네트워크 외에, 아무 것도 존재하지 않음을 확인할 수 있다.

![docker-ip-collision-resolved-by-network-mode-host]({{site.url}}/assets/images/docker-ip-collision-resolved-by-network-mode-host.png){: .align-center}

<br>

Docker Network의 `host` 네트워크 검사 시, OpenLDAP 컨테이너가 붙어 있음을 확인할 수 있다.

```bash
$ docker network inspect host
[
    {
        "Name": "host",
        "Id": "5d6b793cdb0087324dae16f2edd53558c324287a876993d34518ffbdb1027d9f",
        "Created": "2023-10-24T07:23:02.114324605Z",
        "Scope": "local",
        "Driver": "host",
        "EnableIPv6": false,
        "IPAM": {
            "Driver": "default",
            "Options": null,
            "Config": []
        },
        "Internal": false,
        "Attachable": false,
        "Ingress": false,
        "ConfigFrom": {
            "Network": ""
        },
        "ConfigOnly": false,
        "Containers": {
            # 생략
            "4c212084412a4ec316864a62737c57452a8633f0ea06b6463765b37c1ab77e79": {
                "Name": "XXXX-openldap-openldap-1",
                "EndpointID": "9242b59c942f9c30c2e9cdbee991db83db0c6397721a588817cd5ce294a4ad48",
                "MacAddress": "",
                "IPv4Address": "",
                "IPv6Address": ""
            },
            "59e5500bcba45f28e4eb995d9bf66cfa85cfbfc0ae59aa135269ebf7e2748ccf": {
                "Name": "XXXX-postgres-postgres-1",
                "EndpointID": "d5166059bee0ffb3feb8ea9bd09801441fa0f2f6cae2797d18ee8369f764f30f",
                "MacAddress": "",
                "IPv4Address": "",
                "IPv6Address": ""
            },
            # 생략
        },
        "Options": {},
        "Labels": {}
    }
]
```

서버 호스트의 네트워크 인터페이스를 검사할 경우에도, 아무런 Docker Bridge 네트워크 관련 인터페이스를 찾을 수 없다.

![host-ifconfig-after-network-mode-host]({{site.url}}/assets/images/host-ifconfig-after-network-mode-host.png){: .align-center}

<br>

# 결론

 개발 환경이었기에 해프닝으로 치고 넘어갈 수 있지만, 실제 운영 환경에서는 큰 문제가 될 수도 있는 상황이다. 요컨대, Bridge Network 대역이 클라이언트의 IP 대역과 동일하게 Docker Container가 배포되었다고 해 보자. 클라이언트가 보낸 요청에 대한 응답이 클라이언트에게 돌아가지 않을 수도 있고, 클라이언트가 서버에 접속하지 못하게 될 수도 있다. 아찔한 일이 아닐 수 없다.

 어찌 되었건, 결과적으로는 팀장님과 의논을 통해 Host 모드로 컨테이너를 실행함으로써 문제를 해결했다. 

- Bridge Network 대역대를 바꿀 수도 있으나, 개발 환경일 때와 달리 운영 환경일 때도 이 방법을 선택할 수는 없다. 시스템이 운영되는 환경이 사이트 별로 모두 다를 텐데, 각각의 사이트 별로 네트워크 설정이 어떻게 되어 있을지 알 수 없기 때문이다. 
- 시스템 운영 환경 별 네트워크 설정이 잘 되어 있다는 가정 하에, Host 네트워크 스택을 그대로 이용하는 것이 좋다고 판단했다. 다만 이 경우 Host 별로 포트 관리가 필요할 수는 있다.



<br>



네트워크는 항상 어렵지만, 어렵다고 미뤄만 둔다면 이런 문제를 수도 없이 겪게될 것이다. 정말로 공부를 해야 한다.

