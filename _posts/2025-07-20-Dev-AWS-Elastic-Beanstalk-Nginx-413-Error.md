---
title:  "[AWS] AWS elastic beanstalk 환경 413 Entity Too Large 에러 해결"
excerpt: AWS elastic beanstalk 환경에서 발생하는 413 Entity Too Large 에러를 해결해 보자
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

사이드 프로젝트에서 Elastic Beanstalk을 이용해 EC2에 배포한 백엔드 서버에서 발생한 413 Request Entity Too Large 에러를 해결한 과정을 정리한다.

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

Elastic Beanstalk은 어플리케이션 [리버스 프록시 서버로 Nginx를 이용](https://docs.aws.amazon.com/ko_kr/elasticbeanstalk/latest/dg/java-se-nginx.html)한다. 실제로 EC2에 직접 접속해 보면, 아래와 같이 Nginx가 구동되고 있는 것을 확인할 수 있다.

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
Last login: Fri Jul 11 08:13:01 2025 from 211.171.190.220
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
[ec2-user@ip-172-31-19-40 nginx]$ cat nginx.conf
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

- Elastic Beanstalk 배포 후, EC2에 접속하여 Nginx 설정을 변경함
- Elastic Beanstalk 배포 과정에서, Nginx 설정을 변경함

애초에 인프라 관리의 번거로움을 덜기 위해 Elastic Beanstalk을 사용했는데, 첫 번째 방법을 채택하는 것은 매우 비효율적이기 때문에, 두 번째 방법을 선택했다. 

<br>

결론적으로, Nginx 설정을 변경하기 위해(참고: [Configuring Nginx](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/platforms-linux-extend.proxy.html) 아래와 같이 Elastic Beanstalk에 업로드하는 어플리케이션 배포 패키지 내에 설정 파일을 두면 된다.

```bash
.platform/
  ├─ nginx/conf.d/
  |	 └─custom.conf # nginx 설정 파일
  └─ 00_nginx.config # elastic beanstalk 실행 설정 파일
```

- custom.conf
  ```bash
  client_max_body_size 10M;
  ```
- 00_nginx.config
  ```yaml
  container_commands:
      00_reload_nginx:
          command: "service nginx reload"
  ```



<br>

## .platform 

`.platform` 디렉토리는 Elastic Beanstalk에 의해서 인식되는 특별한 용도의 hook을 모아 놓는다. 즉, EB 환경의 배포 라이프라사이클 각 단계에서 적용할 수 있는 platform customization hook이 위치한다.

 Elastic Beanstalk 환경 플랫폼 별로 다를 수 있으나, 다음과 같은 하위 디렉토리가 있을 수 있다. 

- `.platform/hooks/`: EB lifecycle 단계(prebuild, postbuild, predeploy, postdeploy)마다 특정 스크립트를 실행할 수 있음
- `.platform/nginx/conf.d`: default nginx 추가 설정을 위한 config 파일 디렉토리
- `.platform/nginx/nginx.conf`: Nginx 기본 설정 변경
  - 다만, 이 파일을 직접적으로 변경하는 것은 권장되지 않고, `nginx/conf.d` 디렉토리를 이용하는 것이 안전함

- `.platform/*.config`: EB 컨테이너 커맨드, 패키지 등 실행 관련 설정 파일
  - YAML 형식으로, `container_commands`, `packages`, `files`, `services` 등의 키를 가질 수 있음
  - config 파일의 numeric prefix는 실행 순서를 컨트롤함
    - EB 프로세스는 lexical order에 따라 .config 파일들을 실행함
    - 실행 순서를 강제하기 위해, config 파일에 numeric prefix를 붙이는 scheme이 사용됨
    - 예를 들어, 아래와 같은 구조를 사용할 수 있음
      ```bash
      .platform/
        ├─ 00_nginx.config   # reload nginx first
        ├─ 01_packages.config   # install extra OS packages
        ├─ 02_app.config        # run app-specific setup
        └─ nginx/conf.d/custom.conf
      ```



<br>

# 결론



결과적으로 문제를 어떻게 해결하기 위한 설정 파일 구조를 뜯어 보면 다음과 같다.
- `.platform`: EB 환경 커스텀 디렉토리
  - `nginx/conf.d/`: Nginx config 디렉토리
    - `custom.conf`: 문제가 발생했던 client_max_body_size 관련 설정을 변경한 설정 파일
  - `00_nginx_config`: EB 배포 과정에서 적용하고자 하는 설정 사항
    - numeric prefix로 실행 순서를 제어하나, 현재 상황에서는 한 개만 있음



<br>

AWS는 편리하긴 하지만, 그만큼 잘 알고 써야 하니 문제 해결을 하기 위해서는 공식 문서~~(와 GPT)~~의 도움을 잘 받아 보도록 하자.
- [https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/platforms-linux-extend.html](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/platforms-linux-extend.html)



