from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.build_starting_box_service import build_starting_box  # Import the service
from config.database import (
    monthly_draft_box_collection,
    all_customers_collection,
    all_snacks_collection,
)

router = APIRouter()

class BuildStartingBoxRequest(BaseModel):
    phone: str
    new_signup: bool

@router.post("/build-starting-box")
async def build_starting_box_endpoint(
    request: BuildStartingBoxRequest  # Use the model to parse the body
):
    print(f"Request received for /build-starting-box with phone: {request.phone} and new_signup: {request.new_signup}")
    try:
        result = await build_starting_box(
            phone=request.phone, 
            new_signup=request.new_signup,     
            monthly_draft_box_collection=monthly_draft_box_collection,
            all_customers_collection=all_customers_collection,
            all_snacks_collection=all_snacks_collection
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")