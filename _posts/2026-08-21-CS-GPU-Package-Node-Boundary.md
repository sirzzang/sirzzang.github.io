---
title: "[GPU] GPU 패키징과 노드 경계: die에서 랙까지"
excerpt: "GPU 인터커넥트의 경계가 무엇으로 정해지는지 die부터 랙까지 따라가 보자."
categories:
  - CS
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - GPU
  - Chiplet
  - HBM
  - NVLink
  - NUMA
  - PCIe
  - Datacenter
  - Hands-On-LLM-Serving-and-Optimization-Study
  - Hands-On-LLM-Serving-and-Optimization-Study-Week-3
last_modified_at: 2026-08-22
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Hands-On LLM Serving and Optimization Study (LLMSO) 3주차 학습 중 딥다이브한 내용입니다.*

<br>

# TL;DR

- 인터커넥트의 경계선을 부르는 용어는 chip이 아니라 package다. chip은 문맥에 따라 die를 뜻하기도 package를 뜻하기도 해서 경계 용어로 쓰면 흔들린다
- 그 경계는 고정이 아니다. H100 세대까지는 패키지 밖부터가 인터커넥트였지만, Blackwell은 패키지 안의 die↔die 링크(NV-HBI)까지 인터커넥트라 부른다. die를 2개로 잘라 붙이고도 GPU 1장으로 보이려면 그 링크가 자기 HBM보다 빨라야 한다
- 노드의 경계는 물리가 정한다. 전력·냉각(공랭 약 10kW), CPU의 PCIe 레인 예산(2소켓 128 ~ 160레인), NUMA 균형이 겹쳐 8-GPU 노드가 업계 표준이 됐다
- GB200 NVL72는 액랭과 랙 내부 구리 배선으로 스케일업 도메인(NVLink 범위)을 섀시에서 랙(72 GPU)으로 끌어올렸다. 관리 단위(OS)와 스케일업 단위가 처음으로 분리된 사례다

<br>

# 패키징 어휘

3주차 학습 내용 [5.3편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-03-LLM-Serving-Challenge-GPU-Interconnect-Selection %})은 인터커넥트를 "패키지 경계 밖으로 주소 공간을 확장하는 링크"로 정의한다. 그 경계를 정확히 부르려면 반도체 패키징 어휘가 필요하다. 제조 순서를 따라가면 자연스럽게 정리된다.

![Wafer에서 Die를 거쳐 Package가 되는 제조 공정 순서]({{site.url}}/assets/images/llmso-gpu-chip-hardware-process.png){: .align-center width="680"}

<center><sup>AI를 이용해 직접 그린 도식. Wafer → Die → Package로 이어지는 공정 순서가 곧 추상화 순서다</sup></center>

| 순서 | 용어 | 정의 | 성질 |
| --- | --- | --- | --- |
| 1 | Wafer | 회로를 한꺼번에 새기는 실리콘 원판 (300mm) | 재료 |
| 2 | Die | 웨이퍼에서 잘라낸 회로 조각 하나 | 기본 단위 |
| 3 | Chiplet | 큰 기능을 여러 die로 쪼갰을 때의 각 조각 | 설계 전략 (die의 역할 이름) |
| 4 | Interposer | die들을 올려 고밀도 배선으로 잇는 중간 판 | 조립 |
| 5 | Substrate | 패키지 바닥 기판. 외부로 신호·전원을 낸다 | 조립 |
| 6 | Package | 위 전부를 봉지해 하나의 부품으로 만든 것 | 완성 |
| 7 | SiP | 성격이 다른 die를 한 패키지에 담은 형태 | 패키지의 유형 |
| 8 | C2C | 패키지(칩) 사이를 잇는 연결 | 링크 |
| — | Chip | 보통 6번을, 문맥에 따라 2번을 가리키는 구어 | 호칭 |

포함 관계로 정렬하면 `Package ⊃ Substrate ⊃ Interposer ⊃ Die(= Chiplet)`이다. 단면으로 보면 이렇다.

```
┌─ Package ─────────────────────────────┐ ← 부품으로 팔리는 단위 (= 흔히 "Chip")
│                                       │
│  ┌ GPU die ┐ ┌ HBM ┐ ┌ HBM ┐          │ ← Die / Chiplet: 회로가 실제로 있는 실리콘
│  └─────────┘ └─────┘ └─────┘          │
│  ═══════════ Interposer ══════════    │ ← die끼리 잇는 고밀도 중간 판
│  ─────────── Substrate ───────────    │ ← 바닥 기판. 외부 핀/볼로 신호·전원 배출
└───────────────────────────────────────┘
                    ↕  C2C                ← 패키지 밖으로 나가는 칩 간 연결
```

![GPU 패키지 단면 구조. Substrate, Interposer, Die와 HBM, 패키지 경계와 C2C 링크]({{site.url}}/assets/images/llmso-gpu-chip-hardware-structure.png){: .align-center width="680"}

<center><sup>AI를 이용해 직접 그린 도식. 점선이 인터커넥트 경계선(패키지)이고, 애매한 것(die↔die, die↔HBM)은 전부 점선 안, C2C부터가 밖이다</sup></center>

![TSMC CoWoS 패키징 구조]({{site.url}}/assets/images/llmso-gpu-hardware-structure-2.png){: .align-center width="640"}

<center><sup>출처: <a href="https://3dfabric.tsmc.com/english/dedicatedFoundry/technology/cowos.htm">TSMC 3DFabric — CoWoS</a></sup></center>

이 사다리에서 흔히 헷갈리는 지점 세 가지만 짚는다.

- **Wafer는 사다리의 층이 아니다.** die의 상위 개념이 아니라 원재료다. 웨이퍼 1장에서 die 수십 ~ 수백 개가 나온다
- **Chiplet은 크기 개념이 아니라 설계 전략이다.** 수율 때문에 큰 die를 못 만들어 쪼갠 것이고, 쪼갠 조각을 이을 배선이 필요해져 Interposer와 C2C가 등장한다. 즉 3 → 4 → 8은 인과로 이어진 흐름이다
- **C2C는 몸통이 아니라 링크다.** 칸이 아니라 칸 사이에 있다

이 어휘에서 실제로 챙길 결론은 한 줄이다. **경계선을 부를 때는 chip이 아니라 package(또는 die)를 쓴다.** chip은 die를 가리키기도 package를 가리키기도 해서, 인터커넥트 경계를 논할 때 쓰면 개념이 흔들린다. 예를 들어 HBM은 GPU 연산 die와 별개 die지만 실리콘 인터포저로 붙어 같은 패키지 안에 있다 — "칩 밖"이라고 하면 HBM이 안인지 밖인지 애매해지지만, "패키지 안"이라고 하면 명확하다.

<br>

# 인터커넥트의 경계

## 세대별 경계 이동

그렇다면 인터커넥트의 경계는 패키지로 고정인가. 아니다. 세대마다 움직인다.

| 어디를 넘는가 | 이름 | 인터커넥트인가 |
| --- | --- | --- |
| die ↔ die (한 패키지 안) | NV-HBI | 넓게 보면 예 (Blackwell) |
| die ↔ HBM (인터포저 위) | HBM 인터페이스 | 관례상 아니오 (메모리로 센다) |
| 칩 ↔ 칩 (패키지 밖, CPU↔GPU) | NVLink-C2C | 예 |
| GPU ↔ GPU (보드 위) | NVLink · NVSwitch · PCIe | 예 |
| 노드 ↔ 노드 | InfiniBand · RoCE | 예 |

H100 문맥에서 인터커넥트의 경계는 패키지 밖이었다. 그런데 Blackwell부터는 패키지 안에도 인터커넥트가 생겼다. NV-HBI는 한 패키지 안에서 Blackwell die 두 개를 약 10TB/s로 붙여 OS에는 단일 GPU로 보이게 하는 링크인데, NVIDIA는 이것을 인터커넥트라고 부른다. "패키지 밖 = 인터커넥트"로 정의를 고정하면 이 세대에서 바로 깨지는 것이다.

![패키지를 인터커넥트 경계로 볼 때 H100과 B200의 구조 비교]({{site.url}}/assets/images/llmso-gpu-interconnect-comparison.png){: .align-center width="720"}

<center><sup>AI를 이용해 직접 그린 도식. 구조는 그대로고, 가운데 die가 둘로 쪼개지면서 그 사이에 링크(NV-HBI)가 하나 생긴 것이 전부다 (B200 기준)</sup></center>

헷갈리지 않으려면 두 경계를 구분하면 된다.

| 구분 | H100 | B200 |
| --- | --- | --- |
| 논리 경계 (어디까지가 GPU 1장인가) | 패키지 | 패키지 (그대로) |
| 용어 경계 (어디부터 인터커넥트라 부르나) | 패키지 밖 | 패키지 안까지 |

안쪽에 새 "경계"가 생긴 것이 아니라, 안쪽에 새 절단면(cut)이 생겼고 그것을 이을 링크가 필요해진 것이다. OS도 vLLM도 B200 한 패키지를 여전히 GPU 1장으로 본다. 인터커넥트라는 용어의 범위는 좁아진 게 아니라 넓어졌다 — 목록에 안쪽 항목이 추가됐을 뿐 기존 항목이 빠지지는 않았다.

## 단일 GPU의 조건

왜 갑자기 die를 잘랐을까. 난이도의 문제라기보다 그때 처음 자를 필요가 생겼기 때문이다. 노광기가 한 번에 찍을 수 있는 die 크기(레티클 한계)가 약 858mm²인데, H100의 GH100 die가 이미 약 814mm²로 그 벽에 붙어 있었다. B200은 한계 크기의 die 2개를 붙여 약 1600mm²를 만든 것이다. 자를 필요가 없으면 이을 링크도 필요 없다 → 레티클 한계에 부딪혔다 → 잘랐다 → 자른 것을 숨길 링크가 필요해졌다는 흐름이다.

어려운 것은 링크 자체가 아니다. 링크는 오히려 패키지 안에 만드는 쪽이 쉽고 유리하다. 거리가 mm 단위라 비트당 에너지가 낮고 재전송·리타이머가 필요 없어, NVLink(약 1.8TB/s급)보다 NV-HBI(약 10TB/s)가 훨씬 빠르다. 어려운 것은 **잘랐다는 사실을 숨기는 것**이다. 합격선은 die↔die 링크가 자기 HBM보다 빠른가다.

| 구간 | 대역폭 (대략) |
| --- | --- |
| die 내부 배선 (자르지 않았을 때) | 수십 TB/s 이상 |
| NV-HBI (B200 die↔die) | 약 10 TB/s |
| NVLink 5 (GPU↔GPU) | 약 1.8 TB/s |
| PCIe Gen5 | 0.128 TB/s |

링크가 자기 HBM보다 느리면, 옆 die의 데이터를 쓰는 것이 자기 메모리를 읽는 것보다 비싸져서 "어느 die에 있느냐"가 성능에 드러난다. 그러면 소프트웨어가 배치를 신경 써야 하고, 그것은 이미 GPU 2장이다.

| 사례 | die↔die 링크 | 자기 HBM | 결과 |
| --- | --- | --- | --- |
| B200 (NV-HBI) | 약 10 TB/s | 약 8 TB/s | 링크가 더 빠름 → GPU 1장으로 보임 |
| AMD MI250X (Infinity Fabric) | 수백 GB/s급 | 1.6 TB/s (GCD당) | 링크가 몇 배 느림 → GPU 2장으로 보임 |

실제 반례가 MI250X다. die 2개를 한 패키지에 넣었지만 OS에는 GPU 2개(2 GCD)로 보였다. 안쪽에 링크를 만들지 못해서가 아니라, 만들었는데도 HBM보다 느렸기 때문이다(MI300X에서야 하나로 합쳐졌다). 대역폭 외에 숨기기 위해 더 필요한 것들도 있다.

- **단일 주소 공간**: 두 die의 HBM이 하나의 연속된 메모리로 보여야 한다
- **캐시 일관성**: 한쪽 die의 L2에 있는 값을 다른 die가 읽을 때 자동으로 최신 값이 와야 한다 — 멀티코어 CPU에서 두 코어가 한 메모리를 공유할 때와 같은 부류의 일관성 문제를 하드웨어 계층에서 푸는 것이다
- **스케줄러 통합**: 하나의 커널이 두 die의 SM에 걸쳐 뿌려져야 한다

이것은 링크 배선이 아니라 아키텍처 설계의 영역이고, 하나만 빠져도 OS나 드라이버가 장치를 2개로 노출하게 된다.

<br>

# 노드의 경계

## 노드의 세 정의

패키지 밖으로 나가면 다음 경계는 노드다. 보통 노드의 정의는 세 가지가 겹친다.

- **관리 단위**: OS 인스턴스 1개 = Kubernetes Node 1개
- **물리 단위**: 메인보드 1개(2소켓) = 섀시 1대
- **스케일업 단위**: NVLink 도메인 1개 = 최대 8 GPU

전통적인 8-GPU 서버에서는 이 셋이 정확히 일치했다. 그래서 "노드 안/밖"이라는 말이 모호함 없이 통했다. 물리 계층부터 정리하면:

| 단위 | 정의 | 규격·숫자 |
| --- | --- | --- |
| 소켓 | 메인보드에 CPU 패키지 1개를 꽂는 자리 | LGA 4677(Intel), SP5(AMD) 등 |
| 메인보드 | 소켓·DIMM·PCIe 슬롯이 붙은 기판 | 2소켓 보드 = 소켓 2개 |
| 섀시 | 메인보드·GPU·PSU·팬을 담는 금속 박스 1대 = 보통 노드 1개 | 1U ~ 8U |
| 랙 | 섀시를 세로로 꽂는 캐비닛 | 19인치 폭, 보통 42U, 10 ~ 20kW |

U(rack unit)는 높이 단위로 1U = 1.75인치 = 44.45mm다. 19인치 폭 + U 배수 높이는 EIA-310 표준이라 벤더가 달라도 호환된다. 8-GPU 공랭 서버는 실제로 7 ~ 8U를 차지한다. 42U 랙에 물리적으로는 5대까지 들어가지만, 전력 예산(10 ~ 20kW) 때문에 1 ~ 2대만 넣고 비워 두는 경우가 흔하다.

![소켓, 2소켓 메인보드, 섀시, 랙으로 이어지는 물리 계층과 GB200 NVL72 랙 스케일 노드]({{site.url}}/assets/images/llmso-socket-mainboard-chassis-rack.png){: .align-center width="780"}

<center><sup>AI를 이용해 직접 그린 도식. 소켓 → 메인보드 → 섀시 → 랙 계층과, 스케일업 도메인이 랙으로 확장된 GB200 NVL72(하단). 그림의 논리 노드(logical node)는 NVLink 도메인을 가리키며, OS 관리 단위는 여전히 컴퓨트 트레이다 — 구분은 <a href="#8-gpu-표준과-그-너머">8-GPU 표준과 그 너머</a> 참고. 랙 좌측 U 눈금은 개략적 표현이다</sup></center>

한 노드에 GPU를 몇 장까지 담을 수 있는가 — 이 답이 보통 8인 이유는 물리 법칙이 아니라 여러 제약이 겹쳐 업계 표준으로 굳은 결과다. 이유를 하나씩 보자.

## 전력과 냉각

H100/H200 SXM은 장당 700W, B200은 1000W대의 전력을 쓴다. 8장이면 GPU만 5.6 ~ 8kW이고, CPU·메모리·NIC·팬까지 합치면 노드 하나가 10kW 안팎이다. 공랭 기준 4 ~ 8U 섀시가 감당할 수 있는 열량이 딱 이 근처고, 일반 랙의 전력 예산(10 ~ 20kW)도 노드 하나로 거의 소진된다. 16장으로 늘리려면 섀시가 아니라 랙 설계 자체가 바뀌어야 한다.

## PCIe 레인 예산

PCIe 레인은 데이터가 지나가는 차선 1개다(송신·수신 차동쌍 각 1개로 구성된 full-duplex 직렬 링크). 레인은 CPU가 몇 개를 뽑아줄 수 있는지 정해진 유한 자원이다.

| 세대 | 레인당 단방향 | x16 단방향 | x16 양방향 합계 |
| --- | --- | --- | --- |
| PCIe Gen3 | 약 1 GB/s | 약 16 GB/s | 약 32 GB/s |
| PCIe Gen4 | 약 2 GB/s | 약 32 GB/s | 약 64 GB/s |
| PCIe Gen5 | 약 4 GB/s | 약 63 GB/s | 약 128 GB/s |

Intel Xeon Scalable은 소켓당 80레인, AMD EPYC은 소켓당 128레인(2소켓 구성에서는 일부를 소켓 간 연결에 사용)이라, 2소켓 서버의 실사용 레인은 보통 128 ~ 160개다. 데이터센터 GPU는 전부 x16 인터페이스로 설계되어 있으므로 산수가 이렇게 된다.

```
GPU 8장 × 16레인          = 128레인
+ NIC (400G IB/RoCE는 x16) × 2~8장
+ NVMe SSD (각 x4)
+ BMC, 부팅 디바이스 등
─────────────────────────────
CPU가 주는 128~160레인을 초과
```

GPU 8장만으로 레인 예산이 거의 소진되고, 네트워크·스토리지를 붙이면 이미 부족하다. 참고로 SXM 폼팩터에서도 각 GPU는 host와 x16 PCIe로 연결된다. 다만 GPU↔GPU 트래픽이 PCIe를 안 쓰고 NVLink/NVSwitch로 우회하기 때문에, PCIe는 host 통신·NIC·스토리지 경로 전용으로 남는 것이다.

## NUMA와 배치

2소켓 서버는 NUMA(Non-Uniform Memory Access) 구조다. 각 CPU 소켓이 자기 로컬 메모리 채널과 자기 PCIe 루트를 갖고, 다른 소켓의 메모리·장치에 접근하려면 소켓 간 링크(Intel UPI, AMD Infinity Fabric)를 한 번 더 건너야 한다. 이 홉을 건너면 지연이 늘고 대역폭이 깎인다.

```
[좋음 - 로컬 경로]
CPU0 ── 로컬 DRAM ── PCIe(CPU0) ── GPU0 ── NIC0
   같은 소켓 안에서 host→device 복사, GPUDirect RDMA 완결

[나쁨 - 크로스 소켓 경로]
CPU0 ── 로컬 DRAM ─┐
                   UPI/IF 홉   ← 여기서 병목/지연
CPU1 ── PCIe(CPU1) ┴─ GPU5
```

GPU 8장을 소켓당 4장씩(4+4) 배치하면 레인이 균등하게 나뉘고(소켓마다 4×16 = 64레인), GPU마다 같은 소켓의 NIC·NVMe와 짝지어 데이터 로딩과 RDMA를 소켓 안에서 끝낼 수 있으며, 서빙 프로세스를 `numactl --cpubind --membind`로 같은 소켓에 고정하면 UPI 통과를 피할 수 있다. 반대로 6+2처럼 비대칭으로 붙이면 한쪽 소켓은 포화되고 반대쪽 GPU들은 크로스 소켓 홉을 강제로 타서, 같은 서버 안에서 GPU마다 성능이 달라지는 상황이 생긴다. `nvidia-smi topo -m`에서 `SYS`로 표시되는 경로가 바로 소켓을 건너는 경로다.

## PCIe 스위치 오버서브스크립션

레인 예산을 넘어 GPU를 더 붙이려면 CPU와 GPU 사이에 PCIe 스위치 칩을 끼워 팬아웃해야 한다.

```
[오버서브스크립션 없음 - 1:1]
CPU ─x16─ GPU0
CPU ─x16─ GPU1        레인 소모: 32
    각 GPU가 x16 전용 → 각각 ~64 GB/s

[4:1 오버서브스크립션]
              ┌─x16─ GPU0
CPU ─x16─ [SW]┼─x16─ GPU1
   ↑          ├─x16─ GPU2
 업스트림     └─x16─ GPU3     레인 소모: 16
 x16 하나를 4장이 공유
```

다운스트림은 x16씩 4개인데 CPU로 나가는 업스트림은 x16 하나라, 4장이 동시에 host → device 복사를 하면 GPU당 실효 대역폭이 1/4(약 16GB/s)로 떨어진다. 뉘앙스가 하나 있는데, GPU↔GPU P2P는 스위치 내부에서 처리되어 업스트림을 안 타고 full x16이 나온다. 병목은 업스트림을 타는 트래픽 — host→device 복사, NIC 방향 GPUDirect RDMA, 체크포인트 로딩 — 에 걸린다.

LLM 서빙에서 이 경로가 문제 되는 지점은 세 곳이다. 모델 로딩(디스크 → CPU 메모리 → GPU 메모리 경로가 정확히 업스트림을 탄다 — 671B급 가중치를 밀어넣을 때 대역폭이 1/4이면 콜드 스타트가 몇 배 길어져 오토스케일링 대응에 직결된다), NVLink 없는 구성에서의 TP all-reduce, 그리고 KV 캐시·prefix 캐시를 CPU 메모리로 내리는 오프로딩이다.

참고로 추론·렌더링용 PCIe GPU 서버 중에는 10장, 16장씩 넣는 제품도 있다. 같은 GPU인데 가능한 이유는 워크로드 성격이다 — GPU마다 독립 모델을 돌리는 식이라 GPU 간 통신이 거의 없어 오버서브스크립션의 병목을 감수할 수 있고, 카드 자체도 SXM 대비 저전력(L4·L40S급 72 ~ 350W)이라 전력·냉각 벽이 낮다. 이 설명은 제품 구성에서 일반화한 것이라, 특정 서버의 실제 토폴로지는 `nvidia-smi topo -m`으로 확인하는 것이 안전하다.

<br>

# 8-GPU 표준과 그 너머

정리하면 전력·냉각(약 8kW 벽)과 레인 예산(128레인 벽)이 겹쳐 8-GPU 노드가 업계 표준이 됐다. 부품 규격도 이를 고정한다. NVIDIA HGX 베이스보드와 AMD·Intel이 쓰는 OCP OAM(UBB) 규격 모두 8-way로 정의되어 있어, 애초에 부품이 8장 단위로 나온다. 소프트웨어 관행도 여기에 맞춰져 있다 — 텐서 병렬은 보통 2/4/8로 나누는데, 어텐션 헤드 수와 hidden 차원이 2의 거듭제곱으로 깔끔하게 나뉘고 all-reduce 알고리즘 효율도 좋다는 것이 일반적으로 설명되는 근거다(노드 안 NVLink로 TP ≤ 8, 노드 간 InfiniBand로 PP·DP라는 계층 구조가 여기서 나온다).

다만 8이 절대적인 숫자는 아니다. NVIDIA는 2018년 DGX-2에서 NVSwitch 12개로 V100 16장을 한 노드(10U, 10kW)에 묶은 적이 있고, 최근 GB200 NVL72는 아예 랙 하나를 72-GPU 단일 NVLink 도메인으로 만들었다.

NVL72에서 중요한 변화는 노드의 세 정의가 처음으로 분리됐다는 점이다.

- 랙 구성: 1U 컴퓨트 트레이 18개(트레이당 Grace CPU 2 + Blackwell GPU 4) + NVSwitch 트레이 9개 → 랙 전체 36 CPU / 72 GPU
- **관리 단위(OS/K8s Node)는 여전히 컴퓨트 트레이**다. 랙 하나가 리눅스 한 대로 보이는 것이 아니다
- **스케일업 도메인(NVLink 범위)은 섀시 → 랙 전체**로 올라갔다. NVIDIA가 "acts as a single, massive GPU"라고 표현하는 부분이고, TP·EP를 72장 범위까지 NVLink로 걸 수 있게 됐다

이 경계 이동을 가능하게 한 것이 액랭이다. 공랭으로는 섀시가 감당할 열량이 10kW 근처에서 막히는데, 액랭 + 랙 내부 구리 배선(copper spine)으로 가면 랙 TDP 약 120 ~ 132kW를 넣고 랙 안에서 NVLink를 전기 신호로 전부 연결할 수 있다. 광트랜시버 없이 구리로 버틸 수 있는 거리 = 랙 하나라는 물리 제약이 새 경계선을 그은 셈이다. 실무에서 "이 모델 TP는 8까지인가"를 묻던 질문이 NVL72에서는 "TP를 72까지 걸 수 있는가"로 바뀐다 — 서빙 관점의 의미는 3주차 학습 내용 [5.5편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-05-LLM-Serving-Challenge-Accelerator-Trends %})에 정리되어 있다.

<br>

# 정리

- 경계 어휘: 인터커넥트 경계선은 chip이 아니라 **package**로 부른다. die↔HBM은 패키지 안(메모리로 센다), C2C부터가 밖이다
- 경계의 이동: Blackwell은 레티클 한계 때문에 die를 잘랐고, NV-HBI가 자기 HBM보다 빨라서 여전히 GPU 1장으로 보인다. 논리 경계(패키지)는 그대로, 용어 경계만 안으로 들어왔다
- 노드의 경계: 전력·냉각(약 10kW), PCIe 레인 예산(128 ~ 160), NUMA 균형, 8-way 보드 규격이 겹쳐 8-GPU 노드가 표준이 됐다
- 경계의 확장: NVL72는 액랭·구리 배선으로 스케일업 도메인을 랙까지 넓히며 관리 단위와 스케일업 단위를 분리했다

<br>

# 참고 링크

- [TSMC 3DFabric — CoWoS](https://3dfabric.tsmc.com/english/dedicatedFoundry/technology/cowos.htm)
- [NVIDIA GB200 NVL72](https://www.nvidia.com/en-us/data-center/gb200-nvl72/)
- [NVIDIA HGX Platform](https://www.nvidia.com/en-us/data-center/hgx/)
- [OCP OAM (OCP Accelerator Module) Specification](https://www.opencompute.org/projects/oai-open-accelerator-infrastructure)
- [LLM 서빙의 도전 과제 - 5.3. GPU 인터커넥트: 대역폭 계층과 GPU 선택]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-03-LLM-Serving-Challenge-GPU-Interconnect-Selection %})
- [SM 마이크로아키텍처: CUDA 코어·텐서 코어와 TFLOPS의 출처]({% post_url 2026-08-21-CS-GPU-SM-Microarchitecture %})

<br>
