# Use the official Python image as a base
FROM python:alpine

# Set the working directory in the container
WORKDIR /app

# Copy requirements file and install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Add user so we don't need --no-sandbox.
RUN groupadd clowdertech && useradd -g clowdertech clowdertech \
    && mkdir -p /home/clowdertech/Downloads /app \
    && chown -R clowdertech:clowdertech /home/clowdertech \
    && chown -R clowdertech:clowdertech /app

# Run everything after as non-privileged user.
USER clowdertech

# Copy the entire application (including templates and other necessary files)
COPY . .

# Expose the port the app runs on
EXPOSE 8000

# Run the Flask application using Gunicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
