---
title:  "[AWS] AWS elastic beanstalk 환경 도메인 연결"
excerpt: AWS elastic beanstalk 환경에 도메인을 연동해 보자
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - domain
  - subdomain
  - AWS
  - Elastic Beanstalk
  - EC2
  - Route 53
  - GoDaddy
---

<br>

사이드 프로젝트에서 AWS에 배포한 API 서버에 도메인을 연결한 과정을 정리한다.

<br>

# 개요

- API 서버: AWS Elastic Beanstalk을 이용해 배포되어 있음
- 메인 도메인: [GoDaddy](https://kr.godaddy.com/) 서비스에서 구매함
- 작업 내용: [AWS Route 53](https://aws.amazon.com/ko/route53/) 서비스를 이용해 메인 도메인에 대한 하위 도메인을 AWS elastic beanstalk 환경에 연동함
  - Route 53 호스팅 영역 생성
  - 해당 호스팅 영역과 Elastic Beanstalk 환경 연결
  - GoDaddy에 Route 53 네임서버 레코드 설정

<br>



# 작업



## 1. Route 53 호스팅 영역 생성

![aws-route53-subdomain-1]({{site.url}}/assets/images/aws-route53-subdomain-1.png){: .align-center}

사용할 서브 도메인에 대한 호스팅 영역을 생성해 준다.

<br>

![aws-route53-subdomain-2]({{site.url}}/assets/images/aws-route53-subdomain-2.png){: align-center}

이제 설정한 해당 도메인에 대한 네임 서버는 AWS Route 53 서비스에서 관리하게 되는 것을 확인할 수 있다.

<br>

## 2. Elastic Beanstalk 환경 연결

![aws-route53-subdomain-3]({{site.url}}/assets/images/aws-route53-subdomain-3.png){: .align-center}

호스팅 영역에 DNS 레코드를 생성하기 위해, `Create Record` 버튼을 클릭해 레코드 생성 탭으로 들어 간다.

<br>

![aws-route53-dns-record-1]({{site.url}}/assets/images/aws-route53-dns-record-1.png){: .align-center}

도메인을 IPv4 주소로 매핑하기 위한 A 타입 DNS 레코드를 생성한다. AWS에서 이미 Elastic Beanstalk 환경에 연동할 수 있는 기능을 제공하기 때문에, 이미 생성된 환경만 찾아서 연결해 주면 된다.



<br>



## 3. GoDaddy 네임 서버 등록



서브 도메인에 대한 네임 서버를 AWS Route 53에 등록해 주었기 때문에, 해당 서브 도메인에 대한 DNS 쿼리를 AWS Route 53 쪽으로 위임해 주어야 한다. 메인 도메인에 대한 네임 서버를 GoDaddy 측에서 관리하기 때문에, GoDaddy 쪽에 관련 설정을 진행한다.



<br>

![godaddy-import-nameserver-1]({{site.url}}/assets/images/godaddy-import-nameserver-1.png){: .align-center}

![godaddy-import-nameserver-2]({{site.url}}/assets/images/godaddy-import-nameserver-2.png){: .align-center}

`1. Route 53 호스팅 영역 생성` 결과로 확인한 네임서버 DNS 서버 도메인을 GoDaddy 쪽에 네임서버 레코드 생성을 통해 임포트한다.



<br>

# 결과

설정한 하위 도메인으로 요청을 보내 보면, 응답이 잘 돌아 오는 것을 확인할 수 있다.

```bash
~$ curl -X GET http://adminapi.<<main-domain>>
{"message":"Hello, World!"}
```

<br>

![elasticbeanstalk-domain-result]({{site.url}}/assets/images/elasticbeanstalk-domain-result.png){: .align-center}

해당 하위 도메인이 호출되었을 때 일어나는 일은 다음과 같다.

- 하위 도메인 호출 시, 여러 과정을 거쳐서 GoDaddy 네임서버까지 도달
  - DNS 루트 서버부터 시작해, GoDaddy 네임서버까지 오게 됨
- GoDaddy 네임서버 쪽에서 하위 도메인에 대한 Route 53 네임서버 정보 전달
  - GoDaddy는 하위 도메인에 대한 권한이 없지만, DNS 레코드를 가지고 있음

