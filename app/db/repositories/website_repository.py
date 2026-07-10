import uuid

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Website


class WebsiteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, domain: str, root_url: str) -> Website:
        website = Website(domain=domain.lower(), root_url=root_url)
        self.session.add(website)
        await self.session.flush()
        return website

    async def get_by_id(self, website_id: uuid.UUID) -> Website | None:
        return await self.session.get(Website, website_id)

    async def get_by_domain(self, domain: str) -> Website | None:
        statement = select(Website).where(Website.domain == domain.lower())
        return await self.session.scalar(statement)

    async def list(self, *, offset: int = 0, limit: int = 50) -> list[Website]:
        statement: Select[tuple[Website]] = (
            select(Website).order_by(Website.created_at.desc()).offset(offset).limit(limit)
        )
        return list((await self.session.scalars(statement)).all())
