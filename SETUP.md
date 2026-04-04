# Setup Guide - Backend

## Prerequisites

- Python 3.10+
- Git
- Supabase account with PostgreSQL database

## Installation

```bash
pip install -r requirements.txt
```

## Environment Configuration
```

See `.env.example` for all configuration variables and their descriptions.
```
## Database Setup

```bash
supabase db push 
```

## Start Server

Use the provided script:

```powershell
.\run-local.ps1
```

This will:
- Activate virtual environment
- Load local environment configuration
- Start FastAPI server with auto-reload

Server available at: `http://localhost:8000`

Swagger UI: `http://localhost:8000/docs`

