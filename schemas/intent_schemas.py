from pydantic import BaseModel, Field
from typing import List, Optional

class GroceryItem(BaseModel):
    """Represents a single grocery item to be added to the database."""
    item_name: str = Field(description="The normalized name of the grocery item (e.g., 'Milk', 'Eggs')")
    quantity: str = Field(description="The quantity or amount requested (e.g., '1 gallon', '2 dozen', 'Some')")
    category: str = Field(description="The supermarket aisle or category (e.g., 'Dairy', 'Produce', 'Meat')")
    urgency: str = Field(description="Priority of the item: 'High', 'Medium', or 'Low'")

class RecipeIngredients(BaseModel):
    """Represents ingredients extracted from a recipe URL."""
    recipe_name: str = Field(description="The title of the recipe")
    recipe_url: str = Field(description="The source URL of the recipe")
    ingredients: List[GroceryItem] = Field(description="List of ingredients required for the recipe")

class CalendarEventPrediction(BaseModel):
    """Represents projected grocery needs based on an upcoming calendar event."""
    event_name: str = Field(description="The name of the calendar event")
    event_date: str = Field(description="The date of the event in YYYY-MM-DD format")
    predicted_items: List[GroceryItem] = Field(description="Groceries predicted to be needed for this event")

class HouseholdIntentPayload(BaseModel):
    """The root payload returned by the LangChain ReAct agent."""
    summary: str = Field(description="A brief summary of what the agent understood and decided to do.")
    standard_groceries: Optional[List[GroceryItem]] = Field(default=None, description="Directly requested grocery items.")
    recipe_extractions: Optional[List[RecipeIngredients]] = Field(default=None, description="Ingredients extracted from provided URLs.")
    calendar_predictions: Optional[List[CalendarEventPrediction]] = Field(default=None, description="Items suggested based on upcoming events.")
