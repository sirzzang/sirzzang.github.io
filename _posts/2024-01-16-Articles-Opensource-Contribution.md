---
title:  "나의 작고 소중한 오픈 소스 기여 후기"
excerpt: "How to contribute to open source"
toc: true
categories:
  - Articles
tags:
  - 후기
  - 오픈 소스
use_math: true
---

야심차게 맞았던 2023년의 목표 중 하나였던 **오픈 소스 기여해 보기**. 비록 2023년이 가기 전에 성취하지는 못했지만, 2024년 벽두에나마 달성했다. 개발자로서 언젠가는 꼭 한 번 해 보고 싶다고 생각했던 일이었기에, 그 기록을 남기고 싶어 글을 쓰게 되었다.

<br>

# 개요

오픈 소스에 기여하기 위한 절차는 크게 어렵지 않다.

1. 오픈 소스 코드에서 불편함이나 문제점을 찾는다.
2. 오픈 소스 코드를 수정한다. 대부분 아래와 같이 작업하면 된다.
   - 원격 오픈 소스 코드 리포지토리를 Fork한다.
   - Fork한 원격 리포지토리를 로컬 작업 환경에 Clone한다.
   - 원격 오픈 소스 코드 리포지토리를 Upstream으로 설정한다.
   - 로컬 소스 코드 리포지토리에서 작업한 후, Commit한다.
   - Commit 내역을 Remote 소스 코드 리포지토리로 Push한다.
3. Remote 소스 코드 리포지토리에서 Upstream 소스 코드 리포지토리로 PR을 작성한다.

이 과정에서, 대부분의 오픈 소스는 Contribution Guide를 제공한다. 코드 작성 방법에서부터 테스트 통과 및 빌드 확인에 이르기까지, 가이드 범위는 다양하다. 작업의 큰 골자는 위에서 작성한 것과 같으나, 작업 내용이 해당 오픈 소스에서 명시하고 있는 가이드를 따랐는지 꼭 확인해야 한다.

- [go-ldap Contribution Guide](https://github.com/go-ldap/ldap?tab=readme-ov-file#contributing)
- [grule-rule-engine Contribution Guide](https://github.com/hyperjumptech/grule-rule-engine/blob/master/CONTRIBUTING.md)

<br>

# 실패기였으나 성공기

첫 번째 기여 시도는 [grule-rule-engine](https://github.com/hyperjumptech/grule-rule-engine)에 대한 것이었다. 회사 팀원 분이 go의 오픈 소스 rule engine인 `grule-rule-engine`을 이용해 개발을 하고 계신데, 코드를 리뷰하던 중 우연히 `grule-rule-engine` 소스 코드의 주석에서 [오타를 발견했다](https://github.com/hyperjumptech/grule-rule-engine/blob/master/pkg/JsonResource.go#L35).

![grule-typo]({{site.url}}/assets/images/grule-typo.png){: .align-center}

<center><sup>format이 fromat으로 작성되어 있다.</sup></center>

단순한 오타일 뿐이었기에, 이러한 내용으로도 PR을 작성할 수 있는지 궁금해 관련 PR이 있는지 검색해 봤다.

![grule-typo-issues]({{site.url}}/assets/images/grule-typo-issues.png)

오타와 관련된 PR 중 merge된 것이 여럿 보였고, 오픈 소스에 기여하는 것은 오타를 수정하는 것부터라는 말도 들었던 터라, 오타를 수정해 PR을 작성했다. 

![grule-typo-pull-request]({{site.url}}/assets/images/grule-typo-pull-request.png)



~~결과적으로는 merge되지 않았다. 아직까지도 열려 있는 상태다.관련 이슈를 작성하지 않았고, PR 본문도 성의 없이 작성한 탓이 어느 정도 있지 않을까 생각한다.~~

![grule-pr-merged]({{site.url}}/assets/images/grule-pr-merged.png){: .align-center}

오랜만에 다시 확인해 보니, 이 때 작성했던 PR이 merge되었다. 업무 과정에서 사용했던 오픈 소스에 아주 작지만 기여를 할 수 있었던 첫 번째 경험이라 생각하니, 기분이 좋다.



<br>

# 성공기

두 번째 기여 시도는 [go-ldap](https://github.com/go-ldap/ldap)에 대한 것이었다. 회사에서 담당하고 있는 Account Service를 개발하면서 go의 오픈 소스 LDAP client인 `go-ldap`을 이용했는데, 이 과정에서 상수 선언을 추가해 주면 사용자들이 더 쓰기 편할 것 같다는 생각이 들어서였다.

 LDAP 서버에서 Search 요청을 통해 엔트리를 검색해 올 때, 검색 범위로 Scope를 명시해 사용할 수 있다(참고: [RFC 4511](https://github.com/go-ldap/ldap)). 엔트리를 어느 레벨에서 찾을지 그 범위를 지정하기 위한 속성이다. 

 RFC에 명시되어 있지는 않으나, OpenLDAP 서버에서는 Search 요청에 사용할 수 있는 Scope 옵션으로 `children`을 지원한다. OpenLDAP 서버에 대한 검색을 지원하는 `ldapsearch` 커맨드 역시 Scope 옵션을 지정하기 위한 `-s` 플래그의 값 중 하나로 `children`을 지원하고 있다. 하필 나는 OpenLDAP 서버를 이용해 개발을 하고 있었고, 당시 개발해야 하는 기능은 Scope 값으로 `children`을 지정해 Search 요청을 보내면 간단히 개발할 수 있는 기능이었다.

 go-ldap에서는 LDAP 서버에 Search 요청을 보낼 때, 아래와 같은 `SearchRequest` 타입을 사용한다([go-ldap SearchRequest](https://pkg.go.dev/github.com/go-ldap/ldap/v3#SearchRequest))

```go
type SearchRequest struct {
	BaseDN       string
	Scope        int
	DerefAliases int
	SizeLimit    int
	TimeLimit    int
	TypesOnly    bool
	Filter       string
	Attributes   []string
	Controls     []Control
}
```

여기에 Scope 값을 지정할 수 있는데, 여기에 사용할 수 있는 `int` 타입의 Scope 값으로 아래와 같은 상수가 정의되어 있다([go-ldap constants](https://pkg.go.dev/github.com/go-ldap/ldap/v3#pkg-constants)).

```go
const (
	ScopeBaseObject   = 0
	ScopeSingleLevel  = 1
	ScopeWholeSubtree = 2
)
```

Children에 대한 Scope가 정의되어 있다면 그 값을 사용해서 Search 요청을 보내는 코드를 작성하면 될 텐데, 해당 값이 정의되어 있지 않았다. 어떻게 해야 하나 고민을 하다가, 혹시 0, 1, 2 외의 다른 값을 넣었을 때 코드가 어떻게 동작할지 시도라도 해보기로 했다. 그런데 웬걸, `3`을 넣으니 내가 원하는 방향대로 동작하는 것이 아닌가. 혹시 몰라 `4`, `-1`, `999` 등 다른 값을 넣어 봤는데, 에러가 발생한다.

![ldap-scope-value-3.png]({{site.url}}/assets/images/ldap-scope-value-3.png){: .align-center}

![ldap-scope-value-4.png]({{site.url}}/assets/images/ldap-scope-value-4.png){: .align-center}

<center><sup>4로 설정한 코드를 실행할 경우, LDAP Result Code 2 "Protocol Error": invalid scope라는 메시지와 함께 에러가 발생한다.</sup></center>

동작이 안 되는 것은 아니기에 `3` 값을 사용하면 된다. 그러나 코드 상에 static하게 3이라는 숫자가 쓰이는 게 싫었고, `children`에 대한 Scope level을 명시해 주는 상수가 있다면 OpenLDAP 서버를 사용하는 go-ldap 사용자들이 더 편할 수 있지 않을까 하는 생각이 들었다. 그래서 아래와 같이 이슈를 작성하고, PR을 올렸다.

- [Issue 작성 내용](https://github.com/go-ldap/ldap/issues/481)
- [PR 작성 내용](https://github.com/go-ldap/ldap/pull/480)

첫 번째 실패 경험을 교훈 삼아, 이슈를 자세히 작성했고, 작성한 이슈 페이지에 PR을 링크했다. 직접 개발하는 코드에 쓰이게 될 것이니만큼, merge되었으면 좋겠다고 생각하고 있던 차였는데...

![ldap-pull-request-merged]({{site.url}}/assets/images/ldap-pull-request-merged.png){: .align-center}

이게 무슨 일인지! PR이 merge가 되었다. 그것도 너무나도 친절한 답변과 더 자세한 추가 Commit과 함께! merge되었으면 좋겠다고 생각하고 있었는데 진짜 되었다. 그리고 `Contributor` 딱지를 받아 버린 것이었다!

![ldap-contributor]({{site.url}}/assets/images/ldap-contributor.png){: .align-center}





<br>



# 느낀 점



 두 번의 Contribution 시도가 모두 다 거창하다거나 어려운 내용은 아니라 살짝 민망하기도 하지만, 그래도 PR이 merge되는 것을 보니 너무 행복했다. 내가 오픈 소스에 기여를 할 수 있을까 항상 생각만 했는데, 실제로 기여를 하고 나니 개발자 세계에 조금의 기여라도 했다는 생각이 들어 뿌듯하기도 하다. 오픈 소스 Contributor가 되기 위해 이것 저것 시도해 보며 깨달은 것은 다음과 같다.

- 큰 것이 아니어도 된다. 오타, 문서의 어색한 표현 수정 등도 모두 오픈 소스 생태계에 기여할 수 있는 것이다.
- 기여를 하기 위해서는 내가 사용하는 것에서부터 시작하는 것이 좋다. 오픈 소스에 Contribution을 하고 싶다고 해서, 생판 모르는 오픈 소스를 처음부터 분석해 가며 할 수는 없는 일이다. ~~어리석게도 2023년 초의 나는 그러했다.~~ 평소에 개발할 때 기능을 구현하기 앞서 사용할 수 있는 오픈 소스가 있는지 확인해 보고, 찾아 낸 오픈 소스를 직접 사용해 보는 습관을 들여야 한다. 그래야 내가 기여할 수 있는 포인트를 쉽게 찾을 수 있다.
- 오픈 소스 사용 및 그 생태계에의 기여를 적극 장려하는 팀 분위기도 중요하다. 평소 팀 내에서 오픈 소스 사용 및 기여에 대한 이야기를 많이 들었기에 오픈 소스에 기여해 보고 싶다는 생각이 더 강해졌다. 또한 코드 리뷰, PR도 모두 영어로 진행하고 있었기에, 이슈와 PR을 작성하는 것이 크게 어렵지 않았다. 팀 내에서 체득한 개발 문화가 도움이 된다.



멀게만 느껴지던 오픈 소스 Contribution에 한 걸음 다가갈 수 있어 큰 성취감을 느낄 수 있었다. 이 경험을 발판으로 삼아, 앞으로도 오픈 소스 사용을 게을리하지 않고, 더 어려운 구현도 척척 해내서 Contribution할 수 있는 개발자가 되어 보아야겠다. 끗! 

