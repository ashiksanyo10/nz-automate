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

def wait_for_element(selector, timeout=10):
    start_time = time.time()
    while time.time() - start_time < timeout:
        if selector.exists():
            return True
        time.sleep(0.5)
    return False

def is_valid_director_name(name):
    return bool(name) and re.match("^[a-zA-Z ]+$", name)


def get_movie_details_from_website(movie_name, director_name,release_year, retries=1, similarity_threshold=0.8235):
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

def get_movie_details_from_nz_website(movie_name, director_name, release_year, retries=1):
    from difflib import SequenceMatcher  # For string similarity

    base_url = "https://www.fvlb.org.nz/"
    browser = start_chrome(base_url, headless=True)

    def string_similarity(a, b):
        """Calculate string similarity using SequenceMatcher."""
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    for attempt in range(retries):
        try:
            search_title_input = S("#fvlb-input")
            exact_match_checkbox = S("#ExactSearch")
            search_button = S(".submitBtn")

            write(movie_name, into=search_title_input)
            click(exact_match_checkbox)
            click(search_button)

            if not wait_for_element(S('.result-title')):
                browser.quit()
                return {
                    'movie_name': movie_name,
                    'director_name': director_name,
                    'release_year': release_year,
                    'classification': 'N/A',
                    'run_time': 'N/A',
                    'label_issued_by': 'N/A',
                    'label_issued_on': 'N/A',
                    'link': 'N/A',
                    'comment': 'Data not found'
                }

            time.sleep(3)  # Wait for results to load

            movie_links = find_all(S('.result-title'))
            best_match = None
            highest_similarity = 0
            comment = "Need Manual Verification"

            for link in movie_links:
                title_text = link.web_element.text.strip()
                title_similarity = string_similarity(movie_name, title_text)

                if title_similarity >= 0.9:  # Prioritize exact matches
                    click(link)
                    time.sleep(1)

                    page_source = get_driver().page_source
                    soup = BeautifulSoup(page_source, 'html.parser')

                    title_element = soup.find('h1')
                    title_name = title_element.text.strip() if title_element else 'N/A'

                    director_element = soup.find('div', class_='film-director')
                    dir_text = director_element.text.strip().replace('Directed by ', '') if director_element else 'N/A'
                    director_similarity = string_similarity(director_name, dir_text)

                    release_year_text = dir_text.split(",")[0].strip() if ',' in dir_text else 'N/A'

                    if director_similarity >= 0.9 and release_year == release_year_text:
                        classification_element = soup.find('div', class_='film-classification')
                        classification = classification_element.text.strip() if classification_element else 'N/A'

                        runtime_element = soup.find_all('div', class_='film-approved')[1]
                        runtime = runtime_element.text.strip().replace('This title has a runtime of ', '').replace(' minutes.', '')

                        browser.quit()
                        return {
                            'movie_name': title_name,
                            'director_name': dir_text,
                            'release_year': release_year_text,
                            'classification': classification,
                            'run_time': runtime,
                            'label_issued_by': 'N/A',
                            'label_issued_on': 'N/A',
                            'link': browser.current_url,
                            'comment': 'Found as Direct Search'
                        }
                elif title_similarity > highest_similarity:  # Track best partial match
                    best_match = link
                    highest_similarity = title_similarity

            if best_match and highest_similarity >= 0.8:  # Consider as partial match
                click(best_match)
                time.sleep(1)

                page_source = get_driver().page_source
                soup = BeautifulSoup(page_source, 'html.parser')

                title_element = soup.find('h1')
                title_name = title_element.text.strip() if title_element else 'N/A'

                director_element = soup.find('div', class_='film-director')
                dir_text = director_element.text.strip().replace('Directed by ', '') if director_element else 'N/A'
                release_year_text = dir_text.split(",")[0].strip() if ',' in dir_text else 'N/A'

                classification_element = soup.find('div', class_='film-classification')
                classification = classification_element.text.strip() if classification_element else 'N/A'

                runtime_element = soup.find_all('div', class_='film-approved')[1]
                runtime = runtime_element.text.strip().replace('This title has a runtime of ', '').replace(' minutes.', '')

                browser.quit()
                return {
                    'movie_name': title_name,
                    'director_name': dir_text,
                    'release_year': release_year_text,
                    'classification': classification,
                    'run_time': runtime,
                    'label_issued_by': 'N/A',
                    'label_issued_on': 'N/A',
                    'link': browser.current_url,
                    'comment': 'Need Manual Verification'
                }

        except Exception as e:
            logging.error(f"Error fetching details for {movie_name} from NZ website (attempt {attempt+1}/{retries}): {e}")
            time.sleep(5)  # Wait before retrying

    get_driver().quit()
    return {
        'movie_name': movie_name,
        'director_name': director_name,
        'release_year': release_year,
        'classification': 'N/A',
        'run_time': 'N/A',
        'label_issued_by': 'N/A',
        'label_issued_on': 'N/A',
        'link': 'N/A',
        'comment': 'Data not found'
    }

@app.route('/')
def index():
    return send_file('index2.html')

# @app.route('/upload', methods=['POST'])
# def upload_file():
#     try:
#         file = request.files['file']
#         if file.filename.endswith('.xlsx'):
#             df = pd.read_excel(file)
#             movie_names = df['Movie_name'].tolist()
#             director_names = df['Director_name'].tolist()

#             # Mapping 
#             mr_mapping = {
#                 "Suitable for general audiences": "G",
#                 "Parental guidance recommended for younger viewers": "PG",
#                 "Suitable for mature audiences": "M",
#                 "Unsuitable for audiences under 13 years of age": "13",
#                 "Restricted to persons 13 years and over": "R13",
#                 "Restricted to persons 13 years and over unless accompanied by a parent or guardian": "RP13",
#                 "Restricted to persons 15 years and over": "R15",
#                 "Unsuitable for audiences under 16 years of age": "16",
#                 "Restricted to persons 16 years and over": "R16",
#                 "Restricted to persons 16 years and over unless accompanied by a parent or guardian": "RP16",
#                 "Unsuitable for audiences under 18 years of age": "18",
#                 "Restricted to persons 18 years and over": "R18",
#                 "Restricted to persons 17 years and over unless accompanied by a parent or guardian": "RP18"
#             }

#             results = []
#             for movie_name, director_name in zip(movie_names, director_names):
#                 if not is_valid_director_name(director_name):
#                     results.append({
#                         'movie_name': movie_name,
#                         'director_name': 'No Director Details',
#                         'classification': 'N/A',
#                         'release_year': 'N/A',
#                         'run_time': 'N/A',
#                         'label_issued_by': 'N/A',
#                         'label_issued_on': 'N/A',
#                         'MR': 'N/A',
#                         'CD': 'N/A'
#                     })
#                     continue


#                 details = get_movie_details_from_website(movie_name, director_name)
#                 if not details:
#                     details = get_movie_details_from_nz_website(movie_name, director_name)

#                 if not details:
#                     details = {
#                         'movie_name': movie_name,
#                         'director_name': director_name,
#                         'classification': 'N/A',
#                         'release_year': 'N/A',
#                         'run_time': 'N/A',
#                         'label_issued_by': 'N/A',
#                         'label_issued_on': 'N/A',
#                         'MR': 'N/A',
#                         'CD': 'N/A'
#                     }
                
#                 mr_statement = details.get('MR', 'N/A')
#                 details['MR'] = mr_mapping.get(mr_statement, mr_statement) 

#                 results.append(details)

#             results_df = pd.DataFrame(results)
#             filename = 'movie_ratings.xlsx'
#             results_df.to_excel(filename, index=False)

#             return jsonify({'download_url': f'/download/{filename}'})
#         else:
#             return jsonify({'error': 'Invalid file format. Please upload an Excel file with .xlsx extension.'})
#     except Exception as e:
#         logging.error(f"Error processing upload: {e}")
#         return jsonify({'error': 'An error occurred while processing the file. Please try again.'})

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

            # Mapping MR
            mr_mapping = {
                "Suitable for general audiences": "G",
                "Parental guidance recommended for younger viewers": "PG",
                "Suitable for mature audiences": "M",
                "Unsuitable for audiences under 13 years of age": "13",
                "Restricted to persons 13 years and over": "R13",
                "Restricted to persons 13 years and over unless accompanied by a parent or guardian": "RP13",
                "Restricted to persons 15 years and over": "R15",
                "Unsuitable for audiences under 16 years of age": "16",
                "Restricted to persons 16 years and over": "R16",
                "Restricted to persons 16 years and over unless accompanied by a parent or guardian": "RP16",
                "Unsuitable for audiences under 18 years of age": "18",
                "Restricted to persons 18 years and over": "R18",
                "Restricted to persons 17 years and over unless accompanied by a parent or guardian": "RP18"
            }

            results = []
            for movie_name, director_name, release_year in zip(movie_names, director_names, release_years):
                if not is_valid_director_name(director_name):
                    results.append({
                        'movie_name': movie_name,
                        'director_name': 'No Director Details',
                        'release_year': release_year,
                        'classification': 'N/A',
                        'run_time': 'N/A',
                        'label_issued_by': 'N/A',
                        'label_issued_on': 'N/A',
                        'MR': 'N/A',
                        'CD': 'N/A'
                    })
                    continue

                details = get_movie_details_from_website(movie_name, director_name, release_year)
                if not details:
                    details = get_movie_details_from_nz_website(movie_name, director_name, release_year)

                if not details:
                    details = {
                        'movie_name': movie_name,
                        'director_name': director_name,
                        'release_year': release_year,
                        'classification': 'N/A',
                        'run_time': 'N/A',
                        'label_issued_by': 'N/A',
                        'label_issued_on': 'N/A',
                        'MR': 'N/A',
                        'CD': 'N/A',
                    }
                
                mr_statement = details.get('MR', 'N/A')
                details['MR'] = mr_mapping.get(mr_statement, mr_statement)  

                if details['comment'] == 'Found as Direct Search':
                    details['comment'] = 'Data Found via Direct Search'
                elif details['comment'] == 'Need Manual Verification':
                    details['comment'] = 'Need Manual Verification'
                elif details['comment'] == 'Data not found':
                    details['comment'] = 'No Data Found'

                results.append(details)

            results_df = pd.DataFrame(results)
            filename = 'movie_ratings.xlsx'
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
