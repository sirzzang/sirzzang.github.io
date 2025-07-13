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

Elastic Beanstalk은 어플리케이션 리버스 프록시 서버로 Nginx를 이용한다. 실제로 EC2에 직접 접속해 보면, 아래와 같은 nginx 설정으로 nginx가 구동되고 있는 것을 확인할 수 있다.

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





