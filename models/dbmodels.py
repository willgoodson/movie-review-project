## Database Connector
from peewee import *
import os
from dotenv import load_dotenv

load_dotenv()

DB = PostgresqlDatabase(os.environ.get('DATABASE', 'postgres'),
                    user=os.environ.get('DB_USER', ''),
                    password=os.environ.get('DB_PASS', ''),
                    host=os.environ.get('DB_HOST', 'localhost'),
                    port=int(os.environ.get('DB_PORT', '5432')))

class BaseModel(Model):
    class Meta():
        database = DB

class Tags(BaseModel):
    name = CharField(unique=True)

class Directors(BaseModel):
    name = CharField(unique=True)

class Actors(BaseModel):
    name = CharField(unique=True)

class Genres(BaseModel):
    name = CharField(unique=True)

class Movies(BaseModel):
    slug = CharField(unique=True)
    name = CharField()
    description = TextField()
    release_year = IntegerField()
    status = CharField()

class ActorMovie(BaseModel):
    actor = ForeignKeyField(Actors, backref='movies_link')
    movie = ForeignKeyField(Movies, backref='actors_link')
    class Meta():
        indexes = (
            (('actor', 'movie'), True),
        )

class DirectorMovie(BaseModel):
    director = ForeignKeyField(Directors, backref='movies_link')
    movie = ForeignKeyField(Movies, backref='directors_link')
    class Meta():
        indexes = (
            (('director', 'movie'), True),
        )

class GenreMovie(BaseModel):
    genre = ForeignKeyField(Genres, backref='movies_link')
    movie = ForeignKeyField(Movies, backref='genres_link')
    class Meta():
        indexes = (
            (('genre', 'movie'), True),
        )

class TagMovie(BaseModel):
    tag = ForeignKeyField(Tags, backref='movies_link')
    movie = ForeignKeyField(Movies, backref='tags_link')

class Reviews(BaseModel):
    post_time = DateTimeField()
    rating_score = IntegerField()
    sentiment_score = IntegerField()
    full_review = TextField()
    review_hash = CharField(max_length=32)
    movie = ForeignKeyField(Movies, backref='reviews')
    class Meta():
        indexes = (
            (('post_time', 'rating_score', 'review_hash', 'movie'), True),
        )