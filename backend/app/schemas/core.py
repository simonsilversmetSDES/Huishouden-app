from pydantic import BaseModel, ConfigDict


class ContextOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
