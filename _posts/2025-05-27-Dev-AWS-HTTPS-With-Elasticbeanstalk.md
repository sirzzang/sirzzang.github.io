---
title:  "[AWS] AWS elastic beanstalk 환경 https 설정"
excerpt: AWS elastic beanstalk 환경에 https를 설정해 보자
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - https
  - AWS
  - Elastic Beanstalk
  - EC2
---

<br>

사이드 프로젝트에서 AWS에 배포한 API 서버에 https를 적용한 과정을 정리한다. 

<br>

# 개요

- 클라이언트: 웹 어플리케이션
  - vercel을 이용해, https 적용하여 배포되어 있음
- 백엔드 API 서버: AWS elastic beanstalk을 이용해 배포되어 있음
  - 도메인 적용되어 있음
- 해당 클라이언트에서 https가 적용되지 않은 API 서버로 요청을 보낼 수 없음
  - 브라우저 보안 정책에 의해 막혀 있음
  - [Origin에 대한 고찰](https://sirzzang.github.io/dev/Dev-Origin-SOP-CORS/)을 참고하면, 보안 연결이 적용된 Origin에서 보안 연결이 적용되지 않은 Origin으로 요청하여 자원을 로드하는 것은 옳지 않음
- 작업 내용: AWS certificate manager와 Route 53 서비스를 이용해, AWS elastic beanstalk 환경에 https를 설정함
  - certificate manager를 이용해 HTTPS 인증서 발급
  - Route 53 서비스에 DNS 레코드 설정
  - Elastic Beanstalk 환경 Listener 설정

<br>



# 작업



## 1. AWS certificate manager에서 인증서 생성

![elasticbeanstalk-https-certificate-manager-1]({{site.url}}/assets/images/elasticbeanstalk-https-certificate-manager-1.png){: .align-center}

![elasticbeanstalk-https-certificate-manager-2]({{site.url}}/assets/images/elasticbeanstalk-https-certificate-manager-2.png){: .align-center}

기존에 부여한 도메인을 사용했다. 



> *참고*: elastic beanstalk에서 부여한 도메인 사용 시
>
> ![elasticbeanstalk-https-certificate-manager-error]({{site.url}}/assets/images/elasticbeanstalk-https-certificate-manager-error.png){: .align-center}
>
> Elastic Beanstalk 환경 생성 시, 기본으로 부여되는 도메인이 있는데, 해당 도메인을 사용하면 에러가 발생한다.





<br>

## 2. Route 53 CNAME 레코드 생성

![elasticbeanstalk-https-certificate-manager-3]({{site.url}}/assets/images/elasticbeanstalk-https-certificate-manager-3.png){: .align-center}

해당 인증서의 도메인 검증을 위한 CNAME DNS 레코드를 생성하기 위해, `Create Record in Route 53` 버튼을 클릭한다. 

<br>

![elasticbeanstalk-https-certificate-manager-4]({{site.url}}/assets/images/elasticbeanstalk-https-certificate-manager-4.png){: .align-center}

미리 연결하기 쉽게 되어 있기 때문에, 체크 박스에 체크만 해 주면 된다. CNAME 레코드를 생성하지 않았기 때문에, 해당 도메인에 대한 검증 상태가 `pending`인 것을 확인할 수 있다.



<br>

![elasticbeanstalk-https-certificate-manager-4]({{site.url}}/assets/images/elasticbeanstalk-https-certificate-manager-5.png){: .align-center}

DNS 레코드가 생성이 완료되었는지 확인한다.

<br>

## 3. Elastic Beanstalk Listener 등록



![elasticbeanstalk-https-listener]({{site.url}}/assets/images/elasticbeanstalk-https-listener.png){: .align-center}

이제 Elastic Beanstalk 환경에 https 연결을 위해 443 포트에 대한 Listener 설정을 해 준다. 보안을 위해, HTTP 연결에 대한 listener 설정은 해제한다.



<br>

# 결과

https 요청을 보내 보면 응답이 잘 돌아 오는 것을 확인할 수 있다.

```bash
~$ curl -X GET https://adminapi.<<main-domain>>
{"message":"Hello, World!"}
```

HTTP 연결에 대한 listener 설정을 해제했기 때문에, HTTP 연결 시 아무런 응답도 받을 수 없다.

```bash
~$ curl -X GET http://adminapi.<<main-domain>> # 응답 오지 않음
```



