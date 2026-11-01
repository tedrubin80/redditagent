FROM python:3.12-slim
WORKDIR /app
COPY agent /app/agent
COPY config /app/config
RUN useradd --system --uid 10001 agent \
  && mkdir -p /app/data \
  && chown -R agent:agent /app/data
USER agent
ENV DATA_DIR=/app/data \
    SETTINGS_PATH=/app/data/settings.json \
    DB_PATH=/app/data/agent.db
EXPOSE 8080
CMD ["python", "-m", "agent.server"]
