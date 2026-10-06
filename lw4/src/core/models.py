"""ORM-модели. Здесь живёт только Base.

Таблица dictionary объявлена в mt.mt_models (наследуется от этого Base),
чтобы core не зависел от слоя машинного перевода.
"""
from sqlalchemy.orm import declarative_base

Base = declarative_base()