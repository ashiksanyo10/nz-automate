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
