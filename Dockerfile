# Base Image to use
FROM python:3.10-slim

RUN apt-get update --fix-missing && apt-get install -y --fix-missing build-essential

# Set the working directory
WORKDIR /app

# Copy all files into working directory
COPY . /app

# Install dependencies
RUN pip install -r requirements.txt

# Expose port 8080
EXPOSE 8080

# Set the environment variable
ENV FLASK_APP=src/main.py

# Run app.py when the container launches
CMD ["flask", "run", "--host=0.0.0.0", "--port=8080"]
