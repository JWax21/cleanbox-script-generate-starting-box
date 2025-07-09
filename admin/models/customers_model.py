from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict
from uuid import uuid4


class Address(BaseModel):
    street: Optional[str]
    aptSuite: Optional[str]
    city: Optional[str]
    state: Optional[str]
    zip: Optional[str]


class PaymentMethod(BaseModel):
    brand: Optional[str]
    last4: Optional[str]
    funding: Optional[str]


class Snack(BaseModel):
    SnackID: str = Field(..., description="The ID of the snack")
    count: int = Field(..., ge=1, description="The count of the snack")
    primaryCategory: str = Field(..., description="The primary category of the snack")

class SnackItem(BaseModel):  # Distinct model for build_starting_box
    SnackID: str = Field(..., description="The ID of the snack")
    count: int = Field(..., ge=1, description="The count of the snack")
    primaryCategory: str = Field(..., description="The primary category of the snack")
    premium: bool = Field(..., description="Whether the snack is premium")

class BuildStartingBoxRequest(BaseModel):
    customerID: str
    new_signup: bool
    repeat_customer: bool
    off_cycle: bool
    is_reset_box: bool = False
    reset_total: int = 0
    repeat_monthly: List[SnackItem] = Field(default_factory=list)  # Default to []


class Customer(BaseModel):
    customerID: str = Field(default_factory=lambda: str(uuid4()), unique=True)
    firstName: Optional[str]
    lastName: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    textUpdates: bool = Field(default=False)
    stripeCustomerID: Optional[str]
    stripe_status: Optional[str]
    subscription_type: Optional[int]
    allergens: List[str] = Field(default_factory=list)
    category_dislikes: List[str] = Field(default_factory=list)
    shipping_address: Optional[Address]
    billing_address: Optional[Address]
    paymentMethod: Optional[PaymentMethod]
    staples: Dict[str, str] = Field(default_factory=dict)
    favoritedSnacks: List[str] = Field(default_factory=list)
    repeatMonthly: List[Snack] = Field(default_factory=list)