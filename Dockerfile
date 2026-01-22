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

# Set production environment
ENV DJANGO_ENV=PROD

# Copy all source files
COPY . .

# Install Python dependencies from pyproject.toml
RUN pip install uv && uv pip compile pyproject.toml -o requirements.txt && uv pip install --system -r requirements.txt

# Install Node dependencies and build frontend
RUN npm ci && npm run build:prod

# Collect static files to staticfiles/ directory
RUN python manage.py collectstatic --noinput

EXPOSE 8000

# Default command (overridden per service)
CMD ["gunicorn", "app.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]