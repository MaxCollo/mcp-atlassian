FROM ghcr.io/sooperset/mcp-atlassian:latest

EXPOSE 3000

CMD ["--transport", "streamable-http", "--port", "3000"]
