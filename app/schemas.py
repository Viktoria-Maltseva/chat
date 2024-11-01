from pydantic import BaseModel, Field, ConfigDict


class LoginForm(BaseModel):
    username: str
    password: str


class UserBase(BaseModel):
    username: str


class UserCreate(UserBase):
    password: str


class User(UserBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class RegisterForm(BaseModel):
    username: str = Field(..., min_length=4, description="Никнейм должен быть не менее 4 символов")
    password: str = Field(..., min_length=5, description="Пароль должен быть не менее 5 символов")


class ChannelCreate(BaseModel):
    channel_name: str = Field(..., min_length=1, description="Никнейм должен быть не менее 4 символов")