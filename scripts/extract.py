from bs4 import BeautifulSoup
import requests as req
import datetime as dt
import time
import re
import hashlib
import argparse
from curl_cffi import requests
import random

from models.dbmodels import *

## Handle Arguments
parser = argparse.ArgumentParser(
                                    prog='Movie Extract',
                                    description='Extracts movie data from letterboxd from the provided url'
                                )
parser.add_argument('url', help='Enter Letterboxd movie URL of format https://letterboxd.com/film/(movie)/')
args = parser.parse_args()

HEADERS = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }

## Initialize Database
DB.connect()
DB.create_tables([Directors, Actors, Genres, Movies, Reviews, ActorMovie, DirectorMovie, GenreMovie])

def extract_reviews(movie_slug, movie_id):
    """Takes in the movie slug with the movie id. Scrapes reviews from letterboxd using pagination. Then loads the reviews into the database."""
    REVIEW_LIST = set()
    page = 1
    session = requests.Session(impersonate="chrome")
    session.headers.update(HEADERS)
    print('Scraping reviews...')
    start_time = time.time()
    while True:
        try:
            res = session.get(f'https://letterboxd.com/film/{movie_slug}/reviews/by/added-earliest/page/{page}')
        except Exception as err:
            print(f'Failed to retrieve reviews for {movie_slug} on page {page}: {err}')
            continue
        if res.status_code != 200:
            print('Script is being blocked!')
            break
        soup = BeautifulSoup(res.text, 'html.parser')
        reviews = soup.find_all("article", class_='production-viewing')
        for review in reviews:
            try:
                r_time = dt.datetime.strptime(str(review.find('time').text).strip(), "%d %b %Y")
            except Exception as err:
                print(f'Failed to convert time for review on page {page}!', err, (str(review.find('time').text).strip()))
                continue
            try:
                review_text = str(review.find('div', class_='body-text').text).strip()
                REVIEW_LIST.add((
                    r_time,
                    process_rating(review.find('title')),
                    review_text,
                    hashlib.md5(review_text.encode('utf-8')).hexdigest()))
            except Exception as err:
                print('Failed to add review!', err)
        if len(reviews) < 12:
            break
        session.headers.update({"Referer": "https://letterboxd.com/film/{movie_slug}/reviews/page/{page}"})
        page=page+1
        # Please dont rate limit me
        time.sleep(random.uniform(3.0, 7.0))

    review_ins = [{'post_time': p_time, 'rating_score': score, 'full_review': review, 'movie': movie_id, 'sentiment_score': 0, 'review_hash': hash} for p_time, score, review, hash in REVIEW_LIST]
    Reviews.insert_many(review_ins).on_conflict_ignore().execute()
    print('Done. Runtime: ', time.time() - start_time, 'seconds')

def extract_movie(movie_slug):
    """Takes movie slug from url and looks up movie and scrapes page for movie data before inserting data into the database and returning the movie id"""
    html = req.get(f'https://letterboxd.com/film/{movie_slug}/', headers=HEADERS)
    soup = BeautifulSoup(html.text, 'html.parser')
    #Field Defaults
    actors = []
    genres = []
    directors = []
    desc = ''
    name = ''
    release_year = ''
    start_time = time.time()
    print('Extracting Movie Info...')
    # Movie Details
    try:
        details = soup.find('div', class_='details')
        try:
            name = details.find('span', class_='name').text
        except Exception as err:
            print('Could not find movie name!', err)
            return None
        try:
            release_year = details.find('span', class_='releasedate').text
        except Exception as err:
            print('Could not find release year!', err)
            return None
        try:
            directors = [director.text for director in details.find_all('a', class_='contributor')]
        except Exception as err:
            print('Could not find directors!', err)
            return None
    except Exception as err:
        print('Could not find details!', err)
        return None
    # Description
    try:
        desc = soup.find('section', class_='production-synopsis')
        desc = desc.find('p').text
    except Exception as err:
        print('Could not find description!', err)
        return None
    # Actors
    try:
        actors = soup.find('div', class_='cast-list')
        actors = [actor.text for actor in actors.find_all('a')]
        try:
            actors.remove('Show All…')
        except:
            pass
    except Exception as err:
        print('Could not find actors!', err)
        return None
    # Genres
    try:
        genres = soup.find('div', id='tab-panel-genres')
        genres = genres.find_next('div')
        genres = [genre.text for genre in genres.find_all('a')]
    except Exception as err:
        print('Could not find genres!', err)
        return None
    # Insert Movie
    movie_obj, created = Movies.get_or_create(
                            slug=movie_slug,
                            name=name,
                            description=desc,
                            release_year=release_year,
                            status='')
    # Insert Actors and Populate ActorMovie
    for actor in actors:
        actor_obj, created = Actors.get_or_create(name=actor)
        ActorMovie.insert({'actor': actor_obj.id, 'movie': movie_obj.id}).on_conflict_ignore().execute()
     # Insert Genres and Populate GenreMovie
    for genre in genres:
        genre_obj, created = Genres.get_or_create(name=genre)
        GenreMovie.insert({'genre': genre_obj.id, 'movie': movie_obj.id}).on_conflict_ignore().execute()
    # Insert Director and Populate DirectorMovie
    for director in directors:
        director_obj, created = Directors.get_or_create(name=director)
        DirectorMovie.insert({'director': director_obj.id, 'movie': movie_obj.id}).on_conflict_ignore().execute()

    print('Done. Runtime: ', time.time()-start_time, 'seconds')
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
    time.sleep(1)
    return slug

def main ():
    slug = process_link(args.url)
    if slug:
        id = extract_movie(slug)
        if id:
            extract_reviews(slug, id)
            print('done')

if __name__ == "__main__":
    main()
