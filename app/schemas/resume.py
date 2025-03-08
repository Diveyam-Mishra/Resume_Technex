from typing import Dict, List, Literal, Optional, Union, Any
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
import uuid
import re


class CreateResumeRequest(BaseModel):
    title: str
    slug: Optional[str] = None
    visibility: Literal["public", "private"] = "private"
    
    @field_validator('slug')
    def validate_slug(cls, v, values):
        if v is None:
            # Auto-generate slug from title if not provided
            if 'title' in values:
                return re.sub(r'[^a-z0-9]+', '-', values['title'].lower()).strip('-')
        else:
            # Validate slug format if provided
            if not re.match(r'^[a-z0-9-]+$', v):
                raise ValueError('Slug must contain only lowercase alphanumeric characters and hyphens')
        return v


class ResumeMetadataCSS(BaseModel):
    visible: bool = False
    value: str = ""


class ResumeMetadata(BaseModel):
    id: Optional[str] = None
    template: str = "standard"
    layout: List[List[str]] = []
    css: ResumeMetadataCSS = Field(default_factory=ResumeMetadataCSS)
    page: Dict[str, Any] = {}
    theme: Dict[str, Any] = {}
    typography: Dict[str, Any] = {}
    locale: str = "en-US"
    date: Dict[str, Any] = {}
    

class ResumeBasics(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    website: str = ""
    headline: str = ""
    summary: str = ""
    birthdate: str = ""
    photo: Dict[str, Any] = {}
    location: Dict[str, Any] = {}
    profiles: List[Dict[str, Any]] = []
    

class ResumeSection(BaseModel):
    id: str
    name: str
    items: List[Dict[str, Any]] = []


class ResumeData(BaseModel):
    metadata: ResumeMetadata = Field(default_factory=ResumeMetadata)
    basics: ResumeBasics = Field(default_factory=ResumeBasics)
    sections: Dict[str, ResumeSection] = {}


class Resume(BaseModel):
    id: uuid.UUID
    userId: uuid.UUID
    title: str
    slug: str
    visibility: Literal["public", "private"]
    locked: bool = False
    data: ResumeData
    createdAt: datetime
    updatedAt: datetime

    class Config:
        orm_mode = True


class UpdateResumeRequest(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    visibility: Optional[Literal["public", "private"]] = None
    data: Optional[ResumeData] = None
    
    @field_validator('slug')
    def validate_slug(cls, v):
        if v is not None and not re.match(r'^[a-z0-9-]+$', v):
            raise ValueError('Slug must contain only lowercase alphanumeric characters and hyphens')
        return v


class ImportResumeRequest(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    data: ResumeData


class StatisticsResponse(BaseModel):
    views: int = 0
    downloads: int = 0


class PrintResponse(BaseModel):
    url: str