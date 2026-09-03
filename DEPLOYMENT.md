# Enterprise Security Findings Connector - Deployment Guide

> Production-grade deployment architecture and operations guide
>
> Last updated: 2026-08-30

---

## Table of Contents

1. [Deployment Environments](#1-deployment-environments)
2. [Local Development Setup](#2-local-development-setup)
3. [Production Deployment (GCP)](#3-production-deployment-gcp)
4. [Infrastructure Configuration](#4-infrastructure-configuration)
5. [CI/CD Pipeline](#5-cicd-pipeline)
6. [Monitoring & Observability](#6-monitoring--observability)
7. [Security & Compliance](#7-security--compliance)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Deployment Environments

### Environment Matrix

| Environment | Purpose | Infrastructure | Database | Secrets |
|-------------|---------|----------------|----------|---------|
| **Local** | Development | Docker Compose | PostgreSQL container | .env file |
| **Staging** | Pre-production testing | Cloud Run | Cloud SQL (shared) | Secret Manager |
| **Production** | Live system | Cloud Run | Cloud SQL (dedicated) | Secret Manager |

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    LOCAL DEVELOPMENT                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Developer Machine                                                  │
│  ├─ Python 3.13 + venv                                              │
│  ├─ Docker Desktop                                                  │
│  └─ IDE (VS Code / PyCharm)                                         │
│                                                                      │
│  Docker Compose                                                     │
│  ├─ PostgreSQL 16 container                                         │
│  │  └─ Auto-seeded with schema + 12 findings                        │
│  └─ [Optional] Connector container                                  │
│                                                                      │
│  FastAPI Server                                                     │
│  ├─ uvicorn --reload (auto-reload on changes)                       │
│  ├─ http://localhost:8000                                           │
│  └─ MCP stdio transport                                             │
│                                                                      │
│  Configuration                                                      │
│  └─ .env file (not committed)                                       │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                    STAGING ENVIRONMENT                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Google Cloud Run (us-central1)                                     │
│  ├─ Service: enterprise-security-connector-staging                  │
│  ├─ Min instances: 0 (cost optimization)                            │
│  ├─ Max instances: 5                                                │
│  ├─ Memory: 512Mi                                                   │
│  └─ URL: https://connector-staging-*.run.app                        │
│                                                                      │
│  Cloud SQL (shared instance)                                        │
│  ├─ Instance: security-connector-db                                 │
│  ├─ Database: secops_db                                             │
│  ├─ Connection: Unix socket (/cloudsql/...)                         │
│  ├─ Tier: db-f1-micro                                               │
│  └─ Private IP only                                                 │
│                                                                      │
│  Secret Manager                                                     │
│  ├─ staging-jwt-secret                                              │
│  ├─ staging-db-password                                             │
│  └─ staging-user-role-map                                           │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                   PRODUCTION ENVIRONMENT                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Google Cloud Run (us-central1)                                     │
│  ├─ Service: enterprise-security-connector                          │
│  ├─ Min instances: 1 (warm start, reduced latency)                  │
│  ├─ Max instances: 20                                               │
│  ├─ Memory: 1Gi                                                     │
│  ├─ CPU: 1 vCPU                                                     │
│  └─ URL: https://connector-prod-*.run.app                           │
│                                                                      │
│  Cloud SQL (dedicated instance)                                     │
│  ├─ Instance: security-connector-db                                 │
│  ├─ Database: secops_db                                             │
│  ├─ User: connector (password from Secret Manager)                  │
│  ├─ Connection: Unix socket (/cloudsql/PROJECT:REGION:INSTANCE)     │
│  ├─ Tier: db-n1-standard-2 (2 vCPU, 7.5 GB RAM)                    │
│  ├─ High availability: Regional                                     │
│  ├─ Automatic backups: Daily at 03:00 UTC                           │
│  ├─ Point-in-time recovery: 7 days                                  │
│  └─ Private IP + Unix socket (no public access)                     │
│                                                                      │
│  Secret Manager                                                     │
│  ├─ connector-db-password (rotated quarterly)                       │
│  └─ connector-user-role-map (email:ROLE mappings)                   │
│      Example: admin@company.com:SECURITY_ADMIN,                     │
│               service-PROJECT_ID@gcp-sa-discovery...:SECURITY_ADMIN │
│                                                                      │
│  Cloud Monitoring                                                   │
│  ├─ Uptime checks (5 min intervals)                                 │
│  ├─ Error reporting                                                 │
│  ├─ Logging (7 day retention)                                       │
│  └─ Alerting policies                                               │
│                                                                      │
│  Load Balancer (optional)                                           │
│  ├─ Global HTTPS LB with Cloud CDN                                  │
│  └─ Custom domain: api.yourdomain.com                               │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Local Development Setup

### Prerequisites

```bash
# Required
✓ Python 3.13+
✓ Docker Desktop (or Docker Engine + Docker Compose)
✓ Git

# Recommended
✓ VS Code with Python extension
✓ PostgreSQL client (psql) for manual queries
```

### Step-by-Step Setup

#### 1. Clone Repository

```bash
git clone https://github.com/yourorg/enterprise-security-connector.git
cd enterprise-security-connector/Connectors/EnterpriseConnector
```

#### 2. Create Virtual Environment

```bash
# Create venv
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (macOS/Linux)
source venv/bin/activate
```

#### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### 4. Configure Environment

```bash
# Copy example config
cp .env.example .env

# Edit .env with your settings
# Minimum required:
#   DATABASE_URL=postgresql+asyncpg://connector:connector_pass@localhost:5432/security_connector
#   JWT_SECRET_KEY=<generate-a-strong-secret>
#   USER_ROLE_MAP=yourname@company.com:SECURITY_ADMIN
```

**Generate JWT Secret:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

#### 5. Start PostgreSQL

```bash
# Start database container
docker compose up -d postgres

# Verify it's running
docker compose ps

# Check logs
docker compose logs postgres

# Verify database connection
docker exec -it security_connector_db psql -U connector -d security_connector -c "SELECT COUNT(*) FROM findings;"
```

#### 6. Start Connector

```bash
# Start with auto-reload (development mode)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Verify health
curl http://localhost:8000/health
```

#### 7. Run Tests

```bash
# Full test suite
python -m pytest tests/ -v

# With coverage
python -m pytest tests/ --cov=app --cov-report=html

# Specific test file
python -m pytest tests/test_security.py -v
```

#### 8. Run Demo

```bash
# REST API demo only (no Gemini API key needed)
python demo.py --no-gemini

# Full demo with Gemini agent (requires GEMINI_API_KEY in .env)
python demo.py

# Interactive Gemini REPL
python gemini_agent.py
```

### Common Local Commands

```bash
# Reset database to seed state
docker exec security_connector_db psql -U connector -d security_connector \
  -f /dev/stdin < database/reset.sql

# Generate token for email user
python generate_token.py bob@company.com
python generate_token.py --list

# Stop containers
docker compose down

# Stop and remove volumes (full cleanup)
docker compose down -v

# View logs
docker compose logs -f postgres

# Database shell
docker exec -it security_connector_db psql -U connector -d security_connector
```

### Development Workflow

```
1. Start database:        docker compose up -d postgres
2. Start connector:       uvicorn app.main:app --reload
3. Make code changes:     (auto-reload triggers)
4. Run tests:             pytest tests/
5. Test manually:         python demo.py --no-gemini
6. Commit changes:        git commit -am "feat: add feature"
7. Stop services:         docker compose down
```

---

## 3. Production Deployment (GCP)

### Prerequisites

```bash
# Install Google Cloud SDK
# https://cloud.google.com/sdk/docs/install

# Verify installation
gcloud --version

# Login
gcloud auth login

# Set project
export PROJECT_ID=your-gcp-project-id
export REGION=us-central1
gcloud config set project $PROJECT_ID
gcloud config set compute/region $REGION
```

### Deployment Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      PRODUCTION STACK                             │
└──────────────────────────────────────────────────────────────────┘

   Gemini Enterprise
        │
        │ HTTPS (TLS 1.3)
        │ Bearer token per user
        ▼
   ┌─────────────────────┐
   │  Cloud Load Balancer │  (Optional: custom domain + CDN)
   │  • Global HTTPS      │
   │  • Cloud Armor WAF   │
   └──────────┬───────────┘
              │
              ▼
   ┌──────────────────────────────────────────┐
   │         Cloud Run Service                 │
   │  enterprise-security-connector            │
   ├──────────────────────────────────────────┤
   │  Container:                               │
   │  us-central1-docker.pkg.dev/              │
   │    project/connector/                     │
   │    enterprise-security-connector:v1.0.0   │
   │                                           │
   │  Scaling:                                 │
   │  • Min: 1 instance (warm)                 │
   │  • Max: 20 instances                      │
   │  • Concurrency: 80 requests/instance      │
   │  • CPU throttling: Enabled (after request)│
   │                                           │
   │  Resources:                               │
   │  • Memory: 1 GiB                          │
   │  • CPU: 1 vCPU                            │
   │  • Timeout: 300s                          │
   │                                           │
   │  Service Account:                         │
   │  connector-sa@project.iam.gserviceaccount│
   │  • roles/cloudsql.client                  │
   │  • roles/secretmanager.secretAccessor     │
   └──────────┬────────────────────────────────┘
              │
              │ Unix socket: /cloudsql/...
              │ IAM auth (no password)
              ▼
   ┌──────────────────────────────────────────┐
   │      Cloud SQL for PostgreSQL            │
   │      security-connector-db               │
   ├──────────────────────────────────────────┤
   │  Version: PostgreSQL 16                  │
   │  Tier: db-n1-standard-2                  │
   │  • 2 vCPU, 7.5 GB RAM                    │
   │  • 50 GB SSD storage                     │
   │  • Auto-increase enabled                 │
   │                                          │
   │  High Availability:                      │
   │  • Regional (multi-zone)                 │
   │  • Auto failover                         │
   │                                          │
   │  Backups:                                │
   │  • Automated daily at 03:00 UTC          │
   │  • 7 automated backups retained          │
   │  • Point-in-time recovery (7 days)       │
   │                                          │
   │  Network:                                │
   │  • Private IP only (no public IP)        │
   │  • VPC: default or custom                │
   └──────────────────────────────────────────┘

   ┌──────────────────────────────────────────┐
   │          Secret Manager                  │
   ├──────────────────────────────────────────┤
   │  prod-jwt-secret                         │
   │  prod-db-password                        │
   │  prod-user-role-map                      │
   │  prod-gemini-api-key (optional)          │
   └──────────────────────────────────────────┘

   ┌──────────────────────────────────────────┐
   │         Artifact Registry                │
   ├──────────────────────────────────────────┤
   │  Repository: connector                   │
   │  Images: versioned (v1.0.0, v1.1.0, ...) │
   │  Cleanup policy: Keep last 10 tags       │
   └──────────────────────────────────────────┘

   ┌──────────────────────────────────────────┐
   │       Cloud Monitoring Suite             │
   ├──────────────────────────────────────────┤
   │  • Cloud Logging (7 day retention)       │
   │  • Error Reporting                       │
   │  • Uptime Checks                         │
   │  • Custom Metrics                        │
   │  • Alerting (PagerDuty/Email)            │
   └──────────────────────────────────────────┘
```

### Step-by-Step Production Deployment

#### Phase 1: Enable APIs & Setup Project

```bash
# Enable required Google Cloud APIs
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  cloudresourcemanager.googleapis.com \
  compute.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com

# Set environment variables (save these for later)
export PROJECT_ID=$(gcloud config get-value project)
export REGION=us-central1
export SERVICE_NAME=enterprise-security-connector
export DB_INSTANCE=security-connector-db
export SA_NAME=connector-sa
export REPO_NAME=connector
```

#### Phase 2: Create Cloud SQL Database

```bash
# Create Cloud SQL instance (production tier)
gcloud sql instances create $DB_INSTANCE \
  --database-version=POSTGRES_16 \
  --tier=db-n1-standard-2 \
  --region=$REGION \
  --availability-type=REGIONAL \
  --network=default \
  --no-assign-ip \
  --storage-type=SSD \
  --storage-size=50GB \
  --storage-auto-increase \
  --backup-start-time=03:00 \
  --retained-backups-count=7 \
  --enable-point-in-time-recovery \
  --maintenance-window-day=SUN \
  --maintenance-window-hour=04

# Create database
gcloud sql databases create security_connector \
  --instance=$DB_INSTANCE

# Set strong password (generate securely)
DB_PASSWORD=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
echo "DB_PASSWORD: $DB_PASSWORD" # Save this!

# Create database user
gcloud sql users create connector \
  --instance=$DB_INSTANCE \
  --password=$DB_PASSWORD

# Get connection name for later
CONNECTION_NAME=$(gcloud sql instances describe $DB_INSTANCE \
  --format="value(connectionName)")
echo "CONNECTION_NAME: $CONNECTION_NAME"
```

#### Phase 3: Initialize Database Schema

```bash
# Option A: Via Cloud Shell (recommended for first-time setup)
gcloud sql connect $DB_INSTANCE --user=connector --database=security_connector

# Then paste contents of:
# 1. database/schema.sql
# 2. database/seed.sql

# Option B: Via local Cloud SQL Proxy
# Download proxy
wget https://dl.google.com/cloudsql/cloud_sql_proxy.linux.amd64 -O cloud_sql_proxy
chmod +x cloud_sql_proxy

# Start proxy
./cloud_sql_proxy $CONNECTION_NAME &

# Run schema
psql "host=127.0.0.1 port=5432 dbname=security_connector user=connector password=$DB_PASSWORD" \
  -f database/schema.sql \
  -f database/seed.sql
```

#### Phase 4: Configure Secrets

```bash
# Generate JWT secret
JWT_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
echo "JWT_SECRET: $JWT_SECRET" # Save this!

# Store secrets
echo -n "$JWT_SECRET" | gcloud secrets create prod-jwt-secret --data-file=-
echo -n "$DB_PASSWORD" | gcloud secrets create prod-db-password --data-file=-

# User role map (customize with your organization's emails)
USER_ROLE_MAP="admin@yourcompany.com:SECURITY_ADMIN,engineer@yourcompany.com:SECURITY_ENGINEER,viewer@yourcompany.com:VIEWER"
echo -n "$USER_ROLE_MAP" | gcloud secrets create prod-user-role-map --data-file=-

# Optional: Gemini API key for demo/testing
# echo -n "your-gemini-api-key" | gcloud secrets create prod-gemini-api-key --data-file=-

# Verify secrets created
gcloud secrets list
```

#### Phase 5: Create Service Account

```bash
# Create service account
gcloud iam service-accounts create $SA_NAME \
  --display-name="Enterprise Security Connector Service Account"

SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Grant Cloud SQL Client role
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/cloudsql.client"

# Grant Secret Manager Secret Accessor role
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/secretmanager.secretAccessor"

# Optional: Grant logging write permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/logging.logWriter"
```

#### Phase 6: Setup Artifact Registry

```bash
# Create Docker repository
gcloud artifacts repositories create $REPO_NAME \
  --repository-format=docker \
  --location=$REGION \
  --description="Enterprise Security Connector container images"

# Configure Docker authentication
gcloud auth configure-docker ${REGION}-docker.pkg.dev
```

#### Phase 7: Build & Push Container

```bash
# Navigate to repository root (secops-nexus/)
# Build Docker image
IMAGE_URL="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}"
VERSION="v1.0.0"

docker build \
  --platform linux/amd64 \
  -t ${IMAGE_URL}:${VERSION} \
  -t ${IMAGE_URL}:latest \
  .

# Push to Artifact Registry
docker push ${IMAGE_URL}:${VERSION}
docker push ${IMAGE_URL}:latest
```

#### Phase 8: Deploy to Cloud Run

> **EPAM Policy:** `--allow-unauthenticated` is prohibited by EPAM GCP Organization Policy.
> Always use `--no-allow-unauthenticated`.

```bash
# Deploy service
gcloud run deploy $SERVICE_NAME \
  --image=${IMAGE_URL}:${VERSION} \
  --region=$REGION \
  --platform=managed \
  --service-account=$SA_EMAIL \
  --add-cloudsql-instances=$CONNECTION_NAME \
  --set-secrets=JWT_SECRET_KEY=prod-jwt-secret:latest,DB_PASSWORD=prod-db-password:latest,USER_ROLE_MAP=prod-user-role-map:latest \
  --set-env-vars="APP_ENV=production,LOG_LEVEL=INFO,GCP_PROJECT_ID=$PROJECT_ID,CLOUD_SQL_CONNECTION_NAME=$CONNECTION_NAME,CORS_ALLOWED_ORIGINS=*" \
  --no-allow-unauthenticated \
  --port=8000 \
  --memory=1Gi \
  --cpu=1 \
  --timeout=300 \
  --min-instances=1 \
  --max-instances=20 \
  --concurrency=80 \
  --cpu-throttling \
  --no-use-http2

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
  --region=$REGION \
  --format="value(status.url)")
echo "Service deployed at: $SERVICE_URL"

# Grant Gemini Enterprise Layer 1 Discovery Engine invoker permission
# Required: without this, Gemini Enterprise cannot call the Cloud Run service
gcloud run services add-iam-policy-binding $SERVICE_NAME \
  --member="serviceAccount:service-71784361107@gcp-sa-discoveryengine.iam.gserviceaccount.com" \
  --role="roles/run.invoker" \
  --region=$REGION \
  --project=$PROJECT_ID
```

#### Phase 9: Verify Deployment

```bash
# Health check — requires OIDC identity token (no anonymous access)
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  ${SERVICE_URL}/health

# Generate connector JWT for your admin email
python generate_token.py admin@yourcompany.com

# Save connector token
TOKEN="<paste-token-here>"

# Test findings endpoint (uses connector JWT, not OIDC)
curl -H "Authorization: Bearer $TOKEN" \
  "${SERVICE_URL}/api/v1/findings?project_id=proj-payment-0000-0000-000000000001&severity=CRITICAL"

# Test MCP endpoint (OIDC token required for Cloud Run auth)
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  ${SERVICE_URL}/mcp

# View logs
gcloud run services logs read $SERVICE_NAME --region=$REGION --limit=50
```

#### Phase 10: Configure Gemini Enterprise

1. Navigate to **Google Cloud Console** → **Gemini for Google Workspace**
2. Go to **Custom MCP Servers**
3. Click **Add MCP Server**
4. Configure:
   - **Name:** Enterprise Security Findings Connector
   - **MCP Endpoint URL:** `${SERVICE_URL}/mcp`
   - **Transport:** Streamable HTTP
   - **Authentication:** Bearer token
5. Save configuration
6. Test in Gemini: *"Show me critical open findings for the Payment API"*

---

## 4. Infrastructure Configuration

### Cloud Run Configuration

**Service YAML (for declarative deployment):**

```yaml
# cloudrun-service.yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: enterprise-security-connector
  labels:
    app: security-connector
    environment: production
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/minScale: "1"
        autoscaling.knative.dev/maxScale: "20"
        run.googleapis.com/cloudsql-instances: "PROJECT_ID:REGION:security-connector-db"
        run.googleapis.com/cpu-throttling: "true"
    spec:
      serviceAccountName: connector-sa@PROJECT_ID.iam.gserviceaccount.com
      containerConcurrency: 80
      timeoutSeconds: 300
      containers:
      - image: REGION-docker.pkg.dev/PROJECT_ID/connector/enterprise-security-connector:v1.0.0
        ports:
        - containerPort: 8000
        resources:
          limits:
            cpu: "1000m"
            memory: "1Gi"
        env:
        - name: APP_ENV
          value: "production"
        - name: LOG_LEVEL
          value: "INFO"
        - name: CLOUD_SQL_CONNECTION_NAME
          value: "PROJECT_ID:REGION:security-connector-db"
        - name: JWT_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: prod-jwt-secret
              key: latest
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: prod-db-password
              key: latest
        - name: USER_ROLE_MAP
          valueFrom:
            secretKeyRef:
              name: prod-user-role-map
              key: latest
```

**Deploy from YAML:**
```bash
gcloud run services replace cloudrun-service.yaml --region=$REGION
```

### Terraform Configuration

**terraform/main.tf:**

```hcl
terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Cloud SQL Instance
resource "google_sql_database_instance" "main" {
  name             = "security-connector-db"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    tier              = "db-n1-standard-2"
    availability_type = "REGIONAL"
    disk_type         = "PD_SSD"
    disk_size         = 50
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 7
      }
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = "projects/${var.project_id}/global/networks/default"
    }

    maintenance_window {
      day          = 7  # Sunday
      hour         = 4
      update_track = "stable"
    }
  }

  deletion_protection = true
}

# Database
resource "google_sql_database" "main" {
  name     = "security_connector"
  instance = google_sql_database_instance.main.name
}

# Service Account
resource "google_service_account" "connector" {
  account_id   = "connector-sa"
  display_name = "Enterprise Security Connector"
}

# IAM Bindings
resource "google_project_iam_member" "cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.connector.email}"
}

resource "google_project_iam_member" "secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.connector.email}"
}

# Cloud Run Service
resource "google_cloud_run_v2_service" "main" {
  name     = "enterprise-security-connector"
  location = var.region

  template {
    service_account = google_service_account.connector.email

    scaling {
      min_instance_count = 1
      max_instance_count = 20
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/connector/enterprise-security-connector:latest"

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      ports {
        container_port = 8000
      }

      env {
        name  = "APP_ENV"
        value = "production"
      }

      env {
        name  = "CLOUD_SQL_CONNECTION_NAME"
        value = google_sql_database_instance.main.connection_name
      }

      env {
        name = "JWT_SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = "prod-jwt-secret"
            version = "latest"
          }
        }
      }

      env {
        name = "DB_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = "prod-db-password"
            version = "latest"
          }
        }
      }

      env {
        name = "USER_ROLE_MAP"
        value_source {
          secret_key_ref {
            secret  = "prod-user-role-map"
            version = "latest"
          }
        }
      }
    }

    vpc_access {
      connector = "projects/${var.project_id}/locations/${var.region}/connectors/default"
      egress    = "PRIVATE_RANGES_ONLY"
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
}

# IAM — grant Gemini Enterprise Layer 1 Discovery Engine invoker access
# allUsers is prohibited under EPAM GCP Organization Policy
resource "google_cloud_run_service_iam_member" "gemini_enterprise_invoker" {
  service  = google_cloud_run_v2_service.main.name
  location = google_cloud_run_v2_service.main.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:service-71784361107@gcp-sa-discoveryengine.iam.gserviceaccount.com"
}

output "service_url" {
  value = google_cloud_run_v2_service.main.uri
}
```

**Deploy with Terraform:**
```bash
cd terraform/
terraform init
terraform plan
terraform apply
```

### Database Migration Strategy

**Alembic Setup (for schema migrations):**

```bash
# Install Alembic
pip install alembic

# Initialize
alembic init alembic

# Edit alembic.ini - set sqlalchemy.url

# Create migration
alembic revision --autogenerate -m "Add new column"

# Apply migration
alembic upgrade head

# Rollback
alembic downgrade -1
```

---

## 5. CI/CD Pipeline

### GitHub Actions Workflow

**.github/workflows/deploy.yml:**

```yaml
name: Deploy to Cloud Run

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}
  REGION: us-central1
  SERVICE_NAME: enterprise-security-connector
  REGISTRY: us-central1-docker.pkg.dev

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: connector
          POSTGRES_PASSWORD: connector_pass
          POSTGRES_DB: security_connector
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.13'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    
    - name: Run tests
      env:
        DATABASE_URL: postgresql+asyncpg://connector:connector_pass@localhost:5432/security_connector
        JWT_SECRET_KEY: test-secret
      run: |
        pytest tests/ -v --cov=app --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3

  build-and-deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    
    permissions:
      contents: read
      id-token: write

    steps:
    - uses: actions/checkout@v4
    
    - name: Authenticate to Google Cloud
      uses: google-github-actions/auth@v2
      with:
        workload_identity_provider: ${{ secrets.WIF_PROVIDER }}
        service_account: ${{ secrets.WIF_SERVICE_ACCOUNT }}
    
    - name: Set up Cloud SDK
      uses: google-github-actions/setup-gcloud@v2
    
    - name: Configure Docker
      run: gcloud auth configure-docker ${{ env.REGISTRY }}
    
    - name: Build image
      run: |
        IMAGE_TAG=${{ env.REGISTRY }}/${{ env.PROJECT_ID }}/connector/${{ env.SERVICE_NAME }}:${{ github.sha }}
        docker build -t $IMAGE_TAG .
        docker tag $IMAGE_TAG ${{ env.REGISTRY }}/${{ env.PROJECT_ID }}/connector/${{ env.SERVICE_NAME }}:latest
    
    - name: Push image
      run: |
        docker push ${{ env.REGISTRY }}/${{ env.PROJECT_ID }}/connector/${{ env.SERVICE_NAME }}:${{ github.sha }}
        docker push ${{ env.REGISTRY }}/${{ env.PROJECT_ID }}/connector/${{ env.SERVICE_NAME }}:latest
    
    - name: Deploy to Cloud Run
      run: |
        gcloud run deploy ${{ env.SERVICE_NAME }} \
          --image=${{ env.REGISTRY }}/${{ env.PROJECT_ID }}/connector/${{ env.SERVICE_NAME }}:${{ github.sha }} \
          --region=${{ env.REGION }} \
          --platform=managed \
          --no-allow-unauthenticated
    
    - name: Verify deployment
      run: |
        SERVICE_URL=$(gcloud run services describe ${{ env.SERVICE_NAME }} --region=${{ env.REGION }} --format='value(status.url)')
        curl -f ${SERVICE_URL}/health || exit 1
```

### GitLab CI/CD

**.gitlab-ci.yml:**

```yaml
stages:
  - test
  - build
  - deploy

variables:
  DOCKER_DRIVER: overlay2
  REGION: us-central1

test:
  stage: test
  image: python:3.13
  services:
    - postgres:16-alpine
  variables:
    POSTGRES_DB: security_connector
    POSTGRES_USER: connector
    POSTGRES_PASSWORD: connector_pass
    DATABASE_URL: postgresql+asyncpg://connector:connector_pass@postgres:5432/security_connector
    JWT_SECRET_KEY: test-secret
  script:
    - pip install -r requirements.txt
    - pytest tests/ -v --cov=app
  coverage: '/TOTAL.*\s+(\d+%)$/'

build:
  stage: build
  image: google/cloud-sdk:alpine
  only:
    - main
  script:
    - echo $GCP_SERVICE_KEY | base64 -d > ${HOME}/gcp-key.json
    - gcloud auth activate-service-account --key-file ${HOME}/gcp-key.json
    - gcloud config set project $GCP_PROJECT_ID
    - gcloud auth configure-docker ${REGION}-docker.pkg.dev
    - docker build -t ${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/connector/enterprise-security-connector:${CI_COMMIT_SHA} .
    - docker push ${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/connector/enterprise-security-connector:${CI_COMMIT_SHA}

deploy:
  stage: deploy
  image: google/cloud-sdk:alpine
  only:
    - main
  script:
    - echo $GCP_SERVICE_KEY | base64 -d > ${HOME}/gcp-key.json
    - gcloud auth activate-service-account --key-file ${HOME}/gcp-key.json
    - gcloud config set project $GCP_PROJECT_ID
    - gcloud run deploy enterprise-security-connector
        --image=${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/connector/enterprise-security-connector:${CI_COMMIT_SHA}
        --region=${REGION}
        --platform=managed
```

---

## 6. Monitoring & Observability

### Cloud Monitoring Setup

**Uptime Check:**
```bash
# Create uptime check
gcloud monitoring uptime-checks create health-check \
  --display-name="Security Connector Health" \
  --resource-type=https \
  --host="${SERVICE_URL#https://}" \
  --path="/health" \
  --check-interval=5m \
  --timeout=10s
```

**Alerting Policies:**

```bash
# Error rate alert
gcloud alpha monitoring policies create \
  --notification-channels=<CHANNEL_ID> \
  --display-name="High Error Rate" \
  --condition-display-name="Error rate > 5%" \
  --condition-expression='
    resource.type = "cloud_run_revision"
    AND metric.type = "run.googleapis.com/request_count"
    AND metric.label.response_code_class = "5xx"'
```

### Logging Strategy

**Structured Logging (add to app/main.py):**

```python
import logging
import json
from google.cloud import logging as cloud_logging

def setup_cloud_logging():
    if settings.app_env == "production":
        client = cloud_logging.Client()
        client.setup_logging()
    
    # JSON formatter for Cloud Logging
    formatter = logging.Formatter(
        json.dumps({
            "time": "%(asctime)s",
            "level": "%(levelname)s",
            "logger": "%(name)s",
            "message": "%(message)s"
        })
    )
```

**Key Metrics to Monitor:**

| Metric | Alert Threshold | Action |
|--------|----------------|---------|
| Request latency (p95) | > 500ms | Investigate slow queries |
| Error rate | > 5% | Check logs, rollback if needed |
| CPU utilization | > 80% | Scale up instances |
| Memory usage | > 85% | Increase memory limit |
| Database connections | > 80 active | Tune connection pool |
| JWT validation errors | > 10/min | Check for attack patterns |

---

## 7. Security & Compliance

### Security Checklist

- [ ] JWT_SECRET_KEY rotated quarterly
- [ ] DB_PASSWORD rotated quarterly
- [ ] Cloud SQL automatic backups enabled
- [ ] Point-in-time recovery enabled
- [ ] Database on private IP (no public access)
- [ ] Service account with least privilege
- [ ] Secrets in Secret Manager (not env vars)
- [ ] HTTPS only (no HTTP)
- [ ] Cloud Armor WAF configured
- [ ] VPC Service Controls enabled
- [ ] Audit logs exported to Cloud Storage
- [ ] Regular security scans (Container Analysis)

### Secret Rotation

```bash
# Rotate JWT secret
NEW_JWT_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
echo -n "$NEW_JWT_SECRET" | gcloud secrets versions add prod-jwt-secret --data-file=-

# Update Cloud Run to use new version
gcloud run services update enterprise-security-connector \
  --region=$REGION \
  --update-secrets=JWT_SECRET_KEY=prod-jwt-secret:latest

# Rotate DB password
NEW_DB_PASSWORD=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
gcloud sql users set-password connector \
  --instance=security-connector-db \
  --password=$NEW_DB_PASSWORD

echo -n "$NEW_DB_PASSWORD" | gcloud secrets versions add prod-db-password --data-file=-

gcloud run services update enterprise-security-connector \
  --region=$REGION \
  --update-secrets=DB_PASSWORD=prod-db-password:latest
```

---

## 8. Troubleshooting

### Common Issues

#### Issue: Cloud Run service not connecting to Cloud SQL

```bash
# Check Cloud SQL connection name is correct
gcloud sql instances describe security-connector-db --format="value(connectionName)"

# Verify service account has cloudsql.client role
gcloud projects get-iam-policy $PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:connector-sa@*"

# Check Cloud Run logs
gcloud run services logs read enterprise-security-connector --region=$REGION --limit=100
```

#### Issue: 401 Unauthorized on API calls

```bash
# Verify token is valid
python -c "
import jwt
token = 'YOUR_TOKEN'
decoded = jwt.decode(token, options={'verify_signature': False})
print(decoded)
"

# Check USER_ROLE_MAP includes the email
gcloud secrets versions access latest --secret=prod-user-role-map

# Generate fresh token
python generate_token.py your@email.com
```

#### Issue: Database connection pool exhausted

```python
# Tune connection pool in app/database.py
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=20,        # Increase from default 5
    max_overflow=10,     # Increase from default 10
    pool_recycle=3600    # Recycle connections hourly
)
```

#### Issue: High latency (p95 > 500ms)

```bash
# Check slow queries
# Connect to Cloud SQL and run:
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

# Add indexes if needed
CREATE INDEX CONCURRENTLY idx_findings_created_at ON findings(created_at DESC);
```

### Health Check Script

```bash
#!/bin/bash
# health-check.sh

SERVICE_URL="https://your-service-url"
TOKEN="your-jwt-token"

# Health endpoint
echo "Checking /health..."
curl -sf $SERVICE_URL/health || { echo "Health check failed"; exit 1; }

# Auth check
echo "Checking auth..."
curl -sf -H "Authorization: Bearer $TOKEN" \
  "$SERVICE_URL/api/v1/findings?limit=1" > /dev/null || { echo "Auth check failed"; exit 1; }

echo "All checks passed!"
```

---

## Quick Reference Commands

```bash
# Local Development
docker compose up -d postgres              # Start DB
uvicorn app.main:app --reload              # Start connector
python demo.py --no-gemini                 # Run demo
pytest tests/ -v                           # Run tests

# Production Deployment
gcloud run deploy enterprise-security-connector --image=... --region=us-central1
gcloud run services logs read enterprise-security-connector --region=us-central1
gcloud sql instances describe security-connector-db

# Secrets Management
gcloud secrets versions add prod-jwt-secret --data-file=-
gcloud secrets versions access latest --secret=prod-user-role-map

# Monitoring
gcloud monitoring uptime-checks list
gcloud logging read "resource.type=cloud_run_revision" --limit=50

# Cleanup (Staging only!)
gcloud run services delete enterprise-security-connector-staging --region=us-central1
gcloud sql instances delete security-connector-db-staging
```

---

*Last updated: 2026-08-29 | Enterprise Security Findings Connector Deployment Guide*
