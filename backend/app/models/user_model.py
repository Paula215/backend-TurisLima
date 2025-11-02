# app/models/user_model.py (MANTENER ESTE)
from bson import ObjectId
from pydantic import BaseModel, Field, EmailStr, validator
from typing import Optional, List

class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")

class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str
    gender: Optional[str] = None
    age: Optional[int] = None
    preferences: Optional[List[str]] = []
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v
    
    @validator('age')
    def validate_age(cls, v):
        if v is not None and (v < 13 or v > 120):
            raise ValueError('Age must be between 13 and 120')
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str = Field(alias="_id")
    username: str
    email: EmailStr
    gender: Optional[str] = None
    age: Optional[int] = None
    preferences: List[str] = []
    avatar: Optional[str] = None
    
    class Config:
        populate_by_name = True