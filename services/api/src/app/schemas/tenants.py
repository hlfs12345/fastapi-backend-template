from pydantic import BaseModel, ConfigDict, Field


class TenantUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)


class TenantResponse(BaseModel):
    name: str
    slug: str
