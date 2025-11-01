from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api import location, auth, salons, bookings, realtime, admin, rm, vendors, payments, customers

# Create FastAPI app
app = FastAPI(
    title="Salon Management API - Complete Restructure",
    description="Multi-role salon management with RM scoring, dynamic fees, and Razorpay integration",
    version="3.0.0"
)


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(auth.router, prefix="/api")
app.include_router(location.router, prefix="/api")
app.include_router(salons.router, prefix="/api")
app.include_router(bookings.router, prefix="/api")
app.include_router(realtime.router, prefix="/api")

# New routers for restructured system
app.include_router(admin.router, prefix="/api")
app.include_router(rm.router, prefix="/api")
app.include_router(vendors.router, prefix="/api")
app.include_router(payments.router, prefix="/api")
app.include_router(customers.router)  # Customer portal endpoints



@app.get("/")
async def root():
    return {
        "message": "Salon Management API - Complete Restructure",
        "version": "3.0.0",
        "status": "running",
        "roles": ["admin", "relationship_manager", "vendor", "customer"],
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True if settings.ENVIRONMENT == "development" else False
    )
