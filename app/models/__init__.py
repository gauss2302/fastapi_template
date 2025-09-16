"""
Models package - Import order matters!
Base class first, then models in dependency order.
"""

# 1. Import Base first
from app.core.database.database import Base

# 2. Import models with minimal dependencies first
from .user import User
from .company import Company

# 3. Import models that depend on the above
from .recruiter import Recruiter  
from .applicant import Applicant
from .job_position import Job

# 4. Import models with the most dependencies last
from .application import Application

# 5. Export everything
__all__ = [
    "Base",
    "User",
    "Company", 
    "Recruiter",
    "Applicant",
    "Job", 
    "Application"
]