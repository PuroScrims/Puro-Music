FROM python:3.11-slim

# Install FFmpeg, Node.js, and Deno
RUN apt-get update && apt-get install -y \
    ffmpeg \
    nodejs \
    npm \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Deno (required for yt-dlp JavaScript challenges)
RUN curl -fsSL https://deno.land/install.sh | sh && \
    export DENO_INSTALL="/root/.deno" && \
    export PATH="$DENO_INSTALL/bin:$PATH" && \
    echo 'export DENO_INSTALL="/root/.deno"' >> /root/.bashrc && \
    echo 'export PATH="$DENO_INSTALL/bin:$PATH"' >> /root/.bashrc

# Set PATH so Deno is available
ENV DENO_INSTALL="/root/.deno"
ENV PATH="$DENO_INSTALL/bin:$PATH"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
