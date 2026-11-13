# 컴포넌트 공용 이미지. kfp를 미리 설치해 두고 컴포넌트에서 install_kfp_package=False로 쓴다.
# TLS 재서명 프록시 뒤라면 그 CA를 빌드 시크릿으로만 넘긴다(이미지에는 남지 않는다).
#   docker build --secret id=ca,src=<CA 파일> -t mlpe-w4/py:1 .
FROM python:3.12-slim
RUN --mount=type=secret,id=ca,required=false \
    if [ -f /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi; \
    pip install --no-cache-dir "kfp==2.17.3" boto3
