from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from admin.routes.build_starting_box_routes import router as build_starting_box_router

# Initialize FastAPI app
app = FastAPI()

allowed_origins = [
    "https://88560556-a900-47e6-8007-e359b7ed3fd3-00-l5rqe8vdo9vu.picard.replit.dev",
    "https://15b32817-5faa-4f7d-b530-17ba4d07f43f-00-89dgnqdk4hau.spock.replit.dev",
    "https://www.cleanboxsnacks.com",
    "https://staging.cleanboxsnacks.com",
    "http://localhost:5173",
]

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# Include box-related routes
app.include_router(build_starting_box_router, prefix="/api/v1")


# Root endpoint to redirect to Swagger UI
@app.get("/")
async def root():
    return RedirectResponse(url="/docs")


