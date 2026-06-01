---
title: "[GPU] GPU ECC: 메모리 오류를 검출하고 정정하는 원리"
excerpt: ECC가 무엇이고 GPU에서 어떻게 동작하는지, 왜 중요한지 짚어 보자.
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - GPU
  - ECC
  - NVIDIA
  - nvidia-smi
  - MLOps
  - SECDED
  - Blackwell
  - DCGM
---

<br>

# TL;DR

- ECC(Error-Correcting Code)는 특정 칩이나 장치의 기능이 아니라, **데이터에 수학적 여분(패리티)을 붙여 오류를 검출·정정하는 부호화 기법**이다. 메모리뿐 아니라 통신, 스토리지에서도 같은 원리로 쓰인다
- GPU에서 ECC는 **메모리(VRAM)의 비트 오류를 검출·정정하는 메모리 기능**이다. 성능 기능이 아니라 **데이터 무결성·관측가능성** 기능이다
- ECC에는 GDDR7에 내장된 **on-die ECC**와, NVIDIA가 데이터 경로 전체를 보호하고 카운터를 노출하는 **Full ECC** 두 가지가 있다. 운영자가 보고 제어할 수 있는 건 Full ECC뿐이다
- 핵심은 "오류를 안 내는 것"이 아니라 **"오류를 알 수 있는 것"**이다. ECC가 없으면 비트가 뒤집혀도 시스템은 아무 일 없다는 듯 틀린 결과를 내놓는다(silent corruption)

<br>

# ECC란 무엇인가

ECC(Error-Correcting Code)는 데이터에 여분의 정보(redundancy)를 덧붙여, 데이터가 깨졌는지 알아내고(검출) 운이 좋으면 되돌리는(정정) 기법이다. 즉 특정 칩이나 장치에 들어가는 부품이 아니라, **코딩 이론(coding theory)에서 나온 오류 검출·정정 부호(error-detecting/correcting codes)**의 한 갈래다.

그래서 ECC는 한 가지 모습으로만 나타나지 않는다. 'ECC 메모리(ECC RAM)'처럼 하드웨어로 구현되기도 하고, 파일 무결성 검사나 통신 오류정정처럼 소프트웨어로 구현되기도 한다. 어느 레이어에서 구현되느냐에 따라 모습이 달라질 뿐, 뿌리는 같다. 두 가지 축으로 나눠서 정리할 수 있다.

## 축 1: 하드웨어 vs 소프트웨어

먼저 ECC가 **어디서 동작하느냐**로 나눌 수 있다. 메모리 컨트롤러나 칩이 자동으로 처리하면 하드웨어 ECC, 코드나 펌웨어가 명시적으로 호출하면 소프트웨어 ECC다.

|  | 하드웨어 ECC | 소프트웨어 ECC |
| --- | --- | --- |
| 누가 | 메모리 컨트롤러·칩이 자동 | 코드·펌웨어가 명시적으로 |
| 시점 | 매 접근마다 실시간·투명 | 호출할 때(배치·전송 시) |
| 부호 | 주로 Hamming/SECDED (작은 워드) | Reed-Solomon·LDPC·Turbo 등 (큰 블록) |
| 예시 | GPU VRAM ECC, 서버 DDR ECC RAM, CPU 캐시 ECC, SSD 내부 ECC | 통신(5G·WiFi·위성), 스토리지(RAID·erasure coding), par2, QR코드 |

우리가 다룰 GPU ECC는 메모리 컨트롤러가 매 접근마다 처리하는 **하드웨어 ECC** 쪽이다.

## 축 2: 검출만 vs 검출 + 정정

다음은 ECC가 **무엇까지 해주느냐**다. 오류가 났다는 사실만 알려주는지(검출), 깨진 데이터를 되살리는지(정정)로 갈린다.

| 종류 | 할 수 있는 것 | 대표 예시 |
| --- | --- | --- |
| 검출만 | "깨졌다"는 것만 알려줌, 복구는 못 함 | 해시·체크섬 — MD5, SHA-256, CRC32 |
| 검출 + 정정 | 깨진 걸 되살림 | ECC 메모리, RAID 5/6 패리티, Reed-Solomon, par2, erasure coding |

이 둘은 필요한 여분 정보의 양이 다르다. **검출**은 "원본과 달라졌다"는 사실만 알면 되므로 적은 여분(체크섬 한 덩어리)으로 충분하다. 반면 **정정**은 어느 자리가 틀렸는지 특정하고 원래 값을 복원해야 하므로, 그만큼 더 많은 여분(패리티 비트)을 붙여야 한다. 그래서 같은 오류정정 부호 가족이라도 목적에 따라 검출까지만 하기도, 정정까지 하기도 한다.

검출 전용의 대표 사례는 해시·체크섬이다. 파일을 받고 `sha256sum`으로 원본과 비교하거나 git이 object를 SHA로 식별하는 건, "깨졌는지 여부"만 알면 되는 경우라 검출만 한다. 반면 메모리 ECC는 매 접근마다 자동으로 **검출 + 정정**까지 해야 하므로 패리티를 더 붙인다.

> 정정까지 하는 소프트웨어 사례도 있다. RAID 5/6(패리티 디스크로 디스크 손실 복원), Reed-Solomon(CD·QR코드·위성통신), par2(손상된 압축파일 복구), erasure coding(Ceph·S3 같은 분산 스토리지), ZFS·Btrfs의 self-healing은 메모리 ECC와 **진짜 동일한 원리**로 동작한다.

## 두 축을 겹쳐 보기

두 축을 겹치면 다음과 같이 정리된다.

```text
            검출만            검출 + 정정
HW    (패리티 체크)      GPU/DDR ECC, SSD ECC   ← 실시간·자동
SW    해시·체크섬         RAID·erasure·par2·RS   ← 명시적·배치
```

정리하면, ECC는 **"여분 정보로 비트 오류를 잡아내고(검출), 가능하면 되돌리는(정정) 부호화 기법"**이다. 메모리에서는 컨트롤러가 매 접근마다 실시간·자동으로, 통신·스토리지에서는 코드가 명시적으로 호출할 때 쓴다. 우리가 다룰 GPU ECC는 이 중 **하드웨어 + 검출·정정** 사분면에 있다.

<br>

# 비트는 어떻게, 왜 뒤집히는가

여기서부터는 우리 관심사인 **하드웨어 메모리 ECC**로 좁혀서 보자. 앞에서 ECC가 여분 정보로 오류를 검출·정정하는 부호화 기법이라는 걸 봤는데, 그렇다면 메모리에서는 애초에 무슨 오류가 생기길래 ECC가 필요한 걸까? 메모리 ECC가 무엇을 막는지 이해하려면, 먼저 메모리에서 비트가 왜 뒤집히는지부터 알아야 한다.

메모리 ECC가 막으려는 대상은 **비트 플립(bit flip)**이다. GDDR7 같은 VRAM은 셀에 저장된 비트가 우주선(cosmic ray)·전기 노이즈·고온·고밀도·노후화 등으로 가끔 뒤집힌다. 한 비트가 0에서 1로(혹은 그 반대로) 바뀌는 것이다.

> 참고: 우주선(cosmic ray)과 비트 플립의 관계
>
> 우주선이 여기서 왜 나오나 궁금해서 찾아만 봤다. 비트 플립과 연결되는 흐름은 대략 이렇다고 한다.
>
> - 우주에서 날아온 고에너지 입자(1차 우주선)가 대기권 상층의 공기 분자와 충돌 → 2차 입자 샤워, 특히 중성자(neutron)가 쏟아짐
> - 이 중성자가 지상까지 내려와 메모리 셀의 실리콘을 때림 → 순간적으로 전하(electron-hole pair)를 생성
> - 그 전하가 셀에 저장된 값을 바꿀 만큼이면 → 0이 1로(혹은 반대로) 뒤집힘. 칩이 물리적으로 망가진 게 아니라 저장된 값만 틀어지는 거라, 이런 일시적 오류를 soft error라고 부른다
>
> 그래서 같은 칩이라도 고도가 높을수록(대기가 얇아 중성자를 덜 막음) soft error 발생률이 올라간다. 항공기나 고지대 데이터센터에서 더 민감한 이유이고, ECC가 잡으려는 대표적 원인 중 하나다. 물리까지 깊게 이해하진 못했지만, 이 글에서는 "외부 방사선이 셀 값을 가끔 흔든다" 정도로 받아들이고 넘어간다. 더 파고 싶으면 soft error, SEU(Single Event Upset) 키워드로 찾아보면 된다고 한다.

<br>

ECC는 데이터에 여분의 패리티 비트를 붙여 이걸 잡아낸다. 메모리에서 주로 쓰는 방식이 **SECDED(Single Error Correction, Double Error Detection)**다. 이름 그대로 두 가지 일을 한다.

- **단일 비트 오류**: 자동 정정한다(Single Error Correction). 어느 비트가 틀렸는지까지 패리티로 역산해 복구한다
- **이중 비트 오류**: 정정은 못 하지만 검출·로깅한다(Double Error Detection). "오염됐다"는 것을 알려준다

그런데 패리티 비트가 어떻게 "어느 비트가 틀렸는지"까지 알아낼까? 패리티(parity) 하나의 동작부터 보면 감이 온다.

- **패리티 1개**: 데이터 비트들의 1의 개수가 짝수냐 홀수냐만 본다. 비트 하나가 뒤집히면 홀짝이 깨지니 "틀렸다"는 건 안다. 하지만 어느 비트인지는 모른다 → **검출만** 가능
- **패리티 여러 개**: 패리티마다 데이터의 서로 다른 부분집합을 감시하게 배치한다(Hamming 부호). 비트 하나가 뒤집히면, 그 비트를 감시하던 패리티들만 깨진다. **깨진 패리티들의 조합을 읽으면 그게 곧 틀린 비트의 위치**를 가리킨다. 위치를 알면 그 비트만 뒤집어 복구 → **정정(SEC)**
- **전체를 덮는 패리티 1개 추가**: 여기에 데이터 전체를 한 번 더 덮는 패리티를 얹으면, 단일 오류와 이중 오류를 구분할 수 있다. 이중 오류는 위치 조합이 엉뚱한 곳을 가리키는데 전체 패리티는 (짝수 번 뒤집혀) 멀쩡해 보인다 → "뭔가 났는데 못 고친다"를 알아챔 → **검출(DED)**

정리하면, **패리티를 하나만 쓰면 검출, 여러 개를 겹쳐 위치를 특정하면 정정, 거기에 하나를 더 얹어 이중 오류까지 구분하는 게 SECDED**다.

> 참고: 메모리에서 흔히 쓰는 SECDED 구성은 `(72,64)`다. 64비트 데이터에 8비트 패리티를 붙여 72비트로 만든 형태로, 서버 DDR ECC RAM이 64비트 데이터 버스에 칩 하나(8비트)를 더 얹는 구조와 맞아떨어진다. 패리티 비트 수가 데이터 폭에 비해 작은(64→8) 것도 메모리 ECC가 가벼운 이유 중 하나다.

SECDED가 왜 메모리에 딱 맞는 방식인지는, 앞에서 본 하드웨어 vs 소프트웨어 구분으로 다시 돌아가 보면 분명해진다. 둘을 가르는 핵심은 **"워드(word) 단위"**다. 메모리 ECC는 작은 워드 단위에 Hamming/SECDED 부호를 붙여 매 접근마다 실시간으로 검사한다. 매 읽기·쓰기마다 돌아야 하니 부호가 가볍고 빨라야 하고, 그래서 워드 단위의 SECDED가 적합하다. 반면 통신·스토리지의 소프트웨어 ECC는 큰 블록 단위에 Reed-Solomon·LDPC 같은 부호를 써서, 더 많은 오류를 견디는 대신 명시적으로 호출할 때만 동작한다.

|  | 소프트웨어 무결성 | 메모리 ECC |
| --- | --- | --- |
| 위치 | 파일·스토리지 레이어 | 하드웨어(메모리 컨트롤러) |
| 시점 | 내가 명령 돌릴 때(수동·배치) | 매 메모리 접근마다 실시간·자동 |
| 투명성 | 코드·도구로 명시적 수행 | 앱은 모르게 투명하게 처리 |
| 부호 | 보통 큰 블록 대상(SHA, RS) | 워드 단위 Hamming/SECDED |

> 운영 관점에서 실제로 다루는 건 패리티 계산이 아니라 카운터다. 신드롬 역산과 정정은 하드웨어가 자동·투명하게 다 해주고, 우리가 보는 건 `nvidia-smi`의 `Correctable`(SEC가 조용히 고친 횟수)과 `Uncorrectable`(DED가 잡았지만 못 고친 것) 숫자뿐이다. 그래서 "단일은 고치고 이중은 잡아만 낸다"는 동작 모델까지만 알면 충분하다. 

<br>

# GPU 관점의 ECC

GPU에서 ECC는 결국 **메모리 무결성** 문제다. 연산 유닛 자체가 아니라, VRAM에 올라간 가중치·활성값·중간 텐서가 읽고 쓰이는 동안 비트가 보존되는지를 보장하는 것이 핵심이다. GPU의 ECC는 이 VRAM과 그 데이터 경로(data path)에서 발생한 비트 오류를 검출·정정하고, 그 결과를 카운터로 노출한다. 연산 처리량을 높이는 성능 기능이 아니라 **데이터 무결성·관측가능성** 기능이며, "빠르게"보다 "틀리지 않게, 틀렸을 때 알 수 있게"에 무게가 실린다.

그런데 NVIDIA GPU에서 ECC는 **보호하는 구간과 노출 여부가 다른 두 층위**로 나뉜다. 둘 다 ECC지만 같은 것이 아니다. 이 구분을 모르면 "GDDR7가 박힌 RTX 5090에도 ECC가 있어야 하는 것 아닌가"에서 막힌다.

## on-die ECC vs Full ECC

| 종류 | 무엇 | 특징 |
| --- | --- | --- |
| on-die ECC | GDDR6/GDDR7 메모리 표준에 내장 | 항상 켜져 있고 끌 수 없음, 사용자에게 안 보임. **DRAM 칩 내부**의 비트 오류만 잡고, GPU ↔ 메모리 데이터 경로는 보호 안 함 |
| Full ECC | NVIDIA가 말하는 ECC | 메모리 인터페이스 + 데이터 경로 전체를 보호. **오류 카운터·Xid 로깅·row remapping·토글**을 노출 |

두 층위의 차이는 **보호 구간**과 **노출 여부**로 갈린다.

on-die ECC는 공정이 미세화되면서 DRAM 셀이 작아져 늘어난 셀 내부 오류에 대응하려고 GDDR6 세대부터 메모리 표준에 들어갔다. DRAM 다이 안에서 정정을 끝내고 깨끗한 데이터를 내보내기 때문에, 호스트는 그 존재조차 모르고 켜고 끌 수도 없다. 결정적으로, DRAM 칩과 GPU 다이를 잇는 **메모리 버스(데이터 경로)는 보호하지 않는다**. 셀에서 나온 뒤 경로에서 비트가 틀어지면 잡지 못한다.

Full ECC는 이 메모리 인터페이스와 GPU 내부 SRAM(L2·SM 캐시)까지 포함한 **데이터 경로 전체**를 ECC로 감싸고, correctable/uncorrectable 카운터·Xid 로깅·row remapping·토글을 운영자에게 노출한다. 

"오류를 정정한다"는 메커니즘 자체는 on-die든 Full이든 같지만, **노출·로깅·제어가 되는 건 Full ECC뿐**이다. 그래서 Full ECC는 데이터센터(A100·H100 등)와 프로·워크스테이션(RTX PRO, RTX A-series, Quadro) 등급에만 들어가고, RTX 5090 같은 소비자 카드는 GDDR7 on-die ECC에 "맡기는" 수준에 그친다. `nvidia-smi`에 카운터가 뜨지 않고 제어도 안 되는 이유다.


<details markdown="1">
<summary><b>참고: on-die ECC와 Full ECC는 각각 누가 만드나</b></summary>

<br>

두 ECC는 구현 주체부터 다르다.

| | 만드는 주체 | 구현 위치 | 노출·제어 |
| --- | --- | --- | --- |
| on-die ECC | 메모리 제조사(삼성·SK하이닉스·마이크론 등) | DRAM 다이 내부 | 불가 (JEDEC 표준·자동) |
| Full ECC | NVIDIA | GPU 메모리 컨트롤러 + 데이터 경로 | 가능 (제품 등급 게이팅) |

- **on-die ECC**는 GDDR6/GDDR7(및 DDR5)의 JEDEC 표준에 포함된 기능이라, DRAM 칩을 만드는 제조사가 다이 안에 직접 구워 넣는다. 공정 미세화로 셀 자체 오류율이 올라가니, 칩 밖으로 데이터를 내보내기 전에 내부에서 알아서 정정하려는 것이다.
- **Full ECC**는 NVIDIA가 GPU 다이의 메모리 컨트롤러 레벨에서 구현한다. 같은 메모리 칩을 써도 NVIDIA가 이 기능을 제품 등급별로 켜주느냐가 갈린다.

한 가지 더, Full ECC도 여분의 패리티 비트를 **어딘가 저장**해야 하는데 여기서 메모리와 다시 엮인다.

- **sideband 방식(구세대)**: 일반 DRAM 용량 일부를 떼어 패리티로 씀 → ECC 켜면 가용 VRAM이 ~6% 줄었다
- **inline 방식(Blackwell)**: 더 효율적으로 처리해 표시 용량 손실이 거의 없다 → PRO 6000이 96GB를 거의 그대로 잡는 이유

</details>

Full ECC가 있을 때와 없을 때(on-die만)의 차이는 다음과 같다.

| 구분 | Full ECC 있음 (RTX PRO 6000) | Full ECC 없음 (RTX 5090 등 소비자) |
| --- | --- | --- |
| 단일 비트 오류 | 조용히 자동 정정 | 그대로 연산에 반영됨 |
| 이중 비트 오류 | 검출 + Xid 에러·카운터 기록 | 탐지 불가 — 모르고 지나감 |
| 실패 양상 | 눈에 보이는 에러·로그로 드러남 | silent corruption (티 안 나게 결과가 틀어짐) |
| 메모리 노화 관리 | row remapping·오류 카운터로 추적 가능 | 불가 |
| 비용 | VRAM 용량 일부 + 약간의 성능 오버헤드 | 오버헤드 없음, 전량·전대역 사용 |

핵심은 마지막 줄이 아니라 그 위에 있다. **있고 없고의 차이는 "오류가 안 난다"가 아니라 "오류를 알 수 있다"**다. ECC가 없으면 비트가 뒤집혀도 시스템은 아무 일 없다는 듯 계속 돌아간다.

## SRAM vs DRAM: 카운터가 둘로 나뉘는 이유

앞에서 Full ECC가 "VRAM뿐 아니라 GPU 내부 SRAM(L2·SM 캐시)까지" 보호한다고 했다. 이게 실제 출력에서 어떻게 드러나냐면, 뒤에서 `nvidia-smi -q -d ECC`를 돌리면 오류 카운터가 `SRAM Correctable`, `DRAM Correctable`처럼 **두 갈래로 나뉘어** 나온다. 이 출력을 제대로 읽으려면, 먼저 SRAM과 DRAM이 GPU 안에서 위치와 성격이 완전히 다른 메모리라는 걸 알아야 한다.


|  | SRAM (Static RAM) | DRAM (Dynamic RAM) |
| --- | --- | --- |
| 1비트 저장 | 트랜지스터 6개(플립플롭) | 트랜지스터 1개 + 커패시터 1개 |
| Refresh | 불필요 (전원만 있으면 유지) | 주기적 refresh 필요 (전하가 샘 → "dynamic") |
| 속도 | 매우 빠름 | 상대적으로 느림 |
| 집적도·용량 | 낮음 → 소용량 | 높음 → 대용량 |
| GPU에서 위치 | 온칩 캐시 — L1/L2, 레지스터 파일, SM shared memory | VRAM 본체 — GDDR7, HBM |

위 표를 다 이해하지 않아도 된다. 핵심만 짚으면 **SRAM은 빠르지만 작고 비싼 메모리(온칩 캐시), DRAM은 느리지만 크고 싼 메모리(VRAM 본체)**라는 것이다.

> SRAM은 책상 위(즉시 손 닿지만 좁음), DRAM은 책장(넓지만 가지러 걸어가야 함)에 비유할 수 있다. GPU는 자주 쓰는 걸 SRAM 캐시에 두고, 대용량은 DRAM에 둔다.

그래서 Full ECC가 도는 카드의 ECC 출력은 둘로 나뉜다. `DRAM ...`은 VRAM(GDDR7) 셀의 비트 오류, `SRAM ...`은 GPU 내부 캐시(L2·SM 등)의 비트 오류다. Blackwell의 Full ECC는 이 **둘 다** 보호하고 카운트한다.

그럼 on-die ECC만 있는 소비자 카드는 왜 DRAM까지 `N/A`로 뜰까? 여기서 헷갈리기 쉽다. RTX 5090에도 GDDR7 on-die ECC는 분명히 있다. 다만 **on-die ECC는 DRAM 다이 안에서 조용히 정정만 하고 그 결과를 호스트로 보고하지 않는다.** 카운터를 밖으로 노출하는 건 Full ECC의 몫이기 때문이다. 그래서 `nvidia-smi`에는 SRAM이든 DRAM이든 전부 `N/A`로 뜬다 — 여기서 `N/A`는 "ECC가 없다"가 아니라 **"(DRAM은) 있어도 들여다볼 수 없고, SRAM은 애초에 보호 대상이 아니다"**라는 뜻이다.

<br>

# 왜 중요한가

운영하면서 가장 무서운 건 crash가 아니라 **silent corruption**이다. crash는 최소한 멈추기라도 하지만, silent corruption은 티 안 나게 결과만 틀어진다.

게다가 GPU 연산은 대부분 부동소수점(FP32·BF16·FP16)이라, **한 비트가 어디서 뒤집히느냐에 따라 충격이 다르다**. 지수부(exponent) 비트가 뒤집히면 값의 크기가 통째로 달라져 쉽게 `Inf`/`NaN`으로 번지지만, 가수부(mantissa) 비트가 뒤집히면 값이 미세하게만 어긋난다. 역설적으로 후자가 더 위험하다 — 터지지 않고 "조금 틀린 값"으로 계속 흘러가기 때문이다. ECC가 중요한 맥락은 여기에 있다.

- **장시간 학습**: 며칠짜리 학습 중 gradient나 weight의 한 비트가 뒤집히면, 운 나쁘면 `NaN`으로 터지고 더 흔하게는 그냥 살짝 틀린 채로 수렴한다. 재현도 안 되고 원인 추적도 불가능하다. 여기서 ECC의 correctable(SEC)은 단일 비트 오류를 조용히 정정해 학습을 깨끗하게 이어가게 하고, uncorrectable(DED)은 정정은 못 해도 Xid로 터뜨려 **"오염된 채 수렴"하는 최악**을 막아준다
- **추론**: 입력이나 weight의 한 비트가 뒤집혀 결과가 미묘하게 달라져도 모르고 배포될 수 있다. 배치로 수만 건을 돌리는 서빙에서는 이 미세한 오염이 어디서 났는지 사후 추적이 사실상 불가능하다. 안전·정합성이 중요한 도메인일수록 ECC의 "검출 가능성"이 큰 의미를 가진다
- **운영 모니터링**: correctable 카운터가 **늘어나는 추세**면 아직 정정되곤 있어도 메모리 노화 신호이고, uncorrectable이 한 번이라도 뜨면 즉시 조치 대상이다. row remapping까지 진행되는 카드는 RMA(보증 기간 내 불량 하드웨어를 제조사에 반품·교체 신청하는 절차)·교체 판단 근거가 된다

> 참고: **row remapping(행 재배치)**
>
> 디스크 불량 섹터 처리와 같은 발상이다. VRAM의 특정 행(row)에서 오류가 반복되면 GPU가 그 행을 미리 떼어둔 예비 행(spare)으로 갈아끼운다. 즉 row remapping이 일어났다는 건 **물리 메모리가 실제로 손상되기 시작했다**는 신호다(예비 행은 유한해서 다 쓰면 끝).

특히 마지막 항목은 다른 지표와 함께 보면 더 강력하다. 장기 고부하로 운용하면 600W 부하에서 최대 클럭이 서서히 떨어지는 사례가 보고된다. RTX PRO 6000은 부하 시 보통 2GHz 후반대로 도는데, 심하면 500MHz대까지 떨어진다 — **정상의 1/4~1/5 수준**이라 그 카드 처리량이 통째로 추락한다. 더 큰 문제는 분산 학습이다. 동기식 학습은 매 스텝마다 모든 GPU가 gradient를 맞춰야(NCCL all-reduce) 다음으로 넘어가므로, 느려진 한 장이 전체 속도를 결정하는 **straggler**가 되어 멀쩡한 나머지 카드까지 그 속도에 묶인다. 게다가 이 저하는 식으면 회복되는 일시적 throttling이 아니라 수개월 고부하 끝의 영구적 degradation이라, ECC correctable 추세와 함께 보면 어느 카드가 노화로 가고 있는지 조기에 잡을 수 있다.

<br>

# 운영: 확인과 토글

ECC 관련 명령은 **Full ECC를 지원하는 카드에서만** 동작한다.

상태 확인은 `nvidia-smi -q -d ECC`로 한다.

```shell
# volatile/aggregate correctable·uncorrectable 카운트와 row mapping 상태 확인
~$ nvidia-smi -q -d ECC
```

출력에서 봐야 할 핵심 필드는 이렇다.

- **ECC Mode — Current / Pending**: 지금 적용된 상태와, 리셋 후 적용될 예약 상태다. 토글 직후엔 `Current: Disabled / Pending: Enabled`처럼 둘이 갈리고, 리셋을 거쳐야 Pending이 Current로 반영된다
- **Volatile / Aggregate**: Volatile은 마지막 리셋 이후, Aggregate는 카드 수명 전체 누적이다. 모니터링은 주로 **Aggregate가 늘어나는지**를 본다
- **SRAM / DRAM Correctable·Uncorrectable**: 앞서 본 대로 온칩 캐시(SRAM)와 VRAM(DRAM)을 따로 카운트한다

토글은 `-e` 플래그로 한다.

```shell
~$ sudo nvidia-smi -e 1   # ECC 켜기 (전체 GPU)
~$ sudo nvidia-smi -i 0 -e 0   # 0번 GPU만 끄기
```

토글에는 몇 가지 전제가 있다. 우선 해당 GPU에 **실행 중인 프로세스가 없어야** 하고(작업이 물려 있으면 거부된다), 변경은 곧바로 적용되지 않고 **GPU 리셋 후**에 반영된다. 리셋은 `nvidia-smi --gpu-reset`이나 노드 재부팅으로 한다. 그래서 운영 중인 학습 노드에서는 보통 정비 창(maintenance window)을 잡고 일괄로 켠다.

지원하지 않는 카드는 어떻게 될까? `nvidia-smi -q -d ECC`를 실행하면 **`N/A`** 또는 ECC 섹션 자체가 비어서 카운트가 안 나온다. `-e 1`을 시도하면 지원 안 함 에러로 거부된다.

트레이드오프를 정리하면 이렇다.

- **ECC on**: 약간의 용량·성능 ↓, 대신 신뢰성·디버깅성 ↑
- **ECC off**: 전량·전대역, 대신 silent corruption 위험

다만 이 비용은 구현 방식에 따라 다르다. sideband ECC를 쓰던 구세대는 가용 VRAM이 ~6% 줄고 대역폭도 손해를 봤지만, Blackwell의 inline ECC는 표시 용량 손실이 사실상 없다(그래서 PRO 6000이 96GB를 거의 그대로 잡는다). 그래도 정정·검사 로직이 도는 만큼 미세한 성능 오버헤드는 남아, 최대 처리량을 노리는 일부 추론에서는 일부러 끄기도 한다. 다중일·분산 학습이 주 용도라면 **on을 권장**한다.

<br>

# 실제로 확인해 보기

두 노드를 비교해 보자. 한쪽은 Full ECC를 지원하는 RTX PRO 6000 Blackwell Server Edition(`gpu-node-a`), 다른 쪽은 지원하지 않는 RTX 5090(`gpu-node-b`)이다.

## 지원하는 노드: RTX PRO 6000

`nvidia-smi` 요약에서 `Volatile Uncorr. ECC` 열이 `0`으로 잡힌다.

```shell
my-user@gpu-node-a:~$ nvidia-smi
# 실행 결과 (4장 중 1장 발췌)
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
|=========================================+========================+======================|
|   0  NVIDIA RTX PRO 6000 Blac...    On  |   00000000:54:00.0 Off |                    0 |
| N/A   28C    P8             34W /  600W |       0MiB /  97887MiB |      0%      Default |
|                                         |                        |             Disabled |
+-----------------------------------------+------------------------+----------------------+
```

`-q -d ECC`로 상세를 보면 `ECC Mode: Enabled`이고, SRAM/DRAM 카운터가 모두 `0`으로 잡힌다.

```shell
my-user@gpu-node-a:~$ nvidia-smi -q -d ECC
# 실행 결과 (GPU 1장 발췌)
ECC Mode
    Current                  : Enabled
    Pending                  : Enabled
ECC Errors
    Volatile
        SRAM Correctable     : 0
        DRAM Correctable     : 0
        DRAM Uncorrectable   : 0
    Aggregate
        SRAM Correctable     : 0
        DRAM Correctable     : 0
        DRAM Uncorrectable   : 0
    Channel Repair Pending   : No
    Unrepairable Memory      : No
```

<details markdown="1">
<summary><b>전체 출력 (4장)</b></summary>

```text
==============NVSMI LOG==============

Timestamp                                              : Mon Jun  1 11:21:43 2026
Driver Version                                         : 595.58.03
CUDA Version                                           : 13.2

Attached GPUs                                          : 4
GPU 00000000:54:00.0
    ECC Mode
        Current                                        : Enabled
        Pending                                        : Enabled
    ECC Errors
        Volatile
            SRAM Correctable                           : 0
            SRAM Uncorrectable Parity                  : 0
            SRAM Uncorrectable SEC-DED                 : 0
            DRAM Correctable                           : 0
            DRAM Uncorrectable                         : 0
        Aggregate
            SRAM Correctable                           : 0
            SRAM Uncorrectable Parity                  : 0
            SRAM Uncorrectable SEC-DED                 : 0
            DRAM Correctable                           : 0
            DRAM Uncorrectable                         : 0
            SRAM Threshold Exceeded                    : No
        Aggregate Uncorrectable SRAM Sources
            SRAM L2                                    : 0
            SRAM SM                                    : 0
            SRAM Microcontroller                       : 0
            SRAM PCIE                                  : 0
            SRAM Other                                 : 0
        Channel Repair Pending                         : No
        TPC Repair Pending                             : No
        Unrepairable Memory                            : No

(GPU 00000000:55:00.0 / D3:00.0 / D4:00.0 동일 — 모두 0)
```

</details>

> 이 노드의 드라이버(595.58 계열)에는 GSP 펌웨어 핸드셰이크 버그가 보고됐다. idle이라 멀쩡해 보여도 고부하·리셋 시 재현될 수 있으니 드라이버 업그레이드 후보로 봐 두는 게 좋다.

## 지원하지 않는 노드: RTX 5090

같은 명령을 5090 노드에서 돌리면 `Volatile Uncorr. ECC` 열이 `N/A`다.

```shell
my-user@gpu-node-b:~$ nvidia-smi
# 실행 결과 (8장 중 1장 발췌)
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
|=========================================+========================+======================|
|   0  NVIDIA GeForce RTX 5090        Off |   00000000:17:00.0 Off |                  N/A |
|  0%   29C    P8             23W /  575W |       0MiB /  32607MiB |      0%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+
```

`-q -d ECC`도 전부 `N/A`로 뜬다. ECC Mode부터 SRAM·DRAM 카운터까지 모두 측정 불가다.

```shell
my-user@gpu-node-b:~$ nvidia-smi -q -d ECC
# 실행 결과 (GPU 1장 발췌)
ECC Mode
    Current                  : N/A
    Pending                  : N/A
ECC Errors
    Volatile
        SRAM Correctable     : N/A
        DRAM Correctable     : N/A
        DRAM Uncorrectable   : N/A
    Aggregate
        SRAM Correctable     : N/A
        DRAM Correctable     : N/A
        DRAM Uncorrectable   : N/A
```

## 두 출력을 나란히 놓고 읽기

| 필드 | RTX 5090 (`gpu-node-b`) | RTX PRO 6000 (`gpu-node-a`) | 해석 |
| --- | --- | --- | --- |
| Volatile Uncorr. ECC | `N/A` | `0` | **0과 N/A는 천지차이**. 0 = "감시 중인데 오류 없음", N/A = "감시 자체를 못 함" |
| ECC Mode Current | `N/A` | `Enabled` | PRO 6000은 Full ECC 활성 |
| MIG M. | `N/A` | `Disabled` | 5090은 MIG 아예 불가, PRO 6000은 켤 수 있는데 꺼둔 상태 |
| Persistence-M | `Off` | `On` | PRO 6000만 persistence daemon 켜짐 |
| 메모리 | 32,607 MiB | 97,887 MiB | 32GB vs 96GB |

읽을 포인트가 몇 개 있다.

- **0 vs N/A가 핵심이다.** PRO 6000의 `0`은 "Full ECC가 돌고 있고 이번 부팅 이후 정정 불가 오류가 0건"이라는 건강 신호다. 5090의 `N/A`는 "오류가 없다"가 아니라 **"있어도 모른다"**, 정확히 silent corruption 구간이다
- **Volatile = 마지막 리셋 이후, Aggregate = 카드 수명 전체 누적.** 둘 다 0이면 이력상 메모리 오류가 한 번도 없는 깨끗한 카드다. 모니터링은 이 Aggregate 숫자가 시간이 지나며 늘어나는지를 보는 것이다
- **SRAM과 DRAM을 따로 카운트한다.** Blackwell Full ECC는 VRAM(DRAM)뿐 아니라 온칩 SRAM(L2·SM 캐시)까지 보호하고, 오류가 나면 어느 블록에서 났는지까지 분해해 준다. on-die ECC엔 없는 관측가능성이다
- **MIG `Disabled` vs `N/A`도 의미가 다르다.** PRO 6000의 `Disabled`는 "기능은 있고 지금은 꺼둠"이고, 5090의 `N/A`는 하드웨어 자체가 미지원이다
- **96GB가 거의 그대로 보인다.** 구세대 카드는 Full ECC(사이드밴드 방식)를 켜면 가용 용량이 ~6% 줄었는데, 여기선 97,887MiB로 거의 96GB 풀로 잡힌다. Blackwell PRO 6000은 **inline ECC** 방식이라 ECC on에도 표시 용량 손실이 사실상 없다

<br>

# 모니터링 자동화

`nvidia-smi -q -d ECC`를 수동으로 보는 대신, **DCGM + dcgm-exporter → Prometheus/Grafana**로 ECC correctable·uncorrectable, 클럭, 온도를 시계열로 쌓는 게 실속 있는 액션이다. 앞서 말한 클럭 degradation과 ECC 카운터를 같이 보면 메모리·실리콘 노화를 조기에 잡고 RMA를 판단할 수 있다.

그런데 ECC를 모니터링한다면 카운터 숫자만 봐선 부족하다. **uncorrectable ECC 오류는 발생하는 순간 Xid 에러로 커널 로그에 찍히기 때문이다.** Xid는 NVIDIA 드라이버가 GPU 이상을 알리는 에러 코드인데, ECC와 직접 엮이는 코드가 있다 — 대표적으로 Xid 48(이중 비트 오류, DBE), Xid 63·64(row remapping 이벤트), Xid 92(높은 단일 비트 오류율)다. 즉 `nvidia-smi`의 카운터가 "누적 몇 건"이라는 정적 스냅샷이라면, Xid는 "방금 어느 GPU에서 정정 불가 오류가 터졌다"는 실시간 신호에 가깝다.

문제는 이 Xid가 `nvidia-smi`에는 잘 안 뜨고 **커널 로그에 남는다**는 점이다. 그래서 `dmesg`나 `journalctl -k`에서 `NVRM: Xid`를 잡아 알림을 거는 게 ECC 모니터링의 짝이 된다.

```shell
# 커널 로그에서 Xid 에러 추출 (ECC 관련 Xid 48/63/64/92 등이 여기 찍힌다)
~$ journalctl -k | grep -i "NVRM: Xid"
```

ECC 디테일을 더 보고 싶으면 옵션을 추가한다.

```shell
# row remapping·페이지 격리 상태까지
~$ nvidia-smi -q -d ECC,ROW_REMAPPER,PAGE_RETIREMENT
# 부하 줄 때 클럭 throttling 추적
~$ nvidia-smi -q -d PERFORMANCE,CLOCK,TEMPERATURE
```

<br>

# 정리

| 항목 | 내용 |
| --- | --- |
| ECC의 본질 | 코딩 이론 기법. 여분 정보로 검출(+정정) |
| 메모리 ECC 방식 | 워드 단위 SECDED — 단일 정정, 이중 검출 |
| on-die ECC | GDDR7 내장. 항상 on, 제어·관측 불가, DRAM 칩 내부만 |
| Full ECC | 데이터 경로 전체 보호 + 카운터·Xid·row remapping·토글 노출. 프로·데이터센터 등급만 |
| 운영 명령 | `nvidia-smi -q -d ECC`(확인), `-e 1`·`-e 0`(토글) |
| 핵심 가치 | "오류를 안 낸다"가 아니라 "오류를 알 수 있다" |

마지막으로 자주 헷갈리는 점 하나. **MIG와 ECC는 직접적인 관계가 없다.** MIG는 GPU의 연산 유닛·캐시·메모리를 하드웨어 수준에서 물리적으로 분할하는 아키텍처 기능이고, 가능한 이유는 ECC 때문이 아니라 칩 설계 자체가 파티셔닝을 지원하기 때문이다. ECC 있는 카드가 MIG도 되는 것처럼 보이는 건, NVIDIA가 제품 세그먼트를 나눌 때 ECC·MIG·vGPU 같은 데이터센터용 기능을 **묶어서** 프로·데이터센터 등급에만 넣기 때문이다. MIG를 포함해 Time Slicing·MPS·vGPU 등 GPU를 여러 워크로드가 나눠 쓰는 공유 메커니즘은 [GPU 공유 메커니즘: 개요]({% post_url 2025-11-22-Dev-GPU-Sharing-Mechanisms %})에서 다뤘으니 참고하자.

<br>

# 참고 링크

- [NVIDIA GPU Memory Error Management](https://docs.nvidia.com/deploy/gpu-memory-error-management/index.html)
- [NVIDIA Data Center GPU Manager (DCGM)](https://developer.nvidia.com/dcgm)
{% raw %}
- [GPU 공유 메커니즘: 개요]({% post_url 2025-11-22-Dev-GPU-Sharing-Mechanisms %})
- [GPU 팬텀 사용률]({% post_url 2026-05-11-Dev-GPU-Phantom-Utilization %})
- [분산 학습 네트워크 장애]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-03-02-Distributed-Learning-Network-Failure %})
- [NCCL Communicator Lazy Init 디버깅]({% post_url 2026-04-18-Dev-NCCL-Communicator-Lazy-Init-Debugging %})
{% endraw %}

<br>
