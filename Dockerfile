FROM python:3.12-slim

# Install system dependencies for GeoDjango/PostGIS
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    postgresql-client \
    gcc \
    g++ \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install uv && uv pip install --system -e .

# Install Node dependencies and build frontend
COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build:prod

# Collect static files
RUN python manage.py collectstatic --noinput

EXPOSE 8000

# Default command (overridden per service)
CMD ["gunicorn", "app.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]