---
title:  "[Go] Query Parameter를 이용한 Query 수행 시 주의할 점"
excerpt: Go를 이용해 PostgreSQL jsonb 타입의 데이터를 조회할 경우, Query Parameter의 타입에 주의해야 한다.
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Go
  - PostgreSQL
  - Query Parameter
  - jsonb
---

 회사에서 Go와 PostgreSQL을 이용해 인증, 인가를 담당하는 Account 서버를 개발하던 중, `jsonb` 타입의 데이터를 조회하며 겪은 문제에 대해 기록하고자 한다.

<br>

# 상황

 Account 서버에서는 사용자 계정을 관리하기 위해 `users` 테이블을 사용한다. 해당 테이블에서 관리하는 데이터 중 하나는 사용자 별 로그인이 허용된 스케쥴로, 다음과 같은 형태의 json object 데이터를 `jsonb` 타입의 값으로 저장한다.

```json
{
	"Sun": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
	"Mon": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
	"Tue": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
	"Wed": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
	"Thu": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
	"Fri": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
	"Sat": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
}
```

- key: 각 요일별 abbreviation
- value: 시간대 별 user 로그인 허용 여부를 나타내는 길이 24의 배열
  - `0`: 로그인이 허용되어 있지 않음
  - `1`: 로그인이 허용되어 있음

```sql
SELECT * FROM users;
```

![users-table-select-result]({{site.url}}/assets/images/users-select-result.png)



<br>

 위와 같은 테이블에서 구현하고자 했던 기능은 현재 시각 기준 로그인이 허용되어 있지 않은 사용자를 차단하는 것이었다.  이를 위해서는 우선 `users` 테이블에서 현재 시각 기준 로그인이 허용되어 있지 않은 사용자를 조회해야 한다.

 이는 다음과 같은 과정으로 이루어진다.

- 조회하고자 하는 `요일`과 `시간대`를 설정한 후,
- `schedule` 컬럼에 저장된 json object에서 `요일`에 해당하는 배열을 찾아, `시간대` 인덱스에 있는 값을 가져 온다.

 예컨대, 현재 시각이 금요일 오전 9시 30분이고, 위 사진 기준 `testuser1`의 로그인이 허용되어 있는지 확인하기 위해서는 다음과 같은 쿼리를 사용하면 된다.

```sql
SELECT (schedule -> 'Fri' -> 9) AS login_allowed
FROM users
WHERE username='testuser1';
```

![users-login-allowed-result]({{site.url}}/assets/images/login-allowed-result.png)

쿼리를 위해 PostgreSQL에서 `jsonb` 타입의 값에 사용할 수 있는 연산자 중 하나인 `->`를 이용했다. 해당 연산자는 아래와 같이 동작한다.

- 피연산자의 타입이 `text`일 경우, 피연산자를 key로 보고, **값에서 key에 해당하는 json object 필드를 반환**한다. 
  - schedule 컬럼의 `jsonb` 값에서 `Fri`에 해당하는 key의 값을 가져온다. 따라서 길이가 24인 json array가 반환된다.
- 피연산자의 타입이 `integer`일 경우, 피연산자를 index로 보고, **값에서 index에 해당하는 json array 필드를 반환**한다.
  - 길이가 24인 json array에서 index `9`에 해당하는 값을 가져 온다. 따라서 `0`이 반환된다.

> jsonb 타입에 대해 사용할 수 있는 PostgreSQL 연산자 및 내장 함수는 https://www.postgresql.org/docs/9.5/functions-json.html를 참고하면 확인할 수 있다.

 다만, 위의 쿼리로 반환된 `0`이라는 값이 integer가 아님에 주의해야 한다(실제 첨부한 결과 사진에서도 쿼리 결과 값의 타입이 `integer`가 아니라 `jsonb`임을 확인할 수 있다). PostgreSQL에서 `jsonb` 타입은 INSERT 수행 당시의 text 값을 그대로 저장하기 때문에, 반환된 `jsonb` 타입을 활용하기 위해서는 형변환이 필요할 수 있다.

<br>

 위의 과정을 이용해 전체 테이블에서 현재 시각 기준 로그인이 허용되어 있지 않은 사용자를 조회하기 위해서는 아래와 같이 쿼리를 작성하면 된다.

```sql
SELECT id, username, schedule
FROM users
WHERE schedule -> 'Fri' -> 9 = '0'; -- text와 비교
```

```sql
SELECT id, username, schedule
FROM users
WHERE (schedule -> 'Fri' -> 9)::int = 0; -- schedule 값을 integer로 형변환한 후, 0과 비교
```

```sql
SELECT id, username, schedule
FROM users
WHERE (schedule -> 'Fri' -> 9)::int = false::int; -- 의미를 명확히 하기 위해, false를 0으로 형변환하여 비교
```

![users-select-result-2]({{site.url}}/assets/images/users-select-result-2.png)

상술한 이유에 따라, 아래와 같이 쿼리를 작성하면 `WHERE` 절에서 jsonb 타입과 integer 타입을 비교할 수 없기 때문에, 에러가 발생한다.

```sql
SELECT id, username, is_blocked, schedule
FROM users
WHERE schedule -> 'Fri' -> 9 = 0; -- jsonb 타입과 integer 타입의 비교
```

![jsonb-integer-comparison-error]({{site.url}}/assets/images/jsonb-integer-comparison-error.png)

<br>

 문제는 Go에서 PostgreSQL 데이터베이스를 연동해 동일한 과정을 진행했을 때 발생했다. Go에서 위의 쿼리를 실행하고 결과를 조회하기 위해, 아래와 같은 코드를 작성했다.

```go
// 현재 시각에 로그인이 허용되지 않은 user 조회
func (p *PostgresRepository) GetUsersByIsBlockedTrueOrCurrentScheduleFalse() ([]*iface.User, error) {
	ctx, cancel := context.WithTimeout(context.Background(), QUERY_TIMEOUT)
	defer cancel()

	query := `
	SELECT
		username,
		is_blocked
	FROM
		users
	WHERE
		(schedule -> $1 -> $2)::int = 0
	`
	logger.Info("query: %s", query)

	now := time.Now()
	rows, err := p.db.QueryContext(ctx, query, p.convertWeekdayToAbbreviation(now.Weekday()), now.Hour())
	if err != nil {
		logger.Error("failed to query: %v", err)
		return nil, err
	}

	var users []*iface.User = make([]*iface.User, 0)
	for rows.Next() {
		var user iface.User
		err = rows.Scan(
			&user.Username,
			&user.IsBlocked,
		)
		if err != nil {
			logger.Error("failed to scan user: %v", err)
			return nil, err
		}
		users = append(users, &user)
	}
	logger.Debug("found %d users whose current schedule is 0", len(users))

	return users, nil
}

// 요일별 abbreviation을 구하기 위한 util 함수
func (p *PostgresRepository) convertWeekdayToAbbreviation(weekday time.Weekday) string {
	switch weekday {
	case time.Sunday:
		return "Sun"
	case time.Monday:
		return "Mon"
	case time.Tuesday:
		return "Tue"
	case time.Wednesday:
		return "Wed"
	case time.Thursday:
		return "Thu"
	case time.Friday:
		return "Fri"
	case time.Saturday:
		return "Sat"
	default:
		return ""
	}
}
```

 PostgreSQL client를 이용해서 실행 후 작동함을 확인했던 위의 쿼리에서 현재 시각의 요일과 시간대만 Query Parameter로 넘기도록 했다. 그리고 아래와 같은 테스트 코드를 작성해 실행한 결과, 동일한 테이블에서 아무런 레코드도 조회되지 않았다.

```go
var dsn string = "your dsn"

func TestGetUsersByIsBlockedTrueOrCurrentScheduleFalse(t *testing.T) {
	r := require.New(t)
	p := pgrepo.New(dsn)
	users, err := p.GetUsersByIsBlockedTrueOrCurrentScheduleFalse()
	r.NoError(err)
	for _, user := range users {
		fmt.Printf("found user: %v\n", user.Username)
	}
}
```

![go-query-parameter-no-result]({{site.url}}/assets/images/go-query-parameter-no-result.png)

<br>

# 분석

PostgreSQL 데이터베이스에 연동 후 쿼리를 수행할 때, Query Parameter가 text로 처리되며 발생한 문제였다. 

 PostgreSQL 연동을 위해 사용한 [pq 패키지](go-query-parameter-no-result)의 [공식 문서 쿼리 부분](https://pkg.go.dev/github.com/lib/pq#hdr-Queries)을 참고하면, pq 라이브러리는 쿼리 매개변수 표현을 위해 PostgreSQL 기본 형식을 따른다는 것을 알 수 있다.

> database/sql does not dictate any specific format for parameter markers in query strings, and pq uses the Postgres-native ordinal markers, as shown above.

<br>

PostgreSQL에서는 쿼리 매개변수의 형식을 명시적으로 지정하지 않는 경우, 문자열 타입으로 처리한다. 따라서 문제가 되었던 위의 상황에서,

- `hour` 변수에 저장된 값이 문자열로 변환되어 처리되고,

  ```go
  rows, err := p.db.QueryContext(ctx, query, p.convertWeekdayToAbbreviation(now.Weekday()), now.Hour()) // now.Hour()가 integer로 처리되지 않는다
  ```

- `->` 연산자의 정의에 의해 피연산자가 `text` 타입으로 넘어 왔기 때문에,

  -  PostgreSQL은 `schedule` 컬럼에서 요일에 해당하는 json object를 찾은 후,
  - `hour` 변수에 저장된 값을 키로 갖는 json object를 찾으려 할 것이며,

- ~~당연히~~ 해당하는 값이 없어 아무런 레코드도 조회할 수 없는 것이다.

<br>

물론 쿼리 매개변수가 사용되는 연산자나 함수의 문맥에 따라, 문자열이 아니라 다른 타입으로 처리되어야 하는 경우에는 PostgreSQL에서 매개변수의 형변환을 진행해 주는 것 같다.

예컨대, 비슷한 경우인데 아래와 같은 코드를 실행하는 경우, 쿼리 매개 변수로 사용된 `5`는`text`가 아니라 `integer` 값으로 처리된다.

```go
query := `
SELECT
	user_refresh_token_id,
	last_authenticated_at
FROM
	user_session
WHERE
	NOW()- last_authenticated_at >= INTERVAL '1 second' * $1;
`
logger.Trace("query: %s", query)

rows, err := p.db.QueryContext(ctx, query, 5) // $1 자리에 전달되는 쿼리 매개변수 값 5
if err != nil {
	logger.Error("failed to get user sessions by inactive duration: %v", err)
	return nil, err
}
```

<br>

 조금 더 명확히 하기 위해, `users` 테이블에 아래와 같이 더미 데이터를 넣어 본 뒤, 동일한 코드로 테스트를 수행하면, 2개의 레코드를 조회해 오는 것을 확인할 수 있다.

```sql
INSERT INTO users (username, is_blocked, schedule)
VALUES
	('test2', false, '{"Fri":{"1":0,"2":0,"3":0,"4":0,"5":0,"6":0,"7":0,"8":0,"9":0}}'),
	('test3', false, '{"Fri":{"1":0,"2":0,"3":0,"4":0,"5":0,"6":0,"7":0,"8":0,"9":0}}')
ON CONFLICT (username)
	DO UPDATE SET schedule=EXCLUDED.schedule;
```

![dummy-schedule-test-data]({{site.url}}/assets/images/dummy-schedule-test-data.png)

![test-with-string-key]({{site.url}}/assets/images/test-with-string-key.png)



<br>



# 해결

위의 문제를 해결하는 것은 간단하다. 문제가 된 코드의 쿼리 부분에서 사용된 Query Parameter의 값을 아래와 같이 `integer` 타입으로 형변환하면 된다.

- Query Parameter를 형변환함으로써 `->`의 피연산자가 `integer` 타입으로 넘어 왔기 때문에,
-  PostgreSQL은 `schedule` 컬럼에서 요일에 해당하는 json object를 찾은 후,
- `hour` 인덱스에 해당하는 element를 찾는다.

```go
func (p *PostgresRepository) GetUsersByIsBlockedTrueOrCurrentScheduleFalse() ([]*iface.User, error) {
	ctx, cancel := context.WithTimeout(context.Background(), QUERY_TIMEOUT)
	defer cancel()

	// convert $2 to integer type
	query := `
	SELECT
		username,
		is_blocked
	FROM
		users
	WHERE
		(schedule -> $1 -> $2::int)::int = 0
	`
	logger.Info("query: %s", query)

	now := time.Now()
	rows, err := p.db.QueryContext(ctx, query, p.convertWeekdayToAbbreviation(now.Weekday()), now.Hour())
	if err != nil {
		logger.Error("failed to query: %v", err)
		return nil, err
	}

	var users []*iface.User = make([]*iface.User, 0)
	for rows.Next() {
		var user iface.User
		err = rows.Scan(
			&user.Username,
			&user.IsBlocked,
		)
		if err != nil {
			logger.Error("failed to scan user: %v", err)
			return nil, err
		}
		users = append(users, &user)
	}
	logger.Debug("found %d users whose current schedule is 0", len(users))

	return users, nil
}
```

![jsonb-integer-success]({{site.url}}/assets/images/jsonb-integer-success.png)

<br>
