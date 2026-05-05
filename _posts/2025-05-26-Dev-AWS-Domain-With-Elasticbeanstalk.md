---
title:  "[AWS] AWS Elastic Beanstalk 환경 도메인 연결"
excerpt: AWS Elastic Beanstalk 환경에 도메인을 연동해 보자.
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - DNS
  - Route 53
  - AWS
  - Elastic Beanstalk
  - GoDaddy
---

<br>

사이드 프로젝트에서 AWS에 배포한 API 서버에 도메인을 연결한 과정을 정리한다.

<br>

# TL;DR

- GoDaddy에서 구매한 메인 도메인의 서브 도메인을, AWS Route 53을 이용해 Elastic Beanstalk 환경에 연결했다
- Route 53에 호스팅 영역을 생성하고, Alias A 레코드로 EB 환경을 연결한 뒤, GoDaddy에 NS 레코드를 등록하여 DNS 위임을 설정했다

<br>

# 개요

- API 서버: AWS Elastic Beanstalk을 이용해 배포되어 있음
- 메인 도메인: [GoDaddy](https://kr.godaddy.com/) 서비스에서 구매함
- 작업 내용: [AWS Route 53](https://aws.amazon.com/ko/route53/) 서비스를 이용해 메인 도메인에 대한 하위 도메인을 AWS Elastic Beanstalk 환경에 연동함
  - Route 53 호스팅 영역(Hosted Zone) 생성
  - 해당 호스팅 영역과 Elastic Beanstalk 환경 연결
  - GoDaddy에 Route 53 네임서버 레코드 설정

<br>

# DNS 기본 개념

작업에 앞서, 알아 두면 좋은 DNS 관련 개념을 간략히 정리한다.

- **호스팅 영역(Hosted Zone)**: 특정 도메인에 대한 DNS 레코드를 관리하는 컨테이너. Route 53에서 호스팅 영역을 생성하면, 해당 도메인에 대한 DNS 레코드를 관리할 수 있게 된다
- **A 레코드**: 도메인을 IPv4 주소로 매핑하는 DNS 레코드
- **NS 레코드(Name Server Record)**: 특정 도메인의 DNS 쿼리를 처리할 네임서버를 지정하는 레코드. 서브 도메인의 DNS 관리를 다른 네임서버(예: Route 53)에 위임할 때 사용한다
- **Alias 레코드**: Route 53에서 제공하는 레코드 유형으로, AWS 리소스(ELB, CloudFront, EB 환경 등)를 도메인에 연결할 때 사용한다. 일반 A 레코드와 달리 고정 IP 주소가 아닌 AWS 리소스의 DNS 이름을 가리키므로, 리소스의 IP가 변경되더라도 자동으로 반영된다

> *참고*: Alias 레코드를 사용하는 이유
>
> Elastic Beanstalk 환경은 Load Balancer를 통해 접근하는데, Load Balancer의 IP 주소는 고정되어 있지 않다. 일반 A 레코드로 IP를 직접 지정하면 IP가 변경될 때마다 수동으로 업데이트해야 하지만, Alias 레코드를 사용하면 Route 53이 자동으로 현재 IP를 반환한다.

<br>

# 작업



## 1. Route 53 호스팅 영역 생성

![aws-route53-subdomain-1]({{site.url}}/assets/images/aws-route53-subdomain-1.png){: .align-center}

사용할 서브 도메인에 대한 호스팅 영역을 생성해 준다.

<br>

![aws-route53-subdomain-2]({{site.url}}/assets/images/aws-route53-subdomain-2.png){: .align-center}

이제 설정한 해당 도메인에 대한 네임 서버는 AWS Route 53 서비스에서 관리하게 되는 것을 확인할 수 있다.

<br>

## 2. Elastic Beanstalk 환경 연결

![aws-route53-subdomain-3]({{site.url}}/assets/images/aws-route53-subdomain-3.png){: .align-center}

호스팅 영역에 DNS 레코드를 생성하기 위해, `Create Record` 버튼을 클릭해 레코드 생성 탭으로 들어 간다.

<br>

![aws-route53-dns-record-1]({{site.url}}/assets/images/aws-route53-dns-record-1.png){: .align-center}

A 타입 DNS 레코드를 생성한다. 이 때 "Alias" 옵션을 활성화하고, 트래픽 라우팅 대상으로 Elastic Beanstalk 환경을 선택한다. Route 53이 Elastic Beanstalk 환경의 Load Balancer를 자동으로 찾아 연결해 주기 때문에, 이미 생성된 환경만 찾아서 연결해 주면 된다.



<br>



## 3. GoDaddy 네임 서버 등록



서브 도메인에 대한 네임 서버를 AWS Route 53에 등록해 주었기 때문에, 해당 서브 도메인에 대한 DNS 쿼리를 AWS Route 53 쪽으로 위임해 주어야 한다. 메인 도메인에 대한 네임 서버를 GoDaddy 측에서 관리하기 때문에, GoDaddy 쪽에 관련 설정을 진행한다.



<br>

![godaddy-import-nameserver-1]({{site.url}}/assets/images/godaddy-import-nameserver-1.png){: .align-center}

![godaddy-import-nameserver-2]({{site.url}}/assets/images/godaddy-import-nameserver-2.png){: .align-center}

`1. Route 53 호스팅 영역 생성` 결과로 확인한 네임서버 DNS 서버 도메인을 GoDaddy 쪽에 네임서버 레코드 생성을 통해 임포트한다.



<br>

# 결과

설정한 하위 도메인으로 요청을 보내 보면, 응답이 잘 돌아 오는 것을 확인할 수 있다. 이후 이 도메인에 HTTPS를 적용하는 과정은 [Elastic Beanstalk 환경 HTTPS 설정]({% post_url 2025-05-27-Dev-AWS-HTTPS-With-Elasticbeanstalk %}) 포스트에서 다룬다.

```bash
~$ curl -X GET http://adminapi.<<main-domain>>
{"message":"Hello, World!"}
```

<br>

![elasticbeanstalk-domain-result]({{site.url}}/assets/images/elasticbeanstalk-domain-result.png){: .align-center}

해당 하위 도메인이 호출되었을 때 DNS 해석 흐름은 다음과 같다.

1. 클라이언트가 `adminapi.<<main-domain>>`에 대해 DNS 쿼리를 보낸다
2. DNS resolver가 루트 서버 → TLD 서버 → 메인 도메인의 네임서버(GoDaddy) 순으로 질의한다
3. GoDaddy 네임서버는 서브 도메인 `adminapi`에 대한 NS 레코드를 확인하고, Route 53 네임서버 정보를 반환한다 (DNS 위임)
4. DNS resolver가 Route 53 네임서버에 질의하면, Alias A 레코드에 따라 Elastic Beanstalk 환경(Load Balancer)의 IP 주소를 반환한다
5. 클라이언트가 해당 IP로 요청을 보내고, 응답을 받는다

<br>

# 참고 링크

- [AWS Route 53 공식 문서](https://docs.aws.amazon.com/ko_kr/Route53/latest/DeveloperGuide/Welcome.html)
- [Routing traffic to an Elastic Beanstalk environment](https://docs.aws.amazon.com/ko_kr/Route53/latest/DeveloperGuide/routing-to-beanstalk-environment.html)
- [Choosing between alias and non-alias records](https://docs.aws.amazon.com/ko_kr/Route53/latest/DeveloperGuide/resource-record-sets-choosing-alias-non-alias.html)

<br>
