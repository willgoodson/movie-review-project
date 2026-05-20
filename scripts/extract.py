from dotenv import load_dotenv
from bs4 import BeautifulSoup
from peewee import *
import requests as req
import datetime as dt
import time
import re
import hashlib
import os
import argparse

## Load Environment Variables
load_dotenv()

parser = argparse.ArgumentParser(
                                    prog='Movie Extract',
                                    description='Extracts movie data from letterboxd from the provided url'
                                )
parser.add_argument('url', help='Enter Letterboxd movie URL of format https://letterboxd.com/film/(movie)/')
args = parser.parse_args()

## Database Connector
db = PostgresqlDatabase(os.environ.get('DATABASE', 'postgres'),
                    user=os.environ.get('DB_USER', ''),
                    password=os.environ.get('DB_PASS', ''),
                    host=os.environ.get('DB_HOST', 'localhost'),
                    port=int(os.environ.get('DB_PORT', '5432')))

## Schema Definitions
class BaseModel(Model):
    class Meta():
        database = db

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
    director = ForeignKeyField(Directors, backref='directs')
    genre = ForeignKeyField(Genres, backref='movies')

class ActorMovie(BaseModel):
    actor = ForeignKeyField(Actors, backref='movies_link')
    movie = ForeignKeyField(Movies, backref='actors_link')
    class Meta():
        indexes = (
            (('actor', 'movie'), True),
        )

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

HEADERS = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Dest": "document",
            }

## Initialize Database
db.connect()
db.create_tables([Directors, Actors, Genres, Movies, ActorMovie, Reviews])

def extract_reviews(movie_slug, movie_id):
    """Takes in the movie slug with the movie id. Scrapes reviews from letterboxd using pagination. Then loads the reviews into the database."""
    REVIEW_LIST = set()
    page = 1
    while True:
        print(f'Scraping page {page}...')
        html = req.get(f'https://letterboxd.com/film/{movie_slug}/reviews/by/added-earliest/page/{page}', headers=HEADERS)
        soup = BeautifulSoup(html.text, 'html.parser')
        reviews = soup.find_all("article", class_='production-viewing')
        for review in reviews:
            try:
                review_text = str(review.find('div', class_='body-text').text).strip()
                REVIEW_LIST.add((
                    dt.datetime.strptime(str(review.find('time').text).strip(), "%d %b %Y"),
                    process_rating(review.find('title')),
                    review_text,
                    hashlib.md5(review_text.encode('utf-8')).hexdigest()))
            except Exception as err:
                print(err)
        if len(reviews) < 12:
            break
        page=page+1
        # Please dont rate limit me
        time.sleep(0.25)

    review_ins = [{'post_time': p_time, 'rating_score': score, 'full_review': review, 'movie': movie_id, 'sentiment_score': 0, 'review_hash': hash} for p_time, score, review, hash in REVIEW_LIST]
    Reviews.insert_many(review_ins).on_conflict_ignore().execute()

def extract_movie(movie_slug):
    """Takes movie slug from url and looks up movie and scrapes page for movie data before inserting data into the database and returning the movie id"""
    html = req.get(f'https://letterboxd.com/film/{movie_slug}/')
    soup = BeautifulSoup(html.text, 'html.parser')
    # Description
    desc = soup.find('section', class_='production-synopsis')
    desc = desc.find('p').text
    # Actors
    actors = soup.find('div', class_='cast-list')
    actors = [actor.text for actor in actors.find_all('a')]
    # Genre
    genre = soup.find('div', id='tab-panel-genres')
    genre = genre.find('a').text
    # Movie Details
    details = soup.find('div', class_='details')
    name = details.find('span', class_='name').text
    release_year = details.find('span', class_='releasedate').text
    director = details.find_all('a', class_='contributor')[0].text
    print(movie_slug, name, desc, release_year, director, genre, actors)

    # Insert Genre
    genre_obj, created = Genres.get_or_create(name=genre)
    # Insert Director
    director_obj, created = Directors.get_or_create(name=director)
    # Insert Movie
    movie_obj, created = Movies.get_or_create(slug=movie_slug,
                              name=name,
                              description=desc,
                              release_year=release_year,
                              status='',
                              director=director_obj.id,
                              genre=genre_obj.id)
    # Insert Actors and Populate ActorMovie
    for actor in actors:
        actor_obj, created = Actors.get_or_create(name=actor)
        ActorMovie.insert({'actor': actor_obj.id, 'movie': movie_obj.id}).on_conflict_ignore().execute()

    return movie_obj.id


def process_rating(rating):
    """Takes in ascii character 5 star rating from review and returns 0-10 rating"""
    if rating:
        rating = rating.text
        stars = rating.count('★')
        half = rating.count('½')
        score = (stars + (half * 0.5))*2.0
        return int(score)
    return 0

def process_link(link:str):
    """Ensure link is a valid letterboxd link and that it did return a successful webpage then returns movie slug"""
    if not re.match('https://letterboxd.com/film/', link):
        print('Invalid URL! Enter Letterboxd movie URL of format https://letterboxd.com/film/(movie)/')
        return None
    res = req.get(link, headers=HEADERS)
    if res.status_code != 200:
        print('Invalid URL! Enter Letterboxd movie URL of format https://letterboxd.com/film/(movie)/')
        return None
    slug = link.split('/')[4]
    return slug

slug = process_link(args.url)
if slug:
    id = extract_movie(slug)
    extract_reviews(slug, id)
    print('done')
