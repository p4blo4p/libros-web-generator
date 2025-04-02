import requests
from bs4 import BeautifulSoup
import json
import time

def scrape_amazon_bestsellers(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0',
        'Referer': 'https://www.google.com/'
    }

    try:
        print(f"Attempting to fetch URL: {url}")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        print(f"Successfully fetched URL with status code: {response.status_code}")
        # with open("amazon_bestsellers_page.html", "w", encoding="utf-8") as f:
        #     f.write(response.text)
        # print("Saved fetched HTML to amazon_bestsellers_page.html for inspection.")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    books_data = []

    grid_container = soup.find('div', attrs={'data-card-metrics-id': lambda x: x and 'zg-list-grid' in x})
    if not grid_container:
        print("Could not find the main grid container.")
        return []

    book_elements = grid_container.find_all('div', id='gridItemRoot')
    print(f"Found {len(book_elements)} potential book elements using '#gridItemRoot'.")

    if not book_elements:
        print("No book elements found even within grid container.")
        return []

    item_count = 0
    for element in book_elements:
        item_count += 1
        book_info = {}

        # --- Rank ---
        rank_container = element.find('div', class_='zg-bdg-ctr')
        rank_element = rank_container.find('span', class_='zg-bdg-text') if rank_container else None
        book_info['rank'] = rank_element.text.strip('#') if rank_element else None

        # --- Link (Still get from image link if possible) ---
        image_link_element = element.find('a', class_='a-link-normal', href=True) # The one containing the image
        book_info['link'] = 'https://www.amazon.es' + image_link_element['href'] if image_link_element else None

        # --- Title (Search within the whole element now) ---
        title_element = None
        # Attempt 1: Specific Clamp Class
        title_element = element.find('div', class_=lambda x: x and x.startswith('_cDEzb_p13n-sc-css-line-clamp-'))
        # Attempt 2: Look for span/div with role='link' (often used for clickable titles not in <a>)
        if not title_element:
            title_element = element.find(['div', 'span'], attrs={'role': 'link'})
         # Attempt 3: Look for link text *not* the image link
        if not title_element:
            all_links = element.find_all('a', class_='a-link-normal', href=True)
            for link in all_links:
                 # Check if this link actually contains text and is not just the image container
                 link_text = link.get_text(strip=True)
                 if link != image_link_element and link_text:
                     title_element = link # Assume this other link contains the title
                     # Optionally update the main link if this one is preferred
                     # book_info['link'] = 'https://www.amazon.es' + link['href']
                     break

        book_info['title'] = title_element.get_text(strip=True) if title_element else None

        # --- Author ---
        all_author_containers = element.find_all(['div','span'], class_='a-size-small') # Broaden search slightly
        book_info['author'] = None
        title_text_lower = book_info['title'].lower() if book_info['title'] else ""
        rank_text = f"#{book_info['rank']}" if book_info['rank'] else ""

        for container in all_author_containers:
            container_text = container.get_text(strip=True)
            # More robust check: not empty, not title, not rank, not rating, not format/price
            if (container_text and
                container_text != book_info['title'] and
                container_text.lower() != title_text_lower and # Case-insensitive check too
                container_text != rank_text and
                'estrellas' not in container_text.lower() and
                'tapa' not in container_text.lower() and
                'libro' not in container_text.lower() and # Exclude 'Libro de bolsillo'
                '€' not in container_text):

                # Further check: ensure it's not nested within the price or rating elements found later
                price_elem = element.find(['span', 'div'], class_=lambda x: x and ('price' in x or 'Price' in x))
                rating_elem = element.find('div', class_='a-icon-row')
                is_inside_price = price_elem and container in price_elem.find_all(True)
                is_inside_rating = rating_elem and container in rating_elem.find_all(True)

                if not is_inside_price and not is_inside_rating:
                     book_info['author'] = container_text
                     break # Found likely author

        # --- Rating and Reviews --- (Keep previous logic, relative to element)
        rating_row = element.find('div', class_='a-icon-row')
        rating_link = rating_row.find('a', class_='a-link-normal') if rating_row else None
        review_count_span = rating_link.find('span', class_='a-size-small') if rating_link else None
        book_info['rating_avg'] = None
        book_info['review_count'] = None
        if rating_link and rating_link.get('title'):
            try:
                rating_text = rating_link['title'].split(' ')[0].replace(',', '.')
                book_info['rating_avg'] = float(rating_text)
            except (ValueError, IndexError): pass
        if review_count_span:
             try:
                count_text = review_count_span.text.strip().replace('.', '').replace(',', '')
                book_info['review_count'] = int(count_text)
             except ValueError: pass

        # --- Format --- (Keep previous logic, relative to element)
        format_element = element.find('span', class_='a-size-small a-color-secondary a-text-normal')
        book_info['format'] = format_element.text.strip() if format_element else None

        # --- Price --- (Keep previous logic, relative to element)
        price_container = element.find('div', class_='_cDEzb_p13n-sc-price-animation-wrapper_3PzN2')
        price_span = None
        if price_container:
             price_span = price_container.find('span', class_='_cDEzb_p13n-sc-price_3mJ9Z')
        else:
             price_span_alt_cont = element.find('div', class_='a-row')
             if price_span_alt_cont:
                 price_span = price_span_alt_cont.find('span', class_='a-color-price')
        book_info['price'] = price_span.text.strip() if price_span else None


        # --- Image URL --- (Keep previous logic, relative to element)
        image_element = element.find('img', class_='a-dynamic-image')
        book_info['image_url'] = image_element['src'] if image_element and image_element.get('src') else None


        # --- Conditional Append ---
        if book_info.get('rank') is not None and book_info.get('title') is not None:
             books_data.append(book_info)
        # else: # Debugging if items are still skipped
        #      print(f"Skipping item {item_count}. Rank: {book_info.get('rank')}, Title: {book_info.get('title')}")


        time.sleep(0.05)

    return books_data

# --- Main Execution ---
if __name__ == "__main__":
    target_url = "https://www.amazon.es/gp/bestsellers/books"
    print(f"Scraping Amazon ES Best Sellers (Books): {target_url}")

    bestselling_books = scrape_amazon_bestsellers(target_url)

    if bestselling_books:
        print(f"\nSuccessfully scraped {len(bestselling_books)} books.")
        print("\n--- Sample Results ---")
        print(json.dumps(bestselling_books[:5], indent=4, ensure_ascii=False))

        try:
            with open('amazon_bestsellers_es.json', 'w', encoding='utf-8') as f:
                json.dump(bestselling_books, f, ensure_ascii=False, indent=4)
            print("\nSaved all results to amazon_bestsellers_es.json")
        except IOError as e:
            print(f"\nError saving file: {e}")

    else:
        print("\nScraping failed or no books found. Please double-check selectors against 'amazon_bestsellers_page.html'.")