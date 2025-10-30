from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json
import time

def scrape_kickass_anime():
    """
    Fungsi untuk melakukan scraping data anime terbaru dari kickass-anime.ru
    menggunakan Playwright untuk menangani konten dinamis dan mensimulasikan scrolling.
    """
    url = "https://kickass-anime.ru/"
    scraped_data = []

    print("Membuka browser dengan Playwright...")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            print(f"Mengambil data dari: {url}")
            # Pergi ke URL, tunggu hingga struktur dasar halaman (DOM) siap
            page.goto(url, timeout=90000, wait_until="domcontentloaded")

            # Tunggu hingga setidaknya beberapa item anime pertama muncul
            print("Menunggu konten awal dimuat...")
            page.wait_for_selector('div.latest-update div.show-item', timeout=60000)
            print("Konten awal ditemukan. Mulai proses scrolling...")

            # === LOGIKA SCROLLING BARU DIMULAI DI SINI ===
            last_height = page.evaluate("document.body.scrollHeight")
            
            while True:
                # Gulir ke bagian paling bawah halaman
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                print("Scroll ke bawah...")
                
                # Beri waktu agar konten baru dimuat oleh JavaScript
                time.sleep(3) # Anda mungkin perlu menyesuaikan waktu ini (misal: 5 detik jika koneksi lambat)

                # Hitung tinggi halaman yang baru setelah konten dimuat
                new_height = page.evaluate("document.body.scrollHeight")
                
                # Jika tinggi halaman tidak bertambah, berarti kita sudah sampai di paling bawah
                if new_height == last_height:
                    print("Telah mencapai bagian bawah halaman.")
                    break
                
                last_height = new_height
            # === LOGIKA SCROLLING SELESAI ===

            print("Mengambil seluruh konten HTML setelah di-scroll...")
            html_content = page.content()
            browser.close()

            # Parsing konten HTML dengan BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            latest_update_container = soup.find('div', class_='latest-update')
            anime_items = latest_update_container.find_all('div', class_='show-item')
            
            print(f"Menemukan {len(anime_items)} item anime setelah scrolling.")

            for item in anime_items:
                try:
                    title_element = item.find('h2', class_='show-title').find('a')
                    title = title_element.text.strip()
                    show_url = "https://kickass-anime.ru" + title_element['href']

                    episode_element = item.find('a', class_='v-card')
                    episode_url = "https://kickass-anime.ru" + episode_element['href']

                    poster_div = item.find('div', class_='v-image__image--cover')
                    poster_url = poster_div['style'].split('url("')[1].split('")')[0]

                    tags = [tag.text.strip() for tag in item.find_all('span', class_='v-chip__content')]

                    anime_data = {
                        'title': title,
                        'show_url': show_url,
                        'latest_episode_url': episode_url,
                        'poster_image_url': poster_url,
                        'tags': tags
                    }
                    scraped_data.append(anime_data)
                except (AttributeError, IndexError) as e:
                    print(f"Error parsing item: {e}. Melewati item ini.")
                    continue

        except Exception as e:
            print(f"Terjadi error saat menjalankan Playwright: {e}")
            if 'browser' in locals() and browser.is_connected():
                browser.close()
            return []
            
    return scraped_data

if __name__ == "__main__":
    data = scrape_kickass_anime()
    if data:
        with open('latest_anime.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"\nScraping berhasil! Total {len(data)} data disimpan di file 'latest_anime.json'")
    else:
        print("\nScraping gagal atau tidak ada data yang ditemukan. File JSON tidak dibuat.")
