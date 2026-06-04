FROM python:3.11-slim

# Install Node.js
RUN apt-get update && \
    apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
RUN pip install --no-cache-dir fastmcp python-dotenv

# Copy mcp-abap-adt and install Node dependencies
COPY mcp-abap-adt/ ./mcp-abap-adt/
RUN cd mcp-abap-adt && npm install --production

# Copy gateway
COPY gateway.py .

# Expose port
EXPOSE 8080

# Run in HTTP mode
CMD ["python", "gateway.py", "--http", "--host", "0.0.0.0", "--port", "8080"]