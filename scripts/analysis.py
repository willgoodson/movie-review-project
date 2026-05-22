import os
from dotenv import load_dotenv
import json
from ollama import chat
import time
from peewee import *
import argparse

## Load Environment Variables
load_dotenv()

## Handle Arguments
parser = argparse.ArgumentParser(
                                    prog='Movie Analysis',
                                    description='Extracts tags and sentiment score from reviews based on the provided movie slug'
                                )
parser.add_argument('movie_slug', help='Enter Letterboxd movie slug')
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

class Movies(BaseModel):
    slug = CharField(unique=True)
    name = CharField()
    description = TextField()
    release_year = IntegerField()
    status = CharField()


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

class Tags(BaseModel):
    name = CharField(unique=True)

class TagMovie(BaseModel):
    tag = ForeignKeyField(Tags, backref='movies_link')
    movie = ForeignKeyField(Movies, backref='tags_link')
    class Meta():
        indexes = (
            (('tag', 'movie'), True),
        )

## Conntact to database and create tables
db.connect()
db.create_tables([Movies, Reviews, Tags, TagMovie])

def review_analysis(slug):
    """Uses LLM to extract sentiment and relevant tags from review"""
    r_movie = Movies.get(Movies.slug == slug)
    for review in Reviews.select().where(Reviews.movie == r_movie.id):
        response = chat(
            # Downloaded models: llama3.2:3b, gemma3n:e2b
            model='llama3.2:3b',
            format='json',
            messages=[{'role': 'user',
                    'content': """
                            You are a structured data extraction engine. Evaluate the film described in the user comment below and return a JSON object containing exactly two fields: score and tags.

                            ### EXPECTED OUTPUT FORMAT:
                            JSON object structure:
                            - score: An integer from 1 to 10 evaluating the film's quality based on the true underlying sentiment.
                            - tags: An array of descriptive adjectives characterizing the MOVIE itself, not the review or the viewer.

                            ### TRANSFORMATION RULES FOR THE TAGS FIELD:
                            1. Shift the Focus to the Movie: Do not tag what the text is doing; tag what the movie is
                            2. Detect sarcastic or facetious remarks in reviews and score them accordingly but only create tags based on movie
                            3. Strict Blacklist: Never use generic sentiment words like "positive" or "negative". Never use literal film components like "ending", "plot", "acting", or "script". Never describe the viewer's direct state like "emotional" or "impressed".
                            4. Stick to adjectives describing the movie do not include nouns
                            5. Do not provide Null or Empty tags
                            6. Only one word with hyphenated words allowed

                            ### CONSTRAINTS:
                            - Return ONLY the raw JSON object.
                            - Do not include any introductions, explanations, or markdown code fences.

                            Review to analyze:
                            "{}"
                    """.format(review.full_review)}]
                    )
        analysis = json.loads(response.message.content)

        review.sentiment_score = analysis['score']
        review.save()
        for tag in analysis['tags']:
            tag = str(tag).lower()
            tag_obj, created = Tags.get_or_create(name=tag)
            TagMovie.insert({'tag': tag_obj.id, 'movie': r_movie.id}).on_conflict_ignore().execute()

def main():
    start_time = time.time()
    print('Starting Analysis...')
    review_analysis(args.movie_slug)
    print('Done! Runtime:', time.time()-start_time, 'seconds')

if __name__ == '__main__':
    main()