from sqlalchemy import Column, Float, Integer, Text

from .base import Base


class YamlCache(Base):
    __tablename__ = "yaml_cache"

    filename = Column(Text, primary_key=True)
    mtime = Column(Float, nullable=False)
    data_json = Column(Text, nullable=False)
    file_hash = Column(Text, nullable=False, default="")


class MetaKV(Base):
    __tablename__ = "meta"

    key = Column(Text, primary_key=True)
    value = Column(Text, nullable=False)


class YamlRow(Base):
    __tablename__ = "yaml_rows"

    filename = Column(Text, primary_key=True)
    id = Column(Integer, primary_key=True)
    data_json = Column(Text, nullable=False)


class MusicChart(Base):
    __tablename__ = "music_charts"

    music_id = Column(Integer, primary_key=True)
    data_json = Column(Text, nullable=False)
