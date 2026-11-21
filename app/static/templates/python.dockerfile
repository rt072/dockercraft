# Python — unoptimized example (installing build deps in final image)
FROM python:3.11
WORKDIR /app
# Copy everything first (prevents leveraging cache effectively)
COPY . /app
# Install system-level build deps in the runtime image
RUN apt-get update && apt-get install -y build-essential git
# Install Python deps (no --no-cache-dir)
RUN pip install -r requirements.txt
RUN pip install gunicorn
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "app.py"]
