---
title:  "[Python] raise vs. raise from e"
excerpt: 파이썬에서 예외가 어디서부터 발생했는지 알고 싶다면, raise from을 사용하자.
categories:
  - Language
toc: false
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Python
  - 예외
  - except
  - raise
---



  파이썬 `except` 블록에서 예외를 처리하는 도중에 또 다른 예외가 발생할 수 있다. 이 때 예외를 처리하는 도중 발생한 에러가 어떤 예외로부터 파생되었는지 알고 싶다면, `raise from`을 사용하면 된다. 

<br>

* `raise`만 사용한 경우

```python
import json

def load_json_key(data, key):
    try:
        result_dict = json.loads(data) # ValueError 발생할 수 있음.
    except ValueError as e:
        print('ValueError 처리')
        raise KeyError(key) 
    else:
        print('키 검색 중')
        return result_dict[key] # KeyError 발생 가능

load_json_key('{"foo": "bar"', 'foo')
```

  이 경우, 단순히 `ValueError`를 처리하는 도중 다른 에러가 발생했다는 것만을 알 수 있다. 

![jsondecodeerror]({{site.url}}/assets/images/error-02-jsondecode.png){: width="500"}{: .align-center}

<br>

* `raise from`을 사용한 경우

```python
import json

def load_json_key(data, key):
    try:
        result_dict = json.loads(data) # ValueError 발생할 수 있음.
    except ValueError as e:
        raise KeyError(key) from e
    else:
        return result_dict[key] # KeyError 발생 가능

load_json_key('{"foo": "bar"', 'foo')
```

 `KeyError`가 어떤 예외에서부터 파생되었는지 알 수 있다.

![raisefrom]({{site.url}}/assets/images/error-02-jsondecode-raisefrom.png){: width="500"}{: .align-center}

<br>

 `KeyError` 부분을 `OSError`로 바꿔도 실행이 되기는 한다. 그러나 실제 발생한 `OSError`가 없기 때문에 아래와 같이 에러의 내용이 나타나지 않는다.

![raisefrom-oserror]({{site.url}}/assets/images/error-02-jsondecode-oserror.png){: width="400"}{: .align-center}

<br>

 [StackOverflow](https://stackoverflow.com/questions/24752395/python-raise-from-usage){: .btn .btn--primary .btn--small} 에서 관련 내용을 찾을 수 있었다. `from` 절을 사용하면 발생한 예외의 `__cause__` 속성이 설정되어 에러 메시지 출력 시 *directly caused by* 를 통해 어떤 예외로부터 파생된 예외인지 알 수 있다는 것이다. 만약 `from` 절을 사용하지 않으면 `__cause__` 대신 `__context__` 속성이 설정된다. 그렇기 때문에 해당 예외가 어떤 *상황*에서 발생했는지를 알려주기 위해 에러 메시지 출력 시 *during handling ~ happened*와 같은 문구가 나오는 것이다.

 만약 이 모든 메시지를 보는 것이 번거롭다면, `raise … from None`을 사용하면 된다. 처음 발생한 예외만 에러 메시지로 출력된다. 

![raisefromnone]({{site.url}}/assets/images/error-02-jsondecode-raisefromnone.png){: width="400"}{: .align-center}