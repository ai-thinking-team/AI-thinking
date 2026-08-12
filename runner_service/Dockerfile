FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN addgroup -g 10001 runner && adduser -D -u 10001 -G runner runner
WORKDIR /runner
COPY harness.py /runner/harness.py
COPY worker.py /runner/worker.py
RUN chown root:runner /runner/harness.py /runner/worker.py \
    && chmod 0550 /runner/harness.py \
    && chmod 0555 /runner/worker.py

USER runner
ENTRYPOINT ["python", "/runner/harness.py"]
