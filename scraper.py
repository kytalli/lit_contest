import attr
import sqlite3
import datetime

@attr.s
class Grant:
    issuer = attr.ib()
    title = attr.ib()
    cash_prize = attr.ib()
    entry_fee = attr.ib()
    deadline = attr.ib()
    genres = attr.ib()
    description = attr.ib()
    read_more_link = attr.ib()

import requests
from bs4 import BeautifulSoup

class GenreManager:
    def __init__(self, conn):
        self.conn = conn
        self.create_genre_table()
        self.create_grant_genre_table()

    def create_genre_table(self):
        with self.conn:
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS genres (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE
                )
            ''')

    def create_grant_genre_table(self):
        with self.conn:
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS grant_genre (
                    grant_id INTEGER,
                    genre_id INTEGER,
                    FOREIGN KEY(grant_id) REFERENCES grants(id),
                    FOREIGN KEY(genre_id) REFERENCES genres(id),
                    UNIQUE(grant_id, genre_id)
                )
            ''')

    def add_genre(self, genre):
        with self.conn:
            self.conn.execute('''
                INSERT OR IGNORE INTO genres (name) VALUES (?)
            ''', (genre,))

    def get_genre_id(self, genre):
        cursor = self.conn.execute('''
            SELECT id FROM genres WHERE name = ?
        ''', (genre,))
        result = cursor.fetchone()
        return result[0] if result else None

    def link_grant_to_genre(self, grant_id, genre):
        genre_id = self.get_genre_id(genre)
        if genre_id:
            with self.conn:
                self.conn.execute('''
                    INSERT OR IGNORE INTO grant_genre (grant_id, genre_id)
                    VALUES (?, ?)
                ''', (grant_id, genre_id))

    def get_genres_for_grant(self, grant_id):
        cursor = self.conn.execute('''
            SELECT g.name FROM genres g
            JOIN grant_genre gg ON g.id = gg.genre_id
            WHERE gg.grant_id = ?
        ''', (grant_id,))
        return [row[0] for row in cursor.fetchall()]

class Database:
    def __init__(self, db_name):
        self.conn = sqlite3.connect(db_name)
        self.genre_manager = GenreManager(self.conn)  # Composition
        self.create_table()

    def create_table(self):
        with self.conn:
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS grants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    issuer TEXT,
                    title TEXT,
                    cash_prize TEXT,
                    entry_fee TEXT,
                    deadline TEXT,
                    genres TEXT,
                    description TEXT,
                    read_more_link TEXT,
                    extra_info TEXT,
                    UNIQUE(issuer, title, deadline)
                )
            ''')

    def insert_grant(self, grant):
        with self.conn:
            try:
                # Dynamically build the insert statement based on available attributes
                columns = ['issuer', 'title', 'cash_prize', 'entry_fee', 'deadline', 'genres', 'description', 'read_more_link']
                values = [getattr(grant, col) for col in columns]
                
                # Add extra_info if it exists
                if hasattr(grant, 'extra_info'):
                    columns.append('extra_info')
                    values.append(grant.extra_info)
                
                # Build the SQL insert statement
                columns_str = ', '.join(columns)
                placeholders_str = ', '.join(['?' for _ in columns])
                
                sql = f'''
                    INSERT INTO grants ({columns_str})
                    VALUES ({placeholders_str})
                '''
                
                self.conn.execute(sql, values)
                
                grant_id = self.conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                for genre in grant.genres.split(','):
                    genre = genre.strip()
                    if genre:  # Ensure the genre is not an empty string
                        self.genre_manager.add_genre(genre)
                        self.genre_manager.link_grant_to_genre(grant_id, genre)
            except sqlite3.IntegrityError:
                print(f"Grant already exists: {grant.title} by {grant.issuer} with deadline {grant.deadline}")

    def fetch_all_grants(self):
        with self.conn:
            cursor = self.conn.execute('SELECT * FROM grants')
            grants = cursor.fetchall()
            grants_with_genres = []
            for grant in grants:
                grant_id = grant[0]
                genres = self.genre_manager.get_genres_for_grant(grant_id)
                grants_with_genres.append((grant, genres))
            return grants_with_genres

    def close(self):
        self.conn.close()


def scrape_grants():
    base_url = 'https://www.pw.org/grants?page='
    page = 0
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
    }

    grants_list = []

    while True:
        # Construct the URL for the current page
        url = f"{base_url}{page}"
        response = requests.get(url, headers=headers)

        # Check if the request was successful
        if response.status_code != 200:
            print(f'Failed to retrieve the page: {response.status_code}')
            break

        # Parse the HTML content using BeautifulSoup
        soup = BeautifulSoup(response.content, 'html.parser')

        # Find all the grant entries
        grants = soup.find_all('div', class_='views-row')
        
        # Check if no grants were found
        if len(grants) == 0:
            print(f'No more grants found on page {page}. Stopping.')
            break

        print(f"Number of grants found on page {page}: {len(grants)}")

        # Extract information and create Grant objects
        for grant in grants:
            issuer = grant.find('div', class_='views-field-field-award-issuer').find('h2').text.strip()
            title = grant.find('div', class_='views-field-title').find('h2').text.strip()
            cash_prize = grant.find('div', class_='views-field-field-cash-prize').find('span', class_='field-content').text.strip()
            entry_fee = grant.find('div', class_='views-field-field-entry-amount-int').find('span', class_='field-content').text.strip()
            deadline = grant.find('div', class_='views-field-field-deadline').find('span', class_='field-content').text.strip()
            genres = grant.find('div', class_='views-field-taxonomy-vocabulary-3').find('span', class_='field-content').text.strip()
            description_div = grant.find('div', class_='views-field-body').find('div', class_='field-content')
            description = description_div.find('p').text.strip()
            read_more_link = description_div.find('a', class_='views-more-link')['href']

            grant_obj = Grant(
                issuer=issuer,
                title=title,
                cash_prize=cash_prize,
                entry_fee=entry_fee,
                deadline=deadline,
                genres=genres,
                description=description,
                read_more_link=f"https://www.pw.org{read_more_link}"
            )
            grants_list.append(grant_obj)
        
        # Increment the page number for the next iteration
        page += 1

    return grants_list

# Initialize the database
db = Database('grants.db')

# Run the scraper and get the list of grants
grants_list = scrape_grants()

# Insert grants into the database
for grant in grants_list:
    db.insert_grant(grant)

# Fetch and print all grants from the database
all_grants = db.fetch_all_grants()
for grant, genres in all_grants:
    print(grant)
    print("Genres:", genres)

# Close the database connection
db.close()