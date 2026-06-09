---
title: "[GenAI] GenAI on K8s: 4.1 - 도메인 특화 최적화 개요와 LangChain"
excerpt: "범용 LLM의 한계, 3가지 도메인 최적화 기법, LangChain 프레임워크 구조, 그리고 Agent가 실제로 LLM에 보내는 prompt를 들여다보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - GenAI
  - LLM
  - LangChain
  - RAG
  - Fine-tuning
  - Prompt-Engineering
  - Kubernetes-for-Generative-AI-Solutions
  - Kubernetes-for-Generative-AI-Solutions-Chapter-4
use_math: false
---

*[Kubernetes for Generative AI Solutions(Packt 2025, ISBN 978-1-83620-993-5, 저자 Ashok Srirama / Sukirti Gupta)](https://github.com/PacktPublishing/Kubernetes-for-Generative-AI-Solutions) 4장의 학습 내용을 바탕으로 합니다*

<br>

[이전 글]({% post_url 2026-05-24-Kubernetes-GenAI-on-K8s-02-Kubernetes-Introduction-and-Integration-with-GenAI %})에서 K8s 아키텍처와 GenAI 워크로드 통합을 다뤘다. 이번 글에서는 범용 LLM을 **도메인 특화** 유스케이스에 맞게 최적화하는 기법들의 개요와 LangChain 프레임워크를 정리한다.

<br>

# TL;DR

- 범용 LLM은 도메인 전문 용어(jargon)와 맥락에 약하고, knowledge cut-off 문제가 있다. 도메인 특화 최적화가 필요한 이유다
- 3가지 주요 최적화 기법: Prompt Engineering(비용 낮음, 가중치 변경 없음) → RAG(외부 지식 검색·주입, 인프라 필요) → Fine-tuning(가중치 직접 조정, 비용 높음)
- LangChain은 Memory, Agents, Chains, Tool Integration 4가지 구성 요소로 LLM 애플리케이션을 구조화하는 프레임워크다
- LangChain Agent의 실체는 ReAct(Reasoning + Acting) 포맷의 프롬프트 엔지니어링 wrapper다. LLM은 여전히 stateless single call이고, Agent가 Thought/Action/Observation 루프를 자동화한다

<br>

# 도메인 특화 최적화가 필요한 이유

LLM은 광범위한 데이터로 사전학습된 범용 모델이다. 다양한 task를 처리할 수 있지만, **도메인 깊이가 필요한 문제에는 부적합**하다. 두 가지 근본적인 이유가 있다.

- **도메인 전문성 부족**: 범용 학습 데이터로는 특정 산업의 jargon(전문 용어), 맥락, 규제 요건을 충분히 커버하지 못한다
- **Knowledge cut-off(지식 단절)**: 학습 시점 이후의 사건, proprietary dataset(독점 데이터), 실시간 정보를 알 수 없다

## 범용 모델 vs 도메인 특화 모델

| 항목 | 범용 모델 | 도메인 특화 모델 |
|---|---|---|
| 강점 | versatile, 다양한 task 처리 | 특정 task의 정확도·효율·신뢰성 |
| 약점 | 도메인 jargon·맥락에 약함 | 범위 밖 task는 성능 하락 |
| 학습 데이터 | 광범위·일반적 | 도메인 코퍼스 |
| 운영 비용 | 모델 공유로 절감 가능 | 별도 학습·운영 필요 |

## 3가지 최적화 기법 비교

도메인 특화를 달성하는 대표적인 기법 세 가지를 비용·복잡도 순으로 정리하면 다음과 같다.

| 기법 | 정의 | 모델 가중치 변경 | 외부 데이터 의존 | 비용·복잡도 |
|---|---|---|---|---|
| Prompt Engineering | 특정 도메인에 적합한 출력을 유도하도록 prompt 구조를 설계 | X | X (prompt에 inline 가능) | 낮음 — 코드만 |
| Knowledge Distillation (RAG) | 외부 지식 베이스에서 관련 문서를 검색해 LLM의 context에 주입 | X | O (벡터 DB) | 중 — 인프라 필요 |
| Fine-tuning | 도메인 데이터로 사전학습 모델을 추가 학습. 가중치를 조정해 도메인 jargon·지식을 내재화 | O | X (학습 시점에만) | 높음 — GPU·데이터 큐레이션 |

세 기법은 배타적이 아니라 **조합**해서 사용하는 경우가 많다. 예를 들어 Fine-tuning으로 도메인 지식을 내재화한 모델에 RAG로 최신 문서를 보강하고, Prompt Engineering으로 출력 형식을 제어하는 식이다.

이 글에서는 전체 개요와 LangChain 프레임워크를 다루고, RAG 실습은 [다음 글]({% post_url 2026-05-24-Kubernetes-GenAI-on-K8s-04-02-RAG %}), Fine-tuning(QLoRA)은 [그 다음 글]({% post_url 2026-05-24-Kubernetes-GenAI-on-K8s-04-03-Fine-Tuning-QLoRA %})에서 각각 상세히 다룬다.

<br>

# LLM 모델 선택

도메인 최적화의 출발점은 어떤 LLM을 base로 쓸 것인가다. 주요 Provider(제공자)와 대표 모델을 정리하면 다음과 같다.

| Provider | 대표 모델 | 라이선스 | 특징 |
|---|---|---|---|
| Anthropic | Claude 4 (Opus/Sonnet/Haiku) | closed-source (API only) | 안전성·long context 강점 |
| OpenAI | GPT-4o, gpt-3.5-turbo | closed-source (API only) | 가장 광범위한 ecosystem |
| Cohere | Command R+ | closed-source (API only) | 엔터프라이즈 RAG 특화 |
| Meta (Llama) | Llama 3 (8B/70B/405B) | open-weight (Community License) | self-host 가능. 본 실습에서 fine-tune 대상 |

선택 기준은 라이선스(상업 사용·재배포·Fine-tuning 후 배포 가능 여부), 성능, 비용, 데이터 프라이버시 요구사항에 따라 달라진다.

## AWS Bedrock

AWS Bedrock은 fully managed 서비스로, 여러 provider의 pre-trained 모델을 **통합 API**로 제공한다. Anthropic Claude, Meta Llama, Cohere 등 다양한 모델을 하나의 인터페이스로 호출할 수 있어, 멀티 모델 전략을 쉽게 구현할 수 있다. 본 실습에서는 사용하지 않지만, 프로덕션 환경에서 모델 교체·A/B 테스트 시 유용하다.

<br>

# LangChain 프레임워크

LangChain은 LLM 기반 애플리케이션을 구조화하기 위한 프레임워크다. LLM API 호출을 감싸서 메모리 관리, 도구 연동, 멀티스텝 추론 등을 자동화한다. 핵심 구성 요소는 4가지다.

| 구성 요소 | 역할 | 대표 클래스/함수 |
|---|---|---|
| Memory | 세션 내 이전 대화를 기억 → context continuity(문맥 연속성) 제공 | `ConversationBufferMemory`, `ConversationSummaryMemory` |
| Agents | 의사결정·행동·tool/API 호출을 자율적으로 수행 | `create_python_agent`, `create_react_agent` |
| Chains | 여러 LLM 연산을 sequence로 연결 → multi-step reasoning(다단계 추론) | `LLMChain`, `RetrievalQA` |
| Tool Integration | LLM이 외부 tool·API를 호출 (DB 조회, 웹 검색 등) | `PythonREPLTool`, `WikipediaQueryRun` |

표에서 Memory를 짚고 넘어갈 부분이 있다. LLM API 자체는 매 호출이 독립적인 **stateless** 서비스다. ChatGPT나 Claude 웹 UI에서 보이는 "memory"는 두 가지 중 하나다: (a) 시스템 prompt에 사용자 프로필을 주입하거나 (b) 매 호출마다 대화 히스토리를 다시 전송하는 것이다. LangChain의 Memory는 (b)를 자동화한 wrapper다. LLM이 "기억한다"는 건 메모리에 저장된 게 아니라, **이전 대화를 매번 다시 보내주는 것**이다.

<br>

# 실습: LangChain Agent

LangChain Agent가 실제로 어떻게 동작하는지, debug 모드를 켜서 LLM에 보내는 prompt까지 들여다보자.

## langchain 0.x → 1.x 마이그레이션

책의 원본 코드는 langchain 0.x 기준이다. 1.x에서는 import 경로와 호출 방식이 바뀌었다.

| 원본 (0.x) | 수정 (1.x) | 이유 |
|---|---|---|
| `from langchain.chat_models import ChatOpenAI` | `from langchain_openai import ChatOpenAI` | 1.x에서 미노출 → ImportError |
| `import langchain; langchain.debug = True` | `from langchain_core.globals import set_debug; set_debug(True)` | 모듈 레벨 attribute 폐기 |
| `agent.run("...")` | `result = agent.invoke({"input": "..."})` | Chain.run deprecated |

## Agent 코드

```python
import os
from langchain_experimental.agents.agent_toolkits import create_python_agent
from langchain_experimental.tools.python.tool import PythonREPLTool
from langchain_openai import ChatOpenAI
from langchain_core.globals import set_debug

llm = ChatOpenAI(model="gpt-3.5-turbo", api_key=os.environ["OPENAI_API_KEY"])
agent = create_python_agent(llm, tool=PythonREPLTool(), verbose=False)
set_debug(True)

fruit_list = ['Apple', 'Banana', 'Apple', 'Peaches']
agent.invoke({"input": f"Count how many times a fruit is in this list and list every fruit and the numbers: {fruit_list}"})
```

`create_python_agent()`는 내부적으로 `ZERO_SHOT_REACT_DESCRIPTION` AgentType을 사용한다. PythonREPLTool은 sandbox가 아니라 `exec()` 기반이므로, 프로덕션에서는 보안에 주의해야 한다.

## Debug 출력: LLM에 보내는 실제 Prompt

`set_debug(True)`를 켜면 LangChain이 LLM에 보내는 실제 prompt를 볼 수 있다. Agent의 정체를 파악하는 핵심 단서다.

<br>

<details markdown="1">
<summary><b>Debug output — system prompt 전문</b></summary>

<br>

```text
Human: You are an agent designed to write and execute python code to answer questions.
You have access to a python REPL, which you can use to execute python code.
If you get an error, debug your code and try again.
Only use the output of your code to answer the question.
You might know the answer without running any code, but you should still run the code to get the answer.
If it does not seem like you can write code to answer the question, just return "I don't know" as the answer.

Python_REPL - A Python shell. Use this to execute python commands. Input should be a valid python command. If you want to see the output of a value, you should print it out with `print(...)`.

Use the following format:
Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [Python_REPL]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!
Question: Count how many times a fruit is in this list and list every fruit and the numbers: ['Apple', 'Banana', 'Apple', 'Peaches']
Thought:
```

</details>

이 prompt가 바로 **ReAct(Reasoning + Acting) 포맷**이다. LangChain은 이 문자열 패턴을 정규식으로 파싱해서 `Action: Python_REPL` / `Action Input: <code>` 부분을 추출하고, 해당 tool을 실행한다.

## LLM의 1차 응답

LLM은 ReAct 포맷에 맞춰 코드를 생성한다.

```python
fruits = ['Apple', 'Banana', 'Apple', 'Peaches']
fruit_count = {}
for fruit in fruits:
    if fruit in fruit_count:
        fruit_count[fruit] += 1
    else:
        fruit_count[fruit] = 1
print(fruit_count)
```

LangChain은 `Action: Python_REPL`과 `Action Input:`을 파싱해 위 코드를 `PythonREPLTool`로 실행하고, stdout 출력을 `Observation:`으로 append한다.

## Agent 실행 흐름

전체 흐름을 시퀀스로 나타내면 다음과 같다.

```text
User prompt
    │
    ▼
AgentExecutor (LangChain)
    │ 1) build system prompt with ReAct format
    ▼
ChatOpenAI (LLM call #1)  ── 2.38s, "Action: Python_REPL ..."
    │ 2) parse "Action: Python_REPL" / "Action Input: <code>"
    ▼
PythonREPLTool.invoke(<code>)  ── 코드 실행, stdout 캡처
    │ 3) append "Observation: <stdout>" to prompt
    ▼
ChatOpenAI (LLM call #2)  ── 1.10s, "Final Answer: {'Apple': 2, ...}"
    │ 4) parse "Final Answer:" → terminate
    ▼
{'output': "{'Apple': 2, 'Banana': 1, 'Peaches': 1}"}
```

AgentExecutor가 LLM과 Tool 사이를 중개하며, `Final Answer:`가 나올 때까지 Thought → Action → Observation 루프를 반복한다.

## 실행 결과

| 항목 | 값 |
|---|---|
| exit code | 0 |
| 사용 모델 | gpt-3.5-turbo-0125 |
| LLM 호출 횟수 | 2회 (1차: 코드 생성, 2차: 결과 해석) |
| LLM 호출 시간 합 | ~3.5초 |
| Token usage | prompt ~200 + completion ~80 = ~280 tokens |
| 예상 비용 | < $0.001 |
| 최종 출력 | {'Apple': 2, 'Banana': 1, 'Peaches': 1} |

## 핵심 학습 포인트

1. **Agent ≠ LLM 자체**. Agent는 프롬프트 엔지니어링 wrapper다. LLM은 여전히 stateless single call이다. Agent가 하는 일은 (a) ReAct 포맷 prompt를 조립하고 (b) LLM 응답에서 Action/Action Input을 파싱하고 (c) Tool을 실행해 Observation을 만들고 (d) 다시 LLM에 던지는 루프다
2. **ReAct 포맷 = 단순 string 패턴**. `Thought:`, `Action:`, `Action Input:`, `Observation:`, `Final Answer:` 같은 키워드를 LangChain이 정규식으로 파싱한다. LLM이 이 포맷을 지키도록 system prompt에서 강제하는 구조다
3. **PythonREPLTool은 sandbox가 아니다**. `exec()` 기반이므로 LLM이 생성한 코드가 호스트 환경에서 그대로 실행된다. 프로덕션에서는 반드시 격리된 실행 환경(컨테이너, gVisor 등)을 적용해야 한다
4. **AgentType**: `create_python_agent()`는 내부적으로 `ZERO_SHOT_REACT_DESCRIPTION`을 사용한다. few-shot 예시 없이 도구 description만으로 LLM이 어떤 tool을 쓸지 결정하는 방식이다

## LangChain Agent vs 직접 구현

[이전에 AI Agent를 직접 구현한 글]({% post_url 2026-02-08-Dev-AI-Agent %})에서 OpenAI SDK의 Function Calling과 Agentic Loop를 저수준으로 다뤘다. LangChain Agent와의 차이를 비교하면 다음과 같다.

| | 직접 구현 (Function Calling) | LangChain Agent (ReAct) |
|---|---|---|
| Tool 호출 메커니즘 | Function Calling — LLM이 구조화된 JSON으로 tool 호출 정보 반환 | ReAct 문자열 파싱 — LLM이 `Action: Tool이름` / `Action Input: 인자` 텍스트를 생성하면 정규식으로 파싱 |
| Agentic Loop | `while message.tool_calls:` 직접 구현 | `AgentExecutor`가 내부 처리 |
| Tool 정의 | JSON Schema (`tools` 파라미터로 전달) | Python 클래스 (`PythonREPLTool` 등) |
| 추상화 수준 | 저수준 — 메시지 히스토리, tool 결과 피드백 직접 관리 | 고수준 — `create_python_agent()` 한 줄 |
| 보안 제어 | Tool 실행 핸들러에서 직접 제약 (예: SQL `SELECT` only) | Tool 클래스 자체의 구현에 의존 |

결국 두 접근 모두 같은 패턴(LLM 추론 → Tool 실행 → 결과 관찰 → 재추론)의 루프다. LangChain은 이를 추상화해 빠르게 프로토타이핑할 수 있게 해주지만, 내부에서 일어나는 일을 이해하려면 직접 구현 경험이 도움이 된다.

<br>

# 정리

- **범용 LLM의 한계**: 도메인 jargon·맥락 이해 부족, knowledge cut-off 문제. 도메인 특화 최적화가 필수다
- **3가지 기법은 비용-효과 트레이드오프**: Prompt Engineering(저비용·빠른 적용) → RAG(외부 지식 보강·인프라 필요) → Fine-tuning(가중치 변경·고비용). 실무에서는 조합해서 사용한다
- **LangChain의 역할**: LLM API의 stateless 한계를 Memory/Chains/Agents/Tools로 감싸서 구조화된 애플리케이션을 만들 수 있게 해준다
- **Agent의 실체**: LLM에 ReAct 포맷 prompt를 보내고, 응답을 정규식으로 파싱해 Tool을 실행하는 루프. 마법이 아니라 프롬프트 엔지니어링이다

<br>

# 참고 링크

- [Kubernetes for Generative AI Solutions - GitHub](https://github.com/PacktPublishing/Kubernetes-for-Generative-AI-Solutions)
- [LangChain 공식 문서](https://python.langchain.com/docs/get_started/introduction)
- [LangChain Agents 개념](https://python.langchain.com/docs/concepts/agents/)
- [ReAct: Synergizing Reasoning and Acting in Language Models (Yao et al. 2022)](https://arxiv.org/abs/2210.03629)

<br>
