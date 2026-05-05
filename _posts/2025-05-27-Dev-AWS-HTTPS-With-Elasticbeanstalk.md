---
title:  "[AWS] AWS Elastic Beanstalk 환경 HTTPS 설정"
excerpt: AWS Elastic Beanstalk 환경에 HTTPS를 설정해 보자.
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - HTTPS
  - AWS
  - Elastic Beanstalk
  - ACM
  - Route 53
---

<br>

사이드 프로젝트에서 AWS에 배포한 API 서버에 HTTPS를 적용한 과정을 정리한다. 

<br>

# TL;DR

- HTTPS가 적용된 클라이언트에서 HTTP 백엔드로 요청을 보낼 수 없어, Elastic Beanstalk 환경에 HTTPS를 설정했다
- AWS Certificate Manager(ACM)에서 인증서를 발급받고, Route 53에 DNS 검증용 CNAME 레코드를 생성한 뒤, EB 환경의 Load Balancer에 HTTPS Listener를 등록했다
- EB 기본 도메인(`*.elasticbeanstalk.com`)은 AWS 소유이므로 ACM 인증서 발급이 불가하다. 커스텀 도메인이 필요하다

<br>

# 개요

- 클라이언트: 웹 어플리케이션
  - vercel을 이용해, https 적용하여 배포되어 있음
- 백엔드 API 서버: AWS Elastic Beanstalk을 이용해 배포되어 있음
  - [도메인 연결]({% post_url 2025-05-26-Dev-AWS-Domain-With-Elasticbeanstalk %})이 적용되어 있음
- 해당 클라이언트에서 HTTPS가 적용되지 않은 API 서버로 요청을 보낼 수 없음
  - 브라우저 보안 정책에 의해 막혀 있음
  - [Origin에 대한 고찰]({% post_url 2025-05-10-CS-Origin-SOP-CORS %})을 참고하면, 보안 연결이 적용된 Origin에서 보안 연결이 적용되지 않은 Origin으로 요청하여 자원을 로드하는 것은 옳지 않음
- 작업 내용: AWS Certificate Manager(ACM)와 Route 53 서비스를 이용해, AWS Elastic Beanstalk 환경에 HTTPS를 설정함
  - ACM을 이용해 HTTPS 인증서 발급
  - Route 53 서비스에 DNS 레코드 설정
  - Elastic Beanstalk 환경의 Load Balancer에 HTTPS Listener 설정

<br>



# 작업



## 1. AWS Certificate Manager에서 인증서 생성

![elasticbeanstalk-https-certificate-manager-1]({{site.url}}/assets/images/elasticbeanstalk-https-certificate-manager-1.png){: .align-center}

![elasticbeanstalk-https-certificate-manager-2]({{site.url}}/assets/images/elasticbeanstalk-https-certificate-manager-2.png){: .align-center}

기존에 부여한 커스텀 도메인을 사용했다. DNS 검증(DNS Validation) 방식을 선택하면, ACM이 도메인 소유권 확인을 위한 CNAME 레코드를 제공한다. 이 CNAME 레코드를 DNS에 등록해 두면, 인증서 갱신도 자동으로 이루어진다.

> *참고*: Elastic Beanstalk 기본 도메인은 사용 불가
>
> ![elasticbeanstalk-https-certificate-manager-error]({{site.url}}/assets/images/elasticbeanstalk-https-certificate-manager-error.png){: .align-center}
>
> Elastic Beanstalk 환경 생성 시 기본으로 부여되는 도메인(`*.elasticbeanstalk.com`)에는 ACM 인증서를 발급받을 수 없다. ACM은 인증서 발급 시 도메인 소유권 증명을 요구하는데, 이는 DNS에 특정 CNAME 레코드를 추가하거나 관리자 이메일을 수신하는 방식으로 이루어진다. `*.elasticbeanstalk.com`의 DNS는 AWS가 관리하므로, 사용자가 소유권 검증용 레코드를 추가할 수 없어 인증서 발급이 불가하다. 이는 EB 도메인만의 제약이 아니라, 본인이 DNS를 제어할 수 없는 모든 도메인에 동일하게 적용되는 원리다. 따라서 HTTPS를 적용하려면 별도의 커스텀 도메인이 필요하다.





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

Elastic Beanstalk의 Load Balancer 환경에서, 외부 트래픽은 Load Balancer를 통해 EC2 인스턴스에 전달된다. Listener는 이 Load Balancer가 어떤 프로토콜/포트의 트래픽을 수신할지를 정의하는 설정이다.

![elasticbeanstalk-https-listener]({{site.url}}/assets/images/elasticbeanstalk-https-listener.png){: .align-center}

Elastic Beanstalk 환경의 Load Balancer에 HTTPS(443) 포트에 대한 Listener를 추가하고, 위에서 발급받은 ACM 인증서를 연결한다. 이 예시에서는 보안을 위해 HTTP(80) Listener 설정을 해제했다.



<br>

# 결과

HTTPS 요청을 보내 보면 응답이 잘 돌아 오는 것을 확인할 수 있다.

```bash
~$ curl -X GET https://adminapi.<<main-domain>>
{"message":"Hello, World!"}
```

HTTP Listener 설정을 해제했기 때문에, HTTP 연결 시 아무런 응답도 받을 수 없다.

```bash
~$ curl -X GET http://adminapi.<<main-domain>> # 응답 오지 않음
```

<br>

# HTTP → HTTPS 리다이렉트

위 설정에서는 HTTP Listener를 아예 제거했기 때문에, `http://`로 접근하면 응답이 오지 않는다. 실무에서는 HTTP로 접근한 사용자를 자동으로 HTTPS로 리다이렉트하는 것이 일반적이다.

Application Load Balancer(ALB)를 사용하는 경우, HTTP(80) Listener에 리다이렉트 규칙을 추가할 수 있다. EB 환경의 Load Balancer 설정에서 HTTP(80) Listener를 유지하되, 기본 동작(default action)을 "Redirect to HTTPS(443)"로 설정하면 된다.

Classic Load Balancer를 사용하는 경우에는 Load Balancer 수준에서 리다이렉트를 지원하지 않으므로, Nginx 설정에서 HTTP → HTTPS 리다이렉트를 처리해야 한다.

<br>

# 참고 링크

- [AWS Certificate Manager 공식 문서](https://docs.aws.amazon.com/acm/latest/userguide/acm-overview.html)
- [Configuring HTTPS for Elastic Beanstalk environment](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/configuring-https.html)
- [ALB HTTP to HTTPS redirect](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-listeners.html#redirect-actions)

<br>

