FROM python:3.12-slim
WORKDIR /app
COPY agent /app/agent
RUN useradd --system --uid 10001 agent
USER agent
EXPOSE 8080
CMD ["python", "-m", "agent.server"]
