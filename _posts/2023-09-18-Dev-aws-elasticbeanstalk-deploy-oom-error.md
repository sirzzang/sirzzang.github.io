---
title:  "[AWS] EC2 배포 오류"
excerpt: Elastic Beanstalk을 이용해 EC2에 이미지를 배포하던 도중 발생한 OOM 에러
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - AWS
  - Elastic Beanstalk
  - EC2
  - Go
---

<br>

 사이드 프로젝트에서 만든 백엔드 서버 어플리케이션을 Elastic Beanstalk을 이용해 EC2에 배포하는 도중, 그 전에는 전혀 경험하지 못했던 배포 오류가 발생했다.

```bash
ERROR: ServiceError - Failed to deploy application.
```

 버그 해결을 위해 기존 코드를 수정한 후, `eb deploy`를 이용해 배포했는데, 코드만 수정했을 뿐인데 갑자기 배포에 실패했다.

<br>

# 상황

현재 백엔드 서버 어플리케이션은 Elastic Beanstalk을 이용해 EC2 인스턴스에 target 브랜치의 가장 최근 commit을 기준으로 Docke Image를 배포해 컨테이너를 실행한다. Docker Image를 만들기 위한 Dockerfile은 아래와 같다.

```dockerfile
FROM golang:1.19-alpine
COPY . ${HOME}/backend/
WORKDIR ${HOME}/backend
RUN mkdir -p build
EXPOSE 8080
RUN go build -o build/bewell-backend ./cmd/api
WORKDIR ${HOME}/backend/build
ENTRYPOINT [ "./bewell-backend" ]
```

AWS Management Console을 이용해 Elastic Beanstalk Event를 확인하니, 아래와 같이 Docker image 빌드에 실패했다는 로그를 확인할 수 있다.

![aws-elasticbeanstalk-events]({{site.url}}/assets/images/aws-elasticbeanstalk-events.png){: .align-center}

Docker 엔진 로그를 확인하기 위해 `eb-engine.log`를 확인한다. Elastic Beanstalk의 Full Log를 다운로드하여 확인할 수 있다.

![aws-elasticbeanstalk-request-full-logs]({{site.url}}/assets/images/aws-elasticbeanstalk-request-full-logs.png){: .align-center}

Elastic Beanstalk Full Log를 다운로드하면, 아래와 같은 디렉토리 구조를 확인할 수 있다.

- `var/log/eb-docker`: 현재 실행 중인 docker container에서 발생하는 로그
- `var/log/healthd`: Elastic Beanstalk environment health check 발생 로그
- `var/log/nginx`: Nginx access, error 레벨 로그
- `eb-engine.log`: EC2 인스턴스 플랫폼 엔진 로그

> *참고*: full log
>
> 위와 같은 Log 구조는 Elastic Beanstalk envrironment 상태가 정상적(Ready)일 때 확인할 수 있는 구조이다. 글을 쓰는 시점에는 environment가 정상이라 위와 같은 로그 구조를 확인할 수 있다. 그러나 오류가 발생했을 시점에는 정상적이지 않았기(Degraded) 때문에, `eb-docker` 디렉토리가 없었다. 애초에 배포에 실패해서 docker container가 실행 중이지 않았기 때문이다. 그러나 그 상태이더라도, `eb-engine` 로그는 확인할 수 있다.

`eb-engine.log`를 확인해 보자.

![aws-elasticbeanstalk-ebengine-log]({{site.url}}/assets/images/aws-elasticbeanstalk-ebengine-log.png){: .align-center}

Dockerfile을 실행해 Docker Image를 빌드하던 중, OOM 에러가 발생했음을 알 수 있다.

<br>

# 해결

해결책은 아주 간단했다. EC2 인스턴스의 메모리를 늘려 주었다. 

- 기존에는 `t2.micro` 메모리를 이용하고 있었는데, 해당 메모리 크기는 1GiB이다.
- `t3.small`을 이용하도록 변경했다. 해당 메모리 기본 크기는 2GiB이다.

![aws-ec2-memory]({{site.url}}/assets/images/aws-ec2-memory.png)

이후 배포에 성공했다. 해결책은 간단했지만, 어플리케이션 빌드 과정에서 OOM 에러가 발생하는 것은 처음 보는 것이었다. 로컬에서는 항상 PC 혹은 노트북의 메모리를 이용했기 때문에, 실행 중인 어플리케이션에서 OOM 에러를 본 적은 있어도 빌드 과정에서 본 적은 없었다. 클라우드 환경에서 배포했기 때문에 얻을 수 있었던 신박한(?) 경험이다. 

> *참고*: SWAP 메모리를 이용한 해결 방법
>
> 찾아 보니, 빌드 과정에서 메모리 에러가 나는 경우가 꽤 있나 보다. EC2 인스턴스 자체의 메모리 용량을 늘리지 않고, 스왑 메모리를 할당하는 방법도 있다고 한다.
>
> - [Instance store swap volumes](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-store-swap-volumes.html)
> - [AWS-EC2-메모리-스왑](https://velog.io/@shawnhansh/AWS-EC2-%EB%A9%94%EB%AA%A8%EB%A6%AC-%EC%8A%A4%EC%99%91)
>   - 실제로 이 링크를 찾아 보니, 우분투에서도 메모리가 1GiB 이하일 경우 스왑 메모리를 사용하는 것을 권장한다고 한다.
>   - 애초에 1GiB란 크기 자체가 작은 메모리 크기가 아닐까 하는 생각도 든다.



<br>

# 삽질기

처음에는 로그 파일을 확인해 볼 생각을 못 했다. 갑자기 배포가 실패하길래, `뭐지?` 하고 Elastic Beanstalk Health 탭을 먼저 확인했다.

![aws-elasticbeanstalk-health]({{site.url}}/assets/images/aws-elasticbeanstalk-health.png){: .align-center}

 두 가지 문구가 있었는데, 갑자기 배포에 실패해서 판단력이 흐려졌는지 어쨌는지, 두 번째 문구에 꽂혀 버렸다. 배포가 실패했다는 첫 번째 문구는 무시한 채.

 읽어 보니 뭔가 어플리케이션 배포 버전이 안 맞는다는 것 같다. 이 문구로 구글링을 해서 이것 저것 링크를 발견했는데, 버전을 맞춰서 배포를 해야 한다거나, Elastic Beanstalk에서 업로드한 기존 배포 파일을 삭제해 줘야 한다거나, 하는 등의 해결책들이 있었다. 그래서 시도했던 일들은 다음과 같은 것들이 있다.

- S3에 있는 elastic beanstalk 관련 config 파일 삭제해 보기
- S3에 있는 elastic beanstalk 업로드 파일 삭제해 보기
- deployment id 찾아 보기
- ...

 지금 생각해 보면, 애초에 OOM 에러 때문에 배포가 실패했던 것이 근본 원인이다. 그 덕분에 Elastic Beanstalk 환경에서 가장 최근에 배포에 성공한 application version에서의 deployment id와, 현재 배포하고자 하는 application version의 deployment id가 달라서 application version이 맞지 않을 수밖에 없는 것이다. 

 한참 동안 삽질했는데, **결국 로그를 잘 읽는 것이 답이었다**.
