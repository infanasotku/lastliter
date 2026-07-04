# Context of build - project root

# --------------------------------------------
# Build
# --------------------------------------------
FROM python:3.12-slim AS builder
WORKDIR /build

# Updating pip and installing dependencies for build wheels
RUN pip install --no-cache-dir --upgrade pip setuptools wheel build


# Building service requirements to wheel
COPY requirements.txt .
RUN pip wheel --no-cache-dir -r requirements.txt -w /build/wheels


# --------------------------------------------
# Run
# --------------------------------------------
FROM python:3.12-slim AS final
WORKDIR /app
RUN pip install --no-cache-dir --upgrade pip

# Installing wheels from build stage
COPY --from=builder /build/wheels /tmp/wheels
RUN pip install --no-cache-dir /tmp/wheels/*.whl

COPY . .

CMD ["python", "--version"]
