# Use a modern, stable Python base image (Bookworm = Debian 12)
FROM python:3.11-slim-bookworm

WORKDIR /app

# Upgrade pip and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser and let IT handle the messy Linux dependencies safely
RUN playwright install chromium
RUN playwright install-deps

# Copy your actual project code into the container
COPY . .

# Expose the port Render uses
EXPOSE 8000

# Start the engine
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
