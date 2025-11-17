---
title:  "[JavaScript] this 이해하기"
excerpt: 어쩌다 마주친 자바스크립트에서의 this
categories:
  - Language
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - JavaScript
  - undefined
  - this
  - React
---

<br>

 리액트로 개발을 하면서 이것저것 만져 보다가, 컴포넌트의 상태 세터 함수에 `this`를 붙여 보았다. ~~*애초에 지금 생각해 보면 왜 했는지 모르겠는데ㅎㅎ;;*~~

![js-this-error]({{site.url}}/assets/images/js-this-error-01.png){{: .align-center}}

<center><sup>`Discount`와 `Installment`는 비슷한 컴포넌트인데, 저렇게 코드를 바꿔 보았더니</sup></center>

![js-undefined-error]({{site.url}}/assets/images/js-this-error-02.png){{: .align-center}}

<center><sup>`Installment` 컴포넌트에서만 닫기 버튼을 클릭할 때 위와 같은 에러가 난다!</sup></center>

<br>

 

에러를 보니 `setOpen`이라는 property가 없다. `this`가 `undefined`인 것이다. 팀 선배의 도움을 받아 무엇이 잘못되었는지 알아 보았다.

<br>

 일단 `this`의 사용이 개념적으로 잘못되었다. 만약 `setOpen`이 `Installment` 컴포넌트에서 정의된 또 다른 메서드였다면, 다른 `handleClose` 메서드에서 `this.setOpen`으로 접근하는 것이 가능하다. 이 상황은 아니다.

<br>

 최대한 비슷한 상황을 찾아 본다면, 클래스형 컴포넌트를 사용하는 경우다. 리액트에서 클래스형 컴포넌트를 사용할 때는 `this.setState`를 통해 상태를 변경하는 것이 가능하다. 만약 `Installment` 컴포넌트가 `React.Component`를 상속받아 클래스형 컴포넌트로 설계되었다면, `this.setState`라는 함수는 `React.Component`에서 정의된 `setState`라는 메서드를 사용할 수 있었을 것이다. 

```javascript
class Test {
    abc
    fn() {
        // 여기서 abc에 접근하려면 this.abc
        // 여기서 setState를 사용하려고 해도, this.setState
    };
    setState() {
        // 만약 클래스형 컴포넌트를 사용했다면,
        // 클래스인 React.Component에서 선언된 메서드를 내가 만드는 컴포넌트에서 상속받아 사용해야 하므로,
        // this를 통해 접근하는 것.
    }
}
```

 그런데 그런 상황도 아니다! 현재 코드에서와 같이 함수형 컴포넌트와 훅 패턴을 함께 사용하는 경우라면, `useState` 함수를 import해서, 함수 내부에서 `open`, `setOpen`과 같은 변수와 함수를 그 때 그 때 만들어서 사용하는 것이다. 즉, `setOpen`은 `Installment`라는 함수에서 선언된 함수이므로, 그 함수에 `this`를 통해 접근하면 안 된다. (생각해 보니 `open`을 `this.open`으로 접근하지 않는 것과 똑같은 원리)

<br>

 마지막으로, `handleClose`가 화살표 함수이고, 상위 스코프에 정의된 일반 함수나 클래스가 없기 때문에 `this`가 `undefined`가 된다. 

 자바스크립트 화살표 함수 문법에서 `this`는, **정의된 위치가 어디인지**에 따라 결정된다.  `function() {}` 형태로 정의된 함수는 함수 자체에 `this`가 달려 있는데, 화살표형 함수 형태로 `() => {}`와 같이 정의된 함수는 함수 자체에 `this`가 달려 있지 않다. 따라서 아래와 같이 상위 스코프의 `this`를 찾아서 이용한다.

```javascript
function Test() {
    this.test = 10;
    this.fn = () => {
        console.log(this.test); // 상위 스코프의 this를 찾는다
    }
};

var ttt = new Test();
ttt; // Test {test: 10, fn: ƒ}
ttt.test; // 10
ttt.fn(); // 10
```

 문제가 되었던 코드에서는 전체가 화살표 함수이고, `this`를 통해 무언가를 사용하려면 상위에 `this`에 해당하는 무언가가 선언되어 있어야 한다. 그런데 현재 로직에서는 `handleClose` 상위의 `Installment`도 화살표 함수이기 때문에 `this` 객체 자체가 생성되지 않는다. 

 그리고 혹여나 `Installment`가 `function` 키워드를 통해 생성된 함수였다고 하더라도, `setOpen`이 `this`에 저장된 메서드가 아니기 때문에 오류가 발생했을 것이다. (이것은 상술한 단락에서와 같은 맥락이기도 하다. 애초에 `setOpen`은 변수에 선언한 메서드이기 때문에 상위 스코프가 있더라도 `this`를 통해 접근하는 것은 잘못된 것이다.)

<br>



 선배의 조언에 따르자면, 애초에 자바스크립트에서 `class`는 `function`의 prototype을 사용하기 편하게 만든 문법이니, `this`가 제대로 역할을 하려면 인스턴스가 있어야 하기도 하고, `function` 키워드를 통해 선언된 함수가 있어서 prototype 사용하듯 해야 한다는데.

 이거까지 한 번에 이해하기는 ~~객체 무식자에게~~ 조금 어려우니 나중에 차차 이해해 보도록 한다. 애초에 리액트에서 훅 패턴을 사용해서 개발할 때 function 내부에서 `this`를 사용할 일은 별로 없을 듯…하기도 하고… 개발 도중 코드 가지고 놀다가 붙여 본 `this`가 이런 파장을 불러올 줄 몰랐기도 하지만… 어쨌든.. 언제 어디서나 **생각을 하며** 코드를 짜도록 하자! ㅎㅎ;; 