"""ORM-модель словаря EN -> RU.

Типы подобраны так, чтобы одинаково работать и в SQLite, и в PostgreSQL:
String/Text/Integer/DateTime — универсальные, без диалект-специфичных
JSONB/ARRAY/UUID.
"""
from sqlalchemy import (Column, DateTime, Integer, String, Text,
                        UniqueConstraint, func)

from core.models import Base


class Dictionary(Base):
    __tablename__ = 'dictionary'

    id = Column(Integer, primary_key=True)
    source_word = Column(String(255), nullable=False, index=True)  # EN лемма (lower)
    source_form = Column(String(255))                              # исходная форма
    target_word = Column(String(255), nullable=False)              # RU перевод
    pos = Column(String(50), index=True)                           # UPOS
    tag = Column(String(50))                                       # Penn tag
    morph = Column(Text)                                           # морфология EN
    translation_source = Column(String(50), default='manual')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('source_word', 'pos', name='uq_dict_src_pos'),
    )