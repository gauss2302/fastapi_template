import datetime

from sqlalchemy import select, and_, or_, func, desc, asc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from uuid import UUID
import re

from app.core.exceptions.exceptions import ConflictError, ValidationError, NotFoundError
from app.schemas.job_schema import JobPostingCreate, JobSearchRequest, JobPostingUpdate
from app.models.job_position import Job, JobStatus, WorkingType


def _is_spam_title(title: str) -> bool:
    """Check for common spam patterns in job titles"""
    spam_patterns = [
        r'\$\$\$',  # Multiple dollar signs
        r'URGENT.*URGENT',  # Multiple URGENT
        r'!!!',  # Multiple exclamation marks
        r'EARN.*\$.*HOUR',  # Earn X dollars per hour
        r'WORK.*FROM.*HOME.*\$',  # Work from home + money
        r'MAKE.*MONEY.*FAST',  # Make money fast
    ]

    title_upper = title.upper()
    return any(re.search(pattern, title_upper) for pattern in spam_patterns)


def _validate_job_data(job_data: JobPostingCreate) -> List[str]:
    """Additional business validation beyond Pydantic"""
    errors = []

    # Check title for spam patterns
    if _is_spam_title(job_data.title):
        errors.append("Title contains spam patterns")

    # Validate salary range reasonableness
    if job_data.salary_min and job_data.salary_max:
        if job_data.salary_min > job_data.salary_max:
            errors.append("Minimum salary cannot exceed maximum salary")

        # Check for unrealistic salary ranges
        if job_data.salary_max > job_data.salary_min * 5:
            errors.append("Salary range too wide (max cannot be 5x more than min)")

    # Validate requirements quality
    if len(job_data.requirements) < 3:
        errors.append("At least 3 requirements are needed")

    # Check for duplicate requirements
    if len(set(job_data.requirements)) != len(job_data.requirements):
        errors.append("Requirements contain duplicates")

    # Validate skills
    if job_data.skills and len(job_data.skills) > 20:
        errors.append("Too many skills listed (max 20)")

    # Check for duplicate skills
    if job_data.skills and len(set(job_data.skills)) != len(job_data.skills):
        errors.append("Skills contain duplicates")

    return errors


def _clean_title_for_comparison(title: str) -> str:
    """Clean job title for duplicate detection"""
    # Remove common variations
    cleaned = title.lower()
    cleaned = re.sub(r'\b(senior|sr|junior|jr)\b', '', cleaned)
    cleaned = re.sub(r'\b(remote|hybrid|onsite)\b', '', cleaned)
    cleaned = re.sub(r'[^\w\s]', '', cleaned)  # Remove punctuation
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()  # Normalize whitespace
    return cleaned


def _create_slug(text: str) -> str:
    """Convert text to URL-friendly slug"""
    slug = text.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)  # Remove special chars
    slug = re.sub(r'[-\s]+', '-', slug)  # Replace spaces/hyphens with single hyphen
    slug = slug.strip('-')  # Remove leading/trailing hyphens
    return slug[:100]  # Limit length


def _prepare_job_dict(job_dict: dict) -> dict:
    """Prepare job dictionary for database insertion"""
    # Handle enum conversion
    enum_fields = ['level', 'type', 'working_type', 'status']
    for field in enum_fields:
        if field in job_dict and job_dict[field] is not None:
            value = job_dict[field]
            if hasattr(value, 'value'):
                # It's an enum object
                job_dict[field] = value.value
            elif isinstance(value, str):
                # It's already a string, ensure lowercase
                job_dict[field] = value.lower()

    # Handle JSON fields - ensure they're proper lists
    json_fields = ['requirements', 'skills', 'location_restrictions']
    for field in json_fields:
        if field in job_dict:
            if job_dict[field] is None:
                job_dict[field] = []
            elif not isinstance(job_dict[field], list):
                job_dict[field] = []

    # Set default values
    job_dict.setdefault('status', JobStatus.DRAFT.value)
    job_dict.setdefault('views_count', 0)
    job_dict.setdefault('applications_count', 0)

    # Convert HttpUrl to string if present
    if 'apply_url' in job_dict and job_dict['apply_url']:
        job_dict['apply_url'] = str(job_dict['apply_url'])

    # Remove None values for optional fields
    job_dict = {k: v for k, v in job_dict.items() if v is not None}

    return job_dict


def _apply_search_filters(query, params: JobSearchRequest):
    """Apply search filters to query"""

    # Text search in title, description, company
    if params.query:
        search_pattern = f'%{params.query}%'
        query = query.where(
            or_(
                Job.title.ilike(search_pattern),
                Job.description.ilike(search_pattern),
                Job.company_name.ilike(search_pattern)
            )
        )

    # Level filter
    if params.level:
        level_values = [level.value for level in params.level]
        query = query.where(Job.level.in_(level_values))

    # Type filter
    if params.type:
        type_values = [job_type.value for job_type in params.type]
        query = query.where(Job.type.in_(type_values))

    # Working type filter
    if params.working_type:
        working_type_values = [wt.value for wt in params.working_type]
        query = query.where(Job.working_type.in_(working_type_values))

    # Company filter
    if params.company_name:
        query = query.where(Job.company_name.ilike(f'%{params.company_name}%'))

    # Salary filters
    if params.salary_min:
        query = query.where(
            or_(
                Job.salary_min >= params.salary_min,
                Job.salary_max >= params.salary_min
            )
        )

    if params.salary_max:
        query = query.where(Job.salary_min <= params.salary_max)

    # Currency filter
    if params.salary_currency:
        query = query.where(Job.salary_currency == params.salary_currency)

    # Skills filter (JSON contains)
    if params.skills:
        for skill in params.skills:
            query = query.where(Job.skills.contains([skill]))

    # Experience filter
    if params.experience_max:
        query = query.where(
            or_(
                Job.experience_years <= params.experience_max,
                Job.experience_years.is_(None)
            )
        )

    # Timezone filter
    if params.timezone:
        query = query.where(Job.timezone.ilike(f'%{params.timezone}%'))

    # Location filter
    if params.location_allowed:
        query = query.where(
            or_(
                Job.location_restrictions.is_(None),
                Job.location_restrictions.contains([params.location_allowed])
            )
        )

    # Date filters
    if params.posted_after:
        query = query.where(Job.posted_at >= params.posted_after)

    if params.posted_before:
        query = query.where(Job.posted_at <= params.posted_before)

    # Special filters
    if params.has_salary:
        query = query.where(
            or_(
                Job.salary_min.is_not(None),
                Job.salary_max.is_not(None)
            )
        )

    if params.remote_only:
        query = query.where(Job.working_type == WorkingType.REMOTE.value)

    # Only active jobs by default
    query = query.where(Job.status == JobStatus.ACTIVE.value)

    return query


class JobRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, job_data: JobPostingCreate) -> Job:
        """Create a new job posting with validation and duplicate checking"""

        # 1. Validate input data
        validation_errors = _validate_job_data(job_data)
        if validation_errors:
            raise ValidationError(f"Validation failed: {', '.join(validation_errors)}")

        # 2. Check for duplicate jobs
        await self._check_for_duplicates(job_data)

        # 3. Generate unique slug for SEO-friendly URLs
        slug = await self._generate_unique_slug(job_data.title, job_data.company_name)

        # 4. Prepare job data for database
        job_dict = job_data.model_dump()
        job_dict['slug'] = slug
        job_dict = _prepare_job_dict(job_dict)

        # 5. Create database record
        try:
            db_job = Job(**job_dict)
            self.db.add(db_job)
            await self.db.flush()
            await self.db.refresh(db_job)

            return db_job

        except IntegrityError as e:
            await self.db.rollback()
            if "duplicate key" in str(e):
                raise ConflictError("Job posting with these details already exists")
            raise

    async def _check_for_duplicates(self, job_data: JobPostingCreate):
        """Check for potential duplicate job postings"""
        # Look for similar jobs from same company in last 7 days
        week_ago = datetime.utcnow() - timedelta(days=7)

        # Clean title for comparison
        clean_title = _clean_title_for_comparison(job_data.title)

        query = select(Job).where(
            and_(
                Job.company_name.ilike(f"%{job_data.company_name}%"),
                func.similarity(
                    func.lower(Job.title),
                    clean_title
                ) > 0.8,  # 80% similarity
                Job.created_at >= week_ago,
                Job.status.in_([JobStatus.ACTIVE.value, JobStatus.DRAFT.value]),
                Job.deleted_at.is_(None)
            )
        )

        result = await self.db.execute(query)
        existing_job = result.scalar_one_or_none()

        if existing_job:
            raise ConflictError(
                f"Similar job posting already exists: '{existing_job.title}' "
                f"created {existing_job.created_at.strftime('%Y-%m-%d')}"
            )

    async def _generate_unique_slug(self, title: str, company_name: str) -> str:
        """Generate unique slug for SEO-friendly URLs"""
        # Create base slug from title and company
        base_slug = _create_slug(f"{title} {company_name}")

        slug = base_slug
        counter = 1

        # Check for existing slugs and increment if needed
        while await self._slug_exists(slug):
            slug = f"{base_slug}-{counter}"
            counter += 1

        return slug

    async def _slug_exists(self, slug: str) -> bool:
        """Check if slug already exists"""
        query = select(Job.id).where(
            and_(
                Job.slug == slug,
                Job.deleted_at.is_(None)
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None

    # Read operations
    async def get_by_id(self, job_id: UUID) -> Optional[Job]:
        """Get job posting by ID"""
        query = select(Job).where(
            and_(
                Job.id == job_id,
                Job.deleted_at.is_(None)
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Job]:
        """Get job posting by slug"""
        query = select(Job).where(
            and_(
                Job.slug == slug,
                Job.deleted_at.is_(None)
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def search(self, search_params: JobSearchRequest) -> Dict[str, Any]:
        """Search jobs with filters and pagination"""
        query = select(Job).where(Job.deleted_at.is_(None))

        # Apply filters
        query = _apply_search_filters(query, search_params)

        # Get total count
        count_query = select(func.count(Job.id)).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        # Apply sorting
        query = self._apply_sorting(query, search_params)

        # Apply pagination
        offset = (search_params.page - 1) * search_params.limit
        query = query.offset(offset).limit(search_params.limit)

        # Execute query
        result = await self.db.execute(query)
        jobs = result.scalars().all()

        # Calculate pagination info
        pages = (total + search_params.limit - 1) // search_params.limit
        has_next = search_params.page < pages
        has_prev = search_params.page > 1

        return {
            'jobs': jobs,
            'total': total,
            'page': search_params.page,
            'limit': search_params.limit,
            'pages': pages,
            'has_next': has_next,
            'has_prev': has_prev
        }

    def _apply_sorting(self, query, params: JobSearchRequest):
        """Apply sorting to query"""
        sort_column = getattr(Job, params.sort_by, Job.posted_at)

        if params.sort_order == 'desc':
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(asc(sort_column))

        return query

    # Update operations
    async def update(self, job_id: UUID, job_data: JobPostingUpdate) -> Job:
        """Update existing job posting"""
        db_job = await self.get_by_id(job_id)
        if not db_job:
            raise NotFoundError(f"Job posting with id {job_id} not found")

        # Get only the fields that are being updated
        update_data = job_data.model_dump(exclude_unset=True)

        if update_data:
            # Validate the update
            if 'title' in update_data or 'company_name' in update_data:
                # Regenerate slug if title or company changed
                title = update_data.get('title', db_job.title)
                company = update_data.get('company_name', db_job.company_name)
                update_data['slug'] = await self._generate_unique_slug(title, company)

            # Apply updates
            for field, value in update_data.items():
                # Convert enums to strings
                if hasattr(value, 'value'):
                    value = value.value
                setattr(db_job, field, value)

            await self.db.flush()
            await self.db.refresh(db_job)

        return db_job

    async def update_status(self, job_id: UUID, status: JobStatus, reason: str = None) -> Job:
        """Update job status"""
        db_job = await self.get_by_id(job_id)
        if not db_job:
            raise NotFoundError(f"Job posting with id {job_id} not found")

        old_status = db_job.status
        db_job.status = status.value

        if reason:
            db_job.closure_reason = reason

        # Set timestamps based on status
        if status == JobStatus.ACTIVE and old_status == JobStatus.DRAFT.value:
            db_job.posted_at = datetime.utcnow()
        elif status in [JobStatus.FILLED, JobStatus.CANCELLED]:
            db_job.closed_at = datetime.utcnow()

        await self.db.flush()
        await self.db.refresh(db_job)
        return db_job

    async def increment_views(self, job_id: UUID) -> None:
        """Increment view counter"""
        db_job = await self.get_by_id(job_id)
        if db_job:
            db_job.views_count += 1
            await self.db.flush()

    async def increment_applications(self, job_id: UUID) -> None:
        """Increment application counter"""
        db_job = await self.get_by_id(job_id)
        if db_job:
            db_job.applications_count += 1
            await self.db.flush()

    # Delete operations
    async def soft_delete(self, job_id: UUID) -> bool:
        """Soft delete job posting"""
        db_job = await self.get_by_id(job_id)
        if not db_job:
            return False

        db_job.deleted_at = datetime.utcnow()
        await self.db.flush()
        return True

    async def restore(self, job_id: UUID) -> bool:
        """Restore soft deleted job posting"""
        query = select(Job).where(Job.id == job_id)
        result = await self.db.execute(query)
        db_job = result.scalar_one_or_none()

        if not db_job or not db_job.deleted_at:
            return False

        db_job.deleted_at = None
        await self.db.flush()
        return True

    # Company-specific operations
    async def get_company_jobs(self, company_name: str, status: JobStatus = None) -> List[Job]:
        """Get all jobs for a specific company"""
        query = select(Job).where(
            and_(
                Job.company_name.ilike(f'%{company_name}%'),
                Job.deleted_at.is_(None)
            )
        )

        if status:
            query = query.where(Job.status == status.value)

        query = query.order_by(desc(Job.created_at))

        result = await self.db.execute(query)
        return result.scalars().all()

    # Analytics operations
    async def get_job_stats(self, job_id: UUID) -> Optional[Dict[str, Any]]:
        """Get job statistics"""
        db_job = await self.get_by_id(job_id)
        if not db_job:
            return None

        return {
            'id': db_job.id,
            'title': db_job.title,
            'company_name': db_job.company_name,
            'status': db_job.status,
            'views_count': db_job.views_count,
            'applications_count': db_job.applications_count,
            'days_live': db_job.days_live(),
            'posted_at': db_job.posted_at,
            'view_to_application_rate': (
                db_job.applications_count / db_job.views_count
                if db_job.views_count > 0 else None
            )
        }