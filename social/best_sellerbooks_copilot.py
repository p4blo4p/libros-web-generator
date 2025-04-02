import requests
from bs4 import BeautifulSoup

# URL of Amazon best sellers books page
URL = "https://www.amazon.com/best-sellers-books-Amazon/zgbs/books"

# Headers to mimic a browser visit
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

def get_bestsellers_books(url):
    response = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(response.content, "html.parser")

    books = []
    for item in soup.select(".zg-item-immersion"):
        title = item.select_one(".p13n-sc-truncate-desktop-type2").get_text(strip=True)
        author = item.select_one(".a-link-child").get_text(strip=True) if item.select_one(".a-link-child") else "Unknown"
        price = item.select_one(".p13n-sc-price").get_text(strip=True) if item.select_one(".p13n-sc-price") else "Not available"
        
        books.append({
            "title": title,
            "author": author,
            "price": price
        })

    return books

def main():
    bestsellers = get_bestsellers_books(URL)
    for rank, book in enumerate(bestsellers, start=1):
        print(f"{rank}. {book['title']} by {book['author']} - {book['price']}")

if __name__ == "__main__":
    main()