---
title: "[LLM] LLM 서빙과 최적화 - 2.2. Transformer: Transformer Explainer"
excerpt: "Transformer Explainer를 이용해 브라우저에서 GPT-2를 이용해 트랜스포머 내부를 들여다 보자."
categories:
  - AI
toc: true
header:
  teaser: /assets/images/blog-AI.jpg
tags:
  - Transformer
  - Transformer-Explainer
  - GPT-2
  - Visualization
  - Tokenization
  - BPE
  - Hands-On-LLM-Serving-and-Optimization-Study
  - Hands-On-LLM-Serving-and-Optimization-Study-Week-1
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Hands-On LLM Serving and Optimization Study (LLMSO) 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- [Transformer Explainer](https://poloclub.github.io/transformer-explainer/)는 GPT-2(small)를 브라우저에서 직접 돌리며 트랜스포머 내부를 시각화하는 인터랙티브 도구다. 작은 모델이지만 기본 구조를 배우기에는 충분하다
- 트랜스포머는 마법이 아니다. "이 입력 다음에 올 가장 그럴듯한 토큰은 무엇인가"를 반복해서 묻는 기계다. My hobby를 넣으면 is가 나온다
- GPT-2의 어휘 사전은 영어 중심이라 한글을 넣으면 바이트 단위로 잘게 쪼개져 망가진다. 토크나이저가 왜 중요한지를 개요 수준에서 미리 확인할 수 있다
- 전체 아키텍처는 Embedding → Transformer Block(Self-Attention + MLP(Multi-Layer Perceptron)) ×12 → Probabilities 세 부분이다. 이후 글에서 이 세 부분을 하나씩 줌인한다

<br>

# Transformer Explainer

[앞 글]({% post_url 2026-08-05-AI-LLM-Optimization-02-01-LLM-Transformer-Overview %})에서 트랜스포머의 큰 그림과 용어를 지도로 잡았다. 이제 그 지도를 들고 실제 지형을 밟아 볼 차례다. [Transformer Explainer](https://poloclub.github.io/transformer-explainer/)는 Georgia Tech의 Polo Club of Data Science가 만든 인터랙티브 시각화 도구로, **GPT-2(small) 모델을 브라우저 안에서 실제로 실행하면서** 텍스트가 임베딩되고, attention을 통과하고, 다음 토큰 확률로 바뀌는 전 과정을 눌러 볼 수 있게 해 준다.

![Transformer Explainer 첫 화면: 입력 문장이 임베딩, Multi-Head Self-Attention, MLP를 거쳐 다음 토큰 확률로 이어지는 전체 흐름 시각화]({{site.url}}/assets/images/llmso-transformer-explainer-introduction.png){: .align-center width="700"}

<center><sup>Transformer Explainer 화면 직접 캡처</sup></center>

사이트의 소개 문구가 이 도구의 포지션을 잘 요약한다. 트랜스포머는 ChatGPT, Gemini 같은 모델을 움직이는 현대 AI의 핵심 아키텍처이고, 학습과 추론에 같은 아키텍처가 쓰이며, 여기서는 최신 모델보다 단순하지만 기본기를 배우기에 완벽한 GPT-2(small)를 사용한다는 것이다.

## GPT-2 small로 충분한 이유

GPT-2 small의 제원은 다음과 같다.

- 파라미터 약 1억 2,400만 개
- 트랜스포머 블록 12개, attention 헤드 12개
- 모델 차원 768 (헤드당 차원 64)
- 어휘 사전 50,257개, 컨텍스트 길이 1,024 토큰

요즘 기준으로는 아주 작은 모델이다. 하지만 앞 글에서 본 대로 최신 생성형 LLM들도 디코더 전용 트랜스포머라는 골격을 공유하고, 달라지는 것은 주로 블록 수·차원·어휘 크기 같은 규모와 세부 변형이다. 골격을 배우는 데는 작은 모델이 오히려 낫다. 브라우저에서 즉시 돌고, 모든 중간 계산을 눈으로 따라갈 수 있기 때문이다.

<br>

# 다음 토큰 예측 데모

트랜스포머의 동작 원리는 한 문장으로 요약된다. 마법이 아니라, **"이 입력 다음에 올 가장 확률 높은 단어는 무엇인가?"**라는 질문에 답하는 것을 한 스텝씩 반복하며 텍스트를 만들어 낸다.

직접 확인해 보자.

- 입력창에 `My hobby`를 입력하고 엔터를 누른다
- 오른쪽 Probabilities 열에 다음 토큰 후보들이 확률 순으로 나타난다. 이 예문에서는 별다른 조절 없이도 `is`가 가장 높은 확률로 올라온다
- Generate를 클릭하면 `is`가 생성되어 입력 뒤에 붙고, `My hobby is`를 입력 삼아 같은 과정이 반복된다

![My hobby를 입력하고 Generate를 누르자 약 69% 확률의 다음 토큰 is가 생성되어 입력 뒤에 붙은 모습]({{site.url}}/assets/images/llmso-transformer-explainer-my-hobby-generate.png){: .align-center width="700"}

<center><sup>Transformer Explainer 화면 직접 캡처. Generate 직후 is가 입력 뒤에 붙은 상태다</sup></center>

화면 상단에는 **Temperature**와 **Top-k / Top-p** 노브가 있다. 확률 분포에서 다음 토큰을 고르는 방식을 조절하는 장치인데, 이 예문에서는 조절하지 않아도 `is`가 바로 최상위에 오므로 지금은 "이런 노브가 있다" 정도만 알아 두면 충분하다. 샘플링 파라미터가 분포를 어떻게 바꾸는지는 확률(Probabilities) 파트를 줌인하는 글에서 다룬다.

<br>

# 한글 입력과 토크나이저의 한계

영어 예문은 잘 도는데, 한글을 넣으면 다른 그림이 나온다.

![한글 문장을 입력하자 입력창의 글자가 깨지고 임베딩 열의 토큰 수가 크게 늘어난 모습]({{site.url}}/assets/images/llmso-transformer-explainer-korean-not-good-result.png){: .align-center width="700"}

<center><sup>Transformer Explainer 화면 직접 캡처. 한글 입력 시 글자가 깨지고 토큰이 잘게 쪼개진다</sup></center>

"요즘 나의 최대 관심사는"이라는 짧은 문장을 넣었을 뿐인데, 입력창의 글자가 깨져 표시되고, 왼쪽 Embedding 열의 토큰 수가 영어 예문과 비교할 수 없게 길어지며, 후보 토큰들도 온전한 글자가 아닌 조각으로 나타난다.

원인은 뒤에서 볼 토크나이제이션(tokenization)의 어휘 사전 문제다.

- GPT-2의 어휘 사전은 **영어 중심**이라 한글 토큰이 거의 없다
- 그래서 한글은 byte-level BPE(Byte Pair Encoding)에 의해 **바이트 단위로 잘게 쪼개진다**. 한글 한 글자는 UTF-8에서 3바이트라, 글자 하나가 토큰 여러 개로 나뉘는 식이다

결과는 세 가지로 이어진다. ① 시퀀스가 불필요하게 길어져 컨텍스트(1,024 토큰)를 낭비하고, ② 한 글자를 만드는 데도 여러 생성 스텝이 필요해 품질과 속도가 떨어지며, ③ 시퀀스가 길어진 만큼 attention 연산량도 늘어난다. 화면에서 임베딩 열이 비정상적으로 길어진 것이 바로 이 현상이다.

참고로 Qwen처럼 어휘 사전이 약 15만 2천 개로 GPT-2의 3배 규모이고 다국어를 포함하는 모델은 사정이 낫지만, 한국어 커버리지는 여전히 제한적인 것으로 알려져 있다. 토크나이저와 어휘 사전이 모델 성능·비용에 미치는 영향은 [임베딩 파트를 줌인하는 글]({% post_url 2026-08-05-AI-LLM-Optimization-02-03-Transformer-Explainer-Embedding %})에서 제대로 다룬다.

<br>

# 전체 아키텍처: 세 부분

화면 상단의 구조 이름들을 따라가면, 트랜스포머 아키텍처가 크게 세 부분으로 구성된다는 것이 보인다.

![Transformer Explainer의 아키텍처 안내: Embedding, Transformer Block(Self-Attention과 MLP), Probabilities 세 부분]({{site.url}}/assets/images/llmso-transformer-explainer-overview.png){: .align-center width="700"}

<center><sup>Transformer Explainer 화면 직접 캡처. 세 부분으로 나뉜 전체 구조 안내</sup></center>

- **Embeddings**: 텍스트를 숫자(벡터)로 바꾼다. 토크나이제이션과 위치 정보 주입이 여기서 일어난다
- **Transformer Blocks**: Self-Attention으로 토큰 사이의 정보를 섞고, MLP로 그 표현을 정제한다. GPT-2 small에서는 동일한 블록이 12번 반복된다
- **Probabilities**: 마지막 표현을 어휘 사전 크기의 점수로 바꾸고, softmax(점수들을 합이 1인 확률 분포로 정규화하는 함수)로 다음 토큰의 확률 분포를 만든다

[앞 글]({% post_url 2026-08-05-AI-LLM-Optimization-02-01-LLM-Transformer-Overview %})에서 용어로만 정리했던 Multi-Head Self-Attention과 MLP가 화면 가운데 블록 안에 그대로 보이고, MLP는 [시리즈 1편]({% post_url 2026-08-05-AI-LLM-Optimization-01-AI-Overview %})에서 본 "선형층 + 활성화" 골격 그대로다.

> *참고*: 예문을 바꿔 가며 관찰하다 보면 Q·K·V 행렬의 크기가 예문마다 달라지는 것처럼 보인다. 달라지는 축은 특징 차원이 아니라 **시퀀스 길이**다. GPT-2 small에서 Q·K·V의 차원(헤드당 64)은 고정이고, 예문마다 토큰 수가 달라 (토큰 수 × 차원) 행렬의 세로 크기가 달라 보이는 것이다. [Self-Attention을 줌인하는 글]({% post_url 2026-08-05-AI-LLM-Optimization-02-04-Transformer-Explainer-Transformer-Block-and-Self-Attention-Layer %})에서 행렬 모양을 따라가며 다시 확인한다.

이 시리즈의 이후 글들은 이 세 부분을 순서대로 줌인한다. Embedding(토크나이제이션·위치 인코딩) → Transformer Block(Self-Attention, MLP) → Probabilities(출력층과 샘플링) 순으로, 각 화면을 뜯어 보며 내부 계산을 따라갈 예정이다.

<br>

# 정리

- Transformer Explainer는 GPT-2 small을 브라우저에서 실행하며 트랜스포머 내부를 시각화한다. 골격이 같으므로 작은 모델로도 기본 구조 학습에는 충분하다
- 트랜스포머의 동작은 "다음에 올 가장 그럴듯한 토큰은 무엇인가"의 반복이고, Generate 버튼으로 그 한 스텝을 직접 확인할 수 있다
- 한글 입력이 망가지는 현상은 영어 중심 어휘 사전과 byte-level BPE의 결과로, 토크나이저가 컨텍스트 효율·생성 품질·연산량에 직결된다는 것을 보여 준다
- 전체 구조는 Embedding → Transformer Block ×12 → Probabilities 세 부분이며, 다음 글부터 이 순서로 하나씩 줌인한다

<br>

# 참고 링크

- [Transformer Explainer](https://poloclub.github.io/transformer-explainer/)
- [Transformer Explainer GitHub 저장소](https://github.com/poloclub/transformer-explainer)
- [Transformer Explainer: Interactive Learning of Text-Generative Models (논문)](https://arxiv.org/abs/2408.04619)
- [LLM 서빙과 최적화 - 2.1. LLM과 트랜스포머 개요]({% post_url 2026-08-05-AI-LLM-Optimization-02-01-LLM-Transformer-Overview %})

<br>
