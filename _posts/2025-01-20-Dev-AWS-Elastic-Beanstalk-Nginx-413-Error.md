---
title:  "[AWS] AWS Elastic Beanstalk 환경 413 Entity Too Large 에러 해결"
excerpt: AWS Elastic Beanstalk 환경에서 발생하는 413 Entity Too Large 에러를 해결해 보자
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - AWS
  - Elastic Beanstalk
  - Nginx
---

<br>

사이드 프로젝트에서 Elastic Beanstalk을 이용해 EC2에 배포한 백엔드 서버에서 발생한 413 Request Entity Too Large 에러를 해결한 과정을 정리한다. EB 환경의 배포 자동화에 대해서는 [GitHub Actions를 이용한 EB 배포]({% post_url 2024-12-14-Dev-AWS-Elastic-Beanstalk-CICD-Github-Actions %}) 포스트를 참고한다.

<br>

# 배경지식

## Elastic Beanstalk이란

Elastic Beanstalk(EB)은 그 자체로 특별한 런타임이 아니라, EC2 인스턴스(Amazon Linux AMI 기반) 위에 배포, 스케일링, 모니터링을 자동화해주는 오케스트레이션 레이어다. EB 환경의 내부는 일반 EC2와 동일하며, Nginx, OS 설정 등도 Amazon Linux의 구조를 그대로 따른다.

## .platform 디렉토리

이 글에서 다루는 `.platform` 디렉토리는 EB만의 개념이 아니라 Amazon Linux 2/2023 플랫폼의 커스터마이징 구조다. EB는 이를 인식하여 배포 과정에서 자동으로 적용해주는 역할을 한다.

<br>

# TL;DR

- Elastic Beanstalk 환경에서 파일 업로드 시 413 Request Entity Too Large 에러가 발생했다
- 원인은 리버스 프록시인 Nginx의 `client_max_body_size` 기본값이 1MB로 설정되어 있기 때문이다
- `.platform/nginx/conf.d/` 디렉토리에 커스텀 설정 파일을 추가하여 해결했다

<br>

# 문제

클라이언트에서 파일을 업로드하려고 했을 때 아래와 같은 에러가 발생한다.

```html
<head>
    <title>413 Request Entity Too Large</title>
</head>
<body>
    <center>
        <h1>413 Request Entity Too Large</h1>
    </center>
    <hr>
    <center>nginx/1.26.3</center>
</body>
</html>
```

<br>

# 원인

Nginx 이용 시, Request Body의 최대 크기 제한으로 인해 나타나는 전형적인 오류 상황이다. 

<br>

Elastic Beanstalk은 어플리케이션 [리버스 프록시(Reverse Proxy) 서버로 Nginx를 이용](https://docs.aws.amazon.com/ko_kr/elasticbeanstalk/latest/dg/java-se-nginx.html)한다. 실제로 EC2에 직접 접속해 보면, 아래와 같이 Nginx가 구동되고 있는 것을 확인할 수 있다.

> *참고*: EC2 SSH 접속 시 주의 사항
>
> pem 키 파일의 권한이 너무 열려 있으면(`0777` 등) SSH 접속이 거부된다. 반드시 `chmod 400`으로 권한을 제한해야 한다.
> ```bash
> ~$ ssh -i "keypair.pem" root@<ec2_public_dns>
> @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
> @         WARNING: UNPROTECTED PRIVATE KEY FILE!          @
> @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
> Permissions 0777 for 'keypair.pem' are too open.
> Load key "keypair.pem": bad permissions
> Permission denied (publickey,gssapi-keyex,gssapi-with-mic).
>
> ~$ chmod 400 keypair.pem
> ```
> 또한, EC2 인스턴스에 `root`로 접속하면 `ec2-user`를 사용하라는 안내와 함께 연결이 종료된다.
> ```bash
> ~$ ssh -i "keypair.pem" root@<ec2_public_dns>
> Please login as the user "ec2-user" rather than the user "root".
> Connection to <ec2_public_dns> closed.
> ```

```bash
eraser@DESKTOP-FAIGO7U~:$ ssh -i "keypair.pem" <ec2_username>@<ec2_public_ip>
  _____ _           _   _      ____                       _        _ _
 | ____| | __   ___| |_(_) ___| __ )  ___  __ _ _ __  ___| |_ __ _| | | __
 |  _| | |/ _ \/ __| __| |/ __|  _ \ / _ \/ _\ | '_ \/ __| __/ _\ | | |/ /
 | |___| | (_| \__ \ |_| | (__| |_) |  __/ (_| | | | \__ \ || (_| | |   <
 |_____|_|\__,_|___/\__|_|\___|____/ \___|\__,_|_| |_|___/\__\__,_|_|_|\_\

 Amazon Linux 2023 AMI

 This EC2 instance is managed by AWS Elastic Beanstalk. Changes made via SSH
 WILL BE LOST if the instance is replaced by auto-scaling. For more information
 on customizing your Elastic Beanstalk environment, see our documentation here:
 http://docs.aws.amazon.com/elasticbeanstalk/latest/dg/customize-containers-ec2.html

   ,     #_
   ~\_  ####_        Amazon Linux 2023
  ~~  \_#####\
  ~~     \###|
  ~~       \#/ ___   https://aws.amazon.com/linux/amazon-linux-2023
   ~~       V~' '->
    ~~~         /
      ~~._.   _/
         _/ _/
       _/m/'
Last login: Fri Jul 11 08:13:01 2025 from 203.0.113.10
[<ec2_username>@<ec2_host_name>~]$ ls
[<ec2_username>@<ec2_host_name> ~]$ cd /etc
[<ec2_username>@<ec2_host_name> etc]$ cd nginx
[<ec2_username>@<ec2_host_name> nginx]$ ls -al
total 132
drwxr-xr-x.  4 root root 16384 Jul 12 16:13 .
drwxr-xr-x. 86 root root 16384 Apr  9 12:24 ..
drwxr-xr-x.  3 root root   130 Jul 12 16:13 conf.d
-rw-r--r--.  1 root root    26 Jul 11 06:09 custom.conf
drwxr-xr-x.  2 root root     6 Feb 11 02:00 default.d
-rw-r--r--.  1 root root  1077 Feb 11 02:00 fastcgi.conf
-rw-r--r--.  1 root root  1077 Feb 11 02:00 fastcgi.conf.default
-rw-r--r--.  1 root root  1007 Feb 11 02:00 fastcgi_params
-rw-r--r--.  1 root root  1007 Feb 11 02:00 fastcgi_params.default
-rw-r--r--.  1 root root  2837 Feb 11 02:00 koi-utf
-rw-r--r--.  1 root root  2223 Feb 11 02:00 koi-win
-rw-r--r--.  1 root root 35272 Feb  1  2023 mime.types
-rw-r--r--.  1 root root  5349 Feb 11 02:00 mime.types.default
-rw-r--r--.  1 root root  1590 Jul 12 16:13 nginx.conf
-rw-r--r--.  1 root root  2656 Feb 11 02:00 nginx.conf.default
-rw-r--r--.  1 root root   636 Feb 11 02:00 scgi_params
-rw-r--r--.  1 root root   636 Feb 11 02:00 scgi_params.default
-rw-r--r--.  1 root root   664 Feb 11 02:00 uwsgi_params
-rw-r--r--.  1 root root   664 Feb 11 02:00 uwsgi_params.default
-rw-r--r--.  1 root root  3610 Feb 11 02:00 win-utf
```



<br>

이 때, 리버스 프록시로 사용하는 Nginx가 사용하는 파일 업로드 설정이 1MB여서 이러한 상황이 발생한다. EC2에 접속하여 nginx 설정 파일을 확인해 보면, 파일 업로드에 대한 설정은 크게 적용되어 있지 않음을 알 수 있는데, 이 경우 Nginx 기본 설정 값인 1MB가 적용된다.

- [nginx client_max_body_size 설정](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size): 클라이언트가 너무 큰 사이즈의 요청을 보내지 못하게 하기 위한 목적으로, request의 Content-Length 헤더값이 client_max_body_size에 설정된 값을 넘을 수 없도록 제한함

```bash
[<ec2_username>@<ec2_host_name> nginx]$ cat nginx.conf
# Elastic Beanstalk Nginx Configuration File

user  nginx;
worker_processes  auto;
error_log  /var/log/nginx/error.log;
pid        /var/run/nginx.pid;
worker_rlimit_nofile    200000;

events {
    worker_connections  1024;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    access_log    /var/log/nginx/access.log;


    log_format  main  '$remote_addr - $remote_user [$time_local] "$request" '
                          '$status $body_bytes_sent "$http_referer" '
                          '"$http_user_agent" "$http_x_forwarded_for"';

    include  conf.d/*.conf;

    map $http_upgrade $connection_upgrade {
            default       "upgrade";
    }

    server {
        listen 80 default_server;
        gzip on;
        gzip_comp_level 4;
        gzip_types text/plain text/css application/json application/x-javascript text/xml application/xml application/xml+rss text/javascript;

        access_log    /var/log/nginx/access.log main;

        location / {
            proxy_pass            http://docker;
            proxy_http_version    1.1;

            proxy_set_header    Connection             $connection_upgrade;
            proxy_set_header    Upgrade                $http_upgrade;
            proxy_set_header    Host                   $host;
            proxy_set_header    X-Real-IP              $remote_addr;
            proxy_set_header    X-Forwarded-For        $proxy_add_x_forwarded_for;
        }

        # Include the Elastic Beanstalk generated locations
        include conf.d/elasticbeanstalk/*.conf;
    }
}
```





<br>

# 해결

Nginx를 프록시 혹은 리버스 프록시로 사용하다 보면 흔하게 겪는 문제로, Nginx 설정을 변경해 주면 된다. 다만, 직접 Nginx를 컨트롤할 수 없기 때문에, AWS 인프라 상에서 변경할 수 있는 방법을 찾아야 한다. 아래와 같은 방법을 생각해 볼 수 있다.

1. Elastic Beanstalk 배포 후, EC2에 접속하여 Nginx 설정을 변경함
2. Elastic Beanstalk 배포 과정에서, Nginx 설정을 변경함

애초에 인프라 관리의 번거로움을 덜기 위해 Elastic Beanstalk을 사용했는데, 첫 번째 방법을 채택하는 것은 매우 비효율적이기 때문에, 두 번째 방법을 선택했다. 

<br>

결론적으로, Nginx 설정을 변경하기 위해(참고: [Configuring the reverse proxy](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/platforms-linux-extend.proxy.html)) 아래와 같이 Elastic Beanstalk에 업로드하는 어플리케이션 배포 패키지 내에 설정 파일을 두면 된다.

```bash
.platform/
  └─ nginx/conf.d/
     └─ custom.conf
```

- custom.conf: Nginx의 `client_max_body_size` 값을 변경하는 설정 파일
  ```bash
  client_max_body_size 50M;
  ```

`.platform/nginx/conf.d/`에 위치한 `.conf` 파일은 배포 시 Elastic Beanstalk이 자동으로 Nginx 설정에 포함시키고 Nginx를 재시작한다. 이것만으로 문제가 해결된다.

> *돌아보기*: 당시에는 `.platform/` 하위에 `00_nginx.config` 파일도 함께 두었다.
>
> ```bash
> .platform/
>   ├─ nginx/conf.d/
>   |  └─ custom.conf
>   └─ 00_nginx.config  # 아래 내용의 설정 파일
> ```
> ```yaml
> # 당시에 설정한 .platform/00_nginx.config
> container_commands:
>     00_reload_nginx:
>         command: "service nginx reload"
> ```
>
> 그러나 `container_commands`를 사용하는 `.config` 파일은 `.ebextensions/` 디렉토리에서만 인식되는 형식이다. `.platform/` 루트에 두면 Elastic Beanstalk이 이를 처리하지 않으므로, 이 파일은 사실상 무시되고 있었다. 실제 문제 해결은 `custom.conf` 하나만으로 이루어진 셈이다. `.platform`과 `.ebextensions`의 역할 차이는 아래에서 정리한다.



<br>

## .platform과 .ebextensions

Elastic Beanstalk 환경을 커스터마이징하는 방법은 크게 두 가지가 있다.

### .platform

`.platform` 디렉토리는 Amazon Linux 2/2023 기반 플랫폼의 커스터마이징 디렉토리로, Elastic Beanstalk이 배포 과정에서 이 구조를 인식하여 platform hook과 프록시 설정을 자동으로 적용한다.

- `.platform/hooks/`: 배포 lifecycle 단계(prebuild, predeploy, postdeploy)마다 실행할 스크립트
- `.platform/confighooks/`: 환경 설정 변경 시 실행할 스크립트
- `.platform/nginx/conf.d/`: Nginx 추가 설정 파일 디렉토리. 여기에 위치한 `.conf` 파일은 자동으로 Nginx 설정에 포함됨
- `.platform/nginx/nginx.conf`: Nginx 기본 설정 전체를 교체. 다만, 전체를 교체하는 것은 권장되지 않고, `nginx/conf.d/` 디렉토리를 이용하는 것이 안전함

### .ebextensions

`.ebextensions` 디렉토리는 이전 세대(Amazon Linux AMI)부터 사용되어 온 커스터마이징 방식으로, Amazon Linux 2/2023에서도 여전히 사용 가능하다. `.config` 확장자의 YAML 파일을 사용하며, `container_commands`, `packages`, `files`, `services` 등의 키를 지원한다.

```bash
.ebextensions/
  ├─ 00_nginx.config
  ├─ 01_packages.config
  └─ 02_app.config
```

- `.config` 파일은 lexical order(사전 순서)에 따라 실행되므로, numeric prefix로 실행 순서를 제어한다

> *참고*: `.platform` vs `.ebextensions` 사용 기준
>
> Amazon Linux 2/2023 플랫폼에서는 커스텀 코드 실행에 `.platform/hooks/`를 사용하고, Nginx 설정 변경에 `.platform/nginx/`를 사용하는 것이 AWS 권장 방식이다. `.ebextensions`는 CloudFormation 리소스 참조가 필요한 설정에 사용한다.
> - [Extending EB Linux platforms](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/platforms-linux-extend.html)



<br>

# 정리

문제를 해결한 건 `.platform/nginx/conf.d/custom.conf` 하나뿐이다.

- `.platform/nginx/conf.d/custom.conf`에 `client_max_body_size` 값을 설정하면, EB가 배포 과정에서 자동으로 Nginx 설정에 반영한다
- 당시 함께 두었던 `.platform/00_nginx.config`(`container_commands`)는 `.ebextensions/`에서만 인식되는 형식이므로 실제로는 동작하지 않았다

AWS는 편리하긴 하지만, 그만큼 잘 알고 써야 하니 문제 해결을 하기 위해서는 공식 문서~~(와 GPT)~~의 도움을 잘 받아 보도록 하자.

<br>

# 참고 링크

- [nginx `client_max_body_size` 설정](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size)
- [Configuring the reverse proxy](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/platforms-linux-extend.proxy.html)
- [Extending EB Linux platforms](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/platforms-linux-extend.html)

<br>
