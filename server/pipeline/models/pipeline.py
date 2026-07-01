from datetime import datetime
from sqlmodel import Field, SQLModel


class OpensearchDataPipeline(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True, )
    created_at: datetime = Field(default_factory=lambda: datetime.now())

    host: str
    port: int
    username: str
    password: str

    use_ssl: bool
    verify_certs: bool
    ssl_assert_hostname: bool
    ssl_show_warn: bool

    index: str
    subject : str
