import requests
from bs4 import BeautifulSoup
import json

def scrape_kickass_anime():
    """
    Fungsi untuk melakukan scraping data anime terbaru dari kickass-anime.ru.
    """
    url = "https://kickass-anime.ru/"
    
    # Header User-Agent penting untuk meniru browser agar tidak diblokir
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    print(f"Mengambil data dari: {url}")

    try:
        # Mengirim permintaan GET ke URL
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()  # Akan menampilkan error jika status code bukan 200
    except requests.exceptions.RequestException as e:
        print(f"Gagal mengambil halaman web: {e}")
        return []

    # Parsing konten HTML dengan BeautifulSoup
    soup = BeautifulSoup(response.content, 'html.parser')

    # Mencari kontainer utama dari daftar anime terbaru
    latest_update_container = soup.find('div', class_='latest-update')
    if not latest_update_container:
        print("Tidak dapat menemukan kontainer 'latest-update'. Struktur website mungkin telah berubah.")
        return []

    # Mencari semua item anime
    anime_items = latest_update_container.find_all('div', class_='show-item')
    
    scraped_data = []

    print(f"Menemukan {len(anime_items)} item anime.")

    # Loop melalui setiap item anime untuk mengekstrak data
    for item in anime_items:
        try:
            # 1. Judul dan URL Halaman Anime
            title_element = item.find('h2', class_='show-title').find('a')
            title = title_element.text.strip()
            show_url = "https://kickass-anime.ru" + title_element['href']

            # 2. URL Episode
            episode_element = item.find('a', class_='v-card')
            episode_url = "https://kickass-anime.ru" + episode_element['href']

            # 3. URL Gambar Poster
            poster_div = item.find('div', class_='v-image__image--cover')
            # Ekstrak URL dari style="background-image: url(...)"
            poster_url = poster_div['style'].split('url("')[1].split('")')[0]

            # 4. Tags (Tipe, Episode, Sub/Dub)
            tags = [tag.text.strip() for tag in item.find_all('span', class_='v-chip__content')]

            # Menyusun data dalam format dictionary
            anime_data = {
                'title': title,
                'show_url': show_url,
                'latest_episode_url': episode_url,
                'poster_image_url': poster_url,
                'tags': tags
            }
            scraped_data.append(anime_data)

        except (AttributeError, IndexError) as e:
            # Lewati item jika ada elemen yang tidak ditemukan untuk mencegah error
            print(f"Error parsing item: {e}. Melewati item ini.")
            continue
    
    return scraped_data

if __name__ == "__main__":
    data = scrape_kickass_anime()
    if data:
        # Menyimpan hasil ke dalam file JSON
        with open('latest_anime.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print("\nScraping berhasil! Data disimpan di file 'latest_anime.json'")
        # Cetak beberapa hasil pertama untuk verifikasi
        # print(json.dumps(data[:2], indent=4))
