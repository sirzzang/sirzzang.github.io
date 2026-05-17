---
title: "AI 스킬 작성 관찰기: 자연어 문서가 프로그래밍 단위가 되는 순간"
excerpt: "Claude Code가 SKILL.md 구현 계획에 RED-GREEN-REFACTOR를 꺼낸 순간을 분해하며 적어 본 기록."
categories:
  - Articles
toc: true
header:
  teaser: /assets/images/blog-Articles.png
tags:
  - AI
  - Claude-Code
  - Skill
  - TDD
  - Superpowers
  - Prompt-Engineering
  - Retrospective
hidden: true
---

<br>

# 들어가며

자주 반복되는 워크플로우를 플랫폼 설계 트랙용 스킬로 굳히려고 하던 참이었다. [obra/superpowers](https://github.com/obra/superpowers)의 `brainstorming` 스킬로 스킬 요구사항을 먼저 설계하고, 그 결과를 `writing-plans` 스킬에 넘겨 SKILL.md 작성 계획을 짜달라고 했다. 그러자 AI가 작업을 시작하면서 이렇게 말했다.

> ⏺ I'm using the writing-plans skill to create the implementation plan.
>
> 이 구현은 코드가 아니라 SKILL.md 작성이므로, pytest TDD 대신 superpowers:writing-skills의 RED→GREEN→REFACTOR 사이클(서브에이전트 압박 시나리오 + dry-run 회귀)에 맞춰 계획합니다.

![SKILL.md 작성 계획에 RED 단계가 등장한 화면]({{site.url}}/assets/images/skill-tdd-red.png){: .align-center}

순간 멈칫했다. 코드도 아닌 스킬에 TDD라니? 처음엔 위화감의 원인이 "TDD가 코드 아닌 곳에 들어왔다"는 데에 있는 줄 알았다. 분해해 보니 인과가 그 반대였다. **SKILL.md가 코드가 아닌 게 아니라, 어느새 코드와 같은 사물 — 프로그래밍 단위 — 이 되어 있어서 TDD가 따라 들어올 수 있었던 것**이었다. 이 글은 그 분해의 기록이다. AI와 작업하는 방식을 정리해 온 시리즈 — [프롬프트 패턴 개선기]({% post_url 2026-04-10-Articles-AI-Prompt-Pattern-Improvement %}), [AI와 나]({% post_url 2026-04-15-Articles-AI-and-Me %}) — 의 세 번째 글이기도 하다. 앞 두 편이 "프롬프트라는 글쓰기"와 "AI라는 동료"에 대한 기록이었다면, 이번엔 그 글쓰기가 한 칸 더 위로 올라가는 풍경에 대한 기록을 남기고자 한다.

<br>

# 프롬프트가 statement라면 SKILL은 함수다

추상화 사다리를 다시 그려 보자. 가장 아래에 기계어가 있고, 그 위에 어셈블리가 있다. 그 위로 고수준 언어들이 차곡차곡 쌓이는데, 같은 고수준 언어 안에서도 C에서 Python으로 가면 메모리·포인터처럼 기계에 가까운 개념이 가려지고, 사람이 평소 쓰는 사고에 더 가까워진다. 그리고 AI가 등장한 지금, 사다리는 한 칸 더 올라가 **자연어**까지 도달했다. 그래서 "프롬프트 작성이 곧 프로그래밍"이라는 명제는 [지난 글]({% post_url 2026-04-10-Articles-AI-Prompt-Pattern-Improvement %})에서 프롬프트 사용 패턴을 한 번 들여다본 적이 있을 만큼 익숙한 풍경이 되어 있다.

그런데 이번엔 한 칸이 더 있었다. SKILL은 단발 프롬프트가 아니다. **이름이 붙고, 트리거 키워드가 정의되고, 버전 관리되며, 다른 스킬을 invoke할 수 있는** 단위다. 함수처럼 호출되고, 모듈처럼 조립되며, 패키지처럼 배포된다. 한 줄로 압축하면 프롬프트가 statement라면 SKILL은 함수다 — 더 정확히는 함수에서 모듈·패키지로 이어지는 한 묶음이다.

돌아보면 나도 어느새 비슷한 일을 하고 있었다. `support-intake` — 외부에서 들어오는 단발성 이슈를 정리해 후속 워크플로우로 진입시키는 인테이크 스킬, `work-exit` — 한 트랙을 마무리하면서 산출물을 정리해 다른 트랙으로 넘기는 종결 스킬, 이번에 만든 `platform-design-capture` — 설계 요구사항 캡처 스킬. 업무 효율성 향상을 위해 설계한 모든 스킬 각각이 이름과 트리거, 명세, 분기, 에지 케이스를 가지며 외부 파일과 다른 스킬을 의존성으로 명시한다. 인테이크 스킬 하나만 봐도, 입력 필드를 파싱하고(§폼 필드), 외부 인덱스 파일을 매번 동적으로 읽도록 의존성에 명시하고(§의존성), 입력 상태가 일정 조건을 넘으면 더 무거운 트랙으로 분기할지 결정하고, 본문 초안·노트 파일·인덱스 행이라는 세 가지 산출물을 반환한다 — 함수의 시그니처·본문·반환값에 정확히 대응하는 구조다. 의사결정 플로우는 다른 스킬의 패턴을 참조한다고 §의존성에 따로 명시해 두기까지 했다. 어느 순간부터 이걸 "문서를 쓴다"기보다 "프로그램을 짠다"는 감각으로 작업하고 있다는 걸 뒤늦게 알아챘다. 그 감각이 정면에 처음 나타난 게 위의 메시지였다. "코드가 아니라 SKILL.md 작성이므로" — 이 표현 안에서 이미 SKILL.md 작성은 코드 작성과 동격의 작업 단위로 다뤄지고 있다.

이 감각이 일회성 비유로 끝나지 않는다는 건, Superpowers 같은 플러그인 생태계가 이미 SKILL을 first-class object로 다루는 패턴을 굳혀 둔 것을 보고 확인됐다. SKILL을 작성하는 작업 자체에 별도의 스킬(`writing-skills`)이 존재하고, 그 스킬을 테스트하는 또 다른 스킬(`testing-skills-with-subagents`)이 따로 있다. 발단이 된 RED-GREEN-REFACTOR 메시지도 그 패턴화된 스킬 — `writing-plans` — 이 가져온 것이었다. AI가 그때그때 즉흥적으로 TDD를 변형한 게 아니라, 미리 코드화된 메타-스킬을 invoke한 결과였다는 뜻이다. SKILL이 단위로 자리 잡았다는 가장 분명한 증거가 여기 있다 — 단위가 일단 정해지면, 그 단위를 다루는 도구가 자라기 시작한다.

<br>

# TDD의 의미가 재정의된다

SKILL이 함수라면, 함수에 우리가 늘 하던 일 — 테스트 — 이 따라 들어오는 건 자연스럽다. 그래서 진짜 흥미로운 건 "코드가 아닌 데 TDD가 있다"가 아니라 **TDD라는 단어가 들어올 때 그 안의 명사들이 전부 새로 매핑되어 들어온다는 것**이었다.

`writing-plans`가 짜준 계획은 5개 태스크였다 — RED-GREEN-REFACTOR 세 축에 설치·인덱스 갱신 같은 마무리 태스크가 양옆에 붙은 구성이다. Task 1은 RED — **스킬 없이** 서브에이전트에게 회귀 케이스를 던져 baseline 실수를 관찰·기록한다. Task 2는 GREEN — 그 baseline 실수 목록을 막을 만큼만 SKILL.md를 작성한다. 그리고 Task 4는 REFACTOR — 5개 회귀 케이스를 dry-run으로 돌려 어긋나면 SKILL.md의 loophole을 닫는다.

![Task 2 GREEN 단계의 SKILL.md 작성 계획]({{site.url}}/assets/images/skill-tdd-green.png){: .align-center}

표 한 장으로 단어 매핑을 정리하면 이렇게 된다. 표 안의 두 용어를 먼저 풀어 두면 — *verbatim*(글자 그대로)은 에이전트가 자기 합리화에 쓴 표현을 한 글자도 다듬지 않고 받아 적는다는 뜻이고, *negation*(부정 명령)은 그렇게 받아 적은 표현을 SKILL.md에 "이렇게 말하지 마라" 형태로 명시해 등록한다는 뜻이다.

| TDD 단계 | 코드 TDD | 스킬 TDD |
| --- | --- | --- |
| RED | 실패하는 테스트 작성 | 스킬 없이 서브에이전트 실패 관찰 + 합리화 verbatim 기록 |
| GREEN | 최소 코드로 테스트 통과 | 관찰된 실수를 막을 만큼만 SKILL.md 작성, 압박 하 준수 확인 |
| REFACTOR | 외부 동작 보존하며 내부 구조 개선 | 새 loophole 발견 시 명시적 negation 추가 (방어선 보강) |

매핑 자체는 표가 보여주지만, 이 표가 단순한 1:1 대응이 아니라 단어의 의미가 갈아 끼워지는 사건임을 한 번 짚어 둘 필요가 있다.

"테스트"의 통과 기준이 `f(x) == y`에서 **"에이전트가 규칙을 깨고 싶어지는 상황에서 어떻게 행동하는가"**로 옮겨 간다. 그래서 RED 단계에 굳이 fresh context의 다른 에이전트가 들어오고, 거기에 압박이 추가로 걸린다. 본인 컨텍스트에서 "이 스킬 잘 동작해?"라고 물으면, LLM은 자기가 막 만든 결과물을 잘 통과시키는 self-confirmation bias가 있다. 그걸 우회하려면 외부 화자가 필요하다. 그리고 그 외부 화자가 평이한 조건에서 통과시켜 버리면 의미가 없으므로, 시간 압박·sunk cost·사회적 압력 같은 현실적 압박을 걸어 "규칙을 깨고 싶어지는 상황"을 인공적으로 만들어 둔다.

입력은 값이 아니라 그 시나리오 자체고, 출력은 행동이며, 그 행동에서 합리화 문구를 verbatim으로 받아 적는다. 이 verbatim 목록이 곧 SKILL.md가 충족해야 할 명세가 된다 — 전통 TDD의 "테스트 = 명세" 명제가 여기서도 그대로 살아남는 셈이다. assertion이 행동 관찰로 바뀌면 테스트라는 단어가 가리키던 사물 자체가 달라지지만, 단어 위에 얹혀 있던 명제 한 줄만은 살아남는다.

"GREEN"의 의미는 한 번 통과로 끝나지 않는 데서 갈라진다. 결정적이지 않은 출력 위에서 결정적 행동을 끌어내야 하므로, 통과 기준이 단일 입출력 검증보다 fuzz testing이나 LLM evaluation의 robustness 평가 쪽에 가까워진다. 압박을 3개 이상 조합해 시나리오를 변형하면서, 같은 합리화 문구가 더는 나오지 않을 때까지 반복한다.

"REFACTOR"는 내부 구조를 다듬는 일이 아니라, 새로 관찰된 합리화 문구를 catalogue처럼 모아 SKILL.md에 박아 두는 **방어선 누적** 작업이 된다. 외부 동작을 바꾸지 않는다는 원칙이 무너지고, 오히려 외부에서 들어오는 합리화 압력에 맞춰 명시적 금지 조항이 늘어 가는 쪽으로 방향이 뒤집힌다. 이번 작업에서도 5개 회귀 케이스를 dry-run으로 돌리면서 어긋나는 분기마다 `## 에러 / 엣지 케이스` 절을 늘려 가는 식으로 진행됐다.

![REFACTOR 단계의 회귀 케이스 1]({{site.url}}/assets/images/skill-tdd-refactor-1.png){: .align-center}

같은 단어가 들어 있는데, 들여다 보면 안의 명사들이 전부 다른 사물을 가리킨다. SKILL이 함수라는 건 알았는데, 그 함수의 테스트 단어조차 새로 정의되어 들어왔다.

<br>

# "skip TDD just this once" — 합리화 트립와이어

여기까지 분해하다가 실제 [test-driven-development SKILL.md](https://github.com/obra/superpowers/blob/main/skills/test-driven-development/SKILL.md)를 들여다 보고 한 번 멈춰선 자리가 있다.

> Thinking "skip TDD just this once"? Stop. That's rationalization.

처음엔 단순한 규칙처럼 읽혔다. "TDD 건너뛰지 마라"의 강한 표현쯤. 그런데 이 문장은 그렇게 단순하지 않다.

이 문장은 **LLM이 자기 자신에게 말을 걸 때 실제로 쓰는 문구를 verbatim으로 캡처해서 트립와이어로 박은 것**이다. RED 단계의 압박 시나리오에서 서브에이전트가 합리화하는 모습을 관찰하고, 그 합리화 문구를 글자 그대로 받아 적은 다음, "이 문구가 떠오르는 순간 = 위반 시점"으로 등록해 둔 것. 사람으로 치면 자기 합리화 패턴을 입 밖에 내기 전에 끊어 주는 인지행동치료의 트립와이어와 닮았다.

[지난 글]({% post_url 2026-04-15-Articles-AI-and-Me %})에서 디버깅하는 AI에게 동질감을 느낀 적이 있다. "잠깐 —" 하고 가설을 의심하는 모습, "이제 전체 구조가 보입니다"라고 자신 있게 말한 직후에 또 틀리는 모습 같은 것들이었다. 합리화 트립와이어는 그 동질감의 다른 면이다. **AI도 인간처럼 합리화하는데, 그걸 막는 방식은 인간의 어떤 행위와도 잘 매칭되지 않는다.** 사람의 합리화는 사후에야 본인이 알아차리지만, AI의 합리화는 fresh context의 다른 AI에게 압박을 걸어 외부에서 관찰할 수 있다. 그 외부 관찰의 산물이 이 한 줄 트립와이어다.

![REFACTOR 단계의 회귀 케이스 2~3]({{site.url}}/assets/images/skill-tdd-refactor-2.png){: .align-center}

요약하자면, **AI에게 규칙을 가르치려면 AI가 규칙을 깨고 싶어할 때 어떤 말로 자기를 설득하는지부터 들어야 한다.** 이 한 줄은 SKILL.md의 표현 방식만 바꾸는 게 아니라, "AI에게 무언가를 가르친다"는 행위 전체를 다른 카테고리로 옮긴다.

<br>

# 도구체인의 자연어 복제

세 번째 분해까지 마치고 한 걸음 물러서면, 풍경이 한 단계 더 멀리서 보이기 시작한다.

SKILL이 프로그래밍 단위로 자리 잡았다면, 단위 하나를 신뢰 가능하게 만들기 위한 주변 도구들도 따라 생겨야 한다 — 컴파일러·테스트 러너·린터·CI·패키지 매니저처럼. SKILL은 **runtime이 LLM인 프로그램**이고, SKILL.md는 그 프로그램의 소스, LLM은 컴파일러이자 인터프리터다. 그러면 그 프로그램을 신뢰 가능하게 만들기 위한 나머지 도구들이 있어야 하는데 — 이미 있다.

- 컴파일러 ≈ LLM
- 테스트 러너 ≈ fresh-context 서브에이전트
- 테스트 케이스 ≈ 압박 시나리오
- 회귀 슈트 ≈ 합리화 verbatim 카탈로그
- 린터 ≈ Red Flags / Common Rationalizations 섹션
- CI ≈ dry-run 회귀 케이스
- 패키지 매니저 ≈ Superpowers 같은 플러그인 생태계

그리고 코드 리뷰까지 — superpowers의 `subagent-driven-development`는 리뷰를 spec 준수 검토와 코드 품질 검토의 두 단계로 분리해 두었다. 다른 항목들이 "X 같은 도구 ≈ Y 같은 자연어 도구"인 데 비해 이건 "리뷰 워크플로우 자체가 자연어 스킬로 캡슐화"라는 결이라 한 줄 풀어 둔다.

소프트웨어 엔지니어링 도구체인의 한 층이 통째로 자연어 레이어로 복제되고 있다는 신호다. 비유가 아니라, 실제로 같은 역할을 하는 별개의 사물이 만들어지고 있다.

그리고 한 단계 더 자기참조적이다. 위 도구체인은 외부에서 SKILL을 다루는 별개의 사물이 아니라, **그 자체가 다시 SKILL**이다. 스킬을 작성하는 스킬(`writing-skills`), 스킬을 테스트하는 스킬(`testing-skills-with-subagents`), 스킬 실행 계획을 짜는 스킬(`writing-plans`) — SKILL이 first-class object라는 가장 강한 증거는, 그것을 다루는 도구가 다시 같은 종류의 사물로 만들어지고 있다는 점이다. 컴파일러가 자기 자신을 컴파일하는 self-hosting과 닮은 자리가 자연어 레이어에서 만들어지고 있다. §2에서 짚어 둔 "단위가 일단 정해지면 그 단위를 다루는 도구가 자라기 시작한다"는 명제가, 여기서는 도구가 단위와 같은 종류로 자라난다는 한 칸 더 강한 형태로 나타난다.

이 풍경에서 "AI 시대의 프로그래밍"의 실체가 조금 다르게 보인다. 그건 자연어로 코드를 쓰는 일이 아니라, **자연어로 쓰인 프로그램을 관리하는 엔지니어링 디시플린이 새로 생기는 일**이다. 컴파일러가 등장한 시대에 린터·CI·패키지 매니저까지 따라 만들어졌듯, 자연어 컴파일러(LLM) 등장 다음 단계로 그 주변 도구들이 자연어 레이어에 다시 깔리고 있다.

지난 [생산성과 깊이 사이의 갈등]({% post_url 2026-04-11-Articles-AI-Productivity-vs-Knowledge-Depth %})을 정리하며 만들었던 워크플로우 스킬들 — `notion-upload`, `weekly-review`, `prompt-deep-dive`, `workflow-suggest` 같은 것들 — 도 결국 이 풍경의 한 점이었다. 그때는 "내 워크플로우의 도구화"라고 자기 안에서 표현했지만, 멀리서 보면 **자연어로 쓰인 작은 프로그램들의 패키지를 만들고 있던 것**이고, 지금 `platform-design-capture`를 TDD 사이클로 작성하는 건 그 패키지 안 모듈의 품질 보증을 시작한 단계인 셈이다.

<br>

# 마무리

처음엔 단순히 "TDD가 SKILL에 적용되는 게 신기하다" 정도였다. 분해해 보니 그 놀라움의 정체는 — **TDD가 들어왔다는 사실이 아니라, 그 안의 SKILL이 어느새 프로그래밍 단위가 되어 있어서 TDD가 들어올 수 있었다는 인과** 쪽이었다. 내가 작성하는 자연어 문서 한 편이 software artifact로 자라나는 과정을, 그 자라남의 한가운데에서 실시간으로 보고 있었던 것이다.

SKILL.md를 짠다고 자판을 두드리는 동안, 위의 한 줄 트립와이어 문장처럼 어느 자리는 verbatim으로 보존되고, 어느 자리는 산문 호흡 그대로 흘러간다. 한 문서 안에 그 두 가지 텍스처가 공존하기 시작한다는 사실이 처음으로 의식된다. 자연어가 코드와 산문 사이의 어딘가에서 새 거주지를 마련하고 있다.

<br>

# 참고

- [obra/superpowers](https://github.com/obra/superpowers) — `test-driven-development`, `writing-skills`, `testing-skills-with-subagents`, `subagent-driven-development` SKILL.md 원문
- Jesse Vincent, [Superpowers: How I'm using coding agents in October 2025](https://blog.fsck.com/2025/10/09/superpowers/) — 본문에서 인용한 RED-GREEN-REFACTOR 도입 일화의 출처

<br>
