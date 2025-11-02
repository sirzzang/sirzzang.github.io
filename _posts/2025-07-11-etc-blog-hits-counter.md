---
title:  "블로그 hits counter 변경"
toc: false
categories:
  - Etc
tags:
  - github.io
  - hits
---

<br>

얼마 전부터 블로그 hits count 이미지가 계속 404 Not Found로 떴다.

![hit-counter-not-working]({{site.url}}/assets/images/hit-counter-not-working.png){: width="500"}{: .align-center}

<br>

알고 보니, 기존에 hit counter를 표시하기 위해 사용했던 hits 서비스가 종료되었다고 한다. [여기](https://deku.posstree.com/en/share/hit-counts/)에서 발견했다. 그래서 hits count를 표현하기 위해 사용하는 서비스를 [MyHits](https://myhits.vercel.app/)로 변경하려고 한다.

<br>

내가 현재 github.io 블로그에서 사용하는 jekyll 테마인 Minimal Mistakes는 페이지 레이아웃을 `_layouts/single.html`에 정의한다. 나는 해당 레이아웃에서 hit count를 표현할 수 있도록 아래와 같은 부분을 커스텀해 추가했다.

- [hits url 추가 부분](https://github.com/sirzzang/sirzzang.github.io/blob/97a83f7c715f3d357fcb898c9614c3275947b05a/_layouts/single.html#L78)



<br>

MyHits 서비스를 사용해 표현할 수 있도록, MyHits에서 사용하는 URL 형식에 맞게 바꿔 주면 된다.

- [변경 내용 커밋](https://github.com/sirzzang/sirzzang.github.io/commit/d7f08a588f60e9bf61ab7192d7e5fd6b503a15ff)

<br>

[이 포스트](https://sirzzang.github.io/dev/Dev-AWS-HTTPS-With-Elasticbeanstalk/)에 대한 hit count를 표현하는 HTML element가 아래와 같이 생성된다.

```html
<img src="https://myhits.vercel.app/api/hit/https%3A%2F%2Fsirzzang.github.io%2Fdev%2FDev-AWS-HTTPS-With-Elasticbeanstalk?color=green&amp;label=hits&amp;size=small" alt="hit count">
```

![hits-counter-change]({{site.url}}/assets/images/hits-counter-change.png){: width="500"}{: .align-center}
