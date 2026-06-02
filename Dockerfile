FROM ghcr.io/sooperset/mcp-atlassian:0.21.1

# Add a tiny Python frontend (stdlib only — image already has Python) that
# responds 200 on `/` for Central Station's hardcoded K8s probe and proxies
# everything else to mcp-atlassian on PORT+1000.
USER root
COPY frontend.py /app/frontend.py
RUN chmod +x /app/frontend.py

EXPOSE 3000

# Override the base image's entrypoint so all incoming traffic hits frontend.py
# first. argv after the entrypoint passes through to mcp-atlassian.
ENTRYPOINT ["python3", "/app/frontend.py"]
CMD ["--transport", "streamable-http", "--port", "3000"]
