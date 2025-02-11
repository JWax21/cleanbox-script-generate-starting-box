from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from admin.services.build_starting_box_service import build_starting_box  # Import the service
from admin.config.database import (
    monthly_draft_box_collection,
    all_customers_collection,
    all_snacks_collection,
)

router = APIRouter()

class BuildStartingBoxRequest(BaseModel):
    customerID: str
    new_signup: bool
    is_reset_box: bool = False
    reset_total: int = 0

@router.post("/build-starting-box")
async def build_starting_box_endpoint(
    request: BuildStartingBoxRequest  # Use the model to parse the body
):
    print(f"Request received for /build-starting-box with ID: {request.customerID} and new_signup: {request.new_signup}")
    try:
        result = await build_starting_box(
            customerID=request.customerID, 
            new_signup=request.new_signup,     
            is_reset_box=request.is_reset_box,  # Include optional field
            reset_total=request.reset_total,  # Include optional field
            monthly_draft_box_collection=monthly_draft_box_collection,
            all_customers_collection=all_customers_collection,
            all_snacks_collection=all_snacks_collection
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")