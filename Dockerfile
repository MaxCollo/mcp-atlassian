FROM ghcr.io/sooperset/mcp-atlassian:v0.21.1

EXPOSE 3000

CMD ["--transport", "streamable-http", "--port", "3000"]
