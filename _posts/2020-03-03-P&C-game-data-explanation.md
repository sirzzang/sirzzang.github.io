---
title: "[DACON] 월간 데이콘 3 행동 데이터 분석 대회 - 데이터 설명"
excerpt: 게임 행동 데이터 분석 대회의 데이터 설명 자료입니다.
categories:
- P&C
tags:
- 공모전
- 데이터설명서
- 게임
- 행동
- 분석
last_modified_at: 2020-03-04
---





## 데이터 설명

대회에서 제공하는 데이터는 게임 플레이어의 행동 정보를 담고 있습니다. 

이 데이터를 사용하여 게임에서 승리하는 선수를 예측합니다. 

데이터는 5만여 개의 경기 리플레이 데이터로 이루어져 있으며, 각 리플레이 데이터는 총 경기 시간의 일부에 대한 인게임 정보를 포함합니다.



> 데이터 출처 : https://github.com/Blizzard/s2client-proto#downloads 데이터의 저작권은 BLIZZARD ENTERTAINMENT에 있습니다.



## train.csv



## test.csv



## sample_submission.csv

* gaim_id
* winner



### 데이터 컬럼

* game_id : 경기 구분 기호
* winner : player1의 승리 확률
* time : 경기 시간, ex) 2.24 = 2분 24초
* player : 선수 
  * 0: player 0
  * 1: player 1
* species : 종족
  * T : 테란
  * P : 프로토스
  * Z : 저그
* event : 행동 종류
  * Ability : 생산, 공격 등 선수의 주요 행동.
  * AddToControlGroup : 부대에 추가
  * Camera : 시점 선택
  * ControlGroup : 부대 행동
  * GetGontrolGroup : 부대 불러오기
  * Right Click : 마우스 우클릭
  * Selection : 객체 선택
  * SetControlGroup : 부대 지정
* event_contents : 행동 상세
