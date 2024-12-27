import datetime
import pandas as pd
from bs4 import BeautifulSoup
from helium import start_chrome, write, click, S, find_all, get_driver
import time
from flask import Flask, request, send_file, jsonify
import logging
import re
from difflib import SequenceMatcher

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

output_file_path = 'movie_ratings.xlsx'

def string_similarity(str1, str2):
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

def is_valid_director_name(name):
    return bool(name) and re.match("^[a-zA-Z ]+$", name)

def get_movie_details_from_website(movie_name, director_name, release_year, retries=1, similarity_threshold=0.9):
    base_url = "https://www.classificationoffice.govt.nz/find-a-rating/?search="
    search_url = base_url + movie_name.replace(" ", "+")

    for attempt in range(retries):
        try:
            browser = start_chrome(search_url, headless=True)
            time.sleep(5)  # Wait for the page to load
            page_source = browser.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            listings = soup.find_all('div', {'data-listing': ''})

            for listing in listings:
                title_tag = listing.find('h3', class_='h2')
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)

                director_tag = listing.find('p', class_='small')
                if not director_tag:
                    continue
                director_text = director_tag.get_text(strip=True)

                # Extract release year and director name from the text
                release_year_found = re.search(r'(\d{4})', director_text)
                release_year_extracted = release_year_found.group(1) if release_year_found else 'N/A'

                if director_name.lower() in director_text.lower() and release_year_extracted == release_year:
                    classification_tag = listing.find('p', class_='large mb-2')
                    classification = classification_tag.get_text(strip=True) if classification_tag else 'N/A'

                    mr_tag = listing.find('p', class_='large')
                    mr_text = mr_tag.get_text(strip=True) if mr_tag else 'N/A'

                    table = listing.find('table', class_='rating-result-table')
                    run_time = 'N/A'
                    label_issued_by = 'N/A'
                    label_issued_on = 'N/A'
                    if table:
                        lines = table.get_text(separator="\n", strip=True).split('\n')
                        for i, line in enumerate(lines):
                            if 'Running time:' in line:
                                run_time = lines[i + 1].strip()
                            elif 'Label issued by:' in line:
                                label_issued_by = lines[i + 1].strip()
                            elif 'Label issued on:' in line:
                                label_issued_on = lines[i + 1].strip()

                    browser.quit()
                    return {
                        'movie_name': movie_name,
                        'director_name': director_name,
                        'classification': classification,
                        'release_year': release_year,
                        'run_time': run_time,
                        'label_issued_by': label_issued_by,
                        'label_issued_on': label_issued_on,
                        'MR': mr_text,
                        'CD': classification,
                        'link': search_url,
                        'Comment': 'Found as Direct search'
                    }

                # Partial matching fallback
                if string_similarity(movie_name, title) >= similarity_threshold and string_similarity(director_name, director_text) >= similarity_threshold:
                    browser.quit()
                    return {
                        'movie_name': movie_name,
                        'director_name': director_name,
                        'classification': 'N/A',
                        'release_year': release_year_extracted,
                        'run_time': 'N/A',
                        'label_issued_by': 'N/A',
                        'label_issued_on': 'N/A',
                        'MR': 'N/A',
                        'CD': 'N/A',
                        'link': search_url,
                        'Comment': 'Need Manual Verification'
                    }
            browser.quit()
        except Exception as e:
            logging.error(f"Error fetching details for {movie_name} (attempt {attempt+1}/{retries}): {e}")
            time.sleep(5)  # Wait before retrying
    return None

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        file = request.files['file']
        if file.filename.endswith('.xlsx'):
            df = pd.read_excel(file)

            df['Movie_name'] = df['Movie_name'].fillna('').astype(str)
            df['Director_name'] = df['Director_name'].fillna('').astype(str)
            df['Release_year'] = df['Release_year'].fillna('').astype(str)

            movie_names = df['Movie_name'].tolist()
            director_names = df['Director_name'].tolist()
            release_years = df['Release_year'].tolist()

            results = []
            for movie_name, director_name, release_year in zip(movie_names, director_names, release_years):
                if not is_valid_director_name(director_name):
                    results.append({
                        'movie_name': movie_name,
                        'director_name': 'No Director Details',
                        'classification': 'N/A',
                        'release_year': 'N/A',
                        'run_time': 'N/A',
                        'label_issued_by': 'N/A',
                        'label_issued_on': 'N/A',
                        'MR': 'N/A',
                        'CD': 'N/A',
                        'Comment': 'Invalid Director Name'
                    })
                    continue

                details = get_movie_details_from_website(movie_name, director_name, release_year)
                if not details:
                    details = {
                        'movie_name': movie_name,
                        'director_name': director_name,
                        'classification': 'N/A',
                        'release_year': release_year,
                        'run_time': 'N/A',
                        'label_issued_by': 'N/A',
                        'label_issued_on': 'N/A',
                        'MR': 'N/A',
                        'CD': 'N/A',
                        'Comment': 'Data not found'
                    }

                results.append(details)

            results_df = pd.DataFrame(results)
            filename = 'movie_ratings_with_comments.xlsx'
            results_df.to_excel(filename, index=False)

            return jsonify({'download_url': f'/download/{filename}'})
        else:
            return jsonify({'error': 'Invalid file format. Please upload an Excel file with .xlsx extension.'})
    except Exception as e:
        logging.error(f"Error processing upload: {e}")
        return jsonify({'error': 'An error occurred while processing the file. Please try again.'})

@app.route('/download/<filename>')
def download_file(filename):
    return send_file(filename, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True, port=8080)
