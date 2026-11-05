FROM python:3.12-slim
RUN useradd -m -u 1000 agent
COPY input_files/ /app/
RUN chown -R root:root /app && chmod -R a-w /app \
    && mkdir -p /app/output && chown agent:agent /app/output
WORKDIR /app
