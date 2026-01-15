---
title:  "[tcpdump] tcpdump를 사용하며 겪었던 문제 해결하기"
excerpt: tcpdump로 패킷을 분석할 때 마주하는 문제들
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - tcpdump
  - connection
  - wireshark
  - network
  - 네트워크
---



# tcpdump 삽질기

 회사에서 Nginx와 fastcgi 모듈을 이용해 서버를 개발하던 중, 499, 502 에러를 마주하게 되어, connection이 어디서 끊어지는지 알기 위해 패킷 분석 프로그램 tcpdump를 사용하게 되었다. 그 과정에서 겪었던 사소한 문제들과, 이를 어떻게 해결했는지 정리한다. 

<br>



## 권한 에러

 

 tcpdump를 사용하기 위해 명령어를 치면, 아래와 같이 `Operation not permitted`와 같은 오류 메시지를 마주한다.

```bash
eraser@Eraser-laptop:~$ tcpdump -w tcpdump.log port 8888
tcpdump: wlp0s20f3: You don't have permissions to capture on that device
(socket: Operation not permitted)
```

 tcpdump 명령 위치인 `/usr/sbin/tcpdump`에서 파일 소유자와 소유 그룹 및 권한을 확인해 보면, 소유자 및 소유 그룹이 `root`, `root`임을 알 수 있다. 즉, 위의 상황은 non-root user(eraser)로 접속해 tcpdump 프로그램을 사용해서 나타난 문제다.

```bash
eraser@Eraser-laptop:/usr/sbin$ ls -al | grep tcpdump
-rwxr-xr-x  1 root root   1044232 Jan  1  2020 tcpdump
```

<br>

 손쉬운 해결책은 `sudo` 명령어를 붙여 root 권한으로 프로그램을 실행하는 것이다. 혹은 `su`를 통해 root 계정으로 로그인해서 tcpdump 프로그램을 사용해도 된다. 그렇지만 이렇게 권한 에러를 마주칠 때는 [**이 때**](https://sirzzang.github.io/dev/Dev-osgi-permission-denied-error/)처럼 파일 소유 그룹에 사용자를 추가해주는 것이 더 정석적인 해결책 같다. [이 글](https://www.linuxtutorial.co.uk/tcpdump-eth0-you-dont-have-permission-to-capture-on-that-device/)을 참고해 아래와 같이 해결했다.

- `pcap` 그룹 생성 후, tcpdump를 사용하고자 하는 root가 아닌 사용자를 `pcap` 그룹에 추가

  ```bash
  groupadd pcap
  usermod -a -G pcap eraser # pcap 그룹에 eraser 사용자를 추가하라
  ```

  ```bash
  # 그룹에 추가된 것을 확인
  eraser@Eraser-laptop:~$ cat /etc/group | grep pcap
  pcap:x:1001:eraser,tcpdump
  ```

- tcpdump의 소유 그룹을 변경하고 권한 설정

  ```bash
  chgrp pcap /usr/sbin/tcpdump
  chmod 750 /usr/sbin/tcpdump # tcpdump 소유 그룹에 읽기 및 실행 권한 설정
  ```

- 필요한 권한 설정

  - `CAP_NET_RAW`: 네트워크 작업 시 권한 있는 소켓 옵션, 멀티 캐스팅, 인터페이스 구성, 라우팅 테이블 수정 등에 사용되는 권한
  - `CAP_NET_ADMIN`: RAW 및 PACKET 소켓의 사용 허용에 사용되는 권한

  ```bash
  setcap cap_net_raw,cap_net_admin=eip /usr/sbin/tcpdump
  ```

  > *참고*: 네트워크 권한 설정
  >
  >  참고했던 블로그 글에서 권한을 설정하라고 하기에 따라서 진행했는데, [**여기**](https://dongdong-2.tistory.com/4)를 참고하니 패킷 캡쳐 시 설정해 주어야 하는 권한인 듯하다. Elastic stack 중 Packetbeat를 사용하려고 했을 때에도 저 두 권한을 설정해주었어야 했던 기억이 있다.

 위와 같이 필요한 설정을 마치면 사용자 계정에서도 tcpdump 명령을 사용할 수 있다. 다만, 바로 적용되지 않고 재부팅하거나 터미널을 다시 시작해야 될 수도 있을 듯하다. 내 경우는 재부팅 후에 사용할 수 있었다.

<br>



## 패킷을 잡을 수 없음



 권한 설정도 제대로 했는데, tcpdump 실행 시 패킷이 캡쳐되지 않는다.

``` bash
eraser@Eraser-laptop:~$ tcpdump -w tcpdump.pcap port 8888
tcpdump: listening on wlp0s20f3, link-type EN10MB (Ethernet), capture size 262144 bytes
^C0 packets captured
0 packets received by filter
0 packets dropped by kernel
```

<br>

 네트워크 인터페이스의 문제였다. 위와 같이 tcpdump에 네트워크 인터페이스 옵션을 아무 것도 주지 않게 되면, tcpdump는 default 네트워크 인터페이스에 대해 패킷 분석을 수행한다. 하지만 현재 서버 개발을 하면서 loopback IP address를 사용하고 있기 때문에, `ifconfig`를 통해 loopback 네트워크 인터페이스를 확인한 후, 다시 실행한다.

- 네트워크 인터페이스 확인: `lo` 네트워크 인터페이스를 사용해야 함

  ```bash
  eraser@Eraser-laptop:~$ ifconfig
  br-127c8b3d9f13: flags=4099<UP,BROADCAST,MULTICAST>  mtu 1500
          inet 172.18.0.1  netmask 255.255.0.0  broadcast 172.18.255.255
          ether 02:42:53:f3:77:e6  txqueuelen 0  (Ethernet)
          RX packets 0  bytes 0 (0.0 B)
          RX errors 0  dropped 0  overruns 0  frame 0
          TX packets 0  bytes 0 (0.0 B)
          TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0
          
  (중략)
  
  docker0: flags=4099<UP,BROADCAST,MULTICAST>  mtu 1500
          inet 172.17.0.1  netmask 255.255.0.0  broadcast 172.17.255.255
          ether 02:42:d2:3a:92:71  txqueuelen 0  (Ethernet)
          RX packets 0  bytes 0 (0.0 B)
          RX errors 0  dropped 0  overruns 0  frame 0
          TX packets 0  bytes 0 (0.0 B)
          TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0
  
  lo: flags=73<UP,LOOPBACK,RUNNING>  mtu 65536
          inet 127.0.0.1  netmask 255.0.0.0
          inet6 ::1  prefixlen 128  scopeid 0x10<host>
          loop  txqueuelen 1000  (Local Loopback)
          RX packets 4079  bytes 933561 (933.5 KB)
          RX errors 0  dropped 0  overruns 0  frame 0
          TX packets 4079  bytes 933561 (933.5 KB)
          TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0
  
  wlp0s20f3: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
          inet 192.168.0.43  netmask 255.255.255.0  broadcast 192.168.0.255
          inet6 fe80::2a21:77f7:aa38:13f5  prefixlen 64  scopeid 0x20<link>
          ether 94:e6:f7:e6:47:31  txqueuelen 1000  (Ethernet)
          RX packets 63728  bytes 71342318 (71.3 MB)
          RX errors 0  dropped 0  overruns 0  frame 0
          TX packets 26810  bytes 9811978 (9.8 MB)
          TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0
  ```

- 다시 실행

  ```bash
  eraser@Eraser-laptop:~$ tcpdump -w tcpdump.pcap -i lo -nn -vvv -tttt # 네트워크 인터페이스 옵션을 lo로 설정
  tcpdump: listening on lo, link-type EN10MB (Ethernet), capture size 262144 bytes
  ^C160 packets captured
  324 packets received by filter
  0 packets dropped by kernel
  ```

  

<br>

## 패킷 분석 출력 파일을 읽을 수 없음



 `cat`이나 `vi`를 통해 tcpdump 패킷 분석 출력 파일을 읽으려고 하면, 아래와 같이 이상한 문자가 뜬다.

![tcpdump-pcap-error]({{site.url}}/assets/images/tcpdump-pcap-error.png){: .align-center}

<br>

 아래와 같이 tcpdump 명령어를 사용해 읽어 주면 된다.

```bash
tcpdump -r tcpdump.pcap
```

<br>



 여전히 권한 에러가 날 수 있다. 만약 위에서와 같이 tcpdump 파일에 대한 권한 에러가 난다면, tcpdump 파일 소유 그룹을 변경하면 된다. 그게 아니라 출력 파일 자체에 대한 `Permission Denied` 에러가 날 경우, tcpdump를 통한 패킷 분석 명령 실행 시, 출력될 패킷 분석 파일의 소유자를 `-Z` 옵션을 통해 지정해 주면 된다.

```bash
tcpdump -w tcpdump.pcap -i lo -nn -vvv -tttt -Z eraser # -Z 옵션을 사용하면 된다
```

