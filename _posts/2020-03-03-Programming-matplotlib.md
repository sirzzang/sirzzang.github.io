---
title:  "[Python] Matplotlib 라이브러리 정리"
excerpt: "Matplotlib 라이브러리 주요 사용법을 정리합니다."
toc: true
toc_sticky: true
header:
  teaser: /assets/images/blog-Programming.jpg

categories:
  - Programming
tags:
  - Python
  - Matplotlib
  - visualization
last_modified_at: 2020-03-03
---







# _"Matplotlib 사용법 정리"_

> 강의에서 데이터를 차트나 플롯(plot)으로 그려주는 패키지인 Matplotlib에 대해 배웠습니다. 수업을 들을 때는 그 편의성이나 중요성에 대해 제대로 깨닫지 못했지만, 공모전을 진행하며 데이터를 시각화하는 것의 중요성에 대해 알게 됐습니다. 
>
> 이에 Matplotlib의 사용법에 대해 정리하면서 반복하여 공부하고자 합니다.



*이 글이 마지막으로 수정된 시각은 {{ page.last_modified_at }} 입니다.*



## rcParams

* 폰트 크기, 그래프 색깔 등 plot parameter를 조정할 수 있는 class([공식 문서](https://matplotlib.org/3.1.1/api/matplotlib_configuration_api.html#matplotlib.RcParams)).

* 다음의 두 가지 방식을 통해 사용할 수 있다.

  * .rcParams[] : 직접적으로 하나씩 지정해 커스텀.

  ```py
  mpl.rcParams['lines.linewidth'] = 2
  mpl.rcParams['lines.color'] = 'r'
  plt.plot(data)
  ```

  * .rc() : 여러 세팅을 한 번에 바꿀 수 있음.

  ```python
  mpl.rc('lines', linewidth=4, color='g')
  plt.plot(data)
  ```

* 다음과 같은 옵션을 지정할 수 있다.
  * axes.labelsize : x축, y축 이름 폰트 크기.
  * xtick.labelsize, ytick.labelsize : x축, y축 tick의 폰트 크기.
  * `plt.rcParams['axes.unicode_minus'] = False` : 한글 깨짐 현상 해결.



