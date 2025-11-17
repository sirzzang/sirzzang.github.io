---
title:  "[JavaScript] 원시값 vs. 레퍼런스"
excerpt: 내가 선언한 변수가 원시값과 레퍼런스 중 무엇을 가리키는지가 중요하다
categories:
  - Language
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - JavaScript
  - primitive
  - reference
---

<br>

 MobX 스토어에서 상태 관리를 하다, 다음과 같은 상황을 마주했다.

![variable-error]({{site.url}}/assets/images/variable-error-01.png){{: .align-center}}

<br>

 123번 라인에서 `payDoneLength`를 선언한 뒤, `if`문 조건에 걸려서 `payDone` 인스턴스에 새로운 object를 push하더라도 `payDoneLength`의 값이 1이 올라가지 않았다. `payDoneLength`가 생성된 `payDone` 인스턴스의 레퍼런스 값을 저장하지 않고, 선언된 당시 `payDone` 인스턴스의 길이를 나타내는 **숫자** 값을 저장하기 때문이다.

 JavaScript에서 선언한 변수가 레퍼런스 값을 저장하는 경우는 Array, Object, Class 등이고, 숫자의 경우 primitive한 값이다. 따라서 위와 같은 방식으로 코드를 작성하면 `payDoneLength`는 primitive한 값을 저장한다. 제대로 작동하게 하려면, 아래와 같이 바꿔야 한다.

```javascript
// 그 때 그 때 payDone의 길이를 불러야 한다
if (!this.payDone.length || this.payDone[this.payDone.length - 1].isDone) { 
    this.payDone.push({
        id: this.id,
        price: price,
        paid: price,
        isDone: false,
    });
}
```

<br>

 ~~굉장히 기본적인 것이지만,~~ 변수 선언 시 원시값을 저장하는지, 주소값을 저장하는지 잘 고려해야 한다. 팀 선배에게 물어 보니, 비슷한 실수를 자주 하는 경우가 반복문을 돌릴 때라고. 예컨대, 아래와 같이 배열에서 루프를 돌리고 싶으면, `array.length`를 사용해 돌리게 될 텐데, 이 때 `arrayLen` 등과 같은 변수에 `length`를 저장하고 `arrayLen`을 경계값으로 쓰는 게 권장되는 패턴이라고 한다.

```javascript
for (var i =0, arrayLen=array.length; i< arrayLen; i++) // 내부에서 arrayLen을 선언한 뒤 사용하는 게 좋다
```

<br>

 알고 보니, 파이썬도 똑같다!

```python
class test:    
    def __init__(self):
        self.my_arr = []        
    def test_function(self, num):
        test_length = len(self.my_arr) # 이건 그 당시 원시 number 저장하는 변수
        print(self.my_arr, test_length, len(self.my_arr))
        if not test_length:
            self.my_arr.append(num)
        print(self.my_arr, test_length, len(self.my_arr)) # len(self.my_arr)해야 그 때 그 때 레퍼런스에서 길이 불러옴

t = test()
t.test_function(3)

'''결과: 5번째 줄에서 선언한 test_length는 my_arr에 3이 append된 뒤에도 변하지 않는다
[] 0 0
[3] 0 1
'''
```

