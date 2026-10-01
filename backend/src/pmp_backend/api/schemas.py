"""Response bodies shared by several routers."""

from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    email: str
    role: str
    is_active: bool
    must_change_password: bool
    programme: str | None
    year: str | None
