from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from Admin.routes import build_starting_box_routes

# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (use specific domains in production for security)
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# Include box-related routes
app.include_router(build_starting_box_routes.router, prefix="/api/v1")


# Root endpoint to redirect to Swagger UI
@app.get("/")
async def root():
    return RedirectResponse(url="/docs")


