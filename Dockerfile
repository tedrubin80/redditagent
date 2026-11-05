FROM python:3.12-slim
WORKDIR /app
COPY agent /app/agent
COPY config /app/config
COPY scripts/docker-entrypoint.sh /entrypoint.sh
RUN useradd --system --uid 10001 agent \
  && mkdir -p /app/data \
  && chown -R agent:agent /app/data \
  && chmod +x /entrypoint.sh
ENV DATA_DIR=/app/data \
    SETTINGS_PATH=/app/data/settings.json \
    DB_PATH=/app/data/agent.db \
    BIND_HOST=0.0.0.0 \
    PORT=8080
EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "agent.server"]
