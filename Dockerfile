FROM python:3.11-slim

# Install system dependencies (FFmpeg for video, fonts for Pillow)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-liberation \
    fontconfig \
    wget \
    && rm -rf /var/lib/apt/lists/*

# (Optional) Download Segoe UI Emoji replacement or Noto Color Emoji if needed for Linux,
# but Pillow handles standard TTF emojis if provided in the assets folder.

WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files
COPY . .

# Ensure output directory exists and has permissions
RUN mkdir -p output && chmod 777 output

# Expose port (Render injects PORT env variable automatically)
EXPOSE 8000

# Start server
CMD ["python", "main.py"]
