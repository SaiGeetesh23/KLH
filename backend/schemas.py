from pydantic import BaseModel
from typing import Optional, Any, Dict

class UserProfileUpdate(BaseModel):
    age: Optional[int] = None
    risk_tolerance: Optional[str] = None
    notification_preference: Optional[str] = None

class UserCreate(BaseModel):
    """Schema for creating a new user."""
    username: str
    email: str
    password: str

class UserProfileUpdate(BaseModel):
    """Schema for updating a user's financial profile."""
    # All fields are optional so the user can update one at a time.
    age: Optional[int] = None
    risk_tolerance: Optional[str] = None
    notification_preference: Optional[str] = None

class User(BaseModel):
    """Schema for returning user data to the client."""
    id: int
    username: str
    email: str
    thread_id: str
    
    # Include the profile fields, which can be None if not set
    age: Optional[int] = None
    risk_tolerance: Optional[str] = None
    notification_preference: Optional[str] = None

    class Config:
        # Pydantic v1: orm_mode = True
        # Pydantic v2: from_attributes = True
        from_attributes = True

# --- Token Schema ---

class Token(BaseModel):
    """Schema for the authentication token."""
    access_token: str
    token_type: str

# --- Chat Schemas ---

class ChatRequest(BaseModel):
    """Schema for an incoming chat message."""
    message: str

class InvestmentPlanSchema(BaseModel):
    """Nested schema for a structured investment plan."""
    equity_pct: float
    gold_pct: float
    debt_pct: float
    rationale: str
    market_context: Dict[str, Any] # To hold data from MarketAgent

class ChatResponse(BaseModel):
    """
    Schema for a structured chat response.
    This allows the frontend to handle different message types.
    """
    response_type: str  # e.g., "text", "investment_plan", "error"
    content: Any        # Can be a string, or a nested Pydantic model