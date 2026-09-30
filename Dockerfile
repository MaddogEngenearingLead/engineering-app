dockerfile
# Use a lightweight, highly secure stable Python base layer
FROM python:3.10-slim

# Set strict production environmental variable baselines
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /workspace

# Install underlying operating system level security patches and compiler libraries
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Cache dependency parameters independently 
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Inject full modular project app layouts onto the runtime layer
COPY ./app ./app

# Expose backend network listener routing portals
EXPOSE 8000

# Fire up asynchronous multi-threaded production worker loops safely
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
